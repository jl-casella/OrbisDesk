<a id="w176-red-arreglos-tras-w174-fase-8-borrador"></a>


# W176: network, arrangements after W174 (phase 8, draft)

[English](HARDWARE_W176-red-borrador.md) | [Español](HARDWARE_W176-red-borrador-es.md)

Draft of the network side session, to join `HARDWARE_W176.md`. Base: network results of W174 (`build/w174-net-result.txt`, `reports/wine-hardware-w174/physical/20261103T200009Z/`, run- 0001 = explorer + nettest64 as guest, run- 0002 = nettest32). The changes below were compiled separately; They weren't tested on the console.

<a id="resultado-de-w174"></a>


## W174 result

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

## Causes

1. **`recv` / `recvfrom` never ends.** With a waiting reading, `sock_get_poll_events` (`server/sock.c`) order `POLLIN | POLLPRI`. `pw_wine_poll` rejected any event out of IN/OUT with `ENOTSUP`, without trace. Thus the entire waiting of the server failed and no descriptor received events until the waiting time of the async was over.
   - `connect` worked because he only asks `POLLOUT`.
   - loopback worked because the data was already when it was called `recv`.
   - It remains to be seen in W176 why the time-expired reading returned 997 and not 10060 (`WSAETIMEDOUT`). It can be the effect of the same failure, because the server loop was spinning without waiting.
2. **`GetAdaptersAddresses` of 32 bit, `c0000005`.**
   - The failure is in `__wine_unix_call_dispatcher`, `call *(%r10,%rdx,8)`, with handle 0 and code 1 (`get_serverlist` de dnsapi).
   - The dnsapi.dll of 32 bits was charged from `syswow64`, not from `lib/wine/i386-windows`. ntdll gives you your Unix side only in the second case, as it happened with ws2_32 in W119/W120. So dnsapi.dll it recorded "No libresolv support," and the first `DnsQueryConfig` iphlpapi called with no handle.
3. **Guest name of 64 bit.** The guest received as command line the explorer (`/desktop=shell,1280x720`). It's the guest model, not the network, and it's left for the main session. The fixture is now dodging it.

<a id="cambio-w176"></a>


## Change (W176)

|File|What are you doing?|
|---|---|
| `platform/ps4/pw_wine_net.c` |`pw_wine_poll` accepts `POLLPRI`, which is left out of the waiting because sceNetEpoll has no off-band data event and is never reported; is indicated by a line `PWNET poll_pri_not_waited`. It also accepts `POLLERR` / `POLLHUP` on request. Any other event continues to give `ENOTSUP`, now with a line `PWNET poll_events_unsupported`.|
| `tools/stage-wine-i386.py` |`dnsapi` among the objectives: dnsapi.dll of 32 bit also goes to `lib/wine/i386-windows`, as ws2_32.|
| `fixtures/win32/nettest.c` |Jump the arguments that start with `/`. In `http`, before `recv` does a `select` reading (10 s) and writes `readable ready=… ms=…`, So a failure distinguishes "no data came" from "failed reading."|

<a id="construcción"></a>


## Build

1. `python3 tools/stage-wine-i386.py`
2. `python3 tools/link-wine-boot.py` (`pw_wine_net.c`)
3. `python3 tools/build-wine-hardware.py` (fixture and i386)

The other phase building 8 (unixlibs, delete-server, nsi-hw) does not change.

<a id="qué-se-espera"></a>


## What is expected

- `net-result.txt`, in the two blocks: `dns ok=1`, `tcp ok=1`, `readable ready=1`, `http ok=1 status=HTTP/1.x …`, `udp ok=1`.
- In the 32 bit, `adapters ok=1` with the same data as in the 64.
- A line `PWNET poll_pri_not_waited` on the log.
- `ipconfig` with the console IP. `ping` continues to end with error (ICMP goes to nsiproxy, see the draft of W174).

<a id="prueba-física"></a>


## Physical test

Pending.
