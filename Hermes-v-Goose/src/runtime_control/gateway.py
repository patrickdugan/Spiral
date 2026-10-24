"""Tool gateway: the only path from a runtime's tool call to an environment effect.

The gateway speaks MCP (JSON-RPC 2.0) over loopback HTTP or stdio, so any
runtime that can attach an MCP server can use it. For every ``tools/call`` it:

1. fingerprints the call and writes the oracle label to the truth plane,
2. asks the control module to commit (consume a lease, or decide without one),
3. executes against the environment only if committed,
4. reports the outcome with the environment's new public view, and
5. returns the result, or the denial, with the control projection attached.

If the control module cannot be reached the call is denied.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping, TextIO

from runtime_control.client import ControlUnavailable
from runtime_control.errors import ToolArgumentError
from runtime_control.module import ControlError
from runtime_control.wire import OUTCOME_SCHEMA, call_fingerprint, canonical_bytes, sha256_bytes


MCP_PROTOCOL_VERSION = "2025-06-18"
FEEDBACK_MODES = ("none", "outcome_only", "reason_codes")
ACTOR_OUTCOME = {"deny": "block", "escalate": "escalate"}
AGENT_HEADER = "X-Control-Agent"


class ToolGateway:
    def __init__(
        self,
        adapter: Any,
        control: Any,
        *,
        run_id: str,
        truth_path: str | Path,
        io_path: str | Path | None = None,
        feedback_mode: str = "reason_codes",
        default_agent: str = "root",
    ) -> None:
        if feedback_mode not in FEEDBACK_MODES:
            raise ValueError(f"feedback_mode must be one of {FEEDBACK_MODES}")
        self.adapter = adapter
        self.control = control
        self.run_id = run_id
        self.feedback_mode = feedback_mode
        self.default_agent = default_agent
        self.truth_path = Path(truth_path)
        self.io_path = Path(io_path) if io_path else None
        self._lock = threading.Lock()
        self._truth_seq = 0
        self._tool_names = {tool["name"] for tool in adapter.tools()}

    # ---------------------------------------------------------------- records

    def _write_line(self, path: Path, value: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as handle:
            handle.write(canonical_bytes(value) + b"\n")

    def _truth(self, fingerprint: str, tool: str, agent_id: str, label: Any) -> None:
        if label is None:
            return
        self._write_line(
            self.truth_path,
            {"agentId": agent_id, "fingerprint": fingerprint, "label": label, "seq": self._truth_seq, "toolId": tool},
        )
        self._truth_seq += 1

    # ---------------------------------------------------------------- tools

    def list_tools(self) -> list[dict[str, Any]]:
        return self.adapter.tools()

    def _feedback(self, verdict: str, reason_codes: list[str]) -> dict[str, Any]:
        if self.feedback_mode == "none":
            return {"outcome": "not_committed"}
        outcome = {"outcome": ACTOR_OUTCOME.get(verdict, verdict)}
        if self.feedback_mode == "reason_codes" and reason_codes:
            outcome["reasonCodes"] = list(reason_codes)
        return outcome

    def call_tool(
        self,
        name: str,
        args: Mapping[str, Any] | None,
        *,
        agent_id: str | None = None,
        native_call_id: str | None = None,
        surface: str = "agent_loop",
    ) -> dict[str, Any]:
        """Run one tool call through the control module. Returns an MCP ``CallToolResult``."""
        args = dict(args or {})
        agent = agent_id or self.default_agent
        started = time.perf_counter()
        with self._lock:
            fingerprint = call_fingerprint(self.run_id, agent, name, args)
            self._truth(fingerprint, name, agent, self.adapter.label(name, args) if name in self._tool_names else {"unknown_tool": True})
            request = {"agentId": agent, "args": args, "fingerprint": fingerprint, "surface": surface, "toolId": name}
            if native_call_id:
                request["nativeCallId"] = native_call_id
            try:
                decision = self.control.commit(request)
            except (ControlUnavailable, ControlError) as exc:
                code = getattr(exc, "code", "control_unavailable")
                return self._error_result({"outcome": "block", "reasonCodes": [code]})
            if not decision["committed"]:
                reply = self._report(fingerprint, decision, "denied", {}, started)
                return self._error_result(self._feedback(decision["verdict"], decision["reasonCodes"]) | self._trailer(reply))
            try:
                executed = self.adapter.execute(name, args, decision["decisionId"])
            except ToolArgumentError as exc:
                self._report(fingerprint, decision, "error", {"error": str(exc)}, started)
                return self._error_result({"outcome": "invalid", "detail": str(exc)})
            if "truth" in executed:
                self._truth(fingerprint, name, agent, {"committed": executed["truth"]})
            reply = self._report(fingerprint, decision, "ok", executed, started)
        body = {"outcome": "allow", "result": executed["result"]} | self._trailer(reply)
        if reply and reply.get("projection") is not None:
            body["control"] = reply["projection"]
        return {"content": [{"type": "text", "text": json.dumps(body, sort_keys=True)}], "isError": False}

    def _report(
        self, fingerprint: str, decision: Mapping[str, Any], status: str, executed: Mapping[str, Any], started: float
    ) -> dict[str, Any] | None:
        result_bytes = canonical_bytes(executed.get("result", executed))
        outcome: dict[str, Any] = {
            "schema": OUTCOME_SCHEMA,
            "decisionId": decision["decisionId"],
            "durationMs": int((time.perf_counter() - started) * 1000),
            "evidenceIds": list(executed.get("evidenceIds", [])),
            "fingerprint": fingerprint,
            "resultBytes": len(result_bytes),
            "resultSha256": sha256_bytes(result_bytes),
            "status": status,
            "view": self.adapter.view(),
        }
        if executed.get("effectId"):
            outcome["effectId"] = executed["effectId"]
        if self.io_path:
            self._write_line(self.io_path, {"decisionId": decision["decisionId"], "fingerprint": fingerprint, "result": executed.get("result"), "status": status})
        try:
            return self.control.outcome(outcome)
        except (ControlUnavailable, ControlError):
            return None

    @staticmethod
    def _trailer(reply: Mapping[str, Any] | None) -> dict[str, Any]:
        """Controller interventions the control module delivered on this tool result (the fallback channel)."""
        items = (reply or {}).get("interventions") or []
        return {"interventions": [{"kind": item["kind"], "text": item["text"]} for item in items]} if items else {}

    @staticmethod
    def _error_result(body: Mapping[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": json.dumps(dict(body), sort_keys=True)}], "isError": True}

    # ---------------------------------------------------------------- JSON-RPC

    def handle_jsonrpc(self, message: Any, *, agent_id: str | None = None) -> dict[str, Any] | None:
        if not isinstance(message, Mapping) or message.get("jsonrpc") != "2.0":
            return _rpc_error(None, -32600, "invalid request")
        method = message.get("method")
        request_id = message.get("id")
        if request_id is None:
            return None  # notification, e.g. notifications/initialized
        params = message.get("params") or {}
        if method == "initialize":
            return _rpc_result(
                request_id,
                {
                    "capabilities": {"tools": {"listChanged": False}},
                    "protocolVersion": params.get("protocolVersion", MCP_PROTOCOL_VERSION),
                    "serverInfo": {"name": "control-gateway", "version": "1"},
                },
            )
        if method == "ping":
            return _rpc_result(request_id, {})
        if method == "tools/list":
            return _rpc_result(request_id, {"tools": self.list_tools()})
        if method == "tools/call":
            name = params.get("name")
            if not isinstance(name, str):
                return _rpc_error(request_id, -32602, "tools/call needs a tool name")
            meta = params.get("_meta") or {}
            return _rpc_result(
                request_id,
                self.call_tool(
                    name,
                    params.get("arguments") or {},
                    agent_id=agent_id or meta.get("agentId"),
                    native_call_id=meta.get("callId"),
                    surface=meta.get("surface", "agent_loop"),
                ),
            )
        return _rpc_error(request_id, -32601, f"method not found: {method}")

    def serve_stdio(self, stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> None:
        for line in stdin:
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                response = _rpc_error(None, -32700, "parse error")
            else:
                response = self.handle_jsonrpc(message)
            if response is not None:
                stdout.write(json.dumps(response) + "\n")
                stdout.flush()


def _rpc_result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"id": request_id, "jsonrpc": "2.0", "result": result}


def _rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}, "id": request_id, "jsonrpc": "2.0"}


def serve_gateway_http(gateway: ToolGateway, *, host: str = "127.0.0.1", port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    """Serve ``POST /mcp`` on loopback. Returns the server (already running) and its URL."""
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("the gateway only binds to loopback")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:  # keep test output quiet
            return None

        def do_GET(self) -> None:  # no server-initiated stream
            self.send_response(405)
            self.send_header("Allow", "POST")
            self.end_headers()

        def do_POST(self) -> None:
            if self.path.rstrip("/") != "/mcp":
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                message = json.loads(self.rfile.read(length) or b"null")
            except json.JSONDecodeError:
                response: Any = _rpc_error(None, -32700, "parse error")
            else:
                agent = self.headers.get(AGENT_HEADER)
                if isinstance(message, list):
                    response = [r for r in (gateway.handle_jsonrpc(m, agent_id=agent) for m in message) if r]
                else:
                    response = gateway.handle_jsonrpc(message, agent_id=agent)
            if response is None or response == []:
                self.send_response(202)
                self.end_headers()
                return
            data = json.dumps(response).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://{host}:{server.server_address[1]}/mcp"
