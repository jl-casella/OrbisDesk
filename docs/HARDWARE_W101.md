<a id="w101-comparación-de-cierre-sin-cargar-mangohud"></a>


# W101: non-load closing comparison MangoHud

[English](HARDWARE_W101.md) | [Español](HARDWARE_W101-es.md)

W100 did not remove the CE-34878-0. The three guests close with 0 and the log is cut later, in Start, without a new exception or PC. PWHEAP does confirm the activation of the lock. Evidence: `reports/wine-hardware-w100/physical/20261102T122841Z/`.

<a id="variable-de-comparación"></a>


## Comparison variable

The heap W100, the Unix objects of Wine, the PE DLL and MangoHud W099 are maintained. The entry HKLM Software\ Khronos\ Vulkan\ ImplicitLayers from MangoHud passes from DWORD 0 to DWORD 1 to prevent automatic loading by the loader Vulkan. The only different file of the runtime versus W100 is wine-prefix/system.reg. The launcher changes identification and records experiment mangohud_layer = disabled.

**It is not a declared correction or a permanent elimination of overlay.** It seeks to isolate the layer and its hilos/dependencias before another life cycle change. There will be no metrics of MangoHud during this test. The traces, including those of the inicio/fin loading and presence of graphic DLL are preserved.

It is necessary to check on hardware that hud = 0 and that there is PROCESS_ATTACH of libMangoHud. If charged equally, the comparison is not validated. A single correct cycle also does not show general compatibility or an exact cause.

<a id="construcción-y-entrega"></a>


## Construction and delivery

```sh
python3 tools/build-wine-hardware.py --mangohud disabled
python3 tools/upload-hardware.py --build W101 --host 192.168.68.104 --timeout 60
```

APP_VER 02.00, title ORBW00002. The builder accepts --mangohud enabled/disabled; in W101 the default value is disabled. Do not reuse this number for an enabled variant without archiving your artifacts and identifying a new iteration. The future return to overlay must be explicit in command and manifest.

Verified delivery: `/data/pkg/orbis-win-W101-c1c05a3fa350.pkg`, SHA- 256 `c1c05a3fa35053ccdfa67530e7897bd4690ff0c3da9b6e6e436653d112d67ded`. Report: `reports/wine-hardware-w101/transfers/20261102T124200Z.json`. 548 verified files, 546 present and 2 uploaded records. It was removed W100 from the no-fault console after verification. Evidence and local packages preserved; There was no local test matrix.

<a id="prueba-física-pendiente"></a>


## Physical evidence pending

Open the three applications and close them (vkcube first). Open Start and repeat once the cycle. Notify with "I've already tried it"; If you fail, indicate the code or leave 15 seconds when it only freezes. Logs are recovered by:

```sh
python3 tools/fetch-hardware.py --build W101 --host 192.168.68.104
```

Percentages CPU/GPU continue to be postponed until the closure is stabilized and the layer restored with its corrected life cycle.

<a id="resultado-físico"></a>


## Physical result

Proof: six starts and six closures 0 (two cycles), without MangoHud loaded and with Start operating. The session ends with an output 0 at 83829 ms. Logs in `reports/wine-hardware-w101/physical/20261102T125705Z/`. It is followed with [W102](HARDWARE_W102.md), reactivated layer with synchronous sampling, still unvalidated.
