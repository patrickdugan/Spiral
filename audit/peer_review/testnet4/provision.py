"""Provision four empty, isolated testnet4 peers. Never funds or pays.

Run in WSL with a trusted private JSON configuration containing windows_cli
(WSL path), windows_datadir (Windows path), and core_binary (WSL path).
Core must already be synchronized. Existing wallets/containers are preserved.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
RUNTIME = Path('/var/tmp/spiral-testnet4-runtime')
DOCKER = ['/var/tmp/spiral-capital-runtime/bin/docker', '-H', 'unix:///var/tmp/spiral-capital-runtime/docker.sock']
IMAGE = 'elementsproject/lightningd@sha256:0421a5f0d1b2e1ad639edfa17d777816040e3850d91bae7f2d32186d9c1e6da4'
CLN_SOURCE = '8684c68dffb04ab606e526b64d7d60390d1fe7ed'
CLN_SHA = 'cf814f01f69b857ec1cfb48a907b78d33179c803b6e5f3cff50fbf495d4a38a2'
CORE_SOURCE = '9be056a8a72b624dae9623b2f7bded92c2a21c91'
CORE_SHA = 'f79eeb94e1379986df9f7be4c78c8fc8e18dc9be64a31cbaa8acad249d3db77a'
LINUX_CLI_SHA = '3e92883f97850bc445ac033d26d55902dcb035fdf64f78c2c03c83216f083c5d'
GENESIS = '00000000da84f2bafbbc53dee25a72ae507ff4914b867c565be350b0da8bf043'


def docker(*args, check=True):
    return subprocess.run([*DOCKER, *map(str, args)], capture_output=True, text=True, check=check, timeout=30)


def cln(node, method, *args):
    return json.loads(docker('exec', 'spiral-t4-' + node, 'lightning-cli', '--network=testnet4',
        '--lightning-dir=/data', '--json', '--notifications=none', method, *args).stdout)


def bridge_call(config, method, *args):
    auth = base64.b64encode((config['user'] + ':' + config['password']).encode()).decode()
    request = urllib.request.Request('http://127.0.0.1:' + str(config['port']),
        json.dumps({'id': 1, 'method': method, 'params': list(args)}).encode(),
        {'Authorization': 'Basic ' + auth, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=50) as response:
        result = json.load(response)
    if result['error']:
        raise RuntimeError(result['error']['message'])
    return result['result']


def main():
    os.umask(0o077)
    private = json.loads(Path(sys.argv[1]).read_text())
    if shutil.disk_usage('/mnt/c').free < 4 * 1024**3:
        raise RuntimeError('insufficient host disk space')
    if hashlib.sha256(Path(private['core_binary']).read_bytes()).hexdigest() != CORE_SHA:
        raise RuntimeError('Core executable digest mismatch')
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    bridge_path = RUNTIME / 'bridge.json'
    if not bridge_path.exists():
        with bridge_path.open('x') as out:
            json.dump({'cli': private['windows_cli'], 'datadir': private['windows_datadir'],
                'port': 48333, 'user': 'spiral-testnet4', 'password': secrets.token_hex(32),
                'allow_broadcast': False}, out)
    config = json.loads(bridge_path.read_text())
    try:
        chain = bridge_call(config, 'getblockchaininfo')
    except urllib.error.URLError as error:
        if not isinstance(error.reason, ConnectionRefusedError):
            raise
        with (RUNTIME / 'bridge.log').open('ab') as log:
            process = subprocess.Popen([sys.executable, str(HERE / 'interop_rpc.py'), str(bridge_path)],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        (RUNTIME / 'bridge.pid').write_text(str(process.pid))
        for _ in range(20):
            time.sleep(0.25)
            try:
                chain = bridge_call(config, 'getblockchaininfo'); break
            except urllib.error.URLError:
                continue
        else:
            raise RuntimeError('bridge did not start; inspect private log')
    if chain['chain'] != 'testnet4' or chain['initialblockdownload'] or chain['blocks'] != chain['headers']:
        raise RuntimeError('Core is not synchronized testnet4')
    if bridge_call(config, 'getblockhash', 0) != GENESIS:
        raise RuntimeError('wrong genesis')
    backend_cli = RUNTIME / 'backend-bitcoin-cli'
    if not backend_cli.exists():
        docker('cp', 'spiral-bitcoin:/opt/bitcoin-31.0/bin/bitcoin-cli', backend_cli)
    if hashlib.sha256(backend_cli.read_bytes()).hexdigest() != LINUX_CLI_SHA:
        raise RuntimeError('Linux Core CLI digest mismatch')
    manifest = {'evidence_class': 'empty_testnet4_peer_provisioning', 'genesis': GENESIS,
        'core_source_revision': CORE_SOURCE, 'core_binary_sha256': CORE_SHA,
        'cln_source_revision': CLN_SOURCE, 'cln_binary_sha256': CLN_SHA, 'cln_image': IMAGE,
        'backend_cli_version': 'v31.0.0', 'backend_cli_sha256': LINUX_CLI_SHA,
        'backend_cli_source_revision': '6574cb40869b96b9ffc79c19dc8f4e467d60f321',
        'backend_cli_source_image': 'bitcoin/bitcoin@sha256:a1d05be6939b5c85132a761d2b795f5b8a2612ce53782263da4939778e461792',
        'bridge_broadcast_enabled': config['allow_broadcast'], 'nodes': {},
        'transaction_broadcast': False, 'monotonic_start_ns': str(time.monotonic_ns())}
    for i, node in enumerate('abcd'):
        directory = RUNTIME / ('cln-' + node)
        directory.mkdir(mode=0o700, exist_ok=True)
        local_cli = directory / 'backend-bitcoin-cli'
        if not local_cli.exists():
            shutil.copy2(backend_cli, local_cli)
        if hashlib.sha256(local_cli.read_bytes()).hexdigest() != LINUX_CLI_SHA:
            raise RuntimeError('peer backend CLI digest mismatch')
        port = 21935 + i * 1000
        options = ['network=testnet4', 'alias=spiral-clock-' + node,
            f'bind-addr=127.0.0.1:{port}', 'autolisten=false', 'announce-addr-discovered=false',
            'disable-dns', 'autoconnect-seeker-peers=0', f'grpc-port={port+1}', 'grpc-host=127.0.0.1',
            'bitcoin-cli=/data/backend-bitcoin-cli', 'bitcoin-rpcconnect=127.0.0.1', f'bitcoin-rpcport={config["port"]}',
            'bitcoin-rpcuser=' + config['user'], 'bitcoin-rpcpassword=' + config['password'],
            'funding-confirms=3', 'log-level=info', 'log-file=/data/daemon.log']
        conf = directory / 'config'
        expected = '\n'.join(options) + '\n'
        if conf.exists() and conf.read_text() != expected:
            raise RuntimeError('existing peer configuration differs; inspect before changing')
        if not conf.exists():
            with conf.open('x') as out:
                out.write(expected)
        name = 'spiral-t4-' + node
        existing = docker('inspect', name, check=False)
        if existing.returncode:
            docker('run', '-d', '--name', name, '--network', 'host', '--memory', '512m', '--cpus', '1',
                '-v', str(directory) + ':/data', '--entrypoint', 'lightningd', IMAGE,
                '--conf=/data/config', '--lightning-dir=/data', '--network=testnet4')
        else:
            inspected = json.loads(existing.stdout)[0]
            if not inspected['State']['Running'] or inspected['Config']['Image'] != IMAGE:
                raise RuntimeError('existing container stopped or wrong image; inspect before restarting')
            mounts = {(m['Source'], m['Destination']) for m in inspected['Mounts'] if m['Type'] == 'bind'}
            defaults = [m for m in inspected['Mounts'] if m['Type'] != 'bind']
            if mounts != {(str(directory), '/data')} or inspected['HostConfig']['NetworkMode'] != 'host':
                raise RuntimeError('existing container is not the expected private runtime')
            if any(m['Type'] != 'volume' or m['Destination'] != '/root/.lightning' for m in defaults):
                raise RuntimeError('unexpected additional container mount')
            if inspected['Config']['Cmd'] != ['--conf=/data/config', '--lightning-dir=/data', '--network=testnet4']:
                raise RuntimeError('existing container arguments differ; inspect before reusing')
        info = None
        for _ in range(30):
            try:
                info = cln(node, 'getinfo'); break
            except subprocess.CalledProcessError:
                time.sleep(0.5)
        if info is None:
            raise RuntimeError(f'peer {node} RPC did not become ready; inspect private logs')
        actual = docker('exec', name, 'sha256sum', '/usr/local/bin/lightningd').stdout.split()[0]
        if actual != CLN_SHA:
            raise RuntimeError('CLN executable digest mismatch')
        manifest['nodes'][node] = {'getinfo': info, 'public_configuration':
            [v for v in options if not v.startswith('bitcoin-rpcpassword=')],
            'binary_sha256': actual}
    for left, right in [('a', 'b'), ('a', 'c'), ('b', 'd'), ('c', 'd')]:
        cln(left, 'connect', manifest['nodes'][right]['getinfo']['id'], '127.0.0.1', str(21935 + 'abcd'.index(right)*1000))
    for node in 'abcd':
        manifest['nodes'][node].update({method: cln(node, method) for method in ['getinfo', 'listpeers', 'listfunds', 'listpeerchannels']})
    binary = RUNTIME / 'lightningd-pin'
    if not binary.exists():
        temporary = RUNTIME / 'lightningd-pin.new'
        if temporary.exists():
            raise RuntimeError('unfinished binary copy; inspect before retrying')
        docker('cp', '-L', 'spiral-t4-a:/usr/local/bin/lightningd', temporary)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != CLN_SHA:
            raise RuntimeError('copied CLN executable digest mismatch')
        temporary.replace(binary)
    endpoints = {'core': {'cli': [private['windows_cli'], '-datadir=' + private['windows_datadir'],
        '-testnet4', '-rpcwallet=spiral-capital-clock-20261021'], 'pin': {'binary_path': private['core_binary'],
        'source_revision': CORE_SOURCE, 'sha256': CORE_SHA, 'rpc_version': '/Satoshi:31.1.0/'}}}
    for node in 'abcd':
        endpoints[node] = {'cli': [*DOCKER, 'exec', 'spiral-t4-' + node, 'lightning-cli',
            '--network=testnet4', '--lightning-dir=/data', '--json', '--notifications=none'],
            'pin': {'binary_path': str(binary), 'source_revision': CLN_SOURCE, 'sha256': CLN_SHA, 'rpc_version': 'v26.06.7'}}
    local_config = {'dedicated_wallet': True, 'wallet_name': 'spiral-capital-clock-20261021',
        'fee_reserve_sat': 100000, 'endpoints': endpoints}
    path = RUNTIME / 'preflight-config.json'
    if path.exists() and json.loads(path.read_text()) != local_config:
        raise RuntimeError('existing preflight configuration differs')
    if not path.exists():
        with path.open('x') as out:
            json.dump(local_config, out, indent=2)
    manifest['monotonic_end_ns'] = str(time.monotonic_ns())
    manifest['observed_at_unix_ns'] = str(time.time_ns())
    with (RUNTIME / ('provisioning-' + str(time.time_ns()) + '.json')).open('x') as out:
        json.dump(manifest, out, indent=2)
    print(json.dumps({'status': 'peers_provisioned', 'height': chain['blocks'],
        'node_ids': {n: manifest['nodes'][n]['getinfo']['id'] for n in 'abcd'}, 'transaction_broadcast': False}))


if __name__ == '__main__':
    main()
