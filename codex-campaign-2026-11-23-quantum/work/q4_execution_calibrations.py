"""Compare numeric calibration properties at Q4 preflight and job start."""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from calibration import open_account, write_json
from q4_approved_execution import read


def select(properties, layout):
    data = properties.to_dict()
    selected = {}
    for q in layout:
        for row in data["qubits"][q]:
            selected[f"q{q}/{row['name']}"] = [row["value"], row.get("unit")]
    for gate in data["gates"]:
        if set(gate["qubits"]) <= set(layout):
            key = gate["gate"] + "/" + ",".join(map(str, gate["qubits"]))
            for row in gate["parameters"]:
                selected[f"{key}/{row['name']}"] = [row["value"], row.get("unit")]
    return selected


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--credential-file", required=True)
    p.add_argument("--job-dir", required=True, type=Path)
    args = p.parse_args()
    receipt = read(args.job_dir / "job.json")
    try:
        service, _ = open_account(args.credential_file)
        job = service.job(receipt["job_id"])
        start = job.properties()
        preflight = read(args.job_dir / "preflight.json")["current_target"]
        timestamps = read(args.job_dir / "execution.json")
        history = job.backend().target_history(datetime=datetime.fromisoformat(timestamps["running_utc"]))
        layout = receipt["physical_qubits"]
        a, b = {}, {}
        for row in preflight["instructions"]:
            name, sites = row["gate"], tuple(row["physical"])
            key = f"{name}/{','.join(map(str, sites))}"
            a[key] = [row["error"], row["duration_s"]]
            prop = history[name].get(sites) if name in history else None
            b[key] = [prop.error, prop.duration] if prop else [None, None]
        props = select(start, layout)
        for logical, physical in enumerate(layout):
            a[f"q{physical}/coherence_s"] = preflight["coherence_s"][logical]
            source = history.qubit_properties[physical]
            b[f"q{physical}/coherence_s"] = [source.t1, source.t2]
        for item in preflight["noise"]["errors"]:
            if item["type"] == "roerror":
                for (q,) in item["gate_qubits"]:
                    physical = layout[q]
                    key = f"q{physical}/assignment_errors"
                    a[key] = [item["probabilities"][0][1], item["probabilities"][1][0]]
                    b[key] = [props[f"q{physical}/{label}"][0]
                              for label in ("prob_meas1_prep0", "prob_meas0_prep1")]
        comparison = {k: {"preflight": a.get(k), "job_start": b.get(k)}
                      for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)}
        record = {"job_id": job.job_id(), "physical_qubits": layout,
                  "checked_utc": datetime.now(timezone.utc).isoformat(),
                  "preflight_calibration": preflight["calibration_timestamp"],
                  "job_start_calibration": start.last_update_date.isoformat(),
                  "selected_value_count": len(set(a) | set(b)),
                  "selected_numeric_values_equal": not comparison,
                  "changed_properties": comparison, "preflight_values": a, "job_start_values": b}
        write_json(args.job_dir / "calibration_comparison.json", record)
        print(f"Compared {record['selected_value_count']} calibration values: {len(comparison)} changed.")
    except Exception as exc:
        p.exit(1, f"IBM property comparison could not be independently verified ({type(exc).__name__}).\n")


if __name__ == "__main__":
    main()
