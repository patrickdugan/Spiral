"""Wire types for the runtime control plane: canonical hashing and strict validators.

Every object that crosses a process boundary is checked here with exact keys,
following the repository's hand-written validator convention. The JSON Schema
in ``schemas/control_harness/runtime-control-wire.v1.schema.json`` documents the
same shapes; ``tests/test_runtime_control_wire.py`` keeps the two in step.
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterable, Mapping

from runtime_control.ledger import FloatInPayload, canonical_json_bytes, reject_floats


PROPOSAL_SCHEMA = "control.tool_call_proposal.v1"
PROVENANCE_SCHEMA = "control.provenance.v1"
DECISION_SCHEMA = "control.decision.v1"
OUTCOME_SCHEMA = "control.tool_call_outcome.v1"
RUN_START_SCHEMA = "control.run_start.v1"
RUN_END_SCHEMA = "control.run_end.v1"
LEASE_SCHEMA = "control.lease.v1"

VERDICTS = ("allow", "deny", "escalate")
EFFECT_CLASSES = ("none", "read", "local_write", "state_change", "delegation", "authority")
CONSEQUENTIAL = frozenset({"local_write", "state_change", "delegation", "authority"})
SURFACES = (
    "agent_loop",
    "code_mode",
    "subagent",
    "lean_phase",
    "sidecar",
    "app_call",
    "final_output",
    "skill_load",
    "gateway_only",
)
ATTESTATIONS = ("shim", "gateway_only")
RUNTIME_TIERS = ("gateway_only", "hooks", "fork", "harness")
RUN_STATUSES = ("ACTIVE", "CLOSED", "HELD", "CLARIFY", "INCIDENT", "EXPIRED", "EXHAUSTED")
OUTCOME_STATUSES = ("ok", "error", "denied", "timeout", "cancelled")
EVIDENCE_TRUST = ("host_verified", "provider_reported", "untrusted_text")

ACTOR_FIELDS = ("agentId", "lineage", "role")
RUNTIME_FIELDS = ("id", "version", "commit", "shimHash", "tier")
TOOL_FIELDS = ("id", "nativeName", "registryHash")
PROVENANCE_FIELDS = (
    "schema",
    "surface",
    "attestation",
    "nativeCallId",
    "modelTurn",
    "skill",
    "contextTaint",
    "argRefs",
    "claims",
)
PROPOSAL_FIELDS = (
    "schema",
    "runId",
    "seq",
    "actor",
    "runtime",
    "tool",
    "args",
    "fingerprint",
    "contractHash",
    "provenance",
    "proposedAt",
)
OUTCOME_FIELDS = (
    "schema",
    "fingerprint",
    "decisionId",
    "status",
    "resultSha256",
    "resultBytes",
    "resultTokens",
    "evidenceIds",
    "effectId",
    "durationMs",
    "view",
)


class WireError(ValueError):
    """Raised when an object crossing the control boundary is malformed."""


def canonical_bytes(value: Any) -> bytes:
    reject_floats(value)
    return canonical_json_bytes(value)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def call_fingerprint(run_id: str, agent_id: str, tool_id: str, args: Mapping[str, Any]) -> str:
    """Identify one tool call independently of which runtime or surface made it."""
    return sha256_hex({"agentId": agent_id, "args": dict(args), "runId": run_id, "toolId": tool_id})


def _no_floats(value: Any) -> None:
    try:
        reject_floats(value)
    except FloatInPayload as exc:
        raise WireError(str(exc)) from exc


def _closed(value: Any, allowed: Iterable[str], required: Iterable[str], name: str) -> None:
    if not isinstance(value, Mapping):
        raise WireError(f"{name} must be an object")
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise WireError(f"{name} has unsupported fields: {unknown}")
    missing = sorted(set(required) - set(value))
    if missing:
        raise WireError(f"{name} is missing fields: {missing}")


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WireError(f"{name} must be a non-empty string")
    return value


def _count(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise WireError(f"{name} must be a non-negative integer")
    return value


def validate_actor(value: Any) -> None:
    _closed(value, ACTOR_FIELDS, ("agentId", "lineage"), "actor")
    _text(value["agentId"], "actor.agentId")
    lineage = value["lineage"]
    if not isinstance(lineage, list) or not all(isinstance(item, str) for item in lineage):
        raise WireError("actor.lineage must be a list of strings")
    if "role" in value and value["role"] is not None:
        _text(value["role"], "actor.role")


def validate_runtime(value: Any) -> None:
    _closed(value, RUNTIME_FIELDS, RUNTIME_FIELDS, "runtime")
    for key in ("id", "version", "commit", "shimHash"):
        _text(value[key], f"runtime.{key}")
    if value["tier"] not in RUNTIME_TIERS:
        raise WireError(f"runtime.tier must be one of {RUNTIME_TIERS}")


def validate_provenance(value: Any) -> None:
    _closed(value, PROVENANCE_FIELDS, ("schema", "surface", "attestation", "contextTaint"), "provenance")
    if value["schema"] != PROVENANCE_SCHEMA:
        raise WireError(f"provenance.schema must be {PROVENANCE_SCHEMA}")
    if value["surface"] not in SURFACES:
        raise WireError(f"provenance.surface must be one of {SURFACES}")
    if value["attestation"] not in ATTESTATIONS:
        raise WireError(f"provenance.attestation must be one of {ATTESTATIONS}")
    taint = value["contextTaint"]
    if not isinstance(taint, list):
        raise WireError("provenance.contextTaint must be a list")
    for item in taint:
        _closed(item, ("evidenceId", "trust"), ("evidenceId", "trust"), "contextTaint item")
        if item["trust"] not in EVIDENCE_TRUST:
            raise WireError(f"contextTaint.trust must be one of {EVIDENCE_TRUST}")
    turn = value.get("modelTurn")
    if turn is not None:
        _closed(
            turn,
            ("turnId", "requestSha256", "responseSha256", "modelHash", "adapterHash"),
            ("turnId", "requestSha256", "responseSha256", "modelHash"),
            "provenance.modelTurn",
        )
    skill = value.get("skill")
    if skill is not None:
        _closed(skill, ("id", "sha256", "phase"), ("id", "sha256"), "provenance.skill")


def validate_proposal(value: Any) -> None:
    """Check shape only. Whether the fingerprint matches is a decision, recorded as one."""
    _closed(value, PROPOSAL_FIELDS, PROPOSAL_FIELDS, "proposal")
    if value["schema"] != PROPOSAL_SCHEMA:
        raise WireError(f"proposal.schema must be {PROPOSAL_SCHEMA}")
    _text(value["runId"], "proposal.runId")
    _count(value["seq"], "proposal.seq")
    validate_actor(value["actor"])
    validate_runtime(value["runtime"])
    _closed(value["tool"], TOOL_FIELDS, TOOL_FIELDS, "proposal.tool")
    for key in TOOL_FIELDS:
        _text(value["tool"][key], f"proposal.tool.{key}")
    if not isinstance(value["args"], Mapping):
        raise WireError("proposal.args must be an object")
    for key in ("fingerprint", "contractHash", "proposedAt"):
        _text(value[key], f"proposal.{key}")
    validate_provenance(value["provenance"])
    _no_floats(value)


def validate_outcome(value: Any) -> None:
    _closed(
        value,
        OUTCOME_FIELDS,
        ("schema", "fingerprint", "status", "resultSha256", "resultBytes", "evidenceIds", "durationMs"),
        "outcome",
    )
    if value["schema"] != OUTCOME_SCHEMA:
        raise WireError(f"outcome.schema must be {OUTCOME_SCHEMA}")
    if value["status"] not in OUTCOME_STATUSES:
        raise WireError(f"outcome.status must be one of {OUTCOME_STATUSES}")
    _text(value["fingerprint"], "outcome.fingerprint")
    _count(value["resultBytes"], "outcome.resultBytes")
    _count(value["durationMs"], "outcome.durationMs")
    if not isinstance(value["evidenceIds"], list):
        raise WireError("outcome.evidenceIds must be a list")
    if "view" in value and not isinstance(value["view"], Mapping):
        raise WireError("outcome.view must be an object")
    _no_floats(value)


def validate_registry(value: Any) -> None:
    """A tool registry maps tool ids to an effect class and controller-visible fields."""
    _closed(value, ("schema", "tools"), ("schema", "tools"), "registry")
    if value["schema"] != "control.tool_registry.v1":
        raise WireError("registry.schema must be control.tool_registry.v1")
    tools = value["tools"]
    if not isinstance(tools, Mapping) or not tools:
        raise WireError("registry.tools must be a non-empty object")
    for tool_id, entry in tools.items():
        _closed(entry, ("effectClass", "controllerVisible", "controllerHidden"), ("effectClass",), f"registry.{tool_id}")
        if entry["effectClass"] not in EFFECT_CLASSES:
            raise WireError(f"registry.{tool_id}.effectClass must be one of {EFFECT_CLASSES}")
        visible = entry.get("controllerVisible", [])
        if not isinstance(visible, list) or not all(isinstance(item, str) for item in visible):
            raise WireError(f"registry.{tool_id}.controllerVisible must be a list of field names")
        # Dotted paths inside visible fields that stay hashed, such as an actor's own free text.
        hidden = entry.get("controllerHidden", [])
        if not isinstance(hidden, list) or not all(isinstance(item, str) and item.split(".")[0] in visible for item in hidden):
            raise WireError(f"registry.{tool_id}.controllerHidden must be a list of dotted paths inside controllerVisible fields")
