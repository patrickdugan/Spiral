"""Independent offline arithmetic and clock bounds for captured testnet4 data.

No runner imports, network access, signing, or inferred completion from filenames.
Input observations remain a trusted-node evidence boundary, not consensus proofs.
"""
from decimal import Decimal
import hashlib
import json


def check(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value):
    check(type(value) is int and value >= 0, 'nonnegative integer required')
    return value


def sats(value):
    check(isinstance(value, (str, int, Decimal)) and not isinstance(value, bool), 'exact BTC token required')
    amount = Decimal(value) * 100000000
    check(amount.is_finite() and amount >= 0 and amount == amount.to_integral_value(), 'invalid satoshi amount')
    return int(amount)


def outpoint(row):
    return row['txid'] + ':' + str(integer(row['vout']))


def funding_graph(initial, transactions, owned_leaves):
    """Rebuild every spend from initial outpoints, rejecting fresh financing."""
    live, created = {}, set()
    for row in initial:
        key = outpoint(row)
        check(key not in live, 'duplicate initial outpoint')
        live[key] = sats(row['amount']); created.add(key)
    initial_sat = sum(live.values())
    check(initial_sat == 510000, 'initial budget differs from frozen 510000 sats')
    ids = [t['txid'] for t in transactions]
    check(len(ids) <= 5, 'more than allocation plus four funding transactions')
    check(len(set(ids)) == len(ids), 'duplicate transaction')
    pending = list(transactions)
    fees = []
    while pending:
        progress = False
        for tx in pending[:]:
            check(tx['vin'], 'transaction has no funding inputs')
            check(all('txid' in v and 'vout' in v for v in tx['vin']), 'coinbase/external issuance inside experiment')
            inputs = [outpoint(v) for v in tx['vin']]
            check(len(set(inputs)) == len(inputs), 'duplicate transaction input')
            if not all(i in live for i in inputs):
                continue
            outputs = {}
            for index, row in enumerate(tx['vout']):
                check(row['n'] == index, 'noncanonical output indexing')
                key = tx['txid'] + ':' + str(index)
                check(key not in created, 'output reused')
                amount = sats(row['value'])
                if amount == 0 and row.get('scriptPubKey', {}).get('type') == 'nulldata':
                    continue
                outputs[key] = amount
            fee = sum(live[k] for k in inputs) - sum(outputs.values())
            check(fee >= 0, 'transaction creates value')
            for key in inputs:
                del live[key]
            live.update(outputs); created.update(outputs)
            fees.append({'txid': tx['txid'], 'fee_sat': fee})
            pending.remove(tx); progress = True
        check(progress, 'unknown financing, duplicate spend or disconnected ancestry')
    claimed = {}
    for row in owned_leaves:
        key = outpoint(row)
        check(key not in claimed, 'economic output counted more than once')
        claimed[key] = integer(row['amount_sat'])
    check(claimed == live, 'owned wallet/channel leaves do not match transaction graph')
    total_fees = sum(f['fee_sat'] for f in fees)
    check(total_fees <= 110000, 'fees exceed the declared fee/idle reserve')
    check(sum(claimed.values()) + total_fees == initial_sat, 'economic conservation failure')
    return {'initial_sat': initial_sat, 'remaining_assets_sat': sum(claimed.values()),
        'miner_fees_sat': total_fees, 'transactions': fees, 'unique_remaining_outputs': len(claimed)}


