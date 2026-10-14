# The selection gap across generations, exactly

Draft 0.6 — 2026-10-14 (0.5–0.2: 2026-10-13; 0.1: 2026-10-12). Companion to `evaluation_feedback_insertions.md`, whose
selection law stops at one generation and whose multi-generation rows come from seeded JavaScript. This note replaces the
accumulation claim with a finite Markov chain in exact arithmetic. No model is called; nothing here is evidence about any
controller. Evidence levels follow the calculus card (§11): *algebraic identity* (every parameter), *finite verified example*
(enumerated cells only), *synthetic mechanism result* (a property of this toy chain). 0.2 added Props. 5–7; 0.3 proved the
naive chain above every gated chain in true value (Prop. 8); 0.4 proved the count ordering (Prop. 9) and recorded why the
standard routes fail; 0.5 asked whether both survive mixed gain laws (§6) and found no counterexample on its grids; 0.6 settles
it: with one positive gain value (any chance of gain zero) both orderings are a theorem (Prop. 10), with two positive gain values
both fail (exact counterexample at \(n=3,K=1\)). Source `src/spiral_ln/evaluation_feedback_multigen.py`; 177 tests (`python -m
pytest tests/test_evaluation_feedback_multigen.py -q` with `PYTHONPATH=src`); receipt `output/evaluation_feedback_multigen/
multigen_v0_6.json` (95 checks, source hashes, exact fractions, float renderings under `headline`) from `python
scripts/verify_evaluation_feedback_multigen.py --full-sweep --output <receipt>`; without `--full-sweep` the dominance sweep, the
mixed-law fixture and the gain-support fixture run on reduced grids. Bounds involving \(\ln\) or \(\sqrt{}\) are floats, compared
with exact values under an absolute tolerance of \(10^{-12}\).

## 1. The chain: vertices, edges, policy

A reused set of \(n\) items. **State**: the incumbent's realized count \(c\in\{0,\dots,n\}\) on that set. Each generation draws
\(K\) candidates i.i.d. and independent of the incumbent, \(C_k\sim\mathrm{Bin}(n,p)\), \(M=\max_k C_k\). **Actions**: accept or
reject the best candidate. **Policy**: accept iff \(M>c+t(c)\), \(t:\{0..n\}\to\mathbb N\). **Edges**: \(c\to j\) with
probability \(P(M=j)\) for \(j>c+t(c)\); the self-loop carries \(F(c+t(c))^K\), \(F\) the binomial CDF with \(F(j)=1\) for
\(j\ge n\). The graph is a DAG of upward edges plus self-loops; its sinks \(\{c:c+t(c)\ge n\}\) are the absorbing states.
Initial state \(c_0\sim\mathrm{Bin}(n,p)\). Reported score \(c_G/n\); readout value \(p\); readout gap \(\rho_G=\mathbb
E[c_G]/n-p\). In the calculus: \(\operatorname{Repeat}_G\) of one generation (carry map "keep \(c\)") composed with
\(\operatorname{Feedback}_{s,\text{score-only}}\), whose consumer selects among candidates.

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
enumeration of all \(2^{10}\) item outcomes. **Consequences.** (i) \(\rho_G\) is non-decreasing in \(G\): a maximum over more
draws is pointwise larger. (ii) Increments are non-increasing: \(a_{m+1}-a_m=\mathbb E[(X-M_m)^+]\) with \(M_m\) pointwise
non-decreasing in \(m\). (iii) \(P(c_G=n)=1-(1-p^n)^{GK+1}\), so for fixed \(n\) and \(0<p<1\), \(\rho_G\uparrow1-p\): bounded
by the lattice, never stationary. Algebraic identities; the fixture verifies them on the enumerated cells only.

**Proposition 5 (bounds).** For every \(n,K,p,G\), with \(m=GK+1\) and \(\sigma^2=np(1-p)\),
\[\rho_G\le\sqrt{\tfrac{\ln m}{2n}}\qquad\text{and}\qquad
\rho_G\le\sqrt{\tfrac{2p(1-p)\ln m}{n}}+\tfrac{\ln m}{3n}.\]
*Proof.* \(Y_i=X_i-np\) is a sum of \(n\) centred Bernoullis in intervals of length one, so Hoeffding's lemma and independence
give \(\mathbb E e^{\lambda Y_i}\le e^{\lambda^2n/8}\); the maximal inequality \(\mathbb E\max_iY_i\le\lambda^{-1}\ln\sum_i
\mathbb E e^{\lambda Y_i}\) (Jensen, then \(\max\le\sum\)) gives \((\ln m)/\lambda+\lambda n/8\), which
\(\lambda=\sqrt{8\ln m/n}\) makes \(\sqrt{n\ln m/2}\); divide by \(n\). For the second bound, a centred \(|Z|\le1\) with
variance \(v\) has \(\ln\mathbb E e^{\lambda Z}\le v(e^\lambda-1-\lambda)\le\lambda^2v/(2(1-\lambda/3))\) for \(\lambda<3\);
summed over items \(v=\sigma^2\), and \(\lambda^{-1}=\tfrac13+\sqrt{\sigma^2/(2\ln m)}\) in the same maximal inequality gives
\(\sqrt{2\sigma^2\ln m}+\tfrac13\ln m\) (Boucheron–Lugosi–Massart, Cor. 2.6). Algebraic identity. Both grow without limit in
\(G\) while \(\rho_G\le1-p\), so they are loose at fixed \(n\) for large \(G\) (Hoeffding passes \(1-p\) at \(G=7,4,2\) for
\(n=4,p=\tfrac12,K=1,2,4\)). At \(p=\tfrac12\) Hoeffding equals the Gaussian scale \(\sqrt{2p(1-p)\ln m/n}\) of the old remark
and Bernstein exceeds it by \(\ln m/(3n)\); Bernstein is tighter on 3 of 360 cell-generations only (\(p=\tfrac14,n=16,m\le3\)).
Finite table (`bound_fixture`, 18 cells \(\times\) 21 generations): both bounds hold everywhere; \(\rho_G\) over the Gaussian
scale runs from 0.453 to 0.886 at \(G\in\{1,5,10,20\}\), rising in \(G\) and \(n\): an upper envelope, not an approximation.

