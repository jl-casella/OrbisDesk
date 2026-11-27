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

Desde la 04.35, el batching de las llamadas Vulkan de 32 bits está activado por defecto en el mundo de Explorer (04.33, run-0275: las llamadas de zink bajaron 58% en Alan Wake, y Alan Wake y GTA SA se jugaron y cerraron bien). La mejora de FPS en Alan Wake es chica, porque el límite es el propio hilo del juego. Para apagarlo, crear `C:\orbis\vkbatch32.off` y reiniciar OrbisDesk; `vkbatch32.txt` ya no se lee.

## Envíos vacíos asíncronos experimentales (04.47 local)

El [parcheador asíncrono](../tools/vk-h0/patch-mesa-async-empty-submit.py), aplicado después de la corrección 04.35, reemplaza la espera CPU a la finalización de GPU en colas GFX PS4 compatibles por un envío normal del command stream inmutable de limpieza de caché, ya finalizado y propiedad de esa cola. Conserva todos los semáforos de espera y señalización en la ruta normal del winsys. Crema ordena ese envío después de sus prerrequisitos enviados en la cola de hardware; la CPU puede continuar sin esperar que la GPU los termine. No se descarta ningún semáforo ni se lo señala antes de tiempo. Otras colas o aquellas sin ese command stream conservan la alternativa CPU; los errores se propagan sin reintentar un envío aceptado.

El objetivo es reducir serialización innecesaria entre CPU/GPU y podría mejorar los FPS reales donde esas esperas sean importantes. No es una ganancia medida ni una aceptación en hardware. La [prueba de host](../tests/test_async_empty_submit_host.py) compila la función transformada del archivo Mesa fijado y comprueba dependencias binarias/timeline, señales diferidas, alternativa CPU y errores. No ejecuta el driver ni la GPU PS4.

La [prueba de diagnósticos en host](../tests/test_perf_diagnostics_host.py) también compila el runtime nativo y verifica que los resúmenes funcionen con `pw_trace_level=0`, incluyendo tiempos acumulados y fallos.

Para comparar A/B, crear `/data/orbisdesk/perf-empty-submit-cpu.txt` antes de abrir OrbisDesk restaura la ruta CPU; quitarlo y reiniciar activa la asíncrona. El lanzador registra `PWPERF config ... empty_submit=cpu-control|async-gfx`. Comparar el mismo save/escena con caché caliente, mismo renderer, resolución, límite y FG. El cambio de identidad de Mesa inicia una caché nueva: no comparar el primer arranque frío contra una corrida vieja caliente.

`tools/build-wine-hardware.py --performance-diagnostics` activa resúmenes nativos acotados independientemente de `trace.txt`, sin activar los canales verbosos de Wine ni volcados de cuadros. `PWPERF`, `PWFPS`, `PWFG` periódico y `PWVK present` informan tiempos de cuadro, compilación, cadencia, decisiones de generación, tiempo GPU del generador y espera de copia WSI. `PWPERF` agrega intervalos de al menos 34 y 250 ms. `PWQUEUE` informa aproximadamente cada cinco segundos de envíos vacíos: cantidades por ruta asíncrona/CPU, duración total y máxima en host, esperas y fallos. Los tiempos de distintos hilos pueden solaparse; no son tiempo de ejecución GPU. Una cola sin actividad puede no emitir su última ventana parcial. La opción y hash del parche quedan en el manifiesto. Un paquete con `--runtime-outside-package` depende de un runtime compatible ya instalado en `/data`; no sirve como instalación limpia.

## 04.48 local: perfil de hilos y contadores completos de cola

