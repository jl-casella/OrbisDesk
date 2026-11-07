# W098: carga de gráficos después de cerrar invitados

[English](HARDWARE_W098.md) | [Español](HARDWARE_W098-es.md)

W097 mostró que Start recibe el clic, enumera y presenta su menú y retorna al seleccionar una entrada. El corte posterior corresponde a una nueva carga de glxgears. Las esperas de hilos auxiliares devolvieron 0. El crash informado por el usuario no dejó excepción SEH ni salida final del título en el log.

Evidencia: `reports/wine-hardware-w097/physical/20261102T105238Z/analysis.md`.

W098 es diagnóstico focalizado, no una corrección declarada:

- `trace+module,trace+seh,trace+loaddll` para observar la carga/descarga y las inicializaciones de DLL. Es temporal y puede afectar rendimiento y tamaño del log.
- `PWGUEST load_begin/load_end` con nombre del EXE, resultado y estimación de memoria del kernel antes de cargar. Esas cifras no equivalen al RSS del título.
- `PWGUEST unload_begin/unload_end` con resultado de FreeLibrary y presencia de opengl32, libgallium_wgl y libMangoHud antes/después. Las direcciones son evidencia del módulo encontrado, no demuestran que todos sus objetos sean válidos.
- `PWSHELL clocks` añade tiempo QPC transcurrido y el tick compartido de Wine, para detectar si este último deja de avanzar durante el problema.

Se mantienen el arreglo MangoHud de W096 y los objetos Unix de Wine. Los porcentajes CPU/GPU siguen aplazados. Se omite la matriz local por indicación del usuario. APP_VER 01.97, título ORBW00002.

Compilada y transferida a 192.168.68.104 con lectura de vuelta verificada: `/data/pkg/orbis-win-W098-b46d085a7675.pkg`, SHA-256 `b46d085a76759c0e85c741b6aa49708288834acb633094a18bcc9c358f561cf0`. Informe: `reports/wine-hardware-w098/transfers/20261102T110952Z.json`. Runtime: 548 archivos, 539 presentes, 9 subidos, sin fallos de permisos. Instalación manual y prueba física pendientes.

## Reproducción física

Cerrar OrbisDesk antes de instalar. Abrir vkcube, glxgears y vkspin. Cerrarlos, volver a Start y abrir glxgears otra vez. Si sigue respondiendo, repetir una vez. Si se congela sin cerrar, esperar 15 segundos; si se cierra solo, avisar y pasar el código de error de PS4 si lo muestra. No hace falta repetir muchas sesiones.

```sh
python3 tools/build-explorer-hw.py
python3 tools/build-guest-hw.py
python3 tools/build-wine-hardware.py
python3 tools/upload-hardware.py --build W098 --host 192.168.68.104
python3 tools/fetch-hardware.py --build W098 --host 192.168.68.104
```

## Hipótesis adicional a comprobar

En `upstream/Crema/port/mesa/ac_ps4_drm.c`, `ac_drm_device_deinitialize` es un no-op explícito: el comentario dice que el dispositivo vive durante todo el proceso. Eso merece revisar recursos retenidos entre ciclos de apps dentro de nuestro único proceso. No demuestra OOM ni justifica liberar el dispositivo sin revisar sus referencias, colas, buffers diferidos y otros usuarios. W098 no modifica el driver; sus cifras de memoria son evidencia preliminar, no una medición completa de recursos GPU ni una prueba definitiva de esta hipótesis.

## Resultado físico

El usuario completó W098 y confirmó CE-34878-0 al cerrar vkcube con las otras dos apps abiertas. Logs en `reports/wine-hardware-w098/physical/20261102T113949Z/`. El corte ocurre durante la salida de un worker y limpieza de user32, antes del ExitProcess del invitado; no se llegó a recargar glxgears en esta reproducción. Los relojes QPC/tick avanzaban. Se continúa en [W099](HARDWARE_W099-es.md).
