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

// No GPU compositing (Pale Moon W183/W184: D3D11 through DXVK in the browser's process). In the
// Firefox 60 platform the switch is layers.acceleration.disabled (UXP's is ...enabled).
user_pref("layers.acceleration.disabled", true);
user_pref("gfx.direct2d.disabled", true);
user_pref("gfx.canvas.azure.backends", "skia");
user_pref("gfx.content.azure.backends", "skia");
user_pref("media.hardware-video-decoding.enabled", false);
user_pref("webgl.disabled", true);
user_pref("webgl.disable-angle", true);

// No updates, telemetry or default-client checks.
user_pref("app.update.enabled", false);
user_pref("app.update.auto", false);
user_pref("app.update.service.enabled", false);
user_pref("extensions.update.enabled", false);
user_pref("toolkit.telemetry.enabled", false);
user_pref("toolkit.telemetry.unified", false);
user_pref("datareporting.healthreport.uploadEnabled", false);
user_pref("datareporting.policy.dataSubmissionEnabled", false);
user_pref("shell.checkDefaultClient", false);
user_pref("browser.shell.checkDefaultBrowser", false);

// Memory: about 447 MB of flexible memory for the whole title (explorer included).
user_pref("browser.cache.memory.capacity", 32768);
user_pref("browser.cache.disk.capacity", 102400);
user_pref("browser.sessionhistory.max_total_viewers", 0);
user_pref("browser.sessionhistory.max_entries", 20);
user_pref("image.multithreaded_decoding.limit", 1);
user_pref("network.prefetch-next", false);
user_pref("network.dns.disablePrefetch", true);
user_pref("network.http.speculative-parallel-limit", 0);

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
