import json
import os
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import index_archive as index
from core_progress import clock_frontier, execution_interval, execution_reference
from measure_core_window import compare_reference_clock, follow, publish_window
from plan_prefix import candidate_path
from project_core_storage import project, storage_sample
from verify_prefix import check_chain


class ArchiveTests(unittest.TestCase):
    def test_published_clock_advances_for_the_same_withdrawal_and_reference(self):
        window = {'run_manifest_sha256': 'run', 'execution_receipt_sha256': 'reference',
                  'last_execution_clock': 100, 'window_ended_unix': 900}
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'window.json'
            self.assertTrue(publish_window(path, window))
            self.assertFalse(publish_window(path, {**window, 'last_execution_clock': 99, 'window_ended_unix': 901}))
            self.assertFalse(publish_window(path, {**window, 'last_execution_clock': 101, 'window_ended_unix': 899}))
            with self.assertRaisesRegex(ValueError, 'different withdrawal or execution receipt'):
                publish_window(path, {**window, 'execution_receipt_sha256': 'substitute'})
            self.assertTrue(publish_window(path, {**window, 'last_execution_clock': 101, 'window_ended_unix': 901}))
            self.assertEqual(json.loads(path.read_bytes())['last_execution_clock'], 101)
            self.assertTrue(publish_window(path, window, require_advance=False))
            self.assertEqual(json.loads(path.read_bytes()), window)

    def test_clock_follower_stops_without_publishing_if_worker_identity_changes(self):
        args = SimpleNamespace(follow_worker=(79, 4563), run=None, report=None,
                               previous_coverage=None, execution_receipt=None)
        with (patch('measure_core_window.worker_start_ticks', side_effect=[4563, 4563, 9999]),
              patch('measure_core_window.measure', return_value={'reference_clock_status': 'within_reference'}),
              patch('measure_core_window.publish_window') as publish):
            follow(args)
        publish.assert_not_called()

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

    @unittest.skipUnless(hasattr(os, 'statvfs'), 'requires POSIX filesystem accounting')
    def test_storage_projection_skips_non_execution_shards_only_for_the_clock_and_future_sizes(self):
        with TemporaryDirectory() as directory:
            run = Path(directory)
            elf, public = 'aa' * 32, 'bb' * 32
            (run / 'run.json').write_text(json.dumps({
                'schema': 'nb3-prover/core-run/v1', 'expected_public_sha256': public,
                'config': {'sp1_version': '6.9.0', 'elf_sha256': elf},
            }))
            receipt = run / 'receipt.json'
            receipt.write_text(json.dumps({
                'executor': 'sp1-minimal-untraced', 'stage': 'guest_execution', 'elf_sha256': elf,
                'committed_values_sha256': public, 'exit_code': 0, 'instruction_count': 5,
                'trace_clock': 40, 'trace_clock_domain': 'sp1_core_timestamp',
            }))
            samples = ((11, 21, 1600), (11, 11, 2000), (1, 11, 1200))
            events = []
            for ordinal, (start, end, size) in enumerate(samples, 1):
                key = f'{ordinal:016x}'
                memo = run / 'memo/shard' / (key + '0' * 48)
                memo.mkdir(parents=True)
                words = [0] * 187
                words[88], words[150] = int(start != end), int(start == 1)
                words[116], words[120] = start, end
                header = struct.pack('<Q187I', 187, *words)
                (memo / 'out0').write_bytes(header + bytes(size - len(header)))
                events.append(json.dumps({'key': key, 'kind': 'shard', 'replayed': False, 't': ordinal}))
            (run / 'progress.jsonl').write_text('\n'.join(events) + '\n')
            extents = [{'logical_bytes': size, 'physical_extent_bytes': size // 2} for _, _, size in samples]
            with patch('btrfs_extent_usage.usage', side_effect=extents):
                result = project(run, receipt, run, {'compressed_data_bytes': 1, 'logical_shard_bytes': 2},
                                 0, 0, 3, btrfs_extents=True)
            self.assertEqual((result['sampled_execution_shards'], result['sampled_non_execution_shards']), (2, 1))
            self.assertEqual(result['estimated_remaining_execution_shards'], 2)
            self.assertEqual(result['estimated_uncompressed_archive_bytes'], 7600)
            self.assertEqual(result['sampled_average_memo_extent_bytes'], 800)
            self.assertEqual(result['sampled_average_execution_memo_extent_bytes'], 700)
            self.assertEqual(result['estimated_additional_memo_extent_bytes'], 1400)
            mixed = result['same_sample_mix']
            self.assertEqual(mixed['estimated_remaining_non_execution_shards'], 1)
            self.assertEqual(mixed['estimated_uncompressed_archive_bytes'], 9600)
            self.assertEqual(mixed['estimated_archive_bytes_at_pilot_ratio'], 4800)
            self.assertEqual(mixed['estimated_additional_memo_extent_bytes'], 2400)

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
