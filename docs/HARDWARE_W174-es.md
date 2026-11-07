# W174: memoria flexible devuelta al liberar (fase 6), winecfg completo (fase 7) y red para programas Windows (fase 8)

[English](HARDWARE_W174.md) | [Español](HARDWARE_W174-es.md)

APP_VER 02.73. Base W173. El resultado de W173 está en `docs/HARDWARE_W173.md`.

## Memoria flexible

`tools/build-audio-ps4.py`, `virtual.c` de ntdll, sólo en Orbis:
- `unmap_area` (liberar dentro de un área reservada) y `decommit_pages` ya no hacen sólo un `mmap` `PROT_NONE` de libc sobre el rango.
  - Primero desmapean con `sceKernelMunmap`, que devuelve la memoria flexible.
  - Después vuelven a reservar con `pw_wine_anon_tryfixed` (`sceKernelReserveVirtualRange`), la reserva que `pw_wine_memory_protect` sabe comprometer.
  - Si algo falla, se usa el mapeo de Wine como antes y queda `PWVM rereserve … falling back`.
- `PWVM commit` agrega `flexible_free`, la memoria flexible libre en ese momento, para ver si el presupuesto baja durante la carrera.
- Las consultas leen bien el byte de flags.

Se espera que SuperMarioKart termine la carrera sin `PWVM fault`, con `flexible_free` estable.

## Red para programas Windows (fase 8, sesión de red)

### Qué estaba mal (leído en el código)

1. **DNS:** el `config.h` de Orbis no define `HAVE_GETADDRINFO`. El `unix_getaddrinfo` de ws2_32 devolvía error siempre ("getaddrinfo() not found during build time"). Además, la libc del SDK (musl) lee `/etc/resolv.conf`, que una app de PS4 no tiene, y le pregunta a 127.0.0.1.
2. **Sockets no bloqueantes:** wineserver usa `fcntl(F_SETFL, O_NONBLOCK)` en cada socket (`server/sock.c`). W013 midió que la consola lo rechaza en un socket. Con el socket bloqueante, `connect` y `accept` bloquearían el servidor, que corre en el mismo proceso.
3. **`sendmsg`/`recvmsg`:** `pw_wine_sendmsg/recvmsg` se escribieron para el socketpair del servidor. Rechazaban una dirección (`sendto`/`recvfrom` de UDP) y cualquier flag de envío.
4. **Números `MSG_*`:** los del SDK son los de Linux y el kernel lee los de FreeBSD. Por ejemplo, `MSG_DONTWAIT` (0x40) es `MSG_WAITALL` para el kernel, y `MSG_TRUNC` vuelve como 0x10.
5. **Adaptadores:** `nsi.dll` le pide todas las tablas de red a `\\.\Nsi` (nsiproxy.sys, en winedevice.exe), que no corre en el modelo de un proceso. Por eso `GetAdaptersAddresses`, `GetAdaptersInfo` e ipconfig fallaban.
6. **dnsapi:** no tiene Unix side sin libresolv. `DnsQuery` y la lista de servidores DNS fallaban.

### Cambio

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


### Fijación `nettest64.exe` / `nettest32.exe`

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

### Construcción (orden)

1. `python3 tools/build-unixlibs-ps4.py`
2. `python3 tools/build-wine-delete-server.py`
3. `python3 tools/build-nsi-hw.py`
4. `python3 tools/stage-wine-programs.py` (sólo si entran ping/ipconfig)
5. `python3 tools/link-wine-boot.py`
6. `python3 tools/build-wine-hardware.py`

No hace falta recompilar `build/wine-boot` ni `build/wine-server`: los cambios entran por objetos separados, como `virtual.o` o `fd.o`.

### Qué buscar en el log

