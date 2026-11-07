<a id="incremento-15-identidad-de-archivos-symlinks-y-prefijo-externo"></a>


# increment 15: file identity, symbols and external prefix

[English](INCREMENT_15.md) | [Español](INCREMENT_15-es.md)

**There is a prefix of Wine initialized by wineboot and verified with console32-bare.exe, but only with Wine native in Linux (WSL). The EXE is not yet run by Wine within shadPS4.** The PS4 execution continues to use the empty prefix and ends with STATUS_DLL_NOT_FOUND, as in the increment 14.

<a id="adaptación-del-emulador"></a>


## Emulator adaptation

The fork patch `0008` (commit `bf96b33d43c3ebbe842486b42944203d7892fb00`) retains the identity of the host files. So, stat and fstat of the same file, and of two hard links, return equal `st_dev` / `st_ino`, and different files are distinguished. It also exposes lstat and readlink for symlinks, with buffer limits and broken link errors. The open descriptors survive the rename of your file or directory. The Wine backend stops excluding `readlink.lo` from SDK and uses these routes. No semantic invention of lstat is made: it continues to govern the rule of increment 9.

<a id="validación-en-shadps4"></a>


## Validation in shadPS4

There are nine OpenOrbis checks in `--metadata-services` in the fork Linux:

- File and hard link identity; different files.
- Coincidence between stat and fstat.
- lstat and stat on a file symlink.
- readlink with exact and truncated buffer, unwritten off-limit.
- Symlink pendant, and readlink errors on a common file and a non-existent route.
- Directory identity.
- Renowned from a file and directory with open descriptors.

The same ELF in shadPS4 official blocks the nine tests, invokes the stub `readlink`, ends with 92 And the closure is the timeout. That result is kept apart. `check-increment15.py` also repeats the regressions: files, menads-adapter, pe-dl-relocated, vm-stress, ipc, pipes, filesystem and methadata pass; services, gs and wine maintain their expected blockages.

<a id="prefijo-externo-wine-nativo-en-el-host"></a>


## External (Wine native to the host)

`tools/build-host-wine-closure.py` compiles in the host the necessary DLL PE i386/x86_64 for `wineboot --init`, following imports and `DELAYIMPORTS`. The configuration is `--enable-archs=i386,x86_64 --without-x --without-freetype`. `tools/build-host-wine-unix.py` adds Unix libraries and data NLS/winmd.

The first four attempts of `tools/prepare-host-prefix.py` failed. The closing modules were missing, and the last one aborted because wineboot called `wininet.dll.InternetOpenW`, an uncompiled deferred load. With the complete closure (119 modules), two consecutive runs pass:

- `wineboot --init` comes out with 0 and wineserver closes clean before and after.
- `console32-bare.exe` writes `sum=500500;thread=ok;dll=ok\r\n` and comes out with 0.
- The three log files exist and there are no setupadi copy errors.

The hashes in the record change between runs because the `.reg` include time marks, so the prefix is not reproducible byte to byte. The graphic driver (explorer and COM record errors without window) and some 30 DLL that `wine.inf` tries to register (mshtml, urlmon, windowscodens, quartz...) continue to be missing. For the console EXE are not necessary; for GDI yes they will be.

`tools/package-wine-prefix.py` pack the first run for a later preflight in `/data/wine-prefix`. Replaces `c:` and `z:` as relative links, omits `com1..8` and excludes `wow64cpu.dll`, because the provider of CPU The host is not the translator PS4. Copy the EXE to `C:\orbis\console32.exe`. The manifesto records the 497 entries with its hash, and declares `ps4_runtime_ready: false`.

<a id="reproducción-y-evidencia"></a>


## Reproduction and evidence

```sh
python3 tools/build-host-wine-closure.py
python3 tools/build-host-wine-unix.py
python3 tools/prepare-host-prefix.py
python3 tools/package-wine-prefix.py reports/increment15/prefix-producer/<corrida> reports/increment15/prefix-package
python3 tools/check-increment15.py
python3 tools/check-increment15.py --verify-only
```

`reports/increment15/report.json` indexes executions, emulator and section `host_prefix`. The verifier contrasts the hash of the production report and the packed file. The producer's runs are in `reports/increment15/prefix-producer/` (four blocked and two approved). The emulator capsule is in `reports/increment15/emulator-capsule/`. Hardware: pending.

<a id="próximo-hito"></a>


## Next milestone

Track Wine: mount the prefix packaged in the execution PS4 and define a boot policy that uses it without throwing wineboot in the mode of a single process. Then they follow ntdll PE64, GS by thread and the provider WoW64 with the translator.

In parallel, the increment 16 opens an intermediate milestone: run console32-bare.exe with the own PE32 loader and a minimum kernel32, without Wine.
