$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/archive-resume.ps1"

$report = Join-Path ([IO.Path]::GetTempPath()) ('cashu-archive-resume-' + [Guid]::NewGuid().ToString('n'))
New-Item -ItemType Directory -Path $report | Out-Null
function Write-Fixture([string]$Stage = 'bounded_recursion', [string]$Reason = 'host_reserve_or_heartbeat',
                       [int]$Oom = 0, [int]$Killed = 0, [long]$Swap = 0) {
    Set-Content -LiteralPath "$report/stage.txt" $Stage
    Set-Content -LiteralPath "$report/stop-reason.txt" $Reason
    Set-Content -LiteralPath "$report/cgroup.txt" @('729808896', 'low 0', 'high 0', 'max 0', "oom $Oom", "oom_kill $Killed", "$Swap")
    Set-Content -LiteralPath "$report/recursion-placement.json" '{"schema":"proof-grove/cashu-recursion-storage/v1"}'
}
function Expect([string]$Name,[int]$Code,[string]$Reason) {
    $actual = Get-CashuArchiveInterruption $report $Code
    if (($Reason -and $actual -cne $Reason) -or (!$Reason -and $null -ne $actual)) { throw "Unexpected result for $Name." }
    "$Name passed"
}

try {
    Write-Fixture
    Expect 'acknowledged RAM/heartbeat stop' 143 'host_reserve_or_heartbeat'
    Write-Fixture -Reason scratch_disk_reserve
    Expect 'acknowledged scratch stop' 137 'scratch_disk_reserve'
    Expect 'ordinary proof failure' 1 ''
    Expect 'successful exit' 0 ''
    Write-Fixture -Stage seal
    Expect 'seal interruption' 143 ''
    Write-Fixture -Oom 1
    Expect 'cgroup OOM' 143 ''
    Write-Fixture -Killed 1
    Expect 'cgroup OOM kill' 137 ''
    Write-Fixture -Swap 4096
    Expect 'swap activity' 143 ''
    Write-Fixture
    Set-Content -LiteralPath "$report/host-stop" 'The Windows proving worker guard ended.'
    Expect 'terminal host cancellation' 143 ''
    Set-Content -LiteralPath "$report/host-stop" 'Windows memory fell below the 1 GiB reserve.'
    Set-Content -LiteralPath "$report/verified-compressed.bin" 'existing seal'
    Expect 'already published compressed proof' 143 ''
    Remove-Item -LiteralPath "$report/verified-compressed.bin"
    Set-Content -LiteralPath "$report/normalize-progress.jsonl" '{"covered_shards":128}'
    $progress = (Get-FileHash -LiteralPath "$report/normalize-progress.jsonl").Hash
    $placement = (Get-FileHash -LiteralPath "$report/recursion-placement.json").Hash
    $history = Save-CashuArchiveInterruption $report 'host_reserve_or_heartbeat' 143
    if (!(Test-Path -LiteralPath "$history/host-stop") -or !(Test-Path -LiteralPath "$history/cgroup.txt") -or
            (Test-Path -LiteralPath "$report/host-stop") -or (Test-Path -LiteralPath "$report/stop-reason.txt") -or
            (Get-FileHash -LiteralPath "$report/normalize-progress.jsonl").Hash -cne $progress -or
            (Get-FileHash -LiteralPath "$report/recursion-placement.json").Hash -cne $placement) {
        throw 'Interrupting the stage changed its durable progress or lost its diagnostics.'
    }
    'diagnostic rotation and saved progress preservation passed'

    $tokens = $null
    $parseErrors = $null
    $scriptFile = Join-Path $PSScriptRoot 'run-cashu-v4-cuda-leaf-host.ps1'
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($scriptFile, [ref]$tokens, [ref]$parseErrors)
    if ($parseErrors) { throw ($parseErrors -join "`n") }
    $loop = $ast.Find({ param($node) $node -is [System.Management.Automation.Language.DoWhileStatementAst] }, $false)
    $Archive = $RawWithdrawal = $true
    $M13Wrap = $false
    $launchArgs = @('same-pinned-recursion')
    $script:starts = 0
    $script:reserveChecks = 0
    function Record-CashuAvailableMemory { 3GB }
    function Test-CashuArchiveResumeSpace { (++$script:reserveChecks) -gt 1 }
    function Start-Sleep { param([int]$Seconds) if ($Seconds -ne 10) { throw 'Unexpected recovery wait.' } }
    function Start-Process {
        param($FilePath, $ArgumentList, $WindowStyle, [switch]$PassThru, $RedirectStandardOutput, $RedirectStandardError)
        if (($ArgumentList -join ' ') -cne 'same-pinned-recursion') { throw 'The resume changed the launch arguments.' }
        Set-Content -LiteralPath $RedirectStandardOutput 'mock bounded recursion'
        Set-Content -LiteralPath $RedirectStandardError ''
        $script:starts++
        if ($script:starts -eq 1) {
            Write-Fixture
            return [pscustomobject]@{HasExited=$true;ExitCode=143}
        }
        if ($script:reserveChecks -ne 2) { throw 'The archive restarted before its reserves recovered.' }
        return [pscustomobject]@{HasExited=$true;ExitCode=0}
    }
    & ([scriptblock]::Create($loop.Extent.Text)) | Out-Null
    if ($script:starts -ne 2 -or (Get-FileHash -LiteralPath "$report/normalize-progress.jsonl").Hash -cne $progress) {
        throw 'The archive did not resume the same progress exactly once.'
    }
    'host supervisor waits and relaunches the same pinned stage passed'
} finally {
    $parent = (Resolve-Path -LiteralPath ([IO.Path]::GetTempPath())).Path.TrimEnd([IO.Path]::DirectorySeparatorChar)
    $resolved = (Resolve-Path -LiteralPath $report).Path
    if ([IO.Path]::GetDirectoryName($resolved) -cne $parent -or !(Split-Path -Leaf $resolved).StartsWith('cashu-archive-resume-')) {
        throw 'Refusing to remove an unexpected test directory.'
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
