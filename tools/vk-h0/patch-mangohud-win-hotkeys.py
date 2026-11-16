#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""MangoHud hotkeys on Windows keep their defaults when MangoHud.conf names them (2026-11-16).

src/overlay_params.cpp parses key names ("Shift_R+F12") with xkbcommon, only built with X11 or Wayland.
Without them, which is every Windows build, parse_toggle_hud and the other hotkey parsers are defined as
"{}", and set_parameters_from_options applies each line of the file with params->name = parse_name(value):
a file that names toggle_hud (MangoJuice always writes toggle_hud=Shift_R+F12) leaves an empty key list,
which keys_are_pressed never reports pressed. The fork's _WIN32 block in parse_overlay_config redefines
the parsers to keep the value, but it comes after the functions that use them, so it never applied.
Hardware 2026-11-16: once MangoHud read MangoJuice's file (MANGOHUD_CONFIGFILE, native/wine_hardware.c),
the overlay's show/hide (Shift+F12, which MangoHud reads as its default F12) stopped working in 32-bit and
64-bit programs alike. Here the parsers keep the current value: the defaults set_param_defaults gives
on Windows (F12 for toggle_hud). The i386 build copies this tree (build-mangohud-i386.sh).
"""
import pathlib, sys

MARKER = 'OrbisDesk: Windows hotkeys keep their defaults'
path = pathlib.Path(sys.argv[1]) / 'src/overlay_params.cpp'
text = path.read_text()
if MARKER in text:
    print('hotkeys patch already applied')
    sys.exit(0)
old = """#else
#define parse_toggle_hud(x)            {}
#define parse_toggle_hud_position(x)   {}
#define parse_toggle_logging(x)        {}
#define parse_reload_cfg(x)            {}
#define parse_upload_log(x)            {}
#define parse_upload_logs(x)           {}
#define parse_toggle_fps_limit(x)      {}
#define parse_toggle_preset(x)         {}
#define parse_reset_fps_metrics(x)     {}
#endif
"""
new = """#else
/* """ + MARKER + """ (tools/vk-h0/patch-mangohud-win-hotkeys.py): "{}" emptied
 * the key list of every hotkey MangoHud.conf names, and keys_are_pressed never matched again */
#define parse_toggle_hud(x)            params->toggle_hud
#define parse_toggle_hud_position(x)   params->toggle_hud_position
#define parse_toggle_logging(x)        params->toggle_logging
#define parse_reload_cfg(x)            params->reload_cfg
#define parse_upload_log(x)            params->upload_log
#define parse_upload_logs(x)           params->upload_logs
#define parse_toggle_fps_limit(x)      params->toggle_fps_limit
#define parse_toggle_preset(x)         params->toggle_preset
#define parse_reset_fps_metrics(x)     params->reset_fps_metrics
#endif
"""
if text.count(old) != 1:
    raise SystemExit('unexpected src/overlay_params.cpp: the no-X11 hotkey parsers changed')
path.write_text(text.replace(old, new))
print('hotkeys patch applied')
