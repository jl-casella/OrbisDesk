# Steam Big Picture

[English](STEAM_BIG_PICTURE.md) | [Español](STEAM_BIG_PICTURE-es.md)

**Status, 2026-11-24: implemented in the working tree, not built into a package and not tested on a console.** The screens were drawn on the PC from made-up data and compared with the approved mockups; the host tests below pass. Nothing about sign-in, downloads, Play, mode switching or covers has been observed on hardware yet.

Big Picture is a controller UI for OrbisDesk's own [Steam client](STEAM_HOSTED.md), in the style of a console launcher. It replaces the client's pages of capital letters with tabs, cover art and Tahoma text. It is a UI only: a game starts exactly as its Desktop shortcut starts it (same executable, arguments and working folder), with no per-game Wine prefix and no PS4 home-screen icon.

## Two ways in

- **Open Steam Client** (Start menu and Desktop link) opens the client over the running desktop, as before, now with the new look. Circle on a tab, or Back to the desktop in the power menu, returns to the desktop.
- **Steam Big Picture** (new Start menu entry, under Open Steam Client) asks for confirmation and restarts OrbisDesk into Big Picture: Explorer runs with a desktop named `bigpicture` instead of `shell`, so there is no taskbar, Start menu or Desktop icons, and the client opens itself on the first frame.

Settings → **Start OrbisDesk in** chooses which one a normal start uses. Existing installs keep starting in the desktop.

## Screens

The tab bar holds Home, Library, Downloads, Storage and Settings, the download in progress with its percentage, the clock and a power button. L1/R1 switch tabs; OPTIONS opens the power menu.

| Screen | What it shows | Buttons |
| --- | --- | --- |
| Home | Continue playing (by last Play), then the installed games | Directions move, X opens, square marks a favorite |
| Library | Views (Installed, All games, Not installed, Favorites, one per drive holding games) and a 6×2 cover grid | Left from the first column reaches the views; triangle changes the sort (name, size, last played) |
| Game page | Cover, state, a button row and the install's facts | Left/right choose a button; the old shortcuts stay: square language, triangle Steam API emulator, R1 move, OPTIONS uninstall |
| Install location | The drives with free space and space after the install | X installs there, square makes it the default |
| Move | Destination, confirmation, the five stages with progress, the result | Circle stops a move; the original stays |
| Downloads | The download in progress, paused installs, what ended this session | Square pauses or resumes |
| Storage | Each drive's use (Steam games, other files, free) and its games | Square makes the drive the default, triangle measures again |
| Settings | Startup mode, install location, Steam language, exit or restart, account | Left/right change a value |
| Power | Exit to desktop (or Back to the desktop), Close OrbisDesk, Cancel | A game still running asks before it is closed, with Return to the game preselected |

The pages the client already had (sign-in with its QR code, the install plan, SteamStub warnings, language lists, uninstall, errors) keep their text and are drawn as dialogs in the same style; their footer becomes the hint bar.

## Downloads in the background

In the client, the install's plan and confirmation stay as before; once confirmed, the download runs on a thread of its own while every screen stays usable, and its result page shows when it ends. There is still one download at a time: an install, verification or language change is refused while another game downloads, because they would share the CM connection. Leaving the client, signing out or switching modes pauses the download after asking; what was downloaded stays and the next install resumes it.

## Play

Play reads the game's install record and picks the launch entry exactly as the shortcut does (`orbisdesk::ChooseLaunchEntry` in `native/steam/steam_shortcut.cpp`, shared with `WriteGameShortcuts`). It writes Explorer's launch request, `/data/orbisdesk/process-p014/title-launch` (image, command line, folder and token, written to a temporary file and renamed), and waits up to 15 s for `title-launch-reply` (`<token> started <pid>` or `failed <error>`; see [`platform/ps4/pw_shell_open.h`](../platform/ps4/pw_shell_open.h)). Explorer starts the game with `CreateProcessW`, as when the shortcut is opened.

While the game runs the client is hidden and the game has the pad. A launcher may end before its game, so the client comes back only when the title's list of open programs (`pw_hw_open_programs`, `native/hw_overlay.c`) is back to what it was before Play for 1.5 s; a game that never shows in that list is followed by Explorer's `ended` reply. The overlay menu's new **Steam Big Picture** entry (SYSTEM section) brings the client back over a running game; Resume game hides it again.

