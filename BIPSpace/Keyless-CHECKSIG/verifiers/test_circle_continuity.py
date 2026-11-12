import copy
import unittest
from audit_circle_continuity import audit


def records():
    return [
        {'format': 'circle-stage-v1', 'stage': 0, 'script_hex': '51',
         'input_hex': [], 'hint_hex': ['01'], 'expected_output_hex': ['11'*32]},
        {'format': 'circle-stage-v1', 'stage': 1, 'script_hex': '51',
         'input_hex': ['11'*32], 'hint_hex': ['02'], 'expected_output_hex': ['22'*32]},
    ]


class CircleContinuityTests(unittest.TestCase):
    def test_complete_ordered_export(self):
        report = audit(records(), 2)
        self.assertEqual(report['matching_boundary_count'], 1)
        self.assertEqual(report['hint_stack_items'], 2)
        self.assertEqual(report['intermediate_input_items'], 1)
        self.assertFalse(report['onchain_stage_continuity_enforced'])
        self.assertFalse(report['cryptographic_proof_verified_by_this_audit'])

    def test_pin_program_order(self):
        rs = records()
        pin = audit(rs, 2)['program_manifest_sha256']
        self.assertTrue(audit(rs, 2, pin)['program_manifest_independently_pinned'])
        rs[1]['script_hex'] = '52'
        with self.assertRaisesRegex(ValueError, 'manifest'):
            audit(rs, 2, pin)

    def test_reject_missing_or_extra_stage(self):
        for rs in (records()[:1], records() + [records()[1]]):
            with self.assertRaises(ValueError):
                audit(rs, 2)

    def test_reject_reorder_and_duplicate_number(self):
        with self.assertRaises(ValueError):
            audit(list(reversed(records())), 2)
        rs = records()
        rs[1]['stage'] = 0
        with self.assertRaises(ValueError):
            audit(rs, 2)

    def test_reject_spliced_state(self):
        rs = records()
        rs[1]['input_hex'] = ['33'*32]
        with self.assertRaisesRegex(ValueError, 'boundary'):
            audit(rs, 2)

    def test_reject_false_initial_state(self):
        rs = records()
        rs[0]['input_hex'] = ['00'*32]
        with self.assertRaises(ValueError):
            audit(rs, 2)

    def test_reject_malformed_terminal_shape(self):
        for out in ([], ['01'], ['11'*32, '22'*32]):
            rs = records()
            rs[-1]['expected_output_hex'] = out
            with self.assertRaises(ValueError):
                audit(rs, 2)

    def test_host_audit_does_not_claim_cryptographic_validation(self):
        rs = records()
        rs[0]['expected_output_hex'] = rs[1]['input_hex'] = ['99'*32]
        report = audit(rs, 2)
        self.assertTrue(report['fixture_continuity_verified'])
        self.assertFalse(report['cryptographic_proof_verified_by_this_audit'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
