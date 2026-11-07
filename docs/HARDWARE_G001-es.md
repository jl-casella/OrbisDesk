# G001: Vulkan (RADV sobre GNM) en la PS4, hito H0

[English](HARDWARE_G001.md) | [Español](HARDWARE_G001-es.md)

## Objetivo

Probar que la GPU de la PS4 se puede usar con Vulkan desde un homebrew compilado con nuestro SDK. Es el primer paso hacia Vulkan en Wine (H1: el mismo driver dentro del ELF de Wine; H2: winevulkan; H3: `vkcube.exe` con contador de FPS; H4: windows-glxgears mediante Zink).

## De dónde sale

- La investigación de alternativas está en las notas de sesión (`gpu-research.md`). En resumen: DolphinPS4, Crema y Resonance usan Mesa RADV con un winsys propio (`port/mesa/ac_ps4_drm.c`), que envía el trabajo con `libSceGnmDriver.sprx` (`sceGnmSubmitCommandBuffers`). La GPU usa la misma dirección virtual que la CPU.
- El probe es `upstream/DolphinPS4/probe-vk/main.c`, copiado a `native/vk_probe/main.c`. Sus pasos son:
  1. instancia y dispositivo;
  2. `vkCmdFillBuffer` y verificación desde la CPU;
  3. un triángulo que gira, dibujado en dos imágenes lineales que se registran en VideoOut y se muestran con flip en vsync.
- Cambios propios:
  - el log va a `/data/orbis-win/g001/`;
  - el paso 3 dura 20 s (1200 cuadros);
  - una vez por segundo se registra una línea `fps`, con los cuadros presentados y los FPS que permitirían el render y la espera del fence solos, sin vsync.
- DolphinPS4 informa que su probe funciona en una PS4 Slim con 12.52 y en una Pro con 11.00 (`README.md`). En una Pro con 12.52 no está probado.

## Cómo se construye

Todo corre en WSL; el árbol de compilación está en `~/vk-h0` para no compilar sobre el disco de Windows.

1. `tools/vk-h0/fetch.sh` baja los dos tarballs a `.deps/vk/` y crea un venv con meson, mako y pyyaml:
   - Mesa 26.0.8, SHA256 `caf1c0061a68e88dfa74967a7e780c0e85d65b6c4e334cd69095a5dc54ad78bc`;
   - libdrm 2.4.125, solo los headers, SHA256 `d4bae92797a50f81a93524762e0410a49cd84cfa0f997795bc0172ac8fb1d96a`.
2. `tools/vk-h0/setup-libcxx.sh` corre la receta `toolchain/build-libcxx.sh` de DolphinPS4 con nuestro SDK y clang 19 en lugar de PacBrew y clang 21. Genera el libc-overlay y libc++/libc++abi 21.1.6. El libc++ del SDK es la versión 11 y no alcanza para el compilador ACO de Mesa.
3. `tools/vk-h0/build-glslang.sh` compila `glslangValidator` para la PC desde la copia de glslang de shadPS4. Mesa lo usa para sus shaders internos.
4. `tools/vk-h0/build-mesa.sh` replica `scripts/build-mesa.sh` de DolphinPS4: aplica `patches/mesa-ps4.patch` y `ac_ps4_drm.c`, y compila estático, sin LLVM y sin WSI. Tiene un cambio propio, `fix-mesa-detect.py`. Las comprobaciones de funciones de Mesa sin header solo verifican que el símbolo enlace. La libc de OpenOrbis define `qsort_s` sin declararla, y Mesa la llamaba sin declaración. Ahora se exige la declaración.
5. `tools/vk-h0/build-probe.sh` hace dos cosas:
   - compila zlib-ng en modo compatible desde la copia de shadPS4;
   - compila el probe y el runtime de DolphinPS4 (`port/ps4_*`) y los enlaza como `toolchain/ps4-love-style.cmake`.
   
   Lo que replica de ese enlace:
   - RADV con `--whole-archive`;
   - los wraps de malloc, mmap, `clock_gettime` y `pthread_once`;
   - el script de enlace con `.init_array.*` y `.data.*`;
   - el `crt1.o` con heap de libc de 64 MiB.
   
   Nuestro stub de libkernel no exporta `sceKernelJitCreateSharedMemory` ni `sceKernelJitCreateAliasOfSharedMemory`. Las usa el JIT de Dolphin y el probe nunca las llama. `native/vk_probe/jit_unavailable.c` las define como fallas con traza.
6. `tools/build-vk-probe.py --upload 192.168.68.104` arma el eboot y lo sube:
   - `create-fself` con PAID `0x3800000000000035` y el authinfo de love-ps4, como el probe de DolphinPS4;
   - el PKG `ORBG00001`;
   - la subida a `/data/pkg/orbis-win-G001-<sha12>.pkg`.

El OELF tiene un solo segmento `LOAD` RW, que es lo que exige `check-oelf.cmake` de DolphinPS4.

## Primer paquete

- ELF SHA256 `93a4caa6931b582fdc608c7299e0c72769e32676b194090288525f0367995470`.
- PKG `out/vk-probe-g001/IV0000-ORBG00001_00-ORBISWINVKPROBE1.pkg`, SHA256 `c653ba5f50606598c3c4b4a609f477d6a1a9543b5c02abb1cc4dc2d636c7cb13`, subido como `/data/pkg/orbis-win-G001-c653ba5f5060.pkg`.
- No se probó en la consola todavía.
- Logs esperados:
  - `/data/orbis-win/g001/vk-probe.log`;
  - `vk-probe-stderr.log`;
  - `mesa.log`.

## G001 en la PS4 Pro (12.52)

Evidencia: `reports/vk-probe-g001/physical/20261101T164147Z/vk-probe.log`. El `vk-probe-stderr.log` quedó vacío y no se generó `mesa.log`.

- Paso 1: `vkCreateInstance`, `vkEnumeratePhysicalDevices` y `vkCreateDevice` devuelven 0.
  - El dispositivo es `AMD Liverpool (PS4) (RADV BONAIRE)`, Vulkan 1.3.335, device id `0x9920`.
  - Hay una familia de colas (flags `0xf`) con 1 cola.
- Paso 2: `vkCmdFillBuffer` y la espera del fence funcionan. La CPU lee `0x12345678` en el primero y en el último elemento.
- Paso 3: VideoOut se abre (`0x4e110100`) y registra los dos framebuffers de 1920x1080, en memoria de tipo 3. ACO compila el pipeline en 2,3 ms.
- FPS: con vsync se presentan 58,5 a 59,9 cuadros por segundo. El render más la espera del fence tarda unos 0,9 a 1,1 ms por cuadro, lo que equivale a unos 900-1100 FPS sin vsync para este triángulo; en un segundo subió a 2,8 ms.
- El píxel central cambia entre cuadros (`0xff5f6f73`/`0xff606f73`) y la esquina sigue el pulso del fondo, así que la GPU escribe en los framebuffers.
- El log termina en el cuadro 1139, 60 cuadros antes del final del paso 3, sin `step 3 done`. Está pendiente saber si la app se cerró o se cortó antes.

