# W107: asociaciones de texto visibles para HKCR

[English](HARDWARE_W107.md) | [Español](HARDWARE_W107-es.md)

APP_VER 02.06. W106 abre EXE desde WFM correctamente, confirmado por el usuario y por PWOPEN en hilo 0024 (Explorer). vkspin64.exe, gui-window64.exe y gui-text64.exe se lanzaron como invitados; los dos textos intentados fallaron y el guard impidió reemplazar el título. Evidencia: reports/wine-hardware-w106/physical/20261102T151517Z/analysis.json.

La causa es la ubicación del registro: W106 puso las asociaciones en HKCU\Software\Classes, pero la revisión fijada de Wine abre HKCR directamente en \Registry\Machine\Software\Classes. No hay fusión con las clases de usuario en esta implementación. shell32 busca allí extensión, ProgID y comando.

W107 añade las asociaciones ausentes a system.reg (HKLM\Software\Classes), conservando las existentes como .ini -> inifile -> Notepad. El comando sigue siendo Notepad PE64 con el argumento entre comillas. No cambia WFM, Explorer, las DLL ni el mecanismo de invitados que ya abre EXE. No añade un editor ficticio ni trata el error como éxito. Se mantienen el guard contra reinicios y el error para EXE no compatibles como invitados concurrentes.

```sh
python3 tools/build-wine-hardware.py --mangohud enabled
python3 tools/upload-hardware.py --build W107 --host 192.168.68.104 --timeout 60
```

Cerrar OrbisDesk durante la transferencia y antes de instalar para que la sesión anterior no guarde registros antiguos sobre el runtime actualizado. Sin matriz local. En PS4, abrir dos .txt desde WFM (por ejemplo result.txt y text-progress.txt), comprobar que Notepad muestra su contenido y cerrarlo; comprobar WFM, un EXE PE64 y Start después. No guardar cambios en los fixtures.

```sh
python3 tools/fetch-hardware.py --build W107 --host 192.168.68.104
```

Validación: carga de notepad.exe desde Explorer con el documento correcto, apertura visual confirmada por el usuario y ausencia de switch_program para textos. Compilación, entrega y aceptación física son estados separados.

Compilación completada. La comparación con W106 confirma sólo system.reg y user.reg distintos en el runtime; WFM, Explorer y DLL coinciden por hash. Se verificaron .txt -> OrbisDesk.Text -> comando real de Notepad y la asociación preexistente .ini -> inifile. Matriz local omitida, prueba física pendiente. Fuentes/manifiesto en reports/wine-hardware-w107/release-w107. PKG SHA-256: df1d1deadc9a4d9401a7c11e2f41f055a0898e53290c2e951db8fdd694aa140d. ELF SHA-256: 02dc4e424d06e5c4ee5b84b5ea6c441b851e049822fb1849109c14657cde386e.

Entrega completada con lectura de vuelta verificada: `/data/pkg/orbis-win-W107-df1d1deadc9a.pkg`. Informe: reports/wine-hardware-w107/transfers/20261102T164351Z.json. 548 archivos verificados, 546 presentes y 2 subidos, sin fallos de permisos. W106 retirado después de verificar. Prueba física pendiente del usuario.
