# W136: entrada de señales para código de 32 bits nativo (fase 5A, paso 1)

[English](HARDWARE_W136.md) | [Español](HARDWARE_W136-es.md)

APP_VER 02.35. Base W135 (la PS4 ejecuta código de 32 bits en modo compatibilidad).

## Por qué este paso va solo

El `wow64native` de prospero-win corre el código de 32 bits con la base FS apuntando al TEB de 32 bits. Si llega una señal en ese momento, el envoltorio de señales de libkernel busca su hilo por `%fs` y lee basura. Por eso la parche 0883 registra los handlers directamente con el kernel y pone la base FS del host antes de cualquier código C.

Esta build instala esa entrada **sin** ejecutar todavía código de 32 bits nativo: el programa de 32 bits sigue en el traductor (`wowprospero`). Así se prueba sola la parte que cambia cómo llegan todas las señales del proceso.

## Cambios

- `platform/ps4/pw_wine_signals.c` (adaptado de la parche 0883):
  - `pw_wine_native_signals_enable`:
    - toma la instrucción `syscall` del stub `getppid` de libkernel (+10);
    - la prueba ejecutando `getpid`/`getppid` cruzados;
    - con un registro crudo de SIGUSR2 comprueba que el marco del kernel tiene el MXCSR del hilo en uc+320+24 y la base FS en uc+1152.
    - Sólo si todo coincide, los registros siguientes van crudos (`sigaction` es la llamada al sistema 416).
  - `pw_native_signal_entry` (asm), la entrada que el kernel llama:
    - si está en la pila de señales de Wine, lee la base FS del host del TEB (0x348);
    - si la FS actual es otra, pone la del host y llama al handler de siempre;
    - al volver repone la FS de entrada, salvo que el handler haya mandado un hilo de 32 bits (CS 0x33) a código de 64 bits (despacho de excepciones de Wine): ese sigue con la del host, en el registro y en el marco.
    - Sin FS del host conocida y con CS 0x33 termina el proceso (`exit(127)` por la misma syscall), en vez de correr C con la FS del invitado.
- `tools/build-signal-ps4.py` (nuevo) compila `signal_x86_64.c` de ntdll con:
  - un campo `pw_host_fs` en `amd64_thread_data` (TEB+0x348), que cada hilo llena en `init_syscall_frame` con `sysarch(128)`. `pthread_teb` sigue en NULL: con un valor, nuestro despachador haría su propia llamada `sysarch`.
  - `PW_NATIVE_SIGNALS=1` activa el modo crudo antes de registrar los handlers. Se loguea `PWNATIVE signals raw=<0|1> ...`.
  - `__wine_prospero_native_wow64_caps(1)` devuelve `1|2` (entradas crudas, FS del host antes de C). **No** devuelve 4: el contexto de Wine en Orbis no guarda xstate (`XState_sig` es NULL), así que las excepciones pierden la mitad alta de los YMM. Se loguea `PWNATIVE caps=`.
- `native/wine_hardware.c`: un programa PE32 se lanza con `PW_NATIVE_SIGNALS=1`. Explorer y los programas de 64 bits no cambian.

## Qué se espera en el log del programa de 32 bits

- `PWNATIVE signals raw=1 syscall=0x... hits=1 mxcsr=X/X fsbase=Y/Y`
- `PWNATIVE caps=3 cs64=43 ss64=...` (0x43 es el CS medido en W135)
- El programa anda como en W134/W135, ahora con las señales por la entrada nueva.

Si `raw=0`, el detalle dice qué falló y el proceso sigue con el envoltorio de libkernel.

## Prueba física: 20261103T040420Z

El usuario confirmó que gui-window32 y SuperMarioKart anduvieron igual. En los dos logs de 32 bits:

    PWNATIVE signals raw=1 syscall=0x80000087a hits=1 mxcsr=0xbfe1/0xbfe1 fsbase=0x880dad720/0x880dad720
    PWNATIVE caps=3 cs64=43 ss64=3b
    wow64: CPU wowprospero.dll from WINE_PS4_WOW64_CPU

- La instrucción `syscall` del stub de `getppid` de libkernel ejecuta otras llamadas.
- El registro crudo de `sigaction` funciona.
- El marco de señal tiene el MXCSR en uc+320+24 y la base FS en uc+1152, como en PS5.
- Los selectores de 64 bits son CS 0x43 y SS 0x3b, los mismos que usa `wow64native` en PS5.
- gui-window32 terminó con `process_exit status=0`.

Siguiente paso (W137): `wow64native.dll` y su lado Unix, con caída al traductor si no arranca.