Conclusión: RADV sobre GNM funciona en esta consola con nuestro SDK y nuestra identidad de homebrew. El siguiente hito es H1: el mismo driver dentro del ELF de Wine.

## H1: RADV dentro del ELF de Wine (W070)

- `native/vk_probe/main.c` se compila también con `PW_VK_IN_WINE` y queda como `pw_vk_probe()`. En ese modo hace lo siguiente:
  - escribe en el log de la corrida con el prefijo `PWVK`;
  - no abre VideoOut, que es del sink de Wine;
  - dibuja 300 cuadros del triángulo fuera de pantalla, sin flips;
  - deja el dispositivo abierto.
  
  El lanzador (`native/wine_hardware.c`) lo llama antes de iniciar Wine, entre `vk_probe_start` y `vk_probe_end`. Así Wine arranca con las reservas de memoria del driver de GPU ya hechas.
- Mesa se compila en una variante para Wine (`VARIANT=wine tools/vk-h0/build-mesa.sh`, en `~/vk-h0/build/mesa-wine`). Hay dos diferencias con G001:
  - Sin `unistd.h` en el overlay. En el ELF de Wine, `sysconf` es el de la libc del SDK, con la numeración de musl. En G001 era el del kernel, con la numeración de FreeBSD. `mmap` y `clock_gettime` vienen del kernel en los dos casos, así que el overlay de `sys/mman.h` y `time.h` se mantiene.
  - `pthread_once` pasa a llamarse `pw_vk_pthread_once` (`native/wine_vk_runtime.c`). El del kernel trata `pthread_once_t` como una estructura de 16 bytes, mientras que los headers declaran 4. A libc++ y libc++abi se les aplica el mismo cambio con `objcopy`.
    
    Nuestro propio código también llama al `pthread_once` del kernel (`native/hw_pad.c` y `platform/ps4/pw_wine_net.c`) con variables de 4 bytes. Es un riesgo de corrupción que no se corrigió en este paso.
- `tools/build-wine-hardware.py` enlaza:
  - el probe y el runtime;
  - RADV con `--whole-archive`;
  - zlib, libc++ y libc++abi.
  
  Desde W070 el ELF de Wine usa una copia del `link.x` del SDK que junta `.data.*`, `.tdata.*`, `.tbss.*` y `.init_array.*`. Mesa usa `-fdata-sections` y libc++ tiene constructores con prioridad; con el script original esas secciones quedaban huérfanas.
- Resultado del enlace: sin símbolos indefinidos y con un solo `LOAD` RW. La comprobación de que ninguna importación del kernel pase a ser definición estática pasó.
- PKG `/data/pkg/orbis-win-W070-0276a24376b8.pkg` (APP_VER 01.69). No se probó en la consola todavía.
- W070 en la PS4 (`reports/wine-hardware-w070/physical/20261101T174648Z/run-0001.log`):
  - El probe corre dentro del ELF de Wine, entre `vk_probe_start` (2126 ms) y `vk_probe_end` (3080 ms): 953 ms en total.
  - Instancia, dispositivo, `vkCmdFillBuffer` (`0x12345678` en el primer y en el último elemento) y 300 cuadros del triángulo fuera de pantalla. Los resultados son los mismos que en G001: las mismas direcciones (`0x43ff...`), el mismo píxel central, el pipeline compilado en 2,3 ms y unos 2 ms promedio por cuadro, incluido el primero, que tarda 12 ms.
  - Después Wine arranca el escritorio con el dispositivo Vulkan abierto: explorer presenta cuadros y recibe clics del mouse.
  - El log termina sin `process_exit` y sin programas lanzados, en un movimiento del puntero. El usuario cerró la app desde la PS4; no fue un cuelgue.
  - Con esto H1 queda cumplido: RADV funciona dentro del ELF de Wine y Wine arranca con el dispositivo abierto.

## H2: Vulkan para programas de Windows (W071)

- Lado Windows: `winevulkan.dll` y `vulkan-1.dll` se compilan sin cambios como PE64 en el árbol de Wine del host (`make dlls/<nombre>/x86_64-windows/<nombre>.dll`). `build-wine-hardware.py` las copia a `wine/lib/wine/x86_64-windows` y a `system32`.
- Lado Unix de winevulkan: `tools/build-winevulkan-ps4.py` compila `vulkan.c` y `vulkan_thunks.c` sin parches, con las recetas del Makefile de Orbis. Los dos objetos se combinan en uno, y sus símbolos ocultos quedan locales. Las tablas `__wine_unix_call_funcs` y `__wine_unix_call_wow64_funcs` se renombran. `platform/ps4/pw_wine_unixlibs.c` las entrega a ntdll como `winevulkan.so`, y `tools/link-wine-boot.py` agrega el objeto al enlace.
- `win32u` (`build-win32u-ps4.py`): en lugar de `dlopen("libvulkan.so.1")`, toma `vkGetInstanceProcAddr` del puntero `pw_vk_instance_proc_addr` (`pw_wine_unixlibs.c`). El lanzador lo completa con `pw_vk_get_instance_proc_addr` (`native/wine_vk_runtime.c`) después del probe. Esa función también devuelve `vkGetDeviceProcAddr`, que la búsqueda ICD de RADV no devuelve, como hace prospero-win en `wine/ps5/pw_vulkan_radv.c`. Si el puntero es NULL, que es lo que pasa en los enlaces de Wine sin RADV, no hay Vulkan y se registra `PWVK no RADV linked`.
  
  Un primer intento con un símbolo débil hizo que `create-fself` rechazara el ELF de `link-wine-boot.py` (salida 255), porque ese ELF dejaba la referencia sin definir.
- El driver de usuario no implementa `VulkanInit`, así que `win32u` usa el suyo nulo: superficies `VK_EXT_headless_surface`, que RADV ofrece. Todavía no se presenta nada en una ventana; eso es H3.
- Prueba: `fixtures/win32/vkprobe64.c`, compilado con MinGW como `C:\orbis\vkprobe64.exe`. Es un programa de consola que carga `vulkan-1.dll` y hace lo siguiente:
  - crea la instancia;
  - lista las GPU;
  - crea el dispositivo;
  - hace 100 llenados de 1 MiB con la GPU y verifica cada uno desde la CPU.
  
  Escribe el resultado en la consola y en `C:\orbis\vkprobe64.txt`, y termina en `PASSED` si todo funcionó.
