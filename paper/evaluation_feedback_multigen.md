# The selection gap across generations, exactly

Draft 0.1 — 2026-10-12. Companion to `evaluation_feedback_insertions.md`, whose selection law
stops at one generation and whose multi-generation rows come from seeded JavaScript. This note
replaces the accumulation claim with a finite Markov chain in exact arithmetic. No model is
called; nothing here is evidence about any controller. Each result names its evidence level
from the calculus card (§11): *algebraic identity* holds for every parameter; *finite verified
example* is checked only on the enumerated cells; *synthetic mechanism result* is a property
of this toy chain.

Source `src/spiral_ln/evaluation_feedback_multigen.py`; 70 tests in `tests/`; receipt
`output/evaluation_feedback_multigen/multigen_v0_1.json` (30 checks, source hashes, exact
fractions, float renderings under `headline`).

```powershell
$env:PYTHONPATH = "src"
python scripts/verify_evaluation_feedback_multigen.py --output output/evaluation_feedback_multigen/multigen_v0_1.json
python -m pytest tests/test_evaluation_feedback_multigen.py -q
```

## 1. The chain: vertices, edges, policy

A reused set of \(n\) items. **State**: the incumbent's realized count \(c\in\{0,\dots,n\}\) on
that set. Each generation draws \(K\) candidates i.i.d. and independent of the incumbent,
\(C_k\sim\mathrm{Bin}(n,p)\), \(M=\max_k C_k\). **Actions**: accept or reject the best candidate.
**Policy**: accept iff \(M>c+t(c)\), \(t:\{0..n\}\to\mathbb N\). **Edges**: \(c\to j\) with
probability \(P(M=j)\) for \(j>c+t(c)\); the self-loop carries \(F(c+t(c))^K\), \(F\) the binomial
CDF with \(F(j)=1\) for \(j\ge n\). The graph is a DAG of upward edges plus self-loops; its sinks
\(\{c:c+t(c)\ge n\}\) are the absorbing states. Initial state \(c_0\sim\mathrm{Bin}(n,p)\).
Reported score \(c_G/n\); readout value \(p\); readout gap \(\rho_G=\mathbb E[c_G]/n-p\). In the
calculus: \(\operatorname{Repeat}_G\) of one generation with carry map "keep \(c\)", composed
with \(\operatorname{Feedback}_{s,\text{score-only}}\) whose consumer selects among candidates.

