<a id="programas-de-32-bits-como-huéspedes-de-explorer-factibilidad"></a>


# 32 bit programs as guests of explorer: feasibility

[English](investigacion-wow64-en-explorer.md) | [Español](investigacion-wow64-en-explorer-es.md)

Read-only research (2026-11-03). No code was changed, no code was compiled and the FTP was not touched. References to Wine: `.deps/wine/source` (Wine 11.17, commit `490f6d5d`), unless the overlay of PS4 (`.deps/wine/ps4-overlay` is indicated.

<a id="resumen"></a>


## Summary

- **It can, but it is a large and at risk work.** Wine decides WoW64 once per process, in several layers: ntdll Unix (`wow_peb`, `is_wow64()`), wineserver (`process->machine`), ntdll PE (`init_wow64` only in the boot) and wow64.dll (`process_init` read the process machine). No piece is designed to activate WoW64 late in a process of 64 bits.
- **What helps:** backend `wow64native` does not prevent a late start. Unix libraries (win32u, vulkan) already decide by thread with `TEB->WowTebOffset`. The 64 bit Wine TEB already brings a prepared TEB32 on each thread. And the guest model of 64 bits already solved the part "program within another process."
- **Proposed design:** a single "world of 32 bits" per session. It is created the first time that a program of 32 bits is opened, on an EXE host of 32 bits of its own, and is left alive until the app is closed. The 32 bit programs are guests of that world, with the same mechanism as the 64 bit programs, also compiled for i386.
- **Estimate:** between 15 and 25 builds, with 1 or 2 probes at the beginning that can cut the plan.
- **Main risks:** a failure of a game of 32 bit grave explorer and all programs open. The space below 4 GiB becomes shared. The configuration that today is by process (raw signals, rendering of wined3d, `WINE_PS5_FIT`) is no longer able to be chosen by program.
- **Recommendation:** first make the relaunch less visible, which costs 1 or 2 builds. The mode in process should be addressed only if the two probes in the 8 section are good. A second process of PS4 with its own Wine is not viable.

<a id="1-wow64-por-proceso-qué-asume-una-sola-máquina"></a>


## 1. WoW64 by process: what one machine assumes

<a id="ntdll-lado-unix"></a>


### ntdll, Unix side

- `wow_peb` is a global (`dlls/ntdll/unix/env.c:68`). `is_wow64()` is `!!wow_peb` (`dlls/ntdll/unix/unix_private.h:84`). It is fixed only if the main image is not 64 bit (`env.c:1851-1858`), and right there it is put `WowTebOffset` in the first TEB.
- The TEB32 already exists on each thread. `init_teb` always fills it in a 64 bit build, and it only puts `teb64->WowTebOffset` if `is_wow` (`dlls/ntdll/unix/virtual.c:4011-4031`). What is missing, then, is to turn on the thread mark, not to create new structures.
- The first block of TEB is reserved below 2 GiB (`virtual.c:4087`). The following blocks use `user_space_wow_limit` (`virtual.c:4128`), which in a process of 64 bits is worth 0, or without limit (`virtual.c:204`; only set for WoW64 in `virtual.c:5117-5123`). From the thread 31, a TEB of a thread of 32 bits could be above 4 GiB, where the code of 32 Bit's not coming.
- The PEB32 goes in `peb + page_size` (`env.c:1856`). That page is already compromised in every process of 64 bits, because the BEP block is committed whole (`virtual.c:4091-4093`).
- The 32 bit DLL ntdll is mapped only in the boot: `load_wow64_ntdll(main_image_info.Machine)` (`dlls/ntdll/unix/loader.c:1876`, body in `1806-1826`).
- The 64 bit pile and the CPU area of a thread WoW64 are assembled in `init_thread_stack` with `main_image_info.Machine` (`dlls/ntdll/unix/thread.c:1195-1210`).
- `get_cpu_area` look `is_wow64()` and then read `TlsSlots[WOW64_TLS_CPURESERVED]` without checking if it is NULL (`thread.c:1154-1160`). If `is_wow64()` becomes true throughout the process, each 64 bit thread of scout that comes in there reads a NULL. That check has to go by thread.
- Other uses of `is_wow64()` or `wow_peb` that are no longer correct in a mixed process:
  - `process.c:1427`: `ProcessWow64Information` returns `wow_peb`. wow64.dll you need it, but `IsWow64Process` from a program of 64 bits would go on to give TRUE.
  - `process.c:1474` and `1764`: `ProcessExecuteFlags`.
  - `virtual.c:4335`: `NtSetLdtEntries`.
  - `system.c:3809`, `server.c:459` and `621`: system information.
  - `thread.c:1079-1109`: server contexts with `main_image_info.Machine`.
  - `thread.c:1687`: cleansing events.
  - In total there are 16 uses of `main_image_info.Machine` in `dlls/ntdll/unix/*.c`.
- Selectors: `cs32_sel` and `fs32_sel` are fixed at `signal_init_process` only if the first thread is WoW64 (`dlls/ntdll/unix/signal_x86_64.c:2821-2829`). In Orbis, `tools/build-signal-ps4.py` puts `cs32_sel = 0x33`, but within it `if`. The initial context of 32 bits of a new thread depends on `get_cpu_area` (`signal_x86_64.c:2936-2951`), that is, on the same mark.

### wineserver

- The machine is stored by process: `process->machine` (`server/process.c:613` and `1272`). The first image (`server/mapping.c:1680-1687`) is fixed when mapping.
- `set_thread_context` and `get_thread_context` reject a context WoW whose machine is not that of the process (`server/thread.c:1918-1954`, `2198`, `2281-2282`). In an AMD64 process, an i386-by-thread context gives `invalid_param`. As the server is on the same ELF (W011), the change is one more patch, but it has to be done.
- Mapping a 32 bit DLL in an AMD64 da `STATUS_IMAGE_MACHINE_TYPE_MISMATCH` (`mapping.c:1691-1695` process. It is an informative state: the ntdll of 32 bits does not treat it as error (the conversion of `loader.c:2839-2842` exists only in `_WIN64`). Low risk, to confirm with the probe.

<a id="ntdll-lado-pe-64-bits"></a>


### ntdll, PE side (64 bit)

- `LdrInitializeThunk` already decides by thread: if `NtCurrentTeb()->WowTebOffset`, enter `init_wow64` (`dlls/ntdll/loader.c:4498` into the start, `4537` in later threads).
- `init_wow64` load wow64.dll only if `!imports_fixup_done` (`loader.c:4340-4369`). In exploring that indicator it is already TRUE, so the first thread of 32 bits would call `pWow64LdrpInitialize` with the pointer in NULL. It takes an indicator of its own to load wow64.dll late. In addition `build_wow64_main_module` records as the main module the image of `Peb->ImageBaseAddress`, which is to explore and not an EXE of 32 bits.
- The TLS indices reserved for wow64 (`WOW64_TLS_*`, up to `WOW64_TLS_MAX_NUMBER`) are only reserved if the first thread is WoW64 (`loader.c:4480`). In explorer, `TlsAlloc` you may have distributed those indices to DLL of 64 bits. It can be solved by saving them when starting when there is `WINE_PS4_GUESTS`.

### wow64.dll

- `Wow64LdrpInitialize` does `process_init` only once and `thread_init` on each thread (`dlls/wow64/syscall.c:1486-1492`). That distribution is just as good.
- `process_init` (`syscall.c:984-1063`) takes the `RtlWow64GetProcessMachines` machine, which comes from the server. In an AMD64 process that gives AMD64, and `get_cpu_dll_name` ends the process with "unsupported machine" (`syscall.c:911-923`). You have to fix i386 in our wow64.dll, which is already an adapted version (`tools/build-wow64native-ps4.py`).
- Use `ProcessWow64Information` to find the PEB32 (`syscall.c:999`) and `SystemEmulationBasicInformation` for the address limit (`syscall.c:996-997`). That limit comes out of `user_space_wow_limit`, which today is worth 0 in exploring.
- The rest (system call tables, system redirection 32, `init_image_mapping`) is only used by 32 bit threads. It doesn't interfere with exploring.

<a id="kernelbase-win32u-y-vulkan"></a>


### kernelbase, win32u and vulkan

- `kernelbase/main.c:47` consult `IsWow64Process` when loading, once.
- win32u and vulkan already decide by thread:
  - `dlls/win32u/syscall.c:176`, `class.c:1104` and `rawinput.c:474`;
  - `dlls/win32u/vulkan.c:1178`: the mapping test below 4 GiB in 32 bits. This is what makes the design thinkable.

**Answer to question 1:** cannot be turned on WoW64 "on demand" with what brings Wine. It is necessary to separate "the process has a world of 32 bits" (`wow_peb` not null) from "this thread is 32 bits" (`WowTebOffset`) in ntdll Unix, on the server and in the input of ntdll PE. The pieces that follow at that point (wow64.dll, the backend, win32u) already work by thread or are fixed with little.

<a id="2-modelo-de-huéspedes-y-qué-necesitaría-uno-de-32-bits"></a>


## 2. Guest model and what would need one of 32 bits

Today (`tools/build-guest-hw.py`)

- `ps4_guest_image` accepts only `IMAGE_FILE_MACHINE_AMD64` (`build-guest-hw.py:205`).
- `ps4_guest_launch` (`:464`) load the EXE with `LoadLibraryExW` using the mark `PS4_GUEST_LOADING` (`:553`) and starts the entry into a new thread. The thread is carried by the host in `TEB.UserReserved`.
- per guest: command line, `GetModuleHandle(NULL)`, argv of Ukraine (W057), table `atexit` (W184, `struct ps4_guest` in `:43-56`), end of threads, windows and classes (W060 - W069), exception filter (W114.
- A PE32, or a program with `OrbisRunsAlone` (W183, `:453`, passes through the dialogue and by `NtCreateUserProcess` → `pw_hw_switch_program` (`build-guest-hw.py:607-655`, `tools/prepare-wine-boot.py:616-652`, `native/wine_hardware.c:157-185`).

A guest of 32 bits would need:

1. **A world of 32 bits.** The ntdll of 32 bits has its own charger status: `LdrData` in the PEB32, its lock and its heap. The first thread WoW64 in `LdrInitializeThunk`, which also loads kernel32, kernelbase, user32, makes it and ucrtbase 32 bit and EXE `PEB32->ImageBaseAddress`. That state cannot be redone in the same process. Therefore the PEB32 should target a **EXE host of 32 own bits** (e.g. `orbis32host.exe`, tiny) and not the program.
   - A PEB32 per guest makes no sense: the ntdll of 32 bits is one and its status is global.
   - A shared PEB32 is the same thing that makes you explore for guests of 64 bits.
2. **The guest patches compiled for i386.** They are ntdll (`loader.c`), kernelbase (`loader.c`, `thread.c`, `process.c`) and ucrtbase (`data.c`, `exit.c`). Today they are compiled only for `x86_64-windows` (`build-guest-hw.py:715`). In i386 the mark in `TEB32.UserReserved` works the same. The 32 bit DLL system have separate names from those of 64 bit (another `LdrData`), so do not collide with those of Pale Moon (W182. Between two guests of 32 bits can crash.
3. **A bridge between bitness.** The `CreateProcess` of explorer (64 bit) sees a PE32 And you have to ask the world of 32 bits to load it. The most direct way is to create a WoW64 thread whose input of 32 bits is an export of the host (`ps4_guest32_start`). The parameter would be a block below 4 GiB with the route and command line. That thread does in 32 bits the same as `ps4_guest_launch`. A new thread inherits the mark WoW64 of the one who creates it (in `NtCreateThreadEx` Unix: if the thread he calls is WoW64, the new one also). The first one creates it to explore with an explicit indicator.
4. **The thunks of wow64 by thread.** Come out alone: `thread_init` wow64 runs on each 32 bit (`syscall.c:1069-1120` thread.
5. **The reverse sense, from 32 to 64 bit**, when a program of 32 bit launches one of 64. In a first version it can be rejected or sent to the relaunch.

<a id="3-backend-de-cpu-wow64native"></a>

## 3. CPU backend (wow64native)

- `BTCpuProcessInit` (`upstream/prospero-win/wine/wow64native/cpu.c:549-622`) does the following:
  - check that your thunks are below 4 GiB (the DLL is at `0x7a400000`, `tools/build-wow64native-ps4.py:132`);
  - initializes xstate;
  - calls `pw_native_process_init` on the Unix side, which requests the signal capabilities (`unix.c:175-214` and the Orbis adaptation in `build-wow64native-ps4.py:59-77`;
  - write two thunks of far jump and set constant selectors (`PW_NATIVE_CS32` and the others). It does not depend on the main thread or the first code of the process. He sees no difference between running at the start or in the middle of the session.
- `BTCpuThreadInit` (`cpu.c:633-637`, `unix.c:216-245`) stores the FS of the thread host and associates the TEB32 (requires it to be below `0xfffff000`). The state is `__thread`, by thread. A thread of 64 bits of explorer that never calls `BTCpuThreadInit` is not affected.
- `BTCpuThreadTerm` (with the arrangement of W170) only clean the current thread.
- **Process requirement:** `PW_NATIVE_SIGNALS=1`, the raw signal input of W136 (`platform/ps4/pw_wine_signals.c`, `tools/build-signal-ps4.py`). Today it is only passed to PE32 (`native/wine_hardware.c:679-688`). With guests of 32 bits it would have to be always active, with explorer and all programs of 64 bits. The raw input keeps the FS of the host in each thread (`pw_host_fs`), so in principle it is neutral for the threads of 64 bits. But it was never tested with an explorer.
- **Answer:** a `process_init` late is possible. It can also be done when you start scanning: loading `wow64native.dll` and calling your `BTCpuProcessInit` is cheap, and leaves the failure in sight from the start. What cannot be advanced without cost is the initialization of ntdll 32 bit (kernel32, user32 and other 32 bits): takes memory below 4 GiB and start time.

<a id="4-espacio-de-direcciones"></a>


## 4. Address space

What the logs show:

- Wine in the PS4 is limited to `0x7ffff0000` (32 GiB: `PWBOOT virtual_step addr_space_limit=0x7ffff0000` in all runs (`.deps/wine/ps4-overlay/dlls/ntdll/unix/virtual.c:3775`).
- In an explorer (`reports/wine-hardware-w186/physical/20261104T002752Z/run-0001.log`):
  - `explorer.exe` is in `0x140000000`, and the DLL of 64 bit in `0x7FDxxxxxxx` - `0x7FFxxxxxxx` (lines `trace:loaddll`);
  - the heap of `virtual` is in `0x20095c000`;
  - The guests of 64 bits were charged in `0x1001xxxxx` - `0x101EFxxxx` (marks `PS4 guest ... module` in W18x).
  - All this is above 4 GiB.
- What is below: the ELF of the title (base `0x400000`, `docs/INCREMENT_13.md`; Unix addresses as `0x908fe0` in `PWVK lookup`), the first block of TEB and the PEB (below 2 GiB, `virtual.c:4087`).
- In the 17 32 bit runs of W17x and W18x (SuperMarioKart), the `PWVM commit` commitments of 1 MiB or more go from `0x3040000` to `0x20510000`. They are about 500 MiB used in the lower area, unexplored.
- In the 55 scout runs and the 8 of 64 bits alone there is no line `PWVM commit` below 4 GiB. **Not enough to say that explorer leaves the low area free:** the log only records commitments of 1 MiB or more, and the girls assignments of 64 bits (heaps, batteries, sections) do not appear. A probe is needed (section 8).

What changes in a mixed process:

- The 64 bit assignments that do not ask for direction can fall below 4 GiB and compete with the 32 bit program. Wine only remove them if the main EXE has `HIGH_ENTROPY_VA` and `DYNAMIC_BASE`, and in that case it does the opposite: it releases the low reserve (`virtual.c:5106-5116`).
- Proposal: when you start exploring (with `WINE_PS4_GUESTS`), reserve an area below 4 GiB (e.g. 2 - 3 GiB) which is only used for 32 bit thread assignments, WoW64 thread TEB and Vulkan 32 located mapping bits (`VK_EXT_map_memory_placed`, W124). So exploring doesn't take care of it. It is the same resource that you use Wine with `reserve_area` for WoW64 with LAA (`virtual.c:5121`).
- The physical memory of the title (direct and flexible memory, `PWVM commit_backing`) is one. A game of 32 bit more explorer and open guests are distributed the same budget, which today the game has for it alone.

<a id="5-antecedentes"></a>


## 5. Background

- **Windows:** a process is 32 or 64 bits. WoW64 is by process, and Windows only allows your own 64 bit DLL inside a process of 32 bit, never code 32 bits within a native process of 64 bits ([note on 32 and 64 bits in the same process](https://jiangsheng.readthedocs.io/en/latest/blogs/2018/06/can-we-run-32-bit-and-64-bit-code-in-the-same-process.html)).
- **Wine, new WoW64 mode:** the decision is by process and depends on the main image (`env.c:1851`). There's no mixed way. The most similar is ARM64EC (`is_arm64ec()`, x64 and ARM64 in a process), but the two are 64 bit: it does not solve 32 bit points or the limit of 4 GiB.
- **prospero-win:** one game per process. Choosing a game relays the title with `sceSystemServiceLoadExec` and closing it back to the pitcher (`upstream/prospero-win/docs/ARCHITECTURE.md:56-60`). It's the same model as our relaunch. His `WINE_INTEGRATION.md:145-150` also says that several programs in a title would share the same sandbox.
- **Hangover/FEX:** use `libwow64fex.dll` as CPU WoW64 for 32 bit processes and ARM64EC for x86_64. The decision is also by process ([Hangover](https://github.com/AndreRH/hangover)). I found nothing to run several worlds WoW64, or WoW64 along with native programs of 64 bits, in the same process.
- **Partial antecedent:** NTVDM and winevdm perform several tasks of 16 bits within a single host process, with a shared subsystem. It's the same way as the "world of 32 bits with host" proposed here, although the mechanism is another.

Conclusion: there is no reference implementation. The design would be your own.

<a id="6-alternativas-más-simples"></a>


## 6. Simpler alternatives

<a id="6a-relanzamiento-más-disimulado-recomendada-a-corto-plazo"></a>


### 6a. More disguised relaunch (recommended in the short term)

- Today the scout desk takes about 8 - 9 s of process time to show its layers (`frame_presented n=6 ... layers=1 t_ms=7984` in W186 run- 0001. Before there is the test of Vulkan of the launcher (`vk_probe_start` / `vk_probe_end`, 0,85 s) and the closure of the system (`wait_for_system_close`, up to 10 s, `native/wine_hardware.c:113-118`). The wall time of the closing and turning is not in the logs.
- Possible improvements, all in the pitcher and without touching Wine:
  - Save the last box of the desktop in `/data/orbis-win/` when calling `pw_hw_switch_program`, and use it as a background of the load screen (W170) in the relaunch and in the turn, instead of the logo on black.
  - Skip the test of Vulkan in the relegated runners.
  - Measure the wall time of a full cycle with marks on the log and a wall watch.
- **That the 64 bit programs remain alive is not possible with this path:** `LoadExec` the process ends. All you can do is note which guests were open (route and command line) and re-open them on their return. Your status is lost (unsaved documents, for example), and the current dialogue already warns you.

<a id="6b-un-segundo-proceso-de-ps4-con-su-propio-wine"></a>


### 6b. A second process of PS4 with its own Wine

It is not feasible:

- The title cannot create processes: `fork` and `exec` are rejected (`docs/INCREMENT_13.md:100-103`, `docs/INCREMENT_14.md:43-46`), and W052 part of that (`docs/HARDWARE_W003_W011.md:1108`).
- Another title released with the system launcher would be another installed application. The PS4 has a single main application in the foreground, and open another one suspends or closes the current one.
- The wineserver is within the process and passes descriptors with `SCM_RIGHTS` inside it (W011). Sharing it between two isolated processes is not proven, and VideoOut belongs to a single process.
- The app does not make jailbreak (`docs/HARDWARE_W180.md:116`). Using the capabilities of GoldHEN for that would be a separate decision, and still the two previous obstacles would remain.

None of these claims about the system launcher were tested on the console. But they're enough to rule it out in front of 6a.

<a id="7-diseño-propuesto-para-el-modo-en-proceso"></a>


## 7. Proposed design for the in-process mode

A world of 32 bits per session, created the first time it opens a PE32 and never destroyed.

| # |Piece|Change|Where|
|---|-------|--------|-------|
| 1 | ntdll Unix |`pw_wow64_enable()`: fill the PEB32 (the `env.c:1864-1900` and `build_wow64_parameters`), set `user_space_wow_limit = limit_4g-1` and reserve the low area, load `ntdll` i386 (`load_wow64_ntdll(I386)`), fixed `cs32_sel = 0x33`|overlay of `env.c`, `loader.c`, `virtual.c`, `signal_x86_64.c` (via the building of ntdll)|
| 2 | ntdll Unix |Mark WoW64 by thread: `init_teb` and `init_thread_stack` by thread indicator, `get_cpu_area` check NULL, `NtCreateThreadEx` inherits the mark of the calling thread or the taking of an explicit indicator, TEB of threads WoW64 below 4 GiB, `ProcessWow64Information` responds according to the thread| `thread.c`, `virtual.c`, `process.c` |
| 3 | wineserver |Accept context WoW i386 by thread in an AMD64 process|`server/thread.c:1918-1954`, `2198-2308`|
| 4 |ntdll PE 64|`init_wow64` late: load wow64.dll with its own indicator, without `build_wow64_main_module` EXE to explore; reserve the `WOW64_TLS_*` indexes when starting| `dlls/ntdll/loader.c:4340-4369`, `4480` (in `build-guest-hw.py`) |
| 5 | wow64.dll |`current_machine = I386` fixed when the process machine is AMD64|`tools/build-wow64native-ps4.py` (already adapted `syscall.c`)|
| 6 |Amphitrium|`orbis32host.exe` (PE32): minimum loop, export `ps4_guest32_start`|new program, like those of `tools/build-*-hw.py`|
| 7 |Owners i386|The patches of `build-guest-hw.py` also for `i386-windows` (ntdll, kernelbase, ucrtbase| `tools/build-guest-hw.py:713-731` |
| 8 | kernelbase 64 |In `CreateProcessInternalW`, a PE32 passes into a thread WoW64 of the host instead of dialogue and relaunching; no change for `OrbisRunsAlone`| `build-guest-hw.py:603-660` |
| 9 |Launcher|`PW_NATIVE_SIGNALS=1` and `WINE_PS4_WOW64_CPU` always; the yield of wined3d per program (record `AppDefaults\<exe>\Direct3D`, without the global variable `WINE_D3D_CONFIG`); `WINE_PS5_FIT` only for relaunch| `native/wine_hardware.c:609-688` |

Detalles:

- What you can do when you start exploring: the low area, the indices TLS, load `wow64native.dll` and its `BTCpuProcessInit`. What should be done late: the ntdll i386 and the host, not to spend low memory or time if no 32 bit program is opened.
- The relaunch is maintained as an option: a PE32 marked `OrbisRunsAlone` (games that need the entire screen with `WINE_PS5_FIT`, or the entire memory budget) is on the way today.
- An unhandled failure in a 32 bit thread reaches the world exception filter of 32 bit. It has to be turned into the exit of that guest (the `ps4_guest_exit_process` of 32 bit) and not at the end of the process. Today guests of 64 bits are not isolated from this (W113/W114) either.

<a id="riesgos"></a>


### Risks

- **Isolation:** today a game of 32 Failing bits only ends their own relaunch. In process, a failure in compatibility mode or in the backend (FS of the guest, selector, signals) ends the full title, with explorer and what is open. W165-W170 show that such failures existed. It's the biggest risk to the user..
- **Always active raw signals:** `PW_NATIVE_SIGNALS=1` never ran with explorer, Mesa, DXVK or Pale Moon.
- **Low and total memory:** see section 4.
- **GPU:** the render Vulkan of wined3d for 32 bits passes winevulkan WoW64 towards ps5drv, in the same process as the Khronos loader and MangoHud. W127 just separated that by process. The Vulkan 32 bit located mapping is competing in the lower area.
- **Display:** `WINE_PS5_FIT` (W155) is by process. On the desktop, a set of 800x600 would be seen in window, not scaled to full screen.
- **surface of Wine:** are changed ntdll Unix, server and load of ntdll PE at points that today do not have patches of PS4. Each update of Wine needs to be rechecked.
- **Contention with other sessions:** several of these pieces live in files that share other buildings (`platform/ps4`, ntdll). See the memory notes on shared files.

<a id="estimación-en-builds"></a>


### Estimate in buildings

| Etapa | Builds |Closing criteria|
|-------|--------|--------------------|
|Songs (section 8)| 1-2 |Low map 4 GiB of explorer; explore with `PW_NATIVE_SIGNALS=1` and `wow64native` initialized, without regressions|
|World of 32 minimum bits (pieces 1 - 6)| 3-5 |`console32-bare.exe` or a PE32 of console runs like thread WoW64 inside to explore and ends|
|i386 and bridge guests (7 - 8)| 3-5 |A simple PE32 GUI (winemine or notepad of 32 bit) opens, closes and reopens from Start|
|GPU and 32 bit sound in process (9)| 3-6 |SuperMarioKart runs on the desktop, with fps comparable to relaunch|
|Stability| 3-5 |Two PE32 at a time, PE32 next to Pale Moon alone or guests of 64 bit, failure of a PE32 without tumbar explorer|
| **Total** | **13-23**, more 2 margin | |

The figure means the probes are going well. If the server or signals ask for more than you see from the code, the 2 stage can be doubled.

<a id="8-qué-probar-primero-en-la-consola"></a>


## 8. What to try first on the console

A single probe build, without changing visible behavior:

1. **Map below 4 GiB with explorer.** With the desktop ready and after opening and closing a couple of guests, go through `NtQueryVirtualMemory` from `0x10000` to `0x100000000` and record each region (base, size, state, type). Suggested mark: `PWWOW lowmap`. It answers if there are 2 GiB free contiguos and who occupies the lower area.
2. **Raw signals with explorer.** Start explorer with `PW_NATIVE_SIGNALS=1` and verify `PWNATIVE signals raw=1` and `PWNATIVE caps=3`. Use the desk, a 64 bit guest with OpenGL (W172/W173) and Pale Moon alone. If there are regressions, the design in process does not follow.
3. **Late Backend.** From a scout thread, load `wow64native.dll` and call `BTCpuProcessInit`. Wait `wow64native initialized: cs32=0033 ...`. It does not run 32 bit code: just confirms that the DLL enters into `0x7a400000` with loaded explorer and that the Unix side accepts initialization.

If all three give well, just there it is necessary to face the pieces 1 - 3, which are the ones with the most uncertainty.

<a id="recomendación"></a>


## Recommendation

1. Now: 6a (desktop picture during relaunch, without proof of Vulkan in relaunched runs, measure the cycle). They are 1 or 2 build and improve what the user sees.
2. Then, if you want to move forward: the probe build in section 8. Decide with your results.
3. The mode in process, if done, should live with the relaunch (`OrbisRunsAlone`) and start with programs of 32 simple bits, not games.

<a id="9-resultado-de-la-sonda-b0-w232"></a>


## 9. B0 probe result (W232)

The work plan is in the note `pe32-en-explorer-plan.md` of the shared session folder. B0 ran in W232, the 2026-11-04 at 21: 50, with the log in `reports/wine-hardware-w232/physical/20261105T005111Z/run-0001.log`. He gave well on all three points:

- **Raw signals in explorer.**
  - The traces: `PWNATIVE signals raw=1 syscall=0x80000087a hits=1 mxcsr=0xbfe1/0xbfe1 fsbase match` and `PWNATIVE caps=3 cs64=43 ss64=3b`.
  - Explorer was still alive after: there was a beat of `PWSHELL` and pictures presented.
  - The probe `compat32` gave `native32=1 cs=0x43 result=0x32beef32 signal=0`.
- **Low area.**
  - Measuring: `lowmap largest_free=0x8001f000 at=0x7ffe1000`, i.e. 2 GiB free contiguous above 2 GiB.
  - So the world of 32 bits uses the limit of a program * large address aware * (`0xffffffff`).
- **Late Backend.**
  - Measured: `cpu module=0x7bfe0000 below_4g=1` and `BTCpuProcessInit status=0 cpu_flags=0x1`.
  - The log does not have the literal line `wow64native initialized` that the plan expected. It has, on the other hand, `PWNATIVE wow64native caps=3 (no xstate in exception contexts)`, coming from the Unix side.
  - That message is written `WINE_MESSAGE` from the PE side of wow64native, and this log does not appear. This is why the new tracks on the PE side use `ERR`, which does reach the log (they are the same as the lines already used `PWGUEST`).

<a id="10-b1-el-mundo-de-32-bits-mínimo-preparado-sin-probar-en-consola"></a>


## 10. B1: the world of 32 minimum bits (prepared, untested in console)

Objective (B1-B3 of the plan): that `C:\orbis\console32.exe` runs as thread WoW64 within the scout, type `result.txt` and finish, twice in a row, and that scout continues to work.

It is delivered as `wow64-b1-world.patch.py` in the shared session folder. The new files are in `b1/`.

<a id="qué-cambia"></a>


### What changes

- **ntdll Unix (P1, `tools/build-wow64-world-ps4.py`, new builder)**
  - `is_wow64()` goes by thread when the main image is 64 bit: the thread has 32 bit TEB. With 32 bit image (the relaunched mode) it responds as before.
  - **The world is created late, on request.** `NtSetInformationProcess` with the class 1100 weapon:
    - the PEB32, the image of which is the host;
    - the ntdll i386, with a return status instead of `fatal_error`, and maintaining the Ctrl routine to explore;
    - the map of API sets below 4 GiB;
    - the address limit of 32 bits.
  - **Thread WoW64 from 64 bit code.** `NtCreateThreadEx` accept the flag `0x01000000` to create a thread WoW64 from one of 64 bits. The TEB is below 4 GiB, the area CPU is i386 and the code selector is `0x33`.
  - **Answers by thread.** `ProcessWow64Information` and `get_cpu_area` respond by thread.
  - **`TlsFree` clean the slot only in the threads of your own world.** The chargers of 32 and 64 bits share the same indexes from different bitmaps. Without this change, a `TlsFree` of 64 bits erased the slot 1 (`WOW64_TLS_CPURESERVED`) of the threads of 32 bits.
  - **Refined units.** The 11 units that read the state WoW64 are rewarded: the 6 tested and those of env, signal, system, virtual and file, taken from their own builders and verified by hash. The builder checks that no other unit reads that state.
- **ntdll PE (P3, `build-guest-hw.py`).**
  - `wow64.dll` is loaded with the first thread of 32 bits even if the process is already started.
  - If that load fails, finish the thread and not the process.
  - `KiUserExceptionDispatcher` only passes by `Wow64PrepareForException` in threads WoW64.
- **wow64 (P4, `build-wow64native-ps4.py`).**
  - `wow64.dll`:
    - in a process of 64 bits emula i386 for the thread WoW64;
    - a `NtTerminateProcess` from 32 bit code never ends up exploring: "the others" are rejected and "myself" ends only the thread, with trace;
    - a load failure ends the thread.
  - `wow64native.dll`: if a thread of 32 bits is missing, finish that thread.
  - **`wow64win.dll`.** I found a problem that the plan did not have: its `DllMain` replaces `PEB->KernelCallbackTable`. Within the scout, that would have diverted all callbacks from user32 from 64 bit to thunks from WoW64 as soon as I pulled the first thread of 32 bits.
    - Now, in a process of 64 bits, leave the PEB table intact and put yours in `TlsSlots[18]` of the thread, within the reserved range of WoW64.
    - `wow64.dll` the copy on each thread WoW64.
    - The `KiUserCallbackDispatcher` of the ntdll PE is used only in threads WoW64.
- **Host (P5, `fixtures/win32/orbis32host.c`)**
  - It is `C:\windows\syswow64\orbis32host.exe`, with `0x30000000` base, and exports `ps4_guest32_start`.
  - For B1 load the EXE with `DONT_RESOLVE_DLL_REFERENCES`. The ntdll i386 standard does not relocate or solve an EXE loaded as a module and calls its input as `DllMain` (W052/W053 in 64 bits). That's why the host replaces it, solves its imports and points its `ExitProcess` from kernel32 to a own output, which returns to the host and downloads the program.
  - An EXE with TLS is rejected with a trace up to P6.
- **Launcher (`native/wine_hardware.c`).** With the B marker0 (`C:\orbis\wow64probe.txt`), explorer also receives `WINE_PS4_WOW64_CPU=wow64native.dll`.
- **Test trigger.** `C:\orbis\wow64world64.exe` (`fixtures/win32/wow64world.c`) is a host of 64 bits that create the world and run the program twice. Write `C:\orbis\wow64world-result.txt`.

<a id="qué-se-verificó-sin-consola"></a>


### What was verified without a console

- **Script de parche.**
  - Apply on copies of the four shared files.
  - A second pass responds `already applied`.
  - The resulting builders compete as Python.
- **Compilation.**
  - The 11 Unix units compile, and the new symbols are resolved between them (`ld -r`).
  - The ntdll PE compiles and links; The disassembly shows the two `cmpl $0,%gs:0x180c`.
  - `wow64.dll`, `wow64win.dll` and `wow64native.dll` compile and link.
  - The host and the trigger compete with mingw: the host has the export and relocations.
- **Full link.** The ELF hardware links with the 11 new objects. A copy of `build-wine-hardware.py` cut after the link was used. No imports of the kernel were statically defined.

Everything was done in a temporary folder, without touching `build/` or `out/`.

<a id="riesgos-que-quedan"></a>


### Risks left

- **Server (P2).** It didn't touch. If anything asks the i386 context of a thread WoW64 from another thread (suspension, debugging), the server treats it with the process machine (AMD)64). `console32.exe` He doesn't need it..
- **`0x30000000` and `0x400000` free.** Yes `0x30000000` He's busy, the trigger says so (`host_not_at_base`). If `0x400000` is occupied, the host replaces `console32.exe`, which has relocations.
- **Scout routes that remain global.**
  - `p__wine_ctrl_routine` is preserved.
  - The branch of `wow64.dll` that ends the process when the machine is not supported remains the same, but is not reached with i386.
  - An unhandled exception in 32 bit code can still finish the title until P6 brings the guest exception filter.
- **Unmeasured assumption.** No code of 64 bits other than ntdll, wow64 and win32u runs in threads of 32 bits, so `TlsSlots[18]` does not run with a slot of `TlsAlloc` of 64 bits.

<a id="11-resultado-de-b1-w233-y-corrección-w234-preparada-sin-probar-en-consola"></a>


## 11. B1 (W233 result and correction W234 (prepared, not tested in console)

In W233 the world of 32 bits was not created: `PWWOW world_failed status=0x4000000e host=0x30000000` (`reports/wine-hardware-w233/physical/20261105T095116Z/run-0005.log`). The first `status=0xc0000225 host=0` is the expected answer ("there is no world yet; map the host ").

- **Cause.** `0x4000000e` is not `STATUS_IMAGE_NOT_AT_BASE` (`0x40000003`) but `STATUS_IMAGE_MACHINE_TYPE_MISMATCH`, an information state. wineserver (`server/mapping.c`, `map_image_view`) puts it after mapping the view when the image machine is not the process. For the server, explore is AMD64, so every i386 image receives it: the host (which `wow64world64.exe` already accepted) and the ntdll of 32 bits in `pw_wow64_load_ntdll32`, which took it as a failure. The server also puts it after `NOT_AT_BASE`, so it also covers a load off the base.
- **Correction** (`wow64-w234-ntdll32-status.patch.py`, only changes `tools/build-wow64-world-ps4.py`): with either of the two states it is called `virtual_relocate_module`, that does nothing if the image is at its base; the ntdll of 32 bits is limited to less than 2 GiB, as in a process WoW64; a failure leaves `PWWOW ntdll32 failed`.
- **The rest of the DLL from 32 bits don't need it..** The PE of i charger386 (`load_native_dll`) treats that state as success and `build_module` relocations.
- **Verified** in a copy: the patch is applied once and rejects the second, the builder is analyzed, and `loader.c` compiles with the proven recipe. The test is missing on the console.

<a id="12-resultado-de-b1-w234-y-w235-abrir-un-pe32-lo-corre-dentro-de-explorer-preparado-sin-probar-en-consola"></a>


## 12. Results of B1 (W234) and W235: open a PE32 runs it within the scan (prepared, untested in console)

**W234.** B1 passed: `console32.exe` ran twice as thread WoW64 of scout, without relaunching (`reports/wine-hardware-w234/physical/20261105T102836Z/run-0001.log`, lines 1943 - 2081), with output 0 twice. The `rewritten=0` of the second Runs came from the check, not from the program: it compared the time of last writing, and the second writing (13 ms, the same text) fell in the same instant. W235 writes `pending` in `result.txt` before each Runs.

**W235** (`wow64-w235-world-launch.patch.py` plus `w235/` Unite P6, P7 and P8:

- **P7, the bridge.** In the kernelbase of 64 bits, `CreateProcessInternalW` with a PE32 create the world if necessary (mapeia) `orbis32host.exe` in `0x30000000` and asks for the class 1100) and run `ps4_guest32_launch` of the host in a thread WoW64. That thread calls the `CreateProcessW` of 32 bits. The caller receives the first thread of the guest and a handle to this process, as with a guest of 64 bits. Okay for the desktop, the Start menu and WFM.
- **The relaunch remains as a backup:**
  - for a PE32 with `OrbisRunsAlone` (W183);
  - for everything PE32 while there is `C:\orbis\pe32relaunch.txt`, which also takes you away from exploring raw and wow64native signals;
  - when the world fails: the dialogue of always, but with the error in sight.
- **P6, i386 guests.** `build-guest-hw.py` compiles the same reviews of ntdll, kernelbase and ucrtbase also for i386 (`out/guest-hw-i386`). For i386:
  - the image check accepts PE32;
  - the battery routes (W207, W211) follow the EBP chain;
  - a program that cannot be host returns to the side of 64 bits with error; it never reels from a thread of 32 bits.
- **Where they load.** The guest DLL i386 is going to `wine/lib/wine/i386-guest`. The ntdll Unix looks there first, and only in a process of 64 bits. So a relaunched program follows with the usual DLL i386.
- **P8.**
  - Explorer always receives `PW_NATIVE_SIGNALS=1` and wow64native, except with `pe32relaunch.txt`.
  - The environment of the world of 32 bits takes `WINE_D3D_CONFIG=renderer=vulkan`, such as relaunching. With the `renderer=no3d` of explorer, wined3d i386 was left without an adapter (ddraw, Direct3D 7).

**Verified in a copy:**
- the patch is applied once and the second one is rejected;
- the three builders are analysed;
- 11 units of ntdll Unix compile without new warnings;
- `orbis32host.exe` exports `ps4_guest32_launch` and `wow64world.c` compiles;
- `build-guest-hw.py` builds ntdll, kernelbase and ucrtbase for x86_64 and i386. The ntdll and ucrtbase x86_64, which W235 does not change, differ from the previous builder only in about 20 time marks bytes of the PE header.

**Known limits of the alpha:**
- a single current directory for the entire world of 32 bits, so two PE32 at the same time share it;
- The 32 bit console programs depend on that `AllocConsole` start conhost inside the world; if it fails, the dialogue with the error appears;
- a PE32 that launches a PE64 still has no reverse bridge;
- without window climbing: a 640x480 set is left in a window;
- an unhandled exception in 32 bits ends that thread, do not explore (B1), but still does not have the complete cleaning of a guest.

<a id="13-resultado-de-w235-y-w236-preparada-sin-probar-en-consola"></a>


## 13. Results of W235 and W236 (prepared, not tested in console)

**W235** (`reports/wine-hardware-w235/physical/20261105T110320Z`):
- The first opening of `gui-window32.exe` within the explorer worked (run- 0003).
- `console32.exe` returned to the relaunch: the side of 32 bits asked `conhost.exe`, which cannot be host of 32 bits (`not_a_guest`, error 50).
- A second opening of `gui-window32.exe` finished the title.

**Causes of the fall:**
- **(c) Window procedures.** win32u save a single table of procedures of the own classes (button, dialog...). The user32 of 32 bits of the world overwrote it with its own, and the next scout dialog received `WM_NCCREATE` in a direction of 32 bits.
- **(g) Table of GDI.** gdi32 of 32 bit reads the GDI handle table and DC attributes with 32 bit pointers, but in explorer they were above 4 GiB: truncated pointer, failure in gdi32.
- **(e) Recursion in wow64.** In the face of that failure, wow64 was repeated 207 times: the context of 32 bits had esp = 0.

**W236** (`wow64-w236-world-fixes.patch.py` plus `w236/orbis32host.c`:
- **(c)** Each world keeps its own class procedures, and every thread receives those of its world (`build-win32u-ps4.py`, `class.c`).
- **(g)**
  - The GDI table and DC attributes are always below 4 GiB.
  - `zero_bits` is by thread: what asks for a thread WoW64 (DIB bits, message buffers, Vulkan located memory) is below 4 GiB.
- **(e)** In the world, an exception without a stack of 32 bits ends that thread, with trace, rather than repeated (`build-wow64native-ps4.py`).
- **(b) Second opening**
  - The side of 32 bits no longer opens a picture: it brings the window to the front or warns that it was not found.
  - Explorer shows "it's already open."
  - An opening without thread stops counting as a failure.
  - The bridge waiting delivers the messages sent to the scout thread, so that it does not be jammed with a start of 32 bits that sends them.
- **(a) Consola.**
  - A PE32 console receives the console from the side of 64 bits (conhost as host of 64 bits).
  - The world of 32 bits receives copies of their handles in the PEB32.
  - The console is closed when the first thread of the program is finished, unless it is used by a 64 bit console program.

**Verified in a copy:**
- the patch is applied once and the second one is rejected;
- `build-guest-hw.py` builds the DLL x86_64 and i386;
- 47 units of win32u compile;
- `wow64.dll`, `wow64win.dll` and `wow64native.dll` are built, with the guard inside;
- `orbis32host.c` compila.

**Limits:**
- a console program of 32 bits at a time: the PEB32 has one console;
- if the user closes the console window, the 32 bit program continues to run without it;
- the esp background motif = 0 (the context of 32 bits that leaves the raw input of signals when failing in compatibility mode) is still open: W236 avoids recursion but does not deliver the exception to the 32 bit SEH.

**(d) W235 correction: the first window of `gui-window32` never appeared.** The opening returned OK, but the host thread (0068) He left not a line after he was created. In the log you see everything until you create the thread and resume it; after, nothing. It may not have taken off or stood in a quiet step. W236 adds a line `PWWOW` to each step of a new thread of 32 bits:
1. its creation (`PWWOW thread … from=32`, ntdll Unix);
2. `ResumeThread` (`resumed previous=1`);
3. `wow64 thread_init`;
4. the i386 (`loader_init: tls` charger, a `thread_attach <dll>` per DLL, `loader_init: attached`);
5. `start: entry`, just before the program's entry.

The last line that appears for that thread says where it stops. W236 adds `build-wow64-world-ps4.py` to the building steps.

<a id="14-w236-y-w238-los-hilos-de-32-bits-creados-suspendidos-preparado-sin-probar-en-consola"></a>


## 14. W236 and W238: the suspended 32 bit threads (prepared, untested in console)

**W236** (`reports/wine-hardware-w236/physical/20261105T114602Z`). The chain did not pass by `link-wine-boot.py`, so (c), (e) and (g) did not reach ELF: they go in W237. The traces of (d) showed the cause that no 32 bit program reached its entry:
- Any thread that creates code of 32 bits (`from=32`, `flags=0x1`, suspended) is resumed and never reaches `wow64 thread_init`.
- The ones on the bridge (`from=64`, not suspended) run, and also the thread that console32 created without suspension in B1.

**Causa** (ntdll Unix, `thread.c`):
- A suspended thread is waiting at `wait_suspend` before its first instruction.
- `contexts_to_server` sends to wineserver two contexts: the native and the i386 of the CPU area, labeled with the main image machine, which in explorer is AMD64.
- wineserver only accepts a second context in a process whose machine differs from the native (`select`), so the waiting fails in the act.
- `contexts_from_server` then writes an AMD64 context over the i386 area, and the thread is broken before starting.
- The same would happen with `SuspendThread` on a 32 bit thread in motion.

**W238** (`wow64-w238-suspended-threads.patch.py`, only `build-wow64-world-ps4.py`):
- In a process of 64 bits, the context WoW64 is not exchanged with wineserver, which does not save any for a thread of an AMD64 (P2) process. It goes only the native, as for the other scout threads, and the i386 context is where the pull-off of the thread left it.
- The relaunched program doesn't change.
- Cost: another thread cannot change the i386 context of a 32 bit thread suspended through the server.

**Verified in a copy:** is applied once and the 11 units compile. The build chain has to include `link-wine-boot.py`.

<a id="15-w238-y-w239-la-primera-ventana-de-un-pe32-preparado-sin-probar-en-consola"></a>


## 15. W238 and W239: the first window of a PE32 (prepared, untested in console)

**W238** (`reports/wine-hardware-w238/physical/20261105T121747Z`):
- `console32.exe`, open from WFM, ran whole within unrelaunched scans (`sum=500500;thread=ok;dll=ok`).
- The threads `from=32` reach their entrance.
- All PE32 graphic dies in its first window: it runs `FE9ED9E0` with `WM_NCCREATE`.

**Causes:**
- **The procedure.** `FE9ED9E0` is `ime_ui_window_proc` of 64 imm32. bits (`7FE9ED9E0`) cut to 32 bits. imm32 records "Wine IME" as a global class. In the same process it was first recorded by the 64 bit, and the IME window on the 32 bit side received its procedure. The same can happen with any global class on the side of 64 bits.
- **The recursion.** The guard of (e) did not cut her off because she looked at the Esp of the context, which was not 0. `call_user_exception_dispatcher` use `TEB32->SystemReserved1[0]` when SegSs is not `ss32_sel` of wow64, And in the world of exploring that value is 0.

**W239** (`wow64-w239-crossworld-procs.patch.py`):
- **win32u.**
  - A thread WoW64 never calls a procedure above 4 GiB: the message goes to `default_window_proc`, with a thread trace.
  - `GetWindowLongPtr(GWLP_WNDPROC)` gives him the handle instead of that address.
  - The 32 bit EMI window is as common window. There is no IME composition in explorer.
- **wow64.** The guard calculates the stack just like the dispatcher, so that exception ends its thread with trace.
- **remains open:** deliver the exception to the 32 bit SEH. It takes the context of 32 bits of the failure, which the raw input of wow64native signals does not save.

**Verified in a copy:** applies once, 47 units of win32u compile and `wow64.dll` He's got the new guard.

<a id="16-w239-y-w240-las-ventanas-ime-de-32-bits-y-el-guardia-en-el-despachador-preparado-sin-probar-en-consola"></a>


## 16. W239 and W240: the IME windows of 32 bits and the guard in the dispatcher (prepared, untested in console)

**W239** (`reports/wine-hardware-w239/physical/20261105T132122Z/run-0002.log`):
- The win32u guard cut `WM_NCCREATE` from the 32 bit EMI window.
- The following message, `WM_IME_SETCONTEXT`, also executed the 64 bit procedure on another way.
- The guard of (e) in `Wow64PassExceptionToGuest` did not act, although it is in the `wow64.dll` sent (verified disassembling) and `pw_wow64_world` was active: the dispatcher, called just after, calculated esp 0 the same.

**W240** (`wow64-w240-ime-and-dispatcher.patch.py`):
- **IME.** A thread of 32 bits from the scout world does not receive default IME window (`register_imm_window`, win32u). So your imm32 never creates the IME interface window and the "Wine IME" class of the 64 bit imm32 does not reach that thread. The threads of 64 bits and the relaunch do not change.
- **(e).** The check is now in `call_user_exception_dispatcher`, after its own esp calculation. Finish the thread with a line that names SegSs, `ss32_sel`, the context esp and `SystemReserved1[0]`, to see in the next log why they disagree.

**Verified in a copy:** applies once, 47 units of win32u compile and `wow64.dll` Take the check.

<a id="17-w240-pasó-revisión-para-los-juegos-de-32-bits-en-el-mundo-y-w242-preparado-sin-probar-en-consola"></a>


## 17. W240 passed; revision for the 32 bit games in the world and W242 (prepared, untested in console)

**W240** (`reports/wine-hardware-w240/physical/20261105T135118Z`):
- `gui-window32`, `d3d9test32` (DXVK, 1673 tables in 5 s) and `ddraw7test32` (wined3d Vulkan, 2491 pictures) run inside to explore and come out with 0 status.
- There was no c0000005 in the whole run.

**Review: what Vice City needs and SuperMarioKart that the world still does not give.**
- **Record (fixed in W242).** wineserver decides the view Wow6432Node by process, and explorer is AMD64: guests of 32 bits read and write the view of 64 bits. So they were missing:
  - the configuration that Vice City and W229 keep in Wow6432Node;
  - the COM records made only there: the filters DirectShow i386, `pwmpeg1.ax` and DirectMusic.

  W242 requests the redirection with the attribute `OBJ_KEY_WOW64` of the server (ntdll Unix, `registry.c` as the new unit of the world).
- **Exceptions of 32 bits (fixed in W242)** Since W240 a failure ends its thread. Wine (`IsBadReadPtr`) and the games take faults on purpose under SEH. The context of 32 bits of the failure is in the area of CPU (`BTCpuResetToConsistentState`), with your Sp. The dispatcher ignored it when SegSs is not `ss32_sel` and used `SystemReserved1[0]`, which in the world is worth 0. Now use the context esp and the exception comes to the program SEH.
- **Image in `0x400000`.** The ELF title occupies that base, but does not block: in the relaunch `gta-vc.exe` it already loaded relocated (`027D0000`, W208).
- **Memory.** The world is * large address aware * (limit `0xffffffff`) and the 2 GiB free contiguous are above `0x80000000`. A game that is not LAA (Vice City, Blitz3D) can receive pointers above 2 GiB if the lower area is not enough. We have to watch. `PWVM commit` with addresses `>= 0x80000000` before a failure.
- **Display.** `WINE_PS5_FIT` is from the whole process and explorer does not have it, so the game is left in a window (section 5, window scale pending). The F12 key in the frame counter depends in the same way.
- **Vulkan.** `PW_VK_BATCH=1` (relaunch performance) is not in the world environment; is a line in `env.c` if necessary, but in the process is also MangoHud and was not tested together.
- **Audio.** `wineps4` blends all flows into a single port AudioOut: the game shares with explorer. Watch `PWAUDIO`.
- **Command, closer32, second opening and output:** covered by W213, overlay -control, W217/W236 and the guest output (W184 - W224 compiled for i386).

<a id="18-w242-y-w244-vice-city-en-el-mundo-y-el-contexto-de-32-bits-en-cero-preparado-sin-probar-en-consola"></a>


## 18. W242 and W244: Vice City in the world and context of 32 bits in zero (prepared, not tested in console)

**W242** (`reports/wine-hardware-w242/physical/20261105T143753Z/run-0004.log:2224-2277`):
- The 32 bit test programs are still fine.
- `gta-vc.exe`, open from the USB, fails to load: ntdll32 + 0x51D0B writes `0x006DF9E0`.
- In the `ntdll.dll` i386 sent, that direction falls in `fixup_imports`, in the `alloc_tls_slot` integrated: the writing of the TLS index of the program (`*AddressOfIndex`, in the VC .data). The directory TLS (`0x00D60074`) is in the image and the data TLS were read well, so the index page cannot be written. It can be a page of 16 KiB shared with a reading-only section, or an index outside the image.

**Why all the world's failures showed esp = 0** (W235, W239, W242):
- `call_user_exception_dispatcher` order `CONTEXT_I386_ALL`, which includes the debugging records.
- `get_thread_wow64_context` then leave the path of the thread itself and ask wineserver, which has no i386 context for a thread of an AMD64 (P2) process. Fault, and the dispatcher still has a zero context.
- The guard of W239 asked for only CONTROL and that's why he saw real values.

**W244** (`wow64-w244-vc-image.patch.py`):
- **ntdll Unix.** In a process of 64 bits, the i386 debugging records of the thread itself come out of its cache copy. The dispatcher receives the actual context and the W242 office reaches the program's SEH.
- **ntdll i386 of the guests.** Before writing the TLS index of a guest EXE:
  - Trace your base, preferred base, sizes, alignments and each section with your real protection;
  - returns a marked section to be written that the mapping has stopped reading only;
  - never write an index out of the image: it records it.

<a id="19-w244-y-w246-vice-city-necesita-su-base-0x400000-preparado-sin-probar-en-consola"></a>


## 19. W244 and W246: Vice City needs its base 0x400000 (prepared, untested in console)

**W244** (`reports/wine-hardware-w244/physical/20261105T150422Z/run-0002.log`):
- `gta-vc.exe` load and reach its entrance, but in `00AE0000`.
- The section trail shows that it does not have `.reloc`: the charger cannot relocate it (`perform_relocations` succeeds with the empty directory). The TLS index was left in `006DF9E0`, outside the image, and the code used the preferred base addresses until it failed.
- In the relaunch load in `00400000` (W225, W230), because it is mapped first. In exploring that range it's already taken.

**W246** (`wow64-w246-exe-window.patch.py`):
- **(1) Window for old EXE.** In a process of 64 bits, the undirected assignments first seek place above `0x2000000` (reserved areas of Wine and, if the order has limits, the free area) and only use [`0x400000`, `0x2000000`) if there is no other. The images that ask for their preferred base continue to receive it. What you had already put in there before you knew the main image is left.
- **(2) Trace.** When an i386 image does not get its basis in a process of 64 bits: `PWWOW image_not_at_base preferred=… occupied=…+… prot=…`.
- **(3) Dead lawnmower.** A guest whose threads all ended (a failure, a stack overflow) is terminated at the next opening (`PWGUEST stale`), with his module downloaded, and the opening continues. Before it was rejected with error 183.
- **(4) d3d8.** It is the i386: the 32 bit charger names with `system32` The files of `syswow64`, is below 4 GiB, and "native" means the d3d8 of DXVK. Nothing to change.

<a id="20-w246-vice-city-juega-dentro-de-explorer-w248-preparado-sin-probar-en-consola"></a>


## 20. W246: Vice City plays within explorer; W248 (prepared, not tested in console)

**W246** (`reports/wine-hardware-w246/physical/20261105T154532Z/run-0002.log`):
- `gta-vc.exe` loaded in `00400000` (the reserved window worked) and played within explorer, without relaunching: DXVK d3d8, audio and controls.

**What the log shows from the "freezing":**
- It started before leaving, with a loss of device GPU. Esc opened the VC menu, DXVK restarted the full-screen device ("Device reset," "Windowed: false"), and from the line 8066 appears `VK_ERROR_DEVICE_LOST` hundreds of times. A lost device leaves the GPU layer of the game in its last picture.
- To find out if it is from the world or from DXVK/RADV in PS4, you have to try Esc and return to relaunched mode.
- Going out did clean up:
  - the window is gone;
  - 3 files were closed and the 12 modules of the game were downloaded;
  - The command came out of the game mode.
- The 0x230 raw entry flags are only a fixme of Wine (NOLEGACY is not implemented).
- Then the scout interface thread was left with no active window or focus.

**Start videos.** VC never asked DirectShow (it did not load `quartz.dll`; at the relaunch load just after d3d8). VC reproduces them only if your window was not deactivated during startup (`startupDeactivate`). Such a deactivation is not left in the log.

**W248** (`wow64-w248-focus-trace.patch.py`):
- **win32u.** Record each window change in foreground (`PWFOCUS`, the first 400) to see who disable VC when you start.
- **Get out of overlay.** After a guest is finished, put forward the task bar (`Shell_TrayWnd`) so that keyboard and control have window.
- **First window at the front.** User track: in a second opening, the VC screen did not appear until the control was tight, and that touch also skipped the videos. Neither the guests of 64 bits have an explicit step to move forward: it does so the self-activation of Wine when showing the window.
  - In win32u (`NtUserShowWindow`), the first front-level window showing a thread of 32 bits of the world passes to the foreground, such as that of a process that starts at Windows.
  - Threshold: `PWWOW guest32 first window … foreground … set=… tick=…`. The bridge line carries the same `tick=` to measure the ms from the launch.
  - The daughter windows (VMR7 video) follow his father; the layer GPU follows the Z order of the window in ps5drv.

<a id="21-w248-y-w249-el-com-de-32-bits-encuentra-sus-clases-preparado-sin-probar-en-consola"></a>


## 21. W248 and W249: the 32 bit COM finds its classes (prepared, untested in console)

**W248** (`reports/wine-hardware-w248/physical/20261105T164309Z/run-0001.log`):
- The VC window passes to the front instantly.
- The videos are still not released: `class {e436ebb3-…} not registered` (CLSID_FilterGraph). In SuperMarioKart the same happens with `{d2ac2881-…}` (DirectMusic).

**Cause.** The redirection to Wow6432Node of wineserver has three parts:
- W242 gave the one that depends on the attribute `OBJ_KEY_WOW64`: the redirection within a route.
- The other two depend on access rights, which the server forces to `KEY_WOW64_64KEY` in a process that is not WoW64:
  - `get_wow6432_parent`, the father's Wow6432Node;
  - `grab_wow6432node`, which changes an open key that has a child Wow6432Node for that child.
- The i386 combase opens its class root as `\Registry\Machine\Software\Classes`. In a process WoW64 that is left in `Classes\Wow6432Node`; in explorer was left in the 64 bit, and `CLSID\{…}` open relative to it as well.

**W249** (`wow64-w249-classes-view.patch.py`, ntdll Unix `registry.c`):
- For a thread WoW64 of a process of 64 bits that did not ask for the view of 64 bits, a `NtCreateKey` / `NtOpenKeyEx` successful on a key with child Wow6432Node returns that child, as it does `grab_wow6432node`.
- Trace: `PWWOW registry 32-bit view: … -> its Wow6432Node`, the first 32.

<a id="22-w250-gecko-i386-webview32-en-el-mundo-preparado-sin-probar-en-consola"></a>


## 22. W250: Gecko i386 (webview32) in the world (prepared, untested in console)

**W248** (`reports/wine-hardware-w248/physical/20261105T170334Z/run-0004.log`, from the line 75775:
- The Gecko i386 is installed and is located: mshtml load `…\gecko\2.47.4\wine-gecko-2.47.4-x86\xul.dll` (syswow64 by redirection). There's no need to unload anything.
- Your load fails with `c0000017`:
  - `map_fixed_area mmap error Invalid argument` at its base `0x741f0000`, of 69 MiB, which Wine is not occupied;
  - all other ranges fail the same;
  - the session already showed `anon mmap error Invalid argument` for views of 0x34000.
- In Orbis, a map with access in a fixed direction, or in areas reserved or free of Wine, takes a flexible memory instantly, and that memory was exhausted. W175 gives direct memory only on the anonymous path of `map_view`.

**W250** (`wow64-w250-large-views.patch.py`, ntdll Unix `virtual.c`):
- A view of 1 MiB or more with access is located as a reserve `PROT_NONE` on all roads (fixed base, reserved areas, free area and window W246).
- Then it is backed as in W175: direct memory first, if not the flexible engagement, if not `STATUS_NO_MEMORY` with the line `PWVM view … got no memory`.
- `C:\orbis\nodirect.txt` (W220) continues to turn off the direct memory.

<a id="23-w249-y-w251-supermariokart-dentro-de-explorer-preparado-sin-probar-en-consola"></a>


## 23. W249 and W251: SuperMarioKart within the scout (prepared, untested in console)

**W249** (`reports/wine-hardware-w249/physical/20261105T171535Z/run-0001.log`):
- The class view works: DirectMusic load and music sounds.
- SuperMarioKart was closed before the race, and when it was reopened, it was kept waiting forever.

**Causes:**
- **The closing.** A mapping Vulkan "placed" of 64 MiB He did not find a flexible memory (`tryfixed_hint … flexible=0`), wined3d was left with an unmapped BO, and the `assert` of `cs.c:3189` finished the host. win32u compromised that range with reading and writing only as a marker, because RADV mapped his direct memory alias. In Orbis, this commitment takes a flexible memory at once, and wined3d keeps eight blocks of 64 MiB mapped.
- **The waiting.** The global lock of wined3d (`wined3d_cs`) was taken by the thread that came from inside a d3d call. The wined3d i386 is loaded among guests, so the next one waited forever.

**W251** (`wow64-w251-smk-wined3d.patch.py`):
- **win32u.** The "placed" range is compromised without access (in Orbis, a memory-free reserve) and then goes to reading and writing after the RADV mapping. It also applies to relaunched programs.
- **wined3d, mapeo.** The two `assert` of NOOVERWRITE move on to a path with a trace that mops through the CS thread.
- **wined3d, padlock.** A thread that ends with the padlock taken releases it; `wined3d_mutex_lock` you keep it if your owner no longer exists.
- **The VC closure with MangoHud i386.** A thread of 32 bits created just after starting DXVK read `0xFFFFFFFF` in `0x02D8F830` without any memory failure before. I see no cause on the side of the world; It's left for overlay -control.

<a id="24-w251-y-w252-gecko-i386-y-el-crypt32-sin-lado-unix-preparado-sin-probar-en-consola"></a>


## 24. W251 and W252: Gecko i386 and the crypt32 without Unix side (prepared, untested in console)

**W251** (`reports/wine-hardware-w251/physical/20261105T174934Z/run-0003.log`):
- W250 worked: `xul.dll` i386 of 69 MiB already mapped.
- It is immediately downloaded and returned "Failed to init Gecko."
- In the middle, the start process of the `crypt32.dll` i386 makes a Unix call with a null table (failure in `__wine_unix_call_dispatcher`) and its initialization fails. xul.dll it matters through windust.
- There is no `crypt32.dll` i386 in `wine/lib/wine/i386-windows`: only the syswow64 copy of the sealed prefix, which the charger takes without Unix library route. That's why the static table of W180 is never sought. The manager was just jumping it because the prefix already had one.

**W252** (`wow64-w252-crypt32-i386.patch.py`):
- **`stage-mshtml-hw.py`.** Put the `crypt32.dll` i386 of the tree set in the building folder (`BUILTIN_FOLDER`) Even if the prefix has yours. It also serves the relaunched programmes. There's nothing to download.
- **Womens without a window.** The main thread of webview32 never reached its exit. Now the next opening of a graphic program whose host does not show any window ends it (threads and module) and starts again (`PWGUEST stale … no visible window`).
- **The silent death of Vice City after his first video** (W251, `run-0001.log`):
  - The start video was played inside the world until the overlay (`PWOVERLAY open`, line 5052 was opened and the video stopped.
  - Two new quartz threads loaded all your DLL, the `libMangoHud.dll` i386 at the end, and the log ends without exception of Wine no sign.
  - In W249 VC also died three times just after loading the MangoHud i386. The track is overlay with MangoHud of 32 bit in the process (W247 of overlay -control).
  - W252 adds a line for each 32 bit thread that ends (`PWWOW guest32 thread … ends`).

<a id="25-w252-y-w253-la-salida-silenciosa-de-vice-city-preparado-sin-probar-en-consola"></a>


## 25. W252 and W253: the silent exit of Vice City (prepared, untested in console)

**W252.** webview32 works (pages, reopening), and DVD and VLC as well. Vice City continues to die in silence after the videos: they finish their device threads, a new thread of 32 bits loads their DLL, and the title disappears without signal or output.

**Is there a handler for each thread?** Yes, by process: `sigaction` of Wine. With `PW_NATIVE_SIGNALS=1`, the core first enters `pw_native_signal_entry` (W136) into any thread.

**Which can end the title without a line:**
1. **The raw input itself.** A code signal of 32 bits (CS 0x33) that the input cannot bind to a thread of Wine (signal cell disabled or foreign, without TEB, without base FS of the host, or `sysarch` failing) goes to its label 9, which makes `exit(127)` by calling the raw and purposely without C.
2. **The system from outside.** A page failure or a GPU hang (the screen shows a CE- code), or move from the memory budget. The death of VC follows the disassembly and recreation of its device, and in W246 Esc had already lost the device.
3. **One abort/exit on the Unix side** I'd write "Assertion" before... or go through SIGABRT, which Wine record.

**W253** (`wow64-w253-silent-exit.patch.py`):
- The tag 9 first writes `PWNATIVE lost signal=… cs= rip= rsp= addr= fsbase=` in the log of the Runs, with the call `write` raw from a function without libc or TLS, and then comes out as before.
- `native/wine_hardware.c` gives you the log descriptor.
- If VC dies and that line does not appear, it is the case 2: you have to write down the error code that shows the screen.

**Verified in a copy:** is applied once, `pw_wine_signals.c` compiles with the console compiler without warning, and the new function does not touch `%fs` or call libc.

<a id="26-w254-trazas-de-la-recreación-del-dispositivo-de-vice-city-preparado-sin-probar-en-consola"></a>


## 26. W254: traces of the recreation of the Vice City device (prepared, untested in console)

With the MangoHud i386 off, VC dies the same (`reports/wine-hardware-w252/physical/20261105T184512Z/run-0008.log`): after the video end its device threads, a new thread load `gta-vc.exe`, `vulkan-1` and `winevulkan`, And the title goes away.

**W254** (`wow64-w254-vk-trace.patch.py`):
- **win32u.** For the threads of the world of 32 bits, each call of the life cycle of Vulkan leaves one start line and one end line: instance, device, surface, swapchain, and memory reserves of 16 MiB or more (or those that fail). A `PWVK32 begin …` without his `end` is the call in which the title died.
- **DXVK.** As long as there is `C:\orbis\dxvkdebug.txt`, the host of 32 bits put `DXVK_LOG_LEVEL=debug` and `DXVK_LOG_PATH=none`: the log of DXVK goes only to the log of the Runs and never to files in the folder of the game.

**Verified in a copy:** is applied once, 47 units of win32u compile (without new warnings) and the host compiles.

<a id="27-w253-y-w255-una-capa-gpu-que-sobrevive-a-su-swapchain-preparado-sin-probar-en-consola"></a>


## 27. W253 and W255: a layer GPU that survives your swapchain (prepared, untested in console)

**W253** (`reports/wine-hardware-w253/physical/20261105T185751Z/run-0001.log`):
- There is no line `PWNATIVE lost signal`, so it was not the `exit(127)` of the raw input: the system finished the title.
- The last shipments of RADV were all completed.
- The log ends when the threads of the video are finished: those of quartz, then the one that presented the video (`show_frame hwnd=0x2010e path=gpu_layer`) and those of its device.

**Probable mechanism.**
- The composer's GPU reads the image of a program Vulkan in its direction (W152), without a copy or a reference of its own.
- The only release is `ps5_vulkan_forget`, from `vkDestroySwapchainKHR`, which seeks the surface window or its root window (W229).
- If the VMR7 video's daughter window is destroyed before your swapchain, neither one of the searches finds it. The layer is left in the game window with the direction of an image that Mesa releases, and the following composition reads memory GPU without mapping: a page failure of GPU that ends the title from outside.
- The composer's drawing is synchronous (he waits for his fence), so only a forgotten layer can be read after the image is released.

**W255** (`wow64-w255-forget-layers.patch.py`, `ps5drv.c`):
- If the found window does not show that swapchain, or is not found, any window that still shows your image releases it before the swapchain disappears.
- Each release is left in the log (`PWVK forget … cleared=N`).
- It also takes a relaunched mode control run: if there dies the same, the next suspect is the change from W251 to the "placed" mapeos.

**Verified in a copy:** is applied once and 47 units of win32u compile without new warnings.
- **User data after W253.** No CE- code appeared (the title probably came out by itself), and with the VC Movies folder renamed the game goes on within the world. The end is in the post-video disassembly.
- **Output strips** (also in W255, `build-wow64-world-ps4.py`):
  - Wine ends the process when your last thread ends (`nb_threads` reaches 0). A low account would finish the title just when the video threads end, with no signal or CE- code.
  - Now `exit_thread` / `abort_thread` record `PWEXIT last thread …`, and `process_exit_wrapper` and `abort_process` record `PWEXIT process_exit|abort_process …`.

<a id="28-w254-y-w256-el-segundo-grafo-de-video-de-vice-city-preparado-sin-probar-en-consola"></a>


## 28. W254 and W256: the second video graph of Vice City (prepared, untested in console)

**What does W254** (`reports/wine-hardware-w254/physical/20261105T193720Z/run-0001.log` show with the restored Movies folder:
- The first video (Logo.mpg) is played and VC stops it (lines 5489 - 5493, `samples=118 hr=0x80040227`).
- The VMR7 is removed by ddraw/wined3d: its swapchains (5559, 5647) are destroyed and then the device 0x2d152f8 with its instance (5684 - 5687.
- That device is wined3d (13 extensions, just like those of ddrag in 2907 and 3052), not DXVK. The D3D8 VC device over DXVK (0x2d22a98, 25 extensions, line 4217) It's never destroyed.
- They finish the threads of the first graph (5688 - 5691) and start the second:
  - 00cc in quartz + 0x30100 = `message_thread_run` (filtergraph.c);
  - 00d0 in quartz + 0x2fd70 = `io_thread` (filesource.c, the loop of the end port of the File Source).
  - W251 died at the very beginning of `io_thread`.
- The end comes before the `PWMPEG open` of the second graph. In the first, the same section (4586 - 4760) was the enumeration of the cecum (avicap32, msdmo, mmdevapi, the audio of wineps4.drv, msacm32, midimap) and then the `sink_connect` of pwmpeg1.
- The log of DXVK does not go to a file: with `DXVK_LOG_PATH=none` its lines (`info:`, `debug:`) remain in the log of the Runs. The last one is the 4461.

**Disloaded with the same log:**
- **Reuse of TB or battery.** It is routine and always worked (0x7ffa0000: 0068, 007c, 00a8). In addition, 00d0 executed all of its `loader_init` (the THREAD_ATTACH of 18 modules) over that TEB and its 32 bit stack before the end.
- **An output of Wine or of libc.** `native/wine_hardware.c` wraps `exit` and `_exit` and write before `process_exit method=…`. The W252 runs have those lines and the W254 no. The `PWEXIT` lines of W255 probably don't show up either, because they go right before those calls.
- **A lost signal** (W253), a server SIGKILL (the `process_sigkill` of overlay never kills your own process) or a `PWTHREAD` signal near the end.

**What's left:** the system finished the process. It may be a failure that the kernel could not deliver, a failure of GPU or a termination of the system itself. A cheap and read-only verification: list `/user/data/sce_coredumps/` by FTP. A turn at the time of death would indicate the thread and the RIP. There's nothing to be erased there.

**W256** (`wow64-w256-graph-trace.patch.py`):
- `native/wine_hardware.c`: if there is `C:\orbis\winedebug.txt`, your first line is added to `WINEDEBUG`, for example `trace+quartz,trace+devenum`. Only letters, digits and `+-,_` are taken, and the log shows it with `PWBOOT winedebug extra=…`. Without the file, it doesn't change anything.
- `native/pwmpeg1/pwmpeg1.c`: each step of the filter writes a line with its thread (`PWMPEG create`, `connect begin`, `connect length`, `run`, `stop`, `destroy`). The last line of the second graph says how far your weapon got.

**Verified in a copy:** applies once and rejects a second application. pwmpeg1.c compiles with the stager recipe without warning. The pitcher fragment compiles without warning and was tested with the file with content, empty and absent.

**Return:** SuperMarioKart, from menu to race (the path of W251), without `winedebug.txt`. W256 does not change how threads, TEB, batteries, or memory are created or released: it only adds log lines and an optional supfix of `WINEDEBUG`.

<a id="281-la-pantalla-congelada-tras-salir-en-vice-city-w255-también-en-w256"></a>


### 28.1 The screen frozen after leaving in Vice City (W255, also in W256)

**What does W255** (`reports/wine-hardware-w255/physical/20261105T195230Z/run-0001.log`, 8420 - 8546 show:
- The lock ended the guest (TerminateThread of his 23 threads), so his swapchain is never destroyed and `ps5_vulkan_forget` does not run for her.
- But `window_gone` (`purge_dead_windows`) remove from ps5drv the entire window, with its Vulkan (`vk_pixels` image included.
- Since then ps5drv has delivered the desk stack to the sink. `layers=4` is the same account that the desktop had before the game (n = 256, n = 320). During the game it was 1 because a full screen window is displayed alone (W248).
- After the output the desk is still alive: the focus passes to the taskbar, the entrance comes, the beat of the shell is fine and there are 64 more batteries.
- So the origin of the frozen image does not appear on this log: the ps5drv side looks clean.
- A data for overlay -control: the lock recorded `exit result asked32` and no final result (`closed`) appears for overlay.

**W256** (`tools/build-win32u-ps4.py`, `ps5drv.c`):
- `PWVK forget … reason=window_gone|destroy_window` when the missing window had a Vulkan image.
- Then the following 3 batteries are delivered to the sink, one line per layer (`PWSINK stack i/n pixels= rect= flags= source=`). `flags=0x1` is an image Vulkan read by direction: if one appears after the game is finished, it is an old layer. If the stack is only from the desktop, the frozen image is in the sink or in the video output.
- The guest's download comes after the window is no longer (8437 and then 8447), so there's nothing left to forget.

**Verified in a copy:** the revised `ps5drv.c` compiles with the bulder recipe without warning.

<a id="282-w256-vice-city-desde-una-copia-interna-sin-usb"></a>


### 28.2 W256: Vice City from an internal copy (without USB)

- With VC copied to `C:\users\orbis\Documents\…` the two videos are reproduced and disassembled well (Logo of 7 239 684 bytes and GTAtitles of 24 272 900 bytes, 81,84 s), the game runs and Exit closes it.
- All the deaths (W251 - W254) were with VC in `E:\PC\…` (`/mnt/usb1`, exFAT, with the jailbreak).
- There are two differences, not one:
  - the file was on the USB;
  - in W256 there was no USB drive mounted: there are no lines `PWDRIVE`, so the watchman (`usb_watch` → `pw_wine_fs_usb_refresh`, every 2 (s) had no records.
- What the code rules out:
  - the server waits with `pw_wine_poll`: there is no kqueue (`fd.o` does not refer to it);
  - ntdll does not use aio or O_ASYNC;
  - in Wine, a superimposed reading of a regular file is a synchronous `pread` (`virtual_locked_pread`, file.c "no async I/O on regular files "), and the `sync_read` File Source marks the event not to pass through the port;
  - In addition, Logo.mpg was read from the USB with the same path in all the rungs that died, and VC reads from the USB its own large files (gta3.img) without problem with the renowned Movies.
- Tests to separate the two variables, with W256 as and `C:\orbis\winedebug.txt` = `trace+quartz,trace+file`:
  1. VC since `E:` again, with Movies. The `PWMPEG connect …` lines and `SyncRead` quartz lines with their offset show the last reading before the end.
  2. VC from the internal copy with the USB disk connected.

<a id="283-causa-de-la-muerte-de-vice-city-tras-el-video-la-capa-gpu-vieja-corregida-en-w255"></a>


### 28.3 Cause of Vice City's death after the video: the old GPU layer, corrected in W255

- In W256, VC runs from the USB and plays the two videos twice in a row (`reports/wine-hardware-w256/physical/20261105T204055Z/run-0002.log`).
- The log shows what change it imported: the back of W255 in `ps5_vulkan_forget` acts at the end of each video:
  - line 5255: `PWVK forget swapchain=0x20613ce60 hwnd=0x2010c window=0 cleared=1` (Logo);
  - line 6253: `… hwnd=0x20112 window=0 cleared=1`
  - line 9452: `… hwnd=0x10134 window=0 cleared=1` (Logo, second run).
- `window=0 cleared=1` is exactly the case described in W255:
  - VMR7's daughter video window no longer existed when his swapchain was destroyed, so the window search failed;
  - the image remained a layer of the game window;
  - Only the swapchain tour found her.
- Before W255 that layer was pointed to the image already released by Mesa, and the next composition read memory GPU without mapping. That GPU failure ended the title from the outside: no signal, no `process_exit` and, on this console, no CE- on-screen code.
- The internal copy (W256, 20261105T203137Z) and USB were not the cause. Death depended on the timing of the next composition after disassembly, so it fell close to the start of the second graph.
- The traces of W254 - W256 are left for a while. `PWVK forget … window=0 cleared=1` confirms the case every time it happens.

<a id="29-w257-y-w258-los-dll-propios-de-un-invitado-y-las-secciones-críticas-huérfanas-preparado-sin-probar-en-consola"></a>


## 29. W257 and W258: guest's own DLL and orphan critical sections (prepared, not tested in console)

**Portal** (`reports/wine-hardware-w257/physical/20261105T210849Z/run-0002.log`, from the line 5061):
- Portal.exe (00400000) starts hl2.exe and expects it, so it is still a live guest with `E:\PC\Portal\` folder.
- The first hl2.exe (02350000) load `bin\tier0`, `bin\vstdlib` (04340000, Launcher, engine and the others, and it comes out with a state 0.
- When you download it, you find none: `own_modules module=02350000 count=0 … live=2`.
  - W209 jumps every module into another live guest's folder, as it is considered by that guest.
  - `E:\PC\Portal\` is prefix of `E:\PC\Portal\bin\`, so hl2 DLL counted as Portal.exe and were loaded with their status.
- The second hl2.exe (0EFA0000) fails in the old vstdlib (`c0000005 at 043414C3`, `vstdlib.dll+14c3`), which still points to the unloaded image of the first.

**W258** (`wow64-w258-guest-modules.patch.py`, `tools/build-guest-hw.py`):
- **Modules.**
  - When a guest is launched, the modules loaded at that time (`modules_at_launch`) are recorded.
  - When you leave, a module inside another live guest's folder is leaped only if it was already loaded when this guest started. If he appeared later, he is his own and goes with him on the path of W209 - W211:
    - they leave their window classes;
    - there is no DllMain (DETACH);
    - is discharged in rounds according to their imports;
    - is preserved if one of its threads still runs its code.
  - Each one is left in the log: `PWGUEST own … (after launch, in a live guest's folder)`.
  - The remains that are found when another guest is launched are decided as before.
- **Critical sections**
  - In the ntdll of the guests (x86_64 and i386), when the waiting (5 s is over, then 60 s) the owner thread is reviewed.
  - If it no longer exists or is over, the waiting takes the section: `PWGUEST section … held by ended thread T (recursion R): taken over by U`.
  - The dead owner's R entries come out of `LockCount`, and the owner's field is cleaned with a comparison-exchange, so if several see it at the same time only one wins.
  - A living owner, or an id reused by a living thread, is expected as before.
  - Generalize the taking of the wined3d W251 lock. Case: the 0070 thread of SuperMarioKart left the vulkan- 1 section taken (79A10078).

**Verified in a copy:** applies once and rejects a second application. `build-guest-hw.py` compiles ntdll, kernelbase and ucrtbase for x86_64 and i386 (76 reviews). `sync.c` and `process.c` do not give new warnings; the two that appear in `process.c` (lines 1844 and 2296) were already there.

<a id="30-w259w260-portal-se-detiene-por-avifil32dll-y-shfolderdll"></a>


## 30. W259/W260: Portal stops by avifil32.dll and shfolder.dll

**W259** (`reports/wine-hardware-w259/physical/20261105T221907Z/run-0004.log`, from the line 1841: The W258 module download works. The first hl2.exe ends with status 0, download your own DLL (`own=12`, `rounds=7`, `released=11 bytes=190201856`) and the second hl2.exe load new copies. Now stop before:

- line 2253, Portal.exe: `Failed to load module L"SHFOLDER.dll"; status=c0000135`;
- lines 3198 - 3216, the second hl2.exe: `Library AVIFIL32.dll (which is needed by ...\bin\valve_avi.dll) not found`, three times, and then `AppFramework : Unable to load module valve_avi.dll!`;
- line 3299: the hl2.exe ends with 0 state without opening window.

Neither DLL is in the runtime of W259: neither in syswow64 nor in system32, nor in i386 or x86_64 building folders. The two are already compiled in the Wine tree fixed for both architectures.

**W260** (`wow64-w260-avifil32-shfolder.patch.py`, just touch `tools/stage-wine-i386.py`, the manager of W119; does not patch Wine):

- `avifil32` and `shfolder` are added to `TARGETS` (i386: sysmow64 and `wine/lib/wine/i386-windows`) and `X64_TARGETS` (x86_64: system32 and `wine/lib/wine/x86_64-windows`), with their import closure as always;
- avifil32 imports msacm32, msvfw32, ole32, rpcrt4, winmm and the basics; shfolder only matters kernel32 (its two exports are sent to shell32, which is in both views);
- in x86_64 the closure also adds msvfw32.dll, which was missing in system32;
- the msvfw32.dll i386 remains `stage-dshow-i386.py` (W225), which rejects a module already prepared by another manager; for this manager counts as present.

`build-wine-hardware.py` already copies both lists (W119/W120) and does not change. After the patch you have to rerun `stage-wine-i386.py` and then `stage-dshow-i386.py`, because the second reads the manifesto of the first.

**Verified in a copy:** the patch is applied once and rejects a second application. The manager adds, in i386, avifil32.dll and shfolder.dll; in x86_64, avifil32.dll, msvfw32.dll and shfolder.dll. No unsolved imports remain and the other modules retain the same bytes. `stage-dshow-i386.py` continues to work later, with the same msvfw32.dll.

<a id="301-dll-de-wine-que-faltan"></a>


### 30.1 DLL of Wine missing

The modules compiled in `.deps/wine/runtime/build/dlls/*/<arch>-windows` were compared to the runtime of W259. The complete list is in the note folder (`w260-missing-dlls-scan.txt`); There are hundreds, almost all of them without interest for games. The most often important games, absent in **the two** views unless indicated:

- Visual C + + + runtimes: msvcp60/70/71/80/90/100/110/120/140 (and msvcp140_1, _ 2, _ atomic _ wait, _ codecvt _ ids), msvcr70/71/80/90/100/110/120, vcruntime140, concrt140, vcomp and vcomp90- 140, msvcirt, crt.dll;
- graphics: d3d10, d3d10_1, d3d12, d3d12core, d2d1, dwrite, d3dx10_43, d3dx11_43, d3dcompiler_43, d3drm, d3dim, d3dim700, ddrawex, glu32, dxva2;
- audio: xaudio2_7/8/9 (and other versions), x3daudi1 _ *, xapofx1 _ *, xactengin *;
- DirectPlay antiguo: dplay, dpnet, dpnaddr, dpnlobby, dpwsockx;
- video and MCI: mciavi32, mciwave, mciseq, mcicda, mciqtz32; codecs VfW iccvid, msvidc32, msrle32, ir50_32, iyuv_32; Códec ACM msgsm32.acm;
- Other: riched20, riched32, msftedit, imagehlp, lz32, wing32, ctl3d32, wintab32, mswsock, winhttp (only missing in i386), msi, mscoree, mfplat, mf, mfreadwrite, wmvcore, wmmass, amstream, qedit, qcap, evr, msxml6, xmllite.

**d3dx9_24 to d3dx9_43 are not linked to the tree** (there are only `.o`, in both architectures). Before preparing them, you have to compile them (`make dlls/d3dx9_NN/<arch>-windows/d3dx9_NN.dll`).

Many games bring their own C + + runtimes in their folder. However, it is appropriate to prepare in lot the runtimes of Visual C + +, xaudio2/x3daudio, d3dx10/11, d3dcompiler_43, d2d1/dwrite, riched20, imagehlp, glu32 and the codecs VfW with the same mechanism, not to discover them game to game. Some, such as mfplat, dwrite or xaudi2, depend on a Unix part or libraries (GStreamer, FAudio) that need to be reviewed before, one by one.

<a id="302-w260-portal-llega-a-direct3d-9-y-pierde-el-dispositivo"></a>


### 30.2 W260: Portal reaches Direct3D 9 and loses the device

`reports/wine-hardware-w260/physical/20261106T011238Z/run-0001.log`. With avifil32 and shfolder, hl2.exe launched by Portal.exe creates the D3D9 device of DXVK, MangoHud i386 da metrics and presented 5 tables (640x480). From the line 9057 appears `VK_ERROR_DEVICE_LOST`, about 18 000 times.

You can't see anything from the world of 32 bits:

- **Assigned memory.** Only one assignment is visible from CPU: `vkAllocateMemory 0x1000000 type=2` (line 7264). It is the only one that passes through the map set of W126/W251; DXVK mapia in `0x7e40000`, below 4 GiB. The other four (16, 32, 64 and 128 MiB, `type=0`) are DEVICE_LOCAL and never mapped in CPU.
- **No map error.** No lines. `PWVK placed map … protection status` or `placed unmap … failed`.
- **The GPU does not read the alias.** The map placed is a second alias of the same pages, only for the CPU. The GPU continues to use its original mapping. The `NtProtectVirtualMemory` of W251 only makes `mprotect` of the alias of CPU, and that alias has no bits of GPU.
- **Before the loss, everything was fine..** With that memory, the GPU completed the shipments correctly 1 a 39. The shipment 40 It's the one that never ends.
- **The GPU is not completely hung.** It was almost idle: `gpu_busy` of 0,1 s in an interval of 33. The explorer composer continued to present after the loss (`frame_presented` n = 640, then n = 704).
- **There is no diagnosis of failure.** `radv/amdgpu: Failed to query the last GPUVM fault (-22)`: the winsys of PS4 does not give the direction of the failure.

Conclusion: it is a problem of RADV/GFX7 with a picture of Source, not of the world. If it is taken back, it takes what returns the wait for the fence in the winsys PS4 and, if possible, the address of the failure.

<a id="31-w261-todas-las-dll-de-wine-que-faltaban"></a>


## 31. W261: all missing DLL of Wine

At the user's request, W261 prepares at once all the modules of the Wine tree fixed that a Windows program can import and that were missing in both views (30.1 scanning). Plot: `wow64-w261-wine-dlls.patch.py` (note folder). Touch `tools/stage-wine-i386.py` (needs W260) and `tools/build-wine-hardware.py`. Full lists in `w261-dll-lists.txt`.

- **They are added:** 396 modules i386 (110,5 MB) and 393 x86_64 (122,3 MB), unpatched:
  - Visual C + +, Direct3D 10/12, d3dx10/11, d3dcompeller, d2d1, xaudio2/x3daudio/xact;
  - DirectPlay, MCI and the codecs VfW, Media Foundation, msxml, ricked, msi, ODBC/OLE DB, net, shell and COM.
- **No debugging information.** It is used `--strip-debug`: only sections `.debug_*` are removed. Code, RVA and signature "Wine builtin DLL" do not change (checked in the 789 modules), so a failure move continues to correspond to the file without removing from the tree. Without this, the set would occupy about 620 MB.
- **A single copy.** They go only to syswow64 (i386) or system32 (x86_64). None of them have a Unix part, and Wine load a building found there, as it does with the 140 sysmow64 modules of the sealed prefix. A second copy in `wine/lib/wine` would double the size.
- **Full lists.** An import that is not in the view or list stops the manager, and also one of an excluded module. The failures are all reported together. The modules of other stagers (DXVK, Vulkan, MangoHud, HID, W225, W138, W174, W177) count as part of the view and do not touch.
- **COM record for both views.** It is generated from the scripts WINE_REGISTRY, as in W225: 119 i386 and 118 x86_64 modules have scripts, in total 7699 keys. Without this, `CoCreateInstance` I would say "class not registered": the sealed record only has the classes of its own modules, and they were neither xaudio2_7, nor msxml6, nor AVIFile. Details:
  - the record of avifil32 (W260) is also included;
  - no value that already exists in the sealed record is written (28 are retained);
  - the block goes in system.reg before those of MSHTML and DirectShow, whose subsequent sections keep their values where both record a key (265 cases: MSXML2.DOMDocument, MSHTML interface typels);
  - type libraries are not registered, because `register_typelib` runs code.
- **Excludes, with their reason** (by name in the manifest `w261_left_out`):
  - control panel (.sys) and applets;
  - modules that need services: Task programmer, event log, WIA, smart card, Windows Update, BITS and HTTP.sys;
  - printing: spooler and CUPS;
  - modules whose part Unix is not in the ELF Orbis: dwrite, odbc32, qcap, winedm, kerberos, msv1_0, ctapi32;
  - those who import winegstreamer, winedmo or odbc32;
  - mscoree, which needs Wine Monkey;
  - the support of 16 bits;
  - the administration of the system;
  - WinRT (`windows.*`);
  - in x86_64: DirectShow (your filter record is only i386) and DirectMusic (your arrangements are only i386).
- **d3dx9_24 to d3dx9_43** are still not linked to the tree.

Change of behavior to watch: Visual C + + runtimes now exist as a building. A game that brings yours could go on to use those of Wine, according to the order of charge.

**Verified in a copy** (the base W260 was reconstructed and coincided with `builder_sha256` of the W260 manifest:

- the patch is applied once and rejects a second application;
- the two files compile;
- the manager ends up without import problems;
- the modules of W119/W120/W260 retain the same bytes;
- No name hits with the runtime of W259.

<a id="32-w261w262-excepciones-x87-del-juego-en-código-de-64-bits-nfs-y-opengl-de-32-bits-call-of-duty"></a>


## 32. W261/W262: exceptions x87 of the set in code of 64 bits (NFS) and OpenGL of 32 bits (Call of Duty)

<a id="321-nfs-underground-2-y-most-wanted"></a>

### 32.1 NFS Underground 2 and Most Wanted

`reports/wine-hardware-w261/physical/20261106T033201Z`, run- 0003 (speed2.exe) and run- 0006 (speed.exe. Right after the D3D9 device of DXVK, in the main thread 0070, it appears `c0000090 (EXCEPTION_FLT_INVALID_OPERATION) addr=0000001100C009A7`, with `mxcsr=00009fc0`. The 64 bit dispatcher cannot deliver it (`Exception frame is not in stack limits`) and the thread is hung.

- **Where.** 0x1100c009a7 is a `FWAIT` inside `malloc` of musl in the ELF start (`wine.elf`, linked to 0x1100000000).
- **Why it jumps there.** A `FWAIT` triggers an exception x87 pending whose mask is deactivated. The MXCSR 0x9fc0 masks all of SSE's, so it's about the state x87.
- **Cause.** The game will unmask the exceptions x87 (control word) and leave a slope. wow64native, the backend of CPU of prospero-win, changed FS in each transition but left the FP state alive: the host code of 64 bits (Wine, Mesa/RADV, musl) ran with the game's control words and with their outstanding exception. The wow64cpu of Wine does the same.

**W262** (`wow64-w262-fpu-opengl.patch.py`). Change the adaptations of `cpu.c` to `tools/build-wow64native-ps4.py` and use the frame of 0x340 bytes of `BTCpuSimulate`, aligned to 16:

- **When starting `BTCpuSimulate`.** The FCW and MXCSR of 64 bits of the thread are saved in 0x330 and 0x334. The FXSAVE image in 0x30, which was already taken there, is the initial state of the guest, as before.
- **From 32 to 64 bit** (`syscall_32to64` and `unix_call_32to64`, once restored the FS host). `FXSAVE` of the full state x87/SSE of the guest in 0x30, then `FNINIT` (stack x87 empty, with no outstanding exceptions), and the FCW and MXCSR of 64 bit saved are loaded.
- **From 64 to 32 bit** (`syscall_32to64_return`, which also starts the guest, and the return of `unix_call_32to64`). `FXRSTOR` from 0x30, before FS of the guest. The guest recovers exactly what he had, exceptions to be included, as in Windows.
- **Exemptions in code of 32 bits.** Do not change: their context carries the guest's state and the route `RESET_STATE` enters `syscall_32to64` with that state, it's kept the same.
- **User calls.** A callback (a window procedure called within a syscall) starts a `BTCpuSimulate` nested with the words of control 64 bits, not with the game. On returning from callback, the state of the game is restored from the outer frame.
- **The translator** (wowprospero) emulates the 32 bit FPU and is not affected.

**Verified in a copy:**

- the patch is applied once and rejects a second application;
- `build-wow64native-ps4.py` compila wow64native.dll;
- in the disassembly, after `pw_native_restore_host_fs` come `fxsave64 0x30(%rsp)`, `fninit`, `fldcw` and `ldmxcsr`, and `syscall_32to64_return` starts with `fxrstor64 0x30(%rsp)`.

<a id="322-call-of-duty-no-hay-opengl-de-32-bits"></a>

### 32.2 Call of Duty: no 32-bit OpenGL

`run-0004` (CoDSP.exe, Quake engine 3). The game loads the opengl32 i386 building of Wine (W121, prepared for wined3d), sets a screen mode, abandons and tests the next, until it is surrendered.

- **The lines `wglUseFontBitmaps/wglUseFontOutlines not found` are not the cause.** The opengl32 of Windows also exports only the variants A and W.
- **The cause.** The calls `wgl*` of the opening 32 of Wine go to driver OpenGL of win32u, and ps5drv does not implement any, so there is no pixel format.
- **The view of 64 bits** has since W076 the WGL of Mesa with Zink: a native `opengl32.dll` and `libgallium_wgl.dll` in system32, which they draw by Vulkan.

**W262** builds the same for i386:

- **New script `tools/vk-h0/build-mesa-zink-i386.sh`.** It is `build-mesa-zink.sh` with the i686 compilers of llvm-mingw and output in `~/vk-h0/build/mesa-zink-i386`. This session has already compiled it: 941/941 steps, `opengl32.dll` of 166 KB and `libgallium_wgl.dll` of 20,8 MB, PE32, with undecorated exports (`wglCreateContext`, `wglChoosePixelFormat`,...). It only matters the api-set of Ukraine, kernel32, user32 and gdi32.
- **Copy in syswow64** of both files.
- **`"opengl32"="native,builtin"`.** So the programs of 32 bits load this opengl32. wined3d also loads it, and only matters `gl*` / `wgl*` standard names. The 64 bit view has no opengl32 builtin, so it doesn't change.
- **Return to watch.** SuperMarioKart (ddrag over wined3d) now load the opengl32 of Mesa in its 32 bit space.

<a id="323-lanzador-de-prince-of-persia-las-arenas-del-tiempo"></a>


### 32.3 Prince of Persia launcher: The Sands of Time

`run-0002`. The launcher loads its test plugins ("DX Version Test," "CPU Test,...), shows an error dialog and ends with status 0. There is no chain left in the debugging output to explain the failure.

- **Keys of DirectX.** The runtime of W261 I didn't. `HKLM\Software\Microsoft\DirectX`, but the `system.reg` What weapon? W262 and brings them in both views (`InstalledVersion` 9 and `"Version"="4.09.00.0904"`), from the registration of modules of W261. The block W262 He stopped when he found them. The coordinator changed it to omit an existing view. They were not the cause of the launcher's failure: the cause is base_taken (32.4).
- **`get_thread_times not implemented on this platform`.** It is a fixme of ntdll in Orbis: `GetThreadTimes` return zeros. It remains pending if the CPU test continues to fail.
- **`MFC71ENU.DLL` and `MFC71LOC.DLL`** are optional resource DLL.

### 32.4 Prince of Persia: "Request not supported" (W262b)

The text of the error that the user saw is "Can't start. Request not supported, "i.e. `STATUS_NOT_SUPPORTED`. In run- 0002, lines 4175 - 4183:

- the pitcher (a live guest in 0x400000) starts POP.exe;
- POP.exe also needs 0x400000 and has no relocation;
- the load fails with c0000018 (error 487), and the kernelbase i386 returned `STATUS_NOT_SUPPORTED` (`PWWOW guest32 not_a_guest image=L"POP.exe" error=487`).

Two EXE not relocable with the same base cannot be alive at once in the only 32 bit world to explore. This is the typical case of pitcher and game: Prince of Persia and many Ubisoft and EA titles. Open by hand, POP.exe order the pitcher.

**W262b** (`wow64-w262b-base-taken.patch.py`) reuses the existing relaunch (W043/W116:

- **`tools/build-guest-hw.py`** (kernelbase i386, `CreateProcessInternalW`). If the load as a guest fails with the error 487:
  - is recorded `PWWOW guest32 base_taken relaunch image=… cmd=… dir=…`, with the line of orders of the launcher;
  - a relative image ("POP.exe") passes to full route: first the directory given by the pitcher, then the folder of the pitcher's own guest, then the search route;
  - without explicit directory, the work directory is the program folder;
  - the 32 bit dialog asks first, explaining the reason;
  - then the creation of processes of Wine reaches the hook of `NtCreateUserProcess`.
- **`tools/build-wow64-world-ps4.py`** (`process.c` of the Unix part of ntdll, that hook). Before `pw_hw_switch_program`, deliver to `pw_hw_switch_context` (weak symbol) two things:
  - the work directory of the launcher;
  - the environment variables that the launcher fixed or changed with respect to the specific environment of the process: up to 8, only ASCII, and without those of Wine or of Windows.
- **`native/wine_hardware.c`.**
  - Write `/data/orbis-win/next-context.txt`, with lines `dir=` and `env=`.
  - Record the complete command line (`switch_program command=`) and context (`switch_context`).
  - The relegated title gives the program that directory (`PW_PROGRAM_DIR`) and those variables (`--env=`), in addition to the image and up to 6 arguments, as before.

**Verified in a copy:**

- the patch is applied once and rejects a second application, and all three files compile;
- `build-guest-hw.py` builds ntdll, kernelbase and ucrtbase for x86_64 and i386 (77 reviews), and `process.c` only shows the two warnings that already existed;
- the `process.c` of ntdll with the changed hook compiles with the recipe of wine -boot and the head of the world, without new warnings;
- `wine_hardware.c` compiles without warning with the hors of `build-wine-hardware.py`.

<a id="325-worms-4-dejaba-ocupado-0x400000-el-modo-de-8-bits-de-age-of-empires-ii-w262c"></a>


### 32.5 Worms 4 left busy 0x400000; the 8 bit mode of Age of Empire II (W262c)

**Who occupied 0x400000** (`reports/wine-hardware-w261/physical/20261106T034740Z/run-0014.log`. It was the very WORMS 4 MAYHEM.EXE (loaded in 0x400000, size 0x4cd000). The line `image_not_at_base` of 2497 is your DLL that is relocated.

- **The failure.** Worms 4 failed in the line 2933 (`PWFAULT +619da`, NULL + 0x1c reading; it is missing OpenGL from 32 bits).
- **Why the guest did not finish.** His SEH handler did not treat him, and his own top-level filter (a failure informer) responded `EXCEPTION_EXECUTE_HANDLER`. So, the guest check of W208 in `UnhandledExceptionFilter` was never executed. The ntdll thread start directly called `NtTerminateProcess(GetCurrentProcess())`, and wow64 (B1) makes it the end of that thread only.
- **The consequence.** The guest did not go out or unload: he was still alive. (`live=1`) and occupying 0x400000. launcher.exe and Age of Empire II later failed with the error 487.

Set in `tools/build-guest-hw.py`, ntdll guest i386 and x86_64 (`call_thread_func` of `signal_i386.c` and `RtlUserThreadStart` of `signal_x86_64.c`):

- that `__EXCEPT` ends the guest of the thread as it does `RtlExitUserProcess` (W052): its threads end and its modules are downloaded;
- records `PWGUEST unhandled exception … after the program's own filter: the guest ends`;
- outside of a guest, it's still `NtTerminateProcess`.

The base_taken case of Age of Empire II is already covered by W262b, which deals with any error 487.

**Age of Empire II in 8 bits** (run- 0015). Full screen at 800x600 in 8 bit mode, with the Vulkan renderizer of wined3d:

- **The sequence.** A present changed the exchange interval, and the Vulkan swapchain was rehyed for `WINED3DFMT_P8_UINT`, format that no swapchain of Vulkan Admit.
- **The Crash.** `wined3d_swapchain_vk_destroy_vulkan_swapchain` It doesn't clean what it destroys. The blit acquired an image of the already destroyed swapchain: `vkAcquireNextImageKHR` → c0000005, status 3.
- **The fallback that already existed.** wined3d already presents by GDI when there is no swapchain of Vulkan, But your DIB had no color board, so a back buffer P8 would have gone out without a pallet.

Set in `tools/build-wined3d-hw.py`, `swapchain.c`:

- the destruction cleans the swapchain, the surface, the images, the lights and the count, and omits the null handles;
- the Vulkan swapchain-free blit records `PWD3D swapchain … has no Vulkan swapchain for …: GDI present` and returns error before `vkAcquireNextImageKHR`;
- the present draws that picture, and the following, by GDI;
- `swapchain_blit_gdi` apply the swapchain palette (the primary ddraw palette);
- a swapchain that cannot create its swapchain of Vulkan when created remains, with present for GDI, instead of failure of the device.

This is the way of all the DirectDraw games of 8 bit with the renderizer Vulkan (Age of Empire, StarCraft, Devil, C & C). The cost is `StretchBlt` in CPU of the back buffer of 8 bits per box.

**Verified in a copy:**

- the patch is applied once and rejects a second application;
- `build-guest-hw.py` builds the guest DLL from the two architectures, and `signal_i386.c` and `signal_x86_64.c` compile without warning;
- `build-wined3d-hw.py` builds wined3d.dll without warnings;
- W262, W262b and W262c are applied together in any order.

**Worms** (W261): the case base_taken of Worms 3D (launcher.exe → bin\ Worms3D.exe) covers W262b. Worms 4 is a game OpenGL and covers it W262 (Zink i386), along with Call of Duty.

<a id="33-regresión-de-w262-todo-programa-de-32-bits-cerraba-la-app-ce-34878"></a>


## 33. W262 regression: every 32 bit program closed the app (CE- 34878)

`reports/wine-hardware-w262/physical/20261106T155403Z`, runs 0001 - 0009: each log is cut without signal, without PWEXIT and without unhandled exception.

**The correlation.**

- All the executions that died (0001 - 0004 and 0006 - 0009) carried the `libgallium_wgl.dll` / `opengl32.dll` i386 of Mesa in syswow64. wined3d it matters opengl32, so `"opengl32"="native,builtin"` it would put Mesa into almost every program of 32 bits.
- The only execution that survived (run- 0005, the desk that made the relaunch) did not carry either of them.
- After loading Mesa, the main thread of 32 bits continued to make many calls to the system through new FPU transitions of W262 (e.g. AoE2 in run- 0009). The process died by creating the following thread of 32 bits: the last line is `PWWOW thread tid=… from=32`.

**Provisional conclusion.** Point to what it does Mesa when a thread of 32 bits is attached (`DllMain(THREAD_ATTACH)` of their front WGL, or their TLS implicit: the two versions, i386 and x64, have section `.tls`), not to the change of FPU. The x64 version works on scans since W076, and the i386 also died in a process of 32 bit relaunched alone (run- 0006).

**Next diagnostic step.** `C:\orbis\winedebug.txt` with `trace+module` records each call to `THREAD_ATTACH`.

**What the coordinator did.** He removed the `"opengl32"="native,builtin"` line of `build-wine-hardware.py`. So Wine reprefer your opengl32 builtin, as in W261, and the files of Mesa remain in syswow64 unused. The change of FPU of wow64native can be kept.

**W263** (`wow64-w263-relaunch-args-gl.patch.py`). In run- 0005 → run- 0006, the Worms 3D launcher passed the command line without quotes: `E:\PC\Worms 3D\bin\Worms3D.exe /W 1280 /H 720 /FS /REFRESH 60`. With that:

- `pw_hw_switch_program` took "3D\ bin\ Worms3D.exe" as the first argument;
- his limit of 6 arguments ruled out `/REFRESH 60`.

W263 corrige `native/wine_hardware.c`:

- a line of orders that begins with the image's own path the whole jumps, with spaces included;
- program change and relaunch support up to 16 arguments;
- if the opengl32 line is still in `build-wine-hardware.py`, it also takes it off.

**Verified in a copy:**

- applies once and rejects a second application;
- `wine_hardware.c` compiles without warning with the hors of `build-wine-hardware.py`;
- the tokenizer, compiled in the host, gives the 7 arguments of Worms 3D and does not change the result of the lines between quotes or the normal ones.

<a id="331-w264-opengl-de-32-bits-sin-ganchos-en-hilos-ajenos-y-opcional"></a>


### 33.1 W264: OpenGL of 32 bits without hooks on other threads, and optional

**probable cause of death of W262.** It is on the front WGL of Mesa: `stw_tls_init` of `src/gallium/frontends/wgl/stw_tls.c`, called since `DllMain(PROCESS_ATTACH)`.

- * all * process threads (`CreateToolhelp32Snapshot`) and install in each one its hook `WH_CALLWNDPROC` (`SetWindowsHookEx(…, NULL, tid)`, with the procedure within `libgallium_wgl.dll`).
- In the process of exploring that includes the 64 bit threads of the explorer itself and the threads of other programs. In a 32 bit title relegated, it includes the Wine threads that are only 64 bit.
- A 32 bit hook procedure called by a 64 bit thread executes 32 bit code as if it were 64 bit, in the next message that that thread receives.
- The Mesa of 64 bits in explorer (W076) does the same, but only on threads of its own architecture, and it works.

**The enumeration is not necessary.** A thread without hook data gets them the first time you use WGL (`stw_tls_get_data`). The threads created then get them in `DLL_THREAD_ATTACH`.

**W264** (`wow64-w264-gl32-hooks.patch.py`):

1. **`tools/vk-h0/patch-mesa-wgl-hooks.py`** (new, run `build-mesa-zink-i386.sh`). In compilations of 32 bits (`!_WIN64`), `stw_tls_init` omits the enumeration. The 64 bit is the same as before.
2. **`native/wine_hardware.c`.** With `C:\orbis\opengl32native.txt` present, the execution receives `WINEDLLOVERRIDES=opengl32=n,b` and records `PWGL opengl32 native (opengl32native.txt)`. Without the file, the Wine opengl32 building is used, as in W263. It is a switch on the console, without remodel, until it is checked that the Mesa of 32 bit is safe for all programs; then it can become the default value.

**Verified in a copy:**

- the patch is applied once and rejects a second application;
- the Mesa patch, applied to a copy of `stw_tls.c` and compiled with the exact order of each Mesa compilation:
  - in i386 it compiles without diagnoses and no longer refers `CreateToolhelp32Snapshot`;
  - in x64 it compiles the same, with the reference;
- `wine_hardware.c` compiles without warning.

<a id="34-resultados-de-w263-y-w265-argumentos-del-relanzamiento-nfs-underground-2"></a>


## 34. Results of W263 and W265: relaunch arguments; NFS Underground 2

Records: `reports/wine-hardware-w263/physical/20261106T170812Z`. Without Mesa i386 the app no longer closes, which confirms that the regression of W262 came from Mesa (section 33).

<a id="341-el-relanzamiento-por-base-ocupada-perdía-o-rompía-los-argumentos"></a>


### 34.1 The relaunch on an occupied basis lost or broke the arguments

- **Prince of Persia** (run- 0004: 4633): the pitcher passes `POP.exe` as `lpApplicationName` and only `-007` as `lpCommandLine`. Windows deliver that line as it is. `pw_hw_switch_program` took the first element as the name of the program and ruled it out: `args=0`, and POP.exe ended with the state 300 ("start the launcher").
- **3D Worms** (run- 0006: 6414): the line was `E:\PC\Worms 3D\bin\Worms3D.exe /W 1280 /H 720 /FS /REFRESH 60`, no quotes and a space on the road. The first element was left in `E:\PC\Worms`, `3D\bin\Worms3D.exe` became argv [1], and the limit of 6 arguments left out `/REFRESH 60`.

The W263 patch that Worms 3D already contemplated was not applied; W265 replaces it (`wow64-w265-relaunch-argv.patch.py`, in the note folder). Changes in `native/wine_hardware.c`:

- the name of the program at the start of the line is recognized as doing it Windows (`switch_program_name_length`):
  - first item between quotes: is the program if you name the image (complete route, a route tail from `\`, or the file name, with or without `.exe`) or if it ends in `.exe` / `.com`;
  - first item without quotes: the same test;
  - without quotes and with spaces: the shortest prefix, finished in a space, which is the route of the image or a tail of it, as it solves `CreateProcess` a route without quotes;
  - if none of that matches (the `-007` of PoP), the whole line is arguments;
- the arguments are separated with the rules of Microsoft C's runtime (`CommandLineToArgvW`): quotes that group, 2n bars before a quotation give n bars and the quotation opens or closes, 2n + 1 give n bars and a literal quotation, and `""` inside quotation is a quotation. Wine reconstruct the line from that argv and re-set quotes where there are spaces;
- are recorded `switch_program program_name=…` and a line `switch_program arg=…` on argument;
- up to 16 arguments in the change, in the relaunch (`MAX_LAUNCH_ARGS`) and in `native/wine_boot.c` (`MAX_WINE_ARGS`, before 8, and lines of `launch.txt` / `next.txt` up to 299 characters (before 259).

Check in a copy: the patch is applied once and the second is rejected; `wine_hardware.c` and `wine_boot.c` compete with the pitcher's options without warning; the separator, removed from the parched and compiled separate file, gives:

|Image|Line|Name recognized|Arguments|
|---|---|---|---|
| `…\POP.exe` | `-007` |(none)| `-007` |
| `E:\PC\Worms 3D\bin\Worms3D.exe` |the same route without quotes `/W 1280 /H 720 /FS /REFRESH 60`|the complete route| 7: `/W` `1280` `/H` `720` `/FS` `/REFRESH` `60` |
|the same|the route between quotes `/W 1280`|the route between quotes| `/W` `1280` |
| `C:\Games\a.exe` | `a -x "two words" C:\dir\ "q\"x" "a""b"` | `a` | `-x`, `two words`, `C:\dir\`, `q"x`, `a"b` |
| `C:\Games\a.exe` | `C:\PROGRA~1\a2.exe /x` | `C:\PROGRA~1\a2.exe` | `/x` |
| `C:\Games\game.exe` | `-007 C:\Games\game.exe` |(none)| `-007`, `C:\Games\game.exe` |
| `C:\Games\Sub Dir\game.exe` | `Sub Dir\game.exe -w` | `Sub Dir\game.exe` | `-w` |

Console tests: PoP from your launcher (`arg=-007`, `launch_arg --wine-arg=-007`, without the output with the state 300; 3D Worms from your pitcher with `C:\orbis\opengl32native.txt` present (W264), as it also uses OpenGL (in W263: `Failed to create internal global context` and a page failure in `0000001C`); a program with a route between quotes and arguments from Run, and `launch.txt`.

<a id="342-need-for-speed-underground-2-el-modo-1366x768-no-existe"></a>


### 34.2 Need for Speed Underground 2: mode 1366x768 does not exist

The FPU correction of W262 works in run- 0003: no longer appears `c0000090` nor the invalid frame. The new failure (run- 0003: 4365, `PWFAULT … address=005D2740 access=0 target=0`, `speed2.exe+1d2740`, read in 0) This (3963 - 3976 and again in 4319 - 4332) precedes this:

- the game asks D3D9 (DXVK) for a complete-screen device of 1366x768 A8R8G8B8;
- `NtUserChangeDisplaySettings` responds - 2 (`DISP_CHANGE_BADMODE`): the controller does not offer that mode;
- DXVK: `EnterFullscreenMode: Failed to change display mode` and `Failed to set initial fullscreen state`, so `CreateDevice` fails;
- The game does not check the error and uses the null device.

There is no missing DLL or check of CPU, and there are no wide-screen mods charged (neither `.asi` nor `dinput8` own). 1366x768 comes out of the saved configuration of the game, not from our list of modes. It is the same problem as Age of Empire II (maximum 800x600): the list of controller modes (ps5drv), which carries overlay -control. There is nothing to change in the world WoW64. What would be needed in the controller: accept to complete the usual sizes 4: 3, 5: 4 and 16: 9 (1024x768, 1280x1024, 1366x768...) and present them adjusted to 1280x720, as it does `WINE_PS5_FIT`. Meanwhile, choose 1280x720 or a list mode in the game options should avoid failure.

<a id="35-call-of-duty-en-w264-zink-could-not-create-swapchain-trazas-w266"></a>

## 35. Call of Duty in W264: "zink: could not create swapchain" (W266 traces)

Record: `reports/wine-hardware-w264/physical/20261106T172552Z/run-0001.log`, thread 0098, with `C:\orbis\opengl32native.txt` (Mesa of 32 (g) The Commission shall take the necessary measures to ensure that the measures are implemented. The game ends with state 3.

- 28440 - 28443: surface and swapchain of 1274x688 for the first window, `res=0`.
- 40629: `NtUserChangeDisplaySettings` returns - 2 (`DISP_CHANGE_BADMODE`; later `PWSINK mode set 800x600 … result=0` and the full screen window 0x3014e.
- 43666 - 43709: surface for `hwnd=0x2014e` and swapchain of 1024x700, `res=0`.
- 46726 - 46840: `PWVK32 begin vkCreateWin32SurfaceKHR hwnd=0` (`res=0`) and immediately `MESA: error: zink: could not create swapchain`, without any `vkCreateSwapchainKHR` between.

Probable reading, to be confirmed with the traces:

- the kopper surface takes the WGL framebuffer window of Mesa (`stw_st.c`, `stw_st_fill_private_loader_data`: `win32->hwnd = stwfb->fb->hWnd`. That framebuffer had no window: `stw_framebuffer_create` received `hWnd` NULL, either `WindowFromDC(hdc)` in `SetPixelFormat` or `wglMakeCurrent`, or because it was created for a window-free HDC;
- win32u responds to `vkGetPhysicalDeviceSurfaceCapabilitiesKHR` with `VK_ERROR_SURFACE_LOST_KHR` immediately if the `hwnd` of the surface is not a window (`vulkan.c`: `if (!NtUserIsWindow( surface->hwnd ))`);
- So that's why the kopper's `update_caps` fails before `kopper_CreateSwapchain`, and no `vkCreateSwapchainKHR` appears.

They are not the dimensions of the surface (`currentExtent` or the minimum and maximum range) after the change in failed mode: with `hwnd=0` win32u it does not even reach them.

`wow64-w266-zink-surface-trace.patch.py` (note folder) only adds traces, without changing behavior:

1. Mesa, only in the compilation of 32 bits (`#if !_WIN64`; 64 bit is the same), using the new `tools/vk-h0/patch-mesa-zink-trace.py`, which runs `build-mesa-zink-i386.sh` after `patch-mesa-wgl-hooks.py`:
   - `PWSTW framebuffer hdc= hwnd= window_from_dc= window= owner= format=` in `stw_framebuffer_create`;
   - `PWSTW kopper hwnd= window= hdc= window_from_dc=` when giving the window to kopper;
   - `PWZINK surface hwnd= window= res=`, `PWZINK surface support res= supported=`, `PWZINK caps res=` if it fails or `PWZINK caps current= min= max= images=` when they change, and `PWZINK displaytarget WxH: no surface` or `: swapchain res=` when the target display fails.
2. win32u (`tools/build-win32u-ps4.py`, next to the traces W254): `vkGetPhysicalDeviceSurfaceCapabilitiesKHR` and `…Capabilities2KHR` of the world of 32 bits of explorer: `PWVK32 surface caps hwnd= window= res=` if it fails, and `… current= min= max= images=` when the dimensions change (by process, not by call).

Check in copies:

- the patch is applied once and the second one is rejected;
- the Mesa patch is applied once and in the second one it reports that it is already applied;
- `zink_kopper.c`, `stw_framebuffer.c` and `stw_st.c` parcheated compile without errors or warnings with the exact order of the i386 and x64 compilations;
- The `vulkan.c` of win32u, with the W266 revisions applied to a copy of overlay, compiles with the builder's recipe and contains new chains. The three warnings it gives are of previous code (W254/W255);
- the shared source code of Mesa was not changed.

Test: Call of Duty with `opengl32native.txt` until full screen change. If the reading is correct, you will see the following, where - 1000000000 is `VK_ERROR_SURFACE_LOST_KHR`:

```
PWSTW framebuffer … hwnd=00000000 (y lo que dijo window_from_dc)
PWSTW kopper hwnd=00000000
PWZINK surface hwnd=00000000 window=0 res=0
PWVK32 surface caps hwnd=0 window=0 res=-1000000000
PWZINK caps res=-1000000000
PWZINK displaytarget …: swapchain res=-1000000000
```

The correction will depend on what HDC uses the game and what it returns `WindowFromDC` in the world of 32 bits.

<a id="36-resultados-de-w266-cod-portal-y-pop-w267"></a>


## 36. Results of W266: CoD, Portal and PoP (W267)

Records: `reports/wine-hardware-w266/physical/20261106T182510Z`. Portal and AoE2 go to full screen and NFS Underground 2 also; CoD 1 is left in black and PoP does not start.

<a id="361-cod-después-de-portal-el-lanzador-de-portal-seguía-vivo-en-0x400000"></a>


### 36.1 CoD after Portal: the Portal launcher was still alive at 0x400000

In run- 0005, CoD gives `base_taken` (error 487, line 8984). The occupant of 0x400000 (`image_not_at_base` in 2475, `occupied=0x400000+0x3f000`) is `Portal.exe`, the Portal pitcher:

- starts `hl2.exe` as a host (2474 - 2487) and its thread 0070 is still waiting;
- `hl2.exe` ends and is downloaded (8594 - 8630), but `Portal.exe` never comes out: its `exits status` does not appear, and in 8975 it goes on `live=1`.

The probable cause: the launch of a guest returns as `hProcess` a duplicate of the current **process**, the one to explore. A pitcher who waits for his game with `WaitForSingleObject(hProcess)` waits forever and retains his fixed base. The wait of Portal.exe is not drawn; the test below confirms or dismisses it.

W267 (`tools/build-guest-hw.py`, kernelbase of the guests, x86_64 and i386):

- `ps4_guest_launch` returns as `hProcess` a duplicate of the end-of-the-host event (`guest->ended`, W210, which is noted when it was finished and downloaded), with access `SYNCHRONIZE | EVENT_QUERY_STATE`. A wait on that handle comes back when the guest's done. It is recorded `PWGUEST process_handle …: the guest's end event`;
- `GetExitCodeProcess`, before a handle that is not a process (`STATUS_OBJECT_TYPE_MISMATCH` or `STATUS_ACCESS_DENIED`) and matches (`NtCompareObjects`) with one of those events (the last 64), respond `STILL_ACTIVE` until the host ends and then the status of his `exit_process` (0 if he never called him);
- `dwProcessId` is still the one to explore, and `TerminateProcess` or `GetProcessId` over that handle fail, because it's an event.

<a id="362-cod-solo-título-aparte-la-dxgi-de-dxvk-dentro-del-cargador-de-vulkan"></a>


### 36.2 CoD alone (separate title): the DXGI of DXVK inside the Vulkan charger

In run- 0006 there is no line `PWSTW` or `PWZINK`, although the traces are in the DLL of Mesa (`syswow64`) and `warn+debugstr` is active. Mesa never created a framebuffer: CoD stayed while zink created his screen.

- The Khronos charger (`vulkan-1.dll` of syswow64, which from Mesa i386 is charged as `native`) load `dxgi.dll` to order the adapters.
- In a separate 32 bit title, that `dxgi.dll` is the DXVK (`"dxgi"="native,builtin"`, W172). DXVK starts inside the charger (21416: `GetPackagesByPackageFamily`, d3dkmt, `CM_Get_DevNode`, `DXVK: v2.7.1`, again the charger). The same cycle is repeated 9 times and the thread is silent.
- In the world of exploration (W264 run- 0001: 42364) the `dxgi` was the building of Wine (`AppDefaults\explorer.exe`, `"dxgi"="builtin"`, W190), and zink reached his swapchains.

W267 (`native/wine_hardware.c`): with `C:\orbis\opengl32native.txt`, `WINEDLLOVERRIDES=opengl32=n,b;dxgi=b`, as in the world of exploration. They only change the executions they chose for the Mesa of 32 bits. A program D3D10/11 that runs apart with that present file would receive `dxgi` of Wine instead of DXVK, so for it you have to remove the file.

<a id="363-prince-of-persia-dos-exe-con-base-fija"></a>

### 36.3 Prince of Persia: two EXEs with a fixed base

The headers of `PrinceOfPersia.EXE` (the pitcher, 0x1d000) and `POP.exe` (0x739000), read from the console, have `IMAGE_FILE_RELOCS_STRIPPED` and no directory `.reloc`. Both of them ask for the fixed base 0x400000, so they can't share the process; loading the pitcher on another base is not possible.

Released alone (run-0008, already with `-007`, W265), `POP.exe` Look. `PrinceSM` in your folder (1099, as file, does not exist) and ends with status 300. The pitcher didn't write any files. `PrinceSM` in run-0007 or in the run-0009, So it's probably an object with a name (shared memory) that the pitcher keeps alive. Without a second process there is no arrangement in this round; W267 it doesn't change anything for PoP.

<a id="364-comprobación-y-pruebas"></a>


### 36.4 Checking and testing

Check in copies:

- the patch is applied once and the second one is rejected;
- the grated builder is parted, and its 84 revisions (5 of W267) are applied on a copy of overlay;
- `kernelbase/process.c` compiles with the compilation order set for x86_64 and i386. Your warnings are of previous code: `wcstoul` undeclared and an `name` unused variable;
- `wine_hardware.c` compiles without warning.

Console tests:

- Portal from scout and out of the game: `PWGUEST process_handle … hl2.exe`, and then the `exits status` and the download of `Portal.exe`; then CoD from explorer must start at 0x400000, without `base_taken`;
- CoD only with `opengl32native.txt`: `launch_arg --env=WINEDLLOVERRIDES=opengl32=n,b;dxgi=b`, `dxgi.dll` builtin and lines PWSTW/PWZINK (W266);
- regressions: a program initiated from the desktop, unexpected pitchers (Worms 3D, PoP: relaunch by `base_taken` as before) and reboot of Pale Moon (W210).

<a id="37-nfs-underground-2-microcortes-que-se-destraban-con-el-mando-trazas-w268"></a>


## 37. NFS Underground 2: microcycles that are threaded with the control (traces W268)

Registration: `reports/wine-hardware-w266/physical/20261106T182510Z/run-0009.log`. `speed2.exe` runs in the world of exploring from the line 33058; its main thread is 0098 and the presenter of DXVK is 00a8. He ran NFS Most Wanted (`speed.exe`, 32039).

What the record shows:

- **At stake** `PWVK present fps` gives between 78 and 110 (35551 - 35943).
- **Then** goes down to 15,7 (35969), 1,5 (35988), 7,3 (36049), and 29,4, 12,8 and 12,4 to the end (36350). `frame_presented` from 3008 to 3072 takes 3,2 s (156920, and from 3072 to 3136 it takes 4,0 s (160958).
- **The samples `PWTELEM`** come out every 0,5 in play and with 1,4 a 2,6 s of separation in the cuts. There's less CPU (`cpu_mp` from 17 to 23 thousand, against 30 a 34 thousand) and almost no GPU (`gpu_mp` from 108 to 5387, against 12000 to 14600). The game waits, it doesn't count. These samples are taken `native/telemetry.c` when the HUD of MangoHud requests them, one per picture and at most every 0,5.
- **Only in the cuts** the thread 0098 executes callbacks user of 32 bits: returns of `KiUserCallbackDispatcher` of wow64 via `RtlUnwindEx` with code 80000026 (`STATUS_LONGJUMP`, between 2 and 6 per sample, and none in the 40 previous game. Just then, messages come to the window procedure of the game.
- **The input** is not recorded after `PWPAD game_mode=1` (34684), so the control or keyboard events that end each cut cannot be aligned.
- **There is no** missing DLL, failure or server watch line (`PWSERVER stuck_s` in that interval.

The hypothesis, unconfirmed, is that of the coordinator: a timeout wait (a `Sleep`, a `MsgWaitForMultipleObjects`, or a winmm, dsound or dinput timer thread) that the wineserver in process ends late, until an input event awakens its loop. The server's timeouts are their lists of timeouts: they win in `get_next_timeout` and `poll()` wait for them (`pw_wine_poll` in platform/ps4: `sceNetEpollWait`, with a new epoll in each call).

`wow64-w268-server-late-timers-trace.patch.py` (note folder) only adds traces in `server/fd.c`, through `tools/build-wine-delete-server.py`:

- `PWSERVER late_timer n= late_ms= list=rel|abs callback=`: a server timer that beats more than 50 ms after its time. `thread_timeout` is the timeout of a waiting and `timer_callback` a waitable timer; the address is compared to ELF symbols or other executions;
- `PWSERVER late_wake n= asked_ms= took_ms= ret= users=`: a `poll()` that returns more than 50 ms after the timeout it received. With `ret=0` the timeout itself was late; with `ret>0` a descriptor woke him up, after when he had to overcome;
- The first 20 lines of each type are recorded and then one of each 100.

Check in a copy: the patch is applied once and rejects the second, and the `fd.c` of the resulting server (tested source check included) compiles with the order of the server compilation without diagnoses.

Test: NFS Underground 2 in explorer. Play up to a cut, do not touch the command or keyboard for a few seconds and then move them. Reading:

- lines `late_timer` or `late_wake` within the cut, between the lines `PWVK present fps` that come down: the hypothesis is confirmed;
- none: the cut is on the client's side, in a waiting for a message or an object that no one points out, and the next trace goes there.

<a id="38-w267-portal-y-cod-cod-sale-con-estado-3-después-de-iniciar-gl-trazas-w269"></a>


## 38. W267: Portal and CoD; CoD exits with status 3 after starting GL (traces W269)

Records: `reports/wine-hardware-w267/physical/20261106T185934Z`.

The process handle (W267) arrangement works. In run- 0003 `Portal.exe` it comes out and is downloaded after `hl2.exe`, and CoD starts to explore without `base_taken`. The 32 bit GL also comes (run- 0002, thread 0070):

- `PWSTW framebuffer hwnd=00020128 format=43` (20206);
- surface with `supported=1` and caps of 1024x768 (20691);
- `vkCreateSwapchainKHR 1024x768 res=0` (20772).

Then, for 8350 lines, the thread 0070 only runs callbacks of 32 bit user: 1042 `RtlUnwindEx` with code 80000026 (`STATUS_LONGJUMP`), which are the returns of `KiUserCallbackDispatcher` of wow64, that is, messages to the program window procedures. No picture is shown (there are no `PWVK show_frame`) and there are no MESA, abort, MessageBox or unhandled lines. Then come control clicks and Enter, the foreground moves from 0x2013e to the GL window 0x20128 (the two of the thread 0070) and appears `exits status 3` (29122.

Probable, unconfirmed reading:

- the CoD engine (Quake III), in the face of a fatal error (`Sys_Error`, or `Com_Error` with `ERR_FATAL`), shows the error in its own console window and waits in a message loop until the user leaves;
- in that console, the error goes to a static control, the "error box," with `SetWindowText`, and the text of the console to an edit control;
- The 1042 callbacks are that loop, 0x2013e would be the console and enter the exit button. The 3 is the state with which that path comes out, or the `abort()` of the C-run;
- the text of the error is left in that window, not in the record;
- a cause known with Mesa: the games of the Quake III engine copy `GL_EXTENSIONS` to a fixed buffer (`glConfig.extensions_string`), and the chain of Mesa and zink is much longer than in 2003. For these games there is `MESA_EXTENSION_MAX_YEAR`.

`wow64-w269-cod-exit-text-gl-trace.patch.py` (note folder) only adds traces:

1. **win32u** (`defwnd.c`, `set_window_text`: `PWTEXT hwnd= text=` for each window text that sets a thread of 32 bits (`WM_SETTEXT` reaching `DefWindowProc`: static controls, dialogues, message boxes and titles), the first 300. The error box on the Quake III console is one of them. The console buffer (`EM_REPLACESEL`) remains in the control of user32 and does not trace.
2. **kernelbase of the guests** (`ps4_guest_exit_process`, x86_64 e i386): `PWGUEST exit_caller n <exe>+offset at <pila>` for the first 12 words of the pile of the thread that comes out that point into the image of the program. They are the return addresses of the code that called `exit` / `ExitProcess`, plus some data points. These offsets, contrasted with the read EXE of the single reading console, distinguish `Sys_Error`, `Com_Quit` and `abort`.
3. **Mesa of 32 bits** (`patch-mesa-zink-trace.py`, `src/mesa/main/getstring.c`): `PWGL version=... extensions_length=` the first time a program asks `GL_EXTENSIONS`, and `PWGL vendor= renderer=` once.

Check in copies:

- the patch is applied once and rejects the second, and the three edited scripts are parted;
- The `defwnd.c` of win32u compiles with the builder's recipe and contains `PWTEXT`. Your warning in the 904 line is of previous code;
- The `process.c` of kernelbase compiles for x86_64 and i386 with the 85 revisions applied. The warnings are previous (`wcstoul` and `name`);
- the Mesa trace script traces `getstring.c` once, without touching the files already drawn in W266, and `getstring.c` compiles without diagnoses with the orders of i386 and x64;
- the shared source code of Mesa was not changed.

Test: CoD from explorer, with `opengl32native.txt` as in W267, until it stops. Read:

- the lines `PWTEXT` before the output, where the error should be;
- the line `PWGL`: a `extensions_length` well above 1024 or 4096 points to the fixed buffer;
- the offsets of `exit_caller`.

<a id="381-corrección-de-la-lectura-de-cod-y-w269-unificado"></a>


### 38.1 Correction of reading of CoD and W269 unified

The user clarifies: "It does not make a mistake, after a while it closes." No sign appeared, so reading the Quake III error console is in doubt. What the record does show: the program never presented a picture and ended on its own with status 3 (`abort()` of the C runtime, or a `exit(3)` of the game). The copy of `GL_EXTENSIONS` to a fixed buffer remains a candidate, because it corrupts the engine's state without causing a failure. The traces of 38 remain the right ones.

The 38 script is replaced by `wow64-w269-cod-maxpayne.patch.py`, which includes the same traces of CoD and Max Payne's (38.2 and 38.3). The previous one was never applied and removed from the note folder.

<a id="382-max-payne-1-su-propio-msvcrtdll-arreglo-w269"></a>


### 38.2 Max Payne 1: your own MSVCRT.DLL (arrangement W269)

`reports/wine-hardware-w267/physical/20261106T190602Z/run-0006.log:2292` shows `PWGUEST clash app=MaxPayne.exe name=msvcrt.dll loaded=C:\windows\syswow64\msvcrt.dll` and then `not_a_guest` with error 1114. The game folder brings its own `MSVCRT.DLL`, along with MFC42, MSVCP60 and MSVCITT.

- **Why it hits:** shock check (W182, Pale Moon mozgue against Gecko) except only the DLL loaded from `GetSystemDirectory`, that in the world of 32 bits of explorer is system32, while your DLL is loaded from syswow64.
- **What are you doing? Windows:** `msvcrt.dll` is a KnownDLL (the `wine.inf` of Wine it declares it so, just as Windows). Windows always use the system copy, have what the program folder has.
- **What does Wine:** the charger resolves a route-free import with the module already loaded with that name (`find_dll_file` → `find_basename_module`, in `loader.c`), before looking for files.

Setting (`tools/build-guest-hw.py`, `ps4_guest_launch` from kernelbase of guests): a loaded DLL whose name is in KnownDLLs of Wine It doesn't count as a shock. It is recorded `PWGUEST clash_known name=…` and the program is loaded with the system copy, as in Windows. The other names (the case of Pale Moon) are rejected as before.

<a id="383-max-payne-2-excepciones-c-antes-de-salir-traza-w269"></a>


### 38.3 Max Payne 2: exceptions C + + before leaving (trace W269)

Same record, from the line 5324:

- the thread 0074 load `syswow64\D3D9.DLL` (DXVK) and download it immediately, without calling `Direct3DCreate9` (there is no line of DXVK);
- then comes a chain of exceptions C + + (e06d7363) launched in `rlmfc.dll`, the Remedy base library in 02E00000 (02E1C18E, 02E1C468, 02E1C610 and 02E1D5E0), and in MSVCR71, which reaches the EXE handler (004D43C2);
- a window lives about 4 s and the program comes out with a state 0. The exception says why and it's not in the register.

Trace (kernelbase of the guests, in the vectorized handle W207):

- `PWCXX n= thread= type=<primer tipo atrapable> what=<mensaje de una std::exception> throw=<módulo+offset>`;
- the EBP chain as `PWCXX n frame k módulo+offset`;
- the 24 first exceptions C + + guests;
- in x86 the ThrowInfo has points and in x64 RVAs from the base of the image;
- It's all read with `NtReadVirtualMemory`, so an invalid pointer doesn't read anything instead of failing.

<a id="384-comprobación-de-w269"></a>


### 38.4 W269

In copies:

- the patch is applied once and rejects the second, and the three edited scripts are parted;
- with the 88 guest builder reviews (4 of W269), `kernelbase.dll` **compiles and links** for x86_64 and i386, and contains `PWCXX`, `clash_known`, `exit_caller` and `process_handle`. The warnings of `process.c` are of previous code;
- the `defwnd.c` of win32u compiles with the builder's recipe;
- `getstring.c` of Mesa compiles without diagnoses for i386 and x64;
- the shared source code of Mesa was not changed.

Console tests:

- Max Payne 1 from explorer: `clash_known name=msvcrt.dll` and `load_end error=0`, or the following crash, registered as before, if any of your DLL is loaded from another folder;
- Max Payne 2: the lines `PWCXX` before leaving, and `PWTEXT` if you create any dialogue;
- CoD: `PWGL`, `PWTEXT` and `exit_caller`;
- regression: Pale Moon after a web view of Gecko is still rejected.
