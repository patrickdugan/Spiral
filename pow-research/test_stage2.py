"""Source-derived scoring and history-sensitive uniqueness adversarial cases."""
from dataclasses import replace
import json
import math
import unittest

import pow_lab as p
import primecoin_reference as r
import reorg_registry as reg
import reuse_campaign as reuse


class UpstreamScoringTests(unittest.TestCase):
    def test_source_pins_explicit(self):
        self.assertEqual(len(r.UPSTREAM_COMMIT), 40)
        self.assertEqual(len(r.UPSTREAM_PRIME_CPP_BLOB), 40)
        self.assertEqual(len(r.UPSTREAM_PRIME_H_BLOB), 40)

    def test_target_encoding_roundtrip(self):
        for length in (0, 2, 6, 99, 255):
            for fraction in (0, 1, (1 << 23), r.FRAC_MASK):
                self.assertEqual(r.target_parts(r.encode_target(length, fraction)),
                                 (length, fraction))

    def test_invalid_target_encoding(self):
        for n in (True, -1, 1 << 32, 1.5):
            with self.assertRaises(ValueError):
                r.target_parts(n)
        for n in (-1, 256, True):
            with self.assertRaises(ValueError):
                r.encode_target(n)

    def test_fractional_difficulty_exact_uint64(self):
        self.assertEqual(r.target_fractional_difficulty(r.encode_target(6)), 1 << 32)
        self.assertEqual(r.target_fractional_difficulty(r.encode_target(6, r.FRAC_UNIT // 2)), 1 << 33)
        self.assertEqual(r.target_fractional_difficulty(r.encode_target(6, r.FRAC_MASK)), 1 << 56)

    def test_fractional_fermat_failure(self):
        self.assertEqual(r.fermat(25), (False, ((25 - pow(2, 24, 25)) << 24) // 25))
        self.assertTrue(r.fermat(341)[0])  # 341 is composite: probable != proven
        self.assertEqual(r.fermat(7), (True, 0))

    def test_euler_lagrange_lifchitz_classes(self):
        self.assertEqual(r.ell(11, True), (True, 0))
        self.assertEqual(r.ell(13, False), (True, 0))
        self.assertEqual(r.ell(5, True), (False, 0))
        self.assertEqual(r.ell(11, False), (False, 0))

    def test_chain_terminates_after_first_composite(self):
        self.assertEqual(r.target_parts(r.cunningham_length(12, True))[0], 3)
        self.assertEqual(r.target_parts(r.cunningham_length(12, False))[0], 1)
        self.assertEqual(r.target_parts(r.cunningham_length(6, True))[0], 4)
        with self.assertRaises(ValueError):
            r.cunningham_length(6, True, max_steps=1)

    def test_bitwin_odd_terminal_and_fraction(self):
        score = r.scores(6)
        a, b = r.target_parts(score.cunningham1)[0], r.target_parts(score.cunningham2)[0]
        self.assertEqual((a, b), (4, 2))
        self.assertEqual(r.target_parts(score.bitwin)[0], 2 * b + 1)
        self.assertEqual(r.target_parts(score.bitwin)[1], r.target_parts(score.cunningham2)[1])
        even = r.bi_twin_length(r.encode_target(2, 3), r.encode_target(2, 5))
        self.assertEqual(even, r.encode_target(4, 3))

    def test_bounded_acceptance_and_multiplier_normalization(self):
        target = r.encode_target(2)
        self.assertEqual(r.acceptance_preview(6, 1, target, small_origin_fixture=True)["reason"],
                         "accepted_in_bounded_oracle")
        self.assertEqual(r.acceptance_preview(3, 4, target, small_origin_fixture=True)["reason"],
                         "non_normalized_multiplier")
        self.assertEqual(r.acceptance_preview(12, 1, target, small_origin_fixture=True)["reason"],
                         "accepted_in_bounded_oracle")

    def test_cross_check_mismatch_fixture(self):
        result = r.acceptance_preview(2730, 1, r.encode_target(2), small_origin_fixture=True)
        self.assertEqual(result["reason"], "fermat_cross_check_mismatch")
        self.assertNotEqual(result["scores"], result["fermat_scores"])

    def test_header_bounds_without_native_claim(self):
        target = r.encode_target(6)
        self.assertEqual(r.check_header_bounds(1, 1, target), "header_hash_below_limit")
        self.assertIsNone(r.check_header_bounds(1 << 255, 1, target))
        self.assertEqual(r.check_header_bounds(1 << 255, 1, r.encode_target(5)), "target_length")
        self.assertEqual(r.check_header_bounds((1 << 256) - 1, 1 << 1900, target),
                         "origin_too_large")
        self.assertEqual(r.check_header_bounds(True, 1, target), "noncanonical_header_or_multiplier")

    def test_below_target_and_invalid_toy(self):
        result = r.acceptance_preview(12, 1, r.encode_target(6), small_origin_fixture=True)
        self.assertEqual(result["reason"], "below_target")
        self.assertEqual(r.acceptance_preview(7, 1, r.encode_target(2), small_origin_fixture=True)["reason"],
                         "fixture_origin")


class BranchHistoryTests(unittest.TestCase):
    def setUp(self):
        self.full = reg.Claim.from_center(6, "cunningham1", 4)
        self.suffix = reg.Claim.from_center(12, "cunningham1", 3)

    def test_canonical_recurrence_validation(self):
        self.assertEqual(self.full.terms, (5, 11, 23, 47))
        for bad in ((5, 12), (True, 11), (5, 11, 23, 49)):
            with self.assertRaises(ValueError):
                reg.Claim("cunningham1", bad)
        with self.assertRaises(ValueError):
            reg.Claim("bitcoin", (5, 11))

    def test_exact_policy_allows_suffix(self):
        r = reg.BranchRegistry()
        a = r.append("genesis", "A", [self.full])
        b = r.append(a, "B", [self.suffix])
        self.assertEqual(len(r.branch_claims(b)), 2)
        self.assertEqual(r.blocks[b].height, 2)

    def test_overlap_policy_rejects_suffix(self):
        r = reg.BranchRegistry("overlap")
        a = r.append("genesis", "A", [self.full])
        with self.assertRaises(reg.ClaimRejected):
            r.append(a, "suffix", [self.suffix])

    def test_suffix_policy_rejects_subchain(self):
        r = reg.BranchRegistry("suffix")
        a = r.append("genesis", "A", [self.full])
        with self.assertRaises(reg.ClaimRejected):
            r.append(a, "suffix", [self.suffix])

    def test_exact_duplicate_rejected_without_state_mutation(self):
        r = reg.BranchRegistry()
        a = r.append("genesis", "A", [self.full])
        before = set(r.blocks)
        with self.assertRaises(reg.ClaimRejected):
            r.append(a, "B", [self.full])
        self.assertEqual(before, set(r.blocks))
        self.assertEqual(r.tip, "genesis")

    def test_same_block_duplicate_rejected(self):
        r = reg.BranchRegistry()
        with self.assertRaises(reg.ClaimRejected):
            r.append("genesis", "A", [self.full, self.full])
        self.assertEqual(len(r.blocks), 1)

    def test_forks_can_each_include_same_artifact(self):
        r = reg.BranchRegistry()
        a = r.append("genesis", "A", [self.full])
        b = r.append("genesis", "B", [self.full])
        self.assertNotEqual(a, b)
        self.assertEqual(len(r.select_tip(a)["active_keys"]), 1)
        self.assertEqual(len(r.select_tip(b)["active_keys"]), 1)

    def test_rollback_and_activation_on_switch(self):
        r = reg.BranchRegistry()
        a = r.append("genesis", "A", [self.full])
        b = r.append("genesis", "B", [self.suffix])
        r.select_tip(a)
        result = r.select_tip(b)
        self.assertEqual(len(result["rolled_back"]), 1)
        self.assertEqual(len(result["activated"]), 1)
        self.assertEqual(result["active_keys"], [self.suffix.key])

    def test_invalid_parent_and_unknown_tip(self):
        r = reg.BranchRegistry()
        with self.assertRaises(ValueError):
            r.append("missing", "child", [self.full])
        with self.assertRaises(ValueError):
            r.select_tip("missing")
        self.assertEqual(r.tip, "genesis")

    def test_bounded_claim_batch_and_label(self):
        r = reg.BranchRegistry()
        with self.assertRaises(ValueError):
            r.append("genesis", "", [])
        with self.assertRaises(ValueError):
            r.append("genesis", "á", [])
        with self.assertRaises(ValueError):
            r.append("genesis", "too_many", (self.full for _ in range(10_000_000)))

    def test_clash_semantics_are_explicit(self):
        self.assertFalse(reg.clash(self.full, self.suffix, "exact"))
        self.assertTrue(reg.clash(self.full, self.suffix, "suffix"))
        self.assertTrue(reg.clash(self.full, self.suffix, "overlap"))
        with self.assertRaises(ValueError):
            reg.clash(self.full, self.suffix, "unknown")


class OccupancyTests(unittest.TestCase):
    def test_determinism_and_bounds(self):
        self.assertEqual(reuse.report(), reuse.report())
        for n in (3, 17, True):
            with self.assertRaises(ValueError):
                reuse.occupancy(n)
        with self.assertRaises(ValueError):
            reuse.occupancy(8, contexts=0)
        with self.assertRaises(ValueError):
            reuse.occupancy(8, tickets_per_context=True)

    def test_accounting_partition(self):
        for bucket in reuse.report()["buckets"]:
            self.assertEqual(bucket["unique_origins"] + bucket["within_context_reuses"]
                             + bucket["new_context_old_origin"], bucket["ticket_count"])
            self.assertLessEqual(bucket["unique_origins"], bucket["origin_domain"])
            self.assertFalse(bucket["hash_collision_claimed"])

    def test_known_occupancy_fixture(self):
        self.assertEqual([b["unique_origins"] for b in reuse.report()["buckets"]],
                         [127, 396, 637, 741])
        self.assertEqual([b["within_context_reuses"] for b in reuse.report()["buckets"]],
                         [299, 74, 22, 3])

    def test_branch_fixture_conclusions(self):
        b = reuse.report()["branch_scenario"]
        self.assertTrue(b["exact_duplicate_same_branch_rejected"])
        self.assertTrue(b["overlap_suffix_rejected"])
        self.assertEqual(b["cross_branch_rolled_back"], 1)
        self.assertEqual(b["cross_branch_activated"], 1)
        self.assertEqual(b["distinct_keys_after_suffix"], 3)


if __name__ == "__main__":
    unittest.main()
