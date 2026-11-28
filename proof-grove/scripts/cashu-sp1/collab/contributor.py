"""Zero-key contributor worker for Cashu collaborative SP1 group reduction.

Contributors NEVER receive or need any Bitcoin wallet, private key, or Cashu blinding
secret. On startup this worker verifies `kit-manifest.json` (SHA-256 of every binary and
public proving input + zero-wallet hygiene), then leases one group at a time from the
coordinator (or processes a standalone one-group work order via `--one-group`), runs
the pinned reducer binary, sends periodic heartbeats, and uploads `(reduction.bin,
result.json)` to the coordinator for independent CPU verification.
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

from .kit import verify_kit
from .schema import CollabError, assert_no_key_material_in_obj, sha256_bytes


def _http_json(url: str, body: dict | None = None, timeout: float = 120.0) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body, sort_keys=True).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"error": raw}
        return err.code, parsed


def run_pinned_group_reducer(
    kit_dir: Path,
    manifest: dict,
    work_order: dict,
    out_dir: Path,
    *,
    slice_path: Path | None = None,
    timeout_seconds: int = 3600,
) -> tuple[bytes, dict, float]:
    """Execute the pinned reducer binary from `kit_dir` on a single one-group work order."""
    assert_no_key_material_in_obj(work_order)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    order_path = out / "work-order.json"
    order_path.write_text(json.dumps(work_order, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    reducer = (Path(kit_dir) / manifest["binaries"]["replay-reduction-cuda"]["relpath"]).resolve()
    normalizer = (Path(kit_dir) / manifest["binaries"]["normalize-core-cuda"]["relpath"]).resolve()
    run_json = (Path(kit_dir) / manifest["public_inputs"]["run.json"]["relpath"]).resolve()
    program_key = (Path(kit_dir) / manifest["public_inputs"]["program-key.json"]["relpath"]).resolve()
    core_vk = (Path(kit_dir) / manifest["public_inputs"]["core-vk.bin"]["relpath"]).resolve()
    elf = (Path(kit_dir) / manifest["public_inputs"]["cashu-withdrawal.elf"]["relpath"]).resolve()

    args = [
        "--work-order",
        str(order_path),
        "--normalizer",
        str(normalizer),
        "--run-json",
        str(run_json),
        "--program-key",
        str(program_key),
        "--core-vk",
        str(core_vk),
        "--elf",
        str(elf),
        "--out-dir",
        str(out),
    ]
    if slice_path is not None:
        args += ["--shards-slice", str(Path(slice_path).resolve())]

    first_line = reducer.read_bytes()[:64]
    is_python = reducer.suffix.lower() == ".py" or (first_line.startswith(b"#!") and b"python" in first_line.lower())
    cmd = [sys.executable, "-B", str(reducer), *args] if is_python else [str(reducer), *args]
    t0 = time.monotonic()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds, check=False)
    elapsed = time.monotonic() - t0
    if proc.returncode != 0:
        raise CollabError(f"reducer failed for group {work_order['group_id']} (rc={proc.returncode}): {proc.stderr[-400:]}")

    red_path = out / "reduction.bin"
    res_path = out / "result.json"
    if not red_path.is_file() or not res_path.is_file():
        raise CollabError(f"reducer did not emit reduction.bin and result.json for group {work_order['group_id']}")
    reduction_bytes = red_path.read_bytes()
    cuda_receipt = json.loads(res_path.read_text(encoding="utf-8"))
    if cuda_receipt.get("reduction_sha256") != sha256_bytes(reduction_bytes):
        raise CollabError("local reducer output sha256 disagrees with its own receipt")
    return reduction_bytes, cuda_receipt, elapsed


def run_worker_loop(
    *,
    kit_dir: Path,
    coordinator_url: str,
    worker_id: str,
    expected_manifest_sha256: str | None = None,
    max_groups: int | None = None,
    poll_sleep_s: float = 0.25,
) -> dict:
    """Verify kit pins, then lease -> heartbeat -> reduce -> submit until queue drains."""
    manifest = verify_kit(kit_dir, expected_manifest_sha256)
    base = coordinator_url.rstrip("/")
    completed = 0
    accepted = 0
    rejected = 0

    while max_groups is None or completed < max_groups:
        code, resp = _http_json(f"{base}/v1/lease", {"worker_id": worker_id})
        if code != 200:
            raise CollabError(f"lease request failed ({code}): {resp}")
        if resp.get("done") or resp.get("lease") is None:
            break
        lease = resp["lease"]
        lease_id = lease["lease_id"]
        order = lease["work_order"]
        hb_interval = max(0.05, float(lease.get("heartbeat_interval_s", 30.0)))

        stop_hb = threading.Event()

        def _hb_loop():
            while not stop_hb.wait(hb_interval):
                try:
                    _http_json(
                        f"{base}/v1/heartbeat",
                        {"worker_id": worker_id, "lease_id": lease_id, "progress_shards": order["group_shards"] // 2},
                        timeout=15.0,
                    )
                except OSError:
                    pass

        hb_thread = threading.Thread(target=_hb_loop, daemon=True)
        hb_thread.start()
        try:
            with tempfile.TemporaryDirectory(prefix=f"cashu-worker-{worker_id}-{order['group_id']}-") as tmp:
                red_bytes, cuda_receipt, elapsed = run_pinned_group_reducer(
                    kit_dir, manifest, order, Path(tmp)
                )
        finally:
            stop_hb.set()
            hb_thread.join(timeout=2.0)

        sub_code, sub_resp = _http_json(
            f"{base}/v1/submit",
            {
                "worker_id": worker_id,
                "lease_id": lease_id,
                "group_id": order["group_id"],
                "reduction_b64": base64.b64encode(red_bytes).decode("ascii"),
                "cuda_receipt": cuda_receipt,
                "group_seconds": elapsed,
            },
        )
        completed += 1
        if sub_code == 200 and sub_resp.get("accepted"):
            accepted += 1
        else:
            rejected += 1
        if poll_sleep_s > 0:
            time.sleep(poll_sleep_s)

    return {"worker_id": worker_id, "completed": completed, "accepted": accepted, "rejected": rejected}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run a zero-key Cashu collaborative proving contributor.")
    parser.add_argument("--kit-dir", type=Path, required=True)
    parser.add_argument("--manifest-sha256", help="Optional pinned kit manifest_sha256.")
    parser.add_argument("--coordinator", help="Coordinator base URL (e.g. http://127.0.0.1:8787).")
    parser.add_argument("--worker-id", default="contributor-01")
    parser.add_argument("--max-groups", type=int)
    parser.add_argument("--one-group", type=Path, help="Run a single standalone work-order JSON offline.")
    parser.add_argument("--shards-slice", type=Path, help="Optional local shards-NNNNNN.bin slice.")
    parser.add_argument("--out-dir", type=Path, help="Output directory for --one-group mode.")
    args = parser.parse_args(argv)

    if args.one_group is not None:
        if args.out_dir is None:
            raise CollabError("--one-group requires --out-dir")
        manifest = verify_kit(args.kit_dir, args.manifest_sha256)
        order = json.loads(args.one_group.read_text(encoding="utf-8"))
        _, receipt, elapsed = run_pinned_group_reducer(
            args.kit_dir, manifest, order, args.out_dir, slice_path=args.shards_slice
        )
        print(json.dumps({"group_id": order["group_id"], "status": receipt["status"], "seconds": round(elapsed, 4)}))
        return 0

    if not args.coordinator:
        raise CollabError("provide --coordinator URL or --one-group work-order.json")
    summary = run_worker_loop(
        kit_dir=args.kit_dir,
        coordinator_url=args.coordinator,
        worker_id=args.worker_id,
        expected_manifest_sha256=args.manifest_sha256,
        max_groups=args.max_groups,
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
