# Tamaño del runtime

[English](RUNTIME_SIZE.md) | [Español](RUNTIME_SIZE-es.md)

Estado: cambiado en los builders el 2026-11-20. Compilado localmente como versión de la app 04.41. Todavía no se probó en la consola.

## Qué midió una instalación limpia

Se instaló el paquete del CI de `dev` en `ffa54fc` (corrida de producto 44659728449, versión de la app 04.32) en una consola sin datos previos de OrbisDesk. El paquete pesa 1,96 GB. Su primer arranque escribió 1651 MB en 6295 archivos bajo `/data`:

| Parte | MB |
| --- | --- |
| `C:\windows\system32` y `syswow64` | 881 |
| Wine Mono (`C:\windows\mono`) | 275 |
| Wine Gecko (dentro de system32 y syswow64) | 207 |
| SeaMonkey | 131 |
| `/data/wine` (las bibliotecas de Wine) | 118 |
| VLC | 56 |
| MangoJuice | 52 |
| Soundfont MIDI, winsxs, temas, fondos, `C:\orbis` | unos 90 |

El paquete también lleva el runtime completo (`/app0/runtime`), así que la consola lo guarda dos veces: en la aplicación instalada y en `/data`.

## Qué deja afuera este cambio

1. **Los assemblies de referencia de Wine Mono**, `lib/mono/<versión>-api` (unos 98 MB). Son metadatos para compiladores. Un programa en ejecución nunca los carga.
2. **Las herramientas de desarrollo de Wine Mono**: MSBuild, xbuild y los compiladores de C# y VB (`csc`, `vbc`, `mcs`, `ilasm`, `Microsoft.CodeAnalysis*` de Roslyn), unos 30 MB. Con los puntos 1 y 2, el árbol de Mono pasa de 275 MB a unos 146 MB ([stage-wine-mono.py](../tools/stage-wine-mono.py)).
3. **`games-source.tar.gz`** en system32 (93 MB). Es el archivo de fuentes de los juegos de ReactOS. El `<tag>-third-party-sources.tar` de cada release ya lleva la revisión fijada de ReactOS, y [build-games.py](../tools/build-games.py), que genera los includes vacíos, está en el repositorio en el tag. El archivo queda en `out/games` ([juegos](GAMES-es.md)).
4. **Las copias de bibliotecas de Wine que el prefijo ya tiene.** Cada build PS4 de un módulo de Wine se copiaba a `/data/wine/lib/wine/<arch>-windows` y, con los mismos bytes, a system32 o syswow64. En la instalación limpia eran 155 módulos, 93 MB dos veces. El loader de Wine toma un builtin primero de `lib/wine`. Si `lib/wine` no lo tiene, toma la copia del prefijo, que lleva la marca de builtin. La mayoría de los módulos ya cargaban así: son las líneas `find_builtin_dll ... cannot find builtin library` de cada log. [build-wine-hardware.py](../tools/build-wine-hardware.py) ahora borra la copia de `lib/wine` de un módulo cuya copia en el prefijo es idéntica. `ntdll.dll` se queda, porque el loader Unix la mapea desde `lib/wine` y `native/pop_wine_child.c` la abre ahí por ruta.

## Consolas que ya tienen una build anterior

El instalador sólo agrega y reemplaza archivos. Sin más, los archivos que se dejan afuera quedarían en una consola que instaló una build anterior. Para el punto 4 además sería un error, no sólo espacio: una copia vieja en `lib/wine` le ganaría a la copia nueva del prefijo. Por eso cada ruta que se deja afuera entra en la lista de obsoletos de la build, que borran el instalador del launcher ([hw_install.h](../native/hw_install.h)) y [upload-hardware.py](../tools/upload-hardware.py). Esa lista ahora acepta rutas bajo `wine/lib/wine/` además de `wine-prefix/`.

## Límites

- Un programa .NET que compila C# en tiempo de ejecución (`CSharpCodeProvider` de CodeDom) no encuentra compilador.
- El punto 4 cambia desde dónde cargan la mayoría de los módulos PS4 de Wine. Necesita una prueba en la consola con programas de 64 y 32 bits antes de un release: el escritorio, un juego de 32 bits, un juego DirectX 9 por wined3d, un programa Vulkan, audio y un mando.
- Wine Gecko (207 MB) y la doble copia del runtime no cambian acá.

## Cómo probarlo en la consola

1. Instalar el paquete sobre una build anterior.
2. Verificar que `/data/wine/lib/wine/x86_64-windows` tenga `ntdll.dll` y los módulos sin copia en system32, y que ya no estén las carpetas de Mono que se dejaron afuera.
3. Abrir el escritorio, un programa de 32 bits y uno de 64 bits, un juego DirectX 9 y vkcube, reproducir audio y usar el mando.
