# S2: descarga anónima de un depot de Steam

[English](STEAM_S2.md) | [Español](STEAM_S2-es.md)

Es la segunda fase del cliente de Steam (S1 en `docs/STEAM_S1.md`). Baja un depot completo sin cuenta, con el backend de Playden, y verifica cada archivo. Corre en la PC (WSL) y en la PS4. **Aceptada en la consola con la 01.06 (2026-11-07)**; ver al final.

## Qué hace

`native/steam/steam_s2.cpp` sigue los pasos del cliente real. Cada uno deja una línea `PWSTEAM`:

1. **Login en el CM:** pide la lista de servidores a `ISteamDirectory`, abre un WebSocket TLS, manda el saludo y hace el **login anónimo**.
2. **Información de la app:** PICS de la app, interpretado con `ParseAppInfo` de Playden. Lista los depots con su sistema operativo y su manifiesto público, y elige el primero de Windows (o el que se pida con `--depot`).
3. **Acceso al depot:** la clave del depot (`ClientGetDepotDecryptionKey`) y el código del manifiesto (`ContentServerDirectory.GetManifestRequestCode`).
4. **Manifiesto:** pide los servidores de contenido y baja el manifiesto. Después lo descomprime, lo interpreta, descifra los nombres de archivo y lo valida (rutas seguras, chunks contiguos).
5. **Archivos:** por cada chunk lo descarga, lo descifra (AES-256) y lo descomprime (zstd, LZMA o zip). Comprueba el Adler-32 o el SHA-1 del chunk y lo escribe en su posición. Si falla, prueba hasta tres servidores. Al terminar cada archivo compara su SHA-1 con el del manifiesto.
6. **Resultado:** `result=pass` sólo si todos los archivos se escribieron y coincidieron. Con `--max-bytes`, la descarga se corta y el resultado dice `partial`, nunca `pass`.

No usa ningún dato de cuenta. La semilla del dispositivo para el login se genera nueva en cada corrida y no se guarda.

## Código de Playden y cambios propios

- **Fuentes:** `tools/build-steam-s2.py` copia `src/steam` y `src/platform` de `upstream/playden-ps5` (commit `fb74dbf`, comprobado por `REVISION`) al árbol de build y les aplica `native/steam/patches/*.patch`. `upstream/` no se modifica.
- **Parche** `0001-anonymous-logon-and-ca-blob.patch`, con comentarios `OrbisDesk:` en cada cambio:
  - **Login anónimo:** Playden sólo entra con un token de usuario. Se agregan `kAnonUserSteamId`, `EncodeAnonymousLogon` (los campos que manda `LogOnAnonymous` de SteamKit2) e `IsAnonymous`. Una `StoredSession` con ese SteamID y sin token entra sin cuenta.
  - **CA en memoria:** `http_client.cpp` y `ws_client.cpp` pasan el bundle a curl con `CURLOPT_CAINFO_BLOB` y no como ruta, porque `MBEDTLS_FS_IO` está apagado (en la consola arrastraba `getdents`, ver S1).
- **Partes de Playden que se usan:** `proto_wire`, `cm_messages`, `cm_client`, `ws_client`, `http_client`, `native_network`, `json`, `binary_kv`, `vdf`, `app_info`, `content_language`, `app_info_http`, `cdn_client`, `depot_manifest`, `depot_chunk`, `gzip`, `auth_messages`, `token_claims`, `platform/storage` y `platform/effective_uid`. No se usan ni el instalador de Playden ni su login de usuario.

## Dependencias

Todas están en `.deps/steam/downloads`, verificadas por SHA-256. Las compila `tools/build-steam-deps.py --target host` en `build/steam-deps-host/prefix`:

- **Mbed TLS 3.6.6** con `native/steam/mbedtls_user_config.h`, la misma configuración que en S1.
- **curl 8.22.0:** sólo HTTP(S) y WebSocket. Sin rutas de CA propias, sin IPv6 y sin compresión.
- **zstd 1.5.6:** sólo el descompresor.
- **LZMA SDK 24.09:** sólo `LzmaDec`.
- **stb_image.h v2.30:** el inflate que usa Playden, con el SHA-256 que fija Playden (`594c2fe3…`).

