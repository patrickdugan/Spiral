"""Real CDK issuance and a funded holder exit on the same isolated chain."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

from proofdesk import protected_reserve
from protected_fixture_keys import HOLDER_PUB, MINT_PUB, descriptor, fixture_wif

SATS = 100_000_000
AMOUNT = 25_000
FEE = 250
DELAY = 6
HOLDER_WALLET = 'cashu-protected-holder'


def prepare(core, rpc, deposit, mining_address, runtime, rpc_url):
    rpc('createwallet', [HOLDER_WALLET, False, True])
    private = descriptor(fixture_wif(1), MINT_PUB, DELAY)
    checksum = rpc('getdescriptorinfo', [private])['checksum']
    imported = rpc('importdescriptors', [[{'desc': private + '#' + checksum, 'timestamp': 0}]],
                   wallet=HOLDER_WALLET)
    assert imported[0]['success'], imported
    beneficiary = rpc('getnewaddress', [], wallet=True)
    commitment = hashlib.sha256(('proof-grove/protected-issuance-intent/v1:' + deposit['intent_id']).encode()).hexdigest()
    plan = protected_reserve.plan(
        core, holder_pubkey=HOLDER_PUB, mint_pubkey=MINT_PUB, claim_commitment=commitment,
        reserve_sats=AMOUNT, payout_address=beneficiary, fee_sats=FEE, delay_blocks=DELAY,
        min_confirmations=2,
    )
    txid = rpc('sendtoaddress', [plan['funding_address'], AMOUNT / SATS], wallet=True)
    block, _ = rpc('generatetoaddress', [2, mining_address], wallet=True)
    tx = rpc('getrawtransaction', [txid, True, block])
    output = next(out for out in tx['vout'] if out['scriptPubKey']['hex'] == plan['funding_script'])
    bundle = protected_reserve.attach(core, plan, plan['plan_id'], {'txid': txid, 'vout': output['n'], 'block': block})
    bundle_path = runtime / 'protected-bundle.json'
    bundle_path.write_text(json.dumps(bundle), encoding='utf-8')
    config = runtime / 'protected-core.json'
    config.write_text(json.dumps({'core': {'url': rpc_url, 'username': 'proofgrove',
                                         'password_env': 'PG_TEST_RPC_PASSWORD'}}), encoding='utf-8')
    args = ['--bundle', str(bundle_path), '--bundle-id', bundle['bundle_id'],
            '--core-config', str(config), '--python', sys.executable]
    return bundle, args, tx['hex']


def check_normal_melt(node, root, mint, vault, operation, bundle, environment, certificate):
    result = subprocess.run(
        [node, str(root / 'wallet' / 'test-protected-melt.mjs'), mint,
         str(vault), operation, bundle['plan']['payout_address'], str(certificate)],
        cwd=root, env=environment, text=True, capture_output=True, timeout=90, check=False,
    )
    if result.returncode:
        raise AssertionError('Protected Cashu legacy melt control failed: ' + result.stderr[-1000:])
    return json.loads(result.stdout)


def finish(core, rpc, client, operation, mint_url, handoff, mining_address,
           bundle, funding_hex, issuance, legacy_melt, node, root, certificate):
    handoff = Path(handoff)
    (handoff / 'stop-requested').touch(exist_ok=False)
    for _ in range(150):
        if (handoff / 'mint-stopped').is_file():
            break
        time.sleep(0.2)
    else:
        raise RuntimeError('Mint supervisor did not confirm shutdown')
    try:
        with urlopen(mint_url + '/v1/info', timeout=2):
            raise AssertionError('Mint is still serving requests')
    except URLError:
        pass
    offline = client('protected-audit', '--id', operation)
    assert offline['offline_keyset_audit'] and offline['dleq_verified']
    assert offline['proofs_sha256'] == issuance['proofs_sha256']
    independent = json.loads(subprocess.check_output([node,str(root/'wallet/test-verify-protected-issuance.mjs'),
        str(certificate),bundle['bundle_id'],legacy_melt['certificate_sha256']],cwd=root,text=True,timeout=30))
    assert independent['proofs_sha256'] == offline['proofs_sha256'] and independent['changed_secret_rejected']
    outpoint, plan = bundle['funding'], bundle['plan']
    preflight = protected_reserve.unsigned_psbt(core, bundle, bundle['bundle_id'], 'holder')
    signed = rpc('walletprocesspsbt', [preflight['psbt'], True, 'ALL'], wallet=HOLDER_WALLET)
    assert signed['complete'], signed
    blocks = DELAY - preflight['observation']['confirmations']
    if blocks > 0:
        early = protected_reserve.check_signed(core, bundle, bundle['bundle_id'], 'holder', signed['hex'])
        assert early['reject_reason'] == 'non-BIP68-final', early
        rpc('generatetoaddress', [blocks, mining_address], wallet=True)
    checked = protected_reserve.check_signed(core, bundle, bundle['bundle_id'], 'holder', signed['hex'])
    assert checked['mempool_eligible'] and checked['fee_sats'] == FEE, checked
    paid = rpc('sendrawtransaction', [signed['hex']])
    payout_block = rpc('generatetoaddress', [1, mining_address], wallet=True)[0]
    tx = rpc('getrawtransaction', [paid, True, payout_block])
    height = checked['observation']['funding_height'] + DELAY
    assert tx['txid'] == checked['txid'] and rpc('getblockhash', [height]) == payout_block
    assert tx['vout'][0]['scriptPubKey']['hex'] == plan['payout_script']
    assert protected_reserve.status(core, bundle, bundle['bundle_id'])['state'] == 'consumed'
    spent = rpc('testmempoolaccept', [[signed['hex']]])[0]
    assert spent['allowed'] is False
    claim = hashlib.sha256(b'proof-grove/protected-reserve/v1\0' + bytes.fromhex(plan['genesis'])
                          + bytes.fromhex(outpoint['txid']) + outpoint['vout'].to_bytes(4, 'big')).hexdigest()
    return {
        'schema': 'proof-grove/protected-reserve-regtest/v1', 'network': 'regtest', 'genesis': plan['genesis'],
        'claim_id': claim, 'app_bundle': bundle, 'mature_holder_check': checked,
        'reserve': outpoint | {'sats': AMOUNT, 'script': plan['funding_script']},
        'payout': {'txid': paid, 'wtxid': tx['hash'], 'block': payout_block, 'height': height,
                   'script': plan['payout_script'], 'sats': AMOUNT - FEE, 'fee_sats': FEE, 'delay_blocks': DELAY},
        'cdk_issuance': independent, 'legacy_cdk_melt': legacy_melt,
        'controls': {'mint_process_stopped': True, 'offline_dleq_reverified': True,
                     'reserve_consumed': True, 'replayed_exit': spent['reject-reason']},
        'public_transactions': {'funding': funding_hex, 'payout': signed['hex']},
        'public_headers': {'funding': rpc('getblockheader', [outpoint['block'], False]),
                           'payout': rpc('getblockheader', [payout_block, False])},
        'evidence': 'bitcoin-core-regtest-consensus',
    }
