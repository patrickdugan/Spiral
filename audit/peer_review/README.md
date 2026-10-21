# Technical review and reproducibility record

Review date: **21 October 2026**. Reviewed baseline:
`6a9df365f727cf2471ae52e00b36e8816d0081bc`, the supplied 45-page build of
*Where the Capital Bound Moves: Settlement Objects, Proof Economics, and Agent
Coordination on Bitcoin Payment Networks*.

The revised [LaTeX source](../../paper/tex/main.tex) is a **technical discussion
draft**. It retains the accounting results and conditional model comparisons,
corrects implementation errors, and narrows claims about routing, rewards,
coalitions, and deployed protocols. The [revision record](../../paper/peer_review_changes.md)
explains the substantive changes. The revised [41-page PDF](../../paper/tex/main.pdf)
has been rebuilt with XeLaTeX and visually inspected. It has no overfull boxes
or unresolved references. [verification.json](verification.json) records the
review checks and artifact hashes.

This directory records a post hoc review. Its new sensitivity campaign was
designed after the model error was identified. Neither that campaign nor the
[proposed implementation experiments](testnet4_plan.md) should be described as
completed preregistered confirmation.

## Evidence map

| Artifact | What it establishes | Boundary |
|---|---|---|
| [Mathematical review](math_review.md), [finite witness script](math_witnesses.py), [witness output](math_witnesses.json) | Counterexamples to the policy-performance inference, cumulative-fronting bound, and noncanonical nullifier construction; corrected accounting statements | Finite witnesses and mathematical reasoning do not measure the prevalence of these failures in deployed systems |
| [Empirical review](empirical_review.md), [independent checker](check_empirical.py), [check output](empirical_check.json) | Archived CSV integrity, paired policy contrasts, and historical header properties | Reanalysis of retained evidence; the historical simulator campaigns were not regenerated |
| [Grid comparison](math_grid_comparison.json) | Before/after generated rows, baseline identity, and recorded file hashes for the model correction | The trailing server forecast remains a diagnostic when it fails to fund the unconstrained holder replay |
| [Sensitivity generator](model_sensitivity.ts), [retained results](model_sensitivity.json) | Corrected oracle comparisons over 24 demand seeds in each of four cells | Synthetic demand, full-horizon forecasting, one lifetime convention, and occupied-capital accounting |
| [Table renderer](render_sensitivity.py) | Generates the [paper sensitivity table](../../paper/tex/review_sensitivity.tex) from the retained JSON | Formatting adds no evidence beyond the underlying runs |
| [Implementation and testnet4 plan](testnet4_plan.md) | Questions, accounting checks, source support, and proposed stopping rules for future execution | No regtest stack or live payment experiment was run in this review |

Earlier [inference](../inference/report.md) and [incentive](../incentives/REPORT.md)
audits remain available. The retained campaign files and earlier manuscripts
are preserved; the new checker rejects duplicate or unpaired observations
without rewriting the historical analysis.

## What changed the claims

The cut identity holds along each policy's settled history. A route choice can
leave different directional balances for the next request, so conservation
alone supplies no numerical ceiling on routing information. The four-node
witness delivers one or two payments from the same initial state, depending
on the first successful route, while every checked prefix satisfies the cut
identity. See the [mathematical review](math_review.md).

The server bound now constrains outstanding fronting, `W = F - C`, where `F`
is cumulative fronting and `C` cumulative recovery. Recovered capital can be
used again. Channel and hyperedge forecasts now include receipt-before-spend
peaks and reject unaffordable spends in full, matching replay. Locks are
integrated only until their actual recovery point. These corrections change
the generated tables, including the few-steady trailing-channel failure count
from 12,703 to 8 out of 32,256 events. See the
[recorded grid changes](math_grid_comparison.json).

Claim-once rewards now explicitly require one canonical single-signer
credential per eligible object and disjoint economic backing. The registry
validates amounts and fresh identifiers, preserves epoch history, and uses
exact integer allocation arithmetic. It still uses a simulated verifier and
assumes that an eligible-set maintainer excludes overlapping backing. A
complete service denominator and a general bound on coalition earnings remain
unimplemented. See the [revised proof and scope discussion](../../paper/tex/main.tex)
and [registry implementation](../../model/registry.ts).

Current Second documentation supports expiry-time recovery for successful
outgoing Lightning payments. Next-round recovery remains a counterfactual
design case. BIP 448 and LayerTree are analyzed as proposals. LayerTree queue
examples require minimum service, bounded overtaking, and prompt resubmission;
mempool admission ceilings do not supply those guarantees. Published BitVM3
costs describe the cited backend, and no application-specific proof benchmark
has been produced here. Primary-source links and implementation questions are
collected in the [experiment plan](testnet4_plan.md) and
[paper bibliography](../../paper/tex/references.bib).

