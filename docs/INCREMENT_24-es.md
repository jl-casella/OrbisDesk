# Incremento 24: UI de Wine en pantalla, con win32u y un driver de usuario en proceso

[English](INCREMENT_24.md) | [Español](INCREMENT_24-es.md)

**En el fork Linux de shadPS4, programas Win32 con ventanas corren mediante Wine y se presentan por `sceVideoOut`.** Dos programas:

- un fixture propio de 64 bits: abre su ventana, la pinta, comprueba su pixel, escribe un `result.txt` idéntico al de Windows nativo y sale con 0, en tres de tres corridas;
- **`explorer.exe /desktop=shell,800x600`, el escritorio de Wine**, que dibuja su barra de tareas con el botón de inicio.

Todavía no hay texto (no hay fuentes) ni entrada. Hardware: pendiente.

| Fijación `gui-window64.exe` | `explorer.exe /desktop` |
|---|---|
| `reports/increment24/evidence/gui-window64.png` | `reports/increment24/evidence/explorer-desktop.png` |

Las imágenes son los cuadros que Wine entregó al sink de presentación, guardados por el propio sink dentro del emulador. No son capturas de la ventana del host.

## Cómo llega una ventana a la pantalla

1. **win32u para Orbis** (`tools/build-win32u-ps4.py`).
   - Compila las 47 unidades de la parte Unix de `win32u`, cada una con su receta exacta del Makefile de Wine para Orbis.
   - Usa un overlay propio con dos parches de prospero-win (LGPL), adaptados:
     - 0400: el driver de usuario en proceso, `ps5drv.c`;
     - 0410: métricas sin fuentes y escritorio creado por el servidor.
   - Ese driver informa un monitor virtual de 800×600, da a cada ventana una superficie de 32 bpp, compone las ventanas visibles en un buffer de pantalla y lo entrega a `pw_wine_present()`.
   - La adaptación lo habilita con `__ORBIS__` y enlaza el sink directo, porque no hay `dlsym` del título.
   - Las cabeceras generadas desde IDL vienen del árbol de Wine del host (`-idirafter`): son independientes de la plataforma.
2. **Enlace en el ELF único**. Los objetos de `win32u` se combinan en uno solo y sus símbolos ocultos quedan locales, como dentro de su propio `win32u.so`. Su `__wine_unix_lib_init` se registra en la tabla estática de libs Unix (`pw_wine_unixlibs.c`), que ahora admite también punteros de inicialización: se llaman una vez por proceso, como el constructor de un `.so`.
3. **Sink de presentación** (`platform/ps4/pw_wine_sink_ps4.c`).
   - Escala y centra cada cuadro en uno de dos buffers lineales de 1280×720 en memoria directa, registrados en `sceVideoOut`, y hace `sceVideoOutSubmitFlip`.
   - Registra el hash de cada cuadro y guarda en `/data/frames` cada cuadro con contenido nuevo (hasta 24) como BMP, para poder verificar fuera del emulador.
   - `pw_wine_next_input` todavía no tiene fuente de eventos.
4. **Clausura PE64 de la UI** (`tools/stage-wine-gui.py`).
   - Copia del árbol de Wine del host (sin parches) los 52 módulos que importan el fixture y `explorer.exe`, directa o transitivamente.
   - Los PE de Wine compilados con mingw resuelven sus `DELAYIMPORTS` en ejecución, sin directorio de delay-import; para esos se lee el `Makefile.in`.
   - `bcrypt`, `hid` y `msacm32` no están compilados en ese árbol y quedan registrados como no resueltos.
5. **Boot y runner**.
   - `--wine-exe` y `--wine-arg` eligen el programa dentro del prefijo preparado.
   - `--wine-gui` copia la clausura verificada por hash y pone el fixture en `C:\orbis`.
   - El informe de cada corrida trae los cuadros presentados, los BMP y cuántos píxeles tienen el color del fixture.

El código PE de 64 bits corre nativo en el host, así que esta UI no usa el traductor. Los programas de 32 bits siguen pasando por wowprospero, como en el incremento 23.

## Correcciones que hicieron falta

