# Algebra under cross-examination

Date: 2026-09-11. Role: algebra challenger sub-agent. Target: the unmodified
`C:/projects/Spiral` source at the parent-specified `a0a3140` baseline.
This audit uses only offline, small, exact witnesses. It does not operate
testnet4, validate HTLC behavior, contact peers, or make transactions.

## Verdict

The elementary conservation identities survive. Two thousand valid simple-path
rewrites preserve channel bounds and capacity. Fixed-exposure, fixed-weight
identity splitting also survives a competing-capital control. The useful
critique is therefore not that arithmetic conservation is wrong. It is that
conservation does not establish execution safety, horizon throughput, funded
compilation, or protocol-faithful feasibility.

One implementation claim is directly falsified on an accepted input domain:
rejected closed walks can partially mutate state. A related appendix
equivalence needs a route-domain and execution-order restriction. A third
mathematical premise conflates horizon demand and instantaneous inventory if
"demand across the cut" means gross outward demand. Compilation safety is a
specified predicate rather than an implemented guarantee. Fee accumulation is
an already-disclosed omission, not a newly discovered theorem error.

| Challenge | Exact observation | Disposition |
| --- | --- | --- |
| A1: closed-walk atomicity | 161 of 312 prevalidated adversarial closed walks reject after mutating balances | Implementation counterexample; restrict domain or implement rollback |
| A2: net-vector feasibility | Net-zero A-B-A rewrite is in the final-state polytope, but reverse balance is initially zero | Net admissibility is not simultaneous gross resource availability |
| A3: cut stock versus flow | 50 outward units support 200 outward deliveries when reverse flows replenish inventory | Replace gross horizon comparison with net, prefix-sensitive inventory accounting |
| A4: compilation guards | Two distinct connector IDs naming one exposure add 200 units; zero bond and negative expiry also accepted | Abstract safety predicate not enforced by this implementation |
| A5: fee boundary | A nominal 1,000-sat payment fits both edges; one 1-sat forwarder fee makes the upstream edge insufficient | Explicit model limitation with a discontinuous reachability consequence |

The 161/312 ratio is deliberately adversarial enumeration, not an estimated
failure rate for Lightning, random traffic, or the earlier public-topology
campaigns. Those campaigns enumerate simple paths; A1 does not retroactively
invalidate their CSV rows.

## A1. A rejected accepted-domain route can mutate state

Create A-B-C-A with capacity 100 and forward balance 100 on each stored edge.
The closed connector route is A-B-C-A-B-C-A and its amount is 60. The
`Connector` constructor accepts it because it closes. The route precheck sees
100 available on every occurrence, so it returns true. The first three edge
transfers succeed, leaving forward balances 40, 40, 40. The fourth transfer
raises `ValueError("insufficient directional liquidity")`. All channel
invariants still pass, despite the failed route having changed the state.

Evidence: `src/spiral_ln/algebra.py:108` prechecks occurrences independently;
`:119` mutates in place without rollback; `:159` validates closedness without
excluding repeated edges. `paper/manuscript.md:127` calls the operation atomic;
`:581` says a rejected route leaves the entire state unchanged. The
single-edge state-bounds proof at `:236` remains true. Its extrapolation to
arbitrary prevalidated paths requires stronger premises.

The exhaustive grid uses triangle capacities 1 through 12, integer amounts 1
through the corresponding capacity, and one through four repeated cycles:
312 cases. All prevalidate. Exactly 151 complete and 161 reject after partial
mutation. The success condition is repetitions times amount at most capacity.

Champion case, reconstructed by this auditor: the intended routes are simple
paths or simple cycles, and NetworkX's public-routing path enumeration produces
simple paths. The bug therefore lies outside the tested public-routing domain.

Challenger response: that is a valid defense of those results, but not of the
unrestricted API or the appendix's "closed vertex sequence" at `:595`. State
the domain explicitly and enforce it, or make failure transactional. Counting
channel conservation checks cannot detect this bug: conservation survives a
partial route.

### Separate corrected reference

`transactional_reference.py` does not edit the original implementation.
`apply_sequential_transaction` applies all edge rewrites to a clone and replaces
the live state only after success. `apply_prefunded_transaction` additionally
counts gross repeated uses separately for each direction before that operation.
Both produce 151 accepted cases and 161 unchanged rejections on the same grid,
with zero partial rejections. Thirteen pytest cases pass, including both grids,
missing-edge rollback, invalid amounts, and an execution-semantics distinction.

