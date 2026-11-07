<a id="w184-parte-de-winecfg-aceptar-o-cancelar-ya-no-cierran-todo"></a>


# W184, part of winecfg: Accept or Cancel no longer close everything

[English](HARDWARE_W184-winecfg-borrador.md) | [Español](HARDWARE_W184-winecfg-borrador-es.md)

Eraser of the configuration session of Wine. The main session adds it to `HARDWARE_W184.md`.

<a id="qué-pasó-en-w183"></a>


## What happened in W183

In `run-0001.log` (`reports/wine-hardware-w183/physical/20261103T232154Z`; equal to `run-0002` and `run-0003`):

1. winecfg (guest `0x100780000`, thread `0040`) ends with `ExitProcess` and is downloaded.
2. rundll32 (another guest, thread `003c`, the one that runs `winecfg.cpl`) download `winecfg.cpl` and call `exit()` at the end of its `main`.
3. Fault in `0x100782560`, inside the winecfg already downloaded. The title ends with `0xc0000005`.

<a id="la-causa"></a>


## The cause

- `0x100782560` is `winecfg.exe+0x2560`: `do_global_dtors`, from the start of the CRT of mingw.
- When you start, winecfg records it with `_crt_atexit` in ucrtbase, and ucrtbase saves a **single atexus table for the whole process** (`MSVCRT_atexit_table`, `dlls/msvcrt/exit.c`).
- winecfg comes out with `ExitProcess`, not to go through that table, as in Windows. The entry remains, pointing to an image that is then downloaded.
- When rundll32 ends, its `exit()` runs through the whole process table, including winecfg input, and jumps into released memory.
- It's the same type of error as the W114 exception filter: something from the process that keeps an address from a guest that is no longer there.

In addition, in `ps4_guest_launch` the guest's new thread is created from the thread that calls `CreateProcess`. If that thread is from another guest (rundll32), `CreateThread` the new thread is placed in the new thread by the guest from the one who creates it and adds it to **its** list of threads. So in W179 the output of rundll32 finished the winecfg thread.

<a id="cambio"></a>


## Change

In `tools/build-guest-hw.py` (it applies `guest-exit-w184.patch.py`):

- **ucrtbase (`exit.c`):** each guest has its own atexus table, stored in its `struct ps4_guest`, right after the first field.
  - `atexit`, `_onexit` and `_crt_atexit`, called from a guest's thread, record on that guest's table. `exit()` from a guest only travel his board.
  - Outside the guests (explorer) everything remains the same, with the process table.
  - A guest who comes out with `ExitProcess` leaves his tickets unrun, as in Windows, and there is no table left that any other program will go through.
- **kernelbase (`ps4_guest_launch`):** while creating the new guest's thread, the calling thread is no longer marked with its guest. The new thread is just from the new guest.
- Separate compiler (copy of the building with output on the scratchpad): 23 reviews; They link ntdll, ucrtbase and kernelbase. The two warnings that come out are from previous code (W060 and W105).

<a id="prueba"></a>


## Test

1. Control panel → Configuration of Wine → OK. Repeat with Cancel.
2. Repeat from Start → Run `winecfg`, which does not pass by rundl32.
3. In both cases, the desk is still on. In the log, after `PS4 guest module … exits`, rundll32 comes out without `page fault`.
