#!/usr/bin/env bash
set -euo pipefail
umask 077
cd -- "$1"
sha256sum -c --quiet sources.sha256
test "$(cat pins/sp1-revision)" = "b8387fa61e1361d90ee7de49f551863418ca0f08"
export PATH=/root/.cargo/bin:/usr/local/cuda/bin:/usr/bin:/bin
export CUDA_PATH=/usr/local/cuda CUDA_ARCHS=80 RUSTUP_AUTO_INSTALL=0
export CUDACXX=/usr/local/cuda/bin/nvcc CMAKE_BUILD_PARALLEL_LEVEL=1
export CARGO_TARGET_DIR="$PWD/ampere-target" CARGO_BUILD_JOBS=1
nvcc --version | grep -F 'V12.8.93'
nvcc --list-gpu-arch | grep -Fx 'compute_80'
rustc +1.99.1 --version
manifest=prover-gpu-cached-gkr-20261122/Cargo.toml
bin=ark-prove-gpu-cached-gkr
cargo +1.99.1 build --release --locked --offline --manifest-path "$manifest" --bin "$bin" \
    --config profile.release.package.nb3-prover-gpu.codegen-units=256
cuobjdump --list-elf "$CARGO_TARGET_DIR/release/$bin" > ampere-fatbins.txt
grep -m1 -E '\bsm_80([a.]|$)' ampere-fatbins.txt
sha256sum "ampere-target/release/$bin" > ampere-binary.sha256
ldd "$PWD/ampere-target/release/$bin"
cat ampere-binary.sha256