## Cómo correrlo

```sh
python3 tools/build-steam-deps.py --target host
python3 tools/build-steam-s2.py --target host
cd build/steam-s2-host && ./steam_s2 [--app N] [--depot N] [--out DIR] [--max-bytes N]
```

Por defecto usa la app 1007, *Steamworks SDK Redist*, que los servidores dedicados instalan sin cuenta. Escribe en `download/<app>/<depot>/`, y el log en `steam-s2.txt`.

## Resultado en la PC (2026-11-07)

|Paso| Resultado |
|---|---|
| Login anónimo en el CM | `step=logon result=ok` |
| App 1007 |3 depósitos: 1004 Windows 1005 macOS, 1006 Linux|
|Depot 1004| clave y código de manifiesto obtenidos |
| Servidores de contenido | 11 |
| Manifiesto | 3.453 bytes (zip): 8 archivos, 69 chunks, 67.863.136 bytes |
| Archivos | 8 de 8 verificados por SHA-1, 0 fallas, 21,7 s (unos 3 MB/s) |
| Resultado | `result=pass` |

Bajó, entre otros, `steamclient.dll` (PE32, i386) y `steamclient64.dll` (PE32+, x86-64). Quedaron en `build/steam-s2-host/download/`, sólo como prueba local: no se distribuyen ni se suben a la consola.

## S2 en la consola

```sh
python3 tools/build-steam-deps.py --target ps4
python3 tools/build-steam-s2.py --target ps4 [--check]
```

- **Título:** ORBS00001, "OrbisDesk Steam S2", versión 01.06, la que pasó en la consola (las 01.02 y 01.03 fallaron, ver abajo). Se instala **encima de S1 01.01** (mismo título), así que S1 conviene correrlo antes. También cuenta las raíces del bundle de CA al arrancar y registra sus primeros bytes: si no carga ninguna, falla ahí.
- **Paquete:** `out/steam-s2/OrbisDesk-Steam-S2-01.06.pkg` (SHA-256 `fed277b1…f12ac6`). El SHA-256 y los fuentes están en `out/steam-s2/manifest.json`. El eboot pesa 2,7 MB; el PKG mide lo mismo que el de S1 por el relleno.
- **Qué hace en la consola:** lo mismo que en la PC, con los valores por defecto. No tiene pantalla:
  - log en `/data/orbisdesk/steam-s2.txt` (hasta la 01.04 era `/data/orbis-win/`);
  - archivos en `/data/orbisdesk/steam/1007/1004/` (unos 68 MB);
  - en la PC tardó entre 20 y 30 s; en la PS4, 11,6 s.

### Cómo se compila para PS4

