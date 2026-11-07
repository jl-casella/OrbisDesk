/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* B1 of the plan for 32-bit programs as guests of explorer (pe32-en-explorer-plan.md P5): the image of
 * the 32-bit world's PEB, C:\windows\syswow64\orbis32host.exe. The 32-bit loader keeps one state for
 * the whole 32-bit world (its PEB, module list, lock and heap), so its main module is this image and
 * never a game, as explorer's PEB names explorer and not its 64-bit guests. explorer maps it, creates
 * the world (ntdll PW_PROCESS_WOW64_WORLD) and starts each 32-bit program on a WoW64 thread at
 * ps4_guest32_start with a request below 4 GiB (C:\orbis\wow64world64.exe for now; the kernelbase
 * bridge, P7, later).
 * For B1 the program runs as console32.exe needs. The stock 32-bit ntdll leaves an EXE loaded as a
 * module unrelocated and unresolved and calls its entry as DllMain (W052/W053 in 64 bits), so the
 * EXE is loaded with DONT_RESOLVE_DLL_REFERENCES, relocated and resolved here, and its kernel32
 * ExitProcess points at guest_exit_process, which ends the program and not the process. The guest
 * model of the 64-bit guests (TEB.UserReserved, GetModuleHandle(NULL), the command line, TLS,
 * files, memory) comes to 32 bits with P6. Every step leaves a "PWWOW guest32" line in the run log
 * and the step reached in the request.
 * W235 (P6/P7): ps4_guest32_launch is the bridge's entry. explorer's kernelbase (CreateProcessInternalW
 * with a PE32) starts it on a WoW64 thread; it calls the 32-bit CreateProcessW, whose kernelbase is the
 * guest one of wine/lib/wine/i386-guest (tools/build-guest-hw.py), so the program runs as a 32-bit guest
 * with the same model as the 64-bit ones, and returns its first thread. ps4_guest32_start (B1) stays
 * for C:\orbis\wow64world64.exe. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdarg.h>

struct guest32_request     /* fixtures/win32/wow64world.c */
{
    WCHAR exe[MAX_PATH];
    WCHAR dir[MAX_PATH];
    DWORD stage;           /* 1 start, 2 directory set, 3 loaded, 4 relocated, 5 resolved, 6 ended */
    DWORD error;           /* the error of the step that failed */
    DWORD exit_code;
};

#define MAX_IMPORTS 64

static int (__cdecl *dbg_output)( const char *str );
static int (__cdecl *format)( char *buffer, size_t size, const char *fmt, va_list args );
/* one program at a time for now: the exit jump, and what it loaded (P6 keeps them per guest) */
static void *exit_jump[5];
static DWORD exit_thread, exit_value;
static HMODULE loaded[MAX_IMPORTS];
static int loaded_count;

/* -nostdlib: the compiler may still emit calls to these */
void *memset( void *dst, int c, size_t n )
{
    unsigned char *p = dst;
    while (n--) *p++ = c;
    return dst;
}

void *memcpy( void *dst, const void *src, size_t n )
{
    unsigned char *d = dst;
    const unsigned char *s = src;
    while (n--) *d++ = *s++;
    return dst;
}

static void trace( const char *fmt, ... )
{
    char line[512];
    va_list args;

    if (!dbg_output || !format) return;
    va_start( args, fmt );
    format( line, sizeof(line) - 1, fmt, args );
    va_end( args );
    line[sizeof(line) - 1] = 0;
    dbg_output( line );
}

static void narrow( char *dst, const WCHAR *src, int size )
{
    int i;
    for (i = 0; i < size - 1 && src[i]; i++) dst[i] = src[i] < 0x80 ? (char)src[i] : '?';
    dst[i] = 0;
}

static IMAGE_NT_HEADERS32 *headers( HMODULE module )
{
    return (IMAGE_NT_HEADERS32 *)((char *)module + ((IMAGE_DOS_HEADER *)module)->e_lfanew);
}

/* ExitProcess of the program, through its import table: its own thread goes back to
 * ps4_guest32_start; another one of its threads ends (the whole program ending from another
 * thread is P6). */
static void WINAPI guest_exit_process( UINT code )
{
    if (GetCurrentThreadId() == exit_thread)
    {
        exit_value = code;
        __builtin_longjmp( exit_jump, 1 );
    }
    trace( "PWWOW guest32 ExitProcess(%u) on thread %lu, not the program's first: that thread ends\n",
           code, GetCurrentThreadId() );
    ExitThread( code );
}

