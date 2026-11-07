# W097: diagnóstico de Start después de cerrar invitados gráficos

[English](HARDWARE_W097.md) | [Español](HARDWARE_W097-es.md)

W096 permitió al usuario ejecutar vkspin, vkcube y glxgears juntos, pero Start dejó de abrir después del cierre. Los tres invitados salieron con 0 y siguió llegando entrada del mouse. No hay evidencia suficiente para distinguir aún un bloqueo del shell de un problema de entrega de entrada.

Evidencia: `reports/wine-hardware-w096/physical/20261102T103537Z/analysis.md`.

W097 conserva MangoHud y Wine Unix de W096. Cambia explorer para añadir un observador independiente y marcas de progreso, y kernelbase para registrar el resultado de la espera de hilos auxiliares. **No declara solucionado el fallo**. No se incorpora el cambio pendiente de porcentajes CPU/GPU ni se ejecuta matriz local, conforme a la indicación vigente del usuario.

## Interpretación de las trazas

`PWSHELL monitor` informa la antigüedad del heartbeat del reloj del hilo real del shell, el estado GUI y las ventanas activas/de foco/captura/menú. No intenta reiniciar el escritorio ni simular respuesta. El observador no usa SendMessage.

Etapas de `PWSHELL stage`:

|Etapa| Punto |
| --- | --- |
| 20 | Regresó el manejador de un clic de la barra |
| 30 | Entró notificación de creación/destrucción de ventana |
| 31 / 32 | Antes / después de destruir el botón de una ventana cerrada |
| 33 / 34 | Antes / después de limpiar iconos de esa ventana |
| 35 / 36 | Antes / después de sincronizar botones de la barra |
| 100 / 101 | Antes / después de destruir el menú anterior |
| 102 / 103 | Antes / después de enumerar Start y cargar sus iconos |
| 104 | Configuración de carpeta especial de Control Panel |
| 105 / 106 | Entrada / retorno de TrackPopupMenuEx |

Una etapa 105 con heartbeat activo puede ser simplemente un menú abierto. `other_threads_wait=258` indica timeout; 0, finalización de todos los hilos esperados. Un timeout mantiene su comportamiento anterior: W097 sólo lo registra.

## Construcción y prueba física

Desde el workspace en Ubuntu-22.04:

```sh
python3 tools/build-explorer-hw.py
python3 tools/build-guest-hw.py
python3 tools/build-wine-hardware.py
python3 tools/upload-hardware.py --build W097 --host 192.168.68.104
```

APP_VER 01.96, título ORBW00002. Cerrar OrbisDesk antes de instalar. Abrir las tres aplicaciones, cerrarlas y pulsar el centro del botón Start. Si falla, dejarlo así unos 15 segundos para que el observador registre el estado y avisar. No hace falta esperar un minuto ni interpretar el reloj a simple vista.

Subida verificada por lectura de vuelta: `/data/pkg/orbis-win-W097-0641ae78ebb8.pkg`, SHA-256 `0641ae78ebb8ef0bebd0f8fa17e86b283aa738be45c644793da786823740b567`. Informe: `reports/wine-hardware-w097/transfers/20261102T104911Z.json`. Runtime: 548 archivos, 537 presentes, 11 subidos, ningún fallo de permisos.

Mientras se preparaba esta entrega, el usuario precisó que al cerrar vkcube también se detuvieron glxgears y vkspin y dejó de abrir Start. Ese síntoma amplía la investigación al cierre compartido y sus bloqueos, no sólo al menú. Una segunda descarga W096, `physical/20261102T104940Z`, tiene los mismos dos logs sin cambios; no aporta una sesión adicional con esa reproducción. En W097 hay que cerrar **vkcube primero, dejando las otras dos ventanas abiertas**, y dejar unos 15 segundos si se congelan. El estado de Start se comprueba después.

```sh
python3 tools/fetch-hardware.py --build W097 --host 192.168.68.104
```

## Resultado recibido

Logs en `reports/wine-hardware-w097/physical/20261102T105238Z/`. En la segunda sesión las tres aplicaciones cierran con 0 y sus esperas de hilos también devuelven 0. Start abre y retorna al seleccionar otra entrada. El log se corta al recargar glxgears, antes de crear el nuevo hilo; no registra una excepción ni una salida final del título. El usuario informa crash de la app. Se continúa en [W098](HARDWARE_W098-es.md) con trazas de la carga de módulos.
