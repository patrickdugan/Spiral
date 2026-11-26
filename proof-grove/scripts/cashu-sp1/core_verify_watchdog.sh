#!/usr/bin/env bash
# The caller owns the archive lock and the started verifier's direct timer.

core_archive_identity() {
    stat -L -c '%d:%i:%s:%y:%z' -- "$1"
}

wait_for_core_verifier() {
    local timer=$1 log=$2 stop=$3 quiet_limit=${4:-300} poll_seconds=${5:-3}
    local now last_report observed status=0 terminated=false
    last_report=$(date +%s)
    while kill -0 "$timer" 2>/dev/null; do
        now=$(date +%s)
        if observed=$(stat -c '%Y' "$log"); then last_report=$observed; fi
        if ((now - last_report >= quiet_limit)); then
            if pkill -TERM -P "$timer" -x timeout; then terminated=true; fi
            break
        fi
        sleep "$poll_seconds"
    done
    wait "$timer" || status=$?
    if $terminated && [[ $status == 124 || $status == 137 || $status == 143 ]]; then
        printf '%s\n' no_verifier_progress_for_300s > "$stop"
        return 124
    fi
    return "$status"
}

can_retry_core_verifier() {
    local status=$1 stop=$2 memory_events=$3 archive=$4 original_identity=$5
    [[ "$status" == 124 && -s "$stop" && $(<"$stop") == no_verifier_progress_for_300s ]] &&
        grep -Fxq 'oom 0' "$memory_events" && grep -Fxq 'oom_kill 0' "$memory_events" &&
        [[ $(core_archive_identity "$archive") == "$original_identity" ]]
}
