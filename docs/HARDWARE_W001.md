<a id="prueba-física-w001-wine-en-la-ps4"></a>


# Physical test W001: Wine in the PS4

[English](HARDWARE_W001.md) | [Español](HARDWARE_W001-es.md)

W001 is the first attempt to start Wine on hardware. Before they passed H001 and H001B, they tested the basic platform without Wine (see [HARDWARE_H001.md](HARDWARE_H001.md)).

- Paquete: **OrbisDesk Wine W001**, Title ID `ORBW00002`.
- Destination console: PS4 Pro of H001.
- The launcher (`native/wine_hardware.c`) is linked with the same objects of Wine that passed `console32-bare.exe` by wowprospero in the increment 23. `tools/build-wine-hardware.py` verifies it against the hashes of `build/wine-boot/link-report.json`.
- On the console, the launcher does in order:
  1. open `/data/orbis-win/w001/run-NNNN.log`;
  2. try to redirect stdout and stderr to that log;
  3. creates the links `dosdevices/c:` and `z:`;
  4. if there is a previous `result.txt`, it archives it;
  5. Call `pw_wine_boot_main --prepared-prefix --wow64-cpu=wowprospero.dll`.

  On screen is the stage achieved.

The runtime does not travel within the PKG: they are 430 files and 294 MB. They are copied by FTP to `/data`:
- `wine-prefix`, the increment sealed 15;
- `wine-home`;
- `wine/lib/wine/{i386,x86_64}-windows`;
- `wine/share/wine/nls`.

Each file is verified by reading it back. The executable `console32.exe` is left in `drive_c/orbis`.

<a id="cambios-del-launcher-tras-el-smoke-test"></a>


## Changes in the launcher after the smoke test

- **The marker now comes out of a measured effect, not of the return value. `dup2`.**
  - In the fork, `dup2` is a stub that returns 0 without redirecting anything. The first smoke test ended with an empty log.
  - Now the launcher writes a probe by fd 2 and checks that the log grew. The result is `W001 stderr_redirect ... verified=0|1`.
  - The launcher markers are written directly to the log, without depending on the redirection.
- **Unit links cannot be tested in the emulator.**
  - The SDK libc implements `readlink` and `symlink` as direct syscalls FreeBSD (57 and 58). The stub libkernel does not export them.
  - The fork does not attend to direct syscalls and returns ENOSYS (78).
  - `tools/run-wine-hardware.py` explicitly classifies as `emulator-limit` the Runs that stops exactly at `W001 drive_c rc=78` with only stub `_dup2`. That classification is not a `passed`.
  - What's left after the links is only tested on the console.

Smoke test: `reports/wine-hardware-w001/20261031T054609Z/` (`emulator-limit`).

<a id="herramientas"></a>


## Tools

```sh
python3 tools/build-wine-hardware.py
python3 tools/run-wine-hardware.py              # smoke en el fork
python3 tools/upload-hardware.py --build W001   # PKG + runtime, lectura de vuelta por hash
python3 tools/fetch-hardware.py --build W001    # log, cuadros y result.txt de la consola
```

Restrictions of `upload-hardware.py`:
- do not delete anything remote and skip the files whose remote hash already matches;
- apply `SITE CHMOD` 777/666 to `wine-prefix` and `wine-home`, so that Wine can write the record, and 644 to the rest.

`fetch-hardware.py` save the evidence in `reports/wine-hardware-w001/physical/<ts>/` and classify the Runs as follows:
- `passed`: `result.txt` identical to the reference of Windows and output 0;
- `blocked`: there is an output code, but the above is not met;
- `crashed`: there are markers, but there is no output.

<a id="estado"></a>


## Status

The PKG is in `/data/pkg/orbis-win-W001-255931edb0ce.pkg` (7.340.032 bytes).

Up from the runtime: 430 files and 293.681.470 bytes, all verified by reading them back. No flaw of `chmod`.

- The first attempt was cut by a timeout of FTP control.
- The uploader now reconnects and retries every step. The second past found 320 files already correct and uploaded 110.
- Registration: `reports/wine-hardware-w001/transfers/20261031T055154Z.json`.

<a id="resultado-físico"></a>


## Physical result

**Result: `blocked`.** The user installed W001 and executed it five times, of `run-0001.log` a `run-0005.log`. The five of them give the same thing:

```
W001 stderr_redirect dup2_out=-1 dup2_err=-1 verified=0
W001 sysmodule_net rc=0x00000000
W001 drive_c rc=78
```

Evidence: `reports/wine-hardware-w001/physical/20261031T055531Z/`. There's a first collection, which classified this as `crashed`, in `20261031T055338Z/`. Wine He didn't get to start..

**What is known:**
- In the console, `readlink`, which the SDK libc emits as a direct syscall FreeBSD, returns **ENOSYS**, just like in the fork. The most likely is that `symlink` runs the same fate, but it didn't come to be called, because the launcher stops at `readlink`.
- An app of PS4 cannot consult symbolic links by that way, and probably not create them either.
- `dup2` returns - 1, and this version did not record the errno.

**Consequence.** The prefix design involves symbolic links:
- `dosdevices/c:` and `z:`;
- the preflight of the increment 19, which makes `readlink` of both;
- the resolution of routes of `pw_wine_fs.c`, which follows links with `readlink`.

That guess is not worth it on the console. The next step is a no-link prefix of the file system. There is no claim that Wine start on hardware.

What is most likely to appear first in a console is the executable memory: code PE64 file mapping and the sand of the wowprospero translator. H001 did not test JIT or `PROT_EXEC`. If the log stops there, the next step is an isolated probe H002.
