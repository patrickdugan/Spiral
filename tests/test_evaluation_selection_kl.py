from fractions import Fraction as Q
from itertools import product
from math import atan, log, pi, sqrt

import pytest

from spiral_ln.evaluation_feedback_multigen import best_of_pmf
from spiral_ln.evaluation_selection_kl import (
    GRID_P, LOG_TOLERANCE, SUPREMUM_TOLERANCE, TIE_RULES, beirami_radius, binomial_records,
    binomial_score_law, brute_force_selected_law, conditioned_on_max_law, dv_bound,
    first_index_weight, gaussian_max_expectation, gaussian_ratio_limit, gap_to_bound_ratio,
    hoeffding_proxy, kearns_saul_proxy, kl_ball_supremum, kl_divergence, kl_max_law, max_law,
    score_law, selected_record_law, selection_gap, subgaussian_violation, uniform_distinct_scores_kl,
    uniform_weight, verify,
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


@pytest.mark.parametrize("call", [
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
    assert report["all_passed"] and len(report["checks"]) == 24
    assert report["evidence_status"].startswith("exact_synthetic")
    assert report["grid"]["cells"] == 90
    c = report["headline"]["c_K"]
    assert all(c[f"K={k}"] < 1 for k in (2, 3, 5, 10, 100, 1000, 10000))
