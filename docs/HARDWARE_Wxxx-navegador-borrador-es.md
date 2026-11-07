# Wxxx: Pale Moon sin log de red (fase 9, borrador)

[English](HARDWARE_Wxxx-navegador-borrador.md) | [Español](HARDWARE_Wxxx-navegador-borrador-es.md)

Borrador de la sesión lateral del navegador. La sesión principal asigna el número y lo une al `HARDWARE_Wxxx.md` que toque. Base W188. Nada de esto se probó en la consola.

## Qué pasó en W188

Reporte: `reports/wine-hardware-w188/physical/20261104T024404Z/`

- El usuario respondió "Navega": Pale Moon carga sitios remotos.
- La traducción de opciones de socket rechazó sólo tres, que no tienen equivalente en la consola. Ninguna rompió nada visible:
  - TCP 7 (`TCP_SYNCNT` en Linux).
  - IP 10 (`IP_MTU_DISCOVER` en Linux).
  - IPv6 62 (`IPV6_DONTFRAG` en Linux).
  - Los nombres salen de los números de Linux del SDK. No se comprobó qué llamada de Wine los pide.
- No se midió qué sitios funcionan ni cuánto tardan.
- `C:\orbis\palemoon-net.log-main.32` siguió con 0 bytes. No se sabe por qué el log de red de Pale Moon no escribe. Como ya no hace falta, no se sigue investigando.

## Cambio

`fixtures/browser/palemoon-user.js`: se sacan las preferencias de diagnóstico de W185 y W187 (`logging.config.*` y `logging.<módulo>`). Quedan las de red de W185 y `network.tcp.keepalive.enabled=false` de W188.

En la consola queda el archivo viejo `C:\orbis\palemoon-net.log-main.32`, vacío. Se puede borrar a mano; no molesta.

## Construcción

1. `python3 tools/build-wine-hardware.py` (copia el `user.js` nuevo)

## Prueba física

1. Abrir Pale Moon. La página local de prueba tiene que seguir dando `es5-ok`, `es2020-ok` y `canvas-ok`.
2. Entrar a estos sitios y anotar, para cada uno, si carga y cuánto tarda más o menos:
   - `https://example.com/`
   - `https://duckduckgo.com/` y una búsqueda
   - `http://neverssl.com/` (sin TLS)
   - un sitio más pesado, por ejemplo `https://en.wikipedia.org/`
3. Comprobar que no aparece un archivo `C:\orbis\palemoon-net.log-main.*` nuevo.

## No verificado

- Nada se probó en la consola.
- La causa del log vacío sigue sin conocerse.
