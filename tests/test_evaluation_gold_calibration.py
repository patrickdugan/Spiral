import random
from fractions import Fraction as Q
from itertools import permutations, product
from math import comb

import pytest

from spiral_ln.evaluation_gold_calibration import (
    ANTI_INFORMATIVE_SECOND, CELLS3, CELLS4, CONSTRAINTS4, DS_FALSE_NEGATIVES, DS_FALSE_POSITIVES,
    DS_PRIOR, FOUR_FALSE_NEGATIVES, FOUR_FALSE_POSITIVES, FOUR_PRIOR, HALF, OUTSIDE_MODEL, PAIRS,
    PAIRS4, RANGE_FALSIFIER, RESOLUTION, SIGN_FALSIFIER, TRIPLES4, FourRaterTable, LabelTable,
    RecordTable, _binomial_upper_tail, _binomial_window, agreement_counts, agreement_covariance,
    agreement_covariance_model, agreement_patterns, agreement_rate, asymmetric_gold_noise_forward,
    asymmetric_gold_noise_inverse, calibrate, calibrate_asymmetric, calibration_valid,
    clamped_inversion, constraint_jacobian_rank, copy_grader_residual, copy_grader_table,
    copy_grader_table4, copy_grader_tetrad_residual, dawid_skene_four_raters,
    dawid_skene_jacobian_rank, dawid_skene_model, dawid_skene_moments, dawid_skene_three_raters,
    delta_variance, delta_variance_from_table, disagreement_bound, eps1_displacement,
    eps1_sensitivity, error_rate_at_most, error_rate_bracket, error_rate_from_square,
    eta_confidence_set, eta_gradient, exact_square_root, expected_record_table,
    expected_record_table_asymmetric, four_rater_constraints, four_rater_jacobian_rank,
    four_rater_model, four_rater_moments, four_rater_residuals, inverted_eps1, joint_statement,
    judges_separated, measured_judge_rates, model_constraints, model_jacobian_rank,
    observed_square, pairwise_kappas, planning_size, polarity_squares, ratio_relations,
    root_bracket, sampling_law, sampling_law_by_tables, square_tail_bracket, square_tail_law,
    square_test, three_rater_model, verify, walsh_coefficients,
)
from spiral_ln.evaluation_gold_calibration import (
    FIXTURE_REGION, TETRAD_KERNEL_BOUND, TETRAD_SIDES, UNIVERSAL_REGION, _cp_interval, _eps1_corner,
    _tetrad_u_from_counts, _variance_cap, asymmetric_eps1_enclosure, asymmetric_eps1_rational,
    eps1_confidence_interval, eps1_delta_variance, eps1_interval_coverage, interval_counts,
    monotonicity_fixture, root_in_range_interval, rounded_record, sign_at_square_root,
    sign_test_critical_value, sign_test_rejection_probability, sturm_root_count, tetrad_by_enumeration,
    tetrad_cantelli_power_bound, tetrad_cantelli_test, tetrad_influence_variance, tetrad_kernel,
    tetrad_moments, tetrad_point_variance_bound, tetrad_sign_block_law, tetrad_sign_test,
    tetrad_u_statistic, tetrad_u_variance, tetrad_variance_bound, witness_record,
)
from spiral_ln.evaluation_game_feedback import LoopEvent
from spiral_ln.evaluation_judge_measurement import (
    JudgeTable, binomial_upper_tail, clopper_pearson_bracket, gold_noise_forward, gold_noise_inverse,
    measurement_ledger,
)

PRIORS = (Q(0), Q(1, 4), Q(1, 3), Q(1, 2), Q(7, 10), Q(1))
ERRORS = (Q(0), Q(1, 20), Q(1, 10), Q(1, 4), Q(2, 5))
GRID = [(p, e) for p in PRIORS for e in product(ERRORS, repeat=3)]


def _enumerate_latent(prior, errors):
    """All 2^4 cells (Y, X_1, X_2, X_3); returns the label table as a dict."""

    cells = {cell: Q(0) for cell in CELLS3}
    for y, x1, x2, x3 in product((0, 1), repeat=4):
        w = prior if y else 1 - prior
        for x, e in zip((x1, x2, x3), errors):
            w *= (1 - e) if x == y else e
        cells[(x1, x2, x3)] += w
    return cells


def _enumerate_record(prior, accuracy, judge_error, eps1, eta1, eta2):
    """All 2^5 latent cells (Y, x_C, v_J, g_1, g_2) of the independent-grader model."""

    eps0 = (judge_error - (1 - accuracy) * eps1) / accuracy
    cells = {}
    for y, x, v, g1, g2 in product((0, 1), repeat=5):
        w = prior if y else 1 - prior
        right = x == y
        w *= accuracy if right else 1 - accuracy
        says = (1 - eps0) if right else eps1
        w *= says if v else 1 - says
        w *= (1 - eta1) if g1 == y else eta1
        w *= (1 - eta2) if g2 == y else eta2
        cells[(x, v, g1, g2)] = cells.get((x, v, g1, g2), Q(0)) + w
    return cells


# --- identities --------------------------------------------------------------

def test_model_matches_latent_enumeration_and_polarities_factor():
    for prior, errors in GRID:
        table = three_rater_model(prior, errors)
        assert table.cells == _enumerate_latent(prior, errors)
        assert table.total == 1
        d = [1 - 2 * e for e in errors]
        tau = 1 - 2 * prior
        coefficients = walsh_coefficients(table)
        kappas = pairwise_kappas(table)
        for i, j in PAIRS:
            assert kappas[(i, j)] == coefficients[(i, j)] == d[i - 1] * d[j - 1]
            assert agreement_rate(table, i, j) == 1 - errors[i - 1] - errors[j - 1] + 2 * errors[i - 1] * errors[j - 1]
        for i in (1, 2, 3):
            assert coefficients[(i,)] == tau * d[i - 1]
        assert coefficients[(1, 2, 3)] == tau * d[0] * d[1] * d[2]


def test_squares_recover_each_rater_exactly_on_the_grid():
    for prior, errors in GRID:
        kappas = pairwise_kappas(three_rater_model(prior, errors))
        if any(k == 0 for k in kappas.values()):
            with pytest.raises(ValueError):
                polarity_squares(kappas)
            continue
        squares = polarity_squares(kappas)
        for i in (1, 2, 3):
            assert squares[i] == (1 - 2 * errors[i - 1]) ** 2
            assert error_rate_from_square(squares[i]) == errors[i - 1]
            bracket = error_rate_bracket(squares[i])
            assert bracket["exact"] == bracket["lower"] == bracket["upper"] == errors[i - 1]


def test_label_swap_is_observationally_equivalent_and_sign_fixed_by_convention():
    for prior, errors in GRID:
        swapped = three_rater_model(1 - prior, tuple(1 - e for e in errors))
        assert swapped == three_rater_model(prior, errors)
        kappas = pairwise_kappas(swapped)
        negatives = sum(1 for k in kappas.values() if k < 0)
        assert negatives in (0, 2) or any(k == 0 for k in kappas.values())


def test_exact_square_root_and_membership_consistency():
    assert exact_square_root(Q(16, 25)) == Q(4, 5) and exact_square_root(Q(0)) == 0 and exact_square_root(Q(1)) == 1
    assert exact_square_root(Q(2)) is None and exact_square_root(Q(148, 175)) is None and exact_square_root(Q(-1)) is None
    for square in (Q(148, 175), Q(1, 2), Q(2, 3), Q(1, 10), Q(9, 25), Q(16, 25)):
        bracket = error_rate_bracket(square, Q(1, 2 ** 12))
        low, high = bracket["lower"], bracket["upper"]
        assert 0 <= low <= high <= HALF and high - low <= Q(1, 2 ** 12)
        if bracket["exact"] is None:
            assert not error_rate_at_most(square, low) and error_rate_at_most(square, high)
            assert not error_rate_at_most(square, low - Q(1, 1000)) if low >= Q(1, 1000) else True
            assert error_rate_at_most(square, high + Q(1, 1000))
        else:
            assert error_rate_at_most(square, bracket["exact"]) and not error_rate_at_most(square, bracket["exact"] - Q(1, 10 ** 6))
        for bound in (Q(k, 40) for k in range(21)):
            floor = 1 - 2 * bound
            assert error_rate_at_most(square, bound) == (floor <= 0 or square >= floor * floor)


def test_eta_gradient_matches_exact_partials_of_the_square():
    kappas = {(1, 2): Q(12, 25), (1, 3): Q(12, 25), (2, 3): Q(9, 25)}
    gradient = eta_gradient(kappas, 1)
    assert gradient["polarity"] == Q(4, 5)
    assert gradient["per_kappa"] == {(1, 2): Q(-5, 12), (1, 3): Q(-5, 12), (2, 3): Q(5, 9)}
    assert gradient["per_agreement_rate"] == {pair: 2 * g for pair, g in gradient["per_kappa"].items()}
    square = polarity_squares(kappas)[1]
    for pair in PAIRS:
        for delta in (Q(1, 1000), Q(-1, 1000)):
            moved = dict(kappas)
            moved[pair] += delta
            exact_partial = {(1, 2): square / kappas[(1, 2)], (1, 3): square / kappas[(1, 3)],
                             (2, 3): -square / kappas[(2, 3)]}[pair]
            secant = (polarity_squares(moved)[1] - square) / delta
            assert abs(secant - exact_partial) <= Q(1, 100)
            assert gradient["per_kappa"][pair] == -exact_partial / (4 * gradient["polarity"])
    assert eta_gradient({(1, 2): Q(37, 50), (1, 3): Q(12, 25), (2, 3): Q(21, 50)}, 1) is None


# --- constraints -------------------------------------------------------------

def test_constraints_hold_on_model_and_rank_is_four():
    for prior, errors in GRID:
        result = model_constraints(three_rater_model(prior, errors))
        assert result["equalities_hold"] and result["signs_consistent"]
        assert result["model_consistent"]
        if all(e < HALF for e in errors):
            assert result["identifiable"] and result["passes"]
            assert result["squares_in_unit_interval"] and result["prior_in_range"]
        assert result["vacuous_at_balanced_prior"] == (prior == HALF or all(e == HALF for e in errors))
        assert model_jacobian_rank(prior, errors) == 4
    assert model_jacobian_rank(HALF, (Q(1, 10), HALF, Q(1, 5))) == 3
    assert model_jacobian_rank(Q(1, 4), (Q(1, 10), HALF, Q(1, 5))) == 4


def test_copy_grader_fails_constraints_with_closed_form_unless_balanced():
    for prior in (Q(1, 4), Q(1, 3), Q(7, 10), Q(1), HALF):
        for rho in (Q(0), Q(1, 4), HALF, Q(1)):
            table = copy_grader_table(prior, Q(1, 10), Q(1, 5), Q(1, 5), rho)
            result = model_constraints(table)
            closed = copy_grader_residual(prior, Q(1, 10), Q(1, 5), rho)
            assert result["residuals"][1] == result["residuals"][2] == closed
            assert result["residuals"][3] == 0
            if prior == HALF or rho == 0:
                assert result["equalities_hold"]
            else:
                assert not result["equalities_hold"] and not result["passes"]
    assert copy_grader_table(Q(1, 4), Q(1, 10), Q(1, 5), Q(1, 5), Q(0)) == three_rater_model(Q(1, 4), (Q(1, 10), Q(1, 5), Q(1, 5)))


def test_sign_and_range_falsifiers():
    sign = model_constraints(LabelTable(SIGN_FALSIFIER))
    assert sign["negative_kappas"] == 1 and not sign["signs_consistent"] and not sign["model_consistent"]
    assert sign["kappas"] == {(1, 2): Q(-1, 5), (1, 3): Q(1, 5), (2, 3): Q(1, 5)}
    rng = model_constraints(LabelTable(RANGE_FALSIFIER))
    assert rng["squares"][1] == Q(144, 25) and rng["squares_in_unit_interval"] is False
    assert not rng["model_consistent"]
    with pytest.raises(ValueError):
        error_rate_from_square(rng["squares"][1])
    chance = model_constraints(three_rater_model(Q(1, 4), (Q(1, 10), HALF, Q(1, 5))))
    assert chance["chance_rater"] and not chance["identifiable"] and chance["squares"] is None


