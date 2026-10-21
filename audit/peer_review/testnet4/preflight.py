"""Read-only gate before the bounded four-peer testnet4 funding cycle.

Run in the environment containing the trusted CLI command prefixes and binary
paths supplied in a private local configuration. No mutating RPC is exposed.
An eligible result is preparation evidence, never an executed experiment.
"""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

GENESIS = '00000000da84f2bafbbc53dee25a72ae507ff4914b867c565be350b0da8bf043'
CAP_SAT = 1_000_000
CHANNEL_SAT = 100_000
NODES = ('a', 'b', 'c', 'd')
EDGES = {frozenset(e) for e in [('a', 'b'), ('a', 'c'), ('b', 'd'), ('c', 'd')]}
CORE_READS = {'getblockchaininfo', 'getblockhash', 'getnetworkinfo', 'getmempoolinfo',
              'getwalletinfo', 'getbalances', 'listunspent', 'listlockunspent'}
CLN_READS = {'getinfo', 'listfunds', 'listpeerchannels', 'listpeers'}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def integer(value):
    require(type(value) is int and value >= 0, 'nonnegative integer required')
    return value


def btc_sat(value):
    # JSON decimal tokens are parsed as Decimal before any binary float conversion.
    require(isinstance(value, (str, Decimal, int)) and not isinstance(value, bool), 'exact BTC token required')
    if isinstance(value, str):
        require(re.fullmatch(r'[0-9]+(?:\.[0-9]{1,8})?', value) is not None, 'plain BTC decimal required')
    amount = Decimal(value) * 100_000_000
    require(amount.is_finite() and amount >= 0 and amount == amount.to_integral_value(), 'whole satoshi BTC amount required')
    return int(amount)


