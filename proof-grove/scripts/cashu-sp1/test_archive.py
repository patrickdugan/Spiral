import struct
import unittest

import index_archive as index
from core_progress import clock_frontier, execution_interval, execution_reference
from measure_core_window import compare_reference_clock
from plan_prefix import candidate_path
from project_core_storage import storage_sample
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
        self.assertEqual(clock_frontier([(1, 51)], None), (51, 1, 51))

    def test_storage_projection_uses_settled_memos_without_flushing_the_live_volume(self):
        events = [{'t': stamp} for stamp in (100, 160, 200, 230, 260, 300)]
        self.assertEqual(storage_sample(events, 2, now=320, minimum_age=120), events[1:3])
        self.assertEqual(storage_sample(events, 2, now=320, minimum_age=0), events[-2:])
        with self.assertRaisesRegex(ValueError, 'not enough settled'):
            storage_sample(events, 2, now=250, minimum_age=120)

    def test_live_clock_overrun_supersedes_the_reference_estimate(self):
        missing = compare_reference_clock(11, None, 2)
        self.assertEqual(missing['reference_clock_status'], 'trace_clock_unavailable')
        self.assertIsNone(missing['position_as_pct_of_guest_clock'])
        self.assertIsNone(missing['execution_clock_hours_if_same_rate'])
        within = compare_reference_clock(11, 20, 2)
        self.assertEqual(within['position_as_pct_of_guest_clock'], 50)
        self.assertEqual(within['execution_clock_hours_if_same_rate'], 5 / 3600)
        self.assertEqual(compare_reference_clock(21, 20, 2)['reference_clock_excess_ticks'], 0)
        exceeded = compare_reference_clock(22, 20, 2)
        self.assertEqual((exceeded['reference_clock_status'], exceeded['reference_clock_excess_ticks']), ('exceeded', 1))
        self.assertIsNone(exceeded['position_as_pct_of_guest_clock'])
        self.assertIsNone(exceeded['execution_clock_hours_if_same_rate'])

    def test_legacy_instruction_count_cannot_be_used_as_a_trace_clock(self):
        elf, public = 'aa' * 32, 'bb' * 32
        manifest = {'schema': 'nb3-prover/core-run/v1', 'expected_public_sha256': public,
                    'config': {'sp1_version': '6.9.0', 'elf_sha256': elf}}
        receipt = {'executor': 'sp1-minimal-untraced', 'stage': 'guest_execution',
                   'elf_sha256': elf, 'committed_values_sha256': public, 'exit_code': 0, 'global_clock': 20}
        self.assertEqual(execution_reference(manifest, receipt), (20, None))
        exact = receipt | {'instruction_count': 20, 'trace_clock': 161, 'trace_clock_domain': 'sp1_core_timestamp'}
        self.assertEqual(execution_reference(manifest, exact), (20, 161))
        with self.assertRaisesRegex(ValueError, 'invalid trace clock'):
            execution_reference(manifest, exact | {'trace_clock_domain': 'rv64_instruction_count'})
        with self.assertRaisesRegex(ValueError, 'checkpoint workload'):
            execution_reference(manifest, exact | {'committed_values_sha256': 'cc' * 32})

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
