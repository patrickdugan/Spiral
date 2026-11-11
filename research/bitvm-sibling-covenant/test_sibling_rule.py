"""Minimal smoke tests for sibling outpoint equality (not full BitVM model)."""
import unittest
from sibling_rule import Outpoint, descriptor, sibling_verify


class SiblingRuleTests(unittest.TestCase):
    def test_pair(self):
        inputs = (Outpoint(bytes([1])*32, 0), Outpoint(bytes([1])*32, 1))
        self.assertTrue(sibling_verify(inputs, 0, descriptor(0, 1, 1)))
        self.assertTrue(sibling_verify(inputs, 1, descriptor(1, 0, 0)))

    def test_foreign_peer_rejected_exhaustively(self):
        graphs = [(Outpoint(n.to_bytes(32, 'little'), 0),
                   Outpoint(n.to_bytes(32, 'little'), 1)) for n in range(1, 25)]
        accepted = rejected = 0
        for principal, _ in graphs:
            for _, peer in graphs:
                if sibling_verify((principal, peer), 0, descriptor(0, 1, 1)):
                    accepted += 1
                else:
                    rejected += 1
        self.assertEqual((accepted, rejected), (24, 552))

    def test_malformed(self):
        a = Outpoint(bytes(32), 0)
        b = Outpoint(bytes(32), 1)
        ins = (a, b)
        for raw in (b'', bytes(11), bytes(13), descriptor(0, 0, 1),
                    descriptor(0, 2, 1), descriptor(0, 1, 0),
                    descriptor(2, 1, 1), descriptor(0, 1, 2)):
            with self.subTest(raw=raw.hex()):
                self.assertFalse(sibling_verify(ins, 0, raw))


if __name__ == '__main__':
    unittest.main()
