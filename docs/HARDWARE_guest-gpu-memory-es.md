# Memoria de GPU de los invitados que terminan dentro de explorer

[English](HARDWARE_guest-gpu-memory.md) | [Español](HARDWARE_guest-gpu-memory-es.md)

## Síntoma

El 2026-11-16 (app de consola 04.08, base W303), Alan Wake's American Nightmare (Steam, 32 bits, como invitado) se
inició ocho veces en una misma sesión de OrbisDesk (`reports/pop-phase-b/physical/20261116T211401Z/run-0165.log`). El
último inicio, con wined3d + OpenGL, se cerró al cargar un nivel con
`PWVM commit_backing ... direct memory failed; no memory`. `tools/check-guest-memory.py` sobre ese log:

| Inicio | Libre al iniciar | Cómo terminó | Perdido hasta el inicio siguiente |
| --- | --- | --- | --- |
| 1 | 4,97 GB | exit 1 (temprano, wined3d) | 0,03 GB |
| 3 | 4,92 GB | terminate del overlay tras `VK_ERROR_DEVICE_LOST` (DXVK) | 0,75 GB |
| 4 | 4,17 GB | terminate del overlay tras `VK_ERROR_DEVICE_LOST` (DXVK) | 0,72 GB |
| 5 | 3,46 GB | terminó con su consola antes de dibujar | 0,13 GB |
| 6 | 3,33 GB | terminate del overlay | 0,63 GB |
| 7 | 2,70 GB | terminate del overlay (con wined3d-vulkan elegido) | 0,66 GB |
| 8 | 2,04 GB | exit 0 en un diálogo de error de MSAA, antes de dibujar | 0,02 GB |
| 9 | 2,03 GB | wined3d + OpenGL, 6 commits sin memoria | - |

Cada ejecución que dibujó con Direct3D y luego fue terminada perdió 0,63-0,75 GB. Las ejecuciones que terminaron por
sí mismas perdieron 0,02-0,13 GB, pero ninguna había dibujado un nivel, así que el log no tiene un control limpio de
"dibujó y luego salió normalmente". El inicio 2 (`steam-open.exe`) y los invitados sin GPU de la sesión anterior
(`run-0164.log`, 31 inicios) perdieron como mucho 0,02 GB cada uno.

## Causa

Los invitados comparten el proceso de explorer, así que la memoria que un invitado no devuelve queda perdida hasta que
OrbisDesk termina. En la consola, los buffers de RADV son memoria directa: el `ac_ps4_drm.c` de Crema reserva cada uno
con `sceKernelAllocateDirectMemory` y solo lo devuelve cuando se libera el buffer (`vkFreeMemory`), después de que la
GPU termine de usarlo. `ac_drm_device_deinitialize` no hace nada. Un invitado cuyos hilos son terminados (el cierre
del overlay, un crash) nunca libera su dispositivo Direct3D, así que DXVK o wined3d nunca liberan la memoria de
dispositivo que contiene sus texturas y buffers. Los logs de la descarga muestran qué se liberó:
`PWGUEST memory module=00400000 regions=0 released=0`, `detach skipped (terminated)` y
`system_modules ... loaded=48 unloaded=12`, con el `d3d9.dll` de DXVK todavía cargado. Nada libera los objetos de
Vulkan.

## Cambio

- `tools/build-win32u-ps4.py`: la capa Vulkan de win32u registra qué invitado creó cada `VkDevice`, mediante el
  `TEB.UserReserved[0]` del hilo que lo crea (el TEB de 32 bits en un hilo WoW64, como los streams de audio de W285).
  También registra el dispositivo de cada `VkDeviceMemory`. Una llamada nueva, `pw_guest_unix_call_funcs[0]` (con una
  tabla WoW64), libera la memoria de dispositivo que todavía tienen los dispositivos de un invitado. Ninguna memoria se
  libera dos veces: la memoria que no está en el registro ya se liberó, con su invitado o con su dispositivo. El
  `vkDestroyDevice` del propio programa primero libera la memoria de dispositivo que el programa dejó.
- `platform/ps4/pw_wine_unixlibs.c`: la biblioteca Unix estática `pwguest.so` con esas tablas.
- `tools/build-guest-hw.py`: `ps4_guest_unload` la llama cuando los hilos del invitado ya terminaron y ya se ejecutó
  el `DllMain(DETACH)` de sus módulos y de los módulos de sistema. El resultado se registra como
  `PWGUEST vulkan module=... devices=... memories=... bytes=... shared=... others=...`. win32u registra
  `PWVK guest_release`.
- `tools/check-guest-memory.py`: la tabla de arriba, a partir de cualquier log de consola. `--max-loss-gb` falla si
  la pérdida es grande.

## Lo que no se cambió a propósito y sigue abierto

- Se conservan los `VkDevice` del invitado. Destruir uno espera a sus colas, y un hilo terminado pudo dejarlas
  ocupadas o bloqueadas. Siguen ahí los buffers de RADV propios del dispositivo, los command pools, los descriptor
  pools y las imágenes de swapchain.
- El dispositivo de Zink (`libgallium_wgl.dll`, fijado para todos los invitados) queda fuera de la liberación por
  invitado, junto con su memoria. Es el dispositivo del proceso, así que su memoria solo se libera como se describe
  en la sección siguiente.
- Crema guarda en cuarentena hasta 96 MB de buffers liberados por dispositivo. Esa memoria solo se devuelve con
  actividad posterior en el mismo dispositivo, así que pueden quedar hasta unos 0,1 GB por dispositivo muerto.
- Después de `PWOVERLAY terminate`, el log muestra hilos del invitado terminado que fallan en sus módulos ya
  descargados (`PWFAULT ... thread=00c0 ... stack overflow`). Los hilos terminados pueden seguir ejecutándose un
  tiempo después de que vuelve la espera. Sus pilas no se cuentan aquí.

## Un invitado OpenGL terminado (run-0178)

`reports/wine-hardware-w303/physical/20261117T105502Z/run-0178.log` (app de consola 04.11, que ya incluye el cambio
anterior): el mismo juego se ejecutó con wined3d + OpenGL (`choice=wined3d-gl`), así que dibujó a través de
`libgallium_wgl.dll` de Mesa y de Zink. Se cerró desde el overlay: primero WM_CLOSE y, a los 3 s,
`PWOVERLAY terminate ... threads=38`. La memoria libre en el inicio siguiente era 3,50 GB, frente a 4,77 GB en su
propio inicio: una pérdida de 1,27 GB. La liberación sí se ejecutó en esa ruta: `PWGUEST vulkan module=00400000
devices=0 memories=0 bytes=0 shared=1 others=1`. El único dispositivo del invitado era el de Zink, que la liberación
omite.

El WGL de Mesa tiene una sola pantalla, y por tanto un solo `VkDevice` de Zink, para todo el proceso (uno por mundo).
Lo crea el primer invitado OpenGL, y `libgallium_wgl.dll` queda cargada (W173). Un invitado cuyos hilos son
terminados nunca borra sus contextos GL, así que sus texturas y buffers quedan en la memoria de ese dispositivo. Los
hilos de cola de Zink, creados desde los hilos del invitado, terminan con ellos. Borrar los contextos desde otro hilo
puede quedar esperando a esos hilos o a locks que tenían. En su lugar:

- `tools/vk-h0/patch-mesa-wgl-guest.py` (lo ejecutan los dos `build-mesa-zink*.sh`): cada contexto WGL registra el
  invitado del hilo que lo creó, leído de `TEB.UserReserved[0]` (0 para los hilos propios del escritorio). Una
  exportación nueva, `pw_wgl_release_screen`, hace que el dispositivo WGL olvide su pantalla, sus contextos y sus
  framebuffers sin tocarlos, salvo que quede un contexto de un hilo del escritorio. El contexto siguiente crea una
  pantalla nueva con hilos nuevos.
- `tools/build-guest-hw.py`: `ps4_guest_release_vulkan` la llama primero, pero solo cuando no hay ningún otro
  invitado ejecutándose en el mismo mundo. Registra `PWGUEST gl module=... result=... contexts=... desktop=...`, o
  `kept: N other guests running`.
- `tools/build-win32u-ps4.py`: con `PW_GUEST_RELEASE_GL` se libera la memoria de los dispositivos Zink de ese mundo,
  y se registra como `gl_devices=... gl_memories=... gl_bytes=...`. Los dispositivos se conservan, como los de
  cualquier invitado.
- `tools/check-guest-memory.py` suma `gl_bytes` a "vk freed" y muestra el resultado de `PWGUEST gl`.

Lo que esto no cubre:

- Si hay otro invitado ejecutándose en el mismo mundo, no se libera nada. La memoria sigue ocupada hasta que un
  invitado posterior termine estando solo.
