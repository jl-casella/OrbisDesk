# Composición por GPU en SeaMonkey

[English](SEAMONKEY_GPU.md) | [Español](SEAMONKEY_GPU-es.md)

Estado: la composición por GPU salió en 04.19 y falló en la consola al segundo arranque (run-0218). Desde 04.20 el valor por defecto vuelve a ser Basic, y OpenGL es opcional. Run-0234 situó el fallo del segundo arranque en MangoHud; el arreglo de 04.26 no está compilado. 2026-11-18.

## Objetivo

Hasta 04.18, SeaMonkey usa el compositor Basic de Gecko: la CPU mezcla las capas, convierte el vídeo desde YUV y lo escala. El objetivo es pasar ese trabajo a la GPU de la consola, sin bloqueos, con una vuelta limpia a Basic y dentro de la memoria del título.

Esto solo mueve la composición. El JavaScript de la página, la maquetación y el pintado del contenido (Skia en la CPU, ya repartido en 4 hilos de pintado fuera del hilo principal) siguen donde están ([respuesta](SEAMONKEY_RESPONSIVENESS-es.md)).

## OpenGL activado, 04.32: Gecko dimensiona su cuadro GL con el rectángulo de la ventana (04.34)

En la 04.32, con OpenGL activado, la ventana se dibujó otra vez 34 píxeles demasiado arriba, y el vídeo de YouTube no se reprodujo. Run-0270 tiene las tres trazas:
- `PWGL viewport 1163x651 at 0,0 on a 1155x617 window drawable` (línea 1408): Gecko fija un viewport tan grande como el rectángulo de la ventana, con el marco.
- `PWSTW size hwnd=…200f8 thread=0124 client=1155x617 window=1163x651 drawable=1155x617` (línea 1316): WGL de Mesa lee el área cliente y la obtiene bien.
- `PWRECT client hwnd=0x200f8 thread=0124 owner=00a0 … rect=(0,0)-(1155,617)` (línea 1039): win32u devuelve el tamaño cliente al hilo del compositor de Gecko. `PWVK size … image=1155x617 client=1155x617` (línea 1042): la cadena de intercambio también tiene el tamaño cliente.

Así que win32u, Mesa y Zink coinciden en el tamaño cliente. Solo el cuadro de Gecko tiene el tamaño de la ventana.

