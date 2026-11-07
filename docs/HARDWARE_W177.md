<a id="w177-limpieza-de-los-diagnósticos-de-la-carrera-fase-6-temas-luna-y-noir-fase-7-y-navegador-fase-9"></a>


# W177: cleaning of career diagnoses (phase 6), Moon and Noir themes (phase 7) and browser (phase 9)

[English](HARDWARE_W177.md) | [Español](HARDWARE_W177-es.md)

APP_VER 02.76. Base W176. The result of W176 is in `docs/HARDWARE_W176.md`.

<a id="limpieza-de-los-diagnósticos-de-memoria"></a>


## Cleanup of memory diagnoses

The end-of-the-race failure of SuperMarioKart was resolved in W176. The records that were added to find it (W170 - W175) are removed, at the user's request:

- **`tools/build-audio-ps4.py` (`virtual.c`):**
  - The `PWVM fault` diagnosis of `virtual_handle_fault` (W170/W171) comes out, with the consultation of the kernel before and after and the single reattempt.
  - The summaries `PWVM commit …` of each commitment of 1 MiB or more, with `flexible_free` and the direct memory totals, and their counters, are released.
  - The `commit_backing` line of the 32 first pages comes out.
- **`tools/build-win32u-ps4.py` (`vulkan.c`):** come out `PWVK placed map` and `PWVK placed free` (W170). The alias's mapping is rerecorded only if it fails, as in W169.

They remain as traces of error, because they only appear when something fails:
- `PWVM direct map … failed` and `PWVM direct release … failed`;
- `PWVM commit_backing` when the mapping of a page fails;
- `PWVM rereserve … falling back`;
- `PWVK placed unmap … failed`.

The arrangements remain the same: direct memory to zero for large commitments, return when you release, re- reserve, region check on the commitment, store in `commit_reserved`, `TerminateThread(NULL)` and Mesa resident.

<a id="navegador-y-webviews-fase-9-sesión-del-navegador"></a>


## Browser and webviews (phase 9, browser session)

It depends on the phase 8 only for remote pages. Since W176 DNS, TCP, HTTP, UDP and adapters work in 64 and 32 bits. The local page and the embedded control can be tested without a network.

<a id="qué-había-leído-en-el-código-y-en-el-prefijo-de-w173"></a>


### What was there (read in the code and in the prefix of W173)

1. **MSHTML was not installed.** `mshtml`, `jscript`, `msxml3` e `iexplore` are compiled in `.deps/wine/runtime/build` (x86_64 and i386), but are not either in `system32` or `syswow64`. `ieframe`, `shdocvw`, `urlmon` and `wininet` are.
2. **Incomplete record.** In `system.reg`, the control WebBrowser (`{8856F961-…}`, ieframe) is registered only for 64 bits. mshtml and jscript are not registered in either view. A program of 32 bits looks for classes in `Classes\Wow6432Node\CLSID` and found none of these.
3. **Wine Gecko** Wine 11.17 Gecko 2.47.4 (`dlls/appwiz.cpl/addons.c`). mshtml first seeks `HKLM\Software\Wine\MSHTML\2.47.4` `GeckoPath` (`dlls/mshtml/nsembed.c`, `find_wine_gecko_reg`). If you don't find it, you run `control.exe appwiz.cpl install_gecko` with `CreateProcess`, and that doesn't work in a single-process title.
4. **There is no TLS of Windows.** `SONAME_LIBGNUTLS` is not defined in the `config.h` Orbis. schannel and bcrypt don't have Unix side. That's why MSHTML, wininet e `iexplore` cannot open HTTPS. Pale Moon bring your own TLS (NSS), so it doesn't affect you..
5. **Guest of 64 bits.** The guest shares the dxgi builtin with explorer (phase 7), so a browser of 64 bits cannot use D3D11 of DXVK. In addition, `struct ps4_guest` keeps 64 threads (`tools/build-guest-hw.py`). If the program creates more, the spare threads are not recorded and continue to run after the guest ends.

<a id="navegador-elegido-pale-moon-3503-x64-sin-incluirlo-en-el-paquete"></a>


### chosen browser: Pale Moon 35.0.3 x64, not included in the package

