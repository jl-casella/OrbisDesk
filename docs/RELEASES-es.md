# Construcción del producto, releases y rama de desarrollo

[English](RELEASES.md) | [Español](RELEASES-es.md)

## Estado y alcance

`Build PKG and release` es un **workflow experimental del producto** que admite builds en frío y snapshots verificados de dependencias, separado de la matriz de diagnósticos. Todavía no se demostró su primera construcción completa en GitHub. No copia un árbol compilado del desarrollador, usa un runner propio ni accede a la PS4 de casa. Una dependencia ausente, error de compilación, error de PKG o runtime inconsistente hace fallar la corrida e impide publicar.

El primer piloto puede revelar más supuestos de las recetas históricas. No describir este workflow como reconstrucción completa demostrada hasta inspeccionar una corrida satisfactoria y sus artefactos. La validación local cubrió sintaxis de workflows, compilación de Python y tests que rechazan entradas de distribución alteradas o inseguras; no compiló ni arrancó un producto nuevo.

## Piloto manual

Abrir **Actions → Build PKG and release → Run workflow**. El workflow ya debe existir en la rama predeterminada; los fixes de construcción pueden probarse desde su rama subida antes de integrarlos:

1. Seleccionar la rama a probar, por ejemplo `ci/release-llvm-lit`, o `main` para la receta integrada.
2. Dejar `publish` sin marcar en el primer piloto de construcción y mantener `cache_mode=reuse`. Seleccionar `cold` para reconstruir deliberadamente todos los bloques de dependencias.
3. Ejecutar. Descargar `product-evidence-*` incluso si falla. La última fase `product-*` y su log identifican el siguiente problema de portabilidad.
4. Si termina bien, inspeccionar `product-candidate-*`, hashes y runtime completo. Probar ese candidato exacto en emulador y/o consola según corresponda; compilar no valida el arranque.
5. Para publicar un candidato, integrar primero el fix probado pasando por `dev` hacia `main`, seleccionar `main` y ejecutar manualmente con `publish` marcado. Se hace una compilación limpia nueva en el SHA de esa corrida; no promociona el binario probado anteriormente ni hereda aceptación física.

Tanto el actor como quien reejecuta una corrida manual deben coincidir con el owner. Otros usuarios con escritura pueden ver el botón Run workflow, pero la autorización falla antes de compilar. Las corridas manuales sin publicación (`publish=false`) aceptan referencias de ramas; publicar y compilar automáticamente exige `refs/heads/main`. El script de autorización, la condición del job de publicación y su auxiliar mantienen explícito ese límite. Es una comprobación del workflow, no reemplaza proteger cambios a los workflows o a main. Ver [contextos de GitHub](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts).

## Cachés de dependencias del producto

`cache_mode=reuse` es el valor manual predeterminado y también se usa en builds automáticas de main. `cold` omite las tres restauraciones de caché de Actions y reconstruye ambos bloques de dependencias; puede generar cachés verificadas para futuras corridas. Ambos modos requieren un workspace nuevo. Las cachés se restauran como paquetes aislados en `.deps/product-cache/`, no directamente sobre un SDK, prefijo, fuente Wine o runtime existente. La receta recupera/verifica las fuentes fijadas y el SDK antes de instalar cualquier snapshot de dependencias.

| Caché | Contenido | Comportamiento |
| --- | --- | --- |
| Descargas verificadas | Archivos/recursos fijados explícitos, nombrados por SHA-256 en `.deps/product-downloads` | Se verifica el hash de cada archivo consumido; se guardan descargas nuevas completas aunque falle una etapa posterior, prefiriendo entradas completas al restaurar |
| Gráficos | Directorios permitidos de compilación/fuentes/herramientas en `~/vk-h0`, incluidos libc++, glslang, RADV, ambos Zink, loaders, MangoHud y vkcube | Se omite el bloque gráfico costoso sólo tras validar el snapshot; el venv Python se recrea en cada corrida |
| Wine anfitrión | Árbol de build/herramientas nativas, PE base preparados e informes del cierre anfitrión | Se omiten los tres pasos de build anfitrión sólo tras validar el snapshot; se genera y prueba un prefijo nuevo en cada corrida |

