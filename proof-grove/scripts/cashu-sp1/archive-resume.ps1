function Get-CashuArchiveInterruption([string]$Report, [int]$ExitCode) {
    if ($ExitCode -notin 137,143 -or (Test-Path -LiteralPath "$Report/verified-compressed.bin") -or
            (Test-Path -LiteralPath "$Report/m13-handoff.json")) { return }
    foreach ($file in 'stage.txt','stop-reason.txt','cgroup.txt','recursion-placement.json') {
        if (!(Test-Path -LiteralPath "$Report/$file" -PathType Leaf)) { return }
    }
    if ((Get-Content -LiteralPath "$Report/stage.txt" -Raw).Trim() -cne 'bounded_recursion') { return }
    $reason = (Get-Content -LiteralPath "$Report/stop-reason.txt" -Raw).Trim()
    if ($reason -cnotin 'host_reserve_or_heartbeat','scratch_disk_reserve') { return }
    if (Test-Path -LiteralPath "$Report/host-stop") {
        $hostStop = (Get-Content -LiteralPath "$Report/host-stop" -Raw).Trim()
        if ($hostStop -cnotin 'Windows memory fell below the 1 GiB reserve.','Free space fell below a drive reserve.') { return }
    }
    $memory = Get-Content -LiteralPath "$Report/cgroup.txt" -Raw
    if ($memory -cnotmatch '(?m)^oom 0\r?$' -or $memory -cnotmatch '(?m)^oom_kill 0\r?$' -or
            ($memory -split '\r?\n' | Where-Object { $_ })[-1] -cne '0') { return }
    return $reason
}

function Save-CashuArchiveInterruption([string]$Report, [string]$Reason, [int]$ExitCode) {
    $history = Join-Path $Report ('interruptions/' + [Guid]::NewGuid().ToString('n'))
    New-Item -ItemType Directory -Path $history | Out-Null
    foreach ($file in 'host-stop','stop-reason.txt','worker-failure.txt','cgroup.txt','device.csv',
                       'bounded_recursion.time','bounded_recursion.log','bounded_recursion.stdout',
                       'supervisor.log','supervisor.stderr') {
        $path = Join-Path $Report $file
        if (Test-Path -LiteralPath $path -PathType Leaf) { Move-Item -LiteralPath $path -Destination $history }
    }
    [ordered]@{utc=[DateTimeOffset]::UtcNow.ToString('o');reason=$Reason;exit_code=$ExitCode} |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $history 'interruption.json')
    return $history
}
