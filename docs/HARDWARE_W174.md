<a id="w174-memoria-flexible-devuelta-al-liberar-fase-6-winecfg-completo-fase-7-y-red-para-programas-windows-fase-8"></a>


# W174: flexible memory returned at release (phase 6), complete winecfg (phase 7) and network for programs Windows (phase 8)

[English](HARDWARE_W174.md) | [Español](HARDWARE_W174-es.md)

APP_VER 02.73. Base W173. The result of W173 is in `docs/HARDWARE_W173.md`.

<a id="memoria-flexible"></a>

## Flexible memory

`tools/build-audio-ps4.py`, `virtual.c` of ntdll, only in Orbis:
- `unmap_area` (release into a reserved area) and `decommit_pages` no longer make just a `mmap` `PROT_NONE` of libc over the range.
  - First they unmap with `sceKernelMunmap`, which returns the flexible memory.
  - Then they rebook with `pw_wine_anon_tryfixed` (`sceKernelReserveVirtualRange`), the reservation that `pw_wine_memory_protect` can compromise.
  - If something fails, the map of Wine is used as before and is left `PWVM rereserve … falling back`.
- `PWVM commit` adds `flexible_free`, the free flexible memory at that time, to see if the budget drops during the race.
- The consultations read the byte de lags well.

It is expected that SuperMarioKart will end the race without `PWVM fault`, with `flexible_free` stable.

<a id="red-para-programas-windows-fase-8-sesión-de-red"></a>


## Programme network Windows (phase 8, network session)

<a id="qué-estaba-mal-leído-en-el-código"></a>


### What was wrong (read in the code)

