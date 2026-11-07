# W193 y W194: un juego Unity con Direct3D 11 (The Lost Forest)

[English](HARDWARE_W194.md) | [Español](HARDWARE_W194-es.md)

W193: APP_VER 02.92, base W192. W194: APP_VER 02.93, base W193. El resultado de W192 está en `docs/HARDWARE_W192.md`.

## El juego

**The Lost Forest** (elifyener, licencia MIT): un plataformas 2D hecho con Unity 2020.3.3f1.
- Se bajó con permiso del usuario desde itch.io: `WindowsBuild.zip`, 25 525 677 bytes, SHA-256 `37c7b937282efa9c526a6fd6b7fc01d808a6079391efc6e1ad849673270b081b`.
- Está en `.deps/games/lostforest/`. No se empaqueta.
- El exe y `UnityPlayer.dll` son x86-64.
- Se copió por FTP a `C:\users\orbis\Documents\TheLostForest` (165 archivos).

## Cambios

- **W193, `tools/build-wine-hardware.py`:** `winhttp.dll` y `avrt.dll`, del árbol de Wine del host y sin revisar, van a `lib/wine/x86_64-windows` y `system32`. `UnityPlayer.dll` importa winhttp, y Unity carga avrt para sus hilos de audio.
- **W194:** se suma `jsproxy.dll`, que importa winhttp. Ahora se calculó el cierre completo de importaciones del juego contra el runtime de W193, y era la única que faltaba.

## Pruebas físicas

**W192:** `UnityPlayer.dll` no carga (`Library WINHTTP.dll … not found`).

**W193:** `WINHTTP.dll` no carga (`Library jsproxy.dll … not found`).

**W194:** reporte `reports/wine-hardware-w194/physical/20261104T104654Z/`. Respuesta del usuario: "Falla".
- **Lo que anduvo:**
  - el juego carga como invitado dentro de explorer, con `PWGUEST load_end … error=0`;
  - carga Mono (`mono-2.0-bdwgc.dll`);
  - DXVK crea el dispositivo con `Using feature level D3D_FEATURE_LEVEL_11_1`;
  - se abre la salida de audio (`PWAUDIO level`, sin sonido: peak=0).
- **Lo que falla:** no se crea ninguna cadena de presentación (no hay `PWDXGI`) y la ventana no se muestra.
  - Desde poco después de cargar, el servidor pide detener el hilo `004c` con SIGUSR1: `PWBOOT thread_signal unavailable thread=004c sig=10`, unas 17 800 veces.
  - Desde W186, cuando la señal no se puede mandar, el pedido de contexto falla, pero el pedido se repite sin fin.
  - Mono detiene los hilos (SuspendThread y GetThreadContext) para su recolector de basura y para su propio control de hilos. Sin la señal no lo logra, y el arranque no avanza.
- **La segunda apertura del juego:** el usuario lo abrió una segunda vez. Esa segunda instancia en el mismo proceso arrancó el manejador de fallas de Unity (`UnityCrashHandler64.exe`).

## Causa y lo que haría falta

La consola no tiene `tkill` ni `thr_kill2` (W064). En cambio `pthread_kill` de libkernel sí manda una señal a un hilo concreto: `pw_wine_signals.c` ya la usa para el hilo propio.

Para que GetThreadContext de otro hilo funcione dentro del proceso hace falta:
- un registro de TID nativo a `pthread_t`, actualizado al crear y terminar hilos;
- que el servidor mande SIGUSR1 con `pthread_kill`;
- diferir la suspensión mientras el hilo tiene locks del lado Unix de Wine.


Es probable que sea también la causa de que Pale Moon congele el escritorio cuando corre como invitado (W192, `palemooncopy.exe`): W184/W185 ya mostraban que su monitor de cuelgues usa contextos de otros hilos. No está comprobado.

## Pendiente

- La suspensión de hilos con `pthread_kill` (lo de arriba).
- Después, otra vez The Lost Forest: menú, entrada, sonido y vuelta al escritorio.
