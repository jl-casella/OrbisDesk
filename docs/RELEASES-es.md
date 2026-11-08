# Construcción del producto, releases y rama de desarrollo

[English](RELEASES.md) | [Español](RELEASES-es.md)

## Estado y alcance

`Build PKG and release` es un **workflow experimental de construcción limpia**, separado de la matriz de diagnósticos. Todavía no se demostró su primera construcción completa en GitHub. No copia un árbol compilado del desarrollador, usa un runner propio ni accede a la PS4 de casa. Una dependencia ausente, error de compilación, error de PKG o runtime inconsistente hace fallar la corrida e impide publicar.

El primer piloto puede revelar más supuestos de las recetas históricas. No describir este workflow como reconstrucción completa demostrada hasta inspeccionar una corrida satisfactoria y sus artefactos. La validación local cubrió sintaxis de workflows, compilación de Python y tests que rechazan entradas de distribución alteradas o inseguras; no compiló ni arrancó un producto nuevo.

## Piloto manual

Después de integrar esta implementación en `main`, abrir **Actions → Build PKG and release → Run workflow**:

1. Seleccionar `main`.
2. Dejar `publish` sin marcar en el primer piloto de construcción.
3. Ejecutar. Descargar `product-evidence-*` incluso si falla. La última fase `product-*` y su log identifican el siguiente problema de portabilidad.
4. Si termina bien, inspeccionar `product-candidate-*`, hashes y runtime completo. Probar ese candidato exacto en emulador y/o consola según corresponda; compilar no valida el arranque.
5. Para publicar un candidato, ejecutar manualmente con `publish` marcado. Se hace una compilación limpia nueva en el SHA de esa corrida; no promociona el binario probado anteriormente ni hereda aceptación física.

Tanto el actor como quien reejecuta una corrida manual deben coincidir con el owner. Otros usuarios con escritura pueden ver el botón Run workflow, pero la autorización falla antes de compilar. También se exige `refs/heads/main`. Es una comprobación del workflow, no reemplaza proteger cambios a los workflows o a main. Ver [contextos de GitHub](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts).

## Releases automáticas desde main

El workflow declara `push: branches: [main]`, que cubre pushes directos y PRs integrados. Las corridas automáticas quedan omitidas hasta que el owner configure la variable de Actions **`ORBISDESK_AUTO_RELEASE=true`** después de un piloto manual satisfactorio. Borrar esa variable o ponerla en false vuelve a operación manual. Así el merge que introduce la receta aún no probada no publica automáticamente.

Una vez habilitado, cada push a main ejecuta los mismos checks y construcción limpia; crea el tag y publica una **prerelease experimental** sólo si pasan todos los jobs requeridos. No se dispara desde `dev`, PRs ni pushes de tags. Si falla publicar, queda un borrador en vez de una release pública incompleta. Los jobs de construcción tienen permisos de lectura; sólo el publicador separado tiene `contents: write`.

La configuración del repositorio debe proteger main con los checks de PR ya verificados. Las reglas opcionales de revisores de environments pueden servir luego como gate de promoción; estos archivos no configuran revisores. GitHub lo documenta en [deployments y environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).

## Versiones, tags y notas

La versión del SFO y la del selector NORMAL/ROOT usan el mismo valor `NN.NN`. Se calcula como `ORBISDESK_RELEASE_VERSION_BASE + run_number del workflow - 1`, con base predeterminada `400` (04.00 en la corrida número 1). Las corridas omitidas/fallidas consumen números; los saltos son esperados. Reejecutar mantiene la versión. Antes de habilitar automatización, elegir una base superior a todas las versiones instaladas/manuales y coordinar ese rango con los builders físicos manuales. Agotar 99.99 falla explícitamente; nunca se reinicia la numeración.

El tag es `orbisdesk-<NN.NN>-<12 caracteres del SHA>`, apuntando al commit compilado exacto. Nunca se mueven tags existentes ni se sobrescribe una release ya publicada. Un reintento puede completar un borrador sólo del mismo tag/commit. En este despliegue inicial no se declara automáticamente una release estable/latest.

