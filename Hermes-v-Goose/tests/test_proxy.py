"""Model proxy tests: the context ceiling, recording, replay and streaming (C7, R3)."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import kinds, open_module, records  # noqa: E402

from runtime_control.proxy import ModelProxy, PlannedResponder, serve_proxy_http  # noqa: E402


class FakeLlamaServer:
    """One token per character; counts how many chat requests reach it."""

    def __init__(self) -> None:
        self.chat_calls = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:
                return None

            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/apply-template":
                    reply = {"prompt": "".join(f"<{m['role']}>{m.get('content') or ''}" for m in body["messages"])}
                elif self.path == "/tokenize":
                    reply = {"tokens": list(range(len(body["content"])))}
                elif self.path == "/v1/chat/completions":
                    outer.chat_calls += 1
                    reply = {
                        "choices": [{"finish_reason": "stop", "index": 0, "message": {"content": "ok", "role": "assistant"}}],
                        "id": "x",
                        "model": "fake",
                        "object": "chat.completion",
                        "usage": {"completion_tokens": 1, "prompt_tokens": 3, "total_tokens": 4},
                    }
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                data = json.dumps(reply).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def post(url: str, body: dict) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


class ModelProxyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.upstream = FakeLlamaServer()
        self.addCleanup(self.upstream.close)
        self.module, _, _ = open_module(self.root / "ledger.jsonl")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _proxy(self, **kwargs) -> tuple[ModelProxy, str]:
        proxy = ModelProxy(model_id="bonsai", record_path=self.root / "model_io.jsonl", control=self.module, **kwargs)
        server, url = serve_proxy_http(proxy)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return proxy, url

    def test_c7_a_request_over_the_ceiling_never_reaches_the_model(self) -> None:
        _, url = self._proxy(mode="live", upstream=self.upstream.url, ceiling_tokens=100, default_output_reserve=10)
        status, body = post(url + "/v1/chat/completions", {"messages": [{"content": "x" * 200, "role": "user"}], "model": "bonsai"})
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"]["code"], "context_length_exceeded")
        self.assertEqual(self.upstream.chat_calls, 0)
        packets = [r["payload"] for r in records(self.root / "ledger.jsonl") if r["kind"] == "context_packet"]
        self.assertEqual((packets[-1]["overflow"], packets[-1]["counter"]), (True, "server_template"))

    def test_requested_output_counts_against_the_ceiling(self) -> None:
        _, url = self._proxy(mode="live", upstream=self.upstream.url, ceiling_tokens=100)
        status, _ = post(url + "/v1/chat/completions", {"max_tokens": 95, "messages": [{"content": "hi", "role": "user"}]})
        self.assertEqual(status, 400)
        self.assertEqual(self.upstream.chat_calls, 0)

    def test_requests_under_the_ceiling_are_forwarded_recorded_and_reported(self) -> None:
        _, url = self._proxy(mode="live", upstream=self.upstream.url, ceiling_tokens=1_000)
        status, body = post(url + "/v1/chat/completions", {"messages": [{"content": "hi", "role": "user"}], "temperature": 0.2})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["choices"][0]["message"]["content"], "ok")
        self.assertEqual(self.upstream.chat_calls, 1)
        line = json.loads((self.root / "model_io.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual((line["status"], line["inputTokens"]), ("ok", len("<user>hi")))
        self.assertIn("model_turn", kinds(self.root / "ledger.jsonl"))

    def test_r3_replay_answers_from_the_record_without_a_model(self) -> None:
        _, live_url = self._proxy(mode="live", upstream=self.upstream.url, ceiling_tokens=1_000)
        request = {"messages": [{"content": "hi", "role": "user"}], "temperature": 0.2}
        _, original = post(live_url + "/v1/chat/completions", request)
        replay = ModelProxy(mode="replay", model_id="bonsai", record_path=self.root / "replayed.jsonl", replay_path=self.root / "model_io.jsonl")
        server, replay_url = serve_proxy_http(replay)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        _, replayed = post(replay_url + "/v1/chat/completions", request)
        self.assertEqual(json.loads(replayed), json.loads(original))
        self.assertEqual(self.upstream.chat_calls, 1)
        status, _ = post(replay_url + "/v1/chat/completions", {"messages": [{"content": "other", "role": "user"}]})
        self.assertEqual(status, 500)

    def test_r2_replay_matches_through_declared_volatile_spans_only(self) -> None:
        from runtime_control.replay import HERMES_VOLATILE

        _, live_url = self._proxy(mode="live", upstream=self.upstream.url, ceiling_tokens=1_000)
        prompt = "You are Hermes.\nConversation started: Monday, October 13, 2026 06:42 AM\nBe brief."
        post(live_url + "/v1/chat/completions", {"messages": [{"content": prompt, "role": "system"}, {"content": "hi", "role": "user"}]})
        later = prompt.replace("06:42 AM", "06:43 AM")
        for normalizers, expected in (((), 500), (HERMES_VOLATILE, 200)):
            replay = ModelProxy(mode="replay", model_id="bonsai", record_path=self.root / f"replayed-{len(normalizers)}.jsonl", replay_path=self.root / "model_io.jsonl", replay_normalizers=normalizers)
            server, url = serve_proxy_http(replay)
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
            status, _ = post(url + "/v1/chat/completions", {"messages": [{"content": later, "role": "system"}, {"content": "hi", "role": "user"}]})
            self.assertEqual(status, expected, normalizers)
            # A difference outside the declared span still misses.
            status, _ = post(url + "/v1/chat/completions", {"messages": [{"content": later, "role": "system"}, {"content": "hello", "role": "user"}]})
            self.assertEqual(status, 500)
        self.assertEqual(replay.normalized_matches, 1)

    def test_scripted_tool_calls_stream_as_openai_chunks(self) -> None:
        responder = PlannedResponder([{"tool": "treasury_propose", "arguments": {"amount_units": 10, "kind": "sandbox_trade"}}])
        _, url = self._proxy(mode="scripted", responder=responder)
        tools = [{"function": {"name": "ext__treasury_propose", "parameters": {}}, "type": "function"}]
        _, title = post(url + "/v1/chat/completions", {"messages": [{"content": "name this chat", "role": "user"}]})
        self.assertEqual(json.loads(title)["choices"][0]["message"]["content"], "scripted")
        status, raw = post(url + "/v1/chat/completions", {"messages": [{"content": "go", "role": "user"}], "stream": True, "tools": tools})
        self.assertEqual(status, 200)
        events = [line[len(b"data: "):] for line in raw.split(b"\n\n") if line.startswith(b"data: ")]
        self.assertEqual(events[-1], b"[DONE]")
        first = json.loads(events[0])["choices"][0]["delta"]
        call = first["tool_calls"][0]
        self.assertEqual((call["index"], call["function"]["name"]), (0, "ext__treasury_propose"))
        self.assertEqual(json.loads(call["function"]["arguments"]), {"amount_units": 10, "kind": "sandbox_trade"})
        self.assertEqual(json.loads(events[1])["choices"][0]["finish_reason"], "tool_calls")
        _, done = post(url + "/v1/chat/completions", {"messages": [{"content": "next", "role": "user"}], "tools": tools})
        self.assertEqual(json.loads(done)["choices"][0]["message"]["content"], "done")

    def test_non_loopback_upstreams_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            ModelProxy(mode="live", model_id="m", record_path=self.root / "x.jsonl", upstream="http://example.com:8080")


if __name__ == "__main__":
    unittest.main()
