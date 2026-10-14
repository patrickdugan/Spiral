from fractions import Fraction as Q
from itertools import product
from math import atan, comb, erfc, exp, log, pi, sqrt

import pytest

from spiral_ln.evaluation_feedback_multigen import best_of_pmf
from spiral_ln.evaluation_game_feedback import selection_inflation
from spiral_ln.evaluation_selection_kl import (
    EFFECTIVE_START, GRID_P, LOG_TOLERANCE, SUPREMUM_TOLERANCE, TIE_RULES, ExcessPolynomial, GaussianCells,
    asymptotic_margin, asymptotic_normalized_margin, cdf_and_midpoint_constants, cdf_remainder_check, ceil_decimal,
    certify_threshold, effective_threshold_search, exact_rho_sweep, excess_polynomial, exp_neg_bounds,
    gaussian_moment_bound, gaussian_tail_bound, gaussian_tail_sup_bound, local_expansion_majorants,
    local_remainder_check, margin_deficit, margin_deficit_from_excess, midpoint_euler_maclaurin_check,
    midpoint_remainder_check, normal_cdf_bounds, normal_density_bounds, rational_sqrt_bounds, second_order_delta,
    second_order_margin_constant,
    beirami_radius, binomial_records, binomial_score_law, brute_force_selected_law,
    brute_force_tie_count_moment, centered_max, centered_max_from_profile, centered_max_increment,
    conditioned_on_max_law, crude_tie_bound_deficit, dv_bound, exact_kl_ratio_along_items,
    expected_max_count, first_index_weight, gaussian_max_expectation, gaussian_max_moment,
    gaussian_ratio_limit, gap_to_bound_ratio, guess_recurrence, hoeffding_proxy, increment_ratio,
    kearns_saul_proxy, kl_ball_supremum, kl_divergence, kl_max_law, local_sums, max_law, max_of_two_law,
    mean_absolute_difference, monotonicity_sweep, order_statistic_mean_by_enumeration, overlap_profile,
    pair_gap_by_enumeration, pair_scaled_gap_squared, pair_step_ratio, profile_power_sums,
    quadruple_increment, quadruple_numerator, quadruple_recurrence, rational_step_ratio_rank, scaled_gap,
    scaled_gap_squared, score_law, second_profile_increment, selected_record_law, selection_gap,
    standardized_absolute_moment_squared, stop_loss_excess, subgaussian_violation, symmetric_binomial_mad,
    symmetric_binomial_mad_closed_form, tie_count_law, tie_count_moment, tie_mass, tie_polynomial,
    uniform_distinct_scores_kl, uniform_weight, verify, wide_monotonicity_sweep,
)

HALF, QUARTER = Q(1, 2), Q(1, 4)

SPACES = [
    ({"a": Q(1), "b": Q(0)}, {"a": 0, "b": 1}),
    ({"a": Q(1, 3), "b": Q(2, 3)}, {"a": 0, "b": 0}),
    ({"a": Q(1, 2), "b": Q(1, 4), "c": Q(1, 8), "d": Q(1, 8)}, {"a": 0, "b": 1, "c": 1, "d": 2}),
    ({"a": Q(1, 5), "b": Q(1, 5), "c": Q(1, 5), "d": Q(2, 5)}, {"a": 3, "b": 3, "c": 3, "d": 3}),
    ({"w": Q(1, 10), "x": Q(3, 10), "y": Q(2, 5), "z": Q(1, 5)}, {"w": Q(1, 2), "x": -1, "y": Q(1, 2), "z": 7}),
]


def _enumerate(p0, score, candidates, rule):
    """Independent enumeration over index tuples; the tie rule is applied literally."""

    records = list(p0)
    law = {record: Q(0) for record in records}
    for indices in product(range(len(records)), repeat=candidates):
        weight = Q(1)
        for i in indices:
            weight *= p0[records[i]]
        if weight == 0:
            continue
        top = max(score[records[i]] for i in indices)
        winners = [pos for pos, i in enumerate(indices) if score[records[i]] == top]
        if rule == "first_index":
            law[records[indices[winners[0]]]] += weight
        else:
            share = weight / len(winners)
            for pos in winners:
                law[records[indices[pos]]] += share
    return law


@pytest.mark.parametrize("p0,score", SPACES)
@pytest.mark.parametrize("candidates", [1, 2, 3])
def test_tie_rules_match_enumeration_and_each_other(p0, score, candidates):
    conditioned = conditioned_on_max_law(p0, score, candidates)
    for rule in TIE_RULES:
        closed = selected_record_law(p0, score, candidates, rule)
        assert closed == _enumerate(p0, score, candidates, rule)
        assert closed == brute_force_selected_law(p0, score, candidates, rule)
        assert closed == conditioned
        assert sum(closed.values()) == 1


def test_weights_agree_with_the_geometric_identity():
    for below, upto in ((Q(0), Q(1)), (Q(1, 3), Q(1, 2)), (Q(2, 7), Q(9, 10)), (Q(0), Q(1, 5))):
        for candidates in range(1, 7):
            direct = (upto**candidates - below**candidates) / (upto - below)
            assert first_index_weight(below, upto, candidates) == direct
            assert uniform_weight(below, upto, candidates) == direct


def test_max_law_matches_multigen_best_of_pmf():
    for items, candidates, p in ((2, 2, HALF), (3, 4, QUARTER), (5, 3, Q(2, 3)), (8, 1, HALF)):
        law = max_law(binomial_score_law(items, p), candidates)
        assert [law[Q(j, items)] for j in range(items + 1)] == best_of_pmf(items, candidates, p)
        assert sum(law.values()) == 1


