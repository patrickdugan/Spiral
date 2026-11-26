# Proof Grove

A local Ark and Cashu proof desk built from the Nova/BitVM payment contract used by Spiral’s In-and-Out Burger, and the payment-intent approach in Matt Vuk’s Bark/CDK and paid relay work.

[Open Proof Grove](https://patrickdugan.github.io/Spiral/proof-grove/).
The connected build uses your authenticated backend for current chainstate, native
proof checks and configured Ark/Cashu providers. Fixture examples are separate at
`demo/`. See [hosting](docs/hosting.md) and the [VPS deployment](deploy/README.md).
See the [protected Cashu profile](docs/cashu-protected-profile.md) for the
issuance-funded recovery fixture, recursive accounting and campaign evidence.

**This is a working proof admission, Cashu issuance/withdrawal, Ark refresh and offline exit prototype.** The encrypted wallet can obtain and verify Cashu ecash after a bound deposit is admitted, then redeem it into an Ark wallet. It reserves selected proofs and saves change secrets before submitting a payment, with no automatic HTTP replay. The caretaker checks Bark VTXO anchors with Core and reconciles delegated refreshes. An independent watcher advances saved exits using Core alone; the owner signs the final claim. Ark execution is restricted to regtest because the released refresh REST API lacks a signing-time fee cap. The hosted dashboard connects to the live testnet4 verifier and a separate persistent Ark/Cashu regtest backend; fixture examples remain under `demo/`. Testnet4 proof checks never fund the regtest mint.

## Run

The dashboard and proof service require Python 3.11 or newer and no Python dependencies. The optional Cashu wallet uses Node 24 and the pinned official SDK.

```powershell
cd proof-grove
python -m proofdesk serve
```

Open <http://127.0.0.1:8765>. To choose another port, add `--port 8766`. The service binds only to loopback and validates Host, Origin, and a custom header on mutations. Stop it with Ctrl+C.

To try the Cashu recovery verifier in the browser, start the local demo with a
recorded V3 payout and its observer pins.

```powershell
python -m proofdesk serve --port 8766 --protected-preview /path/to/preview.json
```

The preview manifest holds `receipt` (relative to the manifest),
`receipt_sha256`, `bundle_id`, `anchor_height`, and `anchor_hash`. The last
three fields come from the independently observed reserve and Core checkpoint.
The verifier calls OpenSSL on the original payout. Set `PROOF_GROVE_OPENSSL`
to the executable path if OpenSSL is outside `PATH`. Open **Cashu recovery**
to verify the recorded holder signature and mined witness or try the two
substitutions. Append `#protected-preview` to open Cashu recovery directly.
After verifying the original payout, download the evidence ZIP.
It contains the exact receipt and the recorded pins. To replay it, extract the
files and point `--protected-preview` at the extracted `preview.json`. For an
independent check, compare the bundle ID and checkpoint in that manifest with
your own observations. Live protected issuance and recovery use the
[wallet guide](docs/cashu-wallet.md).

To show the proof-backed payout alongside the holder-only exit, add
`--protected-funded-preview /path/to/funded-preview.json`. The status stays
pending until a publication arrives. With
`--protected-funded-statement-sha256 SHA256`, the desk also requires the exact
withdrawal statement chosen by the observer before it offers any downloads.
Create the descriptor after the
recipient's `verify_withdrawal_evidence.py` in the ZK Rusto repository accepts
the ZIP and replays the payout in walletless Core. Use schema
`proof-grove/funded-preview/v1` and the fields `archive`, `archive_sha256`,
`verification`, `verification_sha256`, and `statement_sha256`. Keep the ZIP
and verification receipt beside the descriptor and use their filenames in
`archive` and `verification`. The service checks both file hashes and serves
the original ZIP and the recipient verification receipt. This panel displays
the local verifier's result. The recipient CLI can repeat the verification.

To include the already verified issuance and refusal downloads, add
`--protected-evidence-preview /path/to/recovery-evidence.json` to the local
demo. The manifest uses schema `proof-grove/protected-recovery-evidence/v1`,
the common `claim_id`, `holder_txid`, and `holder_wtxid`, and two objects named
`issuance` and `refusal`. Each object carries `file` and `sha256` for its ZIP
beside the manifest. Use the issuance audit and the walletless funded refusal
archive from the evidence matrix. The demo verifies the archive pins and
checks that the enclosed receipts refer to the same holder transaction. The
downloads include instructions to repeat the underlying verification.

The `refusal` object can also carry `verification` and
`verification_sha256` for the independent recipient receipt beside the
manifest. The preview checks the receipt against the claim, withdrawal statement,
archive and replay results before displaying the block count and offering
the original receipt for download.

To show a registry accounting snapshot, add an `accounting` object with
`file`, `sha256`, `registry_sha256`, `blocks_sha256`, `tip_hash`, `tip_height`
and `nova_verifier_key_sha256`. Use the independently verified registry ZIP
from the evidence matrix. The registry pin is the canonical root digest
from its audit. The block pin is the byte digest from the walletless replay.
Cashu Recovery shows the archived regtest checkpoint and the audited reserve,
outstanding claim and pending issuance totals. The download includes the
Nova proof and materials for repeating the native verification and block replay.

```powershell
python -m unittest discover -s tests -q
node --check web/app.js
python -m proofdesk demo --case replay
```

The browser smoke script uses an existing Playwright and Chromium installation:

```powershell
$env:PROOF_GROVE_PLAYWRIGHT = 'absolute/path/to/playwright'
$env:PROOF_GROVE_BROWSER = 'absolute/path/to/chrome.exe'
node tests/browser-smoke.cjs
```

## What works

- Eight deterministic cases: Cashu and Ark acceptance; deposit redirection/reuse; wrong amount; wrong script; reorg; stale observation; an operator report presented as proof.
- An independently implemented M16 PAY1 parser compatible with the public 1,292-byte statement fixture; a SHA-256-pinned external `kan-payment-gate` invocation; program, recursion, genesis and Nova key pins; exact gate/payment cross-checking.
- A read-only Bitcoin Core observer that checks both the payment block and proof tip against the active chain, rejects initial sync and mid-observation tip changes, and enforces proof freshness.
- Immutable payment intents, **a unique deposit script per intent**, exact satoshi amounts, and atomic SQLite reservations plus a durable prepared outbox. Exact retries return the same request. A beneficiary is fixed before a proof arrives.
- Ark refresh/exit planning from chain height, an exit confirmation budget, package-validation status, operator availability and a fee cap. Every plan is explicitly unexecuted.
- Connected Bark VTXO monitoring and opt-in regtest delegated refresh: durable input reservations, a preflight fee limit, lost-reply/restart recovery, successor value and expiry checks, and independent Core anchor confirmation/reorg checks. Bark performs Ark signature and ownership validation.
- Private presigned exit packages, exact CPFP fee checks, and an independent Core-only regtest broadcaster/watcher. Saved waves survive a lost reply and restart, observe timelocks and reorgs, and stop for an owner claim. The native test confirms that claim with the Ark server offline.
- A NUT-30 Cashu issuance adapter with immutable quote/script/amount/key binding, full-request wallet authorization, persisted blinded outputs, NUT-09 recovery and a separate encrypted SDK wallet. Provider quote responses retain the `operator-report` evidence level.
- Regtest Cashu-to-Ark withdrawals through the locally ported Bark/CDK processor: saved quotes and fee limits, durable proof reservations, single-attempt transport, lost-response change recovery and DLEQ checks. Recipient VTXOs and their refresh anchors are checked separately from the mint's paid report.
- A redacted public receipt export whose exact bytes have a CIDv1 raw SHA-256 identifier. No Filecoin deal is implied or submitted.

The demo starts each case in an isolated in-memory ledger. Connected mode uses a persistent `live` database. Regtest uses a third, isolated namespace that accepts only real regtest Core observations, never a fixture or mainnet transaction. Tests exercise restart recovery, contention and rollback on disk-backed SQLite.

## Configure native verification

Copy `config.example.json` to `config.local.json` (ignored by Git). Set `gate.argv` and the SHA-256 of the actual executable. Supported command forms:

```json
["/absolute/path/to/kan-payment-gate"]
["wsl.exe", "--exec", "/root/kan-gate/kan-payment-gate"]
```

The supplied policy pins come from the documented **historical mainnet replay**, not a current deployment policy. Independently choose current chainwork and confirmation floors, registered receiving scripts, trusted program pins and an executable build. The bundled statement describes a 940,000 sat payment at block 975,067; it is public historical compatibility data. It is not an unclaimed deposit for this application. No final proof is bundled.

```powershell
python -m proofdesk verify --config config.local.json `
  --statement fixtures/m16-mainnet-statement.bin --proof /path/to/final-proof.bin
```

`verify` checks proof bytes and policy, then prints evidence. It does not reserve or settle a payment. The wrapper is invoked as a separate process; the upstream verifier is not vendored or relicensed.

## Configure a connected payment desk

The connected dashboard additionally needs your own synced local Bitcoin Core, its RPC password in the environment variable named by `core.password_env`, and preconfigured intents. Scope the Core RPC credential to `getblockchaininfo`, `getblockhash`, and `getblockheader`. For example:

```json
{
  "id": "my-deposit-001",
  "network": "mainnet",
  "script_sha256": "SHA256_OF_A_UNIQUE_RECEIVING_SCRIPT",
  "amount_sats": 25000,
  "beneficiary": "LOCAL_SETTLEMENT_TARGET_REFERENCE",
  "rail": "cashu",
  "expires_at": 1800000000
}
```

Put the intent in `intents`, register its unique script in `policy.scripts`, then run:

```powershell
python -m proofdesk serve --config config.local.json
```

Choose the intent and upload its M16 statement and final proof. Native verification and a fresh Core observation must both pass before the ledger prepares a request. A browser-supplied `verified` flag or receipt cannot bypass the gate. No endpoint accepts a new recipient or arbitrary executable command. Unknown, expired, underpaid, overpaid, wrong-network, wrong-script, stale and reorged submissions fail closed.

The active-chain check observes a moment in time. The Cashu bridge rechecks it before issuance. A proof of inclusion does not prove a deposit is still unspent or available as a reserve; the mint's own backend still accounts for its wallet.

Optional `cashu_url` and `bark_url` configure the read clients. `bark_bearer_env` names a local environment variable rather than storing its value. Mint info and local Bark history are available from the dashboard. `GET /api/cashu/quote?method=onchain&quote=...` reads a quote at the configured mint. Keep quote IDs private. The raw Bark history view is local and may contain payment metadata; it is never included in the public archive.

## Use the proof-gated Cashu wallet

See the [wallet and integration guide](docs/cashu-wallet.md) for installation, configuration, the full flow and recovery semantics. From `wallet/`, install the exact dependencies with `pnpm install --frozen-lockfile --ignore-scripts`. The SDK version is 4.13.1; the lockfile pins its dependencies.

The wallet creates a NUT-20-locked on-chain quote, binds its unique receiving script and amount through the desk, and returns a deposit address only after binding succeeds. Once the payment passes the configured admission path, the wallet can request blind signatures. It commits its encrypted blinding data before the request, then unblinds and verifies the response. It never asks the desk to store bearer proofs or private keys. The mint must implement NUT-09 recovery.

Actual end-to-end testing used CDK 0.18.3 with its BDK/Core backend: a 25,000 sat regtest deposit, two confirmations, proof admission, one dropped issuance reply, a restarted wallet, recovery of six DLEQ-verified proofs, and no second issuance. This test used real cryptographic Cashu proofs and valueless regtest coins. It did not use an M16 proof or execute an Ark transfer. See [the recorded result](docs/cdk-integration.json).

Reproduce on Linux or in WSL with Docker, Node 24, the pinned official CDK binary, and installed wallet dependencies:

```bash
python3 tests/run-regtest-stack.py --cdk /absolute/path/to/cdk-mintd-0.18.3-x86_64 --node /absolute/path/to/node
```

The foreground supervisor creates a fresh isolated chain and mint, uses public fixture keys, runs the test, and stops only its own labelled containers and mint process. No existing wallet is selected. It retains local test artifacts under `.runtime/`. On WSL, keep the supervisor running; closing the last WSL process can stop its Docker services.

The [Cashu-to-Ark withdrawal guide](docs/cashu-ark-withdrawal.md) covers `ark-quote`,
`ark-pay`, `ark-status` and the combined native supervisor. It extends the flow
through a separately funded Bark payment backend, recipient refresh and an
optional offline exit of the exact redeemed VTXO. The source port retains its
licenses and pins upstream revisions in `integrations/bark-processor`.

The [combined native result](docs/cashu-ark-integration.json) also covers a lost
melt response and the [exact recipient's offline exit](docs/cashu-ark-exit-integration.json).
The 25,000 sat test deposit ended as 15,000 sats of Cashu change and a 9,165 sat
on-chain owner claim, plus 190 sats of refresh and 645 sats of claim fees.
Additional public-fixture coins paid CPFP fees. This is a regtest demonstration;
the historical mainnet M16 proof check remains separate.

## Trust reduction and its limits

“Rolling” is interpreted here as Ark VTXO refresh/rollover. A proof cannot cancel an expiry or extend an existing VTXO. Independent watchers can use chain height and validated, presigned exit packages to reduce manual operation and dependence on one always-online wallet. They still need timely broadcast and enough fee/confirmation runway. The planner accepts a caller’s validation status; it does not validate an Ark exit package itself.

Proof admission removes a discretionary manual payment-approval step for the stated policy. It does not make a Cashu mint noncustodial, prove all liabilities or reserves, stop a signing-key owner from overissuing, enforce database integrity against a machine administrator, or enforce redemption. A bonded BitVM contract would additionally need actual funded targets, challenge incentives, liveness, script validation and observed release; that enforcement is absent here.

The connected Ark caretaker delegates signing to Bark, with execution restricted to regtest. Its [exit watcher](docs/ark-recovery.md) uses only saved transactions and Core; Bark and its server can be unavailable during broadcast. The owner still signs the final claim. The Cashu melt establishes mint redemption and wallet change; the recipient independently validates Ark reception. The desk's M16 policy gates its own forwarding, while direct CDK calls use CDK's paid-quote policy. There is no independent Ark script verifier, Payjoin negotiation, Filecoin uploader or direct p2pool sharechain adapter in this version. The outbox and CID remain integration inputs for that work.

## Provenance and next integration

See [architecture](docs/architecture.md), [source manifest](docs/sources.json), [Matt repository scan](docs/matt-repository-scan.json), [fixture provenance](fixtures/provenance.json), and the [verification record](docs/verification.md).

Matt’s GitHub handle is `mvuk`. The scan enumerated 37 repository metadata records and inspected selected relevant READMEs. The exact November hackathon project was not confirmed. His current Bark processor and paid relay writes are verified baselines; his old misspelled processor repository describes an unfinished template. The apparent event is [Nut November](https://nutnovember.org/), November 1–27, 2026; no registration or submission was made.

See the [Ark caretaker guide](docs/ark-caretaker.md), [refresh test](docs/ark-integration.json), [exit recovery guide](docs/ark-recovery.md), and [offline exit/claim test](docs/ark-exit-integration.json). Production work still needs a signer-enforced refresh fee budget, mint-side proof-policy enforcement, reserve accounting and deployment review. The combined regtest flow uses BDK deposits and separate Bark liquidity; it does not establish a full mainnet M16-to-Cashu-to-Ark flow or production custody guarantees.
