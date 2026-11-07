#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""W126: VK_EXT_map_memory_placed on the PS4 winsys (Mesa RADV, Crema's ac_ps4_drm.c).

Wine maps the memory of a 32-bit program (WoW64) at an address it reserves below 4 GiB and
passes it as VkMemoryMapPlacedInfoEXT::pPlacedAddress; DXVK's x86 d3d9 failed with
VK_ERROR_MEMORY_MAP_FAILED because the __PS4__ branch of radv_amdgpu_winsys_bo_map returned
NULL for every placed map (W124). Here the buffer's direct memory is mapped a second time, for
the CPU only, at that address (sceKernelMapDirectMemory with MAP_FIXED); the GPU keeps the
original mapping, and both alias the same physical pages. The kernel maps in 16 KiB units, so
RADV reports that alignment; Wine reserves at 64 KiB granularity, which a rounded-up length
stays within. Unmapping leaves the alias to Wine, which releases its reservation right after.
"""
import sys as _brand_sys
from pathlib import Path as _BrandPath
_brand_sys.path.insert(0,str(_BrandPath(__file__).resolve().parents[1]))
from project_brand import normalize_marker

import pathlib,sys
mesa=pathlib.Path(sys.argv[1])
MARK='OrbisDesk W126'
def patch(path,old,new):
    target=mesa/path;text=normalize_marker(target.read_text())
    if MARK in text and new.split('\n')[0] in text:return
    if text.count(old)!=1:raise SystemExit('Unexpected context in '+path+': '+old[:60])
    target.write_text(text.replace(old,new,1))

patch('src/amd/common/ac_ps4_drm.c','''int
ac_drm_bo_cpu_unmap(ac_drm_device *dev, ac_drm_bo bo)
{''','''/* OrbisDesk W126: a second, CPU-only mapping of the buffer at an address the caller chose
 * (VK_EXT_map_memory_placed): the same direct memory, so it aliases the GPU mapping. */
int ac_ps4_bo_cpu_map_fixed(ac_drm_device *dev, ac_drm_bo bo, void *addr);
int
ac_ps4_bo_cpu_map_fixed(ac_drm_device *dev, ac_drm_bo bo, void *addr)
{
   struct amdgpu_bo *b = bo.abo;
   void *at = addr;
   uint64_t size = align64(b->size, PS4_PAGE);
   if ((uintptr_t)addr % PS4_PAGE) {
      ps4_log("radv/ps4: placed map of bo %u at %p: not %#llx aligned\\n", b->handle, addr,
              (unsigned long long)PS4_PAGE);
      return -EINVAL;
   }
   int r = sceKernelMapDirectMemory(&at, size, PS4_PROT_CPU_RW, PS4_MAP_FIXED, b->phys, PS4_PAGE);
   if (r || at != addr) {
      ps4_log("radv/ps4: placed map of bo %u (%#llx bytes) at %p failed: %#x, got %p\\n", b->handle,
              (unsigned long long)size, addr, r, at);
      return -ENOMEM;
   }
   if (b->write_combined)
      ps4_flush_cpu_cache(at, size);
   return 0;
}

int
ac_drm_bo_cpu_unmap(ac_drm_device *dev, ac_drm_bo bo)
{''')

patch('src/amd/vulkan/winsys/amdgpu/radv_amdgpu_bo.c','''#ifdef __PS4__
   {
      struct radv_amdgpu_winsys *ws = radv_amdgpu_winsys(_ws);
      void *data = NULL;
      if (use_fixed_addr || ac_drm_bo_cpu_map(ws->dev, bo->bo, &data))
         return NULL;''','''#ifdef __PS4__
   {
      struct radv_amdgpu_winsys *ws = radv_amdgpu_winsys(_ws);
      void *data = NULL;
      /* OrbisDesk W126: placed maps (VK_EXT_map_memory_placed) alias the buffer's memory */
      if (use_fixed_addr) {
         extern int ac_ps4_bo_cpu_map_fixed(ac_drm_device *dev, ac_drm_bo bo, void *addr);
         if (ac_ps4_bo_cpu_map_fixed(ws->dev, bo->bo, fixed_addr))
            return NULL;
         bo->cpu_map = fixed_addr;
         return fixed_addr;
      }
      if (ac_drm_bo_cpu_map(ws->dev, bo->bo, &data))
         return NULL;''')

patch('src/amd/vulkan/radv_physical_device.c','''      .minPlacedMemoryMapAlignment = os_page_size,''','''#ifdef __PS4__
      /* OrbisDesk W126: the PS4 kernel maps direct memory in 16 KiB units */
      .minPlacedMemoryMapAlignment = MAX2(os_page_size, 0x4000),
#else
      .minPlacedMemoryMapAlignment = os_page_size,
#endif''')
print('placed maps patched')
