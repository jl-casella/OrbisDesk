# W109: borrado pendiente y diagnóstico del error 145

[English](HARDWARE_W109.md) | [Español](HARDWARE_W109-es.md)

APP_VER 02.08. El usuario confirmó que el 145 apareció al borrar carpetas con subcarpetas. W108 terminó con código 0, sin un crash registrado. Los mensajes PWFM Unicode no quedaron capturados; no se conoce aún la entrada exacta que bloqueó la operación. Se archivaron LIST de FTP, sin modificar contenidos: Documents/Test estaba vacío después de la sesión. Esto es compatible con una eliminación diferida, pero no demuestra su causa.

Evidencia W108: reports/wine-hardware-w108/physical/20261102T170507Z, incluidos desktop-tree-after-error.json, remaining-tree-roots.json y remaining-directory-entries.json. No se borraron carpetas de la PS4 por FTP.

## Cambios

- WFM reintenta únicamente RemoveDirectory real ante ERROR_DIR_NOT_EMPTY, como máximo 10 esperas de 50 ms en el worker. No vuelve a borrar contenido que aparezca concurrentemente. Respeta cancelación y falla si la carpeta no desaparece. No se simula éxito ni se omiten errores.
- PWFM convierte sus mensajes Unicode a UTF-8 mediante OutputDebugStringA, capturado en el canal de Wine, preservando GetLastError. Registra cada hijo, DeleteFile, reintento y resultado, además del diálogo existente.
- El adaptador nativo registra unlink/rmdir con ruta, retorno y errno.
- El objeto fd del servidor usa la receta probada para registrar la primera entrada que bloquea is_dir_empty y su resultado. Propaga errores de rewind/ readdir en lugar de tratarlos como vacío. No cambia los objetos base: se compila en build/delete-server-ps4, recompone las unidades originales tras verificar sus hashes y aplica el mismo namespace. Se sustituye exactamente el objeto combinado inprocess.o al enlazar; los originales quedan intactos.

W108 rename y las asociaciones/aperturas de W107/W106 se conservan. No se afirma que el 145 esté solucionado hasta repetir la prueba en consola.

```sh
python3 tools/build-wine-delete-server.py
python3 tools/build-wfm.py
python3 tools/build-wine-hardware.py --mangohud enabled
python3 tools/upload-hardware.py --build W109 --host 192.168.68.104 --timeout 60
```

Sin matriz local. En PS4: crear una carpeta de prueba con hijo/nieto y un archivo; renombrar padre, comprobar navegación y borrar confirmando. Si falla, conservar la carpeta para inspección y avisar. Revisar Start al terminar.

```sh
python3 tools/fetch-hardware.py --build W109 --host 192.168.68.104
```

## Consulta de desktop, siguiente iteración

El usuario creó test.lnk hacia test.txt y tampoco aparece. Se verificó por FTP que ambos existen en Desktop. Además de enumerar sólo *.lnk, el código de Explorer descarta un launcher si extract_icon no consigue icono. Intenta extraerlo del .lnk o del destino; un .txt no contiene iconos PE. La siguiente iteración debe dar un icono de asociación/genérico, ampliar archivos/carpetas y verificar refresco del directorio. No asumir que el único fallo es la notificación de cambios. Esta build mantiene ese trabajo separado.

Compilación completada. Los 45 objetos base del servidor se verificaron por hash antes de recombinar; el conjunto de símbolos globales del objeto final coincide con el original. En runtime sólo cambia wfm.exe. Fuentes, manifiestos y objeto de servidor derivado documentados en release-w109 y build-report.json. PKG SHA-256: 9968f1da041b182e5f541bf195204b4fd72148d2cda241a20e913000138fce45. ELF SHA-256: 0fcb12e585fb123ee46c172768559d6d2134dffd824ce8fdd1720745bd9c131c.

Entrega completada con lectura de vuelta verificada: `/data/pkg/orbis-win-W109-9968f1da041b.pkg`. Informe: reports/wine-hardware-w109/transfers/20261102T172053Z.json. 548 archivos verificados, 545 presentes y 3 subidos; sin fallos de permisos. W108 retirado después de verificar. Prueba física pendiente del usuario.
