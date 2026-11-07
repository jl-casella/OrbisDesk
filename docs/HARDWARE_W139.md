<a id="w139-instrumentos-de-directmusic-con-guid_download-fase-5"></a>


# W139: instruments of DirectMusic with GUID_Download (phase 5)

[English](HARDWARE_W139.md) | [Español](HARDWARE_W139-es.md)

APP_VER 02.38. Base W138.

<a id="problema"></a>


## Problem

In W138 the DirectMusic chain of SuperMarioKart starts, but does not sound (see `HARDWARE_W138.md`).
- The game (Blitz3D, DirectX 7) asks to load the instruments of the song into the synthesizer with `IDirectMusicSegment::SetParam(GUID_Download, performance)`.
- In `dlls/dmband/bandtrack.c` of the Wine set that order is only a `FIXME`. No instrument reaches dmsync, and each note gives `Could not find instrument`.

<a id="cambio"></a>


## Change

`tools/build-dmsynth-i386.py` now also compiles `dmband.dll` i386:
- Use a copy of `bandtrack.c` in which `GUID_Download` takes the same branch as `GUID_DownloadToAudioPath`, the equivalent order of DirectX 8.
  - Both receive a performance or an audio path and call `IDirectMusicBand_Download` for each track band.
  - The builder requires to find the original branch once.
- The other objects and resources of dmband are those of the host tree.
- `tools/build-wine-hardware.py` copy this dmband on top of the one that comes in `out/wine-i386`.

<a id="qué-se-espera"></a>


## What is expected

- Let the title music be heard.
- In the log: no `GUID_Download not handled yet`, almost no `Could not find instrument` and `PWAUDIO level` with high peak while the music sounds.
- There may be some `Could not find instrument` left if the bank does not have a battery kit ordered. In that case dmsync uses the standard kit.

<a id="prueba-física"></a>


## Physical test

`reports/wine-hardware-w139/physical/20261103T071201Z`. The user confirms: **music sounds**. The arrows on the menu don't seem to answer.

In the log (`run-0002.log`):
- It doesn't show up. `GUID_Download not handled yet`.
- `PWAUDIO level` reaches peak 32767.
- The `Could not find instrument` warnings were left only for the 0x80000000 and 0x80000018 patches, which are battery kits. The battery doesn't sound.
- The arrows reach Wine as keys (`input_event source=pad type=1 code=39`, `VK_RIGHT`).

The two things are corrected in W140 (see `HARDWARE_W140.md`).
