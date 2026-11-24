#!/usr/bin/env bash
set -euo pipefail
umask 077
out=$(realpath "${1:?pass the verified Ark proof directory}")
base=/var/tmp/ark-asp-full-20261117
public_root="$base/m14-public-file-backed-20261123"
private_root=/var/tmp/ark-m14-private-file-backed-20261123
campaign=/mnt/c/Users/patri/Documents/Codex/2026-11-15/new-chat
ark="$campaign/outputs/zk-rusto-no-bitcoino-ark/Ark"
selection="$campaign/work/ark-m14-file-backed-setup-20261123/toolchain-selection.json"
setup_receipt="$ark/results/m14-bounded-setup-20261123.json"

test -f "$out/independent-sdk-m13-passed"
test -d "$private_root" && test -f "$public_root/run-state.json"
exec 9>"$base/.overnight-m14-evaluation.lock"
flock -n 9
for path in "$public_root" "$private_root" /mnt/d; do
    available=$(df --output=avail -B1 "$path" | tail -1)
    (( available >= 8 * 1024**3 ))
done

python3 - "$out" "$public_root" "$selection" "$setup_receipt" "$ark" <<'PY'
import hashlib, json, pathlib, subprocess, sys

out, public_root, selection_file, receipt_file, ark = map(pathlib.Path, sys.argv[1:])

def data(path):
    return json.loads(path.read_bytes())

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

expected = data(out / 'expected-statement.json')
state = data(public_root / 'run-state.json')
selection = data(selection_file)
receipt = data(receipt_file)
verified = data(out / 'm13-verification.json')
policy = data(out / 'policy-verification.json')
proof = out / 'm13' / 'wrap-v2.bin'
proof_hash = digest(proof)
pins_path = pathlib.Path(selection['build_pins']).resolve(strict=True)
if not pins_path.is_relative_to(ark.resolve() / 'results') or digest(pins_path) != receipt['build_report_sha256']:
    raise ValueError('M14 build report differs from the verified setup pin')
if not (selection['schema'] == 'ark-m14-toolchain-selection-v1'
        and selection['statement'] == state['statement'] == verified['statement'] == policy['statement'] == expected
        and state.get('proof_sha256', proof_hash) == proof_hash
        and state['manifest_sha256'] == receipt['manifest_sha256']
        and verified['status'] == policy['status'] == 'verified'
        and policy['ark_policy_final_proof_verified'] is True):
    raise ValueError('verified M13 proof or preserved M14 setup has a different binding')

report = out / 'm14-claim-v1.json'
subprocess.run([sys.executable, str(ark / 'scripts' / 'run_m14_claim.py'),
                '--native-cli', selection['native_cli'], '--negative-cli', selection['negative_cli'],
                '--build-pins', str(pins_path), '--statement', str(out / 'expected-statement.json'),
                '--proof', str(proof), '--public-root', str(public_root),
                '--private-root', '/var/tmp/ark-m14-private-file-backed-20261123', '--out', str(report)], check=True)
result = data(report)
if not (result['status'] == 'verified_offchain_claim' and result['statement'] == expected
        and result['proof_sha256'] == proof_hash and result['bindings_match'] is True
        and result['full_circuit_negative']['verdict'] == 'reject'):
    raise ValueError('M14 evaluation did not verify the exact statement and full negative control')
(out / 'independent-m14-passed').touch()
PY
