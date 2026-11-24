param([switch]$PublishSnapshot,[switch]$Metrics,[switch]$Console)
$ErrorActionPreference = 'Stop'

$state = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'hyperstack-ark-state.json') -Raw | ConvertFrom-Json
if ($state.vm_id -ne 1178271 -or $state.name -ne 'ark-mnr04-a100-a6e283d956') {
    throw 'The on-disk record does not identify the approved overnight VM and bucket.'
}
$coordinator = Get-CimInstance Win32_Process -Filter 'ProcessId=31376'
if (-not $coordinator -or $coordinator.CommandLine -notmatch 'ark-overnight-stage\.py"?\s+(?:"(?<quoted>[^"]+)"|(?<plain>\S+))') {
    throw 'The exact staging controller is not available.'
}
$credentialPath = if ($Matches.quoted) { $Matches.quoted } else { $Matches.plain }
$credential = (Get-Content -LiteralPath $credentialPath -Raw).Trim()
if (-not $credential) { throw 'The configured cloud credential is empty.' }
$headers = @{ api_key = $credential; Accept = 'application/json' }
$endpoint = 'https://infrahub-api.nexgencloud.com/v1'

$machine = (Invoke-RestMethod -Uri "$endpoint/core/virtual-machines/1178271" -Headers $headers -TimeoutSec 15).instance
if ($machine.id -ne 1178271 -or $machine.name -ne $state.name) { throw 'Cloud VM identity mismatch.' }
$response = Invoke-RestMethod -Uri "$endpoint/object-storage/buckets/ark-mnr04-a100-a6e283d956?region=CANADA-1" -Headers $headers -TimeoutSec 15
$bucket = if ($response.bucket) { $response.bucket } elseif ($response.data) { $response.data } else { $response }
$measurements = [ordered]@{}
foreach ($field in $bucket.PSObject.Properties) {
    if ($field.Name -match 'object.*count|count.*object|num.*object|size|storage.*used') {
        if ($field.Value -is [ValueType]) { $measurements[$field.Name] = $field.Value }
    }
}

if ($PublishSnapshot) {
    if ($null -eq $measurements.num_objects -or $null -eq $measurements.size_bytes) {
        throw 'The provider did not return a usable storage measurement.'
    }
    $snapshot = [ordered]@{
        schema = 'rbzk/ark-private-storage/v1'
        campaign = $state.name
        vm_id = $state.vm_id
        sampled_at_unix = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        bucket_bytes = [long]$measurements.size_bytes
        objects = [long]$measurements.num_objects
    } | ConvertTo-Json -Compress
    $target = Join-Path $PSScriptRoot 'hyperstack-ark-state.storage.json'
    $temporary = Join-Path $PSScriptRoot "hyperstack-ark-state.storage.$PID.tmp"
    [IO.File]::WriteAllText($temporary, $snapshot, [Text.UTF8Encoding]::new($false))
    [IO.File]::Move($temporary, $target, $true)
}
[pscustomobject]@{
    vm_id = $machine.id
    provider_status = $machine.status
    ingress_rules = @($machine.security_rules | Where-Object direction -EQ 'ingress').Count
    bucket_fields = @($bucket.PSObject.Properties.Name)
    bucket_measurements = $measurements
    sampled_at_utc = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json -Compress

if ($Metrics) {
    $observations = Invoke-RestMethod -Uri "$endpoint/core/virtual-machines/1178271/metrics" -Headers $headers -TimeoutSec 20
    $series = foreach ($name in 'cpu','memory.usages','disk.read','disk.write') {
        $metric = $observations.PSObject.Properties[$name].Value
        if ($metric) {
            [pscustomobject]@{name=$name;unit=$metric.unit;columns=$metric.columns;rows=$metric.data.Count;
                              latest=@($metric.data | Select-Object -Last 12)}
        }
    }
    [pscustomobject]@{vm_id=$machine.id;performance=$series} | ConvertTo-Json -Compress -Depth 6
}

if ($Console -and $machine.status -eq 'ACTIVE') {
    $logsEndpoint = "$endpoint/core/virtual-machines/1178271/logs"
    $request = Invoke-RestMethod -Uri $logsEndpoint -Headers $headers -Method Post -ContentType 'application/json' -Body '{"length":500}' -TimeoutSec 15
    if ($request.request_id -le 0) { throw 'The console log request did not return a valid handle.' }
    $lines = @()
    for ($i = 0; $i -lt 10; $i++) {
        try {
            $result = Invoke-RestMethod -Uri "$($logsEndpoint)?request_id=$($request.request_id)" -Headers $headers -TimeoutSec 8
            if ($result.logs -is [string] -and $result.logs.Length -gt 0) {
                $lines = @($result.logs -split '\r?\n' | Where-Object { $_.Trim() })
                break
            }
        } catch {
            if ($_.Exception.Response.StatusCode.value__ -notin @(404, 409, 422, 429, 503)) { throw }
        }
        Start-Sleep -Seconds 3
    }
    # Console lines can contain startup transport credentials. Report only counts.
    $categories = [ordered]@{
        oom=@($lines | Select-String -Pattern 'oom-kill|out of memory:|killed process .*anon-rss').Count
        cuda=@($lines | Select-String -Pattern 'NVRM:.*Xid|GPU has fallen off the bus|CUDA error').Count
        disk=@($lines | Select-String -Pattern 'blk_update_request: I/O error|Buffer I/O error|EXT4-fs error|No space left on device').Count
        cloud_init_failure=@($lines | Select-String -Pattern 'failed to run module.*scripts-user|failed running.*scripts/user').Count
    }
    $kernelTimes = @($lines | ForEach-Object {
        if ($_ -match '^\[\s*(\d+\.\d+)\]') { [double]$Matches[1] }
    })
    $latest = if ($kernelTimes.Count) { ($kernelTimes | Measure-Object -Maximum).Maximum } else { $null }
    [pscustomobject]@{vm_id=$machine.id;console_lines=$lines.Count;latest_kernel_seconds_since_boot=$latest;events=$categories} |
        ConvertTo-Json -Compress
}
