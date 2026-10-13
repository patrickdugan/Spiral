from fractions import Fraction as Q
from itertools import product
from math import comb, log, sqrt

import pytest

from spiral_ln.evaluation_game_feedback import selection_inflation
from spiral_ln.evaluation_feedback_multigen import (
    BOUND_TOLERANCE, best_of_pmf, binomial_cdf, brute_force_drift_distribution,
    brute_force_fresh_reported, brute_force_mutation_distribution,
    brute_force_reuse_distribution, ceiling_mass_closed_form,
    decaying_gain_schedule, divergence_check, drift_gap_increment_from_one_step,
    drift_levels, drift_trajectory, false_acceptance_probability,
    fresh_block_reported, fresh_trajectory, gate_threshold, late_early_ratio,
    mutation_candidate_law, mutation_state_distribution,
    mutation_trajectory, mutation_transition_kernel, naive_closed_form,
    naive_gap_bounds, naive_threshold, one_step_gap_change, phantom_share,
    readout_gap_series, reuse_trajectory, running_max_from_point,
    state_distribution, transition_kernel, verify,
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


def test_verify_reports_every_check_passing():
    report = verify()
    assert report["all_passed"] and len(report["checks"]) == 56
    assert report["evidence_status"].startswith("exact_synthetic")
    assert report["brute_force"]["all_match"]
    assert report["headline"]["naive_readout_gap_n8_k2_p_half"]["G=1"]["exact"] == Q(19305, 131072)
    assert report["one_step"]["states_checked"] == 270
    assert report["gate_order"]["later_generation_agreement_counts"]["ii"]["agree"] == 76
    assert report["mutation"]["cells_where_rho_not_monotone_in_q"] == {"naive": 18, "gate_z1": 15}
