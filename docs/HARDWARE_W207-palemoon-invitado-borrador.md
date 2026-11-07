<a id="w207-pale-moon-como-invitado--archivos-al-terminar-traza-del-fallo-sin-relanzar-borrador"></a>


# W207: Pale Moon as a guest - files when finished, trace the failure, without relaunching (draft)

[English](HARDWARE_W207-palemoon-invitado-borrador.md) | [Español](HARDWARE_W207-palemoon-invitado-borrador-es.md)

Eraser of the browser side session, to join `HARDWARE_W207.md`. None of this was tested on the console.

Three changes:
1. A guest closes his files at the end.
2. A trace of the W205 mozglue failure.
3. The `user.reg` of the build stops bringing `AppDefaults\palemoon.exe`.

The user's decision is that Pale Moon always runs as a guest, without reopening the title ("I want you to always run without reboot"). That's why it's not compared to Pale Moon running alone.

<a id="1-un-invitado-cierra-sus-archivos-al-terminar"></a>


# 1. A guest closes his files when he is finished

<a id="qué-pasó-en-w205"></a>


## What happened in W205

Report: `reports/wine-hardware-w205/physical/20261104T143053Z/run-0002.log`, lines 2818 to 2840.

- Pale Moon, as a guest, ended (by a failure, line 2558). Then it could not be reopened until it restarted OrbisDesk.
- The second start:
  - `palemoon.exe` load;
  - tries to load `Rstrtmgr.dll` (`c0000135`);
  - ends up in a state of 0, without showing anything.
- **What does `Rstrtmgr.dll` indicate:** Pale Moon use the Restart Manager to search for who has taken his profile. It comes there when it cannot open `<perfil>\parent.lock`, because it opened without sharing (`CreateFileW`, sharing 0, `FILE_FLAG_DELETE_ON_CLOSE`) and no one closed it.
- **What he does today `ps4_guest_exit_process`** (`tools/build-guest-hw.py`):
  - ends the guest's threads;
  - destroys its windows;
  - download your module.
  
  He doesn't close any hands. The process is still alive, so nothing closes them, as it would be at the end of a real process. This is for any guest, not just for Pale Moon.

<a id="cambio"></a>


## Change

`tools/build-guest-hw.py`, in kernelbase:
- **`file.c`, `CreateFileW`:** a file that opens from a guest thread, with the program code itself, is entered in the guest together with its file index. It counts as a program code:
  - a caller outside the Windows directory;
  - or the C runtime (`ucrtbase`, `msvcrt`).
  
  The Wine DLL can stay with a file that opened from a guest thread throughout the title, so that those are not annotated.
- **`process.c`, `CloseHandle`:** a handle that closes a guest's thread comes out of the list.
- **`process.c`, `ps4_guest_unload`:** each annotated handle that still points to the same file (same index) is closed, and `PWGUEST files module=… closed=… stale=…` is recorded. This happens:
  - on the departure of the guest;
  - when it fails and ends with `TerminateProcess`;
  - when it ends along with your console.
  
  A handle that the program closed on another path (`NtClose`) and then reused for another file is not touched.

**Not covered:**
- open files directly with `NtCreateFile` or by the DLL of Wine;
- other hands: events, mutex, sockets, sections.

<a id="construcción"></a>


## Build

1. `python3 tools/build-guest-hw.py`.
2. `tools/link-wine-boot.py`.
3. `tools/build-wine-hardware.py`.

<a id="prueba-física"></a>


## Physical test

1. Open Pale Moon (as a guest) and close it.
2. Open it again without reboot OrbisDesk.
3. **What to look for in the log:**
   - when closing it, `PWGUEST files module=… closed=…` with `closed` greater than 0;
   - that the second start opens the window and does not charge `Rstrtmgr.dll`.
4. Repeat with a failure closure, if you can play (W205: second tab and navigation).

<a id="no-verificado"></a>


## Not verified

