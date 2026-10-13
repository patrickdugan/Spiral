# Feedback-channel results and RSITopology: a crosswalk

Draft 0.1 — 2026-10-13. A mapping from the Spiral feedback-channel programme
([calculus](evaluation_design_calculus.md), [insertions](evaluation_feedback_insertions.md),
[signal limits](rl_training_signal_limits.md), [lattice](evaluation_feedback_lattice.md),
[multigen](evaluation_feedback_multigen.md), [composition](evaluation_feedback_composition.md)) to the
AI Safety Millennium Problem statements and to the identity-geometry programme of `MoralityLabAI/RSITopology`
(branch `feat/spectral-bundle-v0.3-bifiltration`). RSITopology paths are relative to that repository's root,
Spiral paths to `paper/`. Nothing was run against a model. One script was written,
`scripts/crosswalk_asmp8_check.py`; its output is in §1.

Statuses: **exact instance** (a Spiral proposition is a finite case of the statement), **bound** (one side's
result bounds a quantity of the other), **same object, different regime** (comparable object, not the same
theorem), **analogy only**, **no relation**. Evidence levels follow the calculus card (§11): *documentary*
means read from both repositories' notes; *finite verified example* means the script checked it.

## 0. The two sides

**Spiral.** \(\mathcal E=\langle G,\Pi,D,Z,J,\mathcal A,C\rangle\) (calculus §2). \(\operatorname{Feedback}_{s,q}\)
reads \(J\) on set \(s\) at access class \(q\in\{\text{sealed},\text{score-only},\text{item-level}\}\) and writes \(\Pi\)
for the next generation (insertions §B); the readout gap \(\rho=V^s_\pi-V^r_\pi\) compares two measurements of one
controller (§E). Exact results: the selection law with gap \(\gamma(n,K,p)\) (§D); the ceiling law and blind range
(§D; signal L3); the correlated judge (L4); bits per episode and score-query reconstruction (L1, L2); Blackwell
garbling (L6); channels as partitions (lattice Props 1–6); the running maximum \(\rho_G=\gamma(n,GK+1,p)\) and the
gate (multigen Props 1–4); footprints, typing \(\Leftrightarrow\) ledger, carry map, Rescore moving \(\rho\) (composition Props 1–5).

**RSITopology (B), the ASMP set.** Twelve problem templates, each opening with a "Freeze:" list
(`ultra-experiments/millennium/AI_SAFETY_MILLENNIUM_PROBLEMS_v0_1.md`, `V0_2_SCOPE_EXPANSION_DRAFT.md`). The
repairs draft (`ASMP_V0_2_STATEMENT_REPAIRS_DRAFT_20261012.md`, R1–R9) and critique
(`docs/CRITIQUE_NOTES_20261012.md`) restate ASMP-8 as a tail-class problem on KL balls, ASMP-10 as a Bayes-error
problem, ASMP-11 as provenance access, and resolve the ASMP-4 fork by its quantifier.

**RSITopology (A), identity geometry.** *Spectral bundle:* per prompt \(p\), a band projector \(P_b(p)\) of a
normalized sheaf Laplacian; the consensus \(U_b\) is the high-occupancy eigenspace of the mean projector
(`reports/mathematical_program.md`). *Lineage:* the chordal overlap \(\operatorname{tr}(P_{\text{ref}}P_t)/\min\operatorname{rank}\)
and the principal angles between reference and current bundles, worst-direction retention being the smallest
squared cosine; it asks whether the coherent subspace at \(t\) still denotes the reference object
(`reports/bundle_lineage_hypothesis.md`, "Mathematical refinement"). *Holonomy:* the polar factors of the
overlaps composed around a context-by-checkpoint loop give \(H_\square\in O(r)\); \(\kappa_\square=1-\operatorname{tr}H_\square/r\)
is the mean signed-coordinate identity loss, \(\det H_\square<0\) a categorical break, and the infinitesimal
object is the curvature \(F=P[\partial P,\partial P]P\) of the Grassmann connection
(`reports/monitor_holonomy_insight.md`). *Attestation:* `AnchorRegistry.certify` returns the level attained among
`engineering_evidence < lineage_certified < holonomy_clean` from basis hashes, the unique spanning-tree path,
edge receipts, a holonomy budget and `det_h_flag`; band failover breaks lineage certification and orientation
reversal blocks signed use (`docs/IDENTITY_ATTESTATION_INTEGRATION.md`; `README.md`, "Identity-attestation consumers").

