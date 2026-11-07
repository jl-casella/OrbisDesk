# S1: HTTPS nativo para el cliente de Steam (ORBS00001)

[English](STEAM_S1.md) | [Español](STEAM_S1-es.md)

Es la primera fase del cliente de Steam. Una sonda nativa de PS4, sin Wine y sin cuenta de Steam, comprueba que la consola puede hacer HTTPS por su cuenta con validación de certificados.

## Qué es

- **Título:** ORBS00001, "OrbisDesk Steam S1", versión 01.01 (la 01.00 falló en la consola, ver abajo). Es el título propio del cliente de Steam, aparte de OrbisDesk (ORBW00002) y de las sondas reemplazables (ORBB00001).
- **Licencia:** GPL-3.0 o posterior, porque el cliente reutilizará código de Playden (`upstream/playden-ps5`, commit `fb74dbf`). En S1 todavía no hay código de Playden: la sonda es propia. Los textos de licencia (GPL-3.0 y Apache-2.0 de Mbed TLS) van en el paquete, en `/app0/assets/misc/`.
- **Fuentes:** `native/steam/steam_probe.c`, `steam_tls.c`/`.h` y `mbedtls_user_config.h`. Builder: `tools/build-steam-probe.py`.
- **Dependencias** (en `.deps/steam/downloads`, verificadas por SHA-256 en el builder):
  - Mbed TLS 3.6.6
  - bundle de CA de Mozilla del 2026-09-25 (121 raíces).
  - curl, zstd y el LZMA SDK ya están descargados, pero S1 no los usa.

## Qué comprueba

Cada línea del log empieza con `PWSTEAM`. El log queda en `/data/orbis-win/steam-probe.txt` y también sale por `sceKernelDebugOutText`.

1. **Reloj:** la hora UTC de la consola. Si está atrasada o adelantada, ningún certificado valida.
2. **Entropía:** `/dev/urandom`, dos lecturas de 32 bytes. Ninguna puede ser todo ceros y tienen que ser distintas entre sí. Es la única fuente que recibe Mbed TLS (`MBEDTLS_ENTROPY_HARDWARE_ALT`). Si falla, la sonda no intenta TLS y lo dice.
3. **CA:** lee `/app0/assets/misc/cacert.pem` y cuenta las raíces cargadas.
4. **Steam:** `GET https://api.steampowered.com/IContentServerDirectoryService/GetServersForSteamPipe/v1/?cell_id=0`, una llamada pública que no usa cuenta. Pasa si:
   - el handshake completa sin marcas de verificación;
   - la respuesta es HTTP 200;
   - la respuesta lista al menos un servidor (`"vhost"`).
5. **Rechazos esperados:** `untrusted-root.badssl.com` tiene que fallar por raíz no confiable (`0x08`) y `expired.badssl.com` por certificado vencido (`0x01`). Así se ve que se usan el almacén y el reloj, y no sólo que el handshake termina.
6. **Resultado:** la última línea es `PWSTEAM S1 result=pass` o `result=fail failed=…`, con los nombres de los pasos que fallaron.

La sonda no tiene pantalla: termina sola unos segundos después y vuelve al menú.

## Detalles de la consola

- **Sockets:** son bloqueantes, con `poll` de 15 s antes de cada lectura. DNS por `sceNetResolverStartNtoa`, como `platform/ps4/pw_ws2_32_libc.c`. Antes se cargan el módulo de red y `sceNetInit`. Sólo IPv4.
- **Configuración de Mbed TLS:** sin `MBEDTLS_NET_C`, `TIMING_C`, `FS_IO` ni almacenamiento PSA en disco. `FS_IO` arrastraba `getdents`, que ningún eboot en uso importa: el bundle se lee con `open`/`read`. Los hilos de Mbed TLS están activos, como en Playden.
- **Imports:** el builder exige que la sonda importe sólo lo que ya importa la última `wine.elf` o `hardware.elf`. Esta versión pasa ese chequeo.
- **SIGPIPE:** se ignora, para que un servidor que cierra durante una escritura no termine el título.

## Resultado en la PC (2026-11-07)

`python3 tools/build-steam-probe.py --host` compila el mismo código para Linux, en `build/steam-probe-host`. En WSL dio:

- **Steam:** TLS 1.3 (`TLS1-3-CHACHA20-POLY1305-SHA256`), HTTP 200 y 12 servidores.
- **untrusted-root:** rechazado con `verify_flags=0x08`.
- **expired:** rechazado con `0x01`.
- **Resultado:** `result=pass`.

## Paquete

- `out/steam-probe-s1/IV0000-ORBS00001_00-ORBISWINSTEAM001.pkg`: 6.619.136 bytes. El SHA-256 está en `out/steam-probe-s1/manifest.json`.
- El builder no sube nada: el PKG lo sube la sesión de builds.

## Pendiente

### Primera corrida en la consola: 01.00, 2026-11-07, `result=fail`

- **Lo que anduvo:** cargó el módulo de red, `sceNetInit` dio 0, el reloj marcó 2026-11-07T11:06:20Z, la entropía dio `ok=1` y el DRBG arrancó.
- **Lo que falló:** `ca … roots=0` con "The CRT/CRL/CSR format is invalid". Por eso nunca intentó HTTPS.
- **Causa probable:** la 01.00 dimensionaba la lectura del bundle con `fstat`. El `struct stat` del SDK es el de musl, y el kernel es FreeBSD (W180/W218 encontraron lo mismo con `statfs`), así que `st_size` puede no estar donde el SDK lo busca. Con un tamaño chico, el buffer no tiene la cabecera PEM ni el `\0` final. Mbed TLS lo toma entonces como DER, y ese es justo el error que dio.
- **Arreglo, en la 01.01:** lee hasta el final del archivo sin `fstat` y registra `ca read bytes=… fstat_rc=… st_size=… head=…`. Si la causa es otra, esa línea lo va a mostrar.

**Falta la corrida de la 01.01 en la consola.** Para dar S1 por aceptada hace falta el `steam-probe.txt` de la PS4 con `result=pass`.

Si falla:
- `entropy ok=0`: hay que buscar otra fuente de entropía antes de seguir.
- `verify_flags` con `0x200` (fecha futura) o `0x01` en Steam: el reloj de la consola está mal.
- `dns … found=0` o `connect=-1` con `errno`: el problema es de red, no de TLS.
