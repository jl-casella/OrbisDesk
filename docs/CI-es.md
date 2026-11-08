# Ejecutar CI y medir la matriz de plataforma

[English](CI.md) | [Español](CI-es.md)

## Qué está implementado

Las primeras tres fases del [plan de CI](CI_PLAN-es.md) aportan checks rápidos de PR, construcción independiente de fixtures/servicios y una matriz manual de plataforma. Todavía hace falta una corrida en un runner nuevo de GitHub para establecer el tiempo en frío. Las corridas locales con dependencias ya instaladas no establecen esa referencia.

Los workflows son:

| Workflow | Disparador | Propósito |
| --- | --- | --- |
| `PR checks` | Pull request o manual | Documentación, estructura, locks, Python y pruebas del host de VM/parser con sanitizadores; cada PR también ejecuta la matriz completa tras aprobar esos checks |
| `Manual platform matrix` | Manual o llamada como workflow reutilizable | Producir fixtures, ejecutar los mismos binarios en Windows, preparar dependencias Linux, compilar y ejecutar el contrato de diagnóstico |
| `Collect matrix timings` | Finalización de la matriz manual o de PR checks | Leer tiempos finales de jobs y pasos desde GitHub; subir `timings.json` |

Estos workflows de diagnóstico no publican releases, compilan el escritorio Wine completo, acceden por FTP ni cambian protecciones de ramas. Una matriz satisfactoria sube únicamente un paquete de diagnósticos. El [workflow experimental de release](RELEASES-es.md) separado intenta la construcción completa limpia; su primer piloto satisfactorio en GitHub sigue pendiente.

El job de PR `Platform matrix` llama al mismo workflow con `profile=platform-v1` y `cache_mode=reuse`, probando el SHA de merge del PR con perfiles diagnósticos nuevos. Se ejecuta en cada PR, incluidos cambios documentales, después de que aprueben `metadata` y `host`; si falla, el workflow de PR no queda aprobado. Las ejecuciones manuales de PR checks y la llamada del workflow de release conservan sus checks rápidos existentes; para diagnósticos a demanda usar la matriz manual separada. Exigir un check para permitir el merge sigue requiriendo configurar las protecciones/reglas del repositorio; este cambio no modifica esos ajustes. Cancelar una corrida de PR reemplazada también cancela su matriz invocada. No se pasan secretos al workflow reutilizable y checkout no conserva credenciales.

