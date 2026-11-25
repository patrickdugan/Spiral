from copy import deepcopy
import unittest

from proofdesk.domain import Refused
from proofdesk.protected_rollover import _match_transaction


class RolloverTransactionTests(unittest.TestCase):
    def test_split_binds_input_sequences_output_order_and_amounts(self):
        parent = {'funding': {'txid': 'a' * 64, 'vout': 2}, 'plan': {'delay_blocks': 6}}
        children = [{'reserve_sats': 12_000, 'funding_script': '0020' + 'b' * 64},
                    {'reserve_sats': 12_750, 'funding_script': '0020' + 'c' * 64}]
        source = {'txid': 'a' * 64, 'vout': 2, 'sequence': 6, 'scriptSig': {'hex': ''}}
        tx = {'version': 2, 'locktime': 0, 'vin': [source], 'vout': [
            {'n': index, 'value': amount, 'scriptPubKey': {'hex': child['funding_script']}}
            for index, (amount, child) in enumerate(zip(('0.00012000', '0.00012750'), children, strict=True))]}
        self.assertEqual(_match_transaction(tx, parent, children), source)

        for key, change in [('txid', 'd' * 64), ('vout', 3), ('sequence', 5), ('scriptSig', {'hex': '01'})]:
            with self.subTest(field=key), self.assertRaisesRegex(Refused, 'protected_rollover_transaction_mismatch'):
                modified = deepcopy(tx)
                modified['vin'][0][key] = change
                _match_transaction(modified, parent, children)

        for key, change in [('n', 0), ('value', '0.00012751'), ('scriptPubKey', {'hex': children[0]['funding_script']})]:
            with self.subTest(field=key), self.assertRaisesRegex(Refused, 'protected_rollover_transaction_mismatch'):
                modified = deepcopy(tx)
                modified['vout'][1][key] = change
                _match_transaction(modified, parent, children)

        for modified in (tx | {'locktime': 1}, tx | {'version': 1}, tx | {'vout': tx['vout'][::-1]},
                         tx | {'vout': tx['vout'] + tx['vout'][:1]}, tx | {'vin': [source, source]}):
            with self.assertRaisesRegex(Refused, 'protected_rollover_transaction_mismatch'):
                _match_transaction(modified, parent, children)


if __name__ == '__main__':
    unittest.main()
