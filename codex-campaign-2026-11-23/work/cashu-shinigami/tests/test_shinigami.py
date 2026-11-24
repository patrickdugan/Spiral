from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from proofdesk import demo
from proofdesk.domain import Refused
from proofdesk.shinigami import EXIT_PROGRAM_HASH, PROOF_PROFILE, ShinigamiGate, paid_output


def _cell(address, number):
    return [address, [(number >> (32 * index)) & (2**32 - 1) for index in range(8)]]


def _serialized_output(txid, vout, amount, script):
    tx = int.from_bytes(bytes.fromhex(txid), "little")
    words = len(script) // 31
    full = [int.from_bytes(script[index * 31:(index + 1) * 31], "big") for index in range(words)]
    remainder = script[31 * words:]
    return [tx % 2**128, tx >> 128, vout, amount, words, *full,
            int.from_bytes(remainder, "big"), len(remainder)]


def _fixture(payment, script):
    program = [_cell(1, 27)]
    bootloader = hashlib.sha256(b"[27]").hexdigest()
    payload = _serialized_output("11" * 32, 0, payment.value_sats + 10, b"\x51")
    payload += _serialized_output(payment.txid, payment.vout, payment.value_sats, script)
    values = [1, len(payload) + 3, EXIT_PROGRAM_HASH, *payload, 1]
    return {
        "preprocessed_trace_variant": "canonical_without_pedersen",
        "channel_salt": 0, "stark_proof": {"config": PROOF_PROFILE},
        "claim": {"public_data": {"public_memory": {
            "program": program,
            "output": [_cell(300 + index, value) for index, value in enumerate(values)],
        }}},
    }, bootloader


class ShinigamiTests(unittest.TestCase):
    def setUp(self):
        _, payment, _, _ = demo.sample()
        self.script = bytes.fromhex("5120" + "23" * 32)
        self.payment = replace(payment, script_sha256=hashlib.sha256(self.script).hexdigest())
        self.doc, self.bootloader = _fixture(self.payment, self.script)

    def test_pinned_public_output_matches_exact_bitcoin_payment(self):
        result = paid_output(json.dumps(self.doc).encode(), self.bootloader)
        self.assertEqual(result, (self.payment.txid, self.payment.vout, self.payment.value_sats,
                                  self.payment.script_sha256))
        with self.assertRaisesRegex(Refused, "shinigami_bootloader_mismatch"):
            paid_output(json.dumps(self.doc).encode(), "11" * 32)

    def test_malformed_memory_coordinates_are_refused(self):
        cells = self.doc["claim"]["public_data"]["public_memory"]["output"]
        cells[2][0] = -1
        with self.assertRaisesRegex(Refused, "shinigami_output_invalid"):
            paid_output(json.dumps(self.doc).encode(), self.bootloader)

    def test_payment_binding_and_native_verification_are_both_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            verifier = root / "scarb-verify"
            verifier.write_bytes(b"test executable")
            sha = hashlib.sha256(verifier.read_bytes()).hexdigest()
            gate = ShinigamiGate(verifier, root, sha, self.bootloader)
            proof = root / f"{self.payment.txid}-{self.payment.vout}.json"
            encoded = json.dumps(self.doc).encode()
            proof.write_bytes(encoded)
            with patch("proofdesk.shinigami.subprocess.run") as native:
                different_amount = replace(self.payment, value_sats=self.payment.value_sats + 1)
                with self.assertRaisesRegex(Refused, "shinigami_payment_mismatch"):
                    gate.verify(different_amount)
                native.assert_not_called()
                native.return_value = SimpleNamespace(returncode=1)
                with self.assertRaisesRegex(Refused, "shinigami_proof_rejected"):
                    gate.verify(self.payment)
                native.return_value = SimpleNamespace(returncode=0)
                result = gate.verify(self.payment)
            self.assertEqual(result.shinigami_proof_sha256, hashlib.sha256(encoded).hexdigest())
            self.assertEqual(result.shinigami_policy_sha256, gate.policy_sha256)
