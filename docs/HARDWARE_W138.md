<a id="w138-música-midi-por-directmusic-fase-5"></a>


# W138: MIDI music by DirectMusic (phase 5)

[English](HARDWARE_W138.md) | [Español](HARDWARE_W138-es.md)

APP_VER 02.37. Base W137 (native 32 bit code).

<a id="causa-del-silencio"></a>


## Cause of silence

SuperMarioKart.exe (Blitz3D) opens `smk/title.mid` and orders `CLSID_DirectMusicPerformance` (`{d2ac2881-b39b-11d1-8704-00600893b1bd}`. In W137:

    err:ole:com_get_class_object class {d2ac2881-b39b-11d1-8704-00600893b1bd} not registered

DirectMusic was not installed or registered for 32 bits.

<a id="cambios"></a>


## Changes

- **DLL i386 from DirectMusic** (`tools/stage-wine-i386.py`): dmime, dmusic, dmloader, dmstyle, dmband, dmcommos, dswave and dmScript, compiled in the Wine tree of the host.
- **dmsync** (`tools/build-dmsynth-i386.py`, new): the software synthesizer of Wine.
  - The host tree was set up without C + + cross compiler for i386. That's why the set deactivated `libs/fluidsynth`, `dlls/dmsynth` and the libc + + of Wine.
  - FluidSynth has a single C + + file and does not use the C + + runtime. It is compiled with `clang++ --target=i686-w64-mingw32` without exceptions, RTTI or C + + headers. The builder checks that the object does not remain with references to `_Z*` / `__cxa*`.
  - dmsync is linked without the C + + bookstores, with the same Makefile recipes of Wine (dmime).
- **Registration:**
  - The COM classes of those DLL go in `Software\Classes\Wow6432Node\CLSID`. They are removed from the `.idl` of the fixed code of Wine.
  - `GMFilePath` (in the two views of `HKLM\Software\Microsoft\DirectMusic`) pointed to `C:\windows\system32\drivers\gm.dls`, which the prefix does not have. Now point to `C:\windows\GeneralUser-GS.sf2`.
- **MIDI General Bank:** GeneralUser GS v2. 0.3, of S. Christian Collins, chosen by the user.
  - It was downloaded from the commitment `684543d5e5efaef08d02be50dcda8d552478fa60` of github.com/mrbumpy409/GeneralUser-GS: 32 319 396 bytes, sha256 `9575028c…688cfe`.
  - Your license allows you to use it and redistribute it, and it goes next to it as `C:\windows\GeneralUser-GS-LICENSE.txt`.
  - Wine dmloader accepts SoundFont (`sfbk`) in addition to DLS.
- **Log of PE32:** is added `warn+` of dmloader, dmsync, dmime and dmusic, to see the load of the collection and the synthesizer.

<a id="qué-se-espera"></a>


## What is expected

That SuperMarioKart play the title music. In the log, `PWAUDIO` with a level greater than 0 and no `class ... not registered`.

<a id="prueba-física"></a>


## Physical test

`reports/wine-hardware-w138/physical/20261103T065542Z`. The user confirms: **the music does not sound**. Enter and Back respond on the menu; the rest of the controls were not tested.

What the log (`run-0002.log`) shows:
- **What does work:** the chain DirectMusic starts whole.
  - He's gone. `class ... not registered`.
  - dmloader opens `C:\windows\GeneralUser-GS.sf2`.
  - The dmsync port is activated on dsound.
  - dmime reads `smk/title.mid` and touches his tracks.
- **Why doesn't it sound:** each note ends in `warn:dmsynth:play_instrument Could not find instrument with patch …`. There are some 3000 lines like this, for the patches 0x4, 0x26, 0x80000018, etc.
- **The output:** `PWAUDIO level` has samples other than zero, but with peak 2 (digital silence). The peak rises to ~ 11 000 only with the WAV effects of the game.
- **Cause:** the game loads the instruments of the song with `IDirectMusicSegment::SetParam(GUID_Download, performance)`, the form of DirectX 7. In the Wine set, `bandtrack.c` just print `fixme:dmband:band_track_SetParam GUID_Download not handled yet` and do not download anything to the synthesizer. It is corrected in W139.
