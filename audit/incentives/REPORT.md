# The Incentive Challenger: accounting before emergence

Audit date: 2026-09-11. This is an independent defensive cross-examination of the recovered paper, not a simulation of financial concealment. The original implementations are imported without modification. All executions are small, deterministic local fixtures or exact finite enumeration; none are autonomous LLM-policy episodes, Lightning executions, or testnet transactions.

## Reproduce and interpret

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\projects\Spiral\.venv\Scripts\python.exe' 'E:\Recovered_C_projects\Spiral_target\projects\Spiral\audit\incentives\run_audit.py' --source-root 'C:\projects\Spiral'
```

The script writes `evidence.json`, records the SHA-256 of itself and six original source/manuscript files, and asserts each claimed witness. Its finite trajectories are integration points in an exact expectation, not additional independent observations. The run passed all assertions. The evidence hash is `0a411df6d3aef04fa9e93bb397bb8d9ac63a35b95f5a6e58f7d69d15cd5b5569`. The filesystem resolves the supplied E: path into `C:\Recovered_C_projects\...` on this host; the script reports the resolved output path rather than claiming a separate disk copy. It also consumes and hashes the root auditor's public-header replay in `audit/testnet4/results`; reproduce that replay first when starting from a checkout without generated evidence.

## Verdict in brief

The identity-splitting theorem survives its actual fixed-weight assumptions. Its implementation does not establish a complete Sybil-resistant incentive mechanism. Score estimation, authenticated exposure, rounding, escrow, and external value are separate obligations. The paper already acknowledges several of these limitations; this audit turns selected ones into executable witnesses rather than alleging that the text never disclosed them.

| Question | Trial and outcome | Disposition |
|---|---|---|
| Does merely relabeling fixed capital change aggregate reward? | 1, 2, 4, 8, 16, 32 identical claims each retain aggregate reward 50,000 against an equal competitor. | Proposition 5 and A.6 survive. |
| Is each implemented resource weight a weight of an observed claim? | Claims `(100, .1)` and `(50, 1)` generate weight 100, though maximum claim product is 50. | Aggregation needs an authenticated canonical source record or joint-claim rule. |
| Do zero-weight sources always receive zero? | With reward pool 2, three equal positive sources and a last-sorted zero source, the zero source receives 2. | Integer allocator violates zero-weight exclusion; total-pool conservation still holds. |
| Is settlement bounded for all accepted inputs? | Availability 120/100 yields slash -1,249, release 26,249 from a posted 25,000, score 1.13. | Domain validation missing; not a counterexample within the intended valid domain. |
| Is the declared hive bond actually reserved? | A 20,000 connector consumes the endpoints' entire available wealth, declares a 4,000 bond, yet reports accounting error 0. | Bond is metadata, not an enforced reserve or lien. |
| Does service score identify incremental welfare? | Identical aggregate records score 1 in two worlds with net external value +9,000 and -1,000 toy units. | Impossible without additional causal/economic evidence. |
| Does observed demand automatically predict post-funding usefulness? | Exact 8-epoch forecasts lose placement advantage as demand forgets its past and funding delay increases. | Observation is not a substitute for a transition model and time horizon. |

## Bout 1: the theorem defender wins the narrow case

Original references: `paper/manuscript.md:246` (Proposition 5), `paper/manuscript.md:603` (A.6), `src/spiral_ln/bonding.py:70`.

The strongest defense is exact: if resource c's authenticated weight is held fixed, and rewards are divided only after the resource's total is fixed, splitting its claimant labels cannot increase the coalition total. Our six controls confirm this in the implementation, including integer sharing. This is a useful quotient-by-resource property, not an equilibrium theorem, not a proof of resource authentication, and not evidence that agents create net value.

The challenge concerns endogenously estimated weights. With one truly unchanged resource, independent Bernoulli service observations of true success probability 1/2, and an implementation that selects the maximum claimant score, expected selected score is `1 - 2^(-m)`. In the exact toy experiment, expected coalition payout rises from 33,333.5 at one observation to approximately 66,667 at 32 observations against a fixed reference source. No real service quality improved. This does not refute the fixed-weight theorem: adding observations changed its premise. It establishes a design obligation to fix the resource-level evaluation protocol independently of the number of claimant records. Neither the toy score distribution nor this observation model is asserted to represent production service assessment.

The independent maxima in `bonding.py:85` create a second, distinct issue. Two inconsistent records for one resource contribute their best coordinates separately. A charitable interpretation is that capital and score are separately authenticated attributes; then selecting them separately could be intentional. But the API supplies no such authentication or consistency invariant. The follow-up should require one canonical amount and one independently defined service estimate per resource, rather than assuming arbitrary submitted records already satisfy that contract.

The allocator's residue rule at `bonding.py:95` gives the entire remainder to the last sorted resource. It conserves the pool but need not preserve zero reward for zero weight. This is separate from identity-only invariance. Fixing that allocator would not establish Sybil resistance either.

## Bout 2: the bond exists in a record, not in a resource ledger

Original references: `paper/manuscript.md:266` (service contract), `paper/manuscript.md:285` (settlement example), `src/spiral_ln/bonding.py:53`, `src/spiral_ln/hive_lab.py:498`, `src/spiral_ln/hive_lab.py:508`, `src/spiral_ln/hive_lab.py:513`, `src/spiral_ln/hive_lab.py:633`.

The settlement-domain witness is intentionally invalid: available time exceeds promised time. Since the data class accepts it, negative downtime produces a negative slash. The exact output differs by one unit from ideal decimal arithmetic because binary floating-point values are passed through `ceil`. The scientific criticism is missing admissibility enforcement, not evidence that a valid contractual service can legally release more than its bond. An admissible domain requires nonnegative fields, `0 <= available <= promised`, `0 <= delivered <= attempted`, and a bounded attributable-event model before arithmetic begins. A valid full-service control releases exactly the posted bond and scores 1. An idle available service scores .4; that can be justified as payment for reserved availability, but cannot be called measured delivery value.

The hive trial is a white-box resource-accounting fixture, not an emergence claim. We establish a mature three-member relationship explicitly, let the original investment method choose an admissible absent cross-community edge, and give each funding endpoint exactly its 10,000 principal share. Investment debits 20,000, adds 20,000 channel capacity, and records a 4,000 bond. Both endpoints finish with zero liquid wealth. No bond reserve is recorded, yet the published wealth equation reports zero error because it excludes collateral obligations.

The strongest defense is that collateral might be a senior lien on the same funding capital instead of a disjoint deposit. That can be a coherent contract, but the implementation supplies neither a lien nor an exclusivity/priority rule. Under a separate-collateral contract, admissibility needs free resources at least principal plus bond. Under a shared-collateral contract, a priority/resolution model must prevent the same spendable balance from simultaneously satisfying incompatible obligations. The finding is an unimplemented binding layer, not a conclusion that the simulator has transferred real money or demonstrated fraud.

## Bout 3: delivery is not incremental economic value

Original references: `paper/manuscript.md:315` (wash-flow caution), `paper/manuscript.md:490` (net-service conditions), `paper/manuscript.md:547` (economics limitation), `src/spiral_ln/bonding.py:27` (record fields).

The manuscript already says volume is insufficient and a 120,000-unit connector may be uneconomic. The implemented service record cannot identify the missing distinction. Two worlds can have identical attempted volume, delivered volume, availability, and attributable failures, while the external incremental benefit of the service differs. Every deterministic scoring rule using only that record gives both worlds the same score. In the toy witness a common 1,000 real-resource cost yields net values +9,000 and -1,000. No larger sample of those same insufficient fields resolves the ambiguity.

A corrected economic statement must specify the welfare boundary. For a service operator, fees and subsidies are revenue and settlement charges are costs. For aggregate stakeholder welfare, internal rewards and fees are transfers, and slashing is not automatically a social loss. The appropriate external costs, capital opportunity cost, and causal incremental service benefit must be distinguished. Report payment success and return on resources separately.

Our illustrative sensitivity, not a market estimate, uses principal 120,000, separately reserved bond 24,000, a 30-day horizon, annual capital opportunity cost 12%, and lifecycle cost 2,000 units. Principal is returned, not expensed. The resource charge is 3,420.27 units. Break-even incremental surplus per additional service is 3,420.27 for one service, 342.03 for ten, or 34.20 for 100. At ten additional services worth 100 units each, improving delivery still loses 2,420.27 units under these assumptions. Different rates, costs, accounting boundaries, or service values can reverse the conclusion; the point is the missing inequality, not the arbitrary calibration.

## Bout 4: forecast value decays while the connector is unavailable

Original references: `paper/manuscript.md:462` and `paper/manuscript.md:466`, `src/spiral_ln/public_topology_eval.py:315` (static failure-aware endpoint choice), `src/spiral_ln/public_topology_eval.py:404` (immediate intervention).

An exact toy consists of two service regions, eight future service epochs, a known last-observed region, and a fixed intervention in that region. The latent region stays where it is with probability rho. A random equal-cost intervention serves either region with probability 1/2. Delay d makes the intervention unavailable for the first d epochs. These are abstract service tokens, not a Lightning liquidity dynamics model.

The expected targeted-minus-random service is exactly:

```text
A(rho, d, H) = (1/2) * sum[t=d+1..H] (2*rho - 1)^t.
```

We independently enumerate all 256 trajectories for each of 20 cells and recover that expression. At rho=.75 and H=8, advantage is .498047 service with immediate availability, .123047 after two epochs, and .029297 after four: most predictable value expires before deployment. At rho=.5 it is exactly zero at every delay. At rho=.25 it is negative (-.166016 with no delay). At rho=1 it is 4, 3, 2, and 0 as delays are 0, 2, 4, and 8. This is a model-contingent forecast result, not new inferential evidence about public demand.

Stationarity of the demand-generating law must not be confused with persistence of individual demand locations: this two-state Markov model has a time-homogeneous transition law even when rho=.25 makes the last location a bad predictor. Nor is stationarity necessary for predictability; a known changing schedule can be predictable. The original experiment only establishes the value of its static historical-demand heuristic in the named configurations. Prefer 'predictive persistence over the deployment horizon' over a universal 'only stationary demand' premise.

## Bout 5: the productivity assumption was honestly labeled

Original references: `paper/hive_lab.md:61`, `paper/hive_lab.md:63`, `paper/hive_lab.md:89`, `src/spiral_ln/hive_lab.py:309`.

The strongest defense is present in the original supplement: coordination income is explicitly assumed, not discovered. Our paired, fixed-coalition one-round test returns identical external income 22,975 with bonus zero at sizes 1, 3, and 5. At bonus .08, sizes 3 and 5 earn 23,781 and 25,662 because the model applies multipliers 1.16 and 1.32 to their members. The critique should not repackage this disclosed assumption as a hidden flaw. Its proper use is a sensitivity parameter that must be independently estimated before claims about real autonomous economic organization.

## Bout 6: historical testnet ordering constrains a hypothetical contract

The root auditor extracted 512 public headers from the retained D: testnet4 block files, heights 147473 through 147984. This auditor independently verifies the supplied CSV hash, the 511 parent links, consecutive heights, and the final anchor hash before consuming the replay scenarios. That is not full Bitcoin consensus validation, not an observed funding transaction, and not a live Lightning channel. The original node's RPC was unavailable during inspection. Miner timestamps are never used as arrival times or a revenue clock.

We apply an explicitly hypothetical operator accounting rule to the root's ordinal depth-gate scenarios: receipt 1,000 units per delivered service and fixed cost 2,000 units. In the three-block service window with assumed inclusion lag one block, immediate service delivers three and nets +1,000; a three-depth gate delivers one and nets -1,000; a six-depth gate delivers none and nets -2,000. No market price or actual testnet revenue is measured. This shows that adding a specified funding horizon can reverse a simulated operator objective even when the principal and demand schedule are unchanged.

The contribution of D: data is a hash-bound historical ordering scaffold and a check against confusing miner timestamps with elapsed time. The economic result comes from imposed demand, cost, and depth rules. Repeating the same ordinal rule over many header windows is not empirical replication; it must not yield a statistical confidence interval or a claim about real settlement profitability.

## Recommended claims for the follow-up

1. Identity invariance is conditional on canonical resource-time exposure and an identity-independent score-estimation protocol.
2. A connector becomes economically admissible only after a reserve or explicit lien has been checked, not when a positive bond number appears in a data class.
3. Service accounting is not a causal estimator of external value; reward transfers and social surplus are distinct objects.
4. Placement value depends on forecast quality over the post-settlement horizon, not merely a statistically impressive pre-deployment failure count.
5. Distinguish the swarm of LLM researchers arguing about the model from the scripted actors inside the simulated economy. Neither is evidence of an emergent real-money society.

No original source was changed. These are counterexample witnesses and strengthened obligations; they are not a production financial mechanism or a deployment recommendation.
