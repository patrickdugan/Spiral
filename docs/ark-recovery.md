# Saved Ark exits and an independent watcher

The owner can save Bark's presigned exit transactions and their fee-paying CPFP children, export them privately, and run a broadcaster that connects only to Core. It does not load the Bark wallet, mnemonic or a Cashu bearer proof. This implementation dispatches on **regtest only**. The owner still signs the final claim after its relative timelock.

## Prepare with the owner wallet

Use a `mode: "regtest"` configuration with the existing Core settings, `bark_url`, `bark_bearer_env`, and `ark_regtest_execution: true`. The owner wallet needs confirmed on-chain funds for CPFP fees in addition to its VTXO balance.

```bash
python -m proofdesk exit-prepare --config owner.local.json \
  --vtxo TRANSACTION_ID:OUTPUT_INDEX --fee-rate 5 --max-fee 25000
python -m proofdesk exit-export --config owner.local.json \
  --id RETURNED_BUNDLE_ID --output private-recovery.json
```

`--fee-rate` is sat/vB. `--max-fee` covers the sum of the saved CPFP fees; the final owner claim has an additional fee. Core decodes every raw transaction. The desk checks transaction identities, the selected anchor ancestry, wave dependencies, conflicting inputs, exact satoshi conservation, P2A fee anchors, successor values and the total CPFP budget. Partially signed plans are refused. The planning allowance is six blocks per wave plus the claim delta and six extra blocks; this is not a confirmation-time guarantee.

An exact preparation retry returns the existing package. Changing its inputs or budget requires review. Desk input reservations prevent the same VTXO from being refreshed through this desk while its saved exit is held. **Bark itself reserves no fee coins when presigning.** Another wallet spend or refresh can invalidate the package. Preparation does not prove that every future transaction is already eligible for the mempool.

Before delegating broadcast, stop the owner wallet or place it under exclusive manual control, and do not authorize another operation using the selected VTXOs or fee inputs. Presigning does not stop Bark's automatic refresh. The desk's reservation cannot freeze another wallet process. Core cannot establish that a VTXO has not been forfeited or spent off-chain; a still-unspent on-chain anchor does not establish that fact. The native test pauses the owner wallet during broadcasting, so no competing wallet operation can be authorized in that interval.

The exported file contains signed spending transactions and private payment metadata. The export command creates a new file with owner-only permissions on systems that support them. Keep it private and retain its bundle ID through a separate trusted channel. Its hash establishes byte identity, not ownership, availability or consensus validity. Exit data is excluded from the public receipt/Filecoin bundle.

## Run without the owner wallet

Copy only the private recovery package and its independently authenticated bundle ID to the broadcaster. For example, `broadcaster.local.json` needs no Bark URL or wallet keys:

```json
{
  "mode": "regtest",
  "database": ".runtime/broadcaster.sqlite",
  "ark_regtest_exit_broadcast": true,
  "core": {
    "url": "http://127.0.0.1:18443",
    "username": "recovery-broadcaster",
    "password_env": "RECOVERY_CORE_PASSWORD"
  }
}
```

Use a synced, txindex-enabled local Core 31 node for the same regtest chain. The read RPC methods are `getblockchaininfo`, `getblockhash`, `getblockheader`, `getrawtransaction`, `decoderawtransaction`, `gettxout`, `getmempoolentry`, and `testmempoolaccept`. The enabled broadcaster additionally calls `submitpackage`; it has no signing or wallet RPC method. Core credentials should allow only the needed methods.

```bash
python -m proofdesk exit-import --config broadcaster.local.json \
  --bundle private-recovery.json --expected-id OWNER_SUPPLIED_BUNDLE_ID
python -m proofdesk exit-advance --config broadcaster.local.json --id BUNDLE_ID
python -m proofdesk exit-watch --config broadcaster.local.json \
  --id BUNDLE_ID --broadcast --interval 5
```

Without `--broadcast`, these commands do not submit transactions. Broadcasting also requires the explicit configuration flag and a Core node reporting `regtest`. The HTTP interface accepts only a saved bundle ID; it has no arbitrary transaction-submission or file-import endpoint.

Before each wave, the broadcaster repeats the saved-plan checks and checks its current inputs. It waits for at least two active-chain confirmations of every parent and child in the previous wave. If a parent has already confirmed without its child, only the missing child is submitted. A lost reply is reconciled by the exact saved transaction IDs after restart. It never generates new signatures. Repeated submission of the same immutable transactions cannot create a second payment. Chain changes, unavailable observers and immature timelocks are retried by the watcher; rejected packages, missing inputs and reached expiry stop it for review.

Core 31's `testmempoolaccept` can reject the zero-fee parent before fully checking its fee-paying child. The app shows `requires_package_validation` in this case, rather than reporting verified signatures. The actual `submitpackage` operation validates the combined package. A successful submission is still followed by independent confirmation checks. The native negative test changes a Schnorr witness without changing the transaction ID: Core rejects the package and does not admit its zero-fee parent. See Core's [dry-run RPC](https://bitcoincore.org/en/doc/31.0.0/rpc/rawtransactions/testmempoolaccept/) and [package-submission RPC](https://bitcoincore.org/en/doc/31.0.0/rpc/rawtransactions/submitpackage/).

The watcher stops at `claim_ready`. The owner must sign a final claim with Bark or another compatible owner wallet. No Ark server cooperation is required for that claim, but the owner's keys, valid inputs, fees and timely confirmation remain necessary. A spent final output is reported as `target_spent`; the desk does not infer the claim's destination from that fact alone.

## Dashboard

**Ark caretaker → Read wallet** offers **Save regtest exit package** for an eligible VTXO. **Read saved plans** works with a Core-only desk even while Bark is unavailable. The card shows the package ID, private download, fresh checks, and an opt-in regtest broadcast action when enabled. Raw signed transactions are confined to the private download; the ordinary status view contains only metadata.

## Actual integration test

The [recorded test](ark-exit-integration.json) used a real Bark 0.8.1 wallet and Core 31.0. It saved two waves, stopped the Ark server, paused the owner wallet, rejected an altered witness through Core, exported/imported the authentic package into a separate desk database, and dropped the first successful submission reply. New CLI processes reconciled it. The remaining waves and claim clock were handled by an independent watcher process. The owner resumed and claimed to a preselected address with the server still offline. Core confirmed the destination, value and claim fee. A confirmed-wave reorg was detected separately.

Reproduce with the pinned binary and configuration template described in the [caretaker guide](ark-caretaker.md):

```bash
python3 tests/run-ark-stack.py \
  --bark /absolute/path/to/barkd-0.8.1-linux-x86_64 \
  --server-config-template /absolute/path/to/captaind.default.toml \
  --test-exits
```

The supervisor creates fresh labelled resources, runs refresh followed by exit recovery, and cleans up its own resources. Add `--keep-preview` to retain the Core-only recovery dashboard; its runtime directory contains `exit-preview.json`. Create `STOP_PREVIEW` there when finished. All coins, wallet keys and RPC passwords belong to this isolated test stack; no existing wallet is selected.
