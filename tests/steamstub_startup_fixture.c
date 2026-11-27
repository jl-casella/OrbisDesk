/* SPDX-License-Identifier: LGPL-3.0-or-later */
#include <windows.h>
#include <winternl.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>
NTSTATUS WINAPI LdrGetDllHandle(WCHAR *, ULONG, UNICODE_STRING *, HMODULE *);
NTSTATUS WINAPI LdrGetProcedureAddress(HMODULE, ANSI_STRING *, ULONG, void **);
NTSTATUS WINAPI LdrLockLoaderLock(ULONG, ULONG *, ULONG_PTR *);
NTSTATUS WINAPI LdrUnlockLoaderLock(ULONG, ULONG_PTR);
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define ERR(...) fprintf(stderr, __VA_ARGS__)
#include "pw_guest_steamstub.inc.c"
#ifdef PW_STUB_VARIANT
extern void __cdecl mainCRTStartup(void);
__attribute__((section(".bind"))) void __cdecl pw_fixture_entry(void)
{
    mainCRTStartup(); /* fixture code only; the copied game bytes are never executed */
}
#endif

int main(int argc, char **argv)
{
    WCHAR marker[4096], value[8]; DWORD written;
    HANDLE file; BOOL result;
    HMODULE image = GetModuleHandleW(NULL);
#ifdef PW_STUB_VARIANT
    extern volatile unsigned char pw_fixture_bind[];
    (void)pw_fixture_bind[0]; /* retain the private, non-executed .bind test input */
#endif
    if (argc != 2) return 2;
    GetModuleFileNameW(image, marker, ARRAY_SIZE(marker));
    wcscat(marker, PW_STEAMSTUB_SUFFIX_W);
    DeleteFileW(marker);
    if (strcmp(argv[1], "disabled")) {
        const char *text = !strcmp(argv[1], "invalid") ? "invalid profile\n" : PW_STEAMSTUB_MAGIC;
        file = CreateFileW(marker, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, 0, NULL);
        if (file == INVALID_HANDLE_VALUE) return 3;
        if (!WriteFile(file, text, (DWORD)strlen(text), &written, NULL)) return 4;
        CloseHandle(file);
    }
    result = ps4_steamstub_start(image);
    if (!strcmp(argv[1], "disabled")) {
        if (!result || GetEnvironmentVariableW(L"PW_STUB_TEST_ATTACHED", value, ARRAY_SIZE(value))) return 5;
    } else if (!strcmp(argv[1], "loaded")) {
        if (!result || !GetEnvironmentVariableW(L"PW_STUB_TEST_ATTACHED", value, ARRAY_SIZE(value))) return 6;
        if (ps4_steamstub_start(image)) return 7; /* reject sharing the addon's static state */
    } else if (!strcmp(argv[1], "armed")) {
        ULONGLONG deadline = GetTickCount64() + 8000;
#ifdef _WIN64
        const WCHAR *addon_name = L"orbisdesk_steamstub_x64.dll";
#else
        const WCHAR *addon_name = L"orbisdesk_steamstub_x86.dll";
#endif
        if (!result || !GetModuleHandleW(addon_name)) return 9;
        (void)GetTickCount(); /* exercise a hook without executing any .bind code */
        while (GetModuleHandleW(addon_name) && GetTickCount64() < deadline) Sleep(20);
        if (GetModuleHandleW(addon_name)) return 10;
        (void)GetTickCount(); /* restored API must still work */
    } else if (result) return 8; /* missing DLL, bad marker, or unsupported real payload */
    DeleteFileW(marker);
    puts("PASS startup fixture");
    return 0;
}
