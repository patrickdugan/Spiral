"""BitAgent's run-contract gates as a policy engine (design phase 6).

The gates are TypeScript: ``evaluateGates`` in BitAgent's
``apps/bitagent-launch-kernel/src/runcontract/gate.ts``. This engine does not
re-implement them. It sends each call to that code through its stdio JSONL gate
server (``scripts/bitagent-gate-server.ts``), so a decision here and a decision
in BitAgent's own bench are the same function on the same inputs.

Config::

    {"tools": {tool_id: {"envelopeArg": "envelope", "phase": "execute"}},
     "contextKey": "bitagent", "disabled": []}

A rule names the argument that carries the ``ActionEnvelopeDraft`` and the gate
phase the tool stands for (``simulate``, ``approval`` or ``execute``). The rest
of the gate context (contract, approval, budget, evidence receipts, the host's
clock and chain tip, the simulation hash a lease was issued for) comes from the
environment's public view under ``contextKey``, so it is on the ledger with
every decision. Only the receipts the envelope references are sent; the gates
resolve nothing else. ``disabled`` lists gates to knock out (BitAgent's
mutation experiments). Tools without a rule are admitted; the registry decides
whether they are consequential at all.

Verdicts: a refused envelope is ``deny`` with BitAgent's own reason codes
(``G07_per_action_cap:per_action_cap_exceeded``); an admitted one is ``allow``
when the contract delegates within its scope (BitAgent routes it to a lease)
and ``escalate`` with ``wallet_user_approval`` when the wallet user must
approve. The full BitAgent verdict is the engine row's ``native``.

The server is found through ``BITAGENT_APP_ROOT`` and ``BITAGENT_NODE``. One
server process serves every engine in this process; a dead or slow server
raises, which the control module records as ``deny`` with ``engine_error``.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import queue
import subprocess
import threading
from pathlib import Path
from typing import Any, Mapping

from runtime_control.engines import EngineConfigError, register_engine
from runtime_control.wire import sha256_hex


ENGINE_ID = "bitagent-gates-v1"
REQUEST_SCHEMA = "bitagent.gate_request.v1"
PHASES = ("simulate", "approval", "execute")
DEFAULT_APP_ROOT = Path.home() / "OneDrive" / "Documents" / "GitHub" / "BitAgent" / "apps" / "bitagent-launch-kernel"
DEFAULT_NODES = (
    Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node.exe",
)
# The gate code a verdict depends on; its bytes are part of the policy hash.
GATE_SOURCES = ("src/runcontract/gate.ts", "src/runcontract/constants.ts", "src/runcontract/contract.ts", "src/runcontract/gateServer.ts", "src/launch/canonical.ts")
CONTEXT_FIELDS = ("contract", "approval", "budget", "receipts", "now")
OPTIONAL_CONTEXT = ("tipSequence", "leaseSimulationHash")


class GateServerError(RuntimeError):
    pass


def find_bitagent() -> tuple[Path, Path] | None:
    """(app root, node) for a BitAgent checkout with its gate server, or None."""
    root = Path(os.environ.get("BITAGENT_APP_ROOT") or DEFAULT_APP_ROOT)
    nodes = [Path(os.environ["BITAGENT_NODE"])] if os.environ.get("BITAGENT_NODE") else list(DEFAULT_NODES)
    node = next((item for item in nodes if item.is_file()), None)
    if node is None or not (root / "scripts" / "bitagent-gate-server.ts").is_file() or not (root / "node_modules" / "tsx" / "dist" / "cli.mjs").is_file():
        return None
    return root, node


def gate_code_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for name in GATE_SOURCES:
        digest.update(name.encode("utf-8") + b"\0" + (root / name).read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()


class GateServer:
    """One ``bitagent-gate-server`` process; requests are answered in order, one at a time."""

    def __init__(self, root: Path, node: Path, *, timeout_s: float = 30.0) -> None:
        self.root, self.node, self.timeout_s = root, node, timeout_s
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._seq = 0

    def _start(self) -> subprocess.Popen[str]:
        if self._process is None or self._process.poll() is not None:
            self._lines = queue.Queue()
            self._process = subprocess.Popen(
                [str(self.node), str(self.root / "node_modules" / "tsx" / "dist" / "cli.mjs"), str(self.root / "scripts" / "bitagent-gate-server.ts")],
                cwd=self.root, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", bufsize=1,
            )
            threading.Thread(target=self._read, args=(self._process, self._lines), daemon=True).start()
        return self._process

    @staticmethod
    def _read(process: subprocess.Popen[str], lines: "queue.Queue[str | None]") -> None:
        for line in process.stdout:  # type: ignore[union-attr]
            lines.put(line)
        lines.put(None)

    def evaluate(self, request: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            process = self._start()
            self._seq += 1
            body = dict(request) | {"id": f"q-{self._seq}"}
            try:
                process.stdin.write(json.dumps(body) + "\n")  # type: ignore[union-attr]
                process.stdin.flush()  # type: ignore[union-attr]
                line = self._lines.get(timeout=self.timeout_s)
            except (OSError, queue.Empty) as exc:
                self.close()
                raise GateServerError(f"gate server did not answer: {exc!r}") from exc
            if line is None:
                self.close()
                raise GateServerError("gate server exited")
            response = json.loads(line)
            if response.get("id") != body["id"]:
                self.close()
                raise GateServerError("gate server answered out of order")
            if not response.get("ok"):
                raise GateServerError(f"gate request refused: {response.get('error')}")
            return response["verdict"]

    def close(self) -> None:
        process, self._process = self._process, None
        if process is not None and process.poll() is None:
            try:
                process.stdin.close()  # type: ignore[union-attr]
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()


_SERVERS: dict[tuple[str, str], GateServer] = {}
_SERVERS_LOCK = threading.Lock()


def shared_server(root: Path, node: Path) -> GateServer:
    key = (str(root), str(node))
    with _SERVERS_LOCK:
        if key not in _SERVERS:
            _SERVERS[key] = GateServer(root, node)
        return _SERVERS[key]


@atexit.register
def _close_servers() -> None:
    for server in list(_SERVERS.values()):
        server.close()


class BitAgentGatesEngine:
    engine_id = ENGINE_ID

    def __init__(self, config: Mapping[str, Any]) -> None:
        tools = config.get("tools")
        if set(config) - {"tools", "contextKey", "disabled"} or not isinstance(tools, Mapping) or not tools:
            raise EngineConfigError("bitagent-gates config is {'tools': {tool_id: {envelopeArg, phase}}, 'contextKey'?, 'disabled'?}")
        for tool_id, rule in tools.items():
            if not isinstance(rule, Mapping) or set(rule) != {"envelopeArg", "phase"} or rule["phase"] not in PHASES:
                raise EngineConfigError(f"rule for {tool_id} needs envelopeArg and a phase in {PHASES}")
        found = find_bitagent()
        if found is None:
            raise EngineConfigError("BitAgent gate server not found; set BITAGENT_APP_ROOT and BITAGENT_NODE")
        self.root, node = found
        self.config = {"contextKey": str(config.get("contextKey", "bitagent")), "disabled": sorted(config.get("disabled") or []), "tools": {k: dict(v) for k, v in tools.items()}}
        self.policy_hash = sha256_hex({"config": self.config, "engineId": self.engine_id, "gateCodeSha256": gate_code_sha256(self.root)})
        self.server = shared_server(self.root, node)

    def request(self, proposal: Mapping[str, Any], view: Mapping[str, Any]) -> dict[str, Any] | None:
        """The gate request for a proposal, or None when the tool has no rule."""
        rule = self.config["tools"].get(proposal["tool"]["id"])
        if rule is None:
            return None
        envelope = proposal["args"].get(rule["envelopeArg"])
        context = view.get(self.config["contextKey"])
        if not isinstance(envelope, Mapping):
            raise ValueError(f"argument {rule['envelopeArg']} is not an action envelope")
        if not isinstance(context, Mapping) or any(field not in context for field in CONTEXT_FIELDS):
            raise ValueError(f"view.{self.config['contextKey']} needs {CONTEXT_FIELDS}")
        refs = [envelope.get("intentRef"), envelope.get("quoteRef"), *(envelope.get("priceRefs") or [])]
        by_id = {receipt.get("id"): receipt for receipt in context["receipts"]}
        request = {
            "schema": REQUEST_SCHEMA,
            "envelope": dict(envelope),
            "phase": rule["phase"],
            "receipts": [by_id[ref] for ref in dict.fromkeys(refs) if ref in by_id],
        } | {field: context[field] for field in ("contract", "approval", "budget", "now")}
        request |= {field: context[field] for field in OPTIONAL_CONTEXT if context.get(field) is not None}
        if self.config["disabled"]:
            request["disabled"] = list(self.config["disabled"])
        return request

    def evaluate(self, proposal: Mapping[str, Any], state: Any) -> dict[str, Any]:
        try:
            request = self.request(proposal, state.env_view)
        except ValueError as exc:
            return {"verdict": "deny", "reasonCodes": ["invalid_arguments"], "checks": {"envelope_valid": False}, "native": {"error": str(exc)}}
        if request is None:
            return {"verdict": "allow", "reasonCodes": [], "checks": {}, "native": None}
        verdict = self.server.evaluate(request)
        if not verdict["admitted"]:
            outcome, reasons = "deny", list(verdict["reasonCodes"])
        elif verdict["nextAuthority"] == "lease":
            outcome, reasons = "allow", []
        else:
            outcome, reasons = "escalate", ["wallet_user_approval"]
        return {"verdict": outcome, "reasonCodes": reasons, "checks": dict(verdict["checks"]), "native": verdict}


register_engine(ENGINE_ID, BitAgentGatesEngine)