The distinction matters: sequential A-B-A can use an earlier transfer to fund
the reverse leg; simultaneously prefunded A-B-A cannot when reverse balance
starts at zero. Clone-and-commit is a local test semantics, not proof of
distributed Lightning atomicity, peer agreement, or concurrency isolation.

## A2. Final-state feasibility hides gross and intermediate requirements

Start with one channel, capacity 100, outward balance 100, reverse balance 0.
For A-B-A with q=60, the signed net increment is zero. Its final vector is
therefore inside the unchanged channel polytope. Yet the original precheck
rejects because the reverse leg initially has no available balance.

`paper/manuscript.md:575` says feasibility is exactly final-state polytope
membership after reserves and locks. That equivalence is defensible for a
simple, non-repeated channel rewrite with a fully specified amount vector;
it is not an equivalence for arbitrary closed walks under the implementation's
prefunding interpretation. This is related to A1, not an independent large
population finding.

For sequential rewrites, every execution prefix needs to remain admissible,
and rejection must restore the starting state. For simultaneous reservation,
each oriented channel needs enough resources for the sum of all its reserved
occurrences. Neither condition is captured by the signed net vector alone.
Slots, time, channel identity and fee-adjusted amounts are further resources,
outside this small reference.

Champion case: a "path" conventionally excludes repeated vertices.
Challenger response: keep that convention for the path lemma and separately
define the permitted cycle/walk domain. Do not transfer an endpoint-polytope
criterion to every accepted closed connector sequence without a reservation
or ordering argument.

## A3. Inventory is not horizon throughput

`paper/manuscript.md:202` declares a directional deficit when forecast
cut demand over a horizon exceeds present directed cut availability. For a
single channel of capacity 100 with 50 available A-to-B, execute five pairs
of A-to-B 40 followed by B-to-A 40. All ten demands succeed. Outward delivered
volume is 200, four times the original outward inventory. No connector or
new capital is needed.

Now retain exactly those demanded totals but place all five outward demands
first, then all five inward demands. Seven demands fail; only 40 outward
and 80 inward are delivered. Horizon net demand is zero in both schedules,
so final net demand alone is insufficient too.

For this fee-free, no-lock, fixed-capital model, let F_out and F_in denote
*settled* cumulative amounts, not desired or merely attempted demand. Then:

```text
Q_A(t) = Q_A(0) - F_out(0,t) + F_in(0,t).
0 <= Q_A(t) <= C_cut  for every execution prefix t.
```

Under an all-demands-delivered feasibility hypothesis, the corresponding
demand prefixes must satisfy those inequalities. This is necessary but not
sufficient for a multihop payment network: internal bottlenecks and per-edge
constraints can still fail. For one cut edge with no other constraints it
captures the relevant inventory condition. Fees, locks, and capacity changes
would require additional terms.

Champion case: perhaps D_A was intended to mean net demand after replenishment,
or a conservative gross-demand stress bound assuming no reverse flow.
Challenger response: either definition would repair the mismatch, but neither
is explicit. Label a no-replenishment gross-demand rule as a conservative
scenario; use signed prefix demand for a dynamic inventory theorem. Do not
equate additional traffic with a proportional need for fresh channel capital.

## A4. Funded compilation is a specification, not a checked theorem

`paper/manuscript.md:177` lists seven compilation predicates, including unique
exposure, consent, funding/fees, expiry, bond, and caps. Appendix A.5 at `:599`
defines Compile(g,S) to fail if any predicate fails. If taken as a definition,
that implication is true by construction. It is not evidence that the listed
predicates can be verified or are enforced by the current code.

`GhostPlan.compile` at `src/spiral_ln/algebra.py:184` takes no state, exposure
registry, budget, consent, or bond-posting evidence. It creates a capital label
from the ghost ID and an integer bond amount. `apply_connector` at `:206`
adds a channel and discards the connector's bond, expiry and capital metadata.
`NetworkState` at `:74` holds channels only.

