/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* B1 of the plan for 32-bit programs as guests of explorer (pe32-en-explorer-plan.md section 7): run as
 * a 64-bit guest of explorer (C:\orbis\wow64world64.exe [program.exe]), it creates the 32-bit world
 * of explorer's process and runs a 32-bit program in it twice, each time on a new WoW64 thread of
 * explorer, without relaunching the title. The program is C:\orbis\console32.exe unless given.
 * - world: maps C:\windows\syswow64\orbis32host.exe (the image of the 32-bit PEB) and asks ntdll
 *   for the world (NtSetInformationProcess class 1100), once per title run; a later run finds it.
 * - run 1, run 2: NtCreateThreadEx with flag 0x01000000 (a WoW64 thread) at the host's
 *   ps4_guest32_start, with a request below 2 GiB; waits for the thread and reads back the step the
 *   host reached and the program's exit code. For console32.exe, result.txt beside it must be
 *   rewritten with "sum=500500;thread=ok;dll=ok".
 * Every line goes to wow64world-result.txt beside this executable (appended, one block per run). */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <stdio.h>
#include <wchar.h>

typedef LONG NTSTATUS;
#define PW_PROCESS_WOW64_WORLD 1100
#define PW_THREAD_CREATE_WOW64 0x01000000
#define STATUS_IMAGE_NOT_AT_BASE ((NTSTATUS)0x40000003)
#define HOST_PATH L"C:\\windows\\syswow64\\orbis32host.exe"

struct pw_wow64_world_request   /* ntdll unix_private.h (tools/build-wow64-world-ps4.py) */
{
    ULONG64 host_base;
    ULONG64 world_peb;
    WCHAR   image_path[260];
};

struct guest32_request          /* fixtures/win32/orbis32host.c */
{
    WCHAR exe[MAX_PATH];
    WCHAR dir[MAX_PATH];
    DWORD stage;
    DWORD error;
    DWORD exit_code;
};

static NTSTATUS (NTAPI *pNtCreateSection)( HANDLE *, ACCESS_MASK, void *, LARGE_INTEGER *, ULONG, ULONG, HANDLE );
static NTSTATUS (NTAPI *pNtMapViewOfSection)( HANDLE, HANDLE, void **, ULONG_PTR, SIZE_T, LARGE_INTEGER *, SIZE_T *,
                                              DWORD, ULONG, ULONG );
static NTSTATUS (NTAPI *pNtUnmapViewOfSection)( HANDLE, void * );
static NTSTATUS (NTAPI *pNtSetInformationProcess)( HANDLE, ULONG, void *, ULONG );
static NTSTATUS (NTAPI *pNtCreateThreadEx)( HANDLE *, ACCESS_MASK, void *, HANDLE, void *, void *, ULONG, ULONG_PTR,
                                            SIZE_T, SIZE_T, void * );
static NTSTATUS (NTAPI *pNtAllocateVirtualMemory)( HANDLE, void **, ULONG_PTR, SIZE_T *, ULONG, ULONG );
static NTSTATUS (NTAPI *pNtFreeVirtualMemory)( HANDLE, void **, SIZE_T *, ULONG );
static FILE *out;

static void *host_export( ULONG_PTR base, const char *name )
{
    IMAGE_NT_HEADERS32 *nt = (IMAGE_NT_HEADERS32 *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    IMAGE_DATA_DIRECTORY *dir = &nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXPORT];
    IMAGE_EXPORT_DIRECTORY *exports;
    DWORD *names, *functions, i;
    WORD *ordinals;

    if (!dir->VirtualAddress) return NULL;
    exports = (IMAGE_EXPORT_DIRECTORY *)(base + dir->VirtualAddress);
    names = (DWORD *)(base + exports->AddressOfNames);
    ordinals = (WORD *)(base + exports->AddressOfNameOrdinals);
    functions = (DWORD *)(base + exports->AddressOfFunctions);
    for (i = 0; i < exports->NumberOfNames; i++)
        if (!strcmp( (const char *)(base + names[i]), name )) return (void *)(base + functions[ordinals[i]]);
    return NULL;
}

