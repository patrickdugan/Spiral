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
5. Monotone approach (D.5, versions 0.2-0.3).  With ``a_n(K) = sqrt(n) gamma(n, K, 1/2)``
   (so ``r(n, K, 1/2) = 2 a_n(K) / sqrt(2 lambda_K)``), ``a_n(2)^2 = n C(2n,n)^2 /
   (4 * 16^n)`` by de Moivre's mean absolute deviation, ``a_{n+1}(2)^2 / a_n(2)^2 =
   1 + 1/(4n(n+1))``, and ``a_n(3) = (3/2) a_n(2)`` by the order-statistic
   recurrence; both rise strictly to ``E[max]/2``, so ``sup_n r = c_K`` for
   ``K = 2, 3``.  For ``K >= 4`` the increase is verified exactly on ``a_n^2`` for ``K = 4..100``
   (``n <= 400``) and ``K = 200, 500, 1000, 10000`` (``n <= 60``), but not proved: with the
   overlap profile ``w_m = F_n(m)(1 - F_n(m))``, ``M_n(4) = 2 sum w_m - sum w_m^2`` (the
   pair-of-pairs step collapses to one sum), yet ``sum w_m^2 = E[Y_(3:4)]/3`` has no de
   Moivre identity, its increment carries ``sum C(n,m)^4``, the step ratio of ``M_n(4)`` is
   not a rational function (exact rank test), and ``2^(4n+1) M_n(4)`` obeys an order-4
   recurrence; the tie-mass bound ``M_{n+1} - M_n >= P(N >= 2)/4`` is tight only for ``K = 2``
   and fails to give ``rho_n >= 1`` at ``K = 3`` by exactly ``(n/2) sum q_m^3``.  The margin's
   limit is ``n (rho_n - 1) -> c(K) = (E[M_K^3] - (5/2) E[M_K]) / (6 E[M_K])`` (Edgeworth, cited;
   matched by Richardson extrapolation of the exact values to ``5e-8`` at ``K = 4``), zero at
   ``K = 2, 3`` and positive beyond, so the question is settled asymptotically and verified
   exactly on the sweeps, with the smallest normalized margin ``1.0826`` at ``K = 4, n = 400``.
"""

from __future__ import annotations

from fractions import Fraction as Q
from functools import lru_cache
from itertools import product
from math import comb, erfc, exp, gcd, log, pi, sqrt

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
    ``(2n+1)^2 = 4n(n+1) + 1``.  Telescoping, ``a_n(2)^2 = (1/16) prod_{j<n} (2j+1)^2/((2j)(2j+2))``
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


# --- verification ----------------------------------------------------------------------

def verify() -> dict[str, object]:
    """Run every fixture and return machine-readable checks."""

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
    }
    return {"evidence_status": "exact_synthetic_fixtures_not_model_or_agent_evidence",
            "checks": checks, "all_passed": all(checks.values()),
            "tolerances": {"log_and_sqrt": LOG_TOLERANCE, "kl_ball_supremum": SUPREMUM_TOLERANCE,
                           "gaussian_quadrature": QUADRATURE_TOLERANCE, "stop_loss_margin": STOP_LOSS_MARGIN},
            "grid": {"items": GRID_ITEMS, "candidates": GRID_CANDIDATES, "p": GRID_P, "cells": len(grid)},
            "monotonicity": {"items": MONOTONE_ITEMS, "candidates": MONOTONE_CANDIDATES,
                             "sweep_items": SWEEP_ITEMS, "sweep_candidates": SWEEP_CANDIDATES,
                             "large": (LARGE_CANDIDATES, LARGE_ITEMS),
                             "wide": (WIDE_SWEEP_CANDIDATES[0], WIDE_SWEEP_CANDIDATES[-1], WIDE_SWEEP_ITEMS),
                             "huge": (HUGE_SWEEP_CANDIDATES, HUGE_SWEEP_ITEMS)},
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
            "margin_limits": margins, "wide_sweeps": sweeps}