/* the loader does not relocate an EXE loaded as a module (only HIGHLOW, what 32-bit images use) */
static DWORD relocate( HMODULE module )
{
    IMAGE_NT_HEADERS32 *nt = headers( module );
    IMAGE_DATA_DIRECTORY *dir = &nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_BASERELOC];
    DWORD delta = (DWORD)module - nt->OptionalHeader.ImageBase;
    IMAGE_BASE_RELOCATION *block, *end;
    DWORD count = 0;

    if (!delta) return 0;
    if (!dir->VirtualAddress || (nt->FileHeader.Characteristics & IMAGE_FILE_RELOCS_STRIPPED))
    {
        trace( "PWWOW guest32 not at its base %#lx (at %p) and has no relocations\n", nt->OptionalHeader.ImageBase, module );
        return ERROR_BAD_EXE_FORMAT;
    }
    block = (IMAGE_BASE_RELOCATION *)((char *)module + dir->VirtualAddress);
    end = (IMAGE_BASE_RELOCATION *)((char *)block + dir->Size);
    while (block < end && block->SizeOfBlock)
    {
        char *page = (char *)module + block->VirtualAddress;
        WORD *entry = (WORD *)(block + 1);
        WORD *last = (WORD *)((char *)block + block->SizeOfBlock);
        DWORD old;

        if (!VirtualProtect( page, 0x2000, PAGE_READWRITE, &old )) return GetLastError();
        for (; entry < last; entry++)
        {
            switch (*entry >> 12)
            {
            case IMAGE_REL_BASED_ABSOLUTE: break;
            case IMAGE_REL_BASED_HIGHLOW: *(DWORD *)(page + (*entry & 0xfff)) += delta; count++; break;
            default:
                trace( "PWWOW guest32 relocation type %u not handled\n", *entry >> 12 );
                return ERROR_BAD_EXE_FORMAT;
            }
        }
        VirtualProtect( page, 0x2000, old, &old );
        block = (IMAGE_BASE_RELOCATION *)last;
    }
    trace( "PWWOW guest32 relocated by %#lx: %lu fixups\n", delta, count );
    return 0;
}

static DWORD resolve( HMODULE module, int *patched )
{
    IMAGE_NT_HEADERS32 *nt = headers( module );
    IMAGE_DATA_DIRECTORY *dir = &nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    FARPROC exit_process = GetProcAddress( GetModuleHandleA( "kernel32.dll" ), "ExitProcess" );
    IMAGE_IMPORT_DESCRIPTOR *imp;

    if (!dir->VirtualAddress) return 0;
    for (imp = (IMAGE_IMPORT_DESCRIPTOR *)((char *)module + dir->VirtualAddress); imp->Name; imp++)
    {
        const char *name = (const char *)module + imp->Name;
        IMAGE_THUNK_DATA32 *lookup = (IMAGE_THUNK_DATA32 *)((char *)module +
                                     (imp->OriginalFirstThunk ? imp->OriginalFirstThunk : imp->FirstThunk));
        IMAGE_THUNK_DATA32 *iat = (IMAGE_THUNK_DATA32 *)((char *)module + imp->FirstThunk);
        DWORD old, entries = 0, i;
        HMODULE dll;

        while (lookup[entries].u1.AddressOfData) entries++;
        if (!(dll = LoadLibraryA( name )))
        {
            DWORD error = GetLastError();
            trace( "PWWOW guest32 import %s not loaded error=%lu\n", name, error );
            return error ? error : ERROR_MOD_NOT_FOUND;
        }
        if (loaded_count < MAX_IMPORTS) loaded[loaded_count++] = dll;
        if (!VirtualProtect( iat, entries * sizeof(*iat) + 1, PAGE_READWRITE, &old )) return GetLastError();
        for (i = 0; i < entries; i++)
        {
            DWORD value = lookup[i].u1.AddressOfData;
            FARPROC proc;

            if (IMAGE_SNAP_BY_ORDINAL32( value ))
                proc = GetProcAddress( dll, (const char *)(ULONG_PTR)IMAGE_ORDINAL32( value ) );
            else
                proc = GetProcAddress( dll, (const char *)((IMAGE_IMPORT_BY_NAME *)((char *)module + value))->Name );
            if (!proc)
            {
                trace( "PWWOW guest32 import %s entry %lu not found\n", name, i );
                return ERROR_PROC_NOT_FOUND;
            }
            if (proc == exit_process)
            {
                proc = (FARPROC)guest_exit_process;
                (*patched)++;
            }
            iat[i].u1.Function = (DWORD)proc;
        }
        VirtualProtect( iat, entries * sizeof(*iat) + 1, old, &old );
    }
    return 0;
}

static DWORD fail( struct guest32_request *req, DWORD error, const char *step )
{
    char exe[MAX_PATH];

    narrow( exe, req->exe, sizeof(exe) );
    req->error = error ? error : ERROR_GEN_FAILURE;
    trace( "PWWOW guest32 failed exe=%s step=%s stage=%lu error=%lu\n", exe, step, req->stage, req->error );
    return 0xc0000000 | req->error;
}

