"""Exact, synthetic checks for evaluation-game estimands and acquisition design.

Nothing in this module calls a model, grades a transcript, or infers intent.  It
uses finite rational fixtures to keep four quantities that are often called an
"evaluation result" separate: baseline gain, robust regret, measurement
discrimination, and strategic exploitability.
"""

from __future__ import annotations

from fractions import Fraction as Q
from itertools import product
from typing import Iterable


def _tv(left: dict[str, Q], right: dict[str, Q]) -> Q:
    """Total variation distance of two finite distributions."""

    return sum(abs(left.get(key, Q(0)) - right.get(key, Q(0)))
               for key in set(left) | set(right)) / 2


def _pushforward(distribution: dict[str, Q], kernel: dict[str, dict[str, Q]]) -> dict[str, Q]:
    """Apply a common finite Markov kernel to an already-produced record."""

    if not distribution or sum(distribution.values()) != 1 or min(distribution.values()) < 0:
        raise ValueError("distribution must be nonnegative and sum to one")
    if not set(distribution) <= set(kernel):
        raise ValueError("kernel is missing a source record")
    if any(not row or sum(row.values()) != 1 or min(row.values()) < 0
           for row in kernel.values()):
        raise ValueError("every kernel row must be nonnegative and sum to one")
    output: dict[str, Q] = {}
    for source, mass in distribution.items():
        for target, probability in kernel[source].items():
            output[target] = output.get(target, Q(0)) + mass * probability
    return output


def _optimal_decision_value(
    states: tuple[str, ...], prior: dict[str, Q], actions: tuple[str, ...],
    observation_kernel: dict[str, dict[str, Q]],
) -> Q:
    """Exhaustively optimize a one-step decision rule respecting observations."""

    observations = tuple(sorted({o for row in observation_kernel.values() for o in row}))
    best = Q(-1)
    for response in product(actions, repeat=len(observations)):
        policy = dict(zip(observations, response))
        value = sum(
            prior[state] * probability * int(policy[observation] == state)
            for state in states
            for observation, probability in observation_kernel[state].items()
        )
        best = max(best, value)
    return best


def baseline_gain_fixture() -> dict[str, Q]:
    """Compare two policies in the same revealed-state game and case law."""

    states = ("left", "right")
    prior = {"left": Q(1, 2), "right": Q(1, 2)}
    revealed = {state: {state: Q(1)} for state in states}
    # Both receive the revealed state; only the candidate uses it.
    baseline = sum(prior[state] * int(state == "left") for state in states)
    candidate = _optimal_decision_value(states, prior, states, revealed)
    return {"baseline_value": baseline, "candidate_value": candidate,
            "baseline_gain": candidate - baseline}


def robust_regret_fixture() -> dict[str, object]:
    """Worst-case opportunity loss of one frozen policy over a stated case set."""

    cases = ({"left": Q(3, 4), "right": Q(1, 4)},
             {"left": Q(1, 4), "right": Q(3, 4)})
    candidate = "left"
    regrets = []
    for prior in cases:
        candidate_value = prior[candidate]
        oracle_value = max(prior.values())
        regrets.append(oracle_value - candidate_value)
    return {"candidate_policy": candidate, "case_regrets": tuple(regrets),
            "robust_regret": max(regrets)}


def observation_hide_fixture() -> dict[str, object]:
    """Show that post-play Hide is a common acquisition kernel, not a game edit."""

    # Two completed traces differ before the evaluator observes them.  The
    # evaluator's Hide kernel is identical for both policies and is applied only
    # after play, so neither actions nor payoff can change.
    policy_a = {"correct": Q(1)}
    policy_b = {"wrong": Q(1)}
    hide = {"correct": {"redacted": Q(1)}, "wrong": {"redacted": Q(1)}}
    visible_gap = _tv(policy_a, policy_b)
    hidden_a, hidden_b = _pushforward(policy_a, hide), _pushforward(policy_b, hide)
    hidden_gap = _tv(hidden_a, hidden_b)
    return {
        "operator_type": "observation_only_common_markov_kernel",
        "visible_discrimination_gap": visible_gap,
        "hidden_discrimination_gap": hidden_gap,
        "same_kernel_for_all_policies": True,
        "acts_after_players_act": True,
        "changes_player_information": False,
        "data_processing_holds": hidden_gap <= visible_gap,
    }


