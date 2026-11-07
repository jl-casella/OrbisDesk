# W176: red, arreglos tras W174 (fase 8, borrador)

[English](HARDWARE_W176-red-borrador.md) | [Español](HARDWARE_W176-red-borrador-es.md)

Borrador de la sesión lateral de red, para unir a `HARDWARE_W176.md`. Base: los resultados de red de W174 (`build/w174-net-result.txt`, `reports/wine-hardware-w174/physical/20261103T200009Z/`, run-0001 = explorer + nettest64 como invitado, run-0002 = nettest32). Los cambios de abajo se compilaron por separado; no se probaron en la consola.

## Resultado de W174

|Paso| 64 bits (invitado) |32 bits|
|---|---|---|
| dns | `error=11001`: el nombre fue `/desktop=shell,1280x720` | ok: 104.20.23.154, 254 ms |
| tcp | no corrió (sin dirección) | Ok.: 22 ms, local 192.168.68.104 |
|http://| no corrió | `recv` 997 a los 10 s |
| nbio | no corrió | ok |
|Loopback| ok | ok |
|adaptadores| ok: Wi-Fi 192.168.68.104/22, gateway .1, DNS 62.210.38.117, MAC, MTU 1500; loopback 127.0.0.1/8 y ::1 | `c0000005` |
| udp | `recvfrom` 997 (a 62.210.38.117) | `recvfrom` 997 (a 8.8.8.8) |

Funcionó lo siguiente:
- `PWNET nonblock … so_nbio=0x00000000`: los sockets quedan no bloqueantes por SO_NBIO.
- libSceNetCtl cargó por ruta, con `module=0x36`.
- El resolvedor de la consola respondió.

## Causas

1. **`recv`/`recvfrom` nunca terminan.** Con una lectura en espera, `sock_get_poll_events` (`server/sock.c`) pide `POLLIN | POLLPRI`. `pw_wine_poll` rechazaba cualquier evento fuera de IN/OUT con `ENOTSUP`, sin traza. Así fallaba la espera entera del servidor y ningún descriptor recibía eventos hasta que vencía el tiempo de espera del async.
   - `connect` funcionó porque sólo pide `POLLOUT`.
   - loopback funcionó porque los datos ya estaban cuando se llamó a `recv`.
   - Queda por ver en W176 por qué la lectura con tiempo vencido devolvió 997 y no 10060 (`WSAETIMEDOUT`). Puede ser efecto del mismo fallo, porque el bucle del servidor giraba sin esperar.
2. **`GetAdaptersAddresses` de 32 bits, `c0000005`.**
   - La falla está en `__wine_unix_call_dispatcher`, `call *(%r10,%rdx,8)`, con handle 0 y código 1 (`get_serverlist` de dnsapi).
   - El dnsapi.dll de 32 bits se cargó desde `syswow64`, no desde `lib/wine/i386-windows`. ntdll le da su Unix side sólo en el segundo caso, como pasó con ws2_32 en W119/W120. Por eso dnsapi.dll registró "No libresolv support", y la primera `DnsQueryConfig` de iphlpapi llamó con handle nulo.
3. **Nombre del invitado de 64 bits.** El invitado recibió como línea de comandos la de explorer (`/desktop=shell,1280x720`). Es del modelo de invitados, no de red, y queda para la sesión principal. El fixture ahora lo esquiva.

## Cambio (W176)

| Archivo | Qué hace |
|---|---|
| `platform/ps4/pw_wine_net.c` | `pw_wine_poll` acepta `POLLPRI`, que queda fuera de la espera porque sceNetEpoll no tiene evento de datos fuera de banda y nunca se reporta; lo indica una línea `PWNET poll_pri_not_waited`. También acepta `POLLERR`/`POLLHUP` en lo pedido. Cualquier otro evento sigue dando `ENOTSUP`, ahora con una línea `PWNET poll_events_unsupported`. |
| `tools/stage-wine-i386.py` | `dnsapi` entre los objetivos: el dnsapi.dll de 32 bits va también a `lib/wine/i386-windows`, como ws2_32. |
| `fixtures/win32/nettest.c` | Salta los argumentos que empiezan con `/`. En `http`, antes de `recv` hace un `select` de lectura (10 s) y escribe `readable ready=… ms=…`, así un fallo distingue "no llegaron datos" de "falló la lectura". |

## Construcción

1. `python3 tools/stage-wine-i386.py`
2. `python3 tools/link-wine-boot.py` (`pw_wine_net.c`)
3. `python3 tools/build-wine-hardware.py` (fixture e i386)

Los demás builders de fase 8 (unixlibs, delete-server, nsi-hw) no cambian.

## Qué se espera

- `net-result.txt`, en los dos bloques: `dns ok=1`, `tcp ok=1`, `readable ready=1`, `http ok=1 status=HTTP/1.x …`, `udp ok=1`.
- En el de 32 bits, `adapters ok=1` con los mismos datos que en el de 64.
- Una línea `PWNET poll_pri_not_waited` en el log.
- `ipconfig` con la IP de la consola. `ping` sigue terminando con error (ICMP va a nsiproxy, ver el borrador de W174).

## Prueba física

Pendiente.
