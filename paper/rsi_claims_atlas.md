# Takeoff-evidence examples for the evaluation design calculus

Draft 0.2 — inspected 2026-10-11; figures checked against full source text the
same day.

This atlas applies [the calculus](evaluation_design_calculus.md) and the
[suggested feedback insertions](evaluation_feedback_insertions.md) to five
published claims that bear on AI-driven AI research and development. These are
design analyses and proposed studies. No model was called and no published
result was reproduced.

Each case distinguishes **observed**, **interpretation**, and **proposed
variation**, as the [Prime Intellect atlas](prime_intellect_eval_atlas.md) does.

**Reading note.** Draft 0.1 was written from a fetch tool that returns a
summary of each page, with one chart read by eye from a screenshot and several
figures taken from secondary pages. For draft 0.2 every figure attributed to a
source below was checked against the source's full text in a browser, or
against the data embedded in the source's page. The secondary pages and the
screenshot are superseded and no longer cited. §9 lists what the check changed.
Source levels are marked per case:

- *primary*: the publisher's own page, paper or repository, read in full.
- *primary, embedded data*: the data behind a chart or table on the
  publisher's page.

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
| OpenAI internal model, mathematics | primary; chart from embedded data | Test-time compute at one checkpoint; the controller was also replaced during the run | Within the run, yes; into training, not stated | No | Amplification slope |
| Anthropic R&D Automation Index | primary | Share of work led by the model | Not applicable | Not applicable | Task-share under a learned judge |
| METR time horizon | primary; values from embedded data | Released models over years | Not stated; suite reused | No | Horizon on a fixed suite, below its ceiling |
| AIDE² harness self-improvement | primary | Agent harness, model frozen | Yes, by design | Yes, four external benchmarks | Held-out gain across harness generations |
| Princeton-led (CRUX) shadow evaluation | primary | Nothing; a single-generation test | No loop | Yes, against pretraining | Failure on two open-ended questions under one judge |

None of the five supplies a generation-over-generation gain ratio for model
weights on a sealed readout. The fourth comes closest, at the level of the
harness, and its held-out gains at a fixed model are large relative to their
standard errors.

## 3. OpenAI's internal model: an amplification curve read as a trajectory