## 1. ASMP-8, the Goodhart frontier

**Objects.** ASMP-8 (`V0_2_SCOPE_EXPANSION_DRAFT.md`, "ASMP-8") fixes nested reachable sets \(\Pi_\lambda\),
true \(R\), proxy \(\hat R\), a divergence class \(D_\varepsilon\), and
\(\mathrm{Regret}(\lambda,\varepsilon)=\sup_{D_\varepsilon}\sup_{\hat\pi\in\arg\max_{\Pi_\lambda}\hat R}[\sup_{\Pi_\lambda}R-R(\hat\pi)]\).
R3 takes the KL slice \(\Pi_\lambda=\{\mathrm{KL}(\pi\|p_0)\le\lambda\}\) and proves: if \(\delta=R-\hat R\) is
\(\sigma\)-sub-Gaussian under \(p_0\) then \(\mathrm{Regret}\le2\sigma\sqrt{2\lambda}\), sharp. Its proof bounds
\(\mathrm{Regret}\le\sup_\pi\mathbb E_\pi[\delta]+\sup_\pi\mathbb E_\pi[-\delta]\) and applies Donsker–Varadhan
to each term: \(\mathbb E_\pi[-\delta]-\mathbb E_{p_0}[-\delta]\le\sigma\sqrt{2\lambda}\).

**Is \(\rho\) a Goodhart gap?** Not in ASMP-8's sense. With \(\pi^*\) a true-best reachable policy,
\(\mathrm{Regret}=[\hat R(\hat\pi)-R(\hat\pi)]+[\hat R(\pi^*)-\hat R(\hat\pi)]+[R(\pi^*)-\hat R(\pi^*)]\); the middle
bracket is \(\le0\) since \(\hat\pi\) maximizes the proxy, and the outer brackets are what R3 bounds. The first
bracket, proxy minus true at the selected controller, *is* Spiral's \(\rho\) (insertions §E; multigen §1).
Under Spiral's null A5 (signal §3) every candidate has true value \(p\), so at that instance
\(\sup R-R(\hat\pi)=p-p=0\) while \(\rho=\gamma(n,K,p)>0\): a *reporting* error, positive where the *choice*
error is zero, and one summand of the triangle bound on it. Status: **analogy only** (different functional,
shared decomposition).

