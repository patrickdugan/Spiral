"""Replay levels over a run directory (design 8.4), and the cross-runtime ledger projection.

* ``audit`` (R0): the chain verifies and folding the ledger reproduces the
  state hash every decision recorded.
* ``replay_decisions`` (R1): each consequential proposal re-evaluated by the
  engines on the state folded up to it, with the controller's action taken
  from the ledger, reproduces the recorded decision. Given other engine specs
  (a gate knockout, a different policy) it yields counterfactual decisions.
* ``replay_controller`` (R1c): rebuilding the thread from the ledger
  reproduces each recorded controller packet; another controller given the
  same packets yields its counterfactual actions.
* ``replay_hermes`` (R2): Hermes Lite run again with the proxy in replay mode
  and the gateway serving recorded results must make the same proposals.
* ``decision_projection``: the part of a ledger two runtimes must agree on
  when they carry the same calls (design 8.6 step 4).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from runtime_control.controller import build_packet, fold_thread, render_record
from runtime_control.engines import build_engine, validate_control_action
from runtime_control.errors import ToolArgumentError
from runtime_control.ledger import parse_receipts, verify_receipt_file
from runtime_control.state import fold
from runtime_control.wire import CONSEQUENTIAL


def _records(run_dir: str | Path) -> list[dict[str, Any]]:
    return [{"index": r["index"], "kind": r["kind"], "payload": r["payload"]} for r in parse_receipts(Path(run_dir) / "ledger.jsonl")]


def audit(run_dir: str | Path) -> dict[str, Any]:
    """R0: chain and state-hash audit."""
    ok, message = verify_receipt_file(Path(run_dir) / "ledger.jsonl")
    records = _records(run_dir)
    mismatched = [
        r["index"] for r in records
        if r["kind"] == "control_decision" and fold(records[: r["index"]]).state_hash() != r["payload"]["state"]["stateHashBefore"]
    ]
    return {"chain": ok, "message": message, "decisions": sum(r["kind"] == "control_decision" for r in records), "stateHashMismatches": mismatched, "ok": ok and not mismatched}


def replay_decisions(run_dir: str | Path, engine_specs: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """R1: re-evaluate every consequential proposal's engine stage; controller actions come from the ledger.

    Only decisions whose engines ran are replayed: the pipeline's earlier checks
    (fingerprint, pins, registration) and later ones (budget) are taken as
    recorded. With ``engine_specs`` (default: the run's own) the result is the
    counterfactual verdict per decision.
    """
    records = _records(run_dir)
    start = records[0]["payload"]
    specs = list(engine_specs) if engine_specs is not None else [{"engineId": e["engineId"], "config": e["config"]} for e in start["engines"]]
    engines = [build_engine(spec) for spec in specs]
    rows = []
    for record in records:
        if record["kind"] != "control_decision":
            continue
        decision = record["payload"]
        if decision.get("resolvesEscalation") or decision["effectClass"] not in CONSEQUENTIAL or not decision["checks"].get("tool_registered", True):
            continue
        pre = [code for code in decision["reasonCodes"] if code in ("fingerprint_mismatch", "registry_hash_mismatch", "run_not_active", "run_id_mismatch", "contract_hash_mismatch", "unknown_actor", "shim_required")]
        if pre:
            continue
        proposal = records[decision["proposalIndex"]]["payload"]["proposal"]
        state = fold(records[: decision["proposalIndex"] + 1])
        verdicts, reasons = [], []
        for engine in engines:
            try:
                result = engine.evaluate(proposal, state)
                verdicts.append(result["verdict"])
                reasons.extend(result.get("reasonCodes", []))
            except Exception:  # noqa: BLE001 - as in the module: an engine failure denies
                verdicts.append("deny")
                reasons.append("engine_error")
        verdict = "deny" if "deny" in verdicts else "escalate" if "escalate" in verdicts else "allow"
        controller = decision.get("controller")
        if controller is not None:
            turn = next(r for r in records if r["kind"] == "controller_turn" and r["payload"]["turn"] == controller["turn"])
            action = turn["payload"]["output"]
            if action["action"] in ("hold", "halt_run") and verdict in ("allow", "escalate"):
                verdict, reasons = "deny", reasons + [action.get("reasonCode", "controller_hold")]
            elif action["action"] == "ask_principal" and verdict == "allow":
                verdict, reasons = "escalate", reasons + ["controller_question"]
        if verdict == "allow" and "budget_exhausted" in decision["reasonCodes"]:
            verdict, reasons = "deny", reasons + ["budget_exhausted"]
        rows.append({
            "index": record["index"], "toolId": decision["toolId"],
            "recorded": (decision["verdict"], list(decision["reasonCodes"])),
            "replayed": (verdict, list(dict.fromkeys(reasons))),
        })
    changed = [row for row in rows if row["recorded"] != row["replayed"]]
    return {"decisions": len(rows), "changed": changed, "reproduced": not changed}


def replay_controller(run_dir: str | Path, controller: Any = None) -> dict[str, Any]:
    """R1c: rebuild every controller packet; with ``controller``, its action on each packet."""
    records = _records(run_dir)
    registry = records[0]["payload"]["registry"]
    view_keys = records[0]["payload"].get("profile", {}).get("controllerView")
    rows = []
    for record in records:
        if record["kind"] != "controller_turn" or "packetSha256" not in record["payload"]:
            continue
        payload = record["payload"]
        prefix = records[: record["index"]]
        thread = fold_thread(prefix)
        start = payload["eventRange"][0]
        events = [line for r in prefix[start:] if (line := render_record(r, registry, view_keys)) is not None]
        packet = build_packet(thread, events, payload["trigger"])
        row = {"index": record["index"], "trigger": payload["trigger"]["kind"], "recorded": payload["output"], "packetReproduced": packet["sha256"] == payload["packetSha256"]}
        if controller is not None:
            try:
                row["counterfactual"] = validate_control_action(controller.turn(thread, events, payload["trigger"], packet=packet))
            except Exception as exc:  # noqa: BLE001 - recorded, not raised: a counterfactual controller may fail
                row["counterfactual"] = {"error": f"{type(exc).__name__}: {exc}"}
        rows.append(row)
    return {"turns": len(rows), "packetsReproduced": all(row["packetReproduced"] for row in rows), "rows": rows}


# ------------------------------------------------------------------ cross-runtime projection

_DROP_KINDS = {"model_turn", "context_packet", "run_end"}


def decision_projection(run_dir: str | Path) -> list[Any]:
    """What two runtimes carrying the same calls must agree on.

    Dropped: the runtime record, native call ids and names, sequence numbers,
    timestamps, durations, ledger-position ids, state hashes (they cover the
    runtime record), and the proxy's records (each runtime writes its own prompts).
    """
    out: list[Any] = []
    for r in _records(run_dir):
        kind, p = r["kind"], r["payload"]
        if kind in _DROP_KINDS:
            continue
        if kind == "run_start":
            out.append(("run_start", p["contractHash"], p["registryHash"], p["profile"].get("requireShim"), json.dumps(p["view"], sort_keys=True)))
        elif kind == "action_proposed":
            q = p["proposal"]
            out.append(("proposed", p["path"], q["tool"]["id"], json.dumps(q["args"], sort_keys=True), q["fingerprint"], q["actor"]["agentId"], q["provenance"]["surface"], q["provenance"]["attestation"]))
        elif kind == "control_decision":
            out.append(("decision", p["toolId"], p["verdict"], tuple(p["reasonCodes"]), p["effectClass"], p["fingerprint"], (p.get("controller") or {}).get("action")))
        elif kind in ("lease_issued", "lease_consumed", "lease_expired"):
            out.append((kind, p["fingerprint"]))
        elif kind in ("tool_result", "environment_transition"):
            out.append((kind, p["status"], p["resultSha256"], p["fingerprint"]))
        elif kind == "escalation":
            out.append(("escalation", p["status"], p.get("toolId"), tuple(p.get("reasonCodes", ()))))
        elif kind == "controller_turn":
            out.append(("controller_turn", p["trigger"]["kind"], json.dumps(p["output"], sort_keys=True)))
        elif kind == "intervention":
            out.append(("intervention", p["status"], p.get("kind"), p.get("text"), p.get("channel")))
        elif kind == "environment_view":
            out.append(("environment_view", json.dumps(p.get("view"), sort_keys=True)))
        else:
            out.append((kind,))
    return out


def compare_projections(a: str | Path, b: str | Path) -> dict[str, Any]:
    left, right = decision_projection(a), decision_projection(b)
    first = next((n for n, (x, y) in enumerate(zip(left, right)) if x != y), None)
    if first is None and len(left) != len(right):
        first = min(len(left), len(right))
    return {
        "equal": left == right, "records": (len(left), len(right)), "firstDifference": first,
        "left": left[first] if first is not None and first < len(left) else None,
        "right": right[first] if first is not None and first < len(right) else None,
    }


# ------------------------------------------------------------------ R2

# Hermes Lite writes the wall clock into its system prompt to the minute
# ("Conversation started: Monday, October 13, 2026 06:42 AM"), so a replay that
# crosses a minute boundary differs there and nowhere else.
HERMES_VOLATILE = ((r'Conversation started: [^\\"]*', "Conversation started: <time>"),)


class RecordedEnvironment:
    """Serves a run's recorded gateway results in order, so a replayed runtime meets the same world."""

    adapter_id = "recorded"

    def __init__(self, run_dir: str | Path, registry: Mapping[str, Any], tools: Iterable[Mapping[str, Any]], view: Mapping[str, Any]) -> None:
        lines = (Path(run_dir) / "gateway_io.jsonl").read_text(encoding="utf-8").splitlines()
        self._results = [json.loads(line) for line in lines]
        self._registry, self._tools, self._view = dict(registry), [dict(t) for t in tools], dict(view)
        self.served = 0

    def tools(self) -> list[dict[str, Any]]:
        return [dict(t) for t in self._tools]

    def registry(self) -> dict[str, Any]:
        return json.loads(json.dumps(self._registry))

    def view(self) -> dict[str, Any]:
        return dict(self._view)

    def label(self, tool: str, args: Mapping[str, Any]) -> None:
        return None

    def execute(self, tool: str, args: Mapping[str, Any], call_id: str) -> dict[str, Any]:
        committed = [r for r in self._results if r.get("status") != "denied"]
        if self.served >= len(committed):
            raise ToolArgumentError("replay: no recorded result left")
        row = committed[self.served]
        self.served += 1
        return {"evidenceIds": [], "result": row.get("result")}

    def truth(self) -> dict[str, Any]:
        return {"served": self.served}


def replay_hermes(original: str | Path, run_dir: str | Path, *, task: str, environment: Any, engines: Sequence[Mapping[str, Any]], **kwargs: Any) -> dict[str, Any]:
    """R2 for Hermes Lite: rerun with the proxy replaying ``model_io.jsonl`` and the gateway serving recorded results."""
    from runtime_control.adapters.hermes_lite import run_hermes_controlled

    recorded = RecordedEnvironment(original, environment.registry(), environment.tools(), environment.view())
    kwargs.setdefault("replay_normalizers", HERMES_VOLATILE)
    report = run_hermes_controlled(run_dir=run_dir, environment=recorded, engines=engines, plan=[], task=task, replay_path=Path(original) / "model_io.jsonl", **kwargs)
    proposals = lambda path: [  # noqa: E731
        (r["payload"]["proposal"]["tool"]["id"], json.dumps(r["payload"]["proposal"]["args"], sort_keys=True))
        for r in _records(path) if r["kind"] == "action_proposed"
    ]
    return {"replayMisses": sum(1 for line in (Path(run_dir) / "model_io.jsonl").read_text(encoding="utf-8").splitlines() if json.loads(line)["status"] == "replay_miss"),
            "sameProposals": proposals(original) == proposals(run_dir), "report": report}
