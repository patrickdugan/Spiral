"""goose PreToolUse hook: propose every tool call to the control module first.

goose (1.53) runs each plugin hook as ``sh -c <command>`` with a JSON
``HookContext`` on stdin. For ``PreToolUse`` a hook blocks the call by printing
``{"decision": "block", "reason": ...}`` or exiting 2; with
``"on_failure": "block"`` a hook that crashes or times out also blocks.

This hook allows a call only when the control module answers ``allow``. Every
other outcome blocks: a refusal, an escalation that times out, an unreachable
control module, or a malformed payload. Gateway tools arrive named
``<extension>__<tool>`` and are proposed under the registry's bare tool id, so
the fingerprint matches the one the gateway computes and the lease is found.
Any other tool (goose's built-ins) is proposed under its native name; it is not
in the registry, so the control module treats it as consequential and refuses.

Known limits of this tier, from goose's source: hooks are disabled in subagent
sessions, and tool calls made from inside code mode do not reach hooks. Runs
in this tier must not enable either.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping, TextIO

from runtime_control.client import ControlClient
from runtime_control.errors import ControlError, ControlUnavailable
from runtime_control.wire import PROPOSAL_SCHEMA, PROVENANCE_SCHEMA, call_fingerprint


CONFIG_SCHEMA = "control.goose_hook_config.v1"
CONFIG_FIELDS = {
    "schema",
    "controlUrl",
    "shimToken",
    "runId",
    "contractHash",
    "registryHash",
    "agentId",
    "runtime",
    "gatewayExtension",
    "registryTools",
    "waitMs",
    "timeoutS",
    "payloadLog",
}


def load_config(path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    unknown = set(config) - CONFIG_FIELDS
    if config.get("schema") != CONFIG_SCHEMA or unknown:
        raise ValueError(f"bad hook config: schema={config.get('schema')} unknown={sorted(unknown)}")
    return config


def tool_id_for(native_name: str, config: Mapping[str, Any]) -> str:
    """Map goose's tool name to the registry id; unmapped names pass through unchanged."""
    prefix, sep, bare = native_name.partition("__")
    if sep and prefix == config["gatewayExtension"] and bare in config["registryTools"]:
        return bare
    return native_name


def build_proposal(payload: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    native = str(payload.get("tool_name") or "")
    if not native:
        raise ValueError("PreToolUse payload has no tool_name")
    args = payload.get("tool_input") or {}
    if not isinstance(args, Mapping):
        raise ValueError("tool_input is not an object")
    tool_id = tool_id_for(native, config)
    provenance: dict[str, Any] = {
        "schema": PROVENANCE_SCHEMA,
        "attestation": "shim",
        "contextTaint": [],
        "surface": "agent_loop",
    }
    if payload.get("tool_call_id"):
        provenance["nativeCallId"] = str(payload["tool_call_id"])
    return {
        "schema": PROPOSAL_SCHEMA,
        "actor": {"agentId": config["agentId"], "lineage": [str(payload.get("session_id") or "")]},
        "args": dict(args),
        "contractHash": config["contractHash"],
        "fingerprint": call_fingerprint(config["runId"], config["agentId"], tool_id, args),
        "proposedAt": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "provenance": provenance,
        "runId": config["runId"],
        "runtime": dict(config["runtime"]),
        "seq": time.time_ns() // 1000,
        "tool": {"id": tool_id, "nativeName": native, "registryHash": config["registryHash"]},
    }


def verdict_for(payload: Mapping[str, Any], config: Mapping[str, Any], client: Any) -> str | None:
    """Return None to allow, or the reason the call is blocked."""
    if payload.get("event") != "PreToolUse":
        return None
    try:
        decision = client.decide(build_proposal(payload, config), wait_ms=int(config.get("waitMs", 0)))
    except ControlUnavailable:
        return "control: control_unavailable"
    except ControlError as exc:
        return f"control: {exc.code}"
    if decision.get("verdict") == "allow":
        return None
    codes = ",".join(decision.get("reasonCodes") or []) or "refused"
    return f"control: {decision.get('verdict')} {codes}"


def main(argv: list[str] | None = None, stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] != "--config":
        print("usage: goose_control_hook --config <path>", file=sys.stderr)
        return 1
    config = load_config(args[1])
    raw = stdin.read()
    if config.get("payloadLog"):
        with open(config["payloadLog"], "a", encoding="utf-8") as handle:
            handle.write(raw.strip() + "\n")
    payload = json.loads(raw)
    client = ControlClient(config["controlUrl"], config["shimToken"], timeout_s=float(config.get("timeoutS", 20)))
    reason = verdict_for(payload, config, client)
    if reason is not None:
        stdout.write(json.dumps({"decision": "block", "reason": reason}))
    return 0