- Los objetos de CPU de la pantalla anterior (contextos, cachés de Zink en memoria de heap) quedan como están.
- La memoria libre es memoria directa. La memoria virtual del mundo de 32 bits sale primero del pool flexible, y
  `pw_flexible_low` (66 MB restantes, por debajo de la reserva de 64 MiB) indica que los commits posteriores salieron
  de memoria directa. Los bloques de heap de un invitado no están entre las regiones registradas desde W208
  (`regions=0`), y `pw_decommit_host` conserva la memoria directa de un rango liberado con decommit. Por eso, parte de
  los 1,27 GB puede ser el heap del juego y no Zink. El nuevo valor `gl_bytes` muestra cuánto era de Zink.
- Este cambio requiere recompilar Mesa para las dos arquitecturas (`build-mesa-zink.sh`, `build-mesa-zink-i386.sh`).
  Sin la exportación nueva, kernelbase registra `kept: libgallium_wgl has no pw_wgl_release_screen`.

## Lo que se seguía perdiendo después de ese cambio (run-0185)

`reports/wine-hardware-w303/physical/20261117T132951Z/run-0185.log` (app de consola 04.12, con el cambio anterior y
Mesa recompilado): el mismo juego, con wined3d + OpenGL, se terminó desde el overlay. La liberación se ejecutó:
`PWGUEST gl module=00400000 result=1 contexts=1 desktop=0`, y luego `gl_devices=1 gl_memories=112 gl_bytes=523534416`.
La memoria libre en el inicio siguiente seguía 0,71 GB más baja (4,96 GB y después 4,25 GB).

La cifra de memoria libre de estos logs es la memoria disponible de `GlobalMemoryStatusEx`: la memoria directa libre
más la memoria flexible libre (`platform/ps4/pw_wine_memory.c`). Esta build suma todos los rangos directos reservados
para obtener la memoria directa libre (`free_source=summed` en la línea `PWBOOT memory_info`, y ningún cambio
`PWMEM direct_free` después). El total registrado es el tamaño de la memoria directa más la memoria flexible libre, así
que un cambio en el total es solo la parte flexible. `tools/check-guest-memory.py` ahora muestra la división:

| Log | Pérdida | Flexible | Directa |
| --- | --- | --- | --- |
| run-0178, antes del cambio | 1,27 GB | 0,21 GB | 1,06 GB |
| run-0185 | 0,71 GB | 0,22 GB | 0,49 GB |
| run-0165, ejecuciones DXVK que dibujaron y se terminaron | 0,63-0,75 GB | 0,03-0,11 GB | 0,60-0,66 GB |

El cambio quitó 0,57 GB de la parte directa, cerca de los 524 MB que liberó. La parte flexible es casi igual en los
dos logs, así que el cambio de Mesa no la afectó. run-0185 no tiene ninguna línea `pw_flexible_low`, así que el pool no
se quedó corto ahí.

La memoria directa tiene aquí dos usuarios: los búferes de RADV y, desde W175, los commits propios de Wine de 1 MiB o
más, hechos con `sceKernelAllocateDirectMemory` (`tools/build-audio-ps4.py`). Un commit solo se devuelve cuando Wine
libera su rango o le hace decommit. Según el código, los 0,49 GB restantes pueden ser:

- Commits grandes que dejó el invitado terminado: los segmentos de heap y bloques `VirtualAlloc` del juego, y las
  copias en memoria de sistema de texturas y búferes de wined3d. El dispositivo `Direct3D` del invitado nunca se
  libera, y `PWGUEST memory module=00400000 regions=0 released=0` muestra que no se devolvió ninguna región del
  invitado.
- Crema libera un búfer cuando la GPU terminó con él, y guarda los 96 MB más recientes de búferes liberados por
  dispositivo. Solo los devuelve cuando ese dispositivo vuelve a reservar o liberar. La pantalla del siguiente
  programa OpenGL usa la misma instancia de Zink, así que su actividad debería devolverlos. Hasta entonces quedan
  hasta 96 MB.
- El `VkDevice` de Zink que se conserva y los objetos que Zink creó en él no se destruyen. RADV reserva su memoria
  directa por su cuenta, no con `vkAllocateMemory`, así que el registro de win32u no la tiene. Esto incluye búferes
  de comandos, pools de descriptores, pools de consultas, el código de shaders compilado, y los búferes de anillo y de
  scratch de la cola.

La parte flexible, 0,22 GB, es memoria de CPU que el invitado dejó en commits más pequeños, por ejemplo bloques de
heap de menos de 1 MiB, los objetos de la pantalla abandonada y las pilas de sus hilos.

Este log no permite distinguirlos. Por eso la siguiente build añade una sonda y ninguna liberación más:

- `tools/build-audio-ps4.py`: `pw_vm_direct_bytes` de ntdll devuelve cuánta memoria directa tienen ahora los commits
  de Wine.
- `tools/build-win32u-ps4.py`: `PWVK guest_memory owner=... why=... direct_free=... flexible=... wine_direct=...
  wine_runs=... heaps=...`, con `why=release_before` y `why=release_after` alrededor de la liberación, y una llamada
  nueva, `pw_guest_unix_call_funcs[1]`, para `why=start`.
- `tools/build-guest-hw.py`: kernelbase hace esa llamada después de `PWGUEST load_begin`, y pasa el número de heaps
  del proceso del mundo (`RtlGetProcessHeaps`) en las dos llamadas.
- `tools/check-guest-memory.py` muestra `of the direct: Wine commits ..., other ...` y el número de heaps de un inicio
  al siguiente, y `release gave back direct ... MB`.

Cómo leer el siguiente log:

- La mayor parte de la pérdida directa en `Wine commits`: memoria propia del invitado. El paso siguiente sería
  liberar los commits de un invitado terminado, que el registro de regiones de W208 hoy no cubre.
- La mayor parte en `other`, con `release gave back direct` muy por debajo de `gl_bytes`: búferes liberados que siguen
  esperando en la cuarentena de Crema o a la GPU.
- La mayor parte en `other`, con `release gave back direct` cerca de `gl_bytes`: memoria de los objetos propios del
  dispositivo conservado. El paso siguiente sería destruir ese dispositivo y los objetos que Zink creó en él.
- Más heaps en el inicio siguiente que en el inicio del invitado: heaps que el invitado creó y nunca destruyó.

Prueba en consola para esta sonda: iniciar el juego con wined3d + OpenGL, dejar que dibuje y cerrarlo desde el
overlay. Hacerlo dos veces, para ver si la pérdida se repite y si la segunda pantalla devuelve la cuarentena. Después
iniciar un programa que no use la GPU (WFM), para que haya una línea de inicio más.

## Heaps, y el segundo invitado OpenGL (run-0190)

`reports/wine-hardware-w303/physical/20261117T151510Z/run-0190.log` (04.13, con la sonda anterior): se inició el
mismo juego con wined3d + OpenGL y se terminó desde el overlay; luego se inició WFM, y después otra vez el juego,
también terminado. `tools/check-guest-memory.py` da, para la primera ejecución:

| | GB |
| --- | --- |
| Perdido hasta el inicio siguiente | 0,86 |
| Flexible | 0,29 |
| Directa, commits de Wine de 1 MiB o más | 0,41 |
| Directa, otra | 0,16 |
| Memoria directa que devolvió la liberación (`gl_bytes` 532 MB) | 0,55 |

Los heaps de proceso del mundo de 32 bits pasaron de 2 al iniciar el juego a 5 al descargarlo, y
`PWGUEST memory ... regions=0`: el código propio del juego no reservó nada con `VirtualAlloc` que W208 pudiera
liberar. En el heap de Wine un bloque de unos 508 KB o más es un commit propio (memoria directa a partir de 1 MiB,
W175), y los bloques menores hacen crecer el heap en pasos de 64 KB (memoria flexible). Así que las dos partes pueden
ser memoria de heap que el invitado terminado nunca liberó, y nunca se destruyó ningún heap. El juego carga
`msvcr100.dll` desde `syswow64`; ese módulo cuenta como módulo del sistema y sigue cargado después del invitado
(`system_modules ... unloaded=0`), así que su heap de runtime de C es un probable responsable. El log no dice qué heap
tiene los bytes.

La segunda ejecución registró `PWGUEST gl ... result=1`, pero `release_before` y `release_after` muestran la misma
memoria libre y no hay línea `PWVK guest_release`. Zink guarda un `VkDevice` por dispositivo físico en una
`device_table` estática (`zink_screen.c`, `get_device`), y su instancia también es estática, así que la pantalla que
crea el WGL de Mesa después de `pw_wgl_release_screen` vuelve a tomar el mismo dispositivo. win32u había marcado ese
dispositivo como `abandoned` tras la primera liberación y desde entonces lo saltaba.

