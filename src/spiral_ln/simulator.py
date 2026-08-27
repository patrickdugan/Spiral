"""Deterministic synthetic experiments for connector-calculus mechanics."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from random import Random
from statistics import mean
from typing import Iterable, Literal

import networkx as nx

from .algebra import Channel, Connector, ConnectorKind, NetworkState, apply_connector


Strategy = Literal["baseline", "random_connector", "ghost_connector"]
Knowledge = Literal["public", "adaptive", "oracle"]


@dataclass(frozen=True)
class Demand:
    source: str
    target: str
    amount: int


@dataclass
class SimulationResult:
    strategy: str
    seed: int
    attempted: int
    succeeded: int
    attempted_volume: int
    delivered_volume: int
    fee_msat: int
    failed_attempts: int
    imbalance_start: float
    imbalance_end: float
    connector_capital: int

    @property
    def success_rate(self) -> float:
        return self.succeeded / max(1, self.attempted)

    @property
    def volume_rate(self) -> float:
        return self.delivered_volume / max(1, self.attempted_volume)

    @property
    def leakage_proxy(self) -> float:
        return self.failed_attempts / max(1, self.attempted)


def two_cluster_state(seed: int, cluster_size: int = 8) -> NetworkState:
    rng = Random(seed)
    state = NetworkState()
    clusters = [[f"A{i}" for i in range(cluster_size)], [f"B{i}" for i in range(cluster_size)]]
    for nodes in clusters:
        for index, u in enumerate(nodes):
            v = nodes[(index + 1) % len(nodes)]
            capacity = rng.randint(70_000, 130_000)
            state.add_channel(Channel(u, v, capacity, rng.randint(capacity // 3, 2 * capacity // 3)))
        for _ in range(cluster_size // 2):
            u, v = rng.sample(nodes, 2)
            if frozenset((u, v)) in state.channels:
                continue
            capacity = rng.randint(50_000, 100_000)
            state.add_channel(Channel(u, v, capacity, rng.randint(capacity // 4, 3 * capacity // 4)))
    # Two deliberately thin, directionally uneven cuts.
    state.add_channel(Channel("A0", "B0", 45_000, 9_000, fee_ppm=300))
    state.add_channel(Channel("A4", "B4", 55_000, 13_000, fee_ppm=250))
    state.assert_invariants()
    return state


def demand_stream(seed: int, steps: int = 360, cluster_size: int = 8) -> list[Demand]:
    rng = Random(seed + 10_000)
    left = [f"A{i}" for i in range(cluster_size)]
    right = [f"B{i}" for i in range(cluster_size)]
    demands: list[Demand] = []
    for _ in range(steps):
        draw = rng.random()
        if draw < 0.58:
            source, target = rng.choice(left), rng.choice(right)
        elif draw < 0.73:
            source, target = rng.choice(right), rng.choice(left)
        else:
            cluster = left if rng.random() < 0.5 else right
            source, target = rng.sample(cluster, 2)
        demands.append(Demand(source, target, rng.choice((1_000, 2_000, 5_000, 8_000))))
    return demands


def graph_of(state: NetworkState) -> nx.Graph:
    graph = nx.Graph()
    for channel in state.channels.values():
        graph.add_edge(channel.u, channel.v)
    return graph


def candidate_paths(state: NetworkState, source: str, target: str, limit: int = 8) -> list[list[str]]:
    try:
        generator = nx.shortest_simple_paths(graph_of(state), source, target)
        paths = []
        for _ in range(limit):
            try:
                paths.append(next(generator))
            except StopIteration:
                break
        return paths
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []


def _public_score(state: NetworkState, path: list[str], amount: int) -> tuple[int, int]:
    return (state.route_cost_msat(path, amount), len(path))


def route_payment(
    state: NetworkState,
    demand: Demand,
    knowledge: Knowledge = "adaptive",
) -> tuple[bool, int, int]:
    paths = sorted(
        candidate_paths(state, demand.source, demand.target),
        key=lambda path: _public_score(state, path, demand.amount),
    )
    if not paths:
        return False, 0, 1
    if knowledge == "public":
        paths = paths[:1]
    elif knowledge == "oracle":
        paths = [path for path in paths if state.route_feasible(path, demand.amount)][:1]
    failures = 0
    for path in paths:
        if not state.route_feasible(path, demand.amount):
            failures += 1
            continue
        fee = state.route_cost_msat(path, demand.amount)
        state.apply_route(path, demand.amount)
        return True, fee, failures
    return False, 0, max(1, failures)


def choose_ghost_connector(demands: Iterable[Demand], amount: int = 120_000) -> Connector:
    cross = Counter(
        (d.source, d.target)
        for d in demands
        if d.source[0] != d.target[0]
    )
    (source, target), _ = cross.most_common(1)[0]
    return Connector(
        "ghost-demand-cut",
        ConnectorKind.TOPOLOGICAL,
        (source, target),
        amount,
        bond=24_000,
        capital_id="utxo:ghost-demand-cut",
    )


def choose_random_connector(seed: int, amount: int = 120_000) -> Connector:
    rng = Random(seed + 20_000)
    return Connector(
        "random-cross-cut",
        ConnectorKind.TOPOLOGICAL,
        (f"A{rng.randrange(8)}", f"B{rng.randrange(8)}"),
        amount,
        bond=0,
        capital_id="utxo:random-cross-cut",
    )


def jam_high_betweenness(state: NetworkState, fraction: float = 0.90) -> list[tuple[str, str]]:
    graph = graph_of(state)
    scores = nx.edge_betweenness_centrality(graph)
    targets = sorted(scores, key=scores.get, reverse=True)[:2]
    for a, b in targets:
        channel = state.channel(a, b)
        channel.locked_uv = min(channel.balance_uv, int(channel.balance_uv * fraction))
        channel.locked_vu = min(channel.balance_vu, int(channel.balance_vu * fraction))
    return targets


def run_simulation(
    seed: int,
    strategy: Strategy = "baseline",
    knowledge: Knowledge = "adaptive",
    steps: int = 360,
    jam: bool = False,
) -> SimulationResult:
    state = two_cluster_state(seed)
    demands = demand_stream(seed, steps)
    connector_capital = 0
    if strategy == "random_connector":
        connector = choose_random_connector(seed)
        if frozenset(connector.endpoints[:2]) not in state.channels:
            apply_connector(state, connector)
            connector_capital = connector.amount
    elif strategy == "ghost_connector":
        connector = choose_ghost_connector(demands[: max(40, steps // 4)])
        if frozenset(connector.endpoints[:2]) not in state.channels:
            apply_connector(state, connector)
            connector_capital = connector.amount
    if jam:
        jam_high_betweenness(state)
    imbalance_start = state.imbalance_energy()
    succeeded = delivered = fees = failures = attempted_volume = 0
    for demand in demands:
        attempted_volume += demand.amount
        ok, fee, failed = route_payment(state, demand, knowledge)
        failures += failed
        if ok:
            succeeded += 1
            delivered += demand.amount
            fees += fee
    state.assert_invariants()
    return SimulationResult(
        strategy,
        seed,
        len(demands),
        succeeded,
        attempted_volume,
        delivered,
        fees,
        failures,
        imbalance_start,
        state.imbalance_energy(),
        connector_capital,
    )


def summarize(results: Iterable[SimulationResult]) -> dict[str, float]:
    rows = list(results)
    return {
        "n": len(rows),
        "success_rate_mean": mean(row.success_rate for row in rows),
        "volume_rate_mean": mean(row.volume_rate for row in rows),
        "leakage_proxy_mean": mean(row.leakage_proxy for row in rows),
        "imbalance_end_mean": mean(row.imbalance_end for row in rows),
        "fee_msat_mean": mean(row.fee_msat for row in rows),
        "connector_capital_mean": mean(row.connector_capital for row in rows),
    }

