# Controlled diamond operational-clock protocol

Version `controlled-diamond-20261021-v1`, specified before any experiment
allocation, channel opening or payment. This instantiates section 3 of the
[original protocol](../testnet4_plan.md). The [setup](peer-provisioning-20261021.json)
is preparation evidence; the monetary phases remain unexecuted at this commit.

## Budget and activation

Use the dedicated wallet's two observed deposits totaling exactly 510,000 test
sats. An initial live preflight must find all of that value confirmed, safe and
spendable, and all four CLN wallets empty. A changed initial balance requires
reconciliation and a declared protocol amendment. No additional funding is part
of this run; the original 1,000,000-test-sat ceiling is not a spending target.

Allocate 230,000 sats to A, 130,000 each to B and C, and 10,000 to D. The Core
wallet retains 10,000 sats less allocation fees. Open four private 100,000-sat
channels, A→B, A→C, B→D and C→D, pushing 50,000 sats to the recipient at each
opening. This leaves 110,000 sats for all on-chain fees and idle/anchor reserves.
The push is an internal transfer among controlled experiment owners.

Use an explicit initial allocation/opening fee rate of 2 sat/vB. Do not silently
bump fees or replace uncertain transactions. Record insufficient-fee, liquidity
and opening failures as outcomes. Opening requires confirmed allocation inputs.
Both endpoints must reach `CHANNELD_NORMAL`, have no unresolved HTLCs, and agree
on funding provenance and balances. Verify each funding output is 100,000 sats
on the active chain at depth at least three before sending any payment.

## Frozen workload

Attempt 200 invoices exactly once each. For zero-based index `i`:

- Even `i` sends A→D; odd `i` sends D→A.
- The intermediate is B when `floor(i/4)` is even, otherwise C.
- The invoice is 1,000 sats when `floor(i/2)` is even, otherwise 2,000 sats.
- Wait at least two seconds after each reconciled terminal result before the
  next attempt. A resumed run retains the existing payment hash and observes its
  outcome; it never resubmits that payment.

This offers 300,000 sats, with 75,000 sats in each direction on each two-hop
path. Use explicit routes over the observed short channel IDs. Derive the
intermediate fee with integer millisatoshi arithmetic from that channel's
actual base and proportional fee; derive CLTV from the invoice and the
intermediate's actual configuration. Do not substitute mainnet defaults for
testnet4 parameters. Forwarding fees transfer value within the four-node boundary.

After each terminal attempt, reconcile all eight channel endpoint balances.
Success must debit the source by principal plus fee, credit the destination by
principal, and leave the intermediate with exactly the fee. A failed payment
must leave every channel balance unchanged after revocation. Validate the
successful payment's preimage against its hash in private memory/artifacts,
then exclude preimages and invoice secrets from public export. A pending
`waitsendpay` timeout is not a failed payment. Any discrepancy stops new attempts.

## Clocks and observation boundaries

The 48-hour clock starts only after an eligible initial preflight and immediately
before the funding cycle's run manifest is saved. Persist both wall and
monotonic deadlines and the WSL boot ID. Refuse new economic actions when either
deadline is reached or the host boot changes. Continue read-only final collection
to report unfinished waits as right-censored. Waiting for the initial donated
funds is preparation and does not consume or reset an already-started run.

Every monetary RPC has a durable, exclusive intent file written and synced
before invocation, plus a separate result or uncertain-outcome file. No intent
is overwritten. Submission timestamps bracket the local RPC, rather than claim
an inaccessible internal broadcast timestamp. Capture a post-return mempool
read, funding-output confirmation evidence, canonical inclusion headers and
both endpoints' activation notifications. A missed mempool observation remains
missing; it is not inferred from later confirmation.

`clock_observer.py` passively subscribes to block, channel-state, forward and
sendpay outcome notifications. It installs **no hooks** and never changes
routing or settlement decisions. Each callback records observer monotonic and
wall time in an append-only hash-linked journal. Callback receipt is not the
daemon's exact internal commit time; notification scheduling and journal I/O
are measurement overhead. Journals retain restarts and are checked for integrity.

