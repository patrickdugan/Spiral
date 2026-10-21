"""Read-only source, chain and virtual-transaction pins for the inbound branch."""
import hashlib
import json
import sys
from pathlib import Path
from bootstrap import core, docker, RUNTIME
from attest import DEST, save

before = json.loads((DEST / 'inbound-pool-before.json').read_text())
after = json.loads((DEST / 'inbound-settled.json').read_text())
known = {v['txid'] for v in before['database']['virtual_transactions']}
decoded = {}
for row in after['database']['virtual_transactions']:
    if row['txid'] not in known and row['signed_tx']:
        tx = core('decoderawtransaction', row['signed_tx'])
        assert tx['txid'] == row['txid']
        decoded[row['txid']] = {'raw_sha256': hashlib.sha256(bytes.fromhex(row['signed_tx'])).hexdigest(), 'transaction': tx}
headers = []
for height in range(before['chain_after']['blocks'] + 1, after['chain_after']['blocks'] + 1):
    headers.append(core('getblockheader', core('getblockhash', str(height))))
diagnostics = []
logs = docker('logs', '--since', '2026-10-21T13:35:00Z', 'spiral-captaind')
for line in (logs.stdout + logs.stderr).splitlines():
    try:
        entry = json.loads(line)
    except json.JSONDecodeError:
        continue
    if entry.get('message', '').startswith('Dropping vtxo pool change '):
        diagnostics.append({k: entry[k] for k in ['timestamp', 'filename', 'line_number', 'message']})
source = Path(sys.argv[1]); hold = Path(sys.argv[2])
files = ['server/src/ln/mod.rs', 'server/src/ln/cln/hold.rs', 'server/src/ln/node_manager.rs',
         'server/src/vtxopool.rs', 'bark/src/actions/lightning/receive.rs', 'bark-cli/src/bin/bark/lightning.rs']
save('inbound-source-and-chain.json', {
    'source_revision': '8f5d8c4f4afae87c8e4b3c6fb26fe06e9ae50e6a',
    'source_sha256': {f: hashlib.sha256((source / f).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for f in files},
    'hold_revision': 'af0055b132f3b9f24d0b1d478a15005fcf8f014f',
    'hold_source_sha256': {f: hashlib.sha256((hold / f).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for f in ['src/main.rs', 'src/config.rs', 'src/grpc/tls.rs']},
    'genesis': core('getblockhash', '0'), 'headers': headers, 'transactions': decoded,
    'pool_change_diagnostics': diagnostics,
    'current_config_sha256': hashlib.sha256((RUNTIME / 'config/captaind.toml').read_bytes()).hexdigest(),
})
print(json.dumps({'headers': len(headers), 'new_decoded_transactions': len(decoded)}))
