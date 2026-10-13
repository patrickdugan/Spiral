from fractions import Fraction as Q
from itertools import combinations, product
from math import comb

import pytest

from spiral_ln.evaluation_feedback_signal import (
    judge_correlation_inflation, observed_accuracy_shared, shared_error_bounds,
)
from spiral_ln.evaluation_game_feedback import LoopEvent, observed_accuracy
from spiral_ln.evaluation_judge_measurement import (
    HALF, JudgeTable, agreement_identity_holds, binomial_lower_tail, binomial_pmf,
    binomial_upper_tail, card_item, ceiling_p_value, clopper_pearson_bracket,
    clopper_pearson_contains, expected_sample_size, expected_table, fisher_p_value,
    gold_noise_forward, gold_noise_inverse, hypergeometric_pmf,
    independence_p_value, independent_judge_measured_excess, measurement_ledger,
    power_at, rejection_threshold, render_card_item, rounded_table,
    smallest_sample_size, smallest_wrong_count, table_estimates,
    unconditional_power, verify,
)

PROBS = (Q(0), Q(1, 20), Q(1, 10), Q(1, 3), Q(1, 2), Q(4, 5), Q(1))


def _brute_upper(trials, p, k):
    total = Q(0)
    for bits in product((0, 1), repeat=trials):
        if sum(bits) >= k:
            total += p ** sum(bits) * (1 - p) ** (trials - sum(bits))
    return total


def _brute_hypergeometric(population, successes, draws):
    marked = set(range(successes))
    counts = [0] * (draws + 1)
    for subset in combinations(range(population), draws):
        counts[len(marked & set(subset))] += 1
    return [Q(c, comb(population, draws)) for c in counts]


# --- tails ---------------------------------------------------------------------

def test_binomial_tails_match_enumeration_and_sum_to_one():
    for trials in range(0, 7):
        for p in PROBS:
            pmf = binomial_pmf(trials, p)
            assert sum(pmf) == 1
            for k in range(-1, trials + 2):
                upper = binomial_upper_tail(trials, p, k)
                assert upper == _brute_upper(trials, p, k)
                assert upper + binomial_lower_tail(trials, p, k - 1) == 1
    assert binomial_upper_tail(5, Q(1, 3), 0) == 1 and binomial_upper_tail(5, Q(1, 3), 6) == 0
    assert binomial_lower_tail(5, Q(1, 3), -1) == 0 and binomial_lower_tail(5, Q(1, 3), 5) == 1


def test_tails_are_monotone_in_p():
    grid = [Q(k, 12) for k in range(13)]
    for trials in (1, 4, 9):
        for k in range(1, trials + 1):
            uppers = [binomial_upper_tail(trials, p, k) for p in grid]
            assert all(x <= y for x, y in zip(uppers, uppers[1:]))
            lowers = [binomial_lower_tail(trials, p, k - 1) for p in grid]
            assert all(x >= y for x, y in zip(lowers, lowers[1:]))


def test_hypergeometric_matches_subset_enumeration():
    for population in range(1, 8):
        for successes in range(population + 1):
            for draws in range(population + 1):
                assert hypergeometric_pmf(population, successes, draws) == \
                    _brute_hypergeometric(population, successes, draws)


@pytest.mark.parametrize("args", [(-1, Q(1, 2)), (2.0, Q(1, 2)), (3, 0.5), (3, Q(3, 2)), (3, True)])
def test_pmf_rejects_malformed(args):
    with pytest.raises(ValueError):
        binomial_pmf(*args)


def test_tail_rejects_non_integer_k():
    with pytest.raises(ValueError):
        binomial_upper_tail(3, Q(1, 2), 1.0)


# --- table and identity --------------------------------------------------------

