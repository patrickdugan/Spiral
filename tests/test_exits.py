from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from proofdesk.domain import Ledger, Refused, digest
from proofdesk.adapters import CoreRPCError
from proofdesk.exits import ExitRecovery, SCHEMA, validate, observed

A,F,P,C,Q,D = [c*64 for c in 'afbcde']
RAW={txid:f'{i:02x}'*20 for i,txid in enumerate([P,C,Q,D],1)}


def vin(txid,index=0):return {'txid':txid,'vout':index,'sequence':0xffffffff}
def out(value,index=0,script='5120'+'11'*32):return {'n':index,'value':value/100000000,'scriptPubKey':{'hex':script}}
TXS={A:{'txid':A,'vin':[],'vout':[out(10000)]}, F:{'txid':F,'vin':[],'vout':[out(20000)]},
     P:{'txid':P,'vin':[vin(A)],'vout':[out(10000),out(0,1,'51024e73')]},
     C:{'txid':C,'vin':[vin(P,1),vin(F)],'vout':[out(19500)]},
     Q:{'txid':Q,'vin':[vin(P)],'vout':[out(10000),out(0,1,'51024e73')]},
     D:{'txid':D,'vin':[vin(Q,1),vin(C)],'vout':[out(19000)]}}


def bundle():
    return {'schema':SCHEMA,'network':'regtest','max_fee_sats':1000,
            'vtxos':[{'id':Q+':0','chain_anchor':A+':0','amount_sat':10000,'expiry_height':1000,'exit_delta':6}],
            'plan':{'exits':[{'vtxo_id':Q+':0','status':{'type':'fully-signed'},'unsigned':[]}],
                    'waves':[{'in_mempool':[],'packages':[{'vtxo_id':Q+':0','exit':{'txid':p,'tx':RAW[p]},
                              'child':{'txid':c,'tx':RAW[c],'fee_info':{'total_fee_sat':500}}}]} for p,c in [(P,C),(Q,D)]]}}


