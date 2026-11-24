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

The unmodified Vortex build script emits `sm_89` and `compute_89`, and also
emits native `sm_120` when it detects a CUDA 13 or 14 toolchain.
[Pinned VortexSTARK build targets](https://github.com/garrick247/VortexSTARK/blob/1e88c31974bcb9906274d7a129bd9f2902d7ae2e/build.rs)

For a native-only build, use a fresh Linux staging directory and choose
`sm_120` for RTX 5090, `sm_86` for RTX A6000 or RTX 3050, or `sm_80` for A100.
Set `CUDA_PATH` to the CUDA toolkit root. Run `nvcc --list-gpu-code` to confirm
that the toolkit supports the target. Record the driver and device compute
capability on the proving host.
`VORTEX_GIT` is a local VortexSTARK checkout containing the exact commit above.
Keep the default NVCC path and Vortex features. The staged build script targets
the selected architecture, the Cairo manifests point both Vortex packages at the same staged tree,
and the lockfile drops only the two Vortex Git source lines. The receipt records
the original Git blob, original and patched build script hashes, and staged
manifest and lock hashes. Resolve metadata with `--locked` before starting the
build. The staged overlay resolved 506 packages under `--locked` with its
lockfile unchanged.

```sh
CUDA_ARCH=sm_86
python3 -B "$INTEGRATION/stage-cuda.py" --cuda-cairo-git "$CUDA_CAIRO_GIT" \
    --vortex-git "$VORTEX_GIT" --cuda-arch "$CUDA_ARCH" --out "$CUDA_STAGED"
export CUDA_PATH
export PATH="$CUDA_PATH/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_PATH/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
cd "$CUDA_STAGED/stwo_cairo_prover"
nvcc --version
nvcc --list-gpu-code | grep -Fx "$CUDA_ARCH"
cargo +nightly-2025-06-23 metadata --locked --format-version 1 \
    --features stwo-cairo-prover/cuda-prove-json >/dev/null
cargo +nightly-2025-06-23 build --locked --release -j1 \
    -p stwo-cairo-prover --bin prove-json-cuda --features cuda-prove-json
cuobjdump --list-elf target/release/build/vortexstark-*/out/libvortex_cuda.a
```

Check the cubin list for the selected architecture. The laptop RTX 3050 is a smoke target. Its
4 GiB VRAM cannot hold the current exact lift-26 layout, which needs nearly
4 GiB for one dense Merkle tree alone. The 48 GiB A6000 is an exact-proof
candidate after smoke and verifier success. Peak GPU and host memory for the
complete proof remain unmeasured, and trace generation still uses CPU/SIMD.

CUDA 12.8.93 resolved the locked build graph for all three native targets and
compiled the pinned `cuda/blake2s.cu` to an RTX 5090 `sm_120` cubin. NVCC took
30.37 seconds at 161,176 KiB peak RSS in a 512 MiB cgroup with zero swap. A
complete Blackwell binary and verification on an RTX 5090 remain outstanding.

The Vortex build script compiles CUDA translation units serially and archives
them after the last one succeeds. For an interrupted SM86 build, use the
local NVCC cache below. Keep the same target directory, toolkit, and build
environment for each retry. The first run populates an empty cache from
successful NVCC commands. Each hit checks the compile receipt and object
hash before restoring the exact output bytes.

```sh
REAL_CUDA_PATH="$CUDA_PATH"
python3.11 -B "$INTEGRATION/nvcc-object-cache.py" prepare \
    --source "$CUDA_STAGED/vortex" --toolkit "$REAL_CUDA_PATH" \
    --shim "$CUDA_SHIM" --cache "$CUDA_OBJECT_CACHE"
export CUDA_PATH="$CUDA_SHIM"
export PATH="$REAL_CUDA_PATH/bin:$PATH"
export LD_LIBRARY_PATH="$REAL_CUDA_PATH/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
# Run the same locked Cargo build above. Reuse the existing shim on retry.
```

Use fresh shim and cache paths on the Linux filesystem. The shim forwards
commands outside the pinned Linux SM86 compile form to the real NVCC. Its
recipe binds the exact command, Vortex CUDA files and headers, CUDA toolkit
and host compiler fingerprint, and relevant environment. Reprepare after a
host or toolkit update. Run a standalone object compile separately from
Cargo, with the same working directory, environment, source flags and
absolute output path, to make its result available to a later build.

The RTX 3050 ran the pinned lifted Blake2s leaf and parent kernels directly.
All 463 hashes matched the stock layout across 27 CUDA launches, including
mixed column heights and the raw `0x7fffffff` zero encoding. The harness checks
launch and synchronization status and compares every tree level.

```sh
VORTEX="$CUDA_STAGED/vortex"
nvcc -shared --cudart shared -Xcompiler=-fPIC -O1 -gencode arch=compute_86,code=sm_86 \
    "$VORTEX/cuda/merkle_leaves_lifted.cu" "$VORTEX/cuda/blake2s.cu" \
    -o "$SM86_KERNEL_LIBRARY"
CUDA_VISIBLE_DEVICES=0 python3.11 -B "$INTEGRATION/check-cuda-merkle.py" "$SM86_KERNEL_LIBRARY"
```

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

Use the CUDA launch trace to confirm Blake2s leaf and parent kernels ran and
check the prover log for CPU fallbacks. The backend can recover from a failed
GPU leaf launch by computing the leaf hashes on the CPU. [Pinned CUDA Merkle implementation](https://github.com/garrick247/VortexSTARK/blob/1e88c31974bcb9906274d7a129bd9f2902d7ae2e/crates/cuda-backend/src/merkle_ops.rs)

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
