<a id="w174-red-para-programas-windows-fase-8-borrador"></a>


# W174: programme network Windows (phase 8, draft)

[English](HARDWARE_W174-red-borrador.md) | [Español](HARDWARE_W174-red-borrador-es.md)

Draft of the network side session, to join `HARDWARE_W174.md`. None of this was built or tested on the console: the bottom comes from reading the code and compiling each piece separately.

<a id="qué-estaba-mal-leído-en-el-código"></a>


## What was wrong (read in the code)

1. **DNS:** the `config.h` of Orbis does not define `HAVE_GETADDRINFO`. The `unix_getaddrinfo` of ws2_32 returned error always ("getaddrinfo () not found during build time"). In addition, the libc of SDK (musl) reads `/etc/resolv.conf`, that an app of PS4 does not have, and asks 127.0.0.1.
2. **Non-blocking Sockets:** wineserver uses `fcntl(F_SETFL, O_NONBLOCK)` on each socket (`server/sock.c`). W013 measured that the console rejects it in a socket. With the blocking socket, `connect` and `accept` would block the server, which runs in the same process.
3. **`sendmsg` / `recvmsg`:** `pw_wine_sendmsg/recvmsg` they were written for the socketpair of the server. They rejected an address (`sendto` / `recvfrom` from UDP) and any shipping flag.
4. **Numbers `MSG_*`:** those of SDK are those of Linux And the kernel reads those of FreeBSD. For example, `MSG_DONTWAIT` (0x40) is `MSG_WAITALL` for the kernel, and `MSG_TRUNC` returns as 0x10.
5. **Adapters:** `nsi.dll` asks for all network tables at `\\.\Nsi` (nsiproxy.sys, in winedevice.exe, which does not run in the model of a process. So `GetAdaptersAddresses`, `GetAdaptersInfo` and ipconfig failed.
6. **dnsapi:** does not have Unix side without libresolv. `DnsQuery` and the DNS server list failed.

<a id="cambio"></a>


## Change

|File|What are you doing?|
|---|---|
|`platform/ps4/pw_ws2_32_libc.c` (new)|`getaddrinfo`, `getnameinfo`, `gethostbyname`, `gethostbyaddr` and `gethostname` for the Unix side of ws2_32. It was adapted from prospero-win (`wine/ps5/pw_ws2_32_libc.c`, see `THIRD_PARTY.md`). Solve the numerical, loopback, `localhost` and `PS4` addresses right here. The point names go to `sceNetResolverStartNtoa` (5 s per attempt, 3 attempts) and, if necessary, to `Ntoa6`. A single label name gives `EAI_NONAME`. A name not found remains 5 s in negative cache. The services accepted are a number or name of a short list (`http`, `https`, `ftp`...); any other gives `EAI_SERVICE` and a line `PWNET`. There's no reverse resolution.|
| `tools/build-unixlibs-ps4.py` |Compile ws2_32 with `-DHAVE_GETADDRINFO` and with those functions instead of those of musl (`-Dgetaddrinfo=pw_ws2_getaddrinfo`...). Add the library `netctl`.|
| `platform/ps4/pw_wine_netctl.c` (new), `pw_netctl_info.h` (new) |**dnsapi.so:** DNS servers since `sceNetCtlGetInfo` (primary and secondary, only IPv4). `query` is a real DNS consultation by UDP to these servers (2 s, 2 attempts each). Return the answer as it comes. There is no TCP: a truncated response is returned with your TC bit and a trace. **nsi.so:** a call reading IP, mask, gateway, DNS, MAC, MTU and type of connection. libSceNetCtl is charged in running time, as the mouse in `hw_pad.c`.|
| `platform/ps4/pw_wine_unixlibs.c` |Entries `dnsapi.so` and `nsi.so`.|
| `platform/ps4/pw_wine_net.c` / `.h` |`msg_name` towards the kernel as it comes. Translation of the `MSG_*` in both senses; an untranslated flag gives `ENOTSUP` with a trace. `EAGAIN` no longer spends traces. `pw_wine_socket_nonblock()` test `fcntl` and then `sceNetSetsockopt(SO_NBIO)`, and leave a line `PWNET nonblock` (the first time, or every time it fails).|
| `tools/build-wine-delete-server.py` |In addition to `fd.c`, check `server/sock.c`: your three `fcntl(O_NONBLOCK)` go on to call `pw_wine_socket_nonblock`, and the `recv(MSG_DONTWAIT)` use the kernel number.|
|`tools/build-nsi-hw.py` (new)|Compile nsi.dll of 64 and 32 bits. If you cannot open `\\.\Nsi`, you can set the tables from nsi.so: loopback (1) interface and wiring or Wi-Fi (2) interface, IPv4 addresses, routes (loopback, subnet, default route) and in IPv6 only `::1`. Link speed and counters remain at 0 because they are not known. Other tables (TCP/UDP, statistics, neighbors, change notifications) return `ERROR_NOT_SUPPORTED` with a line `PWNSI`.|
|`fixtures/win32/nettest.c` (new)|`nettest64.exe` and `nettest32.exe`. See below.|
| `tools/build-wine-hardware.py` |Compile the two fixtures in `C:\orbis` and install nsi.dll: the 64 bit in `lib/wine/x86_64-windows` and `system32`, 32 bit in `lib/wine/i386-windows` and `syswow64`. It goes after the program block, to replace the nsi.dll fixed that brings its closure.|
| `tools/stage-wine-programs.py` |`ipconfig` and `ping` in system32.|

## Fixture `nettest64.exe` / `nettest32.exe`

Use: `nettest64.exe [nombre] [ipv4]`. By default the name is `example.com`. The IPv4 is only used if the name does not solve. Each execution adds to `C:\orbis\net-result.txt` a block that starts with `run arch=64|32 …` and ends with `end`. Steps, each with `ok=` and the Winsock error code or Win32:

- `wsastartup`
- `dns`: `getaddrinfo(nombre, "80")`, with the answers and the ms.
- `tcp`: `connect` blocker to the first IPv4, with the local address.
- `http`: send `HEAD / HTTP/1.0` and receive the state line (`status=HTTP/1.x …`), with 10 waiting.
- `nbio`: the same `connect` in a non-blocking socket, completed with `select`.
- `loopback`: bind/listen in 127.0.0.1, connect, accept and a byte in each sense.
- `adapters`: `GetAdaptersAddresses`, with name, type, status, MAC, MTU, addresses, gateway and DNS.
- `udp`: DNS question for UDP (`sendto` / `recvfrom`, 5 s) to the first DNS of the adapters, or 8.8.8.8 if there are none.

A step that can't run because a previous one failed says it (`skipped=…`) and it's left with `ok=0`.

**Approval criterion:** in the two blocks (64 and 32), `dns ok=1`, `tcp ok=1` and `http ok=1` with an HTTP state line.

<a id="construcción-orden"></a>


## Construction (order)

1. `python3 tools/build-unixlibs-ps4.py`
2. `python3 tools/build-wine-delete-server.py`
3. `python3 tools/build-nsi-hw.py`
4. `python3 tools/stage-wine-programs.py` (only if they enter ping/ipconfig)
5. `python3 tools/link-wine-boot.py`
6. `python3 tools/build-wine-hardware.py`

There is no need to remodel `build/wine-boot` or `build/wine-server`: changes enter by separate objects, such as `virtual.o` or `fd.o`.

<a id="qué-buscar-en-el-log"></a>


## What to look for in the log

- `PWNET resolve name=example.com family=… found=1 rc4=0x00000000`: the solder of the console responded.
- `PWNET nonblock fd=… fcntl_errno=… so_nbio=0x00000000`: the socket was not blocked by SO_NBIO. If `so_nbio` is negative, the sockets are still blocking.
- `PWNET netctl module=… init_sym=0 get_sym=0` and `PWNET netctl init=… ip=…`: libSceNetCtl was loaded and given the configuration.
- `PWNSI …`: a table that asked for some program and is not there.
- `PWBOOT sendmsg_failed` / `recvmsg_failed stage=flag|kernel`: a rejected shipment or reception.

<a id="no-verificado--riesgos"></a>


## Not verified / risks

- That `SO_NBIO` (0x1200, level 0xffff) works from the app. The value comes out of shadPS4. If it doesn't work, `tcp` can pass the same (locking connect), but `nbio` fails and the server is blocked during the connect.
- That `libSceNetCtl.sprx` load with `sceKernelLoadStartModule` without `sceSysmoduleLoadModuleInternal(NETCTL)`. If you don't load, dnsapi adapters and DNS return trace error, and `dns` / `tcp` / `http` do not depend on that.
- The SDK (`IP_TOS`, `IP_TTL`, `IP_MULTICAST_*`, `IPV6_V6ONLY` IP level options numbers they are also of Linux and they were not translated. Basic TCP and UDP do not use them; multicast and TTL are still pending.
- ICMP: `IcmpCreateFile` of iphlpapi opens `\\.\Nsi` directly, and `IcmpSendEcho` goes to nsiproxy (`IOCTL_NSIPROXY_WINE_ICMP_ECHO`). Without nsiproxy, `ping` ends with error when creating the ICMP handle. It was not implemented: iphlpapi should be reviewed to use an ICMP socket, and it is not known if the app can open one.
- `ipconfig` should show the console IP if nsi.dll and libSceNetCtl respond.
- `nslookup` does not exist in this Wine commitment.
- IPv6: only `::1`. The IPv6 addresses of the console are not read.

<a id="prueba-física"></a>


## Physical test

Pending.
