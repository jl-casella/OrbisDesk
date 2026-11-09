# S5: launching an installed game from OrbisDesk's Explorer (in progress)

[English](STEAM_S5.md) | [Español](STEAM_S5-es.md)

The goal agreed with the user: a game downloaded by the Steam title (ORBS00001), such as Portal or Portal 2, starts inside OrbisDesk's Explorer. The Steam client stays a separate title for now. Integrating it into OrbisDesk, and the license question that comes with it (GPL-3 for the combined package), is decided later.

**Status:** the Steam side is in the 01.14 PKG: launch data and shortcuts since 01.11, and the per-game gbe_fork switch in 01.13 (the installer is in [STEAM_S4.md](STEAM_S4.md)). Nothing of S5 has run on the console yet.

## Steam side, 01.11

- **Install record, `format: 2`** (`/data/orbisdesk/steam-games/<app>/.orbisdesk-install.json`). For each Windows launch entry Steam declares, it holds:
  - `executable`;
  - `arguments`, as Windows command-line text;
  - `working_dir`;
  - `description` and `type`;
  - `present`, `pe`, `arch` (x86/x64) and `steamstub`.
  
  It also holds `steam_api_paths`. Paths are written in the case the files have on disk: appinfo's case can differ from the depots', and the console's file system is case-sensitive.
- **Shortcuts** (`native/steam/steam_shortcut.cpp`). After a successful install, a `.lnk` goes to two places:
  - `/data/wine-prefix/drive_c/users/orbis/Desktop/<game>.lnk`;
  - `/data/wine-prefix/drive_c/ProgramData/Microsoft/Windows/Start Menu/Programs/Steam/<game>.lnk`.
  
  The target is `Z:\orbisdesk\steam-games\<app>\<exe>`, with its working folder and arguments. Z: is `/data` in OrbisDesk's prefix (`platform/ps4/pw_wine_fs.c`). Explorer already shows the `.lnk` files of those folders (W045, W168, W169). The bytes are exactly what `tools/make-start-menu.py` writes; a test compared both, including non-ASCII names.
  
  Without `/data/wine-prefix/drive_c` nothing is written, and the log says so. An entry with SteamStub, or one that isn't a PE, is skipped. The log carries only flags (`shortcut prefix=… desktop=… start=…`), never the game's name.

## OrbisDesk side, staged for its maintainer

- **The `Z:` patch** for `windows_unix_path` in `native/wine_hardware.c`. The launcher's path conversion knows C:, D: to K: and L:, but not Z:. Without it, a relaunch through `next.txt` or `launch.txt` of a 32-bit game on Z: can't read its PE machine, so it doesn't get `--wow64-cpu` or `PW_PROGRAM_DIR`. A double-click inside Explorer doesn't go through that function.
- **Not known yet:** whether OrbisDesk's process can read files the Steam title wrote (folders 0777, files 0644), and whether a new desktop icon appears without a restart. Both need the console.

## gbe_fork, 01.13

Without the Steam client, a game's own `steam_api.dll` closes the game or asks for Steam. gbe_fork (LGPL-3.0) answers the game in its place. The user approved the download on 2026-11-07:

| File | Bytes | SHA-256 |
|---|---|---|
| `emu-win-release-vs22.7z`, release `release-2026_09_27` from github.com/Detanup01/gbe_fork | 13,455,496 | `300186c34f49a9ea75b33ce2af299267cc1dad0225cf45e81a229578d4e11c85` |
| `gbe_fork-release-2026_09_27-source.tar.gz`, that tag's source | 8,559,653 | `ce3ce7aee0439f1b7aff2404106fe68184185a8d0b7ca5ab2677a046ea464cbd` |

Both are in `.deps/steam/downloads/gbe_fork-2026_09_27/`, which isn't committed.

- **What goes in the title:** the builder checks both hashes and takes the two unmodified regular builds, `release/regular/x86/steam_api.dll` and `release/regular/x64/steam_api64.dll`, together with the LGPL-3.0 text and a `gbe-SOURCE.txt` with both addresses and hashes. They go flat in `/app0/assets/misc/` (`gbe-x86-steam_api.dll`, `gbe-x64-steam_api64.dll`), because `create-gp4` declares no folders there. The PKG grows to 27.5 MB.
- **Per game, from the Steam title** (`native/steam/steam_emu.cpp`): in the list, X on an installed game opens its page. Triangle turns the emulator on or off. Turning it on does this, for each path in the record's `steam_api_paths`:
  1. the game's DLL is renamed to `.orig`;
  2. gbe_fork's DLL of the same name is copied in;
  3. `steam_settings/` gets `steam_appid.txt`, `configs.user.ini` and `steam_interfaces.txt`.
     - `configs.user.ini` holds the generic player name "OrbisDesk" and the install's language, with no account data.
     - `steam_interfaces.txt` comes from gbe_fork's `generate_interfaces`, ported to C++ with the same patterns and the same SteamClient017 rule. Each pattern is a literal, most followed by `\d+`, so since 2026-11-08 the port searches for the literal instead of using `std::regex` (see [STEAM_HOSTED.md](STEAM_HOSTED.md)).
  
  `.orbisdesk-gbe.txt` lists exactly what was written. Restoring deletes that and renames the `.orig` files back. A file of the same name the game shipped is never touched.
- **Verifying a game with the emulator on** first puts the original DLLs back, then verifies, then turns the emulator on again. Otherwise the verification would replace gbe_fork's DLL with Steam's.
- **A `.orig` left by an interrupted run is accepted only in two cases:** it equals the DLL beside it, or the DLL beside it is gbe_fork's. Otherwise nothing is touched, and the page says so.

**PC tests:** with fake originals carrying 2011-era interface names, 27 checks passed:
- turning it on and off, for x86 and x64;
- the generated interface list against the expected one;
- a second "on", which changes nothing;
- a file of the game's own in `steam_settings/`, which is kept;
- the three `.orig` cases.

**Not tested:** a real game. That needs the console, with Portal or Portal 2 and the record v2 from 01.11 or later.
