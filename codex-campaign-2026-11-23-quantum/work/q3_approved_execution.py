"""One-shot IBM execution guard for the explicitly approved AHR-QPU-03 workload."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4

import numpy as np
from qiskit import qpy
from qiskit_ibm_runtime import SamplerV2

from backend_snapshot import calibration_fingerprint, capture, open_account, write_json
from circuit_synthesis import measure_map


class Hold(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def require(condition, reason):
    if not condition:
        raise Hold(reason)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def text_sha(path):
    return sha256(path.read_text(encoding="utf-8").encode()).hexdigest()


def free_balance(service, crn):
    require(service.active_instance() == crn, "the pinned Open Plan instance changed")
    usage = service.usage()
    seconds, ru = usage.get("usage_remaining_seconds"), usage.get("usage_remaining_ru")
    values = [v for v in (seconds, 60*ru if isinstance(ru, (int, float)) else None)
              if isinstance(v, (int, float)) and np.isfinite(v)]
    require(bool(values), "IBM did not report the free balance")
    return {"plan": "open", "checked_utc": now(),
            "remaining_qpu_seconds": float(max(0, min(values))) if not usage.get("usage_limit_reached") else 0}


def approved_inputs(folder, approved_sha):
    manifest_path = folder / "q3_candidate_manifest.json"
    require(text_sha(manifest_path) == approved_sha, "exact manifest SHA-256 mismatch")
    manifest = read(manifest_path)
    calibration = folder / "calibration.json"
    qpy_file = folder / "q3_candidate_isa.qpy"
    require(text_sha(calibration) == manifest["calibration_sha256"], "calibration SHA-256 mismatch")
    require(sha256(qpy_file.read_bytes()).hexdigest() == manifest["qpy_sha256"], "circuit SHA-256 mismatch")
    approved = read(calibration)
    require(approved["mode"] == "live_read_only" and approved["account"]["plan"] == "open",
            "the approved proposal is not for a verified free IBM instance")
    require(manifest["design_decision"] == "GO design only", "the approved design gate is not GO")
    settings = manifest["settings"]
    require(manifest["circuits"] == len(settings) == 48 and manifest["total_shots"] == 196608
            and all(r["shots"] == 4096 for r in settings), "48 × 4,096 shot scope mismatch")
    require(manifest["provisional_max_execution_time_s"] == 106, "approved cap mismatch")
    with qpy_file.open("rb") as stream:
        circuits = qpy.load(stream)
    require(len(circuits) == len(settings) and len({r["case_id"] for r in settings}) == 48,
            "circuit manifest count or uniqueness mismatch")
    target = approved["backend"]
    require(target["selection"]["physical_xyz"] == manifest["physical_xyz"]
            and target["backend"] == manifest["backend"]
            and target["calibration_timestamp"] == manifest["calibration_timestamp"],
            "the approved backend, layout, or calibration does not match")
    allowed = {(r["gate"], tuple(r["physical"])) for r in target["instructions"]}
    for circuit, row in zip(circuits, settings, strict=True):
        require(circuit.num_qubits == target["backend_width"] and
                circuit.metadata["case_id"] == row["case_id"] and
                measure_map(circuit) == row["classical_bit_to_physical"],
                "an ISA circuit label, width, or readout map changed")
        for item in circuit.data:
            qubits = tuple(circuit.find_bit(q).index for q in item.qubits)
            require((item.operation.name, qubits) in allowed, "an ISA instruction is not approved")
    return manifest, target, circuits


def submit(service, crn, folder, out, approved_sha, allow_timestamp_only=False):
    manifest, target, circuits = approved_inputs(folder, approved_sha)
    checkpoint = out / "hardware_job.json"
    require(not checkpoint.exists(), "a submission checkpoint already exists; recover the job")
    backend = service.backend(manifest["backend"], instance=crn)
    require(backend.status().operational and not backend.configuration().simulator,
            "the approved IBM backend is not operational")
    fresh = capture(backend, target["selection"])
    account = free_balance(service, crn)
    preflight = {"approved_manifest_sha256": approved_sha, "account": account,
                 "target": fresh, "checked_utc": now(), "qpu_submitted": False,
                 "same_model": calibration_fingerprint(fresh, include_calibration_identity=False) ==
                 calibration_fingerprint(target, include_calibration_identity=False),
                 "same_calibration": calibration_fingerprint(fresh) == calibration_fingerprint(target)}
    timestamp_only = (preflight["same_model"] and
                      fresh["calibration_id"] == target["calibration_id"] and
                      fresh["calibration_timestamp"] != target["calibration_timestamp"])
    preflight["timestamp_only_change"] = timestamp_only
    write_json(out / "preflight.json", preflight)
    cap = manifest["provisional_max_execution_time_s"]
    print(f"Verified {account['remaining_qpu_seconds']:g} free QPU seconds. "
          f"Current {backend.name} calibration {fresh['calibration_timestamp']}.", flush=True)
    require(preflight["same_calibration"] or (allow_timestamp_only and timestamp_only),
            "the approved calibration has changed")
    require(account["remaining_qpu_seconds"] >= cap, "the free balance is below the 106-second cap")
    tag = f"ahr-qpu-03-{approved_sha[:10]}-{uuid4().hex[:10]}"
    sampler = SamplerV2(mode=backend, options={
        "max_execution_time": cap,
        "environment": {"job_tags": [tag]},
        "twirling": {"enable_gates": False, "enable_measure": False},
        "dynamical_decoupling": {"enable": False},
    })
    receipt = {"tag": tag, "job_id": None, "submission_requested_utc": now(),
               "backend": manifest["backend"], "physical_xyz": manifest["physical_xyz"],
               "approved_manifest_sha256": approved_sha, "authorization_commit": "93158b3",
               "shots_per_circuit": 4096, "circuits": 48, "max_execution_time_s": cap,
               "timestamp_only_refresh_authorized": allow_timestamp_only,
               "calibration_timestamp_at_preflight": fresh["calibration_timestamp"],
               "free_balance_checked": account}
    with checkpoint.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
    job = sampler.run(circuits, shots=4096)
    receipt["job_id"] = job.job_id()
    write_json(checkpoint, receipt)
    print(f"IBM accepted job {receipt['job_id']}", flush=True)
    return receipt


def collect(service, crn, folder, out, approved_sha, watch_seconds=0):
    manifest, _, _ = approved_inputs(folder, approved_sha)
    checkpoint = out / "hardware_job.json"
    receipt = read(checkpoint)
    require(receipt["approved_manifest_sha256"] == approved_sha, "job receipt does not match approval")
    if not receipt["job_id"]:
        jobs = service.jobs(job_tags=[receipt["tag"]], instance=crn, limit=2)
        require(len(jobs) == 1, "submission status needs verification by job tag")
        receipt["job_id"] = jobs[0].job_id()
        write_json(checkpoint, receipt)
    job = service.job(receipt["job_id"])
    status = job.status()
    print(f"IBM job {receipt['job_id']} is {status}", flush=True)
    timeout = monotonic() + watch_seconds
    while status in {"QUEUED", "RUNNING", "INITIALIZING", "VALIDATING"} and monotonic() < timeout:
        sleep(8)
        new_status = job.status()
        if new_status != status:
            print(f"IBM job {receipt['job_id']} is {new_status}", flush=True)
        status = new_status
    if status != "DONE":
        write_json(out / "job_status.json", {"job_id": receipt["job_id"], "status": status, "checked_utc": now()})
        return
    result = job.result()
    cases = manifest["settings"]
    counts, confirmed_ids = {}, []
    for row, pub in zip(cases, result, strict=True):
        circuit_metadata = pub.metadata.get("circuit_metadata", {})
        confirmed_ids.append(circuit_metadata.get("case_id"))
        values = {k: int(v) for k, v in pub.data.out.get_counts().items()}
        require(sum(values.values()) == row["shots"] and
                all(len(k) == 3 and set(k) <= {"0", "1"} and v >= 0 for k, v in values.items()),
                "IBM counts differ from the approved shot or bit ledger")
        counts[row["case_id"]] = values
    usage = job.usage()
    fit = {"qpu_seconds": usage, "status": status, "retrieved_utc": now(), **receipt,
           "pub_case_ids_match": confirmed_ids == [r["case_id"] for r in cases],
           "pub_case_ids": confirmed_ids, "counts": counts}
    write_json(out / "hardware_counts.json", fit)
    print(f"Collected {sum(map(sum, (c.values() for c in counts.values())))} shots, usage {usage}", flush=True)
    write_json(out / "post_run_allocation.json", free_balance(service, crn))
    spans = (result.metadata.get("execution", {}).get("execution_spans") or
             result.metadata.get("execution_spans") or [])
    chunks = [{"start": span.start.isoformat(), "stop": span.stop.isoformat(),
               "pubs": span.pub_idxs} for span in spans]
    props = job.properties()
    backend = job.backend()
    final = backend.properties(datetime=max(span.start for span in spans)) if spans else None
    times = job.metrics().get("timestamps", {})
    completed = next((times[k] for k in ("finished", "completed", "stopped") if times.get(k)), None)
    if isinstance(completed, str):
        completed = datetime.fromisoformat(completed)
    end = backend.properties(datetime=completed) if completed else None
    evidence = {"job_id": receipt["job_id"], "chunks": chunks,
                "checked_utc": now(), "calibration_preflight": receipt["calibration_timestamp_at_preflight"],
                "calibration_at_job_start": props.last_update_date.isoformat() if props else None,
                "calibration_at_last_chunk": final.last_update_date.isoformat() if final else None,
                "job_completion_utc": completed.isoformat() if completed else None,
                "calibration_at_completion": end.last_update_date.isoformat() if end else None,
                "pub_metadata_matches_manifest": fit["pub_case_ids_match"]}
    write_json(out / "execution_evidence.json", evidence)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("submit", "collect"))
    p.add_argument("--manifest-dir", type=Path, required=True)
    p.add_argument("--approved-manifest-sha256", required=True)
    p.add_argument("--credential-file", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--allow-timestamp-only-refresh", action="store_true")
    p.add_argument("--watch-seconds", type=int, default=0)
    args = p.parse_args()
    logging.getLogger("qiskit_runtime_service").setLevel(logging.CRITICAL)
    try:
        approved_inputs(args.manifest_dir, args.approved_manifest_sha256)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        service, crn = open_account(args.credential_file)
        common = (service, crn, args.manifest_dir, args.output_dir, args.approved_manifest_sha256)
        if args.action == "submit":
            submit(*common, allow_timestamp_only=args.allow_timestamp_only_refresh)
        if args.action == "collect" or args.watch_seconds:
            collect(*common, watch_seconds=args.watch_seconds)
    except Hold as exc:
        p.exit(2, f"HOLD: {exc}\n")
    except Exception as exc:
        p.exit(3, f"IBM operation stopped ({type(exc).__name__}); verify the checkpoint before retrying.\n")


if __name__ == "__main__":
    main()
