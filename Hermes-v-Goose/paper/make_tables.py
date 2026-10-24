"""Every number and table in the paper, from the result files (run before compiling main.tex).

Writes generated/macros.tex and generated/tab_*.tex. A result that is not on disk yet becomes a
red \\pending{...} so the draft still compiles; nothing in the text is typed by hand except where
main.tex says so and names the source.

Sources: BitAgent apps/bitagent-launch-kernel/eval/artifacts (runner reports) and .runtime
(in-process pilots); this repo's results/runs (run directories) and results/phase9-logs (scores).
"""

from __future__ import annotations

import collections
import glob
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import qualify_controller as qc  # noqa: E402
import score_live_controller as slc  # noqa: E402

KERNEL = Path(os.environ.get("BITAGENT_KERNEL", "C:/Users/patri/OneDrive/Documents/GitHub/BitAgent/apps/bitagent-launch-kernel"))
ART = KERNEL / "eval" / "artifacts"
PILOT = KERNEL / ".runtime" / "control-capability" / "pilot"
RUNS = ROOT / "results" / "runs"
LOGS = ROOT / "results" / "phase9-logs"
OUT = Path(__file__).resolve().parent / "generated"
RULE_V1 = json.loads((ROOT / "configs" / "controller_qualification_v1.json").read_text(encoding="utf-8"))
RULE_V2 = json.loads((ROOT / "configs" / "controller_qualification_v2.json").read_text(encoding="utf-8"))
SET_ASIDE = (".stale", ".incomplete", ".harness-error", ".controller-down")

macros: dict[str, str] = {}


def pending(what: str) -> str:
    return "\\pending{" + what + "}"


DIGITS = {"0": "Zero", "1": "One", "2": "Two", "3": "Three", "4": "Four", "5": "Five", "6": "Six", "7": "Seven", "8": "Eight", "9": "Nine"}


def define(name: str, value) -> None:
    # LaTeX macro names are letters only.
    name = "".join(DIGITS.get(c, c) for c in name if c.isalnum())
    macros[name] = value if isinstance(value, str) else fmt(value)


def fmt(value) -> str:
    if value is None:
        return "--"
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, int):
        return f"{value:,}".replace(",", "{,}")
    return str(value)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def kept(arm_dir: Path) -> list[Path]:
    return [p for p in sorted(arm_dir.glob("*")) if (p / "summary.json").exists() and not any(t in p.name for t in SET_ASIDE)]


# ------------------------------------------------------------------ phase 8: soundness

def soundness() -> None:
    r = load(ART / "runtime-soundness-dev-all-arms.json")
    rows = []
    for arm in r["arms"]:
        s = arm["steps"]
        rows.append(f"{arm['arm']} & {s['oracle']['identicalToDirect']}/{s['oracle']['runs']} & {s['adversaryAndRandom']['unauthorizedEffects']} & "
                    f"{s['adversaryAndRandom']['identicalToDirect']}/{s['adversaryAndRandom']['runs']} & {s['knockouts']['caught']}/{s['knockouts']['runs']} & "
                    f"{s['controllers']['runs']} & {arm['seconds']} \\\\")
        define("soundSeconds" + arm["arm"].replace("null", "Null"), arm["seconds"])
    runs = sum(sum(step["runs"] for step in arm["steps"].values()) for arm in r["arms"])
    define("soundRunsPerArm", sum(step["runs"] for step in r["arms"][0]["steps"].values()))
    define("soundRunsTotal", runs)
    comps = r["ledgerComparisons"]
    define("soundProjectionPairs", f"{comps[0]['equal']}/{comps[0]['compared']}")
    write("tab_soundness", [
        r"\begin{tabular}{lrrrrrr}", r"\toprule",
        r"Arm & Oracle $=$ direct & Unauthorized & Adv./random $=$ direct & Knockouts caught & Controller runs & Seconds \\", r"\midrule",
        *rows, r"\bottomrule", r"\end{tabular}"])


# ------------------------------------------------------------------ phase 9: actor stage

