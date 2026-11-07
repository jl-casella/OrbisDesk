<a id="temas-claro-y-oscuro-en-winecfg-plan-borrador"></a>


# Clear and dark themes in winecfg (plan, draft)

[English](HARDWARE_temas-plan-borrador.md) | [Español](HARDWARE_temas-plan-borrador-es.md)

User's request: that the part of winecfg (Desktop Integration) themes work, with a clear theme and a dark one like the current one.

<a id="cómo-funciona-hoy"></a>


## How it works today

- The dark look is not a visual style: it is the colors of the system that `build-wine-hardware.py` writes in `HKCU\Control Panel\Colors` (W045, dictionary `DARK`.
- winecfg has two mechanisms:
  - **Combo of themes:** list `.msstyles` of `C:\windows\resources\themes\*`. The prefix has none, so it just shows "(No theme)."
  - **"Install theme..." with a file `.theme`:** read its section `[Control Panel\Colors]` and apply those colors to the moment (`do_parse_theme` in `programs/winecfg/theme.c`). That is the mechanism that serves as a clear and dark.
- Wine has no dark visual style. Its only `.msstyles` is `aero.msstyles`, of course, with one color ("Blue"). The selector "application theme light/dark" only saves `AppsUseLightTheme`, which `uxtheme` informs the programs that they consult it (`ShouldAppsUseDarkMode`); does not change the controls of Wine.

## Plan

1. **Two colored themes** in `C:\windows\resources\themes\`:
   - `Orbis Oscuro.theme`: the current colors, generated from the same `DARK` dictionary of `build-wine-hardware.py`, so there are no two copies to keep;
   - `Orbis Claro.theme`: the default colors of Windows 10 (white and light grey background, black text, blue selection).
   - Use: winecfg → Desktop integration → "Install theme..." → choose one. It is applied instantly.
2. **That the choice survive the building.** Today `upload-hardware.py` preserves from the console alone `AppDefaults`, so the next rise would put the dark theme back. They add to the list of keys that come from the console:
   - `Control Panel\Colors`;
   - `Control Panel\Desktop\WindowMetrics` (sizes and sources of the same tab);
   - `Software\Microsoft\Windows\CurrentVersion\ThemeManager`;
   - `Software\Microsoft\Windows\CurrentVersion\Themes\Personalize`.
   - Consequence: Once installed, a build can no longer change those colors on its own.
3. **Optional: `aero.msstyles`** in `resources\themes\aero` (compiled in the tree fixed, x86_64), so that the combo of themes will show "Aero."
   - It is a clear visual style: draw the controls with bitmaps through uxtheme.
   - With dark colors it looks mixed, and drawing with bitmaps in the CPU Jaguar can be slower.
   - It comes off; only activated if the user chooses it.

<a id="archivos"></a>


## Files

|File|Change|
|---|---|
| `tools/build-wine-hardware.py` |type the two `.theme` (DARK and a new LIGHT)|
| `tools/upload-hardware.py` |more keys preserved in the fusion of `user.reg`|
| `tools/stage-wine-extras.py` |(if the point 3 goes) `aero.msstyles` and its copy to `resources\themes\aero`|

<a id="prueba"></a>


## Test

1. winecfg → Desktop integration → "Install theme..." → `Orbis Claro.theme`: windows, menus, task bar and clear Start menu.
2. The same with `Orbis Oscuro.theme`: it's back to the same as now.
3. Choose the clear, close the app, install the following build: you have to follow in clear.
4. (If Aero goes) choose Aero in the combo and see how the controls are drawn and if it is noticed slower.