- PKG `/data/pkg/orbis-win-W071-76f501e91750.pkg` (APP_VER 01.70). No se probó en la consola todavía.
- W071 en la PS4 (`reports/wine-hardware-w071/physical/20261101T181202Z/`, con `run-0001.log` y `vkprobe64.txt`): **H2 cumplido.** `vkprobe64.exe` corrió como guest, con su consola:
  - `vulkan-1.dll` carga y ofrece Vulkan 1.4.0 con 8 extensiones de instancia; `vkCreateInstance` tarda 40 ms.
  - Lista una GPU, vendor `0x1002` y device `0x9920`, que son los mismos que en G001/W070, con Vulkan 1.3.335. El nombre que ve el programa es `PS5`: lo pone el driver de usuario de prospero-win, no RADV. Falta cambiarlo.
  - `vkCreateDevice`, la memoria host-visible (mapeada en `0x4fffe60000`), el command pool y el fence funcionan.
  - Los 100 llenados de 1 MiB, cada uno verificado desde la CPU, dan el resultado esperado, con unos 4,5 ms por llenado incluidas la espera del fence y la verificación. Termina en `vkprobe64: PASSED`.
  - El log tiene 160 líneas `radv/ps4: submit`, cada una repetida dos veces. El winsys escribe tanto en stderr como en su log, y los dos van al log de la corrida.
  - El guest y su consola terminan y se descargan normalmente.

## H3: Vulkan en ventanas (W072)

- El driver de usuario no tiene `VulkanInit`, así que las superficies `win32` de las aplicaciones son superficies headless de Mesa, en el host. Su WSI pide imágenes DRM, y la PS4 no tiene DRM. `tools/vk-h0/patch-mesa-wsi.py` (aplicado por `build-mesa.sh`) cambia `wsi_common_headless.c`, solo con `__PS4__`, en dos puntos:
  - Las imágenes del swapchain son de tipo CPU. Es el camino que Mesa usa para los drivers por software: una imagen óptima en la GPU y, en cada present, un blit de la GPU a un buffer lineal que la CPU puede leer (`cpu_map`).
  - En el present se espera el fence de ese blit y se llama a `pw_wsi_headless_presented` con los píxeles, el pitch, el tamaño y el formato.
- `native/wine_vk_runtime.c` guarda el último cuadro de cada swapchain y registra una línea `PWVK present fps` por segundo. `pw_vk_runtime_init()`, que el lanzador llama después del probe, instala los tres punteros: `pw_vk_instance_proc_addr`, `pw_vk_last_frame` y el hook de Mesa.
- `win32u` (`build-win32u-ps4.py`): después del present del host, `pw_vk_show_frame` dibuja ese cuadro en la ventana del swapchain con `NtGdiStretchDIBitsInternal`, escalado al área cliente. Si el formato es RGBA, primero intercambia R y B. El compositor muestra la ventana como cualquier otra. Las primeras 5 copias, y después una de cada 600, quedan en el log como `PWVK show_frame`.
- Costo esperado: cada cuadro pasa por un blit de la GPU a memoria del host y por una copia por GDI. Es más lento que mostrar el cuadro directamente; el número real lo dará la prueba.
- Prueba: `fixtures/win32/vkspin64.c`, compilado como `C:\orbis\vkspin64.exe`. Es una ventana de 640x480 con el triángulo de G001 girando, dibujado con un swapchain de `VK_KHR_win32_surface` que se recrea al cambiar el tamaño de la ventana. Muestra los FPS en el título y los escribe en `C:\orbis\vkspin64.txt`.
- PKG `/data/pkg/orbis-win-W072-39080c7ec6eb.pkg` (APP_VER 01.71). No se probó en la consola todavía.
- W072 en la PS4 (`reports/wine-hardware-w072/physical/20261101T182702Z/`, con `vkspin64.txt`): `vkCreateInstance` devolvió -7 (`VK_ERROR_EXTENSION_NOT_PRESENT`) y el programa terminó sin cuadros.
  - RADV solo ofrece `VK_KHR_surface`, `VK_EXT_headless_surface` y `VK_KHR_swapchain` con `RADV_USE_WSI_PLATFORM` (`src/amd/vulkan/radv_wsi.h`), que se define solo con una plataforma de ventanas: X11, Wayland o display.
  - Sin `VK_EXT_headless_surface` en el host, `win32u` no ofrece `VK_KHR_win32_surface`.
- W073: `patch-mesa-wsi.py` define también `RADV_USE_WSI_PLATFORM` con `__PS4__`, porque headless es la plataforma de la PS4. PKG `/data/pkg/orbis-win-W073-211879c12c51.pkg` (APP_VER 01.72). No se probó en la consola todavía.
- W073 en la PS4 (`reports/wine-hardware-w073/physical/20261101T183811Z/`, con `vkspin64.txt`): **la presentación en ventanas funciona.**
  - `vkspin64` crea la superficie: `presentation support 1`, 2 formatos, usa el 44 (`B8G8R8A8_UNORM`).
  - Crea un swapchain de 632x453 con 4 imágenes. `pw_vk_show_frame` dibuja cada cuadro en la ventana (`drawn=453`, el área cliente completa).
  - FPS en 632x453: 34,3 a 36,7, medidos por el programa y por el hook de Mesa.
  - FPS con la ventana maximizada (1280x701): 11,6 a 12,1. El swapchain se recreó bien las cuatro veces que se maximizó y restauró la ventana.
  - El programa terminó al cerrar la ventana (`end after 817 frames`), y la app salió normalmente desde Inicio (`process_exit status=0`).
  - El tiempo por cuadro (unos 28 ms en 632x453 y 83 ms en 1280x701) crece con el área, así que lo limitan las copias y no la GPU, que en G001 dibujaba este triángulo en unos 1 ms. Hay dos candidatos sin medir: la lectura desde la CPU de la memoria a la que el blit copia la imagen, que puede no tener caché, y la copia por GDI más el compositor.

## Velocidad de la copia (W074)

- `patch-mesa-wsi.py` cambia la memoria de los buffers de CPU del swapchain: en la PS4 pide `HOST_CACHED`, como Mesa hace para los drivers por software. Antes Mesa pedía solo `HOST_COHERENT`, que en RADV puede caer en memoria sin caché; leerla desde la CPU es lento. `build-mesa.sh` restaura del tarball los tres archivos que toca el parche antes de aplicarlo.
- Mediciones nuevas:
  - `blit_wait_us`, en la línea `PWVK present fps`: lo que el present espera el blit de la GPU al buffer de CPU (`os_time_get_nano` en Mesa).
  - `gdi_us`, en `PWVK show_frame` cada 60 cuadros: lo que tarda en `win32u` la copia a la ventana, incluida la conversión de RGBA si la hay.
  - El costo del compositor ya se registraba en `flush_stats`.
- PKG `/data/pkg/orbis-win-W074-3fb6f2f6f272.pkg` (APP_VER 01.73). No se probó en la consola todavía.
- W074 en la PS4 (`reports/wine-hardware-w074/physical/20261101T185124Z/`, con `vkspin64.txt`):
  - FPS en 632x453: 276 a 279. En W073 eran unos 36, unas 7,7 veces menos.
  - FPS en 1280x701 (maximizada): 125,6 a 132,2. En W073 eran unos 12, unas 11 veces menos.
  - 5769 cuadros en total. El swapchain se recreó al maximizar y al restaurar, y el programa y la app terminaron normalmente.
  - Tiempos por cuadro en 1280x701:
    - espera del blit de la GPU (`blit_wait_us`): unos 0,7 ms (0,24 ms en 632x453);
    - copia por GDI a la ventana (`gdi_us`): unos 1,6 ms (0,5 ms en 632x453);
    - compositor (`flush_stats avg_us`): unos 4,1 ms por flush, con unos 880.000 píxeles.
  - La lentitud de W073 venía de que la CPU leía memoria sin caché. Ahora el límite está en la copia por GDI y en el compositor, que corre aparte; la pantalla igual se actualiza a 60 Hz.
  - El programa presenta más cuadros por segundo de los que la pantalla muestra, porque el swapchain headless no espera el vsync. Para un juego eso es trabajo de más.
