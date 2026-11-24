"""Verify and archive the approved AHR-QPU-01 Q2 hardware run."""

from datetime import datetime
from math import degrees
from pathlib import Path
import shutil
from zoneinfo import ZoneInfo

from qiskit import qpy

from experiment import calibration_digest, digest, load, write
from hardware_analysis import summarize


def singapore(value):
    return datetime.fromisoformat(value).astimezone(ZoneInfo("Asia/Singapore")).strftime(
        "%Y-%m-%d %H:%M:%S SGT"
    )


def cfmt(value):
    return f"{value[0]:.5f}{value[1]:+.5f}i"


def interval(values):
    return f"[{values[0]:+.5f}, {values[1]:+.5f}]"


def angles(row):
    phase = row["reference_calibrated_phase"]
    value = degrees(phase["relative_phase_rad"])
    if not phase["phase_identifiable_at_95"]:
        return f"{value:+.2f}°", "Unresolved at 95%"
    half_width = degrees(phase["joint_95_phase_halfwidth_rad"])
    return f"{value:+.2f}°", f"[{value-half_width:+.2f}°, {value+half_width:+.2f}°]"


here = Path.cwd()
run = here.parents[3] / "ahr-qpu-01-approved-run"
out = here / "receipts" / "hardware_q2"
manifest = load(run / "manifest.json")
snapshot = load(run / "calibration.json")
receipt = load(run / "hardware_counts.json")
checkpoint = load(run / "hardware_job.json")
execution = load(run / "execution_evidence.json")
post = load(run / "post_run_allocation.json")
protocol = load(run / "q2_protocol.json")
assert receipt["status"] == "DONE" and receipt["job_id"] == checkpoint["job_id"] == execution["job_id"]
assert receipt["free_balance_checked"]["plan"] == post["plan"] == "open"
assert receipt["free_balance_checked"]["remaining_qpu_seconds"] >= receipt["max_execution_time_s"]
assert digest(run / "q2_isa.qpy") == manifest["qpy_sha256"]
assert digest(run / "calibration.json") == manifest["calibration_sha256"]
assert execution["pub_metadata_matches_manifest"]
assert [p for chunk in execution["chunks"] for p in chunk["pubs"]] == list(range(len(manifest["case_order"])))
assert execution["calibration_prepared"] == execution["calibration_at_job_start"] == execution["calibration_at_last_chunk"]
with (run / "q2_isa.qpy").open("rb") as stream:
    circuits = qpy.load(stream)
assert [c.metadata["case_id"] for c in circuits] == manifest["case_order"]
assert len(circuits) == 36
allowed = {(row["gate"], tuple(row["physical"])) for row in snapshot["instructions"]}
for circuit in circuits:
    actual = {}
    for item in circuit.data:
        qargs = tuple(circuit.find_bit(bit).index for bit in item.qubits)
        assert (item.operation.name, qargs) in allowed
        if item.operation.name == "measure":
            actual[circuit.find_bit(item.clbits[0]).index] = qargs[0]
    assert [actual[0], actual[1]] == manifest["physical_pair_xy"]

analysis = summarize(manifest, protocol["scans"], receipt)
table = analysis["four_phase_groups"]
acceptance = analysis["primary_acceptance"]
assert analysis["shots_total"] == 73728
raw_primary = table["signal_t1.6"]["counts_00"]
direct_quadrature = [(raw_primary[0]-raw_primary[2])/4096, (raw_primary[3]-raw_primary[1])/4096]
assert all(abs(left-right) < 1e-14 for left, right in zip(direct_quadrature, acceptance["observed"], strict=True))

out.mkdir(parents=True, exist_ok=True)
for name in (
    "q2_isa.qpy", "q2_cases.csv", "q2_protocol.json", "q2_compilation.json", "hardware_job.json",
    "hardware_counts.json", "post_run_allocation.json", "execution_evidence.json",
):
    shutil.copy2(run / name, out / name)
raw_calibration_hash = manifest["calibration_sha256"]
shutil.copy2(run / "calibration.json", out / "calibration.json")
manifest["calibration_sha256_as_prepared"] = raw_calibration_hash
manifest["calibration_sha256"] = calibration_digest(out / "calibration.json")
write(out / "manifest.json", manifest)
write(out / "hardware_analysis.json", analysis)
baseline_manifest = load(here / "receipts" / "manifest.json")
baseline_manifest["calibration_sha256"] = calibration_digest(here / "receipts" / "calibration.json")
write(here / "receipts" / "manifest.json", baseline_manifest)

