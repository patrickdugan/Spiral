"""Skill phase contracts as a policy engine (design phase 6).

Hermes Lite's ultra-lean skills (``hermes.ultra_lean_skill.v1``/``v2``, the
LDT) run as a conveyor of phases, and each phase names the tool profile it may
use: ``search``, ``read``, ``run`` or ``write`` (``conveyor.phases[i].tool_profile``).
This engine enforces that: a call is admitted only when its tool's profile is
in the profile of the phase its actor is in.

The current phase comes from the control state, never from the actor: a shim or
harness writes ``phase_entered`` (``{agentId, skillId, phase}``) as the runtime
moves through the conveyor, as Hermes Lite's lean runtime owns its phase index.
A proposal may also claim a phase in ``provenance.skill``; a claim that differs
from the state is refused.

Config::

    {"contracts": {skill_id: {"sha256": ..., "phases": [{"id": ..., "tool_profile": [...]}, ...]}},
     "toolProfiles": {tool_id: "search" | "read" | "run" | "write"}}

Contracts hold phases already normalized; ``phase_contract_spec`` builds the
config from contract files with Hermes Lite's own ``contract_phases``, so the
engine itself needs no Hermes checkout and replays from ``run_start`` alone.
Hermes Lite's contracts map no tool names to profiles, so ``toolProfiles`` is
the experiment's declaration and is pinned in the policy hash. Everything not
declared is refused: an unprofiled tool, an actor with no phase, a skill or
phase the config does not hold.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

from runtime_control.engines import EngineConfigError, register_engine
from runtime_control.wire import sha256_hex


ENGINE_ID = "phase-contract-v1"
PROFILES = ("search", "read", "run", "write")
DEFAULT_HERMES_SRC = Path.home() / "Documents" / "Codex" / "hermes-lite-control-shim" / "src"


def _contract_phases(hermes_src: str | Path | None) -> Any:
    root = Path(hermes_src or os.environ.get("HERMES_LITE_SRC") or (Path(os.environ["HERMES_LITE_ROOT"]) / "src" if os.environ.get("HERMES_LITE_ROOT") else DEFAULT_HERMES_SRC))
    if not (root / "agent" / "lean_contracts.py").is_file():
        raise EngineConfigError(f"Hermes Lite source not found at {root}; set HERMES_LITE_SRC")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from agent.lean_contracts import contract_phases  # Hermes Lite's own normalization

    return contract_phases


def phase_contract_spec(contracts: Iterable[Mapping[str, Any]], tool_profiles: Mapping[str, str], *, hermes_src: str | Path | None = None) -> dict[str, Any]:
    """Engine spec for run_start from ultra-lean contracts, keyed by their ``name``."""
    contract_phases = _contract_phases(hermes_src)
    normalized = {}
    for contract in contracts:
        phases = [{"id": str(p["id"]), "tool_profile": sorted(str(x) for x in p.get("tool_profile") or [])} for p in contract_phases(dict(contract))]
        canonical = json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        normalized[str(contract["name"])] = {"phases": phases, "sha256": hashlib.sha256(canonical).hexdigest()}
    return {"engineId": ENGINE_ID, "config": {"contracts": normalized, "toolProfiles": dict(tool_profiles)}}


class PhaseContractEngine:
    engine_id = ENGINE_ID

    def __init__(self, config: Mapping[str, Any]) -> None:
        contracts, profiles = config.get("contracts"), config.get("toolProfiles")
        if set(config) != {"contracts", "toolProfiles"} or not isinstance(contracts, Mapping) or not isinstance(profiles, Mapping):
            raise EngineConfigError("phase-contract config is {'contracts': {...}, 'toolProfiles': {...}}")
        bad = sorted(tool for tool, profile in profiles.items() if profile not in PROFILES)
        if bad:
            raise EngineConfigError(f"tool profiles must be one of {PROFILES}: {bad}")
        for skill_id, contract in contracts.items():
            phases = contract.get("phases") if isinstance(contract, Mapping) else None
            if not isinstance(phases, list) or not phases or not all(isinstance(p, Mapping) and isinstance(p.get("id"), str) and set(p.get("tool_profile", [])) <= set(PROFILES) for p in phases):
                raise EngineConfigError(f"contract {skill_id} needs phases with ids and tool profiles within {PROFILES}")
        self.config = {"contracts": {k: {"phases": [dict(p) for p in v["phases"]], "sha256": v.get("sha256")} for k, v in contracts.items()}, "toolProfiles": dict(profiles)}
        self.policy_hash = sha256_hex({"config": self.config, "engineId": self.engine_id})

    def evaluate(self, proposal: Mapping[str, Any], state: Any) -> dict[str, Any]:
        tool_id = proposal["tool"]["id"]
        profile = self.config["toolProfiles"].get(tool_id)
        current = state.phases.get(proposal["actor"]["agentId"])
        claim = proposal.get("provenance", {}).get("skill")
        checks = {"tool_profiled": profile is not None, "phase_known": current is not None}

        def refuse(code: str) -> dict[str, Any]:
            return {"verdict": "deny", "reasonCodes": [code], "checks": checks, "native": {"phase": current, "profile": profile}}

        if profile is None:
            return refuse("tool_profile_unknown")
        if current is None:
            return refuse("phase_unknown")
        contract = self.config["contracts"].get(current["skillId"])
        phase = next((p for p in (contract or {}).get("phases", ()) if p["id"] == current["phase"]), None)
        checks["phase_in_contract"] = phase is not None
        if phase is None:
            return refuse("phase_not_in_contract")
        checks["claim_matches_state"] = claim is None or (claim.get("id") == current["skillId"] and claim.get("phase", current["phase"]) == current["phase"])
        if not checks["claim_matches_state"]:
            return refuse("phase_claim_mismatch")
        checks["profile_in_phase"] = profile in phase.get("tool_profile", ())
        if not checks["profile_in_phase"]:
            return refuse("tool_profile_not_in_phase")
        return {"verdict": "allow", "reasonCodes": [], "checks": checks, "native": {"phase": current, "profile": profile}}


register_engine(ENGINE_ID, PhaseContractEngine)