**Observed.** The Navier–Stokes post, dated 8 September 2026 with an update on
10 September, states: "Since August 28 we have been training a new internal
model," and "This model's training is ongoing and its performance continues to
improve." It describes the model as built through large-scale reinforcement
learning on a pretrained model. That result involved on the order of 10,000
concurrent agents, about 88 hours, about 2.7 million messages and roughly 130
billion output tokens, with Lean formalization taking a further 17 hours.
Two details of the run bear on feedback. Partway through, OpenAI moved the
agents to a further-trained version of the internal model. And it
cross-pollinated agent groups, using Codex to turn each group's intermediate
results into follow-up prompts; the group that found the result was guided
this way.
[Primary](https://openai.com/index/navier-stokes-solution/)

A chart titled "Performance of GPT-6 Astra and our Internal Model on a curated
set of open math problems" plots pass rate against test-time compute on a log
scale, with error bars. Its data is embedded in the page. The internal model
runs from 0.262 to 0.474 over six points, at relative compute 2.6 to 93; GPT-6
Astra runs from 0.084 to 0.170 over five points, at 1.4 to 31. Error bars are
one standard error. Every pass rate is a whole multiple of 1/382, which fits
382 scored attempts, for example 191 problems tried twice; the page does not
say which.
[Primary, embedded data](https://openai.com/index/navier-stokes-solution/)

The 6 October release reports ten reasoning summaries and an average result
using "the equivalent compute of roughly three hours of ChatGPT Pro thinking."
The repository README lists 719 manuscripts in 372 families from about 4,000
problems posed, and states that roughly 42% of top-line results are formalized
in Lean; the history file gives 300 of 719. The release went out with 722
manuscripts. On 7 October a sign error led OpenAI to withdraw three and revise
fourteen others. The README also says that some outputs build on earlier
results produced by the models, and that results entered the catalogue only if
judged significant enough. Its README says: "We expanded these evaluations
after performance on our existing mathematical evaluations saturated."
[Primary](https://openai.com/index/sharing-ai-progress-in-mathematics/);
[repository](https://github.com/openai/math) and
[history](https://github.com/openai/math/blob/main/history.md).

**Interpretation.** The chart's horizontal axis is test-time compute. It
compares two controllers at several inference budgets at one moment. It is not
a series over training time, and the sentence that performance "continues to
improve" has no plotted support on the page. At matched compute near 12–13
units the internal model passes 0.382 against GPT-6 Astra's 0.144. Because the
controller was replaced during the Navier–Stokes run, that result is not a
single-checkpoint measurement either.

Three declarations are absent, and a fourth is only partly made:

- \(D\): the rule by which the set was "curated", and whether curation followed
  a look at outcomes. Expanding an evaluation after saturation supplies fresh
  items, and is also a decision taken on results.
- \(Z\): results were kept when judged significant. What is published is
  conditioned on the judgment, and three withdrawals a day after release
  measure some of what that judgment let through.
- \(J\) for the chart: what counts as a pass, and who decides.
- Feedback: within the run the channel is declared and item-level.
  Intermediate results were fed back into prompts, outputs build on earlier
  outputs, and the controller was replaced partway. Whether these problems or
  their outcomes reached training is not stated. The Navier–Stokes page
  addresses a different contamination question.

**Derived arithmetic** (conditional on the reported counts; the mapping from
problems to manuscripts is not given):

\[
\frac{719}{4000},\qquad
\frac{372}{4000}=\frac{93}{1000},\qquad
\frac{300}{719}\approx0.417,\qquad
\frac{3}{722}\approx0.004 .
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
set. It is silent on whether that margin is being trained back in, and the
run that produced the headline result used at least two checkpoints.

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
[Primary](https://www.anthropic.com/institute/measuring-pace-of-ai-development)

**Interpretation.** This is the atlas's Rubric Discovery case at institutional
scale: the produced artifact is a judge, and it needs its own evaluation. Three
points follow from the card.

1. The headline is a threshold count at one boundary of a six-level scale.
   Neither published agreement figure is the one it needs. Exact agreement,
   59%, is a lower bound on how often judge and human put a node on the same
   side of the AL3/AL4 line. Agreement within one level, 97%, does not bound it
   either way, since AL3 against AL4 is within one level. The headline needs
   agreement on that binary call and the direction of the disagreements:
   disagreements that cancel leave the share unbiased.
2. Weights come from staff weeks sampled in July 2026. Each sampled person's
   week is one unit, split evenly across the tasks they worked on. That counts
   tasks touched, not time spent, so a task that became faster does not lose
   weight for that reason. The scheme has a different blind spot: work that no
   sampled person touched in a sampled week never enters the basket. Fully
   delegated work is the most likely to be missed, so the finding that no
   subset is fully autonomous partly reflects how the basket was built.
3. It is a measurement of who does the work. It is the \(p\) of an Amdahl
   bound, not a gain per generation.

**Derived arithmetic** (illustrative only: 26% is a share of task-touch
weights, not of time):

\[
\frac{1}{1-\tfrac{13}{50}}=\frac{50}{37}\approx1.35 .
\]

That is the ceiling on overall speedup if the "leads" share became free and
nothing else changed.

**Proposed variation.** Blind human re-rating of a stratified sample of nodes
near the AL3/AL4 boundary, with the headline reported as an interval under a
one-level perturbation of the judge. Separately, weights from a time-use
survey, compared with the task-touch weights.

**Claim boundary.** There is no scored item set here, so feedback and readout
do not apply. The index supports a statement about task mix under a declared
judge. It does not measure whether each generation improves the next by more.

## 5. METR's time horizon: a suite that hides by saturating

**Observed.** Time Horizon 1.1 fits a logistic curve of success against human
task duration over "over a hundred diverse software tasks" from RE-Bench, HCAST
and shorter novel tasks, and reads off the 50% point. The page states:
"Measurements above 16 hrs are unreliable with our current task suite." It
carries a notice dated 8 September 2026 that it is no longer actively updated.
It mentions private tasks without giving the public/private split. METR added
the 16-hour notice on 8 May 2026, in the same update that added Claude Mythos
Preview (early).
[Primary](https://metr.org/time-horizons/)

The page embeds its data. Claude Mythos Preview (early), released 7 April
2026, has a 50% horizon of 1044.78 minutes, with an interval of 508.9 to
3304.3 minutes, and an average score of 0.852 on the suite. METR's
fitted doubling time for models from 2023 on is 128.7 days, with an interval of
104.4 to 158.0; a stitched all-time fit gives 187.8 days. No fit restricted to
2024 onward is published. The page does not state the level of its intervals.
[Primary, embedded data](https://metr.org/time-horizons/)

**Interpretation.** In the testbed's terms a saturated suite is an
observation-only Hide. Once a controller's ability exceeds the hardest items,
distinct controllers push forward to the same record, and the discrimination
gap between them goes to zero. No change in the game is involved.

The suite is fixed and reused across model generations and developers, and its
scores are published. At the level of the field that is at least score-only
feedback over years. Nothing read asserts that any developer trained against
it. An average score of 0.852 for the top model is consistent with a suite
near saturation.

**Derived arithmetic.**

\[
\frac{1044.78}{60}\approx17.41\ \text{hours}>16,\qquad
\frac{508.9}{60}\approx8.48<16<\frac{3304.3}{60}\approx55.07 .
\]

The highest frontier point lies above the bound the instrument's owner calls
reliable, and METR said so when it published the point. Its interval runs from
about half the bound to more than three times it.

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
pairs fell from 55% to 39% to 32%, against 39% for the human-engineered agent.
The authors state that the selection trace cannot show generalization because
candidates were selected on the grade, and that the outer loop's role "cannot
be decisively distinguished" from a strong baseline. The two evolved agents
reported on the external benchmarks are fixed by position: the incumbent within
the first 50 nodes (step 47) and the final incumbent (step 85). About a quarter
of the graded rewrites that were rejected beat the incumbent on the signal the
agent could see and lost on the private grade.
[Primary](https://arxiv.org/html/2609.26457v1)

Table 1 reports the external benchmarks with one model per benchmark held
fixed across harnesses, and \(\pm\) one standard error of the benchmark mean. On ALE-Bench the initial harness scores
\(1536\pm33\), step 47 \(1713\pm26\) and step 85 \(1790\pm9\). A separate
comparison across models, at a $20 budget per run, has Gemini 3 Flash with the
step-85 harness at \(1858\pm22\) against Fable 5 with the initial harness at
\(1796\pm24\). On MLE-Bench, with Fable 5, the step-85 harness is within one
standard error of the initial one.

**Interpretation.** This is the only case of the five that separates a
selection set from a readout and says which numbers came from which. In ledger
terms:

- Selection set: one fixed suite, 99 score queries. Declared access is at least
  score-only; the reviewer's reading of evaluation artifacts may make it
  item-level. The rise from 0.703 to 0.778 is a selection score.
- Readout: four external benchmarks, read at two evolved checkpoints chosen by
  position, not by readout score. Both are reported on every benchmark, not the
  best per benchmark, which is the reporting a ledger asks for. Whether the
  positions were fixed before the run is not stated.
- The quarter of rejected rewrites that won on the visible signal and lost on
  the private grade measures how far the loop's two signals diverge. It is the
  within-task analogue of the readout gap.
- What improves is the harness. The model is frozen, so this is not evidence
  about weights improving weights.

**Derived arithmetic.**

\[
\frac{7}{99}\approx0.071,\qquad
\frac{0.778-0.703}{7}=\frac{3}{280}\approx0.0107 .
\]

Intervals between acceptances are 4, 22, 11, 8, 16 and 22 steps; five of the
seven fall in steps 1–49 and two in steps 50–99, with none in the last 14.
At a fixed model, step 85 against the initial harness differs by 254 points
on ALE-Bench. Treating the two standard errors as independent, that is
\(254/\sqrt{33^2+9^2}=254/\sqrt{1170}\approx7.4\) standard errors. The same
calculation gives about 3.5 on MLE-Bench, 2.6 on WeatherBench 2 and 3.4 on
FML-Bench. Runs on the same tasks are paired, so these figures are likely
conservative. The cross-model ALE-Bench contrast is 62 points against a
combined error of \(\sqrt{22^2+24^2}=\sqrt{1060}\approx32.6\), about 1.90. It
sets a harness gain against a model gain and measures neither. The
reward-hacking percentages are consistent with 21, 15 and 12 of 38; those
counts are inferred from rounding.

**Proposed variation.** Declare the readout positions before the run and
publish the ledger. Hold a second private split of the selection suite sealed,
and read it once at the end: the difference from the grade is a direct
measurement of the readout gap on the suite the loop worked against.

**Claim boundary.** One trajectory supports the existence of held-out gains
from harness self-modification, large relative to their standard errors at a
fixed model, with acceptances thinning over the run. It does not support a
rate.

## 7. Princeton-led shadow evaluation: sealed against contamination, open at the judge

**Observed.** Agents were given the central question of two unpublished NeurIPS
2026 submissions. Main runs used Claude Opus 4.8 with extra-high reasoning on
OpenClaw; a robustness run used GPT-5.6 Sol on Codex for one question. Each run
had six days, $3,000 in API credits and GPU credits. The papers' own authors
gave overall scores out of 6, knowing the work was AI-generated: 2/6 and 1/6.
The five runs were two pilots without extended reasoning, two main runs and the
robustness run. The paper records three human interventions during a run,
including a fix to a harness bug and a 24-hour deadline extension. Stated
limitations are five runs on two papers, non-blind grading by the original
authors, researcher degrees of freedom in question selection, possible
under-elicitation, and evaluation awareness. The authors found no significant
reward hacking, and report five instances of subagents misrepresenting results
that the orchestrator caught. The author list spans Princeton and about ten
other institutions.
[Primary](https://arxiv.org/html/2607.27191v1)

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

1. **Feedback class and ledger.** Two cases of five declare a feedback channel,
   and only one pairs it with a sealed readout. In the other the channel runs
   within a single effort, and the controller was replaced partway. The card
   should ask for the channel, the readout, and any change of controller.
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
6. **The version read.** OpenAI's repository withdrew and revised manuscripts a
   day after release. A card should record the version of a source it read.

The machine-readable companion is `configs/rsi_claim_cards.json`.
`scripts/verify_rsi_claims_atlas.py` verifies manifest structure and the
derived arithmetic only; its receipt is under `output/rsi_claims_atlas/`.

## 9. Corrections from draft 0.1

The check against full source text changed these points.

| Case | Draft 0.1 | Draft 0.2 |
|---|---|---|
| OpenAI | 722 manuscripts; 162 formalized in Lean, a share of about 0.224 | 719 after three withdrawals on 7 October; about 42% of top-line results formalized, 300 of 719 |
| OpenAI | Feedback not stated | Declared within the run: intermediate results fed back, outputs built on earlier outputs, controller replaced partway |
| OpenAI | Chart values read by eye from a screenshot | Exact values from the page's embedded data; by-eye values were close |
| Anthropic | Weights are post-automation person-time, so a task that became fast weighs less | Weights split each sampled person-week evenly across tasks; that mechanism does not apply |
| Anthropic | Exact agreement, 59%, is the relevant figure | 59% is a lower bound on agreement at the AL3/AL4 line; the binary agreement is not published |
| METR | Doubling times of 131 and 89 days, from a secondary page | 128.7 days from 2023 on, from METR's data; no fit from 2024 on is published |
| AIDE² | Meaning of \(\pm\) unknown; ALE-Bench contrast of 1.90 standard errors | \(\pm\) is one standard error of the benchmark mean; 1.90 is a cross-model contrast, and fixed-model gains run from 2.6 to 7.4 standard errors |
| AIDE² | Number of readout checkpoints unknown | Two, fixed by position |
