from fractions import Fraction as Q
from itertools import product
from math import comb, log, sqrt

import pytest

from spiral_ln.evaluation_game_feedback import selection_inflation
from spiral_ln.evaluation_feedback_multigen import (
    BOUND_TOLERANCE, CROSSING_CELL, NONUNIFORM_LATTICES, best_of_pmf, binomial_cdf,
    brute_force_drift_distribution, brute_force_fresh_reported,
    brute_force_mutation_distribution, brute_force_reuse_distribution,
    ceiling_mass_closed_form, count_dominance_lemma_fixture, coupling_crossing_fixture,
    decaying_gain_schedule, divergence_check,
    dominance_search, drift_absorbing_states, drift_expectations,
    drift_gap_increment_from_one_step, drift_kernel, drift_levels, drift_limit,
    drift_trajectory, false_acceptance_probability, fresh_block_reported,
    fresh_trajectory, gate_threshold, kernel_iterates, late_early_ratio,
    SINGLE_GAIN_LATTICES, SINGLE_GAIN_LAWS, TWO_GAIN_CELL, TWO_GAIN_LAWS, divergence_decomposition,
    gain_support_fixture, integer_iterates, iterate_fraction, rule_dominance_integer, same_level_window,
    single_gain_structure, support_window_screen, two_gain_counterexample,
    mixed_count_structure, mixed_level_structure, mixed_objectives, mixed_window_screen,
    mixed_window_sums, mutation_candidate_law, mutation_state_distribution,
    mutation_trajectory, mutation_transition_kernel, naive_closed_form,
    naive_draw_law, naive_gap_bounds, naive_threshold, one_step_gap_change, phantom_share,
    quantile_coupling_crossing, random_threshold_rules, readout_gap_series, replay_quantile_coupling,
    reuse_trajectory, rule_dominance_check, running_max_from_point, scheduled_rule_dominance_check,
    scheduled_window_screen, state_distribution, threshold_pair_counterexample, threshold_rules,
    transition_kernel, verify, window_sums,
)

HALF, QUARTER = Q(1, 2), Q(1, 4)
Q_GRID = (Q(0), QUARTER, HALF, Q(3, 4), Q(1))


def _pmf(items, p):
    return [Q(comb(items, j)) * p**j * (1 - p)**(items - j) for j in range(items + 1)]


def _count_enumeration(items, candidates, p, threshold, generations):
    """Independent enumeration over count tuples with binomial weights."""

    pmf, distribution = _pmf(items, p), [Q(0)] * (items + 1)
    for counts in product(range(items + 1), repeat=1 + generations * candidates):
        mass = Q(1)
        for j in counts:
            mass *= pmf[j]
        c = counts[0]
        for g in range(generations):
            best = max(counts[1 + g * candidates:1 + (g + 1) * candidates])
            if best > c + threshold[c]:
                c = best
        distribution[c] += mass
    return distribution


def test_binomial_building_blocks_hand_values():
    assert binomial_cdf(2, HALF) == [Q(1, 4), Q(3, 4), Q(1)]
    assert best_of_pmf(2, 2, HALF) == [Q(1, 16), Q(1, 2), Q(7, 16)]
    assert best_of_pmf(2, 1, HALF) == _pmf(2, HALF)
    for items, candidates, p in ((3, 2, QUARTER), (5, 4, Q(2, 3))):
        assert sum(best_of_pmf(items, candidates, p)) == 1


def test_gate_threshold_hand_values_and_floor_inequality():
    assert gate_threshold(16, 3) == (0, 2, 3, 4, 5, 5, 5, 5, 6, 5, 5, 5, 5, 4, 3, 2, 0)
    assert gate_threshold(8, 3) == (0, 2, 3, 4, 4, 4, 3, 2, 0)
    assert gate_threshold(4, 3) == (0, 2, 3, 2, 0)
    assert gate_threshold(2, 2) == (0, 1, 0)
    assert gate_threshold(7, 0) == naive_threshold(7)
    for items in range(1, 21):
        for z in (Q(1, 2), 1, 2, 3):
            for c, t in enumerate(gate_threshold(items, z)):
                q = Q(z)**2 * c * (items - c) / items
                assert t * t <= q < (t + 1) * (t + 1)


def test_gate_threshold_reproduces_sim_rule_on_integer_differences():
    """``d > z sqrt(c (n - c) / n)`` iff ``d > t(c)`` for every integer ``d``."""

    for items, z in ((8, 3), (16, 3), (5, 1)):
        threshold = gate_threshold(items, z)
        for c in range(items + 1):
            q = Q(z)**2 * c * (items - c) / items
            for d in range(items + 1):
                assert (Q(d)**2 > q) == (d > threshold[c])


def test_transition_kernel_hand_values_n2():
    naive = transition_kernel(2, 2, HALF, naive_threshold(2))
    assert naive == [[Q(1, 16), Q(1, 2), Q(7, 16)], [Q(0), Q(9, 16), Q(7, 16)], [Q(0), Q(0), Q(1)]]
    gated = transition_kernel(2, 2, HALF, (0, 1, 0))
    assert gated[0] == naive[0] and gated[1] == [Q(0), Q(1), Q(0)] and gated[2] == naive[2]


@pytest.mark.parametrize("items, candidates, p, z", [
    (4, 2, HALF, 0), (8, 3, QUARTER, 1), (16, 4, HALF, 3), (6, 1, Q(2, 3), 2)])
def test_kernel_is_stochastic_with_only_self_loops_and_upward_edges(items, candidates, p, z):
    threshold = gate_threshold(items, z)
    kernel = transition_kernel(items, candidates, p, threshold)
    for c, row in enumerate(kernel):
        assert sum(row) == 1
        assert all(row[j] == 0 for j in range(c)), "no downward edges"
        assert all(row[j] == 0 for j in range(c + 1, min(items, c + threshold[c]) + 1)), "gate closes near edges"
        absorbing = c + threshold[c] >= items
        assert (row[c] == 1) == absorbing


def test_naive_dp_equals_closed_form_gk_plus_one():
    for items, candidates in ((2, 1), (3, 3), (5, 2), (8, 4)):
        for p in (Q(1, 3), HALF, Q(9, 10)):
            trajectory = reuse_trajectory(items, candidates, p, naive_threshold(items), 6)
            for g in range(7):
                closed = naive_closed_form(items, candidates, p, g)
                assert trajectory["expected_reported"][g] == closed["expected_reported"]
                assert trajectory["readout_gap"][g] == closed["readout_gap"]
            assert trajectory["readout_gap"][1] == selection_inflation(items, candidates + 1, p)["readout_gap"]


def test_known_incumbent_count_is_running_max_with_floor():
    for start in (0, 3, 5, 8):
        point = [Q(int(c == start)) for c in range(9)]
        final = state_distribution(8, 2, HALF, naive_threshold(8), 4, point)[-1]
        assert sum(c * mass for c, mass in enumerate(final)) == running_max_from_point(8, 2, HALF, 4, start)
    assert running_max_from_point(8, 2, HALF, 0, 3) == 3


@pytest.mark.parametrize("items, candidates, generations", [(2, 2, 2), (3, 2, 2), (2, 3, 2), (4, 2, 2), (2, 2, 3)])
def test_dp_matches_independent_count_enumeration(items, candidates, generations):
    for p in (HALF, QUARTER):
        for threshold in (naive_threshold(items), gate_threshold(items, 2)):
            dp = state_distribution(items, candidates, p, threshold, generations)[-1]
            assert dp == _count_enumeration(items, candidates, p, threshold, generations)


def test_dp_matches_literal_item_enumeration_n2_k2_g2():
    for p in (HALF, QUARTER, Q(1, 3)):
        for threshold in (naive_threshold(2), (0, 1, 0)):
            dp = state_distribution(2, 2, p, threshold, 2)[-1]
            assert dp == brute_force_reuse_distribution(2, 2, p, threshold, 2)
    with pytest.raises(ValueError):
        brute_force_reuse_distribution(4, 2, HALF, naive_threshold(4), 2)


def test_naive_gap_monotone_diminishing_bounded_and_ceiling_identity():
    for items, candidates, p in ((4, 1, HALF), (8, 2, QUARTER), (16, 4, HALF), (3, 2, Q(1, 10))):
        trajectory = reuse_trajectory(items, candidates, p, naive_threshold(items), 12)
        gaps = trajectory["readout_gap"]
        increments = [b - a for a, b in zip(gaps, gaps[1:])]
        assert gaps[0] == 0 and all(inc > 0 for inc in increments)
        assert all(b <= a for a, b in zip(increments, increments[1:]))
        assert all(gap <= 1 - p for gap in gaps)
        assert trajectory["ceiling_mass"] == ceiling_mass_closed_form(items, candidates, p, 12)
        assert trajectory["absorbing_states"] == (items,)


def test_false_acceptance_hand_values_and_gate_dominance():
    assert false_acceptance_probability(2, 2, HALF, naive_threshold(2)) == (Q(15, 16), Q(7, 16), Q(0))
    assert false_acceptance_probability(2, 2, HALF, (0, 1, 0)) == (Q(15, 16), Q(0), Q(0))
    for items, candidates in ((8, 2), (16, 4)):
        naive = false_acceptance_probability(items, candidates, HALF, naive_threshold(items))
        for z in (1, 2, 3):
            gated = false_acceptance_probability(items, candidates, HALF, gate_threshold(items, z))
            assert all(a <= b for a, b in zip(gated, naive))
    alpha_16_4_z3 = false_acceptance_probability(16, 4, HALF, gate_threshold(16, 3))
    assert alpha_16_4_z3[8] == 1 - (1 - Q(17, 65536))**4


def test_gated_state_never_exceeds_naive_running_max_path_by_path():
    """The coupling behind the gate-dominance proposition, enumerated."""

    items, candidates, generations = 3, 2, 2
    gate = gate_threshold(items, 2)
    for counts in product(range(items + 1), repeat=1 + generations * candidates):
        naive_state = gated_state = counts[0]
        seen = {counts[0]}
        for g in range(generations):
            best = max(counts[1 + g * candidates:1 + (g + 1) * candidates])
            seen.add(best)
            if best > naive_state:
                naive_state = best
            if best > gated_state + gate[gated_state]:
                gated_state = best
        assert gated_state in seen and gated_state <= naive_state == max(seen)