- Fotos de W074 tomadas por el usuario: el triángulo se ve con sus colores. A ratos, la ventana de `vkspin64` maximizada deja ver el fondo de pantalla (las nubes y las colinas), como si fuera transparente.
  - Causa: `compose_rect` (compositor de `ps5drv.c`) primero copia el fondo de pantalla al buffer del escritorio y después las ventanas encima. El hilo presentador del sink (`PW_SINK_ASYNC`) lee ese mismo buffer sin esperar al compositor. Un cuadro leído entre las dos pasadas tiene el fondo donde está la ventana.
  - Con una ventana que se redibuja 130 veces por segundo pasa seguido. La foto junta varios refrescos en una exposición, y por eso el resultado parece transparencia.
- W075 (`build-win32u-ps4.py`): `compose_rect` arma cada fila en una fila auxiliar (el fondo y las ventanas de abajo hacia arriba) y la copia al buffer del escritorio una sola vez. Una lectura cortada todavía puede mezclar filas del cuadro anterior y del nuevo, pero ninguna fila sin la ventana. PKG `/data/pkg/orbis-win-W075-8e1810d644ae.pkg` (APP_VER 01.74). No se probó en la consola todavía.
- W075 en la PS4 (`reports/wine-hardware-w075/physical/20261101T201511Z/run-0001.log`):
  - `vkspin64` corre a unos 290 FPS en 632x453, igual que en W074.
  - El compositor tarda lo mismo con la fila auxiliar: `flush_stats avg_us` de 1,7 ms con unos 290.000 píxeles y de 3,9 a 4,1 ms con unos 880.000.
  - El log no puede mostrar si el fondo todavía se ve a través de la ventana; eso lo tiene que confirmar el usuario mirando la pantalla.
  - El usuario confirmó que el fondo ya no se ve a través de la ventana.

## H4: OpenGL con Zink (W076)

- `tools/vk-h0/build-mesa-zink.sh` compila el frontend WGL de Mesa con el driver Gallium Zink como DLL PE64: `opengl32.dll` y `libgallium_wgl.dll`. Usa las mismas opciones que `upstream/prospero-win/tools/build_mesa_zink.sh`, pero con el tarball oficial de Mesa 26.0.8 sin parches, extraído aparte en `~/vk-h0/src/mesa-win`, en lugar del fork de prospero-win.
  - El MinGW del sistema no tiene C++, así que se usa llvm-mingw 20260922 UCRT (`fetch-llvm-mingw.sh`, SHA256 `bb7bb765...65c21`), el mismo que fija prospero-win.
  - Zink carga `vulkan-1.dll`, es decir winevulkan y RADV.
  - Las DLL importan UCRT por api-sets, `KERNEL32`, `GDI32` y `USER32`; ninguna biblioteca de C++.
  - SHA256: `opengl32.dll` `bd94657a...bf48bf`, `libgallium_wgl.dll` `de20cd15...41d32dd`.
- `build-wine-hardware.py` las copia a `system32` como `opengl32.dll` nativo, porque el runtime no tiene `opengl32` builtin.
- Prueba: `fixtures/win32/glxgears/main.cpp`, el port de glxgears de CalvinHartwell (`8c27987`, MIT, de Brian Paul), compilado con llvm-mingw como `C:\orbis\glxgears.exe` (SHA256 `44dfe1e8...c90949`). Se agregó lo siguiente:
  - los FPS de cada intervalo de 5 s en el título de la ventana;
  - un archivo `C:\orbis\glxgears.txt` con `GL_RENDERER`, `GL_VERSION`, `GL_VENDOR`, los FPS y cualquier falla de inicialización.
- PKG `/data/pkg/orbis-win-W076-4d3ba493932f.pkg` (APP_VER 01.75). No se probó en la consola todavía.
- W076 en la PS4 (`reports/wine-hardware-w076/physical/20261101T202920Z/`, con `glxgears.txt`):
  - `glxgears` abre su ventana, pero `ChoosePixelFormat` devuelve 0 (`failed to initialise opengl: ... pixel format 0`). El error 203 es un último error viejo del hilo.
  - En la cadena gdi32 → `opengl32.dll` (Mesa) → `wglChoosePixelFormat`, Zink sí llegó a crear el dispositivo: el log tiene las reservas de memoria de RADV (`radv/ps4: bo ...`). Lo que falla es la lista de formatos de píxel de Mesa (`stw_pixelformat.c`), que depende de `is_format_supported` de Zink. La causa no está identificada.
  - El programa termina normalmente y su consola se descarga.
- W077, diagnóstico:
  - `glxgears` registra cuántos formatos de píxel ofrece `DescribePixelFormat` y cómo es el primero.
  - El lanzador define `MESA_LOG_FILE=C:\orbis\mesa-wgl.log` para que el Mesa de Windows escriba sus mensajes (util/log). El RADV del ELF también lee esa variable, pero ese nombre no es una ruta válida para él.
  - El arreglo de argumentos del lanzador pasa de `8+` a `10+MAX_LAUNCH_ARGS`.
  - PKG `/data/pkg/orbis-win-W077-b61d6b344586.pkg` (APP_VER 01.76).
- W077 en la PS4 (`reports/wine-hardware-w077/physical/20261101T215324Z/`, con `glxgears.txt`):
  - `DescribePixelFormat` dice que hay 0 formatos de píxel, y `ChoosePixelFormat` falla con el error 50 (`ERROR_NOT_SUPPORTED`).
  - El log muestra que Zink crea su instancia y su dispositivo en RADV: un segundo winsys, con sus ventanas de direcciones en `0x4c00000000` y `0x5000000000`, y 7 buffers. Después no hay más actividad de la GPU antes de que el programa termine.
  - No se generó `mesa-wgl.log`: en Windows, `util/log.c` de Mesa no usa `MESA_LOG_FILE`; escribe en stderr, que va a la consola del programa, y en `OutputDebugString`.
