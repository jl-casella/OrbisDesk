<a id="incremento-23-console32-bareexe-mediante-wine-con-el-traductor-como-cpu-wow64"></a>


# increment 23: console32-bare.exe by Wine, with the translator as CPU WoW64

[English](INCREMENT_23.md) | [Español](INCREMENT_23-es.md)

**In the fork Linux of shadPS4, `console32-bare.exe` is run by Wine.** Wine load your actual modules (ntdll of 64 and 32 bits, `kernelbase.dll` and `kernel32.dll`) and executes the 32 bit code with the prospero-win IA- 32 translator as a provider of CPU WoW64. The programme:

- create its thread;
- load your DLL;
- writes `C:\orbis\result.txt`, identical byte to byte to that of Windows native;
- sale con 0.

It happens in three runs. In shadPS4 official emulator is still locked. Hardware: pending.

Synthetic modules from the increments 16 to 18 are not used: everything goes by Wine.

<a id="proveedor-wow64-wowprospero-para-ps4"></a>


## provider WoW64: wowprospero for PS4

The increment 22 ended with `0xc0000135` because the provider of CPU WoW64 was missing. It adapts `wowprospero` of prospero-win (LGPL- 2.1 -or-later), the backend `BTCpu*` that runs the i386 code with the translator. `tools/build-wowprospero-ps4.py` builds three pieces and records the original and adapted hash of each source:

- **Part Unix**: `unix.c` and DBT (`pw_x86_engine`, `block`, `cache`, `hostexec`, `reencode`, `x87`, `guest_fp`, `vm`) compiled for Orbis. The only adaptation of `unix.c` is to read RIP and RSP from the signal context with the Layout FreeBSD that Orbis uses (the same of PS5). They are linked within the ELF of Wine. There is no `dlopen`: ntdll find the table `__wine_unix_call_funcs` of the module by the name of its `.so`, in `platform/ps4/pw_wine_unixlibs.c` (`PWBOOT static_unixlib`).
- **`wowprospero.dll`** (64 bit PE), linked as it does prospero-win, against the Wine tree of the set host.
- **`wow64.dll`** with the selection of the provider by environment, adapted from the 0611 patch of prospero-win: `WINE_PS4_WOW64_CPU` only accept `wowprospero.dll`. If you can't load it, use the prefix choice.

The runner activates it with `--wow64-cpu wowprospero`. Copy the two PCs verified by hash and, after checking the prefix package, install `wowprospero.dll` in `system32` of the prefix extracted, as prospero-win install it in PS5. Outside the bootstrap, Wine only loads a building through a file of `system32`. The prefix package does not change, and still does not include the `wow64cpu.dll` host hardware.

<a id="bloqueos-resueltos-en-el-camino"></a>


## Blocks resolved on the way

Each was resolved with an explicit test and correction.

1. **Alternative, non-existent (fork 0014)** signal cell. All thread started with `sigaltstack` in zero and without `SS_DISABLE`. Since the increment 22, the handlers of Wine arrive with `SA_ONSTACK`, so the fork jumped to a pile in the direction 0 and the emulator fell with SIGSEGV. Now the threads start with `SS_DISABLE`, as in FreeBSD.
2. **`stack_t` untranslated (platform)**. Wine install your signal stack with the `stack_t` of the SDK: Layout of Linux and `SS_DISABLE=2`. libkernel waits for the FreeBSD: `ss_size` before `ss_flags` and `SS_DISABLE=4`. `pw_wine_sigaltstack` translates it..
3. **SS in the signal context (fork 0015)**. Wine compare the saved SS to your data selector to recognize 16 bit code. With SS in 0 it treated the failure as 16 bit and read a TEB of WoW64 null. Now SS (from the context of Linux is reported if the kernel keeps it; If not, the current), DS and ES.
4. **No memory (platform)**. Wine book with `PROT_NONE` and then make the commit by changing the protection. In Orbis, and in the PS4 real, a reservation has no memory and the kernel ignores the protection over it. The translator's code sand was empty and the first block failed to run. `pw_wine_memory_protect` mapia fixed flexible memory on the parts not yet compromised, as well as `pw_wine_anon_tryfixed` with new views.
5. **`madvise` stub (fork 0016)**. The title's `free` libc calls `madvise` with `MADV_DONTNEED`. In FreeBSD those tips (up to `MADV_CORE`) only guide the payer and retain the content. The fork validates rank and advice and returns success without asking the host for anything, whose `MADV_DONTNEED` would delete anonymous pages. `MADV_PROTECT` returns EPERM; Unknown advice, EINVAL. Before the Runs had this stub invoked and that's why it didn't count as approved.

