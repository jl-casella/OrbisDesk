# Documentation index

[English](INDEX.md) | [Español](INDEX-es.md)

Index of all public documentation. Start with the AI/developer guide and current state. Historical documents and drafts retain their original scope; a link does not imply current validation. Private notes, downloaded dependencies and ignored evidence are not indexed.

Regenerate both languages: `python3 tools/build-doc-index.py`.

## Entry points and policy

- [AGENTS.md](../AGENTS.md) — OrbisDesk: guide for AI-assisted development
- [README.md](../README.md) — OrbisDesk
- [THIRD_PARTY.md](../THIRD_PARTY.md) — Licences and provenance
- [CURRENT_STATE.md](CURRENT_STATE.md) — Handoff point: OrbisDesk W303 and the hosted product build, 2026-11-10
- [DOCUMENTATION_POLICY.md](DOCUMENTATION_POLICY.md) — Documentation policy
- [REBRANDING_ORBISDESK.md](REBRANDING_ORBISDESK.md) — OrbisDesk: name and update compatibility
- [REPOSITORY_LAYOUT.md](REPOSITORY_LAYOUT.md) — Repository contents and dependency reconstruction
- [STATUS.md](STATUS.md) — Evidence and blockages

## Architecture and guest execution

- [investigacion-gta-vc-base-0x400000.md](investigacion-gta-vc-base-0x400000.md) — Research: GTA Vice City (PE32) and base 0x400000
- [investigacion-wow64-en-explorer.md](investigacion-wow64-en-explorer.md) — 32 bit programs as guests of explorer: feasibility

## Emulator and desktop validation

- [SHAD_W284_DESKTOP.md](SHAD_W284_DESKTOP.md) — Desktop W284 in the fork Linux of shadPS4
- [TASKBAR_CENTER_FIX.md](TASKBAR_CENTER_FIX.md) — Taskbar background and Start menu checks in shadPS4

## Native Steam client, games and attribution

- [GAMES.md](GAMES.md) — W114: games in Start → Programs → Games
- [STEAM_HOSTED.md](STEAM_HOSTED.md) — The Steam client inside OrbisDesk
- [STEAM_S1.md](STEAM_S1.md) — S1: HTTPS native to the Steam customer (ORBS00001)
- [STEAM_S2.md](STEAM_S2.md) — S2: anonymous download of a Steam depot
- [STEAM_S3.md](STEAM_S3.md) — S3: user login by QR and library
- [STEAM_S4.md](STEAM_S4.md) — S4: install a game from the library
- [STEAM_S5.md](STEAM_S5.md) — S5: launching an installed game from OrbisDesk's Explorer (in progress)
- [THIRD_PARTY_FONTS.md](THIRD_PARTY_FONTS.md) — FreeType and runtime sources

## Platform and Wine increments (historical)

