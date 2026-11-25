"""Measure the contiguous execution-clock coverage in a live SP1 6.9 Core checkpoint."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import time

from index_archive import FIELDS, KOALABEAR_MODULUS, timestamp


CORE_HEADER_SIZE = 8 + FIELDS.size
SHA256 = re.compile(r'[a-f0-9]{64}')
MAX_METADATA_BYTES = 64 * 1024


def load_metadata(path):
    with path.open('rb') as stream:
        data = stream.read(MAX_METADATA_BYTES + 1)
    if not 0 < len(data) <= MAX_METADATA_BYTES:
        raise ValueError(f'invalid metadata size for {path}')
    return data, json.loads(data)


def execution_interval(header, nonce):
    if len(header) != CORE_HEADER_SIZE or struct.unpack_from('<Q', header)[0] != 187:
        raise ValueError('expected a complete SP1 6.9 Core public row')
    words = FIELDS.unpack_from(header, 8)
    if max(words) >= KOALABEAR_MODULUS or words[151] or any(words[156:]):
        raise ValueError('unsupported SP1 Core field encoding or layout')
    if words[152:156] != nonce:
        raise ValueError('Core checkpoint proof nonce differs from the run manifest')
    execution, first = words[88], words[150]
    start, end = timestamp(words[113:117]), timestamp(words[117:121])
    if execution == 0 and first == 0 and start == end:
        return None
    if execution != 1 or first != int(start == 1) or not 1 <= start < end:
        raise ValueError('invalid Core execution flags or clock interval')
    return start, end


def clock_frontier(intervals, global_clock):
    frontier = next_clock = 1
    contiguous = 0
    for start, end in sorted(intervals):
        if start < next_clock or end > global_clock + 1:
            raise ValueError('overlapping Core intervals or checkpoint exceeds the executed clock')
        if start == frontier:
            frontier = end
            contiguous += 1
        next_clock = end
    return frontier, contiguous, next_clock


def measure(run, execution):
    manifest_bytes, manifest = load_metadata(run / 'run.json')
    receipt_bytes, receipt = load_metadata(execution)
    config = manifest['config']
    elf_sha256 = config['elf_sha256']
    public_sha256 = manifest['expected_public_sha256']
    global_clock = receipt['global_clock']
    if (manifest['schema'], config['sp1_version']) != ('nb3-prover/core-run/v1', '6.9.0'):
        raise ValueError('expected an SP1 6.9 Core-only manifest')
    if (not SHA256.fullmatch(elf_sha256) or not SHA256.fullmatch(public_sha256)
            or (receipt['elf_sha256'], receipt['committed_values_sha256']) != (elf_sha256, public_sha256)
            or receipt['executor'] != 'sp1-minimal-untraced' or receipt['stage'] != 'guest_execution'
            or receipt['exit_code'] != 0 or type(global_clock) is not int or not 0 < global_clock < 1 << 48):
        raise ValueError('execution receipt does not match the checkpoint workload')
    uses_nonce = config.get('controller_nonce', False)
    nonce = tuple(config['nonce']) if uses_nonce else (0, 0, 0, 0)
    if (type(uses_nonce) is not bool or len(nonce) != 4
            or any(type(word) is not int or not 0 <= word < KOALABEAR_MODULUS for word in nonce)):
        raise ValueError('invalid effective controller nonce')

    interval_times = {}
    sampled_at = time.time()
    with os.scandir(run / 'memo/shard') as entries:
        paths = [Path(entry.path) / 'out0' for entry in entries
                 if SHA256.fullmatch(entry.name) and entry.is_dir(follow_symlinks=False)]
    for path in paths:
        with path.open('rb') as shard:
            interval = execution_interval(shard.read(CORE_HEADER_SIZE), nonce)
            if interval is not None:
                if interval in interval_times:
                    raise ValueError('duplicate Core execution interval')
                interval_times[interval] = os.fstat(shard.fileno()).st_mtime
    frontier, contiguous, furthest = clock_frontier(interval_times, global_clock)
    frontier_saved_at = max((saved_at for (_, end), saved_at in interval_times.items() if end <= frontier),
                            default=None)
    return {
        'schema': 'proof-grove-cashu/sp1-core-progress/v1',
        'sampled_at_unix': sampled_at,
        'scan_finished_at_unix': time.time(),
        'scope': 'Unverified contiguous Core execution clock. Memory, precompiles, recursion and settlement have separate progress.',
        'run_manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
        'execution_receipt_sha256': hashlib.sha256(receipt_bytes).hexdigest(),
        'elf_sha256': elf_sha256,
        'expected_public_sha256': public_sha256,
        'effective_nonce': nonce,
        'saved_core_memos': len(paths),
        'saved_execution_memos': len(interval_times),
        'contiguous_execution_memos': contiguous,
        'checkpoint_frontier_clock': frontier,
        'frontier_saved_at_unix': frontier_saved_at,
        'furthest_checkpoint_clock': furthest,
        'executed_global_clock': global_clock,
        'execution_clock_coverage_pct': round(100 * (frontier - 1) / global_clock, 4),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('execution_receipt', type=Path)
    args = parser.parse_args()
    print(json.dumps(measure(args.run, args.execution_receipt), indent=2))


if __name__ == '__main__':
    main()