# --- record table and pipeline -----------------------------------------------

def test_record_table_matches_latent_enumeration_and_judge_note_forward_map():
    for prior in (Q(1, 4), HALF, Q(9, 10)):
        for accuracy, judge_error, eps1 in ((Q(4, 5), Q(1, 10), Q(1, 10)), (Q(4, 5), Q(1, 10), HALF),
                                            (Q(9, 10), Q(1, 5), Q(1, 5)), (Q(3, 5), Q(1, 4), Q(1, 2))):
            for eta1, eta2 in ((Q(1, 10), Q(1, 5)), (Q(0), Q(1, 4)), (Q(1, 20), Q(1, 20))):
                record = expected_record_table(1, prior, accuracy, judge_error, eps1, eta1, eta2)
                assert record.cells == _enumerate_record(prior, accuracy, judge_error, eps1, eta1, eta2)
                assert record.total == 1
                forward = gold_noise_forward(accuracy, judge_error, eps1, eta1)
                measured = measured_judge_rates(record, 1)
                assert measured["accuracy"] == forward["accuracy"]
                assert measured["judge_error"] == forward["judge_error"]
                assert measured["wrong_wrong_rate"] == forward["wrong_wrong_rate"]
                assert measured["eps1"] == forward["eps1"]
                second = measured_judge_rates(record, 2)
                assert second["accuracy"] == gold_noise_forward(accuracy, judge_error, eps1, eta2)["accuracy"]
                assert record.label_table() == three_rater_model(prior, (eta1, eta2, 1 - accuracy))


def test_inversion_closed_form_matches_judge_module_and_sensitivity():
    for accuracy, judge_error, eps1 in ((Q(4, 5), Q(1, 10), Q(1, 10)), (Q(4, 5), Q(1, 10), HALF),
                                        (Q(9, 10), Q(1, 5), Q(1, 5)), (Q(7, 10), Q(1, 4), Q(2, 5))):
        for eta in (Q(0), Q(1, 20), Q(1, 10), Q(1, 5)):
            forward = gold_noise_forward(accuracy, judge_error, eps1, eta)
            a, e, w = forward["accuracy"], forward["judge_error"], forward["wrong_wrong_rate"]
            assert inverted_eps1(a, e, w, eta) == eps1 == gold_noise_inverse(a, e, forward["eps1"], eta)["eps1"]
            for delta in (Q(1, 100), Q(-1, 100), Q(1, 50)):
                if not 0 <= eta + delta:
                    continue
                direct = inverted_eps1(a, e, w, eta + delta) - eps1
                assert eps1_displacement(a, e, w, eta, delta) == direct
                assert inverted_eps1(a, e, w, eta + delta) == gold_noise_inverse(a, e, forward["eps1"], eta + delta)["eps1"]
            derivative = eps1_sensitivity(a, e, w, eta)
            h = Q(1, 10 ** 8)
            secant = eps1_displacement(a, e, w, eta, h) / h
            assert abs(secant - derivative) < Q(1, 10 ** 5)
            assert eps1_sensitivity(a, e, w, eta) == eps1_displacement(a, e, w, eta, h) * (1 - a - eta - h) / (h * (1 - a - eta))


def test_pipeline_recovers_fixture_and_flags_copy_grader():
    record = expected_record_table(10000, Q(1, 4), Q(4, 5), Q(1, 10), Q(1, 10), Q(1, 10), Q(1, 5))
    result = calibrate(record, Q(1, 10), Q(1, 20))
    assert result["status"] == "exact" and result["valid"]
    assert result["eta1"]["exact"] == Q(1, 10) and result["eta2"]["exact"] == Q(1, 5)
    assert result["accuracy_from_identity"]["exact"] == Q(4, 5) and result["accuracy_consistent"]
    inversion = result["inversions"][0]
    assert inversion["recovered"] == {"accuracy": Q(4, 5), "judge_error": Q(1, 10), "eps1": Q(1, 10)}
    assert inversion["corrected_table"] == JudgeTable(7200, 800, 1800, 200)
    assert inversion["sensitivity_d_eps1_d_eta"] == -4
    assert result["measured"]["table"] == JudgeTable(6500, 900, 1700, 900)
    copied = calibrate(expected_record_table(10000, Q(1, 4), Q(4, 5), Q(1, 10), Q(1, 10), Q(1, 10), Q(1, 5), Q(1)),
                       Q(1, 10), Q(1, 20))
    assert copied["eta1"]["exact"] == 0 and copied["inversions"][0]["recovered"]["eps1"] == Q(9, 26)
    assert not copied["valid"] and not copied["constraints"]["equalities_hold"]
    assert copied["accuracy_consistent"]
    half = calibrate(expected_record_table(10000, Q(1, 4), Q(4, 5), Q(1, 10), Q(1, 10), Q(1, 10), Q(1, 5), HALF),
                     Q(1, 10), Q(1, 20))
    assert half["status"] == "bracketed" and len(half["inversions"]) == 2 and half["chain_sensitivity"] is None
    assert half["eta1"]["width"] <= RESOLUTION and half["accuracy_consistent"]
    low, high = (inv["recovered"]["eps1"] for inv in half["inversions"])
    assert low > high > Q(1, 10)


def test_pipeline_not_identified_when_a_rater_is_at_chance():
    record = expected_record_table(100, Q(1, 4), Q(4, 5), Q(1, 10), Q(1, 10), Q(1, 10), HALF)
    result = calibrate(record)
    assert result["status"] == "not_identified" and result["eta1"] is None and not result["valid"]
    plug_in = calibrate(expected_record_table(10000, Q(1, 4), Q(4, 5), Q(1, 10), Q(1, 10), Q(1, 10), Q(1, 5)))
    assert plug_in["inversions"][0]["tests"]["independence_error_is_plug_in"]
    assert plug_in["inversions"][0]["tests"]["independence_error"] == Q(1, 10)


def test_calibration_valid_needs_ledger_and_constraints():
    record = expected_record_table(10000, Q(1, 4), Q(4, 5), Q(1, 10), Q(1, 10), Q(1, 10), Q(1, 5))
    result = calibrate(record, Q(1, 10))
    once = measurement_ledger(("t0",), ("g0",), (LoopEvent(1, "judge_sample", "readout"),))
    twice = measurement_ledger(("t0",), ("g0",), (LoopEvent(1, "judge_sample", "readout"),
                                                  LoopEvent(2, "judge_sample", "score_query")))
    assert calibration_valid(result, once) and not calibration_valid(result, twice)


# --- sampling law ------------------------------------------------------------

FIXTURE_ERRORS = (Q(1, 10), Q(1, 5), Q(1, 5))


def _count_moments(m, errors):
    """Exact first and second moments of the agreement counts by listing every
    assignment of ``m`` items to the eight cells (``8^m`` sequences)."""

    table = three_rater_model(Q(1, 3), errors)
    first = {pair: Q(0) for pair in PAIRS}
    second = {(p, r): Q(0) for p in PAIRS for r in PAIRS}
    for items in product(CELLS3, repeat=m):
        weight = Q(1)
        for cell in items:
            weight *= table.probability(cell)
        counts = {pair: sum(1 for cell in items if cell[pair[0] - 1] == cell[pair[1] - 1]) for pair in PAIRS}
        for p in PAIRS:
            first[p] += weight * counts[p]
            for r in PAIRS:
                second[(p, r)] += weight * counts[p] * counts[r]
    return {(p, r): second[(p, r)] - first[p] * first[r] for p in PAIRS for r in PAIRS}


def test_agreement_covariance_matches_count_enumeration_and_closed_form():
    for m in (2, 3):
        for errors in (FIXTURE_ERRORS, (Q(1, 20), Q(1, 4), Q(2, 5))):
            sigma = agreement_covariance(three_rater_model(Q(1, 3), errors))
            assert _count_moments(m, errors) == {key: m * v for key, v in sigma.items()}
    for prior, errors in GRID:
        table = three_rater_model(prior, errors)
        sigma = agreement_covariance(table)
        assert sigma == agreement_covariance_model(errors)
        q = agreement_patterns(table)
        assert sum(q.values()) == 1
        kappas = pairwise_kappas(table)
        assert q["all"] == (1 + sum(kappas.values())) / 4
        for pair in PAIRS:
            assert q[pair] == agreement_rate(table, *pair) - q["all"]
        assert agreement_patterns(three_rater_model(Q(9, 10), errors)) == q


def test_delta_variance_closed_form_and_planning():
    delta = delta_variance(FIXTURE_ERRORS)
    assert delta["eta"] == Q(2401, 8100) and delta["root_of_eta_variance"] == Q(49, 90)
    assert delta["square"] == 16 * Q(16, 25) * delta["eta"]
    assert planning_size(FIXTURE_ERRORS, Q(1, 50)) == 742
    assert Q(2401, 8100) / 742 < Q(1, 2500) <= Q(2401, 8100) / 741
    for errors in (FIXTURE_ERRORS, (Q(1, 20), Q(1, 10), Q(1, 10)), (Q(1, 5), Q(1, 4), Q(3, 10)), (Q(0), Q(1, 10), Q(1, 5))):
        table = three_rater_model(Q(1, 4), errors)
        assert delta_variance_from_table(table) == delta_variance(errors)["eta"]
        d1, d2, d3 = (1 - 2 * e for e in errors)
        g = delta_variance(errors)["gradient_per_agreement_rate"]
        assert g == {pair: 2 * v for pair, v in eta_gradient(pairwise_kappas(table), 1)["per_kappa"].items()}
        assert g == {(1, 2): -1 / (2 * d2), (1, 3): -1 / (2 * d3), (2, 3): d1 / (2 * d2 * d3)}
    assert delta_variance_from_table(copy_grader_table(Q(1, 4), Q(1, 10), Q(1, 5), Q(1, 5), HALF)) is None
    with pytest.raises(ValueError):
        delta_variance((Q(1, 2), Q(1, 5), Q(1, 5)))


def test_sampling_law_reduction_equals_label_table_enumeration():
    keys = ("p_undefined_sign", "p_undefined_range", "p_exact", "p_bracketed", "p_within_tolerance",
            "square_mean", "square_variance", "root_mean_bracket", "eta_mean_bracket")
    for m, errors in ((8, FIXTURE_ERRORS), (12, FIXTURE_ERRORS), (8, (Q(1, 5), Q(1, 4), Q(3, 10)))):
        reduced, tables = sampling_law(m, errors), sampling_law_by_tables(m, errors)
        assert all(reduced[k] == tables[k] for k in keys)
        assert reduced["compositions"] < tables["compositions"]
        total = reduced["p_undefined"] + reduced["p_exact"] + reduced["p_bracketed"]
        assert total == 1 and reduced["p_defined"] == 1 - reduced["p_undefined"]
        assert sum(tables["square_distribution"].values()) == reduced["p_defined"]
        assert all(0 < s <= 1 for s in tables["square_distribution"])
        mean = sum((s * p for s, p in tables["square_distribution"].items()), Q(0)) / reduced["p_defined"]
        assert mean == reduced["square_mean"]
        lo, hi = reduced["eta_mean_bracket"]
        assert 0 <= lo < hi <= HALF and hi - lo <= Q(1, 2 ** 17)
        vlo, vhi = reduced["eta_variance_bracket"]
        assert 0 <= vlo <= vhi
        assert reduced["p_within_tolerance_given_defined"] == reduced["p_within_tolerance"] / reduced["p_defined"]
    one = sampling_law(1, FIXTURE_ERRORS)
    q_all = agreement_patterns(three_rater_model(Q(1, 4), FIXTURE_ERRORS))["all"]
    assert one["p_defined"] == one["p_exact"] == q_all and one["square_mean"] == 1 and one["square_variance"] == 0