class Core:
    def __init__(self):
        self.network='regtest';self.height=90;self.live={};self.submits=0;self.valid=True;self.drop=False;self.http=self
    def rpc(self,method,params):
        if method=='getblockchaininfo':return {'chain':self.network,'initialblockdownload':False,'blocks':self.height,'bestblockhash':f'{self.height:064x}'}
        if method=='decoderawtransaction':return deepcopy(TXS[next(k for k,v in RAW.items() if v==params[0])])
        if method=='getrawtransaction':
            txid=params[0]
            if txid not in [A,F] and txid not in self.live:raise CoreRPCError(-5)
            height=80 if txid in [A,F] else self.live[txid]
            return deepcopy(TXS[txid]) | ({'confirmations':self.height-height+1,'blockhash':f'{height:064x}'} if height is not None else {'confirmations':0})
        if method=='getblockheader':return {'height':int(params[0],16)}
        if method=='getblockhash':return f'{params[0]:064x}'
        if method=='gettxout':
            if any(v['txid']==params[0] and v['vout']==params[1] for txid in self.live for v in TXS[txid]['vin']):return None
            return TXS.get(params[0],{}).get('vout',[None])[params[1]] if params[0] in [A,F,*self.live] else None
        if method=='testmempoolaccept':return [{'allowed':self.valid} for _ in params[0]]
        if method=='getmempoolentry':
            if params[0] not in self.live or self.live[params[0]] is not None:raise CoreRPCError(-5)
            return {}
        raise AssertionError(method)
    def request(self,path,body):
        assert body['method']=='submitpackage'
        self.submits+=1
        for raw in body['params'][0]:self.live[next(k for k,v in RAW.items() if v==raw)]=None
        if self.drop:self.drop=False;raise Refused('upstream_unavailable')
        return {'result':{'package_msg':'success'}}
    def mine(self,n=2):
        self.height+=n
        for txid,height in self.live.items():
            if height is None:self.live[txid]=self.height-n+1


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        Path('.runtime').mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir='.runtime');self.path=Path(self.tmp.name)/'recovery.sqlite'
        self.ledger=Ledger(self.path,'regtest');self.core=Core();self.manager=ExitRecovery(self.ledger,self.core,broadcaster=True)
    def tearDown(self):self.ledger.close();self.tmp.cleanup()
    def test_offline_import_lost_reply_restart_and_wave_order(self):
        source=bundle();expected=digest(source)
        self.assertEqual(self.manager.store(source,expected)['id'],expected)
        self.assertEqual(self.manager.advance(expected)['state'],'ready')
        self.core.drop=True
        self.assertEqual(self.manager.advance(expected,broadcast=True)['state'],'submission_uncertain')
        self.ledger.close();self.ledger=Ledger(self.path,'regtest');self.manager=ExitRecovery(self.ledger,self.core,broadcaster=True)
        self.assertEqual(self.manager.advance(expected,broadcast=True)['state'],'awaiting_confirmations')
        self.assertEqual(self.core.submits,1)
        self.core.mine()
        self.assertEqual(self.manager.advance(expected,broadcast=True)['state'],'awaiting_confirmations')
        self.assertEqual(self.core.submits,2)
        self.core.mine()
        self.assertEqual(self.manager.advance(expected)['state'],'exit_confirmed')
        self.core.mine(6)
        self.assertEqual(self.manager.advance(expected)['state'],'claim_ready')
        self.core.live[P]=None
        self.assertEqual(self.manager.advance(expected)['state'],'awaiting_confirmations')
    def test_rejects_incomplete_budget_and_transaction_identity(self):
        for mutation,code in [('partial','exit_plan_incomplete'),('budget','exit_fee_budget_exceeded'),('id','exit_transaction_identity'),('fee','exit_fee_metadata_mismatch')]:
            body=bundle()
            if mutation=='partial':body['plan']['exits'][0]['status']['type']='partially-signed'
            if mutation=='budget':body['max_fee_sats']=999
            if mutation=='id':body['plan']['waves'][0]['packages'][0]['exit']['txid']='1'*64
            if mutation=='fee':body['plan']['waves'][0]['packages'][0]['child']['fee_info']['total_fee_sat']=499
            with self.subTest(mutation=mutation),self.assertRaisesRegex(Refused,code):validate(self.core,body)
    def test_core_signature_rejection_no_broadcast_and_mainnet_refusal(self):
        identifier=self.manager.store(bundle())['id'];self.core.valid=False
        self.assertEqual(self.manager.advance(identifier,broadcast=True)['state'],'not_eligible')
        self.assertEqual(self.core.submits,0)
        self.core.network='main'
        with self.assertRaisesRegex(Refused,'exit_regtest_required'):self.manager.advance(identifier,broadcast=True)
    def test_expected_hash_database_integrity_and_conflicting_package(self):
        with self.assertRaisesRegex(Refused,'exit_bundle_hash_mismatch'):self.manager.store(bundle(),'0'*64)
        identifier=self.manager.store(bundle())['id']
        different=bundle();different['max_fee_sats']=1001
        with self.assertRaisesRegex(Refused,'ark_input_already_reserved'):self.manager.store(different)
        self.ledger.db.execute("UPDATE ark_exits SET body='{}'")
        with self.assertRaisesRegex(Refused,'exit_bundle_hash_mismatch'):self.manager.bundle(identifier)
    def test_consumed_fee_input_never_broadcasts(self):
        identifier=self.manager.store(bundle())['id']
        old=self.core.rpc
        self.core.rpc=lambda method,params:None if method=='gettxout' and params[0]==F else old(method,params)
        self.assertEqual(self.manager.advance(identifier,broadcast=True)['state'],'inputs_unavailable')
        self.assertEqual(self.core.submits,0)
    def test_monitor_cannot_broadcast_without_explicit_configuration(self):
        identifier=self.manager.store(bundle())['id'];self.manager.broadcaster=False
        with self.assertRaisesRegex(Refused,'exit_broadcast_disabled'):self.manager.advance(identifier,broadcast=True)
    def test_prepare_retry_does_not_request_new_signatures(self):
        body=bundle();body['fee_rate_sat_per_vb']=5
        identifier=self.manager.store(body)['id']
        caretaker=SimpleNamespace(allow_regtest=True)
        result=self.manager.prepare(caretaker,[Q+':0'],5,1000)
        self.assertEqual(result['id'],identifier)
        self.assertTrue(result['idempotent_replay'])
        with self.assertRaisesRegex(Refused,'exit_request_immutable'):self.manager.prepare(caretaker,[Q+':0'],6,1000)
    def test_immature_timelock_waits_without_broadcast(self):
        identifier=self.manager.store(bundle())['id'];old=self.core.rpc
        self.core.rpc=lambda method,params:[{'allowed':False,'reject-reason':'non-BIP68-final'},{}] if method=='testmempoolaccept' else old(method,params)
        self.assertEqual(self.manager.advance(identifier,broadcast=True)['state'],'timelock_wait')
        self.assertEqual(self.core.submits,0)
    def test_known_orphan_and_unavailable_observer_are_distinct(self):
        self.core.live[P]=None
        self.assertEqual(observed(self.core,P)['confirmations'],0)
        old=self.core.rpc
        def orphan(method,params):
            if method=='getmempoolentry':raise CoreRPCError(-5)
            return old(method,params)
        self.core.rpc=orphan
        self.assertIsNone(observed(self.core,P))
        self.core.rpc=lambda *args:(_ for _ in ()).throw(Refused('upstream_unavailable'))
        with self.assertRaisesRegex(Refused,'upstream_unavailable'):observed(self.core,P)
    def test_preconfirmed_parent_submits_only_its_missing_child(self):
        identifier=self.manager.store(bundle())['id'];self.core.live[P]=88
        packets=[];send=self.core.request
        def capture(path,body):packets.append(body['params'][0]);return send(path,body)
        self.core.request=capture
        self.assertEqual(self.manager.advance(identifier,broadcast=True)['state'],'awaiting_confirmations')
        self.assertEqual(packets,[[RAW[C]]])
        self.assertEqual(self.core.submits,1)


if __name__=='__main__':unittest.main()
