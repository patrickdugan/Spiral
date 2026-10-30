"""Finite oracles and adversarial wire tests for the isolated PoW lab."""
from collections import Counter
from dataclasses import replace
import copy
import hashlib
import json
import math
import unittest

import pow_lab as p


class PrimeTests(unittest.TestCase):
    def test_cunningham_recurrences(self):
        self.assertEqual(p.chain_terms(6, "cunningham1", 4), [5, 11, 23, 47])
        self.assertEqual(p.chain_terms(6, "cunningham2", 3), [7, 13, 25])
        self.assertEqual(p.chain_terms(6, "bitwin", 4), [5, 7, 11, 13])
        self.assertEqual(p.chain_terms(6, "bitwin", 3), [5, 7, 11])

    def test_primality_against_independent_sieve(self):
        sieve = [True] * 4096
        sieve[0] = sieve[1] = False
        for i in range(2, 64):
            for j in range(i*i, 4096, i):
                sieve[j] = False
        self.assertEqual([p.prime(i, Counter()) for i in range(4096)], sieve)

    def test_certificates_for_all_small_primes(self):
        for n in range(2, 1024):
            if p.prime(n, Counter()):
                with self.subTest(n=n):
                    self.assertTrue(p.check_certificate(p.certify(n, Counter()), n, Counter()))

    def test_fermat_pseudoprime_is_not_prime(self):
        self.assertEqual(pow(2, 340, 341), 1)
        self.assertFalse(p.prime(341, Counter()))
        with self.assertRaises(ValueError):
            p.certify(341, Counter())

    def test_carmichael_forged_certificate(self):
        cert = {"n": 561, "a": 2, "f": [[q, e, p.certify(q, Counter())]
                for q, e in ((2, 4), (5, 1), (7, 1))]}
        self.assertEqual(pow(2, 560, 561), 1)
        self.assertFalse(p.check_certificate(cert, 561, Counter()))

    def test_factorization_tampering(self):
        cert = p.certify(23, Counter())
        variants = []
        for key, value in (("n", 25), ("a", 1), ("f", [])):
            bad = copy.deepcopy(cert)
            bad[key] = value
            variants.append(bad)
        bad = copy.deepcopy(cert)
        bad["f"][0][1] += 1
        variants.append(bad)
        bad = copy.deepcopy(cert)
        bad["f"].reverse()
        variants.append(bad)
        for bad in variants:
            self.assertFalse(p.check_certificate(bad, 23, Counter()))

    def test_certificate_limits_and_types(self):
        cert = p.certify(5, Counter())
        self.assertFalse(p.check_certificate(cert, 5, Counter(), depth=25))
        self.assertFalse(p.check_certificate(cert, 5, Counter(certificate_nodes=2048)))
        self.assertFalse(p.check_certificate({"n": 2, "a": False, "f": []}, 2, Counter()))
        self.assertFalse(p.check_certificate(cert, True, Counter()))
        self.assertFalse(p.prime(p.MAX_PRIME+1, Counter()))

    def test_certificate_malleability_has_stable_artifact_id(self):
        a = p.certify(5, Counter())
        b = copy.deepcopy(a)
        b["a"] = 3
        self.assertTrue(p.check_certificate(a, 5, Counter()))
        self.assertTrue(p.check_certificate(b, 5, Counter()))
        self.assertNotEqual(p.digest(a), p.digest(b))
        self.assertEqual(p.artifact_id("cunningham1", [5, 11]),
                         p.artifact_id("cunningham1", [5, 11]))

    def test_suffix_overlap_is_separate_from_exact_duplicate(self):
        a, b = [5, 11, 23, 47], [11, 23, 47]
        self.assertEqual(p.overlap(a, b), b)
        self.assertNotEqual(p.artifact_id("cunningham1", a), p.artifact_id("cunningham1", b))

    def test_chain_bounds(self):
        for args in ((3, "bitwin", 2), (6, "other", 3), (6, "bitwin", 7)):
            with self.assertRaises(ValueError):
                p.chain_terms(*args)


class WireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.challenge = p.fixture("cunningham1", 0)
        cls.wire, _ = p.solve(cls.challenge)
        assert cls.wire is not None

    def test_all_families_round_trip(self):
        for family in p.FAMILIES:
            with self.subTest(family=family):
                wire, _ = p.solve(p.fixture(family, 0), 65536)
                self.assertIsNotNone(wire)
                self.assertTrue(p.verify(p.fixture(family, 0), wire))

    def test_context_replay_rejected(self):
        changes = {"parent": p.digest("parent2"), "payload": p.digest("payload2"),
                   "beacon": p.digest("beacon2"), "epoch": 1, "bits": 11,
                   "length": 4, "family": "cunningham2", "variables": 11, "clauses": 44}
        for field, value in changes.items():
            with self.subTest(field=field):
                self.assertFalse(p.verify(replace(self.challenge, **{field: value}), self.wire))

    def test_miner_cannot_supply_difficulty(self):
        proof = json.loads(self.wire)
        proof["bits"] = 0
        self.assertFalse(p.verify(self.challenge, p.canonical(proof)))

    def test_truncated_chain_rejected(self):
        proof = json.loads(self.wire)
        proof["solution"].pop()
        proof["certificates"].pop()
        self.assertFalse(p.verify(self.challenge, p.canonical(proof)))

    def test_certificate_and_solution_tampering(self):
        original = json.loads(self.wire)
        proof = copy.deepcopy(original)
        proof["solution"][0] += 2
        self.assertFalse(p.verify(self.challenge, p.canonical(proof)))
        proof = copy.deepcopy(original)
        proof["certificates"][0]["a"] = 1
        self.assertFalse(p.verify(self.challenge, p.canonical(proof)))

    def test_nonce_strict_integer_bounds(self):
        for nonce in (True, -1, 2**32, 1.0, "1"):
            proof = json.loads(self.wire)
            proof["nonce"] = nonce
            self.assertFalse(p.verify(self.challenge, p.canonical(proof)))

    def test_malformed_wire_is_rejected(self):
        variants = (b"", b"[]", b"null", b'{"x":1,"x":2}', b"NaN",
                    self.wire+b" ", b"["*1100+b"]"*1100,
                    b"x"*(p.MAX_WIRE+1), b"\xff", "not bytes")
        for raw in variants:
            self.assertFalse(p.verify(self.challenge, raw))

    def test_toy_origin_collision_preserves_math_work(self):
        proof = json.loads(self.wire)
        target = p.origin(p.ticket(self.challenge.id, proof["nonce"], Counter()), self.challenge.bits)
        for nonce in range(10000):
            if nonce != proof["nonce"] and p.origin(p.ticket(self.challenge.id, nonce, Counter()),
                                                    self.challenge.bits) == target:
                proof["nonce"] = nonce
                self.assertTrue(p.verify(self.challenge, p.canonical(proof)))
                return
        self.fail("deterministic collision fixture missing")

    def test_rebound_context_can_reuse_small_domain_artifact(self):
        # Literal replay fails, but a new ticket may hit the same tiny origin.
        changed = replace(self.challenge, parent=p.digest("alternate-parent"))
        proof = json.loads(self.wire)
        target = (proof["solution"][0]+1)
        self.assertFalse(p.verify(changed, self.wire))
        for nonce in range(10000):
            if p.origin(p.ticket(changed.id, nonce, Counter()), changed.bits) == target:
                proof.update(challenge=changed.id, nonce=nonce)
                self.assertTrue(p.verify(changed, p.canonical(proof)))
                return
        self.fail("deterministic cross-context reuse fixture missing")

    def test_invalid_challenge_parameters(self):
        for changes in ({"bits": True}, {"length": 100}, {"epoch": -1},
                        {"parent": "00"}, {"version": "v0"}, {"family": "unknown"}):
            with self.assertRaises(ValueError):
                replace(self.challenge, **changes)


