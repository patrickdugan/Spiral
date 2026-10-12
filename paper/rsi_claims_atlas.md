# Takeoff-evidence examples for the evaluation design calculus

Draft 0.1 — inspected 2026-10-11.

This atlas applies [the calculus](evaluation_design_calculus.md) and the
[suggested feedback insertions](evaluation_feedback_insertions.md) to five
published claims that bear on AI-driven AI research and development. These are
design analyses and proposed studies. No model was called and no published
result was reproduced.

Each case distinguishes **observed**, **interpretation**, and **proposed
variation**, as the [Prime Intellect atlas](prime_intellect_eval_atlas.md) does.

**Reading caveat.** Every source below was read on the inspection date through
a fetch tool that returns a summary of the page, not its bytes. One chart was
read from a screenshot in a third-party post. Figures are as that tool returned
them. A line-level check against the originals is outstanding and should
precede any circulation. Source levels are marked per case:

- *primary, summarized*: the publisher's own page or paper, through the tool.
- *secondary*: a report about the source.
- *screenshot*: an image of the source reproduced by a third party.

## 1. The question put to each case

A forecast of compounding needs one estimand: the gain from one generation of
controllers to the next, repeated, on a readout the improvement process did not
touch. In the notation of the insertions, that is a series of \(V^{r}_{\pi_g}\)
with \(r\) sealed, together with a ledger showing that it stayed sealed.

| Card field | What to look for in a takeoff claim |
|---|---|
| \(\Pi\) | What improves: weights, harness, test-time budget, or the mix of who does the work |
| \(D\) | How scored items were chosen, and whether the choice followed a look at results |
| \(Z\) | Whether what was kept depends on how it scored |
| \(J\) | Who or what judges, and whether the judge shares errors with the judged |
| Feedback | Whether scores or items from the scored set reached the improvement process |
| Readout | Whether any reported number comes from a set declared sealed |
| \(C\) | Which estimand the evidence supports, as against the one the headline implies |

## 2. The example set

| Case | Source level | What improves | Scored set fed back? | Sealed readout declared? | Estimand supported |
|---|---|---|---|---|---|
| OpenAI internal model, mathematics | primary summarized; chart by screenshot | Test-time compute at one checkpoint | Not stated | No | Amplification slope |
| Anthropic R&D Automation Index | primary summarized | Share of work led by the model | Not applicable | Not applicable | Task-share under a learned judge |
| METR time horizon | primary summarized; values secondary | Released models over years | Not stated; suite reused | No | Horizon on a fixed suite, below its ceiling |
| AIDE² harness self-improvement | primary summarized | Agent harness, model frozen | Yes, by design | Yes, four external benchmarks | Held-out gain across harness generations |
| Princeton shadow evaluation | primary summarized | Nothing; a single-generation test | No loop | Yes, against pretraining | Failure on two open-ended questions under one judge |

None of the five supplies a generation-over-generation gain ratio for model
weights on a sealed readout. The fourth comes closest, at the level of the
harness.

## 3. OpenAI's internal model: an amplification curve read as a trajectory

