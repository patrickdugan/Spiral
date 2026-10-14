# Best-of-K inside the KL slice: tie rules, containment, the DV bound

Draft 0.4 — 2026-10-14 (0.1–0.2 on 2026-10-13; 0.3 added the \(K\ge4\) paragraphs of D.5: pair-of-pairs identities, the two
obstructions, the asymptotic margin, wider sweeps; 0.4 proves the monotone approach for \(K=4..30\) at every \(n\) by an
effective second-order bound, and fixes the index range of the \(K=2\) product). Settles item 1 of §8 of `feedback_channel_rsitopology_crosswalk.md`
and the two "not determined" sentences of its §1. Module `src/spiral_ln/evaluation_selection_kl.py`; 111 tests in `tests/test_evaluation_selection_kl.py`;
receipt `output/evaluation_selection_kl/selection_kl_v0_4.json` (65 checks, source hashes). Nothing is run against a model.
Evidence levels follow the calculus card (§11): *algebraic identity* (proved for every parameter), *finite verified example*
(checked on enumerated cells), *cited* (taken from the literature, not reproved). Rationals are exact; logarithms, square
roots and one quadrature are floats under tolerance \(10^{-12}\) (\(10^{-9}\) for the KL-ball supremum and the quadrature);
the 0.4 bounds use rational enclosures of \(e^{-x}\), \(\varphi\) and \(\Phi\) with directed rounding, so they are exact rational upper bounds.

