#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile the transformed Mesa empty-submit function against a deferred-queue host model.

Requires the pinned Mesa archive. Checks forwarding of binary/timeline dependencies,
no early signal, CPU fallback/error propagation and patch context/idempotency. Not a GPU test.
"""
import pathlib
import subprocess
import sys
import tarfile
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / '.deps/vk/mesa-26.0.8.tar.xz'

PRELUDE = r'''
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdarg.h>
#define __PS4__ 1
#define VK_SUCCESS 0
#define VK_SYNC_WAIT_COMPLETE 1
#define AMD_IP_GFX 0
typedef int VkResult;
struct ac_cmdbuf {int value;};
struct radv_cmd_stream {struct ac_cmdbuf *b;};
struct radeon_winsys_ctx {int value;};
struct sync {uint64_t point;};
struct radv_winsys_submit_info {int ip_type,queue_index;struct ac_cmdbuf **cs_array;unsigned cs_count;};
struct radeon_winsys {
 VkResult (*cs_submit)(struct radeon_winsys_ctx *,struct radv_winsys_submit_info *,unsigned,struct sync *,unsigned,struct sync *);
};
struct radv_device {int vk;struct radeon_winsys *ws;};
struct radv_queue {struct radv_device *device;struct radeon_winsys_ctx *hw_ctx;int ring;
 struct {int index_in_family;} vk;struct {struct radv_cmd_stream *flush_postamble_cs;} state;};
struct vk_queue_submit {unsigned wait_count,signal_count;struct sync *waits,*signals;};
static unsigned submit_calls,wait_calls,event_calls,last_cpu,last_waits,pending_signals;
static int submit_result,wait_result,gpu_complete,signal_complete;
static struct ac_cmdbuf *expected_cs;
static struct sync *expected_wait,*expected_signal;
static bool expect_async;
static uint64_t clock_value;
static struct radv_device *radv_queue_device(struct radv_queue *q) {return q->device;}
static int radv_queue_ring(struct radv_queue *q) {return q->ring;}
static uint64_t os_time_get_nano(void) {return ++clock_value;}
int pw_vk_perf_enabled(void) {return 1;}
void pw_vk_empty_submit_event(int cpu,unsigned waits,uint64_t ns,int result) {
 (void)result;assert(ns);++event_calls;last_cpu=cpu;last_waits=waits;
}
static void ac_ps4_trace(const char *format,...) {(void)format;}
static VkResult vk_sync_wait_many(int *device,unsigned count,struct sync *waits,int flags,uint64_t timeout) {
 (void)device;assert(count==1 && waits==expected_wait);assert(flags==VK_SYNC_WAIT_COMPLETE && timeout==UINT64_MAX);
 ++wait_calls;if(!wait_result)gpu_complete=1;return wait_result;
}
static VkResult mock_submit(struct radeon_winsys_ctx *ctx,struct radv_winsys_submit_info *info,
 unsigned waits,struct sync *wait,unsigned signals,struct sync *signal) {
 (void)ctx;++submit_calls;assert(signals==1 && signal==expected_signal);
 if(expect_async) {
  assert(info->cs_count==1 && *info->cs_array==expected_cs);
  assert(waits==1 && wait==expected_wait && !gpu_complete);
 } else {assert(!info->cs_count && !waits);}
 if(!submit_result)pending_signals=signals;
 return submit_result;
}
static void reset(void) {
 submit_calls=wait_calls=event_calls=last_cpu=last_waits=pending_signals=0;
 submit_result=wait_result=gpu_complete=signal_complete=0;
 unsetenv("ORBISDESK_EMPTY_SUBMIT_CPU");
}
'''
MAIN = r'''
int main(void) {
 struct ac_cmdbuf buffer={1};struct radv_cmd_stream flush={&buffer};
 struct radeon_winsys ws={mock_submit};struct radv_device device={0,&ws};
 struct radeon_winsys_ctx ctx={0};struct radv_queue q={&device,&ctx,AMD_IP_GFX,{2},{&flush}};
 struct sync wait={0},signal={0};struct vk_queue_submit submission={1,1,&wait,&signal};
 expected_cs=&buffer;expected_wait=&wait;expected_signal=&signal;
 for(unsigned kind=0;kind<2;++kind) { /* binary and a future timeline point */
  reset();wait.point=kind?42:0;expect_async=true;
  if(kind)setenv("ORBISDESK_EMPTY_SUBMIT_CPU","0",1); /* launcher's explicit default */
  assert(radv_queue_submit_empty(&q,&submission)==VK_SUCCESS);
  assert(submit_calls==1 && !wait_calls && pending_signals==1 && !signal_complete);
  assert(event_calls==1 && !last_cpu && last_waits==1);
  gpu_complete=1;if(gpu_complete && pending_signals)signal_complete=1;
  assert(signal_complete);
 }
 reset();expect_async=false;setenv("ORBISDESK_EMPTY_SUBMIT_CPU","1",1);
 assert(!radv_queue_submit_empty(&q,&submission));assert(wait_calls==1 && last_cpu==1 && gpu_complete);
 reset();expect_async=false;q.state.flush_postamble_cs=NULL;
 assert(!radv_queue_submit_empty(&q,&submission));assert(wait_calls==1 && last_cpu==1);q.state.flush_postamble_cs=&flush;
 reset();expect_async=false;q.ring=1;
 assert(!radv_queue_submit_empty(&q,&submission));assert(wait_calls==1 && last_cpu==1);q.ring=AMD_IP_GFX;
 reset();expect_async=false;setenv("ORBISDESK_EMPTY_SUBMIT_CPU","1",1);wait_result=-4;
 assert(radv_queue_submit_empty(&q,&submission)==-4);assert(!submit_calls && !pending_signals && last_cpu==1);
 reset();expect_async=true;submit_result=-7;
 assert(radv_queue_submit_empty(&q,&submission)==-7);assert(submit_calls==1 && !wait_calls && !pending_signals);
 reset();expect_async=false;submission.wait_count=0;
 assert(!radv_queue_submit_empty(&q,&submission));assert(submit_calls==1 && !wait_calls && !event_calls);
 puts("PASS: empty-submit dependency forwarding, deferred signals, CPU fallback and failures");
}
'''

def main():
    with tempfile.TemporaryDirectory() as temp:
        base = pathlib.Path(temp)
        target = base / 'src/amd/vulkan/radv_queue.c'
        target.parent.mkdir(parents=True)
        with tarfile.open(ARCHIVE) as archive:
            target.write_bytes(archive.extractfile('mesa-26.0.8/src/amd/vulkan/radv_queue.c').read())
        for name in ['patch-mesa-empty-submit.py', 'patch-mesa-async-empty-submit.py']:
            subprocess.run([sys.executable, str(ROOT/'tools/vk-h0'/name), str(base)], check=True)
        patched = target.read_text()
        script = ROOT/'tools/vk-h0/patch-mesa-async-empty-submit.py'
        subprocess.run([sys.executable,str(script),str(base)],check=True)
        assert target.read_text() == patched
        function = patched[patched.index('static VkResult\nradv_queue_submit_empty('):patched.index('static void\nradv_set_ring_buffer(')]
        source = base/'check.c';source.write_text(PRELUDE+function+MAIN)
        subprocess.run(['cc','-O2','-Wall','-Wextra','-Werror',str(source),'-o',str(base/'check')],check=True)
        subprocess.run([str(base/'check')],check=True)
        target.write_text(patched.replace('OrbisDesk asynchronous empty GFX submit v1','removed').replace('if (submission->wait_count)', 'if (0)'))
        assert subprocess.run([sys.executable,str(script),str(base)],capture_output=True).returncode != 0
    return 0

if __name__ == '__main__':
    sys.exit(main())
