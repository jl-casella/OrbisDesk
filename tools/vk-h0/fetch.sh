#!/bin/bash
# H0: Mesa 26.0.8 (RADV) and libdrm 2.4.125 headers, plus meson/mako/pyyaml in a venv.
set -e
cd /mnt/c/Users/JoseCasella/DEV/Codex/PS4/.deps/vk
[ -f mesa-26.0.8.tar.xz ] || curl -sSfLO https://archive.mesa3d.org/mesa-26.0.8.tar.xz
[ -f libdrm-2.4.125.tar.xz ] || curl -sSfLO https://dri.freedesktop.org/libdrm/libdrm-2.4.125.tar.xz
sha256sum mesa-26.0.8.tar.xz libdrm-2.4.125.tar.xz
# extracted on the Linux side: the Windows file system is slow for a Mesa build
mkdir -p ~/vk-h0/src && cd ~/vk-h0/src
[ -d mesa ] || { tar xf /mnt/c/Users/JoseCasella/DEV/Codex/PS4/.deps/vk/mesa-26.0.8.tar.xz && mv mesa-26.0.8 mesa; }
[ -d libdrm ] || { tar xf /mnt/c/Users/JoseCasella/DEV/Codex/PS4/.deps/vk/libdrm-2.4.125.tar.xz && mv libdrm-2.4.125 libdrm; }
cd ~/vk-h0
[ -d mesa-venv ] || python3 -m venv mesa-venv
mesa-venv/bin/pip install -q meson mako pyyaml packaging 2>&1 | tail -2
mesa-venv/bin/meson --version
ls src/mesa | head -3
