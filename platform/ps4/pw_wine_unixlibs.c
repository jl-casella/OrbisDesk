/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include <string.h>
/* The boot ELF links every builtin module's Unix side statically: ntdll finds a
 * module's __wine_unix_call_funcs or __wine_unix_lib_init here, by the base name
 * of its .so path, instead of through dlopen. An unknown name keeps Wine's own
 * failure path. */
extern const void *pw_wowprospero_unix_call_funcs[];
/* W137: the native WoW64 CPU backend (tools/build-wow64native-ps4.py) */
extern const void *pw_wow64native_unix_call_funcs[];
extern unsigned int pw_win32u_unix_lib_init(void);
/* W071: winevulkan's Unix side (tools/build-winevulkan-ps4.py) */
extern const void *pw_winevulkan_unix_call_funcs[];
extern const void *pw_winevulkan_unix_call_wow64_funcs[];
/* W093: ws2_32's Unix side (tools/build-unixlibs-ps4.py) */
extern const void *pw_ws2_32_unix_call_funcs[],*pw_ws2_32_unix_call_wow64_funcs[];
/* W120: Wine's audio driver for the console (tools/build-audio-ps4.py, prospero-win's wineps5) */
extern const void *pw_wineps4_unix_call_funcs[],*pw_wineps4_unix_call_wow64_funcs[];
/* W121: opengl32's Unix side (tools/build-unixlibs-ps4.py): the 32-bit opengl32.dll that
 * wined3d imports could not initialise without it */
extern const void *pw_opengl32_unix_call_funcs[],*pw_opengl32_unix_call_wow64_funcs[];
/* Phase 8: dnsapi's Unix side and the hardware nsi.dll's settings call, both from libSceNetCtl
 * (platform/ps4/pw_wine_netctl.c, tools/build-unixlibs-ps4.py) */
extern const void *pw_dnsapi_unix_call_funcs[],*pw_dnsapi_unix_call_wow64_funcs[];
extern const void *pw_nsi_unix_call_funcs[],*pw_nsi_unix_call_wow64_funcs[];
/* W180 (phase 9): crypt32's Unix side, without GnuTLS or a CA bundle (platform/ps4/pw_crypt32_unix.c,
 * tools/build-unixlibs-ps4.py); without it crypt32.dll, and every xul.dll through wintrust, failed */
extern const void *pw_crypt32_unix_call_funcs[],*pw_crypt32_unix_call_wow64_funcs[];
/* W178 (phase 7): xinput's Unix side, the console's pad as controller 0 (tools/build-xinput-hw.py) */
extern const void *pw_xinput_unix_call_funcs[],*pw_xinput_unix_call_wow64_funcs[];
/* The pad comes from the hardware launcher (native/hw_pad.c). An ELF without it has no pad:
 * xinput's pad_init then fails and xinput keeps its HID path. */
__attribute__((weak)) int pw_wine_pad_available(void)
{
    return 0;
}
__attribute__((weak)) int pw_wine_pad(void *state)
{
    (void)state;
    return 0;
}
__attribute__((weak)) void pw_wine_set_rumble(unsigned int left,unsigned int right)
{
    (void)left;(void)right;
}
/* W213: guest key profiles (native/hw_pad.c); no pad, no profile */
__attribute__((weak)) void pw_wine_pad_profile(const char *exe,int load)
{
    (void)exe;(void)load;
}
/* HID stack: winebus's Unix side with the console's pad as an Xbox 360 HID gamepad
 * (tools/build-hidstack-hw.py, native/winebus_orbis.c). Without hw_pad.c its bus init fails. */
extern const void *pw_winebus_unix_call_funcs[];
__attribute__((weak)) int pw_wine_pad_peek(void *state)
{
    (void)state;
    return 0;
}
/* W237 (control overlay): DualSense report and light bar (native/hw_pad.c); create-fself refuses an
 * undefined weak reference, so an ELF without hw_pad.c gets these, and no DualSense report */
__attribute__((weak)) int pw_wine_pad_dualsense(unsigned char *report)
{
    (void)report;
    return 0;
}
__attribute__((weak)) void pw_wine_set_lightbar(unsigned int r,unsigned int g,unsigned int b)
{
    (void)r;(void)g;(void)b;
}
/* W071: win32u's vkGetInstanceProcAddr. An ELF that links Mesa's RADV (the hardware
 * launcher, native/wine_hardware.c) sets it before Wine starts; NULL means no Vulkan. */
