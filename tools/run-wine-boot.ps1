[CmdletBinding()]
param(
    [string]$Emulator="$PSScriptRoot/../build/shadPS4-win/shadps4.exe",
    [string]$Exe="$PSScriptRoot/../out/console32.exe",
    [string]$Prefix='',
    [ValidateRange(1,120)][int]$TimeoutSeconds=20
)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/probe-outcome.ps1"
$root=(Resolve-Path "$PSScriptRoot/..").Path
$elf=(Resolve-Path "$root/build/wine-boot/eboot.bin").Path
$emulatorPath=(Resolve-Path $Emulator).Path
$emulatorHash=(Get-FileHash $emulatorPath -Algorithm SHA256).Hash.ToLowerInvariant()
$manifest=Get-Content "$root/build/shadPS4-win/build-manifest.json" -Raw|ConvertFrom-Json
if($emulatorHash -ne $manifest.executable_sha256){throw 'Emulator does not match the pinned fork build manifest'}
$exePath=(Resolve-Path $Exe).Path
$build=Get-Content "$root/build/wine-boot/link-report.json" -Raw|ConvertFrom-Json
if((Get-FileHash $elf -Algorithm SHA256).Hash.ToLowerInvariant() -ne $build.bootstrap_sha256){throw 'Bootstrap ELF hash mismatch'}
$dir=Join-Path $root ('reports/wine-runs/'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'))
New-Item -ItemType Directory -Path "$dir/data/wine-prefix","$dir/data/wine-home","$dir/data/wine/lib/wine/x86_64-unix","$dir/data/wine/lib/wine/i386-windows","$dir/data/wine/lib/wine/x86_64-windows","$dir/data/wine/share/wine/nls" -Force|Out-Null
$prefixKind='empty-for-Wine-initialization'
if($Prefix){Get-ChildItem -LiteralPath (Resolve-Path $Prefix).Path -Force|ForEach-Object {Copy-Item -LiteralPath $_.FullName -Destination "$dir/data/wine-prefix" -Recurse}; $prefixKind='provided-copy'}
Copy-Item -LiteralPath $exePath -Destination "$dir/data/console32.exe"
$distribution=Get-Content "$root/out/wine/wine-runtime-manifest.json" -Raw|ConvertFrom-Json
foreach($module in $distribution.modules){
    $path=Join-Path "$root/out/wine" $module.path
    if((Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $module.sha256){throw 'Wine PE hash mismatch'}
    Copy-Item -LiteralPath $path -Destination "$dir/data/wine/lib/wine/i386-windows/$($module.name)"
}
foreach($data in $distribution.data){
    $path=Join-Path "$root/out/wine" $data.path
    if((Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $data.sha256){throw 'NLS hash mismatch'}
    Copy-Item -LiteralPath $path -Destination "$dir/data/wine/share/wine/nls"
}
$pe64=Get-Content "$root/out/wine-pe64/manifest.json" -Raw|ConvertFrom-Json
foreach($entry in $pe64.modules.PSObject.Properties){
    $path=Join-Path "$root/out/wine-pe64" $entry.Value.path
    if((Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value.sha256){throw 'Wine PE64 hash mismatch'}
    Copy-Item -LiteralPath $path -Destination "$dir/data/wine/lib/wine/x86_64-windows"
}
foreach($id in 1000..1003){New-Item -ItemType Directory -Path "$dir/user/home/$id/savedata","$dir/user/home/$id/trophy","$dir/user/home/$id/inputs" -Force|Out-Null}
$arguments=@('--config-clean','--fullscreen','false','--mount',"`"$dir/data`"",'/data','-g',"`"$elf`"",'--','/app0/eboot.bin','/data/console32.exe','/data/wine-prefix')
$timer=[Diagnostics.Stopwatch]::StartNew()
$process=Start-Process -FilePath $emulatorPath -ArgumentList $arguments -WorkingDirectory $dir -WindowStyle Hidden -PassThru -RedirectStandardOutput "$dir/stdout.log" -RedirectStandardError "$dir/stderr.log"
$timeout=-not $process.WaitForExit($TimeoutSeconds*1000)
if($timeout){Stop-Process -Id $process.Id -Force;$process.WaitForExit()}
$process.Refresh();$timer.Stop()
$logs=@(Get-ChildItem $dir -Recurse -File|Where-Object {$_.Extension -in '.log','.txt'})
$text=($logs|ForEach-Object {Get-Content -LiteralPath $_.FullName -Raw}) -join "`n"
$classification=Get-ProbeOutcome -Case wine-boot -LogText $text -ExitCode $process.ExitCode -TimedOut $timeout -ExpectedExitCode 0
$entered=$text -match 'PWBOOT entered___wine_main'
$reason=if($classification.invoked_stubs.Count){'Unimplemented emulator imports were invoked'}elseif($timeout){'Timeout before verified Windows program completion'}elseif(-not $entered){'Bootstrap did not reach __wine_main'}else{'Wine Unix entry reached; Windows execution unverified'}
$report=[ordered]@{schema_version=1;status='blocked';reason=$reason;Wine_booted=$false;unix_entry_reached=$entered;duration_ms=$timer.ElapsedMilliseconds;timed_out=$timeout;exit_code=$process.ExitCode;invoked_stubs=$classification.invoked_stubs;elf_sha256=$build.bootstrap_sha256;exe_sha256=(Get-FileHash $exePath -Algorithm SHA256).Hash.ToLowerInvariant();wine_commit=$build.wine_commit;emulator_commit=$manifest.commit;emulator_sha256=(Get-FileHash $emulatorPath -Algorithm SHA256).Hash.ToLowerInvariant();prefix_kind=$prefixKind;hardware_status='pending';logs=@($logs|ForEach-Object {$_.FullName.Substring($root.Length+1)})}
$report|ConvertTo-Json -Depth 8|Set-Content "$dir/report.json"
Write-Output ($report|ConvertTo-Json -Depth 8)
Write-Host "Report: $dir/report.json"
exit 1
