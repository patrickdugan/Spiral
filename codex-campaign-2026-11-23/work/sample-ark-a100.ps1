param([int]$Seconds = 330)
$ErrorActionPreference = 'Stop'

$statePath = Join-Path $PSScriptRoot 'hyperstack-ark-state.json'
$output = Join-Path $PSScriptRoot 'ark-a100-overnight-samples.jsonl'
$clock = [Diagnostics.Stopwatch]::StartNew()
$last = 0L
while ($clock.Elapsed.TotalSeconds -le $Seconds) {
    try {
        $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    } catch {
        Start-Sleep -Seconds 3
        continue
    }
    if ($state.vm_id -ne 1178271 -or $state.spot -ne $true -or $state.cleanup) { break }
    $fields = $state.stage.Split('|')
    if ($fields.Count -eq 11 -and $fields[0] -eq 'ark_heartbeat' -and $fields[9] -eq '1') {
        $timestamp = [long]$fields[1]
        $age = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - $timestamp
        if ($timestamp -gt $last -and $age -ge -2 -and $age -le 30) {
            $sample = [pscustomobject]@{
                vm_id = $state.vm_id
                timestamp_unix = $timestamp
                phase = $fields[2]
                core_fresh = [int]$fields[4]
                recursion_fresh = [int]$fields[5]
                core_replayed = [int]$fields[6]
                recursion_replayed = [int]$fields[7]
                vram_mib = [int]$fields[8]
            } | ConvertTo-Json -Compress
            Add-Content -LiteralPath $output -Value $sample -Encoding utf8
            $last = $timestamp
        }
    }
    Start-Sleep -Seconds 15
}
Get-Content -LiteralPath $output -Tail 1
