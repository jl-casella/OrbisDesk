# W138: música MIDI por DirectMusic (fase 5)

[English](HARDWARE_W138.md) | [Español](HARDWARE_W138-es.md)

APP_VER 02.37. Base W137 (código de 32 bits nativo).

## Causa del silencio

SuperMarioKart.exe (Blitz3D) abre `smk/title.mid` y pide `CLSID_DirectMusicPerformance` (`{d2ac2881-b39b-11d1-8704-00600893b1bd}`). En W137:

    err:ole:com_get_class_object class {d2ac2881-b39b-11d1-8704-00600893b1bd} not registered

DirectMusic no estaba instalado ni registrado para 32 bits.

## Cambios

- **DLL i386 de DirectMusic** (`tools/stage-wine-i386.py`): dmime, dmusic, dmloader, dmstyle, dmband, dmcompos, dswave y dmscript, compiladas en el árbol de Wine del host.
- **dmsynth** (`tools/build-dmsynth-i386.py`, nuevo): el sintetizador por software de Wine.
  - El árbol del host se configuró sin compilador C++ cruzado para i386. Por eso el configure desactivó `libs/fluidsynth`, `dlls/dmsynth` y la libc++ de Wine.
  - FluidSynth tiene un solo archivo C++ y no usa el runtime de C++. Se compila con `clang++ --target=i686-w64-mingw32` sin excepciones, RTTI ni cabeceras de C++. El builder verifica que el objeto no quede con referencias a `_Z*`/`__cxa*`.
  - dmsynth se enlaza sin las librerías de C++, con las mismas recetas del Makefile de Wine (las de dmime).
- **Registro:**
  - Las clases COM de esas DLL van en `Software\Classes\Wow6432Node\CLSID`. Se sacan de los `.idl` del código fijado de Wine.
  - `GMFilePath` (en las dos vistas de `HKLM\Software\Microsoft\DirectMusic`) apuntaba a `C:\windows\system32\drivers\gm.dls`, que el prefix no tiene. Ahora apunta a `C:\windows\GeneralUser-GS.sf2`.
- **Banco General MIDI:** GeneralUser GS v2.0.3, de S. Christian Collins, elegido por el usuario.
  - Se descargó del commit `684543d5e5efaef08d02be50dcda8d552478fa60` de github.com/mrbumpy409/GeneralUser-GS: 32 319 396 bytes, sha256 `9575028c…688cfe`.
  - Su licencia permite usarlo y redistribuirlo, y va al lado como `C:\windows\GeneralUser-GS-LICENSE.txt`.
  - dmloader de Wine acepta SoundFont (`sfbk`) además de DLS.
- **Log de los PE32:** se suma `warn+` de dmloader, dmsynth, dmime y dmusic, para ver la carga de la colección y del sintetizador.

## Qué se espera

Que SuperMarioKart toque la música del título. En el log, `PWAUDIO` con nivel mayor que 0 y ningún `class ... not registered`.

## Prueba física

`reports/wine-hardware-w138/physical/20261103T065542Z`. El usuario confirma: **la música no suena**. Enter y Back responden en el menú; el resto de los controles no se probó.

Qué muestra el log (`run-0002.log`):
- **Lo que sí funciona:** la cadena DirectMusic arranca entera.
  - Ya no aparece `class ... not registered`.
  - dmloader abre `C:\windows\GeneralUser-GS.sf2`.
  - El puerto de dmsynth se activa sobre dsound.
  - dmime lee `smk/title.mid` y toca sus pistas.
- **Por qué no suena:** cada nota termina en `warn:dmsynth:play_instrument Could not find instrument with patch …`. Hay unas 3000 líneas así, para los patches 0x4, 0x26, 0x80000018, etc.
- **La salida:** `PWAUDIO level` tiene muestras distintas de cero, pero con pico 2 (silencio digital). El pico sube a ~11 000 sólo con los efectos WAV del juego.
- **Causa:** el juego carga los instrumentos de la canción con `IDirectMusicSegment::SetParam(GUID_Download, performance)`, la forma de DirectX 7. En el Wine fijado, `bandtrack.c` sólo imprime `fixme:dmband:band_track_SetParam GUID_Download not handled yet` y no descarga nada al sintetizador. Se corrige en W139.
