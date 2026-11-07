# S3: login del usuario por QR y biblioteca

[English](STEAM_S3.md) | [Español](STEAM_S3-es.md)

Es la tercera fase del cliente de Steam. S1 y S2 están en `docs/STEAM_S1.md` y `docs/STEAM_S2.md`. Es la primera fase con cuenta, y **el login lo hace el usuario en la consola**: escanea un código QR con la app Steam del teléfono. El título nunca ve la contraseña, y ni el builder ni nadie más que el usuario inicia sesión.

**Estado:** la 01.07 pasó en la PS4 el 2026-11-07 (`result=pass`): el usuario escaneó el QR, entró y la biblioteca cargó. Ver "Corrida en la consola" al final. **Falta reabrirla** para comprobar que entra sin QR con la sesión guardada.

## Decisiones del usuario (2026-11-07)

1. **Login sólo por QR.** Usuario y contraseña con Steam Guard quedan para más adelante.
2. **qrcodegen de Nayuki** (MIT) para dibujar el QR.
3. **"Mantener sesión iniciada" activado:** la sesión queda guardada en la consola, cifrada. El límite de ese cifrado está explicado abajo, y el usuario lo aceptó.

## Qué hace

`native/steam/steam_s3.cpp`. Cada paso deja una línea `PWSTEAM` en `/data/orbisdesk/steam-s3.txt`.

1. **Reloj, CA y red:** igual que en S2 (`clock`, `ca`, `net init`).
2. **Pantalla y control** (`native/steam/steam_ui.c`):
   - un framebuffer propio de 1920x1080 con `sceVideoOut`, como el camino por CPU de `platform/ps4/pw_wine_sink_ps4.c`;
   - texto con `native/hw_text.h`, que sólo tiene mayúsculas sin tildes, dígitos y `: - . / %`, así que las pantallas están escritas con eso;
   - el control con `scePad`: X, O y triángulo.
   
   Un hilo propio dibuja y lee el control mientras el hilo principal espera la red.
3. **Aviso, una vez por consola:**
   - es un cliente no oficial;
   - usarlo puede ir contra el Acuerdo de Suscriptor de Steam, y Valve puede limitar la cuenta;
   - el ingreso es por QR;
   - la sesión queda guardada y cifrada, y quien copie la carpeta puede usarla.
   
   X acepta y se guarda `notice-accepted`. O sale sin tocar la red de Steam.
4. **Sesión guardada:**
   - si hay una, se recupera con `AuthClient::Restore` de Playden. El access token se usa mientras le quede más de un minuto; si no, se renueva por el CM (`RenewAccessToken`), como hace el cliente de Steam.
   - Si Steam cambió algún token, se vuelve a guardar.
   - Si el refresh token venció o fue revocado, se borra la sesión y se pasa al QR.
   - Si falla por red, la sesión queda guardada y el usuario elige entre reintentar o salir.
5. **Login por QR:** `AuthClient::AuthenticateQr` de Playden (`IAuthenticationService`: `BeginAuthSessionViaQR` y `PollAuthSessionStatus`).
   - El QR se dibuja a la derecha, con instrucciones para la app Steam (*Steam Guard → escanear un código QR*).
   - Si Steam renueva el código, la pantalla se actualiza.
   - O cancela.
   - Si vence (5 minutos), el usuario puede pedir otro.
6. **Biblioteca:**
   - los juegos de la cuenta (`GetOwnedGames`, `LibraryClient` de Playden);
   - las licencias por el CM (`FetchAcquisitionDates`);
   - el PICS de cada juego en tandas de 50, para contar sus depots de Windows con manifiesto público.
   
   La lista va a `/data/orbisdesk/steam-library.txt`, con modo 0600. Cada línea tiene app, depots de Windows, bytes y nombre.
7. **Resumen en pantalla:** cantidad de juegos y cuántos tienen un depot de Windows.
   - **O:** venta.
   - **Triángulo:** cierra la sesión en esta consola, es decir, sobrescribe con ceros y borra `session.bin` y `session.key`.

## La sesión guardada

`native/steam/steam_session.cpp`:

- **`session.key`:** 32 bytes al azar de `/dev/urandom`, modo 0600. Se crea una vez.
- **`session.bin`:** `ODSS` 1, un nonce de 12 bytes y el `StoredSession` cifrado con AES-256-GCM (Mbed TLS), con su tag de 16 bytes. Contiene SteamID, celda, nombre de cuenta, refresh token y access token.
- **Escritura:** primero en `.tmp` con `O_EXCL` y 0600, después `fsync` y `rename`.
- **Lectura:** un archivo alterado no pasa el tag, se descarta y se pide QR de nuevo.

**Límite, dicho sin vueltas:** la PS4 no le da a este título un almacén de claves, así que la clave está en la misma carpeta que la sesión. El cifrado evita que los tokens queden en texto plano:
- en un listado de `/data`;
- en una copia de un solo archivo;
- en una mirada por FTP.

**No protege contra quien copie la carpeta entera** (`/data/orbisdesk/steam/`): con los dos archivos tiene la sesión. Se la puede invalidar desde la cuenta de Steam ("Desautorizar todos los otros dispositivos") o con triángulo en la consola.

## Qué va al log y qué no

- **Va:** nombres de evento, contadores, el método y los códigos HTTP y EResult de un rechazo (el gancho `failure` de Playden), y las líneas del CM, que Playden ya escribe sin IDs de cuenta (`fp=` son 8 hex de SHA-256 del token, que no permiten recuperarlo).
- **No va:**
  - nombre de cuenta, SteamID, tokens ni el enlace del QR (sólo `qr code=N shown=1`);
  - nombres de juegos y la lista de paquetes: las líneas del CM con `package=` o `_packages=` se descartan.
