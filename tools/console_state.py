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
