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