def test_kl_on_records_equals_kl_of_max_law_and_gap_matches_selection_inflation():
    for items in range(1, 7):
        for candidates in (2, 3, 4):
            for p in (HALF, QUARTER, Q(9, 10)):
                p0, score = binomial_records(items, p)
                law = selected_record_law(p0, score, candidates)
                assert abs(kl_divergence(law, p0) - kl_max_law(items, candidates, p)) <= LOG_TOLERANCE
                gap = sum((mass * score[r] for r, mass in law.items()), Q(0)) - p
                assert gap == selection_gap(items, candidates, p)


def test_data_processing_inequality_by_direct_computation():
    p0 = {"a": Q(1, 2), "b": Q(1, 4), "c": Q(1, 8), "d": Q(1, 8)}
    score = {"a": 0, "b": 1, "c": 1, "d": 2}
    for candidates in (2, 3):
        discrete = selected_record_law(p0, score, candidates)
        discrete_kl = kl_divergence(discrete, p0)
        previous = -1.0
        for levels in (1, 2, 3, 5, 8):
            joint_p0 = {(r, l): m / levels for r, m in p0.items() for l in range(levels)}
            joint_score = {(r, l): Q(score[r]) + Q(l + 1, 2 * (levels + 1)) for (r, l) in joint_p0}
            joint = selected_record_law(joint_p0, joint_score, candidates)
            marginal = {r: Q(0) for r in p0}
            for (r, _), m in joint.items():
                marginal[r] += m
            assert marginal == discrete
            joint_kl = kl_divergence(joint, joint_p0)
            assert joint_kl >= discrete_kl - LOG_TOLERANCE
            assert joint_kl > previous
            assert joint_kl < beirami_radius(candidates)
            previous = joint_kl
        assert beirami_radius(candidates) - previous < 0.01
    # the same inequality for a pair of laws unrelated to selection
    joint_a = {("x", 0): Q(1, 2), ("x", 1): Q(1, 6), ("y", 0): Q(1, 6), ("y", 1): Q(1, 6)}
    joint_b = {("x", 0): Q(1, 4), ("x", 1): Q(1, 4), ("y", 0): Q(1, 4), ("y", 1): Q(1, 4)}
    marginal_a = {"x": Q(2, 3), "y": Q(1, 3)}
    marginal_b = {"x": Q(1, 2), "y": Q(1, 2)}
    assert kl_divergence(marginal_a, marginal_b) <= kl_divergence(joint_a, joint_b)


def test_n_equals_1_gap_equals_kl_ball_supremum_exactly_via_the_tilt():
    for candidates in (2, 3, 5, 10, 20):
        for p in GRID_P:
            top = 1 - (1 - p)**candidates
            assert selection_gap(1, candidates, p) == top - p
            kl = kl_max_law(1, candidates, p)
            binary = float(top) * log(float(top / p)) + float(1 - top) * log(float((1 - top) / (1 - p)))
            assert abs(kl - binary) <= LOG_TOLERANCE
            sup = kl_ball_supremum(1, p, kl)
            assert abs(sup - float(top)) <= SUPREMUM_TOLERANCE
            # pi_K is itself the exponential tilt of p0 at t = ln(top (1-p) / ((1-top) p))
            t = log(float(top * (1 - p) / ((1 - top) * p)))
            z = float(1 - p) + float(p) * pow(2.718281828459045, t)
            assert abs(float(p) * pow(2.718281828459045, t) / z - float(top)) <= 1e-12


def test_containment_and_dv_bound_on_a_small_grid():
    for items in (1, 4, 16):
        for candidates in (2, 5, 20):
            for p in GRID_P:
                kl = kl_max_law(items, candidates, p)
                radius = beirami_radius(candidates)
                gap = float(selection_gap(items, candidates, p))
                assert 0 < kl < radius
                assert gap <= dv_bound(items, p, kl) + LOG_TOLERANCE
                assert gap <= dv_bound(items, p, radius) + LOG_TOLERANCE
                assert dv_bound(items, p, radius) <= dv_bound(items, p, radius, "hoeffding") + LOG_TOLERANCE
                assert gap_to_bound_ratio(items, candidates, p) < gaussian_ratio_limit(candidates)
                assert gap_to_bound_ratio(items, candidates, p, "exact") <= 1


def test_gaussian_quadrature_closed_forms_and_c_K():
    assert abs(gaussian_max_expectation(1) - 0) <= 1e-9
    assert abs(gaussian_max_expectation(2) - 1 / sqrt(pi)) <= 1e-9
    assert abs(gaussian_max_expectation(3) - 3 / (2 * sqrt(pi))) <= 1e-9
    assert abs(gaussian_max_expectation(4) - 6 * atan(sqrt(2)) / pi**1.5) <= 1e-9
    for candidates in (2, 3, 5, 10, 100):
        assert abs(gaussian_max_expectation(candidates) - gaussian_max_expectation(candidates, "tail")) <= 1e-9
        assert gaussian_max_expectation(candidates) < sqrt(2 * log(candidates))
    values = [gaussian_ratio_limit(k) for k in (2, 3, 5, 10, 100)]
    assert all(0.9 < c < 1 for c in values) and values == sorted(values)
    assert abs(values[0] - (1 / sqrt(pi)) / sqrt(2 * log(2) - 1)) <= 1e-9


def test_kearns_saul_proxy_values_and_grid_sanity():
    assert kearns_saul_proxy(HALF) == 0.25 == hoeffding_proxy()
    for p in (Q(1, 10), QUARTER, Q(2, 5), Q(3, 4)):
        v = kearns_saul_proxy(p)
        assert abs(v - kearns_saul_proxy(1 - p)) <= 1e-15
        assert float(p * (1 - p)) < v < 0.25
        assert subgaussian_violation(p) <= 1e-9
        assert subgaussian_violation(p, "hoeffding") <= 1e-9


def test_uniform_distinct_scores_kl_approaches_the_radius():
    for candidates in (2, 3, 5):
        deficits = [beirami_radius(candidates) - uniform_distinct_scores_kl(n, candidates) for n in (5, 50, 500)]
        assert all(d > 0 for d in deficits) and deficits == sorted(deficits, reverse=True)
        assert deficits[-1] < 1e-4


