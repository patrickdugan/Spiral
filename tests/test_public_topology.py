import networkx as nx

from spiral_ln.public_topology import (
    PublicTopologySample,
    choose_hotspot_pairs,
    network_state_from_public_sample,
    public_demand_stream,
    sample_connected_subgraph,
)


def _graph() -> nx.Graph:
    graph = nx.cycle_graph(24)
    graph.add_edges_from((index, (index + 5) % 24) for index in range(0, 24, 3))
    return nx.relabel_nodes(graph, {node: f"P{node:02d}" for node in graph})


def test_public_subgraph_sampling_is_deterministic_connected_and_anonymized():
    graph = _graph()
    left = sample_connected_subgraph(graph, 4, node_count=16, mode="random")
    right = sample_connected_subgraph(graph, 4, node_count=16, mode="random")
    assert left.sample_id == right.sample_id
    assert set(left.graph) == set(right.graph)
    assert nx.is_connected(left.graph)
    assert all(node.startswith("N") for node in left.graph)


def test_hidden_balance_models_keep_topology_and_capacity_paired():
    sampled = sample_connected_subgraph(_graph(), 2, node_count=16, mode="hub")
    balanced = network_state_from_public_sample(sampled, 8, 9, "balanced_band")
    polarized = network_state_from_public_sample(sampled, 8, 9, "polarized")
    assert set(balanced.channels) == set(polarized.channels)
    assert balanced.total_capacity == polarized.total_capacity
    assert any(
        balanced.channels[key].balance_uv != polarized.channels[key].balance_uv
        for key in balanced.channels
    )
    balanced.assert_invariants()
    polarized.assert_invariants()


def test_shifted_demand_changes_only_after_holdout_boundary():
    sample = sample_connected_subgraph(_graph(), 7, node_count=18, mode="periphery")
    demands, first, second = public_demand_stream(
        sample.graph,
        seed=5,
        steps=20,
        holdout_start=10,
        regime="shifted_hotspot",
        hotspot_probability=1.0,
    )
    assert first != second
    assert all({demand.source, demand.target} == set(first) for demand in demands[:10])
    assert all({demand.source, demand.target} == set(second) for demand in demands[10:])


def test_hotspots_fall_back_to_distance_two_on_diameter_two_graph():
    graph = nx.relabel_nodes(nx.star_graph(15), lambda node: f"N{node:03d}")
    first, second = choose_hotspot_pairs(graph, seed=3)
    assert first != second
    assert all(not graph.has_edge(*pair) for pair in (first, second))
    assert all(nx.shortest_path_length(graph, *pair) == 2 for pair in (first, second))
