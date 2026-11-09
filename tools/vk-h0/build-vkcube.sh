#!/bin/bash
# W086: vkcube from Khronos Vulkan-Tools (v1.4.335) for Windows, built with llvm-mingw against
# the Vulkan loader of build-vulkan-loader.sh. Its shaders are compiled with the host
# glslangValidator (build-glslang.sh).
set -euo pipefail
ORBISDESK_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
H=~/vk-h0
# Keep the checkout and $HOME out of __FILE__ strings and debug info.
prefix_map="-ffile-prefix-map=${ORBISDESK_ROOT}=. -ffile-prefix-map=$H=vk-h0"
TAG=v1.4.335
export PATH="$H/host-tools/bin:$PATH"
cd $H/src
[ -d Vulkan-Tools ] || git clone -q --depth 1 -b $TAG https://github.com/KhronosGroup/Vulkan-Tools.git
git -C Vulkan-Tools log -1 --format="tools %H"
cmake -G Ninja -S Vulkan-Tools -B $H/build/vk-tools -DCMAKE_TOOLCHAIN_FILE=$H/build/mingw-toolchain.cmake \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$H/vk-headers" -DVulkanHeaders_DIR=$H/vk-headers/share/cmake/VulkanHeaders \
  -DBUILD_ICD=OFF -DBUILD_VULKANINFO=OFF -DBUILD_CUBE=ON -DCUBE_WSI_SELECTION=WIN32 \
  -DCMAKE_C_FLAGS="$prefix_map" -DCMAKE_CXX_FLAGS="$prefix_map" \
  -DGLSLANG_INSTALL_DIR=$H/host-tools -DTOOLS_CODEGEN=OFF 2>&1 | tail -8
ninja -C $H/build/vk-tools 2>&1 | tail -4
find $H/build/vk-tools -name "vkcube*.exe" -exec ls -la {} \;
