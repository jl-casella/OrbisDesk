<a id="w177-parte-de-temas-luna-y-noir-y-sin-estilo-visual-por-defecto"></a>


# W177, part of themes: Moon and Noir, and without visual style by default

[English](HARDWARE_W177-temas-borrador.md) | [Español](HARDWARE_W177-temas-borrador-es.md)

Draft of the side session of topics. The main session adds it to `HARDWARE_W177.md` along with the 9 phase.

<a id="pedido-y-resultado-de-w175"></a>


## Order and result of W175

- The user asked for the themes of Windows XP (Luna) and Royale Noir, as similar as possible to those of Microsoft, and Aero by default.
- After he tried W175 he said that Aero felt slower. Therefore the default value was **without visual style**.

<a id="luna-y-noir"></a>


## Moon and Noir

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


## No visual style by default

- The sealed prefix brings in `ThemeManager` `ThemeActive=1` with Aero. Until W174 the file did not exist and uxtheme turned it off; Since W175 a new prefix was starting with Aero.
- `build-wine-hardware.py` puts `ThemeActive` in 0.
- In the console those keys are from the console (W175). If Aero was active, he wrote his clear colors in `Control Panel\Colors`, and turned it off from the record does not restore them.
- That's why this build brings `user_reg_reset = [ThemeManager, Control Panel\Colors]`: that rise takes them from the build (without style, dark scheme) **once**. We have to get him out in W178.

To build: `tools/build-msstyles-hw.py` (already running; `out/msstyles-hw` is up to date) before `tools/build-wine-hardware.py`.

<a id="prueba"></a>


## Test

1. When starting: desk and dark windows, as before W175, without visual style. In the log of the rise, `user_reg.reset` with the two keys.
2. winecfg → Desktop integration → the list of topics has to show Aero, Luna and Noir.
   - Choose Moon → Apply: blue title bar, blue edges, beige dialogues; in winecfg, buttons, boxes, tabs and travel bars in the XP style.
   - The same with Noir.
3. Speed: with Moon and Noir, open the Start menu, move windows, move on a list. Compare with "(No theme)" and with Aero.
4. Back to "(No theme)": dark colors have to return.

Risks:
- Luna and Noir continue to draw with bitmaps through uxtheme, like Aero. Without the fused, they should be better off than Aero, but not as fast as without a subject.
- This is the first time these bitmaps have been seen on the console. There may be details to adjust: sizes, margins, text contrast in Noir.
