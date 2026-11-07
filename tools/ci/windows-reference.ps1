[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path "$PSScriptRoot/../..").Path
$timer = [Diagnostics.Stopwatch]::StartNew()
$fixture = Get-Content -Raw "$root/out/ci-fixtures.json" | ConvertFrom-Json
$revision = (git -C $root rev-parse HEAD).Trim()
if ($fixture.source_sha -ne $revision) { throw 'Fixture source SHA differs' }
foreach ($item in $fixture.artifacts.PSObject.Properties) {
    $digest = (Get-FileHash -LiteralPath "$root/out/$($item.Name)" -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($digest -ne $item.Value.sha256) { throw "Fixture changed: $($item.Name)" }
}
$references = [ordered]@{}
foreach ($case in @(
    @{ Name='console32'; Exe='console32.exe'; Exit=0 },
    @{ Name='console-bare'; Exe='console32-bare.exe'; Exit=0 },
    @{ Name='lifecycle-host'; Exe='lifecycle-host.exe'; Exit=42 }
)) {
    $work = Join-Path ([IO.Path]::GetTempPath()) ('orbisdesk-ci-' + [guid]::NewGuid())
    New-Item -ItemType Directory -Path $work | Out-Null
    try {
        Get-ChildItem "$root/out" -File | Where-Object { $_.Extension -in '.exe','.dll' } | Copy-Item -Destination $work
        $process = Start-Process -FilePath "$work/$($case.Exe)" -WorkingDirectory $work -WindowStyle Hidden -PassThru -RedirectStandardOutput "$work/stdout.log" -RedirectStandardError "$work/stderr.log"
        if (-not $process.WaitForExit(30000)) { $process.Kill(); throw "Reference timeout: $($case.Name)" }
        if ($process.ExitCode -ne $case.Exit) { throw "Unexpected native exit: $($case.Name): $($process.ExitCode)" }
        [byte[]]$data = @()
        if (Test-Path "$work/result.txt") { $data = [IO.File]::ReadAllBytes("$work/result.txt") }
        if ($case.Exit -eq 0 -and $data.Length -eq 0) { throw 'Missing reference output' }
        $references[$case.Name] = @{ exe=$case.Exe; exit_code=$process.ExitCode; result_base64=[Convert]::ToBase64String($data); exe_sha256=$fixture.artifacts.($case.Exe).sha256 }
    } finally {
        # Only this explicitly created temporary directory is removed.
        $resolvedWork = (Resolve-Path -LiteralPath $work).Path
        $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
        if (-not $resolvedWork.StartsWith($tempRoot,[StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected temporary path' }
        Remove-Item -LiteralPath $resolvedWork -Recurse -Force
    }
}
New-Item -ItemType Directory -Path "$root/reports/ci" -Force | Out-Null
$report = @{ source_sha=$revision; scope='Native Windows execution, not Wine/PS4'; fixture_manifest_sha256=(Get-FileHash "$root/out/ci-fixtures.json").Hash.ToLowerInvariant(); references=$references; duration_seconds=$timer.Elapsed.TotalSeconds }
$report | ConvertTo-Json -Depth 8 | Set-Content "$root/reports/ci/windows-reference.json" -Encoding utf8
Write-Output "Windows references verified for $revision"
