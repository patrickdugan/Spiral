import hashlib
import json
import os
from pathlib import Path
import select
import signal
import time


ROOT = Path("/mnt/c/Users/patri/Documents/Codex/2026-11-15/new-chat")
BASE = Path("/var/tmp/ark-asp-full-20261117")
CAMPAIGN = ROOT / "work/ark-run-20261123-native-campaign"
WORKER = "/root/nb3-gpu-target/release/ark-prove-gpu-cached-gkr"


def identify(pid):
    proc = Path("/proc") / str(pid)
    fields = (proc / "stat").read_text().rsplit(")", 1)[1].split()
    argv = (proc / "cmdline").read_bytes().rstrip(b"\0").decode().split("\0")
    return int(fields[1]), int(fields[19]), argv


def main():
    state = json.loads((BASE / "pipeline-status.json").read_text())
    phase = Path(state["phases"]["gpu"])
    if state["status"] != "gpu" or phase.parent != CAMPAIGN / "phases":
        raise RuntimeError("The active phase changed. Recheck its identity.")
    prover = int((phase / "pid").read_text())
    wrapper, prover_start, prover_args = identify(prover)
    if not (prover_args[0] == WORKER and str(BASE / "prover-transient") in prover_args):
        raise RuntimeError("GPU prover identity mismatch.")
    if "arkproof.slice/ark-proof-" not in Path(f"/proc/{prover}/cgroup").read_text():
        raise RuntimeError("GPU prover is outside the expected resource group.")
    coordinator, wrapper_start, wrapper_args = identify(wrapper)
    if not (str(ROOT / "work/ark-parallel-bounded-20261122.py") in wrapper_args
            and str(phase) in wrapper_args and f"arkfull-gpu-{coordinator}" in wrapper_args):
        raise RuntimeError("Resource wrapper identity mismatch.")
    _, coordinator_start, coordinator_args = identify(coordinator)
    if str(ROOT / "work/ark-native-campaign-20261123.py") not in coordinator_args:
        raise RuntimeError("Coordinator identity mismatch.")

    fds = {}
    poll = select.poll()
    try:
        for pid, start in [(prover, prover_start), (wrapper, wrapper_start), (coordinator, coordinator_start)]:
            fd = os.pidfd_open(pid)
            fds[pid] = fd
            if identify(pid)[1] != start:
                raise RuntimeError(f"Process {pid} changed during inspection.")
            poll.register(fd, select.POLLIN)
        hold = CAMPAIGN / "hold.json"
        try:
            with hold.open("x") as file:
                json.dump({"status": "held_at_user_request", "reason": "Inky throughput test",
                           "created_unix": time.time()}, file)
                file.write("\n")
        except FileExistsError:
            pass
        signal.pidfd_send_signal(fds[coordinator], signal.SIGINT)
        deadline = time.monotonic() + 46
        remaining = set(fds.values())
        while remaining and time.monotonic() < deadline:
            for fd, _ in poll.poll(500):
                poll.unregister(fd)
                remaining.discard(fd)
        if remaining:
            raise RuntimeError(f"Shutdown still in progress for {[p for p, fd in fds.items() if fd in remaining]}.")
    finally:
        for fd in fds.values():
            os.close(fd)

    result = json.loads((phase / "result.json").read_text())
    final_state = json.loads((BASE / "pipeline-status.json").read_text())
    run = BASE / "prover-transient"
    counts = {kind: sum(item.is_dir() and not item.name.startswith(".") for item in (run / "memo" / kind).iterdir())
              for kind in ("shard", "reduce")}
    print(json.dumps({"coordinator": coordinator, "prover": prover, "wrapper": wrapper,
                      "status": final_state["status"], "stop_reason": result["stop_reason"],
                      "checkpoint_counts": counts,
                      "run_config_sha256": hashlib.sha256((run / "run.json").read_bytes()).hexdigest(),
                      "restart_hold": str(hold),
                      "compressed_proof_exists": (BASE / "compressed.bin").exists()}))


if __name__ == "__main__":
    main()
