/* SPDX-License-Identifier: LGPL-2.1-or-later */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

static DWORD WINAPI worker(void *arg)
{
    DWORD value = 0;
    for (DWORD i = 1; i <= 1000; ++i) value += i;
    *(DWORD *)arg = value;
    return 0;
}

int main(void)
{
    DWORD value = 0, thread_exit = 99;
    HANDLE thread = CreateThread(NULL, 0, worker, &value, 0, NULL);
    if (!thread) return 10;
    DWORD waited = WaitForSingleObject(thread, 5000);
    BOOL got = GetExitCodeThread(thread, &thread_exit);
    CloseHandle(thread);
    if (waited != WAIT_OBJECT_0 || !got || thread_exit || value != 500500) return 11;
    HMODULE kernel = LoadLibraryA("kernel32.dll");
    if (!kernel || !GetProcAddress(kernel, "GetCurrentProcessId")) return 12;
    FreeLibrary(kernel);
    HANDLE file = CreateFileA("result.txt", GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
                              FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return 13;
    const char expected[] = "sum=500500;thread=ok;dll=ok\r\n";
    DWORD written = 0;
    BOOL ok = WriteFile(file, expected, sizeof(expected) - 1, &written, NULL);
    BOOL closed = CloseHandle(file);
    return ok && closed && written == sizeof(expected) - 1 ? 0 : 14;
}
