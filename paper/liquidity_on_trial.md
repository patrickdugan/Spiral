# Liquidity on Trial

## Counterexamples and a Resource-Sensitive Semantics for Agent Payment Networks

**Authors:** Dugan

**Program:** Spiral

**Version:** Adversarial follow-up draft, September 11, 2026

## Abstract

An algebra can be internally consistent while its implementation accepts operations outside the proved domain, and a successful simulation can answer a narrower question than its surrounding narrative. We subject Connector Calculus to three independent sub-agent audits, executable counterexamples, cross-examination, and a historical Bitcoin testnet4 replay. The elementary channel-conservation and fixed-resource identity-splitting results survive. Stronger interpretations do not. Repeated-edge walks can pass the implementation's preflight test and fail after partial mutation. A horizon's gross outward demand is not bounded by the initial directional stock when reverse flows replenish it. Reward accounting contains boundary cases, and nominal seeded results change with Python's hash-dependent graph order. Oracle comparisons must separate information from candidate and attempt budgets; an informed greedy policy is not an optimal full-horizon policy.

The follow-up introduces distinct ledger notation, gross directional reservation constraints, transactional failure semantics, a prefix cut identity, and an explicit separation between service measurement and economic value. Retained Bitcoin Core block files from an offline testnet4 node supply 512 linked historical headers, not a live Lightning experiment. Their timestamps are unsuitable as observed settlement clocks: 64 of 511 adjacent differences are nonpositive. Block-depth scenarios therefore use ordinal heights and declared inclusion assumptions. The result is not a replacement protocol or a claim that autonomous payment economies have been observed. It is a smaller, more falsifiable foundation for testing them, with reproducible witnesses, preserved controls, and explicit unresolved obligations.

**Keywords:** payment channels, resource semantics, adversarial evaluation, liquidity, autonomous agents, simulation validity, testnet4

## 1. What is on trial?

The original paper distinguishes a public channel graph from a private liquidity state, treats ghost edges as provisional plans, and proposes bonding scarce capital to measurable service. These are useful separations. The ghost construction itself is older than the liquidity setting: it was filed as a method for netting derivative subgraphs toward a target settlement value [R7], and what the original paper adds is the transplant from clearing to directional channel state, not the rewrite idea. Its strongest defensible mathematical results are local: a feasible transfer preserves a channel's capacity; its balances remain bounded; a zero-fee closed route preserves net node ownership; and partitioning a fixed resource reward among more names cannot enlarge that reward [R1]. None of these statements establishes an optimal routing algorithm, verifies deployed collateral, or predicts the behavior of a population of independently released AI systems.

Our question is consequently not whether the paper is entirely right or entirely wrong. It is which implication survives each change of level: from formula to accepted program input, from program behavior to experimental contrast, from contrast to economic interpretation, and from synthetic time to settlement. A passing conservation test cannot stand in for a failure-atomicity test. An invariant over authenticated capital cannot authenticate that capital. An interval conditional on one snapshot cannot make the snapshot representative of future networks.

The audit targets the unmodified repository at commit a0a3140. Original manuscript, source code, configurations, CSV outputs, and PDF remain intact. The new results are exploratory, designed after seeing the earlier study. They are not a fourth preregistered confirmation campaign. Exact counterexamples need no significance test to refute a universal program assertion; empirical prevalence would require a different sampling design. This distinction governs every result below.

### 1.1 Contributions

We provide four contributions. First, executable witnesses expose failures of transactional validation, temporal cut reasoning, and reward accounting while preserving the original's valid restricted claims. Second, matched-budget comparisons distinguish search from information and identify the conditions under which two policies are mathematically equivalent. Third, a public-only testnet4 header audit establishes what a retained, offline node's block archive can and cannot contribute. Fourth, a resource-sensitive transition relation makes direction, reservation, lifecycle, evidence, and cost obligations explicit.

This is a research audit and reference model, not software for obscuring money flows. Payment privacy and harmful activity are not synonymous. Neither the original experiments nor this follow-up measures actual laundering, implements a covert communication channel, or demonstrates an emergent clandestine agent society.

## 2. Method: adversaries, controls, and adjudication

Three reviewer processes worked independently on algebra, inference, and incentives. Each read the frozen source and ran bounded simulations. The coordinating process inspected the retained node data, implemented a small separate resource ledger, and integrated the evidence. A second round assigned reviewers to challenge another reviewer's conclusions. Their actual observations and revisions are recorded in the companion Swarm Arena ledger. Reviewer concurrence is not a vote-based proof: the authority of a finding is its witness, source reference, or stated derivation.

