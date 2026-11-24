$ErrorActionPreference = 'Stop'

$proverUi = 'C:/Users/patri/OneDrive/Documents/GitHub/rbzk-prover-ui/prover-ui'
$oldExe = Join-Path $proverUi 'target/release/rbzk-prover-desktop-overnight.exe'
$liveExe = Join-Path $proverUi 'target/release/rbzk-prover-desktop-live.exe'
$old = Get-Process -Id 8548 -ErrorAction SilentlyContinue
if (-not $old -or $old.Path -ne $oldExe.Replace('/', '\')) {
    throw 'The previous desktop process does not match the expected live UI.'
}
& (Join-Path $proverUi 'scripts/launch-live-desktop.ps1') -ExePath $liveExe

$deadline = (Get-Date).AddSeconds(35)
$sample = $null
do {
    $replacement = Get-Process -Name 'rbzk-prover-desktop-live' -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $liveExe.Replace('/', '\') } | Select-Object -First 1
    if ($replacement -and $replacement.MainWindowHandle -ne 0) {
        $server = Get-NetTCPConnection -OwningProcess $replacement.Id -State Listen -ErrorAction SilentlyContinue |
            Where-Object LocalAddress -EQ '127.0.0.1' | Select-Object -First 1
        if ($server) {
            try {
                $base = 'http://127.0.0.1:' + $server.LocalPort
                $candidate = (Invoke-RestMethod -Uri "$base/api/live" -TimeoutSec 2).cloud_hyperstack_ark
                $frontend = (Invoke-WebRequest -Uri "$base/app.js" -TimeoutSec 2).Content
                if ($candidate.vm_id -eq 1178271 -and $candidate.spot -eq $true -and $frontend.Contains("arkSpot===true?'A100 spot VM'")) {
                    $sample = $candidate
                    break
                }
            } catch { }
        }
    }
    Start-Sleep -Milliseconds 400
} while ((Get-Date) -lt $deadline)
if (-not $sample) { throw 'The replacement window did not confirm the Spot lease. The previous window remains open.' }

if ($old.CloseMainWindow()) { $old.WaitForExit(12000) | Out-Null }
[pscustomobject]@{
    process_id = $replacement.Id
    previous_window_closed = $old.HasExited
    vm_id = $sample.vm_id
    spot = $sample.spot
    stage = $sample.stage
    core_new = $sample.core_new
    recursion_new = $sample.recursion_new
    core_replayed = $sample.core_replayed
} | ConvertTo-Json -Compress
