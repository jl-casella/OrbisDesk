# S4: instalar un juego de la biblioteca

[English](STEAM_S4.md) | [Español](STEAM_S4-es.md)

Es la cuarta fase del cliente de Steam. S3, el login por QR, está en [STEAM_S3-es.md](STEAM_S3-es.md). Ahora la app muestra los juegos de la cuenta que tienen contenido de Windows y permite instalar uno en la consola.

**Estado:** el PKG 01.14 está armado (la 01.11 sumó los datos de lanzamiento y los accesos de S5, la 01.13 el emulador gbe_fork: [STEAM_S5-es.md](STEAM_S5-es.md)). La 01.08 y la 01.09 corrieron en la consola: la reapertura sin QR y la biblioteca anduvieron, pero ninguna pudo medir el espacio libre: la 01.08 se detuvo y en la 01.09 el usuario instaló igual (ver "Corridas en la consola"). En la PC el instalador se probó sin cuenta, con descargas anónimas: instalar, reanudar, reparar un archivo y pausar. Una instalación con la cuenta del usuario **todavía no terminó en la consola**.

## Qué cambia respecto de S3

- **Programa principal:** `native/steam/steam_client.cpp`, que parte de S3. `steam_s3.cpp` queda como estaba cuando se aceptó.
- **Log:** `/data/orbisdesk/steam-client.txt`, con líneas `PWSTEAM client S4 …`.
- **Después del login:** en lugar del resumen, la **lista de la biblioteca**:
  - sólo los juegos con un depot de Windows con manifiesto público, ordenados por nombre;
  - cada uno con su tamaño y "INSTALADO" si ya lo está;
  - arriba y abajo eligen, X instala, O sale y triángulo cierra la sesión, como en S3.
- **Botones nuevos en la pantalla** (`steam_ui.c`): arriba y abajo, y una línea resaltada para el juego elegido.

## Cómo se instala

`native/steam/steam_install.cpp`:

1. **Plan:**
   - el PICS de los DLC del juego;
   - `SelectDepots` de Playden con las licencias de la cuenta: Windows, inglés, rama pública, 64 bits antes que 32, y los DLC que la cuenta tiene;
   - `MissingBaseDepots`: si las licencias dejan afuera parte del juego, no se instala, porque quedaría incompleto.
   
   La pantalla muestra el tamaño instalado, la descarga, el espacio libre y la carpeta, y espera X.
2. **Claves y manifiestos:** `FetchDepotAccess` para todos los depots, los servidores de contenido y cada manifiesto, como en S2.
3. **Unión de los depots:** por ruta en minúsculas; si dos depots traen el mismo archivo, gana el que viene después en la lista de Steam. Los enlaces simbólicos no se crean y se cuentan.
4. **Espacio:** se suma lo que ya está en la carpeta, y tiene que quedar al menos 512 MB libres. En la consola el espacio libre se lee con el `fstatfs` del kernel en la carpeta existente más cercana, con la `struct statfs` de FreeBSD (versión `20030518`, como `native/disc_probe.c`), porque la del SDK no coincide. Una medición que falla o da valores imposibles no se toma como número: la pantalla del plan dice "NO SE PUDO MEDIR", el log tiene la medición completa, y X pasa a ser "instalar igual" (desde la 01.09). Si la consola se llena durante la descarga, la instalación se detiene con su propio aviso (`ENOSPC`) y lo descargado queda.
5. **Archivos:** cada uno se crea con su tamaño final.
6. **Descarga con cuatro hilos,** cada uno con su propio `CdnClient`. Antes de bajar un chunk se leen sus bytes del archivo: si su SHA-1 ya es el del chunk, no se baja. Así una instalación pausada o cortada **se retoma sin diario**, y una carpeta con un archivo dañado se repara bajando sólo lo que cambió.
7. **Verificación:** el SHA-1 de cada archivo contra el manifiesto.
8. **Ejecutable:** la primera entrada de lanzamiento de Windows (`EligibleLaunches`). Del archivo PE se lee:
   - la arquitectura (x86 o x64);
   - si tiene la sección `.bind` de **SteamStub**, el DRM que OrbisDesk no puede ejecutar.
   
   También se anota si el juego trae `steam_api.dll` o `steam_api64.dll`.
