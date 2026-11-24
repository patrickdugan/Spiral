#!/usr/bin/env bash
set -euo pipefail
umask 077
export CUDA_VISIBLE_DEVICES=''
export RAYON_NUM_THREADS=1

shz=/var/tmp/shz-mnr04-target/release/shz
core=/root/opt/bitcoin-31.1/bin/bitcoind
printf '%s  %s\n' 986e63b3c8770f08d0059820ad3dd085d1ab9e1bea23946c243f858a06888a08 "$core" | sha256sum -c --quiet -
old=/var/tmp/shz-mnr04-routes.DRDHJbsC/replay
key=e92e08dafafd66304914f136910fba8942ad8b16faadf9973c85c064962e606d
printf '%s  %s\n' "$key" "$old/proof/vk.bin" | sha256sum -c --quiet -
run=$(mktemp -d /var/tmp/shz-mnr04-signed.XXXXXXXX)
printf 'Signed proof directory %s\n' "$run"

"$shz" mnr04-route-verify "$old/core-archive.json" "$old/proof" "$key" > "$run/unsigned-compatibility.json"
bash <(tr -d '\r' < scripts/bench-mnr04.sh) "$shz" "$core" "$run/replay" signed-route

python3 - "$run" "$shz" "$key" <<'PY'
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1])
shz, key = sys.argv[2:]
replay = root / "replay"
archive = replay / "core-archive.json"
original = json.loads(archive.read_bytes())
summary = json.loads((replay / "benchmark.json").read_bytes())
unsigned = json.loads((root / "unsigned-compatibility.json").read_bytes())
verified = summary["independent_verification"]
proof = (replay / "proof" / "proof.bin").read_bytes()
assert summary["core"]["consensus_accepted"]
assert verified["vk_sha256"] == unsigned["vk_sha256"] == key
assert "signed_origination" not in unsigned["routed_netting"]
assert verified["proof_bytes"] == len(proof)
assert verified["proof_sha256"] == hashlib.sha256(proof).hexdigest()

records = {}
for control in ("wrong_signature", "wrong_terms_digest", "stripped_origination"):
    changed = deepcopy(original)
    if control == "wrong_signature":
        signatures = changed["signed_mnr04_origination"]["signatures"]
        value = signatures[1]
        signatures[1] = ("0" if value[0] != "0" else "1") + value[1:]
    elif control == "wrong_terms_digest":
        value = changed["signed_mnr04_origination"]["terms_sha256"]
        changed["signed_mnr04_origination"]["terms_sha256"] = ("0" if value[0] != "0" else "1") + value[1:]
    else:
        del changed["signed_mnr04_origination"]
    path = root / (control + ".json")
    path.write_text(json.dumps(changed) + "\n")
    records[control] = path

checks = [
    ("wrong_signature", True, "invalid signed origination participant signature"),
    ("wrong_terms_digest", True, "signed origination terms or funding changed"),
    ("stripped_origination", True, "signed MNR-04 origination required"),
    ("stripped_origination", False, None),
]
negative = []
for control, require, expected in checks:
    args = [shz, "mnr04-route-verify", str(records[control]), str(replay / "proof"), key]
    if require:
        args.append("--require-signed")
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    if result.returncode != 1 or (expected and expected not in result.stderr) or "panicked" in result.stderr:
        raise RuntimeError(f"{control}, strict={require}: unexpected refusal {result.returncode}: {result.stderr}")
    negative.append({"case": control, "strict_mode": require, "exit_code": result.returncode,
                     "reason": result.stderr.strip()})

summary["origination_negative_controls"] = negative
summary["unsigned_routed_compatibility"] = {
    "proof_sha256": unsigned["proof_sha256"], "vk_sha256": unsigned["vk_sha256"],
    "txid": unsigned["native"]["txid"],
}
summary["core_archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
summary["core_binary_sha256"] = "986e63b3c8770f08d0059820ad3dd085d1ab9e1bea23946c243f858a06888a08"
(root / "qualified-benchmark.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps({"run": str(root), "txid": verified["native"]["txid"],
                  "proof_sha256": verified["proof_sha256"], "proof_bytes": len(proof),
                  "native_signatures_verified": verified["routed_netting"]["signed_origination"]["native_signatures_verified"],
                  "controls": len(negative), "timings": summary["phases"]}))
PY
