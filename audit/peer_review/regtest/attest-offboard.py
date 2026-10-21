"""Capture the existing exit's ownership, source, chain and forfeit ancestry.

On-chain wallet synchronization updates its local cache, not the chain. All
remaining operations are read-only; no payment or exit is retried.
"""
import hashlib
import json
import sys
from pathlib import Path
from bootstrap import core
from launch import bark
from attest import DEST, save
from observe import snapshot
from pay import action

if core('getblockchaininfo')['chain'] != 'regtest':
    raise RuntimeError('owned regtest required')
action('offboard-onchain-sync', lambda: json.loads(bark('onchain', 'balance').stdout))
after = snapshot('offboard-owned-output')
before = json.loads((DEST / 'offboard-before.json').read_text())
known = {v['txid'] for v in before['database']['virtual_transactions']}
transactions = {}
for row in after['database']['virtual_transactions']:
    if row['txid'] not in known and row['signed_tx']:
        tx = core('decoderawtransaction', row['signed_tx'])
        assert tx['txid'] == row['txid']
        transactions[row['txid']] = {'raw_sha256': hashlib.sha256(bytes.fromhex(row['signed_tx'])).hexdigest(), 'transaction': tx}
headers = [core('getblockheader', core('getblockhash', str(height)))
           for height in range(before['chain_after']['blocks'] + 1, after['chain_after']['blocks'] + 1)]
source = Path(sys.argv[1])
files = ['server/src/offboards.rs', 'server/src/database/mod.rs', 'lib/src/offboard.rs',
         'bark/src/actions/offboard.rs', 'bark-cli/src/bin/bark/main.rs', 'bark-cli/src/bin/bark/onchain.rs']
save('offboard-source-and-chain.json', {
    'source_revision': '8f5d8c4f4afae87c8e4b3c6fb26fe06e9ae50e6a',
    'source_sha256': {f: hashlib.sha256((source / f).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for f in files},
    'genesis': core('getblockhash', '0'), 'headers': headers, 'transactions': transactions,
})
print(json.dumps({'new_decoded_transactions': len(transactions), 'headers': len(headers)}))
