# Wine Mono: programas .NET

[English](WINE_MONO.md) | [Español](WINE_MONO-es.md)

## Por qué

El `settings.exe` de PES 2014 es un programa .NET solo IL. Iniciado desde el escritorio y solo, se detenía con `mscoree.dll not found, IL-only binary "settings.exe" cannot be loaded` (run-0121, run-0163). OrbisDesk no incluía ni el `mscoree.dll` de Wine ni un runtime .NET: los dos estaban en la lista de módulos excluidos (`tools/stage-wine-i386.py`, "needs Wine Mono, not staged").

## Qué agrega la build

- [stage-wine-mono.py](../tools/stage-wine-mono.py) desempaqueta Wine Mono 11.3.0, la versión que pide el Wine fijado (`dlls/mscoree/mscoree_private.h`). El archivo es el `wine-mono-11.3.0-x86.tar.xz` original, fijado por SHA-256 en [product-assets.lock.json](../product-assets.lock.json); el resumen coincide con el del archivo de la release de GitHub. A pesar de su nombre contiene los dos runtimes, `bin/libmono-2.0-x86.dll` y `bin/libmono-2.0-x86_64.dll`, y las bibliotecas de clases.
- El sistema de archivos de la consola no tiene enlaces simbólicos, así que los 156 enlaces de `lib/mono` pasan a ser copias de sus destinos. Se deja fuera `support/`: contiene los ayudantes del `.msi` que el `appwiz.cpl` de Wine ejecuta al crear un prefijo, cosa que este prefijo sellado no hace.
- [build-wine-hardware.py](../tools/build-wine-hardware.py) copia el árbol a `C:\windows\mono\mono-2.0`, el primer lugar donde busca `mscoree` (`get_mono_path_local`), y el `COPYING` de Wine Mono a `C:\windows\mono\licenses`. Eso suma unos 275 MB al runtime.
- `mscoree.dll` y `mscorwks.dll` se incluyen en las dos vistas, `system32` y `syswow64`.

## Primera prueba en hardware (versión de la app 04.09, run-0172)

`settings.exe` ya encontró `mscoree.dll` y después falló en su primera instrucción (`c0000005` en `0x1359e0`). La entrada de la cabecera de un EXE solo IL es un salto a través de una tabla de importaciones que el cargador nunca resuelve para esa imagen: el `fixup_imports_ilonly` de Wine pone en su lugar el `_CorExeMain` de `mscoree` como entrada del cargador. El lanzador de invitados de OrbisDesk llamaba a la entrada de la cabecera. Ahora usa la entrada del cargador para una imagen con cabecera .NET y registra `PWGUEST ilonly entry` ([build-guest-hw.py](../tools/build-guest-hw.py)). Todavía no se comprobó en la consola.

## Segunda prueba en hardware (versión de la app 04.20, run-0221)

Mono ya arranca: `PWGUEST ilonly entry 005359FE -> 7B72C150`, después se cargan `mscorlib`, `System.Windows.Forms` y el `Settings_b.dll` del programa, y WinForms crea su ventana de estacionamiento. Quedaban dos problemas, uno en `settings.exe` y otro en el juego, `pes2014.exe`.

### settings.exe: "Error creating window handle"

El programa terminaba con `System.ComponentModel.Win32Exception: Error creating window handle` desde `TextBoxBase.CreateHandle` en `Settings.Online..ctor`, justo después de dos `PWFAULT ... address=FF665060 access=0`, cada uno seguido de `dispatch_user_callback ignoring exception c0000005`.

- El WinForms de Wine Mono es el de Microsoft. Un `TextBox` es una superclase de `Edit`: WinForms toma el procedimiento de `Edit` de `GetClassInfo` y le pasa con `CallWindowProc` los mensajes que no atiende.
- Con estilos visuales, `Edit` es la clase global `6.0.2600.2982!Edit` de comctl32 v6. En el único proceso del título, el lado de 64 bits de explorer ya la había registrado, con el procedimiento del comctl32 de 64 bits. El comctl32 v6 de 32 bits la registra otra vez cuando se busca la clase (`RegisterClassNameW`), y el servidor lo rechaza: hay una clase por nombre en un proceso.
- W239 le da a un hilo de 32 bits el handle de ese procedimiento en lugar de su dirección. `CallWindowProc` con ese handle le pide los procedimientos a win32u (`NtUserCallWindowProc`); wow64win los copia en campos de 32 bits (`win_proc_params_64to32`), así que el `0x7FF665060` de 64 bits llegaba como `FF665060` y user32 lo llamaba. El fallo dentro de `WM_NCCREATE` hacía fallar `CreateWindowEx`. W239 solo cubría el camino en que win32u llama al procedimiento.

