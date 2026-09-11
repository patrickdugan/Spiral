# Inference under cross-examination

Date: 2026-09-11. Independent inference challenger. Frozen target:
`C:/projects/Spiral`, parent-identified commit `a0a3140`. This audit changes no
original source or result. All executions are offline synthetic computations;
none is a Lightning node, testnet4 payment, wallet operation, or live-network
experiment. Root independently handles the testnet4 evidence.

## Verdict

The strongest new finding is a reproducibility defect, not statistical
corruption. Identical experiment seeds, sample identifier, public topology and
public policy fields can yield different synthetic liquidity and different
results when only Python's process hash seed changes. The source/result hashes
in the earlier receipts do not fully identify this hidden execution input.

Matched-resource controls sharpen, rather than abolish, the oracle result.
The original comparison legitimately measures a privileged-information package
under a restricted attempted-route budget. It does not isolate an intrinsic
increase in available liquidity, and its greedy oracle is not a full-horizon
optimal-control bound. Sparse aggregate feedback from one heuristic is also not
an empirical limit on AI agents generally.

An initial concern that overlapping samples necessarily invalidate all 28
cluster intervals was rejected. Overlap is modest on average and does not, by
itself, establish dependence of conditionally randomized draws. The stronger
limitation is that one historical snapshot and a particular sampling mechanism
do not measure uncertainty across snapshots or operational Lightning states.

## I1. Same declared experiment, different hidden state

Two independent Python processes used `PYTHONHASHSEED=1` and `2`. Everything else
was identical: Python/NetworkX environment, original source, original snapshot,
sample seed 4, random-anchor sampling, 64 nodes, capacity seed 4, balance seed
40000, uniform balances, diffuse demand, and the original 220-step episode.
Both reconstruct `public-random-4-5ae5f9236d61` and identical canonical edge and
public-policy hashes. Yet the resulting synthetic-state and candidate-catalogue
hashes differ.

| Observation | Hash seed 1 | Hash seed 2 |
| --- | ---: | ---: |
| Public-routing successes / 110 | 105 | 102 |
| Retry-routing successes / 110 | 105 | 102 |
| Online-routing successes / 110 | 105 | 102 |
| Oracle-routing successes / 110 | 105 | 102 |
| Public-routing failed attempts | 5 | 8 |
| Retry-routing failed attempts | 5 | 9 |
| Online-routing failed attempts | 5 | 9 |
| Oracle failed-attempt proxy | 0 | 0 |

The mechanism is visible in the source. `public_topology.py:122` copies a
subgraph filtered by a set; `:128` relabels without canonicalizing insertion
order. At `:166`, the state generator sorts the graph's raw `(left, right)`
edge tuples. Only afterward, at `:167`, does it canonicalize endpoint direction.
An undirected edge's raw orientation depends on graph traversal order. Therefore
the same stream of seeded random capacity and balance draws can attach to
different canonical edges. A sample hash over its sorted node set does not
commit to that assignment.

Separately, `public_topology_eval.py:204` takes the first eight unweighted
`shortest_simple_paths` before public-fee sorting at `:273`. Graph insertion
order can affect tie ordering. Fee sorting does not repair an already truncated
candidate set. In the sample used for the hash-seed witness, the inspected 512
endpoint pairs have at most two candidates, so the witness does not establish
a first-eight truncation effect; it establishes catalogue order sensitivity and
hidden-state reassignment. The latter is sufficient to explain a material
reproducibility risk.

A separate canonical-order reference reconstructs the sampled graph with sorted
nodes and canonically oriented, sorted edges. Under both hash seeds, this
reference produces identical state and catalogue hashes and 106/110 successes
under each original policy. This is a determinism repair witness, not a claim
that 106 is the historical or physically correct result. It does not edit the
original sampler, and it does not establish cross-version reproducibility.

Defender: hash seeds were not meant to be an experimental variable; the stored
CSV evidence remains available and its hashes remain valid.

