# Plan de CI: checks rápidos de PR, piloto manual de matriz y distribuciones

[English](CI_PLAN.md) | [Español](CI_PLAN-es.md)

Estado: fases 1–3 implementadas para revisión, 2026-11-07; el primer piloto en frío de GitHub sigue pendiente. Ver [ejecutar CI](CI-es.md) para parámetros, evidencia y activación. Las fases 4–6 siguen propuestas. No cambian las protecciones de ramas ni los releases del producto; la primera corrida manual dará los datos para decidir dónde ejecutar las comprobaciones pesadas.

Continuación del 2026-11-07: el owner pidió construcción limpia en GitHub y releases manuales/automáticas desde main. La [guía de releases](RELEASES-es.md) separada describe la implementación experimental, activación y límites. Sigue pendiente el primer piloto satisfactorio del producto limpio; la matriz de diagnóstico aún no es gate automático de release. La propuesta de promoción siguiente queda como política futura más estricta, no como comportamiento activo.

## Objetivo y despliegue por etapas

```text
PR 1: checks rápidos en pull requests
  -> PR 2: recrear prerrequisitos y definir el contrato de la matriz
  -> PR 3: matriz workflow_dispatch + un piloto frío medido
  -> decidir según el total y los tiempos de cada fase
  -> PR 4: ubicar checks seleccionados en PRs y/o push a main
  -> PR 5: hacer portable la build completa desde un clon limpio
  -> PR 6: validación exitosa de main produce una distribución candidata
```

El workflow manual precede a exigir automáticamente la matriz del emulador a los colaboradores. Aprobar la matriz de plataforma certifica su alcance declarado; no certifica el escritorio Wine moderno, la compatibilidad física ni juegos arbitrarios.

## Base de tiempos

Son mediciones locales de WSL o informes históricos, no benchmarks de runners de GitHub:

| Trabajo | Tiempo observado | Condición |
| --- | --- | --- |
| Documentación, índice, estructura y marca | Unos 16 segundos | Medido con el árbol de trabajo disponible |
| VM y parser PE anfitriones | Unos 4 segundos | Fuentes y fixtures generados disponibles |
| Campaña histórica del incremento 18, 31 ejecuciones | Unos 4 minutos de reloj | Emulador/ELFs/referencias compilados; 162 segundos de ejecución registrados |
| Campaña histórica GUI/texto, cuatro ejecuciones | Unos 5 minutos de reloj | Wine/runtime preparados; separada de la matriz de plataforma |
| Compilación incremental reciente del emulador | Unos 2 minutos | No mide compilador/submódulos/build desde cero |

Objetivo inicial para checks rápidos de PR: 2–5 minutos con preparación incluida. Los presupuestos manuales originales eran 90 minutos globales, 45 para preparación/build y 20 para pruebas. Una corrida de rama en GitHub midió después 41 min 30 s para compilar el emulador y alcanzó el límite de pruebas de 20 minutos. La [guía de CI](CI-es.md) actual usa por eso reutilización verificada del emulador/ccache y presupuestos de 150 minutos globales, 20 para preparación, 60 para compilación y 40 para pruebas; no cambian los límites por caso. Son límites, no tiempos prometidos. Instalaciones/descargas también necesitan reintentos y tiempos máximos finitos.

## PR 1 — checks rápidos en pull requests

Archivos propuestos: `.github/workflows/ci-pr.yml` y pequeños auxiliares si hacen falta. Empezar con Ubuntu 22.04 x64, acorde al entorno anfitrión usado; fijar acciones externas por SHA de commit revisado.

Activar con `pull_request` y opcionalmente `workflow_dispatch`. Empezar por:

```sh
python3 tools/check-repository-layout.py
python3 tools/check-docs-bilingual.py
python3 tools/build-doc-index.py --check
python3 tests/test_project_brand.py
python3 -m compileall -q tools tests
```

Agregar un job VM anfitrión que descargue sólo la fuente fijada de `prospero-win` y ejecute `bash tools/test-vm.sh`. Agregar un check de locks/hashes de parches que lea los locks versionados sin descargar todas las dependencias. Añadir `bash tools/test-pe32.sh` cuando PR 2 pueda generar sus fixtures de manera independiente.

Los jobs iniciales de metadatos/marca no necesitan SDK, Wine, emulador, FTP ni consola. Timeout de job de 10 minutos, permisos de repositorio de sólo lectura y cancelación de corridas anteriores reemplazadas del mismo PR. Fallar si falla un check y guardar logs relevantes. No ejecutar código de PR no confiable mediante `pull_request_target` con permisos de escritura o credenciales de consola.