- **Sin CMake:** las pruebas de CMake enlazan programas de prueba, y eso no funciona en compilación cruzada con OpenOrbis. Mbed TLS, zstd y LZMA se compilan archivo por archivo.
- **curl:** se compila con `native/steam/orbis/curl_config.h`, escrito a mano: HTTP(S) y WebSocket sobre Mbed TLS, sin proxy, cookies ni IPv6. Se le aplica el parche `curl-ps5-native-nonblock.patch` de Playden, que pone los sockets en no bloqueante con `SO_NBIO` de libSceNet, porque el `fcntl` no sirve en la consola.
- **Backend de Playden:** C++17 con el `libc++` del SDK, compilado con `PLAYDEN_PLATFORM_PS5`. Esa macro activa su código de red de consola: el DNS se resuelve con `sceNetResolver` y se le pasa a curl con `CURLOPT_RESOLVE`, y hay una comprobación previa de `SO_NBIO`. libSceNet tiene lo mismo en PS4. `-D_DEFAULT_SOURCE` hace falta porque sin él el `<time.h>` del SDK oculta `nanosleep`, que usa `<thread>`.
- **Constantes de sockets** (`native/steam/orbis/orbis_net_fix.h`): el SDK trae con números de Linux `MSG_NOSIGNAL`, `MSG_DONTWAIT`, `MSG_WAITALL`, `SOCK_NONBLOCK`, `SOCK_CLOEXEC`, `TCP_KEEPIDLE`, `TCP_KEEPINTVL`, `TCP_KEEPCNT` e `IP_BIND_ADDRESS_NO_PORT`. Se reemplazan por los de FreeBSD o se sacan. `TCP_KEEPIDLE` con el número de Linux es `TCP_NOPUSH` en la consola: es el mismo error que trabó el TLS de Pale Moon en W188.
- **Relojes** (`native/steam/orbis/orbis_clock.c`, enlazado con `--wrap=clock_gettime --wrap=clock_getres`): en el SDK `CLOCK_MONOTONIC` vale 1, y en el kernel FreeBSD el 1 es `CLOCK_VIRTUAL`, el tiempo de CPU del proceso. `std::chrono::steady_clock` (compilado así dentro de `libc++.a`) y los temporizadores de curl casi no avanzarían mientras un hilo espera la red, y ningún plazo ni heartbeat llegaría. El wrap traduce los números de Linux a los de FreeBSD (1 → 4, entre otros). Para Wine se había visto lo mismo en W047/W048. La sonda lo mide al empezar: duerme 300 ms y compara `steady_clock` con el reloj real. Si da mal, termina con `fail`.
- **Sin almacenamiento:** `native/steam/orbis/storage_none.cpp` reemplaza a `platform/storage.cpp` de Playden. cm_client sólo lo usa para guardar la semilla del dispositivo, y S2 no guarda nada. Las tres llamadas fallan con un mensaje. Así también se sacan de los imports `opendir`/`readdir` (`getdents`) y `seteuid`. S3 va a necesitar el almacenamiento real.
- **zstd:** con `ZSTD_NO_TRACE`, para no importar sus ganchos de traza.

### Imports nuevos

El builder exige que cada import esté en la última `wine.elf` o en `hardware.elf`, o en la lista `NEW_IMPORTS`, que justifica cada uno. Todos existen en las bibliotecas de stubs del SDK (el enlace con `--no-undefined` lo confirma). Ningún eboot anterior los usaba; la 01.06 los cargó y corrió sin error en la consola.

|Importación| Biblioteca | Quién lo usa |
|---|---|---|
| `sceNetRecv` | libSceNet | `native_network.cpp` de Playden: la prueba de `SO_NBIO` |
| `sceNetResolverAbort` | libSceNet | `native_network.cpp` de Playden: DNS cancelado |
| `sceNetGetDnsInfo` | libSceNet | el resolver musl del SDK, que entra por el `getaddrinfo` de curl. No se usa, porque `CURLOPT_RESOLVE` lo saltea |
| `__pthread_cleanup_push_imp`, `__pthread_cleanup_pop_imp` |libkernel| el mismo resolver musl |
| `pthread_equal` |libkernel| `std::recursive_mutex` de libc++ |

### Para aceptarlo

La última línea de `steam-s2.txt` tiene que ser `PWSTEAM S2 result=pass`, con `files regular=8 verified=8`. Si falla, el log dice en qué paso:
- `clock … ok=0`: el reloj, antes de tocar la red.
- `cm … step=…`: el login en el CM.
- `access`, `cdn` o `manifest`: la clave del depot, los servidores de contenido o el manifiesto.
- `chunk` o `file`: la descarga de los archivos.

La escritura en USB, con el modo ROOT, queda para la versión siguiente.

### Corridas en la consola

**S1 01.01 (2026-11-07): `result=pass`.**
- Se confirmó la causa del fallo de la 01.00: `fstat` daba `st_size=384` y se leyeron 188.900 bytes.
- Se cargaron 121 raíces.
- Steam respondió por TLS 1.3 con HTTP 200 y 12 servidores.
- `untrusted-root` se rechazó con `0x08` y `expired` con `0x01`.