- Nothing was tested on the console.
- The change was compiled only with `-fsyntax-only` (mingw, with the definitions of kernelbase), on a copy of the sources with all the revisions of the builder.
- That `parent.lock` is the hand that blocks it comes out of the code of Pale Moon and the load of `Rstrtmgr.dll`, not of a measurement.

<a id="2-traza-del-fallo-de-mozglue-diagnóstico"></a>


# 2. Mozgue failure race (diagnosis)

<a id="qué-pasó-en-w205-1"></a>


## What happened in W205

Report: `reports/wine-hardware-w205/physical/20261104T142955Z/run-0002.log`, line 2536.

- **The failure:** the `0064` thread of Pale Moon fails in `mozglue.dll+0x10EEA`.
- **The records:** `rcx` and `rsi` are worth `0xe5e5e5e5e5e5e5e5`, and `rbx` worth `e5e5e5e5e5e00000`. It is the filling that mozjemalloc puts in the released memory, masked to the direction of a block. His allocator received a read-out memory pointer: a use after release (use-after-free).
- **Where is the error:** in the code that calls the allocator. The log does not show it: the trace of Wine brings only the records, and then the handle of Pale Moon ends it (`TerminateProcess` 253).
- **Before the failure:** the same thread calls twice to `NtGdiRemoveFontMemResourceEx`, which in Wine is a stub: return `TRUE` and leave the sources registered.
  - Pale Moon releases the source without looking at that result, so the stub does not explain a use after release at the same time.
  - Wine copies the data from the source when adding it, so it doesn't keep the memory of Pale Moon either.
  
  For now it is just a mark of when it passes: the closure of a page or tab.

<a id="cambio-1"></a>


## Change

`tools/build-guest-hw.py` (kernelbase, `process.c`), with `guest-fault-trace-w207.patch.py`:
- **What you install:** with the first guest, a vectorized handler, the first of the chain.
- **What does it record?:** for the first 8 access violations of the title, `PWFAULT`, before the program drivers run. Registration:
  - the direction, reading or writing and the destination;
  - the frames (module + displacement), unrolled from the context of the failure within the stack of the own thread.
  
  The module names come out of `LdrFindEntryForAddress`, which does not take any lock. A frame of JIT, without a module, cuts the route.
- **It does not change behavior:** returns `EXCEPTION_CONTINUE_SEARCH`, so program managers run the same.

<a id="prueba-física-1"></a>


## Physical test

1. Repeat the W205: open a second tab and navigate until Pale Moon closes.
2. **What to look for in the log:** the lines `PWFAULT n=1 …`. The framework 0 It has to be `mozglue.dll+10eea`. The following show who passed the released pointer to the allocator, in general movements within the `xul.dll`.
3. With these displacements the function is sought in `xul.dll` of Pale Moon 35.0.3. Pale Moon does not bring symbols: it is identified by disassembly and by nearby imports.

<a id="3-userreg-sin-appdefaultspalemoonexe"></a>


# 3. `user.reg` without `AppDefaults\palemoon.exe`

`tools/build-wine-hardware.py`, with `palemoon-userreg-w207.patch.py`, remove the two blocks:
- **`OrbisRunsAlone="Y"` (W183):** would make Pale Moon It will relaunch the title again.
- **Your `DllOverrides` (W184: `d3d10core`, `d3d11`):** never apply to a guest, who runs with the `AppDefaults` of `explorer.exe` (Wine takes the name of the executable process).

If the upload merge again adds blocks that the console no longer has is the theme of the desktop-short cuts session.

<a id="construcción-las-tres-partes"></a>


# Construction (all three parts)

1. `python3 tools/build-guest-hw.py`.
2. `tools/link-wine-boot.py`.
3. `tools/build-wine-hardware.py`.

<a id="no-verificado-las-tres-partes"></a>


# Not verified (all three parts)

- Nothing was tested on the console.
- The three scripts were applied together on copies of the builders:
  - the kernelbase revisions are applied to the sources;
  - `file.c` and `process.c` pass `-fsyntax-only` with mingw and definitions of kernelbase.
  
  The builders didn't run.
