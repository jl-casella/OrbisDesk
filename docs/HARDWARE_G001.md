<a id="g001-vulkan-radv-sobre-gnm-en-la-ps4-hito-h0"></a>


# G001: Vulkan (RADV over GNM) in PS4, H0 milestone

[English](HARDWARE_G001.md) | [Español](HARDWARE_G001-es.md)

<a id="objetivo"></a>


## Objective

Prove that the GPU of the PS4 can be used with Vulkan from a homebrew compiled with our SDK. It is the first step towards Vulkan in Wine (H1: the same driver within ELF of Wine; H2: winevulkan; H3: `vkcube.exe` with FPS counter; H4: windows-glxgears by Zink).

<a id="de-dónde-sale"></a>


## Where does it come from

- The research of alternatives is in the session notes (`gpu-research.md`). In short: DolphinPS4, Crema and Resonance use Mesa RADV with a winsys (`port/mesa/ac_ps4_drm.c`), which sends the work with `libSceGnmDriver.sprx` (`sceGnmSubmitCommandBuffers`). The GPU uses the same virtual address as the CPU.
- The probe is `upstream/DolphinPS4/probe-vk/main.c`, copied to `native/vk_probe/main.c`. His steps are:
  1. instance and device;
  2. `vkCmdFillBuffer` and verification from CPU;
  3. a turning triangle, drawn in two linear images that are recorded in VideoOut and shown with flip in vsync.
- Own changes:
  - the log is to `/data/orbis-win/g001/`;
  - the pass 3 lasts 20 s (1200 paintings);
  - Once per second, a line `fps` is recorded, with the tables presented and the FPS that would allow the rendering and waiting of the fice alone, without vsync.
- DolphinPS4 reports that your probe works in a PS4 Slim with 12.52 and a Pro with 11.00 (`README.md`). In a Pro with 12.52 it's not proven.

<a id="cómo-se-construye"></a>


## How it's built

It all runs in WSL; The compilation tree is in `~/vk-h0` to not compile on the Windows disk.

1. `tools/vk-h0/fetch.sh` lower the two tarbals to `.deps/vk/` and create a venv with meson, mako and pyyaml:
   - Mesa 26.0.8, SHA256 `caf1c0061a68e88dfa74967a7e780c0e85d65b6c4e334cd69095a5dc54ad78bc`;
   - libdrm 2.4.125, only the headers, SHA256 `d4bae92797a50f81a93524762e0410a49cd84cfa0f997795bc0172ac8fb1d96a`.
2. `tools/vk-h0/setup-libcxx.sh` run the `toolchain/build-libcxx.sh` recipe of DolphinPS4 with our SDK and clang 19 instead of PacBrew and clang 21. Generates libc- overlay and libc + + / libc + + abi 21.1.6. The libc + + of the SDK is the 11 version and does not reach the ACO compiler of Mesa.
3. `tools/vk-h0/build-glslang.sh` compiles `glslangValidator` for the PC from the glslang copy of shadPS4. Mesa uses it for your internal shakers.
4. `tools/vk-h0/build-mesa.sh` replica `scripts/build-mesa.sh` of DolphinPS4: applies `patches/mesa-ps4.patch` and `ac_ps4_drm.c`, and compiles static, without LLVM and without WSI. It has a change of its own, `fix-mesa-detect.py`. The function checks of Mesa without header only verify that the link symbol. The libc of OpenOrbis defines `qsort_s` without declaring it, and Mesa called it without declaration. The statement is now required.
5. `tools/vk-h0/build-probe.sh` does two things:
   - compiles zlib-ng in compatible mode from the copy of shadPS4;
   - It compiles the probe and runtime of DolphinPS4 (`port/ps4_*`) and links them as `toolchain/ps4-love-style.cmake`.
   
   What you're replicating from that link:
   - RADV with `--whole-archive`;
   - Malloc wraps, mmap, `clock_gettime` and `pthread_once`;
   - the link script with `.init_array.*` and `.data.*`;
   - the `crt1.o` with the bbc heap of 64 MiB.
   
   Our libkernel stub does not export `sceKernelJitCreateSharedMemory` or `sceKernelJitCreateAliasOfSharedMemory`. They are used by the JIT Dolphin and the probe never calls them. `native/vk_probe/jit_unavailable.c` defines them as fault with trace.
6. `tools/build-vk-probe.py --upload 192.168.68.104` weapon the eboot and raise it:
   - `create-fself` with PAID `0x3800000000000035` and the lovinfo-ps4, as the probe of DolphinPS4;
   - el PKG `ORBG00001`;
   - the rise to `/data/pkg/orbis-win-G001-<sha12>.pkg`.

The ELF has a single segment `LOAD` RW, which is what requires `check-oelf.cmake` of DolphinPS4.

<a id="primer-paquete"></a>


## First package

- ELF SHA256 `93a4caa6931b582fdc608c7299e0c72769e32676b194090288525f0367995470`.
- PKG `out/vk-probe-g001/IV0000-ORBG00001_00-ORBISWINVKPROBE1.pkg`, SHA256 `c653ba5f50606598c3c4b4a609f477d6a1a9543b5c02abb1cc4dc2d636c7cb13`, raised as `/data/pkg/orbis-win-G001-c653ba5f5060.pkg`.
- It wasn't tested on the console yet.
- Log expected:
  - `/data/orbis-win/g001/vk-probe.log`;
  - `vk-probe-stderr.log`;
  - `mesa.log`.

<a id="g001-en-la-ps4-pro-1252"></a>


## G001 in PS4 Pro (12.52)

Evidence: `reports/vk-probe-g001/physical/20261101T164147Z/vk-probe.log`. The `vk-probe-stderr.log` was empty and did not generate `mesa.log`.

- Step 1: `vkCreateInstance`, `vkEnumeratePhysicalDevices` and `vkCreateDevice` return 0.
  - The device is `AMD Liverpool (PS4) (RADV BONAIRE)`, Vulkan 1.3.335, device id `0x9920`.
  - There is a family of queues (lags `0xf`) with 1 queue.
