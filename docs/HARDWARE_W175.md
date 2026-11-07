<a id="w175-memoria-directa-para-los-compromisos-grandes-fase-6-y-temas-clarooscuro-fase-7"></a>


# W175: direct memory for large commitments (phase 6) and themes light/dark (phase 7)

[English](HARDWARE_W175.md) | [Español](HARDWARE_W175-es.md)

APP_VER 02.74. Base W174. The result of W174 is in `docs/HARDWARE_W174.md`.

<a id="memoria-directa"></a>


## Direct memory

**The problem** (W174): the title has ~ 400 MB flexible memory and ~ 4,6 GB free direct memory, and SuperMarioKart needs more flexible memory than there is.

`tools/build-audio-ps4.py`, `virtual.c` of ntdll, only in Orbis:
- **Large commitments:** a commitment of 1 MiB or more mapping direct memory (`sceKernelAllocateDirectMemory` type WB_ONION and `sceKernelMapDirectMemory` fixed) on each uncompromised section.
  - Each section is recorded with its offset in a table of 8192 entries.
  - It is recorded `PWVM commit … direct runs=…`, so the kernel reports from the region and totals.
- **Release:** `unmap_area` and the decommit (`pw_rereserve`) first return the direct memory of the range with `sceKernelReleaseDirectMemory`, also by parts.
- **If you fail:** if the reservation or mapping fails, or the table is full, the compromise is still by flexible memory as before, with `PWVM direct map … failed`.

`platform/ps4/pw_wine_platform.c`, `commit_reserved`: does not map flexible memory over a region that the kernel reports as direct memory, although it does not mark as compromised.

It is expected that SuperMarioKart will finish the race and leave without `PWVM fault`.

<a id="temas-claro-y-oscuro-y-aero-fase-7-sesión-de-accesos-directos"></a>


## Clear and dark themes, and Aero (phase 7, direct access session)

<a id="punto-de-partida"></a>


### Point of departure

- The dark look of OrbisDesk is not a visual style: it is the colors of the system that `build-wine-hardware.py` writes in `HKCU\Control Panel\Colors` (W045).
- In winecfg, Desktop integration:
  - the list of topics showed only "(No theme)": it looks for visual styles (`.msstyles`) in `C:\windows\resources\themes`, and that folder was empty;
  - "Install theme..." accepts `.theme` files and then applies its section `[Control Panel\Colors]` (`do_parse_theme`, `programs/winecfg/theme.c`).
- Wine It doesn't bring a dark visual style. His only style is `aero.msstyles`, Sure. The application theme selector light/dark Just keep `AppsUseLightTheme`, that uxtheme informs the programs that they consult it; does not change controls.

<a id="cambios"></a>


### Changes

- `tools/build-wine-hardware.py`:
  - writes `C:\windows\resources\themes\Orbis Oscuro.theme` (the current colors, of the same dictionary `DARK`) and `Orbis Claro.theme` (the default colors of Windows 10);
  - if the two schemes do not name the same colors, the build stops;
  - copy `aero.msstyles` to `C:\windows\resources\themes\aero\`, as `wine.inf`. It is not activated: `ThemeManager` it is as it was.
- `tools/stage-wine-extras.py`: sum `aero.msstyles`, that of the fixed tree x86_64, 7,2 MB. It is a single file for both views, because uxtheme opens it as a resource.
- `tools/upload-hardware.py`: the fusion of `user.reg` (W172) now conserves from the console, each with its subkeys:
  - `Software\Wine\AppDefaults`;
  - `Control Panel\Colors`;
  - `Control Panel\Desktop\WindowMetrics`;
  - `Software\Microsoft\Windows\CurrentVersion\ThemeManager`;
  - `Software\Microsoft\Windows\CurrentVersion\Themes\Personalize`.
  - The record of the rise becomes `user_reg.console_blocks_kept` (per key) and `user_reg.reset`.
- Tested without connection:
  - the fusion, against the `user.reg` of W173:
    - without user changes gives the same file;
    - with clear theme, Aero and program adjustments on the console, it keeps all three, and DLL overrides remain those of the build;
    - a second rise does not change anything;
  - The two `.theme` have 31 colors each, for the purpose of CRLF line.

<a id="colores-en-manos-de-la-consola"></a>


### Colors in the hands of the console

- From the first installation of W175, the colors, the metrics, the visual style and the application theme are those of the console: a build no longer changes them even if it changes `DARK`.
- If a build needs to change them (for example, a corrected dark scheme), it puts in its manifest, only that time: `manifest['user_reg_reset']=['Control Panel\\Colors']`
  - That climb takes that key from the build. The others, including the AppDefaults, continue to come from the console. `user_reg.reset` records it.
  - Accepts only keys from the above list; Any other one stops the climb.
- No need to delete `user.reg` with `obsolete_files`: it would also take the program settings.
- It continues to value the limit of W172: you have to close the app before installing.

<a id="prueba"></a>


### Test

1. winecfg → Desktop integration → "Install theme..." → `C:\windows\resources\themes\Orbis Claro.theme` → Apply. Windows, menus, taskbar and Start menu have to be seen in clear.
2. The same thing with `Orbis Oscuro.theme`: back to the present look.
3. List of topics: "Aero" has to appear.
   - Choose it, with the clear scheme, and see how buttons, boxes and scroll bars are drawn.
   - Look if you notice it slower, for example when opening the Start menu or moving windows.
   - Volver a "(Sin tema)".
4. Leave the theme clear, close the app and install the following build: you have to remain clear, with `user_reg.console_blocks_kept` in the upload record.

Risks:
- Aero draws the controls with bitmaps through the uxtheme, in the CPU. It may be slower, and it is mixed with the dark scheme.
- Some specific drawings of explorer (the Start and Run and Exit glyph) were thought on the dark background; We must see if they can be distinguished.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w175/physical/20261103T202505Z/`. Answer: "Another problem"; According to the user, SuperMarioKart "was closed before, after selecting character in the menu."

- **Direct memory:** works, without any `PWVM fault` or `PWVM direct map … failed`.
  - The kernel reports the regions as `flags=0x12` (direct memory, compromised).
  - By departure there were some 20 reserves, 14 releases and 6 living entries, about 62 MB.
- **New failure**, in the three games at 75 - 85 s, when loading the track:
  - `d3dxof_parsing:parse_template_members_list Array cannot be used to specify variable array size`;
  - then, `c0000005` in `0x1006BB3A`, inside the game, and the game comes out with status 0.
  - The error appears only in W175, just after a direct commitment of 2,4 MB (`base=0x8910000 size=0x260000`).
  - The direct memory does not come in zero, and Windows delivers in zero the compromised memory. The parser of `.x` read remains of memory. It is corrected in W176.
- **Themes:** the user asked for changes to the direct access session.
