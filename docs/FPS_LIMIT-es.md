# Límite de FPS (por programa)

[English](FPS_LIMIT.md) | [Español](FPS_LIMIT-es.md)

La entrada **LÍMITE FPS** del overlay (L3+R3, debajo de GRÁFICOS) limita cada cuánto presenta cuadros el programa al frente: **30** (el valor por defecto desde 04.18), **60**, **Auto** o **No**. Acompasa los presents reales del juego a los límites de vblank para que lleguen a la pantalla a ritmo parejo. No descarta cuadros, no inventa cuadros y no cambia la velocidad de simulación del juego: un juego que espera a su present simplemente corre al límite.

**Estado:**
- **04.16, en una PS4 Pro** (corridas físicas 0208 y 0209 de W303, 20261117T182036Z): vkcube y Prince of Persia se mantuvieron en 30, con `presents=150 held=150 late=0-2` cada 5 s y `period_us≈16683`. La elección por programa se guardó y se aplicó al arrancar (`fpslimit=30 program=POP.exe why=start`).
- **04.18:** 30 es el valor por defecto de todo programa sin una elección guardada. Esto todavía no corrió en una PS4.
- No se afirma ninguna mejora de fluidez ni de rendimiento más allá de lo que muestran esos registros.

## Cómo se elige

1. Abre el programa y luego el overlay con L3+R3.
2. Baja hasta **LÍMITE FPS**. El panel muestra el programa al que se aplica la elección: el último programa abierto que sigue abierto, igual que en CURSOR y ESTIRAR.
3. Elige con izquierda y derecha, y guarda con X. La elección vale en el momento y se guarda en `C:\orbis\overlay.ini` como `fpslimit.<exe>=60`, `auto` u `off`. Con 30, el valor por defecto, no se escribe ninguna línea.

Un programa sin línea corre a 30 desde su arranque (`PWOVERLAY fpslimit=30 program=<exe> why=start`). Las líneas que escribió 04.16 conservan su valor. Un programa que en 04.16 estaba en No no tenía línea, así que ahora arranca en 30: hay que volver a elegir No para que quede sin límite. Sin ningún programa abierto (el escritorio al frente) no se limita nada. Sin ningún programa abierto, X muestra "LÍMITE FPS: NINGÚN PROGRAMA ABIERTO" y no guarda nada. El valor a la derecha de la entrada es el límite vigente para ese programa.

## Qué hace cada opción

| Opción | Efecto |
| --- | --- |
| 30 (por defecto) | Un present espera al segundo vblank después de la liberación anterior, así que los cuadros salen un vblank sí y otro no. |
| 60 | Un present espera al vblank siguiente a aquel en que se liberó el anterior. Solo importa en juegos que presentarían más rápido que 60. |
| No | No se retiene nada. Con el límite apagado para el programa al frente, un present cuesta una llamada a función. |
| Auto | Empieza en 60. En ventanas de alrededor de un segundo mide qué tan rápido podría ir el juego sin la retención: cuadros divididos por el tiempo propio del juego en ellos, desde una liberación hasta el present siguiente. Dos ventanas seguidas por debajo de 52 FPS pasan a 30. Estando en 30, tres ventanas seguidas en 57 FPS o más vuelven a 60. |

Un present que llega después de su vblank permitido se libera en el acto y la cuenta empieza de nuevo desde ahí. A un juego más lento que el límite nunca se lo demora más.

**Auto y DXVK.** DXVK presenta desde un hilo propio, normalmente con el cuadro siguiente ya listo, así que mientras se lo retiene en 30 parece capaz de llegar a 60 y Auto vuelve a probar 60. Si el juego no puede sostenerlo, dos ventanas por debajo de 52 lo devuelven a 30 (unos 2 s de ritmo desparejo). Cada vuelta fallida duplica las ventanas que Auto espera antes del intento siguiente: 3, 6, 12, 24, 48 y después 96. Pasado ese arranque, un juego que no sostiene 60 lo vuelve a intentar más o menos cada 100 s. Una vuelta que dura 10 ventanas devuelve la espera a 3.

## Qué cubre

- **Cubre:** los presents que llegan al `vkQueuePresentKHR` de win32u de Wine, en invitados de 32 y de 64 bits por igual:
  - DXVK (de D3D8 a D3D11);
  - el renderizador Vulkan de wined3d;
  - los juegos Vulkan nativos;
  - el renderizador OpenGL de wined3d a través de Mesa WGL/Zink, que presenta con una swapchain Vulkan. Esto se espera, pero todavía no se comprobó en la consola.
- **No cubre:**
  - los programas que dibujan solo con GDI;
  - los programas que se inician como proceso aparte (la ruta PoP de lanzadores), cuyos presents ocurren en otro proceso.
- **Varias swapchains:** el límite se aplica a toda swapchain Vulkan mientras el programa para el que está puesto sea el último abierto. Cada swapchain se acompasa por su cuenta, pero la medición de Auto es compartida, así que dos programas presentando Vulkan a la vez no se manejan bien.

