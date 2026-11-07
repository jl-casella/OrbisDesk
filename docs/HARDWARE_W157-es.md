# W157: medición de CPU por cuadro (fase 6)

[English](HARDWARE_W157.md) | [Español](HARDWARE_W157-es.md)

APP_VER 02.56. Base W156, que no se probó por separado: esta build la incluye (imagen Vulkan en el área cliente real, con su proporción).

## Para qué

SuperMarioKart anda a 15–18 fps (W155). Lo que ya está medido:
- **Presentación:** la imagen llega a la pantalla con 6–16 µs de CPU por cuadro (`show_frame … path=gpu_layer`).
- **GPU:** cada present espera ~0,5 ms a que la GPU termine todo lo encolado, incluido el cuadro (`blit_wait_us`). La GPU está casi siempre sin trabajo.
- **Logs:** con 8.400 líneas en lugar de 429.000, los fps no cambiaron (W155).

El límite está en la CPU: en el código de 32 bits del juego, en wined3d o en el paso de 32 a 64 bits de cada llamada. Falta saber en qué hilo.

## Cambio

`native/wine_vk_runtime.c`: cada segundo, junto a `PWVK present fps`, el log agrega:

`PWVK cpu process_pct=P present_thread_pct=T frame_ms=F`

- **P:** CPU de todo el proceso (`getrusage(RUSAGE_SELF)`), en % de un núcleo. 100 equivale a un núcleo ocupado todo el segundo.
- **T:** CPU del hilo que presenta (`RUSAGE_THREAD`). En Direct3D 7 con wined3d es el hilo del command stream, que traduce a Vulkan.
- **F:** tiempo medio entre cuadros.
- Si el kernel no da esos tiempos, se ve `PWVK cpu unavailable …` con el errno.

**Cómo se lee:**
- Si T está cerca de 100, el cuello está en wined3d o en las llamadas a Vulkan.
- Si P − T está cerca de 100, está en el hilo del juego: código de 32 bits o sus llamadas al sistema.
- Si ninguno se acerca a 100, el juego espera algo: un temporizador o sincronización.

## Prueba física

Reporte: `reports/wine-hardware-w157/physical/20261103T143810Z`, `run-0002.log` (SuperMarioKart, ~90 s, sin abrir antes programas Vulkan). Respuesta del usuario: "Pantalla completa bien".

**Pantalla (W156):** la vista sigue a 1280×720 (`fit_view 1280x720`), porque la ventana en modo exclusivo emulado cubre la pantalla, y la imagen de 800×600 se ubica centrada con su proporción. El usuario lo confirma.

**CPU:** 55 muestras de un segundo con `frame_ms` < 80:

| | Promedio |
|---|---|
| Proceso | 202 % (dos núcleos ocupados) |
| Hilo que presenta (command stream de wined3d) | 90 % (entre 92 y 97 % en las carreras) |
| Tiempo por cuadro | 60,9 ms (39 ms a 25,5 fps, 63 ms a 15,8 fps) |

- Hay segundos sueltos con 0,2–10 fps y el hilo de wined3d al 16–37 %: en esos momentos el tiempo no se va en ese hilo (carga de recursos o compilación).
- `blit_wait_us` ~0,5 ms y `show_frame` 16 µs, como en W153.
- La salida es otra vez `status=0xc000000d`.

**Conclusión:**
- El límite es el hilo de command stream de wined3d. Está ocupado todo el tiempo y gasta 39–63 ms de CPU por cuadro en traducir Direct3D 7 a Vulkan y hacer las llamadas.
- El hilo del juego usa el otro ~100 %. Con el command stream lleno, wined3d hace que el hilo de la aplicación espere activo, así que no se sabe cuánto de eso es trabajo del juego.
- La GPU y la presentación no limitan.

Falta separar, dentro de ese hilo, el código de wined3d (32 bits) del paso de cada llamada a Vulkan por el thunk WoW64 hacia el lado Unix de 64 bits.