Esta candidata diagnóstica conserva la política de envíos de 04.47. Con `--performance-diagnostics` también activa el perfilador WoW64 existente en el mundo de 32 bits de Explorer y pasa la frecuencia de TSC del kernel. Cada reporte acumulado `PW_NATIVE_PROFILE version=2` viene acompañado de `PWTHREADPERF`: IDs de hilo Wine/nativo, instante de pared, tiempo CPU de usuario/kernel por hilo, contadores de I/O en bloques, cambios de contexto voluntarios/involuntarios y fallos de página. El hook corre en ese hilo con FS de host activo. Se instala mediante un puntero interno, sin dejar una importación de callback sin resolver en el ELF diagnóstico base de Wine.

Comparar dos reportes del mismo hilo: delta de tiempo CPU dividido por delta de pared estima su ocupación CPU. El resto incluye bloqueos y tiempo sin ser planificado, no solo esperas. Correlacionarlo con las categorías de tiempo de pared invitado/Unix/syscalls de WoW64 y las ventanas de cuadros; estos datos no son un muestreo de stacks. Los bloques de I/O no son bytes ni cubren todo acceso en caché; cero no prueba ausencia de I/O. Si falla `getrusage`, se emite `cpu_available=0` en lugar de inventar contadores. Un hilo dormido reporta cuando vuelve a un límite de instrumentación. Cubre hilos WoW64, no todos los workers nativos/de 64 bits.

`PWQUEUE` ahora registra el primer uso inmediatamente, mantiene totales de toda la sesión y vacía cada cinco segundos desde un monitor nativo, incluidos intervalos con cero usos. Los cambios de programa y salidas de proceso también vacían ventanas parciales. Resuelve la ambigüedad de 04.47: una ráfaga corta seguida de silencio podía no producir reportes. El usuario notó más respuesta en 04.47, con caídas restantes; no quedó demostrada una ganancia controlada de FPS ni un uso significativo de la ruta asíncrona. La instrumentación agrega costo: comparar corridas con la misma instrumentación antes de elegir otra optimización.
## Local 04.49: alertas entre hilos del mismo proceso

Este candidato experimental reemplaza el viaje al servidor de `NtAlertThreadByThreadId` y `NtWaitForAlertByThreadId` por un evento del kernel de PS4. Un bit agrupa las alertas pendientes y una espera atómica OR/CLEAR_PAT lo consume. Conserva las alertas anteriores a la espera, el consumo con timeout cero, las esperas finitas e infinitas y los reintentos por interrupción. Las esperas finitas largas usan tramos acotados en microsegundos y mantienen el plazo original. Los demás objetos de sincronización de Windows y los handles entre procesos conservan sus rutas existentes.

Wine usa estas alertas detrás de `RtlWaitOnAddress`/`RtlWakeAddress*`, incluso para locks SRW con contención y variables de condición. El cambio apunta a las esperas y señales entre los hilos de la aplicación y de gráficos; las rutas sin contención que ya trabajan en espacio de usuario conservan su comportamiento. La frecuencia con la que un juego llega a esta ruta debe medirse, sin inferirla del total de tiempo en syscalls.

El [overlay canónico](../tools/wine_thread_alert.py) incluye la [implementación nativa](../platform/ps4/pw_wine_thread_alert.inc.c) en `sync.c` de Wine Unix. Los inicializadores concurrentes publican un único backend por entrada y eliminan los objetos del kernel sobrantes. Si falla la creación, esa entrada conserva permanentemente el evento auto-reset original de Wine; un error al señalar o esperar sigue siendo un error. Como en la tabla original de Wine, las entradas persisten durante la vida del proceso. Si se agotan los recursos más tarde, se usa el servidor sin fingir la creación de un evento.

Creá `/data/orbisdesk/perf-thread-alert-server.txt` y reiniciá OrbisDesk para comparar con la ruta original del servidor. Borrá el archivo y reiniciá para usar la ruta del kernel. El launcher registra `PWALERT config backend=kernel-event|server-control`. Con los diagnósticos de rendimiento, cada reporte de un hilo WoW64 incluye `PWALERTPERF` con contadores acumulados de señales y esperas nativas o de fallback, timeouts, errores, ticks TSC totales de espera y máximo. Usá las diferencias de contadores y la frecuencia TSC medida; el tiempo transcurrido incluye bloqueos y planificación, además del costo de ejecución. Los hilos nativos de 64 bits no adquieren un reporte periódico WoW64 por usar estas funciones.

