# W293: shortcuts in WFM show their own icon, with the arrow (draft)

[English](HARDWARE_W293-wfm-accesos-borrador.md) | [Español](HARDWARE_W293-wfm-accesos-borrador-es.md)

Draft to merge into the W293 notes. Nothing here was tested on the console.

## Report

User, after W292: in File Manager's Desktop folder, the shortcuts other than File Manager, Open Steam Client and Portal 2 appear without their icon, though they are shortcuts and the desktop shows them with it.

## Cause

- WFM asks shell32 for each file's icon (`SHGetFileInfo` with `SHGFI_SYSICONINDEX`, `file_utils.h` `getFileInfo`).
- For a `.lnk`, Wine's shell32 (`dlls/shell32/folders.c`, `IExtractIconW_fnGetIconLocation`, the `lnkfile` branch) takes only the link's **IconLocation**. Without one, it gives the generic file icon and never looks at the target.
- The three that looked right carry an IconLocation:
  - `File Manager.lnk` and `Open Steam Client.lnk` are written by `tools/build-steam-hosted.py`;
  - Portal 2's link is written by the Steam client (`native/steam/steam_shortcut.cpp`, `kHasIconLocation`).
- Links made with only a target, such as `IShellLink::SetPath` (WFM's own "Create shortcut" does this), have none.
- explorer's desktop falls back to the target's icon (`desktop.c` `extract_icon`), so they looked right there.
- Also, shell32 adds the shortcut arrow only for large icons. In the list and details views no shortcut had the arrow.

## Change

`tools/build-wfm.py`, through `wfm-shortcut-icons.patch.py` (notes folder). It adds 2 revisions to `content_view.c`, in the list's `LVN_GETDISPINFO`. For a `.lnk` file:
- the IconLocation when the link has one (shell32 resolves it from the `.lnk`);
- else the target's icon, when the target exists;
- else the `.lnk`'s own icon.

It always asks with `SHGFI_LINKOVERLAY`, so the arrow appears in every view. Opening a shortcut is unchanged. Log, once per item: `PWFM shortcut_icon source=lnk|target|target-missing|unread path=… target=… icon=N`.

A target on a USB disk in NORMAL mode doesn't exist, so the link keeps the generic icon with the arrow: `source=target-missing`. The desktop doesn't show those links at all, because explorer drops a launcher whose icon it can't extract. That explains the W292 log's 5 launchers in NORMAL against 9 in ROOT.

Why not fix shell32: shell32 isn't built by the project (it comes from the pinned Wine build), and the change in WFM is contained. Fixing the fallback in shell32 would also fix file dialogs and other programs; it's left as a possible follow-up.

## Correction after W293 on the console

- On the console, WFM still showed the generic icons, and the log had no `PWFM shortcut_icon` line at all (`reports/wine-hardware-w293/physical/manual-20261108T052636Z/run-0001.log`). WFM had listed Desktop normally (`PWFM children path=Desktop count=9`).
- Cause: WFM's `getFileExtension` returns the extension without its dot, so the W293 check `hasFileExtension(path, L".lnk")` never matched, and the new code never ran. The check is now `L"lnk"`.
- Every list item in a Desktop folder, the user's or the public one, now also logs `PWFM desktop_item_icon path=… type=… view=… icon=N`, whatever its type or the view.
- On a builder that already has the W293 version, the script replaces that block.

## Build

1. Apply: `python3 wfm-shortcut-icons.patch.py tools/build-wfm.py`.
2. `python3 tools/build-wfm.py`, then the package (`build-wine-hardware.py` checks WFM's manifest).

Scratch check, on a copy of the builder at sha `a4b4589b…` (with the W293 version, which the script replaced): WFM builds (`wfm.exe` sha `4e7cffa6…`, in place of W293's `38103c3a…`). The one warning (`pwfmDeleteTree` unused) is in `pwfm_operations.h`, which `content_view.c` already included; this change doesn't cause it.

## Physical test

1. In WFM, open `C:\users\orbis\Desktop`. Every shortcut shows its program's icon with the shortcut arrow, in both the list and the large-icon view. Log: `PWFM shortcut_icon source=target` for SuperMarioKart and The Lost Forest, and `source=lnk` for File Manager, Steam and Portal 2.
2. Double-click a shortcut: the program opens as before.
3. In NORMAL, links to programs on a USB disk show the generic icon with the arrow (`source=target-missing`). In ROOT they show the program's icon.

## Not verified

- The corrected build wasn't tested on the console. The W293 build didn't run the change at all.
- That Wine draws the arrow over a target's icon when asked with `SHGFI_LINKOVERLAY`. `SIC_GetIconIndex` composes it for `GIL_FORSHORTCUT`, which this flag sets.
- The tree on the left lists only folders, so it's unchanged.
