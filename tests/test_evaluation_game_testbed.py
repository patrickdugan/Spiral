from fractions import Fraction as Q

from spiral_ln.evaluation_game_testbed import (
    baseline_gain_fixture, exploitability_fixture, incentive_design_fixture,
    observation_hide_fixture, pre_action_hide_fixture, robust_regret_fixture,
    verify, zero_sum_primal_dual_fixture,
)


def test_estimands_are_separate_exact_quantities():
    assert baseline_gain_fixture()["baseline_gain"] == Q(1, 2)
    assert robust_regret_fixture()["robust_regret"] == Q(1, 2)
    assert baseline_gain_fixture()["candidate_value"] == 1


def test_observation_only_hide_is_a_common_post_play_kernel():
    result = observation_hide_fixture()
    assert result["acts_after_players_act"]
    assert not result["changes_player_information"]
    assert result["visible_discrimination_gap"] == Q(1)
    assert result["hidden_discrimination_gap"] == Q(0)
    assert result["data_processing_holds"]


def test_pre_action_hiding_is_distinct_game_change():
    assert pre_action_hide_fixture()["game_change_value_loss"] == Q(1, 2)


def test_strategic_reporting_separates_rule_set_and_restricted_search():
    result = exploitability_fixture()
    assert result["equilibrium_set"] == (("take", "take"),)
    assert result["selected_outcome"] == ("take", "take")
    assert result["exact_exploitability"] == Q(2)
    assert result["restricted_best_response_lower_bound"] == Q(0)
    assert result["restricted_is_lower_bound"]


def test_zero_sum_fixture_has_primal_dual_certificate():
    result = zero_sum_primal_dual_fixture()
    assert result["primal_maximin_witness"] == result["dual_minimax_witness"] == Q(0)


def test_incentive_design_has_explicit_nuisance_cost_holdout_and_falsifier():
    result = incentive_design_fixture()
    assert result["matched_within"] == ("difficulty", "grader")
    assert result["planned_score_operations"] == 96
    assert result["arithmetic_score_values"] == 8
    assert result["allocation_optimizes_equal_variance_contrast"]
    assert result["held_out_incentive_by_difficulty_interaction"] == Q(1, 5)
    assert not result["intent_identified"]
    assert "invalidates" in result["falsifier"]


def test_exact_fixture_suite_passes():
    assert verify()["all_passed"]
