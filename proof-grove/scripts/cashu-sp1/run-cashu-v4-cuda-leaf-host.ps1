param([switch]$Archive, [switch]$M13Shrink, [switch]$M13Wrap, [switch]$RawWithdrawal, [ValidateRange(1,999)][int]$Attempt = 1,
      [ValidatePattern('^sustained-([5-9]|[1-9][0-9]+)$')][string]$CoreAttempt = 'sustained-10')

$ErrorActionPreference = 'Stop'
if (@($Archive, $M13Shrink, $M13Wrap).Where({ $_ }).Count -gt 1) { throw 'Choose one Cashu proving stage.' }
. 'work/cashu-v4-settlement-profile.ps1'
$settlement = Get-CashuSettlementProfile $Attempt -RawWithdrawal:$RawWithdrawal
$cashuRoot = (Get-Location).Path
$firstLeaf = 'outputs/cashu-v4-first-cuda-recursion-leaf'
$coreReport = 'outputs/cashu-v4-rtx3050-independent-core'
if ($RawWithdrawal) {
    $firstLeaf = 'outputs/cashu-v4-raw-first-cuda-recursion-leaf'
    $profile = Get-Content -LiteralPath work/cashu-v4-raw-profile.json -Raw | ConvertFrom-Json
    $coreReport = $profile.independent_core
}
$builds = if ($M13Wrap) {
    @('outputs/cashu-m13-spill-build')
} elseif ($M13Shrink) {
    @('outputs/cashu-m13-pinned-build')
} elseif ($Archive) {
    @('outputs/cashu-core-cuda-normalizer-linked-batch', 'outputs/cashu-core-cuda-normalizer-linked-compose')
} else {
    @('outputs/cashu-core-cuda-normalizer-linked-keyed')
}
foreach ($build in $builds) {
    if (!(Test-Path -LiteralPath (Join-Path $build 'binary-sha256.txt'))) {
        throw "The prover executable in $build is still building."
    }
}
$archiveName = $settlement.archive_report
$shrinkName = $settlement.shrink_report
$verified = if ($M13Wrap) {
    Join-Path $cashuRoot "$shrinkName/worker-exit.txt"
} elseif ($M13Shrink) {
    Join-Path $cashuRoot "$archiveName/m13-handoff.json"
} elseif ($Archive) {
    Join-Path $cashuRoot "$firstLeaf/independent/result.json"
} else {
    Join-Path $cashuRoot "$coreReport/verified.json"
}
$handoff = Join-Path $cashuRoot "outputs/cashu-v3-rtx3050-$CoreAttempt/v4-core-handoff.log"
$cutoff = [DateTimeOffset]::UtcNow.AddHours(12)
if ($M13Wrap) { 'Waiting for the verified M13 shrink of the exact Cashu withdrawal.' }
elseif ($M13Shrink) { 'Waiting for the stock SP1 seal matched to the pinned M13 statement.' }
elseif ($Archive) { 'Waiting for the first independently verified CUDA Cashu leaf.' }
else { 'Waiting for independent verification of the exact Cashu Core archive.' }
while (!(Test-Path -LiteralPath $verified -PathType Leaf) -or (Get-Item -LiteralPath $verified).Length -eq 0) {
    if ([DateTimeOffset]::UtcNow -gt $cutoff) { throw 'Cashu verification handoff wait expired.' }
    if ((Test-Path -LiteralPath $handoff) -and
        (Select-String -LiteralPath $handoff -Quiet -SimpleMatch 'worker stopped before assembling a Core archive')) {
        throw 'The Core worker stopped before assembling its archive. The checkpoint remains available for resume.'
    }
    if ($Archive -and (Test-Path "$firstLeaf/worker-exit.txt") -and
        ((Get-Content "$firstLeaf/worker-exit.txt" -Raw) -match '^\s*[1-9][0-9]*\s*$')) {
        throw 'The first CUDA leaf worker stopped before verification.'
    }
    if ($M13Shrink -and (Test-Path -LiteralPath "$archiveName/worker-failure.txt")) {
        throw 'CUDA archive proving stopped before the M13 handoff.'
    }
    Start-Sleep -Seconds 15
}
if ($M13Wrap -and ((Get-Content -LiteralPath $verified -Raw).Trim() -ne '0' -or
        !(Test-Path -LiteralPath "$shrinkName/proof/result.json"))) {
    throw 'The bounded M13 shrink stopped before publishing a verified proof.'
}

