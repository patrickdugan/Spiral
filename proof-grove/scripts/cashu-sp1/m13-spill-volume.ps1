function Invoke-CashuM13SpillLinux([string]$Action, [string]$Id) {
    $result = wsl.exe -d ProofGroveCashuRegtest -u root --cd (Get-Location).Path --exec /bin/bash `
        work/Spiral/proof-grove/scripts/cashu-sp1/m13-spill-volume.sh $Action $Id
    if ($LASTEXITCODE) { throw "The M13 spill volume failed during $Action." }
    return $result
}

function Remove-CashuM13SpillVolume($Volume) {
    $expected = "D:\ProofGroveCashuScratch\m13-spill-$($Volume.Id).vhdx"
    if ($Volume.Id -cnotmatch '^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$' -or $Volume.Image -cne $expected) {
        throw 'The disposable M13 spill image path differs.'
    }
    if ($Volume.AttachAttempted) {
        if (!$Volume.Attached) { throw 'The M13 spill disk could not be confirmed attached. Its image was retained.' }
        Invoke-CashuM13SpillLinux unmount $Volume.Id | Out-Null
        wsl.exe --unmount $Volume.Image | Out-Null
        if ($LASTEXITCODE) { throw 'The detached status of the M13 spill image could not be confirmed.' }
    }
    if (Test-Path -LiteralPath $Volume.Image) {
        $actual = Get-Item -LiteralPath $Volume.Image
        if ($actual.FullName -cne $expected -or $actual.PSIsContainer -or
                ($actual.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
                ($actual.Directory.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'The disposable M13 spill image path differs.'
        }
        $finalBytes = $actual.Length
        $freeBeforeRemoval = (Get-PSDrive D).Free
        $handle = [IO.File]::Open($actual.FullName, [IO.FileMode]::Open, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try {
            $handle.SetLength(0)
            $handle.Flush($true)
        } finally { $handle.Dispose() }
        Remove-Item -LiteralPath $actual.FullName
        [ordered]@{image_bytes_before_removal=$finalBytes;d_free_bytes_before=$freeBeforeRemoval;
            d_free_bytes=(Get-PSDrive D).Free;detached=$true} |
            ConvertTo-Json | Set-Content -LiteralPath "$($Volume.Report)/spill-volume-reclaimed.json"
    }
}

function New-CashuM13SpillVolume([string]$Report) {
    if ((Get-PSDrive D).Free -lt 32GB) { throw 'The M13 spill disk needs room above the D: reserve.' }
    $base = 'D:\ProofGroveCashuScratch'
    if (!(Test-Path -LiteralPath $base)) { New-Item -ItemType Directory -Path $base | Out-Null }
    $directory = Get-Item -LiteralPath $base
    if (!$directory.PSIsContainer -or ($directory.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'The M13 spill location must be a regular directory on D:.'
    }
    $id = [Guid]::NewGuid().ToString()
    $volume = [pscustomobject]@{Id=$id;Image=(Join-Path $base "m13-spill-$id.vhdx");Report=$Report;
        AttachAttempted=$false;Attached=$false;Mount="/var/tmp/cashu-m13-spill-$id"}
    $before = (Get-PSDrive D).Free
    try {
        Invoke-CashuM13SpillLinux prepare $id | Out-Null
        $volume.AttachAttempted = $true
        wsl.exe --mount --vhd $volume.Image --bare | Out-Null
        if ($LASTEXITCODE) { throw 'The M13 spill image could not be attached.' }
        $volume.Attached = $true
        $mount, $device, $available = (Invoke-CashuM13SpillLinux mount $id) -split ' '
        if ($mount -cne $volume.Mount -or $device -cnotmatch '^/dev/sd[a-z]+$' -or [long]$available -lt 16GB) {
            throw 'The M13 spill filesystem did not report its dedicated capacity.'
        }
        [ordered]@{image=$volume.Image;uuid=$id;mount=$mount;device=$device;linux_available_bytes=[long]$available;
            d_free_bytes_before=$before;d_free_bytes_mounted=(Get-PSDrive D).Free} |
            ConvertTo-Json | Set-Content -LiteralPath "$Report/spill-volume.json" -Encoding utf8NoBOM
        return $volume
    } catch {
        $failure = $_
        try { Remove-CashuM13SpillVolume $volume }
        catch { Write-Warning $_.Exception.Message }
        throw $failure
    }
}
