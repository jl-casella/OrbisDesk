$ErrorActionPreference = 'Stop'
Add-Type -Path "$PSScriptRoot/windows-view-protection.cs"
$withoutExecution = [WindowsViewProtectionProbe]::Run($false)
$withExecution = [WindowsViewProtectionProbe]::Run($true)
Write-Output $withoutExecution
Write-Output $withExecution
if ($withoutExecution -notmatch 'RW_to_RX=False; win32_error=87') { throw 'Original failure was not reproduced' }
if ($withExecution -notmatch 'RW_to_RX=True; win32_error=0') { throw 'Executable view did not allow RW to RX' }
$root = (Resolve-Path "$PSScriptRoot/..").Path
New-Item -ItemType Directory -Path "$root/build/host" -Force | Out-Null
[ordered]@{
    status='passed'; environment='Windows native API reproduction, not shadPS4'
    original_view=$withoutExecution; executable_view_restricted_to_rw=$withExecution
    source_sha256=(Get-FileHash "$PSScriptRoot/windows-view-protection.cs" -Algorithm SHA256).Hash.ToLowerInvariant()
} | ConvertTo-Json | Set-Content "$root/build/host/windows-view-protection.json" -Encoding utf8
