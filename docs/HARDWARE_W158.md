<a id="w158-dlopen-sin-estado-por-hilo-de-musl-cuelgues-después-de-varios-programas"></a>


# W158: dlopen without state by thread of musl (hang up after several programs)

[English](HARDWARE_W158.md) | [Español](HARDWARE_W158-es.md)

APP_VER 02.57. Base W157.

<a id="problema"></a>


## Problem

Two W155 failures that depended on which programs had run before:
- after closing glxgears, open WFM closed the app without leaving a trace (`20261103T141256Z`);
- after WFM and two games DOS (`doshost`), open glxgears (`20261103T143528Z/run-0005.log`).

In the second:
- the glxgears thread failed within a call to the Unix side: `handle_syscall_fault code=c0000005 addr=0xf8dcae`, with records full of `0xafafafaf`;
- `0xf8dcae` falls into read-only data from ELF, so it was a jump to an invalid pointer;
- the call was the initialization of `dnsapi` (`DllMain` → `__wine_init_unix_call`, followed by `No libresolv support`).
- In the running, that same call ends with `failed to load "…/dnsapi.so": Dynamic loading not supported`.

<a id="causa"></a>

## Cause

`dnsapi` is not on the static Unix library table (`platform/ps4/pw_wine_unixlibs.c`), so ntdll (`load_builtin_unixlib`) does `dlopen` of `dnsapi.so`.

The libc of the SDK is musl. Your `dlopen` static (`stub_dlopen`) fails, as you should, and keeps the error by thread in `__dl_vseterr`. Disassembled from W155:
- read the thread structure of musl in `%fs:0`;
- `free` the pointer on the offset `0xa8`;
- keeps a new message there with `malloc`;
- puts a bit on the offset `0x46`.

`dlerror` read and clean those same fields.

In the PS4, `%fs:0` is the thread block of the system, not that of musl. Every `dlopen` or `dlsym` that failed would release the word that was on that offset and write on the thread block. Wine does one for each integrated DLL with Unix side that is not on the table, on each thread you load first.

The damage depends on what was in that memory, so the failure depended on what programs they ran before. That this is the mechanism of the two cases of W155 is a deduction: the first one left no trace.

<a id="cambio"></a>


## Change

- `platform/ps4/pw_wine_dl.c`: `dlopen`, `dlsym`, `dlerror` and `dlclose` Your own.
  - They fail the same as those of musl: there is no dynamic load; `dlerror` returns "Dynamic loading not supported."
  - They don't touch `%fs` or keep state by thread.
- `tools/build-wine-hardware.py` compiles them and puts them in the link before the libraries, so those of musl (and `__dl_vseterr`) do not enter the ELF. The build script verifies it with `llvm-nm`.

<a id="qué-se-espera"></a>


## What is expected

- In the log they continue to appear `failed to load … Dynamic loading not supported` and `No libresolv support`, which are normal.
- No hanging when opening glxgears after WFM and games DOS, no closing when opening WFM after glxgears.

<a id="prueba-física"></a>


## Physical test

It was tested within W159 (`HARDWARE_W159.md`): the sequence of W155 (WFM, game DOS, glxgears, WFM) did not fail.
