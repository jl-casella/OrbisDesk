[CmdletBinding()]
param([string]$Distribution = 'Ubuntu-22.04', [switch]$InstallBuildTools)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path "$PSScriptRoot/..").Path
$lock = Get-Content -Raw "$root/artifacts.lock.json" | ConvertFrom-Json
$downloads = Join-Path $root '.deps/downloads'
New-Item -ItemType Directory -Path $downloads -Force | Out-Null
function Get-VerifiedArtifact($spec, $name) {
    $path = Join-Path $downloads $name
    if (-not (Test-Path -LiteralPath $path)) {
        & curl.exe -fL --retry 2 --connect-timeout 20 --max-time 600 -o "$path.part" $spec.url
        if ($LASTEXITCODE) { throw "Download failed: $name" }
        if ((Get-FileHash -LiteralPath "$path.part" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $spec.sha256) {
            throw "Checksum mismatch: $name"
        }
        Move-Item -LiteralPath "$path.part" -Destination $path
    }
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $spec.sha256) {
        throw "Checksum mismatch: $name"
    }
    return $path
}
$sdkArchive = Get-VerifiedArtifact $lock.openorbis 'openorbis-v0.5.4.tar.gz'
$emulatorArchive = Get-VerifiedArtifact $lock.shadps4 'shadps4-0.20.0.zip'
if (-not (Test-Path "$root/.deps/sdk/OpenOrbis/PS4Toolchain/lib/crt1.o")) {
    New-Item -ItemType Directory -Path "$root/.deps/sdk" -Force | Out-Null
    & tar -xzf $sdkArchive -C "$root/.deps/sdk"
    if ($LASTEXITCODE) { throw 'SDK extraction failed' }
}
if (-not (Test-Path "$root/.deps/shadPS4/shadPS4.exe")) {
    Expand-Archive -LiteralPath $emulatorArchive -DestinationPath "$root/.deps/shadPS4"
}
if ((Get-FileHash "$root/.deps/shadPS4/shadPS4.exe" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $lock.shadps4.executable_sha256) {
    throw 'Emulator executable does not match the lock'
}
if ($InstallBuildTools) {
    & wsl -d $Distribution -u root -- bash -lc 'apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y build-essential clang lld git curl unzip python3 gcc-mingw-w64-i686'
    if ($LASTEXITCODE) { throw 'Build tool installation failed' }
}
Write-Host 'Verified SDK and official shadPS4 ready. Fetch pinned sources with tools/fetch_sources.py in WSL.'