9. **Registro:** `.orbisdesk-install.json` en la carpeta del juego, escrito al final y sólo si todo pasó. Tiene la app, el nombre, la carpeta de Steam, los depots y manifiestos, el ejecutable, la arquitectura y si tiene `steam_api` o SteamStub. Al empezar una instalación se borra el registro anterior, así que una carpeta a medio actualizar no figura como instalada.

**Carpeta:** `/data/orbisdesk/steam-games/<app>/`.

**Durante la descarga:** la pantalla muestra lo descargado, el porcentaje, los archivos completos y la velocidad. O pausa la instalación, y lo descargado queda en la carpeta.

## Qué va al log

Sólo contadores, tamaños y categorías de error. Por ejemplo:
- `plan depots=N rejected=N os=N …`
- `install merged files=N chunks=N bytes=N`
- `install space ok=1 free=… need=… path=… fstatfs=… version=… bsize=… bavail=…`
- `install files=N verified=N failed=N fetched=N reused=N kib_s=N`
- `install exe pe=1 arch=x64 steamstub=0`

Ninguna app, depot, archivo ni nombre de juego, porque dirían qué juegos tiene la cuenta. Esos datos están sólo en el registro de la carpeta del juego y en `steam-library.txt`, que no se bajan de la consola.

## Pruebas en la PC (2026-11-07), sin cuenta

Un programa de prueba (no forma parte del título) usa el login anónimo de S2 y llama a `PlanInstall` y `RunInstall` con la app 1007, *Steamworks SDK Redist*:

| Prueba | Resultado |
|---|---|
| Instalación nueva | 8 de 8 archivos verificados, 24,3 MB bajados, 67,9 MB instalados |
| Otra vez sobre la misma carpeta | 8 de 8, **0 bytes bajados**, 67,9 MB reutilizados |
| Con 4 bytes alterados en un archivo | 8 de 8, sólo 443 KB bajados (el chunk dañado) |
| Pausa a los 4 s | `canceled=1`, 5,5 MB bajados, sin registro |
| Reanudación | 8 de 8, 13,6 MB reutilizados y el resto bajado |
| Ejecutable | `steamclient64.dll` da `x64` y `steamclient.dll` da `x86` |
| Varios depots: app 228980, *Steamworks Common Redistributables* | 26 depots unidos, 235 de 235 archivos verificados, 1,4 GB en 168 s (8,2 MB/s con cuatro hilos; S2, con uno, iba a unos 3 MB/s en la PC) |

**No se probó:**
- la detección de SteamStub con un ejecutable que lo tenga;
- la lista y la instalación con una cuenta, que son del usuario en la consola;
- la escritura en USB, que queda para la próxima versión.

## Cómo se compila

```sh
python3 tools/build-steam-s4.py --target host
python3 tools/build-steam-s4.py --target ps4 [--check]
```

- **Título:** ORBS00001, "OrbisDesk Steam", versión 01.14. Se instala encima de S3 01.07 y usa la misma sesión guardada.
- **Paquete:** `out/steam-s4/OrbisDesk-Steam-S4-01.14.pkg`, con su SHA-256 en `manifest.json`.
- **Partes nuevas de Playden:** `cdn_client`, `depot_manifest`, `depot_chunk` y `game_path`, además de lo de S3. El instalador de Playden (`depot_installer.cpp`) no se usa: necesita `src/installs`, que no está entre los archivos descargados, y lee carpetas con `readdir`, cuya estructura en la consola no es la del SDK.
- **Imports:** pasa el chequeo. Los únicos fuera de `wine.elf` y `hardware.elf` son los seis de S2. `_fstatfs` ya lo importa `wine.elf`.

