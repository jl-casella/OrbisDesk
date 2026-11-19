# La respuesta de SeaMonkey en la consola

[English](SEAMONKEY_RESPONSIVENESS.md) | [Español](SEAMONKEY_RESPONSIVENESS-es.md)

Estado: dos ejecuciones en la consola, dos cambios de perfil y un arreglo del lanzador, 2026-11-17. Los fotogramas de 04.15 (run-0207) se midieron en la consola. El cambio del desplazamiento suave y el arreglo de trace.txt todavía no están compilados.

## El síntoma

En 04.14, SeaMonkey carga YouTube por completo ([bloqueos de archivos](SEAMONKEY_FILE_LOCKS-es.md)), pero la interfaz responde con retraso:
- mientras carga una página;
- entre pedir un vídeo a pantalla completa y que el vídeo llene la pantalla;
- al desplazarse por la página.

## Qué muestra run-0192.log

La ejecución es `reports/wine-hardware-w303/physical/20261117T152946Z/run-0192.log`, un log de release (`trace level=0`).

- **La pantalla completa pasa por una ventana de transición.** Cada uno de los tres cambios a pantalla completa inicia primero un hilo nuevo (`0ae0`, `039c`, `0488`). Ese hilo toma el primer plano y muestra su propia ventana de 1280x720 (`PWSINK fullscreen on hwnd=0xc000f8`, `0x7b010e`, `0xfb0104`). Solo después la ventana de SeaMonkey (`0x500c2`) pasa a 0,0 y a pantalla completa. Es la transición a pantalla completa de Gecko en Windows: una ventana en su propio hilo funde la pantalla a negro y de vuelta, por defecto en 200 ms en cada sentido. El log no tiene tiempos para ella.
- **Mover una ventana es barato.** Las líneas del arrastre de ventanas miden cada movimiento: `move_loop_setpos took_us` está entre 1,3 y 2,6 ms.
- **La presentación no espera a la pantalla.** Cuando cambia el contenido de una ventana (`ps5_surface_flush` en win32u), se copia el rectángulo modificado y la pila de ventanas pasa al hilo presentador del sink (`pw_wine_present_layers`, `PW_SINK_ASYNC`). El hilo que pinta no espera a ningún flip.
- **Nada en el log de release mide el pintado, la entrada ni el servidor.** Estas líneas existen, pero están desactivadas en un log de release: `flush_stats`, `show_stats`, `PWSERVER late_*` y `PWFG`. Así que el log no puede decir cuántos fotogramas dibuja SeaMonkey ni dónde espera su hilo principal.
- SeaMonkey inició más de 256 hilos (`thread_overflow`). Como en [descriptores](SEAMONKEY_DESCRIPTORS-es.md), eso solo impide que se registren; no detiene nada.

## Qué se deduce del perfil y de la plataforma

Esto se deduce del perfil y del hardware, no de una medición:

- **Un solo hilo hace casi todo el trabajo.** SeaMonkey corre sin e10s (un solo proceso, como todo invitado). La interfaz, el JavaScript de la página, la maquetación y el pintado comparten un hilo principal, así que un script largo de YouTube bloquea por igual los clics, el desplazamiento y el cambio a pantalla completa.
- **El desplazamiento corre en ese mismo hilo.** En la plataforma de Firefox 60, el desplazamiento y zoom asíncronos (los que hace el compositor) necesitan e10s.
- **La composición es por software.** El perfil activa `layers.acceleration.disabled`, porque D3D11 a través de DXVK en el proceso del navegador falló (Pale Moon W183/W184). Así que Gecko compone con su compositor Basic (CPU), y la CPU rasteriza cada repintado.
- **La CPU es lenta por núcleo.** El título tiene 6 de los núcleos Jaguar de la consola (`affinity=3f cores=6`). Van a 1,6 GHz en una PS4 y a 2,1 GHz en una Pro. La velocidad de un solo hilo es lo que más importa para un hilo principal.

Para saber si esto es simplemente el límite de la plataforma, o si hay además una espera del lado de Wine, hacen falta los números de abajo.

## El cambio

