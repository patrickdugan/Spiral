#!/usr/bin/env bash
set -euo pipefail
umask 077
export CUDA_VISIBLE_DEVICES=''
export RAYON_NUM_THREADS=1

shz=/var/tmp/shz-mnr04-target/release/shz
core=/root/opt/bitcoin-31.1/bin/bitcoind
printf '%s  %s\n' 986e63b3c8770f08d0059820ad3dd085d1ab9e1bea23946c243f858a06888a08 "$core" | sha256sum -c --quiet -
legacy_key=/var/tmp/shz-mnr04-netting.1tJnr4KP/replay/proof/vk.bin
legacy_pin=7fc71a8518976ede1ad97855ee164e63356e4ef11cda43565e1177fa5f082db1
printf '%s  %s\n' "$legacy_pin" "$legacy_key" | sha256sum -c --quiet -

run=$(mktemp -d /var/tmp/shz-mnr04-routes.XXXXXXXX)
printf 'Route proof directory %s\n' "$run"
mkdir "$run/legacy-a100"
cp -- evidence/mnr04/a100-proof.bin "$run/legacy-a100/proof.bin"
cp -- "$legacy_key" "$run/legacy-a100/vk.bin"
"$shz" mnr04-verify evidence/mnr04/a100-core-archive.json "$run/legacy-a100" "$legacy_pin" >"$run/legacy-a100.json"
printf 'Verified the existing A100 proof with the existing key pin.\n'

bash <(tr -d '\r' < scripts/bench-mnr04.sh) "$shz" "$core" "$run/replay" route
if "$shz" mnr04-route-verify "$run/replay/core-archive.json" "$run/replay/proof" "$legacy_pin" \
    >"$run/wrong-key.stdout" 2>"$run/wrong-key.stderr"; then
    printf 'Routed proof accepted the legacy verifier-key digest.\n' >&2
    exit 1
fi
grep -q 'Nova verifier key differs from independently pinned digest' "$run/wrong-key.stderr"
python3 - "$run" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
replay = root / "replay"
summary = json.loads((replay / "benchmark.json").read_bytes())
legacy = json.loads((root / "legacy-a100.json").read_bytes())
new = summary["independent_verification"]
core = summary["core"]
proof = (replay / "proof" / "proof.bin").read_bytes()
assert core["consensus_accepted"] is True
assert core["native"]["txid"] == new["native"]["txid"] and core["native"]["wtxid"] == new["native"]["wtxid"]
assert new["proof_sha256"] == hashlib.sha256(proof).hexdigest()
assert new["proof_bytes"] == len(proof) and new["vk_sha256"] != legacy["vk_sha256"]
assert legacy["proof_bytes"] == 12224 and legacy["wrong_txid_claim_refused"]
summary["legacy_a100_compatibility"] = {
    "vk_sha256": legacy["vk_sha256"], "proof_sha256": legacy["proof_sha256"],
    "txid": legacy["native"]["txid"], "wrong_txid_refused": True,
}
summary["legacy_key_refused_by_route_profile"] = True
(root / "qualified-benchmark.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps({"run": str(root), "txid": new["native"]["txid"], "proof_bytes": len(proof),
                  "route_amounts_sats": new["routed_netting"]["allocation_sats"],
                  "proof_sha256": new["proof_sha256"], "vk_sha256": new["vk_sha256"],
                  "legacy_accepted": True, "legacy_key_on_route_refused": True}))
PY
