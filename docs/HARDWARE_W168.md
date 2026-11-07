<a id="w168-excepciones-de-32-bits-sin-perder-fs-sprites-sin-objetos-por-copia-y-acceso-directo-en-el-escritorio-fase-6"></a>


# W168: exceptions of 32 unlost bits FS, without objects by copy and direct access to the desktop (phase 6)

[English](HARDWARE_W168.md) | [Español](HARDWARE_W168-es.md)

APP_VER 02.67. Base W167.

<a id="1-cierre-de-supermariokart-fs-nulo-al-volver-de-una-excepción"></a>


## 1. SuperMarioKart closure: FS null on return from an exception

**Problem.** Almost all the games of SuperMarioKart since W153 end with `EXCEPTION_ACCESS_VIOLATION` and output `0xc000000d`:
- access fails in `0x7BF4C041` (ntdll of 32 bit, `RtlNtStatusToDosError`, instruction `mov %fs:0x18,%edx`), reading the address `0x18`;
- just before, the game (Blitz3D) launches and catches an exception of C + + (`e06d7363`) when changing the music.

The context of the exception has `fs=0000`, while the contexts taken during normal execution have `fs=0013` and `gs=001b`.

**Causa:**
- In FreeBSD, the kernel of PS4, all user thread runs with its user FS selector (`_ufssel`, `0x13`; The base puts it `sysarch` in the MSR.
- `wow64native` (`cpu.c`) weapon the contexts of 32 bits with `SegFs = fs32_sel`, and on the way back with `RESET_STATE` (`NtContinue`, when you resume after an exception) load `context->SegFs` at FS before setting the base.
- `fs32_sel` comes out of `fs32_selector`, which `unix.c` leaves in 0. A zero selector is not used to access memory in compatibility mode, and the next reading of the TEB fails.
- The normal entry to the 32 bit code does not load FS, and therefore only failed after an exception.

**Change.** `tools/build-wow64native-ps4.py` (`unix.c` adaptation): in Orbis, `fs32_selector` is the FS selector of the thread that initializes, read with `mov %fs`, which runs with the FS of the system. The log leaves `PWNATIVE fs32_selector=…`; is expected `0x13`.

It serves for any 32 bit program that resumes after an exception.

**Another failure, not solved.** In the long game of W167 there was also another invalid access, once only:
- in `heap_allocate_large` (ntdll of 32 bit, `heap.c:1015`), writing in `0x1F1A000C`, at the end of the race;
- The big block just booked wasn't mapped.

Still no known cause.

<a id="2-copias-con-color-key-objetos-reutilizados"></a>


## 2. Copies with key color: reused objects

W167 (`PW_VK_FALLBACK_TOP`) showed that each copy with key color of W165 creates and releases an image, two views and a framebuffer: ~ 7 images, ~ 14 views and ~ 98 framebuffers per frame.

`tools/build-wined3d-hw.py`, `texture_vk.c`:
- **Temporary image:** a single, growing up to the largest rectangle that came, with its view and a set of descriptors of its own pool (64 sets). The rectangle is copied in its corner and the shader reads only that part (`src.zw`).
- **Barrier:** before copying the following sprite, a barrier awaits the previous drawing to read the image (`SHADER_READ_ONLY` → `TRANSFER_DST`).
- **Destination:** view and framebuffer are reused as long as the command buffer and image are not changed. Inside a command buffer the image cannot be destroyed.
- **Log:** `PWCKEY source image n` when the image grows. `PWCKEY blit` (the first three and one in each 5.000) counts the created framebuffers.

<a id="3-accesos-directos-en-el-escritorio"></a>


## 3. Direct access to the desktop

Investigated and prepared by the side desk session.

<a id="por-qué-no-había-accesos-directos"></a>


### Why there were no direct access


There are two cases, and the two corrections are needed.

1. **The desktop does not receive what it scans paints.** The scout of Wine loads the `.lnk` of the Desktop folders (`FOLDERID_Desktop` and `FOLDERID_PublicDesktop`) as pitchers and draws them in the `WM_PAINT` of the desktop window (`desktop.c`: `initialize_launchers`, `draw_launchers`. We run with `/desktop=shell,1280x720`, so it's not the root desk and the pitchers do load (`NoDesktop` is not in the record). But in ps5drv the desktop window has no surface (W045: the composer only arms the first-level windows on the bottom layer that loads the driver from `WINE_PS5_WALLPAPER`. What you explore paints on your desktop, background and icons, never gets to the screen.
2. **Desktop folders are empty.** In the prefixes of W126 a W167, `C:\users\orbis\Desktop`, `C:\users\jose\Desktop` and `C:\users\Public\Desktop` they exist but have no `.lnk`. `tools/build-wine-hardware.py` copy the accesses of `tools/make-start-menu.py` only to the Start menu.

The records of W166 do not show errors of this part (`Could not get user desktop folder` does not appear); The bottom is loaded by the driver (`PWBOOT wallpaper_loaded 1280x720 bpp=24`).

<a id="cambio"></a>


### Change

`tools/build-explorer-hw.py`, over `desktop.c`:
- the pitchers move to a first level (`OrbisDesktopIcons`) own window, with the size of the icon grid from the upper left corner;
- paint the bottom with `PaintDesktop` and above the icons with `draw_launchers` of Wine;
- double-click opens access with `ShellExecuteW`, just like the original code of Wine;
- it stays below everything (`HWND_BOTTOM`, also when reordering in `WM_WINDOWPOSCHANGING`), does not take the activation (`WS_EX_NOACTIVATE`, `MA_NOACTIVATE`) and is `WS_EX_TOOLWINDOW`;
- if the contents of the Desktop folders change, the monitor of Wine the redimensione and the repainting; without launchers, it is hidden;
- a line `PWDESK launchers=… panel=… size=… per_row=… desktop=… public=…` when starting; if the class or window fails, `PWDESK class error=` or `PWDESK window error=`, and the pitchers remain in the desktop window as before.

`tools/build-wine-hardware.py`: copy the access to File Manager (the same `.lnk` from the Start menu, with its verified hash) to `C:\users\Public\Desktop`. The side session had set four (File Manager, Notepad, Command Prompt, Solitaire); the user asked only File Manager.

To build you have to run `tools/build-explorer-hw.py` before `tools/build-wine-hardware.py`.

Built in a separate copy, no warnings. Not tested on the console.

<a id="qué-se-espera"></a>


### What is expected

- `PWDESK launchers=1` with `panel` other than zero.
- An icon with its name up to the left, on the bottom, without a visible edge where the window ends.
- Double-click opens the program; the icon does not cover the open windows or appear in the task bar.

<a id="riesgos-y-límites"></a>


### Risks and limits

- If `ExtractIconExW` does not give a large icon for an access, Wine discard that pitcher without notice; The count of `PWDESK` shows it.
- `PaintDesktop` draw the focused and unscalated bitmap; The driver scale it to the screen. With `orbis-hills.bmp` (1280x720) and 1280x720 display match; with another size there would be a visible edge around the icons.
- If a program sends another window to `HWND_BOTTOM`, it's under the icons.
- The folder guard uses `ReadDirectoryChangesW`; if it does not work on the console, new accesses appear only when restart.
- One more layer in the composition, the size of the grid (an icon).

<a id="prueba-física"></a>


## Physical test

Pending.
