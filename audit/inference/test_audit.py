"""Fast deterministic regression witnesses; no snapshot or network required."""
import unittest

from run_audit import pipeline_counterexamples, route_budget_witness, greedy_oracle_witness


class InferenceAuditWitnesses(unittest.TestCase):
    def test_unmatched_observation_budget_witness(self):
        result = route_budget_witness()
        self.assertFalse(result["retry3"]["delivered"])
        self.assertFalse(result["oracle3"]["delivered"])
        self.assertTrue(result["retry8"]["delivered"])
        self.assertTrue(result["oracle8"]["delivered"])
        self.assertEqual(result["retry8"]["failed_attempts"], 3)
        self.assertEqual(result["oracle8"]["failed_attempts"], 0)

    def test_greedy_oracle_is_not_horizon_optimum(self):
        result = greedy_oracle_witness()
        self.assertEqual(result["production_greedy_oracle_successes"], 1)
        self.assertEqual(result["feasible_alternative_successes"], 2)

    def test_empty_interval_has_unjustified_exact_zero_in_old_code(self):
        result = pipeline_counterexamples()["empty_cluster_interval"]
        self.assertEqual(result["cluster_n"], 0)
        self.assertEqual((result["ci95_lower"], result["ci95_upper"]), (0, 0))

    def test_single_cluster_has_zero_width_in_old_code(self):
        result = pipeline_counterexamples()["single_cluster_interval"]
        self.assertEqual(result["cluster_n"], 1)
        self.assertEqual(result["ci95_half_width"], 0)

    def test_duplicate_input_order_changes_old_estimate(self):
        result = pipeline_counterexamples()
        self.assertLess(result["duplicate_last_wins_a"][0][2], 0)
        self.assertGreater(result["duplicate_last_wins_b"][0][2], 0)

    def test_unmatched_rows_are_silently_dropped_in_old_code(self):
        result = pipeline_counterexamples()
        self.assertEqual(len(result["missing_pair_ignored"]), 1)
        self.assertEqual(result["all_missing_pair_returns_empty"], [])


if __name__ == "__main__":
    unittest.main()
