#!/usr/bin/env python3
"""Compare the pinned lifted Blake2s CUDA kernels with the stock tree layout."""

from contextlib import ExitStack
import ctypes as c
import hashlib
from itertools import groupby
import json
from pathlib import Path
import random
import runpy
import struct
import sys
from time import perf_counter


def bind(library, name, result, *arguments):
    function = getattr(library, name)
    function.argtypes = arguments
    function.restype = result
    return function


class Cuda:
    def __init__(self, kernels):
        runtime = c.CDLL('libcudart.so.12')
        pointer, integer, size = c.c_void_p, c.c_int, c.c_size_t
        self.error = bind(runtime, 'cudaGetErrorString', c.c_char_p, integer)
        self.set_device = bind(runtime, 'cudaSetDevice', integer, integer)
        self.get_attribute = bind(runtime, 'cudaDeviceGetAttribute', integer, c.POINTER(integer), integer, integer)
        self.mem_info = bind(runtime, 'cudaMemGetInfo', integer, c.POINTER(size), c.POINTER(size))
        self.malloc = bind(runtime, 'cudaMalloc', integer, c.POINTER(pointer), size)
        self.free = bind(runtime, 'cudaFree', integer, pointer)
        self.copy = bind(runtime, 'cudaMemcpy', integer, pointer, pointer, size, integer)
        self.sync = bind(runtime, 'cudaDeviceSynchronize', integer)
        self.last_error = bind(runtime, 'cudaGetLastError', integer)
        self.leaves = bind(kernels, 'cuda_build_leaves_lifted', None, pointer, pointer,
                           c.c_uint32, c.c_uint32, pointer, c.c_uint32)
        self.parents = bind(kernels, 'cuda_merkle_hash_nodes', None, pointer, pointer, c.c_uint32)

    def check(self, operation, code):
        if code:
            raise RuntimeError(f'{operation} failed with CUDA {code}: {self.error(code).decode()}')

    def allocate(self, stack, size, data=None):
        pointer = c.c_void_p()
        self.check('cudaMalloc', self.malloc(c.byref(pointer), size))
        stack.callback(lambda: self.check('cudaFree', self.free(pointer)))
        if data is not None:
            host = c.create_string_buffer(data, size)
            self.check('host-to-device upload', self.copy(pointer, c.addressof(host), size, 1))
        return pointer

    def read(self, pointer, size):
        host = c.create_string_buffer(size)
        self.check('device-to-host download', self.copy(c.addressof(host), pointer, size, 2))
        return host.raw

    def completed(self, name):
        self.check(f'{name} launch', self.last_error())
        self.check(f'{name} synchronization', self.sync())


def layout(cuda, columns, lifting, reference):
    count = 1 << lifting
    schedule = []
    for height, indexes in groupby(range(len(columns)), key=lambda i: len(columns[i]).bit_length() - 1):
        indices = list(indexes)
        for begin in range(0, len(indices), 16):
            chunk = indices[begin:begin + 16]
            schedule.append(struct.pack('<18I', *chunk, *([0] * (16 - len(chunk))), len(chunk), height))
    expected = reference(columns, count)
    start = perf_counter()
    with ExitStack() as stack:
        device_columns = []
        for column in columns:
            raw = struct.pack(f'<{len(column)}I', *column)
            device_columns.append(cuda.allocate(stack, len(raw), raw))
        pointers = (c.c_void_p * len(device_columns))(*(pointer.value for pointer in device_columns))
        table = cuda.allocate(stack, c.sizeof(pointers), bytes(pointers))
        chunks = cuda.allocate(stack, len(schedule) * 72, b''.join(schedule))
        current = cuda.allocate(stack, count * 32)
        cuda.leaves(table, chunks, len(schedule), lifting, current, count)
        cuda.completed('lifted Blake2s leaves')
        for level, hashes in enumerate(expected):
            if cuda.read(current, len(hashes) * 32) != b''.join(hashes):
                raise ValueError(f'CUDA hash mismatch at level {level} for {len(columns)} columns at lift {lifting}')
            if len(hashes) > 1:
                count = len(hashes) // 2
                parent = cuda.allocate(stack, count * 32)
                cuda.parents(current, parent, count)
                cuda.completed('Blake2s parent layer')
                current = parent
    return {'lifting_log_size': lifting, 'columns': len(columns), 'schedule_chunks': len(schedule),
            'hashes_matched': sum(map(len, expected)), 'kernel_launches': len(expected),
            'root': expected[-1][0].hex(), 'wall_seconds': perf_counter() - start}


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: check-cuda-merkle.py PINNED_LIBMERKLE.so')
    library = Path(sys.argv[1]).resolve(strict=True)
    stock = runpy.run_path(str(Path(__file__).with_name('check-layout.py')))
    reference, prime = stock['reference'], stock['P']
    cuda = Cuda(c.CDLL(str(library)))
    cuda.check('select device zero', cuda.set_device(0))
    free, total = c.c_size_t(), c.c_size_t()
    cuda.check('query device memory', cuda.mem_info(c.byref(free), c.byref(total)))
    capability = []
    for attribute in (75, 76):
        value = c.c_int()
        cuda.check('query compute capability', cuda.get_attribute(c.byref(value), attribute, 0))
        capability.append(value.value)
    rng = random.Random(23750)
    cases = []
    for lifting, heights in ((1, [1]), (3, [2, 3, 3]), (5, [2] * 15 + [5]),
                             (6, [3] * 17 + [5] * 16), (7, [5] * 17)):
        columns = [[rng.randrange(prime) for _ in range(1 << height)] for height in heights]
        for values in columns:
            values[0] = prime
            values[1] = 0
        cases.append(layout(cuda, columns, lifting, reference))
    with library.open('rb') as stream:
        library_digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    print(json.dumps({'schema': 'proof-grove/shinigami-cuda-blake2s-parity/v1',
                      'scope': 'actual lifted leaves and tree parents, every level compared',
                      'library_sha256': library_digest, 'compute_capability': capability,
                      'vram_free_bytes_at_start': free.value, 'vram_total_bytes': total.value,
                      'hashes_matched': sum(case['hashes_matched'] for case in cases),
                      'kernel_launches': sum(case['kernel_launches'] for case in cases), 'cases': cases}, indent=2))


if __name__ == '__main__':
    main()
