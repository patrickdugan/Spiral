from fractions import Fraction as Q
from itertools import product
from math import atan, comb, log, pi, sqrt

import pytest

from spiral_ln.evaluation_feedback_multigen import best_of_pmf
from spiral_ln.evaluation_game_feedback import selection_inflation
from spiral_ln.evaluation_selection_kl import (
    GRID_P, LOG_TOLERANCE, SUPREMUM_TOLERANCE, TIE_RULES, beirami_radius, binomial_records,
    binomial_score_law, brute_force_selected_law, brute_force_tie_count_moment, centered_max,
    centered_max_increment, conditioned_on_max_law, dv_bound, exact_kl_ratio_along_items,
    expected_max_count, first_index_weight, gaussian_max_expectation, gaussian_ratio_limit,
    gap_to_bound_ratio, hoeffding_proxy, increment_ratio, kearns_saul_proxy, kl_ball_supremum,
    kl_divergence, kl_max_law, max_law, monotonicity_sweep, pair_gap_by_enumeration,
    pair_scaled_gap_squared, pair_step_ratio, scaled_gap, scaled_gap_squared, score_law,
    selected_record_law, selection_gap, standardized_absolute_moment_squared, stop_loss_excess,
    subgaussian_violation, symmetric_binomial_mad, symmetric_binomial_mad_closed_form,
    tie_count_moment, uniform_distinct_scores_kl, uniform_weight, verify,
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


@pytest.mark.parametrize("call", [
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
])
def test_malformed_inputs_are_rejected(call):
    with pytest.raises(ValueError):
        call()


def test_verify_reports_every_check_passing():
    report = verify()
    assert report["all_passed"] and len(report["checks"]) == 42
    assert report["evidence_status"].startswith("exact_synthetic")
    assert report["grid"]["cells"] == 90
    c = report["headline"]["c_K"]
    assert all(c[f"K={k}"] < 1 for k in (2, 3, 5, 10, 100, 1000, 10000))
    table = report["headline"]["monotone_table"]
    assert set(table) == {"K=3", "K=4", "K=5", "K=10", "K=20"}
    assert all(row["monotone"] and row["min_step_ratio_at"] == 200 and row["min_rho"] >= 1 for row in table.values())
    assert table["K=3"]["min_margin"] == 1.0 and table["K=3"]["min_rho"] == 1.0
    assert report["headline"]["pair_step_ratio_at_200"] == Q(160801, 160800)
    assert report["headline"]["exact_kl_ratio"]["K=5"]["decreasing_from"] == 2
