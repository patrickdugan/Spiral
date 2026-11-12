"""Malicious-prover tests which generate fresh proofs for false statements.
Changing an already-issued proof's public input misses these attacks.
"""
import unittest
from unittest.mock import patch
import nova_ipa as M


def fresh_false_claim(module, n=4):
    context = module.sha(b'fresh malicious proof against a fixed vector commitment')
    a,b = list(range(1,n+1)),list(range(3,n+3))
    original = module.transcript_init
    def liar(dim,commitment,claim,ctx):
        return original(dim,commitment,(claim+1)%module.Q,ctx)
    with patch.object(module,'transcript_init',liar):
        commitment,true_claim,proof = module.prove(a,b,context)
    return module.verify(commitment,(true_claim+1)%module.Q,proof,context)


def fresh_shifted_commitment(module):
    context = module.sha(b'chosen commitment before Fiat-Shamir')
    a,b = [1,2,3,4],[3,4,5,6]
    G,H,U = module.basis(4)
    honest = module.add(module.msm(G,a),module.msm(H,b))
    forged = module.add(honest,module.neg(U))
    original = module.transcript_init
    def liar(n,C,claim,ctx):
        return original(n,forged,(claim+1)%module.Q,ctx)
    with patch.object(module,'transcript_init',liar):
        _,claim,proof = module.prove(a,b,context)
    return module.verify(forged,(claim+1)%module.Q,proof,context)


class ClaimBindingTests(unittest.TestCase):
    def test_fresh_false_claim_proofs_are_rejected(self):
        for n in (2,4,8):
            with self.subTest(n=n):
                self.assertFalse(fresh_false_claim(M,n))

    def test_chosen_commitment_attack_is_rejected(self):
        self.assertFalse(fresh_shifted_commitment(M))

    def test_commitment_is_independent_of_the_claim(self):
        a,b = [3,5,7,9],[2,4,6,8]
        C,c,proof = M.prove(a,b,M.sha(b'honest claim'))
        G,H,U = M.basis(4)
        self.assertEqual(C,M.add(M.msm(G,a),M.msm(H,b)))
        self.assertTrue(M.verify(C,c,proof,M.sha(b'honest claim')))

    def test_empty_round_object_rejected(self):
        C,c,proof = M.prove([1,2],[3,4],M.sha(b'state'))
        self.assertFalse(M.verify(C,c,M.IpaProof((),(),1,1),M.sha(b'state')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
