"""Model proxy: an OpenAI-compatible endpoint in front of the model server.

Both runtimes point their base URL here instead of at llama-server. The proxy

* enforces the context ceiling with the model server's own tokenizer, so no
  request above it reaches the model (design invariant I7);
* records every request and response body to ``model_io.jsonl`` and reports a
  ``model_turn`` and a ``context_packet`` to the control module; and
* can answer without a model: ``scripted`` mode plays a planned sequence of
  tool calls, ``replay`` mode answers from a recorded ``model_io.jsonl``.

Only loopback upstreams are accepted, as in ``models.local_chat_runner``.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence
from urllib.parse import urlsplit

from runtime_control.ledger import canonical_json_bytes


MODES = ("live", "scripted", "replay")
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
CHAT_PATHS = ("/v1/chat/completions", "/chat/completions")
ESTIMATE_CHARS_PER_TOKEN = 3.2  # Hermes Lite's fallback ratio (agent/lean_packet.py)


def request_sha256(body: Mapping[str, Any]) -> str:
    # Request bodies carry float sampling parameters, so they are hashed with the
    # float-tolerant canonical form and never written to the hash-checked ledger.
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / ESTIMATE_CHARS_PER_TOKEN)


class PlannedResponder:
    """Answer each chat request with the next planned assistant turn.

    A plan step is ``{"tool": name, "arguments": {...}}``, ``{"calls": [step, ...]}``
    for several tool calls in one assistant turn, or ``{"content": text}``.
    When the plan is exhausted the responder answers ``{"content": "done"}``.
    A runtime may prefix tool names (Goose advertises ``<extension>__<tool>``), so a
    step's tool is matched against the request's advertised tools by exact name
    first, then by that suffix.

    Only requests that advertise tools advance the plan. Runtimes also make
    auxiliary calls with no tools (goose asks for a session title even with
    ``--no-session``); those get ``auxiliary_reply`` and leave the plan alone.
    """

    auxiliary_reply = "scripted"

    @staticmethod
    def _advertised(body: Mapping[str, Any], name: str) -> str:
        names = [str((tool.get("function") or {}).get("name", "")) for tool in body.get("tools") or ()]
        if name in names:
            return name
        matches = [item for item in names if item.endswith(f"__{name}")]
        return matches[0] if len(matches) == 1 else name

    def __init__(self, plan: Sequence[Mapping[str, Any]]) -> None:
        self._plan = list(plan)
        self._calls = 0
        self._lock = threading.Lock()

    def __call__(self, body: Mapping[str, Any]) -> dict[str, Any]:
        if not body.get("tools"):
            return {"content": self.auxiliary_reply, "role": "assistant"}
        with self._lock:
            step = self._plan.pop(0) if self._plan else {"content": "done"}
            self._calls += 1
            call_id = f"call_{self._calls}"
        if "tool" in step or "calls" in step:
            calls = [(call_id, step)] if "tool" in step else [(f"{call_id}_{i}", item) for i, item in enumerate(step["calls"])]
            return {
                "content": None,
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {"arguments": json.dumps(item.get("arguments", {})), "name": self._advertised(body, item["tool"])},
                        "id": item_id,
                        "type": "function",
                    }
                    for item_id, item in calls
                ],
            }
        return {"content": str(step["content"]), "role": "assistant"}


class ModelProxy:
    def __init__(
        self,
        *,
        mode: str,
        model_id: str,
        record_path: str | Path,
        ceiling_tokens: int = 12_000,
        default_output_reserve: int = 512,
        upstream: str | None = None,
        responder: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        replay_path: str | Path | None = None,
        control: Any = None,
        timeout_s: float = 600.0,
        replay_normalizers: Sequence[tuple[str, str]] = (),
        upstream_extra: Mapping[str, Any] | None = None,
    ) -> None:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if mode == "live":
            parts = urlsplit(upstream or "")
            if parts.scheme != "http" or parts.hostname not in LOOPBACK_HOSTS:
                raise ValueError(f"live mode needs a loopback http upstream: {upstream}")
        if mode == "scripted" and responder is None:
            raise ValueError("scripted mode needs a responder")
        self.mode = mode
        self.model_id = model_id
        self.ceiling_tokens = ceiling_tokens
        self.default_output_reserve = default_output_reserve
        self.upstream = (upstream or "").rstrip("/")
        # Fields added to every live request, such as a llama-server per-request LoRA scale, so one
        # server can play two models; the record keeps what the runtime sent.
        self.upstream_extra = dict(upstream_extra or {})
        self.responder = responder
        self.control = control
        self.timeout_s = timeout_s
        self.record_path = Path(record_path)
        self._lock = threading.Lock()
        self._turn = 0
        self._replay: dict[str, list[dict[str, Any]]] = {}
        # Replay matches requests exactly unless the run declares spans that may differ, such as a
        # runtime's timestamp in its prompt; each is a (regex, replacement) over the request JSON.
        self.replay_normalizers = [(re.compile(pattern), replacement) for pattern, replacement in replay_normalizers]
        self.normalized_matches = 0
        if mode == "replay":
            for line in Path(replay_path or "").read_text(encoding="utf-8").splitlines():
                item = json.loads(line)
                if item.get("status") == "ok":
                    self._replay.setdefault(self._replay_key(item["request"]), []).append(item["response"])

    # ---------------------------------------------------------------- upstream

    def _upstream(self, path: str, body: Any = None, *, stream: bool = False) -> Any:
        request = urllib.request.Request(
            self.upstream + path,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = urllib.request.urlopen(request, timeout=self.timeout_s)
        if stream:
            return response
        with response:
            return json.loads(response.read())

    def count_tokens(self, body: Mapping[str, Any]) -> tuple[int, str]:
        """Count prompt tokens. Live mode uses the server's template and tokenizer."""
        tools_text = json.dumps(body.get("tools"), sort_keys=True) if body.get("tools") else ""
        if self.mode == "live":
            try:
                prompt = self._upstream("/apply-template", {"messages": body.get("messages", [])})["prompt"]
                counter = "server_template"
            except (urllib.error.URLError, KeyError, json.JSONDecodeError, OSError):
                prompt = "\n".join(str(m.get("content") or "") for m in body.get("messages", []))
                counter = "server_tokenize_concat"
            try:
                total = len(self._upstream("/tokenize", {"add_special": True, "content": prompt})["tokens"])
                if tools_text:
                    total += len(self._upstream("/tokenize", {"add_special": False, "content": tools_text})["tokens"])
                return total, counter + ("+tools_json" if tools_text else "")
            except (urllib.error.URLError, KeyError, json.JSONDecodeError, OSError):
                pass
        text = json.dumps(body.get("messages", []), sort_keys=True) + tools_text
        return estimate_tokens(text), "estimate"

    # ---------------------------------------------------------------- chat

    def chat(self, body: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
        """Return (HTTP status, non-streamed chat completion or error)."""
        with self._lock:
            turn = self._turn
            self._turn += 1
        started = time.perf_counter()
        digest = request_sha256(body)
        input_tokens, counter = self.count_tokens(body)
        reserve = int(body.get("max_tokens") or body.get("max_completion_tokens") or self.default_output_reserve)
        overflow = input_tokens + reserve > self.ceiling_tokens
        self._report("context_packet", {"ceilingTokens": self.ceiling_tokens, "counter": counter, "inputTokens": input_tokens, "outputReserve": reserve, "overflow": overflow, "turnId": f"t-{turn}"})
        if overflow:
            error = {
                "error": {
                    "code": "context_length_exceeded",
                    "message": (
                        f"This model's maximum context length is {self.ceiling_tokens} tokens. However, "
                        f"your messages resulted in {input_tokens} tokens plus {reserve} reserved for output."
                    ),
                    "param": "messages",
                    "type": "invalid_request_error",
                }
            }
            self._record(turn, digest, body, error, "refused_ceiling", input_tokens, counter, started)
            return 400, error
        try:
            response = self._complete(body, input_tokens)
        except LookupError as exc:
            error = {"error": {"code": "replay_miss", "message": str(exc), "type": "server_error"}}
            self._record(turn, digest, body, error, "replay_miss", input_tokens, counter, started)
            return 500, error
        except urllib.error.HTTPError as exc:
            error = {"error": {"code": f"upstream_{exc.code}", "message": exc.read().decode("utf-8", "replace")[:2000], "type": "upstream_error"}}
            self._record(turn, digest, body, error, "upstream_error", input_tokens, counter, started)
            return exc.code, error
        self._record(turn, digest, body, response, "ok", input_tokens, counter, started)
        return 200, response

    def _complete(self, body: Mapping[str, Any], input_tokens: int = 0) -> dict[str, Any]:
        if self.mode == "live":
            forwarded = dict(body) | self.upstream_extra | {"stream": False}
            forwarded.pop("stream_options", None)
            return self._upstream("/v1/chat/completions", forwarded)
        if self.mode == "replay":
            key = self._replay_key(body)
            queue = self._replay.get(key)
            if not queue:
                raise LookupError("no recorded response for this request")
            if key != request_sha256(body):
                self.normalized_matches += 1
            return queue.pop(0)
        message = dict(self.responder(body))
        return {
            "choices": [{"finish_reason": "tool_calls" if message.get("tool_calls") else "stop", "index": 0, "message": message}],
            "created": 0,
            "id": f"chatcmpl-scripted-{self._turn}",
            "model": self.model_id,
            "object": "chat.completion",
            # Report the proxy's own input count; zero usage makes some clients
            # (litellm) re-tokenize, which needs a tokenizer download.
            "usage": {"completion_tokens": 1, "prompt_tokens": input_tokens, "total_tokens": input_tokens + 1},
        }

    def _record(self, turn: int, digest: str, body: Any, response: Any, status: str, input_tokens: int, counter: str, started: float) -> None:
        latency = int((time.perf_counter() - started) * 1000)
        response_digest = request_sha256(response)
        line = {
            "counter": counter,
            "index": turn,
            "inputTokens": input_tokens,
            "latencyMs": latency,
            "mode": self.mode,
            "request": body,
            "requestSha256": digest,
            "response": response,
            "responseSha256": response_digest,
            "status": status,
        }
        with self._lock:
            self.record_path.parent.mkdir(parents=True, exist_ok=True)
            with self.record_path.open("ab") as handle:
                handle.write(canonical_json_bytes(line) + b"\n")
        usage = (response or {}).get("usage") or {}
        self._report(
            "model_turn",
            {
                "counter": counter,
                "inputTokens": input_tokens,
                "latencyMs": latency,
                "mode": self.mode,
                "modelId": self.model_id,
                "outputTokens": int(usage.get("completion_tokens") or 0),
                "requestSha256": digest,
                "responseSha256": response_digest,
                "status": status,
                "turnId": f"t-{turn}",
            },
        )

    def _report(self, kind: str, payload: Mapping[str, Any]) -> None:
        if self.control is None:
            return
        try:
            if hasattr(self.control, "state"):  # in-process ControlModule
                self.control.event(kind, payload, "proxy")
            else:
                self.control.event(kind, payload)
        except Exception:  # noqa: BLE001 - reporting must not change the model's answer
            pass

    def _replay_key(self, body: Mapping[str, Any]) -> str:
        if not self.replay_normalizers:
            return request_sha256(body)
        text = canonical_json_bytes(body).decode("utf-8")
        for pattern, replacement in self.replay_normalizers:
            text = pattern.sub(replacement, text)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def tokenize(self, body: Mapping[str, Any]) -> dict[str, Any]:
        if self.mode == "live":
            return self._upstream("/tokenize", dict(body))
        return {"tokens": list(range(estimate_tokens(str(body.get("content", "")))))}


def sse_chunks(completion: Mapping[str, Any]) -> Iterator[bytes]:
    """Render a finished completion as an OpenAI streaming response."""
    choice = completion["choices"][0]
    message = choice["message"]
    delta: dict[str, Any] = {"role": "assistant"}
    if message.get("content"):
        delta["content"] = message["content"]
    if message.get("tool_calls"):
        delta["tool_calls"] = [dict(call) | {"index": i} for i, call in enumerate(message["tool_calls"])]
    base = {"created": completion.get("created", 0), "id": completion.get("id", "chatcmpl"), "model": completion.get("model"), "object": "chat.completion.chunk"}
    yield b"data: " + json.dumps(base | {"choices": [{"delta": delta, "finish_reason": None, "index": 0}]}).encode("utf-8") + b"\n\n"
    final = base | {"choices": [{"delta": {}, "finish_reason": choice.get("finish_reason", "stop"), "index": 0}]}
    if completion.get("usage"):
        final["usage"] = completion["usage"]
    yield b"data: " + json.dumps(final).encode("utf-8") + b"\n\n"
    yield b"data: [DONE]\n\n"


def serve_proxy_http(proxy: ModelProxy, *, host: str = "127.0.0.1", port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    if host not in LOOPBACK_HOSTS:
        raise ValueError("the model proxy only binds to loopback")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            return None

        def _json(self, status: int, body: Any) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0].rstrip("/")
            if path in ("/v1/models", "/models"):
                self._json(200, {"data": [{"id": proxy.model_id, "object": "model", "owned_by": "control-proxy"}], "object": "list"})
            else:
                self._json(404, {"error": {"code": "not_found", "message": path}})

        def do_POST(self) -> None:
            path = self.path.split("?", 1)[0].rstrip("/")
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._json(400, {"error": {"code": "malformed_json", "message": "body is not JSON"}})
                return
            if path in CHAT_PATHS:
                status, response = proxy.chat(body)
                if status == 200 and body.get("stream"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    for chunk in sse_chunks(response):
                        self.wfile.write(chunk)
                    self.wfile.flush()
                    return
                self._json(status, response)
            elif path == "/tokenize":
                self._json(200, proxy.tokenize(body))
            else:
                self._json(404, {"error": {"code": "not_found", "message": path}})

    server = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://{host}:{server.server_address[1]}"
