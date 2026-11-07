#!/usr/bin/env python3
"""W096: serialize MangoHud's global UI state across in-process Wine guests.

Apply to the build copy, keeping the pinned upstream checkout untouched.
Do not hold the UI lock across the downstream presentation (GDI/VideoOut).
"""
import sys as _brand_sys
from pathlib import Path as _BrandPath
_brand_sys.path.insert(0,str(_BrandPath(__file__).resolve().parents[1]))
from project_brand import normalize_marker

import argparse
import hashlib
import json
import pathlib
import re

parser = argparse.ArgumentParser()
parser.add_argument('source', type=pathlib.Path)
args = parser.parse_args()
path = args.source / 'src/vulkan.cpp'
original = normalize_marker(path.read_text())
marker = '// OrbisDesk W096: shared-process overlay lock.'
text = original

def replace_once(old, new):
    global text
    if text.count(old) != 1:
        raise SystemExit('MangoHud source mismatch: ' + old[:100])
    text = text.replace(old, new, 1)

if marker not in text:
    replace_once('std::mutex global_lock;', '''std::mutex global_lock;
// OrbisDesk W096: shared-process overlay lock.
// ImGui/ImPlot current contexts, HUDElements and configuration are DLL globals.
// Different Wine guests render on different threads in the same process.
// The object-map mutex alone never protected this state. Use a separate lock:
// calls below still acquire global_lock to look up their Vulkan objects.
static std::recursive_mutex orbis_overlay_mutex;''')

    # Protect initialization, frame construction/upload and destruction with the
    # SAME lock. Locking only NewFrame/Render misses context creation/font rebuild.
    for function in ('CreateInstance', 'DestroyInstance', 'CreateDevice',
                     'DestroyDevice', 'CreateSwapchainKHR', 'DestroySwapchainKHR',
                     'QueuePresentKHR'):
        pattern = r'(static (?:VkResult|void) overlay_' + function + r'\([^{}]*\)\s*\{)'
        text, count = re.subn(pattern, r'\1\n   std::unique_lock<std::recursive_mutex> orbis_ui_lock(orbis_overlay_mutex);', text)
        if count != 1:
            raise SystemExit('MangoHud hook mismatch: ' + function)

    replace_once('      VkResult chain_result = queue_data->device->vtable.QueuePresentKHR(queue, &present_info);',
                 '''      // The overlay commands are now recorded/submitted. Let other guests
      // build their HUD while the driver copies/presents this application's image.
      orbis_ui_lock.unlock();
      VkResult chain_result = queue_data->device->vtable.QueuePresentKHR(queue, &present_info);
      orbis_ui_lock.lock();''')

    # CreateContext changes the global current context, so save it BEFORE creation.
    replace_once('''   if (!data->imgui_contexts.imgui)
      data->imgui_contexts = create_imgui_contexts(data->font_atlas);
   auto saved_imgui_contexts = get_current_imgui_contexts();''',
                 '''   auto saved_imgui_contexts = get_current_imgui_contexts();
   if (!data->imgui_contexts.imgui)
      data->imgui_contexts = create_imgui_contexts(data->font_atlas);''')

    replace_once('''static void shutdown_swapchain_data(struct swapchain_data *data)
{
   struct device_data *device_data = data->device;''',
                 '''static void shutdown_swapchain_data(struct swapchain_data *data)
{
   // Font/context destruction must run with this swapchain's context selected.
   // Never restore the context we are about to destroy.
   auto saved_imgui_contexts = get_current_imgui_contexts();
   if (saved_imgui_contexts.imgui == data->imgui_contexts.imgui)
      saved_imgui_contexts.imgui = nullptr;
#ifdef IMPLOT_API
   if (saved_imgui_contexts.implot == data->imgui_contexts.implot)
      saved_imgui_contexts.implot = nullptr;
#endif
   make_imgui_contexts_current(data->imgui_contexts);
   struct device_data *device_data = data->device;''')

    replace_once('''   destroy_imgui_contexts(data->imgui_contexts);
}''', '''   destroy_imgui_contexts(data->imgui_contexts);
   make_imgui_contexts_current(saved_imgui_contexts);
}''')
    path.write_text(text)

# Re-running the patch must not silently accept partial edits.
if text.count('std::unique_lock<std::recursive_mutex> orbis_ui_lock(orbis_overlay_mutex);') != 7:
    raise SystemExit('Incomplete shared-process overlay guards')
expected_wait_boundaries = 4 if '// OrbisDesk W099: join outside the UI lock.' in text else 1
if text.count('orbis_ui_lock.unlock();') != expected_wait_boundaries or text.count('orbis_ui_lock.lock();') != expected_wait_boundaries:
    raise SystemExit('Incomplete downstream-present unlock/relock')
print(json.dumps({'patch': 'W096-shared-process-overlay', 'source': str(path),
                  'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                  'changed': original != text}))
