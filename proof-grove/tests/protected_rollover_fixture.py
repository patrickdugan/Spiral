"""Exercise a mined two-recipient rollover of a real V3 issuance reserve."""

import json
import subprocess
import sys

from proofdesk import protected_reserve as reserve
from protected_fixture_keys import descriptor, fixture_wif


def run(core, rpc, root, runtime, mining, parent, holder_wallet):
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
