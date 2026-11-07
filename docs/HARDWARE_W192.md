<a id="w192-direct3d-11-de-64-bits-dentro-de-explorer"></a>


# W192: Direct3D 11 of 64 bits inside of explorer

[English](HARDWARE_W192.md) | [Español](HARDWARE_W192-es.md)

APP_VER 02.91. Base W191. The result of W191 is in `docs/HARDWARE_W191.md`.

<a id="cambios"></a>


## Changes

- **`tools/build-dxgi-hw.py`** (new): is `dxgi.dll` of 64 Wine bits with a review in `factory.c`. The method is the same as that of `build-ddraw-hw.py`: overlay, and the recipe of `make -n` only for the revised unit.
  - In `CreateSwapChainForHwnd`, a device that is not wined3d neither a tail D3D12 no longer ends in "This is not the device we're looking for." The factory loads `dxvk_dxgi.dll`, creates a factory of DXVK (`CreateDXGIFactory2`) and asks for the presentation chain.
  - DXVK 2 .x no longer offers the interface used by the Wine (`IWineDXGISwapChainFactory` factory. It's the unknown `53cb4ff0…` log of W189.
  - The faults are recorded with `PWDXGI … failed`. The first success leaves a line `PWDXGI swap chain through DXVK's dxgi`.
- **`tools/build-wine-hardware.py`:**
  - the `dxgi` of Wine of `lib/wine/x86_64-windows` is now this;
  - The `dxgi.dll` x64 of DXVK is also copied as `system32\dxvk_dxgi.dll`, with another name, so that it can live in the same process with that of Wine.
- **`tools/build-guest-hw.py`:** the detection of W191 (a program that matters Direct3D 10/11 or DXGI no longer reels alone). `OrbisRunsAlone="Y"` It's still working for whoever has it..

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w192/physical/20261104T041659Z/`. User response: "All right."

- **The copy `d3d11test64d3d11test64.exe`, without mark:**
  - load as a guest within the explorer (`PWGUEST load_begin`), without relaunching;
  - the presentation chain is set out by DXVK (`PWDXGI swap chain through DXVK's dxgi for window 00000000000100E6`, `Presenter: Actual swapchain properties`);
  - It comes out with a state of 0, and the desk is still responding.
- **Pale Moon:** renews by its mark (`OrbisRunsAlone`, W183 and sails.

<a id="pendiente"></a>


## Pending

- **The remaining marks:**
  - `d3d11test64.exe` keeps the W190 in the console record. The rise retains the `AppDefaults` blocks of the console, so it renews even if it is no longer necessary. It is deleted from winecfg (the application tab) or with `user_reg_reset`.
  - Pale Moon continues to run alone, but for other reason: your DLL has the same names as those of Wine Gecko.
- **Not tested:**
  - full screen (`SetFullscreenState`) of a guest with DXVK;
  - Direct3D 10;
  - several guests with Direct3D 11 at the same time;
  - a real game.
