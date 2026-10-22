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



def test_repeated_channel_infeasibility_is_atomic():
    """A route that revisits one channel cannot spend the same balance twice."""
    state = NetworkState()
    state.add_channel(Channel("a", "b", 100, 30))
    state.add_channel(Channel("b", "c", 100, 60))
    state.add_channel(Channel("c", "a", 100, 60))
    snapshot = state.clone()
    path = ("a", "b", "c", "a", "b")
    # Every hop passes the *initial* balance check, but a->b is spent twice.
    assert not state.route_feasible(path, 20)
    with pytest.raises(ValueError, match="infeasible|insufficient"):
        state.apply_route(path, 20)
    for edge, ch in state.channels.items():
        assert ch.balance_uv == snapshot.channels[edge].balance_uv
    state.assert_invariants()


def test_repeated_channel_route_can_reuse_liquidity_after_return():
    """An incoming hop may restore balance for a later legitimate outgoing hop."""
    state = NetworkState()
    state.add_channel(Channel("a", "b", 100, 20))
    path = ("a", "b", "a", "b")
    assert state.route_feasible(path, 20)
    state.apply_route(path, 20)
    assert state.channel("a", "b").balance_uv == 0
    state.assert_invariants()


def test_zero_and_negative_payment_not_feasible():
    state = NetworkState()
    state.add_channel(Channel("a", "b", 100, 50))
    assert not state.route_feasible(("a", "b"), 0)
    assert not state.route_feasible(("a", "b"), -1)
