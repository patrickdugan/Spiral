"""Run exact gold-calibration checks (second-grader estimate of eta); no model, judge or grader is run."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from spiral_ln.evaluation_gold_calibration import verify


def _encode(value):
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        return str(value)
    if isinstance(value, (tuple, set, frozenset)):
        return list(value)
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"cannot encode {type(value)!r}")


def _stringify_keys(value):
    if isinstance(value, dict):
        return {(",".join(map(str, k)) if isinstance(k, tuple) else str(k)): _stringify_keys(v)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_stringify_keys(v) for v in value]
    if is_dataclass(value) and not isinstance(value, type):
        return _stringify_keys(asdict(value))
    return value


def _bracket(entry) -> dict:
    return {"lower": float(entry["lower"]), "upper": float(entry["upper"]),
            "exact": None if entry["exact"] is None else float(entry["exact"])}


def _inversion(inv) -> dict:
    tests = inv["tests"]
    return {"eta": float(inv["eta"]),
            "recovered": {k: float(v) for k, v in inv["recovered"].items()},
            "corrected_table": asdict(inv["corrected_table"]),
            "independence_p": float(tests["independence_p"]), "fisher_p": float(tests["fisher_p"]),
            "ceiling_p": float(tests["ceiling_p"]),
            "d_eps1_d_eta": float(inv["sensitivity_d_eps1_d_eta"])}


def _headline(report: dict) -> dict:
    raters = report["three_raters"]
    pipeline = {name: {"eta1": _bracket(j["calibration"]["eta1"]), "eta2": _bracket(j["calibration"]["eta2"]),
                       "accuracy_from_identity": _bracket(j["calibration"]["accuracy_from_identity"]),
                       "inversions": [_inversion(inv) for inv in j["calibration"]["inversions"]],
                       "constraints_pass": j["calibration"]["constraints"]["passes"]}
                for name, j in report["pipeline"].items()}
    dependent = {rho: {"eta1": _bracket(row["calibration"]["eta1"]),
                       "constraint_residuals": {str(k): float(v) for k, v in row["calibration"]["constraints"]["residuals"].items()},
                       "inversions": [_inversion(inv) for inv in row["calibration"]["inversions"]],
                       "uncorrected_independence_p": float(row["uncorrected_tests"]["independence_p"])}
                 for rho, row in report["dependent_grader"]["rows"].items()}
    return {"kappas": {",".join(map(str, k)): float(v) for k, v in raters["kappas"].items()},
            "squares": {str(k): float(v) for k, v in raters["squares"].items()},
            "recovered": {"eta1": float(raters["recovered_eta1"]), "eta2": float(raters["recovered_eta2"]),
                          "accuracy": float(raters["recovered_accuracy"])},
            "pipeline": pipeline, "dependent_grader": dependent}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    verified = verify()
    report = {"schema_version": "0.1",
              "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              **_stringify_keys(verified), "headline": _headline(verified)}
    root = Path(__file__).resolve().parents[1]
    sources = ("scripts/verify_evaluation_gold_calibration.py",
               "src/spiral_ln/evaluation_gold_calibration.py",
               "src/spiral_ln/evaluation_judge_measurement.py",
               "src/spiral_ln/evaluation_feedback_signal.py",
               "src/spiral_ln/evaluation_game_feedback.py")
    report["source_sha256"] = {name: sha256((root / name).read_bytes()).hexdigest() for name in sources}
    report = json.loads(json.dumps(report, default=_encode))
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(rendered)
    else:
        print(rendered, end="")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
