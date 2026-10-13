# The selection gap across generations, exactly

Draft 0.3 — 2026-10-13 (0.2: 2026-10-13; 0.1: 2026-10-12). Companion to `evaluation_feedback_insertions.md`, whose selection law
stops at one generation and whose multi-generation rows come from seeded JavaScript. This note replaces the accumulation claim
with a finite Markov chain in exact arithmetic. No model is called; nothing here is evidence about any controller. Evidence
levels follow the calculus card (§11): *algebraic identity* (every parameter), *finite verified example* (enumerated cells
only), *synthetic mechanism result* (a property of this toy chain). Version 0.2 added Props. 5–7; version 0.3 settles the
dominance question left open in §6: the naive chain is above every gated chain in true value at every generation and from every
state (Prop. 8, a theorem), while for the reported count a 972-cell exact search finds no counterexample and the standard proof
routes are shown to fail.

Source `src/spiral_ln/evaluation_feedback_multigen.py`; 142 tests in `tests/`; receipt
`output/evaluation_feedback_multigen/multigen_v0_3.json` (71 checks, source hashes, exact fractions, float renderings under
`headline`; produced with `--full-sweep`, without which the dominance sweep runs the fixed law on every cell and the other laws
on subsets). Bounds involving \(\ln\) or \(\sqrt{}\) are floats, compared with exact values under an absolute tolerance of
\(10^{-12}\).

```powershell
$env:PYTHONPATH = "src"
python scripts/verify_evaluation_feedback_multigen.py --full-sweep --output output/evaluation_feedback_multigen/multigen_v0_3.json
python -m pytest tests/test_evaluation_feedback_multigen.py -q
```

## 1. The chain: vertices, edges, policy

A reused set of \(n\) items. **State**: the incumbent's realized count \(c\in\{0,\dots,n\}\) on that set. Each generation draws
\(K\) candidates i.i.d. and independent of the incumbent, \(C_k\sim\mathrm{Bin}(n,p)\), \(M=\max_k C_k\). **Actions**: accept or
reject the best candidate. **Policy**: accept iff \(M>c+t(c)\), \(t:\{0..n\}\to\mathbb N\). **Edges**: \(c\to j\) with
probability \(P(M=j)\) for \(j>c+t(c)\); the self-loop carries \(F(c+t(c))^K\), \(F\) the binomial CDF with \(F(j)=1\) for
\(j\ge n\). The graph is a DAG of upward edges plus self-loops; its sinks \(\{c:c+t(c)\ge n\}\) are the absorbing states.
Initial state \(c_0\sim\mathrm{Bin}(n,p)\). Reported score \(c_G/n\); readout value \(p\); readout gap \(\rho_G=\mathbb
E[c_G]/n-p\). In the calculus: \(\operatorname{Repeat}_G\) of one generation with carry map "keep \(c\)", composed with
\(\operatorname{Feedback}_{s,\text{score-only}}\) whose consumer selects among candidates.

