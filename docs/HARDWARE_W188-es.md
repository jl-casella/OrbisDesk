# W188: números de opciones de socket del kernel (fases 8 y 9)

[English](HARDWARE_W188.md) | [Español](HARDWARE_W188-es.md)

APP_VER 02.87. Base W187. El resultado de W187 está en `docs/HARDWARE_W187.md`.

## Opciones de socket

**El problema** (lo encontró la sesión del navegador):
- Los encabezados `netinet/` del SDK usan los números de Linux para las opciones de nivel TCP, IP e IPv6, y el kernel de la consola lee los de FreeBSD. El nivel de socket (`SOL_SOCKET` 0xffff) coincide.
- `SIO_KEEPALIVE_VALS` de Wine pone `TCP_KEEPIDLE` (4), que para FreeBSD es `TCP_NOPUSH`. El kernel retenía los segmentos cortos, y el saludo TLS y los pedidos HTTP de Pale Moon no salían. En W186 los nombres resolvían, pero las páginas quedaban en blanco y sin error.
- Las pruebas de red de W176 pasaron porque un `HEAD /` simple no activa keep-alive.

**El cambio:**
- `platform/ps4/pw_wine_net.c`: `__wrap_setsockopt` y `__wrap_getsockopt` traducen las opciones:
  - TCP: `TCP_NODELAY` y `TCP_MAXSEG` igual; `TCP_KEEPIDLE`/`KEEPINTVL`/`KEEPCNT` a 0x100/0x200/0x400.
  - IP: `TOS`, `TTL`, `HDRINCL`, `OPTIONS`, `MULTICAST_IF/TTL/LOOP`, `ADD/DROP_MEMBERSHIP`, `RECVTTL` y `RECVTOS`.
  - IPv6: `UNICAST_HOPS`, `MULTICAST_IF/HOPS/LOOP`, `JOIN/LEAVE_GROUP` y `V6ONLY`.
  - Una opción sin equivalente en FreeBSD (`TCP_CORK`, `IP_PKTINFO`, `IP_MTU_DISCOVER`…) da `ENOPROTOOPT` con `PWNET setsockopt|getsockopt … unsupported`, en lugar de caer sobre otra opción.
- `tools/build-wine-hardware.py`: el enlace final pasa `--wrap=setsockopt --wrap=getsockopt`. Así llega todo llamador, incluido el código de sockets de ntdll, compilado hace tiempo.
- Los envoltorios están en un archivo aparte, `platform/ps4/pw_wine_sockopt.c`, que sólo entra al enlace final. El primer intento los tenía en `pw_wine_net.c` con `__real_*` débiles, pero `link-wine-boot.py` compila ese archivo también en `bootstrap.elf`, y `create-fself` rechazó el símbolo sin resolver (`missing library for symbol (__real_setsockopt)`).
- Compila sin advertencias.

## Pendiente: aleatoriedad

`get_random()` de ntdll prueba `getrandom()`, un stub del SDK que da ENOSYS, y después `/dev/urandom`. No se sabe si el sandbox deja abrir `/dev/urandom`; si no, Wine sólo avisa y devuelve el búfer sin cambiar, y NSS sembraría su generador con bytes fijos. Sumar una traza o una fuente de la consola requiere recompilar el objeto de ntdll que W103 ya reemplaza; queda para otra build.

## Pale Moon: keep-alive apagado (fase 9, sesión del navegador)

### Qué pasó en W186

Reporte: `reports/wine-hardware-w186/physical/20261104T002752Z/`

- **Lo que funciona:**
  - Pale Moon ya no se cuelga.
  - Llega el Enter (`code=13`) y el nombre se resuelve (`PWNET resolve name=duckduckgo.com family=2 found=1`; `family=2` es sólo IPv4, por la preferencia de W185).
  - La página local se ve completa: `es5-ok`, `es2020-ok`, `canvas-ok`.
- **Lo que no:** los sitios remotos quedan en blanco o dan error.
- **En el log, después de la resolución:** no hay ningún error de red. Sólo aparecen intentos repetidos de detener dos hilos (`thread_signal unavailable thread=0070 sig=10`, y lo mismo con `00ac`). Coincide con el monitor de cuelgues de Pale Moon tomando muestras de un hilo trabado.

