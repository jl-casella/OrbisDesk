<a id="incremento-18-console32exe-con-el-crt-de-mingw-sin-wine"></a>


# increment 18: console32.exe with the CRT of mingw, without Wine

[English](INCREMENT_18.md) | [Español](INCREMENT_18-es.md)

**console32.exe, compiled with the CRT of mingw, runs complete in the Linux fork of shadPS4 without Wine.** Start the running C (TLS of the EXE, initializers, `__getmainargs`, run `main`, create a thread and write `result.txt` with the same content as in Windows native. It comes out by `exit(0)` after running the handlers of `_onexit`. All of this is based on a msvcrt minimum of its own, not the Windows or the Wine. Hardware: pending.

<a id="referencia-de-windows-y-binario-reproducible"></a>


## Windows and reproductable binary reference

`tools/build.py` linked `console32.exe` and `gdi32.exe` with a time mark, and so each build changed its hash. Now they use `-Wl,--no-insert-timestamp`, like `console32-bare.exe`: two built in a row give the same hash (`d9dbb672…`). `reports/increment18-windows-reference/` save the native execution of that binary in this host (Windows 11 Pro 10.0.26200). It comes out with 0 and produces a `result.txt` identical to that of the 11 increment.

<a id="loader-y-lifecycle"></a>


## Loader and lifecycle

- `PW_PE32_MAX_SECTIONS` goes from 16 to 32. The EXE has 17 sections: 9 own and 8 `.debug_*`, which are mapped as read-only data.
- `pw_pe32_parse_tables` accepts a directory TLS in the EXE, with the same validations as in one DLL.
- `pw_pe32_lifecycle_create` supports an EXE linked to the slot 0, only by its TLS: it gives it index 0 (like Windows), a block by thread and its callbacks TLS in process and threaten attach/detach. `notify` never calls its entry point.

<a id="módulos-sintéticos"></a>


## Synthetic modules

`pw_k32_ps4.c` separates the mechanism of thunks from the export tables (`pw_k32_internal.h`):

- Each export declares a convention (stdcall or cdecl), bytes of arguments and if it is varied.
- An export of data points to an RW page of the module, which is added to the table of regions of each thread. So they work `_iob` and `__initenv`.
- `pw_k32_call_guest` executes the nested guest code within a call. It is the same pattern `pw_guest_callback_enter` + `execute` that the increment 17 uses for `DllMain`. `_initterm` and the handlers of `exit` use it.

**kernel32** goes from 15 to 26 functions:

- `Initialize` / `Enter` / `Leave` / `DeleteCriticalSection`: the property is carried in the host, with owner, recursion and waiting on the condition of the process.
- `GetModuleHandleA`.
- `GetStartupInfoA`.
- `SetUnhandledExceptionFilter`: it is recorded, but nothing invokes it because there is no SEH.
- `Sleep`.
- `TlsGetValue`: read the TEB slots in `+0xE10`. `TlsAlloc` is not served.
- `VirtualQuery`: responds from the table of logical regions.
- `VirtualProtect`: it is rejected with a trace. The list of pseudo-replacements of mingw is empty in this EXE, so the CRT does not call it.

**msvcrt** (`platform/ps4/pw_msvcrt_ps4.c`, 25 exports):

- Guest heap of 1 MiB in `0x3c000000`, with block metadata in the host: `malloc`, `calloc`, `free`.
- `memcpy`, `strlen` and `strncmp` over validated memory. An inaccessible pointer is a guest failure (`PW_ERR_VM`), as would an access violation in Windows.
- Start of CRT: `__getmainargs`, `__p__fmode`, `__p__commode`, `__p__acmdln`, `__set_app_type`, `__setusermatherr`, `__lconv_init`, `_initterm` and `__initenv`.
- Output: `_onexit`, `exit`, `_cexit`, `abort` and `_amsg_exit`.
- `signal` records the handler; He never gives a signal.
- `fwrite`, `fprintf` and `vfprintf` only write in stdout or stderr, as lines `PWCRT` of the trace. The format is limited to `%s %d %i %u %x %X %p %c %%`; the rest is rejected with - 1.

<a id="traductor"></a>

## Translator

The CRT calls `_fpreset`, which is `FNINIT` (`DB E3`). The upstream block translator emulates quite x87, but not that instruction, and the route hostexec does not support it. `platform/ps4/pw_cpu_ps4.c` solves it in its fallback on the already synchronized guest's FP status without touching the host's FP or upstream sources: it restores the control word 0x037F, cleans status, pointers and outstanding exceptions, and marks all records as empty. It counts in `PwPs4CpuStats.x87_resets`. `rep stos` and `lock cmpxchg` already supported by the translator.

<a id="resultado-en-el-fork"></a>


## Results in the fork

The case `console32` requires:

- `result.txt` identical to Windows and output 0;
- no rejection, unclosed handle or thread failure;
- 3 initiators and 2 handlers of `_onexit` executed;
- 8 EXE notifications TLS: two callbacks of mingw for each process attack, threat attack, threat detach and process detach;
- exactly 2 living heap blocks on the way out: the copy of `argv` that makes the CRT of mingw and that never releases;
- no living memory reserve at the end.

`GetModuleHandleA` with name returns `ERROR_MOD_NOT_FOUND`. It's the search for the libgcc DLL that mingw does to register frames; with `-static-libgcc` also fails in Windows. `check-increment18.py` sets the complete sequence of calls visible from the host, so any change of way in the CRT makes the verifier fail.

|Environment, same ELF| console32 |Reasons|
|---|---|---|
| Fork Linux `bf96b33` | **passed** |`result.txt` equal to Windows, output 0, without stubs or rejections|
| shadPS4 oficial Linux v0.20.0 | blocked |The guest passes; `process.cpp:312 exit: Unreachable code!` and timeout, as in the increments 16 and 17|
| shadPS4 oficial Windows v0.20.0 | blocked |`address_space.cpp:603 Protect: Unreachable code!` when publishing the first RX block|

They changed the loader, the lifecycle and the fallback of the CPU, so `check-increment18.py` repeats in the fork all the PE cases of the 4 increments to 7 (`pe-*`, 20 cases), `console-bare`, `lifecycle-host`, and the eight always regressions. Everyone's coming through. No patch was added to the emulator.

<a id="hallazgo-aparte-dispatcher-mixed-en-el-fork-linux"></a>


### Other finding: dispatcher-mixed in the fork Linux

I added `dispatcher-mixed` as extra regression and failed in the fork Linux, with `steps=10 blocks=6 host=4`. I repeated the case with the ELF archived increment 17, prior to all changes of this increment, and fails with the same line of detail. It is not a regression of 18: the case was validated in the fork of Windows during the increment 3 and had never been part of the checks of Linux. It is out of `check-increment18.py` and to be investigated separately.

<a id="reproducción-y-evidencia"></a>


## Reproduction and evidence

```sh
python3 tools/build.py --with-wine-platform
python3 tools/run-linux-wine.py --fork --baseline --case console32
python3 tools/check-increment18.py
python3 tools/check-increment18.py --verify-only
```

```powershell
./tools/run-probes.ps1 -Cases console32 -TimeoutSeconds 25
```

`reports/increment18/report.json` indexes the runs, the call sequence, the output `PWCRT` and the case detail. The official report of Windows, generated with the ELF final, is in `reports/runs/20261030T211159115Z/`. Hardware: pending.

<a id="próximo-hito"></a>


## Next milestone

Retreat the track Wine. The increments 16 to 18 leave the parts needed by a provider WoW64 tested:

- the translator as CPU 32 bit;
- the border of thunks towards the host;
- the callbacks nests;
- the TEB and the TLS by thread.

The proposed order:

1. Mount the prefix of the increment 15 in `/data/wine-prefix` and do not launch wineboot when it is already initialized.
2. GS by thread in the runtime PS4.
3. A provider WoW64 (`BTCpu*`) over `pw_cpu_ps4`, validated with `console32-bare.exe` against the result that it already gives without Wine.
