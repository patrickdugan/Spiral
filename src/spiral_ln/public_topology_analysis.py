"""Cluster-robust analysis across sealed public-topology replications."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from math import sqrt
from pathlib import Path
from statistics import mean, stdev

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


T_975 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}


CONTRASTS = {
    "retry_minus_public_success": (("retry", "none"), ("public", "none"), "evaluation_success_rate", None),
    "online_minus_retry_success": (("online", "none"), ("retry", "none"), "evaluation_success_rate", None),
    "online_minus_retry_leakage": (("online", "none"), ("retry", "none"), "evaluation_leakage_proxy", None),
    "oracle_minus_online_success": (("oracle", "none"), ("online", "none"), "evaluation_success_rate", None),
    "failure_capital_minus_random_success": (
        ("online", "failure_aware"),
        ("online", "random"),
        "evaluation_success_rate",
        None,
    ),
    "failure_capital_diffuse": (
        ("online", "failure_aware"),
        ("online", "random"),
        "evaluation_success_rate",
        "diffuse",
    ),
    "failure_capital_stationary": (
        ("online", "failure_aware"),
        ("online", "random"),
        "evaluation_success_rate",
        "stationary_hotspot",
    ),
    "failure_capital_shifted": (
        ("online", "failure_aware"),
        ("online", "random"),
        "evaluation_success_rate",
        "shifted_hotspot",
    ),
}


def load_rows(path: str | Path, campaign: str) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        rows = [dict(row, campaign=campaign) for row in csv.DictReader(handle)]
    return [row for row in rows if row["evaluation_split"] == "sealed_holdout"]


def _atomic_key(row: dict[str, str]) -> tuple[str, ...]:
    return (
        row["campaign"],
        row["topology_sample_id"],
        row["balance_draw"],
        row["balance_model"],
        row["demand_regime"],
    )


def _condition(rows: list[dict[str, str]], routing: str, capital: str, regime: str | None) -> dict[tuple[str, ...], dict[str, str]]:
    return {
        _atomic_key(row): row
        for row in rows
        if row["routing_policy"] == routing
        and row["capital_policy"] == capital
        and (regime is None or row["demand_regime"] == regime)
    }


def atomic_differences(
    rows: list[dict[str, str]],
    left: tuple[str, str],
    right: tuple[str, str],
    metric: str,
    regime: str | None = None,
) -> list[tuple[str, str, float]]:
    left_rows = _condition(rows, *left, regime)
    right_rows = _condition(rows, *right, regime)
    keys = sorted(set(left_rows) & set(right_rows))
    return [
        (key[0], key[1], float(left_rows[key][metric]) - float(right_rows[key][metric]))
        for key in keys
    ]


def temporal_differences(rows: list[dict[str, str]]) -> list[tuple[str, str, float]]:
    left_rows = _condition(rows, "online", "none", "shifted_hotspot")
    right_rows = _condition(rows, "retry", "none", "shifted_hotspot")
    keys = sorted(set(left_rows) & set(right_rows))
    values = []
    for key in keys:
        left_change = float(left_rows[key]["late_evaluation_success_rate"]) - float(
            left_rows[key]["early_evaluation_success_rate"]
        )
        right_change = float(right_rows[key]["late_evaluation_success_rate"]) - float(
            right_rows[key]["early_evaluation_success_rate"]
        )
        values.append((key[0], key[1], left_change - right_change))
    return values


def cluster_interval(values: list[tuple[str, str, float]]) -> dict[str, object]:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for campaign, topology, value in values:
        grouped[(campaign, topology)].append(value)
    cluster_means = [mean(grouped[key]) for key in sorted(grouped)]
    n = len(cluster_means)
    center = mean(cluster_means) if cluster_means else 0.0
    critical = T_975[min(n - 1, 30)] if n >= 2 else 0.0
    half_width = critical * stdev(cluster_means) / sqrt(n) if n >= 2 else 0.0
    return {
        "cluster_n": n,
        "atomic_n": len(values),
        "mean": center,
        "ci95_half_width": half_width,
        "ci95_lower": center - half_width,
        "ci95_upper": center + half_width,
        "cluster_means": cluster_means,
    }


def _campaign_breakdown(values: list[tuple[str, str, float]]) -> dict[str, dict[str, object]]:
    campaigns = sorted({campaign for campaign, _, _ in values})
    return {
        campaign: cluster_interval([item for item in values if item[0] == campaign])
        for campaign in campaigns
    }


def analyze(rows: list[dict[str, str]]) -> dict[str, object]:
    results: dict[str, object] = {}
    for name, (left, right, metric, regime) in CONTRASTS.items():
        values = atomic_differences(rows, left, right, metric, regime)
        results[name] = {
            "left": "|".join(left),
            "right": "|".join(right),
            "metric": metric,
            "demand_regime": regime or "all",
            "combined": cluster_interval(values),
            "by_campaign": _campaign_breakdown(values),
        }
    temporal = temporal_differences(rows)
    results["online_shift_temporal_advantage_over_retry"] = {
        "metric": "(online late-early) - (retry late-early)",
        "demand_regime": "shifted_hotspot",
        "combined": cluster_interval(temporal),
        "by_campaign": _campaign_breakdown(temporal),
    }
    for mode in ("hub", "random", "periphery"):
        mode_rows = [row for row in rows if row["topology_mode"] == mode]
        values = atomic_differences(
            mode_rows,
            ("online", "failure_aware"),
            ("online", "random"),
            "evaluation_success_rate",
            "shifted_hotspot",
        )
        results[f"failure_capital_shifted_{mode}"] = {
            "left": "online|failure_aware",
            "right": "online|random",
            "metric": "evaluation_success_rate",
            "demand_regime": "shifted_hotspot",
            "topology_mode": mode,
            "combined": cluster_interval(values),
            "by_campaign": _campaign_breakdown(values),
        }
    combined = {name: result["combined"] for name, result in results.items()}
    equivalence_bound = 0.01
    oracle_rows = _condition(rows, "oracle", "none", None).values()
    checks = {
        "retry_beats_public": combined["retry_minus_public_success"]["ci95_lower"] > 0,
        "online_increment_below_one_pp": combined["online_minus_retry_success"]["ci95_upper"] < equivalence_bound,
        "oracle_beats_online": combined["oracle_minus_online_success"]["ci95_lower"] > 0,
        "oracle_has_zero_failed_probe_leakage": all(float(row["evaluation_leakage_proxy"]) == 0 for row in oracle_rows),
        "stationary_capital_beats_random": combined["failure_capital_stationary"]["ci95_lower"] > 0,
        "diffuse_capital_within_one_pp": max(
            abs(combined["failure_capital_diffuse"]["ci95_lower"]),
            abs(combined["failure_capital_diffuse"]["ci95_upper"]),
        ) < equivalence_bound,
        "shifted_capital_within_one_pp": max(
            abs(combined["failure_capital_shifted"]["ci95_lower"]),
            abs(combined["failure_capital_shifted"]["ci95_upper"]),
        ) < equivalence_bound,
        "positive_online_shift_adaptation": combined["online_shift_temporal_advantage_over_retry"]["ci95_lower"] > 0,
    }
    return {
        "schema_version": "1.0",
        "inference_unit": "sampled public-topology cluster",
        "confidence_interval": "two-sided 95% Student-t interval over topology-cluster means",
        "practical_equivalence_bound": equivalence_bound,
        "contrasts": results,
        "hypothesis_checks": checks,
    }


def plot_forest(summary: dict[str, object], path: str | Path) -> None:
    names = [
        "retry_minus_public_success",
        "online_minus_retry_success",
        "oracle_minus_online_success",
        "failure_capital_diffuse",
        "failure_capital_stationary",
        "failure_capital_shifted",
        "online_shift_temporal_advantage_over_retry",
        "failure_capital_shifted_hub",
        "failure_capital_shifted_random",
        "failure_capital_shifted_periphery",
    ]
    labels = [
        "Retry - public",
        "Online - retry",
        "Oracle - online",
        "Capital: diffuse",
        "Capital: stationary",
        "Capital: shifted",
        "Online shift adaptation - retry",
        "Shifted capital: hub",
        "Shifted capital: random",
        "Shifted capital: periphery",
    ]
    cells = [summary["contrasts"][name]["combined"] for name in names]
    means = [100 * cell["mean"] for cell in cells]
    errors = [100 * cell["ci95_half_width"] for cell in cells]
    y = list(range(len(names)))
    figure, axis = plt.subplots(figsize=(8.5, 6.4))
    axis.axvline(0, color="#4b5563", linewidth=1)
    axis.axvspan(-1, 1, color="#e5e7eb", alpha=0.65, label="±1 pp practical bound")
    axis.errorbar(means, y, xerr=errors, fmt="o", color="#0f766e", capsize=4)
    axis.set_yticks(y, labels)
    axis.invert_yaxis()
    axis.set_xlabel("Paired success-rate difference (percentage points)")
    axis.set_title("Combined sealed holdouts; topology-cluster Student-t intervals")
    axis.grid(axis="x", alpha=0.25)
    axis.legend(loc="lower right")
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def run_analysis(campaign_paths: dict[str, str | Path], output_dir: str | Path) -> dict[str, object]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    rows = [row for campaign, path in campaign_paths.items() for row in load_rows(path, campaign)]
    summary = analyze(rows)
    summary["campaigns"] = {
        campaign: {
            "rows_file": Path(path).as_posix(),
            "rows_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        }
        for campaign, path in campaign_paths.items()
    }
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    plot_forest(summary, output / "cluster_forest.png")
    receipt = {
        "schema_version": "1.0",
        "analysis_file": "src/spiral_ln/public_topology_analysis.py",
        "analysis_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "result_file": summary_path.as_posix(),
        "result_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
    }
    (output / "witness_receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", action="append", required=True, help="LABEL=ROWS.csv")
    parser.add_argument("--output", default="output/public_topology_combined")
    args = parser.parse_args()
    campaigns = dict(item.split("=", 1) for item in args.campaign)
    print(json.dumps(run_analysis(campaigns, args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
