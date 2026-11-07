# W144: la GPU apila las ventanas (fase 6, paso 2)

[English](HARDWARE_W144.md) | [Español](HARDWARE_W144-es.md)

APP_VER 02.43. Base W143, en la que la salida a pantalla ya pasa por la GPU.

## Qué quedaba en la CPU

Con W143 la GPU arma el cuadro de salida a partir del escritorio. El escritorio en sí lo seguía componiendo `ps5drv.c` en el hilo de Wine. En cada actualización de una ventana pasaba esto:

1. copiaba la región sucia de la superficie de la ventana a `window->pixels`;
2. con `compose_rect`, armaba esa región del escritorio fila por fila: el fondo, encima cada ventana que la toca, de abajo hacia arriba, y la copia al escritorio.

`flush_stats` mide el total: hasta ~19 ms por actualización en W142. El paso 2 elimina la segunda parte.

## Cambio

- **Pool de memoria en la GPU** (`native/hw_sink_gpu/hw_sink_gpu.c`):
  - Es un solo buffer de 96 MiB con caché de CPU y visible para la GPU. Se achica si `maxTexelBufferElements` es menor.
  - Tiene un asignador first-fit en bloques de 256 bytes (`pw_sink_gpu_alloc`/`pw_sink_gpu_free`).
  - De ahí salen el contenido de cada ventana, el fondo de pantalla y el escritorio de respaldo de W142.
- **Capas:**
  - Un cuadro es una lista de capas, de abajo hacia arriba, en un uniform buffer: rectángulo en el escritorio, posición en el pool y stride.
  - El shader (`screen.frag`) toma, para cada píxel del escritorio, la capa más alta que lo cubre. Si ninguna lo cubre, pone negro: es la misma regla que `compose_rect`.
  - El escritorio de W142 pasa a ser un cuadro de una sola capa.
- **`ps5drv.c`** (revisiones W144 en `tools/build-win32u-ps4.py`):
  - Si el sink dibuja por GPU (`pw_wine_layers()`), el contenido de las ventanas y el fondo se reservan en el pool.
  - En ese modo `compose_rect` no hace nada, y cada present manda la pila con `pw_wine_present_layers`: el fondo y cada ventana visible, recortada a su rectángulo visible.
  - La copia de la superficie a `window->pixels` (parte 1) sigue igual.
- **Sink** (`platform/ps4/pw_wine_sink_ps4.c`):
  - Guarda la última pila y la vuelve a dibujar cuando se mueve el puntero.
  - Si se libera una ventana, la saca de la pila guardada, para que no se lea memoria liberada.
  - Como en este modo no hay un escritorio para volcar a BMP, el volcado de cuadros guarda el buffer de salida ya dibujado. Lo hace sólo en los cuadros que van al log.
- **Si falla:** cualquier falla del pool, del dibujo o de la presentación deja `PWBOOT gpu_layers_off <motivo>: CPU composition`. ps5drv compone entonces el escritorio completo en la CPU y sigue como en W143.

## Qué se espera

- En el log:
  - `PWSINK gpu_pool bytes=… max_texels=…`;
  - `PWBOOT gpu_layers=1`;
  - `PWBOOT frame_presented … layers=N`;
  - `PWSINK show_stats path=layers`, si la sesión llega a 300 cuadros;
  - ningún `gpu_layers_off`, `gpu_failed` ni `gpu_pool_full`.
- El escritorio, el menú Inicio y las ventanas se ven igual que en W143. Las ventanas se mueven, se superponen y se cierran sin dejar restos.
- `flush_stats` baja, porque ya no incluye la composición. Hace falta una sesión con bastante actividad (más de 100 actualizaciones) para que aparezca.

## Prueba física

Reporte: `reports/wine-hardware-w144/physical/20261103T103359Z`. La sesión duró unos 158 s con bastante actividad: 16 128 cuadros presentados, ~15 700 actualizaciones de ventanas, 120 movimientos de ventana. Respuesta del usuario: "Hay restos o parpadeos", con el detalle "un marco negro en paneles, menús y ventanas; el resto ok", y una foto.

**Funcionamiento:**
- `gpu_pool bytes=100663296 memory_type=5 max_texels=536870912`. El pool quedó completo: el límite de texels permite 2 GiB.
- `gpu_layers=1` y el fondo de pantalla quedó como capa.
- No hubo `gpu_layers_off`, `gpu_failed` ni `gpu_pool_full`.

**Tiempos:**

| Medida | W142 (CPU) | W144 (capas en GPU) |
|---|---|---|
| `flush_stats` promedio | 0,4–1,3 ms | 0,06–0,13 ms |
| `flush_stats` máximo típico | ~19 ms | 0,8–1,4 ms (algún pico de 8,6 ms) |
| `show_stats` promedio | ~1,0 ms |0,6 0,95 ms (pat=capas)|
| `show_stats` máximo | 1,3–1,7 ms | hasta ~12 ms, pocas veces |

El hilo de Wine dedica ahora alrededor de una décima parte del tiempo a cada actualización de ventana. El presentador tarda lo mismo o menos que antes. Los picos de ~11–12 ms coinciden con cuadros que también se vuelcan a BMP.

**El marco negro:**
- En los cuadros volcados (`frames/frame-000129.bmp`) hay un borde de 3 a 5 píxeles exactamente negro (`0x000000`) alrededor de WineMine, del menú Inicio y de sus submenús.
- Son píxeles del rectángulo visible de la ventana que nunca se pintaron: la memoria de la ventana empieza en cero.
- Con la composición por CPU no se veían porque `compose_rect` sólo redibuja las regiones que la ventana manda (flush), así que debajo de un margen sin pintar quedaba el fondo.
- Con capas la GPU dibuja el rectángulo completo, y esos ceros salían negros.

Se corrige en W145, ver `HARDWARE_W145.md`.
