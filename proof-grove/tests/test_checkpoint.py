import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import Mock,patch

from proofdesk.adapters import CoreClient
from proofdesk.domain import Refused
from proofdesk.verifier import NativeFinalGate,parse_statement

ROOT=Path(__file__).resolve().parent.parent
RECORD=ROOT.parent/'in-and-out-burger/results/testnet4-bitvm3'


class CheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not RECORD.exists():raise unittest.SkipTest('Spiral public testnet4 record is not adjacent to this standalone checkout')
        cls.raw=(RECORD/'public.bin').read_bytes()
        cls.anchor=json.loads((RECORD/'statement-check.json').read_text())['anchor']

    def test_checkpoint_requires_explicit_matching_height_hash_and_chainwork(self):
        with self.assertRaisesRegex(Refused,'wrong_genesis'):parse_statement(self.raw)
        value=parse_statement(self.raw,self.anchor)
        self.assertEqual(value['network'],'testnet4');self.assertEqual(value['value_sats'],11600)
        for field,wrong in [('height',160001),('hash','0'*64),('chainwork','0x01')]:
            with self.subTest(field=field),self.assertRaisesRegex(Refused,'checkpoint_mismatch'):
                parse_statement(self.raw,{**self.anchor,field:wrong})

    def test_native_response_cannot_substitute_the_statement_digest(self):
        pins=json.loads((RECORD/'native-verify.json').read_text())['statement']
        policy={'network':'testnet4','anchor':self.anchor,'min_confirmations':6,'min_tip_chainwork':'0x01',
          'pins':{**{k:pins[k] for k in ('wrap_vk_sha256','program_vk_digest','recursion_vk_root')},
          'nova_vk_sha256':self.raw[1100:1132].hex(),'genesis_z0_sha256':hashlib.sha256(self.raw[12:556]).hexdigest()},
          'scripts':[{'script_sha256':self.raw[1260:1292].hex(),'min_value_sats':11600}]}
        gate=NativeFinalGate(['mock-native-final-verifier'],'a'*64,policy)
        result={'status':'verified','statement':{**pins,'committed_values_sha256':'b'*64}}
        with patch.object(gate,'_check_binary'),patch('proofdesk.verifier.subprocess.run',return_value=Mock(returncode=0,stdout=json.dumps(result))):
            with self.assertRaisesRegex(Refused,'gate_statement_mismatch'):gate.verify(self.raw,b'unit-test-proof-not-native')

    def test_anchor_is_rechecked_through_core(self):
        gate=object.__new__(NativeFinalGate);gate.policy={'anchor':self.anchor}
        core=Mock();core.rpc.side_effect=['f'*64]
        with self.assertRaisesRegex(Refused,'checkpoint_not_active'):gate.check_anchor(core)

    def test_rotating_core_cookie_is_reloaded_and_never_reported(self):
        import tempfile
        (ROOT/'.runtime').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'.runtime') as directory:
            cookie=Path(directory)/'.cookie';cookie.write_text('user:secret-one')
            core=CoreClient.from_config({'url':'http://127.0.0.1:48332','cookie_file':str(cookie)})
            with patch.object(core.http,'request',return_value={'result':{},'error':None}):
                core.rpc('getblockchaininfo',[]);first=core.http.headers['Authorization']
                cookie.write_text('user:secret-two');core.rpc('getblockchaininfo',[])
                self.assertNotEqual(first,core.http.headers['Authorization'])
                cookie.unlink()
                with self.assertRaisesRegex(Refused,'core_cookie_unavailable'):core.rpc('getblockchaininfo',[])
