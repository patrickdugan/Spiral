"""Capture existing run state and verify it offline; never starts or retries actions."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import time
import analyze
import experiment as e


def read(path):
    return json.loads(Path(path).read_text(), parse_float=Decimal)


def capture():
    manifest = e.manifest(check=False)
    initial = read(e.RUN/'initial-preflight.json')
    initial_utxos = next(row['result'] for row in initial['observations'] if row['node'] == 'core' and row['method'] == 'listunspent')
    state = e.snapshot()
    wallet_rows = e.core('listunspent', minconf=0)
    leaves = [{'txid': row['txid'], 'vout': row['vout'], 'amount_sat': analyze.sats(row['amount']),
        'kind': 'wallet', 'owner': 'core'} for row in wallet_rows]
    for node, observations in state['peers'].items():
        for row in observations['listfunds']['outputs']:
            analyze.check(row['status'] in ('confirmed','unconfirmed'), 'unexpected CLN output disposition')
            analyze.check(row['amount_msat'] % 1000 == 0, 'fractional on-chain satoshi')
            leaves.append({'txid': row['txid'], 'vout': row['output'], 'amount_sat': row['amount_msat']//1000,
                'kind': 'wallet', 'owner': node})
    transactions = []
    allocation_txid = None
    allocation = e.RUN/'action-allocate.result.json'
    if allocation.exists():
        txid = read(allocation)['result']
        allocation_txid = txid
        wallet_tx = e.core('gettransaction', txid=txid)
        decoded = e.core('decoderawtransaction', hexstring=wallet_tx['hex'])
        analyze.check(decoded['txid'] == txid, 'allocation transaction mismatch')
        transactions.append(decoded)
    decoded_ids = {tx['txid'] for tx in transactions}
    for key, proof in state['funding_outputs'].items():
        txid, vout = key.split(':'); vout = int(vout)
        if txid not in decoded_ids:
            params = {'txid': txid, 'verbosity': 1}
            if proof.get('inclusion_hash'):
                params['blockhash'] = proof['inclusion_hash']
            tx = e.core('getrawtransaction', **params)
            analyze.check(tx['txid'] == txid, 'funding transaction mismatch')
            transactions.append(tx); decoded_ids.add(txid)
        tx = next(t for t in transactions if t['txid'] == txid)
        amount = analyze.sats(tx['vout'][vout]['value'])
        analyze.check(amount == 100000, 'funding amount differs from protocol')
        leaves.append({'txid': txid, 'vout': vout, 'amount_sat': amount, 'kind': 'channel', 'owner': 'controlled_pair'})
    payments = [read(p) for p in sorted(e.RUN.glob('payment-*.json'))]
    attempts = []
    for path in sorted(e.RUN.glob('action-pay-*.intent.json')):
        index = int(path.name.removeprefix('action-pay-').removesuffix('.intent.json'))
        invoice = read(e.RUN/f'action-invoice-{index:03}.result.json')['result']
        rows = []
        for sample_path in sorted(e.RUN.glob(f'samples-{index:03}-*.jsonl')):
            data = sample_path.read_text()
            analyze.check(not data or data.endswith('\n'), 'incomplete sample write; capture again without restarting the run')
            rows.extend(json.loads(line) for line in data.splitlines())
        selected = read(e.RUN/f'route-{index:03}.json')
        analyze.check(selected['payment_hash'] == invoice['payment_hash'], 'saved route/invoice mismatch')
        attempts.append({'index': index, 'payment_hash': invoice['payment_hash'],
            'request_ns': read(path)['monotonic_ns'], 'principal_msat': selected['route'][0]['amount_out_msat'],
            'request_unix_ns': read(path)['unix_ns'],
            'saved_route': selected, 'samples': rows})
    observers = {}
    for node in 'abcd':
        data = (e.RUNTIME/('cln-'+node)/'clock-events.jsonl').read_text()
        analyze.check(data.endswith('\n'), 'incomplete observer write; capture again without restarting')
        observers[node] = data.splitlines()
    return {'captured_unix_ns': str(time.time_ns()), 'manifest': manifest, 'initial_utxos': initial_utxos,
        'capture_boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(), 'allocation_txid': allocation_txid,
        'allocation_addresses': read(e.RUN/'action-addresses.result.json')['result'] if allocation_txid else {},
        'core_wallet_utxos': [{k:v for k,v in row.items() if k in {'txid','vout','amount','spendable','safe','confirmations'}} for row in wallet_rows],
        'transactions': transactions, 'owned_leaves': leaves, 'final_snapshot': state,
        'payments': payments, 'attempts': attempts, 'observers': observers}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='new private capture directory; must not exist')
    args = parser.parse_args()
    args.output.mkdir(mode=0o700)
    bundle = capture()
    # Keep raw evidence even if arithmetic or clock validation finds a discrepancy.
    e.write_once(args.output/'private-capture.json', bundle)
    try:
        result = analyze.analyze_bundle(bundle)
    except (ValueError, KeyError, TypeError) as error:
        e.write_once(args.output/'verification-failure.json', {'status': 'invalid_capture', 'reason': str(error)})
        raise
    e.write_once(args.output/'report.json', result)
    e.write_once(args.output/'public-capture.json', analyze.public(bundle))
    print(json.dumps({'status': result['status'], 'terminal_attempts': result['terminal_attempts'],
        'miner_fees_sat': result['economic_reconciliation']['miner_fees_sat']}))


if __name__ == '__main__':
    main()
