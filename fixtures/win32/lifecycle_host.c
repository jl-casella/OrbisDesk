/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include <windows.h>
typedef unsigned (__cdecl *touch_fn)(unsigned);
typedef unsigned (__cdecl *inspect_fn)(unsigned);
typedef void (__cdecl *bind_fn)(unsigned *);
static touch_fn touch;
static unsigned sink[34];
static DWORD WINAPI worker(void *unused)
{
    (void)unused;
    return touch(99) == 7 && touch(100) == 99 ? 0 : 1;
}
static unsigned run(void)
{
    HMODULE module = LoadLibraryA("lifecycle.dll");
    if (!module) return 10;
    union { FARPROC raw; touch_fn typed; } t = {GetProcAddress(module,"Touch")};
    union { FARPROC raw; inspect_fn typed; } i = {GetProcAddress(module,"Inspect")};
    union { FARPROC raw; bind_fn typed; } b = {GetProcAddress(module,"Bind")};
    touch = t.typed;
    inspect_fn inspect = i.typed;
    bind_fn bind = b.typed;
    if (!touch || !inspect || !bind) return 11;
    bind(sink);
    if (inspect(0)) return 0x100 + inspect(0);
    if (inspect(1) != 2) return 0x200 + inspect(1);
    if (inspect(65) != 2) return 0x300 + inspect(65);
    unsigned initial = touch(55);
    if (initial != 7) return 0x400 + initial;
    HANDLE thread = CreateThread(NULL,0,worker,NULL,0,NULL);
    if (!thread || WaitForSingleObject(thread,10000) != WAIT_OBJECT_0) return 13;
    DWORD result;
    if (!GetExitCodeThread(thread,&result) || result || !CloseHandle(thread)) return 14;
    if (inspect(64) != 55 || inspect(0)) return 15;
    if (!FreeLibrary(module)) return 16;
    const unsigned expected[] = {0x11,0x21,0x12,0x22,0x13,0x23,0x10,0x20};
    if (sink[0] || sink[1] != 8) return 17;
    for (unsigned i = 0; i < 8; ++i) if (sink[i+2] != expected[i]) return 18;
    SetLastError(0);
    module = LoadLibraryA("lifecycle-fail.dll");
    if (module || GetLastError() != ERROR_DLL_INIT_FAILED) return 19;
    return 42;
}
unsigned entry(void)
{
    unsigned result = run();
    if (result != 42) TerminateProcess(GetCurrentProcess(),result);
    return result;
}
