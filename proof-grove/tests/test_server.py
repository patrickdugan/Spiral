import json
import threading
import unittest
import urllib.error
import urllib.request

from proofdesk.server import Desk, make_server


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=make_server(Desk(),0)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(5)

    def request(self,path,body=None,headers=None):
        defaults={'Content-Type':'application/json','X-Proof-Grove':'1'}
        defaults.update(headers or {})
        req=urllib.request.Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=defaults)
        try:
            with urllib.request.urlopen(req,timeout=5) as response:
                return response.status,response.read(),response.headers
        except urllib.error.HTTPError as error:
            return error.code,error.read(),error.headers

    def test_all_static_assets_and_apis_are_available(self):
        for path in ('/','/styles.css','/app.js','/icon.svg','/api/status','/api/sources','/api/cases','/api/vtxos','/api/receipts','/api/archive/manifest'):
            with self.subTest(path=path):
                status,body,headers=self.request(path)
                self.assertEqual(status,200)
                self.assertGreater(len(body),0)
                self.assertEqual(headers.get('Cache-Control'),'no-store')
                self.assertIn("frame-ancestors 'none'",headers.get('Content-Security-Policy'))

    def test_can_run_accept_and_reject_cases_through_the_real_http_api(self):
        for case,accepted in [('cashu',True),('replay',False),('wrong-amount',False)]:
            status,body,_=self.request('/api/run',{'case':case})
            self.assertEqual(status,200)
            self.assertEqual(json.loads(body)['decision']['accepted'],accepted)

    def test_demo_server_cannot_verify_live_evidence(self):
        status,body,_=self.request('/api/verify',{'intent_id':'invented','evidence_level':'m16-verified'})
        self.assertEqual(status,400)
        self.assertEqual(json.loads(body)['error'],'live_verifier_not_configured')

    def test_blocks_cross_origin_posts_dns_rebinding_and_missing_custom_header(self):
        for headers in ({'Origin':'https://attacker.example'},{'Host':'attacker.example'},{'X-Proof-Grove':''}):
            status,_,_=self.request('/api/run',{'case':'cashu'},headers)
            self.assertEqual(status,400)

    def test_no_arbitrary_files_or_credentials_are_served(self):
        for path in ('/config.local.json','/config.example.json','/../proofdesk/server.py','/.git/config'):
            self.assertEqual(self.request(path)[0],404)

    def test_export_is_redacted_and_not_a_storage_deal(self):
        self.request('/api/run',{'case':'cashu'})
        status,raw,_=self.request('/api/archive')
        self.assertEqual(status,200)
        parsed=json.loads(raw)
        self.assertIn('no Filecoin deal',parsed['storage'])
        self.assertNotIn('beneficiary',parsed['receipts'][0])

    def test_plan_api_never_executes(self):
        status,raw,_=self.request('/api/plan',{'vtxo':{'id':'x','value_sats':1000,'expiry_height':2000,'exit_budget_blocks':24},'tip_height':1000})
        self.assertEqual(status,200)
        self.assertFalse(json.loads(raw)['executed'])

    def test_unconfigured_ark_cannot_execute(self):
        for path in ('/api/ark/refresh','/api/ark/reconcile'):
            status,raw,_=self.request(path,{})
            self.assertEqual(status,400)
            self.assertEqual(json.loads(raw)['error'],'ark_not_configured')
        self.assertEqual(json.loads(self.request('/api/ark/wallet')[1])['evidence_level'],'not-connected')
        self.assertEqual(json.loads(self.request('/api/ark/operations')[1]),{'operations':[]})
        for path in ('/api/ark/exits/prepare','/api/ark/exits/advance'):
            status,raw,_=self.request(path,{})
            self.assertEqual(status,400)
            self.assertEqual(json.loads(raw)['error'],'exit_not_configured')
        self.assertEqual(json.loads(self.request('/api/ark/exits')[1]),{'exits':[],'broadcast_enabled':False})
        self.assertEqual(self.request('/api/ark/exits/bundle?id=unknown')[0],400)


if __name__ == '__main__':
    unittest.main()
