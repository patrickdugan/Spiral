function Get-CashuM14DriveReserve([string]$Path, [switch]$PreserveBackingReserve) {
    if ($PreserveBackingReserve -and [IO.Path]::GetPathRoot($Path).TrimEnd('\') -eq 'D:') { return 16GB }
    return 8GB
}

function Get-CashuM14CompressedFanoutBudget([long]$FanoutBytes) {
    # An eight-range NTFS control occupied 12.6% of its logical size after writeback.
    return [long][Math]::Ceiling($FanoutBytes / 4.0) + 32MB
}

function Select-CashuM14Scratch([string]$Primary, [string]$Alternate, [long]$PrimaryFree, [long]$AlternateFree,
                               [long]$FanoutBytes, [long]$TapeBytes, [switch]$AllowCompressedFanout,
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
    if ($AllowCompressedFanout) {
        $compressed = Select-CashuM14Scratch $Primary $Alternate $PrimaryFree $AlternateFree `
            (Get-CashuM14CompressedFanoutBudget $FanoutBytes) $TapeBytes -PreserveBackingReserve:$PreserveBackingReserve
        $compressed.compressed_fanout = $true
        return $compressed
    }
    throw 'The available scratch volumes cannot hold the measured M14 fanout, ciphertexts and labels.'
}