def test_agreement_identity_on_every_table_up_to_four_per_cell():
    for cells in product(range(5), repeat=4):
        if not any(cells):
            continue
        table = JudgeTable(*cells)
        estimates = table_estimates(table)
        assert agreement_identity_holds(table)
        assert estimates["agreement_rate"] == Q(cells[0] + cells[3], sum(cells))
        if estimates["eps1_hat"] is not None:
            rhs = estimates["a_hat"] - estimates["eps_hat"] + 2 * (1 - estimates["a_hat"]) * estimates["eps1_hat"]
            assert rhs == estimates["agreement_rate"]
        if estimates["inflation_hat"] is not None:
            assert estimates["inflation_hat"] == estimates["agreement_rate"] - observed_accuracy(
                estimates["a_hat"], estimates["eps_hat"])


def test_expected_table_on_rational_grid_matches_L4():
    for accuracy in (Q(1, 2), Q(3, 5), Q(4, 5), Q(9, 10)):
        for judge_error in (Q(1, 20), Q(1, 10), Q(1, 4)):
            low, high = shared_error_bounds(accuracy, judge_error)
            for step in range(5):
                eps1 = low + (high - low) * Q(step, 4)
                expected = expected_table(120, accuracy, judge_error, eps1)
                assert sum(expected.values()) == 120
                assert all(v >= 0 for v in expected.values())
                agreement = (expected["right_right"] + expected["wrong_wrong"]) / 120
                assert agreement == observed_accuracy_shared(accuracy, judge_error, eps1)
                assert expected["wrong_wrong"] / 120 == (1 - accuracy) * eps1
                assert (expected["right_wrong"] + expected["wrong_wrong"]) / 120 == judge_error


def test_rounding_reports_change_and_fixture_needs_none():
    table, changed = rounded_table(expected_table(200, Q(4, 5), Q(1, 10), Q(1, 10)))
    assert table == JudgeTable(144, 16, 36, 4) and not changed
    table, changed = rounded_table(expected_table(7, Q(4, 5), Q(1, 10), Q(1, 2)))
    assert changed and table.size in (6, 7, 8)
    assert rounded_table({"right_right": Q(1, 2), "right_wrong": Q(3, 2), "wrong_right": Q(0),
                          "wrong_wrong": Q(1, 4)})[0] == JudgeTable(1, 2, 0, 0)


@pytest.mark.parametrize("cells", [(0, 0, 0, 0), (-1, 1, 1, 1), (1.0, 1, 1, 1), (True, 1, 1, 1)])
def test_table_rejects_malformed(cells):
    with pytest.raises(ValueError):
        JudgeTable(*cells)


@pytest.mark.parametrize("args", [(0, Q(4, 5), Q(1, 10), Q(1, 10)), (10, Q(4, 5), Q(1, 10), Q(3, 5)),
                                  (10, 0.8, Q(1, 10), Q(1, 10)), (10, Q(1), Q(1, 10), Q(1, 10))])
def test_expected_table_rejects_malformed(args):
    with pytest.raises(ValueError):
        expected_table(*args)


# --- the tests -----------------------------------------------------------------

def test_independence_p_value_is_upper_tail_and_decreasing_in_w1():
    for wrong in (1, 5, 12):
        for eps in (Q(1, 20), Q(1, 10), Q(1, 5)):
            values = [independence_p_value(wrong, w1, eps) for w1 in range(wrong + 1)]
            assert values[0] == 1
            assert all(x > y for x, y in zip(values, values[1:]))
            assert values[-1] == eps ** wrong
            assert values == [binomial_upper_tail(wrong, eps, w1) for w1 in range(wrong + 1)]


def test_ceiling_p_value_is_supremum_over_composite_null():
    for wrong in (1, 6, 15):
        for w1 in range(wrong + 1):
            p = ceiling_p_value(wrong, w1)
            assert p == binomial_lower_tail(wrong, HALF, w1)
            for eps1 in (HALF, Q(3, 5), Q(3, 4), Q(9, 10), Q(1)):
                assert binomial_lower_tail(wrong, eps1, w1) <= p


