from dataclasses import asdict
import sys

import pytest

sys.path.insert(0, "C:/projects/Spiral/src")
from spiral_ln.algebra import Channel, NetworkState
from transactional_reference import apply_prefunded_transaction, apply_sequential_transaction


def triangle(capacity):
    state = NetworkState()
    for a, b in (("A", "B"), ("B", "C"), ("C", "A")):
        state.add_channel(Channel(a, b, capacity, capacity))
    return state


def snapshot(state):
    return [asdict(c) for c in state.channels.values()]


@pytest.mark.parametrize("transaction", [apply_sequential_transaction, apply_prefunded_transaction])
def test_exhaustive_repeated_walk_rollback_and_acceptance(transaction):
    for capacity in range(1, 13):
        for amount in range(1, capacity + 1):
            for repetitions in range(1, 5):
                state = triangle(capacity)
                old = snapshot(state)
                walk = ("A",) + ("B", "C", "A") * repetitions
                if amount * repetitions > capacity:
                    with pytest.raises(ValueError):
                        transaction(state, walk, amount)
                    assert snapshot(state) == old
                else:
                    transaction(state, walk, amount)
                    assert all(c.balance_uv == capacity - amount * repetitions for c in state.channels.values())
                state.assert_invariants()


def test_sequential_and_prefunded_are_not_equivalent():
    state = NetworkState()
    state.add_channel(Channel("A", "B", 100, 100))
    old = snapshot(state)
    with pytest.raises(ValueError):
        apply_prefunded_transaction(state, ("A", "B", "A"), 60)
    assert snapshot(state) == old
    apply_sequential_transaction(state, ("A", "B", "A"), 60)
    assert snapshot(state) == old


@pytest.mark.parametrize("transaction", [apply_sequential_transaction, apply_prefunded_transaction])
def test_missing_edge_preserves_snapshot(transaction):
    state = triangle(100)
    old = snapshot(state)
    with pytest.raises(KeyError):
        transaction(state, ("A", "B", "missing"), 60)
    assert snapshot(state) == old


@pytest.mark.parametrize("transaction", [apply_sequential_transaction, apply_prefunded_transaction])
@pytest.mark.parametrize("amount", [0, -1, 0.5, True])
def test_invalid_amount_preserves_snapshot(transaction, amount):
    state = triangle(100)
    old = snapshot(state)
    with pytest.raises(ValueError):
        transaction(state, ("A", "B", "C"), amount)
    assert snapshot(state) == old
