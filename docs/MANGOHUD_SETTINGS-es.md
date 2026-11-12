# Ajustes de MangoHud: un editor de las opciones del HUD

[English](MANGOHUD_SETTINGS.md) | [Español](MANGOHUD_SETTINGS-es.md)

Ajustes de MangoHud (`C:\orbis\mangohudcfg.exe`) permite al usuario elegir qué muestra el HUD sin editar `MangoHud.conf` a mano. Ahora lo abre el elemento del menú Inicio **Graphics Tools > MangoHud Config**. El nuevo elemento **MangoHud Config (text)** abre el mismo archivo en el Bloc de notas.

## Decisión: un programa Win32 pequeño, no MangoJuice

El candidato era MangoJuice-Windows (`https://github.com/Leclowndu93150/mangojuice-Windows.git` @ `e2ec0755`, fijado solo como referencia en `dependencies.lock.json`). [G001](HARDWARE_G001-es.md) ya lo había dejado fuera. Esta decisión lo volvió a comprobar:

| Pregunta | MangoJuice-Windows | Editor Win32 nativo |
| --- | --- | --- |
| Código | 7.701 líneas de Vala. La mayoría cubre opciones de MangoHud que ninguno de los dos lectores de OrbisDesk usa: temperaturas de CPU/GPU, relojes, consumo, ventilador, batería, lanzamiento de Steam y juegos, presets. | Un archivo C para las 12 claves que lee OrbisDesk. |
| Runtime | GTK4, libadwaita-1 y gee-0.8 para Windows, junto con GLib, Pango, HarfBuzz, Cairo, FreeType, graphene, un tema de iconos y sus datos. Haría falta compilar toda la pila con mingw, o paquetes de MSYS2 fijados por hash. No se midieron sus tamaños. | `comctl32`, `shell32`, `user32`, `gdi32`, `kernel32`, `msvcrt`. Todos son builtins de Wine que ya se instalan. |
| Herramientas del host | `valac`, meson y la pila de compilación de GTK4. No hay ninguna instalada. | El compilador MinGW-w64 fijado que ya compila los demás programas de `C:\orbis`. |
| Dentro del título | El renderizador por defecto de GTK4 usa GL. Habría que ejecutarlo con `GSK_RENDERER=cairo`, y eso no se probó. El título lee cada imagen entera en memoria, y todos los programas comparten el proceso de explorer (W095, en el comentario de `build-wine-hardware.py`), así que cada DLL de GTK ocupa memoria mientras está cargada. | 70.656 bytes. |
| Modelo de procesos | Ejecuta procesos auxiliares con `Process.spawn_sync` (gestor de juegos), y su vista previa abre vkcube/glxgears. Un invitado lanzado desde otro invitado puede terminar cuando termina su padre ([W180](HARDWARE_W180-es.md)). | No lanza nada. |
| Esfuerzo para mantenerlo | No tiene releases, así que habría que mantener un fork de un upstream que solo apunta a Windows de escritorio. | Dentro de este repositorio. |

El editor ocupa alrededor de 1/1000 del runtime de MangoJuice y no añade dependencias. Las opciones de más de MangoJuice mostrarían al usuario ajustes que aquí no tienen efecto. Se recomienda e implementa la vía nativa. MangoJuice sigue fijado solo como referencia.

## Qué muestra y qué escribe el editor

Dos programas leen `%APPDATA%\MangoHud\MangoHud.conf`, que en la consola es `/data/wine-prefix/drive_c/users/orbis/AppData/Roaming/MangoHud/MangoHud.conf`:

- La capa de MangoHud (`overlay_params.cpp`). Lee el archivo cuando se inicia un programa Vulkan. Gana el último valor de cada clave; primero se aplica `full` y después las demás claves.
- El HUD **Estadisticas** del overlay del título (`native/hw_overlay.c`, `hud_read_conf`). Lee el archivo cada vez que se activa Estadisticas, y procesa las líneas en orden. Su línea de log es `PWOVERLAY hud: ...`.

El formulario edita solo las claves que leen los dos:

| Formulario | Clave | Rango |
| --- | --- | --- |
| Mostrar: fotogramas por segundo, tiempo de fotograma, gráfica de tiempos, GPU, CPU, memoria, memoria de vídeo | `fps`, `frametime`, `frame_timing`, `gpu_stats`, `cpu_stats`, `ram`, `vram` | sí/no |
| Posición | `position` | las 8 posiciones que aceptan los dos lectores |
| Tamaño de letra | `font_size` | 8–96. `hw_overlay.c` ignora los demás valores. |
| Opacidad del fondo | `background_alpha` | 0–100 %, escrito como 0.00–1.00 |
| Desplazamiento horizontal/vertical | `offset_x`, `offset_y` | 0–2000. MangoHud los lee sin signo. |

El formulario se abre con los valores que usaría `hw_overlay.c`: los valores por defecto de MangoHud y después el archivo. En la PS4, VRAM siempre se muestra como "--", porque la memoria es unificada (`native/hw_overlay.c`).