**Best-of-\(K\) is a point of the KL slice.** Let \(\Omega=\{0,1\}^n\), \(p_0=\mathrm{Bern}(p)^n\), \(\hat R(\omega)=\)
score on \(s\), \(R\equiv p\). Keeping the best of \(K\) draws induces a law \(\pi_K\) whose likelihood ratio
depends only on the score, and R3 cites Beirami et al. for \(\mathrm{KL}(\pi_K\|p_0)\le\ln K-(K-1)/K\). So
\(\gamma(n,K,p)=\mathbb E_{\pi_K}[\hat R-R]\) is the first summand at one point of the ball, and the DV step gives
\[
\gamma(n,K,p)\ \le\ \sup_{\mathrm{KL}(\pi\|p_0)\le\lambda_K}\mathbb E_\pi[\hat S]-p\ \le\ \sigma_n\sqrt{2\lambda_K},
\qquad \sigma_n^2=v(p)/n,\quad v(p)=\tfrac{1-2p}{2\ln\frac{1-p}{p}},\ v(\tfrac12)=\tfrac14,
\]
\(v\) the Kearns–Saul variance proxy of a Bernoulli (Kearns and Saul 1998; the constant is checked on a
\(t\)-grid, not reproved; its optimality remains a citation, attributed from memory to Buldygin and Moskvichova
2013 and not checked against that paper). Settled, see `selection_law_kl_containment.md`: the containment
\(\mathrm{KL}(\pi_K\|p_0)\le\ln K-(K-1)/K\) holds for every finite base law, score and \(K\), strictly for
\(K\ge2\), tied best-of-\(K\) included (Theorem B there, by continuous jitter and Jensen on \(x\ln x\); R3's
Beirami citation is no longer load-bearing), and the DV step \(\gamma\le\sqrt{2v(p)\mathrm{KL}(\pi_K\|p_0)/n}\)
is proved for every \(n,K,p\) (Theorem C). The running maximum is the same with
\(K\mapsto GK+1\) (multigen Prop 1), the carry fixture with \(K\mapsto2K-1\) (composition Prop 4). Status:
**same object, different regime** for the summand (exact value at a point of an atomic lattice versus a
supremum over a KL ball, sharp only at an exponential tilt); **bound** for the theorem.

**Check** (`scripts/crosswalk_asmp8_check.py`; \(M\) = draws; exact gaps as fractions, matched to
`selection_inflation(n, M, p)`; KL and bounds as floats, tolerance \(10^{-9}\); 20 cells, all pass):

| cell | exact gap | \(\mathrm{KL}(\pi_M\|p_0)\) | Beirami radius | KL-ball sup | \(\sigma_n\sqrt{2\,\mathrm{KL}}\) | gap/bound |
|---|---:|---:|---:|---:|---:|---:|
| \(n=1,M=2,p=\tfrac12\) | \(1/4\) | 0.1308 | 0.1931 | 0.25000 | 0.25575 | 0.978 |
| \(n=4,M=2\) | \(35/256\) | 0.1745 | 0.1931 | 0.14663 | 0.14771 | 0.926 |
| \(n=64,M=2\) | 0.03519 | 0.1919 | 0.1931 | 0.03870 | 0.03872 | 0.909 |
| \(n=8,M=3\) (multigen \(G=1\)) | \(19305/131072\) | 0.4102 | 0.4319 | 0.15873 | 0.16012 | 0.920 |
| \(n=8,M=41\) (\(G=20\)) | 0.36451 | 2.5572 | 2.7380 | 0.37668 | 0.39978 | 0.912 |
| \(n=16,M=81\) (\(K=4,G=20\)) | 0.29471 | 3.2943 | 3.4068 | 0.30929 | 0.32086 | 0.919 |
| \(n=1,M=3\) (composition gen 2) | \(3/8\) | 0.3164 | 0.4319 | 0.37500 | 0.39773 | 0.943 |
| \(n=8,M=3,p=\tfrac14\) | 0.12933 | 0.4027 | 0.4319 | 0.14445 | 0.15136 | 0.854 |
| \(n=1024,M=2,p=\tfrac12\) | 0.00881 | 0.1931 | 0.1931 | 0.00971 | 0.00971 | 0.908 |

