$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/m14-storage.ps1"

$primary = 'E:\ProofGroveCashuScratch'
$alternate = 'D:\ProofGroveCashuScratch'
$fanout = 9049476142L
$tape = 15685745952L
$btrfsRoot = Get-CashuM14BtrfsRoot
$btrfsBudget = Get-CashuM14BtrfsFanoutBudget $fanout
$cases = @(
    @{name='new plan and tape on E'; e=40GB; d=33GB; fanout=$primary; tape=$primary},
    @{name='new plan on E and tape on D'; e=19GB; d=33GB; fanout=$primary; tape=$alternate},
    @{name='new plan on D and tape on E'; e=24GB; d=26GB; fanout=$alternate; tape=$primary},
    @{name='Btrfs plan and fresh tape on D'; e=11GB; d=33GB; fanout=$btrfsRoot; tape=$alternate; btrfs=$true},
    @{name='Btrfs plan and fresh tape both backed by E'; e=25GB; d=19GB; fanout=$btrfsRoot; tape=$primary; btrfs=$true}
)
foreach ($case in $cases) {
    $result = Select-CashuM14Scratch $primary $alternate $case.e $case.d $fanout $tape `
        -BtrfsFree (4GB) -BtrfsBackingFree $case.e -PreserveBackingReserve
    if ($result.fanout -ne $case.fanout -or $result.tape -ne $case.tape -or
            [bool]$result.btrfs_fanout -ne [bool]$case.btrfs) {
        throw "Wrong placement for $($case.name)"
    }
    "$($case.name) passed"
}

$denied = @(
    @{name='D cannot cross its 16 GiB threshold'; e=11GB; d=($tape + 16GB - 1); btrfsFree=4GB},
    @{name='E budgets the fanout and tape together'; e=($tape + $btrfsBudget + 8GB - 1); d=16GB; btrfsFree=4GB},
    @{name='Btrfs cannot cross its 2 GiB threshold'; e=11GB; d=33GB; btrfsFree=($btrfsBudget + 2GB - 1)},
    @{name='Btrfs virtual free cannot spend the E reserve'; e=($btrfsBudget + 8GB - 1); d=33GB; btrfsFree=4GB},
    @{name='raw placement stays rejected when it cannot fit'; e=11GB; d=33GB; btrfsFree=0}
)
foreach ($case in $denied) {
    $refused = $false
    try {
        Select-CashuM14Scratch $primary $alternate $case.e $case.d $fanout $tape `
            -BtrfsFree $case.btrfsFree -BtrfsBackingFree $case.e -PreserveBackingReserve | Out-Null
    } catch {
        $refused = $_.Exception.Message -like 'The available scratch volumes*'
    }
    if (!$refused) { throw "Expected to refuse $($case.name)" }
    "$($case.name) passed"
}
