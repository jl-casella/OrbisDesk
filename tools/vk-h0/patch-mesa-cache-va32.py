#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""04.32 (docs/SHADER_CACHE.md): RADV's cache identity includes the device's 32-bit GPU window (Crema's tree,
VARIANT=wine only, __PS4__ only).

RADV and ACO bake pdev->info.address32_hi into shader code: the upper half of every pointer built from a 32-bit
descriptor set, push constant or ring address (radv_nir_apply_pipeline_layout.c, radv_nir_lower_abi.c). Upstream it is
one constant per GPU, so RADV's cache UUID leaves it out. Crema (src/amd/common/ac_ps4_drm.c) reserves a new 4 GiB
window for every device it opens, wherever the kernel finds room, and reports address32_hi = va32_start >> 32: the value
depends on what the process opened before. With the disk cache (04.27), a shader compiled by one device was loaded by
another with a different window: RADV's own clear/blit shaders and DXVK's internal pipelines are the same for every
program, so GTA San Andreas (DXVK, after wined3d's probe devices) hit entries compiled for another window, its shaders
addressed memory outside its own, and the console restarted (04.31, runs 0263 and 0264; with the cache off, run 0266,
the game plays).

Here the window goes into the cache UUID, which keys the disk cache (main and builtin shaders, through disk_cache_create's
driver id), VkPipelineCache data (pipelineCacheUUID) and vkGetShaderBinaryDataEXT blobs (shaderBinaryUUID and the
04.28 shader object cache). A hit can then only come from a device with the same window. One PWCACHE line per device
says which window it has.
patch-mesa-cache-va32.py <mesa source>"""
import sys as _brand_sys
from pathlib import Path as _BrandPath
_brand_sys.path.insert(0,str(_BrandPath(__file__).resolve().parents[1]))
from project_brand import normalize_marker

import pathlib,sys
mesa=pathlib.Path(sys.argv[1])
MARK='OrbisDesk 04.32 cache window'
path='src/amd/vulkan/radv_physical_device.c'
target=mesa/path;text=normalize_marker(target.read_text())
if MARK in text:
    print(path,'already patched');raise SystemExit(0)
edits=[
('''#if AMD_LLVM_AVAILABLE
   if (pdev->use_llvm && !disk_cache_get_function_identifier(LLVMInitializeAMDGPUTargetInfo, &ctx))
      return -1;
#endif

   _mesa_sha1_final(&ctx, sha1);''','''#if AMD_LLVM_AVAILABLE
   if (pdev->use_llvm && !disk_cache_get_function_identifier(LLVMInitializeAMDGPUTargetInfo, &ctx))
      return -1;
#endif
#ifdef __PS4__ /* '''+MARK+''': compiled code holds the device's 32-bit window, which Crema picks per device */
   _mesa_sha1_update(&ctx, &pdev->info.address32_hi, sizeof(pdev->info.address32_hi));
#endif

   _mesa_sha1_final(&ctx, sha1);'''),
('''   pdev->disk_cache_meta =
      disk_cache_create_custom(''','''#ifdef __PS4__ /* '''+MARK+''' */
   fprintf(stderr, "PWCACHE radv address32_hi=%#x\\n", pdev->info.address32_hi);
#endif
   pdev->disk_cache_meta =
      disk_cache_create_custom('''),
]
for old,new in edits:
    if text.count(old)!=1:raise SystemExit('Unexpected context in '+path+': '+old[:70])
    text=text.replace(old,new,1)
target.write_text(text);print(path,'patched')
