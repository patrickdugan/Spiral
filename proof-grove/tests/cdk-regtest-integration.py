"""Real CDK + Bitcoin Core test, isolated regtest only; no external funding.

Requires a synced test mint using BDK and the task's regtest RPC, plus Node 24
and the pinned wallet dependencies. A proxy intentionally drops one mint reply.
"""
import argparse
import base64
import datetime
import hashlib
import http.client
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from proofdesk.adapters import CoreClient
from proofdesk.domain import Ledger
from proofdesk.server import Desk,make_server
import cdk_protected_fixture

parser=argparse.ArgumentParser()
parser.add_argument('--node',required=True)
parser.add_argument('--mint',default='http://127.0.0.1:28738')
parser.add_argument('--rpc',default='http://127.0.0.1:28743')
parser.add_argument('--browser-script',help='Optional connected browser QA script, run while the real test services are live')
parser.add_argument('--protected-handoff',type=Path)
parser.add_argument('--cooperative',action='store_true')
parser.add_argument('--batch-protected',action='store_true')
parser.add_argument('--collateral-nova',type=Path)
parser.add_argument('--collateral-m14',type=Path)
args=parser.parse_args()
if args.cooperative and not args.protected_handoff:parser.error('--cooperative requires --protected-handoff')
if args.batch_protected and not args.protected_handoff:parser.error('--batch-protected requires --protected-handoff')
collateral=bool(args.collateral_nova and args.collateral_m14)
if (args.collateral_nova or args.collateral_m14) and (not collateral or not args.protected_handoff or args.cooperative):
    parser.error('The collateral fixture requires the mint-offline holder fixture and both verifier executables')
os.environ['PATH']=str(Path(args.node).resolve().parent)+os.pathsep+os.environ['PATH']
runtime=ROOT/'.runtime'/('cdk-e2e-'+secrets.token_hex(5));runtime.mkdir(parents=True)
auth='Basic '+base64.b64encode(b'proofgrove:public-regtest-only').decode()

def rpc(method,params,*,wallet=False):
    if method not in ('getblockchaininfo','listwallets','createwallet','loadwallet','getnewaddress','generatetoaddress','sendtoaddress','getrawtransaction',
                       'getdescriptorinfo','importdescriptors','walletprocesspsbt','sendrawtransaction','getblockhash','testmempoolaccept','getblockheader',
                       'generateblock','invalidateblock','reconsiderblock','gettxoutproof','verifytxoutproof',
                       'decodescript','walletcreatefundedpsbt','getaddressinfo'):
        raise AssertionError('Unexpected test RPC')
    path=('/wallet/proof-grove-test-miner' if wallet is True else '/wallet/'+wallet) if wallet else ''
    body=json.dumps({'jsonrpc':'2.0','id':'pg-e2e','method':method,'params':params}).encode()
    req=urllib.request.Request(args.rpc+path,data=body,headers={'Authorization':auth,'Content-Type':'application/json'})
    try:
        result=json.load(urllib.request.urlopen(req,timeout=30))
    except urllib.error.HTTPError as error:
        result=json.load(error)
    if result.get('error'):raise RuntimeError(result['error']['message'])
    return result['result']

info=rpc('getblockchaininfo',[])
if info.get('chain')!='regtest':raise RuntimeError('Refusing to fund or mine outside isolated regtest')
if 'proof-grove-test-miner' not in rpc('listwallets',[]):
    try:rpc('createwallet',['proof-grove-test-miner'])
    except RuntimeError:rpc('loadwallet',['proof-grove-test-miner'])
mining_address=rpc('getnewaddress',[],wallet=True)
if info['blocks']<101:rpc('generatetoaddress',[101-info['blocks'],mining_address],wallet=True)

counts={'mint_requests':0,'restore_requests':0,'dropped_replies':0}
mint_url=urllib.parse.urlsplit(args.mint)
class Proxy(BaseHTTPRequestHandler):
    def log_message(self,*_):pass
    def forward(self):
        body=self.rfile.read(int(self.headers.get('Content-Length','0'))) if self.command=='POST' else None
        connection=http.client.HTTPConnection(mint_url.hostname,mint_url.port,timeout=30)
        connection.request(self.command,self.path,body=body,headers={'Content-Type':'application/json'})
        response=connection.getresponse();data=response.read();status=response.status;connection.close()
        if self.path=='/v1/mint/onchain' and self.command=='POST':
            counts['mint_requests']+=1
            if status==200 and counts['dropped_replies']==0:
                counts['dropped_replies']+=1;self.close_connection=True;return
        if self.path=='/v1/restore' and self.command=='POST':counts['restore_requests']+=1
        self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    do_GET=forward
    do_POST=forward

