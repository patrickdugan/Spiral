import hashlib
from pathlib import Path
import tempfile
import unittest

from proofdesk import protected_chain_archive as archive
from proofdesk.protected_reserve import GENESIS


def chain(length):
    blocks, hashes = [], [GENESIS]
    for index in range(length):
        raw = bytes(4) + bytes.fromhex(hashes[-1])[::-1] + bytes(40) + index.to_bytes(4, "little") + b"\x00"
        blocks.append(raw.hex())
        hashes.append(hashlib.sha256(hashlib.sha256(raw[:80]).digest()).digest()[::-1].hex())
    return blocks, hashes


class ProtectedChainArchiveTest(unittest.TestCase):
    def test_capture_replay_and_retry_preserve_the_exact_prefix(self):
        blocks, hashes = chain(3)
        submitted = []

        def source(method, params):
            if method == "getblockchaininfo":
                return {"chain": "regtest", "blocks": 3, "bestblockhash": hashes[-1]}
            if method == "getblockhash":
                return hashes[params[0]]
            if method == "getblock":
                return blocks[hashes.index(params[0]) - 1]
            self.fail(f"unexpected RPC {method}")

        def destination(method, params):
            if method == "getblockchaininfo":
                return {"chain": "regtest", "blocks": len(submitted), "bestblockhash": hashes[len(submitted)]}
            if method == "getblockhash":
                self.assertLessEqual(params[0], len(submitted))
                return hashes[params[0]]
            if method == "submitblock":
                self.assertEqual(params, [blocks[len(submitted)]])
                submitted.append(params[0])
                return None
            self.fail(f"unexpected RPC {method}")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.hex"
            captured = archive.capture(source, path, 3, hashes[-1])
            file_pin = captured["archive_sha256"]
            result = archive.replay(destination, path, file_pin, 3, hashes[-1])
            self.assertEqual(result["blocks_submitted"], 3)
            self.assertEqual(archive.replay(destination, path, file_pin, 3, hashes[-1])["blocks_submitted"], 0)
            self.assertEqual(submitted, blocks)
            with self.assertRaisesRegex(ValueError, "byte pin"):
                archive.replay(destination, path, "ff" * 32, 3, hashes[-1])
            with self.assertRaisesRegex(ValueError, "pinned checkpoint"):
                archive.replay(destination, path, file_pin, 3, "ff" * 32)
            path.write_bytes(path.read_bytes()[:-1] + b"\n\n")
            with self.assertRaisesRegex(ValueError, "byte pin"):
                archive.replay(destination, path, file_pin, 3, hashes[-1])

    def test_different_destination_tip_refuses_before_submission(self):
        blocks, hashes = chain(2)

        def destination(method, _params):
            if method == "getblockchaininfo":
                return {"chain": "regtest", "blocks": 1, "bestblockhash": "44" * 32}
            if method == "getblockhash":
                return GENESIS
            self.fail(f"must not call {method}")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.hex"
            raw = ("\n".join(blocks) + "\n").encode()
            path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, "not an archive prefix"):
                archive.replay(destination, path, hashlib.sha256(raw).hexdigest(), 2, hashes[-1])
