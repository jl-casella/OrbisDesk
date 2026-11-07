/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* W179: "Wine Configuration" in the Start menu's Control Panel.
 *
 * That submenu lists the shell's Control Panel folder, which holds Control Panel applets (*.cpl
 * in system32), and winecfg is a program. This applet carries winecfg's icon (winecfgcpl.rc,
 * from programs/winecfg/winecfg.ico) and starts C:\windows\system32\winecfg.exe when opened.
 * If the start fails, a message box gives the error code. */
#include <windows.h>
#include <cpl.h>
#include <stdio.h>

#define IDI_WINECFG 1

static HINSTANCE module;

BOOL WINAPI DllMain( HINSTANCE instance, DWORD reason, void *reserved )
{
    if (reason == DLL_PROCESS_ATTACH) module = instance;
    return TRUE;
}

static void start_winecfg( HWND parent )
{
    WCHAR path[MAX_PATH], text[160];
    STARTUPINFOW si = {sizeof(si)};
    PROCESS_INFORMATION pi;
    UINT len = GetSystemDirectoryW( path, MAX_PATH );

    if (!len || len > MAX_PATH - 16) lstrcpyW( path, L"C:\\windows\\system32" );
    lstrcatW( path, L"\\winecfg.exe" );
    if (CreateProcessW( path, NULL, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi ))
    {
        /* W180: wait for winecfg's main thread. The applet runs in rundll32, and on the console
         * winecfg is a guest started from that guest: when rundll32 returned, its exit also ended
         * winecfg's thread before it drew anything (W179). Waiting for the thread is also right on
         * Windows; the process handle would not do here, since a guest's is the console's own. */
        WaitForSingleObject( pi.hThread, INFINITE );
        CloseHandle( pi.hThread );
        CloseHandle( pi.hProcess );
        return;
    }
    swprintf( text, ARRAYSIZE(text), L"Could not start winecfg.exe (error %lu).", GetLastError() );
    MessageBoxW( parent, text, L"Wine Configuration", MB_OK | MB_ICONERROR );
}

LONG CALLBACK CPlApplet( HWND hwnd, UINT message, LPARAM lparam1, LPARAM lparam2 )
{
    switch (message)
    {
    case CPL_INIT:
        return TRUE;
    case CPL_GETCOUNT:
        return 1;
    case CPL_INQUIRE:
    {
        CPLINFO *info = (CPLINFO *)lparam2;
        info->idIcon = IDI_WINECFG;
        info->idName = CPL_DYNAMIC_RES;
        info->idInfo = CPL_DYNAMIC_RES;
        info->lData = 0;
        return 0;
    }
    case CPL_NEWINQUIRE:
    {
        NEWCPLINFOW *info = (NEWCPLINFOW *)lparam2;
        info->dwSize = sizeof(*info);
        info->dwFlags = 0;
        info->dwHelpContext = 0;
        info->lData = 0;
        info->hIcon = LoadIconW( module, MAKEINTRESOURCEW(IDI_WINECFG) );
        lstrcpyW( info->szName, L"Wine Configuration" );
        lstrcpyW( info->szInfo, L"Windows version and DLL overrides per program" );
        info->szHelpFile[0] = 0;
        return 0;
    }
    case CPL_DBLCLK:
        start_winecfg( hwnd );
        return 0;
    }
    return 0;
}
