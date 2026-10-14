# The feedback-channel programme: a journey log for auditors

Written 2026-10-13 by the Claude Code session that produced the branch
`feedback-channel-and-rsi-atlas`. This document is the map; the territory is
the session log under `docs/session_logs/2026-10-11_feedback_channel/`
(conversation transcript, sixteen subagent transcripts, tool results),
narrowed to this investigation and redacted as its README describes. Every claim below can be
checked against a commit on the branch and a receipt under `output/`.

## 1. What was asked

1. **2026-10-11.** Patrick forwarded a patch produced by a separate cloud
   session: a `Feedback` operator for the evaluation design calculus, an
   atlas applying it to five published takeoff claims, and two seeded toy
   simulations. He asked whether it could be pushed to the public repository.
2. **2026-10-12.** He asked whether the work had drifted from his aim, the
   *mathematics of evaluation notation*, and then set the research question:
   whether Will Brown's reinforcement-learning paradigm is overestimated,
   approached through the training signal as a declared feedback channel,
   with topology, decision theory, graph theory on Markov decision chains,
   complexity, and the white-boxing of evaluation design as falsifiable axioms.
   He asked for subagents on the open problems.
3. **"lattice and push"**, then **"proceed in that order"** (five items), then
   **"proceed"** (four items), then **"proceed, don't worry about Will"** (five
   items), then **"proceed, also upload the log"** (this document and the raw
   export), then **"cont"** after Patrick switched the session's model from
   `claude-fable-5-1` to `claude-opus-5-5` when the Fable usage limit had
   stopped two subagents (§3).

Will Brown's posts of 2026-10-12 were never read: X walls the profile, the
Nitter mirrors are shut down, and the syndication endpoint rate-limits
anonymous requests. The signal note cites his July 2026 post and a 2025
interview instead and says so.

## 2. The commits, in order

