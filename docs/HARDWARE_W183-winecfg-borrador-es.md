# W183, parte de winecfg: Aplicar un tema ya no se congela

[English](HARDWARE_W183-winecfg-borrador.md) | [Español](HARDWARE_W183-winecfg-borrador-es.md)

Borrador de la sesión de configuración de Wine. La sesión principal lo suma a `HARDWARE_W183.md`.

## Qué dijeron las marcas de W182

En `run-0001.log` (`reports/wine-hardware-w182/physical/20261103T230134Z`, líneas 1423–1442, hilo `0040`):

| Paso de Aplicar | ms |
|---|---|
| `settings` | 0 |
| `theme` (`ApplyTheme` 168, `refresh_sysparams` 15) | 216 |
| `shell_folders` | 11 |
| `sysparams` (`SPI_SETNONCLIENTMETRICS` 21, `SetSysColors` 124) | 145 |
| `refresh` | no termina |

- No hay ninguna línea `PWPAINT` ni `PWBCAST`. No hay un bucle de repintado ni un broadcast que se quede sin tiempo.
- Las 7 líneas `open_mountmgr failed` después de `sysparams` vienen de `read_shell_folder_link_targets`, el primer paso de `refresh`. Las mismas 7 salen dentro de `shell_folders`, que sí termina. Esas llamadas vuelven.
- Lo que sigue en `refresh` es `update_shell_folder_listview` (la lista de la propia página), `update_mime_types` (una clave del registro) y `update_window_pos`.

## La causa

- `update_window_pos` (`programs/winecfg/theme.c`) recorre **todas** las ventanas de primer nivel con `EnumWindows` y a cada una le hace `SetWindowPos(SWP_FRAMECHANGED)`, para que tome los bordes nuevos.
- En win32u (`NtUserSetWindowPos`, `dlls/win32u/window.c`), si la ventana es de otro hilo, el cambio se manda con `send_message`, **sin timeout**: winecfg espera a que ese hilo lea sus mensajes.
- En la consola, winecfg corre como invitado dentro del proceso de explorer, con los hilos de explorer y de los otros programas. Basta una ventana de primer nivel de un hilo que no lee mensajes para que Aplicar no vuelva nunca.
- No es un broadcast (por eso no hay `PWBCAST`), y el hilo de la interfaz de explorer sigue bien (`PWSHELL monitor heartbeat_age_ms=223`).

## Cambio

- `tools/build-winecfg-hw.py`, una revisión más en `theme.c`:
  - a las ventanas de **otros hilos** se les pasa `SWP_ASYNCWINDOWPOS`. win32u entonces manda el cambio con `SendNotifyMessage`, sin esperar, y el otro hilo lo aplica cuando lee sus mensajes;
  - las ventanas del propio hilo de winecfg siguen igual;
  - una marca nueva: `PWCFG window_pos windows=N other_threads=M ms=T`.
- Las marcas `PWCFG` de W182 quedan.
- Compilado aparte (copia del builder con salida en el scratchpad): 7 revisiones, sin advertencias.

## Prueba

1. winecfg → Integración de escritorio → elegir Luna → Aplicar. Repetir con Noir y con "(Sin tema)".
2. winecfg sigue respondiendo; en el log están `PWCFG apply step=refresh` y `PWCFG window_pos`.
3. Las ventanas abiertas (explorer, otros programas) toman los bordes nuevos.
