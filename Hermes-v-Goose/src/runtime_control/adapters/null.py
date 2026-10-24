"""A stand-in runtime for harness-driven episodes.

It forwards an actor's tool calls to the gateway over MCP, optionally proposing
each one to the control module first, as a patched runtime's shim would.
Without a shim the gateway is the only enforcement point.
"""

from __future__ import annotations

import itertools
import json
import urllib.request
from typing import Any, Callable, Mapping

from runtime_control.errors import ControlError, ControlUnavailable
from runtime_control.runs import NULL_RUNTIME
from runtime_control.wire import PROPOSAL_SCHEMA, PROVENANCE_SCHEMA, call_fingerprint


def http_mcp(url: str) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    def send(message: Mapping[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(url, data=json.dumps(message).encode("utf-8"), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())

    return send


class NullRuntimeAdapter:
    adapter_id = "null-runtime"

    def __init__(self, mcp: Callable[[Mapping[str, Any]], dict[str, Any]], *, shim: Any = None, run_id: str, contract_hash: str, registry_hash: str, agent_id: str = "root") -> None:
        self._mcp = mcp
        self._shim = shim
        self._run_id = run_id
        self._contract_hash = contract_hash
        self._registry_hash = registry_hash
        self._agent_id = agent_id
        self._seq = itertools.count()

    def call(self, tool: str, args: Mapping[str, Any]) -> tuple[bool, dict[str, Any]]:
        """Return (is_error, body) as the actor would see it."""
        seq = next(self._seq)
        if self._shim is not None:
            proposal = {
                "schema": PROPOSAL_SCHEMA,
                "actor": {"agentId": self._agent_id, "lineage": [self._run_id]},
                "args": dict(args),
                "contractHash": self._contract_hash,
                "fingerprint": call_fingerprint(self._run_id, self._agent_id, tool, args),
                "proposedAt": "1970-01-01T00:00:00.000+00:00",
                "provenance": {"schema": PROVENANCE_SCHEMA, "attestation": "shim", "contextTaint": [], "nativeCallId": f"call-{seq}", "surface": "agent_loop"},
                "runId": self._run_id,
                "runtime": dict(NULL_RUNTIME),
                "seq": seq,
                "tool": {"id": tool, "nativeName": tool, "registryHash": self._registry_hash},
            }
            try:
                decision = self._shim.decide(proposal)
            except (ControlUnavailable, ControlError):
                return True, {"outcome": "block", "reasonCodes": ["control_unavailable"]}
            if decision["verdict"] != "allow":
                return True, {"outcome": {"deny": "block"}.get(decision["verdict"], decision["verdict"]), "reasonCodes": decision["reasonCodes"]}
        response = self._mcp(
            {
                "id": seq,
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"_meta": {"agentId": self._agent_id, "callId": f"call-{seq}", "surface": "agent_loop"}, "arguments": dict(args), "name": tool},
            }
        )
        result = response["result"]
        return bool(result["isError"]), json.loads(result["content"][0]["text"])
