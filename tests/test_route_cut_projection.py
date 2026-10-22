"""Finite correspondence campaign: concrete route steps versus paper's cut ledger.

This checks the interpretation missing between SpiralFormal/Cut.lean's
abstract CutTrace and the Python NetworkState implementation. Cases include
paths that revisit channels, failed attempts, reserves, and asymmetric
initial liquidity. It is a bounded witness campaign, not a universal proof.
"""
from random import Random

import pytest

from spiral_ln.algebra import Channel, NetworkState


def cut_stocks(state: NetworkState, inside: frozenset[str]) -> tuple[int, int]:
    outbound = inbound = 0
    for channel in state.channels.values():
        if (channel.u in inside) == (channel.v in inside):
            continue
        if channel.u in inside:
            outbound += channel.balance_uv
            inbound += channel.balance_vu
        else:
            outbound += channel.balance_vu
            inbound += channel.balance_uv
    return outbound, inbound


def flow_across_cut(path: list[str], inside: frozenset[str], amount: int) -> tuple[int, int]:
    outward = inward = 0
    for u, v in zip(path, path[1:]):
        if u in inside and v not in inside:
            outward += amount
        elif u not in inside and v in inside:
            inward += amount
    return outward, inward


@pytest.mark.parametrize("seed", range(128))
def test_every_prefix_bound_and_failed_route_identity(seed: int) -> None:
    rng = Random(seed + 4400)
    nodes = ["a", "b", "c"]
    state = NetworkState()
    for u, v in (("a", "b"), ("b", "c"), ("c", "a")):
        cap = rng.randrange(35, 130)
        balance = rng.randrange(5, cap - 5)
        reserve = rng.randrange(0, 5)
        # Each endpoint's locked amount remains within its current balance.
        locked_uv = rng.randrange(0, min(4, balance) + 1)
        locked_vu = rng.randrange(0, min(4, cap - balance) + 1)
        state.add_channel(Channel(
            u, v, cap, balance, reserve=reserve,
            locked_uv=locked_uv, locked_vu=locked_vu,
        ))
    state.assert_invariants()

    # A random walk over a triangle can visit one channel several times.
    path = [rng.choice(nodes)]
    for _ in range(rng.randrange(1, 9)):
        path.append(rng.choice([n for n in nodes if n != path[-1]]))
    amount = rng.randrange(1, 60)

    before = state.clone()
    can_settle = state.route_feasible(path, amount)
    if can_settle:
        state.apply_route(path, amount)
    else:
        with pytest.raises(ValueError):
            state.apply_route(path, amount)
        for key, prior in before.channels.items():
            assert state.channels[key].balance_uv == prior.balance_uv

    assert before.total_capacity == state.total_capacity
    state.assert_invariants()

    for cut in (frozenset({"a"}), frozenset({"b"}), frozenset({"c"}),
                frozenset({"a", "b"}), frozenset({"b", "c"})):
        old_out, old_in = cut_stocks(before, cut)
        new_out, new_in = cut_stocks(state, cut)
        out, incoming = flow_across_cut(path, cut, amount)
        if not can_settle:
            out = incoming = 0
        assert new_out == old_out - out + incoming
        assert new_in == old_in - incoming + out
        # The two paper inequalities hold for this one-event prefix,
        # even when the route leaves and reenters the cut.
        assert out - incoming <= old_out
        assert incoming - out <= old_in
