"""Adversarial checks for Script-compiled full-trace AIR proof.

Proof opens all four rows: it is not a scalable STARK or a Nova SNARK.
"""
import unittest
from dataclasses import replace
from hashlib import sha256
from stark_trace import *

class AirScriptTests(unittest.TestCase):
    def setUp(self):
        self.tx,self.script,self.control,self.wit=fixture(3,0)

    def check(self,tx=None,wit=None,script=None,control=None,**kwargs):
        return run(self.tx if tx is None else tx,
                   self.script if script is None else script,
                   self.control if control is None else control,
                   self.wit if wit is None else wit,**kwargs)

    def refuse(self,**kwargs):
        with self.assertRaises(K.Reject): self.check(**kwargs)

    def test_valid_initial_trace(self): self.assertTrue(self.check())
    def test_valid_second_recipient_and_trace(self):
        tx,sc,c,wit=fixture(5,1)
        self.assertEqual(self.tx.inputs[0],tx.inputs[0])
        self.assertEqual(self.script,sc)
        self.assertTrue(run(tx,sc,c,wit))

    def test_script_is_small(self): self.assertLess(len(self.script),500)
    def test_proof_trace_committed_in_output(self):
        self.assertEqual(self.tx.outputs[1].script,b"\x6a\x20"+K.H(bytes((3,5,7,9))))

    def test_zero_row_rejected(self):
        wit=list(self.wit);wit[-1]=b""
        self.refuse(wit=wit)

    def test_bad_field_range_rejected(self):
        wit=list(self.wit);wit[-2]=b"\x11"
        self.refuse(wit=wit)

    def test_wrong_transition_rejected(self):
        wit=list(self.wit);wit[-2]=b"\x08"
        self.refuse(wit=wit)

    def test_all_trace_rows_changed_but_output_unchanged_rejected(self):
        wit=list(self.wit);wit[-4:]=list(bytes([x]) for x in (4,6,8,10))
        self.refuse(wit=wit)

    def test_valid_alternate_trace_with_transaction_updated(self):
        tx,sc,c,wit=fixture(5,1)
        self.assertTrue(run(tx,sc,c,wit))
        self.assertNotEqual(self.tx.outputs[1],tx.outputs[1])

    def test_recipient_flip(self):
        outs=(replace(self.tx.outputs[0],script=b"\x51\x20"+K.PUBKEYS[1]),self.tx.outputs[1])
        self.refuse(tx=replace(self.tx,outputs=outs))

    def test_outside_allowlist(self):
        outs=(replace(self.tx.outputs[0],script=b"\x51\x20"+bytes(32)),self.tx.outputs[1])
        self.refuse(tx=replace(self.tx,outputs=outs))

    def test_fee_theft(self):
        outs=(replace(self.tx.outputs[0],value=948399),self.tx.outputs[1])
        self.refuse(tx=replace(self.tx,outputs=outs))

    def test_opreturn_digest_replaced(self):
        outs=(self.tx.outputs[0],K.Output(0,b"\x6a\x20"+bytes(32)))
        self.refuse(tx=replace(self.tx,outputs=outs))

    def test_add_third_output(self):
        outs=self.tx.outputs+(K.Output(0,b"\x6a"),)
        self.refuse(tx=replace(self.tx,outputs=outs))

    def test_input_amount(self):
        inp=replace(self.tx.inputs[0],value=self.tx.inputs[0].value+1)
        self.refuse(tx=replace(self.tx,inputs=(inp,)))

    def test_funding_outpoint(self):
        inp=replace(self.tx.inputs[0],txid=K.H(b"other coin"))
        self.refuse(tx=replace(self.tx,inputs=(inp,)))

    def test_sequence(self):
        inp=replace(self.tx.inputs[0],sequence=0xffffffff)
        self.refuse(tx=replace(self.tx,inputs=(inp,)))

    def test_version(self): self.refuse(tx=replace(self.tx,version=3))
    def test_locktime(self): self.refuse(tx=replace(self.tx,locktime=42))

    def test_control(self): self.refuse(control=b"\xc0"+bytes(32))

    def test_sibling(self):
        wit=list(self.wit);wit[3]=bytes(32)
        self.refuse(wit=wit)

    def test_direction(self):
        wit=list(self.wit);wit[4]=b"\x01"
        self.refuse(wit=wit)

    def test_cat_unactivated(self): self.refuse(cat_active=False)

    def test_existing_unknown_pubkey_semantics_are_unsafe(self):
        tx=replace(self.tx,outputs=(self.tx.outputs[0],
                     K.Output(0,b"\x6a\x20"+bytes(32))))
        self.assertTrue(self.check(tx=tx,upgraded=False))
        self.refuse(tx=tx,upgraded=True)

    def test_zero_crossing_excluded_by_one_byte_trace_format(self):
        with self.assertRaises(K.Reject):
            prove_trace(11)  # 11,13,15,0: zero lacks 1-byte ScriptNum

    def test_fake_17_not_accepted(self):
        wit=list(self.wit);wit[-4]=b"\x11"
        self.refuse(wit=wit)

    def test_nonnumeric_transition_byte(self):
        wit=list(self.wit);wit[-1]=b"\xff"
        self.refuse(wit=wit)

if __name__=="__main__":
    unittest.main(verbosity=2)