- Goanna engine (UXP), of a process. Current Firefox and Chromium are multi-process.
- The Pale Moon (palemoon.org/redist.shtml redistribution license requests prior permission from Moonchild Productions to include it in a larger package. It also prohibits changing your files and your default preferences. That's why it's not in the pkg. The user puts his copy in `C:\Program Files\Pale Moon\` (on the console, `drive_c/Program Files/Pale Moon/` inside the prefix).
- Direct access passes a profile of its own with `-no-remote -profile …`. The preferences go in the `user.js` of that profile (`fixtures/browser/`) and do not touch Pale Moon.
- There are two profiles:
  - `orbis`: no acceleration. Do not use D3D11, Direct2D, WebGL or video decoding by GPU. Neither does anything that opens another process: plugins, plugin-container of GMP or the update. The memory and cache are tied.
  - `orbis-nojit`: the same profile with JIT of JavaScript off. It serves to rule out a failure from JIT, which writes code in executable memory.
- Review of imports, without console: `palemoon-35.0.3.win64.7z` (SHA- 256 `745ba383…dbb65b`), all PE against `system32` of W173 and the builtin folder.
  - It's missing `usp10.dll`, `wsock32.dll` and `wtsapi32.dll`. All three are compiled on the fixed tree and now install them `stage-mshtml-hw.py`.
  - `xul.dll` it matters `d3d9.dll` statically. Load the d3d9 of DXVK, but with the acceleration off it does not use it to compose.
- K-Meleon 76.5.5 (GPL/MPL) was left as an alternative. It's just 32 bit, so I'd run as a relegated title, and it's the only way to have D3D11 by DXVK. It wasn't unloaded.

### Webviews

- **MSHTML (IE of Wine) with Wine Gecko 2.47.4**, for 64 and 32 bits. It covers the old programs that embody IE's control.
  - Gecko goes where he would put his `.msi`: `C:\windows\system32\gecko\2.47.4\wine-gecko-2.47.4-x86_64` and `syswow64\…\wine-gecko-2.47.4-x86`.
  - `GeckoPath` goes on both views of the record. A program of 32 bits sees `syswow64` as `system32`.
  - Gecko occupies about 108 MB (x86_64) and 109 MB (x86) in the prefix.
- **Without HTTPS in MSHTML** (point 4 above). Only `file:`, `about:`, `res:` and `http:`.
- **Unrecorded type libraries** (`mshtml.tlb`, ieframe type). A program that requests the type library to oleaut32 (scripts, VB6, marshaling between apartments) receives `TYPE_E_LIBNOTREGISTERED`. The control embedded from C/C++ on the same thread does not need it.
- **WebView2 (Edge/Chromium): not supported.** Open separate processes (browser, renderer, GPU) And there are no processes here Windows apart. Nothing is installed for WebView2. A program that requires it fails when creating the environment (`CreateCoreWebView2Environment`), with the charger error of WebView2.

<a id="cambio"></a>


### Change

|File|What are you doing?|
|---|---|
|`tools/stage-wine-gecko.py` (new)|Check the two tarbals for SHA- 256, remove them with route check (only regular files within `wine-gecko-2.47.4-<arch>/`) and check that `VERSION` says `Wine Gecko 2.47.4`. Write `out/wine-gecko/` with a manifesto (hash of each file and `builder_sha256`).|
|`tools/stage-mshtml-hw.py` (new)|Copia mshtml, jscript, mshxml3, mshml.tlb, iexplore, usp10, wsock32, wtspi32 and netapi32 (in 32 bits, also msimg32 and uxtheme, which matters Gecko x86), each with its import closure, except for what is already in the prefix or other manager. Generates COM record as it would `DllRegisterServer`, without running Wine: the resources scripts `WINE_REGISTRY` for each DLL (read as `dlls/atl/registrar.c`) and `mshtml.inf` (`RegInstall`, with the CLSID of `mshtml_classes.idl`, `mshtml.idl` and `mshtml_private.h`). In 32 bits, `CLSID` e `Interface` go to `Classes\Wow6432Node` and `HKLM\Software` a `Software\Wow6432Node`. It does not repeat values that the `system.reg` sealed already has.|
|`fixtures/win32/webview.c` (new)|`webview64.exe` and `webview32.exe`. See below.|
|`fixtures/web/index.html` (new)|Local test page: an ES5 (`#es5`) script, an ES2020 (`#es2020`), cams, grid, flex, user agent and time of scripts. The two scripts are separated: a syntax error in the ES2020 does not stop the ES5.|
|`fixtures/browser/palemoon-user.js`, `palemoon-nojit-user.js`|The two profiles of Pale Moon.|
| `tools/make-start-menu.py` |Folder `Programs/Internet`: Pale Moon, Pale Moon (no JIT), Internet Explorer (opens the local page), WebView test (64 -bit) and WebView test (32 -bit).|
| `tools/build-guest-hw.py` |`struct ps4_guest` save 256 threads instead of 64. If it is filled, leave `PWGUEST thread_overflow module=… count=…`.|
| `tools/build-wine-hardware.py` |Install MSHTML and Gecko, add `GeckoPath` and `system.reg.add`, compile the two fixtures, copy the page to `C:\orbis\webtest` and create the two profiles in `C:\users\orbis\AppData\Roaming\Moonchild Productions\Pale Moon\Profiles\`.|
| `THIRD_PARTY.md` |Wine Gecko (MPL- 2.0, not modified) and why Pale Moon is not included.|

The changes in the three shared builders are applied (W177 go). There are no changes in `platform/ps4` or ELF.

### Fixture `webview64.exe` / `webview32.exe`

It is a minimum OLE container (client site, in-place site and frame of a window) with the control WebBrowser inside. Each step adds a line to `C:\orbis\webview-result.txt` with your HRESULT:

| Paso |What proof?|
|---|---|
| `ole` | `OleInitialize` |
| `create` |`CoCreateInstance(CLSID_WebBrowser)`: the record of the class in the right view|
| `activate` |`SetClientSite` and `DoVerb(OLEIVERB_INPLACEACTIVATE)` in the window|
| `local` |`Navigate2` to `C:\orbis\webtest\index.html` and messages up to `READYSTATE_COMPLETE` (30 s maximum), with state and milliseconds|
| `title` |Document title. It is expected `orbis-webtest`; it's empty if Gecko didn't load|
| `es5` |Text of `#es5`. It is expected `es5-ok` if jscript ran|
| `es2020` |Text of `#es2020`. Expected `not run`: jscript does not have ES2020|
| `remote` | The same navigation to the argument 1 (`http://example.com/` default; `-` it sauté). It needs network |

A step that can't run because a previous one failed is like `skipped=…`, never like ok. The window is open with the page until it is closed. Compile with mingw (`-O2 -Wall`, 64 and 32 bit): without notice. It wasn't executed.

<a id="construcción-orden"></a>


### Construction (order)

1. `python3 -I tools/stage-wine-gecko.py` → `out/wine-gecko`
2. `python3 -I tools/stage-mshtml-hw.py` → `out/mshtml-hw`. Read the manifests of `out/wine-pe64`, `wine-gui`, `wine-programs`, `wine-extras`, `wine-i386` And `dmsynth-i386`, so it goes after your stagers.
3. `python3 tools/make-start-menu.py`
4. `python3 tools/build-guest-hw.py` (thread limit; ntdll and kernelbase of guests)
5. `python3 tools/build-wine-hardware.py`

No need for `link-wine-boot.py` or `build-unixlibs-ps4.py`. The first rise of W177 takes longer than the previous ones: Wine Gecko adds up about 217 MB.

Test in copy (writing in the scratchpad): `stage-mshtml-hw.py` gave 10 modules of 64 bits and 11 of 32 bits, no unsolved imports, 1770 keys and no sealed value replaced. The WebBrowser control of 32 bits is left in `ieframe.dll`, as is the control of 64 bits that left wineboot. `make-start-menu.py` gave 20 direct access (before 15). The four built-in build-ups compete as Python; The new C of `build-guest-hw.py` was not compiled (that's what the builder does).

<a id="qué-buscar-en-el-log"></a>


### What to look for in the log

- `Could not find Wine Gecko. HTML rendering will be disabled.`: `GeckoPath` was not read or the folder does not have the expected `VERSION`.
- `Gecko can only be used from one thread.`: two threads use MSHTML. It happens if two 64 bit guests use control at once, because they share the process.
- `PWGUEST thread_overflow`: the guest passed from 256 threads (point 5).
- `c0000135` when you open Pale Moon: one DLL missing. The import review did not find any, but `xul.dll` charges others in execution time (`LoadLibrary`).

<a id="no-verificado--riesgos"></a>


### Not verified / risks

- **Nothing was tested on the console** or in a Wine host.
- **`xul.dll` doubled:** the `xul.dll` of Pale Moon And Gecko's have the same name. If a guest uses MSHTML and Pale Moon is open, they would both be in the same process. It is not clear what the Wine charger does with two modules of the same name loaded by full route.
- **mozgue hitch `LdrLoadDll`** (DLL blocking list) in the ntdll process, which is the one to explore. If that fails or gets hooked after closing the browser, it affects to explore.
- **Memory:** the console reports some 447 MB flexible memory for the whole title. A heavy page may not come in.
- **Wire:** in W177 the limit per guest rises from 64 to 256. If it is still filled, it remains `PWGUEST thread_overflow` in the log and that thread keeps running after the guest ends.
- **JIT:** SpiderMonkey changes the protection of running pages all the time. If there are generated code failures, the `orbis-nojit` profile is used to separate them.
- **Profiles and uploads:** `upload-hardware.py` just upload the build files. In each profile, that is just `user.js`, which belongs to the build and is replaced in each climb. What you write Pale Moon (`prefs.js`, history, markers) is not in the build and is preserved. A preference that you want to maintain goes in `prefs.js` (from `about:config`), not in `user.js`.
- **No acceleration in 64 bits** while guests share the scout dxgi.

<a id="prueba-física"></a>


### Physical test

Pending. Proposed order:

1. **No network:** WebView test (64 -bit) and (32 -bit). It is expected `create` / `activate` in 0, `local` complete, `title` = `orbis-webtest`, `es5` = `es5-ok`, and the page visible in the window. Then, Internet Explorer from the menu: open the local page.
2. **With network** (W176: DNS, TCP, HTTP, UDP and adapters in 64 and 32 bits): the step `remote` of the two fixtures (`http://example.com/`).
3. **Pale Moon** (with the user's copy in `C:\Program Files\Pale Moon`): open with the `orbis` profile, see the local page (expected `es5-ok`, `es2020-ok` and `canvas-ok`) and close. Re-open to check that explorer is still well after closing. Then, real sites (HTML5, modern JS, TLS 1.3) with each one's loading time. If it falls, repeat with `orbis-nojit`.

<a id="temas-luna-y-noir-sin-estilo-por-defecto-fase-7-sesión-de-accesos-directos"></a>


## Moon and Noir themes, without default style (phase 7, direct access session)

<a id="pedido-y-resultado-de-w175"></a>


### Order and result of W175

- The user asked for the themes of Windows XP (Luna) and Royale Noir, as similar as possible to those of Microsoft, and Aero by default.
- After he tried W175 he said that Aero felt slower. Therefore the default value was **without visual style**.

<a id="luna-y-noir"></a>


### Moon and Noir

- Microsoft's `.msstyles` cannot be redistributed. These are their own, armed from the `aero.msstyles` of the Wine fixed (LGPL), with `tools/build-msstyles-hw.py` (new).
- For each style, the builder:
  - copy the sources of Aero to a overlay;
  - recolor all bitmaps with the style palette;
  - draw again, state by state and with the sizes and arrangement of Aero, 32 bitmaps: buttons, boxes, option buttons, scroll bars (buttons, thumb, channel), tabs, list headers, editing and combo edges, and groupbox.
- **Moon:** buttons with dark blue edge and white to beige face, orange glow when passing the mouse and blue edge on the default button. Box with green tilde, option buttons with green dot, blue lavender displacement bars, lashes with orange top edge, progress bar in green blocks.
- **Noir:** bright black buttons, dark boxes with white tilde, graphite displacement bars and continuous progress bar.
- The INI of each style has its name ("Moon," "Noir") and, in `[SysMetrics]`, the colors of the system of XP Luna and Royale Noir. xxtheme applies them when choosing the style.
  - Moon: Blue degrade bar, blue edges, beige dialogues.
  - Noir: black title bar, dark grey dialogues.
- Without `TransitionDurations`: Aero has 32 sections with fuses of 100 ms that reprint each control several times by change of state. It's most likely behind the slow.
- It is compiled with the same commands that the fixed build uses for `aero.msstyles` (`make -n`).
- `tools/build-wine-hardware.py` copies them to `C:\windows\resources\themes\luna\luna.msstyles` and `...\noir\noir.msstyles`, with verification of `builder_sha256`. winecfg the list in Desktop Integration.

What Wine does not draw with the theme:
- The title bar, edges and buttons to minimize, maximize and close the draw Wine with the system colors and the classic buttons (`uxtheme/stylemap.c` have only the names). On Moon the blue bar and the blue edges of XP come out, but not the rounded buttons or the red X.
- What does take the style: the displacement bars of all the windows (uxtheme is hooked with `user_api_hook`), the dialog funds and the controls of the programs that ask common controls 6.0, such as winecfg. Explorer use v5 and just take the colors.

<a id="sin-estilo-visual-por-defecto"></a>


### No visual style by default

- The sealed prefix brings in `ThemeManager` `ThemeActive=1` with Aero. Until W174 the file did not exist and uxtheme turned it off; Since W175 a new prefix was starting with Aero.
- `build-wine-hardware.py` puts `ThemeActive` in 0.
- In the console those keys are from the console (W175). If Aero was active, he wrote his clear colors in `Control Panel\Colors`, and turned it off from the record does not restore them.
- That's why this build brings `user_reg_reset = [ThemeManager, Control Panel\Colors]`: that rise takes them from the build (without style, dark scheme) **once**. We have to get him out in W178.

To build: `tools/build-msstyles-hw.py` (already running; `out/msstyles-hw` is up to date) before `tools/build-wine-hardware.py`.

<a id="prueba"></a>


### Test

1. When starting: desk and dark windows, as before W175, without visual style. In the log of the rise, `user_reg.reset` with the two keys.
2. winecfg → Desktop integration → the list of topics has to show Aero, Luna and Noir.
   - Choose Moon → Apply: blue title bar, blue edges, beige dialogues; in winecfg, buttons, boxes, tabs and travel bars in the XP style.
   - The same with Noir.
3. Speed: with Moon and Noir, open the Start menu, move windows, move on a list. Compare with "(No theme)" and with Aero.
4. Back to "(No theme)": dark colors have to return.

Risks:
- Luna and Noir continue to draw with bitmaps through uxtheme, like Aero. Without the fused, they should be better off than Aero, but not as fast as without a subject.
- This is the first time these bitmaps have been seen on the console. There may be details to adjust: sizes, margins, text contrast in Noir.

<a id="prueba-física-1"></a>


## Physical test

Report: `reports/wine-hardware-w177/physical/20261103T211906Z/`. User response: "Browser fails." `webview-result.txt` is copied in `build/w177-webview-result.txt`.

- **webview64:**
  - `ole`, `create` and `activate` give `0x00000000`, i.e. the control is created and activated.
  - The three navigations (local, remote and back) remain at `ready_state=1 complete=no` at 30.
- **Cause:** `xul.dll` from Gecko does not load. He's missing `bcrypt.dll`, which they need `ncrypt.dll` and `crypt32.dll`; `WINTRUST.dll` needs `crypt32`, and xul needs `WINTRUST`.
  - The host tree has only `bcrypt.dll` of i386; There is no x86_64.
  - mshtml records `Failed to init Gecko, returning CLASS_E_CLASSNOTAVAILABLE`.
- **Internet Explorer:** starts as a guest (the `error=1813` is a `GetLastError` old man). Then it fails to create a stub marshaling (`0x80004002`) and has no Gecko to draw with.
- Pale Moon, the themes and SuperMarioKart were not reported.
- The `bcrypt` arrangement (and the Gecko closing review) goes to the browser session, for W178.
