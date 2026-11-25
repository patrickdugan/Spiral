"""Real CDK issuance and a funded holder exit on the same isolated chain."""

import base64
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from threading import Barrier
import time
from urllib.error import URLError
from urllib.request import urlopen

from proofdesk import protected_accounting, protected_payout_evidence, protected_reserve
from proofdesk.domain import Refused
from protected_fixture_keys import HOLDER_PUB, MINT_PUB, descriptor, fixture_wif

SATS = 100_000_000
AMOUNT = 25_000
FEE = 250
DELAY = 6
HOLDER_WALLET = 'cashu-protected-holder'
MINT_WALLET = 'cashu-protected-mint'
NOVA_KEY_SHA256 = 'e472ec73e400c2d88b4e398741596765024fab4ee22ed7b6c600e8753df1034d'


def prepare(core, rpc, deposit, mining_address, runtime, rpc_url, cooperative=False, draft=None):
    beneficiary = rpc('getnewaddress', [], wallet=True)
    commitment = hashlib.sha256(('proof-grove/protected-issuance-intent/v1:' + deposit['intent_id']).encode()).hexdigest()
    schema = protected_reserve.PLAN_SCHEMA
    if draft:
        assert draft['intent_id'] == deposit['intent_id'] and draft['plan_schema'] == protected_reserve.V3_PLAN_SCHEMA
        schema = draft['plan_schema']
        commitment = draft['claim_commitment']
    plan = protected_reserve.plan(
        core, schema=schema, holder_pubkey=HOLDER_PUB, mint_pubkey=MINT_PUB, claim_commitment=commitment,
        reserve_sats=AMOUNT, payout_address=beneficiary, fee_sats=FEE, delay_blocks=DELAY,
        min_confirmations=2,
    )
    issuance_hash = plan['issuance_hash']
    signers = [(HOLDER_WALLET, descriptor(fixture_wif(1), MINT_PUB, DELAY, issuance_hash))]
    if cooperative:
        signers.append((MINT_WALLET, descriptor(HOLDER_PUB, fixture_wif(2), DELAY, issuance_hash)))
    for wallet, private in signers:
        rpc('createwallet', [wallet, False, True])
        checksum = rpc('getdescriptorinfo', [private])['checksum']
        imported = rpc('importdescriptors', [[{'desc': private + '#' + checksum, 'timestamp': 0}]], wallet=wallet)
        assert imported[0]['success'], imported
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


def verify_certificate(node, root, certificate, bundle, legacy_melt):
    return json.loads(subprocess.check_output([
        node, str(root / 'wallet/test-verify-protected-issuance.mjs'), str(certificate),
        bundle['bundle_id'], legacy_melt['certificate_sha256'], str(bundle['plan']['reserve_sats']),
    ], cwd=root, text=True, timeout=45))