## El límite propio de MangoHud

MangoHud tiene su propio `fps_limit`, que se ajusta con MangoJuice. Los cambios de MangoJuice se aplican a todos los programas que muestran el HUD. LÍMITE FPS no lee ni cambia `MangoHud.conf`, y el mostrar/ocultar del HUD en el overlay funciona igual en programas de 32 y de 64 bits, con o sin él.

Cuando están los dos, se aplican uno tras otro: MangoHud duerme primero dentro de su capa y después LÍMITE FPS espera su vblank. **Gana el límite más bajo.** Por ejemplo, MangoHud en 40 más LÍMITE FPS en 30 da 30, y MangoHud en 30 más LÍMITE FPS en 60 da los 30 de MangoHud. La espera de MangoHud es por tiempo y no está alineada con los vblank, así que para un ritmo parejo conviene poner el `fps_limit` de MangoHud en 0 (sin límite) y usar LÍMITE FPS. Con Auto, un límite de MangoHud más bajo también baja lo que mide Auto.

## Con la generación de fotogramas

Un juego sostenido en 30 parejos por LÍMITE FPS es la entrada que necesita la [generación de fotogramas](FRAME_GENERATION-es.md). Con GENERAR CUADROS encendido en el overlay para el mismo programa, el sink muestra un cuadro generado en el vblank entre cada dos del juego, así que la pantalla cambia 60 veces por segundo mientras el juego sigue presentando 30. Con 60, No, o Auto en 60, GENERAR CUADROS muestra solo cuadros reales. La generación de fotogramas todavía no corrió en una PS4.

## Registros

En el registro del título aparecen las líneas de abajo. Desde la 04.37, `PWFPS vblank count`, `PWFPS auto cap` y el reporte de 5 s aparecen solo con trazas encendidas (`/data/orbisdesk/trace.txt`, ver [trazas en release](RELEASE_TRACES-es.md#líneas-del-alpha-2)); las líneas de ajuste aparecen siempre.

- `PWOVERLAY fpslimit=<off|30|60|auto> program=<exe> saved=<0|1> errno=<n> why=menu`: la elección se hizo en el overlay. Con `why=start` o `why=exit`, cambió el programa al frente y entró en vigor su elección guardada.
- `PWFPS limit=<ajuste> cap=<vblanks>`: el sink tomó el ajuste nuevo (cap 2 = 30, 1 = 60, 0 = apagado).
- `PWFPS vblank count trusted|not trusted: <n> in <us> us (period_us=<p>)`: si la cuenta de vblank de VideoOut avanzó a unos 60 Hz durante un segundo. Hasta que se confía en ella, las retenciones se miden por tiempo desde la última liberación (`pacing=time`).
- `PWFPS auto cap <a>-><b> potential_x10=<f> high_needed=<n>`: Auto cambió de límite. `potential_x10` es el FPS potencial medido × 10.
- Cada 5 s mientras hay un límite: `PWFPS limit=… cap=… presents=… held=… held_us_avg=… held_us_max=… late=… pacing=vblank|time period_us=… potential_x10=… high_needed=… switches=… status_failed=…`.
  - `held` cuenta los presents que esperaron.
  - `late` cuenta los que llegaron después de su vblank permitido y se liberaron en el acto.
  - `status_failed` cuenta las lecturas fallidas del estado de vblank.

## Comprobaciones

- `python3 tests/test_fps_limit_host.py` compila `tests/fps_limit_host_check.c` con el compilador del host. Prueba las decisiones de `platform/ps4/pw_fps_limit.h` contra juegos simulados, síncronos y con cola:
  - 30 y 60 dan un espaciado exacto de 2 y de 1 vblank;
  - a un juego de 25 FPS nunca se lo retiene;
  - Auto mantiene en 60 los juegos de 100, 83 y 57 FPS;
  - Auto pasa a 30 un juego síncrono de 45 FPS en menos de 3 s, y lo devuelve a 60 cuando acelera;
  - Auto mantiene en 30 un juego con cola de 45 FPS al menos el 95 % de una corrida de 10 minutos.

  Es un modelo de host: no ejercita VideoOut, la retención del sink ni la consola.

## Archivos

- [hw_overlay.c](../native/hw_overlay.c): la entrada LÍMITE FPS, sus textos y sus líneas de `overlay.ini`, y `pw_hw_overlay_fps_limit`.
- [pw_fps_limit.h](../platform/ps4/pw_fps_limit.h): los objetivos de ritmo y las decisiones de Auto.
- [pw_wine_sink_ps4.c](../platform/ps4/pw_wine_sink_ps4.c): `fl_present`, la retención en el hilo que presenta, los controles del vblank y las líneas de registro. Corre desde el gancho de present al que llama [wine_vk_runtime.c](../native/wine_vk_runtime.c).
- [fps_limit_host_check.c](../tests/fps_limit_host_check.c), [test_fps_limit_host.py](../tests/test_fps_limit_host.py).
