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

Boundaries
----------
Candidates are independent of the incumbent.  ``sim.js`` instead perturbs the
incumbent's per-item quirks, which correlates a candidate's item outcomes with
the incumbent's; that correlation shrinks the spread of ``M - c`` and hence the
per-generation inflation, but leaves the ratchet structure (a state only ever
moves up to a realized candidate count) unchanged.  ``n`` is fixed, labels are
clean, and every statement concerns distributions and expectations, not sample
paths.
"""

from __future__ import annotations

from fractions import Fraction as Q
from itertools import product
from math import isqrt

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
    history = [current]
    for _ in range(generations):
        following = [Q(0)] * (items + 1)
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
    }


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


def _cell(items, candidates, p):
    return f"n={items},K={candidates},p={p}"


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


def verify() -> dict[str, object]:
    """Run all exact fixtures and return machine-readable checks."""

    naive, gated, fresh = naive_fixture(), gated_fixture(), fresh_fixture()
    drift, brute, divergence = drift_fixture(), brute_force_fixture(), divergence_fixture()
    naive_8_2 = naive["cells"][_cell(8, 2, Q(1, 2))]["readout_gap_by_generation"]
    gated_16_4 = gated["cells"][f"{_cell(16, 4, Q(1, 2))},z=3"]
    orderings = drift["orderings_on_enumerated_cells"]
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
    }
    return {"evidence_status": "exact_synthetic_fixtures_not_model_or_agent_evidence",
            "checks": checks, "all_passed": all(checks.values()),
            "headline": _headline(naive, gated, drift),
            "naive": naive, "gated": gated, "fresh": fresh, "drift": drift,
            "brute_force": brute, "divergence": divergence}


def _approx(value):
    return None if value is None else {"exact": value, "float": round(float(value), 6)}


def _headline(naive, gated, drift) -> dict[str, object]:
    """Named cells with a float rendering beside the exact value."""

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
    }
