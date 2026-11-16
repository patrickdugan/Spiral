"""Exercise a NEW isolated Bark 0.8.1/Core 31 regtest stack. No real funds."""
import argparse
import base64
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from proofdesk.adapters import BarkClient, CoreClient
from proofdesk.ark import ArkCaretaker
from proofdesk.domain import Ledger
from proofdesk.server import Desk, make_server

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stack',required=True)
parser.add_argument('--report',default=str(ROOT/'docs/ark-integration.json'))
args=parser.parse_args()
meta=json.loads(Path(args.stack).read_text());runtime=Path(meta['runtime'])
if not re.fullmatch(r'pgark-[0-9a-f]{12}',meta['name']):raise SystemExit('An owned test stack is required')
for suffix in ('-core','-server'):
    record=json.loads(subprocess.check_output(['docker','inspect',meta['name']+suffix]))[0]
    if record['Config']['Labels'].get('proof-grove.ark')!=meta['name'][6:]:raise SystemExit('Test stack ownership mismatch')
auth=Path(meta['auth_file']).read_text().strip()
headers={'Authorization':'Bearer '+auth}

def http(base,path='',body=None,headers=None):
    req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,
                               headers={'Content-Type':'application/json',**(headers or {})})
    try:
        with urllib.request.urlopen(req,timeout=45) as response:raw=response.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'Upstream {path} returned {e.code}: '+e.read().decode()[:600]) from None
    return json.loads(raw) if raw else None

def bark(path,body=None):return http(meta['bark'],'/api/v1'+path,body,headers)
def rpc(method,params, wallet=''):
    result=http(meta['rpc'],('/wallet/'+wallet if wallet else ''),{'jsonrpc':'2.0','id':'pgark','method':method,'params':params},
                {'Authorization':'Basic '+base64.b64encode(b'second:ark').decode()})
    if result.get('error'):raise RuntimeError(str(result['error']))
    return result['result']
def wait(check,description,seconds=90):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        result=check()
        if result:return result
        time.sleep(1)
    raise RuntimeError('Timed out: '+description)

if rpc('getblockchaininfo',[])['chain']!='regtest':raise SystemExit('Regtest required')
assert bark('/wallet')['fingerprint'] is None, 'This test requires a new wallet, never an existing one.'
if 'proof-grove-ark' not in rpc('listwallets',[]):
    rpc('createwallet',['proof-grove-ark'])
mining=rpc('getnewaddress',[], 'proof-grove-ark')
def mine(n=2):return rpc('generatetoaddress',[n,mining])
mine(106)
server=json.loads(subprocess.check_output(['docker','exec',meta['name']+'-server','captaind','--config','/config.toml','rpc','wallet'],text=True))
rpc('sendtoaddress',[server['rounds']['address'],1], 'proof-grove-ark')
mine(3)
bark('/wallet/create',{'network':'regtest','ark_server':meta['ark'],'force':False,
     'chain_source':{'bitcoind':{'bitcoind':meta['rpc'],'bitcoind_auth':{'user-pass':{'user':'second','pass':'ark'}}}}})
bark('/wallet/addresses/next',{})
address=bark('/onchain/addresses/next',{})['address']
rpc('sendtoaddress',[address,0.01], 'proof-grove-ark');mine(3)
bark('/onchain/sync',{})
bark('/boards/board-amount',{'amount_sat':500000});mine(3)
def available():
    bark('/wallet/sync',{})
    return [v for v in bark('/wallet/vtxos') if v['state']['type']=='spendable']
old=wait(available,'boarded VTXO')[0]
print('Boarded real regtest VTXO',flush=True)
mine(8)
bark('/wallet/sync',{})
stats={'refresh_posts':0,'dropped_replies':0}