## 3. Fresh blocks

**Proposition 2.** (a) If each generation scores incumbent and candidates on a fresh block and reports on a second fresh block,
the expected reported score is \(p\) at every generation: the readout block is independent of the selection, and under the
null every controller has probability \(p\). (b) If it reports on the selection block, the reported count at
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
\(\rho^t_G\le\rho^0_G\), and \(\alpha^t(c)\le\alpha^0(c)\). Algebraic identity by coupling, under the null hypothesis that
every candidate's law is history-free; with true gains it fails and can reverse (§6). Values at \(G=20,p=\tfrac12,n=16,K=4\):
naive \(0.2947\); \(z=1\): \(0.2723\); \(z=2\): \(0.2019\); \(z=3\): \(0.1328\); expected false acceptances \(2.34\to0.33\).
\(n=8,K=2\): naive \(0.3645\), \(z=3\): \(0.0967\). The gate also creates sinks below the ceiling (\(n=8,z=3\): states \(4..8\)
absorb, a gated loop freezes), behind the simulation's GATED arm accepting 0–2% of generations.

## 5. Correlated candidates: the mutation chain

`sim.js` perturbs the incumbent's per-item quirks, correlating each candidate with the incumbent item by item. Exact model: on
each item, independently, a candidate copies the incumbent's outcome w.p. \(1-q\) and redraws it as Bernoulli(\(p\)) w.p.
\(q\). Marginally a candidate is still \(\mathrm{Bin}(n,p)\), with item correlation \(1-q\). The map from \(\sin\phi=0.2\) to
\(q\) is not exact (the rotation acts on latent quirks, not outcomes, and no \(q\) matches its conditional count law).

**Proposition 6.** Given incumbent count \(c\), a candidate's count is \(c-L+U\) with \(L\sim\mathrm{Bin}(c,q(1-p))\),
\(U\sim\mathrm{Bin}(n-c,qp)\) independent (a right item is lost iff redrawn and failing, a wrong one gained iff redrawn and
succeeding); by exchangeability and item-symmetry the law depends on the incumbent's outcome vector only through \(c\), so with
\(K\) conditionally i.i.d. candidates the process is again a Markov chain on \(c\) (`mutation_candidate_law`,
`mutation_transition_kernel`). (a) \(q=1\) gives \(\mathrm{Bin}(c,p)+\mathrm{Bin}(n-c,p)=\mathrm{Bin}(n,p)\): the independent
chain, exactly. (b) \(q=0\) gives the point mass at \(c\): nothing is ever accepted, \(\rho_G=0\). (c) For every \(q\),
acceptance requires \(M>c+t(c)\ge c\), so \(c_g\) is pointwise non-decreasing, \(\rho_G\) is non-decreasing in \(G\), and
\(\rho_G\le1-p\). (d) From \(c=n-1\) a candidate reaches \(n\) with probability \(qp(1-q(1-p))^{n-1}\), maximal at
\(q=1/(n(1-p))\) and decreasing beyond it, so the kernel is not monotone in \(q\) state by state and no coupling in \(q\)
exists. All algebraic identities; (a) is checked as equality of the whole state law on every null cell (naive and \(z=1\)),
(b)–(d) on the same cells, and the DP matches enumeration of outcome *vectors* at \(n=2,K=2,G=2\) and \(n=3,K=2,G=1\) (testing
the Markov-on-count claim itself). Proposition 1 has no analogue: the candidate law moves with the state.

**Monotonicity in \(q\), finite survey** (\(q\in\{0,\tfrac14,\tfrac12,\tfrac34,1\}\), 18 null cells, naive and \(z=1\)).
\(\rho_1\) is non-decreasing in \(q\) on every cell: correlation lowers the first-generation inflation. \(\rho_G\) is **not**
monotone in \(q\) on any naive cell (first failure at \(G=2\)–5) and on 15 of 18 gated cells; at \(G=20\) every \(q<1\) gives a
*larger* gap than \(q=1\) on every naive cell with \(n\ge8\), and \(q=\tfrac12\) does on all 18 (\(n=8,K=2,p=\tfrac12\), naive:
\(\rho_{20}=0,.455,.447,.409,.365\) for the five \(q\)). Mechanism: a mutated candidate starts from the already-overfit vector
and need only flip one wrong item without losing a right one, so improvements keep arriving when an independent redraw would
almost never beat an inflated \(c\) (hill-climbing the fixed item set); the 0.1 remark that correlation lowers every
per-generation inflation was wrong beyond \(G=1\). Synthetic mechanism result.