The protocol used five dispositions. A **surviving theorem** remains true on its declared domain. An **implementation counterexample** is an accepted input whose behavior violates the claimed program contract. A **scope failure** appears only when an acknowledged assumption is removed. An **inferential limitation** narrows what an experiment identifies. An **unresolved obligation** requires evidence or infrastructure not present here. These categories prevent a reviewer from winning an argument merely by redescribing an explicitly omitted feature as an accidental discovery.

The algebra reviewer supplied ordinary simple-path controls as well as adversarial walks. The incentives reviewer held authenticated resource weights fixed before changing the weight estimator or record domain. The inference reviewer compared policies on paired demand streams and matched candidate sets. The testnet audit separated data checks from fabricated service assumptions. These controls are essential: otherwise a critique can be as overstated as the proposition it attacks.

### 2.1 What the swarm is, and is not

There are two distinct populations. The audit swarm consists of language-model sub-agents reviewing code and evidence. The simulated payment agents are scripted policies, not independently trained or economically autonomous language models. Their counts, trials, and rewards must not be described as observed AI societal behavior. Similarly, a grid of counterexamples is a set of designed cases, not an estimate of an incident rate in Lightning.

## 3. The algebra that survives

For a channel with total capacity c and one directional balance b, the opposite balance is defined as c-b. A transfer of q changes b to b-q and the opposite to c-b+q. Conservation follows immediately. Subject to q being nonnegative and no larger than genuinely available directional resources, the new balance lies in the original interval. This useful invariant is partly structural: the implementation derives the reverse balance from the total and forward balance.

The audit's 2,000 ordinary simple-path controls preserve capacity and bounds. This does not turn simulation into a proof, but it confirms that the challenge harness is not indiscriminately breaking the simplest valid use case. The fixed-resource reward theorem also survives: six identity counts from 1 through 32 produce the same 50,000-unit coalition payout when capital and service weight are held fixed. The theorem says nothing about whether conflicting claims are authenticated or how a noisy service weight is estimated.

The zero-fee closed-route claim survives as written. Real relay fees produce unequal hop amounts and net fee income for intermediaries, so per-node zero divergence is not the right production invariant. The original paper already states this omission. We classify fee-adjusted failures as a protocol-scope boundary, not a refutation of the restricted zero-fee proposition. Actual Lightning forwarding fees arise from differences between incoming and outgoing HTLC amounts [R2].

## 4. Atomicity fails outside the simple-route domain

Consider three channels oriented A to B, B to C, and C to A, each with capacity 100 and forward balance 100. Submit the closed walk A,B,C,A,B,C,A with amount 60. The preflight routine checks each occurrence against the same initial balance and declares the route feasible. Execution transfers 60 on each edge of the first cycle. The next A-to-B transfer then fails, because only 40 remains. The rejection leaves every forward balance at 40 rather than restoring 100.

This is a precise implementation counterexample to all-or-nothing rejection over the interface's accepted closed walks. It does not show that the simple-path campaign used such a walk. The Connector constructor requires circular endpoints to coincide but does not require internal vertices or edges to be unique. A defense based on the mathematical convention that a path is simple therefore demands an executable guard, or a narrower interface contract. Validation cannot silently assume a domain that the public constructor does not enforce.

In an adversarial grid of 312 prevalidated repeated-triangle cases, 161 rejected after partial mutation and 151 completed. Those counts characterize this deliberately hostile grid, not ordinary traffic. The accompanying transactional reference stages a sequential zero-fee operation on a copy and commits only after successful validation. It preserves the original's intended sequential semantics, including reverse replenishment. The new resource ledger in Section 9 instead reserves gross simultaneous obligations; these are different semantics and are not interchangeable.

### 4.1 Why netting is insufficient

A transfer out and an equal transfer back have a zero terminal net vector. This does not imply that they can be concurrently reserved: the incoming amount is not yet spendable. Conversely, a sequential out-and-back program may be feasible precisely because the first settled transfer replenishes the second direction. A correct model must state whether it represents a settled sequence, simultaneous pending commitments, or an abstract terminal displacement. Confusing them hides both false acceptances and false rejections.

## 5. Liquidity stock is not cumulative throughput