Las notas usan las notas generadas por GitHub y los asuntos de commits desde la release OrbisDesk publicada más cercana en la ascendencia del commit objetivo. La primera incluye el historial disponible. Las notas muestran el SHA y alcance de validación. Ver [API de releases de GitHub](https://docs.github.com/en/rest/releases/releases).

## Qué se construye y sube

[build-product.py](../tools/ci/build-product.py) restaura fuentes, SDK y archivos fijados en directorios ignorados, prepara Wine nativo y el prefijo sellado, compila servicios Unix PS4, ambas arquitecturas PE, RADV/Zink/loaders/layers, shell e invitados, y finalmente invoca el [builder canónico del paquete físico](../tools/build-wine-hardware.py). El orden sigue los manifiestos de entrada; no ejecuta builders alfabéticamente. Steam nativo es un producto separado y no se compila aquí.

La receta usa Ubuntu 22.04, Python 3.12, las versiones de toolchain comprobadas y .NET 8 para el empaquetador administrado del SDK. Los scripts gráficos resuelven el checkout actual en vez de la ruta Windows del autor. `~/vk-h0` se genera en el runner nuevo desde fuentes fijadas, sin copiarlo de una PC. Las URLs/hashes adicionales están en [product-assets.lock.json](../product-assets.lock.json); las dependencias existentes conservan sus locks originales.

La conversión histórica del fondo con System.Drawing en Windows se reemplaza por una conversión Pillow RGB/recorte/bicúbica registrada en la receta limpia; usa la misma foto CC0 fijada, pero puede cambiar el hash BMP. Se mantienen `ORBW00002` y el Content ID existente. Los nombres internos W288 del builder/runtime se conservan como identidad de receta/evidencia; la procedencia de release registra el SHA real y la versión SFO. Las construcciones locales siguen usando 03.87 salvo que se indique `--app-version`.

El candidato contiene:

- `OrbisDesk.pkg` y su `OrbisDesk-runtime.tar.gz` nuevo y correspondiente (contenido dentro de `data/`).
- Manifiestos de producto/construcción/release con identidad de fuentes, inventario y hashes.
- `SHA256SUMS`, `THIRD_PARTY.md`, `LICENSES.tar.gz` e instrucciones de instalación.

Los runtimes grandes se dividen en `.partNNN` ordenados por debajo del límite individual de assets de GitHub. No se recolectan registros de consola, documentos, credenciales, checkouts descargados ni notas privadas de una PC. Las fuentes y avisos requeridos que el builder incorpora explícitamente al runtime siguen formando parte del producto.

[release.py](../tools/ci/release.py) rechaza PKGs cambiados, fuentes cambiadas, archivos extra/ausentes del runtime, contenido alterado, enlaces y rutas que escapen. Sube a un borrador, comprueba inventario y hashes SHA-256 remotos y después publica. Un build fallido nunca llega a ese job. Los gates actuales son empaquetado/importaciones: arranque Wine, smoke GUI y aceptación física quedan explícitamente pendientes. La matriz de 31 casos sigue siendo otro workflow manual y todavía no es prerrequisito de release.

El workflow admite seis horas para compilar desde cero. Es un límite, no una duración medida. Disco/memoria del runner, disponibilidad de archivos, configuración de fuentes, subproyectos gráficos y supuestos obsoletos pueden bloquear el primer piloto. Conservar los fallos reales y corregir la receta canónica; no restaurar un runtime local para ponerlo verde.

## Instalación y flujo dev → main

El PKG solo no alcanza: también necesita su runtime en `/data`. Seguir las instrucciones del candidato, respaldar registros/documentos/configuración/partidas y usar una actualización que preserve cambios del usuario si ya existe una instalación. El archivo es un runtime nuevo; reemplazar un prefijo instalado sin combinar puede perder estado. Actions no hace transferencias FTP ni instala en consola.

Cuando funcione la construcción limpia, crear `dev` desde el main de ese momento. Los PRs diarios de features/fixes apuntan a `dev` y ejecutan checks rápidos. Con un conjunto coherente listo, abrir un PR `dev → main`, revisar/probar ese conjunto e integrar. Con releases automáticas habilitadas, ese push a main lo construye y publica. Mantener main protegida, no integrar dev automáticamente y conservar builds manuales para investigar. La rama **no** se creó con este cambio de workflow.

Ver también [operación de CI](CI-es.md), [plan de CI](CI_PLAN-es.md), [estructura de dependencias](REPOSITORY_LAYOUT-es.md) y [guía del desarrollador](../AGENTS-es.md).
