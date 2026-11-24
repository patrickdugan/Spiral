#!/bin/bash
set -Eeuo pipefail
umask 077
dir=$(mktemp -d /var/tmp/cashu-shinigami.XXXXXXXX)
cd "$dir"
status() {
    python3 - "$1" "$2" "$dir" > "$dir/status.json" <<'PY'
import json, os, pathlib, sys, time
stage, code, directory = sys.argv[1:]
root = pathlib.Path(directory)
data = {"stage": stage, "exit_code": int(code), "sampled_at_unix": int(time.time())}
gpu = root / "gpu.txt"
if gpu.exists():
    data["a100_confirmed"] = "A100" in gpu.read_text()
report = root / "run/report.json"
if report.exists():
    benchmark = json.loads(report.read_text())
    data.update(phase=benchmark["status"], threads=benchmark["rayon_threads"])
mem = {line.split(":", 1)[0]: int(line.split()[1]) for line in pathlib.Path("/proc/meminfo").read_text().splitlines() if line.startswith(("MemTotal:", "MemAvailable:"))}
data.update(logical_cpus=len(os.sched_getaffinity(0)), host_ram_gib=round(mem["MemTotal"]/1048576, 2), host_ram_used_gib=round((mem["MemTotal"]-mem["MemAvailable"])/1048576, 2))
print(json.dumps(data))
PY
    curl -fsS --retry 1 --connect-timeout 5 --max-time 12 -T "$dir/status.json" https://example.invalid/status.json
}
finish() {
    code=$?
    trap - EXIT
    if test -n "${sampler:-}"; then kill "$sampler" 2>/dev/null || true; wait "$sampler" || true; fi
    if test -s "$dir"/run/verifier-input.json; then
        curl -fsS --retry 2 --connect-timeout 10 --max-time 45 -T "$dir"/run/verifier-input.json https://example.invalid/verifier-input.json || code=1
    fi
    if test -s "$dir"/run/report.json; then
        curl -fsS --retry 2 --connect-timeout 10 --max-time 25 -T "$dir"/run/report.json https://example.invalid/benchmark.json || code=1
    fi
    status finished "$code" || true
    exit "$code"
}
trap finish EXIT
status booted 0
if ! test -x /usr/bin/time; then
    DEBIAN_FRONTEND=noninteractive timeout 120 apt-get update -qq
    DEBIAN_FRONTEND=noninteractive timeout 120 apt-get install -y -qq time
fi
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader > gpu.txt
grep -q A100 gpu.txt
curl -fsS --retry 2 --connect-timeout 10 --max-time 150 -o kit.tar.gz https://example.invalid/kit.tar.gz
printf '%s  %s\n' ada77fb81e9f18d619ba2ffdb188b20497b0d73d6f7957f6222728636337a9b4 kit.tar.gz | sha256sum -c
tar -xzf kit.tar.gz
curl -fsS --retry 2 --connect-timeout 10 --max-time 25 -o shinigami-case.json https://example.invalid/shinigami-case.json
curl -fsS --retry 2 --connect-timeout 10 --max-time 25 -o shinigami-case.args.json https://example.invalid/shinigami-case.args.json
status benchmark_started 0
sampler=''
(trap - EXIT; while true; do status benchmark_running 0 || true; sleep 8; done) &
sampler=$!
cd shinigami-cpu-pilot
threads=$(nproc)
if (( threads > 16 )); then threads=16; fi
python3 -B benchmarks/shinigami/run.py ../run --regtest-case ../shinigami-case.json --threads "$threads" --max-seconds 1800
cd "$dir"
