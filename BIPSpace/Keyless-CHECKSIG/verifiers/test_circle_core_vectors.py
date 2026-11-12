import unittest
from circle_core_vectors import compact, convert, push, scan


def stage(program='51', hints=(), inputs=(), outputs=('01',)):
    return {'format': 'circle-stage-v1', 'stage': 0, 'script_hex': program,
            'hint_hex': list(hints), 'input_hex': list(inputs),
            'expected_output_hex': list(outputs)}


class CircleCoreExportTests(unittest.TestCase):
    def test_minimal_pushes(self):
        for value, opcode in [(b'', 0), (b'\x01', 81), (b'\x10', 96), (b'\x81', 79)]:
            self.assertEqual(push(value), bytes([opcode]))
        self.assertEqual(push(b'\x00'), b'\x01\x00')
        self.assertEqual(push(bytes(76))[:2], b'\x4c\x4c')
        self.assertEqual(push(bytes(256))[:3], b'\x4d\x00\x01')
        with self.assertRaises(ValueError):
            push(bytes(521))

    def test_push_payload_does_not_execute_success_opcode(self):
        self.assertEqual(scan(b'\x01\x50\x51'), [1, 81])
        vectors, report = convert([stage(program='0150', outputs=('50',))])
        self.assertEqual(len(vectors), 3)
        self.assertEqual(report['stage_count'], 1)

    def test_success_opcode_rejected(self):
        with self.assertRaisesRegex(ValueError, 'OP_SUCCESS'):
            convert([stage(program='50')])

    def test_cat_is_the_only_allowed_success_opcode(self):
        convert([stage(program='7e')])
        for code in (127, 131, 149, 187, 254):
            with self.assertRaises(ValueError):
                convert([stage(program=bytes([code]).hex())])

    def test_forbid_signature_and_codeseparator_inside_stage(self):
        for code in (171, 172, 173, 174, 175, 186):
            with self.assertRaises(ValueError):
                convert([stage(program=bytes([code]).hex())])

    def test_truncated_pushes_rejected(self):
        for raw in (b'\x02\x01', b'\x4c', b'\x4d\x00', b'\x4e\x01\x00\x00\x00'):
            with self.assertRaises(ValueError):
                scan(raw)

    def test_stage_set_must_be_complete(self):
        with self.assertRaises(ValueError):
            convert([])
        record = stage()
        record['stage'] = 1
        with self.assertRaises(ValueError):
            convert([record])
        with self.assertRaises(ValueError):
            convert([stage(), stage()])

    def test_format_is_required(self):
        record = stage()
        del record['format']
        with self.assertRaises(ValueError):
            convert([record])

    def test_three_vector_controls(self):
        vectors, report = convert([stage()])
        self.assertEqual([v['expected'] for v in vectors], [True, False, True])
        self.assertTrue(vectors[2]['disable_txcommit'])
        a, b = bytes.fromhex(vectors[0]['tx_hex']), bytes.fromhex(vectors[1]['tx_hex'])
        self.assertEqual(len(a), len(b))
        self.assertEqual(sum(x != y for x, y in zip(a, b)), 1)
        self.assertEqual(vectors[1]['tx_hex'], vectors[2]['tx_hex'])
        self.assertFalse(report['composed_verifier'])
        self.assertFalse(report['payout_relation_proved'])

    def test_initial_stack_budget_is_honest(self):
        vectors, report = convert([stage(hints=['00'] * 1000)])
        self.assertEqual(len(vectors), 2)
        self.assertEqual([v['expected'] for v in vectors], [False, False])
        self.assertFalse(report['all_initial_stacks_fit'])
        self.assertEqual(report['stages'][0]['witness_stack_items'], 1001)

    def test_oversized_hint_is_expected_to_fail_in_core(self):
        vectors, report = convert([stage(hints=[bytes(521).hex()])])
        self.assertEqual([v['expected'] for v in vectors], [False, False])
        self.assertFalse(report['all_initial_stacks_fit'])

    def test_compactsize_boundaries(self):
        self.assertEqual(compact(252), b'\xfc')
        self.assertEqual(compact(253), b'\xfd\xfd\x00')
        self.assertEqual(compact(65536), b'\xfe\x00\x00\x01\x00')
        with self.assertRaises(ValueError):
            compact(-1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
