"""Reproducible empirical proof suite for the connector-calculus paper."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from math import sqrt
from pathlib import Path
from random import Random
from statistics import mean, stdev
from typing import Callable, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .algebra import NetworkState
from .bonding import (
    BondPolicy,
    RewardClaim,
    ServiceRecord,
    naive_identity_rewards,
    settle_bond,
    sybil_invariant_rewards,
)
from .simulator import (
    Demand,
    SimulationResult,
    candidate_paths,
    demand_stream,
    route_payment,
    run_simulation,
    summarize,
    two_cluster_state,
)


def _ci95(values: list[float]) -> float:
    return 0.0 if len(values) < 2 else 1.96 * stdev(values) / sqrt(len(values))


def _paired_delta(
    left: list[SimulationResult],
    right: list[SimulationResult],
    metric: Callable[[SimulationResult], float],
) -> dict[str, float]:
    deltas = [metric(b) - metric(a) for a, b in zip(left, right)]
    return {"mean": mean(deltas), "ci95_half_width": _ci95(deltas)}


def experiment_invariants(seed: int = 7, attempts: int = 600) -> dict[str, int | bool]:
    rng = Random(seed)
    state = two_cluster_state(seed)
    initial_capacity = state.total_capacity
    applied = rejected = 0
    nodes = sorted(state.nodes)
    for _ in range(attempts):
        source, target = rng.sample(nodes, 2)
        amount = rng.choice((500, 1_000, 2_000, 5_000))
        paths = candidate_paths(state, source, target, limit=4)
        feasible = next((path for path in paths if state.route_feasible(path, amount)), None)
        if feasible is None:
            rejected += 1
            continue
        state.apply_route(feasible, amount)
        state.assert_invariants()
        applied += 1
    return {
        "attempts": attempts,
        "applied": applied,
        "rejected": rejected,
        "capacity_conserved": state.total_capacity == initial_capacity,
        "channel_invariants_hold": True,
    }


def experiment_connectors(seeds: Iterable[int]) -> dict[str, object]:
    seeds = list(seeds)
    baseline = [run_simulation(seed, "baseline") for seed in seeds]
    random = [run_simulation(seed, "random_connector") for seed in seeds]
    ghost = [run_simulation(seed, "ghost_connector") for seed in seeds]
    return {
        "baseline": summarize(baseline),
        "random_connector": summarize(random),
        "ghost_connector": summarize(ghost),
        "paired_ghost_minus_baseline_success": _paired_delta(
            baseline, ghost, lambda row: row.success_rate
        ),
        "paired_ghost_minus_random_success": _paired_delta(
            random, ghost, lambda row: row.success_rate
        ),
        "rows": [asdict(row) | {"success_rate": row.success_rate, "volume_rate": row.volume_rate, "leakage_proxy": row.leakage_proxy} for row in baseline + random + ghost],
    }


def experiment_privacy_frontier(seeds: Iterable[int]) -> dict[str, object]:
    seeds = list(seeds)
    rows: dict[str, list[SimulationResult]] = {
        knowledge: [run_simulation(seed, "baseline", knowledge=knowledge) for seed in seeds]
        for knowledge in ("public", "adaptive", "oracle")
    }
    return {knowledge: summarize(results) for knowledge, results in rows.items()} | {
        "interpretation": "failed route attempts are used only as an information-leakage proxy"
    }


def experiment_jamming(seeds: Iterable[int]) -> dict[str, object]:
    seeds = list(seeds)
    baseline = [run_simulation(seed, "baseline", jam=True) for seed in seeds]
    connector = [run_simulation(seed, "ghost_connector", jam=True) for seed in seeds]
    return {
        "jammed_baseline": summarize(baseline),
        "jammed_ghost_connector": summarize(connector),
        "paired_success_delta": _paired_delta(baseline, connector, lambda row: row.success_rate),
        "scope": "synthetic lock model; no live-network attack traffic",
    }


def experiment_sybil(pool: int = 100_000) -> dict[str, object]:
    rows = []
    for identities in (1, 2, 4, 8, 16, 32):
        claims = [
            RewardClaim(f"sybil-{i}", "shared-utxo", 100_000, 0.9)
            for i in range(identities)
        ]
        invariant = sybil_invariant_rewards(claims, pool)
        naive = naive_identity_rewards(claims, pool)
        rows.append(
            {
                "identities": identities,
                "invariant_total": sum(invariant.values()),
                "naive_total": sum(naive.values()),
            }
        )
    return {
        "pool": pool,
        "rows": rows,
        "split_invariant": len({row["invariant_total"] for row in rows}) == 1,
    }


def experiment_bonding() -> dict[str, object]:
    policy = BondPolicy()
    honest = ServiceRecord("honest", "utxo-h", 25_000, 100, 98, 500_000, 470_000, 1)
    flaky = ServiceRecord("flaky", "utxo-f", 25_000, 100, 62, 500_000, 220_000, 12)
    return {
        "required_example": policy.required(120_000, 40_000, 0.30),
        "honest": asdict(settle_bond(honest, policy)),
        "flaky": asdict(settle_bond(flaky, policy)),
    }


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _plot_connectors(summary: dict[str, object], path: Path) -> None:
    labels = ["Baseline", "Random connector", "Ghost connector"]
    keys = ["baseline", "random_connector", "ghost_connector"]
    values = [summary[key]["success_rate_mean"] for key in keys]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    bars = ax.bar(labels, values, color=["#6b7280", "#60a5fa", "#0f766e"])
    ax.set_ylim(0, 1)
    ax.set_ylabel("Payment success rate")
    ax.set_title("Demand-cut connectors improve synthetic delivery")
    ax.grid(axis="y", alpha=0.25)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.02, f"{value:.3f}", ha="center")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _plot_privacy(summary: dict[str, object], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6.6, 4.4))
    colors = {"public": "#6b7280", "adaptive": "#d97706", "oracle": "#0f766e"}
    for key in ("public", "adaptive", "oracle"):
        row = summary[key]
        ax.scatter(row["leakage_proxy_mean"], row["success_rate_mean"], s=90, color=colors[key], label=key.title())
        ax.annotate(key.title(), (row["leakage_proxy_mean"], row["success_rate_mean"]), xytext=(6, 5), textcoords="offset points")
    ax.set_xlabel("Failed-attempt leakage proxy per demand")
    ax.set_ylabel("Payment success rate")
    ax.set_title("Routing knowledge exposes a privacy-efficiency frontier")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _plot_sybil(summary: dict[str, object], path: Path) -> None:
    rows = summary["rows"]
    x = [row["identities"] for row in rows]
    fig, ax = plt.subplots(figsize=(6.8, 4.3))
    ax.plot(x, [row["naive_total"] for row in rows], marker="o", label="Naive per identity", color="#b91c1c")
    ax.plot(x, [row["invariant_total"] for row in rows], marker="o", label="Capital-keyed pool", color="#0f766e")
    ax.set_xscale("log", base=2)
    ax.set_xlabel("Identities controlled by one capital source")
    ax.set_ylabel("Coalition reward (units)")
    ax.set_title("Identity splitting cannot enlarge the bonded reward pool")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def run_proof_suite(output_dir: str | Path = "output/experiments", seed_count: int = 24) -> dict[str, object]:
    output = Path(output_dir)
    figures = output / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    seeds = list(range(seed_count))
    connector = experiment_connectors(seeds)
    privacy = experiment_privacy_frontier(seeds)
    jamming = experiment_jamming(seeds)
    sybil = experiment_sybil()
    bonding = experiment_bonding()
    summary = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed_count": seed_count,
        "invariants": experiment_invariants(),
        "connectors": {key: value for key, value in connector.items() if key != "rows"},
        "privacy_frontier": privacy,
        "jamming": jamming,
        "sybil": sybil,
        "bonding": bonding,
        "limitations": [
            "synthetic topology rather than a live Lightning snapshot",
            "additive fee abstraction and no HTLC timing engine",
            "failed attempts are a leakage proxy, not deanonymization measurements",
            "no local zero-knowledge proving or transaction broadcast",
        ],
    }
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_csv(output / "connector_rows.csv", connector["rows"])
    _plot_connectors(connector, figures / "connector_success.png")
    _plot_privacy(privacy, figures / "privacy_frontier.png")
    _plot_sybil(sybil, figures / "sybil_rewards.png")
    proof_cards = [
        {
            "id": "P1",
            "claim": "payment rewrites conserve channel capacity",
            "evidence": summary["invariants"],
            "status": "supported" if summary["invariants"]["capacity_conserved"] else "failed",
        },
        {
            "id": "P2",
            "claim": "demand-cut ghost connectors improve delivery over the unmodified graph",
            "evidence": summary["connectors"]["paired_ghost_minus_baseline_success"],
            "status": "supported" if summary["connectors"]["paired_ghost_minus_baseline_success"]["mean"] > 0 else "not supported",
        },
        {
            "id": "P3",
            "claim": "capital-keyed rewards are invariant to identity splitting",
            "evidence": {"split_invariant": summary["sybil"]["split_invariant"]},
            "status": "supported" if summary["sybil"]["split_invariant"] else "failed",
        },
    ]
    (output / "proof_cards.json").write_text(json.dumps(proof_cards, indent=2), encoding="utf-8")

    config_path = Path("configs/proof_mechanics.json")
    config_bytes = config_path.read_bytes() if config_path.exists() else b"{}"
    receipt = {
        "schema_version": "1.0",
        "experiment_id": f"connector-calculus-synthetic-{seed_count}-seeds",
        "configuration_file": config_path.as_posix(),
        "configuration_hash": hashlib.sha256(config_bytes).hexdigest(),
        "result_file": summary_path.as_posix(),
        "result_hash": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "live_network": False,
        "zk_proof": False,
    }
    (output / "witness_receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return summary
