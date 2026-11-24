"""Verify and export the completed matched gauge rerun."""

from collections import Counter
import csv
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import shutil
from zipfile import ZIP_DEFLATED, ZipFile
from zoneinfo import ZoneInfo

from ahr02.circuits import measurements
from ahr02_gauge.experiment import ARMS, CONTRASTS, analyze
from ahr02_gauge.matched import instruction_key, signature
from qiskit import qpy


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def time_string(value):
    return datetime.fromisoformat(value).astimezone(ZoneInfo("Asia/Singapore")).strftime("%Y-%m-%d %H:%M:%S SGT")


def signed(value):
    return "0.00000" if abs(value) < 0.000005 else f"{value:+.5f}"


def interval(stat):
    return "[" + ", ".join(signed(value) for value in stat["newcombe_95"]) + "]"


source = Path("work/ahr02-gauge-live")
root = Path("outputs/AHR-02-gauge")
destination = root / "results"
manifest = read(source / "manifest.json")
job = read(source / "pilot_counts.json")
checkpoint = read(source / "pilot_job.json")
quota = read(source / "post_run_allocation.json")
simulations = read(source / "simulation.json")
assert job["job_id"] == checkpoint["job_id"] and job["status"] == "DONE"
assert job["free_account_check"]["plan"] == "open"
assert job["free_account_check"]["remaining_qpu_seconds"] >= job["max_execution_time_s"]
assert all(status == "pass" for status in manifest["validation"]["checks"].values())
assert simulations["matched"]["max_absolute_site_error"] < 1e-8
assert simulations["legacy_recompiled"]["max_absolute_site_error"] < 1e-8
pilot = source / "pilot.qpy"
assert sha256(pilot.read_bytes()).hexdigest() == manifest["qpy"]["sha256"] == job["qpy_sha256"]
with pilot.open("rb") as stream:
    circuits = qpy.load(stream)
assert len(circuits) == len(job["counts"]) == 16
assert [c.metadata["case_id"] for c in circuits] == manifest["ordered_circuits"]
assert all(c.num_clbits == 3 and signature(c) == manifest["native_skeleton_sha256"] for c in circuits)
assert len({measurements(c) for c in circuits}) == 1
reps = {arm: next(c for c in circuits if c.metadata["arm"] == arm) for arm in ARMS}
ref = instruction_key(reps["gradient"], parameters=True)
gauge = instruction_key(reps["gauge_copy"], parameters=True)
assert ref == instruction_key(reps["gradient_repeat"], parameters=True)
phase_start = manifest["validation"]["amplitude_prefix_instructions"]
assert ref[:phase_start] == gauge[:phase_start]
assert all(ref[i][0] == "rz" and i >= phase_start
           for i, (a, b) in enumerate(zip(ref, gauge, strict=True)) if a != b)
shots = 2048
assert all(sum(counter.values()) == shots for counter in job["counts"].values())
assert 16 * shots == manifest["resource_estimate"]["total_shots"]
aggregate = {arm: Counter() for arm in ARMS}
for circuit in circuits:
    aggregate[circuit.metadata["arm"]].update(job["counts"][circuit.metadata["case_id"]])
assert all(sum(arm.values()) == 8192 for arm in aggregate.values())
analyze(source)
observations = read(source / "observations.json")
actual = observations["pooled_contrasts"]
for key, (positive, reference, outcomes) in CONTRASTS.items():
    expected = sum(aggregate[positive][s] - aggregate[reference][s] for s in outcomes) / 8192
    assert abs(actual[key]["delta"] - expected) < 1e-12
with (source / "site_probabilities.csv").open(encoding="utf-8", newline="") as stream:
    assert len(list(csv.DictReader(stream))) == 32

patch_labels = manifest["calibration"]["logical_to_initial_physical"]
patch = tuple(patch_labels[key] for key in "xyz")
manifest["matched_wiring"] = {
    "initial_physical_xyz": (patch[2], patch[1], patch[0]),
    "final_measurement_physical_xyz": measurements(circuits[0]),
}
historical_calibration = read(Path("outputs/AHR-02/results/manifest.json"))["calibration"]
assert set(historical_calibration["logical_to_initial_physical"].values()) == set(patch)
previous = simulations["previous_hardware"]
old_metrics = simulations["legacy_recompiled"]["metrics"]
matched_metrics = simulations["matched_circuit_metrics"][0]
legacy_stats = simulations["legacy_recompiled"]["noisy_contrasts"]
matched_stats = simulations["matched"]["noisy_contrasts"]
labels = {
    "gauge_return": "Gauge copy − gradient, return",
    "incremental_gradient_mass": "Gradient − XY + XZ, fixed site mass",
    "incremental_gradient_return": "Gradient − XY + XZ, return",
    "identical_repeat_return": "Identical gradient repeat − gradient, return",
}
status = (
    "The interval meets the ±0.02 practical-equivalence criterion."
    if observations["gauge_return_interval_inside_margin"] else
    "The interval extends outside the ±0.02 practical-equivalence margin."
)
lines = [
    "# AHR-02 · Matched gauge-copy rerun",
    "",
    f"The matched rerun completed on **{job['backend']}**, IBM job **{job['job_id']}**, and was collected "
    f"{time_string(job['retrieved_utc'])}. The independently synthesized original pilot was {previous['job_id']}.",
    "",
    f"At $t=1.5$, the matched gauge-copy return shift was **{signed(actual['gauge_return']['delta'])}** with "
    f"95% interval **{interval(actual['gauge_return'])}**. {status} The original hardware point estimate "
    f"was {signed(previous['gauge_return']['delta'])}. The matched site-mass contrast for gradient versus "
    f"XY + XZ was **{signed(actual['incremental_gradient_mass']['delta'])}**, with 95% interval "
    f"**{interval(actual['incremental_gradient_mass'])}**.",
    "",
    "| Contrast | Exact | Legacy Aer | Matched Aer | Original IBM | Matched IBM | Matched IBM 95% interval |",
    "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
]
for key, label in labels.items():
    prior = signed(previous[key]["delta"]) if key in previous else "—"
    legacy = signed(legacy_stats[key]["delta"]) if key in legacy_stats else "—"
    lines.append(f"| {label} | {signed(simulations['mathematical'][key])} | {legacy} | "
                 f"{signed(matched_stats[key]['delta'])} | {prior} | {signed(actual[key]['delta'])} | "
                 f"{interval(actual[key])} |")
