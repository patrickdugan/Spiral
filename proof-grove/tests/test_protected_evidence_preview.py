import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen
from zipfile import ZipFile

from proofdesk.domain import Refused, digest
from proofdesk.protected_accounting import JOURNAL_SCHEMA, REGISTRY_CATALOG_SCHEMA
from proofdesk.protected_evidence_preview import REFUSAL_STATEMENT, checked_archive
from proofdesk.protected_registry import SCHEMA as REGISTRY_SCHEMA
from proofdesk.protected_reserve import GENESIS
from proofdesk.server import Desk, make_server


class RecoveryEvidenceTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.publication = Path(scratch.name) / 'preview.json'
        self.zip = self.publication.with_name('archive.zip')
        self.claim, self.txid, self.wtxid = ('11' * 32, '22' * 32, '33' * 32)

    def publish(self, case, member, receipt, *, statement=None, members=None, pins=None, **changes):
        with ZipFile(self.zip, 'w') as source:
            source.writestr(member, json.dumps(receipt))
            if statement is not None:
                source.writestr(REFUSAL_STATEMENT, statement)
            for name, raw in (members or {}).items():
                source.writestr(name, raw)
        manifest = {'schema': 'proof-grove/protected-recovery-evidence/v1', 'claim_id': self.claim,
                    'holder_txid': self.txid, 'holder_wtxid': self.wtxid,
                    case: {'file': self.zip.name, 'sha256': hashlib.sha256(self.zip.read_bytes()).hexdigest()} | (pins or {})}
        self.publication.write_text(json.dumps(manifest | changes), encoding='utf-8')

    def test_historical_redemption_binds_evidence_and_limits_the_chain_claim(self):
        member = 'verification/verification.json'
        statement = b'historical Cairo statement'
        proof = b'archived Shinigami STARK'
        audit = {'schema': 'proof-grove/exact-melt-bitcoin-transaction-audit/v1', 'payout_sats': 23750,
                 'funding_outpoint': self.claim + ':0', 'payout_txid': self.txid,
                 'holder_signature_verified': True, 'canonical_chain_and_network_verified_offline': False}
        encoded_audit = json.dumps(audit).encode()
        members = {'proof/redemption-proof.json': proof, 'case/statement.json': statement,
                   'verification/bitcoin-transaction-audit.json': encoded_audit}
        pins = {'proof_sha256': hashlib.sha256(proof).hexdigest(),
                'statement_sha256': hashlib.sha256(statement).hexdigest(),
                'transaction_audit_sha256': hashlib.sha256(encoded_audit).hexdigest()}
        receipt = {'schema': 'rbzk/cashu-independent-verification/v1', 'verified': True,
                   'chain_context_observed': False, 'payout_txid': self.txid, 'funding_outpoint': audit['funding_outpoint'],
                   'cairo_public_memory_output': ['0x1'] * 24,
                   'verified_mutated_cells': [{'index': index, 'exit_code': 1} for index in range(24)],
                   'proof_sha256': pins['proof_sha256'], 'statement_sha256': pins['statement_sha256']}
        pins['receipt_sha256'] = hashlib.sha256(json.dumps(receipt).encode()).hexdigest()
        self.publish('historical', member, receipt, members=members, pins=pins)
        checked = checked_archive(self.publication, 'historical')
        self.assertEqual(checked.summary['holder_sats'], 23750)
        self.assertFalse(checked.summary['chain_context_observed'])
        self.assertEqual(json.loads(checked.verification), receipt)
        for changes in ({'chain_context_observed': True}, {'verified_mutated_cells': receipt['verified_mutated_cells'][:-1]}):
            with self.subTest(changes=changes):
                changed = receipt | changes
                repinned = pins | {'receipt_sha256': hashlib.sha256(json.dumps(changed).encode()).hexdigest()}
                self.publish('historical', member, changed, members=members, pins=repinned)
                with self.assertRaisesRegex(Refused, 'recovery_evidence_unverified'):
                    checked_archive(self.publication, 'historical')
        for path in members:
            with self.subTest(path=path):
                self.publish('historical', member, receipt, members=members | {path: encoded_audit + b' '}, pins=pins)
                with self.assertRaisesRegex(Refused, 'recovery_evidence_unverified'):
                    checked_archive(self.publication, 'historical')

    def test_registry_accounting_requires_the_proof_and_external_chain_pins(self):
        # The structural fixture supplies one linked header and a native receipt.
        block = b'\x01\0\0\0' + bytes.fromhex(GENESIS)[::-1] + bytes(45)
        tip = hashlib.sha256(hashlib.sha256(block[:80]).digest()).digest()[::-1].hex()
        blocks = block.hex().encode() + b'\n'
        root = {'schema': REGISTRY_SCHEMA, 'genesis': GENESIS}
        catalog = json.dumps({'schema': REGISTRY_CATALOG_SCHEMA, 'genesis': GENESIS, 'registry_sha256': digest(root),
                              'tip_hash': tip, 'tip_height': 1, 'bundles': [{}]}).encode()
        journal = json.dumps({'schema': JOURNAL_SCHEMA, 'genesis': GENESIS, 'events': [{}]}).encode()
        proof = b'compressed accounting fixture'
        journal_pin = hashlib.sha256(journal).hexdigest()
        key_pin = '44' * 32
        final = ['00' * 32] * 10
        final[4:7] = [f'{value:064x}' for value in (25_000, 24_000, 1_000)]
        nova = {'schema': 'proof-grove/cashu-nova-regtest-accounting/v1', 'mode': 'verify-journal', 'steps': 1,
                'verified': True, 'journal_sha256': journal_pin, 'proof_bytes': len(proof), 'zn': final,
                'proof_sha256': hashlib.sha256(proof).hexdigest(), 'verifier_key_sha256': key_pin,
                'declared_reserve_sats': 25_000, 'outstanding_claims_sats': 24_000}
        receipt = {'schema': 'proof-grove/protected-ledger-audit/v1', 'tip_hash': tip, 'tip_height': 1,
                   'catalog_sha256': hashlib.sha256(catalog).hexdigest(), 'journal_sha256': journal_pin,
                   'registry': {'root_sha256': digest(root), 'registered_reserves': 1}, 'catalog_reserves': 1,
                   'declared_reserve_sats': 25_000, 'outstanding_claims_sats': 24_000,
                   'pending_issuance_sats': 1_000, 'nova': nova}
        member = 'evidence/nova-registry-verification.json'
        proof_member = 'evidence/nova-proof/nova-proof.bin'
        members = {'evidence/registry-root.json': json.dumps(root), 'evidence/catalog.json': catalog,
                   'evidence/journal.json': journal, proof_member: proof, 'evidence/registry-blocks.hex': blocks}
        pins = {'registry_sha256': digest(root), 'tip_hash': tip, 'tip_height': 1,
                'nova_verifier_key_sha256': key_pin, 'blocks_sha256': hashlib.sha256(blocks).hexdigest()}
        self.publish('accounting', member, receipt, members=members, pins=pins)
        item, raw, verified = checked_archive(self.publication, 'accounting')
        self.assertEqual((item['declared_reserve_sats'], item['outstanding_claims_sats'], item['pending_issuance_sats']),
                         (25_000, 24_000, 1_000))
        self.assertEqual((item['network'], item['tip_hash'], json.loads(verified)), ('regtest', tip, receipt))
        self.assertEqual(raw, self.zip.read_bytes())
        for field in ('registry_sha256', 'tip_hash', 'nova_verifier_key_sha256', 'blocks_sha256'):
            with self.subTest(field=field), self.assertRaisesRegex(Refused, 'recovery_evidence_unverified'):
                self.publish('accounting', member, receipt, members=members, pins=pins | {field: '99' * 32})
                checked_archive(self.publication, 'accounting')
        for changed_members, changed_receipt in (
            (members | {proof_member: b'x' * len(proof)}, receipt),
            (members, receipt | {'pending_issuance_sats': 999}),
        ):
            self.publish('accounting', member, changed_receipt, members=changed_members, pins=pins)
            with self.assertRaisesRegex(Refused, 'recovery_evidence_unverified'):
                checked_archive(self.publication, 'accounting')
        self.publish('refusal', 'refusal-receipt.json', self.refusal_fixture())
        with self.assertRaisesRegex(Refused, 'recovery_accounting_not_configured'):
            checked_archive(self.publication, 'accounting')

    def test_issuance_archive_matches_the_holder_and_offline_verifiers(self):
        issuer = {'dleq_verified': True, 'batch_bound': True, 'offline_keyset_audit': True,
                  'proof_count': 6, 'amount_sats': 25000}
        proof = {'operations': ['register', 'issue', 'redeem'], 'verified': True,
                 'declared_reserve_sats': 0, 'outstanding_claims_sats': 0,
                 'proof_sha256': '44' * 32, 'verifier_key_sha256': '55' * 32}
        bitcoin = {'claim_id': self.claim, 'payout_txid': self.txid, 'payout_wtxid': self.wtxid,
                   'network': 'regtest', 'reserve_sats': 25000, 'payout_sats': 24750,
                   'holder_signature_verified': True, 'witness_inclusion_verified': True}
        receipt = {'schema': 'proof-grove/protected-withdrawal-issuance-audit/v1', 'nova': proof,
                   'issuance': {'claim': self.claim, 'amount_sats': 25000, 'independent_verifier': issuer},
                   'bitcoin_payout': bitcoin}
        self.publish('issuance', 'verification.json', receipt)
        result, raw, verification = checked_archive(self.publication, 'issuance')
        self.assertIsNone(verification)
        self.assertEqual((result['issued_sats'], result['proof_count'], raw), (25000, 6, self.zip.read_bytes()))
        self.zip.write_bytes(raw + b' ')
        with self.assertRaisesRegex(Refused, 'recovery_evidence_archive_changed'):
            checked_archive(self.publication, 'issuance')
        self.publish('issuance', 'verification.json', receipt, holder_txid='99' * 32)
        with self.assertRaisesRegex(Refused, 'recovery_evidence_unverified'):
            checked_archive(self.publication, 'issuance')

    def refusal_fixture(self):
        chain = {'network': 'regtest', 'height': 219, 'anchor': '44' * 32, 'archive_sha256': '55' * 32}
        return {'schema': 'proof-grove/m14/funded-withdrawal-refusal/v1',
                'holder_payout': {'txid': self.txid, 'wtxid': self.wtxid, 'sats': 24750, 'height': 212, 'fee_sats': 250},
                'collateral_timeout': {'txid': '66' * 32, 'sats': 24750, 'height': 219, 'block': chain['anchor'], 'fee_sats': 500},
                'collateral': {'height': 211}, 'joint_package': {'authorization': {'cashu_claim_id': self.claim, 'timeout_blocks': 8}},
                'independent_chain_replay': chain.copy(), 'published_chain': chain, 'verdict_supplied': False,
                'wallets_loaded_during_settlement': 0,
                'controls': {'early_timeout': {'allowed': False}, 'substituted_timeout_beneficiary': {'allowed': False},
                             'timeout_reorg_restored_only_collateral': True}}

    def test_refusal_requires_matching_replay_and_no_verdict(self):
        receipt = self.refusal_fixture()
        chain = receipt['published_chain']
        self.publish('refusal', 'refusal-receipt.json', receipt)
        result, _, verification = checked_archive(self.publication, 'refusal')
        self.assertEqual((result['holder_sats'], result['challenger_sats'], result['timeout_blocks']), (24750, 24750, 8))
        self.assertIsNone(verification)
        self.assertNotIn('independent_replay_verified', result)
        for extra in ({'verdict_supplied': True}, {'independent_chain_replay': chain | {'height': 218}}):
            with self.subTest(extra=extra):
                self.publish('refusal', 'refusal-receipt.json', receipt | extra)
                with self.assertRaisesRegex(Refused, 'recovery_evidence_unverified'):
                    checked_archive(self.publication, 'refusal')

    def configure_independent_refusal(self):
        statement = b'{"fixture":true}'
        receipt = self.refusal_fixture()
        self.publish('refusal', 'refusal-receipt.json', receipt, statement=statement)
        published = json.loads(self.publication.read_bytes())
        verification = {'schema': 'proof-grove/m14/independent-refusal-verification/v1', 'network': 'regtest',
                        'archive_sha256': published['refusal']['sha256'], 'claim_id': self.claim, 'wallets_loaded': 0,
                        'statement_sha256': hashlib.sha256(statement).hexdigest(), 'verdict_supplied': False,
                        'bitcoin': receipt['published_chain'] | {'schema': 'proof-grove/protected-regtest-block-replay/v1',
                                                                 'blocks_submitted': 219},
                        'holder_payout': receipt['holder_payout'], 'collateral_timeout': receipt['collateral_timeout'],
                        'early_timeout_rejected': True, 'substituted_beneficiary_rejected': True,
                        'timeout_reorg_restored_only_collateral': True}
        return verification, published

    def save_verification(self, verification, publication):
        path = self.publication.with_name('refusal-verification.json')
        raw = json.dumps(verification).encode()
        path.write_bytes(raw)
        publication['refusal'].update(verification=path.name, verification_sha256=hashlib.sha256(raw).hexdigest())
        self.publication.write_text(json.dumps(publication), encoding='utf-8')
        return path, raw

    def test_downloads_matching_independent_refusal_receipt_from_http(self):
        verification, publication = self.configure_independent_refusal()
        path, raw = self.save_verification(verification, publication)
        with make_server(Desk(config={'protected_evidence_preview': self.publication}), 0) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            endpoint = f'http://127.0.0.1:{server.server_port}/api/protected/preview/evidence/refusal'
            try:
                with urlopen(endpoint, timeout=5) as response:
                    result = json.load(response)
                self.assertEqual((result['independent_replay_verified'], result['blocks_replayed'],
                                 result['refusal_holder_height'], result['refusal_timeout_height']), (True, 219, 212, 219))
                with urlopen(endpoint + '/verification', timeout=5) as response:
                    self.assertEqual(response.read(), raw)
                path.write_bytes(raw + b' ')
                with self.assertRaises(HTTPError) as refused:
                    urlopen(endpoint + '/verification', timeout=5)
                self.assertEqual(json.loads(refused.exception.read())['error'], 'recovery_evidence_verification_changed')
            finally:
                server.shutdown()
                thread.join(5)

    def test_refuses_rehashed_receipt_from_another_claim_statement_or_chain(self):
        verification, publication = self.configure_independent_refusal()
        for changed in ({'claim_id': '77' * 32}, {'statement_sha256': '78' * 32}, {'archive_sha256': '79' * 32},
                        {'bitcoin': verification['bitcoin'] | {'anchor': '80' * 32}},
                        {'holder_payout': verification['holder_payout'] | {'fee_sats': 251}},
                        {'substituted_beneficiary_rejected': False}):
            with self.subTest(changed=changed):
                self.save_verification(verification | changed, publication)
                with self.assertRaisesRegex(Refused, 'recovery_evidence_unverified'):
                    checked_archive(self.publication, 'refusal')
