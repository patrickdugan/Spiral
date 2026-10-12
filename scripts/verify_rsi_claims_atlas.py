"""Check takeoff-claims atlas structure and derived arithmetic; no models are run."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction as Q
from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_KINDS = {"primary_summarized", "secondary", "screenshot", "search_excerpt"}
REQUIRED = ("observed_contract", "what_improves", "estimand_supported", "headline_estimand",
            "missing_declarations", "proposed_axes", "independent_unit", "claim_boundary")


def verify(manifest):
    checks = []

    def check(name, passed, **evidence):
        checks.append({"name": name, "passed": bool(passed), "evidence": evidence})

    cards = manifest["cards"]
    check("five_distinct_cards",
          len(cards) == manifest["cases"] == 5 and len({c["id"] for c in cards}) == 5)
    check("every_source_has_a_declared_reading_level",
          all(c["sources"] and all(s["kind"] in SOURCE_KINDS and s["url"].startswith("https://")
                                   and s["read_on"] == manifest["inspected_date"]
                                   for s in c["sources"]) for c in cards))
    check("no_card_rests_on_secondary_reading_alone",
          all(any(s["kind"] == "primary_summarized" for s in c["sources"]) for c in cards))
    check("all_studies_explicitly_proposed",
          manifest["model_evaluations_run"] == 0
          and all(c["study_status"] == "proposed_not_executed" for c in cards))
    check("cards_carry_estimand_boundary_and_missing_declarations",
          all(all(c[key] for key in REQUIRED) for c in cards))
    check("headline_and_supported_estimands_differ_on_every_card",
          all(c["estimand_supported"] != c["headline_estimand"] for c in cards))
    declared = [c["id"] for c in cards
                if c["loop_present"] == "yes" and c["feedback_access_declared"]
                and c["sealed_readout_declared"] is True]
    check("one_case_declares_feedback_and_a_sealed_readout",
          len(declared) == manifest["cases_with_declared_feedback_and_sealed_readout"] == 1,
          case=declared)
    check("no_case_supplies_the_compounding_estimand",
          manifest["cases_supplying_weight_level_gain_ratio_on_sealed_readout"] == 0
          and not any(c["what_improves"].startswith("model_weights") for c in cards))

    f = manifest["derived_fixtures"]
    m = f["openai_math"]
    check("openai_ratios",
          Q(m["manuscripts"], m["problems_posed_approx"]) == Q(m["manuscripts_per_problem"])
          and Q(m["families"], m["problems_posed_approx"]) == Q(m["families_per_problem"])
          and Q(m["lean_main_results"], m["manuscripts"]) == Q(m["lean_share_of_manuscripts"])
          and Q(m["problems_posed_approx"], m["families"]) == Q(m["problems_per_family"]),
          scope="Ratios of reported counts; the problem count is approximate in the source")
    check("openai_swarm_scale",
          m["swarm_agents"] * m["swarm_hours"] == m["swarm_agent_hours_upper_bound"]
          and Q(m["output_tokens"], m["messages"]) == Q(m["tokens_per_message"]),
          tokens_per_message=float(Q(m["tokens_per_message"])))

    a = f["anthropic_index"]
    check("amdahl_ceiling_for_leads_share",
          1 / (1 - Q(a["leads_share"])) == Q(a["amdahl_ceiling_if_leads_share_free"]),
          scope="Illustrative; post-automation person-time is not a pre-automation time share")
    check("judge_agrees_with_humans_more_than_humans_agree",
          Q(a["exact_agreement_model_human"]) > Q(a["exact_agreement_human_human"])
          and a["leaves"] < a["nodes"])

    t = f["metr"]
    hours = Q(t["top_frontier_minutes"]) / 60
    check("top_frontier_point_above_stated_ceiling",
          hours == Q(t["top_frontier_hours"]) and hours > t["stated_reliable_ceiling_hours"]
          and t["exceeds_ceiling"], hours=float(hours))

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
    variance = sum(v * v for v in d["ale_pm"])
    z_squared = Q(d["ale_contrast"] ** 2, variance)
    check("ale_contrast_below_conventional_threshold_if_independent_standard_errors",
          variance == d["ale_combined_variance"] and z_squared == Q(d["ale_z_squared"])
          and (z_squared < Q(196, 100) ** 2) == d["ale_below_1_96_if_independent_standard_errors"],
          z_squared=float(z_squared), scope="Conditional on what the plus-or-minus figures denote")
    check("reward_hacking_counts_consistent_with_rounded_percentages",
          all(round(100 * Q(count, d["reward_hacking_pairs"])) == pct
              for count, pct in zip(d["reward_hacking_counts_inferred"],
                                    d["reward_hacking_percentages"])),
          scope="Counts are inferred from rounding, not reported")

    p = f["princeton"]
    check("princeton_sample_is_two_questions",
          p["questions"] == len(p["scores"]) == 2 and p["runs"] == 5
          and all(1 <= s <= p["scale_max"] for s in p["scores"]))
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "configs/rsi_claim_cards.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest_bytes = args.manifest.read_bytes()
    checks = verify(json.loads(manifest_bytes))
    report = {
        "schema_version": "0.1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_status": "manifest_structure_and_exact_derived_arithmetic_only",
        "model_evaluations_run": 0,
        "sources_verified_line_by_line": False,
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