def test_sampling_law_is_prior_free_and_tolerance_is_exact():
    law = sampling_law(12, FIXTURE_ERRORS, Q(1, 50))
    assert law["pattern_probabilities"] == {str(k): v for k, v in agreement_patterns(three_rater_model(Q(9, 10), FIXTURE_ERRORS)).items()}
    wide = sampling_law(12, FIXTURE_ERRORS, HALF)
    assert wide["p_within_tolerance"] == wide["p_defined"]
    tables = sampling_law_by_tables(12, FIXTURE_ERRORS, Q(1, 50))
    low, high = (1 - 2 * (Q(1, 10) + Q(1, 50))) ** 2, (1 - 2 * (Q(1, 10) - Q(1, 50))) ** 2
    assert law["p_within_tolerance"] == sum((p for s, p in tables["square_distribution"].items() if low <= s <= high), Q(0))


def test_disagreement_bound_and_fast_tail():
    for n in (1, 5, 9):
        for k in range(0, n + 2):
            for p in (Q(0), Q(1, 3), Q(3, 4), Q(1)):
                assert _binomial_upper_tail(n, p, k) == binomial_upper_tail(n, p, k)
    bound = disagreement_bound(100, 74, Q(1, 20))
    low, high = bound["lower_endpoint_bracket"]
    assert high - low <= RESOLUTION and bound["eta_upper_bound"] == 1 - low
    assert _binomial_upper_tail(100, low, 74) < Q(1, 20) <= _binomial_upper_tail(100, high, 74)
    assert bound["eta_upper_bound"] > bound["eta_upper_bound_at_population_rate"] == Q(13, 50)
    assert disagreement_bound(100, 74, Q(1, 100))["eta_upper_bound"] > bound["eta_upper_bound"]
    assert disagreement_bound(10, 0, Q(1, 20))["eta_upper_bound"] == 1
    assert disagreement_bound(10, 10, Q(1, 20))["eta_upper_bound"] < Q(3, 10)


def test_root_bracket_agrees_with_bisection():
    for square in (Q(148, 175), Q(1, 2), Q(2, 3), Q(1, 10), Q(9, 25), Q(16, 25), Q(0), Q(1)):
        root = root_bracket(square)
        bisect = error_rate_bracket(square)
        if root["exact"] is not None:
            assert root["exact"] == exact_square_root(square) and bisect["exact"] == (1 - root["exact"]) / 2
            continue
        assert root["upper"] - root["lower"] == Q(1, 2 ** 16)
        assert root["lower"] ** 2 <= square < root["upper"] ** 2
        eta_low, eta_high = (1 - root["upper"]) / 2, (1 - root["lower"]) / 2
        assert bisect["lower"] <= eta_high and eta_low <= bisect["upper"]
        assert error_rate_at_most(square, eta_high) and not error_rate_at_most(square, eta_low)


# --- asymmetric model --------------------------------------------------------

DS_GRID_PAIRS = ((Q(1, 10), Q(1, 20)), (Q(1, 5), Q(1, 10)), (Q(0), Q(1, 4)), (Q(3, 10), Q(3, 10)), (Q(1, 2), Q(1, 2)))


def _enumerate_ds(prior, fn, fp):
    cells = {cell: Q(0) for cell in CELLS3}
    for y, x1, x2, x3 in product((0, 1), repeat=4):
        w = prior if y else 1 - prior
        for x, a, b in zip((x1, x2, x3), fn, fp):
            hit = (1 - a) if y else b
            w *= hit if x == 1 else 1 - hit
        cells[(x1, x2, x3)] += w
    return cells


def _enumerate_record_asymmetric(prior, controller, judge_error, eps1, gold, second):
    acc = {1: 1 - controller[0], 0: 1 - controller[1]}
    accuracy = prior * acc[1] + (1 - prior) * acc[0]
    eps0 = (judge_error - (1 - accuracy) * eps1) / accuracy
    cells = {}
    for y, x, v, g1, g2 in product((0, 1), repeat=5):
        w = prior if y else 1 - prior
        right = x == y
        w *= acc[y] if right else 1 - acc[y]
        says = (1 - eps0) if right else eps1
        w *= says if v else 1 - says
        for g, (a, b) in ((g1, gold), (g2, second)):
            hit = (1 - a) if y else b
            w *= hit if g == 1 else 1 - hit
        cells[(x, v, g1, g2)] = cells.get((x, v, g1, g2), Q(0)) + w
    return cells


def test_dawid_skene_round_trip_on_grid_with_both_conventions():
    for prior in (Q(1, 4), Q(1, 3), HALF, Q(7, 10)):
        for pairs in product(DS_GRID_PAIRS, repeat=3):
            fn, fp = tuple(p[0] for p in pairs), tuple(p[1] for p in pairs)
            table = dawid_skene_model(prior, fn, fp)
            assert table.cells == _enumerate_ds(prior, fn, fp)
            moments = dawid_skene_moments(table)
            u = prior * (1 - prior)
            deltas = [1 - a - b for a, b in zip(fn, fp)]
            for i, j in PAIRS:
                assert moments["covariances"][(i, j)] == u * deltas[i - 1] * deltas[j - 1]
            assert moments["third_cumulant"] == u * (1 - 2 * prior) * deltas[0] * deltas[1] * deltas[2]
            assert moments["radicand"] == (u * deltas[0] * deltas[1] * deltas[2]) ** 2
            fit = dawid_skene_three_raters(table)
            if any(d == 0 for d in deltas):
                assert fit["status"] == "not_identified"
                continue
            assert fit["status"] == "exact" and fit["in_range"]
            assert fit["solution"]["prior"] == prior
            for i in (1, 2, 3):
                assert fit["solution"]["false_negatives"][i] == fn[i - 1]
                assert fit["solution"]["false_positives"][i] == fp[i - 1]
            alt = fit["alternative"]
            assert alt["prior"] == 1 - prior
            assert dawid_skene_model(alt["prior"], tuple(alt["false_negatives"][i] for i in (1, 2, 3)),
                                     tuple(alt["false_positives"][i] for i in (1, 2, 3))) == table
            assert dawid_skene_three_raters(table, "rater_1_informative")["solution"] == fit["solution"]


def test_dawid_skene_symmetric_special_case_and_rank():
    for prior, errors in GRID:
        if prior in (Q(0), Q(1)) or any(e >= HALF for e in errors):
            continue
        table = three_rater_model(prior, errors)
        fit = dawid_skene_three_raters(table)
        squares = polarity_squares(pairwise_kappas(table))
        assert fit["status"] == "exact" and fit["solution"]["prior"] == prior
        for i in (1, 2, 3):
            assert fit["solution"]["false_negatives"][i] == fit["solution"]["false_positives"][i] == errors[i - 1]
            assert error_rate_from_square(squares[i]) == errors[i - 1]
        assert dawid_skene_jacobian_rank(prior, errors, errors) == 7
    assert dawid_skene_jacobian_rank(DS_PRIOR, DS_FALSE_NEGATIVES, DS_FALSE_POSITIVES) == 7
    assert dawid_skene_jacobian_rank(DS_PRIOR, (Q(1, 10), HALF, Q(1, 10)), (Q(1, 5), HALF, Q(3, 10))) < 7
    assert dawid_skene_jacobian_rank(Q(0), DS_FALSE_NEGATIVES, DS_FALSE_POSITIVES) < 7


def test_dawid_skene_conventions_falsifiers_and_brackets():
    anti = dawid_skene_model(DS_PRIOR, (Q(1, 10), ANTI_INFORMATIVE_SECOND[0], Q(1, 10)),
                             (Q(1, 5), ANTI_INFORMATIVE_SECOND[1], Q(3, 10)))
    assert dawid_skene_three_raters(anti)["status"] == "convention_violated"
    found = dawid_skene_three_raters(anti, "rater_1_informative")
    assert found["status"] == "exact" and found["solution"]["prior"] == DS_PRIOR
    assert found["solution"]["deltas"][2] == -Q(1, 5) and found["solution"]["false_negatives"][2] == Q(3, 5)
    outside = dawid_skene_three_raters(LabelTable(OUTSIDE_MODEL))
    assert outside["status"] == "outside_model" and outside["radicand"] < 0
    assert dawid_skene_three_raters(LabelTable({(0, 0, 0): 1, (0, 1, 1): 1, (1, 0, 1): 1, (1, 1, 0): 1}))["status"] == "not_identified"
    table = dawid_skene_model(DS_PRIOR, DS_FALSE_NEGATIVES, DS_FALSE_POSITIVES)
    cells = dict(table.cells)
    cells[(0, 0, 1)] += Q(1, 100)
    cells[(1, 1, 0)] -= Q(1, 100)
    perturbed = dawid_skene_three_raters(LabelTable(cells))
    assert perturbed["status"] == "bracketed" and perturbed["in_range"]
    low, high = perturbed["root_bracket"]
    assert high - low == Q(1, 2 ** 16) and low ** 2 <= perturbed["radicand"] < high ** 2
    for key in ("false_negatives", "false_positives", "deltas"):
        for i in (1, 2, 3):
            lo, hi = perturbed["solution"][key][i]
            assert lo <= hi
    assert perturbed["solution"]["prior"][0] < perturbed["solution"]["prior"][1]
    copied = dawid_skene_three_raters(copy_grader_table(Q(1, 4), Q(1, 10), Q(1, 5), Q(1, 5), Q(1)))
    assert copied["status"] == "exact" and copied["in_range"] and copied["solution"]["false_negatives"][1] == 0


def test_asymmetric_record_forward_inverse_and_symmetric_reduction():
    gold, second, controller = (Q(1, 10), Q(1, 5)), (Q(1, 5), Q(1, 10)), (Q(1, 10), Q(3, 10))
    for prior in (Q(1, 4), HALF, Q(9, 10)):
        for judge_error, eps1 in ((Q(1, 10), Q(1, 10)), (Q(1, 10), Q(2, 5)), (Q(1, 5), Q(1, 5))):
            record = expected_record_table_asymmetric(1, prior, controller, judge_error, eps1, gold, second)
            assert record.cells == _enumerate_record_asymmetric(prior, controller, judge_error, eps1, gold, second)
            assert record.label_table() == dawid_skene_model(prior, (gold[0], second[0], controller[0]),
                                                             (gold[1], second[1], controller[1]))
            forward = asymmetric_gold_noise_forward(prior, controller, judge_error, eps1, gold)
            measured = measured_judge_rates(record, 1)
            assert measured["accuracy"] == forward["accuracy"] and measured["judge_error"] == forward["judge_error"]
            assert measured["wrong_wrong_rate"] == forward["wrong_wrong_rate"]
            cells = measured["cells"]
            assert cells["right_right"] + cells["wrong_wrong"] == forward["agreement_rate"]
            inverse = asymmetric_gold_noise_inverse(prior, controller, gold, forward["accuracy"],
                                                    forward["judge_error"], forward["wrong_wrong_rate"])
            assert inverse["eps1"] == eps1 and inverse["judge_error"] == judge_error
            assert inverse["accuracy"] == forward["true_accuracy"] and inverse["eps0"] == forward["eps0"]
            assert inverse["measured_accuracy_consistent"]
    for accuracy, judge_error, eps1 in ((Q(4, 5), Q(1, 10), Q(1, 10)), (Q(7, 10), Q(1, 4), Q(2, 5))):
        for eta in (Q(0), Q(1, 20), Q(1, 10)):
            sym = gold_noise_forward(accuracy, judge_error, eps1, eta)
            asym = asymmetric_gold_noise_forward(Q(1, 3), (1 - accuracy, 1 - accuracy), judge_error, eps1, (eta, eta))
            assert all(asym[k] == sym[k] for k in ("accuracy", "judge_error", "wrong_wrong_rate", "agreement_rate"))
            inverse = asymmetric_gold_noise_inverse(Q(1, 3), (1 - accuracy, 1 - accuracy), (eta, eta),
                                                    sym["accuracy"], sym["judge_error"], sym["wrong_wrong_rate"])
            assert inverse["eps1"] == gold_noise_inverse(sym["accuracy"], sym["judge_error"], sym["eps1"], eta)["eps1"]
            assert inverse["determinant"] == accuracy * (1 - accuracy) * (1 - 2 * eta)


