# Guest launch compatibility: 04.59 candidate

[English](GUEST_COMPATIBILITY.md) | [Español](GUEST_COMPATIBILITY-es.md)

This candidate preserves the 04.58 performance, renderer-profile and controller changes. It adds per-guest Windows-version and descriptor-pressure fixes, plus corrections to APIs used by games and installer children. Hardware validation is pending.

## Half-Life

Physical run run-0013 on the PS4 Pro Baikal, firmware **12.50**, reached hl.exe and UCRT's _wassert. Its “Wine C++ Runtime Library” dialog reported **g_pFileSystem, launcher.cpp:439**. This was an assertion, not a missing-runtime error.

The installed GoldSrc FileSystem_Stdio.dll has PE SizeOfImage=0x10000. The run recorded a filesystem_stdio.dll of 0x5e000, consistent with the Source DLL used by earlier games. Wine used the world's host EXE as its application directory, while SetDllDirectory is shared.

LdrGetDllPath now takes the calling guest's EXE directory as the application directory. Explicit APPLICATION_DIR and DEFAULT_DIRS searches use it too. Altered paths, system-only searches and root-process behavior retain their rules. The path is copied under the loader lock. This does not create isolated DLL namespaces.

## Windows version per EXE

Wine Configuration → Applications already provides the selector. Kernelbase now reads HKCU\Software\Wine\AppDefaults\<exe>\Version for the actual guest and applies that guest's manifest/PE version restrictions, instead of Explorer's process-cached answer. GetVersionExA and GetVersion delegate to GetVersionExW.

The imported mapping covers XP through Windows 11. This does not change every Wine/NT version API. Windows' manifest-based compatibility caps still apply.

The result is initialized once per guest, including concurrent calls. Repeated queries do not reopen the registry or rescan resources. Restart that application to apply a changed version setting; a new guest gets a separate cache.

## High file descriptors

A newly received, cacheable regular-file or directory descriptor numbered **512 or higher** uses Wine's existing needs_close path instead of remaining in the client cache. The caller closes the temporary copy after use; the server handle stays valid and later operations can request another copy.

Lower descriptors and other types retain their policy. This neither evicts existing cache entries nor raises the kernel limit. PWFS fd_cache off records first use. Fresh boot preparation and the world builder share one context-checked transformation; the title and separate-process helper consume the rebuilt object.

## Installer children

