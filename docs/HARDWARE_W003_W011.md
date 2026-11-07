<a id="pruebas-físicas-w003w011-wine-arranca-en-la-ps4-hasta-el-servidor-interno"></a>


# Physical tests W003 - W011: Wine starts at PS4 to the internal server

[English](HARDWARE_W003_W011.md) | [Español](HARDWARE_W003_W011-es.md)

They all use the same Title ID `ORBW00002` (APP_VER 01.02 to 01.10) and the runtime of W001 already up to `/data`. Each physical Runs is in `reports/wine-hardware-w0NN/physical/<ts>/`, with its log and its `report.json`.

From W004, at the user's request, the packages are uploaded without a smoke test in the emulator. W003 was the last one to pass through the emulator (`reports/wine-hardware-w003/20261031T061617Z/`, `passed`).

<a id="hechos-de-la-plataforma-medidos-en-la-consola"></a>


## Wall facts measured on the console

|Call (app of PS4, firmware 12.52)|Result|
|---|---|
| `dup2(fd, 1/2)` | EPERM |
| `fcntl(fd, F_DUP2FD)` (FreeBSD 10) | EINVAL |
|`dup(fd)` on an open file| **EPERM** |
| `fcntl(fd, F_DUPFD)` (FreeBSD 0) | EINVAL |
|`lstat` (import of libkernel)| **EPERM** |
|`sceKernelStat` per route|works, but returns **st_ino = 0 and st_dev = 0**|
| `sceKernelFstat` |works, with real in- and dev|
| `readlink` |the app ends in that call (W002)|
|`socketpair` + `sendmsg` / `recvmsg` with `SCM_RIGHTS`|works: the descriptor received is the same file (W012)|
|`fcntl(fd, F_GETFD)` and `F_SETFD`|**EINVAL**, also on a descriptor received (W012)|
|`F_GETFL`, `F_SETFL O_NONBLOCK` and `FIONBIO` over a file|(W013)|
|`F_GETFL` on a socket| 2 (O_RDWR) |
|`F_SETFL O_NONBLOCK` and `FIONBIO` on a socket| **EACCES** (W013) |
|First free descriptor|17 (no fd 0 - 2 usable)|

<a id="qué-se-corrigió-en-cada-build"></a>


## What was corrected in each building

| Build |Blocking on the console|Corrigendum|
|---|---|---|
| W003 |preflight 95 without detail|No `readlink` direct. `pw_wine_lstat` use `sceKernelStat` before EPERM. The PWBOOT markers of `sceKernelDebugOutText` go to the log|
| W004 | `file-identity` |The preflight records each case in the debugging channel|
| W005 |ino/dev 0 per route|The check accepts fd ≥ 0 (previously required ≥ 3) and records values|
| W006 |Wine enters `__wine_main` and the app falls (CE-34878-0)|`pw_wine_stat` takes ino/dev of `fstat` when the route gives 0/0|
| W007 |without markers after `__wine_main`|`--wrap` of `write`, `fprintf`, `vfprintf`, `fputs` and `fwrite`: what goes to stdout/stderr passes to log|
| W008 |falls between `first_teb_ready` and the connection to the server|Markers in `dbg_init` and at each step of the internal server|
| W009 |falls in `init_directories`|Block markers and signal handler in the launcher: SIGSEGV in `release_object(NULL)`|
| W010 |`create_fd_mapping` of NLS failure|The server records status and errno and ends with an explicit error: STATUS_ACCESS_DENIED, errno 1; `dup()` da EPERM|
| W011 |the customer receives EINVAL of `recvmsg` when receiving a descriptor|`pw_wine_dup`: before EPERM reopens the registered route when opening the file|
| W012 |the same as W011; the marker shows `recvmsg_failed stage=cloexec errno=22`|Layer markers in `sendmsg` / `recvmsg` and an isolated probe of `SCM_RIGHTS`|
| W013 |**passed**: `result.txt` identical to Windows, output 0|`MSG_CMSG_CLOEXEC`: to EINVAL of `fcntl(F_SETFD)` the descriptor is not marked (there is no `exec`); `F_GETFL` / `F_SETFL` / `FIONBIO` probes|

Up to W010, on the console Wine it reaches:

```
paths_ready, virtual_ready, environment_ready, first_teb_ready, debug_ready,
server_step sock_init … load_intl_file, init_directories (dispositivos, sesiones,
tipos, symlinks, eventos) → dir_intl_mapping: dup EPERM
```

<a id="decisiones-de-plataforma-documentadas-no-éxitos-simulados"></a>


## Platform decisions (documented, not simulated success)

- **`lstat` → `stat` to EPERM.** The app cannot read links, so Wine He doesn't see any. Marker: `PWBOOT lstat_eperm_served_by_stat`.
- **ino/dev from `fstat`.** If the route cannot be opened, the real zeros remain.
- **`dup` for reopening** (W011). It's only for files and directories open by `pw_wine_open`. The new descriptor has its own offset and its own state flags; the offset is copied once. Sockets and pipes return the real EPERM. Marker: `PWBOOT dup_eperm_reopen_by_path`.
- **Stdout/stderr to log** only in the hardware launcher (`--wrap`), not in Wine.
- **Close-on-exec without effect** (W013).
  - `pw_wine_recvmsg` with `MSG_CMSG_CLOEXEC` does not fail when `fcntl(F_SETFD)` gives EINVAL.
  - An app of PS4 cannot do `exec`, and Wine runs with `WINELOADERNOEXEC=1`, so the mark has no effect.
  - Any other errno is still a mistake.
  - Marker: `PWBOOT cloexec_einval_no_exec`.

<a id="próximo-paso"></a>


## Next step

- Run W012 and lower the log with `python3 tools/fetch-hardware.py --build W012 --host 192.168.68.104`.
- The following friction points are likely on the same path:
  - the passage of descriptors between client and server (`SCM_RIGHTS` within the process; see W011);
  - the executable memory for PE64 and the translator.
<a id="regresiones-linux-con-el-código-de-w011"></a>


## Linux returns with W011 code

- **First Runs** (`reports/wine-hardware-w011/regressions-25/`): one case failed, the empty prefix. It ended with 0xc000007b instead of the 0xc0000135 expected.
  - Cause: the assembly table applied to all prefix. In a new prefix, Wine creates its own links and its `z:` points to `/`, not `../..`.
  - Correction: `wine_boot.c` records the table only in `--prepared-prefix` mode, which is the hardware mode.
- **Second Runs** (`reports/wine-hardware-w011/regressions-25b/`): **passed**. They passed the text, `explorer` and the complete matrix of the increment 24 with that of 18.
- W011 was rebuilt with that correction. It's in `out/wine-hardware-w011/` and it's not up yet.

<a id="resultado-físico-de-w011"></a>


## Physical result of W011

`reports/wine-hardware-w011/physical/20261031T182023Z/` (the console went to 192.168.68.104).

- It appears `PWBOOT dup_eperm_reopen_by_path`: the reopening by route resolved the mapping of NLS.
- The internal server completes `init_directories`, `init_threading` and `init_registry`, and creates its thread. The channel between the client and the server is ready (`inprocess_channel_ready`).
- The first receipt of a descriptor in the client fails: `wine client error:0: recvmsg Invalid argument`. Wine ends with `_exit(1)` and then the driver records signals during the output.
- It's still missing where the EINVAL comes from. It may come from the kernel, the conversion of the header or the `fcntl(F_SETFD)` with which it is emulated `MSG_CMSG_CLOEXEC`. W012 records it.

## W012

- `pw_wine_sendmsg` and `pw_wine_recvmsg` emit `PWBOOT <llamada>_failed stage=header|control|kernel|flags|cloexec errno=…` in each rejection.
- The launcher tests `SCM_RIGHTS` isolated:
  - `socketpair`, send a file and receive it without hors, with `fcntl` F_GETFD/F_SETFD on the descriptor received;
  - the same with `MSG_CMSG_CLOEXEC`.
- PKG `/data/pkg/orbis-win-W012-f8a2adfe0e74.pkg` (APP_VER 01.11), uploaded and verified.
- Result (`reports/wine-hardware-w012/physical/20261031T183216Z/`):
  - `SCM_RIGHTS` works: a file is sent and received as fd 20, with the same odour and device.
  - `fcntl` F_GETFD and F_SETFD give EINVAL. This is why it fails `MSG_CMSG_CLOEXEC`, both in the probe and in Wine (`recvmsg_failed stage=cloexec errno=22`).

## W013

- `/data/pkg/orbis-win-W013-333f3d8fb580.pkg` (APP_VER 01.12), uploaded and verified.
- Change: close-on-exec no effect to EINVAL (see decisions).
- New probes: `F_GETFL`, `F_SETFL O_NONBLOCK` and `ioctl(FIONBIO)` on a file and a socket. Wine uses `F_SETFL` for non-blocking descriptors.

<a id="resultado-físico-de-w013-passed"></a>


## Physical result of W013: passed

`reports/wine-hardware-w013/physical/20261031T195509Z/`, a run.

- They appear `PWBOOT cloexec_einval_no_exec` and `dup_eperm_reopen_by_path`, and the channel between the client and the server works.
- Wine load the DLL. The `image_read_fallback` are section readings instead of mapping, along the already existing path.
- Run `console32-bare.exe` by WoW64 with wowprospero.
- `result.txt` = `sum=500500;thread=ok;dll=ok`. Your SHA- 256 `029a3f30…a05` is identical to `reports/increment11-windows-reference/result.txt`.
- `process_exit method=exit status=0`.
- Unresolved observations, after the outcome:
  - `fixme:ntdll:create_logical_proc_info stub`.
  - Two `err:wow:log_reset syscall 0x43 came back replaced`.
  - After `exit(0)`, the driver records three signals 31 (trapno 22) inside libkernel and a `err:seh:call_seh_handlers invalid frame` during closure.
- **Second Runs** (`reports/wine-hardware-w013/physical/20261031T195721Z/`, `run-0002.log`): **passed**.
  - `result.txt` has the same SHA-256.
  - The `result.txt` of the first run, archived by the launcher, also matches.
  - Output 0, with the same signals and the same `err:` in the closure.
  - It also appears `err:seh:NtRaiseException Exception frame is not in stack limits` after the exit.
  - Two out of two runs passed.
