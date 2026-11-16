import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from proofdesk.ark import ArkCaretaker, refresh_fee
from proofdesk.domain import Ledger, Refused

OLD, NEW, ANCHOR = 'a'*64+':0', 'b'*64+':0', 'c'*64+':0'


class Core:
    def __init__(self):self.reorg=False;self.network='regtest'
    def rpc(self, method, params):
        if method=='getblockchaininfo':return {'chain':self.network,'blocks':110,'bestblockhash':'d'*64,'initialblockdownload':False}
        if method=='getrawtransaction':return {'txid':params[0],'confirmations':3,'blockhash':'e'*64,'vout':[{'n':0}]}
        if method=='getblockheader':return {'height':108}
        if method=='getblockhash':return ('f' if self.reorg else 'e')*64


class Bark:
    def __init__(self):
        self.http=SimpleNamespace(base='http://127.0.0.1:9999');self.calls=0;self.completed=False;self.drop=False;self.wallet='first';self.rounds=[]
        self.old={'id':OLD,'amount_sat':10000,'expiry_height':300,'chain_anchor':ANCHOR,'state':{'type':'spendable'}}
        self.new={'id':NEW,'amount_sat':9900,'expiry_height':400,'chain_anchor':ANCHOR,'state':{'type':'spendable'}}
    def read(self, resource):
        if resource=='identity':return {'address':self.wallet}
        if resource=='info':return {'network':'regtest','fees':{'refresh':{'base_fee_sat':100,'ppm_expiry_table':[]}}}
        if resource=='vtxos':return [self.new if self.completed else self.old]
        if resource=='rounds':return self.rounds
        if resource=='history':return [{'id':1,'status':'successful','subsystem':{'name':'bark.round','kind':'refresh'},'sent_to':[],'input_vtxos':[OLD],'output_vtxos':[NEW],'offchain_fee_sat':100}] if self.completed else []
    def vtxo(self, v):return self.new if v==NEW else self.old | {'state':{'type':'spent' if self.completed else 'spendable'}}
    def delegate_refresh(self, identifiers, height):
        self.calls+=1
        result={'id':1,'state':'delegated-pending','participation':{'inputs':identifiers,'outputs':[{'amount_sat':9900}]},'scheduled_height':height}
        self.rounds=[result]
        if self.drop:raise Refused('upstream_unavailable')
        return result


class ArkTests(unittest.TestCase):
    def setUp(self):
        Path('.runtime').mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir='.runtime');self.path=Path(self.tmp.name)/'ark.sqlite'
        self.ledger=Ledger(self.path,'regtest');self.core=Core();self.bark=Bark()
        self.caretaker=ArkCaretaker(self.ledger,self.bark,self.core,allow_regtest=True)
    def tearDown(self):self.ledger.close();self.tmp.cleanup()
    def test_drop_restart_reconcile_never_resends(self):
        self.bark.drop=True
        first=self.caretaker.refresh([OLD],120,100)
        self.assertEqual(first['state'],'uncertain')
        self.ledger.close();self.ledger=Ledger(self.path,'regtest')
        self.caretaker=ArkCaretaker(self.ledger,self.bark,self.core,allow_regtest=True)
        self.assertEqual(self.caretaker.refresh([OLD],120,100)['state'],'pending')
        self.bark.completed=True
        self.assertEqual(self.caretaker.refresh([OLD],120,100)['state'],'confirmed')
        self.assertEqual(self.bark.calls,1)
        self.core.reorg=True
        self.assertEqual(self.caretaker.reconcile(first['id'])['state'],'chain_unconfirmed')
    def test_crash_before_dispatch_is_uncertain(self):
        first=self.caretaker.refresh([OLD],120,100)
        self.bark.rounds=[]
        self.ledger.db.execute("UPDATE ark_operations SET state='dispatching',result=NULL")
        self.assertEqual(self.caretaker.refresh([OLD],120,100)['state'],'uncertain')
        self.assertEqual(self.bark.calls,1)
    def test_changed_request_or_wallet_refused(self):
        op=self.caretaker.refresh([OLD],120,100)
        with self.assertRaisesRegex(Refused,'ark_request_immutable'):self.caretaker.refresh([OLD],121,100)
        self.bark.wallet='other'
        with self.assertRaisesRegex(Refused,'ark_wallet_changed'):self.caretaker.reconcile(op['id'])
    def test_budget_before_dispatch_and_after_wallet_result(self):
        with self.assertRaisesRegex(Refused,'ark_fee_exceeds'):self.caretaker.refresh([OLD],120,99)
        self.assertEqual(self.bark.calls,0)
        op=self.caretaker.refresh([OLD],120,100);self.bark.completed=True;self.bark.new['amount_sat']=9800
        self.assertEqual(self.caretaker.reconcile(op['id'])['state'],'review_required')
    def test_mainnet_execution_always_refused(self):
        self.core.network='main'
        with self.assertRaisesRegex(Refused,'ark_production_signing_cap_required'):self.caretaker.refresh([OLD],120,100)
        self.assertEqual(self.bark.calls,0)
    def test_snapshot_reorg_and_duplicate_inputs(self):
        self.core.reorg=True
        self.assertEqual(self.caretaker.snapshot()['vtxos'][0]['anchor_error'],'ark_anchor_reorged')
        with self.assertRaisesRegex(Refused,'invalid_ark_inputs'):self.caretaker.refresh([OLD,OLD],120,100)
    def test_fractional_ppm_rounded_once(self):
        table={'base_fee_sat':1,'ppm_expiry_table':[{'expiry_blocks_threshold':0,'ppm':1},{'expiry_blocks_threshold':100,'ppm':1000}]}
        self.assertEqual(refresh_fee(table,[{'amount_sat':1,'expiry_height':10}]*2,0),2)
        self.assertEqual(refresh_fee(table,[{'amount_sat':10000,'expiry_height':100}],0),11)
        with self.assertRaises(Refused):refresh_fee({'base_fee_sat':0,'ppm_expiry_table':[{'expiry_blocks_threshold':1,'ppm':3},{'expiry_blocks_threshold':1,'ppm':2}]},[],0)


if __name__=='__main__':unittest.main()
