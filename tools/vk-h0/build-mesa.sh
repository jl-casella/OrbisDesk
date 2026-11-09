#!/bin/bash
# H0 step 2: Mesa 26.0.8 RADV for the PS4 as upstream/DolphinPS4/scripts/build-mesa.sh does it
# (patches/mesa-ps4.patch, port/mesa/ac_ps4_drm.c, static, no LLVM, no WSI), with our
# OpenOrbis SDK and clang 19 in place of PacBrew's and clang 21.
set -euo pipefail
ORBISDESK_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
H=~/vk-h0
OPENORBIS=${ORBISDESK_ROOT}/.deps/sdk/OpenOrbis/PS4Toolchain
SYSROOT=$H/sysroot
MESA=$H/src/mesa
build=$H/build/mesa
# VARIANT=wine (W070, H1): for Wine's ELF, whose sysconf is the SDK libc's (musl numbering,
# so no unistd.h overlay) and whose pthread_once would be the kernel's, which writes 16 bytes
# into the 4-byte pthread_once_t (DolphinPS4 port/ps4_runtime.cpp): Mesa calls
# pw_vk_pthread_once (native/wine_vk_runtime.c) instead.
overlay=$SYSROOT/libc-overlay
extra=""
TARBALL=${ORBISDESK_ROOT}/.deps/vk/mesa-26.0.8.tar.xz
# the PS4 port's Mesa patches, winsys and header overlay: DolphinPS4's for G001
D=$H/dolphin
port=$D
patches="$D/patches/mesa-ps4.patch"
winsys_paths=""
if [ "${VARIANT:-}" = wine ]; then
  build=$H/build/mesa-wine
  overlay=$SYSROOT/libc-overlay-wine
  rm -rf $overlay && cp -r $SYSROOT/libc-overlay $overlay && rm -f $overlay/unistd.h
  extra=", '-Dpthread_once=pw_vk_pthread_once'"
  # W081: Crema's, the most developed (upstream/Crema/patches/BASE.txt: DolphinPS4's Mesa
  # 26.0.8 + patches/mesa-ps4.patch + patches/mesa-ps4-aligned-vertex-fetch.patch, and its
  # port/mesa/ac_ps4_drm.c, which among other things frees a buffer only once the GPU has
  # finished with it). W080: glxgears through Zink lost parts of its gears from frame to frame.
  # Its own source tree, as the patches differ; its log files go under /data/orbisdesk/gpu.
  MESA=$H/src/mesa-crema
  port=$H/crema
  rm -rf $port && mkdir -p $port
  cp -r ${ORBISDESK_ROOT}/upstream/Crema/{patches,port} $port/
  find $port -type f -exec sed -i 's/\r$//' {} +
  patches="$port/patches/mesa-ps4.patch $port/patches/mesa-ps4-aligned-vertex-fetch.patch"
  winsys_paths="s#/data/Crema/gpu#/data/orbisdesk/gpu#g"
fi
if [ ! -f $MESA/VERSION ]; then
  mkdir -p $MESA && tar -xJf $TARBALL -C $MESA --strip-components=1
fi
export PATH="$H/mesa-venv/bin:$H/host-tools/bin:$PATH"
if [ ! -f $MESA/.ps4-patched ]; then
  for patch_file in $patches; do (cd $MESA && patch -p1 --quiet < $patch_file); done
  touch $MESA/.ps4-patched
fi
python3 ${ORBISDESK_ROOT}/tools/vk-h0/fix-mesa-detect.py $MESA
tar -xJf $TARBALL -C $MESA --strip-components=1 mesa-26.0.8/src/vulkan/wsi/wsi_common.c mesa-26.0.8/src/vulkan/wsi/wsi_common_headless.c mesa-26.0.8/src/amd/vulkan/radv_wsi.h
python3 ${ORBISDESK_ROOT}/tools/vk-h0/patch-mesa-wsi.py $MESA
sed -e "${winsys_paths:-s#^##}" $port/port/mesa/ac_ps4_drm.c > $MESA/src/amd/common/ac_ps4_drm.c
if [ "${VARIANT:-}" = wine ]; then
  python3 ${ORBISDESK_ROOT}/tools/vk-h0/patch-crema-telemetry.py "$MESA/src/amd/common/ac_ps4_drm.c"
  # alpha-1: the winsys log follows OrbisDesk's trace switch, each line once (W299)
  python3 ${ORBISDESK_ROOT}/tools/vk-h0/patch-crema-traces.py "$MESA/src/amd/common/ac_ps4_drm.c"
  # W126: VK_EXT_map_memory_placed for Wine's 32-bit programs (DXVK x86)
  python3 ${ORBISDESK_ROOT}/tools/vk-h0/patch-mesa-placed.py "$MESA"