Readings. (i) The chain gap \(\le\) KL-ball sup \(\le\sigma\sqrt{2\mathrm{KL}}\le\sigma\sqrt{2\lambda_{\text{Beirami}}}\)
holds on every cell; the exact KL of the tied best-of-\(M\) law is below Beirami's radius everywhere, approaching
it as \(n\) grows. (ii) At \(n=1\) every law on two points is a tilt, so the Spiral gap *equals* the KL-ball
supremum (\(1/4\), \(3/8\)). (iii) At \(p=\tfrac12\) the ratio is 0.91–0.92 for every \(n,K,G\) computed and
tends to \((1/\sqrt\pi)/\sqrt{2\ln2-1}=0.9077\) at \(K=2\) (0.9076 at \(n=1024\)): the KL slice is within ten
percent of the exact finite optimizer's curse under the null. Off centre the ratio drops (0.85 at \(p=\tfrac14\),
0.81 at \(p=\tfrac34\)) because \(v(p)\) exceeds the variance. (iv) R3's finite-sample corollary (sup-norm proxy error
\(\epsilon_n\Rightarrow\mathrm{Regret}\le2\epsilon_n\)) does not apply, since an empirical score's sup-norm error is
\(\max(p,1-p)\); the light-tail theorem is what covers item scores. (v) Where Spiral's Regret is nonzero (the drift
chain, multigen §5) the candidate laws share no base law, so no KL comparison was attempted. Nothing here is a
result on ASMP-8 as a whole, whose open part (R3) is the tail class and the learned-proxy frontier.

*Evidence: finite verified example (script, 20 cells); R3 and the Kearns–Saul constant cited; the containment
and the DV step are algebraic identities in `selection_law_kl_containment.md`.*

## 2. ASMP-10 and the noise ceiling

