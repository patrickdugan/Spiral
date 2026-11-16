"""Run a fresh Bark/Core regtest stack, verify delegated refresh, then clean up.

Linux/WSL, Docker, the official Bark 0.8.1 binary and pinned config template
are required. No existing wallet or container is selected.
"""
import argparse, hashlib, json, pathlib, secrets, socket, subprocess, sys, time
ROOT=pathlib.Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--bark',required=True,help='Official barkd-0.8.1-linux-x86_64 binary')
parser.add_argument('--server-config-template',required=True,help='server/captaind.default.toml from bark-0.8.1')
parser.add_argument('--keep-preview',action='store_true',help='Keep preview until STOP_PREVIEW is created in the reported runtime directory')
parser.add_argument('--test-exits',action='store_true',help='Also test independent exit broadcasting and the owner claim with the Ark server offline')
parser.add_argument('--test-cashu',action='store_true',help='Test a real Cashu to Ark withdrawal instead of the standalone refresh fixture')
parser.add_argument('--test-cashu-exit',action='store_true',help='Also exit the redeemed Ark payment with mint and Ark server offline')
for option in ('cdk','node','processor','liquidity-helper'):
 parser.add_argument('--'+option,help='Required with --test-cashu')
args=parser.parse_args()
if args.test_cashu_exit:args.test_cashu=True
if args.test_cashu and (args.test_exits or args.keep_preview):parser.error('Cashu test owns its own lifecycle; use it separately')
if args.test_cashu and any(not getattr(args,n) for n in ('cdk','node','processor','liquidity_helper')):parser.error('Cashu test requires --cdk --node --processor --liquidity-helper')
if sys.platform!='linux':raise SystemExit('Run on Linux or inside WSL.')
template=pathlib.Path(args.server_config_template).resolve()
if hashlib.sha256(template.read_bytes()).hexdigest()!='121169bfe16148391745af29278a8b21b5f025c4e036295d2e0130d9b9a7deac':
 raise SystemExit('Server template is not the pinned Bark 0.8.1 file.')
(ROOT/'.runtime').mkdir(exist_ok=True)
R=ROOT/'.runtime'/('ark-'+secrets.token_hex(5));R.mkdir(parents=True)
IMAGE='secondark/captaind@sha256:837e433aabbd275c2ae0b3376cd06bc4a0e07d8a9445d40c6dfed9e9bf16eb9b'
CORE='bitcoin/bitcoin@sha256:a1d05be6939b5c85132a761d2b795f5b8a2612ce53782263da4939778e461792'
BARK=pathlib.Path(args.bark).resolve()
if hashlib.sha256(BARK.read_bytes()).hexdigest()!='e634724a17796de352beb2e28808059dd3d0aef1beb3afd358ee3a582c20c85c':
 raise SystemExit('Bark binary does not match the official 0.8.1 checksum.')
token=secrets.token_hex(6);name='pgark-'+token;owned=[];volumes=[];processes=[]
def run(*args):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT).strip()
def port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
rpcport,arkport,barkport=port(),port(),port()
def ownership(record):
 labels=record.get('Config',{}).get('Labels') or record.get('Labels') or {}
 if labels.get('proof-grove.ark')!=token:raise RuntimeError('Refusing cleanup: test resource ownership changed')
