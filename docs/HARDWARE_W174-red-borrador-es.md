# W174: red para programas Windows (fase 8, borrador)

[English](HARDWARE_W174-red-borrador.md) | [Español](HARDWARE_W174-red-borrador-es.md)

Borrador de la sesión lateral de red, para unir a `HARDWARE_W174.md`. Nada de esto se construyó ni se probó en la consola: lo de abajo sale de leer el código y de compilar cada pieza por separado.

## Qué estaba mal (leído en el código)

1. **DNS:** el `config.h` de Orbis no define `HAVE_GETADDRINFO`. El `unix_getaddrinfo` de ws2_32 devolvía error siempre ("getaddrinfo() not found during build time"). Además, la libc del SDK (musl) lee `/etc/resolv.conf`, que una app de PS4 no tiene, y le pregunta a 127.0.0.1.
2. **Sockets no bloqueantes:** wineserver usa `fcntl(F_SETFL, O_NONBLOCK)` en cada socket (`server/sock.c`). W013 midió que la consola lo rechaza en un socket. Con el socket bloqueante, `connect` y `accept` bloquearían el servidor, que corre en el mismo proceso.
3. **`sendmsg`/`recvmsg`:** `pw_wine_sendmsg/recvmsg` se escribieron para el socketpair del servidor. Rechazaban una dirección (`sendto`/`recvfrom` de UDP) y cualquier flag de envío.
4. **Números `MSG_*`:** los del SDK son los de Linux y el kernel lee los de FreeBSD. Por ejemplo, `MSG_DONTWAIT` (0x40) es `MSG_WAITALL` para el kernel, y `MSG_TRUNC` vuelve como 0x10.
5. **Adaptadores:** `nsi.dll` le pide todas las tablas de red a `\\.\Nsi` (nsiproxy.sys, en winedevice.exe), que no corre en el modelo de un proceso. Por eso `GetAdaptersAddresses`, `GetAdaptersInfo` e ipconfig fallaban.
6. **dnsapi:** no tiene Unix side sin libresolv. `DnsQuery` y la lista de servidores DNS fallaban.

## Cambio

| Archivo | Qué hace |
|---|---|
| `platform/ps4/pw_ws2_32_libc.c` (nuevo) | `getaddrinfo`, `getnameinfo`, `gethostbyname`, `gethostbyaddr` y `gethostname` para el Unix side de ws2_32. Se adaptó de prospero-win (`wine/ps5/pw_ws2_32_libc.c`, ver `THIRD_PARTY.md`). Resuelve aquí mismo las direcciones numéricas, loopback, `localhost` y `PS4`. Los nombres con punto van a `sceNetResolverStartNtoa` (5 s por intento, 3 intentos) y, si hace falta, a `Ntoa6`. Un nombre de una sola etiqueta da `EAI_NONAME`. Un nombre no encontrado queda 5 s en caché negativa. Los servicios aceptados son un número o un nombre de una lista corta (`http`, `https`, `ftp`…); cualquier otro da `EAI_SERVICE` y una línea `PWNET`. No hay resolución inversa. |
| `tools/build-unixlibs-ps4.py` | Compila ws2_32 con `-DHAVE_GETADDRINFO` y con esas funciones en lugar de las de musl (`-Dgetaddrinfo=pw_ws2_getaddrinfo`…). Agrega la biblioteca `netctl`. |
| `platform/ps4/pw_wine_netctl.c` (nuevo), `pw_netctl_info.h` (nuevo) | **dnsapi.so:** servidores DNS desde `sceNetCtlGetInfo` (primario y secundario, sólo IPv4). `query` es una consulta DNS real por UDP a esos servidores (2 s, 2 intentos cada uno). Devuelve la respuesta tal como llega. No hay TCP: una respuesta truncada se devuelve con su bit TC y una traza. **nsi.so:** una llamada que lee IP, máscara, gateway, DNS, MAC, MTU y tipo de conexión. libSceNetCtl se carga en tiempo de ejecución, como el mouse en `hw_pad.c`. |
| `platform/ps4/pw_wine_unixlibs.c` | Entradas `dnsapi.so` y `nsi.so`. |
| `platform/ps4/pw_wine_net.c` / `.h` | `msg_name` hacia el kernel tal como viene. Traducción de los `MSG_*` en los dos sentidos; un flag sin traducción da `ENOTSUP` con traza. `EAGAIN` ya no gasta trazas. `pw_wine_socket_nonblock()` prueba `fcntl` y luego `sceNetSetsockopt(SO_NBIO)`, y deja una línea `PWNET nonblock` (la primera vez, o cada vez que falla). |
| `tools/build-wine-delete-server.py` | Además de `fd.c`, revisa `server/sock.c`: sus tres `fcntl(O_NONBLOCK)` pasan a llamar a `pw_wine_socket_nonblock`, y el `recv(MSG_DONTWAIT)` usa el número del kernel. |
| `tools/build-nsi-hw.py` (nuevo) | Compila nsi.dll de 64 y 32 bits. Si no puede abrir `\\.\Nsi`, arma las tablas desde nsi.so: interfaz loopback (1) e interfaz cableada o Wi-Fi (2), direcciones IPv4, rutas (loopback, subred, ruta por defecto) y en IPv6 sólo `::1`. Velocidad de enlace y contadores quedan en 0 porque no se conocen. Otras tablas (TCP/UDP, estadísticas, vecinos, notificaciones de cambio) devuelven `ERROR_NOT_SUPPORTED` con una línea `PWNSI`. |
| `fixtures/win32/nettest.c` (nuevo) | `nettest64.exe` y `nettest32.exe`. Ver abajo. |
| `tools/build-wine-hardware.py` | Compila los dos fixtures en `C:\orbis` e instala nsi.dll: la de 64 bits en `lib/wine/x86_64-windows` y `system32`, la de 32 bits en `lib/wine/i386-windows` y `syswow64`. Va después del bloque de programas, para reemplazar la nsi.dll fijada que trae su clausura. |
| `tools/stage-wine-programs.py` | `ipconfig` y `ping` en system32. |

