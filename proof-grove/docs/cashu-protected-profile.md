# Protected Cashu profile and campaign evidence

The protected prototype gives a holder a Bitcoin recovery path when the claim is issued. At issuance the wallet verifies that a confirmed reserve outpoint pays the agreed holder-controlled script. In the November 23 melt-funded fixture, CDK first accepted and spent an existing Cashu bundle to fund the recovery outpoint. The mint could refuse that initial melt. After funding the holder could exit independently in both models.

## PG-ZK-01 — exact melt-funded redemption

The archived execution receipt identifies the funding outpoint `51bf73de53a364d423bd8ec05ac2aee1a8b28d34853386c7510fcde87575bd16:0`, a 24,000-sat reserve and payout transaction `098f615affde586e827d5167b86382a2a2c490c5e5c5f5806183bce5a012eceb` paying the holder 23,750 sats after six blocks. The remaining 250 sats were the payout fee. The recorded Cairo execution matched 24 public output words and refused early spending and a changed prevout amount. Its receipt explicitly records that no STARK was generated in that run.

The paired Shinigami receipt records a 25,000-sat issuance proof and a 24,750-sat payout proof from a separately funded reserve. The proof hashes are `979bc9a9f0e9b24f4486b638c7e05aa05d33bc2b508b34308d89955f131a86fb` and `350b8fe97e02ee2ef90880a18d83b43ad0790e8cf7c92c1ea223b569deb9df6c`. The 24,750-sat proof cannot satisfy the 23,750-sat statement. The other archived 23,750-sat regtest receipts also carry different funding and payout txids.

With the original proving bundle and case directory on Linux, the exact case gate runs as follows.

```bash
python3 proof-grove/scripts/audit-exact-melt-stark.py \
  --runner /path/to/shinigami-cpu-pilot/benchmarks/shinigami/run.py \
  --case /path/to/exact/redemption-case --check-only
python3 proof-grove/scripts/audit-exact-melt-stark.py \
  --runner /path/to/shinigami-cpu-pilot/benchmarks/shinigami/run.py \
  --case /path/to/exact/redemption-case --out /path/to/new/evidence-directory
```

A pre-existing candidate can be supplied with `--existing-proof`. The gate checks the archived case and tool pins, then archives the case statement, proof, verifier transcript, timings, and an independent verification receipt. The public-memory mutation loop changes every exposed word. A separate source audit is required to establish which public words constrain which semantic fields. For delivery, the verifier must bind the network, canonical chain anchor, exact funding transaction and output, reserve script and amount, holder authorization, delay, payout transaction and destination, payout amount, change and fees. A Bitcoin inclusion proof needs a separately trusted or verified canonical tip to resolve reorgs.

## PG-ZK-02 — Nova accounting

`integrations/cashu-nova` folds a uniform Pallas/Vesta step. The public state contains four domain-separated Poseidon trees (reserve, intents, live claims, spent claims), three integer balances, sequence, journal and ledger context. The public verifier starts at a pinned genesis or independently accepted checkpoint and uses the expected final state and exact step count. The journal binds the previous journal root, context, sequence, operation, identifiers, amounts and admission-evidence digest. Applications must provide those evidence records and make witness data available for independent replay.

| Step | Authenticated state updates |
| --- | --- |
| Register | Require vacant reserve and intent leaves. Bind the funded outpoint and its amount to one pending intent. |
| Issue | Open the pending intent at its exact amount and reserve, leave an intent tombstone, and create a vacant live claim whose spent slot is empty. |
| Split | Open and consume a live claim, set its spent leaf, and create two distinct positive claims with the same reserve binding and conserved value. |
| Swap | Open and consume one live claim, set its spent leaf, and create another claim at the same amount and reserve. |
| Redeem | Consume a live claim once and decrease its reserve and total liabilities by the exact amount. The reserve entry remains occupied, including at a zero balance. |

The circuit enforces Boolean operation selection and Merkle directions, full 256-bit identifier commitments via two range-checked limbs, authenticated empty leaves, satoshi bounds, and reserve coverage for both pending issuance and live liabilities. The eight-bit tree route is a fixture limit. Colliding occupied slots cause refusal, and production-scale deployment needs a tree design that handles collisions and tombstone growth.

