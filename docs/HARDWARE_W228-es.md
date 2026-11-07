# W228: modo ROOT y discos USB como unidades

[English](HARDWARE_W228.md) | [Español](HARDWARE_W228-es.md)

Resume J001, W227 y W228. Logs de W228: `reports/wine-hardware-w228/physical/20261104T215518Z/` (PWJB mode=root, jailbreak rc=0, identity setuid=1 wineserver_lookup=2, PWDRIVE d: y e:, relanzamiento con source=relaunch, `pe_machine path=/mnt/usb1/PC/Grand Theft Auto Vice City/gta-vc.exe machine=0x14c`).

## Qué hace

- **Para qué:** desde su sandbox, la app no ve `/mnt`, y los discos USB del usuario están en `/mnt/usb0`..`/mnt/usb7`. El modo ROOT pide a GoldHEN el jailbreak de su SDK antes de que arranque Wine, y los discos aparecen como unidades de Windows.
- **Opcional:** sin elegir ROOT, el arranque es el de siempre (NORMAL), sin jailbreak y sin unidades USB.
- **Requisito:** GoldHEN con el comando del SDK (syscall 500). Probado en la PS4 Pro del usuario (firmware informado 12.52). Sin GoldHEN, el pedido falla con su código en el log y la app arranca igual, sin unidades.

## Cómo se elige

En la pantalla de carga, debajo del logo, hay dos recuadros:

| |NORMAL|ROOT|
|---|---|---|
| Posición | izquierda, elegido de entrada | derecha |
| Qué pasa | el sandbox de la app, sin discos USB | jailbreak de GoldHEN, discos USB como D: a K: |

- **Cambiar:** izquierda o derecha en la cruceta o en el stick izquierdo.
- **Arrancar:** X arranca en el acto. Si no se aprieta X, arranca con lo elegido a los 2,5 s, y cada cambio da 2,5 s más para confirmar.
- **El X que abrió la app no cuenta:** la primera lectura del mando sólo registra lo que ya está apretado.
- **Sin mando:** arranca NORMAL en el acto.
- **Programas que reinician el título** (los de 32 bits, iniciados desde el escritorio): el título reinicia sin preguntar y usa el modo del primer arranque, guardado en `/data/orbis-win/boot-mode.txt`.

## Qué pasa en ROOT

1. **Jailbreak:** antes de Wine (justo antes de unir `system.reg`), el lanzador llama al comando 2 del SDK de GoldHEN, que guarda las credenciales originales en un respaldo.
2. **Vuelta al usuario de la app:** enseguida, `setuid` al uid del respaldo (el 1, el de la app). La raíz del proceso sigue siendo la de la consola y sin prisión, así que `/mnt` sigue visible.
   - En W227, Wine corrió como uid 0 y se detuvo en `wineserver: lstat /data/wine-prefix/.wineserver/server-…: Permission denied`.
   - `.wineserver` es la carpeta de Wine, en modo 0700 y del uid 1. En esta consola, el uid 0 de GoldHEN no saltea los permisos de archivos.
   - Además, Wine corriendo como 0 dejaría en el prefijo archivos del uid 0 que un arranque NORMAL no podría usar.
3. **Si el `setuid` falla:** se deshace el jailbreak y la app arranca como NORMAL, sin unidades, con el motivo en el log.
4. **Al salir:** el jailbreak se deshace con el comando 3 y el respaldo. Pasa al salir (`exit`, `_exit`), si la app se cae, y antes de cada `sceSystemServiceLoadExec` (el reinicio para un programa de 32 bits). Si ese reinicio falla, el jailbreak se pide de nuevo. Las credenciales terminan con el proceso de todos modos; así el cierre y el reinicio que pide la app salen desde el sandbox, como sin ROOT.

## Unidades

|Ranura| Unidad |
|---|---|
| `/mnt/usb0` | D: |
| `/mnt/usb1` | E: |
| … | … |
| `/mnt/usb7` | K: |

