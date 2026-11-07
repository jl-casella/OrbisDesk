<a id="mangohud-en-juegos-direct3d-por-dxvk-borrador-para-la-próxima-w"></a>


# MangoHud in games Direct3D by DXVK (draft for the next W)

[English](HARDWARE_W197-mangohud-dxvk-borrador.md) | [Español](HARDWARE_W197-mangohud-dxvk-borrador-es.md)

Eraser of the configuration session of Wine. The main session adds it to the document of the W in which it enters (here "W197").

<a id="qué-pasó-en-w195"></a>


## What happened in W195

- The Lost Forest (Unity, x64, Direct3D 11 by DXVK 2.7.1) He runs, but F12 doesn't show MangoHud.
- In `run-0001.log` (`reports/wine-hardware-w195/physical/20261104T112911Z`), the three times that DXVK starts says `Vulkan: Found vkGetInstanceProcAddr in winevulkan.dll`.
- MangoHud is an implicit layer of Vulkan. It loads the Khronos loader (`system32\vulkan-1.dll`, W086) when `MANGOHUD=1`, and the pitcher already puts it (`launch_arg --env=MANGOHUD=1`). Calling winevulkan directly, DXVK does not pass through the loader and the layer does not load.

<a id="la-causa"></a>


## The cause

- DXVK 2.7.1 search `vkGetInstanceProcAddr` in a fixed list: first `winevulkan.dll` and then `vulkan-1.dll` (`src/vulkan/vulkan_loader.cpp`). Use the first one you carry.
- There is no environment variable or option of `dxvk.conf` to change that order. The chains of the DLL have only `DXVK_HUD`, `DXVK_CONFIG`, `DXVK_WSI_DRIVER` and similar; None of them choose the loader.
- Disable `winevulkan` by DllOverrides does not serve: the Khronos loader loads the same `winevulkan.dll` as driver.

<a id="opciones"></a>


## Options

- **MangoHud for the loader (chosen).** In the x64 DLL from DXVK which load Vulkan (`d3d9`, `d3d11`, `dxgi`), the first name passes `winevulkan.dll` a `vulkan-1.dll`: same length, filled with zeros. Each DLL has one time the couple `winevulkan.dll\0vulkan-1.dll\0`, and the manager checks. So a game Direct3D of 64 bits goes through the loader, like vkcube, and MangoHud is loaded with the same configuration (`%APPDATA%\MangoHud\MangoHud.conf`) and the same F12 key.
- **HUD of DXVK (discarded).** `DXVK_HUD` or `dxvk.hud` in `dxvk.conf` show FPS and frame times, but DXVK 2.7.1 has no key to show or hide it: it is fixed since the game starts. In addition, it does not use the MangoHud configuration that the user already has.
- **Compile DXVK from the code with the changed order.** It gives the same result, but you need to download the code and set up mingw, meson and glslang. The change of bytes is smaller and is checked in every building.

The DLL x32 remains as they come: a program of 32 bits does not have the hhronos loader (W116).

<a id="cambio"></a>


## Change

- `tools/stage-dxvk.py` (applies `dxvk-loader-w197.patch.py` in the note folder):
  - `LOADER` and `LOADER_DLLS`: the replacement, only in `x64/d3d9.dll`, `x64/d3d11.dll` and `x64/dxgi.dll`;
  - if the couple of names does not appear exactly once, the manager stops;
  - the manifest keeps, by file, `release_sha256` (the release) and `patched`.
- `dxvk_dxgi.dll` is a copy of `x64/dxgi.dll` (W192), so it also goes through the loader.
- `tools/build-wine-hardware.py` does not change: it takes the files from the DXVK manifest and checks the stager's sha.
- Tested on a copy of the manager, with output in the scratchpad: change 3 DLL; the size of each is the same; there is no left `winevulkan` in them; the other 7 have the same sha as the release.

<a id="efectos-a-mirar"></a>


## Effects to look at

- Any 64 bit program using the d3d9 or d3d11 of DXVK load MangoHud, and the HUD is seen from the start (the configuration does not bring `no_display`). F12 hides it.
- The loader adds one more call per function of Vulkan. With the visible HUD, MangoHud draws in each `vkQueuePresentKHR`. Compare The Lost Forest's FPS with W195 (about 76).

<a id="prueba"></a>


## Test

1. The Lost Forest: the log says `Vulkan: Found vkGetInstanceProcAddr in vulkan-1.dll`, and MangoHud appears up to the left.
2. F12 hides it and shows it again.
3. FPS similar to W195.
4. vkcube with MangoHud remains the same.
