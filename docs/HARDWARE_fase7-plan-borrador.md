<a id="fase-7-del-plan-pe32-dxgi-de-dxvk-por-programa-y-winecfg-plan-borrador"></a>


# Phase 7 of the plan PE32: dxgi of DXVK per program and winecfg (plan, draft)

[English](HARDWARE_fase7-plan-borrador.md) | [Español](HARDWARE_fase7-plan-borrador-es.md)

Dispatch of the side session. There's no building yet. The number is assigned by the main session.

<a id="punto-de-partida"></a>


## Point of departure

- W124 installed d3d8, d3d9, d3d10core and d3d11 of DXVK 2.7.1 in `system32` and `syswow64`, but **not** your `dxgi.dll`. The `dxgi` building of Wine remains that of the 64 bit desk: the Khronos loader verifies the drivers of the register with a factory DXGI, and MangoHud asks the GPU (W087, with `renderer=no3d`).
- The `d3d11` of DXVK needs the `dxgi` of DXVK. So today D3D10/11 they don't work, and W124 left it for phase 7 ("per program, winecfg").
- `winecfg.exe` It's not in the prefix. It is compiled in the fixed tree of Wine for x86_64 e i386.

<a id="restricción-que-define-el-plan"></a>


## Restriction that defines the plan

- **64 bit:** the 64 bit programs run as guests within the scanning process (W052). That process already has the `dxgi` builtin loaded, and Wine does not have two `dxgi.dll` modules in the same process. A D3D11 program of 64 bits cannot use `dxgi` of DXVK as a guest.
- **32 bits:** each program reels the app and runs in its own process (W116, WoW64). There `vulkan-1` is the Wine building, without Khronos loader and without verification by DXGI: it is the standard combination Wine + DXVK.

<a id="paso-1-d3d1011-en-32-bits"></a>


## Step 1: D3D10/11 in 32 bit

- `tools/build-wine-hardware.py`:
  - the `dxgi.dll` x32 of DXVK goes to `syswow64`;
  - `system32` continues with `dxgi` of Wine;
  - override `"dxgi"="native,builtin"` in `user.reg`. In 64 bits find the building of Wine in `system32` and use it; in 32 bits use the DXVK. The log confirms it with `trace+loaddll`, which is already active.
- New fixture `fixtures/win32/d3d11test.c` → `C:\orbis\d3d11test32.exe`:
  - window, `D3D11CreateDeviceAndSwapChain`, description of the adapter DXGI and level of features;
  - ~ 5 s of `ClearRenderTargetView` with a changing color;
  - `d3d11-result.txt` with the HRESULT of each step, the tables and the ms.
  - It's a minimum case, just like `d3d9test`: it doesn't prove shakers.
- Try the console:
  - `d3d11test32.exe`;
  - regression: `d3d9test32.exe`, `ddraw7test32.exe` and SuperMarioKart (wined3d/ddraw does not use `dxgi`, but we have to check it out).

<a id="paso-2-winecfg"></a>

## Step 2: winecfg

- `tools/stage-wine-programs.py`: adds `winecfg` (x86_64) with its import closure, as does regedit.
- `tools/make-start-menu.py`: input "Wine Configuration" in System Tools.
- Use:
  - tab Applications → add the exe;
  - The Libraries → tab for example `dxgi` = building, for a program of 32 bits that you should use `d3d11` of Wine instead of DXVK.
  - It remains in `HKCU\Software\Wine\AppDefaults\<exe>\DllOverrides`, which the loader reads in the process proper to each program of 32 bits.
- **Let the build not erase what winecfg keeps.**
  - `user.reg` is in `runtime_files`, and `upload-hardware.py` it rises every time the console hash is different.
  - In W108 - W112, `system.reg` and `user.reg` they always appear as `uploaded` and `userdef.reg` as `present`: Wine rewrites the record on the console (the wineserver keeps every 30 (s).
  - Today each climb would step on the user's overrides.
  - It was chosen **to merge by uploading** instead of writing the file only the first time. If it was written only once, the changes in the record of the following buildings (for example, the `dxgi` override of this step) would never reach the console.
  - How it works: `upload-hardware.py` lower the `user.reg` of the console. The blocks whose key starts with `Software\\Wine\\AppDefaults` leave the console; everything else, from the `user.reg` of the building. A block of AppDefaults that only has the build is added.
  - You get the result up and check it with your own hash. The two hashes remain in the search of the rise and how many blocks were kept.
  - If there is no `user.reg` on the console, or it does not start with `WINE REGISTRY Version 2`, then the build up as it is and scores it. The start preflight (`native/wine_prefix_probe.c`) only looks at that header.
  - The general loop of `runtime_files` jumps `user.reg`, so that it will not be raised again with the hash of the build after the fusion.
  - Limit: only programme adjustments are retained. The winecfg globals (the "Default settings" entry) remain from the build.
  - Limit: you have to close the app before installing. If it is open during the rise, Wine rewrite `user.reg` within the following 30 and step on the merged file with what you have in memory. That loses the change in the build, not the user's.
- Test: open winecfg as a guest, go through the eyelashes and save an override. Audio and graphic tabs consult devices; if any failure, it is recorded and reported, without hiding it.

<a id="paso-3-después-aparte-d3d1011-en-64-bits"></a>


## Step 3 (then apart): D3D10/11 in 64 bits

- It requires that the program does not run as a guest. The idea is that `ps4_guest_launch` (`tools/build-guest-hw.py`) look `AppDefaults\<exe>\DllOverrides\dxgi` and, if it is native, use the relaunch as with those of 32 bits.
- Open risk: in this process of 64 bit itself follows the Khronos loader, which it loads `dxgi` to verify drivers. With the `dxgi` of DXVK that can go back into `vkCreateInstance` since DXVK. You have to try it on a `d3d11test64.exe` before you're good.

<a id="archivos"></a>


## Files

|File| Paso |Share with the main session|
|---|---|---|
| `tools/build-wine-hardware.py` | 1 |yes (block DXVK, overrides, fixtures)|
| `fixtures/win32/d3d11test.c` | 1 |no (new)|
| `tools/stage-wine-programs.py` | 2 |is not verified by hash; We have to re- run it.|
| `tools/make-start-menu.py` | 2 |yes (output the build copy - wine -hardware)|
| `tools/upload-hardware.py` | 2 |yes (fusion of `user.reg`)|
| `tools/build-guest-hw.py` | 3 |yes|

`joy.cpl`, which is also part of the 7 phase, remains for after xinput (phase 5).