The original cut-completion discussion compares demand over a horizon with directional liquidity at one instant. That comparison is only valid under further assumptions about net direction and replenishment. In a channel initially able to send 50 units outward, five alternating outward/inward pairs of 40 each deliver 200 units outward with no additional capital. Gross outward throughput exceeds the initial stock without contradiction: inward transfers restore it.

Reordering the same outward and inward totals by putting all outward demands first causes seven of ten demands to fail in the witness. Thus even aggregate net demand is insufficient to guarantee service for an arbitrary arrival sequence. Feasibility depends on every prefix. The same endpoint totals, same total capacity, and same final theoretical imbalance can describe materially different execution histories.

Let A be a cut and let L_A(n) denote the sum of available ownership-side balances oriented from A to its complement, before reservations. Let O_A(n) and I_A(n) be cumulative settled amounts actually crossing that cut outward and inward, respectively. Let K_A(n) be net added directional stock, including removals with a negative sign. Then the accounting identity is:

```math
L_A(n)=L_A(0)-O_A(n)+I_A(n)+K_A(n).
```

Consequently a necessary prefix bound is:

```math
O_A(n)-I_A(n)\leq L_A(0)+K_A(n)\quad\mathrm{for\ every}\ n.
```

This statement concerns actual crossing amounts, not automatically the final recipient amount: fees and routes crossing a cut repeatedly require hop-level accounting. Even a valid aggregate cut bound is not sufficient for end-to-end delivery when liquidity is on the wrong edge, routes are restricted, policies disagree, or pending obligations consume slots. A ghost edge is therefore a proposal for one constraint, not a certificate of whole-network feasibility.

## 6. Information, action budgets, and the oracle

The sealed public-topology study uses an eight-path catalog. Its retry and online policies attempt at most three routes; its oracle examines hidden feasibility across the catalog before emitting a feasible attempt. Online also sees the public description of all eight candidates. The difference is privileged feasibility inspection, not mere access to a longer public list. It is a legitimate comparison of information packages under a restricted executed-attempt budget, but not a resource-neutral measure of generic intelligence. Zero infeasible probes is a property of the oracle's definition, not an experimentally discovered privacy technology.

There is an exact control. Fix the same ordered candidate catalog, initial state, and demand sequence. Compare a retry policy that attempts every candidate with an oracle that selects the first feasible candidate in that same order. If failed attempts do not change balances and both policies perform the same successful transfer, they pick the same first feasible path at the first demand. Their states then match. Induction gives identical balance trajectories and deliveries for every demand. Their failed-attempt counts can differ.

This equality is conditional. It need not hold if failures consume time, lock funds, incur fees, change peer reputation, or exhaust an external deadline. Those are precisely the resources a more realistic model must include. It also does not imply that information is useless: information can reduce attempts, latency, or external cost without increasing delivery in this model. Matching a three-route prefix restricts oracle inspection; allowing eight retries increases operational attempts. Neither control erases the value of hidden information under the original three-attempt constraint.

In the final pinned-hash-seed diagnostic, seven policies run on 18 paired cells for 126 episodes, each 220 demands with 110 scored. All 54 full-trajectory equality checks pass: retry-three equals prefix-oracle-three and frozen-feedback-three; retry-eight equals oracle-eight. The table reports 1,980 evaluation demands per policy. It is a post-hoc diagnostic, not an exact decomposition of the original combined estimate.

| Policy | Success (%) | Infeasible attempts |
|---|---|---|
| Public one-shot | 82.879 | 339 |
| Retry-three | 84.646 | 426 |
| Online-three | 84.596 | 436 |
| Prefix-oracle-three | 84.646 | 0 |
| Retry-eight | 84.798 | 522 |
| Oracle-eight | 84.798 | 0 |

### 6.1 The informed policy is not a full-horizon upper bound

A two-demand counterexample is enough. A greedy informed policy consumes a channel needed by the second payment, although another feasible first route would preserve that channel. It delivers one of the two demands; a different feasible first choice delivers both. Perfect knowledge of the present balance does not confer future demand knowledge or solve intertemporal allocation. The paper's narrow description of an upper-information condition can be retained. A stronger reading as the best attainable total service must be rejected.

The same caution applies to the phrase agent capability. A terminal-feedback heuristic tests one update rule and one observation interface. A small or absent advantage does not bound every reinforcement learner or language-model agent. Conversely, success by a centrally supplied oracle does not show that an independent deployed agent can acquire its observations lawfully, accurately, or cheaply.

## 7. Inference and reproducibility obligations

