<a id="s3-login-del-usuario-por-qr-y-biblioteca"></a>


# S3: user login by QR and library

[English](STEAM_S3.md) | [Español](STEAM_S3-es.md)

It's the third phase of the Steam customer. S1 and S2 are in `docs/STEAM_S1.md` and `docs/STEAM_S2.md`. It is the first phase with account, and **the login is done by the user on the** console: it scans a QR code with the phone app Steam. The title never sees the password, and neither the builder nor anyone else that the user log in.

**Status:** 01.07 passed on the PS4 on 2026-11-07 (`result=pass`): the user scanned the QR code, signed in, and the library loaded. See "Console run" at the end. **Still to do:** reopen it, to check that it signs in from the saved session without a QR code.

<a id="decisiones-del-usuario-2026-11-07"></a>


## User decisions (2026-11-07)

1. **Login only for QR.** User and password with Steam Guard are left for later.
2. **qrcodegen of Nahuki** (MIT) to draw the QR.
3. **"Keep session started" activated:** the session is saved on the console, encrypted. The limit of that encryption is explained below, and the user accepted it.

<a id="qué-hace"></a>


## What are you doing?

`native/steam/steam_s3.cpp`. Each step leaves a line `PWSTEAM` in `/data/orbisdesk/steam-s3.txt`.

