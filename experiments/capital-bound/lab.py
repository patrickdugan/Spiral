#!/usr/bin/env python3
"""Offline Capital Bound lab. This program never connects to a node or signs funds."""
from __future__ import annotations

import argparse
import itertools
import json
from collections import Counter
from fractions import Fraction
from pathlib import Path

EVIDENCE = {"simulation", "native_regtest", "public_testnet4"}
STATES = {"available", "unavailable", "pending_recovery", "released"}
ENCUMBERED = {"unavailable", "pending_recovery"}


def exact_int(x, name, minimum=0):
    if type(x) is not int or x < minimum:
        raise ValueError(f"{name} must be an exact integer >= {minimum}")
    return x


def name(x, field):
    if not isinstance(x, str) or not x.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return x


class Diamond:
    nodes = ("s", "a", "b", "t")
    edges = (("s", "a"), ("a", "t"), ("s", "b"), ("b", "t"))

    def __init__(self):
        self.initial = {}
        for u, v in self.edges:
            self.initial[u, v] = 2
            self.initial[v, u] = 0
        self.balance = self.initial.copy()
        self.transfers = []
        self.cut_checks = 0
        self.check_cuts()

    def paths(self, source, target, amount):
        found = []

        def visit(path):
            if path[-1] == target:
                found.append(path)
                return
            for v in self.nodes:
                if v not in path and self.balance.get((path[-1], v), 0) >= amount:
                    visit(path + [v])

        visit([source])
        return found

    def pay(self, path, amount):
        exact_int(amount, "payment amount", 1)
        if len(path) != len(set(path)) or len(path) < 2:
            raise ValueError("expected a simple path")
        pairs = list(zip(path, path[1:]))
        if any(self.balance.get(edge, 0) < amount for edge in pairs):
            return False
        for u, v in pairs:
            self.balance[u, v] -= amount
            self.balance[v, u] += amount
        self.transfers.append((path, amount))
        self.check_cuts()
        return True

    def check_cuts(self):
        for size in range(1, len(self.nodes)):
            for subset in itertools.combinations(self.nodes, size):
                a = set(subset)
                initial_stock = sum(x for (u, v), x in self.initial.items() if u in a and v not in a)
                stock = sum(x for (u, v), x in self.balance.items() if u in a and v not in a)
                outgoing = incoming = 0
                for path, amount in self.transfers:
                    for u, v in zip(path, path[1:]):
                        outgoing += amount * (u in a and v not in a)
                        incoming += amount * (u not in a and v in a)
                if stock != initial_stock - outgoing + incoming or stock < 0:
                    raise AssertionError(f"cut conservation failed: {subset}")
                self.cut_checks += 1

    def state(self):
        return {f"{u}->{v}": x for (u, v), x in sorted(self.balance.items())}


def counterexample():
    poor = Diamond()
    assert poor.pay(["s", "a", "t"], 1)
    after_first = poor.state()
    routes = poor.paths("a", "t", 2)
    assert not routes
    # There are no admissible simple paths. Retrying unchanged state cannot help.
    assert poor.pay(["a", "t"], 1)
    assert poor.pay(["a", "s", "b", "t"], 1)
    better = Diamond()
    assert better.pay(["s", "b", "t"], 1)
    assert better.pay(["a", "t"], 2)
    return {
        "evidence_level": "simulation",
        "assumptions": ["integer amounts", "zero fees", "sequential requests", "no capacity changes", "atomic simple-path payments"],
        "initial_capacity": {f"{u}->{v}": x for (u, v), x in poor.initial.items()},
        "requests": [{"source": "s", "target": "t", "amount": 1}, {"source": "a", "target": "t", "amount": 2}],
        "first_route_via_a": {"state_after_first": after_first, "second_payment_admissible_paths": routes, "unsplit_settled_payments": 1, "retry_limit": "any finite or infinite unchanged-state retry budget"},
        "first_route_via_b": {"unsplit_settled_payments": 2, "final_state": better.state()},
        "mpp_rescue_after_route_a": {"parts": [{"path": ["a", "t"], "amount": 1}, {"path": ["a", "s", "b", "t"], "amount": 1}], "final_state": poor.state()},
        "all_cut_conservation": {"passed": True, "nontrivial_cuts_per_state": 14, "checked_cut_state_pairs": poor.cut_checks + better.cut_checks},
        "conclusion": "The conservation bound survives routing choice; single-path deliverability can still depend on earlier route selection.",
    }


