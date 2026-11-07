# Incremento 3: dispatcher común de CPU

[English](INCREMENT_03.md) | [Español](INCREMENT_03-es.md)

La carga y ejecución posterior de un PE32 propio se documenta en [Incremento 4](INCREMENT_04-es.md). Este documento conserva la evidencia previa.

## Implementación

`platform/ps4/pw_cpu_ps4.c` añade un contexto de ejecución con estado IA-32, motor de bloques, caché y hostexec de prospero-win. Es una capa propia PS4 sobre la misma revisión upstream fijada; no modifica esas fuentes.

Cada paso llama primero a `pw_x86_engine_step`. Sólo `PW_ERR_UNSUPPORTED` habilita el fallback de una instrucción: materializa flags diferidos, sincroniza el estado FP y obtiene los bytes en el EIP actual antes de llamar a hostexec. Los errores de memoria y de fuente se propagan. El código ya ejecutado por un bloque parcial no se repite al alcanzar una instrucción no soportada.

El contexto pertenece al hilo que lo crea. Las operaciones desde otro hilo devuelven `PW_ERR_STATE`, sin ejecutar ni destruir el contexto. El acceso directo al estado es para el propietario; no es una barrera de seguridad entre hilos C.

`pw_cpu_ps4_run` recibe una frontera de parada y un presupuesto de pasos. Agotar el presupuesto devuelve `PW_ERR_LIMIT`. La frontera sólo es un límite del llamador; no simula `ExitProcess`, una syscall ni un retorno de Wine. El límite cuenta pasos del dispatcher y no reemplaza un timeout externo de proceso.

El motor reserva 256 KiB de código y 64 entradas de caché; hostexec reserva 64 KiB. Chaining, reencoder y FP nativo del reencoder permanecen desactivados. El contexto grande también se reserva con el backend PS4. Así su liberación no depende de la ruta de libc que invocaba el stub `madvise` en shadPS4. Ese bloqueo real se conserva en `reports/increment3-allocator-blocker`, aunque los cálculos del invitado ya produjeran los valores esperados en ese intento.

## Casos nuevos

|Caso| Validación |
|---|---|
| `dispatcher-mixed` | Ejecuta traductor → hostexec → traductor → hostexec → traductor, dos veces; verifica EIP en cada cruce, acarreo, flags, XMM, MXCSR, TEB y resultado 42 |
| `dispatcher-fault` | Rechaza una escritura por permisos de la tabla, conserva el dato y EIP, y registra cero intentos de fallback |
| `dispatcher-stops` | Un bucle agota exactamente tres pasos; HLT queda no soportado; una fuente fuera de rango devuelve `PW_ERR_NOT_FOUND` |
| `dispatcher-owner` | Un hilo ajeno no puede obtener estado, ejecutar, consultar estadísticas ni destruir; el propietario sigue ejecutando correctamente |

La secuencia mixta calcula CF=ZF=1 con aritmética entera; `LDMXCSR`, carga SSE y `ADDPS` deben conservar esos flags. `ADC` consume el acarreo y obtiene 42. Los cuatro resultados flotantes se escriben en memoria y se comparan con valores exactos. Se comprueba además que CW/MXCSR anfitriones se conservan. La segunda ejecución reutiliza tres bloques y dos stubs: seis ejecuciones de bloques, cuatro instrucciones hostexec, tres compilaciones de bloques y dos de stubs.

Todos los casos liberan sus reservas y comprueban que no quedan bytes comprometidos registrados por el backend.

<a id="reproducir"></a>


## Reproducción

```bash
python3 tools/build.py --cc clang-14 --ld ld.lld-14
```

```powershell
$revision = (Get-Content fork.lock.json -Raw | ConvertFrom-Json).commit
./tools/run-probes.ps1 -Emulator build/shadPS4-win/shadps4.exe `
    -EmulatorKind fork -EmulatorCommit $revision `
    -BuildManifest build/shadPS4-win/build-manifest.json `
    -Cases dispatcher-mixed,dispatcher-fault,dispatcher-stops,dispatcher-owner `
    -TimeoutSeconds 25
```

Sin `-Cases`, el runner incluye estos casos en la matriz completa.

## Evidencia preservada

El [informe del fork](../reports/increment3-fork-final/report.json) registra 26 pruebas aprobadas y cuatro bloqueadas, sin fallos ni timeouts. Los resultados de los 26 casos del incremento anterior se conservan: no hay cambios de estado en esos casos. Los cuatro añadidos al dispatcher pasan.

Los bloqueos conservados son `sysarch`/FS/GS nativo, la importación POSIX de `pthread_key_delete` y los dos casos exclusivos del emisor para `LDMXCSR` y `ADDPS`. Estas últimas instrucciones sí se ejecutan por hostexec en la secuencia mixta; no se cambió la clasificación de sus pruebas del emisor aislado.

El fork conserva el commit `c6de833f6bec304b6f08c37520428ba2ed147a1a`; no se añadieron parches del emulador en este incremento. El snapshot contiene sus manifiestos, logs, hashes de los binarios y las 17 fuentes/cabeceras/herramientas propias identificadas por `build.json` en `inputs/`.

El [oficial](../reports/increment3-official-final/report.json), con el mismo ELF, registra 13 aprobadas, 16 bloqueadas y una fallida, sin timeouts. La [comparación por caso](../reports/increment3-fork-final/comparison.json) muestra 13 cambios de estado a aprobado en el fork. Los cuatro casos del dispatcher quedan bloqueados en el oficial al publicar código RX.

Las cuatro pruebas nuevas pasan en tres ejecuciones independientes con el mismo ELF: `reports/increment3-smoke`, la matriz completa y `reports/increment3-repeat`. No invocan stubs y cada proceso termina con código 0.

## Límites y siguiente paso

La fuente del motor debe permanecer mapeada e inmutable durante la vida del contexto. No se ha conectado la invalidación de código ni el reinicio de cachés por agotamiento: esos límites se devuelven al llamador. La ruta hostexec conserva la restricción del incremento anterior: operandos de memoria confiables, sin conversión general de fallos anfitriones a excepciones Windows. No debe usarse como ejecutor de programas arbitrarios en este estado.

El siguiente paso es un cargador PE32 mínimo: validar cabeceras y secciones, aplicar relocaciones y ejecutar la entrada de un EXE propio sin importaciones. Las importaciones reales, inicialización de DLL, archivos e hilos de Win32 necesitan la integración de Wine posterior. Este dispatcher no incluye Wine ni demuestra todavía ejecución de un EXE.
