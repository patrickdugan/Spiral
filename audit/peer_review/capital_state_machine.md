# Capital accounting state machine v1

Status: implemented reference accounting plus a source-pinned, 34-event
reconstruction of the executed Bark regtest lifecycle. Economic invariants and
replay pass; precise transition clocks and matched-service comparisons remain open. See [execution report](capital_regtest_report.md)
and [source mapping](capital_adapter.md). Existing `ArkServer` forecasts and
`SettlementLedger` are preserved.

## Boundary, units, provenance

`CapitalAccountingMachine` represents `S = (A,K,H,B,J)`. `A` is the operator's
economic assets; `K` is holder claims against those assets; `H` contains channel
shares, directional capacity and payment operations; `B` contains gross fronting
and the dedicated pool's source/use ledger; `J` is the canonical observation
view and offered-demand ledger. `journal()` returns a detached copy of the
append-only accepted event log, including branch changes and orphan evidence.

Amounts are nonnegative **integer millisatoshis**, bounded by
`Number.MAX_SAFE_INTEGER` for both individual values and aggregates. `sats(n)`
converts integer sats exactly to msats. Fractional-sat Lightning fees are retained.
Core BTC tokens are converted with decimal-string/BigInt arithmetic; scientific
notation and fractions smaller than a sat are rejected. Onchain observers must
enforce whole-satoshi output amounts. No floating-point money arithmetic or
silent rounding is allowed. BigInt integrals are serialized as decimal strings.

Every lot has the requested ID, amount, owner, location, backing reference,
disposition, creation event and last event. It also carries parent IDs, original
value, maturity and pool membership. A retired parent remains with zero current
value, preserving its original value and journal ancestry. An outpoint registry
prevents funding the same underlying value twice even after channel conversion or
retirement. `SPLIT_MERGE` conserves value and only reshapes free slices of the
same backing. `ONCHAIN_TRANSACTION` consumes whole outpoints, creates indexed
outputs, preserves ancestry, and accounts for miner fees separately from change.

Claims have unique IDs, holder, amount, explicit per-lot allocations, expiry,
state, parent and last event. Splitting allocations is allowed; overallocating a
lot is not. Retained change transfers allocation from the forfeited parent to
the new active claim; it does not add another allocation over the same value.
Forfeited `amount` preserves historical input value while its residual allocations
represent recovery encumbrances. Distinct disjoint allocations may share one root;
unbounded contingent overclaims remain unsupported. Mature initial funding is admitted from a trusted
observer snapshot. Funding a claim is not an external inflow by itself.

A channel's funding reference is metadata, **not another asset**. Its local
economic share consists of the lots located in that channel. Local plus remote
shares equal capacity. `spendable`/`receivable` are service capacity observations,
separate from ownership: a reserve floor can make spendable less than owned.
In-flight amounts remain in the local lots until settlement and are not added
again to economic assets. Live adapters must obtain quiescent initial shares or
reconstruct earlier commitments; they must not guess initial in-flight ownership.

## Event schema and trust boundary

[JSON Schema](capital/capital-event.schema.json) is generated from
`model/capital-schema.ts`; `apply()` uses the same shape definitions. Events carry
the requested envelope fields, `unit: "msat"`, and a discriminated `data` payload.
Every referenced lot/claim must appear in the envelope; its last modifying event
must be a causal parent. Payment and channel reads are similarly linked.
Parent IDs must already be canonical. IDs are unique; an identical duplicate is
a no-op, and a conflicting duplicate is rejected.

`block_height` is the height at observation, not an implicit advance instruction.
`monotonic_timestamp` is elapsed integer seconds from the declared measurement
origin, not wall-clock UTC. Null makes the seconds integral unavailable. Chain
events append contiguous hash-linked observations; Bitcoin PoW/script validation
is the responsibility of the pinned Core node. Transaction/protocol evidence
references point to artifacts whose verification belongs to the observer. The
machine cannot turn an arbitrary evidence string into cryptographic proof.

