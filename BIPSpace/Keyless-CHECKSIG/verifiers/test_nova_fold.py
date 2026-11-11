import unittest
from dataclasses import replace
from hashlib import sha256
from nova_ipa import Q,generator,mul,add
from nova_fold import Instance,expected_fold,verify_fold

CTX=sha256(b"keyless transaction A").digest()
BAD=sha256(b"keyless transaction B").digest()

class NovaFoldTests(unittest.TestCase):
    def setUp(self):
        self.g=generator(b"G",0)
        self.h=generator(b"H",1)
        self.t=generator(b"U",0)
        self.old=Instance(1,(2,5),mul(self.g,7),mul(self.h,11))
        self.new=Instance(1,(3,8),mul(self.g,13),None)
        self.r,self.fold=expected_fold(self.old,self.new,self.t,CTX)

    def test_valid(self):
        self.assertTrue(verify_fold(self.old,self.new,self.t,self.fold,CTX))
    def test_challenge_nonzero(self):
        self.assertTrue(0<self.r<Q)
    def test_public_state_changed(self):
        self.assertFalse(verify_fold(self.old,self.new,self.t,replace(
            self.fold,x=((self.fold.x[0]+1)%Q,self.fold.x[1])),CTX))
    def test_u_changed(self):
        self.assertFalse(verify_fold(self.old,self.new,self.t,replace(
            self.fold,u=(self.fold.u+1)%Q),CTX))
    def test_w_changed(self):
        self.assertFalse(verify_fold(self.old,self.new,self.t,replace(
            self.fold,w=add(self.fold.w,self.g)),CTX))
    def test_e_changed(self):
        self.assertFalse(verify_fold(self.old,self.new,self.t,replace(
            self.fold,e=add(self.fold.e,self.h)),CTX))
    def test_wrong_transaction_context(self):
        self.assertFalse(verify_fold(self.old,self.new,self.t,self.fold,BAD))
    def test_changed_cross_term(self):
        self.assertFalse(verify_fold(self.old,self.new,self.h,self.fold,CTX))
    def test_changed_old_instance(self):
        a=replace(self.old,u=2)
        self.assertFalse(verify_fold(a,self.new,self.t,self.fold,CTX))
    def test_changed_fresh_instance(self):
        b=replace(self.new,x=(3,9))
        self.assertFalse(verify_fold(self.old,b,self.t,self.fold,CTX))
    def test_noncanonical_scalar(self):
        self.assertFalse(verify_fold(self.old,self.new,self.t,replace(self.fold,u=Q),CTX))
    def test_invalid_point(self):
        self.assertFalse(verify_fold(self.old,self.new,self.t,
                                      replace(self.fold,e=(10,10)),CTX))
    def test_arity_mismatch(self):
        self.assertFalse(verify_fold(self.old,replace(self.new,x=(3,)),self.t,
                                      self.fold,CTX))
    def test_algebraic_folding_nonzero_fresh_e(self):
        new=replace(self.new,e=mul(self.h,29))
        _,claimed=expected_fold(self.old,new,self.t,CTX)
        self.assertTrue(verify_fold(self.old,new,self.t,claimed,CTX))
        self.assertFalse(verify_fold(self.old,new,self.t,self.fold,CTX))
    def test_serialization_deterministic(self):
        self.assertEqual(self.old.bytes(),self.old.bytes())
        self.assertNotEqual(self.old.bytes(),self.new.bytes())

if __name__=="__main__":
    unittest.main(verbosity=2)