The earlier results are real outputs of the retained simulator, not measurements of live balances. Their public structural substrate is one July 2023 gossip snapshot; capacities, directional balances, demand, and settlement are synthetic. The confidence intervals quantify variation within the specified analysis, conditional on this modeling pipeline. They do not include uncertainty about the missing economic or protocol variables.

Connected subgraphs sampled from a common snapshot may overlap. All 37 original sample IDs reconstruct, including 28 held-out samples. Those holdouts contain 1,550 unique nodes across 1,792 node occurrences; 182 of 378 pairs share a node, and 47 share an edge. Median pairwise node overlap is zero, and the maximum is 18 of 64 nodes. Overlap does not, by itself, prove a covariance or invalidate conditional Monte Carlo arguments: independently generated random inputs can remain independent conditional on a fixed graph. It does limit population interpretations and requires care about shared latent shocks and the sampling target.

Several analysis functions silently overwrite duplicate pairing keys, discard unmatched pairs, or return zero-width intervals when fewer than two cluster means are available. These behaviors admit negative controls that turn corrupted or inadequate data into apparently precise answers. They must not be confused with evidence that the retained CSVs actually contain those defects. The actual 4,536 rows have zero duplicate condition keys and no missing policy pairs in the audited contrasts. Another negative control shows that a one-sided upper-bound flag can accept a large negative effect as practically equivalent; equivalence requires both boundaries.

Finally, source and random seeds are necessary but not sufficient for this implementation's replay. Independent Python processes with hash seeds 1 and 2 reconstruct the same sample ID, canonical graph, and public policy metadata, yet generate different capacity/balance assignments and path-catalog hashes. On the selected uniform/diffuse cell, all four original routing policies deliver 105 of 110 evaluation demands under one process and 102 under the other. The state generator sorts raw edge tuples before canonicalizing their endpoints, so iteration-order changes reassign the seeded random draws. Candidate enumeration has another ordering dependency.

The final pinned diagnostic exactly reproduces only 6 of 72 old policy records; 66 differ on success count or failed-attempt count. This does not prove the original paired comparisons were fabricated or numerically wrong within their originating process. It proves that the published configuration and random seeds omit a consequential execution input. A separate canonical-order reference makes the two hash-seed witnesses agree at 106 of 110; that is a changed specification, not a retroactive correction of the old data. A portable receipt must bind canonical serialization, ordered candidates, dependency versions, exogenous demand, policy parameters, and result bytes.

### 7.1 Which earlier conclusions need narrowing?

The retained combined estimates remain descriptive evidence: retries outperform one-shot routing in the original simulator; the terminal heuristic contributes a small ordering advantage; stationary synthetic demand favors a failure-aware static connector. They do not establish universal necessity of stationary demand. Failure to detect a gain after a shift is not proof that all adaptive capital strategies fail. A positive result conditional on free instantaneous deployment does not prove a positive return on investment.

Our adversarial analysis was selected after inspecting these outcomes. It cannot retroactively become a confirmatory preregistration. The next affirmative capability claim should be evaluated on new snapshots, independently constructed execution states, matched resources, and a frozen analysis with explicit multiplicity and stopping rules.

## 8. Testnet4 evidence: use the chain without inventing an experiment

The retained environment is a pruned Bitcoin Core testnet4 datadir on a local volume. Its configured local TCP RPC port 48332 was unreachable at inspection. No wallet was opened, no authentication cookie was read, no node was restarted, and no transaction was constructed or broadcast. We used the public block archive instead of representing an unavailable endpoint as a live test.

The parser de-obfuscates Core's on-disk records, checks testnet4 message framing, hashes each 80-byte header, verifies that its hash meets its encoded proof-of-work target, and follows parent hashes back from the last public UpdateTip anchor. The exported 512-header chain spans heights 147473 through 147984. The tip was logged on August 11, 2026; it is not asserted to be the current network tip. File-offset/header digests and a CSV digest make this selection reproducible. Testnet4's network identity and consensus differences are specified in BIP 94 [R3].

These checks are not a full consensus validation. We do not validate the entire difficulty schedule, Merkle roots, transactions, UTXO state, or current best chain. A pruned local historical branch is adequate for demonstrating event ordering and timestamp pitfalls, but not for certifying a funding output or deployed Lightning channel.

### 8.1 Three clocks must remain separate

