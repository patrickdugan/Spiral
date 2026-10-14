"""Best-of-K selection as a point of the KL slice: tie rules, containment, the DV bound.

Companion to ``paper/selection_law_kl_containment.md`` and to section 1 of
the crosswalk note.  Nothing here calls a model or runs a loop; every law is
a finite table of rationals, and the only floats are logarithms, square roots
and one Gaussian quadrature, compared under stated tolerances.

Setting.  A finite record space ``Omega`` with base law ``p0`` and a score
``S``.  ``K`` candidates are drawn i.i.d. from ``p0`` and the best-scoring one
is kept; ties are broken by the first index attaining the maximum or
uniformly among those attaining it.  Under the Spiral null (axiom A5)
``Omega = {0,1}^n``, ``p0 = Bern(p)^n``, ``S = count / n``, and the selection
gap ``gamma(n, K, p) = E[max_k S_k] - p`` of ``selection_inflation`` is the
mean of ``S - p`` under the selected record's law.

1. Tie rules (Theorem A).  Under either rule the selected record has law
   ``pi_K(w) = p0(w) P(max = S(w)) / P0(S = S(w))``: ``p0`` conditioned on the
   score, mixed over the law of the maximum.  Hence ``KL(pi_K || p0)`` equals
   the KL of the law of the maximum of ``K`` scores against the law of one.
2. Containment (Theorem B).  ``KL(pi_K || p0) <= ln K - (K-1)/K`` for every
   finite ``p0``, score and ``K``, strictly for ``K >= 2``: continuous jitter
   removes ties, the jittered selection has KL exactly ``ln K - (K-1)/K``, and
   dropping the jitter is a common deterministic map (Jensen on ``x ln x``).
3. The DV bound (Theorem C).  With the Kearns-Saul proxy ``v(p)`` of a
   Bernoulli, ``gamma(n,K,p) <= sqrt(2 v(p) KL(pi_K||p0) / n)
   <= sqrt(2 v(p) (ln K - (K-1)/K) / n)``.
4. Uniformity (Question D).  ``gamma / (sigma_n sqrt(2 lambda_K))`` tends to
   0 as ``K`` grows at fixed ``n`` and to ``c_K = E[max of K standard
   normals] / sqrt(2 lambda_K) < 1`` as ``n`` grows at ``p = 1/2``; ``c_K -> 1``,
   so the supremum of the ratio is 1 and is not attained.  At ``n = 1`` the
   gap equals the KL-ball supremum exactly.
5. Monotone approach (D.5, versions 0.2-0.4).  With ``a_n(K) = sqrt(n) gamma(n, K, 1/2)``
   (so ``r(n, K, 1/2) = 2 a_n(K) / sqrt(2 lambda_K)``), ``a_n(2)^2 = n C(2n,n)^2 /
   (4 * 16^n)`` by de Moivre's mean absolute deviation, ``a_{n+1}(2)^2 / a_n(2)^2 =
   1 + 1/(4n(n+1))``, and ``a_n(3) = (3/2) a_n(2)`` by the order-statistic
   recurrence; both rise strictly to ``E[max]/2``, so ``sup_n r = c_K`` for
   ``K = 2, 3``.  Version 0.3 verified ``K >= 4`` exactly on ``a_n^2`` (``K = 4..100``, ``n <= 400``;
   ``K = 200, 500, 1000, 10000``, ``n <= 60``) and recorded why the profile identities (``M_n(4) =
   2 sum w_m - sum w_m^2``, an order-4 recurrence) and the tie-mass bound do not close it.
   Version 0.4 proves it for ``K = 4..30`` (and ``31..40`` with ``verify(heavy=True)``): with
   ``H_K = (K/2) w - P_K(w) = O(w^2)`` the margin ``D_n = 2n (M_{n+1} - M_n) - M_n = M_n (rho_n - 1)``
   satisfies ``D_n = sum_m H_K(F(m)) + 2n sum_m sum_k H_K^(2k)(mu_m) q_m^(2k) / (4^k (2k)!)`` exactly (de
   Moivre cancels the ``S_1`` part), and a second-order expansion with every remainder bounded in
   exact rational arithmetic (Robbins' Stirling bounds, the midpoint Euler-Maclaurin kernels, a
   rigorous cell quadrature, Poisson summation) gives ``|sqrt(n) D_n - delta_K| <= C_K / n`` for
   ``n >= 400`` (``C_4 = 0.7413``).  An exact check ``N0^3 D_{N0}^2 > 4 C_K^2`` at ``N0 = 400`` (``K <= 25``)
   or a short exact scan (``N0 <= 498`` for ``K <= 30``) then gives ``rho_n > 1`` for every ``n >= N0``, and the
   0.3 sweep covers ``n <= 400``.  ``delta_K`` matches ``c(K) E[M_K] / 2`` (quadrature), replacing the
   cited Edgeworth expansion of 0.3 for the margin.
"""

from __future__ import annotations

from fractions import Fraction as Q
from functools import lru_cache
from itertools import product
from math import comb, erfc, exp, factorial, gcd, isqrt, log, pi, sqrt

import numpy as np

from spiral_ln.evaluation_game_feedback import selection_inflation

TIE_RULES = ("first_index", "uniform")
PROXIES = ("kearns_saul", "hoeffding")
LOG_TOLERANCE = 1e-12
SUPREMUM_TOLERANCE = 1e-9
QUADRATURE_TOLERANCE = 1e-9
GRID_ITEMS = (1, 2, 4, 8, 16, 64)
GRID_CANDIDATES = (2, 3, 5, 10, 20)
GRID_P = (Q(1, 4), Q(1, 2), Q(3, 4))
GAUSSIAN_CANDIDATES = (2, 3, 5, 10, 100, 1000, 10000)
MONOTONE_ITEMS = 200
MONOTONE_CANDIDATES = (3, 4, 5, 10, 20)
SWEEP_ITEMS = 100
SWEEP_CANDIDATES = tuple(range(2, 31)) + (40, 50, 100)
LARGE_CANDIDATES, LARGE_ITEMS = 1000, 40
STOP_LOSS_MARGIN = 1e-6


# --- argument checks ------------------------------------------------------------

def _law(law: dict, name: str) -> dict:
    if not isinstance(law, dict) or not law:
        raise ValueError(f"{name} must be a non-empty dict of rational masses")
    exact = {}
    for key, mass in law.items():
        if isinstance(mass, float):
            raise ValueError(f"{name} must use exact rationals, not floats")
        exact[key] = Q(mass)
    if any(mass < 0 for mass in exact.values()) or sum(exact.values()) != 1:
        raise ValueError(f"{name} must be non-negative and sum to one")
    return exact


def _candidates(candidates: int) -> None:
    if type(candidates) is not int or candidates < 1:
        raise ValueError("candidates must be a positive integer")


def _scores(p0: dict, score: dict) -> dict:
    if not isinstance(score, dict) or set(score) != set(p0):
        raise ValueError("score must be defined on exactly the records of p0")
    if any(isinstance(value, float) for value in score.values()):
        raise ValueError("scores must be exact (int or Fraction)")
    return {record: Q(value) for record, value in score.items()}


def _items(items: int) -> None:
    if type(items) is not int or items < 1:
        raise ValueError("items must be a positive integer")


def _interior_probability(p) -> Q:
    if isinstance(p, float):
        raise ValueError("p must be an exact rational")
    p = Q(p)
    if not 0 < p < 1:
        raise ValueError("p must lie strictly inside (0, 1)")
    return p


# --- Theorem A: the selected record's law under a tie rule ----------------------

def score_law(p0: dict, score: dict) -> dict[Q, Q]:
    """Push-forward of ``p0`` under the score: ``q(s) = P0(S = s)``."""

    p0 = _law(p0, "p0")
    score = _scores(p0, score)
    q: dict[Q, Q] = {}
    for record, mass in p0.items():
        q[score[record]] = q.get(score[record], Q(0)) + mass
    return q


def score_cdf(q: dict[Q, Q]) -> dict[Q, tuple[Q, Q]]:
    """``s -> (F(s-), F(s))`` for every atom ``s`` of the score law ``q``."""

    q = _law(q, "score law")
    running, table = Q(0), {}
    for s in sorted(q):
        table[s] = (running, running + q[s])
        running += q[s]
    return table


def max_law(q: dict[Q, Q], candidates: int) -> dict[Q, Q]:
    """Law of the maximum of ``candidates`` i.i.d. scores: ``P(max = s) = F(s)^K - F(s-)^K``."""

    _candidates(candidates)
    return {s: upto**candidates - below**candidates for s, (below, upto) in score_cdf(q).items()}


def first_index_weight(below: Q, upto: Q, candidates: int) -> Q:
    """``sum_{k=1}^K F(s-)^{k-1} F(s)^{K-k}``: the first-index rule's multiplier of ``p0(w)``.

    Candidate ``k`` is kept with record ``w`` iff it is ``w``, every earlier
    candidate scores strictly below ``S(w)`` and every later one at most ``S(w)``.
    """

    return sum((below**(k - 1) * upto**(candidates - k) for k in range(1, candidates + 1)), Q(0))


def uniform_weight(below: Q, upto: Q, candidates: int) -> Q:
    """``sum_{j=0}^{K-1} C(K, j+1) q^j F(s-)^{K-1-j}``: the uniform rule's multiplier of ``p0(w)``.

    By exchangeability the kept record is ``w`` with probability ``K`` times
    the chance that candidate 1 is ``w``, the others score at most ``S(w)``,
    and candidate 1 wins the uniform draw among the ``1 + N'`` candidates at
    the top, ``N' ~ Bin(K-1, q)`` on that event; ``K C(K-1, j) / (j+1) = C(K, j+1)``.
    """

    q = upto - below
    return sum((comb(candidates, j + 1) * q**j * below**(candidates - 1 - j) for j in range(candidates)), Q(0))


def selected_record_law(p0: dict, score: dict, candidates: int, rule: str = "uniform") -> dict:
    """Exact law of the record kept by best-of-``candidates`` selection under ``rule``."""

    if rule not in TIE_RULES:
        raise ValueError("unknown tie rule")
    _candidates(candidates)
    p0 = _law(p0, "p0")
    score = _scores(p0, score)
    cdf = score_cdf(score_law(p0, score))
    weight = first_index_weight if rule == "first_index" else uniform_weight
    return {record: mass * weight(*cdf[score[record]], candidates) for record, mass in p0.items()}


def conditioned_on_max_law(p0: dict, score: dict, candidates: int) -> dict:
    """``p0(w) P(max = S(w)) / P0(S = S(w))``: ``p0`` conditioned on the score, mixed over the maximum."""

    _candidates(candidates)
    p0 = _law(p0, "p0")
    score = _scores(p0, score)
    q = score_law(p0, score)
    m = max_law(q, candidates)
    return {record: (mass * m[score[record]] / q[score[record]] if mass else Q(0))
            for record, mass in p0.items()}


def brute_force_selected_law(p0: dict, score: dict, candidates: int, rule: str = "uniform") -> dict:
    """Enumerate every ``candidates``-tuple of records and apply the tie rule literally."""

    if rule not in TIE_RULES:
        raise ValueError("unknown tie rule")
    _candidates(candidates)
    p0 = _law(p0, "p0")
    score = _scores(p0, score)
    support = [record for record, mass in p0.items() if mass > 0]
    law = {record: Q(0) for record in p0}
    for draw in product(support, repeat=candidates):
        weight = Q(1)
        for record in draw:
            weight *= p0[record]
        top = max(score[record] for record in draw)
        attaining = [k for k, record in enumerate(draw) if score[record] == top]
        if rule == "first_index":
            law[draw[attaining[0]]] += weight
        else:
            for k in attaining:
                law[draw[k]] += weight / len(attaining)
    return law


# --- divergences -----------------------------------------------------------------

def kl_divergence(pi: dict, p0: dict) -> float:
    """``KL(pi || p0)`` in nats for rational laws on one key set.

    The log-ratio is taken on integer numerators and denominators so that
    atoms far below float range do not underflow inside the logarithm.
    """

    pi = _law(pi, "pi")
    p0 = _law(p0, "p0")
    if set(pi) != set(p0):
        raise ValueError("pi and p0 must share a key set")
    total = 0.0
    for key, a in pi.items():
        if a > 0:
            b = p0[key]
            if b == 0:
                raise ValueError("pi is not absolutely continuous with respect to p0")
            total += float(a) * (log(a.numerator) - log(a.denominator) - log(b.numerator) + log(b.denominator))
    return total


def beirami_radius(candidates: int) -> float:
    """``ln K - (K-1)/K``: the KL of a tie-free best-of-``K`` law against its base."""

    _candidates(candidates)
    return log(candidates) - (candidates - 1) / candidates


def uniform_distinct_scores_kl(atoms: int, candidates: int) -> float:
    """``KL(pi_K || p0)`` for ``p0`` uniform on ``atoms`` records with distinct scores.

    A Riemann sum of ``K x^{K-1} ln(K x^{K-1})`` on ``[0, 1]``; it tends to the
    radius as ``atoms`` grows, so the radius is the supremum over finite laws.
    """

    _items(atoms)
    q = {Q(i): Q(1, atoms) for i in range(atoms)}
    return kl_divergence(max_law(q, candidates), q)


# --- the Spiral null: binomial scores ---------------------------------------------

def binomial_score_law(items: int, p) -> dict[Q, Q]:
    """Law of ``S = count / items`` for ``count ~ Bin(items, p)``, keyed by the score."""

    _items(items)
    p = _interior_probability(p)
    return {Q(j, items): Q(comb(items, j)) * p**j * (1 - p)**(items - j) for j in range(items + 1)}


def binomial_records(items: int, p) -> tuple[dict, dict]:
    """``(p0, score)`` on the records ``{0,1}^items`` themselves, for small ``items``."""

    _items(items)
    p = _interior_probability(p)
    p0, score = {}, {}
    for bits in product("01", repeat=items):
        record = "".join(bits)
        ones = record.count("1")
        p0[record] = p**ones * (1 - p)**(items - ones)
        score[record] = Q(ones, items)
    return p0, score


def kl_max_law(items: int, candidates: int, p) -> float:
    """``KL(pi_K || p0)`` under the null, computed as the KL of the max law against one score."""

    q = binomial_score_law(items, p)
    return kl_divergence(max_law(q, candidates), q)


def selection_gap(items: int, candidates: int, p) -> Q:
    """``gamma(items, candidates, p)`` from ``selection_inflation``."""

    _items(items)
    _candidates(candidates)
    p = _interior_probability(p)
    return selection_inflation(items, candidates, p)["readout_gap"]


def gap_from_max_law(items: int, candidates: int, p) -> Q:
    """The same gap as ``E[S]`` under the max law minus ``p``; cross-checks ``selection_gap``."""

    q = binomial_score_law(items, p)
    return sum((s * mass for s, mass in max_law(q, candidates).items()), Q(0)) - Q(p)


# --- Theorem C: sub-Gaussian proxies and the DV bound ---------------------------

def kearns_saul_proxy(p) -> float:
    """``v(p) = (1 - 2p) / (2 ln((1-p)/p))``, ``v(1/2) = 1/4`` (Kearns and Saul 1998)."""

    p = _interior_probability(p)
    if p == Q(1, 2):
        return 0.25
    pf = float(p)
    return (1 - 2 * pf) / (2 * log((1 - pf) / pf))


def hoeffding_proxy() -> float:
    """``1/4``: the variance proxy of any variable supported on an interval of length one."""

    return 0.25


def variance_proxy(p, proxy: str = "kearns_saul") -> float:
    if proxy not in PROXIES:
        raise ValueError("unknown proxy")
    return kearns_saul_proxy(p) if proxy == "kearns_saul" else hoeffding_proxy()


def subgaussian_violation(p, proxy: str = "kearns_saul", steps: int = 400, step: float = 0.05) -> float:
    """Largest value of ``ln E exp(t(X - p)) - v t^2 / 2`` for ``X ~ Bern(p)`` on a ``t``-grid.

    A sanity check of the cited inequality, not a proof: it should be ``<= 0``.
    """

    p = _interior_probability(p)
    v, pf, worst = variance_proxy(p, proxy), float(p), -1.0
    for k in range(1, steps + 1):
        for sign in (1.0, -1.0):
            t = sign * k * step
            lmgf = log((1 - pf) * exp(-t * pf) + pf * exp(t * (1 - pf)))
            worst = max(worst, lmgf - v * t * t / 2)
    return worst


def dv_bound(items: int, p, divergence: float, proxy: str = "kearns_saul") -> float:
    """``sqrt(2 (v(p) / items) divergence)``: the Donsker-Varadhan bound on ``E_pi[S] - p``."""

    _items(items)
    if not divergence >= 0:
        raise ValueError("divergence must be non-negative")
    return sqrt(2 * variance_proxy(p, proxy) * divergence / items)


def gap_to_bound_ratio(items: int, candidates: int, p, at: str = "radius") -> float:
    """``gamma / sqrt(2 (v(p)/n) lambda)`` with ``lambda`` the radius or the exact KL."""

    if at not in ("radius", "exact"):
        raise ValueError("at must be 'radius' or 'exact'")
    divergence = beirami_radius(candidates) if at == "radius" else kl_max_law(items, candidates, p)
    return float(selection_gap(items, candidates, p)) / dv_bound(items, p, divergence)


# --- the KL-ball supremum (exponential tilt) --------------------------------------

def _tilt(q: list[Q], scores: list[float], t: float) -> list[float]:
    top = max(scores)
    weights = [float(mass) * exp(t * (s - top)) for mass, s in zip(q, scores)]
    total = sum(weights)
    return [w / total for w in weights]


def _kl_float(pi: list[float], q: list[Q]) -> float:
    return sum(a * log(a / float(b)) for a, b in zip(pi, q) if a > 0)


def kl_ball_supremum(items: int, p, radius: float) -> float:
    """``sup E_pi[S]`` over ``KL(pi || p0) <= radius`` under the null.

    The supremum is attained at the exponential tilt of the score law whose
    KL equals the radius (bisection on the tilt parameter), or at the point
    mass on score 1 once ``-ln p0(1) <= radius``.
    """

    _items(items)
    if not radius >= 0:
        raise ValueError("radius must be non-negative")
    law = binomial_score_law(items, p)
    keys = sorted(law)
    q = [law[s] for s in keys]
    scores = [float(s) for s in keys]
    if radius == 0:
        return float(p)
    if -log(float(q[-1])) <= radius + 1e-12:
        return 1.0
    lo, hi = 0.0, 1.0
    while _kl_float(_tilt(q, scores, hi), q) < radius:
        hi *= 2.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if _kl_float(_tilt(q, scores, mid), q) < radius:
            lo = mid
        else:
            hi = mid
    pi = _tilt(q, scores, lo)
    return sum(a * s for a, s in zip(pi, scores))


# --- Question D: the Gaussian limit ----------------------------------------------

@lru_cache(maxsize=None)
def _gaussian_grid(half_width: float = 12.0, points: int = 48001):
    x = np.linspace(-half_width, half_width, points)
    cdf = np.array([0.5 * erfc(-value / sqrt(2)) for value in x])
    pdf = np.exp(-0.5 * x * x) / sqrt(2 * pi)
    return x, cdf, pdf


def _simpson(y: np.ndarray, h: float) -> float:
    if len(y) % 2 == 0:
        raise ValueError("Simpson's rule needs an odd number of points")
    return float(h / 3 * (y[0] + y[-1] + 4 * y[1:-1:2].sum() + 2 * y[2:-1:2].sum()))


def gaussian_max_expectation(candidates: int, form: str = "density") -> float:
    """``E[max of candidates i.i.d. standard normals]`` by composite Simpson quadrature.

    ``density``: ``K int x phi(x) Phi(x)^{K-1} dx``.  ``tail``: ``int_0^inf (1 - Phi^K)
    - int_{-inf}^0 Phi^K``.  Both on ``[-12, 12]`` with step ``1/2000``.
    """

    _candidates(candidates)
    if form not in ("density", "tail"):
        raise ValueError("form must be 'density' or 'tail'")
    x, cdf, pdf = _gaussian_grid()
    h = float(x[1] - x[0])
    if form == "density":
        return _simpson(candidates * x * pdf * cdf ** (candidates - 1), h)
    power = cdf ** candidates
    middle = len(x) // 2
    return _simpson(1 - power[middle:], h) - _simpson(power[:middle + 1], h)


def gaussian_ratio_limit(candidates: int) -> float:
    """``c_K = E[max of K standard normals] / sqrt(2 (ln K - (K-1)/K))``."""

    return gaussian_max_expectation(candidates) / sqrt(2 * beirami_radius(candidates))


# --- D.5: is sqrt(n) gamma(n, K, 1/2) monotone in n?  (exact, sqrt-free) -------------
#
# Write X_k ~ Bin(n, 1/2) i.i.d., Y_k = X_k - n/2 (symmetric about 0), M_n(K) = E[max_k Y_k]
# = n gamma(n, K, 1/2) and a_n(K) = sqrt(n) gamma = M_n(K) / sqrt(n).  Since the bound
# sigma_n sqrt(2 lambda_K) = sqrt(2 lambda_K / (4n)), r(n, K, 1/2) = 2 a_n(K) / sqrt(2 lambda_K)
# and r is monotone in n iff a_n^2 = M_n^2 / n is, a comparison of rationals.

