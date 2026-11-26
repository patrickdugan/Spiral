#!/bin/bash
set -Eeuo pipefail
. "$(dirname "$0")/core_verify_watchdog.sh"
[[ $(cat "$CASHU_CGROUP/memory.max") == 1520435200 && $(cat "$CASHU_CGROUP/memory.swap.max") == 0 ]]
export RAYON_NUM_THREADS=1
profile=${1:-settlement-v3}
report="$PWD/outputs/cashu-v3-rtx3050-independent-core"
verifier="$PWD/work/cashu-stream-verifier-cached-build/verify-cashu-core-cached"
indexed="$PWD/work/cashu-indexed-verifier-cached-build/verify-cashu-core-cached"
index_ready="$PWD/outputs/cashu-core-shard-index-control/production-ready.sha256"
parallel="$PWD/outputs/cashu-parallel-core-verifier-build/verify-cashu-core-cached"
parallel_ready="$PWD/outputs/cashu-parallel-core-verifier-control/production-ready.sha256"
wider_dir="$PWD/outputs/cashu-four-worker-core-verifier-build"
wider="$wider_dir/verify-cashu-core-cached"
wider_ready="$wider_dir/production-ready.sha256"
index_options=()
verifier_options=()
verification_limit=43200s
if [[ -s $index_ready ]] && (cd "$(dirname "$indexed")" && sha256sum -c "$index_ready" >&2); then
    verifier="$indexed"
elif [[ $profile == withdrawal-v4* ]]; then
    printf '%s\n' 'The indexed Core verifier pin is required for the Cashu withdrawal handoff.' >&2
    exit 65