void *(*pw_vk_instance_proc_addr)(void *instance,const char *name);
/* W072: the last image presented on a headless swapchain (native/wine_vk_runtime.c), which
 * win32u draws into the swapchain's window */
int (*pw_vk_last_frame)(const void *swapchain,const void **pixels,unsigned int *pitch,unsigned int *width,
                        unsigned int *height,int *format);
typedef unsigned int (*PwUnixLibInit)(void);
int pw_wine_static_unixlib(const char *path,int wow,const void **funcs,PwUnixLibInit *init)
{
    static const struct {const char *name;const void *funcs;const void *wow64_funcs;PwUnixLibInit init;} table[]={
        {"wowprospero.so",pw_wowprospero_unix_call_funcs,NULL,NULL},
        {"wow64native.so",pw_wow64native_unix_call_funcs,NULL,NULL},
        {"win32u.so",NULL,NULL,pw_win32u_unix_lib_init},
        {"winevulkan.so",pw_winevulkan_unix_call_funcs,pw_winevulkan_unix_call_wow64_funcs,NULL},
        {"ws2_32.so",pw_ws2_32_unix_call_funcs,pw_ws2_32_unix_call_wow64_funcs,NULL},
        {"wineps4.so",pw_wineps4_unix_call_funcs,pw_wineps4_unix_call_wow64_funcs,NULL},
        {"opengl32.so",pw_opengl32_unix_call_funcs,pw_opengl32_unix_call_wow64_funcs,NULL},
        {"dnsapi.so",pw_dnsapi_unix_call_funcs,pw_dnsapi_unix_call_wow64_funcs,NULL},
        {"nsi.so",pw_nsi_unix_call_funcs,pw_nsi_unix_call_wow64_funcs,NULL},
        {"xinput1_3.so",pw_xinput_unix_call_funcs,pw_xinput_unix_call_wow64_funcs,NULL},
        {"crypt32.so",pw_crypt32_unix_call_funcs,pw_crypt32_unix_call_wow64_funcs,NULL},
        {"winebus.so",pw_winebus_unix_call_funcs,NULL,NULL}};
    const char *base=path?strrchr(path,'/'):NULL;
    base=base?base+1:path;
    if(!base) return 0;
    /* A library initialises once per process, as with dlopen and its constructor. */
    static unsigned char initialised[sizeof(table)/sizeof(table[0])];
    for(unsigned n=0;n<sizeof(table)/sizeof(table[0]);++n) {
        if(strcmp(base,table[n].name)) continue;
        *funcs=wow?table[n].wow64_funcs:table[n].funcs;
        *init=*funcs || initialised[n]?NULL:table[n].init;
        if(*init) initialised[n]=1;
        return *funcs || table[n].init;
    }
    return 0;
}

/* W120: a Unix library loaded by name, without a PE module (mmdevapi asks for its audio
 * driver "wine<name>.drv", Wine's MemoryWineLoadUnixLibByName): the static table entry
 * "wine<name>.so". The name is UTF-16, as in Wine's UNICODE_STRING.
 * W178: also a name without an extension ("<name>.so"): every xinput version loads "xinput1_3". */
int pw_wine_static_unixlib_by_name(const void *unicode_name,int wow,const void **funcs,PwUnixLibInit *init)
{
    const struct {unsigned short length,maximum;const unsigned short *buffer;} *name=unicode_name;
    char path[64];unsigned n=0,count;
    if(!name || !name->buffer) return 0;
    count=name->length/2;
    if(count+4>=sizeof(path)) return 0;
    for(unsigned i=0;i<count;++i) {
        if(name->buffer[i]>0x7e) return 0;
        path[n++]=(char)name->buffer[i];
    }
    path[n]=0;
    if(n && !memchr(path,'.',n)) strcpy(path+n,".so");
    else if(n<4 || strcmp(path+n-4,".drv")) return 0;
    else strcpy(path+n-4,".so");
    return pw_wine_static_unixlib(path,wow,funcs,init);
}
