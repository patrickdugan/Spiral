# Connector Calculus: Adversarial Critique

## Findings, surviving claims, and required revisions

**Authors:** Prepared for Dugan

**Program:** Spiral

**Version:** September 11, 2026; baseline a0a3140; exploratory audit

## Executive verdict

The elementary algebra survives. The present implementation does not establish all the safety, reproducibility, and economic properties its surrounding language can suggest. The most important defects are accepted closed walks that reject after changing balances, hash-dependent generation despite fixed nominal seeds, reward-allocation boundary failures, and compilation predicates that are stated but not enforced. A cut's liquidity stock also cannot be read as a cap on gross throughput over time.

Three sub-agents independently challenged algebra, inference, and incentives, then cross-examined one another. The coordinator supplied a testnet4 header replay from a retained offline node and a separate revised ledger. This critique preserves the original paper and code; all counterexamples, controls, receipts, and new references are separate. Findings are not prevalence estimates, and the study is not a live Lightning or money-laundering experiment.

The follow-up is **Liquidity on Trial: Counterexamples and a Resource-Sensitive Semantics for Agent Payment Networks**. Its distinct notation uses ledger X, channel holdings ell, pending holds h, a resource registry U, and an operation journal J. It does not inherit protocol guarantees merely by changing notation.

## 1. Findings matrix

| ID | Finding | Evidence and verdict |
|---|---|---|
| C1 | Rejection can partially mutate balances | 161 of 312 deliberately repeated-triangle cases; genuine accepted-interface-input defect |
| C2 | Seeds omit a consequential execution input | Same topology/public-policy hashes, hash seeds 1/2, different state and 105/102 successes out of 110 |
| C3 | Instantaneous stock is not horizon throughput | Initial outward 50 supports outward 200 with replenishment; reordered demand fails seven times |
| C4 | Compilation is not funded execution | Duplicate exposure, zero bond, negative expiry accepted; specified predicates remain external assumptions |
| C5 | Resource reward accounting has edge cases | Mixed-coordinate weight, zero-weight rounding payout, invalid negative slash |
| C6 | Delivery and a bond field do not identify economics | Unreserved bond fixture; equal scores in opposite-value worlds; declared costs can reverse net value |
| C7 | Oracle interpretation needs two budgets | Feasibility inspection and executed attempts differ; matched-prefix/full-catalog trajectory controls pass |
| C8 | Current receipts do not identify privacy or emergence | Failed probes are not bits; scripted policies and programmed bonuses are not observed agent societies |

## 2. C1: atomicity and the accepted route domain

Original references: algebra.py:108 and :119; Connector validation at :159; manuscript.md:127 and Appendix A.2 at :581. Paths below are relative to the frozen repository root.

On the walk A-B-C-A-B-C-A, each forward edge initially holds 100 and q=60. The route-wide check sees the original 100 at every occurrence. Execution completes one cycle, then rejects on the next edge. The final forward balances are 40,40,40. Capacity conservation still passes, demonstrating why that invariant cannot certify rollback.

The strongest defense is valid but narrow: the public-topology routing campaigns enumerate simple paths, and the ordinary simple-path theorem survives. The counterexample does not show their CSV rows were corrupted by repeated walks. However, the circular-connector interface accepts a closed sequence without enforcing simple-cycle restrictions. Either validate that domain or stage and commit the operation transactionally. The separate reference supplies both sequential clone-and-commit and gross-prefunded variants; each rejects all 161 failing grid cases unchanged.

The appendix's final-state-polytope equivalence likewise needs a domain and execution interpretation. A zero net vector can fail concurrent gross prefunding, even though sequentially settled out-and-back transfers are possible. Do not equate terminal netting, simultaneous reservation, and a sequence of settled operations.

## 3. C2: reproducibility is weaker than the receipts suggest

Original references: public_topology.py:94-137 and :151-187; public_topology_eval.py:191-214. The audit uses actual retained source and snapshot hashes, Python 3.12.14, and NetworkX 3.6.1.

Two independent processes set PYTHONHASHSEED to 1 and 2. Both reproduce sample public-random-4-5ae5f9236d61, identical canonical edges, and identical canonical public metadata. But state generation sorts raw edge orientations before canonicalizing endpoints. Different iteration orders assign the same stream of random capacity/balance draws to different channels. Generated-state and route-catalog digests differ. On one uniform/diffuse cell, each of the four original routing policies delivers 105/110 versus 102/110 evaluation demands.

In the final pinned-hash-seed diagnostic, only 6 of 72 comparisons exactly reproduce retained policy records; 64 have differing success counts and 50 differing failed-attempt counts, with 66 differing on either field. The new budget comparisons are internally valid on their own paired executions, but they are not an exact decomposition of the previous headline estimates.