def test_calibrate_asymmetric_recovers_and_symmetric_pipeline_misreads():
    gold, second, controller = (Q(1, 10), Q(1, 5)), (Q(1, 5), Q(1, 10)), (Q(1, 10), Q(3, 10))
    record = expected_record_table_asymmetric(4000, Q(1, 4), controller, Q(1, 10), Q(1, 10), gold, second)
    result = calibrate_asymmetric(record, Q(1, 10), Q(1, 20))
    assert result["status"] == "exact" and result["fit"]["in_range"]
    inversion = result["inversions"][0]
    assert inversion["recovered"]["eps1"] == Q(1, 10) and inversion["recovered"]["accuracy"] == Q(3, 4)
    assert inversion["corrected_table"] == JudgeTable(2700, 300, 900, 100)
    assert inversion["tests"]["independence_p"] > Q(1, 20)
    symmetric = calibrate(record, Q(1, 10), Q(1, 20))
    assert symmetric["status"] == "bracketed" and not symmetric["constraints"]["passes"]
    assert all(inv["recovered"]["eps1"] > Q(12, 100) for inv in symmetric["inversions"])
    marginal = Q(1, 4) * gold[0] + Q(3, 4) * gold[1]
    assert marginal == Q(7, 40)
    measured = result["measured"]
    assert inverted_eps1(measured["accuracy"], measured["judge_error"], measured["wrong_wrong_rate"], marginal) == Q(5, 62)
    chance = calibrate_asymmetric(expected_record_table_asymmetric(100, Q(1, 4), controller, Q(1, 10), Q(1, 10), gold, (HALF, HALF)))
    assert chance["status"] == "not_identified" and chance["inversions"] == []
    bracketed = calibrate_asymmetric(expected_record_table(10000, Q(1, 4), Q(4, 5), Q(1, 10), Q(1, 10), Q(1, 10), Q(1, 5), HALF), Q(1, 10))
    assert bracketed["status"] == "bracketed" and len(bracketed["inversions"]) == 2
    assert bracketed["bracket_ends_are_a_bracket_only_if_monotone"]


# --- four raters -------------------------------------------------------------

FOUR_GRID_PAIRS = ((Q(1, 10), Q(1, 20)), (Q(1, 5), Q(1, 10)), (Q(0), Q(1, 4)), (Q(3, 10), Q(3, 10)))
FOUR_GRID_PRIORS = (Q(1, 4), Q(1, 3), HALF, Q(7, 10))


def _enumerate_four(prior, fn, fp):
    """All 2^5 latent cells (Y, X_1, X_2, X_3, X_4); returns the label table as a dict."""

    cells = {cell: Q(0) for cell in CELLS4}
    for y, *xs in product((0, 1), repeat=5):
        w = prior if y else 1 - prior
        for x, a, b in zip(xs, fn, fp):
            hit = (1 - a) if y else b
            w *= hit if x == 1 else 1 - hit
        cells[tuple(xs)] += w
    return cells


def _central_moment(cells, subset):
    p = {i: sum((w for c, w in cells.items() if c[i - 1] == 1), Q(0)) for i in range(1, 5)}
    total = Q(0)
    for cell, w in cells.items():
        for i in subset:
            w *= cell[i - 1] - p[i]
        total += w
    return total


def test_four_rater_moments_match_latent_enumeration_and_closed_forms():
    for prior in FOUR_GRID_PRIORS:
        for pairs in product(FOUR_GRID_PAIRS, repeat=4):
            fn, fp = tuple(p[0] for p in pairs), tuple(p[1] for p in pairs)
            table = four_rater_model(prior, fn, fp)
            cells = _enumerate_four(prior, fn, fp)
            assert table.cells == cells and table.total == 1
            moments = four_rater_moments(table)
            u, d = prior * (1 - prior), [1 - a - b for a, b in zip(fn, fp)]
            for i, j in PAIRS4:
                assert moments["covariances"][(i, j)] == _central_moment(cells, (i, j)) == u * d[i - 1] * d[j - 1]
            for t in TRIPLES4:
                assert moments["third_moments"][t] == _central_moment(cells, t) \
                    == u * (1 - 2 * prior) * d[t[0] - 1] * d[t[1] - 1] * d[t[2] - 1]
            assert moments["fourth_moment"] == _central_moment(cells, (1, 2, 3, 4)) == u * (1 - 3 * u) * d[0] * d[1] * d[2] * d[3]
            assert all(r == 0 for r in four_rater_residuals(moments).values())
            assert all(r == 0 for r in ratio_relations(moments).values()) and len(ratio_relations(moments)) == 12


def test_six_constraints_are_independent_and_the_model_has_rank_nine():
    for prior in FOUR_GRID_PRIORS:
        for pairs in product(FOUR_GRID_PAIRS[:2] + FOUR_GRID_PAIRS[3:], repeat=4):
            fn, fp = tuple(p[0] for p in pairs), tuple(p[1] for p in pairs)
            assert four_rater_jacobian_rank(prior, fn, fp) == 9
            assert constraint_jacobian_rank(four_rater_moments(four_rater_model(prior, fn, fp))) == 6
    assert len(CONSTRAINTS4) == 15 - 9
    for rater in range(4):
        fn = tuple(HALF if i == rater else a for i, a in enumerate(FOUR_FALSE_NEGATIVES))
        fp = tuple(HALF if i == rater else b for i, b in enumerate(FOUR_FALSE_POSITIVES))
        assert four_rater_jacobian_rank(FOUR_PRIOR, fn, fp) == 9
        table = four_rater_model(FOUR_PRIOR, fn, fp)
        assert all(r == 0 for r in four_rater_residuals(four_rater_moments(table)).values())
        assert four_rater_constraints(table)["fit"]["status"] == "not_identified"
        assert not four_rater_constraints(table)["identifiable"]
    two_chance = four_rater_model(FOUR_PRIOR, (HALF, HALF, Q(1, 5), Q(1, 10)), (HALF, HALF, Q(2, 5), Q(3, 10)))
    assert four_rater_jacobian_rank(FOUR_PRIOR, (HALF, HALF, Q(1, 5), Q(1, 10)), (HALF, HALF, Q(2, 5), Q(3, 10))) < 9
    assert not four_rater_constraints(two_chance)["passes"]
    assert four_rater_jacobian_rank(Q(0), FOUR_FALSE_NEGATIVES, FOUR_FALSE_POSITIVES) < 9


def test_ratio_relations_follow_from_three_of_them_and_the_tetrads():
    """Moment points that satisfy the six equalities but come from no table:
    the other nine ratio relations still vanish (an algebraic consequence)."""

    for c12, c13, c14, c23, k123 in ((Q(1, 7), Q(2, 9), Q(-3, 11), Q(5, 13), Q(1, 17)),
                                     (Q(-2, 5), Q(3, 4), Q(1, 6), Q(-7, 8), Q(-4, 9)),
                                     (Q(1), Q(1), Q(1), Q(1), Q(0))):
        c24, c34 = c14 * c23 / c13, c14 * c23 / c12
        third = {(1, 2, 3): k123, (1, 2, 4): k123 * c14 / c13, (1, 3, 4): k123 * c14 / c12,
                 (2, 3, 4): k123 * c24 / c12}
        cov = {(1, 2): c12, (1, 3): c13, (1, 4): c14, (2, 3): c23, (2, 4): c24, (3, 4): c34}
        fourth = c12 * c34 + third[(1, 2, 3)] * third[(1, 2, 4)] / c12
        moments = {"marginals": {i: Q(1, 2) for i in range(1, 5)}, "covariances": cov,
                   "third_moments": third, "fourth_moment": fourth}
        assert all(r == 0 for r in four_rater_residuals(moments).values())
        assert all(r == 0 for r in ratio_relations(moments).values())
        assert constraint_jacobian_rank(moments) == 6
        moved = dict(moments)
        moved["covariances"] = dict(cov)
        moved["covariances"][(3, 4)] = c34 + Q(1, 100)
        residuals = four_rater_residuals(moved)
        assert residuals["tetrad_12_34_vs_13_24"] == c12 * Q(1, 100) and residuals["tetrad_13_24_vs_14_23"] == 0
    # the rank-6 minor needs only c_12 c_13 != 0, at moment points of no model
    values = [Q(k, 7) for k in (-3, -1, 1, 2, 5)]
    for shift in range(5):
        cov = {pair: values[(index + shift) % 5] + index for index, pair in enumerate(PAIRS4)}
        third = {t: values[(index + 2 * shift) % 5] for index, t in enumerate(TRIPLES4)}
        point = {"marginals": {i: Q(1, 3) for i in range(1, 5)}, "covariances": cov,
                 "third_moments": third, "fourth_moment": Q(shift, 11)}
        assert cov[(1, 2)] * cov[(1, 3)] != 0 and constraint_jacobian_rank(point) == 6


def test_four_rater_fixture_recovers_nine_parameters_and_rebuilds_grid_tables():
    table = four_rater_model(FOUR_PRIOR, FOUR_FALSE_NEGATIVES, FOUR_FALSE_POSITIVES)
    assert all((10000 * w).denominator == 1 for w in table.cells.values())
    assert [10000 * table.cells[c] for c in CELLS4] == [2269, 981, 1516, 684, 256, 144, 184, 216,
                                                         576, 324, 414, 486, 99, 351, 186, 1314]
    counts = FourRaterTable({c: 10000 * w for c, w in table.cells.items()})
    result = four_rater_constraints(counts)
    assert result["passes"] and result["fit"]["status"] == "exact" and result["reproduces_table"]
    solution = result["fit"]["solution"]
    assert solution["prior"] == FOUR_PRIOR
    for i in range(4):
        assert solution["false_negatives"][i + 1] == FOUR_FALSE_NEGATIVES[i]
        assert solution["false_positives"][i + 1] == FOUR_FALSE_POSITIVES[i]
    assert solution["deltas"] == {1: Q(7, 10), 2: Q(7, 10), 3: Q(2, 5), 4: Q(3, 5)}
    for drop in (1, 2, 3, 4):
        assert counts.triple(drop).total == 10000
    for prior in FOUR_GRID_PRIORS:
        for pairs in product(FOUR_GRID_PAIRS, repeat=4):
            fn, fp = tuple(p[0] for p in pairs), tuple(p[1] for p in pairs)
            check = four_rater_constraints(four_rater_model(prior, fn, fp))
            assert check["passes"] and check["reproduces_table"] and check["fit"]["solution"]["prior"] == prior
            assert all(check["fit"]["solution"]["false_negatives"][i + 1] == fn[i] for i in range(4))
            assert all(check["fit"]["solution"]["false_positives"][i + 1] == fp[i] for i in range(4))


def test_four_rater_conventions_and_inequality_failures():
    anti_fn = (FOUR_FALSE_NEGATIVES[0], ANTI_INFORMATIVE_SECOND[0]) + FOUR_FALSE_NEGATIVES[2:]
    anti_fp = (FOUR_FALSE_POSITIVES[0], ANTI_INFORMATIVE_SECOND[1]) + FOUR_FALSE_POSITIVES[2:]
    anti = four_rater_model(FOUR_PRIOR, anti_fn, anti_fp)
    assert four_rater_constraints(anti)["fit"]["status"] == "convention_violated"
    oriented = four_rater_constraints(anti, "rater_1_informative")
    assert oriented["passes"] and oriented["fit"]["status"] == "exact" and oriented["reproduces_table"]
    assert oriented["fit"]["solution"]["deltas"][2] == -Q(1, 5)
    assert oriented["fit"]["solution"]["false_positives"][2] == ANTI_INFORMATIVE_SECOND[1]
    # all four raters informative: the rater-1 convention agrees with the default
    table = four_rater_model(FOUR_PRIOR, FOUR_FALSE_NEGATIVES, FOUR_FALSE_POSITIVES)
    assert dawid_skene_four_raters(table, "rater_1_informative")["solution"] == dawid_skene_four_raters(table)["solution"]
    cells = dict(table.cells)
    cells[(0, 0, 0, 1)] += Q(1, 100)
    cells[(1, 1, 1, 0)] -= Q(1, 100)
    perturbed = four_rater_constraints(FourRaterTable(cells))
    assert not perturbed["equalities_hold"] and not perturbed["passes"]
    outside = {(a, b, c, d): OUTSIDE_MODEL.get((a, b, c), Q(0)) if d == a else Q(0) for a, b, c, d in CELLS4}
    result = four_rater_constraints(FourRaterTable(outside))
    assert result["identifiable"] and result["fit"]["status"] == "outside_model" and not result["passes"]