def pre_action_hide_fixture() -> dict[str, Q]:
    """Contrast a player-observation intervention, which changes the game."""

    states = ("left", "right")
    prior = {"left": Q(1, 2), "right": Q(1, 2)}
    revealed = {state: {state: Q(1)} for state in states}
    hidden = {state: {"hidden": Q(1)} for state in states}
    before_hide = _optimal_decision_value(states, prior, states, revealed)
    after_hide = _optimal_decision_value(states, prior, states, hidden)
    return {"pre_action_revealed_value": before_hide,
            "pre_action_hidden_value": after_hide,
            "game_change_value_loss": before_hide - after_hide}


def exploitability_fixture() -> dict[str, object]:
    """Exact strategic checks, including a deliberately restricted lower bound."""

    actions = ("share", "take")
    payoff = {
        ("share", "share"): (Q(3), Q(3)), ("share", "take"): (Q(0), Q(5)),
        ("take", "share"): (Q(5), Q(0)), ("take", "take"): (Q(1), Q(1)),
    }

    def gaps(profile: tuple[str, str], allowed: Iterable[str] = actions) -> tuple[Q, Q]:
        a, b = profile
        base = payoff[profile]
        return (
            max(payoff[(alternative, b)][0] for alternative in allowed) - base[0],
            max(payoff[(a, alternative)][1] for alternative in allowed) - base[1],
        )

    equilibrium_set = tuple(profile for profile in product(actions, repeat=2)
                            if gaps(profile) == (Q(0), Q(0)))
    profile = ("share", "share")
    exact_gaps = gaps(profile)
    restricted_gaps = gaps(profile, ("share",))
    return {
        "adaptation_rule": "enumerate_pure_nash_then_lexicographically_select",
        "equilibrium_set": equilibrium_set,
        "selected_outcome": min(equilibrium_set),
        "profile_evaluated": profile,
        "exact_exploitability": max(exact_gaps),
        "restricted_best_response_lower_bound": max(restricted_gaps),
        "restricted_is_lower_bound": max(restricted_gaps) <= max(exact_gaps),
    }


def zero_sum_primal_dual_fixture() -> dict[str, Q]:
    """Primal/dual certificate for a tiny zero-sum game, not a generic LP solver."""

    # Matching pennies for the row player.  p=q=1/2 makes every pure response
    # worth zero, certifying maximin >= 0 and minimax <= 0 respectively.
    row_minimum = min(Q(1, 2) * Q(1) + Q(1, 2) * Q(-1),
                      Q(1, 2) * Q(-1) + Q(1, 2) * Q(1))
    column_maximum = max(Q(1, 2) * Q(1) + Q(1, 2) * Q(-1),
                         Q(1, 2) * Q(-1) + Q(1, 2) * Q(1))
    return {"primal_maximin_witness": row_minimum,
            "dual_minimax_witness": column_maximum,
            "certified_value": Q(0)}


