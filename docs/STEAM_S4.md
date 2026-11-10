# S4: install a game from the library

[English](STEAM_S4.md) | [Español](STEAM_S4-es.md)

This is the fourth phase of the Steam client. S3, the QR sign-in, is in [STEAM_S3.md](STEAM_S3.md). The app now lists the account's games that have Windows content and can install one on the console.

**Status:** the 01.14 PKG is built (01.11 added S5's launch data and shortcuts, 01.13 the gbe_fork switch: [STEAM_S5.md](STEAM_S5.md)). 01.08 and 01.09 ran on the console: the reopen without a QR code and the library worked, but neither could measure the free space: 01.08 stopped, and in 01.09 the user installed anyway (see "Console runs"). On the PC the installer was tested without an account, using anonymous downloads: installing, resuming, repairing a file and pausing. An install with the user's account **has not completed on the console yet**.

## What changes from S3

- **Main program:** `native/steam/steam_client.cpp`, which starts from S3. `steam_s3.cpp` stays as it was when it was accepted.
- **Log:** `/data/orbisdesk/steam-client.txt`, with `PWSTEAM client S4 …` lines.
- **After sign-in:** the **library list** replaces the summary:
  - only games with a Windows depot that has a public manifest, sorted by name;
  - each with its size, and "INSTALADO" when it is already installed;
  - up and down choose, X installs, O exits and triangle signs out, as in S3.
- **New screen controls** (`steam_ui.c`): up and down, and a highlighted line for the selected game.

## How an install works

`native/steam/steam_install.cpp`:

1. **Plan:**
   - the PICS app info of the game's DLC;
   - Playden's `SelectDepots` with the account's licenses: Windows, English, public branch, 64-bit over 32-bit, and the DLC the account owns;
   - `MissingBaseDepots`: if the licenses leave part of the game out, it is not installed, because it would be incomplete.
   
   The screen shows the installed size, the download size, the free space and the folder, and waits for X.
2. **Keys and manifests:** `FetchDepotAccess` for every depot, the content servers and each manifest, as in S2.
3. **Depot merge:** by lowercase path. When two depots carry the same file, the one later in Steam's list wins. Symbolic links are not created; they are counted.
4. **Space:** whatever is already in the folder counts, and at least 512 MB must stay free. On the console, free space is read with the kernel's `fstatfs` at the nearest existing folder, using FreeBSD's `struct statfs` (version `20030518`, as `native/disc_probe.c`), because the SDK's structure doesn't match. A measurement that fails or reads implausibly is not a number: the plan screen says "NO SE PUDO MEDIR", the log has the full measurement, and X then means "install anyway" (since 01.09). A drive that fills up during the download stops the install with its own message (`ENOSPC`), keeping what was downloaded.
5. **Files:** each one is created at its final size.
6. **Download on four threads,** each with its own `CdnClient`. Before a chunk is fetched, its bytes are read from the file: if their SHA-1 is already the chunk's, it is not fetched. So a paused or interrupted install **resumes without a journal**, and a folder with a damaged file is repaired by fetching only what changed.
7. **Verification:** each file's SHA-1 against the manifest.
8. **Executable:** the first Windows launch entry (`EligibleLaunches`). From the PE file it reads:
   - the architecture (x86 or x64);
   - whether it has **SteamStub**'s `.bind` section, a DRM OrbisDesk can't run.
   
   It also notes whether the game ships `steam_api.dll` or `steam_api64.dll`.
9. **Record:** `.orbisdesk-install.json` in the game's folder, written at the end and only when everything passed. It holds the app, its name, Steam's folder name, the depots and manifests, the executable, the architecture, and whether it has `steam_api` or SteamStub. An install deletes the previous record when it starts, so a half-updated folder isn't listed as installed.

**Folder:** `/data/orbisdesk/steam-games/<app>/`.

**During the download:** the screen shows the amount placed, the percentage, the finished files and the speed. O pauses the install, and what was downloaded stays in the folder.

## What goes to the log

Only counts, sizes and error categories. For example:
- `plan depots=N rejected=N os=N …`
- `install merged files=N chunks=N bytes=N`
- `install space ok=1 free=… need=… path=… fstatfs=… version=… bsize=… bavail=…`
- `install files=N verified=N failed=N fetched=N reused=N kib_s=N`
- `install exe pe=1 arch=x64 steamstub=0`

No app, depot, file or game names, because they would reveal which games the account owns. That data is only in the game folder's record and in `steam-library.txt`, which are not fetched from the console.

## PC tests (2026-11-07), without an account

A test program (not part of the title) uses S2's anonymous logon and calls `PlanInstall` and `RunInstall` on app 1007, *Steamworks SDK Redist*:

| Test | Result |
|---|---|
| Fresh install | 8 of 8 files verified, 24.3 MB fetched, 67.9 MB installed |
| Again on the same folder | 8 of 8, **0 bytes fetched**, 67.9 MB reused |
| With 4 bytes changed in one file | 8 of 8, only 443 KB fetched (the damaged chunk) |
| Paused after 4 s | `canceled=1`, 5.5 MB fetched, no record |
| Resume | 8 of 8, 13.6 MB reused and the rest fetched |
| Executable | `steamclient64.dll` reads as `x64` and `steamclient.dll` as `x86` |
| Several depots: app 228980, *Steamworks Common Redistributables* | 26 depots merged, 235 of 235 files verified, 1.4 GB in 168 s (8.2 MB/s on four threads; S2, on one, did about 3 MB/s on the PC) |

**Not tested:**
- SteamStub detection on an executable that has it;
- the list and an install with an account, which the user does on the console;
- writing to USB, left for the next version.

## How it is built

```sh
python3 tools/build-steam-s4.py --target host
python3 tools/build-steam-s4.py --target ps4 [--check]
```

- **Title:** ORBS00001, "OrbisDesk Steam", version 01.14. It installs over S3 01.07 and uses the same saved session.
- **Package:** `out/steam-s4/OrbisDesk-Steam-S4-01.14.pkg`, with its SHA-256 in `manifest.json`.
- **New Playden parts:** `cdn_client`, `depot_manifest`, `depot_chunk` and `game_path`, on top of S3's. Playden's own installer (`depot_installer.cpp`) is not used: it needs `src/installs`, which isn't among the downloaded files, and it reads folders with `readdir`, whose structure on the console isn't the SDK's.
- **Imports:** the check passes. The only ones outside `wine.elf` and `hardware.elf` are S2's six. `wine.elf` already imports `_fstatfs`.

## Accepting it on the console

1. Open 01.14. If S3's session is still saved, it signs in without a QR code.
2. Choose a small game with up and down, and press X.
3. Confirm with X on the plan screen and wait.
4. **Optional:** press O partway through, install again and check that it resumes.
5. Check the final screen: files verified, executable and architecture, `steam_api` and SteamStub.

`steam-client.txt` must end with `PWSTEAM client S4 result=pass` and contain `install done`.

If it fails:
- `plan none`: Steam doesn't grant the whole game, or there is no Windows content.
- `install access error=…`: the depot keys.
- `install space ok=1` with too little free: not enough space; `ok=0`: the measurement failed, and the same line shows how.
- `install chunk failed` or `failed=N`: the download.

## Console runs

**S4 01.08 (2026-11-07): the install stopped at the space check.** A copy of the log is in `reports/steam-s4-console/steam-client-0108.txt`.
- **What worked:**
  - `session load=none` and `session restore error=none`: the app opened without a QR code, which also closes S3's pending check;
  - the library (36 games);
  - for the chosen game (4 depots, 1,659 files, 4.3 GB): the plan, the keys of all 4 depots, the 11 servers and the manifests.
- **What failed:** `install space free=0 … need=4347052354`, and the install stopped with "no space". The console's storage screen showed about 149 GB free. 01.08 took any failed measurement as 0 and logged nothing about how it went.

**Changes in 01.09:**
- `MeasureFreeSpace` replaces `FreeBytes`:
  - it measures at the nearest existing folder;
  - it logs the path, `fstatfs`'s result and `errno`, and the structure's version, type, block size, blocks, `bfree` and `bavail`, plus the raw start when the values aren't plausible;
  - it returns "not measured" instead of 0.
- With no measurement, the plan screen says so and X installs anyway. A full drive during the download (`ENOSPC`) stops the install with its own message.

**S4 01.09 (2026-11-07): free space still not measured; the user installed anyway.** A copy of the log is in `reports/steam-s4-console/steam-client-0109.txt`.
- The plan screen said "NO SE PUDO MEDIR", and the user chose to install anyway (`install start unmeasured_ok=1`). The game (3 depots, 3,698 files, 12.8 GB installed, 7.5 GB to download) started downloading.
- **Cause:** `MeasureFreeSpace` looked for the nearest existing folder with `access()`, and in this title's libc `access()` fails for every path. It climbed to `/` while the install was writing in the game's folder, and `fstatfs("/")` then failed with `EPERM` (`fstatfs=0xffffffff errno=1`). So there is still no reading of `/data` itself.
- **The same failure explains two other things:**
  - S3 and S4 showed their notice on every run (`notice saved=1` each time);
  - `Installed()` never saw a record, so the list never said "INSTALADO".

  Resuming didn't depend on it, because it compares each chunk with the file.

**Changes in 01.10:**
- `orbisdesk::PathExists` opens the path read-only, and replaces `access()` in the space measurement, in `Installed()` and in the notice check.
- A `fs probe path=… access=… errno=… open=…` line records once what `access()` returns on the data folder, which exists.
- `steam_s3.cpp` keeps `access()`, as it was accepted. 01.10 replaces it on the console.

**S4 01.10 (2026-11-07): `access()` fixed; the sandbox refuses `fstatfs`.** A copy of the log is in `reports/steam-s4-console/steam-client-0110.txt`.
- `fs probe … access=-1 errno=1 open=1`: in this title `access()` answers `EPERM`, and opening works. The notice now appears once (`notice already_accepted=1`), and the free-space search stops at `/data/orbisdesk/steam-games`.
- `fstatfs` on that folder also fails with `EPERM`. It isn't only `/`: the sandbox refuses `fstatfs` to this title.
- The chosen game showed `download_bytes=0`. That is how the appinfo reads: some depots don't list a download size, and Playden's `DepotBytes` adds 0 for those. From 01.12 the screen says "STEAM NO LA INDICA" instead of 0 MB.
- 01.10 overwrote the 01.09 log, so whether the first Portal 2 install reached `install done` is not known.

**Changes in 01.12:**
- If `fstatfs` fails, two more measurements are tried, each logged on its own `plan space` line:
  - `statfs` by path (FreeBSD 9 syscall 396) on the folder, on `/data/orbisdesk` and on `/data`;
  - `getfsstat` (syscall 395), choosing the mount whose `f_mntonname` is the longest prefix of the folder.

  Both are raw syscalls, as `native/disc_probe.c` makes them; the SDK has no wrapper for them. The jailbreak route (GoldHEN's `sys_sdk_cmd`) is not used. "NO SE PUDO MEDIR" with "install anyway" stays as the fallback.
- The previous run's log is kept as `steam-client.prev.txt`.

**S4 01.12 (2026-11-07): no free-space method is allowed; Portal 2 was all on disk.** Copies of the logs are in `reports/steam-s4-console/0112-steam-client.txt` and `0112-steam-client.prev.txt`.
- `fstatfs`, `statfs` (on the folder, `/data/orbisdesk` and `/data`) and `getfsstat` all fail with `errno=1` (`EPERM`). The sandbox doesn't let this title measure free space by any of the three. "NO SE PUDO MEDIR" with "install anyway" stays. The jailbreak route is a decision for the user.
- Portal 2 (`present=12759257499 need=0`): every file was already at its full size. Installing again read and checked its 15,427 chunks against the disk, but the screen looked like a new download.

**Changes in 01.14:**
- The progress screen says **"VERIFICANDO LO QUE YA ESTA EN LA CONSOLA"** while chunks are only found in place, and **"DESCARGANDO DE STEAM"** when something was fetched in the last 3 seconds. It shows what was already correct and what was fetched now, separately; the speed appears only while fetching.
- A `install progress files=N/M reused=… fetched=… failed=…` line every 250 files.
- A file all of whose chunks were found in place, matching their SHA-1, is no longer read a second time for its whole-file SHA-1: the chunks cover it end to end, so its bytes are already checked. Only files with a chunk written in this run are hashed whole (`rehashed=N` in the final line). On the PC, checking the 1007 install again went from 3.2 s to 1.7 s.
