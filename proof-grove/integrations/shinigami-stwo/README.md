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
cargo +nightly-2025-07-14 test --locked -j1 -p stwo --lib \
    --features disk-merkle,parallel disk_blake2s -- --nocapture
```

The disk path uses the same full-width Blake2s leaf bytes as stock. The packed
field representation can contain `0x7fffffff` for zero. Stock leaf hashing
preserves that raw word in both its SIMD and small-column paths. The parity
test compares each stored node, the root and openings against the same pinned
stock implementation. The Python reference checks the mixed-height projection
and file offsets independently for 63 layouts, including Blake2s block
boundaries and raw zero aliases. That check matched 8,085 digests. Both Rust
parity tests passed with and without the `parallel` feature under a 1 GiB
no-swap worker cap. The runs peaked at 522,372 KiB and 583,920 KiB build RSS,
respectively. The patched source staged successfully from both pinned commits,
and the exact Cairo toolchain and locked dependencies were staged in WSL.

The overlay selects plain Blake2s when the Linux binary is built with
`stwo/disk-merkle` and `STWO_MERKLE_DISK_DIR` is set to a private directory on
disk. At lifting depth 26, each nonempty tree can spill about four GiB of
hashes to disk. File cache, traces, polynomials, and FRI still contribute to
process pressure. Plan for those separately and measure actual whole-prover
memory.

After the parity gate, install and build the JSON-only prover. The CLI uses
the pinned Cairo proof generator and reads a saved `ProverInput`. Its
dependencies are the proof generator's runtime crates. Staging records the
CLI source and updated manifest hashes alongside the lockfile hash.

```sh
python3 integrations/shinigami-stwo/stage.py --install-cli "$STAGED"
cd "$STAGED/cairo/stwo_cairo_prover"
cargo +nightly-2025-06-23 build --locked --release -j1 \
    -p stwo-cairo-prover --bin prove-json --features disk-prove-cli,stwo/disk-merkle
```

For a low-cost interoperability control, use
`test_data/test_prove_verify_all_builtins/prover_input.json` from the staged
Cairo tree and this integration's `smoke-profile.json`. Have the separately
installed Scarb verifier check its JSON output using `--proof-file`. The
small profile is intended for smoke testing.

Use the pinned Shinigami kit's exact `profile.json` and the exact archived
case's `prover_input.json` produced by `audit-exact-melt-stark.py --execute-only`.
Pass the input, profile and fresh output path to `prove-json` in that order.
Submit the raw candidate JSON to the existing exact audit as
`--existing-proof`. The audit pins the stock verifier and program and tests
mutations of all 24 Cairo public output cells. The exact historical chain
check also requires the original regtest blocks and an independent checkpoint.

## CUDA compatibility adapter

The published CUDA proof of concept at Cairo
`4c54e2e52fc447b7c97ca3d5ffecb759230a676f` uses Stwo fork
`483f8c94c02bc7c4eaf128f2cd2269dd6f1a5f6c` and VortexSTARK
`1e88c31974bcb9906274d7a129bd9f2902d7ae2e`. The saved-input adapter calls that
candidate's CUDA prover and uses Cairo's same `ProofFormat::Json` serializer
as the CPU CLI. It requires the explicit historical profile. The candidate's
optional component split may be omitted or null, which selects its default.
The adapter rejects a split override or any changed proof parameter. The
historical profile uses plain Blake2s, salt zero, `canonical_without_pedersen`,
lifting log 26, 26 PoW bits, and 70 FRI queries with blowup log one and fold
step one. It disables polynomial coefficient retention and all-column
preprocessed sampling. [CUDA prover API](https://github.com/garrick247/stwo-cairo/blob/4c54e2e52fc447b7c97ca3d5ffecb759230a676f/stwo_cairo_prover/crates/prover/src/cuda_prover.rs)

Stage this source in a fresh directory, separately from the pinned CPU tree.
`CUDA_CAIRO_GIT` is a local clone containing the exact candidate commit.
`PROOF_GROVE` is the absolute path to this repository's `proof-grove/`.

```sh
INTEGRATION="$PROOF_GROVE/integrations/shinigami-stwo"
python3 -B "$INTEGRATION/stage-cuda.py" --cuda-cairo-git "$CUDA_CAIRO_GIT" --out "$CUDA_STAGED"
cd "$CUDA_STAGED/stwo_cairo_prover"
cargo +nightly-2025-06-23 build --locked --release -j1 \
    -p stwo-cairo-prover --bin prove-json-cuda --features cuda-prove-json
