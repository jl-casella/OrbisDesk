# OrbisDesk: paquete con nombre limpio (W284)

[English](HARDWARE_W284.md) | [Español](HARDWARE_W284-es.md)

Cambio de presentación sobre W283. El título de PS4 es `OrbisDesk`, sin sufijo de build, y el archivo distribuido es `OrbisDesk.pkg`.

La versión visible `03.83 (W284)` aparece sólo en la pantalla inicial de elección NORMAL/ROOT. Se retira el pie de versión de la carga posterior y de la pantalla de error. Los logs mantienen su identificación interna y quedan en `/data/orbisdesk/w284`. No cambia la ejecución de programas ni las opciones de modo.

Se mantiene la identidad ORBW00002 y su Content ID. APP_VER/VERSION del SFO son 03.83 para permitir la actualización de la instalación existente; no son parte del título. La versión técnica no se reinicia a 01.00.

## Validación

Compilación finalizada: `out/wine-hardware-w284/OrbisDesk.pkg`. SFO correcto: TITLE=OrbisDesk, APP_VER=03.83 e identidad anterior conservada. 58 hashes fuente coincidentes. Ubicación de la versión comprobada en el código de dibujo. SHA256 del paquete: `bc57f0268524449e916aef601445c83e0e8b3cc5e220e20c887b78609c70e1cb`. Evidencia: `reports/wine-hardware-w284/release-w284/verification.json`. Prueba visual e instalación en PS4 pendientes. Entrega FTP completada: `/data/pkg/OrbisDesk.pkg` en 192.168.68.100:2121. Se verificaron PKG y 1.823 archivos runtime (1 subido, 1.822 presentes), sin fallos de permisos; un paquete anterior retirado tras verificar. Se preservaron los ajustes de consola. Evidencia: `reports/wine-hardware-w284/transfers/20261107T144147Z.json`.

Comparación de runtime: mismos 1.823 archivos, sin entradas eliminadas; sólo se regeneró `winecfg.cpl` durante el build habitual (fuente sin cambios). No se repite la matriz funcional de Wine para este cambio de presentación.

## Prueba física recogida (2026-11-07)

El usuario instaló y probó la nueva entrega. Evidencia descargada desde 192.168.68.100:2121 en `reports/wine-hardware-w284/physical/20261107T153807Z/`. Log `run-0001.log`: W284 confirmada, modo root, presentación de imagen hasta `t_ms=684982` y movimientos de puntero posteriores. Sin registro `W284 crash`, sin excepción no manejada ni código final de salida. Clasificación: `presented`; no equivale a una aprobación de toda la compatibilidad de juegos.

La captura `screen.png` muestra ORBISDESK en el selector NORMAL/ROOT y el pie VERSION 03.83 W284. La ausencia de versión en las otras pantallas se comprobó en código; esta captura corresponde únicamente al selector. Una excepción de syscall durante el volcado diagnóstico de hilos retorna a su manejador y la sesión continúa; no se clasifica como cierre fatal.
