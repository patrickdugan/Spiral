# The RL training signal as a feedback channel: limits from falsifiable axioms

Draft 0.1 — 2026-10-12.

This note types the reinforcement-learning paradigm in the
[evaluation design calculus](evaluation_design_calculus.md) and the
[feedback insertions](evaluation_feedback_insertions.md), states the
assumptions the paradigm's gains rest on as axioms, and derives from each
axiom an exact limit with the observation that would falsify the axiom. The
fixtures are in `src/spiral_ln/evaluation_feedback_signal.py`; the receipt
is under `output/evaluation_feedback_signal/`. No model was called.

Three companion notes carry the pieces delegated to separate runs:
[partial leakage as a lattice](evaluation_feedback_lattice.md),
[the selection gap across generations](evaluation_feedback_multigen.md), and
[Feedback's composition laws](evaluation_feedback_composition.md).

## 1. The question

The claim under test is the one Will Brown and Prime Intellect have argued
for publicly: that gains in agent capability come from reinforcement learning
on environments, that environments are the bottleneck, and that the same
environment abstraction serves evals, RL and data generation. His position
on compounding is narrower than the claim is sometimes read: in a July 2026
post he argued that architectures, optimizers, kernels and algorithms each
sit on a sigmoid, and that figures like a thousandfold R&D speedup are too
loosely defined to assess; in a May 2025 interview he said evals saturate
and always need replacing, that deterministic rewards are painful to build,
and that model-based judges are underexplored. His posts from 12 October
2026 could not be read from this session, so nothing below quotes them.

The dependency the note works along: RL gains depend on the training
signal; the training signal is a judgment fed back to the controller; a
judgment fed back is the calculus's `Feedback` operator, whose source set,
access class and ledger are declarable. So the paradigm's limits are
statements about a declared channel, and they can be checked from the
declaration without access to the model.

## 2. Typing RL in the calculus

An RL environment is an evaluation record \(\mathcal E=\langle
G,\Pi,D,Z,J,\mathcal A,C\rangle\) in which \(J\) is written back into
\(\Pi\) each generation:

\[
\text{RL on } D_{\text{train}}
= \operatorname{Repeat}_{G}\big(\operatorname{Feedback}_{D_{\text{train}},\,q}\big).
\]

Two access classes are in play, at different grains.

- **Episode grain.** The loop sees each episode's reward, so on the training
  set \(q=\text{item\_level}\): every RL run is item-level feedback on its
  training distribution. A run that sees only batch means is score-only.
- **Step grain.** Within an episode of \(T\) steps the reward is a channel
  on the step-outcome record \(r\in\{0,1\}^T\). Outcome reward is the
  two-block partition \(\{r=1^T\}\) against the rest; partial credit is the
  Hamming weight; a verifier that stops at the first error reports the
  position of the first zero; a process reward is the record itself.

`TrainingSignal.feedback_signature()` renders a declared setup in these
terms. Verifiable rewards are the case \(J\) deterministic and exact;
learned judges are the case \(J\) noisy, with an error rate and a share of
errors it has in common with the controller.

## 3. Axioms

Each is a condition the paradigm's reported gains rest on, and each names
the observation that would falsify it.

| | Axiom | Falsified by |
|---|---|---|
| A1 | The loop reads \(J\) only through the declared channel at the declared access class. | A ledger breach; or item-level knowledge shown with fewer score queries than L2 allows. |
| A2 | The judge's errors are independent of the controller's. | Observed accuracy at or above the noise ceiling with patch share below the L3 threshold; or a measured \(\varepsilon_1>\varepsilon\). |
| A3 | The readout set never feeds the loop. | A ledger breach on the readout set. |
| A4 | A patch changes one item's outcome and no other. | Collateral outcome changes on unpatched items (the nearest-neighbour simulation in `output/eval_reuse_toys/` showed them). |
| A5 | Candidates have equal true value (the null for selection inflation). | A measured gain on a sealed readout. |

A5 is the null hypothesis, not a belief; the inflation derived from it is
the part of a reported gain that needs no true gain to explain.

## 4. Limits

**L1. Bits per episode.** A deterministic channel with \(m\) images gives
at most \(\log_2 m\) bits per episode about the step record. Outcome reward
has \(m=2\); partial credit and first-failure have \(m=T+1\); process reward
has \(m=2^T\). To distinguish \(H\) hypotheses the loop needs at least
\(\lceil\log H/\log m\rceil\) episodes of that channel. For \(T=3\) steps,
identifying which steps fail (eight hypotheses) takes at least three
outcome-reward episodes and one process-reward episode. Partial credit and
first-failure are incomparable: neither factors through the other. Proof:
counting; `refines` checks factorization. *Finite verified example* for
\(T\le5\); the counting bound is an *algebraic identity*.

**L2. Score-only is item-level after finitely many queries.** Let the loop
test a patch on any subset of the \(n\) selection items and read the set's
score. Once it knows the failure count \(f\), each query returns one of
\(f+1\) values, so \(q\) queries distinguish at most \((f+1)^q\) of the
\(\binom nf\) failure sets. Hence
\[
q_{\min}(n,f)\ \ge\ \Big\lceil \log\tbinom nf\big/\log(f+1)\Big\rceil ,
\]
and recursive halving identifies the set in at most \(f\lceil\log_2
n\rceil+1\) queries. `exact_min_queries` computes the minimax value
exhaustively for \(n\le7\); it lies between the bound and the halving count
in every cell, and equals \(\lceil\log_2n\rceil\) for one failure. The
ledger's `score_queries` count therefore bounds the leak: below
\(q_{\min}\) the loop cannot have identified the failed items; above the
halving count a set declared score-only should be treated as item-level.
Between the two the loop sits somewhere in the lattice of partial leaks of
the companion note, which prices each position: with per-category failure
counts, the patches needed to reach the ceiling fall monotonically as the
categories refine, from \(\tfrac8{13}\) of the set at one category to
\(\tfrac4{25}\) at singletons, with the exact expected-value formula and
greedy optimality proven. One more result from that note bears on
disclosure: the channel induced by two category maps observed together is
strictly finer than the join of the two channels observed separately, so a
ledger must record what the loop saw jointly, not the partitions one at a
time. *Finite verified example*; the lower bound is an *algebraic identity*.

**L3. Noise ceiling and its blind range.** From the insertions: with judge
error \(\varepsilon\) and base observed accuracy \(v\), a ceiling check is
silent until a share \((1-\varepsilon-v)/(1-v)\) of the set is memorized at
random, or \(1-\varepsilon-v\) of the set is patched on failures. Under A1
and A2 a reported training score above \(1-\varepsilon\) is evidence of
memorization past that share.

**L4. A judge that shares errors with the judged.** Let the judge be wrong
with probability \(\varepsilon_0\) on items the controller gets right and
\(\varepsilon_1\) on items it gets wrong, with marginal
\(\varepsilon=a\varepsilon_0+(1-a)\varepsilon_1\). Observed accuracy is
\[
a(1-\varepsilon_0)+(1-a)\varepsilon_1
= a-\varepsilon+2(1-a)\varepsilon_1 ,
\]
which exceeds the independent-judge value by exactly
\(2(1-a)(\varepsilon_1-\varepsilon)\), and reaches the ceiling
\(1-\varepsilon\) exactly when \(\varepsilon_1\ge\tfrac12\), whatever
\(a\) and \(\varepsilon\). Feasibility caps \(\varepsilon_1\) at
\(\varepsilon/(1-a)\), so the ceiling is reachable without memorization iff
\(\varepsilon\ge(1-a)/2\): the judge must be wrong at least half as often
as the controller. In the fixture (\(a=\tfrac45\), \(\varepsilon=\tfrac1{10}\))
the independent judge reports \(\tfrac{37}{50}\); the most correlated
feasible judge reports \(\tfrac9{10}\), the ceiling, an inflation of
\(\tfrac4{25}\). So L3's check has a confound: a score at the ceiling is
memorization under A2, and A2 is what a learned judge trained on the
controller's outputs most plausibly violates. *Algebraic identity*, checked
on a rational grid.

**L5. Running-maximum inflation under reuse.** Under A5, keeping the best
of \(K\) candidates scored on a reused set overstates by the one-generation
gap of the selection law. Across \(G\) generations with the incumbent kept
and \(K\) fresh candidates each generation, the reported count is the
maximum of \(GK+1\) i.i.d. draws, so the gap is `selection_inflation(n,
GK+1, p)`: non-decreasing in \(G\), with diminishing increments, rising
toward \(1-p\) for fixed \(n\) and never stationary. (The composition note's
two-generation fixture carries the incumbent into a pool of \(K-1\) fresh
candidates and so reaches \(2K-1\) draws; the two conventions agree once the
pool size is fixed.) At \(p=\tfrac12\), \(n=8\), \(K=2\) the gap runs
\(0.147,\ 0.273,\ 0.321,\ 0.365\) at \(G=1,5,10,20\). Fresh blocks remove
the accumulation: a separate readout block gives gap zero, and reporting on
the selection block gives the one-generation gap at every generation. A
gate that accepts only gains above a noise margin lowers the gap under the
null, by a coupling argument, but the ordering can reverse once candidates
carry true gains, because the gate refuses those too. The companion
multi-generation note proves these as a Markov chain on the score lattice,
and finds that the simulations' "late gains look larger than they are"
prediction was a property of their decaying gain schedule, not of reuse.
*Algebraic identity* for the chain results; *synthetic mechanism result*
for the drift cells.

**L6. Finer feedback is worth at least as much.** For the loop's decision
of which candidate to keep, with any prior over candidate types and any
utility, the Bayes value under channel \(g\) is at least the value under
any \(f\) that factors through \(g\): a decision rule on \(f\)-images is a
decision rule on \(g\)-images. This is the garbling direction of
Blackwell's ordering. For incomparable channels each can be worth more:
partial credit beats first-failure when types differ in how many steps fail,
and loses when they differ in which step fails first. With exchangeable
steps partial credit is sufficient, so it ties process reward and beats
first-failure. *Algebraic identity* for the inequality; *finite verified
example* for the strict cases, cross-checked by enumerating every decision
rule.

## 5. What this says about the paradigm claim

Decompose "RL on environments keeps yielding gains" into the conditions
under which the reported gains are not phantom.

1. **Supply.** Fresh sealed items arrive at least as fast as the loop
   consumes them. Otherwise L2 turns score-only reuse into item-level reuse
   and L5 adds a running-maximum gap to every reported score. The
   environments-hub programme is a bet on this condition; the ledger
   quantities that test it are `score_queries` and `distinct_patched` per
   set, against the set's size, and the joint channel through which any
   category-level signal reached the loop. The composition note adds that
   the ledger is the only place this is visible: an offline rescoring of the
   readout set moves the readout gap by the same amount as a memorizing
   feedback step and leaves no other trace.
2. **Signal width.** The reward channel is fine enough for the credit the
   task needs. L1 says outcome reward supplies one bit an episode; process
   and turn-level rewards widen the channel, but every widening past a
   deterministic verifier needs a judge, which brings in the next condition.
3. **Judge independence.** L4 says a judge that shares half its errors with
   the controller reports the ceiling for a controller that has learned
   nothing. A learned judge trained on the same data as the controller, or
   on the controller's outputs, is the case where A2 is least plausible, and
   it is the case the interview called underexplored.

None of L1–L6 bounds the true gain available from fresh environments with
exact verifiers. The limits say where a reported gain can come from without
a true one, and what has to be published to rule that out: the set sizes,
the access class, the query and patch counts, the judge's error and shared
error rates, and the readout ledger. Of the five published claims in the
[atlas](rsi_claims_atlas.md), one publishes a readout at all and none
publishes the counts.

The position in the July post, that every component sits on a sigmoid, is
consistent with these limits and not derived from them. What the limits add
is that the reported curve and the true curve separate under reuse and
under a correlated judge, so a sigmoid in the reported curve is not
evidence either way about the true one until the ledger is published.

## 6. Not delivered

- No observed controller, environment or judge. The fixtures are exact
  arithmetic on declared quantities.
- The step-level channels assume a binary outcome per step and a
  conjunctive task; graded or path-dependent rewards need their own
  partition.
- L2's query model lets the loop patch any subset. A loop that can only
  retrain, not patch, has a noisier channel; the bound still holds as a
  lower bound.
- L4 treats a binary judge. A graded judge with correlated errors needs the
  same decomposition on a larger alphabet.
- A measurement procedure for \(\varepsilon_1\): grade a sealed sample with
  an independent judge and compare error overlap. Proposed, not built.
