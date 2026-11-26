#!/bin/bash
set -Eeuo pipefail
[[ ${1:-} =~ ^[1-9][0-9]*$ ]]
[[ $(cat "$CASHU_CGROUP/memory.max") == 3221225472 && $(cat "$CASHU_CGROUP/memory.swap.max") == 0 ]]

report="$PWD/outputs/cashu-v4-cuda-archive-$1"
verified="$PWD/outputs/cashu-v4-rtx3050-independent-core"
first="$PWD/outputs/cashu-v4-first-cuda-recursion-leaf"
workload=${2:-withdrawal-v4}
if [[ "$workload" == withdrawal-v4-raw ]]; then
    report="$PWD/outputs/cashu-v4-raw-cuda-archive-$1"
    verified="$PWD/outputs/cashu-v4-raw-rtx3050-independent-core"
    first="$PWD/outputs/cashu-v4-raw-first-cuda-recursion-leaf"
else
    [[ "$workload" == withdrawal-v4 ]]
fi
if [[ ! -s "$verified/verified.json" || ! -s "$first/independent/result.json" ]]; then
    printf 'Waiting for independent verification of the Core archive and the first CUDA leaf.\n'
    exit 75
fi
job="$HOME/cashu-v4-withdrawal-rtx3050"
if [[ "$workload" == withdrawal-v4-raw ]]; then
    volume=/var/tmp/proof-grove-cashu-raw-store
    [[ $(stat -f -c '%i' "$volume") == $(<outputs/cashu-raw-storage-volume/fsid.txt) ]]
    read -r _ archive_path < "$verified/archive-sha256.txt"
    job="$volume/cashu-v4-raw-withdrawal-rtx3050"
    if [[ "$archive_path" == "$HOME/cashu-v4-raw-withdrawal-rtx3050/"* ]]; then
        job="$HOME/cashu-v4-raw-withdrawal-rtx3050"
    fi
fi
exec 9<"$job/worker.lock"
flock -n 9 || exit 75
host="$report/windows-available.csv"
healthy_host() {
    [[ ! -e "$report/host-stop" && -s "$host" ]] &&
        (( $(date +%s) - $(stat -c %Y "$host") < 15 ))
}
healthy_host
trap 'cat "$CASHU_CGROUP/memory.peak" "$CASHU_CGROUP/memory.events" "$CASHU_CGROUP/memory.swap.peak" > "$report/cgroup.txt"' EXIT

