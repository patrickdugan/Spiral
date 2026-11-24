"""Aggregate durable checkpoint activity without transmitting proof data."""
import collections
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

from prover_cgroup_sample import sample

root = Path(sys.argv[1])
seen = collections.defaultdict(set)
cursor = 0
last_kind = "starting"
last_progress = 0


def active(unit):
    return subprocess.run(
        ["systemctl", "is-active", "--quiet", unit], timeout=4, check=False
    ).returncode == 0


def ark_health():
    output = subprocess.run(
        ["systemctl", "show", "--property=ControlGroup", "--value", "ark-a100-pilot-prover"],
        timeout=4, check=False, capture_output=True, text=True,
    )
    group = output.stdout.strip()
    if output.returncode or not group.startswith("/") or group == "/":
        return {}
    base = Path("/sys/fs/cgroup")
    cgroup = (base / group.lstrip("/")).resolve()
    if not cgroup.is_relative_to(base):
        return {}
    return sample(cgroup)


def read_sample():
    global cursor, last_kind, last_progress
    start = root / "pilot-start-unix"
    if start.exists():
        prove_start = int(start.read_text())
        progress = root / "cache/progress.jsonl"
        if progress.is_file():
            with progress.open("rb") as events:
                events.seek(cursor)
                while line := events.readline():
                    if not line.endswith(b"\n"):
                        break
                    cursor = events.tell()
                    try:
                        event = json.loads(line)
                        kind, key, stamp, replay = (event[name] for name in ("kind", "key", "t", "replayed"))
                        if kind not in {"shard", "reduce"} or not isinstance(key, str) or not isinstance(stamp, (int, float)):
                            continue
                        if stamp < prove_start or not isinstance(replay, bool):
                            continue
                        bucket = seen[kind, replay]
                        if key not in bucket:
                            bucket.add(key)
                            last_progress = int(stamp)
                            last_kind = "replay" if replay else kind
                    except (KeyError, TypeError, ValueError):
                        continue
    ark_live = active("ark-a100-pilot-prover")
    nova_live = active("ark-a100-pilot-nova")
    if not ark_live and (root / "pilot-end-unix").is_file():
        last_kind = "stopped"
    gpu_samples = root / "gpu-samples.csv"
    used = 0
    if gpu_samples.is_file():
        tail = gpu_samples.read_text().splitlines()
        if tail:
            try:
                used = int(tail[-1].split(",")[2])
            except (IndexError, ValueError):
                pass
    return [
        "ark_heartbeat", int(time.time()), last_kind, int(last_progress),
        len(seen["shard", False]), len(seen["reduce", False]),
        len(seen["shard", True]), len(seen["reduce", True]),
        used, int(ark_live), int(nova_live),
    ]


while True:
    try:
        fields = read_sample()
        # A bounded tagged status keeps the pilot controller's existing state
        # handoff compatible while carrying the current heartbeat on every PUT.
        stage = "|".join(map(str, fields))
        status = {"stage": stage}
        if fields[-2]:
            try:
                status["ark_cgroup"] = ark_health()
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass
        request = urllib.request.Request(
            os.environ["ARK_PILOT_STATUS_URL"],
            json.dumps(status).encode(), method="PUT",
        )
        with urllib.request.urlopen(request, timeout=5):
            pass
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    time.sleep(8)