[seamonkey-user.js](../fixtures/browser/seamonkey-user.js) pone `full-screen-api.transition-duration.enter` y `.leave` a `"0 0"`. Con las dos duraciones a 0, Gecko omite la transición: ni hilo extra, ni ventana extra, ni fundido. El cambio a pantalla completa en sí no cambia.

Esto elimina solo el paso que muestra el log. No acelera el desplazamiento ni la carga de páginas. En run-0207 (04.15) no hay ventana de transición: el cambio a pantalla completa solo mueve la ventana de SeaMonkey.

## Medición de 04.15 (run-0207.log)

La ejecución es `reports/wine-hardware-w303/physical/20261117T173525Z/run-0207.log`: unos 30 s de un vídeo de YouTube reproduciéndose en la página, unos 15 s de desplazamiento, y luego pantalla completa y vuelta.

`framegen.txt` funcionó (`PWFG config mode=timing … kernel_open=0x14`) y dio 184 líneas `PWFG timing`, una por ventana de 2–3 s. `trace.txt` no funcionó (`trace level=0 source=build`). El lanzador lo leía con el `open` de libc, que falla con ese archivo como fallaba con `framegen.txt` y `winedebug.txt`. Así que la ejecución no tiene líneas `flush_stats`, `show_stats` ni `PWSERVER`.

Fotogramas mostrados por segundo (`flips_done` × 1000 / `window_ms`):

| Tramo | Fotogramas/s |
| --- | --- |
| Escritorio en reposo, SeaMonkey cerrado | 1 |
| SeaMonkey arrancando y cargando YouTube | 1–46, irregular |
| Vídeo reproduciéndose en la página (desde el primer flujo de audio) | 57–58 durante 8 ventanas, luego 31–55 |
| Alrededor del cambio a pantalla completa (ventana a 0,0 y vuelta) | 5–39, luego 49–57 |
| El resto de la actividad de la página | casi siempre 10–45 |

En las 184 ventanas:
- `pending_max=0`, y `flips_submitted` es igual a `flips_done`. El presentador nunca tuvo un fotograma esperando, y ningún flip falló (`status_failed=0`).
- `flip_latency_us` es como mucho 16,7 ms, el tiempo hasta el siguiente vblank (`period_us=16683`). Es la espera de la sincronía vertical, unos 8 ms de media, no una cola acumulada.

Lo que se deduce:
- **El camino de Wine y del sink no es lo que limita la página.** La misma ventana, por el mismo flush y el mismo presentador, muestra 57–58 fotogramas por segundo mientras se reproduce un vídeo, cerca de los 60 Hz de la pantalla. El vídeo a pantalla completa actualiza toda la ventana de 1280x720 a 49–57. Cuando la página se desplaza o carga, la tasa baja a 10–45 mientras el presentador sigue libre. Así que SeaMonkey entrega menos fotogramas: el tiempo se va antes del flush, dentro del navegador.
- **Este log no puede mostrar qué hace ahí el navegador.** Un fotograma de vídeo es una imagen que el compositor escala. Un desplazamiento o una carga de página es JavaScript, maquetación y rasterizado por software de texto e imágenes en el hilo principal. Con el arreglo de trace.txt, `flush_stats` añadiría el coste de cada flush y cuántos flushes hay por segundo. No puede ver dentro del hilo principal del navegador.
- **Es el límite de la plataforma para este navegador**, con los números de arriba: un hilo principal en un núcleo Jaguar de 1,6 o 2,1 GHz, sin desplazamiento asíncrono y con composición por CPU. Lo que ayuda es menos trabajo en el hilo principal, no una presentación más rápida.

## Cambios después de 04.15

- En [wine_hardware.c](../native/wine_hardware.c), `trace_setup` lee `trace.txt` primero con `sceKernelOpen` del kernel y, si falla, con el `open` de libc, como hace `fg_read_config` con `framegen.txt`. Su línea del log añade `kernel_open=` y `libc_errno=`.
- [seamonkey-user.js](../fixtures/browser/seamonkey-user.js) pone `general.smoothScroll` a false. Un desplazamiento suave anima cada paso de la rueda o cada tecla durante varios fotogramas, y sin desplazamiento asíncrono cada fotograma es un repintado en el hilo principal. Sin desplazamiento suave, un paso es un repintado, y la página salta en vez de deslizarse.

