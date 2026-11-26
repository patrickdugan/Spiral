import copy
import hashlib
import unittest
from unittest.mock import Mock, patch

from proofdesk import protected_accounting as accounting
from proofdesk import protected_withdrawal as withdrawal
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

    def audit(self, *, registry=None, live_receipt=None):
        with patch.object(accounting, "spending_observation", side_effect=lambda core, bundle, pin: self.observations[pin]):
            return accounting.audit(self.core, self.catalog, self.journal, self.records, registry=registry,
                                    live_receipt=live_receipt)

    def test_reconciles_pending_issued_and_redeemed_at_one_tip(self):
        result = self.audit()
        self.assertEqual(result, {"declared_reserve_sats": 50000, "outstanding_claims_sats": 25000,
                                  "pending_issuance_sats": 25000, "catalog_reserves": 3, "tip_hash": TIP,
                                  "tip_height": 120})

    def test_wallet_admission_requires_the_exact_live_registry_receipt(self):
        bundle = self.catalog["bundles"][1]
        pin = "e1" * 32
        self.records[2]["issuance_receipt_sha256"] = pin
        self.records[2]["independent_verifier"]["keysets_sha256"] = "e2" * 32
        self.journal["events"][2]["evidence_sha256"] = digest(self.records[2])
        with self.assertRaisesRegex(Refused, "live_issuance_requires_registry"):
            self.audit(live_receipt=(bundle["bundle_id"], pin))
        registry = {"trusted": "root"}
        self.catalog.update(schema=accounting.REGISTRY_CATALOG_SCHEMA, registry_sha256=digest(registry))
        registered = {accounting.outpoint(bundle["funding"]) for bundle in self.catalog["bundles"]}
        with patch.object(accounting, "discover", return_value=(registered, {"registered_reserves": len(registered)})):
            claim = self.audit(registry=registry, live_receipt=(bundle["bundle_id"], pin))["live_issuance"]
            self.assertEqual(claim["claim_id"], accounting.bound_claim(accounting.outpoint(bundle["funding"])))
            self.assertEqual((claim["issuance_receipt_sha256"], claim["amount_sats"]), (pin, 25000))
            for selected, reason in ((self.catalog["bundles"][0]["bundle_id"], "issuance_not_live"),
                                     (self.catalog["bundles"][2]["bundle_id"], "issuance_not_live"),
                                     ("e3" * 32, "issuance_bundle_not_registered")):
                with self.subTest(reason=reason), self.assertRaisesRegex(Refused, reason):
                    self.audit(registry=registry, live_receipt=(selected, pin))
            with self.assertRaisesRegex(Refused, "issuance_receipt_mismatch"):
                self.audit(registry=registry, live_receipt=(bundle["bundle_id"], "e4" * 32))

    def test_prewithdrawal_requires_live_issuance_and_one_tip(self):
        bundle = self.catalog['bundles'][1]
        bundle['plan']['holder_pubkey'] = '02' + 'ab' * 32
        issued = bundle['bundle_id']
        observation = {'tip': TIP, 'height': 120, 'funding_height': 115, 'eligible_in_next_block': True,
                       'holder_only_earliest_height': 121}
        checked = {'txid': PAYOUT, 'wtxid': 'aa' * 32, 'payout_sats': 24750, 'fee_sats': 250, 'change_sats': 0,
                   'mempool_eligible': True, 'reject_reason': None, 'observation': observation}
        args = (self.core, self.catalog, self.journal, self.records)
        with (patch.object(accounting, 'spending_observation', side_effect=lambda c, b, pin: self.observations[pin]),
              patch.object(withdrawal, 'check_signed', return_value=checked) as signed):
            result = withdrawal.prepare(*args, issued, 'abcd')
            last = result['journal']['events'][-1]
            self.assertEqual(last['evidence_sha256'], result['withdrawal_id'])
            self.assertEqual(result['journal']['events'][:-1], self.journal['events'])
            self.assertEqual(last['action']['input'], accounting.bound_claim(accounting.outpoint(bundle['funding'])))
            for inactive in (self.catalog['bundles'][0], self.catalog['bundles'][2]):
                with self.assertRaisesRegex(Refused, 'claim_not_live'):
                    withdrawal.prepare(*args, inactive['bundle_id'], 'abcd')
            signed.assert_called_once_with(self.core, bundle, issued, 'holder', 'abcd')
            checked.update(mempool_eligible=False, reject_reason='non-BIP68-final')
            with self.assertRaisesRegex(Refused, 'not_eligible: non-BIP68-final'):
                withdrawal.prepare(*args, issued, 'abcd')
            observation['tip'] = 'ff' * 32
            with self.assertRaisesRegex(Refused, 'chain_changed_retry'):
                withdrawal.prepare(*args, issued, 'abcd')

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

    def test_registry_detects_a_reserve_omitted_from_both_catalog_and_journal(self):
        registry = {"independent": "root"}
        registered = {accounting.outpoint(bundle["funding"]) for bundle in self.catalog["bundles"]}
        enrollment = {"registered_reserves": len(registered), "head_txid": TIP, "head_vout": 0}
        with self.assertRaisesRegex(Refused, "registry_profile_mismatch"):
            self.audit(registry=registry)
        self.catalog.update(schema=accounting.REGISTRY_CATALOG_SCHEMA, registry_sha256=digest(registry))
        with self.assertRaisesRegex(Refused, "registry_profile_mismatch"):
            self.audit()
        with self.assertRaisesRegex(Refused, "registry_root_mismatch"):
            self.audit(registry={"independent": "substitute"})
        with patch.object(accounting, "discover", return_value=(registered, enrollment)) as discover:
            result = self.audit(registry=registry)
            self.assertEqual(result["registry"], enrollment | {"root_sha256": digest(registry)})
            self.catalog["bundles"].pop(0)
            self.journal["events"].pop(0)
            self.records.pop(0)
            with self.assertRaisesRegex(Refused, "registered_reserve_omitted"):
                self.audit(registry=registry)
            with patch.object(accounting, "discover", return_value=(set(), enrollment)):
                with self.assertRaisesRegex(Refused, "unregistered_reserve"):
                    self.audit(registry=registry)
            self.assertEqual(discover.call_count, 2)

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

    def test_funded_rollover_requires_both_ordered_successors(self):
        self.add_bundle(4, "issue")
        parent = self.catalog["bundles"][-1]
        children = []
        for index, amount in enumerate((12000, 12750)):
            child = {"schema": accounting.SUCCESSOR_BUNDLE_SCHEMA, "bundle_id": digest({"child": index}),
                     "funding": {"txid": "bf" * 32, "vout": index, "block": "bc" * 32},
                     "plan": {"reserve_sats": amount}}
            children.append(child)
            self.observations[child["bundle_id"]] = {"state": "unspent", "tip": TIP, "spender": None}
        self.catalog["bundles"].extend(children)
        receipt = {"successors": children, "receipt_id": "11" * 32}
        entries = accounting.rollover_entries(parent, {}, receipt)
        original_events, original_records = self.journal["events"][:], self.records[:]

        def use(group):
            self.journal["events"] = original_events + [event for event, _ in group]
            self.records = original_records + [record for _, record in group]

        with patch.object(accounting, "verify_confirmed", return_value=children):
            use(entries)
            result = self.audit()
            self.assertEqual(result["outstanding_claims_sats"], 49750)
            use(entries[:-1])
            with self.assertRaisesRegex(Refused, "rollover_group_mismatch"):
                self.audit()
            use([entries[0], *entries[3:], *entries[1:3]])
            with self.assertRaisesRegex(Refused, "rollover_group_mismatch"):
                self.audit()
            use(entries[1:])
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
