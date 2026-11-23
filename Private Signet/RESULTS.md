# Private Signet and Keyless-CHECKSIG A/B: results

Runs of 2026-11-23. Local runs used WSL Ubuntu 24.04. Every transaction ID and
block hash below is in the receipts under [evidence/](evidence/).

Nothing here was run on a public network. Keyless-CHECKSIG is enforced only
by the patched regtest node started with `-keylessresearch=1`.

## Phase 1: the private Signet works

| Step | Result | Receipt |
|---|---|---|
| Network | challenge `2102c181…3afac` (P2PK of the disposable signer); standard Signet genesis `00000008…1ef6` (shared by every Signet); Core `/Satoshi:31.1.0/` | `evidence/signet/lab-state-public.json` |
| First signed block | height 1, `0000031ab5ebada2560dbd6fb178853aca48078157a9cf32a6b4e56facf193a1`, 11.9 s | `…083526006911Z-mining.json` |
| 101 blocks | tip `00000238294abc67a468f9d3438383426987a5a4349101b449b2a96de56181a3` | `…085127669599Z-mining.json` |
| Agreement at 101 | miner = observer on genesis, height, all 102 block hashes; chainwork `…1d6a7ff8` | `…085139333541Z-agreement.json` |
| Wallet transaction | fresh wallet paid 1.0 sBTC: txid `b2b803e817d8ab317510e7f37fa67874ae53c3538e7675732b0c3721184f8483`, block `000001f7…ae41` (height 102); UTXO visible on both nodes | `…085306275035Z-wallet-transaction.json` |
| Final agreement | height 106 on both, chainwork `…1edba45c` | `…085407942567Z-agreement.json` |

