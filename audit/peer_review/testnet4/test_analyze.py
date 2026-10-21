"""Adversarial offline checks; synthetic data is never live testnet evidence."""
import copy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import analyze as a
import clock_observer
from test_experiment import state_fixture


def graph_fixture():
    initial = [{'txid': '1'*64, 'vout': 0, 'amount': '0.00510000'}]
    allocation = {'txid': '2'*64, 'vin': [{'txid': '1'*64, 'vout': 0}],
        'vout': [{'n': 0, 'value': '0.00230000'}, {'n': 1, 'value': '0.00270000'}, {'n': 2, 'value': '0.00009000'}]}
    channel = {'txid': '3'*64, 'vin': [{'txid': '2'*64, 'vout': 0}],
        'vout': [{'n': 0, 'value': '0.00100000'}, {'n': 1, 'value': '0.00129500'}]}
    leaves = [{'txid': '2'*64, 'vout': 1, 'amount_sat': 270000}, {'txid': '2'*64, 'vout': 2, 'amount_sat': 9000},
        {'txid': '3'*64, 'vout': 0, 'amount_sat': 100000}, {'txid': '3'*64, 'vout': 1, 'amount_sat': 129500}]
    return initial, [allocation, channel], leaves


def sample(start, end, active):
    return {'start_ns': str(start), 'end_ns': str(end), 'channels': [{'htlcs': [
        {'payment_hash': 'hash', 'direction': 'out', 'amount_msat': 1001010}] if active else []}]}


def payment_fixture():
    before, ids = state_fixture(); after = copy.deepcopy(before)
    # Construct expected independent transfers, without using the runner reducer.
    changes = {('a','b'): -1001010, ('b','a'): 1001010, ('b','d'): -1000000, ('d','b'): 1000000}
    inverse = {value: key for key,value in ids.items()}
    for node, data in after['peers'].items():
        for channel in data['listpeerchannels']['channels']:
            channel['to_us_msat'] += changes.get((node, inverse[channel['peer_id']]), 0)
    preimage = '01'*32; payment_hash = hashlib.sha256(bytes.fromhex(preimage)).hexdigest()
    return {'index': 0, 'job': {'source': 'a', 'destination': 'd', 'middle': 'b', 'amount_msat': 1000000},
        'payment_hash': payment_hash, 'before': before, 'after': after,
        'route': [{'node_id_out': ids['b'], 'amount_out_msat': 1001010, 'short_channel_id_dir': '100x0x0/0', 'cltv_out': 24},
                  {'node_id_out': ids['d'], 'amount_out_msat': 1000000, 'short_channel_id_dir': '100x2x0/0', 'cltv_out': 18}],
        'cltv_policy': {'invoice_min_final': 18, 'middle_delta': 6},
        'authoritative_payment': {'payment_hash': payment_hash, 'status': 'complete', 'amount_msat': 1000000,
            'amount_sent_msat': 1001010, 'payment_preimage': preimage}}