def json_safe(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return value


class ReadonlyCLI:
    def __init__(self, endpoints):
        self.endpoints = endpoints
        self.observations = []

    def __call__(self, node, method, *args):
        require(method in (CORE_READS if node == 'core' else CLN_READS), 'mutating or unknown RPC refused')
        prefix = self.endpoints[node]['cli']
        require(isinstance(prefix, list) and prefix and all(isinstance(x, str) and x for x in prefix), 'CLI argv required')
        started = time.monotonic_ns()
        try:
            result = subprocess.run([*prefix, method, *map(str, args)], capture_output=True, text=True, timeout=20, check=False)
        except (OSError, subprocess.TimeoutExpired):
            # Never expose argv, stdout or stderr, which can contain credentials.
            raise ValueError(f'{node}/{method}: CLI unavailable or timed out') from None
        require(result.returncode == 0, f'{node}/{method}: RPC failed (details withheld)')
        try:
            # bitcoin-cli prints scalar string results without JSON quotes.
            raw = result.stdout.strip()
            value = raw if method == 'getblockhash' and re.fullmatch(r'[0-9a-f]{64}', raw) else json.loads(raw, parse_float=Decimal)
        except (json.JSONDecodeError, ValueError):
            raise ValueError(f'{node}/{method}: invalid JSON response') from None
        public = value
        if node == 'core' and method == 'listunspent':
            # Core includes wallet descriptors and parent xpubs in this response.
            # The gate needs outpoints/value/spendability, not derivation material.
            fields = {'txid', 'vout', 'address', 'amount', 'confirmations', 'spendable', 'safe', 'solvable', 'reused'}
            public = [{k: v for k, v in row.items() if k in fields} for row in value]
        self.observations.append({'node': node, 'method': method,
            'monotonic_start_ns': str(started), 'monotonic_end_ns': str(time.monotonic_ns()), 'result': json_safe(public)})
        return value


def verify_pins(endpoints):
    pins = {}
    for name, endpoint in endpoints.items():
        pin = endpoint['pin']
        require(re.fullmatch(r'[0-9a-f]{40}', pin['source_revision']) is not None, f'{name}: source revision required')
        require(re.fullmatch(r'[0-9a-f]{64}', pin['sha256']) is not None, f'{name}: executable SHA-256 required')
        try:
            with Path(pin['binary_path']).open('rb') as binary:
                actual = hashlib.file_digest(binary, 'sha256').hexdigest()
        except OSError:
            raise ValueError(f'{name}: executable unreadable') from None
        require(actual == pin['sha256'], f'{name}: executable digest mismatch')
        require(isinstance(pin['rpc_version'], str) and pin['rpc_version'], f'{name}: exact RPC version required')
        # Local path and command prefixes are intentionally not published.
        pins[name] = {k: pin[k] for k in ['source_revision', 'sha256', 'rpc_version']}
    return pins


def inspect(config, rpc, pins):
    require(set(config['endpoints']) == {'core', *NODES}, 'one Core and four named CLN endpoints required')
    require(set(pins) == set(config['endpoints']), 'all executable pins required')
    require(config.get('dedicated_wallet') is True, 'dedicated test wallet declaration required')
    reserve = integer(config['fee_reserve_sat'])
    require(0 < reserve <= CAP_SAT - 4 * CHANNEL_SAT, 'fee reserve outside experiment cap')
    chain = rpc('core', 'getblockchaininfo')
    require(chain['chain'] == 'testnet4', 'Core is not on testnet4')
    genesis = rpc('core', 'getblockhash', 0)
    require(genesis == GENESIS, 'testnet4 genesis mismatch')
    height = integer(chain['blocks'])
    require(height > 0 and chain['initialblockdownload'] is False and chain['headers'] == height, 'Core not synchronized')
    network = rpc('core', 'getnetworkinfo')
    require(network['subversion'] == pins['core']['rpc_version'], 'Core RPC version mismatch')
    require(network['networkactive'] is True and network['connections'] > 0, 'Core has no active network peers')
    mempool = rpc('core', 'getmempoolinfo')
    wallet = rpc('core', 'getwalletinfo')
    require(wallet['walletname'] == config['wallet_name'], 'wrong dedicated wallet selected')
    require(wallet['private_keys_enabled'] is True and wallet.get('scanning') is False, 'wallet cannot sign or is still scanning')
    require(not rpc('core', 'listlockunspent'), 'wallet has existing locked inputs')
    balances = rpc('core', 'getbalances')
    require(not balances.get('watchonly'), 'watch-only balances need a separate boundary')
    mine = balances['mine']
    require(btc_sat(mine['untrusted_pending']) == 0 and btc_sat(mine['immature']) == 0, 'wallet has pending or immature funds')
    utxos = rpc('core', 'listunspent', 0)
    seen = set()
    for u in utxos:
        outpoint = (u['txid'], integer(u['vout']))
        require(outpoint not in seen, 'duplicate wallet outpoint'); seen.add(outpoint)
        require(u['confirmations'] > 0 and u['spendable'] is True and u['safe'] is True, 'wallet input not confirmed and spendable')
    funding = sum(btc_sat(u['amount']) for u in utxos)
    require(funding == btc_sat(mine['trusted']), 'wallet balance/UTXO mismatch')
    require(4 * CHANNEL_SAT + reserve <= funding <= CAP_SAT, 'dedicated funding outside declared budget')
    node_info, peers = {}, {}
    for name in NODES:
        info = rpc(name, 'getinfo')
        require(info['network'] == 'testnet4' and info['blockheight'] == height, f'{name}: wrong network or unsynchronized height')
        require(not info.get('warning_bitcoind_sync') and not info.get('warning_lightningd_sync'), f'{name}: sync warning')
        require(info['version'] == pins[name]['rpc_version'], f'{name}: CLN RPC version mismatch')
        require(re.fullmatch(r'(02|03)[0-9a-f]{64}', info['id']) is not None, f'{name}: invalid node ID')
        require(all(info[k] == 0 for k in ['num_pending_channels', 'num_active_channels', 'num_inactive_channels']), f'{name}: pre-existing channel history')
        funds = rpc(name, 'listfunds')
        require(funds['outputs'] == [] and funds['channels'] == [], f'{name}: use an unfunded dedicated CLN wallet')
        require(rpc(name, 'listpeerchannels')['channels'] == [], f'{name}: pre-existing channel')
        peers[name] = rpc(name, 'listpeers')['peers']; node_info[name] = info
    ids = {info['id']: name for name, info in node_info.items()}
    require(len(ids) == 4, 'four distinct controlled node identities required')
    for name in NODES:
        actual = set()
        for peer in peers[name]:
            require(peer['id'] in ids and peer['connected'] is True, f'{name}: uncontrolled or disconnected peer')
            require(peer['id'] not in actual, f'{name}: duplicate peer'); actual.add(peer['id'])
        expected = {node_info[next(iter(edge - {name}))]['id'] for edge in EDGES if name in edge}
        require(actual == expected, f'{name}: connections are not the declared diamond')
    after = rpc('core', 'getblockchaininfo')
    require(after['bestblockhash'] == chain['bestblockhash'] and after['blocks'] == height, 'chain changed during sequential preflight')
    require(after['chain'] == 'testnet4' and after['initialblockdownload'] is False and after['headers'] == height, 'Core lost synchronization')
    return {'status': 'eligible_for_funding_cycle', 'evidence_class': 'testnet4_preflight_only',
        'genesis': genesis, 'height': height, 'best_block_hash': chain['bestblockhash'],
        'funding_sat': funding, 'fee_reserve_sat': reserve, 'funding_cap_sat': CAP_SAT,
        'channel_count': 4, 'channel_value_sat': CHANNEL_SAT, 'payment_count': 200,
        'invoice_values_sat': [1000, 2000], 'hard_stop_seconds': 48 * 3600,
        'node_ids': {name: info['id'] for name, info in node_info.items()}, 'software_pins': pins,
        'mempool': json_safe(mempool), 'transaction_broadcast': False,
        'limits': ['CLI prefixes, binary-to-daemon association and source-to-binary provenance are operator-attested trust boundaries.',
                   'Sync is node-reported and tip-bracketed, not a cross-service atomic snapshot or independent public-chain oracle.',
                   'No channel activation, route attempt, fee, HTLC duration or payment result has been measured by this preflight.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path); parser.add_argument('output', type=Path)
    args = parser.parse_args()
    # Never overwrite a prior observation or action result.
    with args.output.open('x', encoding='utf8') as out:
        observations = []
        try:
            config = json.loads(args.config.read_text(encoding='utf8'))
            require(set(config['endpoints']) == {'core', *NODES}, 'one Core and four named CLN endpoints required')
            pins = verify_pins(config['endpoints'])
            rpc = ReadonlyCLI(config['endpoints']); observations = rpc.observations
            report = inspect(config, rpc, pins)
        except ValueError as error:
            report = {'status': 'not_ready', 'reason': str(error), 'transaction_broadcast': False}
        except (KeyError, TypeError, OSError):
            report = {'status': 'not_ready', 'reason': 'missing or malformed local configuration/response', 'transaction_broadcast': False}
        report['checked_at_unix_ns'] = str(time.time_ns())
        report['observations'] = observations
        out.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'transaction_broadcast': False}))
    return 0 if report['status'] == 'eligible_for_funding_cycle' else 2


if __name__ == '__main__':
    raise SystemExit(main())
