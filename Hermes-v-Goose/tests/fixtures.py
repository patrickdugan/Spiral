"""Shared fixtures: a control module over the demo ledger. Standard library only."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from runtime_control.demo import DemoLedgerEnvironment, demo_engine_spec  # noqa: E402
from runtime_control.module import ControlModule  # noqa: E402
from runtime_control.runs import NULL_RUNTIME, run_spec  # noqa: E402
from runtime_control.wire import PROPOSAL_SCHEMA, PROVENANCE_SCHEMA, call_fingerprint  # noqa: E402


PAY_ALICE = {"amount": 10, "to": "alice"}          # allowed by policy and by truth
PAY_ALICE_BIG = {"amount": 60, "to": "alice"}      # over the per-call cap
PAY_CAROL = {"amount": 5, "to": "carol"}           # escalates to the principal
PAY_MALLORY = {"amount": 5, "to": "mallory"}       # refused by policy; unauthorized in truth


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, ms: int) -> None:
        self.now += timedelta(milliseconds=ms)


def open_module(
    path: Path,
    *,
    shim: bool = True,
    controller: str = "none",
    principal: str = "external",
    clock: Any = None,
    lease_ttl_ms: int = 60_000,
    controller_obj: Any = None,
    max_actions: int = 20,
) -> tuple[ControlModule, DemoLedgerEnvironment, dict[str, Any]]:
    environment = DemoLedgerEnvironment()
    module = ControlModule(path, clock=clock or FakeClock(), controller=controller_obj)
    spec = run_spec("run-fixture", environment, [demo_engine_spec()], max_actions=max_actions, shim=shim, controller=controller, principal=principal, lease_ttl_ms=lease_ttl_ms)
    opened = module.open_run(spec)
    return module, environment, opened


def proposal(opened: Mapping[str, Any], args: Mapping[str, Any], *, tool: str = "ledger_pay", agent: str = "root", fingerprint: str | None = None, seq: int = 0) -> dict[str, Any]:
    return {
        "schema": PROPOSAL_SCHEMA,
        "actor": {"agentId": agent, "lineage": ["run-fixture"]},
        "args": dict(args),
        "contractHash": opened["contractHash"],
        "fingerprint": fingerprint or call_fingerprint(opened["runId"], agent, tool, args),
        "proposedAt": "2026-10-08T12:00:00.000+00:00",
        "provenance": {"schema": PROVENANCE_SCHEMA, "attestation": "shim", "contextTaint": [], "surface": "agent_loop"},
        "runId": opened["runId"],
        "runtime": dict(NULL_RUNTIME),
        "seq": seq,
        "tool": {"id": tool, "nativeName": tool, "registryHash": opened["registryHash"]},
    }


def commit_request(opened: Mapping[str, Any], args: Mapping[str, Any], *, tool: str = "ledger_pay", agent: str = "root") -> dict[str, Any]:
    return {"agentId": agent, "args": dict(args), "fingerprint": call_fingerprint(opened["runId"], agent, tool, args), "toolId": tool}


def view_event(environment: DemoLedgerEnvironment, **changes: Any) -> dict[str, Any]:
    """An environment_view payload as if the world changed outside this actor."""
    view = environment.view() | changes
    return {"cause": "external_change", "view": view}


def records(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def kinds(path: Path) -> list[str]:
    return [record["kind"] for record in records(path)]