## Para aceptarla en la consola

1. Abrir la 01.14. Si la sesión de S3 sigue guardada, entra sin QR.
2. Elegir un juego chico con arriba y abajo, y apretar X.
3. Confirmar con X en la pantalla del plan y esperar.
4. **Opcional:** apretar O a mitad de camino, volver a instalar y ver que retoma.
5. Ver la pantalla final: archivos verificados, ejecutable y arquitectura, `steam_api` y SteamStub.

El `steam-client.txt` tiene que terminar en `PWSTEAM client S4 result=pass` y tener `install done`.

Si falla:
- `plan none`: Steam no da acceso a todo el juego o no hay contenido de Windows.
- `install access error=…`: las claves de los depots.
- `install space ok=1` con poco libre: falta espacio; `ok=0`: falló la medición, y la misma línea muestra cómo.
- `install chunk failed` o `failed=N`: la descarga.

## Corridas en la consola

**S4 01.08 (2026-11-07): la instalación se detuvo en el control de espacio.** La copia del log está en `reports/steam-s4-console/steam-client-0108.txt`.
- **Lo que anduvo:**
  - `session load=none` y `session restore error=none`: la app abrió sin QR, y con eso también queda cerrada la prueba pendiente de S3;
  - la biblioteca (36 juegos);
  - para el juego elegido (4 depots, 1.659 archivos, 4,3 GB): el plan, las claves de los 4 depots, los 11 servidores y los manifiestos.
- **Lo que falló:** `install space free=0 … need=4347052354`, y la instalación se detuvo diciendo que no había espacio. La pantalla de almacenamiento de la consola mostraba unos 149 GB libres. La 01.08 tomaba cualquier medición fallida como 0 y no registraba cómo había salido.

**Cambios en la 01.09:**
- `MeasureFreeSpace` reemplaza a `FreeBytes`:
  - mide en la carpeta existente más cercana;
  - registra la ruta, el resultado de `fstatfs` y su `errno`, y la versión, el tipo, el tamaño de bloque, los bloques, `bfree` y `bavail` de la estructura, más el comienzo crudo cuando los valores no son plausibles;
  - devuelve "sin medir" en lugar de 0.
- Sin medición, la pantalla del plan lo dice y X instala igual. Si la consola se llena durante la descarga (`ENOSPC`), la instalación se detiene con su propio aviso.

**S4 01.09 (2026-11-07): el espacio libre sigue sin medirse; el usuario instaló igual.** La copia del log está en `reports/steam-s4-console/steam-client-0109.txt`.
- La pantalla del plan dijo "NO SE PUDO MEDIR" y el usuario eligió instalar igual (`install start unmeasured_ok=1`). El juego (3 depots, 3.698 archivos, 12,8 GB instalado, 7,5 GB de descarga) empezó a bajar.
- **Causa:** `MeasureFreeSpace` buscaba la carpeta existente más cercana con `access()`, y en la libc de este título `access()` falla para cualquier ruta. Subió hasta `/` mientras la instalación escribía en la carpeta del juego, y ahí `fstatfs("/")` falló con `EPERM` (`fstatfs=0xffffffff errno=1`). Así que todavía no hay una lectura de `/data`.
- **La misma falla explica otras dos cosas:**
  - S3 y S4 mostraban el aviso en cada corrida (`notice saved=1` todas las veces);
  - `Installed()` nunca veía el registro, así que la lista nunca decía "INSTALADO".

  La reanudación no dependía de eso, porque compara cada chunk con el archivo.

