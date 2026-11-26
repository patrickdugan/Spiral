import copy
import hashlib
import io
import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen
from zipfile import ZipFile

from proofdesk import protected_payout_evidence as evidence
from proofdesk.domain import digest
from proofdesk.protected_reserve import GENESIS, V3_BUNDLE_SCHEMA, V3_PLAN_SCHEMA, _witness_script
from proofdesk.server import Desk, make_server


HOLDER = "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
MINT = "02c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5"
ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
OPENSSL = os.environ.get("PROOF_GROVE_TEST_OPENSSL") or shutil.which("openssl")


def hash256(raw):
    return hashlib.sha256(hashlib.sha256(raw).digest()).digest()


def little(value, size=4):
    return value.to_bytes(size, "little")


def vector(value):
    return bytes([len(value)]) + value


def output(amount, script):
    return little(amount, 8) + vector(script)


def transaction(previous, sequence, outputs, *, script=b"", witness=()):
    base = b"\x01" + previous + vector(script) + sequence + bytes([len(outputs)]) + b"".join(outputs)
    stripped = little(2) + base + bytes(4)
    if witness:
        raw = little(2) + b"\x00\x01" + base + bytes([len(witness)]) + b"".join(map(vector, witness)) + bytes(4)
    else:
        raw = stripped
    return raw.hex(), hash256(stripped), hash256(raw)


