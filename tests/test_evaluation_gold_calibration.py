from fractions import Fraction as Q
from itertools import product

import pytest

from spiral_ln.evaluation_gold_calibration import (
    CELLS3, HALF, PAIRS, RANGE_FALSIFIER, RESOLUTION, SIGN_FALSIFIER, LabelTable,
    RecordTable, agreement_rate, calibrate, calibration_valid, copy_grader_residual,
    copy_grader_table, eps1_displacement, eps1_sensitivity, error_rate_at_most,
    error_rate_bracket, error_rate_from_square, eta_gradient, exact_square_root,
    expected_record_table, inverted_eps1, measured_judge_rates, model_constraints,
    model_jacobian_rank, pairwise_kappas, polarity_squares, three_rater_model, verify,
    walsh_coefficients,
)
from spiral_ln.evaluation_game_feedback import LoopEvent
from spiral_ln.evaluation_judge_measurement import (
    JudgeTable, gold_noise_forward, gold_noise_inverse, measurement_ledger,
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


# --- malformed inputs --------------------------------------------------------

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
    assert report["all_passed"] and len(report["checks"]) == 23
    assert report["evidence_status"].startswith("exact_synthetic")
    raters = report["three_raters"]
    assert raters["kappas"] == {(1, 2): Q(12, 25), (1, 3): Q(12, 25), (2, 3): Q(9, 25)}
    assert raters["walsh"][(1,)] == Q(2, 5) and raters["walsh"][(1, 2, 3)] == Q(18, 125)
    ind = report["pipeline"]["independent"]["calibration"]["inversions"][0]
    shared = report["pipeline"]["maximally_shared"]["calibration"]["inversions"][0]
    assert ind["tests"]["ceiling_p"] < Q(1, 10 ** 100) and shared["tests"]["independence_p"] < Q(1, 10 ** 100)
    assert Q(1, 2) < ind["tests"]["independence_p"] < Q(3, 5) and Q(1, 2) < shared["tests"]["ceiling_p"] < Q(3, 5)
    assert report["dependent_grader"]["rows"]["1"]["closed_form_residual"] == Q(-27, 250)
    assert report["dependent_grader"]["rows"]["1/2"]["closed_form_residual"] == Q(-27, 500)
