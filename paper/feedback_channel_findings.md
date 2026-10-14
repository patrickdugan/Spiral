# What the feedback-channel programme has established

Draft 0.1 — 2026-10-14. A synthesis of the exact modules on this branch, written so a reader can see
the whole picture before opening any one note. Every statement below points to the note that proves or
checks it, and carries that note's evidence level: *algebraic identity* (proved for every parameter),
*finite verified example* (checked on enumerated cases only), or *synthetic mechanism result* (a property
of a toy chain). No model, policy, judge or grader was ever run. Every number is exact arithmetic on
declared quantities.

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
- **Score-only is not sealed.** A loop that can score patches on chosen subsets recovers which items
  failed from aggregate scores alone, by group testing, in at most *f*⌈log₂ *n*⌉ + 1 queries for *f*
  failures among *n* items. So the number of score queries must be recorded, not only the access class.
  *Algebraic identity* for the bounds, *finite verified example* for the exact minimum (L2).
- **Finer feedback is never worth less.** For the loop's choice of which candidate to keep, a channel is
  worth at least as much as any channel that factors through it, for every prior and utility: the
  garbling direction of Blackwell's ordering. *Algebraic identity* (L6).

## 3. When a reported score separates from the true one

- **A judge that shares the controller's errors.** Let the judge err with rate ε₁ on items the
  controller gets wrong and ε overall. Observed accuracy is a − ε + 2(1 − a)ε₁ for true accuracy *a*.
  It reaches the ceiling 1 − ε with no memorization at all exactly when ε₁ ≥ ½. A learned judge trained
  on the controller's outputs is where independence is least plausible. *Algebraic identity* (L4).
- **How much patching a ceiling check misses.** With clean accuracy 4/5 and judge error 1/10, a check for
  scores above the ceiling stays silent until 8/13 of the set is memorized blind, but only until 4/25 is
  patched when the loop knows which items failed. Between the two, the cost falls monotonically as the
  failure categories it can see get finer. *Algebraic identity*
  ([insertions](evaluation_feedback_insertions.md); [lattice](evaluation_feedback_lattice.md), Props 4–5).
- **Reuse inflates like a running maximum.** Keeping the best of *K* candidates for *G* generations on
  one reused set of *n* items, with no true differences between candidates, reports the maximum of
  *GK* + 1 draws. The phantom gain grows with *G*, with diminishing increments, and is bounded by
  √(ln(*GK* + 1)/(2*n*)). *Algebraic identity* ([multigen](evaluation_feedback_multigen.md); L5).
- **Perturbative candidates make it worse.** When each candidate is a small perturbation of the current
  incumbent, as a policy update is, first-generation inflation is lower, but the accumulated gap is
  higher: the loop hill-climbs the fixed items. At *n* = 8, *K* = 2 after 20 generations the gap is
  0.455 for strongly correlated candidates against 0.365 for independent ones. *Synthetic mechanism
  result* (multigen §5).
- **A threshold gate does not speed real progress.** When each accepted candidate is truly better by a
  fixed step, accepting any improvement is ahead of every threshold rule, in stochastic order, both in
  true level and in accepted count (multigen Props 8–9). What a gate does to the phantom gap depends on
  how true gains are distributed. A one-generation identity gives its sign (Prop 7). Over 20 generations
  the gate's gap is above the ungated one on every enumerated cell with fixed gains, and below it with
  decaying gains. So a gate is not a general remedy for reuse inflation. When an accepted candidate may
  gain nothing, the count ordering is proved only from states two steps below the target; further away,
  exact search found no counterexample. *Algebraic identity* for Props 7–9 and the two-step case;
  *synthetic mechanism result* for the gap orderings (§6).

## 4. Selection inside a divergence budget

