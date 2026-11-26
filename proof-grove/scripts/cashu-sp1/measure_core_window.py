"""Measure fresh withdrawal execution shards without rereading the whole checkpoint."""

import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time

from core_progress import CORE_HEADER_SIZE, execution_interval, execution_reference, load_metadata


class MeasurementPending(Exception):
    """The live worker has not saved enough contiguous execution yet."""


def compare_reference_clock(frontier, reference, rate):
    if reference is None:
        return {"reference_clock_status": "trace_clock_unavailable", "reference_clock_excess_ticks": None,
                "position_as_pct_of_guest_clock": None, "execution_clock_hours_if_same_rate": None}
    executed = frontier - 1
    if executed > reference:
        return {"reference_clock_status": "exceeded", "reference_clock_excess_ticks": executed - reference,
                "position_as_pct_of_guest_clock": None, "execution_clock_hours_if_same_rate": None}
    return {"reference_clock_status": "within_reference", "reference_clock_excess_ticks": 0,
            "position_as_pct_of_guest_clock": round(100 * executed / reference, 4),
            "execution_clock_hours_if_same_rate": (reference - executed) / rate / 3600}


def measure(run, report, previous, execution_receipt=None):
    previous_bytes, sample = load_metadata(previous)
    manifest_bytes, manifest = load_metadata(run / "run.json")
    manifest_pin = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_pin != sample["run_manifest_sha256"] or (
        manifest["expected_public_sha256"] != sample["expected_public_sha256"]
    ):
        raise ValueError("the fresh window belongs to a different withdrawal")
    clock = sample.get("reference_trace_clock")
    instructions = sample.get("reference_instruction_count", sample.get("executed_global_clock"))
    receipt_pin = sample.get("execution_receipt_sha256")
    if execution_receipt is not None:
        receipt_bytes, receipt = load_metadata(execution_receipt)
        instructions, clock = execution_reference(manifest, receipt)
        receipt_pin = hashlib.sha256(receipt_bytes).hexdigest()
    if clock is not None and (type(clock) is not int or not 0 < clock < 1 << 48):
        raise ValueError("invalid independently measured reference clock")
    baseline = int((report / "progress-baseline-bytes.txt").read_text())
    events = deque(maxlen=512)
    progress = report / "progress.jsonl"
    if not progress.is_file():
        progress = run / "progress.jsonl"
    with progress.open("rb") as stream:
        stream.seek(baseline)
        for raw in stream:
            if not raw.endswith(b"\n"):
                break
            event = json.loads(raw)
            if event["kind"] == "shard" and event["replayed"] is False:
                events.append(event)
    if not events or events[-1]["t"] - events[0]["t"] < 180:
        raise MeasurementPending(f"Need 180 seconds of new shard events, recorded {len(events)} events")
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
        raise MeasurementPending("Waiting for fresh execution intervals")
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
        raise MeasurementPending("Waiting for 180 seconds of contiguous fresh execution slices")
    first_tick = contiguous[0][0]
    frontier = contiguous[-1][1]
    if not sample["checkpoint_frontier_clock"] <= first_tick < frontier:
        raise ValueError("fresh intervals do not follow the independently measured checkpoint")
    ticks = sum(end - start for start, end, stamp in contiguous if stamp > first)
    rate = ticks / (last - first)
    return {
        "scope": "Fresh execution-clock window only. Recursion, archive verification, wrap and payout are separate.",
        "run_manifest_sha256": manifest_pin,
        "prior_coverage_sha256": hashlib.sha256(previous_bytes).hexdigest(),
        "execution_receipt_sha256": receipt_pin,
        "fresh_shard_events": len(events),
        "contiguous_execution_shards_measured": len(contiguous),
        "window_started_unix": first,
        "window_ended_unix": last,
        "window_seconds": last - first,
        "first_execution_clock": first_tick,
        "last_execution_clock": frontier,
        "reference_trace_clock": clock,
        "reference_instruction_count": instructions,
        "clock_ticks_per_second": rate,
        **compare_reference_clock(frontier, clock, rate),
    }


def worker_start_ticks(pid):
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
    except (FileNotFoundError, ProcessLookupError):
        return None
    fields = raw.rsplit(")", 1)[1].split()
    return None if fields[0] in ("X", "Z") else int(fields[19])


def publish_window(path, window, *, require_advance=True):
    previous = None
    if require_advance:
        try:
            _, previous = load_metadata(path)
        except FileNotFoundError:
            pass
    if previous is not None:
        pins = ("run_manifest_sha256", "execution_receipt_sha256")
        if any(previous[pin] != window[pin] for pin in pins):
            raise ValueError("the published window belongs to a different withdrawal or execution receipt")
        if (window["last_execution_clock"] <= previous["last_execution_clock"]
                or window["window_ended_unix"] <= previous["window_ended_unix"]):
            return False
    with tempfile.TemporaryDirectory(dir=path.parent) as scratch:
        staged = Path(scratch) / path.name
        staged.write_text(json.dumps(window, indent=2) + "\n", encoding="utf-8")
        staged.replace(path)
    return True


def follow(args):
    pid, expected_start = args.follow_worker
    if worker_start_ticks(pid) != expected_start:
        raise ValueError("the requested Core worker is absent or has been replaced")
    while worker_start_ticks(pid) == expected_start:
        try:
            window = measure(args.run, args.report, args.previous_coverage, args.execution_receipt)
        except MeasurementPending as error:
            print(error, file=sys.stderr, flush=True)
        else:
            if worker_start_ticks(pid) != expected_start:
                break
            if window["reference_clock_status"] != "within_reference":
                raise ValueError("the live execution window cannot be measured against the pinned guest clock")
            if publish_window(args.out, window):
                print(json.dumps(window), flush=True)
        deadline = time.monotonic() + args.interval_seconds
        while time.monotonic() < deadline and worker_start_ticks(pid) == expected_start:
            time.sleep(min(15, max(0, deadline - time.monotonic())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("previous_coverage", type=Path)
    parser.add_argument("--execution-receipt", type=Path)
    parser.add_argument("--out", type=Path, help="publish the measured window atomically for Neon")
    parser.add_argument("--follow-worker", nargs=2, type=int, metavar=("PID", "START_TICKS"),
                        help="refresh the published window while this exact Linux process is alive")
    parser.add_argument("--interval-seconds", type=int, default=900)
    args = parser.parse_args()
    if args.follow_worker and (not args.out or min(args.follow_worker) <= 0 or args.interval_seconds < 180):
        parser.error("following requires an output path, positive worker identity and an interval of at least 180 seconds")
    try:
        if args.follow_worker:
            follow(args)
        else:
            window = measure(args.run, args.report, args.previous_coverage, args.execution_receipt)
            if args.out is None:
                print(json.dumps(window, indent=2))
            else:
                publish_window(args.out, window, require_advance=False)
    except (MeasurementPending, OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Core execution clock measurement stopped: {error}\n")
