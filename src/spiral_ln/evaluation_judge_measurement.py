"""Measuring the judge's shared error rate on a sealed sample, with exact inference.

L4 of the training-signal note says a binary judge that is wrong with
probability ``eps1`` on items the controller gets wrong lifts observed accuracy
by ``2 (1 - a) (eps1 - eps)`` and reaches the noise ceiling at ``eps1 >= 1/2``.
Axiom A2 (independent judge errors) is checkable only if ``eps1`` is measured.
This module gives that measurement its bookkeeping and its inference.

1. A 2x2 table of controller-right/wrong by judge-right/wrong, both against gold
   from a source independent of controller and judge, on a sample declared as a
   sealed readout set and read once.  The agreement rate equals
   ``a - eps + 2 (1 - a) eps1`` with the rates replaced by their table
   estimates; the identity is exact bookkeeping.
2. Exact binomial tails as fractions on the conditional count
   ``W1 ~ Bin(W, eps1)``: a one-sided test of independence (``eps1 = eps``
   against ``eps1 > eps``) with ``eps`` declared, Fisher's conditional test when
   it is not, a one-sided test of the ceiling condition (``eps1 >= 1/2`` against
   ``eps1 < 1/2``), sample-size planning with power enumerated over the
   rejection region, and exact brackets for the Clopper-Pearson endpoints.
3. Gold labels flipped independently at rate ``eta < 1/2``: the measured rates
   are an invertible affine image of the true ones, the agreement rate is
   invariant, and an independent judge shows a positive measured excess
   ``eps1' - eps'`` whenever ``a > 1/2`` and ``eps < 1/2``.

Nothing here calls a model.  Every quantity is a ``fractions.Fraction``; floats
are rejected at the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from fractions import Fraction as Q
from math import comb

from spiral_ln.evaluation_feedback_signal import (
    ceiling_reachable_without_memorization, judge_correlation_inflation,
    observed_accuracy_shared, shared_error_bounds,
)
from spiral_ln.evaluation_game_feedback import (
    EvalSet, LoopEvent, audit_ledger, noise_ceiling, observed_accuracy,
)

HALF = Q(1, 2)


def _as_q(value, name: str) -> Q:
    if isinstance(value, bool) or not isinstance(value, (int, Q)):
        raise ValueError(f"{name} must be an int or Fraction, not {type(value).__name__}")
    return Q(value)


def _probability(value, name: str) -> Q:
    value = _as_q(value, name)
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must lie in [0, 1]")
    return value


def _count(value, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


# --- 1. the table and its estimates -------------------------------------------

@dataclass(frozen=True)
class JudgeTable:
    """Counts of a gold-labelled sample by controller right/wrong and judge
    right/wrong, both judged against gold.

    ``right_right`` (R0): controller right, judge right.
    ``right_wrong`` (R1): controller right, judge wrong.
    ``wrong_right`` (W0): controller wrong, judge right.
    ``wrong_wrong`` (W1): controller wrong, judge wrong.  With binary labels a
    judge wrong about a wrong answer marks it correct, so it agrees with it.
    """

    right_right: int
    right_wrong: int
    wrong_right: int
    wrong_wrong: int

    def __post_init__(self) -> None:
        for field in fields(self):
            _count(getattr(self, field.name), field.name)
        if self.size < 1:
            raise ValueError("the table needs at least one item")

    @property
    def size(self) -> int:
        return self.right_right + self.right_wrong + self.wrong_right + self.wrong_wrong

    @property
    def controller_right(self) -> int:
        return self.right_right + self.right_wrong

    @property
    def controller_wrong(self) -> int:
        return self.wrong_right + self.wrong_wrong

    @property
    def judge_wrong(self) -> int:
        return self.right_wrong + self.wrong_wrong

    @property
    def agreements(self) -> int:
        return self.right_right + self.wrong_wrong


def table_estimates(table: JudgeTable) -> dict[str, object]:
    """Exact plug-in estimates and the bookkeeping identity.

    ``eps0_hat`` is undefined when the controller is never right and
    ``eps1_hat`` when it is never wrong; the identity is written with
    ``2 (1 - a_hat) eps1_hat = 2 W1 / m``, which is defined in every case.
    """

    m = table.size
    a_hat, eps_hat = Q(table.controller_right, m), Q(table.judge_wrong, m)
    eps0_hat = Q(table.right_wrong, table.controller_right) if table.controller_right else None
    eps1_hat = Q(table.wrong_wrong, table.controller_wrong) if table.controller_wrong else None
    agreement = Q(table.agreements, m)
    identity_rhs = a_hat - eps_hat + 2 * Q(table.wrong_wrong, m)
    inflation = None
    if eps0_hat is not None and eps1_hat is not None:
        inflation = judge_correlation_inflation(a_hat, eps_hat, eps1_hat)
    return {"size": m, "controller_wrong": table.controller_wrong,
            "a_hat": a_hat, "eps_hat": eps_hat, "eps0_hat": eps0_hat, "eps1_hat": eps1_hat,
            "agreement_rate": agreement, "identity_rhs": identity_rhs,
            "identity_holds": agreement == identity_rhs,
            "excess_hat": None if eps1_hat is None else eps1_hat - eps_hat,
            "inflation_hat": inflation}


def agreement_identity_holds(table: JudgeTable) -> bool:
    """``(R0 + W1) / m == a_hat - eps_hat + 2 (1 - a_hat) eps1_hat``.

    Proof: ``a_hat - eps_hat = (R0 + R1 - R1 - W1) / m = (R0 - W1) / m`` and
    ``2 (1 - a_hat) eps1_hat = 2 (W / m)(W1 / W) = 2 W1 / m``; the sum is
    ``(R0 + W1) / m``.
    """

    return table_estimates(table)["identity_holds"]


def expected_table(size: int, accuracy, judge_error, eps1) -> dict[str, Q]:
    """Expected cell counts, as exact rationals, for a sample of ``size`` items
    from a controller of accuracy ``a``, a judge of marginal error ``eps`` and
    shared error ``eps1``; ``eps0`` follows from the marginal."""

    if type(size) is not int or size < 1:
        raise ValueError("size must be a positive integer")
    accuracy, judge_error, eps1 = (_probability(accuracy, "accuracy"),
                                   _probability(judge_error, "judge_error"),
                                   _probability(eps1, "eps1"))
    low, high = shared_error_bounds(accuracy, judge_error)
    if not low <= eps1 <= high:
        raise ValueError("eps1 is infeasible for the marginal judge error")
    eps0 = (judge_error - (1 - accuracy) * eps1) / accuracy
    return {"right_right": size * accuracy * (1 - eps0),
            "right_wrong": size * accuracy * eps0,
            "wrong_right": size * (1 - accuracy) * (1 - eps1),
            "wrong_wrong": size * (1 - accuracy) * eps1}


def rounded_table(expected: dict[str, Q]) -> tuple[JudgeTable, bool]:
    """Round each expected cell half-up to an integer.  Returns the table and
    whether any cell changed; a rounded table may not sum to the planned size."""

    cells = {}
    for name in ("right_right", "right_wrong", "wrong_right", "wrong_wrong"):
        value = _as_q(expected[name], name)
        if value < 0:
            raise ValueError("expected counts must be nonnegative")
        cells[name] = int((value + HALF).__floor__())
    changed = any(Q(cells[name]) != expected[name] for name in cells)
    return JudgeTable(**cells), changed


# --- 2. exact binomial tails and the tests ------------------------------------

def binomial_pmf(trials: int, p) -> list[Q]:
    trials, p = _count(trials, "trials"), _probability(p, "p")
    return [Q(comb(trials, j)) * p ** j * (1 - p) ** (trials - j) for j in range(trials + 1)]


def binomial_upper_tail(trials: int, p, k: int) -> Q:
    """``P(Bin(trials, p) >= k)``; one for ``k <= 0`` and zero past ``trials``."""

    if type(k) is not int:
        raise ValueError("k must be an integer")
    return sum(binomial_pmf(trials, p)[max(k, 0):], Q(0))


def binomial_lower_tail(trials: int, p, k: int) -> Q:
    """``P(Bin(trials, p) <= k)``; zero for ``k < 0`` and one from ``trials`` on."""

    if type(k) is not int:
        raise ValueError("k must be an integer")
    return sum(binomial_pmf(trials, p)[:max(k + 1, 0)], Q(0))


def _conditional_counts(wrong: int, wrong_wrong: int) -> tuple[int, int]:
    wrong, wrong_wrong = _count(wrong, "wrong"), _count(wrong_wrong, "wrong_wrong")
    if wrong < 1:
        raise ValueError("the conditional tests need at least one controller-wrong item")
    if wrong_wrong > wrong:
        raise ValueError("wrong_wrong cannot exceed wrong")
    return wrong, wrong_wrong


def independence_p_value(wrong: int, wrong_wrong: int, judge_error) -> Q:
    """Exact one-sided p-value of ``H0: eps1 = eps`` against ``H1: eps1 > eps``:
    ``P(Bin(W, eps) >= W1)`` with ``eps`` declared from a source other than this
    table.  With ``eps`` replaced by this table's ``eps_hat`` the test is a
    plug-in approximation; use ``fisher_p_value`` for an exact test then."""

    wrong, wrong_wrong = _conditional_counts(wrong, wrong_wrong)
    return binomial_upper_tail(wrong, _probability(judge_error, "judge_error"), wrong_wrong)


def ceiling_p_value(wrong: int, wrong_wrong: int) -> Q:
    """Exact p-value of ``H0: eps1 >= 1/2`` against ``H1: eps1 < 1/2``:
    ``P(Bin(W, 1/2) <= W1)``.  The lower tail is non-increasing in ``eps1``, so
    the supremum over the composite null is attained at ``eps1 = 1/2``."""

    wrong, wrong_wrong = _conditional_counts(wrong, wrong_wrong)
    return binomial_lower_tail(wrong, HALF, wrong_wrong)


def hypergeometric_pmf(population: int, successes: int, draws: int) -> list[Q]:
    population, successes, draws = (_count(population, "population"),
                                    _count(successes, "successes"), _count(draws, "draws"))
    if successes > population or draws > population:
        raise ValueError("successes and draws cannot exceed the population")
    total = comb(population, draws)
    return [Q(comb(successes, k) * comb(population - successes, draws - k), total)
            for k in range(draws + 1)]


def fisher_p_value(table: JudgeTable) -> Q:
    """Exact one-sided test of independence conditional on both margins.

    Under ``eps1 = eps0`` the ``W`` controller-wrong items are an exchangeable
    draw from the ``m`` items, of which ``E = R1 + W1`` are judge-wrong, so
    ``W1`` is hypergeometric; the p-value is ``P(X >= W1)``.  Needs no
    declared ``eps``."""

    if table.controller_wrong < 1:
        raise ValueError("Fisher's test needs at least one controller-wrong item")
    pmf = hypergeometric_pmf(table.size, table.judge_wrong, table.controller_wrong)
    return sum(pmf[table.wrong_wrong:], Q(0))


def rejection_threshold(wrong: int, judge_error, alpha) -> int:
    """Smallest ``c`` with ``P(Bin(W, eps) >= c) <= alpha``; the level-``alpha``
    test rejects at ``W1 >= c``.  Equals ``W + 1`` when no count rejects."""

    wrong = _count(wrong, "wrong")
    judge_error, alpha = _probability(judge_error, "judge_error"), _probability(alpha, "alpha")
    pmf = binomial_pmf(wrong, judge_error)
    tail, c = Q(0), wrong + 1
    for k in range(wrong, -1, -1):
        tail += pmf[k]
        if tail > alpha:
            break
        c = k
    return c


def power_at(wrong: int, judge_error, alpha, alternative=HALF) -> Q:
    """Exact power of the level-``alpha`` test of ``eps1 = eps`` when the true
    shared error is ``alternative``: the alternative's mass on the rejection
    region ``{W1 >= c}``.  Zero power when ``W = 0``."""

    wrong = _count(wrong, "wrong")
    alternative = _probability(alternative, "alternative")
    if not alternative > _probability(judge_error, "judge_error"):
        raise ValueError("the alternative must exceed the null error rate")
    if wrong == 0:
        return Q(0)
    return binomial_upper_tail(wrong, alternative, rejection_threshold(wrong, judge_error, alpha))


def smallest_wrong_count(judge_error, alpha, beta, alternative=HALF, horizon: int = 200) -> dict[str, object]:
    """Smallest ``W`` at which the level-``alpha`` exact test has power at least
    ``1 - beta`` against ``alternative``, and the smallest ``W`` from which the
    power stays there for every larger ``W`` up to ``horizon`` (exact power is
    a sawtooth in ``W``, so the two can differ)."""

    beta = _probability(beta, "beta")
    if type(horizon) is not int or horizon < 1:
        raise ValueError("horizon must be a positive integer")
    powers = {w: power_at(w, judge_error, alpha, alternative) for w in range(1, horizon + 1)}
    hits = [w for w in powers if powers[w] >= 1 - beta]
    if not hits:
        raise ValueError("no sample size up to the horizon reaches the requested power")
    smallest = hits[0]
    stable = horizon + 1
    for w in range(horizon, 0, -1):
        if powers[w] < 1 - beta:
            break
        stable = w
    return {"smallest": smallest, "threshold": rejection_threshold(smallest, judge_error, alpha),
            "power": powers[smallest], "stable_from": stable, "horizon": horizon,
            "sawtooth": stable != smallest}


def expected_sample_size(wrong: int, accuracy) -> dict[str, object]:
    """``m`` whose expected controller-wrong count is ``W``: ``W / (1 - a)``.
    An expectation, not a guarantee: the realised ``W`` is ``Bin(m, 1 - a)``."""

    wrong, accuracy = _count(wrong, "wrong"), _probability(accuracy, "accuracy")
    if accuracy == 1:
        raise ValueError("a perfect controller yields no wrong items")
    exact = Q(wrong) / (1 - accuracy)
    return {"expected": exact, "ceiling": int(-(-exact.numerator // exact.denominator))}


def unconditional_power(size: int, accuracy, judge_error, alpha, alternative=HALF) -> Q:
    """Power of the whole procedure at sample size ``m``: ``W ~ Bin(m, 1 - a)``,
    then the conditional test; ``sum_w P(W = w) power(w)``."""

    if type(size) is not int or size < 1:
        raise ValueError("size must be a positive integer")
    accuracy = _probability(accuracy, "accuracy")
    weights = binomial_pmf(size, 1 - accuracy)
    return sum((weights[w] * power_at(w, judge_error, alpha, alternative) for w in range(size + 1)), Q(0))


def smallest_sample_size(accuracy, judge_error, alpha, beta, alternative=HALF,
                         margin: int = 25, horizon: int = 2000) -> dict[str, object]:
    """Smallest ``m`` whose unconditional power reaches ``1 - beta``, scanning
    ``m`` upward, with the power re-checked on the next ``margin`` sizes.  This
    is the guarantee that ``expected_sample_size`` is not."""

    beta = _probability(beta, "beta")
    accuracy = _probability(accuracy, "accuracy")
    if type(margin) is not int or margin < 0 or type(horizon) is not int or horizon < 1:
        raise ValueError("margin must be a nonnegative integer and horizon a positive integer")
    conditional: dict[int, Q] = {}

    def power(w: int) -> Q:
        if w not in conditional:
            conditional[w] = power_at(w, judge_error, alpha, alternative)
        return conditional[w]

    def whole(m: int) -> Q:
        weights = binomial_pmf(m, 1 - accuracy)
        return sum((weights[w] * power(w) for w in range(m + 1)), Q(0))

    for m in range(1, horizon + 1):
        value = whole(m)
        if value >= 1 - beta:
            window = {m + k: whole(m + k) for k in range(1, margin + 1)}
            return {"smallest_m": m, "power": value,
                    "holds_on_next": all(v >= 1 - beta for v in window.values()),
                    "window_min_power": min(window.values()) if window else value, "margin": margin}
    raise ValueError("no sample size up to the horizon reaches the requested power")


def clopper_pearson_contains(wrong: int, wrong_wrong: int, alpha, value) -> bool:
    """Exact membership of ``value`` in the two-sided level-``alpha``
    Clopper-Pearson interval for ``eps1``: both tails at ``value`` are at
    least ``alpha / 2``."""

    wrong, wrong_wrong = _conditional_counts(wrong, wrong_wrong)
    alpha, value = _probability(alpha, "alpha"), _probability(value, "value")
    return (binomial_upper_tail(wrong, value, wrong_wrong) >= alpha / 2
            and binomial_lower_tail(wrong, value, wrong_wrong) >= alpha / 2)


def clopper_pearson_bracket(wrong: int, wrong_wrong: int, alpha, resolution=Q(1, 2 ** 16)) -> dict[str, object]:
    """Rational brackets of width at most ``resolution`` around the two
    Clopper-Pearson endpoints, found by bisection on exact tails.

    The lower endpoint solves ``P(Bin(W, L) >= W1) = alpha / 2`` (``L = 0`` when
    ``W1 = 0``) and the upper ``P(Bin(W, U) <= W1) = alpha / 2`` (``U = 1`` when
    ``W1 = W``).  They are beta quantiles, algebraic and in general irrational,
    so only brackets are exact; membership of any rational is decided exactly
    by ``clopper_pearson_contains``."""

    wrong, wrong_wrong = _conditional_counts(wrong, wrong_wrong)
    alpha, resolution = _probability(alpha, "alpha"), _as_q(resolution, "resolution")
    if not 0 < alpha < 1 or not resolution > 0:
        raise ValueError("alpha must lie strictly inside (0, 1) and resolution be positive")
    half_alpha = alpha / 2

    def bisect(reject) -> tuple[Q, Q]:
        low, high = Q(0), Q(1)
        while high - low > resolution:
            mid = (low + high) / 2
            if reject(mid):
                low = mid
            else:
                high = mid
        return low, high

    lower = (Q(0), Q(0)) if wrong_wrong == 0 else bisect(
        lambda p: binomial_upper_tail(wrong, p, wrong_wrong) < half_alpha)
    upper = (Q(1), Q(1)) if wrong_wrong == wrong else bisect(
        lambda p: binomial_lower_tail(wrong, p, wrong_wrong) >= half_alpha)
    return {"lower": lower, "upper": upper, "resolution": resolution,
            "point": Q(wrong_wrong, wrong), "alpha": alpha,
            "endpoints_are": "beta quantiles; bracketed, not returned exactly"}


# --- 3. gold noise ------------------------------------------------------------

def gold_noise_forward(accuracy, judge_error, eps1, eta) -> dict[str, Q]:
    """Expected measured rates when gold flips independently at rate ``eta``.

    Measured controller-right is ``C xor F`` and measured judge-right is
    ``J xor F`` (binary labels), so
    ``a' = eta + a (1 - 2 eta)``, ``eps' = eta + eps (1 - 2 eta)``,
    ``W1'/m = (1 - a) eps1 + eta (a - eps)`` and ``eps1' = (W1'/m) / (1 - a')``.
    The agreement rate ``C = J`` does not involve gold and is unchanged."""

    accuracy, judge_error, eps1 = (_probability(accuracy, "accuracy"),
                                   _probability(judge_error, "judge_error"),
                                   _probability(eps1, "eps1"))
    eta = _probability(eta, "eta")
    if not eta < HALF:
        raise ValueError("eta must lie below one half")
    low, high = shared_error_bounds(accuracy, judge_error)
    if not low <= eps1 <= high:
        raise ValueError("eps1 is infeasible for the marginal judge error")
    measured_accuracy = eta + accuracy * (1 - 2 * eta)
    measured_error = eta + judge_error * (1 - 2 * eta)
    wrong_wrong_rate = (1 - accuracy) * eps1 + eta * (accuracy - judge_error)
    measured_eps1 = wrong_wrong_rate / (1 - measured_accuracy)
    measured_eps0 = (measured_error - (1 - measured_accuracy) * measured_eps1) / measured_accuracy
    return {"accuracy": measured_accuracy, "judge_error": measured_error,
            "eps1": measured_eps1, "eps0": measured_eps0,
            "wrong_wrong_rate": wrong_wrong_rate,
            "agreement_rate": observed_accuracy_shared(accuracy, judge_error, eps1)}


def gold_noise_inverse(measured_accuracy, measured_error, measured_eps1, eta) -> dict[str, Q]:
    """Invert ``gold_noise_forward`` at a known ``eta < 1/2``:
    ``a = (a' - eta) / (1 - 2 eta)``, ``eps = (eps' - eta) / (1 - 2 eta)``,
    ``eps1 = (eps1' (1 - a') - eta (a - eps)) / (1 - a)``."""

    measured_accuracy, measured_error, measured_eps1 = (
        _probability(measured_accuracy, "measured_accuracy"),
        _probability(measured_error, "measured_error"),
        _probability(measured_eps1, "measured_eps1"))
    eta = _probability(eta, "eta")
    if not eta < HALF:
        raise ValueError("eta must lie below one half")
    accuracy = (measured_accuracy - eta) / (1 - 2 * eta)
    judge_error = (measured_error - eta) / (1 - 2 * eta)
    if not 0 <= accuracy < 1 or not 0 <= judge_error <= 1:
        raise ValueError("measured rates are not the image of any true rates at this eta")
    eps1 = (measured_eps1 * (1 - measured_accuracy) - eta * (accuracy - judge_error)) / (1 - accuracy)
    return {"accuracy": accuracy, "judge_error": judge_error, "eps1": eps1}


def independent_judge_measured_excess(accuracy, judge_error, eta) -> Q:
    """``eps1' - eps'`` shown by an independent judge (``eps1 = eps``) under gold
    noise: ``eta (1 - eta)(2a - 1)(1 - 2 eps) / (1 - a')``.  Positive whenever
    ``a > 1/2`` and ``eps < 1/2``: a flipped gold label makes controller and
    judge look wrong together, the enrichment of ``failed_item_noise_share``."""

    measured = gold_noise_forward(accuracy, judge_error, judge_error, eta)
    accuracy, judge_error, eta = Q(accuracy), Q(judge_error), Q(eta)
    closed_form = eta * (1 - eta) * (2 * accuracy - 1) * (1 - 2 * judge_error) / (1 - measured["accuracy"])
    if measured["eps1"] - measured["judge_error"] != closed_form:
        raise AssertionError("closed form for the measured excess failed")
    return closed_form


# --- 4. ledger and card -------------------------------------------------------

def measurement_ledger(training_ids: tuple[str, ...], sample_ids: tuple[str, ...],
                       events: tuple[LoopEvent, ...]) -> dict[str, object]:
    """Audit the sample as a sealed readout set read once beside the training
    set, through the shared ledger; a second read or any feedback on the sample
    is a breach and withholds the measurement."""

    sets = (EvalSet("train", "selection", "item_level", training_ids),
            EvalSet("judge_sample", "readout", "sealed", sample_ids))
    return audit_ledger(sets, events, 1, Q(1, 2))


def card_item(table: JudgeTable, declared_judge_error, alpha, gold_source: str,
              gold_independent_of_judge: bool, gold_independent_of_controller: bool,
              judge_trained_on_controller_outputs: bool, ledger: dict[str, object]) -> dict[str, object]:
    """The evaluation-card entry that makes A2 checkable."""

    if not isinstance(gold_source, str) or not gold_source:
        raise ValueError("gold_source must name the source")
    for flag in (gold_independent_of_judge, gold_independent_of_controller,
                 judge_trained_on_controller_outputs):
        if type(flag) is not bool:
            raise ValueError("independence and training declarations must be booleans")
    estimates = table_estimates(table)
    wrong, wrong_wrong = table.controller_wrong, table.wrong_wrong
    declared = _probability(declared_judge_error, "declared_judge_error")
    status = ledger["readout"]["judge_sample"]["endpoint_status"]
    return {
        "sample_size": table.size, "controller_wrong_W": wrong, "judge_wrong_on_wrong_W1": wrong_wrong,
        "accuracy_hat": estimates["a_hat"], "judge_error_hat": estimates["eps_hat"],
        "judge_error_declared": declared, "eps1_hat": estimates["eps1_hat"],
        "excess_hat": estimates["excess_hat"], "inflation_hat": estimates["inflation_hat"],
        "test_independence": {"null": "eps1 = eps (declared)", "alternative": "eps1 > eps",
                              "statistic": "W1 ~ Bin(W, eps)", "alpha": _probability(alpha, "alpha"),
                              "p_value": independence_p_value(wrong, wrong_wrong, declared)},
        "test_independence_conditional": {"null": "eps1 = eps0", "statistic": "W1 hypergeometric on margins",
                                          "p_value": fisher_p_value(table)},
        "test_ceiling": {"null": "eps1 >= 1/2", "alternative": "eps1 < 1/2",
                         "statistic": "W1 ~ Bin(W, 1/2)", "p_value": ceiling_p_value(wrong, wrong_wrong)},
        "gold_source": gold_source,
        "gold_independent_of_judge": gold_independent_of_judge,
        "gold_independent_of_controller": gold_independent_of_controller,
        "judge_trained_on_controller_outputs": judge_trained_on_controller_outputs,
        "ledger_set": "judge_sample", "ledger_status": status,
        "measurement_valid": (status == "evaluable" and gold_independent_of_judge
                              and gold_independent_of_controller),
    }


def render_card_item(item: dict[str, object]) -> str:
    """One paragraph for item 11 of the evaluation card."""

    independence, ceiling = item["test_independence"], item["test_ceiling"]
    return (
        f"Judge shared error: sample m={item['sample_size']} from {item['gold_source']} "
        f"(independent of judge: {item['gold_independent_of_judge']}; of controller: "
        f"{item['gold_independent_of_controller']}), ledger set {item['ledger_set']} "
        f"({item['ledger_status']}). W={item['controller_wrong_W']}, W1={item['judge_wrong_on_wrong_W1']}; "
        f"eps declared {item['judge_error_declared']}, eps_hat {item['judge_error_hat']}, "
        f"eps1_hat {item['eps1_hat']}. Exact binomial test of eps1=eps vs eps1>eps: "
        f"p={independence['p_value']} (alpha {independence['alpha']}); Fisher conditional: "
        f"p={item['test_independence_conditional']['p_value']}; ceiling test eps1>=1/2 vs <1/2: "
        f"p={ceiling['p_value']}. Judge trained on controller outputs: "
        f"{item['judge_trained_on_controller_outputs']}."
    )


# --- fixtures and verification ------------------------------------------------

FIXTURE_SIZE, FIXTURE_ACCURACY, FIXTURE_ERROR = 200, Q(4, 5), Q(1, 10)
PLANNING_ERRORS = (Q(1, 20), Q(1, 10), Q(1, 5))
PLANNING_ALPHA = Q(1, 20)
PLANNING_BETAS = (Q(1, 5), Q(1, 10))
PLANNING_ACCURACIES = (Q(4, 5), Q(9, 10))


def judge_fixture() -> dict[str, dict[str, object]]:
    """The two judges of the signal fixture on a sample of 200 items."""

    judges = {"independent": FIXTURE_ERROR, "maximally_shared": Q(1, 2)}
    out = {}
    for name, eps1 in judges.items():
        expected = expected_table(FIXTURE_SIZE, FIXTURE_ACCURACY, FIXTURE_ERROR, eps1)
        table, changed = rounded_table(expected)
        estimates = table_estimates(table)
        wrong, wrong_wrong = table.controller_wrong, table.wrong_wrong
        out[name] = {
            "eps1": eps1, "expected": expected, "table": table,
            "rounding": "half-up per cell", "rounding_changed_a_cell": changed,
            "estimates": estimates,
            "observed_accuracy_identity":
                estimates["agreement_rate"] == observed_accuracy_shared(FIXTURE_ACCURACY, FIXTURE_ERROR, eps1),
            "independence_p": independence_p_value(wrong, wrong_wrong, FIXTURE_ERROR),
            "fisher_p": fisher_p_value(table),
            "ceiling_p": ceiling_p_value(wrong, wrong_wrong),
            "clopper_pearson": clopper_pearson_bracket(wrong, wrong_wrong, PLANNING_ALPHA),
            "cp_contains_eps": clopper_pearson_contains(wrong, wrong_wrong, PLANNING_ALPHA, FIXTURE_ERROR),
            "cp_contains_half": clopper_pearson_contains(wrong, wrong_wrong, PLANNING_ALPHA, HALF),
        }
    return out


def planning_fixture() -> dict[str, dict[str, object]]:
    cells = {}
    for eps in PLANNING_ERRORS:
        for beta in PLANNING_BETAS:
            plan = smallest_wrong_count(eps, PLANNING_ALPHA, beta)
            sizes = {str(a): expected_sample_size(plan["smallest"], a) for a in PLANNING_ACCURACIES}
            whole = {str(a): unconditional_power(sizes[str(a)]["ceiling"], a, eps, PLANNING_ALPHA)
                     for a in PLANNING_ACCURACIES}
            guaranteed = {str(a): smallest_sample_size(a, eps, PLANNING_ALPHA, beta) for a in PLANNING_ACCURACIES}
            cells[f"eps={eps},beta={beta}"] = {"eps": eps, "beta": beta, **plan,
                                               "expected_m": sizes, "unconditional_power_at_expected_m": whole,
                                               "guaranteed_m": guaranteed}
    return cells


def gold_noise_fixture() -> dict[str, object]:
    eta = Q(1, 20)
    rows = {}
    for name, eps1 in (("independent", FIXTURE_ERROR), ("maximally_shared", Q(1, 2))):
        measured = gold_noise_forward(FIXTURE_ACCURACY, FIXTURE_ERROR, eps1, eta)
        recovered = gold_noise_inverse(measured["accuracy"], measured["judge_error"], measured["eps1"], eta)
        rows[name] = {"true_eps1": eps1, "measured": measured, "recovered": recovered,
                      "inverts": recovered == {"accuracy": FIXTURE_ACCURACY, "judge_error": FIXTURE_ERROR,
                                               "eps1": eps1},
                      "agreement_invariant":
                          measured["agreement_rate"] == observed_accuracy_shared(FIXTURE_ACCURACY, FIXTURE_ERROR, eps1)}
    return {"eta": eta, "judges": rows,
            "independent_judge_measured_excess": independent_judge_measured_excess(FIXTURE_ACCURACY, FIXTURE_ERROR, eta)}


def ledger_fixture() -> dict[str, object]:
    train = tuple(f"t{i}" for i in range(8))
    sample = tuple(f"g{i}" for i in range(8))
    respected = (LoopEvent(1, "train", "item_feedback", ("t0", "t1")),
                 LoopEvent(2, "judge_sample", "readout"))
    breached = respected + (LoopEvent(3, "judge_sample", "readout"),
                            LoopEvent(4, "judge_sample", "item_feedback", ("g0",)))
    return {"respected": measurement_ledger(train, sample, respected),
            "breached": measurement_ledger(train, sample, breached)}


def card_fixture() -> dict[str, object]:
    judges, ledgers = judge_fixture(), ledger_fixture()
    items = {name: card_item(judges[name]["table"], FIXTURE_ERROR, PLANNING_ALPHA,
                             "held-out gold labels from a third grader", True, True,
                             name == "maximally_shared", ledgers["respected"])
             for name in judges}
    withheld = card_item(judges["independent"]["table"], FIXTURE_ERROR, PLANNING_ALPHA,
                         "held-out gold labels from a third grader", True, True, False, ledgers["breached"])
    return {"items": items, "rendered": {name: render_card_item(item) for name, item in items.items()},
            "withheld_after_breach": withheld}


def verify() -> dict[str, object]:
    """Run all exact fixtures and return machine-readable checks."""

    judges, planning, gold, ledgers, cards = (judge_fixture(), planning_fixture(), gold_noise_fixture(),
                                              ledger_fixture(), card_fixture())
    ind, shared = judges["independent"], judges["maximally_shared"]
    grid_tables = [JudgeTable(r0, r1, w0, w1) for r0 in range(4) for r1 in range(4)
                   for w0 in range(4) for w1 in range(4) if r0 + r1 + w0 + w1]
    plan_rows = list(planning.values())
    checks = {
        "fixture_tables_are_integral_without_rounding":
            not ind["rounding_changed_a_cell"] and not shared["rounding_changed_a_cell"]
            and ind["table"] == JudgeTable(144, 16, 36, 4) and shared["table"] == JudgeTable(160, 0, 20, 20),
        "estimates_recover_a_eps_eps1":
            all(j["estimates"]["a_hat"] == FIXTURE_ACCURACY and j["estimates"]["eps_hat"] == FIXTURE_ERROR
                and j["estimates"]["eps1_hat"] == j["eps1"] for j in judges.values()),
        "agreement_identity_on_every_small_table": all(agreement_identity_holds(t) for t in grid_tables),
        "agreement_equals_L4_observed_accuracy":
            ind["observed_accuracy_identity"] and shared["observed_accuracy_identity"]
            and ind["estimates"]["agreement_rate"] == Q(37, 50)
            and shared["estimates"]["agreement_rate"] == noise_ceiling(FIXTURE_ERROR) == Q(9, 10),
        "inflation_hat_matches_L4_identity":
            all(j["estimates"]["inflation_hat"] == 2 * (1 - FIXTURE_ACCURACY) * (j["eps1"] - FIXTURE_ERROR)
                for j in judges.values()) and shared["estimates"]["inflation_hat"] == Q(4, 25),
        "independent_judge_not_rejected_shared_judge_rejected":
            ind["independence_p"] > PLANNING_ALPHA > shared["independence_p"]
            and ind["fisher_p"] > PLANNING_ALPHA > shared["fisher_p"],
        "ceiling_rejected_for_independent_judge_only":
            ind["ceiling_p"] < PLANNING_ALPHA < shared["ceiling_p"],
        "clopper_pearson_separates_the_two_judges":
            ind["cp_contains_eps"] and not ind["cp_contains_half"]
            and shared["cp_contains_half"] and not shared["cp_contains_eps"],
        "clopper_pearson_brackets_hold_the_point":
            all(j["clopper_pearson"]["lower"][1] < j["clopper_pearson"]["point"] < j["clopper_pearson"]["upper"][0]
                for j in judges.values()),
        "planning_power_reaches_target_and_fails_one_below":
            all(row["power"] >= 1 - row["beta"]
                and (row["smallest"] == 1 or power_at(row["smallest"] - 1, row["eps"], PLANNING_ALPHA) < 1 - row["beta"])
                for row in plan_rows),
        "planning_thresholds_are_level_alpha":
            all(binomial_upper_tail(row["smallest"], row["eps"], row["threshold"]) <= PLANNING_ALPHA
                < binomial_upper_tail(row["smallest"], row["eps"], row["threshold"] - 1) for row in plan_rows),
        "planning_W_grows_with_eps_and_with_power":
            all(planning[f"eps={e0},beta={b}"]["smallest"] <= planning[f"eps={e1},beta={b}"]["smallest"]
                for e0, e1 in zip(PLANNING_ERRORS, PLANNING_ERRORS[1:]) for b in PLANNING_BETAS)
            and all(planning[f"eps={e},beta={Q(1, 5)}"]["smallest"] <= planning[f"eps={e},beta={Q(1, 10)}"]["smallest"]
                    for e in PLANNING_ERRORS),
        "expected_m_underpowers_and_guaranteed_m_exceeds_it":
            all(row["unconditional_power_at_expected_m"][a] < 1 - row["beta"]
                and row["guaranteed_m"][a]["smallest_m"] > row["expected_m"][a]["ceiling"]
                and row["guaranteed_m"][a]["holds_on_next"]
                for row in plan_rows for a in ("4/5", "9/10")),
        "ceiling_null_supremum_at_one_half":
            all(binomial_lower_tail(40, p, 20) <= ceiling_p_value(40, 20) for p in (HALF, Q(3, 5), Q(7, 10), Q(9, 10), Q(1))),
        "gold_noise_inverts_and_keeps_agreement":
            all(row["inverts"] and row["agreement_invariant"] for row in gold["judges"].values()),
        "gold_noise_makes_an_independent_judge_look_shared":
            gold["independent_judge_measured_excess"] == Q(57, 575) > 0
            and gold["judges"]["independent"]["measured"]["eps1"] == Q(11, 46),
        "ceiling_reachable_in_fixture":
            ceiling_reachable_without_memorization(FIXTURE_ACCURACY, FIXTURE_ERROR),
        "sealed_sample_read_once_is_evaluable_and_breach_withholds":
            ledgers["respected"]["readout"]["judge_sample"]["endpoint_status"] == "evaluable"
            and ledgers["breached"]["readout"]["judge_sample"]["endpoint_status"] == "not_evaluated"
            and len(ledgers["breached"]["readout"]["judge_sample"]["breaches"]) == 2,
        "card_item_valid_only_with_respected_ledger":
            all(item["measurement_valid"] for item in cards["items"].values())
            and not cards["withheld_after_breach"]["measurement_valid"],
    }
    return {"evidence_status": "exact_synthetic_fixtures_not_model_or_agent_evidence",
            "checks": checks, "all_passed": all(checks.values()),
            "fixture": {"size": FIXTURE_SIZE, "accuracy": FIXTURE_ACCURACY, "judge_error": FIXTURE_ERROR},
            "judges": judges, "planning": planning, "gold_noise": gold, "ledger": ledgers, "card": cards}
