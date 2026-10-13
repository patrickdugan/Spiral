from fractions import Fraction as Q
from itertools import product

import pytest

from spiral_ln.evaluation_gold_calibration import (
    ANTI_INFORMATIVE_SECOND, CELLS3, DS_FALSE_NEGATIVES, DS_FALSE_POSITIVES, DS_PRIOR,
    HALF, OUTSIDE_MODEL, PAIRS, RANGE_FALSIFIER, RESOLUTION, SIGN_FALSIFIER, LabelTable,
    RecordTable, _binomial_upper_tail, agreement_covariance, agreement_covariance_model,
    agreement_patterns, agreement_rate, asymmetric_gold_noise_forward,
    asymmetric_gold_noise_inverse, calibrate, calibrate_asymmetric, calibration_valid,
    copy_grader_residual, copy_grader_table, dawid_skene_jacobian_rank, dawid_skene_model,
    dawid_skene_moments, dawid_skene_three_raters, delta_variance, delta_variance_from_table,
    disagreement_bound, eps1_displacement, eps1_sensitivity, error_rate_at_most,
    error_rate_bracket, error_rate_from_square, eta_gradient, exact_square_root,
    expected_record_table, expected_record_table_asymmetric, inverted_eps1,
    measured_judge_rates, model_constraints, model_jacobian_rank, pairwise_kappas,
    planning_size, polarity_squares, root_bracket, sampling_law, sampling_law_by_tables,
    three_rater_model, verify, walsh_coefficients,
)
from spiral_ln.evaluation_game_feedback import LoopEvent
from spiral_ln.evaluation_judge_measurement import (
    JudgeTable, binomial_upper_tail, gold_noise_forward, gold_noise_inverse, measurement_ledger,
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
    assert report["all_passed"] and len(report["checks"]) == 40
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