$definition = Get-Content work/rtx3050-guarded-host.ps1 -Raw
Add-Type -TypeDefinition ([regex]::Match($definition, '(?sm)using System;.*?^\}').Value)
$floor = 1GB
$cap = if ($M13Wrap) { 5GB } else { 3GB }
$admissionDeadline = [DateTimeOffset]::UtcNow.AddMinutes(5)
while ([ProofGroveHostMemory]::AvailableBytes() -lt $floor -and
        [DateTimeOffset]::UtcNow -lt $admissionDeadline) {
    Start-Sleep -Seconds 5
}
if ([ProofGroveHostMemory]::AvailableBytes() -lt $floor) {
    throw 'Available Windows RAM is below the 1 GiB host reserve.'
}
$usesBackingDrive = $Archive -or $M13Shrink -or $M13Wrap
if ($usesBackingDrive -and ((Get-PSDrive C).Free -lt 8GB -or (Get-PSDrive D).Free -lt 16GB)) {
    throw 'Free space is below the 8 GiB workspace or 16 GiB WSL backing reserve.'
}
if ($M13Wrap) {
    if ((Get-PSDrive D).Free -lt 32GB) { throw 'The M13 wrap needs 32 GiB free on the backing drive at admission.' }
    $name = $settlement.wrap_report
    $workerScript = 'work/run-cashu-v4-m13-stage.sh'
    $linuxMode = @('wrap-v4-m13', "$Attempt")
} elseif ($M13Shrink) {
    $name = $shrinkName
    $workerScript = 'work/run-cashu-v4-m13-shrink.sh'
    $linuxMode = @('shrink-v4-m13', "$Attempt")
} elseif ($Archive) {
    $name = $archiveName
    $workerScript = Join-Path $PSScriptRoot 'run-cashu-v4-cuda-archive.sh'
    $linuxMode = @('normalize-compose-v4-cuda', "$Attempt")
} else {
    $name = $firstLeaf
    $workerScript = 'work/run-cashu-v4-cuda-leaf.sh'
    $linuxMode = @('normalize-v4-cuda-leaf')
}
if ($RawWithdrawal) { $linuxMode += 'withdrawal-v4-raw' }
$report = Join-Path $cashuRoot $name
New-Item -ItemType Directory -Path $report | Out-Null
$launch = New-Item -ItemType Directory -Path (Join-Path $report 'launch')
Copy-Item -LiteralPath work/run-cashu-capped-wsl.sh,$workerScript -Destination $launch.FullName
$memoryLog = Join-Path $report 'windows-available.csv'
$stop = Join-Path $report 'host-stop'
$nativeBackingD = $null
if ($Archive -and $RawWithdrawal) {
    $registry = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss'
    $nativeBackingD = Get-ChildItem -LiteralPath $registry -ErrorAction SilentlyContinue |
        ForEach-Object { Get-ItemProperty -LiteralPath $_.PSPath } |
        Where-Object { $_.DistributionName -eq 'ProofGroveCashuRegtest' -and $_.BasePath -eq 'D:\ProofGroveCashuRegtest\disk' }
}
'utc,bytes,d_free_bytes,e_free_bytes' | Set-Content -LiteralPath $memoryLog
[ordered]@{windows_reserve_bytes=$floor;worker_cap_bytes=$cap} |
    ConvertTo-Json | Set-Content -Encoding utf8 -LiteralPath (Join-Path $report 'host-memory-policy.json')
