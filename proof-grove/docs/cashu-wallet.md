# Proof-gated Cashu wallet and issuance bridge

The wallet is a separate Node 24 client using `@cashu/cashu-ts` 4.13.1. The Python desk holds payment evidence, quote bindings, and blinded requests. Wallet secrets never enter its API. Provider-backed issuance, recovery and a regtest-only Ark withdrawal are implemented. See [Ark withdrawal](cashu-ark-withdrawal.md) for custom melt commands and recipient checks.

## Install and run

From `wallet/`, run `pnpm install --frozen-lockfile --ignore-scripts`. Start the desk with a server-owned configuration containing `cashu_url` and the correct Core observer. Its default `live` admission path requires the existing pinned M16 verifier. Keep endpoints fixed for a vault.

Set `PROOF_GROVE_WALLET_PASSWORD` in the client process environment to your vault passphrase. The CLI does not print or store the passphrase. It uses scrypt and AES-256-GCM to encrypt the committed wallet state in SQLite; keep a backup of the vault and the passphrase. There is no seed-only recovery for a lost vault in this version.

```bash
node wallet/cli.mjs deposit --amount 25000 --vault .runtime/my-wallet.sqlite --mint https://YOUR_MINT --desk http://127.0.0.1:8765
```

This creates a locked on-chain mint quote, signs registration of its exact request/amount/key, and asks the configured desk to bind it. The desk independently reads the quote and decodes its receiving script through Core. The wallet returns a funding address only after binding succeeds. Use `list` to recover the operation ID, and `bind --id ID` to resume an interrupted registration. All commands use the same `--vault`, `--mint`, and `--desk` options.

After paying the request, submit its actual M16 statement and final proof to the configured intent through the dashboard. Native verification, payment binding and fresh active-chain checks must pass. In an explicitly isolated regtest configuration, the `admit-regtest` command instead submits a transaction ID and output index for a real Core check; this is never called ZK evidence.

```bash
node wallet/cli.mjs claim --id OPERATION_ID --vault .runtime/my-wallet.sqlite --mint https://YOUR_MINT --desk http://127.0.0.1:8765
node wallet/cli.mjs audit --id OPERATION_ID --vault .runtime/my-wallet.sqlite --mint https://YOUR_MINT --desk http://127.0.0.1:8765
```

The wallet commits its output secrets and blinding data before asking the desk for issuance. The desk checks wallet authorization, prior payment admission, the current chain, immutable quote identity and the mint's paid accounting. It persists the exact public request before forwarding it. The wallet then unblinds, requires DLEQ verification with the loaded mint keysets, checks the unspent states, and commits its proofs. `audit` decodes the token using those keysets and prints a token hash and amount rather than a bearer token.

An explicit `export --id ID --output FILE` writes a bearer token to a new file. It does not remove local proofs or make a payment. A custom `arkoor` melt is available in the isolated regtest profile. Receiving by swap is not implemented. Do not treat a previously exported copy as a second balance.

## Protected regtest issuance

After binding the Cashu quote, create a holder reserve with `protected-plan` and `protected-attach`. Set the plan's claim commitment to SHA-256 of the UTF-8 string `proof-grove/protected-issuance-intent/v1:` followed by the intent ID. The reserve must match the full quote amount. Confirm the reserve and admit the separately funded CDK quote before claiming.

New plans commit the claim, beneficiary script, amount, fee, keys and timing terms in the P2WSH funding script. Use the plan's complete descriptor in each signer. The generated PSBT supplies the public SHA-256 preimage needed by either spending branch. Existing V1 bundles retain their original descriptor for recovery. A newly registered protected issuance requires the V2 commitment. [BIP174](https://github.com/bitcoin/bips/blob/master/bip-0174.mediawiki)

```bash
node wallet/cli.mjs protected-claim --id OPERATION_ID --vault VAULT --mint MINT --desk DESK \
  --bundle RESERVE_BUNDLE --bundle-id PINNED_BUNDLE_ID --core-config CORE_CONFIG
node wallet/cli.mjs protected-audit --id OPERATION_ID --vault VAULT --mint MINT --desk DESK
```

`CORE_CONFIG` selects the independent loopback Bitcoin Core observer used by the Python holder tools. The wallet binds each note's P2PK guard to the reserve bundle and archives the mint keyset in the encrypted vault. The Bitcoin reserve is the settlement instrument. Export and standard Cashu melts are unavailable for protected notes. See [the protected profile](cashu-protected-profile.md) for claim consumption and the independent evidence.

For a cooperative melt, a regtest desk can configure `protected_melt_wallet` with the name of a dedicated Core wallet holding only the mint's reserve key. Core 31.0 needs `-txospenderindex=1`. The named wallet must have the matching descriptor for the issued reserve. Use the same vault, mint and desk options as at issuance.