Los valores de `wine_direct` son reales. El ELF de hardware (`build/wine-hardware-w303/wine.elf`) tiene un único
`pw_vm_direct_bytes` global, de 319 bytes, junto a `pw_direct_release` en `virtual.c`. Solo el ELF de arranque, que
enlaza el `virtual.o` probado, tiene el valor por defecto débil de 14 bytes de win32u, que responde 0.

Cambios:

- `tools/build-win32u-ps4.py`: cada vez que kernelbase pasa `PW_GUEST_RELEASE_GL` se libera la memoria registrada en
  los dispositivos Zink de este mundo, no solo la primera vez.
- `tools/build-guest-hw.py`: el `HeapCreate` de kernelbase registra un heap creado en un hilo de un invitado, o
  mientras se carga su imagen, con la dirección del código que lo creó. `HeapDestroy` quita antes el registro.
  Después de descargar los módulos propios del invitado, `ps4_guest_release_heaps` registra la memoria libre
  (`PWVK guest_memory ... why=heaps_before`). Luego destruye cada heap registrado de ese invitado cuyo código creador
  ya no está en ningún módulo cargado, o estaba fuera de todo módulo. Un heap cuyo módulo creador sigue cargado se
  registra como `PWGUEST heap ... kept: made by <módulo>, still loaded`, y el total como
  `PWGUEST heaps module=... destroyed= kept= gone=`. El heap del proceso, y un heap que ya no está en la lista del
  proceso, nunca se destruyen.
- `tools/check-guest-memory.py`: `heaps destroyed N, kept M (<módulos>), gave back direct X MB, flexible Y MB`, de
  `heaps_before` a `release_before`. Los recuentos de heaps de la nota `of the direct` ahora son los del propio mundo
  del invitado al descargarse; el inicio siguiente puede estar en el otro mundo.

Lo que esto no cubre:

- Un heap de un módulo que sigue cargado se conserva, porque las variables globales de ese módulo todavía apuntan a
  él. Si el siguiente log nombra `msvcr100.dll` (u otro runtime de C) y la mayor parte de la pérdida se mantiene, el
  paso siguiente es retirar ese runtime cuando un invitado terminado fue su último usuario en su mundo: desmapearlo sin
  `DllMain` y luego destruir su heap. No se hace a ciegas. Otros módulos conservados pueden importarlo, y la segunda
  ejecución de run-0190 muestra que el invitado siguiente hoy reutiliza el runtime conservado sin problema.
- Los bloques del heap del proceso que dejó el invitado (wined3d reserva ahí) no se atribuyen a un invitado, así que
  se quedan.
- Los hilos del invitado que no se pudieron señalizar (`PWBOOT thread_signal unavailable`) siguen ejecutándose
  después de la descarga y fallan en código desmapeado (`PWFAULT`). Un heap destruido bajo uno de ellos se suma a
  fallos que ya ocurren.
- El dispositivo compartido de Zink tiene un único `queue_lock`. Un hilo terminado que lo tuviera bloquearía la
  pantalla siguiente. `pw_wgl_release_screen` solo reinicia los bloqueos del frontend WGL.

Prueba en consola: como en run-0190. Iniciar el juego con wined3d + OpenGL, dejar que dibuje y cerrarlo desde el
overlay. Hacerlo dos veces, con WFM entre las dos, y luego iniciar WFM una vez más para que la segunda ejecución
tenga un inicio siguiente. Después ejecutar `python3 -I tools/check-guest-memory.py <log de la ejecución>`. Lo
esperado: `release gave back direct` cerca de `gl_bytes` en las dos ejecuciones, una nota `heaps ...` en las dos, y
las líneas `PWGUEST heap ... kept` con el nombre de cualquier runtime de C que conserve un heap.

## Importaciones fijadas, y heaps que nada registró (run-0203)

`reports/wine-hardware-w303/physical/20261117T170454Z/run-0203.log` (04.15, con el cambio de run-0190): Alan Wake con
wined3d + OpenGL, terminado desde el overlay; luego WFM, vkcube y el Administrador de tareas; luego Portal 2, que
terminó solo (estado 100), y otra vez WFM. `tools/check-guest-memory.py` da:

| | Alan Wake | Portal 2 |
| --- | --- | --- |
| Perdido hasta el inicio siguiente (GB) | 0,81 | 0,75 |
| Flexible (GB) | 0,27 | 0,02 |
| Directa, commits de Wine de 1 MiB o más (GB) | 0,38 | 0,63 |
| Directa, otra (GB) | 0,16 | 0,10 |
| Memoria Vulkan liberada | 511 MB (`gl_bytes`) | 271 MB |
| Heaps del mundo de 32 bits, inicio -> descarga | 2 -> 5 | 5 -> 8 |
| `PWGUEST heaps` | destruidos 0, conservados 0 | destruidos 0, conservados 0 |

Portal 2 empieza con 5 heaps: los 3 que dejó Alan Wake siguen ahí. El log muestra dos causas.

**No se registró nada.** El registro de run-0190 estaba en el `HeapCreate` de kernelbase, y nada lo llamó. El kernel32
de Wine tiene su propio `HeapCreate` (`dlls/kernel32/heap.c`), no un reenvío a kernelbase. Los programas y sus runtimes
de C importan el de kernel32, y esta build no recompila kernel32. Así que la lista de registros quedó vacía, y se
imprimió `destroyed=0 kept=0 gone=0` para cada invitado.

**Los módulos del sistema del invitado dejaron de descargarse en 04.13.** En run-0185 (04.12), el mismo juego terminado
descargó 13 de sus 48 módulos del sistema, entre ellos `msvcr100.dll`, `MSVCP100.dll`, `d3dx9_43.dll` y
`XINPUT1_3.dll`. Su `DllMain(DETACH)` se ejecutó, y el runtime de C destruyó su propio heap. En run-0190 y run-0203 el
recuento es `system_modules ... loaded=48 unloaded=0`, y Portal 2 descargó 4 de 57. El `process_attach` de Wine fija
cada módulo que inicializa con un `lpReserved` no nulo (`if (lpReserved) wm->ldr.LoadCount = -1`), porque en Windows un
proceso conserva sus importaciones estáticas toda su vida. El cambio de run-0183 para Warcraft III pasa un contexto como
`lpReserved` a las importaciones del EXE de un invitado, y `process_attach` pasa el mismo puntero por todo el árbol de
importaciones. Cada módulo que importa el EXE del invitado, directa o indirectamente, quedó fijado:

- Sus módulos propios se desfijaron otra vez al final por d13 (`was pinned by the program: unpinned`): ninguna línea
  así en run-0185, 15 en run-0203.
- Sus módulos del sistema quedaron durante toda la vida del título, con los heaps de sus runtimes de C. El invitado
  siguiente que los usó empezó con el estado del runtime del invitado anterior.

Cambios (`tools/build-guest-hw.py`; reemplazan el registro de run-0190 en kernelbase):

- `loader.c` de ntdll: el contexto de run-0183 pasa al ámbito del archivo, y `process_attach` no fija un módulo cuando
  `lpReserved` es ese contexto. `DllMain` sigue recibiendo un `lpReserved` no nulo, que es lo que mira Storm.dll. Al
  final del invitado sus importaciones se descargan otra vez con sus módulos propios, como en 04.12, y su
  `DllMain(DETACH)` se ejecuta.
- `heap.c` de ntdll: `RtlCreateHeap`, donde termina cada `HeapCreate`, registra el invitado del hilo que lo crea
  (`TEB.UserReserved`). Un heap creado mientras carga el EXE de un invitado (`UserReserved[2]` es la marca de carga,
  como en el `DllMain` de sus importaciones) se registra como 1. `RtlDestroyHeap` quita el registro. kernelbase lee y
  cambia el registro con `RtlQueryHeapInformation` y `RtlSetHeapInformation` y una clase que Windows no tiene,
  `PW_HEAP_GUEST`. El heap del proceso nunca se registra.
- `process.c` de kernelbase:
  - En el `load_end` del invitado, los heaps registrados como 1 pasan a ser de ese invitado (`PWGUEST heaps ...
    claimed=N made while it loaded`).
  - Después de descargar sus módulos propios, `ps4_guest_release_heaps` registra `why=heaps_before`. Luego toma cada
    heap todavía registrado para el invitado y busca el handle del heap en las secciones escribibles de cada módulo
    cargado salvo ntdll. Un heap que guarda una variable global de un módulo se conserva y se registra como
    `PWGUEST heap ... kept: held by <módulo>`; cualquier otro heap se destruye. El total se registra como
    `PWGUEST heaps module=... destroyed= kept=`.
- `tools/check-guest-memory.py` lee tanto las líneas antiguas `made by` como las nuevas `held by`.

Lo que esto no cubre:

