"""Execute or collect one capped exploratory AHR-QPU-04 pilot."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import ceil, isfinite
from pathlib import Path
import time
from uuid import uuid4

from qiskit import ClassicalRegister, QuantumCircuit, qpy
from qiskit_ibm_runtime import SamplerV2

from calibration import compact_snapshot, open_account, write_json
from circuits import compact_target, measurement_map, timing
from ibm_qpu_03.backend_snapshot import calibration_fingerprint
from noise import STRESS, probabilities

APPROVAL = "99ef1d8f254cf58f052017146eb8d71d74302ae7b69c7edf9a691dedc1c381c0"


class Hold(Exception):
    pass


def require(value, message):
    if not value:
        raise Hold(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def text_sha(path):
    return sha256(path.read_text(encoding="utf-8").encode()).hexdigest()


def inputs(path):
    manifest_path = path / "manifest.json"
    require(text_sha(manifest_path) == APPROVAL, "approved manifest checksum mismatch")
    manifest = read(manifest_path)
    require(text_sha(path / "calibration.json") == manifest["snapshot_sha256"],
            "calibration checksum mismatch")
    circuit_path = path / "q4_candidate_isa.qpy"
    require(sha256(circuit_path.read_bytes()).hexdigest() == manifest["qpy_sha256"],
            "QPY checksum mismatch")
    with circuit_path.open("rb") as stream:
        circuits = qpy.load(stream)
    rows = manifest["cases"]
    require(len(circuits) == len(rows) == manifest["circuit_count"] == 76
            and len({r["case"]["id"] for r in rows}) == 76
            and manifest["shots"] == 155648 and all(r["shots"] == 2048 for r in rows)
            and manifest["provisional_max_seconds"] == 112, "workload or free cap mismatch")
    archived = read(path / "calibration.json")
    original = next(s for s in archived["snapshots"]
                    if s["backend"] == manifest["backend"] and
                    s["selection"]["physical_xyz"] == manifest["physical_qubits"])
    return manifest, original, circuits


def free_balance(service, crn):
    require(service.active_instance() == crn, "verified Open Plan instance changed")
    usage = service.usage()
    ru = usage.get("usage_remaining_ru")
    inferred = 60*ru if isinstance(ru, (int, float)) else None
    values = [v for v in (usage.get("usage_remaining_seconds"), inferred)
              if isinstance(v, (int, float)) and isfinite(v)]
    require(bool(values), "IBM did not report the free balance")
    return {"plan": "open", "checked_utc": now(),
            "remaining_seconds": 0 if usage.get("usage_limit_reached") else max(0, min(values))}


def compact_circuits(circuits, manifest, snapshot):
    layout = manifest["physical_qubits"]
    allowed = {(row["gate"], tuple(row["physical"])) for row in snapshot["instructions"]}
    compact = []
    for circuit, row in zip(circuits, manifest["cases"], strict=True):
        require(circuit.num_qubits == snapshot["backend_width"] and
                circuit.metadata["case_id"] == row["case"]["id"] and
                measurement_map(circuit) == row["measurement_by_classical_bit"],
                "a case ID, backend width, or readout map changed")
        local = QuantumCircuit(4)
        local.add_register(ClassicalRegister(4, "out"))
        for item in circuit.data:
            physical = tuple(circuit.find_bit(q).index for q in item.qubits)
            require(all(q in layout for q in physical), "circuit uses an unapproved physical qubit")
            require(item.operation.name in {"delay", "barrier"} or
                    (item.operation.name, physical) in allowed,
                    "live target no longer supports an approved instruction")
            local.append(item.operation, [layout.index(q) for q in physical],
                         [circuit.find_bit(bit).index for bit in item.clbits])
        compact.append(local)
    return compact


def submit(service, crn, folder, out):
    manifest, original, circuits = inputs(folder)
    checkpoint = out / "job.json"
    require(not checkpoint.exists(), "checkpoint exists; collect or recover it")
    backend = service.backend(manifest["backend"], instance=crn)
    require(backend.status().operational and not backend.configuration().simulator,
            "approved Kingston backend is unavailable")
    fresh = compact_snapshot(backend, original["selection"])
    compact = compact_circuits(circuits, manifest, fresh)
    same_model = (calibration_fingerprint(fresh, include_calibration_identity=False) ==
                  calibration_fingerprint(original, include_calibration_identity=False) and
                  fresh["coherence_s"] == original["coherence_s"])
    require(fresh["rep_delay_s"] is not None, "live backend repetition duration unavailable")
    native = compact_target(fresh)
    metrics = [timing(c, native) for c in compact]
    estimate = manifest["fixed_overhead_assumption_s"] + sum(
        (m["duration_s"] + fresh["rep_delay_s"])*row["shots"]
        for m, row in zip(metrics, manifest["cases"], strict=True))
    cap = manifest["provisional_max_seconds"]
    require(ceil(2*estimate) <= cap, "refreshed resource estimate exceeds the approved cap")
    print(f"Current Kingston calibration {fresh['calibration_timestamp']}; "
          f"same physical model {same_model}; fixed-circuit estimate {estimate:.3f} s.", flush=True)
    if not same_model:
        current = {name: probabilities(compact, fresh, name).tolist() for name in STRESS}
        write_json(out / "refreshed_simulation.json", current)
        print("Simulated the unchanged circuits under the refreshed physical model.", flush=True)
    account = free_balance(service, crn)
    require(account["remaining_seconds"] >= cap, "less than the approved cap remains on the free plan")
    receipt = {"approved_manifest_sha256": APPROVAL, "approved_qpy_sha256": manifest["qpy_sha256"],
               "original_calibration_timestamp": manifest["calibration_timestamp"],
               "current_target": fresh, "same_physical_model": same_model,
               "resource_estimate_s": estimate, "physical_qubits": manifest["physical_qubits"],
               "circuit_count": len(circuits), "shots": manifest["shots"], "account": account,
               "cap_seconds": cap, "cases": [
                   {"id": r["case"]["id"], "readout": r["measurement_by_classical_bit"],
                    "shots": r["shots"], "duration_s": m["duration_s"]}
                   for r, m in zip(manifest["cases"], metrics, strict=True)],
               "exploratory_despite_simulation_gate": True}
    write_json(out / "preflight.json", receipt)
    tag = f"ahr-qpu-04-99ef1d8f-{uuid4().hex[:12]}"
    sampler = SamplerV2(mode=backend, options={
        "max_execution_time": cap, "environment": {"job_tags": [tag]},
        "twirling": {"enable_gates": False, "enable_measure": False},
        "dynamical_decoupling": {"enable": False},
    })
    job_record = {"tag": tag, "job_id": None, "submitted_request_utc": now(),
                  "approved_manifest_sha256": APPROVAL, "preflight_sha256": text_sha(out / "preflight.json"),
                  "preflight_calibration": fresh["calibration_timestamp"], "free_balance": account,
                  "backend": manifest["backend"], "physical_qubits": layout_from(manifest),
                  "cap_seconds": cap, "shots_per_circuit": 2048, "circuits": 76}
    with checkpoint.open("x", encoding="utf-8") as stream:
        json.dump(job_record, stream, indent=2, allow_nan=False)
    job = sampler.run(circuits, shots=2048)
    job_record["job_id"] = job.job_id()
    write_json(checkpoint, job_record)
    print(f"IBM accepted {job_record['job_id']}", flush=True)


def layout_from(manifest):
    return manifest["physical_qubits"]


def collect(service, crn, folder, out, seconds):
    manifest, _, _ = inputs(folder)
    checkpoint = out / "job.json"
    record = read(checkpoint)
    require(record["approved_manifest_sha256"] == APPROVAL, "execution ledger approval mismatch")
    if not record["job_id"]:
        jobs = service.jobs(job_tags=[record["tag"]], instance=crn, limit=2)
        require(len(jobs) == 1, "IBM job could not be uniquely recovered by tag")
        record["job_id"] = jobs[0].job_id()
        write_json(checkpoint, record)
    job = service.job(record["job_id"])
    previous = ""
    end = time.monotonic()+seconds
    while True:
        status = job.status()
        if status != previous:
            print(f"IBM job {record['job_id']} is {status}", flush=True)
            previous = status
        if status in {"DONE", "CANCELLED", "ERROR"} or time.monotonic() >= end:
            break
        time.sleep(8)
    write_json(out / "status.json", {"job_id": record["job_id"], "status": status, "checked_utc": now()})
    if status != "DONE":
        return
    result = job.result()
    rows = manifest["cases"]
    counts, ids = {}, []
    for row, pub in zip(rows, result, strict=True):
        meta = pub.metadata.get("circuit_metadata", {})
        ids.append(meta.get("case_id"))
        sample = pub.data.out.get_counts()
        require(sum(sample.values()) == row["shots"] and
                all(len(k) == 4 and set(k) <= {"0", "1"} for k in sample),
                "IBM returned an invalid shot ledger")
        counts[row["case"]["id"]] = {k: int(v) for k, v in sample.items()}
    usage = job.usage()
    write_json(out / "counts.json", {"job_id": record["job_id"], "status": status,
                                    "retrieved_utc": now(), "counts": counts, "pub_case_ids": ids,
                                    "pub_case_ids_match": ids == list(counts), "qpu_seconds": usage})
    print(f"Collected {sum(sum(c.values()) for c in counts.values())} shots; IBM usage {usage} s.", flush=True)
    write_json(out / "post_allocation.json", free_balance(service, crn))
    calibration = job.properties()
    timestamps = job.metrics().get("timestamps", {})
    start = timestamps.get("running")
    finish = timestamps.get("finished") or timestamps.get("completed")
    endpoint = job.backend().properties(datetime=datetime.fromisoformat(finish)) if finish else None
    write_json(out / "execution.json", {
        "job_id": record["job_id"], "running_utc": start, "completion_utc": finish,
        "start_calibration": calibration.last_update_date.isoformat() if calibration else None,
        "completion_calibration": endpoint.last_update_date.isoformat() if endpoint else None,
        "pub_case_ids_match": ids == list(counts), "read_utc": now()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("submit", "collect"))
    parser.add_argument("--receipt-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--credential-file", required=True, type=Path)
    parser.add_argument("--wait", type=int, default=0)
    args = parser.parse_args()
    try:
        inputs(args.receipt_dir)
        args.output.mkdir(parents=True, exist_ok=True)
        service, crn = open_account(args.credential_file)
        params = (service, crn, args.receipt_dir, args.output)
        if args.action == "submit":
            submit(*params)
        if args.action == "collect" or args.wait:
            collect(*params, args.wait)
    except Hold as exc:
        parser.exit(2, f"HOLD: {exc}\n")
    except Exception as exc:
        parser.exit(3, f"IBM operation stopped ({type(exc).__name__}); verify the checkpoint before retrying.\n")


if __name__ == "__main__":
    main()
