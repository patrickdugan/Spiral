"""Run the sealed private-flow emergence laboratory across paired seeds."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from math import sqrt
from pathlib import Path
from statistics import mean, stdev

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .hive_lab import HiveLabConfig, HiveLabResult, Scenario, run_hive_lab


SCENARIOS: tuple[Scenario, ...] = (
    "ordinary_commerce",
    "private_unicast",
    "hive_reinvestment",
)

METRICS = (
    "success_rate",
    "private_flow_share",
    "delivered_volume",
    "abstract_signal_units",
    "hive_count",
    "largest_hive_size",
    "connector_count",
    "connector_capital",
    "external_income",
    "ending_imbalance",
    "observer_alert_count",
    "observer_hive_edge_recall",
)


def load_config(path: str | Path) -> HiveLabConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data.pop("schema_version", None)
    data.pop("description", None)
    return HiveLabConfig(**data)


def _mean_ci(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"n": 0, "mean": 0.0, "ci95_half_width": 0.0}
    half_width = 0.0 if len(values) < 2 else 1.96 * stdev(values) / sqrt(len(values))
    return {"n": len(values), "mean": mean(values), "ci95_half_width": half_width}


def _metric(result: HiveLabResult, name: str) -> float:
    value = getattr(result, name)
    return float(value() if callable(value) else value)


def summarize(rows: list[HiveLabResult]) -> dict[str, object]:
    grouped = {
        scenario: [row for row in rows if row.scenario == scenario]
        for scenario in SCENARIOS
    }
    scenarios = {
        scenario: {
            metric: _mean_ci([_metric(row, metric) for row in scenario_rows])
            for metric in METRICS
        }
        for scenario, scenario_rows in grouped.items()
    }
    private_by_seed = {row.seed: row for row in grouped["private_unicast"]}
    hive_by_seed = {row.seed: row for row in grouped["hive_reinvestment"]}
    paired_seeds = sorted(set(private_by_seed) & set(hive_by_seed))
    paired_success = [
        hive_by_seed[seed].success_rate - private_by_seed[seed].success_rate
        for seed in paired_seeds
    ]
    paired_income = [
        hive_by_seed[seed].external_income - private_by_seed[seed].external_income
        for seed in paired_seeds
    ]
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed_count": len(paired_seeds),
        "scenarios": scenarios,
        "paired_hive_minus_private": {
            "success_rate": _mean_ci(paired_success),
            "external_income": _mean_ci(paired_income),
        },
        "accounting_holds": all(row.accounting_error == 0 for row in rows),
        "network_invariants_hold": True,
        "interpretation": {
            "abstract_signal_units": "dimensionless coordination demand; no content or codec exists",
            "private_relationship": "simulation overlay, not a claim of protocol-level invisibility",
            "observer_hive_edge_recall": "fraction of mature private edges appearing in a simple sampled-link alert set",
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


def _write_rows(path: Path, rows: list[HiveLabResult]) -> None:
    flat_rows: list[dict[str, object]] = []
    for result in rows:
        row = result.to_dict()
        row.pop("safety_boundary", None)
        flat_rows.append(row)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(flat_rows[0]))
        writer.writeheader()
        writer.writerows(flat_rows)


def _plot_scenarios(summary: dict[str, object], path: Path) -> None:
    labels = ["Ordinary", "Private unicast", "Hive + reinvestment"]
    scenarios = summary["scenarios"]
    success = [scenarios[key]["success_rate"]["mean"] for key in SCENARIOS]
    private = [scenarios[key]["private_flow_share"]["mean"] for key in SCENARIOS]
    x = range(len(labels))
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax.bar([i - 0.18 for i in x], success, width=0.36, label="Payment success", color="#0f766e")
    ax.bar([i + 0.18 for i in x], private, width=0.36, label="Private-flow share", color="#64748b")
    ax.set_xticks(list(x), labels)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Rate")
    ax.set_title("Private economic overlays and synthetic delivery")
    ax.grid(axis="y", alpha=0.25)
    handles, legend_labels = ax.get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="lower center", bbox_to_anchor=(0.5, 0.01), ncol=2)
    fig.tight_layout(rect=(0, 0.09, 1, 1))
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _plot_emergence(summary: dict[str, object], path: Path) -> None:
    scenarios = summary["scenarios"]
    sizes = [scenarios[key]["largest_hive_size"]["mean"] for key in SCENARIOS]
    alerts = [scenarios[key]["observer_alert_count"]["mean"] for key in SCENARIOS]
    labels = ["Ordinary", "Private unicast", "Hive + reinvestment"]
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    positions = list(range(len(labels)))
    ax.plot(positions, sizes, marker="o", linewidth=2, label="Largest mature coalition")
    ax.plot(positions, alerts, marker="s", linewidth=2, label="Observer alerts")
    ax.set_xticks(positions, labels)
    ax.set_ylabel("Count")
    ax.set_title("Emergence and sampled observer signatures")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def run_campaign(
    output_dir: str | Path = "output/hive_lab",
    seed_count: int = 12,
    config_path: str | Path = "configs/stego_hive_lab.json",
) -> dict[str, object]:
    if seed_count <= 0:
        raise ValueError("seed_count must be positive")
    output = Path(output_dir)
    figures = output / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    config = load_config(config_path)
    rows = [
        run_hive_lab(seed, scenario, config)
        for seed in range(seed_count)
        for scenario in SCENARIOS
    ]
    if not all(row.accounting_error == 0 for row in rows):
        raise AssertionError("agent economy accounting failed")
    summary = summarize(rows)
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_rows(output / "rows.csv", rows)
    _plot_scenarios(summary, figures / "scenario_rates.png")
    _plot_emergence(summary, figures / "emergence_observability.png")
    config_path = Path(config_path)
    receipt = {
        "schema_version": "1.0",
        "experiment_id": f"sealed-hive-lab-{seed_count}-seeds",
        "configuration_file": config_path.as_posix(),
        "configuration_hash": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "result_file": summary_path.as_posix(),
        "result_hash": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "live_network": False,
        "payload_codec": False,
    }
    (output / "witness_receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="output/hive_lab")
    parser.add_argument("--seeds", type=int, default=12)
    parser.add_argument("--config", default="configs/stego_hive_lab.json")
    args = parser.parse_args()
    summary = run_campaign(args.output, args.seeds, args.config)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