The [reported WiX Burn failure](https://github.com/jl-casella/OrbisDesk/issues/64) involves a clean-room relaunch and inherited file handles. The prefix already contains VC++ runtimes.

The candidate corrects these shared-process API problems:

- UCRT's narrow/wide WinMain helpers parse each guest's arguments without reading or overwriting the root process's cached pointer.
- During child loading, command-line and module queries used by DLL initializers select the loading child rather than its parent.
- DuplicateHandle recognizes registered guest process end events as references to the shared host handle table. It performs real duplication and preserves access, inheritance, close-source flags and errors; arbitrary events remain invalid process handles.
- GetProcessId recognizes those registered handles and reports the shared PID already returned by CreateProcess. TerminateProcess distinguishes the current guest's end event from another guest's handle, so the shared PID cannot turn a child-termination request into parent termination.

PWBURN startup checks the child's command-line identity; PWBURN inherited checks actual attached/self file-handle validity before entry. These diagnostics do not print complete command lines. No installer is replaced by a successful stub and no installed-prerequisite registry values are fabricated.

These fixes do not implement native Steam's missing install-script executor ([issue 63](https://github.com/jl-casella/OrbisDesk/issues/63)), full process isolation or general inherited-handle virtualization. Burn, MSI installation and GTA IV still need end-to-end console validation.

## Validation

The host test tests/test_guest_launch_compat_host.py applies the canonical transformations to pinned Wine sources and executes the resulting functions under AddressSanitizer/UndefinedBehaviorSanitizer with boundary models. It covers descriptor thresholds/types, root/parent/child WinMain arguments, quoting, loading-child identity, real duplication arguments/errors, DLL search modes and per-EXE version/manifest selection. PE32/PE64 compilation checks the actual Wine ABI separately.

It also checks version-cache reuse and failed-initialization retry, PID queries, and the guard against mistaking a child's process handle for the parent's own process.

After installing the candidate and matching runtime, test Half-Life first after restarting OrbisDesk, then after closing another Source game. For GTA IV, select Windows 10 for the relevant launcher EXE in Wine Configuration and retry the real prerequisite installer. Review PWGUEST version, PWFS, PWBURN, installer logs and guest exits together. Host checks and compilation are not PS4 acceptance.

## 04.60: packed-pixel presentation

The user reached Half-Life in 04.59 but reported green/magenta colours, windowed presentation and a desktop freeze after exit. Physical run-0026 reported VK_FORMAT_A4R4G4B4_UNORM_PACK16 (1000340000): a 640-pixel row had 1,280 bytes. The presentation bridge treated it as 32-bit pixels, submitted a stride of 320 pixels and triggered global GPU-composition fallback. GDI also treated those packed pixels as 32-bit BGRA. Half-Life's own teardown completed with status 0; a responsive displayed desktop was not established.

04.60 converts supported packed 4444, 565 and 5551 frames to BGRA in persistent, GPU-readable storage owned by the window. Storage is reused across frames, resized safely and released when the swapchain is forgotten or the window is destroyed/purged. The compositor waits for GPU completion before returning; conversion/reuse and teardown stay under its screen lock. The existing image-layer metadata and fullscreen fitting remain available. Existing 32-bit BGRA/RGBA frames retain their zero-copy path.

Format, dimensions, stride and size arithmetic are checked before publishing image-layer state. Unsupported or malformed input cannot submit an invalid layer and disable the desktop compositor. GDI fallback uses the same conversion, with a tightly packed 32-bit row and a temporary buffer consumed before it is freed. PWPIXELS layer reports the source format/stride and conversion; PWPIXELS rejected reports bounded invalid-input diagnostics. This does not extend frame generation to packed 16-bit sources.

The host test tests/test_present_pixels_host.py executes the converter and prepared driver entry points under ASan/UBSan: primary colour/alpha vectors, padded and unaligned rows, retained-buffer ownership, allocation failure, resize, stale swapchain notifications, child-window lookup, rejection without GPU fallback, the unchanged 32-bit path, and repeated close/reopen. Window teardown paths are also checked for release. Successful native compilation and these checks do not establish PS4 acceptance. Colour, fullscreen, exit and desktop responsiveness still require a new physical test; no separate desktop deadlock fix is claimed.

## 04.61: bound retained client file descriptors

In the 04.60 test the user reached Half-Life gameplay. Run-0029 records the new packed-pixel conversion and no GPU-composition fallback; a normal close/reopen cycle was not recorded. GTA IV run-0031 rendered through DXVK but logged EMFILE while opening map/interior directories, followed by 200 failed read lookups. There were 664 visible descriptors at the first failure, including 271 regular files, 205 pipe ends and 155 sockets; RLIMIT_NOFILE reported 13,952. The exact kernel resource behind EMFILE is not established. Later loader-lock waits occurred after forced game termination and WFM teardown, not before the loading stall.

The fd-number threshold from 04.59 is insufficient to bound client copies. 04.61 limits each native client's retained regular-file/directory copies to 64, under Wine's existing fd-cache mutex. Additional copies use the existing needs_close contract and are closed by the operation that acquired them; the server handle and its file position, sharing and access rules remain intact. Cached copies are never evicted while another thread may be borrowing them. Normal handle close/close-source duplication releases the budget slot; sockets and other descriptor types retain their policy, and the >=512 rule still applies.

Transient descriptor/memory resource errors are no longer stored as permanent negative fd-cache entries. PWFS fd_cache budget marks the first budget bypass; PWFS fd_lookup_failed reports at most 16 resource failures with status and retained-copy count. Native EMFILE reports remain visible. More uncached operations require extra server requests; this tradeoff and the recovered console margin need measurement.

tests/test_fd_budget_host.py executes the prepared Wine cache and acquisition functions under ASan/UBSan. A real host descriptor limit of 256 reproduces unbounded exhaustion; the bounded path serves 160 simultaneously open server files, preserves concurrent borrowed-descriptor use, retries transient failures and releases all slots through repeated cycles. This is host evidence. GTA IV loading, physical descriptor headroom and shutdown remain pending console validation. Launcher path errors, Social Club IPC/browser errors and the redistributable's remaining Riched20 initialization failure are separate unresolved issues; this candidate does not claim to fix them.

## Follow-up after the 04.61 test

The user reported that GTA IV still looped on loading. Run-0034 again logged EMFILE on map/interior paths at 658 visible descriptors, followed by 185 failed read lookups. No budget-bypass marker appeared, so a pressure reduction from the 64-copy policy was not demonstrated. The logged Vulkan trampoline address matches the archived 04.61 binary and differs from 04.60; installed SFO/SELF files were unavailable through FTP. This is correlation, not a read-back hash of the installed binary.

At the first EMFILE/ENFILE, the follow-up adds PWFS pressure (adapter records grouped by client/server origin, duplicates, game and IPC-file paths), PWFS cache_snapshot (current/peak retained copies and budget bypasses) and PWFS kernel_open_control. Adapter origin is not exclusive ownership: SCM_RIGHTS shares open-file descriptions and not every received descriptor has an adapter record. The kernel control opens the failing path read-only with raw flags 0 and closes only that new descriptor. It is not a retry of the requested operation, never repeats create/truncate flags, and does not change the error returned to the game. The snapshot uses atomic mirrors without taking the client mutex while the server may be serving that client. Existing descriptor-kind and RLIMIT reports remain visible. Further failures do not repeat the full scan/control probe.

Half-Life run-0032 enabled frame generation but logged PWFG skipped image for its packed 16-bit source: pitch 2560 for 1280 pixels. The colour conversion happened later in the driver, after the generator's capture hook. The follow-up defers packed-source capture until the driver has produced its existing window-owned BGRA layer. Capture and the display scheduler use that same pointer; there is no second conversion or duplicate source-present count. Direct 32-bit capture stays in place. The separate-process child publishes its converted layers through the existing bridge and does not run a second generator. Displayed-FPS publication still requires generated frames actually shown; FPS VK continues counting real game presents.

Focused host tests cover the converted-frame bridge, stale callbacks, disabled/uncapped/shadow cases, capture failures, unchanged 32-bit capture, first-failure diagnostic bounds, original errno, and the read-only kernel control. Filesystem regression checks compare against the archived 04.61 source with ASan/UBSan; the old fixture's ENOTSUP expectation for directory rename was updated to the already implemented rename/open-directory contract. Native compilation is separate from physical acceptance. GTA IV resource diagnosis and Half-Life generated/displayed frames require a new console run.

## 04.93: Burn bundles started from the Package Cache

Uninstalling or repairing a WiX Burn bundle from Add/Remove Programs failed. The VC++ redistributables, for example, exited with status 0x80070006 (E_HANDLE) or 1460 and showed no UI (04.92, run-0249 and run-0250 of 20261126T203327Z).

From another folder, Burn copies itself to `%TEMP%\{guid}\.cr\` and starts that copy as its clean-room child. From `C:\ProgramData\Package Cache` it starts the child from its own image. One image is one module in this title, so W210 started that child only after the parent had ended. The parent, however, waits for its child. After 15 seconds (`PWGUEST relaunch ... parent_wait=258`), W252 ended the parent because it had no visible window. Ending it closed its files, including the `-burn.filehandle.self` file the child had inherited (`PWGUEST files ... closed=2`). `PWBURN inherited kind=1` then reported the handle as closed (`valid=0 error=6`) or with its value reused by a non-inheritable object (`flags=0`), and the child failed reading its own bundle. Starts from other folders, such as the Rockstar Games Launcher's, never reached this path: their child ran from `.cr` at another base and kept `flags=0x1`.

A guest that starts its own image with a `-burn.` switch on the command line now gets a private copy of that image in `%TEMP%\OrbisDesk-burn-<thread>-<tick>\`, as Burn makes for itself elsewhere. The copy loads as another module beside the running parent, and the parent's inherited handles stay open. A thread waits for the copy's guest to end and then removes the copy (`PWBURN own_image`, `PWBURN copy_removed`). If the copy cannot be made, the start continues as before. Other programs that restart themselves still use W210.

The change was checked by generating the guest overlay and compiling kernelbase for x86_64 and i386. A console test is still required: uninstall and repair the x86 redistributable from Add/Remove Programs. The log should show `PWBURN own_image`, then `PWBURN inherited kind=1 valid=1 flags=0x1`, no `relaunch_later`, and Burn's own UI.
