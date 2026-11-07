[CmdletBinding()]
param(
    [string]$Emulator = "$PSScriptRoot/../.deps/shadPS4/shadPS4.exe",
    [string]$Elf = "$PSScriptRoot/../out/eboot.bin",
    [ValidateSet('official','fork')][string]$EmulatorKind = 'official',
    [string]$EmulatorCommit = '',
    [string]$BuildManifest = '',
    [ValidateRange(1,300)][int]$TimeoutSeconds = 20,
    [switch]$IncludeWine,
    [switch]$IncludeWinePlatform,
    [string[]]$Cases = @('files','low-memory','reserve-collision','vm-backend','vm-ownership','vm-stress','vm-enforcement','generated-code','generated-rwx','threads','threads-adapter','exceptions','segments','translator','translator-rwx','translator-control','translator-fp','translator-fp-control','translator-fp-add','translator-retranslate','translator-teb','translator-teb-threads','hostexec-fp','hostexec-cache','dispatcher-mixed','dispatcher-fault','dispatcher-stops','dispatcher-owner','pe-preferred','pe-relocated','pe-invalid','pe-collision','pe-fourk-preferred','pe-fourk-relocated','pe-subpage','pe-dll-preferred','pe-dll-relocated','pe-dll-missing','pe-dll-symbol','pe-dll-ordinal','pe-dll-invalid','pe-dll-dependency','pe-init-order','pe-init-relocated','pe-init-failure','pe-tls-threads','pe-tls-invalid','pe-process','pe-process-relocated','pe-process-collision','console-bare','console32','lifecycle-host','process-exit-zero','process-exit-seven')
)
$ErrorActionPreference = 'Stop'
if ($IncludeWine) { $Cases += @('wine-ntdll','wine-kernelbase','wine-kernel') }
if ($IncludeWinePlatform) { $Cases += @('wine-memory','wine-paths','wine-unsupported') }
. "$PSScriptRoot/probe-outcome.ps1"
$root = (Resolve-Path "$PSScriptRoot/..").Path
$emulatorPath = (Resolve-Path -LiteralPath $Emulator).Path
$elfPath = (Resolve-Path -LiteralPath $Elf).Path
$lock = Get-Content -Raw -LiteralPath "$root/sources.lock.json" | ConvertFrom-Json
$artifacts = Get-Content -Raw -LiteralPath "$root/artifacts.lock.json" | ConvertFrom-Json
$emulatorHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $emulatorPath).Hash.ToLowerInvariant()
if ($EmulatorKind -eq 'official' -and $emulatorHash -ne $artifacts.shadps4.executable_sha256) {
    throw 'Emulator hash differs from the pinned official binary; use -EmulatorKind fork and specify -EmulatorCommit.'
}
if ($EmulatorKind -eq 'fork' -and $EmulatorCommit -notmatch '^[0-9a-f]{40}$') {
    throw 'Fork evidence requires the full emulator source commit.'
}
if ($EmulatorKind -eq 'official') { $EmulatorCommit = $artifacts.shadps4.source_commit }
$provenanceVerified = $EmulatorKind -eq 'official'
if ($BuildManifest) {
    $manifest = Get-Content -Raw -LiteralPath $BuildManifest | ConvertFrom-Json
    if ($manifest.commit -ne $EmulatorCommit -or $manifest.executable_sha256 -ne $emulatorHash) {
        throw 'Build manifest does not match the emulator revision and binary.'
    }
    $provenanceVerified = $true
}
$fixtureMetadata = [ordered]@{}
if (@($Cases | Where-Object { $_.StartsWith('pe-') }).Count) {
    foreach ($fixtureName in 'minimal32.exe','minimal4k32.exe','imports32.exe','testmath.dll','nested.dll','lifecycle.dll','lifecycle-peer.dll','lifecycle-fail.dll','process32.exe') {
    $fixturePath = Join-Path $root "out/$fixtureName"
    $fixtureHash = (Get-FileHash -LiteralPath $fixturePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $guestBuild = Get-Content -Raw "$root/out/build.json" | ConvertFrom-Json
    if ($guestBuild.artifacts.$fixtureName.sha256 -ne $fixtureHash) { throw 'PE fixture differs from its build manifest.' }
    $fixtureMetadata[$fixtureName] = [ordered]@{path="out/$fixtureName"; sha256=$fixtureHash; bytes=(Get-Item $fixturePath).Length}
    }
}
if ($Cases -contains 'console-bare') {
    $reference = Get-Content -Raw "$root/reports/increment11-windows-reference/report.json" | ConvertFrom-Json
    $consolePath = Join-Path $root 'out/console32-bare.exe'
    $consoleHash = (Get-FileHash -LiteralPath $consolePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $guestBuild = Get-Content -Raw "$root/out/build.json" | ConvertFrom-Json
    if ($consoleHash -ne $reference.exe_sha256 -or $guestBuild.artifacts.'console32-bare.exe'.sha256 -ne $consoleHash) {
        throw 'console32-bare.exe differs from the Windows reference or its build manifest.'
    }
    $fixtureMetadata['console32-bare.exe'] = [ordered]@{path='out/console32-bare.exe'; sha256=$consoleHash; bytes=(Get-Item $consolePath).Length}
}
if (@($Cases | Where-Object { $_.StartsWith('wine-') }).Count) {
    $wineManifest = Get-Content -Raw "$root/out/wine/wine-runtime-manifest.json" | ConvertFrom-Json
    if ($wineManifest.wine.commit -ne $lock.sources.wine.commit) { throw 'Wine revision mismatch' }
    foreach ($module in $wineManifest.modules) {
        if ($module.name -notin 'ntdll.dll','kernelbase.dll','kernel32.dll') { throw 'Unexpected Wine module' }
        $relative = "out/wine/$($module.path)"
        $hash = (Get-FileHash -LiteralPath (Join-Path $root $relative) -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -ne $module.sha256) { throw 'Wine DLL differs from its build manifest' }
        $fixtureMetadata[$module.name] = [ordered]@{path=$relative; sha256=$hash; bytes=$module.size}
    }
    if (@($wineManifest.modules).Count -ne 3) { throw 'Incomplete Wine module set' }
}
$runId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$runDir = Join-Path $root "reports/runs/$runId"
New-Item -ItemType Directory -Path $runDir -Force | Out-Null
$results = @()
foreach ($case in $Cases) {
    if ($case -notmatch '^[a-z][a-z0-9-]*$') { throw "Invalid case: $case" }
    $dir = Join-Path $runDir $case
    New-Item -ItemType Directory -Path "$dir/user","$dir/data" -Force | Out-Null
    if ($case.StartsWith('pe-') -or $case.StartsWith('wine-')) {
        foreach ($fixtureName in $fixtureMetadata.Keys) {
            Copy-Item -LiteralPath (Join-Path $root $fixtureMetadata[$fixtureName].path) -Destination "$dir/data/$fixtureName"
        }
    }
    if ($case -eq 'console-bare') {
        Copy-Item -LiteralPath (Join-Path $root 'out/console32-bare.exe') -Destination "$dir/data/console32-bare.exe"
        Copy-Item -LiteralPath (Join-Path $root 'reports/increment11-windows-reference/result.txt') -Destination "$dir/data/console-bare-reference.txt"
    }
    if ($case -eq 'console32') {
        Copy-Item -LiteralPath (Join-Path $root 'out/console32.exe') -Destination "$dir/data/console32.exe"
        Copy-Item -LiteralPath (Join-Path $root 'reports/increment18-windows-reference/result.txt') -Destination "$dir/data/console32-reference.txt"
    }
    if ($case -eq 'lifecycle-host') {
        foreach ($fixtureName in 'lifecycle-host.exe','lifecycle.dll','lifecycle-peer.dll','lifecycle-fail.dll') {
            Copy-Item -LiteralPath (Join-Path $root "out/$fixtureName") -Destination "$dir/data/$fixtureName"
        }
    }
    # A fresh isolated profile has no saves to migrate. Existing home directories
    # prevent the first-run migration dialog from blocking unattended tests.
    foreach ($userId in 1000..1003) {
        New-Item -ItemType Directory -Path "$dir/user/home/$userId/savedata","$dir/user/home/$userId/trophy","$dir/user/home/$userId/inputs" -Force | Out-Null
    }
    $stdout = Join-Path $dir 'stdout.log'
    $stderr = Join-Path $dir 'stderr.log'
    # Start-Process uses a Windows command line, so every path is quoted explicitly.
    if ($emulatorPath.Contains('"') -or $elfPath.Contains('"') -or $dir.Contains('"')) { throw 'Invalid path quotation' }
    $arguments = @('--config-clean','--fullscreen','false','--mount', "`"$dir/data`"", '/data', '-g', "`"$elfPath`"", '--', '--case', $case)
    $clock = [Diagnostics.Stopwatch]::StartNew()
    $process = Start-Process -FilePath $emulatorPath -ArgumentList $arguments -WorkingDirectory $dir -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $timedOut = -not $process.WaitForExit($TimeoutSeconds * 1000)
    if ($timedOut) { Stop-Process -Id $process.Id -Force; $process.WaitForExit() }
    $clock.Stop()
    $process.Refresh()
    $logs = @(Get-ChildItem -LiteralPath $dir -Recurse -File | Where-Object { $_.Extension -in '.log','.txt' } | Sort-Object FullName)
    $allText = ($logs | ForEach-Object { Get-Content -Raw -LiteralPath $_.FullName }) -join "`n"
    $expectedExit = if ($case -in 'pe-preferred','pe-relocated','pe-fourk-preferred','pe-fourk-relocated','pe-dll-preferred','pe-dll-relocated','lifecycle-host') { 42 } elseif ($case -eq 'process-exit-seven') { 7 } else { 0 }
    $outcome = Get-ProbeOutcome -Case $case -LogText $allText -ExitCode $process.ExitCode -TimedOut $timedOut -ExpectedExitCode $expectedExit
    $consoleResult = $null
    if ($case -in 'console-bare','console32') {
        $referenceFolder = if ($case -eq 'console32') { 'increment18-windows-reference' } else { 'increment11-windows-reference' }
        $produced = "$dir/data/orbisdesk/$case/result.txt"
        $expectedBytes = [IO.File]::ReadAllBytes((Join-Path $root "reports/$referenceFolder/result.txt"))
        $producedBytes = if (Test-Path -LiteralPath $produced) { [IO.File]::ReadAllBytes($produced) } else { $null }
        $matches = $null -ne $producedBytes -and [Convert]::ToBase64String($producedBytes) -eq [Convert]::ToBase64String($expectedBytes)
        $consoleResult = [ordered]@{produced=$null -ne $producedBytes; matches_windows_reference=$matches}
        if ($outcome.status -eq 'passed' -and -not $matches) { $outcome.status = 'failed'; $outcome.reason = 'result.txt differs from the Windows reference' }
    }
    $result = [ordered]@{
        case=$case; status=$outcome.status; reason=$outcome.reason; duration_ms=$clock.ElapsedMilliseconds
        timed_out=$timedOut; emulator_exit_code=$process.ExitCode; expected_guest_exit_code=$expectedExit; events=$outcome.events
        guest_reported_pass=$outcome.guest_reported_pass; emulator_shutdown=$outcome.emulator_shutdown; invoked_stubs=$outcome.invoked_stubs
        console_result=$consoleResult
        logs=@($logs | ForEach-Object { $_.FullName.Substring($root.Length + 1) })
    }
    $results += $result
    Write-Host "$case : $($outcome.status) ($($outcome.reason))"
}
$report = [ordered]@{
    schema_version=1; run_id=$runId; sources=$lock.sources
    emulator=[ordered]@{kind=$EmulatorKind; version=$artifacts.shadps4.version; commit=$EmulatorCommit; sha256=$emulatorHash; provenance_verified=$provenanceVerified}
    elf=[ordered]@{path=$elfPath; sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $elfPath).Hash.ToLowerInvariant()}
    fixtures=$fixtureMetadata
    configuration=[ordered]@{timeout_seconds=$TimeoutSeconds; fresh_profile=$true; flags=@('--config-clean','--fullscreen false'); mount='/data'; host_os=[Environment]::OSVersion.VersionString}
    validation_environment="shadPS4 $EmulatorKind"; hardware_status='pending'; results=$results
}
$report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath "$runDir/report.json" -Encoding utf8
Write-Host "Report: $runDir/report.json"
if (@($results | Where-Object { $_.status -ne 'passed' }).Count) { exit 1 }
