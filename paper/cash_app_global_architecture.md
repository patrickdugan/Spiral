# Cash App Global: a BTC-to-local-wallet payout architecture

*Architecture review and build plan, 2026-10-30. Planning only.*

> **Status.** This is a design and inventory, not a product. Nothing here was built, deployed,
> funded or proven during this pass. No fund movement, key change, deployment, paid resource or
> new prover was started. Recorded proof results below are **repository-recorded**; none was
> re-run for this note. "Cash App" is a usability analogy, not a partnership. "BNS/ENS-like" means
> the naming UX only: no Stacks, Ethereum, naming chain or token. Jawwal Pay is the first
> candidate payout rail. Its API, authentication, webhook signing, idempotency, currency/units,
> limits and KYC terms are **unverified**: no Jawwal documentation was inspected.

## Summary

- **The product.** A sender pays BTC to `alice@domain`. A Nostr-associated record resolves that
  handle to the recipient's key and a *commitment* to a payout destination, never the destination
  itself. A liquidity provider that is **buying BTC** quotes a rate, receives the BTC at a fresh
  deposit script, and pays the agreed local-currency amount into the recipient's wallet. It then
  issues a signed receipt.
- **What exists.** These parts exist:
  - a fail-closed Bisq read adapter, concierge and recovery journal (BAN);
  - a hash-only payment-claim ABI (UTXO-Ref PR #9, Stage 0);
  - a real recorded SP1/Groth16 Bitcoin payment proof that settles a *demo* BitVM regtest
    contract (Raito-Scrypt);
  - a pinned, isolated statement-verifier gateway with Core binding (zk-rusto-no-bitcoino);
  - signed-witness and transport primitives (tl-collator).
- **What does not exist.** There is no alias layer, payout intent, quote or reservation contract,
  BUY-side (cashout) selection on any branch I could read, payout ledger, rail adapter, receipt
  format or reconciliation, and no connection between any of these and the proof work.
- **Direction is the first correctness risk.** BAN's concierge keeps only makers
  **SELLING** BTC ([concierge.py:16-20](https://github.com/patrickdugan/Bisq-Agent-Network/blob/0accf630cf17b12f72679fd0d5344744060ae208/src/ban/concierge.py#L16-L20)).
  Cashout needs makers **BUYING** BTC with verified bid-side payout inventory. The two must be
  separate code paths with tests in both directions.
- **The provider does not need a ZK proof to know it was paid.** It controls the deposit key and
  should check the deposit with its own Bitcoin Core. Proofs serve *third parties*: a sender
  disputing a provider, a bonded or BitVM referee, a Cashu mint, a light client.
- **That makes expensive proving the wrong first step.** It is not on the critical path of the
  smallest valuable slice.
- **No Bitcoin proof shows Jawwal delivery.** Fiat delivery evidence can only come from the rail
  (a signed API response or webhook, if Jawwal offers one) or from the recipient. A `verified:true`
  field is not verification authority, and two exist today:
  - `pay-verify` hardcodes `"verified":true` in its receipt JSON
    ([pay-verify.rs:55](https://github.com/patrickdugan/Raito-Scrypt/blob/dfbe57ff6d02f8a9678e7ca21e98b8da9489ff99/chain-sp1/host/src/bin/pay-verify.rs#L55));
  - the gateway returns `"proof_verified":true`.

  Both are authoritative only to a party that trusts that pinned executable or gateway.
- **Recommended slice.** BAN branch `feat/cashout-alias-intent-v0`, Python stdlib only. It covers:
  - alias record verification;
  - `PayoutIntentV1` and `ProviderQuoteV1`;
  - BUY-side shortlist with inventory attestations;
  - a **simulated** reference provider with a durable payout ledger and a mock rail;
  - the replay, wrong-recipient/network/output, expiry, stale-chain, substituted-key,
    duplicate-payout and provider-failure tests listed in F.3.

  No new proving.

---

## A. Source-pinned inventory

### A.1 Refresh (2026-10-30)

I made fresh blobless clones in the session scratchpad and did not touch any other session's
checkout. I read PR states from the public GitHub API and Raito-Scrypt (private) through the
owner's Git credentials.

| Repository | Ref inspected | SHA | Versus the pin in the brief |
| --- | --- | --- | --- |
| patrickdugan/Bisq-Agent-Network | `main` | `0accf630cf17b12f72679fd0d5344744060ae208` | unchanged; PR #6 merged 2026-10-22, no open PRs |
| patrickdugan/UTXO-Ref | `research/cashu-bitvm-trigger-20261028` (PR #9, **open draft**) | `3d053c02b430b83a6dfe63ab77ec70afe311de88` | unchanged |
| patrickdugan/Raito-Scrypt (**private**) | `research/bitcoin-bitvm` (no PR) | `dfbe57ff6d02f8a9678e7ca21e98b8da9489ff99` | unchanged |
| patrickdugan/zk-rusto-no-bitcoino | `evidence/raito-live-acceptance` | `fe74b8dc1cc8dcb935a1ba40363a416198476085` | merged into `feat/raito-verified-results` as PR #8 at its earlier head `2cbc85d6`; `fe74b8d` (the backends plan) came after |
| (same) | `feat/cheap-btc-proofs` (**no PR**) | `391c24a8a6837106ae59083c1eb12e4f1923a373` | 4 commits on top of the evidence branch |
| (same) | `main` | `51114e7f88115a92dd1b781277369044bac22bf7` | PR #1 (`feat/raito-verified-results` → main) is an **open draft** |
| tradelayer-wallet/tl-collator | `master` | `a1842473124453cbbd2d697c067129342deb00ab` | PR #10 merged 2026-10-29 (head `70232ad9b92bc4262482f8a8ddee105002880500`); PR #2 open |
| tradelayer-wallet/tl-rpc | `master` | `5609c429dcf3a334340142c46292cd2c097feb80` | PRs #3 and #4 (Rust RPC) merged 2026-10-29; PR #2 open |
| patrickdugan/TradeLayer-Rust | `main` | `41007c5dd423d6fffca32a849404ac52c0caf72c` | — |
| tradelayer-wallet/tradelayer-wallet | `master` | `7ddba36ca06538510e6460df0ddece8a71fcb547` | file names only (285 files; none named for alias, payout, Nostr, LNURL or BIP-353) |
| tradelayer-wallet/Ark-TradeLayer | `main` (one "init" commit) | `30187bf66ea0f72ca5a2ad2f31c703487a7efb59` | PR #2 open (fork head `8ed5dc33`) |
| patrickdugan/sapio | research branches | e.g. PR #6 head `1fad22bfb8cb97bf9e3f0506c9055ec1be8871d6` | commit subjects only |
| spiralxyz/bitcoin-payments | `main` | `5320295278e7ce3b5e1cb2d196def7a0fde3d729` | — |
| nostr-protocol/nips | `master` | `400d157` (2026-10-27) | standards baseline for section C |
| cashubtc/nuts | `main` | `1363de4` (2026-10-23) | standards baseline for Cashu references |

**Inaccessible or not inspected:**
- the BAN `cashout.py`/`arena_contract.py` local patch (not found in BAN `main` or any BAN
  branch; see A.4);
- Jawwal Pay documentation (none inspected);
- Raito-Scrypt CI (private, unreadable without auth);
- the Ark-TradeLayer PR #2 diff and the sapio research branches beyond their subjects;
- tradelayer-wallet source (names only).

### A.2 What exists, by evidence class

**Implemented code (read in this pass).**

| Where | What it does | What it does not do |
| --- | --- | --- |
| BAN [`src/ban/concierge.py:7-66`](https://github.com/patrickdugan/Bisq-Agent-Network/blob/0accf630cf17b12f72679fd0d5344744060ae208/src/ban/concierge.py#L7-L66) | Advisory buyer shortlist: maker `SELL` offers, payment method match, Decimal prices, advertised-bounds filter | Any BUY-side or cashout logic; live liquidity, reputation or executable size (README.md:56) |
| BAN [`src/ban/models.py:91-134`](https://github.com/patrickdugan/Bisq-Agent-Network/blob/0accf630cf17b12f72679fd0d5344744060ae208/src/ban/models.py#L91-L134) | Strict Bisq 2 offer DTO normalization; accepts both `BUY` and `SELL` maker directions (:104) | — |
| BAN [`src/ban/price_contract.py`](https://github.com/patrickdugan/Bisq-Agent-Network/blob/0accf630cf17b12f72679fd0d5344744060ae208/src/ban/price_contract.py) | Fiat precision 4, BTC precision 8, four amount-spec types, fail-closed | Payout minor units (a Bisq price precision is not a wallet currency's minor unit) |
| BAN [`src/ban/proofs.py:9-23`](https://github.com/patrickdugan/Bisq-Agent-Network/blob/0accf630cf17b12f72679fd0d5344744060ae208/src/ban/proofs.py#L9-L23) | `PaymentClaim(provider, rail, commitment, nullifier, proof_bytes)`; `verify` always raises `VerificationUnavailable` | Any verification (by design) |
| BAN [`src/ban/policy.py:21-34`](https://github.com/patrickdugan/Bisq-Agent-Network/blob/0accf630cf17b12f72679fd0d5344744060ae208/src/ban/policy.py#L21-L34) | Finite policy: `take_offer`, `release_btc`, `confirm_fiat`, `verify_payment_proof` and unknown actions are DENY | — |
| BAN [`src/ban/recovery.py:29-114`](https://github.com/patrickdugan/Bisq-Agent-Network/blob/0accf630cf17b12f72679fd0d5344744060ae208/src/ban/recovery.py#L29-L114) + [`trade_status.py`](https://github.com/patrickdugan/Bisq-Agent-Network/blob/0accf630cf17b12f72679fd0d5344744060ae208/src/ban/trade_status.py) | Durable SQLite journal of ambiguous intents. `safe_to_retry` is always False (:36-39), intent-ID reuse with different terms is refused (:73-74), and an empty observation never clears UNKNOWN (:87-93) | Execution; the Bisq status endpoint exists only in the fork experiment (`patrickdugan/bisq2` PR #1) |
| UTXO-Ref [`integrations/cashu-bitvm/claim_v1.py`](https://github.com/patrickdugan/UTXO-Ref/blob/3d053c02b430b83a6dfe63ab77ec70afe311de88/integrations/cashu-bitvm/claim_v1.py) | `PaymentClaimV1`, 178 bytes:<br>version 1, network 1, contract_id 32, claim_id 32, recipient_commitment 32, amount_sats 8, block_hash 32, min_conf 4, expiry_height 4, policy_digest 32.<br>Domain `UTXOREF-CASHU-BITVM-CLAIM-V1\0`. `UnverifiedProofReceiptV1` refuses `verified` (:79-80) | **No txid, vout or script fields.** The paid output lives only in the future private witness. The block hash is a claim (HANDOFF_VPS.md:47). It verifies nothing |
| Raito-Scrypt [`chain-sp1/host/src/bin/pay-verify.rs`](https://github.com/patrickdugan/Raito-Scrypt/blob/dfbe57ff6d02f8a9678e7ca21e98b8da9489ff99/chain-sp1/host/src/bin/pay-verify.rs) | Verifies a compressed SP1 payment proof against four pinned vkeys (:31-37). Decodes the 349-byte statement (:40-50) and optionally writes `btc_payment_v1` receipt JSON (:52-65) | Groth16 verification (that is `pay-wrap` and `sp1-verifier`); unspentness; freshness. The receipt hardcodes `"verified":true` |
| Raito-Scrypt `chain-sp1/pay-core/src/lib.rs:15-17` | `STATEMENT_LEN = 349`, domain `LIGHTO-BTC-PAYMENT-v1`. Layout per pay-verify.rs:40-50:<br>domain 32, node/leaf/segment vkeys 3×32, top_digest 32, start_is_genesis 1, tip_height 4, tip_hash 32, tip_chainwork 32, block_height 4, block_hash 32, txid 32, vout 4, value 8, script_len 4, script_sha256 32, confirmations 4 | Claim ID, expiry, recipient commitment, network discriminant (the chain is implied by the domain, checkpoint and Core) |
| zk-rusto `services/supernode-rpc/src/statements.rs` @391c24a | `zk.statement.verify` for three kinds, all bound to Core at lookup:<br>NHC1 (Nova headers), BPG1 (709-byte SP1 Groth16 payment), NSP1 (Nova + SPV payment).<br>Verifiers run behind a separate-UID broker with SHA-256-pinned executables (BITCOIN_STATEMENTS.md:110-142) | `expected_txid`/`expected_vout` are **optional** (BITCOIN_STATEMENTS.md:35-40; statements.rs:771-772). Payment fields come from the verifier's stdout JSON: the gateway binds the statement bytes by SHA-256 (statements.rs:276) but does not re-derive txid, vout, value or script from them (:447-451). A compromised broker UID can forge a receipt (BITCOIN_STATEMENTS.md:131-132) |
| tl-collator `rust/tl-collator-wire`, `rust/tl-witness-service` @a184247 | TL-Canon v1 canonical JSON (`spec/schemas/tl-canon-v1.md`), signed tape, and an independent witness. The witness does challenge-bound signed heads plus exact compare-and-swap (CAS) and detects rollback and forks (WITNESS_PROTOCOL.md:51-57). PR #10 adds a bounded SSH transport (`src/ssh.rs`, 198 lines) | Independent hosting or durability. Fake-SSH tests "do not test real SSH encryption, authentication, host key verification or remote CAS durability" (SSH_TRANSPORT.md:37-42). One co-located witness is not anti-rollback (tl-witness-service README:32-34) |
| TradeLayer-Rust @41007c5 | Offline deterministic ledger replay, zero third-party crates (README.md:5, :17-34); staged migration (MIGRATION.md) | Real funds, network, consensus validation, keys (README.md:5) |
| tl-rpc @5609c42 | Rust read-only RPC contracts and a bounded TLS transport (PRs #3 and #4) | — |

**Recorded real-proof demonstrations (repository-recorded, not re-run).**

| Record | Facts as recorded | Caveats recorded alongside |
| --- | --- | --- |
| Raito-Scrypt `bitvm-demo/` @dfbe57f: README.md:19-27, `data/p1/payment.json`, `data/p1/run_summary.txt` (run 2026-10-27 at commit `24ab327`, zk VPS) | **H1 segment:** mainnet heights 959,743..959,994 from checkpoint 959,742 (`…7a80…eda0`, chainwork `0x13aad5e508e6972346a426329`). Tip 959,994 (`…cf21…79b5`), chainwork equal to Core's. 3:55, 19.0 GB.<br>**P1 payment:** tx `fd2fdd44…daa6` output 0, 2,010,000 sats to P2WPKH `0014 01e8…bc77`, block 959,984, 11 confirmations, 1,272,918 B proof; 10/10 forged witnesses rejected (`data/p1/negatives.json`).<br>**Groth16 wrap:** 356 B over the same 349-byte statement, 15:21. Pay vkey `0x00de861a80542b3089fed26b37ac4e1f4bb8664dcddadb3a6de5ae7205751e75` | Checkpointed, not genesis. No unspentness or freshness. Header sync stalled at 960,000 while the network was near 973k, so the range dates from July 2026 (README.md:61-63). Candidate keys are unapproved (:83-84) |
| Raito-Scrypt `bitvm-demo/regtest-trigger/out/{honest,tampered}/timeline.json`, `bitvm-harness/out/*/summary.json` | 0.5 BTC (50,000,000 sats) taproot lock `6945fe73…:0`, CSV 13 blocks.<br>**Honest:** payout at height **116**.<br>**Tampered:** assertion 23 makes chunk 8 fail; disprove leaf 8 sweeps at height **111**.<br>365 disprove leaves (364 chunks plus a public-input leaf), 1,110,848,926 B total, largest 3,948,063 B | `demo_only_wots_keys: true`. No presigned n-of-n graph or kickoff/challenge sequence, and disprove leaves are open to anyone. Non-standard transactions are mined with `generateblock` (README.md:80-86). Regtest only |
| zk-rusto `integrations/*/fixtures` @391c24a (BITCOIN_STATEMENTS.md:249-282) | `payment.bpg1`: the same `fd2fdd44` output as a 709-byte BPG1 bundle.<br>`payment959984.nsp1`: the same payment via Nova plus SPV, with no SP1.<br>`tip959994.nhc1`: 1,000 headers ending at the payment proof's tip.<br>CI `bitcoin-statements.yml` runs the real-fixture gateway tests directly and through the broker | Checkpoints are operator-pinned; keys are candidates; "Core's chainwork equality stands in for" best-chain selection (:290-292). Header and payment proofs are not required to agree (:305-307) |

**Synthetic tests (pass without any real proof or real rail):**
- BAN `tests/` (offline, fake node);
- UTXO-Ref `test_claim_v1.py` (encoding and mutation);
- zk-rusto isolation and lifecycle suites. Its own decision record keeps synthetic CI, authentic
  crypto and OS isolation as separate categories and marks the Raito authentic gate **BLOCKED**
  (`docs/evidence/raito-live-acceptance/decision.md:4-20`);
- tl-collator witness and SSH tests (synthetic keys, fake SSH).

**Local-only artifacts (not on any remote branch I read):**
- **Spiral checkout (untracked, not on any Spiral branch):**
  - `model/payment_proof.ts`: BIP340-signed fiat payment records, `judgeProof`, and a reversal
    notice; directly relevant to `PayoutReceiptV1`.
  - `model/schnorr.ts`: BIP340 checked against vectors 0–17.
  - `paper/bisq_for_agents.md`: attested auto-confirm, oracle payout via adaptor signatures,
    reversal bond.
  - `paper/ark_cash_design.md` and `model/ark_cash.ts`.
  - Spiral's remote is public, so check disclosure before committing these.
- **Proof artifacts:** `Raito-Scrypt\proof-artifacts\` is gitignored. The zk VPS was shelved on
  2026-10-29 and its artifacts were archived to `C:\Users\patri\zk-vps-archive-20261029`; I took
  this from session notes and did not re-check it.
- **BAN `cashout.py`/`arena_contract.py` patch:** see A.4.

**Designs, not implementations:**
- the Cashu×BitVM gates G1–G5 (DESIGN.md:22-34, HANDOFF_VPS.md);
- zk-rusto `docs/PROOF_BACKENDS_PLAN.md` (evidence branch);
- BAN `docs/ARCHITECTURE.md:37-39` (the attestation must bind rail, amount, currency, reference,
  recipient commitment, intent, window and nullifier);
- the Ark-TradeLayer `vtxo-loan-system` README (an attestation engine and "event witnesses" for
  payments);
- `bitcoin-payments` README.md:57-58 and :168, the strategic split.

**Missing:**
- handle namespace and alias records;
- private destination enrollment;
- payout intent;
- provider quote and inventory reservation;
- BUY-side selection on any readable branch;
- payout ledger and state machine;
- rail adapter (Jawwal or other);
- signed payout receipt and reconciliation;
- a gateway policy that *requires* the expected outpoint, script and value;
- approved (non-candidate) SP1/Nova keys;
- a current-tip checkpoint;
- a production BitVM graph;
- any Cashu mint integration (G5).

### A.3 Discrepancies found during the refresh

1. **Stale spec on the Bitcoin branch.** Raito-Scrypt `docs/LIGHTO_P1_PAYMENT.md` @dfbe57f still
   describes the **Litecoin** statement:
   - the domain `LIGHTO-LTC-PAYMENT-v1` (:55);
   - "reject the segwit marker" (:21-22).

   The Bitcoin code uses `LIGHTO-BTC-PAYMENT-v1` and parses segwit, taking the txid over the
   stripped serialization. Treat the code (`pay-core/src/lib.rs:15-17`, `pay-verify.rs:40-50`) as
   the spec until the doc is fixed.
2. **Stale recorded scope line.** `bitvm-demo/data/p1/pay_verify.txt` (recorded at `24ab327`)
   prints `scope=inclusion_under_header_context_rules_without_scrypt_pow_not_unspent`. The
   current binary prints `…bitcoin_header_rules_with_sha256d_pow_not_unspent` (pay-verify.rs:51;
   fixed in `dfbe57f`). The recorded artifact predates the `RECEIPT_JSON` path, so no recorded
   `btc_payment_v1` receipt exists in `bitvm-demo/data`.
3. **Two payment-statement ABIs, both legitimate, not interchangeable.**
   - `PaymentClaimV1` (178 B) hides the output and binds a recipient commitment, claim ID and
     expiry.
   - `LIGHTO-BTC-PAYMENT-v1` (349 B) publishes txid, vout, value and script hash and has no claim
     ID or expiry.

   Neither alone binds a payout intent. See D.4.
4. **The adapter's tests mix network labels.** The collator witness example uses
   `"network": "LTCTEST"` (WITNESS_PROTOCOL.md:17). Reusing the witness pattern for this product
   needs its own domain and network strings, not the collator's.

### A.4 Ownership to preserve

| Area | Owner | This plan's stance |
| --- | --- | --- |
| Cashu×BitVM G0–G5 proving | UTXO-Ref PR #9 `HANDOFF_VPS.md` (VPS handoff) | Consume only its *versioned VERIFIED receipt* when one exists. No competing prover. If its VPS is the `zk` box, session notes say that box was shelved on 2026-10-29; I have not verified that, and it would leave the gate with no host |
| SP1 Bitcoin payment pipeline, BitVM demo | Raito-Scrypt `research/bitcoin-bitvm` | Reference evidence profile only |
| Statement verification gateway, Nova/SP1 backend plan, fail-closed acceptance | zk-rusto-no-bitcoino (`feat/cheap-btc-proofs`, evidence branch) | Proposed follow-up (G.2) is a small policy change *inside* that work, not a new verifier |
| Witness, transport, TL-Canon | tl-collator Rust series (RUST-17x) | Pattern reuse later; no dependency in the first slice |
| TradeLayer consensus migration | TradeLayer-Rust `MIGRATION.md` | Out of scope; no alias, intent or payout state in consensus crates |
| Bisq 2 trade-status endpoint | `patrickdugan/bisq2` fork experiment (BAN `upstream-experiments/`) | Unchanged |
| BAN `cashout.py` / `arena_contract.py` | **Does not exist** | Searched 2026-10-30, all negative: every BAN branch (BAN has no forks), the git history of all 64 repos under `GitHub\`, all branches of `patrickdugan/P2P-Settlement-Arena`, and filesystem searches of `GitHub\`, `Codex\` and `Downloads\` (7 levels deep, then unlimited depth). Patrick: "it'd be on a repo or otherwise make it", and he confirmed `arena_contract.py` is the BAN ↔ P2P-Settlement-Arena contract. The slice creates `src/ban/cashout.py` and `src/ban/arena_contract.py` (spec D.5) |
| P2P-Settlement-Arena (Bisq Easy lab, ControlArena Setting) | `patrickdugan/P2P-Settlement-Arena` `main` @`0f8262723d761b34890c49e04e80e5e2254f5387` | Its scoring schema and role rules are an input to D.5. A `cashout-btc-first` profile there is arena-side work (G.12), not part of BAN's slice |

---

## B. End-to-end architecture

### B.1 Actors and what each is authoritative for

| Actor | Authoritative for | Not authoritative for |
| --- | --- | --- |
| **S** sender wallet | Its own BTC inputs (consensus signatures), its intent and fee caps, its refund script | The recipient's identity; delivery |
| **R** recipient key (Nostr secp256k1/BIP340) | Its alias record content, its destination enrollments, optional receipt acknowledgments | The handle-to-key binding (that belongs to D) |
| **D** namespace operator (NIP-05 domain) | `handle@domain → pubkey`, uniqueness within its domain | Record content; destinations |
| **N** relays | Nothing (untrusted cache and transport) | — |
| **P** liquidity provider (**buys** BTC, holds local-wallet float) | Its quotes, reservations, deposit scripts, funding acceptance, payout authorization, receipts | Whether the rail actually credited R (unless the rail signs) |
| **V** evidence verifier | P's own Core: P's deposits. zk-rusto gateway: proof validity under pinned programs plus Core agreement at lookup | Unspentness (Core's view only), checkpoint authenticity, delivery |
| **J** local payout rail (Jawwal Pay, unverified) | Credit to the destination wallet, if it exposes authenticated status | Anything on Bitcoin |
| **W** independent witness (optional, tl-collator pattern) | Monotonic signed heads of a log (alias records, P's ledger) | Log content correctness |
| **X** referee (optional, later: BitVM/UTXO-Ref, Cashu mint) | Enforcing a bond or issuance against a *verified* receipt | Fiat delivery |

### B.2 Flow

```mermaid
sequenceDiagram
  autonumber
  participant R as Recipient key
  participant D as Domain (NIP-05)
  participant N as Relays
  participant S as Sender wallet
  participant P as Provider (buys BTC)
  participant B as Bitcoin / P's Core
  participant J as Jawwal (unverified)
  R->>D: register handle (D's own auth)
  R->>N: AliasRecordV1 (signed, seq, payout commitment C, providers)
  R->>P: DestinationEnrollmentV1 (private, signed; opens C)
  P-->>R: EnrollmentAckV1 (signed)
  S->>D: GET /.well-known/nostr.json?name=handle (no redirects)
  S->>N: fetch AliasRecordV1 from 2+ relays; verify; pin max seq
  S->>P: PayoutIntentV1 (C, rail, currency, amount, caps, refund script, nonce, expiry)
  P-->>S: ProviderQuoteV1 (signed; fresh deposit script; reservation; expiry)
  S->>B: broadcast funding tx to deposit script
  B-->>P: Core watch-only: output, value, confirmations
  P->>P: FundingAcceptanceV1, then PayoutAuthorizationV1 (write-ahead)
  P->>J: payout(idempotency key, destination, minor units)
  J-->>P: status / webhook (authenticity unverified)
  P-->>S: PayoutReceiptV1 (signed)
  P-->>R: PayoutReceiptV1 (signed)
  R-->>P: RecipientAckV1 (optional, signed)
```

### B.3 Every transition: authentication, persistence, retry

| # | Transition | Authenticated by | Verified by | Persisted (who, what) | Idempotency / retry | Failure handling |
| --- | --- | --- | --- | --- | --- | --- |
| T0a | Handle registration | D's own account system (out of scope) plus D's TLS and DNS | S at resolve time | D: `nostr.json` | Re-registration is D's policy | D can rebind: S pins pubkeys, not handles (NIP-05 §"follow public keys", 05.md:70-72) |
| T0b | Publish `AliasRecordV1` | R (BIP340 event signature) | S | Relays (cache); R keeps seq and record ID | Republish same event ID; a new seq for any change | Relay withholding: S needs 2+ relays plus D's relay hint |
| T0c | `DestinationEnrollmentV1` R→P (private) | R signature; P checks the commitment opening and that C is in R's current record | P | P: encrypted destination vault keyed by (R pubkey, C); R: salt | Same (R, C) is a no-op | P rejects if C is absent from R's record or R's record is revoked |
| T1 | Resolve handle | D (binding) plus R (record signature) | S | S: pin (handle → pubkey, max seq, record ID, first-seen) | Re-fetch; **never accept a lower seq** | Equivocation or quorum disagreement → refuse intent (C.6) |
| T2 | `PayoutIntentV1` | S (an ephemeral key is enough) | P | S persists before sending | `intent_id` is deterministic; P returns the same quote for the same `intent_id` while it is valid | — |
| T3 | `ProviderQuoteV1` + reservation | P (BIP340) | S: P's key is in R's record provider list; caps; expiry; network; standard script type | P: reservation row (TTL ≤ quote expiry) and quote; S: quote | Same `intent_id` gets the same quote; after expiry, a new `quote_id` | Inventory gone → no quote. Never quote unreserved inventory |
| T4 | Funding tx | Bitcoin consensus | P (own Core) | S persists the raw tx **before** broadcast | Rebroadcast the *same* tx. RBF changes the txid: P matches by deposit script and quote and accepts one qualifying output | Underpay, overpay or late → the explicit policies in the quote (B.5) |
| T5 | `FundingAcceptanceV1` | P (signs what its Core shows) | Third parties may re-check with a proof (BPG1/NSP1, later PaymentClaimV1) | P ledger: `UNIQUE(outpoint)`, `UNIQUE(quote_id)` | Re-scan is idempotent | Reorg below `min_conf` before authorization → back to FUNDING_SEEN |
| T6 | `PayoutAuthorizationV1` | P (internal policy: limits, optional two-person rule) | P's auditor; W if used | P: written **before** any rail call | `idempotency_key = H(quote_id)`: exactly one per quote | Alias revoked or C changed since the quote → HOLD (B.5) |
| T7 | Rail submission | P's merchant credentials at J (unverified) | J | P: attempt row with request digest | Rail idempotency key or unique merchant reference (**capability unverified**) | Timeout → `PAYOUT_UNKNOWN`. Never resubmit while UNKNOWN (the BAN `recovery.py:36-39` semantic). Resolve only by status query or statement |
| T8 | `PayoutReceiptV1` | P (BIP340) plus a rail evidence digest (a signed webhook only if J offers one) | S, R | S, R, P | The receipt ID is derived from `idempotency_key` | Missing rail evidence → receipt marked `provider_attested_only` |
| T9 | Reconciliation | P (statement versus ledger); optional W signature over the ledger head | P's auditor | P: `ReconciliationRecordV1` | Per period | A mismatch opens a dispute; payout UNKNOWN stays UNKNOWN |
| T10 | Refund | Bitcoin consensus (P signs the refund tx) | S | P: `RefundRecordV1` | One refund per quote | — |

### B.4 Provider ledger state machine (reference provider)

```
INTENT_RECEIVED -> QUOTED -> EXPIRED (reservation released)
QUOTED -> FUNDING_SEEN -> FUNDING_ACCEPTED -> PAYOUT_AUTHORIZED -> PAYOUT_SUBMITTED
PAYOUT_SUBMITTED -> PAYOUT_CONFIRMED | PAYOUT_FAILED | PAYOUT_UNKNOWN
PAYOUT_UNKNOWN -> PAYOUT_CONFIRMED | PAYOUT_FAILED          (only on an observed rail status)
PAYOUT_CONFIRMED -> RECEIPTED -> RECONCILED
PAYOUT_FAILED -> REFUND_DUE -> REFUNDED
FUNDING_SEEN (after expiry) -> LATE_FUNDING -> REFUND_DUE | REQUOTED (at the then-current rate)
FUNDING_ACCEPTED | PAYOUT_AUTHORIZED -> HOLD (alias revoked or C changed) -> PAYOUT_AUTHORIZED | REFUND_DUE
any -> DISPUTED (manual)
```

**Invariants (each gets a test in F.3):**
- **I1:** at most one `PAYOUT_AUTHORIZED` per `quote_id`.
- **I2:** at most one quote per funding outpoint (the outpoint nullifier).
- **I3:** each deposit script belongs to exactly one quote and is never reused.
- **I4:** nothing leaves `PAYOUT_UNKNOWN` except an observed rail status.
- **I5:** the reservation is held from QUOTED until EXPIRED, REFUNDED or RECONCILED.
- **I6:** `net_payout_minor` and fees are fixed at the quote.
- **I7:** a funding block below `quote_created_height` is rejected, which stops an old output to
  a reused script from being replayed.
- **I8:** the alias record seq at authorization is at least the seq at the quote, and the record
  is not revoked.

### B.5 Partial failure and recovery

| Failure | Recovery |
| --- | --- |
| S crashes after broadcast | S restarts from its persisted intent, quote and raw tx, and polls P by `intent_id`. P is unaffected |
| P crashes between `PAYOUT_AUTHORIZED` and the rail call | On restart, the authorized-but-unsubmitted row is submitted once with the same idempotency key |
| P crashes after the rail call, before recording the response | The row is `PAYOUT_SUBMITTED` with no response, so it becomes `PAYOUT_UNKNOWN` and is resolved by status query |
| Rail timeout, duplicate webhook | Timeout → UNKNOWN. A webhook applies only if its reference equals `idempotency_key` and the state is SUBMITTED or UNKNOWN; duplicates are a no-op |
| Rail has no idempotency key and no query-by-reference | **Production gate fails**: manual reconciliation only. The slice uses a mock |
| Reorg after acceptance | Before authorization: back to FUNDING_SEEN. After: P bears the loss, so P chooses `min_conf` by amount |
| Underpay | Quote policy: refund minus network fee, or top-up within expiry |
| Overpay | Pay the quoted net and refund the excess, or treat it as a tip (quote field `overpay_policy`) |
| Late funding | `LATE_FUNDING`: refund, or re-quote at the current rate. **Never** pay at the stale rate |
| P lacks float at payout (oversold reservation) | `PAYOUT_FAILED` → REFUND_DUE. Reservations exist to make this a bug, not a business event |
| P disappears after funding | **Not recoverable in the slice.** This is custodial counterparty risk. Mitigations are later work: a provider bond with a referee, reputation, small limits |
| Alias key compromised after the quote | R publishes a revocation; P moves the payout to HOLD and requires a fresh recipient-signed confirmation or refunds. Compromise before enrollment is out of scope (C.5) |
| Relay withholds the newest record | S's quorum and its max-seq pin catch a *rollback* but not a never-seen update. Records carry `valid_until` so a withheld revocation expires the old record |

---

## C. Minimal Nostr-associated alias design

### C.1 Existing standards first (nips@400d157)

| Need | Use | Why / caveat |
| --- | --- | --- |
| Handle → key | **NIP-05** `/.well-known/nostr.json` | Domain-scoped human names. The local part is restricted to `a-z0-9-_.` (05.md:9). No redirects (05.md:101-103). Clients follow keys, not names (05.md:70-72) |
| Versioned signed record | **NIP-01 addressable event** (kinds 30000–39999, `d` tag) | Relays keep the latest per (kind, pubkey, d) (01.md:99), ties to the lowest ID (01.md:101). The `created_at` order is signer-chosen, so add an explicit monotonic `seq` and a `prev` hash. The kind number is **provisional and unassigned**: check the README kinds table first |
| Where to fetch | **NIP-65** relay list (kind 10002), plus NIP-05 `relays` (05.md:53) | — |
| Private messages (enrollment, intent, quote) | **NIP-17** + **NIP-44** + **NIP-59** gift wrap | NIP-04 is unrecommended (README). Needs ChaCha20 and HKDF, which Python's stdlib lacks, so it is deferred out of slice 1 |
| Expiry | **NIP-40** `expiration` tag | Relays should drop expired records; clients must also check `valid_until` themselves |
| HTTP to P | **NIP-98** HTTP auth | Optional for the API form of T2/T3 |
| Remote signer for R | **NIP-46** | Optional |
| P2P maker discovery | **NIP-69** P2P orders (kind 38383, `k` = `sell` or `buy`) | Inventory there is **self-asserted**. Which side `k` names must be checked per platform, the same direction risk as BAN |
| Provider reputation | **NIP-85** trusted assertions | Optional, later |
| Public payment targets | **NIP-A3** `payto` (kind 10133) | **Do not use for fiat or wallet destinations.** It publishes addresses in public events, including `revolut`, `paypal` and `cashme` (A3.md). Acceptable only for a public BTC or Lightning target, which this product does not need |
| Delegation / rotation | NIP-26 is **unrecommended** (README); no key-migration NIP is merged at 400d157 | A minimal rotation rule is defined below rather than adopting a draft |
| Timestamping | NIP-03 OpenTimestamps is **unrecommended** (README) | Use the witness pattern (C.6) if anti-equivocation must be stronger than a relay quorum |
| Comparisons | BIP-353 DNSSEC payment instructions; Lightning Address/LNURL (HTTPS); Cashu NUT-18 payment requests (with a Nostr transport) | BIP-353 gives offline-verifiable DNSSEC proofs, but it resolves a *payment target*. Here the payee of the BTC is P, chosen per payment, so a static target is the wrong primitive. NUT-18 is the right reference for the later Cashu path |

### C.2 Namespace and uniqueness

- **A name is `local@domain`.** Uniqueness is per domain and enforced by D. There is no global
  registry and no chain. A wallet may ship a default domain so users see `alice`, but the full
  name is always `alice@default.example`.
- **The domain is the trust anchor and can rebind names.** Defenses:
  - the sender pins the pubkey;
  - first payment to a new or changed pubkey shows a "new recipient" warning;
  - rebinding is visible as a record without a valid rotation chain (C.5).
- **Domain policy for the reference operator:**
  - first come, first served;
  - registration requires a signature from the key being bound;
  - names are skeleton-unique (C.7);
  - names are reserved for 90 days after release.

### C.3 Ownership proof

- **Binding:** `nostr.json` maps `local → pubkey` (D's assertion).
- **Possession:** the record is signed by that pubkey and names `d = "local@domain"` (R's
  assertion). Both must agree. A record whose `d` names a handle that `nostr.json` does not map to
  the signer is rejected.

### C.4 Record: `AliasRecordV1`

An addressable event: provisional kind, tags `d` = `local@domain` and `expiration`. The content is
TL-Canon v1 (sorted keys, safe integers, money as strings):

```json
{"v":1,"handle":"alice","domain":"pay.example","seq":7,
 "prev":"<event id of seq 6, or null for seq 1>","status":"active",
 "valid_until":1793500000,"recovery_pubkey":"<hex32>",
 "payout":[{"rail":"jawwal_pay","currency":"ILS","commitment":"<hex32>",
            "providers":["<P pubkey hex32>"]}],
 "rotation":null}
```

- `commitment = SHA256("CAG-PAYOUT-COMMIT-V1\0" || rail || 0x00 || canonical_destination || salt32)`.
- The salt is per provider, so commitments do not link across providers.
- The currency code is illustrative: the Jawwal currency and units are unverified.
- The record contains **no destination, no phone number and no wallet ID**. A lint test enforces
  this, and any `payto` tag is refused.

### C.5 Rotation, recovery, revocation

- **Revocation.** A record with `status: "revoked"`, seq+1, signed by the current key or the
  recovery key. It is terminal for that key: a new key needs a rotation.
- **Rotation (planned).** The new key publishes a seq+1 record with
  `rotation = {"prev_pubkey", "prev_record", "prev_sig"}`, where `prev_sig` is the old key's
  BIP340 signature over the new event ID. D updates `nostr.json`. S accepts it when
  `prev_sig` verifies against the pinned key.
- **Recovery (lost key).** A rotation signed by `recovery_pubkey` instead of the old key is valid
  only after a **72-hour pending window**. During it, S's resolver shows "recovery pending", and
  the old key can veto by publishing a revocation of the pending record. That defends against a
  stolen recovery key while the owner is online.
- **Domain-only rebind** (no old-key or recovery signature) is treated as a **new identity**: the
  "new recipient" warning, and no carry-over of S's pin.
- **Destination change.** A new commitment in a seq+1 record plus a new enrollment at P. Quotes
  bind (record ID, seq, commitment), and a change between quote and payout puts the payout on
  HOLD (B.5).

### C.6 Relay equivocation and stale cache

- **Monotonic pin.** S stores the highest (seq, record ID) seen per handle and refuses any lower
  seq.
- **Equivocation.** Two validly signed records with the same seq and different IDs freeze the
  alias: no intent until a higher seq resolves it.
- **Quorum.** At least 2 relays plus D's relay hint. Any validly signed higher seq wins.
  Disagreement without a higher seq means "stale or withheld": warn, and refuse when the amount is
  above a threshold.
- **Expiry.** `valid_until` is at most 30 days in the reference policy, so a withheld revocation
  or rotation eventually takes effect as expiry.
- **Later, if needed:** an independent witness signs `(handle, seq, record_id)` heads under a
  fresh challenge, the tl-collator WITNESS_PROTOCOL pattern with its own domain string. This adds
  rollback and fork detection across clients, not just within one client's cache.

### C.7 Unicode and lookalikes

- **Local part:** ASCII `a-z0-9-_.` only (the NIP-05 rule). Uppercase input is lowercased before
  lookup. Any other character is rejected, never mapped.
- **Domain:** stored and compared as IDNA2008 A-labels (punycode). It is displayed as a U-label
  only if it passes UTS #39 "highly restrictive" mixed-script rules; otherwise the punycode is
  shown.
- **Registration (D):** names are unique by **skeleton** (UTS #39 confusables plus the ASCII
  folds `0/o`, `1/l/i`, `rn/m`, `vv/w`, `-`/`_`/`.` stripped). `alice` blocks `a1ice` and
  `al_ice`.
- **Sending (S):** show the pubkey fingerprint and first-seen date. A first payment to a handle
  within edit distance 1 of a pinned handle triggers a confirmation.

### C.8 Private destination resolution

**The sender never learns the destination.**
- The public record carries only per-provider commitments.
- P learns the destination only from R's signed `DestinationEnrollmentV1`, sent R→P privately.
  Slice 1 uses an authenticated direct channel or fixture; NIP-17 gift wrap comes later.
- P stores destinations encrypted at rest, keyed by (R pubkey, commitment).
- P's quote names the commitment, never the destination. Receipts carry a rail reference, not the
  wallet ID.

**What remains visible:**
- the provider set in the public record;
- the amount and on-chain funding, which are public on Bitcoin regardless;
- P's knowledge of the destination and amount, which is unavoidable for a payout.

---

## D. Versioned contracts

### D.1 Conventions

- **Signed objects:** domain-separated SHA-256 over a fixed-width binary encoding, the style of
  `claim_v1.py` (unsigned big-endian, explicit widths, lowercase hex). Golden vectors per network.
  The alias record is the exception: it is a Nostr event, identified by its NIP-01 ID, with
  TL-Canon v1 content.
- **Networks:** the `claim_v1.py:8` discriminants (mainnet 0, testnet4 1, signet 2, regtest 3).
- **Units:** sats are `u64`. Local currency is an ISO 4217 code plus an explicit minor-unit
  exponent plus a `u64` amount. No floats anywhere. BAN's price precision 4 is converted
  explicitly, never reused as a payout unit.
- **Signatures:** BIP340 over the object ID.

### D.2 Contracts

| Contract | Key fields | Signed by |
| --- | --- | --- |
| `AliasRecordV1` (C.4) | handle, domain, seq, prev, status, valid_until, recovery_pubkey, payout[rail, currency, commitment, providers], rotation | R (or the recovery key) |
| `DestinationEnrollmentV1` | alias pubkey, record ID and seq, rail, canonical destination, salt, commitment, provider pubkey, created_at | R |
| `EnrollmentAckV1` | enrollment digest, provider pubkey, status (`accepted`, `rejected`, `name_check_unavailable`) | P |
| `InventoryAttestationV1` | provider pubkey, rail, currency, exponent, available_minor, max_per_payout_minor, observed_at, valid_until | P |
| `PayoutIntentV1` | version, network, alias pubkey, record ID, seq, recipient commitment, rail ID = SHA256(rail), currency, exponent, `amount_mode` (receive-exact or send-exact), amount, max_total_fee_sats, max_fee_bps, min_net_payout_minor, refund_script_sha256, sender_nonce32, expiry_unix | S (ephemeral key) |
| `EvidencePolicyV1` | accepted profiles, each with `approval` (`candidate`/`approved` + who and when):<br>`own_core_v1` {chain, min_conf, max_tip_lag};<br>`sp1_btc_payment_v1` {pay_vkey, node/leaf/segment words, groth16_vk_sha256, verifier sha256};<br>`nova_spv_payment_v1` {vk sha256, checkpoint states};<br>`cashu_bitvm_claim_v1` (**reserved; unverified, not accepted**) | P (named by digest in the quote) |
| `ProviderQuoteV1` | version, network, intent_id, provider pubkey, reservation_id, deposit_script plus its SHA-256, sats_required, overpay_policy, underpay_policy, rate (minor per BTC plus exponent), fee_sats, fee_minor, net_payout_minor, currency and exponent, quote_created_height, quote_expiry_height, quote_expiry_unix, min_conf, max_tip_lag, evidence_policy_digest, refund_fee_policy, `idempotency_key = SHA256("CAG-PAYOUT-IDEMP-V1\0" ‖ quote_id)` | P |
| `FundingAcceptanceV1` | quote_id, txid, vout, value, script_sha256, block_hash, block_height, confirmations (Core's count at acceptance), tip_hash_at_acceptance, evidence_profile, evidence_digest | P |
| `PayoutAuthorizationV1` | quote_id, funding acceptance digest, destination_ref (P-internal opaque ID, never the destination), net_payout_minor, currency, idempotency_key, alias seq at authorization | P |
| `PayoutReceiptV1` | quote_id, intent_id, idempotency_key, rail, rail_reference, amount_minor, currency, status (`delivered`, `failed`, `unknown`), rail_evidence_kind (`signed_webhook`, `api_status`, `manual`, `provider_attested_only`), rail_evidence_digest, delivered_at | P |
| `RecipientAckV1` | receipt digest, received (bool), observed_amount_minor | R |
| `RefundRecordV1` / `ReconciliationRecordV1` | quote_id, refund txid / period, ledger head hash, counts, rail statement digest, optional witness signature | P (and W) |

### D.3 The bindings this brief asks for, and where each lives

| Binding | Field(s) |
| --- | --- |
| Identity and version | Every object's version byte; alias record ID and seq in the intent and authorization |
| Recipient commitment | `AliasRecordV1.payout.commitment` → `PayoutIntentV1.recipient_commitment` → quote (through `intent_id`) → authorization `destination_ref` |
| Network | Intent and quote `network`; `EvidencePolicyV1` chain; `claim_v1` discriminants |
| TXID, vout, value, script | `FundingAcceptanceV1`; quote `deposit_script_sha256` and `sats_required`; checked against the evidence. For BPG1/NSP1, `script_sha256` must equal SHA256(deposit_script) |
| Proof and program identities | `EvidencePolicyV1` (pay vkey `0x00de861a…`, program words, Nova vk `e46bb069…`, verifier binary SHA-256) |
| Approved checkpoint and key policy | `EvidencePolicyV1.approval`. Every SP1/Nova key today is a **candidate**: accepted only when `mode = test` |
| Confirmations and freshness | Quote `min_conf` and `max_tip_lag`; acceptance records **Core's** count, not the in-proof count; record `valid_until` |
| Rail, currency, units | Intent and quote `rail`, `currency`, exponent |
| Net payout | Quote `net_payout_minor` (fixed); intent `min_net_payout_minor` |
| Quote expiry | `quote_expiry_height` and `quote_expiry_unix`; I7's lower bound `quote_created_height` |
| Fee caps | Intent `max_total_fee_sats` and `max_fee_bps`; the quote's fee fields must satisfy them |
| Idempotency | `intent_id`, `quote_id`, `idempotency_key`, outpoint nullifier |

### D.4 Existing profiles: kept separate, with explicit mappings only where justified

| Profile | Keep as | Mapping |
| --- | --- | --- |
| BAN `PaymentClaim` (fiat-leg attestation, verifier fail-closed) | Fiat evidence interface | **M3, deferred.** A rail-signed `PayoutReceiptV1` could become a `PaymentClaim` (provider=rail, commitment=receipt digest, nullifier=idempotency_key), but only once a rail signs something. Until then the verifier stays fail-closed |
| UTXO-Ref `PaymentClaimV1` (178 B, hidden output) | Evidence profile `cashu_bitvm_claim_v1`, **unverified** | **M2, deferred to G1.** `contract_id = quote_id`, `amount_sats = sats_required`, `expiry_height = quote_expiry_height`, `minimum_confirmations = min_conf`, `policy_digest = SHA256(EvidencePolicyV1 ‖ quote_id)`. `recipient_commitment` waits for G1's commitment scheme. The ABI is unchanged |
| Raito `LIGHTO-BTC-PAYMENT-v1` (349 B) / zk-rusto `PaymentReceipt`, `SpvPaymentReceipt` | Evidence profiles `sp1_btc_payment_v1`, `nova_spv_payment_v1` | **M1, justified now (read-only).** The acceptance predicate compares receipt fields to the quote: script hash, value ≥ sats_required, block height between `quote_created_height` and `quote_expiry_height`, outpoint unused. It requires the expected outpoint and re-derives fields from the 349 bytes (G.2). No ABI change |
| Spiral `model/payment_proof.ts` (`judgeProof`) | Design reference for `PayoutReceiptV1` and reversal | None (local, TypeScript) |

### D.5 BAN ↔ P2P-Settlement-Arena contract (`src/ban/arena_contract.py`)

**Purpose.** A versioned, stdlib-only interchange contract between BAN's cashout objects and
[P2P-Settlement-Arena](https://github.com/patrickdugan/P2P-Settlement-Arena/tree/0f8262723d761b34890c49e04e80e5e2254f5387)
@`0f826272`, the deterministic Rust lab with a ControlArena Setting. It lets the arena model and
score the cashout direction, and lets BAN's simulated provider emit results in the arena's
scoring vocabulary. Nothing on either side touches a real rail, key or node.

**What the arena already fixes (and the contract must respect):**
- **Roles and order.** Bisq Easy is payment-first: the **BTC buyer pays fiat first**, then the
  seller sends BTC, with no escrow (`docs/PROTOCOL_PROFILES.md:9`).
- **Fiat evidence.** A payment *claim* is never an external bank event, and BTC moves only on the
  external event (`AGENTS.md:7`, `:19`).
- **Units.** Integer fiat cents and satoshis, with independent conservation (`AGENTS.md:6`).
- **Two separate outcome flags.** `passed` means the oracle behaved as designed. `attack_success`
  means a forbidden outcome happened (`AGENTS.md:9`). The two are never conflated.
- **Result lines.** The scenario line has `protocol`, `scenario`, `passed`, `attack_success`,
  `blocked_attacks`, `committed_events`, `final_phase`, `buyer_usd_at_risk_cents`,
  `seller_btc_at_risk_sats` and `safety_findings` (README.md:31). The control-state line has
  `kind:"control_state"`, `case`, `guard`, `phase`, `main_task_success`, `side_task_success` and
  more (`src/control.rs:401-402`).
- **Scope today.** USD only, $6–$600, with reputation gating (`PROTOCOL_PROFILES.md:15-16`).

**Role mapping (the direction check, encoded once).**

| Cashout actor | Arena role | Why |
| --- | --- | --- |
| Provider P (maker **BUY** offer) | `buyer` | P buys BTC and pays fiat |
| Sender S | `seller` | S delivers BTC |
| Recipient R | `fiat_payee` (new) | Fiat goes to a **third party**, not the seller. This is the triangulation shape `model/payment_proof.ts` guards against |

**Two profiles, deliberately not merged.**

| Profile ID | Order | Who bears exposure | Arena status |
| --- | --- | --- | --- |
| `cashout-btc-first` (this architecture, B.3) | S funds BTC → P pays R | S: `sender_btc_at_risk_sats` (P withholds or fails) | **New arena profile needed.** It is the mirror of Bisq Easy |
| `cashout-bisq-easy` | P pays R first → S sends BTC after R's signed ack or rail evidence | P: `provider_minor_at_risk` (S withholds) | Fits the existing Bisq Easy state machine with seller = S and buyer = P. The seller's "external fiat observation" becomes `RecipientAckV1` or rail evidence, because S cannot see R's wallet |

**Module contents.**
- **Constants.** `ARENA_CONTRACT_VERSION = "ban-arena-cashout/1"`, the two profile IDs, and
  `ROLE_MAP`, the table above as a frozen mapping. `ROLE_MAP["provider"] == "buyer"` is asserted
  at import time.
- **`ArenaScenarioV1`.** A deterministic TL-Canon-v1 export of one synthetic cashout case:
  - `profile`, `scenario`, `seed`;
  - integer `amount_sats`, `net_payout_minor`, `currency`, `exponent`;
  - `quote_expiry_height`, `min_conf`;
  - per-actor `behavior`;
  - the `expected` oracle (`blocked` or `exposure_observed`);
  - `source: "SYNTHETIC_FIXTURE"`.

  Behaviors: `honest`, `provider_withholds`, `sender_withholds`, `replay_funding`, `wrong_output`,
  `stale_chain`, `duplicate_payout`, `rail_timeout`, `late_funding`, `substituted_provider_key`,
  `alias_equivocation`, `claim_without_credit`. `scenario_id = SHA256("BAN-ARENA-SCENARIO-V1\0" ‖
  canonical bytes)`.
- **`parse_arena_line(line) -> ArenaResultV1`.** A strict parser for the two existing arena line
  kinds plus the proposed cashout fields (`sender_btc_at_risk_sats`, `provider_minor_at_risk`,
  `recipient_credited_minor`, `currency`, `exponent`). It rejects unknown or missing keys,
  non-integer amounts, and non-boolean `passed`/`attack_success`, with an exact key set per
  `kind`/`protocol`.
- **`ledger_trace_to_arena_lines(trace) -> list[str]`.** Converts a B.4 trace from BAN's simulated
  provider into arena-style score lines with `protocol: "cashout-btc-first"`. Refused attacks give
  `passed=true, attack_success=false`. An unmitigated `provider_withholds` gives
  `attack_success=true` and a positive `sender_btc_at_risk_sats`. That is the custodial risk shown
  honestly, the way the arena reports `seller-withholds`.
- **`check_conservation(trace)`.** Sats and fiat minor units are each conserved across S, P and
  R, and R is credited only by a modeled rail event, never by P's claim (the arena's
  claim-versus-bank-event rule).

**Out of BAN's slice (arena-side, separate owner):** implementing `cashout-btc-first` in the Rust
arena and importing `ArenaScenarioV1` there (G.12). BAN ships the contract, golden scenario
fixtures and its own export. The arena currently scores USD only, so non-USD scenarios are
marked `arena_supported: false` until the arena adds currencies (its README "Next upgrades" #2).

---

## E. Trust boundaries

| Boundary | What establishes it | What does **not** | State today |
| --- | --- | --- | --- |
| Proof validity | Soundness of SP1, Groth16 (BN254, SP1's setup) and Nova (Pallas/Vesta) for the **pinned** program; a pinned verifier binary actually run | A JSON `verified:true`, `proof_verified:true`, a receipt hash, a signed manifest (`claim_v1` README "Trust boundaries") | Pinned candidate keys; real fixtures verify in CI (zk-rusto). Raito's authentic gate is BLOCKED (decision.md) |
| Checkpoint trust | Operator pin of the start state | The proof (it starts *from* the checkpoint) | 959,742 (SP1 demo) and 958,986 (BPG1 fixture) are operator-pinned, not from genesis |
| Active-chain acceptance | Bitcoin Core `getblockhash` and chainwork at lookup (statements.rs:716-739) | Proven chainwork alone (a valid chain is not the best chain) | The gateway checks Core; the demo range is July 2026 |
| Freshness | Core tip versus evidence tip (`max_tip_lag`) and record `valid_until` | In-proof `confirmations` | Not enforced by policy anywhere yet |
| Unspentness | Core `gettxout` (Core's view; statements.rs:850-851) | Any inclusion proof | Not proven anywhere. **Not needed by P** for its own deposit |
| BitVM dispute enforceability | A presigned n-of-n graph, bonds, timeouts, standard-relay transactions, a live honest challenger | The demo (public WOTS seed, anyone-can-disprove, 2.3–3.9 MB leaves via `generateblock`) | Demo only. G4 is undone |
| Cashu mint solvency | Nothing cryptographic (threshold custody plus audits) | A payment proof (DESIGN.md:34, :48) | G5 is undone |
| Provider liquidity | Funded float plus a reservation honored, attested by P | `InventoryAttestationV1` (self-asserted), BAN advertised bounds, NIP-69 `amt`/`fa` | Not built; reservations are the slice's job |
| Actual fiat delivery | Rail-signed status (if Jawwal provides one), recipient acknowledgment, reconciliation | **Any Bitcoin proof**; P's receipt alone (`provider_attested_only`) | Jawwal capabilities are unverified |
| Name binding | D (TLS/DNS) plus R's signature plus the sender's pubkey pin | Relays; the handle string | Not built |
| Destination privacy | Commitments in public; enrollment only to P | Gift wrap alone if destinations are published elsewhere (NIP-A3) | Not built |
| Verifier isolation | Separate-UID broker, pinned binaries, no Core credentials in the broker (BITCOIN_STATEMENTS.md:110-142) | The same UID (dev mode). A compromised broker UID can forge (:131-132) | Built (zk-rusto) |

**Product framing (bitcoin-payments README.md:57-58, :168).** A sender spending BTC they already
hold is *paying in bitcoin*. A sender who buys BTC only to push it through to a Jawwal payout is
using *bitcoin as a payment rail*, and that "doesn't count as customer spending".
`PayoutIntentV1` should carry an optional, unverified `funding_source` hint
(`held_btc`/`bought_for_payment`/`unknown`) so metrics can tell the two apart. The protocol never
trusts that hint.

---

## F. Smallest valuable slice

### F.1 Where and why

**The slice goes in Bisq-Agent-Network**, branch `feat/cashout-alias-intent-v0`, cut from
`main` @ `0accf630`:
- BAN already owns maker selection and the direction semantics, Decimal monetary contracts, the
  finite fail-closed policy and the never-retry recovery journal. Provider-direction correctness
  can only be fixed where the direction lives.
- It is stdlib Python with an offline test culture (AGENTS.md), so the slice adds no paid
  resources and no proving.
- The alias and intent layer is concierge input, and fits BAN's "wallet SDK" milestone
  (README.md:113).

**Rejected homes:**
- *zk-rusto* is proof-verification infrastructure; the slice consumes it later (G.2).
- *UTXO-Ref* owns the claim ABI and the VPS-run gates.
- *TradeLayer-Rust and tl-collator* keep their consensus and migration boundaries.
- *A new repository* would duplicate BAN.

**BAN boundary kept.** The payout engine is a **simulated reference provider** under
`ban/sim/`, with a mock rail only. `policy.py` gains `submit_local_payout` and
`authorize_local_payout` as **DENY**, and the slice adds no executor.

### F.2 Interfaces (Python 3.11, stdlib)

```python
# src/ban/bip340.py  (verify only in src; signing helper lives in tests/)
def verify(pubkey32: bytes, msg32: bytes, sig64: bytes) -> bool: ...

# src/ban/alias.py
@dataclass(frozen=True)
class AliasRecordV1: handle: str; domain: str; pubkey: str; seq: int; prev: str | None
    status: str; valid_until: int; recovery_pubkey: str; payout: tuple[PayoutTarget, ...]
    rotation: Rotation | None; event_id: str
def normalize_handle(text: str) -> tuple[str, str]          # (local, A-label domain); raises
def parse_record(event: dict, *, now: int) -> AliasRecordV1  # NIP-01 id + sig + content schema
class AliasResolver:
    def __init__(self, nip05: Nip05Source, relays: Sequence[RecordSource], pins: PinStore,
                 *, quorum: int = 2): ...
    def resolve(self, name: str, *, now: int) -> Resolution   # raises Equivocation, Rollback,
                                                              # Revoked, Expired, BindingMismatch
# src/ban/intent.py
@dataclass(frozen=True)
class PayoutIntentV1: ...; def encode(self) -> bytes; def intent_id(self) -> str
@dataclass(frozen=True)
class ProviderQuoteV1: ...; def encode(self) -> bytes; def quote_id(self) -> str
def check_quote(quote, sig, intent, resolution, *, tip_height: int, now: int) -> None

# src/ban/cashout.py   (or the existing local patch, if it is found; see H step 1)
def cashout_shortlist(snapshot: Snapshot, intent: PayoutIntentV1,
                      inventory: Mapping[str, InventoryAttestationV1], *, now: int) -> dict
    # maker_direction == "BUY" only; inventory signed by the maker's key, fresh, sufficient

# src/ban/evidence.py
class FundingEvidence(Protocol):
    def accept(self, quote: ProviderQuoteV1, *, now: int) -> FundingAcceptanceV1: ...
class FixtureEvidence: ...            # tests and demo
class CoreRpcEvidence: ...            # loopback regtest only, optional, off in CI

# src/ban/sim/provider.py, sim/ledger.py, sim/rails.py
class PayoutLedger:                   # SQLite, BEGIN IMMEDIATE, UNIQUE(outpoint), UNIQUE(quote_id)
    def transition(self, quote_id: str, to: State, **evidence) -> Row: ...
class LocalPayoutRail(Protocol):
    def submit(self, idempotency_key: str, destination_ref: str,
               amount_minor: int, currency: str) -> RailResult: ...
    def status(self, idempotency_key: str) -> RailResult: ...
class MockJawwalRail: ...             # scripted outcomes: delivered, failed, timeout, duplicate
```

### F.3 Acceptance tests (each one must exist and pass)

- **Direction:**
  - `cashout_shortlist` never returns a SELL maker;
  - the existing buyer `shortlist` still returns only SELL makers (regression);
  - missing, stale, insufficient or wrong-key inventory attestation → excluded;
  - `amount_mode` receive-exact versus send-exact are both priced in Decimal with explicit
    rounding.
- **Alias:**
  - `nostr.json` pubkey ≠ record signer → `BindingMismatch`;
  - bad signature, bad event ID;
  - seq lower than the pin → `Rollback`;
  - same seq, different ID → `Equivocation` (alias frozen);
  - `valid_until` passed → `Expired`;
  - revoked → intent refused;
  - rotation without `prev_sig` → treated as a new identity;
  - recovery rotation inside the 72 h window → pending; old-key veto honored;
  - non-ASCII local part rejected; IDN domain compared as an A-label;
  - skeleton collision helper (`a1ice` versus `alice`);
  - any `payto` tag, or any destination-like field in public content → rejected (lint);
  - relay quorum disagreement → warning, or refusal above the threshold.
- **Intent and quote:**
  - golden vectors for both encodings on all four networks;
  - wrong network;
  - wrong recipient commitment;
  - quote signed by a key that is not in the record's provider list (**substituted provider
    key**);
  - quote for a different `intent_id`;
  - fee above the cap; net below the minimum;
  - **expired quote** (by height and by time);
  - deposit script reused across quotes → rejected.
- **Evidence:**
  - **wrong output** (script hash, vout, value below `sats_required`);
  - funding below `quote_created_height` (**replay of an old output**);
  - funding after expiry → `LATE_FUNDING`, never paid at the old rate;
  - **stale chain** (evidence tip lag > `max_tip_lag`, or block not on the fixture's active
    chain);
  - Core confirmations < `min_conf`;
  - an evidence object containing `"verified": true` with no configured verifier → rejected;
  - candidate keys under `mode = production` → rejected;
  - unpinned program words → rejected.
- **Ledger and payout:**
  - the same outpoint presented for two quotes → the second is rejected (**replay**);
  - the same quote authorized twice → one `submit` call (**duplicate payout**);
  - rail timeout → `PAYOUT_UNKNOWN`, no resubmit, resolved only by `status()`;
  - rail failure → `REFUND_DUE` (**provider failure**);
  - duplicate webhook is a no-op;
  - crash injection between authorize and submit, and between submit and record → correct state
    after restart;
  - reservation released on expiry;
  - alias revoked or commitment changed between quote and payout → `HOLD`;
  - receipt bound to `idempotency_key` with a valid P signature;
  - `provider_attested_only` labelling when the rail evidence is absent.
- **Policy:** `submit_local_payout` and `authorize_local_payout` → DENY; unknown cashout actions
  → DENY.
- **Arena contract (D.5):**
  - `ROLE_MAP` maps the provider to the arena `buyer`, never `seller`;
  - golden `scenario_id` for every behavior and both profiles;
  - `parse_arena_line` accepts real arena lines (fixtures copied from the arena README sample and
    the `control.rs` format) and rejects unknown, missing or non-integer fields;
  - every refused F.3 attack exports as `passed=true, attack_success=false`;
  - unmitigated `provider_withholds` exports `attack_success=true` with
    `sender_btc_at_risk_sats > 0`;
  - `claim_without_credit` never reaches RECEIPTED;
  - conservation holds over every exported trace;
  - non-USD scenarios are flagged `arena_supported: false`.
- **Golden vector cross-check:** BIP340 test vectors (vendored CSV with its source URL and
  SHA-256 recorded).

### F.4 Dependencies

None new: stdlib only, per BAN AGENTS.md. Fixtures are synthetic and labelled
`SYNTHETIC_FIXTURE`. `CoreRpcEvidence` is optional and needs a user-run loopback regtest node; it
is off in CI.

### F.5 Demo

```
PYTHONPATH=src python -m ban.cli cashout-demo --fixture fixtures/cashout_demo.json
```

The demo prints each transition from B.3 against a synthetic world:
- domain `pay.test` (NIP-05 JSON fixture) and two fixture "relays";
- Alice's record signed by a test key, and an enrollment at provider P1;
- an offerbook with both BUY and SELL makers, where the SELL makers are visibly excluded;
- P1's signed quote with a fresh regtest deposit script;
- fixture funding evidence, or real regtest funding if `BAN_REGTEST_RPC_URL` is set;
- the mock Jawwal payout (`pending` → `delivered`) and a signed receipt;
- each attack from F.3 replayed and refused.

There is no network, real money, real rail or proof.

### F.6 Out of the slice (stated, not hidden)

- NIP-44/59 encryption and live relay sockets;
- any real Jawwal call;
- the zk-rusto client;
- BitVM bonds;
- Cashu;
- persistence of P's destination vault beyond SQLite with a test key;
- legal and licensing analysis for operating a cashout provider.

---

## G. Prioritized build plan

| # | Work | Repo / owner | Depends on | Notes |
| --- | --- | --- | --- | --- |
| G.1 | **Slice 1** (F): alias → private intent → BUY-side quote → simulated payout ledger | BAN, new branch | Read the local cashout patch first | No proving; the recommended next step |
| G.2 | Gateway payment policy: optional `require_expected_output`, requiring `expected_txid`, `expected_vout`, `expected_script_sha256`, `min_value_sats` and `min_block_height`; the gateway re-derives the 349-byte statement fields itself and compares them to the verifier receipt | zk-rusto, branch `feat/statement-expected-output` @`eb1bc54` (stacked on `feat/cheap-btc-proofs`) | — | **Built 2026-10-30; CI green:** Rust CI; Isolated statement verifier; real-proof workflow run 41014986866, including the separate-UID broker step. The genuine BPG1 proof passes the gateway's own statement decode. PR not opened (no API auth) |
| G.1 status | — | BAN `feat/cashout-alias-intent-v0` @`2ae98c6` | — | **Built 2026-10-30.** CI green; 152 tests re-run on Linux and 93 on Windows; demo refuses 30/30 attacks. **Do not merge alone:** G.1 never re-checks funding before payout. G.5 adds that re-check (I9), so merge G.1 and G.5 as one stack |
| G.5 status | — | BAN `feat/cashout-regtest-evidence` @`3eb4406` (stacked on G.1) | G.1 | **Built 2026-10-30; I9 fixed and verified.** Verification of `332cdbb` found a payout reaching the rail after funding vanished (HOLD resume, crash-recovery `submit`). `3eb4406` re-judges funding in `authorize()` from FUNDING_ACCEPTED and HOLD, and in `submit()` before `begin_attempt`. It treats re-mining in another block as a rejection and rebinds an unsent authorization to the current acceptance (refused once a rail attempt exists). 181 offline tests re-run on Linux. CI run 41060779277: offline job plus a real-node regtest job on Bitcoin Core 31.1 (SHA-256 pinned), both green |
| G.12 status | — | P2P-Settlement-Arena `feat/cashout-profiles` @`bce93eb` | G.1 | Built; 74 Rust tests, format and clippy pass; BAN parses both profiles' output. No PR, so CI has not run |
| G.3 | Jawwal capability verification: API and auth, sandbox, idempotency or merchant reference, status query, webhook signing, currency and units, limits, KYC, provider eligibility | Patrick / provider (external) | — | **Production gate.** Without idempotency or status query: manual reconciliation only |
| G.4 | NIP-17/44/59 transport for enrollment, intent and quote; live relay adapter (loopback-reviewed) | BAN (adapter), reviewed crypto | G.1 | Needs a reviewed ChaCha20/HKDF implementation or an isolated dependency |
| G.5 | `CoreRpcEvidence` against regtest, then signet: P's own-node deposit acceptance | BAN | G.1 | Cheap and realistic |
| G.6 | Third-party evidence: S-side dispute packet = quote + BPG1/NSP1 via the G.2 gateway | BAN ↔ zk-rusto | G.2, G.5 | Uses existing fixtures; no new proving |
| G.7 | Key approvals and a current-tip checkpoint for the SP1/Nova programs | Patrick (approval); zk-rusto and Raito owners | — | All keys are candidates today |
| G.8 | Doc fixes: Raito `docs/LIGHTO_P1_PAYMENT.md` → the BTC statement; re-record `pay_verify.txt` with the current scope line | Raito-Scrypt owner | — | A.3 items 1–2 |
| G.9 | Cashu×BitVM G1 → G2 (verified receipt), then M2 mapping | UTXO-Ref VPS handoff | Host availability (A.4) | Not this plan's to run |
| G.10 | Bonded provider: P posts a BTC bond in a referee contract; S's dispute packet plus a missing rail-signed receipt by a deadline → slashing | UTXO-Ref / BitVM research | G.6, G.9, G.3 (needs a rail-signed delivery signal or arbitration) | Research. Recipient acknowledgments are gameable, so this needs rail evidence or arbitration |
| G.11 | Witnessed alias and ledger heads (tl-collator pattern, own domain strings) | tl-collator crates reused | G.1 | Only if quorum and expiry prove insufficient |
| G.12 | Arena profiles `cashout-btc-first` (new mirror profile: provider-withholds, replay, late funding) and `cashout-bisq-easy` (seller = sender, buyer = provider, third-party payee); import `ArenaScenarioV1` | P2P-Settlement-Arena owner (Rust, zero deps) | G.1 (D.5 contract and fixtures) | Gives the cashout direction adversarial scoring and a ControlArena side task ("induce payout without funding") |

---

## H. Next bounded implementation prompt

> **Task: BAN cashout slice v0, alias → private intent → BUY-side quote → simulated payout ledger.**
>
> **Repository and branch.** `patrickdugan/Bisq-Agent-Network`. Cut branch
> `feat/cashout-alias-intent-v0` from `main` at `0accf630cf17b12f72679fd0d5344744060ae208`. Work in
> a separate git worktree; do not touch other checkouts. Python 3.11, **standard library only**;
> follow `AGENTS.md` (Decimal money, source labels, fail-closed unknowns, no execution paths).
>
> **Step 1 (settled 2026-10-30).** The earlier `cashout.py`/`arena_contract.py` patch does not
> exist on any repo (A.4). Create the BUY-side selection as `src/ban/cashout.py` and the
> BAN ↔ P2P-Settlement-Arena contract as `src/ban/arena_contract.py`, per D.5.
>
> **Build (spec: `Spiral/paper/cash_app_global_architecture.md` sections B.3, B.4, C.4–C.8, D.2,
> D.5, F.2).**
> 1. `src/ban/bip340.py`: BIP340 verify, plus a test-only signer in `tests/`. Vendor the official
>    BIP340 test-vectors CSV as a fixture, with its source URL and SHA-256.
> 2. `src/ban/alias.py`: NIP-05 binding (fixture source, no redirects), NIP-01 event ID and
>    signature, `AliasRecordV1` content in TL-Canon v1, the monotonic seq pin store (SQLite),
>    equivocation, rollback, expiry and revocation, rotation (old-key co-signature) and recovery
>    (72 h pending window plus veto), ASCII local part and A-label domain, a skeleton helper, and
>    the no-destination/no-`payto` lint.
> 3. `src/ban/intent.py`: `PayoutIntentV1`, `ProviderQuoteV1`, `InventoryAttestationV1`,
>    `EvidencePolicyV1`, `FundingAcceptanceV1`, `PayoutAuthorizationV1` and `PayoutReceiptV1`.
>    Use domain-separated SHA-256 over fixed-width big-endian encodings in the style of UTXO-Ref
>    `claim_v1.py`, the network discriminants from `claim_v1.py:8`, and golden vectors for all
>    four networks. Add `check_quote()`.
> 4. BUY-side selection (step 1 decides the file): `maker_direction == "BUY"` only, with a fresh
>    `InventoryAttestationV1` signed by the maker's key and enough capacity. Leave
>    `concierge.shortlist` unchanged and add a regression test that it still returns only SELL
>    makers.
> 5. `src/ban/evidence.py`: a `FundingEvidence` protocol, `FixtureEvidence`, and an optional
>    loopback-only `CoreRpcEvidence` (skipped unless `BAN_REGTEST_RPC_URL` is set).
>    A `"verified": true` field is never authority.
> 6. `src/ban/sim/{ledger,provider,rails}.py`: the B.4 state machine on SQLite (`BEGIN
>    IMMEDIATE`, `UNIQUE(outpoint)`, `UNIQUE(quote_id)`, write-ahead authorization) and
>    invariants I1–I8. `MockJawwalRail` scripts delivered, failed, timeout and duplicate webhook.
>    UNKNOWN is resolved only by `status()`.
> 7. `policy.py`: add `authorize_local_payout` and `submit_local_payout` as DENY. Add a
>    `cashout-demo` CLI command per F.5, driven by `fixtures/cashout_demo.json` (labelled
>    `SYNTHETIC_FIXTURE`).
> 8. Docs: `docs/CASHOUT.md`, covering the trust boundaries (copy the E rows that apply), what is
>    simulated, and that Jawwal capabilities are unverified.
> 9. `src/ban/arena_contract.py` per D.5: `ROLE_MAP`, `ArenaScenarioV1` with golden fixtures under
>    `fixtures/arena/`, `parse_arena_line`, `ledger_trace_to_arena_lines` and
>    `check_conservation`. The `cashout-demo` command also writes `out/arena_cashout.jsonl`.
>    Do not modify P2P-Settlement-Arena; its profiles are G.12.
>
> **Tests.** Every test listed in F.3, in `tests/test_cashout_*.py`. Done means all of these pass:
> - `PYTHONPATH=src python -m unittest discover -s tests -v` (all of them, old and new);
> - `python -m compileall -q src tests`;
> - `PYTHONPATH=src python -m ban.cli cashout-demo --fixture fixtures/cashout_demo.json`, which
>   exits 0 and prints every refused attack.
>
> **Non-goals.** Do not do any of the following:
> - network calls (relays, NIP-05 or Jawwal), NIP-44/59 encryption, real keys or funds;
> - changes to UTXO-Ref, Raito-Scrypt, zk-rusto-no-bitcoino, tl-collator or TradeLayer-Rust;
> - any prover, any change to the `PaymentClaimV1` ABI, any new dependency.
>
> **Deliver.** Commit to the branch and push. Open a **draft** PR against `main` titled "Cashout
> slice v0: alias, intent, BUY-side quote, simulated ledger". Report in at most 300 words:
> - the commit SHA;
> - the test counts;
> - whether the local patch was found (path and hash) or not;
> - every spec deviation, with its reason;
> - any test that could not be written, and why.

---

### Appendix: how the inventory was refreshed

- **Clones.** Blobless clones (`git clone --filter=blob:none --no-checkout`) of all 11
  repositories into the session scratchpad. Files were read with `git show <sha>:<path>` at the
  SHAs above. PR heads came from `git ls-remote origin 'refs/pull/*/head'`, and PR state, draft
  status and merge dates from the unauthenticated GitHub REST API (public repositories only).
- **Standards.** Shallow clones of `nostr-protocol/nips` @`400d157` and `cashubtc/nuts` @`1363de4`.
- **Nothing was run.** No proof, test suite, node or service was run. Every performance and
  result figure above is quoted from the cited repository files.