- Step 2: `vkCmdFillBuffer` and wait for the fice work. The CPU reads `0x12345678` in the first and last element.
- Step 3: VideoOut opens (`0x4e110100`) and records the two 1920x1080 framebuffers, in type memory 3. ACO compiles the pipeline in 2,3 ms.
- FPS: with vsync 58,5 to 59,9 tables per second are presented. The more the fence waiting takes about 0,9 to 1,1 ms per picture, which is equivalent to about 900 - 1100 FPS without vsync for this triangle; In a second it went up to 2,8 ms.
- The central pixel changes between pictures (`0xff5f6f73` / `0xff606f73`) and the corner follows the pulse of the background, so the GPU writes in the framebuffers.
- The log ends in the table 1139, 60 tables before the end of the step 3, without `step 3 done`. It is pending to know whether the app was closed or cut before.

Conclusion: RADV over GNM works on this console with our SDK and our homebrew identity. The next milestone is H1: the same driver within ELF of Wine.

<a id="h1-radv-dentro-del-elf-de-wine-w070"></a>


## H1: RADV within ELF of Wine (W070

- `native/vk_probe/main.c` is also compiled with `PW_VK_IN_WINE` and is as `pw_vk_probe()`. In this way it does the following:
  - writes in the log of the Runs with the prefix `PWVK`;
  - does not open VideoOut, which is of the Wine sink;
  - draw 300 off-screen triangle tables, without flips;
  - leave the device open.
  
  The pitcher (`native/wine_hardware.c`) calls it before starting Wine, between `vk_probe_start` and `vk_probe_end`. So Wine starts with the memory reserves of driver of GPU already made.
- Mesa is compiled in a variant for Wine (`VARIANT=wine tools/vk-h0/build-mesa.sh`, in `~/vk-h0/build/mesa-wine`). There are two differences with G001:
  - No `unistd.h` in the overlay. In ELF of Wine, `sysconf` is that of the libc of SDK, with the numbering of musl. In G001 it was the kernel, with the numbering of FreeBSD. `mmap` and `clock_gettime` come from the kernel in both cases, so overlay of `sys/mman.h` and `time.h` It's keeping up.
  - `pthread_once` is called `pw_vk_pthread_once` (`native/wine_vk_runtime.c`). The kernel is treated `pthread_once_t` as a structure of 16 bytes, while the headers declare 4. The same change with `objcopy` is applied to libc + + and libc + + abi.
    
    Our own code also calls the `pthread_once` kernel (`native/hw_pad.c` and `platform/ps4/pw_wine_net.c`) with variables of 4 bytes. It is a risk of corruption that was not corrected in this step.
- `tools/build-wine-hardware.py` links:
  - the probe and the runtime;
  - RADV with `--whole-archive`;
  - zlib, libc + + and libc + + abi.
  
  Since W070 the ELF of Wine uses a copy of `link.x` of SDK which gathers `.data.*`, `.tdata.*`, `.tbss.*` and `.init_array.*`. Mesa uses `-fdata-sections` and libc + + has priority builders; With the original script, those sections were orphaned.
- Link result: without indefinite symbols and with a single `LOAD` RW. The verification that no kernel import became static definition has passed.
- PKG `/data/pkg/orbis-win-W070-0276a24376b8.pkg` (APP_VER 01.69). It wasn't tested on the console yet.
- W070 in PS4 (`reports/wine-hardware-w070/physical/20261101T174648Z/run-0001.log`):
  - The probe runs within ELF of Wine, between `vk_probe_start` (2126 ms) and `vk_probe_end` (3080 ms): 953 ms in total.
  - Intution, device, `vkCmdFillBuffer` (`0x12345678` in the first and last element) and 300 out-of-screen triangle tables. The results are the same as in G001: the same addresses (`0x43ff...`), the same central pixel, the pipeline compiled in 2,3 ms and about 2 ms average per picture, including the first one, which takes 12 ms.
  - Then Wine starts the desktop with the Vulkan open device: explorer presents pictures and receives mouse clicks.
  - The log ends without `process_exit` and without programs launched, in a pointer movement. The user closed the app from PS4; It wasn't a hang.
  - With this H1 is fulfilled: RADV works within ELF of Wine and Wine starts with the open device.

<a id="h2-vulkan-para-programas-de-windows-w071"></a>


## H2: Vulkan for Windows (W071 programs

- Side Windows: `winevulkan.dll` and `vulkan-1.dll` are compiled unchanged as PE64 in the tree of Wine (`make dlls/<nombre>/x86_64-windows/<nombre>.dll`). `build-wine-hardware.py` copies to `wine/lib/wine/x86_64-windows` and `system32`.
- Unix side of winevulkan: `tools/build-winevulkan-ps4.py` compiles `vulkan.c` and `vulkan_thunks.c` without patches, with the recipes of the Orbis Makefile. The two objects are combined in one, and their hidden symbols are local. The tables `__wine_unix_call_funcs` and `__wine_unix_call_wow64_funcs` are renamed. `platform/ps4/pw_wine_unixlibs.c` delivers them to ntdll as `winevulkan.so`, and `tools/link-wine-boot.py` adds the object to the link.
- `win32u` (`build-win32u-ps4.py`): instead of `dlopen("libvulkan.so.1")`, take `vkGetInstanceProcAddr` from the pointer `pw_vk_instance_proc_addr` (`pw_wine_unixlibs.c`). The pitcher completes it with `pw_vk_get_instance_proc_addr` (`native/wine_vk_runtime.c`) after the probe. That function also returns `vkGetDeviceProcAddr`, that the ICD search of RADV does not return, as it does prospero-win in `wine/ps5/pw_vulkan_radv.c`. If the pointer is NULL, which is what happens in the links of Wine without RADV, there is Vulkan and it is recorded `PWVK no RADV linked`.
  
  A first attempt with a weak symbol caused `create-fself` to reject the ELF of `link-wine-boot.py` (output 255), because that ELF left the reference undefined.
- The user's driver does not implement `VulkanInit`, so `win32u` uses his null: surfaces `VK_EXT_headless_surface`, which RADV offers. Nothing is yet present in a window; That's H3.
- Test: `fixtures/win32/vkprobe64.c`, compiled with MinGW as `C:\orbis\vkprobe64.exe`. It is a console program that loads `vulkan-1.dll` and does the following:
  - creates the instance;
  - list the GPU;
  - create the device;
  - makes 100 filled with 1 MiB with GPU and verifies each from CPU.
  
  Write the result on the console and in `C:\orbis\vkprobe64.txt`, and end in `PASSED` if everything worked.
