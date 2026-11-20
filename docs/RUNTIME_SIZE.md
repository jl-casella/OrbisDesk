# Runtime size

[English](RUNTIME_SIZE.md) | [Español](RUNTIME_SIZE-es.md)

Status: changed in the builders on 2026-11-20. Built locally as app version 04.41. Not yet checked on the console.

## What a clean install measured

The CI package of `dev` at `ffa54fc` (product run 44659728449, app version 04.32) was installed on a console with no earlier OrbisDesk data. The package is 1.96 GB. Its first start wrote 1651 MB in 6295 files under `/data`:

| Part | MB |
| --- | --- |
| `C:\windows\system32` and `syswow64` | 881 |
| Wine Mono (`C:\windows\mono`) | 275 |
| Wine Gecko (inside system32 and syswow64) | 207 |
| SeaMonkey | 131 |
| `/data/wine` (Wine's libraries) | 118 |
| VLC | 56 |
| MangoJuice | 52 |
| MIDI sound font, winsxs, themes, wallpapers, `C:\orbis` | about 90 |

The package also holds the whole runtime (`/app0/runtime`), so the console stores it twice: in the installed application and in `/data`.

## What this change leaves out

1. **Wine Mono's reference assemblies**, `lib/mono/<version>-api` (about 98 MB). They are metadata for compilers. A running program never loads them.
2. **Wine Mono's development tools**: MSBuild, xbuild and the C#/VB compilers (`csc`, `vbc`, `mcs`, `ilasm`, Roslyn's `Microsoft.CodeAnalysis*`), about 30 MB. With items 1 and 2, the staged Mono tree goes from 275 MB to about 146 MB ([stage-wine-mono.py](../tools/stage-wine-mono.py)).
3. **`games-source.tar.gz`** in system32 (93 MB). It is the source archive of the ReactOS games. Each release's `<tag>-third-party-sources.tar` already carries the pinned ReactOS revision, and [build-games.py](../tools/build-games.py), which makes the stub includes, is in the repository at the tag. The archive stays in `out/games` ([games](GAMES.md)).
4. **Wine library copies that the prefix already holds.** Each PS4 build of a Wine module was copied to `/data/wine/lib/wine/<arch>-windows` and, with the same bytes, to system32 or syswow64. On the clean install that was 155 modules, 93 MB twice. Wine's loader takes a builtin from `lib/wine` first. When `lib/wine` has none, it takes the prefix's copy, which carries the builtin marker. Most modules already loaded that way: those are the `find_builtin_dll ... cannot find builtin library` lines in every log. [build-wine-hardware.py](../tools/build-wine-hardware.py) now removes the `lib/wine` copy of a module whose prefix copy is identical. `ntdll.dll` stays, because the Unix loader maps it from `lib/wine`, and `native/pop_wine_child.c` opens it there by path. `apisetschema.dll` stays too: the Unix loader reads it only from `lib/wine`. Build 04.42 removed it, and every program then failed to resolve `api-ms-win-*` names (`load_apiset_dll failed to load apiset: c000000f`); conhost crashed at desktop start and the start hung. `comctl32_v6.dll` stays because Wine loads it only from `lib/wine`. So do the modules whose Unix library is linked into the launcher ELF (`win32u`, `winevulkan`, `ws2_32`, `opengl32`, `wineps4.drv` and the rest of the table in [pw_wine_unixlibs.c](../platform/ps4/pw_wine_unixlibs.c)): the launcher finds that library by the path Wine records only for a builtin loaded from `lib/wine`. Build 04.43 still loaded `win32u` from system32 with no Unix side, and its start hung at WINE SERVER READY the same way.

## Consoles that already have an earlier build

The installer only adds and replaces files. Without more, the dropped files would stay on a console that installed an earlier build. For item 4 that would also be wrong, not only large: an old `lib/wine` copy would win over the newer copy in the prefix. So every dropped path goes into the build's obsolete list, which the launcher's installer ([hw_install.h](../native/hw_install.h)) and [upload-hardware.py](../tools/upload-hardware.py) delete. That list may now hold paths under `wine/lib/wine/` as well as `wine-prefix/`.

## Limits

- A .NET program that compiles C# at run time (CodeDom's `CSharpCodeProvider`) finds no compiler.
- Item 4 changes where most of Wine's PS4 modules load from. It needs a console run with 64-bit and 32-bit programs before a release: the desktop, a 32-bit game, a DirectX 9 game through wined3d, a Vulkan program, audio and a controller.
- Wine Gecko (207 MB) and the double copy of the runtime are not changed here.

## How to check on the console

1. Install the package over an earlier build.
2. Check that `/data/wine/lib/wine/x86_64-windows` holds `ntdll.dll`, `apisetschema.dll` and the modules with no copy in system32, and that the dropped Mono folders are gone.
3. Start the desktop, open a 32-bit and a 64-bit program, a DirectX 9 game, vkcube, play audio, and use the controller.