lines.extend([
    "",
    "The gauge interval excludes zero even with the matched gate skeleton and identical magnitude "
    "preparation. The identical-gradient control interval includes zero. The fixed-site gradient "
    "interval contains the exact redistribution prediction, and the gradient return interval includes "
    "zero. The fixed outcomes were 000, 010, 011, 100, 101, and 110.",
    "",
    "The same three physical qubits were available for the original and matched runs. The matched "
    "state preparation changes the logical readout mapping relative to the legacy circuits and uses "
    "a later calibration. These cross-run differences leave the mechanism of the original shift "
    "unresolved. The terminal virtual phases were the only "
    "intentional parameter changes within the matched gauge pair.",
    "",
    "## Circuit and simulation verification",
    "",
    f"All {len(manifest['validation']['checks'])} matched-design checks passed. The largest absolute "
    f"ideal compiled site error was {simulations['matched']['max_absolute_site_error']:.2e} for the "
    f"matched implementation and {simulations['legacy_recompiled']['max_absolute_site_error']:.2e} "
    "for the recompiled legacy implementation.",
    "",
    "| Circuit | Depth | Native CZ gates | Logical $x,y,z$ readout physical qubits |",
    "| --- | ---: | ---: | --- |",
])
for name, arm in old_metrics.items():
    readout = ", ".join(map(str, arm["final_measurement_physical_xyz"]))
    lines.append(f"| Legacy {name} | {arm['depth']} | {arm['two_qubit_gates']} | {readout} |")
readout = ", ".join(map(str, matched_metrics["physical_measurement_xyz"]))
lines.append(f"| Each matched arm | {matched_metrics['depth']} | {matched_metrics['native_counts']['cz']} | {readout} |")
lines.extend([
    "",
    f"Live rerun calibration was {time_string(manifest['calibration']['calibration_timestamp'])}. "
    f"The original pilot calibration was {time_string(historical_calibration['calibration_timestamp'])}. "
    "Both simulations here use the rerun calibration and 65,536 shots per arm for the noise model. "
    "Ideal simulation also verifies the complex output of each state-preparation circuit up to global phase.",
    "",
    "## Allocation and block results",
    "",
    f"Four blocks of four circuits returned 32,768 shots in total. The open allocation before the job was "
    f"{job['free_account_check']['remaining_qpu_seconds']:g} s, with a {job['max_execution_time_s']:g} s "
    f"job cap. IBM recorded **{job['quantum_seconds']:g} s** of QPU use, leaving "
    f"**{quota['remaining_qpu_seconds']:g} s**. The matched estimates pool repeated arms across the four "
    "position-balanced submission blocks. The repeated-gradient shots form a separate diagnostic.",
    "",
    "| Block | Gauge return | Incremental gradient site mass | Identical-repeat return |",
    "| --- | ---: | ---: | ---: |",
])
for label, block in observations["per_block_contrasts"].items():
    lines.append(f"| {label} | {signed(block['gauge_return']['delta'])} | "
                 f"{signed(block['incremental_gradient_mass']['delta'])} | "
                 f"{signed(block['identical_repeat_return']['delta'])} |")
lines.extend([
    "",
    "- [Matched contrast figure](results/matched_contrasts.png) · [All site probabilities](results/site_probabilities.csv)",
    "- [Raw IBM counts](results/pilot_counts.json) · [Calibration and circuit manifest](results/manifest.json)",
    "- [Full simulation comparison](results/simulation.json) · [Block and pooled contrasts](results/observations.json)",
])
destination.mkdir(exist_ok=True)
for filename in (
    "observations.json", "pilot_counts.json", "pilot_job.json", "pilot.qpy", "post_run_allocation.json",
    "simulation.json", "site_probabilities.csv", "matched_contrasts.png",
):
    shutil.copy2(source / filename, destination / filename)
(destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
(root / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
with ZipFile(root.with_suffix(".zip"), "w", ZIP_DEFLATED) as archive:
    for path in sorted(root.rglob("*")):
        if path.is_file() and not {"__pycache__", ".pytest_cache", ".ruff_cache", "runs"}.intersection(path.parts):
            archive.write(path, path.relative_to(root.parent))
    for prior, module in (("AHR-01", "ahr01"), ("AHR-02", "ahr02")):
        for path in sorted((root.parent / prior / module).glob("*.py")):
            archive.write(path, Path(root.name) / module / path.name)
with ZipFile(root.with_suffix(".zip")) as archive:
    assert archive.testzip() is None
print(json.dumps({
    "job_id": job["job_id"], "usage_seconds": job["quantum_seconds"],
    "free_seconds_after": quota["remaining_qpu_seconds"], "hardware_contrasts": actual,
    "matched_wiring": manifest["matched_wiring"], "native_counts": matched_metrics["native_counts"],
}, indent=2))
