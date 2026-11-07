<a id="w210-un-invitado-que-se-reinicia-a-sí-mismo-arranca-de-nuevo-cuando-ya-terminó-borrador"></a>


# W210: a guest who reinitiates himself starts again when he is finished (draft)

[English](HARDWARE_W210-invitado-reinicio-borrador.md) | [Español](HARDWARE_W210-invitado-reinicio-borrador-es.md)

Eraser of the browser side session, to join `HARDWARE_W210.md`. None of this was tested on the console.

<a id="qué-pasó-en-w209"></a>


## What happened in W209

Reporte: `reports/wine-hardware-w209/physical/20261104T155634Z/run-0001.log`.

- **The failure output of W209 works:**
  - "36 other threads ended, 7 windows of this thread destroyed";
  - `terminated=1` and `detach skipped`;
  - 28 modules `gone=1`;
  - are released 1,2 GB (`memory … released=119 bytes=1201668096`).
- **Pale Moon starts again** (line 2850, thread `00f8`):
  1. Restruate your start cache (`PWDELETE … startupCache`).
  2. It reinitiates itself: it calls `CreateProcess` with `palemoon.exe` and ends with 0 state (line 3303). This is Mozilla's reboot, which does not wait for the son.
- **Why the child fails:**
  1. As a guest, the son was loaded at the same time, with the first one still running. He received his `palemoon.exe`, `xul.dll` and the rest already initialized (`load_end … module=0000000100DD0000 error=126`).
  2. The first one kept them, with reason: the son is a living guest of the same folder (`count=0 … live=1`).
  3. The son found XPCOM initialized and ended with status 1 (line 3319).

<a id="cambio"></a>


## Change

`tools/build-guest-hw.py` (kernelbase `process.c`), with `guest-relaunch-w210.patch.py`:
- **When it acts:** when a thread of a guest starts the same guest program (the same route).
- **What are you doing?:**
  - `CreateProcess` come back right away.
  - An auxiliary thread, which is not the guest's, is waiting for that guest to finish and download (maximum 15 s). For that there is an event that is marked at the end of `ps4_guest_unload`.
  - Then it starts the program as a new guest, which loads it from scratch.
- **What does it record?:** `PWGUEST relaunch_later …` and `PWGUEST relaunch … parent_wait=0`.
- **If the guest continues to run at 15 s:** the program starts the same, as before (`parent_wait=258`).

<a id="construcción"></a>


## Build

1. `python3 tools/build-guest-hw.py`.
2. `tools/link-wine-boot.py`.
3. `tools/build-wine-hardware.py`.

<a id="prueba-física"></a>


## Physical test

1. Repeat the W209: make Pale Moon fail, reopen it, close it and open it again.
2. **What to look for in the log:**
   - if it is reinitiated, `PWGUEST relaunch_later app=…palemoon.exe` and, shortly after, `PWGUEST relaunch … parent_wait=0`;
   - then a new `load_begin` with `Loaded … xul.dll` again;
   - a window of Pale Moon, without `exits status 1`.

<a id="no-verificado"></a>


## Not verified

- Nothing was tested on the console.
- The change was applied on copies of the sources, and `process.c` passes `-fsyntax-only` with mingw. The builder didn't run.
- The environment variables Mozilla puts for her child remain in the process, which is shared. Mozilla erases them when you start.
