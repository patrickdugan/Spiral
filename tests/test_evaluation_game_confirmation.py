from dataclasses import replace
from fractions import Fraction as Q
from itertools import product

import pytest

from spiral_ln.evaluation_game_testbed import _pushforward, _tv
from spiral_ln.evaluation_game_confirmation import (
    adaptation_fixture, confirm, optimal_allocation, run_confirmation_fixture,
    select_training, synthetic_rows, two_sided_sign_p, zero_sum_certificate,
)


def test_common_binary_channels_contract_tv_over_rational_grid():
    grid = [Q(i, 4) for i in range(5)]
    for p, q, a, b in product(grid, repeat=4):
        left, right = {"x": p, "y": 1-p}, {"x": q, "y": 1-q}
        channel = {"x": {"u": a, "v": 1-a}, "y": {"u": b, "v": 1-b}}
        assert _tv(_pushforward(left, channel), _pushforward(right, channel)) <= _tv(left, right)


@pytest.mark.parametrize("channel", [{}, {"x": {}}, {"x": {"u": Q(1, 2)}},
                                      {"x": {"u": Q(2), "v": Q(-1)}}])
def test_invalid_hide_kernels_rejected(channel):
    with pytest.raises(ValueError):
        _pushforward({"x": Q(1)}, channel)


def test_different_channels_can_manufacture_discrimination():
    same = {"x": Q(1)}
    left = _pushforward(same, {"x": {"u": Q(1)}})
    right = _pushforward(same, {"x": {"v": Q(1)}})
    assert _tv(same, same) == 0 and _tv(left, right) == 1


def test_primal_dual_witnesses_detect_suboptimal_strategy():
    game = ((Q(1), Q(-1)), (Q(-1), Q(1)))
    uniform = (Q(1, 2), Q(1, 2))
    assert zero_sum_certificate(game, uniform, uniform)["optimality_certified"]
    failed = zero_sum_certificate(game, (Q(1), Q(0)), uniform)
    assert failed["duality_gap"] == 1 and not failed["optimality_certified"]
    with pytest.raises(ValueError, match="probability"):
        zero_sum_certificate(game, (Q(2), Q(-1)), uniform)


def test_adaptation_rule_changes_outcome_despite_identical_nash_set():
    result = adaptation_fixture()
    assert len(result["equilibrium_set"]) == 3
    assert result["simultaneous"]["path"] == [(0, 1), (1, 0), (0, 1), (1, 0), (0, 1)]
    assert result["sequential"]["path"][-1] == (1, 1)
    assert result["simultaneous"]["last_payoffs"] != result["sequential"]["last_payoffs"]


def test_allocation_responds_to_variance_and_cost_and_matches_exhaustion():
    weights, variances, costs = (Q(1, 2), Q(1, 2)), (Q(4), Q(1)), (2, 3)
    result = optimal_allocation(weights, variances, costs, 24, minimum=2)
    exhaustive = min((sum(w*w*v/n for w, v, n in zip(weights, variances, (a, b))), (a, b))
                     for a in range(2, 13) for b in range(2, 9) if 2*a+3*b <= 24)
    assert (result["contrast_variance"], result["counts"]) == exhaustive
    assert result["counts"][0] > result["counts"][1]
    equal = optimal_allocation((Q(1, 4),)*4, (Q(1),)*4, (2,)*4, 96)
    assert equal["counts"] == (12, 12, 12, 12)
    with pytest.raises(ValueError, match="minimum"):
        optimal_allocation(weights, variances, costs, 4)


def sample():
    train = synthetic_rows("planning", "training", 8, (Q(1, 10), Q(3, 10)))
    selection = select_training(train)
    holdout = synthetic_rows("planning", "confirmation", 12, (Q(1, 10), Q(3, 10)))
    holdout += synthetic_rows("planning", "confirmation", 12, (Q(0), Q(0)), True)
    return train, selection, holdout


def test_confirmation_costs_and_exact_sign_interaction():
    report = run_confirmation_fixture()
    assert report["family"] == "planning"
    assert report["contrasts"]["incentive_by_difficulty"]["block_mean"] == Q(1, 5)
    assert report["contrasts"]["incentive_by_difficulty"]["block_sign_p"] == Q(1, 2048)
    assert report["total_score_operations"] == 320
    assert report["training_score_operations"] == 128
    assert report["confirmation_score_operations"] == 192
    assert report["fixture_interaction_supported"] and not report["intent_identified"]


def test_training_only_effect_does_not_confirm():
    _, selection, rows = sample()
    rows = [replace(r, incentive_score=r.control_score) for r in rows]
    report = confirm(selection, rows)
    assert not report["fixture_interaction_supported"]
    assert report["contrasts"]["incentive_by_difficulty"]["block_sign_p"] == 1


def test_grader_nuisance_cancels_but_condition_specific_control_bias_falsifies():
    _, selection, rows = sample()
    changed = [replace(r, control_score=r.control_score-Q(1, 20),
                       incentive_score=r.incentive_score-Q(1, 20))
               if r.grader == "strict" else r for r in rows]
    assert confirm(selection, changed) == confirm(selection, rows)
    biased = [replace(r, incentive_score=r.incentive_score-Q(1, 20))
              if r.negative_control else r for r in rows]
    assert not confirm(selection, biased)["fixture_interaction_supported"]


def test_selection_and_confirmation_input_order_invariance():
    train, selection, rows = sample()
    assert select_training(list(reversed(train))) == selection
    assert confirm(selection, list(reversed(rows))) == confirm(selection, rows)


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "overlap", "wrong_family", "training"])
def test_confirmation_rejects_structural_leakage(mutation):
    train, selection, rows = sample()
    if mutation == "duplicate":
        rows += [rows[0]]
    elif mutation == "missing":
        rows.pop()
    elif mutation == "overlap":
        old = rows[0].block_id
        rows = [replace(r, block_id=train[0].block_id) if r.block_id == old else r for r in rows]
    elif mutation == "wrong_family":
        rows = [replace(r, family="other") for r in rows]
    else:
        rows = [replace(r, split="training") for r in rows]
    with pytest.raises(ValueError):
        confirm(selection, rows)


def test_confirmation_data_cannot_enter_selection():
    _, _, rows = sample()
    with pytest.raises(ValueError, match="training"):
        select_training(rows)


def test_sign_test_does_not_report_precision_from_ties():
    assert two_sided_sign_p([Q(0)]*100) == 1
    assert two_sided_sign_p([Q(1)]*3) == Q(1, 4)
    assert two_sided_sign_p([Q(1), Q(-1)]*6) == 1
