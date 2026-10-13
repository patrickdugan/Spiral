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
"""

from __future__ import annotations

from fractions import Fraction as Q
from functools import lru_cache
from itertools import product
from math import comb, erfc, exp, log, pi, sqrt

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
    c_values = [gauss["rows"][f"K={k}"]["c_K"] for k in GAUSSIAN_CANDIDATES]
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
    }
    return {"evidence_status": "exact_synthetic_fixtures_not_model_or_agent_evidence",
            "checks": checks, "all_passed": all(checks.values()),
            "tolerances": {"log_and_sqrt": LOG_TOLERANCE, "kl_ball_supremum": SUPREMUM_TOLERANCE,
                           "gaussian_quadrature": QUADRATURE_TOLERANCE},
            "grid": {"items": GRID_ITEMS, "candidates": GRID_CANDIDATES, "p": GRID_P, "cells": len(grid)},
            "headline": {
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
            "uniform_supports": uniform}
