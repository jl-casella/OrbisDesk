# The Steam client inside OrbisDesk

[English](STEAM_HOSTED.md) | [Español](STEAM_HOSTED-es.md)

The Steam client of [S1–S5](STEAM_S5.md) used to be a title of its own (ORBS00001). This change puts it inside OrbisDesk's title (ORBW00002), as the user asked: **"Open Steam Client"** in the Start menu, right above "Exit desktop", and a Desktop link with the same name. Either one switches the screen to the Steam UI, and leaving the client returns to the same running desktop. The UI is in English. With this, OrbisDesk's package becomes GPL-3.0-or-later (the user's decision).

**Status, 2026-11-10:** the client is integrated into OrbisDesk's title and its complete hosted product recipe (`build-steam-deps.py --target ps4`, then `build-steam-hosted.py`). It is part of the W303 product base. Login, downloads and game launching require their own evidence for the integrated client; neither successful packaging nor clean-install desktop acceptance establishes those flows. The standalone ORBS00001 remains buildable through `tools/build-steam-s4.py` as a separate diagnostic path. See [current state](CURRENT_STATE.md).

## How it fits in the title

| Part | Where | What it does |
|---|---|---|
| Screen | `native/steam/steam_ui.c`, `STEAM_UI_HOSTED` | No VideoOut of its own. The sink calls `pw_hw_steam_draw(target, pitch, 1280, 720)` for each frame, just before the control overlay; while the client is open, it draws its page over the whole frame. Each new page asks the sink for a frame (`pw_hw_cursor_moved`). |
| Pad | same file | `native/hw_pad.c` calls `pw_hw_steam_pad(&data)` with each read, next to the overlay's hook. While the client is open it takes X, O, triangle, up and down, and the desktop reads the pad as neutral. After closing, it keeps the pad until every button is up. |
| Opening | `native/steam/steam_client.cpp`, `pw_hw_steam_open()` | Starts the client on a thread of its own (2 MB stack) and returns `opened`, or `busy` if it is already open. When the client ends, it closes its screen and the desktop comes back. |
| Request | `native/steam/orbis_steam_open.c` → `C:\orbis\steam-open.exe` | A 64-bit guest that sends `<steam-open>` through the same channel as kernelbase's overlay closer: xinput1_3's Unix library, call 3. `native/hw_pad.c` answers in the same buffer. |
| Start menu | `tools/build-explorer-hw.py` | `MENU_ID_STEAM` between the separator and "Exit desktop", with its own glyph. It opens `C:\orbis\steam-open.exe`. |
| Desktop | `C:\users\orbis\Desktop\Open Steam Client.lnk` | The same helper, written in `tools/make-start-menu.py`'s format. Wine's explorer leaves out a Desktop link with no icon (`programs/explorer/desktop.c`, `add_launcher`), and W289's helper had none, so the link didn't show. Since SH1's rebuild of 2026-11-08 the helper carries an icon resource: the Start menu glyph's blue disc with a white hub, drawn by the builder at 16, 32 and 48 pixels and linked with `windres`. |
| Files | `C:\orbis\steam\` | `cacert.pem`, gbe_fork's DLLs (`gbe-x86-steam_api.dll`, `gbe-x64-steam_api64.dll`), their LGPL-3.0 text and `gbe-SOURCE.txt`. |
| Data | `/data/orbisdesk/steam`, `/data/orbisdesk/steam-games` | The same as the standalone title: saved session, library, games. The log is still `/data/orbisdesk/steam-client.txt`, with `PWSTEAM client hosted …` lines. |

**Inside the title the client can't use what it used in ORBS00001,** so the build changes four things:
- **C++:** compiled with clang-19 against `~/vk-h0/sysroot`'s libc++ 21 and its libc overlay (`libc-overlay-wine`), the same libc++ the hardware ELF links. The SDK's libc++ 11, used by the standalone title, has a different ABI. `__PS4__` keeps that libc++ off its FreeBSD paths, as when it was built (`upstream/DolphinPS4/toolchain/env.sh`).
- **Sockets:** Wine wraps `setsockopt` and translates Linux TCP option numbers itself (`platform/ps4/pw_wine_sockopt.c`). With `STEAM_UI_HOSTED`, `native/steam/orbis/orbis_net_fix.h` leaves `TCP_KEEPIDLE`/`INTVL`/`CNT` as Linux numbers, so they aren't translated twice, and curl is rebuilt that way.
- **Clocks:** only the Steam objects get their `clock_gettime`/`clock_getres` renamed, to `orbis_clock.c`'s `pw_steam_*` (`objcopy --redefine-sym`). A global `--wrap` would also touch Wine's and Mesa's calls, which already use FreeBSD's numbers.
- **Network:** Wine has already called `sceNetInit`, and a second call returns an error. Playden patch `0003-shared-net-init.patch` asks the host, and inside the title the answer is "already running".

**Symbols:** the object (`build/steam-hosted/steam_client_hosted.o`, 4.2 MB with no DWARF) has four strong global symbols, `pw_hw_steam_open`, `_draw`, `_pad` and `_active`; every other strong symbol is local, so it can't clash with Wine, Mesa or zlib. The weak symbols stay weak and global: they are the COMDAT copies of inline and template functions, compiled from the same libc++ 21 headers as the title's libc++, and the link keeps one copy of each. The first build made them local too, and W289's link failed: the object's local copy won each COMDAT group, libc++-vk.a's copy was discarded, and libc++'s own objects pointed into a discarded section (`R_X86_64_PC32 out of range`, 340 errors). The builder now fails if any weak symbol is a C name, apart from the two clang emits in every C++ object (`DW.ref.__gxx_personality_v0`, `__clang_call_terminate`). The builder checks that every symbol it needs is defined or imported by the newest `wine.elf`, or provided by the title's static libraries (its libc, libm, libc++, libc++abi, compiler-rt). The only new imports are `sceNetRecv` and `sceNetResolverAbort`, which S2 already proved on the console, plus `pw_hw_root_mode` (weak: the client links without it).

## ROOT mode and free space

`pw_hw_root_mode()` (staged patch for `native/wine_hardware.c`) returns whether GoldHEN's jailbreak is on, and the client logs it. Free space is measured the same way in both modes (`fstatfs`, `statfs`, `getfsstat`; see [STEAM_S4.md](STEAM_S4.md)). In NORMAL mode the sandbox refuses all three (S4 01.12). **Whether they work in ROOT mode is not known yet.** W228 calls `setuid` back to the app's uid right after the jailbreak but stays out of the prison; the console run will tell. If the space still can't be measured, "COULD NOT BE MEASURED" with "install anyway" remains.

## Build

```sh
python3 tools/build-steam-deps.py --target ps4      # once
python3 tools/build-steam-hosted.py
```

Outputs, in `build/steam-hosted/`:
- `steam_client_hosted.o`;
- `prefix/` (files for `drive_c`);
- `manifest.json` (hashes, the `wine.elf` it was checked against, new imports).

`joined.o` keeps the DWARF for reading crash addresses.

## Patches for OrbisDesk's shared files

They are staged for the build session, which integrates and builds. They apply with `git apply --check` on the current tree:
- `steam-hosted-native.patch`:
  - `native/hw_pad.c`: the `<steam-open>` request and `pw_hw_steam_pad` next to the overlay;
  - `platform/ps4/pw_wine_sink_ps4.c`: `pw_hw_steam_draw` before the overlay;
  - `native/wine_hardware.c`: `pw_hw_root_mode`.
- `steam-hosted-tools.patch`:
  - `tools/build-wine-hardware.py`: the object in the link and the prefix files;
  - `tools/build-explorer-hw.py`: the Start menu item.

## PC tests (2026-11-07)

- `tools/build-steam-hosted.py` compiles everything with the title's toolchain, and the symbol check passes against `build/wine-hardware-w288/wine.elf`.
- **Trial link:** the object, with a stub `pw_hw_cursor_moved` and the title's libraries (crt1, libc++-vk, libc++abi-vk, libc, libm, libunwind, libkernel, libSceNet, compiler-rt), links with `--no-undefined` and W289's `link.x` (base `0x1100000000`), with libc++'s locale, thread and system_error objects pulled in. The first trial used the SDK's `link.x`, whose base 0 hid W289's error; with W289's script it reproduced the error, and it passes with the fixed object.
- **Pages:** the hosted renderer drew the library and QR pages into a 1280x720 frame with a 1344-pixel pitch. Both read well, and the QR fills two thirds of the height.
- **Not tested** (console only): the hosted thread, the sink and pad hooks, the helper's request, the Start menu item, and the client's coexistence with running guests (memory, threads, the shared malloc lock).

## First console run (W289, reported by the build session)

- Start menu → "Open Steam Client" opened the hosted client, and leaving it returned to the desktop.
- The Desktop link didn't show, because the helper had no icon (see the table). The fix waits for the next hardware build.
- The Portal 2 run used the game's own `steam_api.dll`: no log has an `emu enable` line, because the emulator wasn't switched on with triangle on the game's page. This is not yet a test of the gbe_fork switch.

## W291: the emulator switch

The user pressed triangle on Portal 2's page and the switch "didn't work" (`reports/wine-hardware-w291/physical/manual-20261108T033824Z/`, `run-0002.log` and `steam-client.txt`). The client log stops at `PWSTEAM emu enable dll=x86 interfaces=30`: the switch never logged `done`, a failure or `ok=`. The title kept running, and its log ends about 15 s later, when the user closed it.

What the evidence shows, and what it doesn't:
- **Not a crash or a wait on another thread:** the client thread was still inside `EnableEmulator` after its first DLL. That line was printed once per DLL, at the end of its steps (copy, interfaces, settings files). What followed is either a second `steam_api*.dll` of the game, or the marker write.
- **No feedback:** the game page stayed on screen, unchanged, through the whole switch.
- **A slow step:** `steam_interfaces.txt` came from 37 `std::regex` scans of the game's DLL. On the PC, with libc++ (the title's), they take 20 s for gbe_fork's 9 MB `steam_api.dll`; the literal search takes 18 ms, with the same output. The PS4 is slower than the PC. How long the scan took on the console, and how many Steam API DLLs Portal 2 has, isn't in the log. The new trace lines will show both.

The change, in the hosted object (and the standalone title's sources):
- `SteamInterfaces` searches for each literal and reads the digits after it, in the same order and with the same SteamClient017 rule. It matches the old regex output on gbe_fork's x86 and x64 DLLs and on 3000 random inputs built from the patterns' pieces.
- The page switches to "TURNING ON THE EMULATOR..." or "RESTORING THE ORIGINAL STEAM API..." as soon as triangle is pressed.
- Each step is logged with the milliseconds since the press: `start dlls=N`, then per DLL `dll=i/N step=read arch= game_bytes= emulator_bytes=`, `copied` (or `already_emulator`), `interfaces lines=` and `settings`, then `done dlls= entries=`, then `emu enable ok=` and `emu page back`. DLLs are numbered rather than named, since a path can name the game.

## Library tabs

The library list has three tabs: **ALL**, **INSTALLED** and **NOT INSTALLED**. A line under the title shows them with each tab's count, and the active tab is drawn in the accent color (blue). W292 put it in brackets, but the font has no brackets, so they showed as blanks. R1 moves to the next tab and L1 to the previous one. The user asked for R1 and R2, but R2 is a trigger, so the pair is L1/R1. L2 and R2 do the same (their digital press), so either pair works. A tab change keeps the selected game when the new tab lists it, and the lists are read again for every page, so a finished install moves its game across. Log: `PWSTEAM library tab=N games=M`. Host builds read `l` and `r` from stdin.

## Content language

Many games keep each language's files in depots of their own. Until now every install chose English: the four `language` rejections in `PWSTEAM plan depots=…` lines are those depots. **Square** on an installed game's page opens **LANGUAGE**. It lists the languages the game's own depots carry (Playden's `SelectionResult::languages`), with the installed one marked. X on one plans the install again in that language, through Playden's `SelectDepots`, and shows the usual install page with `LANGUAGE: SPANISH (INSTALLED NOW: ENGLISH)`. X there runs the install:
- the new language's depots are downloaded;
- every file already in place with the right SHA-1 is kept, as in any verification;
- files that both languages carry are replaced by the new language's.

Files only the old language's depots had stay in the folder, and the page says so. The record's `language` becomes the new one only once everything passed. From then on, X ("verify and update") plans in the record's language, not English. A paused or failed install has no record (`RunInstall` removes it when it starts), so `.orbisdesk-language.txt` in the game's folder keeps the language being installed, and the next install resumes in it. A game with fewer than two languages says that Steam has no language packs for it, and that its languages, if any, are chosen inside the game.

**What the game reads:**
- **The Steam API, through gbe_fork:** gbe_fork answers both `SteamApps()->GetCurrentGameLanguage()` and `SteamUtils()->GetSteamUILanguage()` with `language=` from `steam_settings/configs.user.ini`, beside its DLL (`dll/steam_apps.cpp`, `dll/steam_utils.cpp`, `dll/settings_parser.cpp` of release-2026_09_27). When the emulator is on, an install restores the game's DLLs first and turns the emulator back on at the end, with the language just installed. With the game's own `steam_api.dll` the language comes from Steam, which isn't running inside OrbisDesk.
- **Source engine games:** their interface language comes from `-language <name>` on the command line; without it, it follows Steam's interface language. Community reports say `-language` works in Half-Life 2, Portal and Portal 2. The shortcut of a game installed in another language than English gets `-language <name>` when its executable has `bin/engine.dll` beside it and Steam's launch entry doesn't already choose one. Audio follows the game's content language, which is `GetCurrentGameLanguage`.
- **The registry:** the client doesn't write `HKCU\Software\Valve\Steam\Language`. The registry belongs to the `wineserver` while the title runs: it keeps the registry in memory and saves it back to `user.reg`, so a native write to that file would be lost or overwritten. Whether Portal 2 reads that key isn't known. If `-language` and gbe_fork aren't enough, a launcher that sets the key from inside Wine before starting the game is the next step.
- Other games may take the language from a setting of their own. Nothing is set for those.

**W292 on the console:**
- The Triangle switch took 922 ms, and restoring worked.
- The tabs worked.
- Spanish installed: 686 MB fetched, 3706 files verified.
- With the emulator on, Portal 2 loaded gbe_fork's `steam_api.dll` but stayed in English.
- Two causes are possible, and both are now covered:
  - **A left-over `configs.user.ini`.** W291's interrupted switch had written `bin/steam_settings/` files and stopped before its record. Every later switch counted them as the game's own files and didn't touch them, so `language=english` could have stayed. W292's counts fit: 2 DLLs and 5 record entries, so 3 files and no folder. The switch now sets `language=` in a `configs.user.ini` that is already there, and keeps every other line of it. It logs `step=language file=new|existing state=same|updated language=…`. Seven `configs.user.ini` shapes were checked on the PC, including CRLF lines and a missing section.
  - **Source taking its interface language from the command line:** the `-language` argument above.
- The shortcut gets its arguments when an install or a verification ends. For Portal 2 as installed in W292, that means X on its page (it fetches nothing) or choosing the language again.

**The Steam language** (square on the library list) is the language new installs ask for, as Steam's own setting does. It is saved in `/data/orbisdesk/steam/steam-language.txt`, it is English until changed, and it is shown in the library's title. A game that doesn't carry it installs in English, else in its first language, and the install page says it isn't offered. An installed game keeps its own language: square on its page changes it. The list is Steam's API language codes.

**Language names on screen** are each language's own name, as Steam's language list gives it: ESPAÑOL - ESPAÑA, ESPAÑOL - LATINOAMÉRICA, FRANÇAIS, PORTUGUÊS - BRASIL, ČEŠTINA, ROMÂNĂ, TÜRKÇE, and so on. `steam_ui.c` draws UTF-8:
- a letter of Latin-1 with a mark, or Ă, Č or Š, is `hw_text.h`'s capital with a two-row mark above it, in the line's spacing (a line is 10 rows, a letter 7); the cedilla goes below;
- lower case is drawn as upper case;
- any other non-ASCII character takes no room.

The selection bar now also covers the marks. Languages whose script the font lacks keep their English name: Russian, Bulgarian, Greek, Ukrainian, Arabic, Thai, Vietnamese, Japanese, Korean and both Chinese. Logs keep Steam's codes. Game names with accented letters now show them too. The language list was drawn on the PC in a 1280x720 frame with a 1344-pixel pitch.

Log lines:
- `PWSTEAM language page carried=N installed=…`
- `PWSTEAM language chosen=… installed=…`
- `PWSTEAM plan … language=… asked=… carried=N`
- `PWSTEAM plan resume_language=…`
- `PWSTEAM plan steam_language=…`
- `PWSTEAM steam_language set=… saved=…`
- `PWSTEAM install start … language=… installed_language=…`
- `PWSTEAM shortcut … language_args=…`
- `PWSTEAM emu enable dll=i step=language …`

Language names are Steam's, and they are not account data. If Steam doesn't carry the chosen language for this account, nothing is installed and the page says so (`language unavailable`).

## Uninstall

Requested on 2026-11-08. The build session had deleted `steam-games/19680` (Alice: Madness Returns, SteamStub, about 8.9 GB) by FTP because the client had no way to do it. Now **OPTIONS** on an installed game's page opens an UNINSTALL page.

- **Confirmation:** the page shows the size and the folder, and an amber warning. It says the folder and the game's shortcuts are deleted and that the step can't be undone: the game has to be downloaded again. It also says saves kept in the game's own folder go with it. X uninstalls; O keeps the game.
- **Removal order:** everything in `steam-games/<app>` is deleted first, then the install record `.orbisdesk-install.json`, then the folder itself. When a removal stops partway, the record is still there. The game still shows as installed, its page still opens, and OPTIONS can try again.
- **Links are never followed:** each entry is opened with `O_DIRECTORY | O_NOFOLLOW`. A folder is emptied and removed, and anything else, a symbolic link included, is unlinked. Nothing outside the game's folder is touched. `stat()` is not used, because the SDK's `struct stat` is not the kernel's.
- **Shortcuts:** they are removed only after the folder is gone. The client deletes the `.lnk` that `WriteGameShortcuts` made on the Desktop and in Start → Programs → Steam, but only when its target is inside `Z:\orbisdesk\steam-games\<app>\`. A `.lnk` with the same name that points elsewhere belongs to the user and stays.
- **Result page:** it shows the number of files and folders deleted and each shortcut's state. On a failure it says how many items could not be deleted, plus the first path and its errno. That path goes on screen only, never in the log, since a game's file names can name the game.
- **Log:**
  - `PWSTEAM uninstall page app=N`, then `canceled` or `confirmed bytes=`
  - `PWSTEAM uninstall remove start record=1`
  - `PWSTEAM uninstall remove ok= files= folders= failures= errno=`
  - `PWSTEAM uninstall done ok= ms= shortcuts_prefix= desktop=removed|absent|not_ours|unreadable|failed|kept start=… shortcut_errno=`
- **PC test** (WSL, against the S4 host objects; all checks pass):
  - a tree with nested folders and a link to a folder outside the game is removed, and the outside folder is intact;
  - a folder that can't be emptied (mode 555) fails with errno 13 and keeps the record, and a second try after fixing the mode removes everything;
  - this game's `.lnk` is deleted, a same-named `.lnk` pointing elsewhere is kept, and a second removal reports `absent`.

A paused or failed download (a folder without a record) still has no way to be removed. The game shows as not installed, so its page doesn't open.

## Fixed footer

The user asked for the buttons' help and the status to stay at the bottom of the screen, as in Crema, so they don't move when the list changes length (switching tabs with L1/R1, for example).

- **Footer marker:** a page line that starts with `STEAM_UI_FOOTER` (byte 0x02) begins the footer. That line and every line after it go in a dark band with a blue rule above it.
- **Fixed band:** the band is four body lines tall on every page, so it starts at the same height on all of them (y=548 of 720 hosted). Only a footer longer than four lines makes it taller.
- **Body:** the text above is cut where the band starts, and a line that wouldn't fit whole isn't drawn. Every page's button line moved into the footer.
- **Library:** the footer holds "GAME n OF m" and the Steam language, then (hosted) "CLOSE RUNNING GAMES BEFORE INSTALLING.", then the buttons. The title is just "STEAM LIBRARY". The list keeps 11 rows. Each row is cut to one line: a name longer than 36 characters becomes 33 plus "...", so a long name no longer wraps and pushes the rows down. Up and down have no hint.
- **Language lists:** the lists keep 9 rows. That fits under the Steam-language heading at 1280x720. "n OF m" is in the footer.
- **Warnings:** `STEAM_UI_WARN` (byte 0x03) draws a line in amber. It is used for SteamStub, for the uninstall warning, for a failed removal, for "no shortcut" and for unmeasured free space.
- **SteamStub:** the user missed W293's "HAS STEAMSTUB DRM" line on Alice. SteamStub is now the first line under the game's name, in amber, on the game page and on the install result. When it is the reason no shortcut was made, the shortcut line says so (`skipped=steamstub` in the log). Any other reason is shown as well.
- **Accent:** `STEAM_UI_ACCENT` (byte 0x04) switches the letters to the accent color and back. The library's active tab uses it.
- **Wording:** the font has no comma or apostrophe, so the new pages' texts avoid both. "NEW LANGUAGE'S FILES" now reads "FILES OF THE NEW LANGUAGE".
- **PC renders at 1280x720 and 1920x1080:** the library on ALL with 11 rows and on INSTALLED with 2, the Alice game page with SteamStub, and the uninstall confirmation. The band starts at the same place in all of them.

## Sign-out confirmation

The user signed out by mistake with a stray triangle press, and asked for a confirmation like the one before uninstalling (2026-11-08).

- **Where:** triangle in the library, and triangle on the "COULD NOT LOAD THE LIBRARY" page.
- **What it shows:** a "SIGN OUT" page. Its amber line says the saved session is deleted from the console and that the next use needs a new sign-in with the Steam app. It also says installed games and their shortcuts stay.
- **Buttons:** the footer says "X: SIGN OUT     O: STAY SIGNED IN". Only X deletes the session. O goes back to the library, or exits from the error page, and the session stays.
- **Log:** `PWSTEAM sign_out page`, then `PWSTEAM sign_out confirmed` or `PWSTEAM sign_out canceled`. After a confirmation, `PWSTEAM signed_out=1` as before.
- **Hosted object:** `996b4549fb97fc183589531343d52f335978c4ead8f7a8bb3be43d9da637c9f8`, checked against W297's `wine.elf` with no new imports. It also trial-links with W297's `link.x`. Not yet run on the console.

## SteamStub before the download

W293 brought Alice: Madness Returns (8.9 GB) and BioShock down whole before the post-install check found SteamStub's `.bind` section. The user then had to uninstall them. A new or resumed install now checks first (2026-11-08):

- **What is fetched:** the depot keys and manifests, as the install fetches them, then only the chunks under each listed executable's headers and section table. That is the first chunk as a rule, up to 1 MB per executable. At most four distinct executables from Steam's launch entries are checked. Nothing is written to disk.
- **What counts as SteamStub:** as when the shortcut is made, every executable that reads as a PE has `.bind`. A section table that can't be read leaves it unknown, never "no SteamStub".
- **With SteamStub:** a "STEAMSTUB DRM" page with an amber line and the size the full install would take. The footer says "O: DO NOT INSTALL     OPTIONS: INSTALL ANYWAY". O returns to the library with nothing written. OPTIONS goes on to the usual install page, which then carries an amber SteamStub line.
- **Without it:** the usual install page. The install reuses the precheck's keys, servers and manifests, and writes its chunks in place once the files are sized. The workers find them there (their SHA-1 matches) and don't fetch them again.
- **When it can't run** (no keys, no servers, a chunk that can't be fetched): the install page says so on an amber line, and the install checks the executable afterwards as before.
- **Not checked:** an installed game being verified, updated or changing language. Its record already says whether it has SteamStub.
- **Detection only.** Nothing here removes SteamStub or works around it.
- **Log:** `PWSTEAM precheck entry=N pe= arch= steamstub= chunks=`, then `PWSTEAM precheck app= exe= pe= steamstub=0|1 fetched= ms=`, `PWSTEAM precheck answer=back|install_anyway`, and on the install `PWSTEAM install from_precheck=1` and `PWSTEAM install prefetched=N of=M`.
- **PC test:** PE images cut into chunks give the same machine and `.bind` as the whole image. Only the chunks under the headers and table are asked for (2 of 4096 for a 1 MB image in 256-byte chunks). A table that crosses a chunk boundary is read. A chunk that can't be fetched reads as "not a PE", not as "no SteamStub". Windows' `notepad.exe` (x64 and x86) and `cmd.exe` read the same through chunks as whole.
- **Still to check on the console:** Alice (19680) and BioShock (7670) should give `steamstub=1` without the full download, and Portal (400) should give `steamstub=0`.

## Device name

Steam Guard showed the client's sign-ins as "Playden (PS5)". Playden patch `0004-device-name-steamdesk.patch` changes every name sent to Steam:
- the device name of the QR and password sign-ins (`device_friendly_name`) is "SteamDesk (PS4)";
- the CM logon's machine name, and Steam Cloud's batch machine name (not used by this client), are "SteamDesk";
- the HTTP `User-Agent` is "SteamDesk/1.0".

The machine id doesn't change, so a saved session keeps working. Steam may keep showing the old name for a session made before this change until the next sign-in.

## Accepting it on the console

1. Start menu → "Open Steam Client" shows the English UI.
2. The library, an install and the gbe_fork switch work.
3. In ROOT mode, the plan shows a measured free space.
4. O in the library returns to the same desktop, with its windows as they were.
