<a id="w102-mangohud-reactivado-con-muestreo-en-el-frame"></a>


# W102: MangoHud reactivated with frame sampling

[English](HARDWARE_W102.md) | [Español](HARDWARE_W102-es.md)

The control W101 completed two cycles of the three applications, six outputs 0 and final output 0 in the PS4. It was confirmed that MangoHud was not loaded. Evidence: `reports/wine-hardware-w101/physical/20261102T125705Z/analysis.md`. This links the research to the path activated by the layer; does not test a single cause or turn it off in the final solution.

<a id="cambio-de-ciclo-de-vida"></a>


## Life cycle change

`tools/vk-h0/patch-mangohud-frame-sampling.py` modifies the compilation copy after the patches W096/W099:

- hw_info_updater stop creating a thread and retain parameters from an instance. It runs update_hw_info during the frame sampling, under the block of IU.
- fpsMetrics calculates in update_thread synchronically and protects the reset with its mutex, without worker, output condition or active waiting.
- start_notifier stop launching the file observer. No live recharge; the configuration indicates to save and restart OrbisDesk to apply it.
- PWHUD informa sampling=frame, fps_metrics=frame y config_watcher=disabled.
- It is reactivated ImplicitLayers DWORD 0; The manifesto and the pitcher marker record MangoHud enabled. The build register includes new sources and the packer checks your hashes and markers against the compiled DLL.

The port maintains its previous policies of guest threads. This adaptation avoids these persistent services of MangoHud on the proven route, without introducing a process simulation or a private ownership protocol in Win32. F2/logging, uploads and other optional services are not validated by this test. It is not yet declared that the crash is resolved.

The existing calls and calculations of statistics are retained; can change the coste/tiempo of the frame by sampling. The percentages CPU/GPU. have not been corrected or validated. These providers are still postponed. Wine Unix, DLL PE of Wine, heap W100 and driver are preserved. No local matrix is run.

<a id="construcción-y-prueba"></a>


## Construction and testing

APP_VER 02.01, title ORBW00002. The builder is back to default enabled; the reproducible command expressly indicates this:

```sh
bash tools/vk-h0/build-mangohud.sh
python3 tools/build-wine-hardware.py --mangohud enabled
python3 tools/upload-hardware.py --build W102 --host 192.168.68.104 --timeout 60
```

Close OrbisDesk before installing. Confirm the overlay visually and repeat two cycles of open/close glxgears, vkcube and vkspin and return to Start; close vkcube first. Notify with "I tried it." Check the actual load of MangoHud, frame policy, guest exits, reopenings and Start response on the loops. If there is only freezing, leave 15 seconds; if there is crash, indicate code.

```sh
python3 tools/fetch-hardware.py --build W102 --host 192.168.68.104
```

Delivery completed and verified: `/data/pkg/orbis-win-W102-09be7a07d5eb.pkg`, SHA- 256 `09be7a07d5eb38aa1b348d0821c949edefb5fd821f18c9fabca0cac0dbbed42c`. Report: `reports/wine-hardware-w102/transfers/20261102T130927Z.json`. 548 verified files, 544 present and 4 uploaded; no permit failure. W101 was removed after verification; local evidence and packages preserved. Physical test of W102 pending.

<a id="resultado-físico"></a>


## Physical result

Tested in PS4: two cycles with MangoHud loaded, six openings and six closures with 0 code, operational start and final output 0 at 63455 ms. PROCESS_ATTACH, non-null handles hud and frame policy were verified in the logs. No previous invalid access or crash was recorded at this session.

Evidence: `reports/wine-hardware-w102/physical/20261102T131731Z/`, with analysis.md and acceptance.json. Acceptance limited to this scenario; does not value long sessions, optional login functions or percentages CPU/GPU.
