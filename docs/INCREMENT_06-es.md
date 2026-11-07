# Incremento 6: DLL PE32 e importaciones reales por IAT

[English](INCREMENT_06.md) | [Español](INCREMENT_06-es.md)

La inicialización de DLL y TLS posterior se documenta en [Incremento 7](INCREMENT_07-es.md). Este documento conserva la evidencia anterior.

## Resultado

`imports32.exe` carga junto con la DLL propia `testmath.dll`. La IAT se resuelve con una función por nombre y otra por ordinal. Ambas funciones se ejecutan en el dispatcher; el EXE devuelve 42 y ese valor se propaga a la salida del proceso OpenOrbis. Funciona tanto en las bases preferidas como reubicando ambos módulos.

El mismo par EXE/DLL devuelve 42 en Windows mediante su loader normal. El [informe Windows](../reports/increment6-fork-final/host/windows-dll.json) fija los hashes de ambos archivos, duración y código de salida.

No se añadieron parches ni APIs al emulador. Se conserva el fork `c6de833f6bec304b6f08c37520428ba2ed147a1a`. Wine, kernel32, ntdll y la inicialización general de DLL siguen pendientes; las funciones ejecutadas aquí son código propio de la DLL, sin respuestas simuladas de APIs Windows.

## Implementación

`platform/ps4/pw_pe32_tables.c` valida imports/exports y resuelve el enlace, siguiendo el formato de [tablas PE documentado por Microsoft](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format). Se comprueban RVAs, tamaños, terminadores, cadenas, índices, ordinales, permisos de la IAT y posiciones de destino duplicadas. Los ordinales se resuelven contra la base y la tabla de exports; los huecos de esa tabla no se consideran funciones.

Los nombres de DLL se comparan sin distinguir mayúsculas/minúsculas, mientras que los nombres de símbolos se comparan exactamente. El resolver usa una lista explícita de imágenes ya cargadas: no busca DLL del sistema ni descarga archivos. La vista de instrucciones del dispatcher puede obtener código de cualquiera de los módulos registrados y conserva sus permisos lógicos independientes.

La resolución calcula todos los destinos primero. Sólo cuando todos existen se escriben las direcciones reales en la IAT y la imagen pasa a estado enlazado. Un fallo deja intactas todas las entradas. El informe de enlace identifica DLL, símbolo u ordinal y RVA del slot que no pudo resolverse. Una imagen con imports pendientes no puede entregar instrucciones ni vincularse al estado de CPU.

Los proveedores de esta etapa deben ser DLL sin imports ni punto de entrada. Una DLL con inicialización, imports propios, exports reenviados o características no implementadas se rechaza; no se omiten sus requisitos para declararla funcional.

## Fixtures y ABI

- `testmath.c` y `testmath.def`: exportan `Scale` por nombre/ordinal 7 y `OrdinalScale` sólo por ordinal 11. Hay huecos en los ordinales 8–10.
- `imports.c`: invoca ambas funciones mediante las dos entradas de la IAT. `Scale(1)` calcula 12 usando un factor global de la DLL; la función ordinal suma una variable global 30 y devuelve 42.
- `nested.c` y `nested.def`: forman una DLL real con una dependencia adicional, utilizada para demostrar el rechazo del grafo aún no soportado.

El test comprueba que la IAT contiene direcciones de los exports cargados y que la vista de código visita ambas entradas de función. Verifica retorno 42, pila restaurada y conservación de EBX, EBP, ESI y EDI. No usa thunks que devuelvan constantes desde el anfitrión ni invoca código PE32 directamente en modo x86-64.

En la prueba reubicada, el EXE pasa de `0x30000000` a `0x34000000` y la DLL de `0x32000000` a `0x36000000`. Se aplican cuatro relocaciones: dos en cada módulo.

## Pruebas nuevas

