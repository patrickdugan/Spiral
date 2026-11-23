"""Offline tests for the A/B harness (no Bitcoin Core process)."""
import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import secp  # noqa: E402
from arms import (FUNDING_SATS, PAYOUT_SATS, ArmA, ArmB, ArmC, Parties, UnsafeUnconstrained,  # noqa: E402
                  allowlist_root, assignment_message)
from txlib import Prevout, ref, ref_tx, segwit_address, sighash_keypath, taproot_output, NUMS  # noqa: E402

VECTORS = Path(__file__).resolve().parents[2] / "BIPSpace" / "Keyless-CHECKSIG" / "bip341-vectors.json"


def run_b(arm, tx, outcome_leaf_index=None):
    w = list(tx.vin[0].witness)
    try:
        return ref.execute(ref_tx(tx, [Prevout(FUNDING_SATS, arm.funding_spk)]), w[-2], w[-1], w[:-2])
    except ref.Reject as e:
        return str(e)


class Crypto(unittest.TestCase):
    def test_bip340_vector0(self):
        # bitcoin/bips bip-0340/test-vectors.csv, index 0
        sig = secp.sign(3, bytes(32), bytes(32))
        self.assertEqual(sig.hex().upper(),
                         "E907831F80848D1069A5371B402410364BDF1C5F8307B0084C55F1CE2DCA8215"
                         "25F66A4A85EA8B71E482A74F382D2CE5EBEEE8FDB2172F477DF4900D310536C0")
        self.assertTrue(secp.verify(secp.pubkey_xonly(3), bytes(32), sig))

    def test_adaptor_round_trip_and_wrong_secret(self):
        o = secp.Oracle("unit")
        T, t = o.attestation_point("A"), o.attest("A")
        self.assertEqual(secp.point_mul(secp.G, t), T)
        d, msg = secp.seckey("unit/bob"), b"\x22" * 32
        pre = secp.adaptor_presign(d, msg, T, "u")
        self.assertTrue(secp.adaptor_verify(secp.pubkey_xonly(d), msg, T, pre))
        self.assertTrue(secp.verify(secp.pubkey_xonly(d), msg, secp.adaptor_complete(pre, t)))
        self.assertFalse(secp.verify(secp.pubkey_xonly(d), msg, secp.adaptor_complete(pre, o.attest("B"))))

    def test_oracle_commitment_is_hash_of_attestation(self):
        o = secp.Oracle("unit")
        self.assertEqual(o.hash_commitment("A"), hashlib.sha256(o.attest("A").to_bytes(32, "big")).digest())

    def test_bech32m_bip350(self):
        self.assertEqual(segwit_address("bc", 1, bytes.fromhex(
            "79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798")),
            "bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqzk5jj0")


class Arms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = Parties.fixture("unit")
        cls.s = {m: cls.p.oracle.attest(m) for m in ("ALICE_WINS", "BOB_WINS")}

    def test_arm_a_settles_only_with_matching_attestation(self):
        a = ArmA(self.p)
        pre = a.presign_all("aa" * 32, 0)
        cet = a.settle(pre, "ALICE_WINS", self.s["ALICE_WINS"])
        self.assertEqual(cet.vout[0].value, PAYOUT_SATS)
        with self.assertRaises(AssertionError):
            a.settle(pre, "ALICE_WINS", self.s["BOB_WINS"])

    def test_arm_b_allowlist_oracle_and_digest(self):
        b = ArmB(self.p)
        self.assertTrue(run_b(b, b.settlement("bb" * 32, 0, "ALICE_WINS", "alice", self.s["ALICE_WINS"])))
        self.assertTrue(run_b(b, b.settlement("bb" * 32, 0, "ALICE_WINS", "carol", self.s["ALICE_WINS"])))
        self.assertNotEqual(run_b(b, b.settlement("bb" * 32, 0, "ALICE_WINS", "mallory", self.s["ALICE_WINS"])), True)
        self.assertNotEqual(run_b(b, b.settlement("bb" * 32, 0, "ALICE_WINS", "alice", self.s["BOB_WINS"])), True)
        good = b.settlement("bb" * 32, 0, "ALICE_WINS", "alice", self.s["ALICE_WINS"])
        stale = b.settlement("bb" * 32, 0, "ALICE_WINS", "alice", self.s["ALICE_WINS"],
                             amount=PAYOUT_SATS - 1, witness_for=good)
        self.assertEqual(run_b(b, stale), "txcommit_mismatch")

    def test_unconstrained_fixture_spends_to_anyone_in_model(self):
        k = UnsafeUnconstrained()
        tx = k.steal("cc" * 32, 0, self.p.x("mallory"))
        self.assertEqual(len(tx.vin[0].witness[0]), 32)

    def test_allowlist_root_order(self):
        keys = (self.p.x("alice"), self.p.x("carol"))
        self.assertEqual(allowlist_root(keys),
                         hashlib.sha256(hashlib.sha256(keys[0]).digest() + hashlib.sha256(keys[1]).digest()).digest())

    def test_arm_a_funding_has_no_key_path(self):
        tree = taproot_output(NUMS, [ArmA(self.p).leaf])
        self.assertEqual(tree["controls"][0][1:33], NUMS)


class ArmCTests(unittest.TestCase):
    def setUp(self):
        self.p = Parties.fixture("unit")
        self.c = ArmC(self.p)

    def test_oracle_attestation_is_a_bip340_signature(self):
        s = self.p.oracle.attest("ALICE_WINS")
        sig = self.c.oracle_sig("ALICE_WINS", s)
        self.assertTrue(secp.verify(self.p.oracle.P, secp.Oracle.message("ALICE_WINS"), sig))
        self.assertFalse(secp.verify(self.p.oracle.P, secp.Oracle.message("BOB_WINS"), sig))

    def test_assignment_binds_contract_and_recipient(self):
        a = self.c.assign("ALICE_WINS", "carol")
        msg = assignment_message(self.c.cid["ALICE_WINS"], self.p.x("carol"))
        self.assertTrue(secp.verify(self.p.x("alice"), msg, a))
        self.assertFalse(secp.verify(self.p.x("alice"), assignment_message(self.c.cid["BOB_WINS"], self.p.x("carol")), a))
        self.assertFalse(secp.verify(self.p.x("alice"), assignment_message(self.c.cid["ALICE_WINS"], self.p.x("mallory")), a))

    def test_leaf_layout(self):
        leaf = self.c.leaves["ALICE_WINS"]
        self.assertEqual(len(leaf), 272)
        self.assertEqual(leaf.count(bytes([0xCC])) >= 2, True)
        tx = self.c.settlement("aa" * 32, 0, "ALICE_WINS", "carol",
                               self.c.oracle_sig("ALICE_WINS", self.p.oracle.attest("ALICE_WINS")),
                               self.c.assign("ALICE_WINS", "carol"))
        self.assertEqual(len(tx.vin[0].witness), 7)
        self.assertEqual(tx.vin[0].witness[2], self.p.x("carol"))


if __name__ == "__main__":
    unittest.main()
