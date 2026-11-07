# Incremento 18: console32.exe con el CRT de mingw, sin Wine

[English](INCREMENT_18.md) | [Español](INCREMENT_18-es.md)

**console32.exe, compilado con el CRT de mingw, se ejecuta completo en el fork Linux de shadPS4 sin Wine.** Arranca el runtime C (TLS del EXE, inicializadores, `__getmainargs`), corre `main`, crea un hilo y escribe `result.txt` con el mismo contenido que en Windows nativo. Sale por `exit(0)` después de ejecutar los handlers de `_onexit`. Todo esto se apoya en un msvcrt mínimo propio, no en el de Windows ni en el de Wine. Hardware: pendiente.

## Referencia de Windows y binario reproducible

`tools/build.py` enlazaba `console32.exe` y `gdi32.exe` con marca de tiempo, y por eso cada build cambiaba su hash. Ahora usan `-Wl,--no-insert-timestamp`, como `console32-bare.exe`: dos builds seguidos dan el mismo hash (`d9dbb672…`). `reports/increment18-windows-reference/` guarda la ejecución nativa de ese binario en este host (Windows 11 Pro 10.0.26200). Sale con 0 y produce un `result.txt` idéntico al del incremento 11.

## Loader y lifecycle

- `PW_PE32_MAX_SECTIONS` pasa de 16 a 32. El EXE tiene 17 secciones: 9 propias y 8 `.debug_*`, que se mapean como datos de sólo lectura.
- `pw_pe32_parse_tables` acepta un directorio TLS en el EXE, con las mismas validaciones que en una DLL.
- `pw_pe32_lifecycle_create` admite un EXE enlazado en la ranura 0, sólo por su TLS: le da índice 0 (como Windows), un bloque por hilo y sus callbacks TLS en process y thread attach/detach. `notify` nunca llama a su entry point.

## Módulos sintéticos

`pw_k32_ps4.c` separa el mecanismo de thunks de las tablas de exports (`pw_k32_internal.h`):

- Cada export declara convención (stdcall o cdecl), bytes de argumentos y si es variádico.
- Un export de datos apunta a una página RW del módulo, que se agrega a la tabla de regiones de cada hilo. Así funcionan `_iob` y `__initenv`.
- `pw_k32_call_guest` ejecuta código del invitado anidado dentro de una llamada. Es el mismo patrón `pw_guest_callback_enter` + `execute` que el incremento 17 usa para `DllMain`. `_initterm` y los handlers de `exit` lo usan.

**kernel32** pasa de 15 a 26 funciones:

- `Initialize`/`Enter`/`Leave`/`DeleteCriticalSection`: la propiedad se lleva en el host, con dueño, recursión y espera sobre la condición del proceso.
- `GetModuleHandleA`.
- `GetStartupInfoA`.
- `SetUnhandledExceptionFilter`: se registra, pero nada lo invoca porque no hay SEH.
- `Sleep`.
- `TlsGetValue`: lee las ranuras del TEB en `+0xE10`. `TlsAlloc` no está servido.
- `VirtualQuery`: responde desde la tabla de regiones lógicas.
- `VirtualProtect`: se rechaza con traza. La lista de pseudo-relocaciones de mingw está vacía en este EXE, así que el CRT no lo llama.

**msvcrt** (`platform/ps4/pw_msvcrt_ps4.c`, 25 exportaciones):

- Heap invitado de 1 MiB en `0x3c000000`, con metadatos de bloques en el host: `malloc`, `calloc`, `free`.
- `memcpy`, `strlen` y `strncmp` sobre memoria validada. Un puntero inaccesible es una falla del invitado (`PW_ERR_VM`), como lo sería un access violation en Windows.
- Arranque del CRT: `__getmainargs`, `__p__fmode`, `__p__commode`, `__p__acmdln`, `__set_app_type`, `__setusermatherr`, `__lconv_init`, `_initterm` y `__initenv`.
- Salida: `_onexit`, `exit`, `_cexit`, `abort` y `_amsg_exit`.
- `signal` registra el handler; nunca entrega una señal.
- `fwrite`, `fprintf` y `vfprintf` sólo escriben en stdout o stderr, como líneas `PWCRT` de la traza. El formato se limita a `%s %d %i %u %x %X %p %c %%`; el resto se rechaza con -1.

