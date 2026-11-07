# W209: la salida por fallo de un invitado termina y el siguiente arranque limpia lo que quedó (borrador)

[English](HARDWARE_W209-invitado-salida-borrador.md) | [Español](HARDWARE_W209-invitado-salida-borrador-es.md)

Borrador de la sesión lateral del navegador, para unir a `HARDWARE_W209.md`. Nada de esto se probó en la consola.

## Qué pasó en W208

Reporte: `reports/wine-hardware-w208/physical/20261104T152601Z/run-0001.log`. El usuario dijo: "se cerró sólo Pale Moon esta vez".

- **La red de seguridad de W208 funciona.** En la línea 7106 aparece `PWGUEST unhandled exception c0000005 … the guest ends`, y el escritorio sigue.
- **Pero la salida no termina:**
  - termina los otros 42 hilos (línea 7113) y no registra nada más;
  - al destruir las ventanas del hilo que falló, `DestroyWindow` mandó `WM_DESTROY` al procedimiento de ventana de Pale Moon, en `xul.dll` (`WTSUnRegisterSessionNotification`, TaskbarList);
  - ese código, con sus otros hilos terminados, nunca volvió.
  
  No se descargó nada.
- **El siguiente arranque** (línea 7216) encontró `xul.dll` y el resto ya cargados. W208 sólo contaba como propios los módulos cargados desde el arranque del invitado, así que no tuvo ninguno (`own_modules … count=0`).
- **The Lost Forest:** los hilos de `UnityCrashHandler64.exe`, otro invitado todavía vivo, frenan la descarga (`kept (threads in their code)`, líneas 5331 a 5334). Es lo esperado.

## Cambio

`tools/build-guest-hw.py`, con `guest-exit-w209.patch.py`:

1. **Ventanas sin el código del programa:** cada ventana del invitado, y sus hijas, pasa a `DefWindowProc` antes de destruirla. Así no se llama al código del programa, como cuando Windows destruye las ventanas de un proceso que terminó.
2. **Sin `DllMain` después de `TerminateProcess`:** un invitado que termina con `TerminateProcess` queda marcado. Eso incluye su propio `TerminateProcess`, el de un fallo y el de la excepción no manejada de W208. Sus módulos se descargan sin `DllMain(DETACH)`, que Windows no llama cuando se termina un proceso; `ExitProcess` lo sigue llamando. Se registra `PWGUEST own_modules … detach skipped (terminated)`.
3. **Qué módulos son propios del invitado:** los que cumplen las tres condiciones:
   - están fuera del directorio de Windows;
   - no estaban en el proceso antes de su primer invitado;
   - no están en la carpeta de otro invitado que sigue corriendo.
   
   Hay una lista de invitados vivos. Si un invitado termina sin descargarlos, quedan para el siguiente.
4. **Limpieza al arrancar:** antes de cargar un invitado, se descargan los módulos que dejaron invitados ya terminados, también sin `DllMain` (`PWGUEST own_modules … leftovers=1`). Si un hilo todavía está en ese código, se quedan.

`C:\orbis\noguestunload.txt` sigue dejando todo sólo en trazas.

## Construcción

1. `python3 tools/build-guest-hw.py`.
2. `tools/link-wine-boot.py`.
3. `tools/build-wine-hardware.py`.

## Prueba física

1. Abrir Pale Moon, ir a YouTube con una segunda pestaña hasta que se cierre.
2. Volver a abrirlo sin reiniciar.
3. Cerrarlo normalmente y abrirlo otra vez.
4. **Qué buscar en el log:**
   - después del fallo:
     - `other threads ended, N windows of this thread destroyed`;
     - `own_modules … terminated=1`;
     - `detach skipped (terminated)`;
     - `PWGUEST unloaded xul.dll … gone=1`;
     - `PWGUEST memory … bytes=…`;
   - en cada `load_begin`, un `available=` parecido al anterior;
   - si quedó algo de una salida anterior, `own_modules … leftovers=1` al arrancar.

## No verificado

- Nada se probó en la consola.
- Las revisiones se aplicaron sobre copias de los fuentes, y `kernelbase` (`process.c`, `debug.c`, `memory.c`, `file.c`) pasa `-fsyntax-only` con mingw. El builder no se corrió.
- Un invitado cuya salida queda trabada sigue en la lista de vivos, y sus módulos no se limpian hasta reiniciar.
- Los hooks globales, temporizadores del thread pool y objetos COM de los módulos descargados no se quitan.