def empty_run_fixture():
    initial = [{'txid': '1'*64, 'vout': 0, 'amount': '0.00510000', 'spendable': True}]
    event = {'sequence': 1, 'previous_sha256': '0'*64, 'observer_monotonic_ns': '1',
        'observer_unix_ns': '1', 'topic': 'observer_started', 'payload': {}}
    event['sha256'] = hashlib.sha256(json.dumps(event, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    peers = {n: {'getinfo': {'id': '02'+str(i+1)*64, 'network': 'testnet4'},
        'listfunds': {'outputs': [], 'channels': []}, 'listpeerchannels': {'channels': []}} for i,n in enumerate('abcd')}
    return {'manifest': {'preflight': {'status':'eligible_for_funding_cycle',
        'genesis':'00000000da84f2bafbbc53dee25a72ae507ff4914b867c565be350b0da8bf043'}, 'boot_id':'synthetic',
        'start_monotonic_ns':'10', 'deadline_monotonic_ns':'1000', 'deadline_unix_ns':'1000'},
        'capture_boot_id':'synthetic', 'allocation_txid':None, 'allocation_addresses':{},
        'initial_utxos':initial, 'core_wallet_utxos':initial, 'transactions':[],
        'owned_leaves':[{'txid':'1'*64,'vout':0,'amount_sat':510000,'kind':'wallet','owner':'core'}],
        'final_snapshot':{'stable_tip':True, 'core_before':{'chain':'testnet4'}, 'core_after':{'chain':'testnet4'},
            'peers':peers, 'funding_outputs':{}}, 'payments':[], 'attempts':[],
        'observers':{n:[json.dumps(event)] for n in 'abcd'}}


def terminal_run_fixture():
    bundle = empty_run_fixture()
    bundle['manifest']['deadline_monotonic_ns'] = '1000000'
    bundle['manifest']['deadline_unix_ns'] = '1000000'
    addresses = {n:'address-'+n for n in 'abcd'}
    allocation = {'txid':'2'*64, 'vin':[{'txid':'1'*64,'vout':0}], 'vout':[]}
    for index, (node, value) in enumerate([('a','0.0023'),('b','0.0013'),('c','0.0013'),('d','0.0001')]):
        allocation['vout'].append({'n':index,'value':value,'scriptPubKey':{'address':addresses[node]}})
    allocation['vout'].append({'n':4,'value':'0.00009','scriptPubKey':{'address':'core-change'}})
    txs = [allocation]
    for char, parent, number, change in [('3','2',0,'0.001295'),('4','3',1,'0.00029'),('5','2',1,'0.000295'),('6','2',2,'0.000295')]:
        txs.append({'txid':char*64,'vin':[{'txid':parent*64,'vout':number}],
            'vout':[{'n':0,'value':'0.001'},{'n':1,'value':change}]})
    current, ids = state_fixture(); current['funding_outputs'] = {}
    edges = [('a','b'),('a','c'),('b','d'),('c','d')]
    for i,(left,right) in enumerate(edges):
        txid = str(i+3)*64
        current['funding_outputs'][txid+':0'] = {'utxo':{'confirmations':3,'value':'0.001'}}
        for node, peer in [(left,right),(right,left)]:
            channel = next(c for c in current['peers'][node]['listpeerchannels']['channels'] if c['peer_id'] == ids[peer])
            channel['funding_txid'] = txid
    current.update(core_before={'chain':'testnet4'},core_after={'chain':'testnet4'})
    wallet = {'a':('4',1,29000),'b':('5',1,29500),'c':('6',1,29500),'d':('2',3,10000)}
    leaves = [{'txid':'2'*64,'vout':4,'amount_sat':9000,'kind':'wallet','owner':'core'}]
    for node,(char,number,value) in wallet.items():
        current['peers'][node]['getinfo']['network'] = 'testnet4'
        current['peers'][node]['listfunds'] = {'outputs':[{'txid':char*64,'output':number,'amount_msat':value*1000,'status':'confirmed'}], 'channels':[]}
        leaves.append({'txid':char*64,'vout':number,'amount_sat':value,'kind':'wallet','owner':node})
    leaves += [{'txid':str(i+3)*64,'vout':0,'amount_sat':100000,'kind':'channel','owner':'controlled_pair'} for i in range(4)]
    bundle.update(transactions=txs, allocation_txid='2'*64, allocation_addresses=addresses, owned_leaves=leaves,
        core_wallet_utxos=[{'txid':'2'*64,'vout':4,'amount':'0.00009','spendable':True}])
    inverse = {value:key for key,value in ids.items()}
    for index in range(200):
        src,dst = ('a','d') if index % 2 == 0 else ('d','a')
        mid = 'b' if index % 8 < 4 else 'c'
        amount = 1000000 if index % 4 < 2 else 2000000; fee = 1000+amount//100000
        before = copy.deepcopy(current)
        changes = {(src,mid):-(amount+fee),(mid,src):amount+fee,(mid,dst):-amount,(dst,mid):amount}
        for node,data in current['peers'].items():
            for c in data['listpeerchannels']['channels']:
                c['to_us_msat'] += changes.get((node,inverse[c['peer_id']]),0)
        request = 100+index*1000
        current.update(start_monotonic_ns=str(request+50),end_monotonic_ns=str(request+60))
        preimage = hashlib.sha256(str(index).encode()).hexdigest()
        payment_hash = hashlib.sha256(bytes.fromhex(preimage)).hexdigest()
        route = []
        for x,y,value,cltv in [(src,mid,amount+fee,24),(mid,dst,amount,18)]:
            c = next(c for c in before['peers'][x]['listpeerchannels']['channels'] if c['peer_id']==ids[y])
            route.append({'node_id_out':ids[y],'amount_out_msat':value,'cltv_out':cltv,
                'short_channel_id_dir':c['short_channel_id']+('/0' if ids[x]<ids[y] else '/1')})
        job = {'source':src,'destination':dst,'middle':mid,'amount_msat':amount}
        bundle['payments'].append({'index':index,'job':job,'before':before,'after':copy.deepcopy(current),
            'payment_hash':payment_hash,'route':route,'cltv_policy':{'invoice_min_final':18,'middle_delta':6},
            'authoritative_payment':{'payment_hash':payment_hash,'status':'complete','amount_msat':amount,
                'amount_sent_msat':amount+fee,'payment_preimage':preimage}})
        samples = [{'start_ns':str(request+d),'end_ns':str(request+d+5),'channels':[{'htlcs':[
            {'payment_hash':payment_hash,'direction':'out','amount_msat':amount+fee}] if active else []}]} for d,active in [(-10,False),(10,True),(30,False)]]
        bundle['attempts'].append({'index':index,'payment_hash':payment_hash,'request_ns':str(request),'request_unix_ns':str(request),
            'principal_msat':amount+fee,'saved_route':{'route':route},'samples':samples})
    bundle['final_snapshot'] = current
    return bundle


class GraphTests(unittest.TestCase):
    def test_reconstructs_fees_and_change_in_dependency_order(self):
        initial, txs, leaves = graph_fixture()
        result = a.funding_graph(initial, list(reversed(txs)), leaves)
        self.assertEqual(result['remaining_assets_sat'], 508500)
        self.assertEqual(result['miner_fees_sat'], 1500)

    def test_rejects_fresh_financing_double_spends_and_duplicate_representations(self):
        initial, txs, leaves = graph_fixture()
        cases = []
        foreign = copy.deepcopy(txs); foreign[1]['vin'][0]['txid'] = '9'*64
        cases.append((initial, foreign, leaves))
        cases.append((initial, txs+[txs[1]], leaves))
        cases.append((initial, txs, leaves+[leaves[-1]]))
        changed = copy.deepcopy(leaves); changed[-1]['amount_sat'] += 1
        cases.append((initial, txs, changed))
        for case in cases:
            with self.assertRaises(ValueError):
                a.funding_graph(*case)

    def test_exact_amounts_reject_float_and_fractional_satoshi(self):
        self.assertEqual(a.sats(Decimal('0.00000001')), 1)
        for value in [0.001, '0.000000001', 'NaN', '-1', True]:
            with self.assertRaises(ValueError):
                a.sats(value)

    def test_fee_reserve_is_enforced(self):
        initial, txs, _ = graph_fixture()
        txs[0]['vout'] = [{'n': 0, 'value': '0.003'}]
        leaves = [{'txid': '2'*64, 'vout': 0, 'amount_sat': 300000}]
        with self.assertRaisesRegex(ValueError, 'reserve'):
            a.funding_graph(initial, txs[:1], leaves)


class ClockTests(unittest.TestCase):
    def test_read_intervals_give_conservative_duration_and_capital_time(self):
        result = a.reservation_bounds([sample(0,5,False), sample(20,25,True), sample(40,45,True), sample(60,65,False)], 'hash', 10, 1001010, True)
        self.assertEqual((result['duration_lower_ns'], result['duration_upper_ns']), ('15','55'))
        self.assertEqual(result['capital_time_upper_msat_ns'], str(55*1001010))

    def test_missed_active_samples_do_not_mean_zero_duration(self):
        rows = [sample(0,5,False), sample(60,65,False)]
        result = a.reservation_bounds(rows, 'hash', 10, 1001010, True)
        self.assertEqual(result['classification'], 'not_captured_active')
        self.assertEqual(result['duration_upper_ns'], '55')
        self.assertIsNone(a.reservation_bounds(rows, 'hash', 10, 1001010)['duration_upper_ns'])

    def test_open_reservation_is_right_censored(self):
        result = a.reservation_bounds([sample(20,25,True), sample(40,45,True)], 'hash', 10, 1001010)
        self.assertEqual(result['classification'], 'right_censored')
        self.assertEqual(result['duration_lower_ns'], '15')
        self.assertIsNone(result['duration_upper_ns'])

    def test_reappearance_overlap_and_wrong_principal_fail(self):
        for rows, principal in [([sample(20,25,True), sample(30,35,False), sample(40,45,True)], 1001010),
                ([sample(20,35,True), sample(30,45,False)], 1001010), ([sample(20,25,True)], 1000000)]:
            with self.assertRaises(ValueError):
                a.reservation_bounds(rows, 'hash', 10, principal)


class EvidenceTests(unittest.TestCase):
    def test_full_synthetic_workload_reconciles_with_both_denominators(self):
        report = a.analyze_bundle(terminal_run_fixture())
        self.assertEqual(report['status'], 'terminal_workload_reconciled')
        self.assertEqual(report['economic_reconciliation']['miner_fees_sat'], 3000)
        self.assertEqual(report['offered_msat'], 300000000)
        self.assertEqual(report['delivered_msat'], 300000000)
        self.assertEqual(report['routing_fees_internal_msat'], 203000)
        self.assertEqual(report['value_delivery_rate'], '1')
        self.assertEqual(report['capital_time_per_offered_value_ns'], report['capital_time_per_delivered_value_ns'])

    def test_full_fixture_rejects_deadline_and_allocation_policy_mutations(self):
        for change in [lambda b: b['attempts'][0].update(request_ns='1000000'),
                       lambda b: b['attempts'][0].update(request_unix_ns='1000000'),
                       lambda b: b['transactions'][0]['vout'][0].update(value='0.00229999')]:
            bundle = terminal_run_fixture(); change(bundle)
            with self.assertRaises(ValueError):
                a.analyze_bundle(bundle)

    def test_partial_run_is_not_completion_and_zero_denominators_are_null(self):
        report = a.analyze_bundle(empty_run_fixture())
        self.assertEqual(report['status'], 'partial_run')
        self.assertEqual(report['unattempted_invoices'], 200)
        self.assertIsNone(report['value_delivery_rate'])
        self.assertIsNone(report['capital_time_per_delivered_value_ns'])
        self.assertEqual(report['economic_reconciliation']['remaining_assets_sat'], 510000)

    def test_claimed_ownership_wrong_network_or_reboot_cannot_pass(self):
        cases = [lambda b: b['owned_leaves'][0].update(owner='a'),
            lambda b: b['core_wallet_utxos'][0].update(spendable=False),
            lambda b: b['final_snapshot']['core_after'].update(chain='regtest'),
            lambda b: b.update(capture_boot_id='new-boot')]
        for change in cases:
            bundle = empty_run_fixture(); change(bundle)
            with self.assertRaises(ValueError):
                a.analyze_bundle(bundle)

    def test_route_channel_and_cltv_tampering_fail_even_if_balances_match(self):
        for change in [lambda r: r['route'][0].update(short_channel_id_dir='100x1x0/0'),
                       lambda r: r['route'][0].update(cltv_out=18)]:
            row = payment_fixture(); change(row)
            with self.assertRaises(ValueError):
                a.verify_payment(row)

    def test_independent_journal_check_detects_reordering_or_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'events'; journal = clock_observer.Journal(path)
            journal.append('block_added', {'hash': 'a'*64, 'height': 1})
            journal.append('block_added', {'hash': 'b'*64, 'height': 2})
            lines = path.read_text().splitlines()
            self.assertEqual(len(a.verify_observer(lines)), 2)
            for bad in [list(reversed(lines)), [lines[0].replace('"height":1', '"height":9'), lines[1]]]:
                with self.assertRaises(ValueError):
                    a.verify_observer(bad)

    def test_payment_proof_and_fee_conservation_are_independently_checked(self):
        row = payment_fixture()
        self.assertEqual(a.verify_payment(row)['routing_fee_msat'], 1010)
        row['authoritative_payment']['payment_preimage'] = '02'*32
        with self.assertRaisesRegex(ValueError, 'preimage'):
            a.verify_payment(row)

    def test_one_msat_leak_and_false_failed_outcome_are_rejected(self):
        row = payment_fixture()
        row['after']['peers']['a']['listpeerchannels']['channels'][0]['to_us_msat'] += 1
        row['after']['peers']['b']['listpeerchannels']['channels'][0]['to_us_msat'] -= 1
        with self.assertRaisesRegex(ValueError, 'reconcile'):
            a.verify_payment(row)
        row = payment_fixture(); row['authoritative_payment']['status'] = 'failed'
        with self.assertRaisesRegex(ValueError, 'reconcile'):
            a.verify_payment(row)

    def test_public_export_removes_private_receipt_fields(self):
        raw = {'payment_preimage':'SECRET','data':{'bolt11':'SECRET','payment_secret':'SECRET','amount_msat':1000},
            'wallet':[{'desc':'SECRET','parent_descs':['SECRET']}], 'amount':Decimal('0.00000001')}
        result = a.public(raw)
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertEqual(result['amount'], '1E-8')


if __name__ == '__main__':
    unittest.main()
