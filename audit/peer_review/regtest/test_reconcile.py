"""Adversarial checks against the captured graph, independent of live daemons."""
import json
import unittest
from reconcile import ROOT, reconcile


class ObservedGraphTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = json.loads((ROOT / 'recovered-output-reused.json').read_text())
        self.initial = json.loads((ROOT / 'initial-funding.json').read_text())

    def test_complete_fixture_conserves_every_sat(self):
        result = reconcile(self.snapshot, self.initial)
        self.assertEqual(result['operator_remaining_economic_sat'] + result['client_remaining_onchain_sat'] +
                         result['recipient_channel_share_sat'] + result['all_miner_fees_sat'], 2200000)

    def test_unspent_amount_tampering_is_rejected(self):
        for value in self.snapshot['unspent_outputs'].values():
            if value:
                value['value'] = '0.00000001'
                break
        with self.assertRaises(AssertionError):
            reconcile(self.snapshot, self.initial)

    def test_missing_ancestry_is_rejected(self):
        proof = json.loads((ROOT / 'reuse-proof.json').read_text())
        del self.snapshot['transactions'][proof['sweep_txid']]
        with self.assertRaises(ValueError):
            reconcile(self.snapshot, self.initial)

    def test_channel_double_count_is_rejected(self):
        self.snapshot['channels']['channels'][0]['total_msat'] += 1000
        with self.assertRaises(AssertionError):
            reconcile(self.snapshot, self.initial)

    def test_unbacked_client_claim_is_rejected(self):
        for claim in self.snapshot['bark_vtxos']:
            if claim['state']['type'] == 'spendable':
                claim['chain_anchor'] = 'nonexistent:0'
        with self.assertRaises(AssertionError):
            reconcile(self.snapshot, self.initial)


if __name__ == '__main__':
    unittest.main()