## Archived numerical evidence

The [independent empirical check](empirical_check.json) covers **4,536 rows**
across three campaigns, including **3,348 sealed rows** and **28 sealed
topology clusters**. It reproduces all seven checked archived contrasts to
`1e-12` and additionally computes oracle versus retries directly from the
paired rows. Selected contrasts are:

| Comparison | Mean, percentage points | 95% interval |
|---|---:|---:|
| Retry over one-shot public routing | 5.1389 | [3.0823, 7.1954] |
| Online feedback heuristic over retry | 0.3481 | [0.1477, 0.5485] |
| Current-state greedy oracle over online heuristic | 1.1099 | [0.6395, 1.5803] |
| Current-state greedy oracle over retry, recomputed contrast | 1.4580 | [0.8446, 2.0715] |
| Failure-aware over random capital, stationary demand | 6.1310 | [4.9090, 7.3530] |
| Failure-aware over random capital, diffuse demand | 0.1443 | [-0.0222, 0.3108] |
| Failure-aware over random capital, shifted demand | 0.4383 | [-0.2119, 1.0886] |

These intervals use equally weighted topology-cluster means and the archived
Student-t procedure. All sampled topologies come from one July 16, 2023 gossip
snapshot, with synthetic capacities and hidden balances. The retry and online
arms execute up to three candidate routes; the oracle examines hidden
feasibility across up to eight candidates. The comparison therefore changes
both information and search resources. The shifted interval includes zero and
extends beyond the declared +/-1-point equivalence band. It establishes
neither an exact zero effect nor equivalence under that rule. The
[empirical review](empirical_review.md) also documents hash-order sensitivity
that prevents a claim of exact historical campaign regeneration.

## New model sensitivity

The [retained JSON](model_sensitivity.json) contains **96 seed/cell
combinations** and **192 Ark recovery runs**: seeds 1 through 24 for each of
four demand cells, over eight 4032-block lifetimes, using the corrected oracle
and a 25% provisioning margin. Within each seed/cell combination, all compared
objects receive the same demand and reject only the common unaffordable
outgoing requests. Every included server sizing diagnostic has zero failures.
This equal-service check does not mean that every offered request succeeds.

`C` denotes bilateral channels, `H20` a group of twenty agents plus a hub,
`HN` the full group plus a hub, and `V` the modeled Ark ledger. Ratios compare
capital-duration; values above one favor the denominator on this metric.
Intervals describe 95% Monte Carlo uncertainty in the model mean across the
24 seeds.

| Demand cell | C/H20 | C/HN | C/V, expiry recovery | C/V, next-round counterfactual |
|---|---:|---:|---:|---:|
| 200 agents, zero drift | 1.467 [1.450, 1.483] | 1.541 [1.522, 1.561] | 0.871 [0.865, 0.878] | 1.531 [1.511, 1.551] |
| 200 agents, draining drift | 2.174 [2.138, 2.211] | 2.767 [2.725, 2.809] | 0.649 [0.643, 0.655] | 2.737 [2.696, 2.778] |
| 200 agents, accumulating drift | 1.009 [1.008, 1.009] | 1.009 [1.009, 1.010] | 0.970 [0.970, 0.970] | 0.987 [0.987, 0.988] |
| 3 agents, steady | Not applicable | 1.375 [1.325, 1.424] | 0.00736 [0.00678, 0.00795] | 0.924 [0.902, 0.946] |

The group of twenty captures a mean 86.3% of the full pool's excess gain at
zero drift and 66.5% under draining drift. Every sampled expiry-recovery case
has `C/V < 1`. These are findings about the stated reference model. Its Ark
fronting reserve is unconstrained, idle treasury is uncharged, gateway
financing is incomplete, and the receive-pool and refresh lifetimes have not
been separately calibrated to Bark. Fees, membership churn, and correlated
availability failures are absent. The proposed
[equal-service implementation comparison](testnet4_plan.md) must resolve those
boundaries before interpreting these ratios as a deployment ranking.

## Historical headers and operational clocks

The [header check](empirical_check.json) independently decodes and hashes all
**512 archived headers**, verifies their encoded proof-of-work targets and
**511 internal parent links**, and matches the retained terminal anchor at
height **147984**. The first height is **147473**. There are **64 nonpositive
adjacent header timestamp differences**, with a minimum of **-6004 seconds**.

This supports the identity, encoded-work, and internal-link properties of the
retained segment. It does not establish current chain membership, full
consensus validation, observed funding inclusion, or payment latency. The
synthetic funding/depth gates in the earlier replay remain declared scenarios.
Miner timestamps are not observer arrival times. An operational study needs
local monotonic timestamps, node-observed arrival events, transaction
identifiers, and actual channel activation and HTLC records. See the
[testnet4 plan](testnet4_plan.md).