The accounting proof covers the declared protected ledger. A coordinator must independently check credible Bitcoin Core or chain-verifier evidence for unspent funding and mature, confirmed withdrawals. The circuit binds evidence digests and leaves Bitcoin consensus, Cashu DLEQ, and holder signing to the admission layer. A mint with signing keys can sign additional bearer notes outside the ledger. A protected wallet must verify the canonical protected checkpoint, live claim membership, funding script, individual collateral balance, and the certificate tying that note bundle to its reserve. Missing or stale evidence fails admission. A public enumerable or witness-available protected issuance journal allows auditors to reconstruct that ledger. Completeness for a mint's external bearer liabilities cannot be deduced from an authenticated subset of the ledger.

The fixture demonstrates accounting splits and swaps. A holder assigned only a fractional bookkeeping claim has no independent ability to spend part of a Bitcoin UTXO. Protected transfers and splits require the current holder to roll the whole input into fresh reserve outputs for the new holders, or an independently enforceable transaction graph that creates those outputs. Each recipient waits for its own usable reserve and verifies its own key and recovery delay.

Run the R1CS replay controls, generate the compressed fixture proof, and verify it in a separate process.

```bash
cd proof-grove/integrations/cashu-nova
cargo +stable test --locked
cargo +stable run --locked --release -- prove-demo /path/to/new/proof-directory
cargo +stable run --locked --release -- verify-demo /path/to/proof-directory
```

Both proof commands print the public-state and verification-key identifiers. The separate verifier accepts only the fixture's expected transition chain. The witness checks reject old Merkle paths, reserve reuse, repeated issuance and redemption, overissuance against an intent, invalid split arithmetic, a duplicate output ID, spent ID reuse, and a substituted reserve.

The local run used 42,043 constraints per step. It folded five steps in 2.37 seconds and compressed them in 18.16 seconds, with 413,688 KiB peak prover RSS. A separate verifier process checked the 11,504-byte compressed proof in 0.314 seconds after local key setup. The final public state declares 10,000 sats reserved and 10,000 sats outstanding. The proof was rejected under a different context anchor and a changed step count.

The same verifier accepts a declared regtest journal through `prove-journal PROOF_DIR JOURNAL` and `verify-journal PROOF_DIR JOURNAL EXPECTED_SHA256`. The auditor supplies the expected SHA-256 from its own pinned journal. Each event names a funding txid, vout, exact integer amount, evidence digest and operation. Reserve IDs are derived from the genesis and actual outpoint, so changing a quote intent cannot register the same Bitcoin coin twice. The replay derives the ledger context from the genesis and mint profile, then computes the initial root, event count, final root and root before the last event.

`scripts/protected-fixture-evidence.py journal` prepares the journal from the holder's regtest receipt. For the CDK run, `--issuance-certificate` adds the independently checked DLEQ receipt and the pinned certificate digest to the issuance entry. The builder requires that the reserve bundle, amount, locked-note digest and request digest agree. Run the certificate verifier separately before admitting that evidence. Nova verifies accounting and commits to the admission records. Verification of the Cashu signatures and Bitcoin transactions occurs outside the circuit.

The protected CDK journal ended with zero reserve and zero outstanding claims. Nova produced an 11,504-byte proof with 404,920 KiB peak prover RSS. The separate verifier checked the proof in 0.298 seconds after key setup. Changing the certificate bytes caused journal admission to fail before proving.

To rebuild the protected CDK journal, first reproduce the issuance fixture in [the wallet guide](cashu-wallet.md) and verify its certificate. From `proof-grove/`, point `RECEIPT` and `CERTIFICATE` at those files and `RUN` at a new directory.

```bash
JOURNAL_SHA=$(python3 scripts/protected-fixture-evidence.py journal "$RECEIPT" "$RUN" \
  --issuance-certificate "$CERTIFICATE")
cargo +stable run --locked --release --manifest-path integrations/cashu-nova/Cargo.toml -- \
  prove-journal "$RUN/proof" "$RUN/journal.json"
cargo +stable run --locked --release --manifest-path integrations/cashu-nova/Cargo.toml -- \
  verify-journal "$RUN/proof" "$RUN/journal.json" "$JOURNAL_SHA" > "$RUN/independent-verifier.json"
```

For an independent audit of an existing proof, obtain the expected journal SHA-256 from its trusted evidence manifest. The proof verifies the folded `register`, `issue` and `redeem` steps for that journal.

## PG-ZK-03 — Bitcoin claim consumption

