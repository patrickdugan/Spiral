# Changes for the technical discussion draft

Revision date: **21 October 2026**.

Reviewed baseline: `6a9df365f727cf2471ae52e00b36e8816d0081bc`, the supplied
45-page PDF. This record describes changes to the current [LaTeX source](tex/main.tex)
and reference model relative to that baseline. The revised [PDF](tex/main.pdf)
is **41 pages**, built with XeLaTeX and visually inspected. It has no overfull
boxes or unresolved references. The review [verification record](../audit/peer_review/verification.json)
binds the source, model outputs and compiled artifact with hashes.

The intended publication is a **technical discussion draft for Bitcoin peer
review**. Its central result is an accounting framework for capital committed
under different settlement and recovery rules, supported by conditional
simulation results. Claims about optimal routing, general coalition profit,
real proof performance, and deployed-protocol economics have been reduced to
the scope the evidence supports. The complete evidence index and reproduction
commands are in [audit/peer_review](../audit/peer_review/README.md).

## 1. Conservation no longer implies a routing-performance ceiling

The baseline correctly derived a prefix-cut conservation identity, then used
it to argue that routing information could improve only the attempt budget.
That consequence did not follow. A successful route changes the directional
balances available to later payments.

The revised proposition states that every routing policy obeys the same form
of accounting constraint along its own settled history. It does not order the
delivery achieved by different policies. A retained four-node witness starts
from identical balances and offers the same two payments. Both possible first
routes succeed; one leaves the second payment routable and the other leaves
no feasible route for it. All checked cut identities still hold. This
establishes a logical failure of the former inference without estimating its
frequency on Lightning. See the [mathematical review](../audit/peer_review/math_review.md)
and [machine-readable witnesses](../audit/peer_review/math_witnesses.json).

The abstract, simulator interpretation, coalition discussion, and conclusion
now treat success gains as comparisons of the tested policies and workloads.
The six-point placement estimate supplies no upper bound on all placement
policies or on coalition earnings.

## 2. The archived comparator labels and uncertainty are corrected

The baseline's **1.11-point** oracle effect was oracle over the online
heuristic. Oracle over retries is **1.4580 points**, with a 95% interval of
**[0.8446, 2.0715]**. The revised table includes both contrasts and uses their
comparators consistently. The online heuristic over retries remains
**0.3481 points [0.1477, 0.5485]**. The ordinary retry and online arms attempt
up to three routes, while the oracle inspects hidden feasibility across up to
eight candidates. This resource difference is explicit.

Stationary failure-aware placement remains **6.1310 points [4.9090, 7.3530]**.
After a demand shift the combined estimate is **0.4383 points
[-0.2119, 1.0886]**. The latter includes zero and exceeds the declared
+/-1-point equivalence band at its upper end. The revision removes claims of
exact disappearance or established equivalence for the combined estimate.

The independent reanalysis verifies **4,536 archived rows**, **3,348 sealed
rows**, and **28 sealed topology clusters** across the original, replication,
and precision campaigns. Seven checked archived contrasts reproduce within
`1e-12`; oracle over retries is an additional paired-row calculation. The
precision extension and the new review are identified as adaptive or post hoc
work. All sampled topologies derive from one July 16, 2023 snapshot with
synthetic state. Process hash-order sensitivity prevents claiming exact
regeneration of the historical simulator campaigns. See the
[empirical review](../audit/peer_review/empirical_review.md) and
[retained checker output](../audit/peer_review/empirical_check.json).

## 3. Fronting uses an outstanding-stock identity

The baseline compared cumulative fronting with currently available capital.
A reserve can finance multiple payments after prior advances recover. The
corrected server proposition uses cumulative advances `F`, cumulative
recoveries `C`, and outstanding fronting `W = F - C`. A new advance is admitted
only if it fits within the remaining fronting reserve. Holder-facing issuance
stock is recorded separately.

The exact capital-duration comparison also retains its delivered-volume
factor:

\[
\frac{D_C}{D_V}
=\frac{L_C}{L_V}\frac{\operatorname{Vol}_V}{\operatorname{Vol}_C}.
\]

Here `L` is integrated occupied capital. Dropping the volume factor requires
equal delivery. Fronting locks are integrated from each advance until its
recovery or the observation horizon; payment volume multiplied by an assumed
average lock is an additional approximation. The revision states that idle
reserves, terminal obligations, and gateway funding must be priced for a
deployment comparison. See the [mathematical review](../audit/peer_review/math_review.md).

## 4. Forecast and lock-integration errors are fixed

