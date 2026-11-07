# W182, parte de winecfg y del aspecto: diagnóstico del congelamiento al aplicar un tema, iconos del Panel de control y botón Inicio recto

[English](HARDWARE_W182-winecfg-borrador.md) | [Español](HARDWARE_W182-winecfg-borrador-es.md)

Borrador de la sesión de configuración de Wine. La sesión principal lo suma a `HARDWARE_W182.md`.

## Por qué

- En W180, winecfg se congeló al elegir un tema en Integración de escritorio y apretar Aplicar.
- El log de esa corrida no dice qué llamada no volvió. Hay dos sospechas:
  - `update_now` (repintado con `RDW_UPDATENOW`) en un bucle sin fin, porque una ventana de otro hilo sigue pidiendo `WM_PAINT`;
  - varios `broadcast_message` que agotan su timeout de 2 s, uno detrás de otro, por cada ventana que no responde.
- W182 solo agrega marcas en el log para saber cuál de las dos es. No cambia el comportamiento.

## Cambios de diagnóstico

- `tools/build-winecfg-hw.py` (nuevo): winecfg del Wine fijado con marcas `PWCFG` en Aplicar.
  - Cada paso de `PSN_APPLY` tiene `begin` y `end` con milisegundos: `settings`, `theme`, `shell_folders`, `sysparams`, `refresh`.
  - Dentro de `theme`: `ApplyTheme` (con estilo y sin estilo) y `refresh_sysparams`.
  - Dentro de `sysparams`: `SPI_SETNONCLIENTMETRICS` y `SetSysColors`.
  - Sale `out/winecfg-hw/winecfg.exe` (sha256 `bc36725e…`), sin advertencias.
  - `tools/build-wine-hardware.py` lo copia sobre el de `out/wine-programs`, en `lib/wine/x86_64-windows` y en `system32`, igual que `taskmgr-hw`. Comprueba que el manifest venga del builder actual.
  - `winecfg.cpl` (W179) no cambia: es otro programa que arranca `winecfg.exe`.
- `tools/build-win32u-ps4.py`, con revisiones de `tools/paint-broadcast-diag-w182.patch.py`:
  - `dce.c` `update_now`: si el bucle llega a 256 vueltas, una sola línea por proceso: `PWPAINT update_now_loop hwnd child tid flags`;
  - `message.c` `broadcast_message`: mide cada envío; si una ventana gasta todo el timeout, `PWBCAST timeout msg hwnd tid elapsed_ms`, una vez por ventana y hasta 32 ventanas.
  - Compilado: 47 unidades, ninguna falla.

## Cambios de aspecto (pedidos por el usuario)

- **Iconos en el menú Panel de control** (`tools/build-explorer-hw.py`).
  - Antes, los elementos del Panel de control en el menú Inicio salían con el icono genérico, porque no son archivos.
  - Ahora, si un elemento no trae icono, explorer se lo pide a su carpeta: `IShellFolder::GetUIObjectOf(IID_IExtractIconW)` y `GetIconLocation(GIL_FORSHELL)`.
    - Si la ubicación es un archivo, usa `ExtractIconExW` con ese índice.
    - Si es `GIL_NOTFILENAME`, usa `IExtractIconW::Extract`.
    - Si todo falla, queda el icono genérico de antes.
  - Compilado: 44 revisiones, sin advertencias; `explorer.exe` sha256 `53d66e00…`.
- **Botón Inicio recto en Luna y Noir** (`tools/build-msstyles-hw.py`).
  - El botón verde (Luna) y naranja (Noir) tenía el borde derecho redondeado, como en XP. Ahora es recto de los dos lados.
  - `SizingMargins = 4, 4, 12, 12`.
  - Recompilados: Luna `e316876118aaa794`, Noir `a6a299a396a26ff5`, 35 bitmaps dibujados cada uno.
  - Vista previa en `out/msstyles-preview/desktop-luna.png` y `desktop-noir.png`.

## Perfil de teclas de SuperMarioKart

El "Teclas mal" de W181 fue un toque por error: el usuario confirmó que las teclas andan. Al revisarlo apareció igual el error de abajo, que pasa solo cuando dos botones de la misma tecla se aprietan juntos.

- En `run-0002.log` (`reports/wine-hardware-w181/physical/20261103T224806Z`) el perfil carga (`PWPAD profile=SuperMarioKart.exe keys=14 stick=keys`, línea 367) y manda teclas (`source=profile`).
- Los códigos son teclas virtuales de Windows: 37–40 son las flechas y 13 es Enter. ps5drv les pone el scan code con `MapVirtualKeyEx` y marca las flechas como extendidas (W141), así que DirectInput lee `DIK_LEFT`, `DIK_UP`, `DIK_RETURN`, etc. Ese camino ya estaba probado con el teclado USB.
- El `.ini` coincide con los controles del `Read me.txt` del juego (flechas, espacio y Enter).
- **Error encontrado** en `native/hw_pad.c`: cada fuente mandaba su propia tecla soltada. Con dos fuentes en la misma tecla, soltar una soltaba la tecla aunque la otra siguiera apretada:
  - cruz y stick arriba, las dos `up`: si al doblar el stick pasaba por arriba y volvía, el kart dejaba de acelerar con la cruz apretada;
  - lo mismo con cruceta y stick, círculo y R1 (`space`), y triángulo y Options (`enter`).
- **Arreglo:** un contador por tecla. La tecla baja con la primera fuente y sube con la última. Al entrar en modo juego se sueltan todas las que estén apretadas.
  - Compila con las opciones del enlace, sin advertencias. Probado aparte: dos pulsaciones y dos sueltas dan una sola bajada y una sola subida.
  - **No entra en W182:** se editó con W182 ya compilando (`hw_pad.o` ya estaba hecho). Entra en W183.
- Si el usuario dice que otra tecla está mal, se cambia solo el `.ini`.

## Prueba en la consola

1. winecfg → Integración de escritorio → elegir Luna → Aplicar.
2. En el log:
   - la última línea `PWCFG … begin` que no tiene su `end` dice qué llamada no vuelve;
   - `PWPAINT` dice qué ventana mantiene el repintado en bucle;
   - `PWBCAST` dice qué ventanas agotan los 2 s.
   - Si Aplicar termina bien, todas las marcas tienen `end`, y los milisegundos dicen qué paso tarda.
3. Menú Inicio → Panel de control: cada elemento con su propio icono.
4. Con Luna o Noir: el botón Inicio sin la curva a la derecha.

## Pendiente

- El arreglo del congelamiento queda para W183, según lo que digan estas marcas.
