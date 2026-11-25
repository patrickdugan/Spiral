import struct
import unittest

import index_archive as index
from plan_prefix import candidate_path


class ArchiveTests(unittest.TestCase):
    def test_timestamp_uses_sp1_mixed_limb_widths(self):
        self.assertEqual(index.timestamp((1, 2, 3, 4)), 0x1_0203_0004)
        self.assertEqual(index.timestamp((0, 0, 59, 53937)), 3920561)
        with self.assertRaisesRegex(ValueError, 'timestamp limb'):
            index.timestamp((0, 256, 0, 0))

    def test_public_row_rejects_nonce_and_length_changes(self):
        row = bytearray(index.FIELDS.size)
        row[136 * 4:144 * 4] = index.PROGRAM_KEY
        prefix = bytes(104) + struct.pack('<Q', 187)
        self.assertEqual(index.public_row(prefix + row)[0], row)
        with self.assertRaisesRegex(ValueError, 'public row'):
            index.public_row(bytes(104) + struct.pack('<Q', 188) + row)
        row[183 * 4] = 1
        with self.assertRaisesRegex(ValueError, 'effective nonce'):
            index.public_row(prefix + row)

    def test_candidate_path_prefers_a_reduction_and_ignores_disconnected_rows(self):
        def edge(start, end, count=1):
            return {'before': str(start), 'after': str(end), 'timestamp': [start, end],
                    'included_core_shards': count, 'contains_first_shard': start == 0}

        entries = {'shard/a': edge(0, 1), 'shard/b': edge(1, 2), 'reduce/ab': edge(0, 2, 2),
                   'shard/c': edge(2, 3), 'shard/d': edge(3, 4), 'shard/e': edge(4, 5),
                   'shard/unconnected': edge(6, 10)}
        self.assertEqual(candidate_path(entries, 'shard/a'), ['reduce/ab', 'shard/c', 'shard/d', 'shard/e'])


if __name__ == '__main__':
    unittest.main()
