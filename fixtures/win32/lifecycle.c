/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include <stdint.h>
#ifndef REJECT_ATTACH
#define REJECT_ATTACH 0
#endif
extern const char __ImageBase;
unsigned _tls_index;
__attribute__((section(".tls"))) volatile unsigned tls_template[6] = {7,0,0,0,0,0};
static volatile struct { unsigned errors, count, events[32]; } diagnostics;
static volatile unsigned *sink;
static volatile unsigned *local(void)
{
    unsigned *slots;
    __asm__ volatile("movl %%fs:0x2c,%0" : "=r"(slots));
    return (volatile unsigned *)(uintptr_t)slots[_tls_index];
}
static void event(unsigned tag, unsigned reason, void *module, void *reserved)
{
    if (module != (void *)&__ImageBase) diagnostics.errors |= 0x100;
    if (reserved) diagnostics.errors |= 0x200;
    if (reason > 3) diagnostics.errors |= 0x400;
    if (diagnostics.count < 32) diagnostics.events[diagnostics.count++] = tag | reason;
    else diagnostics.errors++;
    if (sink) {
        sink[0] = diagnostics.errors; sink[1] = diagnostics.count;
        if (diagnostics.count <= 32) sink[diagnostics.count + 1] = tag | reason;
    }
}
static void __attribute__((stdcall)) tls_callback(void *module, unsigned reason, void *reserved)
{
    volatile unsigned *p = local();
    if (reason == 1 || reason == 2) {
        if (p[0] != 7) diagnostics.errors |= 1;
        for (unsigned i = 1; i < 6; ++i) if (p[i]) diagnostics.errors |= 1u << i;
        p[2] = 1;
        p[3] = (unsigned)(uintptr_t)&diagnostics;
    } else {
        if (p[2] != 2) diagnostics.errors++;
        p[2] = 3;
    }
    event(0x10, reason, module, reserved);
}
__attribute__((section(".CRT$XLB"),used))
void (__attribute__((stdcall)) *tls_callbacks[])(void *,unsigned,void *) = {tls_callback,0};
typedef struct TlsDirectory {
    const void *start, *end;
    unsigned *index;
    const void *callbacks;
    unsigned zero_fill, characteristics;
} TlsDirectory;
__attribute__((section(".rdata$T"),used)) const TlsDirectory _tls_used = {
    (const void *)tls_template, (const void *)(tls_template + 6), &_tls_index, tls_callbacks, 0, 0
};
int __attribute__((stdcall)) DllMain(void *module, unsigned reason, void *reserved)
{
    volatile unsigned *p = local();
    if (reason == 1 || reason == 2) {
        if (p[2] != 1) diagnostics.errors++;
        p[2] = 2;
    } else {
        if (p[2] != 3) diagnostics.errors++;
        p[2] = 4;
    }
    event(0x20, reason, module, reserved);
    return !(REJECT_ATTACH && reason == 1);
}
unsigned Touch(unsigned value)
{
    volatile unsigned *p = local();
    unsigned old = p[0]; p[0] = value; return old;
}
unsigned Inspect(unsigned what)
{
    if (what == 0) return diagnostics.errors;
    if (what == 1) return diagnostics.count;
    if (what >= 2 && what < 34) return diagnostics.events[what - 2];
    if (what == 64) return local()[0];
    if (what == 65) return local()[2];
    return 0xbad;
}
void Bind(unsigned *target)
{
    sink = target;
    for (unsigned i = 0; i < 34; ++i) sink[i] = ((volatile unsigned *)&diagnostics)[i];
}
