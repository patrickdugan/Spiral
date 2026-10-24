"""goose runtime adapter, no-fork tiers (design section 6.3).

Tiers:

* ``gateway_only``: goose talks to the tool gateway as a streamable-HTTP MCP
  extension and to the model proxy as its OpenAI provider. The gateway is the
  only enforcement point.
* ``hooks``: as above, plus a ``control-gate`` plugin whose ``PreToolUse`` hook
  proposes every tool call to the control module before goose dispatches it.
  The run profile then requires the shim, so a gateway call without a lease is
  a detected bypass.

goose is isolated from the user's own setup on every run: ``GOOSE_PATH_ROOT``
points all goose directories (config, data, state, plugins) at the run
directory, the keyring is disabled, telemetry is off, and every non-loopback
request goes to the egress sink, which refuses and records it.

Not reachable in these tiers, from goose's source: subagent sessions run with
hooks disabled and in Auto mode, and tool calls made from inside code mode skip
hooks. Runs in these tiers therefore attach no summon or code-execution
extension; the fork tier closes both gaps.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from runtime_control.egress import egress_attempts, egress_env, serve_egress_sink
from runtime_control.ledger import parse_receipts, verify_receipt_file
from runtime_control.runs import run_spec
from runtime_control.gateway import ToolGateway, serve_gateway_http
from runtime_control.module import ControlModule
from runtime_control.proxy import ModelProxy, PlannedResponder, serve_proxy_http
from runtime_control.server import new_tokens, serve_control
from runtime_control.adapters.goose_acp import GooseAcpSession
from runtime_control.shims.goose_hook import CONFIG_SCHEMA


ROOT = Path(__file__).resolve().parents[3]
HOOK_SCRIPT = ROOT / "scripts" / "goose_control_hook.py"
TIERS = ("gateway_only", "hooks", "fork")
DRIVES = ("run", "acp")
ACP_GATEWAY_NAME = "gateway"
# Extensions `goose acp` 1.53 loaded by default in an empty config (observed 2026-10-09),
# plus code execution, which must never be on in the no-fork tiers.
DEFAULT_EXTENSIONS_OFF = ("developer", "analyze", "summon", "skills", "apps", "extensionmanager", "code_execution", "todo", "chatrecall")
SH_CANDIDATES = (r"C:\Program Files\Git\usr\bin\sh.exe", r"C:\Program Files\Git\bin\sh.exe")
TEST_API_KEY = "sk-local-test-not-a-secret"


def find_goose() -> Path | None:
    for candidate in (os.environ.get("GOOSE_BIN"), shutil.which("goose"), str(Path.home() / ".local" / "bin" / "goose.exe")):
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def find_sh() -> Path | None:
    found = shutil.which("sh")
    if found:
        return Path(found)
    return next((Path(item) for item in SH_CANDIDATES if Path(item).is_file()), None)


def gateway_extension_name(gateway_url: str) -> str:
    """goose's name for a streamable-HTTP extension added with --with-streamable-http-extension."""
    from urllib.parse import urlsplit

    parts = urlsplit(gateway_url)
    return "_".join(item for item in (parts.hostname.replace(".", "_"), str(parts.port), parts.path.strip("/").replace("/", "_")) if item)


