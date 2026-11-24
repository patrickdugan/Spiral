"""Bitcoin Core integration for an issuance-funded, single-outpoint reserve.

Run with Python 3.11+ and an installed Bitcoin Core binary with Miniscript
descriptors. The wallets, test keys and coins are isolated to regtest.
"""
from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
from threading import Barrier
import time

from protected_fixture_keys import HOLDER_PUB, MINT_PUB, descriptor, fixture_wif

SATOSHIS = 100_000_000
RESERVE = 25_000
FEE = 250
DELAY = 6
APP_ROOT = Path(__file__).resolve().parents[1]


class CoreRPCError(Exception):
    pass


class CoreClient:
    def __init__(self, port: int, auth: str, path: str = '/'):
        self.port, self.auth, self.path = port, auth, path

    def rpc(self, method: str, params: list):
        body = json.dumps({'jsonrpc': '2.0', 'id': 'protected-regtest', 'method': method, 'params': params})
        client = http.client.HTTPConnection('127.0.0.1', self.port, timeout=120)
        try:
            client.request('POST', self.path, body, {'Authorization': self.auth, 'Content-Type': 'application/json'})
            result = json.load(client.getresponse())
        finally:
            client.close()
        if result.get('error'):
            raise CoreRPCError(result['error']['message'])
        return result['result']


def checked_descriptor(core: CoreClient, expression: str) -> str:
    return f'{expression}#{core.rpc("getdescriptorinfo", [expression])["checksum"]}'


def accept(core: CoreClient, tx: str) -> dict:
    return core.rpc('testmempoolaccept', [[tx]])[0]


def assert_refused(result: dict) -> str:
    assert result['allowed'] is False, result
    return result['reject-reason']


