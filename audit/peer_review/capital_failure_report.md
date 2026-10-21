# Observed outbound HTLC failure and cooperative revocation

Two deliberately failed payments extend the already reconciled owned-regtest
lifecycle. They add no external funding and move no settled value to the peer.
The [46-event journal](regtest/evidence/failure-lifecycle.jsonl) passes the
reference reducer and deterministic replay. Its [reconciliation](regtest/evidence/failure-machine-reconciliation.json)
joins Core, both CLN channel views, Bark claims, captaind attempts/resolutions,
and the signed virtual transaction ancestry.

## What was observed

| Quantity | First attempt | Second attempt |
|---|---:|---:|
| Invoice | 1,000 sat | 1,001 sat |
| Quoted holder fee ceiling | 83 sat | 84 sat |
| Source-derived routing allowance | 74 sat | 75 sat |
| Actual HTLC principal | 1,000 sat | 1,001 sat |
| Captured CLN spendable-capacity reduction | unavailable | 1,428 sat |
| Fee actually charged after revocation | 0 sat | 0 sat |
| Deliberate receiver-held interval | 2.164484015 s | 14.511083908 s |
| Lower bound on principal exposure | 2,164.484015 sat-seconds | 14,525.594991908 sat-seconds |

Both attempts occurred at height 4,439. The receiver's instrumented hook
accepted each HTLC and later returned a failure. The second pending snapshot
shows the same 1,001,000-msat HTLC outbound at the server and inbound at the
peer. CLN reported `SENT_ADD_ACK_REVOCATION` while captaind's attempt still said
`requested`: the database status alone did not describe actual channel exposure.

Before and after each attempt, server Lightning ownership remained 440,000
sats, receiver ownership remained 60,000 sats, server spendable capacity
returned to 430,694 sats, and the client retained 38,347 sats. Wallet UTXOs and
their amounts were unchanged. No preimage settlement was recorded. Each
attempt's HTLC rows became `revoked`, and the corresponding CLN payment became
`failed`. The second `bark send --wait` command exited zero despite that failed
payment: CLI exit status is not a settlement or accounting oracle.

The 84-sat quote was an admission ceiling, not a charged fee. In the second
attempt, 1,001 sats actually in flight, a 1,076-sat invoice-plus-routing envelope,
and 1,428 sats of lost spendable capacity are three different quantities. The
additional CLN capacity headroom is not a second economic asset or additional
payment. The reducer now records actual in-flight principal and observed
capacity reservation separately, and restores that capacity upon verified
resolution. Attribution of a capacity observation requires an isolated attempt
on that channel; it cannot absorb another concurrent HTLC's reservation.

## Claim identities and conservation

Revocation did not reactivate the original claim ID. The first attempt replaced
the 38,347-sat input with two 18,632-sat change claims and one 1,083-sat refund.
The second consumed the 1,083-sat refund and one 18,632-sat change claim. The
terminal client claims are 18,632, 9,315, 8,987, 1,083, 328 and 2 sats, totaling
38,347 sats. All remain backed by the previously proved reuse-round root
`09f458267cc9f50da7af5ad1a32f39b4d83db5eb5dd44aa8ac9bc53b981da272:0`,
with expiry 8,756. The two-sat claim is an observed subdust Arkoor claim;
immediate standalone onchain redemption is not asserted.

`RESOLVE_FAILED` can now replace reserved input claims with the observed
refund/change claims atomically. It verifies claimant, parent identity,
expiry, total backing, and each parent's exact allocation. Old claims retain
their historical amounts and provenance but no longer allocate the same
backing. The [decoded virtual transactions](regtest/evidence/failure-virtual-transactions.json)
prove each new claim's ancestry and output amount. They are claims, not extra
economic assets, and this decoder did not broadcast them.

The two reservations add 2,150 sats to both F and C. Final W remains 38,954
sats, exactly as before the failure experiments. Economic assets, actual fees,
service revenue, and settled outflows are unchanged. The original successful
34-event journal and its independent-reuse proof remain intact.

## Instrumentation and collection gap

The receiver used a small, pinned dynamic plugin implementing CLN's
[documented HTLC hook](https://docs.corelightning.org/reference/hook-htlc_accepted).
It activates only on regtest and one configured payment hash, fails after an
explicit release or a 90-second guard, and never supplies a preimage. Other
HTLCs pass through. It was stopped after collection. Its source hash, Python
executable hash, Debian package versions and kernel boot ID are recorded in
the instrument manifests. Python was added only to the owned receiver's
container overlay; the Lightning executable still matched its archived SHA-256.

The first in-flight collector failed when it attempted a concurrent Bark CLI
read during `send --wait`. Its raw error text was not retained, so wallet
locking is a source-supported explanation rather than a quoted observation.
The cleanup released the receiver hold. The original send process was checked
as terminal, and that same attempt was reconciled without resending it. The
[collection-gap artifact](regtest/evidence/failure-collection-gap.json) preserves
the missing evidence. The separately labeled second attempt used server-side
and channel reads while the client owned its wallet. Its missing intermediate
client fields are explicitly marked, not reconstructed as observations.

The collector makes no monetary transition. One nonmonetary side effect is
now documented precisely: pinned captaind `WalletStatus` reveals the next
address in memory without persisting that reveal. Wallet comparisons therefore
use UTXOs and amounts, not the changing displayed address. A completely
side-effect-free wallet-status endpoint would require upstream instrumentation.
The relevant pinned source blobs are in [failure-source.json](regtest/evidence/failure-source.json).

The held intervals are measured on one kernel's monotonic clock. They bound
only the deliberately delayed receiver phase, not the whole sender reservation,
failure propagation or revocation interval. They are not natural latency
samples. Historical unknown timestamps keep whole-journal second integrals
null; these measured lower bounds are reported separately. Intermediate client
input claims remain aggregate reservations until terminal replacement
reconciliation, so the journal does not claim every intermediate client ID
was sampled.

## Verification and remaining scope

From the repository root:

```sh
python audit/peer_review/regtest/test_fault_plugin.py
node --experimental-strip-types audit/peer_review/regtest/normalize-failure.ts
node --experimental-strip-types --test model/capital.revocation.test.ts model/capital.observed-failure.test.ts
```

The instrument tests cover the non-regtest gate, explicit failure release and
automatic guard. Reducer tests cover actual replacement claims, measured
capacity/principal separation, tampered refunds, holder/backing substitution,
expiry extension, zero economic change on rejection and deterministic replay.

This verifies cooperative revocation after an accepted, failed outbound HTLC.
Live timeout/unilateral failure recovery, inbound issuance, exits and chain
reorganizations remain separate paths. Testnet4 still awaits a synchronized
RPC endpoint and dedicated test funding. No public-network transaction was
made by these experiments.
