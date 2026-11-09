#!/usr/bin/env bash
set -euo pipefail
bash tools/ci/install-runner.sh
sudo apt-get install -y --no-install-recommends \
  clang clang-14 llvm-14 lld bison flex gettext autoconf automake libtool \
  gcc-mingw-w64-x86-64 g++-mingw-w64-x86-64 g++-mingw-w64-i686 \
  libfreetype6-dev libfontconfig1-dev libxrender-dev libxinerama-dev libxrandr-dev \
  libxcursor-dev libxi-dev libxcomposite-dev libxml2-dev libxslt1-dev \
  libgnutls28-dev libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libunwind-dev \
  libssl-dev libjpeg-dev libpng-dev zlib1g-dev libbz2-dev p7zip-full
python3 -m pip install --disable-pip-version-check 'Pillow==11.3.0'
dotnet --info
