# Procesos de Windows separados (fases B–D de PoP)

[English](POP_SEPARATE_PROCESS.md) | [Español](POP_SEPARATE_PROCESS-es.md)

OrbisDesk corre todos los programas de Windows dentro de un único proceso del título de PS4. Ese modelo falla con un launcher y un juego que necesitan la misma base de imagen fija. El launcher de Prince of Persia y `POP.exe` usan los dos `0x400000`. Este documento registra cómo un programa marcado **Separate processes** en winecfg ahora corre en un segundo proceso nativo. Ese proceso ejecuta Wine como cliente del wineserver del título, con el escritorio, el registro y el espacio de nombres de objetos del título.

El sustrato de investigación (fase A, el loader de GoldHEN y su arreglo del planificador) está en [Sondas de familias de procesos](PROCESS_FAMILY_PROBES-es.md). OrbisDesk apunta a consolas con GoldHEN, así que el loader residente es un requisito declarado y no un bloqueo. Igual hay que reenviarlo después de cada reinicio de la consola.

## Qué funciona en hardware (PS4 Pro, 12.50, arranque ROOT, 2026-11-12)

| Fase | Resultado | Evidencia (`reports/pop-phase-b/physical/`) |
| --- | --- | --- |
| B.1 | Un proceso lanzado por el loader se conecta al wineserver del título, se registra (versión 961) y crea `\KernelObjects\OrbisSeparateJoin` en el espacio de nombres compartido | `20261112T032514Z` |
| C | Ese proceso crea una ventana en el escritorio del título con pedidos directos al wineserver. Recibe el mouse, y el título compone sus píxeles | `20261112T085655Z` |
| D.1 | Wine corre en ese proceso. Un programa de consola PE64 enlazado en `0x400000` carga ahí sin reubicarse y sale con 42. Tres arranques seguidos del título son estables | `20261112T130124Z` |
| D.2 | La ventana de un programa GDI aparece en el escritorio. Recibe clicks, teclas y arrastre, y el escritorio sigue abierto cuando el programa termina | `20261112T132927Z` |
| D.3 | `separate_launcher.exe` corre dentro del título en `0x400000`. Llama a `CreateProcess` sobre `separate_game.exe`, marcado separado y también enlazado en `0x400000`, y el juego corre en el segundo proceso. El launcher recibe handles reales y el código de salida 44 del juego. El juego recibe 8 clicks y 11 teclas | `20261112T141146Z`, `20261112T150746Z` |

Estos resultados cubren solo las configuraciones nombradas acá. No prueban compatibilidad general de aplicaciones. El proceso separado no tiene GPU propia (ver *Límites*).

## Cómo fluye un lanzamiento

1. **kernelbase.** `CreateProcessInternalW` ve el modo de ejecución `separate` para la imagen. Su generador es `tools/build-guest-hw.py`. Escribe `/data/orbisdesk/process-p014/spawn-request` con cuatro líneas: un token, la imagen, la línea de comandos y el directorio actual. Después espera hasta 30 s a `started-<token>`.
2. **Vigía del título.** `native/pop_loader_spawn.h` convierte el pedido en el trabajo del hijo. Después manda `/data/orbisdesk/pop-wine-join.elf` al loader residente por el puerto 9021.
3. **Hijo del payload SDK.** `native/process_p014_child.c` adopta el uid del título y carga `pop-wine-child.prx` con `dlopen`, así el linker del sistema resuelve sus imports, el TLS y los inicializadores. Se conecta al socket puente del título y llama a `pop_wine_child_run_job`.
4. **PRX de Wine.** `native/pop_wine_child.c` pone en `WINESERVERSOCKET` el descriptor del puente y llama a `__wine_main`. Así ntdll se une al servidor del título en vez de iniciar uno. Ya unido, el proceso escribe `pid tid` bajo el token, y kernelbase abre handles reales de proceso y de hilo para quien lo llamó.
5. **Pantalla.** El driver de win32u del hijo le pasa su pila de ventanas a `native/pop_child_sink.c`, que nunca abre VideoOut. El sink manda la ventana de arriba y su handle por `surface.sock`. El título compone el cuadro en el rectángulo de la ventana. Un puntero sobre ese rectángulo se entrega a esa ventana por su handle (`pw_hw_separate_window`, `tools/build-win32u-ps4.py`).

## Qué necesitó el PRX de Wine en esta consola

