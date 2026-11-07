# Contenido del repositorio y reconstrucción de dependencias

[English](REPOSITORY_LAYOUT.md) | [Español](REPOSITORY_LAYOUT-es.md)

Estructura del repositorio de fuentes registrada el 2026-11-07. El repositorio raíz usa la rama `main`. Los checkouts externos y la evidencia permanecen locales, excluidos de las fuentes publicadas.

## Qué pertenece a Git

Conservar las fuentes propias de `native/`, `platform/`, `fixtures/`, los scripts y generadores de parches de `tools/`, las comprobaciones de `tests/`, `patches/`, los locks de la raíz, la documentación bilingüe y los archivos de atribuciones/licencias. Los fixtures adaptados y atribuidos siguen siendo fuentes de entrada; los árboles de bibliotecas descargadas y las aplicaciones compiladas quedan afuera.

Ignorar `/upstream/`, `/.deps/`, `/build/`, `/out/`, `/private-notes/` y todo `/reports/`, además de ejecutables/bibliotecas/paquetes generados, archivos comprimidos, cachés y entornos locales. Antes sólo se ignoraba `reports/runs/`; los informes pueden contener runtimes completos, prefijos, archivos capturados, binarios y archivos comprimidos. No corresponden al primer commit de fuentes. Ignorar estas rutas no las borra. La documentación histórica puede seguir enlazando evidencia local que no estará en un clon nuevo.

## Ubicaciones externas

| Carpeta | Contenido | Tratamiento en Git |
| --- | --- | --- |
| `private-notes/` | Investigaciones y comparaciones locales, con sus variantes de idioma | Ignorar todo el directorio; mantener independiente la documentación pública |
| `upstream/` | prospero-win, DolphinPS4, Crema, Resonance, shadPS4 de referencia, exportación de Playden; también puede descargarse Wine aquí | Ignorar todo el directorio |
| `.deps/wine/` | Fuentes limpias de Wine, builds anfitrionas y overlays PS4 generados | Ignorar; conservar revisión, parches y generadores |
| `.deps/shadPS4-fork/` | Fork local del emulador y submódulos | Ignorar; conservar base, 17 parches y overlay 0018 |
| `.deps/shadPS4/`, `.deps/shadPS4-linux/` | Descargas del emulador oficial | Ignorar; versiones/hashes en locks de artefactos |
| `.deps/sdk/`, `.deps/windows-tools/`, `.deps/linux-tools/`, `.deps/linux-runtime/` | SDK, compiladores y runtimes privados | Ignorar; conservar locks de artefactos |
| `.deps/vk/` | Archivos de Mesa/libdrm, llvm-mingw, MangoHud y MangoJuice de referencia | Ignorar; conservar pins y recetas `tools/vk-h0/` |
| `.deps/dosbox-pure/`, `.deps/wfm/`, `.deps/reactos-games/`, `.deps/sdl2/`, `.deps/sdl2-mixer/`, `.deps/spacecadetpinball/` | Fuentes de aplicaciones/runtimes opcionales | Ignorar; conservar pins y adaptadores |
| `.deps/downloads/`, `.deps/steam/`, `.deps/games/`, `.deps/wallpaper-cc0/` | Recursos descargados, navegadores, componentes Vulkan/Direct3D, juegos de entrada y dependencias de Steam | Ignorar; versiones/hashes en locks y recetas de staging |
| `.deps/doc-translation/`, `.deps/doc-translate-venv/` | Modelos de traducción local y entorno Python | Ignorar; no son entradas de compilación de la app |
| `~/vk-h0/` en WSL (`/home/jose/vk-h0/` aquí) | Copias de fuentes gráficas, toolchain, entorno virtual, sysroot y builds | Fuera de esta raíz Git; reconstruir por separado |

## Revisiones fijadas

El catálogo legible por herramientas es `dependencies.lock.json`. Las rutas que empiezan con `~/` corresponden al home de WSL. Las revisiones identifican las fuentes; no afirman que todos los checkouts estén limpios ni que todos se usen en el paquete principal. MangoJuice es material de referencia; MangoHud es la base de la capa activa.

| Dependencia | Ruta | Commit |
| --- | --- | --- |
| prospero-win | `upstream/prospero-win` | `0e7b6b4a53a9aebfeceaf28fabb919e2452bbadc` |
| DolphinPS4 | `upstream/DolphinPS4` | `879b3e57f3d3180bcb5f2234db3903688b28cd7d` |
| Crema | `upstream/Crema` | `475b8d5bd3498dbd5cfefe8175f98d017a017739` |
| Resonance | `upstream/Resonance` | `6b87389033d4f239e97d36c605bf7eea384d1e23` |
| shadPS4 | `upstream/shadPS4` | `1d8004a22feb0d5cc58828bac066018e80b6d73f` |
| wine | `upstream/wine` | `490f6d5dcbb2a5047345b8af88d114bbcaad69a8` |
| wine-build-source | `.deps/wine/source` | `490f6d5dcbb2a5047345b8af88d114bbcaad69a8` |
| dosbox-pure | `.deps/dosbox-pure` | `ba6dcaee84aa2c22d709c3dfdacb7aca5ebc3042` |
| wfm | `.deps/wfm` | `6b1860895885a6d65c37815308260293341acb5f` |
| reactos-games | `.deps/reactos-games` | `5f6ef754f90eef792e4ef90561bcff2cac4d3afb` |
| sdl2 | `.deps/sdl2` | `98d1f3a45aae568ccd6ed5fec179330f47d4d356` |
| sdl2-mixer | `.deps/sdl2-mixer` | `171eb2d420d5643e4ee11514a06e04a41a463bbd` |
| spacecadetpinball | `.deps/spacecadetpinball` | `cb9b7b886244a27773f66b0b19fdc2998392565e` |
| mangohud | `.deps/vk/mangohud-win/repo` | `52592550824ae11d5c68a6826f07db5f60220d23` |
| mangojuice | `.deps/vk/mangojuice-win` | `e2ec0755f83975be5f0b593ee59cee62e793ed4a` |
| playden-ps5 | `upstream/playden-ps5` | `fb74dbfd6bb96fc19a96afc1f48a4e40a885216b` |
| Vulkan-Headers | `~/vk-h0/src/Vulkan-Headers` | `2fa203425eb4af9dfc6b03f97ef72b0b5bcb8350` |
| Vulkan-Loader | `~/vk-h0/src/Vulkan-Loader` | `052ac24611eced7b0ca62cc5cca2eeeb2051fa28` |
| Vulkan-Tools | `~/vk-h0/src/Vulkan-Tools` | `48b5d246b2d0b1a41ee7ea1b69525ae7bb38a2ae` |

