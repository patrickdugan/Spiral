$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/m14-storage.ps1"

$primary = 'E:\ProofGroveCashuScratch'
$alternate = 'D:\ProofGroveCashuScratch'
$fanout = 9049476142L
$tape = 15685745952L
$compressedBudget = Get-CashuM14CompressedFanoutBudget $fanout
$cases = @(
    @{name='new plan and tape on E'; e=40GB; d=33GB; fanout=$primary; tape=$primary},
    @{name='new plan on E and tape on D'; e=19GB; d=33GB; fanout=$primary; tape=$alternate},
    @{name='new plan on D and tape on E'; e=24GB; d=26GB; fanout=$alternate; tape=$primary},
    @{name='compressed plan on E and fresh tape on D'; e=11GB; d=33GB; fanout=$primary; tape=$alternate; compressed=$true},
    @{name='compressed plan and fresh tape on E'; e=25GB; d=19GB; fanout=$primary; tape=$primary; compressed=$true},
    @{name='compressed plan and fresh tape on D'; e=9GB; d=33GB; fanout=$alternate; tape=$alternate; compressed=$true}
)
foreach ($case in $cases) {
    $result = Select-CashuM14Scratch $primary $alternate $case.e $case.d $fanout $tape `
        -AllowCompressedFanout -PreserveBackingReserve
    if ($result.fanout -ne $case.fanout -or $result.tape -ne $case.tape -or
            [bool]$result.compressed_fanout -ne [bool]$case.compressed) {
        throw "Wrong placement for $($case.name)"
    }
    "$($case.name) passed"
}

$denied = @(
    @{name='D cannot cross its 16 GiB threshold'; e=9GB; d=($tape + $compressedBudget + 16GB - 1); compress=$true},
    @{name='E cannot cross its 8 GiB threshold'; e=($tape + $compressedBudget + 8GB - 1); d=16GB; compress=$true},
    @{name='uncompressed placement stays rejected when it cannot fit'; e=9GB; d=33GB; compress=$false}
)
foreach ($case in $denied) {
    $refused = $false
    try {
        Select-CashuM14Scratch $primary $alternate $case.e $case.d $fanout $tape `
            -AllowCompressedFanout:$case.compress -PreserveBackingReserve | Out-Null
    } catch {
        $refused = $_.Exception.Message -like 'The available scratch volumes*'
    }
    if (!$refused) { throw "Expected to refuse $($case.name)" }
    "$($case.name) passed"
}
