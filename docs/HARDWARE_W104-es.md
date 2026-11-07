# W104: etiquetas CPU/GPU y fuente CPU corregida

[English](HARDWARE_W104.md) | [Español](HARDWARE_W104-es.md)

APP_VER 02.03. A pedido del usuario, las etiquetas visibles quedan CPU y GPU, sin «app». Siguen midiendo el título OrbisDesk con sus invitados; no representan el consumo global de la consola.

La prueba W103 dejó CPU fija en 16,666 %: el reloj importado con ID 15 avanzó prácticamente como el tiempo transcurrido. Se rechazó esa métrica. W104 usa getrusage(RUSAGE_SELF), sumando tiempo de usuario y de kernel del proceso, y conserva la normalización por tiempo transcurrido y afinidad inicial. Un error o un intervalo inconsistente muestra N/A. La disponibilidad y los valores de esta nueva fuente deben comprobarse en la PS4.

GPU conserva los timestamps GFX de Crema y el muestreo en el frame de W102. En W103 se observaron valores de 0,356 a 8,909 %, sin eventos perdidos. No se añaden hilos de estadísticas ni cambios de ciclo de vida.

```sh
bash tools/vk-h0/build-mangohud.sh
python3 tools/build-wine-hardware.py --mangohud enabled
python3 tools/upload-hardware.py --build W104 --host 192.168.68.104 --timeout 60
```

Se reutiliza el objeto de consulta privada de W103, ya verificado por hash; se recompila el proveedor nativo y MangoHud. No se ejecuta el preparador Unix ni una matriz local, según la preferencia vigente.

En consola: observar CPU/GPU con una y tres aplicaciones, repetir abrir/cerrar las tres y volver a Start. Tras «Ya la probé», descargar y revisar los logs:

```sh
python3 tools/fetch-hardware.py --build W104 --host 192.168.68.104
```

Comprobar que CPU deja de estar fija, revisar errores/rangos y deltas crudos, pérdidas GPU y salidas de invitados. La ausencia de crash por sí sola no valida los porcentajes. Construcción, transferencia y prueba física se documentan por separado en reports/wine-hardware-w104.

Compilación completada. PKG SHA-256: 33b5527618262a29db545d5e108d9e96c63170f513336adf04d4a8315139e87f. ELF SHA-256: a9571e8eeeaf797e96b18eba9c0819143fb319861608b1de7aa3c721a366c09d. Fuentes de build y manifiesto archivados en release-w104. Un ajuste posterior de metadatos describe la fuente getrusage y las etiquetas; no cambia binarios. El script original está archivado con su hash de compilación.

Transferencia verificada por lectura de vuelta: `/data/pkg/orbis-win-W104-33b552761826.pkg`. Informe: reports/wine-hardware-w104/transfers/20261102T141256Z.json. 548 archivos de runtime verificados, 545 presentes y 3 subidos; sin fallos de permisos. W103 retirado después de verificar. Prueba física pendiente.

## Resultado físico: 20261102T141838Z

Logs descargados y analizados en reports/wine-hardware-w104/physical/20261102T141838Z/analysis.json. 90 muestras: CPU entre 6,917 y 32,801 %, GPU entre 0,08 y 9,5 %. CPU acumulada monotónica, sin muestras con errores y sin pérdidas GPU. Con tres apps se observan CPU alrededor de 28–31 % y GPU alrededor de 8–9 %; al cerrar aplicaciones descienden, llegando CPU a aproximadamente 7–9 % y GPU a 0,8–0,9 % antes del último cierre. Se resuelve el defecto observado de CPU fija en 16,666 %. No hay calibración independiente de exactitud absoluta.

Tres aperturas y tres cierres con código 0, sin marcador de crash. El hilo del escritorio registra actividad después del cierre, pero el log no acredita dos ciclos ni salida final del título. No se convierte el estado automático presented en una aceptación de estabilidad general.