Cada bloque tiene su clave exacta, vinculada a pins de fuentes/SDK, recetas, parches ordenados del fork cuando corresponda, paquetes instalados, hashes/versiones de compiladores/herramientas, arquitectura/kernel, entorno y rutas absolutas del workspace/home. El commit de la aplicación por sí solo no es una clave. Cambiar `build-host-wine-unix.py`, por ejemplo, invalida Wine sin invalidar gráficos. Cambios de infraestructura/recetas compartidas invalidan ambos; las claves gráficas incluyen conservadoramente entradas native/platform. Se normalizan las fechas de los archivos fuente Wine nuevos sólo tras comprobar el checkout limpio fijado, evitando que las fechas de otro checkout obliguen a recompilar todos los objetos cacheados. Las salidas generadas conservan fechas y permisos del productor.

`product_cache.py` sella cada bloque terminado antes de continuar. Tras el paso del producto, los guardados con `always()` conservan bloques nuevos sellados aunque después fallen el prefijo, la compilación de consola o el empaquetado. No se guardan bloques fallidos/incompletos. Un hit no se vuelve a subir. Los manifiestos registran commit/corrida del productor, identidad de entradas e inventario completo de archivos/enlaces; se comprueban hashes del payload y de cada archivo antes de restaurar destinos. Se rechazan rutas absolutas/con escape, enlaces inesperados del archivo comprimido, symlinks externos, ancestros enlazados en el destino, payload alterado y sobrescrituras de salidas existentes. Sólo se permiten enlaces explícitos del SDK/fuentes hacia entradas fijadas restauradas. La restauración mueve los archivos verificados para evitar conservar otra copia expandida completa.

Sólo se guardan ubicaciones fijas de dependencias. Se excluyen metadatos Git, notas privadas, el venv gráfico y las fuentes Vulkan/LLVM restauradas por separado. Productores de prefijo, registros, documentos, datos de consola, PKGs finales, claves SSH y el resto de `.deps/` quedan fuera de las entradas de caché. Crear el prefijo/validar su fixture, adaptadores PS4, staging final, empaquetado y controles de distribución siguen ejecutándose para el SHA actual. `build-provenance.json` incluye reutilización/productor de los bloques; las cachés no transfieren aceptación de arranque Wine o hardware.

Revisar `reports/ci/product-cache-inputs.json`, `product-cache-status.json`, `product-download-cache.json` y las fases `product-cache-restore-*` / `product-cache-seal-*`. Distinguen bloques reutilizados/reconstruidos y registran tiempos de restauración y tamaños de archivos nuevos sellados. La primera corrida normalmente genera las cachés; otra con la misma rama/entorno permite medir el ahorro. Ramas nuevas/main no necesariamente pueden leer cachés producidas en una rama de feature, y las cachés pueden ser expulsadas. Ver [alcance de caché GitHub](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching). Publicar snapshots sólo desde disparadores de build confiables; estos hashes son controles de integridad, no firmas ni confianza en artefactos arbitrarios de PR.

La validación local cubre guardado/restauración, permisos/fechas, enlaces permitidos al SDK, rechazo de alteraciones/rutas/enlaces, modo frío, control de fechas de fuentes, claves independientes y retención de un bloque terminado tras otro fallo. Una auditoría de sólo lectura comprobó rutas y enlaces de salidas gráficas reales preparadas, sin copiar ese árbol de la computadora a una caché de release. Falta medir la generación en frío y el hit posterior en GitHub; todavía no se afirma un ahorro ni aceptación del producto completo.

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

## Primer piloto en GitHub: fuentes LLVM incompletas

La corrida `42503388231` en `7d8ccdd5a58679432f41c645c5eda6ea3574bba8` aprobó restauración de fuentes, descargas fijadas, preparación del entorno gráfico y LLVM-MinGW, y después falló en `product-setup-libcxx`. CMake no encontró `llvm/utils/llvm-lit/CMakeLists.txt`: la extracción parcial del producto incluía `llvm/utils/lit`, pero omitía el directorio separado `llvm/utils/llvm-lit`, requerido por la configuración CMake del runtime fijado. Es un fallo de preparación de fuentes, anterior al PKG o a probar el arranque de Wine.

