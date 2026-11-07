#!/usr/bin/env python3
"""W099: don't hold shared UI state while joining a Windows DLL worker.

Build-copy patch on top of W096. Keep upstream and previous release DLLs intact.
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
marker = '// OrbisDesk W099: join outside the UI lock.'
changed = []

def patch(relative, signature, replacements):
    path = root / relative
    text = normalize_marker(path.read_text())
    if signature in text:
        return
    for old, new in replacements:
        if text.count(old) != 1:
            raise SystemExit('MangoHud teardown context mismatch: ' + relative + ': ' + old[:100])
        text = text.replace(old, new, 1)
    if signature not in text:
        raise SystemExit('Missing teardown marker: ' + relative)
    path.write_text(text)
    changed.append(relative)

patch('src/vulkan.cpp', marker, [
    ('''   shutdown_swapchain_data(swapchain_data);
   swapchain_data->device->vtable.DestroySwapchainKHR(device, swapchain, pAllocator);
   destroy_swapchain_data(swapchain_data);''', '''   shutdown_swapchain_data(swapchain_data);
   orbis_ui_lock.unlock();
   OutputDebugStringA("PWHUD destroy_swapchain downstream begin");
   swapchain_data->device->vtable.DestroySwapchainKHR(device, swapchain, pAllocator);
   OutputDebugStringA("PWHUD destroy_swapchain downstream end");
   orbis_ui_lock.lock();
   destroy_swapchain_data(swapchain_data);'''),
    ('''   device_data->vtable.DestroyDevice(device, pAllocator);
   destroy_device_data(device_data);''', '''   orbis_ui_lock.unlock();
   OutputDebugStringA("PWHUD destroy_device downstream begin");
   device_data->vtable.DestroyDevice(device, pAllocator);
   OutputDebugStringA("PWHUD destroy_device downstream end");
   orbis_ui_lock.lock();
   destroy_device_data(device_data);'''),
    ('''   instance_data->vtable.DestroyInstance(instance, pAllocator);
   if (!is_blacklisted())
      stop_notifier(instance_data->notifier);
   destroy_instance_data(instance_data);''', '''   // OrbisDesk W099: join outside the UI lock.
   // A Windows worker exits through DLL_THREAD_DETACH (including user32).
   // Never keep the render/UI lock while waiting for that work or for the ICD.
   orbis_ui_lock.unlock();
   OutputDebugStringA("PWHUD destroy_instance notifier begin");
   if (!is_blacklisted())
      stop_notifier(instance_data->notifier);
   OutputDebugStringA("PWHUD destroy_instance notifier end");
   OutputDebugStringA("PWHUD destroy_instance downstream begin");
   instance_data->vtable.DestroyInstance(instance, pAllocator);
   OutputDebugStringA("PWHUD destroy_instance downstream end");
   orbis_ui_lock.lock();
   destroy_instance_data(instance_data);'''),
])

# The quit flag is read by one thread and written by another.
patch('src/notify.h', '// OrbisDesk W099: atomic shutdown request.', [
    ('#include <thread>', '#include <thread>\n#include <atomic>'),
    ('    bool quit = false;', '    // OrbisDesk W099: atomic shutdown request.\n    std::atomic<bool> quit{false};'),
])

patch('src/notify_win32.cpp', '// OrbisDesk W099: service sent messages while joining.', [
    ('''    nt.quit = false;

    if (nt.thread.joinable())
        nt.thread.join();''', '''    if (nt.thread.joinable())
        stop_notifier(nt);
    nt.quit = false;'''),
    ('''    if (nt.thread.joinable())
        nt.thread.join();
}''', '''    // OrbisDesk W099: service sent messages while joining.
    // libc++'s Windows backend uses a Win32 HANDLE as its native thread handle.
    // Only dispatch synchronous sent messages, never queued clicks/commands:
    // user32's DLL_THREAD_DETACH may need another GUI thread to answer a send.
    if (!nt.thread.joinable()) return;
    static_assert(std::is_same<std::thread::native_handle_type, HANDLE>::value,
                  "Orbis MangoHud requires libc++'s Windows thread backend");
    HANDLE handle = nt.thread.native_handle();
    OutputDebugStringA("PWHUD notifier_join begin");
    for (;;)
    {
        DWORD result = MsgWaitForMultipleObjectsEx(1, &handle, INFINITE,
                                                  QS_SENDMESSAGE, MWMO_INPUTAVAILABLE);
        if (result == WAIT_OBJECT_0) break;
        if (result != WAIT_OBJECT_0 + 1)
        {
            // Preserve the actual join/failure instead of declaring it complete.
            OutputDebugStringA("PWHUD notifier_join wait failed");
            break;
        }
        MSG message;
        OutputDebugStringA("PWHUD notifier_join service sent messages");
        PeekMessageW(&message, nullptr, 0, 0, PM_NOREMOVE | PM_QS_SENDMESSAGE);
    }
    nt.thread.join();
    OutputDebugStringA("PWHUD notifier_join end");
}'''),
    ('#include <thread>', '#include <thread>\n#include <type_traits>'),
])

print(json.dumps({'patch': 'W099-MangoHud-teardown', 'changed': changed,
    'sources': {name: hashlib.sha256((root/name).read_bytes()).hexdigest()
                for name in ('src/vulkan.cpp', 'src/notify.h', 'src/notify_win32.cpp')}}))
