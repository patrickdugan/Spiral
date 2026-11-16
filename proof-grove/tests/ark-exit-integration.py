"""Exit saved regtest VTXOs with the Ark server stopped and wallet paused.

Requires an owned stack created by run-ark-stack.py and its completed refresh
test. Uses valueless coins only. Claims with the owner's wallet after the
independent broadcaster has finished the saved transaction waves.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from proofdesk.adapters import CoreClient,BarkClient
from proofdesk.ark import ArkCaretaker
from proofdesk.domain import Ledger,Refused,canonical,digest
from proofdesk.exits import ExitRecovery,sats

parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stack',required=True)
parser.add_argument('--resume',action='store_true',help='Resume the exact saved bundle after a setup/test failure')
parser.add_argument('--report',default=str(ROOT/'docs/ark-exit-integration.json'))
parser.add_argument('--expected-vtxo',help='Require this exact recipient successor before any exit signing')
args=parser.parse_args();meta=json.loads(Path(args.stack).read_text());runtime=Path(meta['runtime'])
if not re.fullmatch(r'pgark-[0-9a-f]{12}',meta['name']):raise SystemExit('Owned regtest stack required')
server=meta['name']+'-server'
record=json.loads(subprocess.check_output(['docker','inspect',server]))[0]
if record['Config']['Labels'].get('proof-grove.ark')!=meta['name'][6:]:raise SystemExit('Test ownership mismatch')
core=CoreClient(meta['rpc'],'second','ark')
if core.rpc('getblockchaininfo',[])['chain']!='regtest':raise SystemExit('Regtest required')
auth=Path(meta['auth_file']).read_text().strip();bark=BarkClient(meta['bark'],auth)
def wallet(path,body=None):
    req=urllib.request.Request(meta['bark']+'/api/v1'+path,data=canonical(body) if body is not None else None,
                               headers={'Content-Type':'application/json','Authorization':'Bearer '+auth})
    with urllib.request.urlopen(req,timeout=60) as r:raw=r.read()
    return json.loads(raw) if raw else None
def rpc(method,params,miner=False):
    req=urllib.request.Request(meta['rpc']+('/wallet/proof-grove-ark' if miner else ''),data=canonical({'jsonrpc':'2.0','id':'pg-test','method':method,'params':params}),headers={'Content-Type':'application/json',**core.http.headers})
    r=json.load(urllib.request.urlopen(req,timeout=15))
    if r.get('error'):raise RuntimeError(str(r['error']))
    return r['result']
mining=rpc('getnewaddress',[],True)
def mine(n=2):return rpc('generatetoaddress',[n,mining])
owner=Ledger(runtime/'exit-owner.sqlite','regtest');caretaker=ArkCaretaker(owner,bark,core,allow_regtest=True)
recovery=ExitRecovery(owner,core)
if args.resume:
    records=recovery.records()
    if len(records)!=1:raise SystemExit('Expected exactly one previously saved owner bundle')
    identifier=records[0]['id'];body=recovery.bundle(identifier)
    prepared={'id':identifier,**records[0]['observation']};vtxos=[v['id'] for v in body['vtxos']]
else:
    if recovery.records():raise SystemExit('Use a fresh stack, or --resume for its exact saved bundle')
    vtxos=[v['id'] for v in caretaker.snapshot()['vtxos'] if v['state']['type']=='spendable']
    if len(vtxos)!=1:raise SystemExit('Expected one fresh successor VTXO')
    if args.expected_vtxo and vtxos!=[args.expected_vtxo]:raise SystemExit('Recipient successor does not match the withdrawal')
    prepared=recovery.prepare(caretaker,vtxos,5,25000);identifier=prepared['id'];body=recovery.bundle(identifier)
    assert recovery.prepare(caretaker,vtxos,5,25000)['id']==identifier
destination=wallet('/onchain/addresses/next',{})['address']
destination_script=core.rpc('validateaddress',[destination])['scriptPubKey']
env=os.environ|{'PG_EXIT_RPC_PASSWORD':'ark'}
owner_config=runtime/'exit-owner.local.json'
owner_config.write_text(json.dumps({'mode':'regtest','database':'exit-owner.sqlite','core':{'url':meta['rpc'],'username':'second','password_env':'PG_EXIT_RPC_PASSWORD'}}))
exported=runtime/'private-recovery.json'
def cli(command,config,*extra):
    p=subprocess.run([sys.executable,'-m','proofdesk',command,'--config',str(config),*extra],cwd=ROOT,env=env,text=True,capture_output=True,check=True)
    return json.loads(p.stdout)
if not args.resume or not exported.exists():cli('exit-export',owner_config,'--id',identifier,'--output',str(exported))
owner.close()
assert digest(json.loads(exported.read_text()))==identifier
# The daemon belongs to this stack. Older scratch metadata omitted its PID.
wallet_dir=str(Path(meta['auth_file']).parent)
pids=[]
for p in Path('/proc').iterdir():
    if not p.name.isdigit():continue
    try:argv=(p/'cmdline').read_bytes().split(b'\0')
    except OSError:continue
    if b'--datadir' in argv and wallet_dir.encode() in argv and b'barkd-0.8.1-linux-x86_64' in argv[0]:pids.append(int(p.name))
if len(pids)!=1:raise SystemExit('Exact owned wallet process not found')
pid=pids[0];paused=False;proxy=None
stats={'submit_posts':0,'dropped_replies':0}
try:
    os.kill(pid,signal.SIGSTOP);paused=True
    subprocess.run(['docker','stop','--time','10',server],check=True,capture_output=True)
    assert json.loads(subprocess.check_output(['docker','inspect',server]))[0]['State']['Running'] is False
    print('Ark server stopped; owner wallet paused',flush=True)
    # A witness change keeps txid and fees unchanged, but Core must reject it.
    corrupted=deepcopy(body);child=corrupted['plan']['waves'][0]['packages'][0]['child']
    decoded=core.rpc('decoderawtransaction',[child['tx']])
    signature=next(item for vin in decoded['vin'] for item in vin.get('txinwitness',[]) if len(item) in (128,130))
    raw=bytearray.fromhex(child['tx']);needle=bytes.fromhex(signature)
    assert raw.count(needle)==1
    raw[raw.index(needle)+4]^=1;child['tx']=raw.hex()
    invalid_ledger=Ledger(runtime/'exit-invalid.sqlite','regtest');invalid=ExitRecovery(invalid_ledger,core,broadcaster=True)
    wrong=invalid.store(corrupted)['id'];rejection=invalid.advance(wrong,broadcast=True)
    assert rejection['state']=='package_rejected',rejection
    parent=body['plan']['waves'][0]['packages'][0]['exit']['txid']
    try:core.rpc('getrawtransaction',[parent,True]);raise AssertionError('Invalid child left an accepted parent')
    except Refused:pass
    invalid_ledger.close()
    print('Core rejected altered witness without accepting the zero-fee parent',flush=True)
    # A miner can confirm a valid zero-fee parent without its CPFP child.
    # Recover that partial state by submitting only the still-missing child.
    parent_raw=body['plan']['waves'][0]['packages'][0]['exit']['tx']
    rpc('generateblock',[mining,[parent_raw]])
    assert core.rpc('getrawtransaction',[parent,True])['confirmations']>=1
    class Proxy(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            raw=self.rfile.read(int(self.headers.get('Content-Length','0')));packet=json.loads(raw)
            req=urllib.request.Request(meta['rpc'],data=raw,headers={'Content-Type':'application/json',**core.http.headers})
            with urllib.request.urlopen(req,timeout=30) as r:response=r.read();status=r.status
            if packet['method']=='submitpackage':
                stats['submit_posts']+=1
                if stats['submit_posts']==1 and json.loads(response).get('result',{}).get('package_msg')=='success':
                    stats['dropped_replies']+=1;self.close_connection=True
                    self.connection.shutdown(socket.SHUT_RDWR);self.connection.close();return
            self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(response)));self.end_headers();self.wfile.write(response)
    proxy=ThreadingHTTPServer(('127.0.0.1',0),Proxy);threading.Thread(target=proxy.serve_forever,daemon=True).start()
    config=runtime/'exit-broadcaster.local.json'
    config.write_text(json.dumps({'mode':'regtest','database':'exit-broadcaster.sqlite','ark_regtest_exit_broadcast':True,
                                  'core':{'url':f'http://127.0.0.1:{proxy.server_port}','username':'second','password_env':'PG_EXIT_RPC_PASSWORD'}}))
    assert 'bark_url' not in json.loads(config.read_text())
    cli('exit-import',config,'--bundle',str(exported),'--expected-id',identifier)
    first=cli('exit-advance',config,'--id',identifier,'--broadcast');assert first['state']=='submission_uncertain',first
    second=cli('exit-advance',config,'--id',identifier,'--broadcast');assert second['state']=='awaiting_confirmations',second
    assert stats['submit_posts']==1 and stats['dropped_replies']==1
    # A separate watcher process carries the remaining waves and CSV clock.
    with (runtime/'exit-watcher.log').open('wb') as log:
        watcher=subprocess.Popen([sys.executable,'-m','proofdesk','exit-watch','--config',str(config),'--id',identifier,'--broadcast','--interval','1'],cwd=ROOT,env=env,stdout=log,stderr=log)
        try:
            deadline=time.monotonic()+240;mined_waves=set()
            while watcher.poll() is None and time.monotonic()<deadline:
                with sqlite3.connect(runtime/'exit-broadcaster.sqlite') as db:
                    state,raw=db.execute('SELECT state,observation FROM ark_exits WHERE id=?',(identifier,)).fetchone()
                observation=json.loads(raw) if raw else {}
                if state=='awaiting_confirmations' and observation['wave'] not in mined_waves:
                    mine(2);mined_waves.add(observation['wave'])
                elif state=='exit_confirmed':
                    needed=max(t['claim_height'] for t in observation['targets'])-rpc('getblockcount',[])
                    if needed>0:mine(needed)
                time.sleep(1)
            assert watcher.wait(timeout=10)==0,'Independent watcher failed; inspect its runtime log'
        finally:
            if watcher.poll() is None:watcher.terminate();watcher.wait(timeout=10)
    result=cli('exit-advance',config,'--id',identifier)
    assert result['state']=='claim_ready',result
    assert stats['submit_posts']==sum(len(w['packages']) for w in body['plan']['waves']),stats
    # Reopening the independent broadcaster must recheck a formerly confirmed wave.
    block=core.rpc('getrawtransaction',[parent,True])['blockhash'];rpc('invalidateblock',[block])
    reorg=cli('exit-advance',config,'--id',identifier);assert reorg['state']!='claim_ready',reorg
    rpc('reconsiderblock',[block]);mine(2)
    assert cli('exit-advance',config,'--id',identifier)['state']=='claim_ready'
    os.kill(pid,signal.SIGCONT);paused=False
    wallet('/exits/start/vtxos',{'vtxos':vtxos})
    for _ in range(15):
        wallet('/exits/progress',{'wait':False})
        status=wallet('/exits/status/vtxo/'+vtxos[0])
        if status['state']['type']=='claimable':break
        mine(2);time.sleep(1)
    assert status['state']['type']=='claimable',status
    wallet('/exits/claim/vtxos',{'vtxos':vtxos,'destination':destination,'fee_rate':5000})
    funding,index=vtxos[0].split(':')
    claims=[tx for txid in rpc('getrawmempool',[]) for tx in [rpc('getrawtransaction',[txid,True])]
            if any(v.get('txid')==funding and v.get('vout')==int(index) for v in tx['vin'])]
    assert len(claims)==1,'Expected one owner claim transaction in Core'
    claim_id=claims[0]['txid']
    mine(2)
    assert core.rpc('gettxout',[funding,int(index),True]) is None
    # Verify the confirmed owner claim, its destination and actual fee directly in Core.
    claim=rpc('getrawtransaction',[claim_id,True]);assert claim['confirmations']>=2
    assert len(claim['vout'])==1 and claim['vout'][0]['scriptPubKey']['hex']==destination_script
    claimed_sats=sats(claim['vout'][0]['value'])
    input_sats=sum(sats(rpc('getrawtransaction',[vin['txid'],True])['vout'][vin['vout']]['value']) for vin in claim['vin'])
    claim_fee=input_sats-claimed_sats;assert 0<claim_fee<25000
    for _ in range(15):
        wallet('/exits/progress',{'wait':False})
        status=wallet('/exits/status/vtxo/'+vtxos[0])
        if status['state']['type']=='claimed':break
        mine(2);time.sleep(1)
    assert status['state']['type']=='claimed',status
    (runtime/'claim-status.json').write_text(json.dumps(status,indent=2))
    report={'status':'passed','tested_at':datetime.now(timezone.utc).isoformat(),'network':'isolated regtest',
            'input_vtxos':vtxos,'input_value_sats':sum(v['amount_sat'] for v in body['vtxos']),
            'bundle_id':identifier,'waves':len(body['plan']['waves']),'saved_cpfp_fee_sats':prepared['fee_sats'],
            'ark_server_offline':True,'owner_wallet_paused_during_broadcast':True,'independent_broadcaster_has_no_bark_config':True,
            'cli_export_import':True,'independent_watcher_process':True,'preconfirmed_parent_missing_child_recovered':True,
            'altered_witness_rejected_by_core':True,'invalid_package_parent_not_accepted':True,
            'lost_submission_reply_recovered_after_process_restart':True,'confirmed_wave_reorg_detected':True,
            **stats,'owner_claim_state':status['state']['type'],'owner_claim_txid':claim_id,
            'owner_destination_verified_in_core':True,'owner_claim_value_sats':claimed_sats,'owner_claim_fee_sats':claim_fee,
            'limits':['Regtest only.','CPFP funds are not reserved by Bark and can be spent elsewhere.','Final owner claim fee is additional to the saved CPFP budget.']}
    Path(args.report).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)
    if (runtime/'KEEP_EXIT_PREVIEW').exists():
        from proofdesk.server import Desk,make_server
        preview_ledger=Ledger(runtime/'exit-broadcaster.sqlite','regtest')
        desk=Desk('regtest',preview_ledger,core=core)
        preview=make_server(desk,0);threading.Thread(target=preview.serve_forever,daemon=True).start()
        (runtime/'exit-preview.json').write_text(json.dumps({'url':f'http://127.0.0.1:{preview.server_port}','bundle_id':identifier}))
        print('Independent recovery preview ready',flush=True)
        try:
            while not (runtime/'STOP_PREVIEW').exists():time.sleep(1)
        finally:preview.shutdown();preview.server_close();preview_ledger.close()
finally:
    if paused:os.kill(pid,signal.SIGCONT)
    if proxy:proxy.shutdown();proxy.server_close()
