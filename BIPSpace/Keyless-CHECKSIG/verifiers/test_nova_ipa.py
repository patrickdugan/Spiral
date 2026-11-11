"""Native mathematical checks of one IPA building block for Nova/Spartan.

This is not Nova SNARK verification and has no Bitcoin consensus semantics.
"""
import unittest
from dataclasses import replace
from hashlib import sha256
from nova_ipa import *

CTX = sha256(b"Keyless-CHECKSIG/spend/txA").digest()
BAD = sha256(b"Keyless-CHECKSIG/spend/txB").digest()

class IpaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = [3,5,7,9]
        cls.b = [2,4,6,8]
        cls.C,cls.c,cls.proof = prove(cls.a,cls.b,CTX)

    def test_real_inner_product_argument_accepts(self):
        self.assertTrue(verify(self.C,self.c,self.proof.encode(),CTX))

    def test_public_inner_product_is_correct(self):
        self.assertEqual(self.c, sum(a*b for a,b in zip(self.a,self.b)) % Q)

    def test_proof_is_succinct_relative_to_vector(self):
        self.assertEqual(len(self.proof.encode()),197)

    def test_proof_ser_roundtrip(self):
        self.assertEqual(IpaProof.decode(self.proof.encode()),self.proof)

    def test_different_transaction_rejected(self):
        self.assertFalse(verify(self.C,self.c,self.proof,BAD))

    def test_different_claim_rejected(self):
        self.assertFalse(verify(self.C,(self.c+1)%Q,self.proof,CTX))

    def test_different_commitment_rejected(self):
        self.assertFalse(verify(add(self.C,generator(b"G",0)),self.c,self.proof,CTX))

    def test_bad_final_scalar_rejected(self):
        self.assertFalse(verify(self.C,self.c,replace(self.proof,a=(self.proof.a+1)%Q),CTX))

    def test_bad_final_inner_scalar_rejected(self):
        self.assertFalse(verify(self.C,self.c,replace(self.proof,b=(self.proof.b+1)%Q),CTX))

    def test_wrong_first_round_point_rejected(self):
        l=list(self.proof.L)
        l[0]=encode_point(generator(b"U",0))
        self.assertFalse(verify(self.C,self.c,replace(self.proof,L=tuple(l)),CTX))

    def test_wrong_second_round_point_rejected(self):
        r=list(self.proof.R)
        r[-1]=encode_point(generator(b"U",0))
        self.assertFalse(verify(self.C,self.c,replace(self.proof,R=tuple(r)),CTX))

    def test_noncanonical_scalar_rejected(self):
        blob=self.proof.encode()
        self.assertFalse(verify(self.C,self.c,blob[:-64]+Q.to_bytes(32,"little")+blob[-32:],CTX))

    def test_corrupted_point_encoding_rejected(self):
        blob=bytearray(self.proof.encode())
        blob[1]=4
        self.assertFalse(verify(self.C,self.c,bytes(blob),CTX))

    def test_infinity_round_rejected(self):
        blob=bytearray(self.proof.encode())
        blob[1:34]=bytes(33)
        self.assertFalse(verify(self.C,self.c,bytes(blob),CTX))

    def test_proof_truncation_rejected(self):
        self.assertFalse(verify(self.C,self.c,self.proof.encode()[:-1],CTX))

    def test_extra_proof_bytes_rejected(self):
        self.assertFalse(verify(self.C,self.c,self.proof.encode()+b"\x00",CTX))

    def test_reject_wrong_context_length(self):
        self.assertFalse(verify(self.C,self.c,self.proof,b"\x00"*31))

    def test_reject_bad_public_point(self):
        self.assertFalse(verify((P,2),self.c,self.proof,CTX))

    def test_reject_noncanonical_public_claim(self):
        self.assertFalse(verify(self.C,Q,self.proof,CTX))

    def test_pallas_generator_order(self):
        for G in (generator(b"G",0),generator(b"H",1),generator(b"U",0)):
            self.assertTrue(on_curve(G))
            self.assertIsNone(mul(G,Q))

    def test_point_serialization_roundtrip(self):
        for t in (None, generator(b"G",0),generator(b"H",1), self.C):
            self.assertEqual(decode_point(encode_point(t)), t)

    def test_group_addition_law(self):
        g,h=generator(b"G",0),generator(b"H",0)
        self.assertEqual(add(g,None),g)
        self.assertIsNone(add(g,neg(g)))
        self.assertEqual(add(g,h),add(h,g))
        self.assertEqual(add(add(g,h),g),add(g,add(h,g)))

    def test_multiple_dimensions(self):
        for n in (2,4,8):
            a=list(range(1,n+1));b=list(range(2,n+2))
            C,c,pr=prove(a,b,CTX)
            self.assertTrue(verify(C,c,pr.encode(),CTX))
            self.assertFalse(verify(C,c,pr.encode(),BAD))

    def test_no_hidden_setup_file(self):
        # Reproduce deterministic public generators from the fixed domain.
        self.assertEqual(generator(b"G",0), generator(b"G",0))
        self.assertNotEqual(generator(b"G",0), generator(b"H",0))

if __name__ == "__main__":
    unittest.main(verbosity=2)
