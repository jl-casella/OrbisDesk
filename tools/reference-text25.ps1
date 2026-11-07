# SPDX-License-Identifier: LGPL-2.1-or-later
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$destination=Join-Path $root 'reports/increment25-windows-reference'
if (Test-Path (Join-Path $destination 'report.json')) { throw 'Reference exists; preserve it before rerunning.' }
New-Item -ItemType Directory -Force $destination | Out-Null
Copy-Item (Join-Path $root 'out/gui-text64.exe') $destination
Copy-Item (Join-Path $root 'out/wine-gui/fonts/tahoma.ttf') $destination
$process=Start-Process -FilePath (Join-Path $destination 'gui-text64.exe') -WorkingDirectory $destination -WindowStyle Hidden -PassThru
if (-not $process.WaitForExit(60000)) { $process.Kill(); throw 'Text fixture timed out; inspect text-progress.txt' }
$process.Refresh()
$result=[System.IO.File]::ReadAllText((Join-Path $destination 'text-result.txt'))
$report=[ordered]@{exit_code=$process.ExitCode;exe_sha256=(Get-FileHash (Join-Path $destination 'gui-text64.exe') -Algorithm SHA256).Hash.ToLower();font_sha256=(Get-FileHash (Join-Path $destination 'tahoma.ttf') -Algorithm SHA256).Hash.ToLower();result=$result}
$report | ConvertTo-Json | Set-Content (Join-Path $destination 'report.json')
if ($process.ExitCode -ne 0 -or -not $result.StartsWith('passed=1;family_tahoma=1;')) { throw 'Native Windows text fixture failed' }
$report | ConvertTo-Json -Compress