- [INCREMENT_01.md](INCREMENT_01.md) — increment 1: administered memory and reproducible fork
- [INCREMENT_02.md](INCREMENT_02.md) — 2 increment: 32 bit TEB and execution hostexec
- [INCREMENT_03.md](INCREMENT_03.md) — increment 3: common dispatcher CPU
- [INCREMENT_04.md](INCREMENT_04.md) — increment 4: first PE32 without imports
- [INCREMENT_05.md](INCREMENT_05.md) — increment 5: PE sections of 4 KiB over pages PS4 of 16 KiB
- [INCREMENT_06.md](INCREMENT_06.md) — increment 6: DLL PE32 and actual imports by IAT
- [INCREMENT_07.md](INCREMENT_07.md) — increment 7: initialization of DLL and TLS by thread
- [INCREMENT_08.md](INCREMENT_08.md) — increment 8: process PE32 and first bring-up Wine
- [INCREMENT_09.md](INCREMENT_09.md) — 9 increment: memory, routes and files from the Unix side of Wine
- [INCREMENT_10.md](INCREMENT_10.md) — 10 increment: complete link and actual attempt to start Wine
- [INCREMENT_11.md](INCREMENT_11.md) — increment 11: descriptors and CPI of Wine
- [INCREMENT_12.md](INCREMENT_12.md) — increment 12: file transfer and sockets
- [INCREMENT_13.md](INCREMENT_13.md) — increment 13: pipes and complete connection with wineserver
- [INCREMENT_14.md](INCREMENT_14.md) — increment 14: directories PS4 and diagnosis of wineboot
- [INCREMENT_15.md](INCREMENT_15.md) — increment 15: file identity, symbols and external prefix
- [INCREMENT_16.md](INCREMENT_16.md) — increment 16: console32-bare.exe without Wine
- [INCREMENT_17.md](INCREMENT_17.md) — increment 17: load of DLL from disk without Wine
- [INCREMENT_18.md](INCREMENT_18.md) — increment 18: console32.exe with the CRT of mingw, without Wine
- [INCREMENT_19.md](INCREMENT_19.md) — increment 19: consume the external prefix in shadPS4
- [INCREMENT_20.md](INCREMENT_20.md) — 20 increment: mmap, Wine fallback and relocated main image
- [INCREMENT_21.md](INCREMENT_21.md) — increment 21: private mappings and ntdll protection
- [INCREMENT_22.md](INCREMENT_22.md) — 22 increment: GS by thread, signal contexts and start from Windows to WoW64
- [INCREMENT_23.md](INCREMENT_23.md) — increment 23: console32-bare.exe by Wine, with the translator as CPU WoW64
- [INCREMENT_24.md](INCREMENT_24.md) — increment 24: IU of Wine on-screen, with win32u and driver user in process
- [INCREMENT_25.md](INCREMENT_25.md) — increment 25: text with FreeType for Orbis

## Hardware builds and subsystem evidence