Considerado y sin cambiar:
- **La composición por GPU** (`layers.acceleration.disabled` a false) sigue desactivada. D3D11 a través de DXVK en el proceso del navegador falló (Pale Moon W183/W184), y la medición no apunta a la composición.
- **El pintado fuera del hilo principal** (`layers.omtp.enabled`): en la plataforma de Firefox 60 depende del backend de contenido y del modelo de procesos. about:support muestra si está disponible aquí (Gráficos, registro de decisiones). Sin esa comprobación, activarlo es una suposición.
- **Una frecuencia de refresco menor** (`layout.frame_rate`) limitaría las animaciones, y también el vídeo en la página, que según la medición ya va bien.

## Medir (sin compilar nada)

1. Crear `/data/orbisdesk/trace.txt` (vacío) y `/data/orbisdesk/framegen.txt` con el texto `timing`. Las trazas añaden líneas al log y cuestan algo por sí mismas, así que hay que borrar los dos archivos después. `trace.txt` necesita una compilación con el arreglo de `trace_setup` de 04.15: comprobar que la línea `trace level=` de la ejecución dice `source=trace.txt`.
2. Arrancar OrbisDesk y abrir SeaMonkey. Abrir `about:support` y fotografiar la sección de gráficos. **Composición** debería decir `Basic`.
3. Abrir un vídeo de YouTube:
   - esperar 30 s mientras se reproduce en la página;
   - desplazarse arriba y abajo durante 15 s;
   - pasar a pantalla completa, esperar 10 s y salir de pantalla completa.

   Apuntar más o menos cuándo se hizo cada paso.
4. Recoger el log. Las líneas que responden a la pregunta:
   - `PWFG timing … flips_submitted=… vblanks=…` cada 2 s: los fotogramas que la consola mostró de verdad. 120 vblanks en una ventana de 2 s son 60 Hz.
   - `PWBOOT flush_stats n=… avg_us=… max_us=… avg_px=… over_ms=…` cada 100 actualizaciones de ventana: lo que le cuesta a Wine una actualización (copia, composición y entrega), y con qué frecuencia actualiza SeaMonkey (100 actualizaciones en `over_ms`).
   - `PWSINK show_stats path=… avg_us=… max_us=…` cada 300 fotogramas de salida: el coste por fotograma del presentador.
   - `PWSERVER late_timer`, `late_wake` y `stuck_s`: el wineserver dentro del proceso, retrasado o atascado.

Cómo leerlas:
- **Coste por actualización pequeño, pocas actualizaciones por segundo, sin líneas `PWSERVER`:** el tiempo se va dentro de SeaMonkey (JavaScript, maquetación, pintado por software en el hilo principal). Es el límite de la plataforma para este navegador. Lo que ayudaría es menos trabajo: páginas más ligeras, `general.smoothScroll` a false o una interfaz de YouTube más ligera.
- **`flush_stats` o `show_stats` grandes:** el coste está en el camino de Wine y del sink. El siguiente paso sería componer solo el rectángulo modificado, o ahorrarse la copia.
- **Líneas `PWSERVER` durante el retraso:** el servidor dentro del proceso va con retraso o está atascado. `stuck_s` nombra la petición y el hilo cliente.

## Qué se probó

- Los interruptores de traza y sus líneas se leyeron en el código fuente (`platform/ps4/pw_trace.h`, `pw_wine_sink_ps4.c`, `tools/build-win32u-ps4.py`, `tools/build-wine-delete-server.py`).
- Los nombres de las preferencias son los de la plataforma de Firefox 60. No se comprobó en la consola si SeaMonkey 2.53.24 los aplica.
- Los fotogramas de 04.15 vienen de run-0207 en la consola (PS4 Pro). El fallo de trace.txt es su línea `trace level=0 source=build`.
- Con el arreglo, `trace_setup` compila sin avisos con las opciones registradas para los auxiliares y `-Wall`. No se ha compilado en un paquete.
- **No probado:** el cambio del desplazamiento suave y el arreglo de trace.txt no se han ejecutado en la consola.