The test compiles two plans with the same generated capital identifier at
different endpoints and obtains 200 modeled units. To avoid relying on duplicate
plan identifiers, a second test uses *distinct* connector IDs but the same
capital identifier and again obtains 200. A direct connector with zero bond
and no capital identifier is accepted. A lease with negative expiry is
accepted. There is no clock-based lease-expiry transition here to test; the
audit does not pretend to have advanced a missing clock.

Champion case: external adapters or a future deployment verify those fields;
the graph simulator is intentionally abstract. Challenger response: describe
those external checks as assumptions. A synthetic capital label is not a
scarcity oracle, and materializing a channel object is not compiling a funded
service. The narrow reward theorem can be retained conditional on an authentic
exposure-to-claim mapping and invariant service weights.

## A5. Fee-aware feasibility: boundary, not novelty

`paper/manuscript.md:117`, `:127`, `:240`, and `:531` explicitly disclose uniform
amounts and omission of backward fee accumulation. The audit respects that.
Take A-B-C, amount 1,000 sat, and 1,000 sat available on both forward edges.
The original precheck accepts. A one-satoshi forwarding fee charged by B
requires 1,001 sat on A-B, making that same route infeasible. This demonstrates
that "small" omitted fees can change a discrete success indicator at a tight
boundary, not that the original fee-free conservation proof is invalid.

The challenger does not estimate how often such boundaries occur and does not
claim complete BOLT fee, HTLC, or settlement semantics. Root's follow-up should
use hop-specific amounts and explicit sources/sinks for fee income. Preserve
the original closed-cycle statement only under its stated zero-fee/uniform-flow
premises.

## Surviving controls and interpretation

Two thousand seeded simple-path payments on integer-capacity chains produce
zero conservation/bounds violations. This is a check of the implementation
within its valid domain, not formal verification. Moreover, channel conservation
is structural because reverse balance is defined as capacity minus forward
balance; that invariant cannot diagnose missing fee attribution or partial
settlement.

A coalition with 100,000 capital units and service score 0.9 competes with
200,000 capital units at score 0.5 for a 100,003-unit pool. Splitting the first
coalition across 1, 2, 4, 8, 16, 32, or 64 identities always yields 47,369
units; total allocation remains 100,003. This strengthens the old
single-capital control while leaving its substantive premise explicit: exposure
identity and score are held fixed. It does not test whether labels are backed
by unique economic resources or whether service measurement is manipulable.

## Actual work chronology and reproduction

This is a factual audit log, not a fictional debate transcript:

1. Read the original algebra, bonding functions, existing tests, and cited
   manuscript claims without modifying them.
2. Sent the parent the repeated-cycle atomicity hypothesis and then the
   cut-stock/replenishment challenge, explicitly identifying fee omission as
   already acknowledged.
3. Authored and ran the initial offline script: all five expected witnesses
   and 2,000 champion controls were observed; runtime was about 0.27 seconds.
4. Parent cross-examination requested a separate corrected transactional
   reference and warned against confusing sequential settlement with
   simultaneous HTLC reservation. Implemented both restricted interpretations.
5. Reran the audit and 13 pytest cases successfully. Expanded the duplicate
   exposure witness to include distinct connector IDs. The final JSON embeds
   execution timestamps, source hashes, reference hash and script hash.