ASMP-10 as posed (`V0_2_SCOPE_EXPANSION_DRAFT.md`, "ASMP-10") asks whether training observables predict a later
capability; R4 restates it as the Bayes error \(B(F_s)=\inf_\Phi\mathbb E_\mu[\mathrm{loss}(\Phi(F_s),C(W_{s'}))]\)
under a frozen prior \(\mu\) over training processes, with "sufficient" meaning \(B(F_s)=B(F_{\text{full}})\).
Spiral's ceiling law (insertions §D; signal L3): labels flipped independently at rate \(\varepsilon\), no
predictor blind to the flips exceeds \(1-\varepsilon\). That is the Bayes error of forecasting the observed label
from any filtration independent of the flip, \(B(F)\ge\varepsilon\) under 0–1 loss: R4's functional in a different
experiment (a noisy item label, not a future capability under \(\mu\)). It is not an instance of the problem, whose
content is *which* observables of a training process are sufficient. Status: **same object, different regime**.
The blind range, memorization share \((1-\varepsilon-v)/(1-v)\) before a ceiling check fires (L3; exact per
category in lattice Prop 4), is a detection-power statement with no counterpart: **no relation**. The correlated
judge (L4: the ceiling is reached without memorization iff \(\varepsilon\ge(1-a)/2\)) has no judge to map to in
ASMP-10: **no relation**; its nearest ASMP object is ASMP-3's noisy semantic oracle, whose noise model carries "a
complete correlation/adaptivity class" and forbids assuming independence (`AI_SAFETY_MILLENNIUM_PROBLEMS_v0_1.md`,
ASMP-3); L4 is a one-shot, one-atom accuracy identity, ASMP-3 a multi-round verifier game: **analogy only**.
R4's sufficiency clause is Blackwell sufficiency, the order L6 uses on step-record channels: same order, different experiment.

*Evidence: documentary.*

## 3. ASMP-4, the two-port bracket

What \(h^*\) is (`asmp4_two_port_scalar_uncertain_20261012/NOTE.md` §4.2; R2): for \(x'=ax+u+w\), \(|w|\le\delta<1\),
\(K=K_0=[-1,1]\), \(h^*\) is the infimal transcript rate (bits per step) of a causal code keeping the plant in \(K\)
for every disturbance; with \(\rho=a/(1-\delta)\), \(\log_2\rho\le h^*\le\log_2\lceil\rho\rceil\), equality on the
left iff \(\rho\) is an integer or \(\delta=0\), strictly above otherwise, \(h^*\) the growth rate of a
one-dimensional "fullness" dynamic program; under the canonical quantifier the two-port region is \([h^*,\infty)^2\).
Spiral L1 (a channel with \(m\) images carries at most \(\log_2m\) bits per episode; \(H\) hypotheses need
\(\lceil\log H/\log m\rceil\) episodes) and L2 (\(q_{\min}\ge\lceil\log\binom nf/\log(f+1)\rceil\) queries;
halving needs \(\le f\lceil\log_2n\rceil+1\)) are counting bounds on a static channel with no plant, no adversary
and no rate. The only shared piece is the lemma \(\log_2|L(T)|\le T\log_2m\), which neither programme claims as a
result. ASMP-4's content, that the number of things to distinguish grows like \(\rho^T\) because cells of
measure \(\le2/\rho\) must cover a continuation of measure \(\ge a\lambda(S)+2\delta\) (NOTE §4.3,
Brunn–Minkowski) and that child-count integrality forces \(h^*>\log_2\rho\) (§4.6), has no counterpart in
L1/L2; L1's factorization statement (partial credit and first-failure incomparable) and L2's exact minimax
\(q_{\min}\) have none in ASMP-4, whose controller need not identify the state, only confine it. No quantity in
ASMP-4's statement is bounded by or instantiated by L1 or L2. Status: **analogy only**, at the level of a one-line lemma.

*Evidence: documentary.*

## 4. ASMP-11, ASMP-12, and two unrequested rows

- **ASMP-11** (R5, Lemma S: an oracle polynomial-time computable from \((W,S)\) adds nothing to a white-box
  distinguisher). In lattice terms this is the absorption law \(p\le q\Rightarrow p\vee q=q\) (lattice §1), which
  the partition lattice satisfies trivially; Lemma S's whole content is the complexity clause, which a partition
  lattice cannot express, and its channels run from a model to a distinguisher, not from \(J\) to a loop. **Analogy only.**
- **ASMP-12** (resource-bounded program equilibrium; `asmp12_modal_agent_census_20261012/NOTE.md`). Nothing in
  the feedback-channel results concerns agents reading each other's source, provability, or equilibrium
  selection; the calculus's Nash material (§9) is a \(2\times2\) payoff computation outside the feedback programme. **No relation.**
- **ASMP-3** \(\leftrightarrow\) L4: see §2. **Analogy only.**
- **ASMP-7** (Blackwell composite testing over transformation orbits with an attestation cost) \(\leftrightarrow\) L6 and
  lattice Prop 1: the shared object is the Blackwell preorder; ASMP-7 asks for a Blackwell- or Pareto-minimal
  experiment in a cost frontier, Spiral states the garbling inequality and the TV contraction. **Same object, different regime.**

*Evidence: documentary.*

## 5. Program (A): carry maps, lineage, attestation, holonomy

**Repeat with a carry map vs lineage.** Composition Prop 4 and insertions §C: the carry map carries \(\Pi\) with
its realized outcomes on \(s\), so \((S_1,S_2)\) is not exchangeable and the generation mean overstates by
\((\gamma(n,2K-1,p)-\gamma(n,K,p))/2\) while the sealed readout stays at \(p\); the fault is in the aggregation
unit \(\mathcal A\). Lineage measures whether the carried controller's internal subspace is still the reference
object: a statistic of the pair \((\Pi_g,\Pi_{g+1})\) the carry map produces. Both say the carry map transports
something a naive analysis assumes reset, on different fields of \(\mathcal E\), and neither implies the other:
an item-level patch in the composition model rewrites per-item overrides in `pi` and moves no subspace (perfect
lineage, maximal \(\rho\)), and a bundle can rotate under a sealed channel. **Analogy only.**

**Attestation vs the ledger.** The ledger's certificate is `declarations_respected` (composition Prop 3: well-typed
\(\Leftrightarrow\) respected on all 22,143 short sequences; a breach moves the readout endpoint to `not_evaluated`).
The attestation's certificate is the level attained, with band failover and orientation reversal as categorical
refusals. Both are monotone provenance certificates over a hash or identifier chain, both refuse rather than degrade,
and each is the only record of a change its headline scalar cannot show: composition Prop 5 (Rescore moves \(\rho\)
by exactly a memorizing step's amount, with no ledger event) and program (A)'s silent re-anchoring of a monitor
under the old name (`reports/bundle_lineage_hypothesis.md`, "Why this is interesting"). But the ledger certifies
information flow from \(J\) into \(\Pi\); attestation certifies the identity of the measuring instrument, which
lives in \(J\). So "an attestation is a record that a readout stayed sealed" is not right: a sealed readout scored by
a re-anchored monitor is a \(\operatorname{Rescore}_j\) and the ledger shows nothing (Prop 5's blind spot).
Complementary, not counterparts. **Analogy only**, with that precise complement.

**Holonomy vs the ledger.** Holonomy is a loop-closure invariant, path dependence of transport around a cycle. The
ledger has no loops; its events form a sequence and typing is per prefix (composition §3). **No relation.** The
one cycle condition in Spiral is lattice Prop 2c; see §6.

*Evidence: documentary.*

## 6. The word "topology"

Spiral's objects are order-theoretic: the partition lattice of \(\{0,1\}^n\) with reversed orientation (lattice §1),
the order embedding \(\Phi\) from the partition lattice of \([n]\) (Prop 2), the TV contraction with converse (Prop 1),
the Blackwell preorder (L6); no continuity, homology of a space, or connection appears. Program (A)'s objects are a
bundle over prompt space with a Grassmann connection, curvature and \(O(r)\) holonomy, and the repository itself says
the object "is not graph topology by itself" and that the JSpace controls "deflate topology as an independent
explanation" (`README.md`; `reports/mathematical_program.md`). At the level of the programmes the shared word is nominal.

One invariant is genuinely shared: the cycle rank \(\beta_1=|E|-|V|+c\) of a graph. Lattice Prop 2c: two category
leaks observed separately equal the joint leak iff the bipartite intersection graph \(I(\gamma,\gamma')\) is a
forest; a cycle is exactly where margins fail to determine cells. Program (A), v0.3 amendment: holonomy is
reported `holonomy_unavailable` when \(\beta_1(G_\tau)=0\) for the lineage-filtered transport graph (`README.md`),
and off-tree edges of a rooted spanning tree are the loop-closure audits (`reports/monitor_holonomy_insight.md`).
In both, cycle rank counts the global data that edge-local data cannot fix: free cell counts in one, holonomy
loops in the other. The graphs differ (a contingency table's support; a context-by-checkpoint grid), the theorems
differ, and nothing else transfers. Status for \(\beta_1\): **same object, different regime**; for "topology": nominal.

*Evidence: documentary.*

## 7. Status table

| Mapping | Status |
|---|---|
| \(\rho=V^s-V^r\) \(\leftrightarrow\) ASMP-8 Regret | analogy only (one summand of the triangle bound; Regret is zero at the Spiral null) |
| selection law / running maximum \(\leftrightarrow\) R3 summand \(\sup_{\Pi_\lambda}\mathbb E_\pi[-\delta]\) | same object, different regime |
| R3 light-tail theorem \(\leftrightarrow\) \(\gamma(n,M,p)\) | bound (verified on 20 cells; ratio 0.91–0.92 at \(p=\tfrac12\)) |
| ceiling law \(1-\varepsilon\) \(\leftrightarrow\) ASMP-10 (R4 Bayes-error form) | same object, different regime |
| blind range (L3) \(\leftrightarrow\) ASMP-10 | no relation |
| correlated judge (L4) \(\leftrightarrow\) ASMP-10 / ASMP-3 | no relation / analogy only |
| L1, L2 \(\leftrightarrow\) ASMP-4 \(h^*\) bracket | analogy only (one shared counting lemma) |
| lattice absorption \(\leftrightarrow\) ASMP-11 Lemma S | analogy only |
| feedback results \(\leftrightarrow\) ASMP-12 | no relation |
| L6 / Prop 1 \(\leftrightarrow\) ASMP-7 Blackwell frontier | same object, different regime |
| Repeat with carry (Prop 4) \(\leftrightarrow\) lineage | analogy only |
| ledger certificate (Props 3, 5) \(\leftrightarrow\) attestation | analogy only (complementary: \(\Pi\leftarrow J\) flow vs \(J\)'s identity) |
| ledger \(\leftrightarrow\) holonomy | no relation |
| \(\beta_1\) in Prop 2c \(\leftrightarrow\) \(\beta_1\) in the v0.3 holonomy gate | same object, different regime |
| "topology" (lattice vs bundle) | nominal |

No exact instance was found in either direction, and none is claimed.

## 8. What a joint result would need

1. **Best-of-\(K\) inside the KL slice, all parameters.** *Settled, see `selection_law_kl_containment.md`.*
   Containment holds for every \(n,K,p\), and for every finite base law and score: \(\mathrm{KL}(\pi_K\|p_0)<\ln K-(K-1)/K\)
   for \(K\ge2\) (Theorem B) and \(\gamma(n,K,p)\le\sqrt{2v(p)\,\mathrm{KL}(\pi_K\|p_0)/n}\) (Theorem C). The ratio
   \(\gamma/(\sigma_n\sqrt{2\lambda_K})\) is *not* bounded away from 1 uniformly in \(K\): its supremum over
   \(n,K,p\) is 1, approached in the Gaussian limit \(n\to\infty\) at \(p=\tfrac12\) as \(K\to\infty\) and never
   attained; the per-\(K\) limit is \(c_K=\mathbb E[\max\text{ of }K\text{ standard normals}]/\sqrt{2\lambda_K}\),
   0.9077, 0.9187, 0.9326, 0.9429, 0.9505 at \(K=2,10,100,1000,10^4\), with \(c_K<1\) for each \(K\) and
   \(c_K\to1\); at fixed \(n\) the ratio tends to 0 as \(K\to\infty\); on a 90-cell grid every finite-\(n\) ratio
   lies below its \(c_K\) (finite verified). The 0.91–0.92 observed for \(M\le81\) was the early stretch of that sequence.
2. **Regret with true gains.** For the drift chain (multigen §5), compute the KL of the accepted candidate's record
   law against the base-candidate law per generation; show either that R3's light-tail bound covers the
   reported-minus-true gap there, or that the laws share no base and the KL slice does not cover reuse with gains.
3. **Reanchor as an operator.** Add a basis field to \(J\) in the composition model and \(\operatorname{Reanchor}_h\)
   writing it; prove it is a Rescore (writes \(J\) only), hence moves \(\rho\) with no ledger event (Prop 5); then
   prove that adding program (A)'s certificate level as a premise of rule (RO) restores typing \(\Leftrightarrow\)
   ledger on the ten-symbol alphabet, or exhibit a sequence where it does not.
4. **\(\beta_1\) made precise.** Prove that for category maps \(\gamma,\gamma'\) on \([n]\) the rational dimension of
   the fibre of cell-count vectors over fixed margins equals \(\beta_1(I(\gamma,\gamma'))\), so Prop 2c's failure
   set has exactly that many free parameters, the same count as a transport graph's independent holonomy loops by
   definition; this fixes the shared invariant as combinatorial, not as a shared theorem.
5. **An ASMP-10 instance with a closed Bayes error.** Freeze \(\mu\) as the drift chain, \(F_s\) as the reported-score
   history, \(C=p(i_G)\); compute \(B(F_s)\) exactly and decide whether the reported-score filtration is sufficient
   for \(C\) against the full chain state (under the null \(C\equiv p\) and the question is empty: a liveness check on R4).

*Evidence for §7–§8: documentary; item 1 is settled in `selection_law_kl_containment.md` (algebraic identities
plus finite checks); items 2–5 remain open.*
