#!/usr/bin/env python3
"""Extend Crema GPU timestamps to a union across the title's ordered GFX jobs.
No new thread, no blocking telemetry capacity, no CPU fence time used as GPU work.
"""
import argparse,hashlib,json,pathlib
parser=argparse.ArgumentParser();parser.add_argument('source',type=pathlib.Path)
path=parser.parse_args().source
text=path.read_text();marker='/* OrbisDesk W103: title-wide GFX timestamp union.\n'
if marker not in text and marker.replace('OrbisDesk', 'Orbis-win') not in text:
    def replace(old,new):
        global text
        if text.count(old)!=1:raise SystemExit('Crema telemetry context changed: '+old[:100])
        text=text.replace(old,new,1)
    replace('   uint64_t ts_accounted, ts_prev_end, ts_busy, ts_span_first, ts_span_last;',
            '   uint64_t ts_accounted, ts_prev_end, ts_busy, ts_span_first, ts_span_last;\n   uint64_t *pw_stats_sequence;')
    replace('         dev->ts_ibs = (uint32_t *)(ts + FENCE_IB_COUNT * 16);',
            '         dev->ts_ibs = (uint32_t *)(ts + FENCE_IB_COUNT * 16);\n         dev->pw_stats_sequence = calloc(FENCE_IB_COUNT, sizeof(uint64_t));')
    replace('      dev->ts_start[ts_slot] = 0;',
            '      if (dev->pw_stats_sequence) __atomic_store_n(&dev->pw_stats_sequence[ts_slot], seq, __ATOMIC_RELEASE);\n      dev->ts_start[ts_slot] = 0;')
    insert='''/* OrbisDesk W103: title-wide GFX timestamp union.
 * Crema's per-device timestamps are kept. The common submit thread publishes
 * jobs in the order used by the sole GFX queue; consume only its completed
 * prefix, so intervals are merged in GPU start order even across VkDevices.
 * Devices currently live until title exit (ac_drm_device_deinitialize).
 */
#define PW_GPU_EVENTS 4096
static struct { ac_drm_device *dev; uint64_t seq; } pw_gpu_events[PW_GPU_EVENTS];
static uint64_t pw_gpu_head, pw_gpu_tail, pw_gpu_busy, pw_gpu_first, pw_gpu_end;
static uint64_t pw_gpu_last_start, pw_gpu_lost;
static simple_mtx_t pw_gpu_lock = SIMPLE_MTX_INITIALIZER;

/* pw_gpu_lock held; never acquire a device/job lock, allocate or call Windows. */
static void pw_gpu_account(void)
{
   while (pw_gpu_head < pw_gpu_tail) {
      ac_drm_device *dev = pw_gpu_events[pw_gpu_head % PW_GPU_EVENTS].dev;
      const uint64_t seq = pw_gpu_events[pw_gpu_head % PW_GPU_EVENTS].seq;
      const unsigned slot = seq % FENCE_IB_COUNT;
      if (ps4_completed(dev) < seq) break;
      const uint64_t generation = __atomic_load_n(&dev->pw_stats_sequence[slot], __ATOMIC_ACQUIRE);
      const uint64_t start = dev->ts_start[slot], end = dev->ts_end[slot];
      pw_gpu_head++;
      if (generation != seq || __atomic_load_n(&dev->pw_stats_sequence[slot], __ATOMIC_ACQUIRE) != seq ||
          !start || end <= start || start < pw_gpu_last_start) {
         pw_gpu_lost++;
         continue;
      }
      pw_gpu_last_start = start;
      const uint64_t from = MAX2(start, pw_gpu_end);
      if (end > from) pw_gpu_busy += end - from;
      if (!pw_gpu_first) pw_gpu_first = start;
      pw_gpu_end = MAX2(end, pw_gpu_end);
   }
}

static void pw_gpu_record(ac_drm_device *dev, uint64_t seq, int result)
{
   simple_mtx_lock(&pw_gpu_lock);
   pw_gpu_account();
   if (result || !dev->ts_start || !dev->pw_stats_sequence) {
      pw_gpu_lost++;
   } else {
      if (pw_gpu_tail - pw_gpu_head == PW_GPU_EVENTS) { pw_gpu_head++; pw_gpu_lost++; }
      pw_gpu_events[pw_gpu_tail % PW_GPU_EVENTS].dev = dev;
      pw_gpu_events[pw_gpu_tail % PW_GPU_EVENTS].seq = seq;
      pw_gpu_tail++;
   }
   simple_mtx_unlock(&pw_gpu_lock);
}

void ac_ps4_get_gpu_app_busy(uint64_t *busy, uint64_t *span, uint64_t *lost);
void ac_ps4_get_gpu_app_busy(uint64_t *busy, uint64_t *span, uint64_t *lost)
{
   simple_mtx_lock(&pw_gpu_lock);
   pw_gpu_account();
   *busy = pw_gpu_busy;
   *span = pw_gpu_first ? pw_gpu_end - pw_gpu_first : 0;
   *lost = pw_gpu_lost;
   simple_mtx_unlock(&pw_gpu_lock);
}

'''
    replace('static void *\nps4_submit_thread(void *arg)',insert+'static void *\nps4_submit_thread(void *arg)')
    replace('      /* sceGnmSubmitDone tells the system the frame\'s work is in',
            '      if (!job->flip) pw_gpu_record(dev, job->seq, r);\n      /* sceGnmSubmitDone tells the system the frame\'s work is in')
    path.write_text(text)
print(json.dumps({'patch':'W103-crema-title-gpu-metrics','source':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}))