def ratio(numerator, denominator):
    if denominator == 0:
        return None
    r = Fraction(numerator, denominator)
    return {"numerator": r.numerator, "denominator": r.denominator, "decimal": float(r)}


def analyze(records):
    if not records or records[0].get("kind") != "run_start":
        raise ValueError("first record must be run_start")
    first = records[0]
    level = first.get("evidence_level")
    if level not in EVIDENCE:
        raise ValueError("unsupported evidence_level")
    name(first.get("run_id"), "run_id")
    start_h = last_h = exact_int(first.get("height"), "height")
    start_t = last_t = exact_int(first.get("time_s"), "time_s")
    lots, reserves, offered, settled, fees = {}, set(), {}, {}, {}
    used_lot_ids, replacements = set(), []
    integral = {"encumbered_sat_blocks": 0, "encumbered_sat_seconds": 0,
                "funded_sat_blocks": 0, "funded_sat_seconds": 0}
    peak_encumbered = peak_funded = 0
    failed_attempts = 0
    ended = False

    def stocks():
        committed = sum(x["amount_sat"] for x in lots.values() if x["state"] in ENCUMBERED)
        funded = sum(x["amount_sat"] for x in lots.values() if x["state"] != "released")
        return committed, funded

    for i, event in enumerate(records[1:], 2):
        if ended:
            raise ValueError("records after run_end")
        h = exact_int(event.get("height"), f"line {i}: height")
        t = exact_int(event.get("time_s"), f"line {i}: time_s")
        if h < last_h or t < last_t:
            raise ValueError("heights and observer times must be nondecreasing")
        committed, funded = stocks()
        integral["encumbered_sat_blocks"] += committed * (h - last_h)
        integral["encumbered_sat_seconds"] += committed * (t - last_t)
        integral["funded_sat_blocks"] += funded * (h - last_h)
        integral["funded_sat_seconds"] += funded * (t - last_t)
        last_h, last_t = h, t
        kind = event.get("kind")
        if kind == "lot_open":
            lot_id = name(event.get("lot_id"), "lot_id")
            reserve = name(event.get("reserve_id"), "reserve_id")
            if lot_id in used_lot_ids or reserve in reserves:
                raise ValueError("a canonical reserve may appear in only one lot")
            state = event.get("state")
            if state not in STATES - {"released"}:
                raise ValueError("invalid opening state")
            lots[lot_id] = {"reserve_id": reserve, "amount_sat": exact_int(event.get("amount_sat"), "amount_sat", 1), "state": state, "owner": name(event.get("owner"), "owner")}
            reserves.add(reserve)
            used_lot_ids.add(lot_id)
        elif kind == "lot_replace":
            # A confirmed spend replaces disjoint inputs with disjoint outputs.
            # Parent identifiers remain retired, so replay cannot recreate value.
            parents = event.get("parents")
            children = event.get("children")
            if not isinstance(parents, list) or not parents or not all(isinstance(p, str) for p in parents):
                raise ValueError("replacement needs parent lot identifiers")
            if len(set(parents)) != len(parents) or any(p not in lots or lots[p]["state"] == "released" for p in parents):
                raise ValueError("replacement parents must be distinct active lots")
            if not isinstance(children, list):
                raise ValueError("replacement children must be a list")
            allowed = {"spendable_observed", "refund_confirmed", "timeout_spend_confirmed"}
            if level == "simulation":
                allowed.add("simulation_release")
            if event.get("cause") not in allowed:
                raise ValueError("replacement needs an observed spend receipt; proof verification is insufficient")
            receipt = name(event.get("release_receipt"), "release_receipt")
            transaction = name(event.get("transaction_id"), "transaction_id")
            fee = exact_int(event.get("fee_sat"), "replacement fee")
            if transaction in fees:
                raise ValueError("duplicate transaction fee")
            pending, child_reserves = {}, set()
            for child in children:
                if not isinstance(child, dict):
                    raise ValueError("replacement child must be an object")
                child_id = name(child.get("lot_id"), "lot_id")
                reserve = name(child.get("reserve_id"), "reserve_id")
                if child_id in used_lot_ids or child_id in pending or reserve in reserves or reserve in child_reserves:
                    raise ValueError("replacement cannot reuse a canonical reserve or lot identifier")
                state = child.get("state")
                if state not in STATES - {"released"}:
                    raise ValueError("invalid replacement child state")
                pending[child_id] = {"reserve_id": reserve, "amount_sat": exact_int(child.get("amount_sat"), "amount_sat", 1),
                                     "state": state, "owner": name(child.get("owner"), "owner")}
                child_reserves.add(reserve)
            principal = sum(lots[p]["amount_sat"] for p in parents)
            if principal != sum(c["amount_sat"] for c in pending.values()) + fee:
                raise ValueError("replacement must conserve input value as outputs plus fee")
            replacements.append({"parents": parents[:], "children": list(pending), "input_sat": principal,
                                 "fee_sat": fee, "transaction_id": transaction, "release_receipt": receipt})
            for p in parents:
                del lots[p]
            lots.update(pending)
            reserves.update(child_reserves)
            used_lot_ids.update(pending)
            fees[transaction] = fee
        elif kind == "lot_state":
            lot_id = name(event.get("lot_id"), "lot_id")
            if lot_id not in lots:
                raise ValueError("state change before lot_open")
            lot = lots[lot_id]
            state = event.get("state")
            if state not in STATES or state == lot["state"] or lot["state"] == "released":
                raise ValueError("invalid, repeated, or terminal state transition")
            name(event.get("cause"), "cause")
            is_release = (lot["state"] in ENCUMBERED and state not in ENCUMBERED) or state == "released"
            if is_release:
                allowed = {"spendable_observed", "refund_confirmed", "timeout_spend_confirmed"}
                if level == "simulation":
                    allowed.add("simulation_release")
                if event["cause"] not in allowed:
                    raise ValueError("release needs an observed spendability/refund receipt; proof verification alone is insufficient")
                name(event.get("release_receipt"), "release_receipt")
            lot["state"] = state
        elif kind in {"payment_offered", "payment_settled", "payment_attempt_failed"}:
            invoice = name(event.get("invoice_id"), "invoice_id")
            if kind == "payment_offered":
                if invoice in offered:
                    raise ValueError("duplicate offered invoice")
                purpose = event.get("purpose")
                if purpose not in {"application", "refresh", "self_transfer", "rebalance", "funding"}:
                    raise ValueError("unknown payment purpose")
                offered[invoice] = {"amount_sat": exact_int(event.get("amount_sat"), "amount_sat", 1), "purpose": purpose, "offered_time_s": t}
            else:
                if invoice not in offered or invoice in settled:
                    raise ValueError("unknown or already settled invoice")
                if kind == "payment_settled":
                    amount = exact_int(event.get("amount_sat"), "amount_sat", 1)
                    if amount != offered[invoice]["amount_sat"]:
                        raise ValueError("settled invoice amount differs from offered amount")
                    name(event.get("receipt"), "receipt")
                    settled[invoice] = dict(offered[invoice], settled_time_s=t)
                else:
                    name(event.get("reason"), "reason")
                    failed_attempts += 1
        elif kind == "fee_paid":
            txid = name(event.get("transaction_id"), "transaction_id")
            if txid in fees:
                raise ValueError("duplicate transaction fee")
            fees[txid] = exact_int(event.get("amount_sat"), "fee amount", 0)
        elif kind == "proof_verified":
            # Deliberately does not release any capital.
            name(event.get("proof_id"), "proof_id")
        elif kind == "run_end":
            ended = True
        else:
            raise ValueError(f"unknown event kind {kind!r}")
        committed, funded = stocks()
        peak_encumbered = max(peak_encumbered, committed)
        peak_funded = max(peak_funded, funded)
    if not ended:
        raise ValueError("missing run_end; terminal exposure must be reported explicitly")
    application_offered = {k: v for k, v in offered.items() if v["purpose"] == "application"}
    paid = {k: v for k, v in settled.items() if v["purpose"] == "application"}
    delivered = sum(v["amount_sat"] for v in paid.values())
    latency_by_invoice = {k: v["settled_time_s"] - v["offered_time_s"] for k, v in paid.items()}
    latencies = sorted(latency_by_invoice.values())
    def quantile(percent):
        return latencies[(percent * len(latencies) + 99) // 100 - 1] if latencies else None
    terminal = [{"lot_id": k, **v} for k, v in lots.items() if v["state"] in ENCUMBERED]
    return {
        "run_id": first["run_id"], "evidence_level_as_supplied": level,
        "evidence_verified": False, "validation_scope": "event schema and arithmetic only; node, proof, and receipt authentication require external adapters",
        "horizon_blocks": last_h - start_h, "horizon_seconds": last_t - start_t,
        **integral, "peak_encumbered_sat": peak_encumbered, "peak_funded_sat": peak_funded,
        "offered_application_invoices": len(application_offered), "settled_application_invoices": len(paid),
        "offered_application_volume_sat": sum(v["amount_sat"] for v in application_offered.values()),
        "settled_application_volume_sat": delivered,
        "settled_application_invoice_fraction": ratio(len(paid), len(application_offered)),
        "settled_application_value_fraction": ratio(delivered, sum(v["amount_sat"] for v in application_offered.values())),
        "unsettled_application_invoice_ids": sorted(application_offered.keys() - paid.keys()),
        "settled_application_latency_seconds": {"sample_count": len(latencies), "by_invoice": latency_by_invoice, "p50_nearest_rank": quantile(50), "p95_nearest_rank": quantile(95), "p99_nearest_rank": quantile(99)},
        "attempt_failures": failed_attempts, "fees_paid_sat": sum(fees.values()),
        "conserved_replacements": replacements,
        "funded_duration_blocks": ratio(integral["funded_sat_blocks"], delivered),
        "funded_duration_seconds": ratio(integral["funded_sat_seconds"], delivered),
        "encumbered_duration_blocks": ratio(integral["encumbered_sat_blocks"], delivered),
        "encumbered_duration_seconds": ratio(integral["encumbered_sat_seconds"], delivered),
        "liquidity_duration_alias_definition": "legacy alias for encumbered duration only; use funded_duration for the paper's provisioned-capital comparison",
        "liquidity_duration_blocks": ratio(integral["encumbered_sat_blocks"], delivered),
        "liquidity_duration_seconds": ratio(integral["encumbered_sat_seconds"], delivered),
        "terminal_encumbered_sat": sum(x["amount_sat"] for x in terminal), "terminal_encumbered_lots": terminal,
        "fully_recovered": not terminal,
        "terminal_state_value_sat": dict(Counter({state: sum(v["amount_sat"] for v in lots.values() if v["state"] == state) for state in STATES})),
    }


def allocate_exact(pool, claims):
    """Exact per-claim floors; the caller retains the undistributed reward pool."""
    exact_int(pool, "reward pool", 0)
    clean = {}
    for key, weight in claims.items():
        name(key, "claim id")
        clean[key] = exact_int(weight, "claim weight", 0)
    total = sum(clean.values())
    if total == 0:
        return {key: 0 for key in clean}
    return {key: pool * weight // total for key, weight in clean.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("counterexample")
    audit = sub.add_parser("analyze")
    audit.add_argument("jsonl", type=Path)
    args = parser.parse_args()
    if args.command == "counterexample":
        result = counterexample()
    else:
        result = analyze([json.loads(line) for line in args.jsonl.read_text().splitlines() if line.strip()])
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
