# W145: capas en GPU sin marco negro (fase 6, paso 2)

[English](HARDWARE_W145.md) | [Español](HARDWARE_W145-es.md)

APP_VER 02.44. Base W144.

## Problema en W144

Las ventanas y los menús tenían un marco negro de 3 a 5 píxeles. Era la parte del rectángulo visible que la ventana nunca pinta. Con la composición por CPU ahí se veía lo de abajo; con capas en GPU se veía la memoria en cero. Detalle en `HARDWARE_W144.md`.

## Cambio

- **Píxel "sin pintar":**
  - Mientras la GPU apila las ventanas, la memoria de una ventana nueva o redimensionada empieza con el valor `0x01ff00ff` (`PS5_UNPAINTED` en `ps5drv.c`), no con cero.
  - GDI escribe los píxeles de 32 bits con alfa 0, así que un píxel pintado no toma ese valor.
  - El shader (`screen.frag`) trata ese valor como transparente y sigue con la capa de abajo. Así hace lo mismo que `compose_rect`: donde la ventana no pintó, se ve lo que hay debajo.
- **Vuelta a CPU:** si se pasa a la composición por CPU (`gpu_layers_off`), esos píxeles se convierten en cero antes de componer el escritorio.
- **Ventana liberada al redimensionar:**
  - Antes, el sink la sacaba de la pila guardada y un cuadro redibujado por el puntero podía salir sin esa ventana: un parpadeo.
  - Ahora la pila guardada queda marcada como vieja y no se dibuja hasta que ps5drv manda la nueva, que llega enseguida.

## Qué se espera

- Sin marco negro. Las ventanas y los menús se ven como en W143, con la composición por CPU.
- Los tiempos se mantienen como en W144: `flush_stats` ~0,1 ms de promedio.
- Ningún `gpu_layers_off` ni `gpu_failed`.

## Prueba física

Reporte: `reports/wine-hardware-w145/physical/20261103T110137Z`. Respuesta del usuario: "Sigue el marco".

El marco sigue igual:
- En `frame-000192.bmp` (glxgears) el borde de la ventana va `2d2d30`, `19191c`, `0a0a0a` y después 4 píxeles `000000`.
- Esos píxeles no son "sin pintar". Wine inicializa la superficie de cada ventana en blanco (`0xff`, `window_surface_create` en `dce.c`), y estos llegan en un flush valiendo cero.
- La hipótesis de W145 era incorrecta. La corrección queda (no molesta), pero no era la causa.
- El rectángulo visible es el rectángulo de la ventana (`get_visible_rect` en `window.c`), así que ese margen está dentro de la ventana.

**Hipótesis siguiente (W146):**
- Wine pasa en cada flush la forma de la ventana (`shape_bits`: región, color clave o alfa), y `ps5drv.c` nunca la usó.
- Si el margen está fuera de esa forma, en Windows sería transparente.
- Con la composición por CPU probablemente no se veía porque `compose_rect` sólo redibuja las regiones sucias. Esto no está verificado.
- Ver `HARDWARE_W146.md`.