**Gate discretization.** `sim.js` accepts iff \(M>c+z\sqrt{p(1-p)/n}\,n\) with \(p=c/n\), i.e.
\(M-c>z\sqrt{c(n-c)/n}\). The difference is an integer \(d\), and \(d>x\) iff
\(d\ge\lfloor x\rfloor+1\), so \(t(c)=\lfloor z\sqrt{c(n-c)/n}\rfloor\), computed exactly as
\(\lfloor\sqrt{a/b}\rfloor=\mathrm{isqrt}(ab)\,//\,b\). For \(n=16,z=3\):
\(t=(0,2,3,4,5,5,5,5,6,5,5,5,5,4,3,2,0)\). Fixture `gate_threshold`, checked by
\(t^2\le z^2c(n-c)/n<(t+1)^2\) on every state and against the real-valued rule for every
integer \(d\). Algebraic identity.

## 2. Naive reuse is a running maximum

**Proposition 1.** With \(t\equiv0\), \(c_G=\max(c_0,M_1,\dots,M_G)\), the maximum of \(GK+1\)
i.i.d. \(\mathrm{Bin}(n,p)\) draws, so \(\rho_G=\) `selection_inflation(n, GK+1, p).readout_gap`.
The initial incumbent is one draw because it is scored on the reused set like every candidate;
a *known* count \(c_0\) gives \(\mathbb E[\max(c_0,X)]\), \(X\) the max of \(GK\) draws
(`running_max_from_point`). *Proof.* If \(M_g>c_{g-1}\) the policy sets
\(c_g=M_g=\max(c_{g-1},M_g)\); otherwise \(c_g=c_{g-1}=\max(c_{g-1},M_g)\). Induct. Algebraic
identity. The DP equals the closed form on all 18 null cells (\(n\in\{4,8,16\}\),
\(K\in\{1,2,4\}\), \(p\in\{\tfrac12,\tfrac14\}\), \(G=0..20\)); at \(n=2,K=2,G=2\) it equals
literal enumeration of all \(2^{10}\) item outcomes.

**Consequences.** (i) \(\rho_G\) is non-decreasing in \(G\): a maximum over more draws is
pointwise larger. (ii) Increments are non-increasing: \(a_{m+1}-a_m=\mathbb E[(X-M_m)^+]\) with
\(M_m\) pointwise non-decreasing in \(m\). (iii) \(P(c_G=n)=1-(1-p^n)^{GK+1}\), so for fixed
\(n\) and \(0<p<1\), \(\rho_G\uparrow1-p\): bounded by the lattice, never stationary. These are
algebraic identities with the proofs above; the fixture verifies them on the enumerated cells
only. *Remark, not verified:* while \(GK\) is large and the maximum is still far from \(n\),
the Gaussian extreme-value approximation gives \(\rho_G\approx\sqrt{2\ln(GK+1)\,p(1-p)/n}\).

Values at \(p=\tfrac12\) (exact in the receipt). \(n=8,K=2\): \(\rho_1=19305/131072\approx0.1473\),
\(\rho_5\approx0.2726\), \(\rho_{10}\approx0.3212\), \(\rho_{20}\approx0.3645\). \(n=16,K=4\):
\(0.1440,\ 0.2318,\ 0.2648,\ 0.2947\). \(n=4,K=1\): \(\rho_1=35/256\), the insertions note's
two-candidate four-item value, the incumbent being the second candidate.

## 3. Fresh blocks

**Proposition 2.** (a) If each generation scores incumbent and candidates on a fresh block and
reports on a second fresh block, the expected reported score is \(p\) at every generation: the
readout block is independent of whatever selected the controller, and under the null every
controller has probability \(p\). (b) If it reports on the selection block, the reported count
at \(g\ge1\) is \(M\) if \(M>I+t(I)\), else \(I\), with \(I\sim\mathrm{Bin}(n,p)\) the
incumbent's fresh count; the law does not depend on \(g\). For \(t\equiv0\) it is \(\max(I,M)\),
the maximum of \(K+1\) draws, so the gap equals `selection_inflation(n, K+1, p)` at every
\(g\ge1\) and does not accumulate. Both algebraic identities (independence, linearity);
verified on 12 cells and by enumeration at \(n=2,K=2\) in both modes. The reused chain
coincides with (b) at \(G=1\) for any gate and exceeds it strictly for \(G\ge2\) on every
enumerated cell (finite check).

## 4. The gate

**Proposition 3 (false acceptance).** From state \(c\) the generation accepts with probability
\(\alpha(c)=1-F(\min(n,c+t(c)))^K\); under the null every acceptance is false, and the
unconditional rate at generation \(g\) is \(\sum_c\pi_{g-1}(c)\alpha(c)\). Algebraic identity.
For \(n=16,K=4,z=3\): \(\alpha(8)=1-(1-17/65536)^4\approx1.0\times10^{-3}\); naive \(\approx0.36\).

**Proposition 4 (gate dominance, null only).** For any \(t\ge0\), couple the gated and naive
chains on the same draws. The gated state always belongs to \(\{c_0,M_1,\dots,M_g\}\), whose
maximum is the naive state; hence \(c^t_G\le c^0_G\) pointwise, \(\rho^t_G\le\rho^0_G\), and
\(\alpha^t(c)\le\alpha^0(c)\). Algebraic identity by coupling; its hypothesis is that every
candidate's law is the same whatever the history, i.e. the null. With true gains it fails and
can reverse (§5). Values at \(G=20,p=\tfrac12,n=16,K=4\): naive \(0.2947\); \(z=1\): \(0.2723\);
\(z=2\): \(0.2019\); \(z=3\): \(0.1328\); expected false acceptances \(2.34\to0.33\).
\(n=8,K=2\): naive \(0.3645\), \(z=3\): \(0.0967\). The gate also creates sinks below the
ceiling: for \(n=8,z=3\) states \(4..8\) absorb, so a gated loop freezes; the simulation's
GATED arm accepting 0–2% of generations is the same mechanism.

## 5. True gains: the drift chain

State \((c,i)\) with \(p(i)=\min(1,\tfrac14+i/8)\). Each candidate draws a gain multiple \(m\)
from a law (constant, or one law per generation), has probability \(p(i+m)\), and on acceptance
the state becomes \((M,i+m^*)\), \(m^*\) the accepted candidate's gain; by exchangeability
\(P(M=j,m^*=m)=P(M=j)\,q_m\,\mathrm{Bin}(n,p(i+m))(j)/\mathrm{mix}(j)\). Reported
\(\mathbb E[c_g]/n\), true \(\mathbb E[p(i_g)]\), phantom share \(1-\)true gain/reported gain.
Verified by enumeration of every gain draw and item outcome at \(n=2,K=2,G=2\) (six laws, two
policies); the zero-gain law reproduces the null chain exactly (test). Laws: *fixed*
\(\delta=\tfrac18\); *two-point* \(\delta=\tfrac18\) w.p. \(\tfrac14\); *decaying two-point*
\(q_g=\tfrac14(\tfrac34)^{g-1}\), a lattice analogue of the simulation's \(0.06\cdot0.95^{g-1}\).
Cells \((n,K)\in\{(4,2),(4,4),(8,2),(8,4),(16,2)\}\), \(G=20\), naive and \(z=1\). Everything
below is a synthetic mechanism result on those cells and nothing more.

- Two-point, naive, \(n=8,K=2\): reported \(0.778\), true \(0.420\); phantom share \(0.678\)
  over \(0..20\), \(0.711\) early half, \(0.504\) late half; late/early gain ratio reported
  \(0.195\), true \(0.334\).
- Decaying, naive, \(n=8,K=2\): phantom \(0.838\) whole, \(0.977\) late; late/early reported
  \(0.130\) versus true \(0.016\).
- Against `results.json`: P3 (late phantom share above one half under naive reuse) holds on
  every cell with \(n\le8\) for both laws and on all cells for the decaying law. P5 (reported
  late/early ratio at least twice the true one) holds only under the decaying schedule (about
  8× here, 4× in the simulation); with constant gains the ordering reverses on every cell,
  because an inflated count is beaten less often by no-gain candidates, so late acceptances
  are enriched for real gains. P5 is a property of the simulation's decaying gain scale, not
  of reuse alone.
- Gate ordering with true gains: fixed gain, \(z=1\) gap *above* naive on every cell
  (\(n=8,K=2\): \(0.347\) vs \(0.279\)), because the gate refuses true gains too and the truth
  lags further; decaying gain, gate below naive on every cell. Proposition 4 is a null result
  and must not be read as "gating reduces the gap".
- Lattice ceiling: with fixed gain at \(n=16\) the late phantom share is negative (reported score
  pinned near one while \(p\) still rises); phantom shares near the ceiling are not interpretable.

## 6. The readout-gap series and the divergence flags

\(\rho_g=\mathbb E[c_g]/n-\mathbb E[p_g]\). Feeding \((g,\mathbb E[c_g]/n,\mathbb E[p_g])\) at
\(g\in\{0,4,\dots,20\}\) to `divergence_flags` with margin \(\tfrac1{40}\) flags an interval iff
\(\rho_{g_1}-\rho_{g_0}>\tfrac1{40}\) (identity in the definition). Null \(n=8,K=2\):
\(\rho=(0,.147,.202,.234,.256,.273,\dots,.365)\) gives flags T,T,T,F,F, a prefix as diminishing
increments require; two-point drift matches; the fresh arm flags only the first interval. A check on means.

## 7. Boundaries

Candidates are independent of the incumbent; `sim.js` perturbs the incumbent's per-item quirks
(\(\sin\phi=0.2\)), correlating each candidate's outcomes with the incumbent's item by item, which
shrinks the spread of \(M-c\) and lowers every per-generation inflation; the ratchet and
Propositions 1–4 keep their form with \(\mathrm{Bin}(n,p)\) replaced by the conditional law of a
correlated count. \(n\) is fixed; labels are clean; gains are i.i.d. across candidates; the
\(p\)-lattice is capped at one. Results concern distributions and expectations, not sample
paths. No model, agent, or observed-controller evidence is claimed.
