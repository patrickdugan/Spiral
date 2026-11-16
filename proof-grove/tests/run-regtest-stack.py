"""Run one isolated Core/CDK stack and the real issuance test, then stop only it.

Run on Linux/WSL with Docker, official CDK 0.18.3 and Node 24 binaries. The
foreground supervisor keeps WSL alive; no user wallets or existing containers
are selected. Mint seeds, RPC password and wallet passphrase are public fixtures.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT=Path(__file__).resolve().parent.parent
IMAGE='bitcoin/bitcoin@sha256:68b927b6a2d3b019ce7655f3fd0eb9a4c7011310886ebc7890e5246c16df5ec6'
CDK_SHA256='3a41003fcac0f54a164b6d9187c79ce05591947bb4b4b37c45a125fac813e3af'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--cdk',required=True);parser.add_argument('--node',required=True)
args=parser.parse_args()
if sys.platform!='linux':raise SystemExit('Run this foreground supervisor on Linux or inside WSL.')
cdk,node=Path(args.cdk).resolve(),Path(args.node).resolve()
if hashlib.sha256(cdk.read_bytes()).hexdigest()!=CDK_SHA256:raise SystemExit('CDK binary does not match the pinned official 0.18.3 release.')
major=int(subprocess.check_output([str(node),'--version'],text=True).strip().lstrip('v').split('.')[0])
if major<24:raise SystemExit('Node 24 or newer is required.')
def run(*command):return subprocess.run(command,check=True,text=True,capture_output=True).stdout.strip()
def port():
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));return sock.getsockname()[1]
def wait_url(url,body=None,headers=None,process=None):
    for _ in range(60):
        if process and process.poll() is not None:raise RuntimeError('The test mint exited; inspect its runtime log.')
        try:return json.load(urllib.request.urlopen(urllib.request.Request(url,data=body,headers=headers or {}),timeout=2))
        except OSError:time.sleep(1)
    raise RuntimeError('An existing test process did not become ready; inspect it before any restart.')

(ROOT/'.runtime').mkdir(exist_ok=True)
runtime=Path(tempfile.mkdtemp(prefix='regtest-stack-',dir=ROOT/'.runtime'))
token=secrets.token_hex(6);name='proof-grove-'+token;volume=name+'-core'
rpc_port,mint_port=port(),port()
while rpc_port==mint_port:mint_port=port()
process=None;volume_created=False;container_created=False
environment=os.environ|{'PG_TEST_MINT_MNEMONIC':'abandon '*11+'about',
                       'PG_TEST_BDK_MNEMONIC':'legal winner thank year wave sausage worth useful legal winner thank yellow',
                       'PG_TEST_RPC_PASSWORD':'public-regtest-only'}
try:
    run('docker','volume','create','--label','proof-grove.run='+token,volume);volume_created=True
    run('docker','run','--detach','--name',name,'--label','proof-grove.run='+token,
        '--publish',f'127.0.0.1:{rpc_port}:18443','--mount',f'type=volume,src={volume},dst=/home/bitcoin/.bitcoin',IMAGE,
        'bitcoind','-regtest','-server','-txindex=1','-blockfilterindex=1','-listen=0','-connect=0','-dnsseed=0','-discover=0',
        '-fallbackfee=0.00001','-rpcbind=0.0.0.0','-rpcallowip=0.0.0.0/0','-rpcuser=proofgrove','-rpcpassword=public-regtest-only')
    container_created=True
    rpc_url=f'http://127.0.0.1:{rpc_port}'
    info=wait_url(rpc_url,json.dumps({'jsonrpc':'2.0','id':'pg','method':'getblockchaininfo','params':[]}).encode(),
                  {'Content-Type':'application/json','Authorization':'Basic '+base64.b64encode(b'proofgrove:public-regtest-only').decode()})
    if info['result']['chain']!='regtest':raise RuntimeError('Unexpected network')
    config=runtime/'config.toml'
    config.write_text(f'''[info]
url="http://127.0.0.1:{mint_port}"
listen_host="127.0.0.1"
listen_port={mint_port}
mnemonic="env:PG_TEST_MINT_MNEMONIC"
[info.quote_ttl]
mint_ttl=86400
melt_ttl=600
[info.logging]
output="stderr"
console_level="error"
[database]
engine="sqlite"
[payment_backend]
backend="none"
[onchain]
onchain_backend="bdk"
min_mint=1000
max_mint=1000000
[bdk]
mnemonic="env:PG_TEST_BDK_MNEMONIC"
network="regtest"
num_confs=2
min_receive_amount_sat=1000
min_send_amount_sat=546
chain_source_type="bitcoinrpc"
bitcoind_rpc_host="127.0.0.1"
bitcoind_rpc_port={rpc_port}
bitcoind_rpc_user="proofgrove"
bitcoind_rpc_password="env:PG_TEST_RPC_PASSWORD"
''')
    with (runtime/'bootstrap.log').open('ab') as logfile:
        subprocess.run([str(cdk),'--work-dir',str(runtime),'config','init','--new-mint','--file',str(config)],env=environment,stdout=logfile,stderr=logfile,check=True)
    with (runtime/'mintd.log').open('ab') as logfile:
        process=subprocess.Popen([str(cdk),'--work-dir',str(runtime)],env=environment,stdout=logfile,stderr=logfile)
    mint_url=f'http://127.0.0.1:{mint_port}'
    wait_url(mint_url+'/v1/info',process=process)
    subprocess.run([sys.executable,str(ROOT/'tests/cdk-regtest-integration.py'),'--node',str(node),'--mint',mint_url,'--rpc',rpc_url],cwd=ROOT,env=environment,check=True)
finally:
    if process and process.poll() is None:
        process.terminate()
        try:process.wait(timeout=20)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
    if container_created:
        record=json.loads(run('docker','inspect',name))[0]
        if record['Config']['Labels'].get('proof-grove.run')!=token:raise RuntimeError('Refusing cleanup: container owner changed')
        if record['State']['Running']:run('docker','stop','--time','15',name)
        run('docker','rm',name)
    if volume_created:
        record=json.loads(run('docker','volume','inspect',volume))[0]
        if record.get('Labels',{}).get('proof-grove.run')!=token:raise RuntimeError('Refusing cleanup: volume owner changed')
        run('docker','volume','rm',volume)
