[CmdletBinding()]
param([string]$Distribution = 'Ubuntu-22.04')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path "$PSScriptRoot/..").Path
$lock = Get-Content -Raw "$root/fork-tools.lock.json" | ConvertFrom-Json
$downloads = Join-Path $root '.deps/downloads'
$tools = Join-Path $root '.deps/windows-tools'
New-Item -ItemType Directory -Path $downloads,$tools -Force | Out-Null
foreach ($spec in $lock.tools) {
    $archive = Join-Path $downloads $spec.archive
    if (-not (Test-Path -LiteralPath $archive)) {
        & curl.exe -fL --retry 2 --connect-timeout 20 --max-time 600 -o "$archive.part" $spec.url
        if ($LASTEXITCODE) { throw "Download failed: $($spec.name)" }
        if ((Get-FileHash -LiteralPath "$archive.part" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $spec.sha256) { throw 'Tool archive checksum mismatch' }
        Move-Item -LiteralPath "$archive.part" -Destination $archive
    }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $spec.sha256) { throw 'Tool archive checksum mismatch' }
    $destination = Join-Path $tools $spec.destination
    if (Test-Path -LiteralPath $destination) { continue }
    switch ($spec.kind) {
        'zip-root' { Expand-Archive -LiteralPath $archive -DestinationPath $tools -Force }
        'zip' { Expand-Archive -LiteralPath $archive -DestinationPath $destination -Force }
        'nsis' {
            $linuxArchive = & wsl -d $Distribution -- wslpath -a $archive
            if ($LASTEXITCODE) { throw 'WSL path conversion failed' }
            $linuxDestination = & wsl -d $Distribution -- wslpath -a $destination
            if ($LASTEXITCODE) { throw 'WSL path conversion failed' }
            & wsl -d $Distribution -- 7z x $linuxArchive "-o$linuxDestination" -y
            if ($LASTEXITCODE) { throw 'Clang extraction failed; p7zip-full is required in WSL' }
        }
        default { throw 'Unknown tool archive format' }
    }
}
Write-Output 'Portable fork tools verified. Visual Studio C++ and Windows SDK are separate prerequisites.'
