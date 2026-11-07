#!/usr/bin/env python3
"""Use the versioned native Orbis query, not Windows system/DXGI counters."""
import sys as _brand_sys
from pathlib import Path as _BrandPath
_brand_sys.path.insert(0,str(_BrandPath(__file__).resolve().parents[1]))
from project_brand import normalize_marker

import argparse,hashlib,json,pathlib
parser=argparse.ArgumentParser();parser.add_argument('source',type=pathlib.Path)
root=parser.parse_args().source
project=pathlib.Path(__file__).resolve().parents[2]
schema=normalize_marker((project/'platform/ps4/pw_telemetry.h').read_text())
(root/'src/orbis_telemetry.h').write_text(schema)
helper=r'''#pragma once
#include <windows.h>
#include <cstdio>
#include "orbis_telemetry.h"

namespace orbis_metrics {
inline bool active()
{
    static const bool value=[] { char b[8]={0}; return GetEnvironmentVariableA("WINE_PS4_GUESTS",b,sizeof(b)) && b[0]=='1'; }();
    return value;
}
inline bool read(pw_ps4_telemetry& result)
{
    typedef LONG (NTAPI *Query)(ULONG,void*,ULONG,ULONG*);
    static Query query=nullptr;
    static bool resolved=false;
    static pw_ps4_telemetry cached{};
    static ULONGLONG last=0,last_log=0;
    if (!active()) return false;
    const ULONGLONG now=GetTickCount64();
    if (!resolved) {
        query=(Query)GetProcAddress(GetModuleHandleW(L"ntdll.dll"),"NtQuerySystemInformation");
        resolved=true;
    }
    if (!last || now-last>=500) {
        last=now;
        pw_ps4_telemetry next{};
        ULONG bytes=0;
        LONG status=query?query(PW_PS4_TELEMETRY_CLASS,&next,sizeof(next),&bytes):(LONG)0xc00000bbu;
        if (status || bytes!=sizeof(next) || next.version!=PW_TELEMETRY_VERSION || next.size!=sizeof(next)) {
            next={};next.cpu_status=next.gpu_status=status?status:(LONG)0xc000000du;
        }
        cached=next;
        if (!last_log || now-last_log>=5000) {
            char text[240];
            std::snprintf(text,sizeof(text),"PWHUD native_metrics query=%08lx flags=%x cores=%u cpu_mp=%u cpu_rc=%ld gpu_mp=%u gpu_rc=%ld lost=%llu",
                          (unsigned long)status,cached.flags,cached.cpu_cores,cached.cpu_millipercent,
                          (long)cached.cpu_status,cached.gpu_millipercent,(long)cached.gpu_status,
                          (unsigned long long)cached.gpu_lost_events);
            OutputDebugStringA(text);last_log=now;
        }
    }
    result=cached;
    return true;
}
}
'''
(root/'src/orbis_metrics.h').write_text(helper)

def replace_file(name, marker, replacements):
    path=root/name;text=normalize_marker(path.read_text())
    if marker in text:return
    for old,new in replacements:
        if text.count(old)!=1:raise SystemExit('Orbis metrics source context changed: '+name+': '+old[:100])
        text=text.replace(old,new,1)
    path.write_text(text)

replace_file('src/cpu_win32.cpp','// OrbisDesk W103: native title counters, no fabricated per-core data.',[
    ('#include "cpu.h"','#include "cpu.h"\n#include "orbis_metrics.h"'),
    ('''    // --- Total CPU usage via GetSystemTimes ---''', '''    // OrbisDesk W103: native title counters, no fabricated per-core data.
    if (orbis_metrics::active()) {
        pw_ps4_telemetry sample{};
        orbis_metrics::read(sample);
        m_cpuDataTotal.percent=(sample.flags & PW_CPU_VALID)?sample.cpu_millipercent/1000.0f:-1.0f;
        for (auto& core : m_cpuData) core.percent=-1.0f;
        return (sample.flags & PW_CPU_VALID)!=0;
    }

    // --- Total CPU usage via GetSystemTimes ---''')])

cpu='''    // OrbisDesk W103: display title metrics or explicit N/A.
    if (orbis_metrics::active()) {
        if (HUDElements.params->enabled[OVERLAY_PARAM_ENABLED_cpu_stats]) {
            pw_ps4_telemetry sample{};orbis_metrics::read(sample);
            ImguiNextColumnFirstItem();
            HUDElements.TextColored(HUDElements.colors.cpu,"CPU");
            ImguiNextColumnOrNewRow();
            if (sample.flags & PW_CPU_VALID)
                right_aligned_text(HUDElements.colors.text,HUDElements.ralign_width,"%.1f%%",sample.cpu_millipercent/1000.0);
            else right_aligned_text(HUDElements.colors.text,HUDElements.ralign_width,"N/A");
        }
        return;
    }
'''
gpu=cpu.replace('cpu_stats','gpu_stats').replace('colors.cpu','colors.gpu').replace('"CPU"','"GPU"').replace('PW_CPU_VALID','PW_GPU_VALID').replace('cpu_millipercent','gpu_millipercent')
replace_file('src/hud_elements.cpp','// OrbisDesk W103: display title metrics or explicit N/A.',[
    ('#include "hud_elements.h"','#include "hud_elements.h"\n#include "orbis_metrics.h"'),
    ('void HudElements::cpu_stats(){','void HudElements::cpu_stats(){\n'+cpu),
    ('void HudElements::gpu_stats(){','void HudElements::gpu_stats(){\n'+gpu)])
replace_file('src/overlay.cpp','// OrbisDesk W103: logging/graphs use the same native validity.',[
    ('#include "overlay.h"','#include "overlay.h"\n#include "orbis_metrics.h"'),
    ('   // Save data for graphs','''   // OrbisDesk W103: logging/graphs use the same native validity.
   if (orbis_metrics::active()) {
      pw_ps4_telemetry sample{};orbis_metrics::read(sample);
      currentLogData.cpu_load=(sample.flags & PW_CPU_VALID)?sample.cpu_millipercent/1000.0f:-1.0f;
      currentLogData.gpu_load=(sample.flags & PW_GPU_VALID)?sample.gpu_millipercent/1000.0f:-1.0f;
   }
   // Save data for graphs''')])
# W104: relabel an existing W103 build copy as well as a fresh source.
p=root/'src/hud_elements.cpp'
t=normalize_marker(p.read_text()).replace('colors.cpu,"CPU app"','colors.cpu,"CPU"').replace('colors.gpu,"GPU app"','colors.gpu,"GPU"')
p.write_text(t)
names=('src/cpu_win32.cpp','src/hud_elements.cpp','src/overlay.cpp','src/orbis_metrics.h','src/orbis_telemetry.h')
print(json.dumps({'patch':'W103-Orbis-metrics','sources':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names}}))