`amount` is exact funding/issuance/receipt/demand/delivered/output value for
`FUND`, `ISSUE_VTXO`, `RECEIVE_LIGHTNING`, `PAYMENT_OFFERED`, `REQUEST_OUTGOING`,
`HTLC_SETTLED`, and `SWEEP_CONFIRMED`. Pure disposition events use zero; their
values are obtained from the referenced lots, never trusted from a duplicated
amount field. Record RPC snapshots, DB transaction IDs, source revision and
sanitized evidence hashes outside the economic log. Never publish HTLC preimages
or wallet secrets in the trace.

## Transitions

| Event | Preconditions and effect |
|---|---|
| `FUND` | Unique, owned, mature onchain outpoint; adds economic assets and external inflow. Pool funding increases budget. |
| `OPEN_CHANNEL` / `MOVE_TO_CHANNEL` | Free onchain lot, unique funding reference, transaction evidence and explicit directional capacities; changes representation without adding value. Observed opening uses a preceding fee-paying `ONCHAIN_TRANSACTION`; the legacy abstract lane assumes zero opening fees. |
| `ISSUE_VTXO` | Future expiry and exact allocations within backing capacity; creates a liability and encumbers its backing. It does not mint economic capital. |
| `RECEIVE_LIGHTNING` | Confirmed receipt evidence, sufficient inbound capacity, exact net new backing; increases local share and creates the matching claim. `fee` is an external receipt cost. Ark receive service fees need further instrumentation. |
| `PAYMENT_OFFERED` | Records offered demand before admission. This observation persists even if the following request is unaffordable. |
| `REQUEST_OUTGOING` | Valid holder inputs, prior offer, unallocated pool assets on the requested channel, actual outbound capacity, and `W + reserved + gross <= budget`; atomically reserves the declared gross policy: full input for abstract fresh change, or invoice plus routing limit for `change_backing: retained`. `max_holder_fee` separately bounds total holder fees, including routing. |
| `CANCEL_REQUEST` | Verified cancellation before acceptance; restores claims, reservations and capacity. |
| `HTLC_ACCEPTED` | `RESERVED -> COMMITTED`; increases cumulative F by the actual reserved lot value, releases the budget reservation, and maintains the outbound hold. |
| `HTLC_SETTLED` | Preimage evidence and amount/fee reconciliation; debits only delivered value plus routing fees from local assets. Forfeits original claims, retains original backing, and issues change against fresh reserves or reallocates the original backing under the retained policy. A proven unused routing-limit slice returns to free channel ownership and C; delivered value remains unrecovered. Holder fees include retained service revenue, which is not an external economic fee. |
| `HTLC_FAILED` | Keeps all committed assets/capacity at risk. It does not imply cancellation. A later proved settlement may still supersede failure. |
| `RESOLVE_FAILED` | Verified revocation, or canonical timeout resolution at/after the timeout with configured finality, restores the original claims and reserve. C references the earlier commitment; no new funds are invented. |
| `REFRESH` | Forfeits old claims; funds replacement from distinct free reserves, net of fees. Gross fronting is recorded and the old backing stays encumbered. |
| `EXPIRY_REACHED` | Checks all forfeited inputs' expiry; marks their backing `RECOVERY_DUE`. No economic or fronting recovery occurs. Live-holder expiry/write-off is outside this conservative lane. |
| `SWEEP_BROADCAST` | Exact onchain input outpoints, no competing claims, fee, destination and txid; `RECOVERY_DUE -> RECOVERING`. Mempool evidence is required from the observer. |
| `SWEEP_CONFIRMED` | Active-chain inclusion plus output/fee reconciliation; retires inputs, creates the one owned output at vout 0 in `CONFIRMING`, records fees and retires the recovered claims. Inclusion alone does not increase C. |
| `CAPITAL_REUSABLE` | Canonical finality for sweep **and** subsequent channel funding, explicit spend of the recovered outpoint, no fresh funding, and successful independent reservation on that asset. Atomically moves through `FREE_AGAIN -> RESERVED`, records C, and creates the next payment reservation. It is an actual model reservation, not a boolean reuse assertion. |
| `ONCHAIN_TRANSACTION` | Confirmed whole-input transaction with exact indexed outputs and miner fee. Optional round refresh commits the full fresh root, charges the holder service fee, and retains old backing. Optional sweep reuse requires the recovered output as the sole funding input for an independent round and credits its value once across declared earlier commitments. |
| `BACKING_EXPIRED` / `RECOVERY_SWEEP` | Generalized pool/shared-root expiry and sweep; reject live holder claims, incomplete linked commitments, and partial backing recovery. |
| `CHANNEL_CAPACITY` | Quiescent channel observation reconciles owned/remote shares and updates usable capacity without changing ownership. |
| `EXIT` | Verified cooperative/unilateral ancestry and canonical finality; consumes exclusively backed claim, records fees/outflow and retains the owner's external spendable-output receipt with zero value inside the operator boundary. |
| `REORG` | Rebuilds from the empty checkpoint using canonical hash anchors and causal closure; keeps invalidated observations in the append-only log with orphan reasons. See deep-reorg exception below. |

