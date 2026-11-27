# SPDX-License-Identifier: LGPL-2.1-or-later
"""Context-checked packed-pixel presentation changes, applied after the win32u overlays."""
def change(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Unexpected packed-pixel context: " + old[:90])
    return text.replace(old, new, 1)

def patch_vulkan(text):
    text=change(text, '#include "config.h"', '#include "config.h"\n#include "pw_present_pixels.h"')
    text=change(text, 'BOOL rgba, const RECT *client );', 'int format, const RECT *client );')
    text=change(text, '''    pw_wine_vk_window_presented( (unsigned long long)(UINT_PTR)hwnd );''', '''    if (!pixels || !pw_present_layout(format,pitch,width,height))
    {
        static unsigned rejected;
        if (rejected++ < 8) ERR("PWPIXELS rejected format=%d size=%ux%u pitch=%u\\n",format,width,height,pitch);
        return;
    }
    pw_wine_vk_window_presented( (unsigned long long)(UINT_PTR)hwnd );''')
    text=change(text, '''                              format == VK_FORMAT_R8G8B8A8_UNORM || format == VK_FORMAT_R8G8B8A8_SRGB, &client ))''',
                      '''                              format, &client ))''')
    start=text.index('    if (format == VK_FORMAT_R8G8B8A8_UNORM || format == VK_FORMAT_R8G8B8A8_SRGB)',text.index('static void pw_vk_show_frame'))
    end=text.index('    info.bmiHeader.biWidth = pitch / 4;',start)
    text=text[:start]+'''    /* GDI consumes the temporary copy synchronously; GPU layers own a separate persistent buffer. */
    if (pw_present_bpp(format) != 4 || pw_present_rgba(format) || pitch % 4)
    {
        if (!(converted = malloc((size_t)width * height * 4))) return;
        if (!pw_present_to_bgra(converted,pixels,pitch,width,height,format))
        {
            free(converted);
            return;
        }
        pixels = converted;
        pitch = width * 4;
    }
'''+text[end:]
    text=change(text, '    UINT pitch, width, height, i;', '    UINT pitch, width, height;')
    return text

def patch_driver(text):
    text=change(text, '#include <stdint.h>', '#include <stdint.h>\n#include "pw_present_pixels.h"')
    text=change(text, '    UINT64 vk_swapchain;', '''    UINT64 vk_swapchain;
    struct pw_present_storage vk_converted;
    int vk_source_format;''')
    text=change(text, '''BOOL ps5_vulkan_frame( HWND hwnd, UINT64 swapchain, const void *pixels, UINT pitch, UINT width, UINT height,
                       BOOL rgba, const RECT *client )''', '''static void pw_present_release(void *pixels) { free_pixels(pixels); }

/* Standalone boot links have no generator. The product sink's strong callback
 * replaces this weak, non-inlined notification; it never reports generation. */
void __attribute__((weak,noinline,visibility("default"))) pw_wine_framegen_normalized(const void *swapchain,const void *source,
                                                              const void *bgra,unsigned width,unsigned height)
{ (void)swapchain;(void)source;(void)bgra;(void)width;(void)height; }

BOOL ps5_vulkan_frame( HWND hwnd, UINT64 swapchain, const void *pixels, UINT pitch, UINT width, UINT height,
                       int format, const RECT *client )''')
    begin=text.index('BOOL ps5_vulkan_frame(')
    end=text.index('/* W152: the swapchain is about to be destroyed',begin)
    body=text[begin:end]
    body=change(body, '    if (!pixels || pitch % 4 || !width || !height) return FALSE;',
                     '    if (!pixels || !pw_present_layout(format,pitch,width,height)) return FALSE;')
    body=change(body, '''        window->vk_pixels = pixels;
        window->vk_stride = pitch / 4;''', '''        const uint32_t *layer;
        unsigned stride, rgba;
        if (!pw_present_layer(&window->vk_converted,pixels,pitch,width,height,format,
                              pw_wine_layer_alloc,pw_present_release,&layer,&stride,&rgba))
        {
            /* Do not publish invalid metadata or leave a stale image over the GDI fallback. */
            window->vk_pixels = NULL;
            screen_lock_leave();
            return FALSE;
        }
        extern int pw_trace_enabled( void );  /* layer changes: traces only (platform/ps4/pw_trace.h) */
        if ((window->vk_source_format != format || window->vk_width != width || window->vk_height != height) &&
            pw_trace_enabled())
            fprintf(stderr,"PWPIXELS layer format=%d source_pitch=%u stride=%u size=%ux%u converted=%u\\n",
                    format,pitch,stride,width,height,pw_present_bpp(format)==2);
        window->vk_source_format = format;
        window->vk_pixels = layer;
        window->vk_stride = stride;
        if (pw_present_bpp(format)==2)
        {
            extern void pw_wine_framegen_normalized(const void *,const void *,const void *,unsigned,unsigned)
                __attribute__((weak));
            if (pw_wine_framegen_normalized)
                pw_wine_framegen_normalized((const void *)(uintptr_t)swapchain,pixels,layer,width,height);
        }''')
    text=text[:begin]+body+text[end:]
    begin=text.index('void ps5_vulkan_forget(')
    end=text.index('\n/*',text.index('    screen_lock_leave();\n}',begin)+len('    screen_lock_leave();\n}'))
    body=text[begin:end]
    body=change(body,'window && window->vk_pixels && window->vk_swapchain == swapchain',
                'window && (window->vk_pixels || window->vk_converted.pixels) && window->vk_swapchain == swapchain')
    body=change(body,'windows[i].vk_pixels && windows[i].vk_swapchain == swapchain',
                '(windows[i].vk_pixels || windows[i].vk_converted.pixels) && windows[i].vk_swapchain == swapchain')
    body=change(body, '            window->vk_pixels = NULL;', '''            window->vk_pixels = NULL;
            pw_present_storage_clear(&window->vk_converted,pw_present_release);''')
    body=change(body, '                    windows[i].vk_pixels = NULL;', '''                    windows[i].vk_pixels = NULL;
                    pw_present_storage_clear(&windows[i].vk_converted,pw_present_release);''')
    text=text[:begin]+body+text[end:]
    text=change(text, '''        free_pixels( window->pixels );
        memmove( &windows[index]''', '''        pw_present_storage_clear(&window->vk_converted,pw_present_release);
        free_pixels( window->pixels );
        memmove( &windows[index]''')
    text=change(text, '''        free_pixels( windows[i].pixels );
        memmove( &windows[i]''', '''        pw_present_storage_clear(&windows[i].vk_converted,pw_present_release);
        free_pixels( windows[i].pixels );
        memmove( &windows[i]''')
    return text