def symmetric_binomial_mad(trials: int) -> Q:
    """``E|S - N/2|`` for ``S ~ Bin(N, 1/2)`` by enumeration over the ``N + 1`` atoms."""

    _items(trials)
    return sum((Q(comb(trials, s), 2**trials) * abs(Q(2 * s - trials, 2)) for s in range(trials + 1)), Q(0))


def symmetric_binomial_mad_closed_form(trials: int) -> Q:
    """De Moivre: ``E|S - N/2| = m C(N, m) / 2^N`` with ``m = floor(N/2) + 1`` for ``S ~ Bin(N, 1/2)``.

    For ``N = 2n`` this is ``(n+1) C(2n, n+1) / 4^n = n C(2n, n) / 4^n``.  Proof for ``N = 2n``:
    ``E|S - n| = 2 sum_{s>n} (s - n) C(2n, s) / 4^n``; ``s C(2n, s) = 2n C(2n-1, s-1)`` and
    ``sum_{s>n} C(2n-1, s-1) = 2^{2n-2}`` (half of ``2^{2n-1}``, by symmetry), while
    ``sum_{s>n} C(2n, s) = (4^n - C(2n, n)) / 2``; the difference is ``n C(2n, n) / 2``.
    """

    _items(trials)
    m = trials // 2 + 1
    return Q(m * comb(trials, m), 2**trials)


def expected_max_count(items: int, candidates: int) -> Q:
    """``E[max of K i.i.d. Bin(n, 1/2)]`` exactly, in integer arithmetic.

    ``sum_m m (G(m)^K - G(m-1)^K) / 2^{nK}`` with ``G(m) = sum_{j<=m} C(n, j)``; the same
    quantity as ``selection_inflation`` (cross-checked), but cheap at ``n = 200, K = 100``.
    """

    _items(items)
    _candidates(candidates)
    partial, running = [], 0
    for j in range(items + 1):
        running += comb(items, j)
        partial.append(running)
    total, previous = 0, 0
    for m, g in enumerate(partial):
        current = g**candidates
        total += m * (current - previous)
        previous = current
    return Q(total, 2**(items * candidates))


def centered_max(items: int, candidates: int) -> Q:
    """``M_n(K) = E[max_k X_k] - n/2 = E[max_k Y_k] = n gamma(n, K, 1/2)``."""

    return expected_max_count(items, candidates) - Q(items, 2)


def scaled_gap_squared(items: int, candidates: int) -> Q:
    """``a_n(K)^2 = n gamma(n, K, 1/2)^2 = M_n(K)^2 / n``, exact.

    ``a_n(K)`` is ``sqrt(p(1-p)) = 1/2`` times the expected maximum of ``K`` standardized
    counts, and ``r(n, K, 1/2) = 2 a_n(K) / sqrt(2 lambda_K)``.
    """

    return centered_max(items, candidates)**2 / items


def scaled_gap(items: int, candidates: int) -> float:
    return sqrt(scaled_gap_squared(items, candidates))


def pair_scaled_gap_squared(items: int) -> Q:
    """``K = 2`` closed form: ``a_n(2)^2 = n C(2n, n)^2 / (4 * 16^n)``.

    ``max(X_1, X_2) = (X_1 + X_2)/2 + |X_1 - X_2|/2`` and ``X_1 - X_2 + n = X_1 + (n - X_2)
    ~ Bin(2n, 1/2)``, so ``M_n(2) = E|Bin(2n, 1/2) - n| / 2 = n C(2n, n) / (2 * 4^n)``.
    """

    _items(items)
    return Q(items * comb(2 * items, items)**2, 4 * 16**items)


def pair_step_ratio(items: int) -> Q:
    """``a_{n+1}(2)^2 / a_n(2)^2 = ((n+1)/n) ((2n+1)/(2n+2))^2 = (2n+1)^2 / (4n(n+1)) = 1 + 1/(4n(n+1))``.

    ``C(2n+2, n+1) / C(2n, n) = 2(2n+1)/(n+1)``; the excess over 1 is the ``+1`` in
    ``(2n+1)^2 = 4n(n+1) + 1``.  Telescoping from ``a_1(2)^2 = 1/16``, ``a_n(2)^2 = (1/16) prod_{1<=j<n} (2j+1)^2/((2j)(2j+2))``
    rises to ``(1/16)(4/pi) = 1/(4 pi)`` (Wallis), i.e. ``a_n(2)`` increases strictly to
    ``1/(2 sqrt(pi)) = E[max of two standard normals] / 2``.
    """

    _items(items)
    n = items
    return Q((2 * n + 1)**2, 4 * n * (n + 1))


def pair_gap_by_enumeration(items: int) -> Q:
    """``E[max(X_1, X_2)] - n/2`` as ``sum_{i,j} q_i q_j |i - j| / 2`` over the two counts."""

    q = binomial_score_law(items, Q(1, 2))
    masses = [q[Q(j, items)] for j in range(items + 1)]
    return sum((masses[i] * masses[j] * abs(i - j) for i in range(items + 1) for j in range(items + 1)), Q(0)) / 2


def tie_count_moment(items: int, candidates: int) -> Q:
    """``E[2^{-N}]``, ``N`` the number of the ``K`` candidates attaining the maximum count.

    ``sum_m sum_{j>=1} C(K, j) q_m^j F(m-1)^{K-j} 2^{-j} = sum_m [((F(m-1) + F(m))/2)^K - F(m-1)^K]``;
    the midpoint CDF ``(F(m-1) + F(m))/2`` is that of ``Bin(n+1, 1/2)``.
    """

    _items(items)
    _candidates(candidates)
    partial, running = [], 0
    for j in range(items + 1):
        running += comb(items, j)
        partial.append(running)
    below = [0] + partial[:-1]
    total = sum((below[m] + partial[m])**candidates - (2 * below[m])**candidates for m in range(items + 1))
    return Q(total, 2**((items + 1) * candidates))


def brute_force_tie_count_moment(items: int, candidates: int) -> Q:
    """``E[2^{-N}]`` by enumerating every ``K``-tuple of counts with binomial weights."""

    q = binomial_score_law(items, Q(1, 2))
    masses = [q[Q(j, items)] for j in range(items + 1)]
    total = Q(0)
    for counts in product(range(items + 1), repeat=candidates):
        weight = Q(1)
        for c in counts:
            weight *= masses[c]
        total += weight / 2**counts.count(max(counts))
    return total


def centered_max_increment(items: int, candidates: int) -> Q:
    """``M_{n+1}(K) - M_n(K) = 1/2 - E[2^{-N_n}]`` (identity; cross-checked against ``centered_max``).

    Adding one fair bit ``B_k`` to every count raises the maximum by one iff some candidate
    at the maximum draws ``B_k = 1``, probability ``1 - 2^{-N}``; subtract the ``1/2`` of the
    centering.  For ``K = 2`` this is ``P(X_1 = X_2) / 4 = C(2n, n) / 4^{n+1} = M_n(2) / (2n)``.
    """

    return Q(1, 2) - tie_count_moment(items, candidates)


def increment_ratio(items: int, candidates: int) -> Q:
    """``rho_n = 2n (M_{n+1} - M_n) / M_n``.

    ``a_{n+1}^2 > a_n^2`` iff ``rho_n + rho_n^2 / (4n) > 1``; ``rho_n >= 1`` (i.e. ``M_n(K)/M_n(2)``
    non-decreasing) is sufficient, and ``rho_n = 1`` exactly for ``K = 2, 3``.  As ``n -> oo``,
    ``rho_n -> 1`` for every ``K``, because ``C(K,2) int phi^2 Phi^{K-2} = E[max of K normals]/2``
    (integration by parts), so the general-``K`` question is second order.
    """

    before = centered_max(items, candidates)
    return 2 * items * (centered_max(items + 1, candidates) - before) / before


def monotonicity_sweep(candidates: int, max_items: int = MONOTONE_ITEMS) -> dict[str, object]:
    """Consecutive ratios ``a_{n+1}^2 / a_n^2`` for ``n <= max_items`` compared as rationals.

    Also the normalized margin ``mu_n = 4n(n+1)(a_{n+1}^2/a_n^2 - 1)`` (``1`` for ``K = 2, 3``)
    and ``rho_n``.  Displayed values are floats; every comparison is exact.
    """

    _items(max_items)
    _candidates(candidates)
    centered = [centered_max(n, candidates) for n in range(1, max_items + 2)]
    squares = [m * m / n for n, m in enumerate(centered, start=1)]
    ratios = [b / a for a, b in zip(squares, squares[1:])]
    margins = [4 * n * (n + 1) * (r - 1) for n, r in enumerate(ratios, start=1)]
    rhos = [2 * n * (b - a) / a for n, (a, b) in enumerate(zip(centered, centered[1:]), start=1)]
    failures = [n for n, r in enumerate(ratios, start=1) if r <= 1]
    i_ratio = min(range(len(ratios)), key=ratios.__getitem__)
    i_margin = min(range(len(margins)), key=margins.__getitem__)
    i_rho = min(range(len(rhos)), key=rhos.__getitem__)
    limit = gaussian_max_expectation(candidates) / 2
    final = sqrt(squares[max_items - 1])
    return {"candidates": candidates, "max_items": max_items, "monotone": not failures,
            "first_failure": failures[0] if failures else None,
            "min_step_ratio": float(ratios[i_ratio]), "min_step_ratio_at": i_ratio + 1,
            "min_margin": float(margins[i_margin]), "min_margin_at": i_margin + 1,
            "rho_at_least_one": all(r >= 1 for r in rhos), "rho_equals_one": all(r == 1 for r in rhos),
            "min_rho": float(rhos[i_rho]), "min_rho_at": i_rho + 1,
            "scaled_gap_first": sqrt(squares[0]), "scaled_gap_at_max_items": final,
            "gaussian_limit": limit, "below_gaussian_limit": all(sqrt(s) < limit for s in squares),
            "approach_coefficient": max_items * (limit - final)}


def standardized_absolute_moment_squared(items: int) -> Q:
    """``(E|Z_n|)^2 = 4 MAD_n^2 / n`` for the standardized count ``Z_n = (X - n/2) / sqrt(n/4)``.

    ``E|Z_{2k}| = sqrt(2k) C(2k,k)/4^k`` and ``E|Z_{2k+1}| = sqrt(2k+1) C(2k,k)/4^k``, so
    ``E|Z_n|`` falls at every odd-to-even step (ratio of squares ``(2k+1)/(2k+2)``): ``|x|`` is
    convex, hence ``Z_{2k+1} <=_cx Z_{2k+2}`` is false and the convex-order route to D.5 is closed.
    """

    mad = symmetric_binomial_mad_closed_form(items)
    return 4 * mad * mad / items


def stop_loss_excess(items: int) -> float:
    """``max_c [E(Z_n - c)^+ - E(Z_{n+1} - c)^+]`` over the atoms of both laws (floats).

    The difference is piecewise linear in ``c`` with breakpoints at the atoms, so the maximum
    is attained there; a positive value refutes ``Z_n <=_cx Z_{n+1}`` with a convex test function.
    """

    _items(items)

    def call(n: int, c: float) -> float:
        scale = sqrt(n)
        return sum(comb(n, j) / 2**n * max((2 * j - n) / scale - c, 0.0) for j in range(n + 1))

    atoms = sorted({(2 * j - items) / sqrt(items) for j in range(items + 1)}
                   | {(2 * j - items - 1) / sqrt(items + 1) for j in range(items + 2)})
    return max(call(items, c) - call(items + 1, c) for c in atoms)


def exact_kl_ratio_along_items(candidates: int, items_list: tuple[int, ...]) -> dict[str, dict[str, float]]:
    """``gamma / sqrt(2 sigma_n^2 KL(pi_K || p0))`` and ``KL / lambda_K`` at ``p = 1/2`` along ``n``.

    ``KL(pi_K || p0) -> lambda_K`` as ``n -> oo`` (``m_K(m)/q_m = K xi_m^{K-1}`` with ``xi_m`` in
    ``(F(m-1), F(m))``, a Riemann sum of ``g ln g`` with mesh ``max_m q_m -> 0``), so this
    ratio has the same limit ``c_K`` as the radius ratio; its path is a finite result.
    """

    _candidates(candidates)
    rows = {}
    for items in items_list:
        kl = kl_max_law(items, candidates, Q(1, 2))
        gap = centered_max(items, candidates) / items
        rows[f"n={items}"] = {"ratio_exact": float(gap) / dv_bound(items, Q(1, 2), kl),
                              "kl_over_radius": kl / beirami_radius(candidates)}
    return rows


# --- D.5 at K >= 4 (version 0.3): overlap profile, pair of pairs, tie masses, recurrence, sweeps ---
#
# Write w_m = F_n(m)(1 - F_n(m)) = P(X <= m < X'), m = 0..n-1 (the overlap profile).  Since
# F_n(n-1-m) = 1 - F_n(m), the sum M_n(K) = sum_m [F_n(m) - F_n(m)^K] symmetrizes to
# sum_m P_K(w_m) with 2 P_K(u(1-u)) = 1 - u^K - (1-u)^K: P_2 = w, P_3 = 3w/2, P_4 = 2w - w^2,
# P_5 = (5/2)(w - w^2).  So M_n(2) = S_1, M_n(4) = 2 S_1 - S_2 with S_j = sum_m w_m^j, and the
# pair-of-pairs step E|Y - Y'| = 2 (S_1 - S_2) (Y = max of two) collapses to a single sum.  The
# step n -> n+1 replaces the profile by v_m = (w_{m-1} + w_m)/2 + q_m^2/4 (midpoints of
# consecutive F's), which gives S_2 and M_n(4) increments in the local sums L_1 = sum q^2,
# L_2 = sum q^2 w, L_4 = sum q^4; L_4 is a Franel-type sum of fourth powers of binomials, and
# the step ratio of M_n(4) is not a rational function of n (exact rank test), although the
# integers 2^(4n+1) M_n(4) satisfy an order-4 recurrence with degree-8 coefficients.

WIDE_SWEEP_ITEMS = 400
WIDE_SWEEP_CANDIDATES = tuple(range(4, 101))
HUGE_SWEEP_ITEMS = 60
HUGE_SWEEP_CANDIDATES = (200, 500, 1000, 10000)
RATIONAL_STEP_DEGREE = 6
RECURRENCE_ORDER, RECURRENCE_DEGREE, RECURRENCE_VERIFY_ITEMS = 4, 8, 300
MARGIN_FIT_TOLERANCE = 1e-3


def tie_polynomial(candidates: int) -> list[Q]:
    """Coefficients ``c_0, ..., c_{floor(K/2)}`` of ``P_K(w) = sum_j c_j w^j`` with ``2 P_K(u(1-u)) = 1 - u^K - (1-u)^K``.

    Newton: ``s_K = u^K + (1-u)^K`` obeys ``s_K = s_{K-1} - w s_{K-2}``, ``s_0 = 2``, ``s_1 = 1``
    (the elementary symmetric functions of ``u, 1-u`` are ``1`` and ``w``); ``P_K = (1 - s_K)/2``.
    """

    _candidates(candidates)
    previous, current = [Q(2)], [Q(1)]
    for _ in range(candidates - 1):
        shifted = [Q(0)] + previous
        size = max(len(current), len(shifted))
        current, previous = [(current[i] if i < len(current) else 0) - (shifted[i] if i < len(shifted) else 0)
                             for i in range(size)], current
    poly = [-c / 2 for c in current]
    poly[0] += Q(1, 2)
    return poly


def overlap_profile(items: int) -> list[Q]:
    """``w_m = F_n(m)(1 - F_n(m))``, ``m = 0..n-1``, for ``Bin(n, 1/2)``: ``P(X <= m < X')``."""

    _items(items)
    running, profile = 0, []
    for m in range(items):
        running += comb(items, m)
        profile.append(Q(running * (2**items - running), 4**items))
    return profile


def centered_max_from_profile(items: int, candidates: int) -> Q:
    """``M_n(K) = sum_m P_K(w_m)``; cross-checks ``centered_max`` through the symmetrized polynomial."""

    poly = tie_polynomial(candidates)
    return sum((sum((c * w**j for j, c in enumerate(poly)), Q(0)) for w in overlap_profile(items)), Q(0))


def profile_power_sums(items: int) -> tuple[Q, Q]:
    """``(S_1, S_2) = (sum_m w_m, sum_m w_m^2)``: ``M_n(2) = S_1``, ``M_n(4) = 2 S_1 - S_2``, ``E Y_(3:4) = 3 S_2``."""

    profile = overlap_profile(items)
    return sum(profile, Q(0)), sum((w * w for w in profile), Q(0))


def max_of_two_law(items: int) -> dict[int, Q]:
    """Law of ``max(X_1, X_2)`` on the counts: ``F(j)^2 - F(j-1)^2``."""

    _items(items)
    running, previous, law = 0, Q(0), {}
    for j in range(items + 1):
        running += comb(items, j)
        current = Q(running, 2**items)**2
        law[j] = current - previous
        previous = current
    return law


def mean_absolute_difference(law: dict[int, Q]) -> Q:
    """``E|Y - Y'| = sum_{i,j} m_i m_j |i - j|`` for i.i.d. ``Y, Y'`` with law ``law`` (the literal double sum)."""

    law = _law(law, "law")
    return sum((a * b * abs(i - j) for i, a in law.items() for j, b in law.items()), Q(0))


def order_statistic_mean_by_enumeration(items: int, size: int, rank: int) -> Q:
    """``E[X_(rank:size)] - n/2`` by enumerating every ``size``-tuple of ``Bin(n, 1/2)`` counts (tiny ``n``)."""

    _items(items)
    if type(size) is not int or type(rank) is not int or not 1 <= rank <= size:
        raise ValueError("rank must lie between 1 and size")
    masses = [Q(comb(items, j), 2**items) for j in range(items + 1)]
    total = Q(0)
    for counts in product(range(items + 1), repeat=size):
        weight = Q(1)
        for c in counts:
            weight *= masses[c]
        total += weight * sorted(counts)[rank - 1]
    return total - Q(items, 2)


def local_sums(items: int) -> dict[str, Q]:
    """``L_1 = sum_m q_m^2``, ``L_2 = sum_m q_m^2 w_m`` (``w_n = 0``), ``L_4 = sum_m q_m^4``, ``m = 0..n``.

    ``L_1 = C(2n, n)/4^n`` (hypergeometric); ``L_4 = sum_m C(n, m)^4 / 16^n`` is a Franel-type sum
    (numerators 1, 2, 18, 164, 1810, ...), not hypergeometric; by the symmetry ``m -> n - m``,
    ``sum q_m^2 w_{m-1} = L_2``.
    """

    _items(items)
    q = [Q(comb(items, m), 2**items) for m in range(items + 1)]
    w = overlap_profile(items) + [Q(0)]
    return {"L1": sum((x * x for x in q), Q(0)), "L2": sum((x * x * y for x, y in zip(q, w)), Q(0)),
            "L4": sum((x**4 for x in q), Q(0))}


def second_profile_increment(items: int) -> Q:
    """``S_2^{(n+1)} - S_2^{(n)} = (6 L_2 - L_1)/4 + 5 L_4/16``.

    The new profile is ``v_m = (w_{m-1} + w_m)/2 + q_m^2/4``; expanding ``sum v_m^2`` with
    ``w_m - w_{m-1} = q_m (1 - 2 mid_m)`` and ``w_{m-1} + w_m = 2 mid_m (1 - mid_m) - q_m^2/2`` gives
    ``sum_m q_m^2 (6 v_m - 1 - q_m^2/4)/4``, and ``sum q_m^2 v_m = L_2 + L_4/4``.
    """

    local = local_sums(items)
    return (6 * local["L2"] - local["L1"]) / 4 + Q(5, 16) * local["L4"]


def quadruple_increment(items: int) -> Q:
    """``M_{n+1}(4) - M_n(4) = 3 L_1/4 - 3 L_2/2 - 5 L_4/16`` (from ``M_n(4) = 2 S_1 - S_2`` and de Moivre's ``S_1`` step)."""

    local = local_sums(items)
    return Q(3, 4) * local["L1"] - Q(3, 2) * local["L2"] - Q(5, 16) * local["L4"]


def tie_count_law(items: int, candidates: int) -> dict[int, Q]:
    """``P(N = j) = sum_m C(K, j) q_m^j F(m-1)^{K-j}``, ``j = 1..K``, ``N`` the number of candidates at the maximum."""

    _items(items)
    _candidates(candidates)
    q = [Q(comb(items, m), 2**items) for m in range(items + 1)]
    below, law = Q(0), {}
    for j in range(1, candidates + 1):
        law[j] = Q(0)
    for m in range(items + 1):
        for j in range(1, candidates + 1):
            law[j] += comb(candidates, j) * q[m]**j * below**(candidates - j)
        below += q[m]
    return law


def tie_mass(items: int, candidates: int) -> Q:
    """``P(N >= 2) = sum_m [F(m)^K - F(m-1)^K - K q_m F(m-1)^{K-1}]``: a tie at the maximum."""

    _items(items)
    _candidates(candidates)
    q = [Q(comb(items, m), 2**items) for m in range(items + 1)]
    below, total = Q(0), Q(0)
    for m in range(items + 1):
        upto = below + q[m]
        total += upto**candidates - below**candidates - candidates * q[m] * below**(candidates - 1)
        below = upto
    return total


