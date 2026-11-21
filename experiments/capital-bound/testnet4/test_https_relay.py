import unittest
from unittest.mock import patch

from core import Gate
from https_relay import ENDPOINT, broadcast


class HTTPSRelayTests(unittest.TestCase):
    @patch("https_relay.urllib.request.build_opener")
    def test_passes_exact_bytes_to_testnet4_and_matches_id(self, build):
        txid = "a" * 64
        response = build.return_value.open.return_value.__enter__.return_value
        response.read.return_value = txid.encode()
        self.assertEqual(broadcast("0011", txid), txid)
        request = build.return_value.open.call_args.args[0]
        self.assertEqual((request.full_url, request.data, request.method),
                         (ENDPOINT, b"0011", "POST"))
        response.read.return_value = b"b" * 64
        with self.assertRaisesRegex(Gate, "reserved transaction ID"):
            broadcast("0011", txid)

    @patch("https_relay.urllib.request.build_opener")
    def test_uncertain_submission_keeps_one_http_attempt(self, build):
        build.return_value.open.side_effect = TimeoutError()
        with self.assertRaisesRegex(Gate, "outcome uncertain"):
            broadcast("0011", "a" * 64)
        self.assertEqual(build.return_value.open.call_count, 1)