### Steam's registration in the prefix

A game's own Steam emulator (a repack's ColdClient-style launcher) writes itself into the prefix as Steam: `HKCU\Software\Valve\Steam` (`SteamExe`, `SteamPath`), `ActiveProcess` with its own `steamclient.dll`, the `steam://` handler, and `SteamAppId` in the environment the desktop's programs share. On hardware (2026-11-25) AC2's SteamStub then opened GTA IV's repack launcher through `steam://` and loaded its `steamclient.dll`. Since then the client runs `C:\orbis\steam-open.exe --register <app>` through Explorer's bridge when it opens and right before every Play (Steam and non-Steam games). It writes `SteamExe` = `C:\orbis\steam-open.exe`, `SteamPath` and `InstallPath` (both registry views) = `C:\orbis\steam`, `RunningAppID`, the `steam://` handler (HKLM and HKCU Classes) = `steam-open.exe "%1"`, which opens OrbisDesk's client, and an `ActiveProcess` with no pid and no client DLL, and it clears `SteamAppId`, `SteamGameId`, `SteamOverlayGameId`, `SteamUser`, `SteamClientLaunch` and `SteamEnv`.

OrbisDesk has no Windows Steam client (its client is native), so `ActiveProcess` honestly says Steam is not running. A game wrapped in SteamStub still doesn't start: SteamStub finds no Steam, its `steam://run` now opens OrbisDesk's client instead of another game, and the install precheck keeps flagging it. gbe_fork's experimental `steamclient.dll` (in the pinned archive, not installed) would be another emulator, not Steam. The log says only who held each value before, never a path: `PWSTEAM registry owner=orbisdesk ok=… app=… previous_exe=none|orbisdesk|other previous_client_dll=… previous_url=… env_cleared=…`.

Since hardware 2026-11-26 (run-0214), `steam-open.exe` also handles Steam's run URLs. Rockstar's launcher for the Steam copy of GTA IV, in the separate process, opens `steam://run/12210//-launchTitleInFolder "<folder>"` to have Steam start the game. Its shell read the prefix's `steam://` handler, which another, modded copy's emulator had taken, so that copy started instead. Explorer now sends any title-launch request whose command line carries a `steam://` URL to `C:\orbis\steam-open.exe` with that URL, whatever program the registry names (log `PWLAUNCH steam_url handler=orbisdesk rerouted=1`). `steam://run/<app>[/<language>]//<args>` and `steam://rungameid/<app>` start the installed game as Play would, with the decoded arguments after the plan's (the launch plans: see the shortcuts of SteamStub games below). The program is started with `CreateProcessW`, not a second title-launch request, so the launcher's reply is not overwritten. Any other `steam://` URL, or a game without a plan yet, opens the Steam client as before. What happened goes to `Z:\orbisdesk\steam\url-run.txt` and stderr: `PWSTEAM url run via=url|shortcut app=… args=0|1 plan=ok|blocked|none launched=0|1 error=…`. Up to 04.89 `steam-open.exe` read its arguments from WinMain's `lpCmdLine`, which comes from the C runtime's copy of the command line; OrbisDesk's guests share one process and its msvcrt, so it was another program's. `--register`, `--play` and URLs read as no argument and opened the Steam client: at every desktop start in 04.89 (run-0229), and the registration was never reclaimed. Since 04.90 it reads `GetCommandLineW` without the program's name and logs the start's shape to `Z:\orbisdesk\steam\steam-open.txt` and stderr (`PWSTEAM open args=register|play|url|other|none program_name=quoted|bare|none length=… crt_cmdline_matches=0|1`). Since 2026-11-26 `--register` also flushes HKCU and HKLM (`RegFlushKey`; on the console flush_key writes the changed branches at once), so a program the separate process starts next reads the reclaimed values from the prefix's files: on hardware the registration GTA IV's launcher read was still another copy's emulator, and `registry-owner.txt` now ends with `flushed=0|1`. Explorer also runs `steam-open.exe --register 0` once when the desktop starts (`PWLAUNCH steam_register at=start ok=…`), so a registration a game's emulator left behind doesn't outlive a restart. A plan exists for every installed Steam game once the client has opened after this change.

### Full emulation for SteamStub games

