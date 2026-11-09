# W290: the desktop follows Desktop folder changes, and desktop icons get a right-click menu (draft)

[English](HARDWARE_W290-escritorio-borrador.md) | [Español](HARDWARE_W290-escritorio-borrador-es.md)

Draft to merge into the W290 notes. Nothing here was tested on the console.

## Report

User, after W289: renaming, deleting or adding a shortcut in `C:\users\orbis\Desktop` from WFM changes nothing on the desktop until OrbisDesk restarts.

## Cause

- explorer reads the Desktop `.lnk` files once at start (`add_folder`). After that, its `watch_desktop_folders` thread waits on `ReadDirectoryChangesW` for both Desktop folders. The W168 builder kept that thread; it only moved the icons to their own window.
- **The PS4 wineserver never completes that request.** In `server/change.c`, a folder change is reported only through inotify or dnotify:
  - Wine is configured `--without-inotify` (`tools/probe-wine-unix.py`);
  - the PS4 kernel has no dnotify (`F_NOTIFY`/`F_SETSIG`);
  - `change.c` has no kqueue path (kqueue is only used for polling in `fd.c`).

  The request stays queued (`STATUS_PENDING`), and the thread waits forever without logging anything. The W168 doc had already flagged this risk.
- It doesn't depend on WFM. Any change goes unseen, including the Desktop links the native Steam client writes outside Wine.
- Directory listings themselves are fresh: ntdll caches a listing per handle, and each `FindFirstFileW` opens a new handle.

## Change

`tools/build-explorer-hw.py`, through `desktop-refresh-menu.patch.py` (notes folder). It adds 9 revisions to `desktop.c`, before the W179 block.

- **Poll:**
  - a thread compares a signature of the `*.lnk` files in both Desktop folders every 2 s (name, size and last-write time);
  - on a change, it asks the icon window to reload;
  - it logs `PWDESK poll every 2000 ms` once, and `PWDESK poll change files=N` on each change.
- **Reload on the window's thread:**
  - the list is rebuilt on the icon window's own thread (`PWDESK reload reason=poll|menu|notify launchers=A->B files=N`);
  - upstream changed the list from the watcher thread while the window painted it. A notification, on a Wine that does deliver them, now also just asks for the reload;
  - `process_changes` and `remove_launcher` are no longer needed, and are removed.
- **Right-click menu on an icon** (circle, a two-finger touchpad press or tap, or a mouse's right button):
  - **Open**;
  - **Open file location:** WFM opens in that folder (`wfm.exe "<folder>"`; WFM navigates to its first argument);
  - **Rename:** a small dialog built in memory, so no resource change. The extension is kept, and a name with `\ / : * ? " < > |` is refused;
  - **Delete:** asks first, with No as the default. It deletes only the shortcut, with `DeleteFileW`, since there's no Recycle Bin here;
  - **Properties:** a message box with the target, arguments and start folder, read from the `.lnk`.
  - Errors appear in a message box and in the log (`PWDESK rename|delete … error=N`).
- **Empty desktop:** right-clicking empty desktop, inside or outside the icon window, offers **Refresh** and **Open Desktop folder**.
- **Not included:** "New shortcut" (it needs a target picker) and moving icons by dragging.

## Build

1. Apply: `python3 desktop-refresh-menu.patch.py tools/build-explorer-hw.py`. It refuses if the W179 anchor isn't unique or the patch is already applied.
2. `python3 tools/build-explorer-hw.py`, then the package (`build-wine-hardware.py` checks explorer's manifest).

Scratch check, on a copy of the builder at sha `33c325c6…`, which includes W289's Steam item in Start:
- 66 revisions;
- `desktop.c` compiles without warnings, and `explorer.exe` links.

## Physical test

1. **Rename:** with OrbisDesk open, rename a Desktop shortcut in WFM. Within about 2 s the icon shows the new name. Log: `PWDESK poll change` and `PWDESK reload reason=poll`.
2. **Delete and add:** delete a shortcut in WFM, then copy a `.lnk` into the Desktop folder. Each change appears without restarting.
3. **Steam:** open the Steam client, install or add something that creates a Desktop link, and go back. The icon appears.
4. **Icon menu:** press circle on an icon, then try:
   - Properties shows the target;
   - Rename to "Test" changes the name (a keyboard is needed to type);
   - Delete, then No, keeps it; Delete, then Yes, removes it;
   - Open file location opens WFM in Desktop.
5. **Empty desktop:** press circle on empty desktop. Refresh, then Open Desktop folder.
6. **Closing the menu:** with the menu open, click outside it or press square. It closes, and the taskbar and Start still respond.

## Not verified

- Nothing was tested on the console or in the Linux runner.
- Whether a click outside the menu closes it, given the icon window doesn't take activation; square (Escape) should close it.
- Where the rename dialog and message boxes appear on screen.
- Whether the PS4 file system updates a `.lnk` file's last-write time when it's rewritten in place. A rename, delete or add changes the name or the file count, so those are detected regardless.