- Closing analysis:
  - The "signal 31" is SIGSYS in the SDK (musl/Linux numbering. The `pw_wine_sigaction` trampoline translates that of FreeBSD.
  - `err=0x2` is the length of the instruction `syscall`, which FreeBSD keeps when entering a syscall.
  - The first occurs in the thread 0024 just after `process_exit method=_exit`, with `rip` inside libkernel.
  - Hypothesis, not yet confirmed: a retail app receives SIGSYS in the `exit` syscall of `_exit`. The driver calls back to `_exit` and the system ends up killing the app.

## W014

- `/data/pkg/orbis-win-W014-674d897fd4ab.pkg` (APP_VER 01.13), uploaded and verified. Tie `libSceSystemService`.
- The driver also records `si_code`, `rax` (the syscall number), `rdi` and the return direction in the stack.
- `_exit`:
  - The first caller records the state and requests the system closure with `sceSystemServiceLoadExec("exit", NULL)` (marker `system_close load_exec rc=`).
  - If the rc is 0, wait until 10 s for the system to close the app.
  - If the rc is not 0, or if the 10 s (marker `system_close_timeout`) pass, the original `_exit` is run.
- A SIGSYS does not call `_exit` again: wait for the same closure.

- Result (`reports/wine-hardware-w014/physical/20261031T204439Z/`): **passed**.
  - `result.txt` has the same SHA- 256 as Windows and the output was 0.
  - The log ends at `process_exit method=_exit status=0`.
  - The `system_close load_exec rc=` marker does not appear, no sign, no closing `err:seh`. The app ended within `sceSystemServiceLoadExec("exit")`, without coming back.
  - According to the user, the app returned to the console menu without the error CE-34878-0.
  - Since there was no SIGSYS, the syscall number was not measured. The syscall `exit` hypothesis remains indirect.
- Pending:
  - non-blocking sockets: `F_SETFL` and `FIONBIO` give EACCES on a socket. This EXE didn't need it.

<a id="w015-primer-programa-gui-en-la-consola"></a>


## W015: first GUI program on the console

- `/data/pkg/orbis-win-W015-8b373bb3ac89.pkg` (APP_VER 01.14), uploaded and verified.
- Program: `C:\orbis\gui-window64.exe`, the fixture PE64 of the increment 24, without wowprospero.
  - Open a window, paint it and read a pixel.
  - It writes `result.txt`, which is compared to `reports/increment24-windows-reference/result.txt` (`painted=1;pixel=8c3c14;client=464x280`).
- Runtime: the W014 plus the closing PE64 GUI (`out/wine-gui`), `gui-window64.exe`, `gui-text64.exe` and the Tahoma and Marlett sources with their record.
  - They prepared as with `run-linux-wine.py --wine-gui`.
  - They went up. 64 new or changed files, including `system.reg` and `user.reg` with the sources. The others 429 They were there..
- The tables that have Wine are stored in `/data/orbis-win/w015/frames`.
- Result (`reports/wine-hardware-w015/physical/20261031T212754Z/`): **passed**.
  - `result.txt` = `painted=1;pixel=8c3c14;client=464x280`, identical to Windows. Output 0 and clean closure.
  - Wine presented five pictures. In the room (`frame-000004.png`) you see the window with 129.920 pixels of the painted color, which is exactly 464 × 280.
  - Variance with the emulator:
    - In the console, the title text is drawn with Marlett's glyphs (symbols), while the buttons on the bar go well.
    - In the fork it went backwards: title with Tahoma and buttons like "0 1 r."
    - The log has no source messages because it was not activated `+font`.

<a id="w016-diagnóstico-de-fuentes"></a>


## W016: source diagnosis

- `/data/pkg/orbis-win-W016-5e857e989b1a.pkg` (APP_VER 01.15), uploaded and verified.
- Same program that W015, with `--winedebug=+font`.
- Sound in the launcher: `open`, `fstat` and `mmap(PROT_READ, MAP_PRIVATE)` of `tahoma.ttf`, `tahomabd.ttf` and `marlett.ttf`, plus the first 4 bytes, as does `map_font_file` in win32u.
- Result (`reports/wine-hardware-w016/physical/`): **crashed**.
  - The probe shows that the three sources are opened and well mapped (`magic=00000100`). The `mmap` is ruled out as a cause.
  - Wine stops after `paths_ready`, without reaching `virtual_ready`. The app is left in "STARTING WINE" and then the console closes it with error, without a driver's marker.
  - The only difference with W015 is `WINEDEBUG=+font`. The first `TRACE` of `virtual_init` reads the debugging options.

<a id="w017-dónde-se-cuelga-winedebug"></a>


## W017: where it hangs `WINEDEBUG`

- `/data/pkg/orbis-win-W017-0627b3c68517.pkg` (APP_VER 01.16), uploaded and verified.
- Overlay:
  - markers `PWBOOT debug_options start|stderr_checked|app_name|parsed` in `init_options` (`debug.c`);
  - `PWBOOT virtual_step first_trace_done` in `virtual_init`.
- Same program and same `+font` as W016.
- Remote cleaning requested by the user: in `/data/pkg` the PKG W001 - W016 were deleted. There are W017, H001, H001B and two packages outside the project.
- Result (`reports/wine-hardware-w017/physical/20261031T214209Z/`): **crashed**, the same hang as W016.
  - `debug_options`: `winedebug=+font`, stderr checked, `app_name=gui-window64.exe` and `parsed count=1`. The reading of `WINEDEBUG` works.
  - The last marker is `virtual_step first_trace_done`. The hang is later in `virtual_init`: limit of the address space, writewatch, `mmap_init` or virtual heap.

<a id="w018-separar-las-dos-diferencias-con-w015"></a>


## W018: separate the two differences with W015

- `/data/pkg/orbis-win-W018-590c79286b38.pkg` (APP_VER 01.17), uploaded and verified. The PKG of W017 was deleted.
- The source probe is removed from the launcher (`HW_FONT_MAP_PROBE` undefined) and maintained `+font`.
- Markers in each remaining step of `virtual_init`: `addr_space_limit=`, `writewatch_done`, `mmap_init_done` and `virtual_heap=`.
- How to read the result:
  - If it happens, the launcher's source probe was the cause of the hang.
  - If it hangs, the last marker indicates what step it takes.
- Result (`reports/wine-hardware-w018/physical/20261031T214736Z/`): **crashed**, the same hang without the probe.
  - The probe is ruled out as a cause.
  - `addr_space_limit=0x7fffffff0000`; `writewatch_done` and `mmap_init_done` pass.
  - Wine hangs in `alloc_virtual_heap`, where it maps with `MAP_FIXED` the block of views and the protection table at the end of a reserved area.

<a id="w019-intentos-de-alloc_virtual_heap"></a>


## W019: attempts to `alloc_virtual_heap`

- `/data/pkg/orbis-win-W019-507b1d6fe756.pkg` (APP_VER 01.18), uploaded and verified. The PKG of W018 was deleted.
- New markers:
  - `virtual_step heap_request size= limit=`;
  - `virtual_heap_try area= at= size=` and `virtual_heap_result ret= errno=` in each attempt;
  - `virtual_heap_fallback_alloc`.
- It is maintained `+font`, to reproduce the hang.
- Result (`reports/wine-hardware-w019/physical/20261031T215509Z/`): **crashed**.
  - `heap_request size=240000 limit=0x7fffffff0000`.
  - First attempt: area `0x7ffffe000000-0x7fffffff0000` (which you reserved `mmap_init` with the kernel reservator), `at=0x7fffffdb0000`.
  - There is no `virtual_heap_result`. The app ends inside that `mmap(MAP_FIXED, RW)`, without the driver recording any signals.
  - The same way worked in W013 and W015.

<a id="w020-con-o-sin-winedebug"></a>


## W020: with or without `WINEDEBUG`

- `/data/pkg/orbis-win-W020-4b6a76fa6c46.pkg` (APP_VER 01.19), uploaded and verified. The PKG of W019 was deleted.
- The same arguments as W015, without `+font`, with all the markers of `virtual_init` and `alloc_virtual_heap`.
- New probes in the launcher:
  - `flexible_memory`, with `sceKernelAvailableFlexibleMemorySize`;
  - `top_region`: up to 8 regions of `sceKernelVirtualQuery` from `0x7ff000000000`.
- How to read the result:
  - If it happens, the hang depends on `WINEDEBUG`.
  - If he hangs in the same place, it's a difference between runs, and probes show the state of that area.
- Result (`reports/wine-hardware-w020/physical/20261031T215958Z/`): **crashed** in the same `virtual_heap_try`.
  - `WINEDEBUG` is discarded. W015 went through a difference between runs.
  - `flexible_memory available=447741952`: there is no lack of flexible memory.
  - `top_region rc=0x8002000d`: `sceKernelVirtualQuery` responds EACCES in that area.

<a id="w021-sin-reservar-la-zona-alta"></a>


## W021: without booking the upper area

- Platform decision (overlay, `mmap_init`): in Orbis it is not reserved `0x7ffffe000000-0x7fffffff0000`. Marker: `PWBOOT top_area_not_reserved`.
  - Wine use its other reserved areas (`0x10000-0x68000000` and `0x7f000000-0x7fff0000`).
  - If there is no room, use the free assignment (`anon_mmap_alloc`).
- `/data/pkg/orbis-win-W021-36fd58d86be9.pkg` (APP_VER 01.20), uploaded and verified. The PKG of W020 was deleted.
- Program: `gui-window64.exe` without `WINEDEBUG`.
- Result (`reports/wine-hardware-w021/physical/20261031T220443Z/`): **crashed**, later than before.
  - `top_area_not_reserved`. No low area serves Win64, so there is `virtual_heap_fallback_alloc` and the heap is left in `0x201000000`.
  - They arrive `virtual_ready`, the entire server, `user_shared_data_ready`, `external_prefix_ready` and `main_image_load` (base `0x140000000`).
  - The app ends without a signal before loading `ntdll.dll` PE64. In W015 that section passed.
  - In W013 the main thread pile was in `0x7ffffe1…`, inside the area that is no longer reserved.

<a id="w022-entre-la-imagen-principal-y-ntdll"></a>


## W022: between the main image and ntdll

- `/data/pkg/orbis-win-W022-9c09ac85d911.pkg` (APP_VER 01.21), uploaded and verified. The PKG of W021 was deleted.
- Markers `PWBOOT main_step`:
  - `load_order_ready`;
  - `thread_stack base= limit=`;
  - `keyed_event_ready`;
  - `ntdll_open` and `ntdll_mapped status= module=`.
- Result (`reports/wine-hardware-w022/physical/20261031T221016Z/`): **crashed**.
  - Main root in `0x2017b8000-0x2019b0000` and created event.
  - Die within `open_builtin_pe_file` of `ntdll.dll`.
  - `ntdll.dll` has ImageBase `0x170000000` and is replaceable (DllCharacteristics 0x160). Wine places it from top to bottom from `min(user_space_limit, host_addr_space_limit) = 0x7fffffff0000`.

<a id="w023-tope-del-espacio-de-direcciones"></a>


## W023: address space cap

- Platform decision (overlay, `virtual_init`): in Orbis, `host_addr_space_limit` is cut to `0xfc00000000`.
  - According to `address_space.h` of shadPS4, the mapping area of an app of PS4 ends in `0xFBFFFFFFFF`.
  - Close to the top of `0x7fff…`, both heap (W019/W020) and `ntdll` (W022 failed, without a sign. `sceKernelVirtualQuery` responds EACCES in that area.
  - The marker `virtual_step addr_space_limit=` shows the effective value.
- It's maintained `top_area_not_reserved`.
- `/data/pkg/orbis-win-W023-7945700f76e5.pkg` (APP_VER 01.22), uploaded and verified. The PKG of W022 was deleted.
- Result (`reports/wine-hardware-w023/physical/20261031T222107Z/`): **passed**.
  - `addr_space_limit=0xfc00000000`.
  - Heap in `0x201000000`.
  - `ntdll_mapped status=40000003 module=0xfbffd10000` (STATUS_IMAGE_NOT_AT_BASE: it was relocated below the cap).
  - `result.txt` = `painted=1;pixel=8c3c14;client=464x280`, identical to Windows. Output 0.
  - The tables 3 to 5 have the same hashes as in W015 (`e0fd24a7…`, `3ac7ec09…`, `2bf05020…`). The image is identical, including the title with Marlett's glyphs.
- Second Runs (`reports/wine-hardware-w023/physical/20261031T222153Z/`, `run-0002.log`): **passed**.
  - Same `result.txt` (SHA- 256 `7a4d5541…`), and also matches the first run, archived.
  - `ntdll` was in the same direction, the picture 4 has the same hash and the output was 0.
  - Two out of two runs passed.

<a id="w024-trazas-de-fuentes"></a>


## W024: traces of sources

- `/data/pkg/orbis-win-W024-a53bf2415351.pkg` (APP_VER 01.23), uploaded and verified. The PKG of W023 was deleted.
- Just like W023, with `--winedebug=+font`, to see which source you choose win32u for the title.
- Result (`reports/wine-hardware-w024/physical/20261031T223337Z/`): **passed**, with 10.157 log lines.
  - Marlett is loaded with the OpenType parser of win32u, which opens the files by `pw_wine_*`.
  - Tahoma and Tahoma Bold have embedded bitmaps. The parser dries them to FreeType (`unsupported sfnt font: embedded bitmap data`), and FreeType fails: `Unable to load font ".../dosdevices/c:/windows/Fonts/tahoma.ttf" err = 1` (it cannot open the resource).
  - Cause: `builds/unix/ftsystem.c` opens the route with `open()` of libc. In the PS4, `dosdevices/c:` is the assembly table of `pw_wine_fs`, not a link. In the fork the link exists, and that's why it's loaded there.
  - When Marlett is left as the only family TrueType loaded, the title text is drawn with its glyphs.

<a id="w025-freetype-abre-por-la-tabla-de-montaje"></a>


## W025: FreeType opens by the assembly table

- `platform/ps4/pw_freetype_posix.h` adds `#define open(...) pw_wine_open(0, ...)`, next to the `fstat` that was already adapted.
- `libfreetype.a` now matters `pw_wine_open`. They were rebuilt FreeType and win32u (47 units, no fault) and relinked.
- `/data/pkg/orbis-win-W025-5a801f59718f.pkg` (APP_VER 01.24), uploaded and verified. The PKG of W024 was deleted.
- It keeps `+font`, to confirm that Tahoma loads.
- Result (`reports/wine-hardware-w025/physical/20261031T224137Z/`): **passed**.
  - `new_ft_face` load `tahoma.ttf` and `tahomabd.ttf`. "Tahoma" and "Tahoma Bold" are added to the Tahoma family.
  - `result.txt` identical to Windows and output 0.
  - In `frame-000014.png` the title is read "orbisdesk GUI" in Tahoma Bold, and the buttons to minimize, maximize and close are drawn with Marlett. There are 129.920 pixels of the painted color.
  - Difference with the fork: in the emulator the buttons come out as "0 1 r." Marlett is not used there, and it was not investigated.
  - The Linux matrix was not rerun with the change of the FreeType adapter.

<a id="w026-texto-con-freetype-en-la-consola"></a>


## W026: text with FreeType on the console

- `/data/pkg/orbis-win-W026-08995198fd87.pkg` (APP_VER 01.25), uploaded and verified. The PKG of W025 was deleted.
- Program: `C:\orbis\gui-text64.exe`, the increment fixture 25, without `WINEDEBUG`.
  - Tahoma load from memory and check family, metrics and glyphs indices.
  - Draw with `TextOutW` on a DIB and on the window, with numbers, accents, and pees.
  - Escribe `text-result.txt`.
- The launcher archives the previous `text-result.txt` (macro `HW_RESULT`).
- `fetch-hardware.py` use `result_name` and `expected_prefix` of the manifest.
  - As in the increment 25, `passed=1;family_tahoma=1;` and output 0 is required.
  - The ink of FreeType does not have to match that of Windows (1.397 pixels).
- Result (`reports/wine-hardware-w026/physical/20261031T224623Z/`): **passed**, a Runs.
  - `text-result.txt`: `passed=1;family_tahoma=1;painted=1;width=299;height=24;metric_height=24;ink=1252;window_ink=1252`.
  - The ink is the same as in the fork: 1.252 order them in the DIB and in the window. Windows: width 298 and 1.397 pixels.
  - Output 0.
  - In `frame-000004.png` read "Wine PS4: text 0123456789 aÃ." The title "Wine PS4 - text" is in Tahoma Bold and the buttons, in Marlett.

<a id="w027-explorer-y-evidencia-más-liviana"></a>


## W027: scout and lighter evidence

- `/data/pkg/orbis-win-W027-7523a490fbed.pkg` (APP_VER 01.26), uploaded and verified. The PKG of W026 was deleted.
- Program: `C:\windows\explorer.exe /desktop=shell,800x600`, the case of an increment explorer 25, with the taskbar and the Start button.
  - There is no input source: the Start menu cannot be opened.
  - Explorer doesn't end up alone. `fetch-hardware.py` classifies it as `presented` if there are pictures of 800 × 600 and no crash record (`runs_until_closed`). He never classifies it as `passed`.
- Speed:
  - Without `fsync` per line in `note`, `sceKernelDebugOutText` or the output of Wine. The writing with `write()` is already in the kernel and survives the process. Only the output, crash and closing records continue to do `fsync`.
  - The hardware sink is compiled with `PW_SINK_MAX_DUMPS=8`; the fork is still in 24.
  - With `PW_SINK_TIMING=1`, the tables record `t_ms`, the process time.
  - `calling_wine_boot_main` and `process_exit` also record `t_ms`.
- Result (`reports/wine-hardware-w027/physical/20261031T225306Z/`): **presented**.
  - The log has 506 lines.
  - Process times: the launcher panel appears at 1,36 s and Wine starts at 1,56. The first table on the desktop reaches 4,42 s, and the Start button at 5,02 s (table 5).
  - `frame-000005.png` shows the desktop 800 × 600 with the taskbar and the "Start" button with the Wine icon. A simple view is equal to `reports/increment25-accepted/explorer.png` of the fork.
  - Three `err:ole` appear (`StdMarshalImpl_MarshalInterface`, `CoMarshalInterface`, `apartment_get_local_server_stream`, hr 0x80004002). They weren't investigated.
  - There's no crash record. The app was closed by the user.
  - There are no times of W026 to compare the gain from removing `fsync` and prep braindumps.

<a id="w028-control-y-escritorio-de-1280720"></a>


## W028: control and desktop of 1280 × 720

- `/data/pkg/orbis-win-W028-94ba49ee0bfa.pkg` (APP_VER 01.27), uploaded and verified. The PKG of W027 was deleted.
  - Two runtime files were reuploaded whose hash did not match the console. They're probably the record, which Wine rewrites on the way out. They're just like in the staging.
- Desktop: `explorer.exe /desktop=shell,1280x720` and `WINE_PS5_DESKTOP=1280x720` (variable that I already read `ps5drv.c`). It occupies the entire unscaled video output.
- Input (`native/hw_pad.c`, for hardware only):
  - Initialization: `sceUserServiceInitialize`, `sceUserServiceGetInitialUser`, `scePadInit` and `scePadOpen`.
  - A thread reads the control with `scePadReadState` each 16 ms.
  - Mapeo:

    | Control | Wine |
    |---|---|
    |Left stick|Point movement, with quadratic response and dead area of 24|
    |X|Left button|
    |Circle|Right button|
    | Cruceta | Flechas |
    |Triangle| Enter |
    |Square|Esc|
    | Options |Keyboard Windows|

  - The events reach `ps5drv.c` by `pw_wine_next_input`.
  - Wine wakes up by `socketpair` (`pw_wine_input_fd`).
    - The reading end has `SO_RCVTIMEO` of 1 ms, because sockets cannot become non-blocking (W013). So ends the loop of `read()` with which the driver empties the socket.
    - If `setsockopt` fails, there is no wake-up descriptor and it is recorded.
  - Markers: `pad_open`, `pad_wake`, `pad_thread` and up to 32 `pad_event`.
- pointer:
  - `ps5drv.c` does not draw cursor. The hardware sink (`PW_SINK_EXTERNAL_INPUT`) draws an arrow of 11 × 17 over the last picture.
  - When the pointer moves, the sink shows that picture again.
  - The fork compiles the sink without that option and retains the stub input.
- Result (`reports/wine-hardware-w028/physical/20261031T230639Z/`, second download): **presented**.
  - `pad_open` gave a valid handle and worked `pad_wake` (`rcvtimeo=0`) and `pad_thread rc=0`.
  - A click with X (`type=3 code=0 down=1/0`) was recorded in `640,360`, the center. The pointer never moved from the center.
  - The first download (`20261031T230607Z`) was made with the app still running, without events. `fetch-hardware.py` marked it as `crashed` because it expected pictures of 800 × 600. Now accept any picture after `calling_wine_boot_main`.
- W029 (`orbisdesk-W029-6b98c73025dd.pkg`): added the raw reading of the control. It was replaced by W030 before running.

<a id="w030-control-mouse-y-teclado-usb"></a>


## W030: control, mouse and USB keyboard

- `/data/pkg/orbis-win-W030-b8caa8d188c8.pkg` (APP_VER 01.29), uploaded and verified. The PKG of W029 was deleted.
- `native/hw_pad.c` read three sources every 16 ms:
  - **Control**: just like W028, without requiring `data.connected`. Record raw reading (`pad_read`: rc, buttons, sticks and the first 16 bytes) in the first five readings and then every ~ 2 s for one minute.
  - **USB Mouse**: `sceMouseInit`, `sceMouseOpen` in combination mode and `sceMouseRead`, with the shadPS4 mouse module structure. The relative movement moves the same pointer. Left, right, and middle buttons.
  - **USB keyboard**: `sceKeyboardInit`, `sceKeyboardOpen` and `sceKeyboardReadState`.
    - HID USB codes are translated into virtual keys: letters, numbers, signs, F1-F12, navigation, Enter, Esc, Backspace, Tab and Caps Lock.
    - The modifiers are interpreted as the byte of HID modifiers (Ctrl, Shift, Alt, Windows). It's not checked on the console.
- Mouse and keyboard are not imported into the ELF:
  - They are charged in execution time with `sceSysmoduleLoadModule(MOUSE)` / `sceSysmoduleLoadModuleInternal(INTERNAL_KEYBOARD)` and `sceKernelLoadStartModule`, in `/system/common/lib` or `/system/priv/lib`.
  - The functions are solved with `sceKernelDlsym`.
  - If anything is missing, the app starts the same with the control.
  - Markers: `input_module`, `input_symbol`, `mouse_open`, `keyboard_open`, `input_wake`, `input_thread` and up to 48 `input_event source=pad|mouse|keyboard`.
- Result (`reports/wine-hardware-w030/physical/20261031T231623Z/`): **presented**, no input.
  - According to the user, the pointer did not move either with the control, with the mouse, or with the keyboard.
  - Control: `scePadReadState` gave `rc=0` and `connected=1` for one minute, and the quaternion changes in each reading. But the buttons were always `0` and the sticks `128,128`, and there was no `input_event`.
  - Mouse: `sceSysmoduleLoadModule(MOUSE)=0` From `/system/common/lib` and `/system/priv/lib`, `sceKernelLoadStartModule` gives `0x80020002` (does not exist), and no symbol was resolved.
  - Keyboard: `sceSysmoduleLoadModuleInternal(INTERNAL_KEYBOARD)=0x805a1000` and the same non-existent route.

<a id="w031-separar-el-control-de-los-módulos-usb"></a>


## W031: separate control from USB modules

- `/data/pkg/orbis-win-W031-b2787855f51e.pkg` (APP_VER 01.30), uploaded and verified. The PKG of W030 was deleted.
- The first 20 s (1.250 readings) only the control is read. Then it is recorded `input_usb_open_after_pad_only` and the mouse and keyboard are opened.
  - In W028, without USB modules, it did reach a click with X.
- The control records the first three readings and then each change of buttons or stick area, up to 64. One sample is no longer taken every 2.
- Routes of modules:
  - first `/<sceKernelGetFsSandboxRandomWord>/common/lib/` and `.../priv/lib/`;
  - then `/system/common/lib/`.
- Keyboard: first the public sysmodule `KEYBOARD` (0x0106), then the internal.
- Result (`reports/wine-hardware-w031/physical/20261031T232719Z/`, two runs): **presented**, with partial input.
  - Control buttons: X, Circle, Triangle and Square (`buttons=0x4000`, `0x2000`, `0x1000`, `0x8000` arrive, and generate `input_event`. The sticks are worth `128,128` in all readings.
  - Mouse: `/bnvpCiZOba/common/lib/libSceMouse.sprx` load (module 0x91) and `sceMouseOpen` gives a handle. The pointer moves and there are clicks in `31,711`, on the Start button.
  - Keyboard: the public symmodule `KEYBOARD` load (module 0x93) and `sceKeyboardOpen` gives a handle. Keys arrive (`code=72`, `66`, `74`,...).
  - According to the user, the pointer moves but the clicks and keys have no effect. There are no new pictures after the desktop: only 4 catches, and the sink keeps up to 8 different.
  - The events enter the tail of `hw_pad.c`, but win32u does not respond. It remains to be known if `ps5drv.c` it takes them out of the tail.
- The loading of the mouse and the keyboard did not affect the control: the buttons were already working before the 20 s and followed.

<a id="w032-win32u-saca-los-eventos"></a>


## W032: win32u takes out the events?

- `/data/pkg/orbis-win-W032-66d4e9b1ba06.pkg` (APP_VER 01.31), uploaded and verified. The PKG of W031 was deleted.
- `pw_wine_next_input` records:
  - `input_taken` (up to 32), with the remaining call number, event and tail;
  - `input_poll calls= taken=` in the first four calls and then every 2.000.
- With each change of control is added `scePadRead` (`pad_read_buffered`), to compare the sticks with those of `scePadReadState`.
- Result (`reports/wine-hardware-w032/physical/20261031T233207Z/`): **presented**.
  - The control events, the mouse and the keyboard enter the tail.
  - **Zero** calls to `pw_wine_next_input`: no `input_poll` or `input_taken` appears.
  - `scePadRead` returns 0 samples (`pad_read_buffered rc=0`), so it's no use to compare the sticks.
  - Causa:
    - win32u only calls `ProcessEvents` when the server marks the tail with `QS_DRIVER`.
    - It marks it when the descriptor registered with `set_queue_fd` has data.
    - That handler does `dup(unix_fd)`. With a socket, `pw_wine_dup` returned the real EPERM, because a socket has no route to reopen.
    - `queue->fd` was never created and `register_input_fd` ignores the error.

<a id="w033-dup-real-por-scm_rights"></a>


## W033: `dup` real by SCM_RIGHTS

- Platform decision (`pw_wine_fs.c`):
  - Before EPERM, `pw_wine_dup` send the descriptor to a private socketpair with SCM_RIGHTS and use the one you receive.
  - The new one shares the file description (offset and state flags), as a real `dup`, and also serves sockets.
  - The reopening by route of W011 remains as a backup.
  - Marker: `PWBOOT dup_eperm_scm_rights`.
- `/data/pkg/orbis-win-W033-a9f704fa8753.pkg` (APP_VER 01.32), uploaded and verified. The PKG of W032 was deleted.
- Result (`reports/wine-hardware-w033/physical/20261031T233904Z/`): **presented**.
  - It appears `dup_eperm_scm_rights`, in the first EPERM (the mapping of NLS).
  - There are 48 events, including mouse clicks in `30,713`, on Start.
  - There's still no call to `pw_wine_next_input`.

<a id="w034-cada-eslabón-del-despertar"></a>


## W034: each link of the awakening

- New markers, to see where the chain is cut:
  - win32u `register_input_fd`: `input_fd_register fd= to_handle=` and `input_fd_set_queue status=`.
  - Server `set_queue_fd`: `queue_fd source= dup= errno= fd_object=`.
  - Server `msg_queue_poll_event`: `queue_fd_event event=` (up to 16).
  - `pw_wine_poll`: `poll_unsupported fd= events= net_errno= stat= mode=` when a descriptor cannot be recorded in `sceNetEpoll` and the entire call fails.
- The Unix part, the server and win32u (47 units, no fault) were reconstructed and relinked.
- `/data/pkg/orbis-win-W034-2729a8022cc5.pkg` (APP_VER 01.33), uploaded and verified. The PKG of W033 was deleted.
- Result (`reports/wine-hardware-w034/physical/20261101T001107Z/`): **presented**.
  - Correct record on the three scout threads: `to_handle=0`, `queue_fd dup=69/70/91 fd_object=1` and `set_queue status=0`.
  - There are three `queue_fd_event event=1`, so the server does detect the socket with data.
  - Then they appear `poll_unsupported fd=69 events=0 net_errno=22 mode=140666` (socket) in each turn.
    - After the notice, the server leaves that fd without events (`set_fd_events(fd, 0)`).
    - `sceNetEpollControl` rejects an empty mask and `pw_wine_poll` makes the entire call fail.
    - The server loop was stuck from the first event.

<a id="w035-poll-con-descriptores-sin-eventos"></a>


## W035: `poll` with no event descriptors

- Platform decision (`pw_wine_poll`): an entry with `events=0` is recorded by asking for only error and closure (8 ¥124; 16), which is the only thing `poll()` I'd report to her.
  - If `sceNetEpoll` does not accept it either, the input is omitted (marker `PWBOOT poll_idle_fd_skipped`) rather than failed with all the descriptors.
- `/data/pkg/orbis-win-W035-cff2e75119ca.pkg` (APP_VER 01.34), uploaded and verified. The PKG of W034 was deleted.
- Result (`reports/wine-hardware-w035/physical/20261101T001652Z/`): **presented**. **The Start menu opens with the console input.**
  - He's gone. `poll_unsupported`. The `queue_fd_event`, And now win32u Take out the events: `input_taken` with clicks (`type=3`) and movement (`type=2`), No tail to be reached (`queued=0`).
  - There are new catches after the desk (tables 6, 8, 9 and 10). In `frame-000009.png`, the Start menu is open over the 1280 × 720 bar, with "Run..." and "Exit desktop."
  - The desk occupies the 1280 × 720 of the output.
  - The catches do not include the pointer, because the sink draws it only in the video buffer.
  - Sticks: The control change log only showed `128,128`, but the user confirmed that the left stick moves the pointer. The recorded readings coincided with still stick moments. The right stick is not assigned.
  - `scePadRead` does not return samples. It's only used `scePadReadState`.

<a id="w036-y-w037-sin-espera-inicial-touchpad-y-exit-desktop"></a>


## W036 and W037: without initial waiting, touchpad and "Exit desktop"

- W036 (`orbisdesk-W036-9e21a3647c8e.pkg`, APP_VER 01.35): the mouse and keyboard are opened at the first reading of the input, without the 20 s of W031. It was replaced by W037 without running it.
- W037 (`/data/pkg/orbis-win-W037-c08dff44cd23.pkg`, APP_VER 01.36), uploaded and verified. The PKG of W036 was deleted.
  - **Touchpad**: the first finger moves the pointer relative (× 0,75 per unit). Tear the touchpad (`ORBIS_PAD_BUTTON_TOUCH_PAD`) is the left button.
  - **"Exit desktop"**:
    - Request confirmation and call `ExitWindows`. In user32, that throws `wineboot.exe --end-session --shutdown` as a new process, which cannot exist in a title of PS4.
    - Platform decision (overlay, `NtCreateUserProcess`): in Orbis, if the command line contains `wineboot.exe` and `--shutdown`, it is recorded `PWBOOT session_end_terminates_title` and it's called `NtTerminateProcess(NtCurrentProcess(), 0)`.
    - The closure continues through the normal process output and `sceSystemServiceLoadExec("exit")` of W014.
- Result (`reports/wine-hardware-w037/physical/20261101T002808Z/`): **presented**, with output 0.
  - The control, mouse and keyboard are opened at the start, without waiting.
  - It appears `PWBOOT session_end_terminates_title`, and then `process_exit method=_exit status=0 t_ms=28869`. Exit desktop closes the title.
  - The 8 catches were exhausted before the menu and the confirmation dialog were opened, so they were not saved.
  - The log does not distinguish a click of the touchpad from one with X (both are `source=pad code=0`). The user confirmed that the touchpad moves the pointer and click.

<a id="matriz-linux-con-los-cambios-de-w011w037"></a>


## Matrix Linux with changes of W011 - W037

- `reports/wine-hardware-w037/regressions-25/`: he did not run the cases of Wine.
  - It was cut into a prior verification: `Baseline runs do not match the current out/eboot.bin`.
  - `--reuse-platform reports/increment25/regressions24` points to native crazies of a `out/eboot.bin` previous (`476105bf…`). The current one is `89d8ff99…`.
- `reports/wine-hardware-w037/regressions-25b/`, which reuses the natives of `reports/wine-hardware-w011/regressions-25b/regressions24`, which do match:
  - The 18 increment suite passed (PE, IPC, pipes, files, metadata, threads).
  - **Return** in the increment 24: `gui-window64` in the fork is hung after `dispatcher_slot_ready`, No pictures (95 s timeout).
    - The emulator fails in `GpuComm` with `vk_platform.h:66 Check ... ErrorOutOfDeviceMemory` (`reports/linux-wine-runs/20261101T004441626881Z/`).
    - With the top of W023, `ntdll` was left at `0xfbffd10000`, just below the end of the user area of shadPS4.

<a id="w038-tope-más-bajo-rueda-clic-derecho-con-dos-dedos-y-launchtxt"></a>


## W038: lower top, wheel, right click with two fingers and `launch.txt`

- Memory cap: `host_addr_space_limit` is cut to `0x7ffff0000`, the end of the range administered by the kernel (`SYSTEM_MANAGED_MAX` + 1 of shadPS4, rounded to 64 KiB). The heap and the batteries were already falling on the console.
  - Isolated run of `gui-window64` in the fork with that top (`reports/linux-wine-runs/20261101T010323961339Z/`): **passed**, with the same result as Windows and 129.920 painted pixels.
  - Matrix complete with ELF of W038 (`reports/wine-hardware-w038/regressions-25/`: **passed**, No flaw.
    - The three text runs pass, explore, the suite of the increment 24 and the
      18.

    - The native crazies of `reports/wine-hardware-w011/regressions-25b/regressions24` (same `out/eboot.bin`) are reused.
- Wheel:
  - `ps5drv.c` accepts a type event 4 (delta in `y`, in units of 120) and sends it as `MOUSEEVENTF_WHEEL`.
  - The right stick generates a notch for each 120 accumulated units (tilting up).
  - The USB mouse wheel generates 120 per unit. The sign of the device is not checked.
- Touchpad: clamping with two fingers is the right button. A two-finger touch of less than 300 ms, which moves less than 40 units and without tightening, is a right click.
- `/data/orbis-win/launch.txt`: the first line is the Windows route of the EXE and each next line, an argument (up to 6). Without the file, the scout desktop is opened to 1280 × 720. Markers: `launch_file lines=` and `launch_arg`.
- Context: the Wine desktop has no contextual menu. Your window only serves double click, so the right click on the empty desktop opens nothing, unlike Windows.
- `/data/pkg/orbis-win-W038-3d8eac4c505d.pkg` (APP_VER 01.37), uploaded and verified. The PKG of W037 was deleted.

<a id="w039-menos-diagnóstico-de-entrada"></a>


## W039: less input diagnosis

- Prepared before testing W038, at the user's request: always one iteration ahead.
- The raw readings are removed from the control (`pad_read`, `pad_read_buffered`) and the counters `input_poll` and `input_taken`.
- There are:
  - `pad_read_failed`, each ~ 10 s, only if the reading fails;
  - `input_first_request`, the first time win32u requests events;
  - the openings (`pad_open`, `mouse_open`, `keyboard_open`);
  - the first 48 `input_event`.
- The rest is the same as W038.
- `/data/pkg/orbis-win-W039-e98d98394e37.pkg` (APP_VER 01.38), uploaded and verified. The PKG of W038 is preserved and not yet tested.

<a id="w038-en-la-consola"></a>


## W038 on the console

- Cumed in `reports/wine-hardware-w038/physical/20261101T041248Z/`, classified `presented`.
- Memoria:
  - `addr_space_limit=0x7ffff0000`;
  - `ntdll` was left in `0x7ffd00000`.
  - The lower cap does not break the boot on the console.
- The desktop appears at 4,3 s and the Start menu opens.
- Entry:
  - left and right click of USB mouse;
  - USB keyboard;
  - right-click the touchpad (`source=touchpad type=3 code=1`), three times.
- The wheel cannot be confirmed with this log. The 48 `input_event` were spent on clicks and keys before any `type=4` event.
- The user wrote `launch.txt` in the "Run" dialog. The log has `err:commdlg:DllMain failed to create activation context, last error 14001` and does not show any error notice. `launch.txt` is a file in `/data/orbis-win/launch.txt`, not a command: it was not on the console, so the launcher used the default arguments.
- The app didn't record an output. The user closed it from the system.

<a id="w040-presupuesto-de-log-propio-para-la-rueda"></a>


## W040: own log budget for the wheel

- The wheel has its own budget: 16 lines `input_event ... type=4`. This does not compete with the 48 clicks and keys.
- The rest is the same as W039.
- `/data/pkg/orbis-win-W040-fba6f2644021.pkg` (APP_VER 01.39), uploaded and verified. The PKG of W038 was deleted.
- `launch.txt` test:
  - It went up `/data/orbis-win/launch.txt` with the line `C:\orbis\gui-text64.exe`.
  - `/data/orbis-win` is created by the app (uid 1, mode 755) and the FTP could not write there (550). It was applied to him `SITE CHMOD 777` before it was uploaded.
  - It is expected `launch_file lines=1` and `launch_arg --wine-exe=C:\orbis\gui-text64.exe` in the log.

<a id="w040-en-la-consola"></a>


## W040 on the console

- Runs in `reports/wine-hardware-w040/physical/20261101T041853Z/`.
- `run-0001`, without `launch.txt`:
  - opens the scout desk;
  - record 48 mouse clicks and no wheel event (`type=4`), although the wheel already has its own log budget;
  - "Exit desktop" closes the app with status 0 (`session_end_terminates_title`).
- `run-0002`, with `launch.txt`:
  - `launch_file lines=1`, `launch_arg --wine-exe=C:\orbis\gui-text64.exe`;
  - `text-result.txt`: `passed=1`, `ink=1252`, as in W026;
  - the app comes out with status 0 at 6,9.
- `launch.txt` It works. After the test was deleted from the console, so the next run back to the desk.
- Wheel: unconfirmed.
- `run-0003` (`reports/wine-hardware-w040/physical/20261101T042159Z/`):
  - the USB mouse wheel reaches Wine: 16 events `source=mouse type=4`, with `delta=120` and `delta=-120`;
  - the right stick did not generate events in this Runs and it is not known whether it was used;
  - on the scout desk there's nothing to move, so the effect is not seen. To see it, it takes a program with a list or scroll.
- Second test, in the same `run-0003` (`20261101T042354Z`):
  - there are 14 more clicks and no wheel event of the stick;
  - The 16 wheel log places were already spent by the mouse, so the log does not allow to know if the right stick generated anything.

<a id="w041-presupuesto-de-log-de-la-rueda-por-fuente"></a>


## W041: wheel log budget per source

- The wheel has 16 log lines for the mouse and 16 for the control, separately.
- The first 4 times the right stick leaves the dead area is recorded `right_stick x= y=` with raw values.
- The rest is the same as W040.
- `/data/pkg/orbis-win-W041-0737cf3db9a4.pkg` (APP_VER 01.40), uploaded and verified. The PKG of W039 was deleted.

<a id="w041-en-la-consola"></a>


## W041 on the console

- Runs in `reports/wine-hardware-w041/physical/20261101T042827Z/` and `20261101T043017Z/`.
- `run-0001` (only touchpad, the right stick was not used): 8 touchpad events and none `right_stick`.
- `run-0002` (with the right stick):
  - `right_stick` recorded raw values `x=161 y=27`, `x=202 y=0` and `x=208 y=0`;
  - There were 16 events `source=pad type=4`: 11 with `delta=120` and 5 with `delta=-120`.
- With this, the wheel is confirmed in the USB mouse (W040) and in the right stick (W041), in both ways.

<a id="w042-registro-crudo-del-stick-derecho"></a>


## W042: raw right stick record

- It records `right_stick` when either of the two axes leaves the dead area (up to 8 times), along with the first 16 bytes of the control report.
- It was armed when it seemed that the stick didn't answer. W041 `run-0002` showed after that he did respond, so you don't need to try this version.
- `/data/pkg/orbis-win-W042-7ca3e3cce197.pkg` (APP_VER 01.41), uploaded and verified. The PKG of W040 was deleted.

<a id="w043-compositor-por-orden-de-ventanas-presentación-en-un-hilo-y-programas-de-wine"></a>


## W043: composer in order of windows, presentation in a thread and programs of Wine

- Problem reported: When moving windows the video is stuck, everything is redrawn (including the taskbar) and black parts remain.
- Causes in `ps5drv.c` and in the sink:
  - Each flush was copied directly to the screen, regardless of which window is above.
  - By moving or hiding a window, his old rectangle was erased to black, and what was discovered was not repainted.
  - Each flush, however small, made on the thread of Wine a hash byte to byte of the whole picture (3,6 MB), a erasing and a climbing with a division per pixel, and a flip.
- Changes in `ps5drv.c` (revisions of `tools/build-win32u-ps4.py`):
  - Each window keeps a copy of its latest content.
  - The screen is reinstated from the bottom up with those copies, in the order of stacking. The order comes out of `insert_after` and `SWP_NOZORDER`, and the windows `WS_EX_TOPMOST` are on top.
  - Move, hide, reorder or destroy a window reproduces only the affected rectangles, without asking for repainting.
- Sink changes (`PW_SINK_ASYNC`, hardware only):
  - The thread of Wine only marks the picture as a slope; a presenter thread copies it and does the flip, at most every 16 ms.
  - Direct copy when the desktop measures 1280 × 720.
  - The hash is calculated only for the tables that are recorded or can be flushed.
- Programs: `tools/stage-wine-programs.py` copy `notepad`, `regedit`, `cmd`, `winefile`, `taskmgr` and `winemine`, compiled as PE64 in the tree of Wine fixed, to `system32` and the library directory. They don't need any new DLL.
- Launch programs from Run or Start:
  - The code is already in the launcher (`pw_hw_switch_program`, `next.txt`), but the revision of `process.c` that invokes it remains for W044.
  - It was left out because the Linux matrix ran at the same time with the current ELF, and that review modifies it.
- `/data/pkg/orbis-win-W043-0d60b63dcd3d.pkg` (APP_VER 01.42), uploaded and verified. The PKG of W041 and W042 were deleted.

<a id="w043-en-la-consola"></a>


## W043 on the console

- Cumed in `reports/wine-hardware-w043/physical/20261101T045251Z/`, classified `presented`, with output 0 by "Exit desktop."
- `presenter_thread started`, without `video_out_flip_failed`. The desk appears at 4,2.
- The user moved Run's window and confirmed that everything is no longer redrawn and that there are no black parts left.
- Matrix Linux with the composer of W043 (`reports/wine-hardware-w043/regressions-25/`: **passed**.

<a id="w044-abrir-programas-fondo-ícono-de-start-íconos-de-menú-y-reloj"></a>


## W044: open programs, background, Start icon, menu icons and watch

- Open programs from Run or Start:
  - `NtCreateUserProcess` (revision of `process.c` in `tools/prepare-wine-boot.py`) records `PWBOOT create_process image= helper=`.
  - Except for the auxiliary processes of Wine (`wineboot`, `services`, `rpcss`, `svchost`, `plugplay`, `winedevice`, `conhost`, `winemenubuilder`, call `pw_hw_switch_program`.
  - The launcher writes `/data/orbis-win/next.txt` (the EXE in the first line and the arguments in the following) and reacts with `sceSystemServiceLoadExec("/app0/eboot.bin")`.
  - When starting, `next.txt` has priority over `launch.txt`, it is read only once and erased. When the program is over, the app reels again and returns to the desktop.
  - It is not yet known whether a title can be relaunched like this: the log will show `switch_program load_exec rc=`.
  - Outside the hardware, `platform/ps4/pw_wine_platform.c` defines a weak version that records `switch_program unavailable` and returns error.
  - A weak undefined reference cannot be used: `create-fself` rejects it ("missing library for symbol").
- Explorer hardware (`tools/build-explorer-hw.py`, 11 revisions in overlay, with the same compilation commands as the fixed build). Only the PS4 package is used: the Linux runner continues to use the set explorer.
  - The Start button shows a separate four-panel window icon instead of that of the class.
  - Run and Exit show drawn icons (a window and a ignition symbol).
  - There is a clock (`GetTimeFormatW`, each 1 s) at the right end of the bar, with the notification icons on your left.
- Local time: the launcher reads `TIME_ZONE` and `SUMMERTIME` of the console and passes to Wine `TZ=LCL±H:MM` (marker `time_zone`).
- Wallpaper: `tools/make-wallpaper.py` generates in a determinist way `orbis-hills.bmp` (sky, clouds and hills, without third-party material). It is configured with `Wallpaper` in `user.reg`.
- `DragFullWindows` passes to `1`: dragging a window moves it whole, instead of drawing only the contour.
- `/data/pkg/orbis-win-W044-7710134fab9f.pkg` (APP_VER 01.43), uploaded and verified. The PKG of W043 was deleted.
- pending for W045: folders in the Start menu with new programs and their icons.

<a id="w044-en-la-consola"></a>


## W044 on the console

- Runs in `reports/wine-hardware-w044/physical/20261101T051446Z/` (`run-0001` to `run-0012`).
- According to the user: Start icon, Run and Exit icons, clock and drag of the entire window. The clock takes the console area (`time_zone minutes=-180 summer=0`).
- The 6 programs are opened from Run. Each one leaves `create_process`, `switch_program`, and in the next run `switched_program` with the EXE: `notepad`, `regedit`, `cmd`, `winefile`, `winemine` and `taskmgr`.
- The background is not seen: the desk is still black.
  - Cause: `get_win_ptr` returns `WND_DESKTOP` for the desktop window, so it never has a surface and what you explore paints there doesn't get to the screen.
- When it closed `taskmgr`, the app was half-closed: it did not start a new Runs and the system menu could not close it.
  - The log ends at `process_exit method=_exit status=0`.
  - In no run was the marker of the return to the desk, which was requested from `_exit`.

<a id="w045-fondo-desde-el-driver-tema-oscuro-carpetas-del-menú-start-y-vuelta-al-escritorio"></a>


## W045: background from driver, dark theme, Start menu folders and back to desktop

- Background: `ps5drv.c` load the BMP indicated by `WINE_PS5_WALLPAPER`, that the launcher passes with the route of `orbis-hills.bmp`. He scale it to the screen and uses it as a layer from below the composer rather than from the black one.
  - Markers: `wallpaper_loaded` or `wallpaper_failed`.
  - Without the variable, as in the runner Linux, the background remains black.
- Dark theme: the system colors are filled in `[Control Panel\Colors]` of `user.reg`, which was empty. The background is dark (buttons and bar 45,45,48; 38,38,40 menus; windows 30,30,30), with text 235,235,235 and blue selection 0,120,215 with white text.
  - The edge of the Run icon passes to light grey to be seen on a dark menu.
- Start Menu: `tools/make-start-menu.py` generates 8 direct access `.lnk` (Shell Link with LinkInfo, description and icon of EXE itself) in `C:\ProgramData\Microsoft\Windows\Start Menu`:
  - `Programs/Accessories`: Notepad, Command Prompt, File Manager;
  - `Programs/Games`: Minesweeper;
  - `System Tools`: Command Prompt, File Manager, Registry Editor, Task Manager.
- Back to the desk: you are asked from `exit()`, before the drivers `atexit`, and once. The `return_to_desktop` marker is written before the order.
- `/data/pkg/orbis-win-W045-c2899ac36e20.pkg` (APP_VER 01.44), uploaded and verified. The PKG of W044 was deleted.

<a id="w045-a-w047-en-la-consola-y-la-hora"></a>


## W045 to W047 on the console, and the time

- W045 (`reports/wine-hardware-w045/physical/20261101T052806Z/`):
  - `wallpaper_loaded 1280x720 bpp=24`.
  - The Start menu continues to show only Run and Exit.
  - `cmd` is opened by the program change, but it has no window. It is a console program, and in Wine the console window gives it `conhost.exe`, another process, which the PS4 cannot launch.
  - The bar clock showed 9: 11 PM with the console in 2: 30 AM.
- W046 (`reports/wine-hardware-w046/physical/20261101T053551Z/`), menu diagnosis:
  - `SHGetSpecialFolderLocation(CSIDL_COMMON_STARTMENU)` returns `0x80070002`, and the user and the common folders are left in NULL.
  - `CSIDL_CONTROLS` returns 0, but Control Panel does not appear either.
  - The folders exist in the console (list FTP).
  - Wine runs on the console with the user `orbis`, while the prefix was armed with `jose`: `C:\users\orbis` does not exist.
- W047, first version (`reports/wine-hardware-w047/physical/`):
  - `time_source`: `sceRtcGetCurrentClockLocalTime` da 02: 36: 08 and `time(NULL)` gives 1793511368 (05: 36: 08 UTC). The libc and the area (`localtime` 02: 36: 08 are fine.
  - Clock cause: `<time.h>` of SDK brings the clock numbers of Linux, and `CLOCK_REALTIME_COARSE` (5) in the console kernel is `CLOCK_UPTIME` of FreeBSD. `NtQuerySystemTime` you prefer it if you have resolution of 1 ms, so Wine showed the time from the start.
  - Fix, for W048: `platform/ps4/pw_wine_posix.h` does `#undef CLOCK_REALTIME_COARSE`, and Wine uses `CLOCK_REALTIME` (0), which is the same number in the two systems. `CLOCK_MONOTONIC_RAW` (4), which Wine uses for your counters, is `CLOCK_MONOTONIC` of FreeBSD.
- W047, second version (`orbisdesk-W047-4a88316ed55f.pkg`): explorer adds evidence of `SHGetFolderPathW`, `GetFileAttributesW`, `FindFirstFileW` (the folder, its content and `C:\ProgramData`) and `SHParseDisplayName`. The previous PKG of W047 and W046 was deleted.
- W047, second version, on the console (`reports/wine-hardware-w047/physical/`:
  - `SHGetFolderPathW` da `C:\ProgramData\Microsoft\Windows\Start Menu` and `GetFileAttributesW` da `0x10` (directory).
  - `FindFirstFileW` over the folder and over `carpeta\*` fails with the error 50 (`ERROR_NOT_SUPPORTED`). `SHParseDisplayName` da `0x80070002`.
  - Cause: `pw_wine_fchdir` and `pw_wine_openat` look for the route of the descriptor in the table that fills `pw_wine_open`. The descriptors that arrive by SCM_RIGHTS (the handles that the wineserver in process passes to each thread, and `pw_wine_dup` from W033) do not appear, so `ENOTSUP` becomes `STATUS_NOT_SUPPORTED`.

<a id="w048-hora-listado-de-directorios-y-perfil-orbis"></a>


## W048: time, directory list and profile `orbis`

- Time: `#undef CLOCK_REALTIME_COARSE` in `pw_wine_posix.h` (see above).
- Directories: `directory_path` in `pw_wine_fs.c` first search the record with the same number of descriptor, and then any directory registered with the same device and noodle. In both cases the noodle has to match, because the number may have been reused.
- Profile: `build-wine-hardware.py` creates in `C:\users\orbis` the same folder tree as the host profile.
- The tests of the scout menu are maintained to confirm the arrangement.
- `/data/pkg/orbis-win-W048-3bf2c9ebfa16.pkg` (APP_VER 01.47), uploaded and verified. The PKG of W047 was deleted.
- Several windows: within the same program already work, for example `taskmgr` with your Run dialog. The composer stacks them. Several programmes at the same time continue to require several processes.

<a id="w048-en-la-consola-y-w049"></a>


## W048 on the console and W049

- W048 (`reports/wine-hardware-w048/physical/`):
  - `FindFirstFileW` on the Start Menu folder (`name=Start Menu`) and on its content (`first=.`) already works.
  - `FindFirstFileW(L"C:\ProgramData")` continues to fail with error 3, and `SHParseDisplayName` with `0x80070002`: it fails to search for a name at the root of the unit.
  - The ramp of the matrix with W048 was interrupted at the user's request. He's gonna run after a couple more iterations.
- W049: explore test also `CreateFileW(L"C:\\")`, `GetFileAttributesW(L"C:\\")` and `FindFirstFileW` over `C:\*`, `C:\windows`, `C:\ProgramData\Microsoft` and `Z:\*`. `/data/pkg/orbis-win-W049-190a9526311c.pkg` (APP_VER 01.48), uploaded and verified. The PKG of W048 was deleted.
- W049 on the console (`reports/wine-hardware-w049/physical/`):
  - `CreateFileW(L"C:\\")` and `GetFileAttributesW(L"C:\\")` fail with error 3, and `FindFirstFileW` fails over `C:\*`, `C:\windows` and `Z:\*`.
  - `C:\ProgramData\Microsoft` It works..
  - Cause: for the root of a unit (empty remaining name), `lookup_unix_name` test a single `fstatat(root_fd, "<prefix>/dosdevices/c:/")` and return `STATUS_OBJECT_PATH_NOT_FOUND` if it fails. `fstatat` did not pass through the platform layer, so the bic of the console did not know the assembly table. The longer routes go because they resolve component by component with functions that do pass through the layer.

<a id="w050-fstatat-por-la-capa-de-plataforma"></a>


## W050: `fstatat` by the platform layer

- `pw_wine_fstatat`:
  - the absolute routes or with `AT_FDCWD` pass through the assembly table, such as `stat`;
  - the relative are attached to the directory route (`directory_path`, W048).
  - `AT_SYMLINK_NOFOLLOW` is respected; the other flags (`AT_NO_AUTOMOUNT`) do not change anything.
- `pw_wine_posix.h` redirect `fstatat`. Wine was fully rewarded, because the header is strong in all units.
- Clock: the user confirmed that, since W048, the time of the bar coincides with that of the console.
- `/data/pkg/orbis-win-W050-9edaf00b611b.pkg` (APP_VER 01.49), uploaded and verified. The PKG of W049 was deleted.

<a id="w050-en-la-consola"></a>


## W050 on the console

- Runs in `reports/wine-hardware-w050/physical/20261101T060132Z/`.
- All the scout tests pass:
  - `C:\` is opened (`attributes=0x10`);
  - `C:\*` list (`first=orbis`), just like `C:\windows` and `Z:\*` (`first=apollo`;
  - `SHParseDisplayName` da `hr=0`;
  - the common menu folder is solved and is not empty (`empty=0`).
- `run-0001`: The Buscaminas is opened from the menu (`create_process ... winemine.exe`, `switch_program`).
- `run-0002`: The Buscaminas comes out with a state 0, it is `return_to_desktop t_ms=6409` and the app is rereleased alone.
- `run-0003`: explore again. The return to the desk from `exit()` works.

<a id="w051-sin-trazas-del-menú"></a>


## W051: no trace of the menu

- The user confirmed that in W050 the Start menu shows the folders and icons.
- W051 remove the diagnostic traces from the menu (W046 - W049.
- `/data/pkg/orbis-win-W051-1f52367bba47.pkg`, erased as you go up W052, which includes it.
- The matrix did not run: the user asked to continue with the multitasking.

<a id="w052-multitarea-experimental-programas-huéspedes-en-el-mismo-proceso"></a>


## W052: experimental multitask (guest programs in the same process)

- An app of PS4 cannot create processes. From W052, a 64 bit GUI program that opens from the desktop runs as **guest** within the process of exploring, in own threads, rather than relaunching the app.
- `tools/build-guest-hw.py` weapon, only for the package of PS4, `ntdll.dll` and `kernelbase.dll` with 13 revisions (overlay and the exact commands of the fixed build, with `make -n -W`):
  - **ntdll** (`loader.c`):
    - an EXE loaded as a module is relocated and resolves its imports when `TEB.UserReserved[2]` marks a host load (Wine, like Windows, it only does so with DLL);
    - `RtlExitUserProcess` called from a host thread ends only that host.
  - **kernelbase**:
    - `CreateProcessInternalW`: with `WINE_PS4_GUESTS` and a PE image of 64 bits with GUI subsystem, load the EXE with `LoadLibraryExW` and start its entry point into a new thread. As "process" returns handles of the process itself and of the thread; the rest follows the normal path (the relaunch of W044).
    - `GetModuleHandle(NULL)`, `GetModuleFileName(NULL)` and `GetCommandLineA/W` respond by the host when one of their threads calls them.
    - `CreateRemoteThreadEx`: The threads created by a host inherit the mark, and are kept to finish when the host leaves.
  - The mark of each thread is a pointer in `TEB.UserReserved[0..1]`, which Wine does not use; This does not require new exports.
- El launcher pasa `WINE_PS4_GUESTS=1`.
- Known limits:
  - Only 64 bit GUI programs. The consoles (`cmd`) and the 32 bits follow the relaunch.
  - The `argv` of Ukraine is that of explorer: it weapon once when you load the DLL. The `wmain` of Wine for GUI programs uses `GetCommandLineW`, which is the guest's.
  - `exit()` of a guest runs the `atexit` table of the process, shared with explorer.
- Markers: `PS4 guest <exe> module <p> entry <p> thread <tid>`, `PS4 guest module <p> exits status <n>` and `PS4 guest ...: load failed`.
- `/data/pkg/orbis-win-W052-b59903b3fc10.pkg` (APP_VER 01.51), uploaded and verified.

<a id="w052-en-la-consola-y-w053"></a>


## W052 on the console and W053

- W052 (`reports/wine-hardware-w052/physical/20261101T061638Z/`), according to the user:
  - the Notebook opens a text-free dialogue and its window has no title;
  - while it is open, the Start menu does not respond;
  - When you close it, you close the entire app.
- The log has no marker `PS4 guest`, and everything runs in the thread `0024` of explorer (`err:msvcrt:_invalid_parameter`, `c0000417` in a callback.
- Cause: when the imports of the host EXE were resolved, `process_attach` reached `MODULE_InitDLL`, and the charger of Wine puts `EntryPoint` also for the EXE. So it was called `wmainCRTStartup` as if it were a `DllMain`, inside `LoadLibraryExW` and in the scout thread:
  - without a guest mark, `GetModuleHandle(NULL)` was an explorer, so there were no resources and the texts were missing;
  - `LoadLibraryExW` never came back, and explorer was blocked;
  - `ExitProcess` from that thread the entire process was completed.
- W053: `MODULE_InitDLL` does not call the entry point of an image without `LDR_IMAGE_IS_DLL`. The main EXE does not pass through, because it is marked as already initialized before. The returns TLS are still called.
- `/data/pkg/orbis-win-W053-b31506adcf37.pkg` (APP_VER 01.52), uploaded and verified. The PKG of W052 was deleted.

<a id="w053-en-la-consola-y-w054"></a>


## W053 on the console and W054

- W053 (`reports/wine-hardware-w053/physical/`):
  - the guests start in their own threads: `winemine` (`0038`), `taskmgr` (`003c`) and `notepad` (`004c`);
  - each one comes out alone (`PS4 guest module ... exits status 0`) and explorer keeps walking;
  - the user confirms that the Notebook and the other programs look good.
- Pending according to the user:
  - with an open guest, the Start menu does not open;
  - The host window has no button on the bar, so if it is minimized it cannot be recovered.
- Causes:
  - Start: `ps5drv.c` sent each mouse event with `hwnd` = window in foreground. With a visible window, the wineserver delivers the message to that window no matter where the pointer is, so the clicks on the bar reached the host. It was not seen before because all the windows were the same thread.
  - Bar: `add_taskbar_button` of explorer discards the windows of its own process.
- W054:
  - `ps5drv.c` commands the movements, buttons and wheel of the mouse without a window, and the server looks for the window under the pointer, like winex11. The keyboard is still going to the window in the foreground.
  - The hardware explorer accepts on the bar the guest thread windows: read `TEB.UserReserved` from the thread with `NtQueryInformationThread(ThreadBasicInformation)`.
- `/data/pkg/orbis-win-W054-633cbed438f5.pkg` (APP_VER 01.53), uploaded and verified. The PKG of W053 was deleted.

<a id="w054-en-la-consola-y-w055"></a>


## W054 on the console and W055

- W054: the user reports that the Start menu never opens.
- Cause: with `hwnd` 0, `get_hardware_input_desktop` use the display station desk visible (`WSF_VISIBLE`), which this title does not have, and the server discards the event without error. No click reached any window.
- W055: Each mouse event carries the first-level window below the pointer, according to the composer's stack (`window_at`), or the desktop window if there is none. winex11 does the same with window X under the pointer, and win32u then looks for the child. The capture of the mouse (open menus) is still solved by the server. The keyboard goes to the window in the foreground.
- `/data/pkg/orbis-win-W055-3c82aee64ffb.pkg` (APP_VER 01.54), uploaded and verified. The PKG of W054 was deleted.

<a id="w055-en-la-consola-y-w056"></a>


## W055 on the console and W056

- W055 (`reports/wine-hardware-w055/physical/20261101T064543Z/`), according to the user:
  - the Start menu, the bar buttons and the guests work;
  - `cmd` continues to relaunch (`switch_program`) and stays in "starting wine," because it is a console program and has no one to draw the console;
  - When you drag a window, it just moves when you drop.
- W056:
  - Console programs as guests: `ps4_guest_image` also accepts `IMAGE_SUBSYSTEM_WINDOWS_CUI`. If the process does not have a console (explorer does not), the launch calls `AllocConsole`. That `CreateProcessW` of `conhost.exe` (a GUI program) enters in turn as another guest and draws the console window. When the console program comes out, `FreeConsole` release the console to end the console.
  - `conhost.exe` is compiled and installed along with programs (`stage-wine-programs.py`).
  - Proof of the drag in `ps5drv.c`: `PWBOOT pointer_move` (each 50 movement of the pointer receiving Wine) and `PWBOOT window_move` (every 10 window movements the composer sees), with the thread and position.
- Limits: there is only one console per process, so two open console programs share it. A guest's `argv` profit is still the one to explore.
- `/data/pkg/orbis-win-W056-7981a9fbf155.pkg` (APP_VER 01.55), uploaded and verified. The PKG of W055 was deleted.

<a id="w056-en-la-consola-w057-w058-y-w059"></a>


## W056 on the console, W057, W058 and W059

- W056 (`reports/wine-hardware-w056/physical/`):
  - Conhost starts as a guest, but comes out with `unknown option L"/desktop=shell,1280x720"`: its `wmain` receives the `argv` to explore.
  - Drag: there are some 1.400 `pointer_move` and only some 40 `window_move` in 25 s, of the thread `0040` of the Note Block.
- W057: ucrtbase (`dlls/msvcrt/data.c`, in `build-guest-hw.py`) returns in `__p___argc`, `__p___argv` and `__p___wargv`, for each host thread, the arguments armed with `GetCommandLineW` of the host, once per host. Measurements `window_move t_us` and `flush_stats` are added. Explorer (17 revisions) takes the icon of each menu input with its complete route (`SHGDN_FORPARSING`), because `SHGetFileInfo` with a pidl relative to the folder did not give icon, and adds a back with `IShellLink` and `ExtractIconEx`.
- W057 on the console (`reports/wine-hardware-w057/physical/`):
  - all menu entries receive icon from the system list: folders 2, Command Prompt 3, Notepad 4, Minesweeper 5, Registry Editor 6, Task Manager 7;
  - `flush_stats`: average of 5 ms and maximum of 125 ms by flush;
  - the `window_move` arrive in bursts each ~ 15 ms, with breaks from 1 to 4 s without movement while the pointer keeps moving.
- W058: WFM, the Winlator file manager (https://github.com/brunodev85/wfm, MIT, commit `6b18608`):
  - `tools/build-wfm.py` compiles it with mingw-w64 and the flags of your Makefile;
  - the `libcdio.dll` pre-compiled repository (PE32 +, imports KERNEL32 and msvcrt; SHA- 256 `cc9b86da…`) is installed as, together with `wfm.exe`, in `system32`;
  - "File Manager 'of the WFM menu;
  - at user's request, `winefile` leaves the package and menu, and was deleted from the console.
- W059 (drag breaks hypothesis): all the threads recorded on the server copies (by SCM_RIGHTS) of the same wake-up socket. The server turns off the polling of a tail after each event until its thread waits again. If the console epoll identifies the socket and not each copy, that also silences the other threads. Now `pw_wine_input_fd` gives each thread its own pair of sockets (`input_wake n=`), and the input thread writes in all.
- `/data/pkg/orbis-win-W059-995af74c9a57.pkg` (APP_VER 01.58), which includes W058, uploaded and verified.

<a id="w059-en-la-consola-y-w060"></a>


## W059 on the console and W060

- W059 (`reports/wine-hardware-w059/physical/`), depending on the user and log:
  - WFM is the new File Manager, but if it is closed it does not open again: the following starts come out immediately with 0 status.
  - `cmd` opens a console titled "explorer.exe" that does not accept text: `cmd` comes out when you start and conhost records `read_complete failed: 0xc0000024`.
  - The drag continues with breaks from 1 to 5 s, even with a socket per thread (`input_wake n=0..5`). After each pause the window jumps away.
- Causes:
  - Drag: If the event brings a window, the server seeks capture in the input tail of the thread of that window (`queue_hardware_message`). We sent the window under the pointer, so when the pointer was ahead, the movement would reach the desk and not the thread it drags.
  - WFM: The EXE was not downloaded when it came out, so the second start found its window class and its global variables from the previous time.
  - Console: `AllocConsole` passes to conhost `--server 0x…` and then closes that handle, because a child process would have its own inherited copy. There was a closed handle.
  - Title: `AllocConsole` uses `GetModuleFileNameW(0)` the thread that calls it, which is to explore.
- W060:
  - `window_at`: if the window thread in the foreground has capture (`NtUserGetGUIThreadInfo`), the event goes to the window with capture.
  - When you leave, a guest disrecords the window classes of your module (travel the user atoms from `0xc000` to 256 followed by no use) and download the EXE with `FreeLibrary` (`PS4 guest module ... unloads, N window classes unregistered`).
  - The launch of the conhost receives a duplicate of the `--server` handle.
  - The console takes the name of the program with `SetConsoleTitleW`.
  - WFM is compiled from a copy of the sources, in which `WM_CLOSE` closes without asking for confirmation, at the user's request.
- `/data/pkg/orbis-win-W060-f0a2184ef38f.pkg` (APP_VER 01.59), uploaded and verified. The PKG of W059 was deleted.

<a id="w060-en-la-consola-y-w061"></a>


## W060 on the console and W061

- W060 (`reports/wine-hardware-w060/physical/`):
  - WFM is closed and reopened: when it comes out there are `unloads, 5 window classes unregistered` and `regedit ... unloads, 2`.
  - `cmd` accepts text: from `cmd` (thread `0048`) it was launched `regedit`. The console is called "orbis," which is well according to the user.
  - `cmd` closed does not open again (according to the user). The hypothesis is that conhost is still loaded and reused.
  - Drag: there are no longer long breaks, but the window moves once per second (`window_move` each ~ 0,8 - 1,1 s), the same period as the bar clock.
- W061: `PWBOOT input_pull` records each time a thread takes out events (the first 300): the thread, how many events and time. This is how it can be seen if the sockets of awakening awaken someone or if events wait for some thread to wake up for another reason.
- `/data/pkg/orbis-win-W061-f5c916a792c7.pkg` (APP_VER 01.60), uploaded and verified. The PKG of W060 was deleted.

<a id="w061-en-la-consola-y-w062"></a>


## W061 on the console and W062

- W061 (`reports/wine-hardware-w061/physical/`):
  - `input_pull`: the threads `002c`, `0024` and `0038` take out events every ~ 17 ms. The entry reaches Wine without delay.
  - The drag of the conhost window (`0038`) had only 3 `window_move`, separated {1 s, each 4 ms after an event taken by a scout thread.
  - Console: when you close your window, conhost comes out and is downloaded (`unloads, 7 window classes`), but `cmd` (`003c`) is still alive. The process retains the console, and the following `cmd` does not come to be launched: the scout thread that launches it is blocked, and with it the Start menu (according to the user).
- W062:
  - Console: kernelbase records the conhost (host) and the console guests. If conhost comes out, end and download to the connected programs (`ended with the console`). If the last console program comes out, it ends with conhost. In both cases the console of the process is released.
  - Proof of the drag in `defwnd.c` (loop of mover/redimensionar): `move_loop` records each message received with its point and time, and `move_loop_setpos` which takes every `SetWindowPos`.
- `/data/pkg/orbis-win-W062-458326a6da3b.pkg` (APP_VER 01.61), uploaded and verified. The PKG of W061 was deleted.

<a id="w062-en-la-consola-y-w063"></a>


## W062 on the console and W063

- W062 (`reports/wine-hardware-w062/physical/`):
  - Console: when the console window is closed, conhost ends `cmd` (`ended with the console`) and both are downloaded. The second `cmd` opens well and `exit` ends your conhost.
  - According to the user, after `exit` the console window is hung on the screen. Conhost was finished with `TerminateThread`: the server destroys its windows, but no thread of its own calls `DestroyWindow` of driver, so the composer continues to draw it.
  - Drag: each `SetWindowPos` takes less than 4 ms (`move_loop_setpos`), but the loop receives a `WM_MOUSEMOVE` and right away (< 1 ms) a `WM_LBUTTONUP`, and it ends. The `input_event` of the USB mouse always come from pairs, press and drop at the same point or at 1 px: `hw_pad.c` generates the "drop" as soon as the mouse moves.
- W063:
  - `ps5drv.c`: when you take out input events, at most every 200 ms, remove the windows that no longer exist (`is_window`), release your copy and reclaim your place (`window_gone`).
  - `hw_pad.c` (diagnosis): `mouse_sample` records raw samples of `sceMouseRead` (the first 120 reading with button or with more than one sample): order, time mark, `connected`, buttons and movement. It serves to see if the buttons come only on the change sample.
- `/data/pkg/orbis-win-W063-30ba07779313.pkg` (APP_VER 01.62), uploaded and verified. The PKG of W062 was deleted.

<a id="w063-en-la-consola-y-w064"></a>


## W063 on the console and W064

- W063 (`reports/wine-hardware-w063/physical/20261101T100505Z/`):
  - Mouse buttons: the W062 hypothesis was incorrect. `mouse_sample` shows the button in a single sample (`got=1`, `buttons=0x1`) and the drop on the next; `hw_pad.c` does not invent "drop." In the drag of this log the user kept the button between 0,7 and 1.
  - Drag: while the button is tight, the motion loop (conhost, thread `0038`) receives only `WM_TIMER` and `WM_SYSTIMER`. Its `pt`, which is the cursor of the server, is at the point where it was pressed. When you drop a `WM_MOUSEMOVE` and the `WM_LBUTTONUP`, and the window jumps once. The driver does send the movements (`pointer_move` to 676,68 during the drag). The case is not identified.
  - `exit` in `cmd`: the app was closed. The log ends in `ps4_guest_end ... ended with the console`, without the following `unloads`. `TerminateThread` over the conhost thread, which was running, causes the server to send SIGQUIT with `tkill`. In the PS4 there is no `tkill` or `thr_kill2` (`HAVE_THR_KILL2` is not defined), and `send_thread_signal` use `kill()` on the process, that is, the title above all. In W062 it didn't happen because conhost was waiting on the server, and in that case no signal is sent.
  - `window_gone` does not appear: the app was closed before.
- W064:
  - `server/ptrace.c` (`prepare-wine-boot.py`): in the PS4, `send_thread_signal` no longer sends the signal to the process. It records `thread_signal unavailable thread= sig=` and returns error. A finished thread while running ends in its next call to the server, when it finds its channel closed. The suspension of threads (SIGUSR1) and Ctrl + C of the console also depend on this, and now fail with the trace rather than pointing to any thread.
  - `ps4_guest_end` (kernelbase): first he sends `WM_QUIT` to the guest's threads and waits until 2 s without having taken the guest's lock. Conhost comes out of his loop, destroys his window and goes through `ps4_guest_exit_process`, which downloads it. Only the threads that do not come out are finished with `TerminateThread`. `cmd` has no message queue and ends as before. Threshold: `asked to quit, wait`.
  - `ps5drv.c` (diagnosis): `held_move` records, for the first 150 movements with the left button tight, the destination window, the foreground window, its capture and its lags, the result of the shipment and the server cursor just after.

<a id="w064-en-la-consola-y-w065"></a>


## W064 on the console and W065

- W064 in PS4 (`reports/wine-hardware-w064/physical/20261101T143013Z/run-0001.log`):
  - `exit` in `cmd` closes the console and the app is still open. The two times it was tested, the log shows `1 of 1 threads asked to quit, wait 0`: conhost came out of his loop, was downloaded (`unloads, 6 window classes unregistered`) and no thread had to be finished. It does not appear `thread_signal unavailable`.
  - Drag: `held_move` recorded 38 movements with the button pressed. All go to the captured window (`target` and `capture` equal, `gui_flags=3`, that is `GUI_INMOVESIZE` and capture), and the shipment returns `STATUS_SUCCESS`. Even so the motion loop receives only `WM_TIMER` with `pt` fixed, and the first `WM_MOUSEMOVE` comes with the release of the button.
  - Cause: in win32u, `NtUserSendHardwareInput` does not send the movements to the server but accumulates them by thread (`accum_mouse_motion` in `dlls/win32u/input.c`). It sends them when the target window changes or a button or wheel arrives. During the drag the window under the pointer is always the same, so all movements were held until they were released. The `error=1400` of the record is a last old error of the thread, not of the shipment.
- W065:
  - `ps5drv.c` (`build-win32u-ps4.py`): The pointer movements are sent with `MOUSEEVENTF_MOVE_NOCOALESCE`, which causes win32u to send them to the server at the time. It's one for the mouse.
  - The diagnosis `held_move` was removed.
  - It only changes win32u; the server and kernelbase are those of W064.

<a id="w065-en-la-consola-y-w066"></a>


## W065 on the console and W066

- W065 in the PS4 (`reports/wine-hardware-w065/physical/20261101T143854Z/`, three runs):
  - The drag of windows with the mouse works: the window follows the pointer.
  - When you leave from Start, a console window appears for a moment. In the three runs, the log shows the same thing when it comes out: explorer launches `conhost.exe` and then `wineboot.exe`, whose load fails (`load failed, error 1114`), and the session ends (`session_end_terminates_title`). `ExitWindowsEx` (user32) spears `wineboot.exe --end-session --shutdown` with `DETACHED_PROCESS`, i.e. without a console. The guester didn't look at those lags and create a console for every console program, so the window you see is the wineboot console.
  - Wineboot loading failure (1114, DLL initialization) was not investigated yet. It does not stop you from leaving: the session ends the same.
- W066 (`build-guest-hw.py`, kernelbase):
  - `ps4_guest_launch` receives the lags of `CreateProcess` and does not create a console when they include `DETACHED_PROCESS` or `CREATE_NO_WINDOW`.
  - If the load of a console program fails after the console is created, the console is released with `FreeConsole`, so that it does not open without a program.

<a id="w066-en-la-consola-y-w067"></a>


## W066 on the console and W067

- W066 in PS4 (`reports/wine-hardware-w066/physical/20261101T145558Z/run-0001.log`):
  - When you leave from Start you no longer throw `conhost.exe`. The only thing that is thrown is `wineboot.exe`, which continues to fail when loading (error 1114). The session ends normally.
  - `cmd` closed with the console window: Conhost ended and `cmd` ended with it.
  - File Manager (WFM) was opened twice. The first one was normally closed, but the record says `unloads, 0 window classes unregistered`. The second was immediately released (`exits status 0` in the line following the launch), and when it was downloaded it disregistered 7 classes. The same thing happened in W064. The interpretation is that the first instance was left with windows, his classes could not be unregistered, and the second was unable to register them and went out. The remaining windows would be those of the same thread that calls `ExitProcess`, which is still alive while the module is being downloaded, or those of other finished threads without waiting for them.
- W067 (`build-guest-hw.py`, kernelbase):
  - `ps4_guest_exit_process` wait until 2 s to finish the other guest threads and destroy the top level windows and the only messages windows from the coming thread, before downloading the module. Threshold: `other threads ended, windows of this thread destroyed`.
  - `ps4_guest_unload` records each class that cannot be unregistered because it still has windows (`still has windows`) and the account in `still in use`.
- W067 in PS4 (`reports/wine-hardware-w067/physical/20261101T152905Z/run-0001.log`):
  - File Manager was opened and closed four times in a row; No instance ended when it was launched. Each output destroys 2 the window of the thread that comes out and disrecords the 7 specific WFM classes.
  - `cmd` was closed three times: with `exit` (`1 of 1 threads asked to quit, wait 0`) and closing the console window. In both cases the app remained open.
  - The user confirmed that everything worked.
  - There is noise in the record: the lines `still has windows` are system classes (`Button`, `Static`, `IME`, those of comctl32) they have scout windows or other programs, not guest classes. The atom tour attempts to unregister all kinds with the `HINSTANCE` of the guest, and Wine resolves the global classes without looking at the instance. We need to check whether this route will unregister global classes from another module when they do not have windows.

## W068

- Cause of the noise of W067: in Wine, `UnregisterClass` finds a global class (`CS_GLOBALCLASS`) with any instance (`find_class` in `server/class.c` and `dlls/win32u/class.c`). The `ps4_guest_unload` route, which calls `UnregisterClass` with the guest module for each atom, also found the global classes of other modules. If they had windows, it failed (the lines `still has windows`). If they didn't, I would destroy them. In W067 the first WFM download disregistered 13 classes and the following 7, which would be the WFM's own; the other 6 would be global classes of others (their names were not registered).
- W068 (`build-guest-hw.py`, kernelbase): before unregister, `ps4_guest_unload` consult the class with `GetClassInfoExW`. A global class is registered unless its window procedure is inside the guest image, that is, the guest has recorded it. The trace sum `global kept`.
- W068 in PS4 (`reports/wine-hardware-w068/physical/20261101T155553Z/run-0001.log`):
  - They opened and closed `cmd` and WFM once each. The log ends at 29 s without `process_exit`. It is not yet known whether the app was hung or closed from the PS4 menu.
  - The filter by `CS_GLOBALCLASS` is not enough. The download of `cmd`, which does not record classes, disregistered 6, and continued to appear `Button`, `Static`, `Message` e `IME` with `still has windows`. The specific classes of user32 (`Edit`, `ListBox`, etc.) are global without having `CS_GLOBALCLASS` in style, so W068 (and before W060 - W067) destroyed those who had no windows. Since then, a program that uses these controls cannot create them. The WFM 7 `global kept` would be global classes of comctl32 (the names were not recorded).
- W069 (`build-guest-hw.py`, kernelbase): the test is the window procedure for all kinds, without looking at the style. It is unrecorded only if it is inside the guest image. If `GetClassInfoExW` returns a winproc handle (class registered as ANSI), it is reread with `GetClassInfoExA`. Threshold: `of other modules kept`.
- W069 in PS4 (`reports/wine-hardware-w069/physical/20261101T160626Z/run-0001.log`):
  - `cmd` was opened and closed twice, with `exit` (`asked to quit, wait 0`) and closing the window. WFM opened and closed twice. The exit from Start ended with `process_exit status=0` at 47,7.
  - Each download unrecords only the guest's own classes: 1 for conhost, 0 for `cmd` and 1 for WFM. Classes of other modules are recorded (11 when downloading conhost and `cmd`, 17 when downloading WFM). There was no `still has windows`.
