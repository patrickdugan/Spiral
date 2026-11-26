param([ValidatePattern('^sustained-[1-9][0-9]+$')][string]$Attempt = 'sustained-17',
      [string]$Report = 'outputs/cashu-v4-raw-continuation')

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/core-continuation.ps1"
New-Item -ItemType Directory -Path $Report -Force | Out-Null
$guard = [IO.FileStream]::new((Join-Path (Resolve-Path -LiteralPath $Report).Path 'supervisor.lock'),
    [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
$launcher = (Get-Process -Id $PID).Path
$definition = Get-Content work/rtx3050-guarded-host.ps1 -Raw
Add-Type -TypeDefinition ([regex]::Match($definition, '(?sm)using System;.*?^\}').Value)
$stallRetryAvailable = $true

function Record-Continuation($Event, $Fields) {
    [ordered]@{utc=[DateTimeOffset]::UtcNow.ToString('o');attempt=$Attempt;event=$Event;details=$Fields} |
        ConvertTo-Json -Compress | Add-Content -LiteralPath "$Report/events.jsonl" -Encoding utf8NoBOM
}

try {
    while ($true) {
        $run = "outputs/cashu-v3-rtx3050-$Attempt"
        $handles = Get-Content -LiteralPath "$run/handoff-processes.json" -Raw | ConvertFrom-Json
        if ($handles.attempt -ne $Attempt -or $handles.storage -ne 'compressed') {
            throw 'The continuation requires the exact compressed Cashu handle.'
        }
        $identity = Get-CimInstance Win32_Process -Filter "ProcessId = $($handles.supervisor_pid)"
        if ($identity -and $identity.CommandLine -notmatch ("run-cashu-rtx3050-host\.ps1.*-Attempt\s+" +
                [regex]::Escape($Attempt) + '\s+-RawWithdrawal\s+-CompressedStore')) {
            throw 'The previous process handle is assigned to a different command.'
        }
        $worker = Get-Process -Id $handles.supervisor_pid -ErrorAction SilentlyContinue
        if ($worker -and !$identity) { throw 'The active prover host could not be identified.' }
        Record-Continuation 'monitoring' @{host_pid=$handles.supervisor_pid; verifier_pid=$handles.verifier_pid}
        while ($worker -and !$worker.WaitForExit(5000)) {}
        $terminal = "$run/worker-exit.txt"
        if (!(Test-Path -LiteralPath $terminal -PathType Leaf)) {
            throw 'The Cashu host ended without a worker exit receipt.'
        }
        $exitCode = (Get-Content -LiteralPath $terminal -Raw).Trim()
        $stop = (Get-Content -LiteralPath "$run/host-stop" -Raw -ErrorAction SilentlyContinue)?.Trim()
        $reason = (Get-Content -LiteralPath "$run/stop-reason.txt" -Raw -ErrorAction SilentlyContinue)?.Trim()
        $legacyRamStop = $false
        if ($stop -ceq 'Windows available memory or disk space fell below its reserve.') {
            $last = (Get-Content -LiteralPath "$run/windows-available.csv" -Tail 1) -split ','
            $legacyRamStop = $last.Count -ge 2 -and $last[1] -match '^\d+$' -and [long]$last[1] -lt 1GB
        }
        $memoryEvents = "$run/memory.events"
        $noOomKills = (Test-Path -LiteralPath $memoryEvents -PathType Leaf) -and
            (Select-String -LiteralPath $memoryEvents -Pattern '^oom_kill 0$' -Quiet)
        $action = Get-CashuCoreContinuation $exitCode $reason $stop $noOomKills $legacyRamStop $stallRetryAvailable
        if ($action -ceq 'finished') {
            Record-Continuation 'core_worker_finished' @{exit_code=$exitCode}
            break
        }
        if ($action -ceq 'inspect') {
            Record-Continuation 'terminal_receipt' @{exit_code=$exitCode;stop_reason=$reason;host_stop=$stop}
            break
        }
        $recoverStall = $action -ceq 'core_stall'
        if ($recoverStall) { $stallRetryAvailable = $false }
        Record-Continuation 'waiting_for_host_reserves' @{reason=$action;windows_reserve_bytes=1GB;
            workspace_reserve_bytes=8GB;backing_reserve_bytes=16GB;archive_reserve_bytes=8GB}
        $healthy = 0
        while ($healthy -lt 3) {
            $available = [ProofGroveHostMemory]::AvailableBytes()
            if ($available -ge 1GB -and (Get-PSDrive C).Free -ge 8GB -and (Get-PSDrive D).Free -ge 16GB -and
                    (Get-PSDrive E).Free -ge 8GB) { $healthy++ } else { $healthy = 0 }
            if ($healthy -lt 3) { Start-Sleep -Seconds 10 }
        }
        $index = [int]$Attempt.Substring('sustained-'.Length) + 1
        $next = "sustained-$index"
        $pipeline = [int]$handles.pipeline_run + 1
        if ($pipeline -lt 2) { $pipeline = 2 }
        $resumeArgs = @('-Current',$Attempt,'-Next',$next,'-PipelineRun',$pipeline)
        if ($recoverStall) { $resumeArgs += '-RecoverStall' }
        & $launcher -NoProfile -File work/resume-cashu-raw-storage.ps1 @resumeArgs
        if ($LASTEXITCODE -ne 0) { throw "Cashu restart from $Attempt exited with code $LASTEXITCODE." }
        Record-Continuation 'checkpoint_resumed' @{next_attempt=$next;pipeline_run=$pipeline}
        $Attempt = $next
    }
} catch {
    Record-Continuation 'supervisor_error' @{message=$_.Exception.Message}
    throw
} finally {
    $guard.Dispose()
}
