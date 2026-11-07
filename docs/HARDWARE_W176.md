<a id="w176-memoria-directa-en-cero-fase-6-y-arreglos-de-red-fase-8"></a>


# W176: direct memory in zero (phase 6) and network arrangements (phase 8)

[English](HARDWARE_W176.md) | [Español](HARDWARE_W176-es.md)

APP_VER 02.75. Base W175. The result of W175 is in `docs/HARDWARE_W175.md`.

<a id="memoria-directa-en-cero"></a>


## Direct memory in zero

`tools/build-audio-ps4.py`, `pw_direct_map`:
- The direct memory retains what it had, and Windows delivers the compromised memory to zero. In W175, the `.x` (d3dxof) parser of SuperMarioKart read memory remains when loading the track.
- Now each section is mapped from read/write and set to zero. Then `set_protection` applies the protection requested.

It is expected that SuperMarioKart will load the track, finish the race and leave without `PWVM fault` even the d3dxof error.

<a id="red-arreglos-de-w174-sesión-de-red"></a>


## Network: arrangements of W174 (network session)

<a id="resultado-de-w174"></a>


### W174 result

| Paso |64 bits (guest)| 32 bits |
|---|---|---|
|dns|`error=11001`: the name was `/desktop=shell,1280x720`|ok: 104.20.23.154, 254 ms|
|tcp|did not run (without direction)| ok: 22 ms, local 192.168.68.104 |
| http |He didn't run.|`recv` 997 at 10 s|
|nbio|He didn't run.|Okay.|
| loopback |Okay.|Okay.|
| adapters |ok: Wi-Fi 192.168.68.104/22, gateway. 1, DNS 62.210.38.117, MAC, MTU 1500; loopback 127.0.0.1/8 and: 1| `c0000005` |
|udp| `recvfrom` 997 (a 62.210.38.117) | `recvfrom` 997 (a 8.8.8.8) |

It worked as follows:
- `PWNET nonblock … so_nbio=0x00000000`: sockets are not blocked by SO_NBIO.
- libSceNetCtl loaded by route, with `module=0x36`.
- The console solver responded.

<a id="causas"></a>

### Causes

1. **`recv` / `recvfrom` never ends.** With a waiting reading, `sock_get_poll_events` (`server/sock.c`) order `POLLIN | POLLPRI`. `pw_wine_poll` rejected any event out of IN/OUT with `ENOTSUP`, without trace. Thus the entire waiting of the server failed and no descriptor received events until the waiting time of the async was over.
   - `connect` worked because he only asks `POLLOUT`.
   - loopback worked because the data was already when it was called `recv`.
   - It remains to be seen in W176 why the time-expired reading returned 997 and not 10060 (`WSAETIMEDOUT`). It can be the effect of the same failure, because the server loop was spinning without waiting.
2. **`GetAdaptersAddresses` of 32 bit, `c0000005`.**
   - The failure is in `__wine_unix_call_dispatcher`, `call *(%r10,%rdx,8)`, with handle 0 and code 1 (`get_serverlist` de dnsapi).
   - The dnsapi.dll of 32 bits was charged from `syswow64`, not from `lib/wine/i386-windows`. ntdll gives you your Unix side only in the second case, as it happened with ws2_32 in W119/W120. So dnsapi.dll it recorded "No libresolv support," and the first `DnsQueryConfig` iphlpapi called with no handle.
3. **Guest name of 64 bit.** The guest received as command line the explorer (`/desktop=shell,1280x720`). It's the guest model, not the network, and it's left for the main session. The fixture is now dodging it.

<a id="cambio-w176"></a>


### Change (W176)

|File|What are you doing?|
|---|---|
| `platform/ps4/pw_wine_net.c` |`pw_wine_poll` accepts `POLLPRI`, which is left out of the waiting because sceNetEpoll has no off-band data event and is never reported; is indicated by a line `PWNET poll_pri_not_waited`. It also accepts `POLLERR` / `POLLHUP` on request. Any other event continues to give `ENOTSUP`, now with a line `PWNET poll_events_unsupported`.|
| `tools/stage-wine-i386.py` |`dnsapi` among the objectives: dnsapi.dll of 32 bit also goes to `lib/wine/i386-windows`, as ws2_32.|
| `fixtures/win32/nettest.c` |Jump the arguments that start with `/`. In `http`, before `recv` does a `select` reading (10 s) and writes `readable ready=… ms=…`, So a failure distinguishes "no data came" from "failed reading."|

<a id="construcción"></a>


### Build

1. `python3 tools/stage-wine-i386.py`
2. `python3 tools/link-wine-boot.py` (`pw_wine_net.c`)
3. `python3 tools/build-wine-hardware.py` (fixture and i386)

The other phase building 8 (unixlibs, delete-server, nsi-hw) does not change.

<a id="qué-se-espera"></a>


### What is expected

- `net-result.txt`, in the two blocks: `dns ok=1`, `tcp ok=1`, `readable ready=1`, `http ok=1 status=HTTP/1.x …`, `udp ok=1`.
- In the 32 bit, `adapters ok=1` with the same data as in the 64.
- A line `PWNET poll_pri_not_waited` on the log.
- `ipconfig` with the console IP. `ping` continues to end with error (ICMP goes to nsiproxy, see the draft of W174).

<a id="pendiente-aparte"></a>


### Withdrawal

- A guest of 64 bits linked to `msvcrt.dll` receives as argv the line of scout commands: W057 only fixed `ucrtbase`.
- `nettest` now ignores the arguments that start with `/`. The programs compiled with MSVC use Ugert and do not have the problem.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w176/physical/20261103T205213Z/`. User response: "SMK well." `net-result.txt` is copied in `build/w176-net-result.txt`.

- **SuperMarioKart:** chose character, ran the full race and went out with `status=0x00000000` at 145 s.
  - There was no `PWVM fault` or d3dxof error.
  - Close the end-of-race series of W167 - W175.
- **Network:** the criterion of the 8 phase is met. The two blocks (`arch=64` and `arch=32`, `example.com`) give:

| Paso | 64 bits | 32 bits |
|---|---|---|
|dns|Okay, 172.66.147.243, 240 ms|OK, 238 ms|
|tcp|OK, 22 ms|OK, 25 ms|
| http | ok, `HTTP/1.1 200 OK`, 315 bytes | ok, igual |
|nbio|Okay.|Okay.|
| loopback |Okay.|Okay.|
| adapters |ok: 192.168.68.104/22, gateway. 1, DNS 62.210.38.117, real MAC; loopback `::1` and `127.0.0.1`| ok, igual |
|udp|ok: DNS consultation at 62.210.38.117, 2 answers|Okay.|

- `ipconfig` not reported.
