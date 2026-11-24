# Private Signet and Keyless-CHECKSIG A/B: results

Runs of 2026-11-23. Local runs used WSL Ubuntu 24.04. Every transaction ID and
block hash below is in the receipts under [evidence/](evidence/).

Nothing here was run on a public network. Keyless-CHECKSIG is enforced only
by the patched regtest node started with `-keylessresearch=1`.

## CI confirmation

[Run 45143128356](https://github.com/patrickdugan/Spiral/actions/runs/45143128356)
on commit `69959b6` passed all three jobs. The values below come from its
public notice annotations.

- **signet** (Core 30.2 release tarball and the v30.2 miner, with
  `bitcoin-util` grinding):
  - 101 signed blocks in 204 s, tip `000000ef40849c78238060c1c6c529cd4f4c30daa107d461720e1d68b55af046`;
  - wallet transaction `6d671db326d9ce51b873f3d8f4433bfb54af09d1a2959eb62bc15c1e1f488404`
    confirmed on both nodes;
  - vanilla DLC funding `fec151d7…856d` and CET
    `ae0a509f4b9857a425124ec32abb725d3500a667478c5fc5016fc286c4ae22a2`
    confirmed on both nodes in block
    `00000329fb51ad1441beba4e38079862b84e26c74b5b5843f9dba6fd356b2b84`;
  - both nodes agree at height 104, chainwork `…1e47fc34`.
- **keyless-ab:**
  - patched Core `d0f6d995` built on the runner, interpreter vectors pass;
  - 37 trials, 0 mismatches, with `new` and `old-flag` on the patched v30.0
    build and `old-stock` on Core 30.2.

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

## K4 / C1: Keyless-CHECKSIG on a patched custom Signet

`core/patch_core_signet.py` extends Spiral's regtest-only activation to a
**custom** Signet:

- `-keylessresearch` is read into the Signet options too.
- The flag is refused without `-signetchallenge`, so the default public
  Signet can never run the rules. That refusal is recorded in
  `evidence/signet-keyless/default-signet-refusal.txt`.
- `GetBlockScriptFlags` enables the research flags on REGTEST or SIGNET when
  the flag is set.

The combined patch is 9 files (+104/−5), recorded as
`evidence/signet-keyless/keyless-core-d0f6d995-with-signet.patch`. It was
rebuilt with the wallet enabled, which the signer needs.

The lab ran with three nodes:

- miner and observer on the patched build with `-keylessresearch=1`;
- a `legacy` node on stock Core 31.1, following the miner.

Arm B spends are non-standard, so `lab.mine_with()` puts them into a block
through the official miner's `genpsbt`/`solvepsbt` and the signer wallet.
The result is a correctly signed Signet block with whatever transactions the
experiment needs.

Receipt: `evidence/signet-keyless/20261123T134349654392Z-signet-keyless-k4.json`.

| Step | Result |
|---|---|
| Network | 101 signed blocks, tip `0000021c…fa20`; all three nodes agree on every hash and chainwork |
| K4 | arm B settlement `d4ee81fbc0b8e961f66937da9e00bad4389676d897d73a218e3b1496cc2fed1f` (ALICE_WINS paid to Carol, chosen at settlement). Both mempools refused it with `bad-txns-nonstandard-inputs`. The authorized signer included it in block `000001f8636c6b14d54b46a653fec05739c007d88b1a8c9c2e672695ecd95c01`; miner, observer and legacy all accepted it |
| C1 | stale-witness theft to Mallory, `ef63c4a3…7b69`, in the correctly signed block `00000011cf160cb49e0b363ab3a8fe027cebaa34ee8f887a10ee6a44917d18e7`. The patched miner rejected it with `Invalid Schnorr signature` (the TXCOMMIT mismatch); chain tips show miner **invalid**, observer **invalid**, legacy **active**. The legacy node forked, and invalidating the block there restored it |
| K3 | bare-TXCOMMIT output taken by a thief, `68d23dea…386d`, in block `00000308…4327`, accepted by all three nodes |
| Final | all three nodes agree at height 112, chainwork `…20969cd4` |

CI repeated K4, C1 and K3 in
[run 45187341988](https://github.com/patrickdugan/Spiral/actions/runs/45187341988)
on commit `6d9e880`, with the patched v30.0 node as miner and observer and
stock Core 30.2 as the legacy node:

- **K4:** settlement `6450a38eaa6926ce55f58534534a1b210312991a97f91b02255365d74574a3bb`
  in signed block `000001797096633084ca340c97963310c39f63b2e5043258ef05d63447fec31b`,
  accepted by all three nodes.
- **C1:** block `000002dd…1e32` is invalid on the miner and the observer and
  active on the legacy node.
- **K3:** the theft is accepted by all three nodes.
- **Final:** all three nodes agree.

C1 shows how the split happens in practice. The patched miner announced the
invalid block to its high-bandwidth compact-block peers **before script
validation**, which is ordinary BIP152 behaviour. The observer then answered
`duplicate-invalid` and the legacy node `duplicate`: the legacy node had
already received the block that way and accepted it. No special wiring is
needed for a non-upgraded node to follow a block the upgraded network
rejects.

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

## Arm C: oracle signature in script and owner-assigned transfer

`core/patch_core_csfs.py` adds research **OP_CHECKSIGFROMSTACK** (opcode
`0xcc`, Tapscript only), following BIP348:

- It is enabled with the other research flags by `-keylessresearch`.
- It charges the 50-unit budget per non-empty signature.
- A bad signature with a 32-byte key fails the script; an empty signature
  pushes false; other key types stay upgradable.
- **Lab restriction:** messages must be exactly 32 bytes, because the pinned
  Core's `VerifySchnorr` takes a `uint256`.
- Without the flag, `0xcc` remains OP_SUCCESS204, so this is a soft fork.

The combined patch is 9 files (+135/−5), recorded as
`evidence/regtest/keyless-core-d0f6d995-signet-csfs.patch`.

**Arm C** is a 272-byte leaf per outcome. It checks three things:

1. The oracle's standard DLC attestation `x(R)‖s_m` is a valid BIP340
   signature on the outcome message under the oracle key. No per-outcome
   hash commitment is needed: the oracle publishes only the usual key and
   nonce announcement.
2. The position owner (Alice for `ALICE_WINS`) signed
   `SHA256(contract_id ‖ recipient)`, so the recipient can be anyone and
   needs no counterparty.
3. TXCOMMIT binds that recipient and the fixed amount to the real
   transaction.

Settlement weight is 1,033 WU, against 612 for arm A and 908 for arm B.

**Regtest.** All 55 trials match (`evidence/regtest/ab-regtest-csfs.json`).

| Pattern (new / old-flag / old-stock) | Arm C | CSFS probes on plain P2TR |
|---|---|---|
| accepted everywhere | self-assigned settlement; **Alice → Carol with no Bob**; second assignment to another buyer (each valid alone) | valid BIP340 signature; 33-byte (unknown) key type |
| rejected only by `new` | 9: Carol's assignment but another recipient paid; recipient without assignment; assignment signed by Bob; assignment replayed from another contract; BOB_WINS attestation; forged oracle signature; 63-byte signature; empty oracle signature (CSFS false, then `VERIFY`); stale witness with the amount changed | 4: wrong signature, 63-byte signature, empty signature (false result), 31-byte message |

On old rules every probe is accepted, because `0xcc` is OP_SUCCESS there.
That is the soft-fork property on a standard output type.

**Patched custom Signet** (`evidence/signet-keyless-csfs/`): the patched
miner and observer run with CSFS, alongside a stock Core 31.1 legacy node.

| Step | Result |
|---|---|
| Transfer | Alice assigns her ALICE_WINS payout to Carol. Settlement `3a07a8068bca236126167d0baa882ed89a091f6ddc41be87fd99678fb46316a7` is refused by the mempool (`bad-txns-nonstandard-inputs`), included by the signer in block `000000192fa89c3fa6c77fe5b3ae9680b4c9e0ccba967b9316df0f421d8778d0`, and accepted by all three nodes |
| Double sale | Alice had also signed an assignment to a second buyer. That settlement, `8f8a9d5b…0df8`, in signed block `000002b0…d6bc`, is rejected on every node: the miner says `bad-txns-inputs-missingorspent`, the observer and the legacy node `duplicate-invalid` after receiving it by relay |
| K4, C1, K3 | repeated: K4 `ec598857…b4d4` accepted by all; C1 block `00000362…1eda` invalid on both patched nodes and active on the legacy node; K3 theft `8b7002d4…1c8a` accepted by all |
| Final | all three nodes agree |

CI repeated this in
[run 45209526517](https://github.com/patrickdugan/Spiral/actions/runs/45209526517)
on commit `13f6a45`, with stock Core 30.2 as both the old-stock regtest node
and the Signet legacy node:

- **Regtest:** 55 trials, 0 mismatches.
- **Transfer to Carol:** `28eea7850a5cf94e840881e39ef39ce12c8ed7c02cb206a51adc5070fb585473`
  in block `00000204025135e75f41456182068bc5f6473b73a2eff75a77a838d95ab74c42`,
  accepted by all three nodes.
- **Double sale:** `54e65c77…f57a` rejected on every node.
- **K4, C1 and K3:** repeated, and all three nodes agree.

## SatsHedgeZero on the private Signet

Runs of 2026-11-24 against SatsHedgeZero `5ca390e` plus the shz-cli change
below. Two parts: the SHZ prototype as it is, then SHZ-K1, the same contract
moved onto the keyless rules.

**CI confirmation.** [Run 45282607416](https://github.com/patrickdugan/Spiral/actions/runs/45282607416)
on commit `edd4b53` passed all four jobs: the stock Core 30.2 runner and
the patched v30.0 build, built from source. The values come from its public
notice annotations.

- **shz-prototype** (SatsHedgeZero `33e3a6b`, Core 30.2): funding
  `0dfccb2d…6970` and clearing
  `a401222c5c8ee776ccff42313a7e3da7175e54c540b8d3ab8aa850d9c05ac283`
  (505 vB) confirmed on both nodes in block `00000279…3f07`; the four
  outputs are unspent on both nodes; both 1-sat shaves were refused.
- **keyless-ab, regtest:** SHZ-K1 19 trials, 0 mismatches, with
  `old-stock` on Core 30.2.
- **keyless-ab, patched Signet** (with K4, C1, K3 and arm C in the same
  lab):
  - transfer to Carol
    `f325ace6792ed2a677e3769532f899b946dd7c9ecb3c1d08be3a343fa11a1fbe`
    (1,075 / 550, 794 vB) accepted by all three nodes;
  - the double sale rejected everywhere;
  - the 1-sat-shave block `0000007b…5e5b` invalid on both patched nodes and
    active on the 30.2 legacy node;
  - all nodes agree at the end.
- **What it took:** the first attempt (run 45278249742) failed because the
  block after the K4 run omitted SHZ-K1's funding. The runner now mines
  until the wallet sees the funding confirmed.

### The prototype as it is (stock Core 31.1)

`shz testnet4-live` is SHZ's live flow. It funds three NUMS P2TR DLC outputs
(2,095 / 1,595 / 1,270 sats) in one wallet transaction, pre-signs one
3-input, 4-output collated clearing transaction ($80k → $100k → $125k, +450
sats to Alice), probes the mempool with two 1-sat shaves, and broadcasts.

Until now it could only reach Testnet4 through `wsl bitcoin-cli -testnet4`.
SatsHedgeZero now reads `SHZ_CHAIN` (default `testnet4`),
`SHZ_BITCOIN_CLI_DIRECT=1` and `SHZ_BITCOIN_CLI_EXTRA_ARGS`; explorer links
are left empty off Testnet4. `ab/run_signet_shz_prototype.py` points it at
the lab miner (`evidence/signet-shz-prototype/`).

| Step | Result |
|---|---|
| Funding | `2a22549cfeb1bc8ecf03718523c8dc92c927ad1f87bc8bca4b1279b97edceb70` |
| Clearing | `cb2430ff487199f4233a437beb2176309c85c6e649c731db35d25645baa7deec`, 505 vB, same size as the Testnet4 run |
| Block | both in signed block `00000258153c694f51954619d18432b0cae9d23854ed43631442c7eeeca8a42d`, one confirmation on miner and observer |
| Outputs | 1,250 (Bob), 1,475 (Alice), 990 (anchor), 825 (Carol) sats, unspent on both nodes |
| Probes | both 1-sat shaves refused: `mempool-script-verify-flag-failed (Invalid Schnorr signature)` |
| Agreement | both nodes agree |

**Mislabelled report.** The clearing report SHZ embeds still says
`bitcoin-testnet4` and `network_code: Testnet4`, because the ceremony
builder hard-codes them, while its anchor is Signet block 102. The 304-byte
BitVM3 statement from this run therefore names the wrong network and must
not be presented as a Testnet4 statement. The outer receipt's `network` is
`bitcoin-signet`.

**Lab note.** The Signet miner backdates only 100 block
intervals, so `mine --blocks 110` waits in real time after block 101. The
first try was stopped there (its mining receipt is not kept); the run above
mines 101.

### SHZ-K1: the same contract, settled by script

`ab/shz_margin.py` ports SHZ's contract maths from Rust: InverseContractSpec,
payouts, liquidation prices, the dyadic `compress_cet_ranges` and
`oracle_digit_message`. `ab/test_shz.py` checks the crate's own test vectors
(643 CETs; liquidation 83,333 / 90,909 / 111,112) and values printed by the
Rust crates for trade 1 (949 CETs, the $125k range, the digit message).

`ab/shz_k1.py` keeps the contract, the oracle message format and the
compression unchanged, and replaces the 2-of-2 adaptor CETs with one P2MR
leaf per CET range. Each leaf:

1. **Checks each prefix digit's oracle signature.** For each digit the leaf
   rebuilds `R_j‖s_j` from the announced nonce `R_j` (in the script) and the
   scalar `s_j` (in the witness), then checks it with CSFS against SHZ's
   digit message. Pinning `R_j` keeps SHZ's equivocation deterrent: signing
   both bit values under one nonce reveals the oracle key.
2. **Checks one assignment per side.** Each side's owner signs
   `SHA256(cid‖recipient)` once. The same assignment works in every range
   and in the refund, so a position can be sold without the counterparty.
3. **Binds the outputs.** It rebuilds the range's long and short outputs
   with OP_CAT and binds them with TXCOMMIT.

A further leaf refunds both margins after CSV 144, with the same assignment
checks. No party key can move the funds.

Trade 1 (Alice long $1 at 2x, Bob short $1 at 1.25x, entry $80,000) at a
maximum error of 1 sat:

- 949 CET leaves and the refund leaf; tree depth 10, control block 321 bytes.
- The $125k range is prefix `000111101000` (12 digits), paying 1,075 / 550
  sats, exactly the prototype's +450.
- Each digit costs 103 bytes of leaf and 33 bytes of witness. The earlier
  estimate of about 70 left out the pinned nonce.
- The longest leaf (15 digits) is 1,833 bytes.
- A two-output settlement is 3,176 WU (794 vB); one-sided settlements are
  2,272 and 1,728 WU, and the refund 1,549 WU.

**Regtest** (`evidence/regtest/shz-k1-regtest.json`): all 19 trials match.

| Pattern (new / old-flag / old-stock) | Cases |
|---|---|
| accepted everywhere | $125k self-assigned; long sold to Carol with no Bob; short sold to Mallory with no Alice; a second sale of the long side (valid alone); $50k (long liquidated, short-only output); $500k (short liquidated, long-only output); refund after CSV 144; refund to Carol after the transfer |
| rejected only by `new` | 1-sat shave with a stale witness; 1-sat shave with a fresh witness (TXCOMMIT matches, the leaf amounts do not); $100k attestation on the $125k leaf; forged digit scalar; a digit signed under an unannounced nonce; Mallory paid while Carol's assignment is presented; Mallory paid with Carol's assignment; long assignment signed by Bob; assignment replayed from another contract; refund with a 1-sat shave |
| rejected everywhere | refund before CSV 144 (`bad-txns-nonfinal`: BIP68, consensus on every node) |

**Patched custom Signet** (`evidence/signet-shz-k1/`): patched miner and
observer with CSFS, stock Core 31.1 legacy node.

| Step | Result |
|---|---|
| Funding | two K1 outputs, `tb1zmjqy0jjynp70rn0jlw6drs0w9aj5thcclj9nlxh6hxup30ft4w6synnazt`, 2,625 sats each |
| Transfer | oracle attests $125,000; Alice's long sold to Carol. Settlement `81aaa23b09ed02bca64bd390172d242ec5493f1fa1d42e35ba951aca4f706427` (1,075 to Carol, 550 to Bob) is refused by both mempools (`bad-txns-nonstandard-inputs`), included in signed block `00000334e621cdd612db3499edf60e655f62f565f89bd982c93b81d2084754db`, and accepted by all three nodes |
| Double sale | Alice's second assignment, `a118b872…d6b4`: miner `bad-txns-inputs-missingorspent`, observer and legacy `duplicate-invalid` |
| Split | a 1-sat shave with a fresh witness, `89fc2c0f…15e2`, in signed block `0000014e5b6658bd6d5b75163722dd9dbffb64a5b3075cabeccf8642e8a00a45`: invalid on both patched nodes, active on the legacy node, then invalidated there |
| Final | all three nodes agree |

**What changes relative to SHZ**

- **Gone:** the parties' settlement keys and every pre-signed CET. Setup
  needs no signature exchange, and no party has to be online at maturity.
- **Transfer without the counterparty.** MNR-05 needs novation or a
  ClearingGuard; here one owner signature is enough.
- **Kept:** the oracle trust (the FROST quorum signs the same messages) and
  the exact contract maths.
- **Left open by K1, closed by K2 (next section):**
  - the double sale;
  - SHZ's netted clearing (K1 settles each trade on its own, 794 vB);
  - the CSV refund on the Signet;
  - a single-key lab oracle in place of SHZ's FROST quorum.

### SHZ-K2: exclusive transfer, netted book, FROST, refund on Signet

`ab/shz_k2.py`, `ab/shz_frost.py`, `ab/run_shz_k2_regtest.py`,
`ab/run_signet_shz_k2.py`; evidence in `evidence/regtest/shz-k2-regtest.json`
and `evidence/signet-shz-k2/`.

**Owners live in the output.** The P2MR root is `TapBranch(C, TapLeaf(state))`.
The state leaf is `OP_RETURN <K_1> … <K_n>` and is never executed. `C` is the
tree of contract leaves, none of which contains a key. Each leaf takes the
owner keys, `C` and the branch order from the witness, recomputes the spk,
and writes `SHA256(0x22‖spk)` into the TXCOMMIT message as
`sha_scriptpubkeys`. Naming anyone but the current owners therefore gives a
different spk, and the spend fails.

**Transfer is an on-chain step that one owner signs alone.** The transfer
leaf for party p works as follows:

- the current `K_p` signs the spending transaction with an ordinary BIP342
  CHECKSIG;
- the single output must be the same `C` with only `K_p` replaced;
- the output keeps the input amount minus a fixed 500-sat fee, computed with
  4-byte script arithmetic (amounts stay below 2^31 sats);
- it may not fall below a floor that keeps settlement funded.

The counterparty is not needed and cannot block it. Once the transfer
confirms, the old key is no longer in the state, so a second sale spends a
coin that does not exist, and the former owner can neither settle nor
transfer again. A buyer is exclusive after one confirmation. Before that,
two conflicting transfers race like any double spend.

**Netted book.** SHZ's live flow funds its three trades together, so the
three can share one K2 output with parties alice, bob and carol:

- `compress_book_ranges` partitions the price across all three trades,
  keeping SHZ's per-trade representative so every range conserves every
  trade's collateral;
- each leaf pays the netted per-party totals.

At $125,000 those totals are exactly the prototype's clearing outputs:
1,475 / 1,250 / 825. A party's transfer moves its whole book.

**FROST.** `shz_frost.py` ports `crates/shz-oracle/src/frost.rs`:

- Feldman-checked Shamir shares of the group key;
- one Shamir-shared nonce polynomial per digit;
- partial signatures checked per signer;
- Lagrange combination into a plain BIP340 signature under the announced
  nonce.

The tests check that any 3 of 5 sign, that 2 do not, and that signing both
bit values of a digit reveals the group key.

**Sizes**

| Item | Trade 1 | 3-trade book |
|---|---|---|
| CET leaves | 949 | 8,282 |
| Tree depth (incl. state leaf) | 11 | 15 |
| Longest leaf | 1,857 B | 2,396 B |
| Settlement | 777 vB | 892 vB (three trades) |
| Transfer | 408 vB | 452 vB |
| Refund | 370 vB | 451 vB |

The book's one settlement replaces three per-trade settlements; trade 1's
alone is 777 vB. SHZ's cooperative clearing, signed by all parties, is
505 vB.

**Regtest:** all 26 trials match.

| Pattern (new / old-flag / old-stock) | Cases |
|---|---|
| accepted everywhere | settle $125k (quorum 1,2,3 and 2,4,5); transfer alice → carol without Bob; the new coin settles to carol / bob; book netted 1,475 / 1,250 / 825; book settles after bob's book moves to mallory; refund after CSV to current owners; book refund |
| rejected only by `new` | 2-of-5 attestation; $100k attestation on the $125k leaf; 1-sat shave; paying mallory instead of the long owner; witness naming carol as owner while the state says alice; transfer signed by bob; transfer that also swaps bob's key; transfer taking 1,000 sats extra fee; former owner transferring the new coin (as herself, or signing as carol); new coin settled to the former owner; transfer below the settlement floor (two cases, `OP_VERIFY`); book shave; bob settling after selling his book; refund to the former owner |
| rejected everywhere | refund before CSV (`bad-txns-nonfinal`); second sale of the spent coin (`bad-txns-inputs-missingorspent`) |

The floor rejections fail at the floor's `OP_VERIFY`. The others fail at
the owner CHECKSIG, a CSFS digit check, or TXCOMMIT, which Core all reports
as `Invalid Schnorr signature`.

**Patched custom Signet**, run after K4, C1, K3, arm C and SHZ-K1 in the same
lab, with a stock Core 31.1 legacy node:

| Step | Result |
|---|---|
| Funding | trade 1 (alice / bob), the book (alice / bob / carol) and a refund coin, in one transaction |
| Transfer | `1732bd5f7eea7ec8236858900f540201ab6f060d1e97ebd9b424c93605cc3c7d` (408 vB), signed only by Alice: refused by both mempools (`bad-txns-nonstandard-inputs`), mined in signed block `000002904adb2c7ae2015121066ac178bf5c7c962df545a457a9bfca82b44199`, accepted by all three nodes |
| Second sale | Alice's transfer of the same coin to Mallory: miner `bad-txns-inputs-missingorspent`, observer and legacy `duplicate-invalid` |
| Former owner settles | Alice settling the sold coin to herself, in a signed block: invalid on both patched nodes, active on the legacy node, then invalidated there |
| Settle | `f36dcc650b152e41f009c09e205f79e5b35ad38cf24ac2ea50790e0b9494c5ad`: Carol 1,075, Bob 550 (FROST quorum 2,4,5), accepted by all |
| Book | `74ad58e5378d68a663532a30e0ff568b7f2795df3872ea588f360db8fbeb186c` (892 vB): Alice 1,475, Bob 1,250, Carol 825, accepted by all |
| Refund | refused before the delay (`non-BIP68-final`); after 144 fast-timestamp blocks, `7b90cef6012e85bb11ad5aaafcbbe1e6ba83a46d3a46913ac17bc3003c76c003` pays 625 / 1,000, accepted by all |
| Final | all three nodes agree at height 400 |

`lab.py mine --fast` mines each block with `--set-block-time` one second
after the tip. The timestamps stay above median time past and far below the
two-hour future limit, which is how 144 blocks fit in minutes.

**Still open after K2**

- **Netting trades funded separately.** The book needs its trades created
  together. Netting independently funded outputs would need each leaf to
  check other inputs' contributions, which needs 64-bit amount arithmetic
  or input introspection that these rules do not provide.
- **Book transfers are per party, not per position.** Selling one trade
  out of a book is not possible.
- **Amounts below 2^31 sats per output.** The transfer fee arithmetic uses
  4-byte script numbers.

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

**Arm C.**

- OP_CHECKSIGFROMSTACK removes the oracle's hash pre-commitment: the leaf
  checks the same BIP340 attestation arm A uses as its adaptor secret.
- It removes the counterparty from transfers: one owner signature, checked
  on-chain, redirects the payout.
- It does **not** stop the owner from selling the same position twice. Both
  assignments are valid until one settles, so the buyer bears seller risk
  until confirmation.
- Exclusive transfer still needs an on-chain step: Patrick's rollover
  ([ROLLOVER_DESIGN.md](ROLLOVER_DESIGN.md)), or a spent-outpoint check
  inside the program.

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

- **Mempool relay of keyless spends.** Arm B settlements reach blocks only
  through the block signer (K4). Relay policy is untouched, and so is the
  pre-validation compact-block relay that carried C1 to the legacy node.
- **Exclusive transfer without a transaction.** SHZ-K2 makes transfer
  exclusive and keyless as an on-chain step (one owner signature, no
  counterparty). Purely off-chain exclusivity, as in arm C, still cannot
  stop a second sale.
- **CSFS message length.** The lab restricts CSFS to 32-byte messages.
  BIP348 allows any length; supporting that needs a variable-length
  `VerifySchnorr` in the pinned Core.
- **Netting separately funded trades.** SHZ-K2 nets a book whose trades
  are funded together. Netting independent outputs keylessly is open (see
  SHZ-K2, still open).
- **bitcoin-rs.** No TXCOMMIT, OP_CAT or P2MR; the Core patch is the only
  implementation of the rules.
- **Validation cost.** The `submitblock` latency at this size does not
  separate the arms. A proper cost comparison needs Core's benchmark
  harness.
