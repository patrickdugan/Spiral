"""Crosswalk check: Spiral's exact selection gap against the ASMP-8 KL-slice bound.

Companion to paper/feedback_channel_rsitopology_crosswalk.md, section 1.

Setting.  One candidate's record on the selection set is omega in {0,1}^n with
law p0 = Bernoulli(p)^n (the Spiral null, axiom A5: every candidate has true
value p).  Proxy R_hat(omega) = score = (1/n) sum omega_i; true R(omega) = p.
Keeping the best of K i.i.d. candidates by score induces a law pi_K on records.
The selected score is the maximum of K i.i.d. Bin(n,p)/n draws, so Spiral's
selection gap gamma(n,K,p) = E[max_k S_k] - p (insertions note, selection law;
multigen note, Proposition 1 with K -> GK+1) equals E_{pi_K}[R_hat - R].

The ASMP-8 KL-slice theorem (RSITopology repairs draft, item R3) bounds, for
every pi with KL(pi||p0) <= lambda and delta = R - R_hat sigma-sub-Gaussian
under p0,   E_pi[-delta] - E_p0[-delta] <= sigma sqrt(2 lambda)   (Donsker-
Varadhan step), and Regret <= 2 sigma sqrt(2 lambda).  Here E_p0[-delta] = 0.
So if pi_K lies in the KL ball of radius lambda_K,

    gamma(n,K,p)  <=  sup_{KL(pi||p0)<=lambda_K} E_pi[S] - p  <=  sigma_n sqrt(2 lambda_K).

Three quantities are computed per cell: the exact gap (rational), the exact
KL(pi_K||p0) (float; it is a finite sum of rationals times logs of rationals),
and the KL-ball supremum at that radius (exponential tilt, bisection).  The
sub-Gaussian constant of a Bernoulli(p) is the Kearns-Saul value
v(p) = (1-2p) / (2 ln((1-p)/p)), v(1/2) = 1/4 (its optimality is a citation,
not checked here); for the mean of n independent draws sigma_n^2 = v(p)/n.
The script checks that constant on a t-grid (sanity, not proof).  Beirami et
al. (arXiv 2401.01879) give log K - (K-1)/K as an upper bound on the best-of-K
KL; the exact KL is compared with it.  For the tied law used here the bound is
proved, strictly for K >= 2, in paper/selection_law_kl_containment.md
(Theorem B; module spiral_ln.evaluation_selection_kl), together with the DV
step gamma <= sqrt(2 v(p) KL / n).  Under the null the ASMP-8 Regret is identically
zero, so no regret is computed: the comparison is between the selection gap
and the single-term DV bound that R3's proof passes through.

Exact where possible (Fractions); floats with tolerance 1e-9 where a log or a
square root appears.  Stdlib only.  No model is called.
"""
from __future__ import annotations

import sys
from fractions import Fraction as Q
from math import comb, exp, log, sqrt

TOL = 1e-9


def binom_pmf(n: int, p: Q) -> list[Q]:
    return [comb(n, k) * p**k * (1 - p) ** (n - k) for k in range(n + 1)]


def max_of_draws_law(pmf: list[Q], draws: int) -> list[Q]:
    """Law of the maximum of `draws` i.i.d. scores: P(max = s) = F(s)^M - F(s-1)^M."""
    cdf: list[Q] = []
    acc = Q(0)
    for q in pmf:
        acc += q
        cdf.append(acc)
    law = []
    prev = Q(0)
    for s in range(len(pmf)):
        cur = cdf[s] ** draws
        law.append(cur - prev)
        prev = cur
    return law


def kl(pi: list[Q], p0: list[Q]) -> float:
    """KL of two rational laws; the log-ratio is taken on the integer parts so that
    atoms below float range (e.g. 2^(-16*81)) do not underflow inside the log."""
    total = 0.0
    for a, b in zip(pi, p0):
        if a > 0:
            log_ratio = (log(a.numerator) + log(b.denominator)
                         - log(a.denominator) - log(b.numerator))
            total += float(a) * log_ratio
    return total


def kearns_saul_variance_proxy(p: Q) -> float:
    if p == Q(1, 2):
        return 0.25
    pf = float(p)
    return (1 - 2 * pf) / (2 * log((1 - pf) / pf))


def check_subgaussian(pmf: list[Q], n: int, p: Q, sigma2: float) -> float:
    """Largest violation of log E exp(t(S-p)) <= sigma2 t^2/2 on a t-grid (should be <= 0)."""
    worst = -1.0
    mean = float(p)
    for k in range(1, 401):
        for sgn in (1.0, -1.0):
            t = sgn * k * 0.05 * sqrt(n)
            lmgf = log(sum(float(q) * exp(t * (s / n - mean)) for s, q in enumerate(pmf)))
            worst = max(worst, lmgf - sigma2 * t * t / 2)
    return worst


def tilt(p0: list[Q], scores: list[float], t: float) -> list[float]:
    m = max(scores)
    w = [float(q) * exp(t * (s - m)) for q, s in zip(p0, scores)]
    z = sum(w)
    return [x / z for x in w]


def kl_float(pi: list[float], p0: list[Q]) -> float:
    return sum(a * log(a / float(b)) for a, b in zip(pi, p0) if a > 0)


