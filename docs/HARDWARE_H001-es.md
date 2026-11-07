# Primera prueba física: H001

[English](HARDWARE_H001.md) | [Español](HARDWARE_H001-es.md)

Destino indicado por el usuario: PS4 Pro Baikal, firmware 12.52, GoldHEN, FTP `192.168.68.107:2121`. El servidor respondió como GoldHEN FTP v2.2 y permitió acceso anónimo a `/data/pkg`. Esto verifica la conexión, no la compatibilidad del runtime en hardware.

El paquete **OrbisDesk Hardware Check H001**, Title ID `ORBW00001`, es una aplicación nativa OpenOrbis independiente de Wine. Se instala con Package Installer y se abre desde el menú de PS4. No se envía al BinLoader como payload.

La pantalla muestra los resultados de:

- apertura del log y lectura del encabezado de `/app0/sce_sys/param.sfo`;
- escritura, seek y lectura de un archivo propio en `/data/orbis-win/hw01`;
- mapping de memoria, llamadas de protección R/RW, conservación del dato y liberación;
- reserva bajo 4 GiB y liberación;
- hilo, mutex, join y aislamiento de una variable TLS nativa.

No prueba ejecución JIT, señales, GS de Wine ni un EXE de Windows. La prueba de protección comprueba las llamadas y la lectura; no provoca una escritura ilegal para comprobar recuperación de fallos en esta primera versión.

Al terminar permanece visible. El usuario puede enviar una captura por PSPlay y cerrar la aplicación desde el menú de PS4. Los logs incrementales `report-0001.jsonl`, etc. quedan en `/data/orbis-win/hw01/`, junto con los archivos de roundtrip y cuadros BMP. Se reserva un nuevo nombre por ejecución para no sobrescribir los informes previos. Cada etapa se registra antes de ejecutarla.

## Construcción y comprobación local

```sh
python3 tools/build-hardware-boot.py
python3 tools/run-hardware-boot.py
```

El builder usa el SDK existente; en WSL resuelve el empaquetado criptográfico con PkgTool de Windows y el runtime .NET instalado mediante roll-forward, sin instalar OpenSSL antiguo ni cambiar la configuración del sistema. `pkg_validate` comprueba el PKG. El smoke test ejecuta el ELF durante 15 segundos en el fork y conserva resultados y captura en `reports/hardware-h001/`.

El primer smoke test pasó sin stubs de importación. La prueba física queda **pendiente de ejecución y feedback**. Manifest del paquete en `out/hardware-h001/manifest.json`; los registros de transferencia incluyen el hash del archivo leído de vuelta por FTP.

## Entrega inicial

Se subió `/data/pkg/orbis-win-H001-a8997e445b54.pkg` (6.619.136 bytes) y se verificó mediante lectura de vuelta por FTP, SHA-256 `a8997e445b5441eb3528755200225f7129e74a3f81ad95f6629fe6efe7ffb069`. El eboot del paquete final coincide con el que pasó el smoke test. Transferencia registrada en `reports/hardware-h001/transfers/20261031T050227Z.json`. Instalación manual y ejecución física pendientes del usuario.

## Resultado físico H001 y actualización H001B

El usuario ejecutó H001 en su PS4 Pro y envió una foto. Se recuperaron también el log JSONL y el cuadro generado en la consola: evidencia en `reports/hardware-h001/physical/20261031T051043Z/`. Pasan pantalla, log, roundtrip en `/data`, protección R/RW, reserva baja y TLS/hilos. La lectura del SFO devuelve ENOENT (2). La revisión inicial del paquete y sus fuentes se conservan en `reports/hardware-h001/release-h001/`.

Los archivos se habían creado con modo 0600: FTP podía listarlos pero no descargarlos. Se cambió únicamente el modo de nuestros dos archivos de diagnóstico a 0644 mediante SITE CHMOD, y se pudieron recuperar sin alterar su contenido.

H001B prueba un archivo normal incluido en el paquete, `/app0/hardware-marker.txt`, con contenido verificable. Conserva la lectura original del SFO como observación opcional, sin convertir su ausencia en un resultado de lectura correcto. Además crea los logs y archivos de roundtrip en modo 0644 y aplica fchmod para permitir su recuperación por FTP.

Los constructores actuales generan H001B en `build/hardware-h001b` y `out/hardware-h001b`. `run-hardware-boot.py` usa H001B por defecto y permite `--build H001` para el binario anterior. El smoke test puntual de H001B pasó sin stubs de importación. No se ejecutó la suite completa de Wine.

Actualización: mismo Title ID `ORBW00001`, APP_VER 01.01, título **OrbisDesk Hardware Check H001B**. Subida con lectura de vuelta verificada a `/data/pkg/orbis-win-H001B-0d1e49cc1c38.pkg`. Transferencia en `reports/hardware-h001b/transfers/20261031T051457Z.json`. Hay que cerrar H001 antes de instalarla; la lectura del asset en hardware sigue pendiente de feedback.
