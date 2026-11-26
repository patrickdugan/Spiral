"""Measure a small raw Core checkpoint window and project archive disk use."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import time

from core_progress import CORE_HEADER_SIZE, SHA256, execution_interval, execution_reference, load_metadata


BTRFS_EXTENT_SETTLE_SECONDS = 120


def memo_events(progress):
    events = []
    seen = set()
    with progress.open('rb') as stream:
        for line in stream:
            if not line.endswith(b'\n'):
                break
            event = json.loads(line)
            if event.get('kind') == 'shard' and event.get('replayed') is False:
                key = event['key']
                if (not isinstance(key, str) or len(key) != 16 or any(char not in '0123456789abcdef' for char in key)
                        or key in seen or type(event['t']) is not int):
                    raise ValueError('duplicate or invalid durable shard event')
                seen.add(key)
                events.append(event)
    return events


def storage_sample(events, sample_count, *, now, minimum_age):
    # Publication precedes compressed extent writeback. Read settled files
    # without flushing the live prover's filesystem or changing its I/O load.
    end = len(events)
    while end and events[end - 1]['t'] > now - minimum_age:
        end -= 1
    sample = events[max(0, end - sample_count):end]
    if len(sample) != sample_count or any(event['t'] > now - minimum_age for event in sample):
        raise ValueError('not enough settled shard events for a storage sample')
    return sample


def project(run, execution, filesystem, pilot, baseline_bytes, baseline_shards, sample_count, *, btrfs_extents=False):
    manifest_data, manifest = load_metadata(run / 'run.json')
    execution_data, receipt = load_metadata(execution)
    _, trace_clock = execution_reference(manifest, receipt)
    if trace_clock is None:
        raise ValueError('an independently measured SP1 trace clock is required')
    events = memo_events(run / 'progress.jsonl')
    if not 2 <= sample_count <= 64 or len(events) < sample_count or not 0 <= baseline_shards < len(events):
        raise ValueError('expected a bounded shard sample and an earlier filesystem baseline')
    sampled_at = time.time()
    minimum_age = BTRFS_EXTENT_SETTLE_SECONDS if btrfs_extents else 0
    sample = storage_sample(events, sample_count, now=sampled_at, minimum_age=minimum_age)
    keys = {event['key'] for event in sample}
    locations = {}
    with os.scandir(run / 'memo/shard') as candidates:
        for entry in candidates:
            prefix = entry.name[:16]
            if prefix in keys and SHA256.fullmatch(entry.name) and entry.is_dir(follow_symlinks=False):
                if prefix in locations:
                    raise ValueError('ambiguous shard key in the sampled checkpoint')
                locations[prefix] = Path(entry.path) / 'out0'
    if locations.keys() != keys:
        raise ValueError('a sampled durable shard is missing')
    config = manifest['config']
    nonce = tuple(config['nonce']) if config.get('controller_nonce') is True else (0, 0, 0, 0)
    ranges, sizes, accounted_sizes, link_counts = [], [], [], []
    for event in sample:
        with locations[event['key']].open('rb') as proof:
            interval = execution_interval(proof.read(CORE_HEADER_SIZE), nonce)
            size = os.fstat(proof.fileno())
        if interval is None or interval[1] > trace_clock + 1:
            raise ValueError('the sampled suffix is not execution-clock work')
        ranges.append(interval)
        sizes.append(size.st_size)
        accounted_sizes.append(size.st_blocks * 512)
        link_counts.append(size.st_nlink)
    if any(left[1] != right[0] for left, right in zip(ranges, ranges[1:])):
        raise ValueError('the measured execution shards do not form a contiguous suffix')

    fs = os.statvfs(filesystem)
    used = (fs.f_blocks - fs.f_bfree) * fs.f_frsize
    available = fs.f_bavail * fs.f_frsize
    if used <= baseline_bytes or baseline_bytes < 0:
        raise ValueError('filesystem occupancy did not advance from its supplied baseline')
    growth = (used - baseline_bytes) / (len(events) - baseline_shards)
    ticks_per_shard = (ranges[-1][1] - ranges[0][0]) / sample_count
    remaining = math.ceil((trace_clock - (ranges[-1][1] - 1)) / ticks_per_shard)
    total_execution_estimate = len(events) + remaining
    average_logical = sum(sizes) / sample_count
    archive_logical = math.ceil(total_execution_estimate * average_logical)
    pilot_data = pilot['compressed_data_bytes']
    pilot_logical = pilot['logical_shard_bytes']
    if not 0 < pilot_data <= pilot_logical:
        raise ValueError('invalid independent filesystem compression measurement')
    archive_pilot = math.ceil(archive_logical * pilot_data / pilot_logical)
    projected_growth = math.ceil(remaining * growth)
    result = {
        'schema': 'proof-grove/cashu-core-storage-projection/v1',
        'scope': ('Execution-shard storage projection. Future non-execution shards, filesystem metadata, '
                  'archive compression differences, and recursive artifacts are additional work.'),
        'run_manifest_sha256': hashlib.sha256(manifest_data).hexdigest(),
        'execution_receipt_sha256': hashlib.sha256(execution_data).hexdigest(),
        'baseline_filesystem_used_bytes': baseline_bytes,
        'baseline_saved_shards': baseline_shards,
        'saved_shards': len(events),
        'sampled_shards': sample_count,
        'sampled_at_unix': sampled_at,
        'sample_latest_event_unix': sample[-1]['t'],
        'sample_minimum_age_seconds': minimum_age,
        'sampled_average_logical_bytes': average_logical,
        'sampled_average_inode_accounted_bytes': sum(accounted_sizes) / sample_count,
        'observed_filesystem_growth_bytes_per_shard': growth,
        'execution_clock_pct': 100 * (ranges[-1][1] - 1) / trace_clock,
        'estimated_remaining_execution_shards': remaining,
        'filesystem_used_bytes': used,
        'filesystem_available_bytes': available,
        'estimated_additional_live_bytes': projected_growth,
        'estimated_uncompressed_archive_bytes': archive_logical,
        'estimated_archive_bytes_at_pilot_ratio': archive_pilot,
        'estimated_headroom_at_pilot_ratio_bytes': available - projected_growth - archive_pilot,
        'estimated_headroom_without_archive_compression_bytes': available - projected_growth - archive_logical,
    }
    if btrfs_extents:
        from btrfs_extent_usage import usage

        extents = [usage(locations[event['key']]) for event in sample]
        if any(extent['logical_bytes'] != size for extent, size in zip(extents, sizes, strict=True)):
            raise ValueError('a sampled shard changed during extent measurement')
        average_physical = sum(extent['physical_extent_bytes'] for extent in extents) / sample_count
        projected_memos = math.ceil(remaining * average_physical)
        result.update({
            'sampled_average_memo_extent_bytes': average_physical,
            'sampled_memos_with_multiple_links': sum(count > 1 for count in link_counts),
            'estimated_additional_memo_extent_bytes': projected_memos,
            'headroom_after_memo_extents_and_archive_bytes': available - projected_memos - archive_pilot,
        'memo_extent_scope': ('Settled data extents only, before other live artifacts and filesystem overhead. '
                              'Work committed after the sample is included in the remaining-work allowance.'),
        })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('execution', type=Path)
    parser.add_argument('filesystem', type=Path)
    parser.add_argument('compression_pilot', type=Path)
    parser.add_argument('--baseline-used-bytes', type=int, required=True)
    parser.add_argument('--baseline-shards', type=int, required=True)
    parser.add_argument('--sample', type=int, default=32)
    parser.add_argument('--measure-btrfs-extents', action='store_true', help='read each sampled memo’s Btrfs extent metadata')
    args = parser.parse_args()
    try:
        pilot_data, pilot = load_metadata(args.compression_pilot)
        result = project(args.run, args.execution, args.filesystem, pilot, args.baseline_used_bytes,
                         args.baseline_shards, args.sample, btrfs_extents=args.measure_btrfs_extents)
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(1, f'Core storage projection unavailable: {error}\n')
    result['compression_sample_sha256'] = hashlib.sha256(pilot_data).hexdigest()
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
