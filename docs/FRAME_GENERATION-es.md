# Generación de fotogramas (experimental)

[English](FRAME_GENERATION.md) | [Español](FRAME_GENERATION-es.md)

Objetivo: que un juego que renderiza unos 30 fotogramas por segundo se vea a 60 fotogramas por segundo, insertando entre cada par de fotogramas reales una imagen interpolada a partir de esos dos. Solo se usa la imagen: ni vectores de movimiento, ni profundidad, ni cambios en el motor. Una imagen generada nunca hace avanzar la entrada, el audio ni la simulación del juego; solo puede hacer que el movimiento se vea más suave, y añade latencia (ver más abajo).

El trabajo va por etapas. Las etapas 1 a 5 ya corrieron en una PS4 Pro (04.15 y 04.19, más abajo): los contadores muestran fotogramas generados que llegan a la pantalla entre los reales. **No se afirma ninguna ganancia de fluidez** más allá de esos contadores, y solo para el juego probado.

## Estado

| Etapa | Qué | Estado | Evidencia |
| --- | --- | --- | --- |
| 1 | Observación: marcas de tiempo de origen, finalización de flip/vblank, contadores de renderizados/generados/mostrados | Implementada | PS4 Pro, 04.15 (corrida física de W303 20261117T170454Z, run-0203): `period_us` entre 16 682 y 16 684, unos 120 vblanks cada 2 s, `status_failed=0`, `pending_max=0`. La estructura del estado de vblank es correcta |
| 2 | Propiedad de dos fotogramas de origen completos | Implementada (copia en el hilo que presenta, esperada con su propia fence desde 04.19) | 04.18 (run-0217, NFS Underground 2, 1366x768): no se vio terminada la primera copia y el generador se apagó. 04.19 en PS4 Pro (corrida física de W303 20261117T215143Z, run-0218, NFS Underground 2, 1024x768): `PWFG copy 0..2: fence=signalled` tras 269–279 µs. Ahí el evento de la sonda se leyó `set`, así que el evento solo funciona; lo que falló en 04.18 no está demostrado |
| 3 | Prototipo de cómputo: movimiento grueso/fino, un fotograma generado, tiempo de GPU ("shadow": nunca se muestra) | Implementada | La comprobación en host pasa en Mesa lavapipe (solo referencia de host). Run-0218: unas 120 generaciones cada 2 s; tiempo medio de GPU: captura 247, grueso 198, fino 1 237, mezcla 233 µs (unos 1,9 ms en total, frente a un presupuesto de 8 ms) |
| 4 | Planificador de presentación: fotogramas generados y reales por turnos en vblanks medidos, con vuelta atrás | Implementada | Run-0218: `display on reason=pair`, luego ventanas de 10 s con `pairs=278 alone=22`, `267/20`, `259/14`, `gave_up=0`. La calidad de imagen no se evaluó con esa corrida |
| 5 | Interruptor por programa en el overlay, exclusión de MangoHud, reinicios del historial | Implementada | Run-0218: el interruptor activó la presentación para el programa. El rectángulo de MangoHud en la consola no se revisó cuadro a cuadro |
| 04.20 | La fila de FPS de MangoHud muestra los fotogramas en pantalla mientras se muestran fotogramas generados | Implementada | Compilación comprobada: sink y telemetría nativos para la PS4, `hud_elements.cpp` de MangoHud para x64 e i386. No ejecutada en la consola |

## Interruptor