def test_fisher_matches_hypergeometric_tail_and_fixture_direction():
    independent, shared = JudgeTable(144, 16, 36, 4), JudgeTable(160, 0, 20, 20)
    for table in (independent, shared):
        pmf = hypergeometric_pmf(table.size, table.judge_wrong, table.controller_wrong)
        assert fisher_p_value(table) == sum(pmf[table.wrong_wrong:])
    assert fisher_p_value(independent) > Q(1, 2) > Q(1, 20) > fisher_p_value(shared)
    assert fisher_p_value(JudgeTable(3, 0, 2, 0)) == 1
    assert fisher_p_value(JudgeTable(3, 0, 0, 2)) == Q(1, 10)
    assert fisher_p_value(JudgeTable(2, 1, 1, 1)) == Q(7, 10)


@pytest.mark.parametrize("call", [
    lambda: independence_p_value(0, 0, Q(1, 10)),
    lambda: independence_p_value(5, 6, Q(1, 10)),
    lambda: independence_p_value(5, 2, 0.1),
    lambda: independence_p_value(5, -1, Q(1, 10)),
    lambda: ceiling_p_value(0, 0),
    lambda: ceiling_p_value(4, 5),
    lambda: fisher_p_value(JudgeTable(3, 1, 0, 0)),
    lambda: hypergeometric_pmf(3, 4, 1),
])
def test_conditional_tests_reject_malformed(call):
    with pytest.raises(ValueError):
        call()


# --- planning ------------------------------------------------------------------

def test_rejection_threshold_is_smallest_level_alpha_cutoff():
    for wrong in range(0, 25):
        for eps in (Q(1, 20), Q(1, 10), Q(1, 5)):
            for alpha in (Q(1, 20), Q(1, 100)):
                c = rejection_threshold(wrong, eps, alpha)
                assert 0 <= c <= wrong + 1
                assert binomial_upper_tail(wrong, eps, c) <= alpha
                if c > 0:
                    assert binomial_upper_tail(wrong, eps, c - 1) > alpha
                power = power_at(wrong, eps, alpha)
                assert power == (Q(0) if wrong == 0 else binomial_upper_tail(wrong, HALF, c))
                assert power == sum((binomial_pmf(wrong, HALF)[k] for k in range(c, wrong + 1)), Q(0))


def test_smallest_wrong_count_is_first_hit_and_stable_tail_holds():
    for eps in (Q(1, 20), Q(1, 10), Q(1, 5)):
        for beta in (Q(1, 5), Q(1, 10)):
            plan = smallest_wrong_count(eps, Q(1, 20), beta, horizon=60)
            w = plan["smallest"]
            assert plan["power"] == power_at(w, eps, Q(1, 20)) >= 1 - beta
            assert all(power_at(v, eps, Q(1, 20)) < 1 - beta for v in range(1, w))
            assert all(power_at(v, eps, Q(1, 20)) >= 1 - beta for v in range(plan["stable_from"], 61))
            assert plan["stable_from"] >= w and plan["sawtooth"] == (plan["stable_from"] != w)
            assert plan["threshold"] == rejection_threshold(w, eps, Q(1, 20))
    assert smallest_wrong_count(Q(1, 10), Q(1, 20), Q(1, 5))["smallest"] == 8
    assert smallest_wrong_count(Q(1, 5), Q(1, 20), Q(1, 10))["smallest"] == 21


def test_expected_sample_size_and_unconditional_power():
    assert expected_sample_size(8, Q(4, 5)) == {"expected": Q(40), "ceiling": 40}
    assert expected_sample_size(7, Q(9, 10)) == {"expected": Q(70), "ceiling": 70}
    assert expected_sample_size(7, Q(2, 3)) == {"expected": Q(21), "ceiling": 21}
    assert expected_sample_size(5, Q(3, 4))["ceiling"] == 20
    m, a, eps = 12, Q(2, 3), Q(1, 10)
    weights = binomial_pmf(m, 1 - a)
    direct = sum((weights[w] * power_at(w, eps, Q(1, 20)) for w in range(m + 1)), Q(0))
    assert unconditional_power(m, a, eps, Q(1, 20)) == direct
    assert unconditional_power(1, Q(1, 2), eps, Q(1, 20)) == Q(1, 2) * power_at(1, eps, Q(1, 20))


