# W195: señales a un hilo concreto (pthread_kill)

[English](HARDWARE_W195.md) | [Español](HARDWARE_W195-es.md)

APP_VER 02.94. Base W194. El resultado de W194 está en `docs/HARDWARE_W194.md`.

## Cambios

- **`platform/ps4/pw_wine_threads.c`** (nuevo, sólo en el enlace final): una tabla de id de hilo del kernel (`pthread_getthreadid_np`, el `unix_tid` que ntdll le da al servidor) a `pthread_t`.
  - Los hilos entran por `pthread_create`, enlazado con `--wrap=pthread_create`. El hilo principal entra por un constructor.
  - Salen por el destructor de una clave de pthread, antes de terminar.
  - `pw_wine_thread_kill` busca el hilo y llama a `pthread_kill` de libkernel con el número de señal de FreeBSD.
  - Registra `PWTHREAD kill` (los primeros 16 envíos y toda falla) y `PWTHREAD table_full`.
  - El diseño de la tabla es el de prospero-win (`wine/ps5/pw_wine_threads.c`, LGPL).
- **`platform/ps4/pw_wine_signals.c`:** se agrega `pw_wine_orbis_signal`, que traduce el número de señal del SDK al del kernel.
- **`tools/build-wine-delete-server.py`:** revisa `server/ptrace.c`. `send_thread_signal` manda SIGUSR1 (suspensión, contexto de otro hilo) por `pw_wine_thread_kill`. Las demás señales siguen sin mandarse, como en W064.
- **ntdll no cambia.** Wine ya bloquea SIGUSR1 durante cada llamada al servidor.
- **Espacio en disco:** el empaquetado falló dos veces porque C: estaba lleno. Con permiso del usuario se borraron `runtime/` y `app/` de `build/wine-hardware-w001` a `w180`, salvo W011, que usa `tools/run-wine-hardware.py`. Se liberaron 23 GB.

## Prueba física

Reporte: `reports/wine-hardware-w195/physical/20261104T112911Z/`

Respuesta del usuario: "TLF abrió ok, pero con F12 no pude activarle MangoHud. El joystick le mueve el puntero, el teclado anda ok y se oye tmb ok. Al cerrarlo se cerró todo OrbisDesk. palemooncopy.exe se congeló de nuevo".

<a id="the-lost-forest-run-0001log"></a>


### El bosque perdido (`run-0001.log`)

- **Señales:** las señales llegan a su hilo (`PWTHREAD kill tid=112470 sig=10/30 status=0`). Ya no aparece `thread_signal unavailable … sig=10`.
- **Imagen:** la cadena de presentación sale por DXVK (`PWDXGI swap chain through DXVK's dxgi`). Corre a unos 76 fps a 1280×720 (`PWVK present fps 75.8–79.4`).
- **Audio:** se oye (`PWAUDIO … peak=1250`).
- **Teclado:** anda.
- **Joystick:** mueve el puntero. Es la emulación de mouse del escritorio; el juego no recibe un mando.
- **MangoHud no aparece con F12:** DXVK toma `vkGetInstanceProcAddr` directo de `winevulkan.dll` (`Found vkGetInstanceProcAddr in winevulkan.dll`), así que no pasa por el cargador de Khronos, que es el que carga la capa de MangoHud.
- **Al salir se cierra toda la app:** Unity termina con `TerminateProcess` sobre su propio proceso. El servidor manda SIGQUIT a todos los hilos (`thread_signal unavailable thread=0024 sig=3`, …) y el título sale (`process_exit method=_exit status=0`). No aparece `PS4 guest module … exits`, así que no pasó por `ExitProcess`, que sí termina sólo al invitado.

### Pale Moon como invitado (`run-0002.log`)

- Navega (start.palemoon.org, palemoon.start.me) y después el hilo de explorer deja de responder (`heartbeat_age_ms` sube).
- No hay señales a hilos en esta corrida, así que es otra causa.
- El log termina unos 35 s después. Wine informa una sección crítica trabada recién a los 60 s, así que conviene esperar más en la próxima prueba.

## Pendiente

- W196: `TerminateProcess` del propio proceso desde un invitado termina sólo al invitado.
- MangoHud con DXVK (o el HUD propio de DXVK).
- El mando como mando para juegos (XInput sobre `scePad`), no como mouse.
- Pale Moon como invitado: repetir esperando al menos 2 minutos.
- Windows.Gaming.Input no ve el mando en `joy.cpl`: sus listas quedan vacías. Depende de los avisos de llegada de dispositivos, que no corren en este modelo de un proceso.