Best-of-*K* selection is a point of the KL ball that alignment bounds use. For every finite score law and
every tie rule, KL(best-of-*K* ‖ base) ≤ ln *K* − (*K* − 1)/*K*. The KL bound this gives on the
selection gap is tight in the limit: the ratio of gap to bound has supremum one. *Algebraic identity*
([selection KL](selection_law_kl_containment.md), Theorems A–C). Whether that ratio approaches its limit
monotonically in *n* is proved for *K* = 2 and 3. For *K* ≥ 4 it holds on every case checked, up to
*K* = 100 and *n* = 400, and the limiting margin is positive by a cited expansion; why the *K* = 2 proof
fails there is located exactly.

## 5. Disclosure has structure

- **Leaks form a lattice.** Feedback channels are partitions of the records the judge could return,
  ordered by refinement. Two category leaks observed separately reveal exactly what one joint leak does
  if and only if the bipartite graph of overlapping categories is a forest. A cycle is precisely where
  the separate leaks hide what the joint leak shows. So a ledger must record what the loop saw jointly.
  *Algebraic identity* ([lattice](evaluation_feedback_lattice.md), Prop 2c).
- **Patching failures needs a search, not a rule.** Filling categories in order of failure rate
  maximizes expected hits at every patch count (Prop 3). But for the expected number of patches to reach
  a target, no index rule is optimal: the better of two categories can flip with the rest of the state
  (Prop 7). With one hit needed the optimum has a closed form, min over categories of
  (*n*ᶜ + 1)/(*F*ᶜ + 1) (Theorem 10). Beyond one hit, committing to a category until it hits is
  suboptimal, though by at most one part in 1,526 on the grid. The general optimum is a dynamic
  programme. *Algebraic identity* for Props 3, 7 and Theorem 10; *finite verified example* for the rest.
- **The ledger is the type system.** Over all 22,143 operator sequences of length at most four, a
  design is well typed exactly when its feedback ledger passes the audit. An offline
  rescoring of the readout set moves the readout gap like a memorizing feedback step and leaves no other
  trace. *Finite verified example* ([composition](evaluation_feedback_composition.md)).

## 6. Measuring the judge

- **The shared error is measurable.** A sealed gold-labelled sample, one read, a 2 × 2 table and exact
  binomial and Fisher tests estimate ε₁ with exact p-values and power
  ([judge measurement](judge_shared_error_measurement.md)).
- **Gold noise is a confound.** If the gold labels are themselves wrong at rate η, an independent judge
  looks correlated by exactly η(1 − η)(2a − 1)(1 − 2ε). So the gold's error rate must be declared.
  *Algebraic identity*.
- **Three raters identify that rate but cannot test independence.** In the symmetric model, a second
  independent grader beside the gold grader and the controller gives the gold's error rate from the
  three pairwise agreements. In the asymmetric model the three-rater fit is exactly identified and has
  no test of independence, so a grader that copies the gold grader is absorbed into the fit: at full
  copying it returns two perfect graders. *Algebraic identity*
  ([gold calibration](gold_calibration_second_grader.md), §§3–7).
- **A fourth grader makes it testable.** Four raters give exactly six testable equalities. A copying
  grader leaves a residual of ρ·V₁·c₃₄ on one of them, detectable even at a balanced prior where the
  three-rater check has no power. *Algebraic identity*; finite-sample tests of the six equalities are not
  derived (§8).
- **A joint statement for the gold error and ε₁.** Coverage 1 − 2α holds given two plug-ins, when the
  gold error is a grid point. At 742
  items an independent and a shared judge are told apart by the tests but their ε₁ ranges overlap; at
  4,000 the ranges are disjoint. *Finite verified example* (§9).

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

1. **The optimal patch policy beyond one hit.** It has no known structure. Whether computing it is hard is
   the natural complexity question; no reduction has been attempted.
2. **The approach to the best-of-*K* limit for *K* ≥ 4** needs a uniform proof for small *n*.
3. **Gate dominance when gains can be zero**, more than two steps below the target.
4. **Finite-sample tests** of the four-rater equalities, and the sampling law of the ε₁ estimate.
5. **Topology.** The one invariant genuinely shared with the RSITopology programme is the cycle rank of a
   graph, which here counts what separate category leaks cannot fix. The broader use of the word is
   nominal so far ([crosswalk](feedback_channel_rsitopology_crosswalk.md) §6).

## 9. Where to check

| Note | Module | Receipt |
|---|---|---|
| [training-signal limits](rl_training_signal_limits.md) | `evaluation_feedback_signal` | `signal_v0_1.json` |
| [lattice](evaluation_feedback_lattice.md) | `evaluation_feedback_lattice` | `lattice_v0_6.json` |
| [multigen](evaluation_feedback_multigen.md) | `evaluation_feedback_multigen` | `multigen_v0_5.json` |
| [composition](evaluation_feedback_composition.md) | `evaluation_feedback_composition` | `composition_v0_1.json` |
| [selection KL](selection_law_kl_containment.md) | `evaluation_selection_kl` | `selection_kl_v0_3.json` |
| [judge measurement](judge_shared_error_measurement.md) | `evaluation_judge_measurement` | `judge_v0_1.json` |
| [gold calibration](gold_calibration_second_grader.md) | `evaluation_gold_calibration` | `gold_v0_3.json` |

Modules are under `src/spiral_ln/`, receipts under `output/<module>/`. Each verifier script under `scripts/` regenerates its receipt, which
records the SHA-256 of its sources. The whole suite runs with
`PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests -q` (774 tests). The
[journey map](../docs/feedback_channel_journey_2026-10-11_13.md) records how each result was reached,
including the false claims that were found and corrected along the way.
