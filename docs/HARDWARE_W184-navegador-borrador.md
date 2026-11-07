<a id="w184-pale-moon-sin-d3d11-fase-9-borrador"></a>


# W184: Pale Moon without D3D11 (phase 9, draft)

[English](HARDWARE_W184-navegador-borrador.md) | [Español](HARDWARE_W184-navegador-borrador-es.md)

Eraser of the browser side session, to join `HARDWARE_W184.md`. Base W183. None of this was tested on the console.

<a id="qué-pasó-en-w183"></a>


## What happened in W183

Report: `reports/wine-hardware-w183/physical/20261103T232154Z/`. The relaunch works: run- 0004 and run- 0006 rewind, and run- 0005 and run- 0007 run `palemoon.exe` as a title. Pale Moon falls to 13 s more or less and the app returns to the desktop.

- **run- 0005 (first profile start):**
  - The main thread loads `opengl32`, the `dxgi` building of Wine and then the `d3d11.dll` of DXVK (W124).
  - DXVK tell `D3D11InternalCreateDevice: Adapter is not a DXVK adapter` and create your own device Vulkan. Then it gives `DxvkMemoryAllocator: Memory allocation failed` (4096 bytes, memory types 0,2,3,5, piles of 1024 and 2048 MiB almost empty).
  - Access failure in `7F8941618`: `d3d11.dll` (DXVK), displacement `0xe1618`.
  - Then there is a breakpoint in `7FA464E69`: `xul.dll` of Pale Moon, displacement `0x734e69` (Mozilla's abort). It ends with `0x80000003`.
- **run- 0007 (second start):**
  - Pale Moon delete `d3d11layers.guard` from the profile. It is your guard against D3D11 failures, which was left from the previous failure, so this time you don't use D3D11.
  - Then, `map_view anon mmap error Invalid argument, size 0x810000, unix_prot 0x3`: a reservation of 8 MB reading and writing that the console rejected.
  - `xul.dll` read the address `0x80` in `7F9FD958E` (`xul.dll`, displacement `0x2a958e` and ends with `0xc0000005`.
  - It's a memory problem other than that of D3D11. It belongs to the work of the main session in `virtual.c` (the reserve of 1 GB of W180 was without permits; This is 8 MB with reading and writing).

**Why Pale Moon created a device D3D11.** The `user.js` of W177 - W183 asked `layers.acceleration.disabled`. Pale Moon 35 (UXP) has no such preference. Yours is `layers.acceleration.enabled` (the names are in `xul.dll`). There is no `layers.prefer-d3d9`. Pale Moon ignored both and left the composition for GPU on.

<a id="cambio"></a>


## Change

|File|What are you doing?|
|---|---|
| `fixtures/browser/palemoon-user.js` |`layers.acceleration.enabled=false` instead of `layers.acceleration.disabled`. Take out `layers.prefer-d3d9`. Add `webgl.disable-angle=true` (ANGLE also uses D3D11). They follow `gfx.direct2d.disabled`, `webgl.disabled` and `media.hardware-video-decoding.enabled=false`. All these preferences are in `xul.dll`.|
|`tools/build-wine-hardware.py` (`user.reg`, pending the OK of the main session)|`[Software\Wine\AppDefaults\palemoon.exe\DllOverrides]` `"d3d11"=""` and `"d3d10core"=""`: if any Pale Moon still requests D3D11, the load fails clean and does not reach DXVK. `dxgi` remains the building (Pale Moon uses it to read the adapter). `d3d9` does not touch: `xul.dll` it matters in a static way.|

The `user.js` is from the build, so the rise replaces it. What Pale Moon wrote in the profile (`prefs.js`, guards) remains.

<a id="para-después-vulkan-en-un-título-de-64-bits-relanzado"></a>


## For later: Vulkan in a 64 bit retracted title

In run- 0005, DXVK could not reserve 4 KB of memory Vulkan in a process of 64 bits. The 32 bit relegated programs do use DXVK and wined3d over Vulkan. It was not investigated in W184. It is recorded for when Pale Moon (or a game of 64 bits) use D3D11 in your own process.

<a id="construcción-orden"></a>


## Construction (order)

1. `python3 tools/build-wine-hardware.py` (copy the new `user.js` and, with the OK, write the block `DllOverrides`)
2. `python3 -I tools/check-web-closure.py build/wine-hardware-w184/runtime`

<a id="prueba-física"></a>


## Physical test

1. **Open Pale Moon:**
   - The log does not have to appear `d3d11.dll` loaded by Pale Moon or any line of DXVK (`info:  DXVK: v2.7.1`.
   - The local page is expected with `es5-ok`, `es2020-ok` and `canvas-ok`.
2. **If you return `map_view anon mmap error Invalid argument`** (as in run- 0007), the failure is of memory and not of graphics: it is left for the arrangement of `virtual.c`.
3. **Close Pale Moon:** you have to return the desk.

<a id="no-verificado"></a>


## Not verified

- Nothing was tested on the console.
- It is not confirmed that, with the composition by GPU off, Pale Moon 35 does not create a device D3D11 for anything else (reading the adapter, image decoding). That's what the `DllOverrides` is for.
