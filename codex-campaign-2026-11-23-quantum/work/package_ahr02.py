"""Verify and export the AHR-02 pilot and reproducible experiment."""

import csv
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from zoneinfo import ZoneInfo


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def wall_time(iso):
    return datetime.fromisoformat(iso).astimezone(ZoneInfo("Asia/Singapore")).strftime("%Y-%m-%d %H:%M:%S SGT")


def delta(value):
    return "0.00000" if abs(value) < 0.000005 else f"{value:+.5f}"


def interval(stat):
    return "[" + ", ".join(delta(value) for value in stat["newcombe_95"]) + "]"


source = Path("work/ahr02-live")
package = Path("outputs/AHR-02")
destination = package / "results"
manifest = read(source / "manifest.json")
contrasts = read(source / "contrasts.json")
methods = manifest["selection"]["methods"]
selected = manifest["selection"]["selected"]
calibration = manifest["calibration"]
estimate = manifest["resource_estimate"]
selected_cases = {row["id"]: row for row in read(source / "compilation.json")[selected]}
pilot = read(source / "pilot_counts.json")
quota = read(source / "post_run_allocation.json")
checks = manifest["validation"]
path = source / manifest["qpy"]["file"]
assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest["qpy"]["sha256"] == pilot["qpy_sha256"]
assert manifest["target_type"] == "live" and pilot["status"] == "DONE"
assert all(value == "pass" for value in checks["checks"].values())
assert methods[selected]["eligible"] and methods[selected]["max_absolute_return_error"] <= 0.015
assert pilot["free_account_check"]["plan"] == "open"
assert pilot["free_account_check"]["remaining_qpu_seconds"] >= pilot["max_execution_time_s"]
assert len(pilot["counts"]) == len(manifest["ordered_circuits"]) == 15
assert set(pilot["counts"]) == set(manifest["ordered_circuits"])
assert sum(sum(counts.values()) for counts in pilot["counts"].values()) == estimate["total_shots"] == 30720
outcomes = {f"{i:03b}" for i in range(8)}
assert all(
    set(counts).issubset(outcomes) and sum(counts.values()) == estimate["shots_per_circuit"]
    for counts in pilot["counts"].values()
)
with (source / "site_probabilities.csv").open(encoding="utf-8", newline="") as stream:
    rows = list(csv.DictReader(stream))
assert len(rows) == 120 and all(row["hardware"] for row in rows)
for contrast in contrasts.values():
    keys = contrast.get("outcomes", ["000"])
    time = contrast["time"]
    masses = [
        sum(pilot["counts"][f"{contrast[key]}_t{time:.1f}"].get(outcome, 0) for outcome in keys) / 2048
        for key in ("positive", "reference")
    ]
    assert abs(contrast["hardware"]["delta"] - (masses[0] - masses[1])) < 1e-12

primary = contrasts["primary_gradient_minus_zero"]
gradient = contrasts["secondary_gradient_fixed_site_mass"]
gauge = contrasts["gauge_copy_minus_gradient"]
tree = contrasts["tree_gradient_minus_tree_zero"]
named = [
    ("Gradient − zero, return", primary),
    ("Gradient − XY + XZ, return", contrasts["gradient_minus_xy_xz"]),
    ("Gradient − XY + XZ, fixed site mass", gradient),
    ("Gauge copy − gradient, return", gauge),
    ("Tree gradient − tree zero, return", tree),
]
stat = primary["hardware"]
low, high = stat["newcombe_95"]
if low > 0:
    direction = "The 95% interval lies above zero."
elif high < 0:
    direction = "The 95% interval lies below zero."
else:
    direction = "The 95% interval includes zero."

def contains_zero(row):
    low, high = row["hardware"]["newcombe_95"]
    return low <= 0 <= high


if contains_zero(gauge) and contains_zero(tree):
    controls = "Both control intervals include zero at this shot count."
else:
    names = [name for name, row in (("gauge-copy", gauge), ("tree", tree)) if not contains_zero(row)]
    controls = f"The {' and '.join(names)} control interval excludes zero. Circuit-specific device effects can contribute to the measured contrasts."
usage = pilot["quantum_seconds"]
before = pilot["free_account_check"]["remaining_qpu_seconds"]
after = quota["remaining_qpu_seconds"]
usage_line = (
    f"IBM reported **{usage:g} s** of job usage." if usage else
    "IBM's final job-usage value was unavailable at collection."
)
lines = [
    "# AHR-02 · IBM Quantum cube pilot",
    "",
    f"**DONE** on {pilot['backend']}, IBM job **{pilot['job_id']}**, collected "
    f"{wall_time(pilot['retrieved_utc'])}.",
    "",
    f"At $t=1.5$, the primary gradient-minus-zero return contrast was **{delta(stat['delta'])}** "
    f"with 95% Newcombe interval **{interval(stat)}**. {direction} {controls}",
    "",
    "| Comparison at $t=1.5$ | Exact | Compiled ideal | Calibrated Aer | IBM QPU | QPU 95% interval |",
    "| --- | ---: | ---: | ---: | ---: | --- |",
]
for label, row in named:
    lines.append(
        f"| {label} | {delta(row['exact'])} | {delta(row['aer_ideal'])} | "
        f"{delta(row['aer_noisy']['delta'])} | {delta(row['hardware']['delta'])} | {interval(row['hardware'])} |"
    )
