#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""W250: PWHUD traces in MangoHud i386's own copy of the tree (tools/vk-h0/build-mangohud-i386.sh runs this on
~/vk-h0/src/mangohud-win-i386; the x64 tree and build are untouched).

W248: in Vice City the i386 layer DLL loaded but drew nothing, and Shift+F12 changed nothing. W249 fixes the exports
the loader looks for; these lines say how far the layer gets if it still draws nothing: instance and device
creation through the layer, each swapchain (its size), the first present, and each toggle_hud (the no_display
it leaves). OutputDebugStringA: in the run log through warn+debugstr ("PWHUD i386 ...").

Usage: mangohud-i386-traces.py TREE. Each edit must match once; otherwise it stops and changes nothing.
"""
import sys as _brand_sys
from pathlib import Path as _BrandPath
_brand_sys.path.insert(0,str(_BrandPath(__file__).resolve().parents[1]))
from project_brand import normalize_marker

import pathlib,sys

if len(sys.argv)!=2:raise SystemExit(__doc__)
src=pathlib.Path(sys.argv[1])/'src'
EDITS=[
('vulkan.cpp','''#include <windows.h>
''','''#include <windows.h>
#include <stdio.h>  /* OrbisDesk W250: PWHUD traces */
'''),
('vulkan.cpp','''static VkResult overlay_CreateInstance(
    const VkInstanceCreateInfo*                 pCreateInfo,
    const VkAllocationCallbacks*                pAllocator,
    VkInstance*                                 pInstance)
{
''','''static VkResult overlay_CreateInstance(
    const VkInstanceCreateInfo*                 pCreateInfo,
    const VkAllocationCallbacks*                pAllocator,
    VkInstance*                                 pInstance)
{
   OutputDebugStringA( "PWHUD i386 vkCreateInstance\\n" );  /* OrbisDesk W250 */
'''),
('vulkan.cpp','''static VkResult overlay_CreateDevice(
    VkPhysicalDevice                            physicalDevice,
    const VkDeviceCreateInfo*                   pCreateInfo,
    const VkAllocationCallbacks*                pAllocator,
    VkDevice*                                   pDevice)
{
''','''static VkResult overlay_CreateDevice(
    VkPhysicalDevice                            physicalDevice,
    const VkDeviceCreateInfo*                   pCreateInfo,
    const VkAllocationCallbacks*                pAllocator,
    VkDevice*                                   pDevice)
{
   OutputDebugStringA( "PWHUD i386 vkCreateDevice\\n" );  /* OrbisDesk W250 */
'''),
('vulkan.cpp','''static VkResult overlay_CreateSwapchainKHR(
    VkDevice                                    device,
    const VkSwapchainCreateInfoKHR*             pCreateInfo,
    const VkAllocationCallbacks*                pAllocator,
    VkSwapchainKHR*                             pSwapchain)
{
''','''static VkResult overlay_CreateSwapchainKHR(
    VkDevice                                    device,
    const VkSwapchainCreateInfoKHR*             pCreateInfo,
    const VkAllocationCallbacks*                pAllocator,
    VkSwapchainKHR*                             pSwapchain)
{
   {  /* OrbisDesk W250 */
      char pwhud[96];
      snprintf( pwhud, sizeof(pwhud), "PWHUD i386 vkCreateSwapchainKHR %ux%u\\n",
                (unsigned)pCreateInfo->imageExtent.width, (unsigned)pCreateInfo->imageExtent.height );
      OutputDebugStringA( pwhud );
   }
'''),
('vulkan.cpp','''static VkResult overlay_QueuePresentKHR(
    VkQueue                                     queue,
    const VkPresentInfoKHR*                     pPresentInfo)
{
''','''static VkResult overlay_QueuePresentKHR(
    VkQueue                                     queue,
    const VkPresentInfoKHR*                     pPresentInfo)
{
   {  /* OrbisDesk W250: the first present through the layer */
      static LONG pwhud_presents;
      if (!InterlockedExchangeAdd( &pwhud_presents, 1 )) OutputDebugStringA( "PWHUD i386 first vkQueuePresentKHR\\n" );
   }
'''),
('keybinds.cpp','''#include <cstdint>
#include <cstring>
''','''#include <cstdint>
#include <cstring>
#include <cstdio>  /* OrbisDesk W250: PWHUD traces */
'''),
('keybinds.cpp','''      real_params->no_display = !real_params->no_display;
   }
''','''      real_params->no_display = !real_params->no_display;
      {  /* OrbisDesk W250 */
         char pwhud[64];
         snprintf( pwhud, sizeof(pwhud), "PWHUD i386 toggle_hud no_display=%d\\n", (int)real_params->no_display );
         OutputDebugStringA( pwhud );
      }
   }
'''),
]
texts={}
for name,old,new in EDITS:
    text=texts.get(name) or normalize_marker((src/name).read_text())
    if text.count(old)!=1:raise SystemExit('mangohud-i386-traces: unexpected src/%s (%d matches of %r)'%(name,text.count(old),old[:60]))
    texts[name]=text.replace(old,new)
for name,text in texts.items():(src/name).write_text(text)
print('PWHUD traces: %d edits in %s'%(len(EDITS),', '.join(sorted(texts))))