def reobserve_funding(core, holder, mining_address, original, bundle_path, scratch, holder_cli):
    saved = bundle_path.read_bytes()
    bundle = json.loads(saved)
    original_block = bundle['funding']['block']
    previous_maturity = core.rpc('getblockheader', [original_block])['height'] + DELAY
    args = ('--bundle', bundle_path, '--bundle-id', bundle['bundle_id'])

    # Omit the orphaned transaction until the old CSV maturity has passed.
    empty = [core.rpc('generateblock', [mining_address, []])['hash'] for _ in range(DELAY + 1)]
    active_block = core.rpc('generateblock', [mining_address, [original['hex']]])['hash']
    assert core.rpc('getblockheader', [original_block])['confirmations'] == -1
    active_height = core.rpc('getblockheader', [active_block])['height']
    assert active_height > previous_maturity
    assert core.rpc('getrawtransaction', [original['txid'], True, active_block])['hex'] == original['hex']

    holder_cli('status', *args, rejected='protected_funding_reorged')
    holder_cli('status', *args, '--active-funding-block', empty[-1], rejected='protected_funding_mismatch')
    active_args = (*args, '--active-funding-block', active_block)
    observed = holder_cli('status', *active_args)
    assert observed['pinned_funding_block'] == original_block and observed['active_funding_block'] == active_block
    assert observed['state'] == 'unspent' and observed['funding_height'] == active_height
    assert observed['confirmations'] == 1 and not observed['eligible_in_next_block']
    assert observed['holder_only_earliest_height'] == active_height + DELAY

    tampered = scratch / 'tampered-bundle.json'
    wrong_outpoint = bundle['funding'] | {'vout': bundle['funding']['vout'] ^ 1}
    tampered.write_text(json.dumps(bundle | {'funding': wrong_outpoint}), encoding='utf-8')
    holder_cli('status', '--bundle', tampered, '--bundle-id', bundle['bundle_id'],
               '--active-funding-block', active_block, rejected='protected_bundle_mismatch')

    psbt = scratch / 'reobserved.psbt'
    holder_cli('psbt', *active_args, '--route', 'cooperative', '--output', psbt,
               rejected='protected_holder_reobservation_only')
    prepared = holder_cli('psbt', *active_args, '--route', 'holder', '--output', psbt)
    assert prepared['bundle_id'] == bundle['bundle_id'] and prepared['observation'] == observed
    signed = holder.rpc('walletprocesspsbt', [psbt.read_text(encoding='ascii').strip(), True, 'ALL'])
    assert signed['complete'], signed
    raw = signed['hex']
    vin = core.rpc('decoderawtransaction', [raw])['vin'][0]
    funding = bundle['funding']
    assert (vin['txid'], vin['vout']) == (funding['txid'], funding['vout'])
    txid_le = bytes.fromhex(funding['txid'])[::-1].hex()
    prevout = txid_le + funding['vout'].to_bytes(4, 'little').hex()
    wrong_prevout = txid_le + wrong_outpoint['vout'].to_bytes(4, 'little').hex()
    assert raw.count(prevout) == 1
    wrong_txfile = scratch / 'wrong-reobserved-payout.hex'
    wrong_txfile.write_text(raw.replace(prevout, wrong_prevout), encoding='ascii')
    holder_cli('check', *active_args, '--route', 'holder', '--tx-file', wrong_txfile,
               rejected='protected_payout_mismatch')
    txfile = scratch / 'reobserved-payout.hex'
    txfile.write_text(raw, encoding='ascii')
    check_args = (*active_args, '--route', 'holder', '--tx-file', txfile)
    early = holder_cli('check', *check_args)
    assert not early['mempool_eligible'] and early['reject_reason'] == 'non-BIP68-final'
    core.rpc('generatetoaddress', [DELAY - 1, mining_address])
    reviewed = holder_cli('check', *check_args)
    assert reviewed['mempool_eligible'] and reviewed['bundle_id'] == bundle['bundle_id']
    assert reviewed['txid'] == prepared['txid'] and reviewed['payout_sats'] == RESERVE - FEE
    payout_block = core.rpc('generateblock', [mining_address, [raw]])['hash']
    assert core.rpc('getblockhash', [active_height + DELAY]) == payout_block
    assert holder_cli('status', *active_args)['state'] == 'consumed'
    assert bundle_path.read_bytes() == saved

    core.rpc('invalidateblock', [empty[0]])
    core.rpc('reconsiderblock', [original_block])
    return {'bundle_id': bundle['bundle_id'], 'pinned_funding_block': original_block,
            'active_funding_block': active_block, 'active_funding_height': active_height,
            'payout_block': payout_block, 'payout_height': active_height + DELAY,
            'payout_txid': reviewed['txid'], 'payout_sats': reviewed['payout_sats'],
            'wrong_block_rejected': True, 'wrong_outpoint_rejected': True,
            'cooperative_override_rejected': True, 'old_maturity_rejected': early['reject_reason']}


