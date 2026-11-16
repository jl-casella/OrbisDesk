# MangoJuice: el programa de ajustes de MangoHud

[English](MANGOJUICE.md) | [Español](MANGOJUICE-es.md)

MangoJuice (`C:\Program Files\MangoJuice\bin\mangojuice.exe`) permite al usuario cambiar las opciones del HUD sin editar `MangoHud.conf` a mano. Lo abre **Graphics Tools > MangoJuice**, con el icono propio de MangoJuice, y reemplaza al antiguo elemento **MangoHud Config**, que abría el archivo en el Bloc de notas. El programa es MangoJuice-Windows, `https://github.com/Leclowndu93150/mangojuice-Windows.git` @ `e2ec0755`, GPL-3.0.

## Decisión

[G001](HARDWARE_G001-es.md) dejó fuera MangoJuice: es una aplicación Vala sobre GTK4, libadwaita-1 y libgee sin releases, y compilarla requiere la pila GTK4 para Windows y `valac`. Una primera versión de este trabajo recomendó en su lugar un formulario Win32 nativo pequeño. Era más pequeño (70 KiB frente a 52 MiB) y cubría solo las 12 claves que lee OrbisDesk. El usuario eligió MangoJuice, así que ese formulario se quitó antes de publicarlo. El coste de esta vía queda detallado abajo, para poder revisarla con evidencia.

## Cómo se compila

[build-mangojuice-hw.py](../tools/build-mangojuice-hw.py) se ejecuta en WSL Ubuntu-22.04. Cada entrada está fijada por SHA-256 en [mangojuice.lock.json](../mangojuice.lock.json):

| Entrada | Por qué |
| --- | --- |
| Fuente de MangoJuice en el commit de `dependencies.lock.json` | El programa. Debe estar en ese commit y sin cambios. |
| 84 paquetes **ucrt64** de MSYS2: libadwaita y libgee con su cierre completo de dependencias (gtk4 4.24.1, libadwaita 1.10.0, glib2 2.90.1, libgee 0.20.8, …) | Cabeceras, bibliotecas de importación, DLL, esquemas, iconos y textos de licencia. El repositorio mingw64, más antiguo, ya no tiene gtk4 ni libadwaita. |
| `vala` 0.56.19 de MSYS2 | Solo sus vapis. El valac 0.56.0 de Ubuntu trae un `gtk4.vapi` de GTK 4.6, y MangoJuice usa API de GTK 4.10+ (`ColorDialogButton`, `FileDialog`). |
| .deb de Ubuntu: `valac`, `valac-bin`, `libvala-0.56-0`, `libvalacodegen-0.56-0`, `zstd`, `librsvg2-bin` | Herramientas del host, desempaquetadas sin instalar: Vala a C, extracción de `.pkg.tar.zst` y el icono. |
| llvm-mingw 20260922 (UCRT), de `dependencies.lock.json` | Las DLL de MSYS2 usan la UCRT. El gcc 10 de MinGW de la distribución enlaza msvcrt. |

Pasos:

1. `--fetch` descarga lo que falte en `.deps/mangojuice`, y el builder verifica cada hash.
2. Los paquetes de MSYS2 se desempaquetan en `build/mangojuice-hw/sysroot`, alrededor de 1 GiB, que se borra al terminar salvo con `--keep-work`. Vala genera el C.
3. llvm-mingw lo compila y lo enlaza dos veces. Los dos enlaces deben ser idénticos.
4. El cierre de DLL del programa se copia del árbol de MSYS2, junto con los esquemas GSettings de GTK (compilados en el host), los temas de iconos Adwaita y hicolor, los iconos propios de MangoJuice y los textos de licencia.
5. El `.ico` (16, 32 y 48 px) se genera desde el SVG de MangoJuice con `rsvg-convert`.

