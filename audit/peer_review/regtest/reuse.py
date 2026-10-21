"""Confirm the original recovery and prove the independent round spends it."""
from bootstrap import core
from launch import bark
from fund import mine
from observe import snapshot, watchman_claims
from pay import action
from attest import DEST, save
from decimal import Decimal
import json

board = json.loads((DEST / 'action-board-100k.json').read_text())['result']['funding_tx']['txid']
matching = []
for record in watchman_claims():
    if record['slog_id'] != 'ClaimBroadcast':
        continue
    tx = core('getrawtransaction', record['slog_data']['txid'], 'true')
    if any(v.get('txid') == board and v.get('vout') == 0 for v in tx['vin']):
        matching.append(tx)
if len(matching) != 1:
    raise RuntimeError('Expected one observed original-board sweep')
sweep = matching[0]
if len(sweep['vin']) != 1 or len(sweep['vout']) != 1:
    raise RuntimeError('Unexpected mixed sweep; do not claim isolated reuse')
recovered = int(Decimal(sweep['vout'][0]['value']) * 100000000)
mine(3)
before = snapshot('original-sweep-confirmed')
wallet = before['server_wallet']['rounds']
recovered_point = f"{sweep['txid']}:0"
if wallet['confirmed_utxos'] != [recovered_point] or wallet['total_balance'] != recovered:
    raise RuntimeError('Server wallet is not exclusively the recovered output')
action('independent-round-reuse', lambda: {'stdout': bark('refresh', '--all').stdout})
mine(3)
bark('balance')
after = snapshot('recovered-output-reused')
prior_rounds = {r['funding_txid'] for r in before['database']['rounds']}
new = [r for r in after['database']['rounds'] if r['funding_txid'] not in prior_rounds]
if len(new) != 1:
    raise RuntimeError('Expected exactly one new independent round')
tx = after['transactions'][new[0]['funding_txid']]['transaction']
inputs = [f"{v['txid']}:{v['vout']}" for v in tx['vin']]
if inputs != [recovered_point] or tx.get('confirmations', 0) < 2:
    raise RuntimeError('New confirmed round does not exclusively spend the recovered output')
save('reuse-proof.json', {'evidence_class': 'observed-regtest', 'original_board_outpoint': f'{board}:0',
    'sweep_txid': sweep['txid'], 'sweep_input_sat': 100000, 'recovered_output_sat': recovered,
    'sweep_fee_sat': 100000 - recovered, 'recovered_outpoint': recovered_point,
    'server_wallet_before_reuse': wallet, 'reuse_round_txid': tx['txid'], 'reuse_inputs': inputs,
    'reuse_confirmations': tx['confirmations'], 'reuse_observed_height': after['chain_after']['blocks'],
    'fresh_external_funding_between_recovery_and_reuse': 0,
    'note': 'Proves transaction-level reuse. Complete state-machine normalization and matched-service analysis are separate checks.'})
print('Confirmed: the independent new round exclusively spends the original recovered output.', flush=True)