Al pulsar **Guardar**, el programa vuelve a leer el archivo y lo escribe de nuevo:

- todas las demás líneas se conservan tal como estaban: comentarios, `full`, `toggle_hud` y cualquier otra opción de MangoHud;
- cada clave editada se quita de donde estuviera y se escribe una sola vez al final, con un `clave=0`/`clave=1` o valor explícito, después de un comentario marcador.

Así, los dos lectores terminan con los mismos valores, sean cuales sean sus reglas de orden. Guardar dos veces da el mismo archivo. El programa escribe primero `MangoHud.conf.new` y lo renombra sobre el archivo anterior.

**Valores por defecto** muestra los valores por defecto de MangoHud, que solo se aplican después de Guardar. La interfaz sigue el idioma de la interfaz de Wine: español o inglés. Un argumento indica otro archivo, para pruebas.

## El archivo del usuario sobrevive a las actualizaciones

Antes de este cambio, cada actualización reemplazaba `MangoHud.conf` por la copia de la build cuando las dos eran distintas: la subida por FTP (`tools/upload-hardware.py`) y el instalador del primer arranque (`native/hw_install.h`). Eso habría borrado lo que guardó el usuario. Ahora el archivo pertenece a la consola. `tools/console_state.py` lo lista en `CONSOLE_OWNED_FILES`. El uploader lo omite si ya existe. `build-wine-hardware.py` escribe una línea `P` en `install.txt`, y el instalador copia el archivo solo cuando falta (`PWINSTALL plan ... kept=1`). El archivo de la build sigue siendo el valor por defecto de una instalación limpia.

## Compilación e instalación en el runtime

```sh
# WSL Ubuntu-22.04 from the repository root; the compiler package must match build-environment.lock.json
python3 tools/build-mangohudcfg-hw.py
python3 tests/test_mangohudcfg.py
```

[build-mangohudcfg-hw.py](../tools/build-mangohudcfg-hw.py):

- compila [mangohudcfg.c](../fixtures/win32/mangohudcfg.c) con `x86_64-w64-mingw32-gcc`, con `-Werror` y sin marca de tiempo;
- lo enlaza dos veces en `build/mangohudcfg-hw/{a,b}` y exige que el resultado sea idéntico;
- comprueba las importaciones;
- escribe `out/mangohudcfg-hw/mangohudcfg.exe` y `manifest.json`, que registra el hash de la fuente, el del builder y los paquetes del compilador.

Solo usa sus propios directorios. `build-wine-hardware.py` comprueba el manifiesto contra el builder y la fuente, y copia el programa a `C:\orbis\mangohudcfg.exe`. `tools/ci/build-product.py` ejecuta el builder antes de la build del producto, y el job de host de las PR ejecuta la prueba.

[test_mangohudcfg.py](../tests/test_mangohudcfg.py) compila para el host la lógica de archivo del programa. Comprueba un guardado contra modelos de los dos lectores: el archivo por defecto de la build, un archivo de usuario con CRLF, `full`, claves repetidas, otras opciones y una letra fuera de rango, y un archivo inexistente.

## Qué se comprobó y qué no

- Builder: dos enlaces idénticos. `out/mangohudcfg-hw/mangohudcfg.exe` ocupa 70.656 bytes, sha256 `0e09c86b2c77af2063eff7106de0ce245801708af8d851b1fb9da66163073aaa`, con gcc-mingw-w64-x86-64 `10.3.0-14ubuntu1+24.3`.
- Prueba de lógica en el host: 16 comprobaciones superadas.
- Windows 11 nativo, que es solo comportamiento de referencia, no Wine ni PS4:
  - la ventana se abrió en español;
  - el `full` del archivo mostró todas las filas marcadas;
  - desmarcar la memoria de vídeo y guardar escribió `vram=0` después de `full`, y conservó `# my HUD`, `full` y `toggle_hud`.
- `native/hw_install.h`: solo comprobación de sintaxis en el host, con stubs.
- **No se ejecutó:**
  - bajo Wine: la build de Wine del host no tiene driver de pantalla;
  - en un paquete W, ni en shadPS4 ni en la PS4;
  - las reglas del uploader y del instalador en la consola;
  - si la capa de MangoHud aplica un cambio sin reiniciar el programa, ni cómo se recorre el formulario con el mando.

Una primera prueba en consola:

1. Abrir Graphics Tools > MangoHud Config.
2. Desmarcar la gráfica de tiempos, poner la posición abajo a la derecha y el tamaño de letra en 30, y pulsar Guardar.
3. Desactivar y volver a activar Estadisticas. El log debería mostrar `PWOVERLAY hud: ... frame_timing=0 position=bottom-right font_size=30`.
4. Abrir vkcube y mirar MangoHud.
5. Instalar la build siguiente y comprobar que los ajustes siguen ahí.