def parse_json_output(stdout: str) -> dict[str, Any] | None:
    """goose prints a session banner before the JSON document; decode from the document."""
    for start in [0] + [index + 1 for index, char in enumerate(stdout) if char == "\n" and stdout[index + 1:index + 2] == "{"]:
        try:
            value, _ = json.JSONDecoder().raw_decode(stdout[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class GooseRuntimeAdapter:
    adapter_id = "goose"
    version = "1"

    def __init__(self, goose_bin: str | Path, run_dir: str | Path, *, tier: str = "hooks", hook_python: str | None = None) -> None:
        if tier not in TIERS:
            raise ValueError(f"tier must be one of {TIERS}")
        self.goose_bin = Path(goose_bin)
        self.run_dir = Path(run_dir)
        self.tier = tier
        self.hook_python = hook_python or sys.executable
        self.environment: dict[str, str] = {}
        self.extension_url = ""
        self.native: dict[str, Any] | None = None

    def capabilities(self) -> dict[str, Any]:
        return {
            "codeMode": False,
            "driveModes": ["run", "acp"],
            "nativeEvents": "goose run --output-format json",
            "shim": self.tier in ("hooks", "fork"),
            "subagents": False,
            "tier": self.tier,
        }

    def prepare(self, run: Mapping[str, Any]) -> dict[str, Any]:
        """Write goose's isolated root, the control-gate plugin and its hook config."""
        root = self.run_dir / "goose-root"
        root.mkdir(parents=True, exist_ok=False)
        receipt: dict[str, Any] = {"gooseSha256": _sha256_file(self.goose_bin), "tier": self.tier}
        # `goose acp` enables goose's default extensions (developer shell, subagents,
        # skills, extension manager, ...) unless config turns each one off; `goose run
        # --no-profile` loads none. Disable them so both drives offer the same tools.
        (root / "config").mkdir()
        lines = ["extensions:"]
        builtins = set(run.get("builtins", ()))
        for name in sorted(set(DEFAULT_EXTENSIONS_OFF) | builtins):
            # Requested builtins are switched on explicitly, which is what `goose acp`
            # needs; `goose run` gets them from --with-builtin as well.
            enabled = "true" if name in builtins else "false"
            lines += [f"  {name}:", f"    enabled: {enabled}", "    type: platform", f"    name: {name}", "    description: ''", "    bundled: true", "    available_tools: []"]
        (root / "config" / "config.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
        receipt["configSha256"] = _sha256_file(root / "config" / "config.yaml")
        if self.tier in ("hooks", "fork"):
            config_path = self.run_dir / "hook-config.json"
            config = {
                "schema": CONFIG_SCHEMA,
                "agentId": run.get("agentId", "root"),
                "contractHash": run["contractHash"],
                "controlUrl": run["controlUrl"],
                "gatewayExtension": run.get("gatewayExtension") or gateway_extension_name(run["gatewayUrl"]),
                "payloadLog": str(self.run_dir / "hook_payloads.jsonl"),
                "registryHash": run["registryHash"],
                "registryTools": sorted(run["registryTools"]),
                "runId": run["runId"],
                "runtime": dict(run["runtime"]),
                "shimToken": run["shimToken"],
                "timeoutS": int(run.get("hookTimeoutS", 30)),
                "waitMs": int(run.get("waitMs", 0)),
            }
            config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
            receipt["controlConfigSha256"] = _sha256_file(config_path)
        if self.tier == "hooks":
            python = run.get("hookPython", self.hook_python)
            command = f'"{Path(python).as_posix()}" "{HOOK_SCRIPT.as_posix()}" --config "{config_path.as_posix()}"'
            plugin = root / ".agents" / "plugins" / "control-gate"
            (plugin / "hooks").mkdir(parents=True)
            (plugin / "plugin.json").write_text(json.dumps({"description": "Propose every tool call to the control module.", "name": "control-gate", "version": "1.0.0"}), encoding="utf-8")
            hooks = {"hooks": {"PreToolUse": [{"hooks": [{"command": command, "on_failure": "block", "timeout": int(run.get("hookTimeoutS", 30)) + 5, "type": "command"}]}]}}
            (plugin / "hooks" / "hooks.json").write_text(json.dumps(hooks, indent=2), encoding="utf-8")
            receipt["hooksSha256"] = _sha256_file(plugin / "hooks" / "hooks.json")
        sh = find_sh()
        if self.tier == "hooks" and sh is None:
            raise RuntimeError("goose runs hooks with `sh`; install Git for Windows or put sh on PATH")
        path = os.environ.get("PATH", "")
        if sh is not None:
            path = str(sh.parent) + os.pathsep + path
        self.extension_url = run["gatewayUrl"]
        self.environment = dict(os.environ) | {
            "GOOSE_CONTEXT_LIMIT": str(run.get("contextLimit", 12_000)),
            "GOOSE_DISABLE_KEYRING": "1",
            # `goose run` takes --max-turns, but an ACP session reads only this; without it a live
            # model ran about 30 tool rounds a turn in phase 9's first R2 pass.
            "GOOSE_MAX_TURNS": str(int(run.get("maxTurns", 6))),
            "GOOSE_MODE": "auto",
            "GOOSE_MODEL": run["modelId"],
            "GOOSE_PATH_ROOT": str(root),
            "GOOSE_PROVIDER": "openai",
            "GOOSE_TELEMETRY_OFF": "1",
            "OPENAI_API_KEY": TEST_API_KEY,
            "OPENAI_HOST": run["proxyUrl"],
            "PATH": path,
        }
        if self.tier == "fork":
            # The fork reads the same config as the hook, through its control gate.
            self.environment["GOOSE_CONTROL_CONFIG"] = str(config_path)
            self.environment["GOOSE_CONTROL_REQUIRED"] = "1"
        if run.get("egressUrl"):
            # goose 1.53 fetches https://models.dev/api.json at every start and has no
            # switch for it. The egress sink refuses every non-loopback request.
            self.environment.update(egress_env(run["egressUrl"]))
            receipt["egress"] = "blocked_except_loopback"
        self.environment.update({str(k): str(v) for k, v in (run.get("extraEnv") or {}).items()})
        self.builtins = list(run.get("builtins", ()))
        self.max_turns = int(run.get("maxTurns", 6))
        return receipt

    def run_task(self, text: str, *, timeout_s: int = 300) -> dict[str, Any]:
        command = [str(self.goose_bin), "run", "--no-session", "--no-profile", "--with-streamable-http-extension", self.extension_url]
        for builtin in self.builtins:
            command += ["--with-builtin", builtin]
        command += ["--max-turns", str(self.max_turns), "--output-format", "json", "-t", text]
        completed = subprocess.run(command, env=self.environment, cwd=self.run_dir, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout_s)
        (self.run_dir / "goose_stdout.json").write_text(completed.stdout, encoding="utf-8")
        (self.run_dir / "goose_stderr.txt").write_text(completed.stderr, encoding="utf-8")
        self.native = parse_json_output(completed.stdout)
        return {"exitCode": completed.returncode, "native": self.native}

    def export_native(self, run_dir: str | None = None) -> dict[str, Any]:
        return self.native or {}

    def shutdown(self) -> None:
        return None

    @staticmethod
    def tool_calls(native: Mapping[str, Any] | None) -> list[dict[str, Any]]:
        """Pair every tool request in goose's transcript with its response."""
        requests: dict[str, dict[str, Any]] = {}
        for message in (native or {}).get("messages", ()):
            for item in message.get("content", ()):
                if item.get("type") == "toolRequest":
                    value = (item.get("toolCall") or {}).get("value") or {}
                    requests[item["id"]] = {"arguments": value.get("arguments"), "id": item["id"], "name": value.get("name"), "response": None}
                elif item.get("type") == "toolResponse" and item.get("id") in requests:
                    result = item.get("toolResult") or {}
                    value = result.get("value") or {}
                    text = " ".join(part.get("text", "") for part in value.get("content", ()) if isinstance(part, dict)) if isinstance(value, dict) else ""
                    requests[item["id"]]["response"] = {"isError": result.get("status") != "success" or bool(value.get("isError")) if isinstance(value, dict) else True, "status": result.get("status"), "text": text or json.dumps(result.get("error"))}
        return list(requests.values())


def _steer_interventions(session: GooseAcpSession, module: ControlModule, stop: threading.Event) -> None:
    """goose's native intervention channel: queue each pending intervention into the active run."""
    while not stop.is_set():
        for item in module.pending_interventions("root"):
            try:
                session.steer(f"[control {item['kind']}] {item['text']}")
            except Exception:  # noqa: BLE001 - no active run yet, or goose refused; try again shortly
                break
            module.deliver_intervention(item["interventionId"], "goose_acp_steer")
        stop.wait(0.02)


def _drive_acp(adapter: GooseRuntimeAdapter, gateway_url: str, task: str, module: ControlModule | None = None) -> dict[str, Any]:
    session = GooseAcpSession(adapter.goose_bin, environment=adapter.environment, cwd=adapter.run_dir, transcript_path=adapter.run_dir / "acp_transcript.jsonl")
    stop_steering = threading.Event()
    try:
        session.initialize()
        session.new_session(adapter.run_dir, [{"headers": [], "name": ACP_GATEWAY_NAME, "type": "http", "url": gateway_url}])
        if module is not None:
            threading.Thread(target=_steer_interventions, args=(session, module, stop_steering), daemon=True).start()
        stop = session.prompt(task)
    finally:
        stop_steering.set()
        stderr = session.close()
    (adapter.run_dir / "goose_stderr.txt").write_text(stderr, encoding="utf-8")
    calls = [
        {
            "arguments": call.get("rawInput"),
            "id": call["id"],
            "name": call.get("title"),
            "response": {"isError": call.get("status") == "failed", "status": call.get("status"), "text": json.dumps(call.get("content") or call.get("rawOutput"))},
        }
        for call in session.tool_calls()
    ]
    return {"calls": calls, "exitCode": 0 if stop.get("stopReason") == "end_turn" else 1, "native": {"stopReason": stop.get("stopReason"), "updates": session.updates}}


def _advertised_tools(model_io: Path) -> list[str]:
    """Every tool name the runtime offered the model, across all recorded requests."""
    if not model_io.exists():
        return []
    names: set[str] = set()
    for line in model_io.read_text(encoding="utf-8").splitlines():
        request = json.loads(line).get("request") or {}
        names.update(str((tool.get("function") or {}).get("name")) for tool in request.get("tools") or ())
    return sorted(names)


def _approve_escalations(module: ControlModule, stop: threading.Event, decision: str) -> None:
    while not stop.is_set():
        for escalation_id, item in list(module.state.escalations.items()):
            if item["status"] == "open":
                try:
                    module.resolve_escalation(escalation_id, {"by": "test-principal", "decision": decision})
                except Exception:  # noqa: BLE001 - it may have been resolved meanwhile
                    pass
        stop.wait(0.05)


def run_goose_controlled(
    *,
    goose_bin: str | Path,
    run_dir: str | Path,
    environment: Any,
    engines: Sequence[Mapping[str, Any]],
    plan: Sequence[Mapping[str, Any]],
    task: str,
    tier: str = "hooks",
    require_shim: bool | None = None,
    builtins: Iterable[str] = (),
    principal: str = "external",
    wait_ms: int = 0,
    hook_timeout_s: int = 30,
    max_turns: int = 6,
    hook_python: str | None = None,
    stop_control_before_run: bool = False,
    answer_escalations: str | None = None,
    drive: str = "run",
    extra_registry: Mapping[str, Mapping[str, Any]] | None = None,
    goose_version: str = "1.53.0",
    goose_commit: str | None = None,
    extra_env: Mapping[str, str] | None = None,
    controller: Any = None,
    triggers: Mapping[str, Any] | None = None,
    intervention_channel: str | None = None,
) -> dict[str, Any]:
    """Stand up control module, gateway and proxy on loopback; run goose once; audit it."""
    if drive not in DRIVES:
        raise ValueError(f"drive must be one of {DRIVES}")
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=False)
    module = ControlModule(run_dir / "ledger.jsonl", controller=controller)
    shim = tier in ("hooks", "fork") if require_shim is None else require_shim
    shim_hash = _sha256_file(Path(goose_bin)) if tier == "fork" else hashlib.sha256(HOOK_SCRIPT.read_bytes()).hexdigest()
    runtime = {"commit": goose_commit or f"release-v{goose_version}", "id": "goose", "shimHash": shim_hash, "tier": tier, "version": goose_version}
    spec = run_spec(
        "goose-run", environment, engines, max_actions=12, shim=shim, principal=principal, runtime=runtime, contract={"task": task},
        controller=getattr(controller, "controller_id", "none") if controller else "none", triggers=triggers, intervention_channel=intervention_channel,
    )
    # Non-gateway tools a run admits by name, e.g. {"delegate": {"effectClass": "delegation"}}.
    spec["registry"]["tools"].update({name: dict(entry) for name, entry in (extra_registry or {}).items()})
    opened = module.open_run(spec)
    tokens = new_tokens()
    control_server, control_url = serve_control(module, tokens)
    gateway = ToolGateway(environment, module, run_id=opened["runId"], truth_path=run_dir / "truth.jsonl", io_path=run_dir / "gateway_io.jsonl")
    gateway_server, gateway_url = serve_gateway_http(gateway)
    proxy = ModelProxy(mode="scripted", model_id="scripted-actor", record_path=run_dir / "model_io.jsonl", responder=PlannedResponder(plan), control=module)
    proxy_server, proxy_url = serve_proxy_http(proxy)
    egress_server, egress_url = serve_egress_sink(run_dir / "egress.jsonl")
    adapter = GooseRuntimeAdapter(goose_bin, run_dir, tier=tier, hook_python=hook_python)
    stop = threading.Event()
    watcher = threading.Thread(target=_approve_escalations, args=(module, stop, answer_escalations), daemon=True) if answer_escalations else None
    started = time.perf_counter()
    try:
        receipt = adapter.prepare(
            {
                "builtins": list(builtins),
                "extraEnv": dict(extra_env or {}),
                "contractHash": opened["contractHash"],
                "controlUrl": control_url,
                "egressUrl": egress_url,
                "gatewayExtension": ACP_GATEWAY_NAME if drive == "acp" else None,
                "gatewayUrl": gateway_url,
                "hookPython": hook_python or sys.executable,
                "hookTimeoutS": hook_timeout_s,
                "maxTurns": max_turns,
                "modelId": "scripted-actor",
                "proxyUrl": proxy_url,
                "registryHash": opened["registryHash"],
                "registryTools": list(environment.registry()["tools"]),
                "runId": opened["runId"],
                "runtime": spec["runtime"],
                "shimToken": tokens["shim"],
                "waitMs": wait_ms,
            }
        )
        if stop_control_before_run:
            control_server.shutdown()
            control_server.server_close()
        if watcher:
            watcher.start()
        if drive == "acp":
            # Over ACP the native channel is goose's steer; `goose run` has none, so it keeps the trailer.
            result = _drive_acp(adapter, gateway_url, task, module if intervention_channel == "native" else None)
        else:
            result = adapter.run_task(task)
    finally:
        stop.set()
        closed = module.close({"runtime": "goose", "tier": tier})
        for server in (gateway_server, proxy_server, egress_server) + (() if stop_control_before_run else (control_server,)):
            server.shutdown()
            server.server_close()
    records = parse_receipts(run_dir / "ledger.jsonl")
    calls = result["calls"] if drive == "acp" else GooseRuntimeAdapter.tool_calls(result["native"])
    proposed_ids = {
        r["payload"]["proposal"]["provenance"].get("nativeCallId")
        for r in records
        if r["kind"] == "action_proposed" and r["payload"]["proposal"]["provenance"]["attestation"] == "shim"
    }
    report = {
        "calls": calls,
        "coverage": {"missing": [c["id"] for c in calls if c["id"] not in proposed_ids], "requests": len(calls)},
        "advertisedTools": _advertised_tools(run_dir / "model_io.jsonl"),
        "decisions": [
            {
                "agentId": r["payload"]["agentId"],
                "path": records[r["payload"]["proposalIndex"]]["payload"]["path"],
                "reasonCodes": r["payload"]["reasonCodes"],
                "surface": records[r["payload"]["proposalIndex"]]["payload"]["proposal"]["provenance"]["surface"],
                "toolId": r["payload"]["toolId"],
                "verdict": r["payload"]["verdict"],
            }
            for r in records
            if r["kind"] == "control_decision"
        ],
        "truth": environment.truth(),
        "view": environment.view(),
        "drive": drive,
        "egressAttempts": egress_attempts(run_dir / "egress.jsonl"),
        "exitCode": result["exitCode"],
        "gatewayCalls": len((run_dir / "gateway_io.jsonl").read_text(encoding="utf-8").splitlines()) if (run_dir / "gateway_io.jsonl").exists() else 0,
        "kinds": [r["kind"] for r in records],
        "ledger": verify_receipt_file(run_dir / "ledger.jsonl"),
        "receipt": receipt,
        "root": closed["root"],
        "seconds": round(time.perf_counter() - started, 1),
    }
    (run_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
