"""Offline checks for cooperative DLC UTXO rollover, no Bitcoin Core needed."""
from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import secp
from arms import ArmA, FUNDING_SATS, Parties, SETTLE_FEE_SATS
from rollover import (ROLLOVER_FEE_SATS, RolledDLC, former_holder_attack,
                      make_rollover)
from txlib import Prevout, TxOut, sighash_scriptpath


class RolloverTests(unittest.TestCase):
    def setUp(self):
        self.p = Parties.fixture("rollover-static-v1")
        self.old = ArmA(self.p)
        self.new = RolledDLC(self.p)
        self.funding_txid = "ab" * 32
        self.transfer = make_rollover(self.old, self.p, self.funding_txid, 0, self.new)

    def test_new_funding_script_and_amount(self):
        self.assertNotEqual(self.old.funding_spk, self.new.funding_spk)
        self.assertEqual(self.new.funding_sats, FUNDING_SATS - ROLLOVER_FEE_SATS)
        self.assertEqual(self.new.payout_sats,
                         FUNDING_SATS - ROLLOVER_FEE_SATS - SETTLE_FEE_SATS)
        self.assertEqual(self.transfer.vout, (TxOut(self.new.funding_sats, self.new.funding_spk),))
        self.assertEqual(self.transfer.vin[0].txid, self.funding_txid)

    def test_both_old_signatures_authorize_transfer(self):
        msg = sighash_scriptpath(
            self.transfer, 0, [Prevout(FUNDING_SATS, self.old.funding_spk)], self.old.leaf)
        w = self.transfer.vin[0].witness
        self.assertTrue(secp.verify(self.p.x("bob"), msg, w[0]))
        self.assertTrue(secp.verify(self.p.x("alice"), msg, w[1]))
        self.assertEqual(w[-2], self.old.leaf)
        self.assertEqual(w[-1], self.old.tree["controls"][0])
        attacker_out = replace(self.transfer, vout=(TxOut(self.new.funding_sats - 1,
                                                           self.new.funding_spk),))
        mutated = sighash_scriptpath(attacker_out, 0,
                                     [Prevout(FUNDING_SATS, self.old.funding_spk)],
                                     self.old.leaf)
        self.assertFalse(secp.verify(self.p.x("alice"), mutated, w[1]))

    def test_old_and_new_cets_use_different_outpoints(self):
        old_pre = self.old.presign_all(self.funding_txid, 0)
        old_cet = self.old.settle(old_pre, "ALICE_WINS", self.p.oracle.attest("ALICE_WINS"))
        new_pre = self.new.presign_all(self.transfer.txid, 0)
        new_cet = self.new.settle(new_pre, "ALICE_WINS", self.p.oracle.attest("ALICE_WINS"))
        self.assertEqual(old_cet.vin[0].txid, self.funding_txid)
        self.assertEqual(new_cet.vin[0].txid, self.transfer.txid)
        self.assertNotEqual(old_cet.vin[0].txid, new_cet.vin[0].txid)
        self.assertEqual(new_cet.vout[0].value, self.new.payout_sats)
        self.assertNotEqual(new_cet.vout[0].script, old_cet.vout[0].script)

    def test_buyer_and_bob_sign_new_cets(self):
        pre = self.new.presign_all(self.transfer.txid, 0)
        for outcome in ("ALICE_WINS", "BOB_WINS"):
            with self.subTest(outcome=outcome):
                cet = self.new.settle(pre, outcome, self.p.oracle.attest(outcome))
                msg = sighash_scriptpath(cet, 0,
                                         [Prevout(self.new.funding_sats, self.new.funding_spk)],
                                         self.new.leaf)
                w = cet.vin[0].witness
                self.assertTrue(secp.verify(self.p.x("bob"), msg, w[0]))
                self.assertTrue(secp.verify(self.p.x("carol"), msg, w[1]))
                self.assertFalse(secp.verify(self.p.x("alice"), msg, w[1]))

    def test_former_holder_old_keys_cannot_sign_successor(self):
        tx = former_holder_attack(self.new, self.transfer.txid, 0)
        w = tx.vin[0].witness
        msg = sighash_scriptpath(tx, 0,
                                 [Prevout(self.new.funding_sats, self.new.funding_spk)],
                                 self.new.leaf)
        self.assertTrue(secp.verify(self.p.x("alice"), msg, w[1]))
        self.assertFalse(secp.verify(self.p.x("carol"), msg, w[1]))
        self.assertNotEqual(self.new.leaf, self.old.leaf)

    def test_wrong_rollover_amount_rejected_before_signing(self):
        wrong = RolledDLC(self.p, funding_sats=FUNDING_SATS - 2 * ROLLOVER_FEE_SATS)
        with self.assertRaisesRegex(ValueError, "amount"):
            make_rollover(self.old, self.p, self.funding_txid, 0, wrong)
        with self.assertRaises(ValueError):
            RolledDLC(self.p, holder="bob", counterparty="bob")
        with self.assertRaises(ValueError):
            RolledDLC(self.p, funding_sats=SETTLE_FEE_SATS)


if __name__ == "__main__":
    unittest.main()