|Caso| Resultado exigido |
|---|---|
| `pe-dll-preferred` | Dos imports resueltos, ambas funciones visitadas, retorno y salida 42 |
| `pe-dll-relocated` | Lo mismo después de mover ambos módulos y aplicar cuatro fixups |
| `pe-dll-missing` | `PW_ERR_NOT_FOUND`, DLL identificada, IAT intacta |
| `pe-dll-symbol` | Solicita `Xcale`, conserva la IAT aunque el ordinal anterior sí exista |
| `pe-dll-ordinal` | Solicita el ordinal vacío 8 y conserva la IAT |
| `pe-dll-invalid` | Rechaza cinco alteraciones de tablas o características no soportadas |
| `pe-dll-dependency` | `nested.dll` contiene imports propios; devuelve `PW_ERR_UNSUPPORTED` sin ejecutar ni modificar la IAT |

Los tests de símbolo, ordinal y dependencia alteran copias en memoria del fixture antes de validarlo y cargarlo; los archivos originales conservados no se cambian. Las alteraciones exactas están en `native/dll_probe.c`. La prueba de DLL ausente omite el proveedor del registro; no depende de una búsqueda en el sistema.

La prueba de tablas cubre IAT fuera de rango, export reenviado no soportado, índice de ordinal inválido, tabla de nombres fuera de rango y entrada de DLL no cero. Cada caso verifica su error esperado antes de contabilizar aprobación.

## Evidencia

El [informe del fork](../reports/increment6-fork-final/report.json) registra **40 aprobadas, cuatro bloqueadas, cero fallos y cero timeouts**. Los 37 casos del incremento anterior conservan su estado. Los bloqueos son los mismos: sysarch, borrado POSIX de clave TLS y las dos pruebas exclusivas del emisor FP aislado.

El [parser con sanitizadores](../reports/increment6-fork-final/host/pe32-parser.json) se prueba sobre cinco archivos, con 28.620 truncamientos y 41.486 mutaciones de cabeceras y directorios: ASan, UBSan y detección de fugas no detectaron errores en esa campaña acotada. No equivale a una auditoría exhaustiva de archivos hostiles.

Los snapshots conservan los cinco fixtures, las 29 fuentes/cabeceras/definiciones y herramientas propias identificadas por `build.json`, logs y manifiestos del emulador. El comparador exige los mismos hashes de ELF y fixtures.

El [informe oficial](../reports/increment6-official-final/report.json), con los mismos archivos, registra 20 aprobadas, 23 bloqueadas y una fallida, sin timeouts. Las dos ejecuciones DLL se bloquean en la publicación JIT RX; los cinco casos de rechazo pasan. La [comparación por caso](../reports/increment6-fork-final/comparison.json) mantiene hashes de todos los fixtures.

Los siete casos nuevos pasan en tres ejecuciones independientes con el ELF final: `reports/increment6-smoke`, la matriz completa y `reports/increment6-repeat`. No invocan stubs y dejan cero reservas activas; los positivos salen con 42 y los tests de rechazo con 0.

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
    -Cases pe-dll-preferred,pe-dll-relocated,pe-dll-missing,pe-dll-symbol,pe-dll-ordinal,pe-dll-invalid,pe-dll-dependency `
    -TimeoutSeconds 25
```

El builder genera la biblioteca de importación con GNU ld. No se escriben a mano las entradas IAT de los fixtures. Sin `-Cases`, el runner ejecuta 44 diagnósticos.

## Alcance pendiente

Se admiten hasta 64 imports, 64 slots de exportación y ocho módulos en la vista de ejecución. Se limita el nombre de DLL a 63 caracteres y el de símbolo a 127. Los proveedores deben estar ya cargados y no tener dependencias propias; no hay descubrimiento recursivo, tratamiento de ciclos ni búsqueda por prefijo Windows. No se admiten imports bound/delay, aliases de varios nombres para un export, exports de datos, forwarders, TLS de imagen ni `DllMain`.

La siguiente etapa es inicialización de DLL y TLS con pruebas de orden, argumentos y fallo de inicialización, antes de conectar el arranque real de Wine. La validación en PS4 física sigue pendiente; el banco disponible continúa siendo shadPS4.
