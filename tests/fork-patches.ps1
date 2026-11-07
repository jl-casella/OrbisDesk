$ErrorActionPreference = 'Stop'
$root = (Resolve-Path "$PSScriptRoot/..").Path
$repository = Join-Path $root '.deps/shadPS4-fork'
$lock = Get-Content -Raw "$root/fork.lock.json" | ConvertFrom-Json
$previousIndex = $env:GIT_INDEX_FILE
$taskIndex = Join-Path $root ('.deps/fork-repro-' + [guid]::NewGuid().ToString('N') + '.index')
try {
    $env:GIT_INDEX_FILE = $taskIndex
    & git -C $repository read-tree $lock.base_commit
    if ($LASTEXITCODE) { throw 'Could not prepare isolated index' }
    foreach ($patch in $lock.patches) {
        $path = Join-Path $root $patch.path
        if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $patch.sha256) { throw 'Patch checksum mismatch' }
        & git -C $repository apply --cached $path
        if ($LASTEXITCODE) { throw 'Patch does not apply to pinned base' }
    }
    $actual = & git -C $repository write-tree
    if ($LASTEXITCODE) { throw 'Could not calculate patched tree' }
    $expected = & git -C $repository rev-parse "$($lock.commit)^{tree}"
    if ($LASTEXITCODE -or $actual -ne $expected) { throw 'Reconstructed source differs from the fork commit' }
    Write-Output "Pinned patches reproduce fork tree $actual"
} finally {
    $env:GIT_INDEX_FILE = $previousIndex
    foreach ($path in @($taskIndex,"$taskIndex.lock")) {
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
    }
}
