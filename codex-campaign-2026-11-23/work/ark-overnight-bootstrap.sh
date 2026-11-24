set -euo pipefail
umask 077
export PATH=/usr/local/cuda/bin:/usr/sbin:/usr/bin:/sbin:/bin
export LD_LIBRARY_PATH=/usr/local/cuda/lib64
root=$(mktemp -d /var/tmp/ark-overnight.XXXXXXXX)
cd "$root"
phase=boot
heartbeat=''
exporter=''
notify() {
    printf '%s\n' "$1" > status.json
    curl --silent --fail --retry 2 --max-time 12 --upload-file status.json "$status_url" >/dev/null
}
preparing() {
    notify "{\"stage\":\"preparing_inputs\",\"prepare_phase\":\"$1\"}"
}
finish() {
    code=$?
    if [[ -n "$heartbeat" ]]; then kill "$heartbeat" 2>/dev/null || true; fi
    if (( code != 0 )); then notify "{\"stage\":\"failed\",\"phase\":\"$phase\"}" || true; fi
}
trap finish EXIT
preparing kit
phase=bootstrap
verified_fetch() {
    curl --silent --fail --retry 3 --connect-timeout 15 --max-time 180 --output "$2" "$1"
    printf '%s  %s\n' "$3" "$2" | sha256sum -c --quiet -
}
verified_fetch "$transport_url" transport.json "$transport_sha"
verified_fetch "$runner_url" runner.tar.gz "$runner_sha"
tar -xzf runner.tar.gz --no-same-owner --no-same-permissions
phase=kit
python3 - "$root" <<'PY'
import hashlib,json,pathlib,sys
from concurrent.futures import ThreadPoolExecutor
import urllib.request
cfg=json.loads(pathlib.Path("transport.json").read_text())
kit=cfg["kit"]
size=2*1024**2
def get(offset):
    bound=min(offset+size,kit["bytes"])-1
    request=urllib.request.Request(kit["url"],headers={"Range":f"bytes={offset}-{bound}"})
    for _ in range(4):
        try:
            with urllib.request.urlopen(request,timeout=20) as r: part=r.read(size+1)
            if len(part)==bound-offset+1: return part
        except OSError: pass
    raise RuntimeError("verified kit range unavailable")
sha=hashlib.sha256()
with ThreadPoolExecutor(max_workers=5) as pool, open("kit.tar.gz","wb") as out:
    for part in pool.map(get,range(0,kit["bytes"],size)):
        sha.update(part)
        out.write(part)
if sha.hexdigest()!=kit["sha256"]: raise RuntimeError("GPU kit digest mismatch")
PY
mkdir kit
tar -xzf kit.tar.gz -C kit --no-same-owner --no-same-permissions
phase=checkpoint
test "$(df --output=avail -B1 . | tail -1)" -ge 64424509440
preparing public_base || true
timeout 1500 python3 kit/ark-a100-restore-release.py "$root" "$release_sha" "$((deadline-600))"
preparing private_seed || true
timeout 1800 python3 ark-overnight-worker.py restore "$root"
rm -- kit.tar.gz
if (( $(awk '/^SwapTotal:/ {print $2}' /proc/meminfo) < 4194304 )); then
    if fallocate -l 4G "$root/ark.swap" && chmod 0600 "$root/ark.swap" && mkswap "$root/ark.swap" > swap-setup.log 2>&1; then
        swapon "$root/ark.swap" >> swap-setup.log 2>&1 || true
    fi
fi
phase=durability
preparing export || true
python3 ark-overnight-worker.py export "$root" > checkpoint-export.log 2>&1 &
exporter=$!
for _ in {1..60}; do
    test ! -e checkpoint-export-ready || break
    kill -0 "$exporter"
    sleep 2
done
test -f checkpoint-export-ready
phase=prove
notify '{"stage":"ark_overnight"}'
ARK_PILOT_STATUS_URL="$status_url" python3 ark-a100-heartbeat.py "$root" >/dev/null 2>&1 &
heartbeat=$!
bash ark-overnight-trial.sh "$root" "$deadline" > orchestrator.log 2>&1 &
proof=$!
while kill -0 "$proof" 2>/dev/null; do
    if ! kill -0 "$exporter" 2>/dev/null; then
        if systemctl is-active --quiet ark-a100-pilot-prover; then systemctl stop ark-a100-pilot-prover; fi
        break
    fi
    sleep 15
done
proof_status=0
wait "$proof" || proof_status=$?
printf '%s\n' "$proof_status" > orchestrator-exit-code
kill "$heartbeat" 2>/dev/null || true
wait "$heartbeat" 2>/dev/null || true
heartbeat=''
phase=export
touch stop-export
until [[ -f checkpoint-export-finished ]] || ! kill -0 "$exporter" 2>/dev/null; do
    (( $(date +%s) < deadline - 45 )) || break
    sleep 5
done
mkdir report
for file in pilot-result.json pilot-start-unix pilot-end-unix pilot-exit-code orchestrator-exit-code orchestrator.log gpu-start.txt seed-restored.json resource-stop.txt; do
    if [[ -f "$file" ]]; then cp -- "$file" report/; fi
done
if [[ -f prover.log ]]; then tail -c 524288 prover.log > report/prover-tail.log; fi
if [[ -f checkpoint-export.log ]]; then tail -c 262144 checkpoint-export.log > report/checkpoint-export.log; fi
if [[ -f compressed.bin ]]; then
    curl --silent --fail --retry 2 --max-time 60 --upload-file compressed.bin "$compressed_url" >/dev/null
    sha256sum compressed.bin > report/compressed.sha256
fi
tar -czf overnight-results.tar.gz -C report .
sha=$(sha256sum overnight-results.tar.gz | cut -d ' ' -f1)
bytes=$(stat -c %s overnight-results.tar.gz)
curl --silent --fail --retry 2 --max-time 30 --upload-file overnight-results.tar.gz "$result_url" >/dev/null
durable=false
if [[ -f checkpoint-export-finished ]]; then durable=true; fi
notify "{\"stage\":\"finished\",\"artifact_bytes\":$bytes,\"artifact_sha256\":\"$sha\",\"checkpoint_export_finished\":$durable}"
