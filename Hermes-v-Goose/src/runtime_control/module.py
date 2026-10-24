"""The control module: one ledger, one folded state, one decision pipeline per run.

Runtime shims call ``decide`` before a tool runs; the tool gateway calls
``commit`` before an effect happens and needs a lease to get a yes; everyone
reports outcomes and events. Every call appends to the ledger before it
returns, so an allow that is not in the ledger cannot exist.

Decision pipeline (design section 6.1):

1. caller role (checked by the HTTP layer)        6. tool registered
2. fingerprint recomputed                          7. policy engines, by conjunction
3. ``action_proposed`` appended                    8. controller turn (may only reduce)
4. effect class from the pinned registry           9. budget reservation
5. run active, actor known, pins match            10. ``control_decision`` (+ lease)
"""

from __future__ import annotations

import inspect
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from runtime_control.controller import (
    PROMPT_TEMPLATE_SHA256,
    TURN_SCHEMA,
    PacketOverflow,
    build_packet,
    fold_thread,
    render_record,
    trigger_policy,
    triggers_for,
)
from runtime_control.ledger import ReceiptLedger
from runtime_control.errors import ControlError
from runtime_control.engines import (
    build_controller,
    build_engine,
    build_principal,
    validate_control_action,
)
from runtime_control.state import ControlState, apply, fold
from runtime_control.wire import (
    CONSEQUENTIAL,
    DECISION_SCHEMA,
    PROPOSAL_SCHEMA,
    PROVENANCE_SCHEMA,
    RUN_END_SCHEMA,
    RUN_START_SCHEMA,
    WireError,
    call_fingerprint,
    sha256_hex,
    validate_outcome,
    validate_proposal,
    validate_registry,
)


RUN_SPEC_FIELDS = (
    "schema",
    "runId",
    "runContract",
    "registry",
    "engines",
    "runtime",
    "actors",
    "limits",
    "profile",
    "view",
)
PROFILE_FIELDS = ("requireShim", "controller", "principal", "controllerFailure", "triggers", "interventionChannel", "controllerView", "controllerBrief")
INTERVENTION_CHANNELS = ("gateway_trailer", "native")
LIMIT_FIELDS = ("maxConsequentialActions", "leaseTtlMs")
EVENT_KINDS_BY_ROLE = {
    "harness": frozenset(
        {"environment_view", "contract_amended", "grant_issued", "grant_expired", "probe"}
    ),
    "gateway": frozenset({"environment_view"}),
    "shim": frozenset(
        {
            "skill_loaded",
            "phase_entered",
            "context_compacted",
            "context_packet",
            "delegation_spawned",
            "delegation_returned",
        }
    ),
    "proxy": frozenset({"model_turn", "context_packet"}),
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="milliseconds")