def test_smallest_sample_size_is_first_hit_with_stable_window():
    plan = smallest_sample_size(Q(1, 2), Q(1, 10), Q(1, 20), Q(1, 5), margin=5)
    m = plan["smallest_m"]
    assert plan["power"] == unconditional_power(m, Q(1, 2), Q(1, 10), Q(1, 20)) >= Q(4, 5)
    assert all(unconditional_power(k, Q(1, 2), Q(1, 10), Q(1, 20)) < Q(4, 5) for k in range(1, m))
    assert plan["holds_on_next"] == all(
        unconditional_power(m + k, Q(1, 2), Q(1, 10), Q(1, 20)) >= Q(4, 5) for k in range(1, 6))


@pytest.mark.parametrize("call", [
    lambda: rejection_threshold(5, Q(1, 10), Q(3, 2)),
    lambda: power_at(5, Q(1, 2), Q(1, 20)),
    lambda: power_at(5, Q(1, 10), Q(1, 20), Q(1, 20)),
    lambda: smallest_wrong_count(Q(1, 5), Q(1, 20), Q(1, 10), horizon=10),
    lambda: smallest_wrong_count(Q(1, 5), Q(1, 20), Q(1, 10), horizon=0),
    lambda: expected_sample_size(5, Q(1)),
    lambda: unconditional_power(0, Q(4, 5), Q(1, 10), Q(1, 20)),
    lambda: smallest_sample_size(Q(4, 5), Q(1, 5), Q(1, 20), Q(1, 10), horizon=5),
])
def test_planning_rejects_malformed(call):
    with pytest.raises(ValueError):
        call()


# --- Clopper-Pearson -----------------------------------------------------------

def test_clopper_pearson_brackets_and_membership_agree():
    for wrong, w1 in ((40, 4), (40, 20), (10, 0), (10, 10), (7, 3)):
        bracket = clopper_pearson_bracket(wrong, w1, Q(1, 20), Q(1, 2 ** 10))
        (lo0, lo1), (hi0, hi1) = bracket["lower"], bracket["upper"]
        assert 0 <= lo0 <= lo1 <= bracket["point"] <= hi0 <= hi1 <= 1
        assert lo1 - lo0 <= Q(1, 2 ** 10) and hi1 - hi0 <= Q(1, 2 ** 10)
        if w1 > 0:
            assert binomial_upper_tail(wrong, lo0, w1) < Q(1, 40) <= binomial_upper_tail(wrong, lo1, w1)
            assert not clopper_pearson_contains(wrong, w1, Q(1, 20), lo0)
        assert clopper_pearson_contains(wrong, w1, Q(1, 20), lo1)
        if w1 < wrong:
            assert binomial_lower_tail(wrong, hi0, w1) >= Q(1, 40) > binomial_lower_tail(wrong, hi1, w1)
            assert not clopper_pearson_contains(wrong, w1, Q(1, 20), hi1)
        assert clopper_pearson_contains(wrong, w1, Q(1, 20), hi0)
        assert clopper_pearson_contains(wrong, w1, Q(1, 20), bracket["point"])
    assert clopper_pearson_contains(40, 4, Q(1, 20), Q(1, 10)) and not clopper_pearson_contains(40, 4, Q(1, 20), HALF)
    assert clopper_pearson_contains(40, 20, Q(1, 20), HALF) and not clopper_pearson_contains(40, 20, Q(1, 20), Q(1, 10))


@pytest.mark.parametrize("call", [
    lambda: clopper_pearson_bracket(40, 4, Q(1)),
    lambda: clopper_pearson_bracket(40, 4, Q(1, 20), Q(0)),
    lambda: clopper_pearson_bracket(0, 0, Q(1, 20)),
    lambda: clopper_pearson_contains(40, 4, Q(1, 20), Q(3, 2)),
])
def test_clopper_pearson_rejects_malformed(call):
    with pytest.raises(ValueError):
        call()


