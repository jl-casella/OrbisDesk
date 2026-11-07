# W180: discos USB como unidades D: a K: (fase 10, borrador)

[English](HARDWARE_W180-usb-borrador.md) | [Español](HARDWARE_W180-usb-borrador-es.md)

Borrador de la sesión lateral, para unir a `HARDWARE_W180.md`. Depende de la sonda `PWUSB` de W179: si la app no ve `/mnt/usbN`, nada de esto sirve y hace falta otra decisión (ver Riesgos). Las piezas se compilaron por separado y no se probaron en la consola.

## Resultado de la sonda de W179

`reports/wine-hardware-w179/physical/20261103T221219Z/run-0001.log`, línea 125, con un disco conectado antes de abrir la app:

```
PWUSB slot=0 stat=-1 errno=2 dir=0 entries=-1 list_errno=0 first=- statfs=-1 errno=0 version=00000000 type=- rdonly=-1 from=- on=-
```

`/mnt/usb0` no existe para la app, y tampoco aparece ninguna de las ranuras 1 a 7. Las letras de abajo esperan a la segunda sonda (W180): lista `/`, `/mnt`, `/mnt/sandbox/ORBW00002_000`, `/mnt/ext0`/`ext1`, `/mnt/disc`, `/app0`, `/data`, la carpeta de la palabra aleatoria del sandbox y otras, con una línea `PWUSB path=…` cada una. No usa `getfsstat`, porque habría que llamarlo como syscall directa y, si el sandbox la rechaza, termina la app.

## Cambio (cuando la app vea los discos)

| Archivo | Qué hace |
|---|---|
| `platform/ps4/pw_wine_fs.c` / `.h` | La tabla de montajes pasa de C:/Z: a C:, Z: y `d:`..`k:`, que apuntan a `/mnt/usb0`..`/mnt/usb7`. Si un disco no está conectado, su ruta da ENOENT como cualquier destino que falta, así que la letra aparece y desaparece con el disco: `GetLogicalDrives` de 64 bits ya prueba las raíces (W105). Funciones nuevas: `pw_wine_fs_usb_slot(fd)`, que da la ranura comparando `st_dev` con cada `/mnt/usbN`, y `pw_wine_fs_usb_label`, que lee `.windows-label` de la raíz del disco si el archivo existe. |
| `tools/build-wine-directory-ps4.py` (`file.c` de ntdll) | `FileFsDeviceInformation` marca `FILE_REMOVABLE_MEDIA` en archivos de un disco USB, y `GetDriveType` da `DRIVE_REMOVABLE`. `FileFsVolumeInformation` toma la etiqueta de `.windows-label`; sin ese archivo queda vacía, porque la consola no informa el nombre del volumen. El número de serie queda en 0. |
| `tools/build-explorer-hw.py` (`desktop.c`) | Un hilo compara `GetLogicalDrives` cada 2 s. Cuando cambia, envía `WM_DEVICECHANGE` (`DBT_DEVICEARRIVAL` / `DBT_DEVICEREMOVECOMPLETE` con `DEV_BROADCAST_VOLUME`) a todas las ventanas y `SHChangeNotify(SHCNE_DRIVEADD/REMOVED)`, y escribe una línea `PWDRIVE X: arrived|removed`. En Windows y en Wine lo hace mountmgr, que aquí no corre. |
| `tools/patch-wfm-files.py` | WFM vuelve a listar la vista actual con `WM_DEVICECHANGE` y escribe `PWFM device_change refresh`. El árbol de la izquierda se actualiza recién al plegar y desplegar "Computer". |
| `native/wine_hardware.c` (sesión principal) | `pe_machine` y `program_cwd` aceptan D:..K: (`/mnt/usbN`) además de C:, para relanzar un título de 32 bits desde el disco con su carpeta. |
| `fixtures/win32/drivetest.c` (nuevo) y `tools/build-wine-hardware.py` | `drivetest64.exe` y `drivetest32.exe` (`[letra]`, D: por defecto) escriben en `C:\orbis\drive-result.txt`: unidades y tipos, volumen (etiqueta, serie, FS), espacio, listado de la raíz, lectura del final del archivo más grande y un guardado `D:\orbisdesk-test\save.txt` (escribir, releer, comparar y borrar). |

## Construcción

1. `python3 tools/build-wine-directory-ps4.py`
2. `python3 tools/build-explorer-hw.py`
3. `python3 tools/build-wfm.py` (aplica `patch-wfm-files.py`)
4. `python3 tools/link-wine-boot.py`
5. `python3 tools/build-wine-hardware.py`

## Prueba

1. Con el disco conectado antes de abrir la app, correr `C:\orbis\drivetest64.exe` y `drivetest32.exe`. En `drive-result.txt` debería salir `drive D: type=removable`, el listado y `write ok=1 same=1`, si la sonda de W179 mostró que se puede escribir.
2. Con explorer y WFM abiertos, desconectar el disco y volver a conectarlo. En el log deberían aparecer `PWDRIVE D: removed` / `arrived` y `PWFM device_change refresh`, y D: debería desaparecer y volver en WFM.
3. SuperMarioKart desde el disco, sin copiarlo: carpeta `SMK` copiada a la raíz del disco y abrir `D:\SMK\SuperMarioKart.exe` desde WFM. Requiere el cambio de `wine_hardware.c`.
4. Un guardado del juego en el disco, si el paso 1 dio `write ok=1`.

## Límites y riesgos

- **Sandbox:** la app no hace jailbreak. Si `PWUSB slot=0` da `errno=2/1/13`, la app no ve los discos. Usar el jailbreak del SDK de GoldHEN sería una decisión aparte.
- **Notificaciones de directorio:** el servidor en proceso no avisa cambios de directorio (no hay inotify) en ninguna unidad. WFM no muestra archivos nuevos de D: hasta refrescar. La conexión en caliente no depende de eso.
- **Desconectar con archivos abiertos:** las lecturas fallan, y un juego que corre desde el disco se cae.
- **Letras fijas por ranura:** usb0 es D:, usb1 es E:, aunque D: esté libre.
- **Programas de 32 bits que enumeran unidades:** el `GetLogicalDrives` de 32 bits no tiene el parche W105 y devuelve 0. Las rutas `D:\…` funcionan igual. El parche para el kernelbase de i386 queda como paso opcional.
- **exFAT/FAT32:** los nombres de más de 255 bytes en UTF-8 no entran en `d_name`. FAT32 corta en 4 GiB, guarda fechas con resolución de 2 s y no tiene bits de permisos.

## Prueba física

Pendiente.
