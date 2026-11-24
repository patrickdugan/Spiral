import importlib.util
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


PROFILE = {
    'channel_hash': 'blake2s', 'channel_salt': 0,
    'pcs_config': {'pow_bits': 26, 'lifting_log_size': 26,
                   'fri_config': {'log_last_layer_degree_bound': 0, 'log_blowup_factor': 1,
                                  'n_queries': 70, 'fold_step': 1}},
    'preprocessed_trace': 'canonical_without_pedersen',
    'store_polynomials_coefficients': False, 'include_all_preprocessed_columns': False,
}


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
        self.proof = {
            'claim': {'public_data': {'public_memory': {'output': self.output}}},
            'stark_proof': {'config': copy.deepcopy(PROFILE['pcs_config'])},
            'channel_salt': PROFILE['channel_salt'],
            'preprocessed_trace_variant': PROFILE['preprocessed_trace'],
        }

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

    def test_exact_profile_accepts_stock_normalized_and_extended_encodings(self):
        expected = {key: PROFILE[key] for key in ('channel_hash', 'channel_salt', 'pcs_config', 'preprocessed_trace')}
        self.assertEqual(self.audit.pinned_proof_profile(self.proof, PROFILE), expected)
        stark = self.proof.pop('stark_proof')
        self.proof['extended_stark_proof'] = {'proof': stark, 'aux': {}}
        self.assertEqual(self.audit.pinned_proof_profile(self.proof, PROFILE), expected)
        with self.assertRaisesRegex(ValueError, 'ambiguous or invalid Cairo proof format'):
            self.audit.pinned_proof_profile(self.proof | {'stark_proof': stark}, PROFILE)

    def test_refuses_each_changed_profile_field_and_numeric_aliases(self):
        paths = [
            (('stark_proof', 'config', 'pow_bits'), 1),
            (('stark_proof', 'config', 'lifting_log_size'), None),
            (('stark_proof', 'config', 'fri_config', 'log_last_layer_degree_bound'), 1),
            (('stark_proof', 'config', 'fri_config', 'log_blowup_factor'), True),
            (('stark_proof', 'config', 'fri_config', 'n_queries'), 4),
            (('stark_proof', 'config', 'fri_config', 'fold_step'), 1.0),
            (('channel_salt',), False),
            (('preprocessed_trace_variant',), 'canonical_small'),
        ]
        for path, changed in paths:
            proof = copy.deepcopy(self.proof)
            field = proof
            for key in path[:-1]:
                field = field[key]
            field[path[-1]] = changed
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'pinned Shinigami security profile'):
                self.audit.pinned_proof_profile(proof, PROFILE)
        self.proof['stark_proof']['config'].pop('pow_bits')
        with self.assertRaisesRegex(ValueError, 'pinned Shinigami security profile'):
            self.audit.pinned_proof_profile(self.proof, PROFILE)

    def test_audit_gates_profile_then_exercises_all_public_controls_in_the_verifier(self):
        calls = []

        def stock_verifier(_verifier, path, _cwd, _timeout):
            candidate = json.loads(path.read_bytes())
            self.audit.pinned_proof_profile(candidate, PROFILE)
            actual = candidate['claim']['public_data']['public_memory']['output']
            changed = [i for i, cells in enumerate(zip(actual, self.output)) if cells[0] != cells[1]]
            calls.append(changed)
            if not changed:
                return 0, 0.01, b'Verified proof successfully\n'
            return 1, 0.01, b'Verification failed\n'

        with tempfile.TemporaryDirectory(prefix='cashu-profile-test-', dir=Path.cwd()) as scratch:
            root = Path(scratch)
            proof = root / 'proof.json'
            proof.write_text(json.dumps(self.proof), encoding='utf-8')
            with patch.object(self.audit.tempfile, 'tempdir', scratch), patch.object(self.audit, 'verify_one', stock_verifier):
                _, values, _, controls, verified_profile = self.audit.independent_verify(
                    Path('scarb-verify'), proof, root, self.expected, PROFILE, 10, io.BytesIO(),
                )
                self.assertEqual(values, self.expected)
                self.assertEqual(verified_profile['pcs_config'], PROFILE['pcs_config'])
                self.assertEqual([control['index'] for control in controls], list(range(24)))
                self.assertEqual(calls, [[]] + [[index] for index in range(24)])

                self.proof['stark_proof']['config']['pow_bits'] = 1
                proof.write_text(json.dumps(self.proof), encoding='utf-8')
                calls.clear()
                with self.assertRaisesRegex(ValueError, 'pinned Shinigami security profile'):
                    self.audit.independent_verify(Path('scarb-verify'), proof, root, self.expected, PROFILE,
                                                  10, io.BytesIO())
                self.assertEqual(calls, [])
