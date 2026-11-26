#!/usr/bin/env bash
set -Eeuo pipefail
. "$(dirname "$0")/core_verify_watchdog.sh"

scratch=$(mktemp -d)
trap 'rm -f -- "$scratch"/{verify.log,stop.txt,archive.bin,memory.events}; rmdir -- "$scratch"' EXIT
log="$scratch/verify.log"
stop="$scratch/stop.txt"
archive="$scratch/archive.bin"
events="$scratch/memory.events"

status=0
/usr/bin/time timeout 0s bash -c 'exit 26' 2> "$log" &
wait_for_core_verifier "$!" "$log" "$stop" 3 0.1 || status=$?
[[ $status == 26 && ! -e "$stop" ]]

printf '%s\n' 'archive control' > "$archive"
printf '%s\n' 'oom 0' 'oom_kill 0' > "$events"
identity=$(core_archive_identity "$archive")
status=0
/usr/bin/time timeout --kill-after=1s 0s sleep 20 2> "$log" &
wait_for_core_verifier "$!" "$log" "$stop" 1 0.1 || status=$?
[[ $status == 124 && $(<"$stop") == no_verifier_progress_for_300s ]]
can_retry_core_verifier "$status" "$stop" "$events" "$archive" "$identity"

printf '%s\n' 'oom 1' 'oom_kill 0' > "$events"
if can_retry_core_verifier "$status" "$stop" "$events" "$archive" "$identity"; then exit 1; fi
printf '%s\n' 'oom 0' 'oom_kill 0' > "$events"
printf '%s\n' 'changed' >> "$archive"
if can_retry_core_verifier "$status" "$stop" "$events" "$archive" "$identity"; then exit 1; fi
printf '%s\n' 'Core verifier exit, watchdog, zero-OOM retry and archive identity controls passed.'
