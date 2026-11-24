$ErrorActionPreference = 'Stop'
$stage = Join-Path $PSScriptRoot 'cloud-cashu'
New-Item -ItemType Directory -Force -Path $stage | Out-Null
$record = Join-Path $stage 'cpu.json'
if (Test-Path -LiteralPath $record) { throw 'An existing CPU VM record must be checked before a retry.' }
$intent = Join-Path $stage 'cpu-intent.json'
if (Test-Path -LiteralPath $intent) { throw 'Check the prior CPU provisioning intent before retrying.' }
$credential = (Get-Content -Raw -LiteralPath (Join-Path ([Environment]::GetFolderPath('Desktop')) 'hyper.txt.txt')).Trim()
if ($credential -notmatch '^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$') { throw 'Unexpected Hyperstack credential format.' }
$headers = @{api_key=$credential; Accept='application/json'}
$api = 'https://infrahub-api.nexgencloud.com/v1'
$environment = 'default-CANADA-1'
$suffix = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$name = "cashu-shinigami-cpu-$suffix"
$keyName = "cashu-ark-$suffix"
$sshIdentity = Join-Path $stage 'pilot-ed25519'
if (!(Test-Path -LiteralPath "$sshIdentity.pub")) {
    & ssh-keygen.exe -q -t ed25519 -f $sshIdentity -N '' -C 'cashu-shinigami-isolated-pilot'
    if ($LASTEXITCODE) { throw 'Pilot SSH key generation failed.' }
}

function Post-CloudJson([string] $Path, [hashtable] $Body) {
    $parameters = @{
        Method='Post'; Uri="$api/$Path"; MaximumRedirection=0; Headers=$headers
        ContentType='application/json'; Body=(ConvertTo-Json -InputObject $Body -Depth 6 -Compress); TimeoutSec=30
    }
    try {
        Invoke-RestMethod @parameters
    } catch {
        $code = $_.Exception.Response.StatusCode
        $detail = if ($_.ErrorDetails.Message) { [string]$_.ErrorDetails.Message } else { $_.Exception.GetType().Name }
        $detail = ($detail -replace [regex]::Escape($credential), '[redacted]')
        throw "Hyperstack $Path request failed ($code): $($detail.Substring(0,[Math]::Min(380,$detail.Length)))"
    }
}

$key = Post-CloudJson 'core/keypairs' @{
    name=$keyName; environment_name=$environment
    public_key=(Get-Content -Raw -LiteralPath "$sshIdentity.pub").Trim()
}
if ($key.status -eq $false) { throw 'Hyperstack refused the standalone pilot key.' }
$request = @{
    name=$name; environment_name=$environment
    image_name='Ubuntu Server 24.04 LTS R570 CUDA 12.8 with Docker'
    flavor_name='n1-cpu-xlarge'; key_name=$keyName; count=1; assign_floating_ip=$true
    security_rules=@(@{
        direction='ingress'; protocol='tcp'; port_range_min=22; port_range_max=22
        ethertype='IPv4'; remote_ip_prefix='0.0.0.0/0'
    })
}
$request | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $intent -Encoding utf8
$reply = Post-CloudJson 'core/virtual-machines' $request
if ($reply.status -eq $false -or @($reply.instances).Count -ne 1 -or !$reply.instances[0].id) {
    throw 'A unique VM was not returned. Check the creation intent before retrying.'
}
$vm = $reply.instances[0]
$result = [ordered]@{ id=$vm.id; name=$name; status=$vm.status; key=$keyName; region='CANADA-1'
                       public_ip=$vm.floating_ip; flavor=$request.flavor_name; provisioned_unix=$suffix }
$result | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $record -Encoding utf8
$result | ConvertTo-Json -Depth 4