try:
 run('docker','network','create','--label','proof-grove.ark='+token,name)
 for v in ['core','captaind','pg']:
  volume=name+'-'+v;run('docker','volume','create','--label','proof-grove.ark='+token,volume);volumes.append(volume)
 run('docker','run','-d','--name',name+'-core','--label','proof-grove.ark='+token,'--network',name,'--network-alias','bitcoind','-p',f'127.0.0.1:{rpcport}:18443','-v',volumes[0]+':/home/bitcoin/.bitcoin',CORE,'bitcoind','-regtest','-server','-txindex=1','-blockfilterindex=1','-listen=0','-connect=0','-dnsseed=0','-discover=0','-fallbackfee=0.00001','-rpcbind=0.0.0.0','-rpcallowip=0.0.0.0/0','-rpcuser=second','-rpcpassword=ark');owned.append(name+'-core')
 config=R/'captaind.toml'
 text=template.read_text()
 import re
 for key,value in {'data_dir':'"/data/captaind"','vtxo_lifetime':'288','vtxo_exit_delta':'6','required_board_confirmations':'2','round_interval':'"5s"','round_submit_time':'"1s"','round_sign_time':'"1s"'}.items():
  text=re.sub(r'^'+key+r' = .+$',key+' = '+value,text,count=1,flags=re.M)
 for section,changes in {'rpc':{'public_address':'"0.0.0.0:3535"'},'bitcoind':{'url':'"http://bitcoind:18443"','rpc_user':'"second"','rpc_pass':'"ark"'},'postgres':{'host':'"localhost"','port':'5432','name':'"bark-server-db"','user':'"postgres"','password':'"postgres"'}}.items():
  match=re.search(r'(?ms)^\['+section+r'\].*?(?=^\[|\Z)',text);body=match.group()
  for key,value in changes.items():
   pattern=r'^#?'+key+r'\s*=.*$'
   if re.search(pattern,body,re.M):body=re.sub(pattern,key+' = '+value,body,count=1,flags=re.M)
   else:body+='\n'+key+' = '+value+'\n'
  text=text[:match.start()]+body+text[match.end():]
 config.write_text(text)
 run('docker','run','-d','--name',name+'-server','--label','proof-grove.ark='+token,'--network',name,'-p',f'127.0.0.1:{arkport}:3535','-v',volumes[1]+':/data/captaind','-v',volumes[2]+':/var/lib/postgresql/data','--mount',f'type=bind,src={config},dst=/config.toml,readonly','-e','CAPTAIND_CONFIG=/config.toml',IMAGE);owned.append(name+'-server')
 time.sleep(12)
 data=R/'wallet';data.mkdir()
 logfile=(R/'barkd.log').open('ab');p=subprocess.Popen([str(BARK),'--datadir',str(data),'--port',str(barkport),'--no-ui'],stdout=logfile,stderr=logfile);processes.append(p)
 for _ in range(30):
  if (data/'auth_token').exists():break
  if p.poll() is not None:raise RuntimeError('New Bark daemon exited; inspect runtime log')
  time.sleep(1)
 meta={'runtime':str(R),'name':name,'rpc':f'http://127.0.0.1:{rpcport}','ark':f'http://127.0.0.1:{arkport}','bark':f'http://127.0.0.1:{barkport}','auth_file':str(data/'auth_token'),'bark_pid':p.pid}
 (R/'stack.json').write_text(json.dumps(meta,indent=2));(ROOT/'.runtime/ark-stack.json').write_text(json.dumps(meta,indent=2));print(json.dumps(meta),flush=True)
 if args.keep_preview:(R/('KEEP_EXIT_PREVIEW' if args.test_exits else 'KEEP_PREVIEW')).touch()
 if args.test_cashu:
  command=[sys.executable,str(ROOT/'tests/cashu-ark-integration.py'),'--stack',str(R/'stack.json')]
  if args.test_cashu_exit:command+=['--test-exit']
  for option in ('cdk','node','processor','liquidity-helper'):command+=['--'+option,getattr(args,option.replace('-','_'))]
  subprocess.run(command,cwd=ROOT,check=True)
 else:subprocess.run([sys.executable,str(ROOT/'tests/ark-regtest-integration.py'),'--stack',str(R/'stack.json')],cwd=ROOT,check=True)
 if args.test_exits:
  subprocess.run([sys.executable,str(ROOT/'tests/ark-exit-integration.py'),'--stack',str(R/'stack.json')],cwd=ROOT,check=True)
finally:
 for p in processes:
  if p.poll() is None:p.terminate()
  try:p.wait(timeout=20)
  except subprocess.TimeoutExpired:p.kill();p.wait(timeout=10)
 for n in reversed(owned):
  record=json.loads(run('docker','inspect',n))[0];ownership(record)
  (R/(n+'.log')).write_text(run('docker','logs','--tail','500',n));run('docker','stop','--time','10',n);run('docker','rm',n)
 for v in volumes:
  record=json.loads(run('docker','volume','inspect',v))[0];ownership(record);run('docker','volume','rm',v)
 record=json.loads(run('docker','network','inspect',name))[0];ownership(record);run('docker','network','rm',name)
 print('Stopped owned Ark test stack',flush=True)
