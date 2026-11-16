# Bark caretaker

The caretaker uses the released Bark 0.8.1 API. It reads VTXOs, compares the wallet's network with local Core, and independently checks that each reported chain anchor exists in the active chain with at least two confirmations. Bark's wallet library performs Ark signature, script and ownership validation. These checks have different scopes: an anchor observation alone does not establish that an arbitrary VTXO is valid or spendable.

## Connect

Add these fields to an existing server configuration:

```json
{
  "bark_url": "http://127.0.0.1:3500",
  "bark_bearer_env": "PROOF_GROVE_BARK_TOKEN",
  "ark_regtest_execution": false
}
```

Set the bearer token in that environment variable. Keep Bark loopback-only and use a synced, txindex-enabled Core node for the same network. Generate an Ark receiving address in Bark first: the caretaker reads derivation index zero to bind its durable requests to that wallet. The browser never receives the bearer token or wallet signing keys.

Open **Ark caretaker → Read wallet**. This reads wallet state and chain anchors; it does not sign. Fixture clock controls disappear when a real wallet is read. The default demo still uses fixtures and never connects to a wallet.

## Delegated refresh on regtest

Dispatch requires all three: a `regtest` desk database, a Core node reporting `regtest`, and `ark_regtest_execution: true`. The browser then offers spendable VTXOs whose reported anchors passed the Core check. Select one, a scheduled block height before its expiry, and a preflight fee limit. Bark locks the input and submits signed participation; the server can carry it through a later round without interactive wallet participation.

The upstream API has no fee-cap field. The caretaker calculates the published expiry-based fee, refuses an estimate above the limit, and audits the signed result. A post-signing audit cannot prevent a race or undo an overspend. Consequently **production dispatch is always refused**, even if the configuration flag is set. A production signer must enforce the minimum successor value inside the same signing operation before this restriction can be removed.

Before dispatch, SQLite commits the immutable wallet/input/height/budget request and unique input reservations. Any timeout or crash after this point is uncertain. Retrying the same request reads Bark's rounds/history; it never sends a second refresh POST. A crash before transmission can therefore require manual reconciliation. Inputs remain reserved even after failure because a failed wallet operation may still have consumed funds. The desk offers no automatic unlock or fresh-signing retry.

**Check refresh progress** requires an exact input match and a Bark refresh movement, validates the reported successor value and extended expiry, verifies that the inputs are recorded spent, and checks the successors' active-chain anchors. A later poll repeats those chain checks. A reorg can change `confirmed` to `chain_unconfirmed`. This state is an observation, not an irrevocable settlement guarantee. The old operation record and input reservation remain intact.

The desk database and Bark wallet files contain private payment metadata. They stay local under `.runtime/` and are excluded from public receipt archives. Endpoint changes intentionally invalidate wallet binding and require review.

## Reproduce the actual integration

Use Linux/WSL, Docker, the official `barkd-0.8.1-linux-x86_64` release, and `server/captaind.default.toml` from the `bark-0.8.1` tag. The supervisor checks both file hashes and pins the server and Core images by digest. The [Bark release](https://gitlab.com/ark-bitcoin/bark/-/releases/bark-0.8.1) publishes the wallet binary and SHA256SUMS; the [source template](https://gitlab.com/ark-bitcoin/bark/-/blob/bark-0.8.1/server/captaind.default.toml) is pinned to commit `303682063ed7559b06dcf37c5cb37bb7037b943f`.

```bash
python3 tests/run-ark-stack.py \
  --bark /absolute/path/to/barkd-0.8.1-linux-x86_64 \
  --server-config-template /absolute/path/to/captaind.default.toml
```

The foreground supervisor creates a new chain, server, wallet, volumes, network and dynamic loopback ports. It mines valueless coins, boards 500,000 sats, drops the successful refresh reply, reopens the desk database, reconciles exactly one refresh, and invalidates/reconsiders the successor's funding block. It stops and removes only its owned labelled test resources. It retains logs and wallet artifacts locally in `.runtime/`. No existing wallet is selected. Keep the supervisor running in WSL; closing its last foreground process can stop Docker services.

`--keep-preview` retains the test dashboard for browser QA. Its runtime directory contains `preview.json`; create `STOP_PREVIEW` in that exact directory when done. The test does not execute a Cashu melt, presigned exit, Filecoin deal or funded BitVM challenge.

The official Compose example referenced Core 30 when checked, while the 0.8.1 server source and binary require Core 31 or later. This test pins Core 31.0. It also supplies the complete version-matched server template, a URL scheme for Core, and an explicit container RPC bind. All published host ports bind to loopback.
