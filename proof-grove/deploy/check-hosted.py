"""Owner-run live deployment check; spends only isolated, valueless regtest coins.

Run on the authorized VPS. Wallet secrets stay in a private, uniquely named QA
directory. The printed report contains public observations, never credentials.
Existing testnet4 Core and the persistent Ark/mint services are not stopped.
"""
from datetime import datetime, timezone
import base64
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request

BASE=Path('/opt/proof-grove');R=BASE/'regtest';APP=BASE/'current'
LIVE='https://proof-grove.170-75-168-145.sslip.io'
SANDBOX='https://proof-grove-regtest.170-75-168-145.sslip.io'


def http(base,path,body=None,headers=None):
    request=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type':'application/json',**(headers or {})})
    with urllib.request.urlopen(request,timeout=180) as response:raw=response.read()
    return json.loads(raw) if raw else None


def wait(check,label,seconds=180):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        value=check()
        if value:return value
        time.sleep(2)
    raise RuntimeError('Timed out: '+label)


def main():
    os.umask(0o077)
    settings=json.loads((R/'private.json').read_text())
    container=json.loads(subprocess.check_output(['sudo','-n','docker','inspect','proof-grove-regtest-core']))[0]
    assert container['Config']['Labels']['proof-grove.deployment']==settings['owner']
    token=(BASE/'config/operator.env').read_text().strip().split('=',1)[1]
    headers={'Authorization':'Bearer '+token,'X-Proof-Grove':'1'}
    core_headers={'Authorization':'Basic '+base64.b64encode(('proofgrove:'+settings['rpc_password']).encode()).decode()}
    def rpc(method,params,wallet=False):
        value=http('http://127.0.0.1:28743','/wallet/proof-grove-sandbox-miner' if wallet else '',
            {'jsonrpc':'2.0','id':'pg-live-qa','method':method,'params':params},core_headers)
        assert not value.get('error'),'Sandbox Core refused '+method
        return value['result']
    assert rpc('getblockchaininfo',[])['chain']=='regtest'
    def mine(n=2):rpc('generatetoaddress',[n,settings['mining_address']],True)
    def api(base,path,body=None):return http(base,path,body,headers)
    pid=lambda:subprocess.check_output(['systemctl','show','rehearsal-bitcoind.service','--property=MainPID','--value'],text=True).strip()
    before=pid()
    for base in (LIVE,SANDBOX):
        try:http(base,'/api/status')
        except urllib.error.HTTPError as error:assert error.code==401
        else:raise AssertionError('Unauthenticated API access')
    chain=api(LIVE,'/api/chainstate')
    proof=api(LIVE,'/api/proofs/recorded/check',{})
    assert chain['network']=='testnet4' and proof['proof_verified'] and proof['chain_observation']
    assert proof['payment_admitted'] is False
    status=api(SANDBOX,'/api/status')
    assert status['mode']=='regtest' and status['ark_wallet_configured']
    assert api(SANDBOX,'/api/chainstate')['network']=='regtest'
    api(SANDBOX,'/api/cashu/info')
    bearer=(R/'wallet/auth_token').read_text().strip()
    def bark(path,body=None):return http('http://127.0.0.1:28745','/api/v1'+path,body,{'Authorization':'Bearer '+bearer})
    destination=bark('/wallet/addresses/next',{})['address']
    baseline={v['id'] for v in bark('/wallet/vtxos')}
    qa=R/('qa-'+secrets.token_hex(6));qa.mkdir()
    password=secrets.token_urlsafe(32);(qa/'wallet-password').write_text(password)
    env=os.environ|{'PROOF_GROVE_WALLET_PASSWORD':password,'PROOF_GROVE_DESK_TOKEN':token}
    node='/home/ubuntu/node24/node-v24.22.1-linux-x64/bin/node'
    common=['--vault',str(qa/'wallet.sqlite'),'--mint','http://127.0.0.1:28738','--desk',SANDBOX]
    def client(command,*options):
        cp=subprocess.run([node,str(APP/'wallet/cli.mjs'),command,*common,*options],env=env,text=True,capture_output=True,timeout=180)
        result=json.loads(cp.stdout)
        if cp.returncode:raise RuntimeError('Wallet '+command+' refused: '+str(result.get('error','unknown')))
        return result
    deposit=client('deposit','--amount','25000');operation=deposit['operation_id']
    txid=rpc('sendtoaddress',[deposit['request'],0.00025],True);mine(2)
    transaction=rpc('getrawtransaction',[txid,True])
    vout=next(o['n'] for o in transaction['vout'] if o.get('scriptPubKey',{}).get('address')==deposit['request'])
    with sqlite3.connect('file:'+str(R/'api/desk.sqlite')+'?mode=ro',uri=True) as db:
        binding=json.loads(db.execute('SELECT body FROM cashu_bindings WHERE intent_id=?',(deposit['intent_id'],)).fetchone()[0])
    wait(lambda:http('http://127.0.0.1:28738','/v1/mint/quote/onchain/'+binding['quote']).get('amount_paid')==25000,'mint deposit observation')
    admission=client('admit-regtest','--id',operation,'--txid',txid,'--vout',str(vout))
    assert admission['accepted'] and admission['evidence_level']=='core-regtest'
    issued=client('claim','--id',operation)
    assert issued['amount_sats']==25000 and issued['dleq_verified']
    print(json.dumps({'stage':'real-cashu-issued','network':'regtest','amount_sats':25000}),flush=True)
    quote=client('ark-quote','--id',operation,'--destination',destination,'--amount','10000','--max-fee','0')
    payment=quote['payment_id'];client('ark-pay','--payment',payment)
    paid=client('ark-status','--payment',payment)
    assert paid['state']=='cashu_redeemed' and paid['change_sats']==15000 and paid['actual_fee_sats']==0
    assert client('audit','--id',operation)['amount_sats']==15000
    def received():
        bark('/wallet/sync',{})
        return [v for v in bark('/wallet/vtxos') if v['id'] not in baseline and v['state']['type']=='spendable']
    arrival=wait(received,'Bark recipient ownership')
    assert sum(v['amount_sat'] for v in arrival)==10000
    mine(8);bark('/wallet/sync',{})
    refresh=api(SANDBOX,'/api/ark/refresh',{'vtxos':[v['id'] for v in arrival],'height':rpc('getblockcount',[])+2,'max_fee_sats':1000})
    def confirmed():
        mine(2);bark('/wallet/sync',{})
        result=api(SANDBOX,'/api/ark/reconcile',{'id':refresh['id']})
        return result if result['state']=='confirmed' else None
    refresh=wait(confirmed,'Ark refresh and Core anchors')
    value=sum(v['amount_sat'] for v in refresh['result']['successors']);fee=refresh['result']['actual_fee_sats']
    assert value+fee==10000 and 0<=fee<=1000
    assert before==pid() and before!='0'
    report={'status':'passed','tested_at':datetime.now(timezone.utc).isoformat(),
        'https_origins':[LIVE,SANDBOX],'unauthenticated_status':401,'testnet4_height':chain['blocks'],
        'native_recorded_proof_verified':True,'historical_payment_admitted':False,'existing_testnet4_pid_unchanged':True,
        'cashu_ark_network':'regtest','deposit_sats':25000,'cashu_dleq_verified':True,
        'cashu_to_ark_sats':10000,'cashu_change_sats':15000,'melt_fee_sats':0,
        'recipient_vtxos':[v['id'] for v in arrival],'refresh_confirmed':True,'ark_after_refresh_sats':value,
        'refresh_fee_sats':fee,'anchors':refresh['result']['anchors'],'testnet4_payment_funded_regtest':False,
        'limits':['Valueless regtest payment uses Core evidence, not a new ZK proof.',
            'Historical testnet4 proof is verified separately and cannot mint here.',
            'Cashu custody and Ark expiry/operator liveness remain.']}
    (qa/'public-report.json').write_text(json.dumps(report,indent=2)+'\n')
    (BASE/'state/hosted-backend-check.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
