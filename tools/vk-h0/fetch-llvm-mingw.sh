#!/bin/bash
# H4: llvm-mingw 20260922 (UCRT), the compiler prospero-win pins for its Mesa WGL/Zink build
# (upstream/prospero-win/tools/build_mesa_zink.sh), with its SHA-256 checked.
set -euo pipefail
ORBISDESK_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
H=~/vk-h0
A=llvm-mingw-20260922-ucrt-ubuntu-22.04-x86_64.tar.xz
SUM=bb7bb7654b33d5aa8712acb837c963b2e0c56352560c76105270a3268c665c21
cd ${ORBISDESK_ROOT}/.deps/vk
[ -f $A ] || curl -sSfLO https://github.com/mstorsjo/llvm-mingw/releases/download/20260922/$A
echo "$SUM  $A" | sha256sum --check
if [ ! -x $H/llvm-mingw/bin/x86_64-w64-mingw32-clang ]; then
  mkdir -p $H/llvm-mingw
  tar -xJf $A -C $H/llvm-mingw --strip-components=1
fi
$H/llvm-mingw/bin/x86_64-w64-mingw32-clang --version | head -1