La extracción ahora incluye ambos directorios y compara componentes completos de ruta, excluyendo árboles ajenos con nombres parecidos. El wrapper también conserva toda la salida de libc++ en lugar de pasarla por `tail -15`; `product-setup-libcxx.log` incluirá los diagnósticos completos de configuración/build. Se mantiene la revisión/hash del archivo LLVM. El próximo piloto GitHub de construcción puede seleccionar la rama subida del fix con `publish=false`; publicar sigue requiriendo promoverla pasando por `dev` hacia `main`. Reejecutar el SHA anterior no prueba la corrección. Siguen pendientes la construcción completa, el empaquetado y la aceptación del arranque.

Una comprobación local acotada usó el archivo original con SHA-256 verificado `ae67086eb04bed7ca11ab880349b5f1ab6f50e1b88cda376eaf8a845b935762b`, fuentes recién extraídas, directorios de build aislados y el compilador/sysroot PS4 preparado. La selección anterior reprodujo el fallo de configuración por el directorio ausente (salida 1); agregar `llvm/utils/llvm-lit` permitió terminar la configuración/generación CMake (salida 0). Esto verifica únicamente la corrección de fuentes/configuración, no la compilación de libc++ ni del producto completo en GitHub.

## Estado y evidencia de la build Zink

Un fragmento posterior en `f42fa6141ac4bc91a391aecf21be2fd52821475e` llega a `product-build-mesa-zink` y registra salida 1 tras 129,636 segundos; no incluye el error del compilador ni demuestra si Ninja falló. La inspección encontró otro bug reproducible del shell: los pipelines diagnósticos con `grep` del wrapper PE64 devuelven 1 cuando una build correcta no contiene líneas de fallo, y `set -euo pipefail` lo interpreta como fallo de construcción. Se quitaron esos resúmenes redundantes. Ambos wrappers PE64 y PE32 ahora envían la salida de Ninja por `tee` al log del producto, conservando el código de salida de Ninja con `pipefail`, y retienen toda la salida de configuración Meson. Esto también expone errores reales del compilador que antes quedaban en `~/vk-h0/build/mesa-zink*.log`, fuera de las rutas de evidencia subidas.

Las pruebas acotadas ejecutan el tramo final real de cada script con resultados de Ninja controlados: salida cero sin líneas de error aprueba, y una salida no nula sigue fallando y conserva su log. Validan únicamente el manejo de estado/logs del shell, no la compilación de Mesa. El traceback suministrado no demuestra por sí solo que ese bug causó el fallo GitHub; revisar el ZIP `product-evidence-*` correspondiente o el log completo de la próxima corrida antes de afirmar que la etapa Zink está resuelta en GitHub.

## Cierre PE de Wine anfitrión: corrida 42512489326

La corrida `42512489326` en `78225f28a32da0315271b5691a54484b17cb4139` aprobó libc++, glslang, Mesa/RADV, ambos loaders Vulkan, Mesa Zink PE64/PE32, ambas builds MangoHud, vkcube, fixtures y la build PE inicial de Wine. Falló inmediatamente en `product-build-host-wine-closure` con `Missing required PE64 targets: ['wineusb.sys']`. Esto demuestra avance en GitHub después de corregir el wrapper Zink, no una construcción completa del producto.

El configure de Wine fijado desactiva `wineusb.sys` si faltan los archivos de desarrollo de libusb. La build anfitriona preparada que funcionaba usaba una opción adicional `--enable-wineusb-sys`, ausente en el builder reproducible. Ahora el builder habilita explícitamente el módulo PE real de recursos. Coincide con el diseño existente del prefijo anfitrión: `build-host-wine-unix.py` omite el backend Unix USB del host que no se usa, mientras que el cierre PE exige los recursos del driver. No habilita soporte USB en consola ni reemplaza módulos por stubs; se conservan los controles de targets/imports requeridos.

Una comprobación local acotada usó la fuente Wine fijada y un directorio temporal nuevo, pasando explícitamente `--without-usb` para no depender de libusb instalado. Sin la opción nueva, configure omitió el target PE64; con ella, apareció y `make -j2 dlls/wineusb.sys/x86_64-windows/wineusb.sys` compiló el PE real correctamente (salida 0). Esto verifica la corrección de configuración/módulo, no el cierre anfitrión completo, el arranque del prefijo ni la release en GitHub.

