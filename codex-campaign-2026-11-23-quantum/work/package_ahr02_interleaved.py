"""Verify and export the common-calibration IBM gauge comparison."""

from collections import Counter
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import shutil
from zipfile import ZIP_DEFLATED, ZipFile
from zoneinfo import ZoneInfo

from ahr02.circuits import measurements
from ahr02_gauge.matched import signature
from ahr02_interleaved.design import ARMS, BLOCKS, PHYSICAL_PATCH
from ahr02_interleaved.plot import plot
from qiskit import qpy


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def local(value):
    return datetime.fromisoformat(value).astimezone(ZoneInfo("Asia/Singapore")).strftime("%Y-%m-%d %H:%M:%S SGT")


def signed(value):
    return f"{value:+.5f}"


def interval(bounds):
    return "[" + ", ".join(signed(value) for value in bounds) + "]"


run = Path("work/ahr02-interleaved-live")
root = Path("outputs/AHR-02-interleaved")
destination = root / "results"
manifest = read(run / "manifest.json")
job = read(run / "pilot_counts.json")
submitted = read(run / "pilot_job.json")
simulation = read(run / "simulation.json")
observations = read(run / "observations.json")
execution = read(run / "execution_evidence.json")
quota = read(run / "post_run_allocation.json")
expected = [f"{arm}_b{block}" for block, order in enumerate(BLOCKS, 1) for arm in order]
assert job["job_id"] == submitted["job_id"] == execution["job_id"] and job["status"] == "DONE"
assert manifest["target_type"] == "live" and job["free_account_check"]["plan"] == "open"
assert job["free_account_check"]["remaining_qpu_seconds"] >= job["max_execution_time_s"]
assert all(state == "pass" for state in manifest["validation"]["checks"].values())
assert manifest["ordered_circuits"] == expected and set(job["counts"]) == set(expected)
assert len(expected) == 32 and sum(sum(arm.values()) for arm in job["counts"].values()) == 65536
assert all(sum(counts.values()) == 2048 for counts in job["counts"].values())
assert execution["provider_pub_case_ids_verified"]
assert execution["provider_published_item_indices"] == list(range(len(expected)))
assert execution["calibration"]["same_snapshot_verified_at_job_start_and_last_chunk"]
file = run / "pilot.qpy"
assert sha256(file.read_bytes()).hexdigest() == manifest["qpy"]["sha256"] == job["qpy_sha256"]
with file.open("rb") as stream:
    circuits = qpy.load(stream)
readout = tuple(manifest["logical_readout_physical_xyz"])
assert [c.metadata["case_id"] for c in circuits] == expected
assert all(measurements(c) == readout for c in circuits)
assert set(readout) == set(PHYSICAL_PATCH)
assert all(
    all(circuit.find_bit(bit).index in PHYSICAL_PATCH for gate in circuit.data for bit in gate.qubits)
    for circuit in circuits
)
assert len({signature(c) for c in circuits if c.metadata["arm"].startswith("matched_")}) == 1
pooled = {arm: Counter() for arm in ARMS}
for circuit in circuits:
    pooled[circuit.metadata["arm"]].update(job["counts"][circuit.metadata["case_id"]])
assert pooled == observations["pooled_counts"]
assert all(sum(outcomes.values()) == 16384 for outcomes in pooled.values())
legacy_delta = (pooled["legacy_copy"]["000"] - pooled["legacy_gradient"]["000"]) / 16384
matched_delta = (pooled["matched_copy"]["000"] - pooled["matched_gradient"]["000"]) / 16384
observed = observations["pooled_comparisons"]
assert observed["legacy_gauge_return"]["delta"] == legacy_delta
assert observed["matched_gauge_return"]["delta"] == matched_delta
interaction = observed["matched_minus_legacy_gauge_shift"]
assert interaction["delta"] == matched_delta - legacy_delta

simulated = simulation["calibrated_aer_comparisons"]
block_values = [row["matched_minus_legacy_gauge_shift"]["delta"]
                for row in observations["per_block_comparisons"].values()]
plot(run / "interleaved_contrasts.png", simulated, observed, block_values)
calibration = execution["calibration"]
effect_interval = interaction["wald_95"]
equivalence = observations["matched_gauge_interval_inside_margin"]
names = (
    ("Legacy gauge copy − gradient", "legacy_gauge_return", "newcombe_95"),
    ("Matched gauge copy − gradient", "matched_gauge_return", "newcombe_95"),
    ("Matched gauge shift − legacy gauge shift", "matched_minus_legacy_gauge_shift", "wald_95"),
)
lines = [
    "# AHR-02 · Interleaved legacy and matched gauge pairs",
    "",
    f"IBM job **{job['job_id']}** completed on **{job['backend']}**. Results were collected at "
    f"{local(job['retrieved_utc'])}. "
    "Both pairs used physical qubits 38, 49 and 48, with logical $x,y,z$ read out on "
    f"{readout[0]}, {readout[1]} and {readout[2]} respectively. IBM returned the same calibration "
    f"snapshot used for simulation at job start and at the last chunk, dated {local(calibration['prepared_calibration'])}.",
    "",
    f"Under these shared conditions, the matched gauge shift was **{signed(interaction['delta'])}** "
    f"relative to the legacy shift, with 95% interval **{interval(effect_interval)}**. The block-based "
    f"95% interval was **{interval(observations['block_t_95_for_matched_minus_legacy'])}**.",
    "",
    "| Contrast at $t=1.5$ | Ideal | Calibrated Aer | Aer 95% interval | IBM QPU | IBM 95% interval |",
    "| --- | ---: | ---: | --- | ---: | --- |",
]
for label, key, bound in names:
    aer, hardware = simulated[key], observed[key]
    lines.append(
        f"| {label} | 0.00000 | {signed(aer['delta'])} | {interval(aer[bound])} | "
        f"{signed(hardware['delta'])} | {interval(hardware[bound])} |"
    )
