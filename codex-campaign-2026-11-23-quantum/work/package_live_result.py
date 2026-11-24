"""Verify the collected pilot and package the user-facing live run."""

import csv
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import shutil
from zipfile import ZIP_DEFLATED, ZipFile
from zoneinfo import ZoneInfo


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def format_interval(interval):
    return f"[{interval[0]:+.5f}, {interval[1]:+.5f}]"


def format_delta(value):
    return "0.00000" if abs(value) < 0.000005 else f"{value:+.5f}"


def singapore_time(value):
    return datetime.fromisoformat(value).astimezone(ZoneInfo("Asia/Singapore")).strftime(
        "%Y-%m-%d %H:%M:%S SGT"
    )


source = Path("work/live-pilot")
destination = Path("outputs/AHR-01-live")
manifest = read(source / "manifest.json")
job = read(source / "pilot_counts.json")
job_checkpoint = read(source / "pilot_job.json")
observations = read(source / "pilot_observations.json")
contrasts = read(source / "contrasts.json")
post_run = read(source / "post_run_allocation.json") if (source / "post_run_allocation.json").exists() else None

assert manifest["target_type"] == "live"
assert job["status"] == "DONE" and job["job_id"] == job_checkpoint["job_id"]
assert job["free_account_check"]["plan"] == "open"
assert job["free_account_check"]["remaining_qpu_seconds"] >= job["max_execution_time_s"]
assert len(job["counts"]) == len(observations) == 17
assert set(job["counts"]) == set(manifest["ordered_circuits"]["pilot"])
for outcome in job["counts"].values():
    assert set(outcome) <= {"00", "01", "10", "11"}
    assert sum(outcome.values()) == 2048
for entry in manifest["qpy"].values():
    assert sha256((source / entry["file"]).read_bytes()).hexdigest() == entry["sha256"]
assert job["qpy_sha256"] == manifest["qpy"]["pilot"]["sha256"]
with (source / "return_probabilities.csv").open(encoding="utf-8", newline="") as stream:
    table = list(csv.DictReader(stream))
assert len(table) == 17 and all(row["hardware_p00"] for row in table)

primary, = (row for row in contrasts if row["prespecified_primary"])
tree, = (row for row in contrasts if row["tree"])
cases = {row["label"]: row for row in observations if not row["tree"] and row["time"] == 1.6}
raw_p00 = {
    key: job["counts"][row["id"]].get("00", 0) / 2048 for key, row in cases.items()
}
assert abs(primary["hardware"]["delta"] - (raw_p00["pi"] - raw_p00["0"])) < 1e-12
calibration = manifest["calibration"]
layout = calibration["logical_to_physical"]
planned = manifest["resource_estimates"]["pilot"]
method = manifest["selection"]["pilot"]
method_error = manifest["selection"]["methods"][method]["max_p00_error"]
hardware_low, hardware_high = primary["hardware"]["newcombe_95"]
tree_low, tree_high = tree["hardware"]["newcombe_95"]
primary_statement = (
    "The primary interval lies above zero." if hardware_low > 0 else
    "The primary interval lies below zero." if hardware_high < 0 else
    "The primary interval includes zero."
)
tree_statement = (
    "The broken-square interval includes zero." if tree_low <= 0 <= tree_high else
    "The broken-square interval excludes zero, which warrants checking device and compilation effects."
)
usage_sentence = f"IBM reported **{job['quantum_seconds']:.3f} s** of QPU use."
if post_run:
    usage_sentence += f" The first post-run balance showed **{post_run['remaining_qpu_seconds']:.3f} s** remaining."

