#!/bin/bash
# W244: the Khronos Vulkan loader (vulkan-1.dll) for 32-bit programs (syswow64), the same tag and build as
# build-vulkan-loader.sh's x64 one (W086, v1.4.335), with llvm-mingw's i686 toolchain. Wine's builtin
# vulkan-1 loads no layers; this one loads MangoHud's i386 layer (build-mangohud-i386.sh) through
# HKLM\Software\Wow6432Node\Khronos\Vulkan\ImplicitLayers. Run build-vulkan-loader.sh first (sources, headers).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
H=~/vk-h0
L=$H/llvm-mingw
B=$H/build/vk-loader-i386
TAG=v1.4.335
cd $H/src
[ -d Vulkan-Loader ] && [ -d $H/vk-headers ] || { echo 'run build-vulkan-loader.sh first'; exit 1; }
ROOT=$(cd "$HERE/../.." && pwd)
EXPECTED=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["repositories"]["Vulkan-Loader"]["commit"])' "$ROOT/dependencies.lock.json")
[ "$(git -C Vulkan-Loader rev-parse HEAD)" = "$EXPECTED" ] || { echo 'Vulkan-Loader differs from dependencies.lock.json'; exit 1; }
git -C Vulkan-Loader log -1 --format="loader %H"
cat > $H/build/mingw-toolchain-i686.cmake <<TC
set(CMAKE_SYSTEM_NAME Windows)
set(CMAKE_SYSTEM_PROCESSOR x86)
set(CMAKE_C_COMPILER $L/bin/i686-w64-mingw32-clang)
set(CMAKE_CXX_COMPILER $L/bin/i686-w64-mingw32-clang++)
set(CMAKE_RC_COMPILER $L/bin/i686-w64-mingw32-windres)
set(CMAKE_FIND_ROOT_PATH $L/i686-w64-mingw32)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
TC
rm -rf $B
# W287 (W257/W258: in explorer's 32-bit world the loader's DXGI factory created Wine's dxgi, which created a wined3d
# adapter, which went through this loader again): built from a copy whose loader_windows.c makes no DXGI factory
S=$H/build/vk-loader-i386-src
rm -rf $S
cp -a Vulkan-Loader $S
python3 $HERE/patch-vulkan-loader-i386-nodxgi.py $S/loader/loader_windows.c
cmake -G Ninja -S $S -B $B -DCMAKE_TOOLCHAIN_FILE=$H/build/mingw-toolchain-i686.cmake \
  -DCMAKE_BUILD_TYPE=Release -DVulkanHeaders_DIR=$H/vk-headers/share/cmake/VulkanHeaders \
  -DCMAKE_C_FLAGS=-DWIN32 -DCMAKE_PREFIX_PATH=$H/vk-headers -DUSE_MASM=OFF -DBUILD_TESTS=OFF 2>&1 | tail -5
ninja -C $B 2>&1 | tail -3
dll=$B/loader/vulkan-1.dll
objdump -f $dll | grep -q 'file format pei-i386' || { echo "not an i386 DLL: $dll"; exit 1; }
python3 - $dll <<'PY'
import hashlib,json,pathlib,subprocess,sys
dll=pathlib.Path(sys.argv[1])
commit=subprocess.check_output(['git','-C',str(pathlib.Path.home()/'vk-h0/src/Vulkan-Loader'),'rev-parse','HEAD'],text=True).strip()
record={'dll_sha256':hashlib.sha256(dll.read_bytes()).hexdigest(),'tag':'v1.4.335','commit':commit,'arch':'i386',
        'patched':'W287: no DXGI factory (patch-vulkan-loader-i386-nodxgi.py)'}
(dll.parent.parent/'orbis-build.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
PY