def test_gated_gap_below_naive_on_cells_and_gate_freezes_chain():
    for items, candidates in ((8, 2), (16, 4)):
        naive = reuse_trajectory(items, candidates, HALF, naive_threshold(items), 10)
        for z in (1, 2, 3):
            gated = reuse_trajectory(items, candidates, HALF, gate_threshold(items, z), 10)
            assert all(a <= b for a, b in zip(gated["readout_gap"], naive["readout_gap"]))
            assert gated["expected_acceptances"] < naive["expected_acceptances"]
    assert reuse_trajectory(8, 2, HALF, gate_threshold(8, 3), 1)["absorbing_states"] == (4, 5, 6, 7, 8)


def test_fresh_separate_block_is_unbiased_and_selection_block_does_not_accumulate():
    for items, candidates, p in ((4, 2, HALF), (8, 4, QUARTER), (16, 2, Q(2, 3))):
        threshold = naive_threshold(items)
        separate = fresh_trajectory(items, candidates, p, threshold, 7, "separate_block")
        assert separate["readout_gap"] == [0] * 8
        selection = fresh_trajectory(items, candidates, p, threshold, 7, "selection_block")
        one = selection_inflation(items, candidates + 1, p)["readout_gap"]
        assert selection["readout_gap"] == [0] + [one] * 7
        reuse = reuse_trajectory(items, candidates, p, threshold, 7)["readout_gap"]
        assert reuse[1] == one and all(gap > one for gap in reuse[2:])


def test_fresh_block_matches_first_reuse_generation_for_any_gate():
    for items, candidates, z in ((4, 2, 1), (8, 3, 2), (16, 4, 3)):
        threshold = gate_threshold(items, z)
        fresh = fresh_block_reported(items, candidates, HALF, threshold)["expected_reported"]
        assert fresh == reuse_trajectory(items, candidates, HALF, threshold, 1)["expected_reported"][1]


def test_fresh_block_hand_value_with_gate():
    gated = fresh_block_reported(2, 2, HALF, (0, 1, 0))
    assert gated == {"expected_reported": Q(43, 64), "readout_value": HALF, "readout_gap": Q(11, 64)}
    naive = fresh_block_reported(2, 2, HALF, naive_threshold(2))
    assert naive["readout_gap"] == Q(9, 32) == selection_inflation(2, 3, HALF)["readout_gap"]


def test_fresh_arm_matches_literal_enumeration():
    for p in (HALF, QUARTER):
        for threshold in (naive_threshold(2), (0, 1, 0)):
            assert (fresh_trajectory(2, 2, p, threshold, 2, "selection_block")["expected_reported"]
                    == brute_force_fresh_reported(2, 2, p, threshold, 2, "selection_block"))
            assert (fresh_trajectory(2, 2, p, threshold, 1, "separate_block")["expected_reported"]
                    == brute_force_fresh_reported(2, 2, p, threshold, 1, "separate_block"))


def test_drift_levels():
    assert drift_levels(QUARTER, Q(1, 8)) == (QUARTER, Q(3, 8), HALF, Q(5, 8), Q(3, 4), Q(7, 8), Q(1))
    assert drift_levels(Q(1), Q(1, 8)) == (Q(1),)
    assert drift_levels(Q(9, 10), Q(1, 5)) == (Q(9, 10), Q(1))


def test_drift_with_zero_gain_reduces_to_null_chain():
    for threshold in (naive_threshold(6), gate_threshold(6, 2)):
        drift = drift_trajectory(6, 3, Q(1, 3), Q(1, 6), {0: Q(1)}, threshold, 5)
        null = reuse_trajectory(6, 3, Q(1, 3), threshold, 5)
        assert drift["expected_reported"] == null["expected_reported"]
        assert drift["expected_true"] == [Q(1, 3)] * 6
        assert drift["acceptance_probability"] == null["acceptance_probability"]
        assert drift["expected_true_gain_acceptances"] == 0
        assert all(mass == 1 for mass in drift["mass_per_generation"])


def test_drift_dp_matches_literal_enumeration_tiny():
    schedule = decaying_gain_schedule(2, QUARTER, Q(3, 4))
    assert schedule == [{0: Q(3, 4), 1: Q(1, 4)}, {0: Q(13, 16), 1: Q(3, 16)}]
    for gain in ({1: Q(1)}, {0: Q(3, 4), 1: Q(1, 4)}, {0: HALF, 2: HALF}, schedule):
        for threshold in (naive_threshold(2), (0, 1, 0)):
            dp = drift_trajectory(2, 2, QUARTER, Q(1, 8), gain, threshold, 2)["final_distribution"]
            brute = brute_force_drift_distribution(2, 2, QUARTER, Q(1, 8), gain, threshold, 2)
            assert dp == {f"{c},{level}": mass for (c, level), mass in brute.items()}
    with pytest.raises(ValueError):
        brute_force_drift_distribution(2, 2, QUARTER, Q(1, 8), {0: HALF, 1: HALF}, naive_threshold(2), 4)


def test_drift_schedule_repeating_one_law_equals_constant_law():
    law = {0: Q(3, 4), 1: Q(1, 4)}
    constant = drift_trajectory(4, 2, QUARTER, Q(1, 8), law, naive_threshold(4), 4)
    scheduled = drift_trajectory(4, 2, QUARTER, Q(1, 8), [law] * 4, naive_threshold(4), 4)
    assert constant["expected_reported"] == scheduled["expected_reported"]
    assert constant["expected_true"] == scheduled["expected_true"]
    assert constant["final_distribution"] == scheduled["final_distribution"]


def test_drift_cell_orderings_n8_k2():
    naive, gate = naive_threshold(8), gate_threshold(8, 1)
    two_point = {0: Q(3, 4), 1: QUARTER}
    decaying = decaying_gain_schedule(20, QUARTER, Q(3, 4))
    constant = drift_trajectory(8, 2, QUARTER, Q(1, 8), two_point, naive, 20)
    scheduled = drift_trajectory(8, 2, QUARTER, Q(1, 8), decaying, naive, 20)
    for trajectory in (constant, scheduled):
        assert all(gap >= 0 for gap in readout_gap_series(trajectory))
        assert phantom_share(trajectory, 0, 20)["phantom_share"] > HALF
    early_c, late_c = phantom_share(constant, 0, 10), phantom_share(constant, 10, 20)
    early_s, late_s = phantom_share(scheduled, 0, 10), phantom_share(scheduled, 10, 20)
    assert late_c["phantom_share"] < early_c["phantom_share"]
    assert late_s["phantom_share"] > early_s["phantom_share"] > HALF
    ratio_c, ratio_s = late_early_ratio(constant, 10), late_early_ratio(scheduled, 10)
    assert ratio_c["reported_ratio"] < ratio_c["true_ratio"]
    assert ratio_s["reported_ratio"] > 2 * ratio_s["true_ratio"]
    fixed_naive = drift_trajectory(8, 2, QUARTER, Q(1, 8), {1: Q(1)}, naive, 20)
    fixed_gate = drift_trajectory(8, 2, QUARTER, Q(1, 8), {1: Q(1)}, gate, 20)
    assert fixed_gate["readout_gap"][20] > fixed_naive["readout_gap"][20]
    assert fixed_gate["expected_acceptances"] < fixed_naive["expected_acceptances"]
    assert fixed_naive["expected_true_gain_acceptances"] == fixed_naive["expected_acceptances"]


def test_phantom_share_and_late_early_ratio_hand_values():
    trajectory = {"expected_reported": [Q(0), HALF, Q(3, 4)], "expected_true": [Q(0), QUARTER, QUARTER]}
    assert phantom_share(trajectory, 0, 2)["phantom_share"] == Q(2, 3)
    assert phantom_share(trajectory, 1, 2)["phantom_share"] == 1
    assert late_early_ratio(trajectory, 1) == {"split": 1, "reported_ratio": HALF, "true_ratio": Q(0)}
    flat = {"expected_reported": [HALF, HALF], "expected_true": [HALF, HALF]}
    assert phantom_share(flat, 0, 1)["phantom_share"] is None
    null = reuse_trajectory(4, 2, HALF, naive_threshold(4), 3)
    assert phantom_share(null, 0, 3)["phantom_share"] == 1
    assert readout_gap_series(null) == null["readout_gap"]


def test_divergence_check_on_dp_expectations():
    null = reuse_trajectory(8, 2, HALF, naive_threshold(8), 20)
    result = divergence_check(null, (0, 4, 8, 12, 16, 20), Q(1, 40))
    assert result["flags_match_rho_increments"]
    assert result["flags"] == [True, True, True, False, False]
    assert result["rows"][0]["readout_gain"] == 0 and result["rows"][0]["selection_gain"] == null["readout_gap"][4]
    quiet = divergence_check(fresh_trajectory(8, 2, HALF, naive_threshold(8), 20, "selection_block"),
                             (0, 4, 8, 12, 16, 20), Q(0))
    assert quiet["flags"] == [True, False, False, False, False]
    drift = drift_trajectory(8, 2, QUARTER, Q(1, 8), {0: Q(3, 4), 1: QUARTER}, naive_threshold(8), 20)
    flagged = divergence_check(drift, (0, 4, 8, 12, 16, 20), Q(1, 40))
    assert flagged["flags_match_rho_increments"] and flagged["flags"][0]


