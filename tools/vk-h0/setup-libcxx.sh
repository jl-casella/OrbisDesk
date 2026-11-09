#!/bin/bash
# H0 step 1: the DolphinPS4 toolchain recipe (upstream/DolphinPS4/toolchain) on our OpenOrbis
# SDK and clang 19: libc-overlay and libc++/libc++abi 21.1.6 into ~/vk-h0/sysroot.
set -euo pipefail
ORBISDESK_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
H=~/vk-h0
P=${ORBISDESK_ROOT}
mkdir -p $H/src
# CR-free copy of the DolphinPS4 tree (scripts are CRLF on Windows)
rm -rf $H/dolphin && mkdir -p $H/dolphin
cp -r $P/upstream/DolphinPS4/{toolchain,port,probe-vk,patches,scripts,sce_sys} $H/dolphin/
find $H/dolphin -type f \( -name "*.sh" -o -name "*.c" -o -name "*.cpp" -o -name "*.h" -o -name "*.S" -o -name "*.cmake" -o -name "*.x" -o -name "*.patch" -o -name "*.txt" -o -name "*.vert" -o -name "*.frag" -o -path "*/bin/*" \) -exec sed -i 's/\r$//' {} +
chmod +x $H/dolphin/toolchain/*.sh $H/dolphin/toolchain/bin/* $H/dolphin/scripts/*.sh
# Keep the checkout and $HOME out of __FILE__ strings and debug info.
echo "export PS4_BASE_FLAGS=\"\$PS4_BASE_FLAGS -ffile-prefix-map=$P=. -ffile-prefix-map=$H=vk-h0\"" >> $H/dolphin/toolchain/env.sh
LLVM=21.1.6
if [ ! -d $H/src/llvm-project-$LLVM.src/libcxx ]; then
  curl -sSfL "https://github.com/llvm/llvm-project/releases/download/llvmorg-$LLVM/llvm-project-$LLVM.src.tar.xz" -o $H/src/llvm.tar.xz
  sha256sum $H/src/llvm.tar.xz
  tar -xJf $H/src/llvm.tar.xz -C $H/src llvm-project-$LLVM.src/{runtimes,libcxx,libcxxabi,libunwind,libc,cmake,llvm/cmake,llvm/utils/lit,llvm/utils/llvm-lit,third-party}
fi
export PSB=$H OPENORBIS=$P/.deps/sdk/OpenOrbis/PS4Toolchain CLANG_VER=19 LLVM_LOCAL_SRC=/nonexistent
$H/dolphin/toolchain/build-libcxx.sh
