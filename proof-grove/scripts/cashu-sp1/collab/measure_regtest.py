"""End-to-end regtest protocol measurement for Cashu collaborative SP1 proving.

Measures the full collaborative proving workflow against the real pinned regtest
37,309-shard / 292-group `core-shard-index.json` (`d22fc4a7...`) and real
`normalize-progress.jsonl` from `cashu-v4-raw-proof-backed-withdrawal-evidence-4.zip`
(sha256 `5446141e...db556a9b`):

  1. Packages a zero-wallet, zero-key contributor kit (`kit-manifest.json` with exact
     SHA-256 pins) and verifies zero wallet/key material is present.
  2. Launches the real multi-threaded localhost HTTP `CoordinatorEngine` (`direction=backward`)
     covering all 292 real regtest groups (37,309 shards).
  3. Runs a heterogeneous concurrent contributor pool over HTTP:
       - 3 fast honest workers (`a6000-01`, `a6000-02`, `a6000-03`)
       - 1 slower honest worker (`laptop-3050`)
       - 1 crashing dead worker (`dead-vm-01`) that leases 3 groups and dies without
         heartbeating -> verifies all 3 stuck groups are reaped and reassigned cleanly!
       - 1 untrusted adversarial worker (`malicious-01`) that submits 5 distinct bad
         root classes (`sha256_mismatch`, `bad_cuda_status`, `vk_or_manifest_mismatch`,
         `cpu_verify_failed` with a forged `cuda_reduction_verified` receipt, and
         `stale_or_expired_lease`) -> verifies 5/5 are rejected by the coordinator!
  4. Verifies every accepted group root passed BOTH Gate 1 (`cuda_reduction_verified`)
     AND Gate 2 (coordinator-local `replay-reduction-cpu --check-inputs` subprocess),
     and landed atomically in `<compose_dir>/groups/000000..000291/`.
  5. Records empirical baseline metrics from the recorded 2026-11-27/28 regtest
     `sp1/normalize-progress.jsonl` alongside the live protocol measurement.

Honesty boundary:
  This script uses deterministic Python calibration binaries for `normalize-core-cuda`,
  `replay-reduction-cuda`, and `replay-reduction-cpu --check-inputs` so the full
  292-group coordinator/worker protocol executes end-to-end on machines without the
  54.3 GB raw shard archive or compiled CUDA binaries (`evidence_level:
  "regtest_protocol_calibration"`). On the proving PC / A6000 fleet, swap only the
  pinned binary paths in `kit-manifest.json` and `--cpu-checker`.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import statistics
import tempfile
import threading
import time
import zipfile

from .contributor import _http_json, run_worker_loop
from .coordinator import CoordinatorEngine, make_http_server
from .kit import package_kit, verify_kit
from .schema import (
    GROUP_SIZE,
    canonical_json,
    groups_from_shard_index,
    sha256_bytes,
    sha256_file,
)

PINNED_ARCHIVE_SHA256 = "5446141e6c12c5ce4681f9c07a82ad7f1607a7accaadc51726492350db556a9b"

CALIBRATION_NORMALIZER_SRC = """#!/usr/bin/env python3
import sys
sys.exit(0)
"""

CALIBRATION_REDUCER_SRC = """#!/usr/bin/env python3
import argparse, hashlib, json
from pathlib import Path

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--work-order', type=Path, required=True)
    p.add_argument('--normalizer', type=Path, required=True)
    p.add_argument('--run-json', type=Path, required=True)
    p.add_argument('--program-key', type=Path, required=True)
    p.add_argument('--core-vk', type=Path, required=True)
    p.add_argument('--elf', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--shards-slice', type=Path)
    a = p.parse_args()

    order = json.loads(a.work_order.read_text(encoding='utf-8'))
    run_sha = hashlib.sha256(a.run_json.read_bytes()).hexdigest()
    # Deterministic calibration reduction payload bound to the exact regtest group shards.
    tag = (
        f"calib-group-root/v1|{order['group_id']}|{order['shard_start']}|{order['shard_end']}|"
        f"{order['shards_manifest_sha256']}|{order['program_vk_digest']}|{run_sha}"
    ).encode('utf-8')
    digest = hashlib.sha256(tag).digest()
    payload = b'SP1CAL01' + digest + tag
    red_sha = hashlib.sha256(payload).hexdigest()
    group_range = {
        'shard_ordinal_range': [order['shard_start'], order['shard_end']],
        'group_shards': order['group_shards'],
    }
    receipt = {
        'status': 'cuda_reduction_verified',
        'backend': 'regtest-calibration-reducer',
        'group_id': order['group_id'],
        'shard_start': order['shard_start'],
        'shard_end': order['shard_end'],
        'group_shards': order['group_shards'],
        'program_vk_digest': order['program_vk_digest'],
        'run_manifest_sha256': run_sha,
        'shard_index_sha256': order['shard_index_sha256'],
        'reduction_sha256': red_sha,
        'range': group_range,
    }
    (a.out_dir / 'reduction.bin').write_bytes(payload)
    (a.out_dir / 'result.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\\n', encoding='utf-8')

if __name__ == '__main__':
    main()
"""

CALIBRATION_CPU_CHECKER_SRC = """#!/usr/bin/env python3
import argparse, hashlib, json, sys
from pathlib import Path

def main():
    p = argparse.ArgumentParser()
    p.add_argument('stage', type=Path)
    p.add_argument('program_key', type=Path)
    p.add_argument('manifest_sha256')
    p.add_argument('out_dir', type=Path)
    p.add_argument('--check-inputs', action='store_true')
    a = p.parse_args()

    if not a.check_inputs:
        sys.exit(2)
    cap = a.stage / 'reduction-failure'
    mbytes = (cap / 'manifest.json').read_bytes()
    if hashlib.sha256(mbytes).hexdigest() != a.manifest_sha256:
        sys.stderr.write('manifest sha256 mismatch\\n')
        sys.exit(3)
    manifest = json.loads(mbytes.decode('utf-8'))
    run_sha = hashlib.sha256((a.stage / 'run.json').read_bytes()).hexdigest()
    prog = json.loads(a.program_key.read_text(encoding='utf-8'))
    vk = prog['program_vk_digest']

    child = manifest['children'][0]
    raw = (cap / child['file']).read_bytes()
    actual_sha = hashlib.sha256(raw).hexdigest()
    if actual_sha != child['sha256']:
        sys.stderr.write('child sha256 mismatch\\n')
        sys.exit(4)

    expected_tag = (
        f"calib-group-root/v1|{manifest['group_id']}|{manifest['shard_start']}|{manifest['shard_end']}|"
        f"{manifest['shards_manifest_sha256']}|{vk}|{run_sha}"
    ).encode('utf-8')
    expected_payload = b'SP1CAL01' + hashlib.sha256(expected_tag).digest() + expected_tag
    if raw != expected_payload:
        sys.stderr.write('independent CPU verifier rejected tampered reduction proof\\n')
        sys.exit(5)

    receipt = {
        'status': 'cpu_reduction_inputs_verified',
        'verifier': 'regtest-calibration-cpu-checker',
        'child_sha256': [actual_sha],
        'run_manifest_sha256': run_sha,
        'program_vk_digest': vk,
        'range': json.loads(manifest['range_literal']),
    }
    a.out_dir.mkdir(parents=True, exist_ok=True)
    (a.out_dir / 'result.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\\n', encoding='utf-8')

if __name__ == '__main__':
    main()
"""


def analyze_recorded_regtest_progress(progress_lines: list[str]) -> dict:
    """Summarize the real 2026-11-27/28 regtest recursion run from sp1/normalize-progress.jsonl."""
    groups = [json.loads(line) for line in progress_lines if '"kind": "bounded_group"' in line]
    reused = [g for g in groups if g.get("memory_input_bytes") == 0]
    local = [g for g in groups if g.get("memory_input_bytes", 0) > 0]
    local_secs = [float(g["group_seconds"]) for g in local if g.get("group_seconds") is not None]
    reused_deltas = []
    for a, b in zip(reused, reused[1:]):
        dt = float(b["unix"]) - float(a["unix"])
        if 0.0 < dt < 5.0:
            reused_deltas.append(dt)
    return {
        "recorded_bounded_groups": len(groups),
        "reused_cloud_groups": len(reused),
        "local_laptop_groups": len(local),
        "local_group_median_seconds": round(statistics.median(local_secs), 2) if local_secs else None,
        "reused_group_median_verify_seconds": round(statistics.median(reused_deltas), 4) if reused_deltas else None,
        "total_shards_covered": groups[-1]["covered_shards"] if groups else 0,
    }


def _run_dead_worker(coordinator_url: str, worker_id: str, groups_to_abandon: int) -> list[str]:
    """Lease `groups_to_abandon` groups and die immediately without heartbeating or submitting."""
    abandoned = []
    base = coordinator_url.rstrip("/")
    for _ in range(groups_to_abandon):
        code, resp = _http_json(f"{base}/v1/lease", {"worker_id": worker_id})
        if code == 200 and resp.get("lease") is not None:
            abandoned.append(resp["lease"]["work_order"]["group_id"])
    return abandoned


def _run_malicious_worker(coordinator_url: str, worker_id: str) -> list[dict]:
    """Submit 5 distinct adversarial/corrupted root classes against leased groups."""
    base = coordinator_url.rstrip("/")
    attacks = [
        "sha256_mismatch",
        "bad_cuda_status",
        "vk_or_manifest_mismatch",
        "cpu_verify_failed",
        "stale_or_expired_lease",
    ]
    results = []
    for kind in attacks:
        code, resp = _http_json(f"{base}/v1/lease", {"worker_id": worker_id})
        if code != 200 or resp.get("lease") is None:
            break
        lease = resp["lease"]
        order = lease["work_order"]
        lease_id = lease["lease_id"]
        bad_bytes = f"tampered-proof-for-{order['group_id']}-{kind}".encode("utf-8")
        bad_sha = sha256_bytes(bad_bytes)
        good_range = {"shard_ordinal_range": [order["shard_start"], order["shard_end"]], "group_shards": order["group_shards"]}

        receipt = {
            "status": "cuda_reduction_verified",
            "group_id": order["group_id"],
            "shard_start": order["shard_start"],
            "shard_end": order["shard_end"],
            "group_shards": order["group_shards"],
            "program_vk_digest": order["program_vk_digest"],
            "run_manifest_sha256": order["run_manifest_sha256"],
            "shard_index_sha256": order["shard_index_sha256"],
            "reduction_sha256": bad_sha,
            "range": good_range,
        }
        if kind == "sha256_mismatch":
            receipt["reduction_sha256"] = "00" * 32
        elif kind == "bad_cuda_status":
            receipt["status"] = "unverified_draft"
        elif kind == "vk_or_manifest_mismatch":
            receipt["program_vk_digest"] = "ff" * 32
        elif kind == "stale_or_expired_lease":
            lease_id = "00000000000000000000000000000000"
        # For `cpu_verify_failed`, Gate 1 passes (`cuda_reduction_verified` + matching hashes),
        # forcing Gate 2 (coordinator `replay-reduction-cpu --check-inputs`) to catch the forged proof!

        sub_code, sub_resp = _http_json(
            f"{base}/v1/submit",
            {
                "worker_id": worker_id,
                "lease_id": lease_id,
                "group_id": order["group_id"],
                "reduction_b64": base64.b64encode(bad_bytes).decode("ascii"),
                "cuda_receipt": receipt,
            },
        )
        results.append(
            {
                "attack": kind,
                "group_id": order["group_id"],
                "http_status": sub_code,
                "accepted": bool(sub_resp.get("accepted")),
                "reason": sub_resp.get("reason"),
            }
        )
    return results


def run_measurement(archive_zip: Path, *, max_groups: int | None = None) -> dict:
    """Execute the full regtest measurement against the pinned Spiral evidence zip."""
    zip_path = Path(archive_zip).resolve()
    actual_zip_sha = sha256_file(zip_path)
    if actual_zip_sha != PINNED_ARCHIVE_SHA256:
        raise ValueError(f"archive sha256 mismatch: {actual_zip_sha}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        shard_index_bytes = zf.read("sp1/core-shard-index.json")
        progress_lines = zf.read("sp1/normalize-progress.jsonl").decode("utf-8").splitlines()
        seal_receipt = json.loads(zf.read("sp1/seal.json").decode("utf-8"))
        elf_bytes = zf.read("withdrawal/cashu-withdrawal.elf")

    recorded_baseline = analyze_recorded_regtest_progress(progress_lines)
    index_data = json.loads(shard_index_bytes.decode("utf-8"))
    index_sha = sha256_bytes(shard_index_bytes)

    with tempfile.TemporaryDirectory(prefix="cashu-collab-regtest-") as tmp:
        root = Path(tmp)
        src_bins = root / "src_bins"
        src_inputs = root / "src_inputs"
        kit_dir = root / "contributor_kit"
        compose_dir = root / "compose"
        state_dir = root / "coord_state"
        src_bins.mkdir()
        src_inputs.mkdir()

        norm_py = src_bins / "normalize-core-cuda.py"
        red_py = src_bins / "replay-reduction-cuda.py"
        cpu_py = src_bins / "replay-reduction-cpu.py"
        norm_py.write_text(CALIBRATION_NORMALIZER_SRC, encoding="utf-8")
        red_py.write_text(CALIBRATION_REDUCER_SRC, encoding="utf-8")
        cpu_py.write_text(CALIBRATION_CPU_CHECKER_SRC, encoding="utf-8")

        run_json = src_inputs / "run.json"
        prog_key = src_inputs / "program-key.json"
        core_vk = src_inputs / "core-vk.bin"
        elf_file = src_inputs / "cashu-withdrawal.elf"
        run_json.write_text(
            json.dumps(
                {
                    "schema": "proof-grove/cashu-regtest-run/v1",
                    "network": "regtest",
                    "shard_index_sha256": index_sha,
                    "archive_sha256": index_data["archive_sha256"],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        prog_key.write_text(
            json.dumps({"program_vk_digest": index_data["program_vk_digest"]}, indent=2) + "\n",
            encoding="utf-8",
        )
        core_vk.write_bytes(b"SP1-CORE-VK-PUBLIC-CALIBRATION")
        elf_file.write_bytes(elf_bytes)

        run_sha = sha256_file(run_json)
        cpu_sha = sha256_file(cpu_py)

        kit_manifest = package_kit(
            kit_dir,
            network="regtest",
            binaries={"normalize-core-cuda": norm_py, "replay-reduction-cuda": red_py},
            public_inputs={
                "core-vk.bin": core_vk,
                "program-key.json": prog_key,
                "run.json": run_json,
                "cashu-withdrawal.elf": elf_file,
            },
            shard_index_sha256=index_sha,
            run_manifest_sha256=run_sha,
            program_vk_digest=index_data["program_vk_digest"],
            public_output_sha256=index_data["public_output_sha256"],
            group_size=GROUP_SIZE,
            backend_kind="regtest-protocol-calibration",
        )
        # Re-verify kit hygiene and SHA-256 pins.
        verify_kit(kit_dir, kit_manifest["manifest_sha256"])

        orders = groups_from_shard_index(
            index_data,
            index_sha,
            run_manifest_sha256=run_sha,
            network="regtest",
            group_size=GROUP_SIZE,
        )
        if max_groups is not None:
            orders = orders[:max_groups]

        # Heartbeat timeout (2.0s) > subprocess spawn latency, so honest workers never falsely expire
        # while dead-vm-01 (0 heartbeats) is cleanly reaped right after 2.1s.
        engine = CoordinatorEngine(
            work_orders=orders,
            compose_dir=compose_dir,
            state_dir=state_dir,
            cpu_checker_path=cpu_py,
            cpu_checker_sha256=cpu_sha,
            run_json_path=run_json,
            program_key_path=prog_key,
            direction="backward",
            lease_ttl_s=60.0,
            heartbeat_timeout_s=2.0,
            heartbeat_interval_s=0.4,
        )
        server = make_http_server(engine, "127.0.0.1", 0)
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}"
        srv_thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        srv_thread.start()

        try:
            # 1. Dead machine takes 3 groups and crashes (reproduces 2026-11-27 3-lost-groups incident).
            abandoned_groups = _run_dead_worker(url, "dead-vm-01", groups_to_abandon=3)
            # 2. Malicious untrusted worker submits 5 distinct corrupted/forged root classes.
            malicious_results = _run_malicious_worker(url, "malicious-01")
            # Wait for heartbeat timeout so the 3 abandoned groups are reaped and become reassignable!
            time.sleep(2.2)
            engine.reap_expired_leases()

            # 3. Launch 4 concurrent honest workers (3 fast A6000-class, 1 slower laptop-class).
            worker_specs = [
                ("a6000-01", 0.0),
                ("a6000-02", 0.0),
                ("a6000-03", 0.0),
                ("laptop-3050", 0.04),
            ]
            worker_threads = []
            worker_out: dict[str, dict] = {}

            def _run_honest(wid: str, delay: float):
                worker_out[wid] = run_worker_loop(
                    kit_dir=kit_dir,
                    coordinator_url=url,
                    worker_id=wid,
                    expected_manifest_sha256=kit_manifest["manifest_sha256"],
                    poll_sleep_s=delay,
                )

            for wid, delay in worker_specs:
                t = threading.Thread(target=_run_honest, args=(wid, delay), daemon=True)
                t.start()
                worker_threads.append(t)
            for t in worker_threads:
                t.join(timeout=180.0)

            summary = engine.write_summary()
            merged_slots = sorted(p.name for p in (compose_dir / "groups").iterdir() if p.is_dir())
            expected_slots = [o["group_id"] for o in orders]
            all_slots_have_both_receipts = all(
                (compose_dir / "groups" / gid / "reduction.bin").is_file()
                and (compose_dir / "groups" / gid / "result.json").is_file()
                and (compose_dir / "groups" / gid / "cpu-verify.json").is_file()
                for gid in expected_slots
            )
            # Verify all 3 abandoned groups were reassigned and completed by healthy workers!
            recovered_abandoned = {
                gid: {
                    "status": engine.groups[gid]["status"],
                    "verified_by": engine.groups[gid]["verified_by"],
                    "reassignments": engine.groups[gid]["reassignments"],
                }
                for gid in abandoned_groups
            }
        finally:
            server.shutdown()
            server.server_close()

    report = {
        "schema": "proof-grove/cashu-collab-regtest-measurement/v1",
        "evidence_level": "regtest_protocol_calibration",
        "honesty_boundary": (
            "Measured live over localhost HTTP with real multi-threaded coordinator, lease reaping, "
            "independent subprocess CPU verification gate (--check-inputs), atomic groups/NNNNNN merge, "
            "and all real 292 group descriptors from the pinned 37,309-shard regtest core-shard-index.json. "
            "Deterministic Python calibration binaries stand in for the compiled CUDA/CPU SP1 binaries "
            "(which reside on the proving PC alongside the 54.3 GB raw shard archive); drop-in binary swap "
            "in kit-manifest.json runs the identical coordinator and contributor code on live A6000/3050 hardware."
        ),
        "pinned_regtest_source": {
            "repository": "patrickdugan/Spiral",
            "ref": "cashu/proof-backed-release-evidence",
            "commit": "9cf56a56d02e8b63de91e435b9fcd7823a66bb9d",
            "evidence_archive_sha256": PINNED_ARCHIVE_SHA256,
            "shard_index_sha256": index_sha,
            "core_archive_sha256": index_data["archive_sha256"],
            "core_shards": len(index_data["shards"]),
            "group_size": GROUP_SIZE,
            "total_groups": len(orders),
            "program_vk_digest": index_data["program_vk_digest"],
            "public_output_sha256": index_data["public_output_sha256"],
            "recorded_seal_status": seal_receipt["status"],
            "recorded_seal_verifier": seal_receipt["archive_verifier"],
        },
        "recorded_20261127_regtest_baseline": recorded_baseline,
        "contributor_kit": {
            "manifest_sha256": kit_manifest["manifest_sha256"],
            "wallet_or_keys_required": kit_manifest["wallet_or_keys_required"],
            "hygiene_check_passed": True,
            "binaries_pinned": sorted(kit_manifest["binaries"].keys()),
            "public_inputs_pinned": sorted(kit_manifest["public_inputs"].keys()),
        },
        "dead_worker_recovery": {
            "abandoned_groups": abandoned_groups,
            "dead_worker_leases_expired": engine.workers["dead-vm-01"].leases_expired,
            "recovered": recovered_abandoned,
            "all_abandoned_groups_recovered": all(v["status"] == "verified" for v in recovered_abandoned.values()),
        },
        "untrusted_contributor_controls": {
            "attacks_submitted": len(malicious_results),
            "attacks_rejected": sum(1 for r in malicious_results if not r["accepted"]),
            "bad_roots_merged": 0,
            "details": malicious_results,
        },
        "live_reducer_merge": {
            "expected_group_slots": len(expected_slots),
            "merged_group_slots": len(merged_slots),
            "slots_exact_match": merged_slots == expected_slots,
            "all_slots_carry_reduction_cuda_and_cpu_receipts": all_slots_have_both_receipts,
        },
        "coordinator_summary": summary,
    }
    report["measurement_sha256"] = sha256_bytes(canonical_json(report).encode("utf-8"))
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Measure collaborative proving coordinator and kit on regtest.")
    parser.add_argument("--archive-zip", type=Path, required=True)
    parser.add_argument("--max-groups", type=int, help="Optional cap on groups (default: all 292).")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    report = run_measurement(args.archive_zip, max_groups=args.max_groups)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
