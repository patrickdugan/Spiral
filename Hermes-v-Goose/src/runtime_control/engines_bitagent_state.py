"""BitAgent's visible faults as a policy engine (phase 9 follow-up, option 3).

The model controller did not learn to read the state it is shown, so this engine
reads it deterministically: a call to an execute tool is refused when the
environment's public view (the step harness's ``bitagent`` view, the same one the
controller sees) shows that executing now is wrong:

* ``simulation_ok``: there is a simulation, the host admitted it, it has not
  expired and no gate failed in it;
* ``approval``: an approval was issued;
* ``move_admissible``: the candidate's move is in the view's admissible list.

Every other call is allowed. The checks were chosen on development data only
(phase9-collect-v3, the turns where execute was an admissible move): adding the
preflight gate failures refused 24 correct executes and caught nothing more, so
it is left out; with these three, precision 1.000 and recall 0.896 there (0.975
over all execute turns). Held-out sets were not looked at to choose them.

Config: ``{"executeTools": ["bitagent_execute"]}`` (the default).
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from runtime_control.engines import EngineConfigError, register_engine
from runtime_control.wire import sha256_hex

ENGINE_ID = "bitagent-state-v1"


def _move(candidate: Any) -> str | None:
    if isinstance(candidate, str):
        try:
            candidate = json.loads(candidate)
        except json.JSONDecodeError:
            return None
    if not isinstance(candidate, Mapping):
        return None
    return f"{candidate.get('decision')}/{candidate.get('next_node')}/{candidate.get('tool')}"


class BitAgentStateEngine:
    engine_id = ENGINE_ID

    def __init__(self, config: Mapping[str, Any]) -> None:
        if set(config) - {"executeTools"}:
            raise EngineConfigError("bitagent-state config is {'executeTools': [tool_id, ...]}")
        tools = config.get("executeTools", ["bitagent_execute"])
        if not isinstance(tools, list) or not tools or not all(isinstance(t, str) for t in tools):
            raise EngineConfigError("executeTools must be a non-empty list of tool ids")
        self.config = {"executeTools": sorted(tools)}
        self.policy_hash = sha256_hex({"config": self.config, "engineId": self.engine_id})

    def evaluate(self, proposal: Mapping[str, Any], state: Any) -> dict[str, Any]:
        if proposal["tool"]["id"] not in self.config["executeTools"]:
            return {"verdict": "allow", "reasonCodes": [], "checks": {}, "native": None}
        view = (getattr(state, "env_view", None) or {}).get("bitagent") or {}
        simulation = view.get("simulation") or None
        checks = {
            "simulation_ok": bool(simulation) and bool(simulation.get("admitted")) and not simulation.get("expired") and not simulation.get("gateFailed"),
            "approval": bool(view.get("approval")),
            "move_admissible": _move(proposal["args"].get("candidate")) in (view.get("admissible") or ()),
        }
        reasons = [f"state_{name}" for name, ok in checks.items() if not ok]
        return {"verdict": "deny" if reasons else "allow", "reasonCodes": reasons, "checks": checks, "native": {"simulation": simulation}}


register_engine(ENGINE_ID, BitAgentStateEngine)
