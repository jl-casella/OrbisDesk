[CmdletBinding()]
param(
    [ValidateRange(1,32)][int]$Jobs = 6,
    [switch]$ConfigureOnly,
    [string]$Repository = "$PSScriptRoot/../.deps/shadPS4-fork"
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path "$PSScriptRoot/..").Path
$repositoryPath = (Resolve-Path -LiteralPath $Repository).Path
$forkLock = Get-Content -Raw "$root/fork.lock.json" | ConvertFrom-Json
$revision = & git -C $repositoryPath rev-parse HEAD
$dirty = & git -C $repositoryPath status --porcelain --untracked-files=no --ignore-submodules
if ($revision -ne $forkLock.commit -or $dirty) { throw 'Fork revision is not clean or does not match fork.lock.json' }
$vswhere = "${env:ProgramFiles(x86)}/Microsoft Visual Studio/Installer/vswhere.exe"
$vs = & $vswhere -all -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Select-Object -First 1
if (-not $vs) { throw 'Visual Studio C++ build tools are not installed yet.' }
& "$vs/Common7/Tools/Launch-VsDevShell.ps1" -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
$cmake = "$vs/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe"
$ninja = "$vs/Common7/IDE/CommonExtensions/Microsoft/CMake/Ninja/ninja.exe"
if (-not (Test-Path $cmake)) { $cmake = "$root/.deps/windows-tools/cmake-4.2.3-windows-x86_64/bin/cmake.exe" }
if (-not (Test-Path $ninja)) { $ninja = "$root/.deps/windows-tools/ninja/ninja.exe" }
$clang = "$root/.deps/windows-tools/llvm-19/bin/clang-cl.exe"
foreach ($tool in @($cmake,$ninja,$clang)) { if (-not (Test-Path $tool)) { throw "Missing tool: $tool" } }
$build = Join-Path $root 'build/shadPS4-win'
New-Item -ItemType Directory -Path $build -Force | Out-Null
$python = "$root/.deps/windows-tools/python312/python.exe"
if (-not (Test-Path $python)) { throw 'Missing portable Python: run tools/bootstrap-fork-tools.ps1' }
& $cmake -S $repositoryPath -B $build -G Ninja "-DCMAKE_MAKE_PROGRAM=$ninja" "-DCMAKE_C_COMPILER=$clang" "-DCMAKE_CXX_COMPILER=$clang" "-DPython3_EXECUTABLE=$python" -DCMAKE_BUILD_TYPE=Release -DENABLE_DISCORD_RPC=OFF -DENABLE_UPDATER=OFF -DENABLE_TESTS=OFF 2>&1 | Tee-Object "$build/configure.log"
if ($LASTEXITCODE) { throw 'shadPS4 configure failed; see build/shadPS4-win/configure.log' }
if (-not $ConfigureOnly) {
    & $cmake --build $build --target shadps4 --parallel $Jobs 2>&1 | Tee-Object "$build/build.log"
    if ($LASTEXITCODE) { throw 'shadPS4 build failed; see build/shadPS4-win/build.log' }
    $binary = Join-Path $build 'shadPS4.exe'
    $manifest = [ordered]@{
        schema_version=1; base_commit=$forkLock.base_commit; commit=$revision
        patches=$forkLock.patches
        executable_sha256=(Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash.ToLowerInvariant()
        compiler=(& $clang --version | Select-Object -First 1)
        cmake=(& $cmake --version | Select-Object -First 1)
        flags=@('Release','ENABLE_DISCORD_RPC=OFF','ENABLE_UPDATER=OFF','ENABLE_TESTS=OFF')
        submodules=@(& git -C $repositoryPath submodule status --recursive)
    }
    $manifest | ConvertTo-Json -Depth 10 | Set-Content "$build/build-manifest.json" -Encoding utf8
}
