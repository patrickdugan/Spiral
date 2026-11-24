"""Read IBM historical calibration metadata for the completed pilot's endpoints."""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from backend_snapshot import open_account, write_json
from q3_approved_execution import read


def selected_properties(properties, layout):
    data = properties.to_dict()
    result = {}
    for q in layout:
        for entry in data["qubits"][q]:
            result[f"q{q}/{entry['name']}"] = [entry["value"], entry.get("unit")]
    for entry in data["gates"]:
        if set(entry["qubits"]) <= set(layout):
            gate = entry["gate"] + "/" + ",".join(map(str, entry["qubits"]))
            for parameter in entry["parameters"]:
                result[f"{gate}/{parameter['name']}"] = [parameter["value"], parameter.get("unit")]
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--credential-file", required=True)
    p.add_argument("--job-dir", required=True, type=Path)
    args = p.parse_args()
    receipts = args.job_dir
    recorded = read(receipts / "hardware_job.json")
    evidence = read(receipts / "execution_evidence.json")
    try:
        service, _ = open_account(args.credential_file)
        job = service.job(recorded["job_id"])
        start = job.properties()
        end = job.backend().properties(datetime=datetime.fromisoformat(evidence["job_completion_utc"]))
        layout = recorded["physical_xyz"]
        a, b = selected_properties(start, layout), selected_properties(end, layout)
        changed = {k: {"start": a.get(k), "completion": b.get(k)}
                   for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)}
        result = {"job_id": job.job_id(), "physical_xyz": layout,
                  "checked_utc": datetime.now(timezone.utc).isoformat(),
                  "start_calibration_timestamp": start.last_update_date.isoformat(),
                  "completion_calibration_timestamp": end.last_update_date.isoformat(),
                  "selected_numeric_calibration_equal": not changed,
                  "selected_start_properties": a, "selected_completion_properties": b,
                  "changed_properties": changed}
        write_json(receipts / "boundary_calibration.json", result)
        print(f"Compared {len(a)} selected properties; {len(changed)} differ.")
    except Exception as exc:
        p.exit(1, f"Read-only job calibration comparison failed ({type(exc).__name__}).\n")


if __name__ == "__main__":
    main()
