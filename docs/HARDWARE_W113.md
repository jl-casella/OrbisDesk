<a id="w113-diagnóstico-de-audio-dos-smbexe-sin-sonido"></a>


# W113: audio diagnosis DOS (smb.exe without sound)

[English](HARDWARE_W113.md) | [Español](HARDWARE_W113-es.md)

APP_VER 02.12. Base W112 (Task Manager accepted, DOS included)

<a id="lo-que-muestran-los-logs-de-w112-20261102t193318z"></a>


## What the logs of W112 (20261102T193318Z) show

smb.exe opens through the route DOS (`PWDOS dispatch`), the core DOSBox Pure runs and the audio output of the PS4 is opened without error:

- `PWDOSAUDIO init rc=0`, then `open source_rate=44100 port=536870919 status=0`.
- The core asks 48000 Hz: the host closes and reopens (`init rc=8026000e`, already initialized, accepted) and `open source_rate=48000 ... status=0`.
- When closed: `close blocks=15318` (run- 0001) and `blocks=11137` (run- 0002), no errors. They are about 80 and 60 audio delivered to `sceAudioOutOutput` in blocks of 256 paintings.

I mean, the audio does get to the port and the port accepts it. With these logs you cannot distinguish between: (a) the core delivers silence (the game does not use an active emulated device, or use it with volume 0), or (b) the PS4 does not reproduce that port (port volume, user, exit route).

<a id="cambio-sólo-elf-nativedos_audioc"></a>


## Change (only ELF, native/dos_audio.c)

- After `sceAudioOutOpen`, `sceAudioOutSetVolume` to 0 dB (32768) in L and R, with rc in the log (`PWDOSAUDIO volume`). If it fails, the port is closed and the error is returned; The host shows "without audio." The default port volume is not assumed.
- Level of the signal that sends the core: each 938 block (~ 5 s) `PWDOSAUDIO level` with pictures received, samples other than zero and peak; When you close, the totals.

doshost.exe, the core and the runtime PE do not change (553 files, 2 uploaded: record).

<a id="entrega"></a>

## Delivery

`/data/pkg/orbis-win-W113-20ce4e1f2972.pkg`, check-back reading; report reports/wine-hardware-w113/transfers/20261102T193930Z.json. W112 withdrawn.

<a id="prueba"></a>


## Test

Open Documents/smb.exe, play some 20 s, close. Tell me if anything was heard.

```sh
python3 tools/fetch-hardware.py --build W113 --host 192.168.68.104
```

- `volume rc=0` and you can hear it: it was the volume of the port.
- `peak=0` / `nonzero=0`: the core delivers silence; next step, check which sound device uses the game (PC speaker, Sound Blaster, AdLib) and the core configuration.
- `peak>0`, `volume rc=0` and it is not heard: the problem is at the output of PS4.

<a id="resultado-físico-20261102t194242z"></a>


## Physical result: 20261102T194242Z

- `PWDOSAUDIO volume ... rc=0` in the two openings: the volume of the port was left in 0 dB.
- The core ran in real-time (2046 pictures at 70,087 Hz, 1.401.243 audio tables at 48 kHz, about 29 s) and delivered **only silence**: `nonzero=0 peak=0` in each interval and at close. Close of doshost with 0.
- Conclusion: with smb.exe there is no sound because the emulator DOS does not generate anything, not because it is lost at the output of PS4. That the PS4 reproduces audio is not yet proven: a source that does generate signal is needed.
- smb.exe is packed twice (PKLITE and LZEXE); You can't tell by your chains which sound device you use. Next test: CARMEN.EXE (Where in the World is Carmen Sandiego), which uses PC speaker in the presentation. If it gives `peak>0`, the audio path works and the silence is typical of smb.exe or its configuration.