Adjudication: accepted. The audit does not prove that CSVs were corrupted or
fabricated, nor that their policy comparisons were unpaired within a process.
It does show that configuration seeds alone are insufficient for exact replay.
Canonicalize graph/state construction, pin dependency versions, record the
process hash seed, and commit the generated initial-state and candidate hashes
before interpreting repeated executions as identical trials.

## I2. Distinguish information from route-attempt resources

Let the candidate catalogue be `P=(p1,...,pm)` in public-cost order. Write `j`
for the maximum publicly ordered candidate prefix examined, and `a` for the
maximum number of attempted routes. These are different resources. Exact
feasibility inspection is a privileged observation, not a free network action.

The implementation gives ordinary retry at most three attempts. The online
learner may rank all eight public candidates but attempts at most three. The
oracle inspects the hidden feasibility of all eight, chooses a feasible one,
and records no infeasible network attempt. Calling all of these "same budget"
without specifying the resource is incomplete.

**Restricted equivalence proposition.** In this fee-accounting-only,
zero-duration model, assume that failed attempts do not change balances or
other state, candidates have a fixed public order for each demand, and an
oracle and exhaustive retry inspect the same candidate prefix. Then they
deliver the same payment on the same route or both fail. Their liquidity
states therefore remain equal after that demand. Induction gives identical
liquidity trajectories for a fixed demand sequence. Failed-attempt counts
need not match.

The proof does not apply when attempts incur timing, slots, fees, feedback-driven
reranking, counterparty reactions, or other consequential state changes. It
also does not say information is valueless under a fixed three-attempt budget.

The diagnostic replay uses the first original sealed random/periphery/hub
samples (indices 4, 5, 6), balance draw zero, uniform and polarized balance
models, and all three demand regimes: 18 cells and seven policies, hence 126
episodes. Each episode has 220 demands with the last 110 evaluated. This is a
post-hoc diagnostic, not a new independent confirmatory campaign. No new
confidence interval or population-level claim is inferred from it.

Authoritative results below are the final run pinned to `PYTHONHASHSEED=1`.
Earlier unpinned exploratory aggregates are superseded and must not be mixed
with this table.

| Policy/resource condition | Success rate | Failed attempts / 1,980 evaluation demands |
| --- | ---: | ---: |
| Public: one attempt | 82.8788% | 339 |
| Retry: three public-order attempts | 84.6465% | 426 |
| Online: three ranked attempts | 84.5960% | 436 |
| Frozen feedback: three attempts | 84.6465% | 426 |
| Oracle: inspect public prefix three | 84.6465% | 0 |
| Retry: up to eight attempts | 84.7980% | 522 |
| Oracle: inspect all eight | 84.7980% | 0 |

For every cell, retry-three and prefix-three oracle have identical entire
220-step state trajectories, as do retry-eight and oracle-eight; frozen
feedback also matches retry-three. All 54 paired trajectory checks pass.

A four-branch deterministic witness makes the distinction transparent: only
the fourth candidate is feasible. Retry-three and prefix-three oracle fail;
retry-eight and full oracle succeed. Retry records three failed attempts;
oracle records zero. This is a reachability-versus-observation-cost distinction,
not a proof that privileged state creates no operational advantage.

The final replay does not exactly reproduce the archived campaign. Of 72
original-policy checks, only 6 match both success and failed-attempt counts;
64 differ in successes, 50 in failures, and 66 in at least one measure. The
hash-seed witness establishes a concrete source of execution variability. The
new table therefore is not an attribution decomposition of the published
5.14/0.35/1.11-point estimates. It is a separately identified diagnostic run.

Defender: the original oracle is a legitimate value-of-information benchmark
under a three-attempt operational constraint; increasing retry attempts spends
more resources.

Adjudication: accepted after incentive-challenger cross-examination. Preserve
that interpretation and its lower failed-attempt proxy. Retract only stronger
interpretations such as additional underlying liquidity, a resource-neutral
comparison, or an intrinsic universal intelligence boundary. Failed attempts
are not measured privacy bits; the manuscript already acknowledges that.