- W078: el lanzador define `WINEDEBUG=warn+seh`. Wine registra `OutputDebugString` como advertencia del canal `seh` (`dlls/kernelbase/debug.c`), así que los mensajes de Mesa y Zink van a aparecer en el log de la corrida. PKG `/data/pkg/orbis-win-W078-e8349943b4bd.pkg` (APP_VER 01.77).
- W078 en la PS4 (`reports/wine-hardware-w078/physical/20261101T220147Z/run-0001.log`): `WINEDEBUG=warn+seh` hace visible el mensaje de Zink: `MESA: error: ZINK: failed to get total physical memory`.
  - En Windows, Mesa toma ese dato de `GlobalMemoryStatusEx` (`src/util/os_misc.c`), y si falla, Zink no crea la pantalla. Sin pantalla, WGL no tiene formatos de píxel.
  - El `GlobalMemoryStatusEx` de Wine (`dlls/kernelbase/memory.c`) depende de tres consultas: `NtQuerySystemInformation(SystemBasicInformation)`, `NtQuerySystemInformation(SystemPerformanceInformation)` y `NtQueryInformationProcess(ProcessVmCounters)`. Si alguna falla, devuelve FALSE.
- W079: `glxgears` registra en `glxgears.txt` el resultado de `GlobalMemoryStatusEx` y el status y la longitud de cada una de las tres consultas, antes de iniciar OpenGL. PKG `/data/pkg/orbis-win-W079-0f96d0aa6ba4.pkg` (APP_VER 01.78).
- W079 en la PS4 (`reports/wine-hardware-w079/physical/20261101T220947Z/`, con `glxgears.txt`): `GlobalMemoryStatusEx` devuelve 0 con error 50. `NtQuerySystemInformation(SystemBasicInformation)` y `NtQueryInformationProcess(ProcessVmCounters)` responden 0, pero `NtQuerySystemInformation(SystemPerformanceInformation)` responde `0xc00000bb` (`STATUS_NOT_SUPPORTED`). Ese valor lo devolvía siempre `get_performance_info` en PS4 por una revisión anterior de `prepare-wine-boot.py`, porque entonces no había de dónde sacar los datos.
- W080 (`prepare-wine-boot.py`, `platform/ps4/pw_wine_memory.c`):
  - `pw_wine_memory_info` toma las cifras del kernel. El total es la memoria directa (`sceKernelGetDirectMemorySize`) más la flexible disponible (`sceKernelAvailableFlexibleMemorySize`). Lo disponible es el mayor rango libre de memoria directa (`sceKernelAvailableDirectMemorySize`) más la flexible disponible.
  - El kernel no da el tamaño configurado del pool flexible ni el total libre de memoria directa. Por eso estas cifras no son exactamente las de memoria física de Windows, aunque son medidas reales. La primera llamada queda en el log como `PWBOOT memory_info`.
  - Los prototipos del SDK para las dos funciones `Available` declaran los punteros de salida como valores; `pw_wine_memory.c` los declara como los usa el kernel.
  - `get_performance_info` completa `AvailablePages`, `TotalCommittedPages` y `TotalCommitLimit` con esas cifras. El tiempo ocioso queda en 0 y el archivo de paginación en una página, como hace Wine en sistemas sin swap. Si el kernel falla, sigue devolviendo `STATUS_NOT_SUPPORTED`.
  - `virtual_get_system_info` (`SystemBasicInformation`) usa el mismo total, y vuelve a `sysinfo()` si el kernel falla.
  - PKG `/data/pkg/orbis-win-W080-cda31ccf962f.pkg` (APP_VER 01.79).
- W080 en la PS4 (fotos del usuario): **glxgears funciona** por WGL, Zink, winevulkan y RADV, a unos 66 FPS en una ventana de unos 300x300. Pero partes de los engranajes, sobre todo del rojo (el más grande), desaparecen y vuelven de un cuadro a otro.
- W081: el RADV del ELF de Wine pasa del port de DolphinPS4 al de Crema (`build-mesa.sh` con `VARIANT=wine`).
  - Crema (`upstream/Crema/patches/BASE.txt`) usa el Mesa 26.0.8 de DolphinPS4 más su `mesa-ps4.patch` y `mesa-ps4-aligned-vertex-fetch.patch`.
  - Su `ac_ps4_drm.c` tiene 3609 líneas, contra 2937 en DolphinPS4. Entre otras cosas, libera, desmapea y reutiliza un buffer solo cuando la GPU terminó todo lo enviado antes. Según su comentario, liberarlo antes hacía que las escrituras tardías de la GPU cayeran en lo que ocupara esa memoria después.
  - También agrega una cola para el overflow de cada buffer y un hilo de envío con prioridad alta.
  - Zink sube los vértices de glxgears a buffers que se renuevan cada cuadro, así que esa es la hipótesis para lo que se ve; no está confirmada.
  - El árbol fuente queda aparte (`~/vk-h0/src/mesa-crema`), y sus logs van a `/data/orbis-win/gpu`.
  - `native/wine_vk_runtime.c` implementa las dos funciones del runtime de Crema que llama su winsys: `ps4_boot_trace`, que escribe en el log de la corrida, y `ps4_boost_thread`, que hace `scePthreadSetprio(..., 650)`.
  - G001 sigue con el port de DolphinPS4.
  - PKG `/data/pkg/orbis-win-W081-b38c66a80326.pkg` (APP_VER 01.80).
- W081 en la PS4 (`reports/wine-hardware-w081/physical/20261101T231430Z/`): el usuario informa que **sigue el mismo problema** con los engranajes. El cambio de winsys no lo resolvió.
  - `GlobalMemoryStatusEx` = 1, con un total de 5.097.123.840 bytes y 5.064.753.152 disponibles.
  - `SystemPerformanceInformation` = 0, longitud 312.
  - WGL ofrece 504 formatos de píxel. `GL_RENDERER` = `zink Vulkan 1.3(PS5 (MESA_RADV))`, `GL_VERSION` = `4.6 (Compatibility Profile) Mesa 26.0.8`.
  - glxgears hace 54,8 FPS en los primeros 5 s y después 66,0. El hook de Mesa cuenta 65 a 67 presentaciones por segundo de 300x300, con unos 0,13 ms de espera del blit.
  - `vkspin64` también funciona con el winsys de Crema: 212 a 271 FPS en 632x453.
- W082, experimento: el lanzador define `ZINK_DEBUG=sync`, que fuerza una barrera completa antes de cada dibujo. Si los engranajes quedan enteros, la causa es una sincronización que falta. Si no, es otra cosa: por ejemplo, cómo Zink dibuja los cuadriláteros (`GL_QUAD_STRIP`/`GL_QUADS`) o el sombreado plano de glxgears en gfx7. PKG `/data/pkg/orbis-win-W082-ec3eafd39dc9.pkg` (APP_VER 01.81).
- W082 en la PS4: el usuario informa que con `ZINK_DEBUG=sync` **sigue igual**. La causa no es una sincronización que falta entre dibujos.
- W083, experimento: se quita `ZINK_DEBUG=sync` y el lanzador define `RADV_DEBUG=nohiz,nofastclears`, que desactiva la compresión de profundidad (HTILE/HiZ) y los clears rápidos de RADV.
  - Hipótesis: `vkspin64` no tiene buffer de profundidad y dibuja triángulos enteros; glxgears sí lo tiene y lo limpia en cada cuadro.
  - Si la profundidad comprimida o su clear rápido funcionan mal en Liverpool, partes de la geometría fallan la prueba de profundidad según el ángulo, que es lo que se ve.
  - RADV lee la variable al crear su instancia. La de Zink se crea después de que Wine define el entorno; la del probe del lanzador, antes, así que el probe no la ve.
  - PKG `/data/pkg/orbis-win-W083-06fa4cc22d94.pkg` (APP_VER 01.82).
