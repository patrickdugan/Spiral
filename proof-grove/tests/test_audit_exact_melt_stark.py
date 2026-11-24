import importlib.util
import json
from pathlib import Path
import unittest


def load_audit():
    script = Path(__file__).resolve().parents[1] / 'scripts' / 'audit-exact-melt-stark.py'
    spec = importlib.util.spec_from_file_location('audit_exact_melt_stark', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HistoricalStatementTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = load_audit()
        cls.receipt = json.loads(cls.audit.EXECUTION.read_bytes())

    def setUp(self):
        self.words = [hex(word) for word in range(21)]
        self.expected = self.audit.expected_public_output(self.receipt, self.words)
        self.output = [[index, [(word >> (32 * limb)) & 0xffffffff for limb in range(8)]]
                       for index, word in enumerate(self.expected)]
        self.proof = {'claim': {'public_data': {'public_memory': {'output': self.output}}}}

    def test_exact_public_memory_includes_the_archived_bootloader_envelope(self):
        self.assertEqual(len(self.expected), 24)
        self.assertEqual(self.expected[:3], [1, 23, int(self.receipt['program']['program_hash'], 16)])
        self.assertEqual(self.audit.pinned_proof_output(self.proof, self.expected), (self.output, self.expected))

    def test_rejects_a_changed_word_even_under_the_same_program(self):
        for index, (_, limbs) in enumerate(self.output):
            with self.subTest(index=index):
                limbs[0] ^= 1
                with self.assertRaisesRegex(ValueError, 'differs from the pinned melt-funded statement'):
                    self.audit.pinned_proof_output(self.proof, self.expected)
                limbs[0] ^= 1

    def test_rejects_missing_cells_and_invalid_value_ids(self):
        last = self.output.pop()
        with self.assertRaisesRegex(ValueError, 'unexpected public memory'):
            self.audit.pinned_proof_output(self.proof, self.expected)
        self.output.append([2**32, last[1]])
        with self.assertRaisesRegex(ValueError, 'invalid Cairo public output cell'):
            self.audit.pinned_proof_output(self.proof, self.expected)

    def test_rejects_noncanonical_felts(self):
        for invalid in [1, '0x00', '0xA', hex(self.audit.FIELD_PRIME)]:
            self.words[0] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.audit.expected_public_output(self.receipt, self.words)
