"""Synthetic policy and observer tests. These never fund a real wallet."""
import copy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import clock_observer as observer
import experiment as e


def state_fixture():
    ids = {n: '02' + str(i+1)*64 for i, n in enumerate('abcd')}
    state = {'stable_tip': True, 'peers': {n: {'getinfo': {'id': ids[n]},
        'listpeerchannels': {'channels': []}} for n in 'abcd'}, 'funding_outputs': {}}
    for i, (left, right) in enumerate(e.EDGES):
        txid = str(i+1)*64
        state['funding_outputs'][txid+':0'] = {'utxo': {'confirmations': 3, 'value': Decimal('0.001')}}
        for a, b in [(left, right), (right, left)]:
            state['peers'][a]['listpeerchannels']['channels'].append({'peer_id': ids[b],
                'state': 'CHANNELD_NORMAL', 'htlcs': [], 'total_msat': 100000000,
                'to_us_msat': 50000000, 'funding_txid': txid, 'funding_outnum': 0,
                'short_channel_id': f'100x{i}x0', 'spendable_msat': 49000000,
                'fee_base_msat': 1000, 'fee_proportional_millionths': 10})
    return state, ids


class ObserverTests(unittest.TestCase):
    def test_public_notification_omits_secrets_and_arbitrary_new_fields(self):
        value = {'sendpay_failure': {'code': 204, 'message': 'may contain private data',
            'data': {'payment_hash': 'a'*64, 'payment_preimage': 'SECRET', 'bolt11': 'SECRET',
                     'onionreply': 'SECRET', 'failcode': 42, 'future_secret': 'SECRET'}}}
        public = observer.public_payload(value)
        self.assertNotIn('SECRET', json.dumps(public))
        self.assertNotIn('message', public['sendpay_failure'])
        self.assertEqual(public['sendpay_failure']['data']['failcode'], 42)

    def test_append_restart_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'events.jsonl'
            journal = observer.Journal(path)
            journal.append('forward_event', {'payment_hash': 'a'*64, 'status': 'offered'})
            observer.Journal(path).append('forward_event', {'payment_hash': 'a'*64, 'status': 'settled'})
            self.assertEqual(observer.Journal(path).sequence, 2)
            path.write_text(path.read_text().replace('offered', 'failed'))
            with self.assertRaisesRegex(ValueError, 'inconsistent'):
                observer.Journal(path)

    def test_collector_registers_no_payment_hook(self):
        import io
        source = io.StringIO(json.dumps({'id': 1, 'method': 'getmanifest'})+'\n')
        out = io.StringIO()
        with patch.object(observer.sys, 'stdin', source), patch.object(observer.sys, 'stdout', out):
            observer.main()
        result = json.loads(out.getvalue())['result']
        self.assertEqual(result['hooks'], [])
        self.assertEqual(set(result['subscriptions']), set(observer.TOPICS))