**Cambios en la 01.10:**
- `orbisdesk::PathExists` abre la ruta sólo para leer, y reemplaza a `access()` en la medición del espacio, en `Installed()` y en el control del aviso.
- Una línea `fs probe path=… access=… errno=… open=…` registra una vez qué devuelve `access()` sobre la carpeta de datos, que existe.
- `steam_s3.cpp` conserva `access()`, porque quedó como se aceptó. En la consola lo reemplaza la 01.10.

**S4 01.10 (2026-11-07): `access()` arreglado; el sandbox niega `fstatfs`.** La copia del log está en `reports/steam-s4-console/steam-client-0110.txt`.
- `fs probe … access=-1 errno=1 open=1`: en este título `access()` responde `EPERM` y abrir funciona. El aviso ahora aparece una sola vez (`notice already_accepted=1`), y la búsqueda de espacio libre se detiene en `/data/orbisdesk/steam-games`.
- `fstatfs` sobre esa carpeta también falla con `EPERM`. No es sólo `/`: el sandbox le niega `fstatfs` a este título.
- El juego elegido mostró `download_bytes=0`. Así viene el appinfo: algunos depots no dicen su tamaño de descarga, y `DepotBytes` de Playden suma 0 por ellos. Desde la 01.12 la pantalla dice "STEAM NO LA INDICA" en lugar de 0 MB.
- La 01.10 sobrescribió el log de la 01.09, así que no se sabe si la primera instalación de Portal 2 llegó a `install done`.

**Cambios en la 01.12:**
- Si `fstatfs` falla, se prueban dos mediciones más, cada una registrada en su propia línea `plan space`:
  - `statfs` por ruta (syscall 396 de FreeBSD 9) sobre la carpeta, sobre `/data/orbisdesk` y sobre `/data`;
  - `getfsstat` (syscall 395), eligiendo el montaje cuyo `f_mntonname` es el prefijo más largo de la carpeta.

  Las dos son syscalls directas, como las hace `native/disc_probe.c`; el SDK no tiene funciones para ellas. No se usa el jailbreak (`sys_sdk_cmd` de GoldHEN). "NO SE PUDO MEDIR" con "instalar igual" sigue como último recurso.
- El log de la corrida anterior queda como `steam-client.prev.txt`.

**S4 01.12 (2026-11-07): ningún método de espacio libre está permitido; Portal 2 estaba entero en disco.** Las copias de los logs están en `reports/steam-s4-console/0112-steam-client.txt` y `0112-steam-client.prev.txt`.
- `fstatfs`, `statfs` (sobre la carpeta, `/data/orbisdesk` y `/data`) y `getfsstat` fallan todos con `errno=1` (`EPERM`). El sandbox no deja que este título mida el espacio libre con ninguno de los tres. Se mantiene "NO SE PUDO MEDIR" con "instalar igual". La vía del jailbreak queda como decisión del usuario.
- Portal 2 (`present=12759257499 need=0`): todos los archivos ya tenían su tamaño completo. Instalarlo otra vez leyó y comprobó sus 15.427 chunks contra el disco, pero la pantalla parecía una descarga nueva.

**Cambios en la 01.14:**
- La pantalla de avance dice **"VERIFICANDO LO QUE YA ESTA EN LA CONSOLA"** mientras los chunks sólo se encuentran en su lugar, y **"DESCARGANDO DE STEAM"** cuando se bajó algo en los últimos 3 segundos. Muestra por separado lo que ya estaba bien y lo descargado ahora; la velocidad aparece sólo mientras se descarga.
- Una línea `install progress files=N/M reused=… fetched=… failed=…` cada 250 archivos.
- Un archivo cuyos chunks se encontraron todos en su lugar, con su SHA-1 correcto, ya no se vuelve a leer para el SHA-1 del archivo entero: los chunks lo cubren de punta a punta, así que sus bytes ya están comprobados. Sólo se calcula el hash entero de los archivos que tuvieron un chunk escrito en esta corrida (`rehashed=N` en la línea final). En la PC, volver a comprobar la instalación de 1007 pasó de 3,2 s a 1,7 s.