La evidencia de release ahora incluye también logs de configuración/compilación Wine nativa, logs/informes del cierre anfitrión y logs/JSON del productor de prefijo generado. No se agregan archivos comprimidos del prefijo ni contenido del usuario a la subida de evidencia. Hace falta una build/configuración nueva para aplicar la opción; reejecutar la revisión anterior del workflow o reutilizar su Makefile configurado no verifica el fix.

## Alias de imports diferidos de Wine: corrida 42521647656

La corrida `42521647656` en `52634fb50e231665afc9a765bd568badf3cf01d3` compiló los targets PE requeridos de Wine, incluidos los recursos USB antes ausentes. El cierre anfitrión compiló 156 módulos en seis tandas de make y después rechazó cuatro dependencias: `winspool.dll` desde `gdi32.dll` y `comdlg32.dll` en ambas arquitecturas. El informe las registra como imports diferidos derivados de fuentes. El `dlls/winspool.drv/Makefile.in` fijado declara `MODULE = winspool.drv` e `IMPORTLIB = winspool`: agregar `.dll` a todo alias sin extensión inventaba el nombre incorrecto.

El cierre anfitrión ahora construye un mapa de alias por arquitectura desde las declaraciones `IMPORTLIB` de los targets PE configurados y resuelve cada import diferido de fuentes al nombre real del módulo. Los imports ausentes siguen llegando al control de rechazo existente; los alias conflictivos y las variables sin expandir fallan explícitamente. No se renombra ni parchea ningún PE. La comprobación local ejercitó el mapa con 1.490 targets configurados (478 alias), resolviendo `winspool` a `winspool.drv` en ambas arquitecturas, y probó casos malformados/ausentes/ambiguos. Es validación del resolutor, no otra construcción completa del cierre ni aceptación del producto en GitHub. La próxima build nueva de rama debe compilar el driver/dependencias agregados y continuar la preparación del prefijo.

## Ejecutables nativos de Wine: corrida 42526738112

La corrida `42526738112` en `9a844ba31aba52cab493d750af9f124d83d23e54` aprobó el cierre PE y la construcción de bibliotecas Unix. La preparación del prefijo falló antes de iniciar Wine: no existía `loader/wine`. Seleccionar las bibliotecas Unix del cierre no construía implícitamente el lanzador nativo ni wineserver en un runner limpio; la computadora preparada ya tenía esas salidas adicionales.

`build-host-wine-unix.py` ahora construye explícitamente `loader/all` y `server/wineserver` junto con las bibliotecas/datos. El target del loader también genera `loader/wine.inf` y el preloader Linux. `unix-report.json` registra hashes del lanzador, preloader, servidor e INF además de los hashes existentes de bibliotecas/datos. La preparación del prefijo comprueba esos archivos, los permisos de ejecución y sus entradas PE/fixture antes de arrancar, indicando directamente los prerrequisitos ausentes. Compilar correctamente los ejecutables nativos no demuestra que funcionen wineboot, el fixture del prefijo o el producto PS4; esos gates posteriores se conservan.

Una build local temporal nueva de la fuente fijada ejecutó correctamente `make -j2 loader/all server/wineserver`, generó los tres ejecutables ELF nativos y `wine.inf`, y obtuvo salida 0 de `wineserver --version` (`Wine 11.17`). Esto verifica la compilación de los ejecutables nativos, no un runtime completo ni el arranque del prefijo.

## Esquema API-set y exports reenviados: corrida 42533695365

La corrida `42533695365` en `473f337e81ebf66016fce6405b25b5eae6b826e1` inició el loader y wineserver nativos, pero wineboot terminó con salida 1 después de unos 41 segundos. Escribió los tres registros, pero nunca ejecutó el fixture y `prefix_ready_for_packaging` quedó en false. Su log muestra el esquema API-set ausente (`c000000f`) y el forwarder `cryptbase.SystemFunction036` de `advapi32.dll` no disponible. El cambio posterior de caché no corrige esas dependencias de ejecución: un bloque anfitrión compilado correctamente todavía puede tener un cierre de arranque incompleto, y la verificación del prefijo debe seguir ejecutándose.