```bash
node wallet/cli.mjs protected-melt-prepare --id OPERATION_ID --bundle RESERVE_BUNDLE \
  --core-config CORE_CONFIG --output cooperative.psbt --vault VAULT --mint MINT --desk DESK

node wallet/cli.mjs protected-melt-settle --id OPERATION_ID --bundle RESERVE_BUNDLE \
  --psbt holder-partial.psbt --vault VAULT --mint MINT --desk DESK

node wallet/cli.mjs protected-melt-status --id OPERATION_ID --bundle RESERVE_BUNDLE \
  --vault VAULT --mint MINT --desk DESK
```

The holder CLI generates the PSBT using the pinned bundle and its own Core observer. Between preparation and settlement, sign `cooperative.psbt` with the holder's external signing wallet using `SIGHASH_ALL` and leave the PSBT unfinalized. `settle` gives the desk permission to co-sign and broadcast that exact transaction. Treat `pending-spend` as provisional. `status` reports the active chain's spender and updates when a reorg removes or replaces it. The local holder recovery command remains available when the desk or mint signer is unavailable.

## Recovery and authorization

An exact request is immutable after reservation. On a lost mint reply, the desk uses NUT-09 to restore those original blinded outputs. Complete restoration can finish the request; partial restoration, changed outputs, an unrecognized issued balance, a changed mint, or a reorg stops it. A fresh mint call is possible only for the same original packet when restoration is empty and the provider still reports zero issuance. Upstream atomic quote accounting remains required; local SQLite cannot make a remote mint action atomic.

The SDK's prepared mint uses the amended NUT-20 wire signature, while its standalone public signing/verifying helpers in this pinned version implement the legacy message. The desk leaves wire verification to the mint and uses a separate application domain with the matched SDK primitives. That authorization covers the full prepared request and intent, including denominations and keyset IDs. It cannot be reused to change an output or register a different funding request. No mint signature is treated as wallet-verified until the wallet unblinds and checks it.

The mint's quote expiry is a payment-eligibility deadline, not a deadline for delivering a slow proof. Registration requires an unexpired fresh quote; proof admission has a separate seven-day window, shown alongside the payment expiry in the wallet summary. A proof for an eligible payment may arrive after the quote's deadline. The mint's paid accounting must still credit it; a chain proof cannot establish when a provider first detected a transaction. Already admitted funds remain issuable after the admission window, subject to fresh chain checks. This client handles one fixed deposit and issuance per quote; additional deposits need new quotes.

Also size `max_tip_lag` for the measured prover delay. The example configuration allows 144 blocks of proven-tip lag while requiring a fresh Core observation of the active payment block and proof tip. If the setting is omitted, the service retains its stricter 12-block default. A short deadline or lag limit can otherwise reject an expensive proof that took hours to produce.

`GET /api/cashu/operations` exposes public operation states and request hashes. The original payment receipt records admission; a separate `signatures_received` row records the provider response. These are not interchangeable with an Ark transaction, a reserve-solvency proof, or guaranteed redemption. Cashu remains a claim on its mint.

## Real isolated test

The test uses a new Bitcoin Core 30.0 regtest node with peer connections disabled, and CDK 0.18.3 with BDK. It does not use the fake-wallet backend. It mines task-owned regtest coins, pays a 25,000 sat quote, mines two confirmations, and proves that issuance is refused before admission. A proxy drops a successful mint reply, then a new wallet process recovers six verified proofs without a second issuance request.

Run `tests/run-regtest-stack.py` on Linux or within WSL. It requires installed wallet dependencies, Node 24, and the official CDK 0.18.3 Linux binary whose SHA-256 is `3a41003fcac0f54a164b6d9187c79ce05591947bb4b4b37c45a125fac813e3af`. Use a local Bitcoin Core 31.0 binary with `--bitcoind` or let the supervisor use its pinned Docker image. All nodes, wallets, and keys in this test are isolated regtest fixtures.

```bash
python3 tests/run-regtest-stack.py --protected --node /path/to/node \
  --cdk /path/to/cdk-mintd --bitcoind /path/to/bitcoind
```

The supervisor saves the holder's receipt at `.runtime/cdk-protected-report.json` and the certificate under the run's `protected-handoff/` directory. Match the certificate SHA-256 against the receipt. To recheck it independently with the mint stopped, pass the reported bundle ID and certificate digest to `node wallet/test-verify-protected-issuance.mjs CERTIFICATE BUNDLE_ID CERTIFICATE_SHA256`. The certificate contains the locked fixture notes and public keysets.

Use `--protected-cooperative` in place of `--protected` to run the cooperative wallet and reorg assertions on a fresh chain. Its receipt is `.runtime/cdk-protected-cooperative-report.json`.

The mainnet M16 proof check and this regtest issuance test establish different things. No live mainnet/testnet4 deposit-to-Cashu issuance or Ark rollover has been executed by this build.
