# Incremento 7: inicialización de DLL y TLS por hilo

[English](INCREMENT_07.md) | [Español](INCREMENT_07-es.md)

## Resultado

El runtime ejecuta callbacks TLS y `DllMain` reales mediante el traductor x86. Se validan orden de attach/detach, argumentos, conservación de pila/registros, aislamiento de datos TLS entre hilos y limpieza al devolver FALSE una DLL. La referencia Windows usa los mismos DLL con `LoadLibrary`, `CreateThread` y `FreeLibrary`, y termina con código 42.

Todo este cambio está en la aplicación; el fork sigue en `c6de833f6bec304b6f08c37520428ba2ed147a1a`, sin nuevos parches ni APIs de Orbis. Wine y la validación en consola física continúan pendientes.

## Runtime y contrato

`pw_pe32_lifecycle.c` recibe DLL ya enlazadas en orden explícito. Serializa sus notificaciones con un mutex y prepara un vector TLS y bloques privados para cada hilo. Cada bloque copia la plantilla PE; el FS virtual de IA-32 apunta a un TEB mínimo con `ThreadLocalStoragePointer` en `FS:[0x2c]`. El TLS nativo de Orbis y el FS/GS anfitrión no se sustituyen.

El parser valida el directorio TLS, sus direcciones VA, plantilla, destino del índice y lista de callbacks terminada. Admite hasta 16 callbacks y una plantilla de hasta 4 KiB. El runtime asigna índices de módulo estables y permite bloques distintos para el mismo módulo en diferentes hilos.

