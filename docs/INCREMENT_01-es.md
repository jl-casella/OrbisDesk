# Incremento 1: memoria administrada y fork reproducible

[English](INCREMENT_01.md) | [Español](INCREMENT_01-es.md)

## Backend PS4

El backend mantiene un registro por proceso protegido por mutex. Cada reserva recibe un identificador que no se reutiliza, y cada página de 16 KiB conserva su estado de commit y sus permisos registrados. Las copias de `PwVmRegion` siguen siendo válidas hasta liberar la reserva; reutilizar la variable de salida para otra reserva no invalida una copia conservada por el llamador.

Se rechazan regiones ajenas o alteradas, referencias vencidas, rangos fuera de límites, commits superpuestos y cambios de protección sobre páginas sin commit. Los fallos de las llamadas al kernel no adelantan el estado del registro. Este registro no convierte en atómica una implementación defectuosa del kernel: las pruebas de fallos inyectados verifican el estado del backend y las pruebas OpenOrbis verifican el comportamiento observado del emulador.

`pw_vm_ps4_stats` permite comprobar reservas, bytes reservados y bytes comprometidos. El backend todavía usa memoria flexible; la memoria directa y la emulación de granularidad Windows de 4 KiB corresponden a una etapa posterior.

Pruebas nuevas:

- Host WSL: fallos de reserve/map/protect/unmap, rangos inválidos, superposición, copias, reutilización de direcciones y 400 ciclos concurrentes. Ejecutadas con AddressSanitizer, UndefinedBehaviorSanitizer y detección de fugas.
- OpenOrbis: `vm-ownership`, `vm-stress` y `vm-enforcement`. Esta última comprueba fallos reales de lectura/escritura y no se conforma con consultar los permisos que declara el emulador.
- Traductor: llamadas/retornos y pila; aritmética x87 y operaciones SSE2 enteras; preservación del control FP anfitrión; retraducción explícita de código cambiado.
- Cierre: resultados esperados distintos para `exit(0)` y `exit(7)`.

La prueba de retraducción no valida todavía invalidación automática de cachés ni código que se modifica durante su propia ejecución.

## Fork de shadPS4

El fork es local, sin publicación ni modificación de `upstream/shadPS4`. Su base, commits y parches están en `fork.lock.json`; las herramientas portables se verifican con `fork-tools.lock.json`.

Los tres parches compilados y probados corrigen:

1. Las vistas del backing de RAM en Windows admiten ejecución desde su creación y se restringen inmediatamente a los permisos solicitados antes de devolver el mapeo. Esto permite RW→RX posterior sin conceder RWX permanentemente. Los mapeos de archivos externos conservan su tratamiento propio.
2. El cierre del invitado utiliza la ruta de `quick_exit` existente y conserva su código de salida.
3. La conversión de permisos prueba el bit de escritura individualmente. Usar `True(prot & ReadWrite)` concedía escritura incluso cuando sólo se pedía lectura.
4. El manejador de accesos vigilados por la GPU consulta los permisos del mapeo antes de reintentar. Una escritura realmente prohibida debe llegar al manejador de excepciones del invitado; reintentar indefinidamente causaba un timeout.

El primer parche agrupa las correcciones de vistas ejecutables y cierre. El tercero evita el bucle de fallos; no incorpora excepciones para este programa.

La reproducción independiente de Windows está en `tests/windows-view-protection.ps1`: una vista creada como RW produce error 87 al pasar a RX; una vista con capacidad de ejecución, restringida primero a RW, permite la transición. Esa reproducción no reemplaza la prueba del fork completo.

## Construcción y evidencia

Prerrequisitos: Visual Studio con herramientas C++ x64 y Windows SDK; WSL con OpenOrbis y `p7zip-full` para extraer las herramientas portables.

```powershell
./tools/bootstrap-fork-tools.ps1
./tools/prepare-shad-fork.ps1
./tools/build-shad.ps1 -Jobs 6
```

El builder genera `build/shadPS4-win/build-manifest.json` con commit, parches, hash del ejecutable, versiones de herramientas y revisiones de submódulos.