El piloto satisfactorio [42492292470](https://github.com/jl-casella/OrbisDesk/actions/runs/42492292470) en `10f0e0ddce5f8ee1db2f4a4b00342a01d06518b8` terminó en 333 segundos: 30 aprobados del fork y el bloqueo oficial exacto esperado, 52,206 segundos ejecutando la matriz y reutilización verificada del binario del emulador en 5,421 segundos. Preparar las fuentes llevó 116,347 segundos. Es una medición con caché, no una garantía de tiempo en frío ni para futuros PRs; la visibilidad de caché en un PR puede diferir de las corridas de rama.

## Primera corrida medida

1. Integrar la implementación en la rama predeterminada. GitHub necesita conocer allí el workflow manual antes de seleccionarlo en Actions. El recolector de tiempos también debe existir allí.
2. Abrir **Actions → Manual platform matrix → Run workflow**. Elegir la rama/revisión deseada, `profile=platform-v1` y `cache_mode=cold`.
3. Esperar tanto la matriz como el recolector separado. Una preparación fallida es un piloto fallido, no una matriz aprobada.
4. Descargar `matrix-evidence-*` de la matriz y `matrix-timings-*` del recolector. Registrar URL, SHA, resultado, tiempo total, suma de tiempos de jobs y duración por fase.
5. Repetir con `cache_mode=reuse` (ahora predeterminado) para medir el caso caliente. Restaura descargas verificadas, el binario del emulador si coincide exactamente y caché del compilador para reconstrucciones. Se reconstruyen los ELF/fixtures de diagnóstico y se ejecutan todas las pruebas seleccionadas. Las corridas frías omiten restaurar cachés, pero pueden generarlas para corridas futuras.

Los límites acotan el piloto: 200 minutos para el job Linux, 20 para preparación, un límite interno del emulador de 80 minutos dentro de un paso Actions de 90, y 40 para ejecutar la matriz. Separar los límites deja tiempo para terminar el grupo de procesos, registrar estadísticas de caché y guardar evidencia. Cada caso conserva 60 segundos. La suma máxima de los 31 casos es 31 minutos, de modo que el límite global anterior de 20 podía interrumpir una campaña de fallos legítima. Se guarda el informe antes y después de cada caso, con casos activos/pendientes y `execution_completed=false` hasta terminar el bucle. Cancelar o agotar el límite global nunca implica éxito; los fallos por caso siguen siendo fallos.

## Cachés del emulador y compilador

Sólo se cachean `.deps/emulator-cache`, `.deps/ccache` y el directorio existente de descargas verificadas. El paquete del emulador contiene el binario del fork, su manifiesto original, diff y prueba de caché. La clave vincula commit/árbol/diff restaurados, revisiones limpias de submódulos, identidades de parches/overlay fijados, recetas, binarios/versiones de compilador/scanner/linker/CMake/Ninja/ccache, versiones de paquetes instalados, arquitectura, entorno y ruta del checkout. El commit de OrbisDesk por sí solo no es la clave: cambios ajenos al emulador en aplicación o documentación pueden reutilizarlo.

La caché de descargas se limita a tres archivos completos: `openorbis.tar.gz`, `shadps4-linux.zip` y `libc6.deb`. Después de preparar, incluso si falló una etapa posterior de preparación, una comprobación separada verifica cada archivo presente contra su lock y lo guarda antes de compilar. Al restaurar se prefieren entradas completas de tres archivos y luego entradas parciales verificadas; nunca se guardan `.part`. Así un fallo posterior del emulador ya no impide conservar el SDK descargado. Las corridas frías también guardan descargas completas verificadas para futuras reutilizaciones.

El descargador reintenta HTTP transitorios 408/429/500/502/503/504 y errores de transporte hasta seis intentos, con pausas de 5/10/20/40/60 segundos y ajuste numérico acotado de Retry-After. Registra intentos en Actions y `download-attempts.jsonl`. Los HTTP permanentes y hashes incorrectos siguen fallando; cada archivo descargado o restaurado debe coincidir con SHA-256 antes de extraer. Si el servicio remoto sigue indisponible, la corrida falla en lugar de cambiar de SDK o aceptar bytes incompletos. `--check-download-cache` sólo verifica archivos comprimidos completos y nunca los extrae.

Al restaurar se comprueban identidad, hash del manifiesto y hash del ELF64 antes de instalar el binario para la matriz. Una caché corrupta o incompatible falla explícitamente; no se la declara compatible. Usar `cold` y borrar la caché inválida en GitHub si hace falta. Se conserva la procedencia de compilación original; `emulator-cache.json` registra por separado la reutilización actual. Un hit no es un test aprobado ni validación física.

Si no existe el binario exacto, se configura desde cero usando ccache como launcher C/C++. La caché del compilador tiene límite de 2 GiB y puede recuperar objetos compatibles entre cambios de fuentes; se mantienen las comprobaciones normales de dependencias/contenido. Las compilaciones satisfactorias se guardan **antes** de ejecutar la matriz, para no perder esos 40 minutos si luego falla un test. También se puede guardar trabajo parcial tras una compilación fallida. Las estadísticas están en `ccache-stats.log`; claves e identidades en `emulator-inputs.json`.

Durante la compilación, el helper muestra las últimas líneas de configuración/build cada minuto. Si falla, también imprime esos logs internos, no sólo el traceback Python exterior. Los subprocesos POSIX con timeout de CI usan un grupo propio; al vencer el límite se termina tanto el driver como Ninja y sus compiladores antes de recoger estadísticas. `emulator-build-failure.json` registra el tipo de error y los logs disponibles. Estos cambios mejoran diagnóstico y limpieza; ampliar el presupuesto no demuestra resolver un posible bloqueo de fondo.

La primera corrida de esta implementación todavía necesita compilar: los workflows anteriores no guardaban el binario ni los objetos. GitHub puede expirar/expulsar cachés o impedir su acceso entre ramas; una caché de feature no necesariamente sirve después del merge a main. Hay que medir un hit real en GitHub antes de prometer duración caliente. El workflow de release sigue necesitando su construcción limpia del producto y no reutiliza un runtime de consola.

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

El piloto posterior en `b2f2d8e3e38b22bb727d8581f5e544a40df466bc` terminó la configuración y después falló al analizar dependencias C++ con `CMAKE_CXX_COMPILER_CLANG_SCAN_DEPS-NOTFOUND`. Instalar sólo `clang-19` no incorporaba el scanner. Ahora el runner instala `clang-tools-19`, verifica `clang-scan-deps-19 --version` y pasa su ejecutable resuelto a CMake. También instala Ninja 1.13.0 privado: el escaneo necesita Ninja 1.11+, mientras el Ninja del sistema Ubuntu 22.04 puede ser 1.10. El builder comprueba las herramientas antes de configurar, registra sus identidades en el manifiesto y rechaza cachés reutilizadas con rutas ausentes/diferentes. Un smoke local independiente C++23 con CMake 4.2.3, LLVM 19.1.7 y el Ninja fijado completó escaneo, compilación, enlace y ejecución; valida el toolchain, no una compilación completa de shadPS4 ni la matriz. La siguiente corrida en GitHub debe comprobar esto último.

La corrida de rama en `b6ad6331104955be70f176756968d2c2588349c7` completó después la compilación del emulador en 2.489,7 segundos (41 min 30 s) y la preparación en unos 43 min 11 s. Su paso de matriz alcanzó el límite anterior de 20 minutos; el fragmento suministrado no demuestra causas individuales ni una matriz completada. Ese resultado motivó los cambios de caché, límite e informes parciales anteriores. La implementación actual todavía necesita validar un hit real y una matriz completa en GitHub.

La corrida `42447432083` en `1573d57d4619c8f8c09e8d0cce33d69a490a44bb` duró 3.868 segundos globales y alcanzó el límite interno anterior de 3.600 segundos (el paso Actions duró 3.605). Preparar llevó 142 segundos. Guardar la caché del compilador terminó correctamente en cuatro segundos; se omitieron guardar el binario verificado y ejecutar la matriz. El artefacto de tiempos suministrado no incluye tamaño/aciertos de caché ni el log interno, por lo que no establece la causa de la demora. Antes vencían juntos los límites interno y externo; ahora están separados como se describe arriba. Revisar `matrix-evidence-*`, especialmente `build/shadPS4-linux/build.log` y `reports/ci/ccache-stats.log`, antes de atribuir la demora a compilación, configuración o caché.

La corrida posterior en `49c95f07c1ef7a759be007a3a5dd1cdb77925ab0` restauró las fuentes en 106 segundos y después falló al descargar el SDK con HTTP 504 tras unos 14 segundos. No llegó a compilar. Los cambios de reintentos/caché temprana atienden ese fallo de transporte observado; no demuestran recuperación del servicio remoto ni resolver la demora de compilación anterior. Las pruebas locales cubren reintentos acotados, errores permanentes, rechazo de hashes y verificación de caché parcial sin descargar ni extraer un SDK real.

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

## Fallo de arranque en GitHub: corrida 42484812050

La evidencia suministrada para `24c6a981e574bc6f86fe44b14e49dd28a3780315` registra 31 timeouts de 60 segundos, sin marcadores diagnósticos del invitado. Compilar el emulador llevó 588,702 segundos; el informe de caché dice `reused=false`, por lo que no demuestra reutilización del binario. Tanto oficial como fork sólo muestran el comando inicial en stdout. El CMake cache de GitHub habilita X11. Esta evidencia no establece la causa: el runner anterior descartó el perfil temporal con los logs internos del emulador.

Ahora cada caso conserva `launch.json`, `emulator-evidence.json` y logs/configuración del perfil privado en `cases/<id>/emulator-user/` antes de limpiarlo. Revisar **ambos** archivos `log/shadps4.log` y `log/shad_log.txt`: shadPS4 cambia de log durante el arranque. Se conservan los últimos 16 MiB por archivo, registrando truncamiento; se excluyen enlaces simbólicos y rutas externas. No se lee un perfil real. Los directorios de usuarios vacíos evitan el diálogo incondicional de migración del primer usuario del emulador fijado; shadPS4 sigue generando sus propios ajustes. Esto no demuestra que el timeout de GitHub esté resuelto.

El workflow activa `--stop-on-startup-failure`: si el par inicial fork/oficial ejecuta la misma sonda y ambos agotan el tiempo sin marcadores del invitado, detenerse tras esos dos casos (normalmente unos dos minutos), conservar evidencia, fallar la corrida y dejar los demás pendientes. Es una matriz incompleta y fallida, nunca aceptación ni un bundle diagnóstico satisfactorio. Si cualquiera emite marcadores, continuar el perfil seleccionado normalmente. Para investigar localmente, omitir la opción para ejecutar todos los casos seleccionados o usar `--case console32 --case console32-official --report-dir reports/startup-check` con los fixtures/referencias habituales ya construidos.

Un intento local separado con Xvfb privado falló con `Failed to initialize SDL video subsystem: x11 not available` en el log interno, incluso preparando usuarios vacíos. Es evidencia local; no establece el fallo del runner GitHub. Recuperar los nuevos logs internos antes de cambiar el emulador o atribuir el timeout a Vulkan, Wine o al diálogo de migración.

## Aserción de salida en GitHub: corrida 42490428616

La corrida `42490428616` en `e109edfa3894ee1e48e6257500a8538035c42bba` completó los 31 casos en 41,399 segundos. Los 30 casos del fork coincidieron con el contrato, incluidas las cuatro sondas de servicios. Se reutilizó el binario exacto del fork (`reused=true`, duración del auxiliar 4,614 segundos). Los timeouts generales de arranque anteriores no se repitieron con los directorios de usuarios vacíos preparados.

El único rechazo fue la comparación oficial: el resultado del invitado y la salida de referencia Windows coincidieron, seguidos por la aserción esperada `process.cpp:312 exit: Unreachable code!`, pero Linux lo terminó con `SIGTRAP` (código de subprocess `-5`) en lugar del timeout observado localmente. El contrato ahora permite explícitamente `blocker_exit_codes: [-5]` para ese caso, además del timeout existente. Ambas variantes siguen exigiendo la aserción exacta, marcadores correctos del invitado y salida de referencia. Otras señales, salida normal sin la terminación esperada, marcadores ausentes o salida alterada fallan. Sigue siendo un **bloqueo oficial esperado**, no compatibilidad oficial aprobada. El informe original suministrado permanece fallido; reevaluar sus logs archivados no es una nueva ejecución del emulador ni una corrida verde de Actions.

## Decidir la siguiente fase

La validación de implementación usó WSL local preparado, no un runner en frío: pasaron checks de documentación/locks/marca, cuatro tests de rechazos del evaluador, referencias Windows nativas y pruebas del host con sanitizadores. La primera matriz completa registró 29 resultados esperados de 31 en unos 6,4 minutos, incluyendo el bloqueo esperado del oficial y los cuatro casos de servicios. Dos casos del fork agotaron el timeout al arrancar; una repetición acotada aprobó `pe-fourk-preferred`, pero volvió a agotar el tiempo en `pe-dll-symbol`. El informe completo original sigue fallido. Xvfb no estaba disponible localmente y esas corridas usaron WSLg; CI instala Xvfb. El piloto de GitHub debe determinar si ese fallo de arranque se reproduce allí.

Usar el primer piloto en frío completado para decidir qué checks pueden correr en PR o main con tiempo y costo aceptables. Configurar checks requeridos y protecciones sólo después de verificar corridas satisfactorias en GitHub. El staging del producto completo, las pruebas GUI y la validación en consola requieren criterios propios antes de generar una distribución OrbisDesk desde main.
