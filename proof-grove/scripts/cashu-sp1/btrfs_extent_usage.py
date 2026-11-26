"""Read physical Btrfs data extents for already written regular files on Linux x86-64."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import stat
import struct


# Kernel UAPI types in linux/btrfs.h and linux/btrfs_tree.h.
SEARCH_KEY = struct.Struct('=7Q4I4Q')
BUFFER_SIZE = struct.Struct('=Q')
ITEM_HEADER = struct.Struct('=QQQII')
FILE_EXTENT = struct.Struct('<QQBBHBQQQQ')
EXTENT_DATA_KEY = 108
SEARCH_V2 = (3 << 30) | ((SEARCH_KEY.size + BUFFER_SIZE.size) << 16) | (0x94 << 8) | 17
MAX_ITEMS = 4096
ITEM_BUFFER = MAX_ITEMS * (ITEM_HEADER.size + FILE_EXTENT.size)
U64_MAX = (1 << 64) - 1


def usage(path):
    buffer = bytearray(SEARCH_KEY.size + BUFFER_SIZE.size + ITEM_BUFFER)
    with path.open('rb') as stream:
        meta = os.fstat(stream.fileno())
        if not stat.S_ISREG(meta.st_mode) or meta.st_size <= 0:
            raise ValueError('expected a nonempty regular file')
        SEARCH_KEY.pack_into(buffer, 0, 0, meta.st_ino, meta.st_ino, 0, U64_MAX, 0, U64_MAX,
                             EXTENT_DATA_KEY, EXTENT_DATA_KEY, MAX_ITEMS, 0, 0, 0, 0, 0)
        BUFFER_SIZE.pack_into(buffer, SEARCH_KEY.size, ITEM_BUFFER)
        fcntl.ioctl(stream, SEARCH_V2, buffer, True)
    count = SEARCH_KEY.unpack_from(buffer)[9]
    if not 0 < count <= MAX_ITEMS:
        raise ValueError('no bounded file data extents were returned')
    pointer = SEARCH_KEY.size + BUFFER_SIZE.size
    logical_end = 0
    extents = {}
    for _ in range(count):
        _, inode, logical, tag, length = ITEM_HEADER.unpack_from(buffer, pointer)
        pointer += ITEM_HEADER.size
        if (inode != meta.st_ino or tag != EXTENT_DATA_KEY or length != FILE_EXTENT.size
                or logical != logical_end or pointer + length > len(buffer)):
            raise ValueError('unsupported or discontinuous file extent metadata')
        _, _, compression, encryption, other, kind, disk, physical, _, logical_size = FILE_EXTENT.unpack_from(buffer, pointer)
        if kind != 1 or encryption or other or not disk or not physical or not logical_size:
            raise ValueError('expected regular allocated data extents')
        extents[disk, physical] = compression
        logical_end += logical_size
        pointer += length
    # The last extent can be rounded to a sector beyond EOF.
    if not meta.st_size <= logical_end < meta.st_size + 65536:
        raise ValueError('extent metadata did not cover the file')
    return {
        'path': str(path), 'logical_bytes': meta.st_size, 'covered_bytes': logical_end,
        'physical_extent_bytes': sum(size for _, size in extents),
        'compressed_extent_bytes': sum(size for (_, size), codec in extents.items() if codec),
        'distinct_extents': len(extents),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+', type=Path)
    options = parser.parse_args()
    try:
        results = [usage(path) for path in options.files]
    except (OSError, ValueError, struct.error) as error:
        parser.exit(1, f'Btrfs extent measurement refused: {error}\n')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