- `PWNET resolve name=example.com family=… found=1 rc4=0x00000000`: el resolvedor de la consola respondió.
- `PWNET nonblock fd=… fcntl_errno=… so_nbio=0x00000000`: el socket quedó no bloqueante por SO_NBIO. Si `so_nbio` es negativo, los sockets siguen bloqueantes.
- `PWNET netctl module=… init_sym=0 get_sym=0` y `PWNET netctl init=… ip=…`: libSceNetCtl se cargó y dio la configuración.
- `PWNSI …`: una tabla que pidió algún programa y que no está.
- `PWBOOT sendmsg_failed` / `recvmsg_failed stage=flag|kernel`: un envío o una recepción rechazados.

### No verificado / riesgos

- Que `SO_NBIO` (0x1200, nivel 0xffff) funcione desde la app. El valor sale de shadPS4. Si no funciona, `tcp` puede pasar igual (connect bloqueante), pero `nbio` falla y el servidor queda bloqueado durante el connect.
- Que `libSceNetCtl.sprx` cargue con `sceKernelLoadStartModule` sin `sceSysmoduleLoadModuleInternal(NETCTL)`. Si no carga, adapters y DNS de dnsapi devuelven error con traza, y `dns`/`tcp`/`http` no dependen de eso.
- Los números de opciones de nivel IP del SDK (`IP_TOS`, `IP_TTL`, `IP_MULTICAST_*`, `IPV6_V6ONLY`) también son de Linux y no se tradujeron. TCP y UDP básicos no los usan; multicast y TTL quedan pendientes.
- ICMP: `IcmpCreateFile` de iphlpapi abre `\\.\Nsi` directamente, e `IcmpSendEcho` va a nsiproxy (`IOCTL_NSIPROXY_WINE_ICMP_ECHO`). Sin nsiproxy, `ping` termina con error al crear el handle ICMP. No se implementó: habría que revisar iphlpapi para que use un socket ICMP, y no se sabe si la app puede abrir uno.
- `ipconfig` debería mostrar la IP de la consola si nsi.dll y libSceNetCtl responden.
- `nslookup` no existe en este commit de Wine.
- IPv6: sólo `::1`. No se leen las direcciones IPv6 de la consola.

## winecfg completo: common controls v6 y códecs de audio (fase 7, sesión de accesos directos)

### Problemas de W173

Reporte: `reports/wine-hardware-w173/physical/20261103T193724Z`

- **La pestaña About cerraba winecfg.**
  - La página tiene un control `SysLink`. En el Wine fijado, comctl32 está partido: `dlls/comctl32` es v5 y no registra `SysLink`, que existe solo en `dlls/comctl32_v6`.
  - winecfg pide common controls 6.0 en su manifest, pero el prefijo sellado no tiene ese assembly en `winsxs` (solo gdiplus) y `comctl32_v6.dll` no estaba en el runtime.
  - Con v5 la página no se puede crear y el property sheet vuelve: winecfg terminó con status 0, sin ningún warning en el log (hilo 0040).
- **"Sonido de prueba no sonaba.**
  - winecfg llama a `PlaySound` asíncrono, que devuelve TRUE antes de reproducir; por eso no aparecía ningún error.
  - El sonido de prueba es IMA ADPCM (formato 0x11, mono, 44,1 kHz) y winmm necesita el códec ACM `imaadp32.acm` para decodificarlo. `system.ini [drivers32]` lo declara, pero el archivo no estaba.
  - Los dos `c0000135` del log son `msacm32.drv` (wave mapper) y `midimap.dll` (MIDI mapper), que winmm instala por nombre (`dlls/winmm/lolvldrv.c`).
  - El dispositivo de audio abrió bien (`PWAUDIO open ... failed=00000000`).

### Cambios

