"""Exact multi-generation selection gap as a Markov chain on the score lattice.

``evaluation_game_feedback.selection_inflation`` gives the one-generation
over-report from keeping the best of ``K`` candidates scored on one reused set
of ``n`` items.  ``paper/evaluation_feedback_insertions.md`` records that
accumulation of that gap across generations "is a simulation result, not an
exact one".  This module makes it exact.  Nothing here calls a model, samples,
or reads the simulations; every number is a ``Fraction`` produced by a finite
dynamic programme over a finite Markov chain or by finite enumeration.

The chain (null model: no true improvement)
-------------------------------------------
* Vertices (states): the incumbent's realized count ``c`` on the reused set,
  ``c in {0, ..., n}``.
* Each generation draws ``K`` candidates i.i.d. and independent of the
  incumbent.  Candidate ``k`` scores ``C_k ~ Bin(n, p)`` on the reused set
  (each item an independent Bernoulli(p)).  Write ``M = max_k C_k``.
* Policy (acceptance rule): accept the best candidate iff ``M > c + t(c)`` for
  a threshold function ``t: {0..n} -> N``.  ``t == 0`` is naive reuse.
  ``t(c) = floor(z * sqrt(c (n - c) / n))`` is the exact integer form of the
  PREREG gate ``GATE_Z * sqrt(p (1 - p) / n) * n`` with ``p = c / n``: the
  count difference ``M - c`` is an integer ``d``, and ``d > x`` for real ``x``
  iff ``d >= floor(x) + 1``.  The floor of the square root of a rational is
  computed exactly with ``math.isqrt``.
* Edges: ``c -> j`` with probability ``P(M = j)`` for every ``j > c + t(c)``,
  and the self-loop ``c -> c`` with the remaining mass ``F(c + t(c))^K``,
  where ``F`` is the binomial CDF with ``F(j) = 1`` for ``j >= n``.  Every
  other edge has probability zero, so the transition graph is a DAG of upward
  edges plus self-loops; its sinks, the states with ``c + t(c) >= n``, are the
  absorbing states.
* Initial state: the incumbent's own count on the reused set,
  ``c_0 ~ Bin(n, p)``.
* Reported score after ``G`` generations: ``c_G / n``.  Readout value under
  the null: ``p``.  Readout gap: ``rho_G = E[c_G] / n - p``.

The drift model (``drift_trajectory``) adds a level index for the incumbent's
true success probability on a finite lattice ``p_0 + i * step`` capped at one,
so that true gains and phantom gains can be separated exactly.

Version 0.2 adds three pieces.  (A) Proven upper bounds on the naive gap
(Hoeffding and Bernstein maximal inequalities), compared with the exact DP
in floating point under a stated tolerance.  (B) The mutation chain
(``mutation_candidate_law`` and friends): a candidate copies the incumbent's
outcome on each item with probability ``1 - q`` and redraws it as
Bernoulli(p) with probability ``q``, which is an exact model of
item-correlated candidates and still a Markov chain on the count.  (C) The
one-generation gate-versus-naive theorem under true gains
(``one_step_gap_change``) and finite checks of how its sign chains across
generations.

Version 0.3 adds (D) the dominance question: whether the naive chain is
above every gated chain in both expected count and expected true value at
every generation under a fixed gain.  For the true value this is a theorem
(Proposition 8, proof sketched before ``drift_kernel``; every threshold
rule, every non-decreasing level function, every state); for the count it
is a finite result of an exact 972-cell search with no counterexample
(``dominance_sweep_fixture``) plus witnesses showing why the standard
proof routes fail (``dominance_structure_fixture``).  The search uses an
exact integer-numerator propagation (``drift_expectations``) and the exact
``g -> infinity`` limit (``drift_limit``).

Boundaries
----------
The independent chain has candidates independent of the incumbent; the
mutation chain correlates them item by item through one parameter ``q``,
which is not an exact image of ``sim.js``'s latent rotation.  ``n`` is fixed,
labels are clean, and every statement concerns distributions and
expectations, not sample paths.  Bounds that involve ``ln`` or ``sqrt`` are
floats and are compared to exact values under ``BOUND_TOLERANCE``.
"""

from __future__ import annotations

from fractions import Fraction as Q
from itertools import product
from math import isqrt, lcm, log, sqrt

from spiral_ln.evaluation_game_feedback import (_binomial_pmf, divergence_flags,
                                                selection_inflation)

REPORT_MODES = ("selection_block", "separate_block")
_BRUTE_FORCE_BIT_LIMIT = 16
_BRUTE_FORCE_GAIN_COMBINATIONS = 64


# --------------------------------------------------------------------------
# validation helpers
# --------------------------------------------------------------------------

def _check_items_candidates(items, candidates):
    if (type(items) is not int or type(candidates) is not int
            or items < 1 or candidates < 1):
        raise ValueError("items and candidates must be positive integers")


def _check_probability(p, name="p"):
    if type(p) is bool or not isinstance(p, (int, Q)) or not 0 <= p <= 1:
        raise ValueError(f"{name} must be a Fraction in [0, 1]")
    return Q(p)


def _check_generations(generations):
    if type(generations) is not int or generations < 0:
        raise ValueError("generations must be a non-negative integer")


def _check_threshold(threshold, items):
    try:
        threshold = tuple(threshold)
    except TypeError:
        raise ValueError("threshold must be a sequence") from None
    if (len(threshold) != items + 1
            or any(type(t) is not int or t < 0 for t in threshold)):
        raise ValueError("threshold must give one non-negative integer per state")
    return threshold


def _check_distribution(distribution, items):
    try:
        distribution = [Q(mass) for mass in distribution]
    except (TypeError, ValueError):
        raise ValueError("distribution must be a sequence of rationals") from None
    if (len(distribution) != items + 1 or any(mass < 0 for mass in distribution)
            or sum(distribution) != 1):
        raise ValueError("distribution must be a probability vector over the states")
    return distribution


def _check_gain(gain):
    if not isinstance(gain, dict) or not gain:
        raise ValueError("gain must be a non-empty mapping from step multiples to probabilities")
    checked = {}
    for multiple, mass in gain.items():
        if type(multiple) is not int or multiple < 0:
            raise ValueError("gain multiples must be non-negative integers")
        checked[multiple] = _check_probability(mass, "gain probability")
    if sum(checked.values()) != 1:
        raise ValueError("gain probabilities must sum to one")
    return checked


def _check_gain_schedule(gain, generations):
    """A single mapping applies to every generation; a sequence gives one
    mapping per generation."""

    if isinstance(gain, dict):
        return [_check_gain(gain)] * generations
    try:
        schedule = list(gain)
    except TypeError:
        raise ValueError("gain must be a mapping or a sequence of mappings") from None
    if len(schedule) != generations:
        raise ValueError("gain schedule must have one entry per generation")
    return [_check_gain(entry) for entry in schedule]


def decaying_gain_schedule(generations, q0, ratio, multiple=1) -> list[dict[int, Q]]:
    """Two-point schedule: in generation ``g`` (1-based) a candidate carries
    gain ``multiple`` with probability ``q0 * ratio**(g - 1)`` and gain zero
    otherwise.  A finite-lattice analogue of the simulation's decaying
    general-change scale ``0.06 * 0.95**(g - 1)``."""

    _check_generations(generations)
    q0 = _check_probability(q0, "q0")
    ratio = _check_probability(ratio, "ratio")
    if type(multiple) is not int or multiple < 1:
        raise ValueError("multiple must be a positive integer")
    schedule = []
    for g in range(generations):
        q = q0 * ratio**g
        schedule.append({0: 1 - q, multiple: q} if q else {0: Q(1)})
    return schedule


# --------------------------------------------------------------------------
# binomial building blocks
# --------------------------------------------------------------------------

def binomial_cdf(items: int, p: Q) -> list[Q]:
    running, cdf = Q(0), []
    for mass in _binomial_pmf(items, p):
        running += mass
        cdf.append(running)
    return cdf


def best_of_pmf(items: int, candidates: int, p: Q) -> list[Q]:
    """Law of ``max`` of ``candidates`` i.i.d. ``Bin(items, p)`` draws."""

    _check_items_candidates(items, candidates)
    p = _check_probability(p)
    cdf = binomial_cdf(items, p)
    return [cdf[j]**candidates - (cdf[j - 1]**candidates if j else Q(0))
            for j in range(items + 1)]


# --------------------------------------------------------------------------
# policies
# --------------------------------------------------------------------------

def naive_threshold(items: int) -> tuple[int, ...]:
    """``t == 0``: accept whenever the best candidate beats the incumbent."""

    if type(items) is not int or items < 1:
        raise ValueError("items must be a positive integer")
    return (0,) * (items + 1)


