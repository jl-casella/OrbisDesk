# Compilación de shaders, tiempo de cuadro y la caché de shaders en disco

[English](SHADER_CACHE.md) | [Español](SHADER_CACHE-es.md)

Los juegos pueden perder cuadros por segundo durante cinemáticas y movimientos de cámara rápidos con guion, y recuperarse cuando el control vuelve al personaje. Se vio en Alan Wake's American Nightmare (OpenGL mediante Mesa Zink sobre RADV) y PES 2013 (Direct3D 9 mediante DXVK sobre RADV). Dos causas distintas se ven igual en pantalla:

- **tirones por compilación**: un material o efecto nuevo necesita un shader o pipeline que no se compiló en esta sesión, y un cuadro espera la compilación. Mesa se compila con la caché de shaders en disco desactivada (`-Dshader-cache=disabled` en `tools/vk-h0/build-mesa*.sh`), así que cada pipeline se vuelve a compilar en cada sesión. DXVK 2.7.1 ya no tiene caché de estados propia, así que RADV es el único lugar donde podrían persistir los pipelines compilados;
- **un límite sostenido**: cada cuadro de la escena tarda más de lo que permite el límite, porque la GPU o uno de los hilos del juego está saturado. Una caché no ayuda aquí.

04.27 agrega una medición que las distingue y una caché en disco opcional para RADV.

## La medición: `PWPERF`

