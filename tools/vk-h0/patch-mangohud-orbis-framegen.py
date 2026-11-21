#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""MangoHud's FPS row shows the frames on screen while frame generation shows frames (04.20).

MangoHud counts the presents of the swapchain it draws in. With GENERAR CUADROS on, the game still presents 30 times a
second and the hardware sink adds a generated frame between each two after MangoHud has drawn (docs/FRAME_GENERATION.md),
so the HUD kept saying 30 while the screen showed about 60 (hardware 2026-11-17, run-0218). The sink counts what reached
the screen and the private telemetry query MangoHud already makes (patch-mangohud-orbis-metrics.py) returns it to a
caller whose buffer holds struct pw_ps4_telemetry_fg (platform/ps4/pw_telemetry.h, version 2).

Here, in the fps and fps_only elements only: while the query says generated frames are on screen for an image of this
swapchain's size, the value is the frames on screen (real plus generated) and the FPS superscript reads FG. Everything
else stays MangoHud's own: the frametime column, the graph, the 1% lows, the FPS limiter and the logs keep the game's
presents. Since MangoHud draws it, the row follows MangoHud's show/hide, place, font and colours, and whatever MangoJuice
saves in MangoHud.conf, in the 64-bit and the i386 build alike (build-mangohud-i386.sh copies this tree). With an older
native side the query returns version 1 and nothing changes.

