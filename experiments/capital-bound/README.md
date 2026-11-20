# Capital Bound Moves: experiment program

This directory contains the executable follow-up to the November 20 paper review. The Python tools use the standard library. Evidence is kept at its measured scope: synthetic routing and finite-budget models, signed Bitcoin Core regtest transactions, and independent verification of an existing Nova v2 proof.

`lab.py` performs offline arithmetic. `core_regtest.py` launches a fresh isolated Bitcoin Core regtest, signs with a public fixture key, and mines its own recovery and reuse transactions. `proof_adapter.py` runs a pinned existing Nova verifier on CPU and imports funded BitVM receipt shapes. The full Ark/BitVM application integration and public Testnet4 pilot remain in `protocol.json`.

## Implemented stage

The registry in `../../model/registry.ts` now settles rewards with `settleEpoch(liveSet, pool)`. It validates live descendants, uses exact integer products, freezes a payout receipt and its commitment, then advances the epoch. `previewAllocation()` supplies provisional arithmetic; it is not a reward authorization. The compatibility `closeEpoch()` closes with a zero pool, and calling the deprecated `allocate()` after it throws. Undistributed floor remainder is recorded in the receipt.

`../../model/capital-bound.ts` enforces finite funding during admission. Its default six-request witness funds both arms with 1,600 sats. Lightning settles six invoices worth 2,600 sats. The selected Ark reserve partition settles four worth 1,800 sats; inbound capacity and fronting each reject one request. Both arms consume 32,000 funded sat-blocks through block 20. Ark fronting consumes 5,300 unavailable sat-blocks. This exposes admission effects in a controlled reference model; the witness does not estimate a deployment-wide advantage.

The native Core probe uses a signed three-block CSV script. It verifies rejection before maturity, acceptance at maturity, restart, a one-block rollback of maturity, confirmed recovery and actual reuse. Its ledger follows 100,000 sats into a 99,000-sat recovery output and a 98,000-sat recipient output, with two 1,000-sat fees. The faucet wallet is outside this instrumentation boundary. This probe has no Ark or BitVM transaction graph and does not measure their capital efficiency.

[ADAPTERS.md](ADAPTERS.md) describes the Nova v2 interface and its limits. An existing 12,376-byte, two-contract proof was independently verified in 33.341 seconds with about 489 MiB peak child RSS. Setup accounted for 31.467 seconds and compressed verification for 1.793 seconds. A failed earlier attempt remains in the receipt. The proof constrains transcript hashing and accounting; native authorization and Bitcoin spendability have separate checks. No new proof was generated for this experiment.

Recorded results are under [results/2026-11-21](results/2026-11-21). Their UTC timestamps are retained. The directory date uses Asia/Singapore.

## Run from the repository root

```sh
node --experimental-strip-types --test 'model/*.test.ts'
python3 -m unittest discover -s experiments/capital-bound -p 'test_*.py' -v
node model/capital-bound.ts --out output/capital-bound
python3 experiments/capital-bound/lab.py analyze output/capital-bound/ark.jsonl
python3 experiments/capital-bound/lab.py analyze output/capital-bound/lightning.jsonl
python3 experiments/capital-bound/core_regtest.py \
  --bitcoind /absolute/path/to/bitcoind \
  --output output/capital-bound-core
```

The output directory for each native probe must be new. The launcher owns its temporary datadir and disables peer networking. It cleans up its own process on completion. Run Python with assertions enabled. The reorg check happens before release; raw rollback observations are retained separately from the monotone capital projection. A live adapter still needs rollback of previously accepted release records.

`.github/workflows/capital-bound.yml` runs the model checks and an unmodified Core 31.1 probe on public CI. A separate CPU job builds the pinned Nova verifier with its committed lockfile and verifies the small fixture. It never invokes a proving command. Bitcoin Core's archive is pinned to its published SHA256; both native reports retain binary and input hashes.

## Run the arithmetic tools from their directory

```sh
cd experiments/capital-bound
python lab.py counterexample
python lab.py analyze fixture.jsonl
python -m unittest -v test_lab.py
```

`protocol.json` defines the remaining regtest and Testnet4 program, including the controls and evidence required before a result can support a capital-saving claim. Its public-testnet funding and fee ceilings are proposed bounds for a future pilot. They have not been exercised.

## Routing counterexample

The diamond has directional balances of 2 on s→a, a→t, s→b and b→t; each reverse balance starts at zero. Two requests arrive: s→t for 1, followed by a→t for 2. Sending the first through a leaves a→t and a→s with 1 each. The second request has no path able to carry 2, so retries against that unchanged state fail. Routing the first through b preserves a→t's capacity and both requests succeed. The first route can also recover through multipart payment: 1 directly from a to t and 1 via a→s→b→t. The final balances then equal the successful second schedule.

Every nonempty proper subset of the four nodes is checked after each accepted transfer. The cut conservation identity holds in every state. This witnesses a distinction in the paper's mathematical claims: conservation under every routing policy does not by itself establish that route intelligence matters only through failed attempts under the stated single-path model. This counterexample does not estimate how often the effect occurs in a deployed Lightning network.

## Capital accounting

The analyzer accepts a JSONL event stream beginning with `run_start` and ending with `run_end`. Each event has an observer timestamp in integer seconds and an integer block height. Both must be nondecreasing. Time comes from a monotonic observer clock or from an explicitly documented conversion; block-header timestamps are unsuitable as a monotonic event clock. Analyze reorg segments through an adapter that preserves the observer's monotonic sequence and separately records rollback events. This simple analyzer rejects decreasing heights and does not implement reorg reconstruction.