## Traductor

El CRT llama a `_fpreset`, que es un `FNINIT` (`DB E3`). El traductor de bloques de upstream emula bastante x87, pero no esa instrucción, y la ruta hostexec no la admite. `platform/ps4/pw_cpu_ps4.c` la resuelve en su fallback sobre el estado FP del invitado, ya sincronizado, sin tocar el FP del host ni las fuentes de upstream: restaura la palabra de control 0x037F, limpia status, punteros y excepciones pendientes, y marca todos los registros como vacíos. Lo cuenta en `PwPs4CpuStats.x87_resets`. `rep stos` y `lock cmpxchg` ya los soportaba el traductor.

## Resultado en el fork

El caso `console32` exige:

- `result.txt` idéntico a Windows y salida 0;
- ningún rechazo, handle sin cerrar ni falla de hilo;
- 3 inicializadores y 2 handlers de `_onexit` ejecutados;
- 8 notificaciones TLS del EXE: dos callbacks de mingw por cada process attach, thread attach, thread detach y process detach;
- exactamente 2 bloques de heap vivos al salir: la copia de `argv` que hace el CRT de mingw y que nunca libera;
- ninguna reserva de memoria viva al final.

`GetModuleHandleA` con nombre devuelve `ERROR_MOD_NOT_FOUND`. Es la búsqueda de la DLL de libgcc que hace mingw para registrar frames; con `-static-libgcc` también falla en Windows. `check-increment18.py` fija la secuencia completa de las llamadas visibles desde el host, así que cualquier cambio de camino en el CRT hace fallar el verificador.

| Entorno, mismo ELF |consola32| Motivo |
|---|---|---|
|Presión Linux `bf96b33`|**passed**| `result.txt` igual a Windows, salida 0, sin stubs ni rechazos |
|shadPS4 oficial Linux v0.20.0|bloqueado| El invitado pasa; `process.cpp:312 exit: Unreachable code!` y timeout, como en los incrementos 16 y 17 |
|shadPS4 oficial Windows v0.20.0|bloqueado| `address_space.cpp:603 Protect: Unreachable code!` al publicar el primer bloque RX |

Cambiaron el loader, el lifecycle y el fallback de la CPU, así que `check-increment18.py` repite en el fork todos los casos PE de los incrementos 4 a 7 (`pe-*`, 20 casos), `console-bare`, `lifecycle-host` y las ocho regresiones de siempre. Todos pasan. No se agregó ningún parche al emulador.

### Hallazgo aparte: dispatcher-mixed en el fork Linux

Agregué `dispatcher-mixed` como regresión extra y falla en el fork Linux, con `steps=10 blocks=6 host=4`. Repetí el caso con el ELF archivado del incremento 17, anterior a todos los cambios de este incremento, y falla con la misma línea de detalle. No es una regresión del 18: el caso se validó en el fork de Windows durante el incremento 3 y nunca había formado parte de los checks de Linux. Queda fuera de `check-increment18.py` y pendiente de investigar por separado.

## Reproducción y evidencia

```sh
python3 tools/build.py --with-wine-platform
python3 tools/run-linux-wine.py --fork --baseline --case console32
python3 tools/check-increment18.py
python3 tools/check-increment18.py --verify-only
```

```powershell
./tools/run-probes.ps1 -Cases console32 -TimeoutSeconds 25
```

`reports/increment18/report.json` indexa las corridas, la secuencia de llamadas, la salida `PWCRT` y el detalle del caso. El informe oficial de Windows, generado con el ELF final, está en `reports/runs/20261030T211159115Z/`. Hardware: pendiente.

## Próximo hito

Retomar la pista Wine. Los incrementos 16 a 18 dejan probadas las piezas que necesita un proveedor WoW64:

- el traductor como CPU de 32 bits;
- la frontera de thunks hacia el host;
- los callbacks anidados;
- el TEB y el TLS por hilo.

El orden propuesto:

1. Montar el prefijo empaquetado del incremento 15 en `/data/wine-prefix` y no lanzar wineboot cuando ya está inicializado.
2. GS por hilo en el runtime PS4.
3. Un proveedor WoW64 (`BTCpu*`) sobre `pw_cpu_ps4`, validado con `console32-bare.exe` contra el resultado que ya da sin Wine.
