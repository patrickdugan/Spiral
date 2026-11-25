"""Run one isolated Core/CDK stack and the real issuance test, then stop only it.

Run on Linux/WSL with Docker or a local bitcoind, official CDK 0.18.3, and Node 24.
The supervisor starts its own Core node and mint with public fixture credentials.
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
parser.add_argument('--bitcoind',help='Use an installed Linux Bitcoin Core binary in a temporary data directory')
scenario=parser.add_mutually_exclusive_group()
scenario.add_argument('--protected',action='store_true',help='Issue NUT-11 protected notes, stop the mint and test holder payout')
scenario.add_argument('--protected-cooperative',action='store_true',help='Test the protected melt API and competing holder exit')
parser.add_argument('--batch-protected',action='store_true',help='Commit the ordered blinded batch in the reserve before issuance')
parser.add_argument('--rollover',action='store_true',help='Split a V3 issuance reserve and test both holder exits with the mint offline')
parser.add_argument('--accounting-nova',type=Path,help='Nova executable for the live V3 accounting audit')
parser.add_argument('--collateral-nova',type=Path,help='Local CPU Nova CLI for the optional same-chain bond fixture')
parser.add_argument('--collateral-m14',type=Path,help='Local M14 cashu-settlement executable for the bond fixture')
args=parser.parse_args()
if args.batch_protected and not (args.protected or args.protected_cooperative):
    parser.error('--batch-protected requires a protected scenario')
if args.rollover and (not args.protected or not args.batch_protected or args.accounting_nova
                      or args.collateral_nova or args.collateral_m14):
    parser.error('--rollover requires the isolated V3 mint-offline scenario')
if args.accounting_nova and not (args.protected and args.batch_protected and args.bitcoind):
    parser.error('--accounting-nova requires the V3 holder exit with a local Core binary')
collateral=bool(args.collateral_nova and args.collateral_m14)
if (args.collateral_nova or args.collateral_m14) and (not collateral or not args.protected):
    parser.error('The collateral fixture needs --protected, --collateral-nova and --collateral-m14')
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
        if process and process.poll() is not None:
            raise RuntimeError('The test service exited during startup; inspect its runtime log.')
        try:
            with urllib.request.urlopen(urllib.request.Request(url,data=body,headers=headers or {}),timeout=2) as response:
                data = json.load(response)
        except OSError:
            time.sleep(1)
            continue
        if body is None:
            return data
        error = data.get('error')
        if error is None and 'result' in data:
            return data
        # With JSON-RPC 2.0, Core can reply HTTP 200 with only a warmup error.
        if not isinstance(error, dict) or error.get('code') != -28:
            raise RuntimeError(f'Bitcoin Core readiness RPC failed: {error}')
        time.sleep(1)
    raise RuntimeError('An existing test process did not become ready; inspect it before any restart.')

(ROOT/'.runtime').mkdir(exist_ok=True)
runtime=Path(tempfile.mkdtemp(prefix='regtest-stack-',dir=ROOT/'.runtime'))
token=secrets.token_hex(6);name='proof-grove-'+token;volume=name+'-core'
rpc_port,mint_port=port(),port()
while rpc_port==mint_port:mint_port=port()
process=None;test_process=None;core_process=None;core_data=None;volume_created=False;container_created=False
environment=os.environ|{'PG_TEST_MINT_MNEMONIC':'abandon '*11+'about',
                       'PG_TEST_BDK_MNEMONIC':'legal winner thank year wave sausage worth useful legal winner thank yellow',
                       'PG_TEST_RPC_PASSWORD':'public-regtest-only'}
try:
    core_flags=['-regtest','-server','-txindex=1','-blockfilterindex=1','-listen=0','-connect=0',
                '-dnsseed=0','-discover=0','-fallbackfee=0.00001','-keypool=16',
                '-rpcuser=proofgrove','-rpcpassword=public-regtest-only']
    if args.protected_cooperative or args.accounting_nova:
        if not args.bitcoind:raise RuntimeError('Cooperative settlement requires local Bitcoin Core 31.0 with txospenderindex')
        core_flags.append('-txospenderindex=1')
    if args.bitcoind:
        core_flags.extend(('-dbcache=32', '-par=2'))
        core_data=tempfile.TemporaryDirectory(prefix='proof-grove-cdk-core-')
        with (runtime/'core.log').open('ab') as logfile:
            core_process=subprocess.Popen([str(Path(args.bitcoind).resolve()),*core_flags,
                f'-datadir={core_data.name}',f'-rpcport={rpc_port}','-rpcbind=127.0.0.1'],
                stdout=logfile,stderr=logfile)
    else:
        run('docker','volume','create','--label','proof-grove.run='+token,volume);volume_created=True
        run('docker','run','--detach','--name',name,'--label','proof-grove.run='+token,
            '--publish',f'127.0.0.1:{rpc_port}:18443','--mount',f'type=volume,src={volume},dst=/home/bitcoin/.bitcoin',IMAGE,
            'bitcoind',*core_flags,'-rpcbind=0.0.0.0','-rpcallowip=0.0.0.0/0')
        container_created=True
    rpc_url=f'http://127.0.0.1:{rpc_port}'
    info=wait_url(rpc_url,json.dumps({'jsonrpc':'2.0','id':'pg','method':'getblockchaininfo','params':[]}).encode(),
                  {'Content-Type':'application/json','Authorization':'Basic '+base64.b64encode(b'proofgrove:public-regtest-only').decode()},
                  process=core_process)
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
    test_command=[sys.executable,str(ROOT/'tests/cdk-regtest-integration.py'),'--node',str(node),'--mint',mint_url,'--rpc',rpc_url]
    if args.batch_protected:
        test_command.append('--batch-protected')
    if args.rollover:
        test_command.append('--rollover')
    if args.accounting_nova:
        test_command.extend(('--accounting-nova', str(args.accounting_nova.resolve())))
    if args.protected or args.protected_cooperative:
        handoff=runtime/'protected-handoff';handoff.mkdir()
    if args.protected_cooperative:
        subprocess.run([*test_command,'--protected-handoff',str(handoff),'--cooperative'],cwd=ROOT,env=environment,check=True,timeout=360)
    elif args.protected:
        if collateral:
            test_command.extend(('--collateral-nova',str(args.collateral_nova.resolve()),
                                 '--collateral-m14',str(args.collateral_m14.resolve())))
        test_process=subprocess.Popen([*test_command,'--protected-handoff',str(handoff)],cwd=ROOT,env=environment)
        deadline=time.monotonic()+360
        while test_process.poll() is None and not (handoff/'stop-requested').is_file():
            if time.monotonic()>=deadline:raise TimeoutError('Protected issuance did not reach mint shutdown')
            time.sleep(0.2)
        if test_process.poll() is None:
            process.terminate()
            try:process.wait(timeout=20)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
            (handoff/'mint-stopped').touch(exist_ok=False)
        if test_process.wait(timeout=480 if args.accounting_nova else 300 if collateral else 120)!=0:raise RuntimeError('Protected CDK integration failed')
    else:
        subprocess.run(test_command,cwd=ROOT,env=environment,check=True)
finally:
    if test_process and test_process.poll() is None:
        test_process.terminate()
        try:test_process.wait(timeout=15)
        except subprocess.TimeoutExpired:test_process.kill();test_process.wait(timeout=10)
    if process and process.poll() is None:
        process.terminate()
        try:process.wait(timeout=20)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
    if core_process and core_process.poll() is None:
        core_process.terminate()
        try:core_process.wait(timeout=20)
        except subprocess.TimeoutExpired:core_process.kill();core_process.wait(timeout=10)
    if core_data:
        core_data.cleanup()
    if container_created:
        record=json.loads(run('docker','inspect',name))[0]
        if record['Config']['Labels'].get('proof-grove.run')!=token:raise RuntimeError('Refusing cleanup: container owner changed')
        if record['State']['Running']:run('docker','stop','--time','15',name)
        run('docker','rm',name)
    if volume_created:
        record=json.loads(run('docker','volume','inspect',volume))[0]
        if record.get('Labels',{}).get('proof-grove.run')!=token:raise RuntimeError('Refusing cleanup: volume owner changed')
        run('docker','volume','rm',volume)
