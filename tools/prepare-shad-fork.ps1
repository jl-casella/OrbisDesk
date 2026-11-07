[CmdletBinding()]
param([switch]$SkipSubmodules)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path "$PSScriptRoot/..").Path
$lock = Get-Content -Raw "$root/fork.lock.json" | ConvertFrom-Json
$repository = Join-Path $root '.deps/shadPS4-fork'
foreach ($patch in $lock.patches) {
    $path = Join-Path $root $patch.path
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $patch.sha256) { throw 'Fork patch checksum mismatch' }
}
if (-not (Test-Path -LiteralPath $repository)) {
    & git init $repository
    if ($LASTEXITCODE) { throw 'git init failed' }
    & git -C $repository remote add origin $lock.upstream
    if ($LASTEXITCODE) { throw 'git remote failed' }
    & git -C $repository fetch --depth 1 origin $lock.base_commit
    if ($LASTEXITCODE) { throw 'Fork base fetch failed' }
    & git -C $repository checkout -b $lock.branch FETCH_HEAD
    if ($LASTEXITCODE) { throw 'Fork branch creation failed' }
    foreach ($patch in $lock.patches) {
        & git -C $repository -c user.name='OrbisDesk Prototype' -c user.email='orbisdesk@localhost' am --committer-date-is-author-date (Join-Path $root $patch.path)
        if ($LASTEXITCODE) { throw 'Patch application failed; checkout preserved for inspection' }
    }
}
$actual = & git -C $repository rev-parse HEAD
if ($LASTEXITCODE -or $actual -ne $lock.commit) { throw 'Existing fork revision differs; refusing to overwrite' }
$dirty = & git -C $repository status --porcelain --untracked-files=no --ignore-submodules
if ($LASTEXITCODE -or $dirty) { throw 'Fork tracked sources changed; refusing to overwrite' }
if (-not $SkipSubmodules) {
    & git -C $repository submodule update --init --recursive --depth 1 --jobs 6
    if ($LASTEXITCODE) { throw 'Pinned submodule fetch failed' }
}
Write-Output "Fork ready at $actual"