La corrección está en [build-win32u-ps4.py](../tools/build-win32u-ps4.py):

1. Cuando un hilo de 32 bits registra una clase global que el lado de 64 bits registró con un procedimiento de 64 bits, el servidor la sigue rechazando, pero win32u guarda el procedimiento de 32 bits junto al de 64. Los hilos del mundo de 32 bits reciben ese, como hace W236 con las clases integradas de user32. Registro: `PWWOW win32u: global class L"6.0.2600.2982!Edit" is the 64-bit side's (proc .../...); 32-bit threads get .../...`.
2. Un procedimiento que sigue siendo de 64 bits (una clase que solo tiene el lado de 64 bits, como el `Wine IME` de W239) nunca llega a código de 32 bits por `CallWindowProc` ni por `DispatchMessage`: el hilo recibe su propio `DefWindowProc`, el mismo comportamiento por defecto que da W239 en el otro camino. Registro: `PWWOW win32u: 32-bit thread ... is 64-bit; its DefWindowProc instead`.

Los bytes extra de ventana siguen siendo los del registro de 64 bits, que nunca son menos de los que necesita el control de 32 bits (el `Edit` de comctl32: 8 bytes contra 6).

`mscoree:LoadLibraryShim error reading registry key for installroot` no es fatal: sin la clave `InstallRoot` de `.NETFramework`, que instala el `.msi` y este prefijo no tiene, `LoadLibraryShim` carga la DLL por su nombre solo, y `fusion.dll` se cargó en la línea siguiente.

### pes2014.exe: la imagen no cabía en la ventana de EXE antiguos

`PWWOW image_not_at_base preferred=0x400000 size=0x2050000 status=0xc0000018 occupied=0x23f0000+0xc3000 prot=0x800021`, y después el cuadro de mensaje de `base_taken`.

- El juego no tiene reubicaciones, así que necesita exactamente `[0x400000, 0x2450000)`. W246 deja las asignaciones sin dirección fija del título fuera de `[0x400000, 0x2000000)`, 32 MiB, que alcanzaban para Vice City pero no para esta imagen.
- Lo que ocupa ese lugar no es un resto de `settings.exe`. Es una vista de archivo de solo lectura (`SEC_FILE`, `0x800000`) de 195 páginas, el tamaño de `locale.nls` (794.914 bytes), junto al heap de proceso del mundo de 32 bits en `023D0000`. El mundo de 32 bits mapea los dos al arrancar, justo encima de `0x2000000`, y los conserva mientras corre el título. La vista ya estaba en run-0169, run-0171 y run-0178, donde PES 2014 fue el primer programa de 32 bits del título. Todos los inicios de PES 2014 en el mundo de los registros de W303 (run-0100 a run-0221) y el run-0011 de W261 fallaron igual; la mayoría nombra esta vista, dos una asignación en `0x2200000`, en el mismo rango.
- Los heaps que dejó `settings.exe` (`02B10000`, retenido por `mscoree.dll`) están por encima del rango del juego y no intervinieron.

La corrección está en [build-wow64-world-ps4.py](../tools/build-wow64-world-ps4.py): la ventana ahora es `[0x400000, 0x8000000)`, 124 MiB de imagen, todavía por debajo de la base habitual de las DLL, `0x10000000`. El heap del mundo y su vista de `locale.nls` quedan entonces por encima. El relanzamiento por `base_taken` sigue para una imagen que aún encuentre ocupada su base.

### Prueba en la consola (después de compilar y subir la 04.21)

1. Desde el escritorio, abrir `E:\PC\PES 2014\settings.exe`. Esperado: la ventana de configuración con sus pestañas y cuadros de texto. En el registro: `PWWOW win32u: global class ...Edit... 32-bit threads get`, y ningún `PWFAULT` en `FFxxxxxx` ni `Error creating window handle`.
2. Cambiar una opción, guardar y cerrar `settings.exe`.
3. Sin reiniciar OrbisDesk, abrir `E:\PC\PES 2014\pes2014.exe`. Esperado: ninguna línea `image_not_at_base preferred=0x400000 size=0x2050000` y ningún cuadro de mensaje sobre la misma dirección de memoria; el juego se carga en el mundo de 32 bits del escritorio (`PWGUEST load_end app=...pes2014.exe module=00400000 error=0`). Lo que haga el juego después de sus propias comprobaciones de inicio no forma parte de esta corrección.
4. Cerrar el juego y volver a abrir `settings.exe`, para comprobar un segundo inicio después del final de un invitado.
5. Traer los registros con `tools/fetch-hardware.py`.