class Proxy(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def handle_request(self):
        body=self.rfile.read(int(self.headers.get('Content-Length','0')))
        request=urllib.request.Request(meta['bark']+self.path,data=body if self.command=='POST' else None,
                                       headers={'Content-Type':'application/json',**headers},method=self.command)
        with urllib.request.urlopen(request,timeout=45) as response:raw=response.read();status=response.status
        if self.command=='POST':
            assert self.path=='/api/v1/wallet/refresh/delegated/vtxos'
            stats['refresh_posts']+=1
            if stats['refresh_posts']==1:
                stats['dropped_replies']+=1;self.close_connection=True
                self.connection.shutdown(socket.SHUT_RDWR);self.connection.close();return
        self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    do_GET=handle_request
    do_POST=handle_request

proxy=ThreadingHTTPServer(('127.0.0.1',0),Proxy);threading.Thread(target=proxy.serve_forever,daemon=True).start()
client=BarkClient(f'http://127.0.0.1:{proxy.server_port}')
core=CoreClient(meta['rpc'],'second','ark')
ledger=Ledger(runtime/'caretaker.sqlite','regtest')
caretaker=ArkCaretaker(ledger,client,core,allow_regtest=True)
preview=None
try:
    snapshot=caretaker.snapshot();assert snapshot['vtxos'][0]['anchor_observation']
    height=rpc('getblockcount',[])+2
    first=caretaker.refresh([old['id']],height,10000)
    assert first['state']=='uncertain',first
    ledger.close();ledger=Ledger(runtime/'caretaker.sqlite','regtest')
    caretaker=ArkCaretaker(ledger,client,core,allow_regtest=True)
    restored=caretaker.refresh([old['id']],height,10000)
    assert restored['state'] in ['pending','chain_unconfirmed','confirmed'],restored
    assert stats['refresh_posts']==1
    mine(3)
    result=None
    for _ in range(40):
        bark('/wallet/sync',{})
        result=caretaker.reconcile(first['id'])
        if result['state']=='confirmed':break
        mine(2);time.sleep(1)
    assert result['state']=='confirmed',result
    assert stats=={'refresh_posts':1,'dropped_replies':1},stats
    assert result['result']['successors'][0]['expiry_height']>old['expiry_height']
    # Real successor funding reorg must revoke the desk's confirmed observation.
    block=result['result']['anchors'][0]['block_hash']
    rpc('invalidateblock',[block])
    reorg=caretaker.reconcile(first['id'])
    assert reorg['state']=='chain_unconfirmed',reorg
    rpc('reconsiderblock',[block]);mine(2)
    result=caretaker.reconcile(first['id']);assert result['state']=='confirmed'
    report={'status':'passed','tested_at':datetime.now(timezone.utc).isoformat(),
            'network':'isolated regtest','bark_version':'0.8.1','core_version':'31.0',
            'board_amount_sats':500000,'input_vtxo':old['id'],'successor_vtxos':[v['id'] for v in result['result']['successors']],
            'input_expiry_height':old['expiry_height'],'successor_expiry_heights':[v['expiry_height'] for v in result['result']['successors']],
            'fee_sats':result['result']['actual_fee_sats'],'desk_restart_recovery':True,'successor_reorg_detected':True,
            **stats,'evidence_level':result['result']['evidence_level'],
            'limits':['Regtest execution only; REST API has no signing-time fee cap.','Ark signature and ownership validation is performed by Bark, not independently by this Python desk.','No Cashu-to-Ark melt or presigned exit broadcast in this test.']}
    Path(args.report).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)
    desk=Desk('regtest',ledger,core=core,config={'bark_url':client.http.base,'ark_regtest_execution':True})
    preview=make_server(desk,0);threading.Thread(target=preview.serve_forever,daemon=True).start()
    (runtime/'preview.json').write_text(json.dumps({'url':f'http://127.0.0.1:{preview.server_port}'}))
    # Optional browser QA attaches while this process retains its SQLite ledger.
    if (runtime/'KEEP_PREVIEW').exists():
        print('Ark preview ready',flush=True)
        while not (runtime/'STOP_PREVIEW').exists():time.sleep(1)
finally:
    if preview:preview.shutdown();preview.server_close()
    proxy.shutdown();proxy.server_close();ledger.close()