Each `lot_open` introduces one canonical economic reserve with fixed positive integer sat value, an owner, and a `reserve_id`. The same reserve identifier cannot open a second lot. A virtual claim is represented as an encumbrance of its backing reserve and must never be introduced as extra capital. `lot_state` moves that reserve through disjoint lifecycle states:

| State | Counts as funded | Counts as encumbered |
|---|---:|---:|
| available | Yes | No |
| unavailable | Yes | Yes |
| pending_recovery | Yes | Yes |
| released | No | No |

Available reserves can be reused by returning to `unavailable`. Released lots are terminal. A completed proof can be recorded through `proof_verified`; this event leaves capital locked. A release requires a reference to observed spendability, a confirmed refund, or a confirmed timeout spend. The analyzer checks the shape of that record. An external adapter must authenticate it against the actual node and protocol.

Here `available` means usable again inside the experiment's funded budget. For example, directional liquidity in a Lightning channel may be available for another payment while its backing remains committed to the channel. It therefore still counts in funded exposure. A comparison using only encumbrance could hide the cost of that idle reserve.

For each interval, the analyzer adds `encumbered sat × elapsed seconds` and `encumbered sat × elapsed blocks`, and computes the corresponding integrals of total funded reserves. The totals describe distinct questions: encumbrance describes how much value the protocol keeps unavailable; funded reserves include provisioned idle value. Report both, as a system can pay for a large unused reserve while looking efficient on its encumbered balance.

Payment volume counts unique offered application invoices that have an exact matching settlement amount. Refreshes, rebalances, self-transfers and funding events remain visible in the trace and add no application volume. Duplicate invoice settlement fails validation. A `fee_paid` entry counts a transaction only once. Fees are recorded as a separate cost; this analyzer does not reconcile a complete Bitcoin balance sheet.

The analyzer exposes offer-to-settlement seconds for every paid application invoice and nearest-rank percentiles with their sample count. Unsettled invoices are listed separately, so the latency distribution must always be read alongside the delivery fraction. Live comparisons use the same application deadline and recipient-usable settlement criterion across arms. The protocol proposes a one-hour deadline for an initial comparison; confirmation time and eventual capital recovery remain separate observations.

At the end it reports every unresolved encumbrance. A short observation window can therefore show incomplete recovery directly. For a completed economic comparison, collect the drain period through final recovery. Never extrapolate a missing release from successful proof verification.

The supplied fixture gives **600 sat-blocks** and **6,000 sat-seconds** of encumbrance, **1,350 sat-blocks** and **13,500 sat-seconds** of funded exposure, and **100 sat** of unique application volume. Its **funded duration is 13.5 blocks or 135 seconds** per delivered sat. This is the primary duration for comparison with the paper's provisioned-capital accounting. Its separate **encumbered duration is 6 blocks or 60 seconds** per delivered sat. Peak encumbered capital is 150 sat, with zero remaining at the endpoint. A 100-sat refresh contributes no business volume. These figures are arithmetic fixtures.

The output exposes `funded_duration_blocks`, `funded_duration_seconds`, `encumbered_duration_blocks` and `encumbered_duration_seconds`. The older `liquidity_duration_*` keys remain aliases for encumbered duration, accompanied by an explicit definition; they exclude provisioned available capital.

## Boundary of the analyzer

Adapters must map the real transaction graph to canonical reserves. This program cannot discover whether two differently named reserve IDs conceal the same coins, authenticate a proof, verify a transaction, check UTXO inclusion, or establish finality. It reports `evidence_verified: false` even when an input is labeled `public_testnet4`. The source label is retained as supplied.

Reserve value is constant within one lot. `lot_replace` consumes distinct active parent lots and creates fresh child lots, enforcing `sum(inputs) = sum(outputs) + fee`. Retired lot and reserve identifiers cannot be reopened. The replacement records its transaction fee once and requires a spend/recovery receipt; a proof event cannot satisfy that condition. Children carry their own availability states. This supports explicit splits and merges while leaving transaction authentication to the adapter. Monetary quantities use exact Python integers; the output retains rational liquidity duration as numerator and denominator alongside a decimal.

`allocate_exact` supplies a small arithmetic control for reward allocation from an already frozen snapshot. It rejects negative or fractional weights and computes per-claim integer floors without mutating the snapshot. The caller retains the unallocated pool. Authentication, reward eligibility and epoch persistence belong to the registry protocol. An empty or all-zero weight set returns zero payouts.

## Proposed experimental interpretation

Use the same offered payment schedule and compare service at finite funding budgets. The current paper source at [Spiral df00b03](https://github.com/patrickdugan/Spiral/blob/df00b03b1727b6f5e7275d5f3f34ab822c5149f9/paper/tex/main.tex) defines the cut bound and the liquidity-duration ratio. The accompanying [model/server.ts](https://github.com/patrickdugan/Spiral/blob/df00b03b1727b6f5e7275d5f3f34ab822c5149f9/model/server.ts) gives the Ark simulator a very large funding budget in `runCorner` and calculates server-tier failures after the fact. The live experiment should enforce those inventory constraints during admission.

The proposed service target requires at least 99 percent of offered application invoices and 99 percent of their value to settle by the common deadline. Initial batches contain 1, 2, 8 or 32 claims; a 128-claim batch is a later scaling exercise. Before public Testnet4, prover, verifier and challenger roles run as separate processes, and regtest must exercise rollback after a reorg, process restart and complete recovery while rejecting stale-root and duplicate payouts.

Start with an unchanged Ark implementation and add Nova audit proofs under the same transaction rules. That establishes proof cost and audit coverage. A separate BitVM escrow arm can measure whether authenticated batch settlement improves cost or permits a safe earlier release. The latter result requires a transaction path that invalidates every superseded claim and makes the recovered value spendable. A shorter proof alone changes neither an Ark expiry nor a Bitcoin challenge window.