def test_kl_divergence_handles_tiny_atoms_and_basic_identities():
    tiny = Q(1, 2**4000)
    p0 = {"x": tiny, "y": 1 - tiny}
    pi = {"x": 2 * tiny, "y": 1 - 2 * tiny}
    assert kl_divergence(p0, p0) == 0
    value = kl_divergence(pi, p0)
    assert value >= 0 and value == value and value < 1e-300
    assert kl_divergence({"x": Q(1)}, {"x": Q(1)}) == 0
    assert abs(kl_divergence({"x": Q(1), "y": Q(0)}, {"x": HALF, "y": HALF}) - log(2)) <= LOG_TOLERANCE
    assert score_law({"a": HALF, "b": HALF}, {"a": 1, "b": 1}) == {Q(1): Q(1)}
    assert beirami_radius(1) == 0 and abs(beirami_radius(2) - (log(2) - 0.5)) <= 1e-15


def _mad_by_enumeration(trials):
    return sum(Q(comb(trials, s), 2**trials) * abs(Q(s) - Q(trials, 2)) for s in range(trials + 1))


def test_de_moivre_mean_absolute_deviation_by_enumeration():
    for trials in range(1, 61):
        assert symmetric_binomial_mad(trials) == _mad_by_enumeration(trials) == symmetric_binomial_mad_closed_form(trials)
    for n in range(1, 31):
        # the even case used by the K = 2 theorem; the task's 2^(2n-1) would be twice this
        assert symmetric_binomial_mad(2 * n) == Q(n * comb(2 * n, n), 4**n)
    assert symmetric_binomial_mad(1) == HALF and symmetric_binomial_mad(2) == HALF and symmetric_binomial_mad(4) == Q(3, 4)


def test_expected_max_count_matches_selection_inflation_and_max_law():
    for items in range(1, 13):
        for candidates in (1, 2, 3, 4, 6):
            expected = expected_max_count(items, candidates)
            assert expected / items - HALF == selection_inflation(items, candidates, HALF)["readout_gap"]
            assert centered_max(items, candidates) == items * selection_gap(items, candidates, HALF)
            assert scaled_gap_squared(items, candidates) == items * selection_gap(items, candidates, HALF)**2
            law = max_law(binomial_score_law(items, HALF), candidates)
            assert expected == sum(s * items * mass for s, mass in law.items())
    assert centered_max(1, 2) == QUARTER and scaled_gap(1, 2) == 0.25
    assert expected_max_count(4, 3) == Q(11552, 4096) and scaled_gap_squared(4, 3) == Q(105, 128)**2 / 4


def test_pair_theorem_reduction_closed_form_step_and_limit():
    for n in range(1, 31):
        # E max(X1, X2) - n/2 = E|X1 - X2| / 2 = E|Bin(2n, 1/2) - n| / 2
        assert centered_max(n, 2) == pair_gap_by_enumeration(n) == symmetric_binomial_mad(2 * n) / 2
    for n in range(1, 121):
        assert scaled_gap_squared(n, 2) == pair_scaled_gap_squared(n) == Q(n * comb(2 * n, n)**2, 4 * 16**n)
        step = scaled_gap_squared(n + 1, 2) / scaled_gap_squared(n, 2)
        assert step == pair_step_ratio(n) == Q((2 * n + 1)**2, 4 * n * (n + 1)) == 1 + Q(1, 4 * n * (n + 1))
        assert step > 1
        assert (n + 1) * (2 * n + 1)**2 - n * (2 * n + 2)**2 == n + 1
    # Wallis: a_n(2)^2 rises to 1/(4 pi); the relative deficit is about 1/(4n)
    for n in (10, 100, 120):
        value = float(pair_scaled_gap_squared(n))
        assert value < 1 / (4 * pi)
        assert 0.97 < 4 * n * (1 - 4 * pi * value) < 1.0
    assert abs(sqrt(pair_scaled_gap_squared(120)) - 1 / (2 * sqrt(pi))) < 1e-3


def test_triple_and_quintuple_reduce_to_even_candidates_by_the_order_statistic_recurrence():
    for n in range(1, 61):
        assert centered_max(n, 3) == Q(3, 2) * centered_max(n, 2)
        assert centered_max(n, 5) == Q(5, 2) * (centered_max(n, 4) - centered_max(n, 2))
        assert scaled_gap_squared(n, 3) == Q(9, 4) * scaled_gap_squared(n, 2)
    # the recurrence (n-r) E Y_(r:n) + r E Y_(r+1:n) = n E Y_(r:n-1) itself, on a symmetric three-point law
    law = {-1: Q(1, 4), 0: HALF, 1: Q(1, 4)}

    def order_mean(r, size):
        total = Q(0)
        for draw in product(law, repeat=size):
            weight = Q(1)
            for y in draw:
                weight *= law[y]
            total += weight * sorted(draw)[r - 1]
        return total

    for size in (2, 3, 4):
        for r in range(1, size):
            assert (size - r) * order_mean(r, size) + r * order_mean(r + 1, size) == size * order_mean(r, size - 1)
    assert order_mean(2, 3) == 0 and order_mean(3, 5) == 0


def test_tie_count_moment_and_increment_identity():
    for n, k in ((1, 2), (2, 2), (3, 2), (4, 2), (5, 2), (1, 3), (2, 3), (3, 3), (4, 3), (2, 4), (3, 4), (2, 5)):
        assert tie_count_moment(n, k) == brute_force_tie_count_moment(n, k)
    for n in range(1, 21):
        for k in (1, 2, 3, 4, 7, 12):
            assert centered_max(n + 1, k) - centered_max(n, k) == centered_max_increment(n, k) == HALF - tie_count_moment(n, k)
        assert centered_max_increment(n, 1) == 0
        assert centered_max_increment(n, 2) == Q(comb(2 * n, n), 4**(n + 1)) == centered_max(n, 2) / (2 * n)
        assert increment_ratio(n, 2) == 1 == increment_ratio(n, 3)
        assert increment_ratio(n, 4) > 1 and increment_ratio(n, 12) > 1
    assert tie_count_moment(1, 2) == Q(3, 8)  # N = 2 with probability 1/2, else 1


