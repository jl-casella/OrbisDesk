#!/bin/bash
# W086: the Khronos Vulkan loader (vulkan-1.dll) for Windows, built with llvm-mingw. Wine's own
# vulkan-1.dll forwards to winevulkan and loads no layers; MangoHud-Windows is an implicit
# layer that this loader loads (HKLM\SOFTWARE\Khronos\Vulkan\ImplicitLayers). The loader
# finds winevulkan as its driver through HKLM\SOFTWARE\Khronos\Vulkan\Drivers.
# Tag v1.4.335, the Vulkan version RADV reports here.
# W088: built with WIN32 defined, as MSVC defines it: the loader sends its log to
# OutputDebugString only under that macro (loader/log.c), and MinGW defines only _WIN32.
set -euo pipefail
H=~/vk-h0
L=$H/llvm-mingw
TAG=v1.4.335
mkdir -p $H/src && cd $H/src
[ -d Vulkan-Headers ] || git clone -q --depth 1 -b $TAG https://github.com/KhronosGroup/Vulkan-Headers.git
[ -d Vulkan-Loader ] || git clone -q --depth 1 -b $TAG https://github.com/KhronosGroup/Vulkan-Loader.git
git -C Vulkan-Headers log -1 --format="headers %H"; git -C Vulkan-Loader log -1 --format="loader %H"
cmake -G Ninja -S Vulkan-Headers -B $H/build/vk-headers -DCMAKE_INSTALL_PREFIX=$H/vk-headers >/dev/null && ninja -C $H/build/vk-headers install >/dev/null
cat > $H/build/mingw-toolchain.cmake <<TC
set(CMAKE_SYSTEM_NAME Windows)
set(CMAKE_SYSTEM_PROCESSOR x86_64)
set(CMAKE_C_COMPILER $L/bin/x86_64-w64-mingw32-clang)
set(CMAKE_CXX_COMPILER $L/bin/x86_64-w64-mingw32-clang++)
set(CMAKE_RC_COMPILER $L/bin/llvm-windres)
set(CMAKE_ASM_MASM_COMPILER $L/bin/llvm-ml)
set(CMAKE_FIND_ROOT_PATH $L/x86_64-w64-mingw32)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
TC
cmake -G Ninja -S Vulkan-Loader -B $H/build/vk-loader -DCMAKE_TOOLCHAIN_FILE=$H/build/mingw-toolchain.cmake \
  -DCMAKE_BUILD_TYPE=Release -DVulkanHeaders_DIR=$H/vk-headers/share/cmake/VulkanHeaders \
  -DCMAKE_C_FLAGS=-DWIN32 -DCMAKE_PREFIX_PATH=$H/vk-headers -DUSE_MASM=OFF -DBUILD_TESTS=OFF 2>&1 | tail -5
ninja -C $H/build/vk-loader 2>&1 | tail -3
find $H/build/vk-loader -name "vulkan-1.dll" -exec ls -la {} \;
