# W216: el último hilo de un invitado terminado sale sin DLL_THREAD_DETACH (borrador)

[English](HARDWARE_W216-invitado-terminado-borrador.md) | [Español](HARDWARE_W216-invitado-terminado-borrador-es.md)

Borrador de la sesión de configuración de Wine, para unir a `HARDWARE_W216.md`. Nada de esto se probó en la consola.

## Qué pasó en W214

Reporte: `reports/wine-hardware-w214/physical/20261104T173546Z/run-0002.log`, desde la línea 4807.

- **El fallo:** `C:\orbis\glxgears.exe` (OpenGL por Zink) con MangoHud falló en `libMangoHud.dll+fa984`, dentro de `vkCreateSwapchainKHR`. Los símbolos del DLL desplegado dan esta cadena:
  - `overlay_CreateSwapchainKHR`;
  - `check_fonts` y `create_fonts`;
  - `ImFontAtlas::Build`;
  - `ImFont::GrowIndex`.
- **Por qué:** `ImGui::MemAlloc` pidió unos 249 KB, recibió NULL y `GrowIndex` escribió en la dirección 0 (r9=c0000017, `STATUS_NO_MEMORY`).
  - Pale Moon seguía abierto y trabado con YouTube.
  - La memoria flexible de todo el título es de unos 400 MB, y el crecimiento chico del heap sale de ahí.
  - El usuario dice que glxgears nunca se cayó sin Pale Moon abierto.
  - El log no registra qué llamada del kernel falló.
- **La red de W208 funcionó:**
  - `0x011c` es el hilo del invitado;
  - sus otros 3 hilos terminaron (`other_threads_wait=0`);
  - se destruyó su ventana y se descargó el módulo.
- **El título se cayó igual:** la última línea es `unload_own` (`count=0`). Después sólo corren `ps4_guest_live_remove` y `RtlExitUserThread`, y el log se corta: no hay latido `PWSHELL`, ni cuadros, ni `process_exit`.
- **La diferencia con W208:** la salida por fallo de Pale Moon en W208 siguió el mismo camino y el título siguió andando.
  - `RtlExitUserThread` llama a `LdrShutdownThread`, que manda `DLL_THREAD_DETACH` a cada DLL: OPENGL32, libgallium_wgl, libMangoHud, vulkan-1 y winevulkan.
  - Aquí lo hacía sobre un hilo con el swapchain de GL y Vulkan a medio armar, y con los hilos de trabajo recién terminados.

## Cambio

`tools/build-guest-hw.py` (kernelbase `process.c`, `ps4_guest_exit_process`), con `guest-terminated-exit-w216.patch.py`:
- **Qué cambia:** si el invitado terminó por `TerminateProcess` o por un fallo (`guest->terminated`, W209), su último hilo sale con `NtTerminateThread`, sin `DLL_THREAD_DETACH`. Windows tampoco manda avisos a los DLL cuando se termina un proceso.
- **Qué no cambia:** la salida normal.
- **Traza:** `PWGUEST last thread of module … ends (terminated, no thread detach)` o `(exit)`.

## Construcción

1. `python3 tools/build-guest-hw.py`.
2. `tools/link-wine-boot.py`.
3. `tools/build-wine-hardware.py`.

## Prueba física

1. **Repetir W214:** abrir Pale Moon con una página pesada y después glxgears con MangoHud.
   - Si la memoria alcanza, glxgears anda.
   - Si vuelve a fallar, el log debe mostrar `PWGUEST unhandled exception`, luego `PWGUEST last thread … (terminated, no thread detach)`, y el escritorio debe seguir andando (latidos `PWSHELL`, cuadros).
2. **Si el título se cae antes de esa línea:** la causa no es el detach, y la línea marca hasta dónde llegó.

## No verificado

- Nada se probó en la consola.
- El parche se aplicó sobre copias. `build-guest-hw.py` compila con Python, y `process.c` pasa `-fsyntax-only` con el comando de `out/guest-hw/manifest.json`. Queda una advertencia que ya estaba antes (`wcstoul`). El builder no se corrió.
- Que el título se cayera en `DLL_THREAD_DETACH` sale del orden del código, no de una traza.
- La falta de memoria de fondo sigue igual: sólo se contiene.
