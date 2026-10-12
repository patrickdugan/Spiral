from fractions import Fraction as Q
from itertools import product
from math import comb

import pytest

from spiral_ln.evaluation_game_feedback import selection_inflation
from spiral_ln.evaluation_feedback_multigen import (
    best_of_pmf, binomial_cdf, brute_force_drift_distribution,
    brute_force_fresh_reported, brute_force_reuse_distribution,
    ceiling_mass_closed_form, decaying_gain_schedule, divergence_check,
    drift_levels, drift_trajectory, false_acceptance_probability,
    fresh_block_reported, fresh_trajectory, gate_threshold, late_early_ratio,
    naive_closed_form, naive_threshold, phantom_share, readout_gap_series,
    reuse_trajectory, running_max_from_point, state_distribution,
    transition_kernel, verify,
)

HALF, QUARTER = Q(1, 2), Q(1, 4)


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
])
def test_malformed_inputs_raise(call):
    with pytest.raises(ValueError):
        call()


def test_verify_reports_every_check_passing():
    report = verify()
    assert report["all_passed"] and len(report["checks"]) == 30
    assert report["evidence_status"].startswith("exact_synthetic")
    assert report["brute_force"]["all_match"]
    assert report["headline"]["naive_readout_gap_n8_k2_p_half"]["G=1"]["exact"] == Q(19305, 131072)