/* the world, created by this run or found from an earlier one; returns the host's base */
static ULONG_PTR world(void)
{
    struct pw_wow64_world_request req = { 0 };
    HANDLE file, section;
    void *base = NULL;
    SIZE_T size = 0;
    NTSTATUS status;

    status = pNtSetInformationProcess( GetCurrentProcess(), PW_PROCESS_WOW64_WORLD, &req, sizeof(req) );
    if (!status)
    {
        ULONG_PTR host = *(ULONG *)(ULONG_PTR)(req.world_peb + 8);  /* PEB32.ImageBaseAddress */
        fprintf( out, "world existing peb32=%#llx host=%#llx\n", req.world_peb, (ULONGLONG)host );
        return host;
    }
    if (status != (NTSTATUS)0xc0000225 /* STATUS_NOT_FOUND */)
    {
        fprintf( out, "world unsupported status=%#lx (ntdll without B1?)\n", (unsigned long)status );
        return 0;
    }
    file = CreateFileW( HOST_PATH, GENERIC_READ | GENERIC_EXECUTE, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL );
    if (file == INVALID_HANDLE_VALUE)
    {
        fprintf( out, "world host_missing error=%lu\n", GetLastError() );
        return 0;
    }
    status = pNtCreateSection( &section, SECTION_MAP_READ | SECTION_MAP_EXECUTE | SECTION_QUERY, NULL, NULL,
                               PAGE_EXECUTE_READ, SEC_IMAGE, file );
    CloseHandle( file );
    if (status)
    {
        fprintf( out, "world host_section status=%#lx\n", (unsigned long)status );
        return 0;
    }
    status = pNtMapViewOfSection( section, GetCurrentProcess(), &base, 0, 0, NULL, &size, 1 /* ViewShare */, 0,
                                  PAGE_EXECUTE_READ );
    CloseHandle( section );
    fprintf( out, "world host_mapped status=%#lx base=%p size=%#llx\n", (unsigned long)status, base, (ULONGLONG)size );
    if (status == STATUS_IMAGE_NOT_AT_BASE || (status >= 0 && (ULONG_PTR)base != 0x30000000))
    {
        fprintf( out, "world host_not_at_base: 0x30000000 is taken in this process\n" );
        pNtUnmapViewOfSection( GetCurrentProcess(), base );
        return 0;
    }
    if (status < 0) return 0;
    req.host_base = (ULONG_PTR)base;
    wcscpy( req.image_path, HOST_PATH );
    status = pNtSetInformationProcess( GetCurrentProcess(), PW_PROCESS_WOW64_WORLD, &req, sizeof(req) );
    fprintf( out, "world created status=%#lx peb32=%#llx\n", (unsigned long)status, req.world_peb );
    if (status)
    {
        pNtUnmapViewOfSection( GetCurrentProcess(), base );
        return 0;
    }
    return (ULONG_PTR)base;
}

static void read_result( const WCHAR *path, char *text, DWORD size, FILETIME *written )
{
    WIN32_FILE_ATTRIBUTE_DATA data;
    HANDLE file;
    DWORD got = 0, i;

    text[0] = 0;
    memset( written, 0, sizeof(*written) );
    if (GetFileAttributesExW( path, GetFileExInfoStandard, &data )) *written = data.ftLastWriteTime;
    file = CreateFileW( path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL );
    if (file == INVALID_HANDLE_VALUE) return;
    ReadFile( file, text, size - 1, &got, NULL );
    CloseHandle( file );
    text[got] = 0;
    for (i = 0; i < got; i++) if (text[i] == '\r' || text[i] == '\n') text[i] = ' ';
}

