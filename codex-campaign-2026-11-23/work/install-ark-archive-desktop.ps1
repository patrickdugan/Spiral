$ErrorActionPreference = 'Stop'
$checkout = 'C:/Users/patri/OneDrive/Documents/GitHub/rbzk-prover-ui/prover-ui'
$builder = Join-Path $PSScriptRoot 'live-ui-native/release/rbzk-prover-desktop.exe'
$installed = Join-Path $checkout 'target/release/rbzk-prover-desktop-live.exe'
$switch = Join-Path $checkout 'target/release/rbzk-prover-desktop-archive.exe'
$oldService = Get-NetTCPConnection -State Listen -LocalAddress '127.0.0.1' -LocalPort 8788 |
    Select-Object -First 1
$old = Get-Process -Id $oldService.OwningProcess
$previous = Join-Path $checkout 'target/release/rbzk-prover-desktop-nova.exe'
if ($old.Id -ne 38324 -or $old.Path -ne $previous.Replace('/', '\')) {
    throw 'The existing desktop process does not use the expected installed executable.'
}
if (Test-Path -LiteralPath $switch) {
    throw 'The intended side-by-side executable already exists.'
}
Copy-Item -LiteralPath $builder -Destination $switch
$hash = (Get-FileHash -LiteralPath $builder -Algorithm SHA256).Hash
if ((Get-FileHash -LiteralPath $switch -Algorithm SHA256).Hash -ne $hash) {
    throw 'The side-by-side desktop binary does not match the verified build.'
}
& (Join-Path $checkout 'scripts/launch-live-desktop.ps1') -ExePath $switch

$deadline = (Get-Date).AddSeconds(45)
do {
    $new = Get-Process -Name 'rbzk-prover-desktop-archive' -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $switch.Replace('/', '\') } | Select-Object -First 1
    if ($new -and $new.MainWindowHandle -ne 0) {
        $listener = Get-NetTCPConnection -State Listen -LocalAddress '127.0.0.1' -OwningProcess $new.Id |
            Select-Object -First 1
        if ($listener) {
            $base = 'http://127.0.0.1:' + $listener.LocalPort
            try {
                $ark = (Invoke-RestMethod -Uri "$base/api/live" -TimeoutSec 3).cloud_hyperstack_ark
                $html = (Invoke-WebRequest -Uri $base -TimeoutSec 3).Content
                if ($ark.vm_id -eq 1178271 -and $ark.private_storage.bucket_bytes -gt 0 -and
                    $html.Contains('overview-proof-release') -and $html.Contains('overview-storage')) {
                    $sample = $ark
                    break
                }
            } catch {
                # The old desktop remains open until the new one serves the current campaign.
            }
        }
    }
    Start-Sleep -Milliseconds 350
} while ((Get-Date) -lt $deadline)
if (-not $sample) {
    throw 'The replacement did not present the active campaign and private storage observation.'
}

$closed = $old.CloseMainWindow()
if ($closed) { $old.WaitForExit(12000) | Out-Null }
if ($old.HasExited) {
    Copy-Item -LiteralPath $builder -Destination $installed -Force
    if ((Get-FileHash -LiteralPath $installed -Algorithm SHA256).Hash -ne $hash) {
        throw 'The installed desktop binary differs from the verified build.'
    }
}
[pscustomobject]@{
    pid = $new.Id
    url = $base
    previous_closed = $old.HasExited
    vm_id = $sample.vm_id
    bucket_bytes = $sample.private_storage.bucket_bytes
    objects = $sample.private_storage.objects
} | ConvertTo-Json -Compress