@pytest.mark.parametrize("call", [
    lambda: transition_kernel(0, 2, HALF, (0,)),
    lambda: transition_kernel(2, 0, HALF, (0, 0, 0)),
    lambda: transition_kernel(2, 2, 0.5, (0, 0, 0)),
    lambda: transition_kernel(2, 2, Q(3, 2), (0, 0, 0)),
    lambda: transition_kernel(2, 2, True, (0, 0, 0)),
    lambda: transition_kernel(2, 2, HALF, (0, 0)),
    lambda: transition_kernel(2, 2, HALF, (0, -1, 0)),
    lambda: transition_kernel(2, 2, HALF, (0, 1.0, 0)),
    lambda: transition_kernel(2, 2, HALF, 3),
    lambda: state_distribution(2, 2, HALF, (0, 0, 0), -1),
    lambda: state_distribution(2, 2, HALF, (0, 0, 0), 2.0),
    lambda: state_distribution(2, 2, HALF, (0, 0, 0), 1, [HALF, HALF, HALF]),
    lambda: state_distribution(2, 2, HALF, (0, 0, 0), 1, [Q(1), Q(0)]),
    lambda: gate_threshold(4, -1),
    lambda: gate_threshold(4, 1.5),
    lambda: gate_threshold(0, 1),
    lambda: naive_threshold(0),
    lambda: running_max_from_point(4, 2, HALF, 1, 5),
    lambda: naive_closed_form(4, 2, HALF, -1),
    lambda: fresh_trajectory(4, 2, HALF, (0,) * 5, 3, "readout_block"),
    lambda: fresh_block_reported(4, 2, HALF, (0,) * 4),
    lambda: drift_levels(HALF, Q(0)),
    lambda: drift_levels(HALF, -Q(1, 8)),
    lambda: drift_levels(Q(3, 2), Q(1, 8)),
    lambda: drift_trajectory(2, 2, QUARTER, Q(1, 8), {}, (0, 0, 0), 1),
    lambda: drift_trajectory(2, 2, QUARTER, Q(1, 8), {0: HALF, 1: QUARTER}, (0, 0, 0), 1),
    lambda: drift_trajectory(2, 2, QUARTER, Q(1, 8), {-1: Q(1)}, (0, 0, 0), 1),
    lambda: drift_trajectory(2, 2, QUARTER, Q(1, 8), {1: 1.0}, (0, 0, 0), 1),
    lambda: drift_trajectory(2, 2, QUARTER, Q(1, 8), [{1: Q(1)}], (0, 0, 0), 2),
    lambda: drift_trajectory(2, 2, QUARTER, Q(1, 8), 7, (0, 0, 0), 2),
    lambda: decaying_gain_schedule(3, Q(3, 2), HALF),
    lambda: decaying_gain_schedule(3, QUARTER, HALF, 0),
    lambda: phantom_share({"expected_reported": [Q(0), Q(1)], "expected_true": [Q(0), Q(0)]}, 1, 1),
    lambda: phantom_share({"expected_reported": [Q(0), Q(1)], "expected_true": [Q(0), Q(0)]}, 0, 2),
    lambda: late_early_ratio({"expected_reported": [Q(0), Q(1)], "expected_true": [Q(0), Q(0)]}, 1),
    lambda: divergence_check(reuse_trajectory(2, 2, HALF, (0, 0, 0), 2), (0, 3), Q(0)),
    lambda: divergence_check(reuse_trajectory(2, 2, HALF, (0, 0, 0), 2), (0, 2), -Q(1)),
    lambda: brute_force_fresh_reported(2, 2, HALF, (0, 0, 0), 1, "other"),
    lambda: naive_gap_bounds(4, 2, HALF, -1),
    lambda: naive_gap_bounds(0, 2, HALF, 1),
    lambda: naive_gap_bounds(4, 2, 0.5, 1),
    lambda: mutation_candidate_law(4, HALF, Q(3, 2), 1),
    lambda: mutation_candidate_law(4, HALF, 0.5, 1),
    lambda: mutation_candidate_law(4, HALF, HALF, 5),
    lambda: mutation_candidate_law(4, HALF, HALF, 1.0),
    lambda: mutation_candidate_law(0, HALF, HALF, 0),
    lambda: mutation_transition_kernel(4, 0, HALF, HALF, (0,) * 5),
    lambda: mutation_transition_kernel(4, 2, HALF, HALF, (0,) * 4),
    lambda: mutation_state_distribution(4, 2, HALF, HALF, (0,) * 5, -1),
    lambda: mutation_state_distribution(4, 2, HALF, HALF, (0,) * 5, 1, [Q(1), Q(0)]),
    lambda: brute_force_mutation_distribution(4, 2, HALF, HALF, (0,) * 5, 2),
    lambda: one_step_gap_change(4, 2, HALF, Q(3, 4), 1, 1),
    lambda: one_step_gap_change(4, 2, HALF, -QUARTER, 1, 1),
    lambda: one_step_gap_change(4, 2, HALF, 0.25, 1, 1),
    lambda: one_step_gap_change(4, 2, HALF, QUARTER, 5, 1),
    lambda: one_step_gap_change(4, 2, HALF, QUARTER, 1, -1),
    lambda: one_step_gap_change(4, 2, HALF, QUARTER, 1, 1.0),
    lambda: one_step_gap_change(4, 0, HALF, QUARTER, 1, 1),
    lambda: drift_gap_increment_from_one_step(
        drift_trajectory(4, 2, QUARTER, Q(1, 8), {0: HALF, 1: HALF}, (0,) * 5, 2), 0),
    lambda: drift_gap_increment_from_one_step(
        drift_trajectory(4, 2, QUARTER, Q(1, 8), {1: Q(1)}, (0,) * 5, 2), 2),
    lambda: drift_kernel(2, 2, (QUARTER, 0.5, Q(1)), {1: Q(1)}, (0, 0, 0)),
    lambda: drift_kernel(2, 2, (HALF, QUARTER), {1: Q(1)}, (0, 0, 0)),
    lambda: drift_kernel(2, 2, (HALF, Q(3, 2)), {1: Q(1)}, (0, 0, 0)),
    lambda: drift_kernel(2, 2, (), {1: Q(1)}, (0, 0, 0)),
    lambda: drift_kernel(2, 2, (HALF, Q(1)), {1: HALF}, (0, 0, 0)),
    lambda: drift_kernel(2, 2, (HALF, Q(1)), {1: Q(1)}, (0, 0)),
    lambda: drift_expectations(2, 2, (HALF, Q(1)), {1: Q(1)}, (0, 0, 0), 2, Q(3, 2)),
    lambda: drift_expectations(2, 2, (HALF, Q(1)), [{1: Q(1)}], (0, 0, 0), 2),
    lambda: drift_expectations(2, 2, (HALF, Q(1)), {1: Q(1)}, (0, 0, 0), -1),
    lambda: drift_absorbing_states(2, (HALF, Q(1)), (0, 0)),
    lambda: kernel_iterates(drift_kernel(2, 2, (HALF, Q(1)), {1: Q(1)}, (0, 0, 0)), lambda x: x[0], -1),
    lambda: naive_draw_law(0, 2, (HALF, Q(1))),
    lambda: naive_draw_law(2, 2, (HALF, QUARTER)),
    lambda: quantile_coupling_crossing(0, (HALF, Q(1)), (0,), 1, 2),
    lambda: quantile_coupling_crossing(2, (HALF, Q(1)), (0, 0), 1, 2),
    lambda: quantile_coupling_crossing(2, (HALF, Q(1)), (0, 0, 0), 3, 2),
    lambda: quantile_coupling_crossing(2, (HALF, Q(1)), (0, 0, 0), 0, 2),
    lambda: quantile_coupling_crossing(2, (HALF, Q(1)), (0, 0, 0), 1, -1),
    lambda: threshold_rules(0),
    lambda: random_threshold_rules(3, -1, 0),
    lambda: mixed_objectives(2, (HALF, QUARTER)),
])
def test_malformed_inputs_raise(call):
    with pytest.raises(ValueError):
        call()


# --------------------------------------------------------------------------
# Part A: proven bounds on the naive gap
# --------------------------------------------------------------------------

def test_naive_gap_bounds_closed_forms_and_zero_at_one_draw():
    zero = naive_gap_bounds(8, 2, HALF, 0)
    assert zero["draws"] == 1 and zero["hoeffding"] == 0 and zero["bernstein"] == 0
    for items, candidates, p, g in ((4, 1, HALF, 3), (8, 2, QUARTER, 5), (16, 4, Q(1, 10), 20), (5, 3, Q(2, 3), 7)):
        bounds = naive_gap_bounds(items, candidates, p, g)
        m = g * candidates + 1
        variance = float(p * (1 - p))
        assert bounds["draws"] == m
        assert bounds["hoeffding"] == pytest.approx(sqrt(log(m) / (2 * items)))
        assert bounds["gaussian_scale"] == pytest.approx(sqrt(2 * log(m) * variance / items))
        assert bounds["bernstein"] == pytest.approx(bounds["gaussian_scale"] + log(m) / (3 * items))
    half = naive_gap_bounds(4, 4, HALF, 20)
    assert half["hoeffding"] == pytest.approx(half["gaussian_scale"])
    assert half["hoeffding"] > half["lattice_cap"] == 0.5, "the bound outgrows the lattice cap"


@pytest.mark.parametrize("items, candidates", [(3, 1), (4, 2), (7, 3), (16, 4)])
def test_naive_gap_bounds_dominate_exact_gap(items, candidates):
    for p in (Q(1, 10), QUARTER, Q(1, 3), HALF, Q(9, 10)):
        for g in range(0, 9):
            gap = float(naive_closed_form(items, candidates, p, g)["readout_gap"])
            bounds = naive_gap_bounds(items, candidates, p, g)
            assert gap <= bounds["hoeffding"] + BOUND_TOLERANCE
            assert gap <= bounds["bernstein"] + BOUND_TOLERANCE


def test_bernstein_tighter_only_when_variance_is_small():
    at_half = naive_gap_bounds(16, 1, HALF, 1)
    assert at_half["bernstein"] > at_half["hoeffding"]
    at_quarter = naive_gap_bounds(16, 1, QUARTER, 1)
    assert at_quarter["bernstein"] < at_quarter["hoeffding"]
    far = naive_gap_bounds(16, 4, QUARTER, 20)
    assert far["bernstein"] > far["hoeffding"]


# --------------------------------------------------------------------------
# Part B: mutation chain
# --------------------------------------------------------------------------