Desde la 04.37, `PWPERF` se mide y se loguea solo con trazas encendidas (`/data/orbisdesk/trace.txt`, ver [trazas en release](RELEASE_TRACES-es.md#líneas-del-alpha-2)).

RADV avisa al sink cada creación de `vkCreateGraphicsPipelines` (completa y de biblioteca), `vkCreateComputePipelines` y `vkCreateShadersEXT` ([parcheador de la traza de pipelines](../tools/vk-h0/patch-mesa-pipeline-trace.py), [sink](../platform/ps4/pw_wine_sink_ps4.c)). Los pipelines de DXVK, de Zink y de programas Vulkan nativos llegan todos a RADV en el proceso del título, en el hilo que los compile. Cada aviso lleva el tiempo de la creación, si RADV encontró el pipeline en una caché y si lo leyó de la caché en disco.

Cada 5 segundos, mientras un programa presenta, el log de la ejecución recibe una línea, independiente de LÍMITE FPS y de la generación de cuadros:

```text
PWPERF window_ms=5001 frames=98 frame_us_avg=51020 frame_us_max=183400 over_50ms=61 over_100ms=1 hitches=1
  hitches_with_compile=1 worst_frame_compile_us=131000 compiles=34 compile_ms=812 compile_max_us=129800 cached=20
  disk=0 misses=14 miss_ms=790 gfx=12/640ms lib=22/172ms compute=0/0ms shader=0/0ms gpu_busy_pct=88
  cpu_cores_x10=31 present_thread_pct=97
```

(una sola línea en el log; partida aquí)

| Campo | Significado |
| --- | --- |
| `frames`, `frame_us_avg`, `frame_us_max` | intervalos entre presents en la ventana, como los ve el juego (antes de que LÍMITE FPS retenga un present) |
| `over_50ms`, `over_100ms` | intervalos de al menos 3 y 6 vblanks |
| `hitches`, `hitches_with_compile` | cuadros de más del doble del promedio de la ventana anterior y de al menos 40 ms; los que tuvieron al menos 10 ms de compilación (en cualquier hilo) desde el present anterior |
| `worst_frame_compile_us` | tiempo de compilación dentro del cuadro más largo |
| `compiles`, `compile_ms`, `compile_max_us` | creaciones, su tiempo total y el más largo |
| `cached`, `disk`, `misses`, `miss_ms` | encontradas en una caché (memoria o disco), leídas del disco, compiladas, tiempo compilando |
| `gfx`, `lib`, `compute`, `shader` | cantidad/tiempo por tipo: pipelines gráficos completos, bibliotecas de pipeline gráfico (DXVK y Zink las enlazan rápido y arman pipelines optimizados en segundo plano), cómputo, objetos shader |
| `gpu_busy_pct` | parte de la ventana que la GPU dedicó al trabajo GFX del título (la misma unión de timestamps que la carga de GPU de MangoHud) |
| `cpu_cores_x10` | tiempo de CPU del proceso en la ventana, en décimas de núcleo |
| `present_thread_pct` | parte de CPU del hilo que presenta; -1 cuando otro hilo presentó al final de la ventana. Con Zink es el hilo GL del juego; DXVK presenta desde su propio hilo de cola |

Cada creación que tarda 50 ms o más también deja una línea `PWPERF slow_compile kind=… us=… cached=… disk=…`, como mucho 8 por ventana.

Cómo leerla:

- tirones con tiempo de compilación dentro, `misses` y `miss_ms` altos en las ventanas donde ocurre la caída y casi cero después: tirones por compilación;
- casi todos los cuadros de más de 50 ms con pocas compilaciones: un límite sostenido. Un `gpu_busy_pct` cerca de 100 apunta a la GPU; un `present_thread_pct` cerca de 100 con una parte de GPU menor apunta a ese hilo.

Límites: no se incluye el tiempo que Zink pasa en el invitado antes de que su pipeline llegue a RADV (GLSL a NIR, NIR a SPIR-V). Las compilaciones en hilos de segundo plano se cuentan en el cuadro con el que coincidieron aunque no lo hayan bloqueado; `hitches_with_compile` es una correlación, no una prueba. Con dos programas presentando a la vez los intervalos se mezclan.

## Lo que ya muestra la ejecución de Alan Wake en W303

En la ejecución 0238 (W303, LÍMITE FPS 30, generación de cuadros activa) el menú mantiene 150 presents por ventana (30 fps). En las ventanas lentas `held=0` y `late` es igual a `presents` (66–109 por ventana): ningún present llegó a tiempo para ser retenido, así que cada cuadro tardó más de 2 vblanks, no solo algunos. Las líneas de generación de cuadros que dan el intervalo en vblanks entre presents liberados coinciden: 971 muestran 3 vblanks y 95 muestran 4, contra 6 con 5 o más. Son unos 15–20 fps constantes y no cuadros largos aislados, así que la mayor parte de esa caída es un **límite sostenido**, que la caché en disco no puede quitar. Los tirones por compilación pueden sumar algún cuadro largo ocasional; la línea `PWPERF` resuelve ambas cosas, y `gpu_busy_pct` frente a `present_thread_pct` dice si la parte sostenida es la GPU o el hilo del juego.

## La caché de shaders en disco (cambio de compilación opcional)

Un cambio aparte activa la caché en disco de Mesa en la compilación de RADV que enlaza Wine (`VARIANT=wine` de `tools/vk-h0/build-mesa.sh`). Hallazgos:

- **Dependencias de compilación**: Mesa requiere zlib o zstd para su caché. zlib ya se encuentra en el sysroot de PS4 (`~/vk-h0/sysroot/lib/libz.a`, que compila `build-probe.sh`) y `tools/build-wine-hardware.py` ya la enlaza en el ELF de hardware. zstd sigue desactivado; Mesa comprime entonces con zlib.
- **Zink no puede tener caché propia**: Mesa rechaza `shader-cache` en anfitriones Windows (`Shader Cache does not currently work on Windows`), y Zink se compila como DLL de Windows. Los pipelines de Zink igual llegan a RADV, así que la caché en disco de RADV cubre su compilación final, que es la parte cara; el trabajo propio de Zink con GLSL/NIR/SPIR-V sigue siendo por sesión.
- **DXVK**: 2.7.1 no tiene caché de estados (su `dxvk.conf` no tiene esa opción); la caché en disco de RADV es lo que conserva también sus pipelines.
- **Identidad de la caché**: RADV identifica su caché con `-Dradv-build-id`. Era la cadena fija `mesa-26.0.8-ps4-h0`, que permitiría que una compilación posterior con parches de Mesa cambiados reutilice binarios compilados por una anterior. La compilación ahora lo deriva de un hash de las fuentes de Mesa parcheadas y del archivo cross, así que cualquier cambio en el compilador o en el port empieza una caché nueva.
- **Ubicación y tamaño**: el título fija `MESA_SHADER_CACHE_DIR=/data/orbisdesk/shader-cache`, el tipo de caché de base de datos (`MESA_DISK_CACHE_DATABASE=1`, 8 partes, así que como mucho 16 archivos abiertos) y un tope de 256 MB compilado (`-Dshader-cache-max-size=256M`); la base de datos descarta las entradas usadas hace más tiempo cuando lo supera. Un valor ya presente en el entorno tiene prioridad. Crear `/data/orbisdesk/shader-cache.off` desactiva la caché (`MESA_SHADER_CACHE_DISABLE=1`).
- **Particularidades de la PS4**: todos los tipos de caché de Mesa mapean compartido un archivo índice y antes le dan tamaño con `posix_fallocate`. En la PS4 un error de asignación pasa a `ftruncate`, y un mapeo compartido fallido a uno anónimo ([parcheador de la caché en disco](../tools/vk-h0/patch-mesa-disk-cache-ps4.py)); solo el título usa la caché. Mesa también apaga su caché cuando el usuario real y el efectivo difieren. RADV registra una vez `PWCACHE radv disk_cache=on|failed|none type=… path=… max_mb=… uid=… euid=…`.
- **Costo en la primera ejecución**: los fallos compilan exactamente como antes; además, un hilo de cola en segundo plano comprime y escribe cada pipeline nuevo. En ejecuciones siguientes un acierto reemplaza la compilación por una lectura y descompresión.

Todavía no se midió nada en hardware. Una prueba útil es la misma cinemática dos veces seguidas, reiniciando el título entre ambas: la segunda ejecución debería mostrar aciertos `disk`, un `miss_ms` menor y menos `hitches_with_compile`. Si su tasa de cuadros sigue igual, la caída es el límite sostenido descrito arriba.

## 04.28: lo que mostraron las primeras ejecuciones en consola, y los cambios

Ejecuciones 0244–0246 en W303 con los cambios de 04.27 (`reports/wine-hardware-w303/physical/20261119T110411Z`), sumando las ventanas `PWPERF`:

| Ejecución | Creaciones de pipeline | Tiempo de compilación | Aciertos en disco | Fallos | De ellos, shader objects |
| --- | --- | --- | --- | --- | --- |
| 0244: Alan Wake, primera vez, y Portal 2 | 591 | 27,5 s | 4 | 576 | 306 (7,6 s) |
| 0245: Alan Wake, segunda vez | 325 | 8,1 s | 28 | 290 | 282 (6,4 s) |
| 0246: Doom 3 | 119 | 3,4 s | 15 | 97 | 37 (1,3 s) |

- **La caché funciona para los pipelines.** Las bibliotecas de pipeline bajaron de 213 creaciones y 16,3 s en 0244 a 7 y 45 ms en 0245.
- **La caché no estaba donde la puso el lanzador.** Mesa lee `MESA_SHADER_CACHE_DIR` y `XDG_CACHE_HOME` con `secure_getenv`. En el ELF del título la libc de OpenOrbis tiene activado su indicador de modo seguro, así que esa función devuelve NULL para cualquier nombre. RADV recurrió entonces a `$HOME/.cache` (`/data/wine-home/.cache/mesa_shader_cache_db`). Los dos dispositivos RADV creados antes de que Wine fije `HOME` (el del sink y la sonda Vulkan del lanzador) no tuvieron caché (`PWCACHE … disk_cache=failed`). Uno de ellos es el dispositivo del sink, así que los pipelines de cómputo de la generación de cuadros (~1,4 s) se compilan de nuevo en cada arranque. En la PS4 esas búsquedas usan ahora `getenv`: un título no tiene un límite setuid que proteger.
- **La mayoría de los fallos restantes son shader objects.** RADV guarda pipelines, pero compila cada shader de `VK_EXT_shader_object` en cada `vkCreateShadersEXT`. Zink usa shader objects sobre RADV, y la caché en disco propia de Zink no puede existir en una compilación para Windows. RADV ahora también guarda los shader objects SPIR-V no enlazados en la misma caché en disco. La clave cubre la información de creación (código, punto de entrada, etapas, indicadores, especialización, rangos de push constants, hashes de los layouts de conjuntos, tamaño de subgrupo requerido) y el hash de caché del dispositivo de RADV. Un acierto se crea desde el blob guardado de `vkGetShaderBinaryDataEXT`, y una entrada obsoleta vuelve a compilarse. Los shaders enlazados, las informaciones de creación con otras estructuras `pNext` y los dispositivos para los que RADV no usaría caché compilan como antes. Los aciertos cuentan como `cached`/`disk` en `PWPERF` ([parcheador de la caché de shader objects](../tools/vk-h0/patch-mesa-shader-object-cache.py)).

### Qué limita la tasa de cuadros en Alan Wake

En la ejecución 0245 el menú mantiene 30 fps (`frames=150`, `held=150`). Las ventanas de juego muestran 55–85 cuadros cada 5 s (11–17 fps), todos de más de 50 ms y sin compilaciones. En esas mismas ventanas `gpu_busy_pct` está entre 15 y 23, el proceso usa ~2,8 núcleos (`cpu_cores_x10≈28`) y el hilo que presenta un 3–4%. Por lo tanto la GPU no es el límite. El hilo que presenta es el hilo de envío de Zink, no el del juego, así que su cifra baja no descarta la CPU.

Alan Wake es un programa de 32 bits en el mundo de 32 bits de explorer (`wow64native`, sin traductor), con Zink como DLL de 32 bits. Cada llamada Vulkan de Zink es un cruce propio de 32 a 64 bits con dos cambios de FS. W165 midió ese costo en ~18% del hilo de wined3d a ~80.000 llamadas por segundo, y el agrupamiento de llamadas de W167 (`PW_VK_BATCH=1`) lo redujo, pero solo en el relanzamiento: el mundo nunca lo tuvo ([investigación de WoW64](investigacion-wow64-en-explorer-es.md)). El límite probable es un hilo saturado de CPU, el del juego o uno de Zink, más pesado por los cruces. Todavía no está demostrado. Dos marcadores opcionales en `C:\orbis` (los lee `native/wine_hardware.c` al arrancar; el registro dice `wow64world vk_batch=… native_profile=…`) permiten comprobarlo en una ejecución:

- `nativeprofile.txt` activa el perfil por hilo de wow64native (`PW_NATIVE_PROFILE version=2` cada ~2 s por hilo de 32 bits: llamadas Unix, syscalls y tiempo en cambios de FS). El hilo más ocupado, y qué parte de él son cruces, dice si el agrupamiento puede ayudar.
- `vkbatch32.txt` activa el agrupamiento de llamadas Vulkan de 32 bits en el mundo. Solo se probó en el relanzamiento (W167–W169), nunca junto a los invitados de 64 bits de explorer. Hay que comparar `PWPERF frames` en la misma escena con y sin él.

## 04.30: lo que mostró el perfil por hilo

Ejecuciones 0252 (solo el perfil) y 0253 (perfil y agrupamiento de llamadas Vulkan de 32 bits) en 04.29 (`reports/wine-hardware-w303/physical/20261119T144942Z`). Las proporciones son del tiempo real de cada hilo, entre líneas `PW_NATIVE_PROFILE version=2` consecutivas: *invitado* es código de 32 bits, *unix* son llamadas Unix (entre ellas las de Vulkan) y *sys* son llamadas al sistema, esperas incluidas. Son ventanas de juego típicas de 0252 (55–85 cuadros cada 5 s):

| Hilo | Lo creó | Invitado | Unix | Sys |
| --- | --- | --- | --- | --- |
| 0074, hilo principal del juego | el programa | 70–85% | 0% | 15–30% |
| 00e4, hilo del driver de Zink | `libgallium_wgl.dll` | 50–60% | 22–25% | 15–25% |
| 00a8, flujo de comandos de wined3d | `wined3d.dll` | ~40% | ~10% | ~50% |
| 0084, hilo de envío y presentación de Zink | `libgallium_wgl.dll` | 1% | 3% | 95% (esperando) |

- Alan Wake se dibuja a través de cuatro capas en su proceso: Direct3D 9 → wined3d (renderizador OpenGL) → Mesa WGL/Zink → Vulkan (RADV). Está en wined3d + OpenGL porque su elección de Render en el overlay es `wined3d-gl`; con DXVK perdió el dispositivo tras 5 cuadros en 04.08 (`reports/pop-phase-b/physical/20261116T211401Z/run-0165.log`).
- Ninguna etapa llega al 100%. El hilo del juego es el que más se acerca. El juego, el hilo de wined3d y el de Zink trabajan cada uno parcialmente ocupados y pasan el trabajo al siguiente. La tasa de cuadros la fija esa cadena en serie sobre núcleos Jaguar. La GPU (8–20% ocupada) no es el límite.
- Las llamadas Vulkan son ~25% de una de las tres etapas. Por eso el agrupamiento (ejecución 0253: misma tasa de cuadros, sin `PW_VK_BATCH fatal`) no cambió nada visible.
- La próxima mejora real es quitar capas: ejecutar el juego con DXVK (Direct3D 9 → Vulkan, sin el hilo de wined3d ni Zink) una vez entendida su pérdida de dispositivo, o con el renderizador Vulkan de wined3d. Ninguna de las dos está medida en la compilación actual.
- El perfil se cronometró con una medición de 20 ms (3,43 GHz), cuando el TSC va a ~1,6 GHz. Las proporciones de arriba son correctas, pero las tasas y segundos de las líneas estaban desviados unas 2 veces. Desde 04.30, `nativeprofile.txt` también pasa la frecuencia de TSC del kernel (`PW_QPC_TSC_HZ`, como hacían W160–W177).

## 04.32: la caché reiniciaba la consola con GTA San Andreas

En 04.31, abrir GTA San Andreas (32 bits, DXVK) reinició la consola entera dos veces (`reports/wine-hardware-w303/physical/20261119T175955Z`, ejecuciones 0263 y 0264). Las dos veces ocurrió durante el primer trabajo Vulkan del juego, antes de su primer cuadro. Con `/data/orbisdesk/shader-cache.off` se juega (`20261119T181659Z`, ejecución 0266).

**Causa.** RADV y ACO arman la mitad alta de cada puntero a conjuntos de descriptores, push constants y anillos a partir de una constante: el `address32_hi` del dispositivo. En upstream ese valor es fijo para cada GPU, así que la identidad de caché de RADV no lo incluye. Crema reserva una ventana nueva de 4 GiB para cada dispositivo que abre, donde el kernel encuentre lugar (`ac_drm_device_initialize`), y deriva `address32_hi` de esa ventana. Su valor depende de lo que el proceso abrió antes. Los shaders propios de RADV para borrar y copiar y los pipelines internos de DXVK son iguales para todos los programas. Así, el dispositivo de GTA San Andreas, creado después de los dispositivos de prueba de wined3d, cargó entradas que otro dispositivo había compilado para otra ventana. Sus shaders accedieron entonces a memoria fuera de su propia ventana.

**Corrección** ([parcheador de la ventana de caché](../tools/vk-h0/patch-mesa-cache-va32.py)). En la PS4, `address32_hi` forma parte del UUID de caché de RADV. Ese UUID identifica la caché en disco (la principal y la de shaders internos), los datos de `VkPipelineCache` y los binarios de shaders, así que un acierto solo puede venir de un dispositivo con la misma ventana. Cada dispositivo registra `PWCACHE radv address32_hi=…`. Las ejecuciones que repiten la misma secuencia, como abrir el mismo juego tras los mismos pasos, obtienen la misma ventana y conservan sus aciertos. El UUID nuevo deja inalcanzables todas las entradas viejas.

Una mejora posterior sería una sola ventana de 32 bits por proceso, compartida por todos los dispositivos. Así los aciertos no dependerían del orden en que se abren los dispositivos. Es un cambio en las ventanas de direcciones de Crema y no forma parte de esta corrección.

## 04.33: el agrupamiento de llamadas Vulkan de 32 bits nunca funcionó en el mundo de explorer

El perfil de 04.30, recalculado con la frecuencia de TSC de la consola (1,594 GHz), pone cifras a las tres etapas del cuadro de Alan Wake durante el juego:

| Hilo | Código de 32 bits | Llamadas al lado de 64 bits | Syscalls |
| --- | --- | --- | --- |
| Juego | 57–83% | ~100/s | 13.000–41.000/s de ~12 µs cada una, 17–43% del tiempo |
| Driver de Zink | 55–58% | ~228.000/s de ~1,1 µs cada una, ~25% del tiempo | ~220/s esperas de ~1 ms |
| Flujo de comandos de wined3d | ~40% | ~6.000/s de ~18 µs | ~360/s esperas de ~1,3 ms |

La proporción de syscalls del hilo del juego sube justo cuando baja la de su propio código. El hilo gira en llamadas al sistema cortas mientras espera al resto de la cadena, así que la cadena también fija la tasa de cuadros. Un cuarto del hilo de Zink se va en cruces al lado de 64 bits, uno por llamada Vulkan.

La ejecución 0253 activó el agrupamiento (`vkbatch32.txt`), y el hilo de Zink siguió haciendo ~225.000 cruces por segundo. El agrupamiento nunca se activó. En el mundo de explorer, todo programa de 32 bits llega a winevulkan a través del cargador de Khronos con la capa implícita de MangoHud, y el cargador pasa la información de creación del programa con sus propios enlaces `VK_STRUCTURE_TYPE_LOADER_INSTANCE_CREATE_INFO` todavía en `pNext`. La protección del agrupamiento considera inseguro cualquier `pNext` de instancia, así que lo apagó para todo el proceso en el primer `vkCreateInstance`. El relanzamiento de W167 no tenía cargador ni capa en el proceso de 32 bits; por eso el agrupamiento solo funcionó allí.

`tools/build-winevulkan-batch.py` ahora hace que la protección acepte una cadena formada solo por los enlaces del cargador. Cualquier otra estructura, como mensajeros de depuración o funciones de validación, sigue apagando el agrupamiento. El marcador sigue siendo opcional hasta que una ejecución en consola muestre la mejora y una salida limpia.

**A quién afecta.** A todo programa de 32 bits del mundo que use Vulkan:
- Alan Wake: wined3d sobre Zink, la elección `wined3d-gl` del overlay.
- Doom 3: OpenGL directo a Zink.
- GTA San Andreas, PES 2013, PES 2014, Portal 2 y GTA IV: DXVK.

Los programas de 64 bits mantienen las llamadas normales de Wine (el agrupamiento es solo de 32 bits).

## 04.34: el agrupamiento se activó, y el hilo del juego de Alan Wake es el límite

En 04.33 (`reports/wine-hardware-w303/physical/20261119T200114Z`), la ejecución 0274 jugó Alan Wake sin agrupamiento y la 0275 con él. Las dos tienen dos fases. En los primeros ~65 s, el límite de 30 FPS del overlay retiene cada presentación ~29 ms (`PWFPS … held_us_avg=29000`), así que el límite fija la tasa. Después, en el juego, no se retiene nada y el juego va a 8–19 fps. El promedio de una ejecución mezcla las dos fases, así que no dice nada sobre el agrupamiento.

Solo el juego, según el perfil por hilo:

| Hilo | Sin agrupamiento (0274) | Con agrupamiento (0275) |
| --- | --- | --- |
| Driver de Zink: llamadas Unix por segundo | 192.680 | 80.960 |
| Driver de Zink: cambio de FS | 33% | 15% |
| Driver de Zink: esperando en syscalls | 30% | 31% |
| Juego: código propio de 32 bits | 67% | 78% |
| Juego: syscalls por segundo | 20.100 | 16.200 |
| Cuadros cada 5 s | 42–85 (media 65) | 46–95 (media 70) |

El agrupamiento funcionó: los cruces de Zink bajaron un 58%. El hilo de Zink ya esperaba ~30% del tiempo sin él, así que no era lo que frenaba la tasa de cuadros. Con el agrupamiento, el hilo del juego espera menos y pasa el 78% del tiempo en su propio código. Lo que ayude ahora tiene que quitarle trabajo a ese hilo. Los cuadros del juego subieron ~7%, pero las dos ejecuciones jugaron tramos distintos, así que está dentro del ruido.

GTA San Andreas en la ejecución 0275 mantiene 124–125 cuadros cada 5 s al jugar, igual que en la 0266 sin agrupamiento: 25 fps, el Frame Limiter del propio juego. Su hilo principal hace ~64.000 syscalls por segundo esperando a ese limitador. Hay que desactivar Frame Limiter en las opciones de pantalla del juego antes de que cualquier cambio se note ahí.

`tools/build-winevulkan-batch.py` añade ahora tres líneas de registro al agrupamiento, cada una como mucho una vez por proceso:
- `PW_VK_BATCH on=1` cuando un proceso inicia el agrupamiento;
- `PW_VK_BATCH off from the start` cuando se pidió `PW_VK_BATCH=1` pero el entorno de capas o la máscara de opcodes lo mantienen apagado;
- `PW_VK_BATCH off for the rest of the process: unix call N (nombre)` cuando una llamada lo apaga.

## 04.35: la pérdida del dispositivo con DXVK era un envío vacío, no un fallo de la GPU

Alan Wake con DXVK (04.08, ejecución 0165; 04.33, ejecuciones 0276 y 0277), Left 4 Dead 2 (ejecución 0266) y POP (ejecución 0115) terminaron todos igual, a los pocos cuadros o más tarde:

```text
radv/amdgpu: Failed to query the last GPUVM fault (-22).
err:   DxvkSubmissionQueue: Command submission failed: VK_ERROR_DEVICE_LOST
```

**Qué significan las líneas.**
- RADV imprime la primera línea solo cuando un `vkQueueSubmit` devuelve un error, antes de marcar el dispositivo como perdido. El `-22` es la respuesta de Crema a toda consulta de fallos GPUVM: la PS4 no tiene ninguna (`ac_drm_query_gpuvm_fault_info` devuelve `-EINVAL`). La línea no dice nada sobre un fallo.
- No hubo línea `GPU hang?` ni `gpu-fault.txt`, así que la GPU no se había detenido.
- En Crema, todo paso fallido de un envío con búferes de comandos imprime una línea `radv: … -> fail`. No apareció ninguna.

**Causa.** El envío que falló no tenía búferes de comandos. RADV manda un envío con solo semáforos a `radv_amdgpu_cs_submit_zero`, que une los semáforos que espera al syncobj de la cola mediante sync files. Crema no tiene sync files, así que esas llamadas devuelven `-ENOSYS`. Esa función devuelve entonces `VK_ERROR_DEVICE_LOST` sin ninguna línea, salvo para un punto de timeline que la GPU ya había terminado.
- Un semáforo binario perdía siempre el dispositivo.
- Un semáforo timeline lo perdía cuando la GPU seguía con ese punto. Esa carrera explica por qué ocurría a los pocos cuadros, o solo cuando los cuadros tardaban más (menús, overlay, cambios de modo).

**Corrección** ([parcheador del envío vacío](../tools/vk-h0/patch-mesa-empty-submit.py)). En la PS4, un envío vacío espera en la CPU hasta que sus semáforos se hayan señalado, como ya hace el envío de enlazado disperso de RADV. Después señala sus propios semáforos desde el último envío de la cola, lo que Crema admite. El runtime de Vulkan llama al driver solo cuando todas las esperas ya se enviaron, y la única cola de GPU de la PS4 ejecuta los envíos en orden, así que la espera siempre termina. Todo envío que aún falle imprime ahora `radv: vkQueueSubmit = <resultado>: N búferes de comandos, N esperas, N señales`.

## 04.35: batching de Vulkan de 32 bits activado por defecto

Desde la 04.35, el batching de las llamadas Vulkan de 32 bits está activado por defecto en el mundo de Explorer (04.33, run-0275: las llamadas de zink bajaron 58% en Alan Wake, y Alan Wake y GTA SA se jugaron y cerraron bien). La mejora de FPS en Alan Wake es chica, porque el límite es el propio hilo del juego. Para apagarlo, crear `C:\orbiskbatch32.off` y reiniciar OrbisDesk; `vkbatch32.txt` ya no se lee.
