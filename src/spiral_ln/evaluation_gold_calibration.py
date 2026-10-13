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

Nothing here calls a model.  Every quantity is a ``fractions.Fraction``; floats
are rejected at the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as Q
from itertools import product
from math import isqrt

from spiral_ln.evaluation_feedback_signal import shared_error_bounds
from spiral_ln.evaluation_game_feedback import LoopEvent
from spiral_ln.evaluation_judge_measurement import (
    HALF, JudgeTable, ceiling_p_value, clopper_pearson_contains, expected_table,
    fisher_p_value, gold_noise_forward, gold_noise_inverse, independence_p_value,
    measurement_ledger, rounded_table, table_estimates,
)

RATERS = {1: "G1", 2: "G2", 3: "C"}
PAIRS = ((1, 2), (1, 3), (2, 3))
SUBSETS = ((1,), (2,), (3,)) + PAIRS + ((1, 2, 3),)
CELLS3 = tuple(product((0, 1), repeat=3))
CELLS4 = tuple(product((0, 1), repeat=4))
RESOLUTION = Q(1, 2 ** 16)
DEGREES_OF_FREEDOM = {"cells": 8, "free_cell_probabilities": 7, "symmetric_parameters": 4,
                      "constraints": 3, "asymmetric_dawid_skene_parameters": 7}


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


def verify() -> dict[str, object]:
    """Run all exact fixtures and return machine-readable checks."""

    raters, pipeline, dependent, ledgers = (three_rater_fixture(), pipeline_fixture(),
                                            dependent_grader_fixture(), ledger_fixture())
    ind, shared = pipeline["independent"]["calibration"], pipeline["maximally_shared"]["calibration"]
    ind_inv, shared_inv = ind["inversions"][0], shared["inversions"][0]
    copy_full, copy_half = dependent["rows"]["1"]["calibration"], dependent["rows"]["1/2"]["calibration"]
    half_bracket = copy_half["eta1"]
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
    }
    return {"evidence_status": "exact_synthetic_fixtures_not_model_or_agent_evidence",
            "checks": checks, "all_passed": all(checks.values()),
            "fixture": {"size": FIXTURE_SIZE, "prior": FIXTURE_PRIOR, "accuracy": FIXTURE_ACCURACY,
                        "judge_error": FIXTURE_ERROR, "eta1": FIXTURE_ETA1, "eta2": FIXTURE_ETA2,
                        "judges": JUDGES, "alpha": FIXTURE_ALPHA},
            "three_raters": raters, "pipeline": pipeline, "dependent_grader": dependent, "ledger": ledgers}
