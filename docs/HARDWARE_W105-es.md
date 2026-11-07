# W105: unidades y archivos del administrador WFM

[English](HARDWARE_W105.md) | [Español](HARDWARE_W105-es.md)

APP_VER 02.04. El usuario informó Computer vacío, sin unidades ni archivos. La calibración independiente CPU/GPU se aplaza; se conservan las métricas W104.

## Cambios

GetLogicalDrives de Wine enumera normalmente los enlaces de DosDevices en el servidor. Nuestro título no inicia mountmgr y el directorio no contiene las unidades aunque el adaptador de filesystem ya resuelve C: y Z:. En modalidad WINE_PS4_GUESTS, kernelbase comprueba las 26 raíces DOS mediante GetFileAttributesW y anuncia sólo las que realmente existen como directorios. No crea unidades ficticias ni devuelve éxito para raíces inaccesibles. La ruta general de Wine se conserva fuera de esa modalidad. PWFS registra la máscara obtenida. Se compila volume.o junto a los parches de invitados previos.

WFM verifica el resultado de GetLogicalDriveStrings y de FindFirstFile antes de usar los datos. Lista archivos sin exigir FILE_ATTRIBUTE_ARCHIVE y filtra directorios mediante FILE_ATTRIBUTE_DIRECTORY. Registra PWFM con los errores reales de acceso, enumeración y cantidad de elementos. Sus fuentes MIT se parchean en una copia; checkout y atribución se conservan.

## Construcción y prueba física

```sh
python3 tools/build-wfm.py
python3 tools/build-guest-hw.py
python3 tools/build-wine-hardware.py --mangohud enabled
python3 tools/upload-hardware.py --build W105 --host 192.168.68.104 --timeout 60
```

Sin matriz local, según la preferencia vigente. En PS4: abrir File Manager, comprobar Computer, entrar en C: y C:\orbis, regresar, cerrar y reabrir WFM. Comprobar nombres reales de carpetas/archivos y Start después del cierre. Z: expone la raíz que ya montaba el adaptador, su contenido sigue sujeto a los permisos reales del título. No se modifican ni borran archivos al navegar.

Tras «Ya la probé», recoger logs y revisar PWFS/PWFM y salida del invitado:

```sh
python3 tools/fetch-hardware.py --build W105 --host 192.168.68.104
```

Un paquete compilado no acredita la corrección visual. Build, transferencia y resultado físico se registran por separado en reports/wine-hardware-w105.

Compilación completada. PKG SHA-256: cb9543e2725cd77a35e48f3c2645fedd847c24c8e6380ab46edeec4c7154c6dd. ELF SHA-256: d99dd240cdc8b7789890a23fd7f9f06d3113ecc0b58c62ddf62dba9ce039d43c. Fuentes y manifiestos archivados en release-w105. El builder de invitados recompila también ntdll y ucrtbase: sus secciones de código coinciden con W104, sólo difieren .buildid y .edata. Comparación en module-comparison.json.

Transferencia completada con lectura de vuelta verificada: `/data/pkg/orbis-win-W105-cb9543e2725c.pkg`. Informe: reports/wine-hardware-w105/transfers/20261102T143252Z.json. 548 archivos de runtime verificados, 539 presentes y 9 subidos; sin fallos de permisos. W104 retirado después de verificar; evidencia local conservada. Pendiente de instalar/ejecutar manualmente y comprobar el listado en consola.

## Resultado físico posterior

El usuario confirma unidades y archivos visibles. PWFS registra máscara 02000004 (C: y Z:). Sesión descargada 20261102T145327Z. Abrir result.txt y vkspin64.txt provoca switch_program con esos documentos, un nuevo arranque c000007b y regreso al escritorio. W106 aborda la apertura y conserva el listado. Análisis en reports/wine-hardware-w105/physical/20261102T145327Z/analysis.json.
