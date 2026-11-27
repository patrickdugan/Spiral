# Proof-backed Cashu withdrawal released by BitVM3 (regtest)

Produced 2026-11-28 ~06:38 Taipei. A Cashu holder's exact 24,750-sat withdrawal was proven in SP1, compressed,
wrapped, accepted by the M14 BitVM3 verdict circuit, and then **paid out on Bitcoin regtest by a joint spend that the
proof authorized** — no trusted mint signature on the release path. Every file here is byte-exact (`.gitattributes`).

## The chain of evidence

| Step | Result | Key pins |
|---|---|---|
| SP1 Core proof | 37,309 shard STARKs, `core_proof_verified` by an independent verifier | program key `0x0030ae332ef69e5eb62c7e270b6a3414d88237746023671a8db80fd9c9cf33d3`, public values `8c7cb7de…6d2b`, shard index `d22fc4a7…` |
| Recursion (compress) | 292 groups × 128 shards folded to one proof; every group root verified on its GPU and again locally | archive `bd35977f…`, root `d106b0e4…` |
| Independent SP1 check of the compressed proof | `compressed_proof_verified` (`sp1-sdk-light`), 37,309 shards | `recipient-sp1-verification.json` |
| M13 shrink + wrap | `pinned_wrap_v2_verified`; native M13 verifier `verified` | wrap `94a403fa…`, statement `8fd9bc7f…` |
| M14 verdict | **accept** over 971,724,042 non-free gates; a one-byte-mutated input is rejected (`unbound`) | input blake3 `e48ae8c4…` |
| Garbled evaluation | 971,724,042 ciphertexts authenticated; independent seedless evaluation matches the pinned package | setup `dd041853…` |
| Bitcoin release (regtest) | joint payout **24,750 sats** to the holder, confirmed at height 212 | txid `32e9951df57f6cf0687b4682427bcafa5b7f5cc11f4f71f618082cc71884f564` |
| Recipient verification | fresh walletless Core replay (0 wallets, 103 blocks) + M13 + M14 + SP1 re-checks | `cashu-v4-raw-recipient-verification-4.json` |

Negative controls on the same funded inputs (all rejected by Bitcoin script validation): substituted accept label,
holder signature, issuance preimage, challenger approval, holder approval, and beneficiary. The holder-only CSV
fallback is valid before release and `missing-inputs` after it; reorging the payout restores both inputs; the
competing timeout fork is settled consistently.

## Files

- `cashu-v4-raw-proof-backed-withdrawal-evidence-4.zip` — sha256 `5446141e6c12c5ce4681f9c07a82ad7f1607a7accaadc51726492350db556a9b`
- `cashu-v4-raw-recipient-verification-4.json` — independent funded verification receipt
- `recipient-sp1-verification.json`, `recipient-sp1-transcript.log` — independent SP1 compressed-proof check
- `funded-payout/proof-backed-payout.json`, `funded-payout/proof-backed-blocks.hex` — payout receipt and regtest blocks
- `funded-evidence.json`, `evaluate-staged-checked.json`, `m13-wrap-result.json`, `m13-handoff.json`,
  `independent-core-verified.json`, `pipeline-stages/*.jsonl`

## Scope and limits

Regtest only, with the v2 collateral approval, a trusted single-use garbler and separately pinned chain observations.
This is not a malicious-setup-resistant or mainnet-ready release. A separate holder-only CSV exit (no proof, same
reserve script, fresh keys) was broadcast on testnet4: txid `380aff2486d2b5654473fd33e1b971089604204e8e0c05995e4dd9bb2c0fc8d2`.

## Fixes made overnight to reach this (not all in this repo)

- `proof-grove/scripts/cashu-sp1/m13-spill-volume.sh` (included here): chown the fresh ext4 spill root to the
  unprivileged wrap worker.
- Proving-PC orchestration (outside this repo): host-heartbeat staleness 15 → 90 s for HDD writeback during the wrap;
  PowerShell array splat fix in the evidence step; missing `confirmed` import in
  `zk-rusto-no-bitcoino/.../joint_withdrawal_regtest.py`.
