<a id="s1-https-nativo-para-el-cliente-de-steam-orbs00001"></a>


# S1: HTTPS native to the Steam customer (ORBS00001)

[English](STEAM_S1.md) | [Español](STEAM_S1-es.md)

It is the first phase of the Steam customer. A native probe of PS4, without Wine and without Steam account, checks that the console can make HTTPS on its own with certificate validation.

<a id="qué-es"></a>


## What is it

- **Title:** ORBS00001, "OrbisDesk Steam S1, "version 01.01 (the 01.00 It failed on the console, see below). It is the customer's own title of Steam, other than OrbisDesk (ORBW00002) and replaceable probes (ORBB00001).
- **License:** GPL- 3.0 or later, because the client will re-use code of Playden (`upstream/playden-ps5`, commitment `fb74dbf`). In S1 there is still no code of Playden: the probe is own. The license texts (GPL- 3.0 and Apache - 2.0 from Mbed TLS) go in the package, in `/app0/assets/misc/`.
- **Sources:** `native/steam/steam_probe.c`, `steam_tls.c`/`.h` and `mbedtls_user_config.h`. Builder: `tools/build-steam-probe.py`.
- **Dependencies** (in `.deps/steam/downloads`, verified by SHA- 256 in the builder):
  - Mbed TLS 3.6.6;
  - 2026-09-25 (121 roots).
  - curl, zstd and the LZMA SDK are already downloaded, but S1 does not use them.

<a id="qué-comprueba"></a>


## What's he checking?

Each log line starts with `PWSTEAM`. The log is left in `/data/orbis-win/steam-probe.txt` and also comes out by `sceKernelDebugOutText`.

1. **Clock:** the time of the console. If you are late or advanced, no valid certificate.
2. **Entropy:** `/dev/urandom`, two readings of 32 bytes. None can be all zeros and they have to be different from each other. It is the only source that receives Mbed TLS (`MBEDTLS_ENTROPY_HARDWARE_ALT`). If it fails, the probe does not try TLS and says so.
3. **CA:** reads `/app0/assets/misc/cacert.pem` and counts the loaded roots.
4. **Steam:** `GET https://api.steampowered.com/IContentServerDirectoryService/GetServersForSteamPipe/v1/?cell_id=0`, a public call that does not use account. If:
   - complete handshake without verification marks;
   - the answer is HTTP 200;
   - the answer list at least one server (`"vhost"`).
5. **Expected rejections:** `untrusted-root.badssl.com` has to fail by unreliable root (`0x08`) and `expired.badssl.com` by expired certificate (`0x01`). So you can see that the warehouse and the clock are used, and not only that the handshake is over.
6. **Result:** the last line is `PWSTEAM S1 result=pass` or `result=fail failed=…`, with the names of the steps that failed.

The probe has no screen: it ends only a few seconds later and returns to the menu.

<a id="detalles-de-la-consola"></a>


## Console details

- **Sockets:** are blockers, with `poll` of 15 s before each reading. DNS by `sceNetResolverStartNtoa`, like `platform/ps4/pw_ws2_32_libc.c`. Before the network module is loaded and `sceNetInit`. Only IPv4.
- **Mbed configuration TLS:** without `MBEDTLS_NET_C`, `TIMING_C`, `FS_IO` no PSA storage on disk. `FS_IO` was dragging `getdents`, which no eboot in use matters: the bundle is read with `open` / `read`. The Mbed threads TLS are active, as in Playden.
- **Imports:** the builder requires that the probe only matter what already matters the last `wine.elf` or `hardware.elf`. This version passes that check-up.
- **SIGPIPE:** is ignored, so that a server that closes during a writing does not finish the title.

<a id="resultado-en-la-pc-2026-11-07"></a>


## PC result (2026-11-07)

`python3 tools/build-steam-probe.py --host` compiles the same code for Linux, in `build/steam-probe-host`. In WSL he gave:

- **Steam:** TLS 1.3 (`TLS1-3-CHACHA20-POLY1305-SHA256`), HTTP 200 and 12 servers.
- **untrusted-root:** rejected with `verify_flags=0x08`.
- **atone:** rejected with `0x01`.
- **Result:** `result=pass`.

<a id="paquete"></a>


## Package

- `out/steam-probe-s1/IV0000-ORBS00001_00-ORBISWINSTEAM001.pkg`: 6.619.136 bytes. The SHA-256 is in `out/steam-probe-s1/manifest.json`.
- The builder does not go up anything: the PKG goes up the building session.

<a id="pendiente"></a>


## Pending

<a id="primera-corrida-en-la-consola-0100-2026-11-07-resultfail"></a>


### First run on the console: 01.00, 2026-11-07, `result=fail`

- **What I walked:** loaded the network module, `sceNetInit` gave 0, the clock marked 2026 - 11 -07T11: 06: 20Z, the entropy gave `ok=1` and the DRBG started.
- **What failed:** `ca … roots=0` with "The CRT/CRL/CSR form is invalid. " That's why he never tried HTTPS..
- **probable cause:** the 01.00 dimensioned the reading of the bundle with `fstat`. The `struct stat` of the SDK is that of musl, and the kernel is FreeBSD (W180/W218 They found the same with `statfs`), so `st_size` may not be where the SDK seeks it. With a small size, the buffer does not have the PEM header or the `\0` final. Mbed TLS then takes it as DER, and that's just the mistake he gave.
- **fix, in 01.01:** read to the end of the file without `fstat` and record `ca read bytes=… fstat_rc=… st_size=… head=…`. If the cause is another, that line will show it.

**The 01.01 Runs in the console is missing.** To give S1 as accepted, the `steam-probe.txt` of the PS4 is needed. with `result=pass`.

If you fail:
- `entropy ok=0`: another source of entropy must be sought before following.
- `verify_flags` with `0x200` (future date) or `0x01` in Steam: the console clock is wrong.
- `dns … found=0` or `connect=-1` with `errno`: the problem is network, not TLS.