proxy=ThreadingHTTPServer(('127.0.0.1',0),Proxy)
proxy_thread=threading.Thread(target=proxy.serve_forever,daemon=True);proxy_thread.start()
ledger=Ledger(runtime/'desk.sqlite','regtest')
core=CoreClient(args.rpc,'proofgrove','public-regtest-only')
configuration={'cashu_url':f'http://127.0.0.1:{proxy.server_port}','min_confirmations':2}
if args.cooperative:configuration['protected_melt_wallet']=cdk_protected_fixture.MINT_WALLET
desk=Desk('regtest',ledger,None,core,configuration)
server=make_server(desk,0);server_thread=threading.Thread(target=server.serve_forever,daemon=True);server_thread.start()
environment=os.environ|{'PROOF_GROVE_WALLET_PASSWORD':'public-isolated-regtest-fixture-password',
                        'PG_TEST_RPC_PASSWORD':'public-regtest-only'}
common=['--vault',str(runtime/'wallet.sqlite'),'--mint',args.mint,'--desk',f'http://127.0.0.1:{server.server_port}']
def client(command,*options,expect_error=None):
    cp=subprocess.run([args.node,str(ROOT/'wallet/cli.mjs'),command,*common,*options],cwd=ROOT,env=environment,text=True,capture_output=True,timeout=120)
    try:result=json.loads(cp.stdout)
    except ValueError:raise AssertionError('Wallet did not produce JSON: '+cp.stderr[-600:]) from None
    if expect_error:
        if cp.returncode==0 or result.get('error')!=expect_error:raise AssertionError(f'Expected {expect_error}, got {result}')
    elif cp.returncode!=0:raise AssertionError('Wallet failed: '+str(result))
    return result