Six defects in the scaffold stopped it from producing a block; the
[README](README.md#defects-fixed-in-the-scaffold) lists them. Two of them
reproduced exactly:

- **Bare-P2PK challenge.** Without the added `pk()` descriptor, the official
  miner printed `PSBT signing failed` and mined nothing
  (`evidence/signet/signing-control.txt`).
- **Backdated blocks.** The reward wallet credited only the 24 coinbases
  timestamped after its birth time, so "Insufficient funds" appeared at
  height 101.

Two blocks, 103 and 104, carry a first DLC attempt that crashed after
mining: `gettxout` returns nothing for a spent coin, which the harness then
failed to parse. That run left no receipt. The receipted run below used fresh
funding.

## Vanilla DLC confirmed on the private Signet (arm A, stock consensus)

| Item | Value |
|---|---|
| Construction | Taproot output, NUMS internal key, single leaf `<A> CHECKSIGVERIFY <B> CHECKSIG`; BIP340 adaptor pre-signatures per outcome, encrypted to the oracle's attestation point |
| Funding | `f6aaf8661078b2fc2f45a719ae6e769eb5f7a7356b7fb1343ad303a7fb7d06bd`:1, 1,000,000 sats |
| Outcome | `ALICE_WINS`; oracle attestation scalar decrypts Bob's pre-signature |
| Settlement (CET) | `e068b8a41196af29b660ceefd0c1232698358fb313dbc73c4f8a2510e53d67d9`: 612 WU, 153 vB, 229 witness bytes |
| Relay | `testmempoolaccept` allowed on miner and observer; broadcast with `sendrawtransaction` |
| Confirmation | block `000000a80c15715b0fc4657220cc09505342cd0140b4e8f74c970af41f357084` (height 106); payout UTXO on both nodes; funding spent on both |

Receipt: `evidence/signet/20261123T085407112454Z-signet-vanilla-dlc.json`.

## Phase 2: what exists and the minimum consensus patch

| Capability | bitcoin-rs `dev` `dd6c2040` | Spiral Core patch (`BIPSpace/Keyless-CHECKSIG`) |
|---|---|---|
| BIP341 digest | yes (native Taproot validation) | Core's own `SignatureHashSchnorr`, new `SigVersion::TAPSCRIPT_TXCOMMIT`, key_version 2 |
| Unknown-key-type detection | stock BIP342 only | 33-byte selector `0x02‖SHA256("BIPSpace/Keyless-CHECKSIG/TXCOMMIT-draft")` |
| TXCOMMIT digest comparison | no | yes |
| Immediate abort on mismatch | no | yes; also under CHECKSIG + NOT and CHECKSIGADD |
| CHECKSIG / CHECKSIGVERIFY / CHECKSIGADD | stock | all three; empty candidate keeps BIP342 behaviour |
| Sigops budget | stock | charged by Core's existing 50-unit decrement, which precedes the key-type branch |
| OP_CAT | no | Tapscript only, behind its flag, 520-byte limit |
| P2MR | no | restricted witness-v2 path: `c0` control, depth ≥ 1, no annex |
| Related | BIP 448 regtest (OP_TEMPLATEHASH, OP_CHECKSIGFROMSTACK, OP_INTERNALKEY) | — |

bitcoin-rs has no TXCOMMIT, OP_CAT or P2MR code; its "keyless" matches are
BIP352 scanning. The minimum Core patch is Spiral's existing pair:

- `patch_core.py`: interpreter flags, the TXCOMMIT branch, OP_CAT, P2MR.
- `patch_core_regtest.py`: enables the flags in `GetBlockScriptFlags`, only
  on regtest and only with `-keylessresearch`.

Applied to Core `d0f6d995` (v30.0), the pair touches 9 files (+96/−5),
recorded as `evidence/regtest/keyless-core-d0f6d995.patch` with sha256
`e6b3e5db…2bc6`. It built locally in 8.5 minutes. The patch's 34 interpreter
vectors all pass in `test_bitcoin` (`evidence/regtest/keyless-core-vectors.log`).
Mainnet, testnet and signet flags are untouched, so the patch cannot activate
on the private Signet without a further Signet-specific activation change.

## Phase 3: A/B on three validators

Setup:

- **Validators:**
  - `new`: patched Core with `-keylessresearch=1`.
  - `old-flag`: the same binary without the flag.
  - `old-stock`: unmodified Core 31.1 locally, 30.2 in CI.
- **Trials:** one hand-built block per trial, submitted to all three nodes
  and rolled back afterwards.
- **Matched funding:** both arms are funded with 1,000,000 sats in the same
  transaction (`2040aa17…e4c4`). Both pay 998,000 sats and use the same oracle
  and outcomes.
- **Oracle:** in arm A its scalar decrypts an adaptor signature; in arm B
  `SHA256(scalar)` is checked against the announced commitment.

All 37 trials match their expected verdicts (`evidence/regtest/ab-regtest.json`).

| Pattern (new / old-flag / old-stock) | Arm A | Arm B | Unsafe fixtures |
|---|---|---|---|
| accepted everywhere | 5: two honest settlements, compromised keys, novated CET, superseded CET | 8: settle to Alice, to Carol, counterfactual Bob; fresh-witness outpoint, version, sequence, locktime; unchanged control | unconstrained digest (theft), no oracle gate, bad-builder allowlist |
| rejected everywhere | 8: recipient, amount, outpoint, version, sequence, locktime, tapleaf, wrong attestation | — | — |
| **rejected only by `new`** | — | 12: recipient (stale and fresh), amount (stale and fresh), outpoint, version, sequence, locktime (stale), wrong leaf, leaf outside the tree, wrong attestation, missing attestation | 31-byte digest |

Rejection reasons on `new`:

- TXCOMMIT mismatch reports as `Invalid Schnorr signature`; the patch reuses
  `SCRIPT_ERR_SCHNORR_SIG`.
- A wrong oracle preimage or a non-allowlisted recipient fails
  `OP_EQUALVERIFY`.
- A leaf outside the committed tree fails `Witness program hash mismatch`.
- The 31-byte digest fails `Invalid Schnorr signature size`.

**Old versus upgraded nodes.** Every arm B spend that the new rules forbid
was accepted by both old validators: an unknown witness version is
anyone-can-spend on stock rules. Valid upgraded spends are accepted by all
three, which is what a soft fork requires. The other direction is the
danger: a non-upgraded miner can mine an arm B theft that only upgraded
nodes reject, splitting the chain. Arm A behaves identically on all three.

**Stale versus fresh witnesses.** Arm B rejects any mutation applied
under a witness built for the honest transaction. A spender who re-derives
the witness can still change fields the policy does not constrain: the
input outpoint (any coin with the same script), the version, the sequence
and the locktime. Those spends are accepted, because they are bound to the
actual transaction but not restricted by the program. Recipient and amount
cannot change: the recipient is checked against the allowlist and the
amount is a constant in the leaf.

| Measurement | Arm A (adaptor DLC) | Arm B (TXCOMMIT) |
|---|---|---|
| Settlement weight / vsize | 612 WU / 153 vB | 908–909 WU / 227–228 vB |
| Witness bytes | 229 | 521–522 |
| Spend script | 68-byte leaf | 212-byte leaf (oracle gate 35 B + allowlist/CAT/TXCOMMIT program 177 B) |
| Fee at 10 sat/vB | 1,530 sats | 2,270 sats |
| `submitblock` latency, median of all trials | 3.3–3.7 ms on each node; no difference between arms at this size | same |
| Setup keys | 2 funding keys, both needed to sign anything | 0 |
| Setup messages | 4 adaptor pre-signatures (2 outcomes × 2 parties), exchanged before funding | oracle commits `SHA256(s_m)` per outcome; parties fix the allowlists |
| Settles on stock consensus | yes (Signet, regtest) | spendable by anyone on stock consensus; enforced only on the patched regtest |

## Phase 4: transferability

Both arms were tested with actual signed transactions; the rows are in
`ab-regtest.json`.

- **Arm A (vanilla) transfers by novation.** Alice sells her `ALICE_WINS`
  position to Carol: Bob and Alice re-sign a CET that pays Carol, and that
  CET confirms. The superseded CET paying Alice also still confirms. An
  off-chain novation cannot revoke it, so Carol must trust Alice, or the
  parties must refund into a new funding output on-chain. Bob must be online
  to re-sign.
- **Arm B selects at settlement, not by transfer.** The `ALICE_WINS` leaf
  pays either Alice or Carol, chosen after funding and without any key. The
  choice is limited to the allowlist fixed at funding. It is also
  permissionless: whoever holds the attestation and settles first picks the
  recipient. That is selection, not a transfer of rights. A transfer to an
  arbitrary new holder needs the leaf to check the current holder's consent.
  That means a signature over the recipient, which takes OP_CHECKSIGFROMSTACK
  (BIP348, available in bitcoin-rs's BIP 448 regtest mode) or an equivalent
  extra opcode. It was not built here.

### SatsHedgeZero oracle path

SatsHedgeZero (`5ca390e`) uses numeric DLCs over binary price digits, signed
as BIP340 signatures by a t-of-n FROST confederation:

- the announcement fixes the per-digit nonces (`crates/shz-dlc/src/lib.rs:392`);
- the confederation is described in `docs/ARCHITECTURE.md:46`.

Outcome authenticity is verified off-chain in Rust; L1 sees only completed
adaptor signatures. Its own documentation states that releasing a position
before maturity needs a covenant plus novation
(`crates/shz-utxoref/src/mnr02.rs:27`).

What this means for the two arms:

- **Arm A** plugs into that oracle directly: the digit nonces give the
  adaptor points.
- **Arm B** needs the oracle to also publish `SHA256(s_{j,b})` per digit and
  bit value. A leaf would then check one preimage per digit of the outcome's
  prefix, adding about 35 bytes of script per digit.
- **The committee does not go away.** Oracle authenticity stays with the
  FROST quorum in both arms. Arm B removes the parties' settlement keys, not
  the oracle committee.
- **Lifting the commitment step.** OP_CHECKSIGFROMSTACK would let the leaf
  verify the digit signatures themselves, with no hash pre-commitment. That
  is one more consensus change.

## Phase 5: does keyless reduce the trusted computing base?

| Threat | Arm A | Arm B | Evidence |
|---|---|---|---|
| Both settlement signing machines compromised | funds redirected to any address | no settlement keys exist; payout limited to the allowlist | A "compromised keys" accepted everywhere |
| One party compromised | needs the other key; can refuse to re-sign (blocks novation) | nothing to compromise | — |
| Oracle committee (t members) colludes or equivocates | wrong outcome settles | wrong outcome settles | identical by construction |
| Malicious proof generation | adaptor pre-signatures are verified before funding | preimages are checked on-chain; wrong or missing attestation rejected | rows "invalid proof" |
| Compromised transaction / leaf builder | parties check each CET sighash before pre-signing | **trust moves here**: a leaf with an attacker in the allowlist, or no oracle gate, settles under the new rules | BB and NO accepted on `new` |
| Script bug | stock opcodes only | a bare TXCOMMIT leaf is anyone-can-spend even after the soft fork | K3 theft accepted on `new` |
| Validator implementation bug | mature consensus code | new consensus code; non-upgraded miners accept every forbidden spend | 12 + 1 rows `r/A/A` |

**Conclusion.** Keyless-CHECKSIG removes the settlement keys, and with them
the pre-signature ceremony, from the trusted computing base. It relocates
trust to three places:

- the correctness of the program compiled and audited at funding (allowlist,
  amount, oracle gate);
- the new consensus implementation, together with miner majority enforcement;
- the oracle, which is unchanged.

It is a material reduction where compromise of signing machines or key
ceremonies is the dominant threat. It is no reduction for oracle risk, and
a single unconstrained TXCOMMIT leaf is worse than a key: anyone can spend
it.

## Unresolved

- **TXCOMMIT on the private Signet.** The patch activates only on regtest.
  Doing this on the Signet needs a separately identified patched custom
  Signet with both miner and observer running the patched build. Not done.
- **Oracle authenticity in script.** Arm B uses per-outcome hash commitments.
  Checking the oracle's signature directly needs OP_CHECKSIGFROMSTACK.
- **Transfer to an arbitrary holder.** Needs holder consent checked in
  script. Not built.
- **bitcoin-rs.** No TXCOMMIT, OP_CAT or P2MR; the Core patch is the only
  implementation of the rules.
- **Validation cost.** The `submitblock` latency at this size does not
  separate the arms. A proper cost comparison needs Core's benchmark
  harness.
