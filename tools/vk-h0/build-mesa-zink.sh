#!/bin/bash
# H4 (W076): OpenGL for Windows programs. Mesa 26.0.8's WGL frontend with the Zink Gallium
# driver, built as PE64 DLLs (opengl32.dll, libgallium_wgl.dll) with llvm-mingw 20260922
# (fetch-llvm-mingw.sh; the system MinGW has no C++ compiler), as
# upstream/prospero-win/tools/build_mesa_zink.sh does with its own Mesa and llvm-mingw.
# Zink draws through vulkan-1.dll, that is winevulkan and RADV (W071-W075). The source is
# the same official tarball as RADV's, unpatched, extracted separately.
set -euo pipefail
ORBISDESK_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
H=~/vk-h0
SRC=$H/src/mesa-win
build=$H/build/mesa-zink
export PATH="$H/mesa-venv/bin:$H/host-tools/bin:$PATH"
if [ ! -f $SRC/VERSION ]; then
  mkdir -p $SRC
  tar -xJf ${ORBISDESK_ROOT}/.deps/vk/mesa-26.0.8.tar.xz -C $SRC --strip-components=1
fi
cross=$build-cross.ini
cat > $cross <<INI
[binaries]
c = '$H/llvm-mingw/bin/x86_64-w64-mingw32-clang'
cpp = '$H/llvm-mingw/bin/x86_64-w64-mingw32-clang++'
ar = '$H/llvm-mingw/bin/llvm-ar'
strip = '$H/llvm-mingw/bin/llvm-strip'
windres = '$H/llvm-mingw/bin/llvm-windres'
pkg-config = 'false'

[host_machine]
system = 'windows'
cpu_family = 'x86_64'
cpu = 'x86_64'
endian = 'little'

[properties]
needs_exe_wrapper = true
INI
if [ "${1:-}" = setup ] || [ ! -f $build/build.ninja ]; then
  rm -rf $build
  meson setup $build $SRC --cross-file $cross --wrap-mode=nofallback --buildtype=release \
    --default-library=static -Dplatforms=windows -Dgallium-drivers=zink -Dvulkan-drivers= \
    -Dopengl=true -Degl=disabled -Dgbm=disabled -Dglx=disabled -Dgles1=disabled -Dgles2=disabled \
    -Dllvm=disabled -Dzlib=disabled -Dzstd=disabled -Dshader-cache=disabled -Dxmlconfig=disabled \
    -Dexpat=disabled -Dlibunwind=disabled -Dvalgrind=disabled -Dvideo-codecs= -Dbuild-tests=false \
    -Dtools= -Dgallium-va=disabled -Dgallium-rusticl=false
fi
python3 ${ORBISDESK_ROOT}/tools/vk-h0/patch-mesa-zink.py $SRC
ninja -C $build src/gallium/targets/libgl-gdi/opengl32.dll src/gallium/targets/wgl/libgallium_wgl.dll 2>&1 | tee "$build.log"
ls -la $build/src/gallium/targets/libgl-gdi/opengl32.dll $build/src/gallium/targets/wgl/libgallium_wgl.dll 2>&1
