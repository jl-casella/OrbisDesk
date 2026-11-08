# Ejecutar CI y medir la matriz de plataforma

[English](CI.md) | [Español](CI-es.md)

## Qué está implementado

Las primeras tres fases del [plan de CI](CI_PLAN-es.md) aportan checks rápidos de PR, construcción independiente de fixtures/servicios y una matriz manual de plataforma. Todavía hace falta una corrida en un runner nuevo de GitHub para establecer el tiempo en frío. Las corridas locales con dependencias ya instaladas no establecen esa referencia.

Los workflows son:

| Workflow | Disparador | Propósito |
| --- | --- | --- |
| `PR checks` | Pull request o manual | Documentación, estructura, locks, Python y pruebas del host de VM/parser con sanitizadores |
| `Manual platform matrix` | Sólo manual | Producir fixtures, ejecutar los mismos binarios en Windows, preparar dependencias Linux, compilar y ejecutar el contrato de diagnóstico |
| `Collect matrix timings` | Finalización del workflow manual | Leer tiempos finales de jobs y pasos desde GitHub; subir `timings.json` |

Estos workflows de diagnóstico no publican releases, compilan el escritorio Wine completo, acceden por FTP ni cambian protecciones de ramas. Una matriz satisfactoria sube únicamente un paquete de diagnósticos. El [workflow experimental de release](RELEASES-es.md) separado intenta la construcción completa limpia; su primer piloto satisfactorio en GitHub sigue pendiente.

## Primera corrida medida

1. Integrar la implementación en la rama predeterminada. GitHub necesita conocer allí el workflow manual antes de seleccionarlo en Actions. El recolector de tiempos también debe existir allí.
2. Abrir **Actions → Manual platform matrix → Run workflow**. Elegir la rama/revisión deseada, `profile=platform-v1` y `cache_mode=cold`.
3. Esperar tanto la matriz como el recolector separado. Una preparación fallida es un piloto fallido, no una matriz aprobada.
4. Descargar `matrix-evidence-*` de la matriz y `matrix-timings-*` del recolector. Registrar URL, SHA, resultado, tiempo total, suma de tiempos de jobs y duración por fase.
5. Opcionalmente repetir con `cache_mode=reuse` en la misma revisión. Esa caché contiene sólo descargas verificadas; la compilación se repite. No describirla como medición de compilación incremental.

Los límites acotan el piloto: 90 minutos para el job Linux, 45 para su paso de preparación y 20 para ejecución. Cada caso tiene un timeout de 60 segundos. Cancelaciones o timeouts externos pueden dejar evidencia incompleta; la ausencia de un informe completo nunca implica éxito.

El perfil `platform-core` ejecuta los 27 casos base sin los cuatro de servicios. Sirve para diagnóstico, pero no genera el paquete completo de diagnósticos ni reemplaza la aceptación de 31 casos.

## Alcance y evidencia

[tests/ci-matrix.json](../tests/ci-matrix.json) es el contrato versionado: 27 casos de cargador/traductor/plataforma y cuatro casos de servicios nativos con 45 comprobaciones identificadas. Cada caso usa un proceso nuevo del emulador y un directorio de datos privado. Windows nativo valida los mismos binarios y genera referencias de salida; hashes y revisiones deben coincidir antes de ejecutar Linux.

La comparación con el emulador oficial espera un resultado **blocked** con una firma exacta de aserción, marcadores satisfactorios del invitado y salida coincidente con la referencia. Un crash arbitrario, un marcador ausente o un timeout no satisfacen ese contrato. Los resultados del fork se informan por separado. Hardware queda pendiente y `Wine_booted` sigue falso: estas sondas no arrancan Wine.

La evidencia en el directorio ignorado `reports/ci/` incluye:

- `matrix-report.json`: casos reales, resultados, hashes, procedencia del emulador y errores de preparación.
- `cases/<case>/`: stdout, stderr, informe del caso y archivos de salida cuando corresponda.
- `windows-reference.json`: códigos de salida nativos, bytes de referencia e identidad de fixtures.
- `timings.jsonl` y `phase-timings.json`: duración interna de preparación, construcción y ejecución.
- `environment.json` y logs de construcción: paquetes instalados, hashes de locks y preparación cuando se alcanzan esas etapas.

El artefacto también conserva `build/shadPS4-linux/configure.log`, `build.log`, `CMakeCache.txt` y `CMakeFiles/CMakeConfigureLog.yaml` cuando existen. Un builder fallido imprime los últimos 64 KiB de su log a través de ambas capturas hasta la salida del paso en Actions; los logs completos quedan en el artefacto. La ausencia de archivos de etapas no alcanzadas no implica éxito.

