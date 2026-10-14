# What the feedback-channel programme has established

Draft 0.2 — 2026-10-14 (0.1 the same day). A synthesis of the exact modules, written so a reader can see
the whole picture before opening any one note. Every statement below points to the note that proves or
checks it, and carries that note's evidence level: *algebraic identity* (proved for every parameter),
*finite verified example* (checked on enumerated cases only), *synthetic mechanism result* (a property
of a toy chain), or *cited* (taken from the literature). No model, policy, judge or grader was ever run.
Every number is exact arithmetic on declared quantities.

Draft 0.2 adds two things. **Lean:** each proved result now links to a Lean 4 theorem in
[`lean/`](../lean/CLAIMS.md), with its fidelity to the note's statement (*full*, *special case* or
*supporting lemma*); every linked theorem depends only on the axioms `propext`, `Classical.choice` and
`Quot.sound`. A proved result without a link has not been formalized yet. **New results:** a fifth round
of work on the open problems, reported in §§3–6 and §8.

## 1. The frame

The [evaluation design calculus](evaluation_design_calculus.md) writes an evaluation as a game, a policy
class, data, a scoring rule, a judge, an access regime and a compute budget. The
[feedback insertions](evaluation_feedback_insertions.md) add one operator, `Feedback`, which lets a loop
read the judge's verdicts at one of three access classes: *sealed*, *score-only* (the aggregate score of
a set) or *item-level* (which items passed).

In that notation, reinforcement learning on environments is `Feedback` at item level, repeated over
generations. The question "does the RL paradigm keep yielding gains?" becomes two questions about that
channel. How much information does each round carry? And how much of the reported improvement is the
loop fitting the evaluation rather than getting better? The
[training-signal note](rl_training_signal_limits.md) states the conditions the paradigm's reported gains
rest on as five falsifiable axioms, A1 to A5, and derives a limit from each.

## 2. What a feedback channel can carry

