"""Public-topology sampling and explicit hidden-state ensembles.

Topology and public fee fields come from a GML gossip snapshot. Channel
capacities and directional balances are synthetic experimental variables
because the selected public dataset contains neither authoritative capacities
nor private balance state.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from math import exp, log
from pathlib import Path
from random import Random
from statistics import mean
from typing import Literal

import networkx as nx

from .algebra import Channel, NetworkState
from .simulator import Demand


SamplingMode = Literal["hub", "random", "periphery"]
BalanceModel = Literal["balanced_band", "uniform", "polarized"]
DemandRegime = Literal["diffuse", "stationary_hotspot", "shifted_hotspot"]
SAMPLING_MODES: tuple[SamplingMode, ...] = ("hub", "random", "periphery")
BALANCE_MODELS: tuple[BalanceModel, ...] = ("balanced_band", "uniform", "polarized")
DEMAND_REGIMES: tuple[DemandRegime, ...] = (
    "diffuse",
    "stationary_hotspot",
    "shifted_hotspot",
)


@dataclass(frozen=True)
class PublicTopologySample:
    graph: nx.Graph
    sample_id: str
    mode: str
    anchor_hash: str
    source_node_hash: str

    def stats(self) -> dict[str, float | int | str]:
        degrees = [degree for _, degree in self.graph.degree()]
        bridges = list(nx.bridges(self.graph))
        return {
            "sample_id": self.sample_id,
            "mode": self.mode,
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "mean_degree": mean(degrees) if degrees else 0.0,
            "max_degree": max(degrees, default=0),
            "density": nx.density(self.graph),
            "bridge_count": len(bridges),
            "diameter": nx.diameter(self.graph),
        }


def load_public_graph(path: str | Path) -> nx.Graph:
    graph = nx.Graph(nx.read_gml(Path(path)))
    graph.remove_edges_from(nx.selfloop_edges(graph))
    if graph.number_of_nodes() == 0 or graph.number_of_edges() == 0:
        raise ValueError("public topology is empty")
    return graph


def public_graph_stats(graph: nx.Graph) -> dict[str, float | int]:
    components = sorted((len(component) for component in nx.connected_components(graph)), reverse=True)
    degrees = [degree for _, degree in graph.degree()]
    return {
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "component_count": len(components),
        "largest_component_nodes": components[0],
        "largest_component_share": components[0] / graph.number_of_nodes(),
        "mean_degree": mean(degrees),
        "max_degree": max(degrees),
    }


def _anchor_candidates(graph: nx.Graph, mode: SamplingMode) -> list[str]:
    degrees = dict(graph.degree())
    if mode == "hub":
        return [node for node, _ in sorted(degrees.items(), key=lambda item: (-item[1], item[0]))[:64]]
    if mode == "periphery":
        candidates = sorted(node for node, degree in degrees.items() if degree <= 2)
        if candidates:
            return candidates
    return sorted(graph.nodes())


def sample_connected_subgraph(
    graph: nx.Graph,
    seed: int,
    node_count: int = 64,
    mode: SamplingMode = "random",
) -> PublicTopologySample:
    if mode not in SAMPLING_MODES:
        raise ValueError(f"unknown sampling mode: {mode}")
    largest = max(nx.connected_components(graph), key=len)
    giant = graph.subgraph(largest)
    if not 8 <= node_count <= giant.number_of_nodes():
        raise ValueError("node_count must fit inside the largest component and be at least eight")
    rng = Random(seed + 120_000)
    anchor = rng.choice(_anchor_candidates(giant, mode))
    selected = {anchor}
    frontier = [anchor]
    while len(selected) < node_count:
        if not frontier:
            raise AssertionError("connected frontier exhausted before reaching requested sample size")
        index = rng.randrange(len(frontier))
        current = frontier.pop(index)
        neighbors = [node for node in giant.neighbors(current) if node not in selected]
        rng.shuffle(neighbors)
        for neighbor in neighbors:
            selected.add(neighbor)
            frontier.append(neighbor)
            if len(selected) == node_count:
                break
    sampled = giant.subgraph(selected).copy()
    if not nx.is_connected(sampled):
        raise AssertionError("sampled public subgraph is disconnected")
    originals = sorted(str(node) for node in sampled.nodes())
    source_hash = hashlib.sha256("\n".join(originals).encode()).hexdigest()
    mapping = {node: f"N{index:03d}" for index, node in enumerate(originals)}
    relabeled = nx.relabel_nodes(sampled, mapping, copy=True)
    sample_id = f"public-{mode}-{seed}-{source_hash[:12]}"
    return PublicTopologySample(
        graph=relabeled,
        sample_id=sample_id,
        mode=mode,
        anchor_hash=hashlib.sha256(str(anchor).encode()).hexdigest(),
        source_node_hash=source_hash,
    )


def _balance_fraction(model: BalanceModel, uniform_draw: float) -> float:
    if model == "balanced_band":
        return 0.30 + 0.40 * uniform_draw
    if model == "uniform":
        return 0.02 + 0.96 * uniform_draw
    if model == "polarized":
        if uniform_draw < 0.5:
            return 0.01 + 0.14 * (2 * uniform_draw)
        return 0.85 + 0.14 * (2 * uniform_draw - 1)
    raise ValueError(f"unknown balance model: {model}")


def network_state_from_public_sample(
    sample: PublicTopologySample,
    capacity_seed: int,
    balance_seed: int,
    balance_model: BalanceModel,
    capacity_median: int = 100_000,
    capacity_log_sigma: float = 0.85,
    capacity_minimum: int = 20_000,
    capacity_maximum: int = 1_500_000,
) -> NetworkState:
    if capacity_median <= 0 or capacity_minimum <= 0 or capacity_maximum < capacity_minimum:
        raise ValueError("invalid synthetic capacity bounds")
    capacity_rng = Random(capacity_seed + 121_000)
    balance_rng = Random(balance_seed + 122_000)
    state = NetworkState()
    for left, right, attributes in sorted(sample.graph.edges(data=True)):
        u, v = sorted((left, right))
        capacity = int(exp(log(capacity_median) + capacity_log_sigma * capacity_rng.normalvariate(0, 1)))
        capacity = max(capacity_minimum, min(capacity_maximum, capacity))
        fraction = _balance_fraction(balance_model, balance_rng.random())
        balance_uv = max(1, min(capacity - 1, int(capacity * fraction)))
        base_fee = max(0, int(attributes.get("fee_base_msat", 1_000)))
        fee_ppm = max(0, int(attributes.get("fee_proportional_millionths", 100)))
        cltv = max(0, int(attributes.get("cltv_expiry_delta", 40)))
        state.add_channel(
            Channel(
                u,
                v,
                capacity,
                balance_uv,
                base_fee_msat=base_fee,
                fee_ppm=fee_ppm,
                cltv_delta=cltv,
            )
        )
    state.assert_invariants()
    return state


def choose_hotspot_pairs(graph: nx.Graph, seed: int) -> tuple[tuple[str, str], tuple[str, str]]:
    lengths = dict(nx.all_pairs_shortest_path_length(graph))
    nonadjacent = [
        (distance, left, right)
        for left in sorted(graph.nodes())
        for right in sorted(graph.nodes())
        if left < right
        and not graph.has_edge(left, right)
        and (distance := lengths[left].get(right, 0)) >= 2
    ]
    long_pairs = [item for item in nonadjacent if item[0] >= 3]
    candidates = long_pairs if len(long_pairs) >= 2 else nonadjacent
    if len(candidates) < 2:
        raise ValueError("sample does not contain two nonadjacent hotspot pairs")
    candidates.sort(reverse=True)
    rng = Random(seed + 123_000)
    first_pool = candidates[: min(32, len(candidates))]
    _, first_left, first_right = rng.choice(first_pool)
    disjoint = [item for item in candidates if first_left not in item[1:] and first_right not in item[1:]]
    second_pool = disjoint[: min(32, len(disjoint))] or candidates[: min(32, len(candidates))]
    _, second_left, second_right = rng.choice(second_pool)
    return (first_left, first_right), (second_left, second_right)


def public_demand_stream(
    graph: nx.Graph,
    seed: int,
    steps: int,
    holdout_start: int,
    regime: DemandRegime,
    hotspot_probability: float = 0.35,
    amounts: tuple[int, ...] = (1_000, 2_000, 5_000, 8_000),
) -> tuple[list[Demand], tuple[str, str], tuple[str, str]]:
    if regime not in DEMAND_REGIMES:
        raise ValueError(f"unknown demand regime: {regime}")
    if not 0 < holdout_start < steps:
        raise ValueError("holdout_start must be inside the demand sequence")
    if not 0 <= hotspot_probability <= 1:
        raise ValueError("hotspot_probability must lie in [0, 1]")
    rng = Random(seed + 124_000)
    nodes = sorted(graph.nodes())
    first, second = choose_hotspot_pairs(graph, seed)
    demands = []
    for index in range(steps):
        use_hotspot = regime != "diffuse" and rng.random() < hotspot_probability
        if use_hotspot:
            pair = second if regime == "shifted_hotspot" and index >= holdout_start else first
            source, target = pair if rng.random() < 0.72 else pair[::-1]
        else:
            source, target = rng.sample(nodes, 2)
        demands.append(Demand(source, target, rng.choice(amounts)))
    return demands, first, second
