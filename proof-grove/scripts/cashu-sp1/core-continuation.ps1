function Get-CashuCoreContinuation([string]$ExitCode, [string]$Reason, [string]$HostStop,
                                    [bool]$NoOomKills, [bool]$LegacyRamStop,
                                    [bool]$StallRetryAvailable) {
    if ($ExitCode -ceq '0') { return 'finished' }
    if ($ExitCode -cne '143' -or !$NoOomKills) { return 'inspect' }

    if ($Reason -ceq 'windows_reserve') {
        if ($LegacyRamStop -or $HostStop -ceq 'windows_ram_reserve') { return 'host_ram' }
        if ($HostStop -cin 'workspace_disk_reserve', 'backing_disk_reserve', 'archive_disk_reserve') {
            return 'host_disk'
        }
    }
    if (!$HostStop -and $StallRetryAvailable -and
            $Reason -cin 'no_core_progress_for_300s', 'no_core_startup_progress_for_420s') {
        return 'core_stall'
    }
    return 'inspect'
}