def test_monotonicity_sweep_small_ranges():
    for candidates in (2, 4, 7, 10, 33):
        sweep = monotonicity_sweep(candidates, 60)
        assert sweep["monotone"] and sweep["first_failure"] is None
        assert sweep["min_step_ratio_at"] == 60 and sweep["rho_at_least_one"]
        assert sweep["rho_equals_one"] == (candidates in (2, 3))
        assert sweep["below_gaussian_limit"] and abs(sweep["scaled_gap_first"] - (0.5 - 2.0**-candidates)) < 1e-15
        assert sweep["min_step_ratio"] > 1 and sweep["min_margin"] > 0
    assert monotonicity_sweep(2, 60)["min_margin"] == 1.0
    # the sweep's step ratio is exact: at K = 3 it equals the K = 2 identity
    squares = [scaled_gap_squared(n, 3) for n in range(1, 12)]
    assert all(b / a == pair_step_ratio(n) for n, (a, b) in enumerate(zip(squares, squares[1:]), start=1))


def test_convex_order_of_standardized_counts_fails_at_every_step():
    assert standardized_absolute_moment_squared(1) == 1
    assert standardized_absolute_moment_squared(2) == HALF
    assert standardized_absolute_moment_squared(3) == Q(3, 4)
    for k in range(0, 60):
        odd, even = standardized_absolute_moment_squared(2 * k + 1), standardized_absolute_moment_squared(2 * k + 2)
        assert even < odd and even / odd == Q(2 * k + 1, 2 * k + 2)
        if k:
            assert standardized_absolute_moment_squared(2 * k) < odd
    # the exact value: (E|Z_{2k}|)^2 = 2k C(2k,k)^2 / 16^k, and E|Z_n| -> sqrt(2/pi)
    for k in (1, 2, 5, 20):
        assert standardized_absolute_moment_squared(2 * k) == Q(2 * k * comb(2 * k, k)**2, 16**k)
    assert abs(sqrt(standardized_absolute_moment_squared(400)) - sqrt(2 / pi)) < 2e-3
    for n in range(1, 31):
        assert stop_loss_excess(n) > 1e-3
    # n = 1 -> 2 at c = 0: 1/2 - sqrt(2)/4; n = 2 -> 3 at c = 1/sqrt(3): (sqrt(2) - 2/sqrt(3))/4
    assert abs(stop_loss_excess(1) - (0.5 - sqrt(2) / 4)) < 1e-12
    assert abs(stop_loss_excess(2) - (sqrt(2) - 2 / sqrt(3)) / 4) < 1e-12


def test_exact_kl_ratio_path_at_one_half():
    for candidates, start in ((2, 1), (5, 2)):
        path = exact_kl_ratio_along_items(candidates, tuple(range(1, 41)))
        values = [path[f"n={n}"]["ratio_exact"] for n in range(1, 41)]
        c = gaussian_ratio_limit(candidates)
        assert all(a > b for a, b in zip(values[start - 1:], values[start:]))
        assert all(c < v <= 1 for v in values[start - 1:])
        assert all(0 < path[f"n={n}"]["kl_over_radius"] < 1 for n in range(1, 41))
        assert path["n=40"]["kl_over_radius"] > path["n=1"]["kl_over_radius"]
        assert abs(values[0] - gap_to_bound_ratio(1, candidates, HALF, "exact")) <= 1e-12
    assert exact_kl_ratio_along_items(5, (1,))["n=1"]["ratio_exact"] < gaussian_ratio_limit(5)


def test_overlap_profile_polynomial_reproduces_every_centered_max():
    assert tie_polynomial(1) == [0]  # M_n(1) = 0
    assert tie_polynomial(2) == [0, 1] and tie_polynomial(3) == [0, Q(3, 2)]
    assert tie_polynomial(4) == [0, 2, -1] and tie_polynomial(5) == [0, Q(5, 2), Q(-5, 2)]
    assert tie_polynomial(6) == [0, 3, Q(-9, 2), 1]
    # 2 P_K(u(1-u)) = 1 - u^K - (1-u)^K at a few rationals u
    for k in range(1, 9):
        poly = tie_polynomial(k)
        for u in (Q(1, 3), Q(1, 7), Q(4, 5)):
            w = u * (1 - u)
            assert 2 * sum(c * w**j for j, c in enumerate(poly)) == 1 - u**k - (1 - u)**k
    for n in range(1, 16):
        profile = overlap_profile(n)
        assert len(profile) == n and profile == profile[::-1] and all(0 < w <= QUARTER for w in profile)
        q = binomial_score_law(n, HALF)
        cdf = Q(0)
        for m in range(n):
            cdf += q[Q(m, n)]
            assert profile[m] == cdf * (1 - cdf)
        for k in (1, 2, 3, 4, 5, 7, 10):
            assert centered_max_from_profile(n, k) == centered_max(n, k)