El archivo `VERSION` de Wine indica **11.17**. La base del fork es `529ceb32f5546b820588f194b903cc39d08015fe` (emulador oficial v0.20.0); el HEAD histórico con los 17 parches es `9ac99bb2445e86f525519a4041a6c85362790ad2`. La revisión de shadPS4 de referencia en `sources.lock.json` es distinta; no debe sustituir la base del fork.

## Cambios de Wine y del emulador

La base limpia de compilación de Wine está en `.deps/wine/source`. Conservar `patches/wine/` **y también** `tools/prepare-wine-ps4.py`, `tools/prepare-wine-boot.py`, los builders de Wine/módulos y los adaptadores propios. Muchas modificaciones actuales están expresadas como transformaciones con contexto comprobado dentro de esos scripts. Los tres parches estáticos de Wine no describen por sí solos todo el port actual. No se versionan los árboles de fuentes generados.

Para shadPS4, `fork.lock.json` define la base upstream y los 17 parches ordenados con SHA256. `dependencies.lock.json` agrega el árbol HEAD esperado y `patches/shadPS4/pending/0018-fixed-executable-and-kernel-signals.patch`, SHA256 `d37d54454bc340c54e15c2a867c76c5fcca58a3eee860c81d0b1ed72fff4e30f`. Durante esta preparación coincidió exactamente con todo el diff de fuentes versionadas actual. Reconstruir los commits puede cambiar sus IDs por los datos del committer; se verifica el contenido contra el árbol `a37a8cb543e0dc107a654f1e998112eb57890bef` antes de aplicar el overlay.

## Restaurar e inspeccionar

Ejecutar desde la raíz del repositorio en Ubuntu 22.04 WSL, con Python 3.10 o posterior:

```sh
# Inspección de sólo lectura de las bases, el overlay y los archivos gráficos.
python3 tools/restore-dependencies.py --only wine-build-source --only shadps4-fork --only wfm --only dosbox-pure --only mangohud --archives

# En un clon nuevo, descargar repositorios fijados, reaplicar los parches del fork
# y su overlay e inicializar sus submódulos fijados. Rechaza árboles diferentes existentes.
python3 tools/restore-dependencies.py --fetch

# Opcional: restaurar sólo los dos árboles de fuentes centrales.
python3 tools/restore-dependencies.py --fetch --only wine-build-source --only shadps4-fork

python3 tools/check-repository-layout.py
python3 tools/check-docs-bilingual.py
```

El restaurador no borra/reemplaza árboles existentes, descarga recursos comprimidos, extrae SDKs, aplica cada transformación específica de módulo ni compila el paquete. Una exportación de Playden sin Git se informa como revisión declarada durante la inspección; la descarga se niega a reemplazarla. En un clon nuevo se restaura desde el commit upstream fijado. Las URLs y SHA256 gráficos están en `dependencies.lock.json`; SDK/emuladores y otras herramientas están cubiertos por `artifacts.lock.json`, `fork-tools.lock.json` y los locks Linux. `build-environment.lock.json` registra las versiones instaladas de paquetes WSL y del entorno Python gráfico observadas aquí.

## Validación y trabajo restante de reconstrucción

La preparación reaplicó los 17 parches del emulador sobre la base exacta mediante un índice Git temporal, reprodujo el árbol esperado y aplicó allí el overlay 0018. El checkout real del fork quedó intacto. Pasaron las revisiones centrales y los hashes de los tres archivos gráficos. Este cambio de repositorio no compiló paquetes ni ejecutó pruebas físicas.

La recuperación de fuentes está demostrada para la serie de parches del emulador; una build completa desde un clon limpio **todavía no está demostrada**. Para afirmarlo hay que eliminar rutas particulares `/mnt/c/Users/JoseCasella/...` de las recetas gráficas, orquestar configuración anfitriona/prefijo de Wine, recrear informes usados como entradas de build (por ejemplo `reports/increment15/host-build/report.json`) y recorrer SDK, gráficos, cierre PE y empaquetado en orden de dependencias. No reincorporar runtimes ni informes cacheados para ocultar pasos de generación faltantes. Las descargas opcionales conservan pins en sus builders y scripts de staging; el catálogo nuevo no es un gestor universal de paquetes.
