#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""04.35 (docs/SHADER_CACHE.md): a queue submission with no command buffers but with semaphores to wait on (Crema's
tree, VARIANT=wine only, __PS4__ only).

RADV sends such a submission to radv_amdgpu_cs_submit_zero, which on Linux merges the waits into the queue's syncobj
through sync files (ac_drm_cs_syncobj_export_sync_file / _export_sync_file2 / _import_sync_file). Crema has no sync
files: those three return -ENOSYS (src/amd/common/ac_ps4_drm.c), and radv_amdgpu_cs_submit_zero turns that into
VK_ERROR_DEVICE_LOST, without a line in the log. The only exception is a timeline point the GPU has already finished.
So a binary wait always lost the device, and a timeline wait lost it whenever the GPU was still working on the point:
a race, a few frames in. DXVK (Alan Wake on 04.08 and 04.33, POP, Left 4 Dead 2, runs 0115, 0165, 0197, 0210, 0217,
0266, 0277) printed "radv/amdgpu: Failed to query the last GPUVM fault (-22)" (Crema has no GPUVM fault query
either), then "DxvkSubmissionQueue: Command submission failed: VK_ERROR_DEVICE_LOST", and no "radv: ... -> fail" line.
Every other failing step of a submission prints one.

Here, on the PS4, an empty submission first waits on the CPU until its semaphores have signalled, as RADV's own sparse
binding submission does (radv_queue_sparse_submit). It then signals its semaphores from the queue's last submission,
which Crema supports (ps4_transfer). The vk_queue runtime calls the driver only once every wait has been submitted, and
Crema's single GPU queue runs submissions in order, so the wait ends. A submission that still fails prints one line with
its result and counts, so a device loss names its cause in the log.
patch-mesa-empty-submit.py <mesa source>"""
import sys as _brand_sys
from pathlib import Path as _BrandPath
_brand_sys.path.insert(0,str(_BrandPath(__file__).resolve().parents[1]))
from project_brand import normalize_marker

import pathlib,sys
mesa=pathlib.Path(sys.argv[1])
MARK='OrbisDesk 04.35 empty submit'
path='src/amd/vulkan/radv_queue.c'
target=mesa/path;text=normalize_marker(target.read_text())
if MARK in text:
    print(path,'already patched');raise SystemExit(0)
edits=[
('''      .queue_index = queue->vk.index_in_family,
   };

   return device->ws->cs_submit(ctx, &submit, submission->wait_count, submission->waits, submission->signal_count,
                                submission->signals);
}''','''      .queue_index = queue->vk.index_in_family,
   };

#ifdef __PS4__ /* '''+MARK+''': Crema has no sync files, which radv_amdgpu_cs_submit_zero merges waits with */
   if (submission->wait_count) {
      VkResult wait = vk_sync_wait_many(&device->vk, submission->wait_count, submission->waits, VK_SYNC_WAIT_COMPLETE,
                                        UINT64_MAX);
      if (wait != VK_SUCCESS) {
         ac_ps4_trace("radv: empty submission, CPU wait on %u semaphores = %d\\n", submission->wait_count, wait);
         return wait;
      }
      return device->ws->cs_submit(ctx, &submit, 0, NULL, submission->signal_count, submission->signals);
   }
#endif
   return device->ws->cs_submit(ctx, &submit, submission->wait_count, submission->waits, submission->signal_count,
                                submission->signals);
}'''),
('''      result = radv_queue_submit_normal(queue, submission);
   }

fail:
   if (result != VK_SUCCESS) {''','''      result = radv_queue_submit_normal(queue, submission);
   }

fail:
#ifdef __PS4__ /* '''+MARK+''': every failed submission says so (most steps had no line, see the patcher) */
   if (result != VK_SUCCESS)
      ac_ps4_trace("radv: vkQueueSubmit = %d: %u command buffers, %u waits, %u signals\\n", result,
                   submission->command_buffer_count, submission->wait_count, submission->signal_count);
#endif
   if (result != VK_SUCCESS) {'''),
]
for old,new in edits:
    if text.count(old)!=1:raise SystemExit('Unexpected context in '+path+': '+old[:70])
    text=text.replace(old,new,1)
target.write_text(text);print(path,'patched')
