"""Check atlas structure and derived arithmetic without loading Prime packages."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction as Q
from hashlib import sha256
import json
from math import comb
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def expected_curriculum(n: int, p: Q) -> Q:
    """Exhaust the binomial count distribution for a fixed valid problem."""
    return sum(
        Q(comb(n, k)) * p ** k * (1 - p) ** (n - k)
        * 4 * Q(k, n) * (1 - Q(k, n))
        for k in range(n + 1)
    )


def verify(manifest):
    checks = []

    def check(name, passed, **evidence):
        checks.append({"name": name, "passed": bool(passed), "evidence": evidence})

    cards = manifest["cards"]
    check("nine_distinct_design_cards", len(cards) == 9 and len({c["id"] for c in cards}) == 9)
    hub_sources = [s for c in cards for s in c["sources"]
                   if s["kind"] == "live_hub_specification"]
    check("nine_versioned_hub_packages",
          len({s["slug"] for s in hub_sources}) == manifest["hub_packages"] == 9
          and all(s["version"] for s in hub_sources))
    check("eight_hub_cases_one_source_only_case",
          sum(any(s["kind"] == "live_hub_specification" for s in c["sources"])
              for c in cards) == manifest["hub_cases"] == 8
          and manifest["source_only_cases"] == 1)
    source_recipes = [s for c in cards for s in c["sources"]
                      if s["kind"] == "inspected_source_recipe"]
    check("source_recipes_pinned_and_not_claimed_published",
          bool(source_recipes) and all(
              s["commit"] == manifest["source_commit"]
              and not s["hub_publication_verified"] for s in source_recipes))
    check("all_studies_explicitly_proposed",
          manifest["model_evaluations_run"] == 0
          and all(c["study_status"] == "proposed_not_executed" for c in cards))
    check("cards_include_interpretation_and_sampling_contract",
          all(c["independent_unit"] and c["claim_boundary"] and c["hold_fixed"]
              and c["estimands"] and c["proposed_axes"] for c in cards))

    fixtures = manifest["derived_fixtures"]
    stub = fixtures["poker_stub"]
    rewards = {
        action: Q(stub["format_weight"]) * Q(stub["valid_format_score"])
        + Q(stub["poker_weight"]) * Q(value)
        for action, value in stub["action_rewards"].items()
    }
    check("documented_poker_stub_totals",
          all(value == Q(stub["expected_totals"][action]) for action, value in rewards.items()),
          totals={key: str(value) for key, value in rewards.items()})
    check("constant_raise_maximizes_stub",
          rewards["raise"] > rewards["call"] > rewards["fold"],
          scope="Documented fallback arithmetic; no simulator or model run")

    tile = fixtures["tile_progress"]
    high, target = tile["highest_tile"], tile["target_tile"]
    if min(high, target) <= 1 or high & (high - 1) or target & (target - 1):
        raise ValueError("This exact fixture expects powers of two larger than one")
    progress = min(Q(1), Q(high.bit_length() - 1, target.bit_length() - 1))
    composite = Q(tile["completion_weight"]) * progress + Q(tile["perfect_auxiliary_total"])
    check("high_2048_composite_without_target_attainment",
          high < target and composite == Q(tile["expected_composite"]),
          tile_progress=str(progress), composite=str(composite), target_reached=high >= target)

    curriculum = fixtures["proposer_sample_count"]
    p = Q(curriculum["true_success_probability"])
    for n_raw, expected in curriculum["expected_mean_rewards"].items():
        n = int(n_raw)
        exact = expected_curriculum(n, p)
        check(f"curriculum_expected_reward_n{n}", exact == Q(expected),
              expected_reward=str(exact), true_success_probability=str(p))
    check("curriculum_bias_identity_finite_instances",
          all(expected_curriculum(n, chance) == 4 * chance * (1 - chance) * (1 - Q(1, n))
              for n in (1, 2, 4, 8) for chance in (Q(1, 4), Q(1, 2), Q(3, 4))),
          instance_count=12, assumptions="Fixed problem; conditionally iid Bernoulli outcomes")
    correction = Q(4, 3) * 4 * Q(1, 2) * (1 - Q(1, 2))
    check("unbiased_curriculum_diagnostic_can_exceed_one", correction > 1,
          n=4, observed_successes=2, corrected_observation=str(correction))

    # Illustrative correctness-gated threshold curve; these are invented artifacts.
    artifacts = [(True, Q(6, 5)), (True, Q(12, 5)), (False, Q(10))]
    curve = {s: Q(sum(correct and speedup > s for correct, speedup in artifacts), len(artifacts))
             for s in (Q(1), Q(2), Q(3))}
    check("synthetic_correctness_gated_speedup_curve",
          list(curve.values()) == [Q(2, 3), Q(1, 3), Q(0)],
          values={str(k): str(v) for k, v in curve.items()},
          scope="Synthetic arithmetic; not KernelBench observations")
    check("zero_sum_seat_average_is_uninformative",
          all(Q(payoff - payoff, 2) == 0 for payoff in (-2, -1, 1, 2)),
          scope="Algebraic property of zero-sum signed seat payoffs")
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path,
                        default=ROOT / "configs/prime_intellect_eval_cards.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest_bytes = args.manifest.read_bytes()
    checks = verify(json.loads(manifest_bytes))
    report = {
        "schema_version": "0.1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_status": "manifest_structure_and_exact_derived_arithmetic_only",
        "model_evaluations_run": 0,
        "third_party_packages_executed": False,
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