def incentive_design_fixture() -> dict[str, object]:
    """Difficulty-matched, severity-stratified synthetic contrast and holdout.

    The outcome law has *no latent intent variable*.  It is only a design check:
    within a difficulty/severity stratum, matched control minus incentive score
    estimates an incentive-response contrast while cancelling additive nuisance
    difficulty and grader-severity terms.
    """

    difficulty_base = {"easy": Q(9, 10), "hard": Q(7, 10)}
    severity = {"lenient": Q(0), "strict": Q(-1, 10)}
    incentive_drop = {"easy": Q(1, 10), "hard": Q(3, 10)}
    rows = []
    for difficulty, grader in product(difficulty_base, severity):
        control = difficulty_base[difficulty] + severity[grader]
        incentive = control - incentive_drop[difficulty]
        rows.append({"split": "held_out", "difficulty": difficulty, "grader": grader,
                     "control_score": control, "incentive_score": incentive,
                     "paired_gap": control - incentive})
    by_difficulty = {
        difficulty: sum(r["paired_gap"] for r in rows if r["difficulty"] == difficulty)
        / sum(r["difficulty"] == difficulty for r in rows)
        for difficulty in difficulty_base
    }
    # Equal target weights over difficulty and grading severity.  Every matched
    # pair costs two scored responses; 12 pairs in each of four nuisance strata
    # costs 96 score operations.  This is a transparent balanced allocation,
    # not a claim that it is universally optimal under unknown variances.
    allocation = {f"{difficulty}:{grader}": 12
                  for difficulty, grader in product(difficulty_base, severity)}
    # With four equally weighted, equal-variance strata and fixed total cost,
    # the contrast variance is proportional to sum_h (1/4)^2 / n_h.  Enumerate
    # the feasible integer allocations rather than merely asserting balance.
    def objective(counts):
        return sum(Q(1, 16 * count) for count in counts)
    best_objective = min(
        objective((first, second, third, 48-first-second-third))
        for first in range(1, 46)
        for second in range(1, 47-first)
        for third in range(1, 48-first-second)
    )
    allocation_objective = objective(tuple(allocation.values()))
    return {
        "estimand": "held_out_incentive_response_contrast",
        "nuisance_structure": "score = difficulty + grader_severity + incentive + incentive_by_difficulty + noise",
        "matched_within": ("difficulty", "grader"),
        "scope": "four arithmetic cell values; enforced selection and confirmation are in evaluation_game_confirmation",
        "allocation_pairs": allocation,
        "planned_score_operations": 2 * sum(allocation.values()),
        "arithmetic_score_values": 2 * len(rows),
        "allocation_objective": allocation_objective,
        "allocation_objective_minimum": best_objective,
        "allocation_optimizes_equal_variance_contrast": allocation_objective == best_objective,
        "held_out_gaps_by_difficulty": by_difficulty,
        "held_out_incentive_by_difficulty_interaction": by_difficulty["hard"] - by_difficulty["easy"],
        "intent_identified": False,
        "falsifier": "A comparable interaction in negative-incentive controls, prompt inequivalence, or unblinded scoring invalidates the strategic interpretation.",
    }


def verify() -> dict[str, object]:
    """Run all exact fixtures and return machine-readable checks."""

    gain = baseline_gain_fixture()
    regret = robust_regret_fixture()
    observed = observation_hide_fixture()
    player_hide = pre_action_hide_fixture()
    exploit = exploitability_fixture()
    duality = zero_sum_primal_dual_fixture()
    incentive = incentive_design_fixture()
    checks = {
        "baseline_gain_is_half": gain["baseline_gain"] == Q(1, 2),
        "robust_regret_is_half": regret["robust_regret"] == Q(1, 2),
        "observation_hide_is_common_and_contracts_discrimination": observed["same_kernel_for_all_policies"] and observed["data_processing_holds"] and observed["hidden_discrimination_gap"] == Q(0),
        "pre_action_hide_changes_decision_value": player_hide["game_change_value_loss"] == Q(1, 2),
        "restricted_search_is_only_a_lower_bound": exploit["restricted_is_lower_bound"] and exploit["exact_exploitability"] == Q(2),
        "equilibrium_outcome_is_reported_with_rule": exploit["selected_outcome"] == ("take", "take"),
        "primal_dual_witnesses_agree": duality["primal_maximin_witness"] == duality["dual_minimax_witness"] == duality["certified_value"],
        "heldout_incentive_interaction_is_explicit": incentive["held_out_incentive_by_difficulty_interaction"] == Q(1, 5),
        "allocation_is_optimized_for_declared_contrast": incentive["allocation_optimizes_equal_variance_contrast"],
        "incentive_fixture_does_not_identify_intent": not incentive["intent_identified"],
    }
    return {"evidence_status": "exact_synthetic_fixtures_not_model_or_agent_evidence",
            "checks": checks, "all_passed": all(checks.values()),
            "estimands": {"baseline_gain": gain, "robust_regret": regret,
                           "discrimination_gap": observed, "exploitability": exploit},
            "pre_action_hide": player_hide, "primal_dual": duality,
            "incentive_design": incentive}