fi
pc=$H/mesa-pkgconfig; mkdir -p $pc
cat > $pc/libdrm_amdgpu.pc <<PC
Name: libdrm_amdgpu
Description: libdrm headers only (PS4 has no DRM)
Version: 2.4.125
Cflags: -I$H/src/libdrm -I$H/src/libdrm/include/drm -I$H/src/libdrm/amdgpu
Libs:
PC
flags="'-target', 'x86_64-pc-freebsd12-elf', '-D_GNU_SOURCE', '-D__PS4__', '-D__OPENORBIS__',
  '-D__ORBIS__', '-DPS4', '-D__BSD_VISIBLE', '-D_BSD_SOURCE', '-fPIC', '-funwind-tables',
  '-march=btver2', '-isysroot', '$OPENORBIS', '-isystem', '$overlay',
  '-isystem', '$port/port/mesa-overlay', '-I$H/src/libdrm', '-I$H/src/libdrm/include/drm',
  '-isystem', '$OPENORBIS/include', '-I$OPENORBIS/usr/include'$extra"
link="'-fuse-ld=lld', '-nostdlib', '-Wl,-m,elf_x86_64', '-Wl,-pie',
  '-Wl,--eh-frame-hdr', '-Wl,--script,$OPENORBIS/link.x', '-L$OPENORBIS/lib',
  '$OPENORBIS/lib/crt1.o', '-lkernel', '-lc', '-lclang_rt.builtins-x86_64', '-lSceLibcInternal'"
cross=$build-cross.ini
cat > $cross <<INI
[binaries]
c = 'clang-19'
cpp = 'clang++-19'
ar = 'llvm-ar-19'
strip = 'llvm-strip-19'
pkg-config = 'pkg-config'

[properties]
needs_exe_wrapper = true
pkg_config_libdir = '$pc'

[built-in options]
c_args = [$flags]
cpp_args = ['-nostdinc++', '-isystem', '$SYSROOT/include/c++/v1', $flags]
c_link_args = [$link]
cpp_link_args = [$link, '$SYSROOT/lib/libc++.a', '$SYSROOT/lib/libc++abi.a', '$OPENORBIS/lib/libunwind.a']

[host_machine]
system = 'freebsd'
cpu_family = 'x86_64'
cpu = 'x86_64'
endian = 'little'
INI
if [ "${1:-}" = setup ] || [ ! -f $build/build.ninja ]; then
  rm -rf $build
  PKG_CONFIG_LIBDIR=$pc meson setup $build $MESA --cross-file $cross \
    -Dbuildtype=release -Db_ndebug=true -Ddefault_library=static \
    -Dvulkan-drivers=amd -Dgallium-drivers= -Dplatforms= -Dllvm=disabled \
    -Damd-use-llvm=false -Dopengl=false -Dgles1=disabled -Dgles2=disabled -Dglx=disabled \
    -Degl=disabled -Dgbm=disabled -Dzstd=disabled -Dexpat=disabled -Dxmlconfig=disabled \
    -Dvalgrind=disabled -Dlibunwind=disabled -Dlmsensors=disabled -Dbuild-tests=false \
    -Dshader-cache=disabled -Dvulkan-layers= -Dtools= -Dvideo-codecs= -Dspirv-tools=disabled \
    -Dperfetto=false -Dselinux=false -Dradv-build-id=mesa-26.0.8-ps4-h0 2>&1 | tail -25
fi
libs=(src/amd/vulkan/libvulkan_radeon.a src/amd/addrlib/libaddrlib.a
    src/amd/common/libamd_common.a src/amd/compiler/libaco.a src/c11/impl/libmesa_util_c11.a
    src/compiler/libcompiler.a src/compiler/nir/libnir.a src/compiler/spirv/libvtn.a
    src/util/blake3/libblake3.a src/util/libmesa_util.a src/util/libmesa_util_clflush.a
    src/util/libmesa_util_clflushopt.a src/util/libmesa_util_simd.a src/util/libparson.a
    src/util/libxmlconfig.a src/vulkan/runtime/libvulkan_instance.a
    src/vulkan/runtime/libvulkan_runtime.a src/vulkan/util/libvulkan_util.a
    src/vulkan/wsi/libvulkan_wsi.a)
ninja -C $build -k 0 "${libs[@]}" > $build.log 2>&1
ls -la $build/src/amd/vulkan/libvulkan_radeon.a
