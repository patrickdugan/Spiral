#!/usr/bin/env bash
set -euo pipefail
repo=/mnt/c/Users/patri/Documents/Codex/2026-11-15/new-chat/outputs/zk-rusto-no-bitcoino-ark/integrations/bitvm3-nova
work=/mnt/c/Users/patri/Documents/Codex/2026-11-23/the-goal-is-paused-at-the/work/nb3-library
sandbox=$(mktemp -d /var/tmp/nb3-library-check.XXXXXXXX)
printf '%s\n' "$sandbox" | tee "$work/check-root.txt"
mkdir -p "$sandbox/prover" "$sandbox/prover-gpu"
rsync -a --exclude=target "$repo/prover/" "$sandbox/prover/"
rsync -a --exclude=target "$repo/prover-gpu/" "$sandbox/prover-gpu/"
cp /root/nb3/prover-gpu/Cargo.toml /root/nb3/prover-gpu/Cargo.lock "$sandbox/prover-gpu/"
cp -a --reflink=auto /root/nb3-gpu-target "$sandbox/target"
export PATH=/root/.cargo/bin:/usr/local/cuda/bin:/usr/bin:/bin
export CARGO_TARGET_DIR="$sandbox/target"
export CUDA_PATH=/usr/local/cuda CUDA_ARCHS=120
export LD_LIBRARY_PATH=/usr/local/cuda/lib64:/usr/lib/wsl/lib
cd "$sandbox/prover-gpu"
cargo +1.99.1 test --offline --locked --release -j1 --lib --bin nb3-prove-gpu
cargo +1.99.1 test --offline --locked --release -j1 -p nb3-prover --lib