lines = [
    "# AHR-01 · IBM Quantum pilot",
    "",
    f"**DONE** on {job['backend']}. IBM job ID **{job['job_id']}**. Submitted on "
    f"{singapore_time(job_checkpoint['attempt_started_utc'])} and collected on "
    f"{singapore_time(job['retrieved_utc'])}.",
    "",
    f"The prespecified square contrast at $t=1.6$ was **{primary['hardware']['delta']:+.5f}** "
    f"with a 95% Newcombe interval of **{format_interval(primary['hardware']['newcombe_95'])}**. "
    f"{primary_statement} {tree_statement}",
    "",
    "| $t=1.6$ contrast | Exact | Compiled ideal | Calibrated Aer | IBM QPU | QPU 95% interval |",
    "| --- | ---: | ---: | ---: | ---: | --- |",
]
for label, row in [("Closed square, π vs. 0", primary), ("Broken square, π vs. 0", tree)]:
    lines.append(
        f"| {label} | {format_delta(row['exact_delta'])} | {format_delta(row['aer_ideal_delta'])} | "
        f"{row['aer_noisy']['delta']:+.5f} | {row['hardware']['delta']:+.5f} | "
        f"{format_interval(row['hardware']['newcombe_95'])} |"
    )
lines.extend([
    "",
    "| Closed-square flux at $t=1.6$ | Exact $P_{00}$ | Compiled ideal | Calibrated Aer | QPU $P_{00}$ | QPU 95% Wilson interval |",
    "| --- | ---: | ---: | ---: | ---: | --- |",
])
for key, label in [("0", "0"), ("half", "π/2"), ("pi", "π")]:
    row = cases[key]
    low, high = row["hardware"]["wilson_95"]
    lines.append(
        f"| {label} | {row['exact_site_probabilities'][0]:.5f} | {row['aer_ideal_p00']:.5f} | "
        f"{row['aer_noisy']['p00']:.5f} | {row['hardware']['p00']:.5f} | [{low:.5f}, {high:.5f}] |"
    )
lines.extend([
    "",
    f"The pilot returned **{planned['total_shots']:,} shots** across 15 square circuits and two "
    f"tree controls. The physical layout was $x\\mapsto {layout['x_q0']}$ and "
    f"$y\\mapsto {layout['y_q1']}$. The selected synthesis was {method.replace('strang_8', 'second-order Suzuki–Trotter with eight repetitions')}. "
    f"Its maximum absolute ideal $P_{{00}}$ error across the 17 cases was {method_error:.5f}. "
    f"The calibration snapshot was {singapore_time(calibration['calibration_timestamp'])}.",
    "",
    f"The verified Open Plan balance before submission was {job['free_account_check']['remaining_qpu_seconds']} s. "
    f"The job used a {job['max_execution_time_s']} s QPU cap. {usage_sentence}",
    "",
    "The counts test site-basis return probabilities. Entanglement results in this directory come "
    "from simulation. Sampling intervals account for shot noise, and the calibration-derived Aer model "
    "provides a comparison for device effects. Both tree flux arms used the same missing edge.",
    "",
    "## Run files",
    "",
    "- [Raw IBM counts and usage](pilot_counts.json) · [Submission record](pilot_job.json)",
    "- [Return probabilities and intervals](return_probabilities.csv) · [Return-probability plot](return_probabilities.png) · [Flux contrasts](contrasts.json)",
    "- [Live compilation and calibration manifest](manifest.json) · [Compiled circuit comparison](compilation.json) · [Pilot QPY](pilot.qpy)",
])
if post_run:
    lines.append("- [Post-run Open Plan allocation](post_run_allocation.json)")

destination.mkdir(exist_ok=True)
filenames = [
    "compilation.json", "contrasts.json", "entanglement.json", "manifest.json",
    "pilot_counts.json", "pilot_job.json", "pilot_observations.json", "pilot_predictions.json",
    "pilot.qpy", "return_probabilities.csv", "return_probabilities.png",
    "tomography.qpy", "tomography_predictions.json",
]
if post_run:
    filenames.append("post_run_allocation.json")
for name in filenames:
    shutil.copy2(source / name, destination / name)
(destination / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
with ZipFile(destination.with_suffix(".zip"), "w", ZIP_DEFLATED) as archive:
    for name in ("README.md", *filenames):
        path = destination / name
        archive.write(path, path.relative_to(destination.parent))
with ZipFile(destination.with_suffix(".zip")) as archive:
    assert archive.testzip() is None
print(json.dumps({
    "job_id": job["job_id"], "status": job["status"], "usage_seconds": job["quantum_seconds"],
    "primary": primary, "tree": tree, "p00": raw_p00,
}, indent=2))
