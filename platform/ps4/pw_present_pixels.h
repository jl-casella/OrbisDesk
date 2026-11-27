/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_PRESENT_PIXELS_H
#define PW_PRESENT_PIXELS_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <limits.h>

/* VkFormat values, checked against the pinned Wine Vulkan header by the host test.
 * Output words are AARRGGBB (BGRA bytes on this platform). No gamma conversion. */
static inline unsigned pw_present_bpp(int format)
{
    switch (format)
    {
    case 2: case 3: case 4: case 5: case 6: case 7: case 8:
    case 1000340000: case 1000340001: return 2;
    case 37: case 43: case 44: case 50: case 51: case 57: return 4;
    default: return 0;
    }
}
static inline int pw_present_rgba(int format)
{
    return format == 37 || format == 43 || format == 51 || format == 57;
}
static inline int pw_present_layout(int format, unsigned pitch, unsigned width, unsigned height)
{
    unsigned bpp = pw_present_bpp(format);
    return bpp && width && height && width <= INT_MAX / 4 && height <= INT_MAX &&
           (size_t)width * bpp <= pitch && height <= SIZE_MAX / pitch &&
           (size_t)width * 4 <= SIZE_MAX / height;
}
static inline unsigned pw_present_5(unsigned n) { return (n << 3) | (n >> 2); }
static inline unsigned pw_present_6(unsigned n) { return (n << 2) | (n >> 4); }
static inline uint32_t pw_present_unpack16(unsigned p, int format)
{
    unsigned r, g, b, a;
    switch (format)
    {
    case 2: r=(p>>12)&15;g=(p>>8)&15;b=(p>>4)&15;a=p&15;break;
    case 3: b=(p>>12)&15;g=(p>>8)&15;r=(p>>4)&15;a=p&15;break;
    case 1000340000: a=p>>12;r=(p>>8)&15;g=(p>>4)&15;b=p&15;break;
    case 1000340001: a=p>>12;b=(p>>8)&15;g=(p>>4)&15;r=p&15;break;
    case 4: case 5:
        r=pw_present_5((p>>11)&31);g=pw_present_6((p>>5)&63);b=pw_present_5(p&31);
        if (format==5) { unsigned t=r;r=b;b=t; }
        return 0xff000000u | (r<<16) | (g<<8) | b;
    case 6: case 7:
        r=pw_present_5((p>>11)&31);g=pw_present_5((p>>6)&31);b=pw_present_5((p>>1)&31);a=(p&1)*255;
        if (format==7) { unsigned t=r;r=b;b=t; }
        return (a<<24) | (r<<16) | (g<<8) | b;
    case 8:
        return ((p>>15)*255u<<24) | (pw_present_5((p>>10)&31)<<16) |
               (pw_present_5((p>>5)&31)<<8) | pw_present_5(p&31);
    default: return 0;
    }
    return (a*17u<<24) | (r*17u<<16) | (g*17u<<8) | b*17u;
}
static inline int pw_present_to_bgra(uint32_t *dst, const void *pixels, unsigned pitch,
                                     unsigned width, unsigned height, int format)
{
    unsigned x, y, bpp=pw_present_bpp(format);
    if (!dst || !pixels || !pw_present_layout(format,pitch,width,height)) return 0;
    for (y=0;y<height;y++)
    {
        const unsigned char *row=(const unsigned char *)pixels+(size_t)y*pitch;
        for (x=0;x<width;x++)
        {
            uint32_t p;
            if (bpp==2)
            {
                uint16_t packed;
                memcpy(&packed,row+(size_t)x*2,2);
                p=pw_present_unpack16(packed,format);
            }
            else
            {
                memcpy(&p,row+(size_t)x*4,4);
                if (pw_present_rgba(format)) p=(p&0xff00ff00u)|((p&255)<<16)|((p>>16)&255);
            }
            dst[(size_t)y*width+x]=p;
        }
    }
    return 1;
}
struct pw_present_storage { uint32_t *pixels; size_t capacity; };
static inline void pw_present_storage_clear(struct pw_present_storage *storage, void (*release)(void *))
{
    if (storage->pixels) release(storage->pixels);
    storage->pixels=NULL;storage->capacity=0;
}
/* The compositor owns this storage until forget/window destruction. Its present
 * waits for GPU completion, so a subsequent call can reuse the buffer under screen_lock. */
static inline int pw_present_layer(struct pw_present_storage *storage, const void *pixels,
                                  unsigned pitch, unsigned width, unsigned height, int format,
                                  void *(*allocate)(size_t), void (*release)(void *),
                                  const uint32_t **out, unsigned *stride, unsigned *rgba)
{
    size_t bytes;
    uint32_t *next;
    if (!pixels || !pw_present_layout(format,pitch,width,height)) return 0;
    if (pw_present_bpp(format)==4)
    {
        if ((uintptr_t)pixels%4 || pitch%4) return 0;
        *out=pixels;*stride=pitch/4;*rgba=pw_present_rgba(format);return 1;
    }
    bytes=(size_t)width*height*4;
    if (storage->capacity<bytes)
    {
        if (!(next=allocate(bytes))) return 0;
        pw_present_storage_clear(storage,release);
        storage->pixels=next;storage->capacity=bytes;
    }
    if (!pw_present_to_bgra(storage->pixels,pixels,pitch,width,height,format)) return 0;
    *out=storage->pixels;*stride=width;*rgba=0;
    return 1;
}
#endif