- W083 en la PS4: el usuario informa que con `RADV_DEBUG=nohiz,nofastclears` **sigue igual**. La causa no es la compresión de profundidad ni los clears rápidos. W084 quita ese experimento.
- W084: `fixtures/win32/gltest64.c` (`C:\orbis\gltest64.exe`) dibuja el mismo anillo con luz, que gira, de seis maneras en una grilla de 3x2. El anillo tiene cara frontal, cara trasera y banda exterior, como un engranaje sin dientes. Como en glxgears, las caras traseras se descartan (`GL_CULL_FACE`) en todos los paneles menos el 6.
  1. arriba a la izquierda: modo inmediato, `GL_QUAD_STRIP`, sombreado suave;
  2. arriba al centro: `GL_QUAD_STRIP`, sombreado plano;
  3. arriba a la derecha: `GL_TRIANGLE_STRIP` con los mismos vértices, plano;
  4. abajo a la izquierda: lista de dibujo (como glxgears), `GL_QUAD_STRIP`, plano;
  5. abajo al centro: `GL_QUADS`, plano;
  6. abajo a la derecha: `GL_QUAD_STRIP`, plano, sin descarte de caras.
  
  Los paneles que pierden geometría indican la conversión culpable: cuadriláteros, sombreado plano (vértice provocante), listas de dibujo, o el descarte de caras con el Y invertido de Zink. PKG `/data/pkg/orbis-win-W084-83907ea1d8e3.pkg` (APP_VER 01.83).
- W084 en la PS4: el usuario informa que solo se ve bien el panel de arriba a la derecha (azul, `GL_TRIANGLE_STRIP`). Los cinco paneles con cuadriláteros pierden partes, incluido el 6, sin descarte de caras.
  - Zink dibuja `GL_QUADS` con un geometry shader generado (`zink_create_quads_emulation_gs` en `zink_program.c`), y declara `GL_QUAD_STRIP` sin soporte, así que el frontend lo pasa a quads.
  - Los triángulos no usan geometry shader. Los geometry shaders fallan en Liverpool con RADV; Crema investiga sus anillos GS en `upstream/Crema/patches/mesa-ps4-gs-ring-probe.patch`.
- W085 (`tools/vk-h0/patch-mesa-zink.py`, aplicado por `build-mesa-zink.sh`): Zink no declara `GL_QUADS` entre las primitivas soportadas, así que el frontend de Mesa convierte los cuadriláteros en triángulos indexados.
  - Esto cubre a cualquier programa OpenGL que dibuje con cuadriláteros.
  - **No** corrige los geometry shaders. Siguen afectados los programas que usan GS propios (OpenGL moderno, Direct3D 10/11 por DXVK) y las otras emulaciones de Zink que usan GS: líneas punteadas o suavizadas, bordes y algunos modos de puntos.
  - `libgallium_wgl.dll` SHA256 `f49b5c31...71cf`.
  - PKG `/data/pkg/orbis-win-W085-d3e9c4084736.pkg` (APP_VER 01.84).
- W085, corrida 3 (`reports/wine-hardware-w085/physical/`, `run-0003.log`): el usuario borró archivos de `C:\orbis` y Wine dejó de arrancar (`boot_main_return rc=95`).
  - El chequeo previo del arranque (`preflight`) usa fixtures de esa carpeta, como `console32.exe`. Sin ellos, `drive-resolution`, `drive-z-resolution`, `file-identity` y `exe-pe32` quedan `blocked` con errno 2.
  - `upload-hardware.py --build W085` volvió a subir los 7 archivos que faltaban: `console32.exe`, `gui-window64.exe`, `gui-text64.exe`, `vkprobe64.exe`, `gltest64.exe` y otros dos. Compara cada archivo con el manifest, así que esa es la forma de reparar el prefijo.
- W085 en la PS4: el usuario confirma que **glxgears se ve bien**. `gltest64` no se probó.

## MangoHud Y vkcube (W086)

- Overlay: MangoHud-Windows (`github.com/Leclowndu93150/MangoHud-Windows`, commit `52592550`), un fork comunitario de MangoHud solo para Windows.
  - `tools/vk-h0/build-mangohud.sh` lo compila con llvm-mingw, sin NVML ni tests. Sus subproyectos (imgui, implot, spdlog, minhook, vulkan-headers) vienen de sus wraps de Meson.
  - Un solo cambio: `src/fps_metrics.h` incluye `<sstream>`, que la libc++ de llvm-mingw necesita.
  - Resultado: `libMangoHud.dll` (SHA256 `ef123777...e343`) y la capa implícita `MangoHud.x86_64.json`. Su `library_path` pasa a ser `.\libMangoHud.dll`, al lado del manifiesto en `system32`.
  - El proxy `dxgi.dll` del fork (para DirectX) no se usa.
- MangoHud es una capa de Vulkan, y el `vulkan-1.dll` de Wine reenvía directo a winevulkan sin cargar capas. Por eso se agregó el cargador oficial:
  - `tools/vk-h0/build-vulkan-loader.sh` compila Vulkan-Loader v1.4.335 de Khronos (commit `052ac246`, headers `2fa20342`) con llvm-mingw. `vulkan-1.dll` SHA256 `68b35e07...b333e`.
  - Va en `system32`, con `"vulkan-1"="native"` en las DllOverrides de `user.reg`.
  - Encuentra a winevulkan por `system32\winevulkan.json`, el mismo manifiesto que escribe el `DllRegisterServer` de Wine, registrado en `HKLM\Software\Khronos\Vulkan\Drivers`.
  - La capa se registra en `HKLM\Software\Khronos\Vulkan\ImplicitLayers`, y el lanzador define `MANGOHUD=1`, la variable que la activa.
  - Zink carga `vulkan-1.dll`, así que el overlay también debería aparecer en glxgears.
