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
import secrets
import socket
import subprocess
import tempfile
from threading import Barrier
import time

SATOSHIS = 100_000_000
RESERVE = 25_000
FEE = 250
DELAY = 6
ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
HOLDER_PUB = '0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798'
MINT_PUB = '02c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5'


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


def fixture_wif(scalar: int) -> str:
    key = b'\xef' + scalar.to_bytes(32, 'big') + b'\x01'
    checksum = hashlib.sha256(hashlib.sha256(key).digest()).digest()[:4]
    number = int.from_bytes(key + checksum, 'big')
    encoded = ''
    while number:
        number, remainder = divmod(number, 58)
        encoded = ALPHABET[remainder] + encoded
    return encoded


def descriptor(holder: str, mint: str) -> str:
    return f'wsh(and_v(v:pk({holder}),or_i(pk({mint}),older({DELAY}))))'


def checked_descriptor(core: CoreClient, expression: str) -> str:
    return f'{expression}#{core.rpc("getdescriptorinfo", [expression])["checksum"]}'


def accept(core: CoreClient, tx: str) -> dict:
    return core.rpc('testmempoolaccept', [[tx]])[0]


def assert_refused(result: dict) -> str:
    assert result['allowed'] is False, result
    return result['reject-reason']


def demo(core: CoreClient, wallet) -> dict:
    chain = core.rpc('getblockchaininfo', [])
    assert chain['chain'] == 'regtest' and chain['blocks'] == 0
    for name in ('funding', 'holder', 'mint'):
        core.rpc('createwallet', [name, False, name != 'funding'])
    funding, holder, mint = (wallet(name) for name in ('funding', 'holder', 'mint'))

    # Each signer knows the complete policy and holds exactly its own key.
    public = checked_descriptor(core, descriptor(HOLDER_PUB, MINT_PUB))
    for signer, keys in ((holder, (fixture_wif(1), MINT_PUB)),
                         (mint, (HOLDER_PUB, fixture_wif(2)))):
        private = checked_descriptor(core, descriptor(*keys))
        result = signer.rpc('importdescriptors', [[{'desc': private, 'timestamp': 0}]])
        assert result[0]['success'], result

    mining_address = funding.rpc('getnewaddress', [])
    for count in (25, 25, 25, 26):
        core.rpc('generatetoaddress', [count, mining_address])
    reserve_address = core.rpc('deriveaddresses', [public])[0]
    txid = funding.rpc('sendtoaddress', [reserve_address, RESERVE / SATOSHIS])
    funding_block = core.rpc('generatetoaddress', [1, mining_address])[0]
    original = core.rpc('getrawtransaction', [txid, True, funding_block])
    output = next(row for row in original['vout'] if row['scriptPubKey'].get('address') == reserve_address)
    vout = output['n']
    assert round(output['value'] * SATOSHIS) == RESERVE
    assert core.rpc('gettxout', [txid, vout, False])['confirmations'] == 1

    payout_address = funding.rpc('getnewaddress', [])
    cooperative_address = funding.rpc('getnewaddress', [])
    substituted_address = funding.rpc('getnewaddress', [])

    def psbt(sequence: int, destination: str) -> str:
        return core.rpc('createpsbt', [[{'txid': txid, 'vout': vout, 'sequence': sequence}],
                                       [{destination: (RESERVE - FEE) / SATOSHIS}], 0, False])

    coop_unsigned = psbt(0xfffffffd, cooperative_address)
    mint_partial = mint.rpc('walletprocesspsbt', [coop_unsigned, True, 'ALL', True, False])['psbt']
    holder_partial = holder.rpc('walletprocesspsbt', [coop_unsigned, True, 'ALL', True, False])['psbt']
    assert not core.rpc('finalizepsbt', [mint_partial])['complete']
    assert not core.rpc('finalizepsbt', [holder_partial])['complete']
    combined = core.rpc('combinepsbt', [[mint_partial, holder_partial]])
    cooperative_tx = core.rpc('finalizepsbt', [combined])['hex']
    assert accept(core, cooperative_tx)['allowed']

    # Model refusal from this point onward by removing the mint's signing wallet.
    mint.rpc('unloadwallet', [])
    emergency = holder.rpc('walletprocesspsbt', [psbt(DELAY, payout_address), True, 'ALL'])
    assert emergency['complete'], emergency
    emergency_tx = emergency['hex']
    early = assert_refused(accept(core, emergency_tx))
    assert early == 'non-BIP68-final', early
    core.rpc('generatetoaddress', [DELAY - 1, mining_address])
    assert accept(core, emergency_tx)['allowed']
    assert accept(core, cooperative_tx)['allowed']

    decoded = core.rpc('decoderawtransaction', [emergency_tx])
    payout_script = decoded['vout'][0]['scriptPubKey']['hex']
    substitute_script = core.rpc('validateaddress', [substituted_address])['scriptPubKey']
    assert len(payout_script) == len(substitute_script) and emergency_tx.count(payout_script) == 1
    substituted = emergency_tx.replace(payout_script, substitute_script)
    beneficiary = assert_refused(accept(core, substituted))

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
    spend = decoded['txid']
    payout_block = core.rpc('generateblock', [mining_address, [emergency_tx]])['hash']
    expected_height = core.rpc('getblockheader', [funding_block])['height'] + DELAY
    assert core.rpc('getblockhash', [expected_height]) == payout_block
    payout = core.rpc('getrawtransaction', [spend, True, payout_block])
    assert payout['txid'] == decoded['txid'] == spend
    assert payout['vout'][0]['scriptPubKey']['address'] == payout_address
    assert round(payout['vout'][0]['value'] * SATOSHIS) == RESERVE - FEE
    assert core.rpc('gettxout', [txid, vout, False]) is None
    conflict = assert_refused(accept(core, cooperative_tx))
    replay = assert_refused(accept(core, emergency_tx))

    core.rpc('invalidateblock', [payout_block])
    assert core.rpc('getblockheader', [payout_block])['confirmations'] == -1
    assert core.rpc('gettxout', [txid, vout, False]) is not None
    core.rpc('reconsiderblock', [payout_block])
    assert core.rpc('getblockhash', [expected_height]) == payout_block
    assert core.rpc('gettxout', [txid, vout, False]) is None

    core.rpc('invalidateblock', [funding_block])
    assert core.rpc('getblockheader', [funding_block])['confirmations'] == -1
    assert core.rpc('gettxout', [txid, vout, False]) is None
    core.rpc('reconsiderblock', [funding_block])
    assert core.rpc('getblockhash', [expected_height]) == payout_block

    genesis = core.rpc('getblockhash', [0])
    claim_id = hashlib.sha256(b'proof-grove/protected-reserve/v1\0' + bytes.fromhex(genesis)
                              + bytes.fromhex(txid) + vout.to_bytes(4, 'big')).hexdigest()
    return {
        'schema': 'proof-grove/protected-reserve-regtest/v1', 'network': 'regtest',
        'genesis': genesis, 'chain_version': core.rpc('getnetworkinfo', [])['subversion'],
        'claim_id': claim_id, 'reserve_descriptor': public,
        'reserve': {'txid': txid, 'vout': vout, 'sats': RESERVE, 'block': funding_block,
                    'script': output['scriptPubKey']['hex']},
        'payout': {'txid': spend, 'wtxid': payout['hash'], 'block': payout_block,
                   'height': expected_height, 'script': payout_script, 'sats': RESERVE - FEE,
                   'fee_sats': FEE, 'delay_blocks': DELAY},
        'controls': {'early_exit': early, 'substituted_beneficiary': beneficiary,
                     'conflicting_melt': conflict, 'replayed_exit': replay,
                     'single_signer_cannot_cooperate': True, 'mint_signer_unloaded': True,
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
            print(json.dumps(demo(core, lambda name: CoreClient(port, auth, f'/wallet/{name}')), indent=2))
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
