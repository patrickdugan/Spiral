from spiral_ln.placement_boundary_eval import (
    PlacementBoundaryConfig,
    hotspot_demand_stream,
    isolate_hotspot_endpoints,
    run_episode,
    summarize,
)
from spiral_ln.simulator import two_cluster_state


def _config() -> PlacementBoundaryConfig:
    return PlacementBoundaryConfig(
        seed_count=1,
        steps=40,
        warmup_steps=10,
        hotspot_probabilities=(0.0, 0.75),
        isolation_fractions=(0.0, 0.9),
    )


def test_hotspot_stream_is_deterministic_and_bounded():
    left = hotspot_demand_stream(3, 20, 1.0, "A7", "B7")
    right = hotspot_demand_stream(3, 20, 1.0, "A7", "B7")
    assert left == right
    assert all((demand.source, demand.target) == ("A7", "B7") for demand in left)


def test_isolation_preserves_network_invariants():
    state = two_cluster_state(2)
    isolate_hotspot_endpoints(state, ("A7", "B7"), 0.95)
    state.assert_invariants()
    assert any(
        channel.locked_uv or channel.locked_vu
        for channel in state.channels.values()
        if "A7" in (channel.u, channel.v) or "B7" in (channel.u, channel.v)
    )


def test_equal_budget_episode_is_deterministic():
    config = _config()
    left = run_episode(6, "demand_aware", 0.75, 0.9, config)
    right = run_episode(6, "demand_aware", 0.75, 0.9, config)
    random = run_episode(6, "random", 0.75, 0.9, config)
    assert left == right
    assert left.connector_capital == random.connector_capital == config.connector_capital
    assert left.attempted == config.steps - config.warmup_steps


def test_phase_summary_uses_familywise_intervals():
    config = _config()
    rows = [
        run_episode(1, policy, hotspot, isolation, config)
        for policy in ("none", "random", "demand_aware")
        for hotspot in config.hotspot_probabilities
        for isolation in config.isolation_fractions
    ]
    summary = summarize(rows, config)
    assert "Bonferroni" in summary["design"]["familywise_correction"]
    assert all(
        "familywise_half_width" in cell["demand_minus_random_success"]
        for cell in summary["phase_cells"]
    )
