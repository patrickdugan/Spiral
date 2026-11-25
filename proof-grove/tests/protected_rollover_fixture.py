"""Exercise a mined two-recipient rollover of a real V3 issuance reserve."""

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys

from proofdesk import protected_accounting as accounting, protected_reserve as reserve
from proofdesk.domain import Refused, digest
from protected_fixture_keys import descriptor, fixture_wif


def run(core, rpc, root, runtime, mining, parent, holder_wallet, at_split=None):
    config = runtime / 'protected-core.json'
    parent_path = runtime / 'protected-bundle.json'
    parent_args = ('--bundle', parent_path, '--bundle-id', parent['bundle_id'])

    def cli(action, *args, refusal=None):
        result = subprocess.run([sys.executable, '-m', 'proofdesk', 'protected-' + action,
                                 '--config', str(config), *map(str, args)], cwd=root, text=True,
                                capture_output=True, timeout=30, check=False)
        receipt = json.loads(result.stdout)
        if refusal is None:
            assert result.returncode == 0, (receipt, result.stderr)
        else:
            assert result.returncode == 1 and receipt.get('error') == refusal, (receipt, result.stderr)
        return receipt

    def write(name, data):
        path = runtime / name
        path.write_text(json.dumps(data), encoding='utf-8')
        return path

    def sign(psbt, wallet):
        reply = rpc('walletprocesspsbt', [psbt, True, 'ALL'], wallet=wallet)
        assert reply['complete'], reply
        return reply['hex']

    def mine(count):
        return rpc('generatetoaddress', [count, mining], wallet=True)

    def inclusion(txid, block):
        proof = rpc('gettxoutproof', [[txid], block])
        assert rpc('verifytxoutproof', [proof]) == [txid]
        return proof

    recipients = []
    split_fee = parent['plan']['fee_sats']
    split_total = parent['plan']['reserve_sats'] - split_fee
    scalar_amounts = [(3, 12_000), (4, split_total - 12_000)]
    wallets = ['rollover-child-0', 'rollover-child-1']
    for wallet, (scalar, amount) in zip(wallets, scalar_amounts, strict=True):
        encoded = rpc('getdescriptorinfo', [f'pk({fixture_wif(scalar)})'])['descriptor']
        pubkey = encoded.split('(', 1)[1].split(')', 1)[0]
        rpc('createwallet', [wallet])
        recipients.append({'holder_pubkey': pubkey, 'payout_address': rpc('getnewaddress', [], wallet=wallet),
                           'reserve_sats': amount, 'fee_sats': split_fee,
                           'delay_blocks': parent['plan']['delay_blocks'], 'min_confirmations': 1})
    paths = [write(f'rollover-recipient-{i}.json', terms) for i, terms in enumerate(recipients)]
    plan_path = runtime / 'rollover-plan.json'
    planned = cli('rollover-plan', *parent_args, '--recipient', paths[0], '--recipient', paths[1],
                  '--split-fee-sats', split_fee, '--output', plan_path)
    rollover = json.loads(plan_path.read_bytes())
    args = (*parent_args, '--rollover', plan_path, '--rollover-id', planned['rollover_id'])
    cli('rollover-plan', *parent_args, '--recipient', paths[0], '--recipient', paths[1],
        '--split-fee-sats', split_fee + 1, '--output', runtime/'invalid-value.json',
        refusal='protected_rollover_value_mismatch')
    changed = json.loads(plan_path.read_bytes())
    changed['children'][1]['funding_script'] = changed['children'][0]['funding_script']
    cli('rollover-psbt', *parent_args, '--rollover', write('changed-rollover.json', changed),
        '--rollover-id', planned['rollover_id'], '--output', runtime/'invalid.psbt',
        refusal='protected_rollover_plan_mismatch')

    split_psbt = runtime / 'rollover.psbt'
    prepared = cli('rollover-psbt', *args, '--output', split_psbt)
    split_hex = sign(split_psbt.read_text().strip(), holder_wallet)
    split_path = runtime / 'rollover.hex'
    split_path.write_text(split_hex, encoding='ascii')
    old_exit = reserve.unsigned_psbt(core, parent, parent['bundle_id'], 'holder')
    old_hex = sign(old_exit['psbt'], holder_wallet)
    early = cli('rollover-check', *args, '--tx-file', split_path)
    assert not early['mempool_eligible'] and early['reject_reason'] == 'non-BIP68-final', early
    receipt_path = runtime / 'confirmed-rollover.json'
    cli('rollover-confirm', *args, '--txid', prepared['txid'], '--block', parent['funding']['block'],
        '--output', receipt_path, refusal='protected_rollover_unconfirmed')

    script = rollover['children'][1]['funding_script']
    wrong_script = script[:4] + ('01' if script[4:6] == '00' else '00') + script[6:]
    assert split_hex.count(script) == 1
    wrong_hex = split_hex.replace(script, wrong_script)
    wrong = runtime / 'wrong-recipient.hex'
    wrong.write_text(wrong_hex, encoding='ascii')
    cli('rollover-check', *args, '--tx-file', wrong, refusal='protected_rollover_transaction_mismatch')
    mine(parent['plan']['delay_blocks'] - early['observation']['confirmations'])
    assert rpc('testmempoolaccept', [[wrong_hex]])[0]['allowed'] is False
    mature = cli('rollover-check', *args, '--tx-file', split_path)
    assert mature['mempool_eligible'] and mature['txid'] == prepared['txid']
    split_txid = rpc('sendrawtransaction', [split_hex])
    conflict = rpc('testmempoolaccept', [[old_hex]])[0]
    assert conflict['allowed'] is False
    split_block = mine(1)[0]
    cli('rollover-confirm', *args, '--txid', split_txid, '--block', split_block, '--output', receipt_path)
    confirmed = json.loads(receipt_path.read_bytes())
    assert confirmed['height'] == mature['observation']['holder_only_earliest_height']
    assert reserve.status(core, parent, parent['bundle_id'])['state'] == 'consumed'
    cli('rollover-psbt', *args, '--output', runtime/'replayed-rollover.psbt', refusal='protected_reserve_unavailable')
    assert not rpc('testmempoolaccept', [[split_hex]])[0]['allowed']

    children = confirmed['successors']
    child_paths = [write(f'rollover-successor-{i}.json', child) for i, child in enumerate(children)]
    child_args = [('--bundle', path, '--bundle-id', child['bundle_id']) for path, child in zip(child_paths, children, strict=True)]
    rpc('invalidateblock', [split_block])
    cli('status', *child_args[0], refusal='protected_funding_reorged')
    cli('rollover-confirm', *args, '--txid', split_txid, '--block', split_block,
        '--output', runtime/'orphaned-rollover.json', refusal='protected_rollover_unconfirmed')
    rpc('reconsiderblock', [split_block])
    assert rpc('getblockhash', [confirmed['height']]) == split_block
    if at_split is not None:
        at_split(rollover, confirmed)

    psbts = []
    for i, (child, (scalar, _)) in enumerate(zip(children, scalar_amounts, strict=True)):
        wallet = wallets[i]
        plan = child['plan']
        private = descriptor(fixture_wif(scalar), plan['mint_pubkey'], plan['delay_blocks'], plan['issuance_hash'])
        checksum = rpc('getdescriptorinfo', [private])['checksum']
        assert rpc('importdescriptors', [[{'desc': private + '#' + checksum, 'timestamp': 0}]], wallet=wallet)[0]['success']
        output = runtime / f'rollover-child-{i}.psbt'
        cli('psbt', *child_args[i], '--route', 'holder', '--output', output)
        psbts.append(output.read_text().strip())

    assert not rpc('walletprocesspsbt', [psbts[0], True, 'ALL'], wallet=wallets[1])['complete']
    signed = [sign(psbt, wallet) for psbt, wallet in zip(psbts, wallets, strict=True)]
    tx_paths = [runtime / f'rollover-child-{i}.hex' for i in range(2)]
    for i, raw in enumerate(signed):
        tx_paths[i].write_text(raw, encoding='ascii')
        early_child = cli('check', *child_args[i], '--route', 'holder', '--tx-file', tx_paths[i])
        assert early_child['reject_reason'] == 'non-BIP68-final' and not early_child['mempool_eligible']
    mine(children[0]['plan']['delay_blocks'] - 1)
    payouts = []
    for i, raw in enumerate(signed):
        checked = cli('check', *child_args[i], '--route', 'holder', '--tx-file', tx_paths[i])
        assert checked['mempool_eligible']
        assert rpc('sendrawtransaction', [raw]) == checked['txid']
        payouts.append(checked)
    payout_block = mine(1)[0]
    for i, paid in enumerate(payouts):
        tx = rpc('getrawtransaction', [paid['txid'], True, payout_block])
        assert tx['hash'] == paid['wtxid'] and tx['vout'][0]['scriptPubKey']['hex'] == children[i]['plan']['payout_script']
        assert rpc('getaddressinfo', [recipients[i]['payout_address']], wallet=wallets[i])['ismine']
        assert paid['payout_sats'] == recipients[i]['reserve_sats'] - recipients[i]['fee_sats']
        assert cli('status', *child_args[i])['state'] == 'consumed'
        paid.update(block=payout_block, height=paid['observation']['holder_only_earliest_height'],
                    txoutproof=inclusion(paid['txid'], payout_block), raw=tx['hex'])
    return {'rollover': confirmed, 'plan': rollover, 'split_raw': split_hex,
            'split_txoutproof': inclusion(split_txid, split_block), 'payouts': payouts,
            'controls': {'early_split': early['reject_reason'], 'conflicting_parent_exit': conflict['reject-reason'],
                         'substituted_output_rejected': True, 'orphaned_split_rejected': True,
                         'foreign_holder_cannot_sign': True, 'early_child_payouts_rejected': True,
                         'consumed_parent_cannot_split_again': True}}