# --- gold noise ----------------------------------------------------------------

def _enumerate_measured(accuracy, judge_error, eps1, eta):
    eps0 = (judge_error - (1 - accuracy) * eps1) / accuracy
    joint = {}
    for c, j, f in product((0, 1), repeat=3):
        pc = accuracy if c else 1 - accuracy
        pj = (1 - eps0 if j else eps0) if c else (1 - eps1 if j else eps1)
        pf = eta if f else 1 - eta
        joint[(c, j, f)] = pc * pj * pf
    right = sum(v for (c, j, f), v in joint.items() if c ^ f == 1)
    judge_wrong = sum(v for (c, j, f), v in joint.items() if j ^ f == 0)
    both_wrong = sum(v for (c, j, f), v in joint.items() if c ^ f == 0 and j ^ f == 0)
    agree = sum(v for (c, j, f), v in joint.items() if c == j)
    return {"accuracy": right, "judge_error": judge_wrong, "wrong_wrong_rate": both_wrong,
            "eps1": both_wrong / (1 - right), "agreement_rate": agree}


def test_gold_noise_forward_matches_enumeration_and_inverts():
    for accuracy in (Q(1, 2), Q(3, 5), Q(4, 5), Q(9, 10)):
        for judge_error in (Q(1, 20), Q(1, 10), Q(1, 4)):
            low, high = shared_error_bounds(accuracy, judge_error)
            for step in range(3):
                eps1 = low + (high - low) * Q(step, 2)
                for eta in (Q(0), Q(1, 20), Q(1, 4), Q(2, 5)):
                    measured = gold_noise_forward(accuracy, judge_error, eps1, eta)
                    brute = _enumerate_measured(accuracy, judge_error, eps1, eta)
                    assert all(measured[k] == brute[k] for k in brute)
                    assert measured["agreement_rate"] == observed_accuracy_shared(accuracy, judge_error, eps1)
                    a2, e2, e1 = measured["accuracy"], measured["judge_error"], measured["eps1"]
                    assert a2 * measured["eps0"] + (1 - a2) * e1 == e2
                    assert a2 - e2 + 2 * (1 - a2) * e1 == measured["agreement_rate"]
                    recovered = gold_noise_inverse(a2, e2, e1, eta)
                    assert recovered == {"accuracy": accuracy, "judge_error": judge_error, "eps1": eps1}
                    if eta == 0:
                        assert (a2, e2, e1) == (accuracy, judge_error, eps1)


def test_independent_judge_excess_sign_and_fixture_value():
    assert independent_judge_measured_excess(Q(4, 5), Q(1, 10), Q(1, 20)) == Q(57, 575)
    assert independent_judge_measured_excess(Q(4, 5), Q(1, 10), Q(0)) == 0
    assert independent_judge_measured_excess(Q(1, 2), Q(1, 10), Q(1, 5)) == 0
    assert independent_judge_measured_excess(Q(2, 5), Q(1, 10), Q(1, 5)) < 0
    assert independent_judge_measured_excess(Q(9, 10), Q(1, 5), Q(1, 10)) > 0


@pytest.mark.parametrize("call", [
    lambda: gold_noise_forward(Q(4, 5), Q(1, 10), Q(1, 10), HALF),
    lambda: gold_noise_forward(Q(4, 5), Q(1, 10), Q(3, 5), Q(1, 20)),
    lambda: gold_noise_forward(Q(4, 5), Q(1, 10), Q(1, 10), 0.05),
    lambda: gold_noise_inverse(Q(1, 100), Q(1, 10), Q(1, 10), Q(1, 20)),
    lambda: gold_noise_inverse(Q(4, 5), Q(1, 10), Q(1, 10), Q(1, 2)),
])
def test_gold_noise_rejects_malformed(call):
    with pytest.raises(ValueError):
        call()