```powershell
$revision = (Get-Content fork.lock.json -Raw | ConvertFrom-Json).commit
./tools/run-probes.ps1 -Emulator build/shadPS4-win/shadps4.exe `
    -EmulatorKind fork -EmulatorCommit $revision `
    -BuildManifest build/shadPS4-win/build-manifest.json -TimeoutSeconds 30
```

Para verificar el backend en host, ejecutar `bash tools/test-vm.sh` en WSL. Para verificar la clasificación de resultados, ejecutar `./tests/report-classification.ps1` en PowerShell.

La referencia inicial permanece en `reports/baseline`. La matriz oficial final está preservada en `reports/increment1-official-final`: 13 aprobadas, 8 bloqueadas y 1 fallida. Es una matriz distinta de la inicial; comparar sólo el número de aprobaciones entre ambas no mide regresiones.

La matriz del fork está en [su informe](../reports/increment1-fork/report.json): **18 aprobadas y 4 bloqueadas**, sin fallos ni timeouts. Usa exactamente el mismo ELF que la matriz oficial final (SHA256 registrado en ambos informes). La [comparación por caso](../reports/increment1-fork/comparison.json) registra:

|Caso| Oficial |Fork|
|---|---|---|
|`generated-code` RW→RX| Bloqueado | Aprobado, retorna 42 |
| `translator` en RX | Bloqueado | Aprobado, EAX=42 |
| `vm-enforcement` | Fallido | Aprobado, recupera dos fallos reales |
| `process-exit-zero` | Bloqueado | Aprobado, host termina con 0 |
| `process-exit-seven` | Bloqueado | Aprobado, host termina con 7 |

Commit probado: `c6de833f6bec304b6f08c37520428ba2ed147a1a`. El manifiesto de compilación y los parches fijados acompañan el informe del fork. `tests/fork-patches.ps1` reconstruye su árbol desde la base usando un índice Git aislado y verifica que coincide con el commit publicado en el manifiesto local.

Dos rondas adicionales de seis casos críticos pasan completas en procesos nuevos: `reports/increment1-repeat-1` y `reports/increment1-repeat-2`. Incluyen RW→RX, permisos efectivos, traductor en RX, propiedad de reservas y salidas 0/7. Junto con la matriz completa, son tres ejecuciones independientes de cada uno de esos casos; no equivalen a pruebas de estabilidad de aplicaciones Windows.

Las pruebas dedicadas de cierre exigen terminar sin aserciones; la excepción histórica que separa el resultado de una prueba de plataforma del fallo de cierre no permite aprobar `process-exit-zero` ni `process-exit-seven`.

## Fronteras que siguen pendientes

`sysarch`/FS/GS y la importación POSIX de `pthread_key_delete` siguen bloqueados. El adaptador que usa `scePthreadKeyDelete` pasa, con TLS y destructores reales. Las pruebas de `LDMXCSR` y `ADDPS` registran que la ruta de emisión enlazada todavía no las ejecuta. El runtime completo necesita integrar las rutas de ejecución restantes de prospero-win antes de usar esa evidencia para afirmar compatibilidad de Wine.

El harness exige que un fixture de bloque único se traduzca completo: aceptar sólo su prefijo ya no puede aparecer como ejecución de todas las instrucciones. Los fallos observados durante esta ampliación se preservan también en `reports/increment1-fp-frontier`.

Este incremento todavía no integra Wine, WoW64, GDI ni DXVK, y no valida hardware PS4.

## Siguiente incremento

1. Aislar FS/GS con casos mínimos de lectura, escritura y cambio de hilo; definir la convivencia entre TLS del anfitrión y TEB de Windows antes de integrar Wine.
2. Integrar las rutas restantes del traductor y ampliar instrucciones de control FP, excepciones y coherencia de caché; conservar los bloqueos hasta ejecutarlas.
3. Portar inicialización Unix de Wine y carga PE32, empezando por `console32.exe`. El objetivo será comprobar cálculo, archivo, hilo y código de salida en un proceso nuevo, antes de avanzar a GDI.