def test_pair_of_pairs_decomposition_and_second_largest_of_four():
    for n in range(1, 41):
        s1, s2 = profile_power_sums(n)
        law = max_of_two_law(n)
        assert sum(law.values()) == 1
        mad = mean_absolute_difference(law)
        # E max of four = E Y + E|Y - Y'|/2 with Y = max of two; the double sum collapses
        assert centered_max(n, 4) == s1 + mad / 2 == 2 * s1 - s2
        assert mad == 2 * (s1 - s2) and s1 == centered_max(n, 2)
        assert centered_max(n, 5) == Q(5, 2) * (s1 - s2)
        assert second_profile_increment(n) == profile_power_sums(n + 1)[1] - s2
        assert quadruple_increment(n) == centered_max_increment(n, 4) == centered_max(n + 1, 4) - centered_max(n, 4)
    for n in (1, 2, 3):
        s1, s2 = profile_power_sums(n)
        assert order_statistic_mean_by_enumeration(n, 4, 3) == 3 * s2
        assert order_statistic_mean_by_enumeration(n, 4, 2) == -3 * s2
        assert order_statistic_mean_by_enumeration(n, 4, 4) == centered_max(n, 4)
        assert order_statistic_mean_by_enumeration(n, 3, 2) == 0 and order_statistic_mean_by_enumeration(n, 2, 2) == s1
    local = local_sums(1)
    assert local == {"L1": HALF, "L2": Q(1, 16), "L4": Q(1, 8)}
    assert profile_power_sums(1) == (QUARTER, Q(1, 16)) and profile_power_sums(2) == (Q(3, 8), Q(9, 128))
    assert local_sums(3)["L4"] == Q(1 + 81 + 81 + 1, 8**4) == Q(164, 16**3)  # Franel-type numerator 164


def test_tie_count_law_and_the_crude_tie_bound_witness():
    for n, k in ((1, 2), (2, 2), (2, 3), (3, 3), (2, 4), (3, 4), (1, 5)):
        law = tie_count_law(n, k)
        q = binomial_score_law(n, HALF)
        masses = [q[Q(j, n)] for j in range(n + 1)]
        brute = {j: Q(0) for j in range(1, k + 1)}
        for counts in product(range(n + 1), repeat=k):
            weight = Q(1)
            for c in counts:
                weight *= masses[c]
            brute[counts.count(max(counts))] += weight
        assert law == brute and sum(law.values()) == 1
        assert sum(p for j, p in law.items() if j >= 2) == tie_mass(n, k)
        assert sum(Q(1, 2**j) * p for j, p in law.items()) == tie_count_moment(n, k)
    for n in range(1, 31):
        cubes = sum(Q(comb(n, m), 2**n)**3 for m in range(n + 1))
        assert crude_tie_bound_deficit(n, 2) == 0
        assert crude_tie_bound_deficit(n, 3) == -Q(n, 2) * cubes < 0
        assert crude_tie_bound_deficit(n, 4) < 0 and crude_tie_bound_deficit(n, 7) < 0
        # P(N >= 2) for K = 3 is (3/2) sum q^2 - (1/2) sum q^3 by the symmetry m -> n - m
        squares = sum(Q(comb(n, m), 2**n)**2 for m in range(n + 1))
        assert tie_mass(n, 3) == Q(3, 2) * squares - cubes / 2
    assert crude_tie_bound_deficit(1, 3) == -Q(1, 8) and crude_tie_bound_deficit(2, 4) == -Q(17, 64)


def test_rational_step_ratio_exists_for_pairs_and_triples_only():
    for k in (2, 3):
        assert rational_step_ratio_rank(lambda n, k=k: centered_max(n, k), 1)["exists"]
    for degree in (1, 2, 3, 4, 6):
        report = rational_step_ratio_rank(lambda n: centered_max(n, 4), degree)
        assert not report["exists"] and report["rank"] == report["columns"] == 2 * (degree + 1)
    assert not rational_step_ratio_rank(lambda n: mean_absolute_difference(max_of_two_law(n)), 4)["exists"]
    # positive control: a hypergeometric sequence passes at degree 1
    assert rational_step_ratio_rank(lambda n: Q(comb(2 * n, n), 4**n), 1)["exists"]


def test_quadruple_recurrence_is_found_and_holds_far_beyond_the_fit():
    assert quadruple_numerator(1) == 2**5 * Q(7, 16) and quadruple_numerator(2) == 2**9 * Q(87, 128)
    rec = quadruple_recurrence(verify_items=200)
    assert rec["order"] == 4 and rec["degree"] == 8 and rec["nullity"] == 1 and rec["verified"]
    assert rec["characteristic_monic"] == [2048, 1280, 72, -26, 1]
    assert all(rec["characteristic_roots"].values())
    assert all(v == 0 for v in rec["lower_order_nullity"].values())
    coefficients = rec["coefficients"]
    for n in (201, 250, 333):
        assert sum(sum(poly[d] * n**d for d in range(9)) * quadruple_numerator(n + i) for i, poly in enumerate(coefficients)) == 0
    # the guesser on a known hypergeometric sequence: C(2n, n) obeys (n+1) a_{n+1} - (4n+2) a_n = 0
    basis = guess_recurrence(lambda n: Q(comb(2 * n, n)), 1, 1, 8)
    assert len(basis) == 1
    (p0, p1), = basis
    assert p0[1] / p1[1] == -4 and p0[0] / p1[1] == -2 and p1[0] / p1[1] == 1


def test_gaussian_third_moment_margin_limit():
    assert abs(gaussian_max_moment(2, 1) - gaussian_max_expectation(2)) <= 1e-12
    assert abs(gaussian_max_moment(1, 2) - 1) <= 1e-9 and abs(gaussian_max_moment(1, 3)) <= 1e-9
    assert abs(gaussian_max_moment(2, 3) - 2.5 / sqrt(pi)) <= 1e-9
    assert abs(gaussian_max_moment(3, 3) - 15 / (4 * sqrt(pi))) <= 1e-9
    assert abs(asymptotic_margin(2)) <= 1e-9 and abs(asymptotic_margin(3)) <= 1e-9
    values = [asymptotic_margin(k) for k in range(4, 31)]
    assert all(v > 0 for v in values) and values == sorted(values)
    assert abs(asymptotic_margin(4) - 0.0205606) < 2e-7 and abs(asymptotic_margin(10) - 0.159103) < 2e-6
    assert abs(asymptotic_normalized_margin(4) - 1.08224) < 2e-5
    # the exact sweep's n(rho_n - 1) approaches c(K) from above at K = 4
    excess = [n * (increment_ratio(n, 4) - 1) for n in (50, 100, 200)]
    assert all(float(e) > asymptotic_margin(4) for e in excess)
    assert all(abs(float(e) - asymptotic_margin(4)) < 0.05 / n for e, n in zip(excess, (50, 100, 200)))


