# Prime Intellect examples for the evaluation design calculus

Version 0.1 — inspected 2026-09-11.

This atlas applies [our calculus](evaluation_design_calculus.md) to eight worked cases drawn from nine published Prime Intellect Hub packages, followed by one task-generation example from Prime's current Verifiers source. These are design analyses and proposed experiments. No hosted evaluations, model calls, training jobs, or GPU jobs were run.

Each case distinguishes **observed specification**, **our interpretation**, and **proposed variation**. Hub descriptions were read in the live public browser, including package versions. Current-source examples are pinned to Verifiers commit [`a32cc09c58be3bdff3dd5a206afd8d03fb5b9945`](https://github.com/PrimeIntellect-ai/verifiers/commit/a32cc09c58be3bdff3dd5a206afd8d03fb5b9945). They are not asserted to be byte-identical to any published Hub package.

## 1. Connecting the notation to Prime

Prime v1 distinguishes tasksets, harnesses, agents, environments, toolsets, and traces. A taskset supplies work and task behavior; an agent combines a harness, model, and runtime policy; an environment organizes agent control flow. [Official v1 overview](https://docs.primeintellect.ai/verifiers/v1/overview)

| Our object | Prime-side evidence to record |
|---|---|
| \(G\): playable situation | Task behavior, environment control flow, tools, resources, stopping conditions |
| \(\Pi\): controller protocol | Model, harness, runtime policy, counterpart configurations, memory, sampling |
| \(D\): experiment distribution | Taskset version, dataset revision, selected rows, seeds, repeats, assignment |
| \(Z\): acquired evidence | Trace contents, tool results, metrics, errors, timing, privileged scorer data |
| \(J,\mathcal A\): judgment and aggregation | Reward components, weights, grouping, uncertainty, and failure treatment |
| \(C\): claim | The specific capability and population justified by the above |

The correspondence is many-to-many: one package can contain mechanics, sampling, and grading. A Hub slug alone does not identify a complete evaluation.

All nine inspected Hub package pages carried a **Legacy** banner. For AIME, the README simultaneously describes a Taskset/Harness migration. Treat the banner as registry metadata, not sufficient proof of the package's API semantics. Pin the package and inspect its code before execution; do not mix the legacy examples' command syntax with current v1 recipes.

## 2. The example set

| Case | Verified package/version | Design structure | Useful question |
|---|---|---|---|
| AIME 2025 | `primeintellect/aime2025` 0.2.0 | One-shot answer with deterministic verification | Does performance depend on computation budget or answer extraction? |
| StepFun Prover | `primeintellect/stepfun-prover` 0.1.3 | Iterative proof construction with verifier feedback | Can the agent use diagnostics to repair a proof? |
| 2048 across interfaces | `hud/hud-text-2048` and `hud/hud-browser-2048`, both 0.1.0 | Stateful single-player game through different interfaces | How much of the result depends on observation and action interfaces? |
| MAPP | `salty-duck/mapp` 0.1.0 | Joint navigation with collision constraints | What changes when control or information is distributed? |
| tau2-bench | `will/tau2-bench` 0.2.0 | Tool-using service interaction with a simulated user | How sensitive is success to the counterpart? |
| KernelBench | `primeintellect/kernelbench` 0.1.6 | Construct a program, then test correctness and performance | Which hardware and measurement conditions define improvement? |
| Poker | `strangeloopcanon/poker` 0.1.0 | Single-turn action selection, with optional simulation | Was strategic play actually evaluated? |
| Rubric Discovery | `stochi0/rubric-discovery` 0.2.0 | Infer a grading function from examples | Does a learned judge generalize to new cases and source tasks? |
| Proposer–Solver | Current Verifiers source recipe, package 0.1.0 | Generate a task, run solvers, reward the generator | How do validity and sample count affect the curriculum signal? |

The last row is a source recipe, not a confirmed Hub listing. Kuhn poker is used below as a second explicitly labeled source comparator.

## 3. AIME: answer correctness, budget, and the parser

**Observed.** The published package combines 30 AIME 2025 I/II problems from a pinned dataset revision. It describes single-turn evaluation, boxed-answer extraction, and a single correctness reward. The README states that environment-specific settings are fixed. [Hub specification](https://app.primeintellect.ai/dashboard/environments/primeintellect/aime2025)

**Interpretation.** This is a one-player decision problem. There is no strategic opponent whose best response explains the score. A correct final answer supports success on the sampled problems under the recorded controller protocol; it does not independently certify the reasoning process.

**Proposed variation.** Build a separately named fork with calculator access \(t\in\{0,1\}\) and total generation budget \(b\in\{\text{small},\text{large}\}\):

\[
E_{tb}=\operatorname{Budget}_b(\operatorname{Tools}_t(E)).
\]

`Tools` is an atlas extension: adding a tool changes actions, observations, and possibly runtime costs. It is not a documented switch on this AIME package. Hold the problem list, final-answer contract, model, and sampling fixed. Report correctness and total cost separately.

Estimate the tool effect at each budget and their interaction. Independently rescore saved responses with a preregistered normalization parser to diagnose extraction sensitivity; this offline operation cannot change the answer-generation behavior. Report that parser contrast separately from the capability contrast.

**Claim boundary.** Additional retries on the same 30 problems do not create additional independent problems. Pair by problem and retain the repeated-rollout hierarchy.

## 4. StepFun Prover: feedback is useful only when revision remains possible

**Observed.** The Hub describes a Lean 4 proof environment with iterative feedback, binary proof-completion reward, configurable `max_turns` (default 3), and per-attempt timeout (default 60 seconds). [Hub specification](https://app.primeintellect.ai/dashboard/environments/primeintellect/stepfun-prover)

**Interpretation.** The play structure is construction, verification, and possible repair. Formal feedback is an observation channel; another attempt is an action opportunity. They should have separate effects in the notation.

**Proposed variation.** Cross detailed diagnostics versus a binary failed-attempt message with one versus three proof attempts. The reduced-feedback condition requires a custom adapter. Preserve success termination and use the same underlying Lean environment, libraries, theorem statements, and acceptance criteria.

\[
\Delta_{\text{feedback,revision}}
=V_{\text{detailed},3}-V_{\text{binary},3}
-V_{\text{detailed},1}+V_{\text{binary},1}.
\]

If feedback arrives only after the sole permitted submission, is not anticipated differently by the prompt, and cannot alter that attempt's score, it cannot affect the one-attempt result. Its value must occur through a remaining decision. This is a timing claim about the proposed design, not a measured result for this package.

**Measurements.** Completion, successful repairs after a rejection, total generated tokens, verification time, and error categories. Distinguish budget exhaustion from rejection of a completed proof. A repaired proof supports feedback use under this protocol; additional attempts alone can also raise completion.

## 5. 2048: equivalent goals do not guarantee equivalent evaluations

**Observed.** HUD publishes a text interface using tool actions and a browser interface using screenshots and keyboard actions. Their READMEs describe different composite weights: text uses 0.80 completion, 0.15 format, 0.05 execution; browser uses 0.80, 0.10, 0.10. Both describe a logarithmic highest-tile/target completion component. The text README contains conflicting task-count descriptions, so its full task set is not treated as settled here. [Text package](https://app.primeintellect.ai/dashboard/environments/hud/hud-text-2048), [browser package](https://app.primeintellect.ai/dashboard/environments/hud/hud-browser-2048)

**Interpretation.** Directly subtracting their published aggregate scores does not isolate visual reasoning: sampling, action interface, and judgment may differ along with observations.

**Proposed variation.** Construct one canonical 2048 engine and cross text versus image observations with semantic moves versus keyboard-action encoding. Use matched initial boards, common target values, budgets, and an explicit coupling of subsequent random events. Policies can diverge, so matched randomness does not mean identical later boards. All four cells require adapters; they are not claimed to be built-in package options.

Record actual target attainment as a separate binary measure. For the documented shaped component, reaching 128 with target 256 gives

\[
\frac{\log 128}{\log256}=\frac78,
\qquad 0.8\cdot\frac78+0.2=0.9
\]

when auxiliary components are perfect. A composite score of 0.9 can therefore coexist with failure to reach the target. This is arithmetic derived from the README formula, not an observed run.

**Conservation lens.** An ordinary merge of two equal tiles preserves their sum. Newly spawned tiles add explicit mass. Keep this board-value ledger separate from the game's displayed score. The two published packages have not been proven isomorphic.

## 6. MAPP: multiple pieces versus multiple decision-makers

**Observed.** MAPP describes a grid with multiple start/goal pairs, obstacles, simultaneous movement, five actions including waiting, and collision checks. It lists goal completion, collision count, and path efficiency as measurements. [Hub specification](https://app.primeintellect.ai/dashboard/environments/salty-duck/mapp)

**Interpretation.** A world containing several agents can still be controlled by one planner. The README alone does not establish independently reasoning model participants or decentralized information access. Record controller topology explicitly.

**Proposed variation.** Compare a centralized controller and separate controllers under full versus local observations. For central/local, define a coordinator that receives only the declared local reports; do not silently reconstruct a global map. Match total model budget, initial positions, goals, obstacles, action timing, and the common team objective.

\[
E_{ci}=\operatorname{ControllerTopology}_c
(\operatorname{ObservationScope}_i(E)).
\]

These atlas extensions rewrite \(\Pi\) and observation interfaces, so they require new wrappers. A collision-free central plan demonstrates joint planning; successful decentralized execution supports coordination under the specified communication channel. Neither alone implies negotiation or Nash stability.

**Measurements.** Joint success, per-agent success, collisions, makespan, and total path cost. Define behavior for unreachable tasks and zero-length paths. Topology/scenario is the blocking unit; actions by agents in one world are dependent observations.

## 7. tau2-bench: the counterpart is part of the treatment

**Observed.** The Hub wrapper describes retail, airline, and telecom service tasks with tools and a simulated user. It exposes the user model, conversation-step limit, and tool-error limit, and delegates evaluation to tau2. The README lists task completion, database changes, and communication among its evaluation concerns. [Hub specification](https://app.primeintellect.ai/dashboard/environments/will/tau2-bench)

**Interpretation.** This is an interactive service protocol, not automatically an adversarial game. Replacing the simulated user changes the interaction distribution even if the assistant model is unchanged.

**Proposed variation.** Cross two frozen user-model configurations with two assistant tool-use budgets within one fixed domain and task list. A tool-use cap distinct from the wrapper's general step limit requires an adapter. Match initial database snapshots and user instructions. Keep assistant and user token/resource ledgers separate.

Measure success \(V(\pi,\mu,b)\), where \(\pi\) is the assistant and \(\mu\) the user simulator. Report the assistant effect under each \(\mu\), rather than treating one counterpart as a universal test population.

**Claim boundary.** Counterpart sensitivity is not necessarily assistant regression. A fixed prerecorded user transcript also is not generally a valid substitute for a reactive user after the assistant takes a different action. Inspect the pinned wrapper's actual emitted metrics before treating the README's metric names as a machine-readable contract.

## 8. KernelBench: correctness gates a hardware-conditioned frontier

**Observed.** The Hub describes single-turn kernel generation followed by remote GPU evaluation against a PyTorch reference, including correctness and speedup metrics. It describes `fast_1` and `fast_2` as correctness-gated speedup thresholds. Its README disagrees with itself about the default main reward and timing-trial count. This atlas consequently does not assert those defaults. [Hub specification](https://app.primeintellect.ai/dashboard/environments/primeintellect/kernelbench)

**Interpretation.** A benchmark score depends on both the generated artifact and the measuring apparatus. Faster execution on one GPU is not an environment-independent property of the model.

For generated program \(p\), hardware \(h\), baseline configuration \(c\), and threshold \(s\), define the explicit diagnostic

\[
Q_{h,c}(s)=\Pr[\operatorname{correct}(p)
\land t_{\rm baseline}(h,c)/t_p(h)>s].
\]

**Proposed variation.** Replay the same saved candidate artifacts across two GPU types and eager versus compiled reference baselines. Record correctness before summarizing speed. This is a measurement study: generating new hardware-specific programs would be a separate controller intervention.

**Measurements.** Correctness rate, compilation failures, timing uncertainty, and the threshold curve \(Q(s)\). Preserve failed candidates in the denominator. Average speedup over only successful candidates answers a conditional question and can conceal low reliability. Hardware, compiler/runtime versions, input shapes, warm-up, and timing trials belong in the evidence record.

## 9. Poker: an explicit boundary between a stub and a strategic game

**Observed.** The published package requests one JSON action. Its README describes a 0.2 format reward and 0.8 poker reward. If simulation is disabled, unavailable, or errors, documented fallback values are fold 0.45, call 0.50, and raise 0.55. Optional simulation and different opponent modes are separate configurations. [Hub specification](https://app.primeintellect.ai/dashboard/environments/strangeloopcanon/poker)

For valid JSON in the documented fallback:

\[
R(\text{fold})=0.56,\quad R(\text{call})=0.60,
\quad R(\text{raise})=0.64.
\]

**Interpretation.** Constant raising optimizes this three-action stub. That result supports output-format compliance and preference for the largest fixed reward; it does not establish bluffing, opponent modeling, or equilibrium play. Stub versus simulator is a change of task semantics, not an ordinary difficulty setting. Every run should expose which mode actually produced each score, and simulation-required runs should fail explicitly instead of silently switching estimands.

**Strategic comparator from current source.** Prime's separate [Kuhn poker recipe](https://github.com/PrimeIntellect-ai/verifiers/blob/a32cc09c58be3bdff3dd5a206afd8d03fb5b9945/environments/kuhn_poker/kuhn_poker/taskset.py) runs two live seats, seeded private cards, legal betting histories, zero-sum chip payoffs, and configurable invalid-move retries. It defaults both seats to the run's model but permits an asymmetric counterpart. This source recipe is a different game and is not asserted to be the Hub package above.

Here Nash analysis is meaningful: estimate player-specific unilateral improvement gaps with information-respecting policies. Do not let a best-response search see the other player's card or hidden deal seed. Average signed reward across both seats is identically zero, including forfeits; it cannot measure progress. Report seat-conditioned payoff, forfeit rate, and performance against fixed reference opponents. Self-play performance alone does not establish low exploitability.

**Proposed variation.** For the Kuhn recipe, cross a frozen opponent roster with reset versus persistent focal-agent memory. Balance seats and deals, and group hands by independent match/session when memory persists. This is a strategic extension, not a validated transformation of the Hub stub.

## 10. Rubric Discovery: evaluating the evaluator

**Observed.** This Hub task asks an agent to synthesize `rubric_fn(input_text, response)`. Its data contract separates prompt-side training examples from reward-side test examples. The README describes weights of 0.50 held-out agreement, 0.25 calibration, 0.15 score variance, and 0.10 iterative tool use. It says `validate_rubric` performs AST validation only. [Hub specification](https://app.primeintellect.ai/dashboard/environments/stochi0/rubric-discovery)

**Interpretation.** The produced artifact is a judge \(\hat J\); it needs its own evaluation. Syntax validation does not establish correctness of that judge. Variance and tool-use rewards also do not directly measure fidelity to reference scores.

**Proposed variation.** Cross the number of demonstrations with within-source versus held-out-source evaluation. Freeze source-family assignments, separate exact duplicates and near-duplicates before splitting, and document any task-hint metadata available to the learner. These are proposed dataset interventions.

\[
L_D(\hat J)=\mathbb E_{(x,y,s)\sim D}
|\hat J(x,y)-s|.
\]

Report this loss, agreement under a fixed tolerance, and ranking behavior separately from the training composite. Reference labels themselves may be noisy or encode unwanted preferences, so fidelity to them has a bounded interpretation.

**Composition.** \(\operatorname{FitJudge}(D_{\rm train});\operatorname{Freeze};\operatorname{AssessJudge}(D_{\rm holdout})\) is a typed evaluation pipeline. Using the resulting judge to rank the same responses that taught it would require a different claim.

## 11. Proposer–Solver: the task distribution is produced by an agent

This case is based on a [pinned Verifiers source recipe](https://github.com/PrimeIntellect-ai/verifiers/blob/a32cc09c58be3bdff3dd5a206afd8d03fb5b9945/environments/proposer_solver/proposer_solver/taskset.py), not a verified Hub listing.

**Observed in source.** A proposer emits a problem/answer JSON contract, which becomes a task for \(n\) solver runs (default four). Solvers are scored against the proposed integer. The proposer receives \(4\hat p(1-\hat p)\), where \(\hat p\) is their observed success fraction. Although the prompt asks the proposer to verify its answer, the task-construction code checks the JSON structure and integer type, not an independently checked proof of mathematical correctness.

**Interpretation.** This is endogenous task generation:

\[
\operatorname{Propose}\ ;\ \operatorname{Validate}\ ;\
\operatorname{Solve}^{\otimes n}\ ;\ \operatorname{JudgeGenerator}.
\]

The solvers share a generated problem, so independence is conditional and must not be assumed across all traces. Independent validity checking is a proposed strengthening of the middle stage.

**Exact sample-count effect.** For a fixed valid problem and conditionally independent, identically distributed Bernoulli solver successes with probability \(p\),

\[
\mathbb E[4\hat p(1-\hat p)]
=4p(1-p)\left(1-\frac1n\right).
\]

This follows by substituting \(\mathbb E\hat p=p\) and \(\operatorname{Var}(\hat p)=p(1-p)/n\). At \(p=1/2\), the expected score is zero for \(n=1\), 0.75 for \(n=4\), and 0.875 for \(n=8\). Thus changing solver count changes the expected reward even when underlying task difficulty does not change. Correlation between solver outcomes changes this formula.

For \(n>1\), multiplication by \(n/(n-1)\) gives an unbiased diagnostic for the population quantity under those assumptions, but the corrected observation can exceed one. Clipping it would lose unbiasedness. This is an analytical diagnostic, not an implemented training-reward change.

**Proposed variation.** Cross independent answer validation on/off with \(n\in\{1,4,8\}\), reporting validity and rejection rate separately. Use fixed proposer and solver checkpoints during evaluation. Curriculum reward does not itself demonstrate subsequent learning; that requires a separately controlled training-and-holdout experiment.

## 12. What these examples add to the calculus

Three annotations are now necessary on practical evaluation cards:

1. **Execution mode:** a fallback, real simulator, and live counterpart may implement different games under the same package name.
2. **Judgment dependency:** a score may depend on one trace, sibling attempts, an opponent, a learned judge, or a generated task. Record that dependency graph before choosing independent statistical units.
3. **Evidence level:** distinguish a Hub description, inspected implementation, exact derived arithmetic, and observed model result.

The first useful implementation set is the poker mode diagnostic, matched 2048 interface study, and proof-feedback interaction. Together they exercise semantic validity, observation/action interfaces, and sequential composition. The more advanced extension is Rubric Discovery feeding a frozen judge into another evaluation, with a holdout boundary between them.

The machine-readable companion, `configs/prime_intellect_eval_cards.json`, records these cases and their proposed studies. It is a design manifest, not a Prime CLI configuration. `scripts/verify_prime_eval_atlas.py` verifies only the derived arithmetic and manifest structure; its receipt is under `output/evaluation_design_calculus/prime_atlas_verification.json`.
