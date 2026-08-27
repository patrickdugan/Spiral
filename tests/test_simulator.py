from spiral_ln.simulator import run_simulation, two_cluster_state


def test_synthetic_state_is_valid():
    state = two_cluster_state(3)
    state.assert_invariants()
    assert len(state.nodes) == 16
    assert state.total_capacity > 0


def test_simulation_is_deterministic():
    left = run_simulation(4, "ghost_connector")
    right = run_simulation(4, "ghost_connector")
    assert left == right


def test_ghost_connector_adds_bounded_capital():
    result = run_simulation(5, "ghost_connector")
    assert result.connector_capital in (0, 120_000)