def test_copy_grader_violates_a_tetrad_with_the_closed_form_residual():
    rate_sets = ((FOUR_FALSE_NEGATIVES, FOUR_FALSE_POSITIVES),
                 ((Q(1, 10), Q(1, 5), Q(3, 10), Q(1, 5)), (Q(1, 10), Q(1, 5), Q(3, 10), Q(1, 5))))
    for fn, fp in rate_sets:
        for prior in (Q(1, 4), HALF, Q(2, 3)):
            for rho in (Q(0), Q(1, 4), HALF, Q(1)):
                table = copy_grader_table4(prior, fn, fp, rho)
                result = four_rater_constraints(table)
                closed = copy_grader_tetrad_residual(prior, fn, fp, rho)
                u = prior * (1 - prior)
                v1 = prior * fn[0] * (1 - fn[0]) + (1 - prior) * fp[0] * (1 - fp[0])
                assert closed == rho * v1 * u * (1 - fn[2] - fp[2]) * (1 - fn[3] - fp[3])
                assert result["residuals"]["tetrad_12_34_vs_13_24"] == closed
                assert result["residuals"]["tetrad_13_24_vs_14_23"] == 0
                assert result["residuals"]["third_123_vs_124"] == 0
                if rho == 0:
                    assert table == four_rater_model(prior, fn, fp) and result["passes"]
                else:
                    assert closed != 0 and not result["equalities_hold"] and not result["passes"]
    witness = copy_grader_table4(FOUR_PRIOR, FOUR_FALSE_NEGATIVES, FOUR_FALSE_POSITIVES, Q(1))
    assert [10000 * witness.cells[c] for c in CELLS4] == [2525, 1125, 1700, 900] + [0] * 8 + [675, 675, 600, 1800]
    absorbed = dawid_skene_three_raters(witness.triple(4))
    assert absorbed["status"] == "exact" and absorbed["in_range"] and absorbed["solution"]["prior"] == Q(3, 8)
    assert dawid_skene_four_raters(witness)["status"] == "inconsistent"
    balanced = copy_grader_table(HALF, Q(1, 10), Q(1, 5), Q(1, 5), Q(1))
    assert model_constraints(balanced)["vacuous_at_balanced_prior"] and model_constraints(balanced)["equalities_hold"]


# --- the joint statement -----------------------------------------------------

def test_agreement_counts_keep_parity_and_observed_square_validates():
    record = expected_record_table(742, Q(1, 4), Q(4, 5), Q(1, 10), Q(1, 10), Q(1, 10), Q(1, 5))
    counts = agreement_counts(record)
    assert counts["patterns"] == {"all": 430, (1, 2): 119, (1, 3): 119, (2, 3): 74} and counts["rounded"]
    assert counts["counts"] == {(1, 2): 549, (1, 3): 549, (2, 3): 504}
    assert sum(counts["counts"].values()) - 742 == 2 * counts["patterns"]["all"]
    assert observed_square(742, counts["counts"]) == Q(356 * 356, 742 * 266) == Q(31684, 49343)
    with pytest.raises(ValueError):
        observed_square(742, {(1, 2): 549, (1, 3): 549, (2, 3): 505})
    exact = agreement_counts(expected_record_table(4000, Q(1, 4), Q(4, 5), Q(1, 10), Q(1, 10), Q(1, 10), Q(1, 5)))
    assert not exact["rounded"] and observed_square(4000, exact["counts"]) == Q(16, 25)
    assert observed_square(10, {(1, 2): 5, (1, 3): 9, (2, 3): 6}) == "sign"
    assert observed_square(10, {(1, 2): 9, (1, 3): 9, (2, 3): 8}) == "range"
    for m in (1, 2, 5):
        for k in product(range(m + 1), repeat=4):
            if sum(k) != m:
                continue
            n = {(1, 2): k[0] + k[1], (1, 3): k[0] + k[2], (2, 3): k[0] + k[3]}
            assert observed_square(m, n) in ("sign", "range") or 0 < observed_square(m, n) <= 1


def test_binomial_window_bounds_the_exact_pmf():
    for n, num, den in ((0, 1, 3), (7, 0, 5), (7, 5, 5), (30, 2, 7), (200, 29, 50), (200, 1, 50)):
        for bits, cut in ((160, 128), (40, 20)):
            window = _binomial_window(n, num, den, bits, cut)
            one = 1 << bits
            pmf = [Q(comb(n, k) * num ** k * (den - num) ** (n - k), den ** n) for k in range(n + 1)]
            inside = 0
            for offset, (lo, hi) in enumerate(zip(window["lo"], window["hi"])):
                k = window["start"] + offset
                assert lo <= pmf[k] * one <= hi and hi - lo <= 2 * (n + 1)
                inside += pmf[k]
            assert (1 - inside) * one <= window["outside"]
    assert len(_binomial_window(200, 29, 50, 40, 20)["lo"]) < 201


def test_square_tail_bracket_contains_the_exact_law():
    errors = (Q(1, 10), Q(1, 5), Q(1, 5))
    tables = sampling_law_by_tables(12, errors)
    for s in list(tables["square_distribution"])[::5] + [Q(0), HALF, Q(1), "sign", "range"]:
        exact, bracket = square_tail_law(12, errors, s), square_tail_bracket(12, errors, s)
        for key in ("p_lower", "p_upper", "p_two_sided"):
            assert bracket[key][0] <= exact[key] <= bracket[key][1]
        assert bracket["width"] < Q(1, 2 ** 100)
        coarse = square_tail_bracket(12, errors, s, 48, 24)
        assert coarse["p_two_sided"][0] <= exact["p_two_sided"] <= coarse["p_two_sided"][1]
    for m, errs, s in ((60, (Q(0), Q(1, 4), Q(1, 10)), Q(2, 3)), (90, (Q(1, 5), Q(1, 4), Q(3, 10)), Q(1, 4))):
        exact, bracket = square_tail_law(m, errs, s), square_tail_bracket(m, errs, s)
        assert bracket["p_defined"][0] <= 1 - exact["p_sign"] <= bracket["p_defined"][1]
        assert bracket["p_two_sided"][0] <= exact["p_two_sided"] <= bracket["p_two_sided"][1]
    for observed in ("sign", "range", Q(16, 25)):
        extra = square_tail_law(12, errors, observed, (HALF, Q(9, 10)))["extra_lower"]
        assert extra == {t: square_tail_law(12, errors, t)["p_lower"] for t in (HALF, Q(9, 10))}
    level = square_tail_law(40, errors, Q(16, 25))["p_two_sided"]
    forced = square_test((40, errors, Q(16, 25), level))
    assert forced["decided_by"] == "exact law" and forced["retained"] and forced["p_exact"] == level
    assert square_test((40, errors, Q(16, 25), Q(1, 40)))["decided_by"] == "bracket"


def test_clamped_inversion_matches_the_closed_form_where_feasible():
    a, e, w = Q(37, 50), Q(9, 50), Q(9, 100)
    for eta in (Q(0), Q(1, 20), Q(1, 10), Q(1, 5)):
        rates = clamped_inversion(a, e, w, eta)
        assert rates["eps1"] == inverted_eps1(a, e, w, eta) or rates["clamped"]
        assert rates["accuracy"] == (a - eta) / (1 - 2 * eta)
    assert not clamped_inversion(a, e, w, Q(1, 10))["clamped"]
    clamped = clamped_inversion(a, e, w, Q(1, 4))
    assert clamped["clamped"] and clamped["raw"]["eps1"] < 0 == clamped["eps1"]
    assert clamped_inversion(a, e, w, Q(13, 50)) is None and clamped_inversion(Q(1, 5), e, w, Q(1, 5)) is None


def test_eta_confidence_set_and_joint_statement_structure():
    record = expected_record_table(300, Q(1, 4), Q(4, 5), Q(1, 10), Q(1, 10), Q(1, 10), Q(1, 5))
    grid = tuple(Q(k, 50) for k in range(25))
    statement = joint_statement(record, Q(1, 20), grid, Q(1, 10))
    eta_set = statement["eta_set"]
    assert statement["square_test_used"] and eta_set["level_per_test"] == Q(1, 40)
    assert Q(1, 10) in eta_set["retained"] and eta_set["is_grid_interval"] and eta_set["exact_fallbacks"] == 0
    assert all(row["passes_disagreement_bound"] or not row["retained"] for row in eta_set["rows"])
    assert statement["coverage"] == Q(9, 10)
    bound_only = eta_confidence_set(300, eta_set["counts"], Q(1, 5), Q(4, 5), Q(1, 40), grid, False)
    assert set(eta_set["retained"]) <= set(bound_only["retained"])
    assert bound_only["retained"] == [e for e in grid if e <= bound_only["disagreement_bound"]["eta_upper_bound"]]
    if statement["status"] == "stated":
        low, high = statement["eps1_range"]
        assert all(low <= row["eps1_bracket"][0] <= row["eps1_bracket"][1] <= high
                   for row in statement["inversions"])
    shared = joint_statement(expected_record_table(300, Q(1, 4), Q(4, 5), Q(1, 10), HALF, Q(1, 10), Q(1, 5)),
                             Q(1, 20), grid, Q(1, 10), True, eta_set)
    assert shared["eta_set"] is eta_set
    assert judges_separated(statement, shared) == (statement["eps1_range"] is not None and shared["eps1_range"] is not None
                                                   and statement["eps1_range"][1] < shared["eps1_range"][0])
    copied = joint_statement(expected_record_table(300, Q(1, 4), Q(4, 5), Q(1, 10), Q(1, 10), Q(1, 10), Q(1, 5), Q(1)),
                             Q(1, 20), grid, Q(1, 10))
    assert copied["status"] == "withheld_constraints_fail" and copied["eta_set"] is None
    chance = joint_statement(expected_record_table(300, Q(1, 4), Q(4, 5), Q(1, 10), Q(1, 10), Q(1, 10), HALF),
                             Q(1, 20), grid)
    assert chance["status"] == "not_identified"
    with pytest.raises(ValueError):
        joint_statement(expected_record_table(300, Q(1, 4), Q(4, 5), Q(1, 10), Q(1, 10), Q(1, 10), Q(1, 5)),
                        Q(1, 20), grid, Q(1, 10), True,
                        dict(eta_set, counts={(1, 2): 1, (1, 3): 1, (2, 3): 1}))


# --- 0.4: the tetrad tests -----------------------------------------------------

def _g(x, y, a, b):
    return Q((x[a] - y[a]) * (x[b] - y[b]), 2)


def _k(x, y, z, w):
    """The unsymmetrised kernel g_12(x, y) g_34(z, w) - g_13(x, y) g_24(z, w)."""

    return _g(x, y, 0, 1) * _g(z, w, 2, 3) - _g(x, y, 0, 2) * _g(z, w, 1, 3)


def _random_table(seed, low=1, high=9):
    rng = random.Random(seed)
    return FourRaterTable({cell: rng.randint(low, high) for cell in CELLS4})


def test_tetrad_kernel_is_the_symmetric_unbiased_kernel():
    kernel = tetrad_kernel()
    assert len(kernel) == 65536 and max(abs(k) for k in kernel) == TETRAD_KERNEL_BOUND
    index = {cell: i for i, cell in enumerate(CELLS4)}
    rng = random.Random(4)
    for _ in range(40):
        quad = [rng.choice(CELLS4) for _ in range(4)]
        values = {kernel[((index[a] * 16 + index[b]) * 16 + index[c]) * 16 + index[d]]
                  for a, b, c, d in permutations(quad)}
        assert len(values) == 1
        assert Q(values.pop(), 24) == sum(_k(*p) for p in permutations(quad)) / 24
    for seed in range(4):
        table = _random_table(seed)
        theta = tetrad_moments(table)["tetrad"]
        assert theta == four_rater_residuals(four_rater_moments(table))["tetrad_12_34_vs_13_24"]