- **Letras fijas por ranura:** un disco en usb1 es E: aunque D: esté libre. En W228, Vice City estaba en usb1 y arrancó desde `E:\PC\…`.
- **Sólo ranuras con un disco:** J001 mostró que, con el jailbreak, usb0..usb7 existen siempre, y las vacías son carpetas del mismo dispositivo que `/mnt`. Una ranura cuenta como unidad cuando su `st_dev` es distinto del de `/mnt`. Sin el jailbreak, `/mnt` no existe y no aparece ninguna letra.
- **Sin conexión en caliente:** las letras se arman una vez, al arrancar Wine. Un disco conectado después aparece en el próximo arranque. Hay que conectar el disco antes de abrir la app.
- **Acceso como uid 1:** la app lee los discos con su propio usuario, no como root. En W228 se pudo leer el disco y cargar Vice City.
  - Escribir en el disco no se probó, y depende de cómo la consola montó el disco.
  - Vice City guarda la configuración y las partidas en Mis documentos (C:), así que no necesita escribir en el disco.
- **Tipo y etiqueta:** no se agregó nada. Wine trata la unidad como un disco fijo, no extraíble, y la consola no informa el nombre del volumen.

## Programas desde D: a K:

Un programa iniciado desde el escritorio reinicia el título con su ruta de Windows (W043, `/data/orbis-win/next.txt`). Esto también vale con `launch.txt`. Antes, el lanzador sólo aceptaba C: en dos lugares; ahora `windows_unix_path()` pasa D:..K: a `/mnt/usb0`..`/mnt/usb7`:

- `pe_machine`, que lee la cabecera PE para elegir el arranque de 32 bits;
- la carpeta inicial del programa (`PW_PROGRAM_DIR`, W130).

## Líneas del log

| Línea | Qué dice |
|---|---|
| `PWJB mode=normal\|root source=screen pad=… confirmed=… changes=… waited_ms=…` | la elección en pantalla |
| `PWJB mode=… source=relaunch` | el modo tomado del primer arranque |
| `PWJB jailbreak rc=… errno=… uid=… mnt_usb0=…` | el comando 2 de GoldHEN |
| `PWJB identity setuid=1 rc=… errno=… uid=… euid=… wineserver_lookup=…` | la vuelta al usuario de la app; `wineserver_lookup=2` (ENOENT) quiere decir que la carpeta de Wine se puede recorrer, y 13 que no |
| `PWJB unjailbreak who=exit\|_exit\|crash\|switch_program\|identity rc=… uid=…` | el jailbreak deshecho |
| `PWDRIVE e: -> /mnt/usb1 dev=…` | una unidad USB armada |

## Cómo se llegó

- **J001** (sonda `ORBB00001`, `native/mnt_probe.c`, `tools/build-mnt-probe.py`): desde el sandbox, `/mnt` y `/mnt/usb*` dan ENOENT. Con el jailbreak, uid 0 y `/mnt` lista `usb0`..`usb7`, con dos discos (usb0 y usb1). Después de deshacerlo, uid 1 y ENOENT otra vez.
- **W227:** la elección y el jailbreak funcionaron, y las unidades aparecieron (`PWDRIVE d:` y `e:`). Wine se detuvo en la carpeta del servidor (sección anterior).
- **W228:** con la vuelta a uid 1, ROOT llega al escritorio, los discos se ven y Vice City carga desde un SSD por USB.

## Archivos

| Archivo | Cambio |
|---|---|
| `native/wine_hardware.c` | La elección en pantalla (`boot_choose`, `draw_choice`), el jailbreak y su vuelta atrás, `setuid` al usuario de la app, y `windows_unix_path` para `pe_machine` y la carpeta inicial. |
| `native/hw_pad.c` | El mando se abre una sola vez (`pw_hw_pad_handle`) y lo comparten la elección y el hilo de entrada. El título no importa `scePadClose`, y un segundo `scePadOpen` del mismo usuario falla. El hilo de entrada arranca recién con Wine, así que lo que se apriete en la elección no llega a Wine. |
| `platform/ps4/pw_wine_fs.c` | La tabla de unidades suma D:..K: para las ranuras con disco. |
| `native/mnt_probe.c`, `tools/build-mnt-probe.py` | La sonda J001. |
| `.deps/downloads/goldhen-sdk/` | Siete archivos del SDK de GoldHEN (licencia MIT, `github.com/GoldHEN/GoldHEN_Plugins_SDK`), bajados con permiso del usuario. El lanzador no enlaza el SDK: hace la misma llamada (syscall 500 por la syscall indirecta 0) en su propio código. |

## Pendiente

- Probar si se puede escribir en un disco USB como uid 1.
- Conexión en caliente: las letras no cambian sin reiniciar.
- Tipo extraíble y etiqueta de volumen (W180, plan de la fase 10).
- Los programas de 32 bits relanzados enumeran unidades con el kernelbase de 32 bits, que no tiene el parche W105 de `GetLogicalDrives`.