La [prueba de host](../tests/test_thread_alert_host.py) compila las funciones Wine realmente transformadas contra un modelo de evento del kernel. Verifica alertas pendientes y agrupadas, un hilo bloqueado, 4096 intercambios entre dos hilos, plazos cero/finitos/infinitos, tramos de timeout largos, interrupciones, errores, fallback al servidor original, 16 inicializadores simultáneos y el límite de la tabla, con sanitización de comportamiento indefinido. No valida la implementación de eventos de la PS4 física. El código y la prueba de host no establecen una mejora de FPS reales; hay que correlacionar el uso de alertas, los cambios de contexto y los intervalos entre cuadros en corridas de hardware equivalentes.

## Local 04.50: tareas auxiliares de Vulkan y preparación de FG

El [overlay de batching](../tools/wine_vk_batch_hotpath.py) evita bloquear la lista de productores cuando ya se consumió el prefijo de tickets aceptado, evita buscar productores para liberar cuando ninguno se retiró y evita bloquear los metadatos de plantillas de descriptores en llamadas ajenas a ellas. Los tickets reservados aún no publicados siguen esperando y los streams retirados con datos pendientes siguen vivos. Los comandos, codecs, orden y llamadas síncronas al driver mantienen su comportamiento. El contador de retiros se publica antes que la marca de retiro: una carrera puede demorar la liberación, pero no liberar un nodo activo. La [prueba de host](../tests/test_vk_batch_hotpath_host.py) compila las funciones transformadas con el SPSC y framing originales, incluyendo productores intercalados, huecos de publicación y retiros pendientes.

Las builds de rendimiento activan los contadores existentes de batching y fallback Vulkan. Los resúmenes normales de batching y present ahora se escriben en la primera muestra y cada 300 presents, en vez de cada cuadro. El reporte de fallback nombra las ocho API sin agrupar más frecuentes. `PW_VK_FASTPATH` cuenta las tareas auxiliares evitadas. Estos diagnósticos permiten identificar los cruces restantes; eliminar tareas auxiliares no elimina por sí mismo las llamadas Unix necesarias.

Cuando algún programa guardado tiene FG habilitado, el arranque prepara sus cuatro pipelines compute y ejecuta las comprobaciones existentes de ISA y fences antes de iniciar Wine, serializado con el presentador de la pantalla de carga. Respeta los overrides off/timing de `framegen.txt`. El primer cuadro fuente reutiliza la inicialización y comienza igualmente con el historial de imágenes vacío. La [prueba de host](../tests/test_framegen_prepare_host.py) cubre reutilización, cierre por fallo, perfiles guardados, overrides y contabilidad del arranque. `/data/orbisdesk/perf-fg-prewarm.off` restaura la preparación en el primer uso para comparar. `PWFG prepare` registra el tiempo de preparación y la compilación inicial tiene un reporte de rendimiento separado. La captura de IR y la inspección FLAT siguen siendo necesarias: se mueve la compilación fuera de la jugabilidad sin fingir un acierto de caché de FG. Los diagnósticos de rendimiento habilitan reportes periódicos `PWFG shown_rate`: los generados requieren flips completados y el contador de reales sigue las entregas de cuadros fuente observadas.

El PKG chico necesita la **winevulkan.dll de 32 bits** actualizada en ambas ubicaciones del runtime; subir solo ese PKG deja sin aplicar la optimización PE. Se debe conservar el runtime instalado y actualizar únicamente esas dos copias verificadas. Este candidato no agrega interpolación adaptable ni cambia el planificador 30→60. La aceptación visual y de rendimiento en hardware sigue pendiente.

## Local 04.51: caché síncrona de descriptores

