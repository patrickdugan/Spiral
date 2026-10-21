# Owned regtest evidence and runner

The completed transaction-level run is recorded in `evidence/reuse-proof.json`
and `evidence/economic-reconciliation.json`. It proves original-board recovery
and exclusive reuse as a new round input. The normalized 34-event path also
passes `model/capital.ts` economic replay. It does not supply exact operational
clocks or live validation of the separate failure, receive, exit and reorg paths.

The subsequent [outbound failure report](../capital_failure_report.md) now
verifies two accepted/failed HTLCs followed by cooperative revocation, including
one captured pending-channel state. This leaves timeout, receive, exit and reorg
paths distinct from the completed cooperative failure path.

All participants and keys are owned test fixtures. The logical recipient is
outside the operator's accounting boundary even though its node is controlled
for the test. Mining funds are outside the fixture until the three recorded
initial outputs enter. Quarantined operator funds remain economic assets.

## Runtime

The runner uses Python 3.12, a task-local Docker 28.5.1 daemon, and immutable
images in `bootstrap.py`. Docker uses overlay2 with no bridge or iptables changes;
services bind loopback ports. Runtime data and signing material stay outside Git
in `/var/tmp/spiral-capital-runtime`. Public evidence is allowlisted into `evidence/`.
No system package, service unit, or global WSL configuration is installed.

Check actual host disk space before running: WSL's virtual free space can exceed
Windows physical free space. The Python runner requires at least 4 GiB host
headroom, and image pulling requires 6 GiB. The observed VFS disk-full failure and
chain-index recovery are documented in `../capital_regtest_report.md`.

For a fresh fixture, run under WSL:

```text
sh start-runtime.sh
python3 pull-images.py
python3 bootstrap.py /path/to/bark-at-8f5d8c4
python3 launch.py
python3 watchman.py /path/to/bark-at-8f5d8c4
python3 attest.py
python3 fund.py
python3 observe.py before-board
python3 pay.py
python3 isolate-expiry.py
python3 refresh-change.py
```

Run `node trigger-sweep.mjs expired-pool` from a host that can reach the loopback
watchman port, then `python3 quarantine-reserve.py`. Advance with
`python3 advance.py 4432 before-original-expiry` and
`python3 advance.py 4433 original-expiry-reached`. Run
`node trigger-sweep.mjs original-board`, capture `observe.py original-sweep-broadcast`,
then run `reuse.py` and `attest.py`. Heights are specific to this recorded fixture;
another run must derive its own board expiry before advancing.

Monetary actions write an intent before execution and refuse duplicate labels.
After any uncertain result, inspect actual state; do not rerun funding or payment
scripts to clear the error. `recover-chain.py` is the recorded one-time disk-full
recovery, not a normal setup step. Bootstrap also refuses stopped containers;
inspect their logs and state before explicitly restarting them.

## Independent checks

These checks run offline and need no keys or daemon access:

```text
python reconcile.py
python test_reconcile.py
```

The collector uses one repeatable-read, read-only DB transaction. Other RPCs are
sequential and bracketed by equal Core tip hashes, not cross-service atomic.
Preimages are verified in memory and removed before publication. The observer
uses `--no-sync` wallet reads and never signs, broadcasts, or advances the chain.
Mutation scripts are separate. Decimal BTC tokens are preserved as strings and
converted with exact decimal arithmetic.

For an in-flight payment, `snapshot(label, include_client=False)` avoids opening
the Bark wallet already owned by `send --wait`; the resulting client-read gap
is explicit. Pinned captaind wallet status reveals an address in memory without
persisting it, a nonmonetary side effect. Strictly side-effect-free wallet status
would require a different upstream endpoint.

Sweeps were manually triggered; the source-default two-hour cadence was retained
in config but not measured. Original VTXO lifetime 4320 and exit delta 144 were
retained. Optional pool replenishment was disabled after initial funding to
isolate recovery, with the intervention recorded. Accelerated block generation
and operator delays are not production latency measurements.

The first payment CLI returned empty stdout despite success. Its uncertain local
parser record is retained; `payment-result-reconciliation.json` proves settlement
without a duplicate send. Later code handles that CLI behavior explicitly.

## Economic reducer replay

From the repository root, run `node --experimental-strip-types audit/peer_review/regtest/normalize.ts`.
This reads only committed observations and validates the executed binary/source
pins. It writes the 34-event journal, config, per-event trace and economic
reconciliation. `capture-chain.py` supplies canonical headers using read-only
local RPC if recollection is required. No secrets or running services are needed
for normalization or replay.

The runtime manifest predates normalization and retains its historical
`reference_reducer_acceptance: false`; current acceptance is in
`machine-reconciliation.json` and `../capital/execution-status.json`.
Exact HTLC acceptance and round commitment times were not sampled. The journal
uses confirmed snapshot detection heights and null seconds; it cannot support
a precise operational latency claim.

## Inventory-backed receive extension

See [the inbound report](../capital_inbound_report.md) for the verified 2,000-sat
receipt, the 104-sat service fee, pre-funded pool ancestry and depth-excluded
change. `enable-inbound.py` records the pinned hold-plugin addition;
`prepare-inbound-pool.py` issues one two-leaf pool and disables replenishment;
`receive-inbound.py` attempts one payment. These action scripts refuse existing
intent labels. Do not rerun them to resolve an uncertain payment.

The first receipt completed but its CLI result did not parse. The committed
`reconcile-inbound.py` reads that existing attempt; it never pays again.
`attest-inbound.py` records public source, chain and transaction pins. Run
`node --experimental-strip-types audit/peer_review/regtest/normalize-inbound.ts`
from the repository root to reproduce the 49-event journal offline. The live
fixture now has the loopback hold plugin enabled, automatic pool issuance
disabled, and no pending HTLC from this experiment. Historical snapshots retain
their original configuration and chain tip.

## Cooperative exit extension

The [exit report](../capital_exit_report.md) verifies an 18,632-sat claim's
cooperative offboard to the same client's on-chain wallet. `offboard-observed.py`
is a one-time action with intent guards. `attest-offboard.py` synchronizes the
client's on-chain cache and captures public transaction/source/chain evidence.
Replay the committed evidence with
`node --experimental-strip-types audit/peer_review/regtest/normalize-offboard.ts`.
The resulting 51-event journal retains the original backing and 330-sat
connector; neither is assumed recovered. The captured tip is 4445, and the
confirmed client payout is 15,732 sats.

## Exit reorg extension

The [reorg report](../capital_reorg_report.md) records a controlled three-block
reorg of that exit. Observers were paused during empty-block fork construction
and resumed at the higher replacement tip. The identical transaction was
observed pending at 4446, then reconfirmed in 4447 with a final tip of 4449.
`reorg-exit.py` is a guarded one-time action; do not rerun it against the
completed fixture. Reproduce the 53-event journal offline with
`node --experimental-strip-types audit/peer_review/regtest/normalize-reorg.ts`.
The pending checkpoint is explicitly unreconciled and cannot authorize
spending. Final reconciliation retains the spent claim, forfeit and all
earlier journal evidence without charging another payout or fee.
