#!/bin/bash
# W086: MangoHud-Windows (github.com/Leclowndu93150/MangoHud-Windows), the community Windows
# fork of MangoHud, built as a PE64 Vulkan implicit layer with llvm-mingw. Its subprojects
# (imgui, implot, spdlog, minhook, vulkan headers) come from its Meson wraps.
set -euo pipefail
ORBISDESK_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
H=~/vk-h0
L=$H/llvm-mingw/bin
SRC=${ORBISDESK_ROOT}/.deps/vk/mangohud-win/repo
W=$H/src/mangohud-win
build=$H/build/mangohud
export PATH="$H/mesa-venv/bin:$H/host-tools/bin:$PATH"
[ -d $W ] || cp -r $SRC $W
# llvm-mingw's libc++ needs the header the fork leaves out (libstdc++ includes it indirectly)
grep -q '#include <sstream>' $W/src/fps_metrics.h || sed -i '1i #include <sstream>' $W/src/fps_metrics.h
# W094: the Vulkan layer DLL does not start the DirectX/OpenGL hook thread (src/win/main.cpp,
# MainThread: AllocConsole and kiero hooks). Only the fork's dxgi.dll proxy needs it, and that
# is not installed. Here every program runs inside explorer's process, so in W093 that thread
# opened a "MangoHud" console and an "Assertion failed" dialog (win/d3d11_hook.cpp:126) for
# explorer.exe.
grep -q 'OrbisDesk: no hook thread' $W/src/win/main.cpp || \
  sed -i 's|        CreateThread(NULL, 0, (LPTHREAD_START_ROUTINE)MainThread, NULL, 0, NULL);|        /* OrbisDesk: no hook thread for the Vulkan layer (tools/vk-h0/build-mangohud.sh) */|' $W/src/win/main.cpp
grep -c 'OrbisDesk: no hook thread' $W/src/win/main.cpp
# W096: protect shared UI globals across concurrently rendering Wine guests.
python3 ${ORBISDESK_ROOT}/tools/vk-h0/patch-mangohud-shared-process.py "$W"
python3 ${ORBISDESK_ROOT}/tools/vk-h0/patch-mangohud-teardown.py "$W"
python3 ${ORBISDESK_ROOT}/tools/vk-h0/patch-mangohud-frame-sampling.py "$W"
python3 ${ORBISDESK_ROOT}/tools/vk-h0/patch-mangohud-orbis-metrics.py "$W"
cat > $build-cross.ini <<INI
[binaries]
c = '$L/x86_64-w64-mingw32-clang'
cpp = '$L/x86_64-w64-mingw32-clang++'
ar = '$L/llvm-ar'
strip = '$L/llvm-strip'
windres = '$L/llvm-windres'
pkg-config = 'false'
sh = '/usr/bin/sh'

[properties]
needs_exe_wrapper = true

[host_machine]
system = 'windows'
cpu_family = 'x86_64'
cpu = 'x86_64'
endian = 'little'
INI
if [ "${1:-}" = setup ] || [ ! -f $build/build.ninja ]; then
  rm -rf $build
  (cd $W && meson setup $build --cross-file $build-cross.ini --buildtype=release -Dwith_nvml=disabled -Dtests=disabled 2>&1 | tail -25)
fi
if ! ninja -C "$build" > "$build.log" 2>&1; then
  tail -60 "$build.log"
  exit 1
fi
echo 'MangoHud build succeeded'
python3 - "$W" "$build" <<'PY'
import hashlib,json,pathlib,sys
source,build=map(pathlib.Path,sys.argv[1:])
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
record={'dll_sha256':sha(build/'src/libMangoHud.dll'),
        'sources':{name:sha(source/name) for name in
                   ('src/vulkan.cpp','src/notify.h','src/notify_win32.cpp','src/win/main.cpp',
                    'src/overlay.cpp','src/fps_metrics.h','src/cpu_win32.cpp',
                    'src/hud_elements.cpp','src/orbis_metrics.h','src/orbis_telemetry.h')}}
(build/'orbis-build.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
PY
find $build -maxdepth 3 -name "*.dll" -o -maxdepth 3 -name "*.json" | head
