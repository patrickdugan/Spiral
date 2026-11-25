import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from proofdesk.domain import Refused
from proofdesk.protected_evidence_preview import checked_archive


class RecoveryEvidenceTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.publication = Path(scratch.name) / 'preview.json'
        self.zip = self.publication.with_name('archive.zip')
        self.claim, self.txid, self.wtxid = ('11' * 32, '22' * 32, '33' * 32)

    def publish(self, case, member, receipt, **changes):
        with ZipFile(self.zip, 'w') as source:
            source.writestr(member, json.dumps(receipt))
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
        result, raw = checked_archive(self.publication, 'issuance')
        self.assertEqual((result['issued_sats'], result['proof_count'], raw), (25000, 6, self.zip.read_bytes()))
        self.zip.write_bytes(raw + b' ')
        with self.assertRaisesRegex(Refused, 'recovery_evidence_archive_changed'):
            checked_archive(self.publication, 'issuance')
        self.publish('issuance', 'verification.json', receipt, holder_txid='99' * 32)
        with self.assertRaisesRegex(Refused, 'recovery_evidence_unverified'):
            checked_archive(self.publication, 'issuance')

    def test_refusal_requires_matching_replay_and_no_verdict(self):
        chain = {'network': 'regtest', 'height': 219, 'anchor': '44' * 32, 'archive_sha256': '55' * 32}
        receipt = {'schema': 'proof-grove/m14/funded-withdrawal-refusal/v1',
                   'holder_payout': {'txid': self.txid, 'wtxid': self.wtxid, 'sats': 24750, 'height': 212, 'fee_sats': 250},
                   'collateral_timeout': {'txid': '66' * 32, 'sats': 24750, 'height': 219, 'block': chain['anchor'], 'fee_sats': 500},
                   'collateral': {'height': 211}, 'joint_package': {'authorization': {'cashu_claim_id': self.claim, 'timeout_blocks': 8}},
                   'independent_chain_replay': chain.copy(), 'published_chain': chain, 'verdict_supplied': False,
                   'wallets_loaded_during_settlement': 0,
                   'controls': {'early_timeout': {'allowed': False}, 'substituted_timeout_beneficiary': {'allowed': False},
                                'timeout_reorg_restored_only_collateral': True}}
        self.publish('refusal', 'refusal-receipt.json', receipt)
        result, _ = checked_archive(self.publication, 'refusal')
        self.assertEqual((result['holder_sats'], result['challenger_sats'], result['timeout_blocks']), (24750, 24750, 8))
        for extra in ({'verdict_supplied': True}, {'independent_chain_replay': chain | {'height': 218}}):
            with self.subTest(extra=extra):
                self.publish('refusal', 'refusal-receipt.json', receipt | extra)
                with self.assertRaisesRegex(Refused, 'recovery_evidence_unverified'):
                    checked_archive(self.publication, 'refusal')
