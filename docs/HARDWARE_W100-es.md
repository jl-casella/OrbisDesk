# W100: exclusión mutua para el asignador nativo del SDK

[English](HARDWARE_W100.md) | [Español](HARDWARE_W100-es.md)

W099 completa cierres del overlay y permite reabrir aplicaciones. Tras otro ciclo se bloquea Start con un acceso inválido nativo en malloc+0x5ea. El PC se simbolizó usando la base real de carga confirmada por un símbolo del log. Evidencia: `reports/wine-hardware-w099/physical/20261102T120118Z/analysis.md`.

## Cambio

`native/native_heap.c` protege malloc, calloc, realloc, free, memalign, __memalign, aligned_alloc y posix_memalign mediante --wrap al enlazar. El mutex es un propietario atómico de identidad libkernel (scePthreadSelf), con profundidad recursiva para llamadas entre las funciones de la familia. La espera usa sceKernelUsleep; no requiere pthread de musl ni asigna memoria para obtener el bloqueo. Se preservan errno, resultados, alineamiento y comportamiento real del asignador. No se ignoran punteros inválidos.

El musl enlazado condiciona sus locks a su contador interno de hilos, pero el port crea hilos a través de libkernel. No se escribe sobre ese contador privado ni se habilitan otras rutas de pthread/TLS de musl. Se serializan las entradas del asignador desde el enlace, también para los constructores nativos que las usen. `PWHEAP serialized_sdk_allocator entries=8` registra activación y contadores de inicio; no equivale a una prueba de estrés ni a validación en hardware.

Se verificó compilación/enlace y presencia de los ocho wrappers. No se ejecuta matriz local por indicación del usuario. Los objetos Unix, DLL PE y runtime son idénticos a W099; permanecen el arreglo de cierre de MangoHud y sus trazas. CPU/GPU porcentajes siguen aplazados. La desaparición del fallo físico aún debe comprobarse; el puntero inválido también podría tener otro origen.

APP_VER 01.99, título ORBW00002. La siguiente APP_VER deberá ser 02.00, no 01.100.

## Construcción y prueba

```sh
python3 tools/build-wine-hardware.py
python3 tools/upload-hardware.py --build W100 --host 192.168.68.104
```

El uploader verifica PKG y runtime antes de retirar el PKG Wine anterior de la consola. Conserva logs y copias locales. Cerrar la app antes de instalar.

Repetir dos ciclos: abrir vkcube, glxgears y vkspin, cerrar vkcube primero, cerrar las otras, volver a Start y reabrir las apps. Si se bloquea, dejarlo unos 15 segundos y avisar; si hay crash, indicar el código. Al terminar, pulsar «Ya la probé» para descargar:

```sh
python3 tools/fetch-hardware.py --build W100 --host 192.168.68.104
```

## Entrega completada

Tras un bloqueo FTP y la reactivación del servidor por el usuario en .104, la entrega terminó con lectura de vuelta verificada: `/data/pkg/orbis-win-W100-e388c48da7a5.pkg`, SHA-256 `e388c48da7a5b8972b7d1d7f472d8c4d5451238ebe1b47763f1f2d121ef056b1`. Informe: `reports/wine-hardware-w100/transfers/20261102T122627Z.json`. Runtime 548 archivos, 546 presentes y dos registros subidos; es idéntico al runtime generado para W099. Se borró el PKG W099 con respuesta FTP 250 y no hubo fallos de permisos ni limpieza. Logs y paquetes locales conservados. W100 sigue pendiente de ejecución física.

Resultado posterior: probado y con CE-34878-0 al cerrar programas. PWHEAP está activo y los tres invitados registran cierre 0, pero el log se corta al volver a Start, sin excepción capturada. No se considera solucionado el fallo del heap ni el cierre de apps. Se continúa con [W101](HARDWARE_W101-es.md), comparación sin cargar MangoHud; ver `reports/wine-hardware-w100/physical/20261102T122841Z/analysis.md`.
