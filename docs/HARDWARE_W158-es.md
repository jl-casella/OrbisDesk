# W158: dlopen sin estado por hilo de musl (cuelgues después de varios programas)

[English](HARDWARE_W158.md) | [Español](HARDWARE_W158-es.md)

APP_VER 02.57. Base W157.

## Problema

Dos fallas de W155 que dependían de qué programas habían corrido antes:
- después de cerrar glxgears, abrir WFM cerró la app sin dejar rastro (`20261103T141256Z`);
- después de WFM y dos juegos DOS (`doshost`), abrir glxgears la colgó (`20261103T143528Z/run-0005.log`).

En la segunda:
- el hilo de glxgears falló dentro de una llamada al lado Unix: `handle_syscall_fault code=c0000005 addr=0xf8dcae`, con registros llenos de `0xafafafaf`;
- `0xf8dcae` cae en datos de solo lectura del ELF, así que fue un salto a un puntero inválido;
- la llamada era la inicialización de `dnsapi` (`DllMain` → `__wine_init_unix_call`, seguida de `No libresolv support`).
- En las corridas que andan, esa misma llamada termina con `failed to load "…/dnsapi.so": Dynamic loading not supported`.

## Causa

`dnsapi` no está en la tabla de bibliotecas Unix estáticas (`platform/ps4/pw_wine_unixlibs.c`), así que ntdll (`load_builtin_unixlib`) hace `dlopen` de `dnsapi.so`.

La libc del SDK es musl. Su `dlopen` estático (`stub_dlopen`) falla, como debe, y guarda el error por hilo en `__dl_vseterr`. Desensamblado de W155:
- lee la estructura de hilo de musl en `%fs:0`;
- hace `free` del puntero en el offset `0xa8`;
- guarda ahí un mensaje nuevo con `malloc`;
- pone un bit en el offset `0x46`.

`dlerror` lee y limpia esos mismos campos.

En la PS4, `%fs:0` es el bloque de hilo del sistema, no el de musl. Cada `dlopen` o `dlsym` que fallaba liberaba la palabra que hubiera en ese offset y escribía en el bloque del hilo. Wine hace uno por cada DLL integrada con lado Unix que no está en la tabla, en cada hilo que la carga primero.

El daño depende de qué había en esa memoria, por eso la falla dependía de qué programas corrieron antes. Que este sea el mecanismo de los dos casos de W155 es una deducción: el primero no dejó rastro.

## Cambio

- `platform/ps4/pw_wine_dl.c`: `dlopen`, `dlsym`, `dlerror` y `dlclose` propios.
  - Fallan igual que los de musl: no hay carga dinámica; `dlerror` devuelve "Dynamic loading not supported".
  - No tocan `%fs` ni guardan estado por hilo.
- `tools/build-wine-hardware.py` los compila y los pone en el link antes de las bibliotecas, así que los de musl (y `__dl_vseterr`) no entran al ELF. El script de build lo verifica con `llvm-nm`.

## Qué se espera

- En el log siguen apareciendo `failed to load … Dynamic loading not supported` y `No libresolv support`, que son normales.
- Sin cuelgues al abrir glxgears después de WFM y juegos DOS, ni cierres al abrir WFM después de glxgears.

## Prueba física

Se probó dentro de W159 (`HARDWARE_W159.md`): la secuencia de W155 (WFM, juego DOS, glxgears, WFM) no falló.