The adjacent miner-header timestamp differences have median 1,201 seconds, minimum -6,004 seconds, and maximum 5,708 seconds; 64 of 511 differences are nonpositive. These are measured properties of the selected historical headers. They are not measured payment latencies. The local log observation time is also not a clean alternative because a node may process historical blocks during catch-up. Neither quantity should be clamped into a convenient empirical funding-delay distribution.

We therefore distinguish ordinal block height, miner-declared header time, and independently observed arrival or application time. Confirmation depth uses the first; a latency experiment requires the third, with instrumentation and a stated synchronization model. Lightning channel readiness depends on negotiated funding and channel conditions, including minimum depth, rather than a universal immediate-activation rule [R4]. Zero-confirmation operation is a separate trust configuration, not permission to set every funding delay to zero.

![Figure 1. Measured adjacent header timestamp differences on the selected historical branch. Rust-colored points are nonpositive. These are miner timestamps, not funding or payment latencies.](audit/figures/header_clock.png)

### 8.2 The settlement sensitivity is synthetic

Declare a unit demand at each subsequent block and a connector with ten outward units. Suppose funding is submitted just after an anchor block, included after one block, and usable at a chosen confirmation depth. Over a six-block service horizon, instantaneous activation delivers six demands; activation at depth three delivers four; activation at depth six delivers one. These are ordinal arithmetic scenarios over real header windows, not observed channel outcomes. Inclusion lag, demand, capital, and depth are inputs.

Repeated windows do not create independent replications of this identical arithmetic. The experiment's value is to make the hidden temporal assumption visible: useful demand may expire before usable capital arrives. A later live experiment needs isolated test channels, explicit test-fund authority, implementation compatibility, peer consent, and observed application events. Bitcoin testnet4 alone is not a Lightning network.

## 9. A distinct resource-sensitive notation

We replace the original S/B/K notation with a ledger state X and distinguish commitments from spendable balances. Channel identifiers are retained even when endpoints repeat. Let i index a channel and d in {+,-} its direction. Capacity is chi_i; directional ownership balance is ell_(i,d); h_(i,d) is a held pending amount; and r_(i,d) is an unavailable reserve. The state is:

```math
X_n=(\ell_n,h_n,\mathcal{U}_n,\mathcal{J}_n).
```

Here U is the authenticated resource registry and J is the operation/lifecycle journal. Topology and policies are typed context for the transition relation, not evidence that a resource exists. The elementary constraints are:

```math
\ell_{i,+}+\ell_{i,-}=\chi_i,\qquad 0\leq h_{i,d}+r_{i,d}\leq\ell_{i,d}.
```

Available resource is ell-h-r. Reserving an operation changes h but not ownership ell. Settling it releases its reservation and changes ell. Aborting releases the reservation without a balance transfer. This is a centralized reference semantics: it does not prove distributed HTLC atomicity, consensus, or Byzantine agreement.

### 9.1 Hop-adjusted amounts

For a simple route with m edges, let y_m=q be recipient credit. If relay j charges f_j on its outgoing amount, construct earlier amounts backward:

```math
y_j=y_{j+1}+f_j(y_{j+1}),\qquad j=m-1,\ldots,1.
```

The payer debit is y_1, and total intermediary income is y_1-q. A reference example delivering 100,000 msat through two relays with base/ppm policies (1,000,1,000) and (2,000,2,000) produces hop amounts 103,302, 102,200, and 100,000 msat. Summed relay income is 3,302 msat. The payer is not charged an additional fee for its own first hop. Units, rounding, and fee-policy orientation belong in the contract, not in an ambiguous scalar cost term.

### 9.2 Gross reservations and failure identity

An operation may reference a resource more than once. Define g_(i,d)(o) as the sum of all its simultaneous obligations in that direction. The prepare rule requires every channel to satisfy:

```math
g_{i,d}(o)\leq\ell_{i,d}-h_{i,d}-r_{i,d}.
```

Check all requirements before updating any reservation. Acceptance adds g to h and records a fresh operation identifier. A rejected transition returns the original state, not a partially mutated prefix. Once settled or aborted, an identifier cannot be reused in this bounded journal. Concurrent obligations cannot spend the same residual balance twice; anticipated incoming settlement is not netted away before it occurs.

The separate ResourceLedger reference passes 13 test cases, including an exhaustive grid of 440 small concurrent ledger states. It checks repeated-resource rejection, gross-versus-net feasibility, concurrent double-use, abort release, identifier reuse, parallel-channel identity, fee telescoping, and direction type/domain. The grid is finite implementation evidence, not a proof of arbitrary distributed execution. Its assumptions are deliberate: channel objects are mutated only through the ledger, resources do not disappear between prepare and finish, and finish is a local atomic event.