equivalence_sentence = (
    "The matched gauge interval includes zero and meets the ±0.02 equivalence criterion." if equivalence
    else "The matched gauge interval extends outside the ±0.02 equivalence margin."
)
lines.extend([
    "",
    f"{equivalence_sentence} The legacy gauge interval lies above zero. "
    "The same-job comparison isolates the circuit implementation as a factor under the shared patch, "
    "readout and calibration. The families differ in synthesis, gate count and state-preparation scope, "
    "so the microscopic mechanism of the residual legacy shift remains unresolved.",
    "",
    "## Circuit and execution evidence",
    "",
    "The ideal Aer simulations agree with the full eight-outcome reference for every circuit. "
    f"The worst absolute site error was {max(simulation['ideal_max_site_error_by_arm'].values()):.2e}. "
    "Each calibrated-noise estimate used 65,536 shots per arm.",
    "",
    "| Arm | Depth | CZ gates | Readout-alignment SWAPs | Hardware $P_{000}$ |",
    "| --- | ---: | ---: | ---: | ---: |",
])
for arm, row in simulation["arm_metrics"].items():
    p = observed["return_probabilities"][arm]["p00"]
    lines.append(f"| {arm.replace('_', ' ')} | {row['depth']} | {row['native_counts']['cz']} | "
                 f"{row['readout_alignment_swaps']} | {p:.5f} |")
lines.extend([
    "",
    f"The single submitted job used {len(BLOCKS)} position-balanced four-circuit blocks and "
    f"{job['shots_per_circuit']:,} shots per circuit. IBM returned all 32 PUB identifiers in the submitted "
    f"sequence within {len(execution['chunks'])} execution chunk. The published timestamps are at chunk "
    "resolution. The archived QPY and execution evidence provide the circuit order and IBM's chunk record. "
    "[IBM Sampler metadata](https://quantum.cloud.ibm.com/docs/en/ibm-quantum-compute/sampler-input-output)",
    "",
    f"IBM recorded **{job['quantum_seconds']:g} s** of QPU use. The verified Open Plan balance was "
    f"{job['free_account_check']['remaining_qpu_seconds']:g} s before submission and "
    f"**{quota['remaining_qpu_seconds']:g} s** after the job. The execution cap was {job['max_execution_time_s']:g} s.",
    "",
    "- [Contrast figure](results/interleaved_contrasts.png) · [Block and pooled estimates](results/observations.json)",
    "- [Raw counts](results/pilot_counts.json) · [Cloud execution evidence](results/execution_evidence.json)",
    "- [Simulation data](results/simulation.json) · [Reproducibility manifest](results/manifest.json) · [Pilot circuits](results/pilot.qpy)",
])
destination.mkdir(exist_ok=True)
for filename in (
    "manifest.json", "pilot.qpy", "pilot_job.json", "pilot_counts.json", "post_run_allocation.json",
    "execution_evidence.json", "simulation.json", "observations.json", "interleaved_contrasts.png",
):
    shutil.copy2(run / filename, destination / filename)
(root / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
with ZipFile(root.with_suffix(".zip"), "w", ZIP_DEFLATED) as archive:
    for path in sorted(root.rglob("*")):
        if path.is_file() and not {"__pycache__", ".pytest_cache", ".ruff_cache", "runs"}.intersection(path.parts):
            archive.write(path, path.relative_to(root.parent))
    for name, module in (("AHR-01", "ahr01"), ("AHR-02", "ahr02"), ("AHR-02-gauge", "ahr02_gauge")):
        for item in sorted((root.parent / name / module).glob("*.py")):
            archive.write(item, Path(root.name) / module / item.name)
with ZipFile(root.with_suffix(".zip")) as archive:
    assert archive.testzip() is None
print(json.dumps({
    "job_id": job["job_id"], "qpu_seconds": job["quantum_seconds"], "free_after_seconds": quota["remaining_qpu_seconds"],
    "legacy": observed["legacy_gauge_return"], "matched": observed["matched_gauge_return"],
    "effect": interaction, "block_t95": observations["block_t_95_for_matched_minus_legacy"],
}, indent=2))
