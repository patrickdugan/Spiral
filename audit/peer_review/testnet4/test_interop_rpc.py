"""Synthetic transport tests. No real RPC, wallet or transaction is used."""
import json
import subprocess
import unittest
from unittest.mock import Mock
import interop_rpc as p


class InteropTests(unittest.TestCase):
    def setUp(self):
        self.config = {'cli': '/trusted/bitcoin-cli.exe', 'datadir': 'C:\\private\\core'}
        self.run = Mock(return_value=subprocess.CompletedProcess([], 0, '{"amount":0.00000001}', ''))

    def call(self, method, params=None):
        return json.loads(p.dispatch(self.config, {'id': 42, 'method': method, 'params': params or []}, self.run))

    def test_denies_wallet_control_and_broadcast_by_default(self):
        for method in ['sendtoaddress', 'dumpprivkey', 'stop', 'loadwallet', 'sendrawtransaction']:
            self.assertEqual(self.call(method)['error']['code'], -32601)
        self.run.assert_not_called()

    def test_rejects_cli_option_injection(self):
        for value in ['-rpcwallet=personal', '-rpcconnect=example.com', 'abc\n-rpcpassword=secret']:
            self.assertEqual(self.call('getblock', [value])['error']['code'], -32602)
        self.run.assert_not_called()

    def test_scalar_and_decimal_results_preserved(self):
        raw = p.dispatch(self.config, {'id': 'x', 'method': 'gettxout', 'params': ['a'*64, 0]}, self.run)
        self.assertIn('0.00000001', raw)
        self.assertEqual(self.run.call_args.args[0], ['/trusted/bitcoin-cli.exe', '-datadir=C:\\private\\core', '-testnet4', 'gettxout', 'a'*64, '0'])
        self.run.return_value.stdout = 'b'*64 + '\n'
        self.assertEqual(self.call('getblockhash', [0])['result'], 'b'*64)
        self.run.return_value.stdout = '0'*64 + '\n'
        self.assertEqual(self.call('getblockhash', [0])['result'], '0'*64)

    def test_core_error_retains_code_without_private_stderr(self):
        self.run.return_value = subprocess.CompletedProcess([], 1, '', 'error code: -5\nerror message:\nPRIVATE')
        result = self.call('getrawtransaction', ['b'*64])
        self.assertEqual(result['error']['code'], -5)
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_uncertain_broadcast_is_not_retried(self):
        self.config['allow_broadcast'] = True
        self.run.side_effect = subprocess.TimeoutExpired('PRIVATE', 45)
        result = self.call('sendrawtransaction', ['00'])
        self.assertIn('uncertain', result['error']['message'])
        self.run.assert_called_once()

    def test_malformed_rpc_cannot_invoke_cli(self):
        for request in [[], {'method': 'getblock', 'params': {}}, {'method': ['getblock']}, {'id': {}, 'method': 'getblock'}]:
            self.assertIsNotNone(json.loads(p.dispatch(self.config, request, self.run))['error'])
        self.run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
