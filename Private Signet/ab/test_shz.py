"""Offline tests for the SatsHedgeZero port and SHZ-K1 (no Core process).

Expected values are the Rust crate's own test vectors
(patrickdugan/SatsHedgeZero @ 5ca390e, crates/shz-margin/src/lib.rs tests)
and values printed by the Rust crates for the same inputs.
"""
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import secp  # noqa: E402
from shz_k1 import DigitOracle, K1Contract, merkle_tree  # noqa: E402
from shz_margin import (InverseContractSpec, compress_cet_ranges, decompose_price_bits,  # noqa: E402
                        lookup_cet_for_price, oracle_digit_message)
from txlib import ref  # noqa: E402


class RustVectors(unittest.TestCase):
    def test_covered_short(self):
        s = InverseContractSpec.from_leverages_v0(1_000, 100_000, 50_000, 10_000)
        self.assertEqual((s.long_margin_sats, s.short_margin_sats), (200_000, 1_000_000))
        self.assertTrue(s.is_covered_synthetic_usd_short())
        self.assertIsNone(s.short_liquidation_price_usd())
        self.assertEqual(s.long_liquidation_price_usd(), 83_333)
        p = s.payout_at_price(200_000)
        self.assertEqual((p.long_sats, p.short_sats), (700_000, 500_000))
        p = s.payout_at_price(10_000_000)
        self.assertEqual((p.long_sats, p.short_sats), (1_190_000, 10_000))

    def test_leveraged_liquidation_and_conservation(self):
        s = InverseContractSpec.from_leverages_v0(1_000, 100_000, 100_000, 100_000)
        self.assertEqual(s.long_liquidation_price_usd(), 90_909)
        self.assertEqual(s.short_liquidation_price_usd(), 111_112)
        for price in (0, 1, 50_000, 90_909, 95_000, 100_000, 105_000, 111_112, 250_000):
            self.assertEqual(s.payout_at_price(price).total, 200_000)
        self.assertEqual(s.payout_at_price(90_909).long_sats, 0)
        self.assertEqual(s.payout_at_price(111_112).short_sats, 0)

    def test_compression_643(self):
        s = InverseContractSpec.from_leverages_v0(1_000, 100_000, 100_000, 100_000)
        cets = compress_cet_ranges(s, 20, 250)
        self.assertEqual(len(cets), 643)
        self.assertEqual((cets[0].min_price_usd, cets[-1].max_price_usd), (0, (1 << 20) - 1))
        for a, b in zip(cets, cets[1:]):
            self.assertEqual(a.max_price_usd + 1, b.min_price_usd)
        for price in range(0, 1 << 20, 997):
            c = lookup_cet_for_price(cets, price, 20)
            self.assertEqual(decompose_price_bits(price, 20)[:len(c.prefix_bits)], list(c.prefix_bits))
            self.assertLessEqual(abs(c.payout.long_sats - s.payout_at_price(price).long_sats), 250)

    def test_trade1_matches_rust(self):
        # Rust shz-margin, same spec: 949 CETs; $125k -> prefix 000111101000, 1075/550.
        t1 = InverseContractSpec(1, 80_000, 625, 1_000)
        cets = compress_cet_ranges(t1, 20, 1)
        self.assertEqual(len(cets), 949)
        c = lookup_cet_for_price(cets, 125_000, 20)
        self.assertEqual(list(c.prefix_bits), [0, 0, 0, 1, 1, 1, 1, 0, 1, 0, 0, 0])
        self.assertEqual((c.min_price_usd, c.max_price_usd), (124_928, 125_183))
        self.assertEqual((c.payout.long_sats, c.payout.short_sats), (1_075, 550))

    def test_oracle_digit_message_matches_rust(self):
        self.assertEqual(oracle_digit_message("BTCUSD-test", 3, 1).hex(),
                         "aec8d8c889d03026c535db08711fdcd5475c8363ef6317712de33593105e4f05")


class K1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oracle = DigitOracle("unit", "SHZ/unit", 20)
        cls.alice, cls.bob = secp.seckey("unit/alice"), secp.seckey("unit/bob")
        cls.k1 = K1Contract(InverseContractSpec(1, 80_000, 625, 1_000), cls.oracle,
                            secp.pubkey_xonly(cls.alice), secp.pubkey_xonly(cls.bob),
                            label="unit", max_error_sats=1, fee_sats=1_000)

    def test_attestations_are_bip340_under_announced_nonces(self):
        bits = decompose_price_bits(125_000, 20)
        for j, s in enumerate(self.oracle.attest(125_000)):
            self.assertTrue(secp.verify(self.oracle.P, self.oracle.msg(j, bits[j]), self.oracle.R[j] + s))
            self.assertFalse(secp.verify(self.oracle.P, self.oracle.msg(j, 1 - bits[j]), self.oracle.R[j] + s))

    def test_tree_paths_rebuild_root(self):
        k1 = self.k1
        self.assertEqual(len(k1.leaves), 950)
        for i in (0, 1, 474, len(k1.leaves) - 1):
            h = ref.tapleaf(k1.leaves[i].script)
            for sib in k1.paths[i]:
                h = ref.tapbranch(h, sib)
            self.assertEqual(h, k1.root)
        self.assertEqual(k1.spk, b"\x52\x20" + k1.root)

    def test_leaf_sides_and_witness_shape(self):
        k1 = self.k1
        i = k1.leaf_for_price(125_000)
        leaf = k1.leaves[i]
        self.assertEqual(leaf.sides, [("long", 1_075), ("short", 550)])
        self.assertEqual(k1.leaves[k1.leaf_for_price(50_000)].sides, [("short", 1_625)])
        self.assertEqual(k1.leaves[k1.leaf_for_price(500_000)].sides, [("long", 1_625)])
        x_a, x_b = secp.pubkey_xonly(self.alice), secp.pubkey_xonly(self.bob)
        own = {"long": (x_a, k1.assign(self.alice, x_a)), "short": (x_b, k1.assign(self.bob, x_b))}
        tx = k1.spend("11" * 32, 0, i, own, self.oracle.attest(125_000))
        w = tx.vin[0].witness
        # prefix, suffix, short (x, sig), long (x, sig), 12 digit scalars, leaf, control
        self.assertEqual(len(w), 2 + 4 + 12 + 2)
        self.assertEqual((len(w[0]), w[2], w[4]), (138, x_b, x_a))
        self.assertEqual(w[-3], self.oracle.attest(125_000)[0])
        self.assertEqual([o.value for o in tx.vout], [1_075, 550])
        self.assertEqual(sum(o.value for o in tx.vout) + 1_000, k1.funding_sats)

    def test_assignment_binds_contract(self):
        x_c = secp.pubkey_xonly(secp.seckey("unit/carol"))
        sig = self.k1.assign(self.alice, x_c)
        self.assertTrue(secp.verify(secp.pubkey_xonly(self.alice), hashlib.sha256(self.k1.cid + x_c).digest(), sig))

    def test_merkle_tree_needs_two_leaves(self):
        with self.assertRaises(ValueError):
            merkle_tree([b"\x51"])


