<a id="s2-descarga-anónima-de-un-depot-de-steam"></a>


# S2: anonymous download of a Steam depot

[English](STEAM_S2.md) | [Español](STEAM_S2-es.md)

It is the second phase of the customer of Steam (S1 in `docs/STEAM_S1.md`). Lower a complete, no account, with the Playden backend, and check each file. It runs on the PC (WSL) and on the PS4. **Accepted in the console with 01.06 (2026-11-07)**; see at the end.

<a id="qué-hace"></a>


## What are you doing?

`native/steam/steam_s2.cpp` follow the steps of the real client. Each leaves a line `PWSTEAM`:

1. **Login in the CM:** requests the server list at `ISteamDirectory`, opens a WebSocket TLS, send the greeting and do the **anonymous login**.
2. **App information:** App PICS, played with `ParseAppInfo` of Playden. List the depots with your operating system and public manifesto, and choose the first of Windows (or the one requested with `--depot`).
3. **Depot access:** the Depot key (`ClientGetDepotDecryptionKey`) and the manifest code (`ContentServerDirectory.GetManifestRequestCode`.
4. **Manifesto:** order the content servers and lower the manifesto. Then it decompresses, interprets it, decouples the file names and validates it (safe routes, contiguous chunks).
5. **Files:** for each chunk you download it, disfigure it (AES- 256) and decompress it (zstd, LZMA or zip). Check the Adler- 32 or the SHA- 1 of the chunk and write it in its position. If it fails, try up to three servers. At the end of each file, compare your SHA- 1 to that of the manifesto.
6. **Result:** `result=pass` only if all files were written and matched. With `--max-bytes`, the download is cut and the result says `partial`, never `pass`.

He doesn't use any account data. The seed of the device for the login is generated new in each Runs and is not saved.

<a id="código-de-playden-y-cambios-propios"></a>


## Code of Playden and own changes

- **Sources:** `tools/build-steam-s2.py` copy `src/steam` and `src/platform` of `upstream/playden-ps5` (commit `fb74dbf`, tested by `REVISION`) to the building tree and applied `native/steam/patches/*.patch` to them. `upstream/` is not modified.
- **Plot** `0001-anonymous-logon-and-ca-blob.patch`, with comments `OrbisDesk:` in each change:
  - **Anonymous login:** Playden only comes in with a user token. They are added `kAnonUserSteamId`, `EncodeAnonymousLogon` (the fields that command `LogOnAnonymous` of SteamKit2) and `IsAnonymous`. One `StoredSession` with that SteamID and no token comes in without account.
  - **CA in memory:** `http_client.cpp` and `ws_client.cpp` pass the bundle to curl with `CURLOPT_CAINFO_BLOB` and not as a route, because `MBEDTLS_FS_IO` is off (on the console it dragged `getdents`, see S1).
- **Parts of Playden used:** `proto_wire`, `cm_messages`, `cm_client`, `ws_client`, `http_client`, `native_network`, `json`, `binary_kv`, `vdf`, `app_info`, `content_language`, `app_info_http`, `cdn_client`, `depot_manifest`, `depot_chunk`, `gzip`, `auth_messages`, `token_claims`, `platform/storage` and `platform/effective_uid`. The Playden installer and its user login are not used.

<a id="dependencias"></a>


## Units

They are all in `.deps/steam/downloads`, verified by SHA- 256. It compiles them `tools/build-steam-deps.py --target host` in `build/steam-deps-host/prefix`:

- **Mbed TLS 3.6.6** with `native/steam/mbedtls_user_config.h`, the same configuration as in S1.
- **curl 8.22.0:** only HTTP (S) and WebSocket. No CA routes, no IPv6 and no compression.
- **zstd 1.5.6:** only the decompressor.
- **LZMA SDK 24.09:** only `LzmaDec`.
- **stb_image.h v2.30:** the inflate you use Playden, with the SHA-256 fixing Playden (`594c2fe3…`).

<a id="cómo-correrlo"></a>


## How to run it

```sh
python3 tools/build-steam-deps.py --target host
python3 tools/build-steam-s2.py --target host
cd build/steam-s2-host && ./steam_s2 [--app N] [--depot N] [--out DIR] [--max-bytes N]
```

By default use the app 1007, * Steamworks SDK Redist *, which the dedicated servers install without account. Write in `download/<app>/<depot>/`, and log in `steam-s2.txt`.

<a id="resultado-en-la-pc-2026-11-07"></a>


## PC result (2026-11-07)

| Paso |Result|
|---|---|
|Anonymous login in CM| `step=logon result=ok` |
|App 1007| 3 depots: 1004 Windows, 1005 macOS, 1006 Linux |
| Depot 1004 |the key and manifest code obtained|
|Content servers| 11 |
|Manifesto|3.453 bytes (zip): 8 files, 69 chunks, 67.863.136 bytes|
|Files|8 of 8 verified by SHA- 1, 0 faults, 21,7 s (about 3 MB/s)|
|Result| `result=pass` |

He went down, among others, `steamclient.dll` (PE32, i386) and `steamclient64.dll` (PE32 +, x86 - 64. They were left in `build/steam-s2-host/download/`, only as a local test: they are not distributed or uploaded to the console.

<a id="s2-en-la-consola"></a>


## S2 on the console

```sh
python3 tools/build-steam-deps.py --target ps4
python3 tools/build-steam-s2.py --target ps4 [--check]
```

- **Title:** ORBS00001, "OrbisDesk Steam S2," version 01.06, The one that happened on the console (the 01.02 and 01.03 failed, see below). It is installed **above S1 01.01** (same title), so S1 should run it before. It also counts the roots of the CA bundle when starting and records its first bytes: if it does not load any, it fails there.
- **Package:** `out/steam-s2/OrbisDesk-Steam-S2-01.06.pkg` (SHA-256 `fed277b1…f12ac6`). The SHA-256 and the sources are in `out/steam-s2/manifest.json`. The eboot weighs 2,7 MB; the PKG measures the same as the S1 by the filling.
- **What are you doing on the console?:** the same as on the PC, with the default values. No screen.:
  - log in `/data/orbisdesk/steam-s2.txt` (until 01.04 was `/data/orbis-win/`);
  - files in `/data/orbisdesk/steam/1007/1004/` (about 68 MB);
  - on the PC it took between 20 and 30 s; in the PS4, 11,6 s.

<a id="cómo-se-compila-para-ps4"></a>


### How to compile for PS4

- **Without CMake:** CMake tests link test programs, and that doesn't work in cross-compilation with OpenOrbis. Mbed TLS, zstd and LZMA are compiled file by file.
- **curl:** is compiled with `native/steam/orbis/curl_config.h`, handwritten: HTTP (S) and WebSocket over Mbed TLS, no proxy, cookies or IPv6. The `curl-ps5-native-nonblock.patch` patch of Playden is applied, which puts the sockets in non-blocker with `SO_NBIO` of libSceNet, because the `fcntl` It's not on the console.
- **Backend of Playden:** C + + 17 with `libc++` of SDK, compiled with `PLAYDEN_PLATFORM_PS5`. That macro activates your console network code: the DNS is solved with `sceNetResolver` and is passed to curl with `CURLOPT_RESOLVE`, and there is a prior check of `SO_NBIO`. libSceNet has the same in PS4. `-D_DEFAULT_SOURCE` is necessary because without it the `<time.h>` of the SDK hidden `nanosleep`, which it uses `<thread>`.
- **Socket Constants** (`native/steam/orbis/orbis_net_fix.h`): the SDK brings with numbers Linux `MSG_NOSIGNAL`, `MSG_DONTWAIT`, `MSG_WAITALL`, `SOCK_NONBLOCK`, `SOCK_CLOEXEC`, `TCP_KEEPIDLE`, `TCP_KEEPINTVL`, `TCP_KEEPCNT` and `IP_BIND_ADDRESS_NO_PORT`. They are replaced by those of FreeBSD or taken out. `TCP_KEEPIDLE` with the number of Linux is `TCP_NOPUSH` on the console: it is the same error that has been traced by TLS of Pale Moon in W188.
- **Watches** (`native/steam/orbis/orbis_clock.c`, linked to `--wrap=clock_gettime --wrap=clock_getres`): in SDK `CLOCK_MONOTONIC` worth 1, and in the kernel FreeBSD the 1 is `CLOCK_VIRTUAL`, the time of CPU of the process. `std::chrono::steady_clock` (thus compiled within `libc++.a`) and the curl timers would hardly advance while a thread is waiting for the net, and no time or Heartbeat would come. The wrap translates the numbers of Linux to those of FreeBSD (1 → 4, among others). By Wine the same thing had been seen in W047/W048. The probe measures it at first: it sleeps 300 ms and compares `steady_clock` with the real watch. If it goes wrong, it ends with `fail`.
- **No storage:** `native/steam/orbis/storage_none.cpp` replaces `platform/storage.cpp` of Playden. cm_client only uses it to save the seed from the device, and S2 keeps nothing. All three calls fail with a message. They are also removed from the imports `opendir` / `readdir` (`getdents`) and `seteuid`. S3 is going to need the real storage.
- **zstd:** with `ZSTD_NO_TRACE`, not to import your trace hooks.

<a id="imports-nuevos"></a>


### New imports

The builder requires that each import be in the last `wine.elf` or `hardware.elf`, or in the list `NEW_IMPORTS`, which each justifies. They all exist in the stubs libraries of SDK (the link with `--no-undefined` confirms it). No previous eboot used them; The 01.06 carried them and ran without error on the console.

| Import |Library|Who uses it?|
|---|---|---|
| `sceNetRecv` | libSceNet |`native_network.cpp` of Playden: the test of `SO_NBIO`|
| `sceNetResolverAbort` | libSceNet |`native_network.cpp` of Playden: DNS cancelled|
| `sceNetGetDnsInfo` | libSceNet |the resolution musl of the SDK, which enters by the `getaddrinfo` of curl. It's not used, because `CURLOPT_RESOLVE` it's skipped.|
| `__pthread_cleanup_push_imp`, `__pthread_cleanup_pop_imp` | libkernel |the same solve musl|
| `pthread_equal` | libkernel |`std::recursive_mutex` of libc + +|

<a id="para-aceptarlo"></a>


### To accept it

The last line of `steam-s2.txt` has to be `PWSTEAM S2 result=pass`, with `files regular=8 verified=8`. If it fails, the log says in what step:
- `clock … ok=0`: the clock, before touching the network.
- `cm … step=…`: the login in the CM.
- `access`, `cdn` or `manifest`: the key to the depot, the content servers or the manifesto.
- `chunk` or `file`: downloading the files.

The USB writing, with the ROOT mode, is left for the next version.

<a id="corridas-en-la-consola"></a>


### Runs on the console

**S1 01.01 (2026-11-07: `result=pass`.**
- The cause of the 01.00 failure was confirmed: `fstat` gave `st_size=384` and read 188.900 bytes.
- They were loaded. 121 roots.
- Steam responded by TLS 1.3 with HTTP 200 and 12 servers.
- `untrusted-root` was rejected with `0x08` and `expired` with `0x01`.

**S2 01.02 (2026-11-07): `result=fail`.**
- The clock was good (`steady_ms=300 wall_ms=300`) and the bundle loaded 121 roots.
- The first order, the CM directory, failed with `cm step=directory error=network http=0`, without further details.
- **probable cause:** the `main` of S2 called `sceNetInit()`, and then `InitializeNativeNetworkOnce` of Playden calls him back and demands that he return 0. In the PS4 a second call returns error (`platform/ps4/pw_ws2_32_libc.c`). With that, Playden marks the network as non-initialized and its `HttpClient` answers `kInitializationFailed` without reaching curl.

**S2 changes 01.03:**
- He no longer calls `sceNetInit`: he does Playden.
- Add a network diagnosis before CM (`native/steam/steam_netdiag.cpp`, lines `PWSTEAM netdiag`):
  - the initialization of Playden;
  - its verification of `SO_NBIO`, redone value by value;
  - an order with the `HttpClient` of Playden, with category, curl code, direction and times;
  - curl alone, with `CURLOPT_ERRORBUFFER`, the times of `CURLINFO` and its debugging text.
- The order to the directory records your complete error (line `PWSTEAM directory`).
- curl is compiled with its debugging texts (without `CURL_DISABLE_VERBOSE_STRINGS`).

**S2 01.03 (2026-11-07): `result=fail`.** The full log is in `build/steam-s2-ps4-v0103.txt`.
- **What I walked:**
  - the initialization of Playden (`init=1`, so the cause suspected in 01.02 was excluded);
  - its verification of `SO_NBIO` (`playden_pass=1`);
  - the native resolution;
  - only: TLS 1.3, HTTP 200, `code=0`.
- **What failed:** every order of `HttpClient` of Playden ended instantly with `protocol_error curl=2` (`CURLE_FAILED_INIT`), not solved or connected.
- **Cause, confirmed in the curl code:** the `curl_config.h` of PS4 turned off the proxy, cookies, alta-svc, HSTS, NTLM, Kerberos, Negotiate and AWS, which the PC build does not do. With `CURL_DISABLE_PROXY`, `CURLOPT_PROXY` it doesn't even exist as an option (`setopt.c`), and Playden it uses it (with `""`). The failed `PLAYDEN_SETOPT` would jump at `cleanup` with the initial `CURLE_FAILED_INIT`.
- **S2 changes 01.04:**
  - `curl_config.h` just turn off the same thing as the PC build.
  - The diagnosis tests, one by one, the options that put Playden on a new handle and records the ones that curl rejects (`PWSTEAM netdiag options … refused=N`). On the PC it gives `refused=0`.

**S2 01.06 (2026-11-07): `result=pass`.** It is the version that ran after 01.04: the title is presented as OrbisDesk and the routes passed to `/data/orbisdesk/`. The full log is in `reports/steam-s2-console/steam-s2-0106.txt` (on the console, `/data/orbisdesk/steam-s2.txt`).

| Paso |Result|
|---|---|
|Clock and CA|`steady_ms=300 wall_ms=301`, 121 roots|
|Network of Playden| `init=1`, `playden_pass=1`, `options refused=0` |
|`HttpClient` of Playden| HTTP 200, 3.158 bytes, 1,2 s |
|CM Directory| HTTP 200 |
|Anonymous login| `step=logon result=ok` |
|PICS of the app 1007|3 depots, as in the PC|
| Depot 1004 |the key and manifest code obtained|
|Content servers| 11 |
|Manifesto|3.453 bytes: 8 files, 69 chunks, 67.863.136 bytes|
|Files|8 of 8 verified by SHA- 1, 0 faults, 11,6 s (5.733 KiB/s)|

With this S2 is accepted. In the PS4 they work, with the backend of Playden:
- TLS and WebSocket to CM;
- PICS and content servers;
- deciphering, decompression and verification of the chunks.

S3 and S4 are left with USB writing (ROOT mode) and actual storage.