- Los bloques que el invitado dejó en heaps que no creó siguen ahí: el heap del proceso y el heap de `msvcrt.dll`, que
  usan DXVK y otros módulos compilados con MinGW. Parte de los 0,63 GB de commits de Wine de Portal 2 puede estar ahí.
  El próximo log lo separa: de `heaps_before` a `release_before` es lo que devolvió destruir los heaps propios del
  invitado, y las líneas `system_unloaded` muestran lo que se llevaron las importaciones ya no fijadas.
- Un DLL del sistema que sigue cargado y guarda un heap que creó en un hilo del invitado en otro lugar que una variable
  global pierde ese heap. Entre los DLL de Wine, wined3d (el heap de subida de un contexto diferido), dbghelp (un pool)
  y webservices (un `WS_HEAP`) guardan un heap en un objeto asignado. El de wined3d pertenece al dispositivo del
  invitado terminado; los otros dos son objetos que crea un programa.
- Los hilos que no se pudieron señalar, y el `queue_lock` de Zink, como en la sección de run-0190.
- Sin el fijado, los módulos del sistema de un invitado terminado vuelven a ejecutar `DllMain(DETACH)`, como hasta
  04.12 (run-0185). Warcraft III (run-0183) sigue recibiendo su `lpReserved` no nulo; hay que comprobar su inicio otra
  vez.

Prueba en consola, con una build que contenga este cambio:

1. Iniciar Alan Wake con wined3d + OpenGL, dejar que dibuje y cerrarlo desde el overlay.
2. Iniciar WFM.
3. Iniciar Portal 2 y salir desde su menú.
4. Iniciar WFM otra vez.
5. Iniciar Warcraft III, comprobar que llega a su menú, y salir.
6. Ejecutar `python3 -I tools/check-guest-memory.py <log de la ejecución>`.

Lo esperado:

- Los dos juegos: líneas `system_unloaded`, entre ellas `msvcr100.dll` para Alan Wake.
- `heaps destroyed N` con N mayor que 0, o líneas `kept` que nombren al módulo que lo guarda.
- Portal 2 empieza con el mismo número de heaps con el que empezó Alan Wake.

## Bloques grandes en heaps que el invitado no creó (run-0212)

`reports/wine-hardware-w303/physical/20261117T190919Z/run-0212.log` (04.17, con el cambio de run-0203):
`tools/check-guest-memory.py` da:

| | Alan Wake, terminado desde el overlay | Portal 2, salida desde su menú |
| --- | --- | --- |
| Perdido hasta el inicio siguiente (GB) | 0,69 (04.15: 0,81) | 0,15 (04.15: 0,75) |
| Flexible (GB) | 0,22 | 0,03 |
| Directa, commits de Wine de 1 MiB o más (GB) | 0,32 | 0,05 |
| Directa, otra (GB) | 0,15 | 0,07 |
| Módulos del sistema descargados | 13 de 48, entre ellos `msvcr100.dll` | 2 de 46 |
| `PWGUEST heaps` | destruidos 1, conservados 1 (`msacm32.dll`) | destruidos 1, conservados 1 (`SHELL32.dll`) |

Sin el fijado, una salida normal pierde poco. La terminación del overlay todavía conserva 0,32 GB de commits de Wine
y 0,22 GB de memoria flexible. El heap que destruyó la liberación no devolvió nada: `wine_direct` y `flexible` son
iguales en `heaps_before` y en `release_before`. El heap del runtime de C ya no estaba en ese momento:
`msvcr100.dll` se descarga con los módulos propios del invitado, antes de `heaps_before`, y su `DllMain(DETACH)`
destruye su heap. Lo que queda está en heaps que el invitado no creó:

- El heap del proceso: `HeapAlloc(GetProcessHeap())`, el malloc de `ucrtbase.dll` y el de un runtime de C enlazado
  estáticamente.
- El heap de `msvcrt.dll`: el malloc de los propios DLL de Wine (entre ellos wined3d), de DXVK y del WGL de Mesa.

Un invitado terminado nunca libera sus objetos ahí, y estos heaps se quedan durante toda la vida del título.

Cambios (`tools/build-guest-hw.py`):

- `heap.c` de ntdll:
  - Un bloque de heap de `HEAP_MIN_LARGE_BLOCK_SIZE` o más (unos 508 KB en i386, 1020 KB en x86_64) es una
    asignación virtual propia.
  - Cada uno termina ahora en una etiqueta después de su `block_size`, así que un cambio de tamaño en el mismo lugar no
    la alcanza. La etiqueta registra el invitado del hilo que asigna (`TEB.UserReserved[0]`), el código que llamó a
    `RtlAllocateHeap` o `RtlReAllocateHeap`, y el marco de encima.
  - `RtlQueryHeapInformation` con una clase que Windows no tiene, `PW_HEAP_LARGE`, lista los bloques etiquetados de
    un invitado. También da los commits de los subheaps de un heap y sus bloques grandes.
- `process.c` de kernelbase:
  - Al inicio de cada invitado se registra cada heap de 1 MiB o más (`PWGUEST heap_usage ... why=start`).
  - Después de destruir los heaps propios del invitado, `ps4_guest_release_large` registra otra vez cada heap
    (`why=release`, con el módulo que lo guarda). Luego toma los bloques etiquetados del invitado en cada heap que se
    queda.
  - Un bloque cuyo código de asignación ya no está en ningún módulo cargado se libera. Ese código eran los módulos
    propios del invitado, o un módulo del sistema que se fue con ellos.
  - Cualquier otro bloque se conserva y se cuenta por el módulo que llamó y el módulo de encima
    (`PWGUEST heap_large ... kept bytes= ... from <módulo> via <módulo>`).
- `tools/check-guest-memory.py` muestra el crecimiento de cada heap desde el inicio del invitado hasta su liberación
  (`heap growth`), y los bloques grandes liberados y conservados (`large blocks`).

Lo que esto no cubre:

- Los bloques asignados a través de un runtime de C que sigue cargado, como `msvcrt.dll` o `ucrtbase.dll`, se
  conservan, aunque el módulo de encima ya no esté. Esto incluye los bloques que el código propio del invitado asignó
  con el malloc de `ucrtbase.dll`. En i386 el marco de encima sale de la cadena de punteros de marco, que puede ser
  errónea en código compilado sin punteros de marco, así que nombra el bloque pero no decide su liberación. El próximo
  log muestra cuánto son estos bloques.
- Los bloques por debajo del tamaño grande: hacen crecer los subheaps de un heap (la parte flexible), y nada los
  etiqueta. `heap growth` muestra en qué heap están.
- Un bloque que el código del invitado asignó y entregó a un módulo que se queda, y que lo guarda, se libera debajo de
  ese módulo. No se conoce ningún caso; el log nombra cada cantidad liberada (`freed_bytes`).
- La memoria directa "otra" de GTA SA después de una salida normal (run-0210, 04.16: de 0,40 a 0,49 GB) no viene de
  los commits de Wine y no cambia aquí. Primero necesita una ejecución en 04.17 o posterior.

Prueba en consola, con una build que contenga este cambio:

1. Iniciar Alan Wake con wined3d + OpenGL, dejar que dibuje y cerrarlo desde el overlay.
2. Iniciar WFM.
3. Iniciar Portal 2 y salir desde su menú.
4. Iniciar WFM otra vez.
5. Iniciar Warcraft III, comprobar que llega a su menú, y salir.
6. Ejecutar `python3 -I tools/check-guest-memory.py <log de la ejecución>`.

Lo esperado:

- `heap growth` nombra el heap que conservó los commits de Wine y la memoria flexible de Alan Wake.
- `large blocks` muestra lo que se liberó y, para lo que se conservó, qué módulos lo asignaron.
- Nada falla después de una liberación (`PWFAULT`), y el invitado siguiente arranca.

## El dispositivo Vulkan y el dispositivo de Crema que dejaba una salida normal (run-0215)

`reports/wine-hardware-w303/physical/20261117T194648Z/run-0215.log` (04.17): GTA San Andreas con el renderizador
Vulkan de wined3d, terminado dos veces por su propia salida (estado 0). `tools/check-guest-memory.py` da:

| | Primera ejecución | Segunda ejecución |
| --- | --- | --- |
| Perdido hasta el inicio siguiente (GB) | 0,63 | 0,45 |
| Directa, commits de Wine de 1 MiB o más (GB) | 0,11 | 0,04 |
| Directa, otra (GB) | 0,47 | 0,39 |
| Memoria de dispositivo liberada al final | 170 MB en 19 objetos | 170 MB |

El juego no liberó su dispositivo Direct3D antes de salir, así que la liberación encontró su VkDevice con 19 objetos
de memoria de dispositivo. La liberación los liberó, conservó el dispositivo como siempre, y nada cambió hasta el
inicio siguiente. Quedaban dos poseedores:

