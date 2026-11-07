# W112: primer runtime DOS dentro de Wine

[English](HARDWARE_W112.md) | [Español](HARDWARE_W112-es.md)

APP_VER 02.11. Prioridad elegida por el usuario: juegos DOS. W111 conserva la aceptación de renombrado y borrado recursivo; escritorio y calibración absoluta de CPU/GPU siguen aplazados.

Documents/smb.exe se identificó como MZ MS-DOS/PKLITE, no PE Windows. SHA256 e58adb73373c214a0f4ae1f98fb7dde655095c338cb4121db3bd4abde6049db3. El juego no forma parte de la distribución y no se modifica por FTP.

## Implementación

DOSBox Pure de https://codeberg.org/schelling/dosbox-pure.git, revisión ba6dcaee84aa2c22d709c3dfdacb7aca5ebc3042, fijada en dos.lock.json. Núcleo PE64 con CPU normal interpretada (DISABLE_DYNAREC=1), 4720 ciclos. Se aloja mediante doshost.exe, un frontend libretro propio ejecutado como invitado PE64 del Explorer existente. Vídeo XRGB8888 por GDI, sin Vulkan. No añade instrucciones al traductor WoW64 ni cambios al emulador.

WFM conserva su broker WM_COPYDATA: Explorer clasifica .exe MZ y .com, preservando PE y los formatos Windows NE/LE/LX. Para DOS abre doshost.exe con la ruta como argumento entre comillas, sobre el hilo de apertura de Explorer. FindWindow y un mutex impiden dos anfitriones DOS simultáneos. Los EXE Windows y las asociaciones de texto siguen por ShellExecute habitual.

El frontend recibe teclado y eventos del mando ya traducidos por Wine: flechas/D-pad, Enter/triángulo, Escape/cuadrado, clic izquierdo/cruz=Space, clic derecho/círculo=Ctrl. No implementa ratón DOS ni interfaz de configuración. Una sola ventana DOS por vez; rendimiento y compatibilidad de juegos pendientes.

PCM estéreo llega a un puente nativo AudioOut mediante una clase privada NtQuerySystemInformation 0x50444155, ABI de 48 bytes. Token por apertura, validación de tamaño/tasa/bloques y mutex. Salida real de 256 frames a 48 kHz, con conversión sample-and-hold desde la tasa del núcleo. No crea otro worker de audio. Los errores se registran y la ventana indica «sin audio» si falla; entregar muestras al puente no demuestra que la consola emita sonido audible.

El núcleo mantiene su overlay de guardado en C:\users\orbis\AppData\Local\OrbisDesk\DOS. Persistencia pendiente de comprobar. Al cerrar la ventana se llama retro_unload_game (shutdown del núcleo) y retro_deinit antes de cerrar AudioOut. La DLL permanece cargada; los callbacks se reemplazan en la próxima apertura. Cierre/reapertura requieren prueba física.

Licencia GPL-2.0-or-later: licencia y fuentes correspondientes del núcleo, frontend, puente de audio y receta viajan en system32 junto con el runtime: DOSBox-Pure-LICENSE.txt, DOS-runtime-README.txt y DOS-runtime-source.tar.gz.

## Construcción reproducible en WSL

```sh
python3 tools/build-dos-runtime.py
python3 tools/build-explorer-hw.py
python3 tools/build-telemetry-ps4.py
python3 tools/build-wine-hardware.py
python3 tools/upload-hardware.py --build W112 --host 192.168.68.104 --timeout 60
```

La receta usa el llvm-mingw existente en ~/vk-h0/llvm-mingw para el núcleo estático y mingw GCC para el frontend. Incluye <new> explícitamente para std::nothrow con libc++. --reuse-core permite recompilar sólo el frontend si coinciden revisión, receta y hash del núcleo previamente compilado.

Se corrigió también el guard de idempotencia del parche GPU: buscaba un comentario de una línea pero insertaba uno multilínea. Se restauró la fuente exacta probada y se verificó la biblioteca GPU con el mismo SHA256 de W111: a27136aa640b4e8da90b0ce6af9fd7bd34e6ef16f67c41a790b28e3eaf276849.

## Evidencia y aceptación

Compilados núcleo, frontend, Explorer, sistema Unix, puente AudioOut y ELF/PKG. Sin matriz local por preferencia del usuario. Esto no valida ejecución DOS. Manifiestos: out/wine-dos/manifest.json y out/wine-hardware-w112/manifest.json. Artefactos y recetas archivados en reports/wine-hardware-w112/release-w112.

Instalar W112, abrir Documents/smb.exe desde WFM y observar imagen, teclado/mando y audio. Cerrar la ventana, comprobar Start/WFM y volver a abrir el juego. Si falla, conservar el fallo: los logs PWDOS/PWDOSAUDIO separan dispatch, carga de DLL, init/load, primer frame, audio real y shutdown. Un hash de frame no confirma jugabilidad; un log de apertura de AudioOut no confirma audibilidad. Compatibilidad DOS validada en PS4: pendiente.
