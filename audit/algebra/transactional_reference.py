"""Small offline reference semantics, not a Lightning settlement implementation.

Both functions publish the completed cloned state only after every rewrite
succeeds. They preserve the caller's state on failure. This is single-process
transactional behavior, not concurrency control or a distributed atomic commit.
"""
from collections import Counter


def _validate(path, amount):
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        raise ValueError("amount must be a positive integer")
    if len(path) < 2:
        raise ValueError("a route needs at least one edge")


def apply_sequential_transaction(state, path, amount):
    """Sequential settlement: earlier edge transfers may fund later ones.

This interpretation is intentionally weaker than simultaneous HTLC reservation.
It is useful for testing rewrite composition, not for constructing LN payments.
"""
    path = tuple(path)
    _validate(path, amount)
    trial = state.clone()
    for a, b in zip(path, path[1:]):
        trial.channel(a, b).transfer(a, b, amount)
    trial.assert_invariants()
    if trial.total_capacity != state.total_capacity:
        raise AssertionError("capacity changed")
    state.channels = trial.channels


def apply_prefunded_transaction(state, path, amount):
    """Gross resource precheck followed by transactional uniform-amount rewrite.

Count repeated uses separately in each direction before any state changes.
This only models a balance-reservation constraint. It omits slots, timeout,
fees, channel identity, distributed commitment and peer behavior.
"""
    path = tuple(path)
    _validate(path, amount)
    multiplicities = Counter(zip(path, path[1:]))
    for (a, b), count in multiplicities.items():
        if count * amount > state.channel(a, b).available(a, b):
            raise ValueError("insufficient gross directional resources")
    apply_sequential_transaction(state, path, amount)
