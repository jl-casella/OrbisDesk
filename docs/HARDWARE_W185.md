<a id="w185-pale-moon-siempre-en-línea-sin-proxy-del-sistema-ni-ipv6-con-registro-de-red-fase-9"></a>


# W185: Pale Moon always online, without system proxy or IPv6, with network record (phase 9)

[English](HARDWARE_W185.md) | [Español](HARDWARE_W185-es.md)

APP_VER 02.84. Base W184. The result of W184 is in `docs/HARDWARE_W184.md`. The browser session prepared it. The `palemoon-user.js` that was published is the end (sha256 `e37725f4…`), with `network.proxy.type=0` and `network.notify.changed=false`.

<a id="qué-pasó-en-w184"></a>


## What happened in W184

Pale Moon opens as a separate title, but according to the user does not navigate: "I wrote google.com and youtube.com, and I searched google on the punk duck go bar and nothing, by making enter or click on the go icon, did not navigate." No error page, no load, no unconnected notice.

Log of the Runs: `reports/wine-hardware-w184/physical/20261103T234412Z/run-0002.log`. The `…T234342Z` directory has the same records.

1. **In the log there is no navigation order:**
   - The pitcher records each key and each click before it reaches Wine (`PWBOOT input_event`). In the Runs of Pale Moon the text typed is `WWW.GOGLE.CO` (with the setbacks). Then there is no Enter (code 13), no click, no pad button; Just the mouse wheel.
   - The keyboard Enter does work on the console: run- 0001 (the desktop) records the code 13.
   - In this run there is also no search for DuckDuckGo nor youtube.com (not typed D, U, K, Y, T or B). What the user describes happened in another session, which this report does not have.
2. **There was no resolution of names.** The console resolver (`platform/ps4/pw_ws2_32_libc.c`) records each search (`PWNET resolve name=… found=…`; `nettest` shows them since W176, and in this run there is none. It matches the point 1: Pale Moon never asked for a page.
3. **Network notifications do not block:**
   - The Pale Moon link monitor uses `NotifyIpInterfaceChange`, which in Wine is a stub and returns immediately.
   - `NotifyAddrChange` goes through `NsiRequestChangeNotification`. Without `nsiproxy.sys`, the `nsi.dll` of the console returns `ERROR_NOT_SUPPORTED` immediately (`PWNSI change notifications are not provided`). Neither of us can wait.
4. **Other log lines:**
   - **`PWNSI table 11 …`:** the table 11 of the module `NPI_MS_IPV4_MODULEID` is the one of neighbors (ARP, `NSI_IP_NEIGHBOUR_TABLE`). Pale Moon uses it only to calculate a network identifier, not to decide if there is a link.
   - **The link:** Pale Moon it decides with `GetAdaptersAddresses`, and W176 `nettest64` showed the Wi-Fi interface on and with IPv4.
   - **Unrecorded COM classes:** `{43fb1553-…}` (Tablet PC Ink) and `{56fdf344-…}` (`TaskbarList`). They have nothing to do with the network.
   - **Proxy:** WinINet is loaded and read your global options (`query_global_option Unknown dwOption 10`). It is the "system proxy," the default value of Pale Moon.
   - **When closing:** `RtlpWaitForCriticalSection … blocked by 0050`. The thread `0050` He doesn't register anything. Unexplained.

<a id="cambio"></a>


## Change

Just `fixtures/browser/palemoon-user.js`. Shared builders do not change: `build-wine-hardware.py` already copy the `user.js`.

Preferences rule out what might stop a navigation when requested. They're all in `xul.dll` of Pale Moon 35:

|Preference|What for?|
|---|---|
| `network.manage-offline-status=false`, `network.offline-mirrors-connectivity=false` |Pale Moon does not go to "unconnected" if your link review fails with the console tables.|
| `network.captive-portal-service.enabled=false` |Without the request to notice the captive portal when starting.|
| `network.dns.disableIPv6=true` |Only IPv4. When IPv4 finds nothing, the console resolver also tests IPv6, with 5 s per attempt, and the console has no IPv6 route.|
| `network.proxy.type=0` |No proxy. Do not read the proxy settings of Windows through WinINet.|
| `network.notify.changed=false` |It does not react to notices of network change, which do not exist on the console.|

**Diagnosis, temporary:**
- The network log of its own Pale Moon goes to `C:\orbis\palemoon-net.log` (`logging.config.*`, one line at a time, erased in each boot).
- Modules: `nsIOService`, `nsNotifyAddr`, `nsHostResolver`, `nsSocketTransport` and `nsHttp`. If any of those names don't exist, you don't know.
- We have to get him out when the navigation works.

**No more trace is needed for now.** The `PWNET resolve` lines already show each name search and the `input_event` each key. If no `PWNET resolve` appears with a real order, it is only there that it is suitable `+winsock` for the title of Pale Moon (in the pitcher, file of the main session).

<a id="construcción"></a>


## Build

1. `python3 tools/build-wine-hardware.py` (copy the new `user.js`)

<a id="prueba-física"></a>


## Physical test

1. Open Pale Moon, click the address bar and write `example.com`.
2. Get into the keyboard. If there is no keyboard: Triangle on the pad, that commands Enter, or click (Cross) on the go arrow.
3. Note what you see: page, error (with your text) or wait.
4. **What to look for in the log of the Runs:**
   - a line `input_event source=keyboard … code=13` (or `source=pad`) after the text: confirms that the order arrived;
   - `PWNET resolve name=example.com …`: confirms that Pale Moon solved the name.
5. Down `C:\orbis\palemoon-net.log` by FTP.

If the Enter and resolution arrive and still does not load, the network log shows where it is cut (connection, TLS or HTTP).

<a id="no-verificado"></a>


## Not verified

- Nothing was tested on the console.
- It is not known what happened in the session that the user describes: it is not in this report.
- The hanging when closed (thread `0050`) is not explained.

<a id="prueba-física-1"></a>


## Physical test

Report: `reports/wine-hardware-w185/physical/20261104T000907Z/`. According to the user, "it was frozen Pale Moon now."

- Not created `C:\orbis\palemoon-net.log`.
- `run-0002.log`:
  - `PWBOOT thread_signal unavailable thread=0070 sig=10` (SIGUSR1, the server order to stop a thread and read its context);
  - a click;
  - `RtlpWaitForCriticalSection … wait timed out in thread 0024, blocked by 0050`. It's the same lock as in W184 when you close.
- **Cause:** the thread that asked for the context of another (the Pale Moon hang monitor) waits forever, because the signal never arrives (W064: without signals directed to a thread), and has taken a lock that the thread of the interface needs. I'll fix it in W186.
