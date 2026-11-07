# W184: memoria para vistas grandes y perfil de Pale Moon (fase 9), salida de invitados sin atexit ajenos (fase 7)

[English](HARDWARE_W184.md) | [Español](HARDWARE_W184-es.md)

APP_VER 02.83. Base W183. El resultado de W183 está en `docs/HARDWARE_W183.md`.

## Vistas grandes comprometidas desde el principio

`tools/build-audio-ps4.py`, `virtual.c`, `map_view`, sólo en Orbis:
- **Antes:** en W183, Pale Moon (corriendo solo) pidió 8 MiB de lectura/escritura (`size 0x810000, unix_prot 0x3`). La consola rechazó el `mmap` anónimo con `EINVAL`, y xul leyó `NULL+0x80`.
- **Ahora:** una vista nueva de 1 MiB o más que nace comprometida se reserva primero en el kernel (W182). Cuando se recorta el sobrante de alineación, recibe memoria directa en cero, como los compromisos grandes (W175/W176). Se libera con la vista (`unmap_area`).
- **Si falla:** si la memoria directa falla, el cambio de protección compromete memoria flexible sobre la reserva. Si eso también falla, la reserva devuelve `STATUS_NO_MEMORY` con `PWVM view … got no memory`, en lugar de una dirección sin memoria.
- Sólo cambia el camino de las vistas sin límites de dirección (programas de 64 bits); los de 32 bits siguen por `map_free_area`.

## Pale Moon: preferencias y D3D11 (fase 9, sesión del navegador)

### Qué pasó en W183

Reporte: `reports/wine-hardware-w183/physical/20261103T232154Z/`. El relanzamiento funciona: run-0004 y run-0006 relanzan, y run-0005 y run-0007 corren `palemoon.exe` como título. Pale Moon se cae a los 13 s más o menos y la app vuelve al escritorio.

- **run-0005 (primer arranque del perfil):**
  - El hilo principal carga `opengl32`, el `dxgi` builtin de Wine y después el `d3d11.dll` de DXVK (W124).
  - DXVK avisa `D3D11InternalCreateDevice: Adapter is not a DXVK adapter` y crea su propio dispositivo Vulkan. Después da `DxvkMemoryAllocator: Memory allocation failed` (4096 bytes, tipos de memoria 0,2,3,5, montones de 1024 y 2048 MiB casi vacíos).
  - Fallo de acceso en `7F8941618`: `d3d11.dll` (DXVK), desplazamiento `0xe1618`.
  - Después hay un breakpoint en `7FA464E69`: `xul.dll` de Pale Moon, desplazamiento `0x734e69` (el abort de Mozilla). Termina con `0x80000003`.
- **run-0007 (segundo arranque):**
  - Pale Moon borra `d3d11layers.guard` del perfil. Es su guarda contra fallos de D3D11, que quedó del fallo anterior, así que esta vez no usa D3D11.
  - Después, `map_view anon mmap error Invalid argument, size 0x810000, unix_prot 0x3`: una reserva de 8 MB de lectura y escritura que la consola rechazó.
  - `xul.dll` lee la dirección `0x80` en `7F9FD958E` (`xul.dll`, desplazamiento `0x2a958e`) y termina con `0xc0000005`.
  - Es un problema de memoria distinto del de D3D11. Pertenece al trabajo de la sesión principal en `virtual.c` (la reserva de 1 GB de W180 era sin permisos; esta es de 8 MB con lectura y escritura).

**Por qué Pale Moon creó un dispositivo D3D11.** El `user.js` de W177-W183 pedía `layers.acceleration.disabled`. Pale Moon 35 (UXP) no tiene esa preferencia. La suya es `layers.acceleration.enabled` (los nombres están en `xul.dll`). Tampoco existe `layers.prefer-d3d9`. Pale Moon ignoró las dos y dejó la composición por GPU encendida.

### Cambio

| Archivo | Qué hace |
|---|---|
| `fixtures/browser/palemoon-user.js` | `layers.acceleration.enabled=false` en lugar de `layers.acceleration.disabled`. Saca `layers.prefer-d3d9`. Agrega `webgl.disable-angle=true` (ANGLE también usa D3D11). Siguen `gfx.direct2d.disabled`, `webgl.disabled` y `media.hardware-video-decoding.enabled=false`. Todas esas preferencias están en `xul.dll`. |
| `tools/build-wine-hardware.py` (`user.reg`, pendiente del OK de la sesión principal) | `[Software\Wine\AppDefaults\palemoon.exe\DllOverrides]` `"d3d11"=""` y `"d3d10core"=""`: si algo de Pale Moon igual pide D3D11, la carga falla limpia y no llega a DXVK. `dxgi` sigue siendo el builtin (Pale Moon lo usa para leer el adaptador). `d3d9` no se toca: `xul.dll` lo importa de forma estática. |

El `user.js` es del build, así que la subida lo reemplaza. Lo que Pale Moon escribió en el perfil (`prefs.js`, guardas) queda.

### Para después: Vulkan en un título de 64 bits relanzado

En run-0005, DXVK no pudo reservar ni 4 KB de memoria Vulkan en un proceso propio de 64 bits. Los programas de 32 bits relanzados sí usan DXVK y wined3d sobre Vulkan. No se investigó en W184. Queda anotado para cuando Pale Moon (o un juego de 64 bits) use D3D11 en su propio proceso.

