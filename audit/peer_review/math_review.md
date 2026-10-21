# Mathematical review of *Where the Capital Bound Moves*

Reviewed baseline: `6a9df365f727cf2471ae52e00b36e8816d0081bc`, 21 October 2026.
This is a post hoc publication review. Source line references below refer to that baseline.

## Changes that affect the conclusions

### 1. The cut identity survives; its policy-performance corollary does not

The prefix-cut lemma at `paper/tex/main.tex:87–101` is a direct conservation identity. The sentence at lines 103–110 limiting all information advantage to an attempt budget does not follow. A successful routing decision changes which directional balances remain available for subsequent payments. The cut inequalities hold along both trajectories and do not make the trajectories equally routable.

`math_witnesses.py` constructs a four-node example with identical public capacities and the same hidden initial balances for both policies. A first payment of one unit succeeds on either of two routes. One choice leaves a subsequent two-unit single-path payment feasible; the other leaves no feasible route for it, even after exhaustive path search. Every nontrivial cut satisfies the prefix identity at every settled prefix. This fits the paper's single-path payment model. The witness establishes a logical gap in the claimed consequence; it does not estimate how often this effect occurs on Lightning.

Proposed replacement: state that every routing policy obeys the cut inequalities for its own settled history, conditional on the capacity-event history. State separately that the tested retry and oracle policies differ by the observed number of success points on the supplied simulator campaign. Remove a universal one-point bound and the claim that the experiment proves information has only an attempt-budget role.

### 2. Cumulative fronting is not currently occupied capital

The second inequality of the server proposition at lines 217–229 bounds a cumulative allocation quantity by current available stock. A ten-unit reserve can front ten units, recover it, and front it again. Its cumulative fronting is twenty while outstanding fronting is ten or zero. In the old model `allocated` also increments at receipt, so it reaches forty after two receive-ten/spend-ten cycles. `aggregateBoundHolds()` checked `committed <= capital`, a different, pointwise claim from the printed inequality.

Use cumulative fronting `F_S(n)` and cumulative recoveries `C_S(n)`, with

\[
W_S(n)=W_S(0)+F_S(n)-C_S(n).
\]

For a fixed fronting reserve `B_S^F`, admit an additional front `f_n` only when

\[
f_n\le B_S^F-W_S(n^-).
\]

This ensures `0 <= W_S <= B_S^F`. Holder accounting is `V_A(n)=V_A(0)+I_A(n)-O_A(n)` when inward events include all credited receipts/boarding and refresh preserves face value. Additional subsidies or retirements need their own explicit issuance term. The grid charges issuance stock separately, so the model's `capital` must be described as a fronting reserve, rather than the server's entire capital.

The model comments and `holderBoundHolds()` now match these statements. A recycling witness appears in `math_witnesses.py`, and a regression test checks cumulative delivery exceeding the reserve while the pointwise bound continues to hold.

### 3. Oracle sizing used a different event model from execution

`model/server.ts` originally sized channels from `max(0, balance + in - out)` after each round. Actual execution receives first, then rejects an unaffordable outgoing payment as a whole. Two errors follow. A receipt immediately spent still needs inbound capacity before the spend. An unaffordable spend leaves the existing balance intact rather than partially draining it to zero.

For one round with `in=10, out=10`, the old oracle forecast was zero and both events failed. After correction, the required capital is ten, both events settle, and duration is 0.5 blocks for a one-block horizon. A second witness receives five and attempts to spend seven; the rejected spend leaves five available, so the next five-unit receipt produces a ten-unit peak.

The correction applies to channel and hyperedge oracle forecasts, as well as the peaks observed by their trailing rules. Receipt-first ordering is identical in sizing and execution. A zero-margin exhaustive check covers all 1,024 five-round demand paths over four event types, with a second agent using the reversed path. Every oracle run fails only the independently computed unaffordable outgoing requests; the one-agent hyperedge equals the bilateral channel exactly. Pooling requires no greater stock than the sum of separate stocks.

The headline small-group pooling mechanism survives the baseline-seed correction. Several quoted numbers change. The most significant change is the few-steady cell: trailing channel failures fall from 12,703 to 8 out of 32,256 events, and the server diagnostic's 8,229 failures become zero. The manuscript's suggestion that this cell mostly refuses traffic was caused by the implementation error.

