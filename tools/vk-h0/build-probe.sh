#!/bin/bash
# H0 step 3: zlib (zlib-ng compat, from shadPS4's copy) and the Vulkan probe (native/vk_probe),
# linked as upstream/DolphinPS4/toolchain/ps4-love-style.cmake links it (whole-archive RADV,
# malloc/mmap/clock/pthread_once wraps, init_array and .data.* link script fix), with our SDK.
set -euo pipefail
H=~/vk-h0
P=/mnt/c/Users/JoseCasella/DEV/Codex/PS4
OO=$P/.deps/sdk/OpenOrbis/PS4Toolchain
D=$H/dolphin
S=$H/sysroot
M=$H/build/mesa
B=$H/build/probe; mkdir -p $B
CFLAGS="--target=x86_64-pc-freebsd12-elf -D_GNU_SOURCE -D__PS4__ -D__OPENORBIS__ -D__ORBIS__ -DPS4 -D__BSD_VISIBLE -D_BSD_SOURCE -fPIC -funwind-tables -march=btver2 -O2 -isysroot $OO -isystem $S/libc-overlay -isystem $OO/include -I$OO/usr/include"
CXXFLAGS="-nostdinc++ -isystem $S/include/c++/v1 $CFLAGS -std=c++23"
if [ ! -f $S/lib/libz.a ]; then
  rm -rf $H/src/zlib-ng && cp -r $P/.deps/shadPS4-fork/externals/zlib-ng $H/src/zlib-ng
  cmake -G Ninja -S $H/src/zlib-ng -B $H/build/zlib -DCMAKE_BUILD_TYPE=Release -DCMAKE_SYSTEM_NAME=FreeBSD \
    -DCMAKE_C_COMPILER=clang-19 -DCMAKE_C_FLAGS="$CFLAGS" -DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY \
    -DCMAKE_AR=$(command -v llvm-ar-19) -DCMAKE_RANLIB=$(command -v llvm-ranlib-19) \
    -DZLIB_COMPAT=ON -DBUILD_SHARED_LIBS=OFF -DZLIB_ENABLE_TESTS=OFF -DZLIBNG_ENABLE_TESTS=OFF -DWITH_GTEST=OFF \
    -DCMAKE_INSTALL_PREFIX=$S >/dev/null
  ninja -C $H/build/zlib install >/dev/null
fi
ls $S/lib/libz.a
objs=()
cc() { clang-19 $CFLAGS -Wall -Wno-format -I$H/src/mesa/include -c "$1" -o "$2"; objs+=("$2"); }
cxx() { clang++-19 $CXXFLAGS -c "$1" -o "$2"; objs+=("$2"); }
cc $P/native/vk_probe/main.c $B/main.o
cxx $D/port/ps4_runtime.cpp $B/ps4_runtime.o
cc $D/port/ps4_dlmalloc.c $B/ps4_dlmalloc.o
cxx $D/port/ps4_crashlog.cpp $B/ps4_crashlog.o
cxx $D/port/ps4_sampler.cpp $B/ps4_sampler.o
cc $D/port/ps4_string.c $B/ps4_string.o
cc $P/native/vk_probe/jit_unavailable.c $B/jit_unavailable.o
# crt1.o with an explicit 64 MiB libc heap (toolchain/patch-crt1.sh)
python3 - $B/heap.bin 64 <<'PY'
import struct, sys
open(sys.argv[1], "wb").write(struct.pack("<IIQII", 1, 0, int(sys.argv[2]) << 20, 0, 0) + bytes(0x28 - 24))
PY
llvm-objcopy-19 --update-section .data=$B/heap.bin $OO/lib/crt1.o $B/crt1.o
# link script: prioritized .init_array and per-symbol .data/.tdata/.tbss sections
sed -e 's/\*(\.init_array);/KEEP(*(SORT_BY_INIT_PRIORITY(.init_array.*))); KEEP(*(.init_array));/' \
    -e 's/\*(\.data)/*(.data .data.*)/' -e 's/\*(\.tdata)/*(.tdata .tdata.*)/' -e 's/\*(\.tbss)/*(.tbss .tbss.*)/' \
    $OO/link.x > $B/link.x
mesa=(src/amd/vulkan/libvulkan_radeon.a src/amd/common/libamd_common.a
  src/amd/compiler/libaco.a src/amd/addrlib/libaddrlib.a src/vulkan/util/libvulkan_util.a
  src/compiler/spirv/libvtn.a src/compiler/nir/libnir.a src/compiler/libcompiler.a
  src/util/libxmlconfig.a src/util/libmesa_util.a src/util/libmesa_util_simd.a
  src/util/libmesa_util_clflush.a src/util/libmesa_util_clflushopt.a src/util/libparson.a
  src/util/blake3/libblake3.a src/c11/impl/libmesa_util_c11.a)
wraps=()
for fn in malloc free calloc realloc memalign __memalign pthread_once mmap clock_gettime; do wraps+=(--wrap=$fn); done
ld.lld-19 -m elf_x86_64 -pie --eh-frame-hdr --script $B/link.x -o $B/vk_probe.elf "${wraps[@]}" \
  $B/crt1.o "${objs[@]}" --whole-archive "${mesa[@]/#/$M/}" --no-whole-archive \
  $S/lib/libz.a $S/lib/libc++.a $S/lib/libc++abi.a $OO/lib/libunwind.a \
  -L$OO/lib -lSceSysmodule -lSceSystemService -lSceUserService -lSceVideoOut -lpthread \
  -lkernel -lc -lSceLibcInternal $OO/lib/libclang_rt.builtins-x86_64.a 2>&1 | head -40
ls -la $B/vk_probe.elf
