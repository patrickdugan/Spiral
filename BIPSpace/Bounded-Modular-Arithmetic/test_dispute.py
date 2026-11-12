"""Tests for binding, local completeness and compiler encoding hazards."""
from dataclasses import replace
import itertools
import unittest
from dispute import (Instruction, Program, Trace, Opening, membership, input_fraud,
                     encoding_fraud, output_fraud, arithmetic_fraud, gate_openings, find_fraud)
from muladdmod import muladdmod, encode_modulus, encode_residue

INSTANCE = bytes.fromhex('11' * 32)
OTHER = bytes.fromhex('22' * 32)
COUNTS = {'exhaustive_traces': 0, 'wrong_traces_challenged': 0}


def program():
    return Program(17, (5, 5, 0), (Instruction(0, 1, 2), Instruction(3, 0, 2)), 6)


def script_bool(value):
    # Bitcoin Core CastToBool, used only to exhibit the cross-encoding hazard.
    for i, byte in enumerate(value):
        if byte:
            return not (i == len(value) - 1 and byte == 0x80)
    return False


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.p = program()
        self.good = Trace(self.p, INSTANCE, self.p.evaluate())
        values = list(self.p.evaluate()); values[3] = b'\x04'
        self.bad = Trace(self.p, INSTANCE, tuple(values))

    def test_correct_trace_has_no_fraud(self):
        self.assertIsNone(find_fraud(self.p, INSTANCE, self.good))

    def test_bad_arithmetic_has_authenticated_fraud(self):
        self.assertEqual(find_fraud(self.p, INSTANCE, self.bad), ('arithmetic', 0))

    def test_operand_substitution_fails_membership(self):
        ps = list(gate_openings(self.p, self.good, 0))
        ps[0] = replace(ps[0], value=b'\x04')
        self.assertFalse(arithmetic_fraud(self.p, INSTANCE, self.good.root, 0, tuple(ps)))

    def test_source_index_substitution_rejected(self):
        ps = list(gate_openings(self.p, self.good, 0)); ps[0] = self.good.open(2)
        self.assertTrue(membership(self.p, INSTANCE, self.good.root, ps[0]))
        self.assertFalse(arithmetic_fraud(self.p, INSTANCE, self.good.root, 0, tuple(ps)))

    def test_cross_instance_replay_rejected(self):
        self.assertFalse(arithmetic_fraud(self.p, OTHER, self.bad.root, 0,
                                         gate_openings(self.p, self.bad, 0)))

    def test_modulus_swap_rejected(self):
        q = Program(7, self.p.inputs, self.p.gates, 6)
        self.assertFalse(arithmetic_fraud(q, INSTANCE, self.bad.root, 0,
                                         gate_openings(self.p, self.bad, 0)))

    def test_program_rebinding_rejected(self):
        q = Program(17, self.p.inputs, (Instruction(0, 0, 0), self.p.gates[1]), 6)
        self.assertFalse(membership(q, INSTANCE, self.bad.root, self.bad.open(3)))

    def test_public_input_substitution_is_challengeable(self):
        q = Program(17, (4, 5, 0), self.p.gates, 6)
        t = Trace(self.p, INSTANCE, q.evaluate())
        # All its gates are consistent. The public-input predicate still catches it.
        self.assertFalse(arithmetic_fraud(self.p, INSTANCE, t.root, 0,
                                          gate_openings(self.p, t, 0)))
        self.assertTrue(input_fraud(self.p, INSTANCE, t.root, t.open(0)))

    def test_wrong_claimed_output_is_challengeable(self):
        p = Program(17, self.p.inputs, self.p.gates, 7)
        t = Trace(p, INSTANCE, p.evaluate())
        self.assertFalse(arithmetic_fraud(p, INSTANCE, t.root, 1, gate_openings(p, t, 1)))
        self.assertTrue(output_fraud(p, INSTANCE, t.root, t.open(p.count - 1)))

    def test_output_rebinding_rejects_old_membership(self):
        p = Program(17, self.p.inputs, self.p.gates, 7)
        self.assertFalse(membership(p, INSTANCE, self.good.root, self.good.open(4)))

    def test_malformed_result_is_challengeable(self):
        for bad in (b'', b'\x08\x00', b'\x11', b'\xff', bytes(520)):
            values = list(self.p.evaluate()); values[3] = bad
            t = Trace(self.p, INSTANCE, tuple(values))
            self.assertTrue(encoding_fraud(self.p, INSTANCE, t.root, t.open(3)))
            self.assertFalse(arithmetic_fraud(self.p, INSTANCE, t.root, 0,
                                              gate_openings(self.p, t, 0)))

    def test_wrong_path_length_and_hash_rejected(self):
        proof = self.bad.open(3)
        for bad in (replace(proof, siblings=proof.siblings[:-1]),
                    replace(proof, siblings=proof.siblings + (bytes(32),)),
                    replace(proof, siblings=(bytes(31),) + proof.siblings[1:])):
            self.assertFalse(membership(self.p, INSTANCE, self.bad.root, bad))

    def test_wrong_root_and_index_rejected(self):
        proof = self.bad.open(3)
        self.assertFalse(membership(self.p, INSTANCE, bytes(32), proof))
        for index in (-1, self.p.count, 2**32, True):
            self.assertFalse(membership(self.p, INSTANCE, self.bad.root,
                                        replace(proof, index=index)))

    def test_padding_is_not_a_trace_register(self):
        with self.assertRaises(ValueError): self.bad.open(self.p.count)

    def test_trace_length_bound(self):
        with self.assertRaises(ValueError): Trace(self.p, INSTANCE, self.p.evaluate()[:-1])

    def test_forward_reference_rejected(self):
        with self.assertRaises(ValueError): Program(17, (0,), (Instruction(1, 0, 0),), 0)

    def test_each_modified_register_is_detected(self):
        values = self.p.evaluate()
        for i, v in enumerate(values):
            for replacement in range(self.p.modulus):
                changed = list(values); changed[i] = bytes([replacement])
                t = Trace(self.p, INSTANCE, tuple(changed))
                self.assertEqual(find_fraud(self.p, INSTANCE, t) is None,
                                 replacement == int.from_bytes(v, 'little'))

    def test_exhaustive_local_completeness(self):
        p = Program(3, (1, 2, 0), (Instruction(0, 1, 2), Instruction(3, 0, 2)), 2)
        truth = p.evaluate()
        for values in itertools.product(range(3), repeat=p.count):
            encoded = tuple(bytes([x]) for x in values)
            t = Trace(p, INSTANCE, encoded)
            challenged = find_fraud(p, INSTANCE, t) is not None
            self.assertEqual(challenged, encoded != truth)
            COUNTS['exhaustive_traces'] += 1
            COUNTS['wrong_traces_challenged'] += int(challenged)