## Verification status and commands

Run the commands below from the repository root. The TypeScript checks were
completed with Node **v24.19.0**:

```sh
node --experimental-strip-types --test model/*.test.ts
```

On that runtime the test runner reports six file-level passes. Directly
executing each file exposes the named cases:

```sh
for model_test_path in model/*.test.ts
do
  node --experimental-strip-types "$model_test_path" || exit
done
```

**30/30 named TypeScript tests passed**, with zero failures or skips:

| Module | Named tests |
|---|---:|
| Escrow/warden | 4 |
| Hamiltonian finite fixtures | 1 |
| LayerTree | 2 |
| Ledger | 2 |
| Registry | 12 |
| Server | 9 |

The server cases include all 1,024 five-round paths over four event types and
an exact recovery integral checked with coarse and fine time steps. Registry
cases cover invalid numeric inputs, identifier reuse, snapshot independence,
and exact allocation at the safe-integer boundary. These tests exercise the
reference implementation; they do not execute Bitcoin scripts or a real proof
system.

The completed independent Python checks use the standard library:

```sh
python audit/peer_review/math_witnesses.py
python audit/peer_review/check_empirical.py --output /tmp/spiral-empirical-review.json
```

To regenerate the model outputs and their paper inputs:

```sh
node --experimental-strip-types model/grid.ts > paper/tex/grid.tex
node --experimental-strip-types audit/peer_review/model_sensitivity.ts > audit/peer_review/model_sensitivity.json
python audit/peer_review/render_sensitivity.py
```

The broader Python suite was **not run successfully in this review
environment**: both `pytest` and `networkx` are unavailable. Passing the
standard-library audit scripts does not establish a pass for
`python -m pytest -q`. The revised 41-page PDF built successfully with
`latexmk -xelatex -interaction=nonstopmode -halt-on-error main.tex` from
`paper/tex/`. Every page was rendered and inspected; two figure overlaps and
a nearly empty final page were corrected, and the affected pages were inspected again.

## Priorities for further work

1. **Reconcile one complete Ark capital cycle on owned regtest.** Pin
   Bark/captaind and Lightning builds. Trace successful and failed sends,
   receives, refreshes, and expiry sweeps. Identify the actual asset and
   obligation behind any claimed next-round reuse. Classify each asset once
   at every step and integrate its occupied and reserved capital separately.
2. **Calibrate budgets at a common service target.** Separate receive-pool
   ages from refreshed lifetimes; charge idle reserves and terminal
   obligations. Choose budgets on pilot data and freeze them before separate
   confirmation seeds. Report event success, delivered value, and unmet value
   beside capital-duration.
3. **Then measure operational clocks on bounded, owned testnet4 nodes.** The
   proposed plan uses four controlled Lightning peers in a diamond, a ceiling
   of 200 payments, a 48-hour stopping rule, and a proposed 1,000,000-test-sat
   funding/fee cap. These are unexecuted limits, not performance estimates.
   Record censored waits, HTLC reservations, activation depth, observed arrival
   times, and reconciled fees. Keep identical-state policy comparisons and
   adversarial queue tests on restorable regtest.
4. **Use an enforcing environment for proposal-specific claims.** BIP 448 and
   LayerTree need explicitly patched local nodes or an identified custom
   network. Public testnet4 acceptance cannot establish enforcement of
   inactive opcode semantics. A compiled reward relation and its actual setup
   and challenge path are separate implementation tasks.

The [full plan](testnet4_plan.md) contains source support, required artifacts,
and decision criteria. No live transactions were constructed or broadcast in
this review.

## Focused questions for Bitcoin reviewers

1. Does the revised cut identity omit a balance or timing term needed when
   actual HTLC reservations, fees, and capacity changes are represented?
2. For the documented Ark payment paths, which concrete asset becomes
   reusable at each transition, and can any earlier recovery be demonstrated
   without financing it from another reserve?
3. Which holder, gateway, fronting, and idle-reserve stocks can legitimately
   share funding without counting the same asset twice?
4. What admission and canonical-credential construction would extend the
   restricted registry to alternative script paths or threshold authorities
   while excluding overlapping economic backing?
5. What complete request ledger can support the service denominator, including
   requests refused admission, timeouts, and collusive counterparties?
6. Which measurable miner, relay, and resubmission assumptions would justify
   a useful lower service rate for competing shared-output transitions?
7. Which demand processes, initial balances, service targets, and churn models
   would make the proposed settlement comparisons informative to operators?
8. Which backend and threat assumptions are appropriate for a first actual
   proof and escrow benchmark of the restricted reward construction?