A game whose exe is wrapped in SteamStub (Steam's DRM) looks for a running Steam client, and OrbisDesk's client is native, so Play stays off for it. Since 2026-11-25 Triangle on such a game's page opens a "Steam emulation" menu: Off, the Steam API emulator (only when the game has `steam_api.dll`), and Full emulation (ColdClient), marked experimental. Other games keep Triangle as the Steam API emulator's switch. Turning full emulation on asks once, with a warning that names a second launcher the game's folder shows it needs (Ubisoft's `ubiorbitapi`/`uplay_r1`/`upc_r` DLLs, Rockstar's `socialclub`): such a game will probably stop there.

With it on, Play is enabled, the page shows a COLDCLIENT · EXPERIMENTAL chip and "Last run", and Play starts the game through gbe_fork's ColdClient loader: the pinned archive's experimental `steamclient(64).dll`, `GameOverlayRenderer(64).dll` and `steamclient_loader_x86/x64.exe`, unmodified, in `C:\orbis\steam\coldclient` (`tools/build-steam-hosted.py`). For each start the client writes the loader's `ColdClientLoader.ini` (AppId, the game's exe, folder and arguments; no forced injection, no SteamStub memory patch) and runs the loader that matches the exe's architecture through Explorer's bridge. The loader names its `steamclient.dll` in `ActiveProcess` while the game runs and clears it when the game ends; OrbisDesk's own registration runs before every Play. The choice and the last run's length are kept in the game's folder (`.orbisdesk-coldclient.txt`); no Desktop shortcut is made for it. A start that ends within 30 seconds shows how long it ran and offers to turn full emulation off. The loader's exit code is not the game's (host Wine: a game ending with 7 left the loader's 0), so no exit code is shown.

On host Wine (2026-11-25) a 32-bit probe started by the loader with this ini found `C:\orbis\steam\coldclient\steamclient.dll` in `ActiveProcess`, loaded it (`CreateInterface` present), and got `SteamAppId`, its arguments and its folder. Not verified on the console. It is not Steam: online features, achievements and other launchers are not provided. AC2 (Steam) also needs Ubisoft's launcher, which doesn't work on OrbisDesk yet. Log: `PWSTEAM coldclient set on=… app=… saved=… second_launcher=…`, `coldclient setup app=… arch=… files=… ini=…`, `coldclient play started=… ended=… reply=… loader_code=… seconds=…`.

### Shortcuts of SteamStub games and Create shortcuts

Since 2026-11-26 a SteamStub game gets its Desktop and Start menu shortcuts too. They start `C:\orbis\steam-open.exe --play <app>` with the game's icon, not the exe: that program first names OrbisDesk as Steam in the prefix (as before Play), then runs the game's launch plan, `Z:\orbisdesk\steam\launch\<app>.plan`, through Explorer's title-launch request, the channel Play uses. The plan is what Play would start, decided as Play decides it: with full emulation on, gbe_fork's ColdClient loader with the game's ini (`<app>.ini`, copied over the loader's own); with it off, a message that says to turn it on, and nothing starts. The client writes every installed game's plan (not only SteamStub games') when it opens, rewriting only those that changed, and one game's when it is installed, before each Play, when its emulation changes, after a move and on Create shortcuts. A shortcut made before the plan exists says to open Big Picture once. Games without SteamStub keep shortcuts to their exe. Uninstall removes a launcher shortcut that names this game's `--play`, and leaves any other.

Settings » Create shortcuts (in OrbisDesk) writes the shortcuts of every installed Steam game at once, as an install does, the SteamStub games' plans included: for OrbisDesk installed again over kept games, without a Verify per game. A shortcut with the same name is replaced; the games' files are untouched. The log: `PWSTEAM shortcut ... launcher=0|1`, `PWSTEAM launch_plan app=… state=ok|blocked coldclient=… saved=…`, `PWSTEAM shortcuts_all games=… made=… launchers=… none=… failed=… prefix=…`.

### Launch modes

Since the review approved on 2026-11-26, Triangle on any installed Steam game's page opens one "Launch mode" menu, not only on SteamStub games:

| Mode | What Play starts | Dimmed when | Recommended for |
| --- | --- | --- | --- |
| Direct | The game's exe with its own Steam files | Never; on a SteamStub game it says Play stays off | Games without Steam API or SteamStub |
| Steam API emulator | The exe with gbe_fork's `steam_api(64).dll` in place of the game's | The game has no `steam_api` DLL (or its record needs a Verify) | Games that use Steam API |
| Full emulation (ColdClient) | gbe_fork's ColdClient loader, which starts the exe | No usable exe, or ColdClient's files are missing | SteamStub games (experimental) |