## I3. A greedy oracle is not a horizon-optimal oracle

The exact graph witness has a cheap S-A-T route and a slightly more expensive
S-B-T route. The initial A-T directional balance is two units. The demand
sequence is S-to-T for one unit, then A-to-T for two units. Production greedy
oracle uses S-A-T first and cannot deliver the second demand: 1/2 successes.
Using S-B-T first preserves the scarce A-T balance and delivers both: 2/2.

This refutes a full-horizon optimal-control extension of the word "upper bound"
(the manuscript uses "oracle upper bound" at `paper/manuscript.md:440`). It does
not refute a one-step feasibility filter, an upper-information condition, or
the stored episode statistics. A comparator must be named by its actual scope:
current-state greedy filter, horizon-aware optimizer, or noncausal benchmark.

## I4. Actual row integrity survives; input contracts do not

The three archived campaigns contain 4,536 rows, including 3,348 sealed rows.
The sealed sample count is 28. There are zero duplicate condition keys. Each
unstratified contrast has all 558 paired cells; each demand-regime contrast
has all 186. No missing left/right policy pairs were found.

Synthetic negative controls nevertheless expose pipeline weaknesses:

- `_condition` at `public_topology_analysis.py:102` silently keeps the last
  duplicate row. Merely reversing duplicate order changes a synthetic paired
  estimate from -0.3 to +0.3.
- `atomic_differences` at `:112` silently intersects key sets, discarding an
  unmatched row; a completely absent comparison returns an empty vector.
- `cluster_interval` at `:144` returns [0,0] with zero clusters and a zero-width
  interval around 0.123 with one cluster. Neither is an uncertainty estimate.
- The check at `:214` is one-sided (`upper < 0.01`), so a large negative effect
  could pass a flag suggestive of practical equivalence. The actual reported
  online interval lies inside the two-sided band, so this latent problem does
  not falsify that numerical conclusion.
- The oracle-zero flag at `:216` uses `all(...)`, which is vacuously true on no
  oracle rows. Actual oracle rows exist, so the current result is not vacuous.

Defender: none of these input failures occurred in the present archived files.

Adjudication: accepted. These are hardening requirements and counterexamples
to unconditional reliability of the analysis API, not evidence that its current
CSV-based effect estimates were altered by duplicates or missing pairs. Require
unique keys, exact pairing, nonempty comparisons, at least two clusters for
estimated intervals, and explicit two-sided equivalence contracts.

## I5. What the topology clusters do and do not represent

Reconstruction verifies all 37 sample IDs against archived rows: 9 calibration
samples and 28 sealed samples, all from the same verified 2023-07-16 snapshot.
The sealed samples contain 1,550 distinct source nodes across 1,792 occurrences,
and 3,106 distinct edges across 3,221 occurrences. The original snapshot has
15,100 nodes and 64,212 edges. No raw public node identifiers are written into
the audit results.

Among 378 sealed-sealed pairs, 182 share at least one node and 47 share at least
one edge. Median intersection is zero for both. Maximum intersection is 18
nodes and 17 edges; mean node Jaccard is 0.007159, mean edge Jaccard 0.001397.
Among 252 sealed-calibration pairs, 149 share a node and 34 an edge. Thus
"held-out sample indices" is accurate; "node-disjoint held-out network" is not.

Overlap does not determine the sign or magnitude of statistical covariance.
Independent random draws from one fixed graph may overlap and still be
conditionally independent. No effective sample size is inferred from these
intersection counts, and no replacement interval is manufactured. The sampled
topology may remain a sensible conditional Monte Carlo clustering unit.

However, these 28 draws do not supply 28 independent historical networks.
They do not estimate snapshot-to-snapshot variation, calibrate hidden balances,
or validate the BFS/snowball sampling mechanism as representative of operational
routes. Repeated synthetic balance/demand cells likewise do not create new
public snapshots. Future claims should name the conditional estimand and use
genuinely separated historical snapshots for temporal generalization.

