[CmdletBinding()]
param([Parameter(Mandatory)][string]$RunDirectory, [string]$Name = 'baseline')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path "$PSScriptRoot/..").Path
$source = (Resolve-Path -LiteralPath $RunDirectory).Path
if ($Name -notmatch '^[a-zA-Z0-9_-]+$') { throw 'Invalid snapshot name' }
$destination = Join-Path $root "reports/$Name"
if (Test-Path -LiteralPath $destination) { throw 'Snapshot already exists; choose a new name.' }
$report = Get-Content -Raw -LiteralPath "$source/report.json" | ConvertFrom-Json
$build = Get-Content -Raw -LiteralPath "$root/out/build.json" | ConvertFrom-Json
if ($build.artifacts.'eboot.bin'.sha256 -ne $report.elf.sha256) { throw 'Build no longer matches this run.' }
$inputs = @()
foreach ($inputFile in $build.local_inputs.PSObject.Properties) {
    $path = [IO.Path]::GetFullPath((Join-Path $root $inputFile.Name))
    if (!$path.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Build input leaves the workspace.'
    }
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $inputFile.Value) {
        throw "Build input changed: $($inputFile.Name)"
    }
    $inputs += @{source=$path; relative=[IO.Path]::GetRelativePath($root, $path)}
}
New-Item -ItemType Directory -Path $destination | Out-Null
foreach ($inputFile in $inputs) {
    $target = Join-Path $destination "inputs/$($inputFile.relative)"
    New-Item -ItemType Directory -Path (Split-Path $target) -Force | Out-Null
    Copy-Item -LiteralPath $inputFile.source -Destination $target
}
foreach ($result in $report.results) {
    $paths = @()
    foreach ($log in $result.logs) {
        $original = Join-Path $root $log
        $relative = [IO.Path]::GetRelativePath($source, $original)
        if ($relative.StartsWith('..')) { throw 'Log path leaves the run directory.' }
        $target = Join-Path $destination "logs/$relative"
        New-Item -ItemType Directory -Path (Split-Path $target) -Force | Out-Null
        Copy-Item -LiteralPath $original -Destination $target
        $paths += [IO.Path]::GetRelativePath($root, $target).Replace('\','/')
    }
    $result.logs = $paths
}
foreach ($fixture in $report.fixtures.PSObject.Properties) {
    if ($fixture.Name -notmatch '^[a-zA-Z0-9_.-]+$') { throw 'Invalid fixture filename' }
    $original = Join-Path $root $fixture.Value.path
    if ((Get-FileHash -LiteralPath $original -Algorithm SHA256).Hash.ToLowerInvariant() -ne $fixture.Value.sha256) {
        throw 'Fixture no longer matches this run.'
    }
    New-Item -ItemType Directory -Path "$destination/fixtures" -Force | Out-Null
    Copy-Item -LiteralPath $original -Destination "$destination/fixtures/$($fixture.Name)"
    $fixture.Value.path = [IO.Path]::GetRelativePath($root, "$destination/fixtures/$($fixture.Name)").Replace('\','/')
}
$report | ConvertTo-Json -Depth 14 | Set-Content -LiteralPath "$destination/report.json" -Encoding utf8
Copy-Item -LiteralPath "$root/out/build.json","$root/out/verification.json","$root/artifacts.lock.json" -Destination $destination
Write-Host "Evidence snapshot: $destination"
