set -euo pipefail
umask 077
export PATH=/usr/local/cuda/bin:/usr/sbin:/usr/bin:/sbin:/bin
export LD_LIBRARY_PATH=/usr/local/cuda/lib64
root=$(mktemp -d /var/tmp/ark-mnr04-pilot.XXXXXXXX)
phase=boot
cd "$root"

notify() {
    printf '%s\n' "$1" > status.json
    curl --silent --fail --retry 2 --max-time 12 --upload-file status.json "$status_url" >/dev/null
}
trap 'code=$?; if (( code != 0 )); then notify "{\"stage\":\"failed\",\"phase\":\"$phase\"}" || true; fi' EXIT
notify '{"stage":"preparing_inputs"}'
phase=release
download() {
    local url=$1 file=$2 digest=$3
    local remaining=$(( deadline - 1350 - $(date +%s) ))
    (( remaining >= 40 ))
    curl --silent --fail --retry 2 --retry-delay 3 --connect-timeout 15 \
        --max-time "$remaining" --output "$file" "$url"
    printf '%s  %s\n' "$digest" "$file" | sha256sum -c --quiet -
}
if [[ -n "$kit_size" ]]; then
    python3 - "$kit_size" "$kit_sha" "$deadline" 3<<<"$kit_url" <<'PY'
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
import sys
import time
from urllib.request import Request, urlopen

length = int(sys.argv[1])
pin = sys.argv[2]
cutoff = int(sys.argv[3]) - 1300
url = os.fdopen(3).read().strip()
step = 2 * 1024**2


def pull(start):
    end = min(start + step, length) - 1
    for attempt in range(3):
        if time.time() >= cutoff:
            raise RuntimeError("kit transfer time cutoff")
        try:
            req = Request(url, headers={"Range": f"bytes={start}-{end}"})
            with urlopen(req, timeout=20) as response:
                sample = response.read(step + 1)
            if len(sample) == end - start + 1:
                return sample
        except OSError:
            pass
        time.sleep(2 + attempt)
    raise RuntimeError("pinned kit range could not be read")


digest = hashlib.sha256()
with ThreadPoolExecutor(max_workers=4) as queue, open("kit.tar.gz", "wb") as out:
    for chunk in queue.map(pull, range(0, length, step)):
        out.write(chunk)
        digest.update(chunk)
if digest.hexdigest() != pin:
    raise RuntimeError("pinned kit digest mismatch")
PY
else
    download "$kit_url" kit.tar.gz "$kit_sha"
fi
mkdir kit
tar --extract --gzip --file kit.tar.gz -C kit --no-same-owner --no-same-permissions
df -B1 . > disk-before-extract.txt
(( $(df --output=avail -B1 . | tail -1) > 64424509440 ))
phase=checkpoint
if [[ -n "$release_manifest_sha" ]]; then
    timeout "$((deadline - 1250 - $(date +%s)))" python3 kit/ark-a100-restore-release.py "$root" "$release_manifest_sha" "$((deadline - 1300))"
else
    download "$checkpoint_url" checkpoint.tar "$checkpoint_sha"
    tar --extract --file checkpoint.tar --no-same-owner --no-same-permissions
    rm -- checkpoint.tar
fi
rm -- kit.tar.gz
# The VM is dedicated to this pilot. Provide swap backing for the Ark cgroup.
if (( $(awk '/^SwapTotal:/ {print $2}' /proc/meminfo) < 4194304 )); then
    swap_file="$root/ark-pilot.swap"
    if fallocate -l 4G "$swap_file" && chmod 0600 "$swap_file" && mkswap "$swap_file" > swap-setup.log 2>&1; then
        swapon "$swap_file" >> swap-setup.log 2>&1 || true
    fi
fi
phase=parallel
notify '{"stage":"parallel_ark_and_mnr04"}'
ARK_PILOT_STATUS_URL="$status_url" python3 kit/ark-a100-heartbeat.py "$root" >/dev/null 2>&1 &
heartbeat=$!
trial_status=0
/bin/bash kit/ark-a100-trial.sh "$root" "$deadline" > orchestrator.log 2>&1 || trial_status=$?
kill "$heartbeat" 2>/dev/null || true
wait "$heartbeat" 2>/dev/null || true
printf '%s\n' "$trial_status" > orchestrator-exit-code
phase=pack
mkdir export
for file in pilot-result.json pilot-start-unix pilot-end-unix pilot-exit-code nova-exit-code gpu-start.txt \
    gpu-samples.csv gpu-monitor.log orchestrator.log orchestrator-exit-code nova-launch.log cpu.txt meminfo.txt disk.txt \
    disk-before-extract.txt ark-libs.txt shz-libs.txt resource-stop.txt swap-setup.log; do
    if [[ -f "$file" ]]; then cp -- "$file" export/; fi
done
if [[ -f prover.log ]]; then tail -c 2097152 prover.log > export/prover-tail.log; fi
if [[ -f cache/progress.jsonl ]]; then tail -c 8388608 cache/progress.jsonl > export/progress-tail.jsonl; fi
for file in compressed.bin mnr04/benchmark.json mnr04/proof/proof.bin \
    mnr04/core-archive.json mnr04/core.stderr mnr04/prove.stderr mnr04/verify.stderr mnr04/key.stderr; do
    if [[ -f "$file" ]] && (( $(stat -c %s "$file") < 167772160 )); then
        cp --parents -- "$file" export/
    fi
done
# Keep a complete delta when it is small enough to retrieve before the provider cutoff.
if [[ -f pilot-start-unix ]] && [[ -d cache/memo ]]; then
    find cache/memo -type f -newer pilot-start-unix -printf '%s\t%p\0' > new-memo.list
    python3 - <<'PY'
from pathlib import Path
rows = [row.split(b"\t", 1) for row in Path("new-memo.list").read_bytes().split(b"\0") if row]
with Path("export/memo-delta.txt").open("w") as report:
    selected = len(rows) > 0 and sum(int(size) for size, _ in rows) < 5 * 1024**2
    print(f"new_files={len(rows)}\nexported={str(selected).lower()}", file=report)
if selected:
    Path("memo-delta.paths").write_bytes(b"\0".join(path for _, path in rows) + b"\0")
PY
    if [[ -f memo-delta.paths ]]; then
        tar -cf export/memo-delta.tar --null --verbatim-files-from --files-from=memo-delta.paths
    fi
fi
cp kit/provenance.json export/
tar --gzip --create --file results.tar.gz -C export .
sha=$(sha256sum results.tar.gz | cut -d ' ' -f1)
size=$(stat -c %s results.tar.gz)
phase=upload
curl --silent --fail --retry 2 --max-time 54 --upload-file results.tar.gz "$result_url" >/dev/null
notify "{\"stage\":\"finished\",\"artifact_bytes\":$size,\"artifact_sha256\":\"$sha\"}"
