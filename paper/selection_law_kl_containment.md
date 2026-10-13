# Best-of-K inside the KL slice: tie rules, containment, the DV bound

Draft 0.1 — 2026-10-13. Settles item 1 of §8 of `feedback_channel_rsitopology_crosswalk.md` and the two "not determined"
sentences of its §1. Module `src/spiral_ln/evaluation_selection_kl.py`; 50 tests in `tests/test_evaluation_selection_kl.py`;
receipt `output/evaluation_selection_kl/selection_kl_v0_1.json` (24 checks, source hashes). Nothing is run against a model.
Evidence levels follow the calculus card (§11): *algebraic identity* (proved for every parameter), *finite verified example*
(checked on enumerated cells), *cited* (taken from the literature, not reproved). Rationals are exact; logarithms, square
roots and one quadrature are floats under tolerance \(10^{-12}\) (\(10^{-9}\) for the KL-ball supremum and the quadrature).

```powershell
$env:PYTHONPATH = "src"
python scripts/verify_evaluation_selection_kl.py --output output/evaluation_selection_kl/selection_kl_v0_1.json
python -m pytest tests/test_evaluation_selection_kl.py -q
```

## 0. Setting

Finite \(\Omega\), law \(p_0\), score \(S:\Omega\to\mathbb R\); \(q(s)=P_0(S=s)\), \(F(s)=P_0(S\le s)\),
\(F(s-)=P_0(S<s)\). Draw \(\omega_1,\dots,\omega_K\) i.i.d. from \(p_0\) and keep one of maximal score, ties
broken by the first index attaining the maximum (*first-index rule*) or uniformly among those attaining it
(*uniform rule*). \(\pi_K\) is the law of the kept record; \(m_K(s)=P(\max_kS(\omega_k)=s)=F(s)^K-F(s-)^K\).
Spiral null: \(\Omega=\{0,1\}^n\), \(p_0=\mathrm{Bern}(p)^n\), \(S=\bar S=\)count\(/n\), and
\(\gamma(n,K,p)=\mathbb E[\max_k\bar S_k]-p=\mathbb E_{\pi_K}[\bar S]-p\) (`selection_inflation`);
\(\lambda_K=\ln K-(K-1)/K\).

## 1. Theorem A (tie rules)

**Theorem A.** Let the kept index \(J\) be any function of the score vector \((S(\omega_1),\dots,S(\omega_K))\)
and of randomness independent of the sample, with \(J\) in the argmax set. Then
\(\pi_K(\omega)=p_0(\omega)\,m_K(S(\omega))/q(S(\omega))\) (zero where \(p_0(\omega)=0\)): \(p_0\) conditioned
on the score, mixed over the law of the maximum. Both rules are such a \(J\). Consequently
\(\mathrm{KL}(\pi_K\|p_0)=\mathrm{KL}(m_K\|q)\), the divergence of the law of the maximum of \(K\) scores from the law of one.

*Proof.* Conditionally on the score vector the records are independent with
\(\omega_k\sim p_0(\cdot\mid S=S(\omega_k))\), and \(J\) is conditionally independent of them, so
\(P(\omega_J=\omega\mid\text{scores})=p_0(\omega)\mathbf 1\{S(\omega)=\max\}/q(\max)\); take expectations.
Directly: under the first-index rule candidate \(k\) is kept with record \(\omega\), \(s=S(\omega)\), iff
\(\omega_k=\omega\), every earlier score is \(<s\) and every later one \(\le s\), so
\(P(\omega_J=\omega)=p_0(\omega)\sum_{k=1}^KF(s-)^{k-1}F(s)^{K-k}=p_0(\omega)\frac{F(s)^K-F(s-)^K}{F(s)-F(s-)}\).
Under the uniform rule, by exchangeability
\(P(\omega_J=\omega)=K\,\mathbb E[\mathbf 1\{\omega_1=\omega\}\mathbf 1\{1\in T\}/|T|]
=Kp_0(\omega)\sum_{j=0}^{K-1}\binom{K-1}{j}\frac{q(s)^jF(s-)^{K-1-j}}{j+1}
=p_0(\omega)\sum_{j=0}^{K-1}\binom{K}{j+1}q(s)^jF(s-)^{K-1-j}\), the same binomial expansion (\(T\) the argmax set).
The KL identity: \(\ln(\pi_K/p_0)\) depends on \(\omega\) only through \(S(\omega)\), and \(\pi_K(S=s)=m_K(s)\). \(\square\)

