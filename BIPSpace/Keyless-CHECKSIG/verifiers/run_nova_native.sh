#!/usr/bin/env bash
# Opt-in native verification of a real compressed Nova Spartan+IPA proof.
# Runs the pinned native Nova 0.76 verifier. This is not Bitcoin Script.
set -euo pipefail
REPO=https://github.com/patrickdugan/zk-rusto-no-bitcoino.git
REV=7893ff279dd01e581f14e3e2cbaf99c823173bae
ROOT="$(cd "$(dirname "$0")" && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

git clone -q "$REPO" "$TMP/source"
git -C "$TMP/source" checkout -q --detach "$REV"
test "$(git -C "$TMP/source" rev-parse HEAD)" = "$REV"
NATIVE="$TMP/source/integrations/bitvm3-nova/m12/native"
mkdir -p "$NATIVE/src/bin"
cp "$ROOT/nova_native_verifier.rs" "$NATIVE/src/bin/keyless_nova_verify.rs"

if [[ "$#" == 1 && "$1" == "--fixture-k1" ]]; then
  set -- "$TMP/source/integrations/bitvm3-nova/m12/fixtures/testnet4-k1-0-4.nht4" \
         "--rebuild-testnet4-k1" \
         "d3b478b0ed0055bbd43a59775729c990a33d1df07bd0a66ee728a3573c832fa0"
fi
if [[ "$#" != 3 ]]; then
  echo >&2 "Usage: bash run_nova_native.sh --fixture-k1"
  echo >&2 "   or: bash run_nova_native.sh BUNDLE VK_BIN EXPECTED_STATEMENT_SHA256"
  exit 2
fi
cargo run --release --manifest-path "$NATIVE/Cargo.toml" \
  --bin keyless_nova_verify -- "$1" "$2" "$3"
