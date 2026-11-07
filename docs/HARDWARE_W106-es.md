# W106: abrir archivos desde WFM sin reemplazar el escritorio

[English](HARDWARE_W106.md) | [Español](HARDWARE_W106-es.md)

APP_VER 02.05. El usuario confirmó el listado de W105, pero abrir documentos reinicia la app. Logs: reports/wine-hardware-w105/physical/20261102T145327Z. En run-0001 y run-0003, result.txt y vkspin64.txt llegan a switch_program como imágenes ejecutables. Los arranques siguientes fallan con c000007b y vuelven al escritorio. Es un reemplazo del título por un documento, no un crash demostrado por excepción. El análisis queda en analysis.json de esa sesión.

## Cambios

WFM envía ruta y directorio a la ventana de escritorio con WM_COPYDATA. Explorer comprueba emisor del mismo proceso, tamaño y terminación de cadenas; copia los datos a su heap y publica una solicitud en su propio hilo. Resuelve open mediante ShellExecuteExW NOASYNC, siguiendo la ruta shell que usa Start. La solicitud no conserva memoria ni ejecuta un worker del invitado WFM. Un fallo de envío o apertura se muestra como error. PWOPEN registra cola, resultado y thread ID. Ambos binarios registran el hash del protocolo común; el empaquetador rechaza versiones que no coincidan.

El prefijo registra asociaciones reales para .txt/.log/.ini/.cfg/.conf/.json/ .md/.csv/.xml con Notepad PE64 y argumento de archivo entre comillas. No se ejecuta un documento como PE ni se simula una apertura satisfactoria.

En modalidad PS4, kernelbase bloquea la ruta antigua de reemplazo del título si no hay invitado compatible o falló su carga (STATUS_NOT_SUPPORTED). Devuelve un fallo normal de creación. Los EXE PE64 compatibles se abren en hilos de invitados; PE32 no está implementado como invitado concurrente y falla sin reiniciar. El arranque inicial PE32 del launcher es independiente y conserva su ruta. Se mantiene el tratamiento explícito de wineboot para salir. No cambia Orbis ni shadPS4.

Listado W105 y métricas CPU/GPU W104 se mantienen. Calibración aplazada.

```sh
python3 tools/build-wfm.py
python3 tools/build-explorer-hw.py
python3 tools/build-guest-hw.py
python3 tools/build-wine-hardware.py --mangohud enabled
python3 tools/upload-hardware.py --build W106 --host 192.168.68.104 --timeout 60
```

Sin matriz local. Prueba PS4: abrir C:\orbis\result.txt desde WFM y comprobar contenido en Notepad; cerrar Notepad y seguir navegando en WFM. Repetir con otro texto y probar vkspin64.exe/vkcube.exe desde WFM manteniendo sus ventanas y Explorer abiertos. Un EXE no compatible y un archivo sin asociación debe devolver error sin reiniciar el escritorio. Cerrar WFM y probar Start. No modificar documentos existentes durante esta prueba.

```sh
python3 tools/fetch-hardware.py --build W106 --host 192.168.68.104
```

Revisar PWOPEN y cargas de invitados desde el hilo de Explorer, ausencia de switch_program por documentos y contenido visible informado por el usuario. Construcción, entrega y ejecución se documentan por separado; compilar no valida por sí solo el enrutamiento real de ShellExecute en la consola.

Compilación completada; fuentes y manifiestos archivados en release-w106. PKG SHA-256: 02a9368dc02f976ae4a6c87f9f6fb98da18b8e4ea99923b7168c6a7c38e148ad. ELF SHA-256: 5deac57a1dc22ee346a5d8117b997edf10b8a3d68b89ed8459ca0956d44f5264. Cerrar OrbisDesk antes de instalar para evitar que la sesión anterior guarde su registro sobre las nuevas asociaciones. Las asociaciones se incluyen en user.reg y se verifican junto al resto del runtime en la transferencia.

Entrega completada con lectura de vuelta verificada: `/data/pkg/orbis-win-W106-02a9368dc02f.pkg`. Informe: reports/wine-hardware-w106/transfers/20261102T150943Z.json. 548 archivos verificados, 536 presentes y 12 subidos; sin fallos de permisos. W105 retirado después de verificar. Prueba física pendiente del usuario.

## Prueba física: 20261102T151517Z

El usuario confirma EXE correctos y textos fallidos. PWOPEN en hilo 0024 confirma vkspin64.exe, gui-window64.exe y gui-text64.exe abiertos. Dos textos se rechazan sin switch_program; no se carga Notepad. El guard conserva el escritorio. La asociación quedó en HKCU Classes pero HKCR fijado consulta Machine Classes. W107 corrige la ubicación. Evidencia y análisis: reports/wine-hardware-w106/physical/20261102T151517Z/analysis.json.