Aceptación: un PR documental pequeño y un enlace/hash de parche deliberadamente incorrecto muestran las rutas de éxito y fallo; ningún directorio privado/dependencia entra en artefactos. Habilitar checks requeridos en protección de rama sólo después de comprobar nombres y comportamiento en GitHub.

## PR 2 — prerrequisitos autónomos y contrato de matriz

Puntos de entrada propuestos, todavía inexistentes: `tools/ci/build-prerequisites.py`, `tools/ci/run-matrix.py` y contrato versionado `tests/ci-matrix.json`. Reutilizar implementaciones existentes en lugar de duplicar la lógica de pruebas dentro de YAML.

El [checker histórico del incremento 18](../tools/check-increment18.py) sirve como referencia de cobertura, no como entrada CI desde un clon limpio. Sus 31 ejecuciones principales son **27 de plataforma/PE** (incluida la comparación con el emulador oficial) y **4 de servicios**. El informe contiene además múltiples aserciones de servicios dentro de esas ejecuciones.

Preparación requerida:

1. Restaurar sólo las dependencias del perfil seleccionado verificando commits y hashes. Automatizar extracción del emulador Linux/runtime privado y preparación mínima OpenOrbis/toolchain hoy asumida localmente. Respetar el disco disponible y registrar su uso inicial/máximo.
2. Añadir generación independiente de fixtures para parser PE anfitrión y emulador. No exigir Wine/gráficos completos sólo para crear fixtures PE propios; fijar MinGW y timestamps deterministas.
3. Generar referencias en un runner Windows usando los **mismos binarios de fixtures**. Pasar fixtures y referencias a Linux con sus SHA256 y SHA fuente. No descargar el `reports/` histórico del desarrollador como baseline ni inventar referencias faltantes.
4. Compilar el fork fijado de shadPS4 con su overlay y el ELF de diagnóstico. Conservar controles de identidad fuente/árbol/diff/binario. Un acierto de caché no reemplaza la validación de entradas.
5. Separar las cuatro sondas existentes IPC/pipes/archivos/metadatos del enlace actual del bootstrap Wine completo si sus implementaciones nativas pueden compilarse como ELF de servicios sin modificar aserciones. Revisar [wine_boot.c](../native/wine_boot.c) y las sondas nativas existentes. Demostrar equivalencia con la ruta actual. Si no se pueden preservar sus semánticas, restaurar los prerrequisitos reales de Wine y registrar el costo extra; no usar stubs para evitarlos.
6. Revisar cada expectativa histórica contra el comportamiento correcto actual antes de fijar `platform-v1`. Una corrección intencional puede invalidar una aserción antigua. Conservar informes históricos como tales; no reescribir resultados viejos ni aceptar cualquier fallo como bloqueo conocido.

Reglas del contrato:

- Cada caso declara ID, tipo de emulador, identidad ELF/fixture, resultado esperado, timeout, marcadores requeridos y condiciones de salida/resultado.
- El caso del emulador oficial fijado puede declarar un bloqueo esperado. Debe coincidir su firma específica: un timeout/crash arbitrario no equivale. Informar `contract_passed` separado de resultados individuales `passed`/`blocked` y del estado de arranque Wine. Un éxito inesperado también requiere revisar el contrato.
- Prerrequisitos faltantes fallan en preparación. Durante desarrollo puede seleccionarse explícitamente `platform-core` incompleto con las 27 ejecuciones base, pero no presentarlo como perfil completo de 31. El perfil completo no puede aprobar omitiendo servicios.
- Preferir proceso nuevo del emulador y copia privada de datos por caso. Separar logs/informes y conservar salida exacta, timeout y último marcador.
- GUI/Wine será otro perfil futuro. La matriz de plataforma no ejecuta el escritorio empaquetado actual ni establece compatibilidad PE32 nativa/GPU del fork.

Aceptación: preparar y ejecutar el perfil diagnóstico completo sin `build/`, `out/` o `reports/` previos. Un fixture/referencia faltante y una expectativa deliberadamente incorrecta fallan de forma visible. Validar primero sobre filesystem Linux, no sólo en el workspace Windows montado original.

## PR 3 — workflow manual y primera corrida medida

Workflow propuesto: `.github/workflows/matrix-manual.yml`, al principio sólo con `workflow_dispatch`. GitHub necesita ese workflow en la rama por defecto para habilitar el disparador manual. Mantener la implementación de pruebas en scripts/workflows reutilizables para aprovecharla después desde PR y main.

Entradas:

