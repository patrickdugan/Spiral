"""Offline adversarial gate tests; all RPC responses are synthetic."""
import copy
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import preflight as p


def fixture():
    pins = {n: {'source_revision': '1' * 40, 'sha256': '2' * 64,
                'rpc_version': '/Satoshi:31.0.0/' if n == 'core' else 'v26.06.7'} for n in ('core', *p.NODES)}
    config = {'endpoints': {n: {'cli': ['not-a-real-cli']} for n in pins}, 'dedicated_wallet': True,
              'wallet_name': 'isolated-clock-experiment', 'fee_reserve_sat': 50000}
    ids = {n: '02' + str(i + 1) * 64 for i, n in enumerate(p.NODES)}
    chain = {'chain': 'testnet4', 'blocks': 100, 'headers': 100, 'initialblockdownload': False, 'bestblockhash': '3' * 64}
    rows = {('core', 'getblockchaininfo'): chain, ('core', 'getblockhash'): p.GENESIS,
        ('core', 'getnetworkinfo'): {'subversion': '/Satoshi:31.0.0/', 'networkactive': True, 'connections': 3},
        ('core', 'getmempoolinfo'): {'size': 0},
        ('core', 'getwalletinfo'): {'walletname': config['wallet_name'], 'private_keys_enabled': True, 'scanning': False},
        ('core', 'listlockunspent'): [],
        ('core', 'getbalances'): {'mine': {'trusted': Decimal('0.00500000'), 'untrusted_pending': 0, 'immature': 0}},
        ('core', 'listunspent'): [{'txid': '4' * 64, 'vout': 0, 'amount': Decimal('0.00500000'), 'confirmations': 6, 'spendable': True, 'safe': True}]}
    for n in p.NODES:
        rows[n, 'getinfo'] = {'network': 'testnet4', 'blockheight': 100, 'version': 'v26.06.7', 'id': ids[n],
                             'num_pending_channels': 0, 'num_active_channels': 0, 'num_inactive_channels': 0}
        rows[n, 'listfunds'] = {'outputs': [], 'channels': []}
        rows[n, 'listpeerchannels'] = {'channels': []}
        rows[n, 'listpeers'] = {'peers': [{'id': ids[next(iter(e - {n}))], 'connected': True} for e in p.EDGES if n in e]}
    return config, pins, rows