def test_u_statistic_from_counts_matches_the_ordered_tuple_average():
    rng = random.Random(11)
    for _ in range(12):
        m = rng.randint(4, 7)
        items = [rng.choice(CELLS4) for _ in range(m)]
        ordered = [p for p in permutations(range(m), 4)]
        brute = sum(_k(*(items[i] for i in p)) for p in ordered) / len(ordered)
        table = FourRaterTable({cell: items.count(cell) for cell in CELLS4})
        assert tetrad_u_statistic(table) == brute == _tetrad_u_from_counts([items.count(c) for c in CELLS4])


def test_hoeffding_variance_matches_enumeration_for_any_table():
    table = _random_table(7, 1, 3)                 # not a four-rater model
    moments = tetrad_moments(table)
    assert moments["tetrad"] != 0
    for m in (4, 5):
        enum = tetrad_by_enumeration(m, table)
        assert enum["mean"] == moments["tetrad"]
        assert enum["variance"] == tetrad_u_variance(moments["zeta"], m)
    assert tetrad_u_variance(moments["zeta"], 4) == moments["zeta"][4]


def test_influence_function_factorises_into_two_latent_free_contrasts():
    points = [(FOUR_PRIOR, FOUR_FALSE_NEGATIVES, FOUR_FALSE_POSITIVES),
              (Q(1, 3), (Q(1, 5), Q(3, 5), Q(0), Q(1, 10)), (Q(1, 10), Q(3, 5), Q(1, 4), Q(1, 20)))]
    for prior, fn, fp in points:
        table = four_rater_model(prior, fn, fp)
        mom = four_rater_moments(table)
        p, c = mom["marginals"], mom["covariances"]
        u = prior * (1 - prior)
        d = [1 - a - b for a, b in zip(fn, fp)]
        total = Q(0)
        for cell in CELLS4:
            y = [cell[i] - p[i + 1] for i in range(4)]
            phi = {pair: y[pair[0] - 1] * y[pair[1] - 1] - c[pair] for pair in PAIRS4}
            influence = c[(3, 4)] * phi[(1, 2)] + c[(1, 2)] * phi[(3, 4)] - c[(2, 4)] * phi[(1, 3)] - c[(1, 3)] * phi[(2, 4)]
            assert influence == u * (d[3] * y[0] - d[0] * y[3]) * (d[2] * y[1] - d[1] * y[2])
            total += table.probability(cell) * influence ** 2
        closed = tetrad_influence_variance(prior, fn, fp)
        assert total == closed["influence_variance"] == 16 * tetrad_moments(table)["zeta"][1]


def test_variance_caps_and_the_universal_supremum():
    for s in range(21):
        for t in range(21):
            hit, false = Q(s, 20), Q(t, 20)
            cap = _variance_cap(hit - false)
            assert hit * (1 - hit) <= cap and false * (1 - false) <= cap
    best = Q(0)
    for i in range(41):
        for j in range(41):
            x, y = Q(i, 40), Q(j, 40)
            best = max(best, y * y * _variance_cap(x) + x * x * _variance_cap(y))
    assert best == Q(1, 4) == HALF ** 2 * _variance_cap(Q(1)) + _variance_cap(HALF)   # at x = 1, y = 1/2
    for m in (6, 742, 4000):
        fixture, universal = tetrad_variance_bound(m, FIXTURE_REGION), tetrad_variance_bound(m)
        assert fixture["variance_bound"] < universal["variance_bound"]
        assert tetrad_point_variance_bound(m, FOUR_PRIOR, FOUR_FALSE_NEGATIVES, FOUR_FALSE_POSITIVES) <= fixture["variance_bound"]
        bigger = tetrad_variance_bound(m, (Q(1, 4), Q(1), Q(1)))["variance_bound"]
        assert fixture["variance_bound"] <= bigger <= universal["variance_bound"]


def test_cantelli_tests_on_count_tables_and_power_bound():
    null = four_rater_model(FOUR_PRIOR, FOUR_FALSE_NEGATIVES, FOUR_FALSE_POSITIVES)
    copy = copy_grader_table4(FOUR_PRIOR, FOUR_FALSE_NEGATIVES, FOUR_FALSE_POSITIVES, Q(1))
    for region in (UNIVERSAL_REGION, FIXTURE_REGION):
        for side in TETRAD_SIDES:
            accept = tetrad_cantelli_test(FourRaterTable({c: 10000 * w for c, w in null.cells.items()}), region, Q(1, 20), side)
            reject = tetrad_cantelli_test(FourRaterTable({c: 10000 * w for c, w in copy.cells.items()}), region, Q(1, 20), side)
            assert not accept["reject"] and reject["reject"]
            factor = (1 - Q(1, 20)) / Q(1, 20) if side == "greater" else 1 / Q(1, 20)
            assert reject["critical_value"] ** 2 >= reject["variance_bound"] * factor
    bound = tetrad_cantelli_power_bound(copy, 4000)
    assert bound["tetrad"] == Q(513, 80000) and bound["power_lower_bound"] > Q(4, 5)
    assert tetrad_cantelli_power_bound(copy, 742)["power_lower_bound"] == 0
    assert tetrad_cantelli_power_bound(null, 4000)["power_lower_bound"] == 0


def test_sign_block_law_critical_values_and_rejection_probabilities():
    null = tetrad_sign_block_law(four_rater_model(FOUR_PRIOR, FOUR_FALSE_NEGATIVES, FOUR_FALSE_POSITIVES))
    assert null["p_plus"] == null["p_minus"] and null["mean"] == 0
    independent = four_rater_model(Q(0), (Q(1, 10), Q(1, 5), Q(1, 2), Q(1, 3)), (Q(1, 4), Q(1, 5), Q(1, 2), Q(1, 7)))
    assert tetrad_sign_block_law(independent)["mean"] == 0          # independent raters: every covariance is zero
    table = _random_table(3)
    assert tetrad_sign_block_law(table)["mean"] == 6 * tetrad_moments(table)["tetrad"] != 0
    for n in range(0, 31):
        for alpha, side in ((Q(1, 20), "greater"), (Q(1, 20), "two_sided"), (Q(1, 10), "greater")):
            level = alpha if side == "greater" else alpha / 2
            tails = [sum(comb(n, k) for k in range(c, n + 1)) for c in range(n + 2)]
            expected = min(c for c in range(n + 2) if Q(tails[c], 2 ** n) <= level)
            assert sign_test_critical_value(n, alpha, side) == expected
    p_plus, p_minus = Q(1, 7), Q(1, 11)
    for n in range(0, 7):
        for side in TETRAD_SIDES:
            brute = Q(0)
            for outcome in product((1, -1, 0), repeat=n):
                prob = Q(1)
                for z in outcome:
                    prob *= p_plus if z == 1 else p_minus if z == -1 else 1 - p_plus - p_minus
                plus, minus = outcome.count(1), outcome.count(-1)
                crit = sign_test_critical_value(plus + minus, Q(1, 20), side)
                if plus >= crit or (side == "two_sided" and minus >= crit):
                    brute += prob
            assert sign_test_rejection_probability(n, p_plus, p_minus, Q(1, 20), side)["exact"] == brute
    n = 320
    a, b = Q(3, 100), Q(2, 100)
    exact = Q(0)
    for trials in range(n + 1):
        crit = sign_test_critical_value(trials, Q(1, 20))
        if crit > trials:
            continue
        inner = sum(comb(trials, k) * a ** k * b ** (trials - k) for k in range(crit, trials + 1))
        exact += comb(n, trials) * (1 - a - b) ** (n - trials) * inner
    bracket = sign_test_rejection_probability(n, a, b)["bracket"]
    assert bracket[0] <= exact <= bracket[1] and bracket[1] - bracket[0] < Q(1, 10 ** 20)
    size = sign_test_rejection_probability(1000, null["p_plus"], null["p_minus"])["bracket"]
    assert size[1] <= Q(1, 20)


def test_tetrad_sign_test_on_items():
    rng = random.Random(5)
    items = [rng.choice(CELLS4) for _ in range(203)]
    uniforms = [rng.randrange(4) for _ in range(50)]
    kernel, index = tetrad_kernel(), {cell: i for i, cell in enumerate(CELLS4)}
    plus = minus = 0
    for b in range(50):
        quad = [index[c] for c in items[4 * b:4 * b + 4]]
        value = kernel[((quad[0] * 16 + quad[1]) * 16 + quad[2]) * 16 + quad[3]]
        if uniforms[b] < abs(value):
            plus, minus = plus + (value > 0), minus + (value < 0)
    for side in TETRAD_SIDES:
        result = tetrad_sign_test(items, uniforms, Q(1, 20), side)
        assert (result["blocks"], result["n_plus"], result["n_minus"]) == (50, plus, minus)
        upper = binomial_upper_tail(plus + minus, HALF, plus)
        assert result["p_value"] == (upper if side == "greater" else min(Q(1), 2 * min(
            upper, binomial_upper_tail(plus + minus, HALF, minus))))
        assert result["reject"] == (result["p_value"] <= Q(1, 20))


def test_cp_interval_matches_the_judge_module_brackets():
    for n, k in ((1, 0), (1, 1), (10, 3), (25, 0), (25, 25), (40, 17), (90, 2)):
        for level in (Q(1, 20), Q(1, 120)):
            bracket = clopper_pearson_bracket(n, k, level)
            assert _cp_interval(n, k, level) == (bracket["lower"][0], bracket["upper"][1])
    assert _cp_interval(0, 0, Q(1, 20)) == (Q(0), Q(1))


def test_eps1_interval_counts_corners_and_truth():
    record = rounded_record(expected_record_table(4000, Q(1, 4), Q(4, 5), Q(1, 10), HALF, Q(1, 10), Q(1, 5)))
    counts = interval_counts(record)
    labels = record.label_table()
    agree = {pair: sum(w for cell, w in labels.cells.items() if cell[pair[0] - 1] == cell[pair[1] - 1]) for pair in PAIRS}
    assert counts["rest"] == 4000 - agree[(2, 3)] and counts["right"] == agree[(1, 3)]
    assert counts["k_all"] + counts["k12"] == agree[(1, 2)]
    result = eps1_confidence_interval(record)
    assert result["status"] == "stated" and result["eps1_range"][0] <= HALF <= result["eps1_range"][1]
    assert result["eta_range"][0] <= Q(1, 10) <= result["eta_range"][1]
    rng = random.Random(9)
    ints = result["intervals"]
    for _ in range(200):
        pick = {name: lo + (hi - lo) * Q(rng.randint(0, 100), 100) for name, (lo, hi) in ints.items()}
        eta = result["eta_range"][0] + (result["eta_range"][1] - result["eta_range"][0]) * Q(rng.randint(0, 100), 100)
        value = _eps1_corner(eta, pick["measured_accuracy"], pick["measured_eps0"], pick["measured_eps1"])
        assert result["raw_range"][0] <= value <= result["raw_range"][1]
        kappa = 1 - 2 * pick["disagreement_g2_c"]
        k12_plus_k13 = (2 * pick["unanimous_given_agreement"] - 1) * (1 + kappa)
        k12_minus_k13 = (2 * pick["split_given_disagreement"] - 1) * (1 - kappa)
        square = (k12_plus_k13 ** 2 - k12_minus_k13 ** 2) / (4 * kappa)
        assert result["square_range"][0] <= square <= result["square_range"][1]
    small = eps1_confidence_interval(rounded_record(expected_record_table(100, Q(1, 4), Q(4, 5), Q(1, 10), Q(1, 10),
                                                                        Q(1, 10), Q(1, 5))))
    assert small["status"] in ("eta_unbounded", "eps1_undetermined") and small["eps1_range"] == (Q(0), Q(1))
    custom = eps1_confidence_interval(record, Q(1, 20), {name: Q(1, 120) for name in result["levels"]})
    assert custom["eps1_range"] == result["eps1_range"]


