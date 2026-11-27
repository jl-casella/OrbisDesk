/* SPDX-License-Identifier: LGPL-3.0-or-later
 * Loaded before the EXE entry, with its guest context already installed. Also
 * called for a real Wine process after loader_init releases the loader lock.
 * Resolve kernelbase dynamically: ntdll must not acquire a static import cycle.
 */
#include "pw_steamstub_profile.h"
static BOOL ps4_steamstub_start( HMODULE image )
{
    UNICODE_STRING kb_name;
    ANSI_STRING proc;
    HMODULE kb, addon;
    HANDLE file;
    WCHAR path[4096];
    char marker[sizeof(PW_STEAMSTUB_MAGIC)];
    DWORD count, length;
    BOOL read_ok;
    ULONG_PTR loader_cookie;
    DWORD (WINAPI *get_name)(HMODULE, WCHAR *, DWORD);
    HANDLE (WINAPI *open_file)(const WCHAR *, DWORD, DWORD, SECURITY_ATTRIBUTES *, DWORD, DWORD, HANDLE);
    BOOL (WINAPI *read_file)(HANDLE, void *, DWORD, DWORD *, OVERLAPPED *);
    BOOL (WINAPI *close_handle)(HANDLE);
    DWORD (WINAPI *get_error)(void);
    HMODULE (WINAPI *get_module)(const WCHAR *);
    HMODULE (WINAPI *load_library)(const WCHAR *, HANDLE, DWORD);
#ifdef _WIN64
    const WCHAR *name = L"orbisdesk_steamstub_x64.dll";
    const WCHAR *library = L"C:\\orbis\\steam\\coldclient\\orbisdesk_steamstub_x64.dll";
#else
    const WCHAR *name = L"orbisdesk_steamstub_x86.dll";
    const WCHAR *library = L"C:\\orbis\\steam\\coldclient\\orbisdesk_steamstub_x86.dll";
#endif
    RtlInitUnicodeString( &kb_name, L"kernelbase.dll" );
    if (LdrGetDllHandle( NULL, 0, &kb_name, &kb )) return TRUE; /* very early system processes */
#define PW_STUB_PROC(variable, spelling) do { \
    RtlInitAnsiString( &proc, spelling ); \
    if (LdrGetProcedureAddress( kb, &proc, 0, (void **)&variable )) return FALSE; \
} while (0)
    PW_STUB_PROC(get_name, "GetModuleFileNameW");
    PW_STUB_PROC(open_file, "CreateFileW");
    PW_STUB_PROC(read_file, "ReadFile");
    PW_STUB_PROC(close_handle, "CloseHandle");
    PW_STUB_PROC(get_error, "GetLastError");
    PW_STUB_PROC(get_module, "GetModuleHandleW");
    PW_STUB_PROC(load_library, "LoadLibraryExW");
#undef PW_STUB_PROC
    length = get_name( image, path, ARRAY_SIZE(path) );
    if (!length || length >= ARRAY_SIZE(path) - ARRAY_SIZE(PW_STEAMSTUB_SUFFIX_W)) return TRUE;
    memcpy( path + length, PW_STEAMSTUB_SUFFIX_W, sizeof(PW_STEAMSTUB_SUFFIX_W) );
    file = open_file( path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL );
    if (file == INVALID_HANDLE_VALUE)
    {
        DWORD error = get_error();
        if (error == ERROR_FILE_NOT_FOUND || error == ERROR_PATH_NOT_FOUND) return TRUE;
        ERR( "PWSTUB startup profile_open_failed module=%p error=%lu\n", image, error );
        return FALSE;
    }
    read_ok = read_file( file, marker, sizeof(marker), &count, NULL );
    close_handle( file );
    if (!read_ok || count != sizeof(PW_STEAMSTUB_MAGIC) - 1 ||
        memcmp( marker, PW_STEAMSTUB_MAGIC, sizeof(PW_STEAMSTUB_MAGIC) - 1 ))
    {
        ERR( "PWSTUB startup invalid_profile module=%p\n", image );
        return FALSE;
    }
    /* The addon owns temporary process-wide hooks and self-unloads. Do not share
     * its static EXE identity with a second guest, or retain a second DLL ref. */
    if (LdrLockLoaderLock( 0, NULL, &loader_cookie )) return FALSE;
    if (get_module( name ))
    {
        ERR( "PWSTUB startup addon_busy module=%p\n", image );
        LdrUnlockLoaderLock( 0, loader_cookie );
        return FALSE;
    }
    ERR( "PWSTUB startup begin module=%p\n", image );
    addon = load_library( library, NULL, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS );
    count = addon ? 0 : get_error();
    LdrUnlockLoaderLock( 0, loader_cookie );
    if (!addon)
    {
        ERR( "PWSTUB startup load_failed module=%p error=%lu\n", image, count );
        return FALSE;
    }
    /* Loaded/armed is not proof of a matched variant. The addon reports matched,
     * write_failed, restore and not_armed in its own startup log. */
    ERR( "PWSTUB startup loaded module=%p addon=%p\n", image, addon );
    return TRUE;
}