The oracle forecast used end-of-round net balances, while execution credited
receipts before considering spends and rejected an unaffordable spend in
full. Sizing could therefore miss both an intermediate receipt peak and a
balance preserved by a rejected spend. [server.ts](../model/server.ts) now uses
the same event order and spend rule for forecasts and replay. Lock integration
also stops at recovery within an `advance` interval.

The [before/after table record](../audit/peer_review/math_grid_comparison.json)
preserves all generated row changes and their recorded hashes. Selected
consequences are:

| Quantity | Baseline | Corrected |
|---|---:|---:|
| Zero-drift, eight-lifetime oracle C/V, next-round counterfactual | 1.46 | 1.48 |
| Draining-drift oracle C/V, next-round counterfactual | 2.52 | 2.59 |
| Zero-drift oracle C/H20, baseline seed | 1.4402 | 1.4311 |
| Zero-drift oracle C/H200, baseline seed | 1.5019 | 1.4909 |
| Few-steady trailing channel failures, 32,256 events | 12,703 | 8 |
| Few-steady oracle channel failures | 8 | 4 |
| Few-steady server sizing failures | 8,229 | 0 |

The old few-steady refusal interpretation was caused by the sizing error.
The corrected few-steady row does not support it. The trailing server forecast
still evaluates an unconstrained holder flow after the fact: its forecast
failures do not feed back into holder delivery or later locks. Such cells are
identified as sizing diagnostics. A constrained end-to-end replay remains
future work.

The nine server tests include all **1,024 five-round demand paths** over four
event types, one-agent channel/hyperedge equivalence, reserve reuse, and
coarse/fine recovery-integral agreement. These are finite implementation
checks. They do not prove distributed-protocol correctness.

## 5. The pooling argument now identifies its stochastic scope

The `pi/2` benchmark is stated as a ratio of expectations for independent
zero-start reflected Brownian motions, together with its large-population
limit. It is not a bound on every realized finite spend-rejection path. Signed
imbalance scaling separately requires sufficient initial balances to permit
negative excursions.

A new exploratory [sensitivity campaign](../audit/peer_review/model_sensitivity.json)
uses 24 seeds in four cells, giving **96 seed/cell combinations and 192 Ark
recovery runs**. It uses eight lifetimes, oracle forecasts with a 25% margin,
and matched offered demand and service within each combination. All included
server sizing diagnostics pass. At zero drift, the mean `C/H20` is
**1.467 [1.450, 1.483]** and `C/H200` is **1.541 [1.522, 1.561]**. The group of
twenty captures a mean **86.3%** of the full pool's excess gain at zero drift,
compared with **66.5%** under draining drift. The accumulating cell has a mean
full-pool gain of about **1.009**.

The zero-drift mean `C/V` is **0.871 [0.865, 0.878]** with expiry recovery and
**1.531 [1.511, 1.551]** in the next-round counterfactual. Every sampled expiry
case has `C/V < 1` under this metric. The single-lifetime model, unconstrained
fronting reserve, omitted idle treasury, and excluded fees and churn prevent
an implementation ranking. The intervals describe Monte Carlo precision
conditional on this generator and model; the campaign was designed after
the error was found. The full four-cell table appears in the
[review index](../audit/peer_review/README.md) and generated manuscript table.

## 6. Reward claims are restricted to what the construction establishes

One object can admit several valid authority witnesses. If each witness keys
a different nullifier, a repeated claim can evade a nullifier uniqueness
check. The relation now explicitly requires one canonical single-signer
credential per object. Distinct identifiers must also represent disjoint
backing: a funding output and the virtual claims it backs cannot enter as
independent economic exposure.

The [registry model](../model/registry.ts) now rejects nonpositive or unsafe
claim weights, invalid settled values and reward pools, aggregate weight
overflow, and every previously used object identifier. Failed transitions
preserve their source; snapshots retain identifier history; copies prevent
external object mutation; integer allocation avoids a floating point rounding
error at the safe-integer boundary. The twelve registry tests cover these
cases alongside epoch and successor behavior.

The verifier remains simulated. Canonical authority and disjoint backing are
admission assumptions, with no implemented threshold-credential protocol or
overlap detector. The fixed-pool allocation result therefore bounds only that
pool under its stated eligibility assumptions.

The service relation now requires a complete admitted-request ledger with
unique identifiers, deadlines, outcomes, and a public denominator. Signed
submitted outcomes alone cannot establish that denominator. Refused requests
and independently controlled counterparties require further observation rules.
Neither this admission protocol nor a real service proof circuit is
implemented. Fixture-based cycle detection supplies no general claim of
collusion resistance. See the [mathematical review](../audit/peer_review/math_review.md)
and the revised manuscript's proof, observer, and limitation sections.