__declspec(dllexport) DWORD WINAPI ps4_guest32_start( struct guest32_request *req )
{
    HMODULE ntdll = GetModuleHandleA( "ntdll.dll" );
    struct guest32_request *volatile request = req;
    HMODULE volatile module;
    NT_TIB *volatile tib;
    void *volatile seh;
    IMAGE_NT_HEADERS32 *nt;
    char exe[MAX_PATH];
    int patched = 0;
    DWORD error, code;
    void *entry;

    dbg_output = (void *)GetProcAddress( ntdll, "__wine_dbg_output" );
    format = (void *)GetProcAddress( ntdll, "_vsnprintf" );
    __asm__ volatile( "movl %%fs:0x18,%0" : "=r" (tib) );
    narrow( exe, req->exe, sizeof(exe) );
    loaded_count = 0;
    req->stage = 1;
    trace( "PWWOW guest32 start exe=%s thread=%lu teb32=%p\n", exe, GetCurrentThreadId(), tib );
    if (!SetCurrentDirectoryW( req->dir )) return fail( req, GetLastError(), "directory" );
    req->stage = 2;
    if (!(module = LoadLibraryExW( req->exe, NULL, DONT_RESOLVE_DLL_REFERENCES )))
        return fail( req, GetLastError(), "load" );
    nt = headers( module );
    trace( "PWWOW guest32 loaded exe=%s at %p base=%#lx entry_rva=%#lx\n", exe, module,
           nt->OptionalHeader.ImageBase, nt->OptionalHeader.AddressOfEntryPoint );
    req->stage = 3;
    if (nt->FileHeader.Machine != IMAGE_FILE_MACHINE_I386 || (nt->FileHeader.Characteristics & IMAGE_FILE_DLL))
        error = ERROR_BAD_EXE_FORMAT;
    else if (nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_TLS].VirtualAddress)
    {
        trace( "PWWOW guest32 exe=%s has TLS: not run before P6\n", exe );
        error = ERROR_NOT_SUPPORTED;
    }
    else error = relocate( module );
    if (error)
    {
        FreeLibrary( module );
        return fail( req, error, "relocate" );
    }
    req->stage = 4;
    if ((error = resolve( module, &patched )))
    {
        while (loaded_count) FreeLibrary( loaded[--loaded_count] );
        FreeLibrary( module );
        return fail( req, error, "imports" );
    }
    req->stage = 5;
    entry = (char *)module + nt->OptionalHeader.AddressOfEntryPoint;
    trace( "PWWOW guest32 entry=%p imports=%d exit_process_patched=%d\n", entry, loaded_count, patched );

    exit_thread = GetCurrentThreadId();
    seh = tib->ExceptionList;
    if (!__builtin_setjmp( exit_jump )) exit_value = ((DWORD (WINAPI *)(void))entry)();
    tib->ExceptionList = seh;  /* frames the program left on the stack are gone */
    exit_thread = 0;
    code = exit_value;

    request->stage = 6;
    request->exit_code = code;
    while (loaded_count) FreeLibrary( loaded[--loaded_count] );
    FreeLibrary( module );
    narrow( exe, request->exe, sizeof(exe) );
    trace( "PWWOW guest32 exit exe=%s code=%lu\n", exe, code );
    return code;
}

struct guest32_launch      /* kernelbase (64-bit) ps4_world_launch, tools/build-guest-hw.py (W235) */
{
    DWORD flags;           /* CreateProcess flags of the caller */
    DWORD error;           /* out: why it did not start */
    DWORD thread;          /* out: the guest's first thread, a handle of this process */
    DWORD thread_id;
    DWORD console;         /* W236: a console program's console and standard handles (copies), or 0 */
    DWORD std_input;
    DWORD std_output;
    DWORD std_error;
    WCHAR exe[MAX_PATH];
    WCHAR dir[MAX_PATH];   /* its current directory: the caller's, else the program's folder */
    WCHAR cmd[1];          /* the command line, as long as it is */
};

/* the 32-bit world's process parameters (PEB32): the console of the next console program */
static void set_console( DWORD console, DWORD input, DWORD output, DWORD error )
{
    char *peb;
    DWORD *params;

    __asm__ volatile( "movl %%fs:0x30,%0" : "=r" (peb) );
    params = *(DWORD **)(peb + 0x10);  /* PEB.ProcessParameters */
    params[0x10 / 4] = console;        /* ConsoleHandle */
    params[0x18 / 4] = input;          /* hStdInput */
    params[0x1c / 4] = output;         /* hStdOutput */
    params[0x20 / 4] = error;          /* hStdError */
}