| Entrada | Valores/propósito inicial |
| --- | --- |
| `profile` | `platform-v1` por defecto; `platform-core` claramente incompleto |
| `cache_mode` | `cold` o `reuse`; frío omite todas las cachés de build/dependencias |
| `official_comparison` | Obligatorio para el perfil completo; omitirla cambia el perfil declarado |

Usar el selector de rama/ref de GitHub y registrar el SHA resuelto del checkout. No tomar «último» arbitrariamente. Fijar familia de runner/toolchain y usar Xvfb/Lavapipe cuando haga falta, separando oficial y fork. Empezar con casos secuenciales en un job Linux para compararlo con la medición local. Paralelizar recién cuando se compruebe que no comparten prefijo, perfil del emulador ni salidas.

El **primer piloto es una corrida fría** sobre el commit seleccionado. Medir por separado:

1. checkout y descarga de fuentes/artefactos;
2. verificación y extracción de dependencias;
3. compilación de fixtures y job de referencias Windows;
4. compilación del emulador y ELFs de diagnóstico/servicios;
5. cada prueba y ejecución total de matriz;
6. compresión/subida de informes y artefactos;
7. tiempo total del workflow, duración de jobs y pico de disco.

Guardar `timings.json`, `matrix-report.json`, tabla en el resumen del job, manifiestos, logs de fallo y referencias/resultados relevantes. Subir evidencia diagnóstica con `always()` después de un fallo; usar lista explícita de archivos, eliminar credenciales y limitar tamaño/retención. Una corrida fallida puede subir evidencia de diagnóstico, pero no una distribución candidata exitosa.

El resumen identifica frío/caliente, runner, SHA fuente, hashes de locks, identidad fuente/binario del emulador, perfil, resultados esperados/observados y cantidades. El tiempo total de reloj y la suma de jobs difieren si Windows/Linux se solapan: informar ambos. La espera en cola puede informarse aparte de la ejecución.

Una segunda corrida opcional del mismo SHA con reutilización de caché mide el caso caliente. Es útil, pero no obligatoria para revisar la primera. Una corrida da una estimación inicial, no el percentil 95 ni la tasa de fallos intermitentes. Si el piloto falla en preparación, aporta tiempos útiles, pero no representa un benchmark de matriz completada.

Aceptación: lanzarlo desde Actions, descargar el informe y decidir PR 4 con los tiempos/resultados reales. Este piloto no modifica la PS4 local ni despliega por FTP.

## PR 4 — elegir cobertura de PR/main después de medir

Umbrales propuestos, ajustables tras la primera corrida:

| Comportamiento medido | Ubicación propuesta |
| --- | --- |
| La matriz completa entra de forma confiable en unos 10 minutos con preparación | Considerarla en PRs relevantes; mantener checks rápidos en todos |
| Unos 10–25 minutos | Perfil completo en `push` a `main`; perfil reducido verificado en PRs relevantes |
| Más de 25 minutos o inestabilidad importante | Completa manual/nocturna mientras se divide trabajo o mejora caché/bootstrap |

Preferencia inicial: checks rápidos requeridos en PR y validación completa en main. Filtrar trabajo pesado de PR por cambios de cargador/VM/ABI, adaptadores Wine, builders gráficos/runtime, fixtures y locks/parches. Los cambios sólo documentales mantienen checks rápidos. No hacer desaparecer jobs requeridos por un filtro de rutas dejando la protección esperando: usar un check estable que registre la decisión válida de no aplicabilidad.

`push` a `main` valida el SHA realmente mergeado; un resultado del merge-ref del PR no demuestra automáticamente ese nuevo SHA. Si se incorpora merge queue, añadir cobertura del grupo de merge antes de exigirla allí. Mantener `workflow_dispatch` para repeticiones e investigaciones.

Cachear sólo rutas explícitas de SDK/fuentes/herramientas/intermedios, con claves derivadas de OS/arquitectura, compilador, locks, hashes de parches ordenados, recetas y SHA fuente según corresponda. Verificar binarios/manifiestos restaurados. No cachear `.deps/` entero: esta computadora guarda `.deps/ssh/` allí. Prefijos, estado del usuario, credenciales y notas privadas no pertenecen a cachés/artefactos compartidos. Separar cachés de PR de entradas confiables de publicación.

Aceptación: nombres estables de checks requeridos; un PR de runtime recibe la cobertura prevista, uno documental termina normalmente y el merge se prueba con su propio SHA. La decisión registra el piloto frío y cualquier corrida caliente, sin tratar tiempos históricos locales como medición GitHub.

