// SPDX-License-Identifier: LGPL-2.1-or-later
// SeaMonkey's default preferences for GPU compositing on the console (docs/SEAMONKEY_GPU.md).
// tools/build-wine-hardware.py installs this file as defaults/pref/orbisdesk-gpu.js in SeaMonkey's
// folder.
//
// layers.prefer-opengl true makes Gecko composite with OpenGL when acceleration is on, through the
// 64-bit opengl32 in system32 (Mesa's WGL with Zink on RADV); false there leaves no accelerated
// backend (user.js blocks Direct3D 11), and Gecko uses Basic. If the OpenGL context cannot be made,
// Gecko also falls back to Basic, and about:support shows "[OPENGL] Failed to init compositor"
// under Failure Log.
pref("layers.prefer-opengl", true);

// 04.30: the GPU compositing and WebGL switches, as defaults (up to 04.29 user.js set them at every
// start). Changed in about:config, they stay across starts and uploads. Off for now: with OpenGL,
// 04.29 drew the window 34 pixels too high and YouTube did not play (docs/SEAMONKEY_GPU.md). To turn
// both on by default, set the two "disabled" values below to false. With "disabled" false the
// "force-enabled" values skip Gecko's blocklist, which does not know Wine's adapter.
// 04.34 (run-0270): the 34 pixels are Gecko's own. Its OpenGL compositor takes its frame size from
// nsWindow::GetBounds (GetWindowRect, frame included), while the drawable is the client area. Basic and
// Direct3D 11 hide that; OpenGL on Windows does not. Wine, Mesa and Zink return the client size, so
// OpenGL stays off by default (docs/SEAMONKEY_GPU.md).
pref("layers.acceleration.disabled", true);
pref("layers.acceleration.force-enabled", true);
// 04.34: WebGL on by default with the Basic compositor (the user's choice); GPU compositing stays off.
pref("webgl.disabled", false);
pref("webgl.force-enabled", true);

// 04.30: orbisdesk.cfg in SeaMonkey's folder clears, once per profile, the values user.js saved in
// prefs.js up to 04.29, so the defaults above apply.
pref("general.config.filename", "orbisdesk.cfg");
pref("general.config.obscure_value", 0);
pref("general.config.sandbox_enabled", false);
