# Wxxx: Pale Moon como invitado congela el escritorio (diagnóstico, borrador)

[English](HARDWARE_Wxxx-palemoon-invitado-borrador.md) | [Español](HARDWARE_Wxxx-palemoon-invitado-borrador-es.md)

Borrador de la sesión lateral del navegador. La sesión principal asigna el número y lo une al `HARDWARE_Wxxx.md` que toque. Nada de esto se probó en la consola.

## Qué se sabe

Reportes: W192 `reports/wine-hardware-w192/physical/20261104T101756Z/run-0003.log` (desde la línea 3912) y W195 `reports/wine-hardware-w195/physical/20261104T112911Z/run-0002.log` (desde la 1656).

- **Cómo arranca:** `C:\Program Files\Pale Moon\palemooncopy.exe` no tiene la marca `OrbisRunsAlone`. Por eso abre como invitado dentro de explorer (`PWGUEST load_begin`, hilo principal `0040` en W195).
- **No usa nuestro perfil:**
  - escribe en `…\Pale Moon\Profiles\e3nzp9am.default` (líneas `PWDELETE` de W195);
  - resuelve nombres con `family=0` (IPv4 e IPv6), mientras que nuestro `user.js` pide sólo IPv4.
  
  Tampoco le llegan los `DllOverrides` de `AppDefaults\palemoon.exe` (`d3d11=""`, `d3d10core=""`), porque esa clave usa el nombre del ejecutable. Así que usa la aceleración por hardware: DXVK crea un dispositivo D3D11 en las dos corridas.
- **Lo que registra DXVK:**
  - `Failed to create shared resource: VK_KHR_EXTERNAL_MEMORY_WIN32 not supported`;
  - `D3D11DXGIKeyedMutex::AcquireSync: Not supported`;
  - no aparece ningún `PWVK show_frame` de Pale Moon: su compositor no llegó a presentar con Vulkan.
- **El momento del cuelgue:** el hilo de interfaz de explorer (`0024`) deja de latir:
  - W195: a los ~107 s, mientras se resuelven `palemoon.start.me`, `static.cloudflareinsights.com` y `c.start.me`;
  - W192: justo después de resolver `www.palemoon.org` y `start.palemoon.org`.
  
  Su última marca es `stage=36`, que está después de `sync_taskbar_buttons()`: el hilo volvió a su bucle de mensajes y se trabó en algo sin marca.
- **Después:** ningún hilo registra nada más. Sólo siguen:
  - el observador de explorer (`0030`), que todavía obtiene `GetGUIThreadInfo` y `GetForegroundWindow` del servidor;
  - el lanzador (`input_event`).
- **No es una sección crítica de Win32:** W192 esperó 139 s y no apareció el aviso de 60 s de `RtlpWaitForCriticalSection`.
- **No parece un cuelgue de la GPU:**
  - el compositor (`native/hw_sink_gpu/hw_sink_gpu.c`) espera su fence con 1 s de límite y avisaría `PWSINK gpu_failed`;
  - RADV (`ac_ps4_drm.c`, `ps4_wait_seq`) avisaría `GPU hang?` después de 2 s.
  
  Ninguno de los dos aparece.
- **No es el monitor de cuelgues de W184/W185:** no hay líneas `PWTHREAD`.

**Hipótesis, sin confirmar:** un hilo de Pale Moon queda trabado mientras tiene un lock de la parte Unix que el escritorio también usa. Los candidatos:
- el lock USER de win32u (`user_mutex`);
- el `screen_lock` de ps5drv;
- el lock del compositor (`pw_wine_sink_ps4.c`, que se toma con `screen_lock` tomado).

Un lock de pthread no da aviso al esperar, y eso coincide con el silencio. Los logs no alcanzan para saber cuál es ni qué hace el dueño.

## Prueba sin construir nada (W195 o W196)

Separa la aceleración por hardware de la ejecución como invitado:

1. Abrir `palemooncopy.exe`.
2. Escribir `about:config` en la barra de direcciones y poner `layers.acceleration.enabled` en `false`. Es la misma preferencia que usa nuestro `user.js`. En las opciones de Pale Moon (en inglés) es la casilla "Use hardware acceleration when available".
3. Cerrar Pale Moon y volver a abrir `palemooncopy.exe`.
4. Navegar a dos o tres sitios y esperar 2 minutos.

**Qué buscar en el log:**
- si ya no aparece `Creating resource descriptor heap` ni `D3D11` de DXVK;
- si `heartbeat_age_ms` sigue en ~230.

**Cómo leer el resultado:**
- Si no se congela, la causa está en el camino D3D11/DXVK dentro del proceso de explorer.
- Si se congela igual, no tiene que ver con la GPU.

## Cambio (diagnóstico)

Sólo agrega trazas: nada recupera el cuelgue, acorta una espera ni se salta un lock. Los cambios están en `tools/build-explorer-hw.py` y `tools/build-win32u-ps4.py`.

- **explorer (`PWDUMP`):** el observador de explorer recorre todos los hilos del proceso, Pale Moon incluido. Lo hace una vez cuando el latido del hilo de interfaz tiene 8 s y otra a los 70 s. Para cada hilo registra:
  - su dirección de inicio (módulo+desplazamiento);
  - sus registros;
  - hasta 20 marcos del lado Windows.
  
  Un hilo trabado dentro de una llamada Unix muestra la llamada que hizo (`win32u`, `ntdll`, `winevulkan`). Cada hilo se suspende sólo para `GetThreadContext` (depende de las señales por hilo de W195). El recorrido de la pila se queda dentro de los límites de la pila del hilo y en código de módulos cargados. La primera línea, `PWDUMP begin`, muestra el dueño del loader lock.
- **win32u (`PWLOCK`):** si un hilo espera más de 5 s el lock USER o el `screen_lock` de ps5drv, se registra con el hilo dueño (`PWLOCK wait lock=… tid=… owner=… waited_s=…`). Cuando lo consigue, se registra `PWLOCK got`. La espera sigue sin límite, como antes.
  
  Si `pthread_mutex_timedlock` no funciona en la consola, queda una línea `PWLOCK timedlock … rc=…` y los locks vuelven a la espera normal sin aviso.

## Construcción

1. `tools/build-explorer-hw.py` y `tools/build-win32u-ps4.py` ya tienen los cambios (aplicados con `diag-freeze.patch.py`).
2. Correr esos dos builders y después `tools/link-wine-boot.py` y `tools/build-wine-hardware.py`, como en cualquier W que toque explorer y win32u.

## Prueba física

1. Abrir `palemooncopy.exe` (con la aceleración como venga) y navegar hasta que se congele.
2. Esperar 2 minutos antes de bajar el log.
3. **Qué buscar en el log:**
   - `PWLOCK wait …`: qué lock y qué hilo lo tiene;
   - las dos tandas `PWDUMP` (a los 8 s y a los 70 s): qué hace el hilo dueño, qué hace `0024` y en qué llamada está cada hilo de Pale Moon;
   - si una tanda se corta después de una línea `start` sin `rip`, ese hilo no entregó su contexto.

## No verificado

- Nada se probó en la consola.
- Los dos cambios se compilaron sólo con `-fsyntax-only`, con la receta de cada builder, sobre copias de los overlays actuales; los builders no se corrieron.
- No se comprobó en la consola que `pthread_mutex_timedlock` del SDK funcione. Si no funciona, `PWLOCK` lo avisa una vez y no informa más esperas.
- No se sabe si `GetThreadContext` responde para un hilo trabado dentro de un lock de pthread. Si no responde, la tanda `PWDUMP` se detiene en ese hilo.