def test_mutation_candidate_law_hand_values_and_limits():
    assert mutation_candidate_law(2, HALF, HALF, 1) == [Q(3, 16), Q(10, 16), Q(3, 16)]
    assert mutation_candidate_law(3, QUARTER, Q(1), 0) == _pmf(3, QUARTER)
    for items, p, c in ((4, HALF, 2), (6, QUARTER, 5), (5, Q(2, 3), 0)):
        for q in Q_GRID:
            law = mutation_candidate_law(items, p, q, c)
            assert sum(law) == 1 and all(mass >= 0 for mass in law)
            assert sum(j * mass for j, mass in enumerate(law)) == c + q * (items * p - c)
        assert mutation_candidate_law(items, p, Q(1), c) == _pmf(items, p)
        assert mutation_candidate_law(items, p, Q(0), c) == [Q(int(j == c)) for j in range(items + 1)]
        for q in Q_GRID:
            assert mutation_candidate_law(items, p, q, items - 1)[items] == q * p * (1 - q * (1 - p))**(items - 1)


def test_mutation_state_n_minus_1_up_probability_peaks_then_falls_in_q():
    """From ``c = n - 1`` the per-candidate chance of reaching ``n`` is
    ``q p (1 - q (1 - p))^(n - 1)``, maximal at ``q = 1 / (n (1 - p))``: no
    state-by-state monotone coupling in ``q`` exists."""

    up = {q: mutation_candidate_law(4, HALF, q, 3)[4] for q in Q_GRID}
    assert up[QUARTER] < up[HALF] > up[Q(3, 4)] > up[Q(1)]
    assert up[HALF] == Q(27, 256) and up[Q(1)] == Q(1, 16)


def test_mutation_q1_reproduces_independent_chain_exactly():
    for items, candidates, p in ((4, 2, HALF), (8, 3, QUARTER), (6, 1, Q(2, 3))):
        for threshold in (naive_threshold(items), gate_threshold(items, 2)):
            assert mutation_transition_kernel(items, candidates, p, Q(1), threshold) == \
                transition_kernel(items, candidates, p, threshold)
            assert mutation_state_distribution(items, candidates, p, Q(1), threshold, 6) == \
                state_distribution(items, candidates, p, threshold, 6)
            mutated = mutation_trajectory(items, candidates, p, Q(1), threshold, 6)
            plain = reuse_trajectory(items, candidates, p, threshold, 6)
            assert mutated["readout_gap"] == plain["readout_gap"]
            assert mutated["acceptance_probability"] == plain["acceptance_probability"]


def test_mutation_q0_freezes_and_gap_is_monotone_and_capped_for_every_q():
    for items, candidates, p in ((4, 2, HALF), (8, 2, QUARTER), (16, 4, HALF)):
        for threshold in (naive_threshold(items), gate_threshold(items, 1)):
            for q in Q_GRID:
                kernel = mutation_transition_kernel(items, candidates, p, q, threshold)
                assert all(sum(row) == 1 for row in kernel)
                assert all(row[j] == 0 for c, row in enumerate(kernel) for j in range(c))
                trajectory = mutation_trajectory(items, candidates, p, q, threshold, 12)
                gaps = trajectory["readout_gap"]
                assert gaps[0] == 0 and all(b >= a for a, b in zip(gaps, gaps[1:]))
                assert all(gap <= 1 - p for gap in gaps)
                if q == 0:
                    assert all(gap == 0 for gap in gaps) and trajectory["expected_acceptances"] == 0


def test_mutation_dp_matches_literal_vector_enumeration():
    for p in (HALF, QUARTER):
        for q in (QUARTER, HALF):
            for threshold in (naive_threshold(2), (0, 1, 0)):
                dp = mutation_state_distribution(2, 2, p, q, threshold, 2)[-1]
                assert dp == brute_force_mutation_distribution(2, 2, p, q, threshold, 2)
    assert (mutation_state_distribution(2, 1, HALF, Q(3, 4), naive_threshold(2), 3)[-1]
            == brute_force_mutation_distribution(2, 1, HALF, Q(3, 4), naive_threshold(2), 3))
    assert (mutation_state_distribution(3, 2, QUARTER, HALF, (0, 1, 1, 0), 1)[-1]
            == brute_force_mutation_distribution(3, 2, QUARTER, HALF, (0, 1, 1, 0), 1))


def test_mutation_gap_monotone_in_q_at_first_generation_but_reversed_later_n8_k2():
    series = {q: mutation_trajectory(8, 2, HALF, q, naive_threshold(8), 20)["readout_gap"] for q in Q_GRID}
    assert series[Q(0)][1] < series[QUARTER][1] < series[HALF][1] < series[Q(3, 4)][1] < series[Q(1)][1]
    assert series[Q(1)][20] == naive_closed_form(8, 2, HALF, 20)["readout_gap"]
    assert all(series[q][20] > series[Q(1)][20] for q in (QUARTER, HALF, Q(3, 4)))
    first_failure = next(g for g in range(21)
                         if any(series[b][g] < series[a][g] for a, b in zip(Q_GRID, Q_GRID[1:])))
    assert first_failure == 3


# --------------------------------------------------------------------------
# Part C: one generation, gate versus naive, under a fixed gain
# --------------------------------------------------------------------------

def test_one_step_gap_change_hand_values():
    step = one_step_gap_change(2, 1, HALF, QUARTER, 0, 1)
    assert step["naive_change"] == Q(33, 64) and step["gate_change"] == Q(27, 64)
    assert step["difference"] == Q(3, 32) == step["window_integral"]
    assert step["window_mass"] == Q(6, 16)
    assert step["predicted_sign_of_difference"] == "nonnegative"
    assert one_step_gap_change(2, 1, HALF, QUARTER, 0, 0)["difference"] == 0
    assert one_step_gap_change(2, 1, HALF, QUARTER, 0, 0)["predicted_sign_of_difference"] == "zero"
    saturated = one_step_gap_change(2, 1, HALF, HALF, 0, 1)
    assert saturated["difference"] == 0 and saturated["predicted_sign_of_difference"] == "zero"
    assert one_step_gap_change(8, 2, QUARTER, Q(3, 16), 4, 2)["predicted_sign_of_difference"] == "undetermined"


@pytest.mark.parametrize("items, candidates", [(4, 2), (8, 2), (16, 2)])
def test_one_step_identity_and_sign_by_case_on_drift_states(items, candidates):
    levels = drift_levels(QUARTER, Q(1, 8))
    threshold = gate_threshold(items, 1)
    zero_everywhere = True
    for level in range(len(levels) - 1):
        delta = levels[level + 1] - levels[level]
        for c in range(items + 1):
            step = one_step_gap_change(items, candidates, levels[level], delta, c, threshold[c])
            assert step["difference"] == step["window_integral"]
            predicted, difference = step["predicted_sign_of_difference"], step["difference"]
            assert predicted != "undetermined"
            assert predicted != "zero" or difference == 0
            assert predicted != "nonnegative" or difference >= 0
            assert predicted != "nonpositive" or difference <= 0
            zero_everywhere &= difference == 0
    assert zero_everywhere == (items == 8), "t <= 1 and delta = 1/n make the difference vanish"


def test_one_step_case_iii_takes_both_signs():
    negative = one_step_gap_change(16, 2, QUARTER, Q(3, 32), 8, 2)
    positive = one_step_gap_change(16, 2, HALF, Q(3, 32), 8, 2)
    assert negative["predicted_sign_of_difference"] == positive["predicted_sign_of_difference"] == "undetermined"
    assert negative["difference"] < 0 < positive["difference"]


def test_one_step_increment_matches_drift_dp():
    for items, candidates, step in ((4, 2, Q(1, 8)), (8, 2, Q(1, 16)), (16, 2, QUARTER)):
        for threshold in (naive_threshold(items), gate_threshold(items, 1)):
            trajectory = drift_trajectory(items, candidates, QUARTER, step, {1: Q(1)}, threshold, 5)
            for g in range(5):
                assert drift_gap_increment_from_one_step(trajectory, g) == \
                    trajectory["readout_gap"][g + 1] - trajectory["readout_gap"][g]


def test_gate_order_chaining_on_fixed_gain_cells():
    def runs(items, candidates, step):
        return (drift_trajectory(items, candidates, QUARTER, step, {1: Q(1)}, naive_threshold(items), 20),
                drift_trajectory(items, candidates, QUARTER, step, {1: Q(1)}, gate_threshold(items, 1), 20))

    naive, gate = runs(8, 2, Q(1, 8))
    diff = [a - b for a, b in zip(naive["readout_gap"], gate["readout_gap"])]
    assert diff[1] == 0, "both cases hold at n = 8: identical first-generation gap"
    assert diff[2] > 0 and all(d < 0 for d in diff[3:]), "gate above naive from generation 3 on"
    naive, gate = runs(16, 2, Q(1, 8))
    diff = [a - b for a, b in zip(naive["readout_gap"], gate["readout_gap"])]
    assert all(d < 0 for d in diff[1:]), "case (ii) chains at every generation"
    naive, gate = runs(4, 2, Q(1, 8))
    diff = [a - b for a, b in zip(naive["readout_gap"], gate["readout_gap"])]
    assert all(d > 0 for d in diff[1:15]) and all(d < 0 for d in diff[15:]), "case (i) reverses at generation 15"


def test_naive_dominates_gate_in_expectation_on_fixed_gain_cells():
    for items, candidates in ((4, 2), (8, 2), (16, 2)):
        for step in (Q(1, 16), Q(1, 8), QUARTER):
            naive = drift_trajectory(items, candidates, QUARTER, step, {1: Q(1)}, naive_threshold(items), 20)
            gate = drift_trajectory(items, candidates, QUARTER, step, {1: Q(1)}, gate_threshold(items, 1), 20)
            assert all(a >= b for a, b in zip(naive["expected_reported"], gate["expected_reported"]))
            assert all(a >= b for a, b in zip(naive["expected_true"], gate["expected_true"]))


# --------------------------------------------------------------------------
# Part D: Proposition 8, naive versus gated chains under a fixed gain
# --------------------------------------------------------------------------

LATTICE = drift_levels(QUARTER, Q(1, 8))
FIXED = {1: Q(1)}