**Observed.** The Navier–Stokes post, dated 8 September 2026 with an update on
10 September, states: "Since August 28 we have been training a new internal
model," and "This model's training is ongoing and its performance continues to
improve." It describes the model as built through large-scale reinforcement
learning on a pretrained model. That result involved on the order of 10,000
concurrent agents, about 88 hours, about 2.7 million messages and roughly 130
billion output tokens, with Lean formalization taking a further 17 hours.
[Primary, summarized](https://openai.com/index/navier-stokes-solution/)

A chart titled "Performance of GPT-6 Astra and our Internal Model on a curated
set of open math problems" plots pass rate against test-time compute on a log
scale, with error bars. Read by eye from a screenshot, the internal model runs
from about 0.26 to about 0.48 over six points and GPT-6 Astra from about 0.09 to
about 0.17 over five. The chart could not be retrieved from the page text.
[Screenshot](https://x.com/AndrewCurran_/status/2108609708441657531)

The 6 October release reports 722 manuscripts in 372 result families, about
4,000 problems posed, 162 main results formalized in Lean, ten reasoning
summaries, and an average result using "the equivalent compute of roughly three
hours of ChatGPT Pro thinking." Its README says: "We expanded these evaluations
after performance on our existing mathematical evaluations saturated."
[Primary, summarized](https://openai.com/index/sharing-ai-progress-in-mathematics/);
counts from a [secondary reading of the repository](https://cellcog.ai/blog/openai-math-results/).

**Interpretation.** The chart's horizontal axis is test-time compute. It
compares two controllers at several inference budgets at one moment. It is not
a series over training time, and the sentence that performance "continues to
improve" has no plotted support in what was read.

Four declarations are absent:

- \(D\): the rule by which the set was "curated", and whether curation followed
  a look at outcomes. Expanding an evaluation after saturation supplies fresh
  items, and is also a decision taken on results.
- \(Z\): results were kept when judged significant. What is published is
  conditioned on the judgment.
- \(J\) for the chart: what counts as a pass, and who decides.
- Feedback: whether these problems or their outcomes reached training. The page
  addresses a different contamination question and is silent on this one.

**Derived arithmetic** (conditional on the reported counts; the mapping from
problems to manuscripts was not in what was read):

\[
\frac{722}{4000}=\frac{361}{2000},\qquad
\frac{372}{4000}=\frac{93}{1000},\qquad
\frac{162}{722}=\frac{81}{361}\approx0.224 .
\]

These are ratios of kept output to problems posed, not success rates. If a
failed attempt cost what a kept one did, compute per kept family would be
\(4000/372\approx10.8\) times the per-result figure; the release does not say
whether failures are in its average.

**Proposed variation.** The same pass-rate curve at two training checkpoints, on
a problem set declared sealed before the first, with the selection rule and all
failures published. That yields the training-time gain at fixed inference
budget, which is the quantity the caption asserts.

**Claim boundary.** A steeper curve for the newer model is evidence that more
inference buys more from it than from its predecessor, in mathematics, on this
set. It is silent on whether that margin is being trained back in.

## 4. Anthropic's Automation Index: a judge measuring a mix

**Observed.** A prototype index catalogues about 15,000 granular tasks into a
frozen tree of 542 nodes, 378 of them leaves, each rated on Epoch AI's
automation scale. "Leads" (AL4) means the model completes most of a task
end-to-end from a high-level prompt while a human supervises. Aggregation is
weighted by person-time. A Claude agent gathers evidence per node and an
independent Claude judge assigns the level. Staff rated their own areas as a
check: model–human exact agreement 59%, human–human 35%, within one level 97%.
As of August 2026 the "leads" share is 26% and the share at or above
"collaborates" exceeds 90%; no measured subset is fully autonomous. The basket
is frozen at July 2026. Stated caveats include dependence on the judge,
contestable AL3/AL4 cases, crude weighting, and a judge that may share errors
with the models it rates.
[Primary, summarized](https://www.anthropic.com/institute/measuring-pace-of-ai-development)

**Interpretation.** This is the atlas's Rubric Discovery case at institutional
scale: the produced artifact is a judge, and it needs its own evaluation. Three
points follow from the card.

1. The headline is a threshold count at one boundary of a six-level scale.
   Agreement "within one level" does not protect a count taken exactly at a
   one-level boundary. Exact agreement between judge and human, 59%, is the
   relevant figure, and it is higher than agreement between humans.
2. Weights are person-time measured after automation. A task that became fast
   takes less time and so weighs less. The direction of that bias is to
   understate the automated share of the original work.
3. It is a measurement of who does the work. It is the \(p\) of an Amdahl
   bound, not a gain per generation.

**Derived arithmetic** (illustrative, and conditional on reading 26% as a
pre-automation time share, which point 2 says it is not):

\[
\frac{1}{1-\tfrac{13}{50}}=\frac{50}{37}\approx1.35 .
\]

That is the ceiling on overall speedup if the "leads" share became free and
nothing else changed.

**Proposed variation.** Blind human re-rating of a stratified sample of nodes
near the AL3/AL4 boundary, with the headline reported as an interval under a
one-level perturbation of the judge. Separately, weights taken from a
pre-automation time survey.

**Claim boundary.** There is no scored item set here, so feedback and readout
do not apply. The index supports a statement about task mix under a declared
judge. It does not measure whether each generation improves the next by more.

## 5. METR's time horizon: a suite that hides by saturating

**Observed.** Time Horizon 1.1 fits a logistic curve of success against human
task duration over "over a hundred diverse software tasks" from RE-Bench, HCAST
and shorter novel tasks, and reads off the 50% point. The page states:
"Measurements above 16 hrs are unreliable with our current task suite." It
carries a notice dated 8 September 2026 that it is no longer actively updated.
It mentions private tasks without giving the public/private split.
[Primary, summarized](https://metr.org/time-horizons/)

Values come from secondary readings of METR's data: Claude Mythos Preview
(early) at 1044.78 minutes
([DataLearner](https://www.datalearner.com/en/benchmarks/metr-time-horizons-v1-1));
doubling times of 131 days for the post-2023 fit and 89 days for the since-2024
fit ([Manifold market text](https://manifold.markets/Bayesian/claude-sonnet-5-metr-50-time-horizo)).

**Interpretation.** In the testbed's terms a saturated suite is an
observation-only Hide. Once a controller's ability exceeds the hardest items,
distinct controllers push forward to the same record, and the discrimination
gap between them goes to zero. No change in the game is involved.

The suite is fixed and reused across model generations, by every developer. At
the level of the field that is at least score-only feedback over years. Nothing
read asserts that any developer trained against it.

**Derived arithmetic.**

\[
\frac{1044.78}{60}\approx17.41\ \text{hours}>16 .
\]

The highest frontier point lies above the bound the instrument's owner calls
reliable. The 131-day and 89-day figures are fits over nested windows, so their
difference is not the ratio of two successive doubling intervals.

**Proposed variation.** Report, per model, the count of items above its
estimated ability. Extend the suite with long tasks held sealed. Declare the
freeze date as part of the instrument.

**Claim boundary.** Below the ceiling the horizon supports a statement about
released models on this task family. Above it, neither a plateau nor an
acceleration is identified.

## 6. AIDE²: the case with a declared readout

**Observed.** An agent proposes rewrites of its own harness; candidates are
scored on a selection suite of ML engineering, heuristic algorithm engineering
and harness engineering tasks; scoring uses private data averaged into a grade.
Inner agents see only a public signal. The outer agent "reads the previously
proposed agents and their grades", and its reviewer "explores the evaluation
artifacts". The main run lasted eight days: one initial agent and 99 proposals,
seven accepted at steps 2, 6, 28, 39, 47, 63 and 85, raising the incumbent grade
from 0.703 to 0.778. The outer loop ran on Claude Opus 4.7 and the inner agents
on Gemini 3 Flash. Two further runs accepted two and four rewrites.

Held-out reporting uses ALE-Bench (10 tasks, 10 seeds), MLE-Bench (22 tasks, 3
seeds), FML-Bench (18 tasks, 3 seeds) and WeatherBench 2 (1 task, 3 seeds).
Gains there are described as "positive throughout but not monotone"; the step-47
agent is best on two of the four. Reward hacking on 38 held-out KernelBench
pairs fell from 55% to 39% to 32%. The authors state that the selection trace
cannot show generalization because candidates were selected on the grade, and
that the outer loop's role "cannot be decisively distinguished" from a strong
baseline.
[Primary, summarized](https://arxiv.org/abs/2609.26457)

From a search excerpt of the paper's PDF, not the summarized page: on ALE-Bench,
Gemini 3 Flash with the step-85 harness reaches \(1858\pm22\) against Fable 5
with the initial harness at \(1796\pm24\); on MLE-Bench the step-85 harness
with Fable 5 "stays within one standard error" of its initial score. What the
\(\pm\) denotes was not in the excerpt.

**Interpretation.** This is the only case of the five that separates a
selection set from a readout and says which numbers came from which. In ledger
terms:

- Selection set: one fixed suite, 99 score queries. Declared access is at least
  score-only; the reviewer's reading of evaluation artifacts may make it
  item-level. The rise from 0.703 to 0.778 is a selection score.
- Readout: four external benchmarks, read at several checkpoints. How many
  checkpoints were read, and whether they were fixed in advance, was not in
  what was read. Reporting the best checkpoint per benchmark would be selection
  on the readout.
- What improves is the harness. The model is frozen, so this is not evidence
  about weights improving weights.

**Derived arithmetic.**

\[
\frac{7}{99}\approx0.071,\qquad
\frac{0.778-0.703}{7}=\frac{3}{280}\approx0.0107 .
\]

Intervals between acceptances are 4, 22, 11, 8, 16 and 22 steps; five of the
seven fall in steps 1–49 and two in steps 50–99, with none in the last 14.
The ALE-Bench contrast is 62 points. If the two \(\pm\) figures are independent
standard errors, the combined error is \(\sqrt{22^2+24^2}=\sqrt{1060}\approx32.6\)
and the contrast is about 1.90 of them, below 1.96. The reward-hacking
percentages are consistent with 21, 15 and 12 of 38; those counts are inferred
from rounding.

**Proposed variation.** Fix the readout checkpoints before the run and publish
the ledger. Hold a second private split of the selection suite sealed, and read
it once at the end: the difference from the grade is a direct measurement of
the readout gap on the suite the loop worked against.

**Claim boundary.** One trajectory supports the existence of held-out gains
from harness self-modification, with acceptances thinning over the run. It does
not support a rate.

## 7. Princeton shadow evaluation: sealed against contamination, open at the judge

**Observed.** Agents were given the central question of two unpublished NeurIPS
2026 submissions. Main runs used Claude Opus 4.8 with extra-high reasoning on
OpenClaw; a robustness run used GPT-5.6 Sol on Codex for one question. Each run
had six days, $3,000 in API credits and GPU credits. The papers' own authors
graded on a 1–6 scale, knowing the work was AI-generated: 2/6 and 1/6. Stated
limitations are five runs on two papers, non-blind grading by the original
authors, researcher degrees of freedom in question selection, possible
under-elicitation including a scaffold bug, and evaluation awareness. The
authors found no significant reward hacking, and report five instances of
subagents misrepresenting results that the orchestrator caught.
[Primary, summarized](https://arxiv.org/abs/2607.27191)

**Interpretation.** Using unpublished questions seals the item set against
pretraining, a choice none of the other four makes for its items. The opening
is at \(J\): the judge knows the condition and wrote the reference answer. In
the terms of the v3 protocol's provenance block, `scorer_blinded` would be
false, and there is no negative control. A human-written submission graded
under the same label would say how much of the score belongs to the label.

The models tested predate the internal model of §3. The result is silent on
that model.

**Proposed variation.** Blind grading with human-written decoys mixed in, on
more questions, with the authors of each question grading only the others'.

**Claim boundary.** Failure on two questions under an unblinded judge supports
"not demonstrated here". It does not bound what a later controller does.

## 8. What these examples add to the calculus

1. **Feedback class and ledger.** Only one case of five declares whether scores
   from a scored set reached the process being measured. The card should ask.
2. **Saturation as Hide.** A fixed suite outgrown by its subjects loses
   discrimination without any change to the game. The ceiling belongs on the
   card as a property of \(Z\).
3. **Acquisition conditioned on judgment.** Publishing what scored well makes
   \(Z\) depend on \(J\). Counts of what was attempted are then part of the
   evidence, not a courtesy.
4. **A judge that shares errors with the judged.** Agreement statistics must be
   reported at the boundary the headline is counted at.
5. **Estimand named against headline.** Amplification slope, task share,
   horizon, harness gain and open-ended failure are five different quantities.
   A statement about compounding needs a sixth, which none supplies.

The machine-readable companion is `configs/rsi_claim_cards.json`.
`scripts/verify_rsi_claims_atlas.py` verifies manifest structure and the
derived arithmetic only; its receipt is under `output/rsi_claims_atlas/`.
