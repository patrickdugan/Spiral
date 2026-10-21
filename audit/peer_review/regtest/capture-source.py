"""Capture exact Git blobs for the source revision reported by the live binaries."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

source = Path(sys.argv[1])
revision = '8f5d8c4f4afae87c8e4b3c6fb26fe06e9ae50e6a'
assert subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() == revision
files = ['server/schema.sql', 'server/src/ln/mod.rs', 'server/src/ln/cln/xpay.rs',
         'server/src/database/ln/model.rs', 'server/src/watchman/policy.rs', 'server/src/watchman/mod.rs',
         'server/src/sync/block_index.rs', 'server/src/bitcoind.rs', 'server/src/wallet/mod.rs',
         'server/captaind.default.toml', 'server/watchmand.default.toml',
         'server-log/src/msgs/watchman.rs', 'bark-cli/src/bin/bark/main.rs']
records = []
for path in files:
    raw = subprocess.check_output(['git', '-C', str(source), 'show', f'{revision}:{path}'])
    blob = subprocess.check_output(['git', '-C', str(source), 'rev-parse', f'{revision}:{path}'], text=True).strip()
    records.append({'path': path, 'git_blob': blob, 'sha256': hashlib.sha256(raw).hexdigest(),
                    'url': f'https://gitlab.com/ark-bitcoin/bark/-/blob/{revision}/{path}'})
result = {'revision': revision, 'evidence_class': 'source-inspection',
          'relationship': 'Matches binary-reported build commit; not a reproducible-build attestation.', 'files': records,
          'bitcoin_release_source': 'https://github.com/bitcoin/bitcoin/commit/6574cb40869b96b9ffc79c19dc8f4e467d60f321',
          'cln_release_source': 'https://github.com/ElementsProject/lightning/commit/8684c68dffb04ab606e526b64d7d60390d1fe7ed'}
(Path(__file__).parent / 'evidence/runtime-source.json').write_text(json.dumps(result, indent=2) + '\n', newline='\n')
