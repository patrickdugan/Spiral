"""Exact combinatorial oracles for the PoW shortcut scenario."""
import unittest
from fractions import Fraction
from math import comb

from miner_asymmetry import majority_tail, max_speedup_before_majority, rate_share, scenario


class ExactTests(unittest.TestCase):
    def test_baseline_and_speedup(self):
        self.assertEqual(rate_share(Fraction(1, 10), Fraction(10)), Fraction(10, 19))
        self.assertEqual(rate_share(Fraction(1, 10), Fraction(1)), Fraction(1, 10))
        self.assertEqual(max_speedup_before_majority(Fraction(1, 10)), 9)

    def test_exact_small_enumeration(self):
        for n in range(1, 9):
            for numerator in range(5):
                p = Fraction(numerator, 4)
                count = 0
                total = 4**n
                # Independent alternate oracle over sequences of 4 equiprobable symbols.
                for index in range(total):
                    digits = []
                    value = index
                    for _ in range(n):
                        digits.append(value % 4)
                        value //= 4
                    successes = sum(x < numerator for x in digits)
                    if successes > n // 2:
                        count += 1
                self.assertEqual(majority_tail(p, n), Fraction(count, total))

    def test_fair_coin_odd_window(self):
        for n in (1, 3, 5, 19, 21):
            self.assertEqual(majority_tail(Fraction(1, 2), n), Fraction(1, 2))

    def test_even_window_ties(self):
        self.assertEqual(majority_tail(Fraction(1, 2), 2), Fraction(1, 4))
        self.assertEqual(majority_tail(Fraction(1, 2), 4), Fraction(5, 16))

    def test_monotonic(self):
        for n in (1, 2, 7, 21):
            values = [majority_tail(Fraction(i, 10), n) for i in range(11)]
            self.assertEqual(values, sorted(values))

    def test_extremes(self):
        self.assertEqual(majority_tail(Fraction(0), 21), 0)
        self.assertEqual(majority_tail(Fraction(1), 21), 1)
        self.assertIsNone(max_speedup_before_majority(Fraction(0)))
        self.assertEqual(max_speedup_before_majority(Fraction(1)), 0)

    def test_validation(self):
        for share, speed in ((Fraction(-1), Fraction(1)), (Fraction(1, 2), 0),
                             (Fraction(2), Fraction(1))):
            with self.assertRaises(ValueError):
                rate_share(share, speed)
        for blocks in (0, -1, 1025):
            with self.assertRaises(ValueError):
                majority_tail(Fraction(1, 2), blocks)
        for args in ((-1, 10, 2, 21), (11, 10, 2, 21), (1, 0, 2, 21),
                     (1, 10, 0, 21)):
            with self.assertRaises(ValueError):
                scenario(*args)

    def test_report(self):
        result = scenario(1, 10, 10, 21)
        self.assertEqual(result["effective_share"], "10/19")
        self.assertEqual(result["critical_speedup"], "9")
        self.assertEqual(result["evidence_class"], "exact_finite_model")


if __name__ == "__main__":
    unittest.main()