def verify_observer(lines):
    previous, last_clock = '0'*64, -1
    rows = []
    for index, line in enumerate(lines):
        row = json.loads(line)
        digest = row.pop('sha256')
        actual = hashlib.sha256(json.dumps(row, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        check(row['sequence'] == index + 1 and row['previous_sha256'] == previous and digest == actual,
              'observer hash/sequence mismatch')
        clock = int(row['observer_monotonic_ns'])
        check(clock >= last_clock, 'observer monotonic clock regressed')
        row['sha256'] = digest; rows.append(row)
        previous, last_clock = digest, clock
    return rows


def reservation_bounds(samples, payment_hash, request_ns, principal_msat, resolved=False):
    """Bounds for one non-retried sender HTLC, respecting each RPC read interval."""
    request_ns, principal_msat = int(request_ns), integer(principal_msat)
    observations = []
    for sample in samples:
        start, end = int(sample['start_ns']), int(sample['end_ns'])
        check(0 <= start <= end, 'invalid sample interval')
        htlcs = [h for c in sample['channels'] for h in c.get('htlcs', [])
                 if h.get('payment_hash') == payment_hash and h.get('direction', 'out') == 'out']
        check(len(htlcs) <= 1, 'multiple sender HTLCs violate single-route experiment')
        if htlcs:
            check(htlcs[0]['amount_msat'] == principal_msat, 'sampled principal differs from explicit route')
        observations.append((start, end, bool(htlcs)))
    observations.sort()
    check(observations, 'no reservation samples')
    check(all(a[1] <= b[0] for a, b in zip(observations, observations[1:])), 'overlapping sample reads need separate treatment')
    # Discard absence reads entirely before submission; keep the last as a bound.
    active = [i for i, row in enumerate(observations) if row[2]]
    gap = max([max(0, b[0]-a[1]) for a,b in zip(observations, observations[1:])] or [0])
    if not active:
        post = [row for row in observations if row[0] >= request_ns]
        upper = post[-1][1] - request_ns if post and resolved else None
        lower, classification = 0, 'not_captured_active'
    else:
        first, last = active[0], active[-1]
        check(all(row[2] for row in observations[first:last+1]), 'HTLC reappeared after observed absence')
        prior = observations[first-1] if first else None
        following = observations[last+1] if last+1 < len(observations) else None
        onset_lower = max(request_ns, prior[0] if prior else request_ns)
        onset_upper = observations[first][1]
        check(onset_upper >= onset_lower, 'HTLC precedes submission')
        lower = max(0, observations[last][0] - onset_upper)
        upper = following[1] - onset_lower if following else None
        classification = 'interval_censored' if following else 'right_censored'
    check(upper is None or upper >= lower, 'inconsistent duration bounds')
    return {'classification': classification, 'active_samples': len(active), 'total_samples': len(observations),
        'duration_lower_ns': str(lower), 'duration_upper_ns': str(upper) if upper is not None else None,
        'largest_unsampled_gap_ns': str(gap), 'principal_msat': principal_msat,
        'capital_time_lower_msat_ns': str(lower * principal_msat),
        'capital_time_upper_msat_ns': str(upper * principal_msat) if upper is not None else None,
        'sat_seconds_denominator': '1000000000000',
        'assumption': 'one sender HTLC without retry; sample intervals bound the unknown read instant'}


def balances(snapshot):
    check(snapshot['stable_tip'], 'unstable snapshot')
    peers = snapshot['peers']
    names = {v['getinfo']['id']: k for k,v in peers.items()}
    result = {}
    for node, data in peers.items():
        for c in data['listpeerchannels']['channels']:
            check(c['state'] == 'CHANNELD_NORMAL' and not c.get('htlcs'), 'nonquiescent channel checkpoint')
            other = names[c['peer_id']]
            key = (node, other)
            check(key not in result, 'duplicate directed channel')
            proof = snapshot['funding_outputs'][c['funding_txid'] + ':' + str(c['funding_outnum'])]['utxo']
            check(proof and proof['confirmations'] >= 3 and sats(proof['value']) == 100000,
                  'funding depth/value unproven')
            result[key] = {'balance': integer(c['to_us_msat']), 'total': integer(c['total_msat']),
                'outpoint': c['funding_txid'] + ':' + str(c['funding_outnum']),
                'scid': c['short_channel_id'],
                'base': integer(c['fee_base_msat']), 'ppm': integer(c['fee_proportional_millionths'])}
    expected = {(a,b) for a,b in [('a','b'),('a','c'),('b','d'),('c','d')]} | {(b,a) for a,b in [('a','b'),('a','c'),('b','d'),('c','d')]}
    check(set(result) == expected, 'wrong channel graph')
    for (a,b), row in result.items():
        opposite = result[b,a]
        check(row['outpoint'] == opposite['outpoint'], 'funding identity disagreement')
        check(row['total'] == opposite['total'] == 100000000 and row['balance']+opposite['balance'] == row['total'],
              'endpoint balances do not conserve funding')
    return result


def verify_payment(row):
    index = integer(row['index']); check(index < 200, 'extra payment')
    # Restate the frozen workload independently of the runner's schedule helper.
    src, dst = ('a','d') if index % 2 == 0 else ('d','a')
    mid = 'b' if index % 8 < 4 else 'c'
    amount = 1000000 if index % 4 < 2 else 2000000
    check(row['job'] == {'source': src, 'destination': dst, 'middle': mid, 'amount_msat': amount}, 'workload changed')
    before, after = balances(row['before']), balances(row['after'])
    payment = row['authoritative_payment']
    check(payment['payment_hash'] == row['payment_hash'], 'payment hash mismatch')
    check(payment['status'] in ('complete','failed'), 'pending payment is not terminal')
    fee = before[mid,dst]['base'] + amount * before[mid,dst]['ppm'] // 1000000
    route = row['route']; check(len(route) == 2, 'route length changed')
    ids = {n: row['before']['peers'][n]['getinfo']['id'] for n in 'abcd'}
    check([r['node_id_out'] for r in route] == [ids[mid], ids[dst]], 'route leaves controlled path')
    check([r['amount_out_msat'] for r in route] == [amount+fee, amount], 'route amounts disagree with policy')
    expected_scids = [before[x,y]['scid'] + ('/0' if ids[x] < ids[y] else '/1') for x,y in [(src,mid),(mid,dst)]]
    check([r['short_channel_id_dir'] for r in route] == expected_scids, 'route channel/direction mismatch')
    policy = row['cltv_policy']; final, delta = integer(policy['invoice_min_final']), integer(policy['middle_delta'])
    check([r['cltv_out'] for r in route] == [final+delta,final], 'route CLTV mismatch')
    success = payment['status'] == 'complete'
    if success:
        check(payment['amount_msat'] == amount and payment['amount_sent_msat'] == amount+fee, 'settled principal/fee mismatch')
        check(hashlib.sha256(bytes.fromhex(payment['payment_preimage'])).hexdigest() == row['payment_hash'], 'invalid preimage')
    transfers = {(src,mid): -(amount+fee), (mid,src): amount+fee, (mid,dst): -amount, (dst,mid): amount}
    for edge, prior in before.items():
        check(prior['outpoint'] == after[edge]['outpoint'], 'channel funding changed during payment')
        expected = transfers.get(edge, 0) if success else 0
        check(after[edge]['balance']-prior['balance'] == expected, 'payment does not reconcile at ' + str(edge))
    return {'index': index, 'offered_msat': amount, 'delivered_msat': amount if success else 0,
        'routing_fee_msat': fee if success else 0, 'status': payment['status'], 'preimage_verified': success}


def public(value):
    """Export only after private proof checks; remove known private RPC fields."""
    private = {'payment_preimage','preimage','payment_secret','bolt11','bolt12','desc','parent_descs',
               'password','rpcpassword','mnemonic','hsm_secret','erroronion','onionreply','message','description'}
    if isinstance(value, dict):
        return {k: public(v) for k,v in value.items() if k not in private}
    if isinstance(value, list):
        return [public(v) for v in value]
    return str(value) if isinstance(value, Decimal) else value


def verify_ownership(bundle):
    snapshot = bundle['final_snapshot']
    check(snapshot['stable_tip'], 'final snapshot crossed a tip change')
    check(snapshot['core_before']['chain'] == snapshot['core_after']['chain'] == 'testnet4', 'wrong final network')
    peers = snapshot['peers']; check(set(peers) == set('abcd'), 'missing controlled peer')
    ids = {v['getinfo']['id']: n for n,v in peers.items()}
    check(len(ids) == 4, 'duplicate peer identity')
    rows, references = [], {}
    for u in bundle['core_wallet_utxos']:
        check(u['spendable'] is True, 'Core leaf is not wallet spendable')
        rows.append((u['txid'], u['vout'], sats(u['amount']), 'wallet', 'core'))
    for node, data in peers.items():
        check(data['getinfo']['network'] == 'testnet4', 'peer on wrong network')
        for u in data['listfunds']['outputs']:
            amount = integer(u['amount_msat'])
            check(amount % 1000 == 0 and u['status'] in ('confirmed','unconfirmed'), 'invalid CLN wallet leaf')
            rows.append((u['txid'], u['output'], amount//1000, 'wallet', node))
        for c in data['listpeerchannels']['channels']:
            if 'funding_txid' not in c or 'funding_outnum' not in c:
                continue
            check(c['peer_id'] in ids, 'uncontrolled channel counterparty')
            pair = frozenset((node, ids[c['peer_id']]))
            check(pair in {frozenset(e) for e in [('a','b'),('a','c'),('b','d'),('c','d')]}, 'channel outside diamond')
            key = c['funding_txid'] + ':' + str(c['funding_outnum'])
            refs = references.setdefault(key, [])
            refs.append((node, pair))
    check(set(references) == set(snapshot['funding_outputs']), 'funding proof/peer reference mismatch')
    for key, refs in references.items():
        check(len(refs) == 2 and refs[0][1] == refs[1][1] and {r[0] for r in refs} == set(refs[0][1]),
            'both controlled endpoints must identify the same funding output')
        proof = snapshot['funding_outputs'][key]['utxo']
        check(proof and sats(proof['value']) == 100000, 'funding output not observed unspent at expected value')
        txid, vout = key.split(':')
        rows.append((txid, int(vout), 100000, 'channel', 'controlled_pair'))
    supplied = [(r['txid'],r['vout'],r['amount_sat'],r['kind'],r['owner']) for r in bundle['owned_leaves']]
    check(sorted(rows) == sorted(supplied), 'leaf ownership labels do not match wallet and peer evidence')


def analyze_bundle(bundle):
    check(bundle['manifest']['preflight']['status'] == 'eligible_for_funding_cycle', 'run lacks eligible preflight')
    check(bundle['manifest']['preflight']['genesis'] == '00000000da84f2bafbbc53dee25a72ae507ff4914b867c565be350b0da8bf043', 'wrong genesis')
    check(bundle['capture_boot_id'] == bundle['manifest']['boot_id'], 'clock epoch changed; durations require separate treatment')
    verify_ownership(bundle)
    allocation_id = bundle['allocation_txid']
    if allocation_id is None:
        check(not bundle['transactions'], 'transactions without recorded allocation')
    else:
        allocation = next((tx for tx in bundle['transactions'] if tx['txid'] == allocation_id), None)
        check(allocation is not None, 'recorded allocation is missing')
        addresses = bundle['allocation_addresses']
        check(set(addresses) == set('abcd') and len(set(addresses.values())) == 4, 'allocation address ambiguity')
        for node, amount in {'a':230000,'b':130000,'c':130000,'d':10000}.items():
            paid = sum(sats(v['value']) for v in allocation['vout'] if v.get('scriptPubKey',{}).get('address') == addresses[node])
            check(paid == amount, 'allocation differs from frozen distribution')
    ledger = funding_graph(bundle['initial_utxos'], bundle['transactions'], bundle['owned_leaves'])
    observer_rows = {node: verify_observer(lines) for node, lines in bundle['observers'].items()}
    check(set(observer_rows) == set('abcd') and all(observer_rows.values()), 'missing observer journal')
    outcomes, clocks, previous_after = [], [], None
    payments = bundle['payments']
    check([p['index'] for p in payments] == list(range(len(payments))), 'gap or duplicate in terminal payment journal')
    for row in payments:
        before = balances(row['before'])
        if previous_after is not None:
            check({k:(v['balance'],v['outpoint']) for k,v in before.items()} == previous_after,
                'unaccounted balance change between payments')
        outcomes.append(verify_payment(row))
        after = balances(row['after'])
        previous_after = {k:(v['balance'],v['outpoint']) for k,v in after.items()}
    for attempt in bundle['attempts']:
        index = integer(attempt['index'])
        check(int(bundle['manifest']['start_monotonic_ns']) <= int(attempt['request_ns']) < int(bundle['manifest']['deadline_monotonic_ns']),
            'submission outside the bounded run')
        check(0 < int(attempt['request_unix_ns']) < int(bundle['manifest']['deadline_unix_ns']), 'submission past wall-clock hard stop')
        terminal = payments[index] if index < len(payments) else None
        if terminal:
            check(attempt['saved_route']['route'] == terminal['route'] and attempt['payment_hash'] == terminal['payment_hash'],
                'terminal result differs from immutable submitted route')
            check(attempt['principal_msat'] == terminal['route'][0]['amount_out_msat'], 'reservation principal mismatch')
        samples = list(attempt['samples'])
        if terminal:
            final = terminal['after']; source = terminal['job']['source']
            samples.append({'start_ns': final['start_monotonic_ns'], 'end_ns': final['end_monotonic_ns'],
                'channels': final['peers'][source]['listpeerchannels']['channels']})
        if samples:
            clock = reservation_bounds(samples, attempt['payment_hash'], attempt['request_ns'],
                attempt['principal_msat'], resolved=terminal is not None)
        else:
            clock = {'classification': 'missing_samples', 'duration_lower_ns': '0', 'duration_upper_ns': None,
                'capital_time_lower_msat_ns': '0', 'capital_time_upper_msat_ns': None}
        clocks.append({'index': index, **clock})
    indices = [a['index'] for a in bundle['attempts']]
    check(indices == list(range(len(indices))) and len(indices) <= 200, 'attempt journal gap/duplicate/overflow')
    check(len(payments) <= len(indices), 'terminal payment without a submission intent')
    offered = sum(1000000 if i % 4 < 2 else 2000000 for i in indices)
    delivered = sum(o['delivered_msat'] for o in outcomes)
    lower = sum(int(c['capital_time_lower_msat_ns']) for c in clocks)
    upper = None if any(c['capital_time_upper_msat_ns'] is None for c in clocks) else sum(int(c['capital_time_upper_msat_ns']) for c in clocks)
    final_channels = [x for x in bundle['owned_leaves'] if x['kind'] == 'channel']
    all_terminal = len(payments) == 200
    if all_terminal:
        check(len(bundle['transactions']) == 5 and bundle['allocation_txid'] is not None and len({c['txid'] for c in final_channels}) == 4,
            'funding cycle is not one allocation and four separate openings')
        final = balances(bundle['final_snapshot'])
        check({k:(v['balance'],v['outpoint']) for k,v in final.items()} == previous_after, 'final balances changed after last payment')
    return {'evidence_class': 'independent_testnet4_capture_check',
        'status': 'terminal_workload_reconciled' if all_terminal and len(final_channels) == 4 else 'partial_run',
        'economic_reconciliation': ledger, 'terminal_outcomes': outcomes, 'reservation_bounds': clocks,
        'planned_offered_msat': 300000000, 'submission_attempts': len(indices), 'terminal_attempts': len(payments),
        'unresolved_submission_attempts': len(indices)-len(payments), 'unattempted_invoices': 200-len(indices),
        'offered_msat': offered, 'delivered_msat': delivered,
        'value_delivery_rate': str(Decimal(delivered)/offered) if offered else None,
        'routing_fees_internal_msat': sum(o['routing_fee_msat'] for o in outcomes),
        'reservation_capital_time_msat_ns': {'lower': str(lower), 'upper': str(upper) if upper is not None else None},
        'capital_time_per_offered_value_ns': {'lower': str(Decimal(lower)/offered),
            'upper': str(Decimal(upper)/offered) if upper is not None else None} if offered else None,
        'capital_time_per_delivered_value_ns': {'lower': str(Decimal(lower)/delivered),
            'upper': str(Decimal(upper)/delivered) if upper is not None else None} if delivered else None,
        'observer_journal_lengths': {n: len(rows) for n,rows in observer_rows.items()},
        'limits': ['Captured RPC responses trust the pinned local node; they are not independent consensus proofs.',
            'Reservation bounds assume one non-retried sender HTLC per submission.',
            'Missing active samples never establish zero duration; unresolved upper bounds remain null.',
            'Notification receipt clocks and miner timestamps are separate from internal commitment times.',
            'This arithmetic check does not by itself verify notification coverage or the activation-threshold clock; inspect those event traces separately.',
            'Partial-run ratios use submitted value; unattempted planned invoices are reported separately.']}