Algebraic identity. Finite check: the three closed forms (geometric sum, binomial sum, conditioned-on-max)
agree exactly and equal literal enumeration of every \(K\)-tuple under both rules on five record spaces with
ties, \(K\le3\); on \(\{0,1\}^n\), \(n\le6\), the KL on records equals \(\mathrm{KL}(m_K\|q)\) and the gap equals `selection_inflation`.

## 2. Theorem B (containment)

**Theorem B.** For every finite \(p_0\), score and \(K\): \(\mathrm{KL}(\pi_K\|p_0)\le\lambda_K=\ln K-(K-1)/K\),
with equality iff \(K=1\). The radius is the supremum: for \(p_0\) uniform on \(N\) records with distinct
scores \(\mathrm{KL}\to\lambda_K\) as \(N\to\infty\), and it is attained exactly by any atomless score law
(no ties), which is Beirami et al.'s tie-free best-of-\(K\).

*Proof.* Let \(s_1<\dots<s_m\) be the atoms of \(q\) and \(u\) smaller than \(\min_i(s_{i+1}-s_i)\) (any
\(u>0\) if \(m=1\)). Give every candidate an independent jitter \(U_k\sim\mathrm{Unif}(0,u)\) and the jittered
score \(\tilde S_k=S(\omega_k)+U_k\). Its law has the continuous CDF \(\tilde F(x)=F(s_i-)+q(s_i)(x-s_i)/u\) on
\([s_i,s_i+u]\), flat between; jittered ties are null; the jittered order refines the discrete order, since
\(s_i+U<s_i+u<s_{i+1}\). Keep \(\tilde J=\arg\max_k\tilde S_k\).
(i) *The kept record has law \(\pi_K\).* \(\tilde J\) lies in the discrete argmax set and is a function of the
scores and of the independent \(U\)'s, so Theorem A applies; this is also why the jittered selection and the
uniform rule give the same record law.
(ii) *The jittered KL is exactly \(\lambda_K\).* On \(\tilde\Omega=\Omega\times(0,u)\) with
\(\tilde p_0=p_0\otimes\mathrm{Unif}\) and \(\tilde s(\omega,t)=S(\omega)+t\):
\(P((\omega_{\tilde J},U_{\tilde J})\in A)=\sum_kP(X_k\in A,\ \tilde S_k>\tilde S_j\ \forall j\ne k)
=K\int_A\tilde F(\tilde s(x))^{K-1}\tilde p_0(dx)\), so \(d\tilde\pi_K/d\tilde p_0=h:=K\tilde F(\tilde s)^{K-1}\)
and \(\mathrm{KL}(\tilde\pi_K\|\tilde p_0)=\mathbb E_{\tilde\pi_K}\ln h=\ln K+(K-1)\mathbb E\ln V\) with
\(V=\tilde F(\tilde S_{\max})=\max_k\tilde F(\tilde S_k)\). Each \(\tilde F(\tilde S_k)\) is \(\mathrm{Unif}(0,1)\)
(\(\tilde F\) continuous), so \(V\sim\mathrm{Beta}(K,1)\) and \(\mathbb E\ln V=\int_0^1Kv^{K-1}\ln v\,dv=-1/K\).
(iii) *Dropping the jitter cannot raise KL.* With \(g(\omega,t)=\omega\): \(g_\#\tilde\pi_K=\pi_K\) by (i),
\(g_\#\tilde p_0=p_0\), and \(\pi_K(\omega)/p_0(\omega)=\mathbb E_U[h(\omega,U)]\) directly:
\(K\int_0^u(F(s-)+q(s)t/u)^{K-1}dt/u=(F(s)^K-F(s-)^K)/q(s)=m_K(s)/q(s)\). With \(\varphi(x)=x\ln x\) convex, Jensen gives
\(\mathrm{KL}(\pi_K\|p_0)=\sum_\omega p_0(\omega)\varphi(\mathbb E_Uh(\omega,U))\le\sum_\omega p_0(\omega)\mathbb E_U\varphi(h(\omega,U))
=\mathrm{KL}(\tilde\pi_K\|\tilde p_0)=\lambda_K\).
*Equality.* \(\varphi\) is strictly convex, so equality needs \(t\mapsto\tilde F(S(\omega)+t)^{K-1}\) constant
on \((0,u)\) for every \(\omega\) in the support; \(\tilde F\) rises there at slope \(q(s)/u>0\), so this holds iff \(K=1\).
*Supremum.* For uniform \(q\) on \(N\) atoms, \(Nm_K(i)=N[(i/N)^K-((i-1)/N)^K]=g(\xi_i)\) with \(g(x)=Kx^{K-1}\)
and \(\xi_i\in((i-1)/N,i/N)\) (mean value theorem), so \(\mathrm{KL}=\sum_i\frac1Ng(\xi_i)\ln g(\xi_i)\to\int_0^1g\ln g=\lambda_K\).
For an atomless law the computation in (ii) applies with no jitter. \(\square\)

Algebraic identity. The tied case of Beirami et al.'s bound, left open in the crosswalk, is covered: for
finite \(\Omega\) and \(K\ge2\) it holds strictly. Finite checks: \(\mathrm{KL}(\pi_K\|p_0)<\lambda_K\) on all
90 null cells (largest \(\mathrm{KL}/\lambda_K\) 0.9936, at \(n=64\)); a discrete stand-in for the jitter
(\(L\in\{1,2,4,8,16\}\) equally likely offsets inside the smallest gap) has marginal exactly \(\pi_K\), KL above
the discrete KL and rising toward \(\lambda_K\) (0.351, 0.411, 0.426, 0.431, 0.432 against \(\lambda_3=0.432\));
uniform supports \(N\in\{10,100,1000\}\) have deficits \(3.8\times10^{-3}\), \(5.7\times10^{-5}\), \(7.7\times10^{-7}\) at \(K=2\).

## 3. Theorem C (the Donsker–Varadhan bound)

**Theorem C.** Under the null let \(v(p)=\frac{1-2p}{2\ln\frac{1-p}p}\), \(v(\tfrac12)=\tfrac14\) (Kearns and
Saul 1998: \(\ln\mathbb E e^{t(X-p)}\le v(p)t^2/2\) for \(X\sim\mathrm{Bern}(p)\) and all real \(t\); Hoeffding's
lemma gives the elementary fallback \(v=\tfrac14\)). For every law \(\pi\ll p_0\) on \(\{0,1\}^n\),
\(\mathbb E_\pi[\bar S]-p\le\sqrt{2\,(v(p)/n)\,\mathrm{KL}(\pi\|p_0)}\). Hence
\(\gamma(n,K,p)\le\sqrt{2v(p)\mathrm{KL}(\pi_K\|p_0)/n}\le\sqrt{2v(p)\lambda_K/n}\).

*Proof.* (1) \(\bar S-p=\frac1n\sum_i(X_i-p)\) with independent summands, so
\(\ln\mathbb E_{p_0}e^{t(\bar S-p)}=\sum_i\ln\mathbb E e^{(t/n)(X_i-p)}\le n\,v(p)\,t^2/(2n^2)=\sigma_n^2t^2/2\), \(\sigma_n^2=v(p)/n\).
(2) For any \(f\) and \(\pi\ll p_0\), with \(p_0^f\propto e^fp_0\):
\(\mathrm{KL}(\pi\|p_0)+\ln\mathbb E_{p_0}e^f-\mathbb E_\pi f=\mathbb E_\pi\ln\frac{d\pi}{dp_0^f}=\mathrm{KL}(\pi\|p_0^f)\ge0\), equality iff \(\pi=p_0^f\).
(3) Take \(f=t(\bar S-p)\), \(t>0\): \(\mathbb E_\pi[\bar S]-p\le\mathrm{KL}/t+\sigma_n^2t/2\); at
\(t=\sqrt{2\mathrm{KL}/\sigma_n^2}\) this is \(\sqrt{2\sigma_n^2\mathrm{KL}}\) (\(\mathrm{KL}=0\) forces \(\pi=p_0\), gap 0).
Apply to \(\pi_K\), whose gap is \(\gamma\), and Theorem B. \(\square\)

Algebraic identity given the cited proxy. \(v(p)\le\tfrac14\) because \(\ln\frac{1-p}p\ge2(1-2p)\) for
\(p<\tfrac12\) (\(\ln\frac{1+x}{1-x}\ge2x\)); \(v(p)\ge p(1-p)\) from the \(t\to0\) expansion. Finite checks
(grid \(n\in\{1,2,4,8,16,64\}\), \(K\in\{2,3,5,10,20\}\), \(p\in\{\tfrac14,\tfrac12,\tfrac34\}\), 90 cells,
tolerance \(10^{-12}\), KL as rationals times logarithms, \(\gamma\) exact via `selection_inflation`):
\(\gamma\le\sqrt{2\sigma_n^2\mathrm{KL}}\le\sqrt{2\sigma_n^2\lambda_K}\le\) the Hoeffding version on every cell;
the Kearns–Saul inequality holds on the \(t\)-grid \(|t|\le20\), step 0.05, for the three \(p\). Largest
\(\gamma/\sqrt{2\sigma_n^2\mathrm{KL}}\) on the grid: 0.99993 (\(n=1,K=5,p=\tfrac14\)); largest
\(\gamma/\sqrt{2\sigma_n^2\lambda_K}\): 0.9192 (\(n=64,K=20,p=\tfrac12\)).

## 4. Question D (uniformity)

Write \(r(n,K,p)=\gamma(n,K,p)/(\sigma_n\sqrt{2\lambda_K})\), \(M_K\) the maximum of \(K\) i.i.d. standard
normals, \(c_K=\mathbb E[M_K]/\sqrt{2\lambda_K}\).

**D.1 (fixed \(n\), \(K\to\infty\)).** \(\gamma\le1-p\) since \(\bar S\le1\), while
\(\sigma_n\sqrt{2\lambda_K}\to\infty\); so \(r\to0\). Algebraic identity. The approach is not monotone in
\(K\): at \(n=1,p=\tfrac14\), \(r=0.63,0.74\) at \(K=2,3\); the envelope \((1-p)/(\sigma_n\sqrt{2\lambda_K})\) is.

**D.2 (Gaussian regime).** For fixed \(K\) and \(p\), \(\sqrt n\,\gamma(n,K,p)\to\sqrt{p(1-p)}\,\mathbb E[M_K]\)
and \(r(n,K,p)\to c_K\sqrt{p(1-p)/v(p)}\le c_K\), with equality at \(p=\tfrac12\). *Proof.*
\(\sqrt n\gamma=\sqrt{p(1-p)}\,\mathbb E\max_kZ_{n,k}\) with \(Z_{n,k}\) the standardized counts, independent
across \(k\); \((Z_{n,1},\dots,Z_{n,K})\to(Z_1,\dots,Z_K)\) jointly in law (de Moivre–Laplace), \(\max\) is
continuous, and \(|\max_kZ_{n,k}|\le\sum_k|Z_{n,k}|\) is bounded in \(L^2\) (\(\mathbb E Z_{n,k}^2=1\)), hence
uniformly integrable, so expectations converge. Divide by \(\sigma_n\sqrt{2\lambda_K}=\sqrt{v(p)/n}\sqrt{2\lambda_K}\). \(\square\)

**D.3 (\(c_K<1\) for \(K\ge2\); \(c_K\to1\)).** *Strict:* the Gaussian best-of-\(K\) is itself a point of a KL
ball. Its law has density \(K\Phi^{K-1}\varphi\), and Theorem B's computation (ii) with \(\tilde F=\Phi\) gives
\(\mathrm{KL}(\cdot\|N(0,1))=\lambda_K\) exactly; \(N(0,1)\) is 1-sub-Gaussian with equality, so Theorem C's
steps (2)–(3) give \(\mathbb E[M_K]\le\sqrt{2\lambda_K}\), with equality only if the law is the tilt
\(N(t,1)\), i.e. \(K\Phi^{K-1}\propto e^{tx}\), impossible since the left side is bounded. *Limit:*
\(\mathbb E[M_K]\le\sqrt{2\ln K}\) (the maximal inequality of multigen Prop. 5 at \(\lambda=\sqrt{2\ln K}\)).
For \(\varepsilon\in(0,1)\) and \(x=(1-\varepsilon)\sqrt{2\ln K}\), \(1-\Phi(x)\ge\frac{x}{1+x^2}\varphi(x)\), so
\(P(M_K\le x)=\Phi(x)^K\le\exp(-K(1-\Phi(x)))\le\exp(-K^{1-(1-\varepsilon)^2}x/((1+x^2)\sqrt{2\pi}))\to0\),
and \(\mathbb E[M_K]\ge x\,P(M_K>x)-\mathbb E[Z^-]\) gives \(\liminf\mathbb E[M_K]/\sqrt{2\ln K}\ge1-\varepsilon\).
Since \(\sqrt{2\lambda_K}/\sqrt{2\ln K}\to1\), \(c_K\to1\). \(\square\) (The refined expansion
\(\mathbb E[M_K]=\sqrt{2\ln K}-\frac{\ln\ln K+\ln4\pi-2\gamma_E}{2\sqrt{2\ln K}}+o((\ln K)^{-1/2})\) is cited,
not used; it puts \(1-c_K\) at order \((\ln\ln K+\ln4\pi-2\gamma_E-2)/(4\ln K)\), a slow approach.)

Numerically (`gaussian_max_expectation`: composite Simpson on \([-12,12]\), step \(1/2000\), two integral
forms agreeing to \(10^{-9}\); \(K=2,3,4\) match \(1/\sqrt\pi\), \(3/(2\sqrt\pi)\), \(6\arctan\sqrt2/\pi^{3/2}\)):

| \(K\) | 2 | 3 | 5 | 10 | 100 | 1000 | 10000 |
|---|---:|---:|---:|---:|---:|---:|---:|
| \(\mathbb E[M_K]\) | 0.56419 | 0.84628 | 1.16296 | 1.53875 | 2.50759 | 3.24144 | 3.85162 |
| \(\sqrt{2\lambda_K}\) | 0.62153 | 0.92946 | 1.27235 | 1.67486 | 2.68893 | 3.43766 | 4.05227 |
| \(c_K\) | 0.90775 | 0.91051 | 0.91403 | 0.91873 | 0.93256 | 0.94292 | 0.95048 |

**Answer.** \(\sup_{n,K,p}r(n,K,p)=1\), not attained: \(r\le\sqrt{\mathrm{KL}(\pi_K\|p_0)/\lambda_K}<1\) on every
finite cell (Theorems B, C), while \(r(n,K,\tfrac12)\to c_K\to1\) along \(n\to\infty\) then \(K\to\infty\). No
constant below 1 bounds the ratio uniformly in \(K\); the crosswalk's 0.91–0.92 was the \(M\le81\) stretch of a
sequence that creeps to 1. For each fixed \(K\) the Gaussian limit \(c_K\) is the per-\(K\) bound observed: on
the grid every \(r(n,K,p)<c_K\) (finite verified; largest 0.9192 at \(K=20\) against \(c_{20}=0.9232\)), and at
\(K\in\{2,5\}\), \(n\in\{64,256,1024\}\), \(p=\tfrac12\), \(\sqrt n\gamma\) approaches \(\mathbb E[M_K]/2\) with
shrinking error while \(r\) rises toward \(c_K\) from below (0.90598, 0.90731, 0.90764 → 0.90775 at \(K=2\)).
That \(\sup_nr(n,K,\tfrac12)=c_K\) for every \(K\), i.e. a monotone approach, is not proved.

**D.4 (\(n=1\): the gap equals the KL-ball supremum).** On two points every law \(\pi\ll p_0\) with
\(0<\pi(1)<1\) is the tilt \(p_0^{tS}\), \(t=\ln\frac{\pi(1)(1-p)}{(1-\pi(1))p}\). \(\mathbb E_\pi[\bar S]=\pi(1)\)
is increasing in \(\pi(1)\) and \(\mathrm{KL}(\pi\|p_0)\) is strictly convex in \(\pi(1)\), zero at \(p\), hence
increasing on \([p,1]\); so \(\sup\{\mathbb E_\pi\bar S:\mathrm{KL}(\pi\|p_0)\le\lambda\}\) is attained at the
unique \(\pi(1)\ge p\) with \(\mathrm{KL}=\lambda\). With \(\lambda=\mathrm{KL}(\pi_K\|p_0)\) and
\(\pi_K(1)=1-(1-p)^K\ge p\), that law is \(\pi_K\) itself, and the supremum minus \(p\) is \(\gamma(1,K,p)\). \(\square\)
Algebraic identity; checked to \(10^{-9}\) against the tilt bisection for \(K\in\{2,3,5,10,20\}\),
\(p\in\{\tfrac14,\tfrac12,\tfrac34\}\). For \(n\ge2\) the chain \(\gamma<\sup<\sqrt{2\sigma_n^2\mathrm{KL}}\) is
strict on the 18 cells tried (\(n\in\{2,4,8\}\), \(K\in\{2,5\}\)), as expected since \(m_K/q\) is not exponential
in the score there (\(n=2,K=2,p=\tfrac12\): likelihood ratios \(\tfrac14,1,\tfrac74\)).

## 5. Evidence status and what remains

- *Algebraic identities, every parameter:* Theorems A, B (with strictness and the supremum), C given the proxy; D.1–D.4.
- *Finite verified examples:* the 90-cell grid for B and C; five tie fixtures and \(\{0,1\}^{n\le6}\) for A;
  the jitter stand-in and uniform supports for B; the \(c_K\) table; \(r<c_K\) on the grid and the \(n\le1024\)
  approach; the strict chain at \(n\ge2\).
- *Cited, not reproved:* the Kearns–Saul inequality (checked on a \(t\)-grid only) and its optimality (attributed,
  unchecked, to Buldygin and Moskvichova 2013 or Berend and Kontorovich 2013); Hoeffding's lemma; de
  Moivre–Laplace; the refined extreme-value expansion (remark only).
- Beirami et al.'s bound is no longer load-bearing: Theorem B derives the tie-free value and extends it to the
  tied case, which the crosswalk had left undetermined.
- Open: whether \(r(n,K,\tfrac12)\uparrow c_K\) monotonically in \(n\) for every \(K\); the exact-KL ratio
  \(\gamma/\sqrt{2\sigma_n^2\mathrm{KL}(\pi_K\|p_0)}\), bounded by 1 (Theorem C) and reaching 0.99993 at \(n=1\),
  was not studied further; everything is under the Spiral null, and the drift chain (crosswalk §8 item 2) is untouched.