| Quantity | Baseline | Corrected |
|---|---:|---:|
| Zero-drift, eight-lifetime oracle C/V, hypothetical round recovery | 1.46 | 1.48 |
| Draining-drift oracle C/V, hypothetical round recovery | 2.52 | 2.59 |
| Zero-drift oracle C/H, group size 20 | 1.4402 | 1.4311 |
| Zero-drift oracle C/H, group size 200 | 1.5019 | 1.4909 |
| Few-steady trailing channel failures | 12,703 | 8 |
| Few-steady oracle channel failures | 8 | 4 |
| Few-steady server forecast failures | 8,229 | 0 |

`math_grid_comparison.json` retains every changed table row, the baseline commit and hashes. The corrected zero-drift stock per agent is 105,912.5 sat under the oracle forecast and 38,654.6875 under the trailing rule. LayerTree estimates using the former 104,094/38,112 sat anchors need to be recomputed.

### 4. Lock integration must respect recovery inside a time step

`advance(blocks)` charged every outstanding lock through the endpoint even if it recovered earlier in that interval. Ten sat expiring after five blocks and an advance of ten blocks produced 100 sat-blocks. It now produces 50, with an independent check that a coarse advance and ten one-block advances agree. Existing grid sweep times are aligned to its six-block steps, so this change does not move the current grid by itself.

### 5. Trailing server sizing does not constrain its delivery

`serverTierTerm()` replays the aggregate flow of an otherwise unconstrained Ark simulation. Its failed events do not alter the server's delivered-volume denominator or forfeit locks. Consequently, a nonzero server diagnostic failure count identifies a sizing calculation that cannot be read as an end-to-end feasible service run. This remains an explicit limitation, recorded in the function's comments. An additional constrained replay would have to reject the original receipt, propagate that rejection to holder balances, and recompute later spends and locks.

The exact duration comparison is

\[
\frac{D_C}{D_V}=\frac{L_C}{L_V}\frac{\operatorname{Vol}_V}{\operatorname{Vol}_C},
\]

where `L` is integrated occupied capital. The volume factor can be dropped only for equal delivered volume. A fronting-lock integral uses each fronted input's value and residence time; bidirectional payment volume times an average lock is a separate approximation, because fronting also includes reissued change and refreshes. These conditions should accompany the paper's ratios.

## Further theorem and scope revisions

**Canonical nullifiers.** The relation at lines 515–530 allows any key satisfying an object's authority. Alternative valid spending credentials produce different keyed PRFs for the same object. The per-object theorem therefore requires one canonical nullifier credential verifiably tied to each eligible object. Threshold signing's aggregate public key alone does not specify a secret PRF key or a distributed nullifier protocol. `math_witnesses.py` gives a finite HMAC example of the issue. The model currently represents the restricted case as one authority string per object. Numeric values must also be restricted to positive bounded integers.

**Disjoint backing.** Distinct object identifiers do not by themselves establish distinct economic exposure. A registry admitting a funding UTXO and the virtual claims it backs can count the same backing twice under separate IDs. A capital-proportional conclusion across object classes needs a canonical admission rule that excludes overlapping backing.

**Service attestations.** An arbitrary set of signed outcomes with a claimant-selected denominator proves a submitted-attestation ratio. A complete service-availability claim requires unique request IDs and a complete window fixed independently of the outcomes, including the treatment of omissions and deadlines. That protocol remains to be specified and implemented.

**Coalition earnings.** The empirical six-point placement effect at lines 623–630 is a mean policy comparison. It gives neither an upper bound over all placement policies nor a bound on earnings, and an estimated shifted-demand effect near zero is not exact zero. Retain the authenticated-weight theorem with its assumptions; present the placement result as evidence about the policies actually tested. The current cycle statistic is a fixture result and does not supply the missing economic theorem.

**The diffusion constant.** The `pi/2` statement should identify its expectation and limit. For independent reflected Brownian motions `R_i`,

\[
G_N(T)=\frac{N\,E[\sup_{t\le T}R_1(t)]}{E[\sup_{t\le T}\sum_{i=1}^N R_i(t)]}\le\frac{\pi}{2},
\]

