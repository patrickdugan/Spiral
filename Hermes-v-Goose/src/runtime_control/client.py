"""HTTP client for the control module, with the same method names as ``ControlModule``.

Shims, the gateway and the model proxy use it when the control module runs in
another process. Any transport failure raises ``ControlUnavailable``; callers
treat that as a denial.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Mapping
from urllib.parse import urlsplit

from runtime_control.errors import ControlError, ControlUnavailable


LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


class ControlClient:
    def __init__(self, base_url: str, token: str, *, timeout_s: float = 30.0) -> None:
        parts = urlsplit(base_url)
        if parts.scheme != "http" or parts.hostname not in LOOPBACK_HOSTS:
            raise ValueError(f"the control module is reached over loopback http only: {base_url}")
        self._base = base_url.rstrip("/")
        self._token = token
        self._timeout_s = timeout_s

    def _call(self, method: str, path: str, body: Any = None, *, timeout_s: float | None = None) -> Any:
        request = urllib.request.Request(
            self._base + path,
            method=method,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_s or self._timeout_s) as response:
                return json.loads(response.read() or b"null")
        except urllib.error.HTTPError as exc:
            try:
                error = json.loads(exc.read()).get("error", {})
            except (json.JSONDecodeError, AttributeError):
                error = {}
            raise ControlError(error.get("code", f"http_{exc.code}"), error.get("message", str(exc)), exc.code) from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            raise ControlUnavailable(str(exc)) from exc

    def open_run(self, spec: Mapping[str, Any]) -> dict[str, Any]:
        return self._call("POST", "/v1/runs", dict(spec))

    def decide(self, proposal: Mapping[str, Any], *, wait_ms: int = 0) -> dict[str, Any]:
        timeout = self._timeout_s + wait_ms / 1000
        return self._call("POST", "/v1/decide", {"proposal": dict(proposal), "waitMs": wait_ms}, timeout_s=timeout)

    def commit(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return self._call("POST", "/v1/commit", dict(request))

    def outcome(self, outcome: Mapping[str, Any]) -> dict[str, Any]:
        return self._call("POST", "/v1/outcome", dict(outcome))

    def event(self, kind: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._call("POST", "/v1/events", {"kind": kind, "payload": dict(payload)})

    def projection(self) -> dict[str, Any]:
        return self._call("GET", "/v1/projection")

    def resolve_escalation(self, escalation_id: str, answer: Mapping[str, Any]) -> dict[str, Any]:
        return self._call("POST", f"/v1/escalations/{escalation_id}", dict(answer))

    def pending_interventions(self, agent_id: str | None = None) -> list[dict[str, Any]]:
        from urllib.parse import quote

        return self._call("GET", "/v1/interventions" + (f"?agentId={quote(agent_id)}" if agent_id else ""))

    def deliver_intervention(self, intervention_id: str, channel: str) -> dict[str, Any]:
        return self._call("POST", f"/v1/interventions/{intervention_id}/delivered", {"channel": channel})

    def close(self, summary: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self._call("POST", "/v1/runs/close", {"summary": dict(summary or {})})

    def snapshot(self) -> dict[str, Any]:
        return self._call("GET", "/v1/state")