**Gate discretization.** `sim.js` accepts iff \(M>c+z\sqrt{p(1-p)/n}\,n\) with \(p=c/n\), i.e. \(M-c>z\sqrt{c(n-c)/n}\). The
difference is an integer \(d\), and \(d>x\) iff \(d\ge\lfloor x\rfloor+1\), so \(t(c)=\lfloor z\sqrt{c(n-c)/n}\rfloor\),
computed exactly as \(\lfloor\sqrt{a/b}\rfloor=\mathrm{isqrt}(ab)\,//\,b\). For \(n=16,z=3\):
\(t=(0,2,3,4,5,5,5,5,6,5,5,5,5,4,3,2,0)\). Fixture `gate_threshold`, checked by \(t^2\le z^2c(n-c)/n<(t+1)^2\) on every state
and against the real-valued rule for every integer \(d\). Algebraic identity.

## 2. Naive reuse is a running maximum

**Proposition 1.** With \(t\equiv0\), \(c_G=\max(c_0,M_1,\dots,M_G)\), the maximum of \(GK+1\) i.i.d. \(\mathrm{Bin}(n,p)\)
draws, so \(\rho_G=\) `selection_inflation(n, GK+1, p).readout_gap`. The initial incumbent is one draw because it is scored on
the reused set like every candidate; a *known* count \(c_0\) gives \(\mathbb E[\max(c_0,X)]\), \(X\) the max of \(GK\) draws
(`running_max_from_point`). *Proof.* If \(M_g>c_{g-1}\) the policy sets \(c_g=M_g=\max(c_{g-1},M_g)\); otherwise
\(c_g=c_{g-1}=\max(c_{g-1},M_g)\). Induct. Algebraic identity. The DP equals the closed form on all 18 null cells
(\(n\in\{4,8,16\}\), \(K\in\{1,2,4\}\), \(p\in\{\tfrac12,\tfrac14\}\), \(G=0..20\)); at \(n=2,K=2,G=2\) it equals literal
enumeration of all \(2^{10}\) item outcomes.

**Consequences.** (i) \(\rho_G\) is non-decreasing in \(G\): a maximum over more draws is pointwise larger. (ii) Increments are
non-increasing: \(a_{m+1}-a_m=\mathbb E[(X-M_m)^+]\) with \(M_m\) pointwise non-decreasing in \(m\). (iii)
\(P(c_G=n)=1-(1-p^n)^{GK+1}\), so for fixed \(n\) and \(0<p<1\), \(\rho_G\uparrow1-p\): bounded by the lattice, never
stationary. These are algebraic identities with the proofs above; the fixture verifies them on the enumerated cells only.

**Proposition 5 (bounds).** For every \(n,K,p,G\), with \(m=GK+1\) and \(\sigma^2=np(1-p)\),
\[\rho_G\le\sqrt{\tfrac{\ln m}{2n}}\qquad\text{and}\qquad
\rho_G\le\sqrt{\tfrac{2p(1-p)\ln m}{n}}+\tfrac{\ln m}{3n}.\]
*Proof.* \(Y_i=X_i-np\) is a sum of \(n\) centred Bernoullis, each in an interval of length one, so Hoeffding's lemma and
independence give \(\mathbb E e^{\lambda Y_i}\le e^{\lambda^2n/8}\). The maximal inequality \(\mathbb
E\max_iY_i\le\lambda^{-1}\ln\sum_i\mathbb E e^{\lambda Y_i}\) (Jensen, then \(\max\le\sum\)) gives \(\mathbb E\max_iY_i\le(\ln
m)/\lambda+\lambda n/8\), and \(\lambda=\sqrt{8\ln m/n}\) makes this \(\sqrt{n\ln m/2}\); divide by \(n\). For the second bound,
a centred variable with \(|Z|\le1\) and variance \(v\) has \(\ln\mathbb E e^{\lambda Z}\le
v(e^\lambda-1-\lambda)\le\lambda^2v/(2(1-\lambda/3))\) for \(\lambda<3\); summed over items \(v=\sigma^2\), and the same maximal
inequality with \(\lambda^{-1}=\tfrac13+\sqrt{\sigma^2/(2\ln m)}\) gives \(\sqrt{2\sigma^2\ln m}+\tfrac13\ln m\)
(Boucheron–Lugosi–Massart, Cor. 2.6). Algebraic identity. Both bounds grow without limit in \(G\) while \(\rho_G\le1-p\), so
they are loose at fixed \(n\) for large \(G\) (Hoeffding passes \(1-p\) at \(G=7,4,2\) for \(n=4,p=\tfrac12,K=1,2,4\)). At
\(p=\tfrac12\) Hoeffding equals the Gaussian scale \(\sqrt{2p(1-p)\ln m/n}\) of the old remark and Bernstein exceeds it by \(\ln
m/(3n)\); Bernstein is tighter only for small \(p(1-p)\) and \(\ln m/n\) (3 of 360 cell-generations, all at
\(p=\tfrac14,n=16,m\le3\)). Finite table (`bound_fixture`, 18 cells \(\times\) 21 generations): both bounds hold everywhere; the
ratio \(\rho_G/\sqrt{2p(1-p)\ln m/n}\) runs from 0.453 to 0.886 at \(G\in\{1,5,10,20\}\), rising in \(G\) and \(n\). The
Gaussian scale is an upper envelope on every cell, not an approximation.

## 3. Fresh blocks

**Proposition 2.** (a) If each generation scores incumbent and candidates on a fresh block and reports on a second fresh block,
the expected reported score is \(p\) at every generation: the readout block is independent of whatever selected the controller,
and under the null every controller has probability \(p\). (b) If it reports on the selection block, the reported count at
\(g\ge1\) is \(M\) if \(M>I+t(I)\), else \(I\), with \(I\sim\mathrm{Bin}(n,p)\) the incumbent's fresh count; the law does not
depend on \(g\). For \(t\equiv0\) it is \(\max(I,M)\), the maximum of \(K+1\) draws, so the gap equals `selection_inflation(n,
K+1, p)` at every \(g\ge1\) and does not accumulate. Both algebraic identities (independence, linearity); verified on 12 cells
and by enumeration at \(n=2,K=2\) in both modes. The reused chain coincides with (b) at \(G=1\) for any gate and exceeds it
strictly for \(G\ge2\) on every enumerated cell (finite check).

## 4. The gate

**Proposition 3 (false acceptance).** From state \(c\) the generation accepts with probability
\(\alpha(c)=1-F(\min(n,c+t(c)))^K\); under the null every acceptance is false, and the unconditional rate at generation \(g\) is
\(\sum_c\pi_{g-1}(c)\alpha(c)\). Algebraic identity. For \(n=16,K=4,z=3\):
\(\alpha(8)=1-(1-17/65536)^4\approx1.0\times10^{-3}\); naive \(\approx0.36\).

**Proposition 4 (gate dominance, null only).** For any \(t\ge0\), couple the gated and naive chains on the same draws. The gated
state always belongs to \(\{c_0,M_1,\dots,M_g\}\), whose maximum is the naive state; hence \(c^t_G\le c^0_G\) pointwise,
\(\rho^t_G\le\rho^0_G\), and \(\alpha^t(c)\le\alpha^0(c)\). Algebraic identity by coupling; its hypothesis is that every
candidate's law is the same whatever the history, i.e. the null. With true gains it fails and can reverse (§6). Values at
\(G=20,p=\tfrac12,n=16,K=4\): naive \(0.2947\); \(z=1\): \(0.2723\); \(z=2\): \(0.2019\); \(z=3\): \(0.1328\); expected false
acceptances \(2.34\to0.33\). \(n=8,K=2\): naive \(0.3645\), \(z=3\): \(0.0967\). The gate also creates sinks below the ceiling
(\(n=8,z=3\): states \(4..8\) absorb, a gated loop freezes), the mechanism behind the simulation's GATED arm accepting 0–2% of
generations.

## 5. Correlated candidates: the mutation chain

`sim.js` perturbs the incumbent's per-item quirks, so each candidate is correlated with the incumbent item by item. Exact model:
on each item, independently, a candidate copies the incumbent's outcome with probability \(1-q\) and redraws it as
Bernoulli(\(p\)) with probability \(q\). Marginally a candidate is still \(\mathrm{Bin}(n,p)\), with per-item correlation
\(1-q\) to the incumbent. The map from \(\sin\phi=0.2\) to \(q\) is not exact: the rotation acts on latent quirks, not on
outcomes, and no \(q\) reproduces its conditional count law.

**Proposition 6.** Given incumbent count \(c\), a candidate's count is \(c-L+U\) with \(L\sim\mathrm{Bin}(c,q(1-p))\),
\(U\sim\mathrm{Bin}(n-c,qp)\) independent, because a right item is lost iff it is redrawn and fails and a wrong item is gained
iff it is redrawn and succeeds; the law depends on the incumbent's outcome vector only through \(c\) since items are
exchangeable and the perturbation is item-symmetric, so with \(K\) conditionally i.i.d. candidates and the same policy the
process is again a Markov chain on \(c\) (`mutation_candidate_law`, `mutation_transition_kernel`). (a) \(q=1\) gives
\(\mathrm{Bin}(c,p)+\mathrm{Bin}(n-c,p)=\mathrm{Bin}(n,p)\): the independent chain, exactly. (b) \(q=0\) gives the point mass at
\(c\): nothing is ever accepted, \(\rho_G=0\). (c) For every \(q\), acceptance requires \(M>c+t(c)\ge c\), so \(c_g\) is
pointwise non-decreasing, \(\rho_G\) is non-decreasing in \(G\), and \(\rho_G\le1-p\). (d) From \(c=n-1\) a candidate reaches
\(n\) with probability \(qp(1-q(1-p))^{n-1}\), maximal at \(q=1/(n(1-p))\) and decreasing beyond it, so the kernel is not
monotone in \(q\) state by state and no coupling in \(q\) exists. All algebraic identities; (a) is checked as equality of the
whole state law on every null cell under naive and \(z=1\) policies, (b)–(d) on the same cells, and the DP matches enumeration
of outcome *vectors* at \(n=2,K=2,G=2\) and \(n=3,K=2,G=1\) (a test of the Markov-on-count claim itself). Proposition 1 has no
analogue: the candidate law moves with the state, so \(c_G\) is not a running maximum of i.i.d. draws.

**Monotonicity in \(q\), finite survey** (\(q\in\{0,\tfrac14,\tfrac12,\tfrac34,1\}\), 18 null cells, naive and \(z=1\)).
\(\rho_1\) is non-decreasing in \(q\) on every cell: correlation lowers the first-generation inflation. \(\rho_G\) is **not**
monotone in \(q\) on any naive cell (first failure at \(G=2\)–5) and on 15 of 18 gated cells; at \(G=20\) every \(q<1\) gives a
*larger* gap than \(q=1\) on every naive cell with \(n\ge8\), and \(q=\tfrac12\) does on all 18 (\(n=8,K=2,p=\tfrac12\), naive:
\(\rho_{20}=0,.455,.447,.409,.365\) for the five \(q\)). Mechanism: a mutated candidate starts from the incumbent's
already-overfit vector and need only flip one wrong item without losing a right one, so improvements keep arriving when an
independent redraw would almost never beat an inflated \(c\); the chain hill-climbs the fixed item set. The earlier boundary
remark that correlation "lowers every per-generation inflation" was wrong beyond \(G=1\). Synthetic mechanism result.

## 6. True gains: the drift chain

State \((c,i)\) with \(p(i)=\min(1,\tfrac14+i/8)\). Each candidate draws a gain multiple \(m\) from a law (constant, or one law
per generation), has probability \(p(i+m)\), and on acceptance the state becomes \((M,i+m^*)\), \(m^*\) the accepted candidate's
gain; by exchangeability \(P(M=j,m^*=m)=P(M=j)\,q_m\,\mathrm{Bin}(n,p(i+m))(j)/\mathrm{mix}(j)\). Reported \(\mathbb E[c_g]/n\),
true \(\mathbb E[p(i_g)]\), phantom share \(1-\)true gain/reported gain. Verified by enumeration of every gain draw and item
outcome at \(n=2,K=2,G=2\) (six laws, two policies); the zero-gain law reproduces the null chain exactly (test). Laws: *fixed*
\(\delta=\tfrac18\); *two-point* \(\delta=\tfrac18\) w.p. \(\tfrac14\); *decaying two-point* \(q_g=\tfrac14(\tfrac34)^{g-1}\), a
lattice analogue of the simulation's \(0.06\cdot0.95^{g-1}\). Cells \((n,K)\in\{(4,2),(4,4),(8,2),(8,4),(16,2)\}\), \(G=20\),
naive and \(z=1\). Everything below is a synthetic mechanism result on those cells unless marked otherwise.

- Two-point, naive, \(n=8,K=2\): reported \(0.778\), true \(0.420\); phantom share \(0.678\) over \(0..20\), \(0.711\) early
  half, \(0.504\) late half; late/early gain ratio reported \(0.195\), true \(0.334\). Decaying: phantom \(0.838\) whole,
  \(0.977\) late; late/early reported \(0.130\) versus true \(0.016\).
- Against `results.json`: P3 (late phantom share above one half under naive reuse) holds on every cell with \(n\le8\) for both
  laws and on all cells for the decaying law. P5 (reported late/early ratio at least twice the true one) holds only under the
  decaying schedule (about 8× here, 4× in the simulation); with constant gains the ordering reverses on every cell (an inflated
  count is beaten less often by no-gain candidates, so late acceptances are enriched for real gains): P5 is a property of the
  decaying gain scale.
- Gate ordering with true gains: fixed gain, \(z=1\) gap *above* naive on every cell (\(n=8,K=2\): \(0.347\) vs \(0.279\));
  decaying gain, gate below naive on every cell. Proposition 4 is a null result and must not be read as "gating reduces the
  gap".
- Lattice ceiling: with fixed gain at \(n=16\) the late phantom share is negative (reported score pinned near one while \(p\)
  still rises); phantom shares near the ceiling are not interpretable.

**Proposition 7 (one generation, fixed gain).** From \((c,p_{\rm inc})\) with every candidate at \(p_{\rm inc}+\delta\) and
\(M\) the max of \(K\) counts, one generation changes the gap by \(\mathbb E[((M-c)/n-\delta)\,1_{\rm accept}]\). Since
\(1\{M>c\}-1\{M>c+t\}=1\{c<M\le c+t\}\),
\[\Delta\rho_{\rm naive}-\Delta\rho_{\rm gate}=\mathbb E\big[((M-c)/n-\delta)\,1\{c<M\le c+t(c)\}\big],\]
and on the window \(1\le M-c\le t(c)\). Hence (i) \(\delta\le1/n\): integrand \(\ge0\), the gate lowers the one-generation gap
change; (ii) \(\delta\ge t(c)/n\): integrand \(\le0\), the gate raises it; (iii) otherwise the sign depends on the law of \(M\)
on the window. Algebraic identity (`one_step_gap_change`). Checked on all 270 states \((c,i<\text{top})\) of the five \(z=1\)
cells: difference equals window integral exactly and has the predicted sign everywhere (\(n=16\): 65 strictly negative, 37
zero). Case (iii) takes both signs: \(n=16,K=2,c=8,t=2, \delta=\tfrac3{32}\) gives \(-0.0015\) at \(p_{\rm inc}=\tfrac14\) and
\(+0.0025\) at \(\tfrac12\). At \(n=8,z=1\), \(t(c)\le1\) and \(\delta=\tfrac18=1/n=t/n\), so (i) and (ii) both hold, the
one-step difference is *identically zero* on all 54 states, \(\rho_1\) is the same for both policies, and the \(G=20\) ordering
(gate above) is a state-occupation effect: the gated chain lags where the gap is still positive while the naive chain nears the
corner \((n,\text{top})\) where it vanishes. At \(n=16\) case (ii) holds strictly and the gate is above naive at every
\(g\ge1\). The DP's increments \(\rho_{g+1}-\rho_g\) equal the formula summed over its state law
(`drift_gap_increment_from_one_step`, \(g\le2\), all cells).

**Chaining, finite.** Fixed gain, \(\delta\in\{\tfrac1{16},\tfrac18,\tfrac14\}\), five cells (15 pairs):
\(\delta\ge\max_ct(c)/n\) (case (ii) at every state) on 4 pairs, gate above naive at every \(g=1..20\), 76/76 later generations
agree; \(\delta\le1/n\) (case (i)) on 7 pairs, 114/133 later generations agree, the sign reversing at \(g=15\) and \(g=9\) for
\(n=4,\delta=\tfrac18,K=2,4\) and at \(g=20\) for \(n=16,\delta=\tfrac1{16}\); both cases on 4 pairs, \(\rho_1\) identical then
gate above from \(g=2\) or 3. \(G=1\) agrees on all 15 as the theorem requires; beyond that the sign need not chain.

**Proposition 8 (dominance in true value).** Fixed gain (every accepted candidate carries one lattice step; a multiple \(m\) is
the same chain on the lattice \(p_0+im\delta\)), any non-decreasing level function \(p\), any \(n,K\), any threshold rule
\(t\ge0\) (the gate or not), any starting state \(x=(c,i)\) and any non-decreasing \(\varphi\) on levels: \(\mathbb
E^t_x[\varphi(i_g)]\le\mathbb E^0_x[\varphi(i_g)]\) for every \(g\). In particular \(\mathbb E[p(i_g)]\) is ordered and the
gated level is stochastically dominated, from every initial law. *Proof.* \(P,Q\) the naive and gated kernels,
\(u_k=P^k\varphi\), \(w_k=Q^k\varphi\), \(a(c)=\min(n,c+t(c))\), \(M_\ell\) the best of \(K\) candidates at level \(\ell\)
(stochastically non-decreasing in \(\ell\)), \(F_\ell,\pi_\ell\) its CDF and law. (i) *Naive monotonicity*: \(u_k(c,i)\ge
u_k(c+1,i)\) and \(u_k(c,i+1)\ge u_k(c,i)\) for all \(k\), by downward induction on the level. The first follows from the second
at \((c+1,i)\): on the same draws the chains from \((c,i)\) and \((c+1,i)\) agree until a draw equals \(c+1\), which sends the
lower to \((c+1,i+1)\) and leaves the upper at \((c+1,i)\), so
\(u_k(c,i)-u_k(c+1,i)=\sum_sF_i(c)^{s-1}\pi_i(c+1)[u_{k-s}(c+1,i+1)-u_{k-s}(c+1,i)]\). The second follows from the first at
level \(i+2\): expand the lower chain two jumps and the upper one. The upper waits less (geometric with the larger success
probability \(1-F_{i+1}(c)\)), lands stochastically below the lower's second landing (\(M_{i+1}\,|\,{>}c\preceq
M_{i+1}\,|\,{>}x\) for the lower's first landing \(x>c\)), \(\varphi(i+1)\le\varphi(i+2)\le u(\cdot,i+2)\), and \(u(\cdot,i+2)\)
is non-increasing in the count and non-decreasing in time; a lower chain whose first landing is \(n\) keeps \(\varphi(i+1)\).
Base: at the top levels \(u_k\) is constant in \(c\), one level below it is \(\varphi+(\varphi_{\rm top}-\varphi)(1-F(c)^k)\).
(ii) *Suppressed state*: \(w_k(c,i)\le u_k(j,i+1)\) for \(c<j\le a(c)\). One gated step: the self-loop uses (ii) at \(k-1\);
each landing \(J>a(c)\ge j\) uses (iii) at \(k-1\) and then (i) to pull \(u_{k-1}(J,i+1)\) up to \(u_{k-1}(j,i+1)\);
\(u_{k-1}\le u_k\) closes. (iii) *Dominance*: on the same draws from \(x\) the chains agree until the naive one accepts a draw
\(M\in(c,a(c)]\) the gate rejects, and the remaining difference \(u_{k-s}(M,i+1)-w_{k-s}(c,i)\) is \(\ge0\) by (ii). Induct on
\(k\). Algebraic identity. In the limit it is the backward induction \(V_Q(c,i)=\mathbb E[V_Q(M,i+1)\,|\,M>a(c)]\le\mathbb
E[V_P(M,i+1)\,|\,M>a(c)] \le\mathbb E[V_P(M,i+1)\,|\,M>c]=V_P(c,i)\), the last step by (i). Checked
(`dominance_structure_fixture`) at every state and horizon \(\le25\) and in the exact limit on
\((n,K)\in\{(4,2),(8,2),(16,2),(8,4)\}\), \(\delta\in\{\tfrac1{16},\tfrac18,\tfrac14\}\), \(z\in\{1,2,3\}\) and a non-gate rule,
plus two non-uniform lattices; (i) also holds for \(\varphi=1\{i\ge\ell\}\) and for \(P(c_k\ge m)\). The naive hypothesis is
needed: for \(t=(0,2,0,0)\le t'=(1,2,0,1)\) on \(n=3,K=1\), levels \((\tfrac1{32},\tfrac5{32},\tfrac9{16},
\tfrac{23}{32},\tfrac{15}{16})\), the higher rule is ahead from \((0,0)\) in the limit (\(1483/2752\) vs \(9175/41872\): the
lower rule lands at count 1, where \(t=2\) absorbs it) and at horizon 3 from \((0,2)\).

