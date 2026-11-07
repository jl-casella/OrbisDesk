# W101: comparación de cierre sin cargar MangoHud

[English](HARDWARE_W101.md) | [Español](HARDWARE_W101-es.md)

W100 no eliminó el CE-34878-0. Los tres invitados cierran con 0 y el log se corta después, en Start, sin una nueva excepción ni PC. PWHEAP sí confirma activación del bloqueo. Evidencia: `reports/wine-hardware-w100/physical/20261102T122841Z/`.

## Variable de comparación

Se mantiene el heap W100, los objetos Unix de Wine, los DLL PE y MangoHud W099. La entrada HKLM Software\Khronos\Vulkan\ImplicitLayers de MangoHud pasa de DWORD 0 a DWORD 1 para impedir su carga automática por el loader Vulkan. El único archivo diferente del runtime frente a W100 es wine-prefix/system.reg. El lanzador cambia de identificación y registra experiment mangohud_layer=disabled.

**No es una corrección declarada ni una eliminación permanente del overlay.** Busca aislar la capa y sus hilos/dependencias antes de otro cambio de ciclo de vida. No habrá métricas de MangoHud durante esta prueba. Se conservan las trazas, incluidas las del inicio/fin de carga y presencia de DLL gráficas.

Es necesario comprobar en hardware que hud=0 y que no haya PROCESS_ATTACH de libMangoHud. Si se carga igualmente, la comparación no está validada. Un único ciclo correcto tampoco demuestra compatibilidad general ni una causa exacta.

## Construcción y entrega

```sh
python3 tools/build-wine-hardware.py --mangohud disabled
python3 tools/upload-hardware.py --build W101 --host 192.168.68.104 --timeout 60
```

APP_VER 02.00, título ORBW00002. El builder acepta --mangohud enabled/disabled; en W101 el valor por defecto es disabled. No reutilizar este número para una variante enabled sin archivar sus artefactos e identificar una iteración nueva. La futura vuelta al overlay debe quedar explícita en comando y manifiesto.

Entrega verificada: `/data/pkg/orbis-win-W101-c1c05a3fa350.pkg`, SHA-256 `c1c05a3fa35053ccdfa67530e7897bd4690ff0c3da9b6e6e436653d112d67ded`. Informe: `reports/wine-hardware-w101/transfers/20261102T124200Z.json`. 548 archivos verificados, 546 presentes y 2 registros subidos. Se eliminó W100 de la consola sin fallos, después de verificar. Evidencia y paquetes locales conservados; no hubo matriz de pruebas local.

## Prueba física pendiente

Abrir las tres aplicaciones y cerrarlas (vkcube primero). Abrir Start y repetir una vez el ciclo. Avisar con «Ya la probé»; si falla, indicar el código o dejar 15 segundos cuando sólo se congele. Se recuperan los logs mediante:

```sh
python3 tools/fetch-hardware.py --build W101 --host 192.168.68.104
```

Los porcentajes CPU/GPU siguen aplazados hasta estabilizar el cierre y restaurar la capa con su ciclo de vida corregido.

## Resultado físico

Probado: seis arranques y seis cierres 0 (dos ciclos), sin MangoHud cargado y con Start operativo. La sesión termina con salida 0 a los 83829 ms. Logs en `reports/wine-hardware-w101/physical/20261102T125705Z/`. Se sigue con [W102](HARDWARE_W102-es.md), capa reactivada con muestreo síncrono, aún sin validar.
