<a id="w189-limpieza-de-diagnósticos-y-direct3d-11-de-64-bits"></a>


# W189: cleaning of Direct3D 11 64 bit diagnostics

[English](HARDWARE_W189.md) | [Español](HARDWARE_W189-es.md)

APP_VER 02.88. Base W188. The result of W188 is in `docs/HARDWARE_W188.md` (Pale Moon sails).

<a id="limpieza-de-diagnósticos-temporales"></a>


## Cleaning of temporary diagnoses

|File|What was taken out|Who?|
| --- | --- | --- |
| `tools/build-winecfg-hw.py` |The `PWCFG` marks of Apply, themes and `SetWindowPos` (W182/W183). The arrangements remain, including the `SetWindowPos` asynchronous of W183.|session of direct access|
| `tools/build-win32u-ps4.py` |`PWPAINT update_now_loop` and `PWBCAST timeout` (W182).|session of direct access|
| `platform/ps4/pw_wine_fs.c` |The probe `PWUSB` of the sandbox (W180) and its call. The assembly table follows with C: and Z:.|Network session|
| `fixtures/browser/palemoon-user.js` |The `logging.*` preferences of the network log. The network and keep-live are off.|browser session|

<a id="direct3d-11-en-programas-de-64-bits"></a>


## Direct3D 11 in 64 bit programs

<a id="qué-pasaba"></a>


### What was going on?

In W183 (`reports/wine-hardware-w183/physical/20261103T232154Z/run-0005.log`), Pale Moon relaunched as a title of 64 bits:
- DXVK 2.7.1 creates your own device Vulkan ("Adapter is not to DXVK adapter").
- The first reserve fails: `DxvkMemoryAllocator: Memory allocation failed`, 4096 bytes, with piles of 1024 and 2048 MiB almost empty.
- Then comes a `c0000005`. `d3d11test64.exe` was also closing.

<a id="causa-probable-leída-en-el-código-no-confirmada-en-la-consola"></a>


### probable cause (read in code, not confirmed in console)

- **The missing lines are not the failure.** No lines `radv/ps4: va` / `bo` appear from the second device because the detailed log of the winsys has a quota of 64 lines for the whole process (`ac_ps4_drm.c`, `ps4_verbose_left`), and the boot probe spends it. The real winsys' faults are always logged, and there is none.
- **What's really wrong?:** in 64 bits, win32u offers `VK_KHR_external_memory_win32` and DXVK It activates him. A shared reserve (e.g. a texture) `MISC_SHARED`; Gecko's shared texture test creates one of the 32×32 BGRA, 4096 bytes) passes by `vkGetMemoryFdKHR`. On the console, `ac_drm_bo_export` return `-ENOSYS` Because there's no dma-buf. win32u release the memory and return `VK_ERROR_OUT_OF_HOST_MEMORY` (your notice does not come out, because the 64 bits doesn't have `warn+vulkan`).
- **Why 32 bits goes:** the titles of 32 bits use wined3d over Vulkan (`renderer=vulkan`), which does not ask for shared memory.
- The reserve of 4096 bytes is just a shared one. You can't see it in the log.

<a id="cambio"></a>


### Change

`tools/build-win32u-ps4.py` (W189): in `__ORBIS__`, win32u stop offering `VK_KHR_external_memory_win32`, `VK_KHR_external_semaphore_win32` and `VK_KHR_win32_keyed_mutex`. Without them, DXVK rejects the resources shared with an error code rather than a normal reservation, and the program may remain unshared.

<a id="no-cubierto"></a>


### Not covered

- Export and import real memory within the process (`ac_ps4_drm.c`). It is only necessary if a programme needs shared resources to function.
- `d3d11test64.exe` may have another cause.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w189/physical/20261104T030929Z/`. User response: "1. It's closed, 2. It changes theme ok, but when you reopen the app it always starts with a moon. 3. Let's assume it. "

<a id="d3d11test64-la-memoria-se-arregló-falla-un-paso-después"></a>


### d3d11test64: the memory was fixed, one step fails

In `run-0001.log`, `d3d11test64.exe` runs as a guest within exploring:
- DXVK no longer sees the extension (`khrExternalMemoryWin32 : 0`, "External memory features not supported").
- Create the device with level 11 _ 0, and the memory reserve no longer fails.
- Then the presentation chain fails: `err:dxgi:dxgi_factory_CreateSwapChainForHwnd This is not the device we're looking for.` and `D3D11CreateDevice: Failed to create swap chain`. The program comes out with a state 0.

**Cause:** the `d3d11.dll` is that of DXVK, but the `dxgi.dll` is the building of Wine. Since W124, the `dxgi` 64 bit DXVK is not installed because it scans (the Khronos charger, MangoHud and the Gecko adapter) uses the Wine. The `dxgi` of Wine only accepts devices of wined3d. A guest shares the scanning process and the `dxgi` that is already loaded, so he can't use another.

<a id="tema"></a>

### Theme

The theme change is applied, but when the app reopens it becomes Luna. It is being reviewed by the direct access session (still without cause).

<a id="otras-pruebas"></a>


### Other evidence

- winecfg: change theme, Apply and OK work without the marks `PWCFG`.
- SMK: The user did not thoroughly test it ("let's assume ok").

<a id="para-w190"></a>


## For W190

- `system32\dxgi.dll` becomes DXVK. The one of Wine is left in `lib/wine/x86_64-windows`.
- `HKCU\Software\Wine\AppDefaults\explorer.exe\DllOverrides` `"dxgi"="builtin"`: explore and all your guests continue with that of Wine, because Wine takes the AppDefaults by the name of the process (`set_load_order_app_name`).
- `AppDefaults\d3d11test64.exe` `"OrbisRunsAlone"="Y"`: the test runs alone, relaunching the title, and there it loads `dxgi` of DXVK.
- **Pale Moon** runs alone and now it's going to load the `dxgi` of DXVK to consult the adapter. Its block `DllOverrides` of the console is kept whole on the rise, so adding a value `dxgi` from the build would not arrive. We have to check that he's still sailing.
- **Limit:** a 64 bit program with Direct3D 11 It's only gonna work if he runs alone. As a guest within an explorer, the presentation chain continues to fail.