- `tools/stage-wine-extras.py` (nuevo). Del árbol de Wine fijado, sin parches, para x86_64 e i386:
  - `comctl32_v6.dll`, `imaadp32.acm`, `msadp32.acm`, `msg711.acm`, `msacm32.drv` y `midimap.dll`;
  - el assembly `Microsoft.Windows.Common-Controls` 6.0.2600.2982 como lo instala el `setupapi` de Wine (`fakedll.c`): `winsxs\{amd64,x86}_microsoft.windows.common-controls_6595b64144ccf1df_6.0.2600.2982_none_deadbeef\comctl32.dll` y su manifest en `winsxs\manifests`, con `processorArchitecture` completado.
  - Quedan afuera `msgsm32.acm` y `l3codeca.acm`, que necesitan librerías Unix (libgsm, mpg123).
- `tools/build-wine-hardware.py`:
  - copia los módulos a la carpeta builtin de cada arquitectura y a `system32`/`syswow64`, salvo `comctl32_v6.dll`, que el loader busca por ese nombre solo en la carpeta builtin;
  - copia el assembly a `winsxs`.
- Todos los imports de esos módulos, en las dos arquitecturas, ya estaban en el prefijo de W173.



### Prueba

1. winecfg → pestaña About:
   - se espera la página con el enlace a winehq.org;
   - en el run log, `comctl32.dll` cargado desde `winsxs\amd64_microsoft.windows.common-controls_...` (`trace+loaddll`).
2. winecfg → Audio → Test sound: se espera el sonido de prueba. En el log no tienen que aparecer los `c0000135` de `msacm32.drv` ni de `midimap.dll`.
3. Ajuste por programa (pendiente desde W172):
   - en Aplicaciones, agregar `d3d11test32.exe`, y en Bibliotecas poner `dxgi` = builtin;
   - cerrar la app y volver a abrirla: el ajuste tiene que seguir, y `d3d11test32.exe` tiene que fallar con el `dxgi` de Wine.
4. Regresión: el escritorio, el menú Inicio, WFM y Notepad. Los programas que piden common controls v6 ahora lo reciben, y los controles pueden verse distintos.

Riesgos:
- comctl32 v6 cambia el aspecto y el comportamiento de los controles en los programas con manifest v6. Explorer usa v5 y no cambia.
- Si un programa reproduce MP3 o GSM por ACM, sigue sin poder hacerlo: los códecs que lo hacen quedaron fuera de este cambio.

## Prueba física

Reporte: `reports/wine-hardware-w174/physical/20261103T200009Z/`. Respuesta del usuario: "SMK se cerró". `net-result.txt` está copiado en `build/w174-net-result.txt`.

**SuperMarioKart:**
- Mismo fallo (`PWVM fault addr=0x1f66000c`).
- `flexible_free` responde la pregunta: durante la carrera oscila entre ~80 y ~170 MB, así que la memoria se devuelve.
- Al final el juego compromete 25 bloques de 3 MiB seguidos sin liberar, y el último queda comprometido con `flexible_free=1048576`.
- No es una pérdida de memoria: el presupuesto de memoria flexible (~400 MB) no alcanza. No hubo ningún `PWVM rereserve … falling back`.

**Red** (fase 8, primera prueba):

|Paso| 64 bits (invitado) |32 bits|
|---|---|---|
| dns | falla (11001): el invitado recibió como argumento la línea de comandos de explorer (`/desktop=shell,1280x720`) | ok, `example.com` → 104.20.23.154, 254 ms |
| tcp | no corre (sin dirección) | ok, 22 ms |
|http://| no corre | `recv` queda pendiente 10 s (997) |
| nbio | no corre | ok |
|Loopback| ok | ok |
|adaptadores| Ok.: 192.168.68.104/22, puerta .1, DNS 62.210.38.117, MAC real | falla `c0000005`: el thunk WoW64 de `nsi.so` (`handle_syscall_fault` en `0x448086`, lectura de 0x8) |
| udp | `recvfrom` 997 | `recvfrom` 997 |

`libSceNetCtl` carga y responde (`PWNET netctl init=0x00000000 … ip=192.168.68.104`). Los arreglos van a W176.

**winecfg:** según el usuario, la pestaña About y Test sound funcionan. Common controls v6 y los códecs ACM hacen su parte.