- PKG `/data/pkg/orbis-win-W071-76f501e91750.pkg` (APP_VER 01.70). It wasn't tested on the console yet.
- W071 in PS4 (`reports/wine-hardware-w071/physical/20261101T181202Z/`, with `run-0001.log` and `vkprobe64.txt`): **H2 accomplished.** `vkprobe64.exe` ran as a guest, with his console:
  - `vulkan-1.dll` loading and offering Vulkan 1.4.0 with 8 instance extensions; `vkCreateInstance` late 40 ms.
  - List a GPU, sell `0x1002` and device `0x9920`, which are the same as in G001/W070, with Vulkan 1.3.335. The name you see the program is `PS5`: it is put by driver user of prospero-win, not RADV. It's still going to change.
  - `vkCreateDevice`, the host-visible memory (mapped in `0x4fffe60000`), the command pool and the fence work.
  - The 100 filled with 1 MiB, each verified from CPU, give the expected result, with about 4,5 ms by filling including fence waiting and verification. It ends at `vkprobe64: PASSED`.
  - The log has 160 lines `radv/ps4: submit`, each repeated twice. The winsys writes both in stderr and in his log, and both go to the rush log.
  - The guest and its console end and are normally downloaded.

<a id="h3-vulkan-en-ventanas-w072"></a>


## H3: Vulkan in windows (W072)

- The user driver does not have `VulkanInit`, so the surfaces `win32` of the applications are headless surfaces of Mesa, in the host. Your WSI requests DRM images, and the PS4 does not have DRM. `tools/vk-h0/patch-mesa-wsi.py` (applied by `build-mesa.sh`) changes `wsi_common_headless.c`, only with `__PS4__`, in two points:
  - The images of the swapchain are of type CPU. It is the path that Mesa uses for drivers by software: an optimal image in GPU and, in each present, a blit from GPU to a linear buffer that CPU you can read (`cpu_map`).
  - In the present the fence of that blit is expected and called `pw_wsi_headless_presented` with the pixels, the pitch, the size and the format.
- `native/wine_vk_runtime.c` save the last picture of each swapchain and record one line `PWVK present fps` per second. `pw_vk_runtime_init()`, which the pitcher calls after the probe, installs the three points: `pw_vk_instance_proc_addr`, `pw_vk_last_frame` and the hook of Mesa.
- `win32u` (`build-win32u-ps4.py`): After the host's present, `pw_vk_show_frame` draw that picture in the swapchain window with `NtGdiStretchDIBitsInternal`, climbed to the client area. If the format is RGBA, first it exchanges R and B. The composer shows the window like any other. The first 5 copies, and then one in every 600, are left in the log as `PWVK show_frame`.
- Expected cost: each picture passes through a button of the GPU to the memory of the host and by a copy by GDI. It is slower than showing the picture directly; The actual number will be tested.
- Test: `fixtures/win32/vkspin64.c`, compiled as `C:\orbis\vkspin64.exe`. It is a window of 640x480 with the triangle of G001 turning, drawn with a swapchain of `VK_KHR_win32_surface` that recesses when changing the size of the window. It shows the FPS in the title and writes them in `C:\orbis\vkspin64.txt`.
- PKG `/data/pkg/orbis-win-W072-39080c7ec6eb.pkg` (APP_VER 01.71). It wasn't tested on the console yet.
- W072 in PS4 (`reports/wine-hardware-w072/physical/20261101T182702Z/`, with `vkspin64.txt`): `vkCreateInstance` returned - 7 (`VK_ERROR_EXTENSION_NOT_PRESENT`) and the program ended without pictures.
  - RADV only offers `VK_KHR_surface`, `VK_EXT_headless_surface` and `VK_KHR_swapchain` with `RADV_USE_WSI_PLATFORM` (`src/amd/vulkan/radv_wsi.h`), which is defined only with a window platform: X11, Wayland or display.
  - Without `VK_EXT_headless_surface` in the host, `win32u` does not offer `VK_KHR_win32_surface`.
