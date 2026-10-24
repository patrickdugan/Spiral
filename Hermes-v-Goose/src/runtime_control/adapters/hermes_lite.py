"""Hermes Lite runtime adapter (design section 6.2).

Hermes Lite is driven headless (``python -m agent.control_run``) from a checkout
of its ``control-shim`` branch, which adds:

* ``agent/control_shim.py``: proposes every tool call to the control module
  from the agent loop, before Hermes's own handling, and refuses anything but
  ``allow``;
* a backstop in ``ToolRegistry.dispatch`` that runs a handler only for the call
  the loop authorized, and proposes any other dispatch as surface ``sidecar``;
* ``tools/control_gateway_tools.py``: the gateway's tools as Hermes tools.

Tiers:

* ``gateway_only``: no shim; the gateway is the only enforcement point.
* ``shim``: the shim is on and required (``HERMES_CONTROL_REQUIRED=1``). The
  runtime record names tier ``fork``, since the shim is a source patch.

Every run is isolated: ``HERMES_HOME`` is a fresh directory under the run, the
child gets no inherited API keys or Hermes settings, the model is reached only
through the proxy, and non-loopback egress goes to the egress sink, which
refuses it and records the attempt.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from runtime_control.adapters.goose import _advertised_tools, _approve_escalations
from runtime_control.egress import egress_attempts, egress_env, serve_egress_sink
from runtime_control.gateway import ToolGateway, serve_gateway_http
from runtime_control.ledger import parse_receipts, verify_receipt_file
from runtime_control.module import ControlModule
from runtime_control.proxy import ModelProxy, PlannedResponder, serve_proxy_http
from runtime_control.runs import run_spec
from runtime_control.server import new_tokens, serve_control


TIERS = ("gateway_only", "shim")
SHIM_CONFIG_SCHEMA = "control.hermes_shim_config.v1"
# The files that make up the shim; their bytes are the runtime's shimHash.
SHIM_FILES = ("src/agent/control_shim.py", "src/tools/control_gateway_tools.py", "src/tools/registry.py", "src/hermes_agent.py", "src/agent/control_run.py")
DEFAULT_ROOTS = (Path.home() / "Documents" / "Codex" / "hermes-lite-control-shim",)
# Runtime arms (design 8.1): R0 is Hermes Lite main with only the gateway bridge, R1 the modified
# branch with the shim. Both run on R1's interpreter unless HERMES_LITE_PYTHON says otherwise.
ARM_ROOTS = {
    "R0": Path(os.environ.get("HERMES_LITE_R0_ROOT") or Path.home() / "Documents" / "Codex" / "hermes-lite-r0"),
    "R1": Path(os.environ.get("HERMES_LITE_ROOT") or DEFAULT_ROOTS[0]),
}
TEST_API_KEY = "sk-local-test-not-a-secret"
# litellm routes an ``openai/`` model to OPENAI_BASE_URL, i.e. the proxy.
MODEL = "openai/scripted-actor"
# Inherited variables that would point Hermes at the user's own setup.
DROPPED_PREFIXES = ("HERMES_", "OPENAI_", "ANTHROPIC_", "OPENROUTER_", "LITELLM_", "HONCHO_", "NOUS_")


def find_hermes_lite() -> tuple[Path, Path] | None:
    """(checkout root, python) for a control-shim checkout, from HERMES_LITE_ROOT or the default."""
    candidates = [Path(os.environ["HERMES_LITE_ROOT"])] if os.environ.get("HERMES_LITE_ROOT") else list(DEFAULT_ROOTS)
    for root in candidates:
        python = Path(os.environ.get("HERMES_LITE_PYTHON") or root / ".venv" / "Scripts" / "python.exe")
        if not python.is_file():
            python = root / ".venv" / "bin" / "python"
        if (root / "src" / "agent" / "control_shim.py").is_file() and python.is_file():
            return root, python
    return None


def find_hermes_arm(arm: str) -> tuple[Path, Path] | None:
    """(checkout root, python) for runtime arm R0 or R1, or None when it is not on this machine."""
    found = find_hermes_lite()
    root = ARM_ROOTS[arm]
    if found is None or not (root / "src" / "tools" / "control_gateway_tools.py").is_file():
        return None
    return root, found[1]


def shim_hash(root: Path) -> str:
    """Hash of the files that put the runtime under control; a file the arm lacks hashes as absent."""
    digest = hashlib.sha256()
    for name in SHIM_FILES:
        path = root / name
        content = path.read_bytes().replace(b"\r\n", b"\n") if path.is_file() else b"<absent>"
        digest.update(name.encode("utf-8") + b"\0" + content + b"\0")
    return digest.hexdigest()


def _git_head(root: Path) -> str:
    try:
        out = subprocess.run(["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return out.stdout.strip() or "unknown"


def child_environment(base: Mapping[str, str], extra: Mapping[str, str], *, egress_url: str | None) -> dict[str, str]:
    env = {key: value for key, value in base.items() if not key.upper().startswith(DROPPED_PREFIXES) and not key.upper().endswith("_API_KEY")}
    if egress_url:
        env.update(egress_env(egress_url))
    env.update({str(k): str(v) for k, v in extra.items()})
    return env


def tool_calls(output: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Pair every tool call the model made with the tool message Hermes returned for it."""
    calls: dict[str, dict[str, Any]] = {}
    for message in (output or {}).get("messages", ()):
        for call in message.get("tool_calls") or ():
            calls[call["id"]] = {"arguments": call.get("arguments"), "id": call["id"], "name": call.get("name"), "response": None}
        if message.get("role") == "tool" and message.get("tool_call_id") in calls:
            text = str(message.get("content") or "")
            try:
                body = json.loads(text)
            except json.JSONDecodeError:
                body = None
            is_error = isinstance(body, dict) and (bool(body.get("error")) or body.get("outcome") in ("block", "escalate", "invalid"))
            calls[message["tool_call_id"]]["response"] = {"isError": is_error, "text": text}
    return list(calls.values())