## 7. Protocol sources and cost calculations have explicit boundaries

**Ark recovery.** [Second's Lightning documentation](https://second.tech/docs/learn/payments-lightning)
states that a successful outgoing HTLC is retained off chain and the server
sweeps the round at expiry. The next-round branch is a counterfactual until a
concrete recovery path is demonstrated. The same source distinguishes
432-block receive-pool lifetimes, a minimum 144 blocks remaining when a
receive is offered, and refresh into 4032-block standard rounds. The present
grid's one-lifetime simplification is now explicit.

**Proposal status and contention.** [BIP 448](https://github.com/bitcoin/bips/blob/master/bip-0448.md)
and the [LayerTree draft](https://layertree.tech/paper/main.pdf) remain proposal
inputs. The BIP 446 description includes the current input index. LayerTree
delay formulas are conditional on minimum service, bounded overtaking, and
prompt valid resubmission. The model's values 1, 25, and 64 are illustrative
service rates. Mempool ancestor, descendant, or cluster admission ceilings
do not guarantee those rates. Proposal semantics must be tested on nodes
that enforce them.

**LayerTree units and economics.** Exact exits at depth 16 are separated by
tier: FULL 1,020 model / 1,030 serialized vB; MID 1,355 / 1,398; MIN 1,473 /
1,518; CCV 908 / 918. The revised paper no longer applies FULL's 1,020-vB
value to every tier. Deployment fee-management packages remain unmeasured.

Corrected baseline-seed channel stock is **105,912.5 sat per member** under
the oracle and **38,654.6875 sat** under the trailing rule. With the assumed
3,000-sat credit leaf and 2% annual carry, the recalculated oracle break-even
receipt thresholds are approximately **4,518, 22,591, and 112,956 sat per
round** at fee inputs of 2, 10, and 50 sat/vB. The middle trailing threshold is
about **65,207 sat per round**. The 2% rate is a scenario assumption; 0.25% is
a sensitivity that multiplies thresholds by eight. Neither is a measured
market floor. The linear calculation has not established equivalent service
between a receive-only credit leaf and a channel funded for a net-balance
process. See [layertree.ts](../model/layertree.ts) and its
[regression checks](../model/layertree.test.ts).

**Proof costs.** Application-specific constraint counts and prover timings
have been removed because neither proposed relation has been compiled or
benchmarked. The [BitVM3 figures](https://bitvm.org/bitvm3.pdf) are identified
with the cited Yao/Groth16 backend and its setup and challenger assumptions.
They are not universal lower bounds for every verifier design. Circuit setup,
transaction-signing setup, and challenge execution require their own evidence.

**Designed topologies.** The unrelated appendix is preserved as a
[separate source note](designed_topology_note.tex), excluded from the revised
paper. No central result depends on the cited Barnette preprint, and its Lean
formalization was not compiled in this review.

## 8. Verification and remaining implementation work

The review completed **30/30 named TypeScript tests**, with no failures or
skips: escrow/warden 4, Hamiltonian fixtures 1, LayerTree 2, ledger 2, registry
12, and server 9. On Node v24.19.0 the shell-expanded `--test model/*.test.ts`
command reports six file-level passes; direct execution of all six files
exposes the thirty named cases. The standard-library finite-witness and
archived-data checks completed separately. The full Python suite remains
unverified here because `pytest` and `networkx` are unavailable. See the
[exact commands and status](../audit/peer_review/README.md).

The historical testnet4 check validates **512 recorded header hashes and
encoded PoW targets**, **511 internal parent links**, and the retained anchor
at height **147984**. Its **64 nonpositive adjacent timestamp differences**
include a minimum of **-6004 seconds**. Header timestamps cannot substitute
for node-observed arrival times. No actual funding transaction, operational
payment, recovery latency, or current-chain observation was added. See the
[empirical check](../audit/peer_review/empirical_check.json).

The next implementation priority is an owned regtest trace of a complete Ark
payment and recovery cycle, followed by budget calibration at equal service.
It must distinguish recovery of original backing from reserve reassignment,
include receive-pool age and refresh, and account for idle funding and terminal
obligations. After local reconciliation, the
[testnet4 protocol](../audit/peer_review/testnet4_plan.md) proposes four
controlled Lightning peers, at most 200 payments, a 48-hour stopping rule, and
a fixed funding/fee cap. These are proposed experimental bounds. No execution
or completion time is claimed.

The technical questions for reviewers are listed in the
[review index](../audit/peer_review/README.md). The source changes and rebuilt PDF are ready for technical discussion with
the stated model and implementation limits. This review has not merged the
changes into the repository's main branch or sent the paper to reviewers.