def actor_stage() -> None:
    r = load(ART / "runtime-phase9-phase9-actor-v1.json")
    rows, native, undispatched, approval, closed = [], 0, 0, 0, 0
    for arm in r["result"]:
        for cell in arm["cells"]:
            g = cell["hardGates"]
            rows.append(f"{arm['arm']} & {cell['controller']} & {cell['runs']} & {g['unauthorizedEffects']} & {g['bypasses']} & {g['uncoveredToolCalls']} & "
                        f"{g['offMachineRequests']} & {cell['completion']['acting']} & {cell['completion']['stopping']} \\\\")
        for d in kept(RUNS / "phase9-actor-v1" / arm["arm"]):
            s = json.loads((d / "summary.json").read_text(encoding="utf-8"))
            native += s["coverage"]["nativeCalls"]
            undispatched += s["coverage"].get("undispatched", 0)
            closed += s["bitagent"]["status"] == "CLOSED"
            for line in (d / "truth.jsonl").read_text(encoding="utf-8").splitlines():
                x = json.loads(line)["label"].get("bitagentDecision")
                if x and x["arbiter"] == "accepted" and (x["candidateKey"] or "").split("/")[1:2] == ["approval"]:
                    approval += 1
                    break
    define("actorRuns", sum(cell["runs"] for arm in r["result"] for cell in arm["cells"]))
    define("actorToolCalls", native)
    define("actorUndispatched", undispatched)
    define("actorReachedApproval", approval)
    define("actorClosed", closed)
    write("tab_actor", [
        r"\begin{tabular}{llrrrrrll}", r"\toprule",
        r"Arm & Controller & Runs & Unauth. & Bypass & Uncovered & Off-machine & Acting & Stopping \\", r"\midrule",
        *rows, r"\bottomrule", r"\end{tabular}"])
    # The validate stall, through the runtimes.
    acc = rej = 0
    for arm in ("R1", "R2", "R0"):
        for d in kept(RUNS / "phase9-actor-v1" / arm):
            for line in (d / "truth.jsonl").read_text(encoding="utf-8").splitlines():
                x = json.loads(line)["label"].get("bitagentDecision")
                if x and x["turn"] is not None and (x["candidateKey"] or "").split("/")[1:2] == ["validate"]:
                    acc += x["arbiter"] == "accepted"
                    rej += x["arbiter"] != "accepted"
    define("runtimeValidateAccepted", acc)
    define("runtimeValidateProposed", acc + rej)
    # The first R2 pass (goose without the turn cap) and the environment-v1 arms.
    first = RUNS / "phase9-actor-v1" / "R2-first-pass-goose-uncapped"
    turns = holds = 0
    for d in kept(first):
        s = json.loads((d / "summary.json").read_text(encoding="utf-8"))
        turns += s["controllerTurns"]
        holds += s["controllerActions"]["hold"]
    define("firstPassControllerTurns", turns)
    define("firstPassHolds", holds)


