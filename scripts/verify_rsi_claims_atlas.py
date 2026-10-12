"""Check takeoff-claims atlas structure and derived arithmetic; no models are run."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction as Q
from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_KINDS = {"primary", "primary_embedded_data"}
FEEDBACK_CLASSES = {"score_only", "item_level", "score_only_or_item_level", "item_level_within_run"}
REQUIRED = ("observed_contract", "what_improves", "estimand_supported", "headline_estimand",
            "missing_declarations", "proposed_axes", "independent_unit", "claim_boundary")


def _z_squared(row):
    a, sa, b, sb = (Q(value) for value in row)
    return (a - b) ** 2 / (sa ** 2 + sb ** 2)


def verify(manifest):
    checks = []

    def check(name, passed, **evidence):
        checks.append({"name": name, "passed": bool(passed), "evidence": evidence})

    cards = manifest["cards"]
    check("five_distinct_cards",
          len(cards) == manifest["cases"] == 5 and len({c["id"] for c in cards}) == 5)
    check("every_source_is_primary_and_dated",
          all(c["sources"] and all(s["kind"] in SOURCE_KINDS and s["url"].startswith("https://")
                                   and s["read_on"] == manifest["inspected_date"]
                                   for s in c["sources"]) for c in cards))
    check("sources_declared_checked_line_by_line", manifest["sources_verified_line_by_line"] is True)
    check("all_studies_explicitly_proposed",
          manifest["model_evaluations_run"] == 0
          and all(c["study_status"] == "proposed_not_executed" for c in cards))
    check("cards_carry_estimand_boundary_and_missing_declarations",
          all(all(c[key] for key in REQUIRED) for c in cards))
    check("headline_and_supported_estimands_differ_on_every_card",
          all(c["estimand_supported"] != c["headline_estimand"] for c in cards))
    feedback = [c["id"] for c in cards if c["feedback_access_declared"] in FEEDBACK_CLASSES]
    check("two_cases_declare_a_feedback_channel",
          len(feedback) == manifest["cases_declaring_feedback"] == 2, case=feedback)
    declared = [c["id"] for c in cards
                if c["loop_present"] == "yes" and c["feedback_access_declared"] in FEEDBACK_CLASSES
                and c["sealed_readout_declared"] is True]
    check("one_case_declares_feedback_and_a_sealed_readout",
          len(declared) == manifest["cases_with_declared_feedback_and_sealed_readout"] == 1,
          case=declared)
    changed = [c["id"] for c in cards if c["controller_changed_during_run"] is True]
    check("controller_change_recorded_where_declared", changed == ["openai_internal_model_math"],
          case=changed)
    check("no_case_supplies_the_compounding_estimand",
          manifest["cases_supplying_weight_level_gain_ratio_on_sealed_readout"] == 0
          and not any(c["what_improves"].startswith("model_weights") for c in cards))

    f = manifest["derived_fixtures"]
    m = f["openai_math"]
    check("openai_ratios",
          Q(m["manuscripts"], m["problems_posed_approx"]) == Q(m["manuscripts_per_problem"])
          and Q(m["families"], m["problems_posed_approx"]) == Q(m["families_per_problem"])
          and Q(m["lean_top_line_formalized"], m["manuscripts"]) == Q(m["lean_share_of_manuscripts"])
          and Q(m["problems_posed_approx"], m["families"]) == Q(m["problems_per_family"]),
          scope="Ratios of reported counts; the problem count is approximate in the source")
    check("openai_lean_share_matches_stated_percentage",
          round(100 * Q(m["lean_top_line_formalized"], m["manuscripts"]))
          == m["lean_share_stated_percent_approx"],
          lean_share=float(Q(m["lean_share_of_manuscripts"])))
    check("openai_withdrawals_account_for_count_change",
          m["manuscripts_at_release"] - m["withdrawn_2026_10_07"] == m["manuscripts"]
          and Q(m["withdrawn_2026_10_07"], m["manuscripts_at_release"])
          == Q(m["withdrawn_share_at_release"]))
    check("openai_swarm_scale",
          m["swarm_agents"] * m["swarm_hours"] == m["swarm_agent_hours_upper_bound"]
          and Q(m["output_tokens"], m["messages"]) == Q(m["tokens_per_message"]),
          tokens_per_message=float(Q(m["tokens_per_message"])))

    c = f["openai_chart"]
    denominator = c["pass_rate_denominator"]
    series = (("internal", c["internal_pass_rates"], c["internal_numerators"],
               c["internal_relative_compute"]),
              ("astra", c["astra_pass_rates"], c["astra_numerators"], c["astra_relative_compute"]))
    check("openai_chart_pass_rates_are_whole_multiples_of_denominator",
          all(len(rates) == len(numerators) == len(compute)
              and all(abs(rate - k / denominator) < 1e-12 for rate, k in zip(rates, numerators))
              for _, rates, numerators, compute in series),
          denominator=denominator)
    check("openai_chart_curves_rise_with_compute",
          all(all(a < b for a, b in zip(values, values[1:]))
              for _, rates, _, compute in series for values in (rates, compute)))
    nearest = min(range(len(c["internal_relative_compute"])),
                  key=lambda i: abs(c["internal_relative_compute"][i] - c["astra_relative_compute"][2]))
    check("openai_internal_model_ahead_at_matched_compute",
          c["internal_numerators"][nearest] > c["astra_numerators"][2],
          internal=c["internal_pass_rates"][nearest], astra=c["astra_pass_rates"][2])

    a = f["anthropic_index"]
    check("amdahl_ceiling_for_leads_share",
          1 / (1 - Q(a["leads_share"])) == Q(a["amdahl_ceiling_if_leads_share_free"]),
          scope="Illustrative; the share is of task-touch weights, not time")
    check("judge_agrees_with_humans_more_than_humans_agree",
          Q(a["exact_agreement_model_human"]) > Q(a["exact_agreement_human_human"])
          and Q(a["exact_agreement_model_human"]) < Q(a["within_one_level_model_human"])
          and a["leaves"] < a["nodes"])

    t = f["metr"]
    hours = Q(t["top_frontier_minutes"]) / 60
    low, high = Q(t["top_frontier_minutes_ci_low"]) / 60, Q(t["top_frontier_minutes_ci_high"]) / 60
    ceiling = t["stated_reliable_ceiling_hours"]
    check("top_frontier_point_above_stated_ceiling",
          round(hours, 2) == Q(t["top_frontier_hours_rounded"]) and hours > ceiling
          and t["exceeds_ceiling"], hours=float(hours))
    check("top_frontier_interval_straddles_ceiling",
          low < ceiling < high and t["interval_straddles_ceiling"] is True,
          interval_hours=[float(low), float(high)])
    d_low, d_high = (Q(v) for v in t["doubling_days_from_2023_ci"])
    check("doubling_time_point_inside_its_interval",
          d_low < Q(t["doubling_days_from_2023"]) < d_high and not t["fit_from_2024_published"],
          doubling_days=float(Q(t["doubling_days_from_2023"])))

    d = f["aide2"]
    steps = d["accepted_steps"]
    check("aide2_acceptance_arithmetic",
          Q(len(steps), d["proposals"]) == Q(d["acceptance_rate"])
          and (Q(d["grade_end"]) - Q(d["grade_start"])) / len(steps)
          == Q(d["mean_grade_gain_per_acceptance"])
          and [b - a_ for a_, b in zip(steps, steps[1:])] == d["acceptance_intervals"]
          and sum(s <= 49 for s in steps) == d["accepted_first_half"]
          and sum(s >= 50 for s in steps) == d["accepted_second_half"]
          and d["proposals"] - steps[-1] == d["proposals_after_last_acceptance"])
    first, final = d["readout_checkpoints"]
    check("aide2_readout_checkpoints_follow_position_rule",
          first == max(s for s in steps if s < 50) and final == steps[-1])
    z_fixed = {key: _z_squared(row) for key, row in d["table1_step85_vs_initial"].items()}
    check("aide2_fixed_model_gains_exceed_1_96_standard_errors",
          all(z_fixed[key] == Q(value) for key, value in d["table1_z_squared"].items())
          and all(z > Q(196, 100) ** 2 for z in z_fixed.values()),
          z={key: round(float(z) ** 0.5, 2) for key, z in z_fixed.items()},
          scope="Standard errors treated as independent; runs on shared tasks are paired")
    variance = sum(v * v for v in d["ale_cross_model_pm"])
    z_squared = Q(d["ale_cross_model_contrast"] ** 2, variance)
    check("ale_cross_model_contrast_below_conventional_threshold",
          variance == d["ale_cross_model_combined_variance"]
          and z_squared == Q(d["ale_cross_model_z_squared"])
          and (z_squared < Q(196, 100) ** 2) == d["ale_cross_model_below_1_96_if_independent"],
          z=round(float(z_squared) ** 0.5, 2),
          scope="Harness gain set against model gain; measures neither")
    check("reward_hacking_counts_consistent_with_rounded_percentages",
          all(round(100 * Q(count, d["reward_hacking_pairs"])) == pct
              for count, pct in zip(d["reward_hacking_counts_inferred"],
                                    d["reward_hacking_percentages"])),
          scope="Counts are inferred from rounding, not reported")

    p = f["princeton"]
    check("princeton_sample_is_two_questions",
          p["questions"] == len(p["scores"]) == 2 and p["runs"] == 5
          and all(1 <= s <= p["scale_max"] for s in p["scores"])
          and p["human_interventions_in_a_run"] > 0)
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "configs/rsi_claim_cards.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest_bytes = args.manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    checks = verify(manifest)
    report = {
        "schema_version": "0.2",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_status": "manifest_structure_and_exact_derived_arithmetic_only",
        "model_evaluations_run": 0,
        "sources_verified_line_by_line": manifest["sources_verified_line_by_line"],
        "manifest_sha256": sha256(manifest_bytes).hexdigest(),
        "verifier_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "check_count": len(checks),
        "all_passed": all(c["passed"] for c in checks),
        "checks": checks,
    }
    serialized = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(serialized)
        print(json.dumps({"all_passed": report["all_passed"], "checks": len(checks),
                          "output": str(args.output.resolve())}))
    else:
        print(serialized)
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