def test_drift_kernel_hand_values_n2():
    levels = (QUARTER, HALF, Q(1))
    one = drift_kernel(2, 1, levels, FIXED, naive_threshold(2))
    assert one[(0, 0)] == [((0, 0), QUARTER), ((1, 1), HALF), ((2, 1), QUARTER)]
    assert one[(1, 0)] == [((1, 0), Q(3, 4)), ((2, 1), QUARTER)]
    assert one[(2, 0)] == [((2, 0), Q(1))] and one[(0, 2)] == [((0, 2), Q(0)), ((2, 2), Q(1))]
    two = drift_kernel(2, 2, levels, FIXED, naive_threshold(2))
    assert two[(0, 0)] == [((0, 0), Q(1, 16)), ((1, 1), HALF), ((2, 1), Q(7, 16))]
    gated = drift_kernel(2, 2, levels, FIXED, (0, 1, 0))
    assert gated[(1, 0)] == [((1, 0), Q(1))] and gated[(0, 0)] == two[(0, 0)]
    mixed = drift_kernel(2, 2, levels, {0: HALF, 1: HALF}, naive_threshold(2))
    assert sum(p for _, p in mixed[(0, 0)]) == 1
    assert {y for y, _ in mixed[(0, 0)]} == {(0, 0), (1, 0), (1, 1), (2, 0), (2, 1)}
    for kernel in (one, two, gated, mixed):
        assert all(entries[0][0] == x and sum(p for _, p in entries) == 1 for x, entries in kernel.items())


@pytest.mark.parametrize("items, candidates, gain, z", [
    (4, 2, FIXED, 1), (8, 3, {0: Q(3, 4), 1: QUARTER}, 2), (6, 2, {0: HALF, 2: HALF}, 3), (5, 1, "decay", 1)])
def test_drift_expectations_equal_drift_trajectory(items, candidates, gain, z):
    G = 8
    schedule = decaying_gain_schedule(G, QUARTER, Q(3, 4)) if gain == "decay" else gain
    for threshold in (naive_threshold(items), gate_threshold(items, z), (0, 2, 0, 1, 0, 1)[:items + 1] + (0,) * max(0, items - 5)):
        dp = drift_trajectory(items, candidates, QUARTER, Q(1, 8), schedule, threshold, G)
        fast = drift_expectations(items, candidates, LATTICE, schedule, threshold, G)
        assert fast["expected_reported"] == dp["expected_reported"]
        assert fast["expected_true"] == dp["expected_true"]
        assert fast["stopped_at"] is None and fast["generations_run"] == G
        assert fast["absorbed_mass"][0] == sum(
            mass for c, mass in enumerate(_pmf(items, QUARTER)) if c + threshold[c] >= items)


def test_drift_expectations_early_stop_and_absorbing_states():
    assert drift_absorbing_states(8, LATTICE, gate_threshold(8, 3)) == frozenset(
        (c, i) for c in (4, 5, 6, 7, 8) for i in range(7))
    assert drift_absorbing_states(8, LATTICE, naive_threshold(8)) == frozenset((8, i) for i in range(7))
    run = drift_expectations(4, 4, drift_levels(HALF, QUARTER), FIXED, naive_threshold(4), 100, Q(1, 10**9))
    assert run["stopped_at"] is not None and run["generations_run"] == run["stopped_at"] < 100
    assert run["absorbed_mass"][-1] >= 1 - Q(1, 10**9) > run["absorbed_mass"][-2]
    assert all(b >= a for a, b in zip(run["absorbed_mass"], run["absorbed_mass"][1:]))
    assert all(b >= a for a, b in zip(run["expected_true"], run["expected_true"][1:]))


def test_drift_limit_within_unabsorbed_mass_and_naive_count_limit_is_n():
    levels = drift_levels(HALF, QUARTER)
    for threshold in (naive_threshold(4), gate_threshold(4, 1), gate_threshold(4, 3)):
        run = drift_expectations(4, 4, levels, FIXED, threshold, 200, Q(1, 10**12))
        limit = drift_limit(4, 4, levels, FIXED, threshold)
        slack = 1 - run["absorbed_mass"][-1]
        assert abs(limit["expected_reported"] - run["expected_reported"][-1]) <= slack
        assert abs(limit["expected_true"] - run["expected_true"][-1]) <= slack
    for items, candidates in ((4, 2), (8, 1)):
        naive = drift_limit(items, candidates, LATTICE, FIXED, naive_threshold(items))
        assert naive["expected_reported"] == 1
        assert all(value[0] == items for value in naive["by_state"].values())
        gated = drift_limit(items, candidates, LATTICE, FIXED, gate_threshold(items, 3))
        assert gated["expected_reported"] < 1 and gated["expected_true"] < naive["expected_true"]
    # n = 3, K = 1, lattice NONUNIFORM_LATTICES[0], rule (0, 2, 0, 0): from (0, 0) the
    # first jump lands at 1 (absorbed, 5/32), 2 (then 3 at 9/16) or 3 (5/32).
    limit = drift_limit(3, 1, NONUNIFORM_LATTICES[0], FIXED, (0, 2, 0, 0))
    assert limit["by_state"][(0, 0)][1] == (Q(11060) * Q(5, 32) + Q(2025) * Q(9, 16)) / 13085 == Q(9175, 41872)


def test_kernel_iterates_one_step_is_the_kernel_expectation():
    kernel = drift_kernel(4, 2, LATTICE, FIXED, gate_threshold(4, 2))
    count = kernel_iterates(kernel, lambda x: x[0], 2)
    assert count[0] == {x: Q(x[0]) for x in kernel}
    assert count[1] == {x: sum(p * y[0] for y, p in entries) for x, entries in kernel.items()}
    assert all(count[2][x] >= count[1][x] >= count[0][x] for x in kernel)


@pytest.mark.parametrize("levels", [LATTICE, NONUNIFORM_LATTICES[0], NONUNIFORM_LATTICES[1]])
def test_naive_true_value_iterates_are_monotone_in_count_and_level(levels):
    items, candidates, top = 6, 2, len(levels) - 1
    kernel = drift_kernel(items, candidates, levels, FIXED, naive_threshold(items))
    u = kernel_iterates(kernel, lambda x: levels[x[1]], 12)
    limit = drift_limit(items, candidates, levels, FIXED, naive_threshold(items))["by_state"]
    for k in range(13):
        assert all(u[k][(c, i)] >= u[k][(c + 1, i)] for c in range(items) for i in range(top + 1))
        assert all(u[k][(c, i)] <= u[k][(c, i + 1)] for c in range(items + 1) for i in range(top))
    assert all(limit[(c, i)][1] >= limit[(c + 1, i)][1] for c in range(items) for i in range(top + 1))


def test_naive_count_iterates_are_not_monotone_in_count():
    """A lower count earns a free level: from (0, 0) two naive generations
    report more than from (1, 0)."""

    kernel = drift_kernel(4, 2, drift_levels(QUARTER, Q(1, 16)), FIXED, naive_threshold(4))
    u = kernel_iterates(kernel, lambda x: x[0], 2)
    assert u[1][(0, 0)] < u[1][(1, 0)] and u[2][(0, 0)] > u[2][(1, 0)]
    assert u[2][(0, 0)] == Q(10810976656657108475, 4611686018427387904)


@pytest.mark.parametrize("threshold", [gate_threshold(8, 1), gate_threshold(8, 2), gate_threshold(8, 3),
                                       (3, 1, 2, 2, 0, 1, 0, 2, 0)])
def test_naive_dominates_any_threshold_rule_at_every_state(threshold):
    items, candidates, H = 8, 2, 12
    top = len(LATTICE) - 1
    naive = drift_kernel(items, candidates, LATTICE, FIXED, naive_threshold(items))
    gated = drift_kernel(items, candidates, LATTICE, FIXED, threshold)
    a = [min(items, c + threshold[c]) for c in range(items + 1)]
    for f in (lambda x: LATTICE[x[1]], lambda x: Q(x[0])):
        u, w = kernel_iterates(naive, f, H), kernel_iterates(gated, f, H)
        for k in range(H + 1):
            assert all(w[k][x] <= u[k][x] for x in naive)
            assert all(w[k][(c, i)] <= u[k][(j, min(top, i + 1))]
                       for (c, i) in naive for j in range(c + 1, a[c] + 1))
    limit_naive = drift_limit(items, candidates, LATTICE, FIXED, naive_threshold(items))["by_state"]
    limit_gated = drift_limit(items, candidates, LATTICE, FIXED, threshold)["by_state"]
    assert all(limit_gated[x][1] <= limit_naive[x][1] for x in naive)


def test_level_and_count_are_stochastically_dominated_at_every_state():
    items, candidates, H = 4, 2, 10
    naive = drift_kernel(items, candidates, LATTICE, FIXED, naive_threshold(items))
    gated = drift_kernel(items, candidates, LATTICE, FIXED, gate_threshold(items, 2))
    for ell in range(1, len(LATTICE)):
        u = kernel_iterates(naive, lambda x, ell=ell: Q(int(x[1] >= ell)), H)
        w = kernel_iterates(gated, lambda x, ell=ell: Q(int(x[1] >= ell)), H)
        assert all(w[k][x] <= u[k][x] for k in range(H + 1) for x in naive)
    for m in range(1, items + 1):
        u = kernel_iterates(naive, lambda x, m=m: Q(int(x[0] >= m)), H)
        w = kernel_iterates(gated, lambda x, m=m: Q(int(x[0] >= m)), H)
        assert all(w[k][x] <= u[k][x] for k in range(H + 1) for x in naive)


def test_lowering_a_non_naive_threshold_is_not_monotone():
    pair = threshold_pair_counterexample()
    assert pair["higher_rule_ahead_somewhere"]
    assert pair["lower_threshold"] == (0, 2, 0, 0) and pair["higher_threshold"] == (1, 2, 0, 1)
    assert pair["limit_witness"] == {"state": (0, 0), "lower_rule_true_value": Q(9175, 41872),
                                     "higher_rule_true_value": Q(1483, 2752)}
    finite = pair["finite_witness"]
    assert finite["horizon"] == 3 and finite["state"] == (0, 2)
    assert finite["higher_rule_true_value"] > finite["lower_rule_true_value"]