1. **DNS:** the `config.h` of Orbis does not define `HAVE_GETADDRINFO`. The `unix_getaddrinfo` of ws2_32 returned error always ("getaddrinfo () not found during build time"). In addition, the libc of SDK (musl) reads `/etc/resolv.conf`, that an app of PS4 does not have, and asks 127.0.0.1.
2. **Non-blocking Sockets:** wineserver uses `fcntl(F_SETFL, O_NONBLOCK)` on each socket (`server/sock.c`). W013 measured that the console rejects it in a socket. With the blocking socket, `connect` and `accept` would block the server, which runs in the same process.
3. **`sendmsg` / `recvmsg`:** `pw_wine_sendmsg/recvmsg` they were written for the socketpair of the server. They rejected an address (`sendto` / `recvfrom` from UDP) and any shipping flag.
4. **Numbers `MSG_*`:** those of SDK are those of Linux And the kernel reads those of FreeBSD. For example, `MSG_DONTWAIT` (0x40) is `MSG_WAITALL` for the kernel, and `MSG_TRUNC` returns as 0x10.
5. **Adapters:** `nsi.dll` asks for all network tables at `\\.\Nsi` (nsiproxy.sys, in winedevice.exe, which does not run in the model of a process. So `GetAdaptersAddresses`, `GetAdaptersInfo` and ipconfig failed.
6. **dnsapi:** does not have Unix side without libresolv. `DnsQuery` and the DNS server list failed.

<a id="cambio"></a>


### Change

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

### Fixture `nettest64.exe` / `nettest32.exe`

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


### Construction (order)

1. `python3 tools/build-unixlibs-ps4.py`
2. `python3 tools/build-wine-delete-server.py`
3. `python3 tools/build-nsi-hw.py`
4. `python3 tools/stage-wine-programs.py` (only if they enter ping/ipconfig)
5. `python3 tools/link-wine-boot.py`
6. `python3 tools/build-wine-hardware.py`

There is no need to remodel `build/wine-boot` or `build/wine-server`: changes enter by separate objects, such as `virtual.o` or `fd.o`.

<a id="qué-buscar-en-el-log"></a>


### What to look for in the log

- `PWNET resolve name=example.com family=… found=1 rc4=0x00000000`: the solder of the console responded.
- `PWNET nonblock fd=… fcntl_errno=… so_nbio=0x00000000`: the socket was not blocked by SO_NBIO. If `so_nbio` is negative, the sockets are still blocking.
- `PWNET netctl module=… init_sym=0 get_sym=0` and `PWNET netctl init=… ip=…`: libSceNetCtl was loaded and given the configuration.
- `PWNSI …`: a table that asked for some program and is not there.
- `PWBOOT sendmsg_failed` / `recvmsg_failed stage=flag|kernel`: a rejected shipment or reception.

<a id="no-verificado--riesgos"></a>


### Not verified / risks

- That `SO_NBIO` (0x1200, level 0xffff) works from the app. The value comes out of shadPS4. If it doesn't work, `tcp` can pass the same (locking connect), but `nbio` fails and the server is blocked during the connect.
- That `libSceNetCtl.sprx` load with `sceKernelLoadStartModule` without `sceSysmoduleLoadModuleInternal(NETCTL)`. If you don't load, dnsapi adapters and DNS return trace error, and `dns` / `tcp` / `http` do not depend on that.
- The SDK (`IP_TOS`, `IP_TTL`, `IP_MULTICAST_*`, `IPV6_V6ONLY` IP level options numbers they are also of Linux and they were not translated. Basic TCP and UDP do not use them; multicast and TTL are still pending.
- ICMP: `IcmpCreateFile` of iphlpapi opens `\\.\Nsi` directly, and `IcmpSendEcho` goes to nsiproxy (`IOCTL_NSIPROXY_WINE_ICMP_ECHO`). Without nsiproxy, `ping` ends with error when creating the ICMP handle. It was not implemented: iphlpapi should be reviewed to use an ICMP socket, and it is not known if the app can open one.
- `ipconfig` should show the console IP if nsi.dll and libSceNetCtl respond.
- `nslookup` does not exist in this Wine commitment.
- IPv6: only `::1`. The IPv6 addresses of the console are not read.

<a id="winecfg-completo-common-controls-v6-y-códecs-de-audio-fase-7-sesión-de-accesos-directos"></a>


## complete winecfg: common controls v6 and audio codecs (phase 7, direct access session)

<a id="problemas-de-w173"></a>


### Problems of W173

Reporte: `reports/wine-hardware-w173/physical/20261103T193724Z`.

- **The About tab closed winecfg.**
  - The page has a control `SysLink`. In the Wine set, comctl32 is divided: `dlls/comctl32` is v5 and does not record `SysLink`, which exists only in `dlls/comctl32_v6`.
  - winecfg asks common controls 6.0 in his manifest, but the sealed prefix does not have that assembly in `winsxs` (only gidibus) and `comctl32_v6.dll` was not in the runtime.
  - With v5 the page cannot be created and the property sheet returns: winecfg ended with status 0, without any warning in the log (thread 0040).
- **"Test sound" no sonaba.**
  - winecfg calls `PlaySound` asynchronous, which returns TRUE before playing; That's why there was no mistake.
  - The test sound is IMA ADPCM (format 0x11, mono, 44,1 kHz) and winmm need the ACM codec `imaadp32.acm` to decode it. `system.ini [drivers32]` declares it, but the file was gone.
  - The two `c0000135` of the log are `msacm32.drv` (wave mapper) and `midimap.dll` (MIDI mapper), which winmm installs by name (`dlls/winmm/lolvldrv.c`).
  - The audio device opened well (`PWAUDIO open ... failed=00000000`).

<a id="cambios"></a>


### Changes

- `tools/stage-wine-extras.py` (new) Of a tree of Wine fixed, without patches, for x86_64 and i386:
  - `comctl32_v6.dll`, `imaadp32.acm`, `msadp32.acm`, `msg711.acm`, `msacm32.drv` and `midimap.dll`;
  - the assembly `Microsoft.Windows.Common-Controls` 6.0.2600.2982 as installed by `setupapi` of Wine (`fakedll.c`: `winsxs\{amd64,x86}_microsoft.windows.common-controls_6595b64144ccf1df_6.0.2600.2982_none_deadbeef\comctl32.dll` and its manifest in `winsxs\manifests`, with `processorArchitecture` completed.
  - There are out `msgsm32.acm` and `l3codeca.acm`, which need Unix bookstores (libgsm, mpg123).
- `tools/build-wine-hardware.py`:
  - copy the modules to the builtin folder of each architecture and to `system32` / `syswow64`, except `comctl32_v6.dll`, which the loader seeks by that name only in the builtin folder;
  - copy the assembly to `winsxs`.
- All the imports of these modules, in the two architectures, were already in the prefix of W173.



<a id="prueba"></a>


### Test

1. winecfg → tab About:
   - the page is expected with the link to winehq.org;
   - in the run log, `comctl32.dll` loaded from `winsxs\amd64_microsoft.windows.common-controls_...` (`trace+loaddll`.
2. winecfg → Audio → Test sound: test sound is expected. In the log, the `c0000135` of `msacm32.drv` and `midimap.dll` do not have to appear.
3. Programme adjustment (due from W172):
   - in Applications, add `d3d11test32.exe`, and in Libraries put `dxgi` = builtin;
   - close the app and open it again: the adjustment has to follow, and `d3d11test32.exe` has to fail with `dxgi` of Wine.
4. Return: desktop, Start menu, WFM and Notepad. The programs that ask common controls v6 now receive it, and the controls can be seen to be different.

Risks:
- comctl32 v6 changes the appearance and behaviour of controls in the manifest v6 programs. Explorer use v5 and do not change.
- If a program reproduces MP3 or GSM by ACM, it still can't do it: the codecs that do it were left out of this change.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w174/physical/20261103T200009Z/`. User response: "SMK closed." `net-result.txt` is copied in `build/w174-net-result.txt`.

**SuperMarioKart:**
- Same failure (`PWVM fault addr=0x1f66000c`).
- `flexible_free` answers the question: during the race it ranges between ~ 80 and ~ 170 MB, so the memory is returned.
- In the end the game compromises 25 blocks of 3 MiB followed without release, and the last one is committed to `flexible_free=1048576`.
- It is not a memory loss: the flexible memory budget (~ 400 MB) is not enough. There was no `PWVM rereserve … falling back`.

**Network** (phase 8, first test):

| Paso |64 bits (guest)| 32 bits |
|---|---|---|
|dns|failure (11001): the guest received as an argument the line of explorer commands (`/desktop=shell,1280x720`)|OK, `example.com` → 104.20.23.154, 254 ms|
|tcp|does not run (without address)|OK, 22 ms|
| http |Don't run.|`recv` remains pending 10 s (997)|
|nbio|Don't run.|Okay.|
| loopback |Okay.|Okay.|
| adapters | ok: 192.168.68.104/22, gateway .1, DNS 62.210.38.117, MAC real |`c0000005` failure: thunk WoW64 of `nsi.so` (`handle_syscall_fault` in `0x448086`, reading 0x8)|
|udp| `recvfrom` 997 | `recvfrom` 997 |

`libSceNetCtl` load and respond (`PWNET netctl init=0x00000000 … ip=192.168.68.104`). The arrangements are going to W176.

**winecfg:** according to the user, the About and Test Sound tab works. Common controls v6 and ACM codecs do their part.
