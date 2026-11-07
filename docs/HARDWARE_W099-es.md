# W099: cierre de MangoHud sin retener el bloqueo compartido

[English](HARDWARE_W099.md) | [Español](HARDWARE_W099-es.md)

W098 produjo CE-34878-0 al cerrar vkcube con glxgears y vkspin abiertos. Su log se corta durante DLL_THREAD_DETACH de user32 en un worker de la capa, antes de alcanzar ExitProcess del invitado. No dejó pila ni PC de excepción. Evidencia: `reports/wine-hardware-w098/physical/20261102T113949Z/analysis.md`.

## Cambio

`tools/vk-h0/patch-mangohud-teardown.py` trabaja sobre la copia de compilación, después del parche W096. Conserva la revisión upstream y artefactos anteriores.

- Libera orbis_overlay_mutex antes de esperar al observador y antes de las llamadas descendentes de destrucción de swapchain, dispositivo e instancia. Lo recupera para limpiar sus metadatos. Los contextos y dibujo del overlay continúan protegidos como en W096.
- Solicita salida al observador antes de destruir su instancia del driver.
- La espera usa el handle Win32 de std::thread de libc++/MinGW, comprobado con static_assert. MsgWaitForMultipleObjectsEx permite atender mensajes síncronos enviados durante DLL_THREAD_DETACH; PeekMessage restringe la atención a QS_SENDMESSAGE. No despacha clics/comandos en cola ni simula fin de hilo.
- El flag quit es atomic<bool>, eliminando la carrera lectura/escritura.
- `PWHUD` marca comienzo y retorno de destrucciones y join. Se añade warn+debugstr a las trazas temporales para capturar OutputDebugStringA.
- El empaquetador verifica el hash de la DLL y sus fuentes contra el registro generado sólo después del éxito de ninja.

Se conservan los objetos Unix y los módulos PE de Wine de W098; no se compilan los cambios pendientes de porcentajes CPU/GPU. Sin matriz local por indicación del usuario. APP_VER 01.98, título ORBW00002. La corrección de la dependencia de cierre está implementada; el crash físico no se da por resuelto antes de probar.

## Entrega y prueba

```sh
bash tools/vk-h0/build-mangohud.sh
python3 tools/build-wine-hardware.py
python3 tools/upload-hardware.py --build W099 --host 192.168.68.104
```

El uploader, por preferencia expresa del usuario, elimina los PKG Wine anteriores de /data/pkg únicamente después de verificar la nueva entrega completa. Restringe la eliminación a nombres orbisdesk-WNNN-<12 hex>.pkg con número inferior al nuevo; conserva logs, runtime, copias locales, otros paquetes y versiones nuevas. Registra cada eliminación y fallo. --keep-old-packages permite conservarlos y --skip-runtime no inicia esta limpieza.

Cerrar OrbisDesk antes de instalar. Abrir las tres aplicaciones y cerrar vkcube primero. Comprobar si las otras dos siguen girando, cerrarlas y abrir Start. Si todo responde, reabrir glxgears una vez. Si se congela, esperar 15 segundos; si se cierra con error, avisar con el código.

```sh
python3 tools/fetch-hardware.py --build W099 --host 192.168.68.104
```

Después de la entrega se ofrece el botón «Ya la probé» para recoger los logs cuando el usuario indique que terminó. La transferencia no acredita ejecución.

Entrega completada y verificada: `/data/pkg/orbis-win-W099-fc9220d21b18.pkg`, SHA-256 `fc9220d21b1893650f4d0c7590efc6e810560f6e11a03e783592aa3235f82046`. Informe: `reports/wine-hardware-w099/transfers/20261102T115824Z.json`. Runtime: 548 archivos, 545 presentes y 3 subidos, sin fallos de permisos. Después se borraron cuatro PKG anteriores (W095–W098), todos con respuesta FTP 250 y sin fallos. Se conservaron evidencias y paquetes locales. Instalación y validación física pendientes.

## Resultado físico recibido

W099 fue probado: las rutas PWHUD de cierre y join retornan, los invitados salen con 0 y se pueden reabrir glxgears y vkcube desde Start. Tras otro cierre, Start se bloquea con un acceso inválido dentro de malloc nativo. Los relojes y el observador siguen avanzando. Evidencia en `reports/wine-hardware-w099/physical/20261102T120118Z/`; se continúa con [W100](HARDWARE_W100-es.md), sin dar por resuelta la estabilidad de varios ciclos.
