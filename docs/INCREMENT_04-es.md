# Incremento 4: primer PE32 sin importaciones

[English](INCREMENT_04.md) | [Español](INCREMENT_04-es.md)

El soporte posterior de secciones de 4 KiB y sus permisos compartidos se documenta en [Incremento 5](INCREMENT_05-es.md). Este documento conserva la evidencia previa.

## Resultado

El fork ejecuta la entrada del EXE propio `minimal32.exe` desde un archivo PE32 real. Devuelve 42 en `0x30000000` y también en `0x34000000`, después de aplicar cinco relocaciones HIGHLOW. El retorno se propaga al proceso OpenOrbis y el runner comprueba que shadPS4 termina con código 42 en ambos casos.

El mismo archivo también se ejecutó directamente en Windows y terminó con 42. Su SHA256 es `2aa89653551212b3868bf82e7254c3c017cd95d90b3a8d3f6587dc824ce61037`. La [referencia Windows](../reports/increment4-fork-final/host/windows-pe32.json) registra ese hash, código de salida y duración.

Esto valida la carga y ejecución del PE propio. No valida inicialización de procesos Windows, `ExitProcess`, DLL, CRT ni Wine: el harness prepara una pila IA-32, llama a la entrada y comprueba un retorno real mediante `RET`.

## Cargador y fixture

`platform/ps4/pw_pe32.c` implementa el subconjunto inicial, contrastado con la [especificación PE de Microsoft](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format). Comprueba firmas, arquitectura i386, cabecera opcional PE32, tamaños y rangos, entrada ejecutable, secciones sin solapamientos y bloques de relocación.

Cada imagen se reserva sin reemplazar memoria existente. Se copian cabeceras y secciones, se inicializan a cero las páginas de sección, se aplican relocaciones HIGHLOW y se fijan permisos finales por sección. Las escrituras de reubicación se realizan antes de restringir el código a RX. Las secciones W+X se rechazan. Los huecos no comprometidos permanecen inaccesibles. La vista de instrucciones sólo entrega bytes pertenecientes a secciones ejecutables; la tabla del dispatcher registra por separado los permisos de cabeceras, datos y código.

La reserva admite la base preferida o una dirección alternativa explícita. No elige automáticamente otra base ante una colisión. La ruta reubicada exige relocaciones válidas; sólo admite HIGHLOW y entradas ABSOLUTE de relleno, y rechaza destinos superpuestos o fuera de las secciones.

`fixtures/win32/minimal.c` se compila con MinGW i686 sin CRT ni bibliotecas. Tiene una semilla 7 en `.data`, un puntero que requiere relocación y un resultado en `.bss`. La entrada comprueba que BSS comienza en cero, lee a través del puntero, calcula `7 * 5 + 7`, guarda el resultado y retorna. Las cinco relocaciones se encuentran en código y datos; no basta con mover una única dirección de entrada.

GNU ld emite un descriptor de importación completamente cero. Se acepta sólo ese terminador vacío de 20 bytes; un descriptor de DLL no nulo se rechaza. No se resuelve ninguna importación mediante respuestas simuladas.

## Validación

|Caso| Resultado en fork |
|---|---|
| `pe-preferred` | Entrada ejecutada, EAX=42, pila restaurada, salida del proceso 42 |
| `pe-relocated` | Cinco fixups en otra base, EAX=42, pila restaurada, salida 42 |
| `pe-invalid` | Doce casos inválidos o no admitidos rechazados; el resultado de parseo conserva su valor previo |
| `pe-collision` | Reserva ocupada rechazada sin sobrescribir su contenido |

Las dos ejecuciones positivas pasan por dos bloques reales del dispatcher, sin necesitar hostexec para este programa. Todos los casos liberan sus reservas y verifican cero bytes comprometidos activos al terminar.

El [informe del fork](../reports/increment4-fork-final/report.json) registra **30 aprobadas y cuatro bloqueadas**, sin fallos ni timeouts. Los 30 casos anteriores conservan sus resultados. Los bloqueos restantes siguen siendo `sysarch`/FS/GS nativo, la importación POSIX de `pthread_key_delete` y los dos casos exclusivos del emisor para LDMXCSR/ADDPS; sus rutas hostexec pasan.

El [oficial](../reports/increment4-official-final/report.json), con el mismo ELF y EXE, registra 15 aprobadas, 18 bloqueadas y una fallida, sin timeouts. Los rechazos de entradas y colisiones pasan; ambas ejecuciones PE quedan bloqueadas en la publicación RX. La [comparación](../reports/increment4-fork-final/comparison.json) conserva hashes del ELF y del EXE junto con los resultados por caso.

Las cuatro pruebas PE pasan en tres procesos independientes por caso con los mismos binarios: `reports/increment4-smoke`, la matriz completa y `reports/increment4-repeat`. No invocan stubs. Las ejecuciones positivas terminan con código 42; las dos pruebas de rechazo terminan con 0.

La prueba host del parser recorre 5.606 truncamientos y 8.220 mutaciones de cabeceras y relocaciones con ASan, UBSan y detección de fugas. No aparecieron errores en esa campaña acotada; no es una prueba exhaustiva de entradas hostiles. El [informe host](../reports/increment4-fork-final/host/pe32-parser.json) fija compilador, hashes de fuentes y del EXE. El snapshot conserva también el test y su script.

Los informes identifican tanto el ELF como los fixtures por SHA256. El EXE exacto queda en `fixtures/` del snapshot, las 21 fuentes/cabeceras/herramientas propias de compilación en `inputs/`, junto con manifiestos del fork y logs. El comparador exige que ELF, fixtures y conjunto de casos coincidan antes de comparar estados.

<a id="reproducir"></a>


## Reproducción

En WSL:

```bash
python3 tools/build.py --cc clang-14 --ld ld.lld-14
bash tools/test-pe32.sh
```

En PowerShell:

```powershell
$revision = (Get-Content fork.lock.json -Raw | ConvertFrom-Json).commit
./tools/run-probes.ps1 -Emulator build/shadPS4-win/shadps4.exe `
    -EmulatorKind fork -EmulatorCommit $revision `
    -BuildManifest build/shadPS4-win/build-manifest.json `
    -Cases pe-preferred,pe-relocated,pe-invalid,pe-collision -TimeoutSeconds 25
```

El runner copia el EXE al `/data` aislado de cada prueba y verifica su hash contra el manifiesto de compilación. Sin `-Cases`, ejecuta la matriz de 34 diagnósticos. No se añadieron parches de shadPS4; se conserva el fork del primer incremento.

## Alcance pendiente

Este cargador exige secciones de 16 KiB y limita la imagen a 32 MiB, el archivo a 4 MiB, las secciones a 16 y las relocaciones a 4.096. Rechaza DLL, importaciones activas, TLS de imagen, load config y los demás directorios no implementados. Los PE normales con secciones de 4 KiB aún no son admitidos.

No inicializa PEB, TEB de Wine, argumentos Windows, CRT, DLL ni sus callbacks. El dispatcher mantiene su contrato de código inmutable y operandos confiables en hostexec. Este resultado no convierte el prototipo en un ejecutor general de EXE ni valida hardware PS4.

El próximo incremento debe admitir secciones PE de 4 KiB con permisos coherentes en páginas PS4 de 16 KiB y preparar una llamada Win32 real con imports resueltos. La integración de Wine seguirá siendo necesaria para el fixture completo de archivo e hilo; no se contabilizará como realizada mediante stubs propios.
