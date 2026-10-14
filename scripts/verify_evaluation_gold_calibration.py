"""Run exact gold-calibration checks (second-grader estimate of eta, its sampling law, the asymmetric
Dawid-Skene model, four raters, the joint statement for (eta_1, eps_1), the level-alpha tetrad tests, the
plug-in-free interval for eps_1, monotonicity in the Dawid-Skene root); no model, judge or grader is run."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from spiral_ln.evaluation_gold_calibration import (
    CELLS4, COVERAGE_SIZES, INTERVAL_SIZES, JOINT_SIZES, SAMPLING_SIZES, TETRAD_SIZES, verify,
)


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


def _statement(statement: dict) -> dict:
    out = {"status": statement["status"],
           "eps1_range": _pair(statement["eps1_range"]),
           "below_ceiling_jointly": statement.get("below_ceiling_jointly"),
           "above_independence_jointly": statement.get("above_independence_jointly"),
           "clamped_points": statement.get("clamped_points"),
           "rows": [{"eta0": _f(row["eta0"]), "eps1_hat": _f(row["recovered"]["eps1"]),
                     "clamped": row["recovered"]["clamped"], "corrected_table": asdict(row["corrected_table"]),
                     "eps1_bracket": _pair(row["eps1_bracket"]), "ceiling_p": _f(row["tests"]["ceiling_p"]),
                     "independence_p": _f(row["tests"]["independence_p"])}
                    for row in statement.get("inversions", []) if row["feasible"]]}
    return out


def _joint(joint: dict) -> dict:
    out = {}
    for size, entry in joint["by_size"].items():
        eta_set = entry["eta_set"]
        out[str(size)] = {
            "agreement_counts": {",".join(map(str, k)): v for k, v in eta_set["counts"].items()},
            "observed_square": _f(eta_set["observed_square"]),
            "disagreement_bound": _f(eta_set["disagreement_bound"]["eta_upper_bound"]),
            "eta_set": [_f(e) for e in eta_set["retained"]],
            "square_p": {str(row["eta0"]): _f(row["square_test"]["p_bracket"][1])
                         for row in eta_set["rows"] if row["square_test"] is not None},
            "max_bracket_width": _f(eta_set["max_bracket_width"]),
            "judges": {name: _statement(j["statement"]) for name, j in entry["judges"].items()},
            "ranges_disjoint": entry["ranges_disjoint"], "tests_separate": entry["tests_separate"]}
    return out


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
    four = report["four_raters"]
    four_head = {"counts": [int(four["counts"][c]) for c in CELLS4],
                 "solution": _ds(four["constraints"]["fit"]["solution"]),
                 "residuals": {k: _f(v) for k, v in four["residuals"].items()},
                 "constraint_jacobian_rank": four["constraint_jacobian_rank"],
                 "parameter_jacobian_rank": four["parameter_jacobian_rank"],
                 "chance_rater": {str(k): v for k, v in four["chance_rater"].items()},
                 "copy_grader": {rho: {"tetrad_residual": _f(row["closed_form_residual"]),
                                       "four_rater_status": row["constraints"]["fit"]["status"],
                                       "triple_123_status": row["triple_123"]["status"],
                                       "triple_123_prior": _pair(row["triple_123"]["solution"]["prior"])
                                       if isinstance(row["triple_123"]["solution"]["prior"], tuple)
                                       else _f(row["triple_123"]["solution"]["prior"])}
                                 for rho, row in four["copy_grader"].items()},
                 "copy_witness_counts": [int(four["copy_witness_counts"][c]) for c in CELLS4]}
    tetrad = report["tetrad"]
    tetrad_head = {
        "null_zeta": {str(c): _f(z) for c, z in tetrad["null_moments"]["zeta"].items()},
        "scaled_variance": {str(m): {k: _f(m * x) for k, x in v.items()} for m, v in tetrad["variances"].items()},
        "critical_values": {str(m): {name: {side: _f(t) for side, t in d.items()} for name, d in row.items()}
                            for m, row in tetrad["critical_values"].items()},
        "sign_test_null_size": {str(m): {side: _pair(r["bracket"]) for side, r in d.items()}
                                for m, d in tetrad["null_size_sign_test"].items()},
        "efficiency_ratio": _f(tetrad["efficiency_ratio"]),
        "copy_grader": {rho: {"tetrad": _f(row["tetrad"]), "by_size": {
            str(m): {"sign_test_power": {side: _pair(r["bracket"]) for side, r in entry["sign_test_power"].items()},
                     "cantelli_power_lower_bound": {name: {side: _f(r["power_lower_bound"]) for side, r in d.items()}
                                                    for name, d in entry["cantelli_power_lower_bound"].items()},
                     "asymptotic_noncentrality_squared": _f(entry["asymptotic_noncentrality_squared"])}
            for m, entry in row["by_size"].items()}} for rho, row in tetrad["alternatives"].items()}}
    interval = report["interval"]
    interval_head = {
        "by_size": {str(m): {"ranges_disjoint": e["ranges_disjoint"],
                             "judges": {name: {"status": j["interval"]["status"], "eta_range": _pair(j["interval"]["eta_range"]),
                                               "eps1_range": _pair(j["interval"]["eps1_range"])}
                                        for name, j in e["judges"].items()}}
                    for m, e in interval["by_size"].items()},
        "delta_variance": {name: {k: _f(v) for k, v in d.items()} for name, d in interval["delta_variance"].items()},
        "coverage": {str(m): {name: {"coverage": _f(c["coverage"]), "box_coverage": _f(c["box_coverage"])}
                              for name, c in d.items()} for m, d in interval["coverage"].items()}}
    witness = report["monotonicity"]["witness"]
    monotone_head = {"witness_end_values": [_f(v) for v in witness["end_values"]],
                     "witness_enclosure": _pair(witness["enclosure"]["enclosure"]),
                     "witness_true_minus_end_signs": witness["true_minus_end_signs"],
                     "witness_judge_rates_at_ends": [[_f(a), _f(b)] for a, b in witness["judge_rates_at_ends"]],
                     "fixture_records_critical_points_in_range": {
                         name: r["critical_points_in_range"] for name, r in report["monotonicity"]["fixture_records"].items()}}
    return {"kappas": {",".join(map(str, k)): _f(v) for k, v in raters["kappas"].items()},
            "squares": {str(k): _f(v) for k, v in raters["squares"].items()},
            "recovered": {"eta1": _f(raters["recovered_eta1"]), "eta2": _f(raters["recovered_eta2"]),
                          "accuracy": _f(raters["recovered_accuracy"])},
            "pipeline": pipeline, "dependent_grader": dependent, "sampling": sampling_head,
            "dawid_skene": ds_head, "asymmetric_pipeline": asym_head,
            "four_raters": four_head, "joint": _joint(report["joint"]),
            "tetrad": tetrad_head, "interval": interval_head, "monotonicity": monotone_head}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sampling-size", type=int, action="append", default=[],
                        help="add an item count to the enumerated sampling-law ladder (default %s)" % (SAMPLING_SIZES,))
    parser.add_argument("--joint-size", type=int, action="append", default=[],
                        help="add an item count for the joint statement (default %s)" % (JOINT_SIZES,))
    parser.add_argument("--tetrad-size", type=int, action="append", default=[],
                        help="add an item count for the tetrad tests' sizes and powers (default %s)" % (TETRAD_SIZES,))
    parser.add_argument("--interval-size", type=int, action="append", default=[],
                        help="add an item count for the eps_1 interval (default %s)" % (INTERVAL_SIZES,))
    parser.add_argument("--coverage-size", type=int, action="append", default=[],
                        help="add an item count for the interval's exact coverage enumeration (default %s)" % (COVERAGE_SIZES,))
    parser.add_argument("--workers", type=int, default=1,
                        help="processes for the square tests of the eta set (results do not depend on it)")
    args = parser.parse_args()
    sizes = tuple(sorted(set(SAMPLING_SIZES) | set(args.sampling_size)))
    joint_sizes = tuple(sorted(set(JOINT_SIZES) | set(args.joint_size)))
    tetrad_sizes = tuple(sorted(set(TETRAD_SIZES) | set(args.tetrad_size)))
    interval_sizes = tuple(sorted(set(INTERVAL_SIZES) | set(args.interval_size)))
    coverage_sizes = tuple(sorted(set(COVERAGE_SIZES) | set(args.coverage_size)))
    verified = verify(sizes, joint_sizes, args.workers, tetrad_sizes, interval_sizes, coverage_sizes)
    report = {"schema_version": "0.4",
              "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "sampling_sizes": list(sizes), "joint_sizes": list(joint_sizes),
              "tetrad_sizes": list(tetrad_sizes), "interval_sizes": list(interval_sizes),
              "coverage_sizes": list(coverage_sizes),
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