The type checks were not flawless in the first draft. During cross-examination the algebra reviewer supplied direction=1.0; Python's equality accepted it as 1, and finish later rejected a floating balance after mutation. The coordinator added an exact integer guard and seven regression cases. The pre-fix evidence is preserved with its source hash. The same reviewer independently checked 5,000 properly typed state-machine steps and found no invariant failure. This self-correction is part of the result, not an exchange edited out to make the new model appear infallible.

## 10. Conditional results for the revised semantics

### Proposition L1: conserved capacity under settlement

For a settled obligation of amount y on a channel direction, subtract y from that directional balance and add y to its opposite. The sum is unchanged. A finite collection of such updates preserves every channel's capacity. Fees alter which amounts are transferred and each node's net ownership, not this per-channel identity. Funding, closure, and external transfers are distinct resource-creation/removal events and are excluded from the fixed-capacity proposition.

### Proposition L2: bounded simultaneous reservations

If all gross requirements are checked before any mutation and accepted reservations are immediately deducted from availability, then newly accepted obligations plus existing reservations do not exceed directional spendable resources. On settlement, removing its reservation and debiting exactly the reserved amount preserves sufficient resources for the remaining reservations. An opposite-direction settlement adds balance and cannot undermine that inequality. Abort only removes a hold. This argument assumes no unmodeled external balance mutation.

### Proposition L3: rejection identity

If validation has no side effects, and commit occurs only after every validation succeeds, rejection is the identity map on ledger state. Clone-and-commit is one local implementation. A database transaction is another. The proposition does not assert that independently controlled machines can obtain the same property without a settlement protocol. That missing implementation is a protocol obligation rather than a mathematical detail.

### Proposition L4: conditional identity-partition invariance

Let an authenticated registry assign one fixed weight w_u to each scarce resource u, and let R_u be its already determined integer allocation. Any partition of R_u among identities that sums exactly to R_u preserves coalition payout. This is the original theorem in a form that exposes its real premise. It does not cover an estimator that changes w_u when more identities submit observations, an unverified resource alias, or a rounding rule that violates zero-weight allocation.

### Proposition L5: value is not identifiable from service alone

Let two possible worlds have identical observed service records but different incremental customer surplus, resource cost, or opportunity cost. Every reward rule using only those records returns the same reward in both worlds. If their incremental net values have opposite signs, that rule cannot certify positive net value. This follows by indistinguishability, not by an empirical claim about how frequently such worlds occur. More authenticated observations or a narrower economic objective are required.

## 11. Bonding needs an account, not just a field

The incentives audit distinguishes the valid fixed-weight theorem from its implementation boundary. In one witness, two claims for a resource provide capital/score pairs (100,0.1) and (50,1). The aggregator independently chooses maximum capital and maximum score, fabricating weight 100 rather than the largest attested product 50. Against an equal 100-weight competitor in a 120-unit pool, the subject receives 60 rather than 40 under the maximum-product comparator. A coherent registry must state which jointly authenticated record defines the weight; choosing unrelated maxima is not authentication.

A second witness has a two-unit pool, three positive-weight sources, and a lexically last zero-weight source. Individual integer truncation leaves the pool as a remainder, which the implementation assigns to the final source; the zero-weight source receives both units. The defect violates zero-weight fairness, not necessarily the aggregate fixed-source identity-partition theorem. A third witness submits 120 available steps in a 100-step horizon and produces a negative slash of -1,249 and a 26,249 release on a 25,000 bond. The record is invalid; accepting and over-releasing it is a missing domain guard, not evidence that normal valid records all settle incorrectly.

The hive investment fixture declares a 4,000-unit bond after exhausting 20,000 units of endpoint wealth on channel capital. No separate escrow debit or lien is modeled. If the contract means an additional posted bond, the state is underfunded. If the contract instead intends a lien on channel principal, that priority, enforcement, and effect on usable liquidity must be specified. The ledger cannot silently choose whichever interpretation makes a headline feasible.

The compilation interface has the same gap: two distinct connector IDs naming the same capital identifier can add 200 modeled units, while a zero-bond connector and a negatively expired lease are accepted. The manuscript's stronger compile predicate is true if treated as a definition, but its required funding, uniqueness, consent, and expiry checks are not enforced by this graph rewrite. Our registry notation U names those unresolved obligations; it does not implement authentication by renaming a dictionary.

