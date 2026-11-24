# Exact Shinigami Stwo disk storage experiment

The optional overlay targets Stwo `aeceb74c58184d7886ebd7f34a7453fee714ca40` and
Cairo `467d5c6d4d6d526c1db8ff69c14f2de6d57f4d73`. The archived Shinigami
verifier and exact redemption audit remain the proof acceptance gates.

On Linux, stage a fresh workspace from Git repositories containing the pinned
commits. The script records both source pins, the patch digest and the rewritten
Cairo lockfile digest. Only the four Stwo Git dependencies switch to local
paths. The rest of the dependency lock stays pinned.

```sh
python3 integrations/shinigami-stwo/stage.py --stwo-git "$STWO_GIT" \
    --cairo-git "$CAIRO_GIT" --out "$STAGED"
python3 integrations/shinigami-stwo/check-layout.py

cd "$STAGED/stwo"
cargo +nightly-2025-07-14 test --locked -j1 -p stwo --lib \
    --features disk-merkle disk_blake2s -- --nocapture
```

The disk path uses the same full-width Blake2s leaf bytes as stock. The packed
field representation can contain `0x7fffffff` for zero. Stock leaf hashing
preserves that raw word in both its SIMD and small-column paths. The parity
test compares each stored node, the root and openings against the same pinned
stock implementation. The Python reference checks the mixed-height projection
and file offsets independently for 63 layouts, including Blake2s block
boundaries and raw zero aliases. That check matched 8,085 digests. The patched
source staged successfully from both pinned commits. The shared Windows memory
guard stopped compilation before the Rust parity tests ran.

The overlay selects plain Blake2s when the Linux binary is built with
`stwo/disk-merkle` and `STWO_MERKLE_DISK_DIR` is set to a private directory on
disk. At lifting depth 26, each nonempty tree can spill about four GiB of
hashes to disk. File cache, traces, polynomials, and FRI still contribute to
process pressure. Plan for those separately and measure actual whole-prover
memory.

After the parity gate, build the pinned Cairo development prover:

```sh
cd "$STAGED/cairo/stwo_cairo_prover"
cargo +nightly-2025-06-23 build --locked --release -j1 \
    -p stwo-cairo-dev-utils --bin prove --features stwo/disk-merkle
```

Use the pinned Shinigami kit's exact `profile.json` and the exact archived
case's `prover_input.json` produced by `audit-exact-melt-stark.py --execute-only`.
Use the new prover binary with `--prover_input_path`, `--params_json` and
`--proof_path`. Submit the raw candidate JSON to the existing exact audit as
`--existing-proof`. The audit pins the stock verifier and program and tests
mutations of all 24 Cairo public output cells. The exact historical chain
check also requires the original regtest blocks and an independent checkpoint.
