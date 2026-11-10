# S5: lanzar desde el Explorer de OrbisDesk un juego instalado (en curso)

[English](STEAM_S5.md) | [Español](STEAM_S5-es.md)

La meta acordada con el usuario: que un juego bajado por el título de Steam (ORBS00001), como Portal o Portal 2, arranque dentro del Explorer de OrbisDesk. Por ahora el cliente de Steam sigue siendo un título aparte. Integrarlo a OrbisDesk, y la cuestión de licencia que trae (GPL-3 para el paquete combinado), se decide después.

**Estado:** el lado de Steam está en el PKG 01.14: los datos de lanzamiento y los accesos desde la 01.11, y el emulador gbe_fork por juego en la 01.13 (el instalador está en [STEAM_S4-es.md](STEAM_S4-es.md)). Nada de S5 corrió todavía en la consola.

## Lado de Steam, 01.11

- **Registro de instalación, `format: 2`** (`/data/orbisdesk/steam-games/<app>/.orbisdesk-install.json`). Por cada entrada de lanzamiento de Windows que declara Steam, guarda:
  - `executable`;
  - `arguments`, como texto de línea de comandos de Windows;
  - `working_dir`;
  - `description` y `type`;
  - `present`, `pe`, `arch` (x86/x64) y `steamstub`.
  
  También guarda `steam_api_paths`. Las rutas se escriben con las mayúsculas y minúsculas que tienen en disco: las del appinfo pueden diferir de las de los depots, y el sistema de archivos de la consola las distingue.
- **Accesos directos** (`native/steam/steam_shortcut.cpp`). Después de una instalación correcta se escribe un `.lnk` en dos lugares:
  - `/data/wine-prefix/drive_c/users/orbis/Desktop/<juego>.lnk`;
  - `/data/wine-prefix/drive_c/ProgramData/Microsoft/Windows/Start Menu/Programs/Steam/<juego>.lnk`.
  
  El destino es `Z:\orbisdesk\steam-games\<app>\<exe>`, con su carpeta de trabajo y sus argumentos. `Z:` es `/data` en el prefijo de OrbisDesk (`platform/ps4/pw_wine_fs.c`). Explorer ya muestra los `.lnk` de esas carpetas (W045, W168, W169). Los bytes son exactamente los que escribe `tools/make-start-menu.py`; una prueba comparó los dos, también con nombres no ASCII.
  
  Si no existe `/data/wine-prefix/drive_c` no se escribe nada, y el log lo dice. Se salta una entrada con SteamStub o que no sea PE. El log lleva sólo marcas (`shortcut prefix=… desktop=… start=…`), nunca el nombre del juego.

## Lado de OrbisDesk, preparado para quien lo mantiene

- **El parche de `Z:`** para `windows_unix_path` en `native/wine_hardware.c`. La conversión de rutas del lanzador conoce C:, de D: a K: y L:, pero no Z:. Sin él, un relanzamiento con `next.txt` o `launch.txt` de un juego de 32 bits en Z: no puede leer la máquina de su PE, así que no recibe `--wow64-cpu` ni `PW_PROGRAM_DIR`. Un doble clic dentro de Explorer no pasa por esa función.
- **Todavía no se sabe:** si el proceso de OrbisDesk puede leer los archivos que escribió el título de Steam (carpetas 0777, archivos 0644), y si un ícono nuevo del escritorio aparece sin reiniciar. Las dos cosas necesitan la consola.

## gbe_fork, 01.13

Sin el cliente de Steam, el `steam_api.dll` propio de un juego lo cierra o pide Steam. gbe_fork (LGPL-3.0) le responde al juego en su lugar. El usuario aprobó la descarga el 2026-11-07:

| Archivo | Bytes | SHA-256 |
|---|---|---|
| `emu-win-release-vs22.7z`, versión `release-2026_09_27` de github.com/Detanup01/gbe_fork | 13.455.496 | `300186c34f49a9ea75b33ce2af299267cc1dad0225cf45e81a229578d4e11c85` |
| `gbe_fork-release-2026_09_27-source.tar.gz`, el código fuente de esa etiqueta | 8.559.653 | `ce3ce7aee0439f1b7aff2404106fe68184185a8d0b7ca5ab2677a046ea464cbd` |

Los dos están en `.deps/steam/downloads/gbe_fork-2026_09_27/`, que no se sube al repositorio.

- **Qué va en el título:** el builder comprueba los dos hashes y toma las dos compilaciones regulares sin modificar, `release/regular/x86/steam_api.dll` y `release/regular/x64/steam_api64.dll`, junto con el texto LGPL-3.0 y un `gbe-SOURCE.txt` con las dos direcciones y los hashes. Van sueltos en `/app0/assets/misc/` (`gbe-x86-steam_api.dll`, `gbe-x64-steam_api64.dll`), porque `create-gp4` no declara carpetas ahí. El PKG pasa a medir 27,5 MB.
- **Por juego, desde el título de Steam** (`native/steam/steam_emu.cpp`): en la lista, X sobre un juego instalado abre su página. Triángulo activa o desactiva el emulador. Activarlo hace esto, para cada ruta de `steam_api_paths` del registro:
  1. la DLL del juego se renombra a `.orig`;
  2. se copia la DLL de gbe_fork del mismo nombre;
  3. `steam_settings/` recibe `steam_appid.txt`, `configs.user.ini` y `steam_interfaces.txt`.
     - `configs.user.ini` lleva el nombre genérico de jugador "OrbisDesk" y el idioma de la instalación, sin datos de la cuenta.
     - `steam_interfaces.txt` sale del `generate_interfaces` de gbe_fork, pasado a C++ con los mismos patrones y la misma regla de SteamClient017. Cada patrón es un literal, casi todos seguidos de `\d+`, así que desde el 2026-11-08 el port busca el literal en vez de usar `std::regex` (ver [STEAM_HOSTED-es.md](STEAM_HOSTED-es.md)).
  
  `.orbisdesk-gbe.txt` lista exactamente lo que se escribió. Restaurar borra eso y vuelve a renombrar los `.orig`. Nunca se toca un archivo del mismo nombre que haya traído el juego.
- **Verificar un juego con el emulador activado** primero devuelve las DLL originales, después verifica y al final vuelve a activar el emulador. Si no, la verificación cambiaría la DLL de gbe_fork por la de Steam.
- **Un `.orig` que dejó una corrida interrumpida se acepta sólo en dos casos:** es igual a la DLL que tiene al lado, o la DLL de al lado es la de gbe_fork. Si no, no se toca nada y la página lo dice.

**Pruebas en la PC:** con DLL originales falsas que llevan nombres de interfaz de 2011, pasaron 27 comprobaciones:
- activar y desactivar, en x86 y x64;
- la lista de interfaces generada contra la esperada;
- un segundo "activar", que no cambia nada;
- un archivo propio del juego en `steam_settings/`, que se conserva;
- los tres casos de `.orig`.

**No se probó:** un juego real. Eso necesita la consola, con Portal o Portal 2 y el registro v2 de la 01.11 en adelante.