### Causa probable

- **Los números de las opciones TCP:** el `netinet/tcp.h` del SDK trae los números de Linux (`TCP_KEEPIDLE=4`, `TCP_KEEPINTVL=5`, `TCP_KEEPCNT=6`), pero el kernel de la consola es FreeBSD. Ahí `IPPROTO_TCP` 4 es `TCP_NOPUSH`, y keepalive usa `0x100`, `0x200` y `0x400`. Las opciones de nivel socket (`SOL_SOCKET=0xffff`, `SO_KEEPALIVE=8`) sí coinciden con FreeBSD.
- **Qué hace Wine:** cuando un programa pide keepalive (`WSAIoctl(SIO_KEEPALIVE_VALS)`), Wine (`ntdll/unix/socket.c`, `IOCTL_AFD_WINE_KEEPALIVE_VALS`) hace `setsockopt(IPPROTO_TCP, TCP_KEEPIDLE, segundos)`. En la consola eso enciende `TCP_NOPUSH`.
- **El efecto:** el kernel retiene lo que se escribe hasta juntar un segmento completo o hasta que se cierra el socket. El inicio de una conexión TLS (ClientHello) o un pedido HTTP corto no salen nunca, así que la página queda en blanco y termina por tiempo.
- **Pale Moon pide keepalive** en sus conexiones por defecto (`network.tcp.keepalive.enabled`).
- **Por qué la fase 8 no lo vio:** `nettest` (fase 8) no pide keepalive, y su `HEAD /` funcionó.

### Cambio (parte del navegador)

`fixtures/browser/palemoon-user.js`: `network.tcp.keepalive.enabled=false`. La preferencia está en `xul.dll` de Pale Moon 35. Con esto, Pale Moon no llama a `SIO_KEEPALIVE_VALS`. Queda aunque la traducción de `pw_wine_net.c` arregle la causa, como segunda protección.

### Construcción

`python3 tools/build-wine-hardware.py` (copia el `user.js` nuevo), junto con los cambios de la sesión principal.

### Prueba física

1. Abrir Pale Moon y entrar a `https://example.com/`, `https://duckduckgo.com/` y un sitio `http://`.
2. Anotar, para cada uno, si carga y en cuánto tiempo más o menos.
3. Bajar `C:\orbis\palemoon-net.log-main.*`. Tiene que mostrar la conexión, el intercambio TLS y la respuesta HTTP.
4. **Si todavía no carga:** buscar en ese log dónde se corta (conexión, TLS o HTTP) y en el log de la corrida las líneas `PWNET` de las opciones de socket.

### No verificado (antes de la prueba)

- La causa se dedujo leyendo el código y los encabezados. El log de red de W187 quedó vacío.
- Nota posterior: la prueba de W188 (abajo) confirma el arreglo, aunque no separa cuánto aporta la traducción y cuánto la preferencia.

## Prueba física

Reporte: `reports/wine-hardware-w188/physical/20261104T024404Z/`

- **Resultado:** el usuario contestó "Navega". Pale Moon carga sitios remotos por primera vez.
- **Resolución de nombres:** `duckduckgo.com`, `improving.duckduckgo.com` y `duck.ai` (`found=1`, IPv4).
- **Opciones rechazadas por la traducción** (una por socket, sin efecto visible):
  - TCP 7: en Linux es `TCP_SYNCNT`; no existe en FreeBSD.
  - IP 10: en Linux es `IP_MTU_DISCOVER`. FreeBSD tiene `IP_DONTFRAG` (67), pero no es lo mismo; se deja rechazada.
  - IPv6 62: en Linux es `IPV6_DONTFRAG`, y en FreeBSD tiene el mismo número. Se puede pasar sin traducir en una build próxima.
- **El log de red de Pale Moon:** `C:\orbis\palemoon-net.log-main.32` sigue con 0 bytes, igual que en W187. Ya no hace falta para esta falla; queda para revisar si Pale Moon vuelve a fallar.
- **No medido:** tiempos de carga y qué sitios funcionan bien o mal; HTTPS de MSHTML (WebView) no se probó.