### 11.1 Costs and persistent demand

Incremental service is not incremental profit. A minimal accounting expression is:

```math
\Delta W=V_{\rm incremental}-F_{\rm chain}-F_{\rm relay}-C_{\rm capital}-C_{\rm failure}.
```

All terms require a declared perspective. A fee paid by one participant is income to another; adding all fees as social destruction double-counts transfers. A private operator's profit and a network's social surplus are distinct quantities. Block-depth delay can reduce V by missing the demand window even when all other costs are set to zero. Bond slashing is a contingent transfer and cannot substitute for missing service value or an authenticated fault model.

An exact two-region Markov countermodel clarifies the demand premise. Let rho be the probability of remaining in the current demand region, let the horizon be H=8 epochs, and deploy in the last observed region after delay d. Relative to random placement, expected additional service is:

```math
A(\rho,d,H)=\frac{1}{2}\sum_{t=d+1}^{H}(2\rho-1)^t.
```

The reviewer enumerated all 256 trajectories in each of 20 parameter cells and recovered the expression. At rho=0.75, the advantage falls from 0.498047 to 0.123047 to 0.029297 services for delays 0, 2, and 4. At rho=0.5 it vanishes; at rho=0.25, following the last location is harmful. With uniform initialization the process is stationary even when persistence is negative; a changing but known schedule can also be predictable. Predictive value over the deployment horizon is the operative premise, not stationarity alone.

![Figure 2. Exact conditional service advantage in the two-region eight-epoch countermodel. Curves are scenario calculations, not fitted empirical effects or independent samples.](audit/figures/forecast_delay.png)

The original manuscript acknowledges absent economic optimization and the supplement labels its coalition income bonus as a programmed assumption. We preserve those qualifications. Removing an explicitly supplied bonus is a sensitivity analysis, not discovery that the authors secretly observed emergent productivity. The general proposal remains plausible but conditional: rewards, demand, and capital must be coupled without counting self-generated volume as proof of external benefit.

## 12. What an agent evaluation must now report

A meaningful agent comparison should expose five budgets: observations, candidate evaluations, submitted attempts, committed capital, and elapsed execution or deadline. It should state which actors can access each signal, whether failed attempts alter resources, and whether a policy's training or calibration saw related graph regions or demand histories. Policy rewards should be distinguished from evaluator ground truth.

An adversary model must likewise name the observer and the protected variable before asserting privacy. Failed-attempt counts alone are not bits leaked. A minimal privacy evaluation would define a prior, an observation channel, and a posterior task such as a guessing advantage, while using synthetic identities and bounded consented data. Low observed failure volume neither proves privacy nor implies harmful intent. Our present audit does not implement such a measurement and makes no privacy-performance claim.

For liquidity, disclose not only average delivery but directional depletion, reservations, funding activation time, expiry, concentration, and rejected or rolled-back operations. For incentives, validate record domains, preserve integer pool conservation, prove zero-weight behavior, specify a capital registry, and account for escrow or lien priority. These requirements convert broad statements about agent societies into interfaces that can be falsified one at a time.

## 13. Limitations and the next falsifiable study

The audit is intentionally adversarial and exploratory. Its designed failures cannot estimate production prevalence. The resource ledger omits cryptographic settlement, channel commitment negotiation, MPP, CLTV progression, dust exposure, peer liveness, reorganization handling, and malicious distributed execution. Testnet headers constrain our description of time but do not validate Lightning behavior. The replay's selected historical branch and unusual miner timestamps should not be generalized into mainnet latency or economics.

The next study should freeze a fully specified resource interface, canonicalize graph and path order, and use multiple dated snapshots as distinct environments. It should compare matched search and attempt budgets, test learned policies against fixed and adaptive baselines, and include channel activation delays without conflating confirmed and zero-confirmation modes. A controlled implementation-level channel harness should then validate the event semantics on authorized test resources. Live execution is a new experiment with new authority, not something a simulator can establish by renaming a field.

## 14. Conclusion

Connector Calculus contains useful local algebra and disciplined warnings, but those warnings do not repair missing executable guards or justify stronger empirical claims. The swarm's most important outcome is a separation: conservation survives; generalized transactional safety needs a narrower domain or a repair; gross cut demand must become a prefix net-flow constraint; reward invariance needs authenticated and consistently rounded resource accounts; and an oracle comparison needs matched resources. Testnet4 supplied real historical chain evidence, while also exposing the danger of treating miner timestamps as an application clock.

