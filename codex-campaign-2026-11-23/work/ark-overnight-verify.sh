#!/usr/bin/env bash
set -euo pipefail
umask 077
out=$(realpath "${1:?pass the isolated downloaded proof directory}")
base=/var/tmp/ark-asp-full-20261117
homework=/mnt/c/Users/patri/Documents/Codex/2026-11-15/new-chat
ark="$homework/outputs/zk-rusto-no-bitcoino-ark/Ark"
host=/root/nb3/m13/wrap/target/release/ark-asp-sp1-host
wrapper=/root/nb3/m13/wrap/target/release/m13
checked="$homework/work/ark-modern-verifiers-target-20261122/release"
elf="$homework/work/ark-asp-guest/ark-asp-nova-guest"
manager=/var/tmp/ark-asp-pinned-tools-20261123/ark-asp-management
public=dd352842409878b3da279ce254d39ff95e4425ef5c256fdbbf6426acffa88f41
printf '%s  %s\n' "$public" "$base/expected-public.bin" \
  28c3bb3082bd4d4d20f27647bd3c08046eb9822b295138bfccd03c8eac2ca88c "$host" \
  f3e0608f83f55db8327d371fd90753c9fb450e49682c5ae8f41ce249c784eb2f "$wrapper" \
  7ce5812fd76c3b31a5c3c24d117120b02839175636a68586e0fe97d370dcba5d "$elf" |
  sha256sum -c --quiet -
export CUDA_VISIBLE_DEVICES=
export RAYON_NUM_THREADS=1 TOKIO_WORKER_THREADS=1
exec 9>"$out/independent-verification.lock"
flock -n 9
run_json() {
    local file=$1
    shift
    "$@" > "$out/$file.log" 2>&1
    python3 - "$out/$file.log" "$out/$file.json" <<'PY'
import json, pathlib, sys
source,target=map(pathlib.Path,sys.argv[1:])
for line in reversed(source.read_text().splitlines()):
    try: data=json.loads(line)
    except ValueError: continue
    if isinstance(data,dict):
        target.write_text(json.dumps(data,indent=2)+"\n")
        break
else: raise RuntimeError("verifier did not emit a JSON result")
PY
}
run_json sdk-verification "$host" verify-sp1 "$elf" "$out/compressed.bin" "$base/expected-public.bin"
python3 - "$out" "$ark" "$public" <<'PY'
import json,pathlib,sys
out,ark=map(pathlib.Path,sys.argv[1:3]); public=sys.argv[3]
pins=json.loads((ark/"fixtures/bitvm3-pins.proof-grove.json").read_text())
sdk=json.loads((out/"sdk-verification.json").read_text())
assert sdk["status"]=="compressed_proof_verified"
assert sdk["program_vk_digest"]==pins["program_vk_digest"] and sdk["public_sha256"]==public
statement={key:pins[key] for key in ("wrap_vk_sha256","program_vk_digest","recursion_vk_root")}
statement.update(committed_values_sha256=public,exit_code=0,is_complete=1)
(out/"expected-statement.json").write_text(json.dumps(statement)+"\n")
PY
"$wrapper" shrink-wrap "$out/compressed.bin" "$out/m13" > "$out/shrink-wrap.log" 2>&1
"$wrapper" wrap-only-v2 "$out/m13" > "$out/wrap-v2.log" 2>&1
wrap="$out/m13/wrap-v2.bin"
statement="$out/expected-statement.json"
run_json m13-verification "$checked/m13-verify" verify-v2 "$wrap" "$statement"
run_json policy-verification python3 "$ark/scripts/bitvm3_gate.py" --pins "$ark/fixtures/bitvm3-pins.proof-grove.json" \
    --management-cli "$manager" --m13-verifier "$checked/m13-verify" --snapshot "$ark/fixtures/proof-grove-regtest.json" \
    --policy "$ark/fixtures/policy-proof-grove.json" --proof-dir "$ark/.runtime/proof-grove-verified" --wrap "$wrap"
python3 - "$out" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1])
expected=json.loads((root/"expected-statement.json").read_text())
for name in ("m13-verification","policy-verification"):
    got=json.loads((root/(name+".json")).read_text())
    if got["status"]!="verified" or got["statement"]!=expected: raise RuntimeError("statement mismatch")
    if name=="policy-verification" and not got["ark_policy_final_proof_verified"]:
        raise RuntimeError("Ark policy gate failed")
for source,dest in ((root/"compressed.bin","wrong-compressed.bin"),(root/"m13/wrap-v2.bin","wrong-wrap.bin")):
    data=bytearray(source.read_bytes())
    data[len(data)//2]^=1
    (root/dest).write_bytes(data)
expected["program_vk_digest"]=("0" if expected["program_vk_digest"][0]!="0" else "1")+expected["program_vk_digest"][1:]
(root/"wrong-statement.json").write_text(json.dumps(expected)+"\n")
PY
refuse() {
    local code=0
    local stage=$1
    shift
    "$@" > "$out/$stage.log" 2>&1 || code=$?
    test "$code" -eq 1
}
refuse refuse-compressed "$host" verify-sp1 "$elf" "$out/wrong-compressed.bin" "$base/expected-public.bin"
refuse refuse-wrap "$checked/m13-verify" verify-v2 "$out/wrong-wrap.bin" "$statement"
refuse refuse-statement "$checked/m13-verify" verify-v2 "$wrap" "$out/wrong-statement.json"
touch "$out/independent-sdk-m13-passed"
# The private M14 setup remains untouched until the independently verified wrap
# and refusal logs can be inspected by the campaign's single-use operator.
