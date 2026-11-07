<a id="w188-números-de-opciones-de-socket-del-kernel-fases-8-y-9"></a>


# W188: number of kernel socket options (phases 8 and 9)

[English](HARDWARE_W188.md) | [Español](HARDWARE_W188-es.md)

APP_VER 02.87. Base W187. The result of W187 is in `docs/HARDWARE_W187.md`.

<a id="opciones-de-socket"></a>


## Socket options

**The problem** (found by the browser session):
- The `netinet/` headers of the SDK use the Linux numbers for the TCP, IP and IPv6 level options, and the console kernel reads those of FreeBSD. The socket level (`SOL_SOCKET` 0xffff) coincides.
- `SIO_KEEPALIVE_VALS` of Wine puts `TCP_KEEPIDLE` (4, which for FreeBSD is `TCP_NOPUSH`. The kernel retained the short segments, and the TLS greeting and the HTTP orders of Pale Moon did not come out. In W186 the names resolved, but the pages were blank and without error.
- The network tests of W176 passed because a simple `HEAD /` does not activate keep-alive.

**The change:**
- `platform/ps4/pw_wine_net.c`: `__wrap_setsockopt` and `__wrap_getsockopt` translate the options:
  - TCP: `TCP_NODELAY` and `TCP_MAXSEG` equal; `TCP_KEEPIDLE` / `KEEPINTVL` / `KEEPCNT` to 0x100/0x200/0x400.
  - IP: `TOS`, `TTL`, `HDRINCL`, `OPTIONS`, `MULTICAST_IF/TTL/LOOP`, `ADD/DROP_MEMBERSHIP`, `RECVTTL` and `RECVTOS`.
  - IPv6: `UNICAST_HOPS`, `MULTICAST_IF/HOPS/LOOP`, `JOIN/LEAVE_GROUP` and `V6ONLY`.
  - An option with no equivalent in FreeBSD (`TCP_CORK`, `IP_PKTINFO`, `IP_MTU_DISCOVER`...) gives `ENOPROTOOPT` with `PWNET setsockopt|getsockopt … unsupported`, instead of falling on another option.
- `tools/build-wine-hardware.py`: the final link passes `--wrap=setsockopt --wrap=getsockopt`. This is how all the caller comes, including the ntdll socket code, compiled long ago.
- The wrappers are in a separate file, `platform/ps4/pw_wine_sockopt.c`, which only enters the final link. The first attempt had them in `pw_wine_net.c` with `__real_*` weak, but `link-wine-boot.py` compiles that file also in `bootstrap.elf`, and `create-fself` rejected the unsolved symbol (`missing library for symbol (__real_setsockopt)`).
- You're a complete unwarning.

<a id="pendiente-aleatoriedad"></a>


## Pending: randomness

`get_random()` of ntdll test `getrandom()`, stub of SDK which gives ENOSYS, and then `/dev/urandom`. It is not known whether the sandbox lets open `/dev/urandom`; If not, Wine just tell and return the buffer without changing, and NSS would plant its generator with fixed bytes. The addition of a trace or a source of the console requires the recombination of the object of ntdll that W103 already replaces; It's for another building.

<a id="pale-moon-keep-alive-apagado-fase-9-sesión-del-navegador"></a>


## Pale Moon: keep-live off (phase 9, browser session)

<a id="qué-pasó-en-w186"></a>


### What happened in W186

Reporte: `reports/wine-hardware-w186/physical/20261104T002752Z/`.

- **What works:**
  - Pale Moon He's not hanging up anymore..
  - The Enter (`code=13`) arrives and the name is resolved (`PWNET resolve name=duckduckgo.com family=2 found=1`; `family=2` is only IPv4, by the preference of W185).
  - The local page is complete: `es5-ok`, `es2020-ok`, `canvas-ok`.
- **What does not:** remote sites are blank or make a mistake.
- **In the log, after resolution:** there is no network error. There are only repeated attempts to stop two threads (`thread_signal unavailable thread=0070 sig=10`, and the same with `00ac`). It matches the Pale Moon hanging monitor by taking samples of a stranded thread.

<a id="causa-probable"></a>


### Probable cause

- **The TCP options numbers:** the `netinet/tcp.h` of the SDK brings the numbers of Linux (`TCP_KEEPIDLE=4`, `TCP_KEEPINTVL=5`, `TCP_KEEPCNT=6`), but the console kernel is FreeBSD. There `IPPROTO_TCP` 4 is `TCP_NOPUSH`, and keepalive uses `0x100`, `0x200` and `0x400`. The socket level options (`SOL_SOCKET=0xffff`, `SO_KEEPALIVE=8`) do match FreeBSD.
- **What does Wine:** when a program asks to keep (`WSAIoctl(SIO_KEEPALIVE_VALS)`), Wine (`ntdll/unix/socket.c`, `IOCTL_AFD_WINE_KEEPALIVE_VALS`) does `setsockopt(IPPROTO_TCP, TCP_KEEPIDLE, segundos)`. On the console that lights `TCP_NOPUSH`.
- **The effect:** the kernel retains what is written until a full segment is assembled or the socket is closed. The start of a connection TLS (ClientHello) or a short HTTP order never comes out, so the page is blank and ends for time.
- **Pale Moon order keepalive** in its default connections (`network.tcp.keepalive.enabled`).
- **Why the phase 8 did not see it:** `nettest` (phase 8) He doesn't want to keep, and his `HEAD /` worked.

<a id="cambio-parte-del-navegador"></a>


### Change (browser part)

`fixtures/browser/palemoon-user.js`: `network.tcp.keepalive.enabled=false`. The preference is in `xul.dll` of Pale Moon 35. With this, Pale Moon does not call `SIO_KEEPALIVE_VALS`. It remains even if the translation of `pw_wine_net.c` fixes the cause, as second protection.

<a id="construcción"></a>


### Build

`python3 tools/build-wine-hardware.py` (copy the new `user.js`), along with changes in the main session.

<a id="prueba-física"></a>


### Physical test

1. Open Pale Moon and enter `https://example.com/`, `https://duckduckgo.com/` and a site `http://`.
2. Note, for each, if you load and in how long or so.
3. Get down `C:\orbis\palemoon-net.log-main.*`. You have to show the connection, the TLS exchange and the HTTP response.
4. **If you do not yet load:** look in that log where you cut (connection, TLS or HTTP) and in the log of the Runs the lines `PWNET` of the socket options.

<a id="no-verificado-antes-de-la-prueba"></a>


### Not verified (before test)

- The cause was degenerated by reading the code and the headers. The network log of W187 was empty.
- Later note: the W188 (below) test confirms the arrangement, although it does not separate how much the translation provides and how much the preference.

<a id="prueba-física-1"></a>


## Physical test

Reporte: `reports/wine-hardware-w188/physical/20261104T024404Z/`.

- **Result:** the user replied "Sail." Pale Moon load remote sites for the first time.
- **Name resolution:** `duckduckgo.com`, `improving.duckduckgo.com` and `duck.ai` (`found=1`, IPv4).
- **Options rejected by translation** (one per socket, no visible effect):
  - TCP 7: in Linux is `TCP_SYNCNT`; does not exist in FreeBSD.
  - IP 10: in Linux is `IP_MTU_DISCOVER`. FreeBSD has `IP_DONTFRAG` (67), but it's not the same; it is rejected.
  - IPv6 62: in Linux it is `IPV6_DONTFRAG`, and in FreeBSD it has the same number. It can be passed without translating into a nearby building.
- **The network log of Pale Moon:** `C:\orbis\palemoon-net.log-main.32` continues with 0 bytes, just like in W187. This failure is no longer necessary; you have to check if Pale Moon fails again.
- **Not measured:** loading times and which sites work well or badly; MSHTML HTTPS (WebView) was not tested.