def test_wide_sweep_agrees_with_the_rational_sweep_on_small_ranges():
    wide = wide_monotonicity_sweep((2, 3, 4, 7, 10), 60)
    for k in (2, 3, 4, 7, 10):
        row, reference = wide[f"K={k}"], monotonicity_sweep(k, 60)
        assert row["monotone"] and row["first_failure"] is None and row["rho_at_least_one"]
        assert row["min_margin_at"] == reference["min_margin_at"] and row["min_rho_at"] == reference["min_rho_at"]
        assert abs(row["min_margin"] - reference["min_margin"]) <= 1e-9 * reference["min_margin"]
        assert abs(row["min_rho"] - reference["min_rho"]) <= 1e-12
        assert abs(row["margins"]["n=60"] - float(4 * 60 * 61 * (scaled_gap_squared(61, k) / scaled_gap_squared(60, k) - 1))) <= 1e-9
    assert wide["K=2"]["min_margin"] == 1.0 and wide["K=3"]["min_margin"] == 1.0
    assert wide["K=4"]["richardson_minus_gaussian"] is not None and abs(wide["K=4"]["richardson_minus_gaussian"]) < 1e-4
    huge = wide_monotonicity_sweep((300,), 12)
    assert huge["K=300"]["monotone"] and huge["K=300"]["min_margin"] > 1


# --- version 0.4: the effective second-order bound -------------------------------------------------


def _horner(coeffs, x):
    out = Q(0)
    for c in reversed(coeffs):
        out = out * x + c
    return out


def _derivative(coeffs):
    return [i * coeffs[i] for i in range(1, len(coeffs))] or [Q(0)]


def test_excess_polynomial_closed_forms_and_the_margin_identity():
    w_squared = [0, 0, 1, -2, 1]
    assert excess_polynomial(2) == [0] and excess_polynomial(3) == [0]
    assert excess_polynomial(4) == w_squared and excess_polynomial(5) == [Q(5, 2) * c for c in w_squared]
    for k in (4, 6, 9, 12):
        H = ExcessPolynomial(k)
        coeffs = H.u_coefficients()
        # H = (K/2) w - P_K(w) as a polynomial in w agrees with the u form
        for u in (Q(0), Q(1, 7), Q(1, 2), Q(5, 6), Q(1)):
            w = u * (1 - u)
            assert _horner(coeffs, u) == sum(c * w**i for i, c in enumerate(H.w_coefficients))
        d = coeffs
        for j in range(1, k + 1):
            d = _derivative(d)
            for u in (Q(0), Q(1, 3), Q(1, 2), Q(4, 5), Q(1)):
                assert H.derivative_bound(j, u, u) == abs(_horner(d, u))
            assert all(H.derivative_bound(j, u, u) <= H.sup(j) for u in (Q(0), Q(1, 9), Q(1, 2), Q(1)))
    four = ExcessPolynomial(4)
    assert four.lambda0 == 1 and four.lambda1 == 2 and four.sup(2) == 2 and four.sup(4) == 24
    for n in range(1, 9):
        for k in (2, 3, 4, 6, 7, 10):
            d = margin_deficit(n, k)
            assert d == margin_deficit_from_excess(n, k)
            assert d == centered_max(n, k) * (increment_ratio(n, k) - 1)
        assert margin_deficit(n, 5) == Q(5, 2) * margin_deficit(n, 4)
        assert margin_deficit(n, 2) == margin_deficit(n, 3) == 0


def test_rational_enclosures_bracket_the_special_functions():
    lo, hi = rational_sqrt_bounds(2)
    assert lo * lo <= 2 <= hi * hi and hi - lo <= Q(1, 10**14)
    for x in (Q(0), Q(1, 3), Q(5), Q(50), Q(1201, 8)):
        lo, hi = exp_neg_bounds(x)
        assert 0 < lo <= hi and lo <= exp(-float(x)) * (1 + 1e-12) and exp(-float(x)) * (1 - 1e-12) <= hi
        assert hi - lo <= 1e-60 + 1e-15 * float(hi)
    previous = Q(0)
    for t in [Q(i, 4) for i in range(-24, 25)] + [Q(13, 2), Q(7), Q(9)]:
        c_lo, c_hi = normal_cdf_bounds(t)
        d_lo, d_hi = normal_density_bounds(t)
        value = 0.5 * erfc(-float(t) / sqrt(2))
        assert c_lo <= value + 1e-15 and value - 1e-15 <= c_hi and c_lo <= c_hi
        assert d_lo <= exp(-float(t)**2 / 2) / sqrt(2 * pi) * (1 + 1e-12) and d_lo <= d_hi
        m_lo, m_hi = normal_cdf_bounds(-t)
        assert m_lo == 1 - c_hi and m_hi == 1 - c_lo
        if abs(t) <= 6:
            assert c_hi - c_lo < 1e-12
            assert c_lo >= previous
            previous = c_lo
    assert normal_cdf_bounds(Q(0)) == (Q(1, 2), Q(1, 2))


