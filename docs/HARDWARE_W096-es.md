# W096: MangoHud compartido entre invitados

[English](HARDWARE_W096.md) | [Español](HARDWARE_W096-es.md)

Prioridad indicada por el usuario: corregir la inestabilidad al combinar aplicaciones gráficas antes de los porcentajes CPU/GPU, entregar por FTP y validar directamente en PS4. Se omite la matriz local.

## Reproducción de origen

Evidencia W095: `reports/wine-hardware-w095/physical/20261102T102045Z/`. Al ejecutar aplicaciones de una en una, vkcube sale con 0. Al combinarlas hay aserciones de ImGui y accesos inválidos; `analysis.md` detalla las sesiones.

Los invitados comparten proceso y DLL. MangoHud conserva contextos actuales de ImGui/ImPlot, HUDElements y otros datos como estado global. El mutex anterior protegía únicamente el mapa de objetos Vulkan, no el ciclo de vida de la UI.

## Cambio

`tools/vk-h0/patch-mangohud-shared-process.py` modifica la copia de compilación en WSL, conservando intacta la revisión upstream:

- Un mismo mutex recursivo cubre creación/destrucción de instancia, dispositivo y swapchain, y la preparación del overlay durante QueuePresentKHR.
- Libera ese mutex al llamar a la presentación del driver, después de grabar y enviar los comandos del HUD. Otras aplicaciones pueden preparar su overlay durante la copia/presentación por GDI/VideoOut.
- Guarda el contexto anterior antes de CreateContext, que cambia el contexto global. Destruye fuentes y contextos con la swapchain correcta seleccionada, sin restaurar un contexto que acaba de destruir.
- Mantiene las aserciones y los errores reales. No desactiva MangoHud ni impide que se abran varias aplicaciones.

El script de compilación ahora propaga un fallo de ninja. Antes continuaba después del fallo y podía dejar una DLL anterior como aparente resultado. El manifiesto del paquete registra hashes de la DLL, fuente modificada y scripts.

Se reutilizan los objetos enlazados de Wine que usaba W095. **No se ejecuta prepare-wine-boot.py ni se incorpora su cambio pendiente de tiempos CPU**. W096 designa esta corrección del overlay; el cambio de telemetría queda para una iteración posterior. Los porcentajes CPU/GPU continúan sin validar.

## Construcción y entrega

En Ubuntu-22.04 de WSL, desde el workspace:

```sh
bash tools/vk-h0/build-mangohud.sh
python3 tools/build-wine-hardware.py
python3 tools/upload-hardware.py --build W096 --host 192.168.68.104
```

APP_VER 01.95, título ORBW00002. Los artefactos de W095 permanecen en sus directorios. Las nuevas salidas están en `build/wine-hardware-w096`, `out/wine-hardware-w096` y `reports/wine-hardware-w096`.

Transferencia terminada a `192.168.68.104:2121`, con lectura de vuelta verificada:

- PKG: `/data/pkg/orbis-win-W096-8912ee9f3df1.pkg`, 31457280 bytes.
- SHA-256: `8912ee9f3df154bdfa04c02815a73d6d6cef6ceca97d39c10835f71c743bd814`.
- Runtime: 548 archivos; 545 ya presentes, 3 subidos (DLL y registros que habían cambiado en la consola); ningún fallo de permisos.
- Evidencia: `reports/wine-hardware-w096/transfers/20261102T103439Z.json`.
- Instalación manual y ejecución física pendientes.

## Prueba física pendiente

Cerrar OrbisDesk antes de instalar. Primero abrir glxgears y luego vkspin sin cerrar el primero. Después abrir vkcube; mover las ventanas y cerrarlas en distinto orden. Comprobar que ambas/todas siguen dibujando, que MangoHud no abre una aserción y que cerrar una no rompe las restantes. No se marca resuelto en hardware hasta recibir ese resultado y recuperar los logs.

```sh
python3 tools/fetch-hardware.py --build W096 --host 192.168.68.104
```

La compilación y la transferencia no sustituyen esa validación física.

## Resultado físico recibido

El usuario confirmó tres aplicaciones gráficas simultáneas sin el error de W095. Los logs recuperados en `reports/wine-hardware-w096/physical/20261102T103537Z/` muestran cierre de las tres con código 0 y ausencia de las aserciones/accesos inválidos anteriores. Después de cerrarlas, Start deja de abrir aunque sigue llegando entrada. La recepción de movimientos no demuestra que el hilo del shell esté libre. Se sigue en [W097](HARDWARE_W097-es.md) con diagnóstico de ese bloqueo; no se marca resuelto el ciclo completo de abrir/cerrar/reabrir.
