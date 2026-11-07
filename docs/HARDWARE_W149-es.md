# W149: shader de capas sin divergencia (fase 6, paso 2)

[English](HARDWARE_W149.md) | [Español](HARDWARE_W149-es.md)

APP_VER 02.48. Base W148.

## Problema

El marco negro alrededor de las ventanas (W144–W148) sigue la grilla de 8×8 píxeles de la GPU. Lo producía el shader de capas cuando un bloque de 8×8 tenía píxeles dentro y fuera de una ventana. Detalle en `HARDWARE_W148.md`.

## Cambio

`native/hw_sink_gpu/screen.frag`:
- El bucle recorre siempre todas las capas, de abajo hacia arriba. `count` viene de push constants, así que es igual para todos los píxeles.
- `texelFetch` se ejecuta siempre (índice 0 cuando la capa no cubre el píxel), y el resultado se elige con una selección: una capa que cubre el píxel y no está "sin pintar" reemplaza al valor anterior.
- No hay `return` ni `continue`. El puntero también se resuelve con selecciones al final.

La regla de composición es la misma: la capa más alta que cubre el píxel; negro donde ninguna lo cubre y fuera del área del escritorio.

El costo es una lectura por capa y por píxel. Con 3 a 6 capas en un escritorio normal es poco para la GPU.

Los diagnósticos de W146–W148 siguen activos en esta build (`flush_shape`, `layer_stack`, 40 volcados), para comprobar los bordes en las capturas. Se sacan una vez confirmado.

## Qué se espera

- Sin marco negro en la barra de tareas, los menús ni las ventanas.
- En los volcados, el borde de cada ventana pasa directo al fondo o a la ventana de abajo.

## Prueba física

Reporte: `reports/wine-hardware-w149/physical/20261103T125915Z`. Respuesta del usuario: el marco negro se fue, pero la primera apertura del menú Inicio es muy lenta.

- No hubo `gpu_layers_off` ni `gpu_failed`: todo el uso fue por capas.
- `show_stats path=layers`: promedio 0,58–0,85 ms por bloque de 300 cuadros, igual que W144. Leer todas las capas en cada píxel no se nota.
- La lentitud del menú son los diagnósticos: 38 volcados BMP en los primeros 83 cuadros, justo cuando se abre el menú por primera vez (pico de 144 ms en el primer bloque de `show_stats`), más ~960 líneas de `layer_stack`/`layer` y 80 de `flush_shape`.

Los diagnósticos se sacan en W150 (`HARDWARE_W150.md`).