1. **Clock, CA and network:** as in S2 (`clock`, `ca`, `net init`.
2. **Display and control** (`native/steam/steam_ui.c`):
   - a 1920x1080 own framebuffer with `sceVideoOut`, as the path by CPU of `platform/ps4/pw_wine_sink_ps4.c`;
   - text with `native/hw_text.h`, which only has capital letters without typing, digits and `: - . / %`, so the screens are written with that;
   - the control with `scePad`: X, O and triangle.
   
   A thread of its own draws and reads the control while the main thread waits for the net.
3. **Warning, once per console:**
   - is an unofficial client;
   - using it can go against the Steam Subscriber Agreement, and Valve can limit the account;
   - the income is by QR;
   - the session is saved and encrypted, and whoever copies the folder can use it.
   
   X accepts and is saved `notice-accepted`. Or it goes out without touching the Steam network.
4. **Sitting:**
   - If there is one, it is recovered with `AuthClient::Restore` of Playden. Access token is used for more than a minute; If not, it is renewed by the CM (`RenewAccessToken`), as does the customer of Steam.
   - If Steam changed some token, it is stored again.
   - If the refresh token was defeated or revoked, the session is deleted and passed to the QR.
   - If the network fails, the session is saved and the user chooses between retrying or leaving.
5. **Login for QR:** `AuthClient::AuthenticateQr` of Playden (`IAuthenticationService`: `BeginAuthSessionViaQR` and `PollAuthSessionStatus`).
   - The QR is drawn to the right, with instructions for the app Steam (* Steam Guard → scan a QR code *).
   - If Steam renews the code, the screen is updated.
   - Or cancel.
   - If you expire (5 minutes), the user can order another.
6. **Library:**
   - the sets of the account (`GetOwnedGames`, `LibraryClient` of Playden);
   - CM licences (`FetchAcquisitionDates`);
   - the PICS of each set in tandas of 50, to count its depots of Windows with public manifesto.
   
   The list goes to `/data/orbisdesk/steam-library.txt`, with 0600 mode. Each line has app, Windows depots, bytes and name.
7. **On-screen summary:** number of games and how many have a depot of Windows.
   - **O:** sale.
   - **Triangle:** closes the session on this console, that is, overwrite with zeros and erase `session.bin` and `session.key`.

<a id="la-sesión-guardada"></a>


## The saved session

`native/steam/steam_session.cpp`:

- **`session.key`:** 32 random bytes of `/dev/urandom`, 0600 mode. It's created once.
- **`session.bin`:** `ODSS` 1, a nonce of 12 bytes and `StoredSession` encrypted with ES- 256 -GCM (Mbed TLS), with its tag of 16 bytes. Contains SteamID, cell, account name, refresh token and access token.
- **Scripture:** first in `.tmp` with `O_EXCL` and 0600, then `fsync` and `rename`.
- **Reading:** an altered file does not pass the tag, it is discarded and QR is asked again.

**Limit, said without turning:** the PS4 does not give this title a key store, so the key is in the same folder as the session. The encryption prevents the tokens from remaining in flat text:
- in a list of `/data`;
- in a copy of a single file;
- in a look for FTP.

**It does not protect against those who copy the entire folder** (`/data/orbisdesk/steam/`): with the two files you have the session. It can be invalidated from the Steam account ("Disable all other devices") or with a triangle on the console.

<a id="qué-va-al-log-y-qué-no"></a>


## What goes to the log and what doesn't

- **Go:** event names, counters, method and HTTP and EResult codes of a rejection (the `failure` hook of Playden), and CM lines, which Playden already writes without account IDs (`fp=` are 8 SHA- 256 of the token, which do not allow to recover it).
- **No va:**
  - account name, SteamID, tokens or the link of the QR (only `qr code=N shown=1`);
  - game names and package list: CM lines with `package=` or `_packages=` are discarded.
- **Safety network:** `note()` compares each line with the account name and the tokens of the Runs. If any of them contain them, write `line withheld` in place.

<a id="código-de-playden"></a>


## Playden

- **What you add to S2:** `auth_client`, `password_crypto` (links it `auth_client`, but is not used without password login), `library_client` and `src/library/store.cpp`.
- **New patch `0002-auth-client-wait-const-duration.patch`:** the waiting of `AuthClient` made `duration_cast` to a type `const`. The libc + + of Playden accepts it and the libstdc + + of the PC does not. The patch takes out the `const`, without changing what it does.
- **Storage:** just like S2, without `platform/storage.cpp` on the console (`storage_none.cpp`). S3 keeps the seed of the device and session on its own, with `open`, `write` and `rename`. So they do not appear `getdents` or `seteuid`.

<a id="cómo-se-compila"></a>


## How it is compiled

```sh
python3 tools/build-steam-deps.py --target host   # o ps4, si no está hecho
python3 tools/build-steam-s3.py --target host
python3 tools/build-steam-s3.py --target ps4 [--check]
```

- **PC:** `build/steam-s3-host/steam_s3` takes the stdin buttons (`x`, `o`, `t`) and writes in `steam-data/`.
- **PS4:**
  - Title ORBS00001, "OrbisDesk Steam," version 01.07;
  - is installed above S2 01.06;
  - The PKG is `out/steam-s3/OrbisDesk-Steam-S3-01.07.pkg`, with your SHA- 256 in `manifest.json`.
- **Imports:** passes the check-up. `sceVideoOut*`, `scePad*` and `sceUserService*` already matter to them `wine.elf` or `hardware.elf`. The only ones out of that list are the six of S2, which the 01.06 already loaded on the console.

<a id="pruebas-en-la-pc-2026-11-07"></a>


## Tests on the PC (2026-11-07)

- **No account:**
  - notice accepted with `x`;
  - `session load=missing`;
  - Steam delivered a QR code (`qr code=1 shown=1`) and `o` cancelled it (`qr result=canceled`;
  - `result=declined`;
  - the link does not appear either on the output or on the log.
- **Session file, with false data:**
  - save and read the same;
  - with an altered byte of `decrypt`;
  - without the key given `missing`;
  - the file is left in 0600 and does not contain the text of the tokens;
  - triangle erases the two files.

  In `/mnt/c` the mode cannot be checked because WSL does not apply permits there; In `/tmp` pass.
- **The actual login, CM renewal and library were not tested:**. They're from the user, on the console.

<a id="para-aceptarla-en-la-consola"></a>


## To accept it on the console

1. Install the 01.07 and open it.
2. Accept the notice with X.
3. Scan the QR with the app Steam and confirm on the phone.
4. See the summary with the number of games and go out with O.
5. **Open it again:** you have to enter without QR (`session restore error=none`).

The `steam-s3.txt` has to end in `PWSTEAM S3 result=pass`, without account data. Before I ask for further evidence, I'll check the log.

If you fail:
- **`ui …` with a code other than 0:** the screen or control. It didn't touch Steam.
- **`qr result=network` or `auth refused method=…`:** `IAuthenticationService`, with the code of Steam.
- **`renew error=…`:** the renewal of the access token by the CM, when the session is back.
- **`library owned error=…` or `library pics …`:** library.

<a id="corrida-en-la-consola"></a>


## Console run

**S3 01.07 (2026-11-07): `result=pass`.** The user ran steps 1 to 4. A copy of the log is in `reports/steam-s3-console/steam-s3-0107.txt`; only `steam-s3.txt` was fetched, not the session or the library file.

| Step | Result |
|---|---|
| Clock and CA | `steady_ms=300 wall_ms=301`, 121 roots |
| Screen and pad | every module and `scePadOpen` succeeded, `ui ready 1920x1080` |
| Notice | accepted and saved |
| Saved session | none (`load=missing`), first run |
| QR | one code, confirmed on the phone in 19.2 s; `signed_in persistence=1` |
| Saving the session | `session save=none`: `none` means "no error", so it was saved |
| Owned games | 36 |
| Licenses from the CM | 31 own, 0 borrowed; 328 apps, 1,632 depots |
| PICS | 36 of 36 described, all 36 with a Windows depot |
| Library file | written |

**About the log:**
- It has no account name, Steam ID, token, QR link, or game or package names.
- `fp=00cd43df exp=…` is what Playden writes by design: the first 8 hex digits of the refresh token's SHA-256, from which the token can't be recovered, and its expiry in Unix seconds. They show whether two runs used the same token.
- `lifetime_s=18236196` is the refresh token's lifetime as Steam issued it, about 211 days.

**Step 5 is still to do:** open it again. The log must show `session load=none`, `session restore error=none`, no `qr` line, and `result=pass`. The access token is short-lived, so after a while a `renew error=none` line may come first.