`--lock` vuelve a resolver los pines desde la base de datos actual de MSYS2. MSYS2 acaba retirando las versiones antiguas, así que un lock de esta antigüedad puede necesitar resolverse de nuevo, seguido de una nueva compilación y nuevas pruebas. `ORBISDESK_DEPS` hace que un worktree use el `.deps` del checkout principal.

A MangoJuice se le aplican dos revisiones, y ambas quedan registradas en el manifiesto:

- `main()` fija `GSK_RENDERER=cairo` y `GDK_DISABLE=gl,vulkan` si el usuario no las fijó. El título no tiene GL para GTK y su Vulkan es de los juegos, así que GTK dibuja la ventana por software.
- `main()` también fija `PANGOCAIRO_BACKEND=fontconfig` y carga un poco de CSS que quita la sombra y las esquinas redondeadas de los popovers y los tooltips (ver «Dibujo en la consola» más abajo).
- Se quita la página **Games**. Lanza un `MangoHud.exe` independiente sobre un juego en marcha y registra la capa en HKLM mediante `reg.exe`. OrbisDesk ya carga MangoHud como capa implícita y no incluye `MangoHud.exe`.

El manifiesto `requireAdministrator` de upstream no se enlaza.

`build-wine-hardware.py`:

- comprueba el manifiesto contra el builder y el lock;
- copia `out/mangojuice-hw/MangoJuice` a `C:\Program Files\MangoJuice`, carpeta que el strip de depuración no toca, igual que hace con VLC;
- falla si alguna DLL de Windows que importa el programa, directamente o a través de otra DLL de Wine, no está en system32 una vez terminado el prefijo (las `api-ms-win-*` se resuelven mediante el apiset);
- borra de la consola el antiguo `Graphics Tools\MangoHud Config.lnk`.

`tools/ci/build-product.py` ejecuta el builder con `--fetch`, y la fuente de MangoJuice ahora se restaura en CI.

### DirectWrite

`libharfbuzz-0.dll` y `libpangowin32-1.0-0.dll` de MSYS2 importan `DWrite.dll`, que OrbisDesk no incluía. En la consola (paquete combinado W303, run-0060) MangoJuice no se abrió: no se encontró DWrite.dll, y después fallaron en cadena harfbuzz, freetype, fontconfig, cairo y GTK. Ahora se incluye el dwrite del propio Wine:

- [stage-wine-extras.py](../tools/stage-wine-extras.py) copia `dwrite.dll` para las dos vistas desde la build de Wine del host fijada, sin parches. `build-wine-hardware.py` lo pone en las carpetas builtin y en system32/syswow64, y lo mantiene ahí: `W261_LEFT_OUT` de `stage-wine-i386.py` lista dwrite, que se había dejado fuera porque no tenía lado Unix (SeaMonkey dibujaba páginas sin texto y el Qt de VLC se cerraba). Con solo la copia de la carpeta builtin seguía fallando (run-0061). Ahora que dwrite tiene su lado Unix, SeaMonkey y VLC vuelven a usar DirectWrite y hay que probarlos de nuevo.
- dwrite dibuja los glifos con FreeType en su lado Unix, `dwrite.so`. El título no tiene cargador dinámico. [build-unixlibs-ps4.py](../tools/build-unixlibs-ps4.py) compila sin cambios `dlls/dwrite/freetype.c` de Wine, con su `dlopen`/`dlsym` renombrados a [pw_dwrite_unix.c](../platform/ps4/pw_dwrite_unix.c). Ese archivo responde con el FreeType que win32u ya enlaza en el ELF de arranque, y [pw_wine_unixlibs.c](../platform/ps4/pw_wine_unixlibs.c) registra `dwrite.so`.

El resto del cierre, 64 DLL, estaba en W303. El `usp10.dll` de 8 KiB es el reenviador de Wine a gdi32, no un stub. El lado Unix compila con la toolchain de la consola, y sus únicos símbolos sin definir son las 28 funciones de FreeType, que define `build/freetype-ps4`, más la salida de depuración de ntdll y libc. Necesita un ELF de arranque nuevo (`build-unixlibs-ps4.py` y después `link-wine-boot.py`); no se enlazó ni se ejecutó.

