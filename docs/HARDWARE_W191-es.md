# W191: Direct3D 11 detectado al abrir y aleatoriedad del kernel

[English](HARDWARE_W191.md) | [Español](HARDWARE_W191-es.md)

APP_VER 02.90. Base W190. El resultado de W190 está en `docs/HARDWARE_W190.md`.

## Cambios

- **Detección de Direct3D 10/11** (`tools/build-guest-hw.py`, kernelbase): un programa de 64 bits que importa `d3d11.dll`, `dxgi.dll` o `d3d10*.dll` corre solo, sin marcarlo a mano. Cuenta tanto la importación directa como la diferida. Con `"OrbisRunsAlone"="N"` sigue como invitado. Entre los programas que trae la build, sólo `d3d11test64.exe` importa esas DLL.
- **Aleatoriedad** (`tools/build-telemetry-ps4.py`, ntdll `system.c`):
  - `get_random` primero usa `sysctl kern.arandom` (CTL_KERN 1, KERN_ARND 37), y si falla `/dev/urandom`.
  - Si las dos fallan, la consulta (`SystemInterruptInformation`, por la que pasan `RtlGenRandom` y `BCryptGenRandom`) devuelve `STATUS_UNSUCCESSFUL` con una línea `PWRANDOM unavailable`, en lugar de devolver el búfer sin cambiar.

## Prueba física

Reporte: `reports/wine-hardware-w191/physical/20261104T040443Z/`. Respuesta del usuario: "1. Ok, 2. Ok".

- **Detección:**
  - Una copia sin marcar de la prueba (`d3d11test64d3d11test64.exe`) da `PWGUEST runs_alone … reason=dxgi_import`, se relanza y DXVK crea la cadena de presentación.
  - El original sigue entrando por su marca de W190.
- **Aleatoriedad:** cada proceso registra `PWRANDOM source=kern.arandom` (seis corridas). `/dev/urandom` no hizo falta y no se sabe si el sandbox lo deja abrir.
- **Pale Moon:** abre `https://example.com`.

## Después

En W192 se saca la detección: el `dxgi` de Wine pasa a crear la cadena de presentación de un dispositivo DXVK con el `dxgi` de DXVK, así que Direct3D 11 debería andar dentro de explorer, sin relanzar.
