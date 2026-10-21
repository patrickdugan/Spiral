"""Enable the source-pinned upstream hold plugin in the owned regtest fixture.

Run under WSL after verifying/extracting the release into RUNTIME. The binary
is mounted in the existing CLN container; keys remain in RUNTIME. This changes
only the task's runtime, never a system service or the historical identity pin.
"""
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path
from bootstrap import RUNTIME, core, docker
from fund import cln
from launch import rpc
from attest import save, DEST
from pay import action

ARCHIVE_SHA = 'f9d916430fb70a3d75089f2d1b88d5d71d4987ef79933035978c1f44aab84be5'
BINARY_SHA = 'f98cd795e68a214b11fe168cc08690a50837dcefc93be6b885cb69d74ef1c1a4'
SOURCE_COMMIT = 'af0055b132f3b9f24d0b1d478a15005fcf8f014f'


def main():
    archive = Path(sys.argv[1])
    if core('getblockchaininfo')['chain'] != 'regtest':
        raise RuntimeError('owned regtest required')
    if (DEST / 'inbound-plugin-runtime.json').exists():
        raise RuntimeError('already configured; inspect rather than repeat')
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA:
        raise RuntimeError('archive digest mismatch')
    binary = RUNTIME / 'cln-server/hold'
    if hashlib.sha256(binary.read_bytes()).hexdigest() != BINARY_SHA:
        raise RuntimeError('binary digest mismatch')
    if any(c.get('htlcs') for c in cln('server', 'listpeerchannels')['channels']):
        raise RuntimeError('active HTLC; refuse configuration restart')
    action('inbound-plugin-start', lambda: cln('server', 'plugin', 'start', '/data/hold'))
    cert = RUNTIME / 'cln-server/regtest/hold/client-key.pem'
    for _ in range(20):
        if cert.exists():
            break
        time.sleep(1)
    else:
        raise RuntimeError('hold TLS files not ready')
    cfg = RUNTIME / 'config/captaind.toml'
    old = cfg.read_text()
    if '[cln_array.hold_invoice]' in old:
        raise RuntimeError('hold configuration already exists')
    backup = cfg.with_name('captaind.before-inbound.toml')
    if backup.exists():
        raise RuntimeError('existing configuration backup; reconcile previous attempt')
    shutil.copyfile(cfg, backup)
    addition = '''\n[cln_array.hold_invoice]
uri = "https://localhost:9292"
server_cert_path = "/data/cln-server/regtest/hold/ca.pem"
client_cert_path = "/data/cln-server/regtest/hold/client.pem"
client_key_path = "/data/cln-server/regtest/hold/client-key.pem"
'''
    cfg.write_text(old + addition)
    action('inbound-captain-restart', lambda: {'result': docker('restart', 'spiral-captaind').stdout.strip()})
    for _ in range(30):
        result = rpc('wallet', check=False)
        if result.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError('captain not ready; inspect private logs and saved configuration')
    save('inbound-plugin-runtime.json', {
        'evidence_class': 'owned_regtest_runtime_change', 'source_repository': 'https://github.com/BoltzExchange/hold',
        'source_tag': 'v0.3.3', 'source_commit': SOURCE_COMMIT,
        'release_url': 'https://github.com/BoltzExchange/hold/releases/download/v0.3.3/hold-linux-amd64.tar.gz',
        'archive_sha256': ARCHIVE_SHA, 'binary_sha256': BINARY_SHA,
        'activation': 'dynamic plugin in existing pinned CLN container; no CLN restart',
        'endpoint': 'https://localhost:9292', 'bind_host': '127.0.0.1',
        'captain_config_before_sha256': hashlib.sha256(old.encode()).hexdigest(),
        'captain_config_after_sha256': hashlib.sha256(cfg.read_bytes()).hexdigest(),
        'configuration_addition': addition, 'private_keys_exported': False,
        'genesis': core('getblockhash', '0'), 'height': core('getblockcount'),
        'cln_binary_sha256': docker('exec', 'spiral-cln-server', 'sha256sum', '/usr/local/bin/lightningd').stdout.split()[0],
        'hold_invoices': cln('server', 'listholdinvoices'),
    })
    print('Pinned hold plugin enabled; no invoice or payment attempted.')


if __name__ == '__main__':
    main()
