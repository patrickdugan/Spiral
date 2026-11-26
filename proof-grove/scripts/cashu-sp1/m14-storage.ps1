$CashuM14BtrfsReserve = 2GB

function Get-CashuM14DriveReserve([string]$Path, [switch]$PreserveBackingReserve) {
    if ($PreserveBackingReserve -and [IO.Path]::GetPathRoot($Path).TrimEnd('\') -eq 'D:') { return 16GB }
    return 8GB
}

function Get-CashuM14CompressedFanoutBudget([long]$FanoutBytes) {
    # Physical allocation budget retained for an existing NTFS-compressed plan.
    return [long][Math]::Ceiling($FanoutBytes / 4.0) + 32MB
}

function Get-CashuM14BtrfsRoot {
    return '\\wsl.localhost\ProofGroveCashuRegtest\var\tmp\proof-grove-cashu-raw-store'
}

function Get-CashuM14BtrfsFanoutBudget([long]$FanoutBytes) {
    # The inherited zstd filesystem used 3.14% of the exact fanout sample.
    return [long][Math]::Ceiling($FanoutBytes / 8.0) + 32MB
}

function Get-CashuM14BtrfsFree {
    $info = wsl.exe -d ProofGroveCashuRegtest -u root --exec /bin/bash work/Spiral/proof-grove/scripts/cashu-sp1/m14-btrfs-free.sh
    if ($LASTEXITCODE -or $info -is [array] -or $info -cnotmatch '^[0-9a-f]+:[0-9]+:[0-9]+$') {
        throw 'The M14 fanout cannot measure the Btrfs checkpoint volume.'
    }
    $fsid, $available, $blockSize = $info -split ':'
    if ($fsid -cne (Get-Content -LiteralPath 'outputs/cashu-raw-storage-volume/fsid.txt' -Raw).Trim()) {
        throw 'The M14 fanout filesystem differs from the pinned checkpoint volume.'
    }
    return [long]$available * [long]$blockSize
}

function Select-CashuM14Scratch([string]$Primary, [string]$Alternate, [long]$PrimaryFree, [long]$AlternateFree,
                               [long]$FanoutBytes, [long]$TapeBytes, [long]$BtrfsFree = 0,
                               [long]$BtrfsBackingFree = 0,
                               [switch]$PreserveBackingReserve) {
    $primaryReserve = Get-CashuM14DriveReserve $Primary -PreserveBackingReserve:$PreserveBackingReserve
    $alternateReserve = if ($Alternate) { Get-CashuM14DriveReserve $Alternate -PreserveBackingReserve:$PreserveBackingReserve }
    if ($PrimaryFree -ge ($FanoutBytes + $TapeBytes + $primaryReserve)) {
        return @{fanout=$Primary; tape=$Primary}
    }
    if ($Alternate -and $PrimaryFree -ge ($FanoutBytes + $primaryReserve) -and $AlternateFree -ge ($TapeBytes + $alternateReserve)) {
        return @{fanout=$Primary; tape=$Alternate}
    }
    if ($Alternate -and $AlternateFree -ge ($FanoutBytes + $alternateReserve) -and $PrimaryFree -ge ($TapeBytes + $primaryReserve)) {
        return @{fanout=$Alternate; tape=$Primary}
    }
    if ($Alternate -and $AlternateFree -ge ($FanoutBytes + $TapeBytes + $alternateReserve)) {
        return @{fanout=$Alternate; tape=$Alternate}
    }
    $btrfsBudget = Get-CashuM14BtrfsFanoutBudget $FanoutBytes
    if ($BtrfsFree -ge ($btrfsBudget + $CashuM14BtrfsReserve) -and $BtrfsBackingFree -ge ($btrfsBudget + 8GB)) {
        $choices = @{path=$Primary;free=$PrimaryFree;reserve=$primaryReserve},
                   @{path=$Alternate;free=$AlternateFree;reserve=$alternateReserve}
        foreach ($choice in $choices) {
            if (!$choice.path) { continue }
            $onBacking = [IO.Path]::GetPathRoot($choice.path).TrimEnd('\') -eq 'E:'
            $room = if ($onBacking) { [math]::Min($choice.free, $BtrfsBackingFree) - $btrfsBudget } else { $choice.free }
            if ($room -ge ($TapeBytes + $choice.reserve)) {
                return @{fanout=(Get-CashuM14BtrfsRoot);tape=$choice.path;btrfs_fanout=$true}
            }
        }
    }
    throw 'The available scratch volumes cannot hold the measured M14 fanout, ciphertexts and labels.'
}
