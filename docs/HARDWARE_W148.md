<a id="w148-volcado-de-cuadros-para-el-marco-negro-fase-6-paso-2"></a>


# W148: turning of frames for the black frame (phase 6, step 2)

[English](HARDWARE_W148.md) | [Español](HARDWARE_W148-es.md)

APP_VER 02.47. Base W147. The drawing doesn't change.

<a id="qué-agrega"></a>


## What it adds

- **Volcated:** while the GPU stacks the windows, each output box other than the previous one is turned to BMP, up to 40 (`PW_SINK_MAX_DUMPS=40`; before were 8). Each tilt leaves `PWSINK dump frame=N layers=M` in the log. The cost (read the output buffer for the hash, and write ~ 3,6 MB per tilt) is paid only to reach 40.
- **Pils:** the cell record (`layer_stack` / `layer`) is up from 60 a 200 entries.

With that each overflow can be crossed with its stack: if the black frame falls out of all layer except the bottom, the problem is in the bottom or in the shader; If it falls into a layer, it's in the pixels of that window.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w148/physical/20261103T*`. User response: "In both": the task bar already has a black frame, and also the Start menu, WineMine and its menus. They were 30 turned.

**The cause, by the overturned:**

- With only the background (`frame-000003`, `layers=1`), column x = 600 is grass up to and = 719.
- When the task bar (`frame-000005`, `layers=2`, rect (0,700) - (1280,720) appears, the rows 696 - 699 are `000000` and the bar starts at 700.
- The pile has nothing but the bottom under those rows.
- The width of the frame varies because each black edge ranges from the edge of the window to the multiple of 8 following out:

| Caso |Window overboard|Black|Next multiple of 8|
|---|---|---|---|
|Tasks bar| 700 | 696–699 | 696 |
|Home Menu (W144)| 123 | 123–127 | 128 |
| glxgears (W145) | 307 | 308–311 | 312 |
| WineMine (W144) | 75 arriba | 72–74 | 72 |
| WineMine (W144) |148 left| 144–147 | 144 |

- In the GPU of the PS4 (GFX7) a wave front of fragments are 64 pixels, a block of 8 × 8.
- In the blocks where there are pixels in and out of a window, the outsiders were going black.
- The shader of W144 - W148 went through the layers with `continue`, `return` and a `texelFetch` within those different branches. That code gave an incorrect result in the pixels that were still itterating.
- With a single layer (W143) there is no divergence, and that is why there was no frame.
- The exact cause in the compiler is not isolated: it is derived from geometry.

Correction in W149 (`HARDWARE_W149.md`).
