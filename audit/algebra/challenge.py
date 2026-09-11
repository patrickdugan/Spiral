"""Offline, bounded falsification tests of Connector Calculus (no network I/O).

The source under examination is imported unmodified. Results are observations,
not production Lightning protocol validation or estimates of population rates.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import sys
import time


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(source_root):
    sys.path.insert(0, str(source_root / "src"))
    from spiral_ln.algebra import (
        Channel, Connector, ConnectorKind, GhostPlan, NetworkState,
        apply_connector,
    )
    from spiral_ln.bonding import RewardClaim, sybil_invariant_rewards

    def snapshot(state):
        return [asdict(c) for c in sorted(state.channels.values(), key=lambda c: (c.u, c.v))]

    def triangle(capacity):
        state = NetworkState()
        for a, b in (("A", "B"), ("B", "C"), ("C", "A")):
            state.add_channel(Channel(a, b, capacity, capacity))
        return state

    chronology = []

    def event(label):
        chronology.append({"utc": datetime.now(timezone.utc).isoformat(), "event": label})

    event("Begin repeated-cycle prevalidation and rollback challenge")
    state = triangle(100)
    route = ("A", "B", "C", "A", "B", "C", "A")
    connector = Connector("repeated-cycle", ConnectorKind.CIRCULAR, route, 60)
    before = snapshot(state)
    precheck = state.route_feasible(route, 60)
    error = None
    try:
        apply_connector(state, connector)
    except ValueError as exc:
        error = str(exc)
    after = snapshot(state)
    state.assert_invariants()
    assert precheck and error and before != after
    counts = {"cases": 0, "prevalidated": 0, "successes": 0, "rejected_after_mutation": 0}
    for capacity in range(1, 13):
        for amount in range(1, capacity + 1):
            for repetitions in range(1, 5):
                candidate = triangle(capacity)
                walk = ("A",) + ("B", "C", "A") * repetitions
                counts["cases"] += 1
                assert candidate.route_feasible(walk, amount)
                counts["prevalidated"] += 1
                old = snapshot(candidate)
                try:
                    candidate.apply_route(walk, amount)
                    counts["successes"] += 1
                    assert repetitions * amount <= capacity
                except ValueError:
                    assert repetitions * amount > capacity
                    assert snapshot(candidate) != old
                    counts["rejected_after_mutation"] += 1
                candidate.assert_invariants()
    atomicity = {"classification": "implementation counterexample to unconditional atomic rejection for accepted closed walks",
                 "route": route, "amount": 60, "precheck": precheck, "error": error,
                 "before": before, "after": after, "exhaustive_small_grid": counts,
                 "limitation": "Public-topology routing enumerates simple paths, so this does not by itself invalidate its delivery rows."}

    event("Test final-state polytope membership against pre-funded route feasibility")
    state = NetworkState()
    state.add_channel(Channel("A", "B", 100, 100))
    path = ("A", "B", "A")
    q = 60
    net_delta = -q + q
    in_polytope = 0 <= state.channel("A", "B").balance_uv + net_delta <= 100
    precheck = state.route_feasible(path, q)
    assert in_polytope and not precheck
    vector_feasibility = {
        "classification": "domain counterexample: net final-state admissibility is insufficient for arbitrary closed walks",
        "route": path, "amount": q, "net_delta": net_delta,
        "initial_forward": 100, "initial_reverse": 0,
        "final_state_in_polytope": in_polytope, "reference_precheck": precheck,
        "reservation_gross_forward": q, "reservation_gross_reverse": q,
        "explanation": "A net-zero rewrite hides a reverse-direction resource requirement. Sequential settlement could replenish it, but simultaneous pre-funded reservation cannot; the paper must choose semantics."}

    event("Test horizon cut demand versus instantaneous stock with reverse replenishment")
    def cut_episode(sequence):
        state = NetworkState()
        state.add_channel(Channel("A", "B", 100, 50))
        rows = []
        out = incoming = failures = 0
        for step, (src, dst, q) in enumerate(sequence):
            old = state.channel("A", "B").balance_uv
            ok = state.route_feasible((src, dst), q)
            if ok:
                state.apply_route((src, dst), q)
                if src == "A":
                    out += q
                else:
                    incoming += q
            else:
                failures += 1
            current = state.channel("A", "B").balance_uv
            assert current == 50 - out + incoming
            rows.append({"step": step, "src": src, "dst": dst, "amount": q,
                         "before_outbound_stock": old, "delivered": ok,
                         "after_outbound_stock": current})
        return {"initial_outbound_stock": 50, "demanded_outward": sum(q for s, _, q in sequence if s == "A"),
                "demanded_inward": sum(q for s, _, q in sequence if s == "B"),
                "delivered_outward": out, "delivered_inward": incoming,
                "failures": failures, "trajectory": rows}
    alternating = cut_episode([("A", "B", 40), ("B", "A", 40)] * 5)
    blocked_order = cut_episode([("A", "B", 40)] * 5 + [("B", "A", 40)] * 5)
    assert alternating["delivered_outward"] == 200 and alternating["failures"] == 0
    assert blocked_order["failures"] > 0
    cut = {"classification": "ambiguous mathematical premise; false for gross demand, salvageable with net replenishment and prefix constraints",
           "alternating": alternating, "same_totals_different_order": blocked_order,
           "correct_inventory_identity": "Q_A(t)=Q_A(0)-F_out(0,t)+F_in(0,t), absent fees, locks and capital changes",
           "necessary_prefix_condition": "0 <= Q_A(0)-F_out(0,t)+F_in(0,t) <= total_cut_capacity for every prefix t; not sufficient for multihop routing."}

    event("Test declared compilation guards and lease retention")
    first = GhostPlan("same-exposure", "A", "B", 100, ConnectorKind.LEASED, 1, 0.0).compile()
    second = GhostPlan("same-exposure", "C", "D", 100, ConnectorKind.LEASED, 1, 0.0).compile()
    state = NetworkState()
    apply_connector(state, first)
    apply_connector(state, second)
    assert first.capital_id == second.capital_id and state.total_capacity == 200
    direct_state = NetworkState()
    for connector_id, endpoints in (("unique-plan-1", ("A", "B")), ("unique-plan-2", ("C", "D"))):
        apply_connector(direct_state, Connector(connector_id, ConnectorKind.TOPOLOGICAL,
                                              endpoints, 100, bond=10, capital_id="one-exposure"))
    assert direct_state.total_capacity == 200
    unbonded = Connector("unbonded", ConnectorKind.TOPOLOGICAL, ("E", "F"), 100, bond=0, capital_id=None)
    apply_connector(state, unbonded)
    expired = Connector("negative-expiry", ConnectorKind.LEASED, ("G", "H"), 100, bond=0, expiry_step=-1)
    apply_connector(state, expired)
    assert state.total_capacity == 400
    compile_guard = {
        "classification": "specification/implementation gap, not a contradiction of an abstract Compile defined to require its predicates",
        "first": asdict(first), "second": asdict(second), "duplicate_capital_capacity": 200,
        "distinct_connector_ids_same_capital_capacity": direct_state.total_capacity,
        "unbonded_connector_accepted": True, "negative_expiry_connector_accepted": True,
        "final_total_capacity": state.total_capacity,
        "facts": ["GhostPlan.compile has no state, funding, consent or exposure-registry argument.",
                  "NetworkState retains channels only; apply_connector discards bond, expiry and capital_id.",
                  "No time progression is claimed here: there is no lease-expiry transition to exercise."]}

    event("Test fee-aware boundary as acknowledged model omission, not theorem falsification")
    state = NetworkState()
    state.add_channel(Channel("A", "B", 2000, 1000, base_fee_msat=1000, fee_ppm=0))
    state.add_channel(Channel("B", "C", 2000, 1000, base_fee_msat=1000, fee_ppm=0))
    q_sat = 1000
    forward_fee_msat = state.channel("B", "C").fee_msat(q_sat)
    required_upstream_msat = q_sat * 1000 + forward_fee_msat
    assert state.route_feasible(("A", "B", "C"), q_sat)
    assert state.channel("A", "B").available("A", "B") * 1000 < required_upstream_msat
    fee_boundary = {
        "classification": "explicitly acknowledged idealization with discrete reachability consequence",
        "delivered_sat": q_sat, "forwarder_fee_msat": forward_fee_msat,
        "upstream_available_msat": 1000000, "upstream_required_msat": required_upstream_msat,
        "uniform_amount_feasible": True, "fee_adjusted_feasible": False,
        "note": "Only a two-edge fee recursion is used; no claim of complete BOLT semantics or empirically common boundary cases."}

    event("Run champion controls: valid simple-path invariants and fixed-exposure identity splits")
    rng = random.Random(20260911)
    for _ in range(2000):
        state = NetworkState()
        balances = []
        length = rng.randint(1, 7)
        for edge in range(length):
            cap = rng.randint(10, 10000)
            bal = rng.randint(1, cap)
            balances.append(bal)
            state.add_channel(Channel(str(edge), str(edge + 1), cap, bal))
        q = rng.randint(1, min(balances))
        old_capacity = state.total_capacity
        state.apply_route(tuple(str(i) for i in range(length + 1)), q)
        state.assert_invariants()
        assert state.total_capacity == old_capacity
    rewards = []
    for identities in (1, 2, 4, 8, 16, 32, 64):
        claims = [RewardClaim(f"challenger-{i}", "capital-A", 100000, 0.9) for i in range(identities)]
        claims += [RewardClaim("other", "capital-B", 200000, 0.5)]
        allocation = sybil_invariant_rewards(claims, 100003)
        reward = sum(value for key, value in allocation.items() if key.startswith("challenger-"))
        rewards.append({"identities": identities, "coalition_reward": reward})
        assert sum(allocation.values()) == 100003
    assert len({r["coalition_reward"] for r in rewards}) == 1
    event("Cross-examination requested a corrected separate transactional reference; test both sequential and gross-prefunded semantics")
    from transactional_reference import apply_prefunded_transaction, apply_sequential_transaction
    transactional_results = {}
    for transaction in (apply_sequential_transaction, apply_prefunded_transaction):
        corrected_counts = {"cases": 0, "successes": 0, "rejected_unchanged": 0, "partial_rejections": 0}
        for capacity in range(1, 13):
            for amount in range(1, capacity + 1):
                for repetitions in range(1, 5):
                    candidate = triangle(capacity)
                    old = snapshot(candidate)
                    walk = ("A",) + ("B", "C", "A") * repetitions
                    corrected_counts["cases"] += 1
                    try:
                        transaction(candidate, walk, amount)
                        assert repetitions * amount <= capacity
                        corrected_counts["successes"] += 1
                    except ValueError:
                        assert repetitions * amount > capacity
                        assert snapshot(candidate) == old
                        corrected_counts["rejected_unchanged"] += 1
                    candidate.assert_invariants()
        transactional_results[transaction.__name__] = corrected_counts
    event("All expected counterexamples and champion controls observed; source unmodified")
    sources = ["paper/manuscript.md", "src/spiral_ln/algebra.py", "src/spiral_ln/bonding.py"]
    return {
        "schema": "spiral.algebra_challenge.v1", "scope": "offline toy witnesses against unmodified reference code",
        "source_root": str(source_root),
        "source_sha256": {name: fingerprint(source_root / name) for name in sources},
        "script_sha256": fingerprint(Path(__file__)),
        "reference_sha256": fingerprint(Path(__file__).with_name("transactional_reference.py")),
        "chronology": chronology,
        "challenges": {"A1_repeated_walk_atomicity": atomicity, "A2_net_vector_feasibility": vector_feasibility,
                       "A3_cut_stock_flow": cut, "A4_compilation_guards": compile_guard,
                       "A5_fee_boundary": fee_boundary},
        "champion_controls": {"simple_path_invariant_runs": 2000, "simple_path_failures": 0,
                              "identity_split_results": rewards},
        "separate_transactional_reference": transactional_results,
        "interpretation": {"rates": "Exhaustive small adversarial grid is not a representative population frequency.",
                           "prior_campaigns": "No counterexample here changes prior output CSVs; public routing uses simple paths.",
                           "testnet": "This file performs no testnet or network operation; root's chain observer is separate."}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=Path("C:/projects/Spiral"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("results.json"))
    args = parser.parse_args()
    started = time.monotonic()
    result = run(args.source_root)
    result["runtime_seconds"] = time.monotonic() - started
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "runtime_seconds": result["runtime_seconds"],
                      "atomicity_grid": result["challenges"]["A1_repeated_walk_atomicity"]["exhaustive_small_grid"],
                      "control_runs": result["champion_controls"]["simple_path_invariant_runs"]}, indent=2))


if __name__ == "__main__":
    main()