- `libMangoHud.dll` importa `dxgi`, `d3dcompiler_47` y `dwmapi`. Esas DLL, más `wined3d` que necesita `dxgi`, se compilan sin cambios como PE64 en el árbol de Wine del host y van al directorio de bibliotecas y a `system32`.
- vkcube: `tools/vk-h0/build-vkcube.sh` compila el cubo de Vulkan-Tools v1.4.335 (commit `48b5d246`) con llvm-mingw, como `C:\orbis\vkcube.exe` (SHA256 `a89ee4e5...5873`). Los FPS los muestra MangoHud.
- Datos que MangoHud no va a tener en la PS4: el fork lee la GPU con DXGI y ADL o NVML, la CPU con `GetSystemTimes`/`NtQuerySystemInformation` y la RAM con `GlobalMemoryStatusEx`. El siguiente paso, conectar la carga de la GPU que mide el winsys de Crema y los datos de la PS4, depende de qué muestre en esta corrida.
- PKG `/data/pkg/orbis-win-W086-d798aabd5619.pkg` (APP_VER 01.85), 538 archivos de runtime. No se probó en la consola todavía.
- W086 en la PS4 (`reports/wine-hardware-w086/physical/20261102T001256Z/run-0001.log`):
  - Se lanzaron `vkcube.exe` y `vkspin64.exe`. Zink informa `ZINK: vkCreateInstance failed (VK_ERROR_INCOMPATIBLE_DRIVER)`: el cargador de Khronos no encontró ningún driver.
  - En la vía de registro (`windows_get_registry_files` en `loader_windows.c`), el cargador primero crea una fábrica DXGI para verificar los drivers. El `dxgi` de Wine carga `wined3d`, que intenta OpenGL (`Failed to get a GL context for adapter`) y no deja ningún adaptador.
- W087, cambios en el lanzador:
  - `VK_DRIVER_FILES=C:\windows\system32\winevulkan.json`: el cargador toma el driver de ahí, sin registro ni DXGI.
  - `WINE_D3D_CONFIG=renderer=no3d`: `wined3d` sin 3D, para que `dxgi` solo enumere, que es lo que pide MangoHud para la GPU.
  - `VK_LOADER_DEBUG=error,warn`: los errores y advertencias del cargador salen por `OutputDebugString` y quedan en el log con `warn+seh`.
  - El arreglo de argumentos pasa a `14+MAX_LAUNCH_ARGS`.
  - PKG `/data/pkg/orbis-win-W087-ee536fb98b9d.pkg` (APP_VER 01.86).
- W087 en la PS4 (`reports/wine-hardware-w087/physical/20261102T023852Z/run-0001.log`):
  - Vulkan funciona a través del cargador de Khronos. `vkspin64` presenta a 261-286 FPS en 632x453, y `glxgears` (Zink) a unos 65 FPS en 300x300.
  - El cargador consulta el paquete `Microsoft.D3DMappingLayers` mientras busca capas (`GetPackagesByPackageFamily`, un stub de Wine), y no registra errores ni advertencias.
  - `vkcube.exe` no se lanzó en esta corrida.
  - El log no muestra si la capa de MangoHud se cargó; eso se ve en la pantalla.
- El usuario informa que en W087 **no apareció el overlay** de MangoHud.
  - Tampoco se vieron mensajes del cargador: en `loader/log.c` solo llama a `OutputDebugString` con `#if defined(WIN32)`. MinGW con `-std=c11` define `_WIN32` pero no `WIN32`, así que esos mensajes no salían. Solo iban a stderr, que en un programa GUI no llega a ningún lado.
- W088: el cargador se compila con `-DWIN32`, como en MSVC (`build-vulkan-loader.sh`), y el lanzador amplía `VK_LOADER_DEBUG` a `error,warn,info,layer`. Así el log va a mostrar dónde busca capas el cargador, si encuentra `MangoHud.x86_64.json` y si puede cargar `libMangoHud.dll`. PKG `/data/pkg/orbis-win-W088-7f7eaabdd978.pkg` (APP_VER 01.87).
- W088 en la PS4 (`reports/wine-hardware-w088/physical/20261102T024548Z/`): `vkcube` arranca. `wined3d` se inicia en modo `no3d` y aparece la consulta de RAM (`SYSTEM_PERFORMANCE_INFORMATION`), lo que indica que se cargaron `dxgi` y MangoHud. Pero no aparece el overlay, y tampoco hay mensajes del cargador aunque ahora tiene `OutputDebugString`.
- W089 (`VK_ADD_IMPLICIT_LAYER_PATH=C:\windows\system32`, `VK_LOADER_LAYERS_ENABLE=*mangohud*`, `VK_LOADER_DEBUG=all`, `MANGOHUD_USE_LOGFILE=1`, `MANGOHUD_LOG_LEVEL=debug`): **el usuario confirma que MangoHud se ve en vkcube.**
  - El registro solo no alcanzaba para que la capa se active. Con la ruta adicional y la habilitación por nombre, sí se activa; no está aislado cuál de las dos lo logra, y quedan las dos.
  - Los logs de las tres corridas (`reports/wine-hardware-w089/physical/20261102T025706Z/`) siguen sin mensajes del cargador, y MangoHud no creó su archivo de log. La causa de las dos cosas no está identificada.
- W090:
  - **Menú Inicio:** carpeta "Graphics Tools" (`tools/make-start-menu.py`) con glxgears, vkcube, vkspin y "MangoHud Config".
    - Las tres primeras apuntan a `C:\orbis`. "MangoHud Config" abre `%APPDATA%\MangoHud\MangoHud.conf` con el Bloc de notas.
    - El generador ahora admite argumentos y un ícono aparte (`HAS_ARGUMENTS`, cadenas en el orden de [MS-SHLLINK]). Los accesos anteriores quedan idénticos byte a byte.
  - **Íconos:** `tools/make-icons.py` dibuja en Python los íconos de 16, 32 y 48 px y los escribe como `.ico` (BMP de 32 bits con máscara), en `C:\orbis\icons`: engranajes, cubo, triángulo RGB y una "M" naranja. Los programas de prueba no tienen íconos propios.
  - **MangoHud.conf inicial:** fps, frametime, gráfico de frametime, CPU, GPU, RAM, y posición arriba a la izquierda.
  - **MangoJuice no se incluyó.** MangoJuice-Windows (`e2ec0755`) es una aplicación Vala con GTK4, libadwaita-1 y gee-0.8, y no tiene releases. Hay que compilar toda la pila GTK4 para Windows y tener `valac` en el host, que no está instalado.
  - PKG `/data/pkg/orbis-win-W090-3456e351caaf.pkg` (APP_VER 01.89).
- Corrección: el usuario aclara que el overlay **no apareció** ni en W089 ni en W090.
  - En los dos, `vkcube` carga las mismas DLL. Entre ellas está `dnsapi`, que viene de `IPHLPAPI` y que solo importa `libMangoHud.dll`. `wined3d` arranca en `no3d` y se consulta la RAM.
  - `libMangoHud.dll` exporta `overlay_GetInstanceProcAddr` y `overlay_GetDeviceProcAddr`, los nombres de su manifiesto.
- W091: `fixtures/win32/vklayers64.c` (`C:\orbis\vklayers64.exe`, consola) escribe en `C:\orbis\vklayers64.txt`:
  - las variables de entorno que lee el cargador;
  - la ruta del `vulkan-1.dll` que se carga;
  - las capas que lista `vkEnumerateInstanceLayerProperties`;
  - todos los mensajes del cargador durante dos `vkCreateInstance`: uno solo con capas implícitas y otro con `VK_LAYER_MANGOHUD_overlay_x86_64` explícita.
  
  Los mensajes llegan por un messenger `VK_EXT_debug_utils` en el `pNext`, que el cargador alimenta además de su log. PKG `/data/pkg/orbis-win-W091-7ab53be04873.pkg` (APP_VER 01.90).
