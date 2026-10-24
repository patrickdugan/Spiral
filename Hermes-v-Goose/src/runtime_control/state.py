"""Control state as a fold over the v3 ledger.

The control module never keeps state that is not in its ledger. ``apply`` is the
only way state changes, so folding a ledger reproduces exactly what the module
knew when it wrote each record, and every ``control_decision`` carries the hash
of the state it was decided against.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from runtime_control.wire import CONSEQUENTIAL, sha256_hex


RECENT_ACTIONS = 16


@dataclass
class ControlState:
    run_id: str | None = None
    status: str = "NEW"
    contract_hash: str | None = None
    registry: dict[str, Any] = field(default_factory=dict)
    registry_hash: str | None = None
    engines: list[dict[str, Any]] = field(default_factory=list)
    limits: dict[str, Any] = field(default_factory=dict)
    profile: dict[str, Any] = field(default_factory=dict)
    runtime: dict[str, Any] = field(default_factory=dict)
    actors: dict[str, dict[str, Any]] = field(default_factory=dict)
    env_view: dict[str, Any] = field(default_factory=dict)
    leases: dict[str, dict[str, Any]] = field(default_factory=dict)
    escalations: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Current skill phase per actor, from phase_entered records (harness-owned, like Hermes Lite's lean runtime).
    phases: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Controller interventions by id: issued (pending), then delivered on a channel.
    interventions: dict[str, dict[str, Any]] = field(default_factory=dict)
    reserved: int = 0
    spent: int = 0
    counts: dict[str, int] = field(
        default_factory=lambda: dict.fromkeys(
            (
                "proposed",
                "allowed",
                "denied",
                "escalated",
                "leases_issued",
                "leases_consumed",
                "leases_expired",
                "effects",
                "tool_results",
                "bypasses",
                "controller_turns",
                "controller_holds",
                "interventions",
                "model_turns",
                "context_packets",
                "context_overflows",
                "compactions",
                "skills_loaded",
            ),
            0,
        )
    )
    last_decision: dict[str, Any] | None = None
    recent_actions: list[dict[str, Any]] = field(default_factory=list)
    record_count: int = 0

    def snapshot(self) -> dict[str, Any]:
        snapshot = {
            "actors": self.actors,
            "contract_hash": self.contract_hash,
            "counts": self.counts,
            "engines": self.engines,
            "env_view": self.env_view,
            "escalations": self.escalations,
            "last_decision": self.last_decision,
            "leases": self.leases,
            "limits": self.limits,
            "profile": self.profile,
            "recent_actions": self.recent_actions,
            "record_count": self.record_count,
            "registry_hash": self.registry_hash,
            "reserved": self.reserved,
            "run_id": self.run_id,
            "runtime": self.runtime,
            "spent": self.spent,
            "status": self.status,
        }
        # Only present once a phase was entered, so ledgers written before phases existed keep their hashes.
        if self.phases:
            snapshot["phases"] = self.phases
        if self.interventions:
            snapshot["interventions"] = self.interventions
        return snapshot

    def state_hash(self) -> str:
        return sha256_hex(self.snapshot())

    def effect_class(self, tool_id: str) -> str:
        entry = self.registry.get("tools", {}).get(tool_id)
        # A tool missing from the pinned registry is treated as consequential.
        return entry["effectClass"] if entry else "state_change"

    def active_leases(self, fingerprint: str) -> list[dict[str, Any]]:
        return sorted(
            (
                lease
                for lease in self.leases.values()
                if lease["fingerprint"] == fingerprint and lease["status"] == "active"
            ),
            key=lambda lease: lease["issuedAtIndex"],
        )

    def remaining_actions(self) -> int | None:
        cap = self.limits.get("maxConsequentialActions")
        return None if cap is None else max(int(cap) - self.spent - self.reserved, 0)


def apply(state: ControlState, record: Mapping[str, Any]) -> ControlState:
    """Fold one ledger record into ``state`` in place and return it."""
    kind = record["kind"]
    payload = record["payload"]
    index = record["index"]
    counts = state.counts

    if kind == "run_start":
        state.run_id = payload["runId"]
        state.status = "ACTIVE"
        state.contract_hash = payload["contractHash"]
        state.registry = copy.deepcopy(payload["registry"])
        state.registry_hash = payload["registryHash"]
        state.engines = copy.deepcopy(payload["engines"])
        state.limits = copy.deepcopy(payload.get("limits", {}))
        state.profile = copy.deepcopy(payload.get("profile", {}))
        state.runtime = copy.deepcopy(payload.get("runtime", {}))
        state.env_view = copy.deepcopy(payload.get("view", {}))
        for actor in payload.get("actors", ()):
            state.actors[actor["agentId"]] = {
                "lineage": list(actor.get("lineage", ())),
                "parent": None,
                "role": actor.get("role"),
                "status": "active",
            }
    elif kind == "action_proposed":
        counts["proposed"] += 1
    elif kind == "control_decision":
        verdict = payload["verdict"]
        counts[{"allow": "allowed", "deny": "denied", "escalate": "escalated"}[verdict]] += 1
        state.last_decision = {
            "decisionId": payload["decisionId"],
            "reasonCodes": list(payload["reasonCodes"]),
            "toolId": payload["toolId"],
            "verdict": verdict,
        }
        if payload["effectClass"] in CONSEQUENTIAL:
            state.recent_actions = (
                state.recent_actions
                + [
                    {
                        "agentId": payload["agentId"],
                        "effectClass": payload["effectClass"],
                        "index": index,
                        "reasonCodes": list(payload["reasonCodes"]),
                        "toolId": payload["toolId"],
                        "verdict": verdict,
                    }
                ]
            )[-RECENT_ACTIONS:]
        if payload.get("haltRun"):
            state.status = "HELD"
    elif kind == "lease_issued":
        state.leases[payload["leaseId"]] = {
            "agentId": payload["agentId"],
            "decisionId": payload["decisionId"],
            "expiresAt": payload["expiresAt"],
            "fingerprint": payload["fingerprint"],
            "issuedAtIndex": index,
            "leaseId": payload["leaseId"],
            "resolvesEscalation": payload.get("resolvesEscalation"),
            "status": "active",
            "toolId": payload["toolId"],
        }
        state.reserved += 1
        counts["leases_issued"] += 1
    elif kind == "lease_consumed":
        state.leases[payload["leaseId"]]["status"] = "consumed"
        state.reserved -= 1
        state.spent += 1
        counts["leases_consumed"] += 1
    elif kind == "lease_expired":
        state.leases[payload["leaseId"]]["status"] = "expired"
        state.reserved -= 1
        counts["leases_expired"] += 1
    elif kind == "environment_transition":
        counts["effects"] += 1
        if "view" in payload:
            state.env_view = copy.deepcopy(payload["view"])
    elif kind == "tool_result":
        counts["tool_results"] += 1
        if "view" in payload:
            state.env_view = copy.deepcopy(payload["view"])
    elif kind in ("environment_view", "contract_amended", "grant_issued", "grant_expired"):
        if "view" in payload:
            state.env_view = copy.deepcopy(payload["view"])
    elif kind == "escalation":
        escalation_id = payload["escalationId"]
        if payload["status"] == "open":
            state.escalations[escalation_id] = {
                "agentId": payload["agentId"],
                "fingerprint": payload["fingerprint"],
                "openedAtIndex": index,
                "reasonCodes": list(payload["reasonCodes"]),
                "status": "open",
                "toolId": payload["toolId"],
            } | ({"summary": payload["summary"]} if "summary" in payload else {})
        else:
            state.escalations[escalation_id]["status"] = payload["status"]
    elif kind == "delegation_spawned" and "childAgentId" in payload:
        # v2 records of this kind describe delegated transfers and carry no child agent.
        state.actors[payload["childAgentId"]] = {
            "lineage": list(payload.get("lineage", ())),
            "parent": payload["parentAgentId"],
            "role": payload.get("role"),
            "status": "active",
        }
    elif kind == "delegation_returned" and payload.get("childAgentId") in state.actors:
        state.actors[payload["childAgentId"]]["status"] = "returned"
    elif kind == "bypass_detected":
        counts["bypasses"] += 1
    elif kind == "controller_turn":
        counts["controller_turns"] += 1
        action = payload["output"]["action"]
        counts["controller_holds"] += action == "hold"
        if action == "halt_run":
            state.status = "HELD"
    elif kind == "intervention":
        if payload["status"] == "pending":
            counts["interventions"] += 1
            state.interventions[payload["interventionId"]] = {
                "agentId": payload["agentId"],
                "issuedAtIndex": index,
                "kind": payload["kind"],
                "status": "pending",
                "text": payload["text"],
                "turn": payload["turn"],
            }
        elif payload["interventionId"] in state.interventions:
            state.interventions[payload["interventionId"]] |= {"atIndex": payload["atIndex"], "channel": payload["channel"], "status": payload["status"]}
    elif kind == "model_turn":
        counts["model_turns"] += 1
    elif kind == "context_packet":
        counts["context_packets"] += 1
        counts["context_overflows"] += bool(payload.get("overflow"))
    elif kind == "context_compacted":
        counts["compactions"] += 1
    elif kind == "skill_loaded":
        counts["skills_loaded"] += 1
    elif kind == "phase_entered":
        state.phases[payload["agentId"]] = {"index": index, "phase": payload["phase"], "skillId": payload["skillId"]}
    elif kind == "run_end":
        state.status = "CLOSED"
    # monitor_decision, probe and v2 delegation records do not change control state.
    state.record_count = index + 1
    return state


def fold(records: Iterable[Mapping[str, Any]]) -> ControlState:
    state = ControlState()
    for record in records:
        apply(state, record)
    return state