def sign_public_fixture(message):
    # Deliberately public synthetic key and nonce (both 1) only for this test.
    r = int(HOLDER[2:], 16)
    s = (int.from_bytes(message, "big") + r) % ORDER
    s = min(s, ORDER - s)

    def der_integer(value):
        raw = value.to_bytes((value.bit_length() + 8) // 8, "big")
        return b"\x02" + vector(raw)

    return b"\x30" + vector(der_integer(r) + der_integer(s))


def fixture(*, bad_signature=False):
    destination = b"\x00\x14" + b"\x28" * 20
    terms = {"network": "regtest", "genesis": GENESIS, "holder_pubkey": HOLDER, "mint_pubkey": MINT,
             "claim_commitment": "31" * 32, "reserve_sats": 25000, "fee_sats": 250, "delay_blocks": 6,
             "min_confirmations": 2, "payout_address": "bcrt1-test-recipient", "payout_script": destination.hex()}
    preimage = bytes.fromhex(digest({"schema": "proof-grove/protected-issuance-terms/v3"} | terms))
    issuance_hash = hashlib.sha256(preimage).hexdigest()
    witness_script = _witness_script(HOLDER, MINT, 6, issuance_hash)
    funding_script = b"\x00\x20" + hashlib.sha256(witness_script).digest()
    plan = terms | {"schema": V3_PLAN_SCHEMA, "funding_script": funding_script.hex(),
                    "witness_script": witness_script.hex(), "issuance_preimage": preimage.hex(),
                    "issuance_hash": issuance_hash, "payout_sats": 24750, "change_sats": 0}
    plan["plan_id"] = digest(plan)

    funding, funding_txid, _ = transaction(b"\x44" * 32 + little(0), little(0xFFFFFFFF),
                                           [output(25000, funding_script)])
    previous = funding_txid + little(0)
    sequence = little(6)
    serialized_output = output(24750, destination)
    sighash = hash256(little(2) + hash256(previous) + hash256(sequence) + previous + vector(witness_script)
                      + little(25000, 8) + sequence + hash256(serialized_output) + bytes(4) + little(1))
    signed = bytes(32) if bad_signature else sighash
    payout, payout_txid, payout_wtxid = transaction(previous, sequence, [serialized_output],
        witness=(b"", sign_public_fixture(signed) + b"\x01", preimage, witness_script))
    reserved = b"\x69" * 32
    other_txid, other_wtxid = b"\x31" * 32, b"\x32" * 32
    witness_root = hash256(hash256(bytes(32) + other_wtxid) + hash256(payout_wtxid * 2))
    commitment = evidence.WITNESS_MARKER + hash256(witness_root + reserved)
    coinbase, coinbase_txid, _ = transaction(bytes(32) + b"\xff" * 4, little(0xFFFFFFFF),
        [output(50, b"\x51"), output(0, evidence.WITNESS_MARKER + bytes(32)), output(0, commitment)],
        script=b"\x01\x6e", witness=(reserved,))

    header_roots = [hash256(b"\x55" * 32 + funding_txid), *([bytes(32)] * 5),
                    hash256(hash256(coinbase_txid + other_txid) + hash256(payout_txid * 2))]
    previous_header = b"\x11" * 32
    headers = []
    for merkle in header_roots:
        header = little(4) + previous_header + merkle + bytes(12)
        headers.append(header)
        previous_header = hash256(header)
    anchor = previous_header[::-1].hex()
    outpoint = {"txid": funding_txid[::-1].hex(), "vout": 0, "block": hash256(headers[0])[::-1].hex()}
    bundle = {"schema": V3_BUNDLE_SCHEMA, "plan": plan, "funding": outpoint}
    bundle_id = digest(bundle)
    bundle["bundle_id"] = bundle_id
    claim_id = hashlib.sha256(b"proof-grove/protected-reserve/v1\0" + bytes.fromhex(GENESIS + outpoint["txid"])
                              + (0).to_bytes(4, "big")).hexdigest()
    receipt = {"network": "regtest", "genesis": GENESIS, "app_bundle": bundle, "claim_id": claim_id,
               "mature_holder_check": {"observation": {"funding_height": 104}},
               "reserve": outpoint | {"sats": 25000, "script": funding_script.hex()},
               "payout": {"txid": payout_txid[::-1].hex(), "wtxid": payout_wtxid[::-1].hex(), "height": 110,
                          "block": anchor, "delay_blocks": 6, "sats": 24750, "script": destination.hex(), "fee_sats": 250},
               "public_transactions": {"funding": funding, "payout": payout},
               "bitcoin_chain_evidence": {"schema": evidence.CHAIN_SCHEMA, "headers": [h.hex() for h in headers],
                   "funding_txids": ["55" * 32, funding_txid[::-1].hex()],
                   "payout_txids": [t[::-1].hex() for t in (coinbase_txid, other_txid, payout_txid)],
                   "payout_wtxids": [t[::-1].hex() for t in (bytes(32), other_wtxid, payout_wtxid)],
                   "payout_coinbase": coinbase}}
    return receipt, bundle_id, anchor, sighash


class ProtectedPayoutEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.receipt, self.bundle, self.anchor, self.sighash = fixture()

    def verify(self, receipt=None, *, anchor=None, height=110):
        return evidence.verify(self.receipt if receipt is None else receipt, self.bundle, height,
                               self.anchor if anchor is None else anchor, openssl=OPENSSL or "openssl")

    @patch.object(evidence, "_verify_signature")
    def test_pinned_chain_includes_exact_funding_and_holder_witness(self, signature):
        result = self.verify()
        signature.assert_called_once_with(OPENSSL or "openssl", bytes.fromhex(HOLDER),
                                          sign_public_fixture(self.sighash), self.sighash)
        self.assertTrue(result["witness_inclusion_verified"])
        self.assertEqual((result["funding_height"], result["payout_sats"], result["fee_sats"]), (104, 24750, 250))

    @patch.object(evidence, "_verify_signature")
    def test_download_replays_the_exact_receipt_and_refuses_changed_evidence(self, signature):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            raw = json.dumps(self.receipt, indent=2).encode()
            receipt_path = source / 'recorded-payout.json'
            receipt_path.write_bytes(raw)
            manifest_path = source / 'preview.json'
            pins = {'receipt_sha256': hashlib.sha256(raw).hexdigest(), 'bundle_id': self.bundle,
                    'anchor_height': 110, 'anchor_hash': self.anchor}
            manifest = {'receipt': receipt_path.name, **pins}
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
            desk = Desk(config={'protected_preview': manifest_path})
            with make_server(desk, 0) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                preview = f'http://127.0.0.1:{server.server_port}/api/protected/preview'
                archive_url, transaction_url = (f'{preview}/{name}' for name in ('archive', 'transaction'))
                try:
                    with urlopen(archive_url, timeout=5) as response:
                        self.assertEqual(response.headers.get_content_type(), 'application/zip')
                        with ZipFile(io.BytesIO(response.read())) as archive:
                            self.assertEqual(set(archive.namelist()), {'preview.json', 'holder-receipt.json'})
                            self.assertEqual(json.loads(archive.read('preview.json')), {'receipt': 'holder-receipt.json', **pins})
                            self.assertEqual(archive.read('holder-receipt.json'), raw)
                    with urlopen(transaction_url, timeout=5) as response:
                        self.assertEqual(response.headers.get_content_type(), 'text/plain')
                        self.assertEqual(response.headers.get('Cache-Control'), 'no-store')
                        self.assertEqual(response.read(), (self.receipt['public_transactions']['payout'] + '\n').encode('ascii'))
                    receipt_path.write_bytes(raw + b' ')
                    for url in (archive_url, transaction_url):
                        with self.assertRaises(HTTPError) as refused:
                            urlopen(url, timeout=5)
                        self.assertEqual(json.loads(refused.exception.read())['error'], 'protected_preview_receipt_changed')
                    receipt_path.write_bytes(raw)
                    manifest_path.write_text(json.dumps(manifest | {'anchor_hash': '33' * 32}), encoding='utf-8')
                    for url in (archive_url, transaction_url):
                        with self.assertRaises(HTTPError) as refused:
                            urlopen(url, timeout=5)
                        self.assertEqual(json.loads(refused.exception.read())['error'], 'protected_preview_unverified')
                    self.assertEqual(signature.call_count, 2)
                finally:
                    server.shutdown()
                    thread.join(timeout=5)

    def test_rejects_wrong_checkpoint_and_same_block_payout(self):
        with self.assertRaisesRegex(ValueError, "differ from the checkpoint"):
            self.verify(anchor="33" * 32)
        bad = copy.deepcopy(self.receipt)
        headers = bad["bitcoin_chain_evidence"]["headers"]
        headers[:] = headers[-1:]
        with self.assertRaisesRegex(ValueError, "invalid protected payout header interval"):
            self.verify(bad)

    def test_rejects_disconnected_headers_txids_and_witness_counts(self):
        cases = (("headers", 1, "00" * 80, "headers differ"),
                 ("funding_txids", 1, "92" * 32, "outside the pinned headers"),
                 ("payout_wtxids", 1, None, "witness leaf"),
                 ("payout_wtxids", 2, "89" * 32, "witness leaf"))
        for key, index, value, failure in cases:
            bad = copy.deepcopy(self.receipt)
            items = bad["bitcoin_chain_evidence"][key]
            if value is None:
                del items[index]
            else:
                items[index] = value
            with self.subTest(key=key, index=index), self.assertRaisesRegex(ValueError, failure):
                self.verify(bad)

    def test_same_txid_with_substituted_signature_cannot_open_witness_commitment(self):
        bad = copy.deepcopy(self.receipt)
        changed = fixture(bad_signature=True)[0]["public_transactions"]["payout"]
        self.assertEqual(evidence._transaction(changed).txid, bad["payout"]["txid"])
        bad["public_transactions"]["payout"] = changed
        bad["bitcoin_chain_evidence"]["payout_wtxids"][-1] = evidence._transaction(changed).wtxid
        with self.assertRaisesRegex(ValueError, "outside the pinned BIP141 commitment"):
            self.verify(bad)

    def test_capture_uses_active_block_order_and_rejects_malformed_counts(self):
        expected = self.receipt["bitcoin_chain_evidence"]
        headers = {hash256(bytes.fromhex(header))[::-1].hex(): header for header in expected["headers"]}
        blocks = list(headers)
        funding = {"hash": blocks[0], "height": 104, "tx": expected["funding_txids"], "nTx": 2}
        payout = {"hash": blocks[-1], "height": 110, "nTx": 3, "tx": [
            {"txid": txid, "hash": wtxid} for txid, wtxid in zip(expected["payout_txids"], expected["payout_wtxids"])
        ]}
        payout["tx"][0]["hex"] = expected["payout_coinbase"]

        def rpc(method, params):
            if method == "getblockhash":
                return blocks[params[0] - 104]
            if method == "getblockheader" and params[1] is False:
                return headers[params[0]]
            if method == "getblock" and params in ([blocks[0], 1], [blocks[-1], 2]):
                return funding if params[1] == 1 else payout
            raise AssertionError((method, params))

        self.assertEqual(evidence.capture(rpc, 104, 110, blocks[0], blocks[-1]), expected)
        payout["nTx"] -= 1
        with self.assertRaisesRegex(ValueError, "invalid captured Bitcoin block transaction count"):
            evidence.capture(rpc, 104, 110, blocks[0], blocks[-1])

    @unittest.skipUnless(OPENSSL, "OpenSSL is required for the independent signature test")
    def test_openssl_checks_signature_even_under_valid_witness_commitment(self):
        self.assertTrue(self.verify()["holder_signature_verified"])
        bad, _, anchor, _ = fixture(bad_signature=True)
        with self.assertRaisesRegex(ValueError, "holder BIP143 signature verification failed"):
            self.verify(bad, anchor=anchor)


if __name__ == "__main__":
    unittest.main()