An independent canonical-order reference makes the two hash-seed witnesses identical at 106/110. That is evidence for the mechanism and a candidate repair, not permission to overwrite historical data with a more convenient run. Required revision: canonicalize both endpoint orientation and iteration order before attaching random draws; freeze candidate tie-breaking and dependency versions; save generated states and ordered catalogs or their reconstruction specification. Preserve the original results as process-conditional historical outputs.

## 4. C3: replace gross horizon demand with prefix inventory

Original reference: manuscript.md:194-204, cut completion. The phrase demand across a cut needs a definition. If it means cumulative gross outward volume, comparing it directly with today's outward inventory is not a necessary capital condition.

One channel starts with capacity 100 and outward balance 50. Five pairs of outward 40 then inward 40 settle without failure: 200 outward units reuse 50 units of initial stock. Grouping the same five outward demands before the five inward ones causes seven failures. Gross demand overstates the capital requirement in one ordering, and final net demand understates the timing problem in another.

Required revision: for each execution prefix, account for initial directional inventory minus settled outward flow plus settled inward flow plus net capacity changes. Constraints on every prefix are necessary; a single final net total is not enough. On a multihop network, aggregate cut feasibility is still insufficient because of edge-local balances, route restrictions, policy, and pending resources. The paper may retain a no-replenishment gross-demand stress rule if it labels that assumption explicitly.

## 5. C4-C6: resource accounting and economics

### 5.1 Compilation

Original references: manuscript.md:177 and Appendix A.5 at :599; GhostPlan.compile at algebra.py:184; apply_connector at :198. The mathematical compile predicate lists funding, consent, unique exposure, expiry, and bond conditions. The implementation accepts no authenticated registry or wallet budget and discards key metadata when adding a channel. Distinct connectors naming the same capital source can add 200 modeled units, and zero-bond or already-expired declarations are accepted.

The defense is that the simulator assumes external validation. Accept that defense only by narrowing the claim: compilation safety is a specification conditional on an adapter, not an implemented proof of funded execution. A generated capital identifier does not authenticate economic scarcity.

### 5.2 Rewards and record domains

Original references: bonding.py:53, :70, :85, and :95. The fixed-resource theorem survives six identity-splitting controls: coalition payout remains 50,000 for 1 through 32 identities with unchanged authenticated weights.

The implementation has separate obligations. Maximal capital and maximal score from inconsistent claims can form a weight no single claim attests. A two-unit reward pool can be paid entirely to the last-sorted zero-weight resource after integer truncation. An invalid availability record, 120 available steps out of 100 promised, yields slash -1,249 and release 26,249 from bond 25,000. This last witness is outside the intended record domain; the defect is accepting that domain violation before settlement, not refuting valid-input arithmetic.

Required revision: define one coherent authenticated resource-level record and score-estimation protocol; exclude zero weights from residue allocation; conserve the integer pool; reject invalid service, time, volume, and bond fields before mutation. More claimant observations can also change a maximum-selected score even when real service quality is unchanged. That changes the theorem's premise, so it is a score-estimation warning rather than an identity-partition counterexample.

### 5.3 Escrow, value, and predictive persistence

Original references: hive_lab.py:498-513 and :633; manuscript.md:466 and :547. A white-box fixture spends 20,000 of endpoint wealth on channel principal, declares a 4,000 bond, and leaves no separate reserve, while its reported accounting error remains zero. Under an additional-posted-bond contract this is underfunded. A lien on the same channel could be coherent, but enforcement, priority, and usable-balance effects are absent. This is not evidence of real double spending.

Identical observed service records can coexist with toy incremental net values +9,000 and -1,000. Thus service scoring cannot identify external welfare by itself. The original paper already acknowledges costs are missing, so the new contribution is an executable identification counterexample and cost sensitivity, not discovery of a concealed limitation. A programmed coalition income bonus is explicitly labeled as an assumption in the original supplement and must remain so.

Replace the phrase useful only when demand is stationary with value depends on forecast quality over the deployment horizon. A time-homogeneous Markov law can be anti-persistent, and a changing schedule can be predictable. In the exact eight-epoch two-region model with stay probability .75, historical-region placement advantage falls from .498047 services at immediate deployment to .123047 after two epochs and .029297 after four. These are exact toy expectations, not market forecasts.

## 6. C7: the oracle survives a narrower challenge

The first objection was that the oracle filters eight candidates while retry and online execute at most three attempts. The incentives reviewer challenged an overstrong conclusion: online already sees the public descriptions of all eight; privileged feasibility inspection can legitimately improve choice under an operational attempt cap.

