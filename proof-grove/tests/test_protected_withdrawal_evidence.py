import copy
import hashlib
import unittest
from unittest.mock import patch

from proofdesk import protected_withdrawal_evidence as withdrawal
from proofdesk.domain import digest
from proofdesk.protected_reserve import GENESIS
from test_protected_payout_evidence import OPENSSL, fixture, hash256


def example(*, bad_signature=False):
    receipt, bundle_id, _, _ = fixture(bad_signature=bad_signature)
    headers = receipt['bitcoin_chain_evidence']['headers'][:-1]
    anchor_hash = hash256(bytes.fromhex(headers[-1]))[::-1].hex()
    raw = receipt['public_transactions']['payout']
    payout = receipt['payout']
    admission = {'kind': 'authorized-regtest-withdrawal', 'bundle_id': bundle_id, 'statement': {
        'schema': withdrawal.STATEMENT, 'genesis': GENESIS, 'anchor': {'hash': anchor_hash, 'height': 109},
        'catalog_sha256': 'ab' * 32, 'confirmed_journal_sha256': 'cd' * 32, 'claim_id': receipt['claim_id'],
        'holder_pubkey': receipt['app_bundle']['plan']['holder_pubkey'], 'reserve': receipt['reserve'] | {'height': 104},
        'withdrawal': {key: payout[key] for key in ('txid', 'wtxid', 'script', 'sats', 'fee_sats')} | {
            'change_sats': 0, 'sequence': 6, 'earliest_height': 110,
            'signed_tx_sha256': hashlib.sha256(bytes.fromhex(raw)).hexdigest()},
    }}
    return {'schema': withdrawal.SCHEMA, 'bundle': receipt['app_bundle'], 'admission': admission,
            'headers': headers, 'funding_txids': receipt['bitcoin_chain_evidence']['funding_txids'],
            'funding_tx': receipt['public_transactions']['funding'], 'signed_tx': raw}


class ProtectedWithdrawalEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.evidence = example()
        self.admission = self.evidence['admission']
        self.bundle_id = self.admission['bundle_id']
        self.withdrawal_id = digest(self.admission)
        self.anchor_hash = self.admission['statement']['anchor']['hash']

    def verify(self, evidence, withdrawal_id=None):
        return withdrawal.verify(evidence, self.bundle_id, withdrawal_id or self.withdrawal_id, 109,
                                 self.anchor_hash, openssl=OPENSSL or 'openssl')

    @patch('proofdesk.protected_payout_evidence._verify_signature')
    def test_funding_inclusion_and_next_block_maturity(self, signature):
        result = self.verify(self.evidence)
        self.assertEqual(result['reserve']['sats'], 25000)
        self.assertEqual(result['withdrawal']['earliest_height'], 110)
        self.assertEqual(result['withdrawal']['sats'], 24750)
        self.assertTrue(result['funding_inclusion_verified'])
        signature.assert_called_once()

    def test_rejects_changed_anchor_header_funding_and_leaf(self):
        controls = [
            ('headers', 0, 'ff' * 80, 'headers differ'),
            ('funding_txids', 0, 'ff' * 32, 'funding output is outside'),
            ('funding_tx', None, self.evidence['funding_tx'][:-2] + '01', 'funding output is outside'),
        ]
        for field, index, value, expected in controls:
            changed = copy.deepcopy(self.evidence)
            if index is None:
                changed[field] = value
            else:
                changed[field][index] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, expected):
                self.verify(changed)
        with self.assertRaisesRegex(ValueError, 'observer pins'):
            withdrawal.verify(self.evidence, self.bundle_id, self.withdrawal_id, 109, 'ff' * 32)

    def test_captures_checkpoint_and_refuses_reorg_during_capture(self):
        headers = self.evidence['headers']
        blocks = [hash256(bytes.fromhex(header))[::-1].hex() for header in headers]
        funding = self.admission['statement']['reserve']
        leaves = self.evidence['funding_txids']

        def capture(*, reorg=False):
            anchor_reads = 0

            def rpc(method, params):
                nonlocal anchor_reads
                if method == 'getblockhash':
                    if params == [109]:
                        anchor_reads += 1
                        if reorg and anchor_reads == 2:
                            return 'ff' * 32
                    return blocks[params[0] - 104]
                if method == 'getblockheader':
                    return headers[blocks.index(params[0])]
                if method == 'getblock' and params == [funding['block'], 1]:
                    return {'hash': funding['block'], 'height': 104, 'nTx': len(leaves), 'tx': leaves}
                if method == 'getrawtransaction' and params == [funding['txid'], False, funding['block']]:
                    return self.evidence['funding_tx']
                self.fail(f'unexpected RPC {method} {params!r}')

            return withdrawal.capture(rpc, self.evidence['bundle'], self.admission, self.evidence['signed_tx'])

        self.assertEqual(capture(), self.evidence)
        with self.assertRaisesRegex(ValueError, 'chain changed during capture'):
            capture(reorg=True)

    def test_rejects_rehashed_statement_fields(self):
        controls = [
            (('genesis',), 'ff' * 32, 'observer pins'),
            (('claim_id',), 'ff' * 32, 'funded claim'),
            (('holder_pubkey',), self.evidence['bundle']['plan']['mint_pubkey'], 'funded claim'),
            (('reserve', 'height'), 105, 'funded claim'),
            (('reserve', 'sats'), 24999, 'funded claim'),
            (('reserve', 'script'), '0020' + 'ff' * 32, 'funded claim'),
            (('reserve', 'vout'), 1, 'funded claim'),
            (('withdrawal', 'script'), '0014' + 'ff' * 20, 'pinned beneficiary'),
            (('withdrawal', 'fee_sats'), 251, 'pinned beneficiary'),
            (('withdrawal', 'change_sats'), 1, 'pinned beneficiary'),
            (('withdrawal', 'sats'), 24751, 'pinned beneficiary'),
            (('withdrawal', 'sequence'), 5, 'pinned beneficiary'),
            (('withdrawal', 'earliest_height'), 109, 'pinned beneficiary'),
            (('withdrawal', 'txid'), 'ff' * 32, 'pinned beneficiary'),
            (('withdrawal', 'wtxid'), 'ff' * 32, 'pinned beneficiary'),
        ]
        for path, value, expected in controls:
            changed = copy.deepcopy(self.evidence)
            parent = changed['admission']['statement']
            for part in path[:-1]:
                parent = parent[part]
            parent[path[-1]] = value
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, expected):
                self.verify(changed, digest(changed['admission']))

    @unittest.skipUnless(OPENSSL, 'OpenSSL needed for independent signature verification')
    def test_rejects_signed_witness_with_recomputed_ids(self):
        self.assertTrue(self.verify(self.evidence)['holder_signature_verified'])
        changed = example(bad_signature=True)
        with self.assertRaisesRegex(ValueError, 'BIP143 signature verification failed'):
            self.verify(changed, digest(changed['admission']))