def accounting_prefix(core, root, handoff, node, parent, plan, receipt):
    path = root / 'scripts/protected-fixture-evidence.py'
    spec = importlib.util.spec_from_file_location('fixture_evidence', path)
    evidence = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evidence)
    claim = accounting.bound_claim(accounting.outpoint(parent['funding']))
    funding = parent['funding'] | {'sats': parent['plan']['reserve_sats'], 'script': parent['plan']['funding_script']}
    mint_pin = handoff / 'protected-mint-pin.json'
    issued = evidence.verify_v3_admission({'app_bundle': parent, 'reserve': funding, 'claim_id': claim},
        handoff/'protected-issuance-receipt.json', handoff/'protected-bundle.json', parent['bundle_id'], mint_pin, node)
    quote = issued['intent_id'].removeprefix('cashu:')
    intent = hashlib.sha256(b'proof-grove/protected-issuance-intent/v1\0' + bytes.fromhex(quote)).hexdigest()
    entries = [
        accounting.journal_entry(parent, {'kind': 'register', 'intent': intent},
                                 {'kind': 'observed-regtest-reserve', 'funding': funding}),
        accounting.journal_entry(parent, {'kind': 'issue', 'intent': intent, 'claim': claim}, issued),
        *accounting.rollover_entries(parent, plan, receipt),
    ]
    mint = json.loads(mint_pin.read_bytes())['mint']
    tip = core.rpc('getblockchaininfo', [])
    catalog = {'schema': accounting.CATALOG_SCHEMA, 'genesis': reserve.GENESIS, 'mint': mint,
               'tip_hash': tip['bestblockhash'], 'tip_height': tip['blocks'],
               'bundles': [parent, *receipt['successors']]}
    journal = {'schema': accounting.JOURNAL_SCHEMA, 'genesis': reserve.GENESIS, 'events': [event for event, _ in entries],
               'mint_profile_sha256': digest({'schema': 'proof-grove/protected-accounting-mint/v3', 'mint_url': mint})}
    records = [record for _, record in entries]
    totals = accounting.audit(core, catalog, journal, records)
    assert (totals['declared_reserve_sats'], totals['outstanding_claims_sats'], totals['pending_issuance_sats']) == (
        24750, 24750, 0)
    return catalog, journal, records, totals


