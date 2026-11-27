#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Keep empty PS4 GFX submissions asynchronous using the queue's immutable flush CS.

Apply after patch-mesa-empty-submit.py. The regular winsys path forwards all waits/signals
to Crema's in-order submission queue instead of waiting for GPU completion on the CPU.
Other rings, a missing flush CS and the explicit CPU control retain the 04.35 path.
"""
import pathlib
import sys

path = pathlib.Path(sys.argv[1]) / 'src/amd/vulkan/radv_queue.c'
text = path.read_text()
marker = 'OrbisDesk asynchronous empty GFX submit v1'
if marker in text:
    print(path, 'already patched')
    raise SystemExit(0)
old = '''   if (submission->wait_count) {
      VkResult wait = vk_sync_wait_many(&device->vk, submission->wait_count, submission->waits, VK_SYNC_WAIT_COMPLETE,
                                        UINT64_MAX);
      if (wait != VK_SUCCESS) {
         ac_ps4_trace("radv: empty submission, CPU wait on %u semaphores = %d\\n", submission->wait_count, wait);
         return wait;
      }
      return device->ws->cs_submit(ctx, &submit, 0, NULL, submission->signal_count, submission->signals);
   }'''
new = '''   /* OrbisDesk asynchronous empty GFX submit v1. The GFX7 queue already owns this
    * finalized cache-flush CS until queue teardown. A real IB takes the normal winsys
    * submission path, which preserves the waits and signals without sync-file merging.
    * Crema enqueues behind submitted prerequisites on its single ordered hardware queue.
    * Do not drop waits or signal from the CPU before the prerequisite GPU work completes. */
   if (submission->wait_count) {
      extern int pw_vk_perf_enabled(void);
      extern void pw_vk_empty_submit_event(int, unsigned, uint64_t, int);
      const uint64_t start = pw_vk_perf_enabled() ? os_time_get_nano() : 0;
      const char *control = getenv("ORBISDESK_EMPTY_SUBMIT_CPU");
      const bool cpu = control && control[0] == '1';
      VkResult result;
      if (!cpu && submit.ip_type == AMD_IP_GFX && queue->state.flush_postamble_cs) {
         struct ac_cmdbuf *cs = queue->state.flush_postamble_cs->b;
         submit.cs_array = &cs;
         submit.cs_count = 1;
         result = device->ws->cs_submit(ctx, &submit, submission->wait_count, submission->waits,
                                       submission->signal_count, submission->signals);
         if (start)
            pw_vk_empty_submit_event(0, submission->wait_count, os_time_get_nano() - start, result);
         return result;
      }
      result = vk_sync_wait_many(&device->vk, submission->wait_count, submission->waits, VK_SYNC_WAIT_COMPLETE,
                                UINT64_MAX);
      if (result == VK_SUCCESS)
         result = device->ws->cs_submit(ctx, &submit, 0, NULL, submission->signal_count, submission->signals);
      if (start)
         pw_vk_empty_submit_event(1, submission->wait_count, os_time_get_nano() - start, result);
      if (result != VK_SUCCESS)
         ac_ps4_trace("radv: empty submission CPU fallback = %d\\n", result);
      return result;
   }'''
if text.count(old) != 1:
    raise SystemExit('Unexpected 04.35 empty-submit context: ' + str(path))
# os_time_get_nano is used only for optional summaries.
if '#include "util/os_time.h"' not in text:
    text = '#include "util/os_time.h"\n' + text
text = text.replace(old, new)
path.write_text(text)
print(path, 'patched')