Each protected claim controls one full outpoint. The holder's wallet stores the descriptor, funding transaction and outpoint, key and sequence, chain context, claim-bundle commitment, expected amount, and mint profile identity. A certificate binds these fields to issuance and appears in the accounting journal. The mint's on-chain cooperative redemption needs the holder signature and uses the same outpoint as the unilateral CSV exit. The holder only signs an exact authorized transaction with `SIGHASH_ALL`, covering beneficiary, amounts, change and fees. Confirmation consumes the outpoint. A replacement before finality remains subject to the same consensus exclusivity, so clients keep it pending and recompute active-chain state after a reorg.

The fixture descriptor is `wsh(and_v(v:pk(H),or_i(pk(M),older(6))))` with distinct holder and mint keys. It requires both keys on the cooperative branch and only the holder key when the CSV branch matures. The holder is always required. This profile uses block-based [BIP68](https://github.com/bitcoin/bips/blob/master/bip-0068.mediawiki) and [BIP112](https://github.com/bitcoin/bips/blob/master/bip-0112.mediawiki).

The standalone Bitcoin Core 31.0 fixture confirmed a 24,750-sat payout from a 25,000-sat reserve after six blocks. The test checked concurrent broadcasts, a signature-invalid substituted beneficiary, early payout, replay after confirmation, and invalidation of the payout and funding blocks. Its two script branches are tested with separate signing wallets.

The protected CDK fixture funds the holder reserve before issuance. It pays the mint quote with a separate test payment. CDK 0.18.3 signs six P2PK notes worth 25,000 sats. Their lock key comes from Cashu hash-to-curve over a domain and the pinned reserve bundle ID, with no known signer and no refund branch. The wallet verifies the lock after unblinding and keeps the notes in `protected-issued` state. Proof Grove checks the reserve against Core and assigns the outpoint at most once in its issuance database. A protected recipient also needs its own copy of the reserve bundle and trusted mint keyset pin.

The CDK control submits these inputs to the stock NUT-30 melt endpoint. CDK rejects the spending condition and reports the inputs unspent. A separate process verifies the six DLEQ proofs against cached public mint keys while the actual CDK process is stopped and rejects a changed note secret. The holder then spends the confirmed reserve with its own signing wallet. The certificate is a regtest artifact. Its DLEQ check attests to the keysets pinned by the accepted fixture certificate. Application code must establish those pins against a trusted mint identity before accepting an externally supplied certificate.

The holder uses the Proof Grove CLI with a loopback Bitcoin Core configuration. `protected-plan` saves the two public keys, amount, exact payout, fee and delay, then returns the funding address and plan ID. `protected-attach` verifies the confirmed transaction output before saving its bundle. Keep the plan ID and resulting bundle ID through a trusted channel. `protected-status` checks whether the coin is unspent, pending spend, consumed, or orphaned. `protected-psbt` exports either branch for external signing and includes the exact witness UTXO and witness script. A holder can export before maturity. `protected-check` checks `SIGHASH_ALL`, both branches' exact output and fee, and the active Core mempool result. The signing wallet and broadcaster are separate from these commands.

```bash
python3 proof-grove/tests/protected-reserve-regtest.py --bitcoind /path/to/bitcoind
```

NUT-07 lets CDK report and serialize proof states inside the mint. NUT-11 enforces P2PK conditions within a compliant mint. NUT-12 verifies a blind signature against a mint key. NUT-30 provides on-chain quotes and leaves the mint free to select its payment inputs. Protected redemption uses a dedicated route and the issued reserve as its input. Lightning melt needs a protocol that atomically binds Lightning settlement to that Bitcoin claim. [NUT-07](https://github.com/cashubtc/nuts/blob/main/07.md), [NUT-11](https://github.com/cashubtc/nuts/blob/main/11.md), [NUT-12](https://github.com/cashubtc/nuts/blob/main/12.md), [NUT-30](https://github.com/cashubtc/nuts/blob/main/30.md), [CDK](https://github.com/cashubtc/cdk)

The protected melt routes require the original issuance record and reserve bundle. The desk builds a fresh PSBT and copies only the supplied holder signature. It asks a dedicated mint signing wallet to complete the transaction, then checks the exact Bitcoin transaction through Core before broadcasting. The holder's separate CLI builds its signing PSBT from the local reserve pin. The beneficiary is fixed at issuance. A new beneficiary requires a separately funded and authorized reserve.

The desk derives claim consumption from Core's live UTXO set, mempool, and transaction-output spender index. It treats the same cooperative payout as an idempotent retry, reports a competing holder spend, and invalidates a settlement when its block leaves the active chain. If the funding block leaves the active chain, the pinned funding evidence is unavailable. The outpoint remains eligible under Bitcoin consensus if the funding transaction is later reconfirmed, and the app requires fresh funding evidence for that new block. [Bitcoin Core `gettxspendingprevout`](https://bitcoincore.org/en/doc/31.0.0/rpc/blockchain/gettxspendingprevout/)

The cooperative test archives both signed payouts and the three transaction-inclusion proofs. Core verified each inclusion while its block was active. The cooperative payout confirmed before the six-block holder delay; the holder payout confirmed at the first eligible height on the replacement chain. The same reserve had one confirmed spender on each history.

## PG-ZK-04 — BitVM3 target

The M14 example sizes a fixed settlement record, using the existing BLAKE3 and Boolean arithmetic gadgets. The record commits the network via genesis, chain anchor, old and new roots, claim ID, exact funding outpoint, reserve and beneficiary script hashes, holder authorization commitment, payout txid and wtxid, heights and CSV sequence, and reserve, payout, change and fees. The verifier checks the challenge digest, state change, block-based delay, integer ranges and exact conservation. The challenger needs the authenticated expected digest as an input. In a deployment it must be pinned by the setup and derived from the same verified proof statement, or the check would only enforce consistency with a digest chosen by the attacker.

### Record disclosure bond

The same-chain regtest fixture starts after the holder payout. It independently verifies the Nova journal, constructs the exact settlement record, checks it in M14, and confirms that its payout anchor is active on the Core node where it funds the bond. The setup pins the 404-byte settlement record by SHA-256 and BLAKE3, including its claim, network, chain anchor, old and new journal roots, and reserve and payout transactions. Each bond also commits a fresh nonce, two setup keys, beneficiary scripts, windows and amounts. The setup signatures fix the collateral outpoint, successor outputs, recipients and fees before funding.

| Transaction | Bitcoin rule |
| --- | --- |
| Challenge | The registered challenger holds the jointly signed transaction that moves the 50,000-sat bond to a 49,500-sat dispute output. Timely confirmation spends the output needed by the operator's reclaim. |
| Uncontested reclaim | 49,500 sats to the operator from the funding output at least 144 blocks after its confirmation. |
| Record disclosure | 49,000 sats to the operator from the dispute output when the witness supplies all 404 bytes. Script checks the sizes and SHA-256 hashes of six ordered chunks. |
| Response timeout | 49,000 sats to the challenger from the dispute output at least 24 blocks after the active challenge confirmation. |

The challenger needs the independently anchored record digest, proof and verifier pins, the fully signed challenge and timeout transactions, their committed destinations, and a Core observer. The pre-signed routes require one honest setup signer to withhold any alternative authorization. The fixture generates both setup keys in one process. It returns the four authorized transactions and no setup keys. A live protocol needs distinct signers and a durable handoff before funding.

A CSV delay sets an earliest confirmation height. If a challenge has yet to confirm when the reclaim becomes eligible, the two can race for the same output. A late disclosure can likewise race the matured timeout. A challenge reorg resets the response clock to the active confirmation height. The fixture uses fixed fees on an isolated chain. A deployment needs confirmation margins and a fee-bump policy before relying on those windows. [BIP68](https://github.com/bitcoin/bips/blob/master/bip-0068.mediawiki), [BIP112](https://github.com/bitcoin/bips/blob/master/bip-0112.mediawiki), [BIP143](https://github.com/bitcoin/bips/blob/master/bip-0143.mediawiki)

The opener publishes the record in five 80-byte items and one four-byte item under Bitcoin Core's standard P2WSH relay policy. The challenger checks that the script commits those ordered chunk hashes for its agreed record before signing. [Bitcoin Core standardness limits](https://github.com/bitcoin/bitcoin/blob/v31.0/src/policy/policy.h)

The holder reserve pays under its separate cooperative and CSV branches. Both bond beneficiaries use independent test wallets. Bitcoin enforces signatures, the exact record opening, and the bond timeouts. The Nova and M14 checks run off-chain. The bond has no BitVM3 fraud-witness branch for incorrect computation. A complete dispute requires authenticated garbling, a bound rejection witness and its on-chain spend path. M14's current proof verifier covers SP1's wrap format. Direct verification of Shinigami's Cairo STARK needs separate composition. [BitVM3 paper](https://bitvm.org/bitvm3.pdf)

Run the same-chain fixture from `proof-grove/` with a Linux Bitcoin Core 31.0 binary, the pinned CDK and Node from the wallet guide, and Python `cryptography` with secp256k1 available. Build `proof-grove-cashu-nova` in `integrations/cashu-nova` and `cargo +stable build --locked --release --example cashu-settlement` in the verifier repository's `integrations/bitvm3-nova/m14/circuit`.

```bash
RAYON_NUM_THREADS=4 python3 tests/run-regtest-stack.py --protected \
  --bitcoind "$BITCOIND" --cdk "$CDK" --node "$NODE" \
  --collateral-nova "$NOVA_BIN" --collateral-m14 "$M14_CASHU_SETTLEMENT_BIN"
```

The run's `protected-handoff/collateral` directory contains the holder receipt, accounting proof and independent verifier transcript, M14 record and result, and all three collateral cases with signed transactions and inclusion proofs.

The local measurement was 71,477 non-free gates for 3,488 input bits and about 1.14 MB at 16 bytes per gate before protocol overhead. The example rejected changes to each of the 20 record fields under the pinned digest. It also rejected an early payout and an incorrect fee after recomputing the digest, which exercises the arithmetic beyond the commitment check.

Build a regtest settlement record from the holder receipt and the independent Nova journal verifier with `scripts/protected-fixture-evidence.py settlement RECEIPT RECORD NOVA_VERIFIER`. Supply `--issuance-certificate CERTIFICATE` for the protected CDK run. The M14 example `cashu-settlement RECORD EXPECTED_BLAKE3` uses the challenger-supplied expected digest. The executable's `--digest RECORD` mode calculates a digest for offline preparation. The two roots in this record come from the Nova journal replay before and after redemption. Core's funding and payout inputs remain fixture observations. The linked record passed the same 20 public-field controls and two arithmetic controls at 71,477 non-free gates.

## Measurement and evidence

The paired Cashu benchmark cost $0.2487. The issuance and 24,750-sat payout prover stages took 240.505 seconds and 257.603 seconds and peaked at 45,576,180 KiB and 46,434,300 KiB. This was a 16-thread CPU run on Hyperstack, hosted on an A100 VM. The available WSL machine reported approximately 15 GiB RAM and zero swap. Any new paid run needs ready inputs, approved spend and a bounded lease. Completion ETA is unknown.

| Evidence | Native execution | Cryptographic verification | State-transition soundness | Bitcoin settlement |
| --- | --- | --- | --- | --- |
| Archived paired benchmark | Reported on Core and CDK | Archived verifier receipts for issuance and 24,750-sat payout | Local duplicate issuance control | Historical holder payout after reserve funding |
| Exact 23,750-sat melt-funded case | Archived Cairo 24-word execution | STARK bytes and independent transcript require recovery or fresh proving | CDK rejected reuse of the six source proofs in the archived run | Historical offline payout after cooperative funding |
| Protected reserve fixture | Proof Grove CLI and Bitcoin Core 31.0 | Bitcoin Script signatures and timelock enforced by Core | Concurrent spends, replay and reorg controls | 24,750 sats on regtest with the mint signer unloaded |
| Protected CDK issuance and holder exit | CDK 0.18.3 and Bitcoin Core 31.0 | Offline DLEQ and changed-secret control | Unique app reserve assignment and stock melt rejected with notes unspent | Holder spent the pre-issued reserve after the CDK process stopped |
| Protected cooperative melt | Proof Grove wallet, desk, and Bitcoin Core 31.0 | Exact holder `SIGHASH_ALL` plus mint co-signature, verified by Core | Both branches compete for one issued outpoint. Status follows active confirmations and replay. | Cooperative and holder payouts were confirmed on competing regtest histories |
| Nova accounting fixtures | Native journal replay and constraint tests | Compressed Nova proofs with a separate verifier | Authenticated accounting, canonical outpoints and replay checks | Funding and payout linked to Core records, with a separately verified CDK issuance certificate in the protected journal |
| BitVM3 binding fixture | Boolean circuit, 71,477 non-free gates | BLAKE3 binding under a supplied digest | Full proof-verifier composition remains open | The disclosure bond can be exercised on the anchored holder chain |
| Settlement record disclosure bond | CDK issuance, Nova and M14 on the same holder fixture | Core verified setup signatures, exact record hash and CSV rules | Pinned record ties the bond to Nova roots and an active payout anchor | Reclaim, response timeout and exact disclosure paid from separate collateral on regtest |