El primer piloto en GitHub, corrida `42429594632`, intento 1 en `12eae3a4db4cbf46ec15914449c597743ec6a0a3` del 2026-11-07 (hora argentina), falló al configurar el fork con CMake. Terminaron la restauración de fuentes, extracción SDK/oficial y construcción de ELF de diagnóstico y servicios; la matriz no comenzó. Los aproximadamente tres minutos corresponden al paso de preparación, no a ejecutar los 31 casos. El artefacto original omitía el log de configuración de CMake y por eso no permite determinar su causa. El cambio posterior corrige esa falta de evidencia; no afirma resolver el error de configuración todavía desconocido. Después de integrarlo, iniciar una **corrida manual nueva en main actualizado**; reejecutar el SHA anterior conserva el workflow viejo.

El siguiente piloto en `cbf26969c4ecc8e82b65d693abd550bf6abee15e` mostró `SDL_missing_dependency` en `externals/sdl3/cmake/sdlchecks.cmake:521`: el SDL3 fijado exige headers y biblioteca XRANDR. El instalador del runner omitía `libxrandr-dev`. Ahora lo incluye explícitamente y verifica `pkg-config xrandr` antes de configurar. Esto corrige el requisito identificado; completar la compilación del emulador y la matriz todavía requiere una nueva corrida en GitHub. El instalador del producto usa el mismo instalador del runner y también recibe la corrección.

El `timings.json` separado del recolector incluye todos los jobs y pasos finales. El tiempo total va desde el inicio de la corrida hasta el último job terminado; la suma de tiempos de jobs incluye trabajo paralelo y por eso difiere. El tiempo en cola se informa aparte. El recolector lee metadatos de GitHub y nunca descarga ni ejecuta artefactos de la corrida probada.

## Reproducir o investigar localmente

Usar un checkout limpio separado con Python 3.12 y Ubuntu 22.04; restaurar dependencias escribe en directorios ignorados. El instalador apunta a un runner descartable y usa sudo para instalar paquetes del sistema. Ver [restauración de dependencias](REPOSITORY_LAYOUT-es.md), [guía del desarrollador](../AGENTS-es.md) y los scripts para fuentes fijadas y orden exacto de parches.

```sh
bash tools/ci/install-runner.sh
python3 tools/ci/bootstrap.py --fixtures
```

Ejecutar `tools/ci/windows-reference.ps1` en Windows con los mismos fixtures de `out/` y `ci-fixtures.json`, y devolver su `reports/ci/windows-reference.json` sin regenerar fixtures. Continuar en Linux:

```sh
python3 tools/ci/bootstrap.py
xvfb-run -a python3 tools/ci/run-matrix.py --profile platform-v1
python3 tools/ci/report.py
```

Para una investigación acotada, usar un directorio nuevo de informes:

```sh
xvfb-run -a python3 tools/ci/run-matrix.py --case metadata --report-dir reports/ci-metadata-retry
```

Las corridas acotadas se marcan incompletas y no certifican el contrato entero. Conservar los informes anteriores. Los checks de fuentes se ejecutan sin SDK:

```sh
python3 tools/ci/check-locks.py
python3 -m unittest discover -s tools/ci -p 'test_*.py'
python3 tools/check-docs-bilingual.py
python3 tools/build-doc-index.py --check
```

El builder canónico admite `--fixtures-only` sin SDK y `--diagnostics-only` para reutilizar esos fixtures. Las sondas de servicios usan la misma derivación privada de libc que el builder Wine; ninguno edita el archivo del SDK. No se comitean ni suben como artefactos de fuentes checkouts externos, prefijos, binarios del emulador, credenciales ni notas privadas.

## Decidir la siguiente fase

La validación de implementación usó WSL local preparado, no un runner en frío: pasaron checks de documentación/locks/marca, cuatro tests de rechazos del evaluador, referencias Windows nativas y pruebas del host con sanitizadores. La primera matriz completa registró 29 resultados esperados de 31 en unos 6,4 minutos, incluyendo el bloqueo esperado del oficial y los cuatro casos de servicios. Dos casos del fork agotaron el timeout al arrancar; una repetición acotada aprobó `pe-fourk-preferred`, pero volvió a agotar el tiempo en `pe-dll-symbol`. El informe completo original sigue fallido. Xvfb no estaba disponible localmente y esas corridas usaron WSLg; CI instala Xvfb. El piloto de GitHub debe determinar si ese fallo de arranque se reproduce allí.

Usar el primer piloto en frío completado para decidir qué checks pueden correr en PR o main con tiempo y costo aceptables. Configurar checks requeridos y protecciones sólo después de verificar corridas satisfactorias en GitHub. El staging del producto completo, las pruebas GUI y la validación en consola requieren criterios propios antes de generar una distribución OrbisDesk desde main.
