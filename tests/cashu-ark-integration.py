"""Real Cashu custom melt into a new Bark wallet, isolated regtest coins only.

Invoked by run-ark-stack.py. Uses a separately funded mint Ark wallet and BDK
deposit backend. Drops the successful melt reply and restarts the client before
recovering change. Recipient refresh and Core anchors provide separate evidence.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from proofdesk.adapters import BarkClient, CoreClient
from proofdesk.ark import ArkCaretaker
from proofdesk.domain import Ledger
from proofdesk.server import Desk, make_server

parser=argparse.ArgumentParser(description=__doc__)
for option in ('stack','cdk','node','processor','liquidity-helper'):parser.add_argument('--'+option,required=True)
parser.add_argument('--test-exit',action='store_true',help='Exit the exact recipient successor with mint and Ark server offline')
args=parser.parse_args()
meta=json.loads(Path(args.stack).read_text());runtime=Path(meta['runtime'])
if not re.fullmatch(r'pgark-[0-9a-f]{12}',meta['name']):raise SystemExit('Owned stack required')
for suffix in ('-core','-server'):
 record=json.loads(subprocess.check_output(['docker','inspect',meta['name']+suffix]))[0]
 if record['Config']['Labels'].get('proof-grove.ark')!=meta['name'][6:]:raise SystemExit('Stack ownership mismatch')
cdk=Path(args.cdk).resolve()
if hashlib.sha256(cdk.read_bytes()).hexdigest()!='3a41003fcac0f54a164b6d9187c79ce05591947bb4b4b37c45a125fac813e3af':raise SystemExit('Pinned CDK 0.18.3 required')
environment={k:v for k,v in os.environ.items() if not k.startswith(('BARK_','SERVER_','TLS_','CDK_')) and k!='ALLOW_INSECURE'}|{'PG_TEST_MINT_MNEMONIC':'abandon '*11+'about',
 'PG_TEST_BDK_MNEMONIC':'legal winner thank year wave sausage worth useful legal winner thank yellow',
 'PG_TEST_RPC_PASSWORD':'ark','PROOF_GROVE_WALLET_PASSWORD':'public-isolated-regtest-fixture-password'}
headers={'Authorization':'Bearer '+Path(meta['auth_file']).read_text().strip()}

def http(base,path='',body=None,headers=None):
 req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,
  headers={'Content-Type':'application/json',**(headers or {})})
 try:
  with urllib.request.urlopen(req,timeout=45) as response:raw=response.read()
 except urllib.error.HTTPError as e:raise RuntimeError(f'{path} HTTP {e.code}: '+e.read().decode()[:700]) from None
 return json.loads(raw) if raw else None
def bark(path,body=None):return http(meta['bark'],'/api/v1'+path,body,headers)
def rpc(method,params,wallet=False):
 result=http(meta['rpc'],'/wallet/proof-grove-ark' if wallet else '',{'jsonrpc':'2.0','id':'pgcashu','method':method,'params':params},
  {'Authorization':'Basic '+base64.b64encode(b'second:ark').decode()})
 if result.get('error'):raise RuntimeError(str(result['error']))
 return result['result']
def wait(check,description,seconds=100):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:
  result=check()
  if result:return result
  time.sleep(1)
 raise RuntimeError('Timed out: '+description)
def port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
def ready(base,process):
 for _ in range(60):
  if process.poll() is not None:raise RuntimeError('New fixture process exited; inspect runtime logs')
  try:return http(base,'/v1/info')
  except (OSError,RuntimeError):time.sleep(1)
 raise RuntimeError('Mint did not become ready')

assert rpc('getblockchaininfo',[])['chain']=='regtest'
assert bark('/wallet')['fingerprint'] is None, 'Fresh receiver required'
rpc('createwallet',['proof-grove-ark'])
mining=rpc('getnewaddress',[],True)
def mine(n=2):return rpc('generatetoaddress',[n,mining])
mine(106)
server_info=json.loads(subprocess.check_output(['docker','exec',meta['name']+'-server','captaind','--config','/config.toml','rpc','wallet'],text=True))
rpc('sendtoaddress',[server_info['rounds']['address'],1],True);mine(3)
bark('/wallet/create',{'network':'regtest','ark_server':meta['ark'],'force':False,
 'chain_source':{'bitcoind':{'bitcoind':meta['rpc'],'bitcoind_auth':{'user-pass':{'user':'second','pass':'ark'}}}}})
destination=bark('/wallet/addresses/next',{})['address']
baseline={v['id'] for v in bark('/wallet/vtxos')}

processor_dir=runtime/'processor';processor_dir.mkdir()
grpc_port,mint_port=port(),port()
(processor_dir/'config.toml').write_text(f'''address="127.0.0.1"
port={grpc_port}
allow_insecure=true
[bark]
mnemonic="letter advice cage absurd amount doctor acoustic avoid letter advice cage above"
network="regtest"
server_address="{meta['ark']}"
bitcoind_address="{meta['rpc']}"
bitcoind_user="second"
bitcoind_password_env="PG_TEST_RPC_PASSWORD"
data_dir="{processor_dir/'data'}"
event_poll_interval_ms=500
payment_methods=["arkoor"]
''')
def liquidity(*options):
 cp=subprocess.run([str(Path(args.liquidity_helper).resolve()),*options],cwd=processor_dir,env=environment,text=True,capture_output=True,timeout=90)
 if cp.returncode:raise RuntimeError('Liquidity fixture failed: '+cp.stderr[-1200:])
 return json.loads(cp.stdout)
address=liquidity('address')['address']
rpc('sendtoaddress',[address,0.01],True);mine(3)
board=liquidity('board','500000');mine(3)
mint_liquidity=wait(lambda: (s if (s:=liquidity('status'))['spendable_sats']>=10000 else None),'mint Ark liquidity')
print(json.dumps({'stage':'mint-liquidity-ready','spendable_sats':mint_liquidity['spendable_sats']}),flush=True)

processes=[];ledger=None;desk_server=None;proxy=None
try:
 with (runtime/'processor.log').open('ab') as log:
  processor=subprocess.Popen([str(Path(args.processor).resolve())],cwd=processor_dir,env=environment,stdout=log,stderr=log);processes.append(processor)
 def processor_ready():
  if processor.poll() is not None:raise RuntimeError('Processor exited; inspect processor.log')
  try:
   with socket.create_connection(('127.0.0.1',grpc_port),timeout=1):return True
  except OSError:return False
 wait(processor_ready,'processor gRPC listener',60)
 mint_dir=runtime/'mint';mint_dir.mkdir()
 mint_url=f'http://127.0.0.1:{mint_port}'
 config=mint_dir/'config.toml'
 config.write_text(f'''[info]
url="{mint_url}"
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
backend="grpcprocessor"
unit="sat"
[grpc_processor]
supported_units=["sat"]
address="127.0.0.1"
port={grpc_port}
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
bitcoind_rpc_port={urllib.parse.urlsplit(meta['rpc']).port}
bitcoind_rpc_user="second"
bitcoind_rpc_password="env:PG_TEST_RPC_PASSWORD"
''')
 with (runtime/'mint-bootstrap.log').open('ab') as log:
  subprocess.run([str(cdk),'--work-dir',str(mint_dir),'config','init','--new-mint','--file',str(config)],env=environment,stdout=log,stderr=log,check=True)
 with (runtime/'mint.log').open('ab') as log:
  mint=subprocess.Popen([str(cdk),'--work-dir',str(mint_dir)],env=environment,stdout=log,stderr=log);processes.append(mint)
 ready(mint_url,mint)
 counts={'melt_posts':0,'dropped_replies':0,'restore_posts':0,'melt_http_statuses':[]}
 upstream=urllib.parse.urlsplit(mint_url)
 class Proxy(BaseHTTPRequestHandler):
  def log_message(self,*_):pass
  def forward(self):
   body=self.rfile.read(int(self.headers.get('Content-Length','0'))) if self.command=='POST' else None
   conn=HTTPConnection(upstream.hostname,upstream.port,timeout=60)
   conn.request(self.command,self.path,body=body,headers={'Content-Type':'application/json'})
   response=conn.getresponse();data=response.read();status=response.status;conn.close()
   if self.command=='POST' and self.path=='/v1/melt/arkoor':
    counts['melt_posts']+=1
    counts['melt_http_statuses'].append(status)
    if 200<=status<300 and json.loads(data).get('state')=='PAID' and counts['dropped_replies']==0:
     counts['dropped_replies']+=1;self.close_connection=True;self.connection.shutdown(socket.SHUT_RDWR);self.connection.close();return
   if self.command=='POST' and self.path=='/v1/restore':counts['restore_posts']+=1
   self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
  do_GET=forward
  do_POST=forward
 proxy=ThreadingHTTPServer(('127.0.0.1',0),Proxy);threading.Thread(target=proxy.serve_forever,daemon=True).start()
 proxied_mint=f'http://127.0.0.1:{proxy.server_port}'
 ledger=Ledger(runtime/'cashu-ark.sqlite','regtest')
 core=CoreClient(meta['rpc'],'second','ark')
 desk=Desk('regtest',ledger,None,core,{'cashu_url':proxied_mint,'min_confirmations':2})
 desk_server=make_server(desk,0);threading.Thread(target=desk_server.serve_forever,daemon=True).start()
 common=['--vault',str(runtime/'cashu-wallet.sqlite'),'--mint',proxied_mint,'--desk',f'http://127.0.0.1:{desk_server.server_port}']
 def client(command,*options):
  cp=subprocess.run([args.node,str(ROOT/'wallet/cli.mjs'),command,*common,*options],cwd=ROOT,env=environment,text=True,capture_output=True,timeout=120)
  try:result=json.loads(cp.stdout)
  except ValueError:raise AssertionError('No wallet JSON: '+cp.stderr[-1000:]) from None
  if cp.returncode:raise AssertionError('Wallet failed: '+str(result))
  return result
 started=time.monotonic()
 deposit=client('deposit','--amount','25000');operation=deposit['operation_id']
 txid=rpc('sendtoaddress',[deposit['request'],0.00025],True);mine(2)
 transaction=rpc('getrawtransaction',[txid,True])
 vout=next(o['n'] for o in transaction['vout'] if o.get('scriptPubKey',{}).get('address')==deposit['request'])
 binding=json.loads(ledger.db.execute('SELECT body FROM cashu_bindings WHERE intent_id=?',(deposit['intent_id'],)).fetchone()[0])
 wait(lambda:desk.cashu.mint.raw_quote(binding['quote']).get('amount_paid')==25000,'BDK deposit observation')
 assert client('admit-regtest','--id',operation,'--txid',txid,'--vout',str(vout))['evidence_level']=='core-regtest'
 issued=client('claim','--id',operation);assert issued['amount_sats']==25000 and issued['dleq_verified']
 print(json.dumps({'stage':'cashu-issued','amount_sats':25000}),flush=True)
 quote=client('ark-quote','--id',operation,'--destination',destination,'--amount','10000','--max-fee','0')
 payment=quote['payment_id']
 attempted=client('ark-pay','--payment',payment);assert attempted['state']=='uncertain',(attempted,counts)
 # Every call is a fresh process. A second ark-pay must never resubmit.
 assert client('ark-pay','--payment',payment)['state']=='uncertain'
 recovered=client('ark-status','--payment',payment)
 assert recovered['state']=='cashu_redeemed' and recovered['change_sats']==15000 and recovered['actual_fee_sats']==0,recovered
 assert client('ark-status','--payment',payment)==recovered
 assert client('audit','--id',operation)['amount_sats']==15000
 assert counts['melt_posts']==1 and counts['dropped_replies']==1,counts
 print(json.dumps({'stage':'cashu-redeemed-with-lost-reply','change_sats':15000,**counts}),flush=True)
 def received():
  bark('/wallet/sync',{})
  return [v for v in bark('/wallet/vtxos') if v['id'] not in baseline and v['state']['type']=='spendable']
 arrival=wait(received,'Ark recipient VTXO')
 assert sum(v['amount_sat'] for v in arrival)==10000,arrival
 history=bark('/history')
 matches=[m for m in history if any(d.get('destination',{}).get('value')==destination and d.get('amount_sat')==10000 for d in m.get('received_on',[]))]
 assert len(matches)==1,matches
 # Do not accept the mint's payment_preimage as evidence of recipient ownership.
 # Bark validates the incoming VTXO; refresh gives a new anchored exit path.
 caretaker=ArkCaretaker(ledger,BarkClient(meta['bark'],headers['Authorization'][7:]),core,allow_regtest=True)
 mine(8);bark('/wallet/sync',{})
 refresh=caretaker.refresh([v['id'] for v in arrival],rpc('getblockcount',[])+2,1000)
 for _ in range(40):
  mine(2);time.sleep(1);bark('/wallet/sync',{})
  refresh=caretaker.reconcile(refresh['id'])
  if refresh['state']=='confirmed':break
 assert refresh['state']=='confirmed',refresh
 successor=refresh['result']['successors'];ark_value=sum(v['amount_sat'] for v in successor)
 fee=refresh['result']['actual_fee_sats']
 assert ark_value+fee==10000 and 0<=fee<=1000
 # The completed Ark transfer must remain usable after mint services stop.
 for p in reversed(processes):p.terminate();p.wait(timeout=20)
 assert all(p.poll() is not None for p in processes)
 bark('/wallet/sync',{})
 assert {v['id'] for v in successor}<={v['id'] for v in bark('/wallet/vtxos') if v['state']['type']=='spendable'}
 exit_report=None
 if args.test_exit:
  assert len(successor)==1, 'One recipient successor required for this fixture'
  # CPFP requires independent on-chain fee coins; they are not user deposit value.
  fee_address=bark('/onchain/addresses/next',{})['address']
  rpc('sendtoaddress',[fee_address,0.0004],True);mine(2);bark('/onchain/sync',{})
  report_path=ROOT/'docs/cashu-ark-exit-integration.json'
  subprocess.run([sys.executable,str(ROOT/'tests/ark-exit-integration.py'),'--stack',args.stack,
   '--expected-vtxo',successor[0]['id'],'--report',str(report_path)],cwd=ROOT,env=environment,check=True)
  exit_report=json.loads(report_path.read_text())
  assert exit_report['input_vtxos']==[successor[0]['id']] and exit_report['input_value_sats']==ark_value
  assert exit_report['owner_claim_value_sats']+exit_report['owner_claim_fee_sats']==ark_value
 report={'status':'passed','tested_at':datetime.now(timezone.utc).isoformat(),'network':'isolated regtest',
  'cdk_version':'0.18.3','bark_version':'0.8.1','cashu_sdk':'4.13.1',
  'payment_evidence':'core-regtest','zk_verified':False,
  'processor_upstream_commit':'d7244e261506b51d5b309a558bf19cd4ffc32f13',
  'processor_binary_sha256':hashlib.sha256(Path(args.processor).read_bytes()).hexdigest(),
  'processor_lock_sha256':hashlib.sha256((ROOT/'integrations/bark-processor/Cargo.lock').read_bytes()).hexdigest(),
  'deposit_sats':25000,'melt_amount_sats':10000,'cashu_change_sats':15000,'melt_fee_sats':0,
  'ark_after_refresh_sats':ark_value,'refresh_fee_sats':fee,'change_dleq_verified':True,
  'wallet_restart_recovery':True,'mint_services_stopped_after_payment':True,
  'unilateral_exit_tested':bool(exit_report),
  'owner_claim_sats':exit_report['owner_claim_value_sats'] if exit_report else None,
  'owner_claim_fee_sats':exit_report['owner_claim_fee_sats'] if exit_report else None,
  'independent_cpfp_fee_sats':exit_report['saved_cpfp_fee_sats'] if exit_report else None,
  'extra_fixture_fee_funding_sats':40000 if exit_report else 0,
  'received_vtxos':[v['id'] for v in arrival],'successor_vtxos':[v['id'] for v in successor],
  'anchors':refresh['result']['anchors'],'counts':counts,'seconds':round(time.monotonic()-started,3),
  'limits':['Test coins only. Cashu remains custodial until redemption.',
   'Bark validates Ark signatures and ownership; the Python desk checks Core anchors.',
   'Separate public-fixture Ark liquidity funds the mint; no reserve or solvency proof.',
   'Delegated refresh REST has no signing-time fee cap; writes remain regtest-only.',
   'No new Nova proof or funded BitVM bridge is generated by this test.']}
 (ROOT/'docs/cashu-ark-integration.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report),flush=True)
finally:
 if desk_server:desk_server.shutdown();desk_server.server_close()
 if proxy:proxy.shutdown();proxy.server_close()
 if ledger:ledger.close()
 for p in reversed(processes):
  if p.poll() is None:
   p.terminate()
   try:p.wait(timeout=20)
   except subprocess.TimeoutExpired:p.kill();p.wait(timeout=10)