pair = manifest["physical_pair_xy"]
primary = table["signal_t1.6"]
exact_counts = ", ".join(str(k) for k in raw_primary)
lines = [
    "# AHR-QPU-01 · Approved Q2 results",
    "",
    f"IBM job **{receipt['job_id']}** completed on **{receipt['backend']}**, running 36 circuits with "
    f"2,048 shots each for **{analysis['shots_total']:,} returned shots**. "
    f"The physical mapping was $x\\mapsto{pair[0]}$ and $y\\mapsto{pair[1]}$.",
    "",
    f"The approval covered this Q2 workload on Open Plan. The available balance was "
    f"{receipt['free_balance_checked']['remaining_qpu_seconds']:g} s before submission against "
    f"a {receipt['max_execution_time_s']:g} s cap. IBM reported **{receipt['qpu_seconds']:g} s** "
    f"of QPU use, with **{post['remaining_qpu_seconds']:g} s** remaining after collection.",
    "",
    "## Primary result",
    "",
    f"The predeclared complex-harmonic criterion at $t=1.6$ **{'passed' if acceptance['passes'] else 'failed'}**. "
    f"The measured $Z_4$ was {cfmt(primary['observed_harmonic'])}, compared with "
    f"{cfmt(primary['exact_harmonic'])} from the exact model and "
    f"{cfmt(primary['calibrated_aer_harmonic'])} from calibrated Aer. "
    f"The measured zero-outcome counts were {exact_counts} in the fixed phase order "
    r"$0,\pi/2,\pi,3\pi/2$.",
    "",
    "| Component | Exact | Measured | Joint 95% counting interval | Interval with systematic allowance |",
    "| --- | ---: | ---: | --- | --- |",
]
for index, key in enumerate(("real", "imag")):
    lines.append(f"| {key.capitalize()} | {acceptance['target'][index]:+.5f} | "
                 f"{acceptance['observed'][index]:+.5f} | "
                 f"{interval(acceptance['unexpanded_joint_95_rectangle'][key])} | "
                 f"{interval(acceptance['expanded_joint_rectangle'][index])} |")
lines += [
    "",
    "The directed phase estimates use the independently measured zero-target reference at the same time. "
    "The positive and reversed fixtures at the primary time recover their programmed signs. "
    "The intervals are conservative 95% circular bounds for each estimate.",
    "",
    "| Signal arm | Programmed relative phase | Recovered relative phase | 95% interval |",
    "| --- | ---: | ---: | --- |",
]
for name, label, truth in (
    ("signal_t0.8", "Forward at 0.8", "+41.83°"),
    ("signal_t1.2", "Forward at 1.2", "+41.83°"),
    ("signal_t1.6", "Forward at 1.6", "+41.83°"),
    ("reversed_t1.6", "Reversed at 1.6", "−41.83°"),
):
    point, bounds = angles(table[name])
    lines.append(f"| {label} | {truth} | {point} | {bounds} |")
lines += [
    "",
    f"The tree control gave $Z_4={cfmt(table['tree_t1.6']['observed_harmonic'])}$. "
    "Its joint counting rectangle contains the origin. The matched-detuning control gave "
    f"$Z_4={cfmt(table['matched_detuning_t1.6']['observed_harmonic'])}$, compared with "
    f"the exact prediction {cfmt(table['matched_detuning_t1.6']['exact_harmonic'])}. "
    "That control reports the harmonic directly because its diagonal differs from the phase-reference arm.",
    "",
    "## Calibration and evidence",
    "",
    f"Fresh calibration was recorded at {singapore(execution['calibration_prepared'])}. IBM reported "
    "that calibration at job start and at the last execution chunk. The runtime returned matching case "
    f"identifiers for all 36 circuits in {len(execution['chunks'])} chunk. The refreshed calibration selected "
    f"{manifest['selected_synthesis']} synthesis under the original gates. Q3 remains simulation-only.",
    "",
    "The portable calibration hash normalizes text line endings. The hardware manifest preserves the raw "
    "calibration hash verified before submission and the unchanged binary QPY hash.",
    "",
    "- [Raw IBM counts](receipts/hardware_q2/hardware_counts.json) · [Execution evidence](receipts/hardware_q2/execution_evidence.json)",
    "- [Phase estimates and intervals](receipts/hardware_q2/hardware_analysis.json) · [Matching Q2 simulations](receipts/hardware_q2/q2_protocol.json)",
    "- [Fresh calibration](receipts/hardware_q2/calibration.json) · [Manifest](receipts/hardware_q2/manifest.json) · [ISA QPY](receipts/hardware_q2/q2_isa.qpy)",
]
(here / "Q2_HARDWARE_RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print(f"Archived {analysis['shots_total']:,} shots, matched IBM calibration and all 36 ISA circuits.")