Las llamadas a callbacks y `DllMain` usan `pw_guest_callback_enter/leave` de prospero-win, con ABI stdcall y tres argumentos: base real, motivo y reservado NULL. El orden por módulo es callback TLS y después `DllMain`. Attach recorre el orden suministrado y detach lo invierte. Este contrato se contrastó con la [documentación de DllMain](https://learn.microsoft.com/en-us/windows/win32/dlls/dllmain), el [formato TLS PE](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format) y el comportamiento observado en la prueba Windows.

Se prueban los motivos PROCESS_ATTACH, THREAD_ATTACH, THREAD_DETACH y PROCESS_DETACH. El hilo inicial recibe PROCESS_ATTACH; el hilo nuevo recibe THREAD_ATTACH. El ámbito actual corresponde a carga/descarga dinámica, con reservado NULL, no a todo el arranque estático de Windows.

Si `DllMain` devuelve FALSE en PROCESS_ATTACH, se ejecuta detach del módulo que rechazó la carga y de los anteriores en orden inverso. El runtime devuelve `PW_PE32_INIT_FAILED` (-100), no activa la DLL y bloquea su ejecución posterior. Ese código es de nuestra API, no una simulación de `GetLastError` de Windows. Las excepciones y fallos de ejecución generales todavía no se convierten en SEH.

Los módulos pendientes, fallidos o descargados lógicamente no entregan código. El dispatcher comprueba esa condición en cada paso, también cuando el bloque ya está traducido en caché. No se puede liberar una imagen mientras un runtime de inicialización la tenga registrada. TLS y FS virtual se retiran al destruir el contexto de hilo, antes de liberar las imágenes.

## Fixtures y pruebas

`lifecycle.c` contiene una plantilla TLS con semilla 7 y campos cero, un callback, `DllMain` y funciones de consulta/mutación. El propio código guest comprueba base, motivo, reservado, estado inicial y orden; registra los eventos. Las funciones de prueba escriben sus datos de diagnóstico, sin que el runtime conozca su layout.

Se construyen tres DLL: una principal, otra correcta para el segundo módulo y otra que devuelve FALSE durante attach. Todas se enlazan sin CRT ni imports.

|Caso| Validación |
|---|---|
| `pe-init-order` | Dos módulos, ocho notificaciones, attach en orden y detach inverso |
| `pe-init-relocated` | Mismo contrato con ambos módulos reubicados |
| `pe-init-failure` | FALSE en la segunda DLL, detach de ambas, error -100 y ejecución posterior rechazada |
| `pe-tls-threads` | Hilo nativo nuevo, plantilla independiente, mutaciones 55/99 aisladas, ocho notificaciones y errno nativo preservado |
| `pe-tls-invalid` | Seis alteraciones de directorio/callbacks rechazadas antes de ejecutar |

Los casos funcionales comprueban también que un PC ya cacheado queda bloqueado después del detach o del fallo. Todos verifican que no quedan reservas ni bytes comprometidos activos al terminar.

El [helper Windows](../reports/increment7-fork-final/host/windows-lifecycle.json) carga la DLL, comprueba attach, crea un hilo con TLS independiente, comprueba detach y descarga. Una copia de los eventos queda en el EXE antes de liberar la DLL, lo que permite verificar las ocho notificaciones tras `FreeLibrary`. También comprueba que la DLL que devuelve FALSE no se carga y que Windows informa `ERROR_DLL_INIT_FAILED`. Este helper sólo se ejecuta en Windows: no implementa APIs kernel32 para PS4.

## Hallazgos y límites explícitos

La caché inicial de 64 entradas/256 KiB se agotaba con dos DLL de inicialización. Se amplió a 256 entradas/1 MiB. Sigue siendo acotada: no se inventan ejecuciones ni se omiten callbacks ante agotamiento. El reinicio general de cachés sigue pendiente.

La primera referencia Windows fallaba una comprobación del espacio declarado mediante `SizeOfZeroFill=8` fuera de la plantilla raw de 16 bytes. El retorno temprano del helper sin CRT provocaba después otra excepción al terminar el último hilo, ocultando el fallo original. El depurador de la prueba permitió aislar ambos hechos. No se concluye que todas las versiones de Windows tengan ese comportamiento ni que sea un fallo del sistema.

El fixture validado usa una plantilla raw completa de 24 bytes, incluidos sus campos cero, y `SizeOfZeroFill=0`. **Los valores no nulos de SizeOfZeroFill se rechazan expresamente** hasta investigar esa configuración por separado. El test host exige el rechazo de valor 8 en las tres DLL TLS. No se anuncia soporte de ese campo basándose solamente en el resultado del emulador.

Se conservan el primer intento en `reports/increment7-initial-failures`, la regresión intermedia en `reports/increment7-pre-guard` y el binario/código de la configuración no confirmada en `host/` del snapshot final. La evidencia final usa los fixtures raw completos y el dispatcher que verifica el estado por paso.

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
    -Cases pe-init-order,pe-init-relocated,pe-init-failure,pe-tls-threads,pe-tls-invalid `
    -TimeoutSeconds 25
```

Sin `-Cases` se ejecutan 49 diagnósticos. La prueba Windows es `out/lifecycle-host.exe`, desde el directorio que contiene las DLL.

## Evidencia final

El [informe del fork](../reports/increment7-fork-final/report.json) registra **45 aprobadas y cuatro bloqueadas**, sin fallos ni timeouts. Los 44 casos del incremento anterior conservan sus resultados. Permanecen los bloqueos conocidos de sysarch, borrado POSIX de clave TLS y las dos pruebas exclusivas del emisor FP.

El [oficial](../reports/increment7-official-final/report.json), con los mismos archivos, registra 21 aprobadas, 27 bloqueadas y una fallida, sin timeouts. Los casos que ejecutan inicializadores se bloquean en la publicación JIT RX; el rechazo de TLS inválido pasa. La [comparación](../reports/increment7-fork-final/comparison.json) identifica ELF y los ocho fixtures por hash.

Los cinco casos nuevos pasan en tres ejecuciones independientes con el ELF final: `reports/increment7-smoke-final`, la matriz completa y `reports/increment7-repeat`. No invocan stubs, terminan con código 0 y dejan cero reservas activas. El código 0 de la prueba de rechazo significa que se verificó el error -100 esperado, no que la DLL fallida se haya inicializado.

El [parser con sanitizadores](../reports/increment7-fork-final/host/pe32-parser.json) recorre ocho fixtures, con 50.934 truncamientos y 66.861 mutaciones. Comprueba además explícitamente el rechazo de SizeOfZeroFill=8 en las tres DLL TLS. ASan, UBSan y detección de fugas no detectaron errores en esta campaña acotada.

El snapshot conserva las 35 fuentes/cabeceras/definiciones y herramientas propias de compilación, los ocho PE, logs, manifiestos del fork y el helper Windows exacto. Los objetos de lifecycle y contexto de hilo del API se usan inicializados a cero y conservan su dirección durante su vida; no deben copiarse ni destruirse mientras haya hilos asociados.

## Pendiente

El orden entre módulos lo entrega el llamador. Se mantienen DLL proveedoras sin imports propios, sin descubrimiento recursivo ni ciclos. No se implementa el loader lock de Windows, carga reentrante desde DllMain, `TlsAlloc`/FLS, TLS en EXE, alineaciones TLS explícitas, arranque estático con reservado no nulo ni SEH. Las imágenes no se reinicializan tras detach/fallo: deben remapearse.

El siguiente trabajo es preparar el contexto de proceso y el arranque de Wine, contrastando PEB/TEB, parámetros, dependencias e interfaz Unix de ntdll para PS4. Este runtime de pruebas no sustituye la inicialización de Wine ni ejecuta aún el fixture Win32 completo con archivo e hilo.