### Dibujo en la consola

En run-0062 MangoJuice se abrió, pero a su texto le faltaban trazos y letras enteras («GPU» se leía «GP»), y el menú «…» aparecía dentro de un rectángulo negro.

- **Texto.** El backend Windows de Pango 1.58 enumera las fuentes con DirectWrite, y pangocairo las dibuja con las caras de fuente DirectWrite de cairo, así que cada glifo pasaba por el dwrite de Wine y su nuevo lado Unix con FreeType en la consola. En ese camino se perdían los trazos; no se aisló en qué paso exactamente. pangocairo tiene un segundo backend: `PANGOCAIRO_BACKEND=fontconfig` usa fontconfig y el FreeType propio de MSYS2 dentro del proceso, como hacen GIMP e Inkscape en Windows. El `etc/fonts` de MSYS2 (fonts.conf y conf.d) se incluye junto a `bin`, donde fontconfig lo busca. Recorre `C:\windows\Fonts` y guarda su caché en `%LOCALAPPDATA%\fontconfig`. La consola solo tiene ahí Tahoma y Marlett, así que un `local.conf` generado hace que Tahoma sea la elegida para sans-serif, serif, monospace, system-ui, Adwaita Sans, Cantarell y Segoe UI.
- **Popovers negros.** GTK dibuja los popovers y los tooltips como ventanas aparte con un margen de sombra transparente. Sin DirectComposition, que es opcional (`GDK_DEBUG=dcomp`) y necesitaría Direct3D 11, pide la transparencia a DWM con `DwmEnableBlurBehindWindow`. Wine no compone el canal alfa, así que ese margen salía negro. Un CSS con prioridad de usuario (`window, window.csd, window.background, popover, popover > contents, popover > arrow, tooltip { box-shadow: none; border-radius: 0; } popover > contents { margin: 0; }`) no deja píxeles transparentes alrededor de la sombra. Aun así quedaban dos franjas transparentes:
  - La ventana principal tenía un marco negro hasta maximizarla (run-0064). El CSS solo no lo quitó (run-0066), porque una ventana con decoración del lado del cliente conserva un margen tan ancho como los bordes de redimensionado de GTK. Ahora ninguna ventana tiene decoración (`set_decorated (false)` en `window_added`); libadwaita dibuja su propia barra de título y sus botones dentro de la ventana.
  - Los popovers conservaban la franja de su flecha. El menú principal, el popover de fuentes y el de la ayuda de presets no tienen flecha.

El escritorio es de 1280×720 escalado al televisor, así que MangoJuice nunca se verá ahí tan nítido como en un PC.

### El botón de prueba

El fork de Windows desactiva vkcube y glxgears por ser herramientas de Linux. Cada arranque mostraba un aviso «vkcube and glxgears not found», y el botón de prueba solo se aseguraba de que existiera `MangoHud.conf`. OrbisDesk incluye los dos programas en `C:\orbis` (Inicio > Graphics Tools, [make-start-menu.py](../tools/make-start-menu.py)). Cada uno figura como disponible cuando existe su archivo, y el botón de prueba abre vkcube, o glxgears si falta vkcube, con `WinExec`, como guest con MangoHud encima. No se lleva la cuenta de si ya hay uno abierto, así que guardar no lo reinicia.

### Reabrir después de cerrar

MangoJuice corre como guest dentro del proceso compartido de explorer, así que lo que dejan sus DLL lo sobrevive. Su segundo arranque fallaba hasta que se quitaron tres restos. Los tres arreglos son cambios generales del ciclo de vida de los guests en [build-guest-hw.py](../tools/build-guest-hw.py):