- **Red de seguridad:** `note()` compara cada línea con el nombre de cuenta y los tokens de la corrida. Si alguna los contiene, escribe `line withheld` en su lugar.

## Código de Playden

- **Lo que agrega a S2:** `auth_client`, `password_crypto` (lo enlaza `auth_client`, pero no se usa sin login por contraseña), `library_client` y `src/library/store.cpp`.
- **Parche nuevo `0002-auth-client-wait-const-duration.patch`:** la espera de `AuthClient` hacía `duration_cast` a un tipo `const`. El libc++ de Playden lo acepta y el libstdc++ de la PC no. El parche le saca el `const`, sin cambiar lo que hace.
- **Almacenamiento:** igual que S2, sin `platform/storage.cpp` en la consola (`storage_none.cpp`). S3 guarda la semilla del dispositivo y la sesión por su cuenta, con `open`, `write` y `rename`. Así no aparecen `getdents` ni `seteuid`.

## Cómo se compila

```sh
python3 tools/build-steam-deps.py --target host   # o ps4, si no está hecho
python3 tools/build-steam-s3.py --target host
python3 tools/build-steam-s3.py --target ps4 [--check]
```

- **PC:** `build/steam-s3-host/steam_s3` toma los botones de stdin (`x`, `o`, `t`) y escribe en `steam-data/`.
- **PS4:**
  - título ORBS00001, "OrbisDesk Steam", versión 01.07;
  - se instala encima de S2 01.06;
  - el PKG es `out/steam-s3/OrbisDesk-Steam-S3-01.07.pkg`, con su SHA-256 en `manifest.json`.
- **Imports:** pasa el chequeo. `sceVideoOut*`, `scePad*` y `sceUserService*` ya los importan `wine.elf` o `hardware.elf`. Los únicos fuera de esa lista son los seis de S2, que la 01.06 ya cargó en la consola.

## Pruebas en la PC (2026-11-07)

- **Sin cuenta:**
  - aviso aceptado con `x`;
  - `session load=missing`;
  - Steam entregó un código QR (`qr code=1 shown=1`) y `o` lo canceló (`qr result=canceled`);
  - `result=declined`;
  - el enlace no aparece ni en la salida ni en el log.
- **Archivo de sesión, con datos falsos:**
  - guardar y leer devuelven lo mismo;
  - con un byte alterado da `decrypt`;
  - sin la clave da `missing`;
  - el archivo queda en 0600 y no contiene el texto de los tokens;
  - triángulo borra los dos archivos.

  En `/mnt/c` el modo no se puede comprobar porque WSL no aplica permisos ahí; en `/tmp` pasa.
- **No se probó:** el login real, la renovación por CM ni la biblioteca. Son del usuario, en la consola.

## Para aceptarla en la consola

1. Instalar la 01.07 y abrirla.
2. Aceptar el aviso con X.
3. Escanear el QR con la app Steam y confirmar en el teléfono.
4. Ver el resumen con la cantidad de juegos y salir con O.
5. **Abrirla otra vez:** tiene que entrar sin QR (`session restore error=none`).

El `steam-s3.txt` tiene que terminar en `PWSTEAM S3 result=pass`, sin datos de la cuenta. Antes de pedir más pruebas, reviso el log.

Si falla:
- **`ui …` con un código distinto de 0:** la pantalla o el control. No se tocó Steam.
- **`qr result=network` o `auth refused method=…`:** `IAuthenticationService`, con el código de Steam.
- **`renew error=…`:** la renovación del access token por el CM, al recuperar la sesión.
- **`library owned error=…` o `library pics …`:** la biblioteca.

## Corrida en la consola

**S3 01.07 (2026-11-07): `result=pass`.** El usuario corrió los pasos 1 a 4. La copia del log está en `reports/steam-s3-console/steam-s3-0107.txt`; sólo se bajó `steam-s3.txt`, no la sesión ni la biblioteca.

| Paso | Resultado |
|---|---|
| Reloj y CA | `steady_ms=300 wall_ms=301`, 121 raíces |
| Pantalla y control | todos los módulos y `scePadOpen` dieron bien, `ui ready 1920x1080` |
| Aviso | aceptado y guardado |
| Sesión guardada | ninguna (`load=missing`), primera corrida |
| QR | un código, confirmado en el teléfono en 19,2 s; `signed_in persistence=1` |
| Guardado de la sesión | `session save=none`: `none` es "sin error", o sea que se guardó |
| Juegos de la cuenta | 36 |
| Licencias por el CM | 31 propias, 0 prestadas; 328 apps, 1.632 depots |
| PICS | 36 de 36 descritos, los 36 con depot de Windows |
| Archivo de la biblioteca | escrito |

**Sobre el log:**
- No tiene nombre de cuenta, SteamID, tokens, enlace del QR ni nombres de juegos o paquetes.
- `fp=00cd43df exp=…` es lo que Playden escribe por diseño: los 8 primeros dígitos hex del SHA-256 del refresh token, que no permiten recuperarlo, y su vencimiento en segundos Unix. Sirven para ver si dos corridas usaron el mismo token.
- `lifetime_s=18236196` es la duración del refresh token que dio Steam, unos 211 días.

**Falta el paso 5:** abrirla otra vez. Tiene que mostrar `session load=none`, `session restore error=none`, ningún `qr` y `result=pass`. Como el access token dura poco, si pasó más tiempo puede aparecer antes `renew error=none`.