try:
    started=time.monotonic()
    deposit=client('deposit','--amount','25000');operation=deposit['operation_id']
    if args.protected_handoff:
        if not args.batch_protected:
            bundle, protected_args, funding_hex=cdk_protected_fixture.prepare(core,rpc,deposit,mining_address,runtime,args.rpc,args.cooperative)
        claim_command='protected-claim'
    else:
        protected_args=[]
        claim_command='claim'
    print(json.dumps({'stage':'quote-bound','amount_sats':deposit['amount_sats']}),flush=True)
    txid=rpc('sendtoaddress',[deposit['request'],0.00025],wallet=True)
    rpc('generatetoaddress',[2,mining_address],wallet=True)
    transaction=rpc('getrawtransaction',[txid,True])
    vout=next(o['n'] for o in transaction['vout'] if o.get('scriptPubKey',{}).get('address')==deposit['request'])
    quote_id=json.loads(ledger.db.execute('SELECT body FROM cashu_bindings WHERE intent_id=?',(deposit['intent_id'],)).fetchone()[0])['quote']
    # Poll a live quote, never assume that sleeping means the backend accepted it.
    for attempt in range(90):
        quote=desk.cashu.mint.raw_quote(quote_id)
        if quote.get('amount_paid')==25000:break
        time.sleep(1)
    else:raise AssertionError('CDK did not observe the mined deposit')
    print(json.dumps({'stage':'real-deposit-confirmed','confirmations':transaction['confirmations']}),flush=True)
    if args.batch_protected:
        draft=client('protected-draft','--id',operation)
        assert client('protected-draft','--id',operation)==draft and counts['mint_requests']==0
        client('claim','--id',operation,expect_error='Saved issuance protection cannot change')
        bundle, protected_args, funding_hex=cdk_protected_fixture.prepare(
            core,rpc,deposit,mining_address,runtime,args.rpc,args.cooperative,draft=draft)
    client(claim_command,'--id',operation,*protected_args,expect_error='payment_admission_required')
    assert counts['mint_requests']==0
    admission=client('admit-regtest','--id',operation,'--txid',txid,'--vout',str(vout))
    assert admission['evidence_level']=='core-regtest'
    client(claim_command,'--id',operation,*protected_args,expect_error='upstream_unavailable')
    assert desk.cashu.mint.raw_quote(quote_id)['amount_issued']==25000
    # A new CLI process decrypts the committed preview and uses NUT-09 recovery.
    recovered=client(claim_command,'--id',operation,*protected_args)
    assert recovered['dleq_verified'] is True and recovered['amount_sats']==25000
    repeated=client(claim_command,'--id',operation,*protected_args)
    assert repeated['idempotent_replay'] is True
    audit=client('protected-audit' if args.protected_handoff else 'audit','--id',operation)
    assert audit['amount_sats']==25000 and audit['proof_count']>0
    assert counts=={'mint_requests':1,'restore_requests':1,'dropped_replies':1},counts
    assert ledger.db.execute('SELECT count(*) FROM outbox').fetchone()[0]==1
    if args.browser_script:
        browser_env=os.environ|{'PROOF_GROVE_BASE':f'http://127.0.0.1:{server.server_port}',
                              'PROOF_GROVE_TEST_INTENT':deposit['intent_id'],'PROOF_GROVE_TEST_TXID':txid,'PROOF_GROVE_TEST_VOUT':str(vout)}
        subprocess.run([args.node,args.browser_script],cwd=ROOT,env=browser_env,check=True,timeout=180)
    report={'status':'passed','tested_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'network':'regtest','payment_evidence':'core-regtest','zk_verified':False,
            'mint':'CDK 0.18.3 with real BDK/Bitcoin Core backend','cashu_sdk':'4.13.1',
            'amount_sats':25000,'proof_count':audit['proof_count'],
            'dleq_verified':True,'wallet_restarted_between_attempts':True,'no_second_issuance':True,
            'counts':counts,'seconds':round(time.monotonic()-started,3),
            'meaning':'Actual regtest deposit issued real Cashu cryptographic proofs. Test coins have no monetary value. No Ark transfer or mainnet issuance tested.'}
    if args.protected_handoff:
        assert audit['bundle_id']==bundle['bundle_id']
        client('claim','--id',operation,expect_error='Saved issuance protection cannot change')
        client('export','--id',operation,'--output',str(runtime/'refused-token'),expect_error='No spendable token for this operation')
        certificate=args.protected_handoff/'issuance-certificate.json'
        legacy_melt=cdk_protected_fixture.check_normal_melt(args.node,ROOT,args.mint,runtime/'wallet.sqlite',operation,bundle,environment,certificate)
        portable=args.protected_handoff/'protected-issuance-receipt.json'
        offered_pin=client('protected-export-receipt','--id',operation,'--output',str(portable))
        trusted_pin=client('protected-pin-mint','--keysets',','.join(offered_pin['keyset_ids']))
        assert trusted_pin==offered_pin
        (args.protected_handoff/'protected-mint-pin.json').write_text(json.dumps(trusted_pin),encoding='utf-8')
        if args.batch_protected:
            (args.protected_handoff/'protected-bundle.json').write_text(json.dumps(bundle),encoding='utf-8')
        if args.cooperative:
            payout=cdk_protected_fixture.cooperate(core,rpc,client,operation,runtime,mining_address,bundle)
            independent=cdk_protected_fixture.verify_certificate(args.node,ROOT,certificate,bundle,legacy_melt)
            assert independent['proofs_sha256'] == audit['proofs_sha256'] and independent['changed_secret_rejected']
            payout.update(cdk_issuance=independent,legacy_cdk_melt=legacy_melt,funding_transaction=funding_hex)
            filename='cdk-protected-cooperative-report.json'
        else:
            payout=cdk_protected_fixture.finish(core,rpc,client,operation,args.mint,args.protected_handoff,
                mining_address,bundle,funding_hex,audit,legacy_melt,args.node,ROOT,certificate)
            filename='cdk-protected-report.json'
        payout['issuance_flow']=report
        (ROOT/'.runtime'/filename).write_text(json.dumps(payout,indent=2)+'\n')
        report=payout
        if collateral:
            from cashu_collateral_fixture import run as run_bond
            print(json.dumps({'stage':'holder-payout-confirmed','payout_sats':payout['payout']['sats']}),flush=True)
            target=args.protected_handoff/'collateral'
            report=run_bond(core,rpc,mining_address,payout,certificate,target,args.collateral_nova,args.collateral_m14)
            (target/'regtest-bond-receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    else:
        report['token_sha256']=audit['token_sha256']
        (ROOT/'.runtime/cdk-integration-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
finally:
    server.shutdown();server.server_close();server_thread.join(5)
    proxy.shutdown();proxy.server_close();proxy_thread.join(5)
    ledger.close()