The precision configuration explicitly says it responds to heterogeneity
observed after the prior replication and specifies some combined-data tests.
That is transparent adaptive research, but reusing earlier outcomes in a
newly selected combined test is not the same as collecting an entirely fresh
confirmation of an untouched hypothesis. Report exploratory selection,
extension-only checks and combined precision separately. A failed significance
test alone is not proof of no adaptation or a necessary condition for benefit.

## Actual swarm cross-examination and chronology

This is a factual record of work and exchanged challenges, not invented dialogue.

1. Inference challenger inspected the original manuscript, three configurations,
   sampler, evaluator, analysis functions and CSVs. Proposed oracle-budget,
   sample-overlap and input-integrity challenges to root.
2. Authored deterministic witnesses and ran six passing fast regression tests.
   Authored the bounded replay and reconstructed all 37 sample identities.
3. The first replay stopped on an exact-comparison assertion. Rather than
   discarding the mismatch, the challenger disclosed it and added explicit
   reproduction checks. The subsequent unpinned replay completed.
4. Separate hash-seed processes established changed synthetic state and outcomes
   on the same declared cell. A canonical-order reference removed this
   difference for the tested seeds. Final replay was pinned to hash seed one.
5. Incentive challenger objected that route-attempt and observation budgets are
   distinct, and that overlap does not establish dependent draws. Inference
   challenger accepted both objections and narrowed the adjudication above.
6. Root required the greedy-oracle witness to distinguish full-horizon optimality
   from the intended one-step information condition. That qualification is now
   explicit in I3.
7. Inference challenger independently reviewed algebra's report, original route
   code, Appendix A.1-A.4 and transactional reference. The simple-path convention
   defends the earlier routing campaign; the repeated-walk accepted-API atomicity
   bug still stands. The net-polytope challenge targets a generalized-walk or
   gross-reservation extension, not the simple fee-free path lemma. The cut-stock
   counterexample stands for gross horizon demand; even net demand needs every
   prefix to satisfy inventory constraints. This adjudication was sent to root
   and the algebra challenger.

## Reproduction and evidence

`results.json` is the authoritative final hash-seed-one replay and overlap
record. `receipt.json` binds its source inputs, script, environment and result.
`hash_seed_1.json` and `hash_seed_2.json` are the separate reproducibility
witnesses. `verify_evidence.py` checks and hashes the final bundle.

```powershell
$env:PYTHONPATH = 'C:\projects\Spiral\src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONHASHSEED = '1'
& 'C:\projects\Spiral\.venv\Scripts\python.exe' 'E:\Recovered_C_projects\Spiral_target\projects\Spiral\audit\inference\run_audit.py'
& 'C:\projects\Spiral\.venv\Scripts\python.exe' 'E:\Recovered_C_projects\Spiral_target\projects\Spiral\audit\inference\hash_order_witness.py' --output 'E:\Recovered_C_projects\Spiral_target\projects\Spiral\audit\inference\hash_seed_1.json'
$env:PYTHONHASHSEED = '2'
& 'C:\projects\Spiral\.venv\Scripts\python.exe' 'E:\Recovered_C_projects\Spiral_target\projects\Spiral\audit\inference\hash_order_witness.py' --output 'E:\Recovered_C_projects\Spiral_target\projects\Spiral\audit\inference\hash_seed_2.json'
& 'C:\projects\Spiral\.venv\Scripts\python.exe' -m unittest discover -s 'E:\Recovered_C_projects\Spiral_target\projects\Spiral\audit\inference' -p 'test_audit.py' -v
& 'C:\projects\Spiral\.venv\Scripts\python.exe' 'E:\Recovered_C_projects\Spiral_target\projects\Spiral\audit\inference\verify_evidence.py'
```

The numeric replay is reproducible under the recorded runtime/hash seed; creation
timestamps intentionally change on rerun, so regenerated JSON file hashes will
change even when the deterministic measurements do not. All paths in commands
are local, and all outputs stay within the assigned audit directory.
