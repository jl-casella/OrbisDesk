# W184, parte de winecfg: Aceptar o Cancelar ya no cierran todo

[English](HARDWARE_W184-winecfg-borrador.md) | [Español](HARDWARE_W184-winecfg-borrador-es.md)

Borrador de la sesión de configuración de Wine. La sesión principal lo suma a `HARDWARE_W184.md`.

## Qué pasó en W183

En `run-0001.log` (`reports/wine-hardware-w183/physical/20261103T232154Z`; igual en `run-0002` y `run-0003`):

1. winecfg (invitado `0x100780000`, hilo `0040`) termina con `ExitProcess` y se descarga.
2. rundll32 (otro invitado, hilo `003c`, el que corre `winecfg.cpl`) descarga `winecfg.cpl` y llama a `exit()` al terminar su `main`.
3. Falla en `0x100782560`, dentro del winecfg ya descargado. El título termina con `0xc0000005`.

## La causa

- `0x100782560` es `winecfg.exe+0x2560`: `do_global_dtors`, del arranque del CRT de mingw.
- Al arrancar, winecfg la registra con `_crt_atexit` en ucrtbase, y ucrtbase guarda una **sola tabla de atexit para todo el proceso** (`MSVCRT_atexit_table`, `dlls/msvcrt/exit.c`).
- winecfg sale con `ExitProcess`, que no recorre esa tabla, como en Windows. La entrada queda, apuntando a una imagen que después se descarga.
- Cuando rundll32 termina, su `exit()` recorre la tabla del proceso entera, incluida la entrada de winecfg, y salta a memoria liberada.
- Es el mismo tipo de error que el filtro de excepciones de W114: algo del proceso que guarda una dirección de un invitado que ya no está.

Además, en `ps4_guest_launch` el hilo nuevo del invitado se crea desde el hilo que llama a `CreateProcess`. Si ese hilo es de otro invitado (rundll32), `CreateThread` le pone al hilo nuevo el invitado del que lo crea y lo suma a **su** lista de hilos. Por eso en W179 la salida de rundll32 terminaba el hilo de winecfg.

## Cambio

En `tools/build-guest-hw.py` (lo aplica `guest-exit-w184.patch.py`):

- **ucrtbase (`exit.c`):** cada invitado tiene su propia tabla de atexit, guardada en su `struct ps4_guest`, justo después del primer campo.
  - `atexit`, `_onexit` y `_crt_atexit`, llamados desde un hilo de un invitado, registran en la tabla de ese invitado. `exit()` desde un invitado recorre solo su tabla.
  - Fuera de los invitados (explorer) todo sigue igual, con la tabla del proceso.
  - Un invitado que sale con `ExitProcess` deja sus entradas sin correr, como en Windows, y no quedan en ninguna tabla que otro programa vaya a recorrer.
- **kernelbase (`ps4_guest_launch`):** mientras crea el hilo del invitado nuevo, el hilo que llama deja de estar marcado con su invitado. El hilo nuevo es solo del invitado nuevo.
- Compilado aparte (copia del builder con salida en el scratchpad): 23 revisiones; enlazan ntdll, ucrtbase y kernelbase. Las dos advertencias que salen son de código anterior (W060 y W105).

## Prueba

1. Panel de control → Configuración de Wine → Aceptar. Repetir con Cancelar.
2. Repetir desde Inicio → Ejecutar `winecfg`, que no pasa por rundll32.
3. En los dos casos, el escritorio sigue. En el log, después de `PS4 guest module … exits`, rundll32 sale sin `page fault`.
