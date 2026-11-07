<a id="w190-direct3d-11-de-64-bits-con-el-dxgi-de-dxvk-y-el-registro-guardado-a-tiempo"></a>


# W190: Direct3D 11 of 64 bit with the dxgi of DXVK and the record kept on time

[English](HARDWARE_W190.md) | [Español](HARDWARE_W190-es.md)

APP_VER 02.89. Base W189. The result of W189 is in `docs/HARDWARE_W189.md`.

<a id="cambios"></a>


## Changes

<a id="dxgi-de-dxvk-para-títulos-de-64-bits-que-corren-solos"></a>


### DXVK dxgi for 64 bit titles running alone

`tools/build-wine-hardware.py`:
- `system32\dxgi.dll` becomes DXVK (x64). The Wine building is left in `lib/wine/x86_64-windows`.
- It is added `HKCU\Software\Wine\AppDefaults\explorer.exe\DllOverrides` with `"dxgi"="builtin"`. Explorer and all your 64 bit guests share a process, and Wine takes the AppDefaults by the name of that process (`set_load_order_app_name`). So they continue to use the `dxgi` of Wine: the Khronos charger, MangoHud and Gecko.
- `AppDefaults\d3d11test64.exe` carries `"OrbisRunsAlone"="Y"`: the test reproduces the title and runs alone.
- Pale Moon, which also runs alone, now load the `dxgi` of DXVK. Its `DllOverrides` block of the console is kept whole on the rise, so it could not be added an exception.

<a id="registro-guardado-al-aplicar-sesión-de-accesos-directos"></a>


### Record saved when applying (session of direct access)

The detail is in `docs/HARDWARE_W190-winecfg-borrador.md`:
- **The problem:** the server kept the record every 30 s and never when it came out, because the title is killed.
- **The change:**
  - `server/registry.c`: saved every 5 s, and `RegFlushKey` writes to disk (`tools/build-wine-delete-server.py`);
  - Apply winecfg ends with `RegFlushKey(HKEY_CURRENT_USER)`.

<a id="prueba-física"></a>


## Physical test

Report: `reports/wine-hardware-w190/physical/20261104T033417Z/`. User response: "2. Okay, 1, okay, 3. Okay. "

- **d3d11test64:**
  - `run-0002` relays (`switch_program image=C:\orbis\d3d11test64.exe`).
  - `run-0003` runs the test as a title: load `system32\dxgi.dll` as native, and DXVK creates the presentation chain (`Presenter: Actual swapchain properties`).
  - Tables (`frame_presented n=1920` at 12,7 s) are presented. It comes out with a state 0 (`process_exit … status=0x00000000`) and returns to the desk (`return_to_desktop`).
  - It is the first program of 64 bits with Direct3D 11 that works.
- **Subject:** Noir continues to reopen the app, although it was closed immediately after Accept.
- **Pale Moon:** is retracted (`run-0004` → `run-0005` and the user confirms that he sails with the `dxgi` of DXVK.

<a id="límites"></a>


## Limits

- A 64 bit program with Direct3D 11 works only if it runs alone (`OrbisRunsAlone`). As a guest within the explorer it continues with the `dxgi` of Wine, and the presentation chain fails.
- For now you have to dial every program by hand in the register. No automatic detection.
- The performance of d3d11test64 was not measured.
