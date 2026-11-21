/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* PoP Phase D.1 / P017: the first Windows program run by Wine inside the separate native process.
 * Console subsystem, no user32: it must not need the display. Linked at the fixed PE32-style base 0x400000
 * (relocations kept, so a taken range still runs and the report shows where it landed). It reports what a
 * launcher/game pair needs from a real separate Windows process: its own image base, its own process id
 * (distinct from the desktop's), a named object in the shared namespace, and an exit code the native side
 * can check. Output: Z:\orbisdesk\process-p014\separate-d1.txt (Z: is /data). */
#include <windows.h>
#include <stdio.h>

int main(void)
{
    HANDLE mine = CreateMutexW(NULL, FALSE, L"Global\\OrbisSeparateD1");
    DWORD mine_err = GetLastError();
    FILE *f = fopen("Z:\\orbisdesk\\process-p014\\separate-d1.txt", "w");
    if (!f) return 3;
    fprintf(f, "{\"build\":\"P017\",\"event\":\"exe_running\",\"image_base\":\"%p\",\"pid\":%lu,\"tid\":%lu,"
               "\"mutex\":%d,\"mutex_err\":%lu,\"cmdline\":\"%s\"}\n",
            (void *)GetModuleHandleW(NULL), GetCurrentProcessId(), GetCurrentThreadId(),
            mine != NULL, mine_err, GetCommandLineA());
    fclose(f);
    return 42;
}
