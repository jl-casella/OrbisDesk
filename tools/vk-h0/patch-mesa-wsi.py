# W072 (H3): Mesa's headless WSI on the PS4. There is no window system: the swapchain images
# become CPU images (a GPU blit into a host-visible linear buffer per image, which Mesa does
# for software drivers' windows), and each present waits for that blit and hands the pixels
# to pw_wsi_headless_presented, set by Wine's ELF (native/wine_vk_runtime.c), which shows
# them in the swapchain's window. Without the hook a present only finishes the image, as
# before.
# W074: the CPU buffers are host-cached memory, as for software drivers (W073: 35 FPS at
# 632x453 and 12 at 1280x701 with the CPU reading uncached memory), and the hook also gets
# the time the present waited for the blit.
#   patch-mesa-wsi.py <mesa source>   (build-mesa.sh first restores the three files from the
#   tarball, so the patch always applies to the original text)
import sys as _brand_sys
from pathlib import Path as _BrandPath
_brand_sys.path.insert(0,str(_BrandPath(__file__).resolve().parents[1]))
from project_brand import normalize_marker

import pathlib, sys
root = pathlib.Path(sys.argv[1])

def patch(path, changes):
    target = root / path
    text = normalize_marker(target.read_text())
    for old, new in changes:
        if text.count(old) != 1:
            raise SystemExit('unexpected ' + path + ': ' + old[:60])
        text = text.replace(old, new)
    target.write_text(text)
    print('patched ' + path)

# W073: RADV offers VK_KHR_surface, VK_EXT_headless_surface and VK_KHR_swapchain only with a
# window system platform (X11, Wayland, display); the PS4 build has none, and
# vkCreateInstance with VK_KHR_win32_surface failed with VK_ERROR_EXTENSION_NOT_PRESENT.
# Headless is the PS4's platform.
patch('src/amd/vulkan/radv_wsi.h', [
    ('defined(VK_USE_PLATFORM_XLIB_KHR) ||   \\\n   defined(VK_USE_PLATFORM_DISPLAY_KHR)',
     'defined(VK_USE_PLATFORM_XLIB_KHR) ||   \\\n   defined(VK_USE_PLATFORM_DISPLAY_KHR) || defined(__PS4__)')])

patch('src/vulkan/wsi/wsi_common.c', [
    ('''   if (wsi->sw)
      req_props |= VK_MEMORY_PROPERTY_HOST_CACHED_BIT;
''', '''#ifdef __PS4__
   /* the CPU reads these buffers (tools/vk-h0/patch-mesa-wsi.py) */
   if (true)
#else
   if (wsi->sw)
#endif
      req_props |= VK_MEMORY_PROPERTY_HOST_CACHED_BIT;
''')])

patch('src/vulkan/wsi/wsi_common_headless.c', [
    ('#include "vk_physical_device.h"\n', '''#include "vk_physical_device.h"

#ifdef __PS4__
#include "util/os_time.h"
/* OrbisDesk (tools/vk-h0/patch-mesa-wsi.py): called with each presented image's pixels. */
void (*pw_wsi_headless_presented)(const void *swapchain, const void *pixels, uint32_t row_pitch,
                                  uint32_t width, uint32_t height, VkFormat format,
                                  uint64_t blit_wait_ns);
#endif
'''),
    ('''   chain->images[image_index].busy_on_host = false;

   return VK_SUCCESS;''', '''#ifdef __PS4__
   {
      struct wsi_image *image = &chain->images[image_index].base;
      /* the image's blit into its CPU buffer signals this fence (wsi_common_queue_present) */
      const uint64_t wait_start = os_time_get_nano();
      chain->base.wsi->WaitForFences(chain->base.device, 1, &chain->base.fences[image_index],
                                     true, UINT64_MAX);
      if (pw_wsi_headless_presented && image->cpu_map)
         pw_wsi_headless_presented(chain, image->cpu_map, image->row_pitches[0],
                                   chain->base.image_info.create.extent.width,
                                   chain->base.image_info.create.extent.height,
                                   chain->base.image_info.create.format,
                                   os_time_get_nano() - wait_start);
   }
#endif
   chain->images[image_index].busy_on_host = false;

   return VK_SUCCESS;'''),
    ('''   if (wsi_device->sw) {
      cpu_params = (struct wsi_cpu_image_params) {''', '''#ifdef __PS4__
   /* no DRM and no window system: images the CPU can read */
   if (true) {
#else
   if (wsi_device->sw) {
#endif
      cpu_params = (struct wsi_cpu_image_params) {''')])
