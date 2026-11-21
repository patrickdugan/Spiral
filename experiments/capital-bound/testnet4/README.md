# Capital Bound Moves on Testnet4

This stage follows Spiral PR [#17](https://github.com/patrickdugan/Spiral/pull/17). The runner signs an explicit outpoint into an invoice payment and payer change. It can then spend the confirmed change into the next invoice group. Each step conserves satoshis and records the transaction Core accepted. The capability matrix pins the sources for Nova, BABE and the historical Testnet4 SPV lane.

## Native regtest and proof gates

Run from the Spiral root, where the Stage 0 files are available.

~~~sh
python -m unittest discover -s experiments/capital-bound/testnet4 -v
python experiments/capital-bound/testnet4/native_regtest.py \
  --bitcoind /path/to/bitcoin-31.1/bin/bitcoind --out output/cbm-native
~~~

The public workflow downloads and checks the pinned Core binary, mines both native workloads and uploads sanitized results. The canary regtest replay verifies both payment blocks with a second isolated Core instance. It also rebuilds the pinned public verifier key and verifies the existing Testnet4 genesis-to-height-4 proof on CPU. The same job runs the upstream statement-mutation checks. The Stage 0 workflow builds and runs the separate LNMarkets Nova v2 verifier.

The native comparison uses the same six invoice IDs, amounts, arrival schedule and 100,000-sat funding position in each arm. Each process has a new Core chain and separate payer and recipient wallets. In the batched arm, two obligations share a settlement transaction. The fixed fee of 400 sats per transaction makes this a controlled baseline. Field fee and confirmation times depend on relay conditions and blocks.

The four-node diamond's directional exhaustion and route changes remain in the Stage 0 simulation and finite-budget reference. The two mined native profiles exercise settlement and reuse for a fixed invoice trace. They make one matched observation, so the campaign reports no confidence interval. Compare unavailable capital-time at 99% delivery by count and value before testing the proposed 10% target at greater scale.

## Public canary

Run stock Core 31.1 or newer on a dedicated data volume. Put the following in the canary node's bitcoin.conf and start that node with its explicit data directory.

~~~ini
testnet4=1
server=1
dbcache=128
par=2

[testnet4]
rpcbind=127.0.0.1
~~~

~~~sh
bitcoind -datadir=/absolute/path/to/cbm-node
bitcoin-cli -testnet4 -datadir=/absolute/path/to/cbm-node getblockchaininfo
~~~

Load distinct fresh signing descriptor wallets named cbm-pilot01-payer and cbm-pilot01-recipient. The payer needs exactly one eligible explicit outpoint, at least 4,200 sats with the default fee, at most 2,000,000 sats, and mature if it is a coinbase output. Use Testnet4-only funds. Keep node files and the campaign state directory private and outside Git. The state SQLite file contains reserved signed bytes, and the RPC cookie stays in the node's data directory.

~~~sh
bitcoin-cli -testnet4 -datadir=/absolute/path/to/cbm-node createwallet cbm-pilot01-payer
bitcoin-cli -testnet4 -datadir=/absolute/path/to/cbm-node createwallet cbm-pilot01-recipient
bitcoin-cli -testnet4 -datadir=/absolute/path/to/cbm-node -rpcwallet=cbm-pilot01-payer getnewaddress
~~~

After native CI passes on the source being run, use an explicit campaign ID and preserve the same state directory between invocations. In the shell block, replace the funding placeholder with the actual lowercase transaction ID and output index.

~~~sh
campaign() {
  python experiments/capital-bound/testnet4/campaign.py \
    --network testnet4 --campaign pilot01 --state /absolute/private/path/pilot01 \
    --datadir /absolute/path/to/cbm-node "$@"
}
campaign preflight
campaign plan --funding TXID:VOUT
campaign dry-run
campaign broadcast-canary --broadcast
campaign observe
campaign reconcile
campaign report
~~~

The dry run asks Core to sign and check relay policy without submission. Once signed, the journal reserves the same immutable transaction. After an interrupted send, observe the original ID. An explicit --retry-same submits those identical bytes if the original input is still spendable and policy still accepts it. A fee rejection after reservation is recorded as a stalled arm and requires a fresh campaign for a new fee schedule.

For the second payment, add --observer-datadir and --observer-port before the subcommand and point them to a separate synced Core node on loopback. Reconcile the first payment with both nodes, then call broadcast-canary --advance --broadcast. The second transaction spends the first transaction's recovered change and is separately observed through confirmation. The Testnet4 runner allows the two-payment canary. Matched individual and batch profiles are currently exercised on regtest.

Public GitHub jobs run without a funded wallet. The manual workflow dispatch runs the public gates again. Testnet4 signing and submission run on the operator node, with its own preflight report and explicit broadcast flag.

## Read the receipts

For an isolated Windows signer, pass `--relay https --observer-tip /private/path/manifest.json`
before the subcommand. Use the manifest from the connected Core export and import its blocks
through local Core first. The manifest must match the locally validated height, hash and chainwork
and be under 30 minutes old. The HTTPS mode keeps the confirmation, funding, budget and Core
mempool-policy checks. The native relay continues to require Testnet4 peers.

`broadcast-canary --broadcast` submits the reserved bytes to Mempool's Testnet4 HTTPS relay.
When the shell cannot access that endpoint, add `--signed-out /private/path/canary.hex` and submit
the file's content at [Mempool Testnet4 Broadcast Transaction](https://mempool.space/testnet4/tx/push).
Check the returned transaction ID against the journal. An uncertain submission can be retried
with `--retry-same`. Local Core confirms settlement after importing the relevant blocks. The
second payment still requires an independent Core observation of the first.

The runner exports testnet4-readiness.json, capability-matrix.json, transactions.jsonl, capital-ledger.jsonl, proof-receipts.jsonl, failure-ledger.json, results.json, report.md and a digest manifest. The native node launcher uses only isolated regtest funds. Testnet4 requires a current tip, peers, the pinned genesis and separate campaign wallets. Accounting integrates using observed times and heights, preserving a reorg-aware view of the active reserve. It counts Bitcoin inclusion and confirmed wallet-backed change separately. Reconcile until pending commitments resolve, including past the arrival window if needed.

The Nova application proof and Bitcoin header proof have different statements. Stage 0 independently verified a fixed LNMarkets batch-accounting fixture. Its Pallas transcript constrains funding outpoints and amounts. A fresh campaign batch needs an independently agreed journal and matching native pre-state, payout scripts, authorization and funding evidence. The historical header proof ends at height 4. The canary's Core Merkle receipt uses the current active chain. A fresh recursive SPV receipt needs a sufficiently recent authenticated checkpoint, the payment and continuation proof and a bounded proving run.

Checked reports from the first public run and the local Testnet4 readiness check are in `evidence/`. The artifact IDs and SHA-256 digests identify the exact source receipts.

## MuSig2 shared-capital pool

`musig_regtest.py` funds a `tr(musig(A,B)/0/*)` pool on isolated regtest. It settles two invoices plus pool change through Core's two-round MuSig2 PSBT flow, then spends the same batch from P2WSH 2-of-2 and single-key P2TR for comparison.

~~~sh
python experiments/capital-bound/testnet4/musig_regtest.py \
  --bitcoind /path/to/bitcoin-31.1/bin/bitcoind --out evidence/musig2-regtest.json
~~~

`musig_testnet4.py` stages the same pool on Testnet4 (`setup`, `fund`, `settle`, `observe`). It uses a private journal, an explicit `--broadcast` and `--retry-same` for identical bytes. It funds the pool from the dedicated payer's single confirmed output, so run it only after the canary is reconciled.

## BIP 448 on patched regtest

BIP 448 is not active on Testnet4. OP_TEMPLATEHASH, OP_CHECKSIGFROMSTACK and OP_INTERNALKEY run in `patrickdugan/bitcoin-rs` `dev` (merges `d48670f7`, `dd6c2040`) behind `--network regtest --bip448`. `evidence/bip448-regtest.json` records the test commands and the three-party LN-Symmetry update, replacement and settlement run.

## Results, 2026-11-21

| Stage | Network | Result |
|---|---|---|
| pilot01 canary | Testnet4, native P2P | `a97c0ea8` and `d8c5cbdf` confirmed. The second spends the first's recovered change. There are 4 Core Merkle receipts from two nodes. 2,800 sat delivered, 800 sat fees. Recovery took 1,730 s and reuse came 2,333 s later. invoice-1-0 settled at 4,392 s, past its 3,600 s deadline, after a ~35 min block gap. |
| MuSig2 pool | regtest, Core 31.1 | 2-of-2 key path: 197 vB, one 64-byte signature, 2 signing rounds. Single-key P2TR: 197 vB. P2WSH 2-of-2: 235 vB. |
| MuSig2 pool | Testnet4 | Funding `fb68d5ff` (100,000 sat) and settlement `70890635` (197 vB, 2 invoices plus pool change) in `evidence/musig01-testnet4.json`. |
| BIP 448 hyperedge channel | patched regtest (bitcoin-rs) | 3-party update 131 vB, CSV settlement 171 vB. A later state replaces an earlier one. Stale state, tampered template, tampered signature and early settlement are rejected. |

Evidence for each row is in `evidence/`.

The upstream BABE receipts cover the funded indexed dispute relation on regtest. A complete M14-backed funded dispute suite and application payout and recovery composition are required for public BitVM3 settlement. Keyless-CHECKSIG and BIP 448-dependent constructions belong to patched regtest.