def crude_tie_bound_deficit(items: int, candidates: int) -> Q:
    """``n P(N >= 2) - 2 M_n(K)``: the sign of the route-R2 sufficient condition for ``rho_n >= 1``.

    Since ``1/2 - 2^{-j} >= 1/4`` for ``j >= 2``, ``M_{n+1} - M_n >= P(N >= 2)/4``, so ``n P(N >= 2) >= 2 M_n``
    would give ``rho_n >= 1``.  It is an identity for ``K = 2`` (``N <= 2``) and fails for every ``n``
    at ``K = 3``, by exactly ``-(n/2) sum_m q_m^3``, although ``rho_n(3) = 1``: the bound discards the
    extra ``1/8`` on triple ties.
    """

    return items * tie_mass(items, candidates) - 2 * centered_max(items, candidates)


def _rank(rows: list[list[Q]]) -> int:
    rows = [list(r) for r in rows]
    r = 0
    for c in range(len(rows[0])):
        pivot = next((i for i in range(r, len(rows)) if rows[i][c] != 0), None)
        if pivot is None:
            continue
        rows[r], rows[pivot] = rows[pivot], rows[r]
        head = rows[r][c]
        rows[r] = [x / head for x in rows[r]]
        for i in range(len(rows)):
            if i != r and rows[i][c] != 0:
                f = rows[i][c]
                rows[i] = [a - f * b for a, b in zip(rows[i], rows[r])]
        r += 1
    return r


def _nullspace(rows: list[list[Q]]) -> list[list[Q]]:
    rows = [list(r) for r in rows]
    ncol, pivots, r = len(rows[0]), [], 0
    for c in range(ncol):
        pivot = next((i for i in range(r, len(rows)) if rows[i][c] != 0), None)
        if pivot is None:
            continue
        rows[r], rows[pivot] = rows[pivot], rows[r]
        head = rows[r][c]
        rows[r] = [x / head for x in rows[r]]
        for i in range(len(rows)):
            if i != r and rows[i][c] != 0:
                f = rows[i][c]
                rows[i] = [a - f * b for a, b in zip(rows[i], rows[r])]
        pivots.append(c)
        r += 1
    basis = []
    for free in (c for c in range(ncol) if c not in pivots):
        vector = [Q(0)] * ncol
        vector[free] = Q(1)
        for i, pc in enumerate(pivots):
            vector[pc] = -rows[i][free]
        basis.append(vector)
    return basis


def rational_step_ratio_rank(sequence, degree: int, points: int | None = None) -> dict[str, object]:
    """Exact test of whether ``r_n = sequence(n+1)/sequence(n)`` is a rational function of degree ``<= degree``.

    ``p(n) - r_n s(n) = 0`` at ``n = 1..points`` is linear in the ``2(degree+1)`` coefficients; full
    column rank means no nonzero ``(p, s)`` fits even these points.  For ``K = 2, 3`` the degree-1
    ratio ``(2n+1)/(2n)`` is found; for ``K = 4`` nothing exists through ``RATIONAL_STEP_DEGREE``.
    """

    if type(degree) is not int or degree < 0:
        raise ValueError("degree must be a non-negative integer")
    columns = 2 * (degree + 1)
    points = columns + 4 if points is None else points
    rows = []
    for n in range(1, points + 1):
        ratio = Q(sequence(n + 1)) / Q(sequence(n))
        rows.append([Q(n)**i for i in range(degree + 1)] + [-ratio * Q(n)**i for i in range(degree + 1)])
    rank = _rank(rows)
    return {"degree": degree, "points": points, "rank": rank, "columns": columns, "exists": rank < columns}


def guess_recurrence(sequence, order: int, degree: int, points: int) -> list[list[list[Q]]]:
    """Polynomials ``p_0..p_order`` (degree ``<= degree``) with ``sum_i p_i(n) sequence(n+i) = 0``, ``n = 1..points``.

    Returns a basis of the solution space, each element a list of coefficient lists (low degree first).
    """

    if type(order) is not int or order < 1 or type(degree) is not int or degree < 0:
        raise ValueError("order must be positive and degree non-negative")
    _items(points)
    rows = []
    for n in range(1, points + 1):
        row = []
        for i in range(order + 1):
            value = Q(sequence(n + i))
            row += [value * Q(n)**d for d in range(degree + 1)]
        rows.append(row)
    return [[vector[i * (degree + 1):(i + 1) * (degree + 1)] for i in range(order + 1)] for vector in _nullspace(rows)]


def quadruple_numerator(items: int) -> int:
    """The integer ``2^{4n+1} M_n(4) = n 16^n - 2 sum_{m<n} G(m)^4``, ``G(m) = sum_{j<=m} C(n, j)``."""

    value = centered_max(items, 4) * 2**(4 * items + 1)
    if value.denominator != 1:
        raise ValueError("2^(4n+1) M_n(4) is not an integer")
    return value.numerator


