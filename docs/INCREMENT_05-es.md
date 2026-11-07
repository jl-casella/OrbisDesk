# Incremento 5: secciones PE de 4 KiB sobre páginas PS4 de 16 KiB

[English](INCREMENT_05.md) | [Español](INCREMENT_05-es.md)

La carga de DLL y resolución de imports posterior se documenta en [Incremento 6](INCREMENT_06-es.md). Este documento conserva la evidencia anterior.

## Cambio de plataforma

El cargador acepta ahora alineación de secciones de 4 KiB y conserva el soporte de 16 KiB. Valida `SizeOfImage` y los rangos lógicos usando esa alineación; la reserva anfitriona se redondea a páginas PS4. La relación entre alineación y cabeceras se contrastó con la [especificación PE](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format).

El mapper prepara un plan de páginas físicas. Cada página ocupada se compromete y se pone a cero una sola vez antes de copiar las secciones; así una sección no borra los bytes de otra que comparta página. Después aplica relocaciones y la unión de permisos de lectura/escritura necesarios en cada página física.

Los bytes IA-32 de la imagen se usan como datos de entrada al traductor: no se ejecutan directamente en modo x86-64. Por eso las páginas originales de imagen no reciben EXEC; el código anfitrión generado vive en las cachés JIT RX separadas. Esto también se aplica a las imágenes de 16 KiB. No hay páginas RWX de imagen para acomodar la mezcla de código y datos.

Los permisos lógicos Windows siguen separados: cabeceras R, código RX, datos RW y secciones R conforme a sus atributos. El dispatcher registra rangos lógicos sin solapamientos y la vista de instrucciones sólo acepta secciones ejecutables. La protección física es más amplia cuando varias regiones lógicas comparten una página; **el aislamiento de 4 KiB se comprueba por software**, no mediante un `mprotect` de 4 KiB que el backend no ofrece.

`shared_pages` cuenta páginas con varios contribuyentes y `widened_pages` aquellas que contienen una región lógica sin escritura junto a otra escribible. Son contadores del plan de mapeo aplicado, no una consulta independiente al hardware. El fixture de 4 KiB tiene dos páginas compartidas y dos con permisos ampliados.

Este incremento sólo cambia nuestra aplicación. No añade parches, syscalls ni capacidades a shadPS4. La validación en PS4 real permanece pendiente, según la disponibilidad de hardware.

## Accesos de fallback

El dispatcher comprueba ahora el intervalo completo de los operandos de memoria antes de llamar a hostexec. Permite ADDPS sin prefijos y LDMXCSR/STMXCSR con operandos explícitos; exige lectura de 16 bytes, lectura de 4 bytes o escritura de 4 bytes, respectivamente. Recorre regiones contiguas y rechaza cualquier parte del intervalo que carezca del permiso solicitado, incluido desbordamiento fuera de 32 bits. Los bits reservados altos del operando LDMXCSR se rechazan.

Las demás formas de fallback quedan no soportadas hasta auditar sus operandos; no se ejecutan sin comprobación. La llamada directa a hostexec en diagnósticos anteriores sigue siendo una prueba con operandos confiables y no es la API del dispatcher para aplicaciones. Esto no implementa todas las excepciones FP ni convierte aún los fallos en excepciones de Windows.

## Pruebas nuevas

`minimal4k32.exe` se construye desde el mismo `minimal.c` del incremento anterior, cambiando `SectionAlignment` a 4 KiB. Conserva BSS, el puntero y las cinco relocaciones HIGHLOW. El fixture original de 16 KiB se sigue compilando y probando.

|Caso| Comprobación |
|---|---|
| `pe-fourk-preferred` | Ejecuta la entrada en `0x30000000`, devuelve 42 y el proceso termina con 42 |
| `pe-fourk-relocated` | Ejecuta en `0x34000000`, aplica cinco relocaciones y termina con 42 |
| `pe-subpage` | Dos escrituras prohibidas por hostexec y dos por el emisor, una escritura válida y rechazo de código desde datos |

La prueba de permisos carga una imagen real y usa instrucciones de diagnóstico para intentar escribir en su código y cruzar desde datos RW hacia una sección R. Se comprueba que los destinos no cambian y el EIP se conserva en los rechazos. Sólo la escritura válida llega a ejecutar un stub hostexec. No se presenta esta prueba de instrucciones como ejecución de otra entrada del EXE.

Los casos anteriores de rechazo siguen pasando. La mutación de alineación no admitida ahora usa 2 KiB: una alineación válida de 4 KiB ya no debe rechazarse. Las pruebas de archivos truncados y mutaciones con sanitizadores se ejecutan sobre ambos fixtures.

<a id="reproducir"></a>


## Reproducción

```bash
python3 tools/build.py --cc clang-14 --ld ld.lld-14
bash tools/test-pe32.sh
```

```powershell
$revision = (Get-Content fork.lock.json -Raw | ConvertFrom-Json).commit
./tools/run-probes.ps1 -Emulator build/shadPS4-win/shadps4.exe `
    -EmulatorKind fork -EmulatorCommit $revision `
    -BuildManifest build/shadPS4-win/build-manifest.json `
    -Cases pe-fourk-preferred,pe-fourk-relocated,pe-subpage -TimeoutSeconds 25
```

El runner identifica y conserva ambos EXE por SHA256. Sin `-Cases` ejecuta la matriz ampliada de 37 diagnósticos.

## Evidencia preservada

El [informe del fork](../reports/increment5-fork-final/report.json) registra **33 aprobadas, cuatro bloqueadas y cero fallos/timeouts**. Los 34 casos anteriores conservan sus resultados. Siguen bloqueados los mismos casos de sysarch, la importación POSIX de borrado de clave TLS y los dos del emisor FP aislado.

El [fixture de 4 KiB en Windows](../reports/increment5-fork-final/host/windows-pe32-fourk.json) también devuelve 42. Su SHA256 es `fa5da821add741a82036f74f4b1131a181f91df1335e500bbb3f4b21dbb254a1`. El [parser con sanitizadores](../reports/increment5-fork-final/host/pe32-parser.json) recorre 5.606 truncamientos y 8.220 mutaciones por fixture: 11.212 truncamientos y 16.440 mutaciones en total, sin errores detectados en esta campaña acotada.

El snapshot contiene ambos EXE, fuentes propias, hashes, logs y manifiestos del mismo fork `c6de833f6bec304b6f08c37520428ba2ed147a1a`. El intento previo a ampliar las comprobaciones del emisor se conserva en `reports/increment5-smoke-initial`; la validación final usa el ELF identificado en `increment5-fork-final`.

El [oficial](../reports/increment5-official-final/report.json), usando el mismo ELF y ambos EXE, registra 15 aprobadas, 21 bloqueadas y una fallida, sin timeouts. Los tres casos nuevos quedan bloqueados en la publicación del código JIT RX. La [comparación por caso](../reports/increment5-fork-final/comparison.json) conserva también los hashes de ambos fixtures.

Los tres casos nuevos pasan con el ELF final en tres ejecuciones independientes: `reports/increment5-smoke`, la matriz completa y `reports/increment5-repeat`. Terminan con sus códigos esperados, sin stubs ni reservas activas.

## Siguiente incremento

Carga de una DLL PE32 propia y resolución de imports/exports reales, con una llamada entre módulos que recorra la IAT. Será una prueba de enlace entre módulos propios; no equivaldrá a tener kernel32, ntdll o Wine integrados. Seguirán pendientes inicialización Wine, APIs de archivo e hilos, excepciones Windows y compatibilidad en consola real.