- **El VkDevice conservado.** Parte de su memoria nunca pasa por `vkAllocateMemory`, así que el registro de win32u no
  la ve: lo que RADV asigna para sí mismo (anillos de cola, scratch, arenas de shaders, los búferes de comandos
  internos), y los búferes de los objetos que el programa nunca destruyó (pools de comandos, de descriptores y de
  consultas, las imágenes de una swapchain). Todo eso se queda hasta que se destruye el dispositivo.
- **El dispositivo de Crema de su instancia.** Crema crea un dispositivo nuevo para cada winsys de RADV, es decir uno
  por instancia, y su `ac_drm_device_deinitialize` no hacía nada: "el dispositivo vive todo el proceso". Un
  dispositivo de Crema conserva hasta 96 MB de búferes liberados en cuarentena contra escrituras tardías de la GPU
  (`PS4_QUARANTINE_BYTES`), más cualquier búfer que siga asignado. Nada los devolvía cuando la instancia ya no estaba.

`guest-heap-large-run0212.patch` no cubre esto: solo actúa sobre los commits propios de Wine.

Cambios:

- `tools/vk-h0/patch-crema-release.py` (nuevo, lo ejecuta `tools/vk-h0/build-mesa.sh` con `VARIANT=wine`):
  - `ac_drm_device_deinitialize` se ejecuta cuando termina un winsys, es decir cuando se destruye su instancia,
    después de todos sus dispositivos. Ya no puede llegar ningún envío por ese dispositivo de Crema.
  - Espera hasta 1,5 s al último envío. Luego ejecuta cada desmapeo y liberación diferidos, la cuarentena incluida,
    y desmapea y libera cada búfer que siga en la tabla del dispositivo.
  - La estructura del dispositivo, su página de fence y sus ventanas de direcciones se quedan, porque los registros
    de tiempo de GPU de W103 guardan el puntero del dispositivo.
  - Un dispositivo cuyos envíos no terminaron lo conserva todo, como antes. La línea
    `radv/ps4: device ... ended: gave back N bytes` da los bytes devueltos.
- `tools/build-win32u-ps4.py`:
  - Las swapchains registran su dispositivo, y las instancias registran el invitado que las creó. El propio
    `vkDestroySwapchainKHR` y `vkDestroyInstance` del programa quitan los registros.
  - Cuando se libera un invitado que terminó por sí mismo (`PW_GUEST_RELEASE_DEVICES`), sus dispositivos salen de
    los registros después de liberar su memoria.
  - Sus swapchains dejan de ser capas de GPU (`ps5_vulkan_forget`) en el hilo que llama.
  - Luego un hilo auxiliar destruye esas swapchains, espera a que cada dispositivo esté inactivo
    (`vkDeviceWaitIdle`) y destruye el dispositivo. Después destruye cada instancia que creó el invitado y que ya no
    tiene ningún dispositivo, salvo la compartida de Zink.
  - El que llama espera como mucho 3 s. Una cola que quedó ocupada, o un lock que quedó tomado, por uno de los hilos
    del invitado que se terminó en su salida bloquea solo al hilo auxiliar. Lo que el auxiliar no destruyó se queda,
    fuera de los registros, como se quedaba un dispositivo conservado antes de este cambio.
  - Líneas registradas: `PWVK guest_teardown owner=... swapchains= devices= instances= ms=` del auxiliar, y la memoria
    libre después (`PWVK guest_memory ... why=teardown_after`). Si el auxiliar sigue a los 3 s:
    `PWVK guest_teardown ... still running after N ms`.
- `tools/build-guest-hw.py`: kernelbase pasa `PW_GUEST_RELEASE_DEVICES` salvo que el invitado se haya terminado (el
  cierre del overlay, un fallo; W209).
- `tools/check-guest-memory.py`: `teardown: swapchains, devices, instances, Crema gave back, gave back direct`.

Lo que sigue como estaba:

- Un invitado terminado, como uno cerrado desde el overlay, sigue liberando solo la memoria de su dispositivo. Sus
  hilos se detuvieron donde estuvieran, y una espera de cola o un lock del dispositivo podría bloquear. Las
  ejecuciones terminadas de Alan Wake no cambian con esto.
- El dispositivo y la instancia de Zink, que comparten todos los invitados OpenGL.
- Las ventanas de direcciones de un dispositivo de Crema terminado (espacio de direcciones virtual, no memoria).

Riesgos:

- El auxiliar se ejecuta sin TEB. Solo llama a funciones de Vulkan, a la eliminación de objetos de win32u y a
  `fprintf`. La parte de ventanas (`ps5_vulkan_forget`) se ejecuta antes en el hilo que llama.
- Un hilo del invitado que se terminó dentro de RADV puede dejar un lock tomado. Entonces el auxiliar se bloquea ahí
  para siempre, y no tiene ningún lock propio. Solo se quedan ese dispositivo y su instancia, como antes.
- Un programa que siga usando un dispositivo después de su propia salida no existe en este modelo: su código se
  descarga antes.

El subconjunto más seguro es solo el cambio de Crema (`patch-crema-release.py` y su línea en `build-mesa.sh`). Libera
búferes solo después de que la GPU terminó todo lo que envió ese dispositivo. Ayuda a cada programa que destruye su
propia instancia, pero no a GTA SA, que conserva su dispositivo y su instancia.

Prueba en consola, con una build que contenga este cambio y `guest-heap-large-run0212.patch`:

1. Iniciar GTA San Andreas, cargar una partida y salir desde su menú.
2. Iniciar GTA San Andreas otra vez, cargar una partida y salir desde su menú.
3. Iniciar vkcube y cerrarlo; iniciar Portal 2 y salir desde su menú.
4. Iniciar Alan Wake con wined3d + OpenGL, dejar que dibuje y cerrarlo desde el overlay.
5. Iniciar WFM, y comprobar que el escritorio y la barra de tareas siguen respondiendo.
6. Ejecutar `python3 -I tools/check-guest-memory.py <log de la ejecución>`.

Lo esperado:

- Después de cada ejecución de GTA SA: `teardown: swapchains 1+, devices 1, instances 1+`, una línea
  `radv/ps4: device ... ended`, y una pérdida de directa "otra" muy por debajo de 0,39 GB.
- Ninguna línea `still running`, y ningún fallo de GPU ni `PWFAULT` después de una destrucción.
- Alan Wake, terminado: ninguna línea de destrucción; sus cifras como en run-0212.

## Cada inicio posterior moría en vkCreateDevice (run-0219)

`reports/wine-hardware-w303/physical/20261117T220342Z/run-0219.log` (04.19, con el cambio de run-0215): GTA San
Andreas terminó por su propia salida (estado 0). La destrucción destruyó 1 swapchain, 1 dispositivo y 2 instancias
en 10 ms, y devolvió 155 MB de memoria directa después de los 130 MB de la liberación. Sus dos inicios siguientes
murieron antes de su primer fotograma: `vkCreateDevice Exception 0xc0000005 in Unix call`, estado de salida 3.

La causa son las instancias. El dispositivo real de GTA San Andreas es de DXVK: `PWOVERLAY render ...
choice=dxvk-vulkan`, y el primer inicio carga `openvr_api_dxvk.dll` y `wineopenxr.dll` justo antes. La sección
anterior de run-0215 lo llama renderizador de wined3d; solo son de wined3d los dispositivos de ventana oculta de
antes.

- `d3d9.dll` de DXVK 2.7.1 guarda un único `DxvkInstance` para todo el proceso: `Singleton<DxvkInstance>
  g_dxvkInstance` en `src/d3d9/d3d9_interface.cpp`. Lo libera el último objeto de Direct3D 9, y el juego nunca
  liberó el suyo.
- El mundo de 32 bits conserva las DLL del sistema que cargó un invitado: `PWGUEST system_modules module=00400000
  loaded=46 unloaded=1`. `d3d9.dll` siguió cargada con su singleton, su `VkInstance` y su `VkPhysicalDevice`.
- El inicio siguiente tomó esa instancia otra vez. Su DXVK no volvió a cargar `openvr_api_dxvk.dll`, porque el
  sondeo de VR también se ejecuta una sola vez por proceso. `vkCreateDevice` sobre su dispositivo físico leyó los
  objetos de win32u que la destrucción había liberado.

Antes de run-0215 la instancia perdida seguía viva, así que el inicio siguiente funcionaba sobre ella. Al dispositivo
no le pasa lo mismo: DXVK crea un `VkDevice` nuevo para cada dispositivo de Direct3D 9.

Cambios, contra 04.19 (`guest-vk-teardown-instances-run0219.patch`):

- `tools/build-win32u-ps4.py`: la destrucción destruye las swapchains y los dispositivos del invitado, como antes,
  pero ninguna instancia. Los registros de instancias (`pw_vk_instances`, con el dueño y la lista que mantenían
  `vkCreateInstance` y `vkDestroyInstance`) ya no están. La línea ahora es
  `PWVK guest_teardown owner=... swapchains= devices= ms=`.
