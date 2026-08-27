import networkx as nx

from spiral_ln.public_topology import PublicTopologySample
from spiral_ln.public_topology_eval import (
    FailedDemandTracker,
    PathCatalog,
    PublicTopologyEvalConfig,
    TerminalFeedbackAgent,
    choose_capital_connector,
    execute_payment,
    run_episode,
)
from spiral_ln.simulator import Demand
from spiral_ln.public_topology import network_state_from_public_sample


def _sample() -> PublicTopologySample:
    graph = nx.cycle_graph(18)
    graph.add_edges_from((index, (index + 4) % 18) for index in range(0, 18, 3))
    graph = nx.relabel_nodes(graph, {node: f"N{node:03d}" for node in graph})
    return PublicTopologySample(graph, "test-sample", "random", "a", "b")


def _config() -> PublicTopologyEvalConfig:
    return PublicTopologyEvalConfig(
        topology_sample_count=2,
        calibration_sample_count=1,
        balance_draws=1,
        node_count=18,
        steps=40,
        evaluation_start=20,
        early_evaluation_steps=5,
    )


def test_terminal_feedback_agent_never_stores_hidden_state():
    agent = TerminalFeedbackAgent(5_000)
    path = ("N000", "N001", "N002")
    agent.observe(path, False)
    assert agent.trials[("N000", "N001")] == 1
    assert agent.failures[("N001", "N002")] == 1
    assert not hasattr(agent, "balances")
    assert not hasattr(agent, "network")
    assert agent.rank((path,), {path: 2_000}) == [path]


def test_oracle_does_not_emit_infeasible_probe_attempts():
    sample = _sample()
    state = network_state_from_public_sample(sample, 1, 2, "polarized")
    catalog = PathCatalog(sample.graph, 8)
    agent = TerminalFeedbackAgent(5_000)
    demand = Demand("N000", "N009", 10_000_000)
    delivered, _, failures = execute_payment(state, demand, "oracle", catalog, agent, 3)
    assert not delivered
    assert failures == 0


def test_failure_aware_capital_uses_observed_failed_pair():
    sample = _sample()
    state = network_state_from_public_sample(sample, 1, 2, "uniform")
    tracker = FailedDemandTracker()
    demand = Demand("N000", "N009", 1_000)
    for _ in range(5):
        tracker.observe(demand, False)
    connector = choose_capital_connector(state, "failure_aware", tracker, 1, 120_000, 0.2)
    assert connector is not None
    assert frozenset(connector.endpoints) == frozenset(("N000", "N009"))


def test_public_episode_is_deterministic_and_sealed():
    sample = _sample()
    config = _config()
    left = run_episode(sample, 1, 0, "uniform", "shifted_hotspot", "online", "failure_aware", config)
    right = run_episode(sample, 1, 0, "uniform", "shifted_hotspot", "online", "failure_aware", config)
    assert left == right
    assert left.evaluation_split == "sealed_holdout"
    assert left.training.attempted == config.evaluation_start
    assert left.evaluation.attempted == config.steps - config.evaluation_start
    assert left.connector_capital == config.connector_capital
