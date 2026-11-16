import copy
import hashlib
import tempfile
import time
import unittest
from functools import partial
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

from proofdesk import demo
from proofdesk.cashu import CashuBridge
from proofdesk.domain import Ledger, Refused, Rules
from proofdesk.regtest import payment_from_regtest

POINT = '0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798'
SCRIPT = '0014'+'11'*20


class Mint:
    def __init__(self):
        self.quote={'quote':'private-test-quote','request':'bcrt1-test-address','pubkey':POINT,
                    'unit':'sat','method':'onchain','expiry':demo.NOW+3600,'amount_paid':0,'amount_issued':0}
        self.http=Mock(base='http://127.0.0.1:3338')
        self.http.request.side_effect=self.request
        self.posts=0;self.restores=0;self.stored=None;self.lose_reply=False;self.partial_restore=False
    def raw_quote(self,_):return copy.deepcopy(self.quote)
    def request(self,path,body):
        if path=='/v1/mint/onchain':
            self.posts+=1
            self.stored=copy.deepcopy(body['outputs'])
            self.quote['amount_issued']=sum(o['amount'] for o in self.stored)
            if self.lose_reply:raise Refused('upstream_unavailable')
            return {'signatures':[{'id':o['id'],'amount':o['amount'],'C_':POINT} for o in self.stored]}
        if path=='/v1/restore':
            self.restores+=1
            stored=(self.stored or [])[:1] if self.partial_restore else (self.stored or [])
            return {'outputs':stored,'signatures':[{'id':o['id'],'amount':o['amount'],'C_':POINT} for o in stored]}
        raise AssertionError(path)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.ledger=Ledger(':memory:','regtest');self.mint=Mint();self.core=Mock()
        self.core.rpc.side_effect=lambda method,params:{'chain':'regtest'} if method=='getblockchaininfo' else {'isvalid':True,'scriptPubKey':SCRIPT}
        self.signature=Mock(return_value=True)
        self.clock=Mock(return_value=demo.NOW)
        self.binding_signature=Mock(return_value=True)
        self.bridge=CashuBridge(self.ledger,self.mint,self.core,self.signature,self.clock,binding_verifier=self.binding_signature)
        self.bridge.bind=partial(self.bridge.bind,authorization='33'*64)
        self.bridge.issue=partial(self.bridge.issue,authorization='22'*64)
        self.binding=self.bridge.bind(self.mint.quote['quote'],POINT,25000,'regtest')
        self.id=self.binding['intent']['id']
        _,evidence,chain,rules=demo.sample()
        self.evidence=replace(evidence,kind='core-regtest',script_sha256=hashlib.sha256(bytes.fromhex(SCRIPT)).hexdigest())
        self.chain=replace(chain,source='bitcoin-core')
        self.rules=replace(rules,mode='regtest')
        self.core.view_for.return_value=self.chain
        denoms=[16384,8192,256,128,32,8]
        self.payload={'quote':self.mint.quote['quote'],'signature':'11'*64,
                      'outputs':[{'id':'0011223344556677','amount':a,'B_':'02'+f'{i+1:064x}'} for i,a in enumerate(denoms)]}

    def tearDown(self):self.ledger.close()
    def refuse(self,code,fn,*args):
        with self.assertRaises(Refused) as context:fn(*args)
        self.assertEqual(context.exception.code,code)
    def admit(self):
        self.ledger.prepare(self.id,self.evidence,self.chain,self.rules,demo.NOW)
        self.mint.quote['amount_paid']=25000

    def test_quote_binds_script_amount_owner_mint_and_is_idempotent(self):
        intent=self.ledger.intent(self.id)
        self.assertEqual(intent.beneficiary,'cashu-nut20:'+POINT)
        self.assertEqual(intent.script_sha256,hashlib.sha256(bytes.fromhex(SCRIPT)).hexdigest())
        self.assertTrue(self.bridge.bind(self.mint.quote['quote'],POINT,25000,'regtest')['idempotent_replay'])
        self.refuse('cashu_binding_immutable',self.bridge.bind,self.mint.quote['quote'],POINT,25001,'regtest')

    def test_no_signature_request_before_proof_admission(self):
        self.mint.quote['amount_paid']=25000
        self.refuse('payment_admission_required',self.bridge.issue,self.id,self.payload)
        self.assertEqual(self.mint.posts,0)

    def test_quote_registration_needs_the_wallet_owners_authorization(self):
        self.binding_signature.return_value=False
        self.refuse('binding_authorization_invalid',self.bridge.bind,self.mint.quote['quote'],POINT,25000,'regtest')

    def test_invalid_signature_cannot_lock_issuance(self):
        self.admit();self.signature.return_value=False
        self.refuse('issue_authorization_invalid',self.bridge.issue,self.id,self.payload)
        self.assertEqual(self.ledger.db.execute('SELECT count(*) FROM cashu_issuance').fetchone()[0],0)
        self.assertEqual(self.mint.posts,0)

    def test_success_stores_only_blinded_material_and_retries_same_result(self):
        self.admit();first=self.bridge.issue(self.id,self.payload);retry=self.bridge.issue(self.id,self.payload)
        self.assertEqual(first['state'],'blind-signatures-received')
        self.assertEqual(first['wallet_verification'],'required')
        self.assertEqual(first['signatures'],retry['signatures'])
        self.assertTrue(retry['idempotent_replay']);self.assertEqual(self.mint.posts,1)
        stored=self.ledger.db.execute('SELECT payload FROM cashu_issuance').fetchone()[0]
        self.assertNotIn('secret',stored);self.assertNotIn('privkey',stored)

    def test_lost_issuance_response_restores_identical_outputs_without_second_mint(self):
        self.admit();self.mint.lose_reply=True
        self.refuse('upstream_unavailable',self.bridge.issue,self.id,self.payload)
        self.assertEqual(self.ledger.db.execute('SELECT state FROM cashu_issuance').fetchone()[0],'reconcile')
        result=self.bridge.issue(self.id,self.payload)
        self.assertEqual(result['state'],'blind-signatures-received')
        self.assertEqual(self.mint.posts,1);self.assertEqual(self.mint.restores,1)

    def test_partial_restore_cannot_trigger_a_new_issuance(self):
        self.admit();self.mint.lose_reply=True
        self.refuse('upstream_unavailable',self.bridge.issue,self.id,self.payload)
        self.mint.partial_restore=True
        self.refuse('mint_restore_incomplete',self.bridge.issue,self.id,self.payload)
        self.assertEqual(self.mint.posts,1)

    def test_existing_issuance_cannot_change_blinded_outputs(self):
        self.admit();self.bridge.issue(self.id,self.payload)
        changed=copy.deepcopy(self.payload);changed['outputs'][0]['B_']='03'+'77'*32
        self.refuse('mint_outputs_immutable',self.bridge.issue,self.id,changed)
        self.assertEqual(self.mint.posts,1)

    def test_quote_substitution_and_unpaid_backend_fail_closed(self):
        self.admit();self.mint.quote['request']='another-address'
        self.refuse('cashu_quote_changed',self.bridge.issue,self.id,self.payload)
        self.mint.quote['request']='bcrt1-test-address';self.mint.quote['amount_paid']=0
        self.refuse('mint_payment_pending',self.bridge.issue,self.id,self.payload)
        self.assertEqual(self.mint.posts,0)

    def test_reorg_rechecked_before_calling_the_mint(self):
        self.admit();self.core.view_for.return_value=replace(self.chain,block_hash='22'*32)
        self.refuse('payment_reorged',self.bridge.issue,self.id,self.payload)
        self.assertEqual(self.mint.posts,0)

    def test_payment_expiry_does_not_take_away_previously_admitted_issuance(self):
        self.admit();now=self.ledger.intent(self.id).expires_at+1;self.clock.return_value=now
        self.core.view_for.return_value=replace(self.chain,observed_at=now)
        self.assertEqual(self.bridge.issue(self.id,self.payload)['state'],'blind-signatures-received')

    def test_eligible_payment_proof_can_arrive_after_the_quotes_payment_deadline(self):
        now=self.mint.quote['expiry']+1;self.clock.return_value=now
        self.mint.quote['amount_paid']=25000
        chain=replace(self.chain,observed_at=now);self.core.view_for.return_value=chain
        receipt=self.ledger.prepare(self.id,self.evidence,chain,self.rules,now)
        self.assertGreater(receipt['checked_at'],self.mint.quote['expiry'])
        self.assertEqual(self.bridge.issue(self.id,self.payload)['state'],'blind-signatures-received')

    def test_demo_namespace_cannot_enable_issuance(self):
        ledger=Ledger(':memory:','demo')
        try:self.refuse('real_admission_namespace_required',CashuBridge,ledger,self.mint,self.core)
        finally:ledger.close()

    def test_request_secret_fields_and_overissuance_are_rejected(self):
        for payload in ({**self.payload,'secret':'never-send'},
                        {**self.payload,'outputs':[{**self.payload['outputs'][0],'amount':32768}]}):
            with self.assertRaises(Refused):self.bridge.issue(self.id,payload)
        self.assertEqual(self.mint.posts,0)


class RegtestTests(unittest.TestCase):
    def test_regtest_source_cannot_accept_a_mainnet_node(self):
        core=Mock();core.rpc.return_value={'chain':'main','initialblockdownload':False}
        with self.assertRaises(Refused) as context:payment_from_regtest(core,'11'*32,0)
        self.assertEqual(context.exception.code,'isolated_regtest_required')

    def test_core_regtest_evidence_cannot_be_used_in_live_mode(self):
        intent,evidence,chain,rules=demo.sample()
        ledger=Ledger(':memory:','live')
        try:
            ledger.add_intent(intent)
            with self.assertRaises(Refused):ledger.prepare(intent.id,replace(evidence,kind='core-regtest'),replace(chain,source='bitcoin-core'),replace(rules,mode='live'),demo.NOW)
        finally:ledger.close()


if __name__=='__main__':unittest.main()