because the denominator is at least the expected terminal sum. A uniform law of large numbers supplies the large-population limit `pi/2`. This is a ratio of expectations in the Brownian model. An individual realized finite random-walk ratio has no universal `pi/2` cap. The `sqrt(N)` signed-imbalance regime also needs sufficient initial balances or a mechanism that permits the stated signed deviations.

**Queueing.** A maximum of `kappa` services per block is insufficient for an upper delay bound. The given formula becomes a conservative scheduler scenario under a minimum service rate, bounded overtaking and prompt valid resubmission. Exact FIFO completion in service windows is `ceil((beta+q+1)/kappa)`; the current expression adds at most one conservative window. Mempool admission limits supply no guaranteed mining service rate.

## Verification and follow-up

Run `python audit/peer_review/math_witnesses.py` for the independent finite witnesses. Run `node --experimental-strip-types model/server.test.ts` for the nine server tests, including the exhaustive path group and exact lock-integration regression. Generate the tables with `node --experimental-strip-types model/grid.ts`.

A post hoc fixed-seed sensitivity campaign is recorded separately in `model_sensitivity.ts`. It tests the corrected equal-service oracle comparisons across demand seeds. A live testnet4 transaction cannot validate these population distributions or turn a fixture's detector into a general result; those questions require controlled experiments with declared demand and observation rules.

## Completed sensitivity campaign

`model_sensitivity.json` records seeds 1 through 24 for each of four demand cells, over eight VTXO lifetimes. Each seed uses the same offered demand for bilateral channels, hyperedges, and both server recovery cases. The forecast is the corrected oracle, with the existing 25% provisioning margin. Every included cell passed an equal-service check: the channel and every hyperedge rejected exactly the unaffordable outgoing requests rejected by the unconstrained holder ledger, and the server sizing diagnostic rejected zero events. There are 96 seed/cell combinations and 192 Ark recovery runs.

The intervals below are 95% Student-t intervals for the model mean across the 24 seed replicates. They describe Monte Carlo precision conditional on the demand generator and implementation. They are not estimates of mainnet effects. This exploratory campaign was specified after finding the event-order bug.

| Demand cell | C/H5 mean | C/H20 mean, MC interval | C/HN mean, MC interval |
|---|---:|---:|---:|
| 200 agents, zero drift | 1.319 | 1.467 [1.450, 1.483] | 1.541 [1.522, 1.561] |
| 200 agents, draining drift -30 | 1.643 | 2.174 [2.138, 2.211] | 2.767 [2.725, 2.809] |
| 200 agents, accumulating drift +60 | 1.007 | 1.009 [1.008, 1.009] | 1.009 [1.009, 1.010] |
| 3 agents, steady zero drift | n/a | n/a | 1.375 [1.325, 1.424] |

The group of twenty captures a mean 86.3% of the full pool's excess gain at zero drift, with an observed range of 80.8% to 90.7%. It captures 66.5% under draining drift, with an observed range of 58.0% to 73.5%. Thus the scale at which gains saturate depends on the demand regime. Accumulating demand produces a full-pool gain under 1.3% on every seed.

| Demand cell | C/V with expiry recovery: mean [MC interval] | C/V with hypothetical round recovery: mean [MC interval] |
|---|---:|---:|
| Zero drift | 0.871 [0.865, 0.878] | 1.531 [1.511, 1.551] |
| Draining drift | 0.649 [0.643, 0.655] | 2.737 [2.696, 2.778] |
| Accumulating drift | 0.970 [0.970, 0.970] | 0.987 [0.987, 0.988] |
| Few-steady | 0.00736 [0.00678, 0.00795] | 0.924 [0.902, 0.946] |

Every sampled expiry case favors the channel by this capital-duration metric. The few-steady round-recovery ratio ranges from 0.854 to 1.039, so that hypothetical comparison changes order on some seeds. The zero-drift full-pool gain ranges from 1.456 to 1.627; its sample maximum exceeds `pi/2`, as expected when a diffusion-limit ratio of expectations is applied to individual finite realizations. None of these capital ratios prices membership churn, fees, or correlated availability failures.

Reproduce the complete result with:

```sh
node --experimental-strip-types audit/peer_review/model_sensitivity.ts > audit/peer_review/model_sensitivity.json
```

The script also accepts `--cell zero`, `--cell drain`, `--cell accumulate`, and `--cell steady` for independent jobs. `--combine` followed by those four JSON paths emits the same combined structure.
