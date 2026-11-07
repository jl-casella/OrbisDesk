<a id="w147-diagnóstico-de-la-pila-de-capas-fase-6-paso-2"></a>


# W147: layer cell diagnosis (phase 6, step 2)

[English](HARDWARE_W147.md) | [Español](HARDWARE_W147-es.md)

APP_VER 02.46. Base W146. The drawing doesn't change.

<a id="por-qué"></a>


## Why?

With layers by GPU each window has around a black frame of 3 - 5 pixels. W146 showed that that frame is not inside the window: it is another layer larger than the window (`HARDWARE_W146.md`).

<a id="qué-agrega"></a>


## What it adds

In `present_screen`, for each changing pile (quantity of layers or rectangles), up to 60 times:

```
PWBOOT layer_stack n=… count=… windows=…
PWBOOT layer n=… i=… hwnd=… rect=(l,t)-(r,b) stride=… px=<0,0>,<2,2>,<0,mitad>
```

`hwnd=0` is the wallpaper. This shows which window of `ps5drv` produces the large and black rectangle: hwd, size and content.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w147/physical/20261103T112424Z`. The user opened the Start menu with submenus and WineMine.

- **The stack has no more layers.** There are 11 recorded batteries: background (`hwnd=0`), task bar `0x10038` and each menu or window with its exact rectangle. For example, the Start `0xc0060` menu is (0,586) - (123,700) and WineMine `0x30064` is (0,0) - (160,226. No layer appears larger than a window.
- **The only picture with a window has no frame** (`frame-000064.bmp`): WineMine in (0,0 ends up in `19191c`, `0a0a0a` and follows the background directly.
- **No pictures:** in hardware, the spins are 8; five are spent on startup and the others only come out in the tables 64, 128... So there is no box with an open menu to compare it to your stack.

**Conclusion:** the frame is not an extra layer and is not always. In W144 and W145 it appeared in windows that had moved (WineMine in x = 144, glxgears) and in menus. You have to capture the picture just when it appears (W148).