- [HARDWARE_G001.md](HARDWARE_G001.md) — G001: Vulkan (RADV over GNM) in PS4, H0 milestone
- [HARDWARE_H001.md](HARDWARE_H001.md) — First physical test: H001
- [HARDWARE_W001.md](HARDWARE_W001.md) — Physical test W001: Wine in the PS4
- [HARDWARE_W002.md](HARDWARE_W002.md) — Physical test W002: prefix without symbolic links
- [HARDWARE_W003_W011.md](HARDWARE_W003_W011.md) — Physical tests W003 - W011: Wine starts at PS4 to the internal server
- [HARDWARE_W096.md](HARDWARE_W096.md) — W096: MangoHud shared among guests
- [HARDWARE_W097.md](HARDWARE_W097.md) — W097: diagnosis of Start after closing graphic guests
- [HARDWARE_W098.md](HARDWARE_W098.md) — W098: loading of graphics after closing guests
- [HARDWARE_W099.md](HARDWARE_W099.md) — W099: closure of MangoHud without retaining the shared lock
- [HARDWARE_W100.md](HARDWARE_W100.md) — W100: mutual exclusion for the native allocator of SDK
- [HARDWARE_W101.md](HARDWARE_W101.md) — W101: non-load closing comparison MangoHud
- [HARDWARE_W102.md](HARDWARE_W102.md) — W102: MangoHud reactivated with frame sampling
- [HARDWARE_W103.md](HARDWARE_W103.md) — W103: native percentages for MangoHud
- [HARDWARE_W104.md](HARDWARE_W104.md) — W104: CPU/GPU labels and corrected source CPU
- [HARDWARE_W105.md](HARDWARE_W105.md) — W105: WFM administrator units and files
- [HARDWARE_W106.md](HARDWARE_W106.md) — W106: open files from WFM without replacing the desktop
- [HARDWARE_W107.md](HARDWARE_W107.md) — W107: text associations visible to HKCR
- [HARDWARE_W108.md](HARDWARE_W108.md) — W108: rename folders and delete trees from WFM
- [HARDWARE_W109.md](HARDWARE_W109.md) — W109: pending deletion and diagnosis of error 145
- [HARDWARE_W110.md](HARDWARE_W110.md) — W110: entries omitted by the listing of Wine
- [HARDWARE_W111.md](HARDWARE_W111.md) — W111: filter BSD records of deleted inputs
- [HARDWARE_W112.md](HARDWARE_W112.md) — W112: first runtime DOS within Wine
- [HARDWARE_W112_TASKMGR.md](HARDWARE_W112_TASKMGR.md) — W112: Task Manager (Performance, Processes and End task)
- [HARDWARE_W113.md](HARDWARE_W113.md) — W113: audio diagnosis DOS (smb.exe without sound)
- [HARDWARE_W114.md](HARDWARE_W114.md) — W114: CARMEN.EXE closed the entire desk
- [HARDWARE_W116.md](HARDWARE_W116.md) — W116: 32 bit programs (phase 1 of the plan PE32)
- [HARDWARE_W119.md](HARDWARE_W119.md) — W119: DLL from 32 bits (phase 2 of the plan PE32)
- [HARDWARE_W120.md](HARDWARE_W120.md) — W120: Windows audio (phase 3 of the plan PE32)
- [HARDWARE_W124.md](HARDWARE_W124.md) — W124: Direct3D 8 - 11 with DXVK (plan phase 4 PE32)
- [HARDWARE_W127.md](HARDWARE_W127.md) — W127: DirectDraw and Direct3D 7 with wined3d over Vulkan (phase 4b)
- [HARDWARE_W135.md](HARDWARE_W135.md) — W135: does the PS4 code of 32 native bits run? (phase 5)
- [HARDWARE_W136.md](HARDWARE_W136.md) — W136: entry of signals for native 32 bit code (phase 5A, step 1)
- [HARDWARE_W137.md](HARDWARE_W137.md) — W137: native 32 bit code (phase 5A, step 2)
- [HARDWARE_W138.md](HARDWARE_W138.md) — W138: MIDI music by DirectMusic (phase 5)
- [HARDWARE_W139.md](HARDWARE_W139.md) — W139: instruments of DirectMusic with GUID_Download (phase 5)
- [HARDWARE_W140.md](HARDWARE_W140.md) — W140: General MIDI battery and arrows for DirectInput (phase 5)
- [HARDWARE_W141.md](HARDWARE_W141.md) — W141: arrows as extended keys, by VK (phase 5)
- [HARDWARE_W142.md](HARDWARE_W142.md) — W142: display output by GPU (phase 6, step 1)
- [HARDWARE_W143.md](HARDWARE_W143.md) — W143: output to screen by GPU, corrected start order (phase 6, step 1)
- [HARDWARE_W144.md](HARDWARE_W144.md) — W144: the GPU stacks the windows (phase 6, step 2)
- [HARDWARE_W145.md](HARDWARE_W145.md) — W145: layers in GPU without black frame (phase 6, step 2)
- [HARDWARE_W146.md](HARDWARE_W146.md) — W146: shape of windows as transparency, with diagnosis (phase 6, step 2)
- [HARDWARE_W147.md](HARDWARE_W147.md) — W147: layer cell diagnosis (phase 6, step 2)
- [HARDWARE_W148.md](HARDWARE_W148.md) — W148: turning of frames for the black frame (phase 6, step 2)
- [HARDWARE_W149.md](HARDWARE_W149.md) — W149: non-divergence layer shader (phase 6, step 2)
- [HARDWARE_W150.md](HARDWARE_W150.md) — W150: without black frame diagnoses (phase 6, step 2)
- [HARDWARE_W151.md](HARDWARE_W151.md) — W151: without the old login of the Start menu
- [HARDWARE_W152.md](HARDWARE_W152.md) — W152: tables Vulkan as a layer of GPU (phase 6, steps 2 and 3)
- [HARDWARE_W153.md](HARDWARE_W153.md) — W153: reading images without FLAT, with prior check-up (phase 6, steps 2 and 3)
- [HARDWARE_W154.md](HARDWARE_W154.md) — W154: the image Vulkan follows your window when moving it (phase 6)
- [HARDWARE_W155.md](HARDWARE_W155.md) — W155: 32 bit-free and full-screen programs (phase 6)
- [HARDWARE_W156.md](HARDWARE_W156.md) — W156: the image Vulkan in the actual client area, with its proportion (phase 6)
- [HARDWARE_W157.md](HARDWARE_W157.md) — W157: measurement of CPU per frame (phase 6)
- [HARDWARE_W158.md](HARDWARE_W158.md) — W158: dlopen without state by thread of musl (hang up after several programs)
- [HARDWARE_W159.md](HARDWARE_W159.md) — W159: wow64native profile in 32 bit programs (phase 6)
- [HARDWARE_W160.md](HARDWARE_W160.md) — W160: time per operation of wined3d and syscalls per thread (phase 6)
- [HARDWARE_W161.md](HARDWARE_W161.md) — W161: what are the 2D copies of SuperMarioKart (phase 6)
- [HARDWARE_W162.md](HARDWARE_W162.md) — W162: cache-in-memory staging (phase 6)
- [HARDWARE_W163.md](HARDWARE_W163.md) — W163: wined3d of 32 bit leaves its memory blocks mapped (phase 6)
- [HARDWARE_W164.md](HARDWARE_W164.md) — W164: cache-in-memory stacking (phase 6)
- [HARDWARE_W165.md](HARDWARE_W165.md) — W165: key-colored spites in GPU, FPS counter with F12 and call time Vulkan (phase 6)
- [HARDWARE_W166.md](HARDWARE_W166.md) — W166: Vulkan calls of 32 bits in lots (phase 6)
- [HARDWARE_W167.md](HARDWARE_W167.md) — W167: Vulkan call grouping of 32 bits activated (phase 6)
- [HARDWARE_W168.md](HARDWARE_W168.md) — W168: exceptions of 32 unlost bits FS, without objects by copy and direct access to the desktop (phase 6)
- [HARDWARE_W169.md](HARDWARE_W169.md) — W169: FS when you resume, maps located when you release and direct access to the user's desktop (phase 6)
- [HARDWARE_W170.md](HARDWARE_W170.md) — W170: yarn output with NULL, heap failure diagnosis, unduplicated desk and appearance (phase 6)
- [HARDWARE_W171.md](HARDWARE_W171.md) — W171: page status in heap failure (phase 6)
- [HARDWARE_W172.md](HARDWARE_W172.md) — W172: commitment of invisible pages to the kernel (phase 6), Direct3D 10/11 in 32 bits with the dxgi of DXVK, and winecfg (phase 7)
- [HARDWARE_W173.md](HARDWARE_W173.md) — W173: commitment of heap pages, Mesa resident, DLL de winecfg (phases 6 and 7)
- [HARDWARE_W174.md](HARDWARE_W174.md) — W174: flexible memory returned at release (phase 6), complete winecfg (phase 7) and network for programs Windows (phase 8)
- [HARDWARE_W175.md](HARDWARE_W175.md) — W175: direct memory for large commitments (phase 6) and themes light/dark (phase 7)
- [HARDWARE_W176.md](HARDWARE_W176.md) — W176: direct memory in zero (phase 6) and network arrangements (phase 8)
- [HARDWARE_W177.md](HARDWARE_W177.md) — W177: cleaning of career diagnoses (phase 6), Moon and Noir themes (phase 7) and browser (phase 9)
- [HARDWARE_W178.md](HARDWARE_W178.md) — W178: without speed diagnoses, batch sets descriptor (phases 5 and 6) and control by XInput (phases 5 and 7)
- [HARDWARE_W179.md](HARDWARE_W179.md) — W179: browser with bcrypt (phase 9), DirectInput and XP appearance in Luna/Noir (phase 7), USB probe (phase 10) and icons
- [HARDWARE_W180.md](HARDWARE_W180.md) — W180: Crypt32 Unix side (phase 9), waiting winecfg applet and second USB probe (phase 10)
- [HARDWARE_W181.md](HARDWARE_W181.md) — W181: control key profiles for games that only use keyboard (phase 5)
- [HARDWARE_W182.md](HARDWARE_W182.md) — W182: large reserves and type libraries for the browser (phase 9), application diagnosis in winecfg, control icons Panel and square Start (phase 7)
- [HARDWARE_W183.md](HARDWARE_W183.md) — W183: Pale Moon in its own process (phase 9), Unlocked winecfg Application and control keys with various sources (phases 5 and 7)
- [HARDWARE_W184.md](HARDWARE_W184.md) — W184: memory for large views and profile of Pale Moon (phase 9), departure of guests without other atexes (phase 7)
- [HARDWARE_W185.md](HARDWARE_W185.md) — W185: Pale Moon always online, without system proxy or IPv6, with network record (phase 9)
- [HARDWARE_W186.md](HARDWARE_W186.md) — W186: context orders of another thread without signal (Pale Moon, phase 9)
- [HARDWARE_W187.md](HARDWARE_W187.md) — W187: network record of Pale Moon (phase 9)
- [HARDWARE_W188.md](HARDWARE_W188.md) — W188: number of kernel socket options (phases 8 and 9)
- [HARDWARE_W189.md](HARDWARE_W189.md) — W189: cleaning of Direct3D 11 64 bit diagnostics
- [HARDWARE_W190.md](HARDWARE_W190.md) — W190: Direct3D 11 of 64 bit with the dxgi of DXVK and the record kept on time
- [HARDWARE_W191.md](HARDWARE_W191.md) — W191: Direct3D 11 detected when opening and randomizing the kernel
- [HARDWARE_W192.md](HARDWARE_W192.md) — W192: Direct3D 11 of 64 bits inside of explorer
- [HARDWARE_W194.md](HARDWARE_W194.md) — W193 and W194: a Unity game using Direct3D 11 (The Lost Forest)
- [HARDWARE_W195.md](HARDWARE_W195.md) — W195: signals to a particular thread (pthread_kill)
- [HARDWARE_W197.md](HARDWARE_W197.md) — W196 and W197: close a Unity game without closing the app
- [HARDWARE_W228.md](HARDWARE_W228.md) — W228: ROOT mode and USB drives as units
- [HARDWARE_W284.md](HARDWARE_W284.md) — OrbisDesk: package with a clean name (W284)
- [HARDWARE_W285_W288.md](HARDWARE_W285_W288.md) — W285–W288: guest audio streams, GPU log folder, GRAPHICS menu and MangoHud on wined3d
- [HARDWARE_mando-hid.md](HARDWARE_mando-hid.md) — Command as a HID gamepad (Wine HID stack within the process)
- [HARDWARE_mando-juegos-analisis.md](HARDWARE_mando-juegos-analisis.md) — Command for games after W195: analysis (draft, no code changes)

