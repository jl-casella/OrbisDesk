// SPDX-License-Identifier: LGPL-2.1-or-later
// Draft (not in the repo yet): preferences of the console's SeaMonkey 2.53 profile (user.js in the
// profile folder the Start menu shortcut passes with -profile). SeaMonkey runs as a guest of
// explorer, in one process; its files and default preferences are not changed.

// One process. SeaMonkey turned e10s off by pref (bug 1410614); the Firefox 60 platform can still
// start a GPU process, plugin-container (NPAPI plugins, Gecko media plugins) and a WebExtensions
// process. A guest's CreateProcess starts another guest, not a separate process.
user_pref("browser.tabs.remote.autostart", false);
user_pref("browser.tabs.remote.force-enable", false);
user_pref("layers.gpu-process.enabled", false);
user_pref("layers.gpu-process.force-enabled", false);
user_pref("dom.ipc.plugins.enabled", false);
user_pref("plugin.disable", true);
user_pref("media.gmp-provider.enabled", false);
user_pref("media.gmp-gmpopenh264.enabled", false);
user_pref("media.gmp-widevinecdm.enabled", false);
user_pref("media.eme.enabled", false);
user_pref("extensions.webextensions.remote", false);

// GPU compositing (OpenGL through Mesa WGL/Zink) and WebGL: from 04.30 their switches are SeaMonkey's
// defaults (defaults/pref/orbisdesk-gpu.js, docs/SEAMONKEY_GPU.md), not set here, so a change in
// about:config stays. Up to 04.29 this file set layers.acceleration.disabled, ...force-enabled and
// webgl.disabled at every start; orbisdesk.cfg clears their saved values once per profile.
// Never Direct3D 11: in explorer's process, system32's d3d11.dll is DXVK's, and Pale Moon's D3D11
// compositor there never presented a frame and hung (W204/W205: no VK_KHR_external_memory_win32,
// no keyed mutex). The blocklist value 3 (blocked device) keeps D3D11 compositing, Direct2D and
// D3D11 ANGLE off before d3d11.dll is loaded, with GPU compositing on or off.
user_pref("gfx.blacklist.layers.direct3d11", 3);
user_pref("gfx.blacklist.layers.direct3d11.failureid", "ORBISDESK_NO_D3D11");
user_pref("gfx.direct2d.disabled", true);
user_pref("gfx.canvas.azure.backends", "skia");
user_pref("gfx.content.azure.backends", "skia");
user_pref("media.hardware-video-decoding.enabled", false);
user_pref("webgl.disable-angle", true);

// No updates, telemetry or default-client checks.
user_pref("app.update.enabled", false);
user_pref("app.update.auto", false);
user_pref("app.update.service.enabled", false);
// 04.26: with updates off, nsSuiteGlue.js shows "Your copy of SeaMonkey is old and probably has known security
// flaws" at start once the build is 90 days old; app.updatecheck.override true is its "never show".
user_pref("app.updatecheck.override", true);
user_pref("extensions.update.enabled", false);
user_pref("toolkit.telemetry.enabled", false);
user_pref("toolkit.telemetry.unified", false);
user_pref("datareporting.healthreport.uploadEnabled", false);
user_pref("datareporting.policy.dataSubmissionEnabled", false);
user_pref("shell.checkDefaultClient", false);
user_pref("browser.shell.checkDefaultBrowser", false);

// Memory: about 447 MB of flexible memory for the whole title (explorer included).
user_pref("browser.cache.disk.capacity", 102400);
user_pref("browser.sessionhistory.max_total_viewers", 0);
user_pref("browser.sessionhistory.max_entries", 20);
user_pref("image.multithreaded_decoding.limit", 1);
user_pref("network.prefetch-next", false);
user_pref("network.dns.disablePrefetch", true);
user_pref("network.http.speculative-parallel-limit", 0);

// Descriptors (docs/SEAMONKEY_DESCRIPTORS.md; W303 04.11: YouTube stopped when the title, explorer
// included, ran out at 958 open descriptors). With the in-process wineserver an open file or socket
// handle takes two (the server's and the client's copy) and a live thread six. No disk cache: its
// files (up to 128 open handles in Gecko 60) were what failed to open; the memory cache takes its
// place, its malloc heap in direct memory since docs/SEAMONKEY_FLEXIBLE_MEMORY.md. At most 64
// connections at once instead of 900.
user_pref("browser.cache.disk.enable", false);
user_pref("browser.cache.memory.capacity", 65536);
user_pref("network.http.max-connections", 64);

// Full screen at once (docs/SEAMONKEY_RESPONSIVENESS.md; 04.14 run-0192: every switch to full screen
// started a thread with its own full-screen window, Gecko's fade-to-black transition, before the
// browser's window followed). With both durations 0 Gecko skips the transition.
user_pref("full-screen-api.transition-duration.enter", "0 0");
user_pref("full-screen-api.transition-duration.leave", "0 0");

// Scrolling jumps instead of animating (docs/SEAMONKEY_RESPONSIVENESS.md; 04.15 run-0207: the window
// reached 57-58 displayed frames a second while a video played, but 10-45 while the page scrolled or
// loaded, with the presenter never behind). Without e10s there is no async scrolling, so each step of a
// smooth scroll is another repaint on the main thread; without it a wheel notch or key is one.
user_pref("general.smoothScroll", false);

// The network, as Pale Moon's (W185, W188): online always, no captive-portal probe, IPv4 only,
// no proxy, no reaction to network-change notifications, no TCP keepalive.
user_pref("network.manage-offline-status", false);
user_pref("network.offline-mirrors-connectivity", false);
user_pref("network.captive-portal-service.enabled", false);
user_pref("network.dns.disableIPv6", true);
user_pref("network.proxy.type", 0);
user_pref("network.notify.changed", false);
user_pref("network.tcp.keepalive.enabled", false);

// The browser only at start (SeaMonkey is also a mail client), on the local test page; no session
// restore after a crash.
user_pref("general.startup.browser", true);
user_pref("general.startup.mail", false);
user_pref("browser.startup.homepage", "file:///C:/orbis/webtest/index.html");
user_pref("browser.startup.page", 1);
user_pref("browser.sessionstore.resume_from_crash", false);