def test_dominance_search_small_grid():
    constant = dominance_search(FIXED, (4,), (2,), (1, 2), (QUARTER,), (Q(1, 8),), 30, Q(1, 10**9))
    assert constant["cells"] == 2 and constant["violations"] == [] and constant["limit_violations"] == []
    row = constant["rows"]["gain=law,p0=1/4,step=1/8,n=4,K=2,z=2"]
    assert row["first_violation_generation"] is None and row["limit"]["naive"][0] == 1.0
    assert row["reported_at_end"]["naive"] >= row["reported_at_end"]["gate"]
    assert row["true_at_end"]["naive"] >= row["true_at_end"]["gate"]
    scheduled = dominance_search(lambda h: decaying_gain_schedule(h, QUARTER, Q(3, 4)),
                                 (4,), (2,), (1,), (HALF,), (Q(1, 4),), 12, Q(1, 10**9))
    assert scheduled["cells"] == 1 and scheduled["first_violation"] is None
    assert scheduled["rows"]["gain=schedule,p0=1/2,step=1/4,n=4,K=2,z=1"]["limit"] is None
    assert scheduled["generations_compared"] == 12


# --------------------------------------------------------------------------
# Part E: Proposition 9, count dominance via the window sums of the naive iterates
# --------------------------------------------------------------------------

def test_naive_draw_law_is_best_of_k_at_the_next_level_clamped():
    levels = (QUARTER, HALF, Q(1))
    law = naive_draw_law(3, 2, levels)
    assert law == [best_of_pmf(3, 2, HALF), best_of_pmf(3, 2, Q(1)), best_of_pmf(3, 2, Q(1))]
    kernel = drift_kernel(3, 2, levels, FIXED, naive_threshold(3))
    for (c, i), entries in kernel.items():
        assert {y[0]: p for y, p in entries[1:]} == {J: law[i][J] for J in range(c + 1, 4) if law[i][J]}


def test_window_sums_are_the_gated_versus_naive_one_step_difference():
    """``W_{a(c)}(c, i) = (P f - Q f)(c, i)`` for the rule with ``a(c) = c + t(c)``."""

    items, candidates = 4, 2
    naive = drift_kernel(items, candidates, LATTICE, FIXED, naive_threshold(items))
    law = naive_draw_law(items, candidates, LATTICE)
    f = kernel_iterates(naive, lambda x: Q(x[0]), 3)[3]
    sums = window_sums(naive, f, items, law)
    assert sums[(items, 0)] == [] and all(len(sums[(c, i)]) == items - c for (c, i) in naive)
    for threshold in (gate_threshold(items, 1), gate_threshold(items, 3), (0, 2, 0, 3, 0)):
        gated = drift_kernel(items, candidates, LATTICE, FIXED, threshold)
        for (c, i) in naive:
            pf = sum(p * f[y] for y, p in naive[(c, i)])
            qf = sum(p * f[y] for y, p in gated[(c, i)])
            a = min(items, c + threshold[c])
            assert pf - qf == (sums[(c, i)][a - c - 1] if a > c else 0)
    # the full window is the one-generation gain of the count, non-negative
    full = kernel_iterates(naive, lambda x: Q(x[0]), 4)[4]
    assert all((sums[(c, i)][-1] if c < items else 0) == full[(c, i)] - f[(c, i)] for (c, i) in naive)


def test_hitting_lemmas_by_hand_n2_k1():
    """``n = 2, K = 1``, levels ``(1/4, 1/2, 1)``, ``m = 2``: survival from
    ``(0, 0)`` is the probability that no draw is ``2``; a draw of ``1`` moves
    the chain to ``(1, 1)`` where the next draw is at level ``2``."""

    levels = (QUARTER, HALF, Q(1))
    kernel = drift_kernel(2, 1, levels, FIXED, naive_threshold(2))
    u = kernel_iterates(kernel, lambda x: Q(int(x[0] >= 2)), 3)
    s = lambda k, x: 1 - u[k][x]
    assert s(1, (0, 0)) == Q(3, 4) and s(1, (1, 0)) == Q(3, 4) and s(1, (0, 1)) == 0
    # (L1) at (0, 0): s_2 = F(0) s_1(0,0) + pi(1) s_1(1,1) = 1/4 * 3/4 + 1/2 * 0 <= (3/4) s_1
    assert s(2, (0, 0)) == Q(3, 16) <= Q(3, 4) * s(1, (0, 0))
    # (L2): survival non-decreasing in the count below m; (L3): non-increasing in the level
    for k in range(4):
        assert s(k, (0, 0)) <= s(k, (1, 0)) and s(k, (0, 1)) <= s(k, (0, 0)) and s(k, (1, 1)) <= s(k, (1, 0))
    # (L4): the unit window from (0, 0) is pi(1) [u(1,1) - u(0,0)] >= 0 at every horizon
    law = naive_draw_law(2, 1, levels)
    for k in range(4):
        assert all(w >= 0 for sums in window_sums(kernel, u[k], 2, law).values() for w in sums)


@pytest.mark.parametrize("items, candidates, levels", [
    (4, 2, LATTICE), (6, 1, NONUNIFORM_LATTICES[0]), (5, 3, (Q(1, 8), Q(1, 8), Q(7, 8), Q(1)))])
def test_hitting_lemmas_and_window_sums_every_state_and_m(items, candidates, levels):
    H, top = 8, len(levels) - 1
    kernel = drift_kernel(items, candidates, levels, FIXED, naive_threshold(items))
    law = naive_draw_law(items, candidates, levels)
    for m in range(1, items + 1):
        u = kernel_iterates(kernel, lambda x, m=m: Q(int(x[0] >= m)), H)
        death = [1 - sum(law[i][:m]) for i in range(top + 1)]
        for (c, i) in kernel:
            if c >= m:
                continue
            for k in range(1, H + 1):
                assert 1 - u[k][(c, i)] <= (1 - death[i]) * (1 - u[k - 1][(c, i)]), "L1"
            for k in range(H + 1):
                if c + 1 < m:
                    assert u[k][(c, i)] >= u[k][(c + 1, i)], "L2"
                if i < top:
                    assert u[k][(c, i + 1)] >= u[k][(c, i)], "L3"
        for k in range(H + 1):
            assert all(w >= 0 for sums in window_sums(kernel, u[k], items, law).values() for w in sums), "L4"
    count = kernel_iterates(kernel, lambda x: Q(x[0]), H)
    for k in range(H + 1):
        assert all(w >= 0 for sums in window_sums(kernel, count[k], items, law).values() for w in sums)


def test_window_sums_imply_dominance_for_every_rule_n4():
    """``Q_t P^k c <= P^{k+1} c`` and ``Q_t^k c <= P^k c`` for all 120 rules on ``n = 4``."""

    items, candidates, H = 4, 2, 6
    naive = drift_kernel(items, candidates, LATTICE, FIXED, naive_threshold(items))
    u = kernel_iterates(naive, lambda x: Q(x[0]), H + 1)
    for threshold in product(*[range(items - c + 1) for c in range(items + 1)]):
        gated = drift_kernel(items, candidates, LATTICE, FIXED, threshold)
        w = kernel_iterates(gated, lambda x: Q(x[0]), H)
        for k in range(H):
            assert all(sum(p * u[k][y] for y, p in gated[x]) <= u[k + 1][x] for x in naive)
            assert all(w[k + 1][x] <= u[k + 1][x] for x in naive)


def test_pointwise_cone_fails_and_a_one_step_deviation_beats_naive():
    """``u_k(3, 1) < u_k(0, 0)`` at ``n = 4, K = 2``: rejecting the draw 3 once
    from ``(0, 0)`` and then following the naive rule beats the naive rule."""

    kernel = drift_kernel(4, 2, LATTICE, FIXED, naive_threshold(4))
    u = kernel_iterates(kernel, lambda x: Q(x[0]), 9)
    law = naive_draw_law(4, 2, LATTICE)
    assert u[8][(3, 1)] < u[8][(0, 0)] and u[1][(3, 1)] > u[1][(0, 0)]
    deviation = sum(p * u[8][y] for y, p in kernel[(0, 0)]) + law[0][3] * (u[8][(0, 0)] - u[8][(3, 1)])
    assert deviation > u[9][(0, 0)]
    fixture = count_dominance_lemma_fixture()
    assert all(fixture["flags"].values()) and fixture["pointwise_cone_failure"] is not None
    witness = fixture["pointwise_cone_failure"]
    assert witness["naive_value_at_landing"] < witness["naive_value_at_state"]
    assert witness["deviation_gain_at_next_horizon"] > 0
    assert all(cell["all_lemmas_every_m"] for cell in fixture["cells"].values())


def test_quantile_coupling_crossing_witness_replays_and_is_exact():
    cell = CROSSING_CELL
    witness = quantile_coupling_crossing(cell["items"], cell["levels"], cell["threshold"], cell["m"], cell["horizon"])
    assert witness["start"] == (0, 0) and witness["generations"] == 4 and witness["naive_count_at_crossing"] == 4
    draws = [(step["naive_draw"], step["gated_draw"]) for step in witness["path"]]
    assert draws == [(1, 1), (4, 2), (3, 3), (4, 4)]
    assert [step["naive_state"] for step in witness["path"]] == [(1, 1), (4, 2), (4, 2), (4, 2)]
    assert [step["gated_state"] for step in witness["path"]] == [(0, 0), (2, 1), (3, 2), (4, 3)]
    # first uniform lies in the level-1 cell of the draw 1: (F(0), F(1)] = ((7/8)^5, (7/8)^5 + 5 (1/8)(7/8)^4]
    u0 = witness["path"][0]["uniform"]
    assert Q(7, 8)**5 < u0 <= Q(7, 8)**5 + 5 * Q(1, 8) * Q(7, 8)**4
    assert replay_quantile_coupling(cell["items"], cell["levels"], cell["threshold"], witness)
    broken = {**witness, "path": [dict(witness["path"][0], uniform=Q(1, 2))] + witness["path"][1:]}
    assert not replay_quantile_coupling(cell["items"], cell["levels"], cell["threshold"], broken)
    # the naive rule never crosses itself, and no crossing on the n = 4 gate within horizon 6
    assert quantile_coupling_crossing(4, LATTICE, naive_threshold(4), 4, 6) is None
    assert quantile_coupling_crossing(4, LATTICE, gate_threshold(4, 2), 4, 6) is None
    fixture = coupling_crossing_fixture()
    assert fixture["witness_replays"] and fixture["no_crossing_on_gate_cells_within_horizon"]


