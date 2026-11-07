# S4: instalar un juego de la biblioteca

[English](STEAM_S4.md) | [Español](STEAM_S4-es.md)

Es la cuarta fase del cliente de Steam. S3, el login por QR, está en [STEAM_S3-es.md](STEAM_S3-es.md). Ahora la app muestra los juegos de la cuenta que tienen contenido de Windows y permite instalar uno en la consola.

**Estado:** el PKG 01.08 está armado. En la PC el instalador se probó sin cuenta, con descargas anónimas: instalar, reanudar, reparar un archivo y pausar. La lista y la instalación con la cuenta del usuario **falta probarlas en la consola**.

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
4. **Espacio:** se suma lo que ya está en la carpeta, y tiene que quedar al menos 512 MB libres. En la consola el espacio libre se lee con el `fstatfs` del kernel, con la estructura de FreeBSD 9 (como `native/disc_probe.c`), porque la del SDK no coincide.
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
- `install space free=… need=…`
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

- **Título:** ORBS00001, "OrbisDesk Steam", versión 01.08. Se instala encima de S3 01.07 y usa la misma sesión guardada.
- **Paquete:** `out/steam-s4/OrbisDesk-Steam-S4-01.08.pkg`, con su SHA-256 en `manifest.json`.
- **Partes nuevas de Playden:** `cdn_client`, `depot_manifest`, `depot_chunk` y `game_path`, además de lo de S3. El instalador de Playden (`depot_installer.cpp`) no se usa: necesita `src/installs`, que no está entre los archivos descargados, y lee carpetas con `readdir`, cuya estructura en la consola no es la del SDK.
- **Imports:** pasa el chequeo. Los únicos fuera de `wine.elf` y `hardware.elf` son los seis de S2. `_fstatfs` ya lo importa `wine.elf`.

## Para aceptarla en la consola

1. Abrir la 01.08. Si la sesión de S3 sigue guardada, entra sin QR.
2. Elegir un juego chico con arriba y abajo, y apretar X.
3. Confirmar con X en la pantalla del plan y esperar.
4. **Opcional:** apretar O a mitad de camino, volver a instalar y ver que retoma.
5. Ver la pantalla final: archivos verificados, ejecutable y arquitectura, `steam_api` y SteamStub.

El `steam-client.txt` tiene que terminar en `PWSTEAM client S4 result=pass` y tener `install done`.

Si falla:
- `plan none`: Steam no da acceso a todo el juego o no hay contenido de Windows.
- `install access error=…`: las claves de los depots.
- `install space`: falta espacio.
- `install chunk failed` o `failed=N`: la descarga.