__declspec(dllexport) DWORD WINAPI ps4_guest32_launch( struct guest32_launch *req )
{
    HMODULE ntdll = GetModuleHandleA( "ntdll.dll" );
    STARTUPINFOW startup;
    PROCESS_INFORMATION info;
    char exe[MAX_PATH];

    dbg_output = (void *)GetProcAddress( ntdll, "__wine_dbg_output" );
    format = (void *)GetProcAddress( ntdll, "_vsnprintf" );
    narrow( exe, req->exe, sizeof(exe) );
    trace( "PWWOW guest32 launch exe=%s thread=%lu flags=%#lx\n", exe, GetCurrentThreadId(), req->flags );
    /* the 32-bit world has one current directory (PEB32), separate from explorer's: relative paths of
     * the program (W128: SuperMarioKart's SMK\*.x) start in its folder */
    if (req->dir[0] && !SetCurrentDirectoryW( req->dir ))
        trace( "PWWOW guest32 launch exe=%s directory not set error=%lu\n", exe, GetLastError() );
    memset( &startup, 0, sizeof(startup) );
    startup.cb = sizeof(startup);
    memset( &info, 0, sizeof(info) );
    /* W236 (W235: the 32-bit side asked for conhost, which cannot be a 32-bit guest): explorer gave a
     * console program its console; the guest's kernelbase finds it here and allocates none */
    if (req->console)
    {
        set_console( req->console, req->std_input, req->std_output, req->std_error );
        trace( "PWWOW guest32 launch exe=%s console=%#lx out=%#lx\n", exe, req->console, req->std_output );
    }
    /* W254: DXVK's debug log for the 32-bit world, on demand (C:\orbis\dxvkdebug.txt); never log files in the
     * program's folder (the user's copy) */
    if (GetFileAttributesW( L"C:\\orbis\\dxvkdebug.txt" ) != INVALID_FILE_ATTRIBUTES)
    {
        SetEnvironmentVariableW( L"DXVK_LOG_LEVEL", L"debug" );
        SetEnvironmentVariableW( L"DXVK_LOG_PATH", L"none" );
        trace( "PWWOW guest32 launch exe=%s DXVK_LOG_LEVEL=debug (C:\\orbis\\dxvkdebug.txt)\n", exe );
    }
    else
    {
        SetEnvironmentVariableW( L"DXVK_LOG_LEVEL", NULL );
        SetEnvironmentVariableW( L"DXVK_LOG_PATH", NULL );
    }
    /* W270 (W269: Call of Duty ended with "Buffer overrun detected" right after glGetString(GL_EXTENSIONS),
     * 7831 characters from Mesa): id Tech 3 games copy the string into a fixed buffer. Mesa's
     * MESA_EXTENSION_MAX_YEAR keeps the extensions of their time; Mesa reads it with GetEnvironmentVariableA
     * when the program creates its context, and the 32-bit world has one environment, so it is set or
     * cleared for each program started here */
    {
        static const WCHAR *const old_gl[] = {L"codsp.exe", L"codmp.exe", L"coduosp.exe", L"coduomp.exe"};
        const WCHAR *name = req->exe, *p;
        BOOL cap = FALSE;
        unsigned int i;

        for (p = req->exe; *p; p++) if (*p == '\\' || *p == '/') name = p + 1;
        for (i = 0; i < sizeof(old_gl) / sizeof(old_gl[0]) && !cap; i++) cap = !lstrcmpiW( name, old_gl[i] );
        SetEnvironmentVariableW( L"MESA_EXTENSION_MAX_YEAR", cap ? L"2003" : NULL );
        if (cap) trace( "PWWOW guest32 launch exe=%s MESA_EXTENSION_MAX_YEAR=2003 (id Tech 3 extension buffer)\n", exe );
    }
    SetLastError( 0 );
    if (!CreateProcessW( req->exe, req->cmd, NULL, NULL, FALSE, req->flags, NULL, req->dir[0] ? req->dir : NULL,
                         &startup, &info ))
    {
        req->error = GetLastError();
        if (!req->error) req->error = ERROR_GEN_FAILURE;
        if (req->console) set_console( 0, 0, 0, 0 );  /* explorer closes its copies */
        trace( "PWWOW guest32 launch_failed exe=%s error=%lu\n", exe, req->error );
        return req->error;
    }
    if (info.hProcess) CloseHandle( info.hProcess );
    req->thread = (DWORD)(ULONG_PTR)info.hThread;
    req->thread_id = info.dwThreadId;
    /* W236: no thread is a second start of a running program (W217): its window came to the front, or
     * ERROR_ALREADY_EXISTS when none was found, for explorer to say so */
    if (!info.hThread) req->error = GetLastError() == ERROR_ALREADY_EXISTS ? ERROR_ALREADY_EXISTS : 0;
    trace( "PWWOW guest32 launched exe=%s guest_thread=%04lx error=%lu\n", exe, info.dwThreadId, req->error );
    return 0;
}

/* the main module's entry is not called: the 32-bit world only starts threads at ps4_guest32_start */
void host_entry(void)
{
}
