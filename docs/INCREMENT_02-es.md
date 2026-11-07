# Incremento 2: TEB de 32 bits y ejecución hostexec

[English](INCREMENT_02.md) | [Español](INCREMENT_02-es.md)

El dispatcher común posterior está implementado y documentado en [Incremento 3](INCREMENT_03-es.md). Este documento conserva la evidencia del incremento 2.

## Cambio realizado

El ELF enlaza ahora `pw_x86_hostexec.c` de la misma revisión fijada de prospero-win. Es la ruta real de ejecución de instrucciones IA-32 mediante stubs x86-64; no se sustituyeron instrucciones por resultados calculados por el diagnóstico. El backend PS4 publica sus stubs cambiando páginas de RW a RX.

`native/translator_runtime.c` añade cuatro pruebas y mantiene las pruebas anteriores. `tools/build.py` registra también hashes de fuentes y cabeceras propias en `out/build.json` para identificar los inputs del diagnóstico.

## Separación de TLS

Hay tres contextos distintos en la ejecución probada:

1. El runtime Windows del emulador usa su TLS anfitrión. La implementación de `RetrieveTcbPointer` en el fork obtiene el TCB de PS4 desde las ranuras TLS de Windows mediante GS.
2. El programa OpenOrbis usa el TCB de PS4. Su lectura nativa `fs:0` es tratada por los parches de instrucciones del emulador.
3. Las instrucciones IA-32 traducidas usan `PwX86State.fs_base` y `fs_bytes`. El TEB de prueba vive bajo 4 GiB, separado del TCB OpenOrbis y del TLS de Windows.

Las dos primeras afirmaciones describen el código del fork fijado, en `src/core/cpu_patches.cpp` y `src/core/tls.cpp`. No son una medida de hardware PS4.

La adaptación PS5 de Wine en el parche upstream `wine/patches/0500-ntdll-ps5-signal-context-and-segment-bases.patch` mantiene FS para libc y utiliza GS para el TEB de 64 bits. Aplicar eso al runtime Windows de shadPS4 requerirá virtualizar los accesos GS del invitado o demostrar otra ruta equivalente. No se cambió el GS anfitrión ni se implementó `sysarch` devolviendo un éxito ficticio. Como referencia ABI, el [código de FreeBSD](https://cgit.freebsd.org/src/tree/sys/amd64/amd64/sys_machdep.c?id=fdee312d0c97cf6d907eec0b96efd51bfc9a7567) implementa las operaciones de bases de segmentos; eso no prueba su comportamiento en una PS4.

## Pruebas nuevas

|Caso| Comportamiento comprobado |
|---|---|
| `translator-teb` | 64 ejecuciones; lee `fs:[0x18]`, `fs:[0x30]`, escribe `fs:[0x34]`; conserva flags, TCB nativo, `errno` y clave pthread |
| `translator-teb-threads` | Dos hilos con bases TEB y TCB nativos distintos, 64 ejecuciones por hilo sincronizadas por condición, estado independiente y liberación de reservas |
| Ambos casos TEB | Rechazan una escritura fuera del TEB aunque su página esté mapeada; rechazan desbordamiento base+offset antes del acceso |
| `hostexec-fp` | Ejecuta `LDMXCSR` y `ADDPS`, comprueba cuatro resultados exactos, EIP, flags, MXCSR invitado y conservación de CW/MXCSR anfitriones |
| `hostexec-cache` | Reutiliza el stub sin recompilar al repetir bytes; al cambiar el inmediato en el mismo PC compila de nuevo y obtiene el nuevo valor |

Los datos del TEB son un fixture propio mínimo. No constituyen un TEB creado por Wine ni validan `NtCurrentTeb`, SEH o la inicialización de DLL de Windows. La barrera de mutex/condición exige que ambos hilos establezcan su `errno` antes de comprobarlo en cada iteración; una falla aborta y despierta al otro hilo. La prueba FP usa operandos conocidos y mapeados: no valida la seguridad de la ruta hostexec frente a direcciones arbitrarias o instrucciones maliciosas. La prueba de caché cubre la comprobación de bytes de un stub hostexec, no la invalidación completa de bloques, enlaces o código modificado en ejecución.

Los casos `translator-fp-control` y `translator-fp-add` conservan su significado original: prueban exclusivamente el emisor de bloques y siguen bloqueados. Los casos hostexec muestran una ruta disponible para esas instrucciones, pero aún falta conectarla al dispatcher de WoW64 y comprobar sus transiciones de estado.

<a id="reproducir"></a>


## Reproducción

En WSL, desde la raíz del proyecto:

```bash
python3 tools/build.py --cc clang-14 --ld ld.lld-14
```

En PowerShell:

```powershell
$revision = (Get-Content fork.lock.json -Raw | ConvertFrom-Json).commit
./tools/run-probes.ps1 -Emulator build/shadPS4-win/shadps4.exe `
    -EmulatorKind fork -EmulatorCommit $revision `
    -BuildManifest build/shadPS4-win/build-manifest.json -TimeoutSeconds 25
```

El emulador conserva los tres parches del incremento anterior. Ningún parche nuevo del emulador es necesario para estas cuatro pruebas.

## Resultado preservado

| Entorno, mismo ELF | Aprobadas | Bloqueadas | Fallidas |Tiempos de salida|
|---|---|---|---|---|
|shadPS4 oficial v0.20.0| 13 | 12 | 1 | 0 |
| Fork `c6de833f6bec304b6f08c37520428ba2ed147a1a` | 22 | 4 | 0 | 0 |

Informes completos: [oficial](../reports/increment2-official-final/report.json), [fork](../reports/increment2-fork-final/report.json) y [comparación por caso](../reports/increment2-fork-final/comparison.json). Los resultados de los 22 casos anteriores se conservan en el fork. Las cuatro pruebas nuevas pasan allí y quedan bloqueadas en el oficial al publicar código RX. El fallo oficial de permisos efectivos sigue registrado, sin ocultarlo.

Los snapshots incluyen logs, hashes de los binarios y fuentes propias exactas en `inputs/`, contrastadas contra `build.json`. El informe del fork incluye también el manifiesto de compilación del emulador y los locks de sus parches y herramientas. La referencia anterior y los intentos intermedios se conservan separadamente; esta tabla usa los directorios terminados en `-final`.

Las cuatro pruebas nuevas pasan además en dos rondas adicionales con procesos nuevos: `reports/increment2-repeat-1` y `reports/increment2-repeat-2`. Cada una tiene cuatro aprobaciones, sin bloqueos ni timeouts. Esto da tres ejecuciones independientes por caso con el ELF final, incluyendo la matriz completa.

## Siguiente paso

Integrar el dispatcher de bloques y hostexec con estados de hilo propios, y probar una secuencia que pase de una ruta a otra sin perder flags, FP ni EIP. Después, separar la carga PE32 mínima de la inicialización Wine: un PE sin importaciones puede comprobar carga, relocaciones y entrada; el fixture completo `console32.exe` requiere además los servicios reales de Wine para archivo e hilos. La ruta nativa GS de Wine de 64 bits, sus señales y su ABI siguen pendientes.

Este incremento no ejecuta un EXE de Windows ni valida una consola PS4 real.
