<a id="w114-juegos-en-start--programs--games"></a>


# W114: games in Start → Programs → Games

[English](GAMES.md) | [Español](GAMES-es.md)

Status: compiled in WSL; menu and staging edited. Not packaged, not uploaded and without physical evidence. It was also not executed in Windows or Wine host (the permission to run the .exe was denied in this session).

<a id="qué-entra"></a>


## What's going on?

|Menu|File in `C:\windows\system32`|Origin|License|
|---|---|---|---|
| Solitaire | `sol.exe` | ReactOS `base/applications/games/solitaire` + `sdk/lib/3rdparty/cardlib` |Public domain (J Brown)|
| Spider Solitaire | `spider.exe` | ReactOS `base/applications/games/spider` + cardlib |GPL- 2.0|
|(library)| `cards.dll` |ReactOS `dll/win32/cards`, default card style|LGPL- 2.1 -or-later; free images|

ReactOS revision `5f6ef754f90eef792e4ef90561bcff2cac4d3afb` (`games.lock.json`, partial check out at `.deps/reactos-games`). In the same directory are the notices `ReactOS-COPYING.txt`, `ReactOS-COPYING.LIB.txt`, `cards-images-COPYING.txt`, `games-README.txt` and `games-source.tar.gz` (corresponding source and commands).

It was chosen ReactOS because Solitaire and Spider are Win32 pure (user32, gdi32, comctl32, shell32, advapi32), compete with llvm-mingw without touching the code and all its imports are already in the runtime PE64 of OrbisDesk (`out/wine-gui`, ucrtbase via apiset). cardlib load `cards.dll` with `LoadLibrary`; If missing, it shows "Error loading cards.dll (32bit)" and comes out, it doesn't go on without cards.

The icons of the direct accesses are the icon 0 of each exe (both bring `GROUP_ICON`), as well as Minesweeper.

<a id="cómo-se-construye"></a>


## How it's built

```bash
wsl -d Ubuntu-22.04 -- bash -lc 'cd /mnt/c/Users/JoseCasella/DEV/Codex/PS4 && python3 tools/build-games.py && python3 tools/make-start-menu.py'
```

- `tools/build-games.py` verifies the review and the checkout is clean, compiles cardlib, sun, spider and cards with `~/vk-h0/llvm-mingw` (`-mwindows`, `-static`, PE32 + GUI subsystem) and writes `out/games/manifest.json` with sha256 and commands. Two consecutive compilations gave the same sha256.
- Flags that replace the environment of ReactOS, without changing sources: `-D__REACTOS__`, `-include windows.h` (heads of ReactOS include `windef.h` / `winbase.h` and `min` / `max` as macros. The inclusion `reactos/version.rc` and `reactos/manifest_exe.rc` are stubs empty: the exe do not have a version block or manifest of comctl32 v6.
- `tools/make-start-menu.py` agrega Solitaire y Spider Solitaire a `Programs/Games`.
- `tools/build-wine-hardware.py` has a new block (W114) that checks `builder_sha256` and copies with `copy_verified` everything listed in `system32` and `notices` of the manifesto. Nothing else was changed from that file.

<a id="3d-pinball-space-cadet-pendiente"></a>

## 3D Pinball (Space Cadet): dropped

Removed in W303 together with its SDL2/SDL2_mixer pins: the table needs Microsoft's data files (`PINBALL.DAT`, `.WAV`, `PINBALL.MID`), which are not shipped, and the console never had it.

<a id="sonido"></a>


## Sound

None of the card games or Minesweeper calls `PlaySound` or `waveOut`: they don't make noise in any system, so they don't serve to test audio.

What happens in the current runtime (code Wine fixed, `dlls/winmm`):

- The hardware runtime does not carry `mmdevapi.dll` or `dsound.dll`, or drivers (winealsa/winepulse). `WINMM_InitMMDevices` does `CoCreateInstance(CLSID_MMDeviceEnumerator)`; When you fail, `waveOutGetNumDevs` returns 0 and `waveOutOpen` returns `MMSYSERR_NODRIVER` (`WINMM_StartDevicesThread` failure).
- `PlaySound` synchronus returns `FALSE`. With `SND_ASYNC` returns `TRUE` because it only creates the thread; the thread fails in `waveOutOpen` and ends without visible notice. It's the only case where the caller sees success without sound.

This was not touched in W114.

<a id="posible-siguiente-paso"></a>


## Possible next step

A driver audio for Wine that uses the native bridge PS4 AudioOut that already uses DOS (`native/dos_audio.c`, private class `PW_DOS_AUDIO_CLASS` of `NtQuerySystemInformation`, ABI in `platform/ps4/pw_dos_audio.h`). The most direct thing would be a driver of mmdevapi (as winealsa) or, smaller, a replacement of the `waveOut` road of winmm. It also requires to mount `mmdevapi.dll` (and `dsound.dll`) in the runtime.