1. **Un hilo de GLib en su propio código** (run-0065). `guest->threads` solo registra los hilos que los hilos del guest crean con `CreateThread`, así que un hilo del threadpool que corría en `libglib` no estaba registrado, y la descarga conservaba todos los módulos del programa. Ahora los hilos que siguen corriendo en los módulos propios del guest se terminan, con el loader lock tomado, antes de descargar esos módulos.
2. **GIO fijada en memoria** (run-0076). GIO se fija a sí misma, así que `libgio` sobrevivía al programa, y con ella el tipo y la clase GApplication del primer arranque, cuyas especificaciones de propiedad apuntaban al `libgobject` ya liberado. El primer `g_object_new` del siguiente arranque saltaba ahí (c000001d en una dirección dentro de `libgraphene`, run-0075). Ahora un módulo de la carpeta del programa que el propio programa fijó se libera y se descarga con él, como pasaría al terminar su proceso; la limpieza de restos al lanzar un programa sigue sin tocar los módulos fijados.
3. **Las clases de ventana de GDK** (run-0077). Sin GIO, el segundo arranque pasaba de `g_object_new` y luego abortaba con estado 3. GDK registra `gdkSurfaceToplevel`, `GdkDisplayChange` y `GdkClipboardNotification` a nombre de la instancia de libgtk, que la pasada de clases de la descarga nunca visitaba, y libgtk se descarga con el EXE. Ahora la pasada también visita, mientras siguen cargados, los módulos de la carpeta del guest cargados después de su arranque. Se desregistra toda clase registrada a nombre de uno de ellos cuyo procedimiento esté en el código propio del guest.

Una excepción no manejada en un hilo de un guest ahora también registra el módulo y el desplazamiento de la dirección del fallo, de los registros de argumentos y de hasta 16 direcciones de retorno de la pila (`PWGUEST fault`). Así se encontró la causa 2.

## Resultado de esta compilación

| | |
| --- | --- |
| `mangojuice.exe` | sha256 `000df9f886710b74b988f22c3acaaf0d89dca51fbb4948b1663ca625e5db8f31`, una compilación con las revisiones de ventana, popovers y botón de prueba (la de run-0062 era `b672c722…`, dos enlaces idénticos) |
| Instalado | 989 archivos, 52,2 MiB: 62 DLL (solo `libgtk-4-1.dll` ocupa 12,0 MiB), iconos 4,9 MiB |
| DLL de Windows que aporta Wine | 46, entre ellas `opengl32`, `d3d11`, `d3d12`, `dcomp`, `dwrite`, `gdiplus` y `usp10` |
| No incluida | `vulkan-1.dll` de MSYS2: la de system32 es el cargador Khronos de OrbisDesk |
| Tiempo de compilación | de 7 a 10 minutos en `/mnt/c`, la mayor parte desempaquetando el árbol de MSYS2 |

Cada DLL instalada se lee entera en memoria al cargarse, dentro del proceso compartido de explorer (W095), así que MangoJuice ocupa memoria mientras está abierto. Ese coste no se midió en la consola.

## El archivo de ajustes

MangoJuice escribe `%APPDATA%\MangoHud\MangoHud.conf`, que en la consola es `/data/wine-prefix/drive_c/users/orbis/AppData/Roaming/MangoHud/MangoHud.conf`. Cada guardado reescribe el archivo entero: empieza con `legacy_layout=false`, lista como claves sueltas las filas activadas y omite las desactivadas. Con `legacy_layout` desactivado, MangoHud muestra solo las filas que nombra el archivo (`overlay_params.cpp`, `sort_elements`). El HUD Estadisticas del overlay del título (`native/hw_overlay.c`) ahora hace lo mismo; antes partía de las filas por defecto de MangoHud. Su línea de log añade `legacy_layout=`. El overlay sigue dibujando las filas en su propio orden fijo, no en el del archivo.

