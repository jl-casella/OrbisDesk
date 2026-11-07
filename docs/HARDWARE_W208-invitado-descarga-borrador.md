<a id="w208-un-invitado-descarga-sus-dll-y-libera-su-memoria-al-terminar-borrador"></a>


# W208: A guest download his DLL and release his memory when he finishes (draft)

[English](HARDWARE_W208-invitado-descarga-borrador.md) | [Español](HARDWARE_W208-invitado-descarga-borrador-es.md)

Eraser of the browser side session, to join `HARDWARE_W208.md`. None of this was tested on the console.

<a id="qué-pasó-en-w207"></a>


## What happened in W207

Report: `reports/wine-hardware-w207/physical/20261104T145559Z/run-0001.log`. The user said, "it doesn't open the second time."

- **What already works:** file closing of W207. At the end it appears `PWGUEST files … closed=1` and no longer loads `Rstrtmgr.dll`.
- **The second start** (lines 2779 to 2800) ends immediately with the state 1. The next two attempts are the same.
- **The cause:** `ps4_guest_unload` only download the guest's EXE.
  - `xul.dll`, which `palemoon.exe` loads with `LoadLibrary`, and the DLL that it brings (`mozglue`, `nss3`, ...) are still loaded with their state of the first time.
  - The second start finds them already initialized: it does not appear again `Loaded … xul.dll`.
- **What was it? "23 of other modules":** refers to window classes, not to DLL.
- **The memory:** the available memory of `load_begin` low 4974739456 a 4747493376, a 227 MB for every time it opens Pale Moon. They are the blocks of the allocator of `mozglue`, that no one will release.

<a id="cambio"></a>


## Change

`tools/build-guest-hw.py`, with `guest-unload-w208.patch.py`. At the end of the guest, after his EXE:

1. **Their own modules:** those loaded since it started, outside the directory of Windows and not fixed. The ones that were on the start are recorded and recorded `PWGUEST own <nombre> base=… size=… refcount=…`.
2. **Rings in your code:** other threads of the process are sought whose direction of start, or one of its first 32 frames, is in that code. Each is recorded (`PWGUEST kept: thread … in …`). If there are any, nothing is unloaded.
3. **Window classes:** the classes whose procedure is in those modules are removed, with the same test as W068 used for EXE. If one still has windows, nothing is downloaded (`PWGUEST kept: class …`).
4. **Exceptions filter:** if you point at them, it is deleted.
5. **The download:** `LdrUnloadDll` until each module disappears, from the newest to the oldest. `DllMain(DETACH)` run as usual. It is recorded `PWGUEST unloaded … gone=1`.
6. **In ntdll (`free_modref`), for any image that is unmapped:** the vectorized handlers whose code is in it are removed and their FLS slots (`PWGUEST unmap … handlers=… fls=…` are released.
7. **Memory:** the regions your code reserved with `VirtualAlloc` (`kernelbase` `memory.c`, Annotated as the W207 files are released (`PWGUEST memory … released=… bytes=…`).

**The switch:** if there is `C:\orbis\noguestunload.txt`, everything is recorded but nothing is removed, downloaded or released. It serves to go back without a new build if the download stops the desktop.

**Not covered:**
- Timers or threat pool works that have not yet been corrected, with code in these modules;
- global hooks;
- registered COM objects.

If any of those were left, I'd fail when it's executed.

<a id="una-excepción-no-manejada-en-un-invitado-termina-sólo-el-invitado"></a>


## An exception not handled on a guest ends only the guest

**W207, second Runs** (`reports/wine-hardware-w207/physical/20261104T145950Z/run-0002.log`, lines 2353 a 2407): the user said "I opened 2da tab and sailed at YouTube and closed OrbisDesk."

- **The failure:** the same as W205 in `mozglue.dll+0x10EEA`.
- **The stack** (`PWFAULT`): `mozjs.dll` (5 and then `xul.dll`. The engine of JavaScript passed to the allocator an already released pointer.
- **What happened next:**
  1. This time no Pale Moon driver caught him: the `_XcptFilter` of `palemoon.exe` returned "keep looking."
  2. Wine tried `winedbg` ("Unhandled page fault... starting debugger").
  3. ntdll finished the whole process with `NtTerminateProcess` (`process_exit status=0xc0000005`). That call does not go through the guest's `TerminateProcess` (W196).
- **Why in W205 It didn't happen.:** in W205, a `xul.dll` He caught the same mistake and called `TerminateProcess`, So only the guest is finished..

**Change:** `tools/build-guest-hw.py` (`kernelbase` `debug.c`, `UnhandledExceptionFilter`), with `guest-unhandled-w208.patch.py`.
- First the program uses its own exception filter, as before.
- Then, instead of looking for the debugger, a guest thread ends its guest: `TerminateProcess` of the process itself, which it handles `ps4_guest_exit_process`, with the exception code as a state.
- It is recorded `PWGUEST unhandled exception … the guest ends`.
- The scout threads don't change.

<a id="construcción"></a>


## Build

1. `python3 tools/build-guest-hw.py`.
2. `tools/link-wine-boot.py`.
3. `tools/build-wine-hardware.py`.

<a id="prueba-física"></a>


## Physical test

1. Open Pale Moon (as a guest), navigate a little and close it.
2. Open it again without reboot. Repeat two or three times.
3. **What to look for in the log:**
   - `PWGUEST own_modules … count=…` and lines `PWGUEST own` (modules Pale Moon);
   - `classes=…` and `threads=0`;
   - `PWGUEST unloaded xul.dll … gone=1`;
   - `PWGUEST unmap … handlers=…`;
   - `PWGUEST memory … bytes=…`, of the order of 200 MB;
   - that the `available=` of each `load_begin` return to a value similar to the first.
4. **If the desktop is hung or failed when closing Pale Moon:** create `C:\orbis\noguestunload.txt` by FTP and repeat. The log is going to say what would have been downloaded and what prevented it.
5. **If you hang or fail within `DllMain(DETACH)`:** W209 download without `DllMain`.

<a id="no-verificado"></a>


## Not verified

- Nothing was tested on the console.
- The revisions were applied on copies of the sources, and `kernelbase` (`file.c`, `memory.c`, `process.c`) and `ntdll` (`exception.c`, `loader.c`) pass `-fsyntax-only` with mingw and the definitions of each module. The builder didn't run.
- It is not known if the `DllMain(DETACH)` of `xul.dll` and `mozglue.dll` works after their threads were finished.