To diagnose, the runner was added `--winedebug` and `--wineenv`. They are only used for diagnosis, they are recorded in the report, and the verifier rejects any Runs that uses them. The spins of the falls were produced by the `core_pattern` of WSL (`/wsl-capture-crash`, in `%LOCALAPPDATA%\Temp\wsl-crashes`. From there came the records and the signal of each fall.

<a id="pruebas"></a>


## Tests

- `--signal-services` passes from 5 to 7 cases: `SA_ONSTACK` without alternative stack (with `SS_DISABLE` informed) and a stack installed with the `stack_t` of the SDK, in which the handler must run. The reading case also requires that CS, SS and DS match those of the thread.
- `wine-memory` from 7 to 10 checks:
  - a reservation committed for protection runs code;
  - `MADV_DONTNEED` retains the content;
  - an invalid council returns EINVAL.
- The attempt with prepared prefix now compares `result.txt` to `reports/increment11-windows-reference/` (content, EXE hash and output). `Wine_booted` and `windows_execution_verified` only go true if everything matches, the process comes out with 0, there is no timeout or access violations and no stub was invoked.

|Environment|console32-bare.exe by Wine|
|---|---|
| Fork Linux, `--wow64-cpu wowprospero` |**passed**, 3 of 3: `result.txt` identical, output 0, without stubs|
|Fork Linux without provider|`0xc0000135` (`load_64bit_module`), as in the increment 22|
| shadPS4 oficial Linux v0.20.0 |blocked: `readlink` is stub in preflow of prefix and wins the timeout|

<a id="validación"></a>


## Validation

`tools/check-increment23.py` exige:

- the three approved runs against the reference of Windows;
- the prepared EP hashes (ntdll of 64 and 32 bit, `wow64.dll`, `wowprospero.dll`;
- no `wow64cpu.dll` enter the execution package;
- the above blocks do not appear again;
- the control without a provider and the official comparison;
- GS, signals, `wine-memory`, `segments`, `services`, preflight and empty prefix;
- `exceptions` with the same line in fork and official;
- the contracts of mmap and file mapping, and the matrix of the increment 18.

It's all in `reports/increment23/`. `fork.lock.json` fix the commit `7b9f902` with the patches 0001 to 0016.

<a id="reproducción"></a>


## Reproduction

In Ubuntu 22.04/WSL, in this order: `build.py` regenerates the overlay without boot, so `prepare-wine-boot.py` Go later.

```sh
python3 tools/build-shad-linux.py --reuse-configure --jobs 12
python3 tools/build.py --with-wine-platform
python3 tools/prepare-wine-boot.py
python3 tools/build-wine-ps4.py --boot --all-unix
python3 tools/build-wine-ps4.py --boot --server
python3 tools/build-wowprospero-ps4.py
python3 tools/link-wine-boot.py
python3 tools/run-linux-wine.py --fork --prepared-prefix reports/increment15/prefix-package --wow64-cpu wowprospero
python3 tools/check-increment23.py
python3 tools/check-increment23.py --verify-only
```

<a id="qué-no-está-probado"></a>


## What's not proven

- `console32.exe` (with the CRT of mingw) by Wine. The prefix package only brings `console32-bare.exe`.
- shadPS4 official, host Windows of the fork and hardware PS4.
- 32 bit guest exceptions (SEH) and scriptures on translated code. This program doesn't exercise them.
- Graphics, input and audio.

<a id="próximo-hito"></a>


## Next milestone

1. `console32.exe` by Wine, with a prefix package that includes it and the same contract of Windows.
2. Exemptions of 32 bits and self-configurable code under wowprospero, with own tests.
3. Investigate `dispatcher-mixed` and `exceptions` in Linux, and lock the official emulator.
