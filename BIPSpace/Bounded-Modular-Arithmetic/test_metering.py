import random
import unittest
from metering import compact_size, witness_size, initial_budget, call_ceiling


class MeteringTests(unittest.TestCase):
    def test_compactsize_boundaries(self):
        expected = {0:'00', 252:'fc', 253:'fdfd00', 65535:'fdffff',
                    65536:'fe00000100', 2**32:'ff0000000001000000'}
        for n, h in expected.items(): self.assertEqual(compact_size(n).hex(), h)

    def test_full_witness_and_annex(self):
        items = (bytes(4), bytes(4), bytes(4), bytes(4), bytes(10), bytes(33))
        self.assertEqual(witness_size(items), 66)
        self.assertEqual(initial_budget(items), 116)
        self.assertEqual(initial_budget(items + (b'\x50' + bytes(10),)), 128)

    def test_item_and_count_varint_changes(self):
        self.assertEqual(witness_size((bytes(253),)) - witness_size((bytes(252),)), 3)
        self.assertEqual(witness_size((b'',)*253) - witness_size((b'',)*252), 3)

    def test_input_splitting_cannot_expand_block_limit(self):
        rng = random.Random(20261112)
        for _ in range(1000):
            n = rng.randrange(1, 100)
            sizes = [rng.randrange(1, 2000) for _ in range(n)]
            weight = 164*n + sum(sizes) + 40
            calls = sum((50 + size)//50 for size in sizes)
            self.assertLessEqual(calls, call_ceiling(weight, n))
            self.assertLessEqual(calls, weight//50)

    def test_four_million_weight_bound(self):
        self.assertEqual(call_ceiling(4_000_000), 79997)
        self.assertEqual(744425 * 50, 37_221_250)
        self.assertGreater(744425, call_ceiling(4_000_000))

    def test_bad_ranges(self):
        for n in (-1, True, 2**64):
            with self.assertRaises(ValueError): compact_size(n)
        for w, n in ((1, 1), (1000, 0), (1000, True)):
            with self.assertRaises(ValueError): call_ceiling(w, n)


if __name__ == '__main__':
    unittest.main()