## Drafts and plans (not acceptance evidence)

- [CI_PLAN.md](CI_PLAN.md) — CI plan: fast PR checks, a manual matrix pilot and distributions
- [HARDWARE_W168-escritorio-borrador.md](HARDWARE_W168-escritorio-borrador.md) — W168 (draft): direct access to the desktop
- [HARDWARE_W172-fase7-borrador.md](HARDWARE_W172-fase7-borrador.md) — W172: Direct3D 10/11 in 32 bits with the dxgi of DXVK, and winecfg (phase 7)
- [HARDWARE_W174-red-borrador.md](HARDWARE_W174-red-borrador.md) — W174: programme network Windows (phase 8, draft)
- [HARDWARE_W175-borrador.md](HARDWARE_W175-borrador.md) — W175: clear and dark themes, and Aero, in winecfg (phase 7)
- [HARDWARE_W176-red-borrador.md](HARDWARE_W176-red-borrador.md) — W176: network, arrangements after W174 (phase 8, draft)
- [HARDWARE_W177-navegador-borrador.md](HARDWARE_W177-navegador-borrador.md) — W177: browser and webviews (phase 9, draft)
- [HARDWARE_W177-temas-borrador.md](HARDWARE_W177-temas-borrador.md) — W177, part of themes: Moon and Noir, and without visual style by default
- [HARDWARE_W178-mando-borrador.md](HARDWARE_W178-mando-borrador.md) — W178, part of the control: XInput with the control of PS4, game mode and joy.cpl (phase 7)
- [HARDWARE_W179-borrador.md](HARDWARE_W179-borrador.md) — W179, parts of the Wine configuration session: DirectInput of the control and XP look of Moon and Noir
- [HARDWARE_W179-navegador-borrador.md](HARDWARE_W179-navegador-borrador.md) — W179: browser and webviews arrangements (phase 9, draft)
- [HARDWARE_W180-navegador-borrador.md](HARDWARE_W180-navegador-borrador.md) — W180: Crypt32 Unix side (phase 9, draft)
- [HARDWARE_W180-usb-borrador.md](HARDWARE_W180-usb-borrador.md) — W180: USB disks as D units: a K: (phase 10, draft)
- [HARDWARE_W181-teclas-plan-borrador.md](HARDWARE_W181-teclas-plan-borrador.md) — W181, part of the control: key profiles for games that only use keyboard
- [HARDWARE_W182-navegador-borrador.md](HARDWARE_W182-navegador-borrador.md) — W182: record of type libraries (phase 9, draft)
- [HARDWARE_W182-winecfg-borrador.md](HARDWARE_W182-winecfg-borrador.md) — W182, part of winecfg and appearance: a diagnosis of freezing when applying a theme, control panel icons and straight Start button
- [HARDWARE_W183-navegador-borrador.md](HARDWARE_W183-navegador-borrador.md) — W183: Pale Moon as a separate title (phase 9, draft)
- [HARDWARE_W183-winecfg-borrador.md](HARDWARE_W183-winecfg-borrador.md) — W183, part of winecfg: Apply a theme no longer freezes
- [HARDWARE_W184-navegador-borrador.md](HARDWARE_W184-navegador-borrador.md) — W184: Pale Moon without D3D11 (phase 9, draft)
- [HARDWARE_W184-winecfg-borrador.md](HARDWARE_W184-winecfg-borrador.md) — W184, part of winecfg: Accept or Cancel no longer close everything
- [HARDWARE_W185-navegador-borrador.md](HARDWARE_W185-navegador-borrador.md) — W185: network of Pale Moon (phase 9, draft)
- [HARDWARE_W187-navegador-borrador.md](HARDWARE_W187-navegador-borrador.md) — W187: network log of Pale Moon (phase 9, draft)
- [HARDWARE_W188-navegador-borrador.md](HARDWARE_W188-navegador-borrador.md) — W188: TCP kept in Pale Moon (phase 9, draft)
- [HARDWARE_W190-winecfg-borrador.md](HARDWARE_W190-winecfg-borrador.md) — W190, part of winecfg: the chosen theme is maintained when restart
- [HARDWARE_W197-mangohud-dxvk-borrador.md](HARDWARE_W197-mangohud-dxvk-borrador.md) — MangoHud in games Direct3D by DXVK (draft for the next W)
- [HARDWARE_W203-palemoon-invitado-borrador.md](HARDWARE_W203-palemoon-invitado-borrador.md) — W203: the desktop is frozen with Pale Moon as guest (draft)
- [HARDWARE_W204-palemoon-memoria-borrador.md](HARDWARE_W204-palemoon-memoria-borrador.md) — W204: Pale Moon as a guest it is stuck when asking for memory (draft)
- [HARDWARE_W205-palemoon-pestana-borrador.md](HARDWARE_W205-palemoon-pestana-borrador.md) — W205: Pale Moon as a guest it is stuck when opening a second tab (draft)
- [HARDWARE_W207-palemoon-invitado-borrador.md](HARDWARE_W207-palemoon-invitado-borrador.md) — W207: Pale Moon as a guest - files when finished, trace the failure, without relaunching (draft)
- [HARDWARE_W208-invitado-descarga-borrador.md](HARDWARE_W208-invitado-descarga-borrador.md) — W208: A guest download his DLL and release his memory when he finishes (draft)
- [HARDWARE_W209-invitado-salida-borrador.md](HARDWARE_W209-invitado-salida-borrador.md) — W209: a guest's failure output ends and the next boot cleans what was left (draft)
- [HARDWARE_W210-invitado-reinicio-borrador.md](HARDWARE_W210-invitado-reinicio-borrador.md) — W210: a guest who reinitiates himself starts again when he is finished (draft)
- [HARDWARE_W212-invitado-orden-borrador.md](HARDWARE_W212-invitado-orden-borrador.md) — W212: the modules of a guest are downloaded in order of dependencies and without DllMain (draft)
- [HARDWARE_W214-invitado-carga-borrador.md](HARDWARE_W214-invitado-carga-borrador.md) — W214: The EXE of a guest finds his DLL and its download awaits the loader (draft)
- [HARDWARE_W215-loader-lock-borrador.md](HARDWARE_W215-loader-lock-borrador.md) — W215: the loader lock is taken even if a thread that expected it has been finished (draft)
- [HARDWARE_W216-invitado-terminado-borrador.md](HARDWARE_W216-invitado-terminado-borrador.md) — W216: the last thread of a finished guest comes out without DLL_THREAD_DETACH (draft)
- [HARDWARE_W220-winecfg-solo-borrador.md](HARDWARE_W220-winecfg-solo-borrador.md) — W220: "Run alone" box in the Winecfg Applications tab (draft)
- [HARDWARE_W290-escritorio-borrador.md](HARDWARE_W290-escritorio-borrador.md) — W290: the desktop follows Desktop folder changes, and desktop icons get a right-click menu (draft)
- [HARDWARE_W290-fuentes-tema-borrador.md](HARDWARE_W290-fuentes-tema-borrador.md) — W290: system fonts keep their size after a visual-style change (draft)
- [HARDWARE_W292-escritorio-columnas-borrador.md](HARDWARE_W292-escritorio-columnas-borrador.md) — W292: desktop icons in columns, with File Manager and Steam first (draft)
- [HARDWARE_W292-fondos-borrador.md](HARDWARE_W292-fondos-borrador.md) — W292: choosing the desktop wallpaper, with three more to pick from (draft)
- [HARDWARE_W292-reset-root-borrador.md](HARDWARE_W292-reset-root-borrador.md) — W292: "Reset as Root" and "Reset as Sandbox" in the Start menu (draft)
- [HARDWARE_W293-wfm-accesos-borrador.md](HARDWARE_W293-wfm-accesos-borrador.md) — W293: shortcuts in WFM show their own icon, with the arrow (draft)
- [HARDWARE_Wxxx-navegador-borrador.md](HARDWARE_Wxxx-navegador-borrador.md) — Wxxx: Pale Moon without network log (phase 9, draft)
- [HARDWARE_Wxxx-palemoon-invitado-2-borrador.md](HARDWARE_Wxxx-palemoon-invitado-2-borrador.md) — Wxxx: Pale Moon as guest, second round of diagnosis (draft)
- [HARDWARE_Wxxx-palemoon-invitado-borrador.md](HARDWARE_Wxxx-palemoon-invitado-borrador.md) — Wxxx: Pale Moon as guest freezes the desktop (diagnosis, draft)
- [HARDWARE_fase7-mando-plan-borrador.md](HARDWARE_fase7-mando-plan-borrador.md) — Phase 7, rest: command of PS4 by XInput and DirectInput, and joy.cpl (plan, draft)
- [HARDWARE_fase7-plan-borrador.md](HARDWARE_fase7-plan-borrador.md) — Phase 7 of the plan PE32: dxgi of DXVK per program and winecfg (plan, draft)
- [HARDWARE_temas-plan-borrador.md](HARDWARE_temas-plan-borrador.md) — Clear and dark themes in winecfg (plan, draft)

## Other public notes

- [CI.md](CI.md) — Running CI and measuring the platform matrix
- [RELEASES.md](RELEASES.md) — Product builds, releases and the development branch
- [RELEASE_LICENSES.md](RELEASE_LICENSES.md) — Release licenses (alpha-1)
- [RELEASE_TRACES.md](RELEASE_TRACES.md) — Release traces: one switch for alpha-1