class CompositionTests(unittest.TestCase):
    def f(self, a, b, c, p):
        args = tuple(encode_residue(x, p) for x in (a, b, c)) + (encode_modulus(p),)
        return int.from_bytes(muladdmod(*args), 'little')

    def test_horner_chain(self):
        coefficients = (3, 7, 2, 11, 5)
        for x in range(17):
            h = 0
            for coefficient in reversed(coefficients): h = self.f(h, x, coefficient, 17)
            self.assertEqual(h, sum(v * x**i for i, v in enumerate(coefficients)) % 17)

    def test_quadratic_extension_five_fused_calls(self):
        # Basis u^2=3 over F_17. 3 is a nonsquare; the basis is fixed by the program.
        for a, b, c, d in itertools.product(range(4), repeat=4):
            t = self.f(b, d, 0, 17); v = self.f(a, c, 0, 17)
            real = self.f(3, t, v, 17)
            imag = self.f(b, c, self.f(a, d, 0, 17), 17)
            self.assertEqual((real, imag), ((a*c + 3*b*d) % 17, (a*d+b*c) % 17))

    def test_negative_zero_requires_explicit_byte_comparison(self):
        r = muladdmod(b'\x80', b'\x01', b'\x00', b'\xfb')
        self.assertEqual(r, b'\x80')
        self.assertFalse(script_bool(r))
        self.assertNotEqual(r, b'\x00')

    def test_fixed_width_one_is_not_minimalif_one(self):
        r = muladdmod(encode_residue(1, 257), encode_residue(1, 257),
                      encode_residue(0, 257), encode_modulus(257))
        self.assertEqual(r, b'\x01\x00')
        self.assertNotIn(r, (b'', b'\x01'))

    def test_composite_ring_zero_divisors(self):
        self.assertEqual(self.f(3, 5, 0, 15), 0)
        self.assertFalse(any(self.f(3, x, 0, 15) == 1 for x in range(15)))


if __name__ == '__main__':
    unittest.main()
