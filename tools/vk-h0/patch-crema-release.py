#!/usr/bin/env python3
"""OrbisDesk alpha-1 (run-0215, run-0219): a Crema device gives back its freed buffers once nothing can submit.

Crema (ac_ps4_drm.c, OrbisDesk's copy in the Mesa tree) frees a buffer only after the GPU has finished every
submission made before it, and then still keeps the newest PS4_QUARANTINE_BYTES (96 MB) of freed buffers mapped
against late GPU writes through stale descriptors. Each RADV winsys has its own Crema device (one per VkInstance's
physical device). In OrbisDesk's shared process a program that ends leaves its Crema device behind with that
quarantine. run-0215 (04.17: GTA San Andreas, exit status 0) lost 0.47 and 0.39 GB of direct memory that was not
Wine's own commits after its device memory had been freed.

- Queues: RADV makes a context for each queue (ac_drm_cs_ctx_create2) and frees it when the queue goes
  (ac_drm_cs_ctx_free); Crema's contexts were empty. A device now counts them. While it has none, no VkDevice is
  using it and nothing can submit, so a stale write is not possible: the quarantine goes, and each later free runs
  as soon as its last submission has finished. The VkDevice's own buffers, freed by vkDestroyDevice after its
  queues, go back then. "radv/ps4: device ... has no queues: gave back N bytes" gives the quarantine given back.
- Its end (ac_drm_device_deinitialize, when the winsys ends with its instance) did nothing. It now waits up to
  1.5 s for the last submission and runs every deferred unmap, free and address range free. Buffers still in the
  table stay (run-0219): freeing them would need their GPU mappings taken down first.

The device structure, its fence page and its address windows stay: W103's GPU time records keep the pointer.

Run by tools/vk-h0/build-mesa.sh (VARIANT=wine) after patch-crema-traces.py, on a fresh copy of ac_ps4_drm.c.
"""
import argparse, pathlib
parser = argparse.ArgumentParser(); parser.add_argument('source', type=pathlib.Path)
path = parser.parse_args().source
text = path.read_text()
marker = '/* OrbisDesk alpha-1 (run-0219): queues */'
if marker not in text:
    edits = [
        ('''   unsigned num_deferred, deferred_cap;
''', '''   unsigned num_deferred, deferred_cap;
   /* OrbisDesk alpha-1 (run-0219): queues */
   unsigned pw_contexts; /* RADV's contexts (one per queue) not freed yet; none: nothing can submit */
'''),
        ('''void
ac_drm_device_deinitialize(ac_drm_device *dev)
{
   /* The device lives for the whole process. */
   (void)dev;
}''', '''void
ac_drm_device_deinitialize(ac_drm_device *dev)
{
   /* OrbisDesk alpha-1 (run-0215): the winsys ended (its instance was destroyed, after all its VkDevices), so
    * nothing submits through this device again. Once its last submission has finished, the deferred unmaps and
    * frees run, the quarantine included. Buffers still in the table stay (run-0219: their GPU mappings would
    * have to go first). The structure, its fence page and its address windows stay (W103's GPU time records keep
    * the pointer). */
   if (!dev || !dev->fence)
      return;
   if (dev->last_seq && !ps4_wait_seq(dev, dev->last_seq, os_time_get_nano() + 1500000000ll)) {
      ps4_log("radv/ps4: device %p ended with submissions unfinished (%llu of %llu): its freed buffers are "
              "kept\\n", (void *)dev, (unsigned long long)ps4_completed(dev), (unsigned long long)dev->last_seq);
      return;
   }
   simple_mtx_lock(&dev->lock);
   const uint64_t before = __atomic_load_n(&dev->bo_bytes, __ATOMIC_RELAXED);
   ps4_run_deferred_ex(dev, 0);
   const uint64_t after = __atomic_load_n(&dev->bo_bytes, __ATOMIC_RELAXED);
   const uint64_t left = __atomic_load_n(&dev->bo_count, __ATOMIC_RELAXED);
   const unsigned waiting = dev->num_deferred;
   simple_mtx_unlock(&dev->lock);
   if (before != after || left || waiting)
      ps4_log("radv/ps4: device %p ended: gave back %llu bytes; %llu bytes in %llu buffers its users left are "
              "kept, %u operations still wait\\n", (void *)dev, (unsigned long long)(before - after),
              (unsigned long long)after, (unsigned long long)left, waiting);
}'''),
        ('''int
ac_drm_cs_ctx_create2(ac_drm_device *dev, uint32_t priority, uint32_t *ctx_id)
{
   *ctx_id = 1;
   return 0;
}

int
ac_drm_cs_ctx_free(ac_drm_device *dev, uint32_t ctx_id)
{
   return 0;
}''', '''int
ac_drm_cs_ctx_create2(ac_drm_device *dev, uint32_t priority, uint32_t *ctx_id)
{
   *ctx_id = 1;
   simple_mtx_lock(&dev->lock);
   dev->pw_contexts++; /* OrbisDesk alpha-1 (run-0219) */
   simple_mtx_unlock(&dev->lock);
   return 0;
}

int
ac_drm_cs_ctx_free(ac_drm_device *dev, uint32_t ctx_id)
{
   /* OrbisDesk alpha-1 (run-0219): the last queue went, so nothing submits through this device until a new queue
    * comes. The quarantine (kept against stale writes of later submissions) goes: whatever the GPU has finished
    * is given back now. */
   simple_mtx_lock(&dev->lock);
   if (dev->pw_contexts)
      dev->pw_contexts--;
   uint64_t before = 0, after = 0;
   if (!dev->pw_contexts) {
      before = __atomic_load_n(&dev->bo_bytes, __ATOMIC_RELAXED);
      ps4_run_deferred_ex(dev, 0);
      after = __atomic_load_n(&dev->bo_bytes, __ATOMIC_RELAXED);
   }
   simple_mtx_unlock(&dev->lock);
   if (before != after)
      ps4_log("radv/ps4: device %p has no queues: gave back %llu bytes; %llu bytes in buffers now\\n", (void *)dev,
              (unsigned long long)(before - after), (unsigned long long)after);
   return 0;
}'''),
        ('''   dev->deferred[dev->num_deferred++] = d;
   ps4_run_deferred(dev);
   simple_mtx_unlock(&dev->lock);''', '''   dev->deferred[dev->num_deferred++] = d;
   /* OrbisDesk alpha-1 (run-0219): with no queue, nothing can write through a stale descriptor: no quarantine */
   ps4_run_deferred_ex(dev, dev->pw_contexts ? PS4_QUARANTINE_BYTES : 0);
   simple_mtx_unlock(&dev->lock);'''),
    ]
    for old, new in edits:
        if text.count(old) != 1:
            raise SystemExit('Crema context changed: %r' % old[:60])
        text = text.replace(old, new, 1)
    path.write_text(text)