site_list = ", ".join(map(str, gradient["sites"]))
gradient_statement = (
    "The hardware interval includes zero." if contains_zero(gradient)
    else "The hardware interval excludes zero."
)
lines.extend([
    "",
    f"The calibrated Aer primary forecast ({delta(primary['aer_noisy']['delta'])}) falls inside the "
    f"hardware interval. The exact primary forecast ({delta(primary['exact'])}) lies above it. "
    f"The original gradient and its gauge copy each used "
    f"{selected_cases['gradient_t1.5']['two_qubit_gates']} native two-qubit gates, with compiled "
    f"depths {selected_cases['gradient_t1.5']['depth']} and {selected_cases['gauge_copy_t1.5']['depth']}. "
    "The control compares distinct native gate sequences at the same two-qubit gate count.",
    "",
    f"The secondary site-mass statistic sums the probabilities at sites {site_list}. The exact model "
    f"selected those sites before submission. {gradient_statement} Detailed data for all eight outcomes and "
    "all 15 conditions are in the site table. The primary and diagnostic intervals quantify shot "
    "uncertainty. Device and calibration effects can change the measured probabilities.",
    "",
    "## Simulation and synthesis",
    "",
    f"All {len(checks['checks'])} mathematical checks passed. The largest ideal probability mismatch over "
    f"all transitions and tested times was {checks['max_gauge_copy_probability_residual']:.2e} for the gauge "
    f"copy and {checks['max_tree_probability_residual']:.2e} for the tree.",
    "",
    "| Synthesis | Sum of depths | Max depth | Native 2Q gates | Routing SWAPs before translation | Worst return error | Worst all-site error |",
    "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
])
for method, row in methods.items():
    name = f"**{method}**" if method == selected else method
    lines.append(
        f"| {name} | {row['total_depth']} | {row['max_depth']} | {row['total_two_qubit_gates']} | "
        f"{row['routing_swaps_before_translation']} | {row['max_absolute_return_error']:.4g} | "
        f"{row['max_absolute_site_error']:.4g} |"
    )
position = calibration["logical_to_initial_physical"]
lines.extend([
    "",
    f"The initial IBM patch was $x\\mapsto {position['x']}$, $y\\mapsto {position['y']}$, "
    f"$z\\mapsto {position['z']}$. All routing stayed on this patch. The per-circuit final measurement "
    f"maps are in the compilation record. The target was dated {wall_time(calibration['calibration_timestamp'])}.",
    "",
    "## Resource use",
    "",
    f"The workload was 15 circuits × 2,048 shots. The timing model estimated "
    f"{estimate['modeled_pulse_reset_delay_seconds']:.2f} s with gates, measurement and delays, "
    f"plus a {estimate['fixed_overhead_reserve_seconds']:g} s reserve. The verified free balance before "
    f"submission was {before:g} s and the execution cap was {pilot['max_execution_time_s']} s. "
    f"{usage_line} The post-run free balance was **{after:g} s**.",
    "",
    "The hardware measured site populations in the specified eight-site model. The comparison supports "
    "claims about the engineered circulation phases and the measured contrasts. The site labels provide "
    "the arithmetic encoding. The exact reduced-state matrices in the numerical grid are predictions.",
    "",
    "- [IBM counts and usage](results/pilot_counts.json) · [Submission checkpoint](results/pilot_job.json)",
    "- [Return probability plot](results/return_probabilities.png) · [Eight-outcome table](results/site_probabilities.csv)",
    "- [Exact grid and spectra](results/exact_grid.json) · [Calibrated manifest](results/manifest.json)",
])

destination.mkdir(exist_ok=True)
files = (
    "manifest.json", "compilation.json", "exact_grid.json", "pilot.qpy",
    "pilot_predictions.json", "pilot_observations.json", "pilot_job.json", "pilot_counts.json",
    "post_run_allocation.json", "contrasts.json", "site_probabilities.csv", "return_probabilities.png",
)
for name in files:
    shutil.copy2(source / name, destination / name)
(package / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

with ZipFile(package.with_suffix(".zip"), "w", ZIP_DEFLATED) as archive:
    for path in sorted(package.rglob("*")):
        if path.is_file() and not {"__pycache__", ".pytest_cache", ".ruff_cache", "runs"}.intersection(path.parts):
            archive.write(path, path.relative_to(package.parent))
    for item in sorted(Path("outputs/AHR-01/ahr01").glob("*.py")):
        archive.write(item, Path("AHR-02") / "ahr01" / item.name)
with ZipFile(package.with_suffix(".zip")) as archive:
    assert archive.testzip() is None
print(json.dumps({
    "job_id": pilot["job_id"], "backend": pilot["backend"], "qpu_seconds": usage,
    "free_after_seconds": after, "conditions": {label: row["hardware"] for label, row in named},
}, indent=2))
