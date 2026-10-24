"""Score a model controller from its live turns (BitAgent's ``eval/run-runtime-phase9.ts --stage=live``).

Each recorded ``controller_turn`` is joined to the oracle label of the candidate it
decided, exactly as ``qualify_controller.py`` joins the counterfactual ones, but
the action is the one the controller took in the run, so later turns follow from
its earlier holds. Reports, per arm: the confusion of its vetoes against the
labels, the same for ``always_hold`` and the admissibility lookup on the same
turns, controller failures (a call that failed or answered out of grammar, held
as the live policy says), and interventions issued, delivered and reaching the
actor.

Usage: python scripts/score_live_controller.py --runs <runs-root>/<experiment> [--rule configs/controller_qualification_v1.json] [--out report.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qualify_controller import DEFAULT_RULE, JoinError, confusion, joined_executes, joined_turns, judge  # noqa: E402

from runtime_control.ledger import parse_receipts  # noqa: E402


def _with_label_check(verdict: dict, rows: list) -> dict:
    """Every vetoed turn's label must come from the refused candidate itself.

    Before BitAgent's runner received refused candidates it saw no proposal on a refused turn and
    labelled it critical with no candidate key, so every veto scored as right; such a run cannot
    qualify anything. A veto is labelled from its candidate when BitAgent marked it control_refused,
    when the label carries the candidate's key (a refused move the host would have rejected anyway),
    or when the candidate is one BitAgent cannot parse, which it labels without a key in every run.
    """
    bad = sum(1 for r in rows if r["model"] and r.get("arbiter") != "control_refused" and r["malformed"] and r["shapeOk"])
    verdict["checks"]["veto_labels_from_candidates"] = {"passed": bad == 0, "vetoesLabelledWithoutCandidate": bad}
    verdict["qualified"] = verdict["qualified"] and bad == 0
    return verdict


def score_engine_arm(arm_dir: Path, rule: dict) -> dict:
    """A policy engine's denials of execute calls, scored like a controller's vetoes."""
    positive = set(rule["positive"]["oracleLabel"])
    rows, join_errors = [], []
    runs = [p for p in sorted(arm_dir.iterdir()) if (p / "summary.json").exists() and not any(t in p.name for t in (".stale", ".incomplete", ".harness-error", ".controller-down"))]
    for run_dir in runs:
        try:
            joined = joined_executes(run_dir)
        except JoinError as exc:
            join_errors.append(str(exc))
            continue
        rows.extend(row | {"positive": row["oracleLabel"] in positive, "model": row["verdict"] == "deny", "always_pass": False, "always_hold": True, "admissible_rule": not row["keyAdmissible"]} for row in joined)
    if rule.get("subset") == "keyAdmissible":
        rows = [r for r in rows if r["keyAdmissible"]]
    scores = {name: confusion(rows, name) for name in ("model", "always_pass", "always_hold", "admissible_rule")}
    counts = {"joinErrors": len(join_errors), "negatives": sum(1 for r in rows if not r["positive"]), "positives": sum(1 for r in rows if r["positive"]), "turns": len(rows)}
    reasons: dict[str, int] = {}
    for row in rows:
        for code in row["reasonCodes"]:
            reasons[code] = reasons.get(code, 0) + 1
    return {"decider": "engine", "joinErrors": join_errors[:20], "reasons": reasons, "runs": len(runs), "scores": scores, "subset": rule.get("subset"),
            "turns": len(rows), "positives": counts["positives"], "verdict": _with_label_check(judge(rule, scores, counts), rows)}


def score_arm(arm_dir: Path, rule: dict) -> dict:
    positive, veto = set(rule["positive"]["oracleLabel"]), set(rule["veto"])
    rows, join_errors, failures = [], [], 0
    interventions = {"delivered": 0, "issued": 0, "reached": 0}
    runs = [p for p in sorted(arm_dir.iterdir()) if (p / "summary.json").exists() and not any(t in p.name for t in (".stale", ".incomplete", ".harness-error", ".controller-down"))]
    for run_dir in runs:
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        for key in interventions:
            interventions[key] += int(summary.get("interventions", {}).get(key) or 0)
        failures += sum(1 for r in parse_receipts(run_dir / "ledger.jsonl") if r["kind"] == "controller_turn" and r["payload"].get("failure"))
        try:
            joined = joined_turns(run_dir)
        except JoinError as exc:
            join_errors.append(str(exc))
            continue
        for row in joined:
            rows.append(row | {"positive": row["oracleLabel"] in positive, "model": row["recorded"] in veto, "always_pass": False, "always_hold": True, "admissible_rule": not row["keyAdmissible"],
                               "state_rule": row["stateFault"]})
    if rule.get("subset") == "keyAdmissible":
        rows = [r for r in rows if r["keyAdmissible"]]
    elif rule.get("subset"):
        raise ValueError(f"unknown subset: {rule['subset']}")
    actions: dict[str, int] = {}
    for row in rows:
        actions[row["recorded"]] = actions.get(row["recorded"], 0) + 1
    return {
        "actions": actions,
        "controllerFailures": failures,
        "interventions": interventions,
        "joinErrors": join_errors[:20],
        "runs": len(runs),
        # state_rule (hold what the view marks faulty) is reported on the same turns, not gating (rule v2).
        "scores": (scores := {name: confusion(rows, name) for name in ("model", "always_pass", "always_hold", "admissible_rule", "state_rule")}),
        "subset": rule.get("subset"),
        # The rule's verdict on live turns, for a controller whose turns depend on its own earlier ones.
        "verdict": _with_label_check(judge(rule, scores, {"joinErrors": len(join_errors), "negatives": sum(1 for r in rows if not r["positive"]), "positives": sum(1 for r in rows if r["positive"]), "turns": len(rows)}), rows),
        "turns": len(rows),
        "positives": sum(1 for r in rows if r["positive"]),
        "keyAdmissibleTurns": {"turns": sum(1 for r in rows if r["keyAdmissible"]), "positives": sum(1 for r in rows if r["keyAdmissible"] and r["positive"]),
                               "model": confusion([r for r in rows if r["keyAdmissible"]], "model")},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", required=True, help="<runs-root>/<experiment>: one directory per arm")
    parser.add_argument("--rule", default=str(DEFAULT_RULE))
    parser.add_argument("--out")
    parser.add_argument("--decider", choices=("controller", "engine"), default="controller")
    args = parser.parse_args(argv)
    rule = json.loads(Path(args.rule).read_text(encoding="utf-8"))
    score = score_engine_arm if args.decider == "engine" else score_arm
    report = {arm.name: score(arm, rule) for arm in sorted(Path(args.runs).iterdir()) if arm.is_dir()}
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(json.dumps({arm: {k: v for k, v in r.items() if k in ("runs", "turns", "positives", "actions", "controllerFailures", "interventions", "reasons")} | {"model": {m: r["scores"]["model"][m] for m in ("precision", "recall", "f1", "tp", "fp", "fn")}, "qualified": r["verdict"]["qualified"]} for arm, r in report.items()}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
