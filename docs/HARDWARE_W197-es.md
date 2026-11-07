# W196 y W197: cerrar un juego Unity sin cerrar la app

[English](HARDWARE_W197.md) | [Español](HARDWARE_W197-es.md)

W196: APP_VER 02.95, base W195. W197: APP_VER 02.96, base W196. El resultado de W195 está en `docs/HARDWARE_W195.md`.

## Cambios

- **W196, `tools/build-guest-hw.py`, kernelbase `TerminateProcess`:** si un hilo invitado termina su propio proceso (`GetCurrentProcess()` o un handle con el mismo id), se llama a la salida del invitado, `ps4_guest_exit_process`, como con `ExitProcess`. El log deja `PS4 guest module … TerminateProcess( own process, N )`.
- **W197, `tools/build-guest-hw.py`, ntdll:**
  - `thread.c` tiene `ps4_fls_free_image`, que libera con `RtlFlsFree` las ranuras FLS cuya función de limpieza está dentro de una imagen.
  - `loader.c` la llama desde `free_modref` cuando el módulo es un EXE, es decir un invitado. El log deja `PWGUEST fls_free module=… freed=N`.
  - El motivo: un EXE con el CRT estático de MSVC registra una función FLS en su propia imagen (la limpieza de datos por hilo, con `FlsAlloc` obtenido por `GetProcAddress`). Windows nunca descarga el EXE de un proceso, así que nadie libera esas ranuras.
- **Manifiesto de W197:** `tools/build-explorer-hw.py` y `tools/build-win32u-ps4.py` cambiaron durante la build (diagnósticos de la sesión del navegador). El manifiesto de W197 registra sus sha nuevos, pero W197 usa las salidas anteriores. Esos diagnósticos entran en W198.

## Pruebas físicas

**W196:** reporte `reports/wine-hardware-w196/physical/20261104T114634Z/`. Respuesta: "cerré desde el menú del juego y de nuevo se cerró OrbisDesk".
- La intercepción anduvo: `TerminateProcess( own process, 0 )`, se terminaron 37 hilos y se descargó el EXE.
- Después, al terminar, el hilo 0040 ejecutó `00000001007C1FAC` dentro de la imagen ya descargada: el offset 0x1fac de `The Lost Forest.exe`, una función del CRT con `if (ptd != &__acrt_initial_ptd)`.
- Hubo un acceso inválido sin manejar y el título salió con `process_exit … status=0xc0000005`.

**W197:** reporte `reports/wine-hardware-w197/physical/20261104T120328Z/`. Respuesta: "ya no se cierra OrbisDesk, sólo el juego".
- `PWGUEST fls_free module=00000001007C0000 freed=2` para el juego. Los otros invitados que salieron dejan `freed=0`.
- El escritorio siguió y después se abrió Pale Moon dos veces.

## Pendiente

- W198: el mando como dispositivo HID, MangoHud con DXVK y los diagnósticos del congelamiento de Pale Moon como invitado.