# --------------------------------------------------------------------------
# Part F: mixed gain laws (an accepted candidate may carry gain zero)
# --------------------------------------------------------------------------

JUMP = (QUARTER, Q(3, 4), Q(1))
TWO_POINT_QUARTER = {0: Q(3, 4), 1: QUARTER}


def test_mixed_window_sums_are_the_one_step_difference_and_reduce_to_window_sums():
    items, candidates = 4, 2
    naive = drift_kernel(items, candidates, LATTICE, {0: HALF, 1: HALF}, naive_threshold(items))
    f = kernel_iterates(naive, lambda x: Q(x[0]), 3)[3]
    sums = mixed_window_sums(naive, f, items)
    assert sums[(items, 0)] == [] and all(len(sums[(c, i)]) == items - c for (c, i) in naive)
    for threshold in (gate_threshold(items, 1), gate_threshold(items, 3), (0, 2, 0, 3, 0)):
        gated = drift_kernel(items, candidates, LATTICE, {0: HALF, 1: HALF}, threshold)
        for (c, i) in naive:
            pf = sum(p * f[y] for y, p in naive[(c, i)])
            qf = sum(p * f[y] for y, p in gated[(c, i)])
            a = min(items, c + threshold[c])
            assert pf - qf == (sums[(c, i)][a - c - 1] if a > c else 0)
    fixed = drift_kernel(items, candidates, LATTICE, FIXED, naive_threshold(items))
    g = kernel_iterates(fixed, lambda x: Q(x[0]), 2)[2]
    assert mixed_window_sums(fixed, g, items) == window_sums(fixed, g, items, naive_draw_law(items, candidates, LATTICE))
    names = set(mixed_objectives(3, JUMP))
    assert names == {"count", "level", "hit>=1", "hit>=2", "hit>=3", "level>=1", "level>=2"}


def test_mixed_law_hand_values_n3_k1_averaging_step_fails_but_window_holds():
    """``n = 3, K = 1``, levels ``(1/4, 3/4, 1)``, gain 1 w.p. 1/4, target
    ``m = 3``: from ``(0, 0)`` the landings at count 1 are ``(1, 0)`` w.p.
    81/256 and ``(1, 1)`` w.p. 9/256, at count 2 w.p. 27/256 each; the death
    rates are ``H(0) = 30/256``, ``H(1) = 145/256``.  The posterior-averaged
    landing survival ``g_1`` is decreasing in the count and the prefix
    average exceeds the full one, yet the unit window stays positive."""

    kernel = drift_kernel(3, 1, JUMP, TWO_POINT_QUARTER, naive_threshold(3))
    assert kernel[(0, 0)] == [((0, 0), Q(82, 256)), ((1, 0), Q(81, 256)), ((1, 1), Q(9, 256)),
                              ((2, 0), Q(27, 256)), ((2, 1), Q(27, 256)), ((3, 0), Q(3, 256)), ((3, 1), Q(27, 256))]
    u = kernel_iterates(kernel, lambda x: Q(int(x[0] >= 3)), 2)
    s = lambda k, x: 1 - u[k][x]
    assert s(1, (0, 0)) == Q(113, 128) == s(1, (1, 0)) == s(1, (2, 0)) and s(1, (1, 1)) == Q(111, 256)
    assert s(2, (0, 0)) == Q(5867, 8192) and s(2, (1, 0)) == Q(47971, 65536) and s(2, (1, 1)) == Q(12321, 65536)
    assert s(2, (1, 0)) > s(2, (0, 0)), "L2: the gain-0 landing is worse for hitting than staying"
    g1 = [(Q(81, 90) * s(1, (1, 0)) + Q(9, 90) * s(1, (1, 1))), (s(1, (2, 0)) + s(1, (2, 1))) / 2]
    assert g1 == [Q(429, 512), Q(337, 512)] and g1[0] > g1[1]
    assert g1[0] > (Q(90, 256) * g1[0] + Q(54, 256) * g1[1]) / Q(144, 256) == Q(789, 1024)
    sums = {k: mixed_window_sums(kernel, u[k], 3) for k in (1, 2)}
    assert sums[1][(0, 0)][0] == Q(1035, 65536) and sums[2][(0, 0)][0] == Q(56925, 4194304)
    assert all(w >= 0 for k in (1, 2) for ws in sums[k].values() for w in ws)
    structure = mixed_count_structure(3, 1, JUMP, TWO_POINT_QUARTER, 4)
    assert all(structure["flags"].values())
    witness = structure["witnesses"]["g_not_monotone"]
    assert witness["m"] == 3 and witness["horizon"] == 1 and witness["state"] == (0, 0)
    assert witness["g_by_landing_count"] == [Q(429, 512), Q(337, 512)]
    assert structure["witnesses"]["prefix_average_above_full"]["full_average"] == Q(789, 1024)
    assert structure["witnesses"]["one_step_decay_bound_fails"]["horizon"] == 1
    assert structure["witnesses"]["one_step_suffix_compensation_fails"]["horizon"] == 1


def test_mixed_window_recursion_identity_and_distance_two_closure():
    """``W_k = A W_{k-1} + E_{k-1}`` two below the target: at ``(1, 0)`` of
    the hand cell, ``W_1 = rho(2, 1) (H(1) - H(0)) = 27/256 * 115/256``."""

    kernel = drift_kernel(3, 1, JUMP, TWO_POINT_QUARTER, naive_threshold(3))
    u = kernel_iterates(kernel, lambda x: Q(int(x[0] >= 3)), 3)
    sums = {k: mixed_window_sums(kernel, u[k], 3) for k in range(4)}
    assert sums[1][(1, 0)][0] == Q(27, 256) * Q(115, 256) == Q(3105, 65536)
    A = kernel[(1, 0)][0][1]
    assert A == Q(172, 256)
    for k in (2, 3):
        E = Q(27, 256) * Q(115, 256) * (1 - u[k - 1][(2, 1)])
        assert sums[k][(1, 0)][0] == A * sums[k - 1][(1, 0)][0] + E
    for law in ({0: HALF, 1: QUARTER, 2: QUARTER}, {0: HALF, 2: HALF}, FIXED):
        structure = mixed_count_structure(4, 2, (QUARTER, HALF, Q(3, 4), Q(1)), law, 8)
        assert structure["flags"]["recursion_identity"] and structure["flags"]["distance_two_closure"]
        assert structure["flags"]["windows_nonnegative"] and structure["identity_checks"] > 0


def test_mixed_laws_every_threshold_rule_dominated_on_small_cells():
    assert len(threshold_rules(2)) == 6 and len(threshold_rules(3)) == 24 and len(threshold_rules(4)) == 120
    assert random_threshold_rules(5, 3, 7) == random_threshold_rules(5, 3, 7)
    assert all(0 <= t <= 5 - c for rule in random_threshold_rules(5, 10, 1) for c, t in enumerate(rule))
    out = rule_dominance_check(3, 1, JUMP, {0: HALF, 1: HALF}, threshold_rules(3), 10)
    assert out["first_violation"] is None and out["rules_checked"] == 23 and out["comparisons"] == 23 * 7 * 11 * 12
    out = rule_dominance_check(4, 2, (Q(1, 8), Q(7, 8)), {0: QUARTER, 1: Q(3, 4)}, random_threshold_rules(4, 15, 3), 8)
    assert out["first_violation"] is None
    screen = mixed_window_screen(4, 2, JUMP, {0: HALF, 2: HALF}, 12)
    assert screen["negatives"] == [] and screen["windows_checked"] == 8 * 13 * 30


def test_mixed_laws_decaying_schedule_dominated_on_small_cells():
    schedule = decaying_gain_schedule(8, QUARTER, Q(3, 4))
    screen = scheduled_window_screen(3, 1, JUMP, schedule, 8)
    assert screen["negatives"] == [] and screen["windows_checked"] > 0
    out = scheduled_rule_dominance_check(2, 2, JUMP, schedule[:6], threshold_rules(2), 6)
    assert out["first_violation"] is None and out["rules_checked"] == 5
    constant = scheduled_rule_dominance_check(3, 1, JUMP, [TWO_POINT_QUARTER] * 5, threshold_rules(3), 5)
    assert constant["first_violation"] is None and constant["comparisons"] == 23 * 12 * 5 * 7


def test_level_dominance_holds_under_mixed_laws_but_M2_fails_for_zero_or_two_law():
    """From ``(0, 0)`` the lattice ``(1/4, 3/4, 1)`` with gain 2 w.p. 1/2
    reaches ``p = 1`` on every real draw, while from ``(0, 1)`` a null draw
    of 3 absorbs the chain at ``p = 3/4``: the naive level iterate is not
    monotone in the level, although every gate is still dominated."""

    out = mixed_level_structure(3, 1, JUMP, {0: HALF, 2: HALF}, 6)
    assert out["flags"] == {"M1": True, "M2": False, "D": True, "S_posterior": True, "S_per_gain": True}
    assert out["M2_witness"] == {"horizon": 4, "state": (0, 0), "value": Q(15856573, 16777216),
                                 "value_one_level_up": Q(15512157, 16777216)}
    assert all(mixed_level_structure(3, 1, JUMP, {0: HALF, 1: HALF}, 6)["flags"].values())
    assert all(mixed_level_structure(4, 2, LATTICE, FIXED, 6)["flags"].values())


# --------------------------------------------------------------------------
# version 0.6: one positive gain value (Proposition 10) versus two
# --------------------------------------------------------------------------

ZERO_PLATEAU = SINGLE_GAIN_LATTICES["zero_plateau"]