class ControlModule:
    def __init__(
        self,
        ledger_path: str | Path,
        *,
        clock: Callable[[], datetime] = utc_now,
        controller: Any = None,
        principal: Any = None,
    ) -> None:
        self._ledger = ReceiptLedger(ledger_path)
        self._state = ControlState()
        self._clock = clock
        self._lock = threading.RLock()
        self._changed = threading.Condition(self._lock)
        self._engines: list[Any] = []
        self._controller_override = controller
        self._principal_override = principal
        self._controller: Any = None
        self._principal: Any = None
        # Escalated proposals, by escalation id. Rebuilt from the ledger on resume.
        self._escalated: dict[str, tuple[dict[str, Any], int, str]] = {}
        # The ledger as records, for the controller thread; the next record to scan for
        # non-blocking triggers; and which actor each decision was for.
        self._records: list[dict[str, Any]] = []
        self._nb_cursor = 0
        self._decision_agents: dict[str, str] = {}

    # ------------------------------------------------------------------ lifecycle

    @classmethod
    def resume(
        cls,
        ledger_path: str | Path,
        *,
        clock: Callable[[], datetime] = utc_now,
        controller: Any = None,
        principal: Any = None,
    ) -> "ControlModule":
        """Rebuild a module from an unclosed ledger after a restart."""
        ledger, records = ReceiptLedger.resume(ledger_path)
        module = cls.__new__(cls)
        module._ledger = ledger
        module._state = fold(records)
        module._clock = clock
        module._lock = threading.RLock()
        module._changed = threading.Condition(module._lock)
        module._controller_override = controller
        module._principal_override = principal
        module._escalated = {}
        module._records = [{"index": r["index"], "kind": r["kind"], "payload": r["payload"]} for r in records]
        module._nb_cursor = len(records)
        decisions = {r["payload"]["decisionId"]: r["payload"] for r in records if r["kind"] == "control_decision"}
        module._decision_agents = {decision_id: payload["agentId"] for decision_id, payload in decisions.items()}
        for escalation_id, item in module._state.escalations.items():
            if item["status"] != "open":
                continue
            opened = records[item["openedAtIndex"]]["payload"]
            decision = decisions[opened["decisionId"]]
            proposal = records[decision["proposalIndex"]]["payload"]["proposal"]
            module._escalated[escalation_id] = (proposal, decision["proposalIndex"], decision["effectClass"])
        module._build_pipeline(records[0]["payload"])
        return module

    def _build_pipeline(self, run_start: Mapping[str, Any]) -> None:
        self._engines = [build_engine(spec) for spec in run_start["engines"]]
        profile = run_start.get("profile", {})
        self._controller = self._controller_override or build_controller(profile.get("controller"))
        self._principal = self._principal_override or build_principal(profile.get("principal"))
        self._triggers = trigger_policy(profile)

    @property
    def state(self) -> ControlState:
        return self._state

    @property
    def ledger_path(self) -> Path:
        return self._ledger.path

    def _append(self, kind: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        record = {"index": self._ledger.record_count, "kind": kind, "payload": dict(payload)}
        self._ledger.append(kind, payload)
        apply(self._state, record)
        self._records.append(record)
        self._changed.notify_all()
        return record

    def open_run(self, spec: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self._state.status != "NEW":
                raise ControlError("run_already_open", "this module already holds a run", 409)
            self._validate_run_spec(spec)
            engines = []
            for item in spec["engines"]:
                engine = build_engine(item)
                engines.append(
                    {
                        "config": dict(item.get("config", {})),
                        "engineId": engine.engine_id,
                        "policyHash": engine.policy_hash,
                    }
                )
            payload = dict(spec) | {
                "contractHash": sha256_hex(spec["runContract"]),
                "engines": engines,
                "registryHash": sha256_hex(spec["registry"]),
                "openedAt": _iso(self._clock()),
            }
            self._append("run_start", payload)
            self._build_pipeline(payload)
            return {
                "contractHash": payload["contractHash"],
                "registryHash": payload["registryHash"],
                "runId": spec["runId"],
            }

    @staticmethod
    def _validate_run_spec(spec: Mapping[str, Any]) -> None:
        if not isinstance(spec, Mapping):
            raise ControlError("malformed_run", "run spec must be an object")
        unknown = sorted(set(spec) - set(RUN_SPEC_FIELDS))
        missing = sorted({"schema", "runId", "runContract", "registry", "engines", "actors"} - set(spec))
        if unknown or missing:
            raise ControlError("malformed_run", f"run spec unknown={unknown} missing={missing}")
        if spec["schema"] != RUN_START_SCHEMA:
            raise ControlError("malformed_run", f"run spec schema must be {RUN_START_SCHEMA}")
        try:
            validate_registry(spec["registry"])
        except WireError as exc:
            raise ControlError("malformed_run", str(exc)) from exc
        if set(spec.get("profile", {})) - set(PROFILE_FIELDS):
            raise ControlError("malformed_run", f"profile fields must be within {PROFILE_FIELDS}")
        try:
            trigger_policy(spec.get("profile", {}))
        except ValueError as exc:
            raise ControlError("malformed_run", str(exc)) from exc
        if spec.get("profile", {}).get("interventionChannel", "gateway_trailer") not in INTERVENTION_CHANNELS:
            raise ControlError("malformed_run", f"interventionChannel must be one of {INTERVENTION_CHANNELS}")
        if set(spec.get("limits", {})) - set(LIMIT_FIELDS):
            raise ControlError("malformed_run", f"limits fields must be within {LIMIT_FIELDS}")
        if not spec["actors"] or not all("agentId" in actor for actor in spec["actors"]):
            raise ControlError("malformed_run", "run spec needs at least one actor with an agentId")

    def close(self, summary: Mapping[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            self._require_open()
            for lease_id, lease in sorted(self._state.leases.items()):
                if lease["status"] == "active":
                    self._append("lease_expired", {"cause": "run_closed", "fingerprint": lease["fingerprint"], "leaseId": lease_id})
            for escalation_id, item in sorted(self._state.escalations.items()):
                if item["status"] == "open":
                    self._append("escalation", {"by": "control_module", "escalationId": escalation_id, "status": "withdrawn"})
                    self._escalated.pop(escalation_id, None)
            payload = {
                "counts": dict(self._state.counts),
                "runId": self._state.run_id,
                "schema": RUN_END_SCHEMA,
                "spent": self._state.spent,
                "stateHash": self._state.state_hash(),
                "statusBefore": self._state.status,
                "summary": dict(summary or {}),
            }
            self._append("run_end", payload)
            return {"records": self._ledger.record_count, "root": self._ledger.last_hash}

    def _require_open(self) -> None:
        if self._state.status in ("NEW", "CLOSED"):
            raise ControlError("run_not_open", "no open run", 409)

    # ------------------------------------------------------------------ decisions

    def decide(self, proposal: Mapping[str, Any], *, wait_ms: int = 0) -> dict[str, Any]:
        """Shim entry point. Returns the decision; may block on an escalation."""
        try:
            validate_proposal(proposal)
        except WireError as exc:
            raise ControlError("malformed_proposal", str(exc)) from exc
        with self._lock:
            self._require_open()
            decision = self._decide(proposal, path="decide")
            self._run_nonblocking()
            if decision["verdict"] == "escalate" and wait_ms > 0:
                decision = self._await_escalation(decision, wait_ms)
                self._run_nonblocking()
            return decision

    def _decide(self, proposal: Mapping[str, Any], *, path: str, force_deny: str | None = None) -> dict[str, Any]:
        state = self._state
        tool_id = proposal["tool"]["id"]
        agent_id = proposal["actor"]["agentId"]
        expected = call_fingerprint(state.run_id or "", agent_id, tool_id, proposal["args"])
        fingerprint_ok = expected == proposal["fingerprint"]
        proposed = self._append(
            "action_proposed",
            {"fingerprintValid": fingerprint_ok, "path": path, "proposal": dict(proposal)},
        )

        effect = state.effect_class(tool_id)
        registered = tool_id in state.registry.get("tools", {})
        checks: dict[str, bool] = {
            "fingerprint": fingerprint_ok,
            "registry_pin": proposal["tool"]["registryHash"] == state.registry_hash,
            "run_active": state.status == "ACTIVE",
            "run_pin": proposal["runId"] == state.run_id,
            "contract_pin": proposal["contractHash"] == state.contract_hash,
            "actor_known": agent_id in state.actors,
            "tool_registered": registered,
        }
        reasons = [code for code, ok in (
            ("fingerprint_mismatch", checks["fingerprint"]),
            ("registry_hash_mismatch", checks["registry_pin"]),
            ("run_not_active", checks["run_active"]),
            ("run_id_mismatch", checks["run_pin"]),
            ("contract_hash_mismatch", checks["contract_pin"]),
            ("unknown_actor", checks["actor_known"]),
            ("tool_not_registered", checks["tool_registered"]),
        ) if not ok]
        if force_deny:
            reasons.append(force_deny)

        verdict = "deny" if reasons else "allow"
        engine_rows: list[dict[str, Any]] = []
        controller_row: dict[str, Any] | None = None
        halt = False
        question: dict[str, Any] | None = None
        if verdict == "allow" and effect in CONSEQUENTIAL:
            verdict, engine_reasons, engine_rows = self._run_engines(proposal, checks)
            reasons.extend(engine_reasons)
            blocking = (verdict == "allow" and self._triggers["admitted"] == "all") or (verdict == "escalate" and self._triggers["onEscalate"])
            if self._controller is not None and blocking:
                kind = "admitted_consequential" if verdict == "allow" else "engine_escalate"
                verdict, controller_reasons, controller_row, halt, question = self._blocking_turn(proposal, proposed["index"], kind, verdict)
                reasons.extend(controller_reasons)
            if verdict == "allow":
                remaining = state.remaining_actions()
                checks["budget"] = remaining is None or remaining > 0
                if not checks["budget"]:
                    verdict = "deny"
                    reasons.append("budget_exhausted")
        return self._record_decision(
            proposal, proposed["index"], verdict, effect, reasons, checks, engine_rows, controller_row, halt, question=question
        )

    def _run_engines(
        self, proposal: Mapping[str, Any], checks: dict[str, bool]
    ) -> tuple[str, list[str], list[dict[str, Any]]]:
        rows: list[dict[str, Any]] = []
        reasons: list[str] = []
        verdicts: list[str] = []
        for engine in self._engines:
            try:
                result = engine.evaluate(proposal, self._state)
                verdict = result["verdict"]
                if verdict not in ("allow", "deny", "escalate"):
                    raise ValueError(f"engine returned verdict {verdict!r}")
            except Exception as exc:  # noqa: BLE001 - any engine failure is a denial
                result = {"verdict": "deny", "reasonCodes": ["engine_error"], "checks": {}, "native": {"error": f"{type(exc).__name__}: {exc}"}}
                verdict = "deny"
            verdicts.append(verdict)
            reasons.extend(result.get("reasonCodes", []))
            checks.update(result.get("checks", {}))
            rows.append(
                {
                    "engineId": engine.engine_id,
                    "policyHash": engine.policy_hash,
                    "verdict": result.get("native"),
                    "outcome": verdict,
                }
            )
        if "deny" in verdicts:
            return "deny", reasons, rows
        if "escalate" in verdicts:
            return "escalate", reasons, rows
        return "allow", reasons, rows

    # ------------------------------------------------------------------ controller thread

    def _call_controller(self, thread: Mapping[str, Any], events: list[str], trigger: Mapping[str, Any], packet: Mapping[str, Any]) -> Any:
        turn = self._controller.turn
        try:
            accepts_packet = "packet" in inspect.signature(turn).parameters
        except (TypeError, ValueError):
            accepts_packet = False
        return turn(thread, events, trigger, packet=packet) if accepts_packet else turn(thread, events, trigger)

    def _turn(self, trigger: Mapping[str, Any]) -> tuple[dict[str, Any], int]:
        """One controller turn over the events since the last one. Appends ``controller_turn``."""
        thread = fold_thread(self._records)
        start, end = thread["lastEventIndex"] + 1, len(self._records) - 1
        view_keys = self._state.profile.get("controllerView")
        events = [line for record in self._records[start:] if (line := render_record(record, self._state.registry, view_keys)) is not None]
        failure = self._state.profile.get("controllerFailure", "hold")
        began = self._clock()
        packet: dict[str, Any] | None = None
        problem = None
        try:
            packet = build_packet(thread, events, trigger)
            action = validate_control_action(self._call_controller(thread, events, trigger, packet))
            problem = None if action is not None else "malformed_action"
        except PacketOverflow:
            action, problem = None, "packet_overflow"
        except Exception:  # noqa: BLE001 - a failed controller turn is treated as unavailable
            action, problem = None, "controller_error"
        if action is None:
            action = {"action": "hold", "reasonCode": "controller_unavailable"} if failure == "hold" else {"action": "pass", "note": "controller_unavailable"}
        payload: dict[str, Any] = {
            "controllerId": getattr(self._controller, "controller_id", "custom"),
            "eventRange": [start, end],
            "latencyMs": int((self._clock() - began).total_seconds() * 1000),
            "output": action,
            "promptTemplateSha256": PROMPT_TEMPLATE_SHA256,
            "schema": TURN_SCHEMA,
            "threadId": thread["threadId"],
            "trigger": dict(trigger),
            "turn": thread["turn"],
        }
        if packet is not None:
            payload |= {"counter": packet["counter"], "inputTokens": packet["inputTokens"], "packetSha256": packet["sha256"]}
        if problem:
            payload["failure"] = problem
        if getattr(self._controller, "model_hash", None):
            payload["modelHash"] = self._controller.model_hash
        self._append("controller_turn", payload)
        if action["action"] == "intervene":
            self._issue_intervention(action, thread["turn"], trigger)
        return action, thread["turn"]

    def _blocking_turn(
        self, proposal: Mapping[str, Any], proposed_index: int, kind: str, verdict: str
    ) -> tuple[str, list[str], dict[str, Any], bool, dict[str, Any] | None]:
        """A turn the call waits on. The controller can only reduce what the engines decided."""
        trigger = {"agentId": proposal["actor"]["agentId"], "fingerprint": proposal["fingerprint"], "index": proposed_index, "kind": kind}
        action, turn = self._turn(trigger)
        row = {"action": action["action"], "turn": turn}
        name = action["action"]
        if name == "hold":
            return "deny", [action.get("reasonCode", "controller_hold")], row, False, None
        if name == "halt_run":
            return "deny", [action.get("reasonCode", "controller_halt")], row, True, None
        if name == "ask_principal":
            return "escalate", ["controller_question"], row, False, {"questionId": action["questionId"], "summary": action["summary"]}
        # pass and intervene leave the engines' verdict standing; interventions are delivered separately.
        return verdict, [], row, False, None

    def _run_nonblocking(self) -> None:
        """Run the turns the trigger policy puts after the records appended since the last call."""
        while self._nb_cursor < len(self._records):
            record = self._records[self._nb_cursor]
            self._nb_cursor += 1
            if self._controller is None or self._state.status != "ACTIVE":
                continue
            for trigger in triggers_for(record, self._records[: record["index"] + 1], self._triggers):
                self._turn(trigger)

    def _issue_intervention(self, action: Mapping[str, Any], turn: int, trigger: Mapping[str, Any]) -> None:
        intervention_id = f"i-{self._ledger.record_count}"
        self._append(
            "intervention",
            {
                "agentId": trigger.get("agentId") or "root",
                "interventionId": intervention_id,
                "kind": action["kind"],
                "refs": list(action.get("refs", [])),
                "status": "pending",
                "text": action["text"],
                "textSha256": sha256_hex(action["text"]),
                "turn": turn,
            },
        )

    def _pending(self, agent_id: str | None) -> list[dict[str, Any]]:
        items = sorted(self._state.interventions.items(), key=lambda item: item[1]["issuedAtIndex"])
        return [
            {"agentId": item["agentId"], "interventionId": key, "kind": item["kind"], "text": item["text"]}
            for key, item in items
            if item["status"] == "pending" and (agent_id is None or item["agentId"] == agent_id)
        ]

    def _deliver(self, intervention_id: str, channel: str) -> dict[str, Any]:
        item = self._state.interventions.get(intervention_id)
        if item is None:
            raise ControlError("unknown_intervention", f"no intervention {intervention_id}", 404)
        if item["status"] != "pending":
            raise ControlError("intervention_closed", f"intervention {intervention_id} is {item['status']}", 409)
        if not isinstance(channel, str) or not channel or len(channel) > 64:
            raise ControlError("malformed_delivery", "a delivery names its channel")
        at = self._ledger.record_count
        self._append("intervention", {"atIndex": at, "channel": channel, "interventionId": intervention_id, "status": "delivered"})
        return {"agentId": item["agentId"], "atIndex": at, "channel": channel, "interventionId": intervention_id, "kind": item["kind"], "text": item["text"]}

    def pending_interventions(self, agent_id: str | None = None) -> list[dict[str, Any]]:
        """Interventions issued and not yet delivered, oldest first."""
        with self._lock:
            return self._pending(agent_id)

    def deliver_intervention(self, intervention_id: str, channel: str) -> dict[str, Any]:
        """Record that a runtime put this intervention in front of its actor, and through which channel."""
        with self._lock:
            self._require_open()
            delivered = self._deliver(intervention_id, channel)
            self._run_nonblocking()
            return delivered

    def _record_decision(
        self,
        proposal: Mapping[str, Any],
        proposed_index: int,
        verdict: str,
        effect: str,
        reasons: list[str],
        checks: Mapping[str, bool],
        engine_rows: list[dict[str, Any]],
        controller_row: dict[str, Any] | None,
        halt: bool,
        *,
        resolves: str | None = None,
        question: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = self._state
        now = self._clock()
        decision_index = self._ledger.record_count
        decision_id = f"d-{decision_index}"
        consequential = effect in CONSEQUENTIAL
        payload: dict[str, Any] = {
            "schema": DECISION_SCHEMA,
            "agentId": proposal["actor"]["agentId"],
            "checks": dict(checks),
            "decidedAt": _iso(now),
            "decisionId": decision_id,
            "effectClass": effect,
            "engines": engine_rows,
            "fingerprint": proposal["fingerprint"],
            "nextAuthority": {"allow": "lease" if consequential else "none", "deny": "none", "escalate": "principal"}[verdict],
            "proposalIndex": proposed_index,
            "reasonCodes": list(dict.fromkeys(reasons)),
            "state": {
                "contractHash": state.contract_hash,
                "envContractVersion": state.env_view.get("contract", {}).get("version"),
                "runStatus": state.status,
                "stateHashBefore": state.state_hash(),
            },
            "toolId": proposal["tool"]["id"],
            "verdict": verdict,
        }
        if controller_row is not None:
            payload["controller"] = controller_row
        if halt:
            payload["haltRun"] = True
        if resolves is not None:
            payload["resolvesEscalation"] = resolves
        self._append("control_decision", payload)
        self._decision_agents[decision_id] = payload["agentId"]
        decision = {key: payload[key] for key in ("decisionId", "effectClass", "fingerprint", "nextAuthority", "reasonCodes", "verdict")}
        if verdict == "allow" and consequential:
            ttl = int(state.limits.get("leaseTtlMs", 60_000))
            lease_id = f"l-{self._ledger.record_count}"
            expires = _iso(now + timedelta(milliseconds=ttl))
            self._append(
                "lease_issued",
                {
                    "agentId": proposal["actor"]["agentId"],
                    "decisionId": decision_id,
                    "expiresAt": expires,
                    "fingerprint": proposal["fingerprint"],
                    "leaseId": lease_id,
                    "toolId": proposal["tool"]["id"],
                }
                | ({"resolvesEscalation": resolves} if resolves else {}),
            )
            decision["lease"] = {"expiresAt": expires, "leaseId": lease_id}
        elif verdict == "escalate":
            escalation_id = f"e-{self._ledger.record_count}"
            self._append(
                "escalation",
                {
                    "agentId": proposal["actor"]["agentId"],
                    "decisionId": decision_id,
                    "escalationId": escalation_id,
                    "fingerprint": proposal["fingerprint"],
                    "reasonCodes": list(dict.fromkeys(reasons)),
                    "status": "open",
                    "toolId": proposal["tool"]["id"],
                }
                | ({"questionId": question["questionId"], "summary": question["summary"]} if question else {}),
            )
            decision["escalationId"] = escalation_id
            self._escalated[escalation_id] = (dict(proposal), proposed_index, effect)
            if self._principal is not None:
                answer = self._principal.resolve(state.escalations[escalation_id], state)
                return self._resolve(escalation_id, answer)
        return decision

    def resolve_escalation(self, escalation_id: str, answer: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._require_open()
            decision = self._resolve(escalation_id, answer)
            self._run_nonblocking()
            return decision

    def _resolve(self, escalation_id: str, answer: Mapping[str, Any]) -> dict[str, Any]:
        escalation = self._state.escalations.get(escalation_id)
        if escalation is None:
            raise ControlError("unknown_escalation", f"no escalation {escalation_id}", 404)
        if escalation["status"] != "open":
            raise ControlError("escalation_closed", f"escalation {escalation_id} is {escalation['status']}", 409)
        choice = answer.get("decision")
        if choice not in ("approve", "reject", "timeout"):
            raise ControlError("malformed_answer", "decision must be approve or reject")
        status = {"approve": "approved", "reject": "rejected", "timeout": "timeout"}[choice]
        self._append(
            "escalation",
            {"by": str(answer.get("by", "principal")), "escalationId": escalation_id, "status": status},
        )
        proposal, proposed_index, effect = self._escalated.pop(escalation_id)
        verdict = "allow" if choice == "approve" else "deny"
        reason = {"approve": "principal_approved", "reject": "principal_rejected", "timeout": "escalation_timeout"}[choice]
        return self._record_decision(
            proposal, proposed_index, verdict, effect, [reason], {}, [], None, False, resolves=escalation_id
        )

    def _await_escalation(self, decision: Mapping[str, Any], wait_ms: int) -> dict[str, Any]:
        escalation_id = decision["escalationId"]
        deadline = self._clock() + timedelta(milliseconds=wait_ms)
        while self._state.escalations[escalation_id]["status"] == "open":
            remaining = (deadline - self._clock()).total_seconds()
            if remaining <= 0:
                return self._resolve(escalation_id, {"decision": "timeout", "by": "control_module"})
            self._changed.wait(timeout=min(remaining, 0.25))
        final = self._last_decision_for(escalation_id)
        return final

    def _last_decision_for(self, escalation_id: str) -> dict[str, Any]:
        last = self._state.last_decision or {}
        lease = next(
            (
                {"expiresAt": item["expiresAt"], "leaseId": lease_id}
                for lease_id, item in self._state.leases.items()
                if item["decisionId"] == last.get("decisionId")
            ),
            None,
        )
        result = {
            "decisionId": last.get("decisionId"),
            "escalationId": escalation_id,
            "reasonCodes": last.get("reasonCodes", []),
            "verdict": last.get("verdict"),
        }
        if lease:
            result["lease"] = lease
        return result

    # ------------------------------------------------------------------ gateway commit

    def commit(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Gateway entry point: consume a lease for this exact call, or decide without one."""
        required = {"fingerprint", "toolId", "args", "agentId"}
        if not isinstance(request, Mapping) or required - set(request):
            raise ControlError("malformed_commit", f"commit needs {sorted(required)}")
        with self._lock:
            self._require_open()
            result = self._commit(request)
            self._run_nonblocking()
            return result

    def _commit(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if True:
            state = self._state
            expected = call_fingerprint(state.run_id or "", request["agentId"], request["toolId"], request["args"])
            if expected != request["fingerprint"]:
                return self._gateway_decide(request, force_deny="fingerprint_mismatch")
            if state.effect_class(request["toolId"]) not in CONSEQUENTIAL:
                return self._gateway_decide(request)
            now = self._clock()
            for lease in state.active_leases(request["fingerprint"]):
                lease_id = lease["leaseId"]
                if datetime.fromisoformat(lease["expiresAt"]) <= now:
                    self._append("lease_expired", {"cause": "ttl", "fingerprint": lease["fingerprint"], "leaseId": lease_id})
                    continue
                recheck = self._recheck(request, lease)
                if recheck:
                    self._append("lease_expired", {"cause": "recheck_failed", "fingerprint": lease["fingerprint"], "leaseId": lease_id, "reasonCodes": recheck})
                    return {"committed": False, "decisionId": lease["decisionId"], "reasonCodes": recheck, "verdict": "deny"}
                self._append(
                    "lease_consumed",
                    {"decisionId": lease["decisionId"], "fingerprint": lease["fingerprint"], "leaseId": lease_id, "surface": request.get("surface", "gateway")},
                )
                return {"committed": True, "decisionId": lease["decisionId"], "leaseId": lease_id, "reasonCodes": [], "verdict": "allow"}
            if state.profile.get("requireShim"):
                self._append(
                    "bypass_detected",
                    {"agentId": request["agentId"], "fingerprint": request["fingerprint"], "toolId": request["toolId"], "where": "gateway"},
                )
                return self._gateway_decide(request, force_deny="shim_required")
            return self._gateway_decide(request)

    def _recheck(self, request: Mapping[str, Any], lease: Mapping[str, Any]) -> list[str]:
        """Re-run the deterministic checks against the state now in force.

        A lease the principal granted by answering an escalation has already had
        its question answered, so an engine asking the same question again does
        not fail the re-check. A hard deny always does.
        """
        if self._state.status != "ACTIVE":
            return ["run_not_active"]
        proposal = self._gateway_proposal(request)
        answered = bool(lease.get("resolvesEscalation"))
        reasons: list[str] = []
        for engine in self._engines:
            try:
                result = engine.evaluate(proposal, self._state)
            except Exception:  # noqa: BLE001
                return ["engine_error"]
            if result["verdict"] == "deny" or (result["verdict"] == "escalate" and not answered):
                reasons.extend(result.get("reasonCodes", []) or ["engine_refused"])
        return reasons

    def _gateway_proposal(self, request: Mapping[str, Any]) -> dict[str, Any]:
        actor = self._state.actors.get(request["agentId"], {"lineage": []})
        return {
            "schema": PROPOSAL_SCHEMA,
            "actor": {"agentId": request["agentId"], "lineage": list(actor["lineage"])},
            "args": dict(request["args"]),
            "contractHash": self._state.contract_hash,
            "fingerprint": request["fingerprint"],
            "proposedAt": _iso(self._clock()),
            "provenance": {
                "schema": PROVENANCE_SCHEMA,
                "attestation": "gateway_only",
                "contextTaint": [],
                "surface": "gateway_only",
            }
            | ({"nativeCallId": request["nativeCallId"]} if request.get("nativeCallId") else {}),
            "runId": self._state.run_id,
            "runtime": dict(self._state.runtime) or {"commit": "n/a", "id": "unknown", "shimHash": "n/a", "tier": "gateway_only", "version": "n/a"},
            "seq": 0,
            "tool": {"id": request["toolId"], "nativeName": request.get("nativeName", request["toolId"]), "registryHash": self._state.registry_hash},
        }

    def _gateway_decide(self, request: Mapping[str, Any], *, force_deny: str | None = None) -> dict[str, Any]:
        decision = self._decide(self._gateway_proposal(request), path="commit", force_deny=force_deny)
        lease = decision.get("lease")
        if decision["verdict"] == "allow" and lease:
            self._append(
                "lease_consumed",
                {"decisionId": decision["decisionId"], "fingerprint": decision["fingerprint"], "leaseId": lease["leaseId"], "surface": "gateway_only"},
            )
        committed = decision["verdict"] == "allow"
        return {
            "committed": committed,
            "decisionId": decision["decisionId"],
            "reasonCodes": decision["reasonCodes"],
            "verdict": decision["verdict"],
        } | ({"leaseId": lease["leaseId"]} if committed and lease else {})

    # ------------------------------------------------------------------ outcomes and events

    def outcome(self, outcome: Mapping[str, Any]) -> dict[str, Any]:
        try:
            validate_outcome(outcome)
        except WireError as exc:
            raise ControlError("malformed_outcome", str(exc)) from exc
        with self._lock:
            self._require_open()
            kind = "environment_transition" if outcome.get("effectId") else "tool_result"
            self._append(kind, dict(outcome))
            delivered = []
            agent = self._decision_agents.get(outcome.get("decisionId", ""))
            if agent and self._state.profile.get("interventionChannel", "gateway_trailer") == "gateway_trailer":
                # The fallback channel: the actor reads it on this tool result.
                delivered = [self._deliver(item["interventionId"], "gateway_trailer") for item in self._pending(agent)]
            self._run_nonblocking()
            return {"interventions": delivered, "projection": self.projection()}

    def event(self, kind: str, payload: Mapping[str, Any], role: str) -> dict[str, Any]:
        if kind not in EVENT_KINDS_BY_ROLE.get(role, ()):
            raise ControlError("event_not_allowed", f"role {role} cannot write {kind}", 403)
        if not isinstance(payload, Mapping):
            raise ControlError("malformed_event", "event payload must be an object")
        with self._lock:
            self._require_open()
            if kind == "delegation_spawned":
                self._check_delegation(payload)
            elif kind == "phase_entered":
                self._check_phase(payload)
            record = self._append(kind, payload)
            self._run_nonblocking()
            return {"index": record["index"]}

    def _check_phase(self, payload: Mapping[str, Any]) -> None:
        for key in ("agentId", "skillId", "phase"):
            if not isinstance(payload.get(key), str) or not payload[key]:
                raise ControlError("malformed_event", f"phase_entered needs {key}")
        if payload["agentId"] not in self._state.actors:
            raise ControlError("unknown_actor", "phase_entered names an unknown actor")

    def _check_delegation(self, payload: Mapping[str, Any]) -> None:
        for key in ("childAgentId", "parentAgentId"):
            if not isinstance(payload.get(key), str) or not payload[key]:
                raise ControlError("malformed_event", f"delegation_spawned needs {key}")
        if payload["parentAgentId"] not in self._state.actors:
            raise ControlError("unknown_actor", "a delegation needs a known parent")
        if payload["childAgentId"] in self._state.actors:
            raise ControlError("duplicate_actor", "child agent id already registered", 409)

    # ------------------------------------------------------------------ views

    def projection(self) -> dict[str, Any]:
        """Bounded view of control state for the actor. Never contains truth or leases."""
        with self._lock:
            state = self._state
            tools = state.registry.get("tools", {})
            return {
                "admissibleTools": sorted(tools),
                "lastDecision": dict(state.last_decision) if state.last_decision else None,
                "openQuestions": sorted(key for key, item in state.escalations.items() if item["status"] == "open"),
                "remainingActions": state.remaining_actions(),
                "runStatus": state.status,
            }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"records": self._ledger.record_count, "root": self._ledger.last_hash, "state": self._state.snapshot(), "stateHash": self._state.state_hash()}
