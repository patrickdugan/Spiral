"""Verify the collected IBM tomography settings and export the live result."""

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import shutil
from zipfile import ZIP_DEFLATED, ZipFile
from zoneinfo import ZoneInfo

import numpy as np

from ahr01.model import FLUXES, state
from ahr01.statistics import tomography


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def local_time(value):
    return datetime.fromisoformat(value).astimezone(ZoneInfo("Asia/Singapore")).strftime(
        "%Y-%m-%d %H:%M:%S SGT"
    )


pilot_path = Path("work/live-pilot")
refreshed_path = Path("work/live-tomography")
source = refreshed_path if (refreshed_path / "tomography_counts.json").exists() else pilot_path
destination = Path("outputs/AHR-01-tomography")
pilot = read(pilot_path / "pilot_counts.json")
manifest = read(source / "manifest.json")
job = read(source / "tomography_counts.json")
checkpoint = read(source / "tomography_job.json")
entanglement = read(source / "entanglement.json")
post_quota_path = source / "post_tomography_allocation.json"
post_quota = read(post_quota_path) if post_quota_path.exists() else None
usage_check_path = source / "tomography_usage_check.json"
usage_check = read(usage_check_path) if usage_check_path.exists() else None
settings = [x + y for x in "XYZ" for y in "XYZ"]
expected_ids = [f"tomo_{word}_t0.8_{axes}" for word in ("0", "pi") for axes in settings]

assert pilot["status"] == job["status"] == "DONE"
assert job["job_id"] == checkpoint["job_id"] and job["preceding_pilot_job_id"] == pilot["job_id"]
assert manifest["target_type"] == "live" and manifest["selection"]["tomography"] == "exact"
assert manifest["ordered_circuits"]["tomography"] == expected_ids
assert job["free_account_check"]["plan"] == "open"
assert job["free_account_check"]["remaining_qpu_seconds"] >= job["max_execution_time_s"]
assert len(job["counts"]) == 18 and set(job["counts"]) == set(expected_ids)
assert job["shots_per_circuit"] == 2048
for outcome in job["counts"].values():
    assert set(outcome) <= {"00", "01", "10", "11"}
    assert sum(outcome.values()) == 2048
for entry in manifest["qpy"].values():
    assert sha256((source / entry["file"]).read_bytes()).hexdigest() == entry["sha256"]
assert job["qpy_sha256"] == manifest["qpy"]["tomography"]["sha256"]

rows = []
for label, phi in (FLUXES[0], FLUXES[2]):
    prefix = f"tomo_{label}_t0.8"
    measured = entanglement[prefix]["hardware"]
    independently_analyzed = tomography(
        {axes: job["counts"][f"{prefix}_{axes}"] for axes in settings}, state(phi, 0.8),
        replicates=manifest["sampling"]["bootstrap_replicates"],
    )
    rho = np.array(measured["density_matrix_real"]) + 1j * np.array(measured["density_matrix_imag"])
    np.testing.assert_allclose(rho, rho.conj().T, atol=1e-12)
    np.testing.assert_allclose(np.trace(rho), 1.0, atol=1e-12)
    assert np.min(np.linalg.eigvalsh(rho)) > -1e-12
    for key in (
        "mixed_concurrence", "concurrence_bootstrap_95_descriptive",
        "witness", "witness_upper_95_hoeffding",
    ):
        np.testing.assert_allclose(measured[key], independently_analyzed[key], atol=1e-10, rtol=0)
    certified = measured["witness_upper_95_hoeffding"] < 0
    assert certified == measured["certifies_entanglement_at_95"]
    rows.append({
        "flux": label, "ideal_concurrence": entanglement[prefix]["exact_pure_concurrence"],
        "aer_concurrence": entanglement[prefix]["aer_noisy"]["mixed_concurrence"],
        **{key: value for key, value in measured.items() if not key.startswith("density_matrix")},
    })

layout = manifest["calibration"]["logical_to_physical"]
planned = manifest["resource_estimates"]["tomography"]
finished = local_time(job["retrieved_utc"])
certified_fluxes = ["π" if row["flux"] == "pi" else "0" for row in rows if row["certifies_entanglement_at_95"]]
if certified_fluxes:
    certification = f"The fixed witness certified entanglement at the 95% level for flux {', '.join(certified_fluxes)}."
else:
    certification = "Both witness upper bounds included nonnegative values."

