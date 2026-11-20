import copy
import json
import unittest
from pathlib import Path

from lab import allocate_exact, analyze, counterexample


def fixture():
    return [json.loads(x) for x in Path(__file__).with_name("fixture.jsonl").read_text().splitlines() if x.strip()]


class CapitalBoundTests(unittest.TestCase):
    def test_diamond_route_history_and_mpp(self):
        r = counterexample()
        self.assertEqual(r["first_route_via_a"]["second_payment_admissible_paths"], [])
        self.assertEqual(r["first_route_via_a"]["unsplit_settled_payments"], 1)
        self.assertEqual(r["first_route_via_b"]["unsplit_settled_payments"], 2)
        self.assertEqual(r["mpp_rescue_after_route_a"]["final_state"], r["first_route_via_b"]["final_state"])
        self.assertEqual(r["all_cut_conservation"]["checked_cut_state_pairs"], 98)

    def test_integrals_unique_business_volume_and_proof_no_release(self):
        r = analyze(fixture())
        self.assertEqual(r["encumbered_sat_blocks"], 600)
        self.assertEqual(r["encumbered_sat_seconds"], 6000)
        self.assertEqual(r["funded_sat_blocks"], 1350)
        self.assertEqual(r["funded_sat_seconds"], 13500)
        self.assertEqual(r["settled_application_volume_sat"], 100)
        self.assertEqual(r["offered_application_volume_sat"], 100)
        self.assertEqual(r["settled_application_invoice_fraction"]["decimal"], 1)
        self.assertEqual(r["settled_application_value_fraction"]["decimal"], 1)
        self.assertEqual(r["liquidity_duration_seconds"]["decimal"], 60)
        self.assertEqual(r["encumbered_duration_seconds"]["decimal"], 60)
        self.assertEqual(r["encumbered_duration_blocks"]["decimal"], 6)
        self.assertEqual(r["funded_duration_seconds"]["decimal"], 135)
        self.assertEqual(r["funded_duration_blocks"]["decimal"], 13.5)
        self.assertEqual(r["peak_encumbered_sat"], 150)
        self.assertEqual(r["settled_application_latency_seconds"]["by_invoice"], {"sale-1": 30, "sale-2": 40})
        self.assertTrue(r["fully_recovered"])
        self.assertFalse(r["evidence_verified"])

    def test_terminal_exposure_and_missing_end(self):
        trace = fixture()
        trace.insert(-1, {"kind":"lot_state", "lot_id":"lot-A", "state":"unavailable", "cause":"reserve_reused", "height":8,"time_s":80})
        r = analyze(trace)
        self.assertEqual(r["encumbered_sat_blocks"], 800)
        self.assertEqual(r["terminal_encumbered_sat"], 100)
        self.assertFalse(r["fully_recovered"])
        with self.assertRaises(ValueError):
            analyze(trace[:-1])

    def test_double_counted_reserve_rejected(self):
        trace = fixture()
        extra = copy.deepcopy(trace[1])
        extra["lot_id"] = "another-alias-for-same-coins"
        trace.insert(2, extra)
        with self.assertRaisesRegex(ValueError, "canonical reserve"):
            analyze(trace)

    def test_duplicate_invoice_and_amount_change_rejected(self):
        trace = fixture()
        paid = next(x for x in trace if x["kind"] == "payment_settled")
        index = trace.index(paid)
        trace.insert(index + 1, copy.deepcopy(paid))
        with self.assertRaises(ValueError):
            analyze(trace)
        trace = fixture()
        next(x for x in trace if x["kind"] == "payment_settled")["amount_sat"] = 61
        with self.assertRaisesRegex(ValueError, "differs"):
            analyze(trace)

    def test_proof_acceptance_cannot_release_capital(self):
        trace = fixture()
        release = next(x for x in trace if x["kind"] == "lot_state" and x["state"] == "available")
        release["cause"] = "proof_verified"
        with self.assertRaisesRegex(ValueError, "proof verification"):
            analyze(trace)

    def test_bad_amounts_and_time_order(self):
        for value in (-1, 1.5, True, "100"):
            trace = fixture()
            trace[1]["amount_sat"] = value
            with self.assertRaises(ValueError):
                analyze(trace)
        trace = fixture()
        trace[-1]["time_s"] = 10
        with self.assertRaisesRegex(ValueError, "nondecreasing"):
            analyze(trace)

    def test_frozen_reward_snapshot(self):
        snapshot = {"alpha": 10, "beta": 10}
        self.assertEqual(allocate_exact(100, snapshot), {"alpha": 50, "beta": 50})
        self.assertEqual(snapshot, {"alpha": 10, "beta": 10})
        with self.assertRaises(ValueError):
            allocate_exact(100, {"alpha": 10, "beta": -9})
        self.assertEqual(allocate_exact(7, {"a": 1, "b": 1, "c": 1}), {"a": 2, "b": 2, "c": 2})

    def replacement_trace(self):
        return [
            {"kind": "run_start", "run_id": "replacement", "evidence_level": "native_regtest", "height": 0, "time_s": 0},
            {"kind": "lot_open", "lot_id": "input", "reserve_id": "tx0:0", "amount_sat": 100, "owner": "alice", "state": "unavailable", "height": 0, "time_s": 0},
            {"kind": "lot_replace", "parents": ["input"], "children": [
                {"lot_id": "output-a", "reserve_id": "tx1:0", "amount_sat": 60, "owner": "alice", "state": "available"},
                {"lot_id": "output-b", "reserve_id": "tx1:1", "amount_sat": 39, "owner": "alice", "state": "unavailable"},
            ], "fee_sat": 1, "transaction_id": "tx1", "cause": "spendable_observed", "release_receipt": "receipt-1", "height": 2, "time_s": 20},
            {"kind": "run_end", "height": 3, "time_s": 30},
        ]

    def test_replacement_conserves_splits_fees_and_encumbrance(self):
        result = analyze(self.replacement_trace())
        self.assertEqual(result["funded_sat_blocks"], 299)
        self.assertEqual(result["encumbered_sat_blocks"], 239)
        self.assertEqual(result["terminal_encumbered_sat"], 39)
        self.assertEqual(result["fees_paid_sat"], 1)
        self.assertEqual(sum(result["terminal_state_value_sat"].values()) + result["fees_paid_sat"], 100)

    def test_replacement_rejects_inflation_duplicate_inputs_and_proof_release(self):
        for mutation in ("inflation", "duplicate", "proof", "fee", "reserve"):
            trace = self.replacement_trace()
            event = trace[2]
            if mutation == "inflation":
                event["children"][0]["amount_sat"] += 1
            elif mutation == "duplicate":
                event["parents"].append("input")
            elif mutation == "proof":
                event["cause"] = "proof_verified"
            elif mutation == "fee":
                event["fee_sat"] = -1
            else:
                event["children"][0]["reserve_id"] = "tx0:0"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                analyze(trace)

    def test_replacement_retires_parent_and_supports_conserving_merge(self):
        trace = self.replacement_trace()
        trace.insert(-1, {"kind": "lot_replace", "parents": ["output-a", "output-b"], "children": [
            {"lot_id": "merged", "reserve_id": "tx2:0", "amount_sat": 98, "owner": "alice", "state": "available"}],
            "fee_sat": 1, "transaction_id": "tx2", "cause": "spendable_observed", "release_receipt": "receipt-2", "height": 3, "time_s": 30})
        result = analyze(trace)
        self.assertEqual(result["fees_paid_sat"], 2)
        self.assertEqual(result["terminal_state_value_sat"]["available"], 98)
        self.assertEqual(result["terminal_encumbered_sat"], 0)
        replay = copy.deepcopy(trace[1])
        replay.update(height=3, time_s=30)
        trace.insert(-1, replay)
        with self.assertRaisesRegex(ValueError, "canonical reserve"):
            analyze(trace)


if __name__ == "__main__":
    unittest.main()
