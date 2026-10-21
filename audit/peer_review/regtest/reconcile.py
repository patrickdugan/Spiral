"""Offline satoshi audit of the complete observed transaction graph.

This independent check does not claim the reference reducer supports the live
retained-backing/change path. The initial mining wallet is outside the fixture;
only its three explicitly assigned funding outputs enter the graph.
"""
from pathlib import Path
from decimal import Decimal
import hashlib
import json
import sys

ROOT = Path(__file__).parent / 'evidence'


def sats(value):
    number = Decimal(str(value)) * 100000000
    if number != number.to_integral_value():
        raise ValueError('fractional onchain satoshi')
    return int(number)


def reconcile(snapshot, initial):
    records = snapshot['transactions']
    for txid, record in records.items():
        if 'unresolved' in record:
            raise ValueError(f'unresolved transaction {txid}')
    root = records[initial['txid']]['transaction']
    known, live, fees, steps = {}, {}, [], []
    address_roles = {address: role for role, address in initial['addresses'].items()}
    for output in root['vout']:
        role = address_roles.get(output['scriptPubKey'].get('address'))
        if role:
            value = sats(output['value'])
            assert value == initial['amounts_sat'][role]
            key = f"{root['txid']}:{output['n']}"
            known[key] = live[key] = {'amount_sat': value, 'owner': 'client' if role == 'bark' else 'operator', 'source': role}
    initial_sum = sum(a['amount_sat'] for a in live.values())
    assert initial_sum == sum(initial['amounts_sat'].values())
    anchors = {c['chain_anchor'] for c in snapshot['bark_vtxos']}
    pending = {k: v['transaction'] for k, v in records.items() if k != initial['txid']}
    while pending:
        progressed = False
        for txid, tx in list(pending.items()):
            inputs = [f"{v['txid']}:{v['vout']}" for v in tx['vin'] if 'txid' in v]
            if not inputs or not all(k in known for k in inputs):
                continue
            assert all(k in live for k in inputs), f'double spend in observed graph: {txid}'
            assert len(inputs) == len(set(inputs))
            owners = {live[k]['owner'] for k in inputs}
            assert len(owners) == 1, f'mixed-owner transaction needs explicit allocation: {txid}'
            owner = owners.pop()
            before = sum(live[k]['amount_sat'] for k in inputs)
            after = sum(sats(o['value']) for o in tx['vout'])
            fee = before - after
            assert fee >= 0
            for key in inputs:
                del live[key]
            outputs = []
            for output in tx['vout']:
                key = f"{txid}:{output['n']}"
                value = sats(output['value'])
                known[key] = {'amount_sat': value, 'owner': 'operator' if key in anchors else owner, 'source': txid}
                if value:
                    live[key] = known[key]
                outputs.append(key)
            fees.append({'txid': txid, 'fee_sat': fee, 'payer': owner})
            assert sum(a['amount_sat'] for a in live.values()) + sum(f['fee_sat'] for f in fees) == initial_sum
            steps.append({'txid': txid, 'inputs': inputs, 'outputs': outputs, 'fee_sat': fee})
            del pending[txid]
            progressed = True
        if not progressed:
            raise ValueError(f'incomplete transaction ancestry: {sorted(pending)}')
    for key, asset in live.items():
        observed = snapshot['unspent_outputs'].get(key)
        assert observed, f'graph leaf missing from Core UTXO set: {key}'
        assert sats(observed['value']) == asset['amount_sat']
        assert observed['confirmations'] >= 2, f'unfinalized graph leaf: {key}'
    claims = [c for c in snapshot['bark_vtxos'] if c['state']['type'] == 'spendable']
    allocated = {}
    for claim in claims:
        anchor = claim['chain_anchor']
        assert anchor in live and live[anchor]['owner'] == 'operator'
        assert claim['expiry_height'] > snapshot['chain_after']['blocks']
        allocated[anchor] = allocated.get(anchor, 0) + claim['amount_sat']
    assert all(amount <= live[key]['amount_sat'] for key, amount in allocated.items())
    balance = snapshot['bark_balance']
    assert balance['spendable_sat'] == sum(c['amount_sat'] for c in claims)
    assert all(value == 0 for key, value in balance.items() if key != 'spendable_sat')
    remote_msat = 0
    for channel in snapshot['channels']['channels']:
        assert channel['state'] == 'CHANNELD_NORMAL' and not channel.get('htlcs')
        point = f"{channel['funding_txid']}:{channel['funding_outnum']}"
        assert live[point]['amount_sat'] * 1000 == channel['total_msat']
        assert 0 <= channel['spendable_msat'] <= channel['to_us_msat'] <= channel['total_msat']
        remote_msat += channel['total_msat'] - channel['to_us_msat']
    paid_msat = sum(p['amount_sent_msat'] for p in snapshot['pays']['pays'] if p['status'] == 'complete')
    assert remote_msat == paid_msat and remote_msat % 1000 == 0
    delivered = sum(p['amount_msat'] for p in snapshot['pays']['pays'] if p['status'] == 'complete')
    operator = sum(a['amount_sat'] for a in live.values() if a['owner'] == 'operator') - remote_msat // 1000
    client = sum(a['amount_sat'] for a in live.values() if a['owner'] == 'client')
    operator_fees = sum(f['fee_sat'] for f in fees if f['payer'] == 'operator')
    assert operator + remote_msat // 1000 + operator_fees == 2100000
    return {'evidence_class': 'observed-regtest', 'checks_passed': True,
        'initial_fixture_sat': initial_sum, 'initial_operator_funding_and_board_sat': 2100000,
        'operator_remaining_economic_sat': operator, 'client_remaining_onchain_sat': client,
        'recipient_channel_share_sat': remote_msat // 1000, 'delivered_msat': delivered,
        'all_miner_fees_sat': sum(f['fee_sat'] for f in fees), 'operator_miner_fees_sat': operator_fees,
        'active_client_claims_sat': sum(c['amount_sat'] for c in claims),
        'claims_are_overlay_not_additional_assets': True, 'channel_funding_counted_once': True,
        'assets': live, 'active_claims': claims, 'fees': fees, 'transaction_events': steps,
        'limitation': 'Transaction/claim reconciliation only; reference-reducer acceptance and full capital-time normalization remain separate.'}


if __name__ == '__main__':
    filename = sys.argv[1] if len(sys.argv) > 1 else 'recovered-output-reused.json'
    source = ROOT / filename
    result = reconcile(json.loads(source.read_text()), json.loads((ROOT / 'initial-funding.json').read_text()))
    result['snapshot_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    (ROOT / 'economic-reconciliation.json').write_text(json.dumps(result, indent=2) + '\n', newline='\n')
    print(json.dumps({k: v for k, v in result.items() if k not in {'assets', 'active_claims', 'fees', 'transaction_events'}}, indent=2))