**The count, finite only.** \(\mathbb E^0[c_\infty]=n\) whenever \(p(1)>0\), so the limit ordering is trivial. At finite
horizons: exact search (`dominance_sweep_fixture`, exact integer propagation and exact limits) over \(n\in\{4,8,16\}\),
\(K\in\{1,2,4\}\), \(z\in\{1,2,3\}\), \(\delta\in\{\tfrac1{16},\tfrac18,\tfrac14,\tfrac38\}\), \(p_0\in\{\tfrac14,\tfrac12,0\}\)
(lattices \(\tfrac14+i/8\), \(\tfrac12+i/16\), \(i/8\) and their multiples), fixed, two-point and decaying laws: 972 cells,
\(g\le100\) (stopping once both chains hold mass \(\ge1-10^{-9}\) on absorbing states), 88,171 generation comparisons of both
\(\mathbb E[c_g]\) and \(\mathbb E[p(i_g)]\), exact limits on the 648 constant-law cells: naive above gate everywhere, no
violation. On the structure cells the count ordering, its hitting form \(P(c_k\ge m)\) and the analogue of (ii) hold at every
state. No proof: the naive count iterates are not monotone in the count (\(n=4,K=2,\delta=\tfrac1{16}\): two naive steps from
\((0,0)\) give \(2.344>2.260\) from \((1,0)\), a lower count earning a free level), so (i) fails for the count, and so do the
other standard routes, each with a recorded witness: the gate-cone condition \(u_k(j,i+1)\ge u_k(c,i)\) on the naive iterates,
the policy-improvement condition \(w_k(j,i+1)\ge w_k(c,i)\) on the gated iterates and the componentwise condition \(u_k(c,i)\le
u_k(c',i')\), \(c\le c'\), \(i<i'\); the pathwise coupling fails because levels cross. Prop. 8 covers the fixed law only: a
gain-0 candidate can be accepted without raising the level and the level induction does not chain, so the two-point and decaying
rows are finite. The mutation chain of §5 has no fixed-gain version (a mutated candidate's true value leaves the lattice) and
was not searched.

## 7. The readout-gap series and the divergence flags

\(\rho_g=\mathbb E[c_g]/n-\mathbb E[p_g]\). Feeding \((g,\mathbb E[c_g]/n,\mathbb E[p_g])\) at \(g\in\{0,4,\dots,20\}\) to
`divergence_flags` with margin \(\tfrac1{40}\) flags an interval iff \(\rho_{g_1}-\rho_{g_0}>\tfrac1{40}\) (identity in the
definition). Null \(n=8,K=2\): \(\rho=(0,.147,.202,.234,.256,.273,\dots,.365)\) gives flags T,T,T,F,F, a prefix as diminishing
increments require; two-point drift matches; the fresh arm flags only the first interval. A check on means.

## 8. Boundaries

The independent chain has candidates independent of the incumbent; the mutation chain (§5) correlates them through one parameter
\(q\) and shows the correlation raising, not lowering, the accumulated gap; neither is an exact image of `sim.js`. \(n\) is
fixed; labels are clean; gains are i.i.d. across candidates; the \(p\)-lattice is capped at one, and results near the corner
\((n,\text{top})\) are timing effects. Propositions 5–8 are general (Prop. 8 for the fixed gain law and the true value); the
\(q\)-survey, the chaining counts, the two-point and decaying orderings and the count ordering are finite checks on the
enumerated cells. Results concern distributions and expectations, not sample paths; no model, agent, or observed-controller
evidence is claimed.
