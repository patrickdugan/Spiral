$ErrorActionPreference = 'Stop'

$checkout = 'C:/Users/patri/OneDrive/Documents/GitHub/rbzk-prover-ui/prover-ui'
$builder = Join-Path $PSScriptRoot 'live-ui-native/release/rbzk-prover-desktop.exe'
$existing = 'C:\Users\patri\OneDrive\Documents\GitHub\rbzk-prover-ui\prover-ui\target\release\rbzk-prover-desktop-budget.exe'
$replacement = Join-Path $checkout 'target/release/rbzk-prover-desktop-nova.exe'
$installed = Join-Path $checkout 'target/release/rbzk-prover-desktop-live.exe'
$old = Get-Process -Id 6836 -ErrorAction Stop
if ($old.Path -ne $existing) { throw 'The current desktop process identity changed.' }
if (Test-Path -LiteralPath $replacement) { throw 'The destination desktop binary already exists.' }

Copy-Item -LiteralPath $builder -Destination $replacement
if ((Get-FileHash -LiteralPath $builder).Hash -ne (Get-FileHash -LiteralPath $replacement).Hash) {
    throw 'The copied desktop executable failed its SHA-256 comparison.'
}
& (Join-Path $checkout 'scripts/launch-live-desktop.ps1') -ExePath $replacement

$deadline = (Get-Date).AddSeconds(35)
do {
    $new = Get-Process -Name 'rbzk-prover-desktop-nova' -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $replacement.Replace('/', '\') } | Select-Object -First 1
    if ($new -and $new.MainWindowHandle -ne 0) {
        $server = Get-NetTCPConnection -OwningProcess $new.Id -State Listen -ErrorAction SilentlyContinue |
            Where-Object LocalAddress -EQ '127.0.0.1' | Select-Object -First 1
        if ($server) {
            $address = 'http://127.0.0.1:' + $server.LocalPort
            try {
                $snapshot = Invoke-RestMethod -Uri "$address/api/live" -TimeoutSec 2
                if ($snapshot.runtime.fresh -and $snapshot.cloud_hyperstack_ark.vm_id -eq 1178271) {
                    $closed = $old.CloseMainWindow()
                    if ($closed) { $old.WaitForExit(12000) | Out-Null }
                    Copy-Item -LiteralPath $builder -Destination $installed
                    [pscustomobject]@{ pid = $new.Id; url = $address; previous_closed = $old.HasExited } |
                        ConvertTo-Json -Compress
                    exit 0
                }
            } catch {
                # The previous desktop remains visible while the replacement warms up.
            }
        }
    }
    Start-Sleep -Milliseconds 350
} while ((Get-Date) -lt $deadline)
throw 'The replacement did not present the active Ark campaign and a fresh WSL sample.'