El cierre anfitrión ahora exige targets reales `apisetschema.dll` para ambas arquitecturas y lee los directorios de exports PE además de los imports normales/diferidos. Los exports reenviados agregan sus proveedores reales al grafo recursivo de build (incluidos `cryptbase.dll` y `cryptsp.dll` para advapi32), registrados en `forwarded_imports`. La detección de targets incluye más extensiones PE: por ejemplo, `krnl386.exe16` de Wine es un wrapper PE32 aunque su nombre sea histórico. Los archivos siguen pasando por el parser PE; no se afirma compatibilidad Win16 nueva ni se sustituyen módulos por stubs.

La validación local compiló fixtures reales PE32/PE64 con forwarders y comprobó imágenes fijadas reales de advapi32/kernel32/API-schema. Una auditoría del grafo de sólo lectura visitó 171 nodos sin encontrar dependencias no configuradas entre las imágenes analizadas; faltaba un binario bcrypt x64 local y no se analizó. Es validación local parcial del grafo, no otro arranque de prefijo en GitHub. El builder del cierre y el resolutor existente son entradas de caché exclusivas de Wine, por lo que el fix invalida Wine sin cambiar la clave gráfica. Ejecutar otra build de rama con `cache_mode=reuse`; wineboot y el fixture deben aprobar antes de aceptar el prefijo.

## Prefijo aprobado en GitHub; fuente PS4 generada: corrida 42538487786

La corrida `42538487786` en `9bae47eded67ca36185ad5c74df4e1efcf58e39c` aprobó wineboot nativo, el fixture de consola PE32, limpieza del servidor y controles de registros, y después empaquetó el prefijo nuevo. Es producción verificada del prefijo en Linux nativo, no ejecución de Wine en PS4. Ambos snapshots de dependencias quedaron sellados (`reused=false`): payload gráfico de 587.030.972 bytes y Wine anfitrión de 270.575.859 bytes. La evidencia suministrada demuestra creación de los paquetes de caché, no subida remota correcta ni un hit.

Después de configurar OpenOrbis, `build-wine-ps4.py --boot --all-unix` compiló las unidades Unix anteriores, pero llegó al archivo generado `dlls/ntdll/unix/version.c` antes de que existiera. Invocar directamente las recetas del compilador omitía la regla make de Wine para las fuentes generadas; leer luego el hash ocultaba el error de compilación por entrada ausente. Ahora el builder invoca el target configurado exacto `make <fuente>` para cada fuente generada, registra esa generación y calcula el hash de la entrada preparada antes de compilar. No sintetiza contenido ni copia la versión del host nativo. La evidencia de release también incluye logs por unidad e informes de `build/wine-boot/` y `build/wine-server/`.

Una comprobación local acotada extrajo la regla configurada real de generación de versión de Wine, la ejecutó en un directorio temporal nuevo, compiló la fuente resultante para `x86_64-pc-freebsd12-elf` y verificó el símbolo `wine_build`. Generación y compilación terminaron con salida 0; esto no valida las etapas restantes de compilación cruzada/enlace/arranque. Sólo cambiaron el builder PS4 y las rutas de evidencia, por lo que ambas claves de caché siguen siendo compatibles. Ejecutar una build nueva de rama con `cache_mode=reuse` para intentar la primera restauración caliente y continuar la compilación cruzada.

## Instalación y flujo dev → main

El PKG solo no alcanza: también necesita su runtime en `/data`. Seguir las instrucciones del candidato, respaldar registros/documentos/configuración/partidas y usar una actualización que preserve cambios del usuario si ya existe una instalación. El archivo es un runtime nuevo; reemplazar un prefijo instalado sin combinar puede perder estado. Actions no hace transferencias FTP ni instala en consola.

`dev` ya fue creada desde main. Los PRs diarios de features/fixes apuntan a `dev` y ejecutan checks rápidos y la matriz diagnóstica completa, como describe [operación de CI](CI-es.md). Con un conjunto coherente listo, abrir un PR `dev → main`, revisar/probar ese conjunto e integrar. Con releases automáticas habilitadas, ese push a main lo construye y publica. Mantener main protegida, no integrar dev automáticamente y conservar builds manuales para investigar.

Ver también [operación de CI](CI-es.md), [plan de CI](CI_PLAN-es.md), [estructura de dependencias](REPOSITORY_LAYOUT-es.md) y [guía del desarrollador](../AGENTS-es.md).