- `tools/vk-h0/patch-crema-release.py`, ya que la instancia se queda:
  - Un dispositivo de Crema cuenta los contextos de RADV, uno por cola (`ac_drm_cs_ctx_create2`,
    `ac_drm_cs_ctx_free`).
  - Cuando se va el último, nada puede enviar por ese dispositivo, así que no es posible una escritura tardía por
    un descriptor obsoleto. La cuarentena se va: se devuelve cada búfer liberado cuyos envíos terminaron. Mientras
    el dispositivo no tiene cola, cada liberación posterior se ejecuta en cuanto terminan sus envíos, sin
    cuarentena. Eso incluye los búferes que `vkDestroyDevice` libera después de sus colas.
  - Línea: `radv/ps4: device ... has no queues: gave back N bytes; M bytes in buffers now`. Una cola nueva en el
    mismo dispositivo (el `VkDevice` siguiente de la misma instancia) trae la cuarentena de vuelta.
  - El final de un dispositivo (`ac_drm_device_deinitialize`, cuando un programa destruye su instancia) sigue
    ejecutando las operaciones diferidas. Ya no libera los búferes que quedan en su tabla. Son objetos perdidos de
    un programa, y antes habría que quitar sus mapeos de GPU, como hace el propio desmapeo de Crema. Su línea es
    `radv/ps4: device ... ended: gave back N bytes; M bytes in K buffers its users left are kept, J operations still
    wait`.
- `tools/build-guest-hw.py`: solo su comentario.
- `tools/check-guest-memory.py`:
  - La línea de destrucción puede no tener instancias.
  - Las líneas "has no queues" de Crema cuentan como "Crema gave back".
  - Una línea de Crema cuenta solo para la última ejecución liberada, hasta el inicio siguiente. Antes, a la
    primera ejecución de run-0219 también se le daban los dispositivos de sondeo de la segunda: 246 MB en vez de
    51 MB.

Lo que se queda:

- La instancia y su dispositivo de Crema, con los búferes que retienen los objetos perdidos del programa. Para GTA
  San Andreas eran 9 MB en 160 búferes en run-0219. Un inicio posterior los reutiliza a través de la instancia de
  DXVK.
- Un programa cuya instancia nada reutiliza la conserva hasta que termina el proceso de la consola, como antes de
  run-0215.

Riesgos:

- Destruir el dispositivo se mantiene. Un módulo que sigue cargado también podría guardar un `VkDevice` y usarlo en
  el inicio siguiente. Los objetos de todo el proceso de DXVK 2.7.1 son su instancia, sus adaptadores y su sondeo de
  VR. Los dispositivos de wined3d pertenecen a un objeto de Direct3D. La capa de MangoHud conserva su registro del
  dispositivo destruido, y nada vuelve a llamar a través de ese registro.
- Un recuento de colas de 0 también ocurre un instante mientras RADV comprueba si una prioridad de cola está
  permitida. Solo devuelve búferes con los que la GPU ya terminó.

Prueba en consola (necesita la aprobación del usuario), con una build que contenga este cambio:

1. Iniciar GTA San Andreas, cargar una partida y salir desde su menú. Hacerlo tres veces.
2. Iniciar vkcube y cerrarlo; iniciar Portal 2 y salir desde su menú.
3. Iniciar Alan Wake con wined3d + OpenGL y cerrarlo desde el overlay.
4. Iniciar WFM, y comprobar que el escritorio y la barra de tareas siguen respondiendo.
5. Ejecutar `python3 -I tools/check-guest-memory.py <log de la ejecución>`.

Lo esperado:

- Cada inicio de GTA San Andreas llega a su menú. Ningún `vkCreateDevice Exception`.
- Después de cada ejecución: `teardown: swapchains 1, devices 1, Crema gave back ...`, sin instancias, y "gave back
  direct" cerca de los 155 MB de run-0219.
- Ninguna línea `still running`, ningún fallo de GPU y ningún `PWFAULT`.
- Alan Wake, terminado: ninguna línea de destrucción.

## Invitados terminados: un invitado sin DLL propias, y los bloques de wined3d (ejecuciones de 04.27)

`tools/check-guest-memory.py` sobre `reports/wine-hardware-w303/physical/20261119T111322Z/` (04.27):

| Ejecución | Programa, final | Perdido | Notas |
| --- | --- | --- | --- |
| run-0244 #2 | Alan Wake, terminado | 0.78 GB | heap del proceso +409 MB; 114 MB de bloques grandes retenidos "from ucrtbase via wined3d" |
| run-0244 #3 | Portal 2, terminado | 0.33 GB | ningún bloque grande retenido |
| run-0246 #1 | Doom 3, terminado | 0.44 GB | heaps 2 -> 4; ninguna línea de heaps ni de bloques grandes |

Doom 3 no tiene DLL propias: `PWGUEST own_modules ... count=0 ... terminated=1`. `ps4_guest_unload_own` volvía en el
acto cuando esa cuenta era 0, así que los heaps del invitado (`ps4_guest_release_heaps`) y sus bloques grandes
(`ps4_guest_release_large`) nunca se liberaban. El inicio siguiente seguía listando el heap de Doom 3: `heap_usage ...
heap=09040000 holder=- committed=78839808`. Todo invitado sin DLL propias (wfm, notepad, Doom 3) se saltaba ese paso.

En Alan Wake se liberaron los bloques grandes cuyo código de asignación ya no estaba (7 MB). Los 114 MB que wined3d.dll
había asignado a través de ucrtbase se retuvieron, porque wined3d sigue cargado en el mundo de 32 bits.

Cambios (`tools/build-guest-hw.py`, kernelbase):

- `ps4_guest_unload_own`: sin módulos propios, sigue con la memoria que reservó el código del invitado y con sus heaps
  y bloques grandes, como después de descargar sus módulos propios. Los restos (la descarga en un inicio posterior)
  siguen sin tocar los heaps, como antes.
- `ps4_guest_release_large`: para un invitado terminado (cierre desde el overlay o fallo), también se libera un bloque
  grande cuyo módulo de asignación, o el marco de arriba, es `wined3d.dll`.
  - El estado de todo el proceso de wined3d solo tiene entradas pequeñas: las tablas de procedimientos de ventana y
    de estados de swapchain, y las notificaciones de presupuesto. Sus bloques grandes pertenecen a los objetos que
    creó un programa: copias de recursos en memoria del sistema, las colas del command stream.
  - Un invitado terminado nunca libera esos objetos, y sus ventanas, por las que wined3d llegaría a su dispositivo,
    se destruyeron antes.
  - DXVK no se incluye: su `d3d9.dll` guarda una sola instancia para todo el proceso (run-0219).
  - Un invitado que termina por sí mismo conserva la regla de hoy.
  - Línea nueva, parte del `freed_bytes` de las líneas `heap_large ... heap=`: `PWGUEST heap_large module=... objects
    freed_bytes=N blocks=M: the terminated guest's, made through wined3d.dll`.

No cambiado, sigue abierto:

- El crecimiento propio del heap del proceso (+409 MB en Alan Wake): los bloques pequeños no llevan etiqueta de dueño,
  y el heap del proceso es compartido con todos los demás invitados del mundo.
- La memoria flexible (0.17-0.23 GB) y la otra memoria directa (0.12-0.19 GB) de un invitado terminado.

Lo esperado: Doom 3, terminado, devuelve su propio heap (79 MB en run-0246) y sus bloques grandes; Alan Wake,
terminado, unos 114 MB más. Portal 2 no cambia.

Verificación: solo compilación. El `process.c` de kernelbase para i386 y x86_64, con las mismas advertencias que sin el
cambio. No se construyó ni se ejecutó en la consola.

Prueba en consola (necesita la aprobación del usuario), con una build que contenga este cambio:

1. Iniciar Doom 3 y cerrarlo desde el overlay.
2. Iniciar Alan Wake (wined3d + OpenGL) y cerrarlo desde el overlay.
3. Iniciar Portal 2 y salir desde su menú; iniciarlo otra vez y cerrarlo desde el overlay.
4. Iniciar WFM y el Bloc de notas, cerrarlos, y comprobar que el escritorio y la barra de tareas siguen respondiendo.
5. Ejecutar `python3 -I tools/check-guest-memory.py <log de la ejecución>`.

Lo esperado:

- Doom 3: líneas `PWGUEST heaps module=00400000 destroyed=...` y `heap_large ... heap=`, y "heaps" de vuelta a su
  cuenta del inicio.
- Alan Wake: la línea `objects freed_bytes=` cerca de 114 MB, y ninguna línea `kept ... via L"wined3d.dll"`.
- Ningún PWFAULT después de una liberación, y el juego siguiente inicia y dibuja.

