<a id="w186-pedidos-de-contexto-de-otro-hilo-sin-señal-pale-moon-fase-9"></a>


# W186: context orders of another thread without signal (Pale Moon, phase 9)

[English](HARDWARE_W186.md) | [Español](HARDWARE_W186-es.md)

APP_VER 02.85. Base W185. The result of W185 is in `docs/HARDWARE_W185.md`.

<a id="cambio"></a>


## Change

`tools/build-wine-delete-server.py` adds `server/thread.c` (fixed source, without overlay) to the server objects in process.

- **The problem:** to read or write the context of another thread, the server stops it with SIGUSR1. The console has no signals directed to a thread (W064, `ptrace.c` failure with `PWBOOT thread_signal unavailable`). The order was left in `STATUS_PENDING` and `GetThreadContext`/`SetThreadContext` They waited forever..
  - Pale Moon does so from your hang monitor with a taken lock, so your interface was frozen (W184, W185).
- **Now:** in `stop_thread`, if the signal could not be sent, the pending context is discarded as for a thread that ended (`cleanup_thread`). `get_thread_context` and `set_thread_context` on another thread return `STATUS_UNSUCCESSFUL` at the time.
- **What does not change:** `SuspendThread`. The thread stops at your next call to the server, as before.
- You're a complete unwarning.

<a id="qué-se-espera"></a>


## What is expected

- Pale Moon does not freeze.
- Browse with `example.com` + Enter: in the log, `PWNET resolve name=example.com`. It should also be created `C:\orbis\palemoon-net.log` (the preferences of W185 continue).

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w186/physical/20261104T002752Z/`. User response: remote blank or wrong pages.

- **It no longer freezes:** the hanging monitor continues to ask for contexts (`thread_signal unavailable thread=0070 sig=10`, many times), but it no longer appears `RtlpWaitForCriticalSection`.
- **Entry and DNS:** The Enter comes (`code=13`), and a search solves `duckduckgo.com` (`PWNET resolve … found=1`). Pale Moon also writes in his cache.
- **Local page** (capture): it looks complete in Pale Moon, with `es5-ok`, `es2020-ok`, `canvas-ok`, scripts in 34 ms and the user agent of Pale Moon 35.0.3 in Windows 10 x64.
- **Remote sites:** are left blank or wrong. The name solves, so the problem is later (connection, TLS or certificates). The network record of W187 will tell you.
