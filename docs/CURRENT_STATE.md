# Handoff point: OrbisDesk W288 (03.87), 2026-11-07

[English](CURRENT_STATE.md) | [Español](CURRENT_STATE-es.md)

Latest uploaded build: W288, `OrbisDesk.pkg` 03.87. Not yet tested on the console. Details for W285–W288: [HARDWARE_W285_W288](HARDWARE_W285_W288.md).

- **W285:** a guest's audio streams leave the mixer when it unloads (orphan list, not freed). Tested with NFS U2 closed from the overlay; that run released its own stream.
- **W286:** RADV's GPU logs go to `/data/orbisdesk/gpu`. The old `/data/orbis-win` folder was deleted from the console.
- **W287:** GRAPHICS overlay entry, per 32-bit program: DXVK or wined3d for D3D8/9, Vulkan or OpenGL for wined3d. MangoHud now attaches to wined3d games (SuperMarioKart, confirmed in the log). The saved renderer was not applied, because wined3d stayed loaded between runs.
- **W288:** wined3d reads the program's renderer at each `wined3d_create`. Next check: SuperMarioKart with `gl` saved should log `PWD3D renderer=gl ... from the program`.
- **Earlier on 2026-11-07 (W273–W282, no separate documents):**
  - per-guest command line and module name during load;
  - zero-timeout message wait fix (Quake 3, NFS U2);
  - real CPU affinity through `scePthreadSetaffinity` (6 title cores); process affinity changes are refused;
  - NFS U2 pinned to one core, only for threads that start in its EXE;
  - x87 fault traces, and 32-bit frames in hang dumps;
  - winmm/dinput singleton threads no longer belong to a guest;
  - winmm removes a timer whose callback is unmapped or faults (NFS U2 second start has music again);
  - wmvcore reports a missing winegstreamer instead of crashing (GTA San Andreas).
- **Steam:** S2 01.06 (anonymous depot download, 8/8 files verified) and S3 01.07 (QR sign-in, saved session, library of 36 games) passed on the console. Reopening S3 without a QR is still to be checked. See [STEAM_S3](STEAM_S3.md).
- **Games reported working by the user on this day:** Quake 3, Max Payne 1 and 2, NFS Underground 2 (including music on a second start), NFS Most Wanted, GTA San Andreas, Worms 4, Call of Duty (level loads). SuperMarioKart runs; its MangoHud and renderer choice are being checked.

<a id="punto-de-retoma-orbisdesk-paquete-limpio-w284-0383-2026-11-07"></a>

# Previous handoff: OrbisDesk, clean W284 package (03.83), 2026-11-07

W284 physical test downloaded: root mode, image and interface active for about
11 minutes, with no recorded fatal exit. The selector capture confirms OrbisDesk
and version 03.83 W284. Evidence: `reports/wine-hardware-w284/physical/20261107T153807Z/`.
Classification: `presented`, with no exit code; this does not establish general game compatibility.

Built and verified locally: `out/wine-hardware-w284/OrbisDesk.pkg`.
Visible PS4 title: **OrbisDesk**. The version is visible only in the NORMAL/ROOT
selector; internal SFO version 03.83 updates ORBW00002. Execution logic is unchanged.
58 source hashes and the package SHA256 were checked. A capture confirms the selector.
FTP delivery completed: `/data/pkg/OrbisDesk.pkg`, 192.168.68.100:2121.
The PKG and 1,823 runtime files were verified by reading them back; one previous
package was removed after verification. Settings were preserved; later evidence
confirms installation and startup on physical hardware.
Evidence: `reports/wine-hardware-w284/transfers/20261107T144147Z.json`.
See [W284](HARDWARE_W284.md). The following entries are historical.

<a id="historia-previa-orbisdesk-w283-0382-2026-11-07"></a>

# Previous history: OrbisDesk W283 (03.82), 2026-11-07


**Delivery W283 completed:** `/data/pkg/orbisdesk-W283-a3a72e1401c2.pkg`, FTP 192.168.68.100:2121. PKG and 1.823 runtime files verified by reading (83 uploaded, 1.740 already present); a previous package removed after verification. No permission failures. Console settings preserved. Installation and physical testing pending. Evidence: `reports/wine-hardware-w283/transfers/20261107T142853Z.json`.

The current name is **OrbisDesk**. The change includes own code, interface, documentation, classes and associations Win32, titles and names of packages, probes and Steam customer. Details and exceptions: [REBRANDING_ORBISDESK](REBRANDING_ORBISDESK.md).

- W283 retains ORBW00002 and its Content ID to update the existing installation.
- Estado/logs new in `/data/orbisdesk`; the single import of previous adjustments. Please provide documents and games are still in your original locations.
- Steam S1 01.05 and S2 01.06 rebuilt as OrbisDesk, without new physical evidence.
- Three targeted migration / rutas/paquetes checks approved in host.
- Main package compiled and verified: `out/wine-hardware-w283/OrbisDesk-W283-03.82.pkg`. SFO correct, 58 hashes matching source and web closure without missing imports. Installation and visual validation pending; do not interpret brand change as new game compatibility.
- The logs, packages and historical hashes keep their original names.