```powershell
$env:PYTHONPATH = "src"
python scripts/verify_evaluation_selection_kl.py --output output/evaluation_selection_kl/selection_kl_v0_4.json
python scripts/verify_evaluation_selection_kl.py --heavy   # adds K = 31..40 and the K = 41..50 tails (several minutes more)
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
D.5 proves the monotone approach, hence \(\sup_nr(n,K,\tfrac12)=c_K\), for \(K=2,3\) in closed form and (0.4) for \(K=4..30\) by an effective
second-order bound (\(K=31..40\) with the heavy run), and verifies it exactly on finite ranges beyond.

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

**D.5 (monotone approach in \(n\); versions 0.2–0.4).** Let \(X_k\sim\mathrm{Bin}(n,\tfrac12)\) i.i.d., \(Y_k=X_k-n/2\) (symmetric about 0), \(M_n(K)=\mathbb E\max_kY_k=n\gamma(n,K,\tfrac12)\), \(a_n(K)=M_n(K)/\sqrt n=\sqrt n\,\gamma\). Then \(r(n,K,\tfrac12)=2a_n(K)/\sqrt{2\lambda_K}\), so \(r\) is monotone in \(n\) iff \(a_n^2=M_n^2/n\) is: a comparison of rationals (`scaled_gap_squared`, integer arithmetic, cross-checked against `selection_inflation`).
*Theorem (\(K=2\)).* \(a_n(2)^2=n\binom{2n}n^2/(4\cdot16^n)\), \(a_{n+1}(2)^2/a_n(2)^2=(2n+1)^2/(4n(n+1))=1+1/(4n(n+1))>1\), and \(a_n(2)\uparrow1/(2\sqrt\pi)=\mathbb E[M_2]/2\); so \(r(n,2,\tfrac12)\) increases strictly to \(c_2\) and \(\sup_n=c_2\). *Proof.* \(\max(X_1,X_2)=\frac{X_1+X_2}2+\frac{|X_1-X_2|}2\) and \(X_1-X_2+n=X_1+(n-X_2)\sim\mathrm{Bin}(2n,\tfrac12)\), so \(M_n(2)=\tfrac12\mathbb E|S-n|\), \(S\sim\mathrm{Bin}(2n,\tfrac12)\).
De Moivre: \(\mathbb E|S-n|=2\sum_{s>n}(s-n)\binom{2n}s4^{-n}\) with \(s\binom{2n}s=2n\binom{2n-1}{s-1}\), \(\sum_{s>n}\binom{2n-1}{s-1}=2^{2n-2}\), \(\sum_{s>n}\binom{2n}s=(4^n-\binom{2n}n)/2\), so \(\mathbb E|S-n|=n\binom{2n}n/4^n\) (enumerated for \(n\le30\); the denominator is \(4^n\), not \(2^{2n-1}\)). Hence the closed form; with \(\binom{2n+2}{n+1}/\binom{2n}n=2(2n+1)/(n+1)\) the step ratio is \(\frac{n+1}n\big(\frac{2n+1}{2n+2}\big)^2=\frac{(2n+1)^2}{4n(n+1)}\), above 1 by the \(+1\) in \((2n+1)^2=4n(n+1)+1\). Telescoping from \(a_1(2)^2=\tfrac1{16}\), \(a_n(2)^2=\frac1{16}\prod_{1\le j<n}\frac{(2j+1)^2}{(2j)(2j+2)}\uparrow\frac1{16}\cdot\frac4\pi\) (Wallis; 0.3 wrote \(\prod_{j<n}\), whose \(j=0\) factor has a zero denominator). \(\square\) Checked exactly for \(n\le200\); \(4n(1-4\pi a_n^2)=0.99937\) at \(n=200\).
*Theorem (\(K=3\)).* \(M_n(3)=\tfrac32M_n(2)\), so \(a_n(3)\uparrow3/(4\sqrt\pi)\) strictly and \(\sup_nr(n,3,\tfrac12)=c_3\). *Proof.* Deleting one of \(m\) draws uniformly at random, \(\mathbb EY_{(r:m-1)}=\frac{m-r}m\mathbb EY_{(r:m)}+\frac rm\mathbb EY_{(r+1:m)}\); at \(m=3,r=2\): \(\mathbb EY_{(2:2)}=\frac13\mathbb EY_{(2:3)}+\frac23\mathbb EY_{(3:3)}\), and the median of three symmetric draws has mean 0. \(\square\) The same recurrence gives \(M_n(5)=\tfrac52(M_n(4)-M_n(2))\) (checked exactly, \(n\le200\)): odd \(K\) reduce to even \(K\), which are independent quantities.
*Finite results, version 0.2 (\(a_{n+1}^2\) against \(a_n^2\) as rationals; superseded by the 0.3 sweeps below).* Monotone for \(K\in\{3,4,5,10,20\}\), \(n\le200\); smallest step ratio always at \(n=200\): 1.0000062 (\(=160801/160800\), \(K=3\)), 1.0000067, 1.0000074, 1.0000102, 1.0000140. Also \(K=2..30,40,50,100\) at \(n\le100\) and \(K=1000\) at \(n\le40\). The normalized margin \(\mu_n=4n(n+1)(a_{n+1}^2/a_n^2-1)=4n(\rho_n-1)+\rho_n^2\) is 1 for \(K=2,3\);
\(a_n<\mathbb E[M_K]/2\) throughout, \(a_{200}=0.42288,0.51434,0.58105,0.76859,0.93243\) against limits \(0.42314,0.51469,0.58148,0.76938,0.93374\), with \(n(\mathbb E[M_K]/2-a_n)\approx0.053,0.070,0.086,0.158,0.262\).
*General \(K\).* Adding a fair bit to every count raises the maximum by one iff a candidate at the maximum draws 1, so \(M_{n+1}-M_n=\tfrac12-\mathbb E[2^{-N_n}]\), \(N_n\) the number of candidates at the maximum (identity, enumerated; \(\mathbb E2^{-N}=\sum_m[\bar F(m)^K-F(m-1)^K]\), \(\bar F\) the midpoint CDF, which is \(\mathrm{Bin}(n+1,\tfrac12)\)'s). With \(\rho_n=2n(M_{n+1}-M_n)/M_n\): \(a_{n+1}^2>a_n^2\iff\rho_n+\rho_n^2/(4n)>1\). The sufficient \(\rho_n\ge1\) (\(M_n(K)/M_n(2)\) non-decreasing) holds with equality for \(K=2,3\) and strictly on every cell swept (minimum 1.000103 at \(K=4,n=200\)), but is unproved: \(\rho_n\to1\) for every \(K\) because \(\binom K2\int\varphi^2\Phi^{K-2}=\mathbb E[M_K]/2\) (parts), so the question is second order in \(1/n\).
The natural route, \(Z_n\le_{cx}Z_{n+1}\) for standardized counts, is false at every step: \(\mathbb E|Z_{2k}|=\sqrt{2k}\binom{2k}k4^{-k}<\mathbb E|Z_{2k+1}|=\sqrt{2k+1}\binom{2k}k4^{-k}>\mathbb E|Z_{2k+2}|\) (exact) and a stop-loss \((x-c)^+\) separates every pair \(n\le60\) (floats, excess \(\ge3.3\times10^{-3}\)). \(K=2\) escapes the parity oscillation because \(X_1-X_2\) is a \(\mathrm{Bin}(2n)\), always of even order. Status in 0.3: theorem for \(K=2,3\); finite verified example for the rest (0.4: see the last paragraphs of D.5).
*\(K\ge4\), version 0.3: the overlap profile.* Write \(w_m=F_n(m)(1-F_n(m))=P(X\le m<X')\), \(m<n\). Since \(F_n(n-1-m)=1-F_n(m)\), \(M_n(K)=\sum_{m<n}[F_n(m)-F_n(m)^K]=\sum_mP_K(w_m)\) with \(2P_K(u(1-u))=1-u^K-(1-u)^K\) (Newton: \(P_2=w\), \(P_3=\tfrac32w\), \(P_4=2w-w^2\), \(P_5=\tfrac52(w-w^2)\); `tie_polynomial`, checked against `centered_max`, \(n\le40\), \(K\le12\)). With \(S_j=\sum_mw_m^j\): \(M_n(2)=S_1\), \(M_n(4)=2S_1-S_2\), and the pair-of-pairs step of R1, \(M_n(4)=M_n(2)+\tfrac12\mathbb E|Y-Y'|\) with \(Y\) the max of two, has \(\mathbb E|Y-Y'|=2\sum_mF_Y(1-F_Y)=2(S_1-S_2)\): the double sum collapses (identity, \(n\le60\)); also \(\mathbb EY_{(3:4)}=3S_2\) (enumerated, \(n\le4\)). The step \(n\to n+1\) replaces \(F_n\) by the midpoints of \((0,F_n,1)\), so \(v_m=\tfrac12(w_{m-1}+w_m)+\tfrac14q_m^2\), and with the local sums \(L_1=\sum_mq_m^2\), \(L_2=\sum_mq_m^2w_m\), \(L_4=\sum_mq_m^4\): \(S_2^{(n+1)}-S_2^{(n)}=\tfrac14(6L_2-L_1)+\tfrac5{16}L_4\) and \(M_{n+1}(4)-M_n(4)=\tfrac34L_1-\tfrac32L_2-\tfrac5{16}L_4\) (identities, \(n\le60\)). Hence \(\rho_n(4)\ge1\iff S_2\ge n[3L_2+\tfrac58L_4-\tfrac12L_1]\), the \(K=4\) analogue of de Moivre's \(S_1=\tfrac n2L_1\) — but an inequality, not an identity.
*Why R1 fails.* \(S_2=\mathbb EY_{(3:4)}/3\) is not a local sum, \(L_4=\sum_m\binom nm^4/16^n\) is a Franel-type sum (numerators 1, 2, 18, 164, 1810), and the step ratio \(M_{n+1}(4)/M_n(4)\) is not a rational function of \(n\): the linear system \(p(n)=r_ns(n)\) has full column rank for every degree \(\le6\) (exact; at degree 1 the system is solved by \((2n+1)/(2n)\) for \(K=2,3\)), and likewise for \(\mathbb E|Y-Y'|\). What exists instead: \(u_n=2^{4n+1}M_n(4)\) satisfies an order-4 recurrence with degree-8 integer coefficients (nullity one on 53 terms, verified for \(n\le300\); none of order \(\le3\) through degree 12), characteristic polynomial \((x-16)^2(x+2)(x+4)\) — the double root carries \(16^n\sqrt n\), the roots \(-2,-4\) are exponentially small parity terms. So the \(K=2\) telescoping has no analogue; a proof would be an order-4 interval induction on that recurrence, not attempted. \(K=5\) is equivalent to \(K=4\) (\(D_n(5)=\tfrac52D_n(4)\), below); 0.3's claim that \(K=8\) inherits the status of \(K=4\) was wrong: \(P_8=4w-10w^2+8w^3-w^4\) brings in \(S_3,S_4\), and the constant fit \(M_n(8)=aM_n(4)+bM_n(2)\) through \(n=1,2\) (\(a=\tfrac{1701}{256}\), \(b=-\tfrac{9875}{1024}\)) fails at every \(n=3..8\) (exact).
*Why R2 fails.* \(\tfrac12-2^{-j}\ge\tfrac14\) for \(j\ge2\) gives \(M_{n+1}-M_n\ge P(N_n\ge2)/4\), so \(nP(N_n\ge2)\ge2M_n\) would prove \(\rho_n\ge1\); \(P(N\ge2)=\sum_m[F(m)^K-F(m-1)^K-Kq_mF(m-1)^{K-1}]\) and \(P(N=j)=\sum_m\binom Kjq_m^jF(m-1)^{K-j}\) (exact, enumerated). The bound is an identity for \(K=2\) (\(N\le2\)) and fails at every \(n\) for \(K=3\), where \(\rho_n=1\): by \(m\to n-m\), \(P(N\ge2)=\tfrac32\sum q_m^2-\tfrac12\sum q_m^3\), so \(nP(N\ge2)-2M_n(3)=-\tfrac n2\sum_mq_m^3<0\) exactly (\(-\tfrac18,-\tfrac5{32},-\tfrac{21}{128},\dots\); \(n\le60\)); it fails for \(K=4\) too (\(-\tfrac18,-\tfrac{17}{64},\dots\)). The lost mass is the extra \(\tfrac18\) on triple ties, and restoring the weights \(\tfrac12-2^{-j}\) returns the increment identity itself.
*The asymptotic margin.* Continuity-corrected Edgeworth at \(p=\tfrac12\): \(F_n(m)=\Phi(z)+\varphi(z)(z^3-z)/(12n)+O(n^{-2})\), \(z=(2m+1-n)/\sqrt n\) (lattice plus kurtosis terms); the midpoint sum of \(\varphi_K\circ\Phi\), \(2\varphi_K(u)=1-u^K-(1-u)^K\), has exponentially small error (Poisson), so \(M_n(K)=\tfrac{\sqrt n}2\mathbb E[M_K]-\mathbb E[M_K^3-M_K]/(24\sqrt n)+O(n^{-3/2})\), \(\mu_n\to\mu_\infty(K)=\tfrac23\mathbb E[M_K^3-M_K]/\mathbb E[M_K]\) and \(n(\rho_n-1)\to c(K)=(\mu_\infty-1)/4=(\mathbb E[M_K^3]-\tfrac52\mathbb E[M_K])/(6\mathbb E[M_K])\). Cited expansion, not reproved; three checks: \(\mathbb E[M_2^3]=\tfrac52\mathbb E[M_2]=5/(2\sqrt\pi)\) reproduces the exact \(1/(8n)\) deficit of the \(K=2\) theorem, \(\mathbb E[M_3^3]=15/(4\sqrt\pi)\) gives \(c(3)=0\) as the odd reduction demands (both to \(10^{-9}\)), and Richardson extrapolation of the exact \(n(\rho_n-1)\) from \(n=399,400\) matches the quadrature \(c(K)\) to \(4.5\times10^{-8}\) at \(K=4\) and to relative \(3.5\times10^{-5}\) for every \(K\le100\). \(c(K)>0\) and increasing for \(K=4..100\): \(c(4)=0.020561\), \(c(5)=0.045497\), \(c(10)=0.15910\), \(c(20)=0.30889\), \(c(100)=0.72699\), \(c(10^4)=2.1031\); \(\mu_\infty(4)=1.08224\). So the open inequality holds for all large \(n\) at every \(K\ge4\) in the sense of the expansion, with the slimmest case \(K=4\); what is missing is a uniform statement for small \(n\). (0.4 proves the expansion of the margin with explicit remainders, so for the margin this paragraph is no longer cited.)
*Sweeps, version 0.3 (exact integer comparison of \(nM_{n+1}^2\) with \((n+1)M_n^2\); `wide_monotonicity_sweep`).* \(a_{n+1}^2>a_n^2\) and \(\rho_n>1\) for \(K=4..100\), \(n\le400\), and for \(K\in\{200,500,1000,10^4\}\), \(n\le60\). Smallest margin anywhere: \(\mu_{400}(4)=1.08262\) (\(\rho_{400}(4)=1.0000516\)), above its limit 1.08224; at \(n=400\) the margin exceeds \(\mu_\infty(K)\) for every \(K\le100\) (approach from above: \(n(\rho_n-1)-c(K)\approx0.028/n\) at \(K=4\)). The minimum over \(n\) sits at \(n=400\) for \(K=4..19\) (and for 28–36, 62–70) and near \(n\approx\log_2K\) otherwise, where a wobble dips below \(\mu_\infty\) but never below 2: \(K=20\): 2.207 at \(n=4\); 50: 2.621 at 5; 100: 2.826 at 6; 200: 2.956 at 7; 500: 4.368 at 8; 1000: 4.615 at 9; \(10^4\): 3.965 at 13. Status in 0.3: theorem for \(K=2,3\); for every \(K\ge4\) a finite verified example on these ranges plus a cited asymptotic with positive limit margin. These sweeps are the "exact below" half of the 0.4 proof.
*\(K\ge4\), version 0.4: the margin identity.* Write \(D_n(K)=2n(M_{n+1}-M_n)-M_n=M_n(\rho_n-1)\), so \(\rho_n\ge1\iff D_n\ge0\), and \(H_K(u)=\tfrac K2u(1-u)-\varphi_K(u)\), \(2\varphi_K(u)=1-u^K-(1-u)^K\), so \(M_n(K)=\tfrac K2S_1-\sum_{m<n}H_K(F_n(m))\) and \(H_K=\tfrac K2w-P_K(w)=O(w^2)\): \(H_2=H_3=0\), \(H_4=w^2\), \(H_5=\tfrac52w^2\) (`excess_polynomial`). The points \(F_n(m)\) evolve by midpoint insertion, \(F_{n+1}(m)=\mu_m=\tfrac12(F_n(m-1)+F_n(m))\), so for a polynomial \(h\) with \(h(0)=h(1)=0\), Taylor's formula at \(\mu_m\) gives \(\sum_{m\le n}h(\mu_m)-\sum_{m<n}h(F_n(m))=-\sum_m\sum_{k\ge1}h^{(2k)}(\mu_m)(q_m/2)^{2k}/(2k)!\); de Moivre's \(2n(S_1(n+1)-S_1(n))=S_1(n)\) removes the \(\tfrac K2S_1\) part, leaving
\[D_n(K)=\sum_{m<n}H_K(F_n(m))+2n\sum_{m\le n}\sum_{k\ge1}\frac{H_K^{(2k)}(\mu_m)\,q_m^{2k}}{4^k(2k)!}\]
(identity; `margin_deficit_from_excess`, exact for \(n\le12\) and eight \(K\)). For \(K=4\) it is 0.3's \(D_n=S_2-nT_n\); for \(K=5\) it gives \(D_n(5)=\tfrac52D_n(4)\) (exact, \(n\le60\)). The first sum decays like \(F^2\) in the tails and every local term carries \(q_m^2\), which is what makes an effective bound possible.
*The three lemmas* (\(n\ge N_1=400\); \(\Delta=2/\sqrt n\), \(z_j=(2j-n)/\sqrt n\), \(b_m=z_m+\Delta/2\); every constant an exact rational upper bound, `cdf_and_midpoint_constants`). **L** (local; Robbins 1955, \(\tfrac1{12k+1}<\ln k!-(k+\tfrac12)\ln k+k-\tfrac12\ln2\pi<\tfrac1{12k}\), *cited*): for \(|z_j|\le\sqrt n/2\), \(q_j=\Delta\varphi(z_j)(1+p(z_j)/n+e_j)\), \(p=\tfrac{z^2}2-\tfrac{z^4}{12}-\tfrac14\), \(|e_j|\le(|p_2|+\tfrac1{18})/n^2+e_3/n^3\) with \(p_2=\tfrac{p^2}2-\tfrac{z^6}{30}+\tfrac{z^4}4-\tfrac{z^2}3\) and \(e_3\) an explicit even polynomial with non-negative coefficients, and \(q_j\le\Gamma\Delta\varphi(z_j)\), \(\Gamma<1.003\) (the \(\tfrac1{18}\) is Robbins' \(\tfrac1{144k^2}\) slack; the rest are tails of the positive series of \((1\pm t)\ln(1\pm t)\) and \(\ln(1-t^2)\) and a cubic exponential remainder). **F** (CDF): for \(|b_m|\le\sqrt n/2-4/\sqrt n\), \(|F_n(m)-\Phi(b_m)-\psi(b_m)/n|\le R_F/n^2\), \(\psi=\varphi(b^3-b)/12\), \(R_F=0.355761\). The midpoint Euler–Maclaurin formula \(\sum\Delta h(c)=\int h-\tfrac{\Delta^2}{24}[h']+\tfrac{7\Delta^4}{5760}[h''']-\int K_6h^{(6)}\), \(0\le K_6\le\Delta^6/15360\) (kernel \(\tfrac{7a^2}{11520}-\tfrac{a^4}{576}+\tfrac{a^6}{720}\) in the distance \(a\) to the cell edge; identity, exact on quintics), applied to \(\varphi(1+p/n)\) from \(z=-\sqrt n/2\), produces \(\Phi(b)+\psi(b)/n\) exactly; \(R_F\) is \(\sup_b|-\tfrac16(\varphi p)'(b)+\tfrac7{360}\varphi'''(b)|=0.0225\), \(\sum\Delta\varphi|e_j|\le0.2064+0.0603+0.0664\), third-order terms 0.0002, tails (Chernoff \(e^{-n/8}\), Gaussian) \(10^{-9}\). **M** (midpoints): \(|\mu_m-\Phi(z_m)-\chi(z_m)/n|\le R_\mu/n^2\), \(\chi=\psi-z\varphi/2\), \(R_\mu=0.433616\) (average F at \(z\pm1/\sqrt n\)). Observed at \(n=400\) and 900 (exact enclosures): \(n^2|F-\Phi-\psi/n|\le0.02777\), \(n^2|\mu-\Phi-\chi/n|\le0.0507\), L's slack \(\ge0.0555\). Integrals and suprema of \(|P(z)|\varphi^a|H^{(j)}(\Phi(z))|\) are bounded by a rigorous cell quadrature (400 cells on \([-10,10]\); \(e^{-x}\), \(\varphi\), \(\Phi\) enclosed in integer fixed point with directed rounding — series for \(|t|\le6\), Mills' ratio beyond; exact Taylor shifts for \(P\); interval or mean-value forms of the closed derivatives \(H^{(j)}=\tfrac{K^{(j)}}2(u^{K-j}+(-1)^j(1-u)^{K-j})\), \(j\ge3\)) plus Gaussian tails; grid sums of non-negative majorants by \(\sum h\le\tfrac{\sqrt n}2\int h+\int|h'|\); the five smooth main grid sums by Poisson summation (*cited*) with \(|\hat h(\xi)|\le e^{-|\xi|}\sup_{|y|\le1}\int|h(x+iy)|dx\) (contour shift; \(|\varphi(x+iy)|=\varphi(x)e^{y^2/2}\), \(|\Phi(x+iy)|\le1+\varphi(0)\sqrt e\)), errors of order \(n^2e^{-\pi\sqrt n}\).
*Theorem (version 0.4).* For every \(K\ge2\) and \(n\ge400\), \(|\sqrt n\,D_n(K)-\delta_K|\le C_K/n\), with \(\delta_K=\tfrac12[\int H_K'(\Phi)\psi+\int\varphi^2(2pH_K''(\Phi)+H_K'''(\Phi)\chi)+\tfrac1{12}\int\varphi^4H_K''''(\Phi)]\) and \(C_K\) explicit (rounded up to \(10^{-6}\), `second_order_margin_constant`): \(C_4=0.741294\), \(C_5=1.852897\), \(C_6=3.2488\), \(C_8=6.749227\), \(C_{10}=11.11855\), \(C_{15}=25.722004\), \(C_{20}=45.586835\), \(C_{25}=71.196006\), \(C_{30}=103.723039\). *Proof.* Expand the identity: \(H(F)=H(\Phi)+H'(\Phi)\psi/n+H'(\Phi)r+\tfrac12H''(\xi)(\psi/n+r)^2\) by F; \(\tfrac n4q_m^2H''(\mu_m)=\varphi^2[H''(\Phi)+(2pH''(\Phi)+H'''(\Phi)\chi)/n]+\dots\) by L and M; the \(k=2\) term is \(\tfrac1{12n}\varphi^4H''''(\Phi)+\dots\); the \(k\ge3\) terms are \(O(n^{-3/2})\) after \(q^{2k}\le q_{\max}^{2k-4}(\Gamma\Delta\varphi)^4\). The \(\sqrt n\) terms \(\tfrac{\sqrt n}2[\int H(\Phi)+\int\varphi^2H''(\Phi)]\) cancel by two integrations by parts (\(H(0)=H(1)=0\)); the \(1/\sqrt n\) terms are \(\delta_K/\sqrt n\). The remainders, on the \(n^{3/2}\) scale at \(K=4\): CDF error through \(H'\) 0.1125, quadratic Taylor term 0.0157, \(k=1\) local term 0.5797, \(k=2\) term 0.0334, Poisson remainders and tails \(<10^{-15}\); each decreases in \(n\) and is evaluated at \(n=400\). \(\square\) Algebraic identity given the cited Robbins and Poisson statements, with exact rational constants.
*Corollary (\(K=4..30\): the monotone approach at every \(n\)).* If \(N_0\ge400\) has \(D_{N_0}>0\) and \(N_0^3D_{N_0}^2>4C_K^2\), then \(\delta_K>C_K/N_0\) and \(\sqrt nD_n\ge\delta_K-C_K/n>0\) for every \(n\ge N_0\). Exact checks (`effective_threshold_search`): \(N_0=400\) for \(K=4..25\) (scaled margin \(N_0^{3/2}D_{N_0}/(2C_K)=2.864\) at \(K=4\), 2.209 at \(K=10\), 1.270 at \(K=20\), 1.0036 at \(K=25\)); for \(K=26..30\) an upward scan with \(D_n>0\) at every step stops at \(N_0=417,437,456,477,498\). With 0.3's sweep (\(\rho_n\ge1\) for \(n\le400\), \(K=4..100\)) this gives \(\rho_n(K)\ge1\) — hence \(a_n(K)^2\) strictly increasing and \(\sup_nr(n,K,\tfrac12)=c_K\), approached from below — for every \(n\ge1\) and every \(4\le K\le30\). The heavy run closes \(K=31..40\) the same way (\(N_0=520..760\)) and, for \(K=41..50\), certifies \(N_0\le 1151\) by one exact evaluation each, so there \(D_n>0\) holds for \(n\le400\) and \(n\ge N_0\) with \((400,N_0)\) unchecked. Consistency (floats, tolerance \(10^{-9}\)): \(\delta_K\) by quadrature equals \(c(K)E[M_K]/2\) for \(K=4..30\), so the proof re-derives 0.3's cited margin, though the symbolic identity \(\delta_K=(E[M_K^3]-\tfrac52E[M_K])/12\) is not proved here; the observed \(n(\sqrt nD_n-\delta_K)\) is 0.0129, 0.158, 0.416 at \(K=4,10,20\) (\(n=400,900\)), so the bound is loose by a factor 60–110 and still enough. For \(K>50\) the expansion holds with a computable \(C_K\), but the Poisson strip bound grows like \((1+\varphi(0)\sqrt e)^K\) and the exact range needed to reach \(N_0\) grows; not attempted.
*Exact-KL ratio* \(\gamma/\sqrt{2\sigma_n^2\mathrm{KL}(\pi_K\|p_0)}\) at \(p=\tfrac12\): \(K=2\) falls strictly from 0.97753 (\(n=1\)) to 0.90812 (\(n=200\)); \(K=5\) rises 0.89057→0.93185 (\(n=1\to2\)) then falls strictly to 0.91436; both stay above \(c_K\) and tend to it, since \(\mathrm{KL}\to\lambda_K\) (\(m_K/q=K\xi_m^{K-1}\), \(\xi_m\in(F(m-1),F(m))\): a Riemann sum of \(g\ln g\) with mesh \(\max_mq_m\to0\); \(\mathrm{KL}/\lambda_K=0.9979\) at \(n=200\)). Finite.

## 5. Evidence status and what remains

- *Algebraic identities, every parameter:* Theorems A, B (with strictness and the supremum), C given the proxy; D.1–D.4;
  D.5 for \(K=2,3\), the increment identity \(M_{n+1}-M_n=\tfrac12-\mathbb E2^{-N}\), the odd-\(K\) reductions, \(\mathrm{KL}\to\lambda_K\);
  (0.3) the profile polynomial \(M_n(K)=\sum_mP_K(w_m)\), \(M_n(4)=2S_1-S_2\), \(\mathbb E|Y-Y'|=2(S_1-S_2)\), \(\mathbb EY_{(3:4)}=3S_2\),
  the two increment formulas in \(L_1,L_2,L_4\), the tie-count law, and the \(K=3\) deficit \(-\tfrac n2\sum q_m^3\) of route R2;
  (0.4) the margin identity \(D_n=\sum H_K(F)+2n\sum\sum H_K^{(2k)}(\mu)q^{2k}/(4^k(2k)!)\), \(D_n(5)=\tfrac52D_n(4)\), the midpoint
  Euler–Maclaurin formula with the \(K_6\) kernel, and, given the cited Robbins and Poisson statements, the effective bound
  \(|\sqrt nD_n-\delta_K|\le C_K/n\) (\(n\ge400\)) with exact rational \(C_K\). With the exact checks below it makes D.5 a theorem at
  every \(n\) for \(K=2..30\) (\(K=31..40\) with the heavy run).
- *Finite verified examples:* the 90-cell grid for B and C; five tie fixtures and \(\{0,1\}^{n\le6}\) for A;
  the jitter stand-in and uniform supports for B; the \(c_K\) table; \(r<c_K\) on the grid and the \(n\le1024\)
  approach; the strict chain at \(n\ge2\); the D.5 sweeps (0.3: \(K=4..100\), \(n\le400\); \(K\le10^4\), \(n\le60\)), \(\rho_n>1\),
  the convex-order refutation, the exact-KL path; the rank tests (no rational step ratio for \(K=4\) through degree 6) and
  the order-4 recurrence of \(2^{4n+1}M_n(4)\) (verified \(n\le300\)); the Richardson–quadrature agreement on \(c(K)\);
  (0.4) the threshold checks \(N_0^3D_{N_0}^2>4C_K^2\) (\(N_0=400\) for \(K\le25\), scans to 498 for \(K\le30\); heavy: to 760 for \(K\le40\),
  single certificates for \(K=41..50\)), the lemma remainders at \(n=400,900\), \(\delta_K=c(K)E[M_K]/2\) by quadrature, and the
  observed deviations \(n(\sqrt nD_n-\delta_K)\); the failure of \(M_n(8)\in\mathrm{span}(M_n(4),M_n(2))\).
- *Cited, not reproved:* Robbins' two-sided Stirling bounds (H. Robbins, "A remark on Stirling's formula", *Amer. Math.
  Monthly* 62 (1955) 26–29) and the Poisson summation formula for Schwartz functions (standard; e.g. Stein and Shakarchi,
  *Fourier Analysis*, ch. 5, cited from memory), both used in 0.4; the Kearns–Saul inequality (checked on a \(t\)-grid only) and its optimality (attributed,
  unchecked, to Buldygin and Moskvichova 2013 or Berend and Kontorovich 2013); Hoeffding's lemma; de
  Moivre–Laplace; the refined extreme-value expansion (remark only); the continuity-corrected Edgeworth expansion of
  the symmetric binomial behind \(c(K)\) (its two closed-form consequences at \(K=2,3\) and the Richardson match are the checks;
  for the margin it is superseded in 0.4 by the proved expansion, up to the quadrature identity \(\delta_K=c(K)E[M_K]/2\)).
- Beirami et al.'s bound is no longer load-bearing: Theorem B derives the tie-free value and extends it to the
  tied case, which the crosswalk had left undetermined.
- Open: whether \(a_n(K)\uparrow\) in \(n\) at every \(n\) for \(K>40\). For \(K=41..50\) it is proved for \(n\le400\) and \(n\ge N_0(K)\)
  (\(N_0\le 1151\)), leaving \((400,N_0)\) to an exact scan that was not run; for \(51\le K\le100\) it is exact for \(n\le400\), and for
  \(K\in\{200,500,1000,10^4\}\) for \(n\le60\), with the expansion proved but \(\delta_K>0\) known by quadrature only. Closing it needs
  sharper Poisson strips (or a larger \(N_1\)) and longer exact scans, or a structural argument. Also open: a symbolic proof of
  \(\delta_K=c(K)E[M_K]/2\), and the de Moivre-type identity for \(S_2\) that 0.3 looked for (0.4 goes around it). The exact-KL ratio's path is recorded
  for \(K=2,5\) at \(p=\tfrac12\) only; everything is under the Spiral null, and the drift chain (crosswalk §8 item 2) is untouched.
