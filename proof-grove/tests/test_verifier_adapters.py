import hashlib
import json
import struct
import subprocess
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from proofdesk import demo
from proofdesk.adapters import BarkClient, CashuClient, CoreClient, HTTP
from proofdesk.domain import Refused
from proofdesk.verifier import M16Gate, parse_statement, validate_policy

ROOT = Path(__file__).resolve().parent.parent


class VerifierTests(unittest.TestCase):
    def setUp(self):
        self.statement = (ROOT/'fixtures/m16-mainnet-statement.bin').read_bytes()
        self.policy = json.loads((ROOT/'config.example.json').read_text())['policy']
        self.parsed = parse_statement(self.statement)
        self.gate = M16Gate(['test-verifier'], 'a'*64, self.policy)
        self.accepted = {'status':'accepted', 'payment': {k:self.parsed[k] for k in ('txid','vout','value_sats','script_sha256','confirmations')}}

    def refusal(self, code, function, *args):
        with self.assertRaises(Refused) as context:
            function(*args)
        self.assertEqual(context.exception.code, code)

    def test_public_statement_fixture_has_documented_digest(self):
        provenance = json.loads((ROOT/'fixtures/provenance.json').read_text())
        self.assertEqual(hashlib.sha256(self.statement).hexdigest(), provenance['sha256'])
        self.assertEqual(self.parsed['value_sats'], 940000)
        self.assertEqual(self.parsed['tip_height'], 975072)
        self.assertEqual(self.parsed['confirmations'], 6)
        self.assertNotIn('kind', self.parsed)

    def test_rejects_truncation_trailing_bytes_and_chain_only_statements(self):
        for raw in (b'', self.statement[:-1], self.statement+b'\x00', self.statement[:1164]):
            self.refusal('statement_length', parse_statement, raw)

    def test_byte_order_and_malformed_pay1_state_and_confirmation(self):
        self.assertEqual(self.parsed['txid'], 'a652ab0cf381413ae854a86bb7e4784811b2d4158a65f26ff64a69eb3eb20045')
        for offset, byte, code in [(1164, 0, 'payment_record_magic'), (16, 1, 'statement_state_encoding'),
                                   (1208, 5, 'statement_inconsistent'), (0, 0, 'wrong_network')]:
            raw = bytearray(self.statement); raw[offset] = byte
            self.refusal(code, parse_statement, bytes(raw))

    def test_only_accepted_matching_external_result_yields_verified_evidence(self):
        process = Mock(returncode=0, stdout=json.dumps(self.accepted))
        with patch.object(self.gate, '_check_binary'), patch('proofdesk.verifier.subprocess.run', return_value=process) as command:
            evidence = self.gate.verify(self.statement, b'fake-proof-for-subprocess-contract-test')
        self.assertEqual(evidence.kind, 'm16-verified')
        self.assertIn('check', command.call_args.args[0])
        self.assertEqual(evidence.statement_sha256, hashlib.sha256(self.statement).hexdigest())
        # This test uses a mocked process, not a cryptographic verifier.

    def test_external_failure_malformed_stdout_and_payment_substitution(self):
        for process, code in [
            (Mock(returncode=1, stdout=json.dumps(self.accepted)), 'proof_rejected'),
            (Mock(returncode=0, stdout='not json'), 'gate_response_invalid'),
            (Mock(returncode=0, stdout=json.dumps({'status':'accepted','payment':{}})), 'gate_payment_mismatch'),
            (Mock(returncode=0, stdout=json.dumps({'status':'accepted','payment':{**self.accepted['payment'],'value_sats':940001}})), 'gate_payment_mismatch'),
        ]:
            with self.subTest(code=code), patch.object(self.gate,'_check_binary'), patch('proofdesk.verifier.subprocess.run',return_value=process):
                self.refusal(code,self.gate.verify,self.statement,b'proof')

    def test_verifier_timeout_is_fail_closed(self):
        with patch.object(self.gate,'_check_binary'), patch('proofdesk.verifier.subprocess.run',side_effect=subprocess.TimeoutExpired('gate',1)):
            self.refusal('verifier_unavailable',self.gate.verify,self.statement,b'proof')

    def test_no_proof_or_giant_proof_is_accepted(self):
        for proof in (b'', b'x'*(4*1024*1024+1)):
            self.refusal('artifact_size',self.gate.verify,self.statement,proof)

    def test_binary_pin_is_checked_before_running_proof(self):
        gate = M16Gate([str(ROOT/'web/app.js')], 'a'*64, self.policy)
        self.refusal('verifier_binary_mismatch',gate.verify,self.statement,b'proof')

    def test_policy_requires_all_pins_positive_chainwork_and_registered_script(self):
        for policy, code in [
            ({**self.policy,'pins':{}}, 'missing_verifier_pins'),
            ({**self.policy,'min_tip_chainwork':'0'}, 'invalid_integer'),
            ({**self.policy,'scripts':[]}, 'missing_registered_script'),
            ({**self.policy,'min_confirmations':False}, 'invalid_integer'),
        ]:
            self.refusal(code,validate_policy,policy)


