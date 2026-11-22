# Cairo / Shinigami for Ark, Nova Integration & Proof Grove Audit

## 1. Cross-Repository Lineage & Authorship Review (Claude & Codex)

| Component / Repo | Branch / Rev | Attribution | Role & Verified State |
| :--- | :--- | :--- | :--- |
| `patrickdugan/shinigami` (fork of `starkware-bitcoin/shinigami`) | `taproot-provable` @ `19cb9fa` + `feat/ark-multi-input-hardening` | Claude (Taproot + Core audit) | Syscall-free Cairo Bitcoin Script + BIP-340/341/342 VM (`4,977 / 4,977` Bitcoin Core checks passing); hardened for multi-input Ark forfeits, CSV exits, safe `i64` amounts, and canonical decoding. |
| `patrickdugan/vtxo-exit-proof` | `main` @ `d230376` | Claude | Stwo Blake2s Circle STARK prover over `shinigami` (`board` 797k steps / 158s, `round1` 3.44M / 208s, `arkoor3` 5.03M / 269s; `0.25s` verify; `15.2 MB` proof) + `confirmed_exit.py` composition with M16 `PAY1`. |
| `patrickdugan/vtxo-claim-export` | `main` @ `1e0f014` | Codex (`f00ea73`) + Claude audit (`1e0f014`) | Superseded Stage-0 25-felt ABI prototype (audit confirmed linear `felt252` `mix()` was non-cryptographic; replaced by `vtxo-exit-proof`). |
| `stwo-cairo` (`small-preprocessed`) | `e088e47` | Claude | `CanonicalWithoutPedersenUpTo(k)` cuts small-trace prover RSS from `~8 GB` to `2.6 GB`. |
| `stark-bitvm3` (`feat/stwo-bitvm3-s0`) | `fcddd4d` | Codex (`S0`–`S3n`) + Claude (`S3o`–`S6`) | Direct Stwo -> garbled verifier (`1.72B` ANDs in function form, `263.8 KB` `L21` proof), identifying the **`2,375,891`-bit (~38 MB) BitVM3 L1 input-label wall** for raw STARK proofs vs `2,568` bits (~41 KB) for Groth16 (`M14`). |
| `zk-rusto-no-bitcoino` (`ARK1`) | `ark/asp-management` @ `4ca2d1c` | Codex | Nova 0.76 ASP maintenance-policy prover (`19,113` R1CS/step, arity 24, `11,640 B` proof) + SP1 6.9 guest (`ark-prove-gpu` host-RAM bounded CUDA runner). |
| `zk-rusto-no-bitcoino` (`ark-transition-nova`) + `bitcoin-rs` (`ark-nested-musig2`) | `81140f9` + `37d6a57` | Claude | Nova 0.76 Ark round conservation + fee bound + global single-use `spend_id` grand product (`1,050` R1CS/step, arity 17, `11,104 B` proof, `22/22` mutations rejected) + Arkade-exact NestedMuSig2 harness on Core 31.1 & `bitcoin-rs`. |
| `zk-rusto-no-bitcoino` (`M16` / `M17` / `M18` / `babe-pilot`) | `a183eef` / `6f2ee19` | Claude | Mainnet PoW+SPV (`M16`), Nova legacy/v0 Script VM (`M17`, `2,756/2,756` Core vectors), Windowed UTXO IMT (`M18`), and transparent BABE-Nova Cut-and-Choose (`88.4 kvB` L1 Assert tx). |

## 2. Hardening Added to `shinigami` (`feat/ark-multi-input-hardening`)

Line-by-line review of `taproot-provable` (`19cb9fa`) identified three engine hazards affecting multi-input Ark transactions (2-input connector-bound forfeits and N-input round commitments):

1. **Multi-input `utxos` length guard (`packages/engine/src/engine.cairo`)**: `EngineImpl::new` now rejects mismatched `tx.utxos.len() != tx.inputs.len()` (`Error::TAPROOT_INVALID_SIGHASH_MIDSTATE`) so multi-input callers cannot silently hash a truncated `sha_amounts` / `sha_scriptpubkeys` slice.
2. **Safe two's-complement `i64` amount encoding (`packages/engine/src/hash_cache.cairo`)**: `calc_hash_inputs_amount` converts `i64` safely via `i128` shift instead of panicking on negative `felt252 -> u128`.
3. **Consensus-canonical transaction decoder (`packages/engine/src/transaction.cairo`)**: Added `EngineInternalTransactionTrait::deserialize_canonical` rejecting trailing garbage bytes after `locktime` and BIP-141 superfluous witness flags (`0x0001` with all-empty witnesses).
4. **Ark Regression Vectors (`packages/tests/src/tests/test_p2tr_ark.cairo`)**: Verified byte-exact against `arkade-os/rust-sdk` (`ark-core` `g-2g-12.json`) — 2-input connector-bound forfeit tx (both Tapscript forfeit + Taproot key-path connector inputs), mutated connector amount negative control, truncated `utxos` negative control, unilateral `<12> CSV` owner exit (`nSequence=12` pass, `nSequence=11` `UNSATISFIED_LOCKTIME`), and trailing-byte rejection (`25 / 25` Ark Cairo tests passing).

## 3. Proof Grove Cashu-to-Ark Hackathon App Integration (`proofdesk/ark_zk.py`)

Proof Grove (`proofdesk/ark_zk.py`, `server.py`, `web/index.html`, `web/app.js`) now exposes process-isolated, binary-SHA-256-pinned verification gates alongside its Cashu NUT-09/12/20/30 + Bark Arkoor + offline exit recovery desk:

- **`GET /api/ark/proofs`**: Returns pinned digests, measured benchmarks, and explicit coverage/privacy boundaries for both gates.
- **`POST /api/ark/vtxo-proof/check` (`VtxoExitStarkGate`)**: Verifies Cairo/Shinigami Stwo exit-chain proofs against `PROGRAM_HASH = 0x4f57fcf7291f51140672bbefbaf92a509df7caecef6effab0e99bf24bf9c8b4`, cross-checks anchor unspentness via `CoreClient.gettxout`, and enforces `zero_knowledge: false` / `archive_privacy: "redacted-hash-only"` so raw non-ZK Stwo traces never leak into public CIDv1 archives.
- **`POST /api/ark/round/check` (`ArkTransitionNovaGate`)**: Verifies `ark-transition-nova-public-v1` + 11,104-byte Spartan-IPA proofs against `vk_digest = 22ad3282b71196a227d95b2216921a78e8d362d96702a3377347c0d085dfcdad`, keeping Nova conservation/fee-bound/uniqueness coverage explicitly separated from Taproot script validity and Core chainstate observation.