El archivo del usuario sobrevive a las actualizaciones. `tools/console_state.py` lo lista en `CONSOLE_OWNED_FILES`. El uploader por FTP y el instalador del primer arranque (líneas `P` de `install.txt`, `native/hw_install.h`) lo copian solo cuando falta. Antes, cada actualización lo reemplazaba por el de la build.

### MangoHud no lo leía (2026-11-16)

MangoJuice guardaba las opciones y MangoHud dibujaba las suyas por defecto, así que desmarcar GPU, por ejemplo, no cambiaba nada en un programa Vulkan. MangoHud busca `$XDG_CONFIG_HOME`, o `$HOME/.config`, más `/MangoHud/MangoHud.conf` (`src/config.cpp` `enumerate_config_files`, `src/file_utils.cpp` `get_config_dir`). Aquí `HOME` vale `/data/wine-home` (`platform/ps4/pw_wine_platform.c`), una ruta Unix, y la capa es un PE dentro del invitado, así que ese nombre se resuelve contra la unidad actual y no existe ningún candidato. MangoHud se quedaba con sus valores por defecto: `fps`, `frametime`, `frame_timing`, `cpu_stats` y `gpu_stats`. Estadisticas, el HUD propio del overlay del título, tampoco lo encontraba, por otro motivo: miraba la ruta correcta,
pero pedía el registro del archivo con el `OrbisKernelStat` del SDK, que no coincide con el registro que devuelve el
kernel (`platform/ps4/pw_wine_platform.c` `PwOrbisStat`, W230). La hora de modificación leía los bytes equivocados y
daba 0 en todos los candidatos, así que no se elegía ninguna ruta y el HUD también caía en los valores por defecto de
MangoHud (`PWOVERLAY hud: no MangoHud.conf`, run-0150 y run-0151). Ahora lo pide con `pw_wine_stat`, que convierte ese
registro, y usa el tamaño del archivo como marca de cambio donde la consola no informa hora.

El título ahora pasa `MANGOHUD_CONFIGFILE=C:\users\orbis\AppData\Roaming\MangoHud\MangoHud.conf` junto al `MANGOHUD=1` que ya pasaba (`native/wine_hardware.c`), de modo que los dos HUD leen el archivo que escribe MangoJuice. Donde exista `C:\mangohud\MangoHud.conf`, MangoHud sigue leyendo ese primero: es su propio candidato de Windows, probado antes que la variable, y aquí nada lo escribe.

La comprobación en hardware que lo encontró: un archivo de prueba en esa ruta, con solo `fps` y `position=bottom-right`, movió el HUD de MangoHud y dejó Estadisticas donde estaba. Se borró después.

### Mostrar y ocultar desde el overlay dejó de funcionar (2026-11-16)

En cuanto MangoHud leyó el archivo de MangoJuice, mostrar y ocultar desde el overlay dejó de funcionar, tanto en programas de 32 bits como de 64. El overlay envía Shift+F12, que MangoHud lee como su F12 por defecto (`native/hw_overlay.c`, `HUD_HOLD_US`), y el log seguía mostrando que la tecla se enviaba. MangoJuice siempre escribe `toggle_hud` (`Shift_R+F12`, y una vez en la consola `Shift_L+0xffffff`). MangoHud interpreta los nombres de teclas con xkbcommon, que solo compila con X11 o Wayland. Sin ellos, como en toda build de Windows, `src/overlay_params.cpp` define `parse_toggle_hud` y los demás intérpretes de teclas rápidas como `{}`, así que una línea que nombraba una tecla rápida dejaba una lista de teclas vacía que nunca coincidía. La redefinición `_WIN32` del fork en `parse_overlay_config` viene después de las funciones que usan esos intérpretes, así que nunca se aplicaba.