### Construcción (orden)

1. `python3 tools/build-wine-hardware.py` (copia el `user.js` nuevo y, con el OK, escribe el bloque `DllOverrides`)
2. `python3 -I tools/check-web-closure.py build/wine-hardware-w184/runtime`

### Prueba física

1. **Abrir Pale Moon:**
   - En el log no tiene que aparecer `d3d11.dll` cargado por Pale Moon ni ninguna línea de DXVK (`info:  DXVK: v2.7.1`).
   - Se espera la página local con `es5-ok`, `es2020-ok` y `canvas-ok`.
2. **Si vuelve `map_view anon mmap error Invalid argument`** (como en run-0007), el fallo es de memoria y no de gráficos: queda para el arreglo de `virtual.c`.
3. **Cerrar Pale Moon:** tiene que volver el escritorio.

### No verificado

- Nada se probó en la consola.
- No está confirmado que, con la composición por GPU apagada, Pale Moon 35 no cree igual un dispositivo D3D11 para otra cosa (lectura del adaptador, decodificación de imágenes). Para eso está el `DllOverrides`.

## Cierre de winecfg desde Control Panel (fase 7, sesión de accesos directos)

### Qué pasó en W183

En `run-0001.log` (`reports/wine-hardware-w183/physical/20261103T232154Z`; igual en `run-0002` y `run-0003`):

1. winecfg (invitado `0x100780000`, hilo `0040`) termina con `ExitProcess` y se descarga.
2. rundll32 (otro invitado, hilo `003c`, el que corre `winecfg.cpl`) descarga `winecfg.cpl` y llama a `exit()` al terminar su `main`.
3. Falla en `0x100782560`, dentro del winecfg ya descargado. El título termina con `0xc0000005`.

### La causa

- `0x100782560` es `winecfg.exe+0x2560`: `do_global_dtors`, del arranque del CRT de mingw.
- Al arrancar, winecfg la registra con `_crt_atexit` en ucrtbase, y ucrtbase guarda una **sola tabla de atexit para todo el proceso** (`MSVCRT_atexit_table`, `dlls/msvcrt/exit.c`).
- winecfg sale con `ExitProcess`, que no recorre esa tabla, como en Windows. La entrada queda, apuntando a una imagen que después se descarga.
- Cuando rundll32 termina, su `exit()` recorre la tabla del proceso entera, incluida la entrada de winecfg, y salta a memoria liberada.
- Es el mismo tipo de error que el filtro de excepciones de W114: algo del proceso que guarda una dirección de un invitado que ya no está.

Además, en `ps4_guest_launch` el hilo nuevo del invitado se crea desde el hilo que llama a `CreateProcess`. Si ese hilo es de otro invitado (rundll32), `CreateThread` le pone al hilo nuevo el invitado del que lo crea y lo suma a **su** lista de hilos. Por eso en W179 la salida de rundll32 terminaba el hilo de winecfg.

### Cambio

En `tools/build-guest-hw.py` (lo aplica `guest-exit-w184.patch.py`):

- **ucrtbase (`exit.c`):** cada invitado tiene su propia tabla de atexit, guardada en su `struct ps4_guest`, justo después del primer campo.
  - `atexit`, `_onexit` y `_crt_atexit`, llamados desde un hilo de un invitado, registran en la tabla de ese invitado. `exit()` desde un invitado recorre solo su tabla.
  - Fuera de los invitados (explorer) todo sigue igual, con la tabla del proceso.
  - Un invitado que sale con `ExitProcess` deja sus entradas sin correr, como en Windows, y no quedan en ninguna tabla que otro programa vaya a recorrer.
- **kernelbase (`ps4_guest_launch`):** mientras crea el hilo del invitado nuevo, el hilo que llama deja de estar marcado con su invitado. El hilo nuevo es solo del invitado nuevo.
- Compilado aparte (copia del builder con salida en el scratchpad): 23 revisiones; enlazan ntdll, ucrtbase y kernelbase. Las dos advertencias que salen son de código anterior (W060 y W105).

### Prueba

1. Panel de control → Configuración de Wine → Aceptar. Repetir con Cancelar.
2. Repetir desde Inicio → Ejecutar `winecfg`, que no pasa por rundll32.
3. En los dos casos, el escritorio sigue. En el log, después de `PS4 guest module … exits`, rundll32 sale sin `page fault`.

## Prueba física

Reporte: `reports/wine-hardware-w184/physical/20261103T234342Z/`. Respuesta del usuario: "Pale Moon anda".

- **Pale Moon** abre como título propio (aunque no navega: al escribir `google.com` o buscar en DuckDuckGo y apretar Enter no pasa nada, sin página de error ni aviso de desconexión; ver W185) (`run-0002`: `pe_machine … palemoon.exe`), sin `anon mmap error`, `PWVM view … got no memory`, `c0000005` ni breakpoint. La fase 9 llega a un navegador moderno funcionando en la consola.
- **winecfg:** Apply completa todos los pasos, `step=refresh` incluido (188 ms), dos veces en `run-0001`, y la app sigue después.
- `user.reg` de la consola tiene `AppDefaults\palemoon.exe` con `OrbisRunsAlone="Y"` y `DllOverrides` (`d3d10core`, `d3d11`).
