"""Measure fresh withdrawal execution shards without rereading the whole checkpoint."""

import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from core_progress import CORE_HEADER_SIZE, execution_interval, load_metadata


def measure(run, report, previous):
    previous_bytes, sample = load_metadata(previous)
    manifest_bytes, manifest = load_metadata(run / "run.json")
    manifest_pin = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_pin != sample["run_manifest_sha256"] or (
        manifest["expected_public_sha256"] != sample["expected_public_sha256"]
    ):
        raise ValueError("the fresh window belongs to a different withdrawal")
    baseline = int((report / "progress-baseline-bytes.txt").read_text())
    events = deque(maxlen=512)
    with (run / "progress.jsonl").open("rb") as stream:
        stream.seek(baseline)
        for raw in stream:
            if not raw.endswith(b"\n"):
                break
            event = json.loads(raw)
            if event["kind"] == "shard" and event["replayed"] is False:
                events.append(event)
    if not events or events[-1]["t"] - events[0]["t"] < 180:
        sys.exit(f"Fresh execution measurement needs at least 180 seconds, {len(events)} new shard events recorded")
    times = {event["key"]: event["t"] for event in events}
    if len(times) != len(events) or any(not re.fullmatch(r"[0-9a-f]{16}", key) for key in times):
        raise ValueError("duplicate or noncanonical progress keys")

    paths = {}
    with os.scandir(run / "memo/shard") as entries:
        for entry in entries:
            key = entry.name[:16]
            if key not in times or not re.fullmatch(r"[0-9a-f]{64}", entry.name):
                continue
            if key in paths or not entry.is_dir(follow_symlinks=False):
                raise ValueError("ambiguous saved checkpoint path")
            paths[key] = Path(entry.path) / "out0"
    if paths.keys() != times.keys():
        raise ValueError("fresh progress includes a missing saved shard")
    intervals = []
    nonce = tuple(sample["effective_nonce"])
    for key, path in paths.items():
        with path.open("rb") as stream:
            interval = execution_interval(stream.read(CORE_HEADER_SIZE), nonce)
        if interval is not None:
            intervals.append((*interval, times[key]))
    intervals.sort()
    if not intervals:
        raise ValueError("no fresh execution intervals")
    contiguous = [intervals[0]]
    for interval in intervals[1:]:
        if interval[0] < contiguous[-1][1]:
            raise ValueError("overlapping fresh execution clock intervals")
        if interval[0] != contiguous[-1][1]:
            break
        contiguous.append(interval)
    first = min(stamp for _, _, stamp in contiguous)
    last = max(stamp for _, _, stamp in contiguous)
    if last - first < 180:
        sys.exit("Waiting for 180 seconds of contiguous fresh execution slices")
    clock = sample["executed_global_clock"]
    first_tick = contiguous[0][0]
    frontier = contiguous[-1][1]
    if not sample["checkpoint_frontier_clock"] <= first_tick < frontier <= clock + 1:
        raise ValueError("fresh intervals are outside the independently measured guest clock")
    ticks = sum(end - start for start, end, stamp in contiguous if stamp > first)
    rate = ticks / (last - first)
    return {
        "scope": "Fresh execution-clock window only. Recursion, archive verification, wrap and payout are separate.",
        "run_manifest_sha256": manifest_pin,
        "prior_coverage_sha256": hashlib.sha256(previous_bytes).hexdigest(),
        "fresh_shard_events": len(events),
        "contiguous_execution_shards_measured": len(contiguous),
        "window_started_unix": first,
        "window_ended_unix": last,
        "window_seconds": last - first,
        "first_execution_clock": first_tick,
        "last_execution_clock": frontier,
        "position_as_pct_of_guest_clock": round(100 * (frontier - 1) / clock, 4),
        "clock_ticks_per_second": rate,
        "execution_clock_hours_if_same_rate": (clock - (frontier - 1)) / rate / 3600,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("previous_coverage", type=Path)
    args = parser.parse_args()
    print(json.dumps(measure(args.run, args.report, args.previous_coverage), indent=2))