def test_gaussian_moment_and_tail_bounds():
    exact = {(0, 1): 1.0, (1, 1): sqrt(2 / pi), (2, 1): 1.0, (4, 1): 3.0, (0, 2): 1 / (2 * sqrt(pi)),
             (2, 2): 1 / (4 * sqrt(pi)), (1, 2): 1 / (2 * pi), (0, 4): 1 / (4 * pi**1.5 * sqrt(2))}
    for (k, a), value in exact.items():
        bound = float(gaussian_moment_bound(k, a))
        assert value * (1 - 1e-12) <= bound <= value * (1 + 1e-12)
    for A in (2, 3, 5):
        tail = 0.5 * erfc(A / sqrt(2))
        assert tail <= float(gaussian_tail_bound(0, 1, A)) <= tail * (1 + 1 / A**2) * 1.01
        assert exp(-A * A / 2) / sqrt(2 * pi) <= float(gaussian_tail_sup_bound(0, 1, A)) * (1 + 1e-12)
    assert float(gaussian_tail_bound(-1, 1, 3)) >= 0.5 * erfc(3 / sqrt(2)) / 3 * 0.99


def test_midpoint_euler_maclaurin_and_cell_quadrature():
    assert midpoint_euler_maclaurin_check()
    cells = GaussianCells()
    mass = cells.integral([(Q(1), [Q(1)], 1, None)])
    assert 1 <= mass <= Q(103, 100)   # upper Riemann sum: about (w/2) int |phi'| above 1
    assert sqrt(2 / pi) <= float(cells.integral([(Q(1), [Q(0), Q(1)], 1, None)])) <= sqrt(2 / pi) * 1.08   # plus the Taylor slack (w/2) on each cell
    assert 1 / sqrt(2 * pi) <= float(cells.sup([(Q(1), [Q(1)], 1, None)])) <= 1 / sqrt(2 * pi) * 1.0001
    H = ExcessPolynomial(4)
    # int |H'(Phi)| = int 2 g |1 - 2 Phi| with g = Phi(1 - Phi): compare with a fine Riemann sum
    x = [i / 1000 for i in range(-10000, 10001)]
    cdf = [0.5 * erfc(-v / sqrt(2)) for v in x]
    reference = sum(2 * c * (1 - c) * abs(1 - 2 * c) for c in cdf) / 1000
    bound = float(cells.integral([(Q(1), [Q(1)], 0, (H, 1))]))
    assert reference <= bound <= reference * 1.1


def test_lemma_constants_dominate_the_exact_remainders():
    cells = GaussianCells()
    base = cdf_and_midpoint_constants(EFFECTIVE_START, cells)
    assert 0.3 < float(base["R_F"]) < 0.4 and float(base["R_F"]) < float(base["R_mu"]) < 0.5
    loc = local_expansion_majorants(EFFECTIVE_START)
    assert loc["tau"] == Q(1, 2) and loc["kappa"] == Q(4, 3) and 1 < loc["gamma"] < Q(1004, 1000)
    observed = cdf_remainder_check(400)
    assert observed <= base["R_F"] and 0.027 < float(observed) < 0.029
    assert midpoint_remainder_check(400) <= base["R_mu"]
    assert local_remainder_check(400) <= 0
    # below the proved range the CDF remainder has the same size (no hidden small-n blow-up)
    assert float(cdf_remainder_check(100)) < 0.03


def test_second_order_constant_and_threshold_for_four_candidates():
    cells = GaussianCells()
    base = cdf_and_midpoint_constants(EFFECTIVE_START, cells)
    four = second_order_margin_constant(4, EFFECTIVE_START, cells, base)
    assert four["C"] == ceil_decimal(four["C_exact"]) and four["C"] >= four["C_exact"]
    assert Q(74, 100) < four["C"] < Q(75, 100)
    assert four["H3"] < Q(1, 10**10) and four["L2"] < Q(1, 10**10) and four["tails"] < Q(1, 10**10) and four["L5"] == 0
    search = effective_threshold_search(4, four["C"], EFFECTIVE_START, EFFECTIVE_START)
    assert search["threshold"] == 400 and 2.8 < search["scaled_margin"] < 2.9
    assert certify_threshold(4, four["C"], 400)
    # a larger constant forces a scan past 400 (each scanned D_n is checked positive)
    forced = effective_threshold_search(4, Q(22, 10), EFFECTIVE_START, 460)
    assert forced["threshold"] is not None and 400 < forced["threshold"] <= 460 and forced["first_nonpositive"] is None
    assert effective_threshold_search(4, Q(10**6), EFFECTIVE_START, 402)["threshold"] is None
    # the observed deviation n (sqrt(n) D_n - delta_4) is about 0.0129, far inside C_4
    delta = second_order_delta(4)
    assert abs((float(margin_deficit(400, 4)) * 20 - delta) * 400 - 0.012865) < 1e-5
    six = second_order_margin_constant(6, EFFECTIVE_START, cells, base)
    assert four["C"] < six["C"] and six["L5"] > 0


def test_second_order_delta_matches_the_gaussian_margin():
    for k in (4, 6, 12):
        assert abs(second_order_delta(k) - asymptotic_margin(k) * gaussian_max_expectation(k) / 2) < 1e-9
    assert abs(second_order_delta(5) - 2.5 * second_order_delta(4)) < 1e-12


def test_exact_rho_sweep_is_strict():
    four = exact_rho_sweep(4, 60)
    assert four["all_positive"] and four["min_rho_at"] == 60 and four["min_rho"] > 1
    three = exact_rho_sweep(3, 10)
    assert not three["all_positive"] and three["first_failure"] == 1 and three["min_rho"] == 1.0


