<a id="w175-temas-claro-y-oscuro-y-aero-en-winecfg-fase-7"></a>


# W175: clear and dark themes, and Aero, in winecfg (phase 7)

[English](HARDWARE_W175-borrador.md) | [Español](HARDWARE_W175-borrador-es.md)

APP_VER (complete main session). Base W174.

Eraser of the subject part. The main session adds up to your change of W175 (direct memory for large commitments).

<a id="punto-de-partida"></a>


## Point of departure

- The dark look of OrbisDesk is not a visual style: it is the colors of the system that `build-wine-hardware.py` writes in `HKCU\Control Panel\Colors` (W045).
- In winecfg, Desktop integration:
  - the list of topics showed only "(No theme)": it looks for visual styles (`.msstyles`) in `C:\windows\resources\themes`, and that folder was empty;
  - "Install theme..." accepts `.theme` files and then applies its section `[Control Panel\Colors]` (`do_parse_theme`, `programs/winecfg/theme.c`).
- Wine It doesn't bring a dark visual style. His only style is `aero.msstyles`, Sure. The application theme selector light/dark Just keep `AppsUseLightTheme`, that uxtheme informs the programs that they consult it; does not change controls.

<a id="cambios"></a>


## Changes

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

To build: `tools/stage-wine-extras.py` (already running) before `tools/build-wine-hardware.py`.

<a id="colores-en-manos-de-la-consola"></a>


## Colors in the hands of the console

- From the first installation of W175, the colors, the metrics, the visual style and the application theme are those of the console: a build no longer changes them even if it changes `DARK`.
- If a build needs to change them (for example, a corrected dark scheme), it puts in its manifest, only that time: `manifest['user_reg_reset']=['Control Panel\\Colors']`
  - That climb takes that key from the build. The others, including the AppDefaults, continue to come from the console. `user_reg.reset` records it.
  - Accepts only keys from the above list; Any other one stops the climb.
- No need to delete `user.reg` with `obsolete_files`: it would also take the program settings.
- It continues to value the limit of W172: you have to close the app before installing.

<a id="prueba"></a>


## Test

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
