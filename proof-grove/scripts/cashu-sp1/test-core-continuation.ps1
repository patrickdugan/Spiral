$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/core-continuation.ps1"

$cases = @(
    @{args=@('0', '', '', $false, $false, $true); expected='finished'},
    @{args=@('143', 'windows_reserve', 'windows_ram_reserve', $true, $false, $true); expected='host_ram'},
    @{args=@('143', 'windows_reserve', 'legacy guard', $true, $true, $true); expected='host_ram'},
    @{args=@('143', 'windows_reserve', 'workspace_disk_reserve', $true, $false, $true); expected='host_disk'},
    @{args=@('143', 'windows_reserve', 'backing_disk_reserve', $true, $false, $true); expected='host_disk'},
    @{args=@('143', 'windows_reserve', 'archive_disk_reserve', $true, $false, $true); expected='host_disk'},
    @{args=@('143', 'no_core_progress_for_300s', '', $true, $false, $true); expected='core_stall'},
    @{args=@('143', 'no_core_startup_progress_for_420s', '', $true, $false, $true); expected='core_stall'},
    @{args=@('143', 'no_core_progress_for_300s', '', $true, $false, $false); expected='inspect'},
    @{args=@('143', 'no_core_progress_for_300s', 'unknown host stop', $true, $false, $true); expected='inspect'},
    @{args=@('143', 'no_core_archive_write_progress_for_300s', '', $true, $false, $true); expected='inspect'},
    @{args=@('143', 'no_core_progress_for_300s', '', $false, $false, $true); expected='inspect'},
    @{args=@('137', 'no_core_progress_for_300s', '', $false, $false, $true); expected='inspect'},
    @{args=@('143', 'worker_panic', '', $true, $false, $true); expected='inspect'}
)
foreach ($case in $cases) {
    $arguments = $case.args
    $actual = Get-CashuCoreContinuation @arguments
    if ($actual -cne $case.expected) { throw "Expected $($case.expected), observed $actual for $arguments" }
}
"$($cases.Count) continuation controls passed"
