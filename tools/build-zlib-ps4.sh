#!/bin/bash
# zlib for the hardware ELF's link (tools/build-wine-hardware.py links ~/vk-h0/sysroot/lib/libz.a after
# RADV): zlib-ng in zlib-compatible mode from the pinned shadPS4 fork's externals, built for the console
# exactly as tools/vk-h0/build-probe.sh builds it. The graphics block (tools/ci/product_blocks.py) does
# not run build-probe.sh, so a clean product build makes it here; kept outside tools/vk-h0/ so the
# graphics block key does not change. Does nothing when libz.a is already there.
set -euo pipefail
ORBISDESK_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
H=~/vk-h0
OO=$ORBISDESK_ROOT/.deps/sdk/OpenOrbis/PS4Toolchain
S=$H/sysroot
SRC=$ORBISDESK_ROOT/.deps/shadPS4-fork/externals/zlib-ng
if [ -f $S/lib/libz.a ]; then ls $S/lib/libz.a; exit 0; fi
[ -f $SRC/CMakeLists.txt ] || { echo "missing $SRC (restore-dependencies.py --only shadps4-fork)"; exit 1; }
CFLAGS="--target=x86_64-pc-freebsd12-elf -D_GNU_SOURCE -D__PS4__ -D__OPENORBIS__ -D__ORBIS__ -DPS4 -D__BSD_VISIBLE -D_BSD_SOURCE -fPIC -funwind-tables -march=btver2 -O2 -isysroot $OO -isystem $S/libc-overlay -isystem $OO/include -I$OO/usr/include"
rm -rf $H/src/zlib-ng $H/build/zlib && mkdir -p $H/src && cp -r $SRC $H/src/zlib-ng
cmake -G Ninja -S $H/src/zlib-ng -B $H/build/zlib -DCMAKE_BUILD_TYPE=Release -DCMAKE_SYSTEM_NAME=FreeBSD \
  -DCMAKE_C_COMPILER=clang-19 -DCMAKE_C_FLAGS="$CFLAGS" -DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY \
  -DCMAKE_AR=$(command -v llvm-ar-19) -DCMAKE_RANLIB=$(command -v llvm-ranlib-19) \
  -DZLIB_COMPAT=ON -DBUILD_SHARED_LIBS=OFF -DZLIB_ENABLE_TESTS=OFF -DZLIBNG_ENABLE_TESTS=OFF -DWITH_GTEST=OFF \
  -DCMAKE_INSTALL_PREFIX=$S >/dev/null
ninja -C $H/build/zlib install >/dev/null
ls $S/lib/libz.a
