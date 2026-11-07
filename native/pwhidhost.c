/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* pwhidhost.dll: Wine's HID stack inside the OrbisDesk process (tools/build-hidstack-hw.py).
 *
 * On a PC, winedevice.exe hosts winebus.sys, winehid.sys, winexinput.sys and hidclass.sys, started
 * as services. A PS4 title has one process and no service manager, so explorer loads this DLL and
 * it does what winedevice's ServiceMain does: a thread runs ntoskrnl's IRP loop and another loads
 * winebus.sys. ntoskrnl then enumerates winebus's root device and the HID devices it reports, and
 * installs their drivers from the prefix's INF files. winebus's Unix side (native/winebus_orbis.c)
 * reports the console's pad as an Xbox 360 controller; winexinput.sys gives it the "&IG_00" HID
 * device that Unity and SDL look for in the raw input list.
 * ntoskrnl.exe loads drivers by service registry key without SCM in this package (its overlay).
 * Every step logs a PWHID line through OutputDebugStringA; a failure stops the host, not explorer. */
#include <windows.h>
#include <winternl.h>
#include <stdarg.h>
#include <stdio.h>
#include <wchar.h>

typedef LONG (WINAPI *ZwLoadDriverFn)(const UNICODE_STRING *);
typedef LONG (__cdecl *MainLoopFn)(HANDLE);

static ZwLoadDriverFn load_driver;
static MainLoopFn main_loop;
static HANDLE stop_event;

static void log_line(const char *format,...)
{
    char line[512];va_list args;
    va_start(args,format);vsnprintf(line,sizeof(line),format,args);va_end(args);
    OutputDebugStringA(line);
}

/* winexinput.inf installs its driver as the service "xinput". wineboot only adds a service when it
 * installs a device, and the prefix was made on a host without an XInput pad, so the key is created
 * here, as that INF's svc_section would (setupapi cannot: CreateService needs the service manager). */
static BOOL ensure_xinput_service(void)
{
    static const WCHAR key_name[]=L"System\\CurrentControlSet\\Services\\xinput";
    static const WCHAR image[]=L"C:\\windows\\system32\\drivers\\winexinput.sys";
    static const WCHAR group[]=L"WinePlugPlay",display[]=L"Wine XInput",description[]=L"Wine XInput device driver";
    DWORD type=1,start=3,error_control=1,disposition;HKEY key;LONG rc;
    rc=RegCreateKeyExW(HKEY_LOCAL_MACHINE,key_name,0,NULL,0,KEY_ALL_ACCESS,NULL,&key,&disposition);
    if(rc) {log_line("PWHID xinput_service create error=%ld",rc);return FALSE;}
    if(disposition==REG_CREATED_NEW_KEY) {
        rc=RegSetValueExW(key,L"ImagePath",0,REG_EXPAND_SZ,(const BYTE *)image,sizeof(image));
        if(!rc) rc=RegSetValueExW(key,L"Group",0,REG_SZ,(const BYTE *)group,sizeof(group));
        if(!rc) rc=RegSetValueExW(key,L"DisplayName",0,REG_SZ,(const BYTE *)display,sizeof(display));
        if(!rc) rc=RegSetValueExW(key,L"Description",0,REG_SZ,(const BYTE *)description,sizeof(description));
        if(!rc) rc=RegSetValueExW(key,L"Type",0,REG_DWORD,(const BYTE *)&type,sizeof(type));
        if(!rc) rc=RegSetValueExW(key,L"Start",0,REG_DWORD,(const BYTE *)&start,sizeof(start));
        if(!rc) rc=RegSetValueExW(key,L"ErrorControl",0,REG_DWORD,(const BYTE *)&error_control,sizeof(error_control));
    }
    RegCloseKey(key);
    log_line("PWHID xinput_service %s error=%ld",disposition==REG_CREATED_NEW_KEY?"created":"present",rc);
    return !rc;
}

static DWORD WINAPI irp_loop(void *arg)
{
    LONG status;
    log_line("PWHID irp_loop start");
    status=main_loop(stop_event);
    log_line("PWHID irp_loop exit status=%#lx",(unsigned long)status);
    return 0;
}

static DWORD WINAPI host_thread(void *arg)
{
    static WCHAR service[]=L"\\Registry\\Machine\\System\\CurrentControlSet\\Services\\winebus";
    UNICODE_STRING name={sizeof(service)-sizeof(WCHAR),sizeof(service),service};
    WCHAR drivers[MAX_PATH];HMODULE ntoskrnl;HANDLE loop,ready;DWORD wait;LONG status;
    /* W202: C:\orbis\nohid.txt turns the stack off without a rebuild, to compare a game with and
     * without it; nothing of ntoskrnl is loaded then */
    if(GetFileAttributesW(L"C:\\orbis\\nohid.txt")!=INVALID_FILE_ATTRIBUTES) {log_line("PWHID disabled by C:\\orbis\\nohid.txt");return 0;}
    if(!ensure_xinput_service()) return 1;
    if(!(ntoskrnl=LoadLibraryW(L"ntoskrnl.exe"))) {log_line("PWHID ntoskrnl load error=%lu",GetLastError());return 1;}
    load_driver=(ZwLoadDriverFn)GetProcAddress(ntoskrnl,"ZwLoadDriver");
    main_loop=(MainLoopFn)GetProcAddress(ntoskrnl,"wine_ntoskrnl_main_loop");
    if(!load_driver || !main_loop) {log_line("PWHID ntoskrnl exports missing load=%p loop=%p",load_driver,main_loop);return 1;}
    if(GetSystemDirectoryW(drivers,MAX_PATH-9)) {wcscat(drivers,L"\\drivers");AddDllDirectory(drivers);}
    if(!(stop_event=CreateEventW(NULL,TRUE,FALSE,NULL))) {log_line("PWHID event error=%lu",GetLastError());return 1;}
    /* the IRP loop starts ntoskrnl's PnP manager, which loading a driver needs; ntoskrnl's overlay
     * sets this event once it has (winedevice gets the same order from the service manager) */
    if(!(ready=CreateEventW(NULL,TRUE,FALSE,L"PwNtoskrnlPnpReady"))) {log_line("PWHID ready event error=%lu",GetLastError());return 1;}
    if(!(loop=CreateThread(NULL,0,irp_loop,NULL,0,NULL))) {log_line("PWHID loop thread error=%lu",GetLastError());return 1;}
    CloseHandle(loop);
    if((wait=WaitForSingleObject(ready,10000))) {log_line("PWHID pnp_ready wait=%lu error=%lu",wait,GetLastError());return 1;}
    status=load_driver(&name);
    log_line("PWHID winebus load status=%#lx",(unsigned long)status);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,void *reserved)
{
    if(reason==DLL_PROCESS_ATTACH) {
        HANDLE thread;
        DisableThreadLibraryCalls(instance);
        /* the thread runs once the loader lock is released */
        if((thread=CreateThread(NULL,0,host_thread,NULL,0,NULL))) CloseHandle(thread);
        else log_line("PWHID host thread error=%lu",GetLastError());
    }
    return TRUE;
}
