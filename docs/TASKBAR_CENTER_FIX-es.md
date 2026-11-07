# Fondo de barra y pruebas de Start en shadPS4

[English](TASKBAR_CENTER_FIX.md) | [Español](TASKBAR_CENTER_FIX-es.md)

El fondo central blanco venía del fallback de Explorer cuando no hay tema de Taskbar: se observó `themed=0`. Start y reloj se pintaban aparte. El handler WM_ERASEBKGND ahora rellena toda la barra con el pincel del tema o COLOR_3DFACE y después aplica DrawThemeBackground cuando está disponible. Evita depender del fondo por defecto de la clase y cubre también temas parciales o fallidos.

Cambio en `tools/build-explorer-hw.py`. Compilación de diagnóstico aislada en `build/taskbar-center-fix/`, con Explorer SHA256 `0b6c0661dbf348f22c5c16f1b8ad9ada9ca7176f9850d465d1abcd38954e5025`. Se sustituyeron sólo tres copias PE64 en el runtime privado de W284; originales archivados en `reports/taskbar-center-fix/before/`. No se reescribió un paquete PS4. No se modificaron los artefactos de W286 concurrentes.

Prueba del 2026-11-07, fork Linux, entrada real por mando emulado: Start abre por puntero+Cross; cruceta navega y despliega Graphics Tools, Programs, System Tools y Control Panel. En Programs se desplegaron además Accessories, Games, Internet y Multimedia. Todos mostraron sus entradas. Se cerraron todos los menús, se comprobó el escritorio y se volvió a abrir Start correctamente. La barra central permaneció completa. No se ejecutaron programas ni se valida su compatibilidad a partir de este recorrido. No se registró un W284 crash.

La entrada X11 al ratón del anfitrión no se entregó como ratón USB PS4. El atajo Options/VK_LWIN tampoco abrió Start en este intento; no se clasifica como aprobado. Las capturas y pruebas anteriores usan el clic y cruceta efectivos del mando. El control Windows falló al activar WSLg; se capturó la ventana Linux con XGetImage sin componer ni retocar imágenes. La prueba física de este cambio sigue pendiente.

Evidencia y capturas: `reports/taskbar-center-fix/menu-tests.json` y archivos PNG del mismo directorio. El emulador queda abierto con Start desplegado.
