#!/bin/bash
# H0: host glslangValidator for Mesa's internal shaders, from the glslang copy in shadPS4.
set -euo pipefail
ORBISDESK_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
H=~/vk-h0
rm -rf $H/src/glslang && cp -r ${ORBISDESK_ROOT}/.deps/shadPS4-fork/externals/glslang $H/src/glslang
cmake -G Ninja -S $H/src/glslang -B $H/build/glslang -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=$H/host-tools \
  -DENABLE_OPT=OFF -DGLSLANG_TESTS=OFF -DENABLE_GLSLANG_BINARIES=ON -DBUILD_EXTERNAL=OFF >/dev/null
ninja -C $H/build/glslang install 2>&1 | tail -2
$H/host-tools/bin/glslangValidator --version | head -2
