"""Estimating the gold grader's error rate with a second independent grader, exactly.

The judge-measurement note inverts gold noise at a known flip rate ``eta`` and
stops there: ``eta`` must be known.  This module estimates it.  Three raters of
a binary truth with symmetric error rates, conditionally independent given the
truth -- the gold grader G1 (error ``eta1``), a second grader G2 (``eta2``) and
the controller's own answer C (error ``1 - a``) -- have pairwise agreement
rates whose polarities ``kappa_ij = 2 A_ij - 1`` factor as
``(1 - 2 e_i)(1 - 2 e_j)``, so ``(1 - 2 e_i)^2 = kappa_ij kappa_ik / kappa_jk``.
The judge is left out: its errors are correlated with the controller's (that
is what ``eps1`` measures), so it is a conditionally independent rater only if
A2 already holds.

1. Walsh coefficients of the 2^3 label table; the factorization of the pairwise
   polarities; exact recovery when the square is a perfect square, an exact
   membership test ``eta1 <= eta0`` otherwise, and a 2^-16 bracket by bisection.
2. The symmetric model has four parameters on seven degrees of freedom.  The
   three polynomial constraints ``M_i kappa_jk = P`` (a rater's marginal bias
   times the opposite pair's polarity equals the parity bias), the sign and
   range conditions, and tables that violate each.
3. A pipeline from a 2^4 record table (controller answer, judge verdict, two
   gold labels): ``eta1`` from the three-rater identity, the judge note's
   Proposition 2 inverted at that ``eta1``, the judge module's exact tests on
   the corrected counts, and the exact propagation of an error in ``eta1``
   into ``eps1``.
4. The sampling law of ``eta1_hat`` on ``m`` items: the three agreement counts
   are a function of a four-category multinomial (two agreements force the
   third), so their exact joint law is enumerated in ``C(m+3, 3)`` integer
   terms, cross-checked against the ``C(m+7, 7)`` label tables; the exact
   probability that the estimator is undefined, the exact moments of the
   implied square, brackets on the moments of ``eta1_hat`` itself, the delta
   variance as a rational function of the parameters with the (non-diagonal)
   covariance of the agreement indicators, a planning size, and an exact
   conservative confidence bound from the two graders' disagreement alone.
5. The asymmetric (two-class Dawid-Skene) model: a prior and a false-negative
   and false-positive rate per rater, seven parameters on seven degrees of
   freedom.  The closed-form moment solution in one square root, the label
   switching convention, the symmetric model as the special case, the absence
   of any equality constraint, and the asymmetric inversion of the judge
   note's gold-noise map given the gold grader's two rates.
6. Four raters make the asymmetric model testable: nine parameters on fifteen
   degrees of freedom, six exact polynomial constraints in the centred moments
   (two tetrads, three third-moment ratios, one fourth-moment relation), the
   rank counts that make them exactly six, the four-triple solver, and the
   copying grader's closed-form tetrad residual, which the three-rater fit
   absorbed and the fourth rater exposes.
7. A joint statement for ``(eta_1, eps_1)``: a confidence set for ``eta_1``
   on a rational grid (the disagreement bound intersected with the inverted
   two-sided test of the observed square under a plug-in; the tails are exact
   in ``O(m^2)`` big-integer products, and decided at large ``m`` by rigorous
   fixed-point integer brackets with the exact law as fallback), the
   inversion and the exact judge tests at every retained ``eta_0``, and the
   Bonferroni union at level ``1 - 2 alpha``.

Nothing here calls a model.  Every quantity is a ``fractions.Fraction``; floats
are rejected at the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as Q
from itertools import product
from math import comb, factorial, gcd, isqrt

from spiral_ln.evaluation_feedback_signal import shared_error_bounds
from spiral_ln.evaluation_game_feedback import LoopEvent
from spiral_ln.evaluation_judge_measurement import (
    HALF, JudgeTable, ceiling_p_value, clopper_pearson_bracket, clopper_pearson_contains,
    expected_table, fisher_p_value, gold_noise_forward, gold_noise_inverse, independence_p_value,
    measurement_ledger, rounded_table, table_estimates,
)

RATERS = {1: "G1", 2: "G2", 3: "C"}
PAIRS = ((1, 2), (1, 3), (2, 3))
SUBSETS = ((1,), (2,), (3,)) + PAIRS + ((1, 2, 3),)
CELLS3 = tuple(product((0, 1), repeat=3))
CELLS4 = tuple(product((0, 1), repeat=4))
RESOLUTION = Q(1, 2 ** 16)
DEGREES_OF_FREEDOM = {"cells": 8, "free_cell_probabilities": 7, "symmetric_parameters": 4,
                      "constraints": 3, "asymmetric_dawid_skene_parameters": 7,
                      "four_rater_cells": 16, "four_rater_free_cell_probabilities": 15,
                      "four_rater_parameters": 9, "four_rater_constraints": 6}


def _as_q(value, name: str) -> Q:
    if isinstance(value, bool) or not isinstance(value, (int, Q)):
        raise ValueError(f"{name} must be an int or Fraction, not {type(value).__name__}")
    return Q(value)


def _probability(value, name: str) -> Q:
    value = _as_q(value, name)
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must lie in [0, 1]")
    return value


def _pair(i: int, j: int) -> tuple[int, int]:
    return (i, j) if i < j else (j, i)


def _others(i: int) -> tuple[int, int]:
    return tuple(k for k in (1, 2, 3) if k != i)


def _weights(cells, keys, what: str) -> dict:
    if not isinstance(cells, dict) or not set(cells) <= set(keys):
        raise ValueError(f"cells must map {what} to weights")
    table = {}
    for key in keys:
        value = _as_q(cells.get(key, 0), f"cell {key}")
        if value < 0:
            raise ValueError("cell weights must be nonnegative")
        table[key] = value
    if sum(table.values()) <= 0:
        raise ValueError("the table needs positive total weight")
    return table


# --- 1. three raters: the label table and its Walsh coefficients --------------

@dataclass(frozen=True)
class LabelTable:
    """Rational weights on the 2^3 cells ``(x_1, x_2, x_3)`` of three binary
    raters' labels: counts or probabilities, nonnegative, positive total.
    Rater 1 is the gold grader G1, rater 2 the second grader G2, rater 3 the
    controller's answer."""

    cells: dict

    def __post_init__(self) -> None:
        object.__setattr__(self, "cells", _weights(self.cells, CELLS3, "(x_1, x_2, x_3) in {0,1}^3"))

    @property
    def total(self) -> Q:
        return sum(self.cells.values(), Q(0))

    def probability(self, cell: tuple[int, int, int]) -> Q:
        return self.cells[cell] / self.total


def walsh_coefficients(table: LabelTable) -> dict[tuple[int, ...], Q]:
    """``p_S = sum_x p(x) prod_{i in S} (-1)^{x_i}`` for every nonempty ``S``.
    ``p_{i}`` is rater ``i``'s marginal bias ``P[X_i = 0] - P[X_i = 1]``,
    ``p_{ij}`` the pair's polarity ``2 A_ij - 1`` and ``p_{123}`` the parity
    bias ``P[even parity] - P[odd parity]``."""

    out = {}
    for subset in SUBSETS:
        out[subset] = sum((table.cells[cell] * (-1) ** sum(cell[i - 1] for i in subset)
                           for cell in CELLS3), Q(0)) / table.total
    return out


def agreement_rate(table: LabelTable, i: int, j: int) -> Q:
    """``A_ij = P[X_i = X_j]``, directly from the cells."""

    if i == j or {i, j} - {1, 2, 3}:
        raise ValueError("i and j must be two distinct raters among 1, 2, 3")
    return sum((table.cells[cell] for cell in CELLS3 if cell[i - 1] == cell[j - 1]), Q(0)) / table.total


def pairwise_kappas(table: LabelTable) -> dict[tuple[int, int], Q]:
    """``kappa_ij = 2 A_ij - 1`` for the three pairs."""

    return {pair: 2 * agreement_rate(table, *pair) - 1 for pair in PAIRS}


def three_rater_model(prior, errors) -> LabelTable:
    """Cell probabilities when ``Y ~ Bernoulli(prior)`` and rater ``i`` reports
    ``Y`` flipped independently with probability ``errors[i]``.

    In Walsh coordinates, with ``tau = 1 - 2 prior`` and ``d_i = 1 - 2 e_i``:
    ``p_S = tau^[|S| odd] prod_{i in S} d_i``.  Proof: ``E[(-1)^{X_i} | Y] =
    (-1)^Y d_i``, the raters are independent given ``Y``, and ``E[(-1)^{kY}]``
    is ``tau`` for odd ``k`` and ``1`` for even ``k``."""

    prior = _probability(prior, "prior")
    if not isinstance(errors, (tuple, list)) or len(errors) != 3:
        raise ValueError("errors must list three rates")
    errors = tuple(_probability(e, f"error of rater {i + 1}") for i, e in enumerate(errors))
    cells = {}
    for cell in CELLS3:
        weight = Q(0)
        for y in (0, 1):
            w = prior if y else 1 - prior
            for i in range(3):
                w *= (1 - errors[i]) if cell[i] == y else errors[i]
            weight += w
        cells[cell] = weight
    return LabelTable(cells)


# --- identification from the pairwise polarities -----------------------------

def polarity_squares(kappas: dict[tuple[int, int], Q]) -> dict[int, Q]:
    """``(1 - 2 e_i)^2 = kappa_ij kappa_ik / kappa_jk``.

    Proof: ``kappa_ij = d_i d_j`` for conditionally independent symmetric
    raters, so the ratio is ``d_i d_j d_i d_k / (d_j d_k) = d_i^2``.  A rater
    at chance has ``d = 0``, both of its polarities vanish, and the other two
    raters are left unidentified (one equation, two unknowns)."""

    values = {pair: _as_q(kappas[pair], f"kappa {pair}") for pair in PAIRS}
    if any(k == 0 for k in values.values()):
        raise ValueError("a rater at chance (kappa = 0) leaves the others unidentified")
    return {i: values[_pair(i, j)] * values[_pair(i, k)] / values[_pair(j, k)]
            for i in (1, 2, 3) for j, k in (_others(i),)}


def exact_square_root(value) -> Q | None:
    """The rational square root of ``value`` if it has one, else ``None``.  A
    fraction in lowest terms is a rational square iff numerator and
    denominator are both perfect squares."""

    value = _as_q(value, "value")
    if value < 0:
        return None
    n, d = isqrt(value.numerator), isqrt(value.denominator)
    return Q(n, d) if n * n == value.numerator and d * d == value.denominator else None


def _square_in_range(square) -> Q:
    square = _as_q(square, "square")
    if not 0 <= square <= 1:
        raise ValueError("no error rate in [0, 1/2] has this squared polarity")
    return square


def error_rate_from_square(square) -> Q | None:
    """``e = (1 - sqrt(square)) / 2`` exactly when the square is a perfect
    square (always the case at expected counts with rational rates); ``None``
    otherwise.  The sign is fixed by ``e < 1/2``."""

    root = exact_square_root(_square_in_range(square))
    return None if root is None else (1 - root) / 2


def error_rate_at_most(square, bound) -> bool:
    """Exact membership ``e <= bound`` for rational ``bound`` without taking the
    root: ``e <= bound`` iff ``d >= 1 - 2 bound`` iff (for ``1 - 2 bound > 0``)
    ``square >= (1 - 2 bound)^2``; trivially true when ``bound >= 1/2``."""

    square, bound = _square_in_range(square), _probability(bound, "bound")
    floor = 1 - 2 * bound
    return True if floor <= 0 else square >= floor * floor


def error_rate_bracket(square, resolution=RESOLUTION) -> dict[str, object]:
    """Rational bracket of width at most ``resolution`` around ``e``, by
    bisection on the exact membership test; exact when the square is perfect.
    The true ``e`` lies in ``(lower, upper]``."""

    square, resolution = _square_in_range(square), _as_q(resolution, "resolution")
    if resolution <= 0:
        raise ValueError("resolution must be positive")
    exact = error_rate_from_square(square)
    if exact is not None:
        return {"lower": exact, "upper": exact, "exact": exact, "width": Q(0), "resolution": resolution}
    low, high = Q(0), HALF
    while high - low > resolution:
        mid = (low + high) / 2
        if error_rate_at_most(square, mid):
            high = mid
        else:
            low = mid
    return {"lower": low, "upper": high, "exact": None, "width": high - low, "resolution": resolution}


def eta_gradient(kappas: dict[tuple[int, int], Q], rater: int = 1) -> dict[str, object] | None:
    """Partial derivatives of ``e_i = (1 - sqrt(kappa_ij kappa_ik / kappa_jk)) / 2``:
    ``-d_i / (4 kappa_ij)``, ``-d_i / (4 kappa_ik)``, ``+d_i / (4 kappa_jk)``;
    exact only when ``d_i`` is rational, else ``None``.  Per agreement rate the
    values double, since ``kappa = 2 A - 1``."""

    if rater not in (1, 2, 3):
        raise ValueError("rater must be 1, 2 or 3")
    root = exact_square_root(polarity_squares(kappas)[rater])
    if root is None:
        return None
    j, k = _others(rater)
    per_kappa = {_pair(rater, j): -root / (4 * kappas[_pair(rater, j)]),
                 _pair(rater, k): -root / (4 * kappas[_pair(rater, k)]),
                 _pair(j, k): root / (4 * kappas[_pair(j, k)])}
    return {"polarity": root, "per_kappa": per_kappa,
            "per_agreement_rate": {pair: 2 * g for pair, g in per_kappa.items()}}


# --- 2. the model's testable constraints -------------------------------------

def model_constraints(table: LabelTable) -> dict[str, object]:
    """Residuals of the three equalities ``M_i kappa_jk - P`` (each is
    ``tau d_i d_j d_k - tau d_1 d_2 d_3 = 0`` under the model), the sign
    condition (``kappa_ij = d_i d_j`` has zero or two negative pairs, never one
    or three), the range conditions (``d_i^2 <= 1`` and ``tau^2 = M_i^2 / d_i^2
    <= 1``) and identifiability (every ``kappa > 0`` under ``e_i < 1/2``).

    At ``tau = 0`` (balanced prior) every odd coefficient vanishes and the
    equalities read ``0 = 0``: they then have no power against dependence."""

    coefficients = walsh_coefficients(table)
    kappas = {pair: coefficients[pair] for pair in PAIRS}
    biases = {i: coefficients[(i,)] for i in (1, 2, 3)}
    parity = coefficients[(1, 2, 3)]
    residuals = {i: biases[i] * kappas[_others(i)] - parity for i in (1, 2, 3)}
    negatives = sum(1 for k in kappas.values() if k < 0)
    chance = any(k == 0 for k in kappas.values())
    squares = None if chance else polarity_squares(kappas)
    squares_ok = None if chance else all(0 <= s <= 1 for s in squares.values())
    prior_ok = None if chance else all(biases[i] ** 2 <= squares[i] for i in (1, 2, 3))
    equalities = all(r == 0 for r in residuals.values())
    signs = negatives in (0, 2)
    consistent = equalities and signs and squares_ok is not False and prior_ok is not False
    identifiable = negatives == 0 and not chance
    return {"kappas": kappas, "biases": biases, "parity": parity, "residuals": residuals,
            "equalities_hold": equalities, "negative_kappas": negatives, "signs_consistent": signs,
            "chance_rater": chance, "squares": squares, "squares_in_unit_interval": squares_ok,
            "prior_in_range": prior_ok, "model_consistent": consistent,
            "identifiable": identifiable, "passes": consistent and identifiable,
            "vacuous_at_balanced_prior": all(b == 0 for b in biases.values()) and parity == 0}


def _rank(rows: list[list[Q]]) -> int:
    matrix = [list(row) for row in rows]
    rank = 0
    for col in range(len(matrix[0]) if matrix else 0):
        pivot = next((r for r in range(rank, len(matrix)) if matrix[r][col] != 0), None)
        if pivot is None:
            continue
        matrix[rank], matrix[pivot] = matrix[pivot], matrix[rank]
        for r in range(len(matrix)):
            if r != rank and matrix[r][col] != 0:
                factor = matrix[r][col] / matrix[rank][col]
                matrix[r] = [x - factor * y for x, y in zip(matrix[r], matrix[rank])]
        rank += 1
    return rank


def model_jacobian_rank(prior, errors) -> int:
    """Rank of the exact Jacobian of ``(tau, d_1, d_2, d_3) -> (p_S)_S`` at the
    point: four wherever every ``d_i != 0`` (the three pair rows alone have
    determinant ``-2 d_1 d_2 d_3`` on the ``d`` columns), so the model is
    four-dimensional inside the seven-dimensional simplex and leaves exactly
    three constraints.  With a chance rater the rank drops at a balanced prior
    (``tau = 0``) but not at an unbalanced one, where the marginal bias
    ``tau d_i`` still moves."""

    tau = 1 - 2 * _probability(prior, "prior")
    if not isinstance(errors, (tuple, list)) or len(errors) != 3:
        raise ValueError("errors must list three rates")
    d1, d2, d3 = (1 - 2 * _probability(e, "error") for e in errors)
    zero = Q(0)
    rows = [[d1, tau, zero, zero], [d2, zero, tau, zero], [d3, zero, zero, tau],
            [zero, d2, d1, zero], [zero, d3, zero, d1], [zero, zero, d3, d2],
            [d1 * d2 * d3, tau * d2 * d3, tau * d1 * d3, tau * d1 * d2]]
    return _rank(rows)


def copy_grader_table(prior, eta1, eta2, controller_error, copy_rate) -> LabelTable:
    """Labels when G2 copies G1 with probability ``copy_rate`` and otherwise
    grades independently at ``eta2``: conditional independence fails.  Closed
    form of the residuals: ``r_1 = r_2 = -tau d_C rho 4 eta1 (1 - eta1)``,
    ``r_3 = 0``; the failing constraints name the dependent pair."""

    prior, rho = _probability(prior, "prior"), _probability(copy_rate, "copy_rate")
    eta1, eta2, ec = (_probability(eta1, "eta1"), _probability(eta2, "eta2"),
                      _probability(controller_error, "controller_error"))
    cells = {}
    for cell in CELLS3:
        g1, g2, c = cell
        weight = Q(0)
        for y in (0, 1):
            w = prior if y else 1 - prior
            w *= (1 - eta1) if g1 == y else eta1
            w *= rho * (1 if g2 == g1 else 0) + (1 - rho) * ((1 - eta2) if g2 == y else eta2)
            w *= (1 - ec) if c == y else ec
            weight += w
        cells[cell] = weight
    return LabelTable(cells)


def copy_grader_residual(prior, eta1, controller_error, copy_rate) -> Q:
    """``-tau d_C rho 4 eta1 (1 - eta1)``, the residual of constraints 1 and 2."""

    tau = 1 - 2 * _probability(prior, "prior")
    d_c = 1 - 2 * _probability(controller_error, "controller_error")
    eta1, rho = _probability(eta1, "eta1"), _probability(copy_rate, "copy_rate")
    return -tau * d_c * rho * 4 * eta1 * (1 - eta1)


# --- 3. the record table and the pipeline ------------------------------------

@dataclass(frozen=True)
class RecordTable:
    """Rational weights on the 2^4 cells ``(x_C, v_J, g_1, g_2)``: the
    controller's answer, the judge's verdict (``1`` = "correct"), the gold
    label and the second grader's label.  Counts on a sealed sample, or
    expected counts."""

    cells: dict

    def __post_init__(self) -> None:
        object.__setattr__(self, "cells", _weights(self.cells, CELLS4, "(x_C, v_J, g_1, g_2) in {0,1}^4"))

    @property
    def total(self) -> Q:
        return sum(self.cells.values(), Q(0))

    def label_table(self) -> LabelTable:
        """Marginal over the judge: ``(g_1, g_2, x_C)`` as raters 1, 2, 3."""

        cells = {cell: Q(0) for cell in CELLS3}
        for (x, _v, g1, g2), weight in self.cells.items():
            cells[(g1, g2, x)] += weight
        return LabelTable(cells)

    def judge_cells(self, gold: int = 1) -> dict[str, Q]:
        """The judge note's 2x2 table measured against grader ``gold``:
        controller right iff ``x_C`` equals that label, judge right iff its
        verdict equals that measured correctness."""

        if gold not in (1, 2):
            raise ValueError("gold must be 1 or 2")
        names = {(1, 1): "right_right", (1, 0): "right_wrong", (0, 1): "wrong_right", (0, 0): "wrong_wrong"}
        out = {name: Q(0) for name in names.values()}
        for (x, v, g1, g2), weight in self.cells.items():
            c = int(x == (g1 if gold == 1 else g2))
            out[names[(c, int(v == c))]] += weight
        return out


def expected_record_table(size: int, prior, accuracy, judge_error, eps1, eta1, eta2,
                          copy_rate=Q(0)) -> RecordTable:
    """Expected counts for ``size`` items: ``Y ~ Bernoulli(prior)``; the
    controller answers ``Y`` with probability ``a``; the judge says "correct"
    with probability ``1 - eps0`` on a right answer and ``eps1`` on a wrong
    one; G1 flips ``Y`` at ``eta1``; G2 copies G1 with probability
    ``copy_rate`` (zero for an independent grader) and otherwise flips at
    ``eta2``."""

    if type(size) is not int or size < 1:
        raise ValueError("size must be a positive integer")
    prior, accuracy = _probability(prior, "prior"), _probability(accuracy, "accuracy")
    judge_error, eps1 = _probability(judge_error, "judge_error"), _probability(eps1, "eps1")
    eta1, eta2, rho = (_probability(eta1, "eta1"), _probability(eta2, "eta2"),
                       _probability(copy_rate, "copy_rate"))
    low, high = shared_error_bounds(accuracy, judge_error)
    if not low <= eps1 <= high:
        raise ValueError("eps1 is infeasible for the marginal judge error")
    eps0 = (judge_error - (1 - accuracy) * eps1) / accuracy
    cells = {}
    for cell in CELLS4:
        x, v, g1, g2 = cell
        weight = Q(0)
        for y in (0, 1):
            w = prior if y else 1 - prior
            right = x == y
            w *= accuracy if right else 1 - accuracy
            says_correct = (1 - eps0) if right else eps1
            w *= says_correct if v == 1 else 1 - says_correct
            w *= (1 - eta1) if g1 == y else eta1
            w *= rho * (1 if g2 == g1 else 0) + (1 - rho) * ((1 - eta2) if g2 == y else eta2)
            weight += w
        cells[cell] = size * weight
    return RecordTable(cells)


