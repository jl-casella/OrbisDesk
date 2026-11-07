#!/usr/bin/env bash
set -euo pipefail
# GitHub-hosted Ubuntu 22.04 only. No workstation paths or console credentials.
test "$(. /etc/os-release; echo "$VERSION_CODENAME")" = jammy
sudo apt-get update -o Acquire::Retries=3 -o Acquire::http::Timeout=30
sudo apt-get install -y --no-install-recommends ca-certificates curl gnupg
curl --fail --location --retry 3 --connect-timeout 20 --max-time 120 \
  https://apt.llvm.org/llvm-snapshot.gpg.key -o /tmp/orbisdesk-llvm.asc
gpg --show-keys --with-colons /tmp/orbisdesk-llvm.asc | grep -q '6084F3CF814B57C1CF12EFD515CF4D18AF4F7421'
sudo gpg --dearmor --yes --output /usr/share/keyrings/orbisdesk-llvm.gpg /tmp/orbisdesk-llvm.asc
echo 'deb [signed-by=/usr/share/keyrings/orbisdesk-llvm.gpg] https://apt.llvm.org/jammy/ llvm-toolchain-jammy-19 main' \
  | sudo tee /etc/apt/sources.list.d/orbisdesk-llvm.list >/dev/null
sudo apt-get update -o Acquire::Retries=3 -o Acquire::https::Timeout=30
sudo apt-get install -y --no-install-recommends \
  build-essential clang-19 lld-19 llvm-19 libc++-19-dev libc++abi-19-dev \
  gcc-mingw-w64-i686 ninja-build pkg-config git unzip xvfb xauth \
  libvulkan1 mesa-vulkan-drivers libx11-dev libxext-dev libwayland-dev \
  libdecor-0-dev libxkbcommon-dev libglfw3-dev libgles2-mesa-dev libfuse2 \
  libasound2-dev libpulse-dev libopenal-dev libudev-dev libxcursor-dev \
  libxi-dev libxss-dev libxtst-dev
python3 -m pip install --disable-pip-version-check --target .deps/linux-tools 'cmake==4.2.3'
clang-19 --version
df -h .