## Tercera prueba en hardware (versión de la app 04.22, run-0224)

`settings.exe` abrió su ventana, con sus pestañas, y se cerró con código de salida 0. El registro muestra la corrección de la 04.21 funcionando para `Edit`, `Button`, `Static` y `tooltips_class32`.

### settings.exe: símbolos en lugar de texto

La barra de título, los nombres de las pestañas y la lista de resoluciones (`(1280x720) 16:9`) se leían bien. Todas las etiquetas de grupo, botones de opción, casillas y los botones `OK` y `Cancel` mostraban símbolos en lugar de letras. Los textos en sí eran correctos: `PWTEXT` muestra `Quality`, `High`, `Screen Mode`, `XInput`, `OK` y `Cancel`.

- Los textos legibles los dibujan controles nativos (el control de pestañas, el cuadro combinado) con el handle de `Font.ToHfont`. Su juego de caracteres es el de la fuente que GDI+ eligió de verdad, ANSI para Tahoma.
- Los textos rotos son los que dibuja el propio WinForms (etiquetas, cuadros de grupo, botones, botones de opción y casillas en el estilo estándar). Para ellos WinForms arma su propio `LOGFONT` con el `GdiCharSet` del `Font`. El programa se hizo en un Windows japonés: una etiqueta está en japonés, y el diseñador les da a las fuentes de ese formulario el juego de caracteres 128 (Shift-JIS).
- Ninguna fuente del runtime cubre ese juego de caracteres: tiene Tahoma, Tahoma Bold y Marlett, y no tiene fontconfig. El asignador de fuentes de Wine quita entonces el filtro de juego de caracteres y toma la primera familia en orden alfabético, Marlett. Marlett es una fuente solo de símbolos (su rango de páginas de códigos es solo el bit de símbolos), así que cada letra se convertía en uno de sus glifos de ventana.

La corrección está en [build-win32u-ps4.py](../tools/build-win32u-ps4.py) (`font.c`): en esa búsqueda sin filtro de juego de caracteres se salta una fuente cuya única página de códigos es la de símbolos, salvo que se pida `SYMBOL_CHARSET`. El asignador de Windows tampoco le da una fuente de símbolos a un texto. Quien pide Marlett por su nombre la sigue recibiendo. Si solo hay fuentes de símbolos, se siguen usando. Registro, como mucho ocho veces: `PWFONT L"..." charset 128: no font has its charset; not the symbol font L"Marlett"`.

La etiqueta en japonés sigue mostrando cuadros: el runtime no tiene una fuente japonesa. El texto latino de un programa así ahora usa Tahoma.

### pes2014.exe

`pes2014.exe` ya se carga en `0x400000` dentro del mundo de 32 bits del escritorio. Después muestra un mensaje propio: la copia del juego necesita un `rld.dll` que no está en su carpeta (`c0000135`). Ese archivo es de la copia del juego del usuario, no de OrbisDesk, y OrbisDesk no hace nada al respecto.

### Prueba en la consola (después de compilar y subir la 04.24)

1. Abrir `E:\PC\PES 2014\settings.exe`. Esperado: etiquetas de grupo, botones de opción, casillas y los botones `OK` y `Cancel` en letras latinas legibles. La etiqueta en japonés puede seguir con cuadros. En el registro: `PWFONT ... charset 128: no font has its charset; not the symbol font L"Marlett"`.
2. Revisar lo que usa Marlett a propósito: los botones de cerrar, minimizar y maximizar de una ventana, las flechas de una barra de desplazamiento y una marca de verificación en un menú siguen mostrando sus símbolos.
3. Cambiar una opción, pulsar `OK`, volver a abrir `settings.exe` y comprobar que la opción se guardó.
4. Traer los registros con `tools/fetch-hardware.py`.

## Límites

- Faltan los archivos y claves de registro falsos de .NET Framework que instala el `.msi`. Un programa que busca en el registro una versión instalada de .NET Framework antes de arrancar puede seguir negándose a ejecutarse.
- `settings.exe` se ejecutó de principio a fin en la consola en run-0224 (código de salida 0). Todavía no se comprobó que guarde una opción.
- El runtime no tiene fuentes para japonés, chino ni coreano. El texto en esas escrituras se muestra como cuadros.
- No se cubre un hilo de 64 bits que usa una clase global registrada primero por el mundo de 32 bits (el caso inverso del de arriba).