class ExperimentTests(unittest.TestCase):
    def test_schedule_balances_each_path_and_limits_workload(self):
        jobs = [e.schedule(i) for i in range(200)]
        self.assertEqual(sum(j['amount_msat'] for j in jobs), 300000000)
        for middle in 'bc':
            values = {source: sum(j['amount_msat'] for j in jobs if j['source'] == source and j['middle'] == middle) for source in 'ad'}
            self.assertEqual(values, {'a': 75000000, 'd': 75000000})
        for i in [-1, 200, True]:
            with self.assertRaises(ValueError):
                e.schedule(i)
        self.assertEqual(sum(e.ALLOCATIONS.values()), 500000)

    def test_hard_stop_uses_both_clocks_and_rejects_reboot(self):
        manifest = {'boot_id': 'test', 'deadline_unix_ns': '100', 'deadline_monotonic_ns': '200'}
        e.guard(manifest, 99, 199, 'test')
        for wall, mono, boot in [(100, 0, 'test'), (0, 200, 'test'), (0, 0, 'different')]:
            with self.assertRaises(RuntimeError):
                e.guard(manifest, wall, mono, boot)

    def test_monetary_intent_is_durable_before_call_and_never_repeated(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(e, 'RUN', Path(tmp)), patch.object(e, 'manifest', return_value={}), patch.object(e, 'guard'):
            def fn():
                self.assertTrue((Path(tmp)/'action-test.intent.json').exists())
                raise TimeoutError('response lost')
            execute = Mock(side_effect=fn)
            with self.assertRaises(TimeoutError):
                e.action('test', 'sendpay', execute)
            with self.assertRaises(FileExistsError):
                e.action('test', 'sendpay', execute)
            execute.assert_called_once()
            self.assertTrue((Path(tmp)/'action-test.uncertain.json').exists())

    def test_route_uses_exact_fee_scid_direction_and_cltv(self):
        state, ids = state_fixture()
        channels = e.channel_map(state)
        route, fee = e.make_route(e.schedule(0), channels, ids, 18, 6)
        self.assertEqual(fee, 1010)
        self.assertEqual(route[0]['amount_out_msat'], 1001010)
        self.assertEqual([r['cltv_out'] for r in route], [24, 18])
        self.assertEqual(route[0]['short_channel_id_dir'], '100x0x0/0')
        reverse, _ = e.make_route(e.schedule(1), channels, ids, 18, 6)
        self.assertTrue(reverse[0]['short_channel_id_dir'].endswith('/1'))
        channels['a', 'b']['spendable_msat'] = 1000000
        with self.assertRaisesRegex(RuntimeError, 'capacity'):
            e.make_route(e.schedule(0), channels, ids, 18, 6)

    def test_immediate_rpc_failure_code_is_preserved_without_resubmission(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(e, 'RUN', Path(tmp)), patch.object(e, 'manifest', return_value={}), patch.object(e, 'guard'):
            fn = Mock(side_effect=e.RPCError({'code': 204, 'data': {'failcode': 16399}}))
            with self.assertRaises(e.RPCError):
                e.action('rejected', 'sendpay', fn)
            evidence = json.loads((Path(tmp)/'action-rejected.uncertain.json').read_text())
            self.assertEqual(evidence['rpc_error']['data']['failcode'], 16399)
            with self.assertRaises(FileExistsError):
                e.action('rejected', 'sendpay', fn)
            fn.assert_called_once()

    def test_settlement_reconciles_both_endpoints_and_internal_fees(self):
        before, _ = state_fixture(); after = copy.deepcopy(before)
        job = e.schedule(0); fee = 1010
        mapped = e.channel_map(after)
        for edge, delta in {('a','b'): -1001010, ('b','a'): 1001010, ('b','d'): -1000000, ('d','b'): 1000000}.items():
            mapped[edge]['to_us_msat'] += delta
        result = e.reconcile(before, after, job, fee, True)
        self.assertEqual(result['delivered_msat'], 1000000)
        self.assertEqual(result['routing_fee_msat'], 1010)
        mapped['a', 'b']['to_us_msat'] += 1
        mapped['b', 'a']['to_us_msat'] -= 1
        with self.assertRaisesRegex(RuntimeError, 'discrepancy'):
            e.reconcile(before, after, job, fee, True)

    def test_failed_payment_must_leave_all_balances_unchanged(self):
        before, _ = state_fixture()
        self.assertEqual(e.reconcile(before, copy.deepcopy(before), e.schedule(0), 1010, False)['delivered_msat'], 0)
        after = copy.deepcopy(before); mapped = e.channel_map(after)
        mapped['b', 'd']['to_us_msat'] -= 1; mapped['d', 'b']['to_us_msat'] += 1
        with self.assertRaises(RuntimeError):
            e.reconcile(before, after, e.schedule(0), 1010, False)

    def test_activation_rejects_underconfirmed_unbalanced_or_busy_channels(self):
        base, _ = state_fixture()
        changes = [lambda s: s.update(stable_tip=False),
            lambda s: next(iter(s['funding_outputs'].values()))['utxo'].update(confirmations=2),
            lambda s: s['peers']['a']['listpeerchannels']['channels'][0].update(htlcs=[{'id': 1}]),
            lambda s: s['peers']['a']['listpeerchannels']['channels'][0].update(to_us_msat=1),
            lambda s: s['peers']['a']['listpeerchannels']['channels'].pop()]
        for change in changes:
            state = copy.deepcopy(base); change(state)
            with self.assertRaises(RuntimeError):
                e.channel_map(state)


if __name__ == '__main__':
    unittest.main()
