# Capital lifecycle execution report

Date: 2026-10-21. **The owned Ark regtest lifecycle has not run.** The accounting
implementation, synthetic lifecycle and read-only snapshot adapters have been
locally verified; the full requested acceptance criterion remains unmet.

## What was executed

The implementation branch starts at Spiral
`23155003010310c3a5c41b9ab8f3db910e69bc3e` on
`review/bitcoin-peer-review-2026-10-21`. Node v24.19.0 executes the TypeScript
reference model with built-in type stripping. Strict static checking uses
TypeScript 5.9.3. Figures use Python 3.12 and Matplotlib 3.10.7. The new reducer
adds no runtime package dependency to Spiral.

The [synthetic event journal](capital/lifecycle.jsonl) records one complete
funded-to-recovered-to-reused model lifecycle. Its hash/check result and terminal
state are in [lifecycle-check.json](capital/lifecycle-check.json) and
[lifecycle-summary.json](capital/lifecycle-summary.json).

| Quantity at height 15 | Satoshis |
|---|---:|
| Initial/external funding: original backing + reserve + second claim backing | 3,000 |
| Delivered outward payments: 600 + 1,000 | 1,600 |
| Remaining economic assets: change backing + second payment recovery backing | 1,400 |
| External fees/losses in this zero-fee fixture | 0 |
| Original dedicated reserve budget | 1,000 |
| Cumulative gross fronting F | 2,000 |
| Proven reference-model recovery C | 1,000 |
| Outstanding second front W, still censored | 1,000 |

The 600-sat payment forfeits a 1,000-sat input and creates a 400-sat claim on the
fresh reserve's remaining economic balance. The original 1,000-sat backing stays
locked through expiry at height 10. Sweep inclusion is observed at 11; the
fixture's new funding transaction is included at 12; its independent reservation
is admitted at 13 with two confirmations. That second operation names the
recovered output and successfully settles without new external funding between
recovery and reuse. The second client's backing existed before recovery and was
never counted as free reserve.

Both offered and delivered value are 1,600 sats (100% delivery in this tiny
fixture). Fronting integrates to 15,000 sat-blocks and 9,000,000 sat-seconds.
Unique committed owned assets integrate to 34,000 sat-blocks and 20,400,000
sat-seconds. The corresponding durations are 9.375 and 21.25 blocks over either
denominator. These categories overlap and must not be added. Immediate
acceptance/settlement in this fixture creates zero-duration HTLC exposure;
that is a modeling choice, not a latency observation.

![Synthetic recovery states and capital-time](capital/capital-trace.png)

The ten requested deterministic cases are named in `model/capital.test.ts`.
Additional tests cover schema rejection, duplicate event identity, sub-satoshi
fees, source-pin mismatch, late settlement after failure, channel accounting,
oracle checkpoints, timestamps, deep-reorg halting and demand denominators.
Randomized stateful testing checks 4,096 generated commands and supplies a
deletion shrinker for counterexamples. See [verification.json](capital/verification.json)
for the completed run's counts, commands and code hashes.

## Why the regtest lane did not run

The Windows host has no Docker, bitcoin-cli, captaind or lightning-cli executable
on PATH. An existing Ubuntu-24.04 WSL environment was checked outside the shell
sandbox; it has Cargo, but no Docker socket or Docker/bitcoind/lightningd/captaind
executable. No running owned stack, daemon endpoint, wallet snapshot or effective
configuration was provided. No daemon was launched and no transaction was signed
or broadcast. Source inspection and TypeScript tests do not fill that gap.

The source references were pinned successfully. Their complete hashes are in
[source-pins.json](capital/source-pins.json). The actual chain genesis, execution
binary/container digests, effective node configuration and initial node/wallet
snapshots are explicitly **null**. No standard regtest genesis was guessed and
no mutable container tag was reported as a digest.

[execution-status.json](capital/execution-status.json) preserves the environment
observations and missing evidence. [deep-reorg-unresolved.jsonl](capital/deep-reorg-unresolved.jsonl)
preserves a synthetic unresolved implementation case: a branch change crosses an
already executed offchain payment. The reducer keeps that payment and freezes
spending; liability reconstruction requires further observer data.

## Remaining acceptance work

Provision an owned pinned stack as described in the existing
[testnet4 protocol](testnet4_plan.md) and the [adapter instrumentation plan](capital_adapter.md).
Capture one real lifecycle plus failure/refresh/exit/reorg branches, reconcile
the whole backing graph and fees, then independently spend the recovered asset.
Resolve actual channel reserves and opening fees rather than copying this
fixture's zero-fee, fully spendable channel assumptions.

The [matched-service status artifact](capital/matched-service-status.json) is
blocked before observed recovery calibration. Existing matched-service
sensitivity results remain forecasts; they have not been relabeled or replaced
by synthetic "observations." Re-running the paper comparison under measured
semantics, bounded testnet4 clocks, and patched-local BIP 448/LayerTree experiments
all remain downstream of the missing regtest verification. No testnet4 experiment
was attempted.
