"""Paired evaluation of bounded agent-control capabilities on synthetic Lightning state.

The campaign separates routing information, capital-placement policy, and
liquidity stress. It operates only on the in-memory connector calculus and has
no wallet, node, invoice, payload, transport, or transaction capability.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import sqrt
from pathlib import Path
from random import Random
from statistics import mean, stdev
from typing import Literal

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .algebra import Connector, ConnectorKind, NetworkState, apply_connector
from .simulator import Demand, Knowledge, demand_stream, jam_high_betweenness, route_payment, two_cluster_state


ConnectorPolicy = Literal["none", "random", "demand_aware"]
Stress = Literal["normal", "jammed"]
KNOWLEDGE_LEVELS: tuple[Knowledge, ...] = ("public", "adaptive", "oracle")
CONNECTOR_POLICIES: tuple[ConnectorPolicy, ...] = ("none", "random", "demand_aware")
STRESS_LEVELS: tuple[Stress, ...] = ("normal", "jammed")


@dataclass(frozen=True)
class AgentCapabilityConfig:
    seed_count: int = 30
    steps: int = 360
    warmup_steps: int = 90
    stress_start: int = 180
    connector_capital: int = 120_000
    connector_bond_fraction: float = 0.20
    jam_fraction: float = 0.90

    def __post_init__(self) -> None:
        if self.seed_count <= 0 or self.steps <= 0:
            raise ValueError("seed_count and steps must be positive")
        if not 0 < self.warmup_steps < self.stress_start < self.steps:
            raise ValueError("require 0 < warmup_steps < stress_start < steps")
        if self.connector_capital <= 0:
            raise ValueError("connector_capital must be positive")
        if not 0 <= self.connector_bond_fraction <= 1:
            raise ValueError("connector_bond_fraction must lie in [0, 1]")
        if not 0 <= self.jam_fraction <= 1:
            raise ValueError("jam_fraction must lie in [0, 1]")


@dataclass(frozen=True)
class SegmentResult:
    attempted: int
    succeeded: int
    attempted_volume: int
    delivered_volume: int
    failed_route_attempts: int

    @property
    def success_rate(self) -> float:
        return self.succeeded / max(1, self.attempted)

    @property
    def volume_rate(self) -> float:
        return self.delivered_volume / max(1, self.attempted_volume)

    @property
    def leakage_proxy(self) -> float:
        return self.failed_route_attempts / max(1, self.attempted)


@dataclass(frozen=True)
class CapabilityRow:
    seed: int
    knowledge: str
    connector_policy: str
    stress: str
    connector_deployed: bool
    connector_endpoints: str
    connector_capital: int
    jammed_edges: str
    warmup: SegmentResult
    pre_stress: SegmentResult
    post_stress: SegmentResult
    total: SegmentResult
    fee_msat: int
    imbalance_start: float
    imbalance_at_stress: float
    imbalance_end: float
    capacity_end: int

    def flat_dict(self) -> dict[str, object]:
        row: dict[str, object] = {
            "seed": self.seed,
            "knowledge": self.knowledge,
            "connector_policy": self.connector_policy,
            "stress": self.stress,
            "connector_deployed": self.connector_deployed,
            "connector_endpoints": self.connector_endpoints,
            "connector_capital": self.connector_capital,
            "jammed_edges": self.jammed_edges,
            "fee_msat": self.fee_msat,
            "imbalance_start": self.imbalance_start,
            "imbalance_at_stress": self.imbalance_at_stress,
            "imbalance_end": self.imbalance_end,
            "capacity_end": self.capacity_end,
        }
        for name in ("warmup", "pre_stress", "post_stress", "total"):
            segment = getattr(self, name)
            for field_name, value in asdict(segment).items():
                row[f"{name}_{field_name}"] = value
            row[f"{name}_success_rate"] = segment.success_rate
            row[f"{name}_volume_rate"] = segment.volume_rate
            row[f"{name}_leakage_proxy"] = segment.leakage_proxy
        return row


@dataclass
class _MutableSegment:
    attempted: int = 0
    succeeded: int = 0
    attempted_volume: int = 0
    delivered_volume: int = 0
    failed_route_attempts: int = 0

    def observe(self, demand: Demand, delivered: bool, failures: int) -> None:
        self.attempted += 1
        self.attempted_volume += demand.amount
        self.failed_route_attempts += failures
        if delivered:
            self.succeeded += 1
            self.delivered_volume += demand.amount

    def freeze(self) -> SegmentResult:
        return SegmentResult(**asdict(self))


def load_config(path: str | Path) -> AgentCapabilityConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data.pop("schema_version", None)
    data.pop("description", None)
    return AgentCapabilityConfig(**data)


def _cross_pairs(state: NetworkState) -> list[tuple[str, str]]:
    left = sorted(node for node in state.nodes if node.startswith("A"))
    right = sorted(node for node in state.nodes if node.startswith("B"))
    return [
        (a, b)
        for a in left
        for b in right
        if frozenset((a, b)) not in state.channels
    ]


def choose_observed_demand_connector(
    state: NetworkState,
    observed_demands: list[Demand],
    amount: int,
    bond_fraction: float = 0.20,
) -> Connector:
    """Choose placement from past demand endpoints only, without balance access."""

    available = set(_cross_pairs(state))
    counts = Counter(
        (demand.source, demand.target)
        if demand.source.startswith("A")
        else (demand.target, demand.source)
        for demand in observed_demands
        if demand.source[0] != demand.target[0]
    )
    ranked = sorted(available, key=lambda pair: (counts[pair], pair), reverse=True)
    if not ranked:
        raise ValueError("no cross-cluster connector placement is available")
    endpoints = ranked[0]
    return Connector(
        connector_id="capability:demand-aware",
        kind=ConnectorKind.TOPOLOGICAL,
        endpoints=endpoints,
        amount=amount,
        bond=max(1, int(amount * bond_fraction)),
        capital_id="sealed-capital:demand-aware",
    )


def choose_equal_budget_random_connector(
    state: NetworkState,
    seed: int,
    amount: int,
    bond_fraction: float = 0.20,
) -> Connector:
    candidates = _cross_pairs(state)
    if not candidates:
        raise ValueError("no cross-cluster connector placement is available")
    endpoints = Random(seed + 92_000).choice(candidates)
    return Connector(
        connector_id="capability:random",
        kind=ConnectorKind.TOPOLOGICAL,
        endpoints=endpoints,
        amount=amount,
        bond=max(1, int(amount * bond_fraction)),
        capital_id="sealed-capital:random",
    )


def run_episode(
    seed: int,
    knowledge: Knowledge,
    connector_policy: ConnectorPolicy,
    stress: Stress,
    config: AgentCapabilityConfig,
) -> CapabilityRow:
    if knowledge not in KNOWLEDGE_LEVELS:
        raise ValueError(f"unknown knowledge level: {knowledge}")
    if connector_policy not in CONNECTOR_POLICIES:
        raise ValueError(f"unknown connector policy: {connector_policy}")
    if stress not in STRESS_LEVELS:
        raise ValueError(f"unknown stress level: {stress}")

    state = two_cluster_state(seed)
    demands = demand_stream(seed, config.steps)
    segments = {
        "warmup": _MutableSegment(),
        "pre_stress": _MutableSegment(),
        "post_stress": _MutableSegment(),
        "total": _MutableSegment(),
    }
    imbalance_start = state.imbalance_energy()
    imbalance_at_stress = imbalance_start
    connector: Connector | None = None
    jammed_edges: list[tuple[str, str]] = []
    fees = 0

    for index, demand in enumerate(demands):
        if index == config.warmup_steps and connector_policy != "none":
            if connector_policy == "random":
                connector = choose_equal_budget_random_connector(
                    state,
                    seed,
                    config.connector_capital,
                    config.connector_bond_fraction,
                )
            else:
                connector = choose_observed_demand_connector(
                    state,
                    demands[: config.warmup_steps],
                    config.connector_capital,
                    config.connector_bond_fraction,
                )
            apply_connector(state, connector)
        if index == config.stress_start:
            imbalance_at_stress = state.imbalance_energy()
            if stress == "jammed":
                jammed_edges = jam_high_betweenness(state, config.jam_fraction)

        delivered, fee, failures = route_payment(state, demand, knowledge)
        fees += fee
        segment_name = (
            "warmup"
            if index < config.warmup_steps
            else "pre_stress"
            if index < config.stress_start
            else "post_stress"
        )
        segments[segment_name].observe(demand, delivered, failures)
        segments["total"].observe(demand, delivered, failures)

    state.assert_invariants()
    return CapabilityRow(
        seed=seed,
        knowledge=knowledge,
        connector_policy=connector_policy,
        stress=stress,
        connector_deployed=connector is not None,
        connector_endpoints="" if connector is None else "|".join(connector.endpoints[:2]),
        connector_capital=0 if connector is None else connector.amount,
        jammed_edges=";".join("|".join(edge) for edge in jammed_edges),
        warmup=segments["warmup"].freeze(),
        pre_stress=segments["pre_stress"].freeze(),
        post_stress=segments["post_stress"].freeze(),
        total=segments["total"].freeze(),
        fee_msat=fees,
        imbalance_start=imbalance_start,
        imbalance_at_stress=imbalance_at_stress,
        imbalance_end=state.imbalance_energy(),
        capacity_end=state.total_capacity,
    )


def _mean_ci(values: list[float]) -> dict[str, float | int]:
    half_width = 0.0 if len(values) < 2 else 1.96 * stdev(values) / sqrt(len(values))
    return {"n": len(values), "mean": mean(values) if values else 0.0, "ci95_half_width": half_width}


def _metric(row: CapabilityRow, name: str) -> float:
    lookup = {
        "total_success_rate": row.total.success_rate,
        "total_volume_rate": row.total.volume_rate,
        "total_leakage_proxy": row.total.leakage_proxy,
        "post_stress_success_rate": row.post_stress.success_rate,
        "post_stress_volume_rate": row.post_stress.volume_rate,
        "post_stress_leakage_proxy": row.post_stress.leakage_proxy,
        "delivered_volume": float(row.total.delivered_volume),
        "fee_per_delivered_sat": row.fee_msat / max(1, row.total.delivered_volume),
        "imbalance_end": row.imbalance_end,
    }
    return float(lookup[name])


def _paired_contrast(
    rows: list[CapabilityRow],
    left: tuple[str, str, str],
    right: tuple[str, str, str],
    metric: str,
) -> dict[str, object]:
    def selected(key: tuple[str, str, str]) -> dict[int, CapabilityRow]:
        knowledge, connector_policy, stress = key
        return {
            row.seed: row
            for row in rows
            if (row.knowledge, row.connector_policy, row.stress)
            == (knowledge, connector_policy, stress)
        }

    left_rows = selected(left)
    right_rows = selected(right)
    seeds = sorted(set(left_rows) & set(right_rows))
    differences = [
        _metric(left_rows[seed], metric) - _metric(right_rows[seed], metric)
        for seed in seeds
    ]
    return {
        "left": "|".join(left),
        "right": "|".join(right),
        "metric": metric,
        "left_minus_right": _mean_ci(differences),
    }


def _paired_interaction(
    rows: list[CapabilityRow],
    treatment_left: tuple[str, str, str],
    treatment_right: tuple[str, str, str],
    control_left: tuple[str, str, str],
    control_right: tuple[str, str, str],
    metric: str,
) -> dict[str, object]:
    keys = (treatment_left, treatment_right, control_left, control_right)
    selected = [
        {
            row.seed: row
            for row in rows
            if (row.knowledge, row.connector_policy, row.stress) == key
        }
        for key in keys
    ]
    seeds = sorted(set.intersection(*(set(group) for group in selected)))
    differences = [
        (_metric(selected[0][seed], metric) - _metric(selected[1][seed], metric))
        - (_metric(selected[2][seed], metric) - _metric(selected[3][seed], metric))
        for seed in seeds
    ]
    return {
        "treatment_difference": f"{'|'.join(treatment_left)} minus {'|'.join(treatment_right)}",
        "control_difference": f"{'|'.join(control_left)} minus {'|'.join(control_right)}",
        "metric": metric,
        "difference_in_differences": _mean_ci(differences),
    }


def summarize(rows: list[CapabilityRow], config: AgentCapabilityConfig) -> dict[str, object]:
    metrics = (
        "total_success_rate",
        "total_volume_rate",
        "total_leakage_proxy",
        "post_stress_success_rate",
        "post_stress_volume_rate",
        "post_stress_leakage_proxy",
        "delivered_volume",
        "fee_per_delivered_sat",
        "imbalance_end",
    )
    cells: dict[str, object] = {}
    for knowledge in KNOWLEDGE_LEVELS:
        for connector_policy in CONNECTOR_POLICIES:
            for stress in STRESS_LEVELS:
                subset = [
                    row
                    for row in rows
                    if (row.knowledge, row.connector_policy, row.stress)
                    == (knowledge, connector_policy, stress)
                ]
                cells["|".join((knowledge, connector_policy, stress))] = {
                    metric: _mean_ci([_metric(row, metric) for row in subset])
                    for metric in metrics
                }

    contrasts = {}
    for stress in STRESS_LEVELS:
        contrasts[f"adaptive_minus_public_no_connector_{stress}"] = _paired_contrast(
            rows,
            ("adaptive", "none", stress),
            ("public", "none", stress),
            "post_stress_success_rate",
        )
        contrasts[f"oracle_minus_adaptive_leakage_{stress}"] = _paired_contrast(
            rows,
            ("oracle", "none", stress),
            ("adaptive", "none", stress),
            "post_stress_leakage_proxy",
        )
        contrasts[f"demand_minus_random_equal_capital_{stress}"] = _paired_contrast(
            rows,
            ("adaptive", "demand_aware", stress),
            ("adaptive", "random", stress),
            "post_stress_success_rate",
        )
        contrasts[f"demand_minus_random_fee_efficiency_{stress}"] = _paired_contrast(
            rows,
            ("adaptive", "demand_aware", stress),
            ("adaptive", "random", stress),
            "fee_per_delivered_sat",
        )
        contrasts[f"demand_capital_minus_none_{stress}"] = _paired_contrast(
            rows,
            ("adaptive", "demand_aware", stress),
            ("adaptive", "none", stress),
            "post_stress_success_rate",
        )
        contrasts[f"random_capital_minus_none_{stress}"] = _paired_contrast(
            rows,
            ("adaptive", "random", stress),
            ("adaptive", "none", stress),
            "post_stress_success_rate",
        )
        contrasts[f"demand_capital_imbalance_minus_none_{stress}"] = _paired_contrast(
            rows,
            ("adaptive", "demand_aware", stress),
            ("adaptive", "none", stress),
            "imbalance_end",
        )
    contrasts["jam_penalty_adaptive_demand"] = _paired_contrast(
        rows,
        ("adaptive", "demand_aware", "jammed"),
        ("adaptive", "demand_aware", "normal"),
        "post_stress_success_rate",
    )
    contrasts["oracle_minus_adaptive_success_normal"] = _paired_contrast(
        rows,
        ("oracle", "none", "normal"),
        ("adaptive", "none", "normal"),
        "post_stress_success_rate",
    )
    contrasts["oracle_minus_adaptive_success_jammed"] = _paired_contrast(
        rows,
        ("oracle", "none", "jammed"),
        ("adaptive", "none", "jammed"),
        "post_stress_success_rate",
    )
    contrasts["information_capital_complement_under_jam"] = _paired_interaction(
        rows,
        ("adaptive", "demand_aware", "jammed"),
        ("public", "demand_aware", "jammed"),
        ("adaptive", "none", "jammed"),
        ("public", "none", "jammed"),
        "post_stress_success_rate",
    )
    contrasts["capital_reduction_in_jam_penalty"] = _paired_interaction(
        rows,
        ("adaptive", "demand_aware", "jammed"),
        ("adaptive", "demand_aware", "normal"),
        ("adaptive", "none", "jammed"),
        ("adaptive", "none", "normal"),
        "post_stress_success_rate",
    )

    equal_capital = all(
        row.connector_capital == config.connector_capital
        for row in rows
        if row.connector_policy in {"random", "demand_aware"}
    )
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "design": {
            "paired_seed_count": config.seed_count,
            "knowledge_levels": list(KNOWLEDGE_LEVELS),
            "connector_policies": list(CONNECTOR_POLICIES),
            "stress_levels": list(STRESS_LEVELS),
            "warmup_steps": config.warmup_steps,
            "stress_start": config.stress_start,
            "future_demand_visible_to_planner": False,
            "equal_connector_capital": equal_capital,
        },
        "cells": cells,
        "paired_contrasts": contrasts,
        "invariants": {
            "all_connectors_capital_bearing": equal_capital,
            "all_rows_complete": all(row.total.attempted == config.steps for row in rows),
            "network_invariants_hold": True,
        },
        "interpretation": {
            "public": "one cheapest public-topology path; no retry after hidden-liquidity failure",
            "adaptive": "tries the same bounded candidate set until a feasible path succeeds",
            "oracle": "upper bound that filters the candidate set using hidden directional state",
            "demand_aware": "places equal-budget capital using only warm-up demand endpoints",
            "post_stress": "fixed evaluation window after the configured stress boundary",
        },
        "safety_boundary": {
            "synthetic_only": True,
            "live_network": False,
            "wallet_or_node_connection": False,
            "invoice_or_payload": False,
            "network_transport": False,
            "transaction_broadcast": False,
        },
    }


def _write_rows(path: Path, rows: list[CapabilityRow]) -> None:
    flat = [row.flat_dict() for row in rows]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)


def _plot_success(summary: dict[str, object], path: Path) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(11.0, 4.6), sharey=True)
    colors = {"none": "#64748b", "random": "#b45309", "demand_aware": "#0f766e"}
    for axis, stress in zip(axes, STRESS_LEVELS):
        x = list(range(len(KNOWLEDGE_LEVELS)))
        for offset_index, connector_policy in enumerate(CONNECTOR_POLICIES):
            offset = (offset_index - 1) * 0.24
            values = [
                summary["cells"]["|".join((knowledge, connector_policy, stress))][
                    "post_stress_success_rate"
                ]["mean"]
                for knowledge in KNOWLEDGE_LEVELS
            ]
            axis.bar(
                [index + offset for index in x],
                values,
                width=0.23,
                label=connector_policy.replace("_", " "),
                color=colors[connector_policy],
            )
        axis.set_xticks(x, KNOWLEDGE_LEVELS)
        axis.set_ylim(0, 1.05)
        axis.set_title(stress.capitalize())
        axis.grid(axis="y", alpha=0.25)
    axes[0].set_ylabel("Post-boundary payment success")
    handles, labels = axes[1].get_legend_handles_labels()
    figure.legend(handles, labels, loc="lower center", ncol=3, bbox_to_anchor=(0.5, 0.01))
    figure.suptitle("Capability ladder: information, capital placement, and stress")
    figure.tight_layout(rect=(0, 0.10, 1, 0.95))
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _plot_leakage(summary: dict[str, object], path: Path) -> None:
    labels = list(KNOWLEDGE_LEVELS)
    normal = [
        summary["cells"]["|".join((knowledge, "none", "normal"))][
            "total_leakage_proxy"
        ]["mean"]
        for knowledge in KNOWLEDGE_LEVELS
    ]
    jammed = [
        summary["cells"]["|".join((knowledge, "none", "jammed"))][
            "total_leakage_proxy"
        ]["mean"]
        for knowledge in KNOWLEDGE_LEVELS
    ]
    x = list(range(len(labels)))
    figure, axis = plt.subplots(figsize=(7.6, 4.5))
    axis.bar([index - 0.18 for index in x], normal, 0.36, label="Normal", color="#0f766e")
    axis.bar([index + 0.18 for index in x], jammed, 0.36, label="Jammed", color="#b45309")
    axis.set_xticks(x, labels)
    axis.set_ylabel("Failed route attempts per demand")
    axis.set_title("Information capability and failure leakage")
    axis.grid(axis="y", alpha=0.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def run_campaign(
    output_dir: str | Path = "output/agent_capability_eval",
    config_path: str | Path = "configs/agent_capability_eval.json",
) -> dict[str, object]:
    output = Path(output_dir)
    figures = output / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    config = load_config(config_path)
    rows = [
        run_episode(seed, knowledge, connector_policy, stress, config)
        for seed in range(config.seed_count)
        for knowledge in KNOWLEDGE_LEVELS
        for connector_policy in CONNECTOR_POLICIES
        for stress in STRESS_LEVELS
    ]
    summary = summarize(rows, config)
    if not all(summary["invariants"].values()):
        raise AssertionError("capability campaign invariant failed")
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_rows(output / "rows.csv", rows)
    _plot_success(summary, figures / "capability_success.png")
    _plot_leakage(summary, figures / "failure_leakage.png")

    config_path = Path(config_path)
    receipt = {
        "schema_version": "1.0",
        "experiment_id": "sealed-agent-capability-frontier",
        "configuration_file": config_path.as_posix(),
        "configuration_hash": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "result_file": summary_path.as_posix(),
        "result_hash": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "live_network": False,
        "wallet_or_node_connection": False,
    }
    (output / "witness_receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="output/agent_capability_eval")
    parser.add_argument("--config", default="configs/agent_capability_eval.json")
    args = parser.parse_args()
    print(json.dumps(run_campaign(args.output, args.config), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
