"""Ledger and state-fold tests (design tests L1-L6)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import PAY_ALICE, PAY_ALICE_BIG, FakeClock, open_module, proposal, records  # noqa: E402

from runtime_control.ledger import (  # noqa: E402
    FloatInPayload,
    ReceiptLedger,
    ReceiptVerificationError,
    canonical_json_bytes,
    receipt_digest,
    verify_receipt_file,
    verify_receipts,
)
from runtime_control.module import ControlModule  # noqa: E402
from runtime_control.state import fold  # noqa: E402
from runtime_control.wire import call_fingerprint, canonical_bytes  # noqa: E402


STEPS = [PAY_ALICE, PAY_ALICE_BIG, PAY_ALICE, {"amount": 20, "to": "bob"}]


def scripted_run(path: Path, *, stop_after: int | None = None, clock: FakeClock | None = None):
    module, _, opened = open_module(path, clock=clock)
    for index, args in enumerate(STEPS):
        if stop_after is not None and index == stop_after:
            return module, opened, STEPS[index:]
        module.decide(proposal(opened, args, seq=index))
    return module, opened, []


class LedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_l1_chain_verifies_and_a_flipped_byte_is_caught_at_its_line(self) -> None:
        path = self.root / "ledger.jsonl"
        module, _, _ = scripted_run(path)
        module.close()
        self.assertTrue(verify_receipt_file(path)[0])
        lines = path.read_bytes().splitlines(keepends=True)
        target = 3
        tampered = lines[target].replace(b'"agentId":"root"', b'"agentId":"rooT"', 1)
        self.assertNotEqual(tampered, lines[target])
        path.write_bytes(b"".join(lines[:target] + [tampered] + lines[target + 1:]))
        ok, message = verify_receipt_file(path)
        self.assertFalse(ok)
        self.assertIn(f"line {target + 1}", message)

    def test_l2_the_record_format_is_pinned(self) -> None:
        # Control-Harness's receipt format: its own tests check the same vector.
        record = {"index": 0, "kind": "run_start", "payload": {"runId": "r", "n": 1}, "previous_hash": "0" * 64}
        self.assertEqual(canonical_json_bytes(record), b'{"index":0,"kind":"run_start","payload":{"n":1,"runId":"r"},"previous_hash":"' + b"0" * 64 + b'"}')
        self.assertEqual(receipt_digest(record), "7dbe689c6629528431d87f3856969631dbd0403452a577a8fa470aee4fd04a6e")

    def test_l2_v2_kinds_still_verify(self) -> None:
        path = self.root / "v2.jsonl"
        ledger = ReceiptLedger(path)
        ledger.append("run_start", {"run_id": "r"})
        ledger.append("grant_issued", {"claim": {"claim_id": "c"}})
        ledger.append("run_end", {"run_id": "r"})
        self.assertTrue(verify_receipt_file(path)[0])

    def test_l3_folding_reproduces_every_decision_state_hash(self) -> None:
        path = self.root / "ledger.jsonl"
        module, _, _ = scripted_run(path)
        module.close()
        rows = records(path)
        checked = 0
        for index, record in enumerate(rows):
            if record["kind"] == "control_decision":
                self.assertEqual(fold(rows[:index]).state_hash(), record["payload"]["state"]["stateHashBefore"])
                checked += 1
        self.assertEqual(checked, 4)
        self.assertEqual(fold(rows).state_hash(), module.state.state_hash())

    def test_l4_resume_after_interruption_matches_an_uninterrupted_run(self) -> None:
        whole = self.root / "whole.jsonl"
        module, _, _ = scripted_run(whole, clock=FakeClock())
        module.close()
        split = self.root / "split.jsonl"
        clock = FakeClock()
        first, opened, remaining = scripted_run(split, stop_after=2, clock=clock)
        del first  # the process "dies" here
        resumed = ControlModule.resume(split, clock=clock)
        for offset, args in enumerate(remaining, start=2):
            resumed.decide(proposal(opened, args, seq=offset))
        resumed.close()
        self.assertEqual(whole.read_bytes(), split.read_bytes())

    def test_l4_a_closed_ledger_cannot_be_resumed(self) -> None:
        path = self.root / "closed.jsonl"
        module, _, _ = scripted_run(path)
        module.close()
        with self.assertRaises(ReceiptVerificationError):
            ReceiptLedger.resume(path)

    def test_l5_fingerprint_and_canonical_form_are_pinned(self) -> None:
        args = {"kind": "sandbox_trade", "amount_units": 10}
        self.assertEqual(
            canonical_bytes({"agentId": "root", "args": args, "runId": "run-1", "toolId": "treasury_propose"}),
            b'{"agentId":"root","args":{"amount_units":10,"kind":"sandbox_trade"},"runId":"run-1","toolId":"treasury_propose"}',
        )
        self.assertEqual(call_fingerprint("run-1", "root", "treasury_propose", args), "bf34de40d12f95f57f51238697cf776e52bf5ddf859d48be75b0203d0f70118d")
        # Non-ASCII is escaped, as Python's json.dumps(ensure_ascii=True) does; the Rust gate must match.
        self.assertEqual(canonical_bytes({"to": "zoë"}), b'{"to":"zo\\u00eb"}')

    def test_l6_floats_are_rejected_on_write_and_on_verify(self) -> None:
        path = self.root / "floats.jsonl"
        ledger = ReceiptLedger(path)
        ledger.append("run_start", {"runId": "r"})
        with self.assertRaises(FloatInPayload):
            ledger.append("tool_result", {"amount": 1.5})
        forged = {"index": 1, "kind": "tool_result", "payload": {"amount": 1.5}, "previous_hash": ledger.last_hash}
        forged["hash"] = receipt_digest(forged)
        ok, message = verify_receipts(records(path) + [forged], require_closed=False)
        self.assertFalse(ok)
        self.assertIn("float", message)


if __name__ == "__main__":
    unittest.main()