Run after patch-mangohud-orbis-metrics.py, which writes orbis_metrics.h and orbis_telemetry.h.
"""
import hashlib, json, pathlib, sys

MARKER = 'OrbisDesk 04.20: frame generation frames on screen'
root = pathlib.Path(sys.argv[1])
for needed in ('src/orbis_metrics.h', 'src/orbis_telemetry.h'):
    if not (root / needed).is_file():
        raise SystemExit('run patch-mangohud-orbis-metrics.py first: missing ' + needed)
if 'pw_ps4_telemetry_fg' not in (root / 'src/orbis_telemetry.h').read_text():
    raise SystemExit('src/orbis_telemetry.h has no struct pw_ps4_telemetry_fg: platform/ps4/pw_telemetry.h is older than 04.20')

helper = r'''#pragma once
// ''' + MARKER + r''' (tools/vk-h0/patch-mangohud-orbis-framegen.py)
#include <windows.h>
#include <cstdio>
#include "orbis_telemetry.h"
#include "orbis_metrics.h"

namespace orbis_framegen {
// The frames a second on screen of a width x height swapchain while frame generation shows generated frames on it:
// true and fps set, else false (MangoHud's own value then). Called while the HUD is drawn, under the shared UI lock.
inline bool shown_fps(float width, float height, float& fps)
{
    typedef LONG (NTAPI *Query)(ULONG,void*,ULONG,ULONG*);
    static Query query=nullptr;
    static bool resolved=false;
    static pw_ps4_telemetry_fg cached{};
    static ULONGLONG last=0;
    static ULONG logged_flags=~0ul;
    static unsigned logged_width=0,logged_height=0;
    if (!orbis_metrics::active()) return false;
    const ULONGLONG now=GetTickCount64();
    if (!resolved) {
        query=(Query)GetProcAddress(GetModuleHandleW(L"ntdll.dll"),"NtQuerySystemInformation");
        resolved=true;
    }
    if (!last || now-last>=250) {
        last=now;
        pw_ps4_telemetry_fg next{};
        ULONG bytes=0;
        LONG status=query?query(PW_PS4_TELEMETRY_CLASS,&next,sizeof(next),&bytes):(LONG)0xc00000bbu;
        const bool valid=!status && bytes==sizeof(next) && next.base.version==PW_TELEMETRY_FG_VERSION &&
                         next.base.size==sizeof(next);
        if (!valid) next=pw_ps4_telemetry_fg{};
        cached=next;
        if (cached.fg_flags!=logged_flags || (cached.fg_flags && (cached.fg_width!=logged_width || cached.fg_height!=logged_height))) {
            char text[240];
            std::snprintf(text,sizeof(text),"PWHUD framegen query=%08lx bytes=%lu version=%u flags=%x image=%ux%u shown_x10=%u "
                          "real_x10=%u generated_x10=%u hud=%ux%u",(unsigned long)status,(unsigned long)bytes,
                          valid?next.base.version:0u,cached.fg_flags,cached.fg_width,cached.fg_height,cached.fg_shown_tenths,
                          cached.fg_real_tenths,cached.fg_generated_tenths,(unsigned)(width+0.5f),(unsigned)(height+0.5f));
            OutputDebugStringA(text);
            logged_flags=cached.fg_flags;logged_width=cached.fg_width;logged_height=cached.fg_height;
        }
    }
    if (!(cached.fg_flags & PW_FG_SHOWN)) return false;
    // the image frame generation follows is a swapchain's own size: a HUD on another size is another program's
    if (cached.fg_width!=(unsigned)(width+0.5f) || cached.fg_height!=(unsigned)(height+0.5f)) return false;
    fps=cached.fg_shown_tenths/10.0f;
    return true;
}
}
'''
(root / 'src/orbis_framegen.h').write_text(helper)

path = root / 'src/hud_elements.cpp'
text = path.read_text()
if MARKER not in text:
    def once(haystack, old, new, where):
        if haystack.count(old) != 1:
            raise SystemExit('unexpected src/hud_elements.cpp (' + where + '): ' + old.strip()[:90])
        return haystack.replace(old, new, 1)

    text = once(text, '#include "hud_elements.h"\n', '#include "hud_elements.h"\n#include "orbis_framegen.h"\n', 'includes')
    start = text.index('void HudElements::fps(){')
    middle = text.index('void HudElements::fps_only(){', start)
    end = text.index('void HudElements::gpu_name(){', middle)
    fps, fps_only = text[start:middle], text[middle:end]
    declare = ('    // ' + MARKER + ' (tools/vk-h0/patch-mangohud-orbis-framegen.py):\n'
               '    // the value is the frames on screen, real plus generated, and the superscript FG; the rest is MangoHud\'s\n'
               '    float orbis_fg_fps = 0.0f;\n'
               '    const bool orbis_fg = orbis_framegen::shown_fps(ImGui::GetIO().DisplaySize.x, ImGui::GetIO().DisplaySize.y, orbis_fg_fps);\n'
               '    const float orbis_shown = orbis_fg ? orbis_fg_fps : HUDElements.sw_stats->fps;\n')

    fps = once(fps, 'void HudElements::fps(){\n', 'void HudElements::fps(){\n' + declare, 'fps')
    fps = once(fps, '            int fps = int(HUDElements.sw_stats->fps);', '            int fps = int(orbis_shown);', 'fps colour')
    if fps.count('"%.0f", HUDElements.sw_stats->fps);') != 2:
        raise SystemExit('unexpected src/hud_elements.cpp (fps): the two value texts changed')
    fps = fps.replace('"%.0f", HUDElements.sw_stats->fps);', '"%.0f", orbis_shown);')
    fps = once(fps, '''        if(!HUDElements.params->enabled[OVERLAY_PARAM_ENABLED_hide_fps_superscript]){
            ImGui::PushFont(HUDElements.sw_stats->font_small);
            HUDElements.TextColored(HUDElements.colors.text, "FPS");
            ImGui::PopFont();
        }''', '''        if(orbis_fg || !HUDElements.params->enabled[OVERLAY_PARAM_ENABLED_hide_fps_superscript]){
            ImGui::PushFont(HUDElements.sw_stats->font_small);
            HUDElements.TextColored(HUDElements.colors.text, "%s", orbis_fg ? "FG" : "FPS");
            ImGui::PopFont();
        }''', 'fps superscript')
    if '1000 / HUDElements.sw_stats->fps' not in fps:
        raise SystemExit('unexpected src/hud_elements.cpp (fps): the frametime column changed')

    fps_only = once(fps_only, 'void HudElements::fps_only(){\n', 'void HudElements::fps_only(){\n' + declare, 'fps_only')
    fps_only = once(fps_only, '            int fps = int(HUDElements.sw_stats->fps);', '            int fps = int(orbis_shown);',
                    'fps_only colour')
    fps_only = once(fps_only, '        HUDElements.TextColored(load_color, "%.0f", HUDElements.sw_stats->fps);\n',
                    '''        HUDElements.TextColored(load_color, "%.0f", orbis_shown);
        if (orbis_fg) {
            ImGui::SameLine(0, 1.0f);
            ImGui::PushFont(HUDElements.sw_stats->font_small);
            HUDElements.TextColored(HUDElements.colors.text, "FG");
            ImGui::PopFont();
        }
''', 'fps_only value')
    text = text[:start] + fps + fps_only + text[end:]
    path.write_text(text)
    print('frame generation patch applied')
else:
    print('frame generation patch already applied')
names = ('src/hud_elements.cpp', 'src/orbis_framegen.h')
print(json.dumps({'patch': '04.20-Orbis-framegen', 'sources': {n: hashlib.sha256((root / n).read_bytes()).hexdigest() for n in names}}))
