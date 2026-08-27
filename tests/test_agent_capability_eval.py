from dataclasses import replace

from spiral_ln.agent_capability_eval import (
    CONNECTOR_POLICIES,
    KNOWLEDGE_LEVELS,
    STRESS_LEVELS,
    AgentCapabilityConfig,
    choose_equal_budget_random_connector,
    choose_observed_demand_connector,
    run_episode,
    summarize,
)
from spiral_ln.simulator import Demand, two_cluster_state


def _small_config() -> AgentCapabilityConfig:
    return AgentCapabilityConfig(seed_count=1, steps=48, warmup_steps=12, stress_start=24)


def test_episode_is_deterministic_and_complete():
    config = _small_config()
    left = run_episode(4, "adaptive", "demand_aware", "jammed", config)
    right = run_episode(4, "adaptive", "demand_aware", "jammed", config)
    assert left == right
    assert left.total.attempted == config.steps
    assert left.connector_capital == config.connector_capital


def test_oracle_and_adaptive_share_delivery_ceiling_but_oracle_leaks_less():
    config = _small_config()
    adaptive = run_episode(8, "adaptive", "none", "jammed", config)
    oracle = run_episode(8, "oracle", "none", "jammed", config)
    assert oracle.total.succeeded == adaptive.total.succeeded
    assert oracle.total.delivered_volume == adaptive.total.delivered_volume
    assert oracle.total.failed_route_attempts <= adaptive.total.failed_route_attempts


def test_connector_planners_receive_equal_capital_and_avoid_existing_edges():
    state = two_cluster_state(3)
    observed = [Demand("A1", "B2", 1_000)] * 8 + [Demand("A3", "B4", 1_000)]
    demand = choose_observed_demand_connector(state, observed, 120_000)
    random = choose_equal_budget_random_connector(state, 3, 120_000)
    assert demand.amount == random.amount == 120_000
    assert frozenset(demand.endpoints) not in state.channels
    assert frozenset(random.endpoints) not in state.channels
    assert demand.endpoints == ("A1", "B2")


def test_demand_planner_depends_only_on_passed_warmup_demands():
    state = two_cluster_state(5)
    warmup = [Demand("A2", "B3", 2_000)] * 5
    first = choose_observed_demand_connector(state, warmup, 120_000)
    future = [Demand("A7", "B7", 8_000)] * 100
    second = choose_observed_demand_connector(state, list(warmup), 120_000)
    assert future
    assert first == second


def test_validation_rejects_noncausal_timing():
    config = _small_config()
    try:
        replace(config, warmup_steps=24)
    except ValueError as error:
        assert "warmup_steps" in str(error)
    else:
        raise AssertionError("noncausal timing should be rejected")


def test_factorial_summary_includes_causal_interactions():
    config = _small_config()
    rows = [
        run_episode(2, knowledge, connector, stress, config)
        for knowledge in KNOWLEDGE_LEVELS
        for connector in CONNECTOR_POLICIES
        for stress in STRESS_LEVELS
    ]
    summary = summarize(rows, config)
    contrasts = summary["paired_contrasts"]
    assert "information_capital_complement_under_jam" in contrasts
    assert "capital_reduction_in_jam_penalty" in contrasts
    assert summary["design"]["equal_connector_capital"]