def prove_accounting(core, handoff, nova, key_pin, prefix, payouts):
    catalog, journal, records, split_totals = prefix
    for child, paid in zip(catalog['bundles'][1:], payouts, strict=True):
        amount = child['plan']['reserve_sats']
        payout = {key: paid[key] for key in ('txid', 'wtxid', 'block', 'height', 'fee_sats')}
        payout.update(sats=paid['payout_sats'], script=child['plan']['payout_script'], delay_blocks=child['plan']['delay_blocks'])
        event, record = accounting.journal_entry(child, {
            'kind': 'redeem', 'input': accounting.bound_claim(accounting.outpoint(child['funding'])),
            'reserve_before_sats': amount,
        }, {'kind': 'observed-regtest-payout', 'payout': payout})
        journal['events'].append(event)
        records.append(record)
    tip = core.rpc('getblockchaininfo', [])
    catalog.update(tip_hash=tip['bestblockhash'], tip_height=tip['blocks'])
    totals = accounting.audit(core, catalog, journal, records)
    assert all(totals[key] == 0 for key in ('declared_reserve_sats', 'outstanding_claims_sats', 'pending_issuance_sats'))

    def rejected(candidate, evidence):
        try:
            accounting.audit(core, catalog, candidate, evidence)
        except Refused as error:
            return error.code
        raise AssertionError('invalid rollover journal was accepted')

    incomplete = journal | {'events': journal['events'][:6]}
    assert rejected(incomplete, records[:6]) == 'protected_accounting_rollover_group_mismatch'
    changed = copy.deepcopy(journal)
    changed['events'][6]['action']['claim'] = 'ff' * 32
    assert rejected(changed, records) == 'protected_accounting_rollover_group_mismatch'
    replayed = journal | {'events': journal['events'] + journal['events'][2:7]}
    assert rejected(replayed, records + records[2:7]) == 'protected_accounting_invalid_transition'

    directory = handoff / 'rollover-accounting'
    directory.mkdir()
    for name, data in (('catalog', catalog), ('journal', journal), ('admission-evidence', records)):
        (directory / f'{name}.json').write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    journal_file = directory / 'journal.json'
    pin = hashlib.sha256(journal_file.read_bytes()).hexdigest()
    proof_dir = directory / 'proof'
    print(json.dumps({'stage': 'rollover-nova-prove', 'steps': len(records)}), flush=True)
    with (directory / 'prover.json').open('x', encoding='utf-8') as stream:
        subprocess.run([nova, 'prove-journal', proof_dir, journal_file], stdout=stream, check=True, timeout=540)
    transcript = subprocess.check_output([nova, 'verify-journal', proof_dir, journal_file, pin], timeout=120)
    (directory / 'independent-verifier.json').write_bytes(transcript)
    verified = json.loads(transcript)
    assert (verified['verified'], verified['journal_sha256'], verified['verifier_key_sha256'], verified['steps']) == (
        True, pin, key_pin, len(records))
    for key in ('declared_reserve_sats', 'outstanding_claims_sats'):
        assert verified[key] == totals[key]
    assert accounting.audit(core, catalog, journal, records) == totals
    return {'live_split': split_totals, 'final': totals, 'nova': verified, 'partial_group_rejected': True,
            'substituted_claim_rejected': True, 'replayed_group_rejected': True}