- **Bits per episode.** A deterministic reward channel with *m* possible values gives at most log₂ *m*
  bits per episode. Outcome reward gives one bit; process reward on *T* steps gives up to *T*.
  *Algebraic identity* ([signal note](rl_training_signal_limits.md), L1).
  Lean: [`Signal.L1_card_le`](../lean/FeedbackChannel/Signal.lean#L112), full, through a counting lemma for
  every adaptive strategy.
- **Score-only is not sealed.** A loop that can score patches on chosen subsets recovers which items
  failed from aggregate scores alone, by group testing, in at most *f*⌈log₂ *n*⌉ + 1 queries for *f*
  failures among *n* items, and needs at least ⌈log C(*n*, *f*)/log(*f* + 1)⌉. So the number of score
  queries must be recorded, not only the access class. *Algebraic identity* for the bounds, *finite
  verified example* for the exact minimum (L2).
  Lean: [`Signal.L2_lower_bound`](../lean/FeedbackChannel/Signal.lean#L253), full (the lower bound).
- **Finer feedback is never worth less.** For the loop's choice of which candidate to keep, a channel is
  worth at least as much as any channel that factors through it, for every prior and utility: the
  garbling direction of Blackwell's ordering. *Algebraic identity* (L6).
  Lean: [`Signal.L6_garbling`](../lean/FeedbackChannel/Signal.lean#L517), full, and a stochastic version.

## 3. When a reported score separates from the true one

- **A judge that shares the controller's errors.** Let the judge err with rate ε₁ on items the
  controller gets wrong and ε overall. Observed accuracy is a − ε + 2(1 − a)ε₁ for true accuracy *a*.
  For every *a* < 1 it reaches the ceiling 1 − ε with no memorization at all exactly when ε₁ ≥ ½. A
  learned judge trained on the controller's outputs is where independence is least plausible.
  *Algebraic identity* (L4).
  Lean: [`Signal.L4_ceiling_iff`](../lean/FeedbackChannel/Signal.lean#L424), full.
- **How much patching a ceiling check misses.** With clean accuracy 4/5 and judge error 1/10, a check for
  scores above the ceiling stays silent until 8/13 of the set is memorized blind, but only until 4/25 is
  patched when the loop knows which items failed. Between the two, the cost falls monotonically as the
  failure categories it can see get finer. *Algebraic identity*
  ([insertions](evaluation_feedback_insertions.md); [lattice](evaluation_feedback_lattice.md), Props 4–5).
  Lean: [`Signal.L3_fixture`](../lean/FeedbackChannel/Signal.lean#L382) and
  [`PatchStatic.prop4_staticT`](../lean/FeedbackChannel/PatchStatic.lean#L207), full;
  [`PatchGreedy.prop5`](../lean/FeedbackChannel/PatchGreedy.lean#L336), full.
- **Reuse inflates like a running maximum.** Keeping the best of *K* candidates for *G* generations on
  one reused set of *n* items, with no true differences between candidates, reports the maximum of
  *GK* + 1 draws. The phantom gain grows with *G*, with diminishing increments, and is bounded by
  √(ln(*GK* + 1)/(2*n*)). *Algebraic identity* ([multigen](evaluation_feedback_multigen.md); L5).
  Lean: [`MultigenRunningMax.naive_reported_eq_max`](../lean/FeedbackChannel/MultigenRunningMax.lean#L102)
  and [`MultigenHoeffding.prop5_hoeffding`](../lean/FeedbackChannel/MultigenHoeffding.lean#L260), full.
- **Perturbative candidates make it worse.** When each candidate is a small perturbation of the current
  incumbent, as a policy update is, first-generation inflation is lower, but the accumulated gap is
  higher: the loop hill-climbs the fixed items. At *n* = 8, *K* = 2 after 20 generations the gap is
  0.455 for strongly correlated candidates against 0.365 for independent ones. *Synthetic mechanism
  result* (multigen §5).
- **What a threshold gate does, and when it can help.** Gating means accepting a candidate only when it
  clears a threshold. When every true gain has one positive size, accepting any improvement is ahead of
  every threshold rule, in stochastic order, in both true level and accepted count (multigen Props 8–9).
  Version 0.6 extends this to every gain law with a single positive gain value, {0, *g*} with any chance
  of gaining nothing (Prop 10). With two positive gain values it fails. In *n* = 3, *K* = 1, levels
  (0, ¼, ¼, ¾), gains {0, 1, 3} with chances (3/5, 1/5, 1/5), a gate that rejects a count of one at count
  zero is ahead in the chance of reaching the top count from generation 28, in expected count from
  generation 39, and in the limiting true level, 2909/3968 against 8058689/11073200: it filters the small
  gain and waits for the large one. What a gate does to the phantom gap also depends on the gain law: a
  one-generation identity gives its sign (Prop 7). *Algebraic identity* for Props 7–10; *finite verified
  example* for the counterexamples, which the lead re-derived with an independent chain.
  Lean: [`MultigenCountDominance.gated_expect_le`](../lean/FeedbackChannel/MultigenCountDominance.lean#L468)
  (Prop 9), [`MultigenGate.naive_sub_gate`](../lean/FeedbackChannel/MultigenGate.lean#L56) (Prop 7) and
  [`MultigenMixed.distance_two_nonneg`](../lean/FeedbackChannel/MultigenMixed.lean#L369), full; Props 8
  and 10 not yet formalized.

## 4. Selection inside a divergence budget

- **Best-of-*K* has a known KL cost.** For every finite score law and every tie rule,
  KL(best-of-*K* ‖ base) ≤ ln *K* − (*K* − 1)/*K*, strictly for *K* ≥ 2. The KL bound this gives on the
  selection gap is tight in the limit: the ratio of gap to bound has supremum one. *Algebraic identity*
  ([selection KL](selection_law_kl_containment.md), Theorems A–C).
  Lean: [`SelectionTieRules.theoremB_every_tie_rule`](../lean/FeedbackChannel/SelectionTieRules.lean#L188), full.
- **The approach to that limit is monotone.** For *K* = 2 the ratio's square grows by exactly
  1 + 1/(4*n*(*n* + 1)) per step, a theorem; *K* = 3 reduces to it. Draft 0.4 proves the monotone approach
  at every *n* for *K* = 4 to 30 by an effective second-order bound: |√*n*·D_*n* − δ_K| ≤ C_K/*n* for
  *n* ≥ 400 with every constant an exact rational upper bound, plus the exact sweep below 400. Its
  inputs from the literature (Robbins' Stirling bounds, Poisson summation) are marked *cited*. The lead
  checked the bound's prediction independently with exact values at *n* = 100, 400, 600 and 900.
  Lean: [`SelectionKTwo.a_strictMonoOn`](../lean/FeedbackChannel/SelectionKTwo.lean#L340) and
  [`SelectionKTwo.aSq_succ_div`](../lean/FeedbackChannel/SelectionKTwo.lean#L291), full for *K* = 2; *K* ≥ 4
  not yet formalized.

## 5. Disclosure has structure

- **Leaks form a lattice.** Feedback channels are partitions of the records the judge could return,
  ordered by refinement. Two category leaks observed separately reveal exactly what one joint leak does
  if and only if the bipartite graph of overlapping categories is a forest. A cycle is precisely where
  the separate leaks hide what the joint leak shows. So a ledger must record what the loop saw jointly.
  *Algebraic identity* ([lattice](evaluation_feedback_lattice.md), Prop 2c).
  Lean: [`LatticeJoin.prop2c`](../lean/FeedbackChannel/LatticeJoin.lean#L476), full, at channel level.
- **What the cycles cost.** The fibre of tables with given margins is the cycle space of that graph, of
  dimension β₁ = |*E*| − |*V*| + *c*, and the joint leak is exactly β₁ cell counts more than the separate
  one. Collision ratios and Bayes errors depend on more of the graph than β₁. *Algebraic identity*
  ([leak topology](leak_topology.md), Theorems 1–5); the lead checked Theorem 1 independently on 400
  random pairs. Lean: not yet formalized.
- **Where "topology" is literal and where it is not.** With three or more category maps, when the
  observation pattern has one minimal unobserved set, the fibre is a sum of top reduced homologies of
  links in the nerve of the block cover (Theorem 7). For separate observation an exact sequence gives
  the dimension (Theorem 8), but two triples of maps on six items with matching nerve homotopy data have
  separate fibres of dimension 0 and 1 (Counterexample 9, checked independently by the lead). There the
  word is nominal. Lean: not yet formalized.
- **Patching failures needs a search, not a rule.** Filling categories in order of failure rate
  maximizes expected hits at every patch count (Prop 3). But for the expected number of patches to reach
  a target, no index rule is optimal: the better of two categories can flip with the rest of the state
  (Prop 7). With one hit needed the optimum is the smallest (*n*ᶜ + 1)/(*F*ᶜ + 1) over categories with at
  least one failure (Theorem 10). With two hits needed it has a closed form too: commit to one category
  until it hits, then to the best finisher (Theorem 11). Committing until a hit is optimal at every state
  exactly when at most two hits are needed (Corollary 14): the first failure at three hits appears only
  at category size 14, and beyond, the commit policy loses up to about one part in 739 on the grids
  checked. *Algebraic identity* for Props 3, 7 and Theorems 10–11; *finite verified example* for the
  rest; the lead checked Theorem 11 against an independent dynamic programme on 1,160 random states.
  Lean: [`PatchGreedy.prop3_greedy`](../lean/FeedbackChannel/PatchGreedy.lean#L218),
  [`PatchWitness.prop7_own_counts`](../lean/FeedbackChannel/PatchWitness.lean#L2178) and
  [`PatchDP.theorem10`](../lean/FeedbackChannel/PatchDP.lean#L299), full; Theorem 11 not yet formalized.
- **The ledger is the type system.** Over all 22,143 operator sequences of length at most four, a
  design is well typed exactly when its feedback ledger passes the audit. An offline rescoring of the
  readout set moves the readout gap like a memorizing feedback step and leaves no other trace.
  *Finite verified example* ([composition](evaluation_feedback_composition.md)).

## 6. Measuring the judge

- **The shared error is measurable.** A sealed gold-labelled sample, one read, a 2 × 2 table and exact
  binomial and Fisher tests estimate ε₁ with exact p-values and power
  ([judge measurement](judge_shared_error_measurement.md)).
- **Gold noise is a confound.** If the gold labels are themselves wrong at rate η, an independent judge
  shows a measured shared-error excess, (ε₁′ − ε′)(1 − a′), of exactly η(1 − η)(2a − 1)(1 − 2ε). So the
  gold's error rate must be declared. *Algebraic identity*.
  Lean: [`Judge.gold_noise_excess`](../lean/FeedbackChannel/Judge.lean#L118), full.
- **Three raters identify that rate but cannot test independence.** In the symmetric model, a second
  independent grader beside the gold grader and the controller gives the gold's error rate from the
  three pairwise agreements. In the asymmetric model the three-rater fit is exactly identified and has
  no test of independence, so a grader that copies the gold grader is absorbed into the fit.
  *Algebraic identity* ([gold calibration](gold_calibration_second_grader.md), §§3–7).
  Lean: [`Raters.prop2_gold`](../lean/FeedbackChannel/Raters.lean#L146), full.
- **A fourth rater makes it testable.** Four raters give exactly six testable equalities. A copying
  grader leaves a residual of ρ·V₁·c₃₄ on one of them, detectable even at a balanced prior where the
  three-rater check has no power. *Algebraic identity* (§8).
  Lean: [`Raters.six_equalities`](../lean/FeedbackChannel/Raters.lean#L235),
  [`Raters.copy_grader_residual`](../lean/FeedbackChannel/Raters.lean#L473) and
  [`RatersJacobian.jac_rank`](../lean/FeedbackChannel/RatersJacobian.lean#L70), full.
- **Tests on finite samples are valid but weak.** An integer kernel on four items has expectation
  exactly 24 times the tetrad for every distribution. A block sign test built on it has size at most α
  for every law under which the tetrad vanishes, with no plug-in; a Cantelli test is valid over a
  stated region. Neither has useful power against copying at the planning size of 742 items; at 4,000
  the sign test reaches 0.21 to 0.93 for copy rates ¼ to 1. *Algebraic identity* for the sizes, *finite
  verified example* for the powers (§10). Lean: not yet formalized.
- **An interval for ε₁ with proven coverage.** Six conditionally binomial counts, Clopper–Pearson
  intervals (*cited*) and maps monotone in each coordinate give coverage at least 1 − α at every
  parameter of the symmetric model. The earlier joint statement's binomial plug-in understates the
  variance of the ε₁ estimate about 7.7-fold for an independent judge. *Algebraic identity* (§11). The
  bracketed asymmetric inversion is not monotone, by an exact witness; a certified enclosure replaces it
  (§12). Lean: not yet formalized.

## 7. What this says about the RL-scaling question

None of these limits bounds the true gain available from fresh environments with exact verifiers. What
they do is locate every route by which a reported gain can appear without a true one, and price each
route from quantities an evaluator can declare:

- the size of each scored set and how often it was reused (*n*, *G*, *K*);
- the access class, the number of score queries and patches, and the joint channel of any category-level
  signal;
- the judge's error and shared error rates, measured against gold whose own error rate is declared,
  with a fourth independent grader if independence is to be tested;
- a readout set that never fed the loop.

Given those, the largest phantom gain is computable, and anything above it is real. That is the
falsifiable form of the question: publish the ledger, and the bound either explains the reported gain or
it does not. Of the five published claims in the [atlas](rsi_claims_atlas.md), none supplies a
generation-over-generation gain for model weights on a sealed readout, and none publishes these counts.

## 8. What is open

1. **The optimal patch policy at three or more hits.** Committing is no longer optimal there, and no
   other structure is known. The decision problem is polynomial for a fixed number of categories or a
   fixed maximum size; whether it is hard in general is the natural complexity question, and no
   reduction has been attempted.
2. **Best-of-*K* for *K* > 40** at every *n*, and a symbolic proof of the margin identity
   δ_K = c(K)·E[M_K]/2, which is checked by quadrature to 10⁻⁹.
3. **Gating with two or more positive gain values.** Which such laws let a gate win is not
   characterized, and time-varying gain schedules remain finite checks.
4. **Finite-sample testing.** Only the first tetrad is tested, and no test has useful power at planning
   sizes. The full sampling law of the ε₁ estimate is not derived.
5. **Topology beyond the settled cases.** For separate observation of three or more maps the dimension
   is given by an exact sequence but is not a homotopy invariant; whether some other natural complex
   captures it is open.
6. **Lean.** Proved but not yet formalized: Theorem 11 and Corollary 14 (lattice), Props 8 and 10
   (multigen), the *K* ≥ 4 monotone approach, the leak-topology theorems, and gold calibration §§10–12.

## 9. Corrections in this round

Formalizing in Lean and checking against independent code found these, each now fixed in its note:

- Lattice Theorem 10's minimum ranges only over categories with at least one failure.
- Lattice Proposition 7's witnesses tied for optimal; new witnesses have unique optima.
- The commit policy's loss was not "below one part in a thousand": it reaches about one part in 739 just
  beyond the old grid.
- Multigen 0.5's "(L2)–(L3) finite beyond {0, 1}" is refuted by a two-gain counterexample, and draft 0.1
  of this note said a gate never speeds real progress, which holds only with one positive gain value.
- Selection D.5's product index starts at *j* = 1, and *K* = 8 does not inherit *K* = 4's status.
- The training-signal note's L1 incomparability needs *T* ≥ 2 and L4's ceiling condition needs *a* < 1;
  the judge note's "excess" named the wrong quantity in its fixture.

## 10. Where to check

| Note | Module | Receipt | Lean |
|---|---|---|---|
| [training-signal limits](rl_training_signal_limits.md) | `evaluation_feedback_signal` | `signal_v0_1.json` | [`Signal.lean`](../lean/FeedbackChannel/Signal.lean) |
| [lattice](evaluation_feedback_lattice.md) | `evaluation_feedback_lattice` | `lattice_v0_7.json` | [`Patch*.lean`, `Lattice*.lean`](../lean/CLAIMS.md) |
| [leak topology](leak_topology.md) | `evaluation_leak_topology` | `leak_topology_v0_1.json` | none yet |
| [multigen](evaluation_feedback_multigen.md) | `evaluation_feedback_multigen` | `multigen_v0_6.json` | [`Multigen*.lean`](../lean/CLAIMS.md) |
| [composition](evaluation_feedback_composition.md) | `evaluation_feedback_composition` | `composition_v0_1.json` | none |
| [selection KL](selection_law_kl_containment.md) | `evaluation_selection_kl` | `selection_kl_v0_4.json` | [`Selection*.lean`](../lean/CLAIMS.md) |
| [judge measurement](judge_shared_error_measurement.md) | `evaluation_judge_measurement` | `judge_v0_1.json` | [`Judge.lean`](../lean/FeedbackChannel/Judge.lean) |
| [gold calibration](gold_calibration_second_grader.md) | `evaluation_gold_calibration` | `gold_v0_4.json` | [`Raters*.lean`](../lean/CLAIMS.md) |

Modules are under `src/spiral_ln/`, receipts under `output/<module>/`. Each verifier script under
`scripts/` regenerates its receipt, which records the SHA-256 of its sources. The whole suite runs with
`PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests -q`. [`lean/CLAIMS.md`](../lean/CLAIMS.md)
lists all 202 formalized theorems; `lean/axioms_check.lean` prints their axioms. The
[journey map](../docs/feedback_channel_journey_2026-10-11_13.md) records how each result was reached,
including the false claims that were found and corrected along the way.
