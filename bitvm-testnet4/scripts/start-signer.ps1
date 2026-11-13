param(
    [Parameter(Mandatory=$true)][string]$BitcoinDirectory,
    [Parameter(Mandatory=$true)][string]$PrivateDirectory,
    [Parameter(Mandatory=$true)][string]$SetupFile,
    [string]$ExpectedCoreSha256 = 'f79eeb94e1379986df9f7be4c78c8fc8e18dc9be64a31cbaa8acad249d3db77a'
)
$ErrorActionPreference = 'Stop'
$demoCore = Join-Path $BitcoinDirectory 'bitcoind.exe'
$demoCli = Join-Path $BitcoinDirectory 'bitcoin-cli.exe'
$demoPrivate = [IO.Path]::GetFullPath($PrivateDirectory)
$demoSource = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$demoSetup = [IO.Path]::GetFullPath($SetupFile)
if ($demoPrivate.StartsWith($demoSource + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or $demoPrivate -eq $demoSource) {
    throw 'Keep private wallet files outside the source checkout'
}
if ((Test-Path -LiteralPath $demoPrivate) -or (Test-Path -LiteralPath $demoSetup)) { throw 'Use fresh private and setup paths' }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $demoCore).Hash.ToLowerInvariant() -ne $ExpectedCoreSha256.ToLowerInvariant()) { throw 'Installed Core identity differs' }
New-Item -ItemType Directory -Path $demoPrivate | Out-Null
$demoData = Join-Path $demoPrivate 'data'
New-Item -ItemType Directory -Path $demoData | Out-Null
$demoListener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
$demoListener.Start()
$demoPort = $demoListener.LocalEndpoint.Port
$demoListener.Stop()
$demoArgs = @('-testnet4', "-datadir=$demoData", '-server=1', '-listen=0', '-connect=0', '-dnsseed=0', '-discover=0', '-walletbroadcast=0', '-rpcbind=127.0.0.1', '-rpcallowip=127.0.0.1', "-rpcport=$demoPort", '-prune=550', '-dbcache=64', '-maxconnections=2')
# Explicit quoting supports a data path containing spaces; no shell expansion is involved.
$demoQuotedArgs = $demoArgs | ForEach-Object { '"' + $_ + '"' }
$demoProcess = Start-Process -FilePath $demoCore -ArgumentList $demoQuotedArgs -WindowStyle Hidden -PassThru
$demoOwner = Join-Path $demoPrivate 'owner.json'
[pscustomobject]@{pid=$demoProcess.Id; datadir=$demoData; rpcport=$demoPort; network='testnet4'; wallet='bitvm-demo'} | ConvertTo-Json | Set-Content -LiteralPath $demoOwner -Encoding utf8
$demoRpc = @("-datadir=$demoData", '-testnet4', "-rpcport=$demoPort", '-rpcclienttimeout=5')
try {
    $demoDeadline = [DateTime]::UtcNow.AddSeconds(60)
    $demoInfo = $null
    while ([DateTime]::UtcNow -lt $demoDeadline) {
        if ($demoProcess.HasExited) { throw 'Owned signer exited during startup' }
        $demoReply = & $demoCli @demoRpc getblockchaininfo 2>$null
        if ($LASTEXITCODE -eq 0) { $demoInfo = $demoReply | ConvertFrom-Json; break }
        Start-Sleep -Milliseconds 200
    }
    if ($null -eq $demoInfo -or $demoInfo.chain -ne 'testnet4') { throw 'Testnet4 RPC not ready' }
    $demoGenesis = (& $demoCli @demoRpc getblockhash 0).Trim()
    if ($LASTEXITCODE -ne 0 -or $demoGenesis -ne '00000000da84f2bafbbc53dee25a72ae507ff4914b867c565be350b0da8bf043') { throw 'Wrong network genesis' }
    $demoPeers = [int](& $demoCli @demoRpc getconnectioncount)
    if ($demoPeers -ne 0) { throw 'Signer must have zero peers' }
    $demoCreated = & $demoCli @demoRpc createwallet bitvm-demo
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create dedicated demo wallet' }
    $demoAddress = (& $demoCli @demoRpc '-rpcwallet=bitvm-demo' getnewaddress bitvm-demo-funding bech32m).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $demoAddress.StartsWith('tb1p')) { throw 'Wallet did not produce a testnet Taproot address' }
    $demoAddressInfo = & $demoCli @demoRpc '-rpcwallet=bitvm-demo' getaddressinfo $demoAddress | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $demoAddressInfo.ismine -ne $true) { throw 'Funding address is not owned' }
    New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($demoSetup)) -Force | Out-Null
    $demoReceipt = [pscustomobject]@{status='ready_for_testnet4_funding'; network='testnet4'; genesis=$demoGenesis; wallet='bitvm-demo'; address=$demoAddress; script_pubkey=$demoAddressInfo.scriptPubKey; recommended_funding_sats=100000; blocks=$demoInfo.blocks; peers=$demoPeers; core_sha256=$ExpectedCoreSha256; private_owner_record=$demoOwner; created_at=[DateTime]::UtcNow.ToString('o')}
    $demoReceipt | ConvertTo-Json | Set-Content -LiteralPath $demoSetup -Encoding utf8
    $demoReceipt | ConvertTo-Json
} catch {
    # Stop only the node started by this invocation, through its dedicated RPC endpoint.
    & $demoCli @demoRpc stop 2>$null | Out-Null
    throw
}
