# W186: pedidos de contexto de otro hilo sin señal (Pale Moon, fase 9)

[English](HARDWARE_W186.md) | [Español](HARDWARE_W186-es.md)

APP_VER 02.85. Base W185. El resultado de W185 está en `docs/HARDWARE_W185.md`.

## Cambio

`tools/build-wine-delete-server.py` agrega `server/thread.c` (fuente fijada, sin overlay) a los objetos del servidor en proceso.

- **El problema:** para leer o escribir el contexto de otro hilo, el servidor lo detiene con SIGUSR1. La consola no tiene señales dirigidas a un hilo (W064, `ptrace.c` falla con `PWBOOT thread_signal unavailable`). El pedido quedaba en `STATUS_PENDING` y `GetThreadContext`/`SetThreadContext` esperaban para siempre.
  - Pale Moon lo hace desde su monitor de cuelgues con un lock tomado, así que su interfaz se congelaba (W184, W185).
- **Ahora:** en `stop_thread`, si la señal no se pudo enviar, el contexto pendiente se descarta igual que para un hilo que terminó (`cleanup_thread`). `get_thread_context` y `set_thread_context` sobre otro hilo devuelven `STATUS_UNSUCCESSFUL` en el momento.
- **Lo que no cambia:** `SuspendThread`. El hilo se detiene en su próxima llamada al servidor, como antes.
- Compila sin advertencias.

## Qué se espera

- Pale Moon no se congela.
- Navegar con `example.com` + Enter: en el log, `PWNET resolve name=example.com`. Además debería crearse `C:\orbis\palemoon-net.log` (las preferencias de W185 siguen).

## Prueba física

Reporte: `reports/wine-hardware-w186/physical/20261104T002752Z/`. Respuesta del usuario: páginas remotas en blanco o con error.

- **Ya no se congela:** el monitor de cuelgues sigue pidiendo contextos (`thread_signal unavailable thread=0070 sig=10`, muchas veces), pero ya no aparece `RtlpWaitForCriticalSection`.
- **Entrada y DNS:** el Enter llega (`code=13`), y una búsqueda resuelve `duckduckgo.com` (`PWNET resolve … found=1`). Pale Moon además escribe en su caché.
- **Página local** (captura): se ve completa en Pale Moon, con `es5-ok`, `es2020-ok`, `canvas-ok`, scripts en 34 ms y el user agent de Pale Moon 35.0.3 en Windows 10 x64.
- **Sitios remotos:** quedan en blanco o con error. El nombre resuelve, así que el problema está después (conexión, TLS o certificados). Lo dirá el registro de red de W187.
