# W108: renombrar carpetas y borrar árboles desde WFM

[English](HARDWARE_W108.md) | [Español](HARDWARE_W108-es.md)

APP_VER 02.07. W107 abrió dos veces Desktop/test.txt con Notepad desde Explorer y cerró ambos invitados con 0. El usuario informa que crear/borrar funciona, pero no renombrar carpetas ni borrar carpetas con subcarpetas. Logs: reports/wine-hardware-w107/physical/20261102T164857Z.

## Cambios

pw_wine_rename rechazaba expresamente directorios con ENOTSUP. Ahora resuelve origen y padre del destino, comprueba las longitudes de las rutas guardadas y llama a rename real. Tras éxito actualiza los registros de descriptores y los cwd de ambos lados, incluyendo descendientes y límites de componente. Una operación fallida no cambia esos registros. Conserva el rechazo de raíces de montaje. PWFS registra ruta, retorno y errno. El builder compila el adaptador y sustituye exactamente un pw_wine_fs.o del enlace guardado, sin modificar los objetos base de la evidencia anterior.

WFM informa errores de MoveFileW al renombrar. El borrado usa APIs Win32 reales: enumera hijos, cierra el handle de búsqueda y después elimina recursivamente archivos/subcarpetas y el directorio final. No sigue reparse points, no omite nombres por empezar con punto, rechaza raíces de unidad, comprueba longitudes, atiende cancelación y conserva el primer error. Una eliminación parcial no se anuncia como éxito. El usuario mantiene la confirmación de borrado previa. PWFM registra los resultados; el diálogo muestra el fallo real.

Esto sustituye la ruta silenciosa SHFileOperation de borrado. El fallo exacto de esa ruta anterior no quedó identificado por los logs; no se presenta como una capacidad ya validada en hardware.

## Construcción y comprobación

```sh
python3 tools/build-wfm.py
python3 tools/build-wine-hardware.py --mangohud enabled
python3 tools/upload-hardware.py --build W108 --host 192.168.68.104 --timeout 60
```

Sin matriz local. Una comprobación puntual del adaptador en filesystem Linux pasó: renombrar a nombre más largo/corto con un directorio abierto, continuar openat/fchdir, corregir cwd y preservar rutas ante fallo. Evidencia: build/w108-rename-check.c y build/w108-rename-check-linux.log. La primera ejecución en DrvFS devolvió EACCES al mover un directorio abierto; su log se conserva. No se extrapola el resultado de Linux al kernel de PS4.

El diagnóstico fs-services cambia el caso histórico de rechazo por una ida y vuelta de rename. Los informes históricos de incrementos 14–18 se conservan y su expectativa de rechazo ya no es la expectativa actual.

En PS4, usar sólo una carpeta de prueba creada por el usuario: crear padre/hijo/ nieto y un archivo, renombrar padre, navegar el árbol y borrarlo tras confirmar. Probar nombre destino existente: debe fallar sin sobrescribir contenido. Revisar Start y abrir un TXT/EXE para comprobar las rutas previas. No borrar fixtures del runtime ni carpetas de sistema durante esta prueba.

```sh
python3 tools/fetch-hardware.py --build W108 --host 192.168.68.104
```

Pendiente separado: el desktop Wine actual sólo enumera *.lnk. Mostrar también archivos/carpetas será la siguiente mejora; no es una prohibición de filesystem.

Compilación completada, fuentes/manifiestos en release-w108. En el runtime sólo cambia wfm.exe frente a W107; el ELF incorpora el objeto FS nuevo b9f7f2666464ac2a9f28e15e209c190289f789f11fc932f1e10e768461e70ff6. PKG SHA-256: ec2dd685205f59c6e64c4a2b1b8f837a40670556cbd0cd2ae6df7f9715af1f02. ELF SHA-256: 8aac41f3eaf694178c8c0d0e544ade7924ba305d63afad207eaa7f0d68961e9a.

Entrega completada con lectura de vuelta verificada: `/data/pkg/orbis-win-W108-ec2dd685205f.pkg`. Informe: reports/wine-hardware-w108/transfers/20261102T170417Z.json. 548 archivos verificados, 545 presentes y 3 subidos; sin fallos de permisos. W107 retirado después de verificar. Prueba física pendiente del usuario.
