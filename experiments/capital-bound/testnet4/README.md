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

The runner exports testnet4-readiness.json, capability-matrix.json, transactions.jsonl, capital-ledger.jsonl, proof-receipts.jsonl, failure-ledger.json, results.json, report.md and a digest manifest. The native node launcher uses only isolated regtest funds. Testnet4 requires a current tip, peers, the pinned genesis and separate campaign wallets. Accounting integrates using observed times and heights, preserving a reorg-aware view of the active reserve. It counts Bitcoin inclusion and confirmed wallet-backed change separately. Reconcile until pending commitments resolve, including past the arrival window if needed.

The Nova application proof and Bitcoin header proof have different statements. Stage 0 independently verified a fixed LNMarkets batch-accounting fixture. Its Pallas transcript constrains funding outpoints and amounts. A fresh campaign batch needs an independently agreed journal and matching native pre-state, payout scripts, authorization and funding evidence. The historical header proof ends at height 4. The canary's Core Merkle receipt uses the current active chain. A fresh recursive SPV receipt needs a sufficiently recent authenticated checkpoint, the payment and continuation proof and a bounded proving run.

Checked reports from the first public run and the local Testnet4 readiness check are in `evidence/`. The artifact IDs and SHA-256 digests identify the exact source receipts.

The upstream BABE receipts cover the funded indexed dispute relation on regtest. A complete M14-backed funded dispute suite and application payout and recovery composition are required for public BitVM3 settlement. Keyless-CHECKSIG and BIP 448-dependent constructions belong to patched regtest.