def cooperate(core, rpc, client, operation, runtime, mining_address, bundle):
    bundle_id = bundle['bundle_id']
    outpoint = bundle['funding']
    common = ('--id', operation, '--bundle', str(runtime / 'protected-bundle.json'))
    unsigned_file, partial_file = runtime / 'cooperative.psbt', runtime / 'holder-partial.psbt'
    before = client('protected-melt-status', *common)
    assert before['state'] == 'unspent' and before['spender'] is None
    prepared = client('protected-melt-prepare', *common, '--output', str(unsigned_file),
                      '--core-config', str(runtime / 'protected-core.json'), '--python', sys.executable)
    unsigned = unsigned_file.read_text(encoding='ascii').strip()
    assert not prepared['observation']['eligible_in_next_block']
    client('protected-melt-settle', *common, '--psbt', str(unsigned_file), expect_error='protected_melt_holder_signature_required')
    mint_only = rpc('walletprocesspsbt', [unsigned, True, 'ALL', False, False], wallet=MINT_WALLET)['psbt']
    mint_only_file = runtime / 'mint-only.psbt'
    mint_only_file.write_text(mint_only, encoding='ascii')
    client('protected-melt-settle', *common, '--psbt', str(mint_only_file), expect_error='protected_melt_holder_signature_required')
    holder = rpc('walletprocesspsbt', [unsigned, True, 'ALL', False, False], wallet=HOLDER_WALLET)['psbt']
    partial_file.write_text(holder, encoding='ascii')
    settle_args = (*common, '--psbt', str(partial_file))

    # Keep a syntactically valid but incorrect holder signature on the pinned payout.
    sig = core.rpc('decodepsbt', [holder])['inputs'][0]['partial_signatures'][HOLDER_PUB]
    raw = base64.b64decode(holder)
    encoded = bytes.fromhex(sig)
    changed = encoded[:-2] + bytes([encoded[-2] ^ 1]) + encoded[-1:]
    assert raw.count(encoded) == 1
    forged_file = runtime / 'forged-holder.psbt'
    forged_file.write_bytes(base64.b64encode(raw.replace(encoded, changed)))
    client('protected-melt-settle', *common, '--psbt', str(forged_file), expect_error='protected_melt_cosign_refused')
    substitute = rpc('getnewaddress', [], wallet=True)
    payout_sats = bundle['plan']['payout_sats']
    amount = format(Decimal(payout_sats) / SATS, '.8f')
    substituted = core.rpc('createpsbt', [[{'txid':outpoint['txid'], 'vout':outpoint['vout'],
                                          'sequence':protected_reserve.COOPERATIVE_SEQUENCE}], [{substitute:amount}], 0, False])
    substituted_file = runtime / 'substituted.psbt'
    substituted_file.write_text(substituted, encoding='ascii')
    client('protected-melt-settle', *common, '--psbt', str(substituted_file), expect_error='protected_payout_mismatch')
    assert client('protected-melt-status', *common)['state'] == 'unspent'

    emergency = protected_reserve.unsigned_psbt(core, bundle, bundle_id, 'holder')
    exit_tx = rpc('walletprocesspsbt', [emergency['psbt'], True, 'ALL'], wallet=HOLDER_WALLET)['hex']
    early = rpc('testmempoolaccept', [[exit_tx]])[0]
    assert early['reject-reason'] == 'non-BIP68-final'

    accepted = client('protected-melt-settle', *settle_args)
    assert accepted['state'] == 'pending-spend' and accepted['cooperative_payout_observed'], accepted
    assert accepted['expected_cooperative_txid'] == prepared['txid'] == accepted['spender']['txid']
    assert client('protected-melt-settle', *settle_args) == accepted
    cooperative_block = rpc('generatetoaddress', [1,mining_address], wallet=True)[0]
    confirmed = client('protected-melt-status', *common)
    assert confirmed['state'] == 'consumed' and confirmed['spender']['block'] == cooperative_block
    cooperative_tx = rpc('getrawtransaction', [prepared['txid'], True, cooperative_block])
    assert cooperative_tx['vout'][0]['scriptPubKey']['hex'] == bundle['plan']['payout_script']
    cooperative_inclusion = rpc('gettxoutproof', [[prepared['txid']], cooperative_block])
    assert rpc('verifytxoutproof', [cooperative_inclusion]) == [prepared['txid']]

    rpc('invalidateblock', [cooperative_block])
    reverted = client('protected-melt-status', *common)
    assert reverted['state'] == 'pending-spend' and reverted['spender']['block'] is None
    for _ in range(DELAY - reverted['confirmations']):
        rpc('generateblock', [mining_address, []])
    barrier = Barrier(2)

    def run_melt():
        barrier.wait(timeout=10)
        return client('protected-melt-settle', *settle_args)

    def run_exit():
        barrier.wait(timeout=10)
        try:
            return {'txid':rpc('sendrawtransaction', [exit_tx])}
        except RuntimeError as error:
            return {'refusal':str(error)}

    with ThreadPoolExecutor(max_workers=2) as pool:
        cooperative_attempt, exit_attempt = pool.submit(run_melt), pool.submit(run_exit)
        concurrent_melt, concurrent_exit = cooperative_attempt.result(), exit_attempt.result()
    assert concurrent_melt['cooperative_payout_observed'] and 'refusal' in concurrent_exit

    holder_block = rpc('generateblock', [mining_address, [exit_tx]])['hash']
    holder_spend = client('protected-melt-status', *common)
    assert holder_spend['state'] == 'consumed' and holder_spend['spender']['route'] == 'holder'
    assert holder_spend['spender']['block'] == holder_block
    holder_txid = holder_spend['spender']['txid']
    holder_inclusion = rpc('gettxoutproof', [[holder_txid], holder_block])
    assert rpc('verifytxoutproof', [holder_inclusion]) == [holder_txid]
    replay = client('protected-melt-settle', *settle_args)
    assert replay['spender'] == holder_spend['spender'] and replay['cooperative_payout_observed'] is False
    rpc('invalidateblock', [outpoint['block']])
    orphaned = client('protected-melt-status', *common)
    assert orphaned['state'] == 'funding-unavailable' and orphaned['reason'] == 'protected_funding_reorged'
    rpc('reconsiderblock', [outpoint['block']])
    assert client('protected-melt-status', *common)['spender'] == holder_spend['spender']
    funding_inclusion = rpc('gettxoutproof', [[outpoint['txid']], outpoint['block']])
    assert rpc('verifytxoutproof', [funding_inclusion]) == [outpoint['txid']]
    return {
        'schema':'proof-grove/protected-melt-regtest/v1', 'network':'regtest', 'bundle_id':bundle_id,
        'app_bundle':bundle,
        'funding':outpoint, 'payout_sats':payout_sats, 'fee_sats':bundle['plan']['fee_sats'],
        'cooperative_confirmed':confirmed, 'cooperative_reorged_to_pending':reverted,
        'holder_confirmed_on_replacement_chain':holder_spend, 'old_settlement_request_replayed':replay,
        'funding_orphaned':orphaned, 'concurrent_melt':concurrent_melt, 'concurrent_exit':concurrent_exit,
        'controls':{'no_signature':True, 'mint_signature_only':True, 'forged_holder_signature':True,
                    'substituted_beneficiary':True, 'early_holder_rejection':early['reject-reason'],
                    'melt_retry_idempotent':True},
        'public_transactions':{'cooperative':cooperative_tx['hex'], 'holder':exit_tx},
        'merkle_inclusion':{'funding':funding_inclusion, 'cooperative':cooperative_inclusion, 'holder':holder_inclusion},
    }


