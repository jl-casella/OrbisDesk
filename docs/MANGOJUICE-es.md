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
- **Popovers negros.** GTK dibuja los popovers y los tooltips como ventanas aparte con un margen de sombra transparente. Sin DirectComposition, que es opcional (`GDK_DEBUG=dcomp`) y necesitaría Direct3D 11, pide la transparencia a DWM con `DwmEnableBlurBehindWindow`. Wine no compone el canal alfa, así que ese margen salía negro. Un CSS con prioridad de usuario (`popover > contents, popover > arrow, tooltip { box-shadow: none; border-radius: 0; }`) no deja píxeles transparentes.

El escritorio es de 1280×720 escalado al televisor, así que MangoJuice nunca se verá ahí tan nítido como en un PC.

## Resultado de esta compilación

| | |
| --- | --- |
| `mangojuice.exe` | sha256 `b672c722e30d1342985a9de12efc3c6b8cec513f1e3643748911fd51ae18297a`; dos enlaces idénticos (con las revisiones de run-0062; antes era `51a7bb9b…` en tres compilaciones separadas) |
| Instalado | 989 archivos, 52,2 MiB: 62 DLL (solo `libgtk-4-1.dll` ocupa 12,0 MiB), iconos 4,9 MiB |
| DLL de Windows que aporta Wine | 46, entre ellas `opengl32`, `d3d11`, `d3d12`, `dcomp`, `dwrite`, `gdiplus` y `usp10` |
| No incluida | `vulkan-1.dll` de MSYS2: la de system32 es el cargador Khronos de OrbisDesk |
| Tiempo de compilación | de 7 a 10 minutos en `/mnt/c`, la mayor parte desempaquetando el árbol de MSYS2 |

Cada DLL instalada se lee entera en memoria al cargarse, dentro del proceso compartido de explorer (W095), así que MangoJuice ocupa memoria mientras está abierto. Ese coste no se midió en la consola.

## El archivo de ajustes

MangoJuice escribe `%APPDATA%\MangoHud\MangoHud.conf`, que en la consola es `/data/wine-prefix/drive_c/users/orbis/AppData/Roaming/MangoHud/MangoHud.conf`. Cada guardado reescribe el archivo entero: empieza con `legacy_layout=false`, lista como claves sueltas las filas activadas y omite las desactivadas. Con `legacy_layout` desactivado, MangoHud muestra solo las filas que nombra el archivo (`overlay_params.cpp`, `sort_elements`). El HUD Estadisticas del overlay del título (`native/hw_overlay.c`) ahora hace lo mismo; antes partía de las filas por defecto de MangoHud. Su línea de log añade `legacy_layout=`. El overlay sigue dibujando las filas en su propio orden fijo, no en el del archivo.

El archivo del usuario sobrevive a las actualizaciones. `tools/console_state.py` lo lista en `CONSOLE_OWNED_FILES`. El uploader por FTP y el instalador del primer arranque (líneas `P` de `install.txt`, `native/hw_install.h`) lo copian solo cuando falta. Antes, cada actualización lo reemplazaba por el de la build.

## Qué se comprobó y qué no

- El builder se ejecutó de principio a fin. Los dos enlaces fueron idénticos.
- En la consola, MangoJuice no cargó porque faltaba DWrite.dll (run-0060, arriba). Eso ya está corregido en la build, pero la corrección no se ha probado en la consola.
- `hw_overlay.c` compila con las opciones de compilación de la propia consola (`helper_compile_flags`). En el harness de vista previa del host:
  - un archivo como los de MangoJuice (`legacy_layout=false`, `fps`, `ram`) dio `gpu=0 cpu=0 ram=1 fps=1 frametime=0 frame_timing=0`;
  - el archivo por defecto de la build siguió dando las filas por defecto.
- `native/hw_install.h`: solo comprobación de sintaxis en el host.
- Los iconos se revisaron a 16, 32 y 48 px sobre el menú oscuro (38,38,40), el menú claro (240,240,240) y el color de selección (0,120,215).
- **No se ejecutó en ningún sitio:**
  - el propio MangoJuice: en esta sesión no se permitió ejecutar en el PC de compilación los binarios GTK descargados, y la build de Wine del host no tiene driver de pantalla;
  - ni en shadPS4, y en la PS4 solo hasta el fallo de DWrite.dll;
  - su tiempo de arranque, su uso de memoria y la navegación con el mando;
  - si el camino cairo de GTK 4.24 funciona siquiera bajo el Wine de OrbisDesk.

Una primera prueba en consola:

1. Abrir Graphics Tools > MangoJuice y anotar cuánto tarda la primera ventana.
2. Desmarcar algunas métricas, cambiar la posición y guardar.
3. Desactivar y activar Estadisticas, y comparar su línea `PWOVERLAY hud:`.
4. Abrir vkcube y mirar MangoHud.
5. Cerrar MangoJuice, reabrir Inicio y comprobar que el escritorio sigue respondiendo.
6. Instalar la build siguiente y comprobar que los ajustes se mantuvieron.

## El icono de vkSpin

El icono de vkSpin era un triángulo sin fondo. Su esquina azul se perdía en el menú oscuro y en el resaltado, y su centro blanco en el menú claro. Un fallo de `tools/make-icons.py` lo empeoraba: `raster()` tomaba la transparencia de un píxel del color más frecuente entre sus submuestras. Con un degradado cada submuestra tiene un color distinto, así que el triángulo salía con alrededor de 1/16 de opacidad.

Ahora la transparencia es la cobertura, y el color es la media de las submuestras. vkSpin es ahora el mismo triángulo sobre un recuadro redondeado de amarillo a magenta, con borde oscuro y contorno blanco, y destaca en los tres fondos. Los demás iconos se ven igual o algo más limpios, con menos halos en los bordes, pero sus bytes cambian.
