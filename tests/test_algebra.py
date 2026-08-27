import pytest

from spiral_ln.algebra import (
    Channel,
    ConnectorKind,
    GhostPlan,
    NetworkState,
)


def test_payment_rewrite_conserves_capacity_and_channel_sum():
    state = NetworkState()
    state.add_channel(Channel("a", "b", 100, 70))
    state.add_channel(Channel("b", "c", 100, 60))
    before = state.total_capacity
    state.apply_route(("a", "b", "c"), 20)
    assert state.total_capacity == before
    assert state.channel("a", "b").balance("a", "b") == 50
    assert state.channel("b", "c").balance("b", "c") == 40
    state.assert_invariants()


def test_infeasible_route_is_atomic():
    state = NetworkState()
    state.add_channel(Channel("a", "b", 100, 70))
    state.add_channel(Channel("b", "c", 100, 10))
    snapshot = state.clone()
    with pytest.raises(ValueError):
        state.apply_route(("a", "b", "c"), 20)
    assert state.channel("a", "b").balance_uv == snapshot.channel("a", "b").balance_uv


def test_ghost_plan_compiles_with_positive_bond():
    plan = GhostPlan("g1", "a", "z", 100_000, ConnectorKind.LEASED, 12, 0.01)
    connector = plan.compile()
    assert connector.amount == 100_000
    assert connector.bond == 22_000
    assert connector.expiry_step == 12