El log de hardware 04.50 `run-0006` atribuyó 11.499.129 de 11.752.506 fallbacks síncronos (97,84 %) a `vkGetDescriptorEXT`. Esto identifica el volumen de llamadas, no un costo medido por llamada ni una ganancia de FPS garantizada. La candidata 04.51 agrega una caché acotada en cada productor PE32, cuya clave incluye dispositivo, tipo, tamaño y valores del descriptor. Los aciertos copian el descriptor antes de que retorne la API, incluso para destinos que lee la CPU. No se difiere ninguna escritura. Los tipos desconocidos, cadenas de extensiones, salidas demasiado grandes y entradas superpuestas conservan la ruta original.

Ante un fallo de caché, una operación privada negociada ejecuta dos consultas reales al driver con bytes iniciales distintos, después de reproducir una sola vez el prefijo aceptado. Los bytes iguales identifican escrituras del driver; los huecos intactos conservan los bytes originales de cada llamador. Otras diferencias desactivan la caché. La destrucción de recursos, liberación o revinculación de memoria y vinculación sparse avanzan una generación global antes de la operación. Los primeros 16 aciertos por productor y cada acierto número 4096 posterior se auditan contra resultados nuevos del driver; una diferencia desactiva la caché y devuelve el resultado recién consultado. Cada productor tiene 1024 conjuntos de dos entradas, locales al proceso y liberados junto al productor.

El [overlay con comprobación de contexto](../tools/wine_vk_descriptor_cache.py), el [núcleo de caché](../platform/ps4/pw_vk_descriptor_cache.h) y el [adaptador PE](../platform/ps4/pw_vk_descriptor_cache_pe.inc.c) conservan los formatos batch v1/v2. Un runtime nativo anterior no anuncia la capacidad privada y la DLL actualizada usa su ruta síncrona previa. El backend nativo async queda excluido de esta optimización. `/data/orbisdesk/perf-descriptor-cache.off` desactiva la caché en el siguiente arranque. `PW_DESCRIPTOR_CACHE` y `PW_DESCRIPTOR_TYPES` registran el uso acumulado junto a los reportes periódicos del batch. La [prueba de host](../tests/test_descriptor_cache_host.py) comprueba salida síncrona, relleno, claves, colisiones, generaciones de recursos, desactivación por auditoría, fallback y validación nativa del paquete bajo ASan/UBSan. La tasa de aciertos física, el rendimiento y la aceptación visual siguen pendientes. La política de caché de shaders y el planificador FG conservan el comportamiento de 04.50. La entrega requiere el PKG chico y ambas DLL winevulkan de 32 bits correspondientes; el helper nativo de procesos separados no forma parte de esta prueba de rendimiento en el título principal.

## Local 04.52: política de compilación y confirmación de salida nativa

La corrida física 04.51 `run-0007` ejercitó el caché de descriptores: 68,7 % de aciertos al present 3000, 3041 auditorías y ningún rechazo. Registró 29,18 FPS de presents fuente durante 110,339 segundos, frente a 23,29 durante 90,365 segundos en 04.50; los cuadros de más de 50 ms fueron 0,65 % frente a 22,09 %. Son corridas sin control de entradas, duración ni calentamiento adicional del caché, no una medición causal aislada. La admisión de pares FG pasó de 55,6 % a 93,8 %; los flips generados y las entregas fuente siguen siendo contadores distintos. La peor ventana de cinco segundos todavía incluyó 359 creaciones de pipelines y 804 ms de trabajo de compilación agregado.