src="$PWD/work/zk-rusto-no-bitcoino/integrations/bitvm3-nova/prover/scripts"
leaf_build="$PWD/outputs/cashu-core-cuda-normalizer-linked-batch"
parent_build="$PWD/outputs/cashu-core-cuda-normalizer-linked-compose"
batch_build="$PWD/outputs/cashu-core-cuda-normalizer-linked-compose-batch"
normalizer="$leaf_build/normalize-core-cuda"
reducer="$parent_build/replay-reduction-cuda"
sealer="$PWD/outputs/cashu-compressed-root-counted/seal-compressed-root"
sealer_pin=d0f6382aad94db6de4f0b149a03b0533461c769a84fce6161db53bc7085f5b48
key="$PWD/outputs/cashu-v4-keyed-normalization/key/core-vk.bin"
program_key="$PWD/outputs/cashu-v4-first-cpu-recursion-leaf/program-key.json"
elf="$PWD/work/cashu-sp1-v4-withdrawal/cashu-withdrawal.elf"
public="$PWD/work/cashu-sp1-v4-withdrawal/public-values.bin"
statement="$PWD/work/cashu-sp1-v4-withdrawal/final-statement.json"
handoff_tool="$src/../../cashu-sp1/check-wrap-handoff.py"
manifest_pin=fad4d4e5c025336882b7e0a2bb85d321dfb1db571d71dadbb4a6f9f77b1e7f82
scratch=/mnt/e/ProofGroveCashuScratch
scratch_floor=8589934592
storage_site=checkpoint
key_pin=e3a00ba83b8366052059cbcb86ae1d6973da08be1ccf2aca36197e14fb81b7e5
elf_pin=324cb306bca741c91dec0d6c80dc62c74d63ea2ada2445fd90bc0b93b6f74853
public_pin=8c7cb7deb0650a46dbaa6eefd55ac9b7760ca14133b97a6f5970feee57898d6b
statement_pin=86ce691d58ba7bc21c39221e0a64857b4750165eb58b1d770b408d86fc876085
packed_key=0x003f751c311c96e46dd0682c5524ba12ed904d113d8bfd0046a5f59de2790e4b
if [[ "$workload" == withdrawal-v4-raw ]]; then
    raw_pins=$(python3 -B - <<'PY'
import json
from pathlib import Path

profile = json.loads(Path('work/cashu-v4-raw-profile.json').read_bytes())
for name in ('core_key', 'core_key_sha256', 'elf', 'elf_sha256', 'public_values', 'public_values_sha256',
             'statement', 'statement_sha256', 'program_vkey_bytes32', 'run_manifest_sha256'):
    print(profile[name])
PY
    )
    mapfile -t raw_profile <<< "$raw_pins"
    [[ ${#raw_profile[@]} == 10 ]]
    key="$PWD/${raw_profile[0]}"
    key_pin=${raw_profile[1]}
    elf="$PWD/${raw_profile[2]}"
    elf_pin=${raw_profile[3]}
    public="$PWD/${raw_profile[4]}"
    public_pin=${raw_profile[5]}
    statement="$PWD/${raw_profile[6]}"
    statement_pin=${raw_profile[7]}
    packed_key=${raw_profile[8]}
    manifest_pin=${raw_profile[9]}
    program_key="$first/program-key.json"
    scratch=$volume
    scratch_floor=2147483648
    checker="$PWD/outputs/cashu-core-compose-counted-build/replay-reduction-cpu"
    checker_pin=869cd0ec0f4de33ccb9549cfaf97f162a89f4dcb7ece72816187e7b1b39fd3ab
fi
recursion="$scratch/cashu-v4-recursion-$manifest_pin"
leaves="$recursion/normalized"
parents="$recursion/compose"

filesystem_available() { df -PB1 -- "$1" | awk 'NR == 2 {print $4}'; }
host_disk_available() {
    tail -n 4 "$host" | awk -F, -v field="$1" '
        $4 ~ /^[0-9]+\r?$/ && $field ~ /^[0-9]+\r?$/ {last=$field}
        END {sub(/\r$/, "", last); print last}'
}
scratch_available() {
    if [[ "$workload" == withdrawal-v4-raw ]]; then
        local free field=4 reserve=8589934592
        if [[ "$storage_site" == backing ]]; then field=3; reserve=34359738368; fi
        free=$(host_disk_available "$field")
        [[ $free =~ ^[0-9]+$ ]] && ((free >= reserve)) || return 1
    fi
    filesystem_available "$scratch"
}
if [[ ! -d $scratch ]] || { [[ "$workload" == withdrawal-v4 ]] && ! mountpoint -q /mnt/e; }; then
    printf '%s\n' 'The Cashu recursion scratch drive is unavailable.' > "$report/worker-failure.txt"
    exit 75
fi
require_scratch_reserve() {
    local free_bytes
    free_bytes=$(scratch_available) || free_bytes=
    if [[ ! $free_bytes =~ ^[0-9]+$ ]] || (( free_bytes < scratch_floor )); then
        printf '%s\n' 'Free space on the Cashu recursion scratch drive is below its reserve.' > "$report/worker-failure.txt"
        return 75
    fi
}
if [[ "$workload" == withdrawal-v4 ]]; then require_scratch_reserve; fi

{
    sha256sum -c "$leaf_build/binary-sha256.txt" "$parent_build/binary-sha256.txt"
    printf '%s  %s\n' "$key_pin" "$key" "$manifest_pin" "$job/run/run.json" "$public_pin" "$public" |
        sha256sum -c -
    printf '%s  %s\n' "$sealer_pin" "$sealer" | sha256sum -c -
    if [[ "$workload" == withdrawal-v4-raw ]]; then
        printf '%s  %s\n' "$checker_pin" "$checker" "$elf_pin" "$elf" "$statement_pin" "$statement" | sha256sum -c -
    fi
} > "$report/input-pins.log"

pins=$(PYTHONOPTIMIZE=0 PYTHONPATH="$src" python3 -B - "$job" "$verified" "$first" "$leaves" "$public_pin" "$packed_key" "$manifest_pin" "$workload" <<'PY'
import json
from pathlib import Path
import shutil
import sys
import tempfile

from extract_core_shard import read_index
from stage_core_compose import digest

job, verified, first, leaves = map(Path, sys.argv[1:5])
public, packed_key, run_pin, workload = sys.argv[5:]
core = json.loads((verified / 'verified.json').read_bytes())
assert (core['status'], core['committed_values_sha256'], core['program_vkey_bytes32']) == (
    'core_proof_verified', public, packed_key,
)
index_path = verified / 'shard-index.json'
index, _ = read_index(index_path, core['shard_index_sha256'], 1)
assert core['core_shards'] == len(index['shards'])
assert index['public_output_sha256'] == public
archive_pin, archive = (verified / 'archive-sha256.txt').read_text().strip().split('  ', 1)
archive = Path(archive)
assert archive in (job / 'proof.bin', job / 'core-recovery-unverified.bin')
assert archive_pin == index['archive_sha256'] and archive.stat().st_size == index['archive_size_bytes']

leaf = first / 'leaf'
result = json.loads((leaf / 'result.json').read_bytes())
audit = json.loads((first / 'independent/result.json').read_bytes())
assert audit['status'] == 'cpu_reduction_inputs_verified'
assert audit['child_sha256'] == [result['normalized_leaf_sha256']]
assert audit['run_manifest_sha256'] == run_pin and audit['range'] == result['range']
assert result['program_vk_digest'] == audit['program_vk_digest'] == index['program_vk_digest']
assert result['status'] == 'cuda_normalized_shard_verified'
assert digest((leaf / 'leaf.bin').read_bytes()) == result['normalized_leaf_sha256']
ordinals = [i for i, entry in enumerate(index['shards'], 1) if entry['sha256'] == result['raw_shard_sha256']]
if workload == 'withdrawal-v4-raw':
    assert ordinals == [1]
else:
    leaves.mkdir(parents=True, exist_ok=True)
if workload != 'withdrawal-v4-raw' and len(ordinals) == 1:
    target = leaves / f'{ordinals[0]:06}'
    if not target.exists():
        with tempfile.TemporaryDirectory(dir=leaves) as scratch:
            staged = Path(scratch) / 'leaf'
            staged.mkdir()
            for name in ('leaf.bin', 'result.json'):
                shutil.copyfile(leaf / name, staged / name)
            staged.rename(target)
print(archive)
print(core['shard_index_sha256'])
print(core['core_shards'])
PY
)
mapfile -t selected <<< "$pins"
[[ ${#selected[@]} == 3 ]]
archive=${selected[0]}
index_pin=${selected[1]}
count=${selected[2]}
if [[ "$workload" == withdrawal-v4-raw ]]; then
    host_free=$(host_disk_available 3)
    checkpoint_host_free=$(host_disk_available 4)
    backing_free=0
    if [[ $host_free =~ ^[0-9]+$ && $HOME == /home/pgcashu && $(findmnt -n -T "$HOME" -o FSTYPE) == ext4 ]]; then
        backing_free=$(filesystem_available "$HOME")
    fi
    placement="$verified/recursion-placement.json"
    selection=$(python3 -B work/Spiral/proof-grove/scripts/cashu-sp1/recursion_storage.py "$placement" "$count" \
        "$index_pin" "$(filesystem_available "$volume")" "$backing_free" "${host_free:-0}" \
        --checkpoint-host-free "${checkpoint_host_free:-0}")
    read -r storage_site group_size <<< "$selection"
    if [[ "$storage_site" == backing ]]; then scratch=$HOME; else [[ "$storage_site" == checkpoint ]]; fi
    recursion="$scratch/cashu-v4-recursion-$manifest_pin"
    mkdir -p -- "$recursion"
    parents="$recursion/compose"
    cp -- "$placement" "$report/recursion-placement.json"
fi
require_scratch_reserve
printf '%s\n' "$recursion" > "$report/recursion-storage.txt"

export CUDA_VISIBLE_DEVICES=0 RAYON_NUM_THREADS=2
export LD_LIBRARY_PATH=/opt/proof-grove-regtest/sp1:/usr/lib/wsl/lib
printf '%s\n' 'utc,stage,vram_used_mib,vram_free_mib,gpu_pct,cgroup_bytes,cgroup_peak_bytes,swap_bytes,scratch_free_bytes' > "$report/device.csv"

run_stage() {
    local label=$1 timer status usage current peak swap free_bytes deadline=0s
    shift
    require_scratch_reserve
    printf '%s\n' "$label" > "$report/stage.txt"
    if [[ $label == seal ]]; then deadline=600s; fi
    local command=(/usr/bin/time -v -o "$report/$label.time" timeout --kill-after=10s "$deadline" "$@")
    "${command[@]}" > "$report/$label.stdout" 2> "$report/$label.log" &
    timer=$!
    while kill -0 "$timer" 2>/dev/null; do
        if ! healthy_host; then
            printf '%s\n' host_reserve_or_heartbeat > "$report/stop-reason.txt"
            pkill -TERM -P "$timer" -x timeout || true
            break
        fi
        free_bytes=$(scratch_available) || free_bytes=
        if [[ ! $free_bytes =~ ^[0-9]+$ ]] || (( free_bytes < scratch_floor )); then
            printf '%s\n' scratch_disk_reserve > "$report/stop-reason.txt"
            pkill -TERM -P "$timer" -x timeout || true
            break
        fi
        usage=$(timeout 4s /usr/lib/wsl/lib/nvidia-smi --query-gpu=memory.used,memory.free,utilization.gpu --format=csv,noheader,nounits) || usage=',,'
        current=$(cat "$CASHU_CGROUP/memory.current")
        peak=$(cat "$CASHU_CGROUP/memory.peak")
        swap=$(cat "$CASHU_CGROUP/memory.swap.current")
        printf '%s,%s,%s,%s,%s,%s,%s\n' "$(date -u +%FT%TZ)" "$label" "${usage// /}" "$current" "$peak" "$swap" "$free_bytes" >> "$report/device.csv"
        sleep 3
    done
    status=0
    wait "$timer" || status=$?
    if ((status != 0)); then
        printf '%s exited %s\n' "$label" "$status" > "$report/worker-failure.txt"
        tail -n 12 "$report/$label.log"
        return "$status"
    fi
}

normalize_args=(
    "$src/normalize_core_archive.py" "$archive" "$verified/shard-index.json" "$index_pin"
    "$job/run/run.json" "$manifest_pin" "$program_key" "$elf" "$key" "$key_pin" "$leaves" "$normalizer"
    --progress "$report/normalize-progress.jsonl"
)
if [[ "$workload" == withdrawal-v4 ]]; then run_stage normalize python3 -B "${normalize_args[@]}"; fi
printf '%s\n' build_compose > "$report/stage.txt"
batch_deadline=$(( $(date +%s) + 540 ))
while [[ "$workload" == withdrawal-v4 && ! -s "$batch_build/binary-sha256.txt" && ! -s "$report/compose-build-failed.txt" ]]; do
    healthy_host || exit 1
    if (( $(date +%s) >= batch_deadline )); then break; fi
    sleep 3
done
compose_mode=()
batch_ready="$batch_build/binary-sha256.txt"
if [[ "$workload" == withdrawal-v4-raw ]]; then
    batch_ready="$PWD/outputs/cashu-persistent-reducer-build-control/production-ready.sha256"
fi
if [[ -s "$batch_ready" ]] && cmp -s -- "$batch_ready" "$batch_build/binary-sha256.txt" &&
        sha256sum -c "$batch_ready" >> "$report/input-pins.log"; then
    reducer="$batch_build/replay-reduction-cuda"
    compose_mode=(--batch-stdin)
    printf '%s\n' persistent_cuda > "$report/compose-backend.txt"
else
    printf '%s\n' single_request_cuda > "$report/compose-backend.txt"
fi
compose_args=(
    "$src/compose_core_tree.py" "$job/run/run.json" "$manifest_pin" "$program_key"
    "$verified/shard-index.json" "$index_pin" "$leaves" "$parents" "$reducer"
    --progress "$report/compose-progress.jsonl"
)
if [[ "$workload" == withdrawal-v4-raw ]]; then
    bounded_mode=(--memory-shards)
    if (( ${#compose_mode[@]} )); then bounded_mode+=(--batch-reducer); fi
    run_stage bounded_recursion python3 -B "$src/compose_core_bounded.py" "$archive" "$verified/shard-index.json" "$index_pin" \
        "$job/run/run.json" "$manifest_pin" "$program_key" "$elf" "$key" "$key_pin" "$parents" \
        "$normalizer" "$reducer" "$checker" --group-size "$group_size" \
        --progress "$report/normalize-progress.jsonl" "${bounded_mode[@]}"
    root="$parents/complete/root/reduction.bin"
else
    run_stage compose python3 -B "${compose_args[@]}" "${compose_mode[@]}"
    root="$parents/root/reduction.bin"
fi
seal_directory=$job
if [[ "$workload" == withdrawal-v4-raw ]]; then seal_directory=$recursion; fi
sealed="$seal_directory/verified-compressed.bin"
attempt_archive="$seal_directory/verified-compressed-$1.bin"
seal_args=(
    "$elf" "$elf_pin" "$root" "$public" "$public_pin"
    "$packed_key" "$attempt_archive" --expect-shards "$count"
)
run_stage seal "$sealer" "${seal_args[@]}"
if ! ln -- "$attempt_archive" "$sealed"; then cmp -- "$attempt_archive" "$sealed"; fi
if ! python3 -B "$handoff_tool" --archive "$sealed" --root "$root" --seal-receipt "$report/seal.stdout" \
    --statement "$statement" --statement-sha256 "$statement_pin" --elf-sha256 "$elf_pin" \
    --core-shards "$count" > "$report/m13-handoff.pending" 2> "$report/m13-handoff.log"; then
    printf '%s\n' 'The stock seal did not match the pinned M13 handoff.' > "$report/worker-failure.txt"
    cat "$report/m13-handoff.log" >&2
    exit 1
fi
cp -- "$sealed" "$report/verified-compressed.pending"
cp -- "$root" "$report/reduction-root.pending"
cmp -- "$sealed" "$report/verified-compressed.pending"
cmp -- "$root" "$report/reduction-root.pending"
mv -- "$report/verified-compressed.pending" "$report/verified-compressed.bin"
mv -- "$report/reduction-root.pending" "$report/reduction-root.bin"
mv -- "$report/m13-handoff.pending" "$report/m13-handoff.json"
printf '%s\n' compressed_proof_verified > "$report/stage.txt"
cat "$report/seal.stdout"
