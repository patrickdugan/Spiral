#!/bin/bash
set -Eeuo pipefail
umask 077
ulimit -c 0
ulimit -s 65536

kit=$(realpath -- "${1:?exact proof kit directory required}")
report=$(realpath -m -- "${2:?new report directory required}")
mkdir -- "$report" "$report/hashes"
cd "$kit"
sha256sum -c SHA256SUMS

group=/sys/fs/cgroup$(cut -d: -f3 /proc/self/cgroup)
test "$(cat "$group/memory.swap.max")" = 0
nvidia-smi -i 0 --query-gpu=name,compute_cap,memory.total,driver_version \
    --format=csv,noheader > "$report/hardware.csv"
arch=$(nvidia-smi -i 0 --query-gpu=compute_cap --format=csv,noheader | tr -d '.[:space:]')
case "$arch" in
    80|86|120) ;;
    *) printf 'Unsupported native GPU compute capability %s\n' "$arch" >&2; exit 2 ;;
esac
export CUDA_VISIBLE_DEVICES=0 LD_LIBRARY_PATH="$kit"
export STWO_CUDA_DISK_MERKLE_LIBRARY="$kit/libproofgrove_disk_merkle_sm$arch.so"
export STWO_MERKLE_DISK_DIR="$report/hashes"
export RAYON_NUM_THREADS=${RAYON_NUM_THREADS:-16} RUST_MIN_STACK=67108864 RUST_LOG=info
df -B1 -- "$report" > "$report/disk-before.txt"
gzip -dc -- "$kit/prover-input.json.gz" > "$report/prover-input.json"
printf '%s  %s\n' '267f580c26f5e8d49cd9aea39656ef225b2436823d4553b6722d8ad9f20b1366' \
    "$report/prover-input.json" | sha256sum -c

sample_resources() {
    printf 'unix,gpu_pct,vram_used_mib,ram_current_bytes,ram_peak_bytes,swap_current_bytes,pswpin,pswpout\n'
    while true; do
        gpu=$(nvidia-smi -i 0 --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits)
        ram=$(paste -d, "$group"/memory.{current,peak,swap.current})
        swap=$(awk '/^pswpin / { input=$2 } /^pswpout / { print input "," $2 }' /proc/vmstat)
        printf '%s,%s,%s,%s\n' "$(date +%s)" "${gpu// /}" "$ram" "$swap"
        sleep 2
    done
}
sample_resources > "$report/resources.csv" &
sampler=$!
finish() {
    kill "$sampler" 2>/dev/null || true
    wait "$sampler" 2>/dev/null || true
    cp -- "$group/memory.events" "$report/memory.events"
}
trap finish EXIT

/usr/bin/time -v -o "$report/prove.time" "$kit/prove-json" "$report/prover-input.json" \
    "$kit/profile.json" "$report/candidate.json" > "$report/prove.log" 2>&1
grep -Fq 'Committed disk Merkle tree with CUDA batches' "$report/prove.log"
/usr/bin/time -v -o "$report/verify.time" "$kit/scarb-verify" --proof-file "$report/candidate.json" \
    > "$report/archive-verifier.log" 2>&1
mv -- "$report/candidate.json" "$report/archive-verified.json"
sha256sum "$report/archive-verified.json" > "$report/proof.sha256"