<a id="historia-previa-2026-11-07-w281-0380-subida--prueba-pendiente"></a>


# Previous history: 2026-11-07, W281 (03.80 up / test pending

<a id="último-código-auditado-w281"></a>


## Last code audited: W281

This retake read code, manifests and local evidence. He did not compile, execute, transfer or modify code. The following state W260/W261 remains as history.

- W281 / 03.80, ORBW00002: local package and 56 source files of the manifest tested by SHA256, no differences. 91 guest building reviews for x86_64/i386 and web closure without missing imports.
- PKG /data/pkg/orbis-win-W281-90e022053bab.pkg. Transfer verified in reports/wine-hardware-w281/transfers/20261107T130350Z.json: 1825 runtime files, current destination **192.168.68.100:2121**; W280 withdrawn after verification. Do not automatically use the historical IP. 104. No physical folder of W281 yet.
- Last evidence located in this recome: W279, reports/wine-hardware-w279/physical/20261107T124705Z/. Not equivalent to a global acceptance: the label collector presented, with no final output.

<a id="cambios-posteriores-a-w260w261"></a>


## Changes after W260/W261

- **Owners / processes:** process hands with end event and GetExitCodeProcess per guest (W267); KnownDLLs do not count as shocks (W269); GetModuleHandle (NULL), GetModuleFileName (NULL) and command line respond by host also during carga/DllMain (W273/W274). The first thread uses the EXE (W271 stack reserve.
- **Reload as a fallback:** inherit carpeta/entorno from the pitcher (W262) and analyze the line Windows, with up to 16 arguments (W265). This matters when a second EXE needs a fixed base occupied by the first guest.
- **OpenGL i386:** Mesa WGL/Zink prepared in syswow64 and initialization settings with dxgi; CoD and GL extensions. Do not give general compatibility of these games by proven just by compiling the route.
- **CPU/afinidad (W275 - W279):** pw_wine_thread_setaffinity uses scePthreadSetaffinity and the record TID/pthread_t; system.c reports CPUs allowed. W279 records processes = 6, title_cores = 3f and speed2.exe in mask 0x20. Changes in affinity of the whole process are rejected with ACCESS_DENIED to not set Explorer and server to the kernel that a host requests. It is not implementation of RR or ntsync.
- **W281, still to be tested:** the singleton threads of winmm/dinput/dinput8 do not belong to the host who created them; So the closure does not eliminate the shared timer and leaves the second opening without music. The guest affinity of a kernel applies only if the thread entry falls into your EXE, not to threads of DXVK or other DLL. NFS U2 is the case that motivated both corrections.
- **Multimedia W280:** wmvcore i386/x86_64 returns real error and NULL reader when winegstreamer is missing, rather than ending with the exception of delay-load. Motivated by GTA San Andreas; does not implement GStreamer or WMV reproduction.

Key code: tools/build-guest-hw.py, build-wine-delete-server.py, build-telemetry-ps4.py, build-wmvcore-hw.py; platform/ps4/pw_wine_threads.c; native/wine_hardware.c. The world PE32 continues in the same process of Explorer, with alternative relaunch; no native auxiliary architecture appeared.

<a id="nueva-pista-separada-cliente-nativo-de-steam"></a>


## New separate track: native customer of Steam

- ORBS00001, independent of Wine/ORBW00002. Backend of Playden set at fb74dbfd6bb96fc19a96afc1f48a4e40a885216b, with Mbed TLS/curl/zstd/LZMA. See docs/STEAM_S1.md, STEAM_S2.md and native/steam/.
- S1 checks entropy, CA, HTTPS and certificate rejections. Host passed; first PS4 failed to read CA; 01.01 change to reading to EOF. No evidence of full acceptance of that version was found here.
- S2 host yes complete anonymous login, manifest and download of depot 1004/app 1007: 8 files, 69 chunks, 67863136 bytes, all verified by SHA1. It is not login of an account or the client Steam Windows running within Wine.
- S2 PS4 01.03 fails in HttpClient of Playden; Curl alone does get TLS 1.3/HTTP200. The failure was traced to deactivated curl options that Playden needs. 01.04 is already packed with the corrected configuration and diagnostic options; their physical acceptance is not included in the revised documents. Do not announce full download in PS4 until the verified final result.

Next reading point: physical result W281 (audio/reapertura NFS U2, rendimiento/afinidad), and S2 result 01.04 on your independent track. The "untested" texts of old documents can have later results: read the new chronological sections and check manifests/logs before acting.

<a id="historia-conservada-w260-probado--w261-en-preparación"></a>


## preserved history: W260 tested / W261 in preparation

<a id="retoma-más-reciente-w260w261"></a>


## Most recent handoff: W260 - W261

This block replaces the state W188 and the historical slopes preserved below. Audit of local archives; This retake did not compile or transfer anything.

- **Last build with manifest, transfer and localized physical evidence:** W260 / 03.59. Package /data/pkg/orbis-win-W260-791ed8ceb53a.pkg, transfer reports/wine-hardware-w260/transfers/20261106T004811Z.json with verified reading. Physical tests: 20261106T011238Z and 20261106T021646Z. These are UTC dates: even 5/11 at night in Argentina. The collector says presented, not full acceptance.
- **Code / build in preparation:** W261 / 03.60 There is a PKG in out, but when I checked there was out/wine-hardware-w261/manifest.json not a transfer report. build/w261-final.sh follows the staging chain, link, package and web closure; the link records linked-unvalidated without pending symbols. Do not announce W261 finished, raised or tested without such checks.

<a id="arquitectura-lo-que-ya-dejó-de-ser-hipotético"></a>


## Architecture: what has ceased to be hypothetical

- **World PE32 within Explorer implemented.** probes passed; W234 ran with sole32 twice without relaunching. W235 incorporated orbis32host and the bridge of CreateProcess; guests i386 have their DLL separate from relaunched mode.
- **GUI and graphics PE32 in the world:** W240 ran guided-window32, d3d9test32 DXVK (1673 cuadros/5 s) and ddraw7test32 wined3d Vulkan (2491 tables), all output 0.
- They were resolved callbacks by architecture, TLS, suspended creation, procedure crosses of ventana/IME, record WOW64/COM and SEH release. These are no longer initial pending tasks of the plan. Reload and OrbisRunsAlone continue as alternatives; the pe32rebunch marker allows to return to the previous path.
- **Vice City:** W246 executed it and was played within Explorer with d3d8 DXVK, sound and controls. W256 played from USB both videos twice. W255 fix layers GPU held after destroying a swapchain whose daughter window no longer exists; W256 recover the focus after leaving. Do not infer total compatibility: it was recorded DEVICE_LOST when recreating the device with Esc in W246.
- **Strand signals:** W195 implemented TID/pthread_t record and directed SIGUSR1; Your logs show correct delivery. The historical phrase "there are no directed signals" no longer describes all the current capabilities. It does not involve full support of remote i386 contexts or signals of termination: others remain restricted.
- **Guest closures:** TerminateProcess own and FLS by image (W196/W197), download of own DLL, order of dependencies, threads and orphaned locks had new iterations. W259 credits download of hl2 and new load modules at the next opening, solving a collision with the Father Portal folder.
- This retains a single shared process: it is not native isolation.

<a id="usb-navegador-y-multimedia"></a>


## USB, browser and multimedia

- **USB already works in ROOT mode:** W228 allows you to choose NORMAL/ROOT when starting. GoldHEN remove the sandbox and then return to the app's uid; the mode is kept in relaunches and restores when it comes out. D: -K: correspond to usb0-usb7 mounted, detected at boot. Vice City was read from E: Do not give up proven writing or hot connection. See HARDWARE_W228.md.
- Pale Moon already sailed from W188. There are new iterations about its use as a guest and cierre/reapertura; do not reinstall W188 to solve the old network.
- DirectShow/COM i386 and video playback were expanded; the research records webview32 with pages and reopening, DVD and VLC running in W252. It does not involve support for all formats, DRM or Media Foundation.

<a id="bloqueo-inmediato-y-w261"></a>


## Immediate and W261 blocking

- **Portal in W260:** hl2 reaches DXVK/D3D9 and presents five pictures. Then VK_ERROR_DEVICE_LOST; the composer of Explorer continues to present. The evidence aims to investigate RADV/GFX7, does not show that the activation of the world WoW64 fails. The diagnosis of valla/GPUVM is missing to attribute the exact cause.
- W260 added avifil32/shfolder, which had previously prevented them from reaching that stage.
- W261 prepares 396 additional i386 and 393 x86_64 modules with import closure, debug removed and generated COM record: 7699 119/118 modules keys. It is an extension of availability, not validated execution of all these APIs. There are explicit exclusions by servicios/backend Unix/Mono/WinRT, among others; d3dx9_24 - 43 are still not linked. The w261-final.sh file also includes cursor options per program and blocking statistics on the desktop.

Current working reference: investigacion-wow64-en-explorer.md, sections 9 - 31. Its first paragraphs are the historical plan; the "prepared" headers of intermediate sections should be read together with the results of the following.

Next: verify closure of W261 and their transfer before seeking evidence; continue Portal by evidence GPU. Do not reconstruct or stop other people's processes during a break-in. Settings: iterations focused on PS4 physical, preserve evidence and feedback with button; without extensive local matrix.

<a id="historia-conservada-retoma-w188-0287"></a>


## Conserved history: retakes W188 (02.87)

<a id="retoma-auditada-del-workspace"></a>


## Hearing handoff of the workspace

The notes W113 - W188 advanced without updating this index. This block replaces the "current," "next" and "pending" indications of the W112 and lower history that is kept below. Do not reinstall or rebuild W112.

- Last built: W188, APP_VER 02.87, ORBW00002. Local PKG tested by SHA256: 5c42debd84403324f8510d194dac3e4fc635fef12ce5023e90c258f1c3a32e61.
- verified up to 192.168.68.104:2121: /data/pkg/orbis-win-W188-5c42debd8440.pkg. reports/wine-hardware-w188/transfers/20261104T004515Z.json: readback_verified = true, 861 runtime files, 695120406 bytes; W187 removed after verification. The UTC date of the report is equivalent to the 3 November night in Argentina.
- W188 and W187 have no physical evidence unloaded in their local directories. Do not confuse transfer with installation or execution. Last physical test documented: W186, reports/wine-hardware-w186/physical/20261104T002752Z/.

<a id="capacidades-recuperadas-y-sus-límites"></a>


## Capacities recovered and their limits

- DOSBox Pure already executed DOS in PS4: CARMEN with audible audio and closures 0 (W114). smb.exe generates silence in the core; It is not proof of failure of AudioOut.
- Windows PE32 starts by relaunching the title. W137 added native execution x86 in compatibility mode (wow64native), with signal path / exceptions. Do not claim that PE32 already live as a host within Explorer PE64.
- Audio Windows 32/64 accepted (W120 and subsequent); D3D9 minimum DXVK accepted in both (W126). DDraw/D3D7 with wined3d/Vulkan it comes to SuperMarioKart (W134). Do not generalize these tests to all games or give D3D10/11 Validated.
- Presentation and composition by layers GPU; several staging, mapping and grouping improvements Vulkan. SuperMarioKart completed a race and left 0 in W176; W178 recorded median 54,7 FPS in your session, with variation by scene. W181 confirmed the game with a key profile.
- WFM: list, EXE/textos, rename and delete recursive accepted in previous iterations. Themes Luna/Noir, Start and icons were later worked. winecfg Apply completed twice in W184; that change also separates atexus from guests.
- Basic network accepted W176 in 32/64: DNS, TCP, HTTP 200, non-blocker, loopback, adapters and DNS consultation by UDP. That doesn't credit HTTPS from the browser.
- USB: W181 still sees / mnt non-existent for the app, errno = 2. There is no access to accredited USB drives; the proposed letters do not remove the sandbox.
- WebView Gecko shows local page (W182), with limitations of JS/canvas. Pale Moon 35 run as a separate title to avoid DLL homonymous from Gecko. W186 shows full local page: es5-ok, es2020-ok, canvas-ok. Your GetThreadContext failed arrangement eliminates the observed block; remote sites are still blank or wrong. Do not affirm remote functional navigation.

<a id="trabajo-inmediato"></a>


## Immediate work

1. Get physical result of W188 before another build. Fix translation of options TCP/IP/IPv6 from SDK Linux to the kernel FreeBSD by wrappers in platform/ps4/pw_wine_sockopt.c. Keep logging of Pale Moon and disable keeplive on your profile. See docs/HARDWARE_W188.md: inferred cause of the code, still pending physical validation.
2. Check HTTP/HTTPS and palemoon-net.log -main. * together with PWNET: distinguish connection, TLS and HTTP response. The random source of ntdll remains to be verified (Getandom ENOSYS and unaccredited fallback / dev/urandom).
3. The research docs/investigacion-wow64-en-explorer.md proposes first disimular/medir relaunch and then map probes low 4 GiB, signals and late BTCpuProcessInit. World PE32 within Explorer: not implemented; estimate of the document 15 - 25 builds, conditioned to probes.

Persistent preferences: tests focused on PS4 real, without local matrix; to preserve evidence; to withdraw previous PKGs only after a verified increase; instala/ejecuta user and press with button. Absolute calibration CPU/GPU postponed. This was a local reading and documentation: it was not compiled or touched FTP.

<a id="historia-previa-conservada-índice-antiguo-w112"></a>


## Previous history preserved (old index W112)

<a id="task-manager-en-w112-a81c9325bbaf-aceptado-todo-anda"></a>


## Task Manager in W112 (a81c9325bbaf, accepted: "Everything goes")

Performance in 0 and empty processes: the class 8 (ProcessorPerformance) returned NOT_SUPPORTED in ORBIS and taskmgr left each soda. End task left the line because the delete pass only ran if another window was listed. Arrangements in system.o telemetry and out/taskmgr-hw. W112 (02.11) were rebuilt with DOS already synchronized and uploaded: /data/pkg/orbis-win-W112-a81c9325bbaf.pkg, report transfers/20261102T192004Z.json. The previous PKG W112 (b6809b7be979 was deleted by FTP: His ELF had no arrangement and the / data runtime is already the new one. Detail: [HARDWARE_W112_TASKMGR](HARDWARE_W112_TASKMGR.md).

<a id="última-consulta-documentssmbexe"></a>


## Last consultation: Documents/smb.exe

The user confirmed "He erased everything correctly" and then specified that he failed to open Documents/smb.exe. Only that EXE was downloaded to identify it, without running it or modifying the console. Report: reports/smb-exe-inspection/report.json. It is MZ MS-DOS with PKLITE marker, e_lfanew = 0 and without PE header, 66055 bytes; SHA e58adb73373c214a0f4ae1f98fb7dde655095c338cb4121db3bd4abde6049db3 W111 20261102T181347Z records reject_title_replacement for that file. He needs a run DOS apart; it is not a proven failure of PE32/WoW64. Wine upstream also delegates DOS in DOSBox (programs/winevdm/winevdm.c). The user chose to add support for games DOS. W112 (02.11) already compiles DOSBox Pure PE64 played, doshost.exe GDI, native bridge AudioOut and routing of MZ/.com from the broker of Explorer. See HARDWARE_W112.md. PKG SHA b6809b7be979be7e1a6b638a08fbdfbace2c5351fea7c56fb84cc471d06f2c01. ELF SHA 985ee531e5e49707b4de6086cb07b565239613714c075609d61aa6bed76a72f8. 553 runtime files; DOS source and recipe included, no games. Transfer W112 started at 192.168.68.104:2121; check report before announcing full rise. It has not been executed DOS in PS4 yet. Next: install, open Documents/smb.exe, check imagen/controles/audio, close, check Start/WFM and reopen. Collect logs PWDOS/PWDOSAUDIO. W111 retains your acceptance of renamed, false 145 and erased tree. The GPU patch had non-idempotent guard: corrected and fuente/biblioteca restored to the exact hashes of W111. The percentages were not changed.

<a id="iteración-actual-w111"></a>


## Current: W111

W110 actual collection: 20261102T174008Z. Native_entry CARMEN09.BMP but stat ENOENT; FTP later confirms non-existent name and empty father. It also lists an earlier name of the renamed folder that no longer exists. The server counts those residual inputs as content and fails 145. Identity Guard W110 does not explain this case; is not attributed to an outstanding closure.

W111 (02.10) fixes the BSD contract readdir: omits records with zero inode and whiteouts by validating first length; continues to an input activa/EOF. Maintains real errors and does not simulate empty. The inode of these records was not printed in W110: the following test records skipped_unused to confirm it. Timely check of the decoder passed (activos/borrados/malformados). Built and uploaded package with verified back reading: /data/pkg/orbis-win-W111-e8585b70c409.pkg. Report: reports/wine-hardware-w111/transfers/20261102T175415Z.json. 548 verified files (546 present, 2 ), without permit failure. W110 withdrawn after verification. Only ELF, runtime PE identical by hash. See [HARDWARE_W111](HARDWARE_W111.md). Physical result: Real test collected in 20261102T180132Z: 198 inode slots omissions = 0, rmdir native rc = 0 and folder absent by FTP. Rename with spaces rc = 0, old name absent and new present by FTP. No errors in erasing. The false 145 is validated as corrected in this case; The real name, too. A complete tree test with active files and final title output is missing. No new building is required for that check. New collection 20261102T180735Z after another "I tried it": same run- 0001, without new filesystem operations compared to 180132Z. The user was asked for the observed result (success / error/no completed), without asking for another reinstallation. The user explicitly confirmed "He erased everything correctly." Recursive hardware feedback test is accepted, without attributing it to new log operations. Acceptance: reports/wine-hardware-w111/physical/20261102T180735Z/acceptance.json. W111 remains as a reference for rename, false 145 and erased from the proven tree. There is no further evidence requested for this arrangement. Next priority: desktop with files/folders, text-link icons and refreshment. After "I already tried it," collect W111 and verify rmdir real and missing folder.

<a id="referencia-anterior-w110"></a>


## Previous reference: W110

W109 tested and collected: 20261102T172145Z, two logs. The server records koopa beach_fast .mid and CARMEN09.BMP as blockers. WFM does not register DeleteFile for them; only lists SMK and then fails RemoveDirectory 145. Reattempts do not change that result. The pending closure scenario does not explain these cases. The problem is in files omitted by the list Win32.

W110 (02.09) reproduces the Unix file object from ntdll with receta/hash proven: uninode identities do not hide inputs; errors of readdir they do not become partial success; Saudi PWDIRENUM nativo/mAnal/stat/filtro/resultado. The exact cause of omission is not yet attributed to the inode: it requires logs of this build. Built and uploaded package with verified back reading: /data/pkg/orbis-win-W110-982cf9c8ac3c.pkg. Report: reports/wine-hardware-w110/transfers/20261102T173510Z.json. 548 verified files (546 present, 2 ), no leave failure. W109 withdrawn after verification. Only ELF change, WFM/componentes PE match for hash with W109. Physical evidence pending. The first test notice was investigated in 20261102T173705Z: W110 No. directorio/logs. FTP new sample w109/run-0003.log, downloaded as session W109 20261102T173750Z; Start W109 entered_launcher. Do not count as proof of W110 or infer crash before the main. It was asked to close, install 02.09 and try W110. He didn't go up or rematch again. See [HARDWARE_W110](HARDWARE_W110.md). No local matrix, no emulator changes.

<a id="referencia-anterior-w109"></a>


## Previous reference: W109

W108 failed with 145 when deleting with subfolders (confirmed by the user). Session 20261102T170507Z downloaded, title ends with 0. PWFM Unicode was not captured. FTP later: Documents/Test empty; due cause, possibly deferred elimination. It wasn't erased by FTP.

W109 (02.08) compiled and uploaded with verified back reading: /data/pkg/orbis-win-W109-9968f1da041b.pkg. Report: reports/wine-hardware-w109/transfers/20261102T172053Z.json. 548 Verified (545 files present, 3 uploaded), no permit failure. W108 withdrawn after verification. Physical evidence pending. Reaction of RemoveDirectory real up to 500ms before 145; It contains error/cancelaci on, does not erase concurrent content. It corrects WFM log channel, records unlink/rmdir and adds is_dir_empty server audit by a single object rebuilt with receta/hash tested. No local matrix. Detail: [HARDWARE_W109](HARDWARE_W109.md). After testing, collect W109 and review PWFM/PWDELETE to identify the blocking input or confirm actual erasing.

Next desktop: test.lnk exists by FTP but does not appear. Explorer also discards accesses if you do not get link/destino icon (.txt without PE icon). Add icon and files/folders fallback, and check soda; not to attribute everything to notifications. Do not mix this improvement with erasing iteration.

<a id="referencia-anterior-w108"></a>


## Previous reference: W108

W107 opened Desktop/test.txt twice with Notepad and closed with 0; session 20261102T164857Z downloaded. The user reports failures when renaming folders and erasing trees. W108 (02.07) enables real rename with repair of routes of descriptores/cwd and replaces the silent deletion of WFM by route Win32 that closes Find before recursion, does not continue to repair points and reports errors. The recombinant builder and explicitly replaces the object FS; base intact. Timely resigning check in Linux passed; first execution DrvFS EACCES preserved. Built and uploaded package with verified back reading: /data/pkg/orbis-win-W108-ec2dd685205f.pkg. Report: reports/wine-hardware-w108/transfers/20261102T170417Z.json. 548 verified files (545 present, 3 ), without permit failure. W107 withdrawn after verification. Test PS4 pending. No local matrix. Detail: [HARDWARE_W108](HARDWARE_W108.md).

Next improvement agreed as consultation: current desktop only shows * .lnk; The actual files/folders requires an extension of the listing / presentation of Explorer. To finish this iteration first; calibration CPU/GPU is still postponed.

<a id="referencia-anterior-w107"></a>


## Previous reference: W107

W106 opens EXE correctly according to the user; Logs 20261102T151517Z confirm PWOPEN open = 1 in thread 0024 and guests PE64. Texts fail without reboot. Cause: associations in HKCU Classes, but HKCR of Wine established consultation HKLM Classes without fusion. W107 (02.06) moves associations to system.reg; do not reward WFM, Explorer or DLL. Built package; hash comparison confirms only the two different records in the runtime. Verified transfer: /data/pkg/orbis-win-W107-df1d1deadc9a.pkg. Report: reports/wine-hardware-w107/transfers/20261102T164351Z.json. 548 verified files (546 present, 2 ), without permit failure. W106 withdrawn after verification. Physical evidence pending. Detail: [HARDWARE_W107](HARDWARE_W107.md). After "I already tried it," collect W107 and check Notepad with text argument, visible content, WFM/EXE and Start.

<a id="referencia-anterior-w106"></a>


## Previous reference: W106

The user confirmed that W105 lists units and files. Open result.txt or vkspin64.txt reboot the title: the log of the 20261102T145327Z session show switch_program with the document, then c000007b and back to the desktop.

W106 (02.05), compiled and uploaded with verified back reading: /data/pkg/orbis-win-W106-02a9368dc02f.pkg. Report: reports/wine-hardware-w106/transfers/20261102T150943Z.json. 548 verified files (536 present, 12 ), no leave failure. W105 withdrawn after verification. Physical evidence pending. WFM sends the opening to the thread of the desktop Explorer by a copy validada/encolada; There. ShellExecuteEx solves the association. The prefix associates texts to Notepad. Kernelbase prevents a document or a guest from fallido/no compatible replace the title. EXE PE64 compatible open threads; PE32 concurrent returns error without reboot. The initial start PE32 And wineboot to get out are separate routes. No change to the emulator. Maintains list W105 and metrics W104; calibration CPU/GPU postponed. Detail and physical evidence: [HARDWARE_W106](HARDWARE_W106.md). On receiving "I've already tried it», fetch-hardware.py --build W106 --host 192.168.68.104. Verify visible text in Notepad, Live WFM, closing and reopening, Start, PWOPEN in thread Explorer and absence of switch_program by documents.

<a id="referencia-anterior-w105"></a>


## Previous reference: W105

The user clears the calibration CPU/GPU and prioritizes File Manager: Computer does not show units. W105 (02.04) adapts GetLogicalDrives in kernelbase to list roots DOS really accessible when WINE_PS4_GUESTS is active; does not depend on the device directory that would fill mountmgr. WFM verifies the handles/resultados listing and list files without ARCHIVE requirements. Logs PWFS/PWFM allow to identify denied access or failed listing.

WFM, guest DLL and package compiled and uploaded with verified reading: /data/pkg/orbis-win-W105-cb9543e2725c.pkg. Transfer report: reports/wine-hardware-w105/transfers/20261102T143252Z.json. 548 verified files (539 present, 9 ), without permit failure. W104 removed from /data/pkg after verification. Physical validation pending. It keeps the metrics and tags CPU/GPU of W104. Detail: [HARDWARE_W105](HARDWARE_W105.md). After testing, use fetch-hardware.py --build W105 --host 192.168.68.104. Check Computer, C:, C:\orbis, cerrar/reabrir WFM and Start. Do not mark functional just by starting the desktop.

<a id="referencia-anterior-w104"></a>


## Previous reference: W104

W103 was executed and its logs downloaded in reports/wine-hardware-w103/physical/20261102T140357Z. Three openings and three closures 0, without a crash marker; desk presenting pictures. No final output or two complete cycles. GPU: 0,356 - 8,909%, losses 0. CPU rejected: 16,666% constant, imported watch advancing as real time.

W104 (02.03) changes CPU to getrusage (RUSAGE_SELF, user + kernel, and displays the tags CPU and GPU without "app," at the user's request. It keeps Crema GPU and sampling on the frame. Built and uploaded with verified back reading; physical evidence pending. PKG: /data/pkg/orbis-win-W104-33b552761826.pkg. Report: reports/wine-hardware-w104/transfers/20261102T141256Z.json. 548 verified files (545 present, 3 ), without permit failure. W103 removed from /data/pkg after verification. PKG SHA- 256: 33b5527618262a29db545d5e108d9e96c63170f513336adf04d4a8315139e87f. Physical test collected: reports/wine-hardware-w104/physical/20261102T141838Z. 90 samples: CPU 6,917 - 32,801 %, GPU 0,08 - 9,5%, no errors or losses GPU. CPU fixed at 16,666% resolved in this session; Both metrics respond to load. Three openings and three closures 0, no crash marker. No final output or two cycles; absolute accuracy without independent calibration. Detail: [HARDWARE_W104](HARDWARE_W104.md).

<a id="entrega-anterior-w103"></a>


## Previous delivery: W103

W103, APP_VER 02.02, compiled and uploaded with verified back reading: `/data/pkg/orbis-win-W103-913c7e7df41b.pkg`. Report: `reports/wine-hardware-w103/transfers/20261102T135850Z.json`. 548 verified files: 545 present and 3 uploaded; no permit failure. W102 removed from /data/pkg after verification. Local evidence preserved.

MangoHud shows CPU app (process / time / initial affinity clock CPU) and GPU app (interval binding GPU Crema real between GFX devices). Warmove, unsupported watch or loss of counters show N/A. Follow the sampling on the frame of W102, without new statistical workers. Versioned private consultation no global or core times are produced. Only system.o of Wine Unix is replaced by a compilation with the consultation; The draft CPU of prepare-wine-boot.py was not executed.

The first physical test rejected CPU and recorded GPU without loss (see above). W102 follows as accepted two-cycle reference. The next test is W104; When you receive "I've already tried it," use fetch-hardware.py --build W104 --host 192.168.68.104 and review PWTELEM/PWHUD, deltas, losses and closures. Detail and commands: [HARDWARE_W103](HARDWARE_W103.md).

<a id="referencia-física-anterior-w102"></a>


## Previous physical reference: W102

W102, APP_VER 02.01, compiled and uploaded with verified back reading to PS4 in 192.168.68.104:2121. Installed and tested: two cycles with the loaded layer, six openings and six closures 0, Start operating and final output 0 at 63455 ms. Acceptance: `reports/wine-hardware-w102/physical/20261102T131731Z/acceptance.json`.

- PKG: `/data/pkg/orbis-win-W102-09be7a07d5eb.pkg`.
- SHA- 256: `09be7a07d5eb38aa1b348d0821c949edefb5fd821f18c9fabca0cac0dbbed42c`.
- Informe: `reports/wine-hardware-w102/transfers/20261102T130927Z.json`.
- Runtime: 548 files, 544 present and 4 uploaded, No permission failures.
- W101 was removed from /data/pkg after verification. Local copies and preserved logos.

[Detalle W102](HARDWARE_W102.md). W101 validated the layer-free control; W102 completed the same scenario with MangoHud loaded. No general stability or validation of long sessions, optional login or percentage accuracy is affirmed.

<a id="evidencia-que-condujo-a-w102"></a>


## Evidence that led to W102

W096 allowed three graphic apps together but appeared failures after closing. W098 CE registration-34878-0 when closing vkcube, with log cut during DLL_THREAD_DETACH of user32 in a worker. W099 removed jins from the shared block and allowed closures and recharges, but after another cycle there was invalid access in native malloc. W100 added mutual exclusion to the SDK: was activated, but did not eliminate the EC-34878-0.

W101 deactivated the load of MangoHud and completed two cycles: six starts and six closures 0 of glxgears/vkcube/vkspin, operational start and final output 0 a 83829 ms. Hud = 0 and absence of PROCESS_ATTACH of libMangoHud were verified. Logs: `reports/wine-hardware-w101/physical/20261102T125705Z/`, with analysis.md. This hinders the route involved, without proving an exact cause or general compatibility.

<a id="cambio-w102"></a>


## Change W102

MangoHud is reenabled (ImplicitLayers DWORD 0). The hardware sampling and the metrics FPS are carried out on the protected frame, without workers holding instance parameters. Disable the file observer: save and restart OrbisDesk to apply settings. PWHUD records sampling = frame, fps_metrics = frame and config_watcher = disabled.

The adaptation avoids these persistent layer services in the guest model within a process. It does not change the general policy of the heirloom of Wine. F2/logging and other optional services are not validated. It can change the cost of the frame; have not been corrected or validated CPU/GPU. Wine Unix, DLL of Wine, driver and heap W100 are preserved.

Sources: `tools/vk-h0/patch-mangohud-frame-sampling.py` over the copy WSL in `~/vk-h0/src/mangohud-win`. The upstream checkout is preserved. The build-up record of MangoHud and the manifesto verify hashes from DLL and compiled sources.

<a id="entorno-y-preferencias-vigentes"></a>


## Current environment and preferences

PS4 Pro Baikal, informed firmware 12.52, GoldHEN Last IP. 104; . 107 was previous. Always use --explicit host. WSL Ubuntu - 22.04 to compile.

The user instala/ejecuta manually; is not used BinLoader to launch these apps. Avoid local matrix: compile and verify artefactos/transferencia and continue with the actual test. Do not mark functional by simulated responses or initial catches. The automatic state presented of the collector does not amount to passed.

After a complete, verified rise, remove the previous PKG Wine from /data/pkg, preserving local evidence and packages. The uploader restricts the nombres/versiones and records results. --timeout is 60 s by default; if FTP stops, reconnects or requests reactivation without declaring the delivery completed.

Notify that the new build is up and present a button I already tested it by request_user_input_async. When you receive it, download and analyze login. Do not start the next physical test before you notice that the delivery was completed.

<a id="prioridad-que-originó-w103"></a>


## Priority that originated W103

The two cycles of W102 were already collected and accepted for the bounded stage. The next priority indicated by the user is to take back the CPU/GPU percentages, now that the closing failure is not reproduced in that test. Keep W102 as a stability reference. To collect a new session of W102:

```sh
python3 tools/fetch-hardware.py --build W102 --host 192.168.68.104
```

The layer load, frame policy, six closures, reopenings, Start and final output were checked. It does not replace a prolonged test. W103 use APP_VER 02.02.

The draft times CPU in tools/prepare-wine-boot.py has NOT been incorporated into these buildings; review your semantics and limits before incorporating it, without running that preparation machine by routine or accidentally mixing it with another correction.

<a id="base-funcional-anterior-y-límites"></a>


## Previous functional base and limits

W013 executed PE32 bare by Wine/wowprospero in PS4 with an identical result to Windows; W014 corrected the output to the menu. There are desktop, mando/USB and applications PE64, Vulkan/RADV and OpenGL/Zink in hardware. [Wine](HARDWARE_W003_W011.md), [graphics](HARDWARE_G001.md). The guests share process; are not independent Windows processes. Presentation Vulkan with copy to CPU/GDI. Geometry shakers general, Direct3D/DXVK, commercial games and performance remain outstanding. The closure with the layer passed the described scenario; follows the telemetry accuracy before extending scope.

<a id="validación-adicional-del-emulador-escritorio-w284"></a>


## Additional emulator validation: desktop W284

The fork Linux already presents the W284 desk in WSLg. General corrections to the charger ET_SCE_EXEC, jumps and libkernel signals; six tests OpenOrbis approved in emulator. Image by copy CPU; PE32 native and RADV/GNM still pending. See [evidence and reproduction](SHAD_W284_DESKTOP.md). This check uses the ELF W284 preserved and does not classify the competing W286 sources as validated.
