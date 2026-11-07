<a id="w098-carga-de-gráficos-después-de-cerrar-invitados"></a>


# W098: loading of graphics after closing guests

[English](HARDWARE_W098.md) | [Español](HARDWARE_W098-es.md)

W097 showed that Start receives the click, lists and presents its menu and returns when selecting an input. The posterior cut corresponds to a new load of glxgears. The waiting for auxiliary threads returned 0. The user-informed crash left no SEH exception or final title output in the log.

Evidence: `reports/wine-hardware-w097/physical/20261102T105238Z/analysis.md`.

W098 is a targeted diagnosis, not a declared correction:

- `trace+module,trace+seh,trace+loaddll` to observe carga/descarga and DLL initializations. It is temporary and can affect log performance and size.
- `PWGUEST load_begin/load_end` with the name of the EXE, result and memory estimate of the kernel before loading. These figures do not amount to the title's RSS.
- `PWGUEST unload_begin/unload_end` with result of FreeLibrary and presence of opengl32, libgallium_wgl and libMangoHud antes/despu is. The addresses are evidence of the found module, do not show that all your objects are valid.
- `PWSHELL clocks` adds past QPC time and the shared tick of Wine, to detect if the latter stops advancing during the problem.

The MangoHud arrangement of W096 and the Unix objects of Wine are maintained. Percentages CPU/GPU are still postponed. The local matrix is omitted by the user's indication. APP_VER 01.97, title ORBW00002.

Compile and transferred to 192.168.68.104 with verified back reading: `/data/pkg/orbis-win-W098-b46d085a7675.pkg`, SHA- 256 `b46d085a76759c0e85c741b6aa49708288834acb633094a18bcc9c358f561cf0`. Report: `reports/wine-hardware-w098/transfers/20261102T110952Z.json`. Runtime: 548 files, 539 present, 9 uploaded, No permission failures. Manual installation and physical testing pending.

<a id="reproducción-física"></a>


## Physical reproduction

Close OrbisDesk before installing. Open vkcube, glxgears and vkspin. Close them, go back to Start and open glxgears again. If you keep responding, repeat once. If it freezes without closing, wait 15 seconds; if you close it alone, notify and pass the error code of PS4 if you show it. There is no need to repeat many sessions.

```sh
python3 tools/build-explorer-hw.py
python3 tools/build-guest-hw.py
python3 tools/build-wine-hardware.py
python3 tools/upload-hardware.py --build W098 --host 192.168.68.104
python3 tools/fetch-hardware.py --build W098 --host 192.168.68.104
```

<a id="hipótesis-adicional-a-comprobar"></a>


## Additional assumptions to be checked

In `upstream/Crema/port/mesa/ac_ps4_drm.c`, `ac_drm_device_deinitialize` is an explicit no-op: the comment says the device lives throughout the process. That deserves to review resources held between app cycles within our only process. It does not demonstrate OOM or justify releasing the device without reviewing its references, queues, deferred buffers and other users. W098 does not change the driver; Their memory figures are preliminary evidence, not a complete measurement of resources GPU nor a definitive proof of this hypothesis.

<a id="resultado-físico"></a>


## Physical result

The user completed W098 and confirmed CE-34878-0 when closing vkcube with the other two open apps. Logs in `reports/wine-hardware-w098/physical/20261102T113949Z/`. The cut occurs during the departure of a worker and the cleaning of user32, before the ExitProcess of the guest; glxgears were not recharged in this reproduction. The watches QPC/tick were moving forward. It is continued in [W099](HARDWARE_W099.md).
