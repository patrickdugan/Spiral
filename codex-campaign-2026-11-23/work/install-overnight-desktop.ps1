$ErrorActionPreference = 'Stop'

$checkout = 'C:/Users/patri/OneDrive/Documents/GitHub/rbzk-prover-ui/prover-ui'
$builder = Join-Path $PSScriptRoot 'live-ui-native/release/rbzk-prover-desktop.exe'
$liveDirectory = Join-Path $checkout 'target/release'
$installed = Join-Path $liveDirectory 'rbzk-prover-desktop-live.exe'
$replacement = Join-Path $liveDirectory 'rbzk-prover-desktop-overnight.exe'
$old = Get-Process -Id 40136 -ErrorAction SilentlyContinue
if (-not $old -or $old.Path -ne $installed.Replace('/', '\')) {
    throw 'The original UI process no longer matches the expected live executable.'
}

Copy-Item -LiteralPath $builder -Destination $replacement
if ((Get-FileHash -LiteralPath $builder).Hash -ne (Get-FileHash -LiteralPath $replacement).Hash) {
    throw 'The copied desktop executable failed its SHA-256 comparison.'
}
& (Join-Path $checkout 'scripts/launch-live-desktop.ps1') -ExePath $replacement

$deadline = (Get-Date).AddSeconds(35)
$valid = $null
do {
    $new = Get-Process -Name 'rbzk-prover-desktop-overnight' -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $replacement.Replace('/', '\') } | Select-Object -First 1
    if ($new -and $new.MainWindowHandle -ne 0) {
        $server = Get-NetTCPConnection -OwningProcess $new.Id -State Listen -ErrorAction SilentlyContinue |
            Where-Object LocalAddress -EQ '127.0.0.1' | Select-Object -First 1
        if ($server) {
            try {
                $snapshot = Invoke-RestMethod -TimeoutSec 2 -Uri ('http://127.0.0.1:' + $server.LocalPort + '/api/live')
                if ($snapshot.cloud_hyperstack_ark -and $null -ne $snapshot.frame_seq) {
                    $valid = $snapshot.cloud_hyperstack_ark
                    break
                }
            } catch {
                # Leave the previous app open until the replacement's loopback data is valid.
            }
        }
    }
    Start-Sleep -Milliseconds 400
} while ((Get-Date) -lt $deadline)
if (-not $valid) { throw 'The replacement did not present a live campaign snapshot. The previous window remains open.' }

$priorClosed = $old.CloseMainWindow()
if ($priorClosed) {
    try { $old.WaitForExit(12000) | Out-Null } catch { }
}
$priorClosed = $old.HasExited
if ($priorClosed) { Copy-Item -LiteralPath $builder -Destination $installed }
[pscustomobject]@{
    process_id = $new.Id
    previous_window_closed = $priorClosed
    ark_stage = $valid.stage
    seed_parts = $valid.seed_parts
    vm_id = $valid.vm_id
} | ConvertTo-Json -Compress
