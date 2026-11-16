"""Start the approved, persistent, isolated Ark/Cashu regtest deployment.

Never selects or changes the rehearsal testnet4 service. Keys remain in private
server files. All Docker resources have deployment ownership labels; existing
resources with different ownership are refused. Re-running retains databases.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
import urllib.error
import urllib.request

BASE=Path('/opt/proof-grove');R=BASE/'regtest';BIN=BASE/'bin';APP=BASE/'current'
DOMAIN='proof-grove-regtest.170-75-168-145.sslip.io'
CORE='bitcoin/bitcoin@sha256:a1d05be6939b5c85132a761d2b795f5b8a2612ce53782263da4939778e461792'
ARK='secondark/captaind@sha256:837e433aabbd275c2ae0b3376cd06bc4a0e07d8a9445d40c6dfed9e9bf16eb9b'
LABEL='proof-grove.deployment'


def run(*command):return subprocess.check_output(command,text=True,stderr=subprocess.STDOUT).strip()
def docker(*command):return run('sudo','-n','docker',*command)
def http(base,path='',body=None,headers=None):
    req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,
         headers={'Content-Type':'application/json',**(headers or {})})
    with urllib.request.urlopen(req,timeout=45) as response:raw=response.read()
    return json.loads(raw) if raw else None
def wait(check,label,seconds=120):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        try:
            result=check()
            if result:return result
        except (OSError,subprocess.CalledProcessError,ValueError):pass
        time.sleep(2)
    raise RuntimeError('Service did not become ready: '+label)
def write(path,text):path.write_text(text,encoding='utf-8');path.chmod(0o600)
def service(name,command,directory,environment=None,memory='256M'):
    unit=R/(name+'.service')
    content=f'''[Unit]
Description=Proof Grove isolated regtest {name}
After=network-online.target docker.service
[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory={directory}
ExecStart={command}
Restart=on-failure
RestartSec=5
UMask=0077
MemoryMax={memory}
TasksMax=96
NoNewPrivileges=true
Environment=PYTHONPATH={APP}
Environment=PATH=/home/ubuntu/node24/node-v24.22.1-linux-x64/bin:/usr/local/bin:/usr/bin:/bin
'''
    for file in environment or []:content+='EnvironmentFile='+str(file)+'\n'
    content+='[Install]\nWantedBy=multi-user.target\n'
    write(unit,content)
    run('sudo','-n','install','-m','0644',str(unit),'/etc/systemd/system/'+name+'.service')
    run('sudo','-n','systemctl','daemon-reload')
    run('sudo','-n','systemctl','enable','--now',name+'.service')


def main():
    os.umask(0o077);R.mkdir(exist_ok=True)
    private=R/'private.json'
    fresh=not private.exists()
    settings=json.loads(private.read_text()) if not fresh else {'owner':secrets.token_hex(12),'rpc_password':secrets.token_urlsafe(32)}
    write(private,json.dumps(settings))
    owner=settings['owner'];prefix='proof-grove-regtest';password=settings['rpc_password']
    def owned(kind,name):
        try:record=json.loads(docker(kind,'inspect',name))[0]
        except subprocess.CalledProcessError:return False
        labels=record.get('Config',{}).get('Labels') or record.get('Labels') or {}
        if labels.get(LABEL)!=owner:raise RuntimeError('Existing Docker resource has different ownership: '+name)
        return True
    if not owned('network',prefix):docker('network','create','--label',LABEL+'='+owner,prefix)
    for name in ('core','ark','postgres'):
        if not owned('volume',prefix+'-'+name):docker('volume','create','--label',LABEL+'='+owner,prefix+'-'+name)
    coreconf=R/'bitcoin.conf'
    write(coreconf,f'''regtest=1
server=1
txindex=1
blockfilterindex=1
listen=0
connect=0
dnsseed=0
discover=0
dbcache=64
maxmempool=32
fallbackfee=0.00001
rpcuser=proofgrove
rpcpassword={password}
[regtest]
rpcbind=0.0.0.0
rpcallowip=0.0.0.0/0
''')
    limits=['--restart','unless-stopped','--log-opt','max-size=10m','--log-opt','max-file=3','--pids-limit','256']
    if not owned('container',prefix+'-core'):
        print('Starting isolated Core 31 container',flush=True)
        docker('run','-d','--name',prefix+'-core','--label',LABEL+'='+owner,'--network',prefix,'--network-alias','bitcoind',
            *limits,'--memory','256m','--cpus','0.4','-p','127.0.0.1:28743:18443','-v',prefix+'-core:/home/bitcoin/.bitcoin',
            '--mount',f'type=bind,src={coreconf},dst=/config/bitcoin.conf,readonly',CORE,'bitcoind','-conf=/config/bitcoin.conf')
    else:docker('start',prefix+'-core')
    authorization={'Authorization':'Basic '+base64.b64encode(('proofgrove:'+password).encode()).decode()}
    def rpc(method,params,wallet=False):
        value=http('http://127.0.0.1:28743','/wallet/proof-grove-sandbox-miner' if wallet else '',
            {'jsonrpc':'2.0','id':'pg-bootstrap','method':method,'params':params},authorization)
        if value.get('error'):raise RuntimeError('Isolated Core refused '+method)
        return value['result']
    info=wait(lambda:rpc('getblockchaininfo',[]),'isolated Core')
    if info['chain']!='regtest':raise RuntimeError('Refusing non-regtest bootstrap')
    if 'proof-grove-sandbox-miner' not in rpc('listwallets',[]):
        wallets={entry['name'] for entry in rpc('listwalletdir',[])['wallets']}
        if 'proof-grove-sandbox-miner' in wallets:rpc('loadwallet',['proof-grove-sandbox-miner',True])
        else:rpc('createwallet',{'wallet_name':'proof-grove-sandbox-miner','load_on_startup':True})
    if not settings.get('mining_address'):
        settings['mining_address']=rpc('getnewaddress',[],True);write(private,json.dumps(settings))
    def mine(n=2):rpc('generatetoaddress',[n,settings['mining_address']],True)
    if info['blocks']<106:mine(106-info['blocks'])
    template=BASE/'assets/captaind.default.toml'
    if hashlib.sha256(template.read_bytes()).hexdigest()!='121169bfe16148391745af29278a8b21b5f025c4e036295d2e0130d9b9a7deac':raise RuntimeError('Ark template hash mismatch')
    text=template.read_text()
    for key,value in {'data_dir':'"/data/captaind"','vtxo_lifetime':'8064','vtxo_exit_delta':'6','required_board_confirmations':'2',
       'round_interval':'"10s"','round_submit_time':'"1s"','round_sign_time':'"1s"'}.items():text=re.sub(r'^'+key+r' = .+$',key+' = '+value,text,count=1,flags=re.M)
    for section,changes in {'rpc':{'public_address':'"0.0.0.0:3535"'},'bitcoind':{'url':'"http://bitcoind:18443"','rpc_user':'"proofgrove"','rpc_pass':json.dumps(password)},
       'postgres':{'host':'"localhost"','port':'5432','name':'"bark-server-db"','user':'"postgres"','password':'"postgres"'}}.items():
        match=re.search(r'(?ms)^\['+section+r'\].*?(?=^\[|\Z)',text);body=match.group()
        for key,value in changes.items():
            pattern=r'^#?'+key+r'\s*=.*$'
            body=re.sub(pattern,key+' = '+value,body,count=1,flags=re.M) if re.search(pattern,body,re.M) else body+'\n'+key+' = '+value+'\n'
        text=text[:match.start()]+body+text[match.end():]
    arkconf=R/'captaind.toml';write(arkconf,text)
    if not owned('container',prefix+'-ark'):
        print('Starting isolated Ark 0.8.1 container',flush=True)
        docker('run','-d','--name',prefix+'-ark','--label',LABEL+'='+owner,'--network',prefix,*limits,'--memory','640m','--cpus','0.8',
          '-p','127.0.0.1:28735:3535','-v',prefix+'-ark:/data/captaind','-v',prefix+'-postgres:/var/lib/postgresql/data',
          '--mount',f'type=bind,src={arkconf},dst=/config.toml,readonly','-e','CAPTAIND_CONFIG=/config.toml',ARK)
    else:docker('start',prefix+'-ark')
    def ark_wallet():return json.loads(docker('exec',prefix+'-ark','captaind','--config','/config.toml','rpc','wallet'))
    ark=wait(ark_wallet,'Ark wallet')
    if not settings.get('ark_funded'):
        rpc('sendtoaddress',[ark['rounds']['address'],1],True);mine(3);settings['ark_funded']=True;write(private,json.dumps(settings))
    wallet=R/'wallet';wallet.mkdir(exist_ok=True)
    service('proof-grove-bark',f'{BIN}/barkd-0.8.1-linux-x86_64 --datadir {wallet} --port 28745 --no-ui',R)
    wait(lambda:(wallet/'auth_token').exists(),'Bark authentication')
    bearer=(wallet/'auth_token').read_text().strip()
    def bark(path,body=None):return http('http://127.0.0.1:28745','/api/v1'+path,body,{'Authorization':'Bearer '+bearer})
    wait(lambda:bark('/wallet'),'Bark REST')
    if bark('/wallet')['fingerprint'] is None:
        bark('/wallet/create',{'network':'regtest','ark_server':'http://127.0.0.1:28735','force':False,
          'chain_source':{'bitcoind':{'bitcoind':'http://127.0.0.1:28743','bitcoind_auth':{'user-pass':{'user':'proofgrove','pass':password}}}}})
    bark('/wallet/addresses/next',{})
    if not settings.get('wallet_funded'):
        address=bark('/onchain/addresses/next',{})['address'];rpc('sendtoaddress',[address,0.002],True);mine(3)
        bark('/onchain/sync',{});bark('/boards/board-amount',{'amount_sat':50000});mine(3);bark('/wallet/sync',{})
        settings['wallet_funded']=True;write(private,json.dumps(settings))
    processor=R/'processor';processor.mkdir(exist_ok=True)
    def processor_config(mnemonic):return f'''address="127.0.0.1"
port=28751
allow_insecure=true
[bark]
mnemonic={json.dumps(mnemonic)}
network="regtest"
server_address="http://127.0.0.1:28735"
bitcoind_address="http://127.0.0.1:28743"
bitcoind_user="proofgrove"
bitcoind_password_env="PG_TEST_RPC_PASSWORD"
data_dir="{processor/'data'}"
event_poll_interval_ms=2000
payment_methods=["arkoor"]
'''
    env=os.environ|{'PG_TEST_RPC_PASSWORD':password}
    if not settings.get('processor_mnemonic'):
        write(processor/'config.toml',processor_config('seed-generation-only'))
        for key in ('processor_mnemonic','mint_mnemonic','bdk_mnemonic'):
            cp=subprocess.run([str(BIN/'regtest-liquidity-linux-x86_64'),'seed'],cwd=processor,env=env,text=True,capture_output=True,check=True)
            settings[key]=json.loads(cp.stdout)['mnemonic']
        write(private,json.dumps(settings))
    write(processor/'config.toml',processor_config(settings['processor_mnemonic']))
    env|={'PG_TEST_MINT_MNEMONIC':settings['mint_mnemonic'],'PG_TEST_BDK_MNEMONIC':settings['bdk_mnemonic']}
    environment=R/'credentials.env'
    write(environment,'\n'.join(k+'='+v for k,v in {**{k:env[k] for k in ('PG_TEST_RPC_PASSWORD','PG_TEST_MINT_MNEMONIC','PG_TEST_BDK_MNEMONIC')},'PG_BARK_TOKEN':bearer}.items())+'\n')
    if not settings.get('processor_funded'):
        def liquidity(*options):
            cp=subprocess.run([str(BIN/'regtest-liquidity-linux-x86_64'),*options],cwd=processor,env=env,text=True,capture_output=True,check=True)
            return json.loads(cp.stdout)
        address=liquidity('address')['address'];rpc('sendtoaddress',[address,0.01],True);mine(3);liquidity('board','500000');mine(3)
        wait(lambda:liquidity('status')['spendable_sats']>=10000,'mint Ark liquidity')
        settings['processor_funded']=True;write(private,json.dumps(settings))
    service('proof-grove-processor',str(BIN/'cdk-payment-processor-bark-linux-x86_64'),processor,[environment],memory='384M')
    def grpc_ready():
        import socket
        with socket.create_connection(('127.0.0.1',28751),timeout=2):return True
    wait(grpc_ready,'Bark processor')
    mint=R/'mint';mint.mkdir(exist_ok=True)
    write(mint/'config.toml','''[info]
url="http://127.0.0.1:28738"
listen_host="127.0.0.1"
listen_port=28738
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
backend="grpcprocessor"
unit="sat"
[grpc_processor]
supported_units=["sat"]
address="127.0.0.1"
port=28751
allow_insecure=true
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
bitcoind_rpc_port=28743
bitcoind_rpc_user="proofgrove"
bitcoind_rpc_password="env:PG_TEST_RPC_PASSWORD"
''')
    if not settings.get('mint_initialized'):
        with (R/'mint-bootstrap.log').open('ab') as log:
            subprocess.run([str(BIN/'cdk-mintd-0.18.3-x86_64'),'--work-dir',str(mint),'config','init','--new-mint','--file',str(mint/'config.toml')],env=env,stdout=log,stderr=log,check=True)
        settings['mint_initialized']=True;write(private,json.dumps(settings))
    service('proof-grove-mint',f'{BIN}/cdk-mintd-0.18.3-x86_64 --work-dir {mint}',mint,[environment])
    wait(lambda:http('http://127.0.0.1:28738','/v1/info'),'Cashu mint')
    api=R/'api';api.mkdir(exist_ok=True)
    config={'mode':'regtest','database':str(api/'desk.sqlite'),'core':{'url':'http://127.0.0.1:28743','username':'proofgrove','password_env':'PG_TEST_RPC_PASSWORD'},
      'cashu_url':'http://127.0.0.1:28738','bark_url':'http://127.0.0.1:28745','bark_bearer_env':'PG_BARK_TOKEN',
      'ark_regtest_execution':True,'ark_regtest_exit_broadcast':False,'min_confirmations':2,'intents':[],
      'hosted_api':{'token_env':'PROOF_GROVE_API_TOKEN','allowed_origins':['https://patrickdugan.github.io'],'public_hosts':[DOMAIN],'allow_mutations':True,'allow_private_bundles':False}}
    write(R/'api.local.json',json.dumps(config,indent=2))
    service('proof-grove-regtest-api',f'/usr/bin/python3 -m proofdesk serve --config {R}/api.local.json --hosted --port 8768',api,[BASE/'config/operator.env',environment])
    service('proof-grove-regtest-miner',f'/usr/bin/python3 {APP}/deploy/mine-regtest.py',R)
    # Replace the miner's continuous service policy with a controlled timer.
    miner=R/'proof-grove-regtest-miner.service'
    content=miner.read_text().replace('Restart=on-failure\nRestartSec=5\n','Type=oneshot\n')
    write(miner,content);run('sudo','-n','install','-m','0644',str(miner),'/etc/systemd/system/'+miner.name)
    timer=R/'proof-grove-regtest-miner.timer';write(timer,'[Unit]\nDescription=Mine valueless Proof Grove regtest blocks\n[Timer]\nOnBootSec=30s\nOnUnitActiveSec=30s\nUnit=proof-grove-regtest-miner.service\n[Install]\nWantedBy=timers.target\n')
    run('sudo','-n','install','-m','0644',str(timer),'/etc/systemd/system/'+timer.name)
    run('sudo','-n','systemctl','daemon-reload');run('sudo','-n','systemctl','enable','--now',timer.name)
    print(json.dumps({'regtest_backend_ready':True,'mint':'CDK 0.18.3','bark':'0.8.1','network':'regtest','testnet4_node_changed':False}),flush=True)


if __name__=='__main__':main()
