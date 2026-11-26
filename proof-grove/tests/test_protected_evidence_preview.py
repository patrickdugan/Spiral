import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen
from zipfile import ZipFile

from proofdesk.domain import Refused
from proofdesk.protected_evidence_preview import REFUSAL_STATEMENT, checked_archive
from proofdesk.server import Desk, make_server


class RecoveryEvidenceTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.publication = Path(scratch.name) / 'preview.json'
        self.zip = self.publication.with_name('archive.zip')
        self.claim, self.txid, self.wtxid = ('11' * 32, '22' * 32, '33' * 32)

    def publish(self, case, member, receipt, *, statement=None, **changes):
        with ZipFile(self.zip, 'w') as source:
            source.writestr(member, json.dumps(receipt))
            if statement is not None:
                source.writestr(REFUSAL_STATEMENT, statement)
        manifest = {'schema': 'proof-grove/protected-recovery-evidence/v1', 'claim_id': self.claim,
                    'holder_txid': self.txid, 'holder_wtxid': self.wtxid,
                    case: {'file': self.zip.name, 'sha256': hashlib.sha256(self.zip.read_bytes()).hexdigest()}}
        self.publication.write_text(json.dumps(manifest | changes), encoding='utf-8')

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