<a id="fixture-nettest64exe--nettest32exe"></a>


## Fijación `nettest64.exe` / `nettest32.exe`

Uso: `nettest64.exe [nombre] [ipv4]`. Por defecto el nombre es `example.com`. La IPv4 sólo se usa si el nombre no resuelve. Cada ejecución agrega a `C:\orbis\net-result.txt` un bloque que empieza con `run arch=64|32 …` y termina con `end`. Pasos, cada uno con `ok=` y el código de error de Winsock o Win32:

- `wsastartup`
- `dns`: `getaddrinfo(nombre, "80")`, con las respuestas y los ms.
- `tcp`: `connect` bloqueante a la primera IPv4, con la dirección local.
- `http`: envía `HEAD / HTTP/1.0` y recibe la línea de estado (`status=HTTP/1.x …`), con 10 s de espera.
- `nbio`: el mismo `connect` en un socket no bloqueante, completado con `select`.
- `loopback`: bind/listen en 127.0.0.1, connect, accept y un byte en cada sentido.
- `adapters`: `GetAdaptersAddresses`, con nombre, tipo, estado, MAC, MTU, direcciones, gateway y DNS.
- `udp`: pregunta DNS por UDP (`sendto`/`recvfrom`, 5 s) al primer DNS de los adaptadores, o a 8.8.8.8 si no hay ninguno.

Un paso que no puede correr porque falló uno anterior lo dice (`skipped=…`) y queda con `ok=0`.

**Criterio de aprobado:** en los dos bloques (64 y 32), `dns ok=1`, `tcp ok=1` y `http ok=1` con una línea de estado HTTP.

## Construcción (orden)

1. `python3 tools/build-unixlibs-ps4.py`
2. `python3 tools/build-wine-delete-server.py`
3. `python3 tools/build-nsi-hw.py`
4. `python3 tools/stage-wine-programs.py` (sólo si entran ping/ipconfig)
5. `python3 tools/link-wine-boot.py`
6. `python3 tools/build-wine-hardware.py`

No hace falta recompilar `build/wine-boot` ni `build/wine-server`: los cambios entran por objetos separados, como `virtual.o` o `fd.o`.

## Qué buscar en el log

- `PWNET resolve name=example.com family=… found=1 rc4=0x00000000`: el resolvedor de la consola respondió.
- `PWNET nonblock fd=… fcntl_errno=… so_nbio=0x00000000`: el socket quedó no bloqueante por SO_NBIO. Si `so_nbio` es negativo, los sockets siguen bloqueantes.
- `PWNET netctl module=… init_sym=0 get_sym=0` y `PWNET netctl init=… ip=…`: libSceNetCtl se cargó y dio la configuración.
- `PWNSI …`: una tabla que pidió algún programa y que no está.
- `PWBOOT sendmsg_failed` / `recvmsg_failed stage=flag|kernel`: un envío o una recepción rechazados.

## No verificado / riesgos

- Que `SO_NBIO` (0x1200, nivel 0xffff) funcione desde la app. El valor sale de shadPS4. Si no funciona, `tcp` puede pasar igual (connect bloqueante), pero `nbio` falla y el servidor queda bloqueado durante el connect.
- Que `libSceNetCtl.sprx` cargue con `sceKernelLoadStartModule` sin `sceSysmoduleLoadModuleInternal(NETCTL)`. Si no carga, adapters y DNS de dnsapi devuelven error con traza, y `dns`/`tcp`/`http` no dependen de eso.
- Los números de opciones de nivel IP del SDK (`IP_TOS`, `IP_TTL`, `IP_MULTICAST_*`, `IPV6_V6ONLY`) también son de Linux y no se tradujeron. TCP y UDP básicos no los usan; multicast y TTL quedan pendientes.
- ICMP: `IcmpCreateFile` de iphlpapi abre `\\.\Nsi` directamente, e `IcmpSendEcho` va a nsiproxy (`IOCTL_NSIPROXY_WINE_ICMP_ECHO`). Sin nsiproxy, `ping` termina con error al crear el handle ICMP. No se implementó: habría que revisar iphlpapi para que use un socket ICMP, y no se sabe si la app puede abrir uno.
- `ipconfig` debería mostrar la IP de la consola si nsi.dll y libSceNetCtl responden.
- `nslookup` no existe en este commit de Wine.
- IPv6: sólo `::1`. No se leen las direcciones IPv6 de la consola.

## Prueba física

Pendiente.
