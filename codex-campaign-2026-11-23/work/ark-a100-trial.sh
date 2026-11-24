#!/usr/bin/env bash
set -euo pipefail
umask 077

root=$(realpath "${1:?pass isolated pilot root}")
deadline=${2:?pass provider cutoff in Unix seconds}
cd "$root"
config_sha=a800d7026670d6d2a1240ea6e60d1f8171b2216ffe103b8e826cd36693ce3238
printf '%s  cache/run.json\n' "$config_sha" | sha256sum -c -
(cd kit && sha256sum -c --quiet manifest.sha256)
test -d cache/memo && test ! -L cache/memo
exec 9>pilot.lock
flock -n 9
test ! -e pilot-start-unix && test ! -e compressed.bin

gpu=$(nvidia-smi --query-gpu=name,memory.total,compute_cap,driver_version --format=csv,noheader,nounits)
printf '%s\n' "$gpu" > gpu-start.txt
test "$(printf '%s\n' "$gpu" | wc -l)" -eq 1
grep -Eq 'A100.*80GB.*, *8\.0,' gpu-start.txt
lscpu > cpu.txt
cat /proc/meminfo > meminfo.txt
df -h . > disk.txt
test "$(df --output=avail -B1 . | tail -1)" -ge 34359738368
/lib64/ld-linux-x86-64.so.2 --list "$root/kit/ark-prove-gpu-cached-gkr" > ark-libs.txt
/lib64/ld-linux-x86-64.so.2 --list "$root/kit/shz" > shz-libs.txt
cpus=$(python3 -c 'import os; print(*sorted(os.sched_getaffinity(0))[:2])')
read -r ark_cpu nova_cpu <<<"$cpus"
test -n "$nova_cpu"
# Both services combined are limited to 4 GiB of RAM and 2 logical CPUs.
unit=(--wait --pipe --collect -p CPUQuota=100% -p MemoryMax=2G -p RuntimeMaxSec=3300)
ark_unit=ark-a100-pilot-prover
nova_unit=ark-a100-pilot-nova
free_seconds=$((deadline - 95 - $(date +%s)))
(( free_seconds >= 1200 )) || exit 5
test "$free_seconds" -le 3300 || free_seconds=3300

systemd-run --unit="$nova_unit" "${unit[@]}" -p "AllowedCPUs=$nova_cpu" -p MemorySwapMax=0 \
    --setenv=RAYON_NUM_THREADS=1 /usr/bin/timeout --signal=TERM --kill-after=15 "$free_seconds" \
    /bin/bash "$root/kit/bench-mnr04.sh" "$root/kit/shz" "$root/kit/bitcoin/bin/bitcoind" "$root/mnr04" \
    > nova-launch.log 2>&1 &
nova=$!

date +%s > pilot-start-unix
status=0
ark_env=(
  CUDA_VISIBLE_DEVICES=0
  CUDA_CACHE_PATH="$root/cuda-cache"
  ARK_SP1_TRANSIENT_TRACES=1
  NB3_GPU_MEMORY_SAVER=1 NB3_GPU_RECOMPUTE_GKR=0 NB3_GPU_DROP_LDES=1
  NB3_GPU_COMPOSE_ARITY=2 SP1_WORKER_MAX_COMPOSE_ARITY=4 SP1_WORKER_NORMALIZE_PROGRAM_CACHE_SIZE=0
  ARK_CUDA_DEVICE_POOL_MIB=7168 ARK_CUDA_POOL_RELEASE_MIB=256 ARK_CUDA_HOST_STAGING_MIB=4
  LD_PRELOAD="$root/kit/libark_cuda_call_trace.so:$root/kit/libark_host_staging.so:$root/kit/libark_private_pool.so:$root/kit/libark_cuda_pool.so"
  RUST_LOG=info
)
for name in NUM_CORE_WORKERS NUM_SPLICING_WORKERS NUM_RECURSION_EXECUTOR_WORKERS \
    NUM_PREPARE_REDUCE_WORKERS NUM_RECURSION_PROVER_WORKERS NUM_SETUP_WORKERS \
    NUM_DEFERRED_WORKERS CORE_BUFFER_SIZE RECURSION_EXECUTOR_BUFFER_SIZE \
    RECURSION_PROVER_BUFFER_SIZE SETUP_BUFFER_SIZE NUMBER_OF_GAS_EXECUTORS \
    NUMBER_OF_SEND_SPLICE_WORKERS_PER_SPLICE SPLICING_BUFFER_SIZE; do
    ark_env+=("SP1_WORKER_$name=1")
done
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,memory.total,temperature.gpu \
    --format=csv,noheader,nounits -l 5 > gpu-samples.csv 2> gpu-monitor.log &
gpu_monitor=$!
(
    over_limit=0
    while sleep 10; do
        use=$(tail -n1 gpu-samples.csv | awk -F, '{gsub(/[[:space:]]/, "", $3); print $3}')
        if [[ "$use" =~ ^[0-9]+$ ]] && (( use > 9000 )); then
            over_limit=$((over_limit + 1))
        else
            over_limit=0
        fi
        if (( over_limit >= 3 )) || (("$(df --output=avail -B1 . | tail -1)" < 4294967296)); then
            printf 'Resource stop: GPU memory %s MiB; disk monitor checked.\n' "$use" > resource-stop.txt
            systemctl stop "$ark_unit"
            break
        fi
    done
) &
guard=$!
trap 'kill "$gpu_monitor" "$guard" 2>/dev/null || true' EXIT
systemd-run --unit="$ark_unit" "${unit[@]}" -p "AllowedCPUs=$ark_cpu" -p MemoryHigh=1728M -p MemorySwapMax=4G \
    /usr/bin/timeout --signal=TERM --kill-after=15 "$free_seconds" /usr/bin/env "${ark_env[@]}" \
    "$root/kit/ark-prove-gpu-cached-gkr" prove --elf "$root/kit/inputs/guest.elf" \
    --input "$root/kit/inputs/nova-vk.raw" --input "$root/kit/inputs/nova-proof.arp" \
    --run-dir "$root/cache" --out "$root/compressed.bin" \
    --element-threshold 67108864 --height-threshold 4194304 --shard-size 16777216 \
    --trace-chunk-threshold 16777216 --trace-buffers 1 --trace-chunk-slots 1 --permits 1 > prover.log 2>&1 || status=$?
date +%s > pilot-end-unix
printf '%s\n' "$status" > pilot-exit-code
python3 "$root/kit/report-pilot.py" "$root" > pilot-result.json
nova_status=0
wait "$nova" || nova_status=$?
printf '%s\n' "$nova_status" > nova-exit-code