fi
elf="$PWD/work/cashu-sp1-v3-settlement/cashu-settlement.elf"
proof="$HOME/cashu-v3-rtx3050-production-shards/core-recovery-unverified.bin"
if [[ ! -s "$proof" ]]; then proof="$HOME/cashu-v3-rtx3050-production-shards/proof.bin"; fi
expected=e418164a3475ff948406e7b38d4193c01e3a393f96d715f884bc72d4266a69c2
key="$PWD/outputs/cashu-v3-rtx3050-sustained/core-vk-verified.bin"
key_sha=12de76aa95861771eb2a464d347b3c796f29432bd8ea5c8292fdd16cc953de82
program=8435f74771e40b1730e5665236465e32988a563b687c8f3f151d0823c15a2757
elf_sha=0f88555bbbf59596692948696206f615141ee7e298a28ed7f595948191fd1b41
key_args=("$key" "$key_sha" "$program")
worker_lock=
case "$profile" in
    settlement-v3) ;;
    withdrawal-v4)
        report="$PWD/outputs/cashu-v4-rtx3050-independent-core"
        elf="$PWD/work/cashu-sp1-v4-withdrawal/cashu-withdrawal.elf"
        proof=${2:?supply the finished withdrawal Core archive}
        expected=8c7cb7deb0650a46dbaa6eefd55ac9b7760ca14133b97a6f5970feee57898d6b
        program=188eba1f1bb925478a050d3a2ea14b528968826c01f42f763beb4b0d4b0e7962
        elf_sha=324cb306bca741c91dec0d6c80dc62c74d63ea2ada2445fd90bc0b93b6f74853
        packed_key=0x003f751c311c96e46dd0682c5524ba12ed904d113d8bfd0046a5f59de2790e4b
        key_args=()
        worker_lock="$HOME/cashu-v4-withdrawal-rtx3050/worker.lock"
        ;;
    withdrawal-v4-raw)
        report="$PWD/outputs/cashu-v4-raw-rtx3050-independent-core"
        elf="$PWD/outputs/cashu-v4-raw-withdrawal-guest-4/cashu-withdrawal.elf"
        proof=${2:?supply the finished raw withdrawal Core archive}
        expected=8c7cb7deb0650a46dbaa6eefd55ac9b7760ca14133b97a6f5970feee57898d6b
        program=97195718ad97a73de1c48f454d41a336a3bb11446a9c8d00b31f701bd333cf49
        elf_sha=677921c6d47784754fcf6f68d28425b9d423e82efe5b42c8a43e06bf6912d7eb
        packed_key=0x0030ae332ef69e5eb62c7e270b6a3414d88237746023671a8db80fd9c9cf33d3
        key="$PWD/outputs/cashu-v4-raw-first-core-shard/key/core-vk.bin"
        key_sha=c8f06ed9ccaafb001889efdf3c0e313953ab32b3fff0362d76f67ad6df7c8d80
        key_args=("$key" "$key_sha" "$program")
        verification_limit=0s
        worker_lock="$HOME/cashu-v4-raw-withdrawal-rtx3050/worker.lock"
        if [[ "$proof" == /var/tmp/proof-grove-cashu-raw-store/cashu-v4-raw-withdrawal-rtx3050/* ]]; then
            worker_lock=/var/tmp/proof-grove-cashu-raw-store/cashu-v4-raw-withdrawal-rtx3050/worker.lock
        fi
        ;;
    *) exit 2 ;;
esac
if [[ $profile == withdrawal-v4-raw && -s $parallel_ready ]] &&
        (cd "$(dirname "$parallel")" && sha256sum -c "$parallel_ready" >&2); then
    verifier="$parallel"
    verifier_options=(--parallel-shards)
fi
if [[ $profile == withdrawal-v4-raw && -s $wider_ready && -s "$wider_dir/verified-worker-count.txt" ]] &&
        (cd "$wider_dir" && sha256sum -c "$wider_ready" >&2); then
    workers=$(<"$wider_dir/verified-worker-count.txt")
    if [[ $workers =~ ^[34]$ ]]; then
        verifier="$wider"
        verifier_options=(--shard-workers "$workers")
    fi
fi
if [[ $verifier == "$indexed" || $verifier == "$parallel" || $verifier == "$wider" ]]; then
    index_options=(--shard-index "$report/shard-index.json")
fi
mkdir "$report"
record_resources() {
    cat "$CASHU_CGROUP/memory.peak" "$CASHU_CGROUP/memory.events" "$CASHU_CGROUP/memory.swap.peak" > "$report/cgroup.txt"
}
trap record_resources EXIT
: > "$report/verify.log"
printf '%s\n' verify_archive > "$report/stage.txt"
if [[ -n $worker_lock ]]; then
    # The GPU supervisor holds this lock until its final archive work ends.
    exec 9<"$worker_lock"
    printf '%s\n' 'Waiting for the Cashu Core worker to release the archive before independent verification.'
    deadline=$((SECONDS + 1800))
    until flock -n 9; do
        if (( SECONDS >= deadline )); then
            printf '%s\n' core_worker_lock_timeout > "$report/stop-reason.txt"
            exit 124
        fi
        touch "$report/verify.log"
        sleep 5
    done
fi
printf '%s  %s\n' "$elf_sha" "$elf" \
    | sha256sum -c - > "$report/elf-pin.log"
if (( ${#key_args[@]} )); then
    printf '%s  %s\n' "$key_sha" "$key" | sha256sum -c - > "$report/core-key-pin.log"
fi
test -s "$verifier" && test -s "$proof"
sha256sum "$verifier" > "$report/verifier-sha256.txt"
stat -c '%s' "$proof" > "$report/archive-bytes.txt"
printf '%s\n' "${verifier_options[@]}" > "$report/verifier-options.txt"
verify_archive() {
    /usr/bin/time -v -o "$report/verify.time" timeout --kill-after=8s "$verification_limit" \
        "$verifier" "${verifier_options[@]}" "$elf" "$proof" "$expected" "${key_args[@]}" "${index_options[@]}" \
        > "$report/verified.next" 2> "$report/verify.log" &
    wait_for_core_verifier "$!" "$report/verify.log" "$report/stop-reason.txt"
}
archive_identity=$(core_archive_identity "$proof")
if verify_archive; then
    :
else
    result=$?
    if [[ $profile != withdrawal-v4-raw || ${#verifier_options[@]} == 0 || -e "$report/shard-index.json" ]] ||
            ! can_retry_core_verifier "$result" "$report/stop-reason.txt" "$CASHU_CGROUP/memory.events" "$proof" "$archive_identity"; then
        exit "$result"
    fi
    interrupted="$report/interrupted-parallel-verifier"
    mkdir -- "$interrupted"
    mv -- "$report/verify.log" "$report/verify.time" "$report/verified.next" "$report/verifier-options.txt" \
        "$report/stop-reason.txt" "$interrupted/"
    cp -- "$CASHU_CGROUP/memory.events" "$interrupted/memory.events"
    verifier_options=()
    printf '%s\n' 'Serial retry of the pinned archive after a parallel verification stall.' | tee "$report/retry.txt"
    printf '%s\n' 'serial retry' > "$report/verifier-options.txt"
    verify_archive
fi
if [[ -n ${packed_key:-} ]]; then
    python3 - "$report/verified.next" "$packed_key" "$expected" <<'PY'
import json
from pathlib import Path
import sys

receipt = json.loads(Path(sys.argv[1]).read_bytes())
assert receipt['status'] == 'core_proof_verified'
assert receipt['program_vkey_bytes32'] == sys.argv[2]
assert receipt['committed_values_sha256'] == sys.argv[3]
PY
fi
if (( ${#index_options[@]} )); then
    python3 - "$report" "$proof" "$program" "$expected" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

report, archive = map(Path, sys.argv[1:3])
index_bytes = (report / 'shard-index.json').read_bytes()
index = json.loads(index_bytes)
receipt = json.loads((report / 'verified.next').read_bytes())
assert receipt['status'] == 'core_proof_verified'
assert receipt['shard_index_sha256'] == hashlib.sha256(index_bytes).hexdigest()
assert index['archive_size_bytes'] == archive.stat().st_size
assert (index['program_vk_digest'], index['public_output_sha256']) == tuple(sys.argv[3:])
assert len(index['shards']) == receipt['core_shards']
(report / 'archive-sha256.txt').write_text(f"{index['archive_sha256']}  {archive}\n", encoding='utf-8')
PY
else
    printf '%s\n' hash_verified_archive > "$report/stage.txt"
    sha256sum "$proof" > "$report/archive-sha256.txt"
fi
if [[ -n $worker_lock ]]; then flock -u 9; fi
mv -- "$report/verified.next" "$report/verified.json"
printf '%s\n' archived > "$report/stage.txt"
cat "$report/verified.json"
