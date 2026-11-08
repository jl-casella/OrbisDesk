# S4: install a game from the library

[English](STEAM_S4.md) | [Español](STEAM_S4-es.md)

This is the fourth phase of the Steam client. S3, the QR sign-in, is in [STEAM_S3.md](STEAM_S3.md). The app now lists the account's games that have Windows content and can install one on the console.

**Status:** the 01.08 PKG is built. On the PC the installer was tested without an account, using anonymous downloads: installing, resuming, repairing a file and pausing. The list and an install with the user's account **have not been tested on the console yet**.

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
4. **Space:** whatever is already in the folder counts, and at least 512 MB must stay free. On the console, free space is read with the kernel's `fstatfs`, using FreeBSD 9's structure (as `native/disc_probe.c` does), because the SDK's structure doesn't match.
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
- `install space free=… need=…`
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

- **Title:** ORBS00001, "OrbisDesk Steam", version 01.08. It installs over S3 01.07 and uses the same saved session.
- **Package:** `out/steam-s4/OrbisDesk-Steam-S4-01.08.pkg`, with its SHA-256 in `manifest.json`.
- **New Playden parts:** `cdn_client`, `depot_manifest`, `depot_chunk` and `game_path`, on top of S3's. Playden's own installer (`depot_installer.cpp`) is not used: it needs `src/installs`, which isn't among the downloaded files, and it reads folders with `readdir`, whose structure on the console isn't the SDK's.
- **Imports:** the check passes. The only ones outside `wine.elf` and `hardware.elf` are S2's six. `wine.elf` already imports `_fstatfs`.

## Accepting it on the console

1. Open 01.08. If S3's session is still saved, it signs in without a QR code.
2. Choose a small game with up and down, and press X.
3. Confirm with X on the plan screen and wait.
4. **Optional:** press O partway through, install again and check that it resumes.
5. Check the final screen: files verified, executable and architecture, `steam_api` and SteamStub.

`steam-client.txt` must end with `PWSTEAM client S4 result=pass` and contain `install done`.

If it fails:
- `plan none`: Steam doesn't grant the whole game, or there is no Windows content.
- `install access error=…`: the depot keys.
- `install space`: not enough space.
- `install chunk failed` or `failed=N`: the download.
