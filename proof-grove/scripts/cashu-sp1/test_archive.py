import struct
import unittest

import index_archive as index
from core_progress import clock_frontier, execution_interval
from measure_core_window import compare_reference_clock
from plan_prefix import candidate_path
from verify_prefix import check_chain


class ArchiveTests(unittest.TestCase):
    def test_timestamp_uses_sp1_mixed_limb_widths(self):
        self.assertEqual(index.timestamp((1, 2, 3, 4)), 0x1_0203_0004)
        self.assertEqual(index.timestamp((0, 0, 59, 53937)), 3920561)
        with self.assertRaisesRegex(ValueError, 'timestamp limb'):
            index.timestamp((0, 256, 0, 0))

    def test_core_public_header_binds_the_nonce_and_execution_range(self):
        words = [0] * 187
        words[88] = words[150] = 1
        words[116] = 1
        words[117:121] = [0, 0, 59, 53937]
        words[152:156] = [5, 6, 7, 8]
        def encode():
            return struct.pack('<Q187I', 187, *words)
        self.assertEqual(execution_interval(encode(), (5, 6, 7, 8)), (1, 3920561))
        with self.assertRaisesRegex(ValueError, 'nonce'):
            execution_interval(encode(), (0, 0, 0, 0))
        with self.assertRaisesRegex(ValueError, 'complete'):
            execution_interval(encode()[:-1], (5, 6, 7, 8))
        words[88] = words[150] = 0
        words[117:121] = words[113:117]
        self.assertIsNone(execution_interval(encode(), (5, 6, 7, 8)))
        words[156] = 1
        with self.assertRaisesRegex(ValueError, 'layout'):
            execution_interval(encode(), (5, 6, 7, 8))

    def test_core_clock_frontier_stops_at_the_first_missing_execution_interval(self):
        self.assertEqual(clock_frontier([(31, 40), (1, 11), (11, 21)], 49), (21, 2, 40))
        self.assertEqual(clock_frontier([(1, 50)], 49), (50, 1, 50))
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            clock_frontier([(1, 11), (10, 12)], 49)
        with self.assertRaisesRegex(ValueError, 'executed clock'):
            clock_frontier([(1, 51)], 49)

    def test_live_clock_overrun_supersedes_the_reference_estimate(self):
        within = compare_reference_clock(11, 20, 2)
        self.assertEqual(within['position_as_pct_of_guest_clock'], 50)
        self.assertEqual(within['execution_clock_hours_if_same_rate'], 5 / 3600)
        self.assertEqual(compare_reference_clock(21, 20, 2)['reference_clock_excess_ticks'], 0)
        exceeded = compare_reference_clock(22, 20, 2)
        self.assertEqual((exceeded['reference_clock_status'], exceeded['reference_clock_excess_ticks']), ('exceeded', 1))
        self.assertIsNone(exceeded['position_as_pct_of_guest_clock'])
        self.assertIsNone(exceeded['execution_clock_hours_if_same_rate'])

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

    def test_verified_prefix_requires_exact_order_and_boundaries(self):
        first = {'entry': 'reduce/' + 'a' * 64, 'before': 'start', 'after': 'middle',
                 'timestamp': [1, 10], 'contains_first_shard': True,
                 'complete_flag': False, 'exit_code': 0, 'included_core_shards': 355}
        second = {'entry': 'shard/' + 'b' * 64, 'before': 'middle', 'after': 'end',
                  'timestamp': [10, 20], 'contains_first_shard': False,
                  'complete_flag': False, 'exit_code': 0, 'included_core_shards': 1}
        self.assertEqual(check_chain([first, second]), 356)
        for changed, error in [
            ({'before': 'other state'}, 'disconnected public rows'),
            ({'timestamp': [11, 20]}, 'disconnected public rows'),
            ({'entry': first['entry']}, 'duplicate or invalid proof'),
            ({'contains_first_shard': True}, 'first-shard flag'),
            ({'complete_flag': True}, 'unexpected completion'),
        ]:
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, error):
                check_chain([first, {**second, **changed}])
        with self.assertRaisesRegex(ValueError, 'does not start'):
            check_chain([second, first])


if __name__ == '__main__':
    unittest.main()