A game keeps the mode it uses: the mode is read from the game's own state (the emulator's record, the ColdClient choice in its folder), and the recommended one is only marked (RECOMMENDED; the one in use is CURRENT). A mode that can't apply stays listed, dimmed, with its reason, and the cursor skips it. Choosing ColdClient asks first, with the game's second launcher when its folder shows one: for Rockstar's, that its launcher checks ownership with Steam's servers, which no emulator passes, so at most an offline mode of the launcher might go on. Nothing in OrbisDesk tries to get past such a check. Switching goes through the existing paths (the emulator's enable and restore, ColdClient's choice and profile); a restore that fails doesn't block the change: the emulator's record goes and Verify puts Steam's files back. The choice is also written to `.orbisdesk-launch-mode.txt` in the game's folder (it moves with the game). Then the launch plan is rewritten and the shortcuts too: a game started through the loader gets the launcher's shortcut (`steam-open.exe --play`), any other the exe's, so Play, the shortcuts and `steam://run` start the same thing. The page's LAUNCH MODE line names the mode, and the recommended one when the user chose another. When a game started from Play closes within 30 seconds, in any mode, a dialog offers "Choose another mode". Log: `PWSTEAM launch_mode app=… mode=direct|api|coldclient recommended=… source=user|default` when the menu opens and after a change, `launch_mode set app=… mode=… saved=… shortcut_launcher=…`, and `play ended mode=… started=… ended=… seconds=…`.

## Switching modes

| File | Written by | Read by |
| --- | --- | --- |
| `/data/orbisdesk/startup.ini` (`mode=desktop` or `mode=bigpicture`) | Settings | `native/wine_hardware.c` before Wine starts; missing means desktop |
| `/data/orbisdesk/next-mode` | Exit to desktop, Start's Steam Big Picture, Settings' restart row | The next start, once (then deleted) |
| `/data/orbisdesk/bigpicture-failed` | A Big Picture start | Removed once the client is past its start (Big Picture open, the sign-in, or a failure page of its own); still present at the next start, that start falls back to the desktop. Until 2026-11-25 the client's first frame removed it, so an abort in the client's network start looped every Big Picture start |

Switching restarts the title with `sceSystemServiceLoadExec`, as Reset as Root does (`pw_hw_restart_mode`); every start is still ROOT when GoldHEN is there. A failed relaunch shows its reason and leaves the current session running. Close OrbisDesk ends the title as Wine's exit does (`pw_hw_close_title`).

## Covers

Each game's Steam library cover is fetched once from Steam's CDN on a background thread with its own HTTP client, decoded with stb_image (compiled static to `steam_covers.cpp`), box-filtered to 144×216 and kept in `/data/orbisdesk/steam/art/<app>.cov`. Many games keep that cover under another name (`portrait.png`, or a hashed folder), so the fixed `library_600x900.jpg` path answers 404 for them; since 2026-11-25 the client first asks Steam's store where each game's art is (`IStoreBrowseService/GetItems` with `include_assets`, 20 games a request, no key) and tries, in order: the store's library cover, the fixed path on both CDN hosts, then the landscape header, drawn across the tile's width over a darkened blur of its own colours. Only paths on Steam's own asset host are used. A game with none of them gets `<app>.nocover` and a placeholder (a gradient in a hue from its app id, its initials and its name); a `<app>.none` marker left by earlier versions is removed and the game looked at once more. The UI keeps the 40 most recently drawn covers in memory. The log has counts only: `PWSTEAM covers games=… cached=… fetched=… portrait=… header=… none=… failed=… retried=… store=… store_ok=…`.

## Library cache

Loading the library asks Steam three things in a row (owned games, the account's licenses, each game's app info), which takes seconds on every start. Since 2026-11-25 the last complete load is kept in `/data/orbisdesk/steam/library-cache.bin` (0600, written to a temporary file and renamed): the owned count, the licenses and each owned app's app info as Steam sent it. At the next start for the same account the client builds the library from it at once, shows it, and loads it from Steam again on a background thread. A complete reload replaces the list between screens (a game bought since appears, its cover is fetched); an incomplete one (network error, a failed step) leaves the cached list. Installs and Verify wait for the reload first, so they plan with the account's current licenses and never share the CM client with it.

