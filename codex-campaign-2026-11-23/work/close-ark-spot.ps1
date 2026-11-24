$ErrorActionPreference = 'Stop'
$coordinator = Get-CimInstance Win32_Process -Filter 'ProcessId=31376'
if (-not $coordinator -or $coordinator.CommandLine -notmatch 'ark-overnight-stage\.py"?\s+(?:"(?<quoted>[^"]+)"|(?<plain>\S+))') {
    throw 'The exact Ark staging controller is unavailable.'
}
$credentialPath = if ($Matches.quoted) { $Matches.quoted } else { $Matches.plain }
python (Join-Path $PSScriptRoot 'close-ark-spot.py') $credentialPath
exit $LASTEXITCODE