[patch-mangohud-win-hotkeys.py](../tools/vk-h0/patch-mangohud-win-hotkeys.py) hace ahora que esos intérpretes conserven el valor actual: los valores por defecto de Windows, F12 para `toggle_hud`. Por lo tanto, una tecla rápida escrita en `MangoHud.conf` se ignora y se mantiene la de por defecto. [build-mangohud.sh](../tools/vk-h0/build-mangohud.sh) lo aplica, y [build-mangohud-i386.sh](../tools/vk-h0/build-mangohud-i386.sh) comprueba su marca en el árbol copiado.

Hardware, versión de la app 04.08 (run-0158): d3d9test32 se ejecutó como invitado de 32 bits con MangoHud cargado (`loaded32=1`). El overlay envió dos veces `Shift+F12 held 250 ms`, y el usuario vio cómo el HUD se ocultaba y volvía. La desaparición de la fila de GPU al desmarcarla se vio en vkcube con la 04.06. Las demás combinaciones no se comprobaron en la 04.08: la alternancia en un programa de 64 bits, la fila de GPU en un programa de 32 bits y que Estadisticas lea el archivo.

## Qué se comprobó y qué no

- El builder se ejecutó de principio a fin.
- En la consola (PS4 Pro, paquete W303 con runtimes de prueba, NORMAL/ROOT abierto por el usuario):
  - MangoJuice abre con el texto legible (desde run-0062) y sin marco negro alrededor de su ventana (desde run-0068).
  - El menú «…» no tiene borde negro, ya no aparece el aviso «not found», y el botón de prueba abrió vkcube, que arrancó y se cerró limpiamente (run-0074).
  - Se abrió, se cerró y se volvió a abrir con su ventana las dos veces, y cada arranque terminó con estado 0. En cada cierre se desregistraron las tres clases de GDK y se liberó GIO (run-0078, `reports/pop-phase-b/physical/20261113T055814Z`).
  - El usuario también informó que WFM y un juego funcionaban después de cerrar MangoJuice (run-0074). Los cambios del ciclo de vida de los guests no se comprobaron con arranques repetidos de otros programas, ni con dos guests de la misma carpeta a la vez.
- `hw_overlay.c` compila con las opciones de compilación de la propia consola (`helper_compile_flags`). En el harness de vista previa del host:
  - un archivo como los de MangoJuice (`legacy_layout=false`, `fps`, `ram`) dio `gpu=0 cpu=0 ram=1 fps=1 frametime=0 frame_timing=0`;
  - el archivo por defecto de la build siguió dando las filas por defecto.
- `native/hw_install.h`: solo comprobación de sintaxis en el host.
- Los iconos se revisaron a 16, 32 y 48 px sobre el menú oscuro (38,38,40), el menú claro (240,240,240) y el color de selección (0,120,215).
- **No se comprobó:**
  - MangoJuice de forma nativa en el PC de compilación, ni en shadPS4;
  - su uso de memoria y la navegación con el mando (tarda unos 14 s en mostrar su primera ventana en la consola, `PWSINK busy end … ms=14426`);
  - guardar ajustes y que el HUD Estadisticas los siga (`PWOVERLAY hud:`);
  - que los ajustes sobrevivan a la siguiente actualización.

## El icono de vkSpin

El icono de vkSpin era un triángulo sin fondo. Su esquina azul se perdía en el menú oscuro y en el resaltado, y su centro blanco en el menú claro. Un fallo de `tools/make-icons.py` lo empeoraba: `raster()` tomaba la transparencia de un píxel del color más frecuente entre sus submuestras. Con un degradado cada submuestra tiene un color distinto, así que el triángulo salía con alrededor de 1/16 de opacidad.

Ahora la transparencia es la cobertura, y el color es la media de las submuestras. vkSpin es ahora el mismo triángulo sobre un recuadro redondeado de amarillo a magenta, con borde oscuro y contorno blanco, y destaca en los tres fondos. Los demás iconos se ven igual o algo más limpios, con menos halos en los bordes, pero sus bytes cambian.