static void guest_run( int number, ULONG_PTR host, const WCHAR *exe, const WCHAR *dir, BOOL console32 )
{
    struct guest32_request *req = NULL;
    SIZE_T size = sizeof(*req);
    WCHAR result_path[MAX_PATH];
    char before[256], after[256];
    FILETIME written_before, written_after;
    void *entry = host_export( host, "ps4_guest32_start" );
    HANDLE thread = NULL;
    DWORD waited, thread_exit = 0, start = GetTickCount();
    NTSTATUS status;

    if (!entry)
    {
        fprintf( out, "guest32 run=%d no ps4_guest32_start in the host\n", number );
        return;
    }
    status = pNtAllocateVirtualMemory( GetCurrentProcess(), (void **)&req, 0x7fffffff, &size, MEM_RESERVE | MEM_COMMIT,
                                       PAGE_READWRITE );
    if (status)
    {
        fprintf( out, "guest32 run=%d request_alloc status=%#lx\n", number, (unsigned long)status );
        return;
    }
    wcscpy( req->exe, exe );
    wcscpy( req->dir, dir );
    swprintf( result_path, MAX_PATH, L"%ls\\result.txt", dir );
    /* W235: a sentinel the program must overwrite. W234's second run wrote the same text within the
     * same second, and the last-write time could not tell it (rewritten=0) */
    if (console32)
    {
        HANDLE file = CreateFileW( result_path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, 0, NULL );
        DWORD wrote;

        if (file != INVALID_HANDLE_VALUE)
        {
            WriteFile( file, "pending", 7, &wrote, NULL );
            CloseHandle( file );
        }
        read_result( result_path, before, sizeof(before), &written_before );
    }

    status = pNtCreateThreadEx( &thread, THREAD_ALL_ACCESS, NULL, GetCurrentProcess(), entry, req,
                                PW_THREAD_CREATE_WOW64, 0, 0, 0x200000, NULL );
    fprintf( out, "guest32 run=%d thread status=%#lx entry=%p request=%p\n", number, (unsigned long)status, entry, req );
    fflush( out );
    if (status) return;  /* the request stays: nothing else may hold it */
    waited = WaitForSingleObject( thread, 120000 );
    GetExitCodeThread( thread, &thread_exit );
    CloseHandle( thread );
    fprintf( out, "guest32 run=%d wait=%s ms=%lu thread_exit=%#lx stage=%lu error=%lu exit_code=%lu\n", number,
             waited == WAIT_OBJECT_0 ? "ended" : "timeout", GetTickCount() - start, thread_exit, req->stage,
             req->error, req->exit_code );
    if (console32)
    {
        read_result( result_path, after, sizeof(after), &written_after );
        fprintf( out, "guest32 run=%d result=\"%s\" before=\"%s\" rewritten=%d expected=%d\n", number, after, before,
                 !strcmp( before, "pending" ) && strcmp( after, "pending" ) != 0,
                 !strcmp( after, "sum=500500;thread=ok;dll=ok  " ) );
    }
    if (waited == WAIT_OBJECT_0)
    {
        size = 0;
        pNtFreeVirtualMemory( GetCurrentProcess(), (void **)&req, &size, MEM_RELEASE );
    }
}

int WINAPI WinMain( HINSTANCE instance, HINSTANCE previous, LPSTR command, int show )
{
    HMODULE ntdll = GetModuleHandleW( L"ntdll.dll" );
    WCHAR path[MAX_PATH], exe[MAX_PATH] = L"C:\\orbis\\console32.exe", dir[MAX_PATH], *slash, **argv;
    SYSTEMTIME now;
    ULONG_PTR host;
    int argc, i;

    GetModuleFileNameW( NULL, path, MAX_PATH );
    if ((slash = wcsrchr( path, '\\' ))) wcscpy( slash + 1, L"wow64world-result.txt" );
    if (!(out = _wfopen( path, L"a" ))) return 1;
    if ((argv = CommandLineToArgvW( GetCommandLineW(), &argc )) && argc > 1) lstrcpynW( exe, argv[1], MAX_PATH );
    wcscpy( dir, exe );
    if ((slash = wcsrchr( dir, '\\' ))) *slash = 0;
    GetLocalTime( &now );
    fprintf( out, "run %04u-%02u-%02u %02u:%02u:%02u pid=%lu program=%ls\n", now.wYear, now.wMonth, now.wDay,
             now.wHour, now.wMinute, now.wSecond, GetCurrentProcessId(), exe );

#define GET(name) p##name = (void *)GetProcAddress( ntdll, #name )
    GET( NtCreateSection );
    GET( NtMapViewOfSection );
    GET( NtUnmapViewOfSection );
    GET( NtSetInformationProcess );
    GET( NtCreateThreadEx );
    GET( NtAllocateVirtualMemory );
    GET( NtFreeVirtualMemory );
#undef GET
    if ((host = world()))
    {
        fflush( out );
        for (i = 1; i <= 2; i++)
        {
            guest_run( i, host, exe, dir, !_wcsicmp( wcsrchr( exe, '\\' ) ? wcsrchr( exe, '\\' ) + 1 : exe,
                                                     L"console32.exe" ) );
            fflush( out );
        }
    }
    fprintf( out, "end\n" );
    fclose( out );
    return 0;
}