A next round funded from unrelated assets never recovers earlier fronting.
The observed independent round does recover the already swept original output. Free quota is insufficient by itself:
a request also needs a concrete free, mature pool lot and sufficient directional
capacity. Independently funded payments increase F and the funded budget, not C.

## Invariants and rejection semantics

The reducer clones state, validates the envelope, applies the transition, and
checks invariants before publishing either state or journal changes. Therefore
all rejected transitions, including late invariant failures, have zero state and
journal change. Offered-demand observations are separate accepted events.

* **I1:** `sum(A.amount) + outflows + external_fees + realized_losses = inflows`.
  Initial assets enter as explicit `FUND` events. Claims are excluded from A.
  Local shares plus remote share reconcile every channel.
* **I2:** Active, reserved and forfeited claim allocations against each lot are
  at most its amount; encumbered lots cannot be free. Zero-valued retired lots
  cannot still back live claims. Shared roots require disjoint bounded allocations; contingent overclaims are not admitted.
* **I3:** `F = sum(committed operation gross)`, `C = sum(operation recovered)`,
  `W = F-C >= 0`, `W + reserved <= budget`. Every C entry references an operation
  with a prior commitment. Pool inventory plus pool outflows/fees equals pool
  external funding plus explicit transfers of recovered nonpool backing. This
  physical equation is distinct from free *budget quota*.
* **I4:** For each holder, remaining ACTIVE/RESERVED claims plus outgoing and
  charged fees equal received/initial claims. Refresh and change preserve this.
* **I5:** Duplicate identity, rejection identity and SHA-256 replay determinism
  hold. Hash input is canonical key-sorted JSON of configuration and state;
  it is not a proof of truth of the source observations.
* **I6:** Expiry and failure status cannot increase free recovered capital. Settlement
  releases only the unused routing reservation under the retained policy, never
  the paid amount or its original backing. Recovery requires the recorded chain/protocol proof and
  surviving maturity/finality conditions. Reuse needs a successful reservation.

Sweep fees are not fictitious recoveries. If gross fronting was 1,000 and the
sweep returns 999, C increases by 999, while one remains permanently unrecovered
under `W = F-C`. This residual is a fee loss, not a censored recovery time or a
source of new credit. There is no general write-off transition in v1.

`SettlementLedger` remains the abstract holder settlement oracle. At checkpoints
without pending HTLCs, `reconcile()` compares its V-class holder balances against
valid K claims. The oracle's economic boundary differs from A: adding oracle
holdings to A would double count. The named checkpoint test settles a 600-sat
transfer in the oracle and verifies the 400-sat remaining claim.

## Reorganizations and unresolved irreversible outcomes

