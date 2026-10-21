"""Exact finite witnesses for the October 2026 mathematical review.

Run from the repository root with Python 3. This script uses no network or
external packages. It writes JSON to stdout and verifies every reported claim.
"""

import copy
import hashlib
import hmac
import itertools
import json


def routing_witness():
    nodes = ("s", "a", "b", "t")
    # Every public capacity is 2. Values are the directional balances at endpoints.
    initial = {("s", "a"): [2, 0], ("a", "t"): [1, 1],
               ("s", "b"): [1, 1], ("b", "t"): [1, 1]}

    def edge(state, u, v):
        if (u, v) in state:
            return state[(u, v)], 0
        if (v, u) in state:
            return state[(v, u)], 1
        return None, None

    def stock(state, cut):
        return sum(bal[0 if u in cut else 1] for (u, v), bal in state.items()
                   if (u in cut) != (v in cut))

    def feasible(state, path, amount):
        for u, v in zip(path, path[1:]):
            bal, side = edge(state, u, v)
            if bal is None or bal[side] < amount:
                return False
        return True

    def all_paths(source, target):
        middle = tuple(n for n in nodes if n not in (source, target))
        for length in range(len(middle) + 1):
            for body in itertools.permutations(middle, length):
                yield (source,) + body + (target,)

    def run(first):
        state = copy.deepcopy(initial)
        settled = []
        cuts_checked = 0

        def settle(path, amount):
            nonlocal cuts_checked
            assert feasible(state, path, amount)
            for u, v in zip(path, path[1:]):
                bal, side = edge(state, u, v)
                bal[side] -= amount
                bal[1 - side] += amount
            settled.append((path, amount))
            for size in range(1, len(nodes)):
                for members in itertools.combinations(nodes, size):
                    cut = set(members)
                    outward = inward = 0
                    for route, value in settled:
                        for u, v in zip(route, route[1:]):
                            outward += value * (u in cut and v not in cut)
                            inward += value * (u not in cut and v in cut)
                    assert stock(state, cut) == stock(initial, cut) - outward + inward
                    assert outward - inward <= stock(initial, cut)
                    cuts_checked += 1

        settle(first, 1)
        # The next 2-unit payment is single-path, as in the paper's setting.
        available = [p for p in all_paths("s", "a") if feasible(state, p, 2)]
        if available:
            settle(available[0], 2)
        return {"first_path": first, "first_payment_succeeded": True,
                "second_feasible_paths": available, "payments_delivered": len(settled),
                "cut_prefix_checks": cuts_checked}

    blocked = run(("s", "a", "t"))
    delivered = run(("s", "b", "t"))
    assert blocked["payments_delivered"] == 1
    assert delivered["payments_delivered"] == 2
    assert blocked["second_feasible_paths"] == []
    return {"scope": "same initial state and one route attempt per payment; single-path requests",
            "initial_directional_balances": {"-".join(k): v for k, v in initial.items()},
            "consume_future_route": blocked, "preserve_future_route": delivered,
            "implication": "cut conservation does not imply equal future routability or an attempt-budget-only gain"}


def multi_authority_nullifier_witness():
    # Both keys satisfy one object's authority predicate, e.g. alternate permitted paths.
    object_id, value = "object-1", 100
    valid_keys = (b"allowed-key-a", b"allowed-key-b")
    nullifiers = [hmac.new(k, object_id.encode(), hashlib.sha256).hexdigest() for k in valid_keys]
    assert len(set(nullifiers)) == 2
    return {"object_value": value, "valid_authority_credentials": len(valid_keys),
            "distinct_nullifiers": len(set(nullifiers)), "accepted_weight_under_naive_relation": value * len(nullifiers),
            "implication": "the theorem requires one canonical nullifier credential for each eligible object"}


def stock_flow_witness():
    budget, outstanding, fronted, recovered = 10, 0, 0, 0
    for _ in range(2):
        assert 10 <= budget - outstanding
        fronted += 10
        outstanding += 10
        assert outstanding <= budget
        recovered += 10
        outstanding -= 10
    assert outstanding == fronted - recovered == 0
    assert fronted > budget - outstanding
    return {"fronting_reserve": budget, "cumulative_fronted": fronted,
            "cumulative_recovered": recovered, "outstanding": outstanding,
            "implication": "the capacity bound is pointwise on outstanding fronting, not cumulative allocations"}


if __name__ == "__main__":
    print(json.dumps({"routing": routing_witness(), "nullifier_authority": multi_authority_nullifier_witness(),
                      "stock_flow": stock_flow_witness()}, indent=2))
