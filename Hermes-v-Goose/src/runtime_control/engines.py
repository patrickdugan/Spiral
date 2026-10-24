"""Policy engines, reference controllers and scripted principals.

An engine is a pure function of a proposal and the folded control state, and
returns ``{"verdict": "allow" | "deny" | "escalate", "reasonCodes", "checks",
"native"}``. Engines compose by conjunction in the control module: any deny
refuses, otherwise any escalate escalates. A controller can only reduce
authority, and a principal answers escalations. All three are named in
``run_start`` so a resumed module rebuilds the same pipeline.

Experiment repositories register their own engines with ``register_engine``
(Control-Harness registers its contract control ladder). This module ships one
reference engine, ``AllowlistCapEngine``, used by the demo environment and the
tests.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from runtime_control.state import ControlState
from runtime_control.wire import sha256_hex


CONTROLLER_ACTIONS = ("pass", "hold", "ask_principal", "intervene", "halt_run")
ENGINE_FACTORIES: dict[str, Callable[[Mapping[str, Any]], Any]] = {}


class EngineConfigError(ValueError):
    """Raised when run_start names an engine, controller or principal that cannot be built."""


def register_engine(engine_id: str, factory: Callable[[Mapping[str, Any]], Any]) -> None:
    existing = ENGINE_FACTORIES.get(engine_id)
    if existing is not None and existing is not factory:
        raise EngineConfigError(f"engine id already registered: {engine_id}")
    ENGINE_FACTORIES[engine_id] = factory


# Engines that wrap another project's policy code live in their own modules and load on first
# use, so a resumed or replayed run rebuilds them from run_start without the caller importing them.
OPTIONAL_ENGINE_MODULES = {
    "bitagent-gates-v1": "runtime_control.engines_bitagent",
    "bitagent-state-v1": "runtime_control.engines_bitagent_state",
    "phase-contract-v1": "runtime_control.engines_phase",
    "rtg-gateway-v1": "runtime_control.engines_rtg",
}


def build_engine(spec: Mapping[str, Any]) -> Any:
    engine_id = spec.get("engineId")
    if engine_id not in ENGINE_FACTORIES and engine_id in OPTIONAL_ENGINE_MODULES:
        import importlib

        importlib.import_module(OPTIONAL_ENGINE_MODULES[engine_id])
    factory = ENGINE_FACTORIES.get(spec.get("engineId"))
    if factory is None:
        raise EngineConfigError(f"unknown policy engine: {spec.get('engineId')}; register it first")
    return factory(spec.get("config", {}))


class AllowlistCapEngine:
    """Reference engine: recipient allowlist, escalation list, per-call and total caps.

    Config: ``{"tools": {tool_id: {"recipientField", "amountField", "allow",
    "escalate", "perCallCap", "totalCap"}}}``. The running total is read from the
    environment's public view field ``paid_total``. Tools without a rule are
    admitted; the registry decides whether they are consequential at all.
    """

    engine_id = "reference-allowlist-cap-v1"
    RULE_FIELDS = {"recipientField", "amountField", "allow", "escalate", "perCallCap", "totalCap"}

    def __init__(self, config: Mapping[str, Any]) -> None:
        tools = config.get("tools")
        if set(config) != {"tools"} or not isinstance(tools, Mapping) or not tools:
            raise EngineConfigError("allowlist-cap config is {'tools': {tool_id: rule}}")
        for tool_id, rule in tools.items():
            if not isinstance(rule, Mapping) or set(rule) != self.RULE_FIELDS:
                raise EngineConfigError(f"rule for {tool_id} needs exactly {sorted(self.RULE_FIELDS)}")
        self.config = {"tools": {k: dict(v) for k, v in tools.items()}}
        self.policy_hash = sha256_hex({"config": self.config, "engineId": self.engine_id})

    def evaluate(self, proposal: Mapping[str, Any], state: ControlState) -> dict[str, Any]:
        rule = self.config["tools"].get(proposal["tool"]["id"])
        if rule is None:
            return {"verdict": "allow", "reasonCodes": [], "checks": {}, "native": None}
        args = proposal["args"]
        recipient = args.get(rule["recipientField"])
        amount = args.get(rule["amountField"])
        if not isinstance(recipient, str) or isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            return {"verdict": "deny", "reasonCodes": ["invalid_arguments"], "checks": {"arguments_valid": False}, "native": None}
        paid = int(state.env_view.get("paid_total", 0))
        checks = {
            "arguments_valid": True,
            "per_call_cap": amount <= rule["perCallCap"],
            "recipient_allowed": recipient in rule["allow"],
            "total_cap": paid + amount <= rule["totalCap"],
        }
        reasons = [code for code, ok in (("per_call_cap", checks["per_call_cap"]), ("total_cap", checks["total_cap"])) if not ok]
        if not checks["recipient_allowed"]:
            if recipient in rule["escalate"] and not reasons:
                return {"verdict": "escalate", "reasonCodes": ["recipient_needs_approval"], "checks": checks, "native": None}
            reasons.insert(0, "recipient_not_allowed")
        return {"verdict": "deny" if reasons else "allow", "reasonCodes": reasons, "checks": checks, "native": None}


register_engine(AllowlistCapEngine.engine_id, AllowlistCapEngine)


class AlwaysPassController:
    controller_id = "always_pass"

    def turn(self, thread: Mapping[str, Any], events: Any, trigger: Mapping[str, Any], packet: Any = None) -> dict[str, Any]:
        return {"action": "pass"}


class AlwaysHoldController:
    controller_id = "always_hold"

    def turn(self, thread: Mapping[str, Any], events: Any, trigger: Mapping[str, Any], packet: Any = None) -> dict[str, Any]:
        return {"action": "hold", "reasonCode": "controller_hold"}


CONTROLLER_FACTORIES: dict[str, Callable[[], Any]] = {
    "always_pass": AlwaysPassController,
    "always_hold": AlwaysHoldController,
}


def build_controller(controller_id: str | None) -> Any:
    if controller_id in (None, "none"):
        return None
    factory = CONTROLLER_FACTORIES.get(controller_id)
    if factory is None:
        raise EngineConfigError(f"unknown controller: {controller_id}")
    return factory()


def validate_control_action(output: Any) -> dict[str, Any] | None:
    """Return the action if it is well formed, else None. Malformed output is never obeyed."""
    if not isinstance(output, Mapping) or output.get("action") not in CONTROLLER_ACTIONS:
        return None
    allowed = {
        "pass": {"action", "note"},
        "hold": {"action", "reasonCode", "note"},
        "ask_principal": {"action", "questionId", "summary", "blocking", "note"},
        "intervene": {"action", "kind", "refs", "text", "note"},
        "halt_run": {"action", "reasonCode", "note"},
    }[output["action"]]
    required = {"hold": {"reasonCode"}, "ask_principal": {"questionId", "summary"}, "intervene": {"kind", "text"}, "halt_run": set()}.get(output["action"], set())
    if set(output) - allowed or required - set(output):
        return None
    for key in ("note", "summary", "text", "reasonCode", "questionId"):
        if key in output and not isinstance(output[key], str):
            return None
    # Model-written strings are capped; an over-long one is malformed, never truncated into force.
    caps = {"note": 400, "summary": 600, "text": 600, "questionId": 64, "reasonCode": 48}
    if any(len(output[key]) > cap for key, cap in caps.items() if key in output):
        return None
    if output["action"] == "intervene" and (
        output["kind"] not in ("remind", "correct", "stop_and_wait")
        or not all(isinstance(ref, int) and not isinstance(ref, bool) for ref in output.get("refs", []))
    ):
        return None
    if "blocking" in output and not (isinstance(output["blocking"], list) and all(isinstance(item, str) for item in output["blocking"])):
        return None
    return dict(output)


class ScriptedPrincipal:
    """Answers every escalation the same way. Experiments name it in run_start."""

    def __init__(self, policy: str) -> None:
        if policy not in ("approve", "reject"):
            raise EngineConfigError(f"unknown scripted principal policy: {policy}")
        self.principal_id = f"scripted_{policy}"
        self.policy = policy

    def resolve(self, escalation: Mapping[str, Any], state: ControlState) -> dict[str, Any]:
        return {"decision": self.policy, "by": self.principal_id}


def build_principal(principal_id: str | None) -> Any:
    if principal_id in (None, "external"):
        return None
    if principal_id in ("scripted_approve", "scripted_reject"):
        return ScriptedPrincipal(principal_id.removeprefix("scripted_"))
    raise EngineConfigError(f"unknown principal: {principal_id}")
