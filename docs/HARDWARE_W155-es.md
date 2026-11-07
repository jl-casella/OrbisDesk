# W155: programas de 32 bits sin trazas y a pantalla completa (fase 6)

[English](HARDWARE_W155.md) | [Español](HARDWARE_W155-es.md)

APP_VER 02.54. Base W154, que tampoco se probó: incluye su cambio (la imagen Vulkan sigue a la ventana al moverla).

## SuperMarioKart con W153

Reporte: `reports/wine-hardware-w153/physical/20261103T135602Z`, `run-0002.log`.

- **Arranque:** el juego corre como título aparte de 32 bits, `cpu=wow64native`.
- **Presentación:**
  - el juego usa DirectDraw/Direct3D 7, que wined3d dibuja con su renderer Vulkan (`WINE_D3D_CONFIG=renderer=vulkan`), no DXVK;
  - wined3d presenta por el `vkQueuePresentKHR` de win32u, así que ya usa el camino de W153: `show_frame … 800x600 … path=gpu_layer us=6–13`;
  - algunos cuadros tardan 12–13 ms porque esperan el lock del escritorio.
- **FPS** (`PWVK present fps`): entre 7,6 y 24,7 (el valor más repetido es 24,7), y bajan a ~12,5 hacia el final. `blit_wait_us` ~0,49 ms.
- **Audio:** suena (`PWAUDIO … peak=10331`).
- **Salida:** `process_exit status=0xc000000d` a los 83 s.
- **Log:** 429.035 líneas en ~80 s, casi todas de trazas que quedaron de la puesta en marcha (W131):
  - `trace+file` (`NtReadFile`/`ReadFile`): ~123.000;
  - `trace+ddraw`: `DrawIndexedPrimitiveVB` 67.000, `SetTexture` 65.000, `SetTransform` 24.000, etc.;
  - `trace+virtual`: ~28.000.

- **Pantalla** (usuario: "no fue fullscreen, a su derecha había una gran columna negra"):
  - el juego no pide pantalla completa: `SetCooperativeLevel` con flags `0x8` (`DDSCL_NORMAL`), una ventana sin borde de 800×600 en (0,0);
  - el escritorio del título mide 1280×720, así que la ventana se veía 1:1 arriba a la izquierda, con negro a la derecha y abajo.

## Cambio

- **Vista ajustada en títulos de 32 bits:**
  - `native/wine_hardware.c` agrega `WINE_PS5_FIT=1` cuando el programa es PE32.
  - ps5drv (`present_screen`, camino por GPU) calcula la unión de las ventanas visibles. Si empieza en (0,0), le pasa al sink ese tamaño como tamaño del escritorio, en lugar de 1280×720.
  - El sink escala ese tamaño a la salida manteniendo la proporción: 800×600 queda en 960×720 centrado, con barras negras angostas a los costados.
  - El puntero queda dentro de esa zona: `pw_wine_pointer_area` (sink) y `pw_hw_pointer_area` (`native/hw_pad.c`).
  - Log: `PWBOOT fit_view WxH pointer=1` y `PWBOOT pointer_area WxH`.
  - El escritorio con explorer no cambia, porque no lleva `WINE_PS5_FIT`.
- **Trazas:** `native/wine_hardware.c` (`pe32_log`): `ddraw`, `file`, `virtual` y `section` pasan de `trace` a `warn`. Siguen los avisos y errores de esos canales. `trace+seh` y `trace+loaddll` quedan, porque escriben poco.

## Qué se espera

- SuperMarioKart ocupa la pantalla (960×720 centrado) y el puntero llega a todo el juego.
- SuperMarioKart con un log de miles de líneas, no cientos de miles.
- Si las trazas limitaban el juego, más FPS que en W153.
- Al arrastrar glxgears, la imagen se mueve con la ventana (W154).

## Prueba física

Reportes: `reports/wine-hardware-w155/physical/20261103T141256Z` y `20261103T142029Z`.

- **Arrastre (W154):** el usuario probó glxgears y vkspin y respondió "dibujado bien".
- **Cierre de la app:** después de cerrar glxgears, al abrir WFM para lanzar SuperMarioKart, la app se cerró.
  - El log se corta apenas termina de cargar WFM, sin línea `crash` ni reporte de la GPU.
  - Ya con glxgears cerrado el escritorio presentaba 2 capas, así que su imagen ya no estaba en la pila.
  - Repetido sin abrir antes programas Vulkan, no pasa ("Ahora anduvo").
  - La causa no está identificada.
- **SuperMarioKart (`run-0003.log`):**
  - **Log:** 8.403 líneas, contra 429.035 en W153.
  - **FPS:** 15–18. Sin trazas no mejoró, así que no eran el límite.
  - **No fue a pantalla completa.** Esta vez el juego pidió modo exclusivo (`DDSCL_ALLOWREBOOT`, que va con `EXCLUSIVE`) a 800×600.
    - win32u emula ese modo: para el programa la ventana mide 800×600, pero en la pantalla real cubre 1280×720.
    - `pw_vk_show_frame` pasaba el área cliente en coordenadas del programa, (0,0)-(800,600), así que la imagen quedó otra vez en la esquina.
    - La unión de ventanas medía 1280×720, por lo que `fit_view` volvió a 1280×720 (antes se había ajustado un momento a una ventana de 116×27).
  - **Salida:** `status=0xc000000d` otra vez al terminar, como en W153.

Correcciones en W156 (`HARDWARE_W156.md`).