## 6. True gains: the drift chain

State \((c,i)\) with \(p(i)=\min(1,\tfrac14+i/8)\). Each candidate draws a gain multiple \(m\) from a law (constant, or one law
per generation), has probability \(p(i+m)\), and on acceptance the state becomes \((M,i+m^*)\), \(m^*\) the accepted candidate's
gain; by exchangeability \(P(M=j,m^*=m)=P(M=j)\,q_m\,\mathrm{Bin}(n,p(i+m))(j)/\mathrm{mix}(j)\). Reported \(\mathbb E[c_g]/n\),
true \(\mathbb E[p(i_g)]\), phantom share \(1-\)true gain/reported gain. Verified by enumeration at \(n=2,K=2,G=2\) (six laws,
two policies); the zero-gain law reproduces the null chain exactly (test). Laws: *fixed*
\(\delta=\tfrac18\); *two-point* \(\delta=\tfrac18\) w.p. \(\tfrac14\); *decaying two-point* \(q_g=\tfrac14(\tfrac34)^{g-1}\), a
lattice analogue of the simulation's \(0.06\cdot0.95^{g-1}\). Cells \((n,K)\in\{(4,2),(4,4),(8,2),(8,4),(16,2)\}\), \(G=20\),
naive and \(z=1\). Everything below is a synthetic mechanism result on those cells unless marked otherwise.

- Two-point, naive, \(n=8,K=2\): reported \(0.778\), true \(0.420\); phantom share \(0.678\) over \(0..20\), \(0.711\) early
  half, \(0.504\) late half; late/early gain ratio reported \(0.195\), true \(0.334\). Decaying: phantom \(0.838\) whole,
  \(0.977\) late; late/early reported \(0.130\) versus true \(0.016\).
- Against `results.json`: P3 (late phantom share above one half under naive reuse) holds on every cell with \(n\le8\) for both
  laws and on all cells for the decaying law; P5 (reported late/early ratio at least twice the true one) holds only under the
  decaying schedule (about 8× here, 4× in the simulation) and reverses on every constant-gain cell (an inflated count is
  beaten less often by no-gain candidates, so late acceptances are enriched for real gains): P5 is a property of the decaying
  gain scale.
- Gate ordering with true gains: fixed gain, \(z=1\) gap *above* naive on every cell (\(n=8,K=2\): \(0.347\) vs \(0.279\));
  decaying gain, gate below naive on every cell. Proposition 4 is a null result and must not be read as "gating reduces the
  gap". Lattice ceiling: with fixed gain at \(n=16\) the late phantom share is negative (reported score pinned near one while
  \(p\) still rises); phantom shares near the ceiling are not interpretable.

