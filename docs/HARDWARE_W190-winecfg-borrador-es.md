# W190, parte de winecfg: el tema elegido se mantiene al reiniciar

[English](HARDWARE_W190-winecfg-borrador.md) | [Español](HARDWARE_W190-winecfg-borrador-es.md)

Borrador de la sesión de configuración de Wine. La sesión principal lo suma a `HARDWARE_W190.md`.

## Qué pasó en W189

- El usuario cambió el tema en winecfg, Aplicar y Aceptar funcionaron, pero al volver a abrir la app el tema era otra vez Luna.
- En el `user.reg` de la consola (`/data/wine-prefix/user.reg`, leído por FTP), `ThemeManager`, `Control Panel\Colors` y `WindowMetrics` tienen la marca de tiempo del 2026-11-03 22:56: la sesión en la que se eligió Luna. Ningún cambio posterior llegó al archivo.
- El registro sí se guarda en la consola: claves de la misma corrida (`Shell Folders`, 03:07:31) y del arranque siguiente (`Fonts`, 03:08:15) están en el archivo.
- En `run-0001.log` (`reports/wine-hardware-w189/physical/20261104T030929Z`), winecfg corre entre t≈205 s y t≈226 s (Aceptar). El log termina en t≈232 s: la app se cerró unos 7 s después.

## La causa

- El servidor de Wine (`server/registry.c`) escribe el registro a disco cada 30 s (`periodic_save`) y al apagarse (`flush_registry`).
- En la consola el título se mata; el servidor no se apaga. Lo que cambió en los últimos 30 s antes de cerrar la app se pierde. El tema se aplicó unos 7 s antes de cerrar.
- `RegFlushKey` no servía: en el servidor, `flush_key` no hacía nada.
- No es el arranque (nada vuelve a poner Luna; el valor por defecto de la build es sin estilo, W177) ni la subida (`upload-hardware.py` ya conserva `ThemeManager` y las otras claves del tema de la consola, W175).

## Cambio

- `tools/build-wine-delete-server.py`, una unidad más, `server/registry.c` (solo con `__ORBIS__`):
  - `flush_key` escribe a disco las ramas cambiadas (`flush_registry`), como `RegFlushKey` en Windows;
  - el guardado periódico pasa de 30 s a 5 s. `save_branch` escribe solo las ramas que cambiaron, así que `system.reg` (1,4 MB) se reescribe pocas veces.
- `tools/build-winecfg-hw.py`: Aplicar termina con `RegFlushKey(HKEY_CURRENT_USER)`. Aceptar pasa por Aplicar.
- Los dos builders corren: el servidor compila `registry.c` sin advertencias y enlaza 45 unidades; winecfg queda con 2 revisiones, sin advertencias.

## Prueba

1. winecfg → Integración de escritorio → elegir Noir → Aceptar. Cerrar la app enseguida (menos de 5 s).
2. Abrir la app: el tema sigue siendo Noir.
3. En el `user.reg` de la consola, la marca de tiempo de `ThemeManager` es la hora de Aceptar.
4. Repetir con "(Sin tema)" y con Luna.
