# W188: keepalive de TCP en Pale Moon (fase 9, borrador)

[English](HARDWARE_W188-navegador-borrador.md) | [Español](HARDWARE_W188-navegador-borrador-es.md)

Borrador de la sesión lateral del navegador, para unir a `HARDWARE_W188.md`. Cubre sólo la parte del navegador. La traducción de opciones de sockets en `pw_wine_net.c` y el origen de números aleatorios en ntdll son de la sesión principal y van en su parte del documento. Nada de esto se probó en la consola.

## Qué pasó en W186

Reporte: `reports/wine-hardware-w186/physical/20261104T002752Z/`

- **Lo que funciona:**
  - Pale Moon ya no se cuelga.
  - Llega el Enter (`code=13`) y el nombre se resuelve (`PWNET resolve name=duckduckgo.com family=2 found=1`; `family=2` es sólo IPv4, por la preferencia de W185).
  - La página local se ve completa: `es5-ok`, `es2020-ok`, `canvas-ok`.
- **Lo que no:** los sitios remotos quedan en blanco o dan error.
- **En el log, después de la resolución:** no hay ningún error de red. Sólo aparecen intentos repetidos de detener dos hilos (`thread_signal unavailable thread=0070 sig=10`, y lo mismo con `00ac`). Coincide con el monitor de cuelgues de Pale Moon tomando muestras de un hilo trabado.

## Causa probable

- **Los números de las opciones TCP:** el `netinet/tcp.h` del SDK trae los números de Linux (`TCP_KEEPIDLE=4`, `TCP_KEEPINTVL=5`, `TCP_KEEPCNT=6`), pero el kernel de la consola es FreeBSD. Ahí `IPPROTO_TCP` 4 es `TCP_NOPUSH`, y keepalive usa `0x100`, `0x200` y `0x400`. Las opciones de nivel socket (`SOL_SOCKET=0xffff`, `SO_KEEPALIVE=8`) sí coinciden con FreeBSD.
- **Qué hace Wine:** cuando un programa pide keepalive (`WSAIoctl(SIO_KEEPALIVE_VALS)`), Wine (`ntdll/unix/socket.c`, `IOCTL_AFD_WINE_KEEPALIVE_VALS`) hace `setsockopt(IPPROTO_TCP, TCP_KEEPIDLE, segundos)`. En la consola eso enciende `TCP_NOPUSH`.
- **El efecto:** el kernel retiene lo que se escribe hasta juntar un segmento completo o hasta que se cierra el socket. El inicio de una conexión TLS (ClientHello) o un pedido HTTP corto no salen nunca, así que la página queda en blanco y termina por tiempo.
- **Pale Moon pide keepalive** en sus conexiones por defecto (`network.tcp.keepalive.enabled`).
- **Por qué la fase 8 no lo vio:** `nettest` (fase 8) no pide keepalive, y su `HEAD /` funcionó.

## Cambio (parte del navegador)

`fixtures/browser/palemoon-user.js`: `network.tcp.keepalive.enabled=false`. La preferencia está en `xul.dll` de Pale Moon 35. Con esto, Pale Moon no llama a `SIO_KEEPALIVE_VALS`. Queda aunque la traducción de `pw_wine_net.c` arregle la causa, como segunda protección.

## Construcción

`python3 tools/build-wine-hardware.py` (copia el `user.js` nuevo), junto con los cambios de la sesión principal.

## Prueba física

1. Abrir Pale Moon y entrar a `https://example.com/`, `https://duckduckgo.com/` y un sitio `http://`.
2. Anotar, para cada uno, si carga y en cuánto tiempo más o menos.
3. Bajar `C:\orbis\palemoon-net.log-main.*`. Tiene que mostrar la conexión, el intercambio TLS y la respuesta HTTP.
4. **Si todavía no carga:** buscar en ese log dónde se corta (conexión, TLS o HTTP) y en el log de la corrida las líneas `PWNET` de las opciones de socket.

## No verificado

- Nada se probó en la consola.
- La causa se dedujo leyendo el código y los encabezados. El log de red de W187 todavía no se revisó.
