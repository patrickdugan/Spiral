$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/m14-storage.ps1"
. "$PSScriptRoot/m14-resume.ps1"

function Assert-Refused([scriptblock]$Operation, [string]$Message) {
    try { & $Operation | Out-Null }
    catch { if ($_.Exception.Message -like $Message) { return }; throw }
    throw "Expected refusal matching $Message"
}

$fixture = Join-Path ([IO.Path]::GetTempPath()) ('cashu-m14-resume-' + [Guid]::NewGuid().ToString('n'))
New-Item -ItemType Directory -Path $fixture | Out-Null
try {
    $primary = Join-Path $fixture 'volume-a'
    $alternate = Join-Path $fixture 'volume-b'
    $name = 'cashu-v4-raw-m14-1'
    $fanout = Join-Path $primary "$name-compressed-fanout"
    $tape = Join-Path $alternate $name
    New-Item -ItemType Directory -Path $fanout,$tape -Force | Out-Null
    $storagePath = Join-Path $fixture 'setup-storage.json'
    $storage = @{fanout_directory=$fanout;tape_directory=$tape;fanout_bytes=1024L;
        fanout_compressed=$true;fanout_physical_budget_bytes=(Get-CashuM14CompressedFanoutBudget 1024L);tape_and_labels_bytes=80L}
    $storage | ConvertTo-Json | Set-Content -LiteralPath $storagePath
    $stored = Read-CashuM14Storage $storagePath @($primary,$alternate) $name 1024L 80L
    if ($stored.fanout_directory -cne $fanout -or $stored.tape_directory -cne $tape) { throw 'Placement changed on retry.' }
    Assert-Refused { Read-CashuM14Storage $storagePath @($primary,$alternate) $name 1040L 80L } '*measured circuit*'
    Assert-Refused { Read-CashuM14Storage $storagePath @($primary) $name 1024L 80L } '*scratch directories are unavailable*'
    $storage.fanout_physical_budget_bytes++
    $storage | ConvertTo-Json | Set-Content -LiteralPath $storagePath
    Assert-Refused { Read-CashuM14Storage $storagePath @($primary,$alternate) $name 1024L 80L } '*fanout budget*'

    if (Test-CashuM14CompletedRun $fixture 'export-staged') { throw 'A fresh phase was counted as complete.' }
    Set-Content -LiteralPath "$fixture/export-staged.stdout.log" -Value 'start'
    Assert-Refused { Test-CashuM14CompletedRun $fixture 'export-staged' } '*stopped before recording*'
    Set-Content -LiteralPath "$fixture/export-staged-resources.json" -Value '{"phase":"export-staged","exit_code":124}'
    Assert-Refused { Test-CashuM14CompletedRun $fixture 'export-staged' } '*did not finish successfully*'
    Set-Content -LiteralPath "$fixture/export-staged-resources.json" -Value '{"phase":"export-staged","exit_code":0}'
    Assert-Refused { Test-CashuM14CompletedRun $fixture 'export-staged' } '*did not finish successfully*'
    Set-Content -LiteralPath "$fixture/export-staged.json" -Value '{}'
    if (!(Test-CashuM14CompletedRun $fixture 'export-staged')) { throw 'A successful native export could not be rechecked.' }
    if (Test-CashuM14CompletedRun $fixture 'evaluate-staged') { throw 'The evaluation borrowed the export evidence.' }
    'Ten M14 restart controls passed.'
} finally {
    $resolved = (Resolve-Path -LiteralPath $fixture).Path
    if ($resolved -cne [IO.Path]::GetFullPath($fixture)) { throw 'Unexpected fixture path.' }
    Remove-Item -LiteralPath $resolved -Force -Recurse
}
