#!/usr/bin/env python3
"""W102: adapt persistent MangoHud sampling services to in-process guests.

Run the existing sampling/calculation synchronously under W096's frame lock.
Don't retain instance parameters in a worker created by a short-lived guest.
Configuration is read at instance creation; live file watching is disabled.
"""
import sys as _brand_sys
from pathlib import Path as _BrandPath
_brand_sys.path.insert(0,str(_BrandPath(__file__).resolve().parents[1]))
from project_brand import normalize_marker

import argparse
import hashlib
import json
import pathlib

parser = argparse.ArgumentParser()
parser.add_argument('source', type=pathlib.Path)
root = parser.parse_args().source
changed = []

def edit(name, marker, transform):
    path = root / name
    text = normalize_marker(path.read_text())
    if marker in text:
        return
    updated = transform(text)
    if marker not in updated:
        raise SystemExit('Missing sampling marker: ' + name)
    path.write_text(updated)
    changed.append(name)

def once(text, old, new):
    if text.count(old) != 1:
        raise SystemExit('Sampling patch context mismatch: ' + old[:100])
    return text.replace(old, new, 1)

def overlay(text):
    start = text.index('struct hw_info_updater\n{')
    end = text.index('\nstatic std::unique_ptr<hw_info_updater> hw_update_thread;', start)
    return text[:start] + '''// OrbisDesk W102: sample on the frame thread, never retain instance parameters.
struct hw_info_updater
{
   void update(const struct overlay_params* params, uint32_t vendorID)
   {
      if (params) update_hw_info(*params, vendorID);
   }
};
''' + text[end:]

edit('src/overlay.cpp', '// OrbisDesk W102: sample on the frame thread', overlay)

def metrics(text):
    text = once(text, '''            if (!thread_init) {
                thread = std::thread(&fpsMetrics::_thread, this);
                // Thread naming omitted on Windows
            }''', '''            // OrbisDesk W102: calculate on the frame thread, without a worker.
            thread_init = true;''')
    text = once(text, '''        void update_thread(){
            if (resetting)
                return;

            {
                std::lock_guard<std::mutex> lock(mtx);
                run = true;
            }
            cv.notify_one();
        }''', '''        void update_thread(){
            std::lock_guard<std::mutex> lock(mtx);
            calculate();
        }''')
    text = once(text, '''            resetting = true;
            while (run){}
            frametimes.clear();
            resetting = false;''', '''            std::lock_guard<std::mutex> lock(mtx);
            frametimes.clear();''')
    return once(text, '''        ~fpsMetrics(){
            terminate = true;
            {
                std::lock_guard<std::mutex> lock(mtx);
                run = true;
            }
            cv.notify_one();
            if (thread.joinable())
                thread.join();
        }''', '''        ~fpsMetrics() = default;''')

edit('src/fps_metrics.h', '// OrbisDesk W102: calculate on the frame thread', metrics)
edit('src/notify_win32.cpp', '// OrbisDesk W102: configuration reloads at instance creation',
     lambda text: once(text, '    nt.thread = std::thread(watchDirectory, &nt);',
                      '''    // OrbisDesk W102: configuration reloads at instance creation.
    // No watcher outlives the guest that first initialized a shared GL/Vulkan DLL.
    OutputDebugStringA("PWHUD config_watcher=disabled reload=restart_orbisdesk");'''))
edit('src/vulkan.cpp', '// OrbisDesk W102: report the sampling policy',
     lambda text: once(text, '      init_cpu_stats(instance_data->params);', '''      init_cpu_stats(instance_data->params);
      // OrbisDesk W102: report the sampling policy.
      OutputDebugStringA("PWHUD sampling=frame fps_metrics=frame config_watcher=disabled");'''))

print(json.dumps({'patch': 'W102-frame-sampling', 'changed': changed,
    'sources': {name: hashlib.sha256((root/name).read_bytes()).hexdigest()
                for name in ('src/overlay.cpp','src/fps_metrics.h','src/notify_win32.cpp','src/vulkan.cpp')}}))
