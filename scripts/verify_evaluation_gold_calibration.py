"""Run exact gold-calibration checks (second-grader estimate of eta, its sampling law, the asymmetric
Dawid-Skene model); no model, judge or grader is run."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from spiral_ln.evaluation_gold_calibration import SAMPLING_SIZES, verify


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


def _f(value):
    return None if value is None else float(value)


def _bracket(entry) -> dict:
    return {"lower": _f(entry["lower"]), "upper": _f(entry["upper"]), "exact": _f(entry["exact"])}


def _pair(entry) -> list | None:
    return None if entry is None else [float(entry[0]), float(entry[1])]


def _inversion(inv) -> dict:
    tests = inv["tests"]
    out = {"recovered": {k: _f(v) for k, v in inv["recovered"].items() if k != "measured_accuracy_consistent"},
           "corrected_table": asdict(inv["corrected_table"]),
           "independence_p": _f(tests["independence_p"]), "fisher_p": _f(tests["fisher_p"]),
           "ceiling_p": _f(tests["ceiling_p"])}
    if "eta" in inv:
        out["eta"] = _f(inv["eta"])
        out["d_eps1_d_eta"] = _f(inv["sensitivity_d_eps1_d_eta"])
    return out


def _law(law) -> dict:
    out = {k: _f(law[k]) for k in ("p_undefined_sign", "p_undefined_range", "p_undefined", "p_exact",
                                   "p_bracketed", "p_within_tolerance", "p_within_tolerance_given_defined",
                                   "square_mean", "square_variance")}
    out.update({"size": law["size"], "compositions": law["compositions"], "method": law["method"],
                "scaled_square_variance": _f(law.get("scaled_square_variance")),
                "eta_mean_bracket": _pair(law.get("eta_mean_bracket")),
                "scaled_eta_variance_bracket": _pair(law.get("scaled_eta_variance_bracket"))})
    return out


def _ds(params) -> dict:
    def conv(v):
        return _pair(v) if isinstance(v, tuple) else _f(v)
    return {"prior": conv(params["prior"]),
            "false_negatives": {str(i): conv(v) for i, v in params["false_negatives"].items()},
            "false_positives": {str(i): conv(v) for i, v in params["false_positives"].items()}}


def _headline(report: dict) -> dict:
    raters = report["three_raters"]
    pipeline = {name: {"eta1": _bracket(j["calibration"]["eta1"]), "eta2": _bracket(j["calibration"]["eta2"]),
                       "accuracy_from_identity": _bracket(j["calibration"]["accuracy_from_identity"]),
                       "inversions": [_inversion(inv) for inv in j["calibration"]["inversions"]],
                       "constraints_pass": j["calibration"]["constraints"]["passes"]}
                for name, j in report["pipeline"].items()}
    dependent = {rho: {"eta1": _bracket(row["calibration"]["eta1"]),
                       "constraint_residuals": {str(k): _f(v) for k, v in row["calibration"]["constraints"]["residuals"].items()},
                       "inversions": [_inversion(inv) for inv in row["calibration"]["inversions"]],
                       "uncorrected_independence_p": _f(row["uncorrected_tests"]["independence_p"])}
                 for rho, row in report["dependent_grader"]["rows"].items()}
    sampling = report["sampling"]
    sampling_head = {"delta_variance_eta": _f(sampling["delta"]["eta"]),
                     "delta_variance_square": _f(sampling["delta"]["square"]),
                     "delta_standard_error_scale": _f(sampling["delta"]["root_of_eta_variance"]),
                     "planning_size_se_below_1_50": sampling["planning_size"],
                     "laws": {str(m): _law(law) for m, law in sampling["laws"].items()},
                     "label_table_enumeration_16": _law(sampling["label_table_enumeration"]),
                     "other_points": {name: {"errors": [_f(e) for e in row["errors"]],
                                             "delta_variance_eta": _f(row["delta"]["eta"]),
                                             "planning_size": row["planning_size"],
                                             "law": _law(row["law"])} for name, row in sampling["other_points"].items()},
                     "disagreement_bounds": {k: {"size": b["size"], "agreements": b["agreements"],
                                                 "eta_upper_bound": _f(b["eta_upper_bound"])}
                                             for k, b in sampling["disagreement_bounds"].items()}}
    ds = report["dawid_skene"]
    ds_head = {"fixture_solution": _ds(ds["fit"]["solution"]), "fixture_alternative": _ds(ds["fit"]["alternative"]),
               "root": _f(ds["fit"]["root"]), "jacobian_rank": ds["jacobian_rank"],
               "copy_grader": {rho: {"status": row["status"], "in_range": row.get("in_range"),
                                     "solution": None if "solution" not in row else _ds(row["solution"])}
                               for rho, row in ds["copy_grader"].items()},
               "falsifiers": {k: v["status"] for k, v in ds["falsifiers"].items()}}
    asym = report["asymmetric_pipeline"]
    asym_head = {name: {"status": j["calibration"]["status"],
                        "inversions": [_inversion(inv) for inv in j["calibration"]["inversions"]],
                        "symmetric_pipeline_eta1": _bracket(j["symmetric_pipeline"]["eta1"]),
                        "symmetric_pipeline_eps1_ends": [_f(inv["recovered"]["eps1"]) for inv in j["symmetric_pipeline"]["inversions"]],
                        "symmetric_inversion_at_marginal_flip_rate": _f(j["symmetric_inversion_at_marginal_flip_rate"]),
                        "marginal_flip_rate": _f(j["marginal_flip_rate"])}
                 for name, j in asym["judges"].items()}
    return {"kappas": {",".join(map(str, k)): _f(v) for k, v in raters["kappas"].items()},
            "squares": {str(k): _f(v) for k, v in raters["squares"].items()},
            "recovered": {"eta1": _f(raters["recovered_eta1"]), "eta2": _f(raters["recovered_eta2"]),
                          "accuracy": _f(raters["recovered_accuracy"])},
            "pipeline": pipeline, "dependent_grader": dependent, "sampling": sampling_head,
            "dawid_skene": ds_head, "asymmetric_pipeline": asym_head}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sampling-size", type=int, action="append", default=[],
                        help="add an item count to the enumerated sampling-law ladder (default %s)" % (SAMPLING_SIZES,))
    args = parser.parse_args()
    sizes = tuple(sorted(set(SAMPLING_SIZES) | set(args.sampling_size)))
    verified = verify(sizes)
    report = {"schema_version": "0.2",
              "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "sampling_sizes": list(sizes),
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