def finish(core, rpc, client, operation, mint_url, handoff, mining_address,
           bundle, funding_hex, issuance, legacy_melt, node, root, certificate, *, rollover_runtime=None):
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
    independent = verify_certificate(node, root, certificate, bundle, legacy_melt)
    assert independent['proofs_sha256'] == offline['proofs_sha256'] and independent['changed_secret_rejected']
    if rollover_runtime is not None:
        import protected_rollover_fixture

        split = protected_rollover_fixture.run(core, rpc, root, rollover_runtime, mining_address, bundle, HOLDER_WALLET)
        return {'schema': 'proof-grove/protected-rollover-regtest/v1', 'network': 'regtest', 'genesis': bundle['plan']['genesis'],
                'parent_bundle': bundle, 'parent_funding_raw': funding_hex, 'cdk_issuance': independent,
                'legacy_cdk_melt': legacy_melt, 'mint_process_stopped': True, 'offline_dleq_reverified': True, **split}
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
    receipt = {
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
    if plan['schema'] == protected_reserve.V3_PLAN_SCHEMA:
        receipt['bitcoin_chain_evidence'] = protected_payout_evidence.capture(
            rpc, checked['observation']['funding_height'], height, outpoint['block'], payout_block,
        )
    return receipt


def account(core, rpc, receipt, handoff, nova, node, root):
    """Prove the exact fresh journal, verify it separately and reconcile it while Core is live."""
    payout = receipt['payout']
    tip = core.rpc('getblockchaininfo', [])
    assert tip['bestblockhash'] == payout['block'] and tip['blocks'] == payout['height']
    directory = handoff/'live-accounting'
    directory.mkdir()
    admission = directory/'holder-receipt.json'
    admission.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    mint_pin = handoff/'protected-mint-pin.json'
    bundle = receipt['app_bundle']
    issuance = ('--v3-receipt', handoff/'protected-issuance-receipt.json',
                '--v3-bundle', handoff/'protected-bundle.json', '--v3-bundle-id', bundle['bundle_id'],
                '--v3-mint-pin', mint_pin, '--node', node)
    builder = [sys.executable, str(root/'scripts/protected-fixture-evidence.py')]
    journal_files = directory/'journal-evidence'
    journal_sha = subprocess.check_output([*builder, 'journal', admission, journal_files, *issuance],
                                          text=True, timeout=40).strip()
    proof_dir = directory/'proof'
    with (directory/'prover.json').open('x', encoding='utf-8') as stream:
        subprocess.run([nova, 'prove-journal', proof_dir, journal_files/'journal.json'], stdout=stream,
                       check=True, timeout=210)
    verification = directory/'verification'
    result = json.loads(subprocess.check_output([
        *builder, 'audit-v3', admission, verification, *issuance, '--proof-dir', proof_dir,
        '--nova-verifier', nova, '--journal-sha256', journal_sha, '--nova-key-sha256', NOVA_KEY_SHA256,
        '--anchor-height', str(tip['blocks']), '--anchor-hash', tip['bestblockhash'],
    ], timeout=210))

    catalog = {'schema': protected_accounting.CATALOG_SCHEMA, 'genesis': receipt['genesis'],
               'mint': json.loads(mint_pin.read_bytes())['mint'],
               'tip_hash': tip['bestblockhash'], 'tip_height': tip['blocks'], 'bundles': [bundle]}
    journal = json.loads((verification/'journal.json').read_bytes())
    records = json.loads((verification/'admission-evidence.json').read_bytes())
    totals = protected_accounting.audit(core, catalog, journal, records)
    assert all(result['nova'][key] == totals[key] == 0 for key in ('declared_reserve_sats', 'outstanding_claims_sats'))
    rpc('invalidateblock', [payout['block']])
    try:
        try:
            protected_accounting.audit(core, catalog, journal, records)
        except Refused as error:
            assert error.code == 'protected_accounting_stale_catalog', error
        else:
            raise AssertionError('the previous payout tip survived invalidation')
    finally:
        rpc('reconsiderblock', [payout['block']])
    assert protected_accounting.audit(core, catalog, journal, records) == totals
    report = totals | {'schema': 'proof-grove/live-v3-regtest-accounting/v1', 'journal_sha256': journal_sha,
                       'nova_key_sha256': NOVA_KEY_SHA256, 'nova_proof_sha256': result['nova']['proof_sha256'],
                       'settlement_record_sha256': result['settlement_record_sha256'],
                       'payout_txid': payout['txid'], 'payout_sats': payout['sats'], 'stale_tip_rejected': True}
    (directory/'catalog.json').write_text(json.dumps(catalog, indent=2) + '\n', encoding='utf-8')
    (directory/'live-reconciliation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report
