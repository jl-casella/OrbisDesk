/* SPDX-License-Identifier: GPL-3.0-or-later */
/* C:\orbis\steam-open.exe: "Open Steam Client" in OrbisDesk's Start menu and on its Desktop. A 64-bit
 * guest that asks the title's native side to open the Steam client (native/steam/steam_client.cpp,
 * pw_hw_steam_open), through the same channel kernelbase's overlay closer uses (tools/build-guest-hw.py
 * ps4_overlay_call, W239): xinput1_3's Unix library, call 3 (unix_pad_profile), whose 260-byte name
 * native/hw_pad.c reads as a request ("<steam-open>") and answers in place ("opened", "busy",
 * "error ..."). The client then takes the screen and the pad until it exits; this program ends at once.
 * Built by tools/build-steam-hosted.py with x86_64-w64-mingw32-gcc. */
#include <windows.h>
#include <winternl.h>

#include <string.h>

/* Wine's MemoryWineLoadUnixLibByName (include/winternl.h), and the pad profile call's parameters
 * (tools/build-xinput-hw.py, struct xinput_profile_params) */
#define MEMORY_WINE_LOAD_UNIX_LIB_BY_NAME 1002
struct pad_profile_params {
    char exe[260];
    UINT32 load;
};
typedef NTSTATUS(WINAPI *unix_call_dispatcher)(UINT64 handle, unsigned int code, void *args);
NTSTATUS WINAPI NtQueryVirtualMemory(HANDLE process, LPCVOID address, ULONG klass, PVOID buffer, SIZE_T length,
                                     SIZE_T *result);

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command, int show)
{
    (void)instance;
    (void)previous;
    (void)command;
    (void)show;
    UNICODE_STRING name;
    RtlInitUnicodeString(&name, L"xinput1_3");
    UINT64 result[2] = {0};
    void **dispatcher = (void **)GetProcAddress(GetModuleHandleW(L"ntdll.dll"), "__wine_unix_call_dispatcher");
    const NTSTATUS status = NtQueryVirtualMemory(GetCurrentProcess(), &name, MEMORY_WINE_LOAD_UNIX_LIB_BY_NAME, result,
                                                 sizeof(result), NULL);
    if (status || !dispatcher || !*dispatcher) {
        MessageBoxW(NULL, L"OrbisDesk's native side could not be reached: the Steam client is not available here.",
                    L"Open Steam Client", MB_OK | MB_ICONERROR);
        return 1;
    }
    struct pad_profile_params params;
    memset(&params, 0, sizeof(params));
    strcpy(params.exe, "<steam-open>");
    if (((unix_call_dispatcher)*dispatcher)(result[1], 3, &params)) {
        MessageBoxW(NULL, L"The request to open the Steam client failed.", L"Open Steam Client", MB_OK | MB_ICONERROR);
        return 1;
    }
    params.exe[sizeof(params.exe) - 1] = 0;
    if (!strcmp(params.exe, "opened") || !strcmp(params.exe, "busy")) return 0;
    char text[300];
    lstrcpynA(text, "The Steam client did not open: ", sizeof(text));
    lstrcatA(text, params.exe);
    MessageBoxA(NULL, text, "Open Steam Client", MB_OK | MB_ICONERROR);
    return 1;
}