- W091 en la PS4 (`reports/wine-hardware-w091/physical/20261102T030636Z/vklayers64.txt`):
  - El cargador encuentra la capa por el registro (`Located json file "C:\windows\system32\MangoHud.x86_64.json" from registry`) y la lista en `vkEnumerateInstanceLayerProperties`.
  - Al cargarla falla: `Failed to open dynamic library "C:\windows\system32\.\libMangoHud.dll" with error 1114` (`ERROR_DLL_INIT_FAILED`) y `Requested layer "VK_LAYER_MANGOHUD_overlay_x86_64" failed to load`. La instancia se crea igual, sin la capa.
  - El `DllMain` de MangoHud (`src/win/main.cpp`) devuelve TRUE siempre. El 1114 tiene que venir de la inicialización de otra DLL: una dependencia (`dxgi`, `d3dcompiler_47`, `dwmapi`, `iphlpapi` o `dnsapi`) o el arranque del runtime de C++ de la propia DLL.
  - El cargador informa `running with elevated permissions` e ignora todas las variables `VK_*` (`VK_DRIVER_FILES`, `VK_ADD_IMPLICIT_LAYER_PATH`, `VK_LOADER_LAYERS_ENABLE`). En el entorno del programa, además, figuran sin definir. Driver y capa los encuentra por el registro.
  - `winevulkan` declara la interfaz de cargador 4; el cargador avisa que para Vulkan 1.4 hace falta la 5 (`Policy #LDP_...`).
  - `APPDATA` es `C:\users\jose\AppData\Roaming`, el perfil del host en el prefijo, no `orbis`. El `MangoHud.conf` de W090 quedó en otro lugar.
- W092:
  - `WINEDEBUG=warn+seh,warn+module`, para ver qué DLL falla al inicializarse.
  - Se quitan las variables `VK_*` del lanzador.
  - `MangoHud.conf` y el acceso "MangoHud Config" pasan a `C:\users\jose\AppData\Roaming\MangoHud`.
  - PKG `/data/pkg/orbis-win-W092-06ec1e4fcbe2.pkg` (APP_VER 01.91).
- W092 en la PS4 (`reports/wine-hardware-w092/physical/20261102T031255Z/`), con `warn+module`: `load_builtin_unixlib failed to load ".../ws2_32.so": Dynamic loading not supported` y `process_attach Initialization of L"ws2_32.dll" failed`.
  - La parte Unix de `ws2_32` nunca se había enlazado en el ELF. Su `DllMain` falla, y con él todo módulo que lo importa (`ERROR_DLL_INIT_FAILED`): `iphlpapi`, y por él `libMangoHud.dll`.
  - Cualquier programa de Windows que use Winsock tenía el mismo problema.
- W093:
  - `tools/build-unixlibs-ps4.py` compila sin parches la parte Unix de `ws2_32` (`dlls/ws2_32/unixlib.c`), con la receta del Makefile de Orbis, y la combina como `build-winevulkan-ps4.py`. `pw_wine_unixlibs.c` la entrega como `ws2_32.so` y `link-wine-boot.py` la enlaza.
  - Usa `gethostbyname`, `gethostbyaddr`, `getnameinfo` y `gethostname` de la libc.
  - Su `pthread_once` pasa a ser `pw_wine_pthread_once` (`platform/ps4/pw_wine_once.c`). El del kernel escribe 16 bytes sobre el `pthread_once_t` de 4 que declaran los headers.
  - `dnsapi` no tiene parte Unix sin `libresolv` (todo `libresolv.c` está bajo `HAVE_RESOLV`), y su `DllMain` igual termina bien.
  - Un primer intento de W093 incluía `dnsapi` y dejó objetos en `build/unixlibs-ps4`. No se borran (la regla del proyecto es no borrar en `build/`); el informe nuevo ya no los lista y no se enlazan.
  - Atajos de MangoHud-Windows (`README.md` del fork): F12 muestra u oculta el overlay, F2 activa el registro de FPS. Se configuran en `MangoHud.conf` y los lee con `GetAsyncKeyState`.
  - PKG `/data/pkg/orbis-win-W093-3ed12d6faf9e.pkg` (APP_VER 01.92).
- W093 en la PS4 (foto del usuario): **MangoHud se ve sobre vkcube**.
  - Muestra `GPU 0%`, `CPU 100%`, `VULKAN 147 FPS`, 6,8 ms y el gráfico de frametime (mín. 4,9 ms, máx. 24,0 ms).
  - El cubo de Vulkan-Tools se ve con su textura (LunarG).
  - Al cargarse, la DLL arrancó también el hilo de ganchos de DirectX/OpenGL del fork (`MainThread` en `src/win/main.cpp`). Ese hilo abrió una consola "MangoHud" y un diálogo `Assertion failed`, en `win/d3d11_hook.cpp`, línea 126, `ret == kiero::Status::Success`, para `explorer.exe`, porque acá todos los programas corren en el proceso de explorer. Aceptar ese diálogo probablemente termina explorer.
  - Las cifras de GPU y CPU no son reales:
    - El fork lee la GPU con ADL/NVML/DXGI, que no existen en la PS4.
    - El 100 % de CPU probablemente viene de que `SystemPerformanceInformation` y `SystemProcessorPerformanceInformation` no informan tiempo ocioso en PS4 (W080); no está verificado.
- W094 (`build-mangohud.sh`): la DLL de la capa no arranca ese hilo, que solo usa el proxy `dxgi.dll` del fork, y ese proxy no se instala. `libMangoHud.dll` SHA256 `f9d93f7d...`. PKG `/data/pkg/orbis-win-W094-23e2179dc108.pkg` (APP_VER 01.93).
- W094 en la PS4 (`reports/wine-hardware-w094/physical/`): `vkcube` presenta a unos 162-168 FPS en 500x500, y `vkspin64` a unos 210-228 FPS, los dos con MangoHud.
  - A diferencia de W093, no se lanza ningún `conhost` aparte para MangoHud. No hay consola de MangoHud ni diálogo de aserción.
- W095: se quitaron secciones de depuración de módulos PE64 para reducir la memoria de carga. El usuario confirmó funcionamiento; se recuperaron siete sesiones en `reports/wine-hardware-w095/physical/20261102T102045Z/`. Vkcube sale con 0 en las sesiones 5 y 7, después de cerrar glxgears. Al combinar aplicaciones, las sesiones 2–4 registran excepciones de memoria y la sesión 4 una aserción de ImGui en dos hilos. Ver `analysis.md` junto a los logs.
- [W096](HARDWARE_W096-es.md): serializa el ciclo de vida y dibujo del overlay compartido y corrige la selección/restauración de contextos. Compilado como APP_VER 01.95. El ELF base de Wine es el mismo de W095; el único archivo distinto del runtime es `libMangoHud.dll`. La corrección de porcentajes CPU/GPU queda pendiente. Se omite la matriz local por indicación del usuario; la validación física de varias aplicaciones simultáneas está pendiente.
