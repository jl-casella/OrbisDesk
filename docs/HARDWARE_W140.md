<a id="w140-batería-general-midi-y-flechas-para-directinput-fase-5"></a>


# W140: General MIDI battery and arrows for DirectInput (phase 5)

[English](HARDWARE_W140.md) | [Español](HARDWARE_W140-es.md)

APP_VER 02.39. Base W139.

<a id="batería"></a>


## Battery

In W139 the music sounds without drums: dmsync says `Could not find instrument with patch 0x80000000` and `0x80000018`.
- The MIDI reader of dmime (`dlls/dmime/midi.c`) turns each program change into a band instrument with the program number alone, also in the channel 10.
  - The percussion channel then loads a melodic instrument.
  - If the channel 10 has no program change, it carries nothing.
- dmsync plays the channel 10 as a battery (patch with `F_INSTRUMENT_DRUMS`; If you don't find it, try the standard kit). He doesn't find any kit and he discards the notes.

Change in `tools/build-dmsynth-i386.py`, which now also compiles `dmime.dll` i386 with a copy of `midi.c`:
- The program changes of the channel 10 carry `F_INSTRUMENT_DRUMS`.
- The band track receives in time 0 the default General MIDI value for the 10 channel, the standard kit. A program change of the file itself at the same time is inserted later and wins.
- The other objects and resources of dmime are those of the host tree.

<a id="flechas"></a>

## Arrow keys

In W139 Enter and Back work on the game menu, but the arrows do not.
- The arrows of the pad reach Wine as `VK_LEFT` / `VK_RIGHT` / etc.
- The driver (`ps5drv.c`, overlay of `tools/build-win32u-ps4.py`) sends the scan code without the extended key mark.
- DirectInput weapon the DIK code with the scan code and that mark. Without it, the → arrow (`0x4d`) is read as `DIK_NUMPAD6` instead of `DIK_RIGHT`. Enter is not widespread and that's why it worked.

Change: the driver asks `MAPVK_VK_TO_VSC_EX`. If the result has prefix `E0`, send the key with `KEYEVENTF_EXTENDEDKEY`. It affects the arrows, Insert/Delete/Home/End/ReP ág / AvPág, Ctrl and Alt rights, among others.

<a id="qué-se-espera"></a>


## What is expected

- The music of the title with drums.
- In the log, without `Could not find instrument` for 0x80000000 or 0x80000018. There may be one if the bank does not have that exact kit: then dmsync uses the standard.
- The arrows move the selection in the SuperMarioKart menu.

<a id="prueba-física"></a>


## Physical test

`reports/wine-hardware-w140/physical/20261103T072747Z`. The user confirms: **the music with drums; The arrows remain unanswered**.

- There is no more `Could not find instrument` in the log.
- The arrows reach Wine (`code=38/39/40`), but the arrow arrangement had no effect.
  - In the Wine keyboard table (`kbdus` in `win32u/input.c`), the can code 0x4d without prefix (the 6 of the numerical keyboard) has as VK base `VK_RIGHT`.
  - `MapVirtualKeyEx(VK_RIGHT, MAPVK_VK_TO_VSC_EX)` walk the table from 0, return 0x4d before reaching 0xe04d and never give the prefix `E0`.
  - It is corrected in W141 by marking the keys extended by VK.
