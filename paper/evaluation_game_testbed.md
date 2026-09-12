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
| Exploitability | \(\max_i\sup_{\pi_i'}\mathbb EU_i(\pi_i',\pi_{-i})-\mathbb EU_i(\pi)\) | Generalization or welfare |

The finite fixtures make baseline gain and robust regret both one half. Their
matching numbers are intentional: their source objects and interpretation remain
different, so they must not be combined or relabeled as each other.

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
