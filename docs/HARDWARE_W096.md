<a id="w096-mangohud-compartido-entre-invitados"></a>


# W096: MangoHud shared among guests

[English](HARDWARE_W096.md) | [Español](HARDWARE_W096-es.md)

User-indicated priority: to correct instability by combining graphic applications before the CPU/GPU percentages, deliver by FTP and validate directly in PS4. The local matrix is omitted.

<a id="reproducción-de-origen"></a>


## Reproduction of origin

Evidence W095: `reports/wine-hardware-w095/physical/20261102T102045Z/`. When running one-on-one applications, vkcube comes out with 0. When combined, there are statements of ImGui and invalid accesses; `analysis.md` details the sessions.

Guests share process and DLL. MangoHud conserves current contexts of ImGui/ImPlot, HUDElements and other data as a global state. The above mutex protected only the object map Vulkan, not the life cycle of the IU.

<a id="cambio"></a>


## Change

`tools/vk-h0/patch-mangohud-shared-process.py` modifies the compilation copy in WSL, keeping the upstream review intact:

- The same recursive mutex covers instance creation / destruction, device and swapchain, and preparation of overlay for QueuePresentKHR.
- Release that mutex by calling the driver presentation, after recording and sending the HUD commands. Other applications can prepare your overlay during copia/presentaci on by GDI/VideoOut.
- Save the previous context before CreateContext, which changes the global context. It destroys sources and contexts with the correct swapchain selected, without restoring a context that just destroyed.
- It keeps the real assertions and errors. It does not disable MangoHud or prevent several applications from being opened.

The compilation script now spreads a ninja failure. I used to continue after the failure and could leave an earlier DLL as an apparent result. The package manifesto records hashes from the modified DLL source and scripts.

The linked objects of Wine he used W095 are reused. **It does not run prepare-wine-boot.py nor does it incorporate its pending change of times CPU**. W096 designates this correction of overlay; the change of telemetry is left for a later iteration. Percentages CPU/GPU remain unvalidated.

<a id="construcción-y-entrega"></a>


## Construction and delivery

In Ubuntu - 22.04 of WSL, from the workspace:

```sh
bash tools/vk-h0/build-mangohud.sh
python3 tools/build-wine-hardware.py
python3 tools/upload-hardware.py --build W096 --host 192.168.68.104
```

APP_VER 01.95, title ORBW00002. The W095 artifacts remain in their directories. The new exits are in `build/wine-hardware-w096`, `out/wine-hardware-w096` and `reports/wine-hardware-w096`.

Transfer completed to `192.168.68.104:2121`, with verified return reading:

- PKG: `/data/pkg/orbis-win-W096-8912ee9f3df1.pkg`, 31457280 bytes.
- SHA- 256: `8912ee9f3df154bdfa04c02815a73d6d6cef6ceca97d39c10835f71c743bd814`.
- Runtime: 548 files; 545 already present, 3 uploads (DLL and records that had changed on the console); no permit failure.
- Evidence: `reports/wine-hardware-w096/transfers/20261102T103439Z.json`.
- Manual installation and physical execution pending.

<a id="prueba-física-pendiente"></a>


## Physical evidence pending

Close OrbisDesk before installing. First open glxgears and then vkspin without closing the first. Then open vkcube; move the windows and close them in different order. Check that ambas/todas continue to draw, that MangoHud does not open an assertion and that closing one does not break the remaining ones. It is not marked in hardware until you receive that result and recover the logs.

```sh
python3 tools/fetch-hardware.py --build W096 --host 192.168.68.104
```

The compilation and transfer do not replace such physical validation.

<a id="resultado-físico-recibido"></a>


## Physical result received

The user confirmed three simultaneous graphic applications without the error of W095. The logs recovered in `reports/wine-hardware-w096/physical/20261102T103537Z/` show closure of the three with 0 code and absence of the previous aserciones/accesos invalid. After closing them, Start stops opening even though it's still coming in. The reception of movements does not show that the shell thread is free. It is followed in [W097](HARDWARE_W097.md) with a diagnosis of this block; the complete cycle of open/close/reabrir. is not marked