Desde la 04.37, los reportes periódicos de `PWFG` (`display pairs`, `gpu_us`), `display on|off`, `shown_rate`, las sondas de arranque y `target sc=` aparecen solo con trazas encendidas (`/data/orbisdesk/trace.txt`, ver [trazas en release](RELEASE_TRACES-es.md#líneas-del-alpha-2)). Los fallos, `PWFG config`, `PWFG ready` y `PWFG mode=` se loguean siempre.

Desactivado por defecto, por programa. La entrada **GENERAR CUADROS** del overlay (`FRAME GEN` en inglés, L3+R3, después de LÍMITE FPS) lo enciende o lo apaga con X para el último programa abierto que sigue abierto, igual que ESTIRAR. La elección se guarda en `C:\orbis\overlay.ini` como `framegen.<exe>=on` (apagado no escribe línea), vale en el momento y vuelve cuando ese programa arranca de nuevo (`PWOVERLAY framegen=on program=<exe> why=start`). Solo muestra fotogramas generados mientras [LÍMITE FPS](FPS_LIMIT-es.md) mantiene el programa en 30, que desde 04.18 es el valor por defecto de todos los programas. Con 60, No, o Auto en 60, no genera ni muestra nada.

El archivo `/data/orbisdesk/framegen.txt` ya no hace falta. Queda como anulación para depurar y se lee una vez cuando el sink muestra su primer fotograma (primero con la apertura propia del kernel, después con la de libc). Si el archivo está, decide para todos los programas y la elección del overlay se ignora:

| Contenido | Efecto |
| --- | --- |
| ausente | Decide el overlay, por programa. Sin el archivo no se escriben las líneas de tiempos de 2 s de abajo |
| `off` | Apagado para todos los programas, diga lo que diga el overlay. Con líneas de tiempos |
| `timing` (o cualquier otra palabra, o vacío) | Solo la etapa 1: líneas de tiempos cada 2 s, no se genera nada |
| `shadow` | Etapas 1–3: cada present del swapchain seguido se copia y se genera un fotograma entre él y el anterior; el fotograma generado **no se muestra** |
| `display` | Etapas 1–4 para todos los programas, como si el overlay lo tuviera encendido en todos, con líneas de tiempos |

Cualquier fallo en las etapas 2–3 escribe una línea `PWFG failed ...` con el resultado de Vulkan, libera todo lo que creó el generador (`PWFG off for this run` y después `PWFG generator off for this run: real frames only from now on`) y deja la ruta de presentación como estaba.

## Etapa 1: qué se mide

El runtime de Vulkan llama a un gancho en cada present, en el hilo que presenta, después de que el WSI headless de Mesa haya terminado su copia al búfer de CPU ([wine_vk_runtime.c](../native/wine_vk_runtime.c) `pw_vk_present_hook`). El gancho es un puntero: los enlaces sin el sink, como el hijo PoP, lo dejan vacío. El sink ([pw_wine_sink_ps4.c](../platform/ps4/pw_wine_sink_ps4.c)) registra por swapchain el instante de cada present. Cada flip enviado se etiqueta con el número de presents que Wine había entregado cuando se dibujó. Antes de cada flip, el sink lee el estado de flip de VideoOut (último flip completado y su instante) y el estado de vblank (número de vblanks e instante).

Cada 2 s:

```text
PWFG timing window_ms=… vblanks=… period_us=… flips_submitted=… flips_done=… new_frames_shown=… repeat_vblanks=… flip_latency_us_avg=… flip_latency_us_max=… pending_max=… status_failed=… generated=… generated_failed=… generated_shown=… mode=…
PWFG source sc=… WxH format=… intervals=… rate_x10=… interval_us_avg=… sd=… min=… max=… vblank_spans=<0.5,1,2,3,4,5+>
```

| Campo | Significado |
| --- | --- |
| `vblanks`, `period_us` | Vblanks de la ventana y su periodo medido. No se supone la frecuencia de refresco |
| `flips_submitted`, `flips_done` | Flips que envió el sink y flips que VideoOut da por completados |
| `new_frames_shown` | Flips completados que llevaban un present de Vulkan nuevo: fotogramas renderizados que llegaron a la pantalla |
| `repeat_vblanks` | `vblanks - flips_done`: vblanks que volvieron a mostrar el búfer anterior |
| `flip_latency_us_*` | De envío a finalización del flip completado más reciente, según cada lectura |
| `generated`, `generated_shown` | Fotogramas hechos por la etapa 3 y fotogramas generados a los que el presentador hizo flip (etapa 4). Un flip generado no cuenta en `new_frames_shown`; el flip real que le sigue, sí |
| `vblank_spans` | Intervalos entre fotogramas de origen redondeados a periodos de vblank. Un juego estable a 30 FPS deja sus intervalos en el grupo `2` |

Límites de esta medición: el estado de flip se lee cuando el sink está a punto de hacer flip, así que dos flips que terminan entre dos lecturas cuentan cada uno, pero solo el más reciente tiene instante. La estructura del estado de vblank se declara aquí (el SDK declara la función sin parámetros), así que una primera ejecución debe confirmar que `period_us` está cerca de 16 683 y que `status_failed` es 0. El contador de presents es global: con dos programas Vulkan presentando a la vez, `new_frames_shown` los mezcla.

El sink actual es la referencia que hay que medir: su presentador asíncrono duerme 16 ms después de cada fotograma que muestra. En 04.15 (run-0203), con Portal 2 al frente igual completó entre 101 y 117 flips cada 2 s, casi todos con fotogramas nuevos. Con 115 a 140 presents por segundo solo llegaban a la pantalla unos 57 fotogramas nuevos por segundo: cerca de la mitad de lo renderizado no se veía nunca. `new_frames_shown` vale 0 solo donde no hay ningún fotograma Vulkan en pantalla, por ejemplo el escritorio o una ventana GDI. La etapa 4 cambia la espera fija por esperas al estado de flip, pero solo para los fotogramas que muestra en pares.

## Etapa 2: propiedad

Una imagen presentada está en un búfer visible por la CPU que el WSI headless de Mesa mantiene por imagen del swapchain ([patch-mesa-wsi.py](../tools/vk-h0/patch-mesa-wsi.py)). El siguiente present de la misma imagen del swapchain lo sobrescribe, así que una dirección no conserva un fotograma. En modo `shadow` el gancho copia cada present del swapchain seguido a una de dos ranuras de historial propias del generador, antes de que el present retorne:

- La copia es una pasada de cómputo en el dispositivo y la cola Vulkan propios del compositor nativo ([hw_sink_gpu.c](../native/hw_sink_gpu/hw_sink_gpu.c)). Lee el búfer del WSI por dirección de GPU, como el compositor ya lee las capas de imagen. No se usa nada del dispositivo del juego (imágenes, vistas, semáforos), así que no existe ningún objeto entre dispositivos.
- Desde 04.19 la copia es un envío propio con su propia fence. El hilo que presenta espera esa fence con `vkWaitForFences`, la misma espera que hace el compositor en cada fotograma que dibuja, y retorna cuando está señalada, así que el juego no puede reutilizar la imagen mientras se lee. La generación es un segundo envío que empieza con una barrera, que lo ordena después de la copia en la misma cola. El hilo que presenta no lo espera. Se siguen evitando los objetos de sincronización del kernel (semáforos), porque el port de PS4 tiene probadas las fences, pero no los semáforos.
- La cola del compositor se comparte con el hilo presentador, así que todos los envíos toman un mismo cerrojo.
- La siguiente copia espera primero la fence de la generación anterior, porque sobrescribe la ranura que leyó esa generación.

### Por qué 04.19 cambió la espera de la copia

En 04.18 la copia y la generación eran un único envío. Después de la copia, el command buffer activaba un `VkEvent` y el hilo que presenta lo consultaba con `vkGetEventStatus`. En la PS4 Pro (run-0217, NFS Underground 2, DXVK de 32 bits, swapchain de 1366x768), el generador se inicializó (`FLAT-free, timestamps=1`) y creó sus búferes. Después apareció `PWFG off for this run: the GPU did not finish a copy`: el evento no se vio activo en 1 s. El juego siguió a 30 FPS y el compositor, en el mismo dispositivo y la misma cola, siguió dibujando cada fotograma después sin ninguna línea `PWSINK gpu_failed`, así que la cola no se colgó. La ventana de 5 s alrededor del fallo perdió unos 45 de 150 presents (alrededor de 1,5 s), lo que encaja con un tiempo límite de 1 s del evento más la creación de los pipelines, y no con un segundo tiempo límite de 1 s de la fence al apagar, pero la espera del apagado no se registraba.

Candidatos revisados contra el código:

| Candidato | Resultado |
| --- | --- |
| Evento | Nunca se había usado en este port de PS4 antes de 04.18. En GFX7, RADV convierte un evento de la etapa de cómputo en dos paquetes `EVENT_WRITE_EOP` hacia un búfer GTT mapeado por la CPU. Es la única primitiva del camino de la copia que el port no tenía probada. Sospechoso, no probado: la sonda de 04.19 lo dirá |
| Fence/línea de tiempo | El compositor espera una fence en cada fotograma. El winsys de PS4 señala las fences con su propia escritura de fin de pipeline en cada envío |
| Cerrojo de la cola frente al compositor | Ambos envían bajo un mismo cerrojo; el bucle de consulta de 04.18 no lo retenía. El compositor siguió enviando después del fallo |
| Envío nunca vaciado | El winsys de PS4 entrega cada envío a la GPU de inmediato y llama a submit-done |
| Disposición o propiedad de la imagen de origen | La copia lee por dirección el búfer lineal de CPU del WSI, como las capas de imagen del compositor; la misma imagen se mostraba por ese camino (`path=gpu_layer`) |
| 1366x768 | Dentro de los límites (2560x1440); el paso de 5464 está alineado a 4 bytes; los búferes se crearon |
| Tiempo límite | 1 s para una copia de unos 4 MB. Los pipelines se crearon antes, así que el primer envío no compila nada |

Qué hace 04.19:

- **La copia espera una fence**, como se describe arriba. La copia ya no usa el evento.
- **Una sonda por corrida**, antes de la primera copia. Tres envíos, cada uno solo y cada uno esperado con su fence: un command buffer vacío, un reinicio del query pool con dos marcas de tiempo (leídas después) y un evento activado tras la etapa de cómputo (leído hasta 100 ms después de la fence). Una línea por cada uno. Una sonda cuya fence no se señala apaga la generación para la corrida. Las marcas de tiempo que no se pueden leer se descartan. El resultado del evento solo se informa.
- **Registro de las esperas.** Las tres primeras copias, y cualquier copia cuya fence no se señale, registran el resultado de la fence y el tiempo esperado. Una fence de generación que no se señala registra lo mismo. El apagado registra cómo terminaron sus esperas.
- **Nada se libera con la GPU en marcha.** Si un envío sigue en marcha al apagar, su memoria se conserva en lugar de liberarse, porque la GPU escribiendo memoria liberada provocaría un fallo y el sistema cerraría la aplicación.

Líneas esperadas en la consola:

```text
PWFG probe empty: fence=signalled waited_us=<n>
PWFG probe timestamps: fence=signalled waited_us=<n> results=0 ticks=<n>
PWFG probe event: fence=signalled waited_us=<n> event=set|reset (<r>) after_fence_us=<n>
PWFG ready: 4 compute passes, FLAT-free, timestamps=1 period_ns=10.000, copy waits on its fence
PWFG copy 0: fence=signalled (0) waited_us=<n> limit_us=1000000 image=<p> 1366x768 pitch=5464
```

Cómo leerlas:

- `event=reset` con la fence señalada confirma el evento como causa en 04.18. La generación sigue entonces, porque ya nada espera el evento.
- `event=set` significa que el evento funciona solo. El fallo de 04.18 vino entonces de algo del envío combinado, y la línea de la copia muestra si la copia con fence termina.
- Una sonda o copia con `fence=timeout` significa que la GPU no terminó ese envío en absoluto. Su `waited_us` y la línea del apagado son la evidencia que hay que informar.

Swapchain seguido: el primero que presenta. Otro lo reemplaza solo cuando el seguido lleva 0,5 s sin presentar. Un tamaño u orden de bytes nuevo vuelve a reservar los búferes y reinicia el historial.

## Etapa 3: las pasadas de cómputo

Cuatro shaders de cómputo, compilados a SPIR-V por la build de hardware junto a los shaders del compositor. No se ejecuta ningún compilador GLSL en la consola. Todos los datos están en búferes de almacenamiento, así que no intervienen capacidades de formatos de imagen. El origen debe ser uno de los formatos RGBA/BGRA de 32 bits que el compositor ya muestra.

| Pasada | Malla (origen 1280×720) | Trabajo |
| --- | --- | --- |
| [fg_capture](../native/hw_sink_gpu/fg_capture.comp) | 640×360 (una por cada 2×2 píxeles) | Copia los píxeles a la ranura del historial; escribe la luminancia a media resolución |
| [fg_coarse](../native/hw_sink_gpu/fg_coarse.comp) | 80×45 celdas de 16×16 píxeles | 13×13 desplazamientos candidatos de hasta ±24 píxeles, 16 muestras cada uno; diferencia absoluta media más un pequeño coste por unidad de movimiento |
| [fg_fine](../native/hw_sink_gpu/fg_fine.comp) | 160×90 celdas de 8×8 píxeles | Cero y los vectores gruesos de las 3×3 celdas vecinas como candidatos, un paso al mejor desplazamiento vecino y luego un ajuste de parábola subtexel. Una coincidencia exacta conserva un desplazamiento entero |
| [fg_blend](../native/hw_sink_gpu/fg_blend.comp) | 1280×720 | Movimiento interpolado entre centros de celda; el fotograma anterior se muestrea medio movimiento hacia atrás y el actual medio movimiento hacia delante, y se promedian. Vuelve al fotograma actual donde el error de coincidencia es alto o las dos muestras desplazadas no coinciden |

Cada pasada se comprueba tras compilarse en busca de instrucciones de memoria FLAT, como el propio shader del compositor (W153). Una instrucción FLAT desactiva el generador. La captura lee por dirección como base uniforme más un desplazamiento de 32 bits, la forma que en GFX7 se compila a MUBUF.

Memoria a 1280×720: cuatro búferes de color de 3,5 MiB (dos ranuras de historial y dos salidas), dos búferes de luminancia de 0,9 MiB y los campos de movimiento (0,3 MiB): unos 16 MiB. Estimación de lecturas por fotograma generado, a partir del código: unos 20 M lecturas de luminancia (grueso), 41 M (fino), 12 M (mezcla). No son tiempos de GPU. La línea `PWFG gpu_us` los mide con marcas de tiempo, junto con cuánto tiempo se retuvo al hilo que presenta (`present_block_us`):

```text
PWFG gpu_us capture=avg/max coarse=avg/max fine=avg/max blend=avg/max (avg/max) present_block_us=avg/max generated=… frame=WxH
```

Con las trazas activas, la generación número 90 escribe una vez `previous.bmp`, `current.bmp` y `generated.bmp` en `/data/orbisdesk/framegen/`. Sirven para inspeccionar a ojo contenido real de un juego.

### Comprobación en host

```sh
python3 tests/test_framegen_host.py
```

Compila los mismos shaders y ejecuta [las cuatro pasadas](../tests/framegen_host_check.c) en lavapipe de Mesa, sobre fotogramas sintéticos con un punto medio conocido. Requisitos: `libvulkan-dev`, `mesa-vulkan-drivers`, glslang. Resultado del 2026-11-16 (llvmpipe, LLVM 15.0.7):

```text
motion: mean abs error vs true midpoint: generated=1.16 average=3.33 repeat=3.75
motion: fine field in the square 6.00,3.00 (expect 6,3 texels) err=0.000; background 0.00,0.00 err=0.000
cut: generated vs current frame 0.33 (0 = full fallback)
PASS framegen host check
```

Es solo comportamiento de referencia en host de la lógica de los shaders. No dice nada de la GPU de la PS4, la comprobación FLAT, los tiempos, los búferes del WSI ni el contenido real de un juego. La primera ejecución de esta comprobación encontró que el ajuste subtexel movía 0,05 texel un fondo perfectamente estático, lo que haría temblar el texto estático. La pasada fina ahora conserva desplazamientos enteros en las coincidencias exactas.

Desde 04.18 la comprobación también repite el caso de movimiento con un rectángulo conservado sobre el cuadrado que se mueve (etapa 5): cada píxel de adentro tiene que ser, sin cambios, la palabra del fotograma actual. Resultado del 2026-11-17: `keep: pixels in the rectangle that differ from the current frame 0 (expect 0); generated pixels outside 3009`.

## Etapa 4: mostrar los fotogramas generados

LÍMITE FPS en 30 suelta el fotograma N del juego justo después del vblank V, dos vblanks después del fotograma N-1. La retención ocurre en el hilo que presenta, después de la copia del generador, así que la generación corre durante la retención. Después el fotograma N llega al hilo presentador del sink como parte de la pila de capas de Wine. Con un fotograma que califica, el presentador:

1. dibuja la pila con la imagen del fotograma N reemplazada por el fotograma generado entre N-1 y N, y hace flip (en pantalla en V+1);
2. espera a que VideoOut dé ese flip por hecho, dibuja la pila con la copia propia del generador de N y hace flip (V+2);
3. espera también ese flip, para que el dibujo siguiente nunca vaya a un búfer que está en pantalla o pendiente.

N+1 se suelta en V+2 y sigue igual. En pantalla queda un fotograma por vblank, generado y real por turnos. El escritorio, el puntero, el overlay del título, el contador de cuadros y la página de Steam los dibuja el sink en los dos flips como en cualquier otro, así que nunca se generan. Un fotograma que no califica se muestra como antes: la pila como la entregó Wine, y después la pausa habitual de 16 ms.

[pw_framegen_sched.h](../platform/ps4/pw_framegen_sched.h) decide para cada fotograma nuevo del swapchain seguido. Un par necesita todo lo siguiente, comprobado en este orden. El primer requisito que falla es el motivo que se registra:

| Motivo en el registro | El fotograma se muestra solo porque |
| --- | --- |
| `gave_up` | Pasó del presupuesto demasiado tiempo, ver abajo. Dura hasta que cambie el programa al frente o el ajuste |
| `generator_off` | El generador falló y se liberó para toda la ejecución |
| `cap_not_30` | LÍMITE FPS no mantiene el programa en 30: No, 60, o Auto en 60 |
| `vblank_not_trusted` | LÍMITE FPS acompasa por tiempo y no por la cuenta de vblank |
| `not_followed` | La imagen no es la última copia del generador, por ejemplo otro swapchain |
| `first` | La primera copia después de reiniciar el historial no tiene fotograma anterior |
| `warming_up` | Todavía no hay 30 generaciones medidas con marcas de tiempo de GPU |
| `gpu_over_budget` | El tiempo de GPU medio de la generación (copia más tres pasadas) supera 8 ms |
| `late` | La generación no había terminado 4 ms después de que el fotograma llegara al presentador |
| `irregular` | El fotograma no se soltó exactamente dos vblanks después del anterior |

**Vueltas atrás.**
- Un promedio de más de 8 ms durante 60 decisiones seguidas hace que se rinda para ese programa. La generación se detiene, así que a la GPU ya no se le cobra por fotogramas que nadie ve, y se registra `PWFG display off reason=gpu_over_budget ...: gave up for this program, generation stops`. Vuelve a intentarlo cuando cambia el programa al frente o cuando se apaga y se enciende el interruptor.
- Un fallo de Vulkan en el generador lo apaga para toda la ejecución.
- Si el flip generado no se da por hecho en 50 ms, el fotograma real se muestra como se entregó.
- En una cola sin marcas de tiempo la generación nunca se mide, así que nunca sale de `warming_up` y solo se muestran fotogramas reales.
- Con la generación encendida, el generador copia y genera solo mientras el límite es 30.

**Latencia.** Cada fotograma real llega a la pantalla un vblank (16,7 ms) más tarde que sin generación, porque primero se muestra el fotograma intermedio. La entrada, el audio y los tiempos propios del juego no cambian.

**Qué muestran los contadores.** El `FPS VK` del overlay cuenta los presents del juego (30). Desde 04.20, la fila de FPS de MangoHud muestra los fotogramas en pantalla mientras se muestran fotogramas generados (más abajo). El contador de cuadros propio del sink (F12 en títulos de 32 bits) y el gráfico de tiempos de cuadro de la lectura del overlay cuentan los flips de salida, que pasan a ser 60 mientras se muestran pares.

### La fila de FPS de MangoHud (04.20)

MangoHud cuenta los presents de la swapchain en la que dibuja. El sink agrega los fotogramas generados después de que MangoHud dibujó, así que con GENERAR CUADROS activado MangoHud seguía mostrando 30 (run-0218). Desde 04.20 la fila de FPS muestra los fotogramas en pantalla, reales más generados, con `FG` en lugar del superíndice `FPS`: por ejemplo `60 FG` junto a `VULKAN`.

Por qué la fila propia de MangoHud y no una etiqueta dibujada por el sink:
- **Visibilidad.** El overlay no puede leer si MangoHud está visible (Shift+F12, o F12 desde un teclado); ver la etapa 5. Una etiqueta del sink podría quedar en pantalla con el HUD oculto. La fila de MangoHud se dibuja solo mientras MangoHud dibuja.
- **MangoJuice.** Posición, fuente, tamaño, colores, `fps_only`, `fps_color_change` y el orden de las filas son los de `MangoHud.conf`, para todos los HUD, porque MangoHud dibuja la fila. Una etiqueta que los imitara podría apartarse de lo que guarda MangoJuice.
- **32 y 64 bits.** El mismo parche está en las dos builds de MangoHud; la build i386 copia el árbol parcheado.
- **Costo.** Necesita recompilar MangoHud (x64 e i386). Una etiqueta del sink también habría necesitado cambios en MangoHud para saber si el HUD está visible, así que no habría sido más chica.

Cómo funciona:
1. El presentador cuenta, para la imagen que sigue la generación, cada fotograma real nuevo una vez y cada fotograma generado cuyo flip VideoOut informó terminado. Una vez por segundo publica los fotogramas por segundo (en décimas): todos, reales y generados, con el tamaño de la imagen. No se estima nada.
2. MangoHud ya pide al lado nativo el uso de CPU y GPU mediante una clase privada de `NtQuerySystemInformation` ([pw_telemetry.h](../platform/ps4/pw_telemetry.h)). Quien pasa un búfer que alcanza para el `struct pw_ps4_telemetry_fg`, más grande, recibe la versión 2, con esas cifras agregadas. Quien pasa 80 bytes sigue recibiendo la versión 1, sin cambios, y wow64 deja pasar la consulta para los programas de 32 bits.
3. En los elementos `fps` y `fps_only` de MangoHud ([parche](../tools/vk-h0/patch-mangohud-orbis-framegen.py)): cuando la consulta dice que hubo fotogramas generados en pantalla en un segundo medido dentro de los últimos 2,5 s, y la imagen tiene el tamaño de esta swapchain, el valor son los fotogramas en pantalla y el superíndice dice `FG`. `FG` se muestra aun con `hide_fps_superscript`, para que el número nunca se lea como la tasa del juego. Si no, MangoHud muestra su propio valor, como antes.

Lo que sigue siendo de MangoHud: la columna de tiempo de cuadro (`ms`), el gráfico de tiempos de cuadro, el 1% más bajo, el limitador de FPS y los logs de MangoHud siguen con los presents del juego. Con GENERAR CUADROS activado y nada generado (límite en 60, se rindió, generador apagado), la fila muestra el valor propio de MangoHud y sin `FG`.

Límites:
- La correspondencia es por tamaño: otra ventana Vulkan de exactamente el mismo tamaño también mostraría `FG`.
- El valor se actualiza una vez por segundo, como el propio de MangoHud.
- La fila está dentro del HUD de MangoHud, cuyo rectángulo el generador copia del fotograma real (etapa 5). No se interpola mientras el HUD quede dentro de ese rectángulo estimado.

Líneas de log:

```text
PWFG shown_rate on 1024x768 shown_x10=… real_x10=… generated_x10=… window_us=…     (cuando empiezan o dejan de mostrarse fotogramas generados)
PWTELEM framegen query bytes=112 version=2 fg_flags=…                                 (una vez, el primero que pide la versión 2)
PWHUD framegen query=00000000 bytes=112 version=2 flags=1 image=1024x768 shown_x10=… real_x10=… generated_x10=… hud=1024x768
```

La línea `PWHUD` es de MangoHud (salida de depuración de Wine) y se escribe cuando cambian los flags o el tamaño de la imagen.

Líneas de registro:

```text
PWFG mode=display (overlay)
PWFG display on reason=pair cap=2 vblank_trusted=1 span=2 gpu_us=… timed=…
PWFG display off reason=<motivo> cap=… vblank_trusted=… span=… gpu_us=… timed=…[: gave up for this program, generation stops]
PWFG display pairs=… alone=… reasons=<motivo>:<cuenta>,… gpu_us=… budget_us=8000 timed=… gave_up=0|1   (cada 10 s)
```

`on` y `off` se registran cuando cambia la decisión. La línea de 10 s cuenta los pares y los fotogramas mostrados solos en esa ventana. `PWFG gpu_us` (etapa 3) sigue informando cada pasada cada 120 generaciones.

### Comprobación en host

```sh
python3 tests/test_framegen_sched_host.py
```

Ejecuta las [decisiones](../tests/framegen_sched_host_check.c) sobre secuencias de fotogramas simuladas:
- un juego estable a 30 FPS con 5 ms de generación muestra pares después de 30 fotogramas de calentamiento;
- 60, una cuenta de vblank no confiable y otro swapchain nunca forman pares;
- un fotograma tarde o una generación tarde se muestran solos y el siguiente vuelve a formar par;
- 9,5 ms se rinde a los 60 fotogramas y sigue rendido;
- las rachas por encima del presupuesto de menos de 60 fotogramas no lo rinden;
- un generador caído muestra fotogramas reales;
- un reinicio lo vuelve a intentar.

No ejecuta el sink, VideoOut ni la GPU.

## Etapa 5: por programa, MangoHud y reinicios

- **Por programa:** la entrada del overlay y la línea de `overlay.ini` de arriba. El sink lee la elección del programa al frente en cada present (`PWFG mode=display (overlay)` / `PWFG mode=off (overlay)` cuando cambia).
- **MangoHud:** MangoHud dibuja su HUD dentro de la imagen del juego antes del present, así que el generador arrastraría su texto con el movimiento o promediaría dos valores. Mientras MangoHud dibuja sobre el programa al frente, el overlay le pasa al generador un rectángulo que `fg_blend` copia sin cambios del fotograma real. El rectángulo sale de la copia propia del overlay de la disposición de MangoHud (la imitación de su lectura: filas, posición, desplazamientos y `font_size` del `MangoHud.conf` que MangoJuice guarda para todos los HUD). Se agranda alrededor de la mitad más 16 píxeles por lado, porque aquí no se conocen los anchos exactos del texto de MangoHud. El overlay vuelve a leer `MangoHud.conf` dentro de los 5 s siguientes a un guardado de MangoJuice. No se sabe si el HUD está visible (Shift+F12), así que el rectángulo queda afuera de todos modos. GENERAR CUADROS nunca escribe `MangoHud.conf`, y el mostrar/ocultar de MangoHud del overlay funciona como antes en programas de 32 y de 64 bits.
- **Reinicios del historial:** otro swapchain seguido, un tamaño u orden de bytes nuevo, un cambio del programa al frente o del interruptor, y cualquier present que pasó sin copia (la generación en pausa mientras el límite no era 30) reinician el historial (`first`), así que nunca se genera contra un fotograma viejo. Las decisiones de presentación empiezan de nuevo cuando cambia el interruptor o el programa al frente. Los cortes de escena y los menús dentro del juego dependen de la vuelta al fotograma actual de la mezcla. Un detector de cortes sigue siendo un paso posterior.

## Límites de latencia y calidad

- Para mostrar el fotograma entre N-1 y N, el fotograma N tiene que existir ya. Por eso el fotograma real N se muestra un vblank (16,7 ms) más tarde que sin generación. La generación corre mientras LÍMITE FPS retiene al hilo que presenta, así que no suma demora mientras quede dentro del presupuesto.
- El HUD de MangoHud está dentro de la imagen capturada. Su rectángulo se deja fuera de la generación (etapa 5) con una estimación de su disposición, no con sus píxeles reales: un HUD que MangoJuice dispuso de otra forma (otra fuente, filas extra) puede sobresalir. El escritorio, el puntero, el overlay del título y la interfaz de Steam los dibuja el sink después de componer y nunca se generan.
- El HUD propio de un juego no tiene máscara. El HUD estático conserva movimiento cero, pero el HUD sobre contenido en movimiento puede emborronarse.
- Los cortes de escena, las transparencias y las oclusiones dependen de la vuelta al fotograma actual. La comprobación en host solo cubre un corte completo.
- El generador sigue un solo swapchain. Con dos programas Vulkan presentando a la vez, solo se genera el seguido; el otro se muestra como se entregó.

## Siguientes pasos

1. **Corrida de 04.20 en consola** (necesita las builds x64 e i386 de MangoHud, la build del paquete, una subida y la aprobación del usuario): GENERAR CUADROS en el mismo juego que run-0218, con MangoHud visible. Se espera: la fila de FPS de MangoHud en unos 60 con `FG`, las líneas `PWFG shown_rate on` y `PWHUD framegen ... flags=1`, y la fila de vuelta al valor propio de MangoHud sin `FG` al desactivar GENERAR CUADROS. Ocultar y mostrar MangoHud desde el overlay en un programa Vulkan de 64 bits y en uno de 32 bits; guardar un cambio en MangoJuice y comprobar que se aplica a la fila.
2. Si el tiempo de GPU pasa del presupuesto en juegos reales: achicar la búsqueda gruesa (menos candidatos, o luminancia a un cuarto de resolución) antes de subir el presupuesto.
3. Un detector de cortes (coste grueso medio alto) que muestre solo el fotograma real, y un reinicio ante un cambio de resolución dentro del juego sin swapchain nuevo.
4. Solo cuando la etapa 4 esté medida físicamente (pares contados, `generated_shown` frente a `new_frames_shown` en vblanks medidos, y lo que observe el usuario) se podrá describir un efecto en la fluidez.

## Licencias

El interpolador está escrito para OrbisDesk bajo LGPL-2.1-or-later, como el compositor nativo que amplía. El emparejamiento jerárquico de bloques sobre luminancia con vuelta al fotograma real es una técnica general. El diseño se basó en la lectura del algoritmo de un interpolador de un emulador existente, con licencia GPL-2.0-or-later, pero no se copió de él ningún código, shader ni conjunto de constantes (ver [notas de terceros](../THIRD_PARTY-es.md) y [licencias de la release](RELEASE_LICENSES-es.md)).

## Archivos

- [native/wine_vk_runtime.c](../native/wine_vk_runtime.c): el gancho de present.
- [platform/ps4/pw_wine_sink_ps4.c](../platform/ps4/pw_wine_sink_ps4.c): contadores de la etapa 1, el interruptor, la llamada al generador y los pares del presentador de la etapa 4 (`fgd_begin`, `fgd_stack`, `fgd_wait_flip`).
- [platform/ps4/pw_framegen_sched.h](../platform/ps4/pw_framegen_sched.h): la decisión de la etapa 4 para cada fotograma.
- [native/hw_sink_gpu/framegen.inc.c](../native/hw_sink_gpu/framegen.inc.c): etapas 2–3 y `pw_sink_gpu_fg_pick`, incluido por [hw_sink_gpu.c](../native/hw_sink_gpu/hw_sink_gpu.c).
- [native/hw_sink_gpu/fg_common.glsl](../native/hw_sink_gpu/fg_common.glsl) y los cuatro shaders `fg_*.comp`. `fg_blend` recibe el rectángulo conservado.
- [native/hw_overlay.c](../native/hw_overlay.c): la entrada GENERAR CUADROS, su línea de `overlay.ini`, `pw_hw_overlay_framegen` y `pw_hw_overlay_hud_rect`.
- [platform/ps4/pw_telemetry.h](../platform/ps4/pw_telemetry.h) y [native/telemetry.c](../native/telemetry.c): la telemetría de versión 2 con los fotogramas en pantalla; `pw_hw_sink_fg_rate`, del sink, los publica.
- [tools/vk-h0/patch-mangohud-orbis-framegen.py](../tools/vk-h0/patch-mangohud-orbis-framegen.py): la fila de FPS de MangoHud, aplicada por [build-mangohud.sh](../tools/vk-h0/build-mangohud.sh) y comprobada por [build-mangohud-i386.sh](../tools/vk-h0/build-mangohud-i386.sh).
- [tools/build-wine-hardware.py](../tools/build-wine-hardware.py): compila los shaders y registra sus hashes.
- [tests/test_framegen_host.py](../tests/test_framegen_host.py), [tests/framegen_host_check.c](../tests/framegen_host_check.c): comprobación en host de los shaders.
- [tests/test_framegen_sched_host.py](../tests/test_framegen_sched_host.py), [tests/framegen_sched_host_check.c](../tests/framegen_sched_host_check.c): comprobación en host de las decisiones.
