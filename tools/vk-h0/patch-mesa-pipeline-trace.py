#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""04.27 (docs/SHADER_CACHE.md): RADV notes each pipeline or shader-object create to OrbisDesk's sink.

Every vkCreateGraphicsPipelines (full and library), vkCreateComputePipelines and vkCreateShadersEXT create is timed
and handed to pw_vk_pipeline_note (platform/ps4/pw_wine_sink_ps4.c), a weak symbol: a link without the sink calls
nothing. Each note says whether RADV found the pipeline in a cache (memory or disk) and whether it read it from the
disk cache. DXVK's, Zink's and native Vulkan programs' pipelines all reach RADV in the title process, so the sink's
PWPERF line covers them all. The PS4 build also says once whether its disk shader cache is on, and where.
Nothing changes behaviour.  patch-mesa-pipeline-trace.py <mesa source>"""
import sys as _brand_sys
from pathlib import Path as _BrandPath
_brand_sys.path.insert(0,str(_BrandPath(__file__).resolve().parents[1]))
from project_brand import normalize_marker

import pathlib,sys
mesa=pathlib.Path(sys.argv[1])
MARK='OrbisDesk 04.27 pipeline trace'

HEADER='''/* OrbisDesk 04.27 pipeline trace (tools/vk-h0/patch-mesa-pipeline-trace.py, docs/SHADER_CACHE.md): each
 * create's time, and whether a cache had it, for the sink's PWPERF line. pw_vk_pipeline_note is weak: a link
 * without platform/ps4/pw_wine_sink_ps4.c calls nothing. */
#ifndef PW_PIPELINE_TRACE_H
#define PW_PIPELINE_TRACE_H
#include <stdint.h>
#include "util/os_time.h"
enum {PW_PIPELINE_GFX, PW_PIPELINE_LIB, PW_PIPELINE_COMPUTE, PW_PIPELINE_SHADER_OBJECT};
/* set on the creating thread: radv_pipeline_cache.c (found in a cache), vk_pipeline_cache.c (read from disk) */
extern __thread unsigned pw_vk_cache_found, pw_vk_cache_disk;
void pw_vk_pipeline_note(unsigned kind, uint64_t ns, unsigned flags) __attribute__((weak));
static inline int64_t
pw_pipeline_trace_begin(void)
{
   pw_vk_cache_found = 0;
   pw_vk_cache_disk = 0;
   return os_time_get_nano();
}
static inline void
pw_pipeline_trace_end(unsigned kind, int64_t start)
{
   if (pw_vk_pipeline_note)
      pw_vk_pipeline_note(kind, (uint64_t)(os_time_get_nano() - start),
                          (pw_vk_cache_found ? 1u : 0u) | (pw_vk_cache_disk ? 2u : 0u));
}
#endif
'''

def patch(path,edits):
    target=mesa/path;text=normalize_marker(target.read_text())
    if MARK in text:
        print(path,'already traced');return
    for old,new in edits:
        if text.count(old)!=1:raise SystemExit('Unexpected context in '+path+': '+old[:70])
        text=text.replace(old,new,1)
    target.write_text(text);print(path,'traced')

header=mesa/'src/amd/vulkan/pw_pipeline_trace.h'
if not header.exists() or header.read_text()!=HEADER:
    header.write_text(HEADER)

INCLUDE='#include "pw_pipeline_trace.h" /* '+MARK+' */\n'

patch('src/amd/vulkan/radv_pipeline_graphics.c',[
('#include "util/os_time.h"\n','#include "util/os_time.h"\n'+INCLUDE),
('''      VkResult r;
      if (create_flags & VK_PIPELINE_CREATE_2_LIBRARY_BIT_KHR) {
         r = radv_graphics_lib_pipeline_create(_device, pipelineCache, &pCreateInfos[i], pAllocator, &pPipelines[i]);
      } else {
         r = radv_graphics_pipeline_create(_device, pipelineCache, &pCreateInfos[i], pAllocator, &pPipelines[i]);
      }
''','''      VkResult r;
      const int64_t pw_start = pw_pipeline_trace_begin();
      if (create_flags & VK_PIPELINE_CREATE_2_LIBRARY_BIT_KHR) {
         r = radv_graphics_lib_pipeline_create(_device, pipelineCache, &pCreateInfos[i], pAllocator, &pPipelines[i]);
      } else {
         r = radv_graphics_pipeline_create(_device, pipelineCache, &pCreateInfos[i], pAllocator, &pPipelines[i]);
      }
      pw_pipeline_trace_end(create_flags & VK_PIPELINE_CREATE_2_LIBRARY_BIT_KHR ? PW_PIPELINE_LIB : PW_PIPELINE_GFX,
                            pw_start);
'''),
])

patch('src/amd/vulkan/radv_pipeline_compute.c',[
('#include "util/os_time.h"\n','#include "util/os_time.h"\n'+INCLUDE),
('''      r = radv_compute_pipeline_create(_device, pipelineCache, &pCreateInfos[i], pAllocator, &pPipelines[i]);
''','''      const int64_t pw_start = pw_pipeline_trace_begin();
      r = radv_compute_pipeline_create(_device, pipelineCache, &pCreateInfos[i], pAllocator, &pPipelines[i]);
      pw_pipeline_trace_end(PW_PIPELINE_COMPUTE, pw_start);
'''),
])

# the whole call: DXVK and Zink do not use shader objects today, but a native program may
patch('src/amd/vulkan/radv_shader_object.c',[
('''   VkResult final_result = VK_SUCCESS;

   /* From the Vulkan 1.3.274 spec:''','''   VkResult final_result = VK_SUCCESS;
   const int64_t pw_start = pw_pipeline_trace_begin(); /* '''+MARK+''' */

   /* From the Vulkan 1.3.274 spec:'''),
('''   return final_result;
}

static size_t
radv_get_shader_binary_size(''','''   pw_pipeline_trace_end(PW_PIPELINE_SHADER_OBJECT, pw_start);
   return final_result;
}

static size_t
radv_get_shader_binary_size('''),
('#include "radv_shader_object.h"\n','#include "radv_shader_object.h"\n'+INCLUDE),
])

# found in a cache: the pipeline object search every graphics, library and compute create makes first
patch('src/amd/vulkan/radv_pipeline_cache.c',[
('#include "radv_pipeline_cache.h"\n','#include "radv_pipeline_cache.h"\n'+INCLUDE+'__thread unsigned pw_vk_cache_found;\n'),
('''   radv_report_pso_cache_stats(device, pipeline, !!object);

   if (!object)
      return NULL;
''','''   radv_report_pso_cache_stats(device, pipeline, !!object);

   if (!object)
      return NULL;
   pw_vk_cache_found = 1;
'''),
])

# read from the disk cache (Mesa's runtime, shared by every Vulkan driver it builds: only RADV here)
patch('src/vulkan/runtime/vk_pipeline_cache.c',[
('#include "util/disk_cache.h"\n','#include "util/disk_cache.h"\n/* '+MARK+': set when an object came from the disk cache (src/amd/vulkan/pw_pipeline_trace.h) */\n'
 '__thread unsigned pw_vk_cache_disk;\n'),
('''            free(data);
            if (object != NULL) {
               return vk_pipeline_cache_insert_object(cache, object);''','''            free(data);
            if (object != NULL) {
               pw_vk_cache_disk = 1;
               return vk_pipeline_cache_insert_object(cache, object);'''),
])

# once per physical device: is the disk cache on, and where (a cache that could not open its files says so)
patch('src/amd/vulkan/radv_physical_device.c',[
('#include "util/disk_cache.h"\n','#include "util/disk_cache.h"\n#ifdef __PS4__ /* '+MARK+' */\n#include <unistd.h>\n'
 '#ifdef ENABLE_SHADER_CACHE\n#include "util/disk_cache_os.h"\n#endif\n#endif\n'),
('''   pdev->vk.disk_cache = disk_cache_create(pdev->name, buf, 0);
''','''   pdev->vk.disk_cache = disk_cache_create(pdev->name, buf, 0);
#ifdef __PS4__ /* '''+MARK+''' */
#ifdef ENABLE_SHADER_CACHE
   {
      const struct disk_cache *pw_cache = pdev->vk.disk_cache;
      fprintf(stderr, "PWCACHE radv disk_cache=%s type=%d path=%s max_mb=%llu uid=%d euid=%d\\n",
              !pw_cache ? "none" : pw_cache->path_init_failed ? "failed" : "on", pw_cache ? (int)pw_cache->type : -1,
              pw_cache && pw_cache->path ? pw_cache->path : "-",
              pw_cache ? (unsigned long long)(pw_cache->max_size >> 20) : 0ull, (int)getuid(), (int)geteuid());
   }
#else
   fprintf(stderr, "PWCACHE radv disk_cache=not-built\\n");
#endif
#endif
'''),
])
