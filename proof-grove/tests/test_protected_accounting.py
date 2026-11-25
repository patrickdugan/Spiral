import copy
import hashlib
import unittest
from unittest.mock import Mock, patch

from proofdesk import protected_accounting as accounting
from proofdesk.domain import digest, Refused


TIP = "ab" * 32
PAYOUT = "cd" * 32
MINT = "http://127.0.0.1:31510"


class ProtectedAccountingTest(unittest.TestCase):
    def setUp(self):
        self.catalog = {"schema": accounting.CATALOG_SCHEMA, "genesis": accounting.GENESIS,
                        "mint": MINT, "tip_hash": TIP, "tip_height": 120, "bundles": []}
        self.journal = {"schema": accounting.JOURNAL_SCHEMA, "genesis": accounting.GENESIS,
                        "mint_profile_sha256": digest({"schema": "proof-grove/protected-accounting-mint/v3",
                                                        "mint_url": MINT}), "events": []}
        self.records, self.observations = [], {}
        for index, state in enumerate(("register", "issue", "redeem"), 1):
            self.add_bundle(index, state)
        self.core = Mock()
        self.core.rpc.side_effect = lambda method, params: {
            "getblockchaininfo": {"chain": "regtest", "initialblockdownload": False, "bestblockhash": TIP, "blocks": 120},
            "getblockhash": accounting.GENESIS, "getblockheader": {"height": 110},
        }[method]

    def add_bundle(self, index, state):
        coin = str(index) * 64, 0
        bundle_id = digest({"test_bundle": index})
        funding = {"txid": coin[0], "vout": coin[1], "block": "a1" * 32}
        plan = {"reserve_sats": 25000, "funding_script": "0020" + "a2" * 32, "payout_sats": 24750,
                "payout_script": "0014" + "a3" * 20, "fee_sats": 250, "delay_blocks": 6,
                "claim_commitment": "a4" * 32}
        self.catalog["bundles"].append({"schema": accounting.V3_BUNDLE_SCHEMA, "bundle_id": bundle_id,
                                        "funding": funding, "plan": plan})
        self.observations[bundle_id] = {"state": "unspent", "tip": TIP, "spender": None}
        quote = bytes([index]) * 32
        intent = hashlib.sha256(b"proof-grove/protected-issuance-intent/v1\0" + quote).hexdigest()

        def add(action, evidence):
            record = evidence | {"bundle_id": bundle_id}
            self.records.append(record)
            self.journal["events"].append({"funding_txid": coin[0], "funding_vout": coin[1], "amount_sats": 25000,
                                           "action": action, "evidence_sha256": digest(record)})

        add({"kind": "register", "intent": intent}, {"kind": "observed-regtest-reserve",
            "funding": funding | {"sats": 25000, "script": plan["funding_script"]}})
        if state == "register":
            return
        claim = accounting.bound_claim(coin)
        add({"kind": "issue", "intent": intent, "claim": claim}, {
            "kind": "verified-cdk-protected-v3-batch", "claim": claim, "real_cdk_issuance": True,
            "amount_sats": 25000, "intent_id": f"cashu:{quote.hex()}", "issuance_batch_sha256": plan["claim_commitment"],
            "independent_verifier": {"amount_sats": 25000, "bundle_id": bundle_id, "mint": MINT,
                                     "batch_bound": True, "dleq_verified": True, "offline_keyset_audit": True},
        })
        if state == "redeem":
            spender = {"route": "holder", "block": "ae" * 32, "txid": PAYOUT, "wtxid": "af" * 32}
            self.observations[bundle_id] = {"state": "consumed", "tip": TIP, "spender": spender,
                                            "holder_only_earliest_height": 110}
            payout = {key: spender[key] for key in ("txid", "wtxid", "block")}
            add({"kind": "redeem", "input": claim, "reserve_before_sats": 25000}, {
                "kind": "observed-regtest-payout", "payout": payout | {"sats": 24750, "height": 110,
                    "fee_sats": 250, "delay_blocks": 6, "script": plan["payout_script"]},
            })

    def audit(self):
        with patch.object(accounting, "spending_observation", side_effect=lambda core, bundle, pin: self.observations[pin]):
            return accounting.audit(self.core, self.catalog, self.journal, self.records)

    def test_reconciles_pending_issued_and_redeemed_at_one_tip(self):
        result = self.audit()
        self.assertEqual(result, {"declared_reserve_sats": 50000, "outstanding_claims_sats": 25000,
                                  "pending_issuance_sats": 25000, "catalog_reserves": 3, "tip_hash": TIP,
                                  "tip_height": 120})

    def test_catalog_views_reject_omission_and_duplicate_funding(self):
        original = copy.deepcopy(self.catalog["bundles"])
        self.catalog["bundles"].pop(0)
        with self.assertRaisesRegex(Refused, "event_not_in_catalog"):
            self.audit()
        self.catalog["bundles"] = original + [original[0]]
        with self.assertRaisesRegex(Refused, "duplicate_or_unsupported_reserve"):
            self.audit()
        self.catalog["bundles"] = original
        del self.journal["events"][0]
        del self.records[0]
        with self.assertRaisesRegex(Refused, "catalog_omission"):
            self.audit()

    def test_liability_without_spendable_coin_and_stale_tip_are_refused(self):
        pin = self.catalog["bundles"][1]["bundle_id"]
        self.observations[pin]["state"] = "pending-spend"
        with self.assertRaisesRegex(Refused, "reserve_unavailable"):
            self.audit()
        self.observations[pin]["state"] = "unspent"
        self.catalog["tip_hash"] = "11" * 32
        with self.assertRaisesRegex(Refused, "stale_catalog"):
            self.audit()

    def test_changed_issuance_and_substituted_payout_fail_with_updated_event_hashes(self):
        self.records[2]["independent_verifier"]["mint"] = "http://127.0.0.1:12345"
        self.journal["events"][2]["evidence_sha256"] = digest(self.records[2])
        with self.assertRaisesRegex(Refused, "issuance_mismatch"):
            self.audit()
        self.records[2]["independent_verifier"]["mint"] = MINT
        self.journal["events"][2]["evidence_sha256"] = digest(self.records[2])
        self.records[-1]["payout"]["script"] = "0014" + "ff" * 20
        self.journal["events"][-1]["evidence_sha256"] = digest(self.records[-1])
        with self.assertRaisesRegex(Refused, "payout_mismatch"):
            self.audit()

    def test_split_does_not_authorize_new_full_outpoint_claims(self):
        self.journal["events"][3]["action"]["kind"] = "split"
        with self.assertRaisesRegex(Refused, "invalid_transition"):
            self.audit()

    def test_tip_change_during_reconciliation_invalidates_all_totals(self):
        response = self.core.rpc.side_effect
        first = response("getblockchaininfo", [])
        tips = iter((first, first | {"bestblockhash": "de" * 32}))
        self.core.rpc.side_effect = lambda method, params: next(tips) if method == "getblockchaininfo" else response(method, params)
        with self.assertRaisesRegex(Refused, "chain_changed_retry"):
            self.audit()


if __name__ == "__main__":
    unittest.main()
