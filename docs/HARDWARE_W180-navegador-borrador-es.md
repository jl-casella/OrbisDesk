# W180: Unix side de crypt32 (fase 9, borrador)

[English](HARDWARE_W180-navegador-borrador.md) | [Español](HARDWARE_W180-navegador-borrador-es.md)

Borrador de la sesión lateral del navegador, para unir a `HARDWARE_W180.md`. Base W179. Nada de esto se probó en la consola.

## Qué pasó en W179

Reporte: `reports/wine-hardware-w179/physical/20261103T221219Z/`

- **bcrypt funcionó:** `xul.dll` ya carga sus imports.
- **El bloqueo siguiente es crypt32:**
  - `failed to load "/data/wine/lib/wine/x86_64-unix/crypt32.so": Dynamic loading not supported`
  - `Initialization of "crypt32.dll" failed`
  - xul se descarga y mshtml da `Failed to init Gecko`.
  - Pasa en `webview64` (`run-0001.log`, línea 2436 en adelante) y en Pale Moon (`run-0002.log`, línea 1946 en adelante), que muestra "Could not load XPCOM".
- **El fallo de acceso** (`handle_syscall_fault c0000005`, `ip=0x448636`, lectura de la dirección 8) es del propio crypt32. Cuando falla `DLL_PROCESS_ATTACH`, el cargador llama a `DLL_PROCESS_DETACH`, y ahí crypt32 hace la llamada Unix `process_detach` (índice 1) sin tabla.
- **netapi32:** `netapi32.so` tampoco carga, pero netapi32 revisa que tenga Unix side antes de cada llamada (`samba_init`) y contesta como equipo local. Esa línea del log no es un error.

## Cambio

| Archivo | Qué hace |
|---|---|
| `tools/build-unixlibs-ps4.py` | Biblioteca nueva `crypt32`: `dlls/crypt32/unixlib.c` sin cambios, con su receta del Makefile de Orbis, y `platform/ps4/pw_crypt32_unix.c` con la misma receta. Las tablas de Wine se renombran al compilar a `pw_crypt32_wine_unix_call_funcs` y `pw_crypt32_wine_unix_call_wow64_funcs`. |
| `platform/ps4/pw_crypt32_unix.c` (nuevo) | Las tablas que se registran (`pw_crypt32_unix_call_funcs`, `pw_crypt32_unix_call_wow64_funcs`). Llaman a las de Wine entrada por entrada y agregan trazas `PWCRYPT`. |
| `platform/ps4/pw_wine_unixlibs.c` | Entrada `crypt32.so`, con tabla x64 y tabla wow64 para programas de 32 bits. |

Comportamiento en la consola:

- **Sin GnuTLS:** el `config.h` de Orbis no define `SONAME_LIBGNUTLS`. Por eso `unixlib.c` usa las funciones sin GnuTLS de Wine: abrir, importar y exportar almacenes PFX y claves devuelve `STATUS_DLL_NOT_FOUND`. Cada vez queda la línea `PWCRYPT <x64|wow64> <función> unsupported: no GnuTLS on the console`.
  - Afecta a `PFXImportCertStore` y a la exportación PFX. Ni Gecko ni Pale Moon las usan para navegar.
- **Certificados raíz:** Wine los busca en rutas fijas (`/etc/ssl/certs/ca-certificates.crt`, `/etc/ssl/certs`, `/etc/pki/tls/certs/ca-bundle.crt` y otras), que la consola no tiene. La enumeración termina vacía, y la primera vez queda `PWCRYPT <vista> root_certs=none`. El almacén raíz de crypt32 conserva igual las raíces de Microsoft que trae `rootstore.c`.
  - **Pale Moon** valida TLS con su propio almacén NSS (`nssckbi.dll`), así que no necesita el del sistema.
  - **MSHTML** no tiene TLS en la consola (schannel no tiene Unix side), así que tampoco lo usaría.
  - No se buscó un almacén de certificados propio de la consola.

## Construcción (orden)

1. `python3 tools/build-unixlibs-ps4.py` → `build/unixlibs-ps4` (agrega `crypt32.o` al reporte)
2. `python3 tools/link-wine-boot.py`: enlaza todas las bibliotecas del reporte y compila `pw_wine_unixlibs.c`
3. los pasos del ELF del hardware que use la sesión principal
4. `python3 tools/build-wine-hardware.py`
5. `python3 -I tools/check-web-closure.py build/wine-hardware-w180/runtime`: tiene que terminar con 0. Revisa los imports de los PE, no los Unix sides.

`pw_crypt32_unix.c` sólo lo compila `build-unixlibs-ps4.py`: `link-wine-boot.py` compila una lista fija de archivos de `platform/ps4`.

## Verificación sin consola

Compilé sólo crypt32 con una copia de `build-unixlibs-ps4.py` que escribe en el scratchpad (WSL, `orbis-cc`):
- Las dos unidades compilan sin avisos.
- El objeto combinado define `pw_crypt32_unix_call_funcs` y `pw_crypt32_unix_call_wow64_funcs` como globales.
- Las rutinas Unix de archivos (`open`, `opendir`, `readdir`, `fstat`) quedan redirigidas a las de `platform/ps4` (`pw_wine_open`…), como en las otras bibliotecas.

No se enlazó el ELF.

## Prueba física

1. **WebView test (64-bit) y (32-bit):** se espera `local complete=yes`, `title "orbis-webtest"` y `es5 "es5-ok"`.
2. **Pale Moon:** abre la página local y después sitios reales (ver `HARDWARE_W177.md`).
3. **En el log:**
   - no tiene que aparecer `crypt32.so … Dynamic loading not supported`, `Initialization of "crypt32.dll" failed` ni `Failed to init Gecko`;
   - se espera `PWCRYPT x64 root_certs=none`, y `wow64` en el de 32 bits.

## No verificado

- Nada se probó en la consola.
- Puede haber otro bloqueo después de crypt32 (otro Unix side, memoria, hilos). Para encontrarlo, `check-web-closure.py` sólo cubre imports de PE.
