<a id="wxxx-pale-moon-sin-log-de-red-fase-9-borrador"></a>


# Wxxx: Pale Moon without network log (phase 9, draft)

[English](HARDWARE_Wxxx-navegador-borrador.md) | [Español](HARDWARE_Wxxx-navegador-borrador-es.md)

Eraser of the browser side session. The main session assigns the number and binds it to the `HARDWARE_Wxxx.md` you touch. Base W188. None of this was tested on the console.

<a id="qué-pasó-en-w188"></a>


## What happened in W188

Reporte: `reports/wine-hardware-w188/physical/20261104T024404Z/`.

- The user responded "Sail": Pale Moon loads remote sites.
- The translation of socket options rejected only three, which have no equivalent on the console. None of them broke anything visible:
  - TCP 7 (`TCP_SYNCNT` in Linux).
  - IP 10 (`IP_MTU_DISCOVER` in Linux).
  - IPv6 62 (`IPV6_DONTFRAG` in Linux).
  - The names come from the Linux numbers of SDK. It was not checked which call of Wine you asked.
- He didn't measure which places work or how long it takes.
- `C:\orbis\palemoon-net.log-main.32` continued with 0 bytes. It is not known why the network log of Pale Moon does not write. As it is no longer necessary, no further investigation is required.

<a id="cambio"></a>


## Change

`fixtures/browser/palemoon-user.js`: The diagnostic preferences of W185 and W187 (`logging.config.*` and `logging.<módulo>` are removed. There are those of network of W185 and `network.tcp.keepalive.enabled=false` of W188.

In the console is the old file `C:\orbis\palemoon-net.log-main.32`, empty. It can be erased by hand; It doesn't bother.

<a id="construcción"></a>


## Build

1. `python3 tools/build-wine-hardware.py` (copy the new `user.js`)

<a id="prueba-física"></a>


## Physical test

1. Open Pale Moon. The local test page has to continue to give `es5-ok`, `es2020-ok` and `canvas-ok`.
2. Enter these sites and score, for each, if you load and how much it takes more or less:
   - `https://example.com/`
   - `https://duckduckgo.com/` and a search
   - `http://neverssl.com/` (without TLS)
   - a heavier site, for example `https://en.wikipedia.org/`
3. Check that no new `C:\orbis\palemoon-net.log-main.*` file appears.

<a id="no-verificado"></a>


## Not verified

- Nothing was tested on the console.
- The cause of the empty log is still unknown.