## PR 5 — build portable del producto completo

Es distinto de hacer ejecutable la suite diagnóstica de 31 casos. Resolver los huecos de [estructura del repositorio](REPOSITORY_LAYOUT-es.md): rutas particulares, configure anfitrión de Wine, generación del prefijo, gráficos/compiladores, cierres PE e informes de entrada. El grafo está mapeado en [AGENTS](../AGENTS-es.md).

Workflow reutilizable propuesto: `.github/workflows/build-product.yml`. Generar paquete principal, runtime completo y manifiestos desde un único SHA resuelto. Mantener explícitos los recursos opcionales/pins. Validar identidades de paquete/SFO, arquitecturas/imports PE, hashes, licencias y distribución del runtime esperada por el uploader. Preservar ajustes e identidad de actualización de consola.

Aceptación: un runner limpio produce `OrbisDesk.pkg` y su runtime coincidente sin copiar una build del desarrollador. Registrar tiempos fríos e incrementales/caché por separado. Agregar smoke del escritorio empaquetado con runtime nuevo: los límites del fork/native32/gráficos quedan visibles, sin ocultarlos reutilizando un runtime local inicializado. Empaquetar correctamente no equivale a aprobar ese smoke.

## PR 6 — candidatas de distribución sólo después de validar main

Hay dos salidas con alcances distintos:

- **Bundle diagnóstico:** ELF diagnóstico/servicios probado, fixtures PE propios, resultados y procedencia. Puede ser un artefacto cuando funcione PR 3; no es la distribución completa de OrbisDesk.
- **Candidata del producto:** `OrbisDesk.pkg`, payload completo del runtime `/data`, instalación, dependencias/atribuciones, checksums y procedencia de build/pruebas. Requiere PR 5 y probar los binarios candidatos exactos.

Proponer `.github/workflows/dist.yml` o un job condicionado dentro del workflow de main:

```text
push main -> checks rápidos -> matriz de plataforma requerida
          -> build del producto -> smoke empaquetado con runtime nuevo
          -> artefacto de distribución (sólo si aprobaron todas las dependencias requeridas)
          -> promoción manual opcional tras feedback de PS4
```

Usar `needs` y condiciones de éxito explícitas. Preferir dependencias entre jobs de la misma corrida a asociar workflows separados por nombre de rama. Si se usa `workflow_run`, descargar artefactos del ID/SHA exactos de la corrida exitosa y comprobar procedencia; no ejecutar artefactos de PR no confiables con permisos de publicación. No probar un binario y recompilar silenciosamente otro para distribuir: empaquetar primero y probar esa salida, o exigir hashes idénticos verificados.

Nombrar candidatas por commit/corrida, por ejemplo `OrbisDesk-dist-<shortsha>.zip`; incluir `SHA256SUMS` y manifiesto con SHA fuente, identidad compilador/locks/parches, hashes de binarios/runtime, matriz y alcance del smoke. Un contrato diagnóstico verde puede incluir un bloqueo oficial declarado; no permite afirmar compatibilidad oficial/física. Un smoke empaquetado requerido fallido bloquea la distribución del producto aunque pasen los diagnósticos.

Empezar con artefactos descargables de Actions, no una GitHub Release estable automática. Una promoción separada, protegida/manual, podrá crear prerelease/release de la misma candidata verificada tras el feedback PS4 requerido. Subir/instalar por FTP sigue siendo un flujo separado solicitado explícitamente; no incluir despliegue a una consola doméstica en cada PR/check de main.

Aceptación: una prueba fallida deliberadamente bloquea la candidata; su SHA coincide con lo probado; el usuario recibe paquete y runtime; los informes distinguen presentación en emulador de validación física. Las notas de release separan candidatas experimentales de entregas aceptadas en hardware.

## Archivos y orden de implementación

Los nombres de workflows/auxiliares anteriores son archivos propuestos, no comandos disponibles hoy. Implementar primero PR 1; luego PRs 2–3 para obtener la medición real solicitada. No decidir ubicación automática en main/release antes de revisar el piloto. Los PRs 5–6 pueden dividirse en implementaciones menores al medir su grafo de build.

Mantener este plan bilingüe, regenerar el [índice](INDEX-es.md) y registrar URL de la primera corrida GitHub, SHA, resultado y tiempos por fase en un informe/documento nuevo cuando exista. No presentar tiempos locales como si fueran esa corrida.

Referencias primarias: [workflows manuales](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow), [sintaxis y dependencias](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax), [artefactos](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts), [caché de dependencias](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching).
