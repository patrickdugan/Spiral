#!/usr/bin/env bash
set -euo pipefail
sandbox=/var/tmp/nb3-library-check.073uViNH
pinned=/root/nb3-gpu-target/release/ark-prove-gpu-cached-gkr
before=$(sha256sum "$pinned")
require_unchanged() {
    test "$before" = "$(sha256sum "$pinned")" || exit 90
}
trap require_unchanged EXIT
export PATH=/root/.cargo/bin:/usr/local/cuda/bin:/usr/bin:/bin
export CARGO_TARGET_DIR=/root/nb3-gpu-target
export CUDA_PATH=/usr/local/cuda CUDA_ARCHS=120 RUSTUP_AUTO_INSTALL=0
export LD_LIBRARY_PATH=/usr/local/cuda/lib64:/usr/lib/wsl/lib
cd "$sandbox/prover-gpu"
cargo +stable test --offline --locked --release -j1 --lib --bin nb3-prove-gpu
cargo +stable test --offline --locked --release -j1 -p nb3-prover --lib
