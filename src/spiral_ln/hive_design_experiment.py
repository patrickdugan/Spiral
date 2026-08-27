"""Map coalition phase transitions and ablate learned hive design tropes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from math import sqrt
from pathlib import Path
from statistics import mean, stdev

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .hive_experiment import load_config
from .hive_lab import DesignTropes, HiveEconomyEnv, HiveLabConfig


TROPE_FIELDS = tuple(DesignTropes.__dataclass_fields__)


def _mean_ci(values: list[float]) -> dict[str, float | int]:
    half_width = 0.0 if len(values) < 2 else 1.96 * stdev(values) / sqrt(len(values))
    return {"n": len(values), "mean": mean(values) if values else 0.0, "ci95_half_width": half_width}


def _tropes(names: list[str]) -> DesignTropes:
    unknown = set(names) - set(TROPE_FIELDS)
    if unknown:
        raise ValueError(f"unknown design tropes: {sorted(unknown)}")
    values = {name: name in names for name in TROPE_FIELDS}
    # Observer sampling remains on unless a campaign explicitly names a fully
    # unobserved design; it is a measurement surface, not an agent advantage.
    if "partial_observer" not in names:
        values["partial_observer"] = True
    return DesignTropes(**values)


def _load_campaign(path: str | Path) -> dict[str, object]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def phase_sweep(
    base: HiveLabConfig,
    spec: dict[str, object],
) -> list[dict[str, object]]:
    seeds = range(int(spec["seed_count"]))
    repeats = [float(value) for value in spec["repeat_probabilities"]]
    thresholds = [float(value) for value in spec["reciprocity_thresholds"]]
    giant_size = max(2, int(base.agent_count * float(spec["giant_component_fraction"])))
    rows: list[dict[str, object]] = []
    for repeat_probability in repeats:
        for reciprocity_threshold in thresholds:
            config = replace(
                base,
                repeat_private_peer_probability=repeat_probability,
                hive_min_reciprocity=reciprocity_threshold,
            )
            for seed in seeds:
                result = HiveEconomyEnv("private_unicast", seed, config).run()
                rows.append(
                    {
                        "seed": seed,
                        "repeat_probability": repeat_probability,
                        "reciprocity_threshold": reciprocity_threshold,
                        "giant_component": int(result.largest_hive_size >= giant_size),
                        "largest_hive_size": result.largest_hive_size,
                        "hive_count": result.hive_count,
                        "success_rate": result.success_rate,
                        "private_flow_share": result.private_flow_share,
                        "observer_hive_edge_recall": result.observer_hive_edge_recall,
                        "accounting_error": result.accounting_error,
                    }
                )
    return rows


def ablation_campaign(
    base: HiveLabConfig,
    seed_count: int,
    designs: dict[str, list[str]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for design_name, enabled_names in designs.items():
        tropes = _tropes(enabled_names)
        scenario = "ordinary_commerce" if not tropes.private_relationships else "hive_reinvestment"
        for seed in range(seed_count):
            result = HiveEconomyEnv(scenario, seed, base, tropes=tropes).run()
            rows.append(
                {
                    "design": design_name,
                    "seed": seed,
                    "enabled_tropes": ";".join(tropes.enabled()),
                    "success_rate": result.success_rate,
                    "private_flow_share": result.private_flow_share,
                    "largest_hive_size": result.largest_hive_size,
                    "hive_count": result.hive_count,
                    "connector_count": result.connector_count,
                    "connector_capital": result.connector_capital,
                    "external_income": result.external_income,
                    "ending_imbalance": result.ending_imbalance,
                    "observer_alert_count": result.observer_alert_count,
                    "observer_hive_edge_recall": result.observer_hive_edge_recall,
                    "accounting_error": result.accounting_error,
                }
            )
    return rows


def summarize(
    phase_rows: list[dict[str, object]],
    ablation_rows: list[dict[str, object]],
    campaign: dict[str, object],
) -> dict[str, object]:
    phase_cells = []
    coordinates = sorted(
        {(row["repeat_probability"], row["reciprocity_threshold"]) for row in phase_rows}
    )
    for repeat_probability, reciprocity_threshold in coordinates:
        cell = [
            row
            for row in phase_rows
            if row["repeat_probability"] == repeat_probability
            and row["reciprocity_threshold"] == reciprocity_threshold
        ]
        phase_cells.append(
            {
                "repeat_probability": repeat_probability,
                "reciprocity_threshold": reciprocity_threshold,
                "giant_component_probability": mean(row["giant_component"] for row in cell),
                "largest_hive_size": _mean_ci([float(row["largest_hive_size"]) for row in cell]),
                "success_rate": _mean_ci([float(row["success_rate"]) for row in cell]),
                "observer_hive_edge_recall": _mean_ci(
                    [float(row["observer_hive_edge_recall"]) for row in cell]
                ),
            }
        )

    designs = list(campaign["ablations"])
    ablations = {}
    for design in designs:
        rows = [row for row in ablation_rows if row["design"] == design]
        ablations[design] = {
            "enabled_tropes": rows[0]["enabled_tropes"].split(";") if rows else [],
            "success_rate": _mean_ci([float(row["success_rate"]) for row in rows]),
            "private_flow_share": _mean_ci([float(row["private_flow_share"]) for row in rows]),
            "largest_hive_size": _mean_ci([float(row["largest_hive_size"]) for row in rows]),
            "connector_count": _mean_ci([float(row["connector_count"]) for row in rows]),
            "external_income": _mean_ci([float(row["external_income"]) for row in rows]),
            "ending_imbalance": _mean_ci([float(row["ending_imbalance"]) for row in rows]),
            "observer_hive_edge_recall": _mean_ci(
                [float(row["observer_hive_edge_recall"]) for row in rows]
            ),
        }

    signaling_pair = []
    without = {row["seed"]: row for row in ablation_rows if row["design"] == "repeat_and_trust"}
    with_signal = {row["seed"]: row for row in ablation_rows if row["design"] == "abstract_signaling"}
    for seed in sorted(set(without) & set(with_signal)):
        signaling_pair.append(
            float(with_signal[seed]["success_rate"]) - float(without[seed]["success_rate"])
        )

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase_transition": {
            "giant_component_definition": campaign["phase_sweep"]["giant_component_fraction"],
            "cells": phase_cells,
        },
        "ablations": ablations,
        "paired_signaling_only_success_delta": _mean_ci(signaling_pair),
        "accounting_holds": all(int(row["accounting_error"]) == 0 for row in phase_rows + ablation_rows),
        "interpretation": {
            "trope": "one switchable environment mechanism, not a claim about real agent behavior",
            "phase_transition": "parameter region where a component reaches the configured share of agents",
            "signaling_only_delta": "control expected to be zero because signal units have no economic semantics",
        },
        "safety_boundary": {
            "synthetic_only": True,
            "live_network": False,
            "payload_codec": False,
            "wallet_or_node_connection": False,
            "network_transport": False,
            "transaction_broadcast": False,
        },
    }


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _plot_phase(summary: dict[str, object], path: Path) -> None:
    cells = summary["phase_transition"]["cells"]
    repeats = sorted({cell["repeat_probability"] for cell in cells})
    thresholds = sorted({cell["reciprocity_threshold"] for cell in cells})
    matrix = np.zeros((len(thresholds), len(repeats)))
    for cell in cells:
        row = thresholds.index(cell["reciprocity_threshold"])
        column = repeats.index(cell["repeat_probability"])
        matrix[row, column] = cell["giant_component_probability"]
    fig, ax = plt.subplots(figsize=(7.2, 5.2))
    image = ax.imshow(matrix, origin="lower", vmin=0, vmax=1, cmap="YlGnBu", aspect="auto")
    ax.set_xticks(range(len(repeats)), [f"{value:.2f}" for value in repeats])
    ax.set_yticks(range(len(thresholds)), [f"{value:.2f}" for value in thresholds])
    ax.set_xlabel("Repeat-private-peer probability")
    ax.set_ylabel("Minimum directional reciprocity")
    ax.set_title("Probability of a giant private economic component")
    for row in range(len(thresholds)):
        for column in range(len(repeats)):
            value = matrix[row, column]
            ax.text(column, row, f"{value:.1f}", ha="center", va="center", color="white" if value > 0.55 else "black")
    fig.colorbar(image, ax=ax, label="Emergence probability")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _plot_ablation(summary: dict[str, object], path: Path) -> None:
    ablations = summary["ablations"]
    labels = list(ablations)
    success = [ablations[label]["success_rate"]["mean"] for label in labels]
    hive_fraction = [ablations[label]["largest_hive_size"]["mean"] / 16 for label in labels]
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    ax.bar(x - 0.18, success, width=0.36, label="Payment success", color="#0f766e")
    ax.bar(x + 0.18, hive_fraction, width=0.36, label="Largest coalition share", color="#7c3aed")
    ax.set_xticks(x, [label.replace("_", "\n") for label in labels])
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Rate or population share")
    ax.set_title("Ablating the learned environment tropes")
    ax.grid(axis="y", alpha=0.25)
    handles, legend_labels = ax.get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="lower center", bbox_to_anchor=(0.5, 0.01), ncol=2)
    fig.tight_layout(rect=(0, 0.10, 1, 1))
    fig.savefig(path, dpi=180)
    plt.close(fig)


def run_design_campaign(
    output_dir: str | Path = "output/hive_design",
    base_config_path: str | Path = "configs/stego_hive_lab.json",
    campaign_path: str | Path = "configs/hive_design_campaign.json",
) -> dict[str, object]:
    output = Path(output_dir)
    figures = output / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    base = load_config(base_config_path)
    campaign = _load_campaign(campaign_path)
    phase_rows = phase_sweep(base, campaign["phase_sweep"])
    ablation_rows = ablation_campaign(
        base,
        int(campaign["ablation_seed_count"]),
        campaign["ablations"],
    )
    summary = summarize(phase_rows, ablation_rows, campaign)
    if not summary["accounting_holds"]:
        raise AssertionError("design campaign accounting failed")
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_csv(output / "phase_rows.csv", phase_rows)
    _write_csv(output / "ablation_rows.csv", ablation_rows)
    _plot_phase(summary, figures / "phase_transition.png")
    _plot_ablation(summary, figures / "trope_ablation.png")

    base_path = Path(base_config_path)
    design_path = Path(campaign_path)
    combined_config = base_path.read_bytes() + b"\n" + design_path.read_bytes()
    receipt = {
        "schema_version": "1.0",
        "experiment_id": "sealed-hive-design-phase-and-ablation",
        "configuration_files": [base_path.as_posix(), design_path.as_posix()],
        "configuration_hash": hashlib.sha256(combined_config).hexdigest(),
        "result_file": summary_path.as_posix(),
        "result_hash": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "live_network": False,
        "payload_codec": False,
    }
    (output / "witness_receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="output/hive_design")
    parser.add_argument("--base-config", default="configs/stego_hive_lab.json")
    parser.add_argument("--campaign", default="configs/hive_design_campaign.json")
    args = parser.parse_args()
    summary = run_design_campaign(args.output, args.base_config, args.campaign)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
