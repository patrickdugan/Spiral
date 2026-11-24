#!/bin/bash
set -Eeuo pipefail
umask 077
dir=$(mktemp -d /var/tmp/cashu-paired.XXXXXXXX)
cd "$dir"
download() { curl -fsS --retry 1 --connect-timeout 7 --max-time "$1" -o "$2" "$3"; }
upload() { curl -fsS --retry 1 --connect-timeout 7 --max-time 75 -T "$1" "$2"; }
status() {
    printf '{"stage":"%s","exit_code":%s,"sampled_at_unix":%s}\n' "$1" "$2" "$(date +%s)" > "$dir/status.json"
    upload "$dir/status.json" 'https://example.invalid/status.json?action=put_object'
}
trap 'code=$?; if ((code)); then status failed "$code" || true; fi' EXIT
budget() {
    local remaining=$((1800 - SECONDS))
    if (( remaining < 30 )); then return 1; fi
    printf '%s\n' "$remaining"
}
run_case() {
    local name=$1; shift
    local seconds
    seconds=$(budget)
    status "${name}_started" 0
    python3 -B "$dir/shinigami-cpu-pilot/benchmarks/shinigami/run.py" "$dir/$name" \
        "$@" --threads "$threads" --max-seconds "$seconds"
}
await_input() {
    until download 16 "$1" "$2" 2>/dev/null; do
        budget >/dev/null
        sleep 5
    done
}
status booted 0
if ! test -x /usr/bin/time; then
    DEBIAN_FRONTEND=noninteractive timeout 120 apt-get update -qq
    DEBIAN_FRONTEND=noninteractive timeout 120 apt-get install -y -qq time
fi
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader > gpu.txt
grep -q A100 gpu.txt
threads=$(nproc)
if (( threads > 16 )); then threads=16; fi
await_input issuance-ready 'https://example.invalid/issuance-ready?action=get_object'
download 150 kit.tar.gz 'https://example.invalid/kit.tar.gz?action=get_object'
printf '%s  %s\n' ada77fb81e9f18d619ba2ffdb188b20497b0d73d6f7957f6222728636337a9b4 kit.tar.gz | sha256sum -c
tar -xzf kit.tar.gz
download 30 shinigami-case.json 'https://example.invalid/shinigami-case.json?action=get_object'
download 30 shinigami-case.args.json 'https://example.invalid/shinigami-case.args.json?action=get_object'
run_case issuance --regtest-case "$dir/shinigami-case.json"
upload issuance/report.json 'https://example.invalid/benchmark.json?action=put_object'
upload issuance/verifier-input.json 'https://example.invalid/verifier-input.json?action=put_object'
status issuance_proof_ready 0
await_input redemption-ready 'https://example.invalid/redemption-ready?action=get_object'
mkdir redemption-case
download 30 redemption-case/honest.args.json 'https://example.invalid/redemption-args.json?action=get_object'
download 30 redemption-case/statement.json 'https://example.invalid/redemption-statement.json?action=get_object'
sha256sum -c redemption-ready
run_case redemption --redemption-case "$dir/redemption-case"
upload redemption/report.json 'https://example.invalid/redemption-benchmark.json?action=put_object'
upload redemption/verifier-input.json 'https://example.invalid/redemption-verifier-input.json?action=put_object'
status redemption_proof_ready 0