- **Escritura en secciones de imagen mapeadas de archivo** (overlay de Wine). El fork conserva la política que mapea sin escritura un archivo abierto sólo lectura, aunque el mapping sea privado; el incremento 21 dejó la ampliación por `mprotect` como camino probado. Wine escribe las relocaciones directo en sus secciones copy-on-write, así que la relocación de `shcore.dll` fallaba en la única sección que se mapeó del archivo. En `map_file_into_view`, un mapping privado con escritura hace ahora ese `mprotect` explícito. Si falla, se registra `PWBOOT private_file_write_blocked`.
- **`getrusage` (fork 0017)** era un stub que `explorer` invocaba. En amd64, `struct rusage` tiene el mismo layout en FreeBSD y Linux, así que se mapean `RUSAGE_SELF`, `RUSAGE_CHILDREN` y `RUSAGE_THREAD` a la llamada del host. Un destino desconocido devuelve EINVAL, un buffer nulo EFAULT, y otros hosts ENOSYS.
- **Referencia de Windows del fixture**. El fixture fija el tamaño del área cliente con `AdjustWindowRect` (464×280), porque los bordes dependen del tema. Windows 11 nativo da `painted=1;pixel=8c3c14;client=464x280` y sale con 0 (`reports/increment24-windows-reference/`).

## Resultado

| Corrida | Resultado |
|---|---|
| `gui-window64.exe`, tenedor | **passed** 3 de 3: `result.txt` idéntico a Windows, salida 0; un cuadro presentado tiene exactamente 464×280 píxeles del color del área cliente |
|`gui-window64.exe`, shadPS4 oficial|bloqueado|
| `explorer.exe /desktop=shell,800x600`, tenedor | El escritorio se presenta con su barra de tareas (más de 15.000 píxeles del color de la barra en el último cuadro), sin stubs ni violaciones de acceso. Corre hasta el timeout del runner, como corresponde a un escritorio. |

`explorer.exe C:\` (navegador de carpetas) arranca, carga `shell32` y `comctl32` y dibuja, pero se cae: sin procesos no hay `rpcss` ni administrador de servicios, y el prefijo del incremento 15 no registró las clases COM del panel de navegación porque se inicializó con una clausura mínima. Queda como trabajo siguiente.

## Validación

`tools/check-increment24.py` exigencia:

- las tres corridas del fixture contra la referencia de Windows y el cuadro con el área cliente completa;
- la barra de tareas en el último cuadro de `explorer` y ningún stub;
- que `console32-bare.exe` mediante Wine (incremento 23) siga pasando;
- el control sin proveedor WoW64;
- GS, las 7 señales, `wine-memory` (ahora 12 comprobaciones, con `getrusage`), `segments`, `services`, el preflight y el prefijo vacío;
- `exceptions` con su detalle conocido;
- los contratos de mmap y file mapping, y la matriz del incremento 18.

Exporta a PNG los cuadros de evidencia. `fork.lock.json` fija el commit `9ac99bb` con los parches 0001 a 0017.

## Reproducción

Con las herramientas del incremento 25, construir primero FreeType mediante `python3 tools/build-freetype-ps4.py` antes de `build-win32u-ps4.py`. La ausencia de texto descrita arriba corresponde a la evidencia histórica del 24.

En Ubuntu 22.04/WSL, en este orden:

```sh
python3 tools/build-shad-linux.py --reuse-configure --jobs 12
python3 tools/build.py --with-wine-platform
python3 tools/prepare-wine-boot.py
python3 tools/build-wine-ps4.py --boot --all-unix
python3 tools/build-wine-ps4.py --boot --server
python3 tools/build-wowprospero-ps4.py
python3 tools/build-win32u-ps4.py
python3 tools/stage-wine-gui.py
python3 tools/link-wine-boot.py
python3 tools/run-linux-wine.py --fork --prepared-prefix reports/increment15/prefix-package --wine-gui --wine-exe 'C:\orbis\gui-window64.exe'
python3 tools/run-linux-wine.py --fork --prepared-prefix reports/increment15/prefix-package --wine-gui --wine-exe 'C:\windows\explorer.exe' --wine-arg /desktop=shell,800x600
python3 tools/check-increment24.py
python3 tools/check-increment24.py --verify-only
```

## Qué no está probado y próximo hito

- **Texto**. Wine para Orbis se compila sin FreeType, así que no dibuja glifos: ni títulos ni etiquetas. El siguiente paso es FreeType para Orbis y fuentes en el runtime.
- **Entrada**. Ningún origen alimenta `pw_wine_next_input`. Habría que llevar el mando (y teclado y ratón donde existan) al driver, como hace prospero-win en PS5.
- **Navegador de carpetas de `explorer`**. Necesita un prefijo inicializado con el conjunto completo de DLL (registros COM) y una política para `rpcss` sin procesos separados.
- shadPS4 oficial, el host Windows del fork y el hardware PS4.
