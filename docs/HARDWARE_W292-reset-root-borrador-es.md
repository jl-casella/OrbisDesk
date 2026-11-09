# W292: "Reset as Root" y "Reset as Sandbox" en el menú Start (borrador)

[English](HARDWARE_W292-reset-root-borrador.md) | [Español](HARDWARE_W292-reset-root-borrador-es.md)

Borrador para unir a las notas de W292. Nada de esto se probó en la consola.

## Pedido

Usuario:
- Start tiene siempre un ítem entre "Open Steam Client" y "Exit desktop", según el modo actual:
  - en NORMAL, "Reset as Root" reinicia en ROOT;
  - en ROOT, "Reset as Sandbox" reinicia en NORMAL;
  - cada uno tiene su propio ícono;
- el reinicio saltea la pantalla NORMAL/ROOT, o dice claro por qué no puede.

## Cómo funciona

- **Modo:**
  - el launcher (`native/wine_hardware.c`) guarda en `boot_root` el modo elegido al arrancar. Sale del selector, de `boot-mode.txt` en el relanzamiento por un programa, o de un reinicio;
  - explorer corre como invitado en el mismo proceso, así que le pregunta directo al lado nativo, por el canal que ya usa `C:\orbis\steam-open.exe`: la biblioteca Unix de xinput1_3, llamada 3, cuyo nombre de 260 bytes `native/hw_pad.c` lee como pedido y responde en el lugar;
  - `<root-mode>` responde `root` o `normal`. No hace falta una variable de entorno nueva.
- **Relanzamiento:** `pw_hw_reset_mode(root)` escribe `/data/orbisdesk/force-mode.txt` (`root` o `normal`), deja el jailbreak y relanza el título con `sceSystemServiceLoadExec("/app0/eboot.bin")`. Un programa abierto desde el escritorio hace lo mismo (W043, `pw_hw_switch_program`).
  - En el arranque siguiente, `boot_choose()` lee y borra ese archivo primero. Toma ese modo sin selector, escribe `boot-mode.txt` como lo haría el selector, y deja `PWJB mode=root|normal source=reset` en el log. En ROOT después sigue el jailbreak de siempre.
  - El archivo se usa una sola vez: un arranque manual posterior vuelve a mostrar el selector.
- **Los errores se muestran, no se esconden:**
  - si no se puede escribir el archivo, si se rechaza el relanzamiento o si el sistema no cierra el título en 10 s, el pedido responde `error: …`. El archivo se borra, ROOT recupera el jailbreak, y explorer muestra la respuesta en un cuadro de mensaje;
  - se rechaza pedir el modo que ya está corriendo, o pedirlo desde la corrida de un programa;
  - si el lado nativo no responde `<root-mode>`, el ítem no se agrega, y el log lo dice.

## Cambio

1. `reset-root-native.patch.py` (carpeta de notas) → `native/wine_hardware.c` y `native/hw_pad.c`:
   - `pw_hw_boot_root`, `pw_hw_reset_mode` y la lectura del modo forzado en `boot_choose`;
   - los pedidos `<root-mode>`, `<reset-root>` y `<reset-sandbox>`. `hw_pad.c` los referencia como débiles, así que un build sin ellos responde `error: unavailable`.
2. `reset-root-explorer.patch.py` → `tools/build-explorer-hw.py` (4 revisiones en `startmenu.c`):
   - `MENU_ID_ROOT` y la llamada nativa, que pregunta el modo una vez;
   - el ítem entre Steam y Exit, con el texto del modo actual;
   - dos glifos, dibujados como los de Run, Steam y Exit: una flecha de reinicio ámbar para Root, y un escudo verde con una barra blanca para Sandbox.
   - Al elegirlo pregunta antes, con No por defecto, porque los programas abiertos se cierran sin guardar. Llama a `RegFlushKey` en HKCU y HKLM, para no perder ajustes recientes como la elección de fondo por el guardado cada 30 s del wineserver, y después manda el pedido.
3. Log: `PWROOT explorer mode=…`, `PWROOT explorer reset to=… flush …`, `PWROOT request reset to=…`, `PWROOT reset to=… relaunch` / `load_exec rc=…` / `still_running`, `PWROOT force_mode=… removed=0`, `PWJB mode=… source=reset`.

## Construcción

1. Aplicar `reset-root-native.patch.py .` (raíz del repositorio) y `reset-root-explorer.patch.py tools/build-explorer-hw.py`.
2. Correr `build-explorer-hw.py`, y después `build-wine-hardware.py`, que compila `wine_hardware.c` y `hw_pad.c` en el ELF.

Prueba en copia:
- explorer, con los parches de columnas, fondos y Reset aplicados sobre el builder con sha `b4647688…`: 79 revisiones, y `desktop.c` y `startmenu.c` compilan sin advertencias;
- `wine_hardware.c` y `hw_pad.c` (shas del árbol de trabajo `c6435309…` y `d6f6bff6…`), parcheados: los dos compilan sin advertencias con los flags auxiliares del ELF de arranque.

## Prueba física

1. Arrancar en NORMAL. Start muestra "Reset as Root" entre "Open Steam Client" y "Exit desktop", con una flecha ámbar. Log: `PWROOT explorer mode=0 reply="normal"`.
2. Elegirlo, y después No: no pasa nada.
3. Elegirlo, y después Yes. El título se cierra y arranca de nuevo, sin la pantalla NORMAL/ROOT, directo a la barra de carga. Log de la corrida nueva: `PWROOT force_mode=root`, `PWJB mode=root source=reset`, y después `PWJB jailbreak rc=0 …`.
4. En esa corrida en ROOT, Start muestra "Reset as Sandbox" en el mismo lugar, con un escudo verde, y los discos USB aparecen como D: y letras siguientes.
5. Elegir "Reset as Sandbox", y después Yes. El título arranca de nuevo en NORMAL sin la pantalla. Log: `PWJB mode=normal source=reset`, y ninguna línea del jailbreak.
6. Cerrar OrbisDesk y abrirlo de nuevo. Vuelve la pantalla NORMAL/ROOT, porque cada reinicio se usa una vez.

## No verificado

- Nada se probó en la consola.
- Que `sceSystemServiceLoadExec` del propio título funcione desde la corrida del escritorio sin un programa pendiente. Es la llamada que ya hacen los cambios de programa, pero siempre con `next.txt` presente.
- Si `RegFlushKey` hace que este wineserver guarde el registro en el momento. Su resultado sólo queda en el log.
- Los programas abiertos en ese momento se cierran sin guardar, como en cualquier cambio de programa.