# --- ledger and card -----------------------------------------------------------

def test_ledger_read_once_is_evaluable_and_any_touch_withholds():
    train, sample = ("t0", "t1"), ("g0", "g1")
    once = (LoopEvent(1, "judge_sample", "readout"),)
    assert measurement_ledger(train, sample, once)["readout"]["judge_sample"]["endpoint_status"] == "evaluable"
    twice = once + (LoopEvent(2, "judge_sample", "readout"),)
    assert measurement_ledger(train, sample, twice)["readout"]["judge_sample"]["endpoint_status"] == "not_evaluated"
    scored = once + (LoopEvent(2, "judge_sample", "score_query"),)
    assert measurement_ledger(train, sample, scored)["readout"]["judge_sample"]["endpoint_status"] == "not_evaluated"
    with pytest.raises(ValueError):
        measurement_ledger(("t0", "shared"), ("shared", "g1"), once)


def test_card_item_fields_and_validity():
    table = JudgeTable(144, 16, 36, 4)
    ledger = measurement_ledger(("t0",), ("g0",), (LoopEvent(1, "judge_sample", "readout"),))
    item = card_item(table, Q(1, 10), Q(1, 20), "third grader", True, True, False, ledger)
    assert item["controller_wrong_W"] == 40 and item["judge_wrong_on_wrong_W1"] == 4
    assert item["eps1_hat"] == Q(1, 10) and item["excess_hat"] == 0 and item["inflation_hat"] == 0
    assert item["test_independence"]["p_value"] == independence_p_value(40, 4, Q(1, 10))
    assert item["test_ceiling"]["p_value"] == ceiling_p_value(40, 4)
    assert item["test_independence_conditional"]["p_value"] == fisher_p_value(table)
    assert item["measurement_valid"]
    text = render_card_item(item)
    assert "W=40, W1=4" in text and "evaluable" in text and "third grader" in text
    assert not card_item(table, Q(1, 10), Q(1, 20), "third grader", False, True, False, ledger)["measurement_valid"]
    for bad in (dict(gold_source=""), dict(gold_independent_of_judge=1), dict(judge_trained_on_controller_outputs=None)):
        kwargs = dict(gold_source="third grader", gold_independent_of_judge=True,
                      gold_independent_of_controller=True, judge_trained_on_controller_outputs=False)
        kwargs.update(bad)
        with pytest.raises(ValueError):
            card_item(table, Q(1, 10), Q(1, 20), ledger=ledger, **kwargs)


def test_fixture_values_and_verify():
    report = verify()
    assert report["all_passed"] and len(report["checks"]) == 19
    assert report["evidence_status"].startswith("exact_synthetic")
    ind, shared = report["judges"]["independent"], report["judges"]["maximally_shared"]
    assert ind["table"] == JudgeTable(144, 16, 36, 4) and shared["table"] == JudgeTable(160, 0, 20, 20)
    assert ind["independence_p"] == binomial_upper_tail(40, Q(1, 10), 4) > Q(1, 2)
    assert shared["independence_p"] == sum(
        (comb(40, k) * Q(1, 10) ** k * Q(9, 10) ** (40 - k) for k in range(20, 41)), Q(0)) < Q(1, 10 ** 9)
    assert ind["ceiling_p"] == Q(sum(comb(40, k) for k in range(5)), 2 ** 40) == Q(102091, 2 ** 40)
    assert shared["ceiling_p"] == Q(sum(comb(40, k) for k in range(21)), 2 ** 40)
    assert shared["estimates"]["inflation_hat"] == judge_correlation_inflation(Q(4, 5), Q(1, 10), Q(1, 2)) == Q(4, 25)
    assert report["gold_noise"]["judges"]["independent"]["measured"]["eps1"] == Q(11, 46)
    assert report["planning"]["eps=1/10,beta=1/10"]["smallest"] == 12
