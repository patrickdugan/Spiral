"""The egress sink refuses plain and tunnelled requests at once and records each one."""

from __future__ import annotations

import http.client
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures  # noqa: E402,F401  (puts src on sys.path)

from runtime_control.egress import egress_attempts, egress_env, serve_egress_sink  # noqa: E402


class EgressSinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.record = Path(self.temp.name) / "egress.jsonl"
        self.server, self.url = serve_egress_sink(self.record)

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def test_plain_and_tunnelled_requests_are_refused_and_recorded(self) -> None:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": self.url}))
        started = time.perf_counter()
        with self.assertRaises(urllib.error.HTTPError) as caught:
            opener.open("http://example.invalid/data", timeout=5)
        self.assertEqual(caught.exception.code, 403)
        host, port = self.url.rsplit(":", 1)
        tunnel = http.client.HTTPSConnection(host.split("//")[1], int(port), timeout=5)
        tunnel.set_tunnel("models.dev", 443)
        with self.assertRaises(OSError) as refused:
            tunnel.request("GET", "/api.json")
        self.assertIn("403", str(refused.exception))
        self.assertLess(time.perf_counter() - started, 2.0)
        attempts = egress_attempts(self.record)
        self.assertEqual([(a["method"], a["target"]) for a in attempts], [("GET", "http://example.invalid/data"), ("CONNECT", "models.dev:443")])

    def test_environment_keeps_loopback_direct(self) -> None:
        env = egress_env(self.url)
        self.assertEqual((env["HTTPS_PROXY"], env["http_proxy"]), (self.url, self.url))
        self.assertEqual(env["NO_PROXY"], "127.0.0.1,localhost,::1")

    def test_no_record_means_no_attempts(self) -> None:
        self.assertEqual(egress_attempts(Path(self.temp.name) / "missing.jsonl"), [])


if __name__ == "__main__":
    unittest.main()