## Bloques pequeños del heap del proceso, y bloques grandes de ningún invitado (ejecuciones de 04.29)

`tools/check-guest-memory.py` sobre `reports/wine-hardware-w303/physical/20261119T144942Z/` (04.29, con el cambio
anterior):

| Ejecución | Programa, final | Perdido | Heap del proceso en la liberación |
| --- | --- | --- | --- |
| run-0252 #1 | Alan Wake, terminado | 0.65 GB | 199 MB de subheaps, 204 MB de bloques grandes (146), 68 del invitado |
| run-0253 #1 | Alan Wake, terminado | 0.64 GB | 194 MB de subheaps, 220 MB de bloques grandes (146), 69 del invitado |
| run-0253 #2 | Alan Wake, terminado | 0.42 GB | 364 MB de subheaps (+170 MB), 307 MB de bloques grandes (239, +157), 69 del invitado |

El cambio anterior funcionó: cada vez se liberaron 123 MB de bloques grandes, 116 MB de ellos hechos a través de
wined3d.dll. Lo que queda está en el heap del proceso:

- Sus subheaps crecen 170-200 MB por inicio y el inicio siguiente no los reutiliza: bloques pequeños, por debajo del
  tamaño de bloque grande, todavía en uso. Un bloque pequeño no lleva dueño, así que no se podía liberar nada.
- 88 bloques grandes de unos 83 MB por inicio no llevan la etiqueta del invitado: los hizo un hilo que no es de ningún
  invitado.
- El heap de msacm32.dll, retenido porque msacm32 lo guarda, está por debajo de 1 MiB.

Cambios (`tools/build-guest-hw.py`):

- ntdll, i386: un bloque pequeño que el hilo de un invitado asigna en el heap del proceso lleva su sitio de asignación
  en la ranura de valor de usuario del heap (`HEAP_ADD_USER_INFO`, como la usa `RtlSetUserValueHeap`): el invitado, el
  código que llamó a `RtlAllocateHeap` o `RtlReAllocateHeap`, y el marco de arriba. Un sitio cuenta sus bloques y bytes
  vivos. Un bloque redimensionado conserva su sitio, en el lugar o movido, lo redimensione quien lo redimensione. Estos
  bloques no pasan por el LFH, así que todos se alcanzan bajo el lock del heap. `C:\orbis\nosmalltags.txt` lo
  desactiva sin recompilar.
- kernelbase, después de los bloques grandes de un invitado: se listan sus sitios (`PW_HEAP_SITES`), y los bloques de
  los sitios elegidos se liberan en una pasada por el heap del proceso bajo su lock (`PW_HEAP_SITES_FREE`). Después
  terminan todos sus sitios. Las reglas son las de los bloques grandes: el código que asignó ya no está, o, para un
  invitado terminado, el sitio está en wined3d.dll.
- "Código ausente" ahora también cubre un bloque que un runtime de C (ucrtbase, msvcr*, kernelbase, kernel32) asignó
  para código que ya no está: el marco de arriba no está en ningún módulo cargado. Vale también para los bloques
  grandes.
- Los bloques grandes de un hilo de ningún invitado también registran el marco de arriba. Después de cada liberación
  se listan, se liberan los de código ausente, y el resto se registra por módulo.
- Líneas nuevas: `PWGUEST heap_small module=... sites=N blocks=N bytes=N listed=N missed=N freed=N freed_bytes=N`,
  luego hasta ocho líneas `... kept bytes=N blocks=N from <módulo> via <módulo>` por tamaño, y `... objects bytes=N
  ...` para la parte de wined3d; `PWGUEST heap_unowned module=... blocks=N bytes=N listed=N freed=N freed_bytes=N` y
  sus líneas `kept`. `check-guest-memory.py` las muestra como "small blocks" y "unowned large".

Costos y límites:

- Cada bloque etiquetado ocupa 8 bytes más, y las asignaciones pequeñas de un invitado en el heap del proceso toman el
  lock del heap en lugar del LFH. Cada sitio nuevo hace el recorrido de pila que ya hacen los bloques grandes.
- x86_64 no cambia: su recorrido de pila se desenrolla por tablas, demasiado lento para cada asignación.
- Los bloques que asigna un hilo de ningún invitado (el hilo del temporizador de winmm, el hilo del cargador mientras
  carga el EXE de un invitado) no se etiquetan.
- Un módulo compartido que guarde un bloque hecho por el código ausente quedaría con un bloque liberado. Los bloques
  grandes ya tienen este riesgo.
- Un hilo de invitado matado mientras tiene el spin lock de la tabla de sitios bloquearía las inserciones de sitios
  posteriores. La ventana es de pocas instrucciones, y el propio lock del heap tiene la misma exposición.

Verificación: solo compilación para la consola; el `heap.c` de ntdll y el `process.c` de kernelbase compilan para i386 y
x86_64 con las mismas advertencias que sin el cambio. En el host, a una copia privada de la build de Wine del host se le
volvió a enlazar ntdll con el `heap.c` generado (ambas arquitecturas): `wineboot -i` funcionó, y pasó un programa de
prueba i386. Ese programa ponía `TEB.UserReserved[0]` como lo tienen los hilos de un invitado, y cubría asignaciones,
redimensionados (en el lugar, movidos, por un hilo de ningún invitado, de pequeño a grande) y liberaciones. Las cuentas de
los sitios coincidieron exactamente con los bloques vivos (1500 bloques, 3130254 bytes). Liberar los sitios liberó
exactamente esos, `HeapValidate` pasó antes y después, y los bloques sin etiqueta conservaron su contenido. Una prueba de
estrés con 4 hilos y 100.000 operaciones por hilo, con un hilo de ningún invitado al lado, también coincidió (1241
bloques). Una asignación y liberación etiquetada costó unas 3 veces una sin etiqueta en el host (0.16 s contra 0.05 s por
millón). El código de liberación de kernelbase no se ejecutó en el host.

Lo esperado en la consola: para un Alan Wake terminado, la línea `heap_small` muestra la mayor parte de los 170-200 MB,
y las líneas `kept` nombran lo que queda (la parte de wined3d se libera). El crecimiento del heap del proceso en "heap
growth" baja en lo liberado. `heap_unowned` nombra los 83 MB de bloques grandes de ningún invitado.

Prueba en consola (necesita la aprobación del usuario), con una build que contenga este cambio:

1. Iniciar Alan Wake (wined3d + OpenGL), jugar un poco y cerrarlo desde el overlay. Hacerlo dos veces.
2. Iniciar Portal 2, salir desde su menú, iniciarlo otra vez y cerrarlo desde el overlay.
3. Iniciar Doom 3 y cerrarlo desde el overlay.
4. Iniciar WFM y el Bloc de notas, cerrarlos, y comprobar que el escritorio y la barra de tareas responden.
5. Ejecutar `python3 -I tools/check-guest-memory.py <log de la ejecución>`.

Lo esperado: menos pérdida por inicio de Alan Wake que 0.42-0.65 GB, ningún PWFAULT después de una liberación, el
juego siguiente inicia y dibuja, y tiempos de cuadro no más lentos que en 04.29 en Alan Wake.

## Bloques pequeños que el runtime de C hizo a través de sí mismo (ejecuciones de 04.30)

`tools/check-guest-memory.py` sobre `reports/wine-hardware-w303/physical/20261119T173323Z/` (04.30, con el cambio
anterior):

| Ejecución | Programa, final | Perdido | Bloques pequeños del invitado | Liberados | Mayor retenido |
| --- | --- | --- | --- | --- | --- |
| run-0261 #1 | Alan Wake, terminado | 0.58 GB | 206 MB | 127 MB | 74 MB "ucrtbase.dll via ucrtbase.dll" |
| run-0261 #2 | Alan Wake, terminado | 0.21 GB | 186 MB | 124 MB | 59 MB "ucrtbase.dll via ucrtbase.dll" |
| run-0258 #1 | PES 2013, fallo (c0000005) | 0.49 GB | ninguno etiquetado | - | - |
| run-0258 #2 | PES 2013, terminado | 0.36 GB | ninguno etiquetado | - | - |

La pérdida por inicio de Alan Wake pasó de 0.78 GB (04.27) y 0.64/0.42 GB (04.29) a 0.58/0.21 GB. La memoria
flexible del primer inicio (0.22 GB) y la mayor parte de su memoria directa "other" (0.18 GB) no vuelven en el segundo
inicio (0.00 y 0.05 GB), así que se toman una vez. El heap de msacm32.dll es el propio de msacm32: se crea en el primer
invitado que carga msacm32 y se conserva mientras msacm32 sigue cargado; el segundo inicio no retiene ninguno. Los 1-4
MB de bloques grandes retenidos como "ucrtbase.dll via ucrtbase.dll" no crecen de un inicio al siguiente.

