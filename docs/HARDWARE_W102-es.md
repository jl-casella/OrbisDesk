# W102: MangoHud reactivado con muestreo en el frame

[English](HARDWARE_W102.md) | [Español](HARDWARE_W102-es.md)

El control W101 completó dos ciclos de las tres aplicaciones, seis salidas 0 y salida final 0 en la PS4. Se confirmó que MangoHud no se cargó. Evidencia: `reports/wine-hardware-w101/physical/20261102T125705Z/analysis.md`. Esto acota la investigación a la ruta activada por la capa; no prueba una causa única ni convierte desactivarla en la solución final.

## Cambio de ciclo de vida

`tools/vk-h0/patch-mangohud-frame-sampling.py` modifica la copia de compilación después de los parches W096/W099:

- hw_info_updater deja de crear un hilo y de retener parámetros de una instancia. Ejecuta update_hw_info durante el muestreo del frame, bajo el bloqueo de UI.
- fpsMetrics calcula en update_thread de forma síncrona y protege el reset con su mutex, sin trabajador, condición de salida ni espera activa.
- start_notifier deja de lanzar el observador del archivo. No hay recarga en vivo; la configuración indica guardar y reiniciar OrbisDesk para aplicarla.
- PWHUD informa sampling=frame, fps_metrics=frame y config_watcher=disabled.
- Se reactiva ImplicitLayers DWORD 0; el manifiesto y el marcador del lanzador registran MangoHud enabled. El registro de build incluye las fuentes nuevas y el empaquetador comprueba sus hashes y marcadores contra la DLL compilada.

El port mantiene sus políticas previas de hilos de invitados. Esta adaptación evita esos servicios persistentes de MangoHud en la ruta probada, sin introducir una simulación de procesos ni un protocolo privado de ownership en Win32. F2/logging, uploads y otros servicios opcionales no quedan validados por esta prueba. No se declara todavía que el crash esté resuelto.

Las llamadas y cálculos existentes de estadísticas se conservan; puede cambiar el coste/tiempo del frame al muestrear. No se han corregido ni validado los porcentajes CPU/GPU. Esos proveedores siguen aplazados. Wine Unix, DLL PE de Wine, heap W100 y driver se conservan. No se ejecuta matriz local.

## Construcción y prueba

APP_VER 02.01, título ORBW00002. El builder vuelve a default enabled; el comando reproducible lo indica expresamente:

```sh
bash tools/vk-h0/build-mangohud.sh
python3 tools/build-wine-hardware.py --mangohud enabled
python3 tools/upload-hardware.py --build W102 --host 192.168.68.104 --timeout 60
```

Cerrar OrbisDesk antes de instalar. Confirmar visualmente el overlay y repetir dos ciclos de abrir/cerrar glxgears, vkcube y vkspin y volver a Start; cerrar vkcube primero. Avisar con «Ya la probé». Verificar en los logs la carga real de MangoHud, política frame, salidas de invitados, reaperturas y respuesta de Start. Si hay sólo congelamiento, dejar 15 segundos; si hay crash, indicar código.

```sh
python3 tools/fetch-hardware.py --build W102 --host 192.168.68.104
```

Entrega completada y verificada: `/data/pkg/orbis-win-W102-09be7a07d5eb.pkg`, SHA-256 `09be7a07d5eb38aa1b348d0821c949edefb5fd821f18c9fabca0cac0dbbed42c`. Informe: `reports/wine-hardware-w102/transfers/20261102T130927Z.json`. 548 archivos verificados, 544 presentes y 4 subidos; sin fallos de permisos. W101 fue retirado después de verificar; evidencias y paquetes locales conservados. Prueba física de W102 pendiente.

## Resultado físico

Probado en PS4: dos ciclos con MangoHud cargado, seis aperturas y seis cierres con código 0, Start operativo y salida final 0 a los 63455 ms. Se verificaron PROCESS_ATTACH, handles hud no nulos y la política frame en los logs. No se registraron los accesos inválidos anteriores ni un crash de esta sesión.

Evidencia: `reports/wine-hardware-w102/physical/20261102T131731Z/`, con analysis.md y acceptance.json. Aceptación limitada a este escenario; no valida sesiones largas, funciones opcionales de logging ni porcentajes CPU/GPU.
