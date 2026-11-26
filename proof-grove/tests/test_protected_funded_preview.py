import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen
from zipfile import ZipFile

from proofdesk.server import Desk, make_server


class FundedPreviewTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.publication = self.directory / "preview.json"
        self.archive = self.directory / "funded.zip"
        self.receipt = self.directory / "receipt.json"
        with ZipFile(self.archive, "x") as bundle:
            bundle.writestr("test.json", "fixture archive")
        self.archive_pin = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.statement = "13" * 32
        self.proof = {"status": "verified", "statement_sha256": self.statement,
                      "proof_sha256": "14" * 32, "verifier_sha256": "15" * 32}
        self.chain = {"schema": "proof-grove/protected-regtest-block-replay/v1", "network": "regtest",
                      "wallets_loaded": 0, "txid": "17" * 32, "wtxid": "18" * 32, "height": 212}
        desk = Desk(config={"protected_funded_preview": self.publication,
                            "protected_funded_statement_sha256": self.statement})
        self.server = make_server(desk, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def publish(self, **changes):
        raw = json.dumps({"schema": "proof-grove/m14/independent-funded-cashu-verification/v1",
                          "archive_sha256": self.archive_pin, "holder_sats": 24750, "refund_sats": 24750,
                          "fee_sats": 750, "m13": self.proof, "bitcoin": self.chain,
                          "m14": {"status": "accept_opening_matches_pinned_setup", "setup_sha256": "16" * 32}},
                         indent=2).encode()
        self.receipt.write_bytes(raw)
        publication = {"schema": "proof-grove/funded-preview/v1", "archive": self.archive.name,
                       "archive_sha256": self.archive_pin, "verification": self.receipt.name,
                       "verification_sha256": hashlib.sha256(raw).hexdigest(), "statement_sha256": self.statement}
        self.publication.write_text(json.dumps(publication | changes), encoding="utf-8")

    def call(self, suffix=""):
        return urlopen(f"http://127.0.0.1:{self.server.server_port}/api/protected/preview/funded{suffix}", timeout=5)

    def refused(self, suffix):
        with self.assertRaises(HTTPError) as error:
            self.call(suffix)
        self.assertEqual(error.exception.code, 400)
        return json.loads(error.exception.read())["error"]

    def test_waits_for_recipient_verification_then_serves_the_exact_zip(self):
        with self.call() as response:
            self.assertEqual(json.load(response), {"status": "pending"})
        self.assertEqual(self.refused("/archive"), "funded_preview_pending")
        self.assertEqual(self.refused("/verification"), "funded_preview_pending")
        self.publish()
        with self.call() as response:
            result = json.load(response)
            self.assertEqual((result["status"], result["holder_sats"], result["txid"]), ("verified", 24750, "17" * 32))
        with self.call("/archive") as response:
            self.assertEqual(response.headers.get_content_type(), "application/zip")
            raw = response.read()
            self.assertEqual(raw, self.archive.read_bytes())
            with ZipFile(io.BytesIO(raw)) as downloaded:
                self.assertEqual(downloaded.read("test.json"), b"fixture archive")
        with self.call("/verification") as response:
            self.assertEqual(response.read(), self.receipt.read_bytes())

    def test_refuses_changed_files_and_incomplete_verification(self):
        self.publish()
        self.receipt.write_bytes(self.receipt.read_bytes() + b" ")
        self.assertEqual(self.refused("/archive"), "funded_preview_verification_changed")
        self.publish()
        self.archive.write_bytes(self.archive.read_bytes() + b" ")
        self.assertEqual(self.refused("/verification"), "funded_preview_archive_changed")
        self.proof["status"] = "pending"
        self.publish()
        self.assertEqual(self.refused(""), "funded_preview_unverified")

    def test_refuses_path_substitution_and_a_receipt_for_a_different_statement(self):
        self.publish(archive="../outside.zip")
        self.assertEqual(self.refused("/archive"), "funded_preview_invalid_artifact")
        self.proof["statement_sha256"] = "ff" * 32
        self.publish()
        self.assertEqual(self.refused(""), "funded_preview_unverified")

    def test_refuses_a_consistent_publication_for_a_different_configured_withdrawal(self):
        self.statement = self.proof["statement_sha256"] = "ff" * 32
        self.publish()
        for suffix in ("", "/archive", "/verification"):
            with self.subTest(suffix=suffix):
                self.assertEqual(self.refused(suffix), "funded_preview_statement_mismatch")