def in_process() -> None:
    rows = []
    for name, label in (("bonsai8b-q1-dagv3lora-t1-A1-H3", "Bonsai-8B + v3 adapter"), ("bonsai8b-q1-base-t1-A1-H3", "Bonsai-8B base"), ("bonsai27b-q1-base-t1-A1-H3", "Bonsai-27B base")):
        s = load(PILOT / name / "summary.json")
        traces = [json.loads(l) for l in (PILOT / name / "traces.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        runs = [json.loads(l) for l in (PILOT / name / "runs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        val = [t for t in traces if (t.get("candidateKey") or "").split("/")[1:2] == ["validate"]]
        execs = sum(1 for t in traces if (t.get("candidateKey") or "").split("/")[1:2] == ["execute"] and t["admissibility"]["arbiter"] == "accepted")
        closed = sum(1 for x in runs if x["expectedStatus"] == "CLOSED" and x["status"] == "CLOSED")
        rows.append(f"{label} & {s['model']['cfc']:.3f} & {closed}/{sum(1 for x in runs if x['expectedStatus'] == 'CLOSED')} & "
                    f"{sum(1 for t in val if t['admissibility']['arbiter'] == 'accepted')}/{len(val)} & {execs} \\\\")
    write("tab_inprocess", [
        r"\begin{tabular}{lrrrr}", r"\toprule",
        r"Model (A1, in process, H3) & CFC & Closed & \texttt{validate} accepted & Executes \\", r"\midrule",
        *rows, r"\bottomrule", r"\end{tabular}"])


# ------------------------------------------------------------------ qualification

def counterfactual_v1() -> None:
    q = load(LOGS / "qualification-bonsai8b.json")
    m, h = q["scores"]["model"], q["scores"]["always_hold"]
    define("vOneTurns", q["counts"]["turns"])
    define("vOnePositives", q["counts"]["positives"])
    define("vOneLookupPositives", q["scores"]["admissible_rule"]["tp"])
    define("vOneLookupFOne", q["scores"]["admissible_rule"]["f1"])
    define("vOneModelPrecision", m["precision"])
    define("vOneModelRecall", m["recall"])
    define("vOneModelFOne", m["f1"])
    define("vOneHoldFOne", h["f1"])
    define("vOneHolds", m["vetoes"])
    acts = collections.Counter(t["action"] for t in q["turns"])
    define("vOnePass", acts["pass"])
    define("vOneIntervene", acts["intervene"])
    # The live controller diverges from the replay after its first turn (its thread holds its own turns).
    first, later = collections.Counter(), collections.Counter()
    by_run = collections.defaultdict(list)
    for t in q["turns"]:
        by_run[t["run"][2:]].append((t["index"], t["action"]))
    for d in kept(RUNS / "phase9c-live-controller" / "null"):
        live = [json.loads(l)["payload"]["output"]["action"] for l in (d / "ledger.jsonl").read_text(encoding="utf-8").splitlines() if json.loads(l)["kind"] == "controller_turn"]
        replay = [a for _, a in sorted(by_run.get(d.name[2:], []))]
        if live and replay:
            first[live[0] == replay[0]] += 1
            for a, b in zip(replay[1:], live[1:]):
                later[(a, b)] += 1
    define("divergeFirstAgree", first[True])
    define("divergeFirstRuns", first[True] + first[False])
    define("divergePassToIntervene", later[("pass", "intervene")])
    define("divergeHoldToIntervene", later[("hold", "intervene")])


def v2_reference() -> None:
    class Pass:
        controller_id = "pass"

        def turn(self, thread, events, trigger, packet=None):
            return {"action": "pass"}

    cache = OUT / "cache_v2_reference.json"
    if cache.exists():
        r = json.loads(cache.read_text(encoding="utf-8"))
    else:
        r = qc.qualify(RUNS / "phase9-collect-v3" / "null", Pass(), RULE_V2)
        r = {"counts": r["counts"], "scores": r["scores"]}
        cache.write_text(json.dumps(r), encoding="utf-8")
    define("vTwoRefTurns", r["counts"]["turns"])
    define("vTwoRefPositives", r["counts"]["positives"])
    define("vTwoRefBase", r["counts"]["positives"] / r["counts"]["turns"])
    define("vTwoRefHoldFOne", r["scores"]["always_hold"]["f1"])
    define("vTwoRefStateFOne", r["scores"]["state_rule"]["f1"])
    define("vTwoRefStatePrecision", r["scores"]["state_rule"]["precision"])
    define("vTwoRefStateRecall", r["scores"]["state_rule"]["recall"])


def live_score(experiment: str, decider: str = "controller"):
    path = RUNS / experiment / "null"
    report = ART / f"runtime-phase9-{experiment}.json"
    rep = load(report)
    if not path.exists() or rep is None or not rep.get("complete"):
        return None
    score = slc.score_engine_arm(path, RULE_V2) if decider == "engine" else slc.score_arm(path, RULE_V2)
    outcomes = rep["result"][0]["outcomes"]
    return score, outcomes, rep["result"][0]["hardGates"]


def qualification_table(prefix: str, experiments: list[tuple[str, str]], decider: str = "controller") -> None:
    rows = []
    for label, experiment in experiments:
        got = live_score(experiment, decider)
        tag = prefix + label.split()[0].replace("-", "")
        if got is None:
            rows.append(f"{label} & " + " & ".join([pending("running")] * 9) + r" \\")
            for field in ("Precision", "Recall", "FOne", "Qualified", "CfcWith", "CfcWithout", "Unauthorized", "Base", "HoldShare", "HoldFOne", "StateFOne", "FOneMargin"):
                define(tag + field, pending("running"))
            continue
        score, outcomes, gates = got
        m, h = score["scores"]["model"], score["scores"]["always_hold"]
        state = score["scores"].get("state_rule")
        verdict = "yes" if score["verdict"]["qualified"] else "no"
        rows.append(f"{label} & {fmt(score['turns'])} ({fmt(score['positives'])}) & {fmt(h['precision'])} & {fmt(m['precision'])} & {fmt(m['recall'])} & {fmt(m['f1'])} & {fmt(h['f1'])} & "
                    f"{fmt(state['f1'] if state else None)} & {outcomes['cfcWithout']}$\\to${outcomes['cfcWithController']} & {verdict} \\\\")
        define(tag + "StateFOne", state["f1"] if state else None)
        # always_hold's precision is the base rate; the share of turns vetoed shows how close to it the decider sits.
        define(tag + "Base", h["precision"])
        define(tag + "HoldShare", m["vetoes"] / score["turns"] if score["turns"] else None)
        define(tag + "HoldFOne", h["f1"])
        define(tag + "FOneMargin", m["f1"] - h["f1"] if m["f1"] is not None and h["f1"] is not None else None)
        define(tag + "Precision", m["precision"])
        define(tag + "Recall", m["recall"])
        define(tag + "FOne", m["f1"])
        define(tag + "Qualified", verdict)
        define(tag + "CfcWith", outcomes["cfcWithController"])
        define(tag + "CfcWithout", outcomes["cfcWithout"])
        define(tag + "Unauthorized", gates["unauthorizedEffects"])
    write("tab_" + prefix, [
        r"\begin{tabular}{lrrrrrrrrl}", r"\toprule",
        r"Set & Turns (pos.) & Base rate & Precision & Recall & F1 & \texttt{always\_hold} F1 & View rule F1 & Completions & Qualifies \\", r"\midrule",
        *rows, r"\bottomrule", r"\end{tabular}"])


def label_artifact() -> None:
    """What the scorer said before refused candidates reached the runner (kept to show the artifact)."""
    path = RUNS / "brief-b1-heldout-a" / "null"
    if not path.exists():
        return
    old = slc.score_arm(path, RULE_V2)
    m = old["scores"]["model"]
    define("artifactPrecision", m["precision"])
    define("artifactRecall", m["recall"])
    define("artifactVetoes", m["vetoes"])
    define("artifactUnlabelled", old["verdict"]["checks"]["veto_labels_from_candidates"]["vetoesLabelledWithoutCandidate"])


def live_controller() -> None:
    rep = load(ART / "runtime-phase9-phase9c-live-r2.json")
    if rep is None or not rep.get("complete"):
        for name in ("liveRuns", "liveTurns", "liveHolds", "liveInterventions", "liveReached", "liveUnauthorized"):
            define(name, pending("running"))
        write("tab_live", [r"\begin{tabular}{l}", r"\toprule", pending("phase9c-live-r2 running") + r" \\", r"\bottomrule", r"\end{tabular}"])
        return
    turns = holds = 0
    reached = issued = 0
    rows = []
    for arm in rep["result"]:
        score = slc.score_arm(RUNS / "phase9c-live-r2" / arm["arm"], RULE_V1)
        m = score["scores"]["model"]
        turns += score["turns"]
        holds += score["actions"].get("hold", 0)
        issued += score["interventions"]["issued"]
        reached += score["interventions"]["reached"]
        g = arm["hardGates"]
        rows.append(f"{arm['arm']} & {arm['runs']} & {score['turns']} & {score['actions'].get('hold', 0)} & {score['actions'].get('intervene', 0)} & "
                    f"{score['actions'].get('pass', 0)} & {fmt(m['precision'])} & {fmt(m['recall'])} & {g['unauthorizedEffects'] + g['bypasses'] + g['uncoveredToolCalls'] + g['offMachineRequests']} \\\\")
    define("liveRuns", sum(arm["runs"] for arm in rep["result"]))
    define("liveTurns", turns)
    define("liveHolds", holds)
    define("liveInterventions", issued)
    define("liveReached", reached)
    write("tab_live", [
        r"\begin{tabular}{lrrrrrrrr}", r"\toprule",
        r"Arm & Runs & Turns & Hold & Intervene & Pass & Precision & Recall & Hard-gate events \\", r"\midrule",
        *rows, r"\bottomrule", r"\end{tabular}"])


def write(name: str, lines: list[str]) -> None:
    (OUT / f"{name}.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    OUT.mkdir(exist_ok=True)
    soundness()
    actor_stage()
    in_process()
    counterfactual_v1()
    v2_reference()
    label_artifact()
    live_controller()
    qualification_table("base", [("Development", "qual-v2-base-r2")])
    qualification_table("brief", [("Development", "brief-b1-dev-r2"), ("Held-out-A", "brief-b1-heldout-a-r2"), ("Held-out-B", "brief-b1-heldout-b-r2")])
    qualification_table("engine", [("Development", "engine-dev-r2"), ("Held-out-A", "engine-heldout-a-r2"), ("Held-out-B", "engine-heldout-b-r2")], decider="engine")
    text = "\n".join(f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in sorted(macros.items()))
    (OUT / "macros.tex").write_text(text + "\n", encoding="utf-8")
    print(f"{len(macros)} macros; pending: {sum(1 for v in macros.values() if 'pending' in v)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
