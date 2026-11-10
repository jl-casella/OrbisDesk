# W114: juegos en Start → Programs → Games

[English](GAMES.md) | [Español](GAMES-es.md)

Estado: compilado en WSL; menú y staging editados. No empaquetado, no subido y sin prueba física. Tampoco se ejecutó en Windows ni en Wine host (el permiso para correr los .exe fue denegado en esta sesión).

## Qué entra

| Menú | Archivo en `C:\windows\system32` | Origen | Licencia |
|---|---|---|---|
|Solitaire| `sol.exe` | ReactOS `base/applications/games/solitaire` + `sdk/lib/3rdparty/cardlib` | Dominio público (J Brown) |
|Spider Solitaire| `spider.exe` |ReactOS `base/applications/games/spider` + cardlib| GPL-2.0 |
| (biblioteca) | `cards.dll` | ReactOS `dll/win32/cards`, estilo de cartas por defecto | LGPL-2.1-or-later; imágenes libres |

ReactOS revisión `5f6ef754f90eef792e4ef90561bcff2cac4d3afb` (`games.lock.json`, checkout parcial en `.deps/reactos-games`). En el mismo directorio quedan los avisos `ReactOS-COPYING.txt`, `ReactOS-COPYING.LIB.txt`, `cards-images-COPYING.txt`, `games-README.txt` y `games-source.tar.gz` (fuente correspondiente y comandos).

Se eligió ReactOS porque Solitaire y Spider son Win32 puros (user32, gdi32, comctl32, shell32, advapi32), compilan con llvm-mingw sin tocar el código y todas sus importaciones ya están en el runtime PE64 de OrbisDesk (`out/wine-gui`, ucrtbase vía apiset). cardlib carga `cards.dll` con `LoadLibrary`; si falta, muestra "Error loading cards.dll (32bit)" y sale, no sigue sin cartas.

Los íconos de los accesos directos son el ícono 0 de cada exe (ambos traen `GROUP_ICON`), igual que Minesweeper.

## Cómo se construye

```bash
wsl -d Ubuntu-22.04 -- bash -lc 'cd /mnt/c/Users/JoseCasella/DEV/Codex/PS4 && python3 tools/build-games.py && python3 tools/make-start-menu.py'
```

- `tools/build-games.py` verifica la revisión y que el checkout esté limpio, compila cardlib, sol, spider y cards con `~/vk-h0/llvm-mingw` (`-mwindows`, `-static`, PE32+ subsistema GUI) y escribe `out/games/manifest.json` con sha256 y comandos. Dos compilaciones seguidas dieron los mismos sha256.
- Flags que sustituyen al entorno de ReactOS, sin cambiar fuentes: `-D__REACTOS__`, `-include windows.h` (los headers de ReactOS incluyen `windef.h`/`winbase.h` sueltos) y `min`/`max` como macros. Los includes `reactos/version.rc` y `reactos/manifest_exe.rc` son stubs vacíos: los exe no llevan bloque de versión ni manifiesto de comctl32 v6.
- `tools/make-start-menu.py` agrega Solitaire y Spider Solitaire a `Programs/Games`.
- `tools/build-wine-hardware.py` tiene un bloque nuevo (W114) que comprueba `builder_sha256` y copia con `copy_verified` todo lo listado en `system32` y `notices` del manifiesto. No se cambió nada más de ese archivo.

## 3D Pinball (Space Cadet): descartado

Se quitó en la W303 junto con sus pines de SDL2/SDL2_mixer: la mesa necesita los archivos de datos de Microsoft (`PINBALL.DAT`, `.WAV`, `PINBALL.MID`), que no se empaquetan, y la consola nunca lo tuvo.

## Sonido

Ninguno de los juegos de cartas ni Minesweeper llama a `PlaySound` ni a `waveOut`: no hacen ruido en ningún sistema, así que no sirven para probar audio.

Qué pasa en el runtime actual (código Wine fijado, `dlls/winmm`):

- El runtime de hardware no lleva `mmdevapi.dll` ni `dsound.dll`, ni drivers (winealsa/winepulse). `WINMM_InitMMDevices` hace `CoCreateInstance(CLSID_MMDeviceEnumerator)`; al fallar, `waveOutGetNumDevs` devuelve 0 y `waveOutOpen` devuelve `MMSYSERR_NODRIVER` (`WINMM_StartDevicesThread` falla).
- `PlaySound` síncrono devuelve `FALSE`. Con `SND_ASYNC` devuelve `TRUE` porque sólo crea el hilo; el hilo falla en `waveOutOpen` y termina sin aviso visible. Es el único caso donde el llamador ve éxito sin sonido.

Esto no se tocó en W114.

## Posible siguiente paso

Un driver de audio para Wine que use el puente nativo PS4 AudioOut que ya usa DOS (`native/dos_audio.c`, clase privada `PW_DOS_AUDIO_CLASS` de `NtQuerySystemInformation`, ABI en `platform/ps4/pw_dos_audio.h`). Lo más directo sería un driver de mmdevapi (como winealsa) o, más chico, un reemplazo del camino `waveOut` de winmm. Requiere además montar `mmdevapi.dll` (y `dsound.dll` para SDL/DirectSound) en el runtime.