def kl_ball_sup(p0: list[Q], n: int, lam: float) -> float:
    """sup E_pi[score] over KL(pi||p0) <= lam: the exponential tilt at radius lam,
    or the point mass on score n once -log p0(n) <= lam."""
    scores = [s / n for s in range(n + 1)]
    if -log(float(p0[n])) <= lam + 1e-12:
        return 1.0
    lo, hi = 0.0, 1.0
    while kl_float(tilt(p0, scores, hi), p0) < lam:
        hi *= 2.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if kl_float(tilt(p0, scores, mid), p0) < lam:
            lo = mid
        else:
            hi = mid
    pi = tilt(p0, scores, lo)
    return sum(a * s for a, s in zip(pi, scores))


def try_spiral(n: int, draws: int, p: Q):
    try:
        from spiral_ln.evaluation_game_feedback import selection_inflation
    except Exception:  # noqa: BLE001 - optional cross-check only
        return None
    return selection_inflation(n, draws, p)["readout_gap"]


def cell(n: int, draws: int, p: Q, label: str, expected: Q | None = None) -> dict[str, float]:
    pmf = binom_pmf(n, p)
    law = max_of_draws_law(pmf, draws)
    assert sum(law) == 1
    gap = sum(Q(s, n) * q for s, q in enumerate(law)) - p
    if expected is not None:
        assert gap == expected, (label, gap, expected)
    spiral = try_spiral(n, draws, p)
    if spiral is not None:
        assert spiral == gap, (label, spiral, gap)
    kl_exact = kl(law, pmf)
    lam_b = log(draws) - (draws - 1) / draws
    sigma2 = kearns_saul_variance_proxy(p) / n
    sigma = sqrt(sigma2)
    viol = check_subgaussian(pmf, n, p, sigma2)
    assert viol <= 1e-9, (label, viol)
    sup_exact = kl_ball_sup(pmf, n, kl_exact) - float(p)
    bound_exact = sigma * sqrt(2 * kl_exact)
    bound_b = sigma * sqrt(2 * lam_b)
    g = float(gap)
    assert g <= sup_exact + TOL, (label, g, sup_exact)
    assert sup_exact <= bound_exact + TOL, (label, sup_exact, bound_exact)
    assert kl_exact <= lam_b + TOL, (label, kl_exact, lam_b)
    assert bound_exact <= bound_b + TOL
    frac = f"{gap.numerator}/{gap.denominator}" if gap.denominator < 10**6 else "(long)"
    print(f"  {label:28s} n={n:4d} M={draws:3d} p={p}: gap={g:.5f} [{frac}]"
          f"  KL(pi_M||p0)={kl_exact:.4f} (Beirami {lam_b:.4f})"
          f"  KL-ball sup={sup_exact:.5f}  sigma*sqrt(2KL)={bound_exact:.5f}"
          f"  sigma*sqrt(2*Beirami)={bound_b:.5f}  gap/bound={g / bound_exact:.3f}"
          f"{'' if spiral is None else '  [= spiral selection_inflation]'}")
    return {"gap": g, "sup": sup_exact, "bound": bound_exact, "bound_b": bound_b, "kl": kl_exact}


def main() -> int:
    print("ASMP-8 KL-slice bound vs Spiral exact selection gap (M = number of i.i.d. draws kept-best-of)")
    print("insertions note, selection law, K=2 candidates, p=1/2:")
    half = Q(1, 2)
    cell(1, 2, half, "ins n=1", Q(1, 4))
    cell(4, 2, half, "ins n=4", Q(35, 256))
    cell(16, 2, half, "ins n=16")
    cell(64, 2, half, "ins n=64")
    print("multigen note, Proposition 1 (running maximum, M = GK+1), n=8, K=2:")
    cell(8, 3, half, "mg n=8 K=2 G=1", Q(19305, 131072))
    for G in (5, 10, 20):
        cell(8, 2 * G + 1, half, f"mg n=8 K=2 G={G}")
    print("multigen note, n=16, K=4:")
    for G in (1, 5, 10, 20):
        cell(16, 4 * G + 1, half, f"mg n=16 K=4 G={G}")
    print("composition note, Proposition 4 (n=1, K=2: generation 1 = 2 draws, generation 2 = 2K-1 = 3):")
    cell(1, 2, half, "comp gen 1", Q(1, 4))
    cell(1, 3, half, "comp gen 2", Q(3, 8))
    print("off-centre p (exercises the Kearns-Saul constant):")
    cell(8, 3, Q(1, 4), "p=1/4 n=8 M=3")
    cell(8, 3, Q(3, 4), "p=3/4 n=8 M=3")
    print("Gaussian limit, K=2, p=1/2: sqrt(n)*gap -> 1/(2 sqrt(pi)) = 0.28209;"
          " sqrt(n)*bound(Beirami) = sqrt(2 ln2 - 1)/2 = 0.31077; ratio -> 0.9077")
    for n in (16, 64, 256, 1024):
        r = cell(n, 2, half, f"limit n={n}")
        print(f"      sqrt(n)*gap={sqrt(n) * r['gap']:.5f}  sqrt(n)*bound_B={sqrt(n) * r['bound_b']:.5f}"
              f"  gap/bound_B={r['gap'] / r['bound_b']:.4f}")
    print("Regret under the Spiral null (A5): sup_pi R - R(pi_hat) = p - p = 0 for every cell;"
          " the gap above is the proxy-minus-true term, not the regret.")
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
