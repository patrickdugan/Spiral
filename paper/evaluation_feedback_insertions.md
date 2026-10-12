# Feedback channel: suggested insertions for the evaluation design calculus

Draft 0.2 — 2026-10-12. Suggestions only. Draft 0.2 states the ceiling law for
failure-targeted patching as well as for patching chosen at random.

This file changes nothing in `evaluation_design_calculus.md` or
`evaluation_game_testbed.md`. Each block names a location in those documents,
offers text for it, and states what supports the text. Where a block is adopted,
its wording should be made the author's own. Where it is not, the executable
fixtures still stand by themselves.

The gap being addressed: the calculus already says that a judgment "shown during
play or used for learning ... also enters observations or controller updates"
(§2), and that frozen-controller sensitivity differs from sensitivity "after
retraining, selecting another controller" (§7). It has no operator for that
channel, no estimand for what the channel does to a score, and no record of how
often it was used. A self-improvement loop is that channel applied once per
generation.

## Evidence behind the suggestions

| Level | Source | What it supplies |
|---|---|---|
| Finite verified example | `src/spiral_ln/evaluation_game_feedback.py`, 30 tests, receipt under `output/evaluation_game_feedback/` | Access-class ordering, one-generation selection gap, noise-ceiling threshold, failed-item enrichment, ledger enforcement |
| Synthetic mechanism result | `output/eval_reuse_toys/` (two seeded simulations, predictions hashed before each run) | Multi-generation behaviour of the gap under score-only and item-level feedback |
| Not available | — | Any language-model loop, any observed controller |

The simulations are JavaScript, seeded, and not exact. Their prediction record
is 5 of 6 in the first run and 3 of 6 in the second, and both overpredicted the
size of the gap. One arm of the second run was added after its sealed results
were seen and is marked exploratory in its own files.

## A. §2, after "Maintain three distinctions"

Suggested fourth distinction:

> 4. A judgment that reaches whatever produces the next controller is a channel.
> Its source set, its access class, and the number of times it was used belong
> in the experiment record. A score measured on a set that fed this channel is a
> selection score. A capability claim needs a set that did not.

## B. §3, operator table

Suggested row:

| Proposed operator | Primary effect | Required detail |
|---|---|---|
| \(\operatorname{Feedback}_{s,q}\) | Controller roster/protocol of a later generation | Source set \(s\); access class \(q\in\{\text{sealed},\text{score-only},\text{item-level}\}\); whether the consumer selects among candidates or supplies a training input; generation scope. |

Suggested sentence beneath the table:

> Feedback is not \(\operatorname{Rescore}\), which is offline, and not
> \(\operatorname{Observe}\), which changes what the evaluator records. It reads
> \(J\) restricted to \(s\) and writes \(\Pi\) for the next generation. Declaring
> a set sealed while a score from it reaches the loop is ill-typed.

## C. §4, after the sentence on `Repeat` and reset/carry maps

> Generations joined by Feedback are not independent blocks. The carry map
> carries the controller, and with it whatever of \(s\) the channel transmitted.
> Aggregating a per-generation score across such generations as if each were a
> fresh draw of the same experiment mistakes the unit.

## D. §5, three laws and one observation

**Coarsening law.**

> The access classes are ordered: sealed is a deterministic function of the
> score, and the score is a deterministic function of the per-item outcomes.
> Total-variation distance between two controllers' feedback therefore cannot
> increase from item-level to score-only to sealed. Two controllers that fail
> different items with equal totals are separated completely by item-level
> feedback and not at all by a score.

Support: `access_order_fixture`; the ordering is checked for every pair of
distributions on a rational grid over two-item outcomes.

**Selection law.**

> Keeping the best of \(K\) candidates by score on \(s\), then reporting that
> score, overstates: \(\mathbb E[\max_k\hat S_k]\ge\max_k\mathbb E[\hat S_k]\).
> This is the same convexity as the mixture law, with the candidate index in
> place of the mixture component. For candidates of equal true value
> one half, two candidates and one item give a reported value of three quarters.

Support: `selection_inflation`, checked against independent enumeration of
every outcome matrix in seven small cells. Exact gaps for two candidates at
\(p=\tfrac12\) are \(\tfrac14\), \(\tfrac{35}{256}\), about 0.0700 and about
0.0352 at 1, 4, 16 and 64 items; multiplied by \(\sqrt n\) these are 0.250,
0.273, 0.280 and 0.282. The value \(1/(2\sqrt\pi)\approx0.2821\) is the
standard Gaussian figure for the larger of two draws. The fixture verifies the
listed cells and no limit.

Boundary: one generation, equal candidates, independent items. Accumulation
across generations is a simulation result, not an exact one.

**Ceiling law.**

> With labels flipped independently at rate \(\varepsilon<\tfrac12\), no
> predictor blind to the flips exceeds \(1-\varepsilon\) in expectation on
> observed labels. Let \(v\) be the controller's observed accuracy before any
> item of \(s\) is memorized. If it memorizes a share \(m/n\) of \(s\) chosen
> without regard to its outcomes, it scores \(m/n+(1-m/n)v\) on \(s\) and
> crosses the ceiling only when \(m/n>(1-\varepsilon-v)/(1-v)\). If it memorizes
> items it failed, which is what item-level feedback supplies, it scores
> \(v+m/n\) and crosses when \(m/n>1-\varepsilon-v\): the same threshold
> \((1-\varepsilon-v)/(1-v)\), now as a share of the failed items. Below the
> threshold a ceiling check is silent.

