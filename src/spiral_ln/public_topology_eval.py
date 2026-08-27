"""Sealed agent-capability evaluation on sampled public Lightning topology.

The agent sees public paths, public fee fields, and its own terminal path
outcomes. It never sees synthetic capacities, directional balances, failing
edges, future demand, or oracle feasibility. No live-network capability exists.
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
import networkx as nx
import numpy as np

from .algebra import Connector, ConnectorKind, NetworkState, apply_connector
from .public_topology import (
    BALANCE_MODELS,
    DEMAND_REGIMES,
    SAMPLING_MODES,
    BalanceModel,
    DemandRegime,
    PublicTopologySample,
    load_public_graph,
    network_state_from_public_sample,
    public_demand_stream,
    public_graph_stats,
    sample_connected_subgraph,
)
from .simulator import Demand, graph_of


RoutingPolicy = Literal["public", "retry", "online", "oracle"]
CapitalPolicy = Literal["none", "random", "failure_aware"]
ROUTING_POLICIES: tuple[RoutingPolicy, ...] = ("public", "retry", "online", "oracle")
CAPITAL_POLICIES: tuple[CapitalPolicy, ...] = ("none", "random", "failure_aware")
CONDITIONS: tuple[tuple[RoutingPolicy, CapitalPolicy], ...] = (
    ("public", "none"),
    ("retry", "none"),
    ("online", "none"),
    ("oracle", "none"),
    ("online", "random"),
    ("online", "failure_aware"),
)


@dataclass(frozen=True)
class PublicTopologyEvalConfig:
    snapshot_path: str = "data/topology/20230716.gml.geo"
    snapshot_sha256: str = "ee1b054a6ba2cb0ea3184f9f68f5cca7d8e70d17ff2d9e44e5e8871be8a8b855"
    topology_sample_count: int = 8
    calibration_sample_count: int = 4
    balance_draws: int = 2
    node_count: int = 64
    steps: int = 220
    evaluation_start: int = 110
    early_evaluation_steps: int = 25
    hotspot_probability: float = 0.35
    amounts: tuple[int, ...] = (1_000, 2_000, 5_000, 8_000)
    capacity_median: int = 100_000
    capacity_log_sigma: float = 0.85
    capacity_minimum: int = 20_000
    capacity_maximum: int = 1_500_000
    candidate_path_limit: int = 8
    max_route_attempts: int = 3
    online_risk_penalty_msat: float = 5_000.0
    connector_capital: int = 120_000
    connector_bond_fraction: float = 0.20
    seed_offset: int = 0

    def __post_init__(self) -> None:
        if not 2 <= self.topology_sample_count or not 1 <= self.calibration_sample_count < self.topology_sample_count:
            raise ValueError("invalid topology calibration/holdout split")
        if self.balance_draws <= 0 or self.node_count < 16:
            raise ValueError("balance_draws and node_count are too small")
        if not 0 < self.evaluation_start < self.steps:
            raise ValueError("evaluation_start must be inside the episode")
        if not 0 < self.early_evaluation_steps < self.steps - self.evaluation_start:
            raise ValueError("early evaluation window is invalid")
        if not 0 <= self.hotspot_probability <= 1:
            raise ValueError("hotspot_probability must lie in [0, 1]")
        if not self.amounts or any(amount <= 0 for amount in self.amounts):
            raise ValueError("amounts must be positive")
        if not 1 <= self.max_route_attempts <= self.candidate_path_limit:
            raise ValueError("route attempt budget exceeds the candidate path limit")
        if self.connector_capital <= 0 or not 0 <= self.connector_bond_fraction <= 1:
            raise ValueError("connector capital or bond fraction is invalid")
        if self.seed_offset < 0:
            raise ValueError("seed_offset must be nonnegative")


@dataclass(frozen=True)
class SegmentMetrics:
    attempted: int
    succeeded: int
    attempted_volume: int
    delivered_volume: int
    infeasible_path_attempts: int
    fee_msat: int

    @property
    def success_rate(self) -> float:
        return self.succeeded / max(1, self.attempted)

    @property
    def volume_rate(self) -> float:
        return self.delivered_volume / max(1, self.attempted_volume)

    @property
    def leakage_proxy(self) -> float:
        return self.infeasible_path_attempts / max(1, self.attempted)


@dataclass
class _MutableSegment:
    attempted: int = 0
    succeeded: int = 0
    attempted_volume: int = 0
    delivered_volume: int = 0
    infeasible_path_attempts: int = 0
    fee_msat: int = 0

    def observe(self, demand: Demand, delivered: bool, failures: int, fee: int) -> None:
        self.attempted += 1
        self.attempted_volume += demand.amount
        self.infeasible_path_attempts += failures
        self.fee_msat += fee
        if delivered:
            self.succeeded += 1
            self.delivered_volume += demand.amount

    def freeze(self) -> SegmentMetrics:
        return SegmentMetrics(**asdict(self))


@dataclass(frozen=True)
class PublicEvalRow:
    evaluation_split: str
    topology_index: int
    topology_sample_id: str
    topology_mode: str
    topology_nodes: int
    topology_edges: int
    topology_bridges: int
    balance_draw: int
    balance_model: str
    demand_regime: str
    routing_policy: str
    capital_policy: str
    connector_endpoints: str
    connector_capital: int
    connector_matches_evaluation_hotspot: bool
    training: SegmentMetrics
    early_evaluation: SegmentMetrics
    late_evaluation: SegmentMetrics
    evaluation: SegmentMetrics
    imbalance_start: float
    imbalance_end: float
    capacity_end: int

    def flat_dict(self) -> dict[str, object]:
        row = {
            key: value
            for key, value in asdict(self).items()
            if key not in {"training", "early_evaluation", "late_evaluation", "evaluation"}
        }
        for name in ("training", "early_evaluation", "late_evaluation", "evaluation"):
            segment = getattr(self, name)
            for field_name, value in asdict(segment).items():
                row[f"{name}_{field_name}"] = value
            row[f"{name}_success_rate"] = segment.success_rate
            row[f"{name}_volume_rate"] = segment.volume_rate
            row[f"{name}_leakage_proxy"] = segment.leakage_proxy
        return row


class PathCatalog:
    """Public candidate paths cached independently of hidden balance state."""

    def __init__(self, graph: nx.Graph, limit: int) -> None:
        self.graph = nx.Graph(graph)
        self.limit = limit
        self.cache: dict[tuple[str, str], tuple[tuple[str, ...], ...]] = {}

    def paths(self, source: str, target: str) -> tuple[tuple[str, ...], ...]:
        key = (source, target)
        if key in self.cache:
            return self.cache[key]
        try:
            generator = nx.shortest_simple_paths(self.graph, source, target)
            paths = []
            for _ in range(self.limit):
                try:
                    paths.append(tuple(next(generator)))
                except StopIteration:
                    break
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            paths = []
        self.cache[key] = tuple(paths)
        return self.cache[key]


class TerminalFeedbackAgent:
    """Learns directed-edge risk from whole-path outcomes only."""

    def __init__(self, risk_penalty_msat: float) -> None:
        self.risk_penalty_msat = risk_penalty_msat
        self.trials: Counter[tuple[str, str]] = Counter()
        self.failures: Counter[tuple[str, str]] = Counter()

    def path_risk(self, path: tuple[str, ...]) -> float:
        edges = list(zip(path, path[1:]))
        if not edges:
            return 1.0
        return mean((self.failures[edge] + 1) / (self.trials[edge] + 2) for edge in edges)

    def rank(
        self,
        paths: tuple[tuple[str, ...], ...],
        public_costs: dict[tuple[str, ...], int],
    ) -> list[tuple[str, ...]]:
        return sorted(
            paths,
            key=lambda path: (
                public_costs[path] + self.risk_penalty_msat * self.path_risk(path),
                len(path),
                path,
            ),
        )

    def observe(self, path: tuple[str, ...], delivered: bool) -> None:
        for edge in zip(path, path[1:]):
            self.trials[edge] += 1
            if not delivered:
                self.failures[edge] += 1


class FailedDemandTracker:
    def __init__(self) -> None:
        self.failed_pairs: Counter[tuple[str, str]] = Counter()

    def observe(self, demand: Demand, delivered: bool) -> None:
        if not delivered:
            self.failed_pairs[tuple(sorted((demand.source, demand.target)))] += 1


def _public_cost(state: NetworkState, path: tuple[str, ...], amount: int) -> tuple[int, int, tuple[str, ...]]:
    return state.route_cost_msat(path, amount), len(path), path


def execute_payment(
    state: NetworkState,
    demand: Demand,
    policy: RoutingPolicy,
    catalog: PathCatalog,
    online_agent: TerminalFeedbackAgent,
    max_attempts: int,
) -> tuple[bool, int, int]:
    paths = tuple(sorted(catalog.paths(demand.source, demand.target), key=lambda path: _public_cost(state, path, demand.amount)))
    if policy == "oracle":
        feasible = [path for path in paths if state.route_feasible(path, demand.amount)]
        if not feasible:
            return False, 0, 0
        path = feasible[0]
        fee = state.route_cost_msat(path, demand.amount)
        state.apply_route(path, demand.amount)
        return True, fee, 0
    if policy == "public":
        attempts = list(paths[:1])
    elif policy == "retry":
        attempts = list(paths[:max_attempts])
    elif policy == "online":
        public_costs = {path: state.route_cost_msat(path, demand.amount) for path in paths}
        attempts = online_agent.rank(paths, public_costs)[:max_attempts]
    else:
        raise ValueError(f"unknown routing policy: {policy}")
    failures = 0
    for path in attempts:
        delivered = state.route_feasible(path, demand.amount)
        if policy == "online":
            online_agent.observe(path, delivered)
        if not delivered:
            failures += 1
            continue
        fee = state.route_cost_msat(path, demand.amount)
        state.apply_route(path, demand.amount)
        return True, fee, failures
    return False, 0, failures


def _nonedges(state: NetworkState) -> list[tuple[str, str]]:
    nodes = sorted(state.nodes)
    return [
        (left, right)
        for index, left in enumerate(nodes)
        for right in nodes[index + 1 :]
        if frozenset((left, right)) not in state.channels
    ]


def choose_capital_connector(
    state: NetworkState,
    policy: CapitalPolicy,
    tracker: FailedDemandTracker,
    seed: int,
    amount: int,
    bond_fraction: float,
) -> Connector | None:
    if policy == "none":
        return None
    available = set(_nonedges(state))
    if not available:
        return None
    if policy == "random":
        endpoints = Random(seed + 125_000).choice(sorted(available))
    elif policy == "failure_aware":
        ranked = sorted(available, key=lambda pair: (tracker.failed_pairs[pair], pair), reverse=True)
        endpoints = (
            ranked[0]
            if tracker.failed_pairs[ranked[0]] > 0
            else Random(seed + 125_000).choice(sorted(available))
        )
    else:
        raise ValueError(f"unknown capital policy: {policy}")
    return Connector(
        connector_id=f"public-eval:{policy}",
        kind=ConnectorKind.TOPOLOGICAL,
        endpoints=endpoints,
        amount=amount,
        bond=max(1, int(amount * bond_fraction)),
        capital_id=f"sealed-public-topology:{policy}",
    )


def load_config(path: str | Path) -> PublicTopologyEvalConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data.pop("schema_version", None)
    data.pop("description", None)
    data.pop("preregistered_hypotheses", None)
    if "amounts" in data:
        data["amounts"] = tuple(int(value) for value in data["amounts"])
    return PublicTopologyEvalConfig(**data)


def run_episode(
    sample: PublicTopologySample,
    topology_index: int,
    balance_draw: int,
    balance_model: BalanceModel,
    demand_regime: DemandRegime,
    routing_policy: RoutingPolicy,
    capital_policy: CapitalPolicy,
    config: PublicTopologyEvalConfig,
    base_catalog: PathCatalog | None = None,
) -> PublicEvalRow:
    experiment_seed = config.seed_offset + topology_index
    capacity_seed = experiment_seed
    balance_seed = 10_000 * experiment_seed + balance_draw
    state = network_state_from_public_sample(
        sample,
        capacity_seed,
        balance_seed,
        balance_model,
        config.capacity_median,
        config.capacity_log_sigma,
        config.capacity_minimum,
        config.capacity_maximum,
    )
    demands, training_hotspot, shifted_hotspot = public_demand_stream(
        sample.graph,
        seed=20_000 * experiment_seed + balance_draw,
        steps=config.steps,
        holdout_start=config.evaluation_start,
        regime=demand_regime,
        hotspot_probability=config.hotspot_probability,
        amounts=config.amounts,
    )
    evaluation_hotspot = shifted_hotspot if demand_regime == "shifted_hotspot" else training_hotspot
    catalog = base_catalog or PathCatalog(sample.graph, config.candidate_path_limit)
    agent = TerminalFeedbackAgent(config.online_risk_penalty_msat)
    tracker = FailedDemandTracker()
    training = _MutableSegment()
    early = _MutableSegment()
    late = _MutableSegment()
    evaluation = _MutableSegment()
    connector = None
    imbalance_start = state.imbalance_energy()
    for index, demand in enumerate(demands):
        if index == config.evaluation_start:
            connector = choose_capital_connector(
                state,
                capital_policy,
                tracker,
                seed=30_000 * experiment_seed + balance_draw,
                amount=config.connector_capital,
                bond_fraction=config.connector_bond_fraction,
            )
            if connector is not None:
                apply_connector(state, connector)
                catalog = PathCatalog(graph_of(state), config.candidate_path_limit)
        delivered, fee, failures = execute_payment(
            state,
            demand,
            routing_policy,
            catalog,
            agent,
            config.max_route_attempts,
        )
        tracker.observe(demand, delivered)
        if index < config.evaluation_start:
            training.observe(demand, delivered, failures, fee)
        else:
            evaluation.observe(demand, delivered, failures, fee)
            if index < config.evaluation_start + config.early_evaluation_steps:
                early.observe(demand, delivered, failures, fee)
            else:
                late.observe(demand, delivered, failures, fee)
    state.assert_invariants()
    stats = sample.stats()
    connector_endpoints = () if connector is None else connector.endpoints[:2]
    return PublicEvalRow(
        evaluation_split="calibration" if topology_index < config.calibration_sample_count else "sealed_holdout",
        topology_index=topology_index,
        topology_sample_id=sample.sample_id,
        topology_mode=sample.mode,
        topology_nodes=int(stats["nodes"]),
        topology_edges=int(stats["edges"]),
        topology_bridges=int(stats["bridge_count"]),
        balance_draw=balance_draw,
        balance_model=balance_model,
        demand_regime=demand_regime,
        routing_policy=routing_policy,
        capital_policy=capital_policy,
        connector_endpoints="|".join(connector_endpoints),
        connector_capital=0 if connector is None else connector.amount,
        connector_matches_evaluation_hotspot=(
            bool(connector_endpoints)
            and frozenset(connector_endpoints) == frozenset(evaluation_hotspot)
        ),
        training=training.freeze(),
        early_evaluation=early.freeze(),
        late_evaluation=late.freeze(),
        evaluation=evaluation.freeze(),
        imbalance_start=imbalance_start,
        imbalance_end=state.imbalance_energy(),
        capacity_end=state.total_capacity,
    )


def _mean_ci(values: list[float]) -> dict[str, float | int]:
    half_width = 0.0 if len(values) < 2 else 1.96 * stdev(values) / sqrt(len(values))
    return {"n": len(values), "mean": mean(values) if values else 0.0, "ci95_half_width": half_width}


def _metric(row: PublicEvalRow, name: str) -> float:
    lookup = {
        "evaluation_success_rate": row.evaluation.success_rate,
        "evaluation_volume_rate": row.evaluation.volume_rate,
        "evaluation_leakage_proxy": row.evaluation.leakage_proxy,
        "early_success_rate": row.early_evaluation.success_rate,
        "late_success_rate": row.late_evaluation.success_rate,
        "connector_match": float(row.connector_matches_evaluation_hotspot),
        "imbalance_change": row.imbalance_end - row.imbalance_start,
    }
    return lookup[name]


def _condition_rows(
    rows: list[PublicEvalRow],
    routing: str,
    capital: str,
    balance_model: str | None = None,
    demand_regime: str | None = None,
) -> dict[tuple[int, int, str, str], PublicEvalRow]:
    return {
        (row.topology_index, row.balance_draw, row.balance_model, row.demand_regime): row
        for row in rows
        if row.evaluation_split == "sealed_holdout"
        and row.routing_policy == routing
        and row.capital_policy == capital
        and (balance_model is None or row.balance_model == balance_model)
        and (demand_regime is None or row.demand_regime == demand_regime)
    }


def _paired(
    rows: list[PublicEvalRow],
    left: tuple[str, str],
    right: tuple[str, str],
    metric: str,
    balance_model: str | None = None,
    demand_regime: str | None = None,
) -> dict[str, object]:
    left_rows = _condition_rows(rows, *left, balance_model, demand_regime)
    right_rows = _condition_rows(rows, *right, balance_model, demand_regime)
    keys = sorted(set(left_rows) & set(right_rows))
    differences = [_metric(left_rows[key], metric) - _metric(right_rows[key], metric) for key in keys]
    return {
        "left": "|".join(left),
        "right": "|".join(right),
        "metric": metric,
        "balance_model": balance_model or "all",
        "demand_regime": demand_regime or "all",
        "left_minus_right": _mean_ci(differences),
    }


def _paired_temporal_change(
    rows: list[PublicEvalRow],
    left: tuple[str, str],
    right: tuple[str, str],
    demand_regime: str,
) -> dict[str, object]:
    left_rows = _condition_rows(rows, *left, demand_regime=demand_regime)
    right_rows = _condition_rows(rows, *right, demand_regime=demand_regime)
    keys = sorted(set(left_rows) & set(right_rows))
    differences = [
        (
            left_rows[key].late_evaluation.success_rate
            - left_rows[key].early_evaluation.success_rate
        )
        - (
            right_rows[key].late_evaluation.success_rate
            - right_rows[key].early_evaluation.success_rate
        )
        for key in keys
    ]
    return {
        "left": "|".join(left),
        "right": "|".join(right),
        "metric": "(late_success_rate - early_success_rate) difference-in-differences",
        "demand_regime": demand_regime,
        "left_minus_right": _mean_ci(differences),
    }


def summarize(
    rows: list[PublicEvalRow],
    config: PublicTopologyEvalConfig,
    source_stats: dict[str, float | int],
    sample_stats: list[dict[str, float | int | str]],
) -> dict[str, object]:
    holdout = [row for row in rows if row.evaluation_split == "sealed_holdout"]
    metrics = ("evaluation_success_rate", "evaluation_volume_rate", "evaluation_leakage_proxy")
    cells = {}
    for routing, capital in CONDITIONS:
        subset = [row for row in holdout if row.routing_policy == routing and row.capital_policy == capital]
        cells["|".join((routing, capital))] = {
            metric: _mean_ci([_metric(row, metric) for row in subset]) for metric in metrics
        }

    contrasts = {
        "retry_minus_public_success": _paired(rows, ("retry", "none"), ("public", "none"), "evaluation_success_rate"),
        "online_minus_retry_success": _paired(rows, ("online", "none"), ("retry", "none"), "evaluation_success_rate"),
        "online_minus_retry_leakage": _paired(rows, ("online", "none"), ("retry", "none"), "evaluation_leakage_proxy"),
        "oracle_minus_online_success": _paired(rows, ("oracle", "none"), ("online", "none"), "evaluation_success_rate"),
        "oracle_minus_online_leakage": _paired(rows, ("oracle", "none"), ("online", "none"), "evaluation_leakage_proxy"),
        "failure_capital_minus_random_success": _paired(rows, ("online", "failure_aware"), ("online", "random"), "evaluation_success_rate"),
        "failure_capital_minus_none_success": _paired(rows, ("online", "failure_aware"), ("online", "none"), "evaluation_success_rate"),
    }
    stratified = []
    for balance_model in BALANCE_MODELS:
        for demand_regime in DEMAND_REGIMES:
            stratified.append(
                {
                    "balance_model": balance_model,
                    "demand_regime": demand_regime,
                    "online_minus_retry_success": _paired(
                        rows,
                        ("online", "none"),
                        ("retry", "none"),
                        "evaluation_success_rate",
                        balance_model,
                        demand_regime,
                    )["left_minus_right"],
                    "failure_capital_minus_random_success": _paired(
                        rows,
                        ("online", "failure_aware"),
                        ("online", "random"),
                        "evaluation_success_rate",
                        balance_model,
                        demand_regime,
                    )["left_minus_right"],
                    "failure_capital_match_rate": _mean_ci(
                        [
                            _metric(row, "connector_match")
                            for row in holdout
                            if row.routing_policy == "online"
                            and row.capital_policy == "failure_aware"
                            and row.balance_model == balance_model
                            and row.demand_regime == demand_regime
                        ]
                    ),
                }
            )
    shift_online = [
        row
        for row in holdout
        if row.routing_policy == "online"
        and row.capital_policy == "none"
        and row.demand_regime == "shifted_hotspot"
    ]
    adaptation = {
        "early_evaluation_success": _mean_ci([row.early_evaluation.success_rate for row in shift_online]),
        "late_evaluation_success": _mean_ci([row.late_evaluation.success_rate for row in shift_online]),
        "late_minus_early": _mean_ci(
            [row.late_evaluation.success_rate - row.early_evaluation.success_rate for row in shift_online]
        ),
        "online_minus_retry_early": _paired(
            rows, ("online", "none"), ("retry", "none"), "early_success_rate", demand_regime="shifted_hotspot"
        ),
        "online_minus_retry_late": _paired(
            rows, ("online", "none"), ("retry", "none"), "late_success_rate", demand_regime="shifted_hotspot"
        ),
        "online_temporal_advantage_over_retry": _paired_temporal_change(
            rows, ("online", "none"), ("retry", "none"), "shifted_hotspot"
        ),
    }
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_topology": source_stats,
        "sample_topologies": sample_stats,
        "design": {
            "topology_sample_count": config.topology_sample_count,
            "calibration_sample_count": config.calibration_sample_count,
            "sealed_holdout_sample_count": config.topology_sample_count - config.calibration_sample_count,
            "balance_draws_per_topology": config.balance_draws,
            "seed_offset": config.seed_offset,
            "balance_models": list(BALANCE_MODELS),
            "demand_regimes": list(DEMAND_REGIMES),
            "routing_conditions": ["|".join(condition) for condition in CONDITIONS],
            "agent_feedback": "terminal path success or failure only",
            "future_demand_visible": False,
            "hidden_capacity_visible": False,
            "hidden_balance_visible": False,
            "failing_edge_visible": False,
            "claims_use_sealed_holdout_only": True,
        },
        "holdout_cells": cells,
        "holdout_paired_contrasts": contrasts,
        "holdout_stratified": stratified,
        "shift_adaptation": adaptation,
        "invariants": {
            "all_rows_complete": all(row.training.attempted + row.evaluation.attempted == config.steps for row in rows),
            "equal_connector_capital": all(
                row.connector_capital == config.connector_capital
                for row in rows
                if row.capital_policy in {"random", "failure_aware"}
            ),
            "network_invariants_hold": True,
            "source_hash_verified": True,
        },
        "interpretation": {
            "topology": "public gossip-derived structure from 2023-07-16",
            "capacity": "paired synthetic lognormal capacity; not present in source GML",
            "balance": "hidden paired ensemble; not observed or measured",
            "online": "terminal-feedback edge-risk learner with fixed preregistered parameters",
            "sealed_holdout": "topology samples excluded from calibration indices",
        },
        "safety_boundary": {
            "synthetic_execution_only": True,
            "live_network": False,
            "wallet_or_node_connection": False,
            "invoice_or_payload": False,
            "network_transport": False,
            "transaction_broadcast": False,
        },
    }


def _write_rows(path: Path, rows: list[PublicEvalRow]) -> None:
    flat = [row.flat_dict() for row in rows]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)


def _plot_routing(summary: dict[str, object], path: Path) -> None:
    policies = list(ROUTING_POLICIES)
    success = [summary["holdout_cells"][f"{policy}|none"]["evaluation_success_rate"]["mean"] for policy in policies]
    leakage = [summary["holdout_cells"][f"{policy}|none"]["evaluation_leakage_proxy"]["mean"] for policy in policies]
    x = np.arange(len(policies))
    figure, axis = plt.subplots(figsize=(8.0, 4.7))
    axis.bar(x - 0.18, success, 0.36, label="Success rate", color="#0f766e")
    axis.bar(x + 0.18, leakage, 0.36, label="Infeasible attempts / demand", color="#b45309")
    axis.set_xticks(x, policies)
    axis.set_ylabel("Rate")
    axis.set_title("Sealed public-topology holdout: routing capability")
    axis.grid(axis="y", alpha=0.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _plot_capital(summary: dict[str, object], path: Path) -> None:
    strata = summary["holdout_stratified"]
    matrix = np.zeros((len(BALANCE_MODELS), len(DEMAND_REGIMES)))
    for cell in strata:
        row = BALANCE_MODELS.index(cell["balance_model"])
        column = DEMAND_REGIMES.index(cell["demand_regime"])
        matrix[row, column] = cell["failure_capital_minus_random_success"]["mean"]
    bound = max(0.01, float(np.max(np.abs(matrix))))
    figure, axis = plt.subplots(figsize=(8.2, 4.8))
    image = axis.imshow(matrix, cmap="RdBu", vmin=-bound, vmax=bound, aspect="auto")
    axis.set_xticks(range(len(DEMAND_REGIMES)), [name.replace("_", "\n") for name in DEMAND_REGIMES])
    axis.set_yticks(range(len(BALANCE_MODELS)), [name.replace("_", " ") for name in BALANCE_MODELS])
    axis.set_title("Failure-aware capital minus equal random capital")
    for row in range(len(BALANCE_MODELS)):
        for column in range(len(DEMAND_REGIMES)):
            axis.text(column, row, f"{100 * matrix[row, column]:+.1f} pp", ha="center", va="center")
    figure.colorbar(image, ax=axis, label="Paired holdout success difference")
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def run_campaign(
    output_dir: str | Path = "output/public_topology_eval",
    config_path: str | Path = "configs/public_topology_eval.json",
) -> dict[str, object]:
    output = Path(output_dir)
    figures = output / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    config = load_config(config_path)
    snapshot = Path(config.snapshot_path)
    actual_hash = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    if actual_hash != config.snapshot_sha256:
        raise ValueError("public topology snapshot SHA-256 mismatch")
    source_graph = load_public_graph(snapshot)
    source_stats = public_graph_stats(source_graph)
    source_stats["snapshot_sha256"] = actual_hash
    samples = [
        sample_connected_subgraph(
            source_graph,
            seed=config.seed_offset + index,
            node_count=config.node_count,
            mode=SAMPLING_MODES[index % len(SAMPLING_MODES)],
        )
        for index in range(config.topology_sample_count)
    ]
    catalogs = [PathCatalog(sample.graph, config.candidate_path_limit) for sample in samples]
    rows = []
    for topology_index, sample in enumerate(samples):
        for balance_draw in range(config.balance_draws):
            for balance_model in BALANCE_MODELS:
                for demand_regime in DEMAND_REGIMES:
                    for routing_policy, capital_policy in CONDITIONS:
                        rows.append(
                            run_episode(
                                sample,
                                topology_index,
                                balance_draw,
                                balance_model,
                                demand_regime,
                                routing_policy,
                                capital_policy,
                                config,
                                catalogs[topology_index],
                            )
                        )
    summary = summarize(rows, config, source_stats, [sample.stats() for sample in samples])
    if not all(summary["invariants"].values()):
        raise AssertionError("public-topology evaluation invariant failed")
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_rows(output / "rows.csv", rows)
    _plot_routing(summary, figures / "routing_holdout.png")
    _plot_capital(summary, figures / "capital_holdout.png")
    config_path = Path(config_path)
    provenance_path = snapshot.parent / "snapshot_provenance.json"
    receipt = {
        "schema_version": "1.0",
        "experiment_id": "sealed-public-topology-agent-capability",
        "configuration_file": config_path.as_posix(),
        "configuration_hash": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "topology_provenance_file": provenance_path.as_posix(),
        "topology_provenance_hash": hashlib.sha256(provenance_path.read_bytes()).hexdigest(),
        "topology_snapshot_hash": actual_hash,
        "implementation_hashes": {
            relative_path: hashlib.sha256(Path(relative_path).read_bytes()).hexdigest()
            for relative_path in (
                "src/spiral_ln/public_topology_eval.py",
                "src/spiral_ln/public_topology.py",
                "src/spiral_ln/algebra.py",
                "src/spiral_ln/simulator.py",
            )
        },
        "result_file": summary_path.as_posix(),
        "result_hash": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "live_network": False,
        "wallet_or_node_connection": False,
    }
    (output / "witness_receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="output/public_topology_eval")
    parser.add_argument("--config", default="configs/public_topology_eval.json")
    args = parser.parse_args()
    print(json.dumps(run_campaign(args.output, args.config), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
