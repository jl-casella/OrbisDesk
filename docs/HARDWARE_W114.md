<a id="w114-carmenexe-cerraba-todo-el-escritorio"></a>


# W114: CARMEN.EXE closed the entire desk

[English](HARDWARE_W114.md) | [Español](HARDWARE_W114-es.md)

APP_VER 02.13. Base W113.

<a id="qué-pasó-w113-20261102t194525z-run-0001"></a>


## What happened (W113, 20261102T194525Z, run- 0001)

First it opened smb.exe, it closed well. Then CARMEN.EXE was opened and the title ended with `process_exit status=0xc0000005`. Two chained failures appear in the log:

1. **In the engine DOS.** The emulation thread (004c) writes in the direction 0 with a `memset` of 0xfa000 bytes, which is exactly a picture of 640 × 400 × 4. The module `dosbox_pure_libretro.dll` had not been downloaded when closing smb.exe: the second opening reused the same module, with the overall state of the first. In W112 (run- 0001) he passed the same sequence, smb.exe followed by CARMEN.EXE, and the log also ended at that point. CARMEN.EXE was never opened as the first game, so the cause is the re-use of the engine is the most likely hypothesis, not a fact.
2. **In an explorer.** By not handling the exception, Wine called the global filter of unhandled exceptions, which continued to point at `_gnu_exception_handler` of doshost.exe of smb.exe. That filter is installed by the CRT of mingw, and that doshost was already downloaded (0x1007C39E0, RVA 0x39e0). Free memory was run and the whole process, that is, explorer and all the open programs, fell.

<a id="cambios"></a>


## Changes

- `native/doshost_win32.c`: after `retro_deinit`, `FreeLibrary` of the engine, with `PWDOS core_unloaded freed=…` in the log. Each game starts with the engine recently loaded. It was used to be loaded on purpose to reuse it, and that's what failed.
- `tools/build-guest-hw.py` (kernelbase): when you download a guest, if the unhandled exception filter points into your image, it is deleted (`PWGUEST unload cleared exception filter`). It affects all programs, not just those of DOS.

Delivery: `/data/pkg/orbis-win-W114-dcc5ea137af1.pkg`, with the check-back reading; reports/wine-hardware-w114/transfers/20261102T195238Z.json report (553 files, 10 uploaded). W113 withdrawn.

<a id="prueba"></a>


## Test

1. Open smb.exe, close it and open CARMEN.EXE.
2. Wait for the music of the presentation to sound (PC speaker).
3. If CARMEN.EXE fails again, open it as the first game after reboot the title, to separate a fault of the game from the engine re-use.

In the log you have to search `core_unloaded freed=1`. If there is a failure, it has to appear `cleared exception filter` and not a jump to free memory. For sound, look `PWDOSAUDIO level` (peak greater than 0).

<a id="resultado-físico-20261102t195906z-run-0001"></a>


## Physical result: 20261102T195906Z (run- 0001)

- Order used: CARMEN.EXE first (about 198 s, 13880 paintings), then smb.exe twice. The three closed with 0, no fall to explore.
- In the three closures: `core_unloaded freed=1` and `unload cleared exception filter` (the CRT filter of doshost was recorded; is now deleted).
- CARMEN.EXE Audio: The engine generates real signal (`nonzero=5217060`, peak of up to
  32768) in sections that match music and effects, with between silences. The motor route → bridge → `sceAudioOutOutput` delivers sound samples, and the user confirmed "has carmen sound": the audio DOS can be heard in the PS4.
- smb.exe continues to deliver silence (`peak=0`) in the two openings: it is typical of that game or its sound configuration, not of the output.
- CARMEN.EXE was not tested after smb.exe in the same session, which was the case that failed; The engine's discharge did be exercised between the three openings.

<a id="consulta-documentssupermariokartsupermariokartexe-20261102t200017z"></a>


## Consultation: Documents/SuperMarioKart/SuperMarioKart.exe (20261102T200017Z)

It is not DOS: it is a PE32 of Windows (`machine 0x14c`, GUI subsystem), of 2.043.904 bytes. Explorer sends it by ShellExecute and kernelbase rejects it with `PWOPEN reject_title_replacement`: guests who open from the desk have to be PE64, and a PE32 can only start as an initial program of the title (by WoW64). Nothing falls, just doesn't open. Its data (`SMK/*.x`, `.wav`) indicate Direct3D with mesh DirectX and WAV sound. Even if it opened, it would take Direct3D, which today does not exist (wined3d with `renderer=no3d`, without DXVK), and audio Win32 (winmm/dsound), which has no driver in the PS4. It was inspected only for FTP, without changing files.