Support: `ceiling_detection_threshold` and
`targeted_ceiling_detection_threshold`. With clean accuracy \(\tfrac45\) and
\(\varepsilon=\tfrac1{10}\): \(v=\tfrac{37}{50}\). Memorizing at random, the
check is silent below \(\tfrac8{13}\) of the set. Patching failures, it is
silent below \(\tfrac4{25}\) of the set, which is \(\tfrac8{13}\) of the failed
items. Both formulas assume a memorized item has no effect on any other item.
The nearest-neighbour learner in the second simulation did not satisfy that,
and it also did not reliably absorb a patch: at \(n=4000\) it patched a quarter
of the set and its reported score stayed at 0.759, below the 0.90 ceiling.

**Observation on what item-level feedback selects.**

> An item the controller fails is more likely than an average item to carry a
> wrong label, whenever the controller is better than chance:
> \(\Pr[\text{flipped}\mid\text{failed}]=\varepsilon a/(\varepsilon a+(1-\varepsilon)(1-a))\),
> which exceeds \(\varepsilon\) exactly when \(a>\tfrac12\). Feeding failures
> back concentrates label noise in what the next controller is built from.

Support: `failed_item_noise_share`; \(\tfrac4{13}\) against a base rate of
\(\tfrac1{10}\) in the fixture. In the second simulation the measured share
among patched items was 20–29% against the same 10% base rate. This is the
reason the unchecked answer in the Proposer–Solver recipe (atlas §11) matters
once its output is fed back.

Suggested closing sentence, matching the section's existing last line:

> No unconditional claim is made that feedback lowers readout performance. In
> the simulations, score-only selection of fresh training batches raised it.

## E. §7, after the definition of the order effect

> For a controller \(\pi_g\) produced with feedback from \(s\), and a sealed set
> \(r\) from the same sampling law, define the readout gap
> \(\rho_g=V^{s}_{\pi_g}-V^{r}_{\pi_g}\). It compares two measurements of one
> controller, not two designs, so it is not a design difference. A gain series
> computed on \(s\) estimates the change in value plus the change in \(\rho\).

## F. §11, the evaluation card

Suggested amendment to item 6:

> ... and whether any score feeds back into play *or into the production of a
> later controller*.

Suggested additional item:

> 10. **Feedback ledger:** for each evaluation set, its role (selection or
> readout), declared access class, score queries, items fed back, number and
> generation of readouts, and the rule that retires it.

## G. `evaluation_game_testbed.md`, estimand table

Suggested fifth row:

| Estimand | Definition | It is not |
|---|---|---|
| Readout gap | \(\rho=V^{s}_\pi-V^{r}_\pi\), with \(s\) having fed judgment to the loop and \(r\) sealed | A baseline gain, or evidence that capability changed |

Suggested section, placed after "Executable confirmation and adversarial
checks":

> ### Feedback channel and multi-generation ledger
>
> `evaluation_game_feedback.py` extends the single split enforced by `confirm()`
> to a sequence of generations. Sets are declared with a role and an access
> class. Events record a score reaching the loop, items reaching the loop, or an
> experimenter reading a sealed set. Malformed declarations and malformed
> events raise: a readout set not declared sealed, identifiers shared across
> sets, or a readout event naming a selection set (a readout is by definition
> a read of a sealed set; a selection set is read through score queries).
> Breaches of a well-formed declaration are recorded instead, and move the
> readout endpoint to `not_evaluated`: a breach is a finding about the run.
> A sealed read transmits nothing and is not an event, so `Feedback` at sealed
> access is always well-typed. The [composition note](evaluation_feedback_composition.md)
> checks that, under these rules, well-typed sequences are exactly those the
> ledger reports as respected, on every sequence of length at most four over a
> nine-operator alphabet. Reads of the
> sealed set are budgeted, since a stop-or-continue decision taken on a readout
> is itself adaptive. Identifiers detect recorded overlap. They do not certify
> independence.
>
> ```powershell
> $env:PYTHONPATH = "src"
> python scripts/verify_evaluation_game_feedback.py --output output/evaluation_game_feedback/feedback_v0_2.json
> python -m pytest tests/test_evaluation_game_feedback.py -q
> ```

## H. What is not delivered

- `Feedback` is not implemented against `hive_lab` adapters or any external
  policy. The module checks declarations and arithmetic.
- No loop with a language model has been run. The first observed-controller
  study would pair a small model with a declared selection set and a sealed
  readout, and report the ledger.
- Partial leakage, where the loop learns failure categories and not items, is
  now treated in [evaluation_feedback_lattice.md](evaluation_feedback_lattice.md):
  category channels form a lattice of partial leaks, with the cost of each
  position exact. Composition with the other operators is in
  [evaluation_feedback_composition.md](evaluation_feedback_composition.md),
  and the selection gap across generations in
  [evaluation_feedback_multigen.md](evaluation_feedback_multigen.md).
- The simulations fix one parameter set each. No sweep over candidate count,
  decay rate, or label-noise rate was run.
