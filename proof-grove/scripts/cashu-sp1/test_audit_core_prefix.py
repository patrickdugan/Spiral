import hashlib
import json
from pathlib import Path
import struct
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from audit_core_prefix import MAX_EVENT_BYTES, PREFIX_REJECTION, stage_prefix, verify_starks


class CorePrefixAuditTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.run = Path(temp.name)
        self.archive = self.run / "prefix.bin"
        self.memos = self.run / "memo/shard"
        self.memos.mkdir(parents=True)

    def write_shard(self, digit, start, end):
        row = [0] * 187
        row[88], row[116], row[120], row[150] = 1, start, end, int(start == 1)
        data = struct.pack("<Q187I", len(row), *row) + b"fake proof bytes"
        memo = self.memos / (digit * 64)
        memo.mkdir()
        (memo / "out0").write_bytes(data)
        (memo / "manifest.json").write_text(json.dumps({"out0_sha256": list(hashlib.sha256(data).digest())}))
        return memo / "out0"

    def write_events(self, *digits):
        events = [dict(kind="shard", key=digit * 16, replayed=False) for digit in digits]
        (self.run / "progress.jsonl").write_text("".join(json.dumps(event) + "\n" for event in events))

    def stage(self):
        return stage_prefix(self.run, self.archive, 2, (0, 0, 0, 0), 0)

    def test_stages_exact_prefix_in_progress_order(self):
        self.write_events("a", "b")
        first = self.write_shard("a", 1, 6)
        second = self.write_shard("b", 6, 12)
        result = self.stage()
        self.assertEqual([row["clock_interval"] for row in result], [(1, 6), (6, 12)])
        self.assertEqual(self.archive.read_bytes(), struct.pack("<IQ", 0, 2) + first.read_bytes() + second.read_bytes())

    def test_refuses_changed_saved_proof_bytes(self):
        self.write_events("a", "b")
        first = self.write_shard("a", 1, 6)
        self.write_shard("b", 6, 12)
        first.write_bytes(first.read_bytes() + b"corruption")
        with self.assertRaisesRegex(ValueError, "differs from its saved digest"):
            self.stage()

    def test_refuses_disconnected_trace_clock(self):
        self.write_events("a", "b")
        self.write_shard("a", 1, 6)
        self.write_shard("b", 7, 12)
        with self.assertRaisesRegex(ValueError, "contiguous execution clock"):
            self.stage()

    def test_refuses_duplicate_durable_progress_events(self):
        self.write_events("a", "a")
        with self.assertRaisesRegex(ValueError, "repeated Core progress"):
            self.stage()

    def test_refuses_oversized_progress_event(self):
        (self.run / "progress.jsonl").write_bytes(b"x" * (MAX_EVENT_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "exceeds its byte limit"):
            self.stage()

    def test_only_the_explicit_incomplete_chain_rejection_counts(self):
        args = SimpleNamespace(verifier=Path("verifier"), elf=Path("elf"), core_key=Path("key"),
                               count=2, core_key_sha256="11" * 32, program_vk_digest="22" * 32)
        output = "Verifying 2 Core shards\n" + PREFIX_REJECTION
        complete = subprocess.CompletedProcess([], 1, "", output)
        with patch("audit_core_prefix.subprocess.run", return_value=complete):
            self.assertEqual(verify_starks(args, self.archive, "33" * 32)[0], output)
        for bad in (subprocess.CompletedProcess([], 0, "verified", output),
                    subprocess.CompletedProcess([], 1, "", "Verifying 2 Core shards\nError: verifying Core shard 2/2")):
            with self.subTest(bad=bad), patch("audit_core_prefix.subprocess.run", return_value=bad):
                with self.assertRaisesRegex(ValueError, "did not reach its incomplete-chain check"):
                    verify_starks(args, self.archive, "33" * 32)