def test_eps1_interval_coverage_and_delta_variance():
    for eps1 in (Q(1, 10), HALF):
        coverage = eps1_interval_coverage(6, Q(1, 4), Q(4, 5), Q(1, 10), eps1, Q(1, 10), Q(1, 5))
        assert coverage["coverage"] >= Q(19, 20) and coverage["box_coverage"] >= Q(19, 20)
        assert coverage["tables"] == comb(13, 7)
    delta = eps1_delta_variance(Q(1, 4), Q(4, 5), Q(1, 10), Q(1, 10), Q(1, 10), Q(1, 5))
    assert delta["d_eps1_d_eta"] == -4 and delta["eta_only"] == 16 * Q(2401, 8100)
    assert delta["total"] == delta["judge_only"] + delta["eta_only"] + 2 * delta["cross"]
    assert delta["binomial_plug_in"] == Q(9, 20) < delta["judge_only"] < delta["total"]


def test_sturm_counts_and_square_root_signs():
    cubic = (Q(-6), Q(11), Q(-6), Q(1))                       # (x - 1)(x - 2)(x - 3)
    assert sturm_root_count(cubic, 0, Q(5, 2)) == 2 and sturm_root_count(cubic, Q(3, 2), 4) == 2
    assert sturm_root_count(cubic, 0, HALF) == 0 and sturm_root_count(cubic, Q(5, 2), 3) == 1
    double = (Q(-2), Q(5), Q(-4), Q(1))                      # (x - 1)^2 (x - 2)
    assert sturm_root_count(double, 0, 3) == 2
    assert sign_at_square_root((Q(-2), 0, 1), 2) == 0 and sign_at_square_root((Q(-1), 1), 2) == 1
    assert sign_at_square_root((Q(3), -2), 2) == 1 and sign_at_square_root((Q(-3), 2), 2) == -1
    assert sign_at_square_root((0, Q(-2), 0, 1), 2) == 0 and sign_at_square_root((Q(-7), 0, 0, 1), 4) == 1


def test_asymmetric_inversion_in_the_root_and_the_witness():
    controller, gold, second = (Q(1, 10), Q(3, 10)), (Q(1, 10), Q(1, 5)), (Q(1, 5), Q(1, 10))
    record = expected_record_table_asymmetric(4000, Q(1, 4), controller, Q(1, 10), Q(2, 5), gold, second)
    fit = dawid_skene_three_raters(record.label_table())
    measured = measured_judge_rates(record, 1)
    rational = asymmetric_eps1_rational(fit["moments"], measured["accuracy"], measured["judge_error"],
                                        measured["wrong_wrong_rate"])
    low, high = root_in_range_interval(fit["moments"])
    for k in range(1, 10):
        r = low + (high - low) * Q(k, 10)
        exact = asymmetric_eps1_enclosure(fit["moments"], measured["accuracy"], measured["judge_error"],
                                          measured["wrong_wrong_rate"], r - Q(1, 10 ** 6), r + Q(1, 10 ** 6))
        assert exact["status"] == "monotone"
        value = (sum(c * r ** i for i, c in enumerate(rational["numerator"]))
                 / sum(c * r ** i for i, c in enumerate(rational["denominator"])))
        assert exact["enclosure"][0] <= value <= exact["enclosure"][1]
    result = monotonicity_fixture()
    witness = result["witness"]
    assert witness["true_minus_end_signs"] == [-1, -1] and witness["enclosure_contains_true"]
    assert witness["critical_points_in_bracket"] == 1 and witness["critical_points_in_range"] == 2
    calibration = calibrate_asymmetric(witness_record(), Q(1, 10))
    assert calibration["status"] == "bracketed" and calibration["eps1_enclosure"]["status"] == "certified"
    assert [inv["recovered"]["eps1"] for inv in calibration["inversions"]] == witness["end_values"]
    assert all(r["critical_points_in_range"] == 0 for r in result["fixture_records"].values())


def test_tetrad_enumeration_size_and_rounded_record():
    null = four_rater_model(FOUR_PRIOR, FOUR_FALSE_NEGATIVES, FOUR_FALSE_POSITIVES)
    enum = tetrad_by_enumeration(4, null)
    assert enum["tables"] == comb(19, 15) and enum["mean"] == 0
    assert all(p <= Q(1, 20) for p in enum["rejection"].values())
    record = rounded_record(expected_record_table(742, Q(1, 4), Q(4, 5), Q(1, 10), Q(1, 10), Q(1, 10), Q(1, 5)))
    assert record.total == 742 and all(v.denominator == 1 for v in record.cells.values())


@pytest.mark.parametrize("call", [
    lambda: tetrad_variance_bound(3),
    lambda: tetrad_variance_bound(10, (Q(0), Q(1), Q(1))),
    lambda: tetrad_variance_bound(10, (Q(1, 3), Q(1), Q(1))),
    lambda: tetrad_variance_bound(10, (Q(1, 4), Q(3), Q(1))),
    lambda: tetrad_variance_bound(10, (Q(1, 4), Q(1))),
    lambda: tetrad_variance_bound(10, (0.25, Q(1), Q(1))),
    lambda: tetrad_u_statistic(FourRaterTable({CELLS4[0]: 3})),
    lambda: tetrad_u_statistic(FourRaterTable({CELLS4[0]: Q(9, 2)})),
    lambda: tetrad_cantelli_test(FourRaterTable({CELLS4[0]: 10}), UNIVERSAL_REGION, Q(1, 20), "less"),
    lambda: tetrad_cantelli_test(FourRaterTable({CELLS4[0]: 10}), UNIVERSAL_REGION, Q(0)),
    lambda: tetrad_u_variance({1: Q(0), 2: Q(0), 3: Q(0), 4: Q(0)}, 3),
    lambda: tetrad_influence_variance(Q(1, 4), (Q(1, 10),) * 3, (Q(1, 10),) * 4),
    lambda: sign_test_critical_value(-1, Q(1, 20)),
    lambda: sign_test_critical_value(5, Q(1, 20), "left"),
    lambda: sign_test_rejection_probability(10, Q(1, 2), Q(2, 3)),
    lambda: sign_test_rejection_probability(-1, Q(1, 4), Q(1, 4)),
    lambda: sign_test_rejection_probability(10, 0.25, Q(1, 4)),
    lambda: tetrad_sign_test([(0, 0, 0)] * 4, [0]),
    lambda: tetrad_sign_test([CELLS4[0]] * 8, [0]),
    lambda: tetrad_sign_test([CELLS4[0]] * 4, [4]),
    lambda: tetrad_by_enumeration(3, FourRaterTable({CELLS4[0]: 1})),
    lambda: eps1_confidence_interval(expected_record_table(742, Q(1, 4), Q(4, 5), Q(1, 10), Q(1, 10), Q(1, 10), Q(1, 5))),
    lambda: eps1_confidence_interval(rounded_record(expected_record_table(742, Q(1, 4), Q(4, 5), Q(1, 10), Q(1, 10),
                                                                         Q(1, 10), Q(1, 5))), Q(0)),
    lambda: eps1_confidence_interval(rounded_record(expected_record_table(742, Q(1, 4), Q(4, 5), Q(1, 10), Q(1, 10),
                                                                         Q(1, 10), Q(1, 5))), Q(1, 20), {"x": Q(1, 20)}),
    lambda: eps1_confidence_interval(rounded_record(expected_record_table(742, Q(1, 4), Q(4, 5), Q(1, 10), Q(1, 10),
                                                                         Q(1, 10), Q(1, 5))), Q(1, 20),
                                     {name: Q(1, 100) for name in ("disagreement_g2_c", "split_given_disagreement",
                                                                   "unanimous_given_agreement", "measured_accuracy",
                                                                   "measured_eps0", "measured_eps1")}),
    lambda: eps1_confidence_interval(three_rater_model(Q(1, 4), (Q(1, 10), Q(1, 5), Q(1, 5)))),
    lambda: interval_counts(RecordTable({(0, 0, 0, 0): Q(1, 2), (1, 1, 1, 1): Q(1, 2)})),
    lambda: rounded_record(RecordTable({(0, 0, 0, 0): Q(1, 2), (1, 1, 1, 1): Q(1, 3)})),
    lambda: sturm_root_count((Q(1), Q(1)), 1, 0),
    lambda: sturm_root_count((), 0, 1),
    lambda: sturm_root_count((Q(-1), Q(1)), 1, 2),
    lambda: sign_at_square_root((Q(1),), -1),
    lambda: asymmetric_eps1_rational(dawid_skene_three_raters(dawid_skene_model(Q(1, 4), (Q(1, 10),) * 3,
                                                                               (Q(1, 5),) * 3))["moments"],
                                     Q(1, 2), Q(1, 5), Q(1, 10), 2),
    lambda: asymmetric_eps1_enclosure(dawid_skene_three_raters(dawid_skene_model(Q(1, 4), (Q(1, 10),) * 3,
                                                                                (Q(1, 5),) * 3))["moments"],
                                      Q(1, 2), Q(1, 5), Q(1, 10), Q(1, 10), Q(1, 20)),
])
def test_rejects_malformed_v04(call):
    with pytest.raises(ValueError):
        call()


# --- malformed inputs --------------------------------------------------------

@pytest.mark.parametrize("call", [
    lambda: root_bracket(Q(-1)),
    lambda: root_bracket(Q(1, 2), 0),
    lambda: root_bracket(0.5),
    lambda: delta_variance((Q(1, 10), Q(1, 5))),
    lambda: delta_variance((Q(1, 10), HALF, Q(1, 5))),
    lambda: planning_size(FIXTURE_ERRORS, Q(0)),
    lambda: planning_size(FIXTURE_ERRORS, 0.02),
    lambda: sampling_law(0, FIXTURE_ERRORS),
    lambda: sampling_law(4, FIXTURE_ERRORS, Q(2)),
    lambda: sampling_law(4, (0.1, Q(1, 5), Q(1, 5))),
    lambda: sampling_law_by_tables(4, (Q(1, 10), Q(1, 5))),
    lambda: disagreement_bound(10, 11, Q(1, 20)),
    lambda: disagreement_bound(10, 5, Q(1)),
    lambda: disagreement_bound(10, Q(5), Q(1, 20)),
    lambda: dawid_skene_model(Q(1, 4), (Q(1, 10),) * 2, (Q(1, 10),) * 3),
    lambda: dawid_skene_model(Q(1, 4), (Q(1, 10),) * 3, (Q(3, 2),) * 3),
    lambda: dawid_skene_three_raters(three_rater_model(Q(1, 4), FIXTURE_ERRORS), "majority"),
    lambda: dawid_skene_jacobian_rank(Q(1, 4), (Q(1, 10),) * 3, (0.1,) * 3),
    lambda: expected_record_table_asymmetric(0, Q(1, 4), (Q(1, 10), Q(3, 10)), Q(1, 10), Q(1, 10), (Q(1, 10), Q(1, 5)), (Q(1, 5), Q(1, 10))),
    lambda: expected_record_table_asymmetric(10, Q(1, 4), (Q(1, 10),), Q(1, 10), Q(1, 10), (Q(1, 10), Q(1, 5)), (Q(1, 5), Q(1, 10))),
    lambda: expected_record_table_asymmetric(10, Q(1, 4), (Q(1, 10), Q(3, 10)), Q(1, 10), Q(3, 5), (Q(1, 10), Q(1, 5)), (Q(1, 5), Q(1, 10))),
    lambda: asymmetric_gold_noise_forward(Q(1, 4), (Q(1, 10), Q(3, 10)), Q(1, 10), Q(3, 5), (Q(1, 10), Q(1, 5))),
    lambda: asymmetric_gold_noise_inverse(Q(1, 4), (Q(1), Q(1)), (Q(1, 10), Q(1, 5)), Q(1, 2), Q(1, 2), Q(1, 4)),
    lambda: asymmetric_gold_noise_inverse(Q(1, 4), (Q(1, 10), Q(3, 10)), (Q(1, 10), Q(1, 5)), 0.5, Q(1, 2), Q(1, 4)),
    lambda: calibrate_asymmetric(RecordTable({(0, 0, 0, 0): Q(1, 2), (1, 1, 1, 1): Q(1, 2), (0, 1, 0, 1): Q(1, 3)})),
])
def test_rejects_malformed_v02(call):
    with pytest.raises(ValueError):
        call()


