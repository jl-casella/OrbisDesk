<a id="fondo-de-barra-y-pruebas-de-start-en-shadps4"></a>

# Taskbar background and Start menu checks in shadPS4

[English](TASKBAR_CENTER_FIX.md) | [Español](TASKBAR_CENTER_FIX-es.md)

The white area in the middle of the taskbar came from Explorer's fallback when
there is no Taskbar theme: `themed=0` was observed. Start and the clock were
painted separately. The WM_ERASEBKGND handler now fills the entire taskbar with
the theme brush or COLOR_3DFACE, then applies DrawThemeBackground when available.
This avoids relying on the class background and also covers partial or failed themes.

The change is in `tools/build-explorer-hw.py`. The isolated diagnostic build is
in `build/taskbar-center-fix/`, with Explorer SHA256
`0b6c0661dbf348f22c5c16f1b8ad9ada9ca7176f9850d465d1abcd38954e5025`.
Only three PE64 copies in W284's private runtime were replaced; the originals
were archived in `reports/taskbar-center-fix/before/`. No PS4 package was rewritten.
Concurrent W286 artifacts were left unchanged.

Test on 2026-11-07, Linux fork, using input from the emulated controller:
Start opens with pointer+Cross; the directional pad navigates and opens Graphics
Tools, Programs, System Tools and Control Panel. Under Programs, Accessories,
Games, Internet and Multimedia also opened. All displayed their entries. All menus
were closed, the desktop was checked, and Start opened again successfully.
The middle of the taskbar remained fully drawn. No programs were launched, so
this navigation test does not establish their compatibility. No W284 crash was recorded.

X11 input to the host mouse was not delivered as a PS4 USB mouse. The
Options/VK_LWIN shortcut did not open Start in this attempt either; it is not
classified as passing. These captures and checks used effective controller clicks
and directional input. Windows control failed to activate WSLg; the Linux window
was captured with XGetImage without compositing or retouching the images.
Physical hardware validation of this change remains pending.

Evidence and captures: `reports/taskbar-center-fix/menu-tests.json` and the PNG
files in the same directory. The emulator was left open with Start expanded.
