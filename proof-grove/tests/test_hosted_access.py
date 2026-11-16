import base64
from dataclasses import replace
import json
import threading
import unittest
from unittest.mock import Mock
import urllib.error
import urllib.request

from proofdesk.access import HostedAccess
from proofdesk.domain import Refused
from proofdesk.demo import sample
from proofdesk.server import Desk,make_server

TOKEN='a'*43
ORIGIN='https://patrickdugan.github.io'


class HostedAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.desk=Desk('regtest')
        cls.server=make_server(cls.desk,0,access=HostedAccess(TOKEN,(ORIGIN,),('api.example.com',)))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(5)

    def request(self,path,body=None,headers=None,method=None):
        values={'Origin':ORIGIN,'Content-Type':'application/json','X-Proof-Grove':'1',**(headers or {})}
        req=urllib.request.Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=values,method=method)
        try:
            with urllib.request.urlopen(req,timeout=5) as r:return r.status,r.read(),r.headers
        except urllib.error.HTTPError as r:return r.code,r.read(),r.headers

    def test_api_requires_operator_token_and_emits_no_credentials(self):
        for auth in ('','Bearer '+'b'*43):
            status,raw,_=self.request('/api/status',headers={'Authorization':auth})
            self.assertEqual(status,401);self.assertNotIn(TOKEN,raw.decode())
        status,raw,headers=self.request('/api/status',headers={'Authorization':'Bearer '+TOKEN})
        self.assertEqual(status,200);self.assertEqual(headers.get('Access-Control-Allow-Origin'),ORIGIN)
        self.assertEqual(json.loads(raw)['mode'],'regtest');self.assertNotIn(TOKEN,raw.decode())

    def test_wrong_origin_never_receives_cors_access(self):
        status,_,headers=self.request('/api/status',headers={'Authorization':'Bearer '+TOKEN,'Origin':'https://attacker.example'})
        self.assertNotEqual(status,200);self.assertIsNone(headers.get('Access-Control-Allow-Origin'))

    def test_preflight_is_allowed_without_token_but_cannot_authorize_a_request(self):
        status,raw,headers=self.request('/api/status',method='OPTIONS',headers={'Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'authorization,x-proof-grove'})
        self.assertEqual(status,204);self.assertEqual(raw,b'')
        self.assertEqual(headers['Access-Control-Allow-Origin'],ORIGIN)
        self.assertEqual(self.request('/api/status')[0],401)

    def test_private_exit_data_and_mutations_are_disabled_by_default(self):
        headers={'Authorization':'Bearer '+TOKEN}
        self.assertEqual(self.request('/api/ark/exits/bundle?id=x',headers=headers)[0],403)
        self.assertEqual(self.request('/api/ark/refresh',{},headers)[0],403)
        self.assertEqual(self.request('/api/proofs/check',{},headers)[0],400) # passes access; no verifier configured

    def test_fixture_backend_cannot_be_exposed_as_live(self):
        with self.assertRaisesRegex(Refused,'hosted_gateway_requires_connected_mode'):
            make_server(Desk(),0,access=HostedAccess(TOKEN,(ORIGIN,),('api.example.com',)))

    def test_chainstate_calls_the_configured_core_instead_of_fixture_data(self):
        core=Mock();core.rpc.return_value={'chain':'testnet4','blocks':161596,'headers':161596,'bestblockhash':'01'*32,'initialblockdownload':False}
        desk=Desk('live',core=core);value=desk.chainstate()
        core.rpc.assert_called_once_with('getblockchaininfo',[])
        self.assertEqual(value['blocks'],161596);self.assertEqual(value['evidence_level'],'bitcoin-core')

    def test_native_verification_without_current_chain_is_not_admission(self):
        _,evidence,_,_=sample();gate=Mock()
        gate.verify.return_value=replace(evidence,network='testnet4',kind='m16-verified')
        core=Mock();core.view_for.side_effect=Refused('core_not_ready')
        desk=Desk('live',gate=gate,core=core)
        result=desk.proof_check({'statement_base64':base64.b64encode(b'x'*1292).decode(),'proof_base64':base64.b64encode(b'proof').decode()})
        self.assertTrue(result['proof_verified']);self.assertFalse(result['payment_admitted'])
        self.assertEqual(result['chain_error'],'core_not_ready');self.assertIsNone(result['chain_observation'])
