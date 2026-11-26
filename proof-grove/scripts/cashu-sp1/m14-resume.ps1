function Read-CashuM14Storage($Path, [string[]]$Roots, [string]$SetupName, [long]$FanoutBytes, [long]$TapeBytes) {
    $stored = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -AsHashtable
    $compressed = $stored.fanout_compressed
    if ($compressed -isnot [bool] -or $stored.fanout_bytes -ne $FanoutBytes -or $stored.tape_and_labels_bytes -ne $TapeBytes) {
        throw 'Saved M14 scratch placement differs from the measured circuit.'
    }
    $fanoutName = if ($compressed) { "$SetupName-compressed-fanout" } else { $SetupName }
    $fanoutOptions = @($Roots | ForEach-Object { Join-Path $_ $fanoutName })
    $tapeOptions = @($Roots | ForEach-Object { Join-Path $_ $SetupName })
    if ($stored.fanout_directory -notin $fanoutOptions -or $stored.tape_directory -notin $tapeOptions -or
            !(Test-Path -LiteralPath $stored.fanout_directory -PathType Container) -or
            !(Test-Path -LiteralPath $stored.tape_directory -PathType Container)) {
        throw 'Saved M14 scratch directories are unavailable for this settlement.'
    }
    $budget = if ($compressed) { Get-CashuM14CompressedFanoutBudget $FanoutBytes } else { $FanoutBytes }
    if ($stored.fanout_physical_budget_bytes -ne $budget) {
        throw 'Saved M14 fanout budget differs from the measured circuit.'
    }
    return $stored
}

function Test-CashuM14CompletedRun([string]$Report, [ValidateSet('export-staged','evaluate-staged')][string]$Phase) {
    $base = Join-Path $Report $Phase
    $resources = "$base-resources.json"
    $native = "$base.json"
    if (!(Test-Path -LiteralPath $resources -PathType Leaf)) {
        if (@($native,"$base-checked.json","$base.stdout.log","$base.stderr.log").Where({Test-Path -LiteralPath $_}).Count) {
            throw "The saved M14 $Phase attempt stopped before recording a successful native run."
        }
        return $false
    }
    $state = Get-Content -LiteralPath $resources -Raw | ConvertFrom-Json -AsHashtable
    if ($state.phase -cne $Phase -or $state.exit_code -isnot [long] -or $state.exit_code -ne 0 -or $state.stop_reason -or
            !(Test-Path -LiteralPath $native -PathType Leaf)) {
        throw "The saved M14 $Phase attempt did not finish successfully."
    }
    return $true
}