def run_hermes_controlled(
    *,
    run_dir: str | Path,
    environment: Any,
    engines: Sequence[Mapping[str, Any]],
    plan: Sequence[Mapping[str, Any]],
    task: str,
    tier: str = "shim",
    hermes_root: str | Path | None = None,
    hermes_python: str | Path | None = None,
    require_shim: bool | None = None,
    principal: str = "external",
    wait_ms: int = 0,
    toolsets: Iterable[str] = ("control-gateway",),
    gateway_prefix: str = "",
    extra_registry: Mapping[str, Mapping[str, Any]] | None = None,
    max_iterations: int = 6,
    stop_control_before_run: bool = False,
    answer_escalations: str | None = None,
    extra_env: Mapping[str, str] | None = None,
    timeout_s: int = 300,
    controller: Any = None,
    triggers: Mapping[str, Any] | None = None,
    intervention_channel: str | None = None,
    replay_path: str | Path | None = None,
    replay_normalizers: Sequence[tuple[str, str]] = (),
) -> dict[str, Any]:
    """Stand up control module, gateway and proxy on loopback; run Hermes Lite once; audit it.

    With ``replay_path`` the proxy answers from a recorded ``model_io.jsonl`` instead of ``plan``
    (replay level R2): a request that differs from every recorded one gets a replay miss.
    """
    if tier not in TIERS:
        raise ValueError(f"tier must be one of {TIERS}")
    if hermes_root is None or hermes_python is None:
        found = find_hermes_lite()
        if found is None:
            raise RuntimeError("no Hermes Lite control-shim checkout; set HERMES_LITE_ROOT")
        hermes_root, hermes_python = hermes_root or found[0], hermes_python or found[1]
    root, python = Path(hermes_root), Path(hermes_python)
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=False)
    module = ControlModule(run_dir / "ledger.jsonl", controller=controller)
    shim = tier == "shim" if require_shim is None else require_shim
    has_shim = (root / "src" / "agent" / "control_shim.py").is_file()
    if tier == "shim" and not has_shim:
        raise ValueError(f"{root} has no control shim; run it in tier gateway_only")
    runtime = {"commit": _git_head(root), "id": "hermes-lite", "shimHash": shim_hash(root), "tier": "fork" if tier == "shim" else "gateway_only", "version": "control-shim" if has_shim else "main"}
    spec = run_spec(
        "hermes-run", environment, engines, max_actions=12, shim=shim, principal=principal, runtime=runtime, contract={"task": task},
        controller=getattr(controller, "controller_id", "none") if controller else "none", triggers=triggers, intervention_channel=intervention_channel,
    )
    spec["registry"]["tools"].update({name: dict(entry) for name, entry in (extra_registry or {}).items()})
    opened = module.open_run(spec)
    tokens = new_tokens()
    control_server, control_url = serve_control(module, tokens)
    gateway = ToolGateway(environment, module, run_id=opened["runId"], truth_path=run_dir / "truth.jsonl", io_path=run_dir / "gateway_io.jsonl")
    gateway_server, gateway_url = serve_gateway_http(gateway)
    if replay_path is not None:
        proxy = ModelProxy(mode="replay", model_id="scripted-actor", record_path=run_dir / "model_io.jsonl", replay_path=replay_path, control=module, replay_normalizers=replay_normalizers)
    else:
        proxy = ModelProxy(mode="scripted", model_id="scripted-actor", record_path=run_dir / "model_io.jsonl", responder=PlannedResponder(plan), control=module)
    proxy_server, proxy_url = serve_proxy_http(proxy)
    egress_server, egress_url = serve_egress_sink(run_dir / "egress.jsonl")
    home = run_dir / "hermes-home"
    home.mkdir()
    # Hermes looks a model's context length up here before asking a remote API;
    # seed it with the ceiling the proxy enforces (JSON is valid YAML).
    base_url = proxy_url + "/v1"
    (home / "context_length_cache.yaml").write_text(json.dumps({"context_lengths": {f"{MODEL}@{base_url}": proxy.ceiling_tokens}}), encoding="utf-8")
    extra = {
        "CONTEXT_COMPRESSION_ENABLED": "false",
        "HERMES_CONTROL_AGENT_ID": "root",
        "HERMES_CONTROL_GATEWAY_PREFIX": gateway_prefix,
        "HERMES_CONTROL_GATEWAY_URL": gateway_url,
        "HERMES_HOME": str(home),
        "HERMES_RUNTIME_MODE": "standard",
        # Nothing off the machine: no tokenizer download, no remote cost map.
        "HF_HUB_OFFLINE": "1",
        "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        "TRANSFORMERS_OFFLINE": "1",
        "OPENAI_API_KEY": TEST_API_KEY,
        "OPENAI_BASE_URL": base_url,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONPATH": str(root / "src"),
    }
    receipt: dict[str, Any] = {"egress": "blocked_except_loopback", "shimHash": runtime["shimHash"], "tier": tier}
    if tier == "shim":
        config = {
            "schema": SHIM_CONFIG_SCHEMA,
            "agentId": "root",
            "contractHash": opened["contractHash"],
            "controlUrl": control_url,
            "gatewayPrefix": gateway_prefix,
            "gatewayUrl": gateway_url,
            "registryHash": opened["registryHash"],
            "registryTools": sorted(environment.registry()["tools"]),
            "runId": opened["runId"],
            "runtime": runtime,
            "shimToken": tokens["shim"],
            "timeoutS": 30,
            "waitMs": wait_ms,
        }
        config_path = run_dir / "shim-config.json"
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        extra |= {"HERMES_CONTROL_CONFIG": str(config_path), "HERMES_CONTROL_REQUIRED": "1"}
    if intervention_channel != "native":
        # Interventions then arrive on the gateway trailer only.
        extra["HERMES_CONTROL_INTERVENTIONS"] = "off"
    extra |= dict(extra_env or {})
    env = child_environment(os.environ, extra, egress_url=egress_url)
    output_path = run_dir / "hermes_output.json"
    command = [str(python), "-m", "agent.control_run", "--task", task, "--output", str(output_path), "--model", MODEL, "--max-iterations", str(max_iterations), "--toolsets", ",".join(toolsets)]
    stop = threading.Event()
    watcher = threading.Thread(target=_approve_escalations, args=(module, stop, answer_escalations), daemon=True) if answer_escalations else None
    started = time.perf_counter()
    try:
        if stop_control_before_run:
            control_server.shutdown()
            control_server.server_close()
        if watcher:
            watcher.start()
        completed = subprocess.run(command, env=env, cwd=run_dir, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout_s)
    finally:
        stop.set()
        closed = module.close({"runtime": "hermes-lite", "tier": tier})
        for server in (gateway_server, proxy_server, egress_server) + (() if stop_control_before_run else (control_server,)):
            server.shutdown()
            server.server_close()
    (run_dir / "hermes_stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (run_dir / "hermes_stderr.txt").write_text(completed.stderr, encoding="utf-8")
    output = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else {}
    src = str((root / "src").resolve()).lower()
    sources = {name: path for name, path in (output.get("sources") or {}).items() if path}
    records = parse_receipts(run_dir / "ledger.jsonl")
    calls = tool_calls(output)
    proposed_ids = {
        r["payload"]["proposal"]["provenance"].get("nativeCallId")
        for r in records
        if r["kind"] == "action_proposed" and r["payload"]["proposal"]["provenance"]["attestation"] == "shim"
    }
    report = {
        "advertisedTools": _advertised_tools(run_dir / "model_io.jsonl"),
        "calls": calls,
        "coverage": {"missing": [c["id"] for c in calls if c["id"] not in proposed_ids], "requests": len(calls)},
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
        "egressAttempts": egress_attempts(run_dir / "egress.jsonl"),
        "exitCode": completed.returncode,
        "gatewayCalls": len((run_dir / "gateway_io.jsonl").read_text(encoding="utf-8").splitlines()) if (run_dir / "gateway_io.jsonl").exists() else 0,
        "kinds": [r["kind"] for r in records],
        "ledger": verify_receipt_file(run_dir / "ledger.jsonl"),
        "output": output,
        "receipt": receipt | {"sources": sources, "sourcesFromArm": bool(sources) and all(str(Path(path).resolve()).lower().startswith(src) for path in sources.values())},
        "root": closed["root"],
        "seconds": round(time.perf_counter() - started, 1),
        "truth": environment.truth(),
        "view": environment.view(),
    }
    (run_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
