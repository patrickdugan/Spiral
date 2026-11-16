import base64
import concurrent.futures
import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from proofdesk import demo
from proofdesk.archive import bundle
from proofdesk.domain import Ledger, Refused, Rules, decide, digest, plan_vtxo

TEMP_ROOT = Path(__file__).resolve().parent.parent / '.runtime' / 'tests'
TEMP_ROOT.mkdir(parents=True, exist_ok=True)


class DomainTests(unittest.TestCase):
    def setUp(self):
        self.intent, self.evidence, self.chain, self.rules = demo.sample()

    def refusal(self, code, function, *args):
        with self.assertRaises(Refused) as context:
            function(*args)
        self.assertEqual(context.exception.code, code)

    def test_valid_payment_prepares_fixed_recipient(self):
        result = decide(self.intent, self.evidence, self.chain, self.rules, demo.NOW)
        self.assertEqual(result['beneficiary'], self.intent.beneficiary)
        self.assertEqual(result['state'], 'prepared')
        self.assertNotIn('paid', result)

    def test_rejects_wrong_network_amount_script_and_confirmations(self):
        for evidence, code in [
            (replace(self.evidence, network='testnet4'), 'wrong_network'),
            (replace(self.evidence, value_sats=24999), 'wrong_amount'),
            (replace(self.evidence, value_sats=25001), 'wrong_amount'),
            (replace(self.evidence, script_sha256=digest('wrong')), 'wrong_payment_script'),
            (replace(self.evidence, confirmations=5, tip_height=1004), 'too_few_confirmations'),
            (replace(self.evidence, tip_chainwork=7999), 'chainwork_below_floor'),
        ]:
            with self.subTest(code=code):
                self.refusal(code, decide, self.intent, evidence, self.chain, self.rules, demo.NOW)

    def test_reorg_fork_freshness_and_expiry(self):
        for chain, code in [
            (replace(self.chain, block_hash=digest('reorg')), 'payment_reorged'),
            (replace(self.chain, tip_hash=digest('fork')), 'proof_fork'),
            (replace(self.chain, observed_at=demo.NOW-121), 'chain_view_stale'),
            (replace(self.chain, observed_at=demo.NOW+1), 'chain_view_stale'),
            (replace(self.chain, tip_height=1018), 'proof_tip_stale'),
        ]:
            with self.subTest(code=code):
                self.refusal(code, decide, self.intent, self.evidence, chain, self.rules, demo.NOW)
        self.refusal('intent_expired', decide, replace(self.intent, expires_at=demo.NOW), self.evidence, self.chain, self.rules, demo.NOW)

    def test_live_never_accepts_fixtures_or_operator_reports(self):
        rules = replace(self.rules, mode='live')
        for kind in ('fixture', 'operator-report', 'native-receipt', 'm16-parsed'):
            self.refusal('verified_evidence_required', decide, self.intent, replace(self.evidence, kind=kind), self.chain, rules, demo.NOW)
        self.refusal('verified_evidence_required', decide, self.intent, replace(self.evidence, kind='m16-verified'), self.chain, rules, demo.NOW)

    def test_amounts_cannot_be_booleans_floats_negative_or_unsafe(self):
        for amount in (True, 1.0, -1, 0, 2_100_000_000_000_001):
            self.refusal('invalid_integer', decide, replace(self.intent, amount_sats=amount), self.evidence, self.chain, self.rules, demo.NOW)

    def test_exact_retry_is_idempotent_and_outbox_is_durable(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as directory:
            path = Path(directory)/'ledger.sqlite'
            ledger = Ledger(path, 'demo')
            ledger.add_intent(self.intent)
            first = ledger.prepare(self.intent.id, self.evidence, self.chain, self.rules, demo.NOW)
            ledger.close()
            ledger = Ledger(path, 'demo')
            try:
                retry = ledger.prepare(self.intent.id, self.evidence, self.chain, self.rules, demo.NOW)
                self.assertEqual(retry['id'], first['id'])
                self.assertTrue(retry['idempotent_replay'])
                self.assertEqual(ledger.db.execute('SELECT count(*) FROM outbox').fetchone()[0], 1)
                self.refusal('intent_already_prepared', ledger.prepare, self.intent.id, replace(self.evidence, txid=digest('second')), self.chain, self.rules, demo.NOW)
            finally:
                ledger.close()

    def test_intent_recipient_is_immutable_and_deposit_script_is_unique(self):
        ledger = Ledger(':memory:', 'demo')
        try:
            ledger.add_intent(self.intent)
            self.refusal('intent_immutable', ledger.add_intent, replace(self.intent, beneficiary='attacker'))
            self.refusal('deposit_script_reused', ledger.add_intent, replace(self.intent, id='attacker', beneficiary='attacker'))
        finally:
            ledger.close()

    def test_namespace_cannot_be_reopened_as_live(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as directory:
            path = Path(directory)/'ledger.sqlite'
            Ledger(path, 'demo').close()
            self.refusal('database_namespace_mismatch', Ledger, path, 'live')

    def test_live_rules_cannot_write_demo_database(self):
        ledger = Ledger(':memory:', 'demo')
        try:
            ledger.add_intent(self.intent)
            self.refusal('database_namespace_mismatch', ledger.prepare, self.intent.id, self.evidence, self.chain, replace(self.rules, mode='live'), demo.NOW)
        finally:
            ledger.close()

    def test_concurrent_retries_prepare_one_outbox_entry(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as directory:
            path = Path(directory)/'ledger.sqlite'
            seed = Ledger(path, 'demo'); seed.add_intent(self.intent); seed.close()
            def claim(_):
                ledger = Ledger(path, 'demo')
                try:
                    return ledger.prepare(self.intent.id, self.evidence, self.chain, self.rules, demo.NOW)
                finally:
                    ledger.close()
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                receipts = list(executor.map(claim, range(8)))
            self.assertEqual(len({r['id'] for r in receipts}), 1)
            self.assertEqual(sum(not r['idempotent_replay'] for r in receipts), 1)

    def test_outbox_failure_rolls_back_payment_reservation(self):
        ledger = Ledger(':memory:', 'demo')
        try:
            ledger.add_intent(self.intent)
            ledger.db.execute("CREATE TRIGGER fail_outbox BEFORE INSERT ON outbox BEGIN SELECT RAISE(ABORT,'disk-like error'); END")
            self.refusal('intent_already_prepared', ledger.prepare, self.intent.id, self.evidence, self.chain, self.rules, demo.NOW)
            self.assertEqual(ledger.receipts(), [])
            ledger.db.execute('DROP TRIGGER fail_outbox')
            self.assertFalse(ledger.prepare(self.intent.id, self.evidence, self.chain, self.rules, demo.NOW)['idempotent_replay'])
        finally:
            ledger.close()

    def test_all_demo_cases_have_correct_outcome(self):
        expected = {'cashu':'prepared', 'ark':'prepared', 'replay':'deposit_script_reused',
                    'wrong-amount':'wrong_amount', 'wrong-script':'wrong_payment_script',
                    'reorg':'payment_reorged', 'stale':'chain_view_stale', 'operator-report':'demo_namespace_required'}
        for case, code in expected.items():
            with self.subTest(case=case):
                result = demo.run_case(case)
                self.assertEqual(result['decision']['code'], code)
                self.assertTrue(result['simulation'])

    def test_archive_cid_commits_exact_bytes_and_omits_sensitive_fields(self):
        receipts = demo.run_case('cashu')['receipts']
        data, manifest = bundle(receipts)
        self.assertEqual(manifest['sha256'], hashlib.sha256(data).hexdigest())
        decoded = base64.b32decode(manifest['cid'][1:].upper() + '='*((-(len(manifest['cid'])-1)) % 8))
        self.assertEqual(decoded, b'\x01\x55\x12\x20' + hashlib.sha256(data).digest())
        parsed = json.loads(data)['receipts'][0]
        for field in ('beneficiary', 'outpoint', 'intent_id', 'chain_tip'):
            self.assertNotIn(field, parsed)
        self.assertIsNone(manifest['deal_id'])


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.vtxo = demo.vtxos()[0]

    def test_hold_refresh_exit_and_urgent_boundaries(self):
        for remaining, action in [(145,'hold'), (144,'refresh'), (73,'refresh'), (72,'delegate_exit'), (25,'delegate_exit'), (24,'urgent'), (0,'urgent'), (-1,'urgent')]:
            with self.subTest(remaining=remaining):
                plan = plan_vtxo(self.vtxo, self.vtxo['expiry_height']-remaining)
                self.assertEqual(plan['action'], action)
                self.assertFalse(plan['executed'])

    def test_offline_operator_exits_early(self):
        self.assertEqual(plan_vtxo({**self.vtxo, 'operator_online':False},1005)['action'], 'delegate_exit')

    def test_unvalidated_exit_package_is_never_delegated(self):
        self.assertEqual(plan_vtxo({**self.vtxo, 'exit_package_validated':False},1330)['action'], 'prepare_exit')

    def test_malformed_vtxo_is_rejected(self):
        with self.assertRaises(Refused):
            plan_vtxo({**self.vtxo, 'exit_budget_blocks':False},1005)


if __name__ == '__main__':
    unittest.main()