def quadruple_recurrence(verify_items: int = RECURRENCE_VERIFY_ITEMS) -> dict[str, object]:
    """The order-4, degree-8 recurrence of ``u_n = 2^{4n+1} M_n(4)``, guessed on the first points and verified beyond.

    Its leading coefficients give the characteristic polynomial ``75 (x - 16)^2 (x + 2)(x + 4)``: the
    double root ``16`` carries ``16^n sqrt(n)``, the roots ``-2, -4`` are exponentially small parity
    corrections.  No recurrence of order ``<= 3`` exists through degree 12 (nullity zero).
    """

    order, degree = RECURRENCE_ORDER, RECURRENCE_DEGREE
    unknowns = (order + 1) * (degree + 1)
    basis = guess_recurrence(quadruple_numerator, order, degree, unknowns + 8)
    if len(basis) != 1:
        return {"order": order, "degree": degree, "nullity": len(basis), "verified": False}
    polys = basis[0]
    common = 1
    for poly in polys:
        for c in poly:
            common = common * c.denominator // gcd(common, c.denominator)
    integers = [[int(c * common) for c in poly] for poly in polys]
    g = 0
    for poly in integers:
        for c in poly:
            g = gcd(g, abs(c))
    integers = [[c // g for c in poly] for poly in integers]
    if integers[-1][-1] < 0:
        integers = [[-c for c in poly] for poly in integers]
    verified = all(sum(sum(poly[d] * n**d for d in range(degree + 1)) * quadruple_numerator(n + i)
                       for i, poly in enumerate(integers)) == 0 for n in range(1, verify_items + 1))
    leading = [poly[-1] for poly in integers]
    characteristic = [c // leading[-1] for c in leading] if all(c % leading[-1] == 0 for c in leading) else None
    roots_check = None
    if characteristic is not None:
        roots_check = {str(x): sum(c * x**i for i, c in enumerate(characteristic)) == 0 for x in (16, -2, -4)}
        derivative_at_16 = sum(i * c * 16**(i - 1) for i, c in enumerate(characteristic) if i)
        roots_check["16 is a double root"] = derivative_at_16 == 0
    lower = {f"order={o},degree={d}": len(guess_recurrence(quadruple_numerator, o, d, (o + 1) * (d + 1) + 8))
             for o, d in ((1, 8), (2, 8), (3, 12))}
    return {"order": order, "degree": degree, "nullity": 1, "coefficients": integers, "verified_items": verify_items,
            "verified": verified, "characteristic_monic": characteristic, "characteristic_roots": roots_check,
            "lower_order_nullity": lower}


def gaussian_max_moment(candidates: int, power: int) -> float:
    """``E[M_K^power]`` for the maximum of ``K`` standard normals, by the same composite Simpson rule."""

    _candidates(candidates)
    if type(power) is not int or power < 0:
        raise ValueError("power must be a non-negative integer")
    x, cdf, pdf = _gaussian_grid()
    return _simpson(candidates * x**power * pdf * cdf ** (candidates - 1), float(x[1] - x[0]))


def asymptotic_margin(candidates: int) -> float:
    """``c(K) = lim_n n (rho_n - 1) = (E[M_K^3] - (5/2) E[M_K]) / (6 E[M_K])`` (Edgeworth; zero at ``K = 2, 3``).

    Continuity-corrected Edgeworth at ``p = 1/2``: ``F_n(m) = Phi(z) + phi(z)(z^3 - z)/(12 n) + O(n^-2)``,
    ``z = (2m + 1 - n)/sqrt(n)`` (lattice and kurtosis terms), and the midpoint Riemann sum of
    ``phi_K(Phi)`` has exponentially small error, so ``M_n(K) = (sqrt(n)/2) E[M_K] - E[M_K^3 - M_K]/(24 sqrt(n))
    + O(n^-3/2)``; then ``a_n^2 = (E[M_K]/2)^2 (1 - E[M_K^3 - M_K]/(6 n E[M_K]) + ...)``, the step
    margin ``mu_n -> (2/3) E[M_K^3 - M_K]/E[M_K]`` and ``c(K) = (mu_inf - 1)/4``.  For ``K = 2``,
    ``E[M^3] = (5/2) E[M] = 5/(2 sqrt(pi))`` reproduces the exact ``1/(8n)`` deficit.  The expansion is
    cited, not reproved; the limit is checked against Richardson extrapolation of the exact ``rho_n``.
    """

    first = gaussian_max_moment(candidates, 1)
    return (gaussian_max_moment(candidates, 3) - 2.5 * first) / (6 * first)


def asymptotic_normalized_margin(candidates: int) -> float:
    """``mu_inf(K) = 1 + 4 c(K) = (2/3) E[M_K^3 - M_K] / E[M_K]``: the limit of ``4n(n+1)(a_{n+1}^2/a_n^2 - 1)``."""

    return 1 + 4 * asymptotic_margin(candidates)


def wide_monotonicity_sweep(candidates: tuple[int, ...], max_items: int) -> dict[str, dict[str, object]]:
    """Exact ``a_{n+1}^2 > a_n^2`` for every ``K`` in ``candidates`` and ``n <= max_items``, integer arithmetic.

    ``M_n(K) = N_n / 2^{nK}`` with ``N_n = n 2^{nK-1} - sum_{m<n} G(m)^K``; the powers ``G(m)^K`` are
    built incrementally across the sorted ``K`` list.  Per ``K``: the minimal margin ``mu_n`` and ``rho_n``
    with their locations, ``n (rho_n - 1)`` at ``max_items`` with one Richardson step, and the Gaussian
    prediction ``c(K)`` with its residual.  Displayed values are floats; every comparison is exact.
    """

    _items(max_items)
    ks = tuple(sorted(set(candidates)))
    if not ks or any(type(k) is not int or k < 1 for k in ks):
        raise ValueError("candidates must be positive integers")
    keep = {1, 2, 3, 4, 5, 6, 8, 10, 20, 50, 100, 200, 400, max_items - 1, max_items}
    state = {k: None for k in ks}
    summary = {k: {"failures": [], "min_margin": None, "min_margin_at": None, "min_rho": None, "min_rho_at": None,
                   "margins": {}, "rhos": {}} for k in ks}

    def less(a: tuple[int, int, float], b: tuple[int, int, float]) -> bool:
        # (numerator, positive denominator, float value); exact cross-multiplication only on near-ties
        if abs(a[2] - b[2]) > 1e-9 * max(abs(a[2]), abs(b[2]), 1e-300):
            return a[2] < b[2]
        return a[0] * b[1] < b[0] * a[1]

    for n in range(1, max_items + 2):
        partial, running = [], 0
        for j in range(n):
            running += comb(n, j)
            partial.append(running)
        totals = {k: 0 for k in ks}
        for g in partial:
            power, previous_k = g**ks[0], ks[0]
            for k in ks:
                if k != previous_k:
                    power *= g**(k - previous_k)
                    previous_k = k
                totals[k] += power
        for k in ks:
            numerator = n * 2**(n * k - 1) - totals[k]
            if state[k] is not None:
                prev_num, prev_n = state[k]
                lhs = prev_n * numerator * numerator
                rhs = (prev_n + 1) * prev_num * prev_num * 4**k
                margin_num, rho_num, rho_den = 4 * prev_n * (prev_n + 1) * (lhs - rhs), 2 * prev_n * (numerator - 2**k * prev_num), 2**k * prev_num
                margin = (margin_num, rhs, margin_num / rhs)
                rho = (rho_num, rho_den, rho_num / rho_den)
                row = summary[k]
                if lhs <= rhs:
                    row["failures"].append(prev_n)
                if row["min_margin"] is None or less(margin, row["min_margin"]):
                    row["min_margin"], row["min_margin_at"] = margin, prev_n
                if row["min_rho"] is None or less(rho, row["min_rho"]):
                    row["min_rho"], row["min_rho_at"] = rho, prev_n
                if prev_n in keep:
                    row["margins"][prev_n] = margin[2]
                    row["rhos"][prev_n] = rho[2]
            state[k] = (numerator, n)
    out = {}
    for k in ks:
        row = summary[k]
        last = row["rhos"][max_items]
        c_last = max_items * (last - 1)
        richardson = None
        if max_items > 1:
            c_before = (max_items - 1) * (row["rhos"][max_items - 1] - 1)
            richardson = max_items * c_last - (max_items - 1) * c_before
        gaussian = asymptotic_margin(k)
        out[f"K={k}"] = {"candidates": k, "max_items": max_items, "monotone": not row["failures"],
                         "first_failure": row["failures"][0] if row["failures"] else None,
                         "min_margin": row["min_margin"][2], "min_margin_at": row["min_margin_at"],
                         "min_rho": row["min_rho"][2], "min_rho_at": row["min_rho_at"],
                         "rho_at_least_one": row["min_rho"][0] >= row["min_rho"][1],
                         "margin_at_max_items": row["margins"][max_items],
                         "scaled_rho_excess_at_max_items": c_last, "scaled_rho_excess_richardson": richardson,
                         "gaussian_margin_limit": gaussian, "gaussian_normalized_margin_limit": 1 + 4 * gaussian,
                         "richardson_minus_gaussian": None if richardson is None else richardson - gaussian,
                         "margins": {f"n={n}": v for n, v in sorted(row["margins"].items())},
                         "rhos": {f"n={n}": v for n, v in sorted(row["rhos"].items())}}
    return out


# --- D.5 at K >= 4 (version 0.4): an effective second-order bound, hence a proof for every n ---------
#
# The margin D_n(K) = 2n (M_{n+1}(K) - M_n(K)) - M_n(K) = M_n (rho_n - 1) is positive iff rho_n > 1, and
# rho_n >= 1 gives a_{n+1}^2 > a_n^2.  Write H_K(u) = (K/2) u(1-u) - phi_K(u), phi_K(u) = (1 - u^K - (1-u)^K)/2,
# so that M_n(K) = (K/2) S_1 - sum_{m<n} H_K(F_n(m)).  The points {F_n(m)} evolve by midpoint insertion
# (F_{n+1}(m) = mu_m = (F_n(m-1) + F_n(m))/2), and de Moivre's 2n (S_1(n+1) - S_1(n)) = S_1(n) cancels the
# (K/2) S_1 part exactly, leaving the algebraic identity
#
#     D_n(K) = sum_{m<n} H_K(F_n(m)) + 2n sum_{m<=n} sum_{k>=1} H_K^(2k)(mu_m) q_m^(2k) / (4^k (2k)!),
#
# in which H_K = O(w^2) decays in the tails and every local term carries q_m^2.  For n >= N1 = 400 each sum is
# expanded to second order with explicit remainders: a local expansion of q_m (Robbins' Stirling bounds,
# cited), a continuity-corrected CDF expansion F_n(m) = Phi(b) + psi(b)/n + O(R_F / n^2) proved from it by
# the midpoint Euler-Maclaurin formula with explicit kernels, and Poisson summation (cited) for the
# Gaussian grid sums.  The sqrt(n) terms cancel by an integration by parts, the 1/sqrt(n) terms define delta_K,
# and every remainder is bounded by exact rational arithmetic:
#
#     |sqrt(n) D_n(K) - delta_K| <= C_K / n   for all n >= N1.
#
# If some N0 >= N1 has sqrt(N0) D_{N0} > 2 C_K / N0 (an exact check), then D_n > 0 for every n >= N0, and the
# exact integer sweep covers n < N0.  The rational enclosures of exp, phi and Phi below are rigorous (directed
# rounding in integer fixed point); floats appear only in delta_K's quadrature, a consistency check that the
# proof does not use.

EFFECTIVE_START = 400                               # N1: a perfect square, so grid points are rational
EFFECTIVE_CANDIDATES = tuple(range(4, 31))          # K = 4..25 close at N1 = 400; 26..30 after a short exact scan
EFFECTIVE_SCAN_LIMIT = 600
HEAVY_EFFECTIVE_CANDIDATES = tuple(range(31, 41))   # verify(heavy=True): exact scans to N0(K) <= 800
HEAVY_SCAN_LIMIT = 800
HEAVY_TAIL_CANDIDATES = tuple(range(41, 51))        # verify(heavy=True): N0 certified by one exact evaluation only
LOCAL_TAU = Q(1, 2)                                 # the local expansion is used for |m - n/2| <= tau n / 2
CELL_RANGE, CELLS_PER_UNIT = 10, 20                 # cell quadrature on [-10, 10], width 1/20
PI_LOWER, PI_UPPER = Q(314159265358979, 10**14), Q(314159265358980, 10**14)
E_UPPER = Q(2718281828459046, 10**15)
_FIXED_BITS, _ROUND_BITS = 256, 64
DELTA_TOLERANCE = 1e-9


def rational_sqrt_bounds(x, scale: int = 10**15) -> tuple[Q, Q]:
    """``(lo, hi)`` with ``lo <= sqrt(x) <= hi``, both rationals with denominator ``scale``."""

    x = Q(x)
    if x < 0:
        raise ValueError("x must be non-negative")
    root = isqrt(x.numerator * scale * scale // x.denominator)
    return Q(root, scale), Q(root + 1, scale)


def _sqrt_hi(x) -> Q:
    return rational_sqrt_bounds(x)[1]


def _sqrt_lo(x) -> Q:
    return rational_sqrt_bounds(x)[0]


INV_SQRT_2PI_UPPER = 1 / _sqrt_lo(2 * PI_LOWER)     # phi(0) <= this
INV_SQRT_2PI_LOWER = 1 / _sqrt_hi(2 * PI_UPPER)
SQRT_E_UPPER = _sqrt_hi(E_UPPER)


def _round_up(x: Q, bits: int = _ROUND_BITS) -> Q:
    scale = 1 << bits
    return Q(-((-x.numerator * scale) // x.denominator), scale)


def ceil_decimal(x, digits: int = 6) -> Q:
    """The least multiple of ``10^-digits`` that is ``>= x`` (constants are reported, and used, rounded up)."""

    x = Q(x)
    scale = 10**digits
    return Q(-((-x.numerator * scale) // x.denominator), scale)


def _round_down(x: Q, bits: int = _ROUND_BITS) -> Q:
    scale = 1 << bits
    return Q(x.numerator * scale // x.denominator, scale)


@lru_cache(maxsize=None)
def exp_neg_bounds(x) -> tuple[Q, Q]:
    """``(lo, hi)`` with ``lo <= exp(-x) <= hi`` for rational ``x >= 0``.

    ``u = x / 2^k <= 1/2``: the alternating Taylor series of ``exp(-u)`` brackets it between consecutive partial
    sums; ``k`` squarings in integer fixed point (``2^-256``), rounding down for ``lo`` and up for ``hi``.
    """

    x = Q(x)
    if x < 0:
        raise ValueError("x must be non-negative")
    k = 0
    while x > Q(1, 2) * 2**k:
        k += 1
    u = x / 2**k
    lo, term = Q(0), Q(1)
    for i in range(24):
        lo += term if i % 2 == 0 else -term
        term = term * u / (i + 1)
    hi = lo + term
    scale = 1 << _FIXED_BITS
    lo_i = lo.numerator * scale // lo.denominator
    hi_i = -((-hi.numerator * scale) // hi.denominator)
    for _ in range(k):
        lo_i = (lo_i * lo_i) >> _FIXED_BITS
        hi_i = -((-(hi_i * hi_i)) >> _FIXED_BITS)
    return Q(lo_i, scale), Q(hi_i, scale)


def normal_density_bounds(t) -> tuple[Q, Q]:
    """Rational enclosure of ``phi(t) = exp(-t^2/2) / sqrt(2 pi)``."""

    lo, hi = exp_neg_bounds(Q(t) * Q(t) / 2)
    return INV_SQRT_2PI_LOWER * lo, INV_SQRT_2PI_UPPER * hi


@lru_cache(maxsize=None)
def normal_cdf_bounds(t) -> tuple[Q, Q]:
    """Rational enclosure of ``Phi(t)``.

    ``0 < t <= 6``: ``Phi(t) = 1/2 + phi(t) sum_i t^(2i+1)/(2i+1)!!`` (positive terms; after 120 terms the
    remainder is at most the next term over ``1 - t^2/243``).  ``t > 6``: Mills' ratio,
    ``t phi(t)/(1+t^2) <= 1 - Phi(t) <= phi(t)/t`` (integrate ``phi(s) <= (s/t) phi(s)`` and
    ``(1 + 1/s^2) phi(s) = -(phi(s)/s)'`` over ``[t, oo)``).  ``t < 0`` by symmetry.
    """

    t = Q(t)
    if t < 0:
        lo, hi = normal_cdf_bounds(-t)
        return 1 - hi, 1 - lo
    if t == 0:
        return Q(1, 2), Q(1, 2)
    density_lo, density_hi = normal_density_bounds(t)
    if t > 6:
        return 1 - density_hi / t, 1 - density_lo * t / (1 + t * t)
    scale = 1 << _FIXED_BITS
    a2, b2 = (t * t).numerator, (t * t).denominator
    term_lo = t.numerator * scale // t.denominator
    term_hi = -((-t.numerator * scale) // t.denominator)
    sum_lo = sum_hi = 0
    terms = 120
    for i in range(terms):
        sum_lo += term_lo
        sum_hi += term_hi
        term_lo = term_lo * a2 // (b2 * (2 * i + 3))
        term_hi = -((-term_hi * a2) // (b2 * (2 * i + 3)))
    tail = Q(term_hi, scale) / (1 - t * t / (2 * terms + 3))
    return Q(1, 2) + density_lo * Q(sum_lo, scale), Q(1, 2) + density_hi * (Q(sum_hi, scale) + tail)


# polynomials as coefficient lists, lowest degree first

def _padd(a, b):
    size = max(len(a), len(b))
    return [Q(a[i] if i < len(a) else 0) + Q(b[i] if i < len(b) else 0) for i in range(size)]


def _pscale(a, c):
    return [Q(v) * c for v in a]


def _pmul(a, b):
    out = [Q(0)] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        if x:
            for j, y in enumerate(b):
                out[i + j] += x * y
    return out


def _pderiv(a):
    return [Q(i) * a[i] for i in range(1, len(a))] or [Q(0)]


def _pphi(a, power: int = 1):
    """``(phi^power P)' / phi^power = P' - power z P``."""

    return _padd(_pderiv(a), _pscale([Q(0)] + list(a), -power))


def _pphi_iter(a, times: int, power: int = 1):
    for _ in range(times):
        a = _pphi(a, power)
    return a


def _pabs(a):
    return [abs(Q(v)) for v in a]


def _ptrim(a):
    a = [Q(v) for v in a]
    while len(a) > 1 and a[-1] == 0:
        a.pop()
    return a


def _peval(a, x):
    out = Q(0)
    for c in reversed(a):
        out = out * x + c
    return out


def _double_factorial(m: int) -> int:
    out = 1
    while m > 1:
        out *= m
        m -= 2
    return out


def _bernstein_sup(c, width=Q(1), elevate: int = 40) -> Q:
    """Upper bound for ``sup_{[0, width]} |P|``: the largest Bernstein coefficient after degree elevation."""

    c = [Q(v) * Q(width)**i for i, v in enumerate(c)]
    degree = len(c) - 1
    top = degree + elevate
    return max(abs(sum((Q(comb(j, i), comb(top, i)) * c[i] for i in range(min(j, degree) + 1)), Q(0)))
               for j in range(top + 1))


def gaussian_moment_bound(power: int, phi_power: int) -> Q:
    """Upper bound for ``int |z|^power phi(z)^phi_power dz`` (``phi_power >= 1``).

    Even ``power = 2i``: ``(2i-1)!! (2 pi)^{(1-a)/2} / (a^i sqrt(a))``; odd ``2i+1``: ``i! 2^{i+1} (2 pi)^{-a/2} / a^{i+1}``.
    """

    if type(power) is not int or power < 0 or type(phi_power) is not int or phi_power < 1:
        raise ValueError("power must be >= 0 and phi_power >= 1")
    a = phi_power
    if power % 2 == 0:
        i = power // 2
        return _double_factorial(2 * i - 1) * INV_SQRT_2PI_UPPER**(a - 1) / (Q(a)**i * _sqrt_lo(a))
    i = (power - 1) // 2
    return factorial(i) * Q(2)**(i + 1) * INV_SQRT_2PI_UPPER**a / Q(a)**(i + 1)


def gaussian_tail_bound(power: int, phi_power: int, start) -> Q:
    """``int_A^oo z^k phi(z)^a dz <= A^k phi(A)^a / lambda``, ``lambda = aA - k/A`` (``k >= 0``) or ``aA`` (``k = -1``).

    ``log(z^k phi^a)`` has derivative ``k/z - az <= -lambda`` on ``[A, oo)`` when ``a A^2 > k`` (for ``k = -1`` because
    ``-1/z <= 0``), so the integrand is at most its value at ``A`` times ``exp(-lambda (z - A))``.
    """

    A = Q(start)
    lam = phi_power * A - Q(power) / A if power >= 0 else phi_power * A
    if A <= 0 or phi_power * A * A <= max(power, 0) or lam <= 0:
        raise ValueError("tail start too small for this power")
    return A**power * normal_density_bounds(A)[1]**phi_power / lam


def gaussian_tail_sup_bound(power: int, phi_power: int, start) -> Q:
    """``sup_{z >= A} z^k phi(z)^a = A^k phi(A)^a`` once ``a A^2 >= k`` (the function decreases there)."""

    A = Q(start)
    if A <= 0 or phi_power * A * A < power:
        raise ValueError("tail start too small for this power")
    return A**power * normal_density_bounds(A)[1]**phi_power


def _falling(K: int, j: int) -> int:
    out = 1
    for i in range(j):
        out *= K - i
    return out


class ExcessPolynomial:
    """``H_K(u) = (K/2) u(1-u) - phi_K(u)`` with ``phi_K(u) = (1 - u^K - (1-u)^K)/2``; ``H_K = O(w^2)``, ``w = u(1-u)``.

    Derivatives in closed form: ``H' = (K/2)(1 - 2u) + (K/2)(u^(K-1) - (1-u)^(K-1))``,
    ``H'' = -K + (K(K-1)/2)(u^(K-2) + (1-u)^(K-2))`` and ``H^(j) = (K^(j)/2)(u^(K-j) + (-1)^j (1-u)^(K-j))`` for ``j >= 3``
    (``K^(j)`` the falling factorial).  ``H_2 = H_3 = 0``, ``H_4 = w^2``, ``H_5 = (5/2) w^2``.
    """

    def __init__(self, candidates: int):
        _candidates(candidates)
        if candidates < 2:
            raise ValueError("candidates must be at least 2")
        self.K = candidates
        self.w_coefficients = self._w_coefficients()
        self.lambda0 = _bernstein_sup(self.w_coefficients[2:] or [Q(0)], Q(1, 4))      # sup |H| / w^2
        self.lambda1 = _bernstein_sup(_pderiv(self.w_coefficients)[1:] or [Q(0)], Q(1, 4))   # sup |H'| / w

    def _w_coefficients(self):
        hw = [-c for c in tie_polynomial(self.K)] + [Q(0), Q(0)]
        hw[1] += Q(self.K, 2)
        return _ptrim(hw)

    def u_coefficients(self):
        K = self.K
        out = [Q(comb(K, i) * (-1)**i, 2) for i in range(K + 1)]
        out[0] -= Q(1, 2)
        out[1] += Q(K, 2)
        out[2] -= Q(K, 2)
        out[K] += Q(1, 2)
        return _ptrim(out)

    def linear_part(self, j: int):
        """``((c0, c1), c)``: ``H^(j) = c0 + c1 u + c (u^m + (-1)^j (1-u)^m)``, ``m = K - j``, for ``1 <= j <= K``."""

        K = self.K
        if j == 1:
            return (Q(K, 2), Q(-K)), Q(K, 2)
        if j == 2:
            return (Q(-K), Q(0)), Q(_falling(K, 2), 2)
        return (Q(0), Q(0)), Q(_falling(K, j), 2)

    def value(self, j: int, u: Q) -> Q:
        """``H^(j)(u)`` exactly from the closed form (``1 <= j <= K``)."""

        (c0, c1), c = self.linear_part(j)
        m = self.K - j
        return c0 + c1 * u + c * (u**m + (-1)**j * (1 - u)**m)

    def _interval_bound(self, j: int, lo: Q, hi: Q) -> Q:
        if j > self.K:
            return Q(0)
        (c0, c1), c = self.linear_part(j)
        m = self.K - j
        lin_lo, lin_hi = sorted((c0 + c1 * lo, c0 + c1 * hi))
        if j % 2 == 1:
            pow_lo, pow_hi = lo**m - (1 - lo)**m, hi**m - (1 - hi)**m
        else:
            pow_lo, pow_hi = lo**m + (1 - hi)**m, hi**m + (1 - lo)**m
        return max(abs(lin_lo + c * pow_lo), abs(lin_hi + c * pow_hi))

    def derivative_bound(self, j: int, lo: Q, hi: Q) -> Q:
        """``sup_{u in [lo, hi]} |H^(j)(u)|``, ``0 <= lo <= hi <= 1``, ``j >= 1``: the smaller of the interval form (linear part
        and ``u^m - (1-u)^m`` -- increasing, odd ``j`` -- or ``u^m + (1-u)^m`` -- endpoint bounds, even ``j`` -- bounded
        separately) and the mean-value form ``|H^(j)(centre)| + radius sup |H^(j+1)|``."""

        if j > self.K:
            return Q(0)
        if j < 1:
            raise ValueError("j must be at least 1 (H itself is bounded by lambda0 w^2)")
        direct = self._interval_bound(j, lo, hi)
        if hi == lo or j == self.K:
            return direct
        centre, radius = (lo + hi) / 2, (hi - lo) / 2
        return min(direct, abs(self.value(j, centre)) + radius * self._interval_bound(j + 1, lo, hi))

    def sup(self, j: int) -> Q:
        """``sup_{[0,1]} |H^(j)|``."""

        if j > self.K:
            return Q(0)
        if j == 0:
            return self.lambda0 / 16
        if j == 1:
            return self.lambda1 / 4
        if j == 2:
            return max(self.derivative_bound(2, v, v) for v in (Q(0), Q(1, 2)))
        return Q(_falling(self.K, j), 2) * (2 if j == self.K else 1)


def excess_polynomial(candidates: int) -> list[Q]:
    """Coefficients (in ``u``) of ``H_K(u) = (K/2) u(1-u) - phi_K(u)``."""

    return ExcessPolynomial(candidates).u_coefficients()


def _binomial_cdf_integers(items: int) -> list[int]:
    partial, running = [], 0
    for j in range(items + 1):
        running += comb(items, j)
        partial.append(running)
    return partial


def _centered_max_numerator(items: int, candidates: int) -> int:
    """``2^{nK} M_n(K) = n 2^{nK-1} - sum_{m<n} G(m)^K``."""

    partial = _binomial_cdf_integers(items)
    return items * 2**(items * candidates - 1) - sum(g**candidates for g in partial[:-1])


def margin_deficit(items: int, candidates: int) -> Q:
    """``D_n(K) = 2n (M_{n+1}(K) - M_n(K)) - M_n(K) = M_n (rho_n - 1)``, exact (integer numerators)."""

    _items(items)
    _candidates(candidates)
    n, K = items, candidates
    now, nxt = _centered_max_numerator(n, K), _centered_max_numerator(n + 1, K)
    return Q(2 * n * nxt - (2 * n + 1) * 2**K * now, 2**((n + 1) * K))


def margin_deficit_from_excess(items: int, candidates: int) -> Q:
    """The same ``D_n(K)`` from the identity ``sum_{m<n} H(F(m)) + 2n sum_m sum_k H^(2k)(mu_m) q_m^(2k) / (4^k (2k)!)``."""

    _items(items)
    H = ExcessPolynomial(candidates)
    coeffs = H.u_coefficients()
    derivatives = [coeffs]
    for _ in range(candidates):
        derivatives.append(_pderiv(derivatives[-1]))
    cdf = [Q(g, 2**items) for g in _binomial_cdf_integers(items)]
    first = sum((_peval(coeffs, cdf[m]) for m in range(items)), Q(0))
    second, previous = Q(0), Q(0)
    for m in range(items + 1):
        mu, q = (previous + cdf[m]) / 2, cdf[m] - previous
        for k in range(1, candidates // 2 + 1):
            second += _peval(derivatives[2 * k], mu) * q**(2 * k) / (4**k * factorial(2 * k))
        previous = cdf[m]
    return first + 2 * items * second


def midpoint_euler_maclaurin_check(max_degree: int = 5) -> bool:
    """Exact check of ``sum_cells D h(c) = int h - (D^2/24)[h'] + (7 D^4/5760)[h''']`` for polynomials of degree <= 5.

    The remainder is ``-int K_6 h^(6)`` with the kernel ``K_6 = D^6 k_6``, ``k_6(a) = 7a^2/11520 - a^4/576 + a^6/720`` in the
    distance ``a`` to the cell edge, increasing on ``[0, 1/2]``, so ``0 <= K_6 <= D^6/15360``; it vanishes on quintics.
    """

    width, left, cells = Q(1, 3), Q(-2, 7), 5
    right = left + cells * width
    ok = True
    for degree in range(max_degree + 1):
        h = [Q(0)] * degree + [Q(1)]
        antiderivative = [Q(0)] + [c / (i + 1) for i, c in enumerate(h)]
        d1, d3 = _pderiv(h), _pderiv(_pderiv(_pderiv(h)))
        lhs = sum((width * _peval(h, left + (i + Q(1, 2)) * width) for i in range(cells)), Q(0))
        rhs = (_peval(antiderivative, right) - _peval(antiderivative, left)
               - width**2 / 24 * (_peval(d1, right) - _peval(d1, left))
               + 7 * width**4 / 5760 * (_peval(d3, right) - _peval(d3, left)))
        ok &= lhs == rhs
    kernel = [Q(0), Q(0), Q(7, 11520), Q(0), Q(-1, 576), Q(0), Q(1, 720)]
    ok &= _peval(kernel, Q(1, 2)) == Q(1, 15360) and _peval(_pderiv(kernel), Q(1, 2)) == 0
    ok &= _peval(_pderiv(_pderiv(kernel)), Q(0)) == Q(7, 5760)     # k_6'' = k_4 - mean(k_4), mean(k_4) = -7/5760
    return ok


class GaussianCells:
    """Rigorous cell quadrature for ``W(z) = sum_g c_g |P_g(z)| phi(z)^{a_g} |U_g(Phi(z))|`` on ``[-L, L]`` plus tails.

    Each cell carries an upper bound for ``phi`` and an enclosure of ``Phi`` (rounded outward to ``2^-64``).  On a cell
    ``|P|`` is bounded by an integer Taylor shift at the centre (exact for polynomials), and ``|U|`` -- a derivative of
    ``H_K``, optionally at points within ``widen`` of ``Phi`` -- by :meth:`ExcessPolynomial.derivative_bound`.
    ``U = (H, 0, ...)`` uses ``|H| <= lambda0 w^2``.  Tails ``|z| > L`` use :func:`gaussian_tail_bound` with the sup of
    ``|U|``; a group with ``a = 0`` must have ``U = H'`` and uses ``|H'(Phi)| <= lambda1 (1 - Phi(|z|)) <= lambda1 phi/|z|``.
    """

    def __init__(self, half_range: int = CELL_RANGE, per_unit: int = CELLS_PER_UNIT):
        self.L, self.per_unit, self.width = Q(half_range), per_unit, Q(1, per_unit)
        self.cells = []
        count = 2 * half_range * per_unit
        for i in range(count):
            left = -self.L + i * self.width
            right = left + self.width
            nearest = Q(0) if left < 0 < right else min(abs(left), abs(right))
            u_lo = _round_down(max(normal_cdf_bounds(left)[0], Q(0)))
            u_hi = min(_round_up(normal_cdf_bounds(right)[1]), Q(1))
            centre = 2 * i + 1 - 2 * half_range * per_unit      # centre = this / (2 per_unit)
            self.cells.append((centre, _round_up(normal_density_bounds(nearest)[1]), u_lo, u_hi))
        self._p, self._u = {}, {}

    def poly_bounds(self, poly):
        P = _ptrim(poly)
        key = tuple(P)
        if key not in self._p:
            degree, den = len(P) - 1, 1
            for c in P:
                den = den * c.denominator // gcd(den, c.denominator)
            scale = 2 * self.per_unit
            base = [int(c * den) * scale**(degree - i) for i, c in enumerate(P)]   # P(y/scale) = base(y) / (den scale^d)
            values = []
            for centre, _, _, _ in self.cells:
                b = list(base)
                for i in range(degree):
                    for j in range(degree - 1, i - 1, -1):
                        b[j] += centre * b[j + 1]
                values.append(_round_up(Q(sum(abs(v) for v in b), den * scale**degree)))
            self._p[key] = values
        return self._p[key]

    def excess_bounds(self, H: ExcessPolynomial, j: int, widen: Q = Q(0)):
        key = (H.K, j, widen)
        if key not in self._u:
            values = []
            for _, _, u_lo, u_hi in self.cells:
                lo, hi = max(Q(0), u_lo - widen), min(Q(1), u_hi + widen)
                if j == 0:
                    w = Q(1, 4) if lo <= Q(1, 2) <= hi else max(lo * (1 - lo), hi * (1 - hi))
                    values.append(_round_up(H.lambda0 * w * w))
                else:
                    values.append(_round_up(H.derivative_bound(j, lo, hi)))
            self._u[key] = values
        return self._u[key]

    def _values(self, groups):
        total = [Q(0)] * len(self.cells)
        for coef, P, a, U in groups:
            pb = self.poly_bounds(P)
            ub = self.excess_bounds(*U) if U is not None else None
            for i, (_, phi_max, _, _) in enumerate(self.cells):
                v = coef * pb[i] * phi_max**a
                total[i] += v * ub[i] if ub is not None else v
        return total

    def _tail(self, groups, integral: bool):
        out = Q(0)
        for coef, P, a, U in groups:
            sup_u = U[0].sup(U[1]) if U is not None else Q(1)
            for k, c in enumerate(_ptrim(P)):
                if not c:
                    continue
                if a >= 1:
                    piece = 2 * gaussian_tail_bound(k, a, self.L) if integral else gaussian_tail_sup_bound(k, a, self.L)
                    out += coef * abs(c) * sup_u * piece
                else:
                    if U is None or U[1] != 1:
                        raise ValueError("a group without a Gaussian factor must be H'")
                    piece = (2 * gaussian_tail_bound(k - 1, 1, self.L) if integral
                             else gaussian_tail_sup_bound(k, 1, self.L) / self.L)
                    out += coef * abs(c) * U[0].lambda1 * piece
        return out

    def integral(self, groups) -> Q:
        return sum(self._values(groups), Q(0)) * self.width + self._tail(groups, True)

    def sup(self, groups) -> Q:
        return max(max(self._values(groups)), self._tail(groups, False))


def _derivative_groups(groups):
    """Majorant groups for ``|W'|``: ``|P'| phi^a |U| + a |zP| phi^a |U| + |P| phi^{a+1} |U'|`` (the moving window of a
    widened ``U`` moves at speed ``phi``, so its sup changes at rate at most ``sup |U'| phi``)."""

    out = []
    for coef, P, a, U in groups:
        out.append((coef, _pderiv(P), a, U))
        if a:
            out.append((coef * a, [Q(0)] + list(P), a, U))
        if U is not None and U[1] + 1 <= U[0].K:
            out.append((coef, P, a + 1, (U[0], U[1] + 1) + tuple(U[2:])))
    return [g for g in out if any(g[1])]


def _moment_bound(groups) -> Q:
    """Crude: ``int sum c |P| phi^a |U(Phi)| <= sum c sup|U| sum_k |p_k| int |z|^k phi^a``."""

    out = Q(0)
    for coef, P, a, U in groups:
        sup_u = U[0].sup(U[1]) if U is not None else Q(1)
        out += coef * sup_u * sum((abs(c) * gaussian_moment_bound(k, a) for k, c in enumerate(P) if c), Q(0))
    return out


# the polynomials of the expansion (z = standardized grid point)
EXPANSION_P = [Q(-1, 4), Q(0), Q(1, 2), Q(0), Q(-1, 12)]                        # q = D phi (1 + p/n + ...)
EXPANSION_C2 = [Q(0), Q(0), Q(-1, 3), Q(0), Q(1, 4), Q(0), Q(-1, 30)]
EXPANSION_P2 = _padd(EXPANSION_C2, _pscale(_pmul(EXPANSION_P, EXPANSION_P), Q(1, 2)))   # second-order term of q
PSI_FACTOR = [Q(0), Q(-1, 12), Q(0), Q(1, 12)]                                   # psi = phi (z^3 - z)/12
CHI_FACTOR = [Q(0), Q(-7, 12), Q(0), Q(1, 12)]                                   # chi = psi - z phi / 2


def local_expansion_majorants(start: int = EFFECTIVE_START) -> dict[str, object]:
    """Lemma L: for ``n >= start``, ``|z_j| <= tau sqrt(n)``: ``q_j = D phi(z_j) (1 + p/n + e_j)`` with
    ``|e_j| <= (|p_2| + 1/18)/n^2 + e_3(z_j)/n^3`` and ``q_j <= D phi(z_j) Gamma``.

    From Robbins (cited), ``log(q_j/(D phi)) = p/n + c_2/n^2 + rho_eps + eta_3``: ``-(n/2)(Lambda(t) - t^2)``,
    ``-(1/2)log(1-t^2)`` (series with positive terms, tails ``<= z^8/(56 n^3 (1-t^2))``, ``z^6/(6 n^3 (1-t^2))``) and
    ``r_n - r_j - r_{n-j} = -1/(4n) - z^2/(3n^2) - z^4/(3n^3(1-t^2)) + rho_eps`` with
    ``-1/(144 n^2) < rho_eps < (1+t^2)/(18 n^2 (1-t^2)^2) <= (1/18 + eps_1 z^2/n)/n^2`` (chord of a convex function of ``t^2``).
    Then ``e = e^a - 1 - p/n`` is expanded to second order, the cubic remainder carrying ``Gamma = e^{a_max/n}`` with
    ``a <= (3 kappa^2/4 - 1/4)/n + c_eps/n^2``.  All majorants are even polynomials with non-negative coefficients.
    """

    N = Q(start)
    tau = LOCAL_TAU
    kappa = 1 / (1 - tau**2)
    c_eps = (1 + tau**2) / (18 * (1 - tau**2)**2)
    eps1 = (c_eps - Q(1, 18)) / tau**2
    p_abs = _pabs(EXPANSION_P)
    eta3 = [Q(0)] * 4 + [kappa / 3, Q(0), kappa / 6, Q(0), kappa / 56]
    eta_bar = _padd(_padd(_pabs(EXPANSION_C2), [Q(1, 18)]), _pscale(_padd(eta3, [0, 0, eps1]), 1 / N))
    a_max = (3 * kappa**2 - 1) / 4 + c_eps / N
    gamma = 1 / (1 - a_max / N)
    cube = _padd(p_abs, _pscale(eta_bar, 1 / N))
    e3 = _padd(_padd(_padd([0, 0, eps1], eta3), _pmul(p_abs, eta_bar)), _pscale(_pmul(eta_bar, eta_bar), 1 / (2 * N)))
    e3 = _ptrim(_padd(e3, _pscale(_pmul(_pmul(cube, cube), cube), gamma / 6)))
    return {"tau": tau, "kappa": kappa, "eps1": eps1, "gamma": gamma, "p_abs": p_abs, "e3": e3}


def cdf_and_midpoint_constants(start: int = EFFECTIVE_START, cells: GaussianCells | None = None) -> dict[str, object]:
    """Lemma F (``|F_n(m) - Phi(b) - psi(b)/n| <= R_F/n^2`` for ``|b| <= sqrt(n)/2 - 4/sqrt(n)``) and Lemma M
    (``|mu_m - Phi(z) - chi(z)/n| <= R_mu/n^2`` for ``|z| <= sqrt(n)/2 - 5/sqrt(n)``), ``n >= start``.

    Lemma F: ``F(m) = sum_{j<j0} q_j + sum_{j0}^m D f(z_j) + sum_{j0}^m D phi e_j``, ``f = phi (1 + p/n)``; the midpoint
    Euler-Maclaurin formula gives ``Phi(b) + phi(b)(b^3-3b)/(12n) - (1/6n) f'(b) + (7/(360 n^2)) f'''(b) - int K_6 f^(6)``,
    i.e. ``Phi(b) + psi(b)/n`` plus ``[-(phi p)'(b)/6 + (7/360) phi'''(b)]/n^2``, terms of order ``n^-3``, the local errors
    ``sum D phi |e_j|`` and tails (Chernoff ``e^{-n/8}``, Gaussian tails beyond ``sqrt(n)/2 - 1/sqrt(n)``).  Lemma M: average
    Lemma F at ``z +- 1/sqrt(n)`` (Taylor: ``sup|phi'''|/24`` and ``sup|psi''|/2``).
    """

    cells = cells or GaussianCells()
    N = Q(start)
    rt = Q(isqrt(start))
    if rt * rt != start or start < 100:
        raise ValueError("start must be a perfect square >= 100")
    loc = local_expansion_majorants(start)
    one = [Q(1)]
    p1 = _pphi(EXPANSION_P)
    t3 = _pphi_iter(one, 3)
    out = {}
    out["leading_sup"] = cells.sup([(Q(1), _padd(_pscale(p1, Q(-1, 6)), _pscale(t3, Q(7, 360))), 1, None)])
    p3, t6, p6 = _pphi_iter(EXPANSION_P, 3), _pphi_iter(one, 6), _pphi_iter(EXPANSION_P, 6)
    out["third_order"] = (Q(7, 360) * cells.sup([(Q(1), p3, 1, None)])
                          + (cells.integral([(Q(1), t6, 1, None)]) + cells.integral([(Q(1), p6, 1, None)]) / N) / 240) / N
    step = 2 / rt
    out["local_second_order"] = (cells.integral([(Q(1), EXPANSION_P2, 1, None)])
                                 + step * cells.integral([(Q(1), _pphi(EXPANSION_P2), 1, None)]))
    out["robbins_slack"] = Q(1, 18) * (1 + step * cells.integral([(Q(1), _pphi(one), 1, None)]))
    e3 = loc["e3"]
    out["local_third_order"] = (_moment_bound([(Q(1), e3, 1, None)]) + step * _moment_bound([(Q(1), _pabs(_pphi(e3)), 1, None)])) / N
    A = rt / 2 - 1 / rt
    f0 = _padd(one, _pscale(_pabs(EXPANSION_P), 1 / N))
    f1 = _padd([0, 1], _pscale(_pabs(p1), 1 / N))
    f3 = _padd(_pabs(t3), _pscale(_pabs(p3), 1 / N))
    # n^2 [e^{-n/8} + int_A^oo |f| + |f'(l)|/(6n) + 7|f'''(l)|/(360 n^2)]: each term n^d A^k e^{-A^2/2}, decreasing for n >= start
    out["tails"] = (N**2 * exp_neg_bounds(N / 8)[1]
                    + N**2 * sum((c * gaussian_tail_bound(k, 1, A) for k, c in enumerate(f0) if c), Q(0))
                    + N / 6 * sum((c * gaussian_tail_sup_bound(k, 1, A) for k, c in enumerate(f1) if c), Q(0))
                    + Q(7, 360) * sum((c * gaussian_tail_sup_bound(k, 1, A) for k, c in enumerate(f3) if c), Q(0)))
    out["R_F"] = sum((out[k] for k in ("leading_sup", "third_order", "local_second_order", "robbins_slack",
                                       "local_third_order", "tails")), Q(0))
    psi2 = _pphi_iter(PSI_FACTOR, 2)
    out["R_mu"] = cells.sup([(Q(1), t3, 1, None)]) / 24 + cells.sup([(Q(1), psi2, 1, None)]) / 2 + out["R_F"]
    out["psi_sup"] = cells.sup([(Q(1), PSI_FACTOR, 1, None)])
    out["chi_sup"] = cells.sup([(Q(1), CHI_FACTOR, 1, None)])
    out["local"] = loc
    out["start"] = start
    return out


def _poisson_U(H: ExcessPolynomial, j: int, B: Q) -> Q:
    """``sup |H^(j)(Phi(x + iy))| <= |c0| + |c1| B + 2 c B^m`` (``|Phi|, |1 - Phi| <= B`` on the strip)."""

    (c0, c1), c = H.linear_part(j)
    return abs(c0) + abs(c1) * B + 2 * c * B**(H.K - j)


def poisson_strip_integral(terms, H: ExcessPolynomial | None = None, strip=Q(1)) -> Q:
    """``sup_{|y| <= s} int |h(x + iy)| dx`` for ``h = sum c z^k phi^a H^(j)(Phi)`` (``j >= 1``): ``|phi(x+iy)| = phi(x) e^{y^2/2}``,
    ``|Phi(x+iy)|, |1-Phi(x+iy)| <= B = 1 + s phi(0) e^{s^2/2}``, ``|z| <= |x| + s``."""

    B = 1 + strip * INV_SQRT_2PI_UPPER * SQRT_E_UPPER**(strip * strip)
    total = Q(0)
    for coef, P, a, j in terms:
        sup_u = _poisson_U(H, j, B) if j is not None else Q(1)
        for k, c in enumerate(P):
            if c:
                moment = sum((comb(k, i) * strip**(k - i) * gaussian_moment_bound(i, a) for i in range(k + 1)), Q(0))
                total += abs(coef) * abs(c) * sup_u * SQRT_E_UPPER**(a * strip * strip) * moment
    return total


def poisson_strip_integral_excess(H: ExcessPolynomial, strip=Q(1)) -> Q:
    """Same for ``h = H(Phi)``: ``|w(Phi(x+iy))| <= B c_s phi(x)`` with ``c_s = sqrt(2 pi)/2 + s e^{s^2/2}`` (using
    ``1 - Phi(x) <= e^{-x^2/2}/2`` for ``x >= 0``), and ``|H| <= |w|^2 sum_i |h_i| |w|^{i-2}``."""

    B = 1 + strip * INV_SQRT_2PI_UPPER * SQRT_E_UPPER**(strip * strip)
    t = B * (1 / (2 * INV_SQRT_2PI_LOWER) + strip * SQRT_E_UPPER**(strip * strip))
    total = sum((abs(c) * (t * INV_SQRT_2PI_UPPER)**(i - 2) for i, c in enumerate(H.w_coefficients) if i >= 2), Q(0))
    return t * t * total * gaussian_moment_bound(0, 2)


def poisson_factor(start: int, strip=Q(1)) -> Q:
    """``n^2 E/(1-E)``, ``E = exp(-pi s sqrt n)``, at ``n = start`` (decreasing beyond): Poisson summation (cited) turns a
    grid sum of spacing ``2/sqrt n`` into ``(sqrt n/2) int h`` plus at most ``sqrt(n) J E/(1-E)``, ``J`` the strip integral."""

    E = exp_neg_bounds(PI_LOWER * strip * _sqrt_lo(start))[1]
    return Q(start)**2 * E / (1 - E)


def second_order_margin_constant(candidates: int, start: int = EFFECTIVE_START, cells: GaussianCells | None = None,
                                 base: dict | None = None) -> dict[str, object]:
    """``C_K`` with ``|sqrt(n) D_n(K) - delta_K| <= C_K / n`` for every ``n >= start`` (exact rational upper bound).

    Pieces (each a bound on ``n^{3/2}`` times an error of ``D_n``, valid for all ``n >= start``):
    ``H1`` CDF error through ``H'(Phi)`` (``R_F int |H'(Phi)| / 2`` + BV term); ``H2`` the quadratic Taylor term of ``H``
    (``|H''|`` within ``sup|psi|/n + R_F/n^2`` of ``Phi``); ``H3`` Poisson remainders of the two CDF-sum grid sums; ``L1`` the
    ``k = 1`` local term (``q^2 = (4/n) phi^2 (1 + 2p/n + E_2)``, ``H''(mu) = H''(Phi) + H'''(Phi) chi/n + eps_H``); ``L2``
    Poisson remainders of the three local grid sums; ``L3`` the ``k = 2`` local term; ``L5`` the ``k >= 3`` local terms
    (``q^(2k) <= q_max^(2k-4) (D phi Gamma)^4``); ``tails`` everything outside the expansion regions (Chernoff and
    Gaussian tails, ``e^{-n/8}`` scale).  Grid sums of non-negative majorants use ``sum h <= (sqrt n/2) int h + int |h'|``.
    """

    _candidates(candidates)
    if candidates < 2:
        raise ValueError("candidates must be at least 2")
    cells = cells or GaussianCells()
    base = base or cdf_and_midpoint_constants(start, cells)
    if base["start"] != start:
        raise ValueError("base constants were computed for another start")
    N, rt = Q(start), Q(isqrt(start))
    H = ExcessPolynomial(candidates)
    K = candidates
    R_F, R_mu, loc = base["R_F"], base["R_mu"], base["local"]
    p_abs, e3, Gam = loc["p_abs"], loc["e3"], loc["gamma"]
    one = [Q(1)]
    d_mu = base["chi_sup"] / N + R_mu / N**2
    d_F = base["psi_sup"] / N + R_F / N**2
    out = {"candidates": K, "start": start}
    out["H1"] = R_F * (cells.integral([(Q(1), one, 0, (H, 1))]) / 2 + cells.integral([(Q(1), one, 1, (H, 2))]) / rt)
    psi_sq = [(Q(1), _pmul(PSI_FACTOR, PSI_FACTOR), 2, (H, 2, d_F))]
    out["H2"] = cells.integral(psi_sq) / 2 + cells.integral(_derivative_groups(psi_sq)) / rt + H.sup(2) * R_F**2 / rt
    factor = poisson_factor(start)
    out["H3"] = (poisson_strip_integral_excess(H) + poisson_strip_integral([(Q(1), PSI_FACTOR, 1, 1)], H) / N) * factor
    # k = 1 local term: n^2 times the error at a grid point is at most W(z_m)
    ebar2 = _padd(_padd(_pabs(EXPANSION_P2), [Q(1, 18)]), _pscale(e3, 1 / N))
    M_E = _padd(_padd(_pscale(e3, 2), _pscale(_pmul(p_abs, ebar2), 2)), _pscale(_pmul(ebar2, ebar2), 1 / N))
    X2 = _pmul(CHI_FACTOR, CHI_FACTOR)
    U3, U4 = (H, 3), (H, 4, d_mu)
    fine = [(Q(2), _pmul(EXPANSION_P, CHI_FACTOR), 3, U3), (R_mu, one, 2, U3), (Q(1), X2, 4, U4),
            (Q(2), EXPANSION_P2, 2, (H, 2)), (Q(1), _pmul(EXPANSION_P, EXPANSION_P), 2, (H, 2)), (Q(1, 9), one, 2, (H, 2))]
    crude = [(2 * R_mu / N, _pabs(EXPANSION_P), 2, U3), (2 / N, _pabs(_pmul(EXPANSION_P, X2)), 4, U4),
             (R_mu**2 / N**2, one, 2, U4), (2 * R_mu**2 / N**3, _pabs(EXPANSION_P), 2, U4), (1 / N, M_E, 2, (H, 2))]
    for c, E in ((Q(2), _pabs(EXPANSION_P2)), (Q(1), _pmul(EXPANSION_P, EXPANSION_P)), (Q(1, 9), one), (1 / N, M_E)):
        crude += [(c / N, _pmul(E, _pabs(CHI_FACTOR)), 3, U3), (c * R_mu / N**2, E, 2, U3),
                  (c / N**2, _pmul(E, X2), 4, U4), (c * R_mu**2 / N**4, E, 2, U4)]
    fine = [g for g in fine if g[3][1] <= K]
    crude = [g for g in crude if g[3][1] <= K]
    out["L1"] = (cells.integral(fine) / 2 + cells.integral(_derivative_groups(fine)) / rt
                 + _moment_bound(crude) / 2 + _moment_bound([(c, _pabs(P), a, U) for c, P, a, U in _derivative_groups(crude)]) / rt)
    two_p = _pscale(EXPANSION_P, 2)
    J3 = poisson_strip_integral([(Q(1), one, 2, 2)], H)
    J4 = poisson_strip_integral([(Q(1), two_p, 2, 2), (Q(1), CHI_FACTOR, 3, 3)], H)
    J5 = poisson_strip_integral([(Q(1), one, 4, 4)], H) if K >= 4 else Q(0)
    out["L2"] = (J3 + J4 / N + J5 / (12 * N)) * factor
    # k = 2: per point (1/(12 n^2)) phi^4 [4 Gamma^3 (|p| + ebar2/N) |H''''| + |H^(5)| (phi |chi| + R_mu/N)]
    fine2, crude2 = [], []
    if K >= 4:
        fine2 = [(4 * Gam**3, EXPANSION_P, 4, U4)]
        crude2 = [(4 * Gam**3 / N, ebar2, 4, U4)]
    if K >= 5:
        U5 = (H, 5, d_mu)
        fine2 += [(Q(1), CHI_FACTOR, 5, U5), (R_mu / N, one, 4, U5)]
    out["L3"] = (cells.integral(fine2) / 2 + cells.integral(_derivative_groups(fine2)) / rt
                 + _moment_bound(crude2) / 2
                 + _moment_bound([(c, _pabs(P), a, U) for c, P, a, U in _derivative_groups(crude2)]) / rt) / 12 if fine2 else Q(0)
    qmax2 = 2 / (PI_LOWER * (N - Q(1, 2)))
    L5 = Q(0)
    for k in range(3, K // 2 + 1):
        Wk = [(Gam**4, one, 4, (H, 2 * k, d_mu))]
        L5 += (16 * N / (4**k * factorial(2 * k)) * qmax2**(k - 2)
               * (cells.integral(Wk) + 2 * cells.integral(_derivative_groups(Wk)) / rt))
    out["L5"] = L5
    out["tails"] = _margin_tails(H, start, base)
    out["C_exact"] = sum((out[k] for k in ("H1", "H2", "H3", "L1", "L2", "L3", "L5", "tails")), Q(0))
    out["C"] = ceil_decimal(out["C_exact"])
    return out


def _margin_tails(H: ExcessPolynomial, start: int, base: dict) -> Q:
    """All pieces outside the expansion regions, ``n^{3/2}`` scale, bounded at ``n = start`` (each is ``c n^d A^k
    e^{-a A^2/2}`` with ``A >= sqrt(n)/2 - 5/sqrt(n)``, decreasing for ``n >= start``).

    (i) ``m < n`` with ``|b_m| > beta``: ``|H(F)| <= lambda0 e^{-beta^2}``, at most ``n`` terms.  (ii) Grid tails of the
    CDF-sum approximants ``lambda0 (sqrt(pi/2) phi)^2`` and ``lambda1 sqrt(pi/2) phi^2 |psi factor| / n``.  (iii) Local
    terms with ``|z_m| > gamma``: ``(n/4)|H''| q^2 + (n/192)|H''''| q^4 + sum_k ...`` is at most
    ``[(n/4)|H''| q_max + (n/192)|H''''| q_max^3 + 2n sum_k |H^(2k)| q_max^(2k-1)/(4^k (2k)!)] q_m`` and
    ``sum_tail q_m <= 2 e^{-gamma^2/2}``.  (iv) Grid tails of the local approximants.
    """

    N, rt = Q(start), Q(isqrt(start))
    beta = rt / 2 - 4 / rt
    gamma = rt / 2 - 5 / rt
    K = H.K
    cg = 1 / (2 * INV_SQRT_2PI_LOWER)
    qmax = _sqrt_hi(2 / (PI_LOWER * (N - Q(1, 2))))
    n32 = N * rt

    def grid_tail(k, a, A):
        # sum over grid points beyond A (both sides) of |y|^k phi^a <= 2 [A^k phi(A)^a + (sqrt n/2) int_A^oo]
        return 2 * (gaussian_tail_sup_bound(k, a, A) + rt / 2 * gaussian_tail_bound(k, a, A))

    out = n32 * N * H.lambda0 * exp_neg_bounds(beta * beta)[1]
    out += n32 * (H.lambda0 * cg * cg * grid_tail(0, 2, beta)
                  + H.lambda1 * cg / N * sum((abs(c) * grid_tail(k, 2, beta) for k, c in enumerate(PSI_FACTOR) if c), Q(0)))
    local = N / 4 * H.sup(2) * qmax + N / 192 * H.sup(4) * qmax**3
    for k in range(3, K // 2 + 1):
        local += 2 * N * H.sup(2 * k) * qmax**(2 * k - 1) / (4**k * factorial(2 * k))
    out += n32 * local * 2 * exp_neg_bounds(gamma * gamma / 2)[1]
    approx = H.sup(2) * grid_tail(0, 2, gamma)
    approx += sum((H.sup(2) * 2 * abs(c) * grid_tail(k, 2, gamma) for k, c in enumerate(EXPANSION_P) if c), Q(0)) / N
    approx += sum((H.sup(3) * abs(c) * grid_tail(k, 3, gamma) for k, c in enumerate(CHI_FACTOR) if c), Q(0)) / N
    approx += H.sup(4) * grid_tail(0, 4, gamma) / (12 * N)
    out += n32 * approx
    return out


def second_order_delta(candidates: int) -> float:
    """``delta_K = (1/2)[int H'(Phi) psi + int phi^2 (2p H''(Phi) + H'''(Phi) chi) + (1/12) int phi^4 H''''(Phi)]`` by the
    module's Simpson rule (floats); it should equal ``c(K) E[M_K]/2 = (E[M_K^3] - (5/2) E[M_K])/12``.  Not used in the proof."""

    H = ExcessPolynomial(candidates)
    x, cdf, pdf = _gaussian_grid()
    h = float(x[1] - x[0])

    def derivative(j):
        if j > H.K:
            return np.zeros_like(x)
        (c0, c1), c = H.linear_part(j)
        m = H.K - j
        return float(c0) + float(c1) * cdf + float(c) * (cdf**m + (-1)**j * (1 - cdf)**m)

    p = -0.25 + x**2 / 2 - x**4 / 12
    psi = pdf * (x**3 - x) / 12
    chi = pdf * (x**3 - 7 * x) / 12
    integrand = derivative(1) * psi + pdf**2 * (2 * p * derivative(2) + derivative(3) * chi) + pdf**4 * derivative(4) / 12
    return 0.5 * _simpson(integrand, h)


def effective_threshold_search(candidates: int, constant: Q, start: int = EFFECTIVE_START,
                               limit: int = EFFECTIVE_SCAN_LIMIT) -> dict[str, object]:
    """Smallest ``N0`` in ``[start, limit]`` with ``N0^3 D_{N0}^2 > 4 C^2`` and ``D_{N0} > 0``, scanning upward exactly.

    Every scanned ``n`` also checks ``D_n > 0`` (so the scan is an exact sweep of ``rho_n > 1`` on ``[start, N0]``).
    With ``|sqrt(n) D_n - delta| <= C/n`` for ``n >= start``: ``delta >= sqrt(N0) D_{N0} - C/N0 > C/N0``, hence
    ``sqrt(n) D_n >= delta - C/n > 0`` for every ``n >= N0``.
    """

    _candidates(candidates)
    constant = Q(constant)
    if constant <= 0:
        raise ValueError("constant must be positive")
    _items(start)
    _items(limit)
    K = candidates
    now = _centered_max_numerator(start, K)
    for n in range(start, limit + 1):
        nxt = _centered_max_numerator(n + 1, K)
        d = Q(2 * n * nxt - (2 * n + 1) * 2**K * now, 2**((n + 1) * K))
        if d <= 0:
            return {"threshold": None, "first_nonpositive": n, "scanned_to": n}
        if Q(n)**3 * d * d > 4 * constant * constant:
            return {"threshold": n, "first_nonpositive": None, "scanned_to": n,
                    "scaled_margin": float(d) * n**1.5 / (2 * float(constant))}
        now = nxt
    return {"threshold": None, "first_nonpositive": None, "scanned_to": limit}


def certify_threshold(candidates: int, constant: Q, items: int) -> bool:
    """One exact evaluation: ``n^3 D_n^2 > 4 C^2`` and ``D_n > 0`` at ``n = items`` (proves ``D_n > 0`` for all larger ``n``,
    leaving ``[start, items)`` to an exact sweep)."""

    d = margin_deficit(items, candidates)
    return d > 0 and Q(items)**3 * d * d > 4 * Q(constant)**2


def exact_rho_sweep(candidates: int, max_items: int) -> dict[str, object]:
    """``D_n(K) > 0`` (i.e. ``rho_n > 1``) for ``n = 1..max_items``, integer arithmetic, each ``M_n`` computed once."""

    _candidates(candidates)
    _items(max_items)
    K = candidates
    previous = _centered_max_numerator(1, K)
    failures, worst, worst_at = [], None, None
    for n in range(1, max_items + 1):
        nxt = _centered_max_numerator(n + 1, K)
        num = 2 * n * nxt - (2 * n + 1) * 2**K * previous       # 2^{(n+1)K} D_n
        if num <= 0:
            failures.append(n)
        rho = Q(2 * n * (nxt - 2**K * previous), 2**K * previous)
        if worst is None or rho < worst:
            worst, worst_at = rho, n
        previous = nxt
    return {"candidates": K, "max_items": max_items, "all_positive": not failures,
            "first_failure": failures[0] if failures else None, "min_rho": float(worst), "min_rho_at": worst_at}


def _square_root_of_items(items: int) -> int:
    _items(items)
    root = isqrt(items)
    if root * root != items:
        raise ValueError("items must be a perfect square (rational grid points)")
    return root


def cdf_remainder_check(items: int) -> Q:
    """``max n^2 |F_n(m) - Phi(b_m) - psi(b_m)/n|`` over ``|b_m| <= sqrt(n)/2 - 4/sqrt(n)``, an exact upper bound from the
    rational enclosures (perfect-square ``n``, so ``b_m`` is rational).  Lemma F says it is at most ``R_F`` for ``n >= 400``."""

    root = _square_root_of_items(items)
    beta = Q(root, 2) - Q(4, root)
    worst, cdf = Q(0), _binomial_cdf_integers(items)
    for m in range(items):
        b = Q(2 * m + 1 - items, root)
        if abs(b) > beta:
            continue
        F = Q(cdf[m], 2**items)
        (c_lo, c_hi), (d_lo, d_hi) = normal_cdf_bounds(b), normal_density_bounds(b)
        y = _peval(PSI_FACTOR, b)
        p_lo, p_hi = sorted((d_lo * y, d_hi * y))
        worst = max(worst, items**2 * max(abs(F - c_lo - p_lo / items), abs(F - c_hi - p_hi / items)))
    return worst


def midpoint_remainder_check(items: int) -> Q:
    """``max n^2 |mu_m - Phi(z_m) - chi(z_m)/n|`` over ``|z_m| <= sqrt(n)/2 - 5/sqrt(n)`` (Lemma M: at most ``R_mu``)."""

    root = _square_root_of_items(items)
    gamma = Q(root, 2) - Q(5, root)
    worst, cdf, previous = Q(0), _binomial_cdf_integers(items), 0
    for m in range(items + 1):
        z = Q(2 * m - items, root)
        if abs(z) <= gamma:
            mu = Q(previous + cdf[m], 2 * 2**items)
            (c_lo, c_hi), (d_lo, d_hi) = normal_cdf_bounds(z), normal_density_bounds(z)
            y = _peval(CHI_FACTOR, z)
            x_lo, x_hi = sorted((d_lo * y, d_hi * y))
            worst = max(worst, items**2 * max(abs(mu - c_lo - x_lo / items), abs(mu - c_hi - x_hi / items)))
        previous = cdf[m]
    return worst


def local_remainder_check(items: int, start: int = EFFECTIVE_START) -> Q:
    """``max n^2 (|e_j| - (|p_2| + 1/18)/n^2 - e_3/n^3)`` over ``|z_j| <= sqrt(n)/2``; Lemma L says it is ``<= 0``."""

    root = _square_root_of_items(items)
    if items < start:
        raise ValueError("Lemma L is stated for items >= start")
    e3 = local_expansion_majorants(start)["e3"]
    worst = None
    for j in range(items + 1):
        z = Q(2 * j - items, root)
        if abs(z) > Q(root, 2):
            continue
        q = Q(comb(items, j), 2**items)
        d_lo, d_hi = normal_density_bounds(z)
        step = Q(2, root)
        p = _peval(EXPANSION_P, z)
        e_far = max(abs(q / (step * d_hi) - 1 - p / items), abs(q / (step * d_lo) - 1 - p / items))
        bound = (abs(_peval(EXPANSION_P2, z)) + Q(1, 18)) / items**2 + _peval(e3, z) / items**3
        excess = items**2 * (e_far - bound)
        worst = excess if worst is None else max(worst, excess)
    return worst


# --- fixtures ------------------------------------------------------------------------

def tie_rule_fixture() -> dict[str, object]:
    """A four-record space with a tie at the middle score; both rules, three closed forms, brute force."""

    p0 = {"a": Q(1, 2), "b": Q(1, 4), "c": Q(1, 8), "d": Q(1, 8)}
    score = {"a": Q(0), "b": Q(1), "c": Q(1), "d": Q(2)}
    laws, agree, brute, kl_equal = {}, True, True, True
    q = score_law(p0, score)
    for candidates in (1, 2, 3, 4):
        first = selected_record_law(p0, score, candidates, "first_index")
        uniform = selected_record_law(p0, score, candidates, "uniform")
        conditioned = conditioned_on_max_law(p0, score, candidates)
        agree &= first == uniform == conditioned
        if candidates <= 3:
            brute &= (brute_force_selected_law(p0, score, candidates, "first_index") == first
                      and brute_force_selected_law(p0, score, candidates, "uniform") == uniform)
        kl_records = kl_divergence(uniform, p0)
        kl_scores = kl_divergence(max_law(q, candidates), q)
        kl_equal &= abs(kl_records - kl_scores) <= LOG_TOLERANCE
        laws[f"K={candidates}"] = {"law": uniform, "kl": kl_records, "radius": beirami_radius(candidates)}
    return {"p0": p0, "score": score, "laws": laws, "closed_forms_agree": agree,
            "brute_force_agrees": brute, "kl_on_records_equals_kl_of_max_law": kl_equal}


def record_fixture() -> dict[str, object]:
    """``KL`` computed on the records ``{0,1}^n`` equals ``kl_max_law`` on small null cells."""

    cells = {}
    for items in (1, 2, 3, 4, 5):
        for candidates in (2, 3):
            for p in (Q(1, 2), Q(1, 4)):
                p0, score = binomial_records(items, p)
                law = selected_record_law(p0, score, candidates)
                on_records = kl_divergence(law, p0)
                on_scores = kl_max_law(items, candidates, p)
                gap = sum((mass * score[record] for record, mass in law.items()), Q(0)) - p
                cells[f"n={items},K={candidates},p={p}"] = {
                    "kl_on_records": on_records, "kl_on_scores": on_scores,
                    "equal": abs(on_records - on_scores) <= LOG_TOLERANCE,
                    "gap_matches_selection_inflation": gap == selection_gap(items, candidates, p)}
    return cells


def jittered_selection_fixture(levels_list: tuple[int, ...] = (1, 2, 4, 8, 16)) -> dict[str, object]:
    """A finite stand-in for Theorem B's jitter: each record carries one of ``L`` equally
    likely offsets inside the smallest score gap.  The jittered selection's marginal on
    records is ``pi_K`` exactly, its KL dominates the discrete KL (data processing), and
    it rises toward the radius as ``L`` grows."""

    base = tie_rule_fixture()
    p0, score, candidates = base["p0"], base["score"], 3
    discrete = selected_record_law(p0, score, candidates)
    discrete_kl = kl_divergence(discrete, p0)
    distinct = sorted(set(score.values()))
    gap = min(b - a for a, b in zip(distinct, distinct[1:]))
    rows, marginal_ok, dominated, previous, rising = {}, True, True, -1.0, True
    for levels in levels_list:
        joint_p0 = {(record, level): mass / levels for record, mass in p0.items() for level in range(levels)}
        joint_score = {(record, level): score[record] + gap * Q(level + 1, 2 * (levels + 1))
                       for record, level in joint_p0}
        joint = selected_record_law(joint_p0, joint_score, candidates)
        marginal = {record: Q(0) for record in p0}
        for (record, _), mass in joint.items():
            marginal[record] += mass
        joint_kl = kl_divergence(joint, joint_p0)
        marginal_ok &= marginal == discrete
        dominated &= joint_kl >= discrete_kl - LOG_TOLERANCE
        rising &= joint_kl > previous
        previous = joint_kl
        rows[f"levels={levels}"] = {"joint_kl": joint_kl, "marginal_kl": discrete_kl}
    return {"candidates": candidates, "rows": rows, "radius": beirami_radius(candidates),
            "marginal_is_pi_K": marginal_ok, "joint_kl_dominates_discrete_kl": dominated,
            "joint_kl_rises_with_levels": rising,
            "joint_kl_below_radius": all(r["joint_kl"] < beirami_radius(candidates) for r in rows.values())}


def grid_fixture() -> dict[str, dict[str, object]]:
    """Theorems B and C on ``n in GRID_ITEMS``, ``K in GRID_CANDIDATES``, ``p in GRID_P``."""

    cells = {}
    for items in GRID_ITEMS:
        for candidates in GRID_CANDIDATES:
            for p in GRID_P:
                gap = selection_gap(items, candidates, p)
                kl = kl_max_law(items, candidates, p)
                radius = beirami_radius(candidates)
                exact_bound = dv_bound(items, p, kl)
                radius_bound = dv_bound(items, p, radius)
                hoeffding_bound = dv_bound(items, p, radius, "hoeffding")
                cells[f"n={items},K={candidates},p={p}"] = {
                    "items": items, "candidates": candidates, "p": p,
                    "gap": gap, "gap_from_max_law_equal": gap == gap_from_max_law(items, candidates, p),
                    "kl": kl, "radius": radius, "dv_at_exact_kl": exact_bound,
                    "dv_at_radius": radius_bound, "dv_hoeffding_at_radius": hoeffding_bound,
                    "ratio_exact": float(gap) / exact_bound, "ratio_radius": float(gap) / radius_bound,
                    "c_K": gaussian_ratio_limit(candidates)}
    return cells


def proxy_fixture() -> dict[str, object]:
    rows = {}
    for p in GRID_P:
        v = kearns_saul_proxy(p)
        rows[f"p={p}"] = {"kearns_saul": v, "variance": float(p * (1 - p)), "hoeffding": hoeffding_proxy(),
                          "grid_violation_kearns_saul": subgaussian_violation(p, "kearns_saul"),
                          "grid_violation_hoeffding": subgaussian_violation(p, "hoeffding")}
    return rows


def supremum_fixture() -> dict[str, object]:
    """``n = 1``: the gap equals the KL-ball supremum.  ``n >= 2``: strictly below it (finite)."""

    equality, strict = {}, {}
    for candidates in GRID_CANDIDATES:
        for p in GRID_P:
            gap = selection_gap(1, candidates, p)
            sup = kl_ball_supremum(1, p, kl_max_law(1, candidates, p)) - float(p)
            equality[f"K={candidates},p={p}"] = {"gap": gap, "kl_ball_sup": sup,
                                                 "equal": abs(float(gap) - sup) <= SUPREMUM_TOLERANCE}
    for items in (2, 4, 8):
        for candidates in (2, 5):
            for p in GRID_P:
                gap = float(selection_gap(items, candidates, p))
                kl = kl_max_law(items, candidates, p)
                sup = kl_ball_supremum(items, p, kl) - float(p)
                strict[f"n={items},K={candidates},p={p}"] = {
                    "gap": gap, "kl_ball_sup": sup, "dv_at_exact_kl": dv_bound(items, p, kl),
                    "chain_strict": gap < sup - SUPREMUM_TOLERANCE and sup < dv_bound(items, p, kl) - SUPREMUM_TOLERANCE}
    return {"n_equals_1": equality, "n_at_least_2": strict}


def gaussian_fixture() -> dict[str, object]:
    rows = {}
    for candidates in GAUSSIAN_CANDIDATES:
        density = gaussian_max_expectation(candidates, "density")
        tail = gaussian_max_expectation(candidates, "tail")
        rows[f"K={candidates}"] = {"expected_max": density, "expected_max_tail_form": tail,
                                   "quadratures_agree": abs(density - tail) <= QUADRATURE_TOLERANCE,
                                   "sqrt_2_radius": sqrt(2 * beirami_radius(candidates)),
                                   "c_K": gaussian_ratio_limit(candidates)}
    closed = {"K=2": 1 / sqrt(pi), "K=3": 3 / (2 * sqrt(pi))}
    return {"rows": rows, "closed_forms": closed,
            "closed_forms_match": all(abs(rows[k]["expected_max"] - v) <= QUADRATURE_TOLERANCE
                                      for k, v in closed.items())}


def limit_fixture() -> dict[str, object]:
    """``sqrt(n) gamma(n,K,1/2) -> E[max]/2`` and the ratio rises toward ``c_K`` (finite)."""

    rows = {}
    for candidates in (2, 5):
        target = gaussian_max_expectation(candidates) / 2
        c = gaussian_ratio_limit(candidates)
        previous_error, previous_ratio, shrinking, rising, below = None, -1.0, True, True, True
        for items in (64, 256, 1024):
            scaled = sqrt(items) * float(selection_gap(items, candidates, Q(1, 2)))
            ratio = gap_to_bound_ratio(items, candidates, Q(1, 2))
            error = abs(scaled - target)
            shrinking &= previous_error is None or error < previous_error
            rising &= ratio > previous_ratio
            below &= ratio < c
            previous_error, previous_ratio = error, ratio
            rows[f"n={items},K={candidates}"] = {"sqrt_n_gap": scaled, "gaussian_target": target,
                                                "ratio_radius": ratio, "c_K": c}
        rows[f"K={candidates}"] = {"error_shrinks": shrinking, "ratio_rises": rising, "ratio_below_c_K": below}
    return rows


def uniform_support_fixture() -> dict[str, object]:
    rows = {}
    for candidates in (2, 3, 5):
        radius = beirami_radius(candidates)
        previous, shrinking = None, True
        for atoms in (10, 100, 1000):
            deficit = radius - uniform_distinct_scores_kl(atoms, candidates)
            shrinking &= deficit > 0 and (previous is None or deficit < previous)
            previous = deficit
            rows[f"N={atoms},K={candidates}"] = {"deficit": deficit}
        rows[f"K={candidates}"] = {"deficit_positive_and_shrinking": shrinking, "deficit_at_1000": previous}
    return rows


def mad_fixture(max_trials: int = 60) -> dict[str, object]:
    """De Moivre's mean absolute deviation against enumeration for ``N <= max_trials``."""

    closed_matches = all(symmetric_binomial_mad(trials) == symmetric_binomial_mad_closed_form(trials)
                         for trials in range(1, max_trials + 1))
    even_form = all(symmetric_binomial_mad_closed_form(2 * n) == Q(n * comb(2 * n, n), 4**n)
                    for n in range(1, max_trials // 2 + 1))
    return {"max_trials": max_trials, "closed_form_matches_enumeration": closed_matches,
            "even_trials_form_n_C_2n_n_over_4_to_n": even_form,
            "values": {f"N={trials}": symmetric_binomial_mad_closed_form(trials) for trials in (1, 2, 3, 4, 10)}}


def pair_theorem_fixture(max_items: int = MONOTONE_ITEMS) -> dict[str, object]:
    """``K = 2``: the absolute-difference reduction, the closed form, the step identity, the limit."""

    reduction = all(centered_max(n, 2) == pair_gap_by_enumeration(n) == symmetric_binomial_mad(2 * n) / 2
                    for n in range(1, 31))
    closed = all(scaled_gap_squared(n, 2) == pair_scaled_gap_squared(n) for n in range(1, max_items + 1))
    steps = all(scaled_gap_squared(n + 1, 2) / scaled_gap_squared(n, 2) == pair_step_ratio(n)
                == 1 + Q(1, 4 * n * (n + 1)) > 1 for n in range(1, max_items + 1))
    last = scaled_gap_squared(max_items, 2)
    deficit = 4 * max_items * (1 - 4 * pi * float(last))
    return {"max_items": max_items, "reduction_to_mean_absolute_difference": reduction,
            "closed_form_matches": closed, "step_identity_and_strict_increase": steps,
            "limit_squared": 1 / (4 * pi), "scaled_gap_squared_at_max_items": float(last),
            "below_limit": float(last) < 1 / (4 * pi),
            "scaled_deficit_4n_times_relative_gap": deficit,
            "scaled_deficit_near_one": 0.99 < deficit < 1.0}


def odd_candidates_fixture(max_items: int = MONOTONE_ITEMS) -> dict[str, object]:
    """Order-statistic recurrence for symmetric laws: ``M_n(3) = (3/2) M_n(2)``, ``M_n(5) = (5/2)(M_n(4) - M_n(2))``.

    Deleting one of ``n`` draws uniformly gives ``E Y_{(r:n-1)} = ((n-r)/n) E Y_{(r:n)} + (r/n) E Y_{(r+1:n)}``;
    the median of an odd symmetric sample has mean zero.  ``n = 3, r = 2`` gives the triple,
    ``n = 5, r = 3, 4`` and ``n = 4, r = 3`` the quintuple.
    """

    triple = all(centered_max(n, 3) == Q(3, 2) * centered_max(n, 2) for n in range(1, max_items + 1))
    quintuple = all(centered_max(n, 5) == Q(5, 2) * (centered_max(n, 4) - centered_max(n, 2))
                    for n in range(1, max_items + 1))
    return {"max_items": max_items, "triple_is_three_halves_of_pair": triple,
            "quintuple_is_five_halves_of_quadruple_minus_pair": quintuple,
            "triple_limit": 3 / (4 * sqrt(pi)), "triple_limit_matches_quadrature":
            abs(gaussian_max_expectation(3) / 2 - 3 / (4 * sqrt(pi))) <= QUADRATURE_TOLERANCE}


def tie_increment_fixture() -> dict[str, object]:
    """``E[2^{-N}]`` closed form against enumeration; ``M_{n+1} - M_n = 1/2 - E[2^{-N}]``; the ``K = 2`` value."""

    enumeration = all(tie_count_moment(n, k) == brute_force_tie_count_moment(n, k)
                      for n, k in ((1, 2), (2, 2), (3, 2), (4, 2), (1, 3), (2, 3), (3, 3), (4, 3), (2, 4), (3, 4)))
    identity = all(centered_max(n + 1, k) - centered_max(n, k) == centered_max_increment(n, k)
                   for n in range(1, 31) for k in (2, 3, 4, 5, 10))
    pair = all(centered_max_increment(n, 2) == Q(comb(2 * n, n), 4**(n + 1)) == centered_max(n, 2) / (2 * n)
               for n in range(1, 31))
    return {"closed_form_matches_enumeration": enumeration, "increment_identity_n_le_30": identity,
            "pair_increment_is_tie_probability_over_four": pair}


def monotonicity_fixture() -> dict[str, object]:
    """D.5 sweeps: ``MONOTONE_CANDIDATES`` to ``n = 200`` in full, ``SWEEP_CANDIDATES`` to ``n = 100``
    as booleans, ``K = 1000`` to ``n = 40``; ``scaled_gap_squared`` against ``selection_inflation``."""

    full = {f"K={k}": monotonicity_sweep(k) for k in MONOTONE_CANDIDATES}
    broad = {}
    for k in SWEEP_CANDIDATES:
        row = monotonicity_sweep(k, SWEEP_ITEMS)
        broad[f"K={k}"] = {key: row[key] for key in ("monotone", "rho_at_least_one", "rho_equals_one",
                                                     "min_step_ratio", "min_step_ratio_at", "min_margin",
                                                     "min_margin_at", "below_gaussian_limit")}
    large = monotonicity_sweep(LARGE_CANDIDATES, LARGE_ITEMS)
    cross = all(scaled_gap_squared(n, k) == n * selection_gap(n, k, Q(1, 2))**2
                for n in range(1, 41) for k in (2,) + MONOTONE_CANDIDATES)
    return {"full": full, "broad": broad, "large": large, "matches_selection_inflation_n_le_40": cross}


def convex_order_fixture(max_pairs: int = 100, max_items: int = 60) -> dict[str, object]:
    """``Z_n <=_cx Z_{n+1}`` fails at every step: exactly via ``E|Z|`` at odd-to-even steps, by a
    stop-loss function (floats, margin ``STOP_LOSS_MARGIN``) at every step ``n <= max_items``."""

    odd_to_even = all(standardized_absolute_moment_squared(2 * k + 2) < standardized_absolute_moment_squared(2 * k + 1)
                      and standardized_absolute_moment_squared(2 * k + 2) / standardized_absolute_moment_squared(2 * k + 1)
                      == Q(2 * k + 1, 2 * k + 2) for k in range(0, max_pairs))
    even_to_odd_rises = all(standardized_absolute_moment_squared(2 * k + 1) > standardized_absolute_moment_squared(2 * k)
                            for k in range(1, max_pairs))
    excess = {n: stop_loss_excess(n) for n in range(1, max_items + 1)}
    return {"absolute_moment_falls_odd_to_even_exact": odd_to_even,
            "absolute_moment_rises_even_to_odd_exact": even_to_odd_rises,
            "absolute_moment_squared": {f"n={n}": standardized_absolute_moment_squared(n) for n in range(1, 7)},
            "stop_loss_refutes_every_step": all(v > STOP_LOSS_MARGIN for v in excess.values()),
            "stop_loss_min_excess": min(excess.values()), "stop_loss_min_excess_at": min(excess, key=excess.get),
            "stop_loss_first_values": {f"n={n}": excess[n] for n in range(1, 7)}}


def exact_kl_ratio_fixture(max_items: int = MONOTONE_ITEMS) -> dict[str, object]:
    """The exact-KL ratio at ``p = 1/2`` along ``n`` for ``K = 2, 5`` (finite)."""

    rows = {}
    for candidates, start in ((2, 1), (5, 2)):
        path = exact_kl_ratio_along_items(candidates, tuple(range(1, max_items + 1)))
        values = [path[f"n={n}"]["ratio_exact"] for n in range(1, max_items + 1)]
        c = gaussian_ratio_limit(candidates)
        rows[f"K={candidates}"] = {
            "c_K": c, "decreasing_from": start,
            "strictly_decreasing_from_start": all(a > b for a, b in zip(values[start - 1:], values[start:])),
            "above_c_K_from_start": all(v > c for v in values[start - 1:]), "max_value": max(values),
            "max_value_at": values.index(max(values)) + 1, "value_at_max_items": values[-1],
            "within_5e-4_of_c_K_at_max_items": values[-1] - c < 5e-4,
            "kl_over_radius_at_max_items": path[f"n={max_items}"]["kl_over_radius"],
            "path": {f"n={n}": path[f"n={n}"] for n in (1, 2, 3, 4, 8, 16, 64, max_items)}}
    return rows


def profile_fixture(max_items: int = 60) -> dict[str, object]:
    """The overlap-profile polynomial, the pair-of-pairs identities and the profile increments (version 0.3)."""

    polynomial = all(centered_max_from_profile(n, k) == centered_max(n, k)
                     for n in range(1, 41) for k in (1, 2, 3, 4, 5, 6, 9, 12))
    named = (tie_polynomial(2) == [0, 1] and tie_polynomial(3) == [0, Q(3, 2)] and tie_polynomial(4) == [0, 2, -1]
             and tie_polynomial(5) == [0, Q(5, 2), Q(-5, 2)])
    pairs, mad_double_sum, increments = True, True, True
    for n in range(1, max_items + 1):
        s1, s2 = profile_power_sums(n)
        mad = mean_absolute_difference(max_of_two_law(n))
        pairs &= s1 == centered_max(n, 2) and 2 * s1 - s2 == centered_max(n, 4) and centered_max(n, 5) == Q(5, 2) * (s1 - s2)
        mad_double_sum &= mad == 2 * (s1 - s2) and centered_max(n, 4) == centered_max(n, 2) + mad / 2
        increments &= (second_profile_increment(n) == profile_power_sums(n + 1)[1] - s2
                       and quadruple_increment(n) == centered_max_increment(n, 4))
    enumeration = all(order_statistic_mean_by_enumeration(n, 4, 3) == 3 * profile_power_sums(n)[1]
                      and order_statistic_mean_by_enumeration(n, 4, 4) == centered_max(n, 4)
                      and order_statistic_mean_by_enumeration(n, 2, 2) == centered_max(n, 2) for n in (1, 2, 3, 4))
    return {"max_items": max_items, "polynomial_matches_centered_max_n_le_40": polynomial, "named_polynomials": named,
            "pair_of_pairs_identities": pairs, "mean_absolute_difference_is_two_S1_minus_S2": mad_double_sum,
            "second_largest_of_four_is_three_S2_by_enumeration_n_le_4": enumeration,
            "profile_increment_identities": increments,
            "values": {f"n={n}": {"S1": profile_power_sums(n)[0], "S2": profile_power_sums(n)[1],
                                  "L": local_sums(n)} for n in (1, 2, 3, 4)}}


def tie_mass_fixture(max_items: int = 60) -> dict[str, object]:
    """Route R2: the exact tie-count law, its weighted sum, and the crude bound's deficit (version 0.3)."""

    def brute_law(n: int, k: int) -> dict[int, Q]:
        masses = [Q(comb(n, j), 2**n) for j in range(n + 1)]
        law = {j: Q(0) for j in range(1, k + 1)}
        for counts in product(range(n + 1), repeat=k):
            weight = Q(1)
            for c in counts:
                weight *= masses[c]
            law[counts.count(max(counts))] += weight
        return law

    enumeration = all(tie_count_law(n, k) == brute_law(n, k) for n, k in ((1, 2), (2, 3), (3, 3), (2, 4), (3, 4), (2, 5)))
    weighted = all(sum((Q(1, 2) - Q(1, 2**j)) * p for j, p in tie_count_law(n, k).items()) == centered_max_increment(n, k)
                   and sum(tie_count_law(n, k).values()) == 1
                   and sum(p for j, p in tie_count_law(n, k).items() if j >= 2) == tie_mass(n, k)
                   for n in range(1, 31) for k in (2, 3, 4, 5, 8))
    pair_exact, triple, quadruple = True, True, True
    for n in range(1, max_items + 1):
        cubes = sum((Q(comb(n, m), 2**n)**3 for m in range(n + 1)), Q(0))
        pair_exact &= crude_tie_bound_deficit(n, 2) == 0
        triple &= crude_tie_bound_deficit(n, 3) == -Q(n, 2) * cubes < 0
        quadruple &= crude_tie_bound_deficit(n, 4) < 0
    return {"max_items": max_items, "tie_count_law_matches_enumeration": enumeration,
            "weighted_tie_law_is_increment_n_le_30": weighted, "crude_bound_exact_for_pairs": pair_exact,
            "crude_bound_fails_for_triples_by_half_n_sum_q_cubed": triple, "crude_bound_fails_for_quadruples": quadruple,
            "deficits": {f"n={n},K={k}": crude_tie_bound_deficit(n, k) for n in (1, 2, 4, 8) for k in (3, 4)}}


def step_ratio_fixture() -> dict[str, object]:
    """Route R1: rational step ratios exist for ``K = 2, 3`` (degree 1), none for ``K = 4`` or for ``E|Y - Y'|``; the recurrence."""

    ranks = {f"K={k}": rational_step_ratio_rank(lambda n, k=k: centered_max(n, k), RATIONAL_STEP_DEGREE) for k in (2, 3, 4)}
    degree_one = {f"K={k}": rational_step_ratio_rank(lambda n, k=k: centered_max(n, k), 1)["exists"] for k in (2, 3, 4)}
    mad = rational_step_ratio_rank(lambda n: mean_absolute_difference(max_of_two_law(n)), RATIONAL_STEP_DEGREE)
    recurrence = quadruple_recurrence()
    return {"rank_tests": ranks, "degree_one_exists": degree_one, "mean_absolute_difference_rank_test": mad,
            "pairs_and_triples_have_degree_one_ratio": degree_one["K=2"] and degree_one["K=3"],
            "quadruple_has_no_rational_ratio": not ranks["K=4"]["exists"] and not mad["exists"],
            "recurrence": recurrence}


def margin_limit_fixture() -> dict[str, object]:
    """``c(K)`` from the Gaussian third moment: closed forms at ``K = 2, 3``, positivity and growth beyond."""

    second, third = gaussian_max_moment(2, 3), gaussian_max_moment(3, 3)
    closed = (abs(second - 2.5 / sqrt(pi)) <= QUADRATURE_TOLERANCE and abs(third - 15 / (4 * sqrt(pi))) <= QUADRATURE_TOLERANCE
              and abs(asymptotic_margin(2)) <= QUADRATURE_TOLERANCE and abs(asymptotic_margin(3)) <= QUADRATURE_TOLERANCE)
    values = [asymptotic_margin(k) for k in range(4, 101)]
    huge = {f"K={k}": asymptotic_margin(k) for k in HUGE_SWEEP_CANDIDATES}
    return {"third_moment_K_2": second, "third_moment_K_3": third, "closed_forms_K_2_3": closed,
            "positive_K_4_to_100": all(v > 0 for v in values), "increasing_K_4_to_100": all(a < b for a, b in zip(values, values[1:])),
            "c_K": {f"K={k}": asymptotic_margin(k) for k in (4, 5, 6, 8, 10, 20, 50, 100)}, "c_K_huge": huge,
            "normalized_margin_limit": {f"K={k}": asymptotic_normalized_margin(k) for k in (4, 5, 10, 20, 100)}}


def wide_sweep_fixture() -> dict[str, object]:
    """``K = 4..100`` to ``n = 400`` and ``K in HUGE_SWEEP_CANDIDATES`` to ``n = 60``, exact comparisons."""

    wide = wide_monotonicity_sweep(WIDE_SWEEP_CANDIDATES, WIDE_SWEEP_ITEMS)
    huge = wide_monotonicity_sweep(HUGE_SWEEP_CANDIDATES, HUGE_SWEEP_ITEMS)
    rows = list(wide.values())
    global_min = min(rows, key=lambda r: r["min_margin"])
    fit = max(abs(r["richardson_minus_gaussian"]) / r["gaussian_margin_limit"] for r in rows)
    return {"wide": wide, "huge": huge,
            "wide_monotone": all(r["monotone"] for r in rows), "wide_rho_at_least_one": all(r["rho_at_least_one"] for r in rows),
            "wide_global_min_margin": global_min["min_margin"], "wide_global_min_margin_K": global_min["candidates"],
            "wide_global_min_margin_at": global_min["min_margin_at"],
            "wide_margin_at_max_items_above_gaussian_limit": all(r["margin_at_max_items"] > r["gaussian_normalized_margin_limit"]
                                                                 for r in rows),
            "wide_min_margin_at_max_items_for": [r["candidates"] for r in rows if r["min_margin_at"] == WIDE_SWEEP_ITEMS],
            "wide_max_relative_fit_residual": fit,
            "huge_monotone": all(r["monotone"] for r in huge.values()),
            "huge_rho_at_least_one": all(r["rho_at_least_one"] for r in huge.values()),
            "huge_min_margin": min(r["min_margin"] for r in huge.values())}


def excess_identity_fixture(max_items: int = 12) -> dict[str, object]:
    """Version 0.4 algebra: the excess identity for ``D_n(K)``, ``H_4 = w^2``, ``H_5 = (5/2) w^2`` (so ``D_n(5) = (5/2) D_n(4)``),
    ``K = 8`` not reducible to ``K = 2, 4``, the midpoint Euler-Maclaurin formula and the rational enclosures."""

    identity = all(margin_deficit(n, k) == margin_deficit_from_excess(n, k)
                   for n in range(1, max_items + 1) for k in (2, 3, 4, 5, 6, 7, 8, 11))
    w_squared = [Q(0), Q(0), Q(1), Q(-2), Q(1)]
    excess_named = (excess_polynomial(2) == [0] and excess_polynomial(3) == [0] and excess_polynomial(4) == w_squared
                    and excess_polynomial(5) == _pscale(w_squared, Q(5, 2)))
    five_is_four = all(margin_deficit(n, 5) == Q(5, 2) * margin_deficit(n, 4) for n in range(1, 61))
    a_fit = [[centered_max(1, 4), centered_max(1, 2)], [centered_max(2, 4), centered_max(2, 2)]]
    y_fit = [centered_max(1, 8), centered_max(2, 8)]
    det = a_fit[0][0] * a_fit[1][1] - a_fit[0][1] * a_fit[1][0]
    a = (y_fit[0] * a_fit[1][1] - a_fit[0][1] * y_fit[1]) / det
    b = (a_fit[0][0] * y_fit[1] - y_fit[0] * a_fit[1][0]) / det
    eight_not_reducible = all(centered_max(n, 8) != a * centered_max(n, 4) + b * centered_max(n, 2) for n in range(3, 9))
    samples = [Q(0), Q(1, 7), Q(-3, 4), Q(2), Q(-5, 2), Q(37, 10), Q(-6), Q(13, 2), Q(-9)]
    brackets, widths = True, []
    for t in samples:
        e_lo, e_hi = exp_neg_bounds(t * t / 2)
        c_lo, c_hi = normal_cdf_bounds(t)
        brackets &= e_lo <= exp(-float(t)**2 / 2) * (1 + 1e-12) and exp(-float(t)**2 / 2) * (1 - 1e-12) <= e_hi
        brackets &= c_lo <= 0.5 * erfc(-float(t) / sqrt(2)) + 1e-15 and 0.5 * erfc(-float(t) / sqrt(2)) - 1e-15 <= c_hi
        widths.append(float(c_hi - c_lo))
    return {"identity_n_le_max": identity, "max_items": max_items, "excess_polynomials_named": excess_named,
            "margin_five_is_five_halves_of_four_n_le_60": five_is_four,
            "M8_fit_on_n_1_2": (a, b), "M8_not_a_combination_of_M4_M2": eight_not_reducible,
            "euler_maclaurin_exact": midpoint_euler_maclaurin_check(),
            "enclosures_bracket_floats": brackets, "cdf_enclosure_widths": widths,
            "cdf_enclosures_tight_for_abs_t_le_6": all(w < 1e-12 for w, t in zip(widths, samples) if abs(t) <= 6)}


def effective_lemma_fixture(sizes: tuple[int, ...] = (400, 900), cells: GaussianCells | None = None,
                            base: dict | None = None) -> dict[str, object]:
    """Lemmas L, F, M at perfect-square ``n``: observed remainders (exact upper bounds) against the proved constants."""

    cells = cells or GaussianCells()
    base = base or cdf_and_midpoint_constants(EFFECTIVE_START, cells)
    rows, hold = {}, True
    for n in sizes:
        cdf, mid, loc = cdf_remainder_check(n), midpoint_remainder_check(n), local_remainder_check(n)
        hold &= cdf <= base["R_F"] and mid <= base["R_mu"] and loc <= 0
        rows[f"n={n}"] = {"cdf_remainder_scaled": ceil_decimal(cdf, 9), "midpoint_remainder_scaled": ceil_decimal(mid, 9),
                          "local_excess_scaled": ceil_decimal(loc, 9)}
    pieces = {key: ceil_decimal(base[key], 9) for key in ("leading_sup", "third_order", "local_second_order", "robbins_slack",
                                                         "local_third_order", "tails")}
    return {"R_F": ceil_decimal(base["R_F"]), "R_mu": ceil_decimal(base["R_mu"]), "R_F_pieces": pieces, "rows": rows,
            "lemmas_hold": hold}


def effective_theorem_fixture(candidates: tuple[int, ...] = EFFECTIVE_CANDIDATES, wide: dict | None = None,
                              scan_limit: int = EFFECTIVE_SCAN_LIMIT, cells: GaussianCells | None = None,
                              base: dict | None = None) -> dict[str, object]:
    """Per ``K``: ``C_K`` at ``N1 = 400``, the exact threshold scan from 400, and the verdict.

    The theorem for ``K`` (``rho_n(K) >= 1``, hence ``a_n(K)^2`` strictly increasing, for every ``n >= 1``) needs the
    exact sweep ``rho_n >= 1`` for ``n <= 400`` (taken from ``wide`` when given, else :func:`exact_rho_sweep`), ``D_n > 0`` on
    the scanned ``[400, N0]``, and ``N0^3 D_{N0}^2 > 4 C_K^2``.
    """

    cells = cells or GaussianCells()
    base = base or cdf_and_midpoint_constants(EFFECTIVE_START, cells)
    rows = {}
    for k in candidates:
        constant = second_order_margin_constant(k, EFFECTIVE_START, cells, base)
        search = effective_threshold_search(k, constant["C"], EFFECTIVE_START, scan_limit)
        if wide is not None and f"K={k}" in wide:
            below = wide[f"K={k}"]["rho_at_least_one"] and wide[f"K={k}"]["max_items"] >= EFFECTIVE_START
        else:
            below = exact_rho_sweep(k, EFFECTIVE_START)["all_positive"]
        rows[f"K={k}"] = {"candidates": k, "C": constant["C"],
                          "pieces": {key: float(constant[key]) for key in ("H1", "H2", "H3", "L1", "L2", "L3", "L5", "tails")},
                          "threshold": search["threshold"], "scaled_margin_at_threshold": search.get("scaled_margin"),
                          "first_nonpositive": search["first_nonpositive"], "exact_below_400": below,
                          "theorem_all_n": search["threshold"] is not None and below}
    return {"start": EFFECTIVE_START, "rows": rows, "all_theorems": all(r["theorem_all_n"] for r in rows.values()),
            "closed_at_start": [r["candidates"] for r in rows.values() if r["threshold"] == EFFECTIVE_START],
            "thresholds": {key: r["threshold"] for key, r in rows.items()}}


def effective_consistency_fixture(theorem: dict, candidates: tuple[int, ...] = (4, 10, 20),
                                  sizes: tuple[int, ...] = (400, 900)) -> dict[str, object]:
    """Floats, under the quadrature tolerance: ``delta_K`` matches ``c(K) E[M_K]/2`` and ``|sqrt(n) D_n - delta_K| <= C_K/n``."""

    deltas = {}
    for k in sorted({int(key[2:]) for key in theorem["rows"]}):
        d = second_order_delta(k)
        target = (gaussian_max_moment(k, 3) - 2.5 * gaussian_max_moment(k, 1)) / 12
        deltas[f"K={k}"] = {"delta": d, "c_K_half_E_M_K": target, "agree": abs(d - target) <= DELTA_TOLERANCE}
    rows = {}
    for k in candidates:
        C = float(theorem["rows"][f"K={k}"]["C"])
        for n in sizes:
            scaled = (float(margin_deficit(n, k)) * sqrt(n) - deltas[f"K={k}"]["delta"]) * n
            rows[f"K={k},n={n}"] = {"n_times_deviation": scaled, "C_K": C, "within": abs(scaled) <= C}
    return {"deltas": deltas, "deviations": rows,
            "deltas_agree": all(r["agree"] for r in deltas.values()),
            "deviations_within_C": all(r["within"] for r in rows.values())}


def heavy_effective_fixture(cells: GaussianCells | None = None, base: dict | None = None) -> dict[str, object]:
    """``verify(heavy=True)``: full theorems for ``HEAVY_EFFECTIVE_CANDIDATES`` (exact sweeps to 400 and scans to ``N0``) and,
    for ``HEAVY_TAIL_CANDIDATES``, ``D_n > 0`` for ``n >= N0`` with ``N0`` certified by one exact evaluation (the range
    ``(400, N0)`` is then not checked)."""

    cells = cells or GaussianCells()
    base = base or cdf_and_midpoint_constants(EFFECTIVE_START, cells)
    full = effective_theorem_fixture(HEAVY_EFFECTIVE_CANDIDATES, None, HEAVY_SCAN_LIMIT, cells, base)
    tails = {}
    for k in HEAVY_TAIL_CANDIDATES:
        constant = second_order_margin_constant(k, EFFECTIVE_START, cells, base)["C"]
        guess = max(EFFECTIVE_START, int(2 * float(constant) / second_order_delta(k)) + 1)
        tails[f"K={k}"] = {"C": constant, "N0": guess, "certified": certify_threshold(k, constant, guess),
                           "exact_below_400": exact_rho_sweep(k, EFFECTIVE_START)["all_positive"]}
    return {"full": full, "tails": tails,
            "all_passed": full["all_theorems"] and all(r["certified"] and r["exact_below_400"] for r in tails.values())}


# --- verification ----------------------------------------------------------------------

def verify(heavy: bool = False) -> dict[str, object]:
    """Run every fixture and return machine-readable checks (``heavy=True`` adds the ``K = 31..40`` scans and the
    ``K = 41..50`` certified tails, several minutes more)."""

    ties = tie_rule_fixture()
    records = record_fixture()
    jitter = jittered_selection_fixture()
    grid = grid_fixture()
    proxies = proxy_fixture()
    sup = supremum_fixture()
    gauss = gaussian_fixture()
    limit = limit_fixture()
    uniform = uniform_support_fixture()
    mad = mad_fixture()
    pair = pair_theorem_fixture()
    odd = odd_candidates_fixture()
    ties_increment = tie_increment_fixture()
    mono = monotonicity_fixture()
    convex = convex_order_fixture()
    exact_kl = exact_kl_ratio_fixture()
    profile = profile_fixture()
    tie_masses = tie_mass_fixture()
    steps = step_ratio_fixture()
    margins = margin_limit_fixture()
    sweeps = wide_sweep_fixture()
    excess = excess_identity_fixture()
    cells = GaussianCells()
    base = cdf_and_midpoint_constants(EFFECTIVE_START, cells)
    lemmas = effective_lemma_fixture(cells=cells, base=base)
    effective = effective_theorem_fixture(EFFECTIVE_CANDIDATES, sweeps["wide"], EFFECTIVE_SCAN_LIMIT, cells, base)
    consistency = effective_consistency_fixture(effective)
    heavy_run = heavy_effective_fixture(cells, base) if heavy else None
    c_values = [gauss["rows"][f"K={k}"]["c_K"] for k in GAUSSIAN_CANDIDATES]
    full_sweeps = list(mono["full"].values())
    broad_sweeps = list(mono["broad"].values())
    checks = {
        "A_first_index_uniform_and_conditioned_on_max_agree": ties["closed_forms_agree"],
        "A_closed_forms_match_brute_force_enumeration": ties["brute_force_agrees"],
        "A_kl_on_records_equals_kl_of_max_law_fixture": ties["kl_on_records_equals_kl_of_max_law"],
        "A_kl_on_records_equals_kl_of_max_law_null_cells": all(c["equal"] for c in records.values()),
        "A_gap_on_records_matches_selection_inflation": all(c["gap_matches_selection_inflation"] for c in records.values()),
        "B_kl_strictly_below_radius_on_grid": all(c["kl"] < c["radius"] for c in grid.values()),
        "B_jittered_marginal_is_pi_K": jitter["marginal_is_pi_K"],
        "B_jittered_kl_dominates_discrete_kl": jitter["joint_kl_dominates_discrete_kl"],
        "B_jittered_kl_rises_toward_radius": jitter["joint_kl_rises_with_levels"] and jitter["joint_kl_below_radius"],
        "B_radius_is_supremum_over_uniform_supports": all(uniform[f"K={k}"]["deficit_positive_and_shrinking"]
                                                         and uniform[f"K={k}"]["deficit_at_1000"] < 0.02 for k in (2, 3, 5)),
        "C_gap_matches_max_law_on_grid": all(c["gap_from_max_law_equal"] for c in grid.values()),
        "C_gap_le_dv_at_exact_kl_on_grid": all(float(c["gap"]) <= c["dv_at_exact_kl"] + LOG_TOLERANCE for c in grid.values()),
        "C_gap_le_dv_at_radius_on_grid": all(float(c["gap"]) <= c["dv_at_radius"] + LOG_TOLERANCE for c in grid.values()),
        "C_kearns_saul_between_variance_and_hoeffding": all(
            r["variance"] <= r["kearns_saul"] + LOG_TOLERANCE and r["kearns_saul"] <= r["hoeffding"] + LOG_TOLERANCE
            for r in proxies.values()),
        "C_proxies_hold_on_t_grid": all(r["grid_violation_kearns_saul"] <= SUPREMUM_TOLERANCE
                                        and r["grid_violation_hoeffding"] <= SUPREMUM_TOLERANCE for r in proxies.values()),
        "C_hoeffding_bound_dominates_kearns_saul_bound": all(c["dv_at_radius"] <= c["dv_hoeffding_at_radius"] + LOG_TOLERANCE
                                                            for c in grid.values()),
        "D_gap_bounded_by_one_minus_p_on_grid": all(c["gap"] <= 1 - c["p"] for c in grid.values()),
        "D_ratio_below_envelope_one_minus_p_over_bound_which_falls_in_K": all(
            c["ratio_radius"] <= float(1 - c["p"]) / c["dv_at_radius"] for c in grid.values()) and all(
            float(1 - p) / grid[f"n={n},K={a},p={p}"]["dv_at_radius"]
            > float(1 - p) / grid[f"n={n},K={b},p={p}"]["dv_at_radius"]
            for a, b in zip(GRID_CANDIDATES, GRID_CANDIDATES[1:]) for p in GRID_P for n in GRID_ITEMS),
        "D_gaussian_quadratures_agree_and_match_closed_forms": gauss["closed_forms_match"]
            and all(r["quadratures_agree"] for r in gauss["rows"].values()),
        "D_c_K_below_one_and_increasing": all(c < 1 for c in c_values)
            and all(a < b for a, b in zip(c_values, c_values[1:])),
        "D_ratio_below_c_K_on_grid": all(c["ratio_radius"] < c["c_K"] for c in grid.values()),
        "D_sqrt_n_gap_approaches_gaussian_and_ratio_rises_below_c_K": all(
            limit[f"K={k}"]["error_shrinks"] and limit[f"K={k}"]["ratio_rises"] and limit[f"K={k}"]["ratio_below_c_K"]
            for k in (2, 5)),
        "D_n_equals_1_gap_equals_kl_ball_supremum": all(c["equal"] for c in sup["n_equals_1"].values()),
        "D_n_at_least_2_chain_strict": all(c["chain_strict"] for c in sup["n_at_least_2"].values()),
        "E_mad_closed_form_matches_enumeration_N_le_60": mad["closed_form_matches_enumeration"]
            and mad["even_trials_form_n_C_2n_n_over_4_to_n"],
        "E_pair_gap_is_half_mean_absolute_difference_n_le_30": pair["reduction_to_mean_absolute_difference"],
        "E_pair_closed_form_n_le_200": pair["closed_form_matches"],
        "E_pair_step_ratio_identity_strict_increase_n_le_200": pair["step_identity_and_strict_increase"],
        "E_pair_limit_quarter_pi_from_below": pair["below_limit"] and pair["scaled_deficit_near_one"],
        "E_triple_is_three_halves_of_pair_n_le_200": odd["triple_is_three_halves_of_pair"]
            and odd["triple_limit_matches_quadrature"],
        "E_quintuple_identity_n_le_200": odd["quintuple_is_five_halves_of_quadruple_minus_pair"],
        "E_tie_count_moment_matches_enumeration": ties_increment["closed_form_matches_enumeration"],
        "E_increment_is_half_minus_tie_moment_n_le_30": ties_increment["increment_identity_n_le_30"]
            and ties_increment["pair_increment_is_tie_probability_over_four"],
        "E_scaled_gap_matches_selection_inflation_n_le_40": mono["matches_selection_inflation_n_le_40"],
        "E_scaled_gap_monotone_K_3_4_5_10_20_n_le_200": all(s["monotone"] for s in full_sweeps),
        "E_min_step_ratio_at_end_of_range": all(s["min_step_ratio_at"] == MONOTONE_ITEMS for s in full_sweeps),
        "E_rho_at_least_one_equality_exactly_for_K_2_3": all(s["rho_at_least_one"] for s in full_sweeps + broad_sweeps)
            and all(s["rho_equals_one"] == (k in (2, 3)) for k, s in zip(SWEEP_CANDIDATES, broad_sweeps)),
        "E_scaled_gap_monotone_K_2_to_30_40_50_100_n_le_100_and_K_1000_n_le_40": all(s["monotone"] for s in broad_sweeps)
            and mono["large"]["monotone"] and mono["large"]["rho_at_least_one"],
        "E_scaled_gap_below_gaussian_limit_on_sweeps": all(s["below_gaussian_limit"] for s in full_sweeps + broad_sweeps)
            and mono["large"]["below_gaussian_limit"],
        "E_convex_order_fails_odd_to_even_exact": convex["absolute_moment_falls_odd_to_even_exact"]
            and convex["absolute_moment_rises_even_to_odd_exact"],
        "E_convex_order_fails_every_step_n_le_60_stop_loss": convex["stop_loss_refutes_every_step"],
        "E_exact_kl_ratio_decreasing_toward_c_K": all(
            r["strictly_decreasing_from_start"] and r["above_c_K_from_start"] and r["within_5e-4_of_c_K_at_max_items"]
            for r in exact_kl.values()),
        "F_profile_polynomial_matches_centered_max_n_le_40": profile["polynomial_matches_centered_max_n_le_40"]
            and profile["named_polynomials"],
        "F_pair_of_pairs_M4_is_2S1_minus_S2_and_mad_is_2S1_minus_2S2_n_le_60": profile["pair_of_pairs_identities"]
            and profile["mean_absolute_difference_is_two_S1_minus_S2"],
        "F_second_largest_of_four_is_3S2_by_enumeration_n_le_4": profile["second_largest_of_four_is_three_S2_by_enumeration_n_le_4"],
        "F_profile_and_quadruple_increments_in_local_sums_n_le_60": profile["profile_increment_identities"],
        "F_tie_count_law_matches_enumeration_and_weighted_sum_is_increment": tie_masses["tie_count_law_matches_enumeration"]
            and tie_masses["weighted_tie_law_is_increment_n_le_30"],
        "F_crude_tie_bound_exact_K_2_fails_K_3_by_half_n_sum_q_cubed_and_K_4_n_le_60": tie_masses["crude_bound_exact_for_pairs"]
            and tie_masses["crude_bound_fails_for_triples_by_half_n_sum_q_cubed"] and tie_masses["crude_bound_fails_for_quadruples"],
        "F_rational_step_ratio_degree_1_for_K_2_3_none_through_degree_6_for_K_4": steps["pairs_and_triples_have_degree_one_ratio"]
            and steps["quadruple_has_no_rational_ratio"] and not steps["degree_one_exists"]["K=4"],
        "F_quadruple_recurrence_order_4_degree_8_verified_n_le_300_roots_16_16_m2_m4": steps["recurrence"]["verified"]
            and all(steps["recurrence"]["characteristic_roots"].values())
            and all(v == 0 for v in steps["recurrence"]["lower_order_nullity"].values()),
        "F_gaussian_third_moment_closed_forms_K_2_3_give_zero_margin": margins["closed_forms_K_2_3"],
        "F_gaussian_margin_limit_positive_and_increasing_K_4_to_100": margins["positive_K_4_to_100"] and margins["increasing_K_4_to_100"],
        "F_scaled_gap_monotone_K_4_to_100_n_le_400_exact": sweeps["wide_monotone"] and sweeps["wide_rho_at_least_one"],
        "F_scaled_gap_monotone_K_200_500_1000_10000_n_le_60_exact": sweeps["huge_monotone"] and sweeps["huge_rho_at_least_one"],
        "F_richardson_matches_gaussian_margin_limit_K_4_to_100": sweeps["wide_max_relative_fit_residual"] <= MARGIN_FIT_TOLERANCE,
        "F_global_min_margin_at_K_4_n_400_and_margins_at_n_400_above_their_limits": sweeps["wide_global_min_margin_K"] == 4
            and sweeps["wide_global_min_margin_at"] == WIDE_SWEEP_ITEMS and sweeps["wide_margin_at_max_items_above_gaussian_limit"],
        "G_excess_identity_D_n_equals_H_sum_plus_local_terms_n_le_12": excess["identity_n_le_max"]
            and excess["excess_polynomials_named"],
        "G_midpoint_euler_maclaurin_formula_and_K6_kernel_exact": excess["euler_maclaurin_exact"],
        "G_rational_enclosures_of_exp_and_Phi_bracket_floats": excess["enclosures_bracket_floats"]
            and excess["cdf_enclosures_tight_for_abs_t_le_6"],
        "G_lemmas_L_F_M_hold_exactly_at_n_400_and_900": lemmas["lemmas_hold"],
        "G_delta_K_quadrature_equals_c_K_E_M_K_over_2_K_4_to_30": consistency["deltas_agree"],
        "G_sqrt_n_D_n_within_C_K_over_n_of_delta_K_at_n_400_900": consistency["deviations_within_C"],
        "G_threshold_at_n_400_for_K_4_to_25_and_by_n_500_for_K_26_to_30": effective["closed_at_start"] == list(range(4, 26))
            and all(t is not None and t <= 500 for t in effective["thresholds"].values()),
        "G_theorem_rho_n_ge_1_for_every_n_K_4_to_30": effective["all_theorems"],
        "G_K_5_margin_is_five_halves_of_K_4_and_K_8_does_not_reduce": excess["margin_five_is_five_halves_of_four_n_le_60"]
            and excess["M8_not_a_combination_of_M4_M2"],
    }
    if heavy:
        checks["G_heavy_theorem_K_31_to_40_and_certified_tails_K_41_to_50"] = heavy_run["all_passed"]
    rows4 = effective["rows"]["K=4"]
    headline_v0_4 = {
        "verdict": {"K=2,3": "theorem (closed forms)",
                    "K=4..30": "theorem for every n: |sqrt(n) D_n - delta_K| <= C_K/n for n >= 400, threshold N0 checked exactly, "
                               "exact rho_n >= 1 below",
                    "K=5": "equivalent to K=4 (D_n(5) = (5/2) D_n(4))",
                    "K=31..40": "theorem with verify(heavy=True) (exact scans to N0 <= 800)",
                    "K=41..50": "D_n > 0 for n >= N0 (certified, heavy run) and for n <= 400 (exact); (400, N0) unchecked",
                    "K=51..100": "exact for n <= 400; the expansion holds for every K with a computable C_K (not run here, "
                                 "large through the Poisson terms); delta_K > 0 by quadrature only",
                    "K=200,500,1000,10000": "exact for n <= 60 only"},
        "R_F": lemmas["R_F"], "R_mu": lemmas["R_mu"], "R_F_pieces": lemmas["R_F_pieces"],
        "observed_remainders": lemmas["rows"],
        "C_K": {key: r["C"] for key, r in effective["rows"].items()},
        "thresholds": effective["thresholds"],
        "scaled_margin_at_threshold": {key: r["scaled_margin_at_threshold"] for key, r in effective["rows"].items()},
        "K4_pieces": rows4["pieces"],
        "delta_K": {key: r["delta"] for key, r in consistency["deltas"].items()},
        "deviations": consistency["deviations"]}
    if heavy:
        headline_v0_4["heavy"] = {"C_K": {key: r["C"] for key, r in heavy_run["full"]["rows"].items()},
                                  "thresholds": heavy_run["full"]["thresholds"],
                                  "tails": heavy_run["tails"]}
    return {"evidence_status": "exact_synthetic_fixtures_not_model_or_agent_evidence",
            "checks": checks, "all_passed": all(checks.values()),
            "tolerances": {"log_and_sqrt": LOG_TOLERANCE, "kl_ball_supremum": SUPREMUM_TOLERANCE,
                           "gaussian_quadrature": QUADRATURE_TOLERANCE, "stop_loss_margin": STOP_LOSS_MARGIN},
            "grid": {"items": GRID_ITEMS, "candidates": GRID_CANDIDATES, "p": GRID_P, "cells": len(grid)},
            "heavy": heavy,
            "monotonicity": {"items": MONOTONE_ITEMS, "candidates": MONOTONE_CANDIDATES,
                             "sweep_items": SWEEP_ITEMS, "sweep_candidates": SWEEP_CANDIDATES,
                             "large": (LARGE_CANDIDATES, LARGE_ITEMS),
                             "wide": (WIDE_SWEEP_CANDIDATES[0], WIDE_SWEEP_CANDIDATES[-1], WIDE_SWEEP_ITEMS),
                             "huge": (HUGE_SWEEP_CANDIDATES, HUGE_SWEEP_ITEMS)},
            "effective": {"start": EFFECTIVE_START, "candidates": EFFECTIVE_CANDIDATES, "scan_limit": EFFECTIVE_SCAN_LIMIT,
                          "local_tau": LOCAL_TAU, "cells": (CELL_RANGE, CELLS_PER_UNIT), "delta_tolerance": DELTA_TOLERANCE},
            "headline_v0_4": headline_v0_4,
            "headline_v0_3": {
                "verdict": {"K=2": "theorem", "K=3": "theorem",
                            "K>=4": "exact on K=4..100 (n<=400) and K=200,500,1000,10000 (n<=60); limit margin c(K)>0 by Edgeworth; unproved"},
                "wide_sweep_table": {k: {key: r[key] for key in ("monotone", "min_margin", "min_margin_at", "min_rho", "min_rho_at",
                                                                 "margin_at_max_items", "scaled_rho_excess_at_max_items",
                                                                 "scaled_rho_excess_richardson", "gaussian_margin_limit",
                                                                 "gaussian_normalized_margin_limit", "richardson_minus_gaussian")}
                                     for k, r in sweeps["wide"].items() if r["candidates"] in (4, 5, 6, 8, 10, 20, 50, 100)},
                "huge_sweep_table": {k: {key: r[key] for key in ("monotone", "min_margin", "min_margin_at", "min_rho", "min_rho_at",
                                                                 "margin_at_max_items", "gaussian_margin_limit")}
                                     for k, r in sweeps["huge"].items()},
                "wide_global_min_margin": (sweeps["wide_global_min_margin"], sweeps["wide_global_min_margin_K"],
                                           sweeps["wide_global_min_margin_at"]),
                "wide_min_margin_at_max_items_for_K": sweeps["wide_min_margin_at_max_items_for"],
                "wide_max_relative_fit_residual": sweeps["wide_max_relative_fit_residual"],
                "quadruple_recurrence": {key: steps["recurrence"][key] for key in ("coefficients", "characteristic_monic",
                                                                                   "verified_items", "lower_order_nullity")},
                "rank_tests": steps["rank_tests"],
                "crude_tie_bound_deficits": tie_masses["deficits"],
                "gaussian_margin_limits": {**margins["c_K"], **margins["c_K_huge"]},
                "normalized_margin_limits": margins["normalized_margin_limit"]},
            "headline": {
                "monotone_table": {k: {key: s[key] for key in ("monotone", "min_step_ratio", "min_step_ratio_at",
                                                              "min_margin", "min_margin_at", "min_rho", "min_rho_at",
                                                              "scaled_gap_first", "scaled_gap_at_max_items",
                                                              "gaussian_limit", "approach_coefficient")}
                                   for k, s in mono["full"].items()},
                "pair_step_ratio_at_200": pair_step_ratio(MONOTONE_ITEMS),
                "exact_kl_ratio": {k: {key: r[key] for key in ("c_K", "decreasing_from", "max_value", "max_value_at",
                                                               "value_at_max_items", "kl_over_radius_at_max_items")}
                                   for k, r in exact_kl.items()},
                "stop_loss_min_excess": convex["stop_loss_min_excess"],
                "c_K": {f"K={k}": gauss["rows"][f"K={k}"]["c_K"] for k in GAUSSIAN_CANDIDATES},
                "expected_max_of_K_normals": {f"K={k}": gauss["rows"][f"K={k}"]["expected_max"] for k in GAUSSIAN_CANDIDATES},
                "max_ratio_radius_on_grid": max(c["ratio_radius"] for c in grid.values()),
                "max_ratio_radius_cell": max(grid, key=lambda k: grid[k]["ratio_radius"]),
                "max_ratio_exact_kl_on_grid": max(c["ratio_exact"] for c in grid.values()),
                "max_ratio_exact_kl_cell": max(grid, key=lambda k: grid[k]["ratio_exact"]),
                "max_ratio_radius_per_K": {f"K={k}": max(c["ratio_radius"] for c in grid.values() if c["candidates"] == k)
                                           for k in GRID_CANDIDATES},
                "max_kl_over_radius_on_grid": max(c["kl"] / c["radius"] for c in grid.values())},
            "tie_rules": ties, "records": records, "jitter": jitter, "grid_cells": grid,
            "proxies": proxies, "supremum": sup, "gaussian": gauss, "limit": limit,
            "uniform_supports": uniform, "mad": mad, "pair_theorem": pair, "odd_candidates": odd,
            "tie_increment": ties_increment, "monotonicity_sweeps": mono, "convex_order": convex,
            "exact_kl_ratio": exact_kl, "profile": profile, "tie_masses": tie_masses, "step_ratios": steps,
            "margin_limits": margins, "wide_sweeps": sweeps,
            "excess_identity": excess, "effective_lemmas": lemmas,
            "effective_theorem": {"start": effective["start"], "thresholds": effective["thresholds"],
                                  "rows": {key: {k2: v for k2, v in r.items()} for key, r in effective["rows"].items()}},
            "effective_consistency": consistency}