@pytest.mark.parametrize("call", [
    lambda: tie_polynomial(0),
    lambda: overlap_profile(0),
    lambda: mean_absolute_difference({0: 0.5, 1: 0.5}),
    lambda: order_statistic_mean_by_enumeration(2, 3, 4),
    lambda: tie_count_law(3, 0),
    lambda: tie_mass(0, 3),
    lambda: rational_step_ratio_rank(lambda n: Q(n), -1),
    lambda: guess_recurrence(lambda n: Q(n), 0, 2, 5),
    lambda: gaussian_max_moment(3, -1),
    lambda: wide_monotonicity_sweep((2, 0), 5),
    lambda: wide_monotonicity_sweep((2,), 0),
    lambda: symmetric_binomial_mad(0),
    lambda: symmetric_binomial_mad_closed_form(-2),
    lambda: expected_max_count(3, 0),
    lambda: expected_max_count(0, 3),
    lambda: pair_scaled_gap_squared(0),
    lambda: pair_step_ratio(0),
    lambda: tie_count_moment(2, 1.5),
    lambda: monotonicity_sweep(2, 0),
    lambda: stop_loss_excess(0),
    lambda: exact_kl_ratio_along_items(0, (1, 2)),
    lambda: selected_record_law({"a": HALF, "b": HALF}, {"a": 0, "b": 1}, 0),
    lambda: selected_record_law({"a": HALF, "b": HALF}, {"a": 0, "b": 1}, 2.0),
    lambda: selected_record_law({"a": HALF, "b": HALF}, {"a": 0, "b": 1}, 2, "last_index"),
    lambda: selected_record_law({"a": HALF, "b": HALF}, {"a": 0}, 2),
    lambda: selected_record_law({"a": HALF, "b": QUARTER}, {"a": 0, "b": 1}, 2),
    lambda: selected_record_law({"a": 0.5, "b": 0.5}, {"a": 0, "b": 1}, 2),
    lambda: selected_record_law({"a": HALF, "b": HALF}, {"a": 0.0, "b": 1}, 2),
    lambda: selected_record_law({}, {}, 2),
    lambda: brute_force_selected_law({"a": HALF, "b": HALF}, {"a": 0, "b": 1}, 2, "median"),
    lambda: kl_divergence({"a": Q(1)}, {"b": Q(1)}),
    lambda: kl_divergence({"a": HALF, "b": HALF}, {"a": Q(1), "b": Q(0)}),
    lambda: kl_max_law(0, 2, HALF),
    lambda: kl_max_law(4, 2, Q(0)),
    lambda: kl_max_law(4, 2, Q(1)),
    lambda: kl_max_law(4, 2, 0.5),
    lambda: kearns_saul_proxy(Q(0)),
    lambda: dv_bound(4, HALF, -1.0),
    lambda: dv_bound(4, HALF, 1.0, "bernstein"),
    lambda: kl_ball_supremum(4, HALF, -0.1),
    lambda: gaussian_max_expectation(0),
    lambda: gaussian_max_expectation(2, "moment"),
    lambda: gap_to_bound_ratio(4, 2, HALF, "radius_plus"),
    lambda: uniform_distinct_scores_kl(0, 2),
    lambda: selection_gap(4, 2, Q(3, 2)),
    lambda: excess_polynomial(1),
    lambda: ExcessPolynomial(0),
    lambda: ExcessPolynomial(4).derivative_bound(0, Q(0), Q(1)),
    lambda: exp_neg_bounds(-1),
    lambda: rational_sqrt_bounds(-1),
    lambda: gaussian_moment_bound(-1, 1),
    lambda: gaussian_moment_bound(2, 0),
    lambda: gaussian_tail_bound(4, 1, 1),
    lambda: gaussian_tail_sup_bound(9, 1, 2),
    lambda: cdf_remainder_check(401),
    lambda: local_remainder_check(100),
    lambda: cdf_and_midpoint_constants(401),
    lambda: second_order_margin_constant(1),
    lambda: effective_threshold_search(4, 0),
    lambda: effective_threshold_search(4, Q(1), 0),
    lambda: margin_deficit(0, 4),
    lambda: exact_rho_sweep(4, 0),
])
def test_malformed_inputs_are_rejected(call):
    with pytest.raises(ValueError):
        call()


def test_verify_reports_every_check_passing():
    report = verify()
    assert report["all_passed"] and len(report["checks"]) == 65 and not report["heavy"]
    assert sum(k.startswith("F_") for k in report["checks"]) == 14
    assert sum(k.startswith("G_") for k in report["checks"]) == 9
    v4 = report["headline_v0_4"]
    assert all(v4["thresholds"][f"K={k}"] == 400 for k in range(4, 26))
    assert all(400 < v4["thresholds"][f"K={k}"] <= 500 for k in range(26, 31))
    assert Q(74, 100) < v4["C_K"]["K=4"] < Q(75, 100) and v4["C_K"]["K=30"] < 104
    assert v4["R_F"] < Q(36, 100) and v4["R_mu"] < Q(44, 100)
    assert all(row["within"] for row in v4["deviations"].values())
    assert report["evidence_status"].startswith("exact_synthetic")
    v3 = report["headline_v0_3"]
    assert v3["wide_global_min_margin"][1:] == (4, 400) and 1.0826 < v3["wide_global_min_margin"][0] < 1.0827
    assert v3["wide_max_relative_fit_residual"] < 1e-3
    assert all(row["monotone"] for row in v3["huge_sweep_table"].values())
    assert v3["quadruple_recurrence"]["characteristic_monic"] == [2048, 1280, 72, -26, 1]
    assert report["grid"]["cells"] == 90
    c = report["headline"]["c_K"]
    assert all(c[f"K={k}"] < 1 for k in (2, 3, 5, 10, 100, 1000, 10000))
    table = report["headline"]["monotone_table"]
    assert set(table) == {"K=3", "K=4", "K=5", "K=10", "K=20"}
    assert all(row["monotone"] and row["min_step_ratio_at"] == 200 and row["min_rho"] >= 1 for row in table.values())
    assert table["K=3"]["min_margin"] == 1.0 and table["K=3"]["min_rho"] == 1.0
    assert report["headline"]["pair_step_ratio_at_200"] == Q(160801, 160800)
    assert report["headline"]["exact_kl_ratio"]["K=5"]["decreasing_from"] == 2