Liquidity on Trial supplies a resource semantics, not a solution to Lightning liquidity or evidence of an autonomous financial society. Its remaining premises are explicit obligations for future tests.

\pagebreak

# Appendix A. Evidence map and reproduction

The companion critique and Swarm Arena ledger provide finding identifiers, reviewer defenses, and source references. Machine-readable evidence is stored under audit/algebra/results.json, audit/incentives/evidence.json, audit/inference/, and audit/testnet4/results/. The original source is preserved at the audited commit; no bug has been silently patched into the baseline to make a test pass.

Use the existing project environment, set PYTHONDONTWRITEBYTECODE=1, and put the repository's src directory on PYTHONPATH. The review scripts are lightweight except for snapshot reconstruction and seeking retained block records. Do not delete or migrate the retained node datadir to reproduce the paper. The exported public header CSV suffices for checks that do not require source-record rereading.

The top-level audit README specifies exact commands. Outputs distinguish exact witnesses, matched synthetic episodes, conditional sensitivity calculations, and historical observations. The manifest binds manuscript sources, scripts, outputs, and PDFs. Hashes establish byte identity, not truth, authorship endorsement, or correctness of the modeled world.

# Appendix B. Notation crosswalk

| Original concept | Follow-up notation | Additional obligation |
|---|---|---|
| State S_t | Ledger X_n | Separate holdings, holds, registry, journal |
| Directional B_t | Ownership ell_(i,d) | Retain channel identity and direction |
| Capacity c_e | Resource total chi_i | Creation/removal are separate events |
| Lock L_t | Pending hold h_(i,d) | Aggregate gross concurrent requirements |
| Connector K_t | Registry U and journal J | Funding/lien evidence and lifecycle |
| Scalar path q | Hop amount vector y | Fee recursion and explicit msat units |
| Cut deficit | Prefix net crossing bound | Incoming replenishment and ordering |
| Bond/reward score | Authenticated weight w_u | Valid domain, coherent record, rounding |

This notation change is deliberate: it prevents the revised semantics from appearing to inherit protocol guarantees from unchanged letters. It remains compatible with ordinary graph-theoretic descriptions of endpoints and routes.

\pagebreak

# References

[R1] Dugan. Connector Calculus: Ghost-Node Rewrites, Bonded Liquidity, and Adversarial Agent Routing on the Lightning Network. Spiral reconstructed draft, August 2026. Local manuscript and repository baseline a0a3140. This follow-up audits that draft rather than claiming to restore the lost pre-incident paper.

[R2] Lightning Labs. Channel Fees. Builder's Guide. Accessed September 11, 2026. [Official fee documentation](https://docs.lightning.engineering/lightning-network-tools/lnd/channel-fees).

[R3] Jahr, F. BIP 94: Testnet 4. Bitcoin Improvement Proposals. Assigned May 27, 2024; accessed September 11, 2026. [Specification](https://github.com/bitcoin/bips/blob/master/bip-0094.mediawiki).

[R4] Lightning protocol contributors. BOLT 2: Peer Protocol for Channel Management, accept_channel and channel_ready. Accessed September 11, 2026. [Protocol specification](https://github.com/lightning/bolts/blob/master/02-peer-protocol.md).

[R5] Bitcoin Core contributors. v31.0, src/kernel/chainparams.cpp, testnet4 network parameters. Accessed September 11, 2026. [Versioned implementation](https://github.com/bitcoin/bitcoin/blob/v31.0/src/kernel/chainparams.cpp).

[R6] Spiral adversarial audit artifacts. Algebra, inference, incentives, resource ledger, public testnet4 header replay, and Swarm Arena cross-examination. September 11, 2026. Included with this paper, separately from the frozen original outputs.

[R7] Dugan, Patrick B., Daniel P. Pizarro, and Lihki J. Rubio. *Graph Re-write Using Ghost Nodes for Target Value Rebalancing*. U.S. Patent Application Publication US 2021/0004796 A1, published January 7, 2021; application 16/920,416, filed July 2, 2020; claims priority to provisional 62/869,730, filed July 2, 2019. Bibliographic fields taken from the USPTO Patent Public Search record; the specification concerns decentralized derivatives clearing by graph rewrite and is cited here for the ghost-node construction only.
