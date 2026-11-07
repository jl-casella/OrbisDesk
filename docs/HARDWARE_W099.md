<a id="w099-cierre-de-mangohud-sin-retener-el-bloqueo-compartido"></a>


# W099: closure of MangoHud without retaining the shared lock

[English](HARDWARE_W099.md) | [Español](HARDWARE_W099-es.md)

W098 produced CE-34878-0 when vkcube was closed with glxgears and vkspin open. Your log is cut for DLL_THREAD_DETACH of user32 in a worker of the layer, before reaching ExitProcess of the guest. He left no special stack or PC. Evidence: `reports/wine-hardware-w098/physical/20261102T113949Z/analysis.md`.

<a id="cambio"></a>


## Change

`tools/vk-h0/patch-mangohud-teardown.py` works on the compilation copy, after the patch W096. Keep the upstream review and previous artifacts.

- Release orbis_overlay_mutex before waiting for the observer and before the descending calls for destruction of swapchain, device and instance. He gets it back to clean his metadata. The contexts and drawing of the overlay continue to be protected as in W096.
- He requests the observer to leave before destroying his instance of driver.
- The waiting uses the handle Win32 from std:: libc threat++/MinGW, with static_assert. MsgWaitForMultipleObjectsEx allows to attend to synchronous messages sent during DLL_THREAD_DETACH; PeekMessage restricts attention to QS_SENDMESSAGE. No dispatch clics/comandos in queue or yarn-end simulates.
- The cut flag is atomic <bool>, eliminating the race read/write.
- `PWHUD` mark start and return of destruction and joint. Warn + debugstr is added to the temporary traces to capture OutputDebugStringA.
- The packer verifies the hash of the DLL and its sources against the record generated only after ninja success.

Unix objects and PE modules of Wine of W098 are preserved; no outstanding changes of CPU/GPU. percentages are compiled without local matrix by user indication. APP_VER 01.98, title ORBW00002. The correction of the closing unit is implemented; The physical crash is not resolved before testing.

<a id="entrega-y-prueba"></a>


## Delivery and testing

```sh
bash tools/vk-h0/build-mangohud.sh
python3 tools/build-wine-hardware.py
python3 tools/upload-hardware.py --build W099 --host 192.168.68.104
```

The uploader, by the user's express preference, eliminates the previous PKG Wine of /data/pkg only after verifying the new full delivery. Restrict the removal to orbisdesk-WNNN- <12 hex> .pkg names with a number less than the new one; conserves logs, runtime, local copies, other packages and new versions. It records every elimination and failure. --keep-old-packages allows you to keep them and --skip-runtime does not start this cleaning.

Close OrbisDesk before installing. Open all three applications and close vkcube first. Check if the other two keep turning, closing and opening Start. If everything answers, reopen glxgears once. If frozen, wait 15 seconds; If it is closed with error, call the code.

```sh
python3 tools/fetch-hardware.py --build W099 --host 192.168.68.104
```

After delivery, the "Already Tested" button is offered to collect the logs when the user indicates that it was over. The transfer does not prove execution.

Delivery completed and verified: `/data/pkg/orbis-win-W099-fc9220d21b18.pkg`, SHA- 256 `fc9220d21b1893650f4d0c7590efc6e810560f6e11a03e783592aa3235f82046`. Report: `reports/wine-hardware-w099/transfers/20261102T115824Z.json`. Runtime: 548 files, 545 present and 3 uploaded, No permission failures. Then four previous PKG (W095 - W098) were deleted, all with FTP 250 response and no failure. Local evidence and packages were retained. Installation and physical validation pending.

<a id="resultado-físico-recibido"></a>


## Physical result received

W099 was tested: the PWHAD closing and joint routes return, the guests leave with 0 and you can reopen glxgears and vkcube from Start. After another closure, Start is blocked with invalid access inside native malloc. The watches and the observer are still moving forward. Evidence in `reports/wine-hardware-w099/physical/20261102T120118Z/`; is continued with [W100](HARDWARE_W100.md), without taking the stability of several cycles for granted.
