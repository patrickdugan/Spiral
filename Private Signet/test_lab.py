"""Static tests for the Private Signet harness (no Core process required)."""
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("private_signet_lab", Path(__file__).with_name("lab.py"))
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


class StaticHarnessTests(unittest.TestCase):
    def test_compressed_key_challenge(self):
        key = "02" + "ab" * 32
        self.assertEqual(lab.challenge_from_pubkey(key), "21" + key + "ac")
        self.assertEqual(len(lab.challenge_from_pubkey(key)), 70)

    def test_invalid_challenges(self):
        for value in ("", "04" + "ab" * 64, "02" + "ab" * 31, "03" + "xx" * 32):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    lab.challenge_from_pubkey(value)

    def test_descriptor_import(self):
        export = {"descriptors": [
            {"desc": "wpkh(tprv-example/0/*)#checksum", "range": [0, 9]},
            {"desc": "pk(02" + "33" * 32 + ")#checksum"},
        ]}
        imported = lab.descriptors_for_import(export)
        self.assertEqual(len(imported), 2)
        self.assertEqual(imported[0]["range"], [0, 9])
        self.assertNotIn("range", imported[1])
        self.assertFalse(imported[0]["active"])
        self.assertEqual(imported[1]["timestamp"], "now")

    def test_empty_descriptor_export(self):
        with self.assertRaises(RuntimeError):
            lab.descriptors_for_import({"descriptors": []})

    def test_hex_validation(self):
        self.assertEqual(lab.validate_txhex("AA" * 10 + "\n"), "aa" * 10)
        for raw in ("invalid", "abc", "", "aa" * 4, "gg" * 10):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    lab.validate_txhex(raw)


if __name__ == "__main__":
    unittest.main()
