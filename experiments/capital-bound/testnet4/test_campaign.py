import unittest

from campaign import Gate, funding_reference, groups, validate_tx
from core import btc, sats
from report import timeline


class CampaignTests(unittest.TestCase):
    def test_workload_matches(self):
        flatten = lambda profile: [row for group in groups(profile) for row in group]
        self.assertEqual(flatten("individual"), flatten("batched"))
        self.assertEqual(sum(i["sat"] for i in flatten("batched")), 11_400)

    def test_money_is_exact(self):
        self.assertEqual(sats(btc(2_000_000)), 2_000_000)
        for value in ("0.000000001", "NaN", 0.01, "-1"):
            with self.subTest(value=value), self.assertRaises(Gate):
                sats(value)
        with self.assertRaises(Gate):
            funding_reference("1" * 64 + ":4294967296")

    def test_transaction_binds_input_and_payout_scripts(self):
        inp = {"txid": "1" * 64, "vout": 0, "sat": 100_000}
        tx = {"txid": "2" * 64, "vin": [{**inp, "sequence": 0xfffffffe}],
              "vout": [{"n": 0, "value": btc(1_400), "scriptPubKey": {"hex": "pay"}},
                       {"n": 1, "value": btc(98_200), "scriptPubKey": {"hex": "change"}}]}
        outputs = [{"script": "pay", "sat": 1_400}]
        self.assertEqual(validate_tx(tx, inp, outputs, 98_200, "change")["vout"], 1)
        for changed in ({"txid": "3" * 64}, {"vout": 1}, {"sequence": 100}):
            with self.subTest(changed=changed), self.assertRaises(Gate):
                validate_tx({**tx, "vin": [{**tx["vin"][0], **changed}]},
                            inp, outputs, 98_200, "change")
        tx["vout"][0]["scriptPubKey"]["hex"] = "substitute"
        with self.assertRaises(Gate):
            validate_tx(tx, inp, outputs, 98_200, "change")

    def test_reorg_reverses_release_and_invoice(self):
        funding = {"sat": 100_000, "txid": "a", "vout": 0}
        invoice = groups("canary")[0][0]
        plan = {"started_at": 10, "initial_height": 100, "funding": funding,
                "groups": [[invoice]]}
        draft = {"txid": "b", "change": {"txid": "b", "vout": 1, "sat": 98_200},
                 "payments": [invoice], "fee_sat": 400, "vsize": 141}
        good = {"event_order": 2, "at": 20, "height": 102, "tip": "good", "phases": [
            {"position": 0, "txid": "b", "status": "recovered", "blockhash": "good"}]}
        bad = {"event_order": 3, "at": 30, "height": 100, "tip": "other", "reorg": True,
               "phases": [{"position": 0, "txid": "b", "status": "mempool"}]}
        result, rows = timeline(plan, [draft], [(0, 10, 100, 1)], [good, bad])
        self.assertEqual(result["confirmed_application_sat"], 0)
        self.assertEqual(result["unavailable_sat_blocks"], 200_000)
        self.assertEqual(rows[-2]["funded_sat"], 98_200)
        self.assertEqual(rows[-1]["unavailable_sat"], 100_000)


if __name__ == "__main__":
    unittest.main()