La candidata 04.52 solicita una sección de `DXVK_CONFIG` específica para `alan_wakes_american_nightmare.exe`: `dxvk.enableGraphicsPipelineLibrary=True` y `dxvk.numCompilerThreads=2`. Según la [configuración de DXVK 2.7.1](https://github.com/doitsujin/dxvk/blob/v2.7.1/dxvk.conf), True conserva las bibliotecas de pipelines pero desactiva la compilación de pipelines optimizados, y el otro ajuste limita los trabajadores compiladores. Se cambia posible optimización de GPU por menor competencia de CPU; los shaders nuevos necesarios siguen compilándose, por lo que no se afirma eliminar todos los tirones de compilación. Otros nombres de ejecutable no reciben estas opciones. La configuración explícita del entorno de proceso o de lanzamiento tiene prioridad; esta sección experimental sí reemplaza las opciones correspondientes de un `dxvk.conf` local del juego. `/data/orbisdesk/perf-aw-pipelines.off` restaura la política original en el siguiente arranque. La [prueba de host](../tests/test_aw_pipeline_profile_host.py) ejecuta el parser original, fijado por hash, contra el perfil del launcher y nombres ajenos. La identidad del caché RADV y el planificador FG no cambian: 04.51 midió unos 2 ms de GPU para FG y ninguna desactivación por presupuesto, por lo que esta candidata apunta a la cadencia fuente.

La misma corrida expuso otro fallo en el cierre: el servidor marcó los hilos del invitado como terminados mientras rechazaba SIGQUIT y descargó DLL antes de que esos hilos nativos se detuvieran. Ahora usa el mapeo existente hacia un pthread concreto para SIGQUIT solo cuando está instalado el handler raw actual de Wine. No recurre a una señal para todo el proceso. Las secciones críticas del registro bloquean SIGQUIT para evitar que el propietario terminado bloquee su destructor de salida. Una extensión privada de ThreadTimes, identificada con una marca, confirma el límite de salida nativa de Wine, con tokens de generación para distinguir identificadores reutilizados. Los llamadores habituales de ThreadTimes y las tablas de syscalls WoW64 conservan su interfaz. Antes de descargar código o recursos del invitado, kernelbase espera esta confirmación de los hilos registrados. Si la ejecución no se conoce, no se soporta la consulta o sigue activa, conserva los mapeos y registra el motivo sin informar una descarga exitosa. Se mantienen el período de gracia de WM_CLOSE y el fallback de cierre forzado; este cambio no afirma resolver el cierre cooperativo del juego.

El [overlay nativo](../tools/wine_guest_quiesce.py), la [estructura del protocolo](../platform/ps4/pw_thread_quiesce.h) y la [protección del invitado](../platform/ps4/pw_guest_quiesce.inc.c) son entradas canónicas del build. La [prueba de host](../tests/test_guest_quiesce_host.py) ejercita el registro nativo real, la diferencia entre finalización nativa y del servidor, reutilización de IDs, ThreadTimes habitual y extendido, y rechazo de descarga con backends anteriores, desconocidos o fallidos, bajo ASan/UBSan. Siguen pendientes la entrega de señales en hardware, el cierre, la reapertura de juegos y el rendimiento. El PKG chico requiere el conjunto de DLL guest correspondiente y respaldo de los archivos anteriores de la consola; subir solo el PKG no instala la protección nueva.
## Local 04.53: hilos de compilación opcionales

El perfil combinado de pipelines de 04.52 produjo tonos verdes y magenta en el juego en la PS4 Pro Baikal (12.50). Desactivarlo restauró los colores normales manteniendo activa la caché de descriptores. Esto identifica el perfil combinado, no una opción individual de DXVK. Las corridas físicas también registraron confirmación de salida nativa antes de descargar el huésped y ciclos de reapertura satisfactorios. El cierre cooperativo y la compatibilidad general siguen sin demostrarse.

04.53 elimina el perfil fijo. GRÁFICOS coloca **HILOS DE COMPILACIÓN** inmediatamente debajo de **RENDERIZADO**, con **AUTO / 2 HILOS**. Auto es el valor inicial y respeta la configuración existente de DXVK. La opción experimental de dos hilos genera únicamente `dxvk.numCompilerThreads=2`; nunca cambia la política de bibliotecas de pipelines gráficos. La ayuda y la notificación explican que, como Renderizado, se aplica al volver a abrir el juego. No es un ajuste en vivo ni garantiza más FPS, y no afecta a WineD3D ni a otros renderizadores ajenos a DXVK.

El overlay guarda atómicamente `compiler.<nombre base del ejecutable>=2` en `C:\orbis\overlay.ini`; Auto elimina esa sobreescritura. Las secciones por ejecutable coexisten sin aplicar el límite de un juego a otro. El arranque del huésped actualiza el entorno antes de inicializar las DLL del juego, en ambas arquitecturas PE; el auxiliar nativo de proceso separado lee el mismo archivo antes de iniciar Wine. El PKG chico requiere el auxiliar y las DLL correspondientes. Se conservan los demás ajustes por juego y la identidad de la caché de shaders. La preparación, admisión y presentación de FG conservan la implementación anterior.

Las [pruebas del parser](../tests/test_aw_pipeline_profile_host.py) usan el parser original fijado de DXVK; las [del overlay](../tests/test_compiler_overlay_host.py) cubren persistencia, otros ajustes, Auto y errores del guardado atómico; las [del huésped](../tests/test_compiler_guest_host.py) ejercitan la actualización al próximo arranque, la pertenencia de las asignaciones y errores de lectura o memoria. Estos modelos de host y una compilación correcta no demuestran rendimiento ni aceptación física de procesos separados en 04.53. Comparar Auto y dos hilos en el mismo tramo tras reabrir el juego, comprobando colores, intervalos de cuadros y cierre/reapertura posterior.

### Seguimiento sin publicar: diagnóstico de excepciones

La traza existente de las primeras ocho excepciones de huéspedes incorpora ahora los registros generales originales, hasta dieciséis bytes de instrucciones y ocho palabras de pila mediante el auxiliar existente de lectura segura. La memoria ilegible se informa explícitamente. Se conservan el contexto de la excepción y el resultado del manejador. Las [pruebas en host](../tests/test_guest_fault_context_host.py) compilan ambas estructuras de contexto y verifican lecturas acotadas, errores de lectura y preservación del contexto. Estos diagnósticos no corrigen la compatibilidad de DXVK ni el estado compartido de DLL, y las pruebas de host no demuestran aceptación física del camino de excepciones.

## Candidata local 04.54: esperas temporizadas y correlación con cuadros

L4D2 después arrancó y presentó con DXVK/Vulkan en dos sesiones de 04.53, publicando Auto y luego dos hilos en el entorno al iniciar. La excepción anterior no se reprodujo; no se instaló una corrección nueva entre esas corridas. Las tasas de presentación base en ventanas regulares de cinco segundos fueron 25,84 y 23,97 FPS, con escenas e historia de caché diferentes. Esas muestras no aíslan el efecto de los hilos. Auto sigue siendo el valor inicial. En Auto, 44 de 55 tirones detectados se superpusieron con compilación instrumentada; es correlación, no una pila muestreada de la llamada bloqueada.

La [transformación de la espera](../tools/wine_delay_yield.py) conserva la cesión de CPU antes de un `NtDelayExecution` no alertable de duración distinta de cero, pero omite dos consultas `getrusage` por hilo cuyo resultado se descarta. Las esperas de duración cero conservan el `NtYieldExecution` original y su estado. Las esperas alertables e infinitas conservan sus caminos originales. Las [pruebas](../tests/test_delay_yield_host.py) comparan las funciones originales y transformadas en esperas cero, relativas, absolutas, vencidas, interrumpidas, alertables e infinitas. El cambio por sí solo no demuestra una ganancia de FPS.

El empaquetador ejecuta automáticamente [el constructor de operaciones](../tools/build-wine-optrace.py), con la receta Unix probada y las firmas exactas de Wine. Observa seis llamadas Unix: lectura, espera simple/múltiple, demora, cesión de CPU y consulta del contador de rendimiento. El [registrador](../platform/ps4/pw_optrace.inc.c) usa la frecuencia TSC del kernel y contadores por hilo; desactivado toma una rama sin leer el reloj. Las llamadas anidadas se cuentan solo en la operación observada exterior. Se conservan argumentos, salidas, estado y errno. Los tamaños de lectura son bytes solicitados; una lectura pendiente no se considera completada. Emite hasta tres resúmenes por hilo cada cinco segundos y ocho eventos lentos por proceso cada cinco segundos. Los tiempos incluyen bloqueo y desplanificación. Esta candidata habilita los informes en el título principal; el auxiliar separado conserva su política existente de trazas desactivadas.

Los eventos de compilación lenta renuevan su presupuesto acotado cada cinco segundos e incluyen marcas monótonas e identificadores de hilo nativo. `PWFRAME` registra intervalos base superiores a 100 ms y trabajo agregado de compilación superpuesto; ese trabajo puede abarcar varios hilos. Las ventanas `PWPERF` incluyen su marca final. Permite correlacionar eventos sin debilitar sincronización Vulkan, omitir dibujos, cambiar la identidad de caché ni modificar la planificación de FG. Las pruebas de [registro](../tests/test_optrace_host.py), [envoltorios](../tests/test_optrace_wrappers_host.py) y [cuadros](../tests/test_pipeline_frame_trace_host.py) cubren reenvío, casos pendientes/con error, preservación de errno, contabilidad anidada y límites de trazas. Quedan pendientes el rendimiento físico, la cobertura de los envoltorios y el costo de los diagnósticos en la candidata correspondiente.

### Seguimiento sin publicar: hilos efectivos y etapas de lectura

Según el usuario, las dos sesiones de L4D2 en 04.54 usaron el mismo mapa y un recorrido parecido. Publicar dos hilos o Auto no acredita cuántos se usaron: DXVK 2.7.1 captura la configuración en una instancia D3D9 compartida que OrbisDesk puede conservar tras terminar forzosamente un invitado. El overlay ahora pide reiniciar OrbisDesk después de cambiar la política, en lugar de prometer que alcanza con reabrir el juego. Los mensajes de entorno indican explícitamente que la cantidad efectiva no está verificada. Las compilaciones de rendimiento habilitan los anuncios INFO de DXVK sobre sus hilos, en el título principal y el auxiliar separado; el host de 32 bits conserva esta selección de diagnóstico. Las compilaciones normales conservan la política de advertencias/errores y no crean logs en las carpetas de los juegos. Un proceso nuevo del título evita instancias anteriores, pero otro cliente DXVK puede inicializar primero la instancia compartida; sigue siendo necesaria evidencia de los hilos efectivos. Este seguimiento no implementa una actualización de configuración por dispositivo ni reemplaza las DLL de DXVK.

La [instrumentación de lectura](../tools/wine_read_trace.py) separa búsqueda del descriptor, validación del buffer de destino, E/S y procesamiento de notificaciones dentro del `NtReadFile` Unix original. Los resúmenes `PWREAD` independientes distinguen archivo/socket/otro/desconocido, bytes solicitados, bytes conocidos de lecturas realizadas dentro de la llamada, resultados asíncronos/pendientes, eventos, APC y entrega de notificaciones al servidor. No miden ancho de banda del disco: incluyen planificación y bloqueos, y los resultados delegados conservan una cantidad de bytes desconocida sin inspeccionar un IOSB inseguro o pendiente. El presupuesto de eventos lentos pasa a ocho por operación cada cinco segundos para que las demoras de fondo no agoten la cobertura de lecturas. Se conservan estado, salidas, errno y orden de las notificaciones. Las [pruebas de contrato](../tests/test_read_trace_contract.py) comparan la función original y transformada de Wine fijada; las [pruebas de etapas](../tests/test_read_stages_host.py) verifican contabilidad y límites. No cambian claves de caché, política de descriptores ni planificación de FG. Estos cambios de código no acreditan un paquete nuevo, aceptación física ni ganancia de FPS.

### Seguimiento: retirar controles de compilación y distinguir esperas de CPU/presentación

La prueba de L4D2 en 04.55 confirmó dos compiladores efectivos, sin acreditar una ventaja de FPS sobre la referencia anterior que solicitaba Auto. Una opción guardada por juego tampoco describe de manera fiable la instancia compartida que DXVK conserva. Por eso se retiran el selector de compilación y su persistencia. Se ignoran los antiguos `compiler.*`, que desaparecen al guardar correctamente cualquier ajuste del overlay. La limpieza de arranque elimina únicamente el sufijo marcado de `DXVK_CONFIG` generado por OrbisDesk, tanto en invitados de ambas arquitecturas como en el auxiliar separado; conserva opciones explícitas del usuario, incluidos ajustes manuales de compiladores. Hay que reiniciar OrbisDesk para descartar instancias DXVK existentes. Las pruebas de [migración](../tests/test_aw_pipeline_profile_host.py), [invitado/auxiliar](../tests/test_compiler_guest_host.py) y [overlay](../tests/test_compiler_overlay_host.py) verifican limpieza, preservación ante fallos y preferencias ajenas. Las cachés de shaders permanecen habilitadas y no cambia su identidad.

En los intervalos medidos de 04.55 posteriores a los 160 segundos del proceso, el hilo principal del juego ocupaba aproximadamente el 69% de un núcleo y el de presentación, el 5%; los intervalos de dos segundos no identifican una pila bloqueada. Los próximos diagnósticos suman `NtWaitForAlertByThreadId`, `NtAlertThreadByThreadId`, activación/reinicio de eventos y consulta/espera de mensajes a los envoltorios de ABI exacta existentes. `PWPRESENT` mide por separado el tiempo fuera del callback de presentación, bloqueo/trabajo de metadatos, preparación que incluye FG, limitador y trabajo final. El tiempo exterior incluye productor, controlador y planificación; el tiempo de preparación no es ejecución GPU de FG y la espera de blit recibida puede superponerse con el intervalo exterior. No se presentan como tiempo de CPU. Las [pruebas del registrador](../tests/test_present_trace_host.py) cubren contabilidad, swapchains independientes, exclusión del registro, retroceso del reloj, errno y salida acotada. Se conservan pacing, sincronización y planificación de FG. Estos cambios preparan la atribución para la próxima build y no acreditan una mejora física de FPS.

### Alertas de hilo pendientes (candidata 04.58)

El reemplazo de sincronización para hardware agrega un bit pendiente local al proceso para las alertas de hilo. Una alerta ya encolada se consume en espacio de usuario; los eventos del kernel sólo bloquean al hilo si no hay una alerta lista. El registro de esperadores y la señalización usan operaciones atómicas secuencialmente consistentes. Los despertares del kernel se comprueban contra el bit pendiente, por lo que uno residual nunca crea una alerta NT; las señales repetidas siguen fusionándose y las esperas finitas conservan un único vencimiento durante despertares residuales e interrupciones. Los handles de eventos Windows entre procesos siguen en su ruta existente por servidor, incluido el fallback por entrada cuando el backend nativo no está disponible. Los errores del kernel siguen siendo errores.

`PWPENDINGALERT` informa esperas lógicas, casos listos inmediatos/tras registrarse, activaciones del kernel evitadas y despertares residuales, junto con los contadores del kernel existentes. La [prueba del protocolo en host](../tests/test_thread_alert_pending_host.py) cubre 65.536 intercambios entre hilos, entrega pendiente/bloqueada, fusión de señales, carreras de inicialización, vencimientos relativos/absolutos/largos, despertares residuales, errores y fallback. Valida el modelo del protocolo, no la velocidad de PS4. La ganancia física de FPS queda pendiente de medir; no cambian la identidad de la caché de shaders, la política de renderer ni la planificación de FG.
