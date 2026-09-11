"""Exact defensive toy accounting audits; no node, wallet, or network access.

Run with the original project's Python environment and --source-root pointing to
the unmodified repository.  Enumeration cells are not independent observations.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import platform
import sys
from dataclasses import asdict, replace
from fractions import Fraction
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("evidence.json"))
    parser.add_argument("--testnet-replay", type=Path,
                        default=Path(__file__).parents[1] / "testnet4" / "results")
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(args.source_root / "src"))
    from spiral_ln.bonding import RewardClaim, ServiceRecord, settle_bond, sybil_invariant_rewards
    from spiral_ln.hive_lab import DesignTropes, HiveEconomyEnv, HiveLabConfig, PrivateRelationship

    pool = 100_000
    competitor = RewardClaim("reference", "reference-resource", 100_000, 0.5)
    fixed_weight_controls = []
    for identities in (1, 2, 4, 8, 16, 32):
        claims = [RewardClaim(f"subject-{i}", "subject-resource", 100_000, 0.5) for i in range(identities)]
        rewards = sybil_invariant_rewards([competitor, *claims], pool)
        total = sum(rewards[c.identity_id] for c in claims)
        assert total == 50_000
        fixed_weight_controls.append({"identity_count": identities, "coalition_reward": total})

    # A source-weight estimator that maximizes identity-level noisy observations
    # changes the premise of the identity-invariance theorem. Exact Bernoulli
    # enumeration collapses to two sufficient cases: at least one 1, or all 0.
    score_selection = []
    for observations in (1, 2, 4, 8, 16, 32):
        probabilities = {0: Fraction(1, 2) ** observations, 1: 1 - Fraction(1, 2) ** observations}
        expectation = Fraction(0)
        for observed_maximum, probability in probabilities.items():
            claims = [RewardClaim(f"subject-{i}", "subject-resource", 100_000,
                                  observed_maximum if i == 0 else 0) for i in range(observations)]
            rewards = sybil_invariant_rewards([competitor, *claims], pool)
            expectation += probability * sum(rewards[c.identity_id] for c in claims)
        score_selection.append({"independent_identity_observations": observations,
                                "true_success_probability_each": 0.5,
                                "expected_selected_score": float(probabilities[1]),
                                "exact_expected_reward": str(expectation),
                                "expected_reward": float(expectation)})

    mixed_claims = [RewardClaim("a", "subject-resource", 100, 0.1),
                    RewardClaim("b", "subject-resource", 50, 1.0),
                    RewardClaim("reference", "reference-resource", 100, 1.0)]
    mixed_reward = sybil_invariant_rewards(mixed_claims, 120)
    mixed = {"claims": [asdict(c) for c in mixed_claims],
             "implemented_source_weight": 100.0,
             "largest_attested_claim_product": 50.0,
             "implemented_subject_reward": mixed_reward["a"] + mixed_reward["b"],
             "reward_if_weight_were_maximum_claim_product": 40}
    assert mixed["implemented_subject_reward"] == 60

    rounding_claims = [RewardClaim(c, c, 1, 1.0) for c in ("a", "b", "c")]
    rounding_claims.append(RewardClaim("z", "z", 1, 0.0))
    rounding = {"pool": 2, "rewards": sybil_invariant_rewards(rounding_claims, 2),
                "zero_score_identity": "z"}
    assert rounding["rewards"]["z"] == 2

    valid_record = ServiceRecord("service", "source", 25_000, 100, 100, 500_000, 500_000, 0)
    idle_record = replace(valid_record, attempted_volume=0, delivered_volume=0)
    invalid_record = replace(valid_record, available_steps=120)
    invalid_settlement = settle_bond(invalid_record)
    assert invalid_settlement.slashed < 0 and invalid_settlement.released > 25_000
    record_domain = {"valid": asdict(settle_bond(valid_record)),
                     "idle": asdict(settle_bond(idle_record)),
                     "invalid_input": asdict(invalid_record),
                     "invalid_output": asdict(invalid_settlement)}

    # Two worlds with identical observed contract records but different external
    # incremental surplus cannot be separated by any function of those records.
    observability = {"common_observed_record": asdict(valid_record),
                     "common_score": settle_bond(valid_record).score,
                     "worlds": [{"name": "externally_valuable_service", "external_incremental_surplus_units": 10_000},
                                {"name": "no_incremental_external_service", "external_incremental_surplus_units": 0}],
                     "assumed_common_real_resource_cost_units": 1_000,
                     "net_social_values_units": [9_000, -1_000],
                     "claim": "aggregate service records do not identify incremental social value"}

    # A white-box fixture bypasses relationship learning to isolate investment
    # accounting. It does not claim that this coalition emerged spontaneously.
    env = HiveEconomyEnv("hive_reinvestment", seed=17,
                        config=HiveLabConfig(initial_wealth=10_000, rounds=1))
    candidates = [(a, b) for a in env.agents for b in env.agents
                  if a < b and a[0] != b[0] and frozenset((a, b)) not in env.network.channels]
    left, right = candidates[0]
    third = next(a for a in env.agents if a not in (left, right))
    for a, b in itertools.combinations(sorted((left, right, third)), 2):
        env.relationships[(a, b)] = PrivateRelationship(a, b, interactions=4,
            successful_payments=4, delivered_value=4_000, trust=0.9,
            a_to_b_interactions=2, b_to_a_interactions=2)
    before_liquid = sum(a.wealth for a in env.agents.values())
    before_capacity = env.network.total_capacity
    env._maybe_invest_connector()
    assert len(env.investments) == 1
    investment = env.investments[0]
    collateral = {"fixture": "explicit mature three-member relationship, endpoints have principal only",
                  "investment": asdict(investment),
                  "liquid_debit": before_liquid - sum(a.wealth for a in env.agents.values()),
                  "capacity_increment": env.network.total_capacity - before_capacity,
                  "declared_bond_from_source_rule": max(1, investment.capital // 5),
                  "recorded_investment_total": sum(a.invested for a in env.agents.values()),
                  "ending_endpoint_liquid": {a: env.agents[a].wealth for a in investment.endpoints},
                  "reported_accounting_error": env.result().accounting_error}
    assert collateral["liquid_debit"] == 20_000
    assert collateral["reported_accounting_error"] == 0
    assert collateral["declared_bond_from_source_rule"] == 4_000

    # Programmed income sensitivity, paired random streams and fixed explicit
    # coalition. No endogenous learning, policy search, or model calls occur.
    bonus_rows = []
    for size in (1, 3, 5):
        for bonus in (0.0, 0.08):
            bonus_env = HiveEconomyEnv("hive_reinvestment", seed=23,
                config=HiveLabConfig(rounds=1, external_job_probability=1,
                                     coordination_income_bonus=bonus),
                tropes=DesignTropes(coordination_bonus=True))
            members = set(list(bonus_env.agents)[:size])
            bonus_env.hives = lambda members=members: [members] if len(members) >= 3 else []
            bonus_env._earn_external_income()
            bonus_rows.append({"fixed_coalition_size": size, "configured_bonus": bonus,
                               "external_income": bonus_env.external_income,
                               "multiplier": 1 + bonus * min(4, size - 1) if size >= 3 else 1})
    assert bonus_rows[0]["external_income"] == bonus_rows[2]["external_income"] == bonus_rows[4]["external_income"]

    # Eight abstract resource-service epochs, one preselected intervention. The
    # last observed warmup region is 0. Markov demand stays in its previous
    # region with rho. Every possible future is enumerated, not sampled.
    # Delay epochs use no service and incur a fixed funding opportunity cost.
    horizon = 8
    persistence_rows = []
    for rho in (Fraction(0), Fraction(1, 4), Fraction(1, 2), Fraction(3, 4), Fraction(1)):
        for delay in (0, 2, 4, 8):
            expected_targeted = Fraction(0)
            expected_random = Fraction(0)
            mass = Fraction(0)
            for trajectory in itertools.product((0, 1), repeat=horizon):
                probability = Fraction(1)
                previous = 0
                for region in trajectory:
                    probability *= rho if region == previous else 1 - rho
                    previous = region
                mass += probability
                targeted = sum(region == 0 for region in trajectory[delay:])
                expected_targeted += probability * targeted
                expected_random += probability * Fraction(horizon - delay, 2)
            assert mass == 1
            persistence_rows.append({"stay_probability": float(rho), "delay_epochs": delay,
                "expected_targeted_service": float(expected_targeted),
                "expected_random_service": float(expected_random),
                "targeted_minus_random": float(expected_targeted - expected_random),
                "exact_targeted_minus_random": str(expected_targeted - expected_random)})

    # Illustrative accounting only. No market-price or testnet fee estimates.
    # Principal is not expensed: the opportunity cost of principal AND posted
    # collateral is included separately from fixed lifecycle resource costs.
    cost_rows = []
    capital, bond, horizon_days = 120_000, 24_000, 30
    for annual_rate in (0.0, 0.12):
        for fixed_cost in (0, 2_000):
            cost = Fraction(fixed_cost) + Fraction(capital + bond) * Fraction(str(annual_rate)) * Fraction(horizon_days, 365)
            for additional_services in (1, 10, 100):
                cost_rows.append({"capital_units": capital, "bond_units": bond,
                    "horizon_days": horizon_days, "annual_opportunity_rate": annual_rate,
                    "fixed_lifecycle_cost_units": fixed_cost,
                    "additional_external_services": additional_services,
                    "total_resource_cost_units": float(cost),
                    "break_even_external_surplus_per_service_units": float(cost / additional_services),
                    "net_value_if_surplus_is_100_units_each": float(100 * additional_services - cost)})

    replay = json.loads((args.testnet_replay / "summary.json").read_text(encoding="utf-8"))
    header_path = args.testnet_replay / "headers.csv"
    assert digest(header_path) == replay["headers_csv_sha256"]
    with header_path.open(encoding="utf-8", newline="") as handle:
        headers = list(csv.DictReader(handle))
    assert len(headers) == replay["header_count"] == 512
    assert all(current["previous"] == previous["hash"]
               and int(current["height"]) == int(previous["height"]) + 1
               for previous, current in zip(headers, headers[1:]))
    assert headers[-1]["hash"] == replay["tip_hash"]
    replay_costs = []
    for row in replay["settlement_scenarios"]:
        replay_costs.append({"horizon_blocks": row["horizon_blocks"],
                            "depth_gate": row["depth"],
                            "assumed_inclusion_lag_blocks": row["inclusion_lag_blocks"],
                            "synthetic_delivered": row["delivered"],
                            "hypothetical_receipt_per_delivery_units": 1_000,
                            "hypothetical_fixed_operator_cost_units": 2_000,
                            "operator_net_receipt_units": row["delivered"] * 1_000 - 2_000})
    testnet_accounting = {"replay_summary_sha256": digest(args.testnet_replay / "summary.json"),
                         "headers_csv_sha256": digest(header_path),
                         "verified_parent_links": len(headers) - 1,
                         "first_height": int(headers[0]["height"]),
                         "last_height": int(headers[-1]["height"]),
                         "scope": "historical public-header ordering, synthetic depth gates and receipts; no live LN",
                         "timestamp_used_as_clock": False,
                         "observed_funding_transactions": False,
                         "empirical_market_prices": False,
                         "scenario_rows_are_independent_replications": False,
                         "cost_rows": replay_costs}

    tracked = ["paper/manuscript.md", "paper/hive_lab.md", "src/spiral_ln/bonding.py",
               "src/spiral_ln/hive_lab.py", "src/spiral_ln/algebra.py",
               "src/spiral_ln/public_topology_eval.py"]
    evidence = {"schema": "spiral-incentive-cross-examination/v1", "python": platform.python_version(),
        "source_root": str(args.source_root.resolve()), "source_sha256": {p: digest(args.source_root / p) for p in tracked},
        "script_sha256": digest(Path(__file__)),
        "execution_scope": {"unmodified_original_implementation": True, "synthetic_only": True,
            "autonomous_llm_agent_runs": False, "node_or_wallet_access": False,
            "network_access": False, "transaction_broadcast": False},
        "fixed_weight_identity_invariance": fixed_weight_controls,
        "max_score_selection_sensitivity": score_selection,
        "independent_maximum_mismatch": mixed,
        "zero_weight_rounding": rounding,
        "service_record_domain": record_domain,
        "social_value_nonidentifiability": observability,
        "unfunded_bond_fixture": collateral,
        "programmed_coordination_bonus": bonus_rows,
        "exact_markov_persistence_and_delay": persistence_rows,
        "illustrative_cost_sensitivity": cost_rows,
        "testnet4_ordinal_settlement_accounting": testnet_accounting,
        "verification": {"assertions_passed": True, "exact_future_trajectories_per_cell": 256,
            "trajectory_count_is_not_statistical_sample_size": True}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()),
                      "evidence_sha256": digest(args.output),
                      "identity_control_reward": 50_000,
                      "unfunded_declared_bond": collateral["declared_bond_from_source_rule"],
                      "assertions_passed": True}))


if __name__ == "__main__":
    main()
