#!/bin/bash
# W244: MangoHud-Windows for 32-bit programs (syswow64), from the same tree as the x64 build (W086,
# build-mangohud.sh: the fork at .deps/vk/mangohud-win/repo with W094-W112's Orbis patches, its subprojects
# from Meson's packagecache), with llvm-mingw's i686 toolchain, in its own build directory. The x64 tree is
# only read: run build-mangohud.sh first, which copies and patches it. It is copied to mangohud-win-i386,
# where one i386-only fix is made (ADL's allocation callback type, below).
set -euo pipefail
ORBISDESK_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
H=~/vk-h0
# Keep the checkout and $HOME out of __FILE__ strings and debug info.
prefix_map="'-ffile-prefix-map=${ORBISDESK_ROOT}=.', '-ffile-prefix-map=$H=vk-h0'"
L=$H/llvm-mingw/bin
X=$H/src/mangohud-win
W=$H/src/mangohud-win-i386
build=$H/build/mangohud-i386
export PATH="$H/mesa-venv/bin:$H/host-tools/bin:$PATH"
[ -d $X ] || { echo 'run build-mangohud.sh first'; exit 1; }
# the i386 copy, made again from the x64 tree each time
rm -rf $W && cp -a $X $W
# the Orbis patches the x64 build applies (build-mangohud.sh), checked, not applied again
for check in 'src/win/main.cpp:OrbisDesk: no hook thread' 'src/vulkan.cpp:OrbisDesk W096: shared-process overlay lock.' \
             'src/vulkan.cpp:OrbisDesk W099: join outside the UI lock.' 'src/overlay.cpp:OrbisDesk W102: sample on the frame thread' \
             'src/fps_metrics.h:OrbisDesk W102: calculate on the frame thread' 'src/fps_metrics.h:#include <sstream>'; do
  file=${check%%:*}; marker=${check#*:}
  # or its historical spelling, in a working copy patched before the rename (tools/project_brand.py normalize_marker)
  grep -qF "$marker" "$W/$file" || grep -qF "${marker/OrbisDesk/Orbis-win}" "$W/$file" || { echo "missing in $file: $marker (run build-mangohud.sh)"; exit 1; }
done
[ -f $W/src/orbis_metrics.h ] && [ -f $W/src/orbis_telemetry.h ] || { echo 'Orbis metrics patch missing (run build-mangohud.sh)'; exit 1; }
# ADL's allocation callback is __stdcall (AMD's ADL SDK, ADL_MAIN_MALLOC_CALLBACK; adl.cpp defines it so); the
# fork's typedef leaves that out: the same type on x64, a compile error on x86. ADL (atiadlxx.dll) does not
# exist on the console: it only has to compile.
old='typedef int (*ADL_MAIN_CONTROL_CREATE)(void* (*callback)(int), int);'
[ "$(grep -cF "$old" $W/src/adl.h)" = 1 ] || { echo "unexpected src/adl.h: $old"; exit 1; }
sed -i 's|void\* (\*callback)(int), int);|void* (__stdcall *callback)(int), int); /* OrbisDesk i386 */|' $W/src/adl.h
grep -qF 'OrbisDesk i386' $W/src/adl.h || { echo 'adl.h fix not applied'; exit 1; }
# W250: PWHUD traces (instance, device, swapchain, first present, toggle_hud) in this copy only
python3 "$(dirname "$0")/mangohud-i386-traces.py" $W
# W250 (W249: Vice City's DXVK threads faulted at heap addresses as soon as the layer was in the chain): the fork's
# Vulkan hooks (overlay_QueueSubmit, overlay_BeginCommandBuffer, ... 15 of them) have no VKAPI_CALL; ADD_HOOK casts
# them to void *, so nothing complains, and on x64 there is one convention. On x86 the loader and DXVK call them
# __stdcall: a cdecl hook leaves the arguments on the stack and the caller returns into garbage.
[ "$(grep -cE '^static (VkResult|void) overlay_[A-Za-z]+\($' $W/src/vulkan.cpp)" = 15 ] || { echo 'unexpected hook declarations in src/vulkan.cpp'; exit 1; }
sed -i -E 's/^static (VkResult|void) (overlay_[A-Za-z]+\()$/static VKAPI_ATTR \1 VKAPI_CALL \2/' $W/src/vulkan.cpp
[ "$(grep -cE '^static VKAPI_ATTR (VkResult|void) VKAPI_CALL overlay_[A-Za-z]+\($' $W/src/vulkan.cpp)" = 15 ] || { echo 'hook convention fix not applied'; exit 1; }
cross=$build-cross.ini
old_cross=$(cat $cross 2>/dev/null || true)
cat > $build-cross.ini <<INI
[binaries]
c = '$L/i686-w64-mingw32-clang'
cpp = '$L/i686-w64-mingw32-clang++'
ar = '$L/llvm-ar'
strip = '$L/llvm-strip'
windres = '$L/i686-w64-mingw32-windres'
pkg-config = 'false'
sh = '/usr/bin/sh'

[properties]
needs_exe_wrapper = true

# W249 (W248: the loader found no "overlay_GetInstanceProcAddr" in it and left the layer out): on x86 the
# VKAPI_CALL entry points are __stdcall and were exported as "overlay_GetInstanceProcAddr@8"; the loader asks
# for the plain names the manifest gives, as on x64
[built-in options]
c_args = [$prefix_map]
cpp_args = [$prefix_map]
c_link_args = ['-Wl,--kill-at']
cpp_link_args = ['-Wl,--kill-at']

[host_machine]
system = 'windows'
cpu_family = 'x86'
cpu = 'i686'
endian = 'little'
INI
if [ "${1:-}" = setup ] || [ ! -f $build/build.ninja ] || [ "$old_cross" != "$(cat $cross)" ]; then
  rm -rf $build
  (cd $W && meson setup $build --cross-file $build-cross.ini --buildtype=release -Dwith_nvml=disabled -Dtests=disabled \
     --wrap-mode=nodownload 2>&1 | tail -25)
fi
# only the layer DLL: the fork's standalone MangoHud.exe (src/app/mangohud_overlay.cpp) passes a lambda to
# EnumWindows, which does not convert to the stdcall callback on x86, and is not used here
if ! ninja -C "$build" src/libMangoHud.dll > "$build.log" 2>&1; then
  tail -60 "$build.log"
  exit 1
fi
objdump -f $build/src/libMangoHud.dll | grep -q 'file format pei-i386' || { echo 'not an i386 DLL'; exit 1; }
# W249: the layer's entry points under the names the manifest gives (objdump's output to a file first: with
# pipefail, grep -q ending early would fail the pipe)
objdump -p $build/src/libMangoHud.dll > $build/exports.txt
grep -q '\] overlay_GetInstanceProcAddr$' $build/exports.txt || { echo 'overlay_GetInstanceProcAddr not exported plain'; exit 1; }
echo 'MangoHud i386 build succeeded'
python3 - "$W" "$build" <<'PY'
import hashlib,json,pathlib,sys
source,build=map(pathlib.Path,sys.argv[1:])
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
record={'dll_sha256':sha(build/'src/libMangoHud.dll'),'json':'MangoHud.x86.json','arch':'i386',
        'sources':{name:sha(source/name) for name in
                   ('src/vulkan.cpp','src/notify.h','src/notify_win32.cpp','src/win/main.cpp',
                    'src/overlay.cpp','src/fps_metrics.h','src/cpu_win32.cpp',
                    'src/hud_elements.cpp','src/orbis_metrics.h','src/orbis_telemetry.h','src/adl.h','src/keybinds.cpp')}}
(build/'orbis-build.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
PY
ls -la $build/src/libMangoHud.dll $build/src/MangoHud.x86.json