FOUR_FIXTURE = four_rater_model(FOUR_PRIOR, FOUR_FALSE_NEGATIVES, FOUR_FALSE_POSITIVES)
FIXTURE_COUNTS = {(1, 2): 549, (1, 3): 549, (2, 3): 504}
A_MEASURED, E_MEASURED, W_MEASURED = Q(37, 50), Q(9, 50), Q(9, 100)


@pytest.mark.parametrize("call", [
    lambda: four_rater_model(Q(1, 4), (Q(1, 10),) * 3, (Q(1, 10),) * 4),
    lambda: four_rater_model(Q(5, 4), (Q(1, 10),) * 4, (Q(1, 10),) * 4),
    lambda: four_rater_model(Q(1, 4), (0.1,) * 4, (Q(1, 10),) * 4),
    lambda: FourRaterTable({(0, 0, 0): 1}),
    lambda: FourRaterTable({cell: 0 for cell in CELLS4}),
    lambda: FourRaterTable({(0, 0, 0, 0): 1}).triple(5),
    lambda: copy_grader_table4(Q(1, 4), FOUR_FALSE_NEGATIVES, FOUR_FALSE_POSITIVES, Q(2)),
    lambda: copy_grader_tetrad_residual(Q(1, 4), FOUR_FALSE_NEGATIVES, FOUR_FALSE_POSITIVES, 0.5),
    lambda: four_rater_jacobian_rank(Q(1, 4), FOUR_FALSE_NEGATIVES, (0.1,) * 4),
    lambda: dawid_skene_four_raters(FOUR_FIXTURE, "majority"),
    lambda: four_rater_constraints(FOUR_FIXTURE, "majority"),
    lambda: square_tail_law(10, (Q(1, 10), Q(1, 5), Q(1, 5)), "neither"),
    lambda: square_tail_law(10, (Q(1, 10), Q(1, 5), Q(1, 5)), Q(3, 2)),
    lambda: square_tail_bracket(10, (Q(1, 10), Q(1, 5), Q(1, 5)), HALF, 20, 20),
    lambda: square_tail_bracket(0, (Q(1, 10), Q(1, 5), Q(1, 5)), HALF),
    lambda: square_tail_bracket(10, (Q(1, 10), Q(1, 5)), HALF),
    lambda: observed_square(742, {(1, 2): 549, (1, 3): 549, (2, 3): 505}),
    lambda: observed_square(10, {(1, 2): 5}),
    lambda: observed_square(10, {(1, 2): 11, (1, 3): 5, (2, 3): 5}),
    lambda: observed_square(10, {(1, 2): 0, (1, 3): 6, (2, 3): 6}),
    lambda: eta_confidence_set(742, FIXTURE_COUNTS, Q(1, 5), Q(4, 5), Q(1, 20), ()),
    lambda: eta_confidence_set(742, FIXTURE_COUNTS, Q(1, 5), Q(4, 5), Q(1, 20), (HALF,)),
    lambda: eta_confidence_set(742, FIXTURE_COUNTS, Q(1, 5), Q(4, 5), Q(1, 20), (0.1,)),
    lambda: eta_confidence_set(742, FIXTURE_COUNTS, Q(1, 5), Q(4, 5), Q(0), (Q(1, 10),)),
    lambda: eta_confidence_set(742, FIXTURE_COUNTS, Q(1, 5), Q(4, 5), Q(1, 20), {Q(1, 10)}),
    lambda: clamped_inversion(A_MEASURED, E_MEASURED, W_MEASURED, HALF),
    lambda: clamped_inversion(0.74, E_MEASURED, W_MEASURED, Q(1, 10)),
    lambda: joint_statement(expected_record_table(100, Q(1, 4), Q(4, 5), Q(1, 10), Q(1, 10), Q(1, 10), Q(1, 5)),
                            HALF, (Q(1, 10),)),
    lambda: joint_statement(RecordTable({(0, 0, 0, 0): Q(1, 2), (1, 1, 1, 1): Q(1, 3)}), Q(1, 20), (Q(1, 10),)),
    lambda: joint_statement(three_rater_model(Q(1, 4), (Q(1, 10), Q(1, 5), Q(1, 5))), Q(1, 20), (Q(1, 10),)),
    lambda: agreement_counts(RecordTable({(0, 0, 0, 0): Q(1, 2)})),
])
def test_rejects_malformed_v03(call):
    with pytest.raises(ValueError):
        call()


@pytest.mark.parametrize("call", [
    lambda: LabelTable({}),
    lambda: LabelTable({(0, 0, 0): -1}),
    lambda: LabelTable({(0, 0, 0): 0.5}),
    lambda: LabelTable({(0, 0, 0): True}),
    lambda: LabelTable({(0, 0): 1}),
    lambda: LabelTable([1] * 8),
    lambda: RecordTable({(0, 0, 0): 1}),
    lambda: RecordTable({cell: 0 for cell in product((0, 1), repeat=4)}),
    lambda: three_rater_model(Q(3, 2), (Q(1, 10),) * 3),
    lambda: three_rater_model(Q(1, 2), (Q(1, 10),) * 2),
    lambda: three_rater_model(0.5, (Q(1, 10),) * 3),
    lambda: polarity_squares({(1, 2): Q(0), (1, 3): Q(1, 2), (2, 3): Q(1, 2)}),
    lambda: polarity_squares({(1, 2): 0.5, (1, 3): Q(1, 2), (2, 3): Q(1, 2)}),
    lambda: error_rate_from_square(Q(3, 2)),
    lambda: error_rate_from_square(Q(-1, 4)),
    lambda: error_rate_at_most(Q(1, 2), Q(3, 2)),
    lambda: error_rate_bracket(Q(1, 2), Q(0)),
    lambda: error_rate_bracket(Q(1, 2), 0.001),
    lambda: eta_gradient({(1, 2): Q(1, 2), (1, 3): Q(1, 2), (2, 3): Q(1, 2)}, 4),
    lambda: agreement_rate(three_rater_model(Q(1, 2), (Q(1, 10),) * 3), 1, 1),
    lambda: model_jacobian_rank(Q(1, 2), (Q(1, 10),) * 4),
    lambda: copy_grader_table(Q(1, 2), Q(1, 10), Q(1, 5), Q(1, 5), Q(2)),
    lambda: expected_record_table(0, Q(1, 4), Q(4, 5), Q(1, 10), Q(1, 10), Q(1, 10), Q(1, 5)),
    lambda: expected_record_table(10, Q(1, 4), Q(4, 5), Q(1, 10), Q(3, 5), Q(1, 10), Q(1, 5)),
    lambda: expected_record_table(10, 0.25, Q(4, 5), Q(1, 10), Q(1, 10), Q(1, 10), Q(1, 5)),
    lambda: expected_record_table(10, Q(1, 4), Q(4, 5), Q(1, 10), Q(1, 10), Q(1, 10), Q(1, 5), Q(-1)),
    lambda: RecordTable({(0, 0, 0, 0): 1}).judge_cells(3),
    lambda: inverted_eps1(Q(37, 50), Q(9, 50), Q(9, 100), HALF),
    lambda: inverted_eps1(Q(37, 50), Q(9, 50), Q(9, 100), Q(13, 50)),
    lambda: eps1_sensitivity(Q(37, 50), Q(9, 50), Q(9, 100), 0.1),
    lambda: eps1_displacement(Q(37, 50), Q(9, 50), Q(9, 100), Q(1, 10), Q(-1, 5)),
    lambda: eps1_displacement(Q(37, 50), Q(9, 50), Q(9, 100), Q(1, 10), Q(1, 5)),
    lambda: calibrate(expected_record_table(10000, Q(1, 4), Q(4, 5), Q(1, 10), Q(1, 10), Q(1, 10), Q(1, 5)), 0.1),
    lambda: calibrate(RecordTable({(0, 0, 0, 0): Q(1, 2), (1, 1, 1, 1): Q(1, 2), (0, 1, 0, 1): Q(1, 3)})),
])
def test_rejects_malformed(call):
    with pytest.raises(ValueError):
        call()


def test_fixture_values_and_verify():
    report = verify()
    assert report["all_passed"] and len(report["checks"]) == 75
    tetrad = report["tetrad"]
    assert tetrad["null_moments"]["zeta"][1] * 16 == Q(321813, 512000000)
    assert tetrad["alternatives"]["1"]["by_size"][4000]["sign_test_power"]["greater"]["bracket"][0] > Q(9, 10)
    assert Q(1, 17) < tetrad["efficiency_ratio"] < Q(1, 16)
    interval = report["interval"]["by_size"]
    assert interval[4000]["judges"]["independent"]["interval"]["eps1_range"][1] \
        < interval[4000]["judges"]["maximally_shared"]["interval"]["eps1_range"][0]
    witness = report["monotonicity"]["witness"]
    assert witness["true_minus_end_signs"] == [-1, -1]
    assert report["evidence_status"].startswith("exact_synthetic")
    sampling = report["sampling"]
    assert sampling["delta"]["eta"] == Q(2401, 8100) and sampling["planning_size"] == 742
    assert sampling["laws"][16]["p_undefined"] == sampling["label_table_enumeration"]["p_undefined"]
    assert Q(32, 100) < sampling["laws"][16]["p_undefined"] < Q(33, 100)
    assert Q(1, 100) < sampling["laws"][200]["p_undefined"] < Q(13, 1000)
    ds = report["dawid_skene"]
    assert ds["fit"]["root"] == Q(441, 8000) and ds["copy_grader"]["1"]["solution"]["prior"] == Q(3, 10)
    asym = report["asymmetric_pipeline"]["judges"]
    assert asym["independent"]["forward"]["accuracy"] == Q(67, 100)
    assert asym["independent"]["calibration"]["inversions"][0]["corrected_table"] == JudgeTable(2700, 300, 900, 100)
    raters = report["three_raters"]
    assert raters["kappas"] == {(1, 2): Q(12, 25), (1, 3): Q(12, 25), (2, 3): Q(9, 25)}
    assert raters["walsh"][(1,)] == Q(2, 5) and raters["walsh"][(1, 2, 3)] == Q(18, 125)
    ind = report["pipeline"]["independent"]["calibration"]["inversions"][0]
    shared = report["pipeline"]["maximally_shared"]["calibration"]["inversions"][0]
    assert ind["tests"]["ceiling_p"] < Q(1, 10 ** 100) and shared["tests"]["independence_p"] < Q(1, 10 ** 100)
    assert Q(1, 2) < ind["tests"]["independence_p"] < Q(3, 5) and Q(1, 2) < shared["tests"]["ceiling_p"] < Q(3, 5)
    assert report["dependent_grader"]["rows"]["1"]["closed_form_residual"] == Q(-27, 250)
    assert report["dependent_grader"]["rows"]["1/2"]["closed_form_residual"] == Q(-27, 500)
    four = report["four_raters"]
    assert four["constraint_jacobian_rank"] == 6 and four["parameter_jacobian_rank"] == 9
    assert four["copy_grader"]["1"]["closed_form_residual"] == Q(513, 80000)
    assert four["chance_rater"][2] == {"parameter_rank": 9, "constraint_rank": 4, "status": "not_identified"}
    joint = report["joint"]["by_size"][742]
    assert joint["eta_set"]["retained"] == [Q(k, 100) for k in range(6, 15)]
    ind, shared = (joint["judges"][name]["statement"] for name in ("independent", "maximally_shared"))
    assert ind["eps1_range"][0] == 0 and Q(29, 100) < ind["eps1_range"][1] < Q(3, 10)
    assert Q(1, 4) < shared["eps1_range"][0] < Q(26, 100) and Q(65, 100) < shared["eps1_range"][1] < Q(66, 100)
    assert joint["tests_separate"] and not joint["ranges_disjoint"]
    assert report["joint"]["asymmetric_record"]["status"] == "withheld_constraints_fail"
