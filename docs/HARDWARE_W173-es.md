# W173: compromiso de páginas del heap, Mesa residente, DLL de winecfg (fases 6 y 7)

[English](HARDWARE_W173.md) | [Español](HARDWARE_W173-es.md)

APP_VER 02.72. Base W172. El resultado de W172 está en `docs/HARDWARE_W172.md`.

## Cambios

**1. `opengl32` y `libgallium_wgl` quedan cargados** (`tools/build-guest-hw.py`, descarga de invitados en kernelbase):
- Antes de liberar el módulo de un invitado, si esas dos DLL están cargadas, se fijan (`GET_MODULE_HANDLE_EX_FLAG_PIN`) y se registra `PWGUEST unload pinned`.
- El WGL de Mesa mantiene hilos propios dentro de `libgallium_wgl`. En W172, al descargar `d3d11test64.exe` se liberaron con él, y explorer falló dentro del módulo liberado.

**2. DLL de winecfg en `system32`** (`tools/build-wine-hardware.py`, bloque de programas de W043; lo hizo la sesión de accesos directos):
- La clausura de imports de los programas de Wine (`uxtheme.dll` y `msimg32.dll`) también va a `system32`.
- En W172 esas DLL sólo estaban en la carpeta builtin, y winecfg no abría (`c0000135`).

**3. Compromiso de páginas del heap** (`tools/build-audio-ps4.py`, `virtual.c`, `pw_commit_backing`):
- En W172 la carrera terminó igual: `PWVM fault addr=0x1f08000c … before=0x8002000d … retry=1`, y después el mismo fallo con `retry=0`.
- No hubo ningún `PWVM commit_backing`: al comprometer, la consulta de cada página había dado 0, así que el arreglo no actuó.
- Una consulta con flag 0 sobre una dirección que el kernel no conoce puede devolver la región siguiente. Desde W173 una página cuenta como respaldada sólo si la región reportada la contiene y está comprometida (bit 4 de flags).
- Una reserva que la contiene se deja a `pw_wine_memory_protect`. Cualquier otro caso se mapea con memoria flexible.
- Cada compromiso de 1 MiB o más registra `PWVM commit` con páginas, respaldadas, mapeadas, fallidas y la primera consulta.

**4. Red:** `platform/ps4/pw_wine_net.c` vuelve al original; W172 había salido con una versión en curso de la fase 8. La fase 8 pasa a W174 (borrador: `docs/HARDWARE_W174-red-borrador.md`).

## Qué se espera

- `d3d11test64.exe` sigue fallando en la cadena de intercambio, pero explorer no se cae al cerrarlo.
- winecfg abre. Después siguen los pasos 5 y 6 de la prueba de W172: el override por programa `dxgi=builtin` tiene que seguir al reabrir la app y después de la próxima subida.

## Prueba física

Reporte: `reports/wine-hardware-w173/physical/20261103T193724Z/`

- **`d3d11test64.exe`:** se abrió dos veces. Las dos fallan en la cadena de intercambio, como se esperaba (para el usuario, "se cerró").
  - Al descargarse: `PWGUEST unload pinned L"opengl32.dll"` y `L"libgallium_wgl.dll"`.
  - Explorer siguió funcionando y después abrió SuperMarioKart. El cambio 1 funciona.
- **winecfg:** abre. Faltan dos cosas, que van a la sesión de accesos directos:
  - **About:** según el usuario "se cierra". El invitado sale con status 0 y sin error en el log.
  - **Test sound:** no suena. Se abre el puerto de audio (`PWAUDIO open init=00000000 … failed=00000000`) y fallan `msacm32.drv` y `midimap.dll` (`c0000135`).
- **SuperMarioKart** (`20261103T193958Z`, "error como siempre, se cerró"):
  - `PWVM fault addr=0x1f66000c`, con la consulta fallida (`0x8002000d`) antes y después; el reintento falló igual.
  - Justo antes, `PWVM commit base=0x1f660000 size=0x2f0000`: la consulta había dado 0 con la región `0x1f660000-0x1f950000`, exactamente la vista.
  - El `flags` registrado (`0x6f6e6101`) está mal leído: los bits ocupan un byte y el nombre de la región empieza enseguida. El byte real es `0x01`, es decir memoria flexible, no comprometida. Por eso el arreglo dejó la página a `pw_wine_memory_protect`.
  - El bloque que falla es el último de una serie: hubo 2530 compromisos de 1 MiB o más, 2304 de ellos de `0x2F0000`, 7,3 GiB en total a lo largo de la carrera, con otros tantos `NtFreeVirtualMemory`. La memoria flexible libre al arrancar era de unos 400 MB.
- **Hipótesis para W174:** Wine devuelve memoria mapeando `PROT_NONE` encima con el `mmap` de libc, y eso no le devuelve la memoria flexible al kernel. El presupuesto se agota, y el compromiso del último bloque queda sin memoria detrás.