def demo(core: CoreClient, wallet, scratch: Path, holder_cli) -> dict:
    chain = core.rpc('getblockchaininfo', [])
    assert chain['chain'] == 'regtest' and chain['blocks'] == 0
    for name in ('funding', 'holder', 'mint'):
        core.rpc('createwallet', [name, False, name != 'funding'])
    funding, holder, mint = (wallet(name) for name in ('funding', 'holder', 'mint'))

    # Each signer knows the complete policy and holds exactly its own key.
    for signer, keys in ((holder, (fixture_wif(1), MINT_PUB)),
                         (mint, (HOLDER_PUB, fixture_wif(2)))):
        private = checked_descriptor(core, descriptor(*keys, DELAY))
        result = signer.rpc('importdescriptors', [[{'desc': private, 'timestamp': 0}]])
        assert result[0]['success'], result

    mining_address = funding.rpc('getnewaddress', [])
    for count in (25, 25, 25, 26):
        core.rpc('generatetoaddress', [count, mining_address])
    payout_address = funding.rpc('getnewaddress', [])
    claim_commitment = hashlib.sha256(b'proof-grove/regtest-protected-issuance-fixture').hexdigest()
    plan_path = scratch / 'plan.json'
    created = holder_cli('plan', '--holder-pubkey', HOLDER_PUB, '--mint-pubkey', MINT_PUB,
                         '--claim-commitment', claim_commitment, '--reserve-sats', str(RESERVE),
                         '--payout-address', payout_address, '--fee-sats', str(FEE),
                         '--delay-blocks', str(DELAY), '--min-confirmations', '1', '--output', plan_path)
    saved_plan = json.loads(plan_path.read_bytes())
    public = saved_plan['descriptor']
    reserve_address = created['funding_address']
    txid = funding.rpc('sendtoaddress', [reserve_address, RESERVE / SATOSHIS])
    funding_block = core.rpc('generatetoaddress', [1, mining_address])[0]
    original = core.rpc('getrawtransaction', [txid, True, funding_block])
    output = next(row for row in original['vout'] if row['scriptPubKey'].get('address') == reserve_address)
    vout = output['n']
    assert round(output['value'] * SATOSHIS) == RESERVE
    assert core.rpc('gettxout', [txid, vout, False])['confirmations'] == 1

    substituted_address = funding.rpc('getnewaddress', [])
    bundle_path = scratch / 'bundle.json'
    attach_args = ('--plan', plan_path, '--plan-id', created['plan_id'], '--txid', txid, '--block', funding_block)
    holder_cli('attach', *attach_args, '--vout', str(vout ^ 1), '--output', bundle_path,
               rejected='protected_funding_mismatch')
    attached = holder_cli('attach', *attach_args, '--vout', str(vout), '--output', bundle_path)
    saved_bundle = json.loads(bundle_path.read_bytes())
    bundle_args = ('--bundle', bundle_path, '--bundle-id', attached['bundle_id'])
    holder_cli('status', '--bundle', bundle_path, '--bundle-id', '0' * 64,
               rejected='protected_bundle_mismatch')

    def psbt(route):
        path = scratch / f'{route}.psbt'
        result = holder_cli('psbt', *bundle_args, '--route', route, '--output', path)
        assert not result['observation']['eligible_in_next_block']
        return path.read_text(encoding='ascii').strip()

    def checked(raw, route='holder', rejected=None):
        path = scratch / 'checker-transaction.hex'
        path.write_text(raw, encoding='ascii')
        return holder_cli('check', *bundle_args, '--route', route, '--tx-file', path, rejected=rejected)

    coop_unsigned = psbt('cooperative')
    mint_partial = mint.rpc('walletprocesspsbt', [coop_unsigned, True, 'ALL', True, False])['psbt']
    holder_partial = holder.rpc('walletprocesspsbt', [coop_unsigned, True, 'ALL', True, False])['psbt']
    assert not core.rpc('finalizepsbt', [mint_partial])['complete']
    assert not core.rpc('finalizepsbt', [holder_partial])['complete']
    combined = core.rpc('combinepsbt', [[mint_partial, holder_partial]])
    cooperative_tx = core.rpc('finalizepsbt', [combined])['hex']
    assert accept(core, cooperative_tx)['allowed']
    assert checked(cooperative_tx, 'cooperative')['mempool_eligible']

    # Model refusal from this point onward by removing the mint's signing wallet.
    mint.rpc('unloadwallet', [])
    emergency = holder.rpc('walletprocesspsbt', [psbt('holder'), True, 'ALL'])
    assert emergency['complete'], emergency
    emergency_tx = emergency['hex']
    early = assert_refused(accept(core, emergency_tx))
    assert early == 'non-BIP68-final', early
    early_review = checked(emergency_tx)
    assert not early_review['mempool_eligible'] and early_review['reject_reason'] == early
    core.rpc('generatetoaddress', [DELAY - 1, mining_address])
    assert accept(core, emergency_tx)['allowed']
    assert accept(core, cooperative_tx)['allowed']
    reviewed = checked(emergency_tx)
    assert reviewed['mempool_eligible'] and reviewed['payout_sats'] == RESERVE - FEE and reviewed['fee_sats'] == FEE

    decoded = core.rpc('decoderawtransaction', [emergency_tx])
    payout_script = decoded['vout'][0]['scriptPubKey']['hex']
    substitute_script = core.rpc('validateaddress', [substituted_address])['scriptPubKey']
    assert len(payout_script) == len(substitute_script) and emergency_tx.count(payout_script) == 1
    substituted = emergency_tx.replace(payout_script, substitute_script)
    beneficiary = assert_refused(accept(core, substituted))
    checked(substituted, rejected='protected_payout_mismatch')
    changed_value = (RESERVE - FEE - 1).to_bytes(8, 'little').hex()
    payout_value = (RESERVE - FEE).to_bytes(8, 'little').hex()
    assert emergency_tx.count(payout_value) == 1
    checked(emergency_tx.replace(payout_value, changed_value), rejected='protected_payout_mismatch')

    barrier = Barrier(2)

    def broadcast(candidate):
        barrier.wait(timeout=10)
        try:
            return {'txid': core.rpc('sendrawtransaction', [candidate])}
        except CoreRPCError as error:
            return {'rejection': str(error)}

    # Both same-fee candidates were eligible at one tip. Submit them together,
    # then have the fixture miner select the holder's valid transaction.
    with ThreadPoolExecutor(max_workers=2) as race:
        raced = list(race.map(broadcast, (emergency_tx, cooperative_tx)))
    assert sum('txid' in result for result in raced) == 1, raced
    assert holder_cli('status', *bundle_args)['state'] == 'pending-spend'
    spend = decoded['txid']
    payout_block = core.rpc('generateblock', [mining_address, [emergency_tx]])['hash']
    expected_height = core.rpc('getblockheader', [funding_block])['height'] + DELAY
    assert core.rpc('getblockhash', [expected_height]) == payout_block
    payout = core.rpc('getrawtransaction', [spend, True, payout_block])
    assert payout['txid'] == decoded['txid'] == spend
    assert payout['vout'][0]['scriptPubKey']['address'] == payout_address
    assert round(payout['vout'][0]['value'] * SATOSHIS) == RESERVE - FEE
    assert core.rpc('gettxout', [txid, vout, False]) is None
    assert holder_cli('status', *bundle_args)['state'] == 'consumed'
    conflict = assert_refused(accept(core, cooperative_tx))
    replay = assert_refused(accept(core, emergency_tx))

    core.rpc('invalidateblock', [payout_block])
    assert core.rpc('getblockheader', [payout_block])['confirmations'] == -1
    assert core.rpc('gettxout', [txid, vout, False]) is not None
    assert holder_cli('status', *bundle_args)['state'] in ('unspent', 'pending-spend')
    core.rpc('reconsiderblock', [payout_block])
    assert core.rpc('getblockhash', [expected_height]) == payout_block
    assert core.rpc('gettxout', [txid, vout, False]) is None

    core.rpc('invalidateblock', [funding_block])
    assert core.rpc('getblockheader', [funding_block])['confirmations'] == -1
    assert core.rpc('gettxout', [txid, vout, False]) is None
    holder_cli('status', *bundle_args, rejected='protected_funding_reorged')
    reobserved = reobserve_funding(core, holder, mining_address, original, bundle_path, scratch, holder_cli)
    assert core.rpc('getblockhash', [expected_height]) == payout_block

    genesis = core.rpc('getblockhash', [0])
    claim_id = hashlib.sha256(b'proof-grove/protected-reserve/v1\0' + bytes.fromhex(genesis)
                              + bytes.fromhex(txid) + vout.to_bytes(4, 'big')).hexdigest()
    return {
        'schema': 'proof-grove/protected-reserve-regtest/v1', 'network': 'regtest',
        'genesis': genesis, 'chain_version': core.rpc('getnetworkinfo', [])['subversion'],
        'claim_id': claim_id, 'reserve_descriptor': public,
        'app_bundle': saved_bundle, 'mature_holder_check': reviewed,
        'holder_funding_reobservation': reobserved,
        'reserve': {'txid': txid, 'vout': vout, 'sats': RESERVE, 'block': funding_block,
                    'script': output['scriptPubKey']['hex']},
        'payout': {'txid': spend, 'wtxid': payout['hash'], 'block': payout_block,
                   'height': expected_height, 'script': payout_script, 'sats': RESERVE - FEE,
                   'fee_sats': FEE, 'delay_blocks': DELAY},
        'controls': {'early_exit': early, 'substituted_beneficiary': beneficiary,
                     'conflicting_melt': conflict, 'replayed_exit': replay,
                     'single_signer_cannot_cooperate': True, 'mint_signer_unloaded': True,
                     'app_rejected_wrong_outpoint_plan_and_payout': True,
                     'both_paths_eligible_before_confirmation': True, 'concurrent_broadcasts': raced,
                     'reorg_reverted_consumption': True, 'funding_reorg_invalidated_reserve': True},
        'public_transactions': {'funding': original['hex'], 'payout': emergency_tx,
                                'conflicting_cooperative_payout': cooperative_tx},
        'public_headers': {'funding': core.rpc('getblockheader', [funding_block, False]),
                           'payout': core.rpc('getblockheader', [payout_block, False])},
        'evidence': 'bitcoin-core-regtest-consensus',
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bitcoind', default='bitcoind')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='proof-grove-protected-') as scratch:
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        user, password = 'proofgrove', secrets.token_hex(24)
        command = [args.bitcoind, '-regtest', f'-datadir={scratch}', '-server=1', '-listen=0',
                   '-connect=0', '-dnsseed=0', '-discover=0', '-keypool=16',
                   '-fallbackfee=0.00001', '-printtoconsole=0',
                   f'-rpcport={port}', f'-rpcuser={user}', f'-rpcpassword={password}']
        process = subprocess.Popen(command)
        auth = 'Basic ' + base64.b64encode(f'{user}:{password}'.encode()).decode()
        core = CoreClient(port, auth)
        scratch_path = Path(scratch)
        config = scratch_path / 'core.json'
        config.write_text(json.dumps({'core': {'url': f'http://127.0.0.1:{port}', 'username': user,
                                              'password_env': 'PG_PROTECTED_TEST_RPC_PASSWORD'}}), encoding='utf-8')

        def holder_cli(action, *arguments, rejected=None):
            run = subprocess.run([sys.executable, '-m', 'proofdesk', f'protected-{action}', '--config',
                                  str(config), *(str(argument) for argument in arguments)], cwd=APP_ROOT,
                                 env=os.environ | {'PG_PROTECTED_TEST_RPC_PASSWORD': password},
                                 capture_output=True, text=True, timeout=30, check=False)
            response = json.loads(run.stdout)
            if rejected is None:
                assert run.returncode == 0, (response, run.stderr)
            else:
                assert run.returncode == 1 and response.get('error') == rejected, (response, run.stderr)
            return response
        try:
            for _ in range(100):
                try:
                    core.rpc('getblockchaininfo', [])
                    break
                except (CoreRPCError, OSError):
                    if process.poll() is not None:
                        raise RuntimeError('Bitcoin Core exited while starting')
                    time.sleep(0.1)
            else:
                raise RuntimeError('Bitcoin Core did not start')
            print(json.dumps(demo(core, lambda name: CoreClient(port, auth, f'/wallet/{name}'),
                                  scratch_path, holder_cli), indent=2))
        finally:
            if process.poll() is None:
                try:
                    core.rpc('stop', [])
                    process.wait(timeout=10)
                except (CoreRPCError, OSError, subprocess.TimeoutExpired):
                    process.kill()
                    process.wait()


if __name__ == '__main__':
    main()