| Commit | Date | What it did |
|---|---|---|
| `a9b9a91` | 10-12 | The forwarded patch, applied unchanged after verification (hashes, 128 tests, receipts, simulations reproduced; one simulation differs in the last float digit on this machine). |
| `662557c` | 10-12 | Atlas draft 0.2 after a line-level check of every source in the browser pane, replacing a summarizer and a screenshot. Six figures corrected (see §4). Ceiling law extended to failure-targeted patching: 4/25 of the set, not 8/13. |
| `b7b3ee1` | 10-12 | Four exact modules from the first round of delegation: training-signal limits (axioms A1–A5, limits L1–L6), the leak lattice, the multi-generation chain, the composition laws. 382 tests. |
| `3ff5b09` | 10-13 | Lattice 0.2: meets preserved, joins preserved iff the intersection graph is a forest, optimal adaptive schedule monotone; greedy suboptimal. Pushed to the public origin at Patrick's word. |
| `d988c99` | 10-13 | Lattice 0.3: no index rule is optimal (preference reversals); the optimal first patch can have a lower rate. |
| `a004d89` | 10-13 | Judge shared-error measurement procedure; crosswalk to the RSITopology problem set (no exact instance in either direction). |
| `4401d78` | 10-13 | Multigen 0.2: Hoeffding bound on the running maximum; correlated candidates raise the accumulated gap; the one-generation gate theorem. |
| `fc62b75` | 10-13 | Lattice 0.4: pair-commutation lemma; survey of what structure the optimal patch lacks. |
| `8ddec92` | 10-13 | Selection law inside the KL slice for every parameter: tie rules, containment (Beirami's radius derived, tied case covered), DV bound, sup of the ratio is 1. |
| `413f815` | 10-13 | Gold calibration from a second independent grader: three-rater identities, constraints, the copy-grader false finding. |
| `3ec8bab` | 10-13 | Multigen 0.3: gate dominance proven for the true value; count finite. |
| `a5ab4ff` | 10-13 | Lattice 0.5: one hit in closed form (Theorem 10); two grid regularities refuted; a prior claim corrected (§4). |
| `70f6f27` | 10-13 | Selection KL 0.2: the approach to c_K monotone for K = 2, 3; finite beyond. |
| `0f583ee` | 10-13 | Multigen 0.4: count dominance proven for every threshold rule. |
| `f1b9dad` | 10-13 | Gold calibration 0.2: exact sampling law of the gold-error estimate; the asymmetric three-rater model and its absence of any independence test. |
| `6518851` | 10-13 | Lattice 0.6: committing to a category until it hits is suboptimal beyond one hit, by at most one part in 1,526 on the grid. |
| `ca6ba24` | 10-13 | Selection KL 0.3: the approach to c_K for K ≥ 4 is still not a theorem. The obstruction is located (no de Moivre identity for the K = 4 overlap sum; an order-4 recurrence instead of a telescoping ratio), and the asymptotic margin c(K) = (E[M_K³] − (5/2)·E[M_K])/(6·E[M_K]) is zero at K = 2, 3 and positive beyond, from a cited expansion. Exact sweeps to K = 100, n = 400. |
| `fe9d51c` | 10-13 | Multigen 0.5: gate dominance under mixed gain laws (an accepted candidate may gain nothing). No counterexample in an exact search over every rule; proven two below the target for every law by an exact window recursion; finite beyond. |
| `988efa5` | 10-13 | Gold calibration 0.3: a fourth rater gives exactly six testable equalities and detects a copying grader that three raters absorb; a joint statement for (η₁, ε₁) whose coverage holds given two plug-ins. |
| the commit adding this file | 10-14 | This map and the session log. |

Every module has a verifier script whose receipt under `output/` records
the SHA-256 of its sources; `PYTHONPATH=src .venv/Scripts/python.exe -m
pytest tests -q` runs the whole suite (705 tests at `6518851`, 774 at
`988efa5`). The log beside this map ends with the round-4 wrap-up.

**History rewrite.** On 2026-10-14, at the author's request, the branch was
rebuilt from `6518851` so that no earlier version of the log remains on it
(§4, items 13–15). The three round-4 commits were replayed unchanged under
new IDs, which this map and the log use throughout: `ca6ba24`, `fe9d51c` and
`988efa5`. The IDs of the removed log commits read `[removed-commit]` in the
log.

## 3. How the work was organised

The session acted as lead. Mathematical problems that were independent of
each other were delegated to subagents, one per problem, each in its own
detached git worktree at the branch head, with instructions to create or
extend only its own files, never to commit, and to report what was proven
in general versus checked on enumerated cases. The lead then reran the
agent's tests, inspected its receipt and git status, read its note, and in
several cases its proof line by line, before copying the files into the
branch worktree, running the full suite, committing and pushing. The
subagent transcripts in the export are the primary record of each
delegation; the lead's verification of each is in the main transcript
immediately after the agent's report.

| Problem | Subagent transcript |
|---|---|
| Partial-leakage lattice (round 1) | `agent-ab43631a2b331546e` |
| Multi-generation chain (round 1) | `agent-a8f70008319d14008` |
| Composition laws (round 1) | `agent-afe28ab653cb4d8f7` |
| Multigen 0.2: bound, correlation, gate theorem | `agent-a8f175b3b81d6fbfc` |
| Judge shared-error measurement | `agent-a7a5fb6b63b2d5a45` |
| RSITopology crosswalk | `agent-a8dccf5456eb3fcb3` |
| Selection law KL containment | `agent-aaaa7bc0ef80b0eb3` |
| Gate dominance (multigen 0.3) | `agent-a58295504f13fcadd` |
| Gold calibration, second grader | `agent-a88021944d49cc33a` |
| Count dominance (multigen 0.4) | `agent-a2720158120a14204` |
| Monotone approach to c_K | `agent-a0a48c70545f74f7e` |
| Sampling law and Dawid–Skene | `agent-af4031af24ee0c5b0` |
| c_K for K ≥ 4 (selection KL 0.3) | `agent-a4078b66ab04b87ab` |
| Mixed gain laws (multigen 0.5) | `agent-a8e6a31053670dded` |
| Fourth rater and joint statement, first attempt | `agent-a992e8ad543fe5899` |
| Fourth rater and joint statement, completion | `agent-a714182c964e5a809` |

**Interruptions in round 4.** The mixed-gain and fourth-rater agents both
lost their API connection early and were resumed from their transcripts.
Both then stopped on the usage limit of `claude-fable-5-1`, and Patrick
switched the session to `claude-opus-5-5`. The mixed-gain agent had
already written its module, tests, receipt and note, and stopped before
reporting; the lead verified that work as it stood. The fourth-rater
agent had written most of the module but no tests, verifier, receipt or
note. A new agent on `claude-opus-5-5` recovered the original brief from
the first agent's transcript, checked the code it found, and finished it.

The lead kept for itself the source check of the atlas, the training-signal
module, the lattice's policy-structure work, and all integration.

## 4. Errors found and corrected, in the order they were found

An auditor should weigh these more than the theorems.

1. **The forwarded atlas (draft 0.1)** had been written from a summarizing
   fetch tool. The line-level check found: OpenAI's Lean share was 42%
   (300/719), not 162/722, and three manuscripts had been withdrawn the day
   after release; the OpenAI run had within-run feedback and a mid-run model
   swap the atlas called "not stated"; Anthropic's index weights split each
   sampled person-week evenly across tasks, so the atlas's "fast tasks weigh
   less" mechanism did not follow; METR's own doubling time was 128.7 days,
   the atlas's 131/89 came from a prediction-market page; the AIDE² contrast
   of 1.90 standard errors was cross-model, while the fixed-model gains were
   2.6–7.4. Commit `662557c`.
2. **The toy-simulation README** claimed byte-for-byte reproduction; on this
   machine one of three result files differs in the last digit of 24
   floats. Recorded as such.
3. **Multigen 0.1's boundary remark** said correlated candidates lower every
   per-generation inflation. The exact mutation model showed the opposite for
   the accumulated gap. Commit `4401d78`.
4. **A reading of the gate-vs-naive cells** attributed the "gate above naive"
   ordering at n = 8 to the one-step theorem; the one-step difference is
   identically zero there and the ordering is a timing effect. Commit `4401d78`.
5. **Lattice 0.2's claim that greedy-by-rate is optimal at one hit**, with an
   exchange-argument proof, was false: the argument never considered staying
   in a category whose rate rose after a miss, and the claim fails at size 7,
   one past the exhaustive grid that had "verified" it. The correct statement
   is Theorem 10 (the best finisher, in closed form). The lead had repeated
   the false claim in its own summaries. Commit `a5ab4ff`.
6. **Two regularities that held on the exhaustive grid** (equal rates favour
   the larger category; the lowest of three rates is never uniquely optimal)
   failed just beyond it. Commit `a5ab4ff`.
7. **A formula the lead supplied to a subagent** (de Moivre's mean absolute
   deviation) was off by a factor of two; the subagent caught it by
   enumeration before using it. Commit `70f6f27`.
8. **A claim in a subagent brief** that the controller–judge agreement rate
   stops being invariant under label-dependent gold flips was wrong; the
   agent showed C⊕F = J⊕F iff C = J for any flip law. Commit `f1b9dad`.
9. **Two citations in the crosswalk** were taken from memory and are marked
   unverified in the note rather than presented as checked.
10. **The mixed-gain agent's note** said lemmas L1–L3 hold under every mixed
    gain law. Its own module proves L2–L3 only for gains in {0, 1}. The lead
    narrowed the sentence before committing. Commit `fe9d51c`.
11. **The interrupted fourth-rater code** had six defects, found by the agent
    that finished it. It rounded the three agreement counts separately,
    giving counts no item table can produce. It expected the parameter
    Jacobian's rank to drop with a chance rater, which it does not. It
    misoriented an anti-informative second grader. It did not withhold the
    joint statement when the constraint check failed, as its docstring said
    it would. It asserted disjoint ε₁ ranges at m = 742, which is false.
    It had an off-by-one in a tail law. Commit `988efa5`.
12. **The lead's brief for the completion agent** named the wrong note file.
    The agent found the right one from the original brief.
13. **The first version of the session log**, published on 2026-10-13, left 25 JSON records
    unparseable. Its memory-line rule ran on raw text, and where a private
    review's line ended a string, the rule ran past the closing quote and
    deleted the rest of the record. Its README said every line parsed and
    nothing else changed, which was false for those records. The lead found
    this while refreshing the log and rewrote the redaction to work on
    decoded strings.
14. **The same first version missed one private audit's working-tree folder
    name**, which appears 24 times in it. The refreshed log removes it, and
    the history rewrite removed that version from the branch.
15. **Both earlier versions of the log carried the author's other work.**
    Every turn's context held the full memory index, with a line for each of
    the author's other projects, and a git-status snapshot of the whole
    working tree. The lead had redacted only the private-review lines and
    published the rest. The author pointed out that the log was meant to
    cover this investigation only. The current version withholds every
    memory-index line except this investigation's own notes, the git-status
    snapshots, other projects' file names, five memory notes read from other
    work, and the app's configuration files. The author then had the branch
    history rewritten so that neither earlier version remains on it.

The lesson recorded in the lead's memory: small exhaustive grids let two
false theorems through; a regularity observed on a grid is stressed at larger
sizes before anything is called a proof.

## 5. The results an auditor should test first

- Theorem 10 (lattice): one-hit optimum = min_c (n_c+1)/(F_c+1). Witness
  that rate-greedy fails: {(2,1),(16,9)}, 3/2 against 53/32.
- Proposition 7 (lattice): no index rule; witness {(2,1),(4,2)} with and
  without a (1,1) category at two hits.
- Theorem B (selection KL): KL(π_K‖p₀) ≤ ln K − (K−1)/K for every finite
  law and tie rule, via jitter and Jensen.
- Propositions 8 and 9 (multigen): the gate lowers the true value and the
  count in stochastic order, for every threshold rule, under fixed gains.
- L4 (signal): observed accuracy = a − ε + 2(1−a)ε₁; the ceiling is reached
  without memorization iff ε₁ ≥ 1/2.
- The mutation-model finding (multigen 0.2): correlation with the incumbent
  lowers first-generation inflation and raises the accumulated gap.
- The corollary in the judge measurement note: with gold wrong at rate η,
  an independent judge shows a measured shared-error excess
  (ε₁′ − ε′)(1 − a′) of exactly η(1−η)(2a−1)(1−2ε).
- Proposition 6 (gold calibration 0.3): four raters give exactly six
  equalities, via a lower-triangular minor with determinant −c₁₂⁴c₁₃². A
  grader copying the gold grader with probability ρ leaves the residual
  ρV₁c₃₄ on one tetrad. The lead re-derived both by hand and checked the
  fixture, the six residuals and the copy residual on 200 random model
  points each, with a script independent of the module.
- The distance-two closure (multigen 0.5): at count m − 2 the window sums
  obey W_k = A·W_{k−1} + E_{k−1} with E ≥ 0, for every gain law.
- The margin c(K) (selection KL 0.3): exactly zero at K = 2 and 3, as the
  K = 2 and K = 3 theorems require, and 0.020561 at K = 4.

## 6. What the session did not do

No model, policy, environment, judge or grader was ever run; every result
is exact arithmetic on declared quantities, with the evidence level stated
per proposition. The session did not read Will Brown's posts of 12 October.
It did not open a pull request against `main`; the branch is public and the
link to open one is in the push output in the transcript.

## 7. How to read the raw log

`transcript.jsonl` is one JSON object per line in conversation order; tool
calls and their results are interleaved with the assistant's text. Each
subagent file under `subagents/` is the same format for one delegation; its
`.prefix.json` holds the context it started with. `tool-results/` holds
tool outputs too large to inline. `REDACTIONS.json` lists, per file, how
many replacements the redaction made; the rules are in the README beside it.
A line reading `[... the author's other work: withheld]` held context from
the author's other projects. A line or string reading
`[withheld by redaction: ...]` named one of the private review terms; nearly
all such lines are in the stretch where the redaction itself was built.
