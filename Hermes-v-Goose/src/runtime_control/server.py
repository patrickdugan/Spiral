"""Loopback HTTP daemon around one ``ControlModule``.

Each caller role has its own bearer token, and each route accepts only the roles
that may use it: a shim can propose but not commit, the gateway can commit but
not propose, and only the harness opens runs, writes principal events and
answers escalations.
"""

from __future__ import annotations

import hmac
import json
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl
from typing import Any, Mapping

from runtime_control.module import ControlError, ControlModule


ROLES = ("harness", "shim", "gateway", "proxy")
ESCALATION_ROUTE = re.compile(r"^/v1/escalations/(?P<escalation>[A-Za-z0-9_.-]+)$")
DELIVERY_ROUTE = re.compile(r"^/v1/interventions/(?P<intervention>[A-Za-z0-9_.-]+)/delivered$")


def new_tokens() -> dict[str, str]:
    return {role: secrets.token_hex(32) for role in ROLES}


def serve_control(
    module: ControlModule,
    tokens: Mapping[str, str],
    *,
    host: str = "127.0.0.1",
    port: int = 0,
) -> tuple[ThreadingHTTPServer, str]:
    """Start the daemon on loopback. Returns the running server and its base URL."""
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("the control module only binds to loopback")
    if set(tokens) != set(ROLES) or len(set(tokens.values())) != len(ROLES):
        raise ValueError(f"need one distinct token per role: {ROLES}")

    def role_of(header: str | None) -> str | None:
        if not header or not header.startswith("Bearer "):
            return None
        presented = header[len("Bearer "):]
        for role, token in tokens.items():
            if hmac.compare_digest(presented, token):
                return role
        return None

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            return None

        def _reply(self, status: int, body: Any) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _error(self, status: int, code: str, message: str) -> None:
            self._reply(status, {"error": {"code": code, "message": message}})

        def _body(self) -> Any:
            length = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(length) or b"null")

        def _dispatch(self, method: str) -> None:
            role = role_of(self.headers.get("Authorization"))
            if role is None:
                self._error(401, "unauthenticated", "missing or unknown bearer token")
                return
            path, _, query = self.path.partition("?")
            path = path.rstrip("/")
            try:
                # A GET's parameters arrive as its body.
                body = self._body() if method == "POST" else dict(parse_qsl(query))
                result = self._route(method, path, role, body)
            except json.JSONDecodeError:
                self._error(400, "malformed_json", "request body is not JSON")
                return
            except ControlError as exc:
                self._error(exc.status, exc.code, str(exc))
                return
            except PermissionError as exc:
                self._error(403, "role_not_allowed", str(exc))
                return
            if result is None:
                self._error(404, "not_found", path)
                return
            self._reply(200, result)

        def _route(self, method: str, path: str, role: str, body: Any) -> Any:
            def allow(*roles: str) -> None:
                if role not in roles:
                    raise PermissionError(f"role {role} cannot call {method} {path}")

            if method == "POST" and path == "/v1/runs":
                allow("harness")
                return module.open_run(body)
            if method == "POST" and path == "/v1/decide":
                allow("shim")
                if not isinstance(body, Mapping):
                    raise ControlError("malformed_request", "decide needs {proposal, waitMs}")
                return module.decide(body.get("proposal"), wait_ms=int(body.get("waitMs") or 0))
            if method == "POST" and path == "/v1/commit":
                allow("gateway")
                return module.commit(body)
            if method == "POST" and path == "/v1/outcome":
                allow("shim", "gateway")
                return module.outcome(body)
            if method == "POST" and path == "/v1/events":
                if not isinstance(body, Mapping):
                    raise ControlError("malformed_request", "events need {kind, payload}")
                return module.event(str(body.get("kind")), body.get("payload"), role)
            if method == "GET" and path == "/v1/projection":
                allow("harness", "shim", "gateway")
                return module.projection()
            if method == "GET" and path == "/v1/state":
                allow("harness")
                return module.snapshot()
            if method == "POST" and path == "/v1/runs/close":
                allow("harness")
                return module.close((body or {}).get("summary"))
            if method == "GET" and path == "/v1/interventions":
                allow("harness", "shim", "gateway")
                return module.pending_interventions(body.get("agentId") or None)
            delivery = DELIVERY_ROUTE.match(path)
            if method == "POST" and delivery:
                allow("harness", "shim")
                return module.deliver_intervention(delivery["intervention"], (body or {}).get("channel"))
            match = ESCALATION_ROUTE.match(path)
            if method == "POST" and match:
                allow("harness")
                return module.resolve_escalation(match["escalation"], body or {})
            return None

        def do_GET(self) -> None:
            self._dispatch("GET")

        def do_POST(self) -> None:
            self._dispatch("POST")

    server = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://{host}:{server.server_address[1]}"