**Proposition 7 (one generation, fixed gain).** From \((c,p_{\rm inc})\) with every candidate at \(p_{\rm inc}+\delta\) and
\(M\) the max of \(K\) counts, one generation changes the gap by \(\mathbb E[((M-c)/n-\delta)\,1_{\rm accept}]\). Since
\(1\{M>c\}-1\{M>c+t\}=1\{c<M\le c+t\}\),
\[\Delta\rho_{\rm naive}-\Delta\rho_{\rm gate}=\mathbb E\big[((M-c)/n-\delta)\,1\{c<M\le c+t(c)\}\big],\]
and on the window \(1\le M-c\le t(c)\). Hence (i) \(\delta\le1/n\): integrand \(\ge0\), the gate lowers the one-generation gap
change; (ii) \(\delta\ge t(c)/n\): integrand \(\le0\), the gate raises it; (iii) otherwise the sign depends on the law of \(M\)
on the window. Algebraic identity (`one_step_gap_change`). Checked on all 270 states \((c,i<\text{top})\) of the five \(z=1\)
cells: difference equals window integral exactly and has the predicted sign everywhere (\(n=16\): 65 strictly negative, 37
zero). Case (iii) takes both signs (\(n=16,K=2,c=8,t=2,\delta=\tfrac3{32}\): \(-0.0015\) at \(p_{\rm inc}=\tfrac14\),
\(+0.0025\) at \(\tfrac12\)). At \(n=8,z=1\), \(t(c)\le1\) and \(\delta=\tfrac18=1/n=t/n\), so both cases hold, the one-step
difference is *identically zero* on all 54 states, \(\rho_1\) agrees, and the \(G=20\) ordering (gate above) is a
state-occupation effect: the gated chain lags where the gap is still positive while the naive chain nears the corner
\((n,\text{top})\) where it vanishes. At \(n=16\) case (ii) holds strictly and the gate is above naive at every
\(g\ge1\) (the DP's increments match the formula, `drift_gap_increment_from_one_step`, \(g\le2\)). **Chaining, finite.** Fixed
gain, \(\delta\in\{\tfrac1{16},\tfrac18,\tfrac14\}\), five cells (15 pairs): case (ii) at every state on 4 pairs, gate above
naive at every \(g=1..20\) (76/76); case (i) on 7 pairs, 114/133 later generations agree, the sign reversing at \(g=15,9\)
(\(n=4,\delta=\tfrac18,K=2,4\)) and \(g=20\) (\(n=16,\delta=\tfrac1{16}\)); both cases on 4 pairs, \(\rho_1\) identical then
gate above from \(g=2\) or 3. \(G=1\) agrees on all 15 as the theorem requires; beyond that the sign need not chain.

**Proposition 8 (dominance in true value).** Fixed gain (one lattice step per acceptance; a multiple \(m\) is the same chain on
the lattice \(p_0+im\delta\)), any non-decreasing level function \(p\), any \(n,K\), any threshold rule \(t\ge0\), any state
\(x=(c,i)\) and any non-decreasing \(\varphi\) on levels: \(\mathbb E^t_x[\varphi(i_g)]\le\mathbb E^0_x[\varphi(i_g)]\) for
every \(g\). In particular \(\mathbb E[p(i_g)]\) is ordered and the gated level is stochastically dominated, from every initial
law. *Proof.* \(P,Q\) the naive and gated kernels, \(u_k=P^k\varphi\), \(w_k=Q^k\varphi\), \(a(c)=\min(n,c+t(c))\), \(M_\ell\)
the best of \(K\) candidates at level \(\ell\) (stochastically non-decreasing in \(\ell\)), \(F_\ell,\pi_\ell\) its CDF and law.
(i) *Naive monotonicity*: \(u_k(c,i)\ge u_k(c+1,i)\) and \(u_k(c,i+1)\ge u_k(c,i)\) for all \(k\), by downward induction on
the level. The first follows from the second at \((c+1,i)\): on the same draws the chains from \((c,i)\) and \((c+1,i)\) agree
until a draw equals \(c+1\), which sends the lower to \((c+1,i+1)\) and leaves the upper at \((c+1,i)\), so
\(u_k(c,i)-u_k(c+1,i)=\sum_sF_i(c)^{s-1}\pi_i(c+1)[u_{k-s}(c+1,i+1)-u_{k-s}(c+1,i)]\). The second follows from the first at
level \(i+2\): expand the lower chain two jumps and the upper one. The upper waits less (success probability \(1-F_{i+1}(c)\)
is larger), lands stochastically below the lower's second landing (\(M_{i+1}\,|\,{>}c\preceq M_{i+1}\,|\,{>}x\) for the
lower's first landing \(x>c\)), \(\varphi(i+1)\le\varphi(i+2)\le u(\cdot,i+2)\), and \(u(\cdot,i+2)\) is non-increasing in the
count and non-decreasing in time; a lower chain whose first landing is \(n\) keeps \(\varphi(i+1)\). Base: at the top levels
\(u_k\) is constant in \(c\), one level below it is \(\varphi+(\varphi_{\rm top}-\varphi)(1-F(c)^k)\). (ii) *Suppressed
state*: \(w_k(c,i)\le u_k(j,i+1)\) for \(c<j\le a(c)\). One gated step: the self-loop uses (ii) at \(k-1\); each landing
\(J>a(c)\ge j\) uses (iii) at \(k-1\) and then (i) to pull \(u_{k-1}(J,i+1)\) up to \(u_{k-1}(j,i+1)\); \(u_{k-1}\le u_k\)
closes. (iii) *Dominance*: on the same draws from \(x\) the chains agree until the naive one accepts a draw \(M\in(c,a(c)]\)
the gate rejects, and the remaining difference \(u_{k-s}(M,i+1)-w_{k-s}(c,i)\) is \(\ge0\) by (ii). Induct on \(k\). Algebraic
identity; the limit version is the backward induction \(V_Q\le V_P\), last step by (i). Checked (`dominance_structure_fixture`)
at every state, horizon \(\le25\) and in the exact limit on \((n,K)\in\{(4,2),(8,2),(16,2),(8,4)\}\),
\(\delta\in\{\tfrac1{16},\tfrac18,\tfrac14\}\), \(z\in\{1,2,3\}\) and a non-gate rule, plus two non-uniform lattices; (i) also
holds for \(\varphi=1\{i\ge\ell\}\). The naive hypothesis is needed: for \(t=(0,2,0,0)\le t'=(1,2,0,1)\) on \(n=3,K=1\), levels
\((\tfrac1{32},\tfrac5{32},\tfrac9{16},\tfrac{23}{32},\tfrac{15}{16})\), the higher rule is ahead from \((0,0)\) in the limit
(\(1483/2752\) vs \(9175/41872\): the lower rule lands at count 1, which \(t=2\) absorbs) and at horizon 3 from \((0,2)\).

**The count: search.** \(\mathbb E^0[c_\infty]=n\) whenever \(p(1)>0\), so the limit ordering is trivial. Exact search (`dominance_sweep_fixture`)
over \(n\in\{4,8,16\}\), \(K\in\{1,2,4\}\), \(z\in\{1,2,3\}\), \(\delta\in\{\tfrac1{16},\tfrac18,\tfrac14,\tfrac38\}\), \(p_0\in\{\tfrac14,\tfrac12,0\}\), fixed,
two-point and decaying laws: 972 cells, \(g\le100\) (stopping at absorbed mass \(\ge1-10^{-9}\)), 88,171 comparisons of \(\mathbb E[c_g]\)
and \(\mathbb E[p(i_g)]\), exact limits on the 648 constant-law cells: naive above gate everywhere. The fixed-law rows are now covered by
Prop. 9, the two-point rows by Prop. 10; the decaying rows remain finite; the mutation chain was not searched.

**Proposition 9 (dominance in count).** Fixed gain, any non-decreasing level function, any \(n,K\), any threshold rule
\(t\ge0\), any state \(x\) and any non-decreasing \(\psi\) on counts: \(\mathbb E^t_x[\psi(c_g)]\le\mathbb E^0_x[\psi(c_g)]\)
for every \(g\), hence from every initial law (stochastic dominance of the count); indeed one gated step followed by naive
steps is already dominated, \(QP^k\psi\le P^{k+1}\psi\). *Proof.* \(\psi\) is a non-negative
combination of \(1\{c\ge m\}\), so fix \(m\), \(u_k=P^k1\{c\ge m\}\). Under the naive rule \(c_k\ge m\) iff \(c_0\ge m\) or
some draw by generation \(k\) was \(\ge m\) (Prop. 1), so \(u_k\) is a first-passage probability; on states \(c<m\) write
\(s_k=1-u_k\), \(H(i)=1-F_{i+1}(m-1)^K\) for the probability that a draw from level \(i\) is \(\ge m\) (non-decreasing in
\(i\)), \(A=F_{i+1}(c)^K\), \(\pi(J)\) for the surviving landings \(c<J<m\), \(B=\sum\pi\), \(e_k\) the \(\pi\)-average of
\(s_k\) over them; so \(s_{k+1}(c,i)=As_k(c,i)+Be_k\). (L1, *new better than used*) \(s_{k+1}(x)\le(1-H(x))s_k(x)\), i.e.
\(e_k\le s_k(x)\): by induction on \(k\), (L1) at the landings (level \(i+1\), death rate \(H(i+1)\ge H(i)\)) gives
\(e_k\le(1-H(i+1))e_{k-1}\), and (L1) at \(x\) gives \(s_k(x)\ge(A+B)e_{k-1}=(1-H(i))e_{k-1}\ge e_k\); base \(s_1=1-H\).
(L2, *count*) \(s_k(c,i)\le s_k(c+1,i)\) for \(c+1<m\): the chains share draws and agree unless the draw equals \(c+1\), which
sends the lower to \((c+1,i+1)\) and leaves the upper at \((c+1,i)\); the difference is \(A[\cdot]_{k-1}+
\pi(c+1)[s_{k-1}(c+1,i)-s_{k-1}(c+1,i+1)]\ge0\) by (L2), (L3) at \(k-1\). (L3, *level*) \(s_k(c,i+1)\le s_k(c,i)\): with
\(\sigma_r=s_r(c,i+1)\), (L2) at level \(i+1\) bounds every surviving landing of the lower chain below by \(\sigma\), so
\(s_k(c,i)\ge R_k\), \(R_0=1\), \(R_k=AR_{k-1}+B\sigma_{k-1}\) (wait at \((c,i)\), then run the upper chain), and
\(R_k\ge(1-H(i))\sigma_{k-1}\ge(1-H(i+1))\sigma_{k-1}\ge\sigma_k\) by (L1) at \((c,i+1)\). (L4, *window*) for every
\(a\in(c,n]\), \(W_a=\sum_{c<J\le a}\pi_{i+1}(J)[u_k(J,i+1)-u_k(c,i)]\ge0\): terms with \(J\ge m\) are \(\ge0\); for the rest,
by (L2) the \(\pi\)-average of \(s_k(\cdot,i+1)\) over \((c,\min(a,m-1)]\) is at most its average over \((c,m)\), which is
\(e_k\le s_k(c,i)\) by (L1). Since \((Pf-Qf)(c,i)=W_{a(c)}\), (L4) is \(Qu_k\le Pu_k\) for every rule, and
\(Q^kf=Q(Q^{k-1}f)\le Q(P^{k-1}f)\le P^kf\) closes. At the top level all lemmas are equalities. Algebraic identity; it uses
only that the best of \(K\) is stochastically non-decreasing in the level and that acceptance raises the level by one. Checked
(`count_dominance_lemma_fixture`): (L1)–(L4) and each intermediate inequality on 23 cells (\(n\le16\), \(K\le4\); uniform,
non-uniform and big-jump lattices), every \(m\) and state (6,168 below \(m\)), horizon \(\le12\); dominance for all 120 rules
at \(n=4\) (test).

**Why the standard routes fail, with witnesses.** The pointwise cone \(u_k(J,i+1)\ge u_k(c,i)\) is false: \(n=4,K=2,\delta=\tfrac1{16}\),
from \((0,2)\) at horizon 5 the landing \((3,3)\) is worth \(3.4756<3.4840\), so rejecting the draw 3 once and then playing naive beats
the naive rule at horizon 6: the naive rule maximizes \(\mathbb E[c_g]\) among threshold rules, not among all accept/reject policies.
Prop. 8's route (i)–(iii), the policy-improvement and componentwise conditions fail because the naive count iterates are not monotone
in the count (\(n=4,K=2,\delta=\tfrac1{16}\): two naive steps give \(2.344\) from \((0,0)\), \(2.260\) from \((1,0)\); witnesses in
`dominance_structure_fixture`). The same-uniform coupling cannot give the hitting form either: \(n=5,K=1\), levels
\((0,\tfrac18,\tfrac38,\tfrac7{16},\tfrac12,\tfrac{15}{16})\), \(t=(1,4,0,0,0,0)\), \(m=5\): the uniforms \((45619/65536,\,31371/32768,\,420931/524288,\,
1955493/2097152)\) drive the naive chain \((0,0)\to(1,1)\to(4,2)\) and hold it there while the gated chain goes
\((0,0)\to(2,1)\to(3,2)\to(4,3)\), its level passing the naive's while the naive count is \(4<m\) (`quantile_coupling_crossing`, replayed
from the uniforms); on the lattice \(\tfrac14+i/8\) no such path exists for \(z=1,2,3\) or the non-gate rule within 10 generations.

**Mixed gain laws (0.5).** If an accepted candidate may carry gain 0, a draw \(J>c\) accepted with gain 0 lands at \((J,i)\), which
(L2) makes *worse* for reaching \(m\) than staying at \((c,i)\); a rule rejecting such draws could beat naive. The 0.5 search
(`mixed_gain_dominance_fixture`: every prefix window sum of the naive iterates for every objective, which by \(Q^kf\le QP^{k-1}f\le P^kf\)
covers every rule at once; \(n=2..6\), \(K\le2\), jumps \((\tfrac14,\tfrac34,1)\), \((\tfrac18,\tfrac78)\), two-point \(q\in\{\tfrac14,\tfrac12,\tfrac34\}\)
and \(\{0,2\}\) laws, \(g\le20\); every rule at \(n\le4\), random rules at \(n=5,6\); the decaying schedule) found no violation, and the
fixed-gain proof does not extend: the landing average \(g_k(J)=\sum_\mu w_\mu(J)s_k(J,i+\mu)\), \(w\) the posterior on the gain given the
count, is not monotone in \(J\) (\(n=3,K=1\), levels \((\tfrac14,\tfrac34,1)\), \(q=\tfrac14\), \(m=3\), from \((0,0)\) at \(k=1\):
\(g_1=(\tfrac{429}{512},\tfrac{337}{512})\), prefix average above \(e_1=\tfrac{789}{1024}\), unit window \(\tfrac{1035}{65536}>0\)), and the exact
recursion \(W^a_k=(1-H(i))W^a_{k-1}+E^a_{k-1}+\sum_{(c,a]}\rho(y)W^{m-1}_{k-1}(y)-B_aW^{m-1}_{k-1}(x)\) closes only at \(c=m-2\), where the one window
below \(m\) is the full one, i.e. (L1). (L1) itself, \(s_{k+1}(x)\le(1-H(i))s_k(x)\), equivalently \(W^{m-1}_k(x)\ge0\), is a theorem for every
gain law under two hypotheses: every gain is \(\ge0\) (each landing is at a level \(\ge i\)) and the death rate \(H(i)=P(M\ge m\mid\text{level }i)\)
is non-decreasing in the level (automatic here: \(p\) is non-decreasing and a candidate's count is \(\mathrm{Bin}(n,p(\min(\text{top},i+\mu)))\));
the fixed-gain induction carries over unchanged. Algebraic identity (Lean: `full_window_nonneg`, `lean/FeedbackChannel/MultigenMixed.lean`).
Level: (M1) holds, (M2) fails for \(\{0,2\}\) between adjacent levels, which lie on different
sub-lattices of that law (\(u_4(0,0)=\tfrac{15856573}{16777216}>u_4(0,1)\) on the same cell). 0.5 also recorded (L2)–(L3) as finite beyond
\(\{0,1\}\); the witnesses below refute that.

**Proposition 10 (one positive gain value).** *Hypotheses*, on the abstract chain: states \((c,i)\), \(c\in\{0..n\}\), \(i\in\{0..\text{top}\}\);
from level \(i\) the best candidate is a pair \((J,i')\) drawn from a law \(\pi_i\) that does not depend on the count, and the naive rule
moves to \((J,i')\) iff \(J>c\); (A) one positive gain value: \(i'\in\{i,i^+\}\), \(i^+=\min(\text{top},i+1)\); (B), for the count only: for
every \(m\) the death rate \(H_m(i)=\pi_i(J\ge m)\) is non-decreasing in \(i\). The drift chain satisfies (A) for every gain law on
\(\{0,1\}\) with any \(q_0\in[0,1]\) (a law on \(\{0,g\}\) is the same chain on each sub-lattice \(i+g\mathbb N\) clamped at the top; \(q_0=0\) is
Props. 8–9) and (B) for every non-decreasing level function and every \(n,K\). *Statement*: for any threshold rule (it may depend on the
level and on the generation), any state and horizon: \(\mathbb E^t_x[\psi(c_g)]\le\mathbb E^0_x[\psi(c_g)]\) and
\(\mathbb E^t_x[\varphi(i_g)]\le\mathbb E^0_x[\varphi(i_g)]\) for every non-decreasing \(\psi\) on counts and \(\varphi\) on levels: the naive count
and the naive level are both stochastically above every threshold rule's, from every initial law. *Proof.* (W, every law and every
\(f\)) For \(c<a\) let \(\theta=F_i(a)\) be the naive self-loop probability at \((a,i)\). \(Pu_k\) at \((c,i)\) and at \((a,i)\) share every
landing beyond \(a\), so the window sum is a same-level growth defect,
\[W^a_k(c,i)=[u_{k+1}(c,i)-\theta u_k(c,i)]-[u_{k+1}(a,i)-\theta u_k(a,i)]=\Gamma_{k+1}-\theta\Gamma_k,\qquad\Gamma_k=u_k(c,i)-u_k(a,i).\]
(V, every law) Run chains from \((c,i)\) and \((a,i)\) on the same draws: they agree on a draw at most the lower count, merge on a draw
above \(a\), the lower moves inside the window on a draw there that keeps the level, and diverges on one that raises it, landing at
\(y\), after which the difference is \(Y_r(y,a)=u_r(y)-u_r(a,i)\). For level objectives and for \(1\{c\ge m\}\) with \(a<m\) (the residual
term of a pair that has neither diverged nor merged then vanishes), \(\Gamma_k=\sum_{t\le k}\sum_y\kappa_t(y)Y_{k-t}(y,a)\) with
\(\kappa\ge0\) free of \(k\), so \(\Gamma_{k+1}-\theta\Gamma_k=\sum_y\kappa_{k+1}(y)Y_0(y,a)+\sum_{t\le k}\sum_y\kappa_t(y)[Y_{k+1-t}-\theta Y_{k-t}]\): the window
condition follows from \(Y_0\ge0\) and the *cross-gap growth* \(Y_{r+1}\ge\theta Y_r\). Under a law on \(\{0,1\}\) every divergence state is
\((J,i+1)\), \(J\le a\). (Count) For \(1\{c\ge m\}\), \(a<m\), \(s=1-u\): \(Y_0=0\) and
\[Y_{r+1}-\theta Y_r=\sum_{a<J'<m}\sum_\mu\pi_i(J',\mu)s_r(J',i+\mu)+\theta s_r(J,i+1)-s_{r+1}(J,i+1)\ge(\sigma_i-\sigma_{i+1})s_r(J,i+1)\ge0,\]
\(\sigma_i=1-H(i)\): every landing beyond \(a\) is worth at least \(s_r(J,i+1)\) by (L3) at \(J'\) and (L2) at level \(i+1\), the landings below
\(m\) carry mass \(\sigma_i-\theta\), and (L1) at \((J,i+1)\) bounds the last term. Windows with \(a\ge m\) add non-negative terms to the full
window, which is (L1). (Level) For \(\varphi\): \(Y_0=\varphi(i+1)-\varphi(i)\ge0\), every landing beyond \(a\) is worth at most \(u_r(J,i+1)\) by
(M2) at \(J'\) and (M1) at level \(i+1\) and carries mass \(1-\theta\), so \(Y_{r+1}-\theta Y_r\ge u_{r+1}(J,i+1)-u_r(J,i+1)\ge0\) (the level never
decreases). (Lemmas) (L1) from gains \(\ge0\) and (B), as above; (L2), (L3) as in Prop. 9 from (A) and (B), every landing of the lower chain
being at level \(i\) or \(i+1\); (M1) by first divergence (the chains from \((c,i)\) and \((c+1,i)\) differ only after a gain-1 draw equal to
\(c+1\), worth \(u(c+1,i+1)-u(c+1,i)\ge0\) by (M2)); (M2) by the waiting chain (every landing of \((c,i)\) is worth at most \(v_r=u_r(c,i+1)\) by
(M2) and (M1) at level \(i+1\), so \(u_k(c,i)\le Au_{k-1}(c,i)+(1-A)v_{k-1}\le v_{k-1}\le v_k\), \(A=F_i(c)\)); joint induction on \(k\). The
level statement uses (A) alone; the count statement uses (A) and (B). Then \((Pf-Qf)(c,i)=W^{a(c,i)}_k(c,i)\ge0\)
for every indicator iterate, so \(QP^kf\le P^{k+1}f\) and \(Q_1\cdots Q_kf\le P^kf\). Algebraic identity; for the fixed law it is a second proof
of Props. 8 and 9 that avoids the averaging step. Checked (`gain_support_fixture`, `single_gain_structure`): every step — (L1)–(L3),
(M1), (M2), time monotonicity, both cross-gap growths and every window — at every state and horizon \(\le16\) on 1,176 cells
(\(n=3..10\), \(K\in\{1,2,4\}\), seven lattices including \(p=0\), a plateau and a non-uniform lattice; \(q_1\in\{\tfrac1{16},\tfrac14,\tfrac12,\tfrac{15}{16},1\}\),
\(\{0,2\}\), \(\{0,3\}\)), 50,936,046 exact inequalities; identities (W) and (V) on one- and two-gain cells; every rule directly at
\(n\le4\) on 294 cells (14,406 rule–cell pairs, 64,652,000 comparisons, horizon \(\le24\)); no failure.

**Two positive gain values: counterexample.** The bounds in (Count) and (Level) need every landing beyond the window to be no better
than the divergence state \((J,i+1)\); with two positive gain values a landing above the divergence level is not, and (L2), (L3)
fail with it. \(n=3\), \(K=1\), levels \((0,\tfrac14,\tfrac14,\tfrac34)\), gains \(\{0,1,3\}\) w.p. \((\tfrac35,\tfrac15,\tfrac15)\) (`two_gain_counterexample`):
the rule \(t=(1,0,0,0)\), which rejects a count of one at count zero, is ahead of the naive rule from \((0,0)\) in \(P(c_k=3)\) at every
\(k=28..80\) (largest at \(k=34\): \(0.99090\) against \(0.99045\)), in \(\mathbb E[c_k]\) at \(k=39..80\), and in \(\mathbb E[p(i_k)]\) at \(k=19..80\)
and in the limit (\(\tfrac{2909}{3968}\approx0.7331\) against \(\tfrac{8058689}{11073200}\approx0.7278\)). Mechanism: gain-0 candidates score 0 at \(p=0\);
one unit of gain is worth nothing on the plateau \(p(1)=p(2)\); a count of one comes from a gain-1 candidate w.p. \(\tfrac{27}{320}\) and from a
gain-3 one w.p. \(\tfrac9{320}\), a count of two the other way round. The gate filters out the small gain and waits for the large one,
which a locked-in count of one would block (the naive chain at count one rejects the gain-3 candidates scoring one). On the same cell the
window is first negative at \(k=16\) (\(W^1_{16}(0,0)\approx-1.26\times10^{-5}\) for \(m=3\)), (L3) fails at \(k=10\) (\((1,1)\) survives longer than
\((1,0)\)) and (L2) at \(k=28\). Neither the plateau nor gain 0 is needed: \(n=4\), levels \((0,\tfrac14,\tfrac34)\), gains \(\{0,1,2\}\) w.p.
\((\tfrac37,\tfrac17,\tfrac37)\), the same rule, is ahead in \(P(c_k=4)\) and \(\mathbb E[c_k]\) at \(k=31..80\) (by about \(10^{-6}\)) and in \(\mathbb E[p]\) at
\(k=15..80\); \(n=7\), \(K=2\), levels \((\tfrac1{32},\tfrac5{32},\tfrac9{16},\tfrac{23}{32},\tfrac{15}{16})\), gains \(\{1,3\}\) w.p. \(\tfrac12\) each, \(t(0)=1\), is ahead in
\(\mathbb E[c_k]\) at \(k=8..12\). A three-level witness for the level, by hand: \(n=3\), \(K=1\), levels \((0,\tfrac12,1)\), gains \(\{0,1,2\}\) w.p.
\((\tfrac23,\tfrac16,\tfrac16)\), \(t(0)=2\); naively a middling gain-1 acceptance reaches \(p=1\) only w.p. \(\tfrac45\) before a null perfect score locks
it at \(\tfrac12\), so \(\mathbb E^0[p_\infty]=\tfrac{139}{150}\) against \(\tfrac{17}{18}\) for the gate (finite horizons from \(k=19\)). Finite verified
examples. Exact window screen by support (`support_window_screen`, count and level indicators, every state and window, \(k\le40\);
\(n=3..8\), \(K\in\{1,2,4\}\), the seven lattices; seven single-gain and six two-gain laws, 1,638 cells, 51,813,996 windows): no
negative window on any of the 882 single-gain cells, as Prop. 10 requires; negative count windows on 39 and negative level
windows on 296 of the 756 two-gain cells (count: \(\{0,1,3\}\) 24, \(\{1,3\}\) 9, the skewed three-point law 4, \(\{0,1,2\}\) 2,
\(\{1,2\}\) and \(\{0,2,3\}\) none, of 126 each; level: 108, 54, 79, 14, 14 and 27). A negative window shows that one gated step
followed by naive play wins somewhere; it is necessary, not sufficient, for a threshold rule to win.

**What remains.** Which two-gain cells fail is not characterized (the window condition holds on most screened two-gain cells and on
all of the 0.5 grids; no count failure was found for \(\{1,2\}\)); \(q_0\le\tfrac12\) does not rescue them (the \(\{1,3\}\) witness has \(q_0=0\), the plateau-free one \(q_0=\tfrac37\)). The time-varying
single-gain schedule (the decaying law) is outside the proof, whose divergence weights then depend on the generation; it stays finite
(0.5). The mutation chain was not searched.

## 7. The readout-gap series and the divergence flags

\(\rho_g=\mathbb E[c_g]/n-\mathbb E[p_g]\). Feeding \((g,\mathbb E[c_g]/n,\mathbb E[p_g])\) at \(g\in\{0,4,\dots,20\}\) to
`divergence_flags` with margin \(\tfrac1{40}\) flags an interval iff \(\rho_{g_1}-\rho_{g_0}>\tfrac1{40}\) (identity in the
definition). Null \(n=8,K=2\): \(\rho=(0,.147,.202,.234,.256,.273,\dots,.365)\) gives flags T,T,T,F,F, a prefix as diminishing
increments require; two-point drift matches; the fresh arm flags only the first interval. A check on means.

## 8. Boundaries

Candidates are independent of the incumbent, or correlated through one parameter \(q\) (§5, where the correlation raises
rather than lowers the accumulated gap); neither chain is an exact image of `sim.js`. \(n\) is fixed; labels are clean; gains
are i.i.d. across candidates; the \(p\)-lattice is capped at one, and results near the corner \((n,\text{top})\) are timing
effects. Propositions 5–10 are general (Props. 8–9 for the fixed gain law, Prop. 10 for every law with one positive gain value; with
two positive gain values both orderings fail, by exact counterexample); the \(q\)-survey, the chaining counts, the decaying-schedule
ordering and the two-gain screen are finite checks on the enumerated cells. Results are about distributions, not sample paths; no
model, agent or observed-controller evidence is claimed.