- The file holds a key derived from the SteamID, not the SteamID, and another account's file is not used. Signing out, or starting without a saved session (never signed in, revoked), deletes it, so a signed-out account's games never show at the next start.
- Leaving the client or restarting into the desktop or Big Picture cancels the reload and waits for its thread before the session and the library go, so the thread never outlives what it uses.
- A truncated or damaged file is ignored and the library loads as before, with "LOADING THE LIBRARY...".

The log has counts only: `PWSTEAM library cache hit owned=… windows=…` or `cache none`, `library refresh start threaded=…`, `library refresh end complete=… canceled=… ms=…`, `library refresh applied games=… changed=…` and `library cache write=…`.

## Non-Steam games

Since 2026-11-25 a Windows game already on the console (installed by its own installer, a launcher or a disc, or copied to a USB drive) can be added to the library and started with Play like a Steam game. The list stays on the console in `/data/orbisdesk/steam/non-steam-games.txt` (0600): name, program, start folder, launch options and cover choice. Nothing is sent to the Steam account, and signing out doesn't delete it.

- **Adding.** The last tile of All games (and of the Non-Steam view) is "Add a non-Steam game"; Settings has the same row. It first lists games found on the console: Desktop and Start shortcuts (their target, arguments and folder) and exes one or two folders deep under `Program Files`, `Program Files (x86)`, `C:\Games` and each USB drive's top and `Games` folder. Several can be ticked and added at once. Setup, uninstall, update, crash-report and redistributable programs, Steam games' folders, OrbisDesk's own programs and games already in the list are left out. Square opens a browser over C:, Z:, the USB drives and the Desktop (folders, `.exe` files and shortcuts, with each exe's kind and the name in its version resource).
- **Details.** A browsed game shows its name, program, start folder, launch options and cover before it is added. The name comes from the exe's version resource (else the shortcut's or the folder's). Name, start folder and launch options are typed on an on-screen keyboard drawn by Big Picture (four rows of characters, Shift, Space, Delete, Done; square deletes, triangle types a space, OPTIONS finishes).
- **Cover.** By default the best match for the name in Steam's public store search (no account, no key: `IStoreQueryService/SearchSuggestions` on api.steampowered.com, else the store's own `storesearch`). The name is searched without trademark signs, bracketed parts and edition words, then without its subtitle, then as the program's folder (first, when the name is one word like an exe's); since hardware 2026-11-25, where "speed2" found no cover. A name the user typed (on the details or Edit screen) is searched as typed, with the same trimming but never the folder, and from then on every cover search for that game uses it; the list keeps that as an eighth column, `named` (lists written before it read as not named); confirming the name on the Edit screen, changed or not, sets it. Since hardware 2026-11-26, where "Need for Speed Underground 2" (not sold on Steam) got three other games' DLC covers, a store result counts only when the store's type for it is a game (`type` 0 in `IStoreBrowseService/GetItems`, which the art comes from anyway) and its name is the game's: the same words, edition words (Deluxe, GOTY, Complete...) and years aside, with the same sequel number (II..X read as 2..10), or the game's title without its subtitle and nothing more. When no store result counts, the cover comes from English Wikipedia: the article image of a page whose short description is a single video game (not a franchise, series or list) and whose title passes the same check, by the open MediaWiki API with no key and a User-Agent that names OrbisDesk. PCGamingWiki, the first choice, answers automated clients with a Cloudflare challenge, so it is not used. With neither, no cover is offered (the console image and the plain tile stay). The picker's caption says where each cover came from (FROM STEAM'S STORE, FROM WIKIPEDIA). SteamGridDB with the user's own key is not done. It is drawn as Steam games' covers are (the library cover, else the header letterboxed). The cover screen also offers the next matches, a `.jpg` or `.png` on the console (cropped to the tile) or the plain tile. Covers are kept in `art/<id>.cov` like Steam games'.
- **Library.** Each game gets an id with the top bit set (from its program path), so it never collides with a Steam app id in covers, favorites or last played. Imported games are installed by definition: they are in Installed, All games, Favorites when marked, a "Non-Steam" view, and the view of the drive their program is on; Home shows them with the installed games. Their covers carry a small NON-STEAM chip. When the program's USB drive is unplugged the game shows DRIVE OFFLINE.
- **Game page.** Play, Change cover, Edit (step 2 again) and Remove from library, which leaves the game's files and shortcuts where they are. Install, Verify, Language, Move and the Steam API emulator are not shown. Play writes the same request to Explorer as a Steam game's Play: the program, its launch options and its start folder.
- **Not built.** Creating Desktop and Start shortcuts for a game that has none (the review's option) is left for later.

The log has counts and outcomes only: `PWSTEAM nonsteam found shortcuts=… folders=… ms=…`, `nonsteam added count=… store_covers=… saved=…`, `nonsteam cover_search named=… terms=… tried=… suggest=… search=… items=… results=… not_games=… other_names=… apps=…` (HTTP statuses and counts), `nonsteam wiki_search named=… terms=… tried=… status=… articles=… covers=…`, `nonsteam cover provider=steam|wikipedia|none found=…`, `nonsteam cover_lookup matches=…`, `nonsteam edited program_changed=… cover=…`, `nonsteam removed=1`.

## Saved choices

In `/data/orbisdesk/steam/`: `favorites.txt` (app ids), `played.txt` (app id and last Play time), `install-location.txt` (the default drive's id; empty means ask every time) and `art/`. The Steam language stays in `steam-language.txt`. Logs never hold game names or the account name; the account name is only drawn on the Settings tab.

## Rendering

[`native/steam/steam_draw.c`](../native/steam/steam_draw.c) is a CPU canvas in 1920×1080 design units scaled to the frame (1280×720 inside the title, the sink's output; 1920×1080 for the standalone title): rounded panels, gradients, lines, icons, scaled images, QR codes, and text in Wine's Tahoma (`/data/wine-prefix/drive_c/windows/Fonts/tahoma.ttf` and `tahomabd.ttf`) through stb_truetype from the OpenOrbis SDK, pinned by SHA-256 in both builders and compiled static. Without the fonts (the standalone title on a console without OrbisDesk) it falls back to `native/hw_text.h`'s 5×7 capitals. [`native/steam/steam_bp.cpp`](../native/steam/steam_bp.cpp) holds the screens as plain views and their drawing; [`steam_ui.c`](../native/steam/steam_ui.c) gives the client a back buffer, and the client's own thread draws and publishes it. The sink's `pw_hw_steam_draw` only copies the last published frame, and frames are drawn on input, every second while a download runs, and when a cover arrives. The pad adds left/right, the left stick, and repeat after 400 ms held.

## Native changes

- `native/wine_hardware.c`: startup mode, `next-mode` and the fallback marker; `pw_hw_bigpicture_boot`, `pw_hw_bigpicture_ready`, `pw_hw_restart_mode`, `pw_hw_close_title`.
- `native/hw_pad.c`: the `<bigpicture>` request from Explorer.
- `native/hw_overlay.c`: `pw_hw_open_programs` and the SYSTEM section's Steam Big Picture entry (Spanish and English).
- `tools/build-explorer-hw.py`: the Start menu entry with its confirmation and glyph, and no Desktop icons on a desktop that is not `shell`.
- `tools/build-steam-hosted.py` and `tools/build-steam-s4.py`: the new sources, the stb_truetype pin; the hosted object's new weak imports are listed in `NEW_IMPORTS`. Its exports are unchanged.

## Tests on the PC

```sh
python3 tests/test_steam_bigpicture_host.py --out /tmp/bigpicture-shots
python3 tests/test_steam_storage_ui_host.py
python3 tests/test_steam_storage_host.py
python3 tests/test_steam_library_cache_host.py
python3 tests/test_steam_nonsteam_host.py
```

The first draws every screen at 1280×720 and 1920×1080 with Tahoma and at 1280×720 with the bitmap fallback, checks each frame's text, and decodes, saves and reads back a cover. The second drives the real install location picker and move flow with simulated buttons and real files.

## Not verified yet

Everything on the console: the hosted and standalone builds with these sources, sign-in and library in the new UI, a background download end to end, Play and the return after a game and after a launcher, the overlay entry over a running game, both restarts and the fallback marker, Close OrbisDesk, cover downloads, the clock, frame time on the PS4's CPU, and the Explorer changes (compiled only when the hardware package is built).