Lo que queda por inicio son sobre todo los bloques pequeños retenidos como "ucrtbase.dll via ucrtbase.dll". El runtime
de C los hizo a través de sí mismo: `_aligned_malloc` llama a `_aligned_offset_malloc`, que llama a `malloc`, y
`_strdup` y `realloc` también llaman a `malloc`. El marco de arriba del que llamó vuelve a ser el runtime de C, así
que ni "código ausente" ni la regla de wined3d vieron el código que pidió el bloque.

Cambio (`tools/build-guest-hw.py`):

- ntdll, i386: un sitio de bloques pequeños también registra los tres marcos de arriba del marco que ya tenía. Wine
  compila sus módulos PE i386 con punteros de marco, así que los marcos dentro del runtime de C son exactos.
- kernelbase: cuando el que llamó es un runtime de C y el marco de arriba también, el marco que cuenta es el primero
  de los tres de arriba que no es de un runtime de C. "Código ausente", la regla de wined3d y las líneas `kept` lo
  usan, así que lo que queda se nombra por el módulo que lo pidió.
- Los bloques grandes no cambian.

Verificación: solo compilación para la consola; `heap.c` de ntdll y `process.c` de kernelbase compilan para i386 y
x86_64 con las mismas advertencias que sin el cambio. En el host, ntdll se reenlazó con el `heap.c` generado en una
copia privada de la build de Wine del host, y la prueba de heap i386 volvió a pasar (cuentas de sitios, liberación,
`HeapValidate`, estrés de 4 hilos). Una parte nueva asigna a través de `_aligned_malloc`, `realloc(NULL)`, `malloc`,
`calloc` y `_strdup` de ucrtbase, y aplica la regla de kernelbase a los sitios listados: los 100 bloques llegaron al
marco del programa de prueba. El ucrtbase del host necesitó el tercer marco para `_aligned_malloc` (`malloc`,
`_aligned_offset_malloc`, `_aligned_malloc`). El código de liberación de kernelbase no se ejecutó en el host.

Sin cambiar: PES 2013 no tuvo ningún bloque pequeño etiquetado, pero el heap de su proceso creció 55 MB por inicio
(59 MB comprometidos, luego 114 MB). Esos bloques vienen de hilos que no son de ningún invitado, o de asignaciones que
no se etiquetan, y hay que mirarlos aparte.

Prueba en consola (necesita la aprobación del usuario), con una build que contenga este cambio:

1. Iniciar Alan Wake (wined3d + OpenGL), jugar un poco y cerrarlo desde el overlay. Hacerlo dos veces.
2. Iniciar PES 2013 y cerrarlo desde el overlay.
3. Iniciar Portal 2, salir desde su menú, e iniciarlo otra vez.
4. Iniciar WFM y el Bloc de notas, cerrarlos, y comprobar que el escritorio y la barra de tareas responden.
5. Ejecutar `python3 -I tools/check-guest-memory.py <log de la ejecución>`.

Lo esperado: las líneas `kept` "ucrtbase.dll via ucrtbase.dll" desaparecen o son pequeñas. Sus bloques se liberan (los
de wined3d, o de código ausente), o se retienen bajo el módulo que los pidió, por ejemplo libgallium_wgl.dll. El
segundo inicio de Alan Wake pierde menos de 0.21 GB. Ningún PWFAULT después de una liberación, el juego siguiente
inicia y dibuja, y los tiempos de cuadro no son peores que en 04.30.

## Relacionado: una carga fallida de invitado dejaba su base ocupada

`reports/pop-phase-b/physical/20261113T192438Z/run-0121.log`: el `settings.exe` de PES 2014, un EXE .NET solo IL, se
cargó en 0x400000 y falló con `mscoree.dll not found` (c0000135). Su inicio siguiente registró
`image_not_at_base preferred=0x400000 size=0x156000 status=0xc0000018 occupied=0x400000+0x156000`, que es su propia
imagen. Cuando el `build_module` de Wine no puede resolver las importaciones, saca el módulo de las listas del
cargador pero pone `*module` a NULL, así que `load_native_dll` no desmapea la vista. Un proceso que falla normalmente
termina, por eso upstream deja la vista. Un EXE invitado dentro del proceso de explorer mantenía su base fija ocupada
hasta que OrbisDesk terminaba. La revisión de ntdll en `tools/build-guest-hw.py` ahora desmapea la vista de un EXE
invitado cuyas importaciones fallan y registra `PWGUEST load_failed unmap`. El modref sigue reservado, como lo deja
upstream.

El otro caso informado, `vampire.exe` en `run-0164.log` (líneas 503-505), no es una fuga. `PATCH 1.2.exe` seguía
ejecutándose en 0x400000 (`live=1`; su `exits status 1607` aparece en la línea 531), y el relanzamiento `base_taken`
existente lo resolvió. `leftovers=1` en `PWGUEST own_modules` es la marca del barrido previo a cada inicio, no un
recuento.

## Verificación y lo que falta

- Comprobaciones de solo compilación en una raíz aislada: el `vulkan.c` de win32u con todas las revisiones aplicadas,
  compilado con la receta de Orbis, da las mismas tres advertencias que el generador confirmado, y las dos tablas de
  llamadas son símbolos globales. El `kernelbase/process.c` y el `ntdll/loader.c` de los invitados compilan para x86_64
  e i386 con las mismas advertencias que antes.
- Cambio de run-0178, también solo compilación: el parche de Mesa se aplica dos veces a una copia del frontend WGL
  (la segunda no cambia nada). `stw_context.c` y `stw_device.c` compilan con los comandos i386 y x86_64 de la receta
  sin advertencias, y exportan `pw_wgl_release_screen`. Las unidades de kernelbase y win32u dan las mismas
  advertencias que antes de este cambio.
- Sonda de run-0185, también solo compilación, a partir de los generadores para los que se escribió: el `vulkan.c` de
  win32u da las mismas advertencias que antes de ella, y deja `pw_vm_direct_bytes`, `pw_wine_memory_info` y
  `sceKernelGetDirectMemorySize` para el enlace final. `pw_vm_direct_bytes` se compiló aparte con las opciones de la
  consola, no como parte de todo `virtual.c`. La unidad de kernelbase da las mismas advertencias que antes de ella,
  para x86_64 e i386.
- Cambio de run-0190, también solo compilación, contra los generadores de 04.13 con las correcciones propias de esa
  build: el `vulkan.c` de win32u da las mismas advertencias que antes de él. Las unidades `process.c` y `memory.c` de
  kernelbase, para x86_64 e i386, dan las mismas advertencias que antes de él. El verificador lee run-0190 como
  antes, con los recuentos de heaps tomados dentro del mundo.
- Cambio de run-0203, también solo compilación, contra el generador de 04.15: las unidades `loader.c` y `heap.c` de
  ntdll y `process.c` y `memory.c` de kernelbase, para x86_64 e i386, dan las mismas advertencias que antes de él
  (ninguna en ntdll). El verificador lee run-0203 como antes.
- Cambio de run-0212, también solo compilación, contra el generador de 04.17: las unidades `heap.c` y `loader.c` de
  ntdll y `process.c` y `memory.c` de kernelbase, para x86_64 e i386, dan las mismas advertencias que antes de él. El
  verificador muestra run-0212 como antes, y lee las líneas nuevas de un log al que se añadieron a mano.
- Cambio de run-0215, también solo compilación, contra los generadores de 04.18 con el cambio de run-0212: el
  `vulkan.c` de win32u y la unidad `process.c` de kernelbase (x86_64 e i386) dan las mismas advertencias que antes de
  él, y el `ac_ps4_drm.c` de Crema con `patch-crema-release.py` (idempotente) la misma advertencia que sin él. El
  verificador muestra run-0212, run-0213 y run-0215 como antes, y lee las líneas nuevas de un log al que se añadieron
  a mano.
- Cambio de run-0219, también solo compilación, contra los generadores de 04.19: el `vulkan.c` de win32u da las mismas
  advertencias que antes de él, y el `ac_ps4_drm.c` de Crema con el nuevo `patch-crema-release.py` (idempotente) la
  misma advertencia que sin él. El verificador muestra run-0212 y run-0215 como antes, y run-0219 con 51 MB de Crema
  para su primera ejecución en vez de 246 MB. Lee las líneas nuevas de un log al que se añadieron a mano.
- No se generó ningún paquete y no se ejecutó nada en el emulador ni en la consola.
- Prueba en consola, con una build que contenga este cambio: iniciar el mismo juego DXVK, dejar que dibuje, cerrarlo
  desde el overlay y repetir tres veces. Después ejecutar
  `python3 -I tools/check-guest-memory.py <log de la ejecución> --max-loss-gb 0.25` y buscar las líneas
  `PWGUEST vulkan`.