**S2 01.02 (2026-11-07): `result=fail`.**
- El reloj dio bien (`steady_ms=300 wall_ms=300`) y el bundle cargó 121 raíces.
- El primer pedido, el directorio de CM, falló con `cm step=directory error=network http=0`, sin más detalle.
- **Causa probable:** la `main` de S2 llamaba a `sceNetInit()`, y después `InitializeNativeNetworkOnce` de Playden lo vuelve a llamar y exige que devuelva 0. En la PS4 una segunda llamada devuelve error (`platform/ps4/pw_ws2_32_libc.c`). Con eso, Playden marca la red como no inicializada y su `HttpClient` contesta `kInitializationFailed` sin llegar a curl.

**Cambios en S2 01.03:**
- Ya no llama a `sceNetInit`: lo hace Playden.
- Agrega un diagnóstico de red antes del CM (`native/steam/steam_netdiag.cpp`, líneas `PWSTEAM netdiag`):
  - la inicialización de Playden;
  - su comprobación de `SO_NBIO`, rehecha valor por valor;
  - un pedido con el `HttpClient` de Playden, con categoría, código de curl, dirección y tiempos;
  - curl solo, con `CURLOPT_ERRORBUFFER`, los tiempos de `CURLINFO` y su texto de depuración.
- El pedido al directorio registra su error completo (línea `PWSTEAM directory`).
- curl se compila con sus textos de depuración (sin `CURL_DISABLE_VERBOSE_STRINGS`).

**S2 01.03 (2026-11-07): `result=fail`.** El log completo está en `build/steam-s2-ps4-v0103.txt`.
- **Lo que anduvo:**
  - la inicialización de Playden (`init=1`, así que la causa que se sospechaba en la 01.02 quedó descartada);
  - su comprobación de `SO_NBIO` (`playden_pass=1`);
  - el resolver nativo;
  - curl solo: TLS 1.3, HTTP 200, `code=0`.
- **Lo que falló:** todo pedido del `HttpClient` de Playden terminaba al instante con `protocol_error curl=2` (`CURLE_FAILED_INIT`), sin resolver ni conectar.
- **Causa, confirmada en el código de curl:** el `curl_config.h` de PS4 apagaba el proxy, las cookies, alt-svc, HSTS, NTLM, Kerberos, Negotiate y AWS, cosa que la build de la PC no hace. Con `CURL_DISABLE_PROXY`, `CURLOPT_PROXY` ni siquiera existe como opción (`setopt.c`), y Playden la usa (con `""`). La `PLAYDEN_SETOPT` que fallaba saltaba a `cleanup` con el `CURLE_FAILED_INIT` inicial.
- **Cambios en S2 01.04:**
  - `curl_config.h` apaga sólo lo mismo que la build de la PC.
  - El diagnóstico prueba, una por una, las opciones que pone Playden sobre un handle nuevo y registra las que curl rechace (`PWSTEAM netdiag options … refused=N`). En la PC da `refused=0`.

**S2 01.06 (2026-11-07): `result=pass`.** Es la versión que corrió después de la 01.04: el título se presenta como OrbisDesk y las rutas pasaron a `/data/orbisdesk/`. El log completo está en `reports/steam-s2-console/steam-s2-0106.txt` (en la consola, `/data/orbisdesk/steam-s2.txt`).

|Paso| Resultado |
|---|---|
| Reloj y CA | `steady_ms=300 wall_ms=301`, 121 raíces |
| Red de Playden | `init=1`, `playden_pass=1`, `options refused=0` |
| `HttpClient` de Playden |HTTP 200, 3.158 bytes, 1,2 s|
| Directorio de CM | HTTP 200 |
| Login anónimo | `step=logon result=ok` |
| PICS de la app 1007 | 3 depots, igual que en la PC |
|Depot 1004| clave y código de manifiesto obtenidos |
| Servidores de contenido | 11 |
| Manifiesto | 3.453 bytes: 8 archivos, 69 chunks, 67.863.136 bytes |
| Archivos | 8 de 8 verificados por SHA-1, 0 fallas, 11,6 s (5.733 KiB/s) |

Con esto S2 queda aceptada. En la PS4 funcionan, con el backend de Playden:
- TLS y el WebSocket al CM;
- PICS y los servidores de contenido;
- el descifrado, la descompresión y la verificación de los chunks.

Quedan para S3 y S4 la escritura en USB (modo ROOT) y el almacenamiento real.
