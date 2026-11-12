"""Deterministic semantics and differential tests; no Bitcoin Core execution."""
import itertools
import random
import unittest
from muladdmod import (ScriptError, DRAFT_COST, muladdmod, muladdmod_bytewise,
                       execute, encode_modulus, encode_residue)

COUNTS = {"exhaustive_vectors": 0, "random_vectors": 0, "boundary_vectors": 0}


def args(a, b, c, m):
    return tuple(encode_residue(x, m) for x in (a, b, c)) + (encode_modulus(m),)


class ArithmeticTests(unittest.TestCase):
    def assert_backends(self, a, b, c, m):
        operands = args(a, b, c, m)
        oracle = muladdmod(*operands)
        self.assertEqual(oracle, muladdmod_bytewise(*operands))
        self.assertEqual(int.from_bytes(oracle, "little"), (a * b + c) % m)
        self.assertEqual(len(oracle), len(operands[-1]))

    def test_example(self):
        self.assertEqual(muladdmod(*args(7, 11, 3, 17)), b"\x0c")

    def test_exhaustive_small_rings(self):
        for m in range(2, 14):
            for a, b, c in itertools.product(range(m), repeat=3):
                self.assert_backends(a, b, c, m)
                COUNTS["exhaustive_vectors"] += 1

    def test_seeded_all_widths(self):
        rng = random.Random(20261112)
        for width in range(1, 33):
            for _ in range(64):
                m = rng.randrange(max(2, 1 << (8 * (width - 1))), 1 << (8 * width))
                a, b, c = (rng.randrange(m) for _ in range(3))
                self.assert_backends(a, b, c, m)
                COUNTS["random_vectors"] += 1

    def test_width_boundaries(self):
        for width in range(1, 33):
            ms = {max(2, 1 << (8 * (width - 1))), (1 << (8 * width)) - 1}
            for m in ms:
                for a, b, c in itertools.product({0, 1, m - 1}, repeat=3):
                    self.assert_backends(a, b, c, m)
                    COUNTS["boundary_vectors"] += 1

    def test_maximum_modulus(self):
        m = (1 << 256) - 1
        self.assert_backends(m - 1, m - 1, m - 1, m)
        self.assertEqual(muladdmod(*args(m - 1, m - 1, m - 1, m)), bytes(32))

    def test_addition_and_multiplication(self):
        self.assertEqual(muladdmod(*args(13, 1, 9, 17)), b"\x05")
        self.assertEqual(muladdmod(*args(13, 9, 0, 17)), b"\x0f")

    def test_inverse_certificate(self):
        self.assertEqual(muladdmod(*args(3, 6, 0, 17)), b"\x01")
        for witness in range(17):
            self.assertNotEqual(muladdmod(*args(0, witness, 0, 17)), b"\x01")

    def test_composite_ring_is_allowed(self):
        self.assertEqual(muladdmod(*args(3, 5, 0, 15)), b"\x00")

    def test_koalabear_width_and_residue(self):
        m = (1 << 31) - (1 << 24) + 1
        operands = args(m - 1, m - 1, 0, m)
        self.assertEqual(len(operands[-1]), 4)
        self.assertEqual(muladdmod(*operands), b"\x01\x00\x00\x00")

    def test_bytes_are_unsigned(self):
        self.assertEqual(muladdmod(b"\x81", b"\x01", b"\x00", b"\xfb"), b"\x81")

    def test_wrong_modulus_can_change_a_verdict(self):
        # A committed p=17 rejects the claim 5*5 = 4. An unpinned p=7 accepts it.
        self.assertNotEqual(muladdmod(*args(5, 5, 0, 17)), b"\x04")
        self.assertEqual(muladdmod(*args(5, 5, 0, 7)), b"\x04")

    def test_unbound_operands_can_change_a_verdict(self):
        # Correct arithmetic alone cannot authenticate the operator's actual data.
        self.assertEqual(muladdmod(*args(5, 5, 0, 17)), b"\x08")
        self.assertNotEqual(muladdmod(*args(4, 5, 0, 17)), b"\x08")


class EncodingTests(unittest.TestCase):
    def bad(self, operands):
        for fn in (muladdmod, muladdmod_bytewise):
            with self.assertRaises(ScriptError):
                fn(*operands)

    def test_empty_modulus(self):
        self.bad((b"", b"", b"", b""))

    def test_zero_and_one_moduli(self):
        for m in (b"\x00", b"\x01"):
            self.bad((b"\x00", b"\x00", b"\x00", m))

    def test_nonminimal_modulus(self):
        self.bad((bytes(2), bytes(2), bytes(2), b"\x11\x00"))

    def test_oversized_modulus(self):
        self.bad((bytes(33), bytes(33), bytes(33), b"\x01" * 33))

    def test_wrong_residue_width_each_position(self):
        for i in range(3):
            for replacement in (b"", bytes(2)):
                operands = list(args(1, 1, 1, 17))
                operands[i] = replacement
                self.bad(tuple(operands))

    def test_noncanonical_residue_each_position(self):
        for i in range(3):
            for replacement in (b"\x11", b"\xff"):
                operands = list(args(1, 1, 1, 17))
                operands[i] = replacement
                self.bad(tuple(operands))

    def test_fixed_width_zero(self):
        self.assertEqual(muladdmod(*args(0, 0, 0, 257)), bytes(2))
        self.bad((b"", bytes(2), bytes(2), encode_modulus(257)))

    def test_nonbytes(self):
        self.bad((1, b"\x01", b"\x00", b"\x11"))


class ExecutionTests(unittest.TestCase):
    def test_stack_effect_and_exact_budget(self):
        stack = [b"prefix", *args(7, 11, 3, 17)]
        self.assertEqual(execute(stack, DRAFT_COST), 0)
        self.assertEqual(stack, [b"prefix", b"\x0c"])

    def test_short_budget(self):
        stack = list(args(7, 11, 3, 17))
        before = stack.copy()
        with self.assertRaises(ScriptError):
            execute(stack, DRAFT_COST - 1)
        self.assertEqual(stack, before)

    def test_stack_underflow(self):
        for length in range(4):
            with self.assertRaises(ScriptError):
                execute([b"\x01"] * length, 100)

    def test_shared_budget(self):
        budget = 100
        for _ in range(2):
            budget = execute(list(args(7, 11, 3, 17)), budget)
        self.assertEqual(budget, 0)
        with self.assertRaises(ScriptError):
            execute(list(args(7, 11, 3, 17)), budget)

    def test_bytewise_execution(self):
        stack = list(args(7, 11, 3, 17))
        self.assertEqual(execute(stack, 51, bytewise=True), 1)
        self.assertEqual(stack, [b"\x0c"])

    def test_invalid_budget(self):
        for budget in (-1, True, 50.0):
            with self.assertRaises(ScriptError):
                execute(list(args(7, 11, 3, 17)), budget)

    def test_failure_atomicity(self):
        stack = [b"prefix", b"\xff", b"\x01", b"\x01", b"\x11"]
        original = stack.copy()
        with self.assertRaises(ScriptError):
            execute(stack, 100)
        self.assertEqual(stack, original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
