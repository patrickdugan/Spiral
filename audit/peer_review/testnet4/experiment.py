"""Bounded, resumable testnet4 experiment; commands never repeat monetary intent.

Private run artifacts are outside Git. Export only after verification/redaction.
All money actions are explicit phases; instrumentation and observation are reads
or local observer installation. A lost RPC result is uncertain, never retried.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

import preflight
import provision

RUNTIME = provision.RUNTIME
RUN = RUNTIME / 'experiment'
EDGES = [('a', 'b'), ('a', 'c'), ('b', 'd'), ('c', 'd')]
ALLOCATIONS = {'a': 230000, 'b': 130000, 'c': 130000, 'd': 10000}
STOP_SECONDS = 48 * 3600


class RPCError(RuntimeError):
    def __init__(self, error):
        self.error = error
        super().__init__('RPC error ' + str(error.get('code')))


def rpc(node, method, params=None, timeout=20):
    """Direct local Unix RPC, avoiding a docker-exec process per sample."""
    request_id = str(time.monotonic_ns())
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout)
        connection.connect(str(RUNTIME / ('cln-' + node) / 'testnet4/lightning-rpc'))
        connection.sendall((json.dumps({'jsonrpc': '2.0', 'id': request_id,
            'method': method, 'params': params or {}}) + '\n\n').encode())
        data = b''
        while True:
            chunk = connection.recv(65536)
            if not chunk:
                raise RuntimeError('RPC disconnected before response; action outcome uncertain')
            data += chunk
            if len(data) > 32 * 1024 * 1024:
                raise RuntimeError('RPC response exceeds collection limit')
            while b'\n\n' in data:
                frame, data = data.split(b'\n\n', 1)
                response = json.loads(frame)
                if response.get('id') != request_id:
                    continue
                if 'error' in response:
                    raise RPCError(response['error'])
                return response['result']


def core(method, **params):
    config = json.loads((RUNTIME / 'preflight-config.json').read_text())
    argv = config['endpoints']['core']['cli'] + ['-named', method]
    argv += [k + '=' + (v if isinstance(v, str) else json.dumps(v, separators=(',', ':'))) for k, v in params.items()]
    result = subprocess.run(argv, text=True, capture_output=True, timeout=45, check=False)
    if result.returncode:
        raise RuntimeError('Core RPC failed; private response withheld; inspect existing action before retrying')
    raw = result.stdout.strip()
    try:
        return json.loads(raw, parse_float=Decimal)
    except ValueError:
        return raw


def write_once(path, value):
    path = Path(path)
    with path.open('x') as out:
        json.dump(value, out, indent=2, default=str); out.write('\n')
        out.flush(); os.fsync(out.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def guard(manifest, now_wall=None, now_mono=None, boot=None):
    now_wall = time.time_ns() if now_wall is None else now_wall
    now_mono = time.monotonic_ns() if now_mono is None else now_mono
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip() if boot is None else boot
    if boot != manifest['boot_id']:
        raise RuntimeError('host reboot: original monotonic clock is unavailable; stop and reconcile')
    if now_wall >= int(manifest['deadline_unix_ns']) or now_mono >= int(manifest['deadline_monotonic_ns']):
        raise RuntimeError('48-hour hard stop reached; unfinished waits must be right-censored')


def manifest(check=True):
    value = json.loads((RUN / 'manifest.json').read_text())
    if check:
        guard(value)
    return value


def action(label, method, fn):
    guard(manifest())
    path = RUN / ('action-' + label)
    # Never overwrite intent even when the earlier command failed or timed out.
    write_once(path.with_suffix('.intent.json'), {'label': label, 'method': method,
        'monotonic_ns': str(time.monotonic_ns()), 'unix_ns': str(time.time_ns())})
    try:
        result = fn()
    except Exception as error:
        write_once(path.with_suffix('.uncertain.json'), {'error_type': type(error).__name__,
            'rpc_error': error.error if isinstance(error, RPCError) else None,
            'monotonic_ns': str(time.monotonic_ns()), 'requires_reconciliation': True})
        raise
    write_once(path.with_suffix('.result.json'), {'result': result, 'monotonic_ns': str(time.monotonic_ns()),
        'unix_ns': str(time.time_ns())})
    return result


def instrument():
    source = Path(__file__).with_name('clock_observer.py')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    statuses = {}
    for node in 'abcd':
        target = RUNTIME / ('cln-' + node) / 'clock_observer.py'
        plugins = rpc(node, 'plugin', {'subcommand': 'list'})['plugins']
        active = [p for p in plugins if p['name'].endswith('/clock_observer.py') and p['active']]
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise RuntimeError('observer source differs; stop and preserve the old journal before replacing')
        if not target.exists():
            shutil.copyfile(source, target); target.chmod(0o700)
        if not active:
            rpc(node, 'plugin', {'subcommand': 'start', 'plugin': '/data/clock_observer.py'})
        statuses[node] = rpc(node, 'spiral-clock-status')
    return {'observer_sha256': digest, 'statuses': statuses, 'monetary_action': False}


def snapshot():
    started = time.monotonic_ns()
    before = core('getblockchaininfo')
    peers = {}
    for n in 'abcd':
        peers[n] = {method: rpc(n, method) for method in
            ['getinfo', 'listpeerchannels', 'listfunds', 'spiral-clock-status']}
    funding = {}
    for node, observations in peers.items():
        for channel in observations['listpeerchannels']['channels']:
            if 'funding_txid' not in channel or 'funding_outnum' not in channel:
                continue
            key = channel['funding_txid'] + ':' + str(channel['funding_outnum'])
            if key in funding:
                continue
            start = time.monotonic_ns()
            utxo = core('gettxout', txid=channel['funding_txid'], n=channel['funding_outnum'], include_mempool=True)
            proof = {'read_start_ns': str(start), 'read_end_ns': str(time.monotonic_ns()), 'utxo': utxo}
            if utxo and utxo['confirmations']:
                tip = core('getblockheader', blockhash=utxo['bestblock'])
                height = tip['height'] - utxo['confirmations'] + 1
                blockhash = core('getblockhash', height=height)
                proof.update(inclusion_height=height, inclusion_hash=blockhash,
                    header=core('getblockheader', blockhash=blockhash))
            funding[key] = proof
    after = core('getblockchaininfo')
    return {'start_monotonic_ns': str(started), 'end_monotonic_ns': str(time.monotonic_ns()),
        'unix_ns': str(time.time_ns()), 'core_before': before, 'core_after': after,
        'stable_tip': before['bestblockhash'] == after['bestblockhash'], 'peers': peers,
        'funding_outputs': funding, 'dedicated_wallet_balances': core('getbalances')}


def begin():
    if (RUN / 'manifest.json').exists():
        raise RuntimeError('experiment already begun; inspect existing run instead of starting another')
    config = json.loads((RUNTIME / 'preflight-config.json').read_text())
    reads = preflight.ReadonlyCLI(config['endpoints'])
    gate = preflight.inspect(config, reads, preflight.verify_pins(config['endpoints']))
    if gate['funding_sat'] != 510000:
        raise RuntimeError('funding differs from the frozen 510000-sat budget; reconcile before revising protocol')
    observed = instrument()
    RUN.mkdir(mode=0o700, exist_ok=True)
    now_wall, now_mono = time.time_ns(), time.monotonic_ns()
    value = {'protocol': 'controlled-diamond-20261021-v1', 'initial_funding_sat': 510000,
        'channels': 4, 'channel_sat': 100000, 'total_fee_and_idle_reserve_sat': 110000,
        'allocations_sat': ALLOCATIONS, 'transaction_feerate_sat_vb': 2, 'payment_count': 200,
        'minimum_payment_spacing_seconds': 2, 'htlc_poll_seconds': 0.025,
        'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'start_unix_ns': str(now_wall), 'start_monotonic_ns': str(now_mono),
        'deadline_unix_ns': str(now_wall + STOP_SECONDS * 10**9),
        'deadline_monotonic_ns': str(now_mono + STOP_SECONDS * 10**9),
        'preflight': gate, 'instrumentation': observed,
        'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path(__file__), Path(__file__).with_name('clock_observer.py')]}}
    write_once(RUN / 'manifest.json', value)
    write_once(RUN / 'initial-preflight.json', {'gate': gate, 'observations': reads.observations})
    write_once(RUN / 'initial.json', snapshot())
    return {'status': 'begun', 'deadline_unix_ns': value['deadline_unix_ns'], 'transaction_broadcast': False}


def allocate():
    m = manifest()
    if not (RUN / 'initial-preflight.json').exists() or not (RUN / 'initial.json').exists():
        raise RuntimeError('initial provenance checkpoint incomplete; reconcile before funding')
    # Funding must still satisfy the entire empty-wallet gate immediately before
    # the first outgoing transaction; creating receive addresses does not fund.
    config = json.loads((RUNTIME / 'preflight-config.json').read_text())
    gate = preflight.inspect(config, preflight.ReadonlyCLI(config['endpoints']), preflight.verify_pins(config['endpoints']))
    if gate['funding_sat'] != m['initial_funding_sat']:
        raise RuntimeError('initial budget changed')
    addresses = action('addresses', 'newaddr', lambda: {n: rpc(n, 'newaddr', {'addresstype': 'bech32'})['bech32'] for n in 'abcd'})
    amounts = {addresses[n]: format(Decimal(sat)/100_000_000, '.8f') for n, sat in ALLOCATIONS.items()}
    txid = action('allocate', 'sendmany', lambda: core('sendmany', dummy='', amounts=amounts,
        comment='spiral bounded testnet4 clocks', replaceable=True, fee_rate=2))
    observe_mempool('allocate', txid)
    return {'txid': txid, 'allocated_sat': sum(ALLOCATIONS.values())}


def channels():
    m = manifest()
    allocation = json.loads((RUN/'action-allocate.result.json').read_text())['result']
    tx = core('gettransaction', txid=allocation)
    if tx['confirmations'] < 1:
        raise RuntimeError('allocation still unconfirmed; wait without repeating it')
    bridge = json.loads((RUNTIME/'bridge.json').read_text())
    if bridge['allow_broadcast'] is not True:
        raise RuntimeError('enable the private bridge broadcast capability after reviewing the eligible funding manifest')
    ids = m['preflight']['node_ids']
    results = {}
    for left, right in EDGES:
        label = 'channel-' + left + right
        if (RUN/('action-'+label+'.intent.json')).exists():
            result_path = RUN/('action-'+label+'.result.json')
            if not result_path.exists():
                raise RuntimeError('uncertain channel intent; reconcile existing opening before continuing')
            previous = json.loads(result_path.read_text())['result']
            known = rpc(left, 'listpeerchannels')['channels']
            if not any(c.get('funding_txid') == previous['txid'] and c['peer_id'] == ids[right] for c in known):
                raise RuntimeError('recorded opening is missing from the live peer')
            results[label] = previous
            continue
        results[label] = action(label, 'fundchannel', lambda: rpc(left, 'fundchannel', {
            'id': ids[right], 'amount': '100000sat', 'feerate': '2000perkb', 'announce': False,
            'minconf': 1, 'push_msat': 50000000, 'mindepth': 3}, timeout=60))
        observe_mempool(label, results[label]['txid'])
    return results


def observe_mempool(label, txid):
    started = time.monotonic_ns()
    try:
        result = {'entry': core('getmempoolentry', txid=txid)}
    except RuntimeError:
        result = {'unavailable': True, 'meaning': 'absence or RPC failure; not proof of confirmation'}
    write_once(RUN/f'mempool-{label}-{started}.json', {'txid': txid,
        'read_start_ns': str(started), 'read_end_ns': str(time.monotonic_ns()), **result})


def schedule(index):
    if type(index) is not int or not 0 <= index < 200:
        raise ValueError('payment index outside frozen workload')
    source, destination = ('a', 'd') if index % 2 == 0 else ('d', 'a')
    return {'source': source, 'destination': destination, 'middle': 'bc'[(index//4) % 2],
            'amount_msat': (1000 if (index//2) % 2 == 0 else 2000) * 1000}


def channel_map(state):
    if not state.get('stable_tip', False):
        raise RuntimeError('chain tip changed across snapshot')
    result = {}
    ids = {n: state['peers'][n]['getinfo']['id'] for n in 'abcd'}
    names = {value: key for key, value in ids.items()}
    for node in 'abcd':
        for row in state['peers'][node]['listpeerchannels']['channels']:
            peer = names.get(row['peer_id'])
            if peer is None or frozenset((node, peer)) not in {frozenset(e) for e in EDGES}:
                raise RuntimeError('uncontrolled channel')
            if row['state'] != 'CHANNELD_NORMAL' or row.get('htlcs'):
                raise RuntimeError('channel not active and quiescent')
            if (node, peer) in result or row['total_msat'] != 100000000:
                raise RuntimeError('channel count/value differs from protocol')
            result[node, peer] = row
    if len(result) != 8:
        raise RuntimeError('four channels at both endpoints required')
    for left, right in EDGES:
        a, b = result[left, right], result[right, left]
        if a['funding_txid'] != b['funding_txid'] or a['funding_outnum'] != b['funding_outnum']:
            raise RuntimeError('endpoint funding provenance mismatch')
        if a['to_us_msat'] + b['to_us_msat'] != a['total_msat']:
            raise RuntimeError('endpoint balances do not conserve funding')
        proof = state['funding_outputs'][a['funding_txid'] + ':' + str(a['funding_outnum'])]
        if not proof['utxo'] or proof['utxo']['confirmations'] < 3 or preflight.btc_sat(proof['utxo']['value']) != 100000:
            raise RuntimeError('channel funding lacks the configured confirmation depth or value')
    return result


def make_route(job, channels, ids, final_cltv, middle_delta):
    src, mid, dst, amount = job['source'], job['middle'], job['destination'], job['amount_msat']
    outgoing = channels[mid, dst]
    fee = outgoing['fee_base_msat'] + amount * outgoing['fee_proportional_millionths'] // 1_000_000
    route = []
    for a, b, value, delay in [(src, mid, amount + fee, final_cltv + middle_delta), (mid, dst, amount, final_cltv)]:
        channel = channels[a, b]
        if channel['spendable_msat'] < value:
            raise RuntimeError('controlled route lacks outbound capacity')
        direction = 0 if ids[a] < ids[b] else 1
        route.append({'short_channel_id_dir': channel['short_channel_id'] + '/' + str(direction),
            'node_id_out': ids[b], 'amount_out_msat': value, 'cltv_out': delay})
    return route, fee


def reconcile(before, after, job, fee, complete):
    previous, current = channel_map(before), channel_map(after)
    deltas = {edge: 0 for edge in previous}
    if complete:
        src, mid, dst = job['source'], job['middle'], job['destination']
        amount = job['amount_msat']
        deltas[src, mid] -= amount + fee; deltas[mid, src] += amount + fee
        deltas[mid, dst] -= amount; deltas[dst, mid] += amount
    for edge in previous:
        if current[edge]['funding_txid'] != previous[edge]['funding_txid']:
            raise RuntimeError('funding changed during payment')
        if current[edge]['to_us_msat'] - previous[edge]['to_us_msat'] != deltas[edge]:
            raise RuntimeError('payment/fee balance discrepancy at ' + str(edge))
    return {'reconciled': True, 'delivered_msat': job['amount_msat'] if complete else 0,
        'routing_fee_msat': fee if complete else 0}


def sample(node, payment_hash):
    start = time.monotonic_ns()
    channels = rpc(node, 'listpeerchannels')['channels']
    return {'start_ns': str(start), 'end_ns': str(time.monotonic_ns()), 'channels': [
        {k: v for k, v in c.items() if k in {'channel_id', 'short_channel_id', 'to_us_msat', 'spendable_msat', 'receivable_msat'}} |
        {'htlcs': [h for h in c.get('htlcs', []) if h['payment_hash'] == payment_hash]} for c in channels]}


def payments(count):
    m = manifest()
    ids = m['preflight']['node_ids']
    completed = sorted(RUN.glob('payment-*.json'))
    first = len(completed)
    if [p.name for p in completed] != [f'payment-{i:03}.json' for i in range(first)]:
        raise RuntimeError('payment journal has a gap; reconcile before continuing')
    if (RUN/'halted.json').exists():
        raise RuntimeError('run halted; reconcile the recorded discrepancy')
    for index in range(first, min(first + count, 200)):
        m = manifest()
        job = schedule(index)
        attempt = RUN / f'attempt-{index:03}.json'
        if attempt.exists():
            before = json.loads(attempt.read_text(), parse_float=Decimal)['before']
        else:
            before = snapshot()
            channel_map(before)
            write_once(attempt, {'before': before, 'job': job})
        channels_before = channel_map(before)
        label = f'spiral-t4-clock-{index:03}'
        invoice_file = RUN/f'action-invoice-{index:03}.result.json'
        if invoice_file.exists():
            invoice = json.loads(invoice_file.read_text())['result']
        else:
            invoice = action(f'invoice-{index:03}', 'invoice', lambda: rpc(job['destination'], 'invoice',
                {'amount_msat': job['amount_msat'], 'label': label, 'description': 'controlled testnet4 clock', 'expiry': 3600}))
        decoded = rpc(job['source'], 'decodepay', {'bolt11': invoice['bolt11']})
        route_file = RUN / f'route-{index:03}.json'
        if route_file.exists():
            selected = json.loads(route_file.read_text())
            if selected['payment_hash'] != invoice['payment_hash']:
                raise RuntimeError('saved route belongs to another invoice')
        else:
            delta = rpc(job['middle'], 'listconfigs', {'config': 'cltv-delta'})['configs']['cltv-delta']['value_int']
            route, fee = make_route(job, channels_before, ids, decoded['min_final_cltv_expiry'], delta)
            selected = {'payment_hash': invoice['payment_hash'], 'route': route, 'fee_msat': fee,
                'cltv_policy': {'invoice_min_final': decoded['min_final_cltv_expiry'], 'middle_delta': delta}}
            write_once(route_file, selected)
        route, fee = selected['route'], selected['fee_msat']
        start = time.monotonic_ns()
        sample_file = RUN / f'samples-{index:03}-{start}.jsonl'
        with sample_file.open('x'):
            pass
        samples = []
        def collect():
            row = sample(job['source'], invoice['payment_hash'])
            with sample_file.open('a') as stream:
                stream.write(json.dumps(row) + '\n'); stream.flush(); os.fsync(stream.fileno())
            samples.append(row)
        collect()
        # Submission is recorded once. waitsendpay only observes this exact hash.
        pay_intent = RUN/f'action-pay-{index:03}.intent.json'
        if pay_intent.exists():
            known = rpc(job['source'], 'listsendpays', {'payment_hash': invoice['payment_hash']})['payments']
            if len(known) != 1:
                raise RuntimeError('uncertain submission has no unique authoritative payment; do not resend')
            sent = {'resumed_observation_only': True, 'original_intent': json.loads(pay_intent.read_text())}
        else:
            sent = action(f'pay-{index:03}', 'sendpay', lambda: rpc(job['source'], 'sendpay',
                {'route': route, 'payment_hash': invoice['payment_hash'], 'amount_msat': job['amount_msat'],
                 'bolt11': invoice['bolt11'], 'payment_secret': decoded['payment_secret'], 'label': label}))
        with ThreadPoolExecutor(max_workers=1) as pool:
            waiter = pool.submit(rpc, job['source'], 'waitsendpay', {'payment_hash': invoice['payment_hash'], 'timeout': 60}, 65)
            while not waiter.done():
                guard(m)
                collect()
                time.sleep(0.025)
            try:
                outcome = waiter.result(); complete = outcome['status'] == 'complete'
            except RPCError as error:
                outcome = {'error': error.error}; complete = False
        wait_response_observed_ns = time.monotonic_ns()
        collect()
        # A wait timeout is still pending, never a terminal failed payment.
        recorded = rpc(job['source'], 'listsendpays', {'payment_hash': invoice['payment_hash']})['payments']
        if len(recorded) != 1 or recorded[0]['status'] not in ('complete', 'failed'):
            raise RuntimeError('payment outcome unresolved; retain intent and do not resend')
        complete = recorded[0]['status'] == 'complete'
        terminal_status_read_end_ns = time.monotonic_ns()
        if complete:
            proof = recorded[0]['payment_preimage']
            if hashlib.sha256(bytes.fromhex(proof)).hexdigest() != invoice['payment_hash']:
                raise RuntimeError('settlement preimage mismatch')
            if recorded[0]['amount_sent_msat'] != job['amount_msat'] + fee:
                raise RuntimeError('settled fee differs from explicit route')
        # Revocation can lag the terminal payment callback. Wait for quiescent
        # channels, preserving these extra samples as reservation evidence.
        for _ in range(100):
            guard(m)
            after = snapshot()
            try:
                checked = reconcile(before, after, job, fee, complete); break
            except RuntimeError:
                collect(); time.sleep(0.05)
        else:
            write_once(RUN/'halted.json', {'index': index, 'reason': 'balance/quiescence discrepancy', 'after': after})
            raise RuntimeError('payment accounting did not reconcile; halted')
        write_once(RUN/f'payment-{index:03}.json', {'index': index, 'job': job, 'route': route,
            'cltv_policy': selected['cltv_policy'],
            'payment_hash': invoice['payment_hash'], 'collection_start_ns': str(start),
            'wait_response_observed_ns': str(wait_response_observed_ns),
            'terminal_status_read_end_ns': str(terminal_status_read_end_ns),
            'quiescent_reconciliation_ns': str(time.monotonic_ns()), 'submission': sent, 'outcome': outcome,
            'authoritative_payment': recorded[0], 'samples': samples, 'before': before, 'after': after,
            'accounting': checked})
        time.sleep(2)
    return {'completed_invoice_attempts': min(first + count, 200), 'target': 200}


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['instrument', 'begin', 'allocate', 'channels', 'observe', 'payments'])
    parser.add_argument('--count', type=int, default=1)
    args = parser.parse_args()
    if not 1 <= args.count <= 200:
        parser.error('count must be between 1 and 200')
    if args.phase == 'observe':
        manifest(check=False)  # Final censoring observations remain possible after the stop.
        result = snapshot(); write_once(RUN/('observation-'+str(time.time_ns())+'.json'), result)
        print(json.dumps({'status': 'observed', 'stable_tip': result['stable_tip']})); return
    function = {'instrument': instrument, 'begin': begin, 'allocate': allocate, 'channels': channels,
        'payments': lambda: payments(args.count)}[args.phase]
    result = function()
    # Phase outputs contain only public receipt metadata; raw RPC artifacts stay private.
    print(json.dumps(result, default=str))


if __name__ == '__main__':
    main()