def test_integer_iterates_and_window_identity_match_the_fraction_versions():
    """Identity (W): every window sum equals the same-level growth defect
    ``[u_{k+1}(c,i) - F_i(a) u_k(c,i)] - [u_{k+1}(a,i) - F_i(a) u_k(a,i)]``,
    for one- and two-gain laws and every objective."""

    for items, candidates, levels, law in ((4, 2, LATTICE, {0: HALF, 1: QUARTER, 2: QUARTER}),
                                           (3, 1, ZERO_PLATEAU, TWO_GAIN_CELL["law"]),
                                           (4, 1, JUMP, TWO_POINT_QUARTER)):
        kernel = drift_kernel(items, candidates, levels, law, naive_threshold(items))
        for f in mixed_objectives(items, levels).values():
            exact = kernel_iterates(kernel, f, 4)
            fast = integer_iterates(kernel, f, 4)
            assert all(iterate_fraction(fast, k, x) == exact[k][x] for k in range(5) for x in kernel)
            for k in range(4):
                for (c, i), sums in mixed_window_sums(kernel, exact[k], items).items():
                    assert [same_level_window(fast, k, c, a, i) for a in range(c + 1, items + 1)] == sums
    assert integer_iterates(kernel, lambda x: Q(x[0]), 0)["numerators"][0][(2, 1)] == 2


def test_divergence_decomposition_with_and_without_residual():
    """Identity (V) at ``(0, 0)`` with ``a = 1`` on the two-gain cell: the
    first divergences are the count-one landings ``(1, 1)`` and ``(1, 3)``
    with weights 27/320 and 9/320 at generation one; the residual term is
    zero for a hitting indicator with ``a < m`` and for the level, not for
    the count itself."""

    items, levels, law = 3, ZERO_PLATEAU, TWO_GAIN_CELL["law"]
    kernel = drift_kernel(items, 1, levels, law, naive_threshold(items))
    hit = kernel_iterates(kernel, lambda x: Q(int(x[0] >= 3)), 6)
    out = divergence_decomposition(kernel, hit, 0, 1, 0)
    assert out["identity_holds"] and out["kappa_nonnegative"]
    assert out["kappa"][0] == {(1, 1): Q(27, 320), (1, 3): Q(9, 320)}
    assert out["kappa"][1] == {(1, 1): Q(11, 16) * Q(27, 320), (1, 3): Q(11, 16) * Q(9, 320)}
    assert set(out["residual"]) == {0}
    count = kernel_iterates(kernel, lambda x: Q(x[0]), 6)
    out = divergence_decomposition(kernel, count, 0, 2, 0)
    assert out["identity_holds"] and out["residual"][0] == -2 and out["residual"][1] != 0
    level = kernel_iterates(kernel, lambda x: levels[x[1]], 6)
    assert set(divergence_decomposition(kernel, level, 1, 3, 1)["residual"]) == {0}
    with pytest.raises(ValueError):
        divergence_decomposition(kernel, hit, 2, 2, 0)


@pytest.mark.parametrize("law_name", ["q=1/16", "q=15/16", "fixed", "zero_or_two_q=1/2", "zero_or_three_q=1/4"])
def test_single_gain_structure_every_step_of_proposition_10(law_name):
    for items, candidates, lname in ((3, 1, "zero_plateau"), (4, 2, "nonuniform"), (5, 2, "zero_to_one")):
        out = single_gain_structure(items, candidates, SINGLE_GAIN_LATTICES[lname], SINGLE_GAIN_LAWS[law_name], 6)
        assert all(out["flags"].values()), (lname, out["flags"])
        assert all(n > 0 for n in out["checks"].values())
    with pytest.raises(ValueError):
        single_gain_structure(3, 1, ZERO_PLATEAU, TWO_GAIN_CELL["law"], 4)


def test_single_gain_every_rule_dominated_and_integer_check_matches_fraction_check():
    out = rule_dominance_integer(4, 2, ZERO_PLATEAU, SINGLE_GAIN_LAWS["q=1/4"], threshold_rules(4), 10)
    assert out["first_violation"] is None and out["rules_checked"] == 119
    small = (3, 1, JUMP, {0: HALF, 1: HALF}, threshold_rules(3), 6)
    assert rule_dominance_integer(*small) == rule_dominance_check(*small)
    two = rule_dominance_integer(3, 1, ZERO_PLATEAU, TWO_GAIN_CELL["law"], threshold_rules(3), 40)
    assert two["first_violation"] is not None and two["first_violation"]["gated"] > two["first_violation"]["naive"]


def test_two_gain_counterexample_count_and_level_exact():
    """``n = 3, K = 1``, levels ``(0, 1/4, 1/4, 3/4)``, gains ``{0, 1, 3}``
    w.p. ``(3/5, 1/5, 1/5)``: rejecting a count of one at count zero beats
    the naive rule in the count tail, the mean count and the true value.
    The three-level cell (gains ``{0, 1, 2}`` w.p. ``(2/3, 1/6, 1/6)``,
    levels ``(0, 1/2, 1)``) by hand: naively the first acceptance is a
    gain-2 candidate (weight 1/6), a gain-1 candidate scoring 3 (1/48, stuck
    at p = 1/2) or one scoring 1 or 2 (1/8), which then reaches the top
    before a null 3 w.p. (1/3) / (1/3 + 1/12) = 4/5; so P(top) = (1/6 +
    1/10) / (15/48) = 64/75 and E[p] = 139/150, while the gate t(0) = 2
    gives P(top) = 8/9 and E[p] = 17/18."""

    out = two_gain_counterexample()
    assert out["count_dominance_fails"] and out["level_dominance_fails"] and out["no_zero_gain_needed"]
    assert out["draws_from_start"]["naive"] == [
        ((0, 0), Q(11, 16)), ((1, 1), Q(27, 320)), ((1, 3), Q(9, 320)), ((2, 1), Q(9, 320)),
        ((2, 3), Q(27, 320)), ((3, 1), Q(1, 320)), ((3, 3), Q(27, 320))]
    assert out["draws_from_start"]["gated"][0] == ((0, 0), Q(4, 5))
    assert out["top_count"]["first"]["horizon"] == 28 and out["top_count"]["largest"]["horizon"] == 34
    assert out["top_count"]["horizons_gate_ahead"] == list(range(28, 81))
    assert out["count"]["first"]["horizon"] == 39 and out["level"]["first"]["horizon"] == 19
    assert out["limit_true_value"] == {"naive": Q(8058689, 11073200), "gated": Q(2909, 3968)}
    assert out["first_negative_window_m3_state00_top1"]["horizon"] == 16
    assert out["L3_fails"]["horizon"] == 10 and out["L3_fails"]["state"] == (1, 0)
    assert out["L2_fails"]["horizon"] == 28 and out["L2_fails"]["state"] == (0, 0)
    assert out["level_cell"]["limit_true_value"] == {"naive": Q(139, 150), "gated": Q(17, 18)}
    assert out["level_cell"]["level"]["first"]["horizon"] == 19
    assert out["no_zero_cell"]["count"]["horizons_gate_ahead"] == [8, 9, 10, 11, 12]
    plateau_free = out["no_plateau_cell"]
    assert out["no_plateau_needed"] and plateau_free["top_count"]["horizons_gate_ahead"] == list(range(31, 81))
    assert plateau_free["level"]["first"]["horizon"] == 15


def test_support_screen_single_gain_clean_two_gains_negative():
    for law in (SINGLE_GAIN_LAWS["q=1/4"], SINGLE_GAIN_LAWS["zero_or_two_q=1/2"], SINGLE_GAIN_LAWS["fixed"]):
        out = support_window_screen(3, 1, ZERO_PLATEAU, law, 30)
        assert out["negatives"] == {"count": 0, "level": 0} and out["first_negative"] is None
    out = support_window_screen(3, 1, ZERO_PLATEAU, TWO_GAIN_LAWS["0|1|3"], 30)
    assert out["negatives"]["count"] > 0 and out["negatives"]["level"] > 0
    assert out["windows_checked"] == (3 + 3) * 31 * 4 * (3 + 2 + 1)
    fixture = gain_support_fixture()
    assert fixture["support_screen"]["single_gain_clean"] and fixture["structure"]["all_cells_pass"]
    assert not fixture["rules"]["violations"] and all(fixture["identities"].values())


def test_verify_reports_every_check_passing():
    report = verify()
    assert report["all_passed"] and len(report["checks"]) == 95
    assert report["evidence_status"].startswith("exact_synthetic")
    assert report["brute_force"]["all_match"]
    assert report["headline"]["naive_readout_gap_n8_k2_p_half"]["G=1"]["exact"] == Q(19305, 131072)
    assert report["one_step"]["states_checked"] == 270
    assert report["gate_order"]["later_generation_agreement_counts"]["ii"]["agree"] == 76
    assert report["mutation"]["cells_where_rho_not_monotone_in_q"] == {"naive": 18, "gate_z1": 15}
    sweep = report["dominance_sweep"]
    assert not sweep["full_sweep"] and sweep["by_law"]["fixed"]["cells"] == 324 and sweep["cells"] == 414
    assert sweep["violations"] == 0 and sweep["limit_violations"] == 0
    assert len(report["dominance_structure"]["routes_that_fail_for_the_count"]) == 4
    lemmas = report["count_dominance_lemmas"]
    assert len(lemmas["cells"]) == 23 and lemmas["states_below_m_checked"] == 6168
    assert report["headline"]["count_dominance"]["quantile_coupling_crossing"]["generations"] == 4
    mixed = report["mixed_gain_laws"]
    assert mixed["no_violation_anywhere"] and not mixed["full"] and mixed["fixed_gain_averaging_step_fails"]
    assert mixed["screen"]["cells"] == 120 and mixed["rules"]["cells"] == 40 and mixed["decaying"]["cells"] == 24
    assert mixed["level_structure"]["M2_fails_on_laws"] == ["zero_or_two_q=1/2"]
    assert report["headline"]["mixed_gain_laws"]["witnesses"]["g_not_monotone"]["state"] == (0, 0)
    gain = report["gain_support"]
    assert not gain["full"] and gain["structure"]["cells"] == 72 and gain["rules"]["cells"] == 6
    assert gain["support_screen"]["cells"] == 48 and gain["support_screen"]["single_gain_clean"]
    assert report["headline"]["gain_support"]["two_gain_ahead"]["top_count"]["first_horizon"] == 28