class AdapterTests(unittest.TestCase):
    def test_core_verifies_payment_and_proof_tip_in_active_chain(self):
        evidence = demo.sample()[1]
        core = CoreClient('http://127.0.0.1:8332','user','not-a-secret-test-value')
        info = {'chain':'regtest','initialblockdownload':False,'bestblockhash':evidence.tip_hash,'blocks':evidence.tip_height}
        with patch.object(core,'rpc',side_effect=[info,evidence.block_hash,evidence.tip_hash,info]) as rpc:
            view = core.view_for(evidence)
        self.assertEqual(view.source,'bitcoin-core')
        self.assertEqual(rpc.call_args_list[2].args,('getblockhash',[evidence.tip_height]))

    def test_core_catches_reorg_fork_tip_change_and_initial_sync(self):
        e = demo.sample()[1]
        info={'chain':'regtest','initialblockdownload':False,'bestblockhash':e.tip_hash,'blocks':e.tip_height}
        core=CoreClient('http://localhost:8332','user','test')
        cases=[([{**info,'initialblockdownload':True}],'core_not_ready'),
               ([info,'wrong'],'payment_reorged'),([info,e.block_hash,'wrong'],'proof_fork'),
               ([info,e.block_hash,e.tip_hash,{**info,'bestblockhash':'new'}],'chain_changed_retry')]
        for responses,code in cases:
            with self.subTest(code=code),patch.object(core,'rpc',side_effect=responses),self.assertRaises(Refused) as context:
                core.view_for(e)
            self.assertEqual(context.exception.code,code)

    def test_core_cannot_send_a_transaction(self):
        core=CoreClient('http://127.0.0.1:8332','user','test')
        for method in ('sendrawtransaction','submitpackage','signrawtransactionwithwallet'):
            with self.assertRaises(Refused):
                core.rpc(method,['00'])

    def test_core_error_keeps_only_numeric_code(self):
        core=CoreClient('http://127.0.0.1:8332','user','test')
        with patch.object(core.http,'request',return_value={'result':None,'error':{'code':-5,'message':'sensitive upstream details'}}):
            with self.assertRaises(Refused) as context:core.rpc('getrawtransaction',['1'*64,True])
        self.assertEqual(context.exception.rpc_code,-5)
        self.assertNotIn('sensitive',str(context.exception))

    def test_plaintext_remote_credentials_and_url_userinfo_are_rejected(self):
        for url in ('http://example.com','https://user:pass@example.com','file:///tmp/data','https://example.com/?secret=1'):
            with self.assertRaises(Refused):
                HTTP(url)
        with self.assertRaises(Refused):
            BarkClient('https://example.com')

    def test_cashu_info_and_quotes_remain_operator_reports(self):
        mint=CashuClient('https://mint.example')
        with patch.object(mint.http,'request',return_value={'state':'PAID','amount_paid':1000,'amount_issued':0,'updated_at':10,'request':'private-invoice'}):
            result=mint.quote('arkoor','private quote')
        self.assertEqual(result['evidence_level'],'operator-report')
        self.assertNotIn('request',result)
        self.assertNotIn('quote',result)
        with self.assertRaises(Refused):
            mint.quote('../secrets','x')

    def test_bark_history_is_not_a_proof(self):
        bark=BarkClient('http://localhost:3000')
        with patch.object(bark.http,'request',return_value=[]):
            self.assertEqual(bark.history()['evidence_level'],'operator-report')


if __name__ == '__main__':
    unittest.main()