def measured_judge_rates(record: RecordTable, gold: int = 1) -> dict[str, object]:
    """``a'``, ``eps'``, ``w = W1'/m`` and ``eps1'`` of the table measured
    against grader ``gold``, plus the half-up rounded ``JudgeTable`` when the
    total is an integer count (``None`` for a probability table)."""

    cells = record.judge_cells(gold)
    m = record.total
    measured_accuracy = (cells["right_right"] + cells["right_wrong"]) / m
    measured_error = (cells["right_wrong"] + cells["wrong_wrong"]) / m
    wrong_wrong_rate = cells["wrong_wrong"] / m
    table, changed = None, None
    if m.denominator == 1:
        try:
            table, changed = rounded_table(cells)
        except ValueError:  # every cell rounds to zero: no table to test
            pass
    return {"cells": cells, "accuracy": measured_accuracy, "judge_error": measured_error,
            "wrong_wrong_rate": wrong_wrong_rate,
            "eps1": None if measured_accuracy == 1 else wrong_wrong_rate / (1 - measured_accuracy),
            "table": table, "rounding_changed_a_cell": changed}


def inverted_eps1(measured_accuracy, measured_error, wrong_wrong_rate, eta) -> Q:
    """Proposition 2 inverted as one rational function of ``eta``:
    ``eps1(eta) = (w (1 - 2 eta) - eta (a' - eps')) / (1 - a' - eta)``.
    Proof: substitute ``a - eps = (a' - eps') / (1 - 2 eta)`` and
    ``1 - a = (1 - a' - eta) / (1 - 2 eta)`` into the note's
    ``eps1 = (eps1' (1 - a') - eta (a - eps)) / (1 - a)`` with
    ``eps1' (1 - a') = w``."""

    a, e, w = (_probability(measured_accuracy, "measured_accuracy"),
               _probability(measured_error, "measured_error"),
               _probability(wrong_wrong_rate, "wrong_wrong_rate"))
    eta = _probability(eta, "eta")
    if not eta < HALF or not 1 - a - eta > 0:
        raise ValueError("eta must lie below one half and below 1 - a'")
    return (w * (1 - 2 * eta) - eta * (a - e)) / (1 - a - eta)


def _sensitivity_numerator(a: Q, e: Q, w: Q) -> Q:
    return w * (2 * a - 1) - (a - e) * (1 - a)


def eps1_sensitivity(measured_accuracy, measured_error, wrong_wrong_rate, eta) -> Q:
    """``d eps1 / d eta = K / (1 - a' - eta)^2`` with the ``eta``-free
    ``K = w (2a' - 1) - (a' - eps')(1 - a')``.  Proof: ``eps1 = N / D`` with
    ``N = w - eta (2w + a' - eps')`` and ``D = 1 - a' - eta`` both affine, so
    ``N' D - N D' = -(2w + a' - eps') D + N = K``."""

    a, e, w = (_probability(measured_accuracy, "measured_accuracy"),
               _probability(measured_error, "measured_error"),
               _probability(wrong_wrong_rate, "wrong_wrong_rate"))
    eta = _probability(eta, "eta")
    if not eta < HALF or not 1 - a - eta > 0:
        raise ValueError("eta must lie below one half and below 1 - a'")
    return _sensitivity_numerator(a, e, w) / (1 - a - eta) ** 2


def eps1_displacement(measured_accuracy, measured_error, wrong_wrong_rate, eta, delta) -> Q:
    """Exact ``eps1(eta + delta) - eps1(eta) = delta K / (D(eta) D(eta + delta))``:
    the derivative's denominator with one factor moved to the displaced point."""

    a, e, w = (_probability(measured_accuracy, "measured_accuracy"),
               _probability(measured_error, "measured_error"),
               _probability(wrong_wrong_rate, "wrong_wrong_rate"))
    eta, delta = _probability(eta, "eta"), _as_q(delta, "delta")
    moved = eta + delta
    if not 0 <= moved < HALF or not eta < HALF or not 1 - a - eta > 0 or not 1 - a - moved > 0:
        raise ValueError("eta and eta + delta must lie in [0, 1/2) and below 1 - a'")
    return delta * _sensitivity_numerator(a, e, w) / ((1 - a - eta) * (1 - a - moved))


def _judge_tests(table: JudgeTable, error, alpha, plug_in: bool) -> dict[str, object]:
    wrong, wrong_wrong = table.controller_wrong, table.wrong_wrong
    if wrong < 1:
        return {"note": "no controller-wrong items; the conditional tests are undefined"}
    return {"independence_p": independence_p_value(wrong, wrong_wrong, error),
            "independence_error": error, "independence_error_is_plug_in": plug_in,
            "fisher_p": fisher_p_value(table), "ceiling_p": ceiling_p_value(wrong, wrong_wrong),
            "cp_contains_error": clopper_pearson_contains(wrong, wrong_wrong, alpha, error),
            "cp_contains_half": clopper_pearson_contains(wrong, wrong_wrong, alpha, HALF),
            "alpha": alpha}


def calibrate(record: RecordTable, declared_judge_error=None, alpha=Q(1, 20),
              resolution=RESOLUTION) -> dict[str, object]:
    """The pipeline.  From the 2^4 record: the label table's constraint check;
    ``eta1``, ``eta2`` and ``a`` from the three-rater identity (exact or
    bracketed); Proposition 2 inverted at ``eta1`` (at both bracket ends when
    bracketed -- every inverted rate is monotone in ``eta``, so the ends map
    to ends); the corrected expected counts rounded half-up; the judge
    module's exact tests on them; the sensitivity of ``eps1`` to ``eta1``.

    The tests take the corrected counts as given.  They are an estimate, not a
    sample, so the sampling error of ``eta1`` is not in their p-values; the
    sensitivity is the first-order account of it."""

    alpha = _probability(alpha, "alpha")
    declared = None if declared_judge_error is None else _probability(declared_judge_error, "declared_judge_error")
    labels = record.label_table()
    constraints = model_constraints(labels)
    measured = measured_judge_rates(record, 1)
    out = {"size": record.total, "constraints": constraints, "identifiable": constraints["identifiable"],
           "measured": measured, "declared_judge_error": declared}
    if not constraints["identifiable"]:
        out.update({"status": "not_identified", "eta1": None, "eta2": None, "accuracy_from_identity": None,
                    "inversions": [], "valid": False})
        return out
    squares = constraints["squares"]
    brackets = {i: error_rate_bracket(squares[i], resolution) for i in (1, 2, 3)}
    accuracy_identity = {"lower": 1 - brackets[3]["upper"], "upper": 1 - brackets[3]["lower"],
                         "exact": None if brackets[3]["exact"] is None else 1 - brackets[3]["exact"]}
    eta1 = brackets[1]
    points = [eta1["exact"]] if eta1["exact"] is not None else [eta1["lower"], eta1["upper"]]
    if record.total.denominator != 1:
        raise ValueError("corrected counts need an integer total")
    size = int(record.total)
    inversions = []
    for eta in points:
        rates = gold_noise_inverse(measured["accuracy"], measured["judge_error"], measured["eps1"], eta)
        closed = inverted_eps1(measured["accuracy"], measured["judge_error"], measured["wrong_wrong_rate"], eta)
        if closed != rates["eps1"]:
            raise AssertionError("closed-form inversion disagrees with the judge module")
        expected = expected_table(size, rates["accuracy"], rates["judge_error"], rates["eps1"])
        table, changed = rounded_table(expected)
        error = declared if declared is not None else rates["judge_error"]
        inversions.append({"eta": eta, "recovered": rates, "corrected_expected": expected,
                           "corrected_table": table, "rounding_changed_a_cell": changed,
                           "tests": _judge_tests(table, error, alpha, declared is None),
                           "sensitivity_d_eps1_d_eta": eps1_sensitivity(
                               measured["accuracy"], measured["judge_error"], measured["wrong_wrong_rate"], eta)})
    recovered_accuracies = [inv["recovered"]["accuracy"] for inv in inversions]
    if accuracy_identity["exact"] is not None:
        consistent = all(a == accuracy_identity["exact"] for a in recovered_accuracies)
    else:
        consistent = (min(recovered_accuracies) <= accuracy_identity["upper"]
                      and max(recovered_accuracies) >= accuracy_identity["lower"])
    gradient = eta_gradient(constraints["kappas"], 1)
    chain = None
    if gradient is not None and len(inversions) == 1:
        sens = inversions[0]["sensitivity_d_eps1_d_eta"]
        chain = {"d_eps1_d_kappa": {pair: sens * g for pair, g in gradient["per_kappa"].items()},
                 "d_eps1_d_agreement": {pair: sens * g for pair, g in gradient["per_agreement_rate"].items()}}
    out.update({"status": "exact" if len(points) == 1 else "bracketed",
                "squares": squares, "eta1": eta1, "eta2": brackets[2],
                "accuracy_from_identity": accuracy_identity, "accuracy_consistent": consistent,
                "inversions": inversions, "eta_gradient": gradient, "chain_sensitivity": chain,
                "valid": constraints["passes"]})
    return out


def calibration_valid(result: dict[str, object], ledger: dict[str, object]) -> bool:
    """Identifiable, constraints passed, and the sealed sample read once."""

    status = ledger["readout"]["judge_sample"]["endpoint_status"]
    return bool(result["identifiable"]) and bool(result["constraints"]["passes"]) and status == "evaluable"


# --- 4. the sampling law of eta1_hat ------------------------------------------

PATTERNS = ("all", (1, 2), (1, 3), (2, 3))
ROOT_BITS = 16


def _three(values, name: str) -> tuple[Q, Q, Q]:
    if not isinstance(values, (tuple, list)) or len(values) != 3:
        raise ValueError(f"{name} must list three rates")
    return tuple(_probability(v, f"{name}[{i}]") for i, v in enumerate(values))


def _size(value) -> int:
    if type(value) is not int or value < 1:
        raise ValueError("size must be a positive integer")
    return value


def _rate_pair(value, name: str) -> tuple[Q, Q]:
    """A rater's ``(false_negative, false_positive)`` pair of probabilities."""

    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError(f"{name} must be a pair (false_negative, false_positive)")
    return _probability(value[0], f"{name} false_negative"), _probability(value[1], f"{name} false_positive")