def gate_threshold(items: int, z) -> tuple[int, ...]:
    """``t(c) = floor(z * sqrt(c (n - c) / n))`` computed exactly.

    With ``q = z^2 c (n - c) / n = a / b`` in lowest terms,
    ``floor(sqrt(q)) = isqrt(a b) // b``, because ``floor(x / b) =
    floor(floor(x) / b)`` for real ``x >= 0`` and integer ``b >= 1``.
    """

    if type(items) is not int or items < 1:
        raise ValueError("items must be a positive integer")
    if type(z) is bool or not isinstance(z, (int, Q)) or z < 0:
        raise ValueError("z must be a non-negative Fraction")
    thresholds = []
    for c in range(items + 1):
        q = Q(z)**2 * c * (items - c) / items
        thresholds.append(isqrt(q.numerator * q.denominator) // q.denominator)
    return tuple(thresholds)


def false_acceptance_probability(items, candidates, p, threshold) -> tuple[Q, ...]:
    """``alpha(c) = P(M > c + t(c)) = 1 - F(min(n, c + t(c)))^K``.

    Under the null every acceptance is false, so this is the per-generation
    false-acceptance probability from state ``c``.
    """

    _check_items_candidates(items, candidates)
    p = _check_probability(p)
    threshold = _check_threshold(threshold, items)
    cdf = binomial_cdf(items, p)
    return tuple(1 - cdf[min(items, c + threshold[c])]**candidates
                 for c in range(items + 1))


# --------------------------------------------------------------------------
# null chain: kernel, DP, trajectory
# --------------------------------------------------------------------------

def transition_kernel(items, candidates, p, threshold) -> list[list[Q]]:
    """Row ``c`` is the law of the next state from ``c``.

    ``kernel[c][c] = F(cap)^K`` with ``cap = min(n, c + t(c))``;
    ``kernel[c][j] = P(M = j)`` for ``j > cap``; zero elsewhere.
    """

    _check_items_candidates(items, candidates)
    p = _check_probability(p)
    threshold = _check_threshold(threshold, items)
    cdf = binomial_cdf(items, p)
    best = best_of_pmf(items, candidates, p)
    rows = []
    for c in range(items + 1):
        cap = min(items, c + threshold[c])
        row = [Q(0)] * (items + 1)
        row[c] = cdf[cap]**candidates
        for j in range(cap + 1, items + 1):
            row[j] = best[j]
        rows.append(row)
    return rows


def state_distribution(items, candidates, p, threshold, generations,
                       initial=None) -> list[list[Q]]:
    """Exact law of the state after ``0, 1, ..., generations`` generations.

    ``initial`` defaults to ``Bin(items, p)``: the incumbent is scored on the
    reused set before any selection.  A point mass models an incumbent whose
    count is known.
    """

    _check_generations(generations)
    kernel = transition_kernel(items, candidates, p, threshold)
    current = (_binomial_pmf(items, Q(p)) if initial is None
               else _check_distribution(initial, items))
    return _propagate(kernel, current, generations)


def _propagate(kernel, current, generations):
    history = [current]
    for _ in range(generations):
        following = [Q(0)] * len(current)
        for c, mass in enumerate(current):
            if mass:
                for j, prob in enumerate(kernel[c]):
                    if prob:
                        following[j] += mass * prob
        history.append(following)
        current = following
    return history


def reuse_trajectory(items, candidates, p, threshold, generations) -> dict[str, object]:
    """Per-generation expectations for the reused-set chain under the null.

    ``expected_true`` is the constant ``p`` so that the same readers work on
    null and drift trajectories.  ``acceptance_probability[g - 1]`` is the
    probability that generation ``g`` accepts, every acceptance being false.
    """

    history = state_distribution(items, candidates, p, threshold, generations)
    threshold = _check_threshold(threshold, items)
    alpha = false_acceptance_probability(items, candidates, p, threshold)
    reported = [sum(c * mass for c, mass in enumerate(dist)) / items for dist in history]
    acceptance = [sum(mass * alpha[c] for c, mass in enumerate(dist)) for dist in history[:-1]]
    p = Q(p)
    return {
        "items": items, "candidates": candidates, "p": p, "threshold": threshold,
        "generations": generations,
        "expected_reported": reported, "expected_true": [p] * (generations + 1),
        "readout_value": p, "readout_gap": [value - p for value in reported],
        "acceptance_probability": acceptance,
        "expected_acceptances": sum(acceptance, Q(0)),
        "ceiling_mass": history[-1][items],
        "absorbing_states": tuple(c for c in range(items + 1) if c + threshold[c] >= items),
        "final_distribution": history[-1],
    }


# --------------------------------------------------------------------------
# closed forms for naive reuse (t == 0)
# --------------------------------------------------------------------------

def naive_closed_form(items, candidates, p, generations) -> dict[str, Q]:
    """Naive reuse after ``G`` generations is the max of ``G K + 1`` draws.

    With ``t == 0`` the state satisfies ``c_g = max(c_{g-1}, M_g)``, so
    ``c_G = max(c_0, M_1, ..., M_G)`` is the maximum of the initial incumbent's
    draw and all ``G K`` candidate draws: ``G K + 1`` i.i.d. ``Bin(n, p)``
    counts.  The one-generation formula applies with ``K`` replaced by
    ``G K + 1``; the initial incumbent counts as one draw because it is
    scored on the reused set like every candidate.
    """

    _check_generations(generations)
    _check_items_candidates(items, candidates)
    return selection_inflation(items, generations * candidates + 1, p)


def running_max_from_point(items, candidates, p, generations, start) -> Q:
    """``E[max(c_0, X)]`` for a known incumbent count ``c_0`` and ``X`` the
    max of ``G K`` candidate draws; the naive chain started at a point."""

    _check_generations(generations)
    _check_items_candidates(items, candidates)
    if type(start) is not int or not 0 <= start <= items:
        raise ValueError("start must be a state")
    draws = generations * candidates
    if draws == 0:
        return Q(start)
    pmf = best_of_pmf(items, draws, p)
    return sum(max(start, j) * mass for j, mass in enumerate(pmf))


def ceiling_mass_closed_form(items, candidates, p, generations) -> Q:
    """``P(c_G = n) = 1 - (1 - p^n)^(G K + 1)`` under naive reuse."""

    _check_generations(generations)
    _check_items_candidates(items, candidates)
    p = _check_probability(p)
    return 1 - (1 - p**items)**(generations * candidates + 1)


# --------------------------------------------------------------------------
# proven upper bounds for naive reuse (floats; compared under a tolerance)
# --------------------------------------------------------------------------

BOUND_TOLERANCE = 1e-12


def naive_gap_bounds(items, candidates, p, generations) -> dict[str, object]:
    """Upper bounds on ``rho_G`` under naive reuse, from maximal inequalities.

    ``c_G`` is the max of ``m = G K + 1`` i.i.d. ``Bin(n, p)`` draws
    (``naive_closed_form``).  Write ``Y_i = X_i - n p``.

    Hoeffding.  Each centred Bernoulli lies in an interval of length one, so
    Hoeffding's lemma gives ``E exp(lam (B - p)) <= exp(lam^2 / 8)``, and by
    independence over items ``E exp(lam Y_i) <= exp(lam^2 n / 8)``.  The
    maximal inequality ``E max_i Y_i <= (1 / lam) ln sum_i E exp(lam Y_i)``
    (Jensen, then ``max <= sum`` on the exponentials) gives
    ``E max_i Y_i <= (ln m) / lam + lam n / 8`` for every ``lam > 0``, and
    ``lam = sqrt(8 ln m / n)`` makes the right side ``sqrt(n ln m / 2)``.
    Dividing by ``n``: ``rho_G <= sqrt(ln m / (2 n))``.

    Bernstein.  For a centred variable ``Z`` with ``|Z| <= 1`` and variance
    ``v``, ``E exp(lam Z) <= exp(v (e^lam - 1 - lam))``, and
    ``e^lam - 1 - lam <= lam^2 / (2 (1 - lam / 3))`` for ``0 < lam < 3``
    (``k! >= 2 * 3^(k-2)``).  Over ``n`` items ``v = n p (1 - p)``, and the
    maximal inequality with ``lam = 1 / (1/3 + sqrt(v / (2 ln m)))`` gives
    ``E max_i Y_i <= sqrt(2 v ln m) + (ln m) / 3`` (Boucheron, Lugosi and
    Massart, Corollary 2.6).  Dividing by ``n``:
    ``rho_G <= sqrt(2 p (1 - p) ln m / n) + ln m / (3 n)``.

    ``gaussian_scale`` is the leading term ``sqrt(2 p (1 - p) ln m / n)``,
    the Gaussian extreme-value scale the earlier remark used.  Both bounds
    are proven for every ``n, K, p, G``; both grow without bound in ``G``
    while ``rho_G <= 1 - p``, so they are loose for large ``G`` at fixed
    ``n``.  The values are floats (``math.log``, ``math.sqrt``); compare with
    exact gaps under ``BOUND_TOLERANCE``.
    """

    _check_generations(generations)
    _check_items_candidates(items, candidates)
    p = _check_probability(p)
    draws = generations * candidates + 1
    log_draws = log(draws)
    variance = float(p * (1 - p))
    gaussian = sqrt(2 * log_draws * variance / items)
    return {"draws": draws, "log_draws": log_draws,
            "hoeffding": sqrt(log_draws / (2 * items)),
            "bernstein": gaussian + log_draws / (3 * items),
            "gaussian_scale": gaussian,
            "lattice_cap": float(1 - p)}


# --------------------------------------------------------------------------
# fresh-set arm
# --------------------------------------------------------------------------

def fresh_block_reported(items, candidates, p, threshold) -> dict[str, Q]:
    """One generation on a fresh block, reporting on that same block.

    The incumbent is re-scored on the fresh block, ``I ~ Bin(n, p)``,
    independently of the ``K`` candidates.  The reported count is ``M`` if
    ``M > I + t(I)`` and ``I`` otherwise.  With ``t == 0`` this is
    ``max(I, M)``, the max of ``K + 1`` draws, i.e.
    ``selection_inflation(n, K + 1, p)``.
    """

    _check_items_candidates(items, candidates)
    p = _check_probability(p)
    threshold = _check_threshold(threshold, items)
    pmf, cdf = _binomial_pmf(items, p), binomial_cdf(items, p)
    best = best_of_pmf(items, candidates, p)
    expected = Q(0)
    for c, mass in enumerate(pmf):
        cap = min(items, c + threshold[c])
        expected += mass * (c * cdf[cap]**candidates
                            + sum(j * best[j] for j in range(cap + 1, items + 1)))
    reported = expected / items
    return {"expected_reported": reported, "readout_value": p, "readout_gap": reported - p}


def fresh_trajectory(items, candidates, p, threshold, generations, report_on) -> dict[str, object]:
    """Per-generation expected reported score when every generation scores on
    a fresh block.

    Under the null the incumbent's identity carries no score, so the arm's
    state space is a single point and each generation's reported score is an
    independent copy.  ``separate_block``: the accepted controller is scored
    on a second fresh block, whose count is ``Bin(n, p)`` whatever was
    selected, so the expected reported score is ``p`` at every generation.
    ``selection_block``: generation ``g >= 1`` reports ``fresh_block_reported``
    and generation ``0`` reports the incumbent's own fresh count, mean ``p``.
    """

    _check_generations(generations)
    if report_on not in REPORT_MODES:
        raise ValueError("unknown report mode")
    p = _check_probability(p)
    if report_on == "separate_block":
        _check_items_candidates(items, candidates)
        _check_threshold(threshold, items)
        reported = [p] * (generations + 1)
    else:
        one = fresh_block_reported(items, candidates, p, threshold)["expected_reported"]
        reported = [p] + [one] * generations
    return {"report_on": report_on, "expected_reported": reported,
            "expected_true": [p] * (generations + 1), "readout_value": p,
            "readout_gap": [value - p for value in reported]}


# --------------------------------------------------------------------------
# mutation chain: candidates correlated with the incumbent item by item
# --------------------------------------------------------------------------

def _check_state(c, items):
    if type(c) is not int or not 0 <= c <= items:
        raise ValueError("c must be a state in 0..items")


def mutation_candidate_law(items, p, q, c) -> list[Q]:
    """Law of one candidate's count given the incumbent's count ``c``.

    On each item, independently, the candidate copies the incumbent's
    outcome with probability ``1 - q`` and otherwise redraws it as
    Bernoulli(p).  An item the incumbent got right is lost iff it is redrawn
    and fails, probability ``q (1 - p)``; an item the incumbent got wrong is
    gained iff it is redrawn and succeeds, probability ``q p``.  Hence
    ``count = c - L + U`` with ``L ~ Bin(c, q (1 - p))`` and
    ``U ~ Bin(n - c, q p)`` independent.  The law depends on the incumbent's
    outcome vector only through ``c`` because items are exchangeable and
    the perturbation is the same on every item, so the chain on ``c`` is
    Markov.  ``q = 1`` gives ``Bin(c, p) + Bin(n - c, p) = Bin(n, p)``, the
    independent chain; ``q = 0`` gives the point mass at ``c``.  Marginally
    (incumbent ``~ Bin(n, p)``) a candidate is again ``Bin(n, p)``, with
    per-item outcome correlation ``1 - q`` to the incumbent.
    """

    if type(items) is not int or items < 1:
        raise ValueError("items must be a positive integer")
    p = _check_probability(p)
    q = _check_probability(q, "q")
    _check_state(c, items)
    loss = _binomial_pmf(c, q * (1 - p))
    gain = _binomial_pmf(items - c, q * p)
    law = [Q(0)] * (items + 1)
    for lost, mass_lost in enumerate(loss):
        for gained, mass_gained in enumerate(gain):
            law[c - lost + gained] += mass_lost * mass_gained
    return law


def mutation_transition_kernel(items, candidates, p, q, threshold) -> list[list[Q]]:
    """As ``transition_kernel`` with ``K`` i.i.d. mutation candidates given
    ``c``: ``kernel[c][c] = F_c(cap)^K``, ``kernel[c][j] = P(M = j)`` for
    ``j > cap``, where ``F_c`` is the CDF of ``mutation_candidate_law``."""

    _check_items_candidates(items, candidates)
    threshold = _check_threshold(threshold, items)
    rows = []
    for c in range(items + 1):
        cdf, running = [], Q(0)
        for mass in mutation_candidate_law(items, p, q, c):
            running += mass
            cdf.append(running)
        cap = min(items, c + threshold[c])
        row = [Q(0)] * (items + 1)
        row[c] = cdf[cap]**candidates
        for j in range(cap + 1, items + 1):
            row[j] = cdf[j]**candidates - cdf[j - 1]**candidates
        rows.append(row)
    return rows


def mutation_state_distribution(items, candidates, p, q, threshold, generations,
                                initial=None) -> list[list[Q]]:
    """Exact state law after ``0..generations`` generations of the mutation
    chain; ``initial`` defaults to ``Bin(items, p)``."""

    _check_generations(generations)
    kernel = mutation_transition_kernel(items, candidates, p, q, threshold)
    current = (_binomial_pmf(items, Q(p)) if initial is None
               else _check_distribution(initial, items))
    return _propagate(kernel, current, generations)


def mutation_trajectory(items, candidates, p, q, threshold, generations) -> dict[str, object]:
    """Per-generation expectations for the mutation chain under the null.

    Acceptance never lowers ``c`` (it requires ``M > c + t(c) >= c``), so
    ``c_g`` is pointwise non-decreasing and ``rho_g`` is non-decreasing in
    ``g`` and bounded by ``1 - p`` for every ``q``.  Unlike the independent
    chain, ``c_G`` is not a running maximum of i.i.d. draws: the candidate
    law moves with the state, so Proposition 1 has no analogue here.
    """

    history = mutation_state_distribution(items, candidates, p, q, threshold, generations)
    kernel = mutation_transition_kernel(items, candidates, p, q, threshold)
    threshold = _check_threshold(threshold, items)
    alpha = tuple(1 - kernel[c][c] for c in range(items + 1))
    reported = [sum(c * mass for c, mass in enumerate(dist)) / items for dist in history]
    acceptance = [sum(mass * alpha[c] for c, mass in enumerate(dist)) for dist in history[:-1]]
    p, q = Q(p), Q(q)
    return {
        "items": items, "candidates": candidates, "p": p, "q": q, "threshold": threshold,
        "generations": generations,
        "expected_reported": reported, "expected_true": [p] * (generations + 1),
        "readout_value": p, "readout_gap": [value - p for value in reported],
        "acceptance_probability": acceptance,
        "acceptance_by_state": alpha,
        "expected_acceptances": sum(acceptance, Q(0)),
        "ceiling_mass": history[-1][items],
        "final_distribution": history[-1],
    }


# --------------------------------------------------------------------------
# drift model: true gains on a finite lattice
# --------------------------------------------------------------------------

def drift_levels(p0, step) -> tuple[Q, ...]:
    """Lattice ``p(i) = min(1, p0 + i * step)``, ending at the first level
    that reaches one; the index is clamped there."""

    p0 = _check_probability(p0, "p0")
    if type(step) is bool or not isinstance(step, (int, Q)) or step <= 0:
        raise ValueError("step must be a positive Fraction")
    levels, index = [], 0
    while p0 + index * step < 1:
        levels.append(p0 + index * step)
        index += 1
    levels.append(Q(1))
    return tuple(levels)


def drift_trajectory(items, candidates, p0, step, gain, threshold, generations) -> dict[str, object]:
    """Exact chain on ``(count, level)`` with true gains.

    The incumbent at level ``i`` has true success probability ``p(i)``.  Each
    candidate independently draws a gain multiple ``m`` from ``gain``
    (``{m: probability}``), has true probability ``p(min(top, i + m))`` and
    count ``C ~ Bin(n, p(.))``.  ``M`` is the best count; the policy accepts
    iff ``M > c + t(c)``; on acceptance the state becomes ``(M, i + m*)``
    where ``m*`` is the gain of the accepted candidate.  Ties among candidates
    go to the first index, which for exchangeable candidates gives the
    conditional law ``P(m | C = M)``; so
    ``P(M = j, m* = m) = P(M = j) * gain[m] * Bin(n, p(i + m))(j) / mix(j)``
    with ``mix`` the candidate count mixture.

    Reported value: ``E[c_g] / n``.  True value: ``E[p(i_g)]``.  Readout gap:
    their difference.  Initial state ``(c_0, 0)`` with ``c_0 ~ Bin(n, p0)``.
    ``gain`` is one mapping (the same law every generation) or a sequence of
    ``generations`` mappings (a schedule; the chain is then time-inhomogeneous
    and the DP uses generation ``g``'s kernel at step ``g``).
    Boundaries: candidates independent of the incumbent, gains i.i.d. across
    candidates within a generation, lattice capped at one.
    """

    _check_items_candidates(items, candidates)
    _check_generations(generations)
    threshold = _check_threshold(threshold, items)
    schedule = _check_gain_schedule(gain, generations)
    levels = drift_levels(p0, step)
    top = len(levels) - 1
    tables: dict[tuple, tuple[list, list]] = {}

    def table(gain_law):
        key = tuple(sorted(gain_law.items()))
        if key in tables:
            return tables[key]
        stay_power, joint = [], []
        for level in range(top + 1):
            parts = {m: _binomial_pmf(items, levels[min(top, level + m)]) for m in gain_law}
            mixture = [sum(gain_law[m] * parts[m][j] for m in gain_law) for j in range(items + 1)]
            cdf, running = [], Q(0)
            for mass in mixture:
                running += mass
                cdf.append(running)
            best = [cdf[j]**candidates - (cdf[j - 1]**candidates if j else Q(0))
                    for j in range(items + 1)]
            per_count = []
            for j in range(items + 1):
                if mixture[j]:
                    per_count.append({m: best[j] * gain_law[m] * parts[m][j] / mixture[j]
                                      for m in gain_law})
                else:
                    per_count.append({m: Q(0) for m in gain_law})
            joint.append(per_count)
            stay_power.append([cdf[j]**candidates for j in range(items + 1)])
        tables[key] = (stay_power, joint)
        return tables[key]

    current = {(c, 0): mass for c, mass in enumerate(_binomial_pmf(items, levels[0])) if mass}
    history, acceptance, true_gain_acceptance = [current], [], []
    for gain_law in schedule:
        stay_power, joint = table(gain_law)
        following, accepted, accepted_with_gain = {}, Q(0), Q(0)
        for (c, level), mass in current.items():
            cap = min(items, c + threshold[c])
            stay = stay_power[level][cap]
            following[(c, level)] = following.get((c, level), Q(0)) + mass * stay
            accepted += mass * (1 - stay)
            for j in range(cap + 1, items + 1):
                for m, prob in joint[level][j].items():
                    if prob:
                        key = (j, min(top, level + m))
                        following[key] = following.get(key, Q(0)) + mass * prob
                        if m > 0 and level < top:
                            accepted_with_gain += mass * prob
        current = {key: mass for key, mass in following.items() if mass}
        history.append(current)
        acceptance.append(accepted)
        true_gain_acceptance.append(accepted_with_gain)

    reported = [sum(mass * c for (c, _), mass in dist.items()) / items for dist in history]
    true = [sum(mass * levels[level] for (_, level), mass in dist.items()) for dist in history]
    return {
        "items": items, "candidates": candidates, "p0": levels[0], "step": Q(step),
        "gain_schedule": schedule, "threshold": threshold, "generations": generations,
        "levels": levels,
        "expected_reported": reported, "expected_true": true,
        "readout_gap": [r - t for r, t in zip(reported, true)],
        "acceptance_probability": acceptance,
        "true_gain_acceptance_probability": true_gain_acceptance,
        "expected_acceptances": sum(acceptance, Q(0)),
        "expected_true_gain_acceptances": sum(true_gain_acceptance, Q(0)),
        "mass_per_generation": [sum(dist.values(), Q(0)) for dist in history],
        "final_distribution": {f"{c},{level}": mass for (c, level), mass in sorted(history[-1].items())},
        "state_history": history,
    }


# --------------------------------------------------------------------------
# one generation, gate versus naive, under a fixed true gain
# --------------------------------------------------------------------------

def one_step_gap_change(items, candidates, p_inc, delta, c, t) -> dict[str, object]:
    """One generation from incumbent count ``c`` and true value ``p_inc``
    when every candidate has true probability ``p_inc + delta``.

    ``M`` is the max of ``K`` i.i.d. ``Bin(n, p_inc + delta)`` counts.  On
    acceptance the reported score changes by ``(M - c) / n`` and the true
    value by ``delta``; otherwise neither moves.  Naive accepts iff
    ``M > c``; the gate iff ``M > c + t``.  Since
    ``1{M > c} - 1{M > c + t} = 1{c < M <= c + t}``,

        naive_change - gate_change
            = E[ ((M - c) / n - delta) * 1{c < M <= c + t} ].

    On the window ``1 <= M - c <= t``, so the integrand lies in
    ``[1/n - delta, t/n - delta]``: (i) ``delta <= 1/n`` makes it ``>= 0``
    (the gate lowers the one-generation gap change); (ii)
    ``delta >= t/n`` makes it ``<= 0`` (the gate raises it); (iii) in
    between the sign depends on the law of ``M`` on the window.  When both
    (i) and (ii) hold (``t <= 1`` and ``delta = 1/n``, or ``t = 0``) the
    difference is exactly zero.  ``t`` is the gate's threshold at ``c``.
    All quantities are exact rationals.
    """

    _check_items_candidates(items, candidates)
    p_inc = _check_probability(p_inc, "p_inc")
    if type(delta) is bool or not isinstance(delta, (int, Q)) or delta < 0 or p_inc + delta > 1:
        raise ValueError("delta must be a non-negative Fraction with p_inc + delta <= 1")
    delta = Q(delta)
    _check_state(c, items)
    if type(t) is not int or t < 0:
        raise ValueError("t must be a non-negative integer")
    best = best_of_pmf(items, candidates, p_inc + delta)

    def change(cap):
        return sum((Q(j - c, items) - delta) * best[j] for j in range(cap + 1, items + 1))

    naive, gate = change(c), change(min(items, c + t))
    window = range(c + 1, min(items, c + t) + 1)
    window_integral = sum(((Q(j - c, items) - delta) * best[j] for j in window), Q(0))
    window_mass = sum((best[j] for j in window), Q(0))
    case_i, case_ii = delta <= Q(1, items), delta >= Q(t, items)
    predicted = ("zero" if case_i and case_ii else "nonnegative" if case_i
                 else "nonpositive" if case_ii else "undetermined")
    return {"items": items, "candidates": candidates, "p_inc": p_inc, "delta": delta,
            "c": c, "t": t, "naive_change": naive, "gate_change": gate,
            "difference": naive - gate, "window_integral": window_integral,
            "window_mass": window_mass,
            "case_i_delta_at_most_one_over_n": case_i,
            "case_ii_delta_at_least_t_over_n": case_ii,
            "predicted_sign_of_difference": predicted}


def drift_gap_increment_from_one_step(trajectory, generation) -> Q:
    """``rho_{g+1} - rho_g`` of a fixed-gain drift trajectory recomputed from
    ``one_step_gap_change`` on the state law at ``g``: the consistency
    check between the one-step theorem and the drift DP.  Requires the
    gain law ``{1: 1}`` (every candidate carries exactly one lattice step)."""

    schedule = trajectory["gain_schedule"]
    if not 0 <= generation < len(schedule) or schedule[generation] != {1: Q(1)}:
        raise ValueError("generation must index a fixed-gain generation of the trajectory")
    items, candidates = trajectory["items"], trajectory["candidates"]
    levels, threshold = trajectory["levels"], trajectory["threshold"]
    top = len(levels) - 1
    increment = Q(0)
    for (c, level), mass in trajectory["state_history"][generation].items():
        nxt = min(top, level + 1)
        step = one_step_gap_change(items, candidates, levels[level], levels[nxt] - levels[level],
                                   c, threshold[c])
        increment += mass * step["gate_change"]
    return increment


# --------------------------------------------------------------------------
# readers: phantom share, readout-gap series, divergence flags
# --------------------------------------------------------------------------

def _check_window(trajectory, start, end):
    last = len(trajectory["expected_reported"]) - 1
    if (type(start) is not int or type(end) is not int
            or not 0 <= start < end <= last):
        raise ValueError("window must satisfy 0 <= start < end <= generations")


def phantom_share(trajectory, start, end) -> dict[str, object]:
    """``1 - (true gain) / (reported gain)`` over generations ``start..end``.

    ``None`` when the reported gain is zero.  Under the null the true gain is
    zero, so the share is one whenever anything was reported as gained.
    """

    _check_window(trajectory, start, end)
    reported = trajectory["expected_reported"][end] - trajectory["expected_reported"][start]
    true = trajectory["expected_true"][end] - trajectory["expected_true"][start]
    share = None if reported == 0 else 1 - true / reported
    return {"start": start, "end": end, "reported_gain": reported,
            "true_gain": true, "phantom_share": share}


def late_early_ratio(trajectory, split) -> dict[str, object]:
    """Gain over ``split..G`` divided by gain over ``0..split``, for reported
    and for true value; the simulation's P5 quantity."""

    last = len(trajectory["expected_reported"]) - 1
    if type(split) is not int or not 0 < split < last:
        raise ValueError("split must lie strictly inside the horizon")
    out = {}
    for key in ("expected_reported", "expected_true"):
        series = trajectory[key]
        early, late = series[split] - series[0], series[last] - series[split]
        out[key] = None if early == 0 else late / early
    return {"split": split, "reported_ratio": out["expected_reported"],
            "true_ratio": out["expected_true"]}


def readout_gap_series(trajectory) -> list[Q]:
    """``rho_g = E[c_g] / n - E[p_g]`` for ``g = 0..G``: the readout gap of
    the insertions note, evaluated on the chain's expectations."""

    return [r - t for r, t in zip(trajectory["expected_reported"], trajectory["expected_true"])]


def divergence_check(trajectory, readout_generations, margin) -> dict[str, object]:
    """Feed the DP's expected selection and true scores at the listed
    generations to ``divergence_flags`` and record what it flagged.

    This is a check on means: the chain supplies ``E[c_g] / n`` as the
    selection-set score and ``E[p_g]`` as the readout-set score.  A flag at
    an interval means the expected selection gain exceeded the expected true
    gain by more than ``margin`` over that interval.
    """

    generations = list(readout_generations)
    last = len(trajectory["expected_reported"]) - 1
    if any(type(g) is not int or not 0 <= g <= last for g in generations):
        raise ValueError("readout generations must index the trajectory")
    points = [(g, trajectory["expected_reported"][g], trajectory["expected_true"][g])
              for g in generations]
    rows = divergence_flags(points, margin)
    rho = readout_gap_series(trajectory)
    expected = [rho[g1] - rho[g0] > margin for g0, g1 in zip(generations, generations[1:])]
    flags = [row["flagged"] for row in rows]
    return {"readout_generations": tuple(generations), "margin": Q(margin),
            "rows": rows, "flags": flags,
            "expected_flags_from_rho_increments": expected,
            "flags_match_rho_increments": flags == expected,
            "check_on": "expectations, not sample paths"}


# --------------------------------------------------------------------------
# brute-force enumerations (independent of the DP)
# --------------------------------------------------------------------------

def _path_weight(bits, p):
    ones = sum(bits)
    return p**ones * (1 - p)**(len(bits) - ones)


def brute_force_reuse_distribution(items, candidates, p, threshold, generations) -> list[Q]:
    """Enumerate every item outcome of the incumbent and of all ``G K``
    candidates on the reused set, run the policy on each, and tally the final
    state.  Limited to 16 item outcomes."""

    _check_items_candidates(items, candidates)
    _check_generations(generations)
    p = _check_probability(p)
    threshold = _check_threshold(threshold, items)
    bits = items * (1 + generations * candidates)
    if bits > _BRUTE_FORCE_BIT_LIMIT:
        raise ValueError("brute force limited to 16 item outcomes")
    distribution = [Q(0)] * (items + 1)
    for outcome in product((0, 1), repeat=bits):
        c, position = sum(outcome[:items]), items
        for _ in range(generations):
            best = max(sum(outcome[position + k * items:position + (k + 1) * items])
                       for k in range(candidates))
            position += candidates * items
            if best > c + threshold[c]:
                c = best
        distribution[c] += _path_weight(outcome, p)
    return distribution


def brute_force_fresh_reported(items, candidates, p, threshold, generations, report_on) -> list[Q]:
    """Enumerate every item outcome of the fresh arm and return the expected
    reported score at each generation.

    Each generation draws a fresh block on which the incumbent (``n`` bits)
    and the ``K`` candidates (``K n`` bits) are scored.  ``selection_block``
    reports the accepted controller's count on that block.
    ``separate_block`` draws a further ``n`` readout bits for the accepted
    controller and reports those.  Generation ``0`` reports the incumbent's
    own fresh count.
    """

    _check_items_candidates(items, candidates)
    _check_generations(generations)
    p = _check_probability(p)
    threshold = _check_threshold(threshold, items)
    if report_on not in REPORT_MODES:
        raise ValueError("unknown report mode")
    per_generation = items * (candidates + 1) + (items if report_on == "separate_block" else 0)
    bits = items + generations * per_generation
    if bits > _BRUTE_FORCE_BIT_LIMIT:
        raise ValueError("brute force limited to 16 item outcomes")
    expected = [Q(0)] * (generations + 1)
    for outcome in product((0, 1), repeat=bits):
        weight = _path_weight(outcome, p)
        expected[0] += weight * sum(outcome[:items])
        position = items
        for g in range(1, generations + 1):
            incumbent = sum(outcome[position:position + items])
            position += items
            best = max(sum(outcome[position + k * items:position + (k + 1) * items])
                       for k in range(candidates))
            position += candidates * items
            reported = best if best > incumbent + threshold[incumbent] else incumbent
            if report_on == "separate_block":
                reported = sum(outcome[position:position + items])
                position += items
            expected[g] += weight * reported
    return [value / items for value in expected]


def brute_force_drift_distribution(items, candidates, p0, step, gain, threshold,
                                   generations) -> dict[tuple[int, int], Q]:
    """Enumerate every gain draw and every item outcome of the drift model,
    weighting each path by its exact probability, and tally the final
    ``(count, level)`` state."""

    _check_items_candidates(items, candidates)
    _check_generations(generations)
    threshold = _check_threshold(threshold, items)
    schedule = _check_gain_schedule(gain, generations)
    levels = drift_levels(p0, step)
    top = len(levels) - 1
    draws = generations * candidates
    bits = items * (1 + draws)
    supports = [sorted(schedule[g]) for g in range(generations) for _ in range(candidates)]
    combinations = 1
    for support in supports:
        combinations *= len(support)
    if bits > _BRUTE_FORCE_BIT_LIMIT or combinations > _BRUTE_FORCE_GAIN_COMBINATIONS:
        raise ValueError("brute force limited to 16 item outcomes and 64 gain combinations")
    distribution: dict[tuple[int, int], Q] = {}
    for gains in product(*supports):
        gain_weight = Q(1)
        for index, m in enumerate(gains):
            gain_weight *= schedule[index // candidates][m]
        for outcome in product((0, 1), repeat=bits):
            weight = gain_weight * _path_weight(outcome[:items], levels[0])
            c, level, position = sum(outcome[:items]), 0, items
            for g in range(generations):
                best, best_multiple = -1, None
                for k in range(candidates):
                    m = gains[g * candidates + k]
                    block = outcome[position:position + items]
                    position += items
                    weight *= _path_weight(block, levels[min(top, level + m)])
                    count = sum(block)
                    if count > best:
                        best, best_multiple = count, m
                if best > c + threshold[c]:
                    c, level = best, min(top, level + best_multiple)
            if weight:
                distribution[(c, level)] = distribution.get((c, level), Q(0)) + weight
    return distribution


_MUTATION_BRUTE_FORCE_PATH_LIMIT = 2**16


def brute_force_mutation_distribution(items, candidates, p, q, threshold, generations) -> list[Q]:
    """Enumerate the incumbent's item outcomes and, for every candidate item,
    one of three symbols (copy the incumbent's outcome, redraw and fail,
    redraw and succeed, weights ``1 - q``, ``q (1 - p)``, ``q p``), tracking
    outcome *vectors* rather than counts so that the Markov-on-count claim
    is itself under test.  Ties among candidates go to the first index."""

    _check_items_candidates(items, candidates)
    _check_generations(generations)
    p = _check_probability(p)
    q = _check_probability(q, "q")
    threshold = _check_threshold(threshold, items)
    symbols = items * generations * candidates
    if 2**items * 3**symbols > _MUTATION_BRUTE_FORCE_PATH_LIMIT:
        raise ValueError("brute force limited to 2^16 paths")
    symbol_weight = (1 - q, q * (1 - p), q * p)
    distribution = [Q(0)] * (items + 1)
    for incumbent in product((0, 1), repeat=items):
        base = _path_weight(incumbent, p)
        for choice in product((0, 1, 2), repeat=symbols):
            weight = base
            for symbol in choice:
                weight *= symbol_weight[symbol]
            if not weight:
                continue
            vector, c, position = incumbent, sum(incumbent), 0
            for _ in range(generations):
                best, best_vector = -1, None
                for _ in range(candidates):
                    block = choice[position:position + items]
                    position += items
                    candidate = tuple(vector[j] if block[j] == 0 else block[j] - 1
                                      for j in range(items))
                    count = sum(candidate)
                    if count > best:
                        best, best_vector = count, candidate
                if best > c + threshold[c]:
                    vector, c = best_vector, best
            distribution[c] += weight
    return distribution


# --------------------------------------------------------------------------
# Proposition 8: naive versus gated chains under a fixed true gain
# --------------------------------------------------------------------------
#
# Fix the gain law {1: 1} (every accepted candidate carries one lattice
# step; a deterministic multiple m is the same chain on the coarser lattice
# p0 + i m step).  Write P for the naive kernel and Q for the kernel of any
# threshold rule t >= 0 on states x = (c, i), u_k = P^k f, w_k = Q^k f.
#
# Theorem (true value).  For every non-decreasing phi on levels, f = phi(i),
# every t >= 0, every non-decreasing level function and every state x:
# w_k(x) <= u_k(x) for all k.  Proof in three steps, all finite inductions.
#   (M1)/(M2)  The naive iterates u_k are non-increasing in c and
#     non-decreasing in i.  Downward induction on the level: (M1) at level l
#     follows from (M2) at level l by the first-divergence identity
#     u_k(c,l) - u_k(c+1,l) = sum_s F_l(c)^(s-1) pi_l(c+1) [u_{k-s}(c+1,l+1)
#     - u_{k-s}(c+1,l)]; (M2) at level l follows from (M1) at level l+2 by
#     expanding the lower chain two jumps and the upper chain one jump: the
#     upper waits less (sigma <=_st tau), lands below the lower's second
#     landing (M_{l+1} | > c <=_st M_{l+1} | > x for x > c), and u(., l+2)
#     is non-increasing in the count and non-decreasing in time.  Base: at
#     the top levels u is constant in c or equals phi(l) + (phi(l+1) -
#     phi(l)) (1 - F_l(c)^k).
#   (S)  w_k(c,i) <= u_k(j,i+1) for c < j <= a(c) = min(n, c + t(c)): one
#     gated step, then (S)_{k-1} on the self-loop, the theorem at k-1 on the
#     landings J > a(c) >= j, (M1) to pull every landing back to j, and
#     u_{k-1} <= u_k.
#   (D)  Couple both chains on the same draws from x; they agree until the
#     first generation at which the naive accepts a draw M in (c, a(c)]
#     that the gate rejects, and then the difference is u_{k-s}(M,i+1) -
#     w_{k-s}(c,i) >= 0 by (S).
# Corollary: the level is stochastically dominated (phi = 1{i >= l}) and
# E[p(i_g)] is ordered, from every initial law, at every horizon.
#
# The count.  E[c_infinity] = n for the naive chain whenever p(1) > 0, so
# the limit ordering is trivial; at finite horizons no proof is known.  The
# routes that work for the level fail provably: the naive count iterates
# are not monotone in c (a lower count earns a free level), so neither the
# pathwise coupling, nor the gate-cone condition u_k(j,i+1) >= u_k(c,i) on
# the naive iterates, nor the policy-improvement condition on the gated
# iterates, nor the componentwise condition u_k(c,i) <= u_k(c',i') for
# c <= c', i < i' holds (``dominance_structure_fixture`` records witnesses).
# What holds on every enumerated cell, at every state and horizon, is the
# ordering itself, its hitting-probability form P(c_k >= m), and (S) for
# the count.  Lowering an arbitrary threshold is NOT monotone in general:
# ``threshold_pair_counterexample`` gives two rules t <= t' with the higher
# one ahead in true value.  All of this is finite evidence only.


def _check_levels(levels):
    try:
        levels = tuple(levels)
    except TypeError:
        raise ValueError("levels must be a sequence of rationals") from None
    if (not levels or any(type(x) is bool or not isinstance(x, (int, Q)) or not 0 <= x <= 1 for x in levels)
            or any(b < a for a, b in zip(levels, levels[1:]))):
        raise ValueError("levels must be non-decreasing rationals in [0, 1]")
    return tuple(Q(x) for x in levels)


_PMF_CACHE: dict[tuple[int, Q], list[Q]] = {}


def _cached_pmf(items, p):
    key = (items, p)
    if key not in _PMF_CACHE:
        _PMF_CACHE[key] = _binomial_pmf(items, p)
    return _PMF_CACHE[key]


def drift_kernel(items, candidates, levels, gain_law, threshold) -> dict[tuple[int, int], list[tuple[tuple[int, int], Q]]]:
    """Exact one-generation kernel of the drift chain on ``(count, level)``.

    ``kernel[(c, i)]`` lists ``((c', i'), probability)`` with the self-loop
    first.  The same chain as ``drift_trajectory`` on the lattice ``levels``
    (checked by test), with the joint law of the best count and its gain
    written as ``gain[m] Bin(n, p(i+m))(j) S_j``, ``S_j = sum_{k=1}^K
    F(j-1)^(k-1) F(j)^(K-k)`` summing the first-max tie rule over the index
    of the winning candidate; ``mix(j) S_j = F(j)^K - F(j-1)^K``, so the
    denominators stay powers of the binomial denominators.
    """

    _check_items_candidates(items, candidates)
    levels = _check_levels(levels)
    gain_law = _check_gain(gain_law)
    threshold = _check_threshold(threshold, items)
    top = len(levels) - 1
    kernel = {}
    for level in range(top + 1):
        parts = {m: _cached_pmf(items, levels[min(top, level + m)]) for m in gain_law}
        mixture = [sum(gain_law[m] * parts[m][j] for m in gain_law) for j in range(items + 1)]
        cdf, running = [], Q(0)
        for mass in mixture:
            running += mass
            cdf.append(running)
        ties = []
        for j in range(items + 1):
            lower = cdf[j - 1] if j else Q(0)
            ties.append(sum((lower**(k - 1) * cdf[j]**(candidates - k)
                             for k in range(1, candidates + 1)), Q(0)))
        for c in range(items + 1):
            cap = min(items, c + threshold[c])
            entries = [((c, level), cdf[cap]**candidates)]
            for j in range(cap + 1, items + 1):
                for m in gain_law:
                    prob = gain_law[m] * parts[m][j] * ties[j]
                    if prob:
                        entries.append(((j, min(top, level + m)), prob))
            kernel[(c, level)] = entries
    return kernel


def drift_absorbing_states(items, levels, threshold) -> frozenset[tuple[int, int]]:
    """States ``(c, i)`` with ``c + t(c) >= n``: nothing is ever accepted."""

    levels = _check_levels(levels)
    threshold = _check_threshold(threshold, items)
    return frozenset((c, i) for c in range(items + 1) for i in range(len(levels))
                     if c + threshold[c] >= items)


def drift_expectations(items, candidates, levels, gain, threshold, generations,
                       absorption_tolerance=None) -> dict[str, object]:
    """``E[c_g] / n``, ``E[p(i_g)]`` and the absorbed mass for ``g = 0..G``.

    The state law is propagated as integer numerators over one common
    denominator (the lcm of the kernel's denominators, one factor per
    generation), so no gcd is taken until an expectation is formed; the
    values equal ``drift_trajectory``'s exactly (test).  With
    ``absorption_tolerance`` the run stops at the first generation whose
    mass on ``drift_absorbing_states`` is at least ``1 - tolerance``
    (``stopped_at``); from then on each expectation can move by at most the
    unabsorbed mass.  ``gain`` is one law or a schedule of length ``G``.
    """

    _check_items_candidates(items, candidates)
    _check_generations(generations)
    levels = _check_levels(levels)
    threshold = _check_threshold(threshold, items)
    schedule = _check_gain_schedule(gain, generations)
    if absorption_tolerance is not None:
        absorption_tolerance = _check_probability(absorption_tolerance, "absorption_tolerance")
    absorbing = drift_absorbing_states(items, levels, threshold)
    initial = {(c, 0): mass for c, mass in enumerate(_cached_pmf(items, levels[0])) if mass}
    denominator = lcm(*[mass.denominator for mass in initial.values()])
    current = {x: int(mass * denominator) for x, mass in initial.items()}
    kernels: dict[tuple, tuple[int, dict]] = {}
    reported, true, absorbed = [], [], []

    def record():
        by_level = [0] * len(levels)
        for (_, i), mass in current.items():
            by_level[i] += mass
        reported.append(Q(sum(mass * c for (c, _), mass in current.items()), denominator) / items)
        true.append(sum((level * mass for level, mass in zip(levels, by_level) if mass), Q(0)) / denominator)
        absorbed.append(Q(sum(mass for x, mass in current.items() if x in absorbing), denominator))

    record()
    stopped = None
    for g, law in enumerate(schedule):
        key = tuple(sorted(law.items()))
        if key not in kernels:
            kernel = drift_kernel(items, candidates, levels, law, threshold)
            common = lcm(*[prob.denominator for entries in kernel.values() for _, prob in entries])
            kernels[key] = (common, {x: [(y, int(prob * common)) for y, prob in entries]
                                     for x, entries in kernel.items()})
        common, integer_kernel = kernels[key]
        following: dict[tuple[int, int], int] = {}
        for x, mass in current.items():
            for y, weight in integer_kernel[x]:
                following[y] = following.get(y, 0) + mass * weight
        current = {x: mass for x, mass in following.items() if mass}
        denominator *= common
        record()
        if absorption_tolerance is not None and absorbed[-1] >= 1 - absorption_tolerance:
            stopped = g + 1
            break
    return {"items": items, "candidates": candidates, "levels": levels, "threshold": threshold,
            "generations": generations, "generations_run": len(reported) - 1,
            "expected_reported": reported, "expected_true": true, "absorbed_mass": absorbed,
            "stopped_at": stopped}


def drift_limit(items, candidates, levels, gain_law, threshold) -> dict[str, object]:
    """Exact ``g -> infinity`` expectations of a constant-law drift chain.

    Jumps raise the count, so the states ordered by count form a DAG with
    self-loops; processing counts from ``n`` downward, the limit value at a
    transient state is the mean of the limit values at its landings under
    the law of the jump given that it leaves.  A state that cannot leave
    (``c + t(c) >= n``, or a zero leaving probability) keeps its own value.
    ``by_state[(c, i)] = (E[c_inf], E[p(i_inf)])`` from that state;
    ``expected_reported`` and ``expected_true`` average over the initial
    law ``(Bin(n, p(0)), 0)``.
    """

    kernel = drift_kernel(items, candidates, levels, gain_law, threshold)
    levels = _check_levels(levels)
    threshold = _check_threshold(threshold, items)
    top = len(levels) - 1
    by_state: dict[tuple[int, int], tuple[Q, Q]] = {}
    for c in range(items, -1, -1):
        for i in range(top + 1):
            x = (c, i)
            stay = kernel[x][0][1]
            if c + threshold[c] >= items or stay == 1:
                by_state[x] = (Q(c), levels[i])
                continue
            leave = 1 - stay
            by_state[x] = (sum((prob * by_state[y][0] for y, prob in kernel[x][1:]), Q(0)) / leave,
                           sum((prob * by_state[y][1] for y, prob in kernel[x][1:]), Q(0)) / leave)
    initial = _cached_pmf(items, levels[0])
    return {"by_state": by_state,
            "expected_reported": sum((initial[c] * by_state[(c, 0)][0] for c in range(items + 1)), Q(0)) / items,
            "expected_true": sum((initial[c] * by_state[(c, 0)][1] for c in range(items + 1)), Q(0))}


def kernel_iterates(kernel, f, horizon) -> list[dict[tuple[int, int], Q]]:
    """``P^k f`` on every state for ``k = 0..horizon``: ``P^k f(x)`` is the
    expectation of ``f`` after ``k`` generations from ``x``."""

    _check_generations(horizon)
    current = {x: Q(f(x)) for x in kernel}
    history = [current]
    for _ in range(horizon):
        current = {x: sum((prob * current[y] for y, prob in entries), Q(0))
                   for x, entries in kernel.items()}
        history.append(current)
    return history


DOMINANCE_ITEMS = (4, 8, 16)
DOMINANCE_CANDIDATES = (1, 2, 4)
DOMINANCE_Z = (1, 2, 3)
DOMINANCE_STEPS = (Q(1, 16), Q(1, 8), Q(1, 4), Q(3, 8))
DOMINANCE_P0 = (Q(1, 4), Q(1, 2), Q(0))
DOMINANCE_HORIZON = 100
DOMINANCE_ABSORPTION_TOLERANCE = Q(1, 10**9)
DOMINANCE_SUBSET = {"candidates": (2,), "z": (1, 3)}
DOMINANCE_DECAY_SUBSET = {"candidates": (2,), "z": (1,), "steps": (Q(1, 16), Q(1, 8)), "horizon": 60}


def _render_float(value):
    return None if value is None else round(float(value), 9)


def dominance_search(gain, items_grid, candidates_grid, z_grid, p0_grid, step_grid,
                     horizon, tolerance) -> dict[str, object]:
    """Naive versus ``z``-gate on every cell of the grid: exact expectations
    at every generation up to ``horizon`` (stopping early once both chains
    are within ``tolerance`` of absorption) and, for a constant law, the
    exact limits.  ``gain`` is a constant law or a callable ``horizon ->
    schedule``.  Records the first generation at which the gate is above
    the naive chain in either expectation, with exact values, or ``None``.
    """

    rows, violations, limit_violations, generations, absorbed_cells = {}, [], [], 0, 0
    constant = isinstance(gain, dict)
    for p0 in p0_grid:
        for step in step_grid:
            levels = drift_levels(p0, step)
            for items in items_grid:
                for candidates in candidates_grid:
                    for z in z_grid:
                        thresholds = {"naive": naive_threshold(items), "gate": gate_threshold(items, z)}
                        schedule = gain if constant else gain(horizon)
                        runs = {name: drift_expectations(items, candidates, levels, schedule, thr,
                                                         horizon, tolerance)
                                for name, thr in thresholds.items()}
                        naive, gate = runs["naive"], runs["gate"]
                        compared = min(naive["generations_run"], gate["generations_run"])
                        generations += compared
                        key = f"gain={'law' if constant else 'schedule'},p0={p0},step={step},n={items},K={candidates},z={z}"
                        first = next((g for g in range(compared + 1)
                                      if naive["expected_reported"][g] < gate["expected_reported"][g]
                                      or naive["expected_true"][g] < gate["expected_true"][g]), None)
                        if first is not None:
                            violations.append({"cell": key, "generation": first,
                                               "naive": (naive["expected_reported"][first], naive["expected_true"][first]),
                                               "gate": (gate["expected_reported"][first], gate["expected_true"][first])})
                        limits = None
                        if constant:
                            ln = drift_limit(items, candidates, levels, gain, thresholds["naive"])
                            lg = drift_limit(items, candidates, levels, gain, thresholds["gate"])
                            limits = {"naive": (ln["expected_reported"], ln["expected_true"]),
                                      "gate": (lg["expected_reported"], lg["expected_true"])}
                            if (ln["expected_reported"] < lg["expected_reported"]
                                    or ln["expected_true"] < lg["expected_true"]):
                                limit_violations.append({"cell": key, **limits})
                        absorbed_cells += naive["stopped_at"] is not None and gate["stopped_at"] is not None
                        rows[key] = {
                            "generations_compared": compared,
                            "stopped_at": {"naive": naive["stopped_at"], "gate": gate["stopped_at"]},
                            "first_violation_generation": first,
                            "reported_at_end": {k: _render_float(r["expected_reported"][compared]) for k, r in runs.items()},
                            "true_at_end": {k: _render_float(r["expected_true"][compared]) for k, r in runs.items()},
                            "limit": None if limits is None else {k: tuple(_render_float(v) for v in vals)
                                                                  for k, vals in limits.items()},
                        }
    return {"cells": len(rows), "generations_compared": generations,
            "cells_absorbed_within_horizon": absorbed_cells,
            "violations": violations, "limit_violations": limit_violations,
            "first_violation": violations[0] if violations else None,
            "horizon": horizon, "absorption_tolerance": tolerance,
            "rows": rows, "note": "end-of-horizon and limit values are float renderings; comparisons are exact"}


def dominance_sweep_fixture(full=False) -> dict[str, object]:
    """The three gain laws of section 6 over the dominance grid.  ``full``
    runs all 324 cells per law (the receipt); otherwise the fixed law runs
    on every cell and the other laws on subsets, for the test suite."""

    grid = dict(items_grid=DOMINANCE_ITEMS, candidates_grid=DOMINANCE_CANDIDATES, z_grid=DOMINANCE_Z,
                p0_grid=DOMINANCE_P0, step_grid=DOMINANCE_STEPS,
                horizon=DOMINANCE_HORIZON, tolerance=DOMINANCE_ABSORPTION_TOLERANCE)
    subset = dict(grid, candidates_grid=DOMINANCE_SUBSET["candidates"], z_grid=DOMINANCE_SUBSET["z"])
    decay = dict(grid, candidates_grid=DOMINANCE_DECAY_SUBSET["candidates"], z_grid=DOMINANCE_DECAY_SUBSET["z"],
                 step_grid=DOMINANCE_DECAY_SUBSET["steps"], horizon=DOMINANCE_DECAY_SUBSET["horizon"])
    laws = {
        "fixed": (DRIFT_GAINS["fixed"], grid),
        "two_point": (DRIFT_GAINS["two_point"], grid if full else subset),
        "decaying_two_point": (lambda h: decaying_gain_schedule(h, DRIFT_DECAY_Q0, DRIFT_DECAY_RATIO),
                               grid if full else decay),
    }
    out = {name: dominance_search(gain, **params) for name, (gain, params) in laws.items()}
    return {"full_sweep": full, "by_law": out,
            "cells": sum(s["cells"] for s in out.values()),
            "generations_compared": sum(s["generations_compared"] for s in out.values()),
            "violations": sum(len(s["violations"]) for s in out.values()),
            "limit_violations": sum(len(s["limit_violations"]) for s in out.values()),
            "grid": {"items": DOMINANCE_ITEMS, "candidates": DOMINANCE_CANDIDATES, "z": DOMINANCE_Z,
                     "p0": DOMINANCE_P0, "steps": DOMINANCE_STEPS, "horizon": DOMINANCE_HORIZON,
                     "lattice_note": "p(i) = min(1, p0 + i step); a gain multiple m on step s is the chain on step m s"}}


STRUCTURE_HORIZON = 25
STRUCTURE_CELLS = ((4, 2), (8, 2), (16, 2), (8, 4))
STRUCTURE_STEPS = (Q(1, 16), Q(1, 8), Q(1, 4))
NONGATE_THRESHOLDS = {4: (0, 2, 0, 3, 0), 8: (3, 1, 2, 2, 0, 1, 0, 2, 0), 16: (2, 0, 3, 1, 0, 0, 4, 2, 0, 3, 1, 1, 0, 2, 0, 1, 0)}
NONUNIFORM_LATTICES = ((Q(1, 32), Q(5, 32), Q(9, 16), Q(23, 32), Q(15, 16)),
                       (Q(1, 16), Q(1, 8), Q(3, 4), Q(1)))
INDICATOR_CELLS = ((4, 2), (8, 2))


def threshold_pair_counterexample() -> dict[str, object]:
    """Two rules ``t <= t'`` pointwise (``items = 3``, ``K = 1``, lattice
    ``NONUNIFORM_LATTICES[0]``) for which the higher rule is ahead in true
    value at some state and horizon and in the limit: lowering a threshold
    is not monotone in general; Proposition 8 needs the naive rule."""

    items, candidates, levels = 3, 1, NONUNIFORM_LATTICES[0]
    lower, higher = (0, 2, 0, 0), (1, 2, 0, 1)
    f = lambda x: levels[x[1]]
    law = DRIFT_GAINS["fixed"]
    low = kernel_iterates(drift_kernel(items, candidates, levels, law, lower), f, STRUCTURE_HORIZON)
    high = kernel_iterates(drift_kernel(items, candidates, levels, law, higher), f, STRUCTURE_HORIZON)
    witness = next(((k, x) for k in range(STRUCTURE_HORIZON + 1) for x in sorted(low[k])
                    if high[k][x] > low[k][x]), None)
    limit_low = drift_limit(items, candidates, levels, law, lower)["by_state"]
    limit_high = drift_limit(items, candidates, levels, law, higher)["by_state"]
    limit_witness = next((x for x in sorted(limit_low) if limit_high[x][1] > limit_low[x][1]), None)
    return {"items": items, "candidates": candidates, "levels": levels,
            "lower_threshold": lower, "higher_threshold": higher,
            "finite_witness": None if witness is None else {
                "horizon": witness[0], "state": witness[1],
                "lower_rule_true_value": low[witness[0]][witness[1]],
                "higher_rule_true_value": high[witness[0]][witness[1]]},
            "limit_witness": None if limit_witness is None else {
                "state": limit_witness, "lower_rule_true_value": limit_low[limit_witness][1],
                "higher_rule_true_value": limit_high[limit_witness][1]},
            "higher_rule_ahead_somewhere": witness is not None and limit_witness is not None}


def dominance_structure_fixture() -> dict[str, object]:
    """Every-state checks behind Proposition 8 and its count caveat on
    ``STRUCTURE_CELLS`` x ``STRUCTURE_STEPS`` (lattice ``1/4 + i step``),
    the gates ``z = 1, 2, 3`` and a non-gate rule, plus two non-uniform
    lattices: the naive-iterate monotonicities (M1)/(M2), the intermediate
    (S), the per-state ordering (D) for true value and count, their
    indicator forms (stochastic dominance of level and count), the limit
    ordering by state, and the failure witnesses for the routes that do
    not work for the count."""

    law = DRIFT_GAINS["fixed"]
    H = STRUCTURE_HORIZON
    flags = {"naive_M1_true_value": True, "naive_M2_true_value": True,
             "S_true_value": True, "D_true_value_every_state": True,
             "D_count_every_state": True, "S_count": True,
             "naive_count_gain_nonincreasing_in_count": True,
             "limit_true_value_dominance_every_state": True,
             "limit_M1_true_value": True,
             "level_stochastic_dominance": True, "count_hitting_dominance": True,
             "kernel_rows_sum_to_one": True}
    witnesses = {"gate_cone_fails_on_naive_iterates": None,
                 "componentwise_condition_fails_for_count": None,
                 "policy_improvement_fails_on_gated_iterates": None,
                 "naive_count_not_monotone_in_count": None}
    configs = []
    for items, candidates in STRUCTURE_CELLS:
        for step in STRUCTURE_STEPS:
            configs.append((items, candidates, drift_levels(DRIFT_P0, step), f"n={items},K={candidates},step={step}"))
    for index, levels in enumerate(NONUNIFORM_LATTICES):
        configs.append((8, 2, levels, f"n=8,K=2,lattice={index}"))
    cells = {}
    for items, candidates, levels, name in configs:
        top = len(levels) - 1
        up = lambda i: min(top, i + 1)
        fp = lambda x: levels[x[1]]
        fc = lambda x: Q(x[0])
        naive_kernel = drift_kernel(items, candidates, levels, law, naive_threshold(items))
        flags["kernel_rows_sum_to_one"] &= all(sum(p for _, p in e) == 1 for e in naive_kernel.values())
        states = list(naive_kernel)
        u_p = kernel_iterates(naive_kernel, fp, H)
        u_c = kernel_iterates(naive_kernel, fc, H)
        limit_naive = drift_limit(items, candidates, levels, law, naive_threshold(items))["by_state"]
        m1 = all(u_p[k][(c, i)] >= u_p[k][(c + 1, i)] for k in range(H + 1) for (c, i) in states if c < items)
        m2 = all(u_p[k][(c, i)] <= u_p[k][(c, i + 1)] for k in range(H + 1) for (c, i) in states if i < top)
        flags["naive_M1_true_value"] &= m1
        flags["naive_M2_true_value"] &= m2
        flags["limit_M1_true_value"] &= all(limit_naive[(c, i)][1] >= limit_naive[(c + 1, i)][1]
                                            for (c, i) in states if c < items)
        flags["naive_count_gain_nonincreasing_in_count"] &= all(
            u_c[k][(c, i)] - c >= u_c[k][(c + 1, i)] - (c + 1) for k in range(H + 1) for (c, i) in states if c < items)
        if witnesses["naive_count_not_monotone_in_count"] is None:
            hit = next(((k, c, i) for k in range(H + 1) for (c, i) in states if c < items
                        and u_c[k][(c, i)] > u_c[k][(c + 1, i)]), None)
            if hit:
                k, c, i = hit
                witnesses["naive_count_not_monotone_in_count"] = {
                    "cell": name, "horizon": k, "state": (c, i),
                    "value": u_c[k][(c, i)], "value_at_count_plus_one": u_c[k][(c + 1, i)]}
        if witnesses["componentwise_condition_fails_for_count"] is None:
            hit = next(((k, x, y) for k in range(H + 1) for x in states for y in states
                        if x[0] <= y[0] and x[1] < y[1] and u_c[k][x] > u_c[k][y]), None)
            if hit:
                witnesses["componentwise_condition_fails_for_count"] = {
                    "cell": name, "horizon": hit[0], "lower_state": hit[1], "higher_state": hit[2],
                    "value_lower": u_c[hit[0]][hit[1]], "value_higher": u_c[hit[0]][hit[2]]}
        rules = {f"z={z}": gate_threshold(items, z) for z in GATE_Z_VALUES}
        rules["nongate"] = NONGATE_THRESHOLDS[items]
        entry = {"naive_M1": m1, "naive_M2": m2, "rules": {}}
        for rule, threshold in rules.items():
            a = [min(items, c + threshold[c]) for c in range(items + 1)]
            kernel = drift_kernel(items, candidates, levels, law, threshold)
            w_p = kernel_iterates(kernel, fp, H)
            w_c = kernel_iterates(kernel, fc, H)
            d_p = all(w_p[k][x] <= u_p[k][x] for k in range(H + 1) for x in states)
            d_c = all(w_c[k][x] <= u_c[k][x] for k in range(H + 1) for x in states)
            s_p = all(w_p[k][(c, i)] <= u_p[k][(j, up(i))] for k in range(H + 1)
                      for (c, i) in states for j in range(c + 1, a[c] + 1))
            s_c = all(w_c[k][(c, i)] <= u_c[k][(j, up(i))] for k in range(H + 1)
                      for (c, i) in states for j in range(c + 1, a[c] + 1))
            limit_gate = drift_limit(items, candidates, levels, law, threshold)["by_state"]
            l_p = all(limit_gate[x][1] <= limit_naive[x][1] for x in states)
            flags["D_true_value_every_state"] &= d_p
            flags["D_count_every_state"] &= d_c
            flags["S_true_value"] &= s_p
            flags["S_count"] &= s_c
            flags["limit_true_value_dominance_every_state"] &= l_p
            if witnesses["gate_cone_fails_on_naive_iterates"] is None:
                hit = next(((k, c, i, j) for k in range(H + 1) for (c, i) in states
                            for j in range(c + 1, a[c] + 1) if u_p[k][(j, up(i))] < u_p[k][(c, i)]), None)
                if hit:
                    k, c, i, j = hit
                    witnesses["gate_cone_fails_on_naive_iterates"] = {
                        "cell": name, "rule": rule, "horizon": k, "state": (c, i), "landing": (j, up(i)),
                        "naive_value_at_state": u_p[k][(c, i)], "naive_value_at_landing": u_p[k][(j, up(i))]}
            if witnesses["policy_improvement_fails_on_gated_iterates"] is None:
                hit = next(((k, c, i, j) for k in range(H + 1) for (c, i) in states
                            for j in range(c + 1, a[c] + 1) if w_p[k][(j, up(i))] < w_p[k][(c, i)]), None)
                if hit:
                    k, c, i, j = hit
                    witnesses["policy_improvement_fails_on_gated_iterates"] = {
                        "cell": name, "rule": rule, "horizon": k, "state": (c, i), "landing": (j, up(i)),
                        "gated_value_at_state": w_p[k][(c, i)], "gated_value_at_landing": w_p[k][(j, up(i))]}
            entry["rules"][rule] = {"D_true_value": d_p, "D_count": d_c, "S_true_value": s_p, "S_count": s_c,
                                    "limit_true_value": l_p}
        cells[name] = entry
    indicator = {}
    for items, candidates in INDICATOR_CELLS:
        levels = drift_levels(DRIFT_P0, DRIFT_STEP)
        top = len(levels) - 1
        naive_kernel = drift_kernel(items, candidates, levels, law, naive_threshold(items))
        states = list(naive_kernel)
        for z in (1, 2):
            kernel = drift_kernel(items, candidates, levels, law, gate_threshold(items, z))
            level_ok, count_ok = True, True
            for ell in range(1, top + 1):
                f = lambda x, ell=ell: Q(int(x[1] >= ell))
                u, w = kernel_iterates(naive_kernel, f, H), kernel_iterates(kernel, f, H)
                level_ok &= all(w[k][x] <= u[k][x] for k in range(H + 1) for x in states)
            for m in range(1, items + 1):
                f = lambda x, m=m: Q(int(x[0] >= m))
                u, w = kernel_iterates(naive_kernel, f, H), kernel_iterates(kernel, f, H)
                count_ok &= all(w[k][x] <= u[k][x] for k in range(H + 1) for x in states)
            flags["level_stochastic_dominance"] &= level_ok
            flags["count_hitting_dominance"] &= count_ok
            indicator[f"n={items},K={candidates},z={z}"] = {"level": level_ok, "count": count_ok}
    return {"flags": flags, "witnesses": witnesses, "cells": cells, "indicator_cells": indicator,
            "horizon": H, "threshold_pair": threshold_pair_counterexample(),
            "routes_that_fail_for_the_count": [k for k, v in witnesses.items() if v is not None]}


# --------------------------------------------------------------------------
# fixtures and verify()
# --------------------------------------------------------------------------

NULL_ITEMS = (4, 8, 16)
NULL_CANDIDATES = (1, 2, 4)
NULL_PROBABILITIES = (Q(1, 2), Q(1, 4))
HORIZON = 20
REPORT_GENERATIONS = (1, 5, 10, 20)
GATE_Z_VALUES = (1, 2, 3)
DRIFT_P0, DRIFT_STEP = Q(1, 4), Q(1, 8)
DRIFT_GAINS = {"fixed": {1: Q(1)}, "two_point": {0: Q(3, 4), 1: Q(1, 4)}}
DRIFT_DECAY_Q0, DRIFT_DECAY_RATIO = Q(1, 4), Q(3, 4)
DRIFT_CELLS = ((4, 2), (4, 4), (8, 2), (8, 4), (16, 2))
MUTATION_Q_VALUES = (Q(0), Q(1, 4), Q(1, 2), Q(3, 4), Q(1))
GATE_ORDER_STEPS = (Q(1, 16), Q(1, 8), Q(1, 4))
ONE_STEP_CONSISTENCY_GENERATIONS = (0, 1, 2)


def _cell(items, candidates, p):
    return f"n={items},K={candidates},p={p}"


def _sign(value):
    return "+" if value > 0 else "-" if value < 0 else "0"


def bound_fixture() -> dict[str, object]:
    """Hoeffding and Bernstein bounds against the exact DP gap on every null
    cell and generation, in floats under ``BOUND_TOLERANCE``, with the ratio
    of the exact gap to the Gaussian scale ``sqrt(2 ln(GK+1) p(1-p)/n)``
    tabulated at the report generations."""

    cells, ratios = {}, []
    flags = {"hoeffding_holds": True, "bernstein_holds": True,
             "hoeffding_tighter_at_p_half": True, "bernstein_tighter_somewhere_at_p_quarter": False,
             "ratio_below_one": True, "bound_exceeds_cap_somewhere": False}
    tighter = {"hoeffding": 0, "bernstein": 0}
    for items in NULL_ITEMS:
        for candidates in NULL_CANDIDATES:
            for p in NULL_PROBABILITIES:
                gaps = reuse_trajectory(items, candidates, p, naive_threshold(items), HORIZON)["readout_gap"]
                cap, table, cap_crossing = float(1 - p), {}, None
                for g in range(HORIZON + 1):
                    bounds = naive_gap_bounds(items, candidates, p, g)
                    gap = float(gaps[g])
                    flags["hoeffding_holds"] &= gap <= bounds["hoeffding"] + BOUND_TOLERANCE
                    flags["bernstein_holds"] &= gap <= bounds["bernstein"] + BOUND_TOLERANCE
                    if g:
                        # At p = 1/2 the Gaussian scale equals the Hoeffding
                        # bound, so Bernstein exceeds it by ln m / (3 n).
                        bernstein_tighter = bounds["bernstein"] < bounds["hoeffding"] - BOUND_TOLERANCE
                        tighter["bernstein" if bernstein_tighter else "hoeffding"] += 1
                        if p == Q(1, 2):
                            flags["hoeffding_tighter_at_p_half"] &= not bernstein_tighter
                        else:
                            flags["bernstein_tighter_somewhere_at_p_quarter"] |= bernstein_tighter
                        if cap_crossing is None and bounds["hoeffding"] > cap:
                            cap_crossing = g
                    if g in REPORT_GENERATIONS:
                        ratio = gap / bounds["gaussian_scale"]
                        ratios.append(ratio)
                        flags["ratio_below_one"] &= ratio < 1
                        table[g] = {"exact_gap": gaps[g], "gap_float": gap,
                                    "hoeffding": bounds["hoeffding"],
                                    "bernstein": bounds["bernstein"],
                                    "gaussian_scale": bounds["gaussian_scale"],
                                    "ratio_gap_to_gaussian_scale": ratio,
                                    "hoeffding_slack": bounds["hoeffding"] - gap}
                flags["bound_exceeds_cap_somewhere"] |= cap_crossing is not None
                cells[_cell(items, candidates, p)] = {
                    "by_generation": table, "lattice_cap": cap,
                    "first_generation_hoeffding_exceeds_cap": cap_crossing}
    return {"cells": cells, "flags": flags, "tolerance": BOUND_TOLERANCE,
            "tighter_bound_counts_over_cells_and_generations": tighter,
            "ratio_range_over_cells_and_report_generations": (min(ratios), max(ratios)),
            "note": "bounds are floats from math.log/math.sqrt; the exact gap is a Fraction"}


def mutation_fixture() -> dict[str, object]:
    """The mutation chain on the null cells for ``q`` in ``MUTATION_Q_VALUES``
    under naive and ``z = 1`` policies: structural checks (q = 1 is the
    independent chain, q = 0 never accepts, monotone in G, bounded by the
    cap), and the finite monotonicity-in-q survey with witnesses."""

    cells = {}
    flags = {"rows_sum": True, "upward_only": True, "q1_equals_independent": True,
             "q0_never_accepts": True, "monotone_in_generations": True,
             "bounded_by_cap": True, "rho1_non_decreasing_in_q": True,
             "rho_monotone_in_q_fails_on_every_naive_cell": True,
             "half_q_above_independent_at_horizon_on_naive_cells": True,
             "every_q_above_independent_at_horizon_on_naive_cells_n_ge_8": True,
             "state_n_minus_1_identity": True}
    nonmonotone = {"naive": 0, "gate_z1": 0}
    for items in NULL_ITEMS:
        for candidates in NULL_CANDIDATES:
            for p in NULL_PROBABILITIES:
                for policy, threshold in (("naive", naive_threshold(items)),
                                          ("gate_z1", gate_threshold(items, 1))):
                    series = {}
                    for q in MUTATION_Q_VALUES:
                        kernel = mutation_transition_kernel(items, candidates, p, q, threshold)
                        flags["rows_sum"] &= all(sum(row) == 1 for row in kernel)
                        flags["upward_only"] &= all(
                            row[j] == 0 for c, row in enumerate(kernel) for j in range(c))
                        trajectory = mutation_trajectory(items, candidates, p, q, threshold, HORIZON)
                        gaps = trajectory["readout_gap"]
                        flags["monotone_in_generations"] &= all(b >= a for a, b in zip(gaps, gaps[1:]))
                        flags["bounded_by_cap"] &= all(gap <= 1 - p for gap in gaps)
                        if q == 1:
                            flags["q1_equals_independent"] &= (
                                mutation_state_distribution(items, candidates, p, q, threshold, HORIZON)
                                == state_distribution(items, candidates, p, threshold, HORIZON))
                        if q == 0:
                            flags["q0_never_accepts"] &= (
                                all(gap == 0 for gap in gaps) and trajectory["expected_acceptances"] == 0)
                        series[q] = gaps
                    failing = [g for g in range(HORIZON + 1)
                               if any(series[b][g] < series[a][g]
                                      for a, b in zip(MUTATION_Q_VALUES, MUTATION_Q_VALUES[1:]))]
                    flags["rho1_non_decreasing_in_q"] &= 1 not in failing
                    nonmonotone[policy] += bool(failing)
                    if policy == "naive":
                        flags["rho_monotone_in_q_fails_on_every_naive_cell"] &= bool(failing)
                        flags["half_q_above_independent_at_horizon_on_naive_cells"] &= (
                            series[Q(1, 2)][HORIZON] > series[Q(1)][HORIZON])
                        if items >= 8:
                            flags["every_q_above_independent_at_horizon_on_naive_cells_n_ge_8"] &= all(
                                series[q][HORIZON] > series[Q(1)][HORIZON] for q in MUTATION_Q_VALUES[1:-1])
                    cells[f"{_cell(items, candidates, p)},policy={policy}"] = {
                        "readout_gap_by_q": {str(q): {g: series[q][g] for g in REPORT_GENERATIONS}
                                             for q in MUTATION_Q_VALUES},
                        "generations_where_rho_not_monotone_in_q": failing,
                        "first_generation_rho_not_monotone_in_q": failing[0] if failing else None,
                        "witness_at_first_failure": (
                            {str(q): series[q][failing[0]] for q in MUTATION_Q_VALUES} if failing else None),
                        "q_above_independent_at_horizon": {
                            str(q): series[q][HORIZON] > series[Q(1)][HORIZON] for q in MUTATION_Q_VALUES[1:-1]},
                    }
    # From c = n - 1 one candidate reaches n iff its single wrong item is
    # redrawn and succeeds and none of its n - 1 right items is redrawn and
    # fails: probability q p (1 - q (1 - p))^(n - 1), maximal at
    # q = 1 / (n (1 - p)) and decreasing beyond it, so no state-by-state
    # monotone coupling in q exists.
    identity, peak = {}, {}
    for items in NULL_ITEMS:
        for p in NULL_PROBABILITIES:
            for q in MUTATION_Q_VALUES:
                law = mutation_candidate_law(items, p, q, items - 1)
                flags["state_n_minus_1_identity"] &= law[items] == q * p * (1 - q * (1 - p))**(items - 1)
            identity[f"n={items},p={p}"] = {str(q): mutation_candidate_law(items, p, q, items - 1)[items]
                                             for q in MUTATION_Q_VALUES}
            peak[f"n={items},p={p}"] = Q(1, items * (1 - p))
    return {"cells": cells, "flags": flags, "q_values": MUTATION_Q_VALUES,
            "cells_per_policy": len(NULL_ITEMS) * len(NULL_CANDIDATES) * len(NULL_PROBABILITIES),
            "cells_where_rho_not_monotone_in_q": nonmonotone,
            "state_n_minus_1_up_probability": identity,
            "state_n_minus_1_up_probability_peak_q": peak}


def one_step_fixture() -> dict[str, object]:
    """``one_step_gap_change`` on every state of the drift cells (``z = 1``,
    lattice ``1/4 + i/8``): identity check, sign-by-case tally, the ``n = 8``
    identically-zero difference, and two case (iii) examples of either sign."""

    levels = drift_levels(DRIFT_P0, DRIFT_STEP)
    top = len(levels) - 1
    cells, identity, signs_ok, states = {}, True, True, 0
    for items, candidates in DRIFT_CELLS:
        threshold = gate_threshold(items, 1)
        tally, zero_everywhere = {}, True
        for level in range(top):
            delta = levels[level + 1] - levels[level]
            for c in range(items + 1):
                step = one_step_gap_change(items, candidates, levels[level], delta, c, threshold[c])
                states += 1
                identity &= step["difference"] == step["window_integral"]
                predicted, sign = step["predicted_sign_of_difference"], _sign(step["difference"])
                signs_ok &= {"zero": sign == "0", "nonnegative": sign != "-",
                             "nonpositive": sign != "+", "undetermined": True}[predicted]
                zero_everywhere &= sign == "0"
                tally.setdefault(predicted, {"+": 0, "0": 0, "-": 0})[sign] += 1
        cells[f"n={items},K={candidates},z=1,step={DRIFT_STEP}"] = {
            "threshold": threshold, "one_over_n": Q(1, items),
            "max_threshold_over_n": Q(max(threshold), items), "delta": DRIFT_STEP,
            "sign_tally_by_predicted_case": tally,
            "difference_zero_at_every_state": zero_everywhere}
    examples = {}
    for p_inc in (Q(1, 4), Q(1, 2)):
        step = one_step_gap_change(16, 2, p_inc, Q(3, 32), 8, 2)
        examples[f"n=16,K=2,c=8,t=2,p_inc={p_inc},delta=3/32"] = {
            "predicted": step["predicted_sign_of_difference"],
            "difference": step["difference"], "sign": _sign(step["difference"])}
    both_signs = {e["sign"] for e in examples.values()} == {"+", "-"}
    return {"cells": cells, "states_checked": states,
            "difference_equals_window_integral": identity,
            "sign_matches_predicted_case": signs_ok,
            "n8_difference_identically_zero": all(
                cells[k]["difference_zero_at_every_state"] for k in cells if k.startswith("n=8,")),
            "case_iii_examples": examples, "case_iii_takes_both_signs": both_signs}


def gate_order_fixture() -> dict[str, object]:
    """Fixed-gain drift chains, naive versus ``z = 1``, for steps in
    ``GATE_ORDER_STEPS``: the sign of ``rho^naive_g - rho^gate_g`` against
    the one-step prediction at every generation, the DP-versus-one-step
    consistency identity, and the expectation ordering (naive above gate in
    reported and in true value) that the coupling argument does not reach."""

    cells = {}
    flags = {"lattice_steps_uniform": True, "first_generation_matches_prediction": True,
             "case_ii_gate_above_naive_every_generation": True,
             "case_i_reverses_somewhere": False, "both_cases_zero_at_first_generation": True,
             "one_step_increment_matches_dp": True,
             "naive_dominates_gate_reported": True, "naive_dominates_gate_true": True}
    agreement = {"i": [0, 0], "ii": [0, 0]}
    for items, candidates in DRIFT_CELLS:
        threshold = gate_threshold(items, 1)
        for step in GATE_ORDER_STEPS:
            levels = drift_levels(DRIFT_P0, step)
            flags["lattice_steps_uniform"] &= all(b - a == step for a, b in zip(levels, levels[1:]))
            runs = {policy: drift_trajectory(items, candidates, DRIFT_P0, step, DRIFT_GAINS["fixed"],
                                             thr, HORIZON)
                    for policy, thr in (("naive", naive_threshold(items)), ("gate_z1", threshold))}
            naive, gate = runs["naive"], runs["gate_z1"]
            for policy, run in runs.items():
                for g in ONE_STEP_CONSISTENCY_GENERATIONS:
                    flags["one_step_increment_matches_dp"] &= (
                        drift_gap_increment_from_one_step(run, g)
                        == run["readout_gap"][g + 1] - run["readout_gap"][g])
            diff = [a - b for a, b in zip(naive["readout_gap"], gate["readout_gap"])]
            signs = "".join(_sign(d) for d in diff)
            case_i, case_ii = step <= Q(1, items), step >= Q(max(threshold), items)
            label = "both" if case_i and case_ii else "i" if case_i else "ii" if case_ii else "none"
            if label == "i":
                flags["first_generation_matches_prediction"] &= diff[1] >= 0
                later = [d >= 0 for d in diff[2:]]
                agreement["i"][0] += sum(later)
                agreement["i"][1] += len(later)
                flags["case_i_reverses_somewhere"] |= not all(later)
            elif label == "ii":
                flags["first_generation_matches_prediction"] &= diff[1] <= 0
                later = [d <= 0 for d in diff[2:]]
                agreement["ii"][0] += sum(later)
                agreement["ii"][1] += len(later)
                flags["case_ii_gate_above_naive_every_generation"] &= all(d < 0 for d in diff[1:])
            else:
                flags["first_generation_matches_prediction"] &= diff[1] == 0
                flags["both_cases_zero_at_first_generation"] &= diff[1] == 0
            flags["naive_dominates_gate_reported"] &= all(
                a >= b for a, b in zip(naive["expected_reported"], gate["expected_reported"]))
            flags["naive_dominates_gate_true"] &= all(
                a >= b for a, b in zip(naive["expected_true"], gate["expected_true"]))
            negatives = [g for g, d in enumerate(diff) if d < 0]
            cells[f"n={items},K={candidates},z=1,step={step}"] = {
                "case": label, "one_over_n": Q(1, items),
                "max_threshold_over_n": Q(max(threshold), items),
                "sign_of_naive_minus_gate_gap_by_generation": signs,
                "first_generation_gate_gap_above_naive": negatives[0] if negatives else None,
                "gap_at_horizon": {"naive": naive["readout_gap"][HORIZON], "gate_z1": gate["readout_gap"][HORIZON]},
                "reported_at_horizon": {"naive": naive["expected_reported"][HORIZON],
                                        "gate_z1": gate["expected_reported"][HORIZON]},
                "true_at_horizon": {"naive": naive["expected_true"][HORIZON],
                                    "gate_z1": gate["expected_true"][HORIZON]},
            }
    return {"cells": cells, "flags": flags,
            "later_generation_agreement_counts": {
                k: {"agree": v[0], "of": v[1]} for k, v in agreement.items()},
            "dominance_note": ("expectation ordering checked on the enumerated cells only; "
                               "no monotone coupling is claimed")}


def naive_fixture() -> dict[str, object]:
    """DP against the ``G K + 1`` closed form on every null cell, with
    monotonicity, diminishing increments and the ceiling-mass identity."""

    cells, consistent = {}, {"closed_form": True, "monotone": True, "diminishing": True,
                             "ceiling": True, "one_generation": True, "rows_sum": True}
    for items in NULL_ITEMS:
        for candidates in NULL_CANDIDATES:
            for p in NULL_PROBABILITIES:
                threshold = naive_threshold(items)
                kernel = transition_kernel(items, candidates, p, threshold)
                consistent["rows_sum"] &= all(sum(row) == 1 for row in kernel)
                trajectory = reuse_trajectory(items, candidates, p, threshold, HORIZON)
                gaps = trajectory["readout_gap"]
                closed = [naive_closed_form(items, candidates, p, g)["readout_gap"]
                          for g in range(HORIZON + 1)]
                consistent["closed_form"] &= gaps == closed
                consistent["one_generation"] &= (
                    gaps[1] == selection_inflation(items, candidates + 1, p)["readout_gap"])
                increments = [b - a for a, b in zip(gaps, gaps[1:])]
                consistent["monotone"] &= all(inc >= 0 for inc in increments)
                consistent["diminishing"] &= all(b <= a for a, b in zip(increments, increments[1:]))
                consistent["ceiling"] &= (
                    trajectory["ceiling_mass"] == ceiling_mass_closed_form(items, candidates, p, HORIZON))
                cells[_cell(items, candidates, p)] = {
                    "readout_gap_by_generation": {g: gaps[g] for g in REPORT_GENERATIONS},
                    "expected_acceptances": trajectory["expected_acceptances"],
                    "ceiling_mass_at_horizon": trajectory["ceiling_mass"],
                }
    point = {str(start): running_max_from_point(8, 2, Q(1, 2), 5, start)
             == sum(c * mass for c, mass in enumerate(state_distribution(
                 8, 2, Q(1, 2), naive_threshold(8), 5,
                 [Q(int(c == start)) for c in range(9)])[-1]))
             for start in (0, 4, 8)}
    return {"cells": cells, "consistency": consistent,
            "point_start_matches_running_max_formula": point}


def gated_fixture() -> dict[str, object]:
    """Gate thresholds, false-acceptance tables and gaps for ``z`` in 1, 2, 3."""

    cells, dominated, below_naive, floor_ok = {}, True, True, True
    for items in (8, 16):
        for candidates in (2, 4):
            p = Q(1, 2)
            naive = reuse_trajectory(items, candidates, p, naive_threshold(items), HORIZON)
            naive_alpha = false_acceptance_probability(items, candidates, p, naive_threshold(items))
            for z in GATE_Z_VALUES:
                threshold = gate_threshold(items, z)
                for c, t in enumerate(threshold):
                    q = Q(z)**2 * c * (items - c) / items
                    floor_ok &= t * t <= q < (t + 1) * (t + 1)
                alpha = false_acceptance_probability(items, candidates, p, threshold)
                dominated &= all(a <= b for a, b in zip(alpha, naive_alpha))
                gated = reuse_trajectory(items, candidates, p, threshold, HORIZON)
                below_naive &= all(a <= b for a, b in zip(gated["readout_gap"], naive["readout_gap"]))
                cells[f"{_cell(items, candidates, p)},z={z}"] = {
                    "threshold": threshold,
                    "false_acceptance_by_state": alpha,
                    "absorbing_states": gated["absorbing_states"],
                    "readout_gap_by_generation": {g: gated["readout_gap"][g] for g in REPORT_GENERATIONS},
                    "naive_readout_gap_at_horizon": naive["readout_gap"][HORIZON],
                    "expected_false_acceptances": gated["expected_acceptances"],
                    "naive_expected_false_acceptances": naive["expected_acceptances"],
                }
    return {"cells": cells, "floor_inequality_holds": floor_ok,
            "false_acceptance_never_above_naive": dominated,
            "gap_never_above_naive": below_naive}


def fresh_fixture() -> dict[str, object]:
    """Fresh-set arm: separate readout block gives gap zero; reporting on the
    selection block gives the one-generation gap at every generation."""

    cells, matches, constant, below_reuse, zero = {}, True, True, True, True
    for items in NULL_ITEMS:
        for candidates in (2, 4):
            for p in NULL_PROBABILITIES:
                threshold = naive_threshold(items)
                separate = fresh_trajectory(items, candidates, p, threshold, HORIZON, "separate_block")
                selection = fresh_trajectory(items, candidates, p, threshold, HORIZON, "selection_block")
                reuse = reuse_trajectory(items, candidates, p, threshold, HORIZON)
                one = selection_inflation(items, candidates + 1, p)["readout_gap"]
                zero &= all(gap == 0 for gap in separate["readout_gap"])
                matches &= selection["readout_gap"][1] == one
                constant &= all(gap == one for gap in selection["readout_gap"][1:])
                below_reuse &= (reuse["readout_gap"][1] == one
                                and all(reuse["readout_gap"][g] > one for g in range(2, HORIZON + 1)))
                cells[_cell(items, candidates, p)] = {
                    "separate_block_gap": separate["readout_gap"][HORIZON],
                    "selection_block_gap_every_generation": one,
                    "reuse_gap_at_horizon": reuse["readout_gap"][HORIZON],
                }
    return {"cells": cells, "separate_block_gap_zero": zero,
            "selection_block_gap_is_one_generation_gap": matches,
            "selection_block_gap_constant_in_generations": constant,
            "reuse_gap_exceeds_fresh_gap_after_first_generation": below_reuse}


def drift_fixture() -> dict[str, object]:
    """True gains on the lattice ``1/4 + i/8``: phantom shares, late/early
    ratios and gate ordering for constant and decaying gain laws.

    ``constant`` gain laws (``fixed``, ``two_point``) are the same every
    generation; ``decaying_two_point`` is the schedule
    ``q_g = q0 * ratio**(g - 1)``.  The summary flags record which orderings
    held on every enumerated cell; none is claimed beyond those cells.
    """

    gains = dict(DRIFT_GAINS)
    gains["decaying_two_point"] = decaying_gain_schedule(HORIZON, DRIFT_DECAY_Q0, DRIFT_DECAY_RATIO)
    cells, conserved, nonnegative = {}, True, True
    half = HORIZON // 2
    for items, candidates in DRIFT_CELLS:
        for gain_name, gain in gains.items():
            per_policy = {}
            for policy, threshold in (("naive", naive_threshold(items)),
                                      ("gate_z1", gate_threshold(items, 1))):
                trajectory = drift_trajectory(items, candidates, DRIFT_P0, DRIFT_STEP,
                                              gain, threshold, HORIZON)
                conserved &= all(mass == 1 for mass in trajectory["mass_per_generation"])
                nonnegative &= all(gap >= 0 for gap in trajectory["readout_gap"])
                whole = phantom_share(trajectory, 0, HORIZON)
                early = phantom_share(trajectory, 0, half)
                late = phantom_share(trajectory, half, HORIZON)
                ratios = late_early_ratio(trajectory, half)
                per_policy[policy] = {
                    "reported_at_horizon": trajectory["expected_reported"][HORIZON],
                    "true_at_horizon": trajectory["expected_true"][HORIZON],
                    "readout_gap_at_horizon": trajectory["readout_gap"][HORIZON],
                    "reported_gain": whole["reported_gain"],
                    "true_gain": whole["true_gain"],
                    "phantom_share_whole": whole["phantom_share"],
                    "phantom_share_early_half": early["phantom_share"],
                    "phantom_share_late_half": late["phantom_share"],
                    "late_early_ratio_reported": ratios["reported_ratio"],
                    "late_early_ratio_true": ratios["true_ratio"],
                    "expected_acceptances": trajectory["expected_acceptances"],
                    "expected_true_gain_acceptances": trajectory["expected_true_gain_acceptances"],
                }
            for policy, entry in per_policy.items():
                cells[f"{_cell(items, candidates, DRIFT_P0)},gain={gain_name},policy={policy}"] = entry

    def every(gain_names, policy, predicate):
        return all(predicate(cells[f"{_cell(i, k, DRIFT_P0)},gain={g},policy={policy}"],
                             cells[f"{_cell(i, k, DRIFT_P0)},gain={g},policy=naive"])
                   for i, k in DRIFT_CELLS for g in gain_names)

    def defined(*values):
        return all(value is not None for value in values)

    constant, decaying = ("fixed", "two_point"), ("decaying_two_point",)
    orderings = {
        "two_point_phantom_share_whole_exceeds_half_up_to_8_items": all(
            cells[f"{_cell(i, k, DRIFT_P0)},gain=two_point,policy=naive"]["phantom_share_whole"] > Q(1, 2)
            for i, k in DRIFT_CELLS if i <= 8),
        "decaying_phantom_share_whole_exceeds_half": every(
            decaying, "naive", lambda e, _: e["phantom_share_whole"] > Q(1, 2)),
        "constant_gain_late_phantom_share_below_early": every(
            constant, "naive", lambda e, _: defined(e["phantom_share_late_half"], e["phantom_share_early_half"])
            and e["phantom_share_late_half"] < e["phantom_share_early_half"]),
        "decaying_gain_late_phantom_share_above_early": every(
            decaying, "naive", lambda e, _: defined(e["phantom_share_late_half"], e["phantom_share_early_half"])
            and e["phantom_share_late_half"] > e["phantom_share_early_half"]),
        "constant_gain_reported_late_early_ratio_below_true": every(
            constant, "naive", lambda e, _: defined(e["late_early_ratio_reported"], e["late_early_ratio_true"])
            and e["late_early_ratio_reported"] < e["late_early_ratio_true"]),
        "decaying_gain_reported_late_early_ratio_exceeds_true": every(
            decaying, "naive", lambda e, _: defined(e["late_early_ratio_reported"], e["late_early_ratio_true"])
            and e["late_early_ratio_reported"] > e["late_early_ratio_true"]),
        "fixed_gain_gate_gap_above_naive": every(
            ("fixed",), "gate_z1", lambda e, n: e["readout_gap_at_horizon"] > n["readout_gap_at_horizon"]),
        "decaying_gain_gate_gap_below_naive": every(
            decaying, "gate_z1", lambda e, n: e["readout_gap_at_horizon"] < n["readout_gap_at_horizon"]),
        "gate_gap_ordering_depends_on_gain_law": True,
    }
    orderings["gate_gap_ordering_depends_on_gain_law"] = (
        orderings["fixed_gain_gate_gap_above_naive"] and orderings["decaying_gain_gate_gap_below_naive"])
    return {"cells": cells, "mass_conserved": conserved, "readout_gap_nonnegative": nonnegative,
            "orderings_on_enumerated_cells": orderings,
            "lattice": drift_levels(DRIFT_P0, DRIFT_STEP),
            "decaying_schedule": gains["decaying_two_point"]}


def brute_force_fixture() -> dict[str, object]:
    """DP against literal enumeration of every item outcome on tiny cases."""

    checks = {}
    for p in (Q(1, 2), Q(1, 4)):
        for name, threshold in (("naive", naive_threshold(2)), ("gate_z2", gate_threshold(2, 2))):
            dp = state_distribution(2, 2, p, threshold, 2)[-1]
            checks[f"reuse,n=2,K=2,G=2,p={p},{name}"] = (
                dp == brute_force_reuse_distribution(2, 2, p, threshold, 2))
        checks[f"fresh_selection_block,n=2,K=2,G=2,p={p}"] = (
            fresh_trajectory(2, 2, p, naive_threshold(2), 2, "selection_block")["expected_reported"]
            == brute_force_fresh_reported(2, 2, p, naive_threshold(2), 2, "selection_block"))
        checks[f"fresh_separate_block,n=2,K=2,G=1,p={p}"] = (
            fresh_trajectory(2, 2, p, naive_threshold(2), 1, "separate_block")["expected_reported"]
            == brute_force_fresh_reported(2, 2, p, naive_threshold(2), 1, "separate_block"))
    gains = dict(DRIFT_GAINS)
    gains["decaying_two_point"] = decaying_gain_schedule(2, DRIFT_DECAY_Q0, DRIFT_DECAY_RATIO)
    for gain_name, gain in gains.items():
        for name, threshold in (("naive", naive_threshold(2)), ("gate_z2", gate_threshold(2, 2))):
            dp = drift_trajectory(2, 2, DRIFT_P0, DRIFT_STEP, gain, threshold, 2)["final_distribution"]
            brute = brute_force_drift_distribution(2, 2, DRIFT_P0, DRIFT_STEP, gain, threshold, 2)
            checks[f"drift,n=2,K=2,G=2,gain={gain_name},{name}"] = (
                dp == {f"{c},{level}": mass for (c, level), mass in brute.items()})
    for p in (Q(1, 2), Q(1, 4)):
        for q in (Q(1, 4), Q(1, 2)):
            for name, threshold in (("naive", naive_threshold(2)), ("gate_z2", gate_threshold(2, 2))):
                dp = mutation_state_distribution(2, 2, p, q, threshold, 2)[-1]
                checks[f"mutation,n=2,K=2,G=2,p={p},q={q},{name}"] = (
                    dp == brute_force_mutation_distribution(2, 2, p, q, threshold, 2))
    dp = mutation_state_distribution(3, 2, Q(1, 2), Q(1, 2), (0, 1, 1, 0), 1)[-1]
    checks["mutation,n=3,K=2,G=1,p=1/2,q=1/2,t=(0,1,1,0)"] = (
        dp == brute_force_mutation_distribution(3, 2, Q(1, 2), Q(1, 2), (0, 1, 1, 0), 1))
    return {"checks": checks, "all_match": all(checks.values()),
            "gate_z2_threshold_n2": gate_threshold(2, 2)}


def divergence_fixture() -> dict[str, object]:
    """``divergence_flags`` on DP trajectories of expectations."""

    readouts = (0, 4, 8, 12, 16, 20)
    null = reuse_trajectory(8, 2, Q(1, 2), naive_threshold(8), HORIZON)
    null_check = divergence_check(null, readouts, Q(1, 40))
    flags = null_check["flags"]
    prefix = flags == sorted(flags, reverse=True)
    drift = drift_trajectory(8, 2, DRIFT_P0, DRIFT_STEP, DRIFT_GAINS["two_point"],
                             naive_threshold(8), HORIZON)
    drift_check = divergence_check(drift, readouts, Q(1, 40))
    quiet = divergence_check(fresh_trajectory(8, 2, Q(1, 2), naive_threshold(8), HORIZON,
                                              "selection_block"), readouts, Q(0))
    return {"null": null_check, "null_flags_form_a_prefix": prefix,
            "null_rho_series": readout_gap_series(null),
            "drift": drift_check, "drift_rho_series": readout_gap_series(drift),
            "fresh_selection_block": quiet,
            "fresh_selection_block_never_flags_after_first_interval": not any(quiet["flags"][1:])}


def consistency_fixture() -> dict[str, object]:
    """The Proposition 8 machinery against the earlier DP: ``drift_kernel``
    plus ``drift_expectations`` reproduce ``drift_trajectory`` exactly on
    every drift cell and gain law (naive and ``z = 1``), and the exact limit
    lies within the unabsorbed mass of the DP value at the stopping
    generation on every cell that absorbs within the horizon."""

    gains = dict(DRIFT_GAINS)
    gains["decaying_two_point"] = decaying_gain_schedule(12, DRIFT_DECAY_Q0, DRIFT_DECAY_RATIO)
    levels = drift_levels(DRIFT_P0, DRIFT_STEP)
    matches, limit_within_mass, absorbed = True, True, 0
    for items, candidates in DRIFT_CELLS:
        for gain_name, gain in gains.items():
            for threshold in (naive_threshold(items), gate_threshold(items, 1)):
                dp = drift_trajectory(items, candidates, DRIFT_P0, DRIFT_STEP, gain, threshold, 12)
                fast = drift_expectations(items, candidates, levels, gain, threshold, 12)
                matches &= (dp["expected_reported"] == fast["expected_reported"]
                            and dp["expected_true"] == fast["expected_true"])
    for p0 in DOMINANCE_P0:
        for step in (Q(1, 4), Q(3, 8)):
            levels = drift_levels(p0, step)
            for items, candidates in ((4, 4), (8, 4)):
                for threshold in (naive_threshold(items), gate_threshold(items, 2)):
                    run = drift_expectations(items, candidates, levels, DRIFT_GAINS["fixed"], threshold,
                                             DOMINANCE_HORIZON, DOMINANCE_ABSORPTION_TOLERANCE)
                    if run["stopped_at"] is None:
                        continue
                    absorbed += 1
                    limit = drift_limit(items, candidates, levels, DRIFT_GAINS["fixed"], threshold)
                    slack = 1 - run["absorbed_mass"][-1]
                    limit_within_mass &= (abs(limit["expected_reported"] - run["expected_reported"][-1]) <= slack
                                          and abs(limit["expected_true"] - run["expected_true"][-1]) <= slack)
    return {"fast_expectations_equal_dp": matches, "limit_within_unabsorbed_mass": limit_within_mass,
            "cells_absorbed_within_horizon": absorbed}


def verify(full_sweep: bool = False) -> dict[str, object]:
    """Run all exact fixtures and return machine-readable checks.  With
    ``full_sweep`` the dominance sweep covers all 324 cells per gain law
    (the receipt); otherwise the fixed law covers every cell and the other
    laws run on subsets."""

    naive, gated, fresh = naive_fixture(), gated_fixture(), fresh_fixture()
    drift, brute, divergence = drift_fixture(), brute_force_fixture(), divergence_fixture()
    bounds, mutation = bound_fixture(), mutation_fixture()
    one_step, gate_order = one_step_fixture(), gate_order_fixture()
    consistency, structure = consistency_fixture(), dominance_structure_fixture()
    sweep = dominance_sweep_fixture(full_sweep)
    naive_8_2 = naive["cells"][_cell(8, 2, Q(1, 2))]["readout_gap_by_generation"]
    gated_16_4 = gated["cells"][f"{_cell(16, 4, Q(1, 2))},z=3"]
    orderings = drift["orderings_on_enumerated_cells"]
    bound_flags, mutation_flags, order_flags = bounds["flags"], mutation["flags"], gate_order["flags"]
    structure_flags, witnesses = structure["flags"], structure["witnesses"]
    sweep_laws = sweep["by_law"]
    checks = {
        "kernel_rows_sum_to_one": naive["consistency"]["rows_sum"],
        "naive_dp_equals_closed_form_gk_plus_one": naive["consistency"]["closed_form"],
        "naive_one_generation_is_selection_inflation_k_plus_one": naive["consistency"]["one_generation"],
        "naive_gap_non_decreasing_in_generations": naive["consistency"]["monotone"],
        "naive_gap_increments_non_increasing": naive["consistency"]["diminishing"],
        "naive_ceiling_mass_identity": naive["consistency"]["ceiling"],
        "naive_point_start_matches_running_max": all(
            naive["point_start_matches_running_max_formula"].values()),
        "naive_n8_k2_half_gap_grows_from_one_to_twenty_generations":
            naive_8_2[1] < naive_8_2[5] < naive_8_2[10] < naive_8_2[20],
        "dp_matches_brute_force_enumeration": brute["all_match"],
        "gate_floor_discretization_exact": gated["floor_inequality_holds"],
        "gated_false_acceptance_never_above_naive": gated["false_acceptance_never_above_naive"],
        "gated_gap_never_above_naive": gated["gap_never_above_naive"],
        "gate_z3_n16_k4_gap_below_naive_at_horizon":
            gated_16_4["readout_gap_by_generation"][20] < gated_16_4["naive_readout_gap_at_horizon"],
        "fresh_separate_block_gap_zero": fresh["separate_block_gap_zero"],
        "fresh_selection_block_gap_is_one_generation_gap":
            fresh["selection_block_gap_is_one_generation_gap"],
        "fresh_selection_block_gap_constant_in_generations":
            fresh["selection_block_gap_constant_in_generations"],
        "reuse_gap_exceeds_fresh_gap_after_first_generation":
            fresh["reuse_gap_exceeds_fresh_gap_after_first_generation"],
        "drift_mass_conserved": drift["mass_conserved"],
        "drift_readout_gap_nonnegative_on_cells": drift["readout_gap_nonnegative"],
        "drift_two_point_phantom_share_exceeds_half_up_to_8_items":
            orderings["two_point_phantom_share_whole_exceeds_half_up_to_8_items"],
        "drift_decaying_phantom_share_exceeds_half_on_cells":
            orderings["decaying_phantom_share_whole_exceeds_half"],
        "drift_constant_gain_late_phantom_share_below_early_on_cells":
            orderings["constant_gain_late_phantom_share_below_early"],
        "drift_decaying_gain_late_phantom_share_above_early_on_cells":
            orderings["decaying_gain_late_phantom_share_above_early"],
        "drift_constant_gain_reported_late_early_ratio_below_true_on_cells":
            orderings["constant_gain_reported_late_early_ratio_below_true"],
        "drift_decaying_gain_reported_late_early_ratio_exceeds_true_on_cells":
            orderings["decaying_gain_reported_late_early_ratio_exceeds_true"],
        "drift_gate_gap_ordering_depends_on_gain_law":
            orderings["gate_gap_ordering_depends_on_gain_law"],
        "divergence_flags_match_rho_increments_null":
            divergence["null"]["flags_match_rho_increments"],
        "divergence_flags_fire_then_stop_under_null": divergence["null_flags_form_a_prefix"]
            and divergence["null"]["flags"][0] and not divergence["null"]["flags"][-1],
        "divergence_flags_match_rho_increments_drift":
            divergence["drift"]["flags_match_rho_increments"],
        "divergence_flags_silent_on_constant_fresh_gap":
            divergence["fresh_selection_block_never_flags_after_first_interval"],
        # Part A: proven bounds, compared in floats under BOUND_TOLERANCE
        "hoeffding_bound_holds_on_null_cells": bound_flags["hoeffding_holds"],
        "bernstein_bound_holds_on_null_cells": bound_flags["bernstein_holds"],
        "hoeffding_tighter_than_bernstein_at_p_half": bound_flags["hoeffding_tighter_at_p_half"],
        "bernstein_tighter_somewhere_at_p_quarter": bound_flags["bernstein_tighter_somewhere_at_p_quarter"],
        "gap_below_gaussian_scale_on_null_cells": bound_flags["ratio_below_one"],
        "hoeffding_bound_exceeds_lattice_cap_on_some_cell": bound_flags["bound_exceeds_cap_somewhere"],
        # Part B: mutation chain
        "mutation_kernel_rows_sum_to_one_upward_only":
            mutation_flags["rows_sum"] and mutation_flags["upward_only"],
        "mutation_q1_equals_independent_chain": mutation_flags["q1_equals_independent"],
        "mutation_q0_never_accepts": mutation_flags["q0_never_accepts"],
        "mutation_gap_non_decreasing_in_generations_every_q": mutation_flags["monotone_in_generations"],
        "mutation_gap_bounded_by_lattice_cap": mutation_flags["bounded_by_cap"],
        "mutation_dp_matches_brute_force_enumeration": all(
            value for key, value in brute["checks"].items() if key.startswith("mutation")),
        "mutation_state_n_minus_1_up_probability_identity": mutation_flags["state_n_minus_1_identity"],
        "mutation_rho1_non_decreasing_in_q_on_cells": mutation_flags["rho1_non_decreasing_in_q"],
        "mutation_rho_not_monotone_in_q_on_every_naive_cell":
            mutation_flags["rho_monotone_in_q_fails_on_every_naive_cell"],
        "mutation_half_q_gap_above_independent_at_horizon_on_naive_cells":
            mutation_flags["half_q_above_independent_at_horizon_on_naive_cells"],
        "mutation_every_q_gap_above_independent_at_horizon_on_naive_cells_n_ge_8":
            mutation_flags["every_q_above_independent_at_horizon_on_naive_cells_n_ge_8"],
        # Part C: one-generation theorem and its chaining
        "one_step_difference_equals_window_integral_on_drift_states":
            one_step["difference_equals_window_integral"],
        "one_step_sign_matches_predicted_case_on_drift_states": one_step["sign_matches_predicted_case"],
        "one_step_difference_identically_zero_n8_z1_step_eighth": one_step["n8_difference_identically_zero"],
        "one_step_case_iii_takes_both_signs": one_step["case_iii_takes_both_signs"],
        "one_step_increment_matches_drift_dp": order_flags["one_step_increment_matches_dp"],
        "gate_order_first_generation_matches_one_step_prediction":
            order_flags["first_generation_matches_prediction"] and order_flags["lattice_steps_uniform"],
        "gate_order_case_ii_cells_gate_above_naive_every_generation":
            order_flags["case_ii_gate_above_naive_every_generation"],
        "gate_order_case_i_sign_reverses_on_some_cell": order_flags["case_i_reverses_somewhere"],
        "gate_order_naive_dominates_gate_in_expectation_on_cells":
            order_flags["naive_dominates_gate_reported"] and order_flags["naive_dominates_gate_true"],
        # Part D: Proposition 8 (dominance) and its count caveat
        "dominance_kernel_and_fast_expectations_match_dp":
            consistency["fast_expectations_equal_dp"] and structure_flags["kernel_rows_sum_to_one"],
        "dominance_limit_within_unabsorbed_mass_of_dp":
            consistency["limit_within_unabsorbed_mass"] and consistency["cells_absorbed_within_horizon"] > 0,
        "dominance_sweep_fixed_law_no_violation":
            not sweep_laws["fixed"]["violations"] and not sweep_laws["fixed"]["limit_violations"],
        "dominance_sweep_two_point_law_no_violation":
            not sweep_laws["two_point"]["violations"] and not sweep_laws["two_point"]["limit_violations"],
        "dominance_sweep_decaying_law_no_violation":
            not sweep_laws["decaying_two_point"]["violations"],
        "dominance_sweep_fixed_law_covers_all_cells": sweep_laws["fixed"]["cells"] == 324,
        "naive_iterates_monotone_true_value_M1_M2":
            structure_flags["naive_M1_true_value"] and structure_flags["naive_M2_true_value"]
            and structure_flags["limit_M1_true_value"],
        "dominance_true_value_every_state_and_horizon":
            structure_flags["D_true_value_every_state"] and structure_flags["S_true_value"],
        "dominance_true_value_limit_every_state": structure_flags["limit_true_value_dominance_every_state"],
        "dominance_level_stochastic_every_state": structure_flags["level_stochastic_dominance"],
        "dominance_count_every_state_and_horizon":
            structure_flags["D_count_every_state"] and structure_flags["S_count"],
        "dominance_count_hitting_probabilities_every_state": structure_flags["count_hitting_dominance"],
        "naive_count_gain_nonincreasing_in_count": structure_flags["naive_count_gain_nonincreasing_in_count"],
        "count_routes_fail_gate_cone_componentwise_policy_improvement":
            all(witnesses[k] is not None for k in ("gate_cone_fails_on_naive_iterates",
                                                   "componentwise_condition_fails_for_count",
                                                   "policy_improvement_fails_on_gated_iterates",
                                                   "naive_count_not_monotone_in_count")),
        "threshold_monotonicity_fails_for_a_non_naive_pair":
            structure["threshold_pair"]["higher_rule_ahead_somewhere"],
    }
    return {"evidence_status": "exact_synthetic_fixtures_not_model_or_agent_evidence",
            "checks": checks, "all_passed": all(checks.values()),
            "headline": _headline(naive, gated, drift, bounds, mutation, one_step, gate_order, sweep, structure),
            "naive": naive, "gated": gated, "fresh": fresh, "drift": drift,
            "brute_force": brute, "divergence": divergence,
            "bounds": bounds, "mutation": mutation, "one_step": one_step,
            "gate_order": gate_order, "dominance_consistency": consistency,
            "dominance_structure": structure, "dominance_sweep": sweep}


def _approx(value):
    return None if value is None else {"exact": value, "float": round(float(value), 6)}


def _headline(naive, gated, drift, bounds, mutation, one_step, gate_order, sweep, structure) -> dict[str, object]:
    """Named cells with a float rendering beside the exact value."""

    def sweep_row(law, key):
        return sweep["by_law"][law]["rows"][key]

    pair = structure["threshold_pair"]
    dominance = {
        "full_sweep": sweep["full_sweep"], "cells": sweep["cells"],
        "generations_compared": sweep["generations_compared"],
        "violations": sweep["violations"], "limit_violations": sweep["limit_violations"],
        "cells_by_law": {law: s["cells"] for law, s in sweep["by_law"].items()},
        "n16_k4_z1_fixed_p0_quarter_step_eighth": sweep_row("fixed", "gain=law,p0=1/4,step=1/8,n=16,K=4,z=1"),
        "n8_k2_z3_fixed_p0_zero_step_sixteenth": sweep_row("fixed", "gain=law,p0=0,step=1/16,n=8,K=2,z=3"),
        "structure_flags": structure["flags"],
        "routes_that_fail_for_the_count": structure["routes_that_fail_for_the_count"],
        "count_not_monotone_witness": {k: (_approx(v) if isinstance(v, Q) else v) for k, v in
                                       (structure["witnesses"]["naive_count_not_monotone_in_count"] or {}).items()},
        "threshold_pair_counterexample": {
            "lower": pair["lower_threshold"], "higher": pair["higher_threshold"], "levels": pair["levels"],
            "finite": None if pair["finite_witness"] is None else {
                k: (_approx(v) if isinstance(v, Q) else v) for k, v in pair["finite_witness"].items()},
            "limit": None if pair["limit_witness"] is None else {
                k: (_approx(v) if isinstance(v, Q) else v) for k, v in pair["limit_witness"].items()}},
    }

    def gaps(items, candidates):
        cell = naive["cells"][_cell(items, candidates, Q(1, 2))]["readout_gap_by_generation"]
        return {f"G={g}": _approx(v) for g, v in cell.items()}

    def gate(items, candidates):
        out = {"naive": _approx(gated["cells"][f"{_cell(items, candidates, Q(1, 2))},z=1"]
                               ["naive_readout_gap_at_horizon"])}
        for z in GATE_Z_VALUES:
            entry = gated["cells"][f"{_cell(items, candidates, Q(1, 2))},z={z}"]
            out[f"z={z}"] = _approx(entry["readout_gap_by_generation"][HORIZON])
            out[f"z={z}_expected_false_acceptances"] = _approx(entry["expected_false_acceptances"])
        return out

    def drift_cell(gain_name, policy, items=8, candidates=2):
        entry = drift["cells"][f"{_cell(items, candidates, DRIFT_P0)},gain={gain_name},policy={policy}"]
        return {key: _approx(entry[key]) for key in (
            "reported_at_horizon", "true_at_horizon", "readout_gap_at_horizon",
            "phantom_share_whole", "phantom_share_early_half", "phantom_share_late_half",
            "late_early_ratio_reported", "late_early_ratio_true")}

    def bound_cell(items, candidates, p):
        table = bounds["cells"][_cell(items, candidates, p)]["by_generation"]
        return {f"G={g}": {key: round(row[key], 6) for key in (
            "gap_float", "hoeffding", "bernstein", "gaussian_scale", "ratio_gap_to_gaussian_scale")}
            for g, row in table.items()}

    def mutation_cell(items, candidates, p, policy):
        entry = mutation["cells"][f"{_cell(items, candidates, p)},policy={policy}"]
        return {"gap_at_horizon_by_q": {q: _approx(v[HORIZON]) for q, v in entry["readout_gap_by_q"].items()},
                "gap_at_g1_by_q": {q: _approx(v[1]) for q, v in entry["readout_gap_by_q"].items()},
                "first_generation_rho_not_monotone_in_q": entry["first_generation_rho_not_monotone_in_q"]}

    def order_cell(items, candidates, step):
        entry = gate_order["cells"][f"n={items},K={candidates},z=1,step={step}"]
        return {"case": entry["case"], "signs": entry["sign_of_naive_minus_gate_gap_by_generation"],
                "first_generation_gate_gap_above_naive": entry["first_generation_gate_gap_above_naive"],
                "gap_at_horizon": {k: _approx(v) for k, v in entry["gap_at_horizon"].items()}}

    return {
        "naive_readout_gap_n8_k2_p_half": gaps(8, 2),
        "naive_readout_gap_n16_k4_p_half": gaps(16, 4),
        "gate_readout_gap_at_horizon_n16_k4_p_half": gate(16, 4),
        "gate_readout_gap_at_horizon_n8_k2_p_half": gate(8, 2),
        "drift_n8_k2_two_point_naive": drift_cell("two_point", "naive"),
        "drift_n8_k2_decaying_two_point_naive": drift_cell("decaying_two_point", "naive"),
        "drift_n8_k2_fixed_naive": drift_cell("fixed", "naive"),
        "drift_n8_k2_fixed_gate_z1": drift_cell("fixed", "gate_z1"),
        "drift_n16_k2_fixed_naive": drift_cell("fixed", "naive", 16, 2),
        "bounds_n8_k2_p_half": bound_cell(8, 2, Q(1, 2)),
        "bounds_n16_k4_p_half": bound_cell(16, 4, Q(1, 2)),
        "bounds_n16_k4_p_quarter": bound_cell(16, 4, Q(1, 4)),
        "bounds_ratio_range": bounds["ratio_range_over_cells_and_report_generations"],
        "mutation_n8_k2_p_half_naive": mutation_cell(8, 2, Q(1, 2), "naive"),
        "mutation_n16_k4_p_half_naive": mutation_cell(16, 4, Q(1, 2), "naive"),
        "mutation_n8_k2_p_half_gate_z1": mutation_cell(8, 2, Q(1, 2), "gate_z1"),
        "one_step_sign_tally_by_cell": {k: v["sign_tally_by_predicted_case"]
                                        for k, v in one_step["cells"].items()},
        "one_step_case_iii_examples": {k: {"sign": v["sign"], "difference": _approx(v["difference"])}
                                       for k, v in one_step["case_iii_examples"].items()},
        "gate_order_n8_k2_step_eighth": order_cell(8, 2, Q(1, 8)),
        "gate_order_n16_k2_step_eighth": order_cell(16, 2, Q(1, 8)),
        "gate_order_n4_k2_step_eighth": order_cell(4, 2, Q(1, 8)),
        "gate_order_later_generation_agreement": gate_order["later_generation_agreement_counts"],
        "dominance": dominance,
    }
