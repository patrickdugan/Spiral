"""Run exact judge-shared-error measurement checks; no model, judge or controller is run."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from spiral_ln.evaluation_judge_measurement import verify


def _encode(value):
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        return str(value)
    if isinstance(value, (tuple, set, frozenset)):
        return list(value)
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"cannot encode {type(value)!r}")


def _headline(report: dict) -> dict:
    judges = {name: {"table": asdict(j["table"]),
                     "independence_p": float(j["independence_p"]),
                     "fisher_p": float(j["fisher_p"]),
                     "ceiling_p": float(j["ceiling_p"]),
                     "clopper_pearson_95": [float(j["clopper_pearson"]["lower"][0]),
                                            float(j["clopper_pearson"]["upper"][1])]}
              for name, j in report["judges"].items()}
    planning = {key: {"W_smallest": row["smallest"], "threshold": row["threshold"],
                      "power": float(row["power"]), "W_stable_from": row["stable_from"],
                      "expected_m": {a: s["ceiling"] for a, s in row["expected_m"].items()},
                      "unconditional_power_at_expected_m":
                          {a: float(p) for a, p in row["unconditional_power_at_expected_m"].items()},
                      "guaranteed_m": {a: g["smallest_m"] for a, g in row["guaranteed_m"].items()}}
                for key, row in report["planning"].items()}
    return {"judges": judges, "planning": planning,
            "independent_judge_measured_excess_under_gold_noise":
                float(report["gold_noise"]["independent_judge_measured_excess"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    verified = verify()
    report = {"schema_version": "0.1",
              "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              **verified, "headline": _headline(verified)}
    root = Path(__file__).resolve().parents[1]
    sources = ("scripts/verify_evaluation_judge_measurement.py",
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