**De dónde saca Gecko ese tamaño (plataforma de Firefox 60, código de mozilla-esr60):**
- `ClientLayerManager::BeginTransactionWithTarget` manda `mWidget->GetNaturalBounds()` al compositor. `nsIWidget::GetNaturalBounds()` devuelve `GetBounds()`.
- En Windows, `nsWindow::GetBounds()` es `GetWindowRect`: la ventana con su marco.
- `CompositorBridgeParent::ShadowLayersUpdated` lo pasa como límites de dibujo (`UpdateRenderBounds(targetConfig.naturalBounds())`). `CompositorOGL::BeginFrame` crea el destino de dibujo de la ventana con ese tamaño, y `PrepareViewport` fija `glViewport` en él.
- La página se maqueta con el tamaño cliente. Así que el cuadro se dibuja 34 filas más alto que la superficie de dibujo. Las filas de GL van de abajo arriba, así que las 34 primeras (la barra de menús) quedan fuera, y las 34 últimas se quedan negras.
- El marco también es el de por defecto en Windows. Gecko cambia el área no cliente solo en una ventana con el atributo `chromemargin` (`nsWindow::SetNonClientMargins` activa `mCustomNonClient`, y solo entonces su manejador de `WM_NCCALCSIZE` encoge el marco). El chrome de SeaMonkey 2.53 nunca lo fija en Windows. El único que lo fija en `omni.ja` es `LightweightThemeConsumer.jsm`, y solo en macOS. win32u manda `WM_NCCALCSIZE` y usa su resultado (`calc_ncsize` de Wine, sin cambios de nuestros generadores). El área cliente de run-0270 es la del marco por defecto: bordes de 4 píxeles y un título de 26 píxeles.
- El contexto GL de Gecko está en esa ventana de nivel superior con marco (`hwnd=0x200f8` en `PWSTW` y `PWVK`), no en una hija sin marco.
- Los otros compositores lo ocultan. Basic dibuja de arriba abajo en el área cliente por GDI, así que las filas de más caen abajo y a la derecha, donde no se dibuja nada. Direct3D 11 dimensiona su cadena de intercambio con `GetClientRect`. El compositor OpenGL de Gecko no se usa por defecto en Windows, y el bug [1125754](https://bugzilla.mozilla.org/show_bug.cgi?id=1125754) informa de una ventana recortada con `layers.prefer-opengl` en Windows.
- Así que el fallo es de Gecko, en cualquier Windows con cualquier controlador OpenGL, no de la consola. La nota de la 04.26 de que el anfitrión lo colocaba todo bien era errónea: las ejecuciones de "Prueba en el anfitrión" más abajo tenían la ventana minimizada, así que no comprobaron la imagen dibujada.
- **Comprobación en el anfitrión (04.34, Windows 11, AMD, solo referencia):** SeaMonkey 2.53.24 con el `opengl32.dll` y el `libgallium_wgl.dll` de 64 bits de la W303 junto a `seamonkey.exe`, `GALLIUM_DRIVER=zink`, el user.js de la consola con la aceleración activada y `layers.prefer-opengl` en true, en una ventana restaurada de 1163x651 (cliente 1147x612).
  - Con OpenGL falta la barra de menús, la barra de navegación sale cortada por arriba, y bajo la barra de estado hay una franja negra de unos 39 píxeles: la altura de la ventana menos la del cliente. Es el fallo de la consola, con el marco más alto de Windows 11.
  - Con `layers.prefer-opengl` en false (Basic), en la misma ventana, todo está en su sitio.

**Las otras líneas:**
- `PWGL viewport 1163x651 at 0,0 on a 1x1 window drawable` (línea 1037) es el primer cuadro, antes de que el primer intercambio de Mesa leyera la ventana. Es lo esperado.
- `PWGL viewport 766x23 at 0,0 on a 766x132 window drawable` (línea 2182) es una ventana emergente que se encogió de 132 a 23 filas. Gecko dibujó un cuadro con el tamaño nuevo antes de que el siguiente intercambio de Mesa lo leyera, y la siguiente cadena de intercambio es `766x23` (línea 2185). Dura un cuadro y no es el fallo de 34 píxeles.

**Este cambio (04.34):** ningún cambio de código para el desplazamiento. Nada en Wine, Mesa o Zink devuelve un tamaño equivocado, así que cambiarlos daría el tamaño equivocado a todos los demás programas. [seamonkey-gpu.js](../fixtures/browser/seamonkey-gpu.js) mantiene la composición por GPU desactivada por defecto (Basic), y su comentario nombra ahora la causa. Con OpenGL activado en about:config, el desplazamiento sigue. Las trazas de la 04.30 y la 04.32 se quedan como están; tienen límite y son de solo lectura.

**Formas de arreglarlo, todas fuera de nuestro Wine y Mesa (no hechas; una decisión):**
- Parchear el `xul.dll` de SeaMonkey: en `ClientLayerManager::BeginTransactionWithTarget`, llamar a `GetClientBounds` en vez de `GetNaturalBounds`. Cambia una sola entrada de llamada virtual, y da el tamaño que ya usa Direct3D 11. Hay que encontrar la llamada sin símbolos. Hay que comprobar los bytes exactos contra el archivo fijado y publicar el cambio como código fuente (`xul.dll` es MPL 2.0).
- Quitar el marco a las ventanas de SeaMonkey (`chromemargin` a `0,0,0,0` desde orbisdesk.cfg), para que el área cliente sea la ventana. El tema de SeaMonkey no dibuja barra de título, así que las ventanas perderían su título y sus botones. Los diálogos y las ventanas emergentes necesitarían lo mismo.
- Seguir con Basic, como ahora. YouTube tampoco se reproduce con OpenGL (más abajo).

**YouTube:** sigue siendo el problema abierto del camino de vídeo de Zink (ver "El vídeo se queda negro con OpenGL activado" más abajo). En la foto de la 04.32 la zona del reproductor mostraba un anuncio azul, y el vídeo no se reproducía. Sin cambios aquí.

## OpenGL activado, 04.30: las trazas no dijeron nada (04.32)

En la 04.30 se activó OpenGL en about:config. La ventana se dibujó desplazada como antes, y los vídeos de YouTube no se reproducían; el usuario vio que la zona del reproductor cambiaba de color (verde azulado oscuro en la foto). En run-0262 volvió `PWVK size hwnd=0x800c2 image=1154x617 client=1154x617 window=1162x651` (línea 781), y ninguna línea `PWGL viewport` ni `PWRECT`.

**Por qué la traza de Mesa no podía salir:**
- Las dos trazas estaban en la compilación subida: `PWGL viewport` está en el `libgallium_wgl.dll` de 64 bits, y `PWRECT` en el `window.o` de win32u.
- En Windows, `mesa_loge` escribe en el stderr del programa y en `OutputDebugStringA`. El stderr de un invitado no es el log de la consola, y Wine imprime `OutputDebugStringA` solo en su canal `warn+debugstr`. El `WINEDEBUG` del lanzador es `fixme-all,warn+module`. Las líneas `PWSTW` de la W267 venían de una ejecución que tenía `warn+debugstr`.
- Así que la falta de la línea `PWGL viewport` no dice nada del viewport de Gecko.

**Por qué la traza de win32u no dijo nada:**
- Se armaba en la primera presentación de una ventana con marco (`0x800c2` en la línea 781) y solo registraba lecturas de esa ventana desde otros hilos.
- Las presentaciones vienen del hilo `0178`, que creó Mesa (`by=L"libgallium_wgl.dll"`); el hilo del compositor de Gecko es `00e8`. WGL de Mesa lee el rectángulo cliente de su ventana en cada intercambio, así que se esperaba una lectura desde `00e8`, y no se registró ninguna.
- Qué ventana nombraban esas lecturas, o si llegaron antes de armarse la traza, no está en el log.

**Este cambio (no compilado):**
- [patch-mesa-gl-viewport-trace.py](../tools/vk-h0/patch-mesa-gl-viewport-trace.py) ahora también manda las líneas de nivel error de Mesa por `__wine_dbg_output` de ntdll cuando existe, que escribe en el log de la consola diga lo que diga `WINEDEBUG`. Los demás niveles, y Mesa fuera de Wine, no cambian. Las líneas de nivel error son raras: estas trazas, las trazas de ventana de 32 bits de la W266 y los errores reales. También añade `PWSTW size hwnd=… thread=… client=WxH window=WxH drawable=WxH`: lo que devuelven `GetClientRect` y `GetWindowRect` a WGL en cada intercambio, cuando cambia, las 16 primeras veces.
  - Los archivos parcheados compilan para las dos compilaciones (64 bits e i386) con la receta registrada y `-Wall`, sin avisos. La compilación i386 comparte la carpeta de código de Mesa, así que recibe el cambio si se compila después de la de 64 bits.
- [build-win32u-ps4.py](../tools/build-win32u-ps4.py): `PWRECT client|window` se registra ahora para cualquier ventana leída por un hilo que no es el suyo, desde el principio, una vez por ventana, hilo, tipo y tamaño devuelto, las 48 primeras. `window.c` compila con la receta registrada sin avisos; `vulkan.c` quita el armado de la 04.30 y mantiene sus 3 avisos de antes.

**Qué dirá una ejecución con OpenGL activado:**
- `PWGL viewport 1162x651 … on a 1154x617 window drawable`: el tamaño de Gecko es el de la ventana.
- `PWSTW size … client=1162x651`: la superficie de dibujo que lee WGL ya tiene el tamaño de la ventana.
- `PWRECT client hwnd=0x… thread=00e8 … rect=(0,0)-(1162,651)`: win32u devuelve el tamaño de la ventana al hilo del compositor de Gecko.

**YouTube no reproduce:** sigue siendo el problema abierto de Zink en el camino de vídeo de Gecko (ver "El vídeo se queda negro con OpenGL activado" más abajo). Los colores que cambian en la zona del reproductor encajan con cuadros de vídeo dibujados con la conversión de color equivocada, como en el anfitrión (magenta). Sin arreglar aquí.

## OpenGL activado, 04.29: la imagen sigue 34 píxeles demasiado arriba y YouTube no reproduce (04.30)

En la 04.29 se editó a mano el `user.js` de la consola: `layers.acceleration.disabled` a false, `layers.acceleration.force-enabled` a true, `webgl.disabled` a false y `webgl.force-enabled` a true. about:support mostraba Compositing OpenGL, y WebGL funcionaba. La ventana volvió a dibujarse desplazada, con negro abajo, y los vídeos de YouTube no se reproducían (run-0254, run-0255).

**Qué muestra la traza de tamaños:**
- `PWVK size hwnd=0x1c00b4 swapchain=… image=1154x617 client=1154x617 window=1162x651` (run-0255 línea 774, run-0254 línea 1550). La imagen de la swapchain tiene el tamaño del área cliente.
- La línea siguiente la coloca en el área cliente: `PWVK layer … client=(74,50)-(1228,667) … at=(74,50)-(1228,667)`, y la pila del sink la tiene ahí (`stack 4/5 … rect=(74,50)-(1228,667) flags=0x1 source=1154x617`).
- Así que la imagen no se coloca en el origen de la ventana, y moverla colocaría mal todos los programas que van bien. El desplazamiento está dentro de la imagen.
- Encaja con un cuadro dibujado para el tamaño de la ventana, 1162x651, en una superficie de dibujo del tamaño del área cliente, 1154x617. Las filas de GL van de abajo arriba, así que las 34 filas de arriba del cuadro se salen por arriba y sus últimas 34 filas quedan negras. Basic dibuja de arriba abajo con GDI, así que el mismo cuadro demasiado grande solo pierde filas por debajo, donde la página no tiene nada, y se ve bien.
- WGL de Mesa toma el tamaño de la superficie de dibujo de `GetClientRect` en cada intercambio, y la swapchain de Zink es el `currentExtent` de la superficie (el área cliente). El compositor de Gecko lee el tamaño de su widget en su propio hilo. En Windows real el mismo SeaMonkey, el mismo Mesa y el mismo perfil van bien, así que una de estas lecturas recibe el tamaño de la ventana en nuestro camino. Cuál, no está en estos logs.

**Este cambio (no compilado), dos trazas para una ejecución:**
- [patch-mesa-gl-viewport-trace.py](../tools/vk-h0/patch-mesa-gl-viewport-trace.py), que ejecuta [build-mesa-zink.sh](../tools/vk-h0/build-mesa-zink.sh): `PWGL viewport WxH at X,Y on a WxH window drawable` cuando un viewport sobre la superficie de dibujo de una ventana no tiene su tamaño (en cada cambio, las 16 primeras veces). `1162x651 … on a 1154x617` significa que el tamaño de Gecko es el de la ventana. Compila con la receta registrada sin avisos. La compilación i386 comparte la misma carpeta de código de Mesa, así que también recibe la traza si se compila después de la de 64 bits.
- [build-win32u-ps4.py](../tools/build-win32u-ps4.py): para la primera ventana con marco que tiene una swapchain de Vulkan, `PWRECT client|window hwnd=… thread=… owner=… dpi=… rect=…` para `GetClientRect` y `GetWindowRect` desde hilos que no son el de la ventana (los 48 primeros). Muestra qué lee el hilo del compositor de Gecko. `vulkan.c` y `window.c` compilan con la receta registrada, con los mismos avisos que antes.

**YouTube no reproduce:** los logs muestran el decodificador (`mozavcodec.dll`) cargado y sus hilos arrancados, y ningún fallo. En el anfitrión Windows, el mismo camino de vídeo dibujado por Zink también sale mal (magenta, ver "El vídeo se queda negro con OpenGL activado" más abajo), así que sigue siendo el problema abierto de Zink en el camino de vídeo de Gecko, sin arreglar aquí.

**Los interruptores de la GPU son ahora valores por defecto (04.30, no compilado):**
- [seamonkey-user.js](../fixtures/browser/seamonkey-user.js) ya no pone `layers.acceleration.disabled`, `layers.acceleration.force-enabled` ni `webgl.disabled`. [seamonkey-gpu.js](../fixtures/browser/seamonkey-gpu.js) los pone, con `webgl.force-enabled`, como valores por defecto de SeaMonkey. Así, un cambio en about:config se mantiene entre arranques y subidas.
- Siguen apagados hasta que se arreglen el desplazamiento y el vídeo. Encenderlos por defecto es poner allí los dos valores `disabled` a false.
- Hasta la 04.29, Gecko guardaba los valores de user.js en el `prefs.js` de cada perfil (también los editados a mano), donde se impondrían a los nuevos valores por defecto. [seamonkey-orbisdesk.cfg](../fixtures/browser/seamonkey-orbisdesk.cfg), instalado como `orbisdesk.cfg` junto a `seamonkey.exe` y nombrado por `general.config.filename`, borra esos cuatro valores guardados una vez por perfil, al final del arranque, y anota `orbisdesk.prefs-migration` = 1.
- Comprobación en el anfitrión con SeaMonkey 2.53.24: un perfil cuyo `prefs.js` tenía los cuatro valores activados los perdió en el primer arranque y recibió la marca. En el arranque siguiente, `layers.acceleration.disabled` a false puesto por el usuario se mantuvo.
- **Activar OpenGL desde la 04.30:** en about:config, poner `layers.acceleration.disabled` a false (y `webgl.disabled` a false para WebGL), y reiniciar SeaMonkey. about:support muestra Compositing OpenGL. Los pasos con `user.js` de "Desde 04.20" valen hasta la 04.29.

**Siguiente ejecución en la consola (04.30):** OpenGL activado como arriba, abrir SeaMonkey en una página y enviar el log. Las líneas `PWGL viewport` y `PWRECT` dicen qué tamaño era el de la ventana.

## SeaMonkey terminaba al abrir otro programa (04.27, 04.28)

En la 04.27, SeaMonkey terminó con la misma violación de acceso en las dos ejecuciones (run-0244, run-0245): `0xc0000005` en `nss3.dll+13c67d`, leyendo `7f82950d2`, en uno de sus hilos, y después su informe de fallos. La dirección está dentro de `nssckbi.dll` (cargada en `7F8230000`, tamaño `0x75000`), los certificados raíz integrados de NSS. Poco antes, el log tiene `PWGUEST own L"nssckbi.dll" ... leftovers=1 live=2`, justo al arrancar WFM. Así que `nssckbi.dll` se descargó mientras SeaMonkey todavía la usaba.

- **Por qué:** en cada arranque, kernelbase descarga las DLL que dejaron los invitados al terminar (W209). Conserva una DLL cuya ruta empieza por la carpeta de un invitado en marcha. NSS carga `nssckbi.dll` por su ruta 8.3, `C:\PROG~FBU\SEAM~E5Z\nssckbi.dll`, que no empieza por `C:\Program Files\SeaMonkey\`. Así que contaba como de nadie.
- **No son los cambios de 04.26:** la preferencia de la barra y la exclusión de MangoHud no tocan NSS ni el perfil. La 04.25 tenía la misma ruta; en sus ejecuciones no se abrió otro programa con SeaMonkey en marcha. Lo tenía todo programa cuyas DLL se cargan por una ruta corta, al arrancar otro programa y al terminar otro invitado.
- **Arreglo (04.28, no compilado):** [build-guest-hw.py](../tools/build-guest-hw.py) compara también por su forma larga (`GetLongPathNameW`) una carpeta o una ruta de DLL que tenga `~`. El log tiene entonces `PWGUEST own ...: by its 8.3 path in a live guest's folder` en lugar de la descarga. `process.c` de kernelbase compila para x86_64 e i386 con los comandos registrados del builder, con los mismos avisos que antes.
- **Traza de tamaño:** run-0244 y run-0245 tienen líneas `PWVK size` solo de juegos (todas 1280x720, imagen igual al área cliente). SeaMonkey no presentó por Vulkan en ellas, así que el desplazamiento de 34 píxeles sigue abierto.

**Prueba en la consola:** abrir SeaMonkey, después WFM (u otro programa) con SeaMonkey en marcha, y seguir navegando. SeaMonkey sigue en marcha, y el log tiene la línea `8.3 path`.

## La imagen de la GPU 34 píxeles demasiado arriba (captura de 04.25, 04.26)

Una captura de la consola con 04.25 y OpenGL activado (2026-11-18, 19:52) muestra SeaMonkey en YouTube:
- Falta la barra de menús, y la barra de navegación está cortada por arriba.
- Hay una banda negra bajo la barra de estado, dentro del marco de la ventana.
- El usuario cuenta que los clics actúan más arriba de donde se ven.

Así que la imagen que dibuja Gecko se muestra unos 34 píxeles más arriba que las coordenadas del propio Gecko. Medida en la captura, la banda mide 34 píxeles a la resolución 1280x720 de la consola. En run-0224 la misma ventana era `visible=(90,46)-(976,720)` con `client=(94,76)-(972,716)`: su ventana es 34 píxeles más alta que su área cliente (una barra de título de 26 píxeles y dos bordes de 4). La página seguía siendo la página de prueba anterior mientras YouTube cargaba; la barra de estado lo dice. Es una página que todavía no había cargado, no un cuadro viejo.

**Qué lado está mal:**
- El sink no recorta. `fit_image`, en `ps5drv.c` de win32u, escala una imagen a su área cliente, conservando sus proporciones y centrándola. Una colocación mal hecha daría bandas en dos lados o una imagen escalada, no una banda solo abajo con el contenido a su propia escala.
- El patrón encaja con las filas de abajo arriba de OpenGL. Si Gecko dibuja un cuadro 34 filas más alto que la imagen, sus 34 filas de arriba (la barra de menús) quedan por encima de la imagen, y sus últimas 34 filas se quedan vacías abajo. Lo mismo pasa si Zink da la vuelta a las filas con una superficie de dibujo 34 filas más alta que su imagen de swapchain. Los clics caen entonces 34 píxeles por debajo de lo que se muestra, que es lo que ve el usuario.
- Así que uno de estos tamaños es el alto de la ventana en lugar del del área cliente: el tamaño del compositor de Gecko, el de la superficie de dibujo de WGL de Mesa (`GetClientRect`) o la swapchain de Zink (el `currentExtent` de la superficie, que en win32u también es el área cliente). Los logs no dicen cuál. La única línea `PWVK layer` de la ventana de SeaMonkey es la de su primera swapchain (`image=878x640`, el área cliente; run-0234: `1280x694`, también el área cliente). SeaMonkey sustituyó esa swapchain enseguida (`PWVK forget … cleared=0`), y el tamaño de la nueva no se registró.
- En el host Windows, el mismo SeaMonkey, el mismo Mesa y el mismo perfil colocan todo bien. Así que es nuestro camino, no Gecko ni Zink por sí solos.

**Este cambio (no compilado), un diagnóstico:** [build-win32u-ps4.py](../tools/build-win32u-ps4.py) registra `PWVK size hwnd=… swapchain=… image=WxH client=WxH window=WxH` cada vez que cambia el tamaño de la imagen, del área cliente o de la ventana, con `differs` cuando la imagen no tiene el tamaño del área cliente, en los 64 primeros cambios del título. `vulkan.c` de win32u compila con la receta registrada, con los mismos tres avisos que antes.

**Siguiente ejecución en la consola:** OpenGL activado. Abrir SeaMonkey y después YouTube, y enviar el log y una foto. `differs` con una imagen tan alta como la ventana apunta a la swapchain. Una imagen igual al área cliente, con el dibujo todavía demasiado arriba, apunta al tamaño de dibujo de Gecko o de WGL.

## Otros cambios de 04.26 para SeaMonkey

- La barra roja "Your copy of SeaMonkey is old and probably has known security flaws" ya no aparece. Con las actualizaciones apagadas, `nsSuiteGlue.js` de SeaMonkey la muestra al arrancar en cuanto la compilación tiene 90 días. [seamonkey-user.js](../fixtures/browser/seamonkey-user.js) pone `app.updatecheck.override` a `true`, su "no mostrar nunca".
- MangoHud no se muestra nunca para SeaMonkey, y la fila de RAM de MangoHud muestra ahora GiB ([MangoJuice](MANGOJUICE-es.md)).

## El vídeo se queda negro con OpenGL activado (04.26)

El usuario informa de que con la composición por OpenGL (04.25) la zona del vídeo se ve negra en YouTube y en otros sitios. Run-0234 muestra el decodificador en marcha: aquí no hay ningún decodificador de Media Foundation (`h264_decoder_create GStreamer doesn't support H.264`), y Gecko decodifica con su propio ffvpx (`mozavcodec.dll` arranca sus hilos de decodificación). Así que los cuadros se decodifican en la CPU y se entregan al compositor como tres planos (Y, Cb, Cr).

**Reproducción en el host (Windows 11, AMD; solo como referencia).** SeaMonkey 2.53.24 usó el `opengl32.dll` y el `libgallium_wgl.dll` de 64 bits de esta compilación con el `user.js` de la consola. Una página de prueba grabó un canvas animado con `MediaRecorder` (VP8) y lo reprodujo en un `<video>`, junto al mismo vídeo dibujado en un canvas.
- Composición Basic: el vídeo se ve bien.
- OpenGL con llvmpipe de Mesa: el vídeo se ve bien.
- OpenGL con Zink: el vídeo del canvas se ve bien, así que la decodificación está bien. El elemento `<video>` muestra solo su brillo, teñido de magenta y rosa. Los colores medidos encajan con Cb y Cr leídos los dos a escala completa (1.0) por el shader YCbCr de Gecko, mientras que Y está bien.
- No cambia al ocultar `GL_ARB_texture_rg` (Gecko sube entonces `GL_LUMINANCE` en lugar de `GL_R8`), con GL 2.1, al ocultar las texturas rectangulares, los objetos de sincronización o los pixel buffer objects, ni con `ZINK_DEBUG` `sync`, `noopt`, `optimal_keys`, `gpl`, `noshobj`, `compact`, `nobgc` o `nopc`.
- Unos programas nativos pequeños sobre el mismo Zink funcionan bien: tres planos con los tamaños, pasos de fila, alineaciones y formatos de Gecko, actualizados en cada cuadro con `glTexSubImage2D`, el texto del shader YCbCr de Gecko sacado de `xul.dll` con sus uniforms, y otros programas dibujados entre medias. Así que todavía no se ha encontrado la secuencia de GL que usa Gecko y estos programas no.

Así que el fallo está en cómo trata Zink lo que hace el compositor OpenGL de Gecko para el vídeo, no en la decodificación ni en Gecko solo. En el RADV de la consola se ve negro, y con el driver del host, magenta. Es la misma familia de síntomas, pero no está demostrado que la causa sea la misma. Este cambio no lo arregla.

**Siguiente paso:** grabar las llamadas GL de Gecko en el host (una traza de API de la ejecución de arriba, con la aprobación del usuario para descargar el trazador), reproducirlas en Zink y en llvmpipe, y recortar la traza hasta la llamada que difiere.

## Run-0234: el fallo del segundo arranque es de MangoHud (04.26)

**MangoHud no se muestra nunca para SeaMonkey (04.26).** Es la decisión del usuario: [MangoJuice](MANGOJUICE-es.md) explica la exclusión y el arreglo de mostrar y ocultar que vino con ella.

Run-0234 es 04.25 con OpenGL activado, en `reports/wine-hardware-w303/physical/20261118T215511Z/`. El primer arranque presentó fotogramas de la GPU y salió con estado 0. El segundo arranque terminó a los 6 s más o menos, como en run-0218, run-0222 y run-0223.

**Lo que capturó `PWTOP`:**
- Una excepción no controlada con código `0x20474343` en el hilo `056c`, que empieza en `xul.dll+8e8ff0` (el inicio de hilo de Gecko; este es el del compositor). Ese código es el que lanza el runtime de C++ de llvm-mingw para una excepción de C++. Así que una excepción de C++ llegó al filtro de nivel superior sin ningún `catch` para ella.
- Justo antes, el hilo `056c` había arrancado tres hilos desde `libgallium_wgl.dll`: los hilos de cola de Zink. Así que estaba dentro de la preparación de GL, donde Zink crea su dispositivo Vulkan y su swapchain a través de la capa de MangoHud.
- La pila alrededor es `libMangoHud.dll` y ucrtbase. Contra la DLL compilada (su SHA-256 coincide con el manifiesto de W303), las entradas de `libMangoHud.dll` son el código de lanzamiento de libunwind y libc++abi, más `typeinfo for std::regex_error`. El objeto lanzado es un `std::regex_error`.
- Después vino el informe de fallos de Gecko (`crashreporter.exe`, `minidump-analyzer.exe`) y luego `TerminateProcess( own process, 1 )`. Run-0218, run-0222 y run-0223 terminaron igual, en el hilo del compositor, sin `PWFAULT` y sin `PWCRT`. Una excepción de C++ no capturada lo explica, porque no produce ninguna violación de acceso y no pasa por ningún gestor de ucrt. Así que lo más probable es que fuera el mismo fallo.

**Por qué MangoHud lanza la excepción solo en el segundo arranque:**
- La compilación de Windows de MangoHud tiene un solo `std::regex`: `remove_parentheses` en `src/file_utils.cpp`. `overlay_CreateSwapchainKHR` lo llama en cada swapchain para limpiar el nombre de la GPU. El patrón es una constante y es válido.
- La regex de libc++ clasifica los caracteres del patrón con la faceta `ctype<char>` de `std::locale::classic()`. Con el runtime de C de Microsoft, libc++ llena esa faceta una sola vez con `__pctype_func()`, la tabla de caracteres de la configuración regional del hilo que llama en ese momento. La preparación estática de iostream de MangoHud lo hace al cargarse la DLL.
- MangoHud sigue cargada de un invitado al siguiente. SeaMonkey cambia la configuración regional de ucrt al arrancar, dejando `"C"`, y el ucrt de Wine reserva memoria para la tabla de toda configuración regional salvo `"C"`. Así que el puntero que guardó MangoHud puede sobrevivir a su tabla. Si entonces `(` o `)` se leen como letra o dígito, el analizador lanza `regex_error`.
- El segundo paso se deduce, no se observó: el log no muestra qué tabla tenía MangoHud. Pero un patrón constante y válido solo puede fallar al analizarse si esa tabla cambió. El primer arranque creó las mismas swapchains sin ninguna excepción.

**Este cambio (no compilado):**
- [patch-mangohud-gpu-name.py](../tools/vk-h0/patch-mangohud-gpu-name.py): `remove_parentheses` pasa a ser un bucle. Cada `(` con un `)` después se quita hasta ese `)` incluido, y un `(` sin cierre se queda. Es el resultado de la regex, sin configuración regional. Con 12 nombres da el mismo texto que `std::regex_replace`, y compila con llvm-mingw para x86_64 e i686 con `-Wall -Wextra`, sin avisos.
- [build-mangohud.sh](../tools/vk-h0/build-mangohud.sh) lo ejecuta y registra `src/file_utils.cpp` en su registro de compilación. [build-mangohud-i386.sh](../tools/vk-h0/build-mangohud-i386.sh) comprueba la marca en el árbol que copia, así que los dos HUD lo llevan.
- [build-wine-hardware.py](../tools/build-wine-hardware.py) rechaza un árbol de MangoHud de 32 o 64 bits sin la marca, y registra el hash del parche.
- No se tocan los ajustes de MangoHud, sus atajos ni el mostrar y ocultar del overlay. El archivo de MangoJuice sigue aplicándose a todos los HUD.
- Los demás usos de esa faceta por parte de libc++ en MangoHud (por ejemplo `>>` de un flujo a una cadena) todavía pueden leer una tabla caducada. No lanzan excepciones, y ninguno está en este camino.

**El `PWFAULT` en `00000007F98C0705` es la misma consecuencia que antes.** `xul.dll` se volvió a cargar en `00000007F8930000`, así que la dirección es `xul.dll+0xF90705`, el retorno de `DwmFlush` en el hilo de vsync. Al hilo `0568` no se le pudo enviar la señal (`PWBOOT thread_signal unavailable thread=0568 sig=3`), y volvió al `xul.dll` ya desmapeado después del fallo. Es el mismo problema de cierre que en run-0218 y run-0222, y lo provocó el fallo. No es un segundo error en esta ejecución.

**Siguiente ejecución en la consola, con este cambio compilado:** OpenGL activado. Arrancar SeaMonkey, cerrarlo, arrancarlo otra vez y cerrarlo otra vez. Después arrancar un juego de 32 bits y uno de 64 bits con el HUD, y mostrarlo y ocultarlo con Shift+F12. No debería aparecer ningún `PWTOP … code=0x20474343`, y el HUD debería mostrar el nombre de la GPU sin la parte entre paréntesis.

## 04.19 en la consola (run-0218.log)

La ejecución es `reports/wine-hardware-w303/physical/20261117T215143Z/run-0218.log`.

- **Primer arranque (módulo `0x101720000`, línea 1733): OpenGL funcionó.**
  - El hilo `01c8` carga `opengl32.dll` y `libgallium_wgl.dll` de system32. Los avisos `LdrGetProcedureAddress "wgl…ARB"/"gl…" not found in Opengl32.dll` son Gecko buscando primero por exportación los puntos de entrada de extensiones y de GL 2+. Los obtiene con `wglGetProcAddress`, como en Windows.
  - La ventana se presenta por la cadena de intercambio de Zink (líneas `PWVK forget swapchain`), con pantalla completa y el overlay. La capa de 64 bits de MangoHud se engancha (`mangohud … guest64=1`).
  - El navegador sale con estado 0. Al salir, `PWGUEST gl … result=1` y `PWVK guest_release … gl_devices=1 gl_memories=23 gl_bytes=33868200`: se liberó el dispositivo de Zink y volvieron 34 MB.
- **Segundo arranque (módulo `0x101410000`): falló antes de su ventana.**
  - A los 7,3 s, sin ventana todavía, el propio gestor de fallos de Gecko (hilo `0308`) arranca `crashreporter.exe`, y el invitado termina con `TerminateProcess( own process, 1 )`.
  - Gecko trató esa excepción él mismo, así que el log no tiene `PWFAULT` para ella. Dónde falló está en el minidump que escribió crashreporter.
  - En ese arranque seguían cargados `opengl32.dll`, `libgallium_wgl.dll` y `libMangoHud.dll` de 64 bits (`gl=`, `gallium=` y `hud=` distintos de 0). Mesa tenía una pantalla nueva después de la liberación, y win32u había liberado el dispositivo de Zink anterior.
- **El `PWFAULT … address=00000007F9840705 access=8` es una consecuencia, no la causa.**
  - Esa dirección es `xul.dll`+0xF90705, la dirección de retorno después de `call DwmFlush` (`dwmapi`). Es el hilo de vsync de Gecko (`0374`) esperando en `DwmFlush`.
  - Al hilo no se le pudo enviar la señal (`thread_signal unavailable thread=0374`). Seguía en `DwmFlush` cuando se desmapeó `xul.dll`, y luego volvió a una memoria que ya no estaba: un fallo de ejecución.
  - Esto puede pasar siempre que se termina un invitado de Gecko, también con Basic. Es un problema aparte del cierre de invitados.
- **Comprobación en el anfitrión (referencia):** un programa de 64 bits hace los pasos WGL de Gecko con las DLL de Mesa de W303: un contexto de prueba, `wglCreateContextAttribsARB`, 30 fotogramas en una ventana, y contextos sin borrar, como con hilos terminados. Después llama a `pw_wgl_release_screen` y lo repite todo, tres rondas. Las tres rondas funcionan (`release=1`). Así que la liberación de Mesa por sí sola no reproduce el fallo. No reproducido en el anfitrión: que win32u libere el dispositivo de Zink anterior, y la capa de MangoHud de 64 bits que sigue cargada entre los dos arranques.

Para encontrar la causa hace falta el informe de fallo del segundo arranque:
- `C:\users\orbis\AppData\Roaming\Mozilla\SeaMonkey\Crash Reports\pending\` (`/data/wine-prefix/drive_c/users/orbis/AppData/Roaming/Mozilla/SeaMonkey/Crash Reports/pending/`): el archivo `.dmp` y su archivo `.extra`;
- o, en SeaMonkey, `about:crashes`, fotografiado.

## Los informes de fallo y la zona azul (run-0218, run-0219)

**Informes de fallo.** `reports/wine-hardware-w303/physical/20261117T220342Z/seamonkey-minidumps/` tiene dos archivos `.extra` y dos archivos `.dmp` de 0 bytes.
- **`335276ed…`: el segundo arranque de run-0218.**
  - Falló 4 s después de arrancar (`StartupTime` 1794952528, `CrashTime` 1794952532).
  - Su `ThreadIdNameMapping` llama al hilo 884 (0x374) `WindowsVsyncThread`, el hilo del `PWFAULT` posterior.
  - Adaptador `0x1002`/`0x9920`, controlador `35.0.21025.1024`.
- **`c05db0a6…`: otro fallo, 67 s después** (`SecondsSinceLastCrash`). Adaptador `0x0000`/`0x0000`.
- **Ninguno de los dos tiene `MozCrashReason` ni `GraphicsCriticalError`.** Así que no fue una aserción de Gecko (`MOZ_CRASH`/`MOZ_RELEASE_ASSERT`) ni un error gráfico que Gecko informara.
- `Notes` muestra `OMTP+4`, `D2D1.1-`, `WR-`.

**El fallo del segundo arranque ocurrió antes de tocar OpenGL.**
- Ese arranque no tiene ninguna de las líneas `LdrGetProcedureAddress … Opengl32.dll` que la preparación WGL de Gecko imprime en cada navegador nuevo. Falló a los 4 s; la ventana del primer arranque tardó 12 s.
- No se registró ningún `PWFAULT` para él. El trazador (`ps4_guest_fault_trace`, el primero de la cadena de gestores) solo toma violaciones de acceso y excepciones de coma flotante. Así que la excepción tenía otro código: un fast fail (un `abort`, un fallo de `/GS`, el parámetro inválido de ucrt), una instrucción ilegal, un desbordamiento de pila, una corrupción del heap o un punto de ruptura.
- La tomó el informador de fallos de Gecko, y su escritor de minidumps (el `MiniDumpWriteDump` del dbghelp de Wine sobre un proceso que es explorer más todos los invitados) no escribió nada.
- Lo que tenía el segundo arranque y no tiene una ejecución con Basic: `opengl32`/`libgallium_wgl` de Mesa y `libMangoHud.dll` de 64 bits residentes desde el primer arranque, una pantalla de Mesa reiniciada por `pw_wgl_release_screen`, y la memoria del dispositivo de Zink anterior liberada por win32u.

**El `PWFAULT` en `00000007F9840705` (acceso 8)** es el hilo de vsync que vuelve de `DwmFlush` al `xul.dll` ya desmapeado después del fallo (ver arriba). Es una consecuencia.

**La zona azul.**
- En run-0219, el compositor GL de SeaMonkey presenta directamente en su ventana de primer nivel (`PWVK forget swapchain=… hwnd=0xa00c8 window=0xa00c8`). Este SeaMonkey tiene una `MozillaCompositorWindowClass`, pero nada en el log muestra una ventana así.
- win32u apila los píxeles de CPU de cada ventana (el marco y el título de Wine incluidos) y después su imagen Vulkan sobre el área cliente (`ps5_vulkan_frame`, `fit_image`). El log de release no tiene ninguna línea con estos rectángulos, así que no puede mostrar qué tapa la barra de título: una ventana propia, o la imagen colocada sobre el marco.
- En OrbisDesk no hay ningún componente "decorador". El azul es muy probablemente el color del título de Wine.

**Diagnósticos añadidos en 04.20:**
- [build-win32u-ps4.py](../tools/build-win32u-ps4.py): el primer fotograma de cada cadena de intercambio nueva en una ventana registra `PWVK layer hwnd=… window=… child=… image=WxH visible=… client=… passed=… at=…`, y se listan las dos pilas siguientes que se entregan al sink (`PWSINK stack i/n … rect=… flags=…`). La imagen Vulkan es `flags=0x1`.
- [build-guest-hw.py](../tools/build-guest-hw.py): `PWFAULT` también traza `0xc0000409`, `0xc000001d`, `0xc0000096`, `0xc00000fd`, `0xc0000374`, `0xc0000420` y `0x80000003`, todavía las 8 primeras del título. En un fast fail, `access=` es su código `FAST_FAIL`.

**Siguiente ejecución en la consola.** Hacen falta los dos pasos para un arreglo.
1. **Sin compilar:** activar la opción en el `user.js` del perfil, y escribir `+seh,+loaddll,warn+debugstr` en `C:\orbis\winedebug.txt` (`/data/wine-prefix/drive_c/orbis/winedebug.txt`).
   - Arrancar SeaMonkey, cerrarlo y volver a arrancarlo.
   - Fotografiar la zona azul, con el HUD oculto.
   - `+seh` registra cada excepción con su código y su dirección. `+loaddll` da la dirección base de cada DLL, para situar la dirección en un módulo. `warn+debugstr` muestra lo que Mesa y Gecko imprimen con `OutputDebugString`.
   - Borrar `winedebug.txt` después.
2. **Con este cambio compilado:** los mismos pasos. Leer `PWVK layer` y las líneas `PWSINK stack` para la zona azul, y `PWFAULT` para el fallo.

## Run-0223: la ejecución de trazas en 04.21

Run-0223 es 04.21 con OpenGL activado en el `user.js` de la consola. Se arrancó SeaMonkey, se cerró y se volvió a arrancar. Está en `reports/wine-hardware-w303/physical/20261118T011404Z/`, y su informe de fallo es `ff451770-…` en `20261117T220342Z/seamonkey-minidumps/` (el `.dmp` vuelve a estar vacío).

**El segundo arranque falló a los 3 s, antes de cualquier llamada WGL.**
- No hay búsquedas en `Opengl32.dll` después del segundo arranque, como en run-0218. Run-0222 pasó de las búsquedas `wgl…ARB`. Así que el fallo no está ligado a un punto de la preparación de Mesa.
- `StartupTime` 1794964308, `CrashTime` 1794964311.
- El hilo gestor de Breakpad (0x218, sin nombre en `ThreadIdNameMapping`) arrancó `crashreporter.exe` y llamó a `TerminateProcess( own process, 1 )`.

**Ninguna línea `PWCRT` y ninguna línea `PWFAULT` antes del fallo.**
- El ucrtbase de 04.21 tiene el código `PWCRT` (en `system32` y `x86_64-windows`). El `ucrtbase.dll` propio de SeaMonkey no se carga: sus archivos `api-ms-win-crt-*` se resuelven al que ya está en el proceso.
- Así que ningún hilo invitado tuvo una violación de acceso, una excepción de coma flotante o un código fatal trazado, y ninguno pasó por los caminos de ucrt de parámetro inválido, llamada virtual pura o `abort`.
- Las dos trazas solo cubrían hilos invitados. El filtro de nivel superior de Gecko y sus gestores de ucrt son del proceso: un hilo de ningún invitado (de explorer, del grupo de hilos de ntdll, un hilo compartido por módulos) también llega a ellos. Es lo que queda, y 04.21 no lo traza.

**La salida del primer arranque dejó un hilo en marcha y no esperó a ninguno.**
- `PWBOOT thread_signal unavailable thread=0188 sig=3`: a uno de los otros 103 hilos de SeaMonkey no se le pudo enviar la señal al terminarlo. Estaba en marcha fuera del servidor, así que siguió vivo hasta su siguiente llamada al servidor. Run-0222 muestra lo mismo (`018c`).
- `other_threads_wait=4294967295 count=103`: `WaitForMultipleObjects` admite como mucho 64 handles y falló de inmediato. Todos los invitados con más de 64 hilos han descargado sus módulos sin esperar (el archivo tiene este resultado en las 144 salidas así, cuentas de 69 a 255).
- El segundo arranque mapeó `xul.dll` en la misma dirección, `00000007F8930000`.

**La zona azul.** Run-0223 tiene la misma línea `PWVK layer` que run-0222: la imagen de la GPU cubre exactamente el área cliente. MangoHud dibujó encima (`PWOVERLAY mangohud in_front=1 presented=0x600b4 guest64=1`). `screen.png` es una captura anterior y los fotogramas son fotogramas negros de arranque, así que sigue sin haber foto. Sin ella, el azul no se puede distinguir del título azul de Wine.

**Este cambio (no compilado):**
- [build-guest-hw.py](../tools/build-guest-hw.py): la salida de un invitado espera a sus otros hilos de 64 handles en 64, dentro de los mismos 2 s. Esto arregla la espera fallida, pero no termina un hilo al que no se puede enviar la señal.
- `PWGUEST thread_starts module=… id=módulo+desplazamiento …`: el inicio de cada hilo del invitado que sale, seis por línea, para que la línea `thread_signal unavailable` nombre su código.
- `PWTOP n=… thread=… guest=… code=… address=… start=… filter=…` y hasta 12 líneas `PWTOP … stack[i] módulo+desplazamiento`: lo que llegue al filtro de nivel superior, en cualquier hilo, antes de llamarlo. Las 8 primeras del título.
- `PWCRT` cubre ahora todos los hilos donde hay un gestor, y `abort`, con `guest=` y `start=`.
- Las dos unidades de kernelbase y las dos de ucrtbase compilan para x86_64 e i386 con la receta del builder y `-Wall`, sin avisos nuevos.

**El valor por defecto sigue siendo Basic.** La consola conserva el `user.js` con GPU para una ejecución más.

**Siguiente ejecución en la consola, con este cambio compilado:** OpenGL activado. Arrancar SeaMonkey, cerrarlo y volver a arrancarlo. Leer `PWTOP` (o `PWCRT`) para el hilo que entró en el informador de fallos, y la entrada `thread_starts` del hilo sin señal. Si la ventana está azul, fotografiarla con el HUD oculto.

## Run-0222: los diagnósticos en 04.20

Run-0222 es 04.20 con OpenGL activado en el `user.js` de la consola. Se arrancó SeaMonkey, se cerró y se volvió a arrancar. Está en `reports/wine-hardware-w303/physical/20261117T233219Z/`, y su informe de fallo es `45680939-…` en `seamonkey-minidumps/`.

**La imagen de la GPU está bien colocada.**
- `PWVK layer hwnd=0xb00b4 window=0xb00b4 child=0 image=878x640 visible=(90,46)-(976,720) client=(94,76)-(972,716) … at=(94,76)-(972,716)`.
- La pila siguiente tiene cinco capas: el escritorio, dos ventanas del escritorio, el marco de SeaMonkey (`(90,46)-(976,720)`, sus píxeles de CPU) y la imagen de la GPU (`flags=0x1`) exactamente sobre el área cliente. El sink dibuja las capas opacas, sin mezcla.
- Así que la imagen de la GPU no tapa la barra de título, y nada más tapa la ventana. Una zona azul, si el usuario la vio, está dentro de los píxeles del propio marco de SeaMonkey (el título de Wine es azul en este tema) o dentro de la imagen de la GPU. Solo una foto puede decir cuál.
- En sus primeros 7 s, SeaMonkey presentó 8 fotogramas (`PWFPS … presents=8`).

**El segundo arranque terminó en el hilo Compositor de Gecko, en la preparación WGL de Mesa.**
- El `ThreadIdNameMapping` del `.extra` llama al hilo 664 (0x298) `Compositor` y al 660 (0x294) `WindowsVsyncThread`.
- El hilo 0x298 imprimió las búsquedas `wgl…ARB` que Gecko hace cuando ya tiene un primer contexto WGL activo. En el primer arranque las seguían las búsquedas de puntos de entrada `gl…`, después de crear el contexto propio del compositor. En el segundo no siguió nada: arrancó el informador de fallos.
- El segundo arranque de run-0218 terminó antes, antes de las búsquedas `wgl…ARB`. Los dos terminaron dentro de la preparación WGL de Mesa, en puntos distintos.
- No se registró ningún `PWFAULT`, aunque 04.20 traza violaciones de acceso, excepciones de coma flotante, fast fails, instrucciones ilegales y privilegiadas, desbordamientos de pila, corrupción del heap, fallos de aserción y puntos de ruptura. Así que ninguna excepción llegó a los gestores. El informador de fallos de Gecko tiene tres entradas que no lanzan ninguna, todas por ucrt (compartido por todos los invitados, Mesa y MangoHud): el gestor de parámetro inválido, el de llamada virtual pura y el `SIGABRT` de `abort`.
- Después del informe, el hilo 0x220 del informador terminó SeaMonkey con `TerminateProcess( own process, 1 )`.

**Lo que el segundo arranque encuentra del primero:**
- `opengl32`/`libgallium_wgl` de Mesa, fijados, con su pantalla liberada cuando quedaba un contexto (`PWGUEST gl … result=1 contexts=1`).
- El `libMangoHud.dll` de 64 bits, una capa Vulkan de Zink.
- El estado de proceso de ucrtbase.
- El mundo de 32 bits reinicia Mesa después de `contexts=1` (Alan Wake en run-0190). Este es el primer programa de 64 bits que lo hace.

**El `PWFAULT` en `00000007F98C0705` es el mismo que en run-0218.** `xul.dll` se cargó en `00000007F8930000` las dos veces. Así que la dirección es `xul.dll+0xF90705`, el retorno de `DwmFlush` en el hilo de vsync. A ese hilo no se le pudo enviar la señal (`PWBOOT thread_signal unavailable thread=0294`) y volvió al `xul.dll` ya desmapeado. Es una consecuencia del fallo.

**Diagnósticos de este cambio (no compilados):**
- [build-guest-hw.py](../tools/build-guest-hw.py): en un hilo invitado, `_invalid_parameter`, `_get_purecall_handler`, `_purecall` y `abort` de ucrtbase registran `PWCRT <camino> thread=… handler=…` y hasta 12 marcos como `módulo+desplazamiento`, los 8 primeros del título.
- `PWFAULT` también traza `0xc0000417`, el parámetro inválido de ucrt sin gestor.
- Las dos unidades de ucrtbase compilan para x86_64 e i386 con la receta del builder y `-Wall`, sin avisos.

**El valor por defecto sigue siendo Basic.** La consola tiene el `user.js` con GPU de esta ejecución. Conservarlo para la siguiente ejecución de diagnóstico y después volver a poner el seguro.

**Siguiente ejecución en la consola, con este cambio compilado:** OpenGL activado, arrancar SeaMonkey, cerrarlo y volver a arrancarlo. Leer las líneas `PWCRT`; el marco siguiente a los de ucrtbase nombra el módulo que lo llamó. Fotografiar la ventana si está azul.

## Desde 04.20: Basic por defecto, OpenGL opcional

- [seamonkey-user.js](../fixtures/browser/seamonkey-user.js) vuelve a poner `layers.acceleration.disabled` a true y `layers.acceleration.force-enabled` a false, los ajustes gráficos de 04.18.
  - Los dos valores se ponen explícitamente, porque el user.js de 04.19 guardó false y true en el `prefs.js` de cada consola, y un user.js posterior los heredaría.
  - El bloqueo de Direct3D 11 se mantiene.
- [seamonkey-gpu.js](../fixtures/browser/seamonkey-gpu.js) sigue instalado. Sin la opción activada no hace nada.
- **Activarlo, para pruebas:** en el `user.js` del perfil (`/data/wine-prefix/drive_c/users/orbis/AppData/Roaming/Mozilla/SeaMonkey/Profiles/orbis/user.js`), cambiar las dos líneas a `layers.acceleration.disabled` false y `layers.acceleration.force-enabled` true. Cada subida sustituye user.js, así que después hay que volver a activarlo.
- Con la opción activada, el primer arranque de una sesión fue bien en run-0218. Lo que falló fue arrancar SeaMonkey por segunda vez en la misma sesión.

## Los tres caminos

| Camino | Veredicto |
| --- | --- |
| Direct3D 11 a través de DXVK | No se usa. En el proceso de explorer, el `d3d11.dll` de system32 es el de DXVK, y `dxgi` es el builtin de Wine (`WINEDLLOVERRIDES=…dxgi=b`). El compositor D3D11 de Pale Moon ahí (W204/W205) registró `VK_KHR_EXTERNAL_MEMORY_WIN32 not supported` y `D3D11DXGIKeyedMutex::AcquireSync: Not supported`, nunca presentó un fotograma y se colgó al abrir una segunda pestaña. Por eso los programas Direct3D 11 de 64 bits corren solos (W190/W191), y un navegador no puede. |
| Capas Direct3D 9 | No existen en este Gecko. El `xul.dll` de SeaMonkey 2.53 no tiene `layers.prefer-d3d9`: el compositor D3D9 se quitó antes de la plataforma de Firefox 60. |
| OpenGL a través de WGL/Zink de Mesa | **Se usa.** El `opengl32.dll` de 64 bits de system32 es el de Mesa (Zink sobre el RADV enlazado). OpenGL ya funciona en invitados de 64 bits, y el kernelbase de Wine libera el dispositivo de Zink cuando termina un invitado (`pw_wgl_release_screen`, run-0178). El compositor OpenGL de Gecko no está activado por defecto en Windows. `layers.prefer-opengl` lo activa. |

## El cambio

- [seamonkey-user.js](../fixtures/browser/seamonkey-user.js):
  - `layers.acceleration.disabled` a false y `layers.acceleration.force-enabled` a true. La aceleración queda activada y forzada por encima de la lista de bloqueo de Gecko, que no conoce el adaptador de Wine.
  - `gfx.blacklist.layers.direct3d11` = 3 (dispositivo bloqueado), con el identificador de fallo `ORBISDESK_NO_D3D11`. Eso desactiva la composición D3D11, Direct2D y ANGLE sobre D3D11 antes de que se cargue `d3d11.dll`. user.js lo vuelve a poner en cada arranque, por encima de una lista de bloqueo descargada.
  - Sin cambios: Direct2D desactivado, Skia para canvas y contenido, sin decodificación de vídeo por hardware, WebGL desactivado, ANGLE desactivado.
- [seamonkey-gpu.js](../fixtures/browser/seamonkey-gpu.js): `layers.prefer-opengl` a true. [build-wine-hardware.py](../tools/build-wine-hardware.py) lo instala como `C:\Program Files\SeaMonkey\defaults\pref\orbisdesk-gpu.js`.
  - Es el valor por defecto de SeaMonkey, no un valor de user.js. Así, un cambio en about:config se guarda en el `prefs.js` de la consola y sobrevive a los arranques y a las subidas.
  - Gecko copia los valores de user.js en `prefs.js`, así que las consolas ya tienen ahí `layers.acceleration.disabled` a true. Por eso el interruptor es una preferencia que nunca estuvo en user.js.

El orden de motores de Gecko es OpenGL (solo con `layers.prefer-opengl`), después D3D11 (aquí bloqueado) y después Basic.

## Desactivarlo (04.19)

Así funcionaba 04.19. Desde 04.20 el valor por defecto es Basic; ver arriba.


En SeaMonkey, abrir `about:config`, poner `layers.prefer-opengl` a `false` y reiniciar SeaMonkey. about:support muestra entonces Composición `Basic`. "Restablecer" en la misma preferencia vuelve a activar OpenGL.

Si SeaMonkey no llega tan lejos, borrar por FTP `/data/wine-prefix/drive_c/Program Files/SeaMonkey/defaults/pref/orbisdesk-gpu.js`. Sin ese archivo el valor por defecto es false, y SeaMonkey usa Basic.

## Prueba en el anfitrión (Windows 11, AMD Radeon, controlador Vulkan de AMD)

Es solo una referencia. Ejecuta SeaMonkey 2.53.24 (el archivo fijado) con `opengl32.dll` y `libgallium_wgl.dll` de 64 bits de W303 junto a `seamonkey.exe`, y `GALLIUM_DRIVER=zink`.

Los datos salen del propio about:support: un script de autoconfig, solo para el anfitrión, escribe a los 20 s la instantánea de gráficos de `Troubleshoot.jsm` en un archivo, con la ventana minimizada.

| Configuración | Composición | Notas |
| --- | --- | --- |
| user.js de 04.18 | Basic | `HW_COMPOSITING` desactivado por preferencia; `OMTP` disponible, 4 hilos de pintado |
| aceleración activada, D3D11 sin bloquear | Direct3D 11 | el controlador del sistema: Gecko carga `d3d11.dll` desde system32, así que el DXVK junto al exe no se usa (no hay log de DXVK) |
| + `layers.prefer-opengl`, D3D11 sin bloquear | Direct3D 11 | composición OpenGL forzada, pero se elige D3D11 |
| + D3D11 bloqueado (este cambio) | **OpenGL** | módulos: `opengl32.dll` y `libgallium_wgl.dll` de SeaMonkey, `vulkan-1.dll`, el controlador Vulkan de AMD; ningún `d3d11.dll` |
| lo mismo + WebGL forzado | OpenGL | renderizador WebGL 1 `Mesa -- zink Vulkan 1.3(AMD Radeon (TM) Graphics (AMD_PROPRIETARY))`, versión `4.6 (Compatibility Profile) Mesa 26.0.8` |
| este cambio, Zink roto (`GALLIUM_DRIVER=nosuchdriver`) | **Basic** | registro de fallos: `[OPENGL] Failed to init compositor with reason: FEATURE_FAILURE_OPENGL_CREATE_CONTEXT` |
| este cambio con `layers.prefer-opengl` a false en `prefs.js` | **Basic** | el interruptor |
| este cambio con el `prefs.js` antiguo (`layers.acceleration.disabled` a true) | OpenGL | gana user.js |

Memoria de trabajo justo después de arrancar: unos 150–175 MB con Basic, y 285–305 MB con OpenGL a través de Zink (incluido el controlador del anfitrión). La ventana estaba minimizada, así que estas ejecuciones prueban la inicialización y la elección del motor, no el dibujo ni la velocidad.

## Prueba en la consola (04.19, o 04.18 con los dos archivos)

En 04.18 no hace falta compilar nada. Sustituir el `user.js` del perfil (`/data/wine-prefix/drive_c/users/orbis/AppData/Roaming/Mozilla/SeaMonkey/Profiles/orbis/user.js`) por el archivo de este cambio, y añadir `orbisdesk-gpu.js` en `/data/wine-prefix/drive_c/Program Files/SeaMonkey/defaults/pref/`.

1. Crear `/data/orbisdesk/framegen.txt` con el texto `timing`. Añadir un `/data/orbisdesk/trace.txt` vacío solo en una compilación con el arreglo de trace.txt ([respuesta](SEAMONKEY_RESPONSIVENESS-es.md)).
2. Arrancar OrbisDesk, abrir SeaMonkey e ir a `about:support`. Fotografiar:
   - **Gráficos → Composición**: se espera `OpenGL`; `Basic` significa que volvió atrás (ver el registro de fallos).
   - **GPU #1**: descripción, ID del fabricante, ID del dispositivo, versión del controlador. Es lo que Gecko lee de Wine.
   - **Renderizador del controlador WebGL 1**: se espera `WebGL is currently disabled.`
   - **Decisiones**: las líneas `OPENGL_COMPOSITING` y `D3D11_COMPOSITING` (se espera `#BLOCKLIST_ORBISDESK_NO_D3D11`).
   - **Registro de fallos**, si lo hay.
3. YouTube, como en run-0207: 30 s de un vídeo reproduciéndose en la página, 15 s de desplazamiento, y luego pantalla completa durante 10 s y vuelta.
4. Abrir y cerrar un menú y una ventana emergente de ayuda, y abrir una segunda pestaña (el compositor D3D11 de Pale Moon se colgó ahí, W205).
5. Con SeaMonkey delante, mostrar y ocultar el overlay y MangoHud.
6. Cerrar SeaMonkey, volver a abrirlo, comprobar otra vez Composición y cerrarlo. Después abrir otro programa (glxgears o vkcube) y cerrarlo.
7. Desactivarlo en about:config (`layers.prefer-opengl` a false), reiniciar SeaMonkey y comprobar que Composición dice `Basic`. Después restablecer la preferencia.
8. Recoger el log.

Qué leer en el log:
- `PWGUEST load_begin … gl= gallium=`: 0 en el primer arranque, distinto de 0 una vez que Mesa está cargado (se queda residente).
- `PWGUEST gl module=… result=…` al salir SeaMonkey: `result=1` liberó el dispositivo de Zink; `kept: … other guests running` cuando había otro invitado abierto.
- `PWVK guest_memory … direct_free=` en cada arranque y después de cada salida. Debería recuperarse al cerrar.
- Ninguna línea `DXVK` ni `d3d11` de SeaMonkey.
- `PWFG timing` frente a run-0207 (57–58 fotogramas/s con vídeo en la página; 10–45 al desplazar o cargar).
- `PWHUNG` / `PWDUMP` si una ventana deja de responder.

## ¿Es seguro para 04.19?

Razonablemente, con el interruptor, pero solo después de una ejecución en la consola con los pasos de arriba.

- La vuelta atrás cuando no se puede crear el contexto OpenGL está probada en el anfitrión. Una pérdida del dispositivo Vulkan o un bloqueo de Zink más tarde no tiene vuelta atrás. Las protecciones propias de Gecko solo actúan después de un fallo, en el siguiente arranque.
- La memoria de Zink va a memoria directa (unos 4,6 GB libres en run-0207), no al conjunto flexible que antes limitaba a SeaMonkey. Aun así hay que medirlo en la consola.
- Lo que gana no está medido: la GPU hace la composición y la conversión YUV y el escalado del vídeo, pero cada fotograma sigue pasando por la presentación de Zink al sink.

Si la ejecución en la consola muestra un bloqueo, fotogramas perdidos o memoria que no vuelve, publicar 04.19 sin `orbisdesk-gpu.js` (o con `layers.prefer-opengl` a false). Solo con user.js queda Basic, como antes.

## Qué se probó

- El anfitrión, como en la tabla de arriba. No es evidencia de PS4: el Zink de la consola corre sobre el RADV enlazado, no sobre el controlador de Windows de AMD, y dibuja a través del sink de OrbisDesk.
- `tools/build-wine-hardware.py` compila (`py_compile`). No se compiló nada más.
- **No probado:** nada en la consola, WebGL en una página, la velocidad de dibujo, y MangoHud con SeaMonkey en OpenGL.

## 04.34: WebGL activado, composición Basic

Desde la 04.34, `seamonkey-gpu.js` pone `webgl.disabled` en false por defecto. La composición por GPU (`layers.acceleration.disabled`) sigue en true, así que las páginas se componen con Basic, que muestra los videos y dibuja la ventana en su lugar. Los lienzos WebGL se dibujan con Mesa/Zink y se copian a Basic. Los dos interruptores se pueden seguir cambiando en about:config.