class OtherPuzzleTests(unittest.TestCase):
    def test_sat_clauses_use_distinct_variables(self):
        c = p.fixture("sat", 0)
        formula = p.sat_instance(c, Counter())
        self.assertEqual(len(formula), c.clauses)
        self.assertTrue(all(len({abs(x) for x in clause}) == 3 for clause in formula))
        self.assertEqual(formula, p.sat_instance(c, Counter()))

    def test_sat_exhaustive_unsat_fixture(self):
        found = []
        for seed in range(8):
            wire, stats = p.solve(p.fixture("sat", seed), 1024)
            if stats["status"] == "exhaustive_unsat":
                found.append(seed)
                self.assertIsNone(wire)
                self.assertEqual(stats["candidates_tested"], 1024)
        self.assertEqual(len(found), 2)

    def test_sat_budget_exhaustion_differs_from_unsat(self):
        wire, stats = p.solve(p.fixture("sat", 0), 1)
        self.assertIsNone(wire)
        self.assertEqual(stats["status"], "budget_exhausted")

    def test_sat_witness_does_not_choose_formula(self):
        c = p.fixture("sat", 0)
        wire, _ = p.solve(c)
        proof = json.loads(wire)
        proof["nonce"] = 1
        self.assertFalse(p.verify(c, p.canonical(proof)))
        proof["nonce"], proof["solution"] = 0, True
        self.assertFalse(p.verify(c, p.canonical(proof)))

    def test_toy_curve_group_exhaustive_oracle(self):
        points = {(x, y) for x in range(p.FIELD) for y in range(p.FIELD)
                  if (y*y-x*x*x-7) % p.FIELD == 0}
        self.assertEqual(len(points)+1, p.ORDER)
        generated = {p.ec_mul(k, p.BASE, Counter()) for k in range(p.ORDER)}
        self.assertEqual(generated, points | {None})
        self.assertIsNone(p.ec_mul(p.ORDER, p.BASE, Counter()))

    def test_ecdlp_targets_on_curve(self):
        for seed in range(32):
            x, y = p.ec_target(p.fixture("ecdlp", seed), Counter())
            self.assertEqual((y*y-x*x*x-7) % p.FIELD, 0)

    def test_ecdlp_wrong_and_noncanonical_scalar(self):
        c = p.fixture("ecdlp", 0)
        wire, _ = p.solve(c)
        proof = json.loads(wire)
        for value in (0, p.ORDER, True, proof["solution"] % (p.ORDER-1)+1):
            proof["solution"] = value
            self.assertFalse(p.verify(c, p.canonical(proof)))

    def test_hashcash_target_boundaries(self):
        c = p.fixture("hashcash", 0)
        wire, _ = p.solve(c, 65536)
        proof = json.loads(wire)
        self.assertLess(int(proof["solution"], 16), 2**(256-c.bits))
        proof["solution"] = "00"*32
        self.assertFalse(p.verify(c, p.canonical(proof)))

    def test_work_counter_is_populated(self):
        for family in p.FAMILIES:
            wire, stats = p.solve(p.fixture(family, 0), 65536)
            work = Counter()
            self.assertTrue(p.verify(p.fixture(family, 0), wire, work))
            self.assertGreater(sum(work.values()), 0)
            self.assertGreater(sum(stats["search_work"].values()), 0)

    def test_private_shortcut_share(self):
        self.assertAlmostEqual(p.shortcut_share(0.1, 10), 10/19)
        self.assertEqual(p.shortcut_share(0, 10), 0)
        self.assertEqual(p.shortcut_share(1, 10), 1)
        for args in ((-0.1, 1), (0.1, 0), (math.nan, 2), (0.1, math.inf)):
            with self.assertRaises(ValueError):
                p.shortcut_share(*args)

    def test_campaign_is_deterministic_and_explicitly_synthetic(self):
        a, b = p.run(2, 4096), p.run(2, 4096)
        self.assertEqual(a, b)
        self.assertEqual(len(a["rows"]), 12)
        self.assertEqual(a["evidence_class"], "bounded_synthetic")
        self.assertIsNone(a["energy_joules"])
        self.assertIsNone(a["economic_security_usd"])

    def test_budget_and_seed_limits(self):
        for budget in (0, -1, 65537, True):
            with self.assertRaises(ValueError):
                p.solve(p.fixture("hashcash"), budget)
        for seeds in (0, 65, True):
            with self.assertRaises(ValueError):
                p.run(seeds)


if __name__ == "__main__":
    unittest.main()
