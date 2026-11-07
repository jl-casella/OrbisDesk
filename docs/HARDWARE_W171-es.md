# W171: estado de la página en el fallo del heap (fase 6)

[English](HARDWARE_W171.md) | [Español](HARDWARE_W171-es.md)

APP_VER 02.70. Base W170. El resultado de W170 está en `docs/HARDWARE_W170.md`.

## Cambio

`tools/build-audio-ps4.py`, `virtual.c` de ntdll, `virtual_handle_fault`:
- Cuando falla un acceso a una página que Wine tiene accesible, `PWVM fault` agrega lo que el kernel dice de la página antes y después de volver a aplicar la protección: rango, protección, tipo y flags de `sceKernelVirtualQuery` (bit 4: comprometida).
- Si volver a aplicar la protección devolvió 0, la instrucción se ejecuta una vez más. Si la página sigue fallando, el segundo fallo llega al programa como antes y queda registrado con `retry=0`.

## Qué se espera

- Que el log diga si la página estaba comprometida y con qué protección, para corregir `pw_wine_memory_protect` o el mapeo de Wine.
- Si el reintento basta, SuperMarioKart sigue después de la carrera, y el log muestra `retry=1` sin un segundo fallo en esa página.

La fase 7 (DXVK de 32 bits y winecfg) de la sesión de accesos directos pasa a W172.

## Prueba física

Reporte: `reports/wine-hardware-w171/physical/20261103T190203Z/`. Respuesta del usuario: "Se cerró al salir". Salida `status=0x00000000`.

```
PWVM fault addr=0x1f66000c err=1 vprot=0x23 view=0x1f660000 size=0x2f0000 protect=0x3 reprotect=0 errno=0
  before=0x8002000d 0-0 prot=0 type=0 flags=0 after=0x8002000d 0-0 prot=0 type=0 flags=0 retry=1
(segundo fallo en la misma página, retry=0)
```

- `sceKernelVirtualQuery` falla con `0x8002000d` (EACCES) antes y después: el kernel no reporta la página, aunque Wine la tiene comprometida y `mprotect` devuelve 0. El reintento falla igual.
- `pw_wine_memory_protect` (`platform/ps4/pw_wine_platform.c`) compromete con memoria flexible sólo las páginas que la consulta reporta como no comprometidas. Si la consulta falla, no hace nada y devuelve 0.
- Las páginas así salen del `anon_mmap_fixed` con `PROT_NONE` de Wine, es decir del `mmap` de libc: el decommit, y la liberación dentro de un área reservada. Es una inferencia del código; no está medida.
- La subida de W171 usó por primera vez la fusión de `user.reg` de la fase 7: `source=merged`, un bloque AppDefaults conservado, y el archivo subido es igual al de la build.