- W073: `patch-mesa-wsi.py` also defines `RADV_USE_WSI_PLATFORM` with `__PS4__`, because headless is the platform of PS4. PKG `/data/pkg/orbis-win-W073-211879c12c51.pkg` (APP_VER 01.72). It wasn't tested on the console yet.
- W073 in the PS4 (`reports/wine-hardware-w073/physical/20261101T183811Z/`, with `vkspin64.txt`): **the presentation in windows works.**
  - `vkspin64` creates the surface: `presentation support 1`, 2 formats, use the 44 (`B8G8R8A8_UNORM`.
  - Create a 632x453 swapchain with 4 images. `pw_vk_show_frame` draw each box in the window (`drawn=453`, the complete client area).
  - FPS in 632x453: 34,3 to 36,7, measured by the program and by the hook of Mesa.
  - FPS with the maximized window (1280x701): 11,6 to 12,1. The swapchain was well recreated the four times it was maximized and restored the window.
  - The program ended when the window closed (`end after 817 frames`), and the app usually came out from Start (`process_exit status=0`).
  - The time per picture (about 28 ms in 632x453 and 83 ms in 1280x701) grows with the area, so it is limited by the copies and not by the GPU, which in G001 drew this triangle in about 1 ms. There are two unmeasured candidates: reading from the CPU memory to which the blit copies the image, which may not have cache, and copying it by GDI plus the composer.

<a id="velocidad-de-la-copia-w074"></a>


## Copy speed (W074)

- `patch-mesa-wsi.py` changes the memory of the buffers from CPU of the swapchain: in the PS4 order `HOST_CACHED`, as Mesa makes for the drivers by software. Before Mesa asked only `HOST_COHERENT`, that in RADV may fall into memory without cache; reading it from the CPU is slow. `build-mesa.sh` restores from the tarball the three files that touch the patch before applying it.
- New measurements:
  - `blit_wait_us`, in the line `PWVK present fps`: what the present expects the blit from GPU to the buffer from CPU (`os_time_get_nano` in Mesa).
  - `gdi_us`, in `PWVK show_frame` each 60 pictures: which takes `win32u` the copy to the window, including the conversion of RGBA if there is one.
  - The cost of the composer was already recorded in `flush_stats`.
- PKG `/data/pkg/orbis-win-W074-3fb6f2f6f272.pkg` (APP_VER 01.73). It wasn't tested on the console yet.
- W074 in PS4 (`reports/wine-hardware-w074/physical/20261101T185124Z/`, with `vkspin64.txt`):
  - FPS in 632x453: 276 to 279. In W073 were about 36, about 7,7 times less.
  - FPS in 1280x701 (maximized): 125,6 to 132,2. In W073 were about 12, about 11 times less.
  - 5769 total tables. The swapchain was recreated by maximising and restoring, and the program and the app ended normally.
  - Times per picture in 1280x701:
    - waiting for the GPU blit (`blit_wait_us`): about 0,7 ms (0,24 ms in 632x453);
    - copy by GDI to the window (`gdi_us`): about 1,6 ms (0,5 ms in 632x453);
    - composer (`flush_stats avg_us`): about 4,1 ms per flush, with about 880.000 pixels.
  - The slowness of W073 came from the CPU reading memory without cache. Now the limit is in the copy by GDI and in the composer, who runs separately; The screen is also updated to 60 Hz.
  - The program presents more pictures per second than the screen shows, because the swapchain headless does not expect the vsync. For one game that's more work.
- Photos of W074 taken by the user: the triangle is seen with its colors. At times, the `vkspin64` maximized window lets you see the wallpaper (clouds and hills), as if it were transparent.
  - Cause: `compose_rect` (composer of `ps5drv.c`) first copy the wallpaper to the desktop buffer and then the windows on top. The thread of the sink (`PW_SINK_ASYNC`) reads the same buffer without waiting for the composer. A picture read between the two past has the background where the window is.
  - With a window that is redrawn 130 times per second it passes followed. The photo brings together several refreshments in an exhibition, and that's why the result seems to be transparent.
- W075 (`build-win32u-ps4.py`): `compose_rect` weapon each row in an auxiliary row (the bottom and the windows below up) and copy it to the desktop buffer only once. A cut-off reading can still mix rows from the previous and the new box, but no rows without the window. PKG `/data/pkg/orbis-win-W075-8e1810d644ae.pkg` (APP_VER 01.74). It wasn't tested on the console yet.
- W075 in PS4 (`reports/wine-hardware-w075/physical/20261101T201511Z/run-0001.log`):
  - `vkspin64` runs at about 290 FPS in 632x453, as in W074.
  - The composer takes the same thing with the auxiliary row: `flush_stats avg_us` of 1,7 ms with some 290.000 pixels and 3,9 a 4,1 ms with about 880.000.
  - The log cannot show if the background is still seen through the window; that's got to be confirmed by the user looking at the screen.
  - The user confirmed that the background is no longer seen through the window.

<a id="h4-opengl-con-zink-w076"></a>


## H4: OpenGL with Zink (W076

- `tools/vk-h0/build-mesa-zink.sh` compiles the front WGL of Mesa with the driver Gallium Zink as DLL PE64: `opengl32.dll` and `libgallium_wgl.dll`. Use the same options as `upstream/prospero-win/tools/build_mesa_zink.sh`, but with the official target of Mesa 26.0.8 without patches, extracted separately in `~/vk-h0/src/mesa-win`, instead of the fork of prospero-win.
  - The system's MinGW has no C + +, so it is used llvm-mingw 20260922 UCRT (`fetch-llvm-mingw.sh`, SHA256 `bb7bb765...65c21`), the same as it fixes prospero-win.
  - Zink load `vulkan-1.dll`, i.e. winevulkan and RADV.
  - DLL imports UCRT per api-sets, `KERNEL32`, `GDI32` and `USER32`; no C + + library.
  - SHA256: `opengl32.dll` `bd94657a...bf48bf`, `libgallium_wgl.dll` `de20cd15...41d32dd`.
- `build-wine-hardware.py` copies them to `system32` as `opengl32.dll` native, because the runtime does not have `opengl32` build.
- Test: `fixtures/win32/glxgears/main.cpp`, the CalvinHartwell glxgears port (`8c27987`, by Brian Paul), compiled with lvm-mingw as `C:\orbis\glxgears.exe` (SHA256 `44dfe1e8...c90949`). The following was added:
  - the FPS of each interval of 5 s in the window title;
  - a file `C:\orbis\glxgears.txt` with `GL_RENDERER`, `GL_VERSION`, `GL_VENDOR`, FPS and any initialization failure.
- PKG `/data/pkg/orbis-win-W076-4d3ba493932f.pkg` (APP_VER 01.75). It wasn't tested on the console yet.
- W076 in PS4 (`reports/wine-hardware-w076/physical/20261101T202920Z/`, with `glxgears.txt`):
  - `glxgears` opens your window, but `ChoosePixelFormat` returns 0 (`failed to initialise opengl: ... pixel format 0`). The 203 error is a last old thread error.
  - In the chain gdi32 → `opengl32.dll` (Mesa) → `wglChoosePixelFormat`, Zink if you have created the device: the log has the memory reserves of RADV (`radv/ps4: bo ...`). What fails is the list of pixel formats of Mesa (`stw_pixelformat.c`), which depends on `is_format_supported` of Zink. The case is not identified.
  - The program ends normally and your console is downloaded.
- W077, diagnosis:
  - `glxgears` records how many pixel formats it offers `DescribePixelFormat` and how it is first.
  - The pitcher defines `MESA_LOG_FILE=C:\orbis\mesa-wgl.log` for the Mesa of Windows to write your messages (util/log. The RADV of the ELF also reads that variable, but that name is not a valid route for him.
  - The pitcher's argument arrangement goes from `8+` to `10+MAX_LAUNCH_ARGS`.
  - PKG `/data/pkg/orbis-win-W077-b61d6b344586.pkg` (APP_VER 01.76).
- W077 in PS4 (`reports/wine-hardware-w077/physical/20261101T215324Z/`, with `glxgears.txt`):
  - `DescribePixelFormat` says there are 0 pixel formats, and `ChoosePixelFormat` fails with the error 50 (`ERROR_NOT_SUPPORTED`).
  - The log shows that Zink creates its instance and its device in RADV: a second winsys, with its address windows in `0x4c00000000` and `0x5000000000`, and 7 buffers. Then there is no more activity than GPU before the program is over.
  - It was not generated `mesa-wgl.log`: in Windows, `util/log.c` of Mesa it does not use `MESA_LOG_FILE`; writes in stderr, which goes to the program console, and in `OutputDebugString`.
- W078: the launcher defines `WINEDEBUG=warn+seh`. Wine records `OutputDebugString` as channel warning `seh` (`dlls/kernelbase/debug.c`), so messages of Mesa and Zink are going to appear in the log of the Runs. PKG `/data/pkg/orbis-win-W078-e8349943b4bd.pkg` (APP_VER 01.77).
- W078 in the PS4 (`reports/wine-hardware-w078/physical/20261101T220147Z/run-0001.log`): `WINEDEBUG=warn+seh` makes the message of Zink visible: `MESA: error: ZINK: failed to get total physical memory`.
  - In Windows, Mesa takes that `GlobalMemoryStatusEx` (`src/util/os_misc.c` data, and if it fails, Zink Don't create the screen. Without a screen, WGL has no pixel formats.
  - The `GlobalMemoryStatusEx` of Wine (`dlls/kernelbase/memory.c`) depends on three queries: `NtQuerySystemInformation(SystemBasicInformation)`, `NtQuerySystemInformation(SystemPerformanceInformation)` and `NtQueryInformationProcess(ProcessVmCounters)`. If any fails, return FALSE.
- W079: `glxgears` records in `glxgears.txt` the result of `GlobalMemoryStatusEx` and the status and length of each of the three consultations, before starting OpenGL. PKG `/data/pkg/orbis-win-W079-0f96d0aa6ba4.pkg` (APP_VER 01.78).
- W079 in PS4 (`reports/wine-hardware-w079/physical/20261101T220947Z/`, with `glxgears.txt`): `GlobalMemoryStatusEx` return 0 with error 50. `NtQuerySystemInformation(SystemBasicInformation)` and `NtQueryInformationProcess(ProcessVmCounters)` respond 0, but `NtQuerySystemInformation(SystemPerformanceInformation)` respond `0xc00000bb` (`STATUS_NOT_SUPPORTED`). That value was always returned by `get_performance_info` in PS4 for an earlier review of `prepare-wine-boot.py`, because then there was no place to draw the data.
- W080 (`prepare-wine-boot.py`, `platform/ps4/pw_wine_memory.c`):
  - `pw_wine_memory_info` take the kernel figures. The total is the direct (`sceKernelGetDirectMemorySize`) memory plus the flexible (`sceKernelAvailableFlexibleMemorySize` memory available. What is available is the highest free range of direct memory (`sceKernelAvailableDirectMemorySize`) plus the flexible range available.
  - The kernel does not give the configured size of the flexible pool or the total free of direct memory. This is why these figures are not exactly those of physical memory of Windows, although they are real measures. The first call is left in the log as `PWBOOT memory_info`.
  - The prototypes of SDK for the two functions `Available` declare the output pointers as values; `pw_wine_memory.c` declares them as the kernel uses them..
  - `get_performance_info` complete `AvailablePages`, `TotalCommittedPages` and `TotalCommitLimit` with those figures. The idle time is left in 0 and the paging file on a page, as it does Wine in systems without swap. If the kernel fails, it keeps returning `STATUS_NOT_SUPPORTED`.
  - `virtual_get_system_info` (`SystemBasicInformation`) uses the same total, and returns to `sysinfo()` if the kernel fails.
  - PKG `/data/pkg/orbis-win-W080-cda31ccf962f.pkg` (APP_VER 01.79).
- W080 in the PS4 (user photos): **glxgears works** by WGL, Zink, winevulkan and RADV, at about 66 FPS in a window of about 300x300. But parts of the gears, especially the red (the largest), disappear and return from one picture to another.
- W081: the RADV of the ELF of Wine the port of DolphinPS4 the Crema (`build-mesa.sh` with `VARIANT=wine`).
  - Crema (`upstream/Crema/patches/BASE.txt`) use Mesa 26.0.8 of DolphinPS4 plus its `mesa-ps4.patch` and `mesa-ps4-aligned-vertex-fetch.patch`.
  - His `ac_ps4_drm.c` has 3609 lines, against 2937 in DolphinPS4. Among other things, it releases, unmounds and reuses a buffer only when the GPU finished everything sent before. According to his comment, releasing him earlier made the late scriptures of the GPU fall into what occupied that memory later.
  - It also adds a tail for the overflow of each buffer and a high priority shipping thread.
  - Zink raises the vertices of glxgears to buffers that are renewed each picture, so that's the hypothesis for what you see; It's not confirmed.
  - The source tree is left apart (`~/vk-h0/src/mesa-crema`), and its logs are going to `/data/orbis-win/gpu`.
  - `native/wine_vk_runtime.c` implements the two functions of the Crema runtime that calls his winsys: `ps4_boot_trace`, that he writes in the log of the Runs, and `ps4_boost_thread`, that he does `scePthreadSetprio(..., 650)`.
  - G001 continues with the port of DolphinPS4.
  - PKG `/data/pkg/orbis-win-W081-b38c66a80326.pkg` (APP_VER 01.80).
- W081 in the PS4 (`reports/wine-hardware-w081/physical/20261101T231430Z/`): the user reports that **follows the same problem** with the gears. The winsys change didn't solve it.
  - `GlobalMemoryStatusEx` = 1, with a total of 5.097.123.840 bytes and 5.064.753.152 available.
  - `SystemPerformanceInformation` = 0, length 312.
  - WGL offers 504 pixel formats. `GL_RENDERER` = `zink Vulkan 1.3(PS5 (MESA_RADV))`, `GL_VERSION` = `4.6 (Compatibility Profile) Mesa 26.0.8`.
  - glxgears does 54,8 FPS in the first 5 s and then 66,0. The hook of Mesa counts 65 to 67 presentations per second of 300x300, with about 0,13 ms waiting for the blit.
  - `vkspin64` also works with the winsys from Crema: 212 to 271 FPS in 632x453.
- W082, experiment: the launcher defines `ZINK_DEBUG=sync`, which forces a complete barrier before each drawing. If the gears are whole, the cause is a missing synchronization. If not, it is another thing: for example, how Zink draw the quadrilateral (`GL_QUAD_STRIP` / `GL_QUADS`) or the flat shading of glxgears in gfx7. PKG `/data/pkg/orbis-win-W082-ec3eafd39dc9.pkg` (APP_VER 01.81).
- W082 in the PS4: the user reports that with `ZINK_DEBUG=sync` **it remains the same**. The cause is not a missing synchronization between drawings.
- W083, experiment: it is removed `ZINK_DEBUG=sync` and the launcher defines `RADV_DEBUG=nohiz,nofastclears`, which disables depth compression (HTILE/HiZ) and rapid clears of RADV.
  - Hypothesis: `vkspin64` has no depth buffer and draws whole triangles; glxgears does have it and clean it in every picture.
  - If the compressed depth or its fast clear work badly in Liverpool, parts of the geometry fail the depth test according to the angle, which is what you see.
  - RADV read the variable when creating its instance. Zink is created after Wine defines the environment; The pitcher's probe, before, so the probe doesn't see it.
  - PKG `/data/pkg/orbis-win-W083-06fa4cc22d94.pkg` (APP_VER 01.82).
- W083 in the PS4: the user reports that with `RADV_DEBUG=nohiz,nofastclears` **stays the same.**. The cause is not depth compression or fast clears.. W084 Take away that experiment..
- W084: `fixtures/win32/gltest64.c` (`C:\orbis\gltest64.exe`) draw the same ring with light, which turns, in six ways on a 3x2 grid. The ring has a front face, a back face and an outside band, like a toothless gear. As in glxgears, the back faces are discarded (`GL_CULL_FACE`) on all panels but 6.
  1. up to the left: immediate, `GL_QUAD_STRIP`, soft shading;
  2. up to the center: `GL_QUAD_STRIP`, flat shading;
  3. up to the right: `GL_TRIANGLE_STRIP` with the same vertices, flat;
  4. down left: drawing list (as glxgears), `GL_QUAD_STRIP`, flat;
  5. down to the center: `GL_QUADS`, flat;
  6. down to the right: `GL_QUAD_STRIP`, flat, without discarding of faces.
  
  The panels that lose geometry indicate the guilty conversion: quadrilateral, flat shaded (provocative vertex), drawing lists, or discarding of faces with the Y inverted of Zink. PKG `/data/pkg/orbis-win-W084-83907ea1d8e3.pkg` (APP_VER 01.83).
- W084 in the PS4: the user reports that only the panel from top to right (blue, `GL_TRIANGLE_STRIP`) looks good. The five quadrilateral panels lose parts, including 6, without dissolving faces.
  - Zink draw `GL_QUADS` with a generated shader geometry (`zink_create_quads_emulation_gs` in `zink_program.c`), and declare `GL_QUAD_STRIP` No support, so the front end goes to quads.
  - Triangles do not use shader geometry. The geometry shakers fail in Liverpool with RADV; Crema investigate your rings GS in `upstream/Crema/patches/mesa-ps4-gs-ring-probe.patch`.
- W085 (`tools/vk-h0/patch-mesa-zink.py`, applied by `build-mesa-zink.sh`): Zink does not declare `GL_QUADS` between the primitives supported, so the front of Mesa converts the quadrilateral into indexed triangles.
  - This covers any program OpenGL I draw with quadrilateral.
  - **No** fixes the geometry shakers. The programs that use GS their own (OpenGL modern, Direct3D 10/11 by DXVK continue to be affected. and other Zink emulations using GS: stitched or softened lines, edges and some point modes.
  - `libgallium_wgl.dll` SHA256 `f49b5c31...71cf`.
  - PKG `/data/pkg/orbis-win-W085-d3e9c4084736.pkg` (APP_VER 01.84).
- W085, Runs 3 (`reports/wine-hardware-w085/physical/`, `run-0003.log`): the user deleted files from `C:\orbis` and Wine stopped starting (`boot_main_return rc=95`).
  - The pre-start check (`preflight`) uses fixtures from that folder, as `console32.exe`. Without them, `drive-resolution`, `drive-z-resolution`, `file-identity` and `exe-pe32` remain `blocked` with errno 2.
  - `upload-hardware.py --build W085` returned to upload the missing 7 files: `console32.exe`, `gui-window64.exe`, `gui-text64.exe`, `vkprobe64.exe`, `gltest64.exe` and two others. Compare each file with the manifest, so that's the way to repair the prefix.
- W085 in the PS4: the user confirms that **glxgears looks good**. `gltest64` was not tested.

<a id="mangohud-y-vkcube-w086"></a>

## MangoHud and vkcube (W086)

- Overlay: MangoHud - Windows (`github.com/Leclowndu93150/MangoHud-Windows`, commit `52592550`), a community fork of MangoHud only for Windows.
  - `tools/vk-h0/build-mangohud.sh` compiles it with lvm-mingw, without NVML or tests. His subprojects (imgui, implot, spdlog, minholk, vulkan-headers) come from his Meson wraps.
  - A single change: `src/fps_metrics.h` includes `<sstream>`, which the libc + + of lvm-mingw needs.
  - Result: `libMangoHud.dll` (SHA256 `ef123777...e343`) and the implicit layer `MangoHud.x86_64.json`. His `library_path` becomes `.\libMangoHud.dll`, next to the manifesto in `system32`.
  - The proxy `dxgi.dll` of the fork (for DirectX) is not used.
- MangoHud is a layer of Vulkan, and the `vulkan-1.dll` of Wine resends directly to winevulkan No layers. That's why the official charger was added:
  - `tools/vk-h0/build-vulkan-loader.sh` compiles Vulkan -Loader v1. 4.335 from Khronos (commit `052ac246`, headers `2fa20342`) with lvm-mingw. `vulkan-1.dll` SHA256 `68b35e07...b333e`.
  - It goes in `system32`, with `"vulkan-1"="native"` in DllOverrides of `user.reg`.
  - Find winevulkan by `system32\winevulkan.json`, the same manifesto that writes `DllRegisterServer` of Wine, recorded in `HKLM\Software\Khronos\Vulkan\Drivers`.
  - The layer is recorded in `HKLM\Software\Khronos\Vulkan\ImplicitLayers`, and the launcher defines `MANGOHUD=1`, the variable that activates it.
  - Zink load `vulkan-1.dll`, so the overlay should also appear in glxgears.
- `libMangoHud.dll` matters `dxgi`, `d3dcompiler_47` and `dwmapi`. Those DLL, more `wined3d` you need `dxgi`, are compiled without change as PE64 in the host's Wine tree and go to the library directory and `system32`.
- vkcube: `tools/vk-h0/build-vkcube.sh` compiles the Vulkan -Tools v1. 4.335 (commit `48b5d246`) cube with lvm-mingw, as `C:\orbis\vkcube.exe` (SHA256 `a89ee4e5...5873`). The FPS shows them MangoHud.
- Data that MangoHud will not have in PS4: the fork reads the GPU with DXGI and ADL or NVML, the CPU with `GetSystemTimes` / `NtQuerySystemInformation` and the RAM with `GlobalMemoryStatusEx`. The next step, connecting the load of the GPU that measures the winsys of Crema and the data of the PS4, depends on what it shows in this Runs.
- PKG `/data/pkg/orbis-win-W086-d798aabd5619.pkg` (APP_VER 01.85), 538 runtime files. It wasn't tested on the console yet.
- W086 in PS4 (`reports/wine-hardware-w086/physical/20261102T001256Z/run-0001.log`):
  - They were launched `vkcube.exe` and `vkspin64.exe`. Zink reports `ZINK: vkCreateInstance failed (VK_ERROR_INCOMPATIBLE_DRIVER)`: the Khronos charger did not find any driver.
  - On the registration track (`windows_get_registry_files` in `loader_windows.c`), the shipper first creates a factory DXGI to verify the drivers. The `dxgi` of Wine load `wined3d`, which tries OpenGL (`Failed to get a GL context for adapter`) and leaves no adapter.
- W087, changes to the launcher:
  - `VK_DRIVER_FILES=C:\windows\system32\winevulkan.json`: The charger takes the driver from there, without registration or DXGI.
  - `WINE_D3D_CONFIG=renderer=no3d`: `wined3d` without 3D, so that `dxgi` just list, which is what you ask MangoHud for GPU.
  - `VK_LOADER_DEBUG=error,warn`: the errors and warnings of the charger come out by `OutputDebugString` and remain in the log with `warn+seh`.
  - The argument setting goes to `14+MAX_LAUNCH_ARGS`.
  - PKG `/data/pkg/orbis-win-W087-ee536fb98b9d.pkg` (APP_VER 01.86).
- W087 in PS4 (`reports/wine-hardware-w087/physical/20261102T023852Z/run-0001.log`):
  - Vulkan works through the Khronos charger. `vkspin64` presents 261 - 286 FPS in 632x453, and `glxgears` (Zink) at about 65 FPS at 300x300.
  - The charger consults the package `Microsoft.D3DMappingLayers` while looking for layers (`GetPackagesByPackageFamily`, a stub of Wine), and does not record errors or warnings.
  - `vkcube.exe` He didn't throw himself in this run..
  - The log does not show whether the MangoHud layer was loaded; That looks on the screen.
- The user reports that in W087 **the overlay** of MangoHud did not appear.
  - No messages from the charger were seen either: in `loader/log.c` just call `OutputDebugString` with `#if defined(WIN32)`. MinGW with `-std=c11` defines `_WIN32` but not `WIN32`, so those messages didn't come out. They were just going to stderr, which in a GUI program doesn't get anywhere.
- W088: the charger is compiled with `-DWIN32`, as in MSVC (`build-vulkan-loader.sh`), and the launcher is extended `VK_LOADER_DEBUG` to `error,warn,info,layer`. So the log will show where the charger is looking for layers, if it finds `MangoHud.x86_64.json` and if it can load `libMangoHud.dll`. PKG `/data/pkg/orbis-win-W088-7f7eaabdd978.pkg` (APP_VER 01.87).
- W088 in the PS4 (`reports/wine-hardware-w088/physical/20261102T024548Z/`): `vkcube` starts. `wined3d` starts in mode `no3d` and the RAM consultation (`SYSTEM_PERFORMANCE_INFORMATION`) appears, indicating that `dxgi` and MangoHud were charged. But the overlay does not appear, and there are no messages from the charger even though it now has `OutputDebugString`.
- W089 (`VK_ADD_IMPLICIT_LAYER_PATH=C:\windows\system32`, `VK_LOADER_LAYERS_ENABLE=*mangohud*`, `VK_LOADER_DEBUG=all`, `MANGOHUD_USE_LOGFILE=1`, `MANGOHUD_LOG_LEVEL=debug`): **the user confirms that MangoHud is seen in vkcube.**
  - The record just didn't reach for the layer to activate. With the additional route and the name rating, it is activated; it is not isolated which of the two makes it, and the two of them remain.
  - The three-run (`reports/wine-hardware-w089/physical/20261102T025706Z/`) logs still have no messages from the charger, and MangoHud did not create your log file. The cause of both is not identified.
- W090:
  - **Home Menu:** folder "Graphics Tools" (`tools/make-start-menu.py`) with glxgears, vkcube, vkspin and "MangoHud Config".
    - The first three point to `C:\orbis`. "MangoHud Config" opens `%APPDATA%\MangoHud\MangoHud.conf` with the Notebook.
    - The generator now supports arguments and a separate icon (`HAS_ARGUMENTS`, chains in the order of [MS-SHLLINK]). The above accesses are identical byte to byte.
  - **Icons:** `tools/make-icons.py` draw in Python the icons of 16, 32 and 48 px and writes them as `.ico` (BMP of 32 bit with mask), in `C:\orbis\icons`: gears, cube, triangle RGB and an orange "M." The test programs have no icons of their own.
  - **MangoHud.initial conf:** fps, frametime, frametime chart, CPU, GPU, RAM, and position up left.
  - **MangoJuice not included.** MangoJuice - Windows (`e2ec0755`) is a Vala application with GTK4, libadwait- 1 and ge- 0.8, and has no releases. You have to compile the whole GTK4 battery for Windows and have `valac` in the host, which is not installed.
  - PKG `/data/pkg/orbis-win-W090-3456e351caaf.pkg` (APP_VER 01.89).
- Correction: the user clarifies that the overlay **did not appear** either in W089 or in W090.
  - In both of these, `vkcube` load the same DLL. Among them is `dnsapi`, which comes from `IPHLPAPI` and which only matters `libMangoHud.dll`. `wined3d` starts at `no3d` and the RAM is consulted.
  - `libMangoHud.dll` exports `overlay_GetInstanceProcAddr` and `overlay_GetDeviceProcAddr` the names of your manifesto.
- W091: `fixtures/win32/vklayers64.c` (`C:\orbis\vklayers64.exe`, console) writes in `C:\orbis\vklayers64.txt`:
  - the environment variables read by the charger;
  - the route of the `vulkan-1.dll` which is charged;
  - the layers that are listed `vkEnumerateInstanceLayerProperties`;
  - all the messages of the charger for two `vkCreateInstance`: one with implicit layers and one with `VK_LAYER_MANGOHUD_overlay_x86_64` explicit.
  
  The messages come by a message `VK_EXT_debug_utils` in the `pNext`, which the charger feeds in addition to its log. PKG `/data/pkg/orbis-win-W091-7ab53be04873.pkg` (APP_VER 01.90).
- W091 in PS4 (`reports/wine-hardware-w091/physical/20261102T030636Z/vklayers64.txt`):
  - The charger finds the layer by the record (`Located json file "C:\windows\system32\MangoHud.x86_64.json" from registry`) and the list in `vkEnumerateInstanceLayerProperties`.
  - When loading it fails: `Failed to open dynamic library "C:\windows\system32\.\libMangoHud.dll" with error 1114` (`ERROR_DLL_INIT_FAILED`) and `Requested layer "VK_LAYER_MANGOHUD_overlay_x86_64" failed to load`. The instance is created equally, without the layer.
  - The `DllMain` of MangoHud (`src/win/main.cpp`) returns TRUE always. The 1114 has to come from the initialization of another DLL: a dependence (`dxgi`, `d3dcompiler_47`, `dwmapi`, `iphlpapi` o `dnsapi`) or the boot of C + + 's own DLL.
  - The charger reports `running with elevated permissions` and ignores all variables `VK_*` (`VK_DRIVER_FILES`, `VK_ADD_IMPLICIT_LAYER_PATH`, `VK_LOADER_LAYERS_ENABLE`. In the programme environment, they are also undefined. Driver and cape find them by the record.
  - `winevulkan` declares the charger interface 4; the charger warns that for Vulkan 1.4 the 5 (`Policy #LDP_...` is needed.
  - `APPDATA` is `C:\users\jose\AppData\Roaming`, the host profile in the prefix, not `orbis`. The `MangoHud.conf` of W090 was left somewhere else.
- W092:
  - `WINEDEBUG=warn+seh,warn+module`, to see what DLL fails when you start.
  - The `VK_*` variables are removed from the launcher.
  - `MangoHud.conf` and the access "MangoHud Config" goes to `C:\users\jose\AppData\Roaming\MangoHud`.
  - PKG `/data/pkg/orbis-win-W092-06ec1e4fcbe2.pkg` (APP_VER 01.91).
- W092 in PS4 (`reports/wine-hardware-w092/physical/20261102T031255Z/`), with `warn+module`: `load_builtin_unixlib failed to load ".../ws2_32.so": Dynamic loading not supported` and `process_attach Initialization of L"ws2_32.dll" failed`.
  - The Unix part of `ws2_32` had never been linked to ELF. His `DllMain` fails, and with him every module that matters to him (`ERROR_DLL_INIT_FAILED`): `iphlpapi`, and by him `libMangoHud.dll`.
  - Any Windows program using Winsock had the same problem.
- W093:
  - `tools/build-unixlibs-ps4.py` compiles without patches the Unix part of `ws2_32` (`dlls/ws2_32/unixlib.c`), with the Orbis Makefile recipe, and combines it as `build-winevulkan-ps4.py`. `pw_wine_unixlibs.c` the delivery as `ws2_32.so` and `link-wine-boot.py` the link.
  - Use `gethostbyname`, `gethostbyaddr`, `getnameinfo` and `gethostname` of the libc.
  - Your `pthread_once` becomes `pw_wine_pthread_once` (`platform/ps4/pw_wine_once.c`. The kernel writes 16 bytes on the `pthread_once_t` of 4 that the headers declare.
  - `dnsapi` has no Unix part without `libresolv` (all `libresolv.c` is low `HAVE_RESOLV`), and its `DllMain` It still ends well.
  - A first attempt of W093 included `dnsapi` and left objects in `build/unixlibs-ps4`. They are not deleted (the project rule is not to delete in `build/`); the new report no longer lists them and they are not linked.
  - shortcuts of MangoHud - Windows (`README.md` of the fork): F12 shows or hides overlay, F2 activates the FPS record. They are set in `MangoHud.conf` and read with `GetAsyncKeyState`.
  - PKG `/data/pkg/orbis-win-W093-3ed12d6faf9e.pkg` (APP_VER 01.92).
- W093 in the PS4 (user photo): **MangoHud is seen over vkcube**.
  - Shows `GPU 0%`, `CPU 100%`, `VULKAN 147 FPS`, 6,8 ms and the chart of frametime (min. 4,9 ms, max. 24,0 ms).
  - The cube of Vulkan -Tools is seen with its texture (LunarG).
  - When it's loaded, the DLL also ripped the DirectX/OpenGL hook thread from the fork (`MainThread` in `src/win/main.cpp`). That thread opened a console "MangoHud" and a dialogue `Assertion failed`, in `win/d3d11_hook.cpp`, line 126, `ret == kiero::Status::Success`, for `explorer.exe`, because here all the programs run in the process of exploring. Accepting that dialogue probably ends up exploring.
  - The figures of GPU and CPU are not real:
    - The fork reads the GPU with ADL/NVML/DXGI, which do not exist in the PS4.
    - The 100% of CPU probably comes from that `SystemPerformanceInformation` and `SystemProcessorPerformanceInformation` do not report idle time in PS4 (W080); It's not checked.
- W094 (`build-mangohud.sh`): The layer DLL does not start that thread, which only uses the proxy `dxgi.dll` of the fork, and that proxy is not installed. `libMangoHud.dll` SHA256 `f9d93f7d...`. PKG `/data/pkg/orbis-win-W094-23e2179dc108.pkg` (APP_VER 01.93).
- W094 in the PS4 (`reports/wine-hardware-w094/physical/`): `vkcube` presents some 162 - 168 FPS in 500x500, and `vkspin64` at about 210 - 228 FPS, Both with MangoHud.
  - Unlike W093, no `conhost` is released apart for MangoHud. There is no console of MangoHud or an assertion dialogue.
- W095: modules debugging sections PE64 were removed to reduce the load memory. The user confirmed operation; seven sessions were recovered in `reports/wine-hardware-w095/physical/20261102T102045Z/`. Vkcube comes out with 0 in the 5 and 7 sessions, after closing glxgears. By combining applications, the sessions 2 - 4 record memory exceptions and the session 4 a statement of ImGui in two threads. See `analysis.md` next to the logs.
- [W096](HARDWARE_W096.md): serializes the shared overlay life cycle and drawing and corrects the selection / restoration of contexts. Compile as APP_VER 01.95. The ELF base of Wine is the same as W095; The only file other than the runtime is `libMangoHud.dll`. The correction of percentages CPU/GPU is pending. The local matrix is omitted on the basis of the user's indication; the physical validation of several simultaneous applications is pending.
