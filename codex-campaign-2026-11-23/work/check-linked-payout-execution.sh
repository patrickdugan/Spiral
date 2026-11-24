#!/usr/bin/env bash
set -euo pipefail
umask 077
previous=/mnt/c/Users/patri/Documents/Codex/2026-11-15/new-chat/outputs/ark-cashu-proofdesk/.runtime/regtest-stack-ki14y5s6
bundle=$(tr -d '\r\n' </mnt/c/Users/patri/Documents/Codex/2026-11-23/the-goal-is-paused-at-the/work/paired-local-bundle.txt)/benchmarks/shinigami
out=$(mktemp -d /var/tmp/cashu-linked-execution.XXXXXXXX)
mkdir -p "$out/project/target/dev" "$out/cache"
export PATH="$bundle/bin:/usr/bin:/bin" SCARB_CACHE="$out/cache" SCARB_TARGET_DIR="$out/project/target"
cp "$bundle/redemption/Runtime.toml" "$out/project/Scarb.toml"
cp "$bundle/redemption/main.executable.json" "$out/project/target/dev/main.executable.json"
python3 -B "$bundle/redemption/case.py" "$previous/funded-refusal-state.json" "$previous/funded-refusal-report.json" "$out/case"
python3 -B "$bundle/redemption/check.py" "$out/case" --project "$out/project" --scarb "$bundle/bin/scarb"