Adjudication: keep two budget axes. Prefix-oracle-three restricts inspection; retry-eight relaxes executed attempts. Under the original free-failed-attempt balance semantics, retry and an oracle choosing the first feasible path from the same ordered set have equal trajectories by induction. This does not eliminate information value once attempts consume time or other resources.

The final pinned diagnostic uses 18 cells, 126 episodes, and 1,980 evaluation demands per policy. Retry-three, frozen-feedback-three, and prefix-oracle-three each deliver 84.646%; retry-three emits 426 infeasible attempts and the oracle none. Retry-eight and oracle-eight each deliver 84.798%, with 522 versus zero failed attempts. All 54 paired trajectory checks pass. These are exploratory subset results without a new confirmatory interval.

The greedy oracle is also not an optimal full-horizon controller: a two-demand witness delivers one payment when an alternative feasible first route preserves capacity to deliver both. Retain upper-information reference; remove any implication of an upper bound on all possible cumulative service.

## 7. Statistical integrity: a clean dataset, unsafe edge handling

Original references: public_topology_analysis.py:102-161 and :211-226. The actual 4,536 rows contain no duplicate condition keys and no unmatched policy pairs in audited contrasts. All 37 sample IDs reconstruct. Among the 28 holdouts, 182/378 pairs share a node and 47 share an edge, but median node overlap is zero. Do not claim that overlap alone proves dependence or derive an effective sample size from it. Conditional random draws from a fixed snapshot can remain independent.

Negative controls nevertheless expose silently overwritten duplicates, discarded missing pairs, zero-width intervals for empty/single-cluster inputs, a one-sided equivalence flag, and a vacuous empty-data oracle check. Required revision: fail closed on inadequate or inconsistent inputs and check both practical-equivalence bounds. Preserve the valid distinction between these latent pipeline hazards and the actual clean retained rows.

The snapshot is still one historical environment with synthetic hidden state. The original confidence intervals do not cover model misspecification, unknown hash-order inputs, omitted settlement resources, or a population of future networks. This post-hoc audit cannot retroactively preregister its preferred corrections.

## 8. Retained testnet4 node: actual evidence and hard limits

The configured port at 127.0.0.1:48332 was unreachable. We did not restart a node, open a wallet, read credentials, or broadcast transactions. Instead, a public-only parser read the retained testnet4 datadir's block records and exported 512 linked historical headers, heights 147473-147984, anchored to the last logged tip on August 11.

The independent algebra reviewer recomputed all 512 header hashes and encoded-target checks, verified 511 internal parent links, and reread three exact on-disk offsets. All matched. These checks do not validate full consensus, current chain choice, transactions, or any funding event. A historical metadata string said 512 parent links; the correct count is 511, recorded as an erratum without overwriting the original receipt bytes.

Of 511 adjacent miner timestamp differences, 64 are nonpositive. Minimum is -6,004 seconds; median 1,201. These are not observed arrival or funding times. Depth-gate scenarios therefore use block order and explicitly assumed inclusion, demand, and costs. Repeating the same arithmetic over different header windows is not empirical replication. The incentives reviewer consumes this authenticated scaffold and shows a hypothetical three-block service window changing from +1,000 to -1,000 toy operator units when depth changes from immediate to three. None of those receipts is actual testnet income.

Testnet4 identity is documented by [BIP 94](https://github.com/bitcoin/bips/blob/master/bip-0094.mediawiki); Lightning readiness and minimum-depth conditions belong to [BOLT 2](https://github.com/lightning/bolts/blob/master/02-peer-protocol.md). Bitcoin testnet4 data by itself does not constitute a live Lightning experiment.

\pagebreak

## 9. Proposed disposition of the original paper

Retain the elementary conservation results, the fixed-authenticated-weight identity theorem, the distinction between a ghost plan and a real connector, and the reported original outputs as historical process-conditional simulations. Correct the domain of route and cut statements. Downgrade compilation guarantees to unimplemented conditional specifications. Strengthen receipts and deterministic ordering before new headline campaigns. Replace broad privacy, economics, and agent-emergence inferences with explicit measurement obligations.

The follow-up's new ledger was itself challenged: a float direction initially bypassed its membership guard and caused post-mutation validation failure. That finding is preserved, an exact integer guard was added, and seven regression cases were included. Together with original controls, 32 new audit/reference test cases pass. The original source remains unchanged. Passing those tests is finite implementation evidence, not a complete protocol proof.

The next research investment should be a canonical, resource-budgeted, settlement-aware evaluation on multiple dated environments. The present audit gives concrete reasons to do that work; it does not claim that changing notation or adding a bond number has already solved it.