lines = [
    "# AHR-01 · IBM entanglement tomography",
    "",
    f"**DONE** on {job['backend']}. IBM job ID **{job['job_id']}**. Results collected on {finished}. "
    f"The preceding return-probability pilot was {pilot['job_id']}.",
    "",
    f"At $t=0.8$, all nine local Pauli settings were measured at both fluxes. {certification}",
    "",
    "| Flux | Ideal concurrence | Calibrated Aer concurrence | QPU concurrence | QPU 95% bootstrap interval | QPU witness | Witness 95% upper bound |",
    "| --- | ---: | ---: | ---: | --- | ---: | ---: |",
]
for row in rows:
    label = "π" if row["flux"] == "pi" else "0"
    low, high = row["concurrence_bootstrap_95_descriptive"]
    lines.append(
        f"| {label} | {row['ideal_concurrence']:.5f} | {row['aer_concurrence']:.5f} | "
        f"{row['mixed_concurrence']:.5f} | [{low:.5f}, {high:.5f}] | "
        f"{row['witness']:+.5f} | {row['witness_upper_95_hoeffding']:+.5f} |"
    )
tomo_balance = (
    f" The post-run Open Plan balance was {post_quota['remaining_qpu_seconds']:g} s." if post_quota else ""
)
if job["quantum_seconds"] > 0:
    billed = f"IBM reported **{job['quantum_seconds']:g} s** of QPU use."
else:
    billed = "IBM initially reported zero job seconds. Use the account balance below for the observed allocation change."
lines.extend([
    "",
    f"IBM returned {planned['total_shots']:,} shots across {planned['circuit_count']} circuits, "
    f"with {job['shots_per_circuit']:,} shots per setting. The physical layout was "
    f"$x\\mapsto {layout['x_q0']}$ and $y\\mapsto {layout['y_q1']}$ with calibration from "
    f"{local_time(manifest['calibration']['calibration_timestamp'])}.",
    "",
    f"The verified free balance before submission was {job['free_account_check']['remaining_qpu_seconds']:g} s. "
    f"The execution cap was {job['max_execution_time_s']} s. {billed}"
    f"{tomo_balance}",
    "",
    "Measurement settings are written in logical $x,y$ order. Outcome strings and the reconstructed "
    "density matrices are in Qiskit $y,x$ order. Each density matrix comes from linear Pauli inversion "
    "and Frobenius projection onto positive, trace-one matrices. Wootters concurrence is reported "
    "with a 600-resample descriptive multinomial bootstrap interval. Near the separable boundary, "
    "finite shots and positivity projection can bias the concurrence estimate. "
    "[Wootters (1998)](https://doi.org/10.1103/PhysRevLett.80.2245)",
    "",
    "The fixed ideal-state projector witness uses the largest squared Schmidt coefficient as the "
    "separable overlap bound. It is evaluated directly from the measured Pauli statistics. "
    "An upper one-sided 95% Hoeffding bound below zero certifies entanglement under independent "
    "sampling and the stated local Pauli measurement model.",
    "",
    "- [Density matrices and entanglement analysis](entanglement.json) · [Raw IBM counts](tomography_counts.json)",
    "- [Calibration manifest](manifest.json) · [Tomography QPY](tomography.qpy) · [Exact and Aer setting predictions](tomography_predictions.json)",
    "- [Submission and resource record](tomography_job.json)",
])
if post_quota:
    lines.append("- [Post-run Open Plan allocation](post_tomography_allocation.json)")
if usage_check:
    lines.append("- [Final provider job-usage check](tomography_usage_check.json)")

destination.mkdir(exist_ok=True)
filenames = [
    "entanglement.json", "manifest.json", "pilot.qpy", "tomography.qpy",
    "tomography_counts.json", "tomography_job.json", "tomography_predictions.json",
]
if post_quota:
    filenames.append("post_tomography_allocation.json")
if usage_check:
    filenames.append("tomography_usage_check.json")
for filename in filenames:
    shutil.copy2(source / filename, destination / filename)
(destination / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
with ZipFile(destination.with_suffix(".zip"), "w", ZIP_DEFLATED) as archive:
    for filename in ("README.md", *filenames):
        item = destination / filename
        archive.write(item, item.relative_to(destination.parent))
with ZipFile(destination.with_suffix(".zip")) as archive:
    assert archive.testzip() is None
print(json.dumps({
    "job_id": job["job_id"], "backend": job["backend"], "usage_seconds": job["quantum_seconds"],
    "remaining_seconds": post_quota["remaining_qpu_seconds"] if post_quota else None,
    "results": rows,
}, indent=2))
