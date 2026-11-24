#!/usr/bin/env python3
"""Cross-check the overlay's raw-word projection and file offsets."""

import hashlib
import json
import random
import struct
import tempfile

P = 2**31 - 1


def grow(states, size):
    while len(states) < size:
        states = [states[index + parity].copy() for index in range(0, len(states), 2)
                  for parity in (0, 1, 0, 1)]
    return states


def reference(columns, size):
    states = [hashlib.blake2s(), hashlib.blake2s()]
    for column in columns:
        states = grow(states, len(column))
        for state, raw in zip(states, column):
            state.update(struct.pack('<I', raw))
    levels = [[state.digest() for state in grow(states, size)]]
    while len(levels[-1]) > 1:
        child = levels[-1]
        levels.append([hashlib.blake2s(child[index] + child[index + 1]).digest()
                       for index in range(0, len(child), 2)])
    return levels


def check_file_layout(columns, log_size, batch):
    size = 1 << log_size
    expected = reference(columns, size)
    shifts = [log_size - (len(column).bit_length() - 1) for column in columns]
    with tempfile.TemporaryFile() as tree:
        for leaf in range(size):
            words = [col[((leaf >> (shift + 1)) << 1) + (leaf & 1)] for col, shift in zip(columns, shifts)]
            tree.write(hashlib.blake2s(struct.pack(f'<{len(words)}I', *words)).digest())
        offsets = [0]
        for height in range(log_size - 1, -1, -1):
            children = offsets[-1]
            parents = children + (1 << (height + 1)) * 32
            offsets.append(parents)
            width = 1 << height
            for first in range(0, width, batch):
                count = min(batch, width - first)
                tree.seek(children + first * 64)
                data = tree.read(count * 64)
                assert len(data) == count * 64
                tree.seek(parents + first * 32)
                for index in range(0, len(data), 64):
                    tree.write(hashlib.blake2s(data[index:index + 64]).digest())
        for offset, hashes in zip(offsets, expected):
            tree.seek(offset)
            assert tree.read(len(hashes) * 32) == b''.join(hashes)
    reduced = [[0 if value == P else value for value in col] for col in columns]
    assert expected[-1] != reference(reduced, size)[-1], 'raw-zero alias must change the stock leaf bytes'
    return sum(map(len, expected))


def main():
    assert hashlib.blake2s(struct.pack('<I', P)).hexdigest() == (
        'f5d1a320fdf3c0d1df822e9e7730252047751647702c39e4dfc2bcd7fd69ef1a')
    rng = random.Random(23750)
    shapes = [(1, 1, 1), (3, 5, 6), (4, 6, 7)]
    layouts = digests = 0
    for minimum, tallest, lifting in shapes:
        for columns in (1, 15, 16, 17, 31, 32, 33):
            heights = sorted([minimum, *(rng.randint(minimum, tallest) for _ in range(columns - 1))])
            values = [[rng.randrange(P) for _ in range(1 << height)] for height in heights]
            for entries in values:
                for row in (0, 1, len(entries) // 2, len(entries) - 1):
                    entries[row] = P
            for batch in (1, 7, 32):
                layouts += 1
                digests += check_file_layout(values, lifting, batch)
    print(json.dumps({'schema': 'proof-grove/raw-blake2s-layout/v1', 'layouts': layouts,
                      'digests_matched': digests, 'compiled_stwo_test': False}))


if __name__ == '__main__':
    main()
