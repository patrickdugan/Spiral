#!/usr/bin/env bash
set -euo pipefail
umask 077
base=$1
staging=$(mktemp -d /var/tmp/ark-mnr04-kit.XXXXXX)
build=$(tr -d '\r\n' < "$base/ark-a100-build-root.txt")
archive="$base/ark-a100-prebuilt.tar.gz"
mary="$base/SatsHedgeZero-mnr04"
old=/mnt/c/Users/patri/Documents/Codex/2026-11-15/new-chat
runtime=/var/tmp/ark-asp-full-20261117
report="$old/outputs/zk-rusto-no-bitcoino-ark/Ark/results"
test ! -e "${archive%.gz}.ready"
(cd "$build" && sha256sum -c --quiet ampere-binary.sha256 && sha256sum -c --quiet inputs.sha256)
verify_lib() {
    python3 - "$1" "$2" <<'PY'
import hashlib, json, pathlib, sys
lib, report = map(pathlib.Path, sys.argv[1:])
if hashlib.sha256(lib.read_bytes()).hexdigest() != json.loads(report.read_text())["shared_object_sha256"]:
    raise SystemExit(f"CUDA preload hash differs from pin: {lib.name}")
PY
    install -m 0755 -- "$1" "$staging/"
}
verify_lib "$runtime/libark_cuda_pool.so" "$report/cuda-pool-cap.json"
verify_lib "$runtime/libark_cuda_call_trace.so" "$report/cuda-call-trace.json"
verify_lib "$old/work/ark-private-pool-no-internal-20261122/libark_private_pool.so" "$report/cuda-private-pool-cap.json"
verify_lib "$old/work/ark-host-staging-bidirectional-20261122/libark_host_staging.so" "$report/cuda-host-staging.json"
install -m 0755 "$build/ampere-target/release/ark-prove-gpu-cached-gkr" "$staging/"
install -m 0755 /var/tmp/shz-mnr04-target/release/shz "$staging/"
mkdir -p "$staging/inputs" "$staging/bitcoin/bin"
install -m 0600 "$build/inputs/guest.elf" "$build/inputs/nova-vk.raw" "$build/inputs/nova-proof.arp" "$staging/inputs/"
core_tar=/root/opt/dl-core/bitcoin-31.1-x86_64-linux-gnu.tar.gz
printf '%s  %s\n' b80d9c3e04da78fb6f0569685673418cf686fadba9042d926d13fb87ff503f9e "$core_tar" | sha256sum -c --quiet -
for bin in bitcoind bitcoin-cli; do
    tar -xOf "$core_tar" "bitcoin-31.1/bin/$bin" > "$staging/bitcoin/bin/$bin"
    test -s "$staging/bitcoin/bin/$bin"
    chmod 0755 "$staging/bitcoin/bin/$bin"
done
for name in ark-a100-trial.sh ark-a100-heartbeat.py ark-a100-restore-release.py; do
    tr -d '\r' < "$base/$name" > "$staging/$name"
done
tr -d '\r' < "$old/outputs/zk-rusto-no-bitcoino-ark/Ark/scripts/prover_cgroup_sample.py" > "$staging/prover_cgroup_sample.py"
tr -d '\r' < "$base/ark-h100/repo/report-pilot.py" > "$staging/report-pilot.py"
install -m 0644 "$mary/scripts/bench-mnr04.sh" "$staging/"
bash -n "$staging/ark-a100-trial.sh"
bash -n "$staging/bench-mnr04.sh"
bash -n "$base/ark-a100-bootstrap.sh"
python3 - "$staging" "$build" "$mary" <<'PY'
import hashlib, json, pathlib, subprocess, sys
root, build, source = map(pathlib.Path, sys.argv[1:])
files = [
    "Cargo.lock", "crates/shz-nova-bitvm/Cargo.toml",
    "crates/shz-nova-bitvm/src/mnr04.rs",
    "crates/shz-nova-bitvm/src/mnr04/fixture.rs",
    "crates/shz-nova-bitvm/src/mnr04/nova.rs",
    "bins/shz-cli/Cargo.toml", "bins/shz-cli/src/mnr04.rs",
    "scripts/bench-mnr04.sh",
]
(root / "provenance.json").write_text(json.dumps({
    "rustc": subprocess.check_output(["/root/.cargo/bin/rustc", "+1.99.1", "--version"], text=True).strip(),
    "bitcoin_core": "31.1",
    "sp1_revision": (build / "pins/sp1-revision").read_text().strip(),
    "cuda_build_arch": "sm_80",
    "cuda_toolkit": "12.8.93",
    "mnr04_source_base": "3db6fb889a20c630eb0d8cf00df0f64244c26ddf",
    "mnr04_source_sha256": {i: hashlib.sha256((source/i).read_bytes()).hexdigest() for i in files},
}, indent=2) + "\n")
PY
(cd "$staging" && find . -type f ! -name manifest.sha256 -print0 | sort -z | xargs -0 sha256sum > manifest.sha256)
tar -czf "$archive.part" -C "$staging" .
mv -T "$archive.part" "$archive"
sha256sum "$archive" | cut -d ' ' -f1 > "${archive%.gz}.ready.tmp"
mv -T "${archive%.gz}.ready.tmp" "${archive%.gz}.ready"
cat "${archive%.gz}.ready"
