<a id="w187-registro-de-red-de-pale-moon-fase-9"></a>


# W187: network record of Pale Moon (phase 9)

[English](HARDWARE_W187.md) | [Español](HARDWARE_W187-es.md)

APP_VER 02.86. Base W186. The result of W186 is in `docs/HARDWARE_W186.md`. The browser session prepared it.

<a id="qué-pasó-con-el-log-de-w185"></a>


## What happened to the log of W185

The `user.js` of W185 requested the network log of Pale Moon in `C:\orbis\palemoon-net.log`. In the console there was only one file, `C:\orbis\palemoon-net.log-main.32`, with 0 bytes.

- **The name:** Mozilla log preference observer opens the file of `logging.config.LOG_FILE` with the suffix `-main.<pid>`. So the exact name `palemoon-net.log` does not exist.
- **Why it was empty:** the `user.js` put `logging.config.clear_on_startup=true`. That value does not empty the file: when you start, delete all the preferences `logging.*` that the user put, including the levels of the modules that he had just put the `user.js`. Pale Moon opened the file with the name it already had and did not register anything.

<a id="cambio"></a>


## Change

`fixtures/browser/palemoon-user.js`: `logging.config.clear_on_startup=false`. Do not change the route: the file will be `C:\orbis\palemoon-net.log-main.<pid>`.

The levels of the modules (`nsIOService`, `nsNotifyAddr`, `nsHostResolver`, `nsSocketTransport`, `nsHttp` remain the same, `logging.config.sync` and `logging.config.add_timestamp`, and network preferences of W185.

<a id="construcción"></a>


## Build

1. `python3 tools/build-wine-hardware.py` (copy the new `user.js`)

<a id="prueba-física"></a>


## Physical test

1. Open Pale Moon, write `example.com` in the address bar and press Enter. If there is no keyboard: Triangle on the pad, or Cross on the arrow to go.
2. Write down what you see.
3. Down by FTP `C:\orbis\palemoon-net.log-main.*`. Now you have to have lines with time: for example, resolution of `example.com` (`nsHostResolver`) and connection (`nsSocketTransport`).
4. In the log of the Runs they have to appear `input_event … code=13` (or `source=pad`) and `PWNET resolve name=example.com`.

<a id="no-verificado"></a>


## Not verified

- Nothing was tested on the console.
- The names of the log modules could not be confirmed in `xul.dll`. If any of them don't exist, that module doesn't write anything.

<a id="prueba-física-1"></a>


## Physical test

It was not tested: W188 arrived earlier with the arrangement and kept the network record.