function Record-CashuAvailableMemory {
    $available = [ProofGroveHostMemory]::AvailableBytes()
    $backingFree = if ($nativeBackingD -or $M13Wrap) { (Get-PSDrive D).Free } else { 0 }
    $archiveFree = if ($Archive -and $RawWithdrawal) { [long](Get-PSDrive E -ErrorAction SilentlyContinue).Free } else { 0 }
    "$([DateTimeOffset]::UtcNow.ToString('o')),$available,$backingFree,$archiveFree" | Add-Content -LiteralPath $memoryLog
    return $available
}
$linuxRoot = '/mnt/c' + $cashuRoot.Substring(2).Replace('\', '/')
$launchArgs = @(
    '-d','ProofGroveCashuRegtest','--user','root','--cd',"`"$linuxRoot`"",'--exec','/bin/bash',
    "$name/launch/run-cashu-capped-wsl.sh"
) + $linuxMode
$spill = $null
$worker = $null
try {
    if ($M13Wrap -and $RawWithdrawal) {
        . "$PSScriptRoot/m13-spill-volume.ps1"
        $spill = New-CashuM13SpillVolume $report
    }
    [void](Record-CashuAvailableMemory)
    $worker = Start-Process -FilePath wsl.exe -ArgumentList $launchArgs -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $report 'supervisor.log') `
        -RedirectStandardError (Join-Path $report 'supervisor.stderr')
    while (!$worker.HasExited) {
        if ((Record-CashuAvailableMemory) -lt $floor) {
            'Windows memory fell below the 1 GiB reserve.' | Set-Content -LiteralPath $stop
            break
        }
        if ($usesBackingDrive -and ((Get-PSDrive C).Free -lt 8GB -or (Get-PSDrive D).Free -lt 16GB)) {
            'Free space fell below a drive reserve.' | Set-Content -LiteralPath $stop
            break
        }
        Start-Sleep -Seconds 2
    }
} finally {
    if ($worker -and !$worker.HasExited) {
        if (!(Test-Path -LiteralPath $stop)) { 'The Windows proving worker guard ended.' | Set-Content -LiteralPath $stop }
        if (!$worker.WaitForExit(25000)) { throw 'The bounded proving worker has yet to acknowledge the host stop.' }
    }
    if ($spill) { Remove-CashuM13SpillVolume $spill }
}
Get-Content -LiteralPath (Join-Path $report 'supervisor.log') -Tail 18
Get-Content -LiteralPath (Join-Path $report 'supervisor.stderr') -Tail 10
if ($worker.ExitCode -ne 0) { exit $worker.ExitCode }
if ($M13Wrap) {
    $statementPin = $settlement.assets.statement_sha256
    $result = Get-Content -LiteralPath "$report/proof/result.json" -Raw | ConvertFrom-Json
    if ($result.status -ne 'pinned_wrap_v2_verified' -or $result.statement_sha256 -cne $statementPin -or
            $result.wrap_sha256 -cnotmatch '^[0-9a-f]{64}$') {
        throw 'The wrap worker did not publish a receipt for the pinned withdrawal statement.'
    }
    $nativeTarget = 'work/cashu-m13-native-target/release'
    $reference = 'work/m14-full-seed-check/tree/m13/fixtures/c4-wrap-blake3-v2.bin'
    if ((Get-FileHash -LiteralPath $reference -Algorithm SHA256).Hash -ne 'b37cb7a694be0f85bac7fb882c3dc69aee490a7d1bc91b434770b4939de68564') {
        throw 'The M14 reference wrap differs from its pin.'
    }
    & 'C:/Python312/python.exe' -B work/zk-rusto-no-bitcoino/integrations/bitvm3-nova/m14/assertion-smoke/stage_wrap_input.py `
        --wrap "$report/proof/wrap-v2.bin" --wrap-sha256 $result.wrap_sha256 `
        --statement $settlement.assets.statement --statement-sha256 $statementPin `
        --m13-verifier "$nativeTarget/m13-verify.exe" --m13-verifier-sha256 f01531736e8d248f6a555179f177dd2b31e5c3cc23fef63c558aa107316492d2 `
        --m14-claim "$nativeTarget/m14-claim-full-seed.exe" --m14-claim-sha256 ed2becd7ad8359891fddab96aa45656fef291b7bfb5a25c632ec9cbfead96cf2 `
        --out "$report/verified-wrap-input"
    exit $LASTEXITCODE
}
if ($Archive -or $M13Shrink) { exit 0 }
$leafMode = if ($RawWithdrawal) { 'cuda-raw' } else { 'cuda' }
wsl.exe -d ProofGroveCashuRegtest -u root --cd $linuxRoot -- /bin/bash work/run-cashu-capped-wsl.sh verify-v4-normalized-leaf $leafMode
exit $LASTEXITCODE