def root_bracket(value, bits: int = ROOT_BITS) -> dict[str, object]:
    """``sqrt(value)`` exactly when rational, else the bracket
    ``[r / 2^bits, (r + 1) / 2^bits)`` with ``r = isqrt(floor(value 4^bits))``:
    an exact integer statement, since ``floor(sqrt(floor(x))) = floor(sqrt(x))``
    for ``x >= 0``.  Agrees with the bisection bracket of ``error_rate_bracket``."""

    value = _as_q(value, "value")
    if value < 0 or type(bits) is not int or bits < 1:
        raise ValueError("value must be nonnegative and bits a positive integer")
    exact = exact_square_root(value)
    if exact is not None:
        return {"lower": exact, "upper": exact, "exact": exact, "width": Q(0)}
    r = isqrt((value.numerator << (2 * bits)) // value.denominator)
    return {"lower": Q(r, 1 << bits), "upper": Q(r + 1, 1 << bits), "exact": None, "width": Q(1, 1 << bits)}


def agreement_patterns(table: LabelTable) -> dict[object, Q]:
    """Per item the agreement indicators ``(I_12, I_13, I_23)`` take one of
    four values, ``(1,1,1)`` (``"all"``), ``(1,0,0)``, ``(0,1,0)``, ``(0,0,1)``:
    two agreements force the third.  ``q_all = p(000) + p(111) = (1 + kappa_12
    + kappa_13 + kappa_23) / 4`` and ``q_ij = A_ij - q_all`` depend on the table
    only through the kappas, so under the model the law of any function of the
    agreement counts is free of the prior."""

    q = {name: Q(0) for name in PATTERNS}
    for cell in CELLS3:
        a, b, c = cell
        key = "all" if a == b == c else (1, 2) if a == b else (1, 3) if a == c else (2, 3)
        q[key] += table.probability(cell)
    return q


def agreement_covariance(table: LabelTable) -> dict[tuple, Q]:
    """Per-item covariance of ``(I_12, I_13, I_23)``: ``Var I_ij = (1 -
    kappa_ij^2) / 4`` and ``Cov(I_ij, I_ik) = q_all - A_ij A_ik = (kappa_jk -
    kappa_ij kappa_ik) / 4`` for any distribution; the sample agreement rates
    on ``m`` items have covariance ``Sigma / m``.  Not diagonal."""

    kappas = pairwise_kappas(table)
    q_all = agreement_patterns(table)["all"]
    return {(p, r): (1 - kappas[p] ** 2) / 4 if p == r else q_all - (1 + kappas[p]) * (1 + kappas[r]) / 4
            for p in PAIRS for r in PAIRS}


def agreement_covariance_model(errors) -> dict[tuple, Q]:
    """The same matrix under the model: ``Cov(I_ij, I_ik) = d_j d_k (1 - d_i^2) / 4``
    (``kappa_jk - kappa_ij kappa_ik = d_j d_k - d_i^2 d_j d_k``) and
    ``Var I_ij = (1 - d_i^2 d_j^2) / 4``."""

    d = {i + 1: 1 - 2 * e for i, e in enumerate(_three(errors, "errors"))}
    out = {}
    for p in PAIRS:
        for r in PAIRS:
            if p == r:
                out[(p, r)] = (1 - (d[p[0]] * d[p[1]]) ** 2) / 4
            else:
                (i,) = set(p) & set(r)
                j, k = _others(i)
                out[(p, r)] = d[j] * d[k] * (1 - d[i] ** 2) / 4
    return out


def delta_variance(errors) -> dict[str, object]:
    """Asymptotic ``m Var(eta1_hat) -> V = g^T Sigma g`` with the gradient per
    agreement rate ``g = (-1/(2 d_2), -1/(2 d_3), d_1/(2 d_2 d_3))`` (twice the
    per-kappa gradient of ``eta_gradient``) and ``Sigma`` the model covariance:

    ``V = (d_1^2 + d_2^2 + d_3^2 - 2 d_1^2 d_2^2 - 2 d_1^2 d_3^2 + 2 d_2^2 d_3^2
    - d_1^2 d_2^2 d_3^2) / (16 d_2^2 d_3^2)``.

    The square ``S = (1 - 2 eta_1)^2 = kappa_12 kappa_13 / kappa_23`` has
    gradient ``-4 d_1 g``, so ``m Var(S_hat) -> 16 d_1^2 V``.  Every rater
    must be better than chance: at ``d_1 = 0`` the root is not differentiable
    and the estimator is undefined with probability bounded away from zero."""

    errors = _three(errors, "errors")
    d1, d2, d3 = (1 - 2 * e for e in errors)
    if not (d1 > 0 and d2 > 0 and d3 > 0):
        raise ValueError("the delta method needs every error rate below one half")
    gradient = {(1, 2): -1 / (2 * d2), (1, 3): -1 / (2 * d3), (2, 3): d1 / (2 * d2 * d3)}
    sigma = agreement_covariance_model(errors)
    quadratic = sum((gradient[p] * sigma[(p, r)] * gradient[r] for p in PAIRS for r in PAIRS), Q(0))
    numerator = (d1 ** 2 + d2 ** 2 + d3 ** 2 - 2 * d1 ** 2 * d2 ** 2 - 2 * d1 ** 2 * d3 ** 2
                 + 2 * d2 ** 2 * d3 ** 2 - d1 ** 2 * d2 ** 2 * d3 ** 2)
    closed = numerator / (16 * d2 ** 2 * d3 ** 2)
    if closed != quadratic:
        raise AssertionError("closed form of the delta variance disagrees with g^T Sigma g")
    return {"eta": closed, "square": 16 * d1 ** 2 * closed, "gradient_per_agreement_rate": gradient,
            "covariance": sigma, "numerator": numerator, "root_of_eta_variance": exact_square_root(closed)}


def delta_variance_from_table(table: LabelTable, rater: int = 1) -> Q | None:
    """``g^T Sigma g`` from a table alone, ``g`` from ``eta_gradient`` (exact
    only when the square is perfect) and ``Sigma`` from ``agreement_covariance``."""

    gradient = eta_gradient(pairwise_kappas(table), rater)
    if gradient is None:
        return None
    g, sigma = gradient["per_agreement_rate"], agreement_covariance(table)
    return sum((g[p] * sigma[(p, r)] * g[r] for p in PAIRS for r in PAIRS), Q(0))


def planning_size(errors, target_se) -> int:
    """Smallest ``m`` with delta standard error ``sqrt(V / m) < target``:
    ``floor(V / target^2) + 1``."""

    target = _as_q(target_se, "target_se")
    if target <= 0:
        raise ValueError("target_se must be positive")
    v = delta_variance(errors)["eta"]
    return int(v / target ** 2) + 1


def _pattern_integers(errors) -> tuple[dict, int]:
    q = agreement_patterns(three_rater_model(HALF, _three(errors, "errors")))
    den = 1
    for v in q.values():
        den = den * v.denominator // gcd(den, v.denominator)
    return {k: int(v * den) for k, v in q.items()}, den


def _law_summary(m: int, eta1: Q, tolerance: Q, bits: int, total: int, w: dict, acc_num: dict,
                 acc_num2: dict, acc_root: int, square_distribution: dict | None) -> dict[str, object]:
    w_def = w["exact"] + w["bracketed"]
    out = {"size": m, "eta1": eta1, "tolerance": tolerance,
           "p_undefined_sign": Q(w["sign"], total), "p_undefined_range": Q(w["range"], total),
           "p_undefined": Q(w["sign"] + w["range"], total), "p_exact": Q(w["exact"], total),
           "p_bracketed": Q(w["bracketed"], total), "p_defined": Q(w_def, total),
           "p_within_tolerance": Q(w["within"], total),
           "p_within_tolerance_given_defined": None if w_def == 0 else Q(w["within"], w_def)}
    if w_def == 0:
        out.update({"square_mean": None, "square_variance": None})
        return out
    es = sum((Q(v, m * d) for d, v in acc_num.items()), Q(0)) / w_def
    es2 = sum((Q(v, (m * d) ** 2) for d, v in acc_num2.items()), Q(0)) / w_def
    root_lo, root_hi = Q(acc_root, w_def << bits), Q(acc_root + w_def, w_def << bits)
    out.update({"square_mean": es, "square_variance": es2 - es * es, "scaled_square_variance": m * (es2 - es * es),
                "root_mean_bracket": (root_lo, root_hi),
                "eta_mean_bracket": ((1 - root_hi) / 2, (1 - root_lo) / 2),
                "eta_variance_bracket": ((es - root_hi ** 2) / 4, (es - root_lo ** 2) / 4),
                "scaled_eta_variance_bracket": (m * (es - root_hi ** 2) / 4, m * (es - root_lo ** 2) / 4),
                "moments_are": "conditional on the estimator being defined",
                "square_distribution": square_distribution})
    return out


def _tolerance_bounds(eta1: Q, tolerance: Q) -> tuple[Q, Q]:
    """``|eta_hat - eta1| <= tol`` iff ``lo <= S_hat <= hi`` with ``lo = max(0,
    1 - 2(eta1 + tol))^2`` and ``hi = min(1, 1 - 2(eta1 - tol))^2``."""

    low_root, high_root = max(Q(0), 1 - 2 * (eta1 + tolerance)), min(Q(1), 1 - 2 * (eta1 - tolerance))
    return low_root ** 2, high_root ** 2


def sampling_law(size, errors, tolerance=Q(1, 50), bits: int = ROOT_BITS) -> dict[str, object]:
    """Exact law of ``eta1_hat`` on ``m`` items, free of the prior, by
    enumerating the ``C(m+3, 3)`` compositions of the four-category multinomial
    of agreement patterns (integer weights over a common denominator ``D^m``).

    Outcome classes: some ``kappa_hat <= 0`` (sign; undefined), all positive
    but ``S_hat > 1`` (range; undefined), ``S_hat`` a perfect square (exact
    ``eta1_hat``) and otherwise (bracketed).  Moments of ``S_hat`` and of
    ``eta1_hat`` are conditional on the defined event; those of ``eta1_hat``
    are brackets, from ``root_bracket`` at ``2^-bits`` per outcome.  Also the
    exact probability that the estimator is defined and within ``tolerance``
    of ``eta1``."""

    m, errors, tolerance = _size(size), _three(errors, "errors"), _probability(tolerance, "tolerance")
    n, den = _pattern_integers(errors)
    n0, n12, n13, n23 = n["all"], n[(1, 2)], n[(1, 3)], n[(2, 3)]
    pw = {name: [1] * (m + 1) for name in ("0", "12", "13", "23")}
    for name, base in (("0", n0), ("12", n12), ("13", n13), ("23", n23)):
        for k in range(1, m + 1):
            pw[name][k] = pw[name][k - 1] * base
    fact = [factorial(k) for k in range(m + 1)]
    choose = [[comb(r, j) for j in range(r + 1)] for r in range(m + 1)]
    lo_sq, hi_sq = _tolerance_bounds(errors[0], tolerance)
    lo_n, lo_d, hi_n, hi_d = lo_sq.numerator, lo_sq.denominator, hi_sq.numerator, hi_sq.denominator
    shift = 2 * bits
    w = {"sign": 0, "range": 0, "exact": 0, "bracketed": 0, "within": 0}
    acc_num, acc_num2, acc_root, total = {}, {}, 0, 0
    for k23 in range(m + 1):
        for k0 in range(m - k23 + 1):
            rest = m - k23 - k0
            d = 2 * (k0 + k23) - m
            dd = m * d
            outer = fact[m] // (fact[k23] * fact[k0] * fact[rest]) * pw["23"][k23] * pw["0"][k0]
            row, p12, p13 = choose[rest], pw["12"], pw["13"]
            s_num = s_num2 = 0
            for k12 in range(rest + 1):
                weight = outer * row[k12] * p12[k12] * p13[rest - k12]
                total += weight
                a, b = 2 * (k0 + k12) - m, 2 * (k0 + rest - k12) - m
                if a <= 0 or b <= 0 or d <= 0:
                    w["sign"] += weight
                    continue
                num = a * b
                if num > dd:
                    w["range"] += weight
                    continue
                s_num += weight * num
                s_num2 += weight * num * num
                g = gcd(num, dd)
                nn, dn = num // g, dd // g
                rn, rd = isqrt(nn), isqrt(dn)
                w["exact" if rn * rn == nn and rd * rd == dn else "bracketed"] += weight
                if num * lo_d >= lo_n * dd and num * hi_d <= hi_n * dd:
                    w["within"] += weight
                acc_root += weight * isqrt((num << shift) // dd)
            if s_num:
                acc_num[d] = acc_num.get(d, 0) + s_num
                acc_num2[d] = acc_num2.get(d, 0) + s_num2
    if total != den ** m:
        raise AssertionError("the multinomial weights do not sum to D^m")
    out = _law_summary(m, errors[0], tolerance, bits, total, w, acc_num, acc_num2, acc_root, None)
    out.update({"method": "four-pattern multinomial", "compositions": comb(m + 3, 3),
                "pattern_probabilities": {str(k): Q(v, den) for k, v in n.items()}})
    return out


def sampling_law_by_tables(size, errors, tolerance=Q(1, 50), bits: int = ROOT_BITS) -> dict[str, object]:
    """The same law by enumerating every label table, ``C(m+7, 7)`` of them,
    with the full distribution of ``S_hat`` on the defined event: the
    cross-check of the four-pattern reduction."""

    m, errors, tolerance = _size(size), _three(errors, "errors"), _probability(tolerance, "tolerance")
    table = three_rater_model(HALF, errors)
    den = 1
    for cell in CELLS3:
        den = den * table.probability(cell).denominator // gcd(den, table.probability(cell).denominator)
    n = [int(table.probability(cell) * den) for cell in CELLS3]
    pw = [[base ** k for k in range(m + 1)] for base in n]
    fact = [factorial(k) for k in range(m + 1)]
    patterns = [(int(a == b), int(a == c), int(b == c)) for a, b, c in CELLS3]
    lo_sq, hi_sq = _tolerance_bounds(errors[0], tolerance)
    w = {"sign": 0, "range": 0, "exact": 0, "bracketed": 0, "within": 0}
    acc_num, acc_num2, acc_root, total, distribution = {}, {}, 0, 0, {}
    shift = 2 * bits

    def visit(counts: list[int]) -> None:
        nonlocal acc_root, total
        weight, n12, n13, n23 = fact[m], 0, 0, 0
        for j, k in enumerate(counts):
            weight = weight // fact[k] * pw[j][k]
            n12 += patterns[j][0] * k
            n13 += patterns[j][1] * k
            n23 += patterns[j][2] * k
        total += weight
        a, b, d = 2 * n12 - m, 2 * n13 - m, 2 * n23 - m
        if a <= 0 or b <= 0 or d <= 0:
            w["sign"] += weight
            return
        square = Q(a * b, m * d)
        if square > 1:
            w["range"] += weight
            return
        distribution[square] = distribution.get(square, 0) + weight
        acc_num[d] = acc_num.get(d, 0) + weight * a * b
        acc_num2[d] = acc_num2.get(d, 0) + weight * (a * b) ** 2
        w["exact" if exact_square_root(square) is not None else "bracketed"] += weight
        if lo_sq <= square <= hi_sq:
            w["within"] += weight
        acc_root += weight * isqrt((a * b << shift) // (m * d))

    def compositions(i: int, remaining: int, counts: list[int]) -> None:
        if i == 7:
            visit(counts + [remaining])
            return
        for k in range(remaining + 1):
            compositions(i + 1, remaining - k, counts + [k])

    compositions(0, m, [])
    if total != den ** m:
        raise AssertionError("the multinomial weights do not sum to D^m")
    out = _law_summary(m, errors[0], tolerance, bits, total, w, acc_num, acc_num2, acc_root,
                       {s: Q(c, total) for s, c in sorted(distribution.items())})
    out.update({"method": "all label tables", "compositions": comb(m + 7, 7)})
    return out


def _binomial_upper_tail(trials: int, p: Q, k: int) -> Q:
    """``P(Bin(n, p) >= k)`` by integer accumulation over the common
    denominator ``b^n`` (``p = a/b``, ``c = b - a``): the terms ``t_j = C(n, j)
    a^j c^(n-j)`` satisfy ``t_{j+1} = t_j (n - j) a / ((j + 1) c)`` exactly, so
    one small multiplication and one exact small division per term.  Equals
    the judge module's tail."""

    a, b = p.numerator, p.denominator
    c = b - a
    if k <= 0:
        return Q(1)
    if k > trials or a == 0:
        return Q(0)
    if c == 0:
        return Q(1)
    term = comb(trials, k) * a ** k * c ** (trials - k)
    acc = term
    for j in range(k, trials):
        term = term * (trials - j) * a // ((j + 1) * c)
        acc += term
    return Q(acc, b ** trials)


def disagreement_bound(size, agreements, alpha=Q(1, 20), resolution=RESOLUTION) -> dict[str, object]:
    """An exact conservative confidence statement from ``N_12`` alone, which
    is ``Bin(m, A_12)`` with ``A_12 = (1 + d_1 d_2) / 2`` whenever G1 and G2
    are conditionally independent (the controller is not needed).  With the
    one-sided lower Clopper-Pearson endpoint ``A_L`` (``P[Bin(m, A_L) >= N_12]
    = alpha``), ``d_1 d_2 >= 2 A_L - 1`` at confidence ``1 - alpha``, and since
    ``d_2 <= 1``: ``eta_1 <= 1 - A_L``, likewise ``eta_2 <= 1 - A_L``.  It bounds
    each grader's error by the pair's disagreement; it gives no lower bound,
    does not separate ``eta_1`` from ``eta_2``, ignores the controller, and is
    tight only when the other grader is perfect.  ``A_L`` is a beta quantile,
    bracketed to ``resolution`` by bisection on the exact tail."""

    m, alpha, resolution = _size(size), _probability(alpha, "alpha"), _as_q(resolution, "resolution")
    if type(agreements) is not int or not 0 <= agreements <= m:
        raise ValueError("agreements must be an integer count between 0 and size")
    if not 0 < alpha < 1 or resolution <= 0:
        raise ValueError("alpha must lie strictly inside (0, 1) and resolution be positive")
    if agreements == 0:
        low = high = Q(0)
    else:
        low, high = Q(0), Q(1)
        while high - low > resolution:
            mid = (low + high) / 2
            if _binomial_upper_tail(m, mid, agreements) < alpha:
                low = mid
            else:
                high = mid
    return {"size": m, "agreements": agreements, "alpha": alpha, "agreement_rate": Q(agreements, m),
            "lower_endpoint_bracket": (low, high), "eta_upper_bound": 1 - low,
            "eta_upper_bound_at_population_rate": 1 - Q(agreements, m),
            "bounds": "eta_1 and eta_2 each, from above only; valid without the controller"}


# --- 5. the asymmetric three-rater model (two-class Dawid-Skene) ---------------

CONVENTIONS = ("all_informative", "rater_1_informative")


def _ds_cells(prior: Q, sensitivities: tuple, false_positives: tuple) -> dict:
    cells = {}
    for cell in CELLS3:
        weight = Q(0)
        for y in (0, 1):
            w = prior if y else 1 - prior
            for i in range(3):
                hit = sensitivities[i] if y else false_positives[i]
                w *= hit if cell[i] == 1 else 1 - hit
            weight += w
        cells[cell] = weight
    return cells


def dawid_skene_model(prior, false_negatives, false_positives) -> LabelTable:
    """Cell probabilities when ``Y ~ Bernoulli(prior)`` and rater ``i`` reports
    ``X_i = 0`` with probability ``alpha_i`` when ``Y = 1`` and ``X_i = 1``
    with probability ``beta_i`` when ``Y = 0``, independently given ``Y``.
    The symmetric model is ``alpha_i = beta_i = e_i``."""

    prior = _probability(prior, "prior")
    alphas, betas = _three(false_negatives, "false_negatives"), _three(false_positives, "false_positives")
    return LabelTable(_ds_cells(prior, tuple(1 - a for a in alphas), betas))


def dawid_skene_moments(table: LabelTable) -> dict[str, object]:
    """``p_i = P[X_i = 1]``, the pair covariances ``c_ij = p_ij - p_i p_j`` and
    the third central moment ``k_3 = E prod (X_i - p_i) = p_123 - sum_i p_i
    p_jk + 2 p_1 p_2 p_3``.  Under the model, with ``u = pi (1 - pi)`` and
    ``delta_i = 1 - alpha_i - beta_i``: ``c_ij = u delta_i delta_j`` (rank one)
    and ``k_3 = u (1 - 2 pi) delta_1 delta_2 delta_3``, so the radicand
    ``k_3^2 + 4 c_12 c_13 c_23 = (u delta_1 delta_2 delta_3)^2``."""

    p = {i: sum((table.probability(c) for c in CELLS3 if c[i - 1] == 1), Q(0)) for i in (1, 2, 3)}
    pp = {pair: sum((table.probability(c) for c in CELLS3 if c[pair[0] - 1] == 1 and c[pair[1] - 1] == 1), Q(0))
          for pair in PAIRS}
    p123 = table.probability((1, 1, 1))
    cov = {pair: pp[pair] - p[pair[0]] * p[pair[1]] for pair in PAIRS}
    third = p123 - sum(p[i] * pp[_others(i)] for i in (1, 2, 3)) + 2 * p[1] * p[2] * p[3]
    radicand = third ** 2 + 4 * cov[(1, 2)] * cov[(1, 3)] * cov[(2, 3)]
    return {"marginals": p, "pair_moments": pp, "triple_moment": p123, "covariances": cov,
            "third_cumulant": third, "radicand": radicand}


def _ds_parameters(moments: dict, root: Q, sigma: int) -> dict[str, object]:
    """Under ``delta_1 > 0`` with ``sigma = sign(c_23)``: ``pi = (R - sigma k_3)
    / (2R)``, ``delta_1 = R / |c_23|``, ``delta_2 = sigma R / c_13``, ``delta_3 =
    sigma R / c_12``, ``1 - alpha_i = p_i + (1 - pi) delta_i``, ``beta_i = p_i
    - pi delta_i``.  Proof: ``R = u |delta_1 delta_2 delta_3|`` and ``k_3 / c_23
    = (1 - 2 pi) delta_1``, so ``1 - alpha_1 - p_1`` and ``beta_1 - p_1`` are the
    roots ``(1 - pi) delta_1`` and ``-pi delta_1`` of ``z^2 - (k_3 / c_23) z -
    c_12 c_13 / c_23``; every parameter but ``pi`` is affine in ``R`` and ``pi``
    is monotone in it."""

    p, cov, third = moments["marginals"], moments["covariances"], moments["third_cumulant"]
    prior = (root - sigma * third) / (2 * root)
    delta = {1: root / abs(cov[(2, 3)]), 2: sigma * root / cov[(1, 3)], 3: sigma * root / cov[(1, 2)]}
    sens = {i: p[i] + (1 - prior) * delta[i] for i in (1, 2, 3)}
    beta = {i: p[i] - prior * delta[i] for i in (1, 2, 3)}
    return {"prior": prior, "false_negatives": {i: 1 - sens[i] for i in (1, 2, 3)}, "false_positives": beta,
            "deltas": delta}


def _ds_switch(params: dict) -> dict:
    """The label-switched solution ``(1 - pi, 1 - beta, 1 - alpha)``, which
    fits the same table."""

    return {"prior": 1 - params["prior"],
            "false_negatives": {i: 1 - b for i, b in params["false_positives"].items()},
            "false_positives": {i: 1 - a for i, a in params["false_negatives"].items()},
            "deltas": {i: -d for i, d in params["deltas"].items()}}


def _ds_in_range(params: dict) -> bool:
    values = [params["prior"]] + list(params["false_negatives"].values()) + list(params["false_positives"].values())
    return all(0 <= v <= 1 for v in values)


def _ds_bracket(low: dict, high: dict) -> dict:
    out = {}
    for key in ("prior", "false_negatives", "false_positives", "deltas"):
        if key == "prior":
            out[key] = (min(low[key], high[key]), max(low[key], high[key]))
        else:
            out[key] = {i: (min(low[key][i], high[key][i]), max(low[key][i], high[key][i])) for i in (1, 2, 3)}
    return out


def dawid_skene_three_raters(table: LabelTable, convention: str = "all_informative",
                             bits: int = ROOT_BITS) -> dict[str, object]:
    """The just-identified moment solution.  Statuses: ``not_identified`` (a
    pair covariance is zero: a rater at chance under every labelling, or a
    degenerate prior), ``outside_model`` (radicand ``<= 0``: no real parameter
    point; the model's image is cut out by inequalities only), ``convention_
    violated`` (``all_informative`` asked but a pair covariance is negative, so
    one rater is anti-informative under either labelling), ``exact`` (the
    radicand is a rational square, always so at expected counts of rational
    parameters) or ``bracketed`` (every parameter bracketed through the root's
    ``2^-bits`` bracket).  ``solution`` follows the convention, ``alternative``
    is its label switch; both reproduce the table."""

    if convention not in CONVENTIONS:
        raise ValueError(f"convention must be one of {CONVENTIONS}")
    moments = dawid_skene_moments(table)
    cov, radicand = moments["covariances"], moments["radicand"]
    out = {"convention": convention, "moments": moments, "radicand": radicand,
           "degrees_of_freedom_left": DEGREES_OF_FREEDOM["free_cell_probabilities"]
           - DEGREES_OF_FREEDOM["asymmetric_dawid_skene_parameters"]}
    if any(c == 0 for c in cov.values()):
        out["status"] = "not_identified"
        return out
    if radicand <= 0:
        out["status"] = "outside_model"
        return out
    if convention == "all_informative" and any(c < 0 for c in cov.values()):
        out["status"] = "convention_violated"
        return out
    sigma = 1 if cov[(2, 3)] > 0 else -1
    bracket = root_bracket(radicand, bits)
    if bracket["exact"] is not None:
        solution = _ds_parameters(moments, bracket["exact"], sigma)
        out.update({"status": "exact", "root": bracket["exact"], "solution": solution,
                    "alternative": _ds_switch(solution), "in_range": _ds_in_range(solution)})
        return out
    low, high = (_ds_parameters(moments, bracket[end], sigma) for end in ("lower", "upper"))
    out.update({"status": "bracketed", "root": None, "root_bracket": (bracket["lower"], bracket["upper"]),
                "solution": _ds_bracket(low, high), "alternative": _ds_bracket(_ds_switch(low), _ds_switch(high)),
                "in_range": _ds_in_range(low) and _ds_in_range(high)})
    return out


def dawid_skene_jacobian_rank(prior, false_negatives, false_positives) -> int:
    """Rank of the exact Jacobian of ``(pi, alpha, beta) -> cells``.  Each cell
    is affine in every single parameter, so ``p(theta + e_j) - p(theta)`` is the
    exact partial derivative.  Seven wherever every ``delta_i != 0`` and
    ``0 < pi < 1``: the image is full-dimensional in the simplex and there is
    no equality constraint, hence no test of conditional independence."""

    prior = _probability(prior, "prior")
    alphas, betas = _three(false_negatives, "false_negatives"), _three(false_positives, "false_positives")
    sens = tuple(1 - a for a in alphas)
    base = _ds_cells(prior, sens, betas)

    def column(moved_prior, moved_sens, moved_betas) -> list[Q]:
        cells = _ds_cells(moved_prior, moved_sens, moved_betas)
        return [cells[c] - base[c] for c in CELLS3]

    columns = [column(prior + 1, sens, betas)]
    for i in range(3):
        bumped = list(sens)
        bumped[i] += 1
        columns.append(column(prior, tuple(bumped), betas))
        bumped = list(betas)
        bumped[i] += 1
        columns.append(column(prior, sens, tuple(bumped)))
    return _rank([[col[r] for col in columns] for r in range(8)])


def expected_record_table_asymmetric(size: int, prior, controller, judge_error, eps1, gold, second) -> RecordTable:
    """Expected counts with class-dependent rates: the controller answers
    ``Y`` with probability ``1 - alpha_C`` on ``Y = 1`` and ``1 - beta_C`` on
    ``Y = 0``; the judge depends on correctness only (``eps0`` from the
    marginal accuracy); G1 and G2 flip at ``(alpha, beta)`` each."""

    size, prior = _size(size), _probability(prior, "prior")
    (ac, bc), (a1, b1), (a2, b2) = (_rate_pair(controller, "controller"), _rate_pair(gold, "gold"),
                                   _rate_pair(second, "second"))
    judge_error, eps1 = _probability(judge_error, "judge_error"), _probability(eps1, "eps1")
    accuracy = prior * (1 - ac) + (1 - prior) * (1 - bc)
    low, high = shared_error_bounds(accuracy, judge_error)
    if not low <= eps1 <= high:
        raise ValueError("eps1 is infeasible for the marginal judge error")
    eps0 = (judge_error - (1 - accuracy) * eps1) / accuracy
    cells = {}
    for cell in CELLS4:
        x, v, g1, g2 = cell
        weight = Q(0)
        for y in (0, 1):
            w = prior if y else 1 - prior
            right_rate = (1 - ac) if y else (1 - bc)
            right = x == y
            w *= right_rate if right else 1 - right_rate
            says_correct = (1 - eps0) if right else eps1
            w *= says_correct if v == 1 else 1 - says_correct
            for g, (fn, fp) in ((g1, (a1, b1)), (g2, (a2, b2))):
                hit = (1 - fn) if y else fp
                w *= hit if g == 1 else 1 - hit
            weight += w
        cells[cell] = size * weight
    return RecordTable(cells)


def _class_rates(prior, controller, gold) -> tuple[Q, dict, dict]:
    prior = _probability(prior, "prior")
    (ac, bc), (a1, b1) = _rate_pair(controller, "controller"), _rate_pair(gold, "gold")
    return prior, {1: 1 - ac, 0: 1 - bc}, {1: a1, 0: b1}


def asymmetric_gold_noise_forward(prior, controller, judge_error, eps1, gold) -> dict[str, Q]:
    """Measured rates against an asymmetric gold grader.  With ``a_y`` the
    controller's accuracy and ``f_y`` the gold flip rate on class ``y``:
    ``a' = sum_y pi_y (a_y (1 - f_y) + (1 - a_y) f_y)``,
    ``eps' = sum_y pi_y (f_y + (1 - 2 f_y)(a_y eps0 + (1 - a_y) eps1))``,
    ``w = sum_y pi_y ((1 - a_y)(1 - f_y) eps1 + a_y f_y (1 - eps0))``.
    The agreement rate ``P[C = J]`` is still invariant: the same flip hits
    both measured indicators, label-dependent or not."""

    prior, acc, flip = _class_rates(prior, controller, gold)
    judge_error, eps1 = _probability(judge_error, "judge_error"), _probability(eps1, "eps1")
    accuracy = prior * acc[1] + (1 - prior) * acc[0]
    low, high = shared_error_bounds(accuracy, judge_error)
    if not low <= eps1 <= high:
        raise ValueError("eps1 is infeasible for the marginal judge error")
    eps0 = (judge_error - (1 - accuracy) * eps1) / accuracy
    weight = {1: prior, 0: 1 - prior}
    measured_accuracy = sum(weight[y] * (acc[y] * (1 - flip[y]) + (1 - acc[y]) * flip[y]) for y in (0, 1))
    measured_error = sum(weight[y] * (flip[y] + (1 - 2 * flip[y]) * (acc[y] * eps0 + (1 - acc[y]) * eps1))
                         for y in (0, 1))
    wrong_wrong = sum(weight[y] * ((1 - acc[y]) * (1 - flip[y]) * eps1 + acc[y] * flip[y] * (1 - eps0))
                      for y in (0, 1))
    return {"accuracy": measured_accuracy, "judge_error": measured_error, "wrong_wrong_rate": wrong_wrong,
            "eps1": None if measured_accuracy == 1 else wrong_wrong / (1 - measured_accuracy),
            "agreement_rate": accuracy * (1 - eps0) + (1 - accuracy) * eps1,
            "true_accuracy": accuracy, "eps0": eps0}


def asymmetric_gold_noise_inverse(prior, controller, gold, measured_accuracy, measured_error,
                                  wrong_wrong_rate) -> dict[str, Q]:
    """Invert the forward map given the gold grader's two rates and the
    controller's two accuracies (both from the Dawid-Skene fit).  ``eps'`` and
    ``w`` are affine in ``(eps0, eps1)``: with ``F = sum pi_y f_y``, ``E_a = sum
    pi_y (1 - 2 f_y) a_y``, ``E_b = sum pi_y (1 - 2 f_y)(1 - a_y)``, ``G_a = sum
    pi_y a_y f_y``, ``G_b = sum pi_y (1 - a_y)(1 - f_y)`` and ``Delta = E_a G_b +
    E_b G_a``: ``eps1 = (E_a (w - G_a) + G_a (eps' - F)) / Delta``, ``eps0 =
    (G_b (eps' - F) - E_b (w - G_a)) / Delta``.  Symmetric case: ``Delta = a (1 -
    a)(1 - 2 eta)`` and the judge note's inversion.  ``a'`` is reproduced by the
    fit and serves as a consistency check."""

    prior, acc, flip = _class_rates(prior, controller, gold)
    a_m, e_m, w = (_probability(measured_accuracy, "measured_accuracy"),
                   _probability(measured_error, "measured_error"), _probability(wrong_wrong_rate, "wrong_wrong_rate"))
    weight = {1: prior, 0: 1 - prior}
    f_bar = sum(weight[y] * flip[y] for y in (0, 1))
    e_a = sum(weight[y] * (1 - 2 * flip[y]) * acc[y] for y in (0, 1))
    e_b = sum(weight[y] * (1 - 2 * flip[y]) * (1 - acc[y]) for y in (0, 1))
    g_a = sum(weight[y] * acc[y] * flip[y] for y in (0, 1))
    g_b = sum(weight[y] * (1 - acc[y]) * (1 - flip[y]) for y in (0, 1))
    determinant = e_a * g_b + e_b * g_a
    if determinant == 0:
        raise ValueError("the inversion is singular (a degenerate controller or a gold grader at chance)")
    eps1 = (e_a * (w - g_a) + g_a * (e_m - f_bar)) / determinant
    eps0 = (g_b * (e_m - f_bar) - e_b * (w - g_a)) / determinant
    accuracy = prior * acc[1] + (1 - prior) * acc[0]
    predicted = sum(weight[y] * (acc[y] * (1 - flip[y]) + (1 - acc[y]) * flip[y]) for y in (0, 1))
    return {"accuracy": accuracy, "eps0": eps0, "eps1": eps1,
            "judge_error": accuracy * eps0 + (1 - accuracy) * eps1,
            "determinant": determinant, "measured_accuracy_consistent": predicted == a_m}


def calibrate_asymmetric(record: RecordTable, declared_judge_error=None, alpha=Q(1, 20),
                         convention: str = "all_informative", bits: int = ROOT_BITS) -> dict[str, object]:
    """The pipeline under the asymmetric model: Dawid-Skene fit of the label
    table, the asymmetric inversion at the fitted rates, corrected counts and
    the judge module's tests.  When the fit is bracketed the inversion is
    evaluated at both ends of the root's bracket; those are the ends of the
    ``eps1`` bracket only if the inversion is monotone in the root, which is
    not checked here."""

    alpha = _probability(alpha, "alpha")
    declared = None if declared_judge_error is None else _probability(declared_judge_error, "declared_judge_error")
    if record.total.denominator != 1:
        raise ValueError("corrected counts need an integer total")
    size = int(record.total)
    fit = dawid_skene_three_raters(record.label_table(), convention, bits)
    measured = measured_judge_rates(record, 1)
    out = {"size": record.total, "fit": fit, "measured": measured, "declared_judge_error": declared,
           "symmetric_constraints": model_constraints(record.label_table())}
    if fit["status"] not in ("exact", "bracketed") or not fit["in_range"]:
        out.update({"status": "out_of_range" if fit["status"] in ("exact", "bracketed") else fit["status"],
                    "inversions": []})
        return out
    if fit["status"] == "exact":
        points = [fit["solution"]]
    else:
        sigma = 1 if fit["moments"]["covariances"][(2, 3)] > 0 else -1
        points = [_ds_parameters(fit["moments"], r, sigma) for r in fit["root_bracket"]]
    inversions = []
    for params in points:
        gold = (params["false_negatives"][1], params["false_positives"][1])
        controller = (params["false_negatives"][3], params["false_positives"][3])
        rates = asymmetric_gold_noise_inverse(params["prior"], controller, gold, measured["accuracy"],
                                              measured["judge_error"], measured["wrong_wrong_rate"])
        expected = expected_table(size, rates["accuracy"], rates["judge_error"], rates["eps1"])
        table, changed = rounded_table(expected)
        error = declared if declared is not None else rates["judge_error"]
        inversions.append({"parameters": params, "recovered": rates, "corrected_expected": expected,
                           "corrected_table": table, "rounding_changed_a_cell": changed,
                           "tests": _judge_tests(table, error, alpha, declared is None)})
    out.update({"status": fit["status"], "inversions": inversions,
                "bracket_ends_are_a_bracket_only_if_monotone": fit["status"] == "bracketed"})
    return out


# --- 6. four raters: the asymmetric model becomes testable --------------------

RATERS4 = {1: "G1", 2: "G2", 3: "G3", 4: "C"}
PAIRS4 = tuple((i, j) for i in range(1, 5) for j in range(i + 1, 5))
TRIPLES4 = ((1, 2, 3), (1, 2, 4), (1, 3, 4), (2, 3, 4))
CONSTRAINTS4 = ("tetrad_12_34_vs_13_24", "tetrad_13_24_vs_14_23", "third_123_vs_124",
                "third_123_vs_134", "third_123_vs_234", "fourth_moment")
MOMENT_KEYS4 = tuple((i,) for i in range(1, 5)) + PAIRS4 + TRIPLES4 + ((1, 2, 3, 4),)


def _four(values, name: str) -> tuple[Q, Q, Q, Q]:
    if not isinstance(values, (tuple, list)) or len(values) != 4:
        raise ValueError(f"{name} must list four rates")
    return tuple(_probability(v, f"{name}[{i}]") for i, v in enumerate(values))


@dataclass(frozen=True)
class FourRaterTable:
    """Rational weights on the 2^4 cells ``(x_1, x_2, x_3, x_4)`` of four binary
    raters' labels: the gold grader G1, a second grader G2, a third grader G3
    and the controller's answer C.  One more independent grading of the same
    sealed sample than ``LabelTable``: that is what a fourth rater costs."""

    cells: dict

    def __post_init__(self) -> None:
        object.__setattr__(self, "cells", _weights(self.cells, CELLS4, "(x_1, x_2, x_3, x_4) in {0,1}^4"))

    @property
    def total(self) -> Q:
        return sum(self.cells.values(), Q(0))

    def probability(self, cell: tuple[int, int, int, int]) -> Q:
        return self.cells[cell] / self.total

    def triple(self, drop: int) -> LabelTable:
        """Marginal over rater ``drop``; the other three keep their order and
        become raters 1, 2, 3 of a ``LabelTable``."""

        if drop not in (1, 2, 3, 4):
            raise ValueError("drop must name a rater 1..4")
        keep = [i - 1 for i in range(1, 5) if i != drop]
        cells = {cell: Q(0) for cell in CELLS3}
        for cell, weight in self.cells.items():
            cells[tuple(cell[i] for i in keep)] += weight
        return LabelTable(cells)


def _four_cells(prior: Q, sensitivities: tuple, false_positives: tuple) -> dict:
    cells = {}
    for cell in CELLS4:
        weight = Q(0)
        for y in (0, 1):
            w = prior if y else 1 - prior
            for i in range(4):
                hit = sensitivities[i] if y else false_positives[i]
                w *= hit if cell[i] == 1 else 1 - hit
            weight += w
        cells[cell] = weight
    return cells


def four_rater_model(prior, false_negatives, false_positives) -> FourRaterTable:
    """Four conditionally independent raters with asymmetric rates: nine
    parameters ``(pi, alpha_i, beta_i)`` on the fifteen degrees of freedom of
    the 2^4 table, so six constraints (``four_rater_constraints``)."""

    prior = _probability(prior, "prior")
    alphas, betas = _four(false_negatives, "false_negatives"), _four(false_positives, "false_positives")
    return FourRaterTable(_four_cells(prior, tuple(1 - a for a in alphas), betas))


def four_rater_moments(table: FourRaterTable) -> dict[str, object]:
    """Centred moments ``k_S = E prod_{i in S} (X_i - p_i)`` for every subset
    with at least two raters, plus the marginals ``p_i``.  Under the model,
    with ``u = pi (1 - pi)``, ``delta_i = 1 - alpha_i - beta_i`` and
    ``E[X_i - p_i | Y] = delta_i (Y - pi)``: conditional independence gives
    ``k_S = E[(Y - pi)^|S|] prod_{i in S} delta_i`` with ``E[(Y - pi)^2] = u``,
    ``E[(Y - pi)^3] = u (1 - 2 pi)``, ``E[(Y - pi)^4] = u (1 - 3u)``.  So
    ``c_ij = u delta_i delta_j``, ``k_ijk = u (1 - 2 pi) delta_i delta_j
    delta_k`` and ``k_1234 = u (1 - 3u) delta_1 delta_2 delta_3 delta_4``."""

    p = {i: sum((table.probability(c) for c in CELLS4 if c[i - 1] == 1), Q(0)) for i in range(1, 5)}
    moments = {}
    for subset in MOMENT_KEYS4[4:]:
        total = Q(0)
        for cell in CELLS4:
            w = table.probability(cell)
            for i in subset:
                w *= cell[i - 1] - p[i]
            total += w
        moments[subset] = total
    return {"marginals": p, "covariances": {pair: moments[pair] for pair in PAIRS4},
            "third_moments": {t: moments[t] for t in TRIPLES4}, "fourth_moment": moments[(1, 2, 3, 4)]}


def four_rater_residuals(moments: dict) -> dict[str, Q]:
    """The six polynomial equalities, as residuals that vanish under the model.

    Tetrads: ``c_12 c_34 = c_13 c_24 = c_14 c_23`` (each is ``u^2 prod delta``;
    two independent equalities).  Third-moment ratios: ``k_ijk / k_ijl = c_ik
    / c_il = delta_k / delta_l``; written without division, ``k_ijk c_il = k_ijl
    c_ik`` (both are ``u^2 (1 - 2 pi) delta_i^2 delta_j delta_k delta_l``).
    Twelve such relations exist (two per pair ``{i, j}``); three express
    ``k_124, k_134, k_234`` through ``k_123`` and the covariances, and the other
    nine follow from those three and the tetrads by substitution wherever the
    covariances are nonzero (``ratio_relations``).
    Fourth moment: ``(k_1234 - c_12 c_34) c_12 = k_123 k_124``, since
    ``k_1234 - c_12 c_34 = u (1 - 4u) prod delta = u (1 - 2 pi)^2 prod delta``
    and ``k_123 k_124 = u^2 (1 - 2 pi)^2 delta_1^2 delta_2^2 delta_3 delta_4``.
    The six have a rank-6 Jacobian wherever ``c_12 c_13 != 0``
    (``constraint_jacobian_rank``) and the model's parameter Jacobian has rank
    9 (``four_rater_jacobian_rank``): near such a model point the image (nine
    dimensions) and the zero set of six independent functions (15 - 6 = 9)
    coincide, so there are exactly six independent equalities."""

    c, k, m4 = moments["covariances"], moments["third_moments"], moments["fourth_moment"]
    return {"tetrad_12_34_vs_13_24": c[(1, 2)] * c[(3, 4)] - c[(1, 3)] * c[(2, 4)],
            "tetrad_13_24_vs_14_23": c[(1, 3)] * c[(2, 4)] - c[(1, 4)] * c[(2, 3)],
            "third_123_vs_124": k[(1, 2, 3)] * c[(1, 4)] - k[(1, 2, 4)] * c[(1, 3)],
            "third_123_vs_134": k[(1, 2, 3)] * c[(1, 4)] - k[(1, 3, 4)] * c[(1, 2)],
            "third_123_vs_234": k[(1, 2, 3)] * c[(2, 4)] - k[(2, 3, 4)] * c[(1, 2)],
            "fourth_moment": (m4 - c[(1, 2)] * c[(3, 4)]) * c[(1, 2)] - k[(1, 2, 3)] * k[(1, 2, 4)]}


def _third(k: dict, a: int, b: int, c: int) -> Q:
    return k[tuple(sorted((a, b, c)))]


def ratio_relations(moments: dict) -> dict[tuple[int, int, int], Q]:
    """All twelve third-moment ratio relations as residuals: for a pair
    ``{i, j}``, the other two raters ``k < l`` and a pivot ``p`` in ``{i, j}``,
    ``k_ijk c_pl - k_ijl c_pk`` (zero under the model, both sides being
    ``u^2 (1 - 2 pi) delta_p^2 prod_{q != p} delta_q``).  Keyed ``(i, j, p)``."""

    c, k = moments["covariances"], moments["third_moments"]
    out = {}
    for i, j in PAIRS4:
        a, b = (r for r in range(1, 5) if r not in (i, j))
        for pivot in (i, j):
            out[(i, j, pivot)] = (_third(k, i, j, a) * c[_pair(pivot, b)]
                                  - _third(k, i, j, b) * c[_pair(pivot, a)])
    return out


def constraint_jacobian_rank(moments: dict) -> int:
    """Rank of the 6 x 15 Jacobian of the residuals in the centred moments
    ``(p_i, c_ij, k_ijk, k_1234)``, which are a coordinate system on the
    simplex.  Every residual has degree at most two in each single moment, so
    the central difference ``(r(x + h) - r(x - h)) / 2h`` is the exact partial.

    Six wherever ``c_12 c_13 != 0``, at any moment point, model or not.
    Proof: on the columns ``(c_24, c_34, k_124, k_134, k_234, k_1234)`` with
    rows ordered (tetrad 2, tetrad 1, the three ratios, fourth moment) the
    minor is lower triangular with diagonal ``(c_13, c_12, -c_13, -c_12, -c_12,
    c_12)``, determinant ``-c_12^4 c_13^2``."""

    flat = {(i,): moments["marginals"][i] for i in range(1, 5)}
    flat.update(moments["covariances"])
    flat.update(moments["third_moments"])
    flat[(1, 2, 3, 4)] = moments["fourth_moment"]

    def residuals_at(values: dict) -> list[Q]:
        split = {"marginals": {i: values[(i,)] for i in range(1, 5)},
                 "covariances": {pair: values[pair] for pair in PAIRS4},
                 "third_moments": {t: values[t] for t in TRIPLES4}, "fourth_moment": values[(1, 2, 3, 4)]}
        r = four_rater_residuals(split)
        return [r[name] for name in CONSTRAINTS4]

    h = Q(1)
    columns = []
    for key in MOMENT_KEYS4:
        up, down = dict(flat), dict(flat)
        up[key] += h
        down[key] -= h
        columns.append([(a - b) / (2 * h) for a, b in zip(residuals_at(up), residuals_at(down))])
    return _rank([[col[r] for col in columns] for r in range(len(CONSTRAINTS4))])


def four_rater_jacobian_rank(prior, false_negatives, false_positives) -> int:
    """Rank of the exact 16 x 9 Jacobian of ``(pi, alpha, beta) -> cells``
    (affine in each parameter, so one difference per column is exact).

    Nine wherever ``0 < pi < 1`` and at least three ``delta_i != 0``.  Proof:
    if ``delta_1 delta_2 delta_3 != 0`` (relabel otherwise), Proposition 4 on
    the triple (1, 2, 3) and ``delta_4 = c_14 / (u delta_1)``, ``s_4 = p_4 +
    (1 - pi) delta_4``, ``t_4 = p_4 - pi delta_4`` form a map ``G``, smooth on
    a neighbourhood of the table, with ``G(F(theta)) = theta`` near ``theta``;
    so ``DG DF = I_9``.  A chance rater therefore does not lower the rank,
    though it zeroes three covariances and can degenerate the six residuals."""

    prior = _probability(prior, "prior")
    alphas, betas = _four(false_negatives, "false_negatives"), _four(false_positives, "false_positives")
    sens = tuple(1 - a for a in alphas)
    base = _four_cells(prior, sens, betas)

    def column(moved_prior, moved_sens, moved_betas) -> list[Q]:
        cells = _four_cells(moved_prior, moved_sens, moved_betas)
        return [cells[c] - base[c] for c in CELLS4]

    columns = [column(prior + 1, sens, betas)]
    for i in range(4):
        bumped = list(sens)
        bumped[i] += 1
        columns.append(column(prior, tuple(bumped), betas))
        bumped = list(betas)
        bumped[i] += 1
        columns.append(column(prior, sens, tuple(bumped)))
    return _rank([[col[r] for col in columns] for r in range(16)])


def _merge_point(values: list) -> tuple[object, bool]:
    """Exact values agree, or brackets intersect (returning the intersection)."""

    if all(not isinstance(v, tuple) for v in values):
        return values[0], all(v == values[0] for v in values)
    lows = [v[0] if isinstance(v, tuple) else v for v in values]
    highs = [v[1] if isinstance(v, tuple) else v for v in values]
    low, high = max(lows), min(highs)
    return (low, high), low <= high


def dawid_skene_four_raters(table: FourRaterTable, convention: str = "all_informative",
                            bits: int = ROOT_BITS) -> dict[str, object]:
    """Fit the three-rater solution on each of the four triples and check that
    they agree: the prior on all four, each rater's two rates on the three
    triples containing it.  Statuses: a triple's failure status
    (``not_identified``, ``outside_model``, ``convention_violated``), ``exact``
    (all triples exact and equal), ``bracketed`` (every bracket intersects;
    the solution is the intersection) or ``inconsistent``.  Agreement uses
    moments of order at most three; the fourth-moment constraint is checked
    separately by ``four_rater_constraints``.

    Under ``rater_1_informative`` the triple (2, 3, 4) fixes its own first
    rater, G2, as informative; the global convention ``delta_1 > 0`` needs
    ``sign(delta_2) = sign(c_12)``, so that triple's label-switched solution is
    used when ``c_12 < 0``."""

    fits = {}
    for triple in TRIPLES4:
        (drop,) = set(range(1, 5)) - set(triple)
        fits[triple] = dawid_skene_three_raters(table.triple(drop), convention, bits)
    out = {"convention": convention, "triple_fits": fits,
           "degrees_of_freedom_left": DEGREES_OF_FREEDOM["four_rater_free_cell_probabilities"]
           - DEGREES_OF_FREEDOM["four_rater_parameters"]}
    bad = [f["status"] for f in fits.values() if f["status"] not in ("exact", "bracketed")]
    if bad:
        out["status"] = bad[0]
        return out
    oriented = {triple: f["solution"] for triple, f in fits.items()}
    if convention == "rater_1_informative" and fits[(1, 2, 3)]["moments"]["covariances"][(1, 2)] < 0:
        oriented[(2, 3, 4)] = fits[(2, 3, 4)]["alternative"]
    prior, ok = _merge_point([s["prior"] for s in oriented.values()])
    solution = {"prior": prior, "false_negatives": {}, "false_positives": {}, "deltas": {}}
    for i in range(1, 5):
        for key in ("false_negatives", "false_positives", "deltas"):
            values = [s[key][triple.index(i) + 1] for triple, s in oriented.items() if i in triple]
            merged, agree = _merge_point(values)
            solution[key][i] = merged
            ok = ok and agree
    exact = all(f["status"] == "exact" for f in fits.values())
    out.update({"status": "inconsistent" if not ok else "exact" if exact else "bracketed",
                "solution": solution, "triples_agree": ok})
    if ok:
        flat = [solution["prior"]] + list(solution["false_negatives"].values()) + list(solution["false_positives"].values())
        out["in_range"] = all((0 <= v <= 1) if not isinstance(v, tuple) else (0 <= v[0] and v[1] <= 1) for v in flat)
    return out


def four_rater_constraints(table: FourRaterTable, convention: str = "all_informative",
                           bits: int = ROOT_BITS) -> dict[str, object]:
    """The exact test.  Among tables with every ``c_ij != 0``, a table is the
    image of a four-rater model (every ``delta_i > 0`` under
    ``all_informative``; ``delta_1 > 0`` under ``rater_1_informative``) iff the
    six residuals vanish and the triple fits exist (``R^2 > 0``, convention
    met) with the nine implied parameters in ``[0, 1]``.  Proof of the
    converse: the fifteen centred moments are coordinates on the simplex
    (Moebius inversion, then a triangular polynomial change), so they
    determine the table; the triple-(1, 2, 3) fit reproduces ``p_1, p_2, p_3,
    c_12, c_13, c_23, k_123``; ``delta_4 = c_14 / (u delta_1)`` and ``p_4`` fix
    rater 4; then the tetrads give ``c_24 = c_14 c_23 / c_13 = u delta_2
    delta_4`` and ``c_34``, the three ratio equalities ``k_124, k_134, k_234``,
    and the fourth-moment equality ``k_1234 = c_12 c_34 + k_123 k_124 / c_12 =
    u (1 - 3u) prod delta``.  Agreement of the four triple fits then follows
    and is computed as a cross-check; when the fit is exact the table is also
    rebuilt cell by cell (``reproduces_table``)."""

    moments = four_rater_moments(table)
    residuals = four_rater_residuals(moments)
    cov = moments["covariances"]
    identifiable = all(c != 0 for c in cov.values())
    equalities = all(r == 0 for r in residuals.values())
    fit = dawid_skene_four_raters(table, convention, bits)
    in_range = fit.get("in_range")
    reproduces = None
    if fit["status"] == "exact" and in_range:
        s = fit["solution"]
        rebuilt = four_rater_model(s["prior"], tuple(s["false_negatives"][i] for i in range(1, 5)),
                                   tuple(s["false_positives"][i] for i in range(1, 5)))
        reproduces = all(rebuilt.cells[c] * table.total == table.cells[c] for c in CELLS4)
    passes = (equalities and identifiable and fit["status"] in ("exact", "bracketed") and bool(in_range)
              and reproduces is not False)
    return {"moments": moments, "residuals": residuals, "equalities_hold": equalities,
            "identifiable": identifiable, "fit": fit, "in_range": in_range,
            "reproduces_table": reproduces, "passes": passes,
            "constraint_count": len(CONSTRAINTS4)}


def copy_grader_table4(prior, false_negatives, false_positives, copy_rate) -> FourRaterTable:
    """Four raters where G2 copies G1 with probability ``rho`` and otherwise
    labels independently at its own rates.  Given ``Y``, ``X_2`` stays
    independent of ``X_3, X_4``, with effective rates ``rho (alpha_1, beta_1) +
    (1 - rho)(alpha_2, beta_2)``; only the pair (1, 2) is dependent."""

    prior, rho = _probability(prior, "prior"), _probability(copy_rate, "copy_rate")
    alphas, betas = _four(false_negatives, "false_negatives"), _four(false_positives, "false_positives")
    sens = tuple(1 - a for a in alphas)
    cells = {}
    for cell in CELLS4:
        weight = Q(0)
        for y in (0, 1):
            w = prior if y else 1 - prior
            for i in (0, 2, 3):
                hit = sens[i] if y else betas[i]
                w *= hit if cell[i] == 1 else 1 - hit
            own = sens[1] if y else betas[1]
            w *= rho * (1 if cell[1] == cell[0] else 0) + (1 - rho) * (own if cell[1] == 1 else 1 - own)
            weight += w
        cells[cell] = weight
    return FourRaterTable(cells)


def copy_grader_tetrad_residual(prior, false_negatives, false_positives, copy_rate) -> Q:
    """Closed form of the tetrad residual ``c_12 c_34 - c_13 c_24`` (and of
    ``c_12 c_34 - c_14 c_23``) under copying: ``rho V_1 c_34`` with ``V_1 =
    pi alpha_1 (1 - alpha_1) + (1 - pi) beta_1 (1 - beta_1)`` (the mean
    conditional variance of G1's label) and ``c_34 = u delta_3 delta_4``.
    Proof: ``E[X_1 X_2 | Y] = rho E[X_1 | Y] + (1 - rho) E[X_1 | Y] E[X_2' | Y]``
    exceeds the conditionally independent value ``E[X_1 | Y] E[X_2 | Y]`` by
    ``rho Var(X_1 | Y)``, so ``c_12 = u delta_1 delta_2~ + rho V_1`` while
    ``c_13, c_24, c_34`` keep their product form; the tetrad ``c_13 c_24 -
    c_14 c_23`` is unaffected.  Any ``rho > 0`` is detected whenever ``V_1 >
    0`` (G1 imperfect on a class of positive prior), ``0 < pi < 1`` and
    ``delta_3 delta_4 != 0`` -- at a balanced prior too, where the symmetric
    three-rater check is vacuous.  The odd product ``c_12 c_34`` names the
    split ``{1, 2 | 3, 4}``, not which side of it is dependent."""

    prior, rho = _probability(prior, "prior"), _probability(copy_rate, "copy_rate")
    alphas, betas = _four(false_negatives, "false_negatives"), _four(false_positives, "false_positives")
    u = prior * (1 - prior)
    v1 = prior * alphas[0] * (1 - alphas[0]) + (1 - prior) * betas[0] * (1 - betas[0])
    c34 = u * (1 - alphas[2] - betas[2]) * (1 - alphas[3] - betas[3])
    return rho * v1 * c34


# --- 7. a joint statement for (eta_1, eps_1) ---------------------------------

def agreement_counts(record: RecordTable) -> dict[str, object]:
    """Integer agreement counts ``N_12, N_13, N_23`` (G1-G2, G1-C, G2-C) of
    the record's label table.  They come from the four agreement-pattern
    counts ``(k_all, k_12, k_13, k_23)``, ``N_ij = k_all + k_ij``; when the
    cells are expected rather than observed counts the pattern counts are
    rounded by largest remainder (ties in the order all, 12, 13, 23), which
    keeps the total and hence the parity ``N_12 + N_13 + N_23 = m + 2 k_all``
    of every realisable observation.  (Rounding the three ``N`` separately can
    break it: at ``m = 742`` it gives 549, 549, 505, which no item table has.)"""

    labels = record.label_table()
    if labels.total.denominator != 1:
        raise ValueError("agreement counts need an integer total")
    m = int(labels.total)
    exact = {name: Q(0) for name in PATTERNS}
    for a, b, c in CELLS3:
        key = "all" if a == b == c else (1, 2) if a == b else (1, 3) if a == c else (2, 3)
        exact[key] += labels.cells[(a, b, c)]
    floors = {name: int(v.__floor__()) for name, v in exact.items()}
    deficit = m - sum(floors.values())
    order = sorted(PATTERNS, key=lambda name: (-(exact[name] - floors[name]), PATTERNS.index(name)))
    patterns = {name: floors[name] + (1 if name in order[:deficit] else 0) for name in PATTERNS}
    counts = {pair: patterns["all"] + patterns[pair] for pair in PAIRS}
    return {"size": m, "patterns": patterns, "counts": counts,
            "rounded": any(Q(patterns[name]) != exact[name] for name in PATTERNS)}


def observed_square(size: int, counts: dict) -> object:
    """The observed ``S_hat = kappa_12 kappa_13 / kappa_23`` from the counts, or
    the class ``"sign"`` (some ``kappa_hat <= 0``) or ``"range"`` (``S_hat > 1``).
    The counts must be realisable: ``k_all = (N_12 + N_13 + N_23 - m) / 2`` a
    nonnegative integer and every ``k_ij = N_ij - k_all >= 0``."""

    m = _size(size)
    if not isinstance(counts, dict) or set(counts) != set(PAIRS):
        raise ValueError("counts must map the three pairs to agreement counts")
    kappas = {}
    for pair in PAIRS:
        n = counts[pair]
        if type(n) is not int or not 0 <= n <= m:
            raise ValueError("counts must be integers between 0 and size")
        kappas[pair] = Q(2 * n - m, m)
    twice_all = sum(counts.values()) - m
    if twice_all < 0 or twice_all % 2 or any(counts[pair] < twice_all // 2 for pair in PAIRS):
        raise ValueError("no item table has these agreement counts (parity or pattern counts)")
    if any(k <= 0 for k in kappas.values()):
        return "sign"
    square = kappas[(1, 2)] * kappas[(1, 3)] / kappas[(2, 3)]
    return "range" if square > 1 else square


def _threshold(rest: int, sigma: int, rhs: int, den: int, strict: bool) -> tuple[int, int] | None:
    """The ``k_12`` tails where ``a b <= C`` (or ``< C``), as ``(K_lo, K_hi)``:
    ``k_12 <= K_lo`` or ``k_12 >= K_hi``; ``None`` when every ``k_12`` qualifies.
    With ``a + b = sigma`` and ``a - b = 4 k_12 - 2 rest``: ``a b = (sigma^2 -
    (a - b)^2) / 4 <= C`` iff ``den (a - b)^2 >= den sigma^2 - 4 den C = rhs``."""

    if rhs < 0 or (rhs == 0 and not strict):
        return None
    y = rhs // den + 1 if strict else (rhs + den - 1) // den
    q = isqrt(y - 1) + 1
    return (2 * rest - q) // 4, -((-(2 * rest + q)) // 4)


def square_tail_law(size, errors, observed, thresholds=()) -> dict[str, object]:
    """Exact tails of the extended square ``S~`` under the four-pattern
    multinomial, in ``O(m^2)`` big-integer products instead of the ``C(m+3, 3)``
    terms of ``sampling_law``.  ``S~`` orders sign failures (some ``kappa_hat <=
    0``) below every defined value and range failures (``S_hat > 1``) above.

    Reduction: ``d = 2 N_23 - m = m - 2 rest`` with ``rest = k_12 + k_13``
    depends on ``rest`` only; given ``rest`` and ``k_0``, ``a + b`` is fixed and
    ``a b <= C`` is a pair of tails in ``k_12`` (``_threshold``), so the sum over
    ``k_12`` is a difference of prefix sums of the inner binomial terms, and
    the ``k_0`` with the same tails share one product.  Returns, over the
    common denominator ``D^m``, ``P[S~ <= s]``, ``P[S~ >= s]``, ``P[S~ = s]``,
    ``P[sign]``, ``P[range]`` and the two-sided ``p = min(1, 2 min(lower,
    upper))``; also ``P[S~ <= t]`` for each extra threshold ``t``."""

    m, errors = _size(size), _three(errors, "errors")
    if isinstance(observed, str):
        if observed not in ("sign", "range"):
            raise ValueError("observed must be a square in [0, 1], 'sign' or 'range'")
        s = None
    else:
        s = _as_q(observed, "observed")
        if not 0 <= s <= 1:
            raise ValueError("observed must be a square in [0, 1], 'sign' or 'range'")
    extra = tuple(_probability(t, "threshold") for t in thresholds)
    targets = ([] if s is None else [s]) + list(extra) + [Q(1)]
    n, den = _pattern_integers(errors)
    n0, n12, n13, n23 = n["all"], n[(1, 2)], n[(1, 3)], n[(2, 3)]
    g_in = gcd(n12, n13) or 1
    a12, a13 = n12 // g_in, n13 // g_in
    w_sign = w_def = 0
    w_le = [0] * len(targets)
    w_lt = [0] * len(targets)
    total = 0
    for rest in range(m + 1):
        outer_total = comb(m, rest) * (n12 + n13) ** rest * (n0 + n23) ** (m - rest)
        total += outer_total
        if 2 * rest >= m:
            w_sign += outer_total
            continue
        d = m - 2 * rest
        # inner binomial terms over k_12 and their prefix sums
        inner = [0] * (rest + 1)
        for k in range(rest + 1):
            inner[k] = comb(rest, k) * a12 ** k * a13 ** (rest - k)
        pre = [0] * (rest + 2)
        for k in range(rest + 1):
            pre[k + 1] = pre[k] + inner[k]

        def interval(lo: int, hi: int) -> int:
            lo, hi = max(lo, 0), min(hi, rest)
            return pre[hi + 1] - pre[lo] if lo <= hi else 0

        # outer weights over k_0 (k_23 = m - rest - k_0)
        span = m - rest
        outer = [0] * (span + 1)
        if n23 == 0 or n0 == 0:
            for k0 in range(span + 1):
                outer[k0] = comb(span, k0) * n0 ** k0 * n23 ** (span - k0)
        else:
            outer[0] = n23 ** span
            for k0 in range(span):
                outer[k0 + 1] = outer[k0] * (span - k0) * n0 // ((k0 + 1) * n23)
        groups_def: dict = {}
        groups_le = [dict() for _ in targets]
        groups_diff = [dict() for _ in targets]  # k_0 whose strict and non-strict tails differ
        for k0 in range(span + 1):
            t = m - 2 * k0
            g = max(0, t // 2 + 1)
            if 2 * g > rest:
                continue
            w = outer[k0]
            groups_def[g] = groups_def.get(g, 0) + w
            sigma = 2 * (2 * k0 + rest - m)
            for idx, target in enumerate(targets):
                rhs = target.denominator * sigma * sigma - 4 * target.numerator * m * d
                key_le = _threshold(rest, sigma, rhs, target.denominator, False)
                key_lt = _threshold(rest, sigma, rhs, target.denominator, True)
                groups_le[idx][(g, key_le)] = groups_le[idx].get((g, key_le), 0) + w
                if key_lt != key_le:
                    groups_diff[idx][(g, key_le, key_lt)] = groups_diff[idx].get((g, key_le, key_lt), 0) + w
        scale = comb(m, rest) * g_in ** rest
        row_def = sum(w * interval(g, rest - g) for g, w in groups_def.items())
        w_def += scale * row_def

        def tail(g: int, key) -> int:
            if key is None:
                return interval(g, rest - g)
            k_lo, k_hi = key
            return interval(g, min(k_lo, rest - g)) + interval(max(k_hi, g), rest - g)

        for idx in range(len(targets)):
            row_le = sum(w * tail(g, key) for (g, key), w in groups_le[idx].items())
            row_diff = sum(w * (tail(g, key_le) - tail(g, key_lt))
                           for (g, key_le, key_lt), w in groups_diff[idx].items())
            w_le[idx] += scale * row_le
            w_lt[idx] += scale * (row_le - row_diff)
    if total != den ** m:
        raise AssertionError("the multinomial weights do not sum to D^m")
    if w_sign > total - w_def:
        raise AssertionError("the d <= 0 rows exceed the sign-failure mass")
    p_def = Q(w_def, total)
    p_sign = 1 - p_def  # d <= 0 rows plus a <= 0 or b <= 0 inside the d > 0 rows
    p_range = p_def - Q(w_le[-1], total)
    out = {"size": m, "errors": errors, "observed": observed, "p_sign": p_sign, "p_defined_sign": p_def,
           "p_range": p_range, "p_undefined": p_sign + p_range, "method": "O(m^2) tails"}
    if s is None:
        lower = p_sign if observed == "sign" else Q(1)
        upper = Q(1) if observed == "sign" else p_range
        equal = p_sign if observed == "sign" else p_range
    else:
        lower = p_sign + Q(w_le[0], total)
        upper = p_def - Q(w_lt[0], total)
        equal = Q(w_le[0] - w_lt[0], total)
    out.update({"p_lower": lower, "p_upper": upper, "p_equal": equal,
                "p_two_sided": min(Q(1), 2 * min(lower, upper)),
                "extra_lower": {t: p_sign + Q(w_le[(s is not None) + i], total) for i, t in enumerate(extra)}})
    return out


TAIL_BITS = 160   # fixed-point scale of the bracketed tails: integers count units of 2^-160
TAIL_CUT = 128    # binomial terms below 2^-128 are bounded in bulk instead of summed


def _binomial_window(n: int, num: int, den: int, bits: int = TAIL_BITS, cut: int = TAIL_CUT) -> dict[str, object]:
    """Integer bounds ``lo_k <= 2^bits t_k <= hi_k`` on the ``Bin(n, num/den)``
    pmf over a window ``[start, start + len(lo))`` around the mode, and an
    integer ``outside >= 2^bits * (mass outside the window)``.

    The mode term ``M = floor((n + 1) num / den)`` is computed exactly and
    rounded down and up once.  Moving away from the mode the ratios
    ``t_{k+1}/t_k = (n - k) num / ((k + 1)(den - num))`` (for ``k >= M``) and
    ``t_{k-1}/t_k = k (den - num) / ((n - k + 1) num)`` (for ``k <= M``) are at
    most one; each step rounds the lower chain down and the upper chain up,
    so both bounds hold by induction and the rounding loss stays below one
    unit per step.  A chain stops at the first ``hi < 2^(bits - cut)``; the
    terms beyond it decrease, so ``count * hi`` bounds their mass."""

    one = 1 << bits
    if n == 0 or num == 0:
        return {"start": 0, "lo": [one], "hi": [one], "outside": 0}
    if num == den:
        return {"start": n, "lo": [one], "hi": [one], "outside": 0}
    rest = den - num
    mode = (n + 1) * num // den
    q, r = divmod((comb(n, mode) * num ** mode * rest ** (n - mode)) << bits, den ** n)
    lo_mode, hi_mode = q, q + (1 if r else 0)
    floor_cut = 1 << (bits - cut)
    outside = 0
    up_lo, up_hi = [], []
    lo, hi, k = lo_mode, hi_mode, mode
    while k < n:
        a, b = (n - k) * num, (k + 1) * rest
        lo, hi, k = lo * a // b, -((-hi * a) // b), k + 1
        if hi < floor_cut:
            outside += (n - k + 1) * hi
            break
        up_lo.append(lo)
        up_hi.append(hi)
    down_lo, down_hi = [], []
    lo, hi, k = lo_mode, hi_mode, mode
    while k > 0:
        a, b = k * rest, (n - k + 1) * num
        lo, hi, k = lo * a // b, -((-hi * a) // b), k - 1
        if hi < floor_cut:
            outside += (k + 1) * hi
            break
        down_lo.append(lo)
        down_hi.append(hi)
    return {"start": mode - len(down_lo), "lo": down_lo[::-1] + [lo_mode] + up_lo,
            "hi": down_hi[::-1] + [hi_mode] + up_hi, "outside": outside}


def square_tail_bracket(size, errors, observed, bits: int = TAIL_BITS, cut: int = TAIL_CUT) -> dict[str, object]:
    """Rigorous rational brackets on the tails of ``square_tail_law`` in
    ``O(m^2)`` fixed-point integer operations, windowed to ``O(m)`` terms per
    row.

    The four-pattern multinomial factors as ``rest ~ Bin(m, q_12 + q_13)``,
    then independently ``k_all ~ Bin(m - rest, q_all / (q_all + q_23))`` and
    ``k_12 ~ Bin(rest, q_12 / (q_12 + q_13))``.  Each factor is bounded by
    ``_binomial_window``; products and sums of nonnegative lower (upper)
    bounds are lower (upper) bounds, the mass outside a window enters the
    upper bound only, and every inner sum is capped at one.  So
    ``P[defined]``, ``P[defined, S_hat <= s]`` and ``P[defined, S_hat < s]``
    are bracketed exactly as integers over ``2^(3 bits)``, and with them the
    lower, upper and two-sided p-values.  No floating point; the width is
    reported and is below ``2^-90`` at every size used here."""

    m, errors = _size(size), _three(errors, "errors")
    if isinstance(observed, str):
        if observed not in ("sign", "range"):
            raise ValueError("observed must be a square in [0, 1], 'sign' or 'range'")
        s = None
    else:
        s = _as_q(observed, "observed")
        if not 0 <= s <= 1:
            raise ValueError("observed must be a square in [0, 1], 'sign' or 'range'")
    if type(bits) is not int or type(cut) is not int or not 0 < cut < bits:
        raise ValueError("need integers 0 < cut < bits")
    target = s if s is not None else (Q(1) if observed == "range" else None)
    n, den = _pattern_integers(errors)
    n0, n12, n13, n23 = n["all"], n[(1, 2)], n[(1, 3)], n[(2, 3)]
    one = 1 << bits
    outer = _binomial_window(m, n12 + n13, den, bits, cut)
    acc = {key: 0 for key in ("def_lo", "def_hi", "le_lo", "le_hi", "lt_lo", "lt_hi")}
    for index, (a_lo, a_hi) in enumerate(zip(outer["lo"], outer["hi"])):
        rest = outer["start"] + index
        if 2 * rest >= m:
            continue
        d = m - 2 * rest
        middle = _binomial_window(m - rest, n0, n0 + n23, bits, cut)
        inner = _binomial_window(rest, n12, n12 + n13, bits, cut)
        c_start, c_lo, c_hi, c_out = inner["start"], inner["lo"], inner["hi"], inner["outside"]
        c_end = c_start + len(c_lo) - 1
        pre_lo, pre_hi = [0], [0]
        for x, y in zip(c_lo, c_hi):
            pre_lo.append(pre_lo[-1] + x)
            pre_hi.append(pre_hi[-1] + y)

        def interval(lo: int, hi: int) -> tuple[int, int]:
            lo, hi = max(lo, 0), min(hi, rest)
            if lo > hi:
                return 0, 0
            i0, i1 = max(lo, c_start) - c_start, min(hi, c_end) - c_start
            low, high = (pre_lo[i1 + 1] - pre_lo[i0], pre_hi[i1 + 1] - pre_hi[i0]) if i0 <= i1 else (0, 0)
            if lo < c_start or hi > c_end:
                high += c_out
            return low, min(high, one)

        def tail(g: int, key) -> tuple[int, int]:
            if key is None:
                return interval(g, rest - g)
            first, second = interval(g, min(key[0], rest - g)), interval(max(key[1], g), rest - g)
            return first[0] + second[0], min(first[1] + second[1], one)

        row = {key: 0 for key in acc}
        for offset, (b_lo, b_hi) in enumerate(zip(middle["lo"], middle["hi"])):
            k0 = middle["start"] + offset
            g = max(0, (m - 2 * k0) // 2 + 1)
            if 2 * g > rest:
                continue
            low, high = interval(g, rest - g)
            row["def_lo"] += b_lo * low
            row["def_hi"] += b_hi * high
            if target is None:
                continue
            sigma = 2 * (2 * k0 + rest - m)
            rhs = target.denominator * sigma * sigma - 4 * target.numerator * m * d
            for name, strict in (("le", False), ("lt", True)):
                low, high = tail(g, _threshold(rest, sigma, rhs, target.denominator, strict))
                row[name + "_lo"] += b_lo * low
                row[name + "_hi"] += b_hi * high
        for key in ("def_hi", "le_hi", "lt_hi"):
            row[key] += middle["outside"] * one
        for key in acc:
            acc[key] += (a_lo if key.endswith("_lo") else a_hi) * row[key]
    for key in ("def_hi", "le_hi", "lt_hi"):
        acc[key] += outer["outside"] * one * one
    scale = one ** 3

    def clip(value: int) -> Q:
        return min(max(Q(value, scale), Q(0)), Q(1))

    p_def = (clip(acc["def_lo"]), clip(acc["def_hi"]))
    if observed == "sign":
        lower, upper = (clip(scale - acc["def_hi"]), clip(scale - acc["def_lo"])), (Q(1), Q(1))
    elif observed == "range":
        lower, upper = (Q(1), Q(1)), (clip(acc["def_lo"] - acc["le_hi"]), clip(acc["def_hi"] - acc["le_lo"]))
    else:
        lower = (clip(scale - acc["def_hi"] + acc["le_lo"]), clip(scale - acc["def_lo"] + acc["le_hi"]))
        upper = (clip(acc["def_lo"] - acc["lt_hi"]), clip(acc["def_hi"] - acc["lt_lo"]))
    two_sided = tuple(min(Q(1), 2 * min(lower[i], upper[i])) for i in (0, 1))
    return {"size": m, "errors": errors, "observed": observed, "bits": bits, "cut": cut,
            "p_defined": p_def, "p_lower": lower, "p_upper": upper, "p_two_sided": two_sided,
            "width": two_sided[1] - two_sided[0], "method": "fixed-point bracket"}


def square_test(args) -> dict[str, object]:
    """Decide ``p >= level`` for the two-sided square test exactly: by the
    bracket when it lies on one side of ``level``, else by the exact law.
    ``args = (size, errors, observed, level)`` (one tuple, for a process pool)."""

    size, errors, observed, level = args
    bracket = square_tail_bracket(size, errors, observed)
    low, high = bracket["p_two_sided"]
    out = {"p_bracket": (low, high), "width": bracket["width"], "p_exact": None}
    if low >= level:
        out.update({"retained": True, "decided_by": "bracket"})
    elif high < level:
        out.update({"retained": False, "decided_by": "bracket"})
    else:
        exact = square_tail_law(size, errors, observed)["p_two_sided"]
        out.update({"retained": exact >= level, "decided_by": "exact law", "p_exact": exact})
    return out


def eta_confidence_set(size, counts, eta2, accuracy, alpha, grid, use_square_test: bool = True,
                       resolution=RESOLUTION, workers: int = 1) -> dict[str, object]:
    """Step 1 of the joint statement: the grid points ``eta_0`` not rejected
    by (a) the one-sided disagreement bound (``eta_0 <= 1 - A_L`` from
    ``N_12`` alone; no plug-in) and, when asked, (b) the two-sided test of the
    observed ``S_hat`` under ``eta_1 = eta_0`` with ``(eta_2, a)`` at the
    plug-in values, ``p = min(1, 2 min(P[S~ <= s], P[S~ >= s]))`` under the
    four-pattern law, decided exactly (``square_test``).  Each test runs at
    level ``alpha / 2`` when both are used (``alpha`` when only (a) is): if
    the true ``eta_1`` is a grid point, it is retained with probability at
    least ``1 - alpha``, exactly for (a) and under the plug-in for (b)."""

    m, alpha = _size(size), _probability(alpha, "alpha")
    if not 0 < alpha < 1:
        raise ValueError("alpha must lie strictly inside (0, 1)")
    eta2, accuracy = _probability(eta2, "eta2"), _probability(accuracy, "accuracy")
    if not isinstance(grid, (tuple, list)):
        raise ValueError("grid must be a nonempty list of rationals in [0, 1/2)")
    points = sorted({_probability(e, "grid point") for e in grid})
    if not points or any(e >= HALF for e in points):
        raise ValueError("grid must be a nonempty list of rationals in [0, 1/2)")
    observed = observed_square(m, counts)
    level = alpha / 2 if use_square_test else alpha
    bound = disagreement_bound(m, counts[(1, 2)], level, resolution)
    rows = [{"eta0": eta0, "passes_disagreement_bound": eta0 <= bound["eta_upper_bound"], "square_test": None}
            for eta0 in points]
    for row in rows:
        row["retained"] = row["passes_disagreement_bound"]
    if use_square_test:
        todo = [row for row in rows if row["retained"]]
        jobs = [(m, (row["eta0"], eta2, 1 - accuracy), observed, level) for row in todo]
        if workers > 1 and len(jobs) > 1:
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(max_workers=min(workers, len(jobs))) as pool:
                results = list(pool.map(square_test, jobs))
        else:
            results = [square_test(job) for job in jobs]
        for row, result in zip(todo, results):
            row["square_test"] = result
            row["retained"] = result["retained"]
    retained = [r["eta0"] for r in rows if r["retained"]]
    tested = [r["square_test"] for r in rows if r["square_test"] is not None]
    return {"size": m, "counts": dict(counts), "observed_square": observed, "alpha": alpha, "level_per_test": level,
            "tests_used": ("disagreement_bound", "square_test") if use_square_test else ("disagreement_bound",),
            "plug_in": {"eta2": eta2, "accuracy": accuracy}, "disagreement_bound": bound, "rows": rows,
            "retained": retained, "grid": points,
            "is_grid_interval": all(points.index(b) - points.index(a) == 1 for a, b in zip(retained, retained[1:])),
            "max_bracket_width": max((t["width"] for t in tested), default=None),
            "exact_fallbacks": sum(1 for t in tested if t["decided_by"] == "exact law")}


def _plug_in(bracket: dict) -> tuple[Q, bool]:
    return (bracket["exact"], False) if bracket["exact"] is not None else (bracket["lower"], True)


def clamped_inversion(measured_accuracy, measured_error, wrong_wrong_rate, eta) -> dict[str, object] | None:
    """The judge note's inversion at ``eta`` with every rate clamped into its
    feasible range: ``eps`` into ``[0, 1]``, ``eps_1`` into the
    ``shared_error_bounds`` at ``(a, eps)``.  ``None`` when no controller of
    accuracy strictly inside ``(0, 1)`` is implied: ``eta >= 1 - a'`` (never
    wrong) or ``eta >= a'`` (never right).  A clamp means the measured rates
    are not the image of any population at this ``eta``; it is flagged and
    counted, not hidden."""

    a_m, e_m, w = (_probability(measured_accuracy, "measured_accuracy"),
                   _probability(measured_error, "measured_error"), _probability(wrong_wrong_rate, "wrong_wrong_rate"))
    eta = _probability(eta, "eta")
    if not eta < HALF:
        raise ValueError("eta must lie below one half")
    if not 1 - a_m - eta > 0 or not a_m - eta > 0:
        return None
    raw_a, raw_e = (a_m - eta) / (1 - 2 * eta), (e_m - eta) / (1 - 2 * eta)
    raw_eps1 = inverted_eps1(a_m, e_m, w, eta)
    a, e = min(max(raw_a, Q(0)), Q(1)), min(max(raw_e, Q(0)), Q(1))
    low, high = shared_error_bounds(a, e)
    eps1 = min(max(raw_eps1, low), high)
    return {"accuracy": a, "judge_error": e, "eps1": eps1, "raw": {"accuracy": raw_a, "judge_error": raw_e, "eps1": raw_eps1},
            "clamped": a != raw_a or e != raw_e or eps1 != raw_eps1}


def joint_statement(record: RecordTable, alpha=Q(1, 20), grid=(), declared_judge_error=None,
                    use_square_test: bool = True, eta_set: dict | None = None,
                    resolution=RESOLUTION, workers: int = 1) -> dict[str, object]:
    """A conservative joint statement for ``(eta_1, eps_1)`` at level ``alpha``.

    (1) ``eta_confidence_set`` on the record's agreement counts; (2) for each
    retained ``eta_0``, the judge note's inversion at ``eta_0``, the corrected
    counts rounded half-up, the exact ceiling and independence tests and the
    two-sided level-``alpha`` Clopper-Pearson bracket for ``eps_1``; (3) with
    probability at least ``1 - 2 alpha`` (Bonferroni over the two steps)
    ``eta_1`` lies in the set and ``eps_1`` in the union of the brackets.

    Plug-in: step (1b) fixes ``eta_2`` and ``a`` at their estimates (the lower
    end of each error-rate bracket when not exact); step (2) treats the
    corrected counts as a binomial sample at the inverted rates, the same
    assumption as the pipeline's tests.  The sampling law of ``eps1_hat``
    itself is not derived.  A retained ``eta_0`` whose inversion implies no
    controller strictly inside ``(0, 1)`` leaves the ``eps_1`` range
    undetermined.  The statement is withheld when the symmetric constraint
    check fails: ``eta_1`` and the inversion presuppose that model."""

    alpha = _probability(alpha, "alpha")
    if not 0 < alpha < HALF:
        raise ValueError("alpha must lie strictly inside (0, 1/2)")
    declared = None if declared_judge_error is None else _probability(declared_judge_error, "declared_judge_error")
    if not isinstance(record, RecordTable):
        raise ValueError("record must be a RecordTable")
    if record.total.denominator != 1:
        raise ValueError("the joint statement needs an integer total")
    size = int(record.total)
    calibration = calibrate(record, declared, alpha, resolution)
    measured = calibration["measured"]
    out = {"size": size, "alpha": alpha, "coverage": 1 - 2 * alpha, "calibration_status": calibration["status"],
           "constraints_pass": calibration["constraints"]["passes"], "measured": measured,
           "square_test_used": False}
    if not calibration["identifiable"]:
        out.update({"status": "not_identified", "eta_set": None, "eps1_range": None})
        return out
    if not calibration["constraints"]["passes"]:
        out.update({"status": "withheld_constraints_fail", "eta_set": None, "eps1_range": None,
                    "residuals": calibration["constraints"]["residuals"]})
        return out
    eta2, eta2_bracketed = _plug_in(calibration["eta2"])
    accuracy, accuracy_bracketed = (calibration["accuracy_from_identity"]["exact"], False)
    if accuracy is None:
        accuracy, accuracy_bracketed = calibration["accuracy_from_identity"]["upper"], True
    counts = agreement_counts(record)
    if eta_set is None:
        eta_set = eta_confidence_set(size, counts["counts"], eta2, accuracy, alpha, grid,
                                     use_square_test, resolution, workers)
    elif eta_set["counts"] != counts["counts"] or eta_set["size"] != size:
        raise ValueError("the supplied eta set was computed from other agreement counts")
    out.update({"agreement_counts": counts, "plug_in_bracketed": eta2_bracketed or accuracy_bracketed,
                "eta_set": eta_set, "square_test_used": "square_test" in eta_set["tests_used"]})
    if measured["table"] is None:
        out.update({"status": "no_judge_table", "eps1_range": None})
        return out
    inversions = []
    undetermined = clamped = 0
    for eta0 in eta_set["retained"]:
        row = {"eta0": eta0}
        rates = clamped_inversion(measured["accuracy"], measured["judge_error"], measured["wrong_wrong_rate"], eta0)
        if rates is None:
            row.update({"feasible": False, "reason": "no controller with accuracy inside (0, 1) at this eta0"})
            undetermined += 1
            inversions.append(row)
            continue
        expected = expected_table(size, rates["accuracy"], rates["judge_error"], rates["eps1"])
        table, changed = rounded_table(expected)
        error = declared if declared is not None else rates["judge_error"]
        tests = _judge_tests(table, error, alpha, declared is None)
        clamped += rates["clamped"]
        row.update({"feasible": True, "recovered": rates, "corrected_table": table,
                    "rounding_changed_a_cell": changed, "tests": tests})
        if "ceiling_p" in tests:
            cp = clopper_pearson_bracket(table.controller_wrong, table.wrong_wrong, alpha, resolution)
            row["eps1_bracket"] = (cp["lower"][0], cp["upper"][1])
            row["eps1_point"] = cp["point"]
        else:
            row["feasible"] = False
            undetermined += 1
        inversions.append(row)
    feasible = [r for r in inversions if r["feasible"]]
    if not eta_set["retained"]:
        status, eps1_range = "empty_set", None
    elif undetermined:
        status, eps1_range = "eps1_undetermined", None
    else:
        status = "stated"
        eps1_range = (min(r["eps1_bracket"][0] for r in feasible), max(r["eps1_bracket"][1] for r in feasible))
    stated = status == "stated"
    out.update({"status": status, "inversions": inversions, "eps1_range": eps1_range,
                "clamped_points": clamped, "undetermined_points": undetermined,
                "below_ceiling_jointly": stated and all(r["tests"]["ceiling_p"] < alpha for r in feasible)
                and eps1_range[1] < HALF,
                "above_independence_jointly": stated and all(r["tests"]["independence_p"] < alpha for r in feasible),
                "statement": (f"with probability >= {1 - 2 * alpha}: eta_1 in the retained set and eps_1 in the "
                              f"union of the level-{alpha} Clopper-Pearson brackets, under the plug-in"),
                "assumes": ("conditionally independent symmetric raters (constraint check)",
                            "step 1b: eta_2 and a fixed at their estimates",
                            "step 2: the corrected counts are a binomial sample at the inverted rates",
                            "the sampling law of eps1_hat is not derived")})
    return out


def judges_separated(independent: dict, shared: dict) -> bool:
    """Both statements made and their ``eps_1`` ranges disjoint."""

    a, b = independent.get("eps1_range"), shared.get("eps1_range")
    return a is not None and b is not None and (a[1] < b[0] or b[1] < a[0])


# --- fixtures and verification ------------------------------------------------

FIXTURE_SIZE, FIXTURE_PRIOR = 10000, Q(1, 4)
FIXTURE_ACCURACY, FIXTURE_ERROR = Q(4, 5), Q(1, 10)
FIXTURE_ETA1, FIXTURE_ETA2 = Q(1, 10), Q(1, 5)
FIXTURE_ALPHA = Q(1, 20)
JUDGES = {"independent": FIXTURE_ERROR, "maximally_shared": HALF}
SIGN_FALSIFIER = {(0, 0, 0): Q(3, 20), (1, 1, 1): Q(3, 20), (0, 1, 0): Q(3, 20), (1, 0, 1): Q(3, 20),
                  (1, 0, 0): Q(3, 20), (0, 1, 1): Q(3, 20), (0, 0, 1): Q(1, 20), (1, 1, 0): Q(1, 20)}
RANGE_FALSIFIER = {(0, 0, 0): Q(1, 4), (1, 1, 1): Q(1, 4), (0, 0, 1): Q(3, 25), (1, 1, 0): Q(3, 25),
                   (0, 1, 0): Q(3, 25), (1, 0, 1): Q(3, 25), (1, 0, 0): Q(1, 100), (0, 1, 1): Q(1, 100)}
SAMPLING_SIZES = (16, 100, 200)
TOLERANCE = Q(1, 50)
OTHER_POINTS = {"better_raters": (Q(1, 20), Q(1, 10), Q(1, 10)), "worse_raters": (Q(1, 5), Q(1, 4), Q(3, 10))}
OTHER_POINT_SIZE = 200
DS_PRIOR, DS_SIZE = Q(1, 4), 4000
DS_FALSE_NEGATIVES, DS_FALSE_POSITIVES = (Q(1, 10), Q(1, 5), Q(1, 10)), (Q(1, 5), Q(1, 10), Q(3, 10))
DS_JUDGES = {"independent": FIXTURE_ERROR, "maximally_shared": Q(2, 5)}
DS_PRIOR_GRID = (Q(1, 4), Q(1, 3), HALF, Q(7, 10))
DS_PAIR_GRID = ((Q(1, 10), Q(1, 20)), (Q(1, 5), Q(1, 10)), (Q(0), Q(1, 4)), (Q(3, 10), Q(3, 10)))
ANTI_INFORMATIVE_SECOND = (Q(3, 5), Q(3, 5))
OUTSIDE_MODEL = {(1, 0, 0): Q(7, 30), (0, 1, 0): Q(7, 30), (0, 0, 1): Q(7, 30),
                 (0, 1, 1): Q(1, 10), (1, 0, 1): Q(1, 10), (1, 1, 0): Q(1, 10)}
FOUR_PRIOR, FOUR_SIZE = Q(1, 4), 10000
FOUR_FALSE_NEGATIVES = (Q(1, 10), Q(1, 5), Q(1, 5), Q(1, 10))   # gold, second, third grader, controller
FOUR_FALSE_POSITIVES = (Q(1, 5), Q(1, 10), Q(2, 5), Q(3, 10))
FOUR_PRIOR_GRID = (Q(1, 4), Q(1, 3), HALF)
FOUR_PAIR_GRID = ((Q(1, 10), Q(1, 20)), (Q(1, 5), Q(1, 10)), (Q(3, 10), Q(3, 10)))
FOUR_COPY_RATES = (Q(1, 4), HALF, Q(1))
PLANNING_SIZE = 742
JOINT_SIZES = (PLANNING_SIZE,)
JOINT_GRID = tuple(Q(k, 100) for k in range(50))
BRACKET_CASES = ((16, (Q(1, 10), Q(1, 5), Q(1, 5)), Q(16, 25)), (16, (Q(1, 10), Q(1, 5), Q(1, 5)), "sign"),
                 (16, (Q(1, 10), Q(1, 5), Q(1, 5)), "range"), (16, (Q(1, 5), Q(1, 4), Q(3, 10)), HALF),
                 (100, (Q(1, 10), Q(1, 5), Q(1, 5)), Q(16, 25)), (100, (Q(0), Q(1, 5), Q(1, 5)), Q(9, 10)),
                 (200, (Q(3, 20), Q(1, 5), Q(1, 5)), Q(16, 25)), (200, (Q(1, 20), Q(1, 10), Q(1, 10)), Q(4, 5)),
                 (742, (Q(13, 100), Q(1, 5), Q(1, 5)), Q(31684, 49343)))


def four_rater_fixture() -> dict[str, object]:
    """The four-rater fixture, the grid checks of the six constraints and the
    two ranks, the copying grader's tetrad residual, and tables that fail."""

    table = four_rater_model(FOUR_PRIOR, FOUR_FALSE_NEGATIVES, FOUR_FALSE_POSITIVES)
    constraints = four_rater_constraints(table)
    moments = constraints["moments"]
    u = FOUR_PRIOR * (1 - FOUR_PRIOR)
    deltas = [1 - a - b for a, b in zip(FOUR_FALSE_NEGATIVES, FOUR_FALSE_POSITIVES)]
    product_delta = deltas[0] * deltas[1] * deltas[2] * deltas[3]
    closed_ok, points, ranks_ok, converse_ok, ratios_ok = True, 0, True, True, True
    for prior in FOUR_PRIOR_GRID:
        for pairs in product(FOUR_PAIR_GRID, repeat=4):
            fn, fp = tuple(p[0] for p in pairs), tuple(p[1] for p in pairs)
            grid_table = four_rater_model(prior, fn, fp)
            mom = four_rater_moments(grid_table)
            uu, dd = prior * (1 - prior), [1 - a - b for a, b in zip(fn, fp)]
            closed_ok = closed_ok and all(mom["covariances"][(i, j)] == uu * dd[i - 1] * dd[j - 1] for i, j in PAIRS4) \
                and all(mom["third_moments"][t] == uu * (1 - 2 * prior) * dd[t[0] - 1] * dd[t[1] - 1] * dd[t[2] - 1]
                        for t in TRIPLES4) \
                and mom["fourth_moment"] == uu * (1 - 3 * uu) * dd[0] * dd[1] * dd[2] * dd[3] \
                and all(r == 0 for r in four_rater_residuals(mom).values())
            ranks_ok = ranks_ok and constraint_jacobian_rank(mom) == 6 and four_rater_jacobian_rank(prior, fn, fp) == 9
            ratios_ok = ratios_ok and all(r == 0 for r in ratio_relations(mom).values())
            check = four_rater_constraints(grid_table)
            converse_ok = converse_ok and check["passes"] and check["reproduces_table"] \
                and check["fit"]["solution"]["prior"] == prior \
                and all(check["fit"]["solution"]["false_negatives"][i + 1] == fn[i]
                        and check["fit"]["solution"]["false_positives"][i + 1] == fp[i] for i in range(4))
            points += 1
    copy = {}
    for rho in FOUR_COPY_RATES:
        copied = copy_grader_table4(FOUR_PRIOR, FOUR_FALSE_NEGATIVES, FOUR_FALSE_POSITIVES, rho)
        check = four_rater_constraints(copied)
        copy[str(rho)] = {"copy_rate": rho, "constraints": check,
                          "closed_form_residual": copy_grader_tetrad_residual(FOUR_PRIOR, FOUR_FALSE_NEGATIVES,
                                                                              FOUR_FALSE_POSITIVES, rho),
                          "triple_123": check["fit"]["triple_fits"][(1, 2, 3)]}
    symmetric_errors = (FIXTURE_ETA1, FIXTURE_ETA2, Q(3, 10), 1 - FIXTURE_ACCURACY)
    symmetric_copy = {str(rho): four_rater_constraints(copy_grader_table4(FIXTURE_PRIOR, symmetric_errors,
                                                                            symmetric_errors, rho))["residuals"]
                      for rho in FOUR_COPY_RATES}
    balanced_copy = copy_grader_table4(HALF, symmetric_errors, symmetric_errors, Q(1))
    balanced_three = copy_grader_table(HALF, FIXTURE_ETA1, FIXTURE_ETA2, 1 - FIXTURE_ACCURACY, Q(1))
    perturbed_cells = dict(table.cells)
    perturbed_cells[(0, 0, 0, 1)] += Q(1, 100)
    perturbed_cells[(1, 1, 1, 0)] -= Q(1, 100)
    chance = {}
    for rater in (2, 4):
        fn = tuple(HALF if i == rater - 1 else a for i, a in enumerate(FOUR_FALSE_NEGATIVES))
        fp = tuple(HALF if i == rater - 1 else b for i, b in enumerate(FOUR_FALSE_POSITIVES))
        chance_table = four_rater_model(FOUR_PRIOR, fn, fp)
        chance[rater] = {"parameter_rank": four_rater_jacobian_rank(FOUR_PRIOR, fn, fp),
                         "constraint_rank": constraint_jacobian_rank(four_rater_moments(chance_table)),
                         "status": four_rater_constraints(chance_table)["fit"]["status"]}
    anti_fn = (FOUR_FALSE_NEGATIVES[0], ANTI_INFORMATIVE_SECOND[0]) + FOUR_FALSE_NEGATIVES[2:]
    anti_fp = (FOUR_FALSE_POSITIVES[0], ANTI_INFORMATIVE_SECOND[1]) + FOUR_FALSE_POSITIVES[2:]
    anti_table = four_rater_model(FOUR_PRIOR, anti_fn, anti_fp)
    return {"prior": FOUR_PRIOR, "false_negatives": FOUR_FALSE_NEGATIVES, "false_positives": FOUR_FALSE_POSITIVES,
            "table": table, "size": FOUR_SIZE, "counts": {c: FOUR_SIZE * w for c, w in table.cells.items()},
            "cells_integral": all((FOUR_SIZE * w).denominator == 1 for w in table.cells.values()),
            "moments": moments, "residuals": constraints["residuals"], "constraints": constraints,
            "closed_forms": {"u": u, "deltas": deltas, "tetrad": u * u * product_delta,
                             "k_123": u * (1 - 2 * FOUR_PRIOR) * deltas[0] * deltas[1] * deltas[2],
                             "k_1234": u * (1 - 3 * u) * product_delta},
            "constraint_jacobian_rank": constraint_jacobian_rank(moments),
            "parameter_jacobian_rank": four_rater_jacobian_rank(FOUR_PRIOR, FOUR_FALSE_NEGATIVES, FOUR_FALSE_POSITIVES),
            "chance_rater": chance, "degenerate_prior_rank": four_rater_jacobian_rank(
                Q(0), FOUR_FALSE_NEGATIVES, FOUR_FALSE_POSITIVES),
            "grid_points": points, "closed_forms_on_grid": closed_ok, "ranks_on_grid": ranks_ok,
            "ratio_relations_on_grid": ratios_ok, "converse_on_grid": converse_ok,
            "copy_grader": copy, "symmetric_copy_residuals": symmetric_copy,
            "copy_witness_counts": {c: FOUR_SIZE * w for c, w in copy_grader_table4(
                FOUR_PRIOR, FOUR_FALSE_NEGATIVES, FOUR_FALSE_POSITIVES, Q(1)).cells.items()},
            "balanced_prior_copy": {"four_rater_residuals": four_rater_constraints(balanced_copy)["residuals"],
                                    "closed_form": copy_grader_tetrad_residual(HALF, symmetric_errors, symmetric_errors, Q(1)),
                                    "three_rater_check": model_constraints(balanced_three)},
            "anti_informative_second": {"all_informative": four_rater_constraints(anti_table),
                                        "rater_1_informative": four_rater_constraints(anti_table, "rater_1_informative")},
            "perturbed": four_rater_constraints(FourRaterTable(perturbed_cells)),
            "degrees_of_freedom": DEGREES_OF_FREEDOM}


def joint_fixture(sizes=JOINT_SIZES, grid=JOINT_GRID, workers: int = 1) -> dict[str, object]:
    """The joint statement on the §5 record at each size (both judges share
    the label table, so the ``eta_1`` set is computed once per size); with
    the disagreement bound alone (``eps_1`` undetermined); on the asymmetric
    §7 record (withheld: the symmetric constraints fail); and the
    cross-checks of the square tails: the ``O(m^2)`` law against the label
    table enumeration at ``m = 16`` and the sampling law's undefined mass,
    and the fixed-point bracket against the exact law."""

    errors = (FIXTURE_ETA1, FIXTURE_ETA2, 1 - FIXTURE_ACCURACY)
    by_size = {}
    for m in sizes:
        judges = {}
        shared_set = None
        for name, eps1 in JUDGES.items():
            record = expected_record_table(m, FIXTURE_PRIOR, FIXTURE_ACCURACY, FIXTURE_ERROR, eps1,
                                           FIXTURE_ETA1, FIXTURE_ETA2)
            statement = joint_statement(record, FIXTURE_ALPHA, grid, FIXTURE_ERROR, True, shared_set,
                                        RESOLUTION, workers)
            shared_set = statement["eta_set"]
            judges[name] = {"eps1": eps1, "statement": {k: v for k, v in statement.items() if k != "eta_set"}}
        ind, shared = judges["independent"]["statement"], judges["maximally_shared"]["statement"]
        by_size[m] = {"judges": judges, "eta_set": shared_set,
                      "ranges_disjoint": judges_separated(ind, shared),
                      "tests_separate": ind["status"] == shared["status"] == "stated"
                      and ind["below_ceiling_jointly"] and shared["above_independence_jointly"]
                      and not ind["above_independence_jointly"] and not shared["below_ceiling_jointly"]}
    small = sizes[0]
    bound_only = joint_statement(expected_record_table(small, FIXTURE_PRIOR, FIXTURE_ACCURACY, FIXTURE_ERROR, FIXTURE_ERROR,
                                                       FIXTURE_ETA1, FIXTURE_ETA2), FIXTURE_ALPHA, grid, FIXTURE_ERROR, False)
    controller = (DS_FALSE_NEGATIVES[2], DS_FALSE_POSITIVES[2])
    gold, second = (DS_FALSE_NEGATIVES[0], DS_FALSE_POSITIVES[0]), (DS_FALSE_NEGATIVES[1], DS_FALSE_POSITIVES[1])
    asymmetric = joint_statement(expected_record_table_asymmetric(DS_SIZE, DS_PRIOR, controller, FIXTURE_ERROR,
                                                                  FIXTURE_ERROR, gold, second),
                                 FIXTURE_ALPHA, grid, FIXTURE_ERROR, True)
    laws = {m: square_tail_law(m, errors, Q(16, 25)) for m in (16, 100, 200)}
    tables16 = sampling_law_by_tables(16, errors)
    dist = tables16["square_distribution"]
    agree = True
    for s in list(dist)[:6] + [HALF, Q(16, 25), Q(1)]:
        law = square_tail_law(16, errors, s)
        agree = agree and law["p_lower"] == tables16["p_undefined_sign"] + sum((p for v, p in dist.items() if v <= s), Q(0)) \
            and law["p_upper"] == tables16["p_undefined_range"] + sum((p for v, p in dist.items() if v >= s), Q(0)) \
            and law["p_equal"] == dist.get(s, Q(0))
    contains, widths, cases = True, [], 0
    for m, errs, observed in BRACKET_CASES:
        exact, bracket = square_tail_law(m, errs, observed), square_tail_bracket(m, errs, observed)
        for key in ("p_lower", "p_upper", "p_two_sided"):
            contains = contains and bracket[key][0] <= exact[key] <= bracket[key][1]
        contains = contains and bracket["p_defined"][0] <= 1 - exact["p_sign"] <= bracket["p_defined"][1]
        widths.append(bracket["width"])
        cases += 1
    return {"sizes": tuple(sizes), "grid": tuple(grid), "by_size": by_size, "bound_only": bound_only,
            "asymmetric_record": asymmetric, "tail_laws": laws, "tails_match_label_table_enumeration_at_16": agree,
            "bracket_contains_exact": contains, "bracket_cases": cases, "bracket_max_width": max(widths)}


def three_rater_fixture() -> dict[str, object]:
    """G1, G2 and the controller's answer at the fixture rates, prior 1/4."""

    errors = (FIXTURE_ETA1, FIXTURE_ETA2, 1 - FIXTURE_ACCURACY)
    table = three_rater_model(FIXTURE_PRIOR, errors)
    kappas = pairwise_kappas(table)
    squares = polarity_squares(kappas)
    recovered = {i: error_rate_from_square(squares[i]) for i in (1, 2, 3)}
    swapped = three_rater_model(1 - FIXTURE_PRIOR, tuple(1 - e for e in errors))
    grid = [(Q(1, 2), (Q(1, 10), Q(1, 5), Q(1, 4))), (Q(1, 3), (Q(0), Q(1, 10), Q(2, 5))),
            (Q(1, 4), errors), (Q(9, 10), (Q(1, 5), Q(1, 5), Q(1, 20)))]
    factor = all(pairwise_kappas(three_rater_model(p, e))[pair] == (1 - 2 * e[pair[0] - 1]) * (1 - 2 * e[pair[1] - 1])
                 for p, e in grid for pair in PAIRS)
    return {"prior": FIXTURE_PRIOR, "errors": dict(zip(RATERS.values(), errors)), "table": table,
            "walsh": walsh_coefficients(table), "kappas": kappas, "squares": squares,
            "recovered_errors": recovered, "recovered_eta1": recovered[1], "recovered_eta2": recovered[2],
            "recovered_accuracy": 1 - recovered[3],
            "membership": {"eta1_le_1/10": error_rate_at_most(squares[1], Q(1, 10)),
                           "eta1_le_9/100": error_rate_at_most(squares[1], Q(9, 100)),
                           "eta1_le_11/100": error_rate_at_most(squares[1], Q(11, 100))},
            "bracket_exact_case": error_rate_bracket(squares[1]),
            "constraints": model_constraints(table), "jacobian_rank": model_jacobian_rank(FIXTURE_PRIOR, errors),
            "label_swap_equivalent": swapped == table, "factorization_on_grid": factor,
            "sign_falsifier": model_constraints(LabelTable(SIGN_FALSIFIER)),
            "range_falsifier": model_constraints(LabelTable(RANGE_FALSIFIER)),
            "balanced_prior_dependent": model_constraints(copy_grader_table(HALF, FIXTURE_ETA1, FIXTURE_ETA2,
                                                                            1 - FIXTURE_ACCURACY, HALF)),
            "degrees_of_freedom": DEGREES_OF_FREEDOM}


def pipeline_fixture() -> dict[str, dict[str, object]]:
    """Both judges of the signal fixture on 10000 items with two graders."""

    out = {}
    for name, eps1 in JUDGES.items():
        record = expected_record_table(FIXTURE_SIZE, FIXTURE_PRIOR, FIXTURE_ACCURACY, FIXTURE_ERROR, eps1,
                                       FIXTURE_ETA1, FIXTURE_ETA2)
        forward = gold_noise_forward(FIXTURE_ACCURACY, FIXTURE_ERROR, eps1, FIXTURE_ETA1)
        result = calibrate(record, FIXTURE_ERROR, FIXTURE_ALPHA)
        measured = result["measured"]
        displacements = {str(d): eps1_displacement(measured["accuracy"], measured["judge_error"],
                                                   measured["wrong_wrong_rate"], FIXTURE_ETA1, d)
                         for d in (Q(1, 100), Q(-1, 100), Q(1, 20))}
        direct = {str(d): inverted_eps1(measured["accuracy"], measured["judge_error"], measured["wrong_wrong_rate"],
                                        FIXTURE_ETA1 + d) - eps1 for d in (Q(1, 100), Q(-1, 100), Q(1, 20))}
        out[name] = {"eps1": eps1, "record": record, "cells_integral": all(c.denominator == 1 for c in record.cells.values()),
                     "forward_from_judge_note": forward,
                     "measured_matches_forward": (measured["accuracy"] == forward["accuracy"]
                                                  and measured["judge_error"] == forward["judge_error"]
                                                  and measured["wrong_wrong_rate"] == forward["wrong_wrong_rate"]),
                     "label_table_matches_model": record.label_table().cells == {
                         cell: FIXTURE_SIZE * w for cell, w in three_rater_model(
                             FIXTURE_PRIOR, (FIXTURE_ETA1, FIXTURE_ETA2, 1 - FIXTURE_ACCURACY)).cells.items()},
                     "calibration": result, "displacements": displacements, "direct_differences": direct}
    return out


def dependent_grader_fixture() -> dict[str, object]:
    """The independent judge with a second grader that copies G1."""

    rows = {}
    for rho in (Q(1), HALF):
        record = expected_record_table(FIXTURE_SIZE, FIXTURE_PRIOR, FIXTURE_ACCURACY, FIXTURE_ERROR, FIXTURE_ERROR,
                                       FIXTURE_ETA1, FIXTURE_ETA2, rho)
        result = calibrate(record, FIXTURE_ERROR, FIXTURE_ALPHA)
        closed = copy_grader_residual(FIXTURE_PRIOR, FIXTURE_ETA1, 1 - FIXTURE_ACCURACY, rho)
        rows[str(rho)] = {"copy_rate": rho, "record": record, "calibration": result,
                          "closed_form_residual": closed,
                          "residuals_match_closed_form": (result["constraints"]["residuals"][1] == closed
                                                          and result["constraints"]["residuals"][2] == closed
                                                          and result["constraints"]["residuals"][3] == 0),
                          "uncorrected_tests": _judge_tests(result["measured"]["table"], FIXTURE_ERROR, FIXTURE_ALPHA, False)}
    residual_grid = {str(rho): (model_constraints(copy_grader_table(FIXTURE_PRIOR, FIXTURE_ETA1, FIXTURE_ETA2,
                                                                     1 - FIXTURE_ACCURACY, rho))["residuals"][1]
                                == copy_grader_residual(FIXTURE_PRIOR, FIXTURE_ETA1, 1 - FIXTURE_ACCURACY, rho))
                     for rho in (Q(0), Q(1, 4), HALF, Q(3, 4), Q(1))}
    return {"rows": rows, "residual_closed_form_on_grid": residual_grid}


def ledger_fixture() -> dict[str, object]:
    train = tuple(f"t{i}" for i in range(8))
    sample = tuple(f"g{i}" for i in range(8))
    respected = (LoopEvent(1, "train", "item_feedback", ("t0", "t1")), LoopEvent(2, "judge_sample", "readout"))
    breached = respected + (LoopEvent(3, "judge_sample", "readout"),)
    return {"respected": measurement_ledger(train, sample, respected),
            "breached": measurement_ledger(train, sample, breached)}


LAW_KEYS = ("p_undefined_sign", "p_undefined_range", "p_exact", "p_bracketed", "p_within_tolerance",
            "square_mean", "square_variance", "root_mean_bracket")


def sampling_fixture(sizes=SAMPLING_SIZES) -> dict[str, object]:
    """The exact law of ``eta1_hat`` at the fixture rates along a ladder of
    item counts, its cross-check, the delta variance, two other parameter
    points and the disagreement bound."""

    errors = (FIXTURE_ETA1, FIXTURE_ETA2, 1 - FIXTURE_ACCURACY)
    table = three_rater_model(FIXTURE_PRIOR, errors)
    delta = delta_variance(errors)
    laws = {m: sampling_law(m, errors, TOLERANCE) for m in sizes}
    reduced16 = laws[16] if 16 in laws else sampling_law(16, errors, TOLERANCE)
    tables16 = sampling_law_by_tables(16, errors, TOLERANCE)
    planning = planning_size(errors, TOLERANCE)
    a12 = agreement_rate(table, 1, 2)
    others = {name: {"errors": e, "delta": delta_variance(e), "planning_size": planning_size(e, TOLERANCE),
                     "law": sampling_law(OTHER_POINT_SIZE, e, TOLERANCE)} for name, e in OTHER_POINTS.items()}
    return {"errors": errors, "delta": delta, "delta_from_table": delta_variance_from_table(table),
            "covariance_from_cells": agreement_covariance(table),
            "covariance_closed_form": agreement_covariance_model(errors),
            "laws": laws, "label_table_enumeration": tables16,
            "reduction_matches_tables": all(reduced16[k] == tables16[k] for k in LAW_KEYS),
            "planning_size": planning, "largest_size": max(sizes), "other_points": others,
            "prior_free": all(agreement_patterns(three_rater_model(p, errors)) == agreement_patterns(table)
                              for p in (Q(0), Q(1, 3), HALF, Q(9, 10))),
            "disagreement_bounds": {"planning_size": disagreement_bound(planning, round(planning * a12), FIXTURE_ALPHA),
                                    "ten_thousand": disagreement_bound(FIXTURE_SIZE, round(FIXTURE_SIZE * a12),
                                                                       FIXTURE_ALPHA)},
            "population_disagreement": 1 - a12}


def dawid_skene_fixture() -> dict[str, object]:
    """The asymmetric fixture, the grid round trip, the symmetric special case,
    the Jacobian rank, the copy grader absorbed, conventions and falsifiers."""

    table = dawid_skene_model(DS_PRIOR, DS_FALSE_NEGATIVES, DS_FALSE_POSITIVES)
    fit = dawid_skene_three_raters(table)
    alt = fit["alternative"]
    alt_table = dawid_skene_model(alt["prior"], tuple(alt["false_negatives"][i] for i in (1, 2, 3)),
                                  tuple(alt["false_positives"][i] for i in (1, 2, 3)))
    round_trip, points = True, 0
    for prior in DS_PRIOR_GRID:
        for pairs in product(DS_PAIR_GRID, repeat=3):
            fn, fp = tuple(p[0] for p in pairs), tuple(p[1] for p in pairs)
            found = dawid_skene_three_raters(dawid_skene_model(prior, fn, fp))
            points += 1
            round_trip = round_trip and found["status"] == "exact" and found["solution"]["prior"] == prior and all(
                found["solution"]["false_negatives"][i + 1] == fn[i] and found["solution"]["false_positives"][i + 1] == fp[i]
                for i in range(3))
    symmetric_ok = True
    for prior, errors in ((FIXTURE_PRIOR, (FIXTURE_ETA1, FIXTURE_ETA2, 1 - FIXTURE_ACCURACY)),
                          (Q(1, 3), (Q(1, 20), Q(1, 10), Q(2, 5))), (Q(9, 10), (Q(1, 5), Q(1, 5), Q(1, 20)))):
        sym_table = three_rater_model(prior, errors)
        found = dawid_skene_three_raters(sym_table)
        squares = polarity_squares(pairwise_kappas(sym_table))
        symmetric_ok = symmetric_ok and found["status"] == "exact" and found["solution"]["prior"] == prior and all(
            found["solution"]["false_negatives"][i] == found["solution"]["false_positives"][i]
            == error_rate_from_square(squares[i]) == errors[i - 1] for i in (1, 2, 3))
    copy = {}
    for rho in (Q(1), HALF):
        copied = copy_grader_table(FIXTURE_PRIOR, FIXTURE_ETA1, FIXTURE_ETA2, 1 - FIXTURE_ACCURACY, rho)
        copy[str(rho)] = {**dawid_skene_three_raters(copied), "symmetric_passes": model_constraints(copied)["passes"]}
    anti = dawid_skene_model(DS_PRIOR, (DS_FALSE_NEGATIVES[0], ANTI_INFORMATIVE_SECOND[0], DS_FALSE_NEGATIVES[2]),
                             (DS_FALSE_POSITIVES[0], ANTI_INFORMATIVE_SECOND[1], DS_FALSE_POSITIVES[2]))
    chance = dawid_skene_model(DS_PRIOR, (DS_FALSE_NEGATIVES[0], HALF, DS_FALSE_NEGATIVES[2]),
                               (DS_FALSE_POSITIVES[0], HALF, DS_FALSE_POSITIVES[2]))
    perturbed_cells = dict(table.cells)
    perturbed_cells[(0, 0, 1)] += Q(1, 100)
    perturbed_cells[(1, 1, 0)] -= Q(1, 100)
    perturbed = LabelTable(perturbed_cells)
    return {"prior": DS_PRIOR, "false_negatives": DS_FALSE_NEGATIVES, "false_positives": DS_FALSE_POSITIVES,
            "table": table, "fit": fit, "alternative_fits_table": alt_table == table,
            "round_trip_on_grid": round_trip, "grid_points": points, "symmetric_special_case": symmetric_ok,
            "jacobian_rank": dawid_skene_jacobian_rank(DS_PRIOR, DS_FALSE_NEGATIVES, DS_FALSE_POSITIVES),
            "jacobian_rank_symmetric_point": dawid_skene_jacobian_rank(
                FIXTURE_PRIOR, (FIXTURE_ETA1, FIXTURE_ETA2, 1 - FIXTURE_ACCURACY),
                (FIXTURE_ETA1, FIXTURE_ETA2, 1 - FIXTURE_ACCURACY)),
            "jacobian_rank_chance_rater": dawid_skene_jacobian_rank(
                DS_PRIOR, (DS_FALSE_NEGATIVES[0], HALF, DS_FALSE_NEGATIVES[2]),
                (DS_FALSE_POSITIVES[0], HALF, DS_FALSE_POSITIVES[2])),
            "copy_grader": copy,
            "falsifiers": {"outside_model": dawid_skene_three_raters(LabelTable(OUTSIDE_MODEL)),
                           "not_identified": dawid_skene_three_raters(chance),
                           "convention_violated": dawid_skene_three_raters(anti),
                           "anti_informative_under_rater_1": dawid_skene_three_raters(anti, "rater_1_informative")},
            "perturbed": {"fit": dawid_skene_three_raters(perturbed),
                          "symmetric_passes": model_constraints(perturbed)["passes"]},
            "degrees_of_freedom": DEGREES_OF_FREEDOM}


def asymmetric_pipeline_fixture() -> dict[str, object]:
    """Both judges against an asymmetric gold grader, with the symmetric
    pipeline run on the same records for contrast."""

    controller = (DS_FALSE_NEGATIVES[2], DS_FALSE_POSITIVES[2])
    gold, second = (DS_FALSE_NEGATIVES[0], DS_FALSE_POSITIVES[0]), (DS_FALSE_NEGATIVES[1], DS_FALSE_POSITIVES[1])
    marginal_flip = DS_PRIOR * gold[0] + (1 - DS_PRIOR) * gold[1]
    judges = {}
    for name, eps1 in DS_JUDGES.items():
        record = expected_record_table_asymmetric(DS_SIZE, DS_PRIOR, controller, FIXTURE_ERROR, eps1, gold, second)
        forward = asymmetric_gold_noise_forward(DS_PRIOR, controller, FIXTURE_ERROR, eps1, gold)
        measured = measured_judge_rates(record, 1)
        cells = measured["cells"]
        judges[name] = {
            "eps1": eps1, "record": record,
            "cells_integral": all(c.denominator == 1 for c in record.cells.values()),
            "label_table_is_dawid_skene": record.label_table() == LabelTable(
                {c: DS_SIZE * w for c, w in dawid_skene_model(DS_PRIOR, DS_FALSE_NEGATIVES, DS_FALSE_POSITIVES).cells.items()}),
            "forward": forward,
            "measured_matches_forward": (measured["accuracy"] == forward["accuracy"]
                                         and measured["judge_error"] == forward["judge_error"]
                                         and measured["wrong_wrong_rate"] == forward["wrong_wrong_rate"]),
            "measured_agreement": (cells["right_right"] + cells["wrong_wrong"]) / record.total,
            "agreement_invariant": (cells["right_right"] + cells["wrong_wrong"]) / record.total == forward["agreement_rate"],
            "calibration": calibrate_asymmetric(record, FIXTURE_ERROR, FIXTURE_ALPHA),
            "symmetric_pipeline": calibrate(record, FIXTURE_ERROR, FIXTURE_ALPHA),
            "marginal_flip_rate": marginal_flip,
            "symmetric_inversion_at_marginal_flip_rate": inverted_eps1(
                measured["accuracy"], measured["judge_error"], measured["wrong_wrong_rate"], marginal_flip)}
    reduces = True
    for accuracy, judge_error, eps1 in ((Q(4, 5), Q(1, 10), Q(1, 10)), (Q(4, 5), Q(1, 10), HALF), (Q(7, 10), Q(1, 4), Q(2, 5))):
        for eta in (Q(0), Q(1, 20), Q(1, 10)):
            for prior in (Q(1, 4), HALF):
                sym = gold_noise_forward(accuracy, judge_error, eps1, eta)
                asym = asymmetric_gold_noise_forward(prior, (1 - accuracy, 1 - accuracy), judge_error, eps1, (eta, eta))
                inverse = asymmetric_gold_noise_inverse(prior, (1 - accuracy, 1 - accuracy), (eta, eta),
                                                        sym["accuracy"], sym["judge_error"], sym["wrong_wrong_rate"])
                reduces = reduces and all(asym[k] == sym[k] for k in ("accuracy", "judge_error", "wrong_wrong_rate", "agreement_rate")) \
                    and inverse["eps1"] == eps1 == gold_noise_inverse(sym["accuracy"], sym["judge_error"], sym["eps1"], eta)["eps1"] \
                    and inverse["determinant"] == accuracy * (1 - accuracy) * (1 - 2 * eta)
    return {"judges": judges, "reduces_to_symmetric_inversion": reduces, "size": DS_SIZE}


def verify(sampling_sizes=SAMPLING_SIZES, joint_sizes=JOINT_SIZES, workers: int = 1) -> dict[str, object]:
    """Run all exact fixtures and return machine-readable checks."""

    raters, pipeline, dependent, ledgers = (three_rater_fixture(), pipeline_fixture(),
                                            dependent_grader_fixture(), ledger_fixture())
    sampling, ds, asym = sampling_fixture(sampling_sizes), dawid_skene_fixture(), asymmetric_pipeline_fixture()
    joint_sizes = tuple(sorted(set(joint_sizes) | {PLANNING_SIZE}))
    four, joint = four_rater_fixture(), joint_fixture(joint_sizes, JOINT_GRID, workers)
    copy4 = four["copy_grader"]
    small = joint["by_size"][PLANNING_SIZE]
    small_ind, small_shared = (small["judges"]["independent"]["statement"],
                               small["judges"]["maximally_shared"]["statement"])
    small_set = small["eta_set"]["retained"]
    big_joint = joint["by_size"][max(joint_sizes)]
    ind, shared = pipeline["independent"]["calibration"], pipeline["maximally_shared"]["calibration"]
    ind_inv, shared_inv = ind["inversions"][0], shared["inversions"][0]
    copy_full, copy_half = dependent["rows"]["1"]["calibration"], dependent["rows"]["1/2"]["calibration"]
    half_bracket = copy_half["eta1"]
    laws, largest = sampling["laws"], sampling["largest_size"]
    ladder = [laws[m]["p_undefined"] for m in sorted(laws)]
    delta_eta, delta_square = sampling["delta"]["eta"], sampling["delta"]["square"]
    big = laws[largest]
    bounds = sampling["disagreement_bounds"]
    fit, copy1, copy_half_ds = ds["fit"], ds["copy_grader"]["1"], ds["copy_grader"]["1/2"]
    falsifiers = ds["falsifiers"]
    asym_ind, asym_shared = asym["judges"]["independent"], asym["judges"]["maximally_shared"]
    checks = {
        "pairwise_polarities_factor_on_rational_grid": raters["factorization_on_grid"],
        "fixture_squares_are_perfect_and_recover_eta1_eta2_a":
            raters["squares"] == {1: Q(16, 25), 2: Q(9, 25), 3: Q(9, 25)}
            and raters["recovered_eta1"] == FIXTURE_ETA1 and raters["recovered_eta2"] == FIXTURE_ETA2
            and raters["recovered_accuracy"] == FIXTURE_ACCURACY,
        "membership_test_agrees_with_exact_value":
            raters["membership"]["eta1_le_1/10"] and not raters["membership"]["eta1_le_9/100"]
            and raters["membership"]["eta1_le_11/100"] and raters["bracket_exact_case"]["width"] == 0,
        "bracket_on_non_square_has_width_2_pow_minus_16_and_contains_eta1":
            half_bracket["exact"] is None and half_bracket["width"] <= RESOLUTION
            and not error_rate_at_most(copy_half["squares"][1], half_bracket["lower"])
            and error_rate_at_most(copy_half["squares"][1], half_bracket["upper"])
            and copy_half["squares"][1] == Q(148, 175),
        "constraints_hold_at_fixture_and_model_is_four_dimensional":
            raters["constraints"]["passes"] and raters["constraints"]["equalities_hold"]
            and raters["jacobian_rank"] == 4
            and DEGREES_OF_FREEDOM["free_cell_probabilities"] - DEGREES_OF_FREEDOM["symmetric_parameters"]
            == DEGREES_OF_FREEDOM["constraints"] == 3,
        "label_swap_is_observationally_equivalent": raters["label_swap_equivalent"],
        "sign_falsifier_has_one_negative_kappa":
            raters["sign_falsifier"]["negative_kappas"] == 1 and not raters["sign_falsifier"]["signs_consistent"]
            and not raters["sign_falsifier"]["model_consistent"],
        "range_falsifier_implies_square_above_one":
            raters["range_falsifier"]["squares"][1] == Q(144, 25)
            and raters["range_falsifier"]["squares_in_unit_interval"] is False
            and not raters["range_falsifier"]["model_consistent"],
        "constraints_are_vacuous_at_balanced_prior":
            raters["balanced_prior_dependent"]["vacuous_at_balanced_prior"]
            and raters["balanced_prior_dependent"]["equalities_hold"],
        "copy_grader_residuals_match_closed_form":
            all(dependent["residual_closed_form_on_grid"].values())
            and all(row["residuals_match_closed_form"] for row in dependent["rows"].values())
            and dependent["rows"]["1"]["closed_form_residual"] == Q(-27, 250),
        "record_marginals_match_judge_note_forward_map_and_three_rater_model":
            all(j["measured_matches_forward"] and j["label_table_matches_model"] for j in pipeline.values()),
        "expected_record_cells_integral_at_m_10000":
            all(j["cells_integral"] for j in pipeline.values())
            and all(c.denominator == 1 for c in dependent["rows"]["1"]["record"].cells.values()),
        "pipeline_recovers_eta1_eta2_a_exactly_for_both_judges":
            all(j["calibration"]["status"] == "exact" and j["calibration"]["eta1"]["exact"] == FIXTURE_ETA1
                and j["calibration"]["eta2"]["exact"] == FIXTURE_ETA2
                and j["calibration"]["accuracy_from_identity"]["exact"] == FIXTURE_ACCURACY
                for j in pipeline.values()),
        "inversion_recovers_a_eps_eps1_exactly_for_both_judges":
            all(j["calibration"]["inversions"][0]["recovered"] == {
                "accuracy": FIXTURE_ACCURACY, "judge_error": FIXTURE_ERROR, "eps1": j["eps1"]}
                for j in pipeline.values()),
        "identity_accuracy_equals_inverted_accuracy":
            ind["accuracy_consistent"] and shared["accuracy_consistent"] and copy_full["accuracy_consistent"],
        "corrected_counts_are_integral_and_are_the_clean_fixture_scaled":
            not ind_inv["rounding_changed_a_cell"] and not shared_inv["rounding_changed_a_cell"]
            and ind_inv["corrected_table"] == JudgeTable(7200, 800, 1800, 200)
            and shared_inv["corrected_table"] == JudgeTable(8000, 0, 1000, 1000),
        "judge_tests_on_corrected_counts_separate_the_judges":
            ind_inv["tests"]["independence_p"] > FIXTURE_ALPHA > shared_inv["tests"]["independence_p"]
            and ind_inv["tests"]["fisher_p"] > FIXTURE_ALPHA > shared_inv["tests"]["fisher_p"]
            and ind_inv["tests"]["ceiling_p"] < FIXTURE_ALPHA < shared_inv["tests"]["ceiling_p"]
            and ind_inv["tests"]["cp_contains_error"] and not ind_inv["tests"]["cp_contains_half"]
            and shared_inv["tests"]["cp_contains_half"] and not shared_inv["tests"]["cp_contains_error"],
        "sensitivity_is_minus_four_and_minus_five_halves":
            ind_inv["sensitivity_d_eps1_d_eta"] == -4 and shared_inv["sensitivity_d_eps1_d_eta"] == Q(-5, 2),
        "displacement_formula_matches_direct_inversion":
            all(j["displacements"] == j["direct_differences"] for j in pipeline.values())
            and pipeline["independent"]["displacements"]["1/100"] == Q(-4, 100) * Q(4, 25) / (Q(4, 25) - Q(1, 100)),
        "eta_gradient_chain_at_fixture":
            ind["eta_gradient"]["per_kappa"] == {(1, 2): Q(-5, 12), (1, 3): Q(-5, 12), (2, 3): Q(5, 9)}
            and ind["chain_sensitivity"]["d_eps1_d_agreement"][(1, 2)] == Q(10, 3),
        "copy_grader_hides_gold_noise_and_makes_the_independent_judge_look_shared":
            copy_full["eta1"]["exact"] == 0 and copy_full["inversions"][0]["recovered"]["eps1"] == Q(9, 26)
            and copy_full["inversions"][0]["recovered"]["judge_error"] == Q(9, 50)
            and copy_full["inversions"][0]["tests"]["independence_p"] < FIXTURE_ALPHA
            and copy_full["inversions"][0]["tests"]["fisher_p"] < FIXTURE_ALPHA
            and not copy_full["constraints"]["passes"] and not copy_full["valid"],
        "half_copy_grader_is_bracketed_and_inflates_eps1":
            copy_half["status"] == "bracketed" and not copy_half["constraints"]["passes"]
            and Q(4, 100) < half_bracket["lower"] < half_bracket["upper"] < Q(41, 1000)
            and all(Q(27, 100) < inv["recovered"]["eps1"] < Q(28, 100) for inv in copy_half["inversions"])
            and all(inv["tests"]["independence_p"] < FIXTURE_ALPHA for inv in copy_half["inversions"]),
        "ledger_breach_withholds_calibration":
            calibration_valid(ind, ledgers["respected"]) and not calibration_valid(ind, ledgers["breached"])
            and not calibration_valid(copy_full, ledgers["respected"]),
        # --- 0.2: the sampling law ---
        "agreement_covariance_closed_form_matches_cells_and_is_not_diagonal":
            sampling["covariance_from_cells"] == sampling["covariance_closed_form"]
            and sampling["covariance_from_cells"][((1, 2), (1, 3))] == Q(9, 25) * Q(9, 25) / 4
            and all(sampling["covariance_from_cells"][(p, r)] > 0 for p in PAIRS for r in PAIRS),
        "delta_variance_is_2401_over_8100_and_planning_size_is_742":
            delta_eta == Q(2401, 8100) == sampling["delta_from_table"]
            and sampling["delta"]["root_of_eta_variance"] == Q(49, 90)
            and delta_square == 16 * Q(16, 25) * delta_eta and sampling["planning_size"] == 742
            and Q(2401, 8100) / 742 < TOLERANCE ** 2 <= Q(2401, 8100) / 741,
        "four_pattern_law_equals_label_table_enumeration_at_m_16":
            sampling["reduction_matches_tables"] and sampling["label_table_enumeration"]["compositions"] == 245157
            and laws[16]["compositions"] == 969 if 16 in laws else sampling["reduction_matches_tables"],
        "undefined_probability_falls_along_the_ladder_and_is_below_2_percent_at_m_200":
            all(a > b for a, b in zip(ladder, ladder[1:])) and laws[16]["p_undefined"] > Q(3, 10)
            and laws[200]["p_undefined"] < Q(1, 50) and all(law["p_exact"] > 0 for law in laws.values()),
        "scaled_variances_at_largest_size_within_5_percent_of_delta":
            all(abs(v - delta_eta) <= Q(5, 100) * delta_eta for v in big["scaled_eta_variance_bracket"])
            and abs(big["scaled_square_variance"] - delta_square) <= Q(5, 100) * delta_square
            and big["eta_mean_bracket"][0] < FIXTURE_ETA1 + TOLERANCE / 4
            and big["eta_mean_bracket"][1] > FIXTURE_ETA1 - TOLERANCE / 4,
        "law_of_eta_hat_is_free_of_the_prior":
            sampling["prior_free"] and all(row["law"]["p_undefined"] > 0 for row in sampling["other_points"].values())
            and sampling["other_points"]["better_raters"]["planning_size"] < 742 < sampling["other_points"]["worse_raters"]["planning_size"],
        "disagreement_bound_is_an_upper_bound_only":
            all(FIXTURE_ETA2 <= b["eta_upper_bound"] < HALF and b["eta_upper_bound"] > sampling["population_disagreement"]
                for b in bounds.values())
            and sampling["population_disagreement"] == Q(13, 50) and bounds["ten_thousand"]["eta_upper_bound"] < Q(27, 100),
        # --- 0.2: the asymmetric model ---
        "dawid_skene_fixture_recovers_rates_exactly_and_label_switch_fits":
            fit["status"] == "exact" and fit["root"] == Q(441, 8000) and fit["in_range"]
            and fit["solution"]["prior"] == DS_PRIOR
            and all(fit["solution"]["false_negatives"][i + 1] == DS_FALSE_NEGATIVES[i]
                    and fit["solution"]["false_positives"][i + 1] == DS_FALSE_POSITIVES[i] for i in range(3))
            and fit["alternative"]["prior"] == 1 - DS_PRIOR and ds["alternative_fits_table"],
        "dawid_skene_round_trip_on_rational_grid": ds["round_trip_on_grid"] and ds["grid_points"] == 256,
        "dawid_skene_reduces_to_symmetric_etas": ds["symmetric_special_case"],
        "dawid_skene_jacobian_rank_7_leaves_no_equality_constraint":
            ds["jacobian_rank"] == ds["jacobian_rank_symmetric_point"] == 7 and ds["jacobian_rank_chance_rater"] < 7
            and fit["degrees_of_freedom_left"] == 0 and ds["perturbed"]["fit"]["status"] == "bracketed"
            and ds["perturbed"]["fit"]["in_range"] and not ds["perturbed"]["symmetric_passes"],
        "dawid_skene_absorbs_the_copy_grader":
            copy1["status"] == "exact" and copy1["in_range"] and not copy1["symmetric_passes"]
            and copy1["solution"]["prior"] == Q(3, 10)
            and all(copy1["solution"][k][i] == 0 for k in ("false_negatives", "false_positives") for i in (1, 2))
            and copy_half_ds["status"] == "bracketed" and copy_half_ds["in_range"] and not copy_half_ds["symmetric_passes"],
        "dawid_skene_conventions_and_inequality_falsifiers":
            falsifiers["outside_model"]["status"] == "outside_model" and falsifiers["outside_model"]["radicand"] == Q(-49, 30000)
            and falsifiers["not_identified"]["status"] == "not_identified"
            and falsifiers["convention_violated"]["status"] == "convention_violated"
            and falsifiers["anti_informative_under_rater_1"]["status"] == "exact"
            and falsifiers["anti_informative_under_rater_1"]["solution"]["deltas"][2] == -Q(1, 5)
            and falsifiers["anti_informative_under_rater_1"]["solution"]["false_negatives"][2] == ANTI_INFORMATIVE_SECOND[0],
        "asymmetric_record_matches_forward_map_and_agreement_is_invariant":
            all(j["measured_matches_forward"] and j["agreement_invariant"] and j["label_table_is_dawid_skene"]
                for j in asym["judges"].values()) and asym_ind["cells_integral"],
        "asymmetric_pipeline_recovers_both_judges_exactly":
            all(j["calibration"]["status"] == "exact"
                and j["calibration"]["inversions"][0]["recovered"]["eps1"] == j["eps1"]
                and j["calibration"]["inversions"][0]["recovered"]["judge_error"] == FIXTURE_ERROR
                and j["calibration"]["inversions"][0]["recovered"]["accuracy"] == Q(3, 4)
                and j["calibration"]["inversions"][0]["recovered"]["measured_accuracy_consistent"]
                and not j["calibration"]["inversions"][0]["rounding_changed_a_cell"] for j in asym["judges"].values())
            and asym_ind["calibration"]["inversions"][0]["corrected_table"] == JudgeTable(2700, 300, 900, 100)
            and asym_shared["calibration"]["inversions"][0]["corrected_table"] == JudgeTable(3000, 0, 600, 400)
            and asym_ind["calibration"]["inversions"][0]["tests"]["independence_p"] > FIXTURE_ALPHA
            > asym_shared["calibration"]["inversions"][0]["tests"]["independence_p"],
        "symmetric_pipeline_misreads_asymmetric_gold":
            all(not j["symmetric_pipeline"]["constraints"]["passes"] and j["symmetric_pipeline"]["status"] == "bracketed"
                for j in asym["judges"].values())
            and asym_ind["marginal_flip_rate"] == Q(7, 40)
            and asym_ind["symmetric_inversion_at_marginal_flip_rate"] == Q(5, 62)
            and all(abs(inv["recovered"]["eps1"] - FIXTURE_ERROR) > Q(1, 50)
                    for inv in asym_ind["symmetric_pipeline"]["inversions"]),
        "asymmetric_inverse_reduces_to_judge_note_inverse": asym["reduces_to_symmetric_inversion"],
        # --- 0.3: four raters ---
        "four_rater_moments_match_closed_forms_and_residuals_vanish_on_grid":
            four["closed_forms_on_grid"] and four["ratio_relations_on_grid"] and four["grid_points"] == 243
            and four["moments"]["fourth_moment"] == four["closed_forms"]["k_1234"] == Q(3087, 320000)
            and four["moments"]["third_moments"][(1, 2, 3)] == four["closed_forms"]["k_123"] == Q(147, 8000)
            and four["moments"]["covariances"][(1, 2)] * four["moments"]["covariances"][(3, 4)]
            == four["closed_forms"]["tetrad"] == Q(1323, 320000)
            and all(r == 0 for r in four["residuals"].values()),
        "four_rater_six_constraints_constraint_rank_6_parameter_rank_9":
            four["constraint_jacobian_rank"] == 6 and four["parameter_jacobian_rank"] == 9 and four["ranks_on_grid"]
            and DEGREES_OF_FREEDOM["four_rater_free_cell_probabilities"] - DEGREES_OF_FREEDOM["four_rater_parameters"]
            == DEGREES_OF_FREEDOM["four_rater_constraints"] == len(CONSTRAINTS4) == 6,
        "chance_rater_keeps_parameter_rank_9_but_degenerates_the_residuals":
            all(row["parameter_rank"] == 9 and row["status"] == "not_identified" for row in four["chance_rater"].values())
            and four["chance_rater"][2]["constraint_rank"] == 4 and four["chance_rater"][4]["constraint_rank"] == 6
            and four["degenerate_prior_rank"] < 9,
        "four_rater_fixture_integral_at_10000_and_nine_parameters_recovered_exactly":
            four["cells_integral"] and four["constraints"]["passes"] and four["constraints"]["fit"]["status"] == "exact"
            and four["constraints"]["reproduces_table"] and four["constraints"]["fit"]["solution"]["prior"] == FOUR_PRIOR
            and all(four["constraints"]["fit"]["solution"]["false_negatives"][i + 1] == FOUR_FALSE_NEGATIVES[i]
                    and four["constraints"]["fit"]["solution"]["false_positives"][i + 1] == FOUR_FALSE_POSITIVES[i]
                    for i in range(4)),
        "four_rater_converse_reconstructs_every_grid_table": four["converse_on_grid"],
        "copy_grader_tetrad_residual_is_rho_V1_c34":
            all(row["constraints"]["residuals"]["tetrad_12_34_vs_13_24"] == row["closed_form_residual"]
                == row["copy_rate"] * Q(57, 400) * Q(9, 200)
                and row["constraints"]["residuals"]["tetrad_13_24_vs_14_23"] == 0
                and not row["constraints"]["equalities_hold"] and not row["constraints"]["passes"]
                for row in copy4.values())
            and all(res["tetrad_12_34_vs_13_24"] == rho * FIXTURE_ETA1 * (1 - FIXTURE_ETA1) * Q(3, 16) * Q(2, 5) * Q(3, 5)
                    for rho, res in ((Q(1, 4), four["symmetric_copy_residuals"]["1/4"]),
                                     (HALF, four["symmetric_copy_residuals"]["1/2"]),
                                     (Q(1), four["symmetric_copy_residuals"]["1"])))
            and all(v.denominator == 1 for v in four["copy_witness_counts"].values()),
        "fourth_rater_exposes_the_copy_grader_three_raters_absorb":
            all(row["triple_123"]["status"] in ("exact", "bracketed") and row["triple_123"]["in_range"]
                and row["constraints"]["fit"]["status"] == "inconsistent" for row in copy4.values())
            and copy4["1"]["triple_123"]["status"] == "exact" and copy4["1"]["triple_123"]["solution"]["prior"] == Q(3, 8),
        "tetrad_detects_copying_at_a_balanced_prior_where_the_symmetric_check_is_vacuous":
            four["balanced_prior_copy"]["four_rater_residuals"]["tetrad_12_34_vs_13_24"]
            == four["balanced_prior_copy"]["closed_form"] == FIXTURE_ETA1 * (1 - FIXTURE_ETA1) * Q(1, 4) * Q(2, 5) * Q(3, 5)
            and four["balanced_prior_copy"]["three_rater_check"]["vacuous_at_balanced_prior"]
            and four["balanced_prior_copy"]["three_rater_check"]["equalities_hold"],
        "anti_informative_second_grader_needs_the_rater_1_convention":
            four["anti_informative_second"]["all_informative"]["fit"]["status"] == "convention_violated"
            and four["anti_informative_second"]["rater_1_informative"]["passes"]
            and four["anti_informative_second"]["rater_1_informative"]["fit"]["solution"]["false_negatives"][2]
            == ANTI_INFORMATIVE_SECOND[0]
            and four["anti_informative_second"]["rater_1_informative"]["fit"]["solution"]["prior"] == FOUR_PRIOR,
        "four_rater_perturbed_table_fails_the_equalities":
            not four["perturbed"]["equalities_hold"] and not four["perturbed"]["passes"],
        # --- 0.3: the joint statement ---
        "square_tails_match_label_table_enumeration_and_sampling_law":
            joint["tails_match_label_table_enumeration_at_16"]
            and all(joint["tail_laws"][m]["p_undefined"] == sampling["laws"][m]["p_undefined"]
                    for m in joint["tail_laws"] if m in sampling["laws"]),
        "fixed_point_bracket_contains_the_exact_tails_within_2_pow_minus_90":
            joint["bracket_contains_exact"] and joint["bracket_cases"] == len(BRACKET_CASES)
            and joint["bracket_max_width"] < Q(1, 2 ** 90)
            and all(entry["eta_set"]["exact_fallbacks"] == 0 and entry["eta_set"]["max_bracket_width"] < Q(1, 2 ** 90)
                    for entry in joint["by_size"].values()),
        "eta_set_at_planning_size_is_a_grid_interval_around_the_truth":
            FIXTURE_ETA1 in small_set and Q(0) not in small_set and Q(1, 5) not in small_set
            and small["eta_set"]["is_grid_interval"] and small["eta_set"]["level_per_test"] == FIXTURE_ALPHA / 2
            and small_ind["square_test_used"]
            and small_ind["agreement_counts"]["counts"] == {(1, 2): 549, (1, 3): 549, (2, 3): 504}
            and small["eta_set"]["observed_square"] == Q(31684, 49343),
        "joint_tests_separate_the_judges_at_planning_size_though_the_ranges_overlap":
            small["tests_separate"] and not small["ranges_disjoint"]
            and small_ind["eps1_range"][0] < small_shared["eps1_range"][0] < small_ind["eps1_range"][1] < HALF
            and small_shared["eps1_range"][0] > FIXTURE_ERROR and small_ind["coverage"] == 1 - 2 * FIXTURE_ALPHA,
        "joint_statement_at_largest_size_is_stated_and_separates_by_tests":
            all(j["statement"]["status"] == "stated" for j in big_joint["judges"].values()) and big_joint["tests_separate"]
            and FIXTURE_ETA1 in big_joint["eta_set"]["retained"] and big_joint["eta_set"]["is_grid_interval"],
        "ranges_disjoint_and_set_nested_at_largest_size_when_above_planning":
            big_joint is small or (big_joint["ranges_disjoint"]
                                   and set(big_joint["eta_set"]["retained"]) < set(small_set)),
        "disagreement_bound_alone_leaves_eps1_undetermined":
            joint["bound_only"]["status"] == "eps1_undetermined" and not joint["bound_only"]["square_test_used"]
            and joint["bound_only"]["undetermined_points"] > 0,
        "asymmetric_record_withholds_the_joint_statement":
            joint["asymmetric_record"]["status"] == "withheld_constraints_fail"
            and not joint["asymmetric_record"]["constraints_pass"] and joint["asymmetric_record"]["eta_set"] is None,
    }
    return {"evidence_status": "exact_synthetic_fixtures_not_model_or_agent_evidence",
            "checks": checks, "all_passed": all(checks.values()),
            "fixture": {"size": FIXTURE_SIZE, "prior": FIXTURE_PRIOR, "accuracy": FIXTURE_ACCURACY,
                        "judge_error": FIXTURE_ERROR, "eta1": FIXTURE_ETA1, "eta2": FIXTURE_ETA2,
                        "judges": JUDGES, "alpha": FIXTURE_ALPHA, "tolerance": TOLERANCE,
                        "sampling_sizes": tuple(sampling_sizes), "joint_sizes": tuple(joint_sizes),
                        "asymmetric": {"size": DS_SIZE, "prior": DS_PRIOR, "false_negatives": DS_FALSE_NEGATIVES,
                                       "false_positives": DS_FALSE_POSITIVES, "judges": DS_JUDGES},
                        "four_raters": {"size": FOUR_SIZE, "prior": FOUR_PRIOR, "false_negatives": FOUR_FALSE_NEGATIVES,
                                        "false_positives": FOUR_FALSE_POSITIVES}},
            "three_raters": raters, "pipeline": pipeline, "dependent_grader": dependent, "ledger": ledgers,
            "sampling": sampling, "dawid_skene": ds, "asymmetric_pipeline": asym,
            "four_raters": four, "joint": joint}