Ordinary reorgs roll back inclusion, finality, recovered output and dependent
reservations by replaying their surviving causal ancestors. Replay uses the
empty state as a valid checkpoint; optimizing checkpoint storage is deferred.
The canonical capital-time view is recomputed; old observations remain in J's
audit history and should be analyzed separately for historical perceived risk.

A Lightning settlement/receipt already executed offchain cannot be erased by
rewinding Bitcoin. If such an event depends on orphaned recovery/funding, v1
retains the last reconciled economic checkpoint, appends the new reorg evidence,
sets `reconciliation_required`, and **halts further transitions** except a new
chain reconciliation. It does not claim its old chain is current or invent a
replacement debit. This is a documented unsupported insolvency/contingent-credit
case; the next observer must expose the surviving liabilities and assets. Tests
prove that the external payment remains recorded and spending is blocked.

## Capital-time and experiment denominators

Each event accrues the old stock up to its observed height/time before changing
state. There is no hidden expiry sweep inside a simulation step. The suite
inserts intermediate ticks and obtains identical integrals to coarse replay.
Categories are fronting W, unique committed owned lots, in-flight HTLC budgets,
remote inbound shares, owned outbound shares, and free idle pool lots. Channel
ownership and service capacity are separately visible. A lot contributes once
to `unique_committed`; category integrals must **not be summed**. Provisioned
remote capacity is reported separately from the operator-owned boundary.

Exact integral units are msat-blocks and msat-seconds. Divide by 1,000 for
sat-blocks/seconds. Published ratios are dimensionless money-normalized durations
in blocks; conversion to JavaScript Number for ratios is approximate, while
raw integrals remain exact. Each ratio is accompanied by offered/delivered
values and delivery rate. `PAYMENT_OFFERED` prevents rejected requests from
disappearing from the denominator. Unknown timestamps produce null seconds.

Terminal obligations remain in state and are listed with outstanding amount,
recovery height, and right censoring. No terminal liquidation or zero recovery
time is assumed. For the supplied trace at height 15, the second payment's
1,000-sat front remains censored even though the first lifecycle recovered.

## Reproduction

```sh
node --experimental-strip-types --test model/*.test.ts
node --experimental-strip-types audit/peer_review/capital_artifacts.ts build
node --experimental-strip-types audit/peer_review/capital_artifacts.ts check \
  audit/peer_review/capital/config.json audit/peer_review/capital/lifecycle.jsonl
python audit/peer_review/render_capital.py  # matplotlib 3.10.7
```

The checker returns the first failing index/event ID, reason and last valid
state hash, exiting nonzero. A structurally valid but halted deep-reorg trace
returns `ok: true, reconciled: false` and also exits nonzero. The TypeScript sources have no runtime package
dependencies. Strict type checking used TypeScript 5.9.3 with Node declarations.
Randomized testing executes 128 deterministic seeds of 32 commands each, checks
every accepted/rejected transition and replay, and deletion-shrinks failures to
a 1-minimal command counterexample. A separate shrinker test verifies reduction.
No failing minimized counterexample remained in the completed run.

## Executed retained-backing lane

The [observed reconstruction](regtest/evidence/lifecycle-observed.jsonl) uses actual
outpoints and claim IDs. At its final snapshot F=138,158, C=99,204, W=38,954 sats.
C includes 499 sats of unused routing limit plus the 98,705-sat board sweep.
The first refresh committed a 38,982-sat root for a 38,652-sat claim. Recovery
allocation pays the earlier Lightning commitment first; 277 sats remain
unrecovered after that backing is exhausted. The second round commits 38,677
sats and leaves its 38,347-sat holder claim intact. The 277-sat shortfall is kept
in F-C and marked completed, not right-censored or debited again as an economic
loss. Miner fees already appear in I1.

These journal block heights are confirmed snapshot detection heights. Exact
HTLC acceptance and earlier round commitment intervals were not sampled;
seconds are null, and these integrals must not be described as precise
operational measurements. The full-chain capture permits economic replay and
synthetic reorg testing, not reconstruction of missing offchain timestamps.