PowerShell reproduction (no network or source modification):

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:\projects\Spiral\.venv\Scripts\python.exe' 'E:\Recovered_C_projects\Spiral_target\projects\Spiral\audit\algebra\challenge.py'
& 'C:\projects\Spiral\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider 'E:\Recovered_C_projects\Spiral_target\projects\Spiral\audit\algebra\test_transactional.py'
```

The script's `--source-root` and `--output` options permit relocation. Tests use
the designated C source explicitly. Exact audit-source SHA-256 values:

```text
paper/manuscript.md
56f2109b793be5a06eb405bd73810573be64402682281e3e4a1bd49c406cd049
src/spiral_ln/algebra.py
f4542d5fdcbf023cbb2e8b527dd4ba00ece7e586c7b18f3f16f83ab7edfa8b6e
src/spiral_ln/bonding.py
692b5b7eae2f96346593971577348c7b75154f3e55fc402209dd45062ae2cf67
```

No original files were changed. The numerical evidence lives in
`audit/algebra/results.json`; code lives alongside it. The separate reference
is an audit witness and proposed semantic repair, not a production patch.

## Independent cross-lane adjudication

After the initial report, the parent requested a review of the incentive
challenger and the new resource reference, plus independent verification of
the testnet4 replay. These are additional actions, not part of the initial
offline-only original-algebra experiment above. The added script is
`cross_examination.py`, with hashed evidence in `cross_examination.json`.
It reads public historical headers on D: but no wallet or network interface.

### Incentive lane

Independently reproduced the allocator's zero-weight witness: three positive
unit weights followed lexically by one zero weight, with pool 2, allocate
0, 0, 0, 2. This is an actual zero-weight-exclusion bug on admissible input,
although total-pool conservation and fixed-weight identity invariance survive.

Independently reproduced the inconsistent-coordinate witness: claim records
(capital 100, score .1) and (capital 50, score 1) for one resource are combined
into weight 100, exceeding either observed joint weight. The resulting
coalition allocation is 60 from pool 120 against reference weight 100; the
maximum *joint-record* weight rule would allocate 40. This adjudication agrees
with the incentive report's charitable qualification: separately authenticated
capital and score could justify combining them, but that canonical contract
must be stated and verified. The arithmetic alone does not demonstrate that
every use of independent maxima is economically invalid.

The score-selection thought experiment changes a resource's estimated weight
as observations multiply. It therefore challenges the measurement procedure,
not the theorem conditional on fixed weights. Likewise, the hive bond fixture
shows neither separately escrowed collateral nor an explicit lien/priority
model. It is a missing binding layer, not proof of actual double spending or
evidence that collateral must always be disjoint from funding capital.

### New resource reference

On the reviewed root `audit/resource_model.py` version, 5,000 seeded state
machine steps yielded 1,577 accepted prepares, 1,847 unchanged rejected
prepares, 1,096 settlements and 480 aborts, with no balance, reserve, or
gross-held-sum violation. One accepted operation remained pending at the end.
This supports the intended typed-state invariant.

However, the challenger found and executed an input-validation counterexample
in the new reference itself. Direction `1.0` passed membership testing against
`(-1, 1)`. On settlement the balance became float-valued, and validation raised
after balance mutation, pending deletion, and identifier consumption. Reported
this to the parent for correction; the parent-owned source was not edited by
this sub-agent. The JSON source hash identifies the reviewed version. A later
replay of the check can show rejection at prepare after the parent repairs the
guard. This is a concrete instance of the swarm challenging its own proposed
repair, not merely attacking the original paper.

### D: testnet4 public-header check

Independently recomputed 512 double-SHA256 identities and encoded proof-of-work
target comparisons; all pass. Verified 511 internal parent links and ascending
ordinal heights. Read three public headers directly from
`D:/BitcoinTestnet/testnet4/blocks/blk00089.dat`, checking testnet4 framing,
record length and exact header bytes at these offsets:

| Height | Byte offset | Result |
| --- | --- | --- |
| 147473 | 82782255 | Matches replay header |
| 147728 | 84976307 | Matches replay header |
| 147984 | 116170255 | Matches replay header |

Core disk XOR obfuscation was decoded locally; its key was not printed. It is
not wallet encryption. The three-disk-header spotcheck is intentionally
separate from the all-512 CSV-header identity checks. It does not claim full
block, merkle, difficulty-retarget, consensus, live-tip, funding-transaction,
or LN validation.

There are 64 nonpositive differences among 511 consecutive miner timestamp
differences. These fields are not observed arrivals and cannot be used as
funding-latency measurements. The synthetic depth-gate outcomes depend on
assumed ordinal inclusion delays and demand, not on header-specific random
conditions. The real headers anchor historical block ordering; they do not
turn an arithmetic delay scenario into a measured Lightning experiment.

### Adversarial review received from the inference lane

The inference challenger subsequently read the report, Appendix A.1-A.4, the
original implementation and the transactional reference. The reviewer upheld
A1 on the accepted API domain while defending the simple-path campaign;
required A2 to remain a closed-walk/reservation extension critique rather than
a refutation of simple fee-free path feasibility; and upheld A3 with its
gross-versus-net and necessary-not-sufficient qualifications. These
qualifications are retained above. No disagreement was resolved by counting
agent votes: the exact witnesses and domain distinctions determine the result.