class PreflightTests(unittest.TestCase):
    def test_valid_gate_is_preflight_only(self):
        config, pins, rows = fixture()
        calls = []
        def rpc(n, method, *args):
            calls.append((n, method, args)); return copy.deepcopy(rows[n, method])
        result = p.inspect(config, rpc, pins)
        self.assertEqual(result['status'], 'eligible_for_funding_cycle')
        self.assertEqual(result['funding_sat'], 500000)
        self.assertEqual(result['hard_stop_seconds'], 172800)
        self.assertFalse(result['transaction_broadcast'])
        self.assertEqual(result['evidence_class'], 'testnet4_preflight_only')
        self.assertTrue(all(method in (p.CORE_READS if n == 'core' else p.CLN_READS) for n, method, _ in calls))

    def test_wrong_chain_funds_identity_and_topology_fail_closed(self):
        changes = [
            ('mainnet', lambda c, r: r['core', 'getblockchaininfo'].update(chain='main')),
            ('regtest', lambda c, r: r['core', 'getblockchaininfo'].update(chain='regtest')),
            ('genesis', lambda c, r: r.update({('core', 'getblockhash'): '0' * 64})),
            ('IBD', lambda c, r: r['core', 'getblockchaininfo'].update(initialblockdownload=True)),
            ('headers ahead', lambda c, r: r['core', 'getblockchaininfo'].update(headers=101)),
            ('offline', lambda c, r: r['core', 'getnetworkinfo'].update(connections=0)),
            ('wrong version', lambda c, r: r['core', 'getnetworkinfo'].update(subversion='unknown')),
            ('wrong wallet', lambda c, r: r['core', 'getwalletinfo'].update(walletname='personal-wallet')),
            ('not dedicated', lambda c, r: c.update(dedicated_wallet=False)),
            ('fee budget', lambda c, r: c.update(fee_reserve_sat=600001)),
            ('watchonly', lambda c, r: r['core', 'getbalances'].update(watchonly={'trusted': 1})),
            ('pending', lambda c, r: r['core', 'getbalances']['mine'].update(untrusted_pending=Decimal('0.00000001'))),
            ('unspendable', lambda c, r: r['core', 'listunspent'][0].update(spendable=False)),
            ('unconfirmed', lambda c, r: r['core', 'listunspent'][0].update(confirmations=0)),
            ('unsafe', lambda c, r: r['core', 'listunspent'][0].update(safe=False)),
            ('duplicate outpoint', lambda c, r: r['core', 'listunspent'].append(copy.deepcopy(r['core', 'listunspent'][0]))),
            ('locked', lambda c, r: r['core', 'listlockunspent'].append({'txid': '4' * 64, 'vout': 0})),
            ('CLN wrong chain', lambda c, r: r['a', 'getinfo'].update(network='bitcoin')),
            ('CLN behind', lambda c, r: r['a', 'getinfo'].update(blockheight=99)),
            ('CLN warning', lambda c, r: r['a', 'getinfo'].update(warning_lightningd_sync='loading')),
            ('duplicate identity', lambda c, r: r['a', 'getinfo'].update(id=r['b', 'getinfo']['id'])),
            ('CLN old funds', lambda c, r: r['a', 'listfunds']['outputs'].append({'amount_msat': 1})),
            ('CLN old channel', lambda c, r: r['a', 'listpeerchannels']['channels'].append({'state': 'ONCHAIN'})),
            ('external peer', lambda c, r: r['a', 'listpeers']['peers'].append({'id': '03' + 'a' * 64, 'connected': True})),
            ('disconnected', lambda c, r: r['a', 'listpeers']['peers'][0].update(connected=False)),
            ('missing edge', lambda c, r: r['a', 'listpeers']['peers'].pop()),
        ]
        for label, mutate in changes:
            with self.subTest(label=label):
                config, pins, rows = fixture(); mutate(config, rows)
                with self.assertRaises(ValueError):
                    p.inspect(config, lambda n, method, *args: rows[n, method], pins)

    def test_budget_both_edges_and_balance_mismatch(self):
        for amount in ['0.00449999', '0.01000001']:
            config, pins, rows = fixture()
            rows['core', 'listunspent'][0]['amount'] = Decimal(amount)
            rows['core', 'getbalances']['mine']['trusted'] = Decimal(amount)
            with self.assertRaisesRegex(ValueError, 'outside declared budget'):
                p.inspect(config, lambda n, method, *args: rows[n, method], pins)
        rows['core', 'getbalances']['mine']['trusted'] = Decimal('0.005')
        with self.assertRaisesRegex(ValueError, 'balance/UTXO mismatch'):
            p.inspect(config, lambda n, method, *args: rows[n, method], pins)

    def test_tip_race_is_not_silently_retried(self):
        config, pins, rows = fixture(); calls = 0
        def rpc(n, method, *args):
            nonlocal calls
            value = copy.deepcopy(rows[n, method])
            if method == 'getblockchaininfo':
                calls += 1
                if calls == 2:
                    value['bestblockhash'] = '5' * 64
            return value
        with self.assertRaisesRegex(ValueError, 'chain changed'):
            p.inspect(config, rpc, pins)
        self.assertEqual(calls, 2)

    def test_rpc_allowlist_and_error_redaction(self):
        cli = p.ReadonlyCLI({'core': {'cli': ['bitcoin-cli', '-rpcpassword=DO-NOT-LOG']}})
        with patch.object(p.subprocess, 'run') as run:
            for method in ['sendtoaddress', 'sendrawtransaction', 'createwallet', 'fundchannel', 'pay']:
                with self.assertRaisesRegex(ValueError, 'refused'):
                    cli('core', method)
            run.assert_not_called()
            run.return_value = subprocess.CompletedProcess([], 1, 'DO-NOT-LOG', 'DO-NOT-LOG')
            with self.assertRaisesRegex(ValueError, 'details withheld') as raised:
                cli('core', 'getblockchaininfo')
            self.assertNotIn('DO-NOT-LOG', str(raised.exception))
            run.return_value = subprocess.CompletedProcess([], 0, '{"amount":0.00000001}', '')
            self.assertEqual(cli('core', 'getbalances')['amount'], Decimal('0.00000001'))
            run.return_value = subprocess.CompletedProcess([], 0, p.GENESIS + '\n', '')
            self.assertEqual(cli('core', 'getblockhash', 0), p.GENESIS)
            self.assertNotIn('DO-NOT-LOG', json.dumps(cli.observations))

    def test_binary_digest_is_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'synthetic-binary'; path.write_bytes(b'fixture only')
            endpoint = {'pin': {'binary_path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                               'source_revision': '1' * 40, 'rpc_version': 'test'}}
            checked = p.verify_pins({'core': endpoint})
            self.assertNotIn('binary_path', checked['core'])
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'digest mismatch'):
                p.verify_pins({'core': endpoint})

    def test_exact_money_rejects_fractional_sat_and_float(self):
        self.assertEqual(p.btc_sat(Decimal('0.00000001')), 1)
        for amount in [0.01, True, '-1', 'NaN', Decimal('Infinity'), Decimal('0.000000001')]:
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                p.btc_sat(amount)

    def test_example_cannot_start_rpc_and_result_cannot_be_overwritten(self):
        example = Path(__file__).with_name('config.example.json')
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'observation.json'
            with patch.object(sys, 'argv', ['preflight', str(example), str(output)]), patch.object(p.subprocess, 'run') as run, patch('sys.stdout', new_callable=io.StringIO):
                self.assertEqual(p.main(), 2)
                run.assert_not_called()
                result = json.loads(output.read_text())
                self.assertEqual(result['status'], 'not_ready')
                self.assertFalse(result['transaction_broadcast'])
                before = output.read_bytes()
                with self.assertRaises(FileExistsError):
                    p.main()
                self.assertEqual(output.read_bytes(), before)

    def test_missing_private_configuration_is_an_explicit_failed_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'observation.json'
            with patch.object(sys, 'argv', ['preflight', str(Path(tmp) / 'missing.json'), str(output)]), patch('sys.stdout', new_callable=io.StringIO):
                self.assertEqual(p.main(), 2)
            result = json.loads(output.read_text())
            self.assertEqual(result['status'], 'not_ready')
            self.assertEqual(result['observations'], [])


if __name__ == '__main__':
    unittest.main()
