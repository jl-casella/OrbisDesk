# W187: registro de red de Pale Moon (fase 9)

[English](HARDWARE_W187.md) | [Español](HARDWARE_W187-es.md)

APP_VER 02.86. Base W186. El resultado de W186 está en `docs/HARDWARE_W186.md`. Lo preparó la sesión del navegador.

## Qué pasó con el log de W185

El `user.js` de W185 pedía el log de red de Pale Moon en `C:\orbis\palemoon-net.log`. En la consola quedó un solo archivo, `C:\orbis\palemoon-net.log-main.32`, con 0 bytes.

- **El nombre:** el observador de preferencias de log de Mozilla abre el archivo de `logging.config.LOG_FILE` con el sufijo `-main.<pid>`. Por eso el nombre exacto `palemoon-net.log` no existe.
- **Por qué quedó vacío:** el `user.js` ponía `logging.config.clear_on_startup=true`. Ese valor no vacía el archivo: al arrancar, borra todas las preferencias `logging.*` que puso el usuario, incluidos los niveles de los módulos que acababa de poner el `user.js`. Pale Moon abrió el archivo con el nombre que ya tenía y no registró nada.

## Cambio

`fixtures/browser/palemoon-user.js`: `logging.config.clear_on_startup=false`. No cambia la ruta: el archivo va a ser `C:\orbis\palemoon-net.log-main.<pid>`.

Siguen igual los niveles de los módulos (`nsIOService`, `nsNotifyAddr`, `nsHostResolver`, `nsSocketTransport`, `nsHttp`), `logging.config.sync` y `logging.config.add_timestamp`, y las preferencias de red de W185.

## Construcción

1. `python3 tools/build-wine-hardware.py` (copia el `user.js` nuevo)

## Prueba física

1. Abrir Pale Moon, escribir `example.com` en la barra de direcciones y apretar Enter. Si no hay teclado: Triángulo en el pad, o Cruz en la flecha de ir.
2. Anotar qué se ve.
3. Bajar por FTP `C:\orbis\palemoon-net.log-main.*`. Ahora tiene que tener líneas con hora: por ejemplo, la resolución de `example.com` (`nsHostResolver`) y la conexión (`nsSocketTransport`).
4. En el log de la corrida tienen que aparecer `input_event … code=13` (o `source=pad`) y `PWNET resolve name=example.com`.

## No verificado

- Nada se probó en la consola.
- No se pudieron confirmar en `xul.dll` los nombres de los módulos de log. Si alguno no existe, ese módulo no escribe nada.

## Prueba física

No se probó: W188 llegó antes con el arreglo y mantiene el registro de red.