```

For the RTX 5090, use a CUDA 13 toolchain and matching NVIDIA driver so the
pinned build script emits native `sm_120`. Record the GPU compute capability
and toolkit version. The script also emits `sm_89` and `compute_89` for Ada.
An RTX A6000 or RTX 3050 needs separate Ampere targeting and compatibility
checks. CUDA still uses a CPU/SIMD trace generator, and device and host memory
for the complete historical proof remain unmeasured. [Pinned VortexSTARK build targets](https://github.com/garrick247/VortexSTARK/blob/1e88c31974bcb9906274d7a129bd9f2902d7ae2e/build.rs)

Start with the pinned CPU tree's `test_data/test_prove_verify_all_builtins/prover_input.json`
and set `SMOKE_PROOF` to a new path. `SHINIGAMI` points to the archived kit's
`benchmarks/shinigami/` directory. The `--smoke` switch is required for the
smaller CanonicalSmall test parameters.

```sh
BIN="$CUDA_STAGED/stwo_cairo_prover/target/release/prove-json-cuda"
printf '%s  %s\n' '07287a92f6b59878c0296e0a4fd956d6cfd160d2daaac8d2f2dbaa81cee1ef29' \
    "$SMOKE_INPUT" | sha256sum -c
nvidia-smi --query-gpu=name,compute_cap,memory.total,driver_version --format=csv
nvcc --version
/usr/bin/time -v -o "$SMOKE_PROOF.time" "$BIN" --smoke "$SMOKE_INPUT" \
    "$INTEGRATION/smoke-profile.json" "$SMOKE_PROOF"
"$SHINIGAMI/bin/scarb-verify" --proof-file "$SMOKE_PROOF"
```

Once the separate stock verifier accepts that proof, use the retained
historical raw input and verified kit profile with the same adapter. Record
the binary and source pins, timings, and memory. The historical audit checks
the proof profile and program hash, all 24 exact public words, and one
mutation per public word.

```sh
printf '%s  %s\n' \
    '267f580c26f5e8d49cd9aea39656ef225b2436823d4553b6722d8ad9f20b1366' "$EXACT_INPUT" \
    '62670efbaaf0ba945a291e18153ca0d27a49d6c8882899cc2d7b4d4b51953ecd' "$SHINIGAMI/profile.json" \
    | sha256sum -c
sha256sum "$BIN"
/usr/bin/time -v -o "$EXACT_PROOF.time" "$BIN" "$EXACT_INPUT" "$SHINIGAMI/profile.json" "$EXACT_PROOF"
python3.11 "$PROOF_GROVE/scripts/audit-exact-melt-stark.py" --runner "$SHINIGAMI/run.py" \
    --case "$EXACT_CASE" --existing-proof "$EXACT_PROOF" --out "$EXACT_AUDIT"
```

The adapter is staged source. CUDA smoke and exact proof compatibility are
still to be measured. The VortexSTARK pin is licensed under Business Source
License 1.1. The pinned terms permit non-production evaluation, testing and
development, with a stated change date of March 20, 2029 to Apache 2.0.
Production use requires a grant that covers it. Retain the license and its
notices with any redistribution under the pinned terms. [Pinned VortexSTARK license](https://github.com/garrick247/VortexSTARK/blob/1e88c31974bcb9906274d7a129bd9f2902d7ae2e/LICENSE)
