# W185: Pale Moon siempre en línea, sin proxy del sistema ni IPv6, con registro de red (fase 9)

[English](HARDWARE_W185.md) | [Español](HARDWARE_W185-es.md)

APP_VER 02.84. Base W184. El resultado de W184 está en `docs/HARDWARE_W184.md`. Lo preparó la sesión del navegador. El `palemoon-user.js` que se publicó es el final (sha256 `e37725f4…`), con `network.proxy.type=0` y `network.notify.changed=false`.

## Qué pasó en W184

Pale Moon abre como título aparte, pero según el usuario no navega: "escribí google.com y youtube.com, y busqué google en la barra de duck duck go y nada, al hacer enter o click en el icono de ir, no navegó". No aparece página de error, ni carga, ni aviso de sin conexión.

Log de la corrida: `reports/wine-hardware-w184/physical/20261103T234412Z/run-0002.log`. El directorio `…T234342Z` tiene los mismos registros.

1. **En el log no hay ningún pedido de navegación:**
   - El lanzador registra cada tecla y cada clic antes de que lleguen a Wine (`PWBOOT input_event`). En la corrida de Pale Moon el texto tecleado es `WWW.GOGLE.CO` (con los retrocesos). Después no hay Enter (código 13), ni clic, ni botón del pad; sólo la rueda del mouse.
   - El Enter del teclado sí funciona en la consola: run-0001 (el escritorio) registra el código 13.
   - En esta corrida tampoco está la búsqueda de DuckDuckGo ni youtube.com (no se teclearon D, U, K, Y, T ni B). Lo que describe el usuario pasó en otra sesión, que este reporte no tiene.
2. **No hubo ninguna resolución de nombres.** El resolvedor de la consola (`platform/ps4/pw_ws2_32_libc.c`) registra cada búsqueda (`PWNET resolve name=… found=…`; `nettest` las muestra desde W176), y en esta corrida no hay ninguna. Coincide con el punto 1: Pale Moon nunca pidió una página.
3. **Las notificaciones de red no bloquean:**
   - El monitor de enlace de Pale Moon usa `NotifyIpInterfaceChange`, que en Wine es un stub y devuelve enseguida.
   - `NotifyAddrChange` pasa por `NsiRequestChangeNotification`. Sin `nsiproxy.sys`, el `nsi.dll` de la consola devuelve `ERROR_NOT_SUPPORTED` enseguida (`PWNSI change notifications are not provided`). Ninguno de los dos puede quedarse esperando.
4. **Otras líneas del log:**
   - **`PWNSI table 11 …`:** la tabla 11 del módulo `NPI_MS_IPV4_MODULEID` es la de vecinos (ARP, `NSI_IP_NEIGHBOUR_TABLE`). Pale Moon la usa sólo para calcular un identificador de la red, no para decidir si hay enlace.
   - **El enlace:** Pale Moon lo decide con `GetAdaptersAddresses`, y en W176 `nettest64` mostró la interfaz Wi-Fi encendida y con IPv4.
   - **Clases COM sin registrar:** `{43fb1553-…}` (Tablet PC Ink) y `{56fdf344-…}` (`TaskbarList`). No tienen que ver con la red.
   - **Proxy:** WinINet se carga y lee sus opciones globales (`query_global_option Unknown dwOption 10`). Es el proxy "del sistema", el valor por defecto de Pale Moon.
   - **Al cerrar:** `RtlpWaitForCriticalSection … blocked by 0050`. El hilo `0050` no registra nada. Queda sin explicar.

## Cambio

Sólo `fixtures/browser/palemoon-user.js`. Los builders compartidos no cambian: `build-wine-hardware.py` ya copia el `user.js`.

Las preferencias descartan lo que podría frenar una navegación cuando se pida. Todas están en `xul.dll` de Pale Moon 35:

| Preferencia | Para qué |
|---|---|
| `network.manage-offline-status=false`, `network.offline-mirrors-connectivity=false` | Pale Moon no pasa a "sin conexión" si su revisión de enlace falla con las tablas de la consola. |
| `network.captive-portal-service.enabled=false` | Sin la petición de aviso de portal cautivo al arrancar. |
| `network.dns.disableIPv6=true` | Sólo IPv4. Cuando IPv4 no encuentra nada, el resolvedor de la consola también prueba IPv6, con 5 s por intento, y la consola no tiene ruta IPv6. |
| `network.proxy.type=0` | Sin proxy. No lee la configuración de proxy de Windows a través de WinINet. |
| `network.notify.changed=false` | No reacciona a avisos de cambio de red, que en la consola no existen. |

**Diagnóstico, temporal:**
- El log de red del propio Pale Moon va a `C:\orbis\palemoon-net.log` (`logging.config.*`, una línea por vez, borrado en cada arranque).
- Módulos: `nsIOService`, `nsNotifyAddr`, `nsHostResolver`, `nsSocketTransport` y `nsHttp`. Si alguno de esos nombres no existe, se ignora.
- Hay que sacarlo cuando la navegación funcione.

**No hace falta más traza por ahora.** Las líneas `PWNET resolve` ya muestran cada búsqueda de nombre y las `input_event` cada tecla. Si con un pedido real no aparece ninguna `PWNET resolve`, recién ahí conviene `+winsock` para el título de Pale Moon (en el lanzador, archivo de la sesión principal).

## Construcción

1. `python3 tools/build-wine-hardware.py` (copia el `user.js` nuevo)

## Prueba física

1. Abrir Pale Moon, hacer clic en la barra de direcciones y escribir `example.com`.
2. Apretar Enter en el teclado. Si no hay teclado: Triángulo en el pad, que manda Enter, o clic (Cruz) en la flecha de ir.
3. Anotar qué se ve: página, error (con su texto) o espera.
4. **Qué buscar en el log de la corrida:**
   - una línea `input_event source=keyboard … code=13` (o `source=pad`) después del texto: confirma que el pedido llegó;
   - `PWNET resolve name=example.com …`: confirma que Pale Moon resolvió el nombre.
5. Bajar `C:\orbis\palemoon-net.log` por FTP.

Si llegan el Enter y la resolución y aun así no carga, el log de red muestra dónde se corta (conexión, TLS o HTTP).

## No verificado

- Nada se probó en la consola.
- No se sabe qué pasó en la sesión que describe el usuario: no está en este reporte.
- El cuelgue al cerrar (hilo `0050`) no está explicado.

## Prueba física

Reporte: `reports/wine-hardware-w185/physical/20261104T000907Z/`. Según el usuario, "se congeló Pale Moon ahora".

- No se creó `C:\orbis\palemoon-net.log`.
- `run-0002.log`:
  - `PWBOOT thread_signal unavailable thread=0070 sig=10` (SIGUSR1, el pedido del servidor para detener un hilo y leer su contexto);
  - un clic;
  - `RtlpWaitForCriticalSection … wait timed out in thread 0024, blocked by 0050`. Es el mismo bloqueo que en W184 al cerrar.
- **Causa:** el hilo que pidió el contexto de otro (el monitor de cuelgues de Pale Moon) espera para siempre, porque la señal nunca llega (W064: sin señales dirigidas a un hilo), y tiene tomado un lock que el hilo de la interfaz necesita. Arreglo en W186.
