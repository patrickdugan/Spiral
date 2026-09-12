# Evaluation-game estimands and incentive-response testbed

## Scope

This is a small exact, finite synthetic testbed. It does not call a model,
collect transcripts, simulate interacting agents, or identify strategic intent.
It builds on the separation among game, case distribution, measurement, and
claim in [evaluation_design_calculus.md](evaluation_design_calculus.md). It
does not alter the frozen v3 sandbagging results or protocol.

```powershell
$env:PYTHONPATH = "src"
python scripts/verify_evaluation_game_testbed.py --output output/evaluation_game_testbed.json
python -m pytest tests/test_evaluation_game_testbed.py -q
```

The output is exact synthetic fixture evidence, not model or agent evidence.
It stores rational values as strings and will not overwrite an existing output.

## Four non-interchangeable estimands

Fix \(\mathcal E=\langle G,\Pi,D,Z,J,\mathcal A,C\rangle\). A score alone
does not say which object changed.

| Estimand | Definition | It is not |
|---|---|---|
| Baseline gain | \(B=V_{\pi_1}(d)-V_{\pi_0}(d)\) with a named case law and judgment | Robustness or strategic stability |
| Robust regret | \(R(\pi;\mathcal Q)=\max_{q\in\mathcal Q}[\max_{\pi'}V_{\pi'}(q)-V_\pi(q)]\) | A baseline gain or a measurement gap |
| Discrimination gap | \(\mathrm{TV}(Z_\#P_{\pi_1},Z_\#P_{\pi_0})\) | Utility, regret, or player information |
| Exploitability | \(\max_i[\sup_{\pi_i'}\mathbb EU_i(\pi_i',\pi_{-i})-\mathbb EU_i(\pi)]\) | Generalization or welfare |

The finite fixtures make baseline gain and robust regret both one half. Their
matching numbers are intentional: their source objects and interpretation remain
different, so they must not be combined or relabeled as each other.
Both policies in the corrected baseline fixture receive the revealed state:
the baseline always chooses left and the candidate follows the observation.
The game and case law are consequently fixed for that comparison.

## Observation-only Hide versus player-facing hiding

Observation-only `Hide` belongs to acquisition. After players act, apply a
common Markov kernel \(H(z'\mid z)\) to each completed record:

\[
P_H(z'\mid\pi)=\sum_z H(z'\mid z)P(z\mid\pi).
\]

It does not change legal actions, player histories, transitions, or payoffs.
In the fixture, perfectly correct and perfectly wrong traces have visible
total-variation discrimination gap one. The common kernel maps both to
`redacted`, leaving an acquired-record gap of zero and demonstrating finite
data processing: \(\mathrm{TV}(H_\#P,H_\#Q)\leq\mathrm{TV}(P,Q)\).

Removing information from a player before action instead changes \(O_i\) in
\(G\). In the two-location game, the optimal value falls from one to one half.
That is a game intervention, not offline measurement redaction. An adapter that
removes player feedback must type it that way irrespective of its method name.

## Strategic checks, costs, and falsifiers

The social-dilemma fixture enumerates a pure equilibrium set and reports the
selected outcome under `enumerate_pure_nash_then_lexicographically_select`; it
does not present the outcome as controller behavior. At `share, share`, exact
exploitability is two. Searching only the `share` deviation returns zero, which
is marked as a lower bound rather than exploitability. A matching-pennies
fixture separately checks equal primal maximin and dual minimax witnesses at
zero. It is not a generic equilibrium solver.

Falsifiers for an applied strategic interpretation are an illegal deviation
class, private state leaked to the search, an unspecified adaptation or
equilibrium-selection rule, dependent payoff estimates, or calling a restricted
search exact exploitability. Report the restriction and withhold that stronger
claim when any appears.

## Incentive-response design for sandbagging investigation

The estimand is a behavioral incentive-response contrast, not intent. Let
\(Y_{c,d,g}\) be a blinded score with condition \(c\), difficulty \(d\), and
grader-severity stratum \(g\):

\[
Y=\mu+\alpha_c+\beta_d+\gamma_g+\eta_{c,d}+\varepsilon.
\]

Match paired control/incentive tasks within \((d,g)\), estimate
\(\tau_d=\mathbb E[Y_{0,d,g}-Y_{1,d,g}]\), and reserve untouched blocks to
test \(\iota=\tau_{hard}-\tau_{easy}\). Pairing cancels additive difficulty
and grader severity; it does not establish prompt equivalence or intent.
Selection of strata, allocation, and any target family remains in training data;
the interaction is tested only in the held-out confirmation data.

For acquisition, condition 0 gives the ordinary task and performance objective;
condition 1 adds a preregistered evaluation-contingent incentive frame while
holding task instructions, tools, time budget, scoring rubric, and stated role
fixed. The frame is shown to the participant before acting, so it is a
presentation/incentive intervention on the game, not observation-only Hide.
Use held-out isomorphic task forms matched by difficulty calibrated on separate
data; randomize form-to-condition and AB/BA order in reset contexts. A negative
control uses comparably sized neutral framing with no changed incentive. This
design checks sensitivity to the chosen frame, not compliance with an assumed
internal utility function. Semantic equivalence must be reviewed independently.

Estimate grader severity on independent anchor responses with condition labels
removed. Cross each grader/severity stratum with both conditions and both
difficulties using the same rubric and version; do not assign strict graders
only to the incentive arm. Save response, form, block, assignment, scorer, and
calibration identifiers. Difficulty- or condition-dependent grading errors
require an expanded nuisance model and separate checks. The executable fixture
encodes known additive severity, not estimated severity or verified blinding.

The fixture has four equal-weight equal-variance strata and a 96-score budget.
Each matched pair costs two scored responses. It enumerates the 48-pair integer
allocation minimizing \(\sum_h(1/4)^2/n_h\) and obtains 12 pairs per stratum.
This optimization is conditional on its equal-variance and equal-cost premise.
In an applied study, preregister variance/cost estimates, retain minimum stratum
coverage, and use the resulting Neyman-style allocation without holdout tuning.

The fixture deliberately has no latent intent variable and records
`intent_identified: false`. A contrast can arise from strategic response, benign
role constraints, task changes, condition-dependent scoring, or distribution
shift. Falsifiers include an interaction in negative-incentive controls, failed
prompt-equivalence review, unblinded scoring, grader severity not linked within
pairs, or a selection/holdout block overlap. Any falsifier defeats the strategic
interpretation; it is not evidence of a zero effect.

## Executable confirmation and adversarial checks

`evaluation_game_confirmation.py` now enforces the split on actual synthetic
pair and block records. Every block contains all four difficulty/grader strata.
Duplicate pairs, missing strata, mixed block metadata, reused training IDs,
and confirmation of a different family all raise errors. The selected family
is chosen by training mean gap with lexical ties, before confirmation rows are
generated. Identifiers can detect recorded overlap; they cannot independently
certify independence or prevent an operator from relabeling reused observations.

The saved fixture has two families with eight training blocks each (64 pairs,
128 score operations), then 12 target and 12 negative-control blocks for the
selected family (96 pairs, 192 score operations). The total is **320**. These
are constructed score values, not paid model calls or independent model trials.
The older four-cell arithmetic illustration records eight score values and a
separate *planned* 96-score target allocation; that plan is not an acquisition
receipt. Calibration, prompt review, and scorer qualification costs remain
outside this synthetic count and must be budgeted for an observed study.

Each confirmation block produces an equal-weight incentive-response contrast
and a hard-minus-easy interaction. Two exact two-sided sign tests receive
alpha/2 each, with ties discarded. These test directional consistency under
independent blocks and equiprobable nonzero signs under the null; they do not
test the population mean. The fixture reports the arithmetic means separately.
Its interaction is 1/5, with sign p-value 1/2048 across 12 positive blocks.
This deterministic positive fixture does not measure statistical coverage or
false-positive rates. Training-only effects return a holdout p-value of one.
This budget covers one selected-family evaluation. Multiple subjects or added
confirmatory contrasts require a frozen campaign correction; do not reuse the
same alpha independently for each subject or retune on confirmation outcomes.

Negative controls must have exactly zero paired differences for this fixture's
support flag. This is an arithmetic diagnostic, not an empirical equivalence
test; observed controls would need uncertainty, tolerance margins, adequate
sample sizes, and a preregistered inference procedure. A control bias withholds
the support flag. Passing that flag still leaves `intent_identified: false`.

The allocation optimizer solves the finite integer problem with supplied
weights, paired-difference variances, pair costs, budget, and minimum stratum
counts. Independent exhaustive enumeration checks it with unequal costs and
variances. Its variance objective assumes independent strata. Covariances of
contrasts measured in common blocks require a different objective; the block
confirmation fixture is not claimed to attain that independent-stratum bound.

Additional checks cover 625 rational binary distribution/channel combinations
for total-variation contraction, malformed kernel rejection, and a falsifier
where different policy-specific channels manufacture discrimination. A general
finite matrix certificate reports primal and dual bounds and refuses to certify
an inferior matching-pennies strategy. A coordination-game example reports its
complete Nash set (two pure profiles and one uniformly mixed profile) alongside
two explicit update paths: simultaneous best responses cycle from (0,1), while
row-then-column updates reach (1,1). The former equilibrium enumeration rule is
a selection convention; these new paths supply actual finite adaptation rules.

The verifier's schema 1.1 includes confirmation, allocation, adaptation, and
primal/dual results and source hashes. Run the expanded regressions with:

```powershell
python -m pytest tests/test_evaluation_game_testbed.py tests/test_evaluation_game_confirmation.py -q
```