Cada punto se encontró en hardware. El comentario junto al código da la corrida y el motivo.

- **Carga.** El loader solo copia una imagen: sin imports, sin TLS, sin inicializadores. Por eso Wine es un PRX con firma falsa cargado con `dlopen`. `__init_libc` de musl se llama a mano, porque un PRX nunca ejecuta `crt1`.
- **Base fija.** El proceso de sistema prestado tiene su eboot en `0x400000–0x588000`. Ese código no vuelve a correr, y sus regiones se liberan antes de que arranque Wine.
- **Página compartida.** Con páginas de 16 KiB, el lugar del despachador de syscalls de ntdll (`0x7ffe1000`) comparte página del host con la vista compartida de `KUSER_SHARED_DATA`. Un segundo proceso pisaba el despachador del título, y explorer saltaba al ntdll del otro proceso. En el proceso separado esa página es privada y se refresca desde la vista compartida cada 15 ms.
- **Vida del escritorio.** El servidor cierra un escritorio cuando solo quedan los hilos de su dueño. El proceso separado se vuelve proceso de *sistema* de Wine apenas se une, así su salida deja abierto el escritorio del título.
- **Nombre del escritorio.** `ProcessParameters->Desktop` se pone en `WinSta0\shell` antes de que ntdll copie los parámetros para una imagen de 32 bits. Así todo programa cae en el escritorio del título.
- **PE32.** La CPU es `wow64native.dll` con `PW_NATIVE_SIGNALS=1`, como en el título.
- **Esperas.** Usan el `poll` del kernel en vez de un `sceNetEpoll` por llamada. Es una precaución: el título abortó al arrancar dentro de `sceNetEpollControl` después de sesiones con el hijo, hasta reiniciar. La causa no se probó.
- **Salida del proceso.** Una aserción termina el proceso con `_exit`. Wine atiende `SIGABRT`, y los hijos que fallaban una aserción quedaban colgados.

## Compilar y desplegar

```sh
python3 tools/build-wine-hardware.py --runtime-outside-package   # el título (su comando de enlace alimenta el PRX)
python3 tools/build-pop-wine-child.py                            # PRX, sonda, hijo, programas de prueba + manifiesto
python3 tools/upload-hardware.py --build W303 --host IP_CONSOLA --port 2121 --skip-runtime
python3 tools/upload-pop-separate.py --host IP_CONSOLA
```

`tools/build-guest-hw.py` y `tools/build-winecfg-hw.py` producen el kernelbase y el winecfg que el título prepara. Si esos cambian, también hay que actualizar sus copias del runtime bajo `/data/wine` y del prefijo. `/data/wine` pertenece al uid del título con modo 755. El FTP igual puede cambiar modos, así que conviene abrir un directorio solo para la subida y devolverle su modo después.

Acá importan dos comportamientos del FTP de GoldHEN. Sobrescribir un PRX en su lugar dejaba cargado el anterior, así que hay que borrarlo antes de guardar el nuevo. `RETR` de un SELF/PRX devuelve el ELF descifrado, así que se verifica por contenido y no por hash. `tools/upload-pop-separate.py` hace las dos cosas. La autoprueba del arranque corre solo si existe `/data/orbisdesk/process-p014/selftest`.

## Límites

- **Todavía sin Direct3D.** RADV/GNM y VideoOut son del título. Un programa Direct3D o Vulkan en el proceso separado no puede dibujar. Por eso Prince of Persia todavía necesita un camino de gráficos: acceso a la GPU en el segundo proceso, o cuadros enviados al título.
- **Una ventana, siempre arriba.** Solo se muestra la ventana de arriba del proceso separado, y se dibuja sobre todas las del título. No se manejan el orden respecto del título, varias ventanas ni las formas del cursor.
- **Cursor viejo en el hijo.** Dentro del proceso separado, `GetCursorPos` puede devolver un punto viejo. Eso afecta a menús y arrastres que maneja el propio programa.
- **Señales y suspensión.** El servidor no puede enviar señales a los hilos de un proceso separado ni suspenderlos (`pw_wine_thread_kill` solo alcanza los hilos del propio título).
- **Loader de GoldHEN.** Hay que reenviar el loader residente después de cada reinicio de la consola.

La historia de desarrollo está en los comentarios junto a cada cambio y en `native/pop_separate.h` (`P014`–`P019`).