class Frost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from shz_frost import FrostOracle
        cls.o = FrostOracle("unit", "SHZ/unit", 20, t=3, n=5)

    def test_any_quorum_signs_under_announced_nonce(self):
        bits = decompose_price_bits(125_000, 20)
        for quorum in ([1, 2, 3], [2, 4, 5], [5, 3, 1]):
            for j, s in enumerate(self.o.attest(125_000, quorum)[:4]):
                self.assertTrue(secp.verify(self.o.P, self.o.msg(j, bits[j]), self.o.R[j] + s))

    def test_two_signers_are_not_enough(self):
        bits = decompose_price_bits(125_000, 20)
        s = self.o.attest(125_000, [1, 2])[0]
        self.assertFalse(secp.verify(self.o.P, self.o.msg(0, bits[0]), self.o.R[0] + s))

    def test_equivocation_reveals_group_key(self):
        q = [1, 2, 3]
        s0, s1 = (int.from_bytes(self.o.sign_digit(0, b, q), "big") for b in (0, 1))
        e0, e1 = (secp.challenge(self.o.R[0], self.o.P, self.o.msg(0, b)) for b in (0, 1))
        d = (s0 - s1) * pow(e0 - e1, -1, secp.N) % secp.N
        self.assertEqual(secp.pubkey_xonly(d), self.o.P)


class Book(unittest.TestCase):
    def test_shz_triangle_nets_to_prototype_clearing(self):
        from shz_margin import BookTrade, book_payout_at_price, compress_book_ranges
        trades = [BookTrade(InverseContractSpec(1, 80_000, 625, 1_000), "alice", "bob"),
                  BookTrade(InverseContractSpec(1, 100_000, 500, 625), "bob", "carol"),
                  BookTrade(InverseContractSpec(1, 125_000, 400, 400), "carol", "alice")]
        # SHZ's live clearing outputs: Alice 1,475, Bob 1,250, Carol 825.
        self.assertEqual(book_payout_at_price(trades, 125_000), {"alice": 1_475, "bob": 1_250, "carol": 825})
        ranges = compress_book_ranges(trades, 20, 1)
        r = next(x for x in ranges if x.matches_price(125_000, 20))
        exact = book_payout_at_price(trades, 125_000)
        for party, amt in r.payouts.items():
            self.assertLessEqual(abs(amt - exact[party]), 1)
        for x in ranges:
            self.assertEqual(sum(x.payouts.values()), 3_550)
        for a, b in zip(ranges, ranges[1:]):
            self.assertEqual(a.max_price_usd + 1, b.min_price_usd)


class K2(unittest.TestCase):
    def test_state_bound_spk_and_transfer_shape(self):
        from shz_frost import FrostOracle
        from shz_k2 import Coin, enc_num, single_trade
        o = FrostOracle("unit-k2", "SHZ/unit", 20)
        k2 = single_trade(o, InverseContractSpec(1, 80_000, 625, 1_000), max_error_sats=1, settle_fee=1_000)
        a, b, c = (secp.pubkey_xonly(secp.seckey(f"unit/{w}")) for w in ("alice", "bob", "carol"))
        self.assertNotEqual(k2.spk([a, b]), k2.spk([c, b]))
        i = k2.index("cet", price=125_000)
        for keys in ([a, b], [c, b]):
            h = ref.tapleaf(k2.leaves[i].script)
            for sib in k2.paths[i] + [k2.h_state(keys)]:
                h = ref.tapbranch(h, sib)
            self.assertEqual(b"\x52\x20" + h, k2.spk(keys))
        coin = Coin("22" * 32, 0, 4_625, [a, b])
        tx, nxt = k2.transfer(coin, "long", c, secp.seckey("unit/alice"))
        self.assertEqual(nxt.keys, [c, b])
        self.assertEqual(tx.vout[0].value, 4_125)
        self.assertEqual(tx.vout[0].script, k2.spk([c, b]))
        self.assertEqual(tx.vin[0].witness[3], enc_num(4_625))
        self.assertEqual(enc_num(128), b"\x80\x00")


if __name__ == "__main__":
    unittest.main()