`experiment.py` polls the sender's active HTLCs and spendable balance at a nominal
25-ms cadence through the local Unix RPC socket. Each read carries start/end
times, and samples are flushed before proceeding so uncertain attempts retain
their trace. Actual cadence includes RPC and disk time. Reservation onset and
release must be reported as intervals bracketed by observations, not point
estimates. An HTLC absent from every sample has an unresolved duration bounded
by the enclosing submission/terminal observations, not an asserted zero. A
resumed collection has an explicit gap. Intermediate forward callbacks provide
a distinct observed forwarding interval; do not equate that with total sender
reservation time. Keep principal and observed capacity reservation separate.

Record miner header timestamps separately from node-observed block arrivals.
The Windows/WSL CLI bridge adds backend transport overhead and is part of this
fixture. All nodes share one host; this measures implementation and testnet
confirmation behavior, not geographic or mainnet routing latency. The experiment
does not alter the historical regtest or frozen matched-service forecasts.

## Execution and evidence

Private configuration, HSM material, invoices and raw action responses stay
under `/var/tmp/spiral-testnet4-runtime`. Before public export, validate economic
accounting and remove preimages, invoice secrets, wallet descriptors and auth.
The passive observer already selects only public schema fields.

Run from the repository in WSL:

```sh
python3 -m unittest discover -s audit/peer_review/testnet4 -p 'test_*.py' -v
python3 audit/peer_review/testnet4/experiment.py instrument
python3 audit/peer_review/testnet4/experiment.py begin
python3 audit/peer_review/testnet4/experiment.py allocate
# Observe confirmed allocation, then enable the private bridge's broadcast
# capability and restart only that verified task-owned bridge process.
python3 audit/peer_review/testnet4/experiment.py channels
python3 audit/peer_review/testnet4/experiment.py observe
python3 audit/peer_review/testnet4/experiment.py payments --count 1
# Inspect the first live accounting checkpoint before larger bounded batches.
```

Instrumenting empty peers does not start the 48-hour run. CLN's pinned image
requires an added Debian Python runtime including its standard library for the
collector; installed package versions and executable hashes are separately
attested. Do not replace daemon binaries. The runner's pure accounting and
safety tests are not a substitute for validating its first live opening and
payment; those phases remain pending until funded execution actually occurs.

## Exact interface sources

The following Git blobs were read at CLN source revision
`8684c68dffb04ab606e526b64d7d60390d1fe7ed`:

| Schema under `doc/schemas/` | Git blob |
|---|---|
| `fundchannel.json` | `c90067c50459baa74ba2261a0490baeb4b86e491` |
| `sendpay.json` | `fc1a98ae1e14ffa2d051619db43f89dd4eb4780a` |
| `notification/block_added.json` | `182decb2e3cb2053ee675b8eab63fa711eb7d74b` |
| `notification/channel_state_changed.json` | `bb2f0f4866a3c453dd98c08d29e46fdc3a050297` |
| `notification/forward_event.json` | `920941bc3ac0a3bbe7f3c81175bc2a3fc73deec1` |
| `notification/sendpay_failure.json` | `02e47b1c3bdd0cf3734127e7302de9980e76c05f` |
| `notification/sendpay_success.json` | `a434b191efa18d8fe1e70825f495450dadac344a` |

Pinned [notification schemas](https://github.com/ElementsProject/lightning/tree/8684c68dffb04ab606e526b64d7d60390d1fe7ed/doc/schemas/notification)
define payload fields. The official [notification mechanism](https://docs.corelightning.org/docs/event-notifications)
explains subscription delivery. Core 31.1's installed `help sendmany` confirms
string BTC amounts and an explicit sat/vB `fee_rate`, preserving exact amounts.
