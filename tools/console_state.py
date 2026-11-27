# SPDX-License-Identifier: LGPL-2.1-or-later
"""What the console keeps of user.reg across builds, shared by tools/upload-hardware.py (FTP updates)
and tools/build-wine-hardware.py (install.json, read by the launcher's first-run installer).

W172 (phase 7): the console keeps what the user chose per program in winecfg
(HKCU\\Software\\Wine\\AppDefaults); everything else in user.reg is the build's. Wine rewrites the
file on the console (its server saves every 30 s), so a plain copy would erase those choices.
W175: also the keys of winecfg's Desktop Integration tab (colours, metrics, visual style, app
theme), so the theme the user picks survives builds. Each with its subkeys. A build that must
change one of them names it in manifest['user_reg_reset'] (this spelling, single backslashes):
that update takes it from the build, once."""
CONSOLE_OWNED=('software\\wine\\appdefaults','control panel\\colors','control panel\\desktop\\windowmetrics',
               'software\\microsoft\\windows\\currentversion\\thememanager',
               'software\\microsoft\\windows\\currentversion\\themes\\personalize',
               # W292: explorer's copy of the wallpaper choice (Control Panel\\Desktop stays the build's)
               'software\\orbisdesk')
# Runtime files the console keeps once it has them: an update (upload-hardware.py, or the launcher's first-run
# installer through install.txt's P lines, native/hw_install.h) copies one only when it is missing.
# MangoHud.conf: the user's HUD choices, made with MangoJuice (docs/MANGOJUICE.md) or Notepad;
# the build's copy is the clean-install default.
# 04.36: the pad key profiles OrbisDesk ships (fixtures/padmaps): the overlay's KEY MAPPING edits them on the console.
# The build's copies also go to C:\orbis\padmaps-default, always updated, which its DEFAULT action restores. The
# launcher's installer keeps at most 16 such paths (native/hw_install.h HW_INSTALL_MAX_ROOTS).
import pathlib as _pathlib
_PADMAPS=tuple('wine-prefix/drive_c/orbis/padmaps/'+p.name
               for p in sorted((_pathlib.Path(__file__).resolve().parent.parent/'fixtures/padmaps').glob('*.ini')))
CONSOLE_OWNED_FILES=('wine-prefix/drive_c/users/orbis/AppData/Roaming/MangoHud/MangoHud.conf',)+_PADMAPS
if len(CONSOLE_OWNED_FILES)>16:raise SystemExit('console_state: more than 16 console-owned files (hw_install.h keeps 16)')

# 04.92 (2026-11-26, docs/VCRUNTIME_FALLBACK.md): the Visual C++ runtime DLLs of system32 and syswow64. A
# Microsoft redistributable that a game installer runs inside OrbisDesk (vc_redist, the Rockstar Games Launcher's)
# replaces Wine's copies with Microsoft's, and deletes them again when it is uninstalled or when a failed install
# rolls back: Wine's MSI removes every file of a component it removes unless the disk copy is newer
# (dlls/msi/files.c ACTION_RemoveFiles) and keeps no backup of what it replaced, and this Wine's loader only falls
# back to lib/wine while the prefix is being bootstrapped (dlls/ntdll/loader.c find_builtin_without_file), so a
# missing vcruntime140.dll stays missing and everything importing it fails. Updates (this uploader, and the
# launcher's installer through install.txt's V lines, native/hw_install.h) therefore never replace a copy that is
# not Wine's, and the launcher restores Wine's copy of a missing one on every start from VCRT_FALLBACK_DIR, a
# second copy no installer owns, listed with its hashes in VCRT_FALLBACK_LIST.
# Names: the VC++ 2010-2022 families (versions 100-140), which redistributables install into system32/syswow64
# (2005 and 2008 install into WinSxS); msvcrt.dll (a system DLL OrbisDesk revises) and ucrtbase.dll (likewise,
# and not part of vc_redist on Windows 10) are not in it.
import re as _re
VCRT_NAME=_re.compile(r'^(?:msvcp|msvcr|vcomp|vcruntime|concrt|vccorlib|vcamp|atl|mfc)1[0-4]0(?:_[a-z0-9_]+|u)?\.dll$')
VCRT_FOLDERS=('wine-prefix/drive_c/windows/system32/','wine-prefix/drive_c/windows/syswow64/')
VCRT_FALLBACK_DIR='wine/lib/wine/vcrt-fallback/'
VCRT_FALLBACK_LIST=VCRT_FALLBACK_DIR+'list.txt'
# winebuild (tools/winebuild/spec32.c builtin_signature) writes this after the DOS header of every Wine PE module
WINE_BUILTIN_SIGNATURE=b'Wine builtin DLL'
WINE_BUILTIN_OFFSET=0x40
def is_vcrt_file(path):
    """a runtime path (wine-prefix/drive_c/windows/system32/... spelling) of the Visual C++ runtime"""
    folder,_,name=path.rpartition('/')
    return folder+'/' in VCRT_FOLDERS and bool(VCRT_NAME.match(name.lower()))
def vcrt_fallback_path(path):
    """the runtime path of a VC++ runtime file's fallback copy: wine/lib/wine/vcrt-fallback/<folder>/<name>"""
    folder,_,name=path.rpartition('/')
    return VCRT_FALLBACK_DIR+folder.rpartition('/')[2]+'/'+name
def is_wine_builtin(data):
    """the first bytes (at least 0x50) of a PE file: True when winebuild made it"""
    return data[WINE_BUILTIN_OFFSET:WINE_BUILTIN_OFFSET+len(WINE_BUILTIN_SIGNATURE)]==WINE_BUILTIN_SIGNATURE
