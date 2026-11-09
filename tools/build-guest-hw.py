#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build the hardware variants of ntdll.dll and kernelbase.dll (PE64) that run guest programs.

W052, multitasking experiment. A PS4 title cannot start a second process, so a 64-bit
GUI program started from the desktop runs as a guest inside this process:
kernelbase's CreateProcessInternalW loads the EXE as a module (ntdll relocates it and
resolves its imports, which the loader otherwise does only for DLLs) and starts its
entry point on a new thread. The guest's threads carry a pointer to it in
TEB.UserReserved, through which GetModuleHandle(NULL), GetModuleFileName(NULL) and
GetCommandLine answer for the guest, and RtlExitUserProcess ends only the guest's
threads. Opt-in at run time with WINE_PS4_GUESTS (set by the hardware launcher).

Only the hardware package uses these modules. Each changed object is compiled with the
exact command the pinned Wine build uses (from `make -n`), with the overlay source and a
separate output; the other objects of the module are the pinned build's own.
"""
import hashlib,json,pathlib,re,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'.deps/wine/source';BUILD=ROOT/'.deps/wine/runtime/build'
overlay=ROOT/'.deps/wine/guest-hw-overlay';work=ROOT/'build/guest-hw';out=ROOT/'out/guest-hw'
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('Wine source is not the pinned revision')
if overlay.exists():shutil.rmtree(overlay)
for folder in (work,out):folder.mkdir(parents=True,exist_ok=True)
revisions=[];sources={}
def revise(module,unit,old,new,why,source=None):
    """source: the unit's file when the module builds it from another directory
    (ucrtbase from dlls/msvcrt)."""
    source=source or 'dlls/%s/%s.c'%(module,unit)
    sources.setdefault(module,{})[unit]=source
    target=overlay/module/(unit+'.c')
    if not target.exists():target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(SOURCE/source,target)
    text=target.read_text()
    if text.count(old)!=1:raise SystemExit('Unexpected context in %s: %s'%(source,old[:60]))
    target.write_text(text.replace(old,new));revisions.append({'path':source,'module':module,'why':why})

GUEST_H='''/* PS4 hardware build (W052): a 64-bit GUI program run as a guest thread of this process
 * (see tools/build-guest-hw.py). ntdll's RtlExitUserProcess calls exit_process, so it
 * stays the first member. */
struct ps4_guest
{
    void (WINAPI *exit_process)( struct ps4_guest *guest, DWORD status );
    void *atexit_table[3];  /* W184: ucrtbase's atexit table of the guest (_onexit_table_t, dlls/msvcrt/exit.c) */
    HMODULE module;
    WCHAR *command_lineW;
    char *command_lineA;
    void *entry;
    CRITICAL_SECTION lock;
    HANDLE threads[256];    /* W177: a browser (phase 9) starts more than 64 */
    UINT thread_count;
    BOOL console;           /* W056: a console program; the console goes when it exits */
    BOOL console_host;      /* W062: conhost, which draws the process's console */
    struct ps4_guest_file *files;  /* W206: files it opened, closed when it exits */
    UINT file_count, file_size;
    HMODULE *modules_before;       /* W208: the modules loaded when it started */
    UINT modules_before_count;
    HMODULE *modules_at_launch;    /* W258: every module loaded at its launch, before its EXE */
    UINT modules_at_launch_count;
    struct ps4_guest_region *regions;  /* W208: memory its own code reserved */
    UINT region_count, region_size;
    BOOL terminated;               /* W209: ended through TerminateProcess (a crash included) */
    HANDLE ended;                  /* W210: set when it has ended and unloaded */
    struct ps4_guest_patch *patches[64];  /* W224: pages of system modules it made writable */
    UINT patch_count;
    DWORD mode_width, mode_height;  /* W248: the display mode when it started */
    LONG serial;                    /* W248: launch order */
    DWORD_PTR affinity;             /* W275: the one core its threads run on, or 0 */
};
/* TEB.UserReserved[0..1] holds the guest of the thread; [2] marks a guest image load */
#define PS4_GUEST_LOADING 0x47345350
static inline struct ps4_guest *ps4_guest_current(void) { return *(struct ps4_guest **)NtCurrentTeb()->UserReserved; }
static inline void ps4_guest_set( TEB *teb, struct ps4_guest *guest ) { *(struct ps4_guest **)teb->UserReserved = guest; }
/* W274 (W273: Max Payne's rlmfc.dll takes its folder from GetCommandLineA in its DllMain, while the guest EXE
 * loads): kernelbase process.c; the guest whose image a thread is loading */
extern struct ps4_guest *ps4_guest_loading;
static inline struct ps4_guest *ps4_guest_or_loading(void)
{
    if (ps4_guest_current()) return ps4_guest_current();
    return NtCurrentTeb()->UserReserved[2] == PS4_GUEST_LOADING ? ps4_guest_loading : NULL;
}
/* W206: kernelbase process.c; CreateFileW and CloseHandle of a guest thread */
void ps4_guest_file_opened( HANDLE handle, void *caller );
void ps4_guest_file_closing( HANDLE handle );
/* W208: kernelbase process.c; VirtualAlloc and VirtualFree of a guest thread */
void ps4_guest_memory_reserved( void *base, void *caller );
void ps4_guest_memory_released( void *base );
/* W224: kernelbase process.c; VirtualProtectEx and WriteProcessMemory of a guest thread */
void ps4_guest_code_writable( HANDLE process, void *addr, SIZE_T size, DWORD prot );
'''
(overlay/'kernelbase').mkdir(parents=True,exist_ok=True);(overlay/'kernelbase/ps4_guest.h').write_text(GUEST_H)

# ntdll: relocate and resolve imports of a guest EXE; a guest's exit ends the guest only.
revise('ntdll','loader','''    if (!(nt->FileHeader.Characteristics & IMAGE_FILE_DLL) &&
        module != NtCurrentTeb()->Peb->ImageBaseAddress)
        return STATUS_SUCCESS;''','''    if (!(nt->FileHeader.Characteristics & IMAGE_FILE_DLL) &&
        module != NtCurrentTeb()->Peb->ImageBaseAddress &&
        NtCurrentTeb()->UserReserved[2] != 0x47345350 /* PS4 guest image load (W052) */)
        return STATUS_SUCCESS;''','Relocate a guest EXE loaded as a module.')
revise('ntdll','loader','''    if (!(flags & LDR_DONT_RESOLVE_REFS) &&
        ((nt->FileHeader.Characteristics & IMAGE_FILE_DLL) ||
         nt->OptionalHeader.Subsystem == IMAGE_SUBSYSTEM_NATIVE))''','''    if (!(flags & LDR_DONT_RESOLVE_REFS) &&
        ((nt->FileHeader.Characteristics & IMAGE_FILE_DLL) ||
         nt->OptionalHeader.Subsystem == IMAGE_SUBSYSTEM_NATIVE ||
         NtCurrentTeb()->UserReserved[2] == 0x47345350 /* PS4 guest image load (W052) */))''',"Resolve a guest EXE's imports.")
# W053: once its imports resolve, process_attach reached the guest EXE and called its entry
# point as DllMain, inside LoadLibraryEx on explorer's thread (W052: notepad ran there,
# without its own resources, explorer stopped, and its exit ended the title). An EXE's
# entry is never a DllMain; the main EXE is marked attached before and never gets here.
revise('ntdll','loader','''    if (wm->ldr.TlsIndex == -1) call_tls_callbacks( wm->ldr.DllBase, reason );
    if (!entry) return STATUS_SUCCESS;''','''    if (wm->ldr.TlsIndex == -1) call_tls_callbacks( wm->ldr.DllBase, reason );
    if (!entry) return STATUS_SUCCESS;
    if (!(wm->ldr.Flags & LDR_IMAGE_IS_DLL)) return STATUS_SUCCESS;  /* PS4 guest EXE (W053) */''',
       "A guest EXE's entry point is not a DllMain.")
revise('ntdll','loader','''void WINAPI RtlExitUserProcess( DWORD status )
{''','''void WINAPI RtlExitUserProcess( DWORD status )
{
    /* PS4 hardware build (W052): a guest program (kernelbase ps4_guest) ends alone; its
     * first member is the function that ends it, which does not return */
    void **guest = *(void ***)NtCurrentTeb()->UserReserved;

    if (guest && guest[0]) ((void (WINAPI *)(void *, DWORD))guest[0])( guest, status );''',"A guest's exit ends the guest.")
# W197: a guest EXE built with the static MSVC CRT registers an FLS callback in its own image
# (its per-thread data cleanup; FlsAlloc through GetProcAddress). The guest is unloaded and its
# thread then ends (ps4_guest_exit_process); thread exit ran that callback in the unmapped image.
# W196 run-0001.log: The Lost Forest's thread 0040 faulted at 00000001007C1FAC (the image's
# 0x1fac, "if (ptd != &__acrt_initial_ptd)") after unload_end, and the title exited. Windows never
# unloads a process's EXE, so nothing frees those slots; here they are freed as the image goes
# (RtlFlsFree, which runs the callback for every thread's value while the code is still mapped).
revise('ntdll','thread','''/***********************************************************************
 *              RtlFlsSetValue (NTDLL.@)
 */''','''/* PS4 hardware build (W197): free the FLS slots whose callback is in an image being unloaded
 * (a guest EXE, tools/build-guest-hw.py); returns how many were freed */
unsigned int ps4_fls_free_image( const void *base, SIZE_T size )
{
    unsigned int i, index, count = 0, freed[64];

    lock_fls_data();
    for (i = 0; i < ARRAY_SIZE(fls_data.fls_callback_chunks); ++i)
    {
        if (!fls_data.fls_callback_chunks[i] || !fls_data.fls_callback_chunks[i]->count) continue;
        for (index = 0; index < fls_chunk_size( i ) && count < ARRAY_SIZE(freed); ++index)
        {
            ULONG_PTR callback = (ULONG_PTR)fls_data.fls_callback_chunks[i]->callbacks[index].callback;
            if (callback && callback != ~(ULONG_PTR)0 && callback - (ULONG_PTR)base < size)
                freed[count++] = fls_index_from_chunk_index( i, index );
        }
    }
    unlock_fls_data();
    for (i = 0; i < count; ++i) RtlFlsFree( freed[i] );
    return count;
}


/***********************************************************************
 *              RtlFlsSetValue (NTDLL.@)
 */''',"FLS slots of an unloaded guest EXE are freed.")
revise('ntdll','loader','''static void free_modref( WINE_MODREF *wm )
{
    SINGLE_LIST_ENTRY *entry;
    LDR_DEPENDENCY *dep;
''','''static void free_modref( WINE_MODREF *wm )
{
    SINGLE_LIST_ENTRY *entry;
    LDR_DEPENDENCY *dep;

    /* PS4 hardware build (W197): a guest EXE leaves no FLS callback behind (tools/build-guest-hw.py) */
    if (!(wm->ldr.Flags & LDR_IMAGE_IS_DLL))
    {
        extern unsigned int ps4_fls_free_image( const void *base, SIZE_T size );
        unsigned int freed = ps4_fls_free_image( wm->ldr.DllBase, wm->ldr.SizeOfImage );
        ERR( "PWGUEST fls_free module=%p freed=%u\\n", wm->ldr.DllBase, freed );
    }
''',"FLS slots of an unloaded guest EXE are freed.")

# W057: ucrtbase builds each program's argv once, at its own load, from explorer's command
# line; conhost then refused explorer's "/desktop=shell,1280x720" and quit, so console
# programs had no console. A guest's threads get argc/argv/wargv built from the guest's
# command line (GetCommandLineW answers for the guest), once per guest.
revise('ucrtbase','data','#include "msvcrt.h"\n','#include "msvcrt.h"\n#include <winternl.h>\n','TEB access.','dlls/msvcrt/data.c')
revise('ucrtbase','data','''int* CDECL __p___argc(void) { return &MSVCRT___argc; }''','''/* PS4 hardware build (W057): the arguments of a guest program (kernelbase ps4_guest),
 * whose threads carry it in TEB.UserReserved */
static struct { void *guest; int argc; wchar_t **wargv; char **argv; } guest_args[32];
static RTL_SRWLOCK guest_args_lock = RTL_SRWLOCK_INIT;

static int guest_slot(void)
{
    void *guest = *(void **)NtCurrentTeb()->UserReserved;
    int i, slot = -1, count = sizeof(guest_args) / sizeof(guest_args[0]);

    if (!guest) return -1;
    RtlAcquireSRWLockExclusive( &guest_args_lock );
    for (i = 0; i < count && slot < 0; i++)
        if (guest_args[i].guest == guest) slot = i;
    for (i = 0; i < count && slot < 0; i++)
        if (!guest_args[i].guest)
        {
            guest_args[i].wargv = cmdline_to_argv( GetCommandLineW(), &guest_args[i].argc );
            guest_args[i].argv = build_argv( guest_args[i].wargv );
            guest_args[i].guest = guest;
            slot = i;
        }
    RtlReleaseSRWLockExclusive( &guest_args_lock );
    return slot;
}

int* CDECL __p___argc(void) { int slot = guest_slot(); return slot < 0 ? &MSVCRT___argc : &guest_args[slot].argc; }''',
       "A guest's argc.",'dlls/msvcrt/data.c')
revise('ucrtbase','data','''char*** CDECL __p___argv(void) { return &MSVCRT___argv; }''',
       '''char*** CDECL __p___argv(void) { int slot = guest_slot(); return slot < 0 ? &MSVCRT___argv : &guest_args[slot].argv; }''',
       "A guest's argv.",'dlls/msvcrt/data.c')
revise('ucrtbase','data','''wchar_t*** CDECL __p___wargv(void) { return &MSVCRT___wargv; }''',
       '''wchar_t*** CDECL __p___wargv(void) { int slot = guest_slot(); return slot < 0 ? &MSVCRT___wargv : &guest_args[slot].wargv; }''',
       "A guest's wargv.",'dlls/msvcrt/data.c')

# kernelbase: the guest's own answers.
revise('kernelbase','loader','#include "kernelbase.h"','#include "kernelbase.h"\n#include "ps4_guest.h"','Guest state.')
revise('kernelbase','loader','''    name.Buffer = filename;
    name.MaximumLength = min( size, UNICODE_STRING_MAX_CHARS ) * sizeof(WCHAR);''','''    if (!module && ps4_guest_current()) module = ps4_guest_current()->module;
    name.Buffer = filename;
    name.MaximumLength = min( size, UNICODE_STRING_MAX_CHARS ) * sizeof(WCHAR);''','GetModuleFileName(NULL) of a guest.')
revise('kernelbase','loader','''        ret = name ? RtlPcToFileHeader( (void *)name, &dummy ) : NtCurrentTeb()->Peb->ImageBaseAddress;''',
       '''        ret = name ? RtlPcToFileHeader( (void *)name, &dummy ) :
              ps4_guest_current() ? ps4_guest_current()->module : NtCurrentTeb()->Peb->ImageBaseAddress;''',
       'GetModuleHandle(NULL) of a guest.')
# W273 (W272: Max Payne's DLLs, initialized while explorer's 32-bit world loaded MaxPayne.exe, took
# orbis32host's folder from GetModuleFileName(NULL) for the game's, made it the current directory and
# found no data folder): during a guest image load the program is the EXE being loaded.
revise('kernelbase','loader','''/***********************************************************************
 *	GetModuleFileNameW   (kernelbase.@)''','''/* PS4 hardware build (W273): the program of this thread. During a guest image load (its DLLs'
 * DllMain), the EXE being loaded: the last module in load order that is not a DLL. */
static HMODULE ps4_guest_program(void)
{
    LIST_ENTRY *list = &NtCurrentTeb()->Peb->LdrData->InLoadOrderModuleList, *entry;
    HMODULE ret = NULL;
    ULONG_PTR magic;

    if (ps4_guest_current()) return ps4_guest_current()->module;
    if (NtCurrentTeb()->UserReserved[2] != PS4_GUEST_LOADING || LdrLockLoaderLock( 0, NULL, &magic )) return NULL;
    for (entry = list->Blink; entry != list && !ret; entry = entry->Blink)
    {
        LDR_DATA_TABLE_ENTRY *mod = CONTAINING_RECORD( entry, LDR_DATA_TABLE_ENTRY, InLoadOrderLinks );
        if (!(mod->Flags & LDR_IMAGE_IS_DLL) && mod->DllBase != NtCurrentTeb()->Peb->ImageBaseAddress)
            ret = mod->DllBase;
    }
    LdrUnlockLoaderLock( 0, magic );
    if (ret) ERR( "PWGUEST program_during_load module=%p\\n", ret );
    return ret;
}

/***********************************************************************
 *	GetModuleFileNameW   (kernelbase.@)''','The program of a thread during a guest image load (W273).')
revise('kernelbase','loader','''    if (!module && ps4_guest_current()) module = ps4_guest_current()->module;
    name.Buffer = filename;''','''    if (!module) module = ps4_guest_program();
    name.Buffer = filename;''','GetModuleFileName(NULL) during a guest image load (W273).')
revise('kernelbase','loader','''              ps4_guest_current() ? ps4_guest_current()->module : NtCurrentTeb()->Peb->ImageBaseAddress;''',
       '''              ps4_guest_program() ? ps4_guest_program() : NtCurrentTeb()->Peb->ImageBaseAddress;''',
       'GetModuleHandle(NULL) during a guest image load (W273).')
revise('kernelbase','thread','#include "kernelbase.h"','#include "kernelbase.h"\n#include "ps4_guest.h"','Guest state.')
revise('kernelbase','thread','''    if (actctx)
    {
        ULONG_PTR cookie;
        RtlActivateActivationContextEx( 0, teb, actctx, &cookie );
        RtlReleaseActivationContext( actctx );
    }''','''    if (actctx)
    {
        ULONG_PTR cookie;
        RtlActivateActivationContextEx( 0, teb, actctx, &cookie );
        RtlReleaseActivationContext( actctx );
    }

    /* PS4 hardware build (W052): a guest's threads belong to the guest */
    {
        struct ps4_guest *guest = ps4_guest_current();
        LDR_DATA_TABLE_ENTRY *mod = NULL;
        HANDLE copy;

        /* W281 (W279: Need for Speed Underground 2's second start had no music and no movie sound: winmm's timer
         * thread, made once per process from the first start's thread, ended with that guest, and winmm kept its
         * handle, so timeSetEvent never fired again): a module's one thread for the whole process (winmm's timer,
         * dinput's hook thread) is no guest's */
        if (guest && process == GetCurrentProcess() && !LdrFindEntryForAddress( (void *)start, &mod ) &&
            mod->BaseDllName.Buffer && (!wcsicmp( mod->BaseDllName.Buffer, L"winmm.dll" ) ||
                                        !wcsicmp( mod->BaseDllName.Buffer, L"dinput.dll" ) ||
                                        !wcsicmp( mod->BaseDllName.Buffer, L"dinput8.dll" )))
        {
            ERR( "PWGUEST shared_thread %04lx start=%s+%Ix: not the guest's\\n", GetThreadId( handle ),
                 debugstr_w( mod->BaseDllName.Buffer ), (ULONG_PTR)start - (ULONG_PTR)mod->DllBase );
            guest = NULL;
        }
        if (guest && process == GetCurrentProcess())
        {
            ps4_guest_set( teb, guest );
            RtlEnterCriticalSection( &guest->lock );
            /* W177: a thread past the list is not ended with the guest; say so */
            if (guest->thread_count >= ARRAY_SIZE(guest->threads))
                ERR( "PWGUEST thread_overflow module=%p count=%u: thread %04lx not tracked, it keeps running after the guest exits\\n",
                     guest->module, guest->thread_count, GetThreadId( handle ) );
            else if (DuplicateHandle( GetCurrentProcess(), handle, GetCurrentProcess(), &copy, 0, FALSE, DUPLICATE_SAME_ACCESS ))
                guest->threads[guest->thread_count++] = copy;
            RtlLeaveCriticalSection( &guest->lock );
            /* W275: a guest kept on one core keeps its new threads there */
            /* W281 (W279: NFS U2 ran slower with DXVK's and the system's threads on its one core too): only threads
             * that start in the program's own image are kept there; the race is between the program's threads */
            if (guest->affinity && guest->module && (ULONG_PTR)start >= (ULONG_PTR)guest->module &&
                (ULONG_PTR)start < (ULONG_PTR)guest->module + RtlImageNtHeader( guest->module )->OptionalHeader.SizeOfImage)
            {
                DWORD_PTR mask = guest->affinity;
                NTSTATUS status = NtSetInformationThread( handle, ThreadAffinityMask, &mask, sizeof(mask) );
                if (status) ERR( "PWGUEST affinity thread=%04lx mask=%#Ix failed status=%#lx\\n", GetThreadId( handle ),
                                 mask, status );
            }
        }
    }''','Threads inherit the guest.')
revise('kernelbase','process','#include "kernelbase.h"','#include "kernelbase.h"\n#include "ps4_guest.h"','Guest state.')
revise('kernelbase','process','''LPSTR WINAPI GetCommandLineA(void)
{
    return command_lineA;''','''LPSTR WINAPI GetCommandLineA(void)
{
    if (ps4_guest_or_loading()) return ps4_guest_or_loading()->command_lineA;
    return command_lineA;''','GetCommandLineA of a guest (W274: also while its image loads).')
revise('kernelbase','process','''LPWSTR WINAPI GetCommandLineW(void)
{
    return command_lineW;''','''LPWSTR WINAPI GetCommandLineW(void)
{
    if (ps4_guest_or_loading()) return ps4_guest_or_loading()->command_lineW;
    return command_lineW;''','GetCommandLineW of a guest (W274: also while its image loads).')
revise('kernelbase','process','''/**********************************************************************
 *           CreateProcessInternalW   (kernelbase.@)
 */''','''/* W274: the guest whose image a thread is loading (ps4_guest.h) */
struct ps4_guest *ps4_guest_loading;

/* PS4 hardware build (W052): run a 64-bit GUI program as a guest of this process.
 * W056: console programs too; the image's subsystem, or 0 when it cannot be a guest. */
/* W235 (P6): the i386 build runs the guests of explorer's 32-bit world, PE32 programs */
#ifdef _WIN64
#define PS4_GUEST_MACHINE IMAGE_FILE_MACHINE_AMD64
#else
#define PS4_GUEST_MACHINE IMAGE_FILE_MACHINE_I386
#endif
static WORD ps4_guest_image( const WCHAR *path )
{
    IMAGE_DOS_HEADER dos;
    IMAGE_NT_HEADERS nt;
    DWORD read;
    WORD ok = 0;
    HANDLE file = CreateFileW( path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_DELETE, NULL, OPEN_EXISTING, 0, 0 );

    if (file == INVALID_HANDLE_VALUE) return FALSE;
    if (ReadFile( file, &dos, sizeof(dos), &read, NULL ) && read == sizeof(dos) && dos.e_magic == IMAGE_DOS_SIGNATURE &&
        SetFilePointer( file, dos.e_lfanew, NULL, FILE_BEGIN ) != INVALID_SET_FILE_POINTER &&
        ReadFile( file, &nt, sizeof(nt), &read, NULL ) && read == sizeof(nt) && nt.Signature == IMAGE_NT_SIGNATURE &&
        nt.FileHeader.Machine == PS4_GUEST_MACHINE && !(nt.FileHeader.Characteristics & IMAGE_FILE_DLL) &&
        (nt.OptionalHeader.Subsystem == IMAGE_SUBSYSTEM_WINDOWS_GUI ||
         nt.OptionalHeader.Subsystem == IMAGE_SUBSYSTEM_WINDOWS_CUI))
        ok = nt.OptionalHeader.Subsystem;
    CloseHandle( file );
    return ok;
}

/* W062: the process's console and the guests attached to it. Closing the console window
 * (conhost exits) ends them, as on Windows; the last of them ending closes the console.
 * W061: cmd outlived its conhost, and the next cmd, finding a console, talked to the dead
 * one and blocked the thread starting it (explorer's, so the Start menu too). */
static struct ps4_guest *console_host, *console_guests[16];
static UINT console_count;
static RTL_SRWLOCK console_lock = RTL_SRWLOCK_INIT;

static void ps4_guest_unload( struct ps4_guest *guest );

/* end another guest from this thread. W064: a guest with a message loop (conhost) is
 * asked to quit, and exits and unloads itself through ps4_guest_exit_process; W063:
 * TerminateThread on its running thread had the server signal the whole title, which
 * ended it ("exit" in cmd). Threads that do not quit are terminated and the module
 * unloaded here. The lock is not held while waiting: the exiting guest takes it. */
static void ps4_guest_end( struct ps4_guest *guest, DWORD status )
{
    BOOL (WINAPI *post)( DWORD, UINT, WPARAM, LPARAM ) =
        (void *)GetProcAddress( GetModuleHandleW( L"user32.dll" ), "PostThreadMessageW" );
    HANDLE threads[ARRAY_SIZE(guest->threads)];
    DWORD wait = WAIT_TIMEOUT;
    UINT i, count, posted = 0;

    RtlEnterCriticalSection( &guest->lock );
    count = guest->thread_count;
    memcpy( threads, guest->threads, count * sizeof(*threads) );
    RtlLeaveCriticalSection( &guest->lock );
    for (i = 0; post && i < count; i++)
        if (post( GetThreadId( threads[i] ), 0x0012 /* WM_QUIT */, status, 0 )) posted++;
    if (posted) wait = WaitForMultipleObjects( count, threads, TRUE, 2000 );
    ERR( "PS4 guest module %p ended with the console: %u of %u threads asked to quit, wait %lu\\n",
         guest->module, posted, count, wait );
    if (posted && wait == WAIT_OBJECT_0) return;
    for (i = 0; i < count; i++) TerminateThread( threads[i], status );
    if (count) WaitForMultipleObjects( count, threads, TRUE, 2000 );
    ps4_guest_unload( guest );
}

/* W209: a window gets DefWindowProc (ps4_guest_destroy_windows) */
struct ps4_default_proc
{
    LONG_PTR (WINAPI *set)( HWND, int, LONG_PTR );
    void *proc;
};

static BOOL CALLBACK ps4_guest_default_proc( HWND hwnd, LPARAM lparam )
{
    const struct ps4_default_proc *dp = (const struct ps4_default_proc *)lparam;

    dp->set( hwnd, -4 /* GWLP_WNDPROC */, (LONG_PTR)dp->proc );
    return TRUE;
}

/* destroy the top-level and message-only windows of a thread, from that thread; their
 * child windows go with them. Returns how many were destroyed. */
static UINT ps4_guest_destroy_windows( DWORD tid )
{
    HMODULE user32 = GetModuleHandleW( L"user32.dll" );
    BOOL (WINAPI *children)( HWND, BOOL (CALLBACK *)( HWND, LPARAM ), LPARAM ) = (void *)GetProcAddress( user32, "EnumChildWindows" );
    struct ps4_default_proc dp = { (void *)GetProcAddress( user32, "SetWindowLongPtrW" ),
                                   (void *)GetProcAddress( user32, "DefWindowProcW" ) };
    HWND (WINAPI *find)( HWND, HWND, const WCHAR *, const WCHAR * ) = (void *)GetProcAddress( user32, "FindWindowExW" );
    DWORD (WINAPI *owner)( HWND, DWORD * ) = (void *)GetProcAddress( user32, "GetWindowThreadProcessId" );
    BOOL (WINAPI *destroy)( HWND ) = (void *)GetProcAddress( user32, "DestroyWindow" );
    BOOL (WINAPI *exists)( HWND ) = (void *)GetProcAddress( user32, "IsWindow" );
    HWND parents[2] = {0, (HWND)-3 /* HWND_MESSAGE */}, hwnd, list[128];
    UINT i, j, count = 0, destroyed = 0;

    if (!find || !owner || !destroy || !exists) return 0;
    /* listed first: destroying a window also destroys the windows it owns */
    for (i = 0; i < ARRAY_SIZE(parents); i++)
        for (hwnd = find( parents[i], 0, NULL, NULL ); hwnd && count < ARRAY_SIZE(list); hwnd = find( parents[i], hwnd, NULL, NULL ))
            if (owner( hwnd, NULL ) == tid) list[count++] = hwnd;
    /* W209 (W208: Pale Moon's crash exit stopped in its own WM_DESTROY, in xul.dll, after its other
     * threads were ended): the windows go without the program's code, as Windows destroys the
     * windows of a process that ended; each and its children get DefWindowProc first */
    if (children && dp.set && dp.proc)
        for (j = 0; j < count; j++)
            if (exists( list[j] ))
            {
                children( list[j], ps4_guest_default_proc, (LPARAM)&dp );
                ps4_guest_default_proc( list[j], (LPARAM)&dp );
            }
    for (j = 0; j < count; j++)
        if (exists( list[j] ) && destroy( list[j] )) destroyed++;
    return destroyed;
}

/* ExitProcess from a guest thread (ntdll RtlExitUserProcess): end the guest's other
 * threads, then this one; their windows go with them. */
static void WINAPI ps4_guest_exit_process( struct ps4_guest *guest, DWORD status )
{
    struct ps4_guest *ended[ARRAY_SIZE(console_guests) + 1];
    HANDLE others[ARRAY_SIZE(guest->threads)];
    DWORD self = GetCurrentThreadId();
    UINT i, count = 0, other_count = 0, destroyed;
    ULONG_PTR loader_magic = 0;
    BOOL loader_locked;

    ERR( "PS4 guest module %p exits status %lu\\n", guest->module, status );
    /* W122: no other thread of the guest may be ended inside the loader. In W121 winmm's
     * wave thread was in LdrUnloadDll, holding the loader lock, when it was terminated:
     * the lock stayed owned by a dead thread and explorer (Start, every load) hung. The
     * lock is taken (trying for up to 2 s) before the threads are ended and released after
     * they are gone, as the end of a real process makes them stop outside the loader. */
    {
        ULONG lock_state = 0;
        int tries;
        for (tries = 0; tries < 200; tries++)
        {
            if (!LdrLockLoaderLock( 2 /* LDR_LOCK_LOADER_LOCK_FLAG_TRY_ONLY */, &lock_state, &loader_magic ) &&
                lock_state == 1) break;
            /* W215: a waiter terminated earlier leaves the lock ownerless and never free to a try
             * (its LockCount stays raised); a blocking acquire takes it at once */
            if (!((RTL_CRITICAL_SECTION *)NtCurrentTeb()->Peb->LoaderLock)->OwningThread &&
                !LdrLockLoaderLock( 0, NULL, &loader_magic ))
            {
                lock_state = 1;
                break;
            }
            Sleep( 10 );
        }
        loader_locked = lock_state == 1;
        ERR( "PS4 guest module %p: loader_lock=%u tries=%d\\n", guest->module, loader_locked, tries );
    }
    RtlEnterCriticalSection( &guest->lock );
    for (i = 0; i < guest->thread_count; i++)
        if (GetThreadId( guest->threads[i] ) != self)
        {
            TerminateThread( guest->threads[i], status );
            others[other_count++] = guest->threads[i];
        }
    RtlLeaveCriticalSection( &guest->lock );
    /* W067: the windows of the ended threads go when those threads are gone, and this
     * thread's own windows are destroyed here, as the process ending would on Windows.
     * W066: WFM left windows behind, its classes could not be unregistered, and the next
     * start of WFM failed to register them and quit at once. */
    if (other_count)
    {
        DWORD wait = WaitForMultipleObjects( other_count, others, TRUE, 2000 );
        ERR( "PS4 guest module %p: other_threads_wait=%lu count=%u\\n", guest->module, wait, other_count );
    }
    if (loader_locked) LdrUnlockLoaderLock( 0, loader_magic );
    destroyed = ps4_guest_destroy_windows( self );
    ERR( "PS4 guest module %p: %u other threads ended, %u windows of this thread destroyed\\n",
         guest->module, other_count, destroyed );
    ps4_guest_set( NtCurrentTeb(), NULL );

    RtlAcquireSRWLockExclusive( &console_lock );
    if (guest->console_host)
    {
        /* the console window closed: its programs go with it */
        for (i = 0; i < console_count; i++) ended[count++] = console_guests[i];
        console_count = 0;
        console_host = NULL;
    }
    else if (guest->console)
    {
        for (i = 0; i < console_count; i++)
            if (console_guests[i] == guest) console_guests[i--] = console_guests[--console_count];
        /* the last program of the console: the console window closes too */
        if (!console_count && console_host) ended[count++] = console_host, console_host = NULL;
    }
    RtlReleaseSRWLockExclusive( &console_lock );
    for (i = 0; i < count; i++) ps4_guest_end( ended[i], status );
    if (guest->console || guest->console_host) FreeConsole();
    {
        /* W216 (W214: glxgears' fault under Zink and MangoHud; the title stopped right after
         * the unload, in this thread's end): a guest ended by TerminateProcess or a fault ends
         * its last thread without DLL_THREAD_DETACH, as a terminated process does on Windows.
         * The other DLLs' thread state is the guest's (a half-built GL or Vulkan swapchain). */
        BOOL terminated = guest->terminated;
        HMODULE module = guest->module;

        ps4_guest_unload( guest );
        ERR( "PWGUEST last thread of module %p ends (%s)\\n", module,
             terminated ? "terminated, no thread detach" : "exit" );
        if (terminated) for (;;) NtTerminateThread( GetCurrentThread(), status );
    }
    RtlExitUserThread( status );
}

static void ps4_guest_unload( struct ps4_guest *guest )
{
    /* W060: the next start must load the program afresh (W059: WFM started again found its
     * window class and globals from the first run and quit): unregister the classes of
     * its module, then unload it. Class names are user atoms, allocated upwards from
     * 0xc000; the walk stops after a run of unused ones.
     * W068: UnregisterClass finds a global class (CS_GLOBALCLASS) whatever the instance,
     * so the walk also destroyed the global classes of other modules that had no window
     * left (W067: 13 classes for WFM's 7). A global class is unregistered only when its
     * window procedure is in the guest's image, that is, the guest registered it.
     * W069: user32's builtin classes (Edit, ListBox, ...) are global without having
     * CS_GLOBALCLASS in their style, and W068 destroyed 6 of them when cmd unloaded. The
     * test is the window procedure for every class; a procedure that GetClassInfoExW
     * returns as a handle (class registered as ANSI) is read again with GetClassInfoExA. */
    {
        struct
        {
            UINT size, style;
            void *proc;
            int class_extra, window_extra;
            void *instance, *icon, *cursor, *background;
            const WCHAR *menu, *name;
            void *small_icon;
        } info;
        HMODULE user32 = GetModuleHandleW( L"user32.dll" );
        BOOL (WINAPI *unregister)( const WCHAR *, HINSTANCE ) = (void *)GetProcAddress( user32, "UnregisterClassW" );
        int (WINAPI *atom_name)( UINT, WCHAR *, int ) = (void *)GetProcAddress( user32, "GetClipboardFormatNameW" );
        BOOL (WINAPI *class_info)( HINSTANCE, const WCHAR *, void * ) = (void *)GetProcAddress( user32, "GetClassInfoExW" );
        BOOL (WINAPI *class_infoA)( HINSTANCE, const char *, void * ) = (void *)GetProcAddress( user32, "GetClassInfoExA" );
        IMAGE_NT_HEADERS *nt = RtlImageNtHeader( guest->module );
        char *image = (char *)guest->module, *image_end = image + (nt ? nt->OptionalHeader.SizeOfImage : 0);
        UINT atom, unused = 0, unregistered = 0, in_use = 0, kept = 0;
        WCHAR name[256];

        for (atom = 0xc000; unregister && atom_name && class_info && class_infoA && atom <= 0xffff && unused < 256; atom++)
        {
            if (!atom_name( atom, name, ARRAY_SIZE(name) )) { unused++; continue; }
            unused = 0;
            info.size = sizeof(info);
            if (!class_info( guest->module, (const WCHAR *)(ULONG_PTR)atom, &info )) continue;
            if (((ULONG_PTR)info.proc >> 16) == 0xffff)  /* a winproc handle */
            {
                info.size = sizeof(info);
                if (!class_infoA( guest->module, (const char *)(ULONG_PTR)atom, &info )) continue;
            }
            if ((char *)info.proc < image || (char *)info.proc >= image_end)
            {
                kept++;
                continue;
            }
            if (unregister( (const WCHAR *)(ULONG_PTR)atom, guest->module )) unregistered++;
            else if (GetLastError() == 1412 /* ERROR_CLASS_HAS_WINDOWS */)
            {
                ERR( "PS4 guest module %p: class %s still has windows\\n", guest->module, debugstr_w(name) );
                in_use++;
            }
        }
        ERR( "PS4 guest module %p unloads, %u window classes unregistered, %u still in use, %u of other modules kept\\n",
             guest->module, unregistered, in_use, kept );
        /* W114: the unhandled-exception filter is process-wide. A guest's CRT installs one
         * (mingw _gnu_exception_handler); after the guest unloads, a later fault in any
         * thread jumped to it and explorer died (W113, 0x...39e0 in a freed doshost). */
        {
            LPTOP_LEVEL_EXCEPTION_FILTER filter = SetUnhandledExceptionFilter( NULL );
            if ((char *)filter >= image && (char *)filter < image_end)
                ERR( "PWGUEST unload cleared exception filter %p of module %p\\n", filter, guest->module );
            else SetUnhandledExceptionFilter( filter );
        }
        /* W173: Mesa's WGL keeps threads of its own running in libgallium_wgl. A guest that
         * pulled it in (wined3d's GL adapter, under Wine's dxgi: d3d11test64 in W172) unloaded
         * it with the guest, and explorer then faulted inside the freed module. Once loaded,
         * opengl32 and libgallium_wgl stay for the life of the process. */
        {
            static const WCHAR *const resident[] = { L"opengl32.dll", L"libgallium_wgl.dll" };
            HMODULE pinned;
            unsigned int i;
            for (i = 0; i < ARRAY_SIZE(resident); i++)
                if (GetModuleHandleW( resident[i] ) &&
                    GetModuleHandleExW( GET_MODULE_HANDLE_EX_FLAG_PIN, resident[i], &pinned ))
                    ERR( "PWGUEST unload pinned %s at %p\\n", debugstr_w(resident[i]), pinned );
        }
        ERR( "PWGUEST unload_begin module=%p gl=%p gallium=%p hud=%p\\n", guest->module,
             GetModuleHandleW( L"opengl32.dll" ), GetModuleHandleW( L"libgallium_wgl.dll" ),
             GetModuleHandleW( L"libMangoHud.dll" ) );
        {
            BOOL freed = FreeLibrary( guest->module );
            ERR( "PWGUEST unload_end module=%p freed=%u gl=%p gallium=%p hud=%p\\n", guest->module, freed,
                 GetModuleHandleW( L"opengl32.dll" ), GetModuleHandleW( L"libgallium_wgl.dll" ),
                 GetModuleHandleW( L"libMangoHud.dll" ) );
        }
    }
}

static DWORD WINAPI ps4_guest_start( void *param )
{
    struct ps4_guest *guest = param;

    ps4_guest_set( NtCurrentTeb(), guest );
#ifndef _WIN64
    /* W236 (W235: gui-window32's thread 0068 logged nothing): the program's entry is next */
    ERR( "PWWOW guest32 thread %04lx start: entry %p of module %p\\n", GetCurrentThreadId(), guest->entry, guest->module );
#endif
    return ((DWORD (WINAPI *)(void *))guest->entry)( NtCurrentTeb()->Peb );
}

#include "winreg.h"
/* W183 (phase 9): a 64-bit program the AppDefaults mark to run alone
 * (HKCU\\Software\\Wine\\AppDefaults\\<exe> "OrbisRunsAlone"="Y") is not a guest: it gets the title
 * to itself, as a 32-bit program does. W182: Pale Moon's mozglue.dll, xul.dll and nss3.dll have
 * the names of Wine Gecko's; in one process the second program bound to the first's and aborted. */
static BOOL ps4_runs_alone( const WCHAR *name )
{
    WCHAR key[MAX_PATH + 40], value[4];
    DWORD size = sizeof(value);

    if (wcslen( name ) > MAX_PATH) return FALSE;
    swprintf( key, ARRAY_SIZE(key), L"Software\\\\Wine\\\\AppDefaults\\\\%s", name );
    return !RegGetValueW( HKEY_CURRENT_USER, key, L"OrbisRunsAlone", RRF_RT_REG_SZ, NULL, value, &size ) &&
           (value[0] == 'Y' || value[0] == 'y');
}

static BOOL ps4_guest_launch( const WCHAR *app_name, const WCHAR *cmd_line, DWORD flags, PROCESS_INFORMATION *info )
{
    struct ps4_guest *guest, *parent;
    IMAGE_NT_HEADERS *nt;
    WCHAR flag[4];
    HANDLE thread, copy;
    DWORD tid;
    WORD subsystem;
    BOOL allocated = FALSE;
    int len;

    if (!GetEnvironmentVariableW( L"WINE_PS4_GUESTS", flag, ARRAY_SIZE(flag) ) || !(subsystem = ps4_guest_image( app_name )))
        return FALSE;
    /* W095: wineboot is Wine's helper, never a guest. ExitWindowsEx starts "wineboot --shutdown",
     * which NtCreateUserProcess turns into the end of the title (prepare-wine-boot.py). Until
     * W093 wineboot failed to load as a guest (ws2_32's initialisation failed) and reached that
     * path; once it loaded (W094), it ran as a guest and Exit did nothing. */
    {
        const WCHAR *base = wcsrchr( app_name, '\\\\' );
        if (!wcsicmp( base ? base + 1 : app_name, L"wineboot.exe" )) return FALSE;
        /* W183: it relaunches the title instead (CreateProcessInternalW, below) */
        if (ps4_runs_alone( base ? base + 1 : app_name ))
        {
            ERR( "PWGUEST runs_alone app=%s\\n", debugstr_w(app_name) );
            return FALSE;
        }
    }
    /* W056: a console program gets the process's console (explorer has none): AllocConsole
     * starts conhost.exe, a GUI program, so as another guest that draws the window.
     * W066: not when the caller asks for no console (ExitWindowsEx starts wineboot with
     * DETACHED_PROCESS; W065 flashed its console window on Exit). */
    if (subsystem == IMAGE_SUBSYSTEM_WINDOWS_CUI && !(flags & (DETACHED_PROCESS | CREATE_NO_WINDOW)) &&
        !RtlGetCurrentPeb()->ProcessParameters->ConsoleHandle && !(allocated = AllocConsole()))
    {
        ERR( "PS4 guest %s: no console, error %lu\\n", debugstr_w(app_name), GetLastError() );
        return FALSE;
    }
    /* W060: the console window is titled after the program, not this process (explorer) */
    if (subsystem == IMAGE_SUBSYSTEM_WINDOWS_CUI)
    {
        const WCHAR *base = wcsrchr( app_name, '\\\\' );
        SetConsoleTitleW( base ? base + 1 : app_name );
    }
    /* W060: AllocConsole passes conhost its console server handle as "--server 0x..", then
     * closes it, as a child process would hold its own inherited copy; in this process
     * conhost was left with a closed handle (W059: read_complete failed 0xc0000024). The
     * guest gets a duplicate of its own. */
    {
        static WCHAR fixed[1024];
        const WCHAR *server = wcsstr( cmd_line, L"--server 0x" );
        HANDLE copy_server;

        if (server && lstrlenW( cmd_line ) < ARRAY_SIZE(fixed) - 32 &&
            DuplicateHandle( GetCurrentProcess(), (HANDLE)(ULONG_PTR)wcstoul( server + 9, NULL, 16 ),
                             GetCurrentProcess(), &copy_server, 0, FALSE, DUPLICATE_SAME_ACCESS ))
        {
            const WCHAR *rest = server + 11;
            while ((*rest >= '0' && *rest <= '9') || (*rest >= 'a' && *rest <= 'f') || (*rest >= 'A' && *rest <= 'F')) rest++;
            memcpy( fixed, cmd_line, (server - cmd_line) * sizeof(WCHAR) );
            swprintf( fixed + (server - cmd_line), ARRAY_SIZE(fixed) - (server - cmd_line), L"--server 0x%x%s",
                      HandleToUlong( copy_server ), rest );
            cmd_line = fixed;
        }
    }
    if (!(guest = RtlAllocateHeap( GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(*guest) ))) return FALSE;
    len = lstrlenW( cmd_line ) + 1;
    guest->command_lineW = RtlAllocateHeap( GetProcessHeap(), 0, len * sizeof(WCHAR) );
    len = WideCharToMultiByte( CP_ACP, 0, cmd_line, -1, NULL, 0, NULL, NULL );
    guest->command_lineA = RtlAllocateHeap( GetProcessHeap(), 0, len );
    if (!guest->command_lineW || !guest->command_lineA) return FALSE;
    lstrcpyW( guest->command_lineW, cmd_line );
    WideCharToMultiByte( CP_ACP, 0, cmd_line, -1, guest->command_lineA, len, NULL, NULL );
    guest->exit_process = ps4_guest_exit_process;
    guest->console = subsystem == IMAGE_SUBSYSTEM_WINDOWS_CUI;
    {
        const WCHAR *base = wcsrchr( app_name, '\\\\' );
        guest->console_host =!wcsicmp( base ? base + 1 : app_name, L"conhost.exe" );
    }
    RtlInitializeCriticalSection( &guest->lock );

    {
        MEMORYSTATUSEX memory = { .dwLength = sizeof(memory) };
        BOOL queried = GlobalMemoryStatusEx( &memory );
        ERR( "PWGUEST load_begin app=%s memory_valid=%u available=%I64u total=%I64u loader_owner=%p gl=%p gallium=%p hud=%p\\n",
             debugstr_w(app_name), queried, memory.ullAvailPhys, memory.ullTotalPhys,
             NtCurrentTeb()->Peb->LoaderLock ? ((RTL_CRITICAL_SECTION *)NtCurrentTeb()->Peb->LoaderLock)->OwningThread : NULL,
             GetModuleHandleW( L"opengl32.dll" ), GetModuleHandleW( L"libgallium_wgl.dll" ),
             GetModuleHandleW( L"libMangoHud.dll" ) );
    }
    /* A DLL of the program's folder whose name is already loaded from another folder would be
     * bound to that one (W182: Pale Moon's mozglue/xul/nss3 to Wine Gecko's, which stays loaded
     * under system32's gecko folder once a web view used it): the program does not start. system32's own
     * builtins and the program's folder do not count */
    {
        static WCHAR dir[MAX_PATH], system[MAX_PATH], candidate[MAX_PATH], clash[64], loaded[MAX_PATH], windows[MAX_PATH];
        UINT windows_len = GetWindowsDirectoryW( windows, MAX_PATH );
        const WCHAR *slash = wcsrchr( app_name, 0x5c );
        UINT dir_len = slash ? slash - app_name + 1 : 0, system_len = GetSystemDirectoryW( system, MAX_PATH );
        LIST_ENTRY *list = &NtCurrentTeb()->Peb->LdrData->InLoadOrderModuleList, *entry;
        ULONG_PTR magic;

        clash[0] = 0;
        /* W217 (W216 refused wfm and conhost: system32 has an explorer.exe, and explorer is loaded from
         * C:\\windows): a program under the Windows directory is not checked, and only DLLs count */
        if (windows_len && windows_len < MAX_PATH && !wcsnicmp( app_name, windows, windows_len ) &&
            app_name[windows_len] == 0x5c) dir_len = 0;
        if (dir_len && dir_len < MAX_PATH - 64 && system_len && system_len < MAX_PATH && !LdrLockLoaderLock( 0, NULL, &magic ))
        {
            memcpy( dir, app_name, dir_len * sizeof(WCHAR) );
            dir[dir_len] = 0;
            for (entry = list->Flink; entry != list && !clash[0]; entry = entry->Flink)
            {
                LDR_DATA_TABLE_ENTRY *mod = CONTAINING_RECORD( entry, LDR_DATA_TABLE_ENTRY, InLoadOrderLinks );
                const WCHAR *path = mod->FullDllName.Buffer, *base = mod->BaseDllName.Buffer, *mod_slash;
                UINT mod_dir_len, base_len;

                if (!path || !base || !(mod->Flags & LDR_IMAGE_IS_DLL) || (base_len = lstrlenW( base )) >= ARRAY_SIZE(clash)) continue;
                mod_slash = wcsrchr( path, 0x5c );
                mod_dir_len = mod_slash ? mod_slash - path + 1 : 0;
                if (mod_dir_len == dir_len && !wcsnicmp( path, dir, dir_len )) continue;
                if (mod_dir_len == system_len + 1 && !wcsnicmp( path, system, system_len )) continue;
                memcpy( candidate, dir, dir_len * sizeof(WCHAR) );
                memcpy( candidate + dir_len, base, (base_len + 1) * sizeof(WCHAR) );
                if (GetFileAttributesW( candidate ) == INVALID_FILE_ATTRIBUTES) continue;
                lstrcpynW( clash, base, ARRAY_SIZE(clash) );
                lstrcpynW( loaded, path, ARRAY_SIZE(loaded) );
            }
            LdrUnlockLoaderLock( 0, magic );
        }
        if (clash[0])
        {
            int (WINAPI *box)( HWND, const WCHAR *, const WCHAR *, UINT ) =
                (void *)GetProcAddress( GetModuleHandleW( L"user32.dll" ), "MessageBoxW" );
            WCHAR text[512];

            ERR( "PWGUEST clash app=%s name=%s loaded=%s\\n", debugstr_w(app_name), debugstr_w(clash), debugstr_w(loaded) );
            swprintf( text, ARRAY_SIZE(text), L"Este programa no puede abrirse ahora: usa su propia %s y ya hay otra cargada "
                      L"(%s).\\n\\nReiniciá OrbisDesk y abrilo antes que el otro programa.", clash, loaded );
            if (box) box( NULL, text, slash ? slash + 1 : app_name, 0x30 /* MB_ICONWARNING */ );
            if (allocated) FreeConsole();
            SetLastError( ERROR_DLL_INIT_FAILED );
            return FALSE;
        }
    }
    ps4_guest_loading = guest;  /* W274 */
    NtCurrentTeb()->UserReserved[2] = PS4_GUEST_LOADING;
    /* W214 (W212: the relaunch from W210's helper thread found no mozglue.dll): its imports are
     * looked for in its own folder, as for a process's image, whatever the current directory */
    guest->module = LoadLibraryExW( app_name, 0, wcschr( app_name, 0x5c ) ? LOAD_WITH_ALTERED_SEARCH_PATH : 0 );
    NtCurrentTeb()->UserReserved[2] = 0;
    ps4_guest_loading = NULL;
    ERR( "PWGUEST load_end app=%s module=%p error=%lu\\n", debugstr_w(app_name), guest->module, GetLastError() );
    if (!guest->module || !(nt = RtlImageNtHeader( guest->module )))
    {
        ERR( "PS4 guest %s: load failed, error %lu\\n", debugstr_w(app_name), GetLastError() );
        /* W066: the console made for it would stay open with no program */
        if (allocated) FreeConsole();
        return FALSE;
    }
    guest->entry = (char *)guest->module + nt->OptionalHeader.AddressOfEntryPoint;
    /* W184: CreateThread gives a new thread the guest of the thread creating it. A guest started
     * from a guest thread (winecfg from rundll32's applet) is not a thread of that guest: in W179
     * rundll32's exit ended winecfg's thread. */
    parent = ps4_guest_current();
    ps4_guest_set( NtCurrentTeb(), NULL );
    /* W271 (W270: Call of Duty's gamex86.dll overflowed its first thread's stack loading a level): a process's
     * first thread has the stack its image asks for (CoDSP.exe 8 MB), not the host's default */
    ERR( "PWGUEST stack app=%s reserve=%#Ix commit=%#Ix\\n", debugstr_w(app_name),
         (SIZE_T)nt->OptionalHeader.SizeOfStackReserve, (SIZE_T)nt->OptionalHeader.SizeOfStackCommit );
    thread = CreateThread( NULL, nt->OptionalHeader.SizeOfStackReserve, ps4_guest_start, guest,
                           CREATE_SUSPENDED | STACK_SIZE_PARAM_IS_A_RESERVATION, &tid );
    ps4_guest_set( NtCurrentTeb(), parent );
    if (!thread)
    {
        ERR( "PS4 guest %s: no thread, error %lu\\n", debugstr_w(app_name), GetLastError() );
        return FALSE;
    }
    /* W275 (W274: Need for Speed Underground 2 crashed loading a car, speed2.exe+0x33924d read 0x38: the function
     * keeps state in globals 0x8b7bb0/0x8b7bc0 and restores them on return, so two of its threads running it at once
     * on different cores leave one with NULL; the known multi-core crash of the game, fixed on Windows by running it
     * on one core): its threads stay on one core, the last the process may use */
    {
        static const WCHAR *const one_core[] = {L"speed2.exe"};
        const WCHAR *name = wcsrchr( app_name, 0x5c ) ? wcsrchr( app_name, 0x5c ) + 1 : app_name;
        PROCESS_BASIC_INFORMATION pbi;
        DWORD_PTR mask = 0;
        NTSTATUS status;
        unsigned int i;

        for (i = 0; i < ARRAY_SIZE(one_core); i++)
            if (!wcsicmp( name, one_core[i] ) &&
                !NtQueryInformationProcess( GetCurrentProcess(), ProcessBasicInformation, &pbi, sizeof(pbi), NULL ))
                for (mask = (DWORD_PTR)1 << (sizeof(mask) * 8 - 1); mask && !(mask & pbi.AffinityMask); mask >>= 1) ;
        if (mask)
        {
            guest->affinity = mask;
            if (!(status = NtSetInformationThread( thread, ThreadAffinityMask, &mask, sizeof(mask) )))
                ERR( "PWGUEST affinity app=%s mask=%#Ix of %#Ix (one core)\\n", debugstr_w(app_name), mask,
                     (DWORD_PTR)pbi.AffinityMask );
            else
                ERR( "PWGUEST affinity app=%s mask=%#Ix failed status=%#lx\\n", debugstr_w(app_name), mask, status );
        }
    }
    if (DuplicateHandle( GetCurrentProcess(), thread, GetCurrentProcess(), &copy, 0, FALSE, DUPLICATE_SAME_ACCESS ))
        guest->threads[guest->thread_count++] = copy;
    DuplicateHandle( GetCurrentProcess(), GetCurrentProcess(), GetCurrentProcess(), &info->hProcess, 0, FALSE, DUPLICATE_SAME_ACCESS );
    info->hThread = thread;
    info->dwProcessId = GetCurrentProcessId();
    info->dwThreadId = tid;
    ERR( "PS4 guest %s module %p entry %p thread %04lx\\n", debugstr_w(app_name), guest->module, guest->entry, tid );
    RtlAcquireSRWLockExclusive( &console_lock );
    if (guest->console_host) console_host = guest;
    else if (guest->console && console_count < ARRAY_SIZE(console_guests)) console_guests[console_count++] = guest;
    RtlReleaseSRWLockExclusive( &console_lock );
#ifdef _WIN64
    ResumeThread( thread );
#else
    {
        /* W236 (W235: gui-window32's thread 0068 logged nothing after its creation) */
        DWORD previous = ResumeThread( thread );
        ERR( "PWWOW guest32 thread %04lx resumed previous=%lu error=%lu\\n", tid, previous,
             previous == (DWORD)-1 ? GetLastError() : 0 );
    }
#endif
    return TRUE;
}

/**********************************************************************
 *           CreateProcessInternalW   (kernelbase.@)
 */''','Guest launch.')
# W196: TerminateProcess of its own process from a guest thread ends the guest, as ExitProcess
# does (RtlExitUserProcess above). W195: The Lost Forest (Unity) quits with
# TerminateProcess(GetCurrentProcess()); the server ended every thread and the whole title
# exited (run-0001.log: "thread_signal unavailable thread=0024 sig=3", then process_exit).
revise('kernelbase','process','''    return set_ntstatus( NtTerminateProcess( handle, exit_code ));''','''    {
        /* PS4 hardware build (W196): a guest that terminates its own process ends alone */
        struct ps4_guest *guest = ps4_guest_current();
        if (guest && guest->exit_process &&
            (handle == GetCurrentProcess() || GetProcessId( handle ) == GetCurrentProcessId()))
        {
            ERR( "PS4 guest module %p TerminateProcess( own process, %u )\\n", guest->module, exit_code );
            guest->terminated = TRUE;  /* W209: no DllMain(DETACH) for its modules */
            guest->exit_process( guest, exit_code );
        }
    }
    return set_ntstatus( NtTerminateProcess( handle, exit_code ));''',"A guest that terminates its own process ends alone.")
revise('kernelbase','process','''    info->hThread = info->hProcess = 0;
    info->dwProcessId = info->dwThreadId = 0;
''','''    info->hThread = info->hProcess = 0;
    info->dwProcessId = info->dwThreadId = 0;

    if (ps4_guest_launch( app_name, tidy_cmdline, flags, info ))
    {
        status = STATUS_SUCCESS;
        goto done;
    }
#ifndef _WIN64
    /* W235 (P6): this i386 kernelbase loads only in explorer's 32-bit world (wine/lib/wine/i386-guest,
     * tools/build-wow64-world-ps4.py). A program that is not a guest here goes back to explorer's
     * 64-bit side (ps4_world_launch), which offers the relaunch: nothing relaunches from a 32-bit thread */
    ERR( "PWWOW guest32 not_a_guest image=%s error=%lu\\n", debugstr_w(app_name), GetLastError() );
    /* W262 (W261: Prince of Persia's launcher starts POP.exe, which needs the launcher's base 0x400000 and has no
     * relocations, error 487): such a program is relaunched alone, as the starter asked for it (ntdll's
     * NtCreateUserProcess hands its command line, working directory and environment to the switch) */
    if (GetLastError() == ERROR_INVALID_ADDRESS)
    {
        DWORD saved = GetLastError();
        const WCHAR *slash;

        if (!wcschr( app_name, '\\\\' ) && !wcschr( app_name, ':' ))
        {
            struct ps4_guest *starter = ps4_guest_current();
            LDR_DATA_TABLE_ENTRY *mod;

            ps4_image[0] = 0;
            if (cur_dir && lstrlenW( cur_dir ) + lstrlenW( app_name ) + 2 < MAX_PATH)
            {
                lstrcpyW( ps4_image, cur_dir );
                if (ps4_image[0] && ps4_image[lstrlenW( ps4_image ) - 1] != '\\\\') lstrcatW( ps4_image, L"\\\\" );
                lstrcatW( ps4_image, app_name );
                if (GetFileAttributesW( ps4_image ) == INVALID_FILE_ATTRIBUTES) ps4_image[0] = 0;
            }
            if (!ps4_image[0] && starter && starter->module && !LdrFindEntryForAddress( starter->module, &mod ) &&
                mod->FullDllName.Buffer && mod->FullDllName.Length / sizeof(WCHAR) + lstrlenW( app_name ) + 1 < MAX_PATH)
            {
                memcpy( ps4_image, mod->FullDllName.Buffer, mod->FullDllName.Length );
                ps4_image[mod->FullDllName.Length / sizeof(WCHAR)] = 0;
                if ((slash = wcsrchr( ps4_image, '\\\\' ))) lstrcpyW( (WCHAR *)slash + 1, app_name );
                if (!slash || GetFileAttributesW( ps4_image ) == INVALID_FILE_ATTRIBUTES) ps4_image[0] = 0;
            }
            if (!ps4_image[0] && !SearchPathW( NULL, app_name, NULL, MAX_PATH, ps4_image, NULL )) ps4_image[0] = 0;
            if (ps4_image[0]) app_name = ps4_image;
        }
        if (!cur_dir && (slash = wcsrchr( app_name, '\\\\' )) && slash - app_name < MAX_PATH)
        {
            memcpy( ps4_dir, app_name, (slash - app_name) * sizeof(WCHAR) );
            ps4_dir[slash - app_name] = 0;
            cur_dir = ps4_dir;
        }
        ps4_base_taken = TRUE;
        ERR( "PWWOW guest32 base_taken relaunch image=%s cmd=%s dir=%s\\n", debugstr_w(app_name),
             debugstr_w(tidy_cmdline), debugstr_w(cur_dir) );
        SetLastError( saved );
    }
    else
    {
        status = STATUS_NOT_SUPPORTED;
        goto done;
    }
#endif
    /* W106: an unsupported image or failed guest must not enter the legacy
     * title replacement path. wineboot retains explicit session-end handling.
     * W116: a 32-bit program (PE32, i386) cannot be a guest of this 64-bit process (WoW64 is
     * chosen once per process). After the user agrees, it goes on to NtCreateUserProcess,
     * which relaunches the title with that program alone (pw_hw_switch_program); the
     * launcher starts it under WoW64 with wowprospero and returns to the desktop at exit. */
    {
        WCHAR mode[4];
        const WCHAR *name = wcsrchr( app_name, '\\\\' );
        BOOL pe32 = FALSE, alone = FALSE;
        WCHAR world_text[512];

        world_text[0] = 0;
        name = name ? name + 1 : app_name;
        if (GetEnvironmentVariableW( L"WINE_PS4_GUESTS", mode, ARRAY_SIZE(mode) ))
        {
            IMAGE_DOS_HEADER dos;
            IMAGE_NT_HEADERS32 nt32;
            DWORD read;
            HANDLE file = CreateFileW( app_name, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                                       NULL, OPEN_EXISTING, 0, NULL );
            if (file != INVALID_HANDLE_VALUE)
            {
                if (ReadFile( file, &dos, sizeof(dos), &read, NULL ) && read == sizeof(dos) && dos.e_magic == IMAGE_DOS_SIGNATURE &&
                    SetFilePointer( file, dos.e_lfanew, NULL, FILE_BEGIN ) != INVALID_SET_FILE_POINTER &&
                    ReadFile( file, &nt32, sizeof(nt32), &read, NULL ) && read == sizeof(nt32) &&
                    nt32.Signature == IMAGE_NT_SIGNATURE && nt32.FileHeader.Machine == IMAGE_FILE_MACHINE_I386 &&
                    !(nt32.FileHeader.Characteristics & IMAGE_FILE_DLL))
                    pe32 = TRUE;
                CloseHandle( file );
            }
            /* W183: a 64-bit program marked to run alone (ps4_runs_alone) takes the same path */
            if (!pe32 && ps4_runs_alone( name )) alone = TRUE;
        }
#ifdef _WIN64
        /* W235 (pe32-en-explorer-plan.md P7): a PE32 runs as a guest of explorer's 32-bit world. The
         * relaunch stays for programs marked to run alone (OrbisRunsAlone), for every PE32 while
         * C:\\\\orbis\\\\pe32relaunch.txt exists, and when the world fails (the dialog says why) */
        if (pe32 && !ps4_runs_alone( name ) && !ps4_pe32_relaunch_forced())
        {
            DWORD error = ps4_world_launch( app_name, tidy_cmdline, cur_dir, flags, info );

            if (!error)
            {
                status = STATUS_SUCCESS;
                goto done;
            }
            swprintf( world_text, ARRAY_SIZE(world_text),
                      L"No se pudo abrir este programa de 32 bits dentro del escritorio (error %lu).\\n\\n"
                      L"Para abrirlo, OrbisDesk se reinicia y lo ejecuta solo; al cerrarlo vuelve al escritorio. "
                      L"Se cerrarán los programas abiertos. ¿Continuar?", error );
        }
#endif
#ifndef _WIN64
        if (ps4_base_taken)  /* W262 */
            swprintf( world_text, ARRAY_SIZE(world_text),
                      L"Este programa de 32 bits necesita la misma dirección de memoria que otro programa abierto "
                      L"en el escritorio y no se puede mover.\\n\\n"
                      L"Para abrirlo, OrbisDesk se reinicia y lo ejecuta solo, con los mismos argumentos; al cerrarlo "
                      L"vuelve al escritorio. Se cerrarán los programas abiertos. ¿Continuar?" );
#endif
        if (pe32 || alone)
        {
            int (WINAPI *message_box)( HWND, const WCHAR *, const WCHAR *, UINT ) =
                (void *)GetProcAddress( GetModuleHandleW( L"user32.dll" ), "MessageBoxW" );
            int answer = message_box ? message_box( NULL, world_text[0] ? world_text : pe32 ?
                L"Este es un programa de 32 bits. Para abrirlo, OrbisDesk se reinicia y lo ejecuta solo; "
                L"al cerrarlo vuelve al escritorio.\\n\\nSe cerrarán los programas abiertos. ¿Continuar?" :
                L"Este programa se ejecuta solo: OrbisDesk se reinicia para abrirlo y al cerrarlo vuelve al "
                L"escritorio.\\n\\nSe cerrarán los programas abiertos. ¿Continuar?",
                name, 0x41 /* MB_OKCANCEL | MB_ICONINFORMATION */ ) : 0;
            ERR( "PWOPEN %s image=%s answer=%d\\n", pe32 ? "pe32_relaunch" : "runs_alone_relaunch",
                 debugstr_w(app_name), answer );
            if (answer != 1 /* IDOK */)
            {
                status = message_box ? STATUS_CANCELLED : STATUS_NOT_SUPPORTED;
                goto done;
            }
        }
        else if (GetEnvironmentVariableW( L"WINE_PS4_GUESTS", mode, ARRAY_SIZE(mode) ) &&
            wcsicmp( name, L"wineboot.exe" ))
        {
            ERR( "PWOPEN reject_title_replacement image=%s\\n", debugstr_w(app_name) );
            status = STATUS_NOT_SUPPORTED;
            goto done;
        }
    }
''','CreateProcess runs a 64-bit GUI program as a guest.')
# W262 (W261: Prince of Persia's launcher starts POP.exe, which needs the launcher's base): the i386 relaunch's
# variables, with the function's own declarations
revise('kernelbase','process','''    USHORT machine = 0;
    NTSTATUS status;

    /* Process the AppName and/or CmdLine to get module name and path */''','''    USHORT machine = 0;
    NTSTATUS status;
#ifndef _WIN64
    WCHAR ps4_image[MAX_PATH], ps4_dir[MAX_PATH];  /* W262: a program whose base another guest holds */
    BOOL ps4_base_taken = FALSE;
#endif

    /* Process the AppName and/or CmdLine to get module name and path */''','The i386 relaunch of a program whose base is taken (W262).')

# W105: mountmgr is not running in the single-process hardware title. Discover
# accessible DOS roots through the real filesystem instead of an empty object
# directory. Do not invent drives, labels or successful filesystem operations.
revise('kernelbase','volume', '''DWORD WINAPI DECLSPEC_HOTPATCH GetLogicalDrives(void)
{
''', '''DWORD WINAPI DECLSPEC_HOTPATCH GetLogicalDrives(void)
{
    if (GetEnvironmentVariableW( L"WINE_PS4_GUESTS", NULL, 0 ))
    {
        WCHAR root[] = L"A:\\\\";
        DWORD mask = 0, saved_error = GetLastError(), attributes;
        unsigned int drive;
        for (drive = 0; drive < 26; drive++)
        {
            root[0] = 'A' + drive;
            attributes = GetFileAttributesW( root );
            if (attributes != INVALID_FILE_ATTRIBUTES && (attributes & FILE_ATTRIBUTE_DIRECTORY))
                mask |= 1u << drive;
        }
        ERR( "PWFS logical_drives accessible_roots=%08lx\\n", mask );
        SetLastError( saved_error );
        return mask;
    }
''', 'Enumerate accessible DOS roots when the PS4 title has no mountmgr process.')

# W184: OK or Cancel in winecfg (a guest that rundll32's applet, another guest, starts) closed the
# title. winecfg's CRT registered do_global_dtors with _crt_atexit in ucrtbase's process table and
# left with ExitProcess; rundll32's exit() then called it in the unloaded image (W183 run-0001.log:
# page fault at winecfg.exe+0x2560). A guest's atexit table is its own.
revise('ucrtbase','exit','#include "msvcrt.h"\n','#include "msvcrt.h"\n#include <winternl.h>\n','TEB access.','dlls/msvcrt/exit.c')
revise('ucrtbase','exit','''static _onexit_table_t MSVCRT_atexit_table;
''','''static _onexit_table_t MSVCRT_atexit_table;

/* PS4 hardware build (W184): the atexit table of a guest program (kernelbase ps4_guest, whose
 * threads carry it in TEB.UserReserved) is kept in the guest, after its first member. A guest's
 * exit() runs its own table only, and a guest that leaves with ExitProcess and is unloaded leaves
 * nothing in the process table for another program's exit() to call. */
static _onexit_table_t *atexit_table(void)
{
    void **guest = *(void ***)NtCurrentTeb()->UserReserved;
    return guest ? (_onexit_table_t *)(guest + 1) : &MSVCRT_atexit_table;
}
''','The atexit table of a guest.','dlls/msvcrt/exit.c')
revise('ucrtbase','exit','''    execute_onexit_table(&MSVCRT_atexit_table);''','''    execute_onexit_table(atexit_table());''',
       'exit() runs the table of its guest.','dlls/msvcrt/exit.c')
revise('ucrtbase','exit','''  register_onexit_function(&MSVCRT_atexit_table, func);''','''  register_onexit_function(atexit_table(), func);''',
       'atexit registers in the table of its guest.','dlls/msvcrt/exit.c')

# W206 (W205: Pale Moon's profile lock stayed open after it ended, and the next start quit): the
# files a guest opened from its own code are closed when it exits, as the end of its process would.
revise('kernelbase','file','#include "kernelbase.h"','#include "kernelbase.h"\n#include "ps4_guest.h"','Guest state.')
revise('kernelbase','file','''    TRACE("returning %p\\n", ret);
    return ret;
}''','''    /* W206: closed when the guest exits (ps4_guest_unload) */
    if (ret != INVALID_HANDLE_VALUE && ps4_guest_current()) ps4_guest_file_opened( ret, __builtin_return_address( 0 ) );
    TRACE("returning %p\\n", ret);
    return ret;
}''','Record the files a guest opens.')
revise('kernelbase','process','''    return set_ntstatus( NtClose( handle ));
}''','''    if (ps4_guest_current()) ps4_guest_file_closing( handle );  /* W206 */
    return set_ntstatus( NtClose( handle ));
}''','A guest file closed by the guest leaves its record.')
revise('kernelbase','process','''static void ps4_guest_unload( struct ps4_guest *guest );''','''static void ps4_guest_unload( struct ps4_guest *guest );

/* W206: the files a guest program opens (CreateFileW), closed when it exits as the end of its
 * process would (W205: Pale Moon's parent.lock, opened without sharing, stayed open after it
 * crashed, and the next start found its profile in use and quit). Only files opened from the
 * program's own code: a caller outside the Windows directory, or the C runtime; Wine's DLLs may
 * keep a file they opened on a guest thread for the whole title. A file is known by its index,
 * so a handle closed some other way (NtClose) and reused for another file is left alone. */
struct ps4_guest_file
{
    HANDLE handle;
    LONGLONG index;
};

static BOOL ps4_guest_own_code( void *caller )
{
    static WCHAR windows[MAX_PATH];
    static UINT windows_len;
    LDR_DATA_TABLE_ENTRY *mod;
    const WCHAR *path, *name;

    if (LdrFindEntryForAddress( caller, &mod )) return TRUE;  /* outside any module: the program's generated code */
    if (!windows_len) windows_len = GetWindowsDirectoryW( windows, ARRAY_SIZE(windows) );
    if (!windows_len || windows_len >= ARRAY_SIZE(windows) || !(path = mod->FullDllName.Buffer) ||
        mod->FullDllName.Length / sizeof(WCHAR) <= windows_len ||
        wcsnicmp( path, windows, windows_len ) || path[windows_len] != '\\\\') return TRUE;
    name = mod->BaseDllName.Buffer;
    return name && (!wcsicmp( name, L"ucrtbase.dll" ) || !wcsicmp( name, L"msvcrt.dll" ));
}

static BOOL ps4_guest_file_index( HANDLE handle, LONGLONG *index )
{
    FILE_INTERNAL_INFORMATION info;
    IO_STATUS_BLOCK io;

    if (NtQueryInformationFile( handle, &io, &info, sizeof(info), FileInternalInformation ) ||
        !info.IndexNumber.QuadPart) return FALSE;
    *index = info.IndexNumber.QuadPart;
    return TRUE;
}

void ps4_guest_file_opened( HANDLE handle, void *caller )
{
    struct ps4_guest *guest = ps4_guest_current();
    static BOOL full_reported;
    LONGLONG index;

    if (!guest || !ps4_guest_own_code( caller ) || !ps4_guest_file_index( handle, &index )) return;
    RtlEnterCriticalSection( &guest->lock );
    if (guest->file_count == guest->file_size)
    {
        UINT size = guest->file_size ? guest->file_size * 2 : 64;
        struct ps4_guest_file *files = NULL;

        if (size <= 16384)
            files = guest->files ? RtlReAllocateHeap( GetProcessHeap(), 0, guest->files, size * sizeof(*files) )
                                 : RtlAllocateHeap( GetProcessHeap(), 0, size * sizeof(*files) );
        if (!files)
        {
            if (!full_reported) ERR( "PWGUEST files module=%p not recorded past %u\\n", guest->module, guest->file_count );
            full_reported = TRUE;
            RtlLeaveCriticalSection( &guest->lock );
            return;
        }
        guest->files = files;
        guest->file_size = size;
    }
    guest->files[guest->file_count].handle = handle;
    guest->files[guest->file_count].index = index;
    guest->file_count++;
    RtlLeaveCriticalSection( &guest->lock );
}

void ps4_guest_file_closing( HANDLE handle )
{
    struct ps4_guest *guest = ps4_guest_current();
    UINT i;

    if (!guest || !guest->file_count) return;
    RtlEnterCriticalSection( &guest->lock );
    for (i = guest->file_count; i--;)
        if (guest->files[i].handle == handle)
        {
            guest->files[i] = guest->files[--guest->file_count];
            break;
        }
    RtlLeaveCriticalSection( &guest->lock );
}

/* after the guest's threads are gone */
static void ps4_guest_close_files( struct ps4_guest *guest )
{
    UINT i, closed = 0, stale = 0;
    LONGLONG index;

    RtlEnterCriticalSection( &guest->lock );
    for (i = 0; i < guest->file_count; i++)
    {
        if (!ps4_guest_file_index( guest->files[i].handle, &index ) || index != guest->files[i].index ||
            NtClose( guest->files[i].handle )) stale++;
        else closed++;
    }
    if (guest->file_count) ERR( "PWGUEST files module=%p closed=%u stale=%u\\n", guest->module, closed, stale );
    RtlFreeHeap( GetProcessHeap(), 0, guest->files );
    guest->files = NULL;
    guest->file_count = guest->file_size = 0;
    RtlLeaveCriticalSection( &guest->lock );
}''','Track and close the files of a guest (W206).')
revise('kernelbase','process','''static void ps4_guest_unload( struct ps4_guest *guest )
{''','''static void ps4_guest_unload( struct ps4_guest *guest )
{
    ps4_guest_close_files( guest );  /* W206 */''','Close a guest\'s files when it goes.')

# W207 (W205: Pale Moon as a guest faulted in mozglue's allocator on a freed pointer, and its own
# handler ended it): the frames of a guest thread's first access violations. Read only.
revise('kernelbase','process','''static UINT console_count;''','''/* W207: where a guest thread's access violation comes from (W205: Pale Moon faulted in mozglue's
 * allocator, mozglue.dll+0x10EEA, on a pointer read from freed memory, 0xe5e5...; its handler then
 * ended it). The first 8 of the title, before the program's handlers, which then run as before. */
static LONG CALLBACK ps4_guest_fault_trace( EXCEPTION_POINTERS *ptrs )
{
    static LONG traced;
    EXCEPTION_RECORD *rec = ptrs->ExceptionRecord;
    NT_TIB *tib = &NtCurrentTeb()->Tib;
    CONTEXT context;
    unsigned int frame;
    LONG n;

    /* W275 (W274: Need for Speed Most Wanted ended with c0000090 at an fld of a constant: an x87 stack overflow,
     * which it sees because it unmasks x87 exceptions): float exceptions are traced too, with the x87 state */
    BOOL fp = rec->ExceptionCode >= EXCEPTION_FLT_DENORMAL_OPERAND && rec->ExceptionCode <= EXCEPTION_FLT_UNDERFLOW;

    if ((rec->ExceptionCode != EXCEPTION_ACCESS_VIOLATION && !fp) || !ps4_guest_current()) return EXCEPTION_CONTINUE_SEARCH;
    if ((n = InterlockedIncrement( &traced )) > 8) return EXCEPTION_CONTINUE_SEARCH;
    ERR( "PWFAULT n=%ld thread=%04lx code=%#lx address=%p access=%Iu target=%Ix\\n", n, GetCurrentThreadId(),
         rec->ExceptionCode, rec->ExceptionAddress, rec->NumberParameters > 0 ? rec->ExceptionInformation[0] : 0,
         rec->NumberParameters > 1 ? rec->ExceptionInformation[1] : 0 );
    context = *ptrs->ContextRecord;
#ifdef __i386__
    if (fp)
        ERR( "PWFAULT n=%ld x87 flags=%#lx cw=%#lx sw=%#lx tw=%#lx top=%lu error_at=%#lx data_at=%#lx mxcsr=%#lx\\n", n,
             context.ContextFlags, context.FloatSave.ControlWord & 0xffff, context.FloatSave.StatusWord & 0xffff,
             context.FloatSave.TagWord & 0xffff, (context.FloatSave.StatusWord >> 11) & 7,
             context.FloatSave.ErrorOffset, context.FloatSave.DataOffset,
             *(const DWORD *)(context.ExtendedRegisters + 24) );
#endif
#ifdef __i386__
    /* W235: i386 guests have no unwind tables; the EBP chain */
    for (frame = 0; frame < 24; frame++)
    {
        LDR_DATA_TABLE_ENTRY *mod;

        if (LdrFindEntryForAddress( (void *)context.Eip, &mod ))
        {
            ERR( "PWFAULT n=%ld frame %u %lx\\n", n, frame, context.Eip );
            break;
        }
        ERR( "PWFAULT n=%ld frame %u %s+%lx\\n", n, frame, debugstr_w( mod->BaseDllName.Buffer ),
             context.Eip - (ULONG_PTR)mod->DllBase );
        if (context.Ebp < (ULONG_PTR)tib->StackLimit || context.Ebp + 8 > (ULONG_PTR)tib->StackBase) break;
        context.Eip = ((ULONG *)context.Ebp)[1];
        context.Ebp = ((ULONG *)context.Ebp)[0];
        if (!context.Eip) break;
    }
#else
    for (frame = 0; frame < 24; frame++)
    {
        LDR_DATA_TABLE_ENTRY *mod;
        RUNTIME_FUNCTION *function;
        ULONG_PTR base, establisher;
        void *data;

        if (LdrFindEntryForAddress( (void *)context.Rip, &mod ))
        {
            ERR( "PWFAULT n=%ld frame %u %Ix\\n", n, frame, context.Rip );
            break;
        }
        ERR( "PWFAULT n=%ld frame %u %s+%Ix\\n", n, frame, debugstr_w( mod->BaseDllName.Buffer ),
             context.Rip - (ULONG_PTR)mod->DllBase );
        if (context.Rsp < (ULONG_PTR)tib->StackLimit || context.Rsp + 8 > (ULONG_PTR)tib->StackBase) break;
        if ((function = RtlLookupFunctionEntry( context.Rip, &base, NULL )))
            RtlVirtualUnwind( UNW_FLAG_NHANDLER, base, context.Rip, function, &context, &data, &establisher, NULL );
        else
        {
            context.Rip = *(ULONG_PTR *)context.Rsp;
            context.Rsp += 8;
        }
        if (!context.Rip) break;
    }
#endif
    return EXCEPTION_CONTINUE_SEARCH;
}

static UINT console_count;''','Trace the frames of guest access violations (W207).')
revise('kernelbase','process','''    RtlInitializeCriticalSection( &guest->lock );''','''    RtlInitializeCriticalSection( &guest->lock );
    {
        static LONG fault_trace;  /* W207: once for the title, first in the chain */
        if (!InterlockedExchange( &fault_trace, 1 )) RtlAddVectoredExceptionHandler( 1, ps4_guest_fault_trace );
    }''','Add the access violation trace with the first guest (W207).')

# W208 (W207: Pale Moon as a guest could not start again; its DLLs stayed loaded with their state,
# and about 227 MB of its allocator's memory stayed reserved): a guest's own DLLs are unloaded
# when it exits, and the memory they reserved released. C:\orbis\noguestunload.txt: traces only.
revise('ntdll','exception','''#if defined(__x86_64__) && !defined(__arm64ec__)
/*
 * Some vectored exception handlers restore''','''/* PS4 hardware build (W208): the vectored handlers whose code is in an image being unmapped
 * (loader.c free_modref; a guest's DLLs, tools/build-guest-hw.py); a stale one would be called in
 * freed memory at the next exception of any thread. A handler being called right now is removed
 * by its caller when the call ends, as RemoveVectoredExceptionHandler does. Returns how many. */
ULONG ps4_remove_image_handlers( const void *base, SIZE_T size )
{
    LIST_ENTRY *lists[2] = { &vectored_exception_handlers, &vectored_continue_handlers };
    LIST_ENTRY *entry, *next;
    ULONG count = 0;
    unsigned int i;

    RtlEnterCriticalSection( &vectored_handlers_section );
    for (i = 0; i < ARRAY_SIZE(lists); i++)
    {
        for (entry = lists[i]->Flink; entry != lists[i]; entry = next)
        {
            VECTORED_HANDLER *handler = CONTAINING_RECORD( entry, VECTORED_HANDLER, entry );
            ULONG_PTR func = (ULONG_PTR)RtlDecodePointer( handler->func );

            next = entry->Flink;
            if (func - (ULONG_PTR)base >= size) continue;
            count++;
            if (!--*handler->count)
            {
                RemoveEntryList( entry );
                RtlFreeHeap( GetProcessHeap(), 0, handler );
            }
        }
    }
    RtlLeaveCriticalSection( &vectored_handlers_section );
    return count;
}

#if defined(__x86_64__) && !defined(__arm64ec__)
/*
 * Some vectored exception handlers restore''','Vectored handlers of an unmapped image (W208).')
revise('ntdll','loader','''        ERR( "PWGUEST fls_free module=%p freed=%u\\n", wm->ldr.DllBase, freed );
    }
''','''        ERR( "PWGUEST fls_free module=%p freed=%u\\n", wm->ldr.DllBase, freed );
    }
    /* PS4 hardware build (W208): no vectored handler or FLS callback is left in an unmapped DLL */
    {
        extern ULONG ps4_remove_image_handlers( const void *base, SIZE_T size );
        extern unsigned int ps4_fls_free_image( const void *base, SIZE_T size );
        ULONG handlers = ps4_remove_image_handlers( wm->ldr.DllBase, wm->ldr.SizeOfImage );
        unsigned int fls = (wm->ldr.Flags & LDR_IMAGE_IS_DLL) ? ps4_fls_free_image( wm->ldr.DllBase, wm->ldr.SizeOfImage ) : 0;

        if (handlers || fls)
            ERR( "PWGUEST unmap module=%p %s handlers=%lu fls=%u\\n", wm->ldr.DllBase,
                 debugstr_w( wm->ldr.BaseDllName.Buffer ), handlers, fls );
    }
''','Vectored handlers and FLS slots of an unmapped DLL (W208).')
revise('kernelbase','memory','#include "kernelbase.h"','#include "kernelbase.h"\n#include "ps4_guest.h"','Guest state.')
revise('kernelbase','memory','''LPVOID WINAPI DECLSPEC_HOTPATCH VirtualAlloc( void *addr, SIZE_T size, DWORD type, DWORD protect )
{
    return VirtualAllocEx( GetCurrentProcess(), addr, size, type, protect );
}''','''LPVOID WINAPI DECLSPEC_HOTPATCH VirtualAlloc( void *addr, SIZE_T size, DWORD type, DWORD protect )
{
    void *ret = VirtualAllocEx( GetCurrentProcess(), addr, size, type, protect );

    /* W208: released when the guest's own modules are unloaded (ps4_guest_unload) */
    if (ret && (type & MEM_RESERVE) && ps4_guest_current()) ps4_guest_memory_reserved( ret, __builtin_return_address( 0 ) );
    return ret;
}''','Record the memory a guest reserves.')
revise('kernelbase','memory','''BOOL WINAPI DECLSPEC_HOTPATCH VirtualFree( void *addr, SIZE_T size, DWORD type )
{''','''BOOL WINAPI DECLSPEC_HOTPATCH VirtualFree( void *addr, SIZE_T size, DWORD type )
{
    if (type == MEM_RELEASE && ps4_guest_current()) ps4_guest_memory_released( addr );  /* W208 */''',
       'A region the guest releases leaves its record.')
revise('kernelbase','process','''/* after the guest's threads are gone */''','''/* W208: memory reserved with VirtualAlloc from a guest's own code (the files' rule above), released
 * when its own modules are unloaded (W207: about 227 MB of Pale Moon's allocator per run) */
struct ps4_guest_region
{
    void *base;
};

void ps4_guest_memory_reserved( void *base, void *caller )
{
    struct ps4_guest *guest = ps4_guest_current();
    static BOOL full_reported;

    if (!guest || !ps4_guest_own_code( caller )) return;
    RtlEnterCriticalSection( &guest->lock );
    if (guest->region_count == guest->region_size)
    {
        UINT size = guest->region_size ? guest->region_size * 2 : 256;
        struct ps4_guest_region *regions = NULL;

        if (size <= 65536)
            regions = guest->regions ? RtlReAllocateHeap( GetProcessHeap(), 0, guest->regions, size * sizeof(*regions) )
                                     : RtlAllocateHeap( GetProcessHeap(), 0, size * sizeof(*regions) );
        if (!regions)
        {
            if (!full_reported) ERR( "PWGUEST memory module=%p not recorded past %u regions\\n", guest->module, guest->region_count );
            full_reported = TRUE;
            RtlLeaveCriticalSection( &guest->lock );
            return;
        }
        guest->regions = regions;
        guest->region_size = size;
    }
    guest->regions[guest->region_count++].base = base;
    RtlLeaveCriticalSection( &guest->lock );
}

void ps4_guest_memory_released( void *base )
{
    struct ps4_guest *guest = ps4_guest_current();
    UINT i;

    if (!guest || !guest->region_count) return;
    RtlEnterCriticalSection( &guest->lock );
    for (i = guest->region_count; i--;)
        if (guest->regions[i].base == base)
        {
            guest->regions[i] = guest->regions[--guest->region_count];
            break;
        }
    RtlLeaveCriticalSection( &guest->lock );
}

/* W208: the guest's own modules: loaded since it started, from outside the Windows directory */
struct ps4_guest_own
{
    char *base;
    SIZE_T size;
    SHORT count;
    WCHAR name[48];
};

static BOOL ps4_guest_outside_windows( const UNICODE_STRING *path )
{
    static WCHAR windows[MAX_PATH];
    static UINT windows_len;

    if (!windows_len) windows_len = GetWindowsDirectoryW( windows, ARRAY_SIZE(windows) );
    if (!path->Buffer || !windows_len || windows_len >= ARRAY_SIZE(windows)) return FALSE;
    return path->Length / sizeof(WCHAR) <= windows_len || wcsnicmp( path->Buffer, windows, windows_len ) ||
           path->Buffer[windows_len] != '\\\\';
}

static const struct ps4_guest_own *ps4_guest_own_at( const struct ps4_guest_own *own, UINT count, ULONG_PTR address )
{
    UINT i;

    for (i = 0; i < count; i++)
        if (address - (ULONG_PTR)own[i].base < own[i].size) return &own[i];
    return NULL;
}

/* W209: the modules of the process before its first guest, and the guests running (W208 counted
 * only modules loaded since a guest's launch, and the next start of a guest whose exit had not
 * unloaded them found them loaded: "own_modules ... count=0") */
static HMODULE *ps4_baseline;
static UINT ps4_baseline_count;
static struct ps4_guest *ps4_live_guests[64];
static UINT ps4_live_count;
static RTL_SRWLOCK ps4_live_lock = RTL_SRWLOCK_INIT;

static void ps4_guest_unload_own( struct ps4_guest *guest, BOOL leftovers );

/* at a guest's launch, before its EXE loads */
static void ps4_guest_note_modules( struct ps4_guest *guest )
{
    RtlAcquireSRWLockExclusive( &ps4_live_lock );
    if (!ps4_baseline)
    {
        LIST_ENTRY *list = &NtCurrentTeb()->Peb->LdrData->InLoadOrderModuleList, *entry;
        ULONG_PTR magic;
        UINT count = 0;

        LdrLockLoaderLock( 0, NULL, &magic );
        for (entry = list->Flink; entry != list; entry = entry->Flink) count++;
        if ((ps4_baseline = RtlAllocateHeap( GetProcessHeap(), 0, count * sizeof(HMODULE) )))
            for (entry = list->Flink; entry != list; entry = entry->Flink)
                ps4_baseline[ps4_baseline_count++] = CONTAINING_RECORD( entry, LDR_DATA_TABLE_ENTRY, InLoadOrderLinks )->DllBase;
        LdrUnlockLoaderLock( 0, magic );
    }
    guest->modules_before = ps4_baseline;
    guest->modules_before_count = ps4_baseline_count;
    /* W258 (W257: Portal): every module loaded now, before this guest's EXE. A module that appears later in
     * another live guest's folder is this guest's own (ps4_guest_unload_own) */
    {
        LIST_ENTRY *list = &NtCurrentTeb()->Peb->LdrData->InLoadOrderModuleList, *entry;
        ULONG_PTR magic;
        UINT count = 0;

        LdrLockLoaderLock( 0, NULL, &magic );
        for (entry = list->Flink; entry != list; entry = entry->Flink) count++;
        guest->modules_at_launch_count = 0;
        if ((guest->modules_at_launch = RtlAllocateHeap( GetProcessHeap(), 0, (count + 1) * sizeof(HMODULE) )))
            for (entry = list->Flink; entry != list; entry = entry->Flink)
                guest->modules_at_launch[guest->modules_at_launch_count++] =
                    CONTAINING_RECORD( entry, LDR_DATA_TABLE_ENTRY, InLoadOrderLinks )->DllBase;
        LdrUnlockLoaderLock( 0, magic );
    }
    RtlReleaseSRWLockExclusive( &ps4_live_lock );

    /* the modules of guests that ended without unloading them */
    ps4_guest_unload_own( guest, TRUE );

    RtlAcquireSRWLockExclusive( &ps4_live_lock );
    if (ps4_live_count < ARRAY_SIZE(ps4_live_guests)) ps4_live_guests[ps4_live_count++] = guest;
    RtlReleaseSRWLockExclusive( &ps4_live_lock );
}

/* at the end of a guest's unload */
static void ps4_guest_live_remove( struct ps4_guest *guest )
{
    UINT i;

    RtlAcquireSRWLockExclusive( &ps4_live_lock );
    for (i = 0; i < ps4_live_count; i++)
        if (ps4_live_guests[i] == guest)
        {
            ps4_live_guests[i] = ps4_live_guests[--ps4_live_count];
            break;
        }
    RtlReleaseSRWLockExclusive( &ps4_live_lock );
}

/* does a thread start in, or run, the guest's own code? It is suspended only for its context;
 * its stack is walked after it runs again, within its TEB's limits */
static BOOL ps4_guest_thread_in( DWORD tid, const struct ps4_guest_own *own, UINT own_count )
{
    HANDLE thread = OpenThread( THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT | THREAD_QUERY_INFORMATION, FALSE, tid );
    CONTEXT context = {.ContextFlags = CONTEXT_CONTROL | CONTEXT_INTEGER};
    THREAD_BASIC_INFORMATION basic;
    const struct ps4_guest_own *in;
    ULONG_PTR start = 0, stack_low = 0, stack_high = 0;
    DWORD suspend;
    BOOL got;
    unsigned int frame;

    if (!thread) return FALSE;  /* gone */
    NtQueryInformationThread( thread, ThreadQuerySetWin32StartAddress, &start, sizeof(start), NULL );
    if (!NtQueryInformationThread( thread, ThreadBasicInformation, &basic, sizeof(basic), NULL ) && basic.TebBaseAddress)
    {
        NT_TIB *tib = basic.TebBaseAddress;
        stack_low = (ULONG_PTR)tib->StackLimit;
        stack_high = (ULONG_PTR)tib->StackBase;
    }
    if ((in = ps4_guest_own_at( own, own_count, start )))
    {
        ERR( "PWGUEST kept: thread %04lx starts in %s+%Ix\\n", tid, debugstr_w(in->name), start - (ULONG_PTR)in->base );
        CloseHandle( thread );
        return TRUE;
    }
    suspend = SuspendThread( thread );
    got = suspend != (DWORD)-1 && GetThreadContext( thread, &context );
    if (suspend != (DWORD)-1) ResumeThread( thread );
    CloseHandle( thread );
    if (!got) return FALSE;  /* ended meanwhile */
#ifdef __i386__
    /* W235: i386 guests have no unwind tables; the EBP chain */
    for (frame = 0; frame < 32; frame++)
    {
        LDR_DATA_TABLE_ENTRY *mod;

        if ((in = ps4_guest_own_at( own, own_count, context.Eip )))
        {
            ERR( "PWGUEST kept: thread %04lx in %s+%lx (frame %u)\\n", tid, debugstr_w(in->name),
                 context.Eip - (ULONG_PTR)in->base, frame );
            return TRUE;
        }
        if (context.Ebp < stack_low || context.Ebp + 8 > stack_high ||
            LdrFindEntryForAddress( (void *)context.Eip, &mod )) break;
        context.Eip = ((ULONG *)context.Ebp)[1];
        context.Ebp = ((ULONG *)context.Ebp)[0];
        if (!context.Eip) break;
    }
    return FALSE;
#else
    for (frame = 0; frame < 32; frame++)
    {
        RUNTIME_FUNCTION *function;
        ULONG_PTR base, establisher;
        LDR_DATA_TABLE_ENTRY *mod;
        void *data;

        if ((in = ps4_guest_own_at( own, own_count, context.Rip )))
        {
            ERR( "PWGUEST kept: thread %04lx in %s+%Ix (frame %u)\\n", tid, debugstr_w(in->name),
                 context.Rip - (ULONG_PTR)in->base, frame );
            return TRUE;
        }
        if (context.Rsp < stack_low || context.Rsp + 8 > stack_high ||
            LdrFindEntryForAddress( (void *)context.Rip, &mod )) break;
        if ((function = RtlLookupFunctionEntry( context.Rip, &base, NULL )))
            RtlVirtualUnwind( UNW_FLAG_NHANDLER, base, context.Rip, function, &context, &data, &establisher, NULL );
        else
        {
            context.Rip = *(ULONG_PTR *)context.Rsp;
            context.Rsp += 8;
        }
        if (!context.Rip) break;
    }
    return FALSE;
#endif
}

/* the threads of the process, other than this one, in the guest's own code; ~0u when unknown */
static UINT ps4_guest_threads_in( const struct ps4_guest_own *own, UINT own_count )
{
    SYSTEM_PROCESS_INFORMATION *spi;
    ULONG size = 0x40000;
    char *buffer = NULL;
    NTSTATUS status;
    DWORD pid = GetCurrentProcessId(), self = GetCurrentThreadId();
    UINT found = 0, i;

    for (;;)
    {
        if (!(buffer = RtlAllocateHeap( GetProcessHeap(), 0, size ))) return ~0u;
        if ((status = NtQuerySystemInformation( SystemProcessInformation, buffer, size, NULL )) != STATUS_INFO_LENGTH_MISMATCH) break;
        RtlFreeHeap( GetProcessHeap(), 0, buffer );
        if ((size *= 2) > 0x1000000) return ~0u;
    }
    if (status)
    {
        RtlFreeHeap( GetProcessHeap(), 0, buffer );
        return ~0u;
    }
    for (spi = (SYSTEM_PROCESS_INFORMATION *)buffer;; spi = (SYSTEM_PROCESS_INFORMATION *)((char *)spi + spi->NextEntryOffset))
    {
        if (HandleToULong( spi->UniqueProcessId ) == pid)
        {
            for (i = 0; i < spi->dwThreadCount; i++)
            {
                DWORD tid = HandleToULong( spi->ti[i].ClientId.UniqueThread );
                if (tid != self && ps4_guest_thread_in( tid, own, own_count )) found++;
            }
            break;
        }
        if (!spi->NextEntryOffset) break;
    }
    RtlFreeHeap( GetProcessHeap(), 0, buffer );
    return found;
}

/* W211: is an own module still mapped? */
static BOOL ps4_guest_own_loaded( const struct ps4_guest_own *own )
{
    LDR_DATA_TABLE_ENTRY *mod;

    return !LdrFindEntryForAddress( own->base, &mod ) && mod->DllBase == own->base;
}

/* W211: does a module import, or delay-load, a DLL of this name? (its own headers) */
static BOOL ps4_guest_name_is( const char *import, const WCHAR *name )
{
    while (*import && *name)
    {
        WCHAR a = (unsigned char)*import++, b = *name++;
        if (a >= 'A' && a <= 'Z') a += 'a' - 'A';
        if (b >= 'A' && b <= 'Z') b += 'a' - 'A';
        if (a != b) return FALSE;
    }
    return !*import && !*name;
}

static BOOL ps4_guest_imports( const struct ps4_guest_own *from, const WCHAR *name )
{
    const IMAGE_IMPORT_DESCRIPTOR *imports;
    const IMAGE_DELAYLOAD_DESCRIPTOR *delayed;
    ULONG size;

    if ((imports = RtlImageDirectoryEntryToData( (HMODULE)from->base, TRUE, IMAGE_DIRECTORY_ENTRY_IMPORT, &size )))
        for (; imports->Name; imports++)
            if ((SIZE_T)imports->Name < from->size && ps4_guest_name_is( from->base + imports->Name, name )) return TRUE;
    if ((delayed = RtlImageDirectoryEntryToData( (HMODULE)from->base, TRUE, IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT, &size )))
        for (; delayed->DllNameRVA; delayed++)
            if ((SIZE_T)delayed->DllNameRVA < from->size && ps4_guest_name_is( from->base + delayed->DllNameRVA, name )) return TRUE;
    return FALSE;
}

/* after the guest's EXE is unloaded (ps4_guest_unload); leftovers: at a launch, the modules of
 * guests that ended (W209) */
static void ps4_guest_unload_own( struct ps4_guest *guest, BOOL leftovers )
{
    static WCHAR live_dirs[ARRAY_SIZE(ps4_live_guests)][MAX_PATH];
    UINT live_dir_count = 0, k;
    struct
    {
        UINT size, style;
        void *proc;
        int class_extra, window_extra;
        void *instance, *icon, *cursor, *background;
        const WCHAR *menu, *name;
        void *small_icon;
    } info;
    static struct ps4_guest_own own[256];
    static RTL_SRWLOCK own_lock = RTL_SRWLOCK_INIT;
    LIST_ENTRY *list = &NtCurrentTeb()->Peb->LdrData->InLoadOrderModuleList, *entry;
    HMODULE user32 = GetModuleHandleW( L"user32.dll" );
    BOOL (WINAPI *unregister)( const WCHAR *, HINSTANCE ) = (void *)GetProcAddress( user32, "UnregisterClassW" );
    int (WINAPI *atom_name)( UINT, WCHAR *, int ) = (void *)GetProcAddress( user32, "GetClipboardFormatNameW" );
    BOOL (WINAPI *class_info)( HINSTANCE, const WCHAR *, void * ) = (void *)GetProcAddress( user32, "GetClassInfoExW" );
    BOOL (WINAPI *class_infoA)( HINSTANCE, const char *, void * ) = (void *)GetProcAddress( user32, "GetClassInfoExA" );
    BOOL trace_only = GetFileAttributesW( L"C:\\\\orbis\\\\noguestunload.txt" ) != INVALID_FILE_ATTRIBUTES;
    UINT own_count = 0, i, j, threads, atom, unused = 0, classes = 0, in_use = 0, released = 0;
    LPTOP_LEVEL_EXCEPTION_FILTER filter;
    SIZE_T released_bytes = 0;
    ULONG lock_state = 0;
    ULONG_PTR magic = 0;
    int tries;
    WCHAR name[256];

    /* one guest at a time: own[] is shared. W214: a launch (explorer's thread) does not wait for
     * another guest's unload; its leftovers are left to that one */
    if (!leftovers) RtlAcquireSRWLockExclusive( &own_lock );
    else if (!RtlTryAcquireSRWLockExclusive( &own_lock ))
    {
        ERR( "PWGUEST own_modules leftovers skipped: another unload runs\\n" );
        return;
    }
    /* W214 (W212: "loader lock busy for 2 s" after a normal exit, and the next starts exited with
     * status 1): an exit waits up to 30 s, a launch 2 s; the owner is traced */
    for (tries = 0; tries < (leftovers ? 200 : 3000); tries++)
    {
        if (!LdrLockLoaderLock( 2 /* LDR_LOCK_LOADER_LOCK_FLAG_TRY_ONLY */, &lock_state, &magic ) && lock_state == 1) break;
        /* W215 (W214: "waits for the loader lock, owner 0000" for 30 s): no owner, a terminated
         * waiter's LockCount; a blocking acquire takes it at once */
        if (!((RTL_CRITICAL_SECTION *)NtCurrentTeb()->Peb->LoaderLock)->OwningThread &&
            !LdrLockLoaderLock( 0, NULL, &magic ))
        {
            ERR( "PWGUEST own_modules module=%p took the ownerless loader lock after %d tries\\n", guest->module, tries );
            lock_state = 1;
            break;
        }
        if (!(tries % 500))
            ERR( "PWGUEST own_modules module=%p waits for the loader lock, owner %04lx\\n", guest->module,
                 HandleToULong( ((RTL_CRITICAL_SECTION *)NtCurrentTeb()->Peb->LoaderLock)->OwningThread ) );
        Sleep( 10 );
    }
    if (lock_state != 1)
    {
        ERR( "PWGUEST own_modules module=%p kept: loader lock busy for %d s\\n", guest->module, tries / 100 );
        RtlReleaseSRWLockExclusive( &own_lock );
        return;
    }
    /* W209: the folders of the other guests running; their modules are theirs. Read from the loader's
     * entries under its lock (GetModuleFileName would wait for the lock) */
    RtlAcquireSRWLockShared( &ps4_live_lock );
    for (i = 0; i < ps4_live_count; i++)
    {
        LDR_DATA_TABLE_ENTRY *mod;
        WCHAR *slash;

        if (ps4_live_guests[i] == guest || !ps4_live_guests[i]->module ||
            LdrFindEntryForAddress( ps4_live_guests[i]->module, &mod ) || !mod->FullDllName.Buffer) continue;
        lstrcpynW( live_dirs[live_dir_count], mod->FullDllName.Buffer, MAX_PATH );
        if ((slash = wcsrchr( live_dirs[live_dir_count], '\\\\' ))) slash[1] = 0, live_dir_count++;
    }
    RtlReleaseSRWLockShared( &ps4_live_lock );
    for (entry = list->Flink; entry != list && own_count < ARRAY_SIZE(own); entry = entry->Flink)
    {
        LDR_DATA_TABLE_ENTRY *mod = CONTAINING_RECORD( entry, LDR_DATA_TABLE_ENTRY, InLoadOrderLinks );

        if (mod->LoadCount == -1 || !ps4_guest_outside_windows( &mod->FullDllName )) continue;
        for (j = 0; j < guest->modules_before_count; j++) if (guest->modules_before[j] == mod->DllBase) break;
        if (j < guest->modules_before_count) continue;
        for (k = 0; k < live_dir_count; k++)
            if (!wcsnicmp( mod->FullDllName.Buffer, live_dirs[k], wcslen( live_dirs[k] ))) break;
        if (k < live_dir_count)
        {
            /* W258 (W257: Portal.exe waits in E:\\PC\\Portal while its hl2.exe ends): another live guest's folder;
             * still this guest's own if it was loaded after this guest's launch. Leftovers as before */
            for (j = 0; !leftovers && guest->modules_at_launch && j < guest->modules_at_launch_count; j++)
                if (guest->modules_at_launch[j] == mod->DllBase) break;
            if (leftovers || !guest->modules_at_launch || j < guest->modules_at_launch_count) continue;
            ERR( "PWGUEST own %s (after launch, in a live guest's folder)\\n", debugstr_w( mod->BaseDllName.Buffer ) );
        }
        own[own_count].base = mod->DllBase;
        own[own_count].size = mod->SizeOfImage;
        own[own_count].count = mod->LoadCount;
        lstrcpynW( own[own_count].name, mod->BaseDllName.Buffer ? mod->BaseDllName.Buffer : L"?", ARRAY_SIZE(own[0].name) );
        own_count++;
    }
    LdrUnlockLoaderLock( 0, magic );
    ERR( "PWGUEST own_modules module=%p count=%u trace_only=%u regions=%u leftovers=%u terminated=%u live=%u\\n",
         guest->module, own_count, trace_only, guest->region_count, leftovers, guest->terminated, live_dir_count );
    for (i = 0; i < own_count; i++)
        ERR( "PWGUEST own %s base=%p size=%Ix refcount=%d\\n", debugstr_w(own[i].name), own[i].base, own[i].size, own[i].count );
    if (!own_count) goto done;

    threads = ps4_guest_threads_in( own, own_count );
    if (threads == ~0u) ERR( "PWGUEST own_modules module=%p kept: the thread list is not available\\n", guest->module );

    /* window classes whose procedure is in them (W068 for the EXE, the same test for these). A
     * local class is found under the instance it was registered with: the EXE's or one of these
     * modules'; global and builtin classes are found under any, and their procedure decides */
    for (atom = 0xc000; unregister && atom_name && class_info && class_infoA && atom <= 0xffff && unused < 256; atom++)
    {
        if (!atom_name( atom, name, ARRAY_SIZE(name) )) { unused++; continue; }
        unused = 0;
        for (i = 0; i <= own_count; i++)
        {
            HINSTANCE instance = i < own_count ? (HINSTANCE)own[i].base : (HINSTANCE)guest->module;

            info.size = sizeof(info);
            if (!class_info( instance, (const WCHAR *)(ULONG_PTR)atom, &info )) continue;
            if (((ULONG_PTR)info.proc >> 16) == 0xffff)  /* a winproc handle: registered as ANSI */
            {
                info.size = sizeof(info);
                if (!class_infoA( instance, (const char *)(ULONG_PTR)atom, &info )) continue;
            }
            if (!ps4_guest_own_at( own, own_count, (ULONG_PTR)info.proc )) continue;
            if (trace_only || threads) classes++;
            else if (unregister( (const WCHAR *)(ULONG_PTR)atom, instance )) classes++;
            else
            {
                ERR( "PWGUEST kept: class %s still in use (error %lu)\\n", debugstr_w(name), GetLastError() );
                in_use++;
            }
            break;
        }
    }
    filter = SetUnhandledExceptionFilter( NULL );
    if (!ps4_guest_own_at( own, own_count, (ULONG_PTR)filter ) || trace_only || threads) SetUnhandledExceptionFilter( filter );
    else ERR( "PWGUEST own_modules cleared exception filter %p\\n", filter );
    ERR( "PWGUEST own_modules module=%p classes=%u in_use=%u threads=%u\\n", guest->module, classes, in_use,
         threads == ~0u ? 0 : threads );
    if (trace_only || threads || in_use)
    {
        ERR( "PWGUEST own_modules module=%p kept (%s)\\n", guest->module,
             trace_only ? "noguestunload.txt" : threads ? "threads in their code" : "classes in use" );
        goto done;
    }

    /* W209: no DllMain(DETACH) for a guest ended by TerminateProcess or a fault, nor for what ended
     * guests left: Windows skips DLL_PROCESS_DETACH when a process is terminated, and their code
     * would run without the threads it expects (W208).
     * W211: for any guest; the other threads of one that exits normally are ended too, and in W210
     * MSVCP140's detach called into a VCRUNTIME140 already unmapped and held the loader lock */
    {
        if (!LdrLockLoaderLock( 0, NULL, &magic ))
        {
            for (i = 0; i < own_count; i++)
            {
                LDR_DATA_TABLE_ENTRY *mod;

                if (!LdrFindEntryForAddress( own[i].base, &mod ) && mod->DllBase == own[i].base)
                    mod->Flags &= ~LDR_PROCESS_ATTACHED;
            }
            LdrUnlockLoaderLock( 0, magic );
        }
        ERR( "PWGUEST own_modules module=%p detach skipped (%s)\\n", guest->module,
             leftovers ? "leftovers" : guest->terminated ? "terminated" : "exit" );
    }

    /* W211: in rounds, once per round for each module no other one still loaded imports (W210:
     * unloading each until gone dropped the import references of others, and VCRUNTIME140 went
     * while MSVCP140 and mozglue still used it); their imports go with them */
    {
        UINT round, remaining = 0;
        BOOL progress = TRUE;

        for (round = 0; round < 64 && progress; round++)
        {
            progress = FALSE;
            for (i = own_count; i--;)
            {
                if (!ps4_guest_own_loaded( &own[i] )) continue;
                for (k = 0; k < own_count; k++)
                    if (k != i && ps4_guest_own_loaded( &own[k] ) && ps4_guest_imports( &own[k], own[i].name )) break;
                if (k < own_count) continue;
                LdrUnloadDll( (HMODULE)own[i].base );
                progress = TRUE;
            }
        }
        for (i = 0; i < own_count; i++)
        {
            if (!ps4_guest_own_loaded( &own[i] )) continue;
            ERR( "PWGUEST kept: %s still loaded after %u rounds\\n", debugstr_w(own[i].name), round );
            remaining++;
        }
        ERR( "PWGUEST unloaded module=%p own=%u remaining=%u rounds=%u\\n", guest->module, own_count, remaining, round );
        if (remaining)
        {
            ERR( "PWGUEST memory module=%p regions=%u kept: modules still loaded\\n", guest->module, guest->region_count );
            goto done;
        }
    }

    /* the memory their code reserved */
    RtlEnterCriticalSection( &guest->lock );
    for (i = 0; i < guest->region_count; i++)
    {
        MEMORY_BASIC_INFORMATION mbi;
        void *addr = guest->regions[i].base;
        SIZE_T size = 0;

        if (!VirtualQuery( addr, &mbi, sizeof(mbi) ) || mbi.AllocationBase != addr || mbi.State == MEM_FREE) continue;
        if (!NtFreeVirtualMemory( GetCurrentProcess(), &addr, &size, MEM_RELEASE ))
        {
            released++;
            released_bytes += size;
        }
    }
    ERR( "PWGUEST memory module=%p regions=%u released=%u bytes=%Iu\\n", guest->module, guest->region_count, released,
         released_bytes );
    RtlFreeHeap( GetProcessHeap(), 0, guest->regions );
    guest->regions = NULL;
    guest->region_count = guest->region_size = 0;
    RtlLeaveCriticalSection( &guest->lock );

done:
    RtlReleaseSRWLockExclusive( &own_lock );
}

/* after the guest's threads are gone */''','Unload the own modules of a guest and release their memory (W208).')
revise('kernelbase','process','''    RtlInitializeCriticalSection( &guest->lock );''','''    RtlInitializeCriticalSection( &guest->lock );
    ps4_guest_note_modules( guest );  /* W208 */''','Note the modules loaded before the guest (W208).')
revise('kernelbase','process','''            ERR( "PWGUEST unload_end module=%p freed=%u gl=%p gallium=%p hud=%p\\n", guest->module, freed,
                 GetModuleHandleW( L"opengl32.dll" ), GetModuleHandleW( L"libgallium_wgl.dll" ),
                 GetModuleHandleW( L"libMangoHud.dll" ) );
        }''','''            ERR( "PWGUEST unload_end module=%p freed=%u gl=%p gallium=%p hud=%p\\n", guest->module, freed,
                 GetModuleHandleW( L"opengl32.dll" ), GetModuleHandleW( L"libgallium_wgl.dll" ),
                 GetModuleHandleW( L"libMangoHud.dll" ) );
        }
        ps4_guest_unload_own( guest, FALSE );  /* W208 */
        ps4_guest_live_remove( guest );  /* W209 */''','Then its own modules (W208).')

# W208 (W207: Pale Moon's unhandled fault took the whole title down through ntdll's
# NtTerminateProcess): an unhandled exception on a guest thread ends the guest only.
revise('kernelbase','debug','#include "kernelbase.h"','#include "kernelbase.h"\n#include "ps4_guest.h"','Guest state.')
revise('kernelbase','debug','''        if (top_filter && !nested)
        {
            LONG ret = top_filter( epointers );
            if (ret != EXCEPTION_CONTINUE_SEARCH) return ret;
        }
''','''        if (top_filter && !nested)
        {
            LONG ret = top_filter( epointers );
            if (ret != EXCEPTION_CONTINUE_SEARCH) return ret;
        }

        /* W208: a guest's unhandled exception ends the guest (ps4_guest_exit_process, through
         * TerminateProcess), as the end of its own process would; ntdll would end the title */
        if (ps4_guest_current())
        {
            ERR( "PWGUEST unhandled exception %08lx at %p on thread %04lx: the guest ends\\n",
                 rec->ExceptionCode, rec->ExceptionAddress, GetCurrentThreadId() );
            TerminateProcess( GetCurrentProcess(), rec->ExceptionCode );
        }
''','An unhandled exception on a guest thread ends the guest (W208).')
# W262 (W261: Worms 4 Mayhem faulted, its own top-level filter answered EXCEPTION_EXECUTE_HANDLER, so W208's check never
# ran, and ntdll's thread start called NtTerminateProcess, which wow64 (B1) turns into the end of that thread only: the
# guest stayed live and held 0x400000 for the next 32-bit programs, error 487): that path ends the guest.
for unit in ('signal_i386','signal_x86_64'):
    revise('ntdll',unit,'''    __EXCEPT(call_unhandled_exception_filter)
    {
        NtTerminateProcess( GetCurrentProcess(), GetExceptionCode() );
    }''','''    __EXCEPT(call_unhandled_exception_filter)
    {
        /* PS4 hardware build (W262): the program's own top-level filter handed the exception back for the
         * process to end; on a guest's thread that ends the guest, as RtlExitUserProcess does (W052) */
        void **guest = *(void ***)NtCurrentTeb()->UserReserved;

        if (guest && guest[0])
        {
            ERR( "PWGUEST unhandled exception %08lx on thread %04lx after the program's own filter: the guest ends\\n",
                 (ULONG)GetExceptionCode(), HandleToULong( NtCurrentTeb()->ClientId.UniqueThread ) );
            ((void (WINAPI *)(void *, DWORD))guest[0])( guest, GetExceptionCode() );
        }
        NtTerminateProcess( GetCurrentProcess(), GetExceptionCode() );
    }''','A thread start\'s unhandled exception on a guest thread ends the guest (W262).')
# W244 (W242 run 20261105T143753Z, run-0001.log:18546): VLC's guest ended, its 41 threads were ended
# and its own modules unloaded (libxml_plugin.dll among them, "threads=0" in them); then thread 0070,
# which carried no guest, executed at 00000007F73CBB70 inside the freed libxml_plugin and the title
# ended through start_debugger. A thread with no guest that executes memory no longer committed
# (code of an image unloaded with a guest) ends alone, with its start address in the log; any other
# unhandled exception goes on as before. Its locks, if it held any, stay held: the trace says so.
revise('kernelbase','debug','''            TerminateProcess( GetCurrentProcess(), rec->ExceptionCode );
        }
''','''            TerminateProcess( GetCurrentProcess(), rec->ExceptionCode );
        }

        /* W244: a thread outside any guest running code that is no longer mapped ends alone */
        if (!ps4_guest_current() && rec->ExceptionCode == EXCEPTION_ACCESS_VIOLATION &&
            rec->NumberParameters >= 2 && rec->ExceptionInformation[0] == EXCEPTION_EXECUTE_FAULT)
        {
            MEMORY_BASIC_INFORMATION info;

            if (VirtualQuery( (void *)rec->ExceptionInformation[1], &info, sizeof(info) ) && info.State != MEM_COMMIT)
            {
                WCHAR start_name[MAX_PATH] = L"-";
                HMODULE start_module = NULL;
                void *start = NULL;

                NtQueryInformationThread( GetCurrentThread(), ThreadQuerySetWin32StartAddress, &start, sizeof(start), NULL );
                if (GetModuleHandleExW( GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                                        start, &start_module ))
                    GetModuleFileNameW( start_module, start_name, ARRAY_SIZE(start_name) );
                ERR( "PWGUEST stale_code thread=%04lx addr=%p state=%#lx start=%p %s: no guest, the thread ends\\n",
                     GetCurrentThreadId(), rec->ExceptionAddress, info.State, start, debugstr_w(start_name) );
                RtlExitUserThread( rec->ExceptionCode );
            }
        }
''','A thread with no guest that runs unmapped code ends alone (W244).')

# W210 (W209: Pale Moon restarted itself after rebuilding its startup cache, and the new start, a
# guest loaded while the first one still ran, got its modules initialised and exited with status 1):
# a guest starting its own program again gets the new start once it has ended and unloaded.
revise('kernelbase','process','''static BOOL ps4_guest_launch( const WCHAR *app_name, const WCHAR *cmd_line, DWORD flags, PROCESS_INFORMATION *info )
{''','''/* W210: the start of a guest's own program from that guest, made once the guest has gone */
static BOOL ps4_guest_launch( const WCHAR *app_name, const WCHAR *cmd_line, DWORD flags, PROCESS_INFORMATION *info );

struct ps4_relaunch
{
    WCHAR *app, *cmd;
    DWORD flags;
    HANDLE ended;
};

static DWORD WINAPI ps4_guest_relaunch( void *arg )
{
    struct ps4_relaunch *relaunch = arg;
    PROCESS_INFORMATION started = {0};
    DWORD wait = WaitForSingleObject( relaunch->ended, 15000 );

    ERR( "PWGUEST relaunch app=%s parent_wait=%lu\\n", debugstr_w(relaunch->app), wait );
    if (ps4_guest_launch( relaunch->app, relaunch->cmd, relaunch->flags, &started ))
    {
        if (started.hThread) CloseHandle( started.hThread );
        if (started.hProcess) CloseHandle( started.hProcess );
    }
    else ERR( "PWGUEST relaunch app=%s failed, error %lu\\n", debugstr_w(relaunch->app), GetLastError() );
    RtlFreeHeap( GetProcessHeap(), 0, relaunch->app );
    RtlFreeHeap( GetProcessHeap(), 0, relaunch->cmd );
    RtlFreeHeap( GetProcessHeap(), 0, relaunch );
    return 0;
}

static BOOL ps4_guest_relaunch_later( struct ps4_guest *self, const WCHAR *app_name, const WCHAR *cmd_line, DWORD flags,
                                      PROCESS_INFORMATION *info )
{
    struct ps4_relaunch *relaunch = RtlAllocateHeap( GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(*relaunch) );
    UINT app_len = lstrlenW( app_name ) + 1, cmd_len = lstrlenW( cmd_line ) + 1;
    HANDLE thread;
    DWORD tid;

    if (!relaunch) return FALSE;
    relaunch->app = RtlAllocateHeap( GetProcessHeap(), 0, app_len * sizeof(WCHAR) );
    relaunch->cmd = RtlAllocateHeap( GetProcessHeap(), 0, cmd_len * sizeof(WCHAR) );
    if (!relaunch->app || !relaunch->cmd)
    {
        RtlFreeHeap( GetProcessHeap(), 0, relaunch->app );
        RtlFreeHeap( GetProcessHeap(), 0, relaunch->cmd );
        RtlFreeHeap( GetProcessHeap(), 0, relaunch );
        return FALSE;
    }
    memcpy( relaunch->app, app_name, app_len * sizeof(WCHAR) );
    memcpy( relaunch->cmd, cmd_line, cmd_len * sizeof(WCHAR) );
    relaunch->flags = flags;
    relaunch->ended = self->ended;
    /* not a thread of the guest: its exit must not end it (W184) */
    ps4_guest_set( NtCurrentTeb(), NULL );
    thread = CreateThread( NULL, 0, ps4_guest_relaunch, relaunch, 0, &tid );
    ps4_guest_set( NtCurrentTeb(), self );
    if (!thread)
    {
        RtlFreeHeap( GetProcessHeap(), 0, relaunch->app );
        RtlFreeHeap( GetProcessHeap(), 0, relaunch->cmd );
        RtlFreeHeap( GetProcessHeap(), 0, relaunch );
        return FALSE;
    }
    DuplicateHandle( GetCurrentProcess(), GetCurrentProcess(), GetCurrentProcess(), &info->hProcess, 0, FALSE, DUPLICATE_SAME_ACCESS );
    info->hThread = thread;
    info->dwProcessId = GetCurrentProcessId();
    info->dwThreadId = tid;
    ERR( "PWGUEST relaunch_later app=%s module=%p thread %04lx\\n", debugstr_w(app_name), self->module, tid );
    return TRUE;
}

static BOOL ps4_guest_launch( const WCHAR *app_name, const WCHAR *cmd_line, DWORD flags, PROCESS_INFORMATION *info )
{''','Start a guest program again once its guest has gone (W210).')
revise('kernelbase','process','''    if (!(guest = RtlAllocateHeap( GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(*guest) ))) return FALSE;''','''    /* W210: a guest starting its own program again (Pale Moon's restart after rebuilding its startup
     * cache) would get that program's modules still loaded and initialised by itself */
    {
        struct ps4_guest *self = ps4_guest_current();
        LDR_DATA_TABLE_ENTRY *mod;

        if (self && self->module && self->ended && !LdrFindEntryForAddress( self->module, &mod ) &&
            mod->FullDllName.Buffer && !wcsicmp( mod->FullDllName.Buffer, app_name ))
            return ps4_guest_relaunch_later( self, app_name, cmd_line, flags, info );
    }
    if (!(guest = RtlAllocateHeap( GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(*guest) ))) return FALSE;''',
       'A guest starting its own program again (W210).')
revise('kernelbase','process','''    ps4_guest_note_modules( guest );  /* W208 */''','''    ps4_guest_note_modules( guest );  /* W208 */
    guest->ended = CreateEventW( NULL, TRUE, FALSE, NULL );  /* W210 */''','The end of a guest, as an event (W210).')
revise('kernelbase','process','''        ps4_guest_live_remove( guest );  /* W209 */''','''        ps4_guest_live_remove( guest );  /* W209 */
        if (guest->ended) SetEvent( guest->ended );  /* W210: a relaunch of its program may start */''',
       'Signal the end of a guest (W210).')
# W213: the pad's key profile (C:\orbis\padmaps\<exe>.ini, native/hw_pad.c) follows the guest. W181's
# profiles applied only to a program the title started on its own, never to a 64-bit guest such as
# The Lost Forest. A guest's start and end reach hw_pad.c through xinput's Unix library (call 3,
# unix_pad_profile, tools/build-xinput-hw.py); hw_pad.c keeps the active profile when a guest has
# none and clears a profile only when its own guest ends.
revise('kernelbase','process','#include "kernelbase.h"\n#include "ps4_guest.h"','''#include "kernelbase.h"
#include "ps4_guest.h"

/* W213: the pad's key profile follows the guest (tools/build-xinput-hw.py, native/hw_pad.c).
 * winecrt0's __wine_load_unix_lib/__wine_unix_call are not linked into kernelbase, so this does
 * what they do: load the library by name through NtQueryVirtualMemory, and call it through
 * ntdll's exported __wine_unix_call_dispatcher. */
struct ps4_pad_profile_params { char exe[260]; UINT32 load; };
static void ps4_guest_pad_profile( const WCHAR *path, BOOL load )
{
    static NTSTATUS (WINAPI *dispatcher)( UINT64, unsigned int, void * );
    static UINT64 handle;
    static LONG state;  /* 0 not tried, 1 ready, 2 no library */
    struct ps4_pad_profile_params params = {{0}};

    if (!state)
    {
        UNICODE_STRING name = RTL_CONSTANT_STRING( L"xinput1_3" );
        void **export = (void **)GetProcAddress( GetModuleHandleW( L"ntdll.dll" ), "__wine_unix_call_dispatcher" );
        UINT64 res[2];
        NTSTATUS status = NtQueryVirtualMemory( GetCurrentProcess(), &name, MemoryWineLoadUnixLibByName,
                                                res, sizeof(res), NULL );
        if (!status && export && *export) { handle = res[1]; dispatcher = *export; state = 1; }
        else { state = 2; OutputDebugStringA( "PWPAD no pad library for guest profiles\\n" ); }
    }
    if (state != 1 || !path) return;
    WideCharToMultiByte( CP_UTF8, 0, path, -1, params.exe, sizeof(params.exe) - 1, NULL, NULL );
    params.load = load;
    dispatcher( handle, 3 /* unix_pad_profile */, &params );
}''','The pad\'s key profile follows the guest (W213).')
revise('kernelbase','process','''    guest->entry = (char *)guest->module + nt->OptionalHeader.AddressOfEntryPoint;''','''    guest->entry = (char *)guest->module + nt->OptionalHeader.AddressOfEntryPoint;
    ps4_guest_pad_profile( app_name, TRUE );  /* W213 */''','A starting guest asks for its pad profile (W213).')
revise('kernelbase','process','''    ERR( "PS4 guest module %p exits status %lu\\n", guest->module, status );''','''    ERR( "PS4 guest module %p exits status %lu\\n", guest->module, status );
    {
        WCHAR path[MAX_PATH];  /* W213: its pad profile ends with it */
        if (GetModuleFileNameW( guest->module, path, ARRAY_SIZE(path) )) ps4_guest_pad_profile( path, FALSE );
    }''','An ending guest clears its pad profile (W213).')

# A second start of a running guest's program brings its window to the front (W217: SeaMonkey's
# second start ran over the first one's modules).
revise('kernelbase','process','''static BOOL ps4_guest_launch( const WCHAR *app_name, const WCHAR *cmd_line, DWORD flags, PROCESS_INFORMATION *info )
{''','''/* A program started while a guest of the same EXE runs (W217: SeaMonkey started twice; the second
 * ran over the first's modules): the running guest's window comes to the front instead */
static BOOL ps4_guest_show_running( struct ps4_guest *running, const WCHAR *app_name, PROCESS_INFORMATION *info )
{
    HMODULE user32 = GetModuleHandleW( L"user32.dll" );
    HWND (WINAPI *find)( HWND, HWND, const WCHAR *, const WCHAR * ) = (void *)GetProcAddress( user32, "FindWindowExW" );
    DWORD (WINAPI *owner)( HWND, DWORD * ) = (void *)GetProcAddress( user32, "GetWindowThreadProcessId" );
    BOOL (WINAPI *visible)( HWND ) = (void *)GetProcAddress( user32, "IsWindowVisible" );
    BOOL (WINAPI *iconic)( HWND ) = (void *)GetProcAddress( user32, "IsIconic" );
    BOOL (WINAPI *show)( HWND, int ) = (void *)GetProcAddress( user32, "ShowWindow" );
    BOOL (WINAPI *front)( HWND ) = (void *)GetProcAddress( user32, "SetForegroundWindow" );
    int (WINAPI *box)( HWND, const WCHAR *, const WCHAR *, UINT ) = (void *)GetProcAddress( user32, "MessageBoxW" );
    const WCHAR *name = wcsrchr( app_name, 0x5c );
    DWORD tids[ARRAY_SIZE(running->threads)];
    HWND hwnd, found = NULL;
    UINT i, count = 0;

    RtlEnterCriticalSection( &running->lock );
    for (i = 0; i < running->thread_count; i++) tids[count++] = GetThreadId( running->threads[i] );
    RtlLeaveCriticalSection( &running->lock );
    if (find && owner && visible)
        for (hwnd = find( 0, 0, NULL, NULL ); hwnd && !found; hwnd = find( 0, hwnd, NULL, NULL ))
        {
            DWORD tid;

            if (!visible( hwnd )) continue;
            tid = owner( hwnd, NULL );
            for (i = 0; i < count; i++) if (tids[i] == tid) { found = hwnd; break; }
        }
    ERR( "PWGUEST second_start app=%s module=%p window=%p threads=%u\\n", debugstr_w(app_name), running->module,
         found, count );
    if (found)
    {
        if (iconic && show && iconic( found )) show( found, 9 /* SW_RESTORE */ );
        if (front) front( found );
    }
#ifdef _WIN64
    else if (box)
        box( NULL, L"Este programa ya está abierto. Esperá a que aparezca su ventana, o cerralo antes de volver a abrirlo.",
             name ? name + 1 : app_name, 0x40 /* MB_ICONINFORMATION */ );
#else
    /* W236: in explorer's 32-bit world the box is explorer's (ps4_world_launch). In W235 a box on this
     * thread faulted, and it would wait on explorer's UI thread, which waits for this one */
    (void)box;
#endif
    DuplicateHandle( GetCurrentProcess(), GetCurrentProcess(), GetCurrentProcess(), &info->hProcess, 0, FALSE, DUPLICATE_SAME_ACCESS );
    info->hThread = NULL;
    info->dwProcessId = GetCurrentProcessId();
    info->dwThreadId = 0;
#ifndef _WIN64
    SetLastError( found ? 0 : ERROR_ALREADY_EXISTS );  /* W236: for the bridge (orbis32host.c) */
#endif
    return TRUE;
}

static BOOL ps4_guest_launch( const WCHAR *app_name, const WCHAR *cmd_line, DWORD flags, PROCESS_INFORMATION *info )
{''','A second start of a running guest program (W217).')
revise('kernelbase','process','''    if (!(guest = RtlAllocateHeap( GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(*guest) ))) return FALSE;''','''    /* a guest of the same program already runs, and this start is not its own (W210 above) */
    {
        struct ps4_guest *running = NULL, *self = ps4_guest_current();
        UINT i;

        RtlAcquireSRWLockShared( &ps4_live_lock );
        for (i = 0; i < ps4_live_count && !running; i++)
        {
            LDR_DATA_TABLE_ENTRY *mod;

            if (ps4_live_guests[i] != self && ps4_live_guests[i]->module &&
                !LdrFindEntryForAddress( ps4_live_guests[i]->module, &mod ) && mod->FullDllName.Buffer &&
                !wcsicmp( mod->FullDllName.Buffer, app_name )) running = ps4_live_guests[i];
        }
        RtlReleaseSRWLockShared( &ps4_live_lock );
        /* W246 (W244: Vice City's thread died of a stack overflow; the next start was refused as running):
         * a guest whose recorded threads have all ended is ended here, and this start goes on */
        if (running)
        {
            UINT count, live = 0;

            RtlEnterCriticalSection( &running->lock );
            count = running->thread_count;
            for (i = 0; i < count; i++)
                if (WaitForSingleObject( running->threads[i], 0 ) == WAIT_TIMEOUT) live++;
            RtlLeaveCriticalSection( &running->lock );
            if (count && !live)
            {
                ERR( "PWGUEST stale app=%s module=%p: its %u threads are gone; ended before this start\\n",
                     debugstr_w(app_name), running->module, count );
                ps4_guest_end( running, STATUS_UNSUCCESSFUL );
                running = NULL;
            }
        }
        /* W252 (W251: webview32's main thread never reached its exit; every next start was refused): a GUI
         * program whose guest shows no window is ended here, and this start goes on */
        if (running && subsystem == IMAGE_SUBSYSTEM_WINDOWS_GUI)
        {
            HMODULE user32 = GetModuleHandleW( L"user32.dll" );
            HWND (WINAPI *find)( HWND, HWND, const WCHAR *, const WCHAR * ) =
                user32 ? (void *)GetProcAddress( user32, "FindWindowExW" ) : NULL;
            DWORD (WINAPI *owner)( HWND, DWORD * ) = user32 ? (void *)GetProcAddress( user32, "GetWindowThreadProcessId" ) : NULL;
            BOOL (WINAPI *visible)( HWND ) = user32 ? (void *)GetProcAddress( user32, "IsWindowVisible" ) : NULL;
            DWORD tids[ARRAY_SIZE(running->threads)];
            UINT count = 0, j;
            HWND hwnd, found = NULL;

            RtlEnterCriticalSection( &running->lock );
            for (j = 0; j < running->thread_count; j++) tids[count++] = GetThreadId( running->threads[j] );
            RtlLeaveCriticalSection( &running->lock );
            if (find && owner && visible)
            {
                for (hwnd = find( 0, 0, NULL, NULL ); hwnd && !found; hwnd = find( 0, hwnd, NULL, NULL ))
                {
                    DWORD tid;

                    if (!visible( hwnd )) continue;
                    tid = owner( hwnd, NULL );
                    for (j = 0; j < count; j++) if (tids[j] == tid) { found = hwnd; break; }
                }
                if (!found)
                {
                    ERR( "PWGUEST stale app=%s module=%p: no visible window (%u threads); ended before this start\\n",
                         debugstr_w(app_name), running->module, count );
                    ps4_guest_end( running, STATUS_UNSUCCESSFUL );
                    running = NULL;
                }
            }
        }
        if (running)
        {
            if (allocated) FreeConsole();
            return ps4_guest_show_running( running, app_name, info );
        }
    }
    if (!(guest = RtlAllocateHeap( GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(*guest) ))) return FALSE;''',
       'A second start of a running guest program (W217).')

# W224: code a guest patches in a module of the Windows directory is written back when it ends
# (W222: mozglue's patch of ntdll's LdrLoadDll stayed after SeaMonkey, and explorer's next
# LoadLibrary jumped into unloaded mozglue).
revise('kernelbase','memory','''    if (!old_prot && (GetVersion() & 0x80000000)) old_prot = &prot;
    return set_ntstatus( NtProtectVirtualMemory( process, &addr, &size, new_prot, old_prot ));''','''    if (!old_prot && (GetVersion() & 0x80000000)) old_prot = &prot;
    if (ps4_guest_current()) ps4_guest_code_writable( process, addr, size, new_prot );  /* W224 */
    return set_ntstatus( NtProtectVirtualMemory( process, &addr, &size, new_prot, old_prot ));''',
       'A system page a guest makes writable is copied first (W224).')
revise('kernelbase','memory','''        status = NtWriteVirtualMemory( process, addr, buffer, size, bytes_written );''','''        if (ps4_guest_current()) ps4_guest_code_writable( process, addr, size, PAGE_EXECUTE_READWRITE );  /* W224 */
        status = NtWriteVirtualMemory( process, addr, buffer, size, bytes_written );''',
       'A system page a guest writes is copied first (W224).')
revise('kernelbase','process','''static void ps4_guest_unload( struct ps4_guest *guest )
{
    ps4_guest_close_files( guest );  /* W206 */''','''/* W224 (W222: mozglue patched ntdll's LdrLoadDll, "mov r11, hook; jmp r11", and the patch outlived
 * it; explorer's next LoadLibrary jumped into unloaded mozglue): a page of an image from the Windows
 * directory, in a section that is not writable, is copied before a guest thread makes it writable,
 * and written back when the guest ends, before its modules are unloaded. */
struct ps4_guest_patch
{
    char *page;
    void *module;
    BYTE bytes[0x1000];
};

static BOOL ps4_guest_system_code( char *page, LDR_DATA_TABLE_ENTRY **found )
{
    static WCHAR windows[MAX_PATH];
    static UINT windows_len;
    LDR_DATA_TABLE_ENTRY *mod;
    IMAGE_NT_HEADERS *nt;
    IMAGE_SECTION_HEADER *sec;
    ULONG_PTR rva;
    UINT i;

    if (!windows_len) windows_len = GetWindowsDirectoryW( windows, ARRAY_SIZE(windows) );
    if (!windows_len || windows_len >= ARRAY_SIZE(windows)) return FALSE;
    if (LdrFindEntryForAddress( page, &mod ) || !mod->FullDllName.Buffer) return FALSE;
    if (mod->FullDllName.Length / sizeof(WCHAR) <= windows_len ||
        wcsnicmp( mod->FullDllName.Buffer, windows, windows_len ) || mod->FullDllName.Buffer[windows_len] != 0x5c)
        return FALSE;
    if (!(nt = RtlImageNtHeader( mod->DllBase ))) return FALSE;
    rva = page - (char *)mod->DllBase;
    sec = IMAGE_FIRST_SECTION( nt );
    for (i = 0; i < nt->FileHeader.NumberOfSections; i++)
        if (rva - sec[i].VirtualAddress < max( sec[i].Misc.VirtualSize, sec[i].SizeOfRawData ))
        {
            if (sec[i].Characteristics & IMAGE_SCN_MEM_WRITE) return FALSE;  /* data: it changes */
            *found = mod;
            return TRUE;
        }
    return FALSE;
}

void ps4_guest_code_writable( HANDLE process, void *addr, SIZE_T size, DWORD prot )
{
    struct ps4_guest *guest = ps4_guest_current();
    char *page, *end;

    if (!guest || !addr || !size) return;
    if (!(prot & (PAGE_READWRITE | PAGE_WRITECOPY | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY))) return;
    if (process != GetCurrentProcess() && GetProcessId( process ) != GetCurrentProcessId()) return;
    end = (char *)addr + size;
    for (page = (char *)((ULONG_PTR)addr & ~(ULONG_PTR)0xfff); page < end; page += 0x1000)
    {
        LDR_DATA_TABLE_ENTRY *mod;
        struct ps4_guest_patch *patch;
        UINT i;

        if (!ps4_guest_system_code( page, &mod )) continue;
        RtlEnterCriticalSection( &guest->lock );
        for (i = 0; i < guest->patch_count; i++) if (guest->patches[i]->page == page) break;
        if (i == guest->patch_count)
        {
            if (guest->patch_count == ARRAY_SIZE(guest->patches) ||
                !(patch = RtlAllocateHeap( GetProcessHeap(), 0, sizeof(*patch) )))
                ERR( "PWGUEST patch_saved module=%p page=%p not copied (%u copies)\\n", guest->module, page, guest->patch_count );
            else
            {
                patch->page = page;
                patch->module = mod->DllBase;
                memcpy( patch->bytes, page, sizeof(patch->bytes) );
                guest->patches[guest->patch_count++] = patch;
                ERR( "PWGUEST patch_saved module=%p page=%p %s+%#lx prot=%#lx caller=%p\\n", guest->module, page,
                     debugstr_w(mod->BaseDllName.Buffer), (ULONG)(page - (char *)mod->DllBase), prot,
                     __builtin_return_address( 0 ) );
            }
        }
        RtlLeaveCriticalSection( &guest->lock );
    }
}

static void ps4_guest_unpatch( struct ps4_guest *guest )
{
    UINT i, restored = 0;

    RtlEnterCriticalSection( &guest->lock );
    for (i = 0; i < guest->patch_count; i++)
    {
        struct ps4_guest_patch *patch = guest->patches[i];
        LDR_DATA_TABLE_ENTRY *mod;
        NTSTATUS status = STATUS_SUCCESS;
        void *base = patch->page;
        SIZE_T size = sizeof(patch->bytes);
        ULONG old;

        /* a module unloaded meanwhile took its pages with it */
        if (!LdrFindEntryForAddress( patch->page, &mod ) && mod->DllBase == patch->module &&
            memcmp( patch->page, patch->bytes, sizeof(patch->bytes) ))
        {
            if (!(status = NtProtectVirtualMemory( GetCurrentProcess(), &base, &size, PAGE_EXECUTE_READWRITE, &old )))
            {
                memcpy( patch->page, patch->bytes, sizeof(patch->bytes) );
                base = patch->page;
                size = sizeof(patch->bytes);
                NtProtectVirtualMemory( GetCurrentProcess(), &base, &size, old, &old );
                NtFlushInstructionCache( GetCurrentProcess(), patch->page, sizeof(patch->bytes) );
                restored++;
            }
            ERR( "PWGUEST unpatch module=%p page=%p %s+%#lx status=%#lx\\n", guest->module, patch->page,
                 debugstr_w(mod->BaseDllName.Buffer), (ULONG)(patch->page - (char *)mod->DllBase), status );
        }
        RtlFreeHeap( GetProcessHeap(), 0, patch );
    }
    if (guest->patch_count)
        ERR( "PWGUEST unpatch module=%p copies=%u written_back=%u\\n", guest->module, guest->patch_count, restored );
    guest->patch_count = 0;
    RtlLeaveCriticalSection( &guest->lock );
}

static void ps4_guest_unload( struct ps4_guest *guest )
{
    ps4_guest_close_files( guest );  /* W206 */
    ps4_guest_unpatch( guest );      /* W224 */''','Write back the system code a guest patched (W224).')

# W225 (W224: mozglue's DLL load notification stayed registered after SeaMonkey, and explorer's
# next DLL load called it in unmapped memory): an unmapped DLL leaves no notification behind.
revise('ntdll','loader','''        if (handlers || fls)
            ERR( "PWGUEST unmap module=%p %s handlers=%lu fls=%u\\n", wm->ldr.DllBase,
                 debugstr_w( wm->ldr.BaseDllName.Buffer ), handlers, fls );
    }
''','''        if (handlers || fls)
            ERR( "PWGUEST unmap module=%p %s handlers=%lu fls=%u\\n", wm->ldr.DllBase,
                 debugstr_w( wm->ldr.BaseDllName.Buffer ), handlers, fls );
    }
    /* PS4 hardware build (W225): no DLL load notification is left in an unmapped image (W224: a
     * guest ends without DLL detach, and mozglue's notification was called after it was gone) */
    {
        struct ldr_notification *notify, *notify_next;

        LIST_FOR_EACH_ENTRY_SAFE( notify, notify_next, &ldr_notifications, struct ldr_notification, entry )
        {
            if ((ULONG_PTR)notify->callback - (ULONG_PTR)wm->ldr.DllBase >= wm->ldr.SizeOfImage) continue;
            ERR( "PWGUEST unmap module=%p %s ldr_notification=%p removed\\n", wm->ldr.DllBase,
                 debugstr_w( wm->ldr.BaseDllName.Buffer ), notify->callback );
            list_remove( &notify->entry );
            RtlFreeHeap( GetProcessHeap(), 0, notify );
        }
    }
''','DLL load notifications of an unmapped DLL (W225).')
# W225: a callback exception that finds no callback to return to goes on to the outer handlers
# (W222/W224: explorer's UI thread caught c0000258 again and again, forever).
revise('ntdll','exception','''    if (!(record->ExceptionFlags & (EXCEPTION_UNWINDING | EXCEPTION_EXIT_UNWIND)))
    {
        ERR( "ignoring exception %lx\\n", record->ExceptionCode );''','''    if (!(record->ExceptionFlags & (EXCEPTION_UNWINDING | EXCEPTION_EXIT_UNWIND)))
    {
        /* PS4 hardware build (W225): after an exception in a callback this handler unwinds to
         * KiUserCallbackDispatcherReturn; when NtCallbackReturn then finds no callback
         * (STATUS_NO_CALLBACK_ACTIVE), RtlRaiseStatus raised it here again and the thread looped
         * forever (W222/W224). It is not caught: the outer handlers get it, and without one the
         * exception is unhandled and the program ends with a trace. */
        if (record->ExceptionCode == STATUS_NO_CALLBACK_ACTIVE)
        {
            ERR( "PWCALLBACK no callback to return to at %p (frame %p); not caught, the outer handlers get it\\n",
                 record->ExceptionAddress, frame );
            return ExceptionContinueSearch;
        }
        ERR( "ignoring exception %lx at %p\\n", record->ExceptionCode, record->ExceptionAddress );''',
       'A callback exception with no callback to return to is not caught again (W225).')

# B1 (pe32-en-explorer-plan.md P3): 32-bit guests of explorer run as WoW64 threads of this 64-bit
# process beside its 64-bit threads (ntdll's Unix side: tools/build-wow64-world-ps4.py, which also keeps
# TlsFree in its own world). wow64.dll loads when the first of them starts; only those threads go
# through wow64.dll's exception preparation.
revise('ntdll','loader','''static void init_wow64( CONTEXT *context )
{
    if (!imports_fixup_done)
    {
        HMODULE wow64;''','''static void init_wow64( CONTEXT *context )
{
    /* PS4 hardware build (B1, pe32-en-explorer-plan.md P3): wow64.dll also loads after the process
     * started, when a 64-bit process (explorer) starts its first 32-bit thread */
    static BOOL wow64_loaded;

    if (!wow64_loaded)
    {
        HMODULE wow64;''','wow64.dll loads for the first 32-bit thread of a 64-bit process (B1).')
revise('ntdll','loader','''        build_wow64_main_module();
        build_ntdll_module();

        if ((status = load_dll( NULL, wow64_path, 0, &wm, FALSE )))
        {
            ERR( "could not load %s, status %lx\\n", debugstr_w(wow64_path), status );
            NtTerminateProcess( GetCurrentProcess(), status );
        }''','''        if (!imports_fixup_done)
        {
            build_wow64_main_module();
            build_ntdll_module();
        }
        else ERR( "PWWOW first 32-bit thread %04lx of this 64-bit process: loading wow64.dll\\n",
                  HandleToULong( NtCurrentTeb()->ClientId.UniqueThread ) );

        if ((status = load_dll( NULL, wow64_path, 0, &wm, FALSE )))
        {
            ERR( "could not load %s, status %lx\\n", debugstr_w(wow64_path), status );
            if (imports_fixup_done)  /* PS4 (B1): that 32-bit thread ends, not the process */
            {
                RtlLeaveCriticalSection( &loader_section );
                NtTerminateThread( GetCurrentThread(), status );
            }
            NtTerminateProcess( GetCurrentProcess(), status );
        }''','A late wow64.dll failure ends the 32-bit thread only (B1).')
revise('ntdll','loader','''#undef GET_PTR
        imports_fixup_done = TRUE;
    }
''','''#undef GET_PTR
        imports_fixup_done = TRUE;
        wow64_loaded = TRUE;
    }
''','wow64.dll is loaded once (B1).')
revise('ntdll','signal_x86_64','''                   "mov " __ASM_NAME("pWow64PrepareForException") "(%rip),%rax\\n\\t"
                   "test %rax,%rax\\n\\t"
                   "jz 1f\\n\\t"
                   "mov %rsp,%rdx\\n\\t"           /* context */''','''                   "mov " __ASM_NAME("pWow64PrepareForException") "(%rip),%rax\\n\\t"
                   "test %rax,%rax\\n\\t"
                   "jz 1f\\n\\t"
                   /* PS4 hardware build (B1): only a WoW64 thread; a 64-bit thread of a process with
                    * 32-bit guests has no 32-bit state to prepare (NtCurrentTeb()->WowTebOffset) */
                   "cmpl $0,%gs:0x180c\\n\\t"
                   "je 1f\\n\\t"
                   "mov %rsp,%rdx\\n\\t"           /* context */''',
       "The 64-bit threads' exceptions skip wow64.dll (B1).")
revise('ntdll','signal_x86_64','''                   "movq %gs:0x60,%rax\\n\\t"     /* peb */
                   "movq 0x58(%rax),%rax\\n\\t"   /* peb->KernelCallbackTable */
                   "call *(%rax,%r8,8)\\n\\t"     /* KernelCallbackTable[id] */''','''                   "movq %gs:0x60,%rax\\n\\t"     /* peb */
                   "movq 0x58(%rax),%rax\\n\\t"   /* peb->KernelCallbackTable */
                   /* PS4 hardware build (B1): in a 64-bit process with 32-bit guests the PEB's table is
                    * 64-bit user32's; a WoW64 thread has wow64win's in TlsSlots[18] (wow64.dll thread_init) */
                   "cmpl $0,%gs:0x180c\\n\\t"     /* NtCurrentTeb()->WowTebOffset */
                   "je 7f\\n\\t"
                   "movq %gs:0x1510,%r9\\n\\t"    /* NtCurrentTeb()->TlsSlots[18] */
                   "testq %r9,%r9\\n\\t"
                   "cmovnzq %r9,%rax\\n"
                   "7:\\tcall *(%rax,%r8,8)\\n\\t"  /* KernelCallbackTable[id] */''',
       "A WoW64 thread of a 64-bit process gets wow64win's callback table (B1).")

# W235 (pe32-en-explorer-plan.md P7): the bridge from explorer's 64-bit kernelbase to its 32-bit world.
revise('kernelbase','process','''/**********************************************************************
 *           CreateProcessInternalW   (kernelbase.@)
 */''','''#ifdef _WIN64
/* W235 (pe32-en-explorer-plan.md P7): a PE32 opened in explorer (desktop, Start menu, WFM) runs as a
 * guest of this process's 32-bit world. The world is created the first time (orbis32host.exe mapped
 * at its base, ntdll class PS4_PROCESS_WOW64_WORLD, tools/build-wow64-world-ps4.py); a WoW64 thread
 * runs the host's ps4_guest32_launch, which calls the 32-bit CreateProcessW: there the i386 guest
 * kernelbase (out/guest-hw-i386) loads and starts the program as 64-bit guests are started here. */
#define PS4_PROCESS_WOW64_WORLD 1100
#define PS4_THREAD_CREATE_WOW64 0x01000000
#define PS4_WORLD_HOST_BASE 0x30000000
#define PS4_WORLD_HOST L"C:\\\\windows\\\\syswow64\\\\orbis32host.exe"

struct ps4_world_request    /* ntdll Unix, struct pw_wow64_world_request */
{
    ULONG64 host_base;
    ULONG64 world_peb;
    WCHAR   image_path[260];
};

struct ps4_guest32_launch   /* fixtures/win32/orbis32host.c */
{
    DWORD flags;
    DWORD error;
    DWORD thread;
    DWORD thread_id;
    DWORD console;          /* W236: a console program's console and standard handles (copies), or 0 */
    DWORD std_input;
    DWORD std_output;
    DWORD std_error;
    WCHAR exe[MAX_PATH];
    WCHAR dir[MAX_PATH];
    WCHAR cmd[1];
};

/* W236: the subsystem of a PE32, 0 when unreadable */
static WORD ps4_pe32_subsystem( const WCHAR *path )
{
    IMAGE_DOS_HEADER dos;
    IMAGE_NT_HEADERS32 nt;
    DWORD read;
    WORD subsystem = 0;
    HANDLE file = CreateFileW( path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, NULL,
                               OPEN_EXISTING, 0, NULL );

    if (file == INVALID_HANDLE_VALUE) return 0;
    if (ReadFile( file, &dos, sizeof(dos), &read, NULL ) && read == sizeof(dos) && dos.e_magic == IMAGE_DOS_SIGNATURE &&
        SetFilePointer( file, dos.e_lfanew, NULL, FILE_BEGIN ) != INVALID_SET_FILE_POINTER &&
        ReadFile( file, &nt, sizeof(nt), &read, NULL ) && read == sizeof(nt) && nt.Signature == IMAGE_NT_SIGNATURE)
        subsystem = nt.OptionalHeader.Subsystem;
    CloseHandle( file );
    return subsystem;
}

/* W236 (W235: console32.exe asked the 32-bit side for conhost, which cannot be a guest there): the 32-bit
 * console programs on the console explorer gave them. The last one ending closes it, unless a 64-bit
 * console program still uses it (W062's rule) */
static LONG ps4_world_console_users;

static void ps4_world_console_release(void)
{
    struct ps4_guest *ended = NULL;

    RtlAcquireSRWLockExclusive( &console_lock );
    if (!InterlockedDecrement( &ps4_world_console_users ) && !console_count && console_host)
    {
        ended = console_host;
        console_host = NULL;
    }
    RtlReleaseSRWLockExclusive( &console_lock );
    ERR( "PWWOW bridge console program ended, the console %s\\n", ended ? "closes" : "stays" );
    if (ended) ps4_guest_end( ended, 0 );
}

static DWORD WINAPI ps4_world_console_watch( void *thread )
{
    WaitForSingleObject( thread, INFINITE );
    CloseHandle( thread );
    ps4_world_console_release();
    return 0;
}

/* W236: the wait for the 32-bit start delivers the messages sent to this thread (explorer's UI thread):
 * a 32-bit start that sends to explorer's windows (activation, a box) would otherwise wait on it */
static DWORD ps4_world_wait( HANDLE thread, DWORD timeout )
{
    HMODULE user32 = GetModuleHandleW( L"user32.dll" );
    DWORD (WINAPI *msg_wait)( DWORD, const HANDLE *, BOOL, DWORD, DWORD ) =
        user32 ? (void *)GetProcAddress( user32, "MsgWaitForMultipleObjects" ) : NULL;
    BOOL (WINAPI *peek)( void *, HWND, UINT, UINT, UINT ) = user32 ? (void *)GetProcAddress( user32, "PeekMessageW" ) : NULL;
    DWORD start = GetTickCount(), elapsed, wait;
    ULONG_PTR msg[8];  /* MSG */

    if (!msg_wait || !peek) return WaitForSingleObject( thread, timeout );
    for (;;)
    {
        if ((elapsed = GetTickCount() - start) >= timeout) return WAIT_TIMEOUT;
        wait = msg_wait( 1, &thread, FALSE, timeout - elapsed, 0x0040 /* QS_SENDMESSAGE */ );
        if (wait != WAIT_OBJECT_0 + 1) return wait;
        peek( msg, 0, 0, 0, 0x00400000 /* PM_NOREMOVE | PM_QS_SENDMESSAGE */ );
    }
}

/* the relaunch for every PE32, as before W235, while C:\\\\orbis\\\\pe32relaunch.txt exists */
static BOOL ps4_pe32_relaunch_forced(void)
{
    return GetFileAttributesW( L"C:\\\\orbis\\\\pe32relaunch.txt" ) != INVALID_FILE_ATTRIBUTES;
}

static ULONG_PTR ps4_world_export( ULONG_PTR base, const char *name )
{
    const IMAGE_NT_HEADERS32 *nt = (const IMAGE_NT_HEADERS32 *)(base + ((const IMAGE_DOS_HEADER *)base)->e_lfanew);
    const IMAGE_DATA_DIRECTORY *dir = &nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXPORT];
    const IMAGE_EXPORT_DIRECTORY *exports;
    const DWORD *names, *functions;
    const WORD *ordinals;
    DWORD i;

    if (!dir->VirtualAddress) return 0;
    exports = (const IMAGE_EXPORT_DIRECTORY *)(base + dir->VirtualAddress);
    names = (const DWORD *)(base + exports->AddressOfNames);
    ordinals = (const WORD *)(base + exports->AddressOfNameOrdinals);
    functions = (const DWORD *)(base + exports->AddressOfFunctions);
    for (i = 0; i < exports->NumberOfNames; i++)
        if (!strcmp( (const char *)(base + names[i]), name )) return base + functions[ordinals[i]];
    return 0;
}

/* the 32-bit world's host, created the first time (or found: C:\\\\orbis\\\\wow64world64.exe makes it too) */
static ULONG_PTR ps4_world_host( DWORD *error )
{
    static RTL_SRWLOCK lock = RTL_SRWLOCK_INIT;
    static ULONG_PTR host;
    struct ps4_world_request req;
    HANDLE file, section;
    void *base = NULL;
    SIZE_T size = 0;
    NTSTATUS status;

    RtlAcquireSRWLockExclusive( &lock );
    if (host) goto done;
    memset( &req, 0, sizeof(req) );
    status = NtSetInformationProcess( GetCurrentProcess(), PS4_PROCESS_WOW64_WORLD, &req, sizeof(req) );
    if (!status)
    {
        host = *(const ULONG *)(ULONG_PTR)(req.world_peb + 8);  /* PEB32.ImageBaseAddress */
        ERR( "PWWOW bridge world existing peb32=%I64x host=%Ix\\n", req.world_peb, host );
        goto done;
    }
    if (status != STATUS_NOT_FOUND)
    {
        ERR( "PWWOW bridge world_unsupported status=%#lx\\n", status );
        *error = RtlNtStatusToDosError( status );
        goto done;
    }
    file = CreateFileW( PS4_WORLD_HOST, GENERIC_READ | GENERIC_EXECUTE, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL );
    if (file == INVALID_HANDLE_VALUE)
    {
        *error = GetLastError();
        ERR( "PWWOW bridge host_missing error=%lu\\n", *error );
        goto done;
    }
    status = NtCreateSection( &section, SECTION_MAP_READ | SECTION_MAP_EXECUTE | SECTION_QUERY, NULL, NULL,
                              PAGE_EXECUTE_READ, SEC_IMAGE, file );
    CloseHandle( file );
    if (status)
    {
        ERR( "PWWOW bridge host_section status=%#lx\\n", status );
        *error = RtlNtStatusToDosError( status );
        goto done;
    }
    status = NtMapViewOfSection( section, GetCurrentProcess(), &base, 0, 0, NULL, &size, ViewShare, 0,
                                 PAGE_EXECUTE_READ );
    CloseHandle( section );
    /* W234: an i386 image maps in this AMD64 process with STATUS_IMAGE_MACHINE_TYPE_MISMATCH (informational) */
    if (NT_ERROR( status ) || (ULONG_PTR)base != PS4_WORLD_HOST_BASE)
    {
        ERR( "PWWOW bridge host_not_mapped status=%#lx base=%p\\n", status, base );
        if (!NT_ERROR( status )) NtUnmapViewOfSection( GetCurrentProcess(), base );
        *error = NT_ERROR( status ) ? RtlNtStatusToDosError( status ) : ERROR_INVALID_ADDRESS;
        goto done;
    }
    req.host_base = (ULONG_PTR)base;
    lstrcpyW( req.image_path, PS4_WORLD_HOST );
    status = NtSetInformationProcess( GetCurrentProcess(), PS4_PROCESS_WOW64_WORLD, &req, sizeof(req) );
    ERR( "PWWOW bridge world created status=%#lx peb32=%I64x\\n", status, req.world_peb );
    if (status)
    {
        NtUnmapViewOfSection( GetCurrentProcess(), base );
        *error = RtlNtStatusToDosError( status );
        goto done;
    }
    host = (ULONG_PTR)base;
done:
    RtlReleaseSRWLockExclusive( &lock );
    return host;
}

/* a PE32 as a guest of the 32-bit world; 0 or why not. info as for a 64-bit guest: a handle to this
 * process and the guest's first thread */
static DWORD ps4_world_launch( const WCHAR *app_name, const WCHAR *cmd_line, const WCHAR *cur_dir, DWORD flags,
                               PROCESS_INFORMATION *info )
{
    struct ps4_guest32_launch *req = NULL;
    ULONG_PTR host, entry;
    const WCHAR *slash;
    HANDLE thread;
    SIZE_T size;
    DWORD error = 0, wait, exit_code = 0;
    UINT cmd_len = lstrlenW( cmd_line );
    NTSTATUS status;

    if (lstrlenW( app_name ) >= MAX_PATH || (cur_dir && lstrlenW( cur_dir ) >= MAX_PATH)) return ERROR_FILENAME_EXCED_RANGE;
    if (!(host = ps4_world_host( &error ))) return error ? error : ERROR_NOT_SUPPORTED;
    if (!(entry = ps4_world_export( host, "ps4_guest32_launch" )))
    {
        ERR( "PWWOW bridge no ps4_guest32_launch in the host\\n" );
        return ERROR_PROC_NOT_FOUND;
    }
    size = FIELD_OFFSET( struct ps4_guest32_launch, cmd ) + (cmd_len + 1) * sizeof(WCHAR);
    if ((status = NtAllocateVirtualMemory( GetCurrentProcess(), (void **)&req, 0x7fffffff, &size,
                                           MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE )))
        return RtlNtStatusToDosError( status );
    req->flags = flags;
    lstrcpyW( req->exe, app_name );
    if (cur_dir) lstrcpyW( req->dir, cur_dir );
    else if ((slash = wcsrchr( app_name, 0x5c )))  /* its folder, as the relaunch starts it (W129) */
    {
        UINT len = slash - app_name + (slash - app_name == 2);  /* C:\\\\ keeps its backslash */
        memcpy( req->dir, app_name, len * sizeof(WCHAR) );
        req->dir[len] = 0;
    }
    memcpy( req->cmd, cmd_line, (cmd_len + 1) * sizeof(WCHAR) );
    /* W236 (W235: console32.exe asked the 32-bit side for conhost.exe, "not_a_guest", and relaunched): a
     * console program gets its console here, as a 64-bit guest does (AllocConsole starts conhost as a
     * 64-bit guest), and the 32-bit world copies of its handles (orbis32host.c puts them in the PEB32) */
    if (ps4_pe32_subsystem( app_name ) == IMAGE_SUBSYSTEM_WINDOWS_CUI && !(flags & (DETACHED_PROCESS | CREATE_NO_WINDOW)))
    {
        RTL_USER_PROCESS_PARAMETERS *params = NtCurrentTeb()->Peb->ProcessParameters;
        HANDLE handles[4], copy;
        DWORD *copies[4] = { &req->console, &req->std_input, &req->std_output, &req->std_error };
        UINT i;

        if (!params->ConsoleHandle && !AllocConsole())
            ERR( "PWWOW bridge console32 no console, error %lu\\n", GetLastError() );
        else
        {
            SetConsoleTitleW( (slash = wcsrchr( app_name, 0x5c )) ? slash + 1 : app_name );
            handles[0] = params->ConsoleHandle;
            handles[1] = params->hStdInput;
            handles[2] = params->hStdOutput;
            handles[3] = params->hStdError;
            for (i = 0; i < 4; i++)
                if (handles[i] && DuplicateHandle( GetCurrentProcess(), handles[i], GetCurrentProcess(), &copy, 0, FALSE,
                                                   DUPLICATE_SAME_ACCESS ))
                    *copies[i] = HandleToULong( copy );
            if (req->console) InterlockedIncrement( &ps4_world_console_users );
            ERR( "PWWOW bridge console32 console=%#lx out=%#lx\\n", req->console, req->std_output );
        }
    }
    status = NtCreateThreadEx( &thread, THREAD_ALL_ACCESS, NULL, GetCurrentProcess(), (void *)entry, req,
                               PS4_THREAD_CREATE_WOW64, 0, 0, 0x200000, NULL );
    if (status)
    {
        ERR( "PWWOW bridge thread status=%#lx image=%s\\n", status, debugstr_w(app_name) );
        if (req->console) ps4_world_console_release();
        size = 0;
        NtFreeVirtualMemory( GetCurrentProcess(), (void **)&req, &size, MEM_RELEASE );
        return RtlNtStatusToDosError( status );
    }
    /* as a 64-bit guest, the program loads on the caller's thread's watch: only the start waits.
     * W236: delivering the messages sent to this thread meanwhile */
    wait = ps4_world_wait( thread, 120000 );
    GetExitCodeThread( thread, &exit_code );
    CloseHandle( thread );
    ERR( "PWWOW bridge launch image=%s wait=%lu exit=%lu error=%lu guest_thread=%04lx tick=%lu\\n",
         debugstr_w(app_name), wait, exit_code, req->error, req->thread_id, GetTickCount() );  /* W248: tick */
    if (wait != WAIT_OBJECT_0) return ERROR_TIMEOUT;  /* the request stays: its thread may still use it */
    if (exit_code) error = req->error ? req->error : exit_code;
    else
    {
        DuplicateHandle( GetCurrentProcess(), GetCurrentProcess(), GetCurrentProcess(), &info->hProcess, 0, FALSE,
                         DUPLICATE_SAME_ACCESS );
        info->hThread = req->thread ? ULongToHandle( req->thread ) : NULL;
        info->dwProcessId = GetCurrentProcessId();
        info->dwThreadId = req->thread_id;
        /* W236: no thread is a second start of a running program (W217, W235 took it for a failure); the
         * 32-bit side brought its window to the front, or found none */
        if (!req->thread)
        {
            int (WINAPI *box)( HWND, const WCHAR *, const WCHAR *, UINT ) =
                (void *)GetProcAddress( GetModuleHandleW( L"user32.dll" ), "MessageBoxW" );

            ERR( "PWWOW bridge second_start image=%s window_found=%u\\n", debugstr_w(app_name),
                 req->error != ERROR_ALREADY_EXISTS );
            if (req->error == ERROR_ALREADY_EXISTS && box)
                box( NULL, L"Este programa ya está abierto. Esperá a que aparezca su ventana, o cerralo antes de volver a abrirlo.",
                     (slash = wcsrchr( app_name, 0x5c )) ? slash + 1 : app_name, 0x40 /* MB_ICONINFORMATION */ );
        }
    }
    if (req->console)
    {
        HANDLE watched, watcher = NULL;

        if (error)  /* the 32-bit side let go of them (orbis32host.c) */
        {
            CloseHandle( ULongToHandle( req->console ) );
            if (req->std_input) CloseHandle( ULongToHandle( req->std_input ) );
            if (req->std_output) CloseHandle( ULongToHandle( req->std_output ) );
            if (req->std_error) CloseHandle( ULongToHandle( req->std_error ) );
        }
        if (!error && req->thread &&
            DuplicateHandle( GetCurrentProcess(), ULongToHandle( req->thread ), GetCurrentProcess(), &watched,
                             SYNCHRONIZE, FALSE, 0 ))
        {
            if (!(watcher = CreateThread( NULL, 0, ps4_world_console_watch, watched, 0, NULL ))) CloseHandle( watched );
        }
        if (watcher) CloseHandle( watcher );
        else ps4_world_console_release();
    }
    size = 0;
    NtFreeVirtualMemory( GetCurrentProcess(), (void **)&req, &size, MEM_RELEASE );
    return error;
}
#endif

/**********************************************************************
 *           CreateProcessInternalW   (kernelbase.@)
 */''','The bridge from explorer to its 32-bit world (W235).')

# W236 (W235: gui-window32's thread 0068 logged nothing): the i386 loader's steps for a new 32-bit thread of
# explorer's 32-bit world (this i386 ntdll loads only there).
revise('ntdll','loader','''        if ((status = alloc_thread_tls()) != STATUS_SUCCESS)
            NtTerminateThread( GetCurrentThread(), status );
        thread_attach();
''','''#ifndef _WIN64
        ERR( "PWWOW guest32 thread %04lx loader_init: tls\\n", HandleToULong( NtCurrentTeb()->ClientId.UniqueThread ) );
#endif
        if ((status = alloc_thread_tls()) != STATUS_SUCCESS)
            NtTerminateThread( GetCurrentThread(), status );
        thread_attach();
#ifndef _WIN64
        ERR( "PWWOW guest32 thread %04lx loader_init: attached\\n", HandleToULong( NtCurrentTeb()->ClientId.UniqueThread ) );
#endif
''','The steps of a new 32-bit thread (W236).')
revise('ntdll','loader','''        if ( mod->Flags & LDR_NO_DLL_CALLS )
            continue;

        MODULE_InitDLL( CONTAINING_RECORD(mod, WINE_MODREF, ldr), DLL_THREAD_ATTACH, NULL );''','''        if ( mod->Flags & LDR_NO_DLL_CALLS )
            continue;

#if !defined(_WIN64) && defined(ORBIS_RELEASE) && !ORBIS_RELEASE
        /* alpha-1: a line per DLL for every new 32-bit thread; only in a -DORBIS_RELEASE=0 build (pw_trace.h) */
        ERR( "PWWOW guest32 thread %04lx thread_attach %s\\n", HandleToULong( NtCurrentTeb()->ClientId.UniqueThread ),
             debugstr_w( mod->BaseDllName.Buffer ) );  /* W236 */
#endif
        MODULE_InitDLL( CONTAINING_RECORD(mod, WINE_MODREF, ldr), DLL_THREAD_ATTACH, NULL );''',
       'The steps of a new 32-bit thread (W236).')

# W236: the control overlay's Salir (native/hw_overlay.c, L3+R3 on the pad) closes the program in front.
# The pad thread sends F24, which a thread of this kernelbase registers as a hotkey: the server posts
# WM_HOTKEY to it and the program in front never gets the key. The guest owning the foreground window
# ends as TerminateProcess would end a process. A 32-bit guest belongs to the i386 kernelbase of
# explorer's 32-bit world (W235); its closer waits on an event that the 64-bit closer sets.
revise('kernelbase','process','''static BOOL ps4_guest_launch( const WCHAR *app_name, const WCHAR *cmd_line, DWORD flags, PROCESS_INFORMATION *info )
{''','''/* W236: the control overlay's Salir (native/hw_overlay.c) */
#define PS4_OVERLAY_HOTKEY 0x4f57
#define PS4_OVERLAY_EVENT32 L"PwOverlayClose32"
#define PS4_OVERLAY_HOTKEY_HUD 0x4f58
#define PS4_OVERLAY_HUD32 L"PwOverlayHud32"  /* W245: set while the 32-bit world has libMangoHud.dll */

#ifdef _WIN64
/* W239: the overlay's requests and results, through xinput's Unix library like the pad profiles (call 3,
 * unix_pad_profile); native/hw_pad.c answers "<overlay-poll>" in the same buffer */
static BOOL ps4_overlay_call( const char *what, char *reply, UINT size )
{
    static NTSTATUS (WINAPI *dispatcher)( UINT64, unsigned int, void * );
    static UINT64 handle;
    static LONG state;  /* 0 not tried, 1 ready, 2 no library */
    struct ps4_pad_profile_params params = {{0}};

    if (!state)
    {
        UNICODE_STRING name = RTL_CONSTANT_STRING( L"xinput1_3" );
        void **export = (void **)GetProcAddress( GetModuleHandleW( L"ntdll.dll" ), "__wine_unix_call_dispatcher" );
        UINT64 res[2];
        NTSTATUS status = NtQueryVirtualMemory( GetCurrentProcess(), &name, MemoryWineLoadUnixLibByName,
                                                res, sizeof(res), NULL );
        if (!status && export && *export) { handle = res[1]; dispatcher = *export; state = 1; }
        else { state = 2; ERR( "PWOVERLAY closer: no pad library, status %#lx: Salir not available\\n", status ); }
    }
    if (state != 1) return FALSE;
    lstrcpynA( params.exe, what, sizeof(params.exe) );
    if (dispatcher( handle, 3 /* unix_pad_profile */, &params )) return FALSE;
    if (reply) lstrcpynA( reply, params.exe, size );
    return TRUE;
}
#endif

/* W238: whether MangoHud's layer (W086, 64-bit Vulkan and Zink programs) is loaded in this process;
 * hw_pad.c hears of each change through the pad profile call ("<mangohud>", not a file name). The
 * loader lock is only tried: a guest stopped inside the loader must not stop this thread (Salir). */
static int ps4_overlay_mangohud_loaded(void)
{
    LIST_ENTRY *list = &NtCurrentTeb()->Peb->LdrData->InLoadOrderModuleList, *entry;
    ULONG lock_state = 0;
    ULONG_PTR magic;
    int loaded = 0;

    if (LdrLockLoaderLock( 2 /* LDR_LOCK_LOADER_LOCK_FLAG_TRY_ONLY */, &lock_state, &magic ) || lock_state != 1)
        return -1;  /* busy: the next second */
    for (entry = list->Flink; entry != list && !loaded; entry = entry->Flink)
    {
        LDR_DATA_TABLE_ENTRY *mod = CONTAINING_RECORD( entry, LDR_DATA_TABLE_ENTRY, InLoadOrderLinks );

        if (mod->BaseDllName.Buffer && mod->BaseDllName.Length == 15 * sizeof(WCHAR) &&
            !wcsnicmp( mod->BaseDllName.Buffer, L"libMangoHud.dll", 15 )) loaded = 1;
    }
    LdrUnlockLoaderLock( 0, magic );
    return loaded;
}

/* the running guest one of whose threads is tid */
static struct ps4_guest *ps4_overlay_guest_of( DWORD tid )
{
    struct ps4_guest *found = NULL;
    UINT i, j;

    RtlAcquireSRWLockShared( &ps4_live_lock );
    for (i = 0; i < ps4_live_count && !found; i++)
    {
        struct ps4_guest *guest = ps4_live_guests[i];

        RtlEnterCriticalSection( &guest->lock );
        for (j = 0; j < guest->thread_count; j++)
            if (GetThreadId( guest->threads[j] ) == tid) found = guest;
        RtlLeaveCriticalSection( &guest->lock );
    }
    RtlReleaseSRWLockShared( &ps4_live_lock );
    return found;
}

/* end a guest from the closer thread as a terminated process ends: its threads are terminated
 * outside the loader (the loader lock is held meanwhile, as in ps4_guest_exit_process), their
 * windows go with them, then it is unloaded without DllMain(DETACH) (W209). A thread that does not
 * end within 2 s (one that never calls into Wine) keeps the guest loaded, logged. */
/* W248 (W246: after Vice City's Salir explorer had no active or focus window): the taskbar comes to the front,
 * so the keyboard and the pad have a window again */
static void ps4_overlay_tray_front(void)
{
    HMODULE user32 = GetModuleHandleW( L"user32.dll" );
    HWND (WINAPI *find)( const WCHAR *, const WCHAR * ) = user32 ? (void *)GetProcAddress( user32, "FindWindowW" ) : NULL;
    BOOL (WINAPI *front)( HWND ) = user32 ? (void *)GetProcAddress( user32, "SetForegroundWindow" ) : NULL;
    HWND tray = find ? find( L"Shell_TrayWnd", NULL ) : NULL;
    BOOL done = tray && front && front( tray );

    ERR( "PWOVERLAY foreground after close tray=%p set=%u\\n", tray, done );
}

static const char *ps4_overlay_close_guest( struct ps4_guest *guest )
{
    HANDLE threads[ARRAY_SIZE(guest->threads)];
    HMODULE module = guest->module;
    ULONG_PTR loader_magic = 0;
    ULONG lock_state = 0;
    DWORD wait = WAIT_OBJECT_0;
    WCHAR path[MAX_PATH];
    UINT i, count;
    int tries;

    if (guest->console || guest->console_host)
    {
        ERR( "PWOVERLAY close module=%p refused: a console program ends with its console\\n", module );
        return "refused-console";
    }
    if (!GetModuleFileNameW( module, path, ARRAY_SIZE(path) )) path[0] = 0;
    /* W239: the target, before anything is ended */
    ERR( "PWOVERLAY terminate module=%p path=%s threads=%u\\n", module, debugstr_w(path), guest->thread_count );
    if (path[0]) ps4_guest_pad_profile( path, FALSE );
    for (tries = 0; tries < 200; tries++)
    {
        if (!LdrLockLoaderLock( 2 /* LDR_LOCK_LOADER_LOCK_FLAG_TRY_ONLY */, &lock_state, &loader_magic ) &&
            lock_state == 1) break;
        if (!((RTL_CRITICAL_SECTION *)NtCurrentTeb()->Peb->LoaderLock)->OwningThread &&
            !LdrLockLoaderLock( 0, NULL, &loader_magic ))
        {
            lock_state = 1;
            break;
        }
        Sleep( 10 );
    }
    guest->terminated = TRUE;
    RtlEnterCriticalSection( &guest->lock );
    count = guest->thread_count;
    memcpy( threads, guest->threads, count * sizeof(*threads) );
    RtlLeaveCriticalSection( &guest->lock );
    for (i = 0; i < count; i++) TerminateThread( threads[i], 1 );
    for (i = 0; i < count && wait == WAIT_OBJECT_0; i += 64)
        wait = WaitForMultipleObjects( count - i < 64 ? count - i : 64, threads + i, TRUE, 2000 );
    if (lock_state == 1) LdrUnlockLoaderLock( 0, loader_magic );
    ERR( "PWOVERLAY close module=%p threads=%u wait=%lu loader_lock=%lu tries=%d\\n", module, count, wait,
         lock_state, tries );
    if (wait != WAIT_OBJECT_0)
    {
        ERR( "PWOVERLAY close module=%p kept loaded: a thread did not end\\n", module );
        return "kept";
    }
    ps4_guest_unload( guest );
    ps4_overlay_tray_front();
    ERR( "PWOVERLAY closed module=%p\\n", module );
    return "closed";
}

/* W256 (W253: Vice City's Salir terminated its thread inside DXVK's and MangoHud's swapchain teardown): the window
 * is asked to close first, as its close button does; the guest has 3 s to end by itself (its own teardown, then
 * ExitProcess's unload) before its threads are terminated. TRUE when it ended. */
static BOOL ps4_overlay_ask_close( HWND hwnd, DWORD tid )
{
    HMODULE user32 = GetModuleHandleW( L"user32.dll" );
    BOOL (WINAPI *post)( HWND, UINT, WPARAM, LPARAM ) = user32 ? (void *)GetProcAddress( user32, "PostMessageW" ) : NULL;
    UINT waited;

    if (!post || !post( hwnd, 0x0010 /* WM_CLOSE */, 0, 0 ))
    {
        ERR( "PWOVERLAY close window=%p: WM_CLOSE not posted, error %lu\\n", hwnd, GetLastError() );
        return FALSE;
    }
    for (waited = 100; waited <= 3000; waited += 100)
    {
        Sleep( 100 );
        if (!ps4_overlay_guest_of( tid ))
        {
            ERR( "PWOVERLAY close window=%p ended by itself after WM_CLOSE in %u ms\\n", hwnd, waited );
            return TRUE;
        }
    }
    ERR( "PWOVERLAY close window=%p still running 3000 ms after WM_CLOSE: its threads are terminated\\n", hwnd );
    return FALSE;
}

/* W261: the desktop or the taskbar (Salir refuses it; Estadisticas does not turn the overlay's readout on) */
static BOOL ps4_overlay_is_desktop( HWND hwnd, const WCHAR *class )
{
    HMODULE user32 = GetModuleHandleW( L"user32.dll" );
    HWND (WINAPI *desktop)( void ) = user32 ? (void *)GetProcAddress( user32, "GetDesktopWindow" ) : NULL;
    HWND (WINAPI *shell)( void ) = user32 ? (void *)GetProcAddress( user32, "GetShellWindow" ) : NULL;

    return (desktop && hwnd == desktop()) || (shell && hwnd == shell()) || !wcsicmp( class, L"#32769" ) ||
           !wcsicmp( class, L"Progman" ) || !wcsicmp( class, L"WorkerW" ) || !wcsicmp( class, L"Shell_TrayWnd" );
}

/* W239: the target is logged before anything; the desktop and an empty foreground are refused */
static const char *ps4_overlay_close_foreground( HANDLE event32 )
{
    HMODULE user32 = GetModuleHandleW( L"user32.dll" );
    HWND (WINAPI *front)( void ) = user32 ? (void *)GetProcAddress( user32, "GetForegroundWindow" ) : NULL;
    DWORD (WINAPI *owner)( HWND, DWORD * ) = user32 ? (void *)GetProcAddress( user32, "GetWindowThreadProcessId" ) : NULL;
    int (WINAPI *class_of)( HWND, WCHAR *, int ) = user32 ? (void *)GetProcAddress( user32, "GetClassNameW" ) : NULL;
    HWND hwnd = front ? front() : NULL;
    DWORD tid = hwnd && owner ? owner( hwnd, NULL ) : 0;
    struct ps4_guest *guest;
    WCHAR class[64] = {0};

    if (hwnd && class_of) class_of( hwnd, class, ARRAY_SIZE(class) );
    ERR( "PWOVERLAY exit target window=%p thread=%04lx class=%s\\n", hwnd, tid, debugstr_w(class) );
    if (!hwnd || !tid)
    {
        ERR( "PWOVERLAY exit refused: no window in front\\n" );
        return "refused-none";
    }
    if (ps4_overlay_is_desktop( hwnd, class ))
    {
        ERR( "PWOVERLAY exit refused: the desktop or the taskbar is in front\\n" );
        return "refused-desktop";
    }
    if ((guest = ps4_overlay_guest_of( tid )))
    {
        ERR( "PWOVERLAY close window=%p thread=%04lx module=%p\\n", hwnd, tid, guest->module );
        /* W256: WM_CLOSE first; the guest is looked up again, it may have ended meanwhile */
        if (ps4_overlay_ask_close( hwnd, tid ) || !(guest = ps4_overlay_guest_of( tid )))
        {
            ps4_overlay_tray_front();
            return "closed";
        }
        return ps4_overlay_close_guest( guest );
    }
    if (event32)
    {
        ERR( "PWOVERLAY close window=%p thread=%04lx: not a 64-bit guest's, the 32-bit world is asked\\n", hwnd, tid );
        SetEvent( event32 );
        return "asked32";
    }
    ERR( "PWOVERLAY close window=%p thread=%04lx: no guest owns it, nothing closed\\n", hwnd, tid );
    return "refused-none";
}

#ifdef _WIN64
/* W242: MangoHud counts for the program in front only (W240: one 64-bit program loaded it, and the
 * 32-bit ones opened later got "MANGOHUD" with no HUD; there is no i386 MangoHud): libMangoHud.dll
 * loaded, the foreground window a 64-bit guest's, and one of the windows a Vulkan swapchain presented to
 * in the last 2 s (the poll's reply after its first word, in hex) that window or a child of it */
static void ps4_overlay_report_hud( const char *reply )
{
    static int reported = -1;
    HMODULE user32 = GetModuleHandleW( L"user32.dll" );
    HWND (WINAPI *front)( void ) = user32 ? (void *)GetProcAddress( user32, "GetForegroundWindow" ) : NULL;
    HWND (WINAPI *ancestor)( HWND, UINT ) = user32 ? (void *)GetProcAddress( user32, "GetAncestor" ) : NULL;
    DWORD (WINAPI *owner)( HWND, DWORD * ) = user32 ? (void *)GetProcAddress( user32, "GetWindowThreadProcessId" ) : NULL;
    HWND hwnd = front ? front() : NULL, presented = NULL;
    const char *at = reply;
    int loaded = ps4_overlay_mangohud_loaded(), guest64 = 0, loaded32, hud;
    static HANDLE hud32;

    if (loaded < 0) return;
    /* W245: the 32-bit world's closer keeps this set while libMangoHud.dll (i386) is loaded there */
    if (!hud32) hud32 = CreateEventW( NULL, TRUE, FALSE, PS4_OVERLAY_HUD32 );
    loaded32 = hud32 && !WaitForSingleObject( hud32, 0 );
    while (*at && *at != ' ') at++;
    while (hwnd && *at == ' ' && !presented)
    {
        ULONG_PTR value = 0;

        while (*at == ' ') at++;
        for (; (*at >= '0' && *at <= '9') || (*at >= 'a' && *at <= 'f'); at++)
            value = value * 16 + (*at <= '9' ? *at - '0' : *at - 'a' + 10);
        if (value && ((HWND)value == hwnd || (ancestor && ancestor( (HWND)value, 2 /* GA_ROOT */ ) == hwnd)))
            presented = (HWND)value;
    }
    if (presented && owner) guest64 = ps4_overlay_guest_of( owner( hwnd, NULL ) ) != NULL;
    /* W245: a window in front that is not a 64-bit guest's and that Vulkan presents to is a 32-bit guest's:
     * explorer's own windows do not present */
    hud = presented && (guest64 ? loaded : loaded32);
    if (hud == reported) return;
    reported = hud;
    ERR( "PWOVERLAY mangohud in_front=%d window=%p presented=%p guest64=%d loaded=%d loaded32=%d\\n", hud, hwnd,
         presented, guest64, loaded, loaded32 );
    ps4_guest_pad_profile( L"<mangohud>", hud );
}

/* W261: whether the desktop, the taskbar or no window is in front, as Salir refuses them; native/hw_overlay.c hears
 * of each change ("<overlay-desktop>") and Estadisticas does not turn its own readout on meanwhile */
static void ps4_overlay_report_desktop(void)
{
    static int reported = -1;
    HMODULE user32 = GetModuleHandleW( L"user32.dll" );
    HWND (WINAPI *front)( void ) = user32 ? (void *)GetProcAddress( user32, "GetForegroundWindow" ) : NULL;
    DWORD (WINAPI *owner)( HWND, DWORD * ) = user32 ? (void *)GetProcAddress( user32, "GetWindowThreadProcessId" ) : NULL;
    int (WINAPI *class_of)( HWND, WCHAR *, int ) = user32 ? (void *)GetProcAddress( user32, "GetClassNameW" ) : NULL;
    HWND hwnd;
    WCHAR class[64] = {0};
    int desktop;

    if (!front || !owner || !class_of) return;
    if ((hwnd = front())) class_of( hwnd, class, ARRAY_SIZE(class) );
    desktop = !hwnd || !owner( hwnd, NULL ) || ps4_overlay_is_desktop( hwnd, class );
    if (desktop == reported) return;
    reported = desktop;
    ERR( "PWOVERLAY desktop in_front=%d window=%p class=%s\\n", desktop, hwnd, debugstr_w(class) );
    ps4_guest_pad_profile( L"<overlay-desktop>", desktop );
}
#endif

static DWORD WINAPI ps4_overlay_closer( void *arg )
{
    HANDLE event32 = CreateEventW( NULL, FALSE, FALSE, PS4_OVERLAY_EVENT32 );
#ifdef _WIN64
    HMODULE user32 = LoadLibraryW( L"user32.dll" );
    BOOL (WINAPI *hotkey)( HWND, int, UINT, UINT ) = user32 ? (void *)GetProcAddress( user32, "RegisterHotKey" ) : NULL;
    BOOL (WINAPI *get)( void *, HWND, UINT, UINT ) = user32 ? (void *)GetProcAddress( user32, "GetMessageW" ) : NULL;
    UINT_PTR (WINAPI *timer)( HWND, UINT_PTR, UINT, void * ) = user32 ? (void *)GetProcAddress( user32, "SetTimer" ) : NULL;
    struct { HWND hwnd; UINT message; WPARAM wparam; LPARAM lparam; DWORD time; POINT pt; DWORD reserved; } msg;
    unsigned int hud_keys = 0, ticks = 0;
    BOOL hud;

    /* W239: Salir is polled (the overlay's request, every 150 ms), not a key: in W238 the title ended
     * as soon as F24 entered the input path, before this thread got any WM_HOTKEY */
    if (!get || !timer || !timer( NULL, 0, 150, NULL ))
    {
        ERR( "PWOVERLAY closer: no timer, error %lu: Salir not available\\n", GetLastError() );
        return 0;
    }
    /* W238: MangoHud's toggle_hud is F12 alone on Windows (overlay_params.cpp), read with
     * GetAsyncKeyState. The server sets the key's async state before it turns a key into a hotkey
     * (queue_hardware_message), so with Shift+F12 registered MangoHud sees F12 down and the program
     * gets no F12. Without this hotkey or the timer, MangoHud is never reported, and the overlay keeps
     * its own readout. */
    hud = hotkey && hotkey( NULL, PS4_OVERLAY_HOTKEY_HUD, 0x0004 /* MOD_SHIFT */, 0x7b /* VK_F12 */ );
    if (!hud) ERR( "PWOVERLAY closer: no Shift+F12 hotkey, error %lu: MangoHud not offered\\n", GetLastError() );
    ERR( "PWOVERLAY closer ready: request poll 150 ms, mangohud=%u, event32=%p\\n", hud, event32 );
    if (hud) ps4_guest_pad_profile( L"<mangohud>", FALSE );  /* W242: nothing in front until checked */
    while (get( &msg, NULL, 0, 0 ) > 0)
    {
        char reply[128], result[64];

        if (msg.message == 0x0312 /* WM_HOTKEY */ && msg.wparam == PS4_OVERLAY_HOTKEY_HUD && hud_keys++ < 8)
            ERR( "PWOVERLAY mangohud key: Shift+F12 held back from the program\\n" );
        if (msg.message != 0x0113 /* WM_TIMER */) continue;
        if (!ps4_overlay_call( "<overlay-poll>", reply, sizeof(reply) )) continue;
        if (hud && !(++ticks % 7)) ps4_overlay_report_hud( reply );  /* about once a second */
        ps4_overlay_report_desktop();  /* W261 */
        if (strncmp( reply, "exit", 4 ) || (reply[4] && reply[4] != ' ')) continue;
        ERR( "PWOVERLAY closer exit request\\n" );
        lstrcpyA( result, "<overlay-result>" );
        lstrcatA( result, ps4_overlay_close_foreground( event32 ) );
        ps4_overlay_call( result, NULL, 0 );
    }
#else
    if (!event32)
    {
        ERR( "PWOVERLAY closer32: no event, error %lu\\n", GetLastError() );
        return 0;
    }
    ResetEvent( event32 );  /* a request from before this world had a closer is not for it */
    {
        /* W245: and, once a second, whether this world has MangoHud's i386 layer (PwOverlayHud32) */
        HANDLE hud32 = CreateEventW( NULL, TRUE, FALSE, PS4_OVERLAY_HUD32 );
        int reported = -1, loaded;
        DWORD wait;

        ERR( "PWOVERLAY closer32 ready, hud32=%p\\n", hud32 );
        while ((wait = WaitForSingleObject( event32, 1000 )) == WAIT_OBJECT_0 || wait == WAIT_TIMEOUT)
        {
            if (wait == WAIT_OBJECT_0) ps4_overlay_close_foreground( NULL );
            if (!hud32 || (loaded = ps4_overlay_mangohud_loaded()) < 0 || loaded == reported) continue;
            reported = loaded;
            if (loaded) SetEvent( hud32 );
            else ResetEvent( hud32 );
            ERR( "PWOVERLAY closer32 mangohud loaded=%d\\n", loaded );
        }
        ERR( "PWOVERLAY closer32 ends: wait %lu, error %lu\\n", wait, GetLastError() );
    }
#endif
    return 0;
}

/* with the first program opened (64-bit explorer) or the first guest of the 32-bit world */
static void ps4_overlay_closer_start(void)
{
    static LONG started;
    struct ps4_guest *parent;
    HANDLE thread;

    if (InterlockedExchange( &started, 1 )) return;
    parent = ps4_guest_current();
    ps4_guest_set( NtCurrentTeb(), NULL );  /* not a thread of a guest that starts a program (W184) */
    thread = CreateThread( NULL, 0, ps4_overlay_closer, NULL, 0, NULL );
    ps4_guest_set( NtCurrentTeb(), parent );
    if (thread) CloseHandle( thread );
    else ERR( "PWOVERLAY closer: no thread, error %lu\\n", GetLastError() );
}

static BOOL ps4_guest_launch( const WCHAR *app_name, const WCHAR *cmd_line, DWORD flags, PROCESS_INFORMATION *info )
{''','The control overlay closes the guest in front (W236).')
revise('kernelbase','process','''    if (!GetEnvironmentVariableW( L"WINE_PS4_GUESTS", flag, ARRAY_SIZE(flag) ) || !(subsystem = ps4_guest_image( app_name )))
        return FALSE;''','''    if (!GetEnvironmentVariableW( L"WINE_PS4_GUESTS", flag, ARRAY_SIZE(flag) )) return FALSE;
    ps4_overlay_closer_start();  /* W236: also when this is a PE32 for the 32-bit world */
    if (!(subsystem = ps4_guest_image( app_name ))) return FALSE;''','Start the overlay closer with the first program (W236).')

# W244 (W242: gta-vc.exe faulted in ntdll32's alloc_tls_slot writing its TLS index, 0x006DF9E0): a guest EXE's
# layout and protections are traced before that write; writable sections the mapping left read-only become
# writable; an index outside the image is never written.
revise('ntdll','loader','''static BOOL alloc_tls_slot( LDR_DATA_TABLE_ENTRY *mod )
{''','''#ifndef _WIN64
/* PS4 hardware build (W244): a 32-bit guest EXE of explorer's 32-bit world, before its TLS index is written */
static BOOL ps4_guest_image_check( LDR_DATA_TABLE_ENTRY *mod, const IMAGE_TLS_DIRECTORY *dir )
{
    const IMAGE_NT_HEADERS *nt = RtlImageNtHeader( mod->DllBase );
    const IMAGE_SECTION_HEADER *sec;
    MEMORY_BASIC_INFORMATION info;
    char *base = mod->DllBase, *index = (char *)dir->AddressOfIndex;
    unsigned int i;

    if (NtCurrentTeb()->UserReserved[2] != 0x47345350 /* PS4 guest image load (W052) */ || !nt) return TRUE;
    ERR( "PWWOW guest32 image %s at %p preferred %#lx size %#lx section_align %#lx file_align %#lx tls_index %p\\n",
         debugstr_w(mod->BaseDllName.Buffer), base, nt->OptionalHeader.ImageBase, nt->OptionalHeader.SizeOfImage,
         nt->OptionalHeader.SectionAlignment, nt->OptionalHeader.FileAlignment, index );
    sec = IMAGE_FIRST_SECTION( nt );
    for (i = 0; i < nt->FileHeader.NumberOfSections; i++, sec++)
    {
        char *start = base + sec->VirtualAddress;
        SIZE_T size = sec->Misc.VirtualSize ? sec->Misc.VirtualSize : sec->SizeOfRawData;

        memset( &info, 0, sizeof(info) );
        NtQueryVirtualMemory( GetCurrentProcess(), start, MemoryBasicInformation, &info, sizeof(info), NULL );
        ERR( "PWWOW guest32 image section %.8s rva %#lx size %#lx flags %#lx: protect %#lx state %#lx region %p+%#lx\\n",
             (const char *)sec->Name, sec->VirtualAddress, (ULONG)size, sec->Characteristics, info.Protect, info.State,
             info.BaseAddress, (ULONG)info.RegionSize );
        /* a writable section the mapping left read-only (a 16 KiB host page shared with a read-only one) */
        if ((sec->Characteristics & IMAGE_SCN_MEM_WRITE) && info.State == MEM_COMMIT &&
            !(info.Protect & (PAGE_READWRITE | PAGE_WRITECOPY | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY)))
        {
            void *addr = start;
            ULONG old = 0;
            NTSTATUS status = NtProtectVirtualMemory( GetCurrentProcess(), &addr, &size,
                                                      (sec->Characteristics & IMAGE_SCN_MEM_EXECUTE) ?
                                                      PAGE_EXECUTE_READWRITE : PAGE_READWRITE, &old );
            ERR( "PWWOW guest32 image section %.8s made writable status %#lx old %#lx\\n", (const char *)sec->Name,
                 status, old );
        }
    }
    if (index < base || index + sizeof(DWORD) > base + nt->OptionalHeader.SizeOfImage)
    {
        ERR( "PWWOW guest32 image tls_index %p outside the image %p-%p (not relocated?): not written\\n",
             index, base, base + nt->OptionalHeader.SizeOfImage );
        return FALSE;
    }
    memset( &info, 0, sizeof(info) );
    NtQueryVirtualMemory( GetCurrentProcess(), index, MemoryBasicInformation, &info, sizeof(info), NULL );
    ERR( "PWWOW guest32 image tls_index %p protect %#lx state %#lx\\n", index, info.Protect, info.State );
    return info.State == MEM_COMMIT;
}
#endif

static BOOL alloc_tls_slot( LDR_DATA_TABLE_ENTRY *mod )
{''','A 32-bit guest EXE before its TLS index is written (W244).')
revise('ntdll','loader','''    *(DWORD *)dir->AddressOfIndex = i;''','''#ifndef _WIN64
    if (!ps4_guest_image_check( mod, dir )) return FALSE;  /* W244 */
#endif
    *(DWORD *)dir->AddressOfIndex = i;''','A 32-bit guest EXE before its TLS index is written (W244).')

# W248 (W246: SuperMarioKart left the desktop at its 800x600): a guest's display mode is undone when it ends.
revise('kernelbase','process','''#include "winnls.h"
#include "wincontypes.h"''','''#include "winnls.h"
#include "wingdi.h"  /* W248: DEVMODEW */
#include "wincontypes.h"''','DEVMODEW (W248).')
revise('kernelbase','process','''static void ps4_guest_unload( struct ps4_guest *guest )
{''','''/* W248: the display mode a guest found when it started, set back when it ends if it changed. ps5drv offers one
 * mode, so win32u applies a program's ChangeDisplaySettings to the whole desktop (W246: SuperMarioKart's
 * 800x600, and explorer's taskbar moved to 0,580); a process ending takes its mode with it on Windows, a guest
 * does not. Every end goes through ps4_guest_unload: its exit, a fault, the overlay's Salir. Which guest
 * changed the mode is not known here (win32u logs the thread): the newest live guest, or the last one, sets it
 * back; an older one ending (a helper the game started before, or a program opened earlier) leaves it. */
#define PS4_ENUM_CURRENT_SETTINGS ((DWORD)-1)
static LONG ps4_guest_serial;
static void ps4_guest_note_mode( struct ps4_guest *guest )
{
    HMODULE user32 = LoadLibraryW( L"user32.dll" );
    BOOL (WINAPI *settings)( const WCHAR *, DWORD, DEVMODEW * ) =
        user32 ? (void *)GetProcAddress( user32, "EnumDisplaySettingsW" ) : NULL;
    DEVMODEW mode = {.dmSize = sizeof(mode)};

    guest->serial = InterlockedIncrement( &ps4_guest_serial );
    if (!settings || !settings( NULL, PS4_ENUM_CURRENT_SETTINGS, &mode )) return;
    guest->mode_width = mode.dmPelsWidth;
    guest->mode_height = mode.dmPelsHeight;
}

static void ps4_guest_restore_mode( struct ps4_guest *guest )
{
    HMODULE user32 = GetModuleHandleW( L"user32.dll" );
    BOOL (WINAPI *settings)( const WCHAR *, DWORD, DEVMODEW * ) =
        user32 ? (void *)GetProcAddress( user32, "EnumDisplaySettingsW" ) : NULL;
    LONG (WINAPI *change)( const WCHAR *, DEVMODEW *, HWND, DWORD, void * ) =
        user32 ? (void *)GetProcAddress( user32, "ChangeDisplaySettingsExW" ) : NULL;
    DEVMODEW now = {.dmSize = sizeof(now)}, back = {.dmSize = sizeof(back)};
    WCHAR path[MAX_PATH];
    struct ps4_guest *newer = NULL;
    LONG ret;
    UINT i;

    if (!guest->mode_width || !settings || !change || !settings( NULL, PS4_ENUM_CURRENT_SETTINGS, &now )) return;
    if (now.dmPelsWidth == guest->mode_width && now.dmPelsHeight == guest->mode_height) return;
    if (!GetModuleFileNameW( guest->module, path, ARRAY_SIZE(path) )) path[0] = 0;
    RtlAcquireSRWLockShared( &ps4_live_lock );
    for (i = 0; i < ps4_live_count && !newer; i++)
        if (ps4_live_guests[i] != guest && ps4_live_guests[i]->serial > guest->serial) newer = ps4_live_guests[i];
    RtlReleaseSRWLockShared( &ps4_live_lock );
    if (newer)
    {
        ERR( "PWSINK mode kept guest=%s %lux%lu: a newer guest (module %p) runs\\n", debugstr_w(path), now.dmPelsWidth,
             now.dmPelsHeight, newer->module );
        return;
    }
    back.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT;
    back.dmPelsWidth = guest->mode_width;
    back.dmPelsHeight = guest->mode_height;
    ret = change( NULL, &back, NULL, 0, NULL );
    ERR( "PWSINK mode restore guest=%s %lux%lu -> %lux%lu result=%ld\\n", debugstr_w(path), now.dmPelsWidth,
         now.dmPelsHeight, guest->mode_width, guest->mode_height, ret );
}

static void ps4_guest_unload( struct ps4_guest *guest )
{''','Note and restore the display mode of a guest (W248).')
revise('kernelbase','process','''    ps4_guest_close_files( guest );  /* W206 */
    ps4_guest_unpatch( guest );      /* W224 */''','''    ps4_guest_close_files( guest );  /* W206 */
    ps4_guest_unpatch( guest );      /* W224 */
    ps4_guest_restore_mode( guest ); /* W248 */''','Restore the mode when a guest ends (W248).')
revise('kernelbase','process','''    guest->exit_process = ps4_guest_exit_process;''','''    guest->exit_process = ps4_guest_exit_process;
    ps4_guest_note_mode( guest );  /* W248 */''','Note the mode when a guest starts (W248).')

# W252 (W251: Vice City died silently after its first movie): each 32-bit thread of explorer's world logs its end
# (this i386 ntdll loads only there).
revise('ntdll','loader','''    /* don't do any detach calls if process is exiting */
    if (process_detaching) return;

    RtlProcessFlsData( NtCurrentTeb()->FlsSlots, 1 );''','''    /* don't do any detach calls if process is exiting */
    if (process_detaching) return;
#ifndef _WIN64
    ERR( "PWWOW guest32 thread %04lx ends\\n", HandleToULong( NtCurrentTeb()->ClientId.UniqueThread ) );  /* W252 */
#endif

    RtlProcessFlsData( NtCurrentTeb()->FlsSlots, 1 );''','A 32-bit thread of the world logs its end (W252).')

# W258 (W257: Portal's second hl2.exe faulted in the first one's vstdlib.dll; SuperMarioKart's ended thread 0070 left
# vulkan-1's critical section held): a critical section whose owner thread has ended is taken over by a waiter
# after its wait times out (W251 did it for wined3d's lock only).
revise('ntdll','sync','''        ERR( "section %p %s wait timed out in thread %04lx, blocked by %04lx, retrying (%u sec)\\n",
             crit, debugstr_a(crit_section_get_name(crit)), GetCurrentThreadId(), HandleToULong(crit->OwningThread), timeout );
    }''','''        ERR( "section %p %s wait timed out in thread %04lx, blocked by %04lx, retrying (%u sec)\\n",
             crit, debugstr_a(crit_section_get_name(crit)), GetCurrentThreadId(), HandleToULong(crit->OwningThread), timeout );
        {
            /* PS4 hardware build (W258): an owner that ended cannot release it (a guest thread ended inside it) */
            CLIENT_ID cid = { 0, crit->OwningThread };
            OBJECT_ATTRIBUTES attr = { sizeof(attr) };
            LARGE_INTEGER zero = {{0}};
            HANDLE thread;
            BOOL gone = FALSE;
            NTSTATUS st;

            if (cid.UniqueThread)
            {
                if ((st = NtOpenThread( &thread, SYNCHRONIZE, &attr, &cid )))
                    gone = (st == STATUS_INVALID_CID || st == STATUS_INVALID_PARAMETER);
                else
                {
                    gone = NtWaitForSingleObject( thread, FALSE, &zero ) == STATUS_WAIT_0;
                    NtClose( thread );
                }
            }
            if (gone && InterlockedCompareExchangePointer( &crit->OwningThread, NULL, cid.UniqueThread ) == cid.UniqueThread)
            {
                LONG recursion = crit->RecursionCount;

                ERR( "PWGUEST section %p %s held by ended thread %04lx (recursion %ld): taken over by %04lx\\n",
                     crit, debugstr_a(crit_section_get_name(crit)), HandleToULong(cid.UniqueThread), recursion,
                     GetCurrentThreadId() );
                crit->RecursionCount = 0;
                InterlockedExchangeAdd( &crit->LockCount, -recursion );
                break;  /* RtlEnterCriticalSection makes this thread the owner */
            }
        }
    }''','A critical section held by an ended thread is taken over (W258).')

# W267 (W266: Portal.exe, Portal's launcher, waited on hl2.exe's process handle, explorer's own, and kept 0x400000
# after hl2.exe ended, so Call of Duty got error 487): a guest's process handle is its end event (W210), which a wait
# follows; GetExitCodeProcess answers for it.
revise('kernelbase','process','''static void ps4_guest_unload( struct ps4_guest *guest );
''','''static void ps4_guest_unload( struct ps4_guest *guest );

/* W267: the end events (W210) handed out as guests' process handles, and the status each guest exited with */
static struct { HANDLE ended; DWORD status; } ps4_guest_exits[64];
static UINT ps4_guest_exit_count, ps4_guest_exit_next;
static SRWLOCK ps4_guest_exits_lock = SRWLOCK_INIT;

static void ps4_guest_exit_note( HANDLE ended, DWORD status, BOOL add )
{
    UINT i;

    if (!ended) return;
    RtlAcquireSRWLockExclusive( &ps4_guest_exits_lock );
    for (i = 0; i < ps4_guest_exit_count; i++)
        if (!NtCompareObjects( ps4_guest_exits[i].ended, ended )) break;
    if (i == ps4_guest_exit_count && add)
    {
        HANDLE copy;

        i = ps4_guest_exit_next++ % ARRAY_SIZE(ps4_guest_exits);
        if (ps4_guest_exits[i].ended) NtClose( ps4_guest_exits[i].ended );
        ps4_guest_exits[i].ended = NULL;
        if (DuplicateHandle( GetCurrentProcess(), ended, GetCurrentProcess(), &copy, SYNCHRONIZE, FALSE, 0 ))
            ps4_guest_exits[i].ended = copy;
        if (ps4_guest_exit_count < ARRAY_SIZE(ps4_guest_exits)) ps4_guest_exit_count++;
    }
    if (i < ps4_guest_exit_count) ps4_guest_exits[i].status = status;
    RtlReleaseSRWLockExclusive( &ps4_guest_exits_lock );
}

/* a guest's process handle: STILL_ACTIVE until the guest has ended, then its status */
static BOOL ps4_guest_exit_code( HANDLE process, DWORD *exit_code )
{
    BOOL found = FALSE;
    UINT i;

    RtlAcquireSRWLockShared( &ps4_guest_exits_lock );
    for (i = 0; i < ps4_guest_exit_count && !found; i++)
    {
        if (!ps4_guest_exits[i].ended || NtCompareObjects( ps4_guest_exits[i].ended, process )) continue;
        if (exit_code) *exit_code = WaitForSingleObject( process, 0 ) == WAIT_OBJECT_0 ?
                                    ps4_guest_exits[i].status : STILL_ACTIVE;
        found = TRUE;
    }
    RtlReleaseSRWLockShared( &ps4_guest_exits_lock );
    return found;
}
''','A guest process handle is its end event (W267).')
revise('kernelbase','process','''        guest->threads[guest->thread_count++] = copy;
    DuplicateHandle( GetCurrentProcess(), GetCurrentProcess(), GetCurrentProcess(), &info->hProcess, 0, FALSE, DUPLICATE_SAME_ACCESS );
''','''        guest->threads[guest->thread_count++] = copy;
    /* W267: the caller's process handle is the guest's end (W210): a launcher waiting for its game ends with it */
    if (guest->ended && DuplicateHandle( GetCurrentProcess(), guest->ended, GetCurrentProcess(), &info->hProcess,
                                         SYNCHRONIZE | EVENT_QUERY_STATE, FALSE, 0 ))
    {
        ps4_guest_exit_note( guest->ended, 0, TRUE );
        ERR( "PWGUEST process_handle %s: the guest's end event\\n", debugstr_w(app_name) );
    }
    else
        DuplicateHandle( GetCurrentProcess(), GetCurrentProcess(), GetCurrentProcess(), &info->hProcess, 0, FALSE, DUPLICATE_SAME_ACCESS );
''','A guest process handle is its end event (W267).')
revise('kernelbase','process','''    ERR( "PS4 guest module %p exits status %lu\\n", guest->module, status );
''','''    ERR( "PS4 guest module %p exits status %lu\\n", guest->module, status );
    ps4_guest_exit_note( guest->ended, status, FALSE );  /* W267: for GetExitCodeProcess */
''','The exit status of a guest, for its process handle (W267).')
revise('kernelbase','process','''BOOL WINAPI DECLSPEC_HOTPATCH GetExitCodeProcess( HANDLE process, LPDWORD exit_code )
{''','''static BOOL ps4_guest_exit_code( HANDLE process, DWORD *exit_code );  /* W267 */

BOOL WINAPI DECLSPEC_HOTPATCH GetExitCodeProcess( HANDLE process, LPDWORD exit_code )
{''','GetExitCodeProcess answers for a guest process handle (W267).')
revise('kernelbase','process','''    status = NtQueryInformationProcess( process, ProcessBasicInformation, &pbi, sizeof(pbi), NULL );
    if (!status && exit_code) *exit_code = pbi.ExitStatus;
''','''    status = NtQueryInformationProcess( process, ProcessBasicInformation, &pbi, sizeof(pbi), NULL );
    /* W267: a guest's process handle is its end event */
    if ((status == STATUS_OBJECT_TYPE_MISMATCH || status == STATUS_ACCESS_DENIED) && ps4_guest_exit_code( process, exit_code ))
        return TRUE;
    if (!status && exit_code) *exit_code = pbi.ExitStatus;
''','GetExitCodeProcess answers for a guest process handle (W267).')

# W269 (W267: Max Payne 1's own MSVCRT.DLL was a clash with syswow64's, explorer's 32-bit world loads its DLLs from
# syswow64 and the check exempted system32 only): a KnownDLL is the system's on Windows, and Wine's loader binds the
# import to the loaded one by name (find_basename_module); no clash.
revise('kernelbase','process','''                if (mod_dir_len == system_len + 1 && !wcsnicmp( path, system, system_len )) continue;
''','''                if (mod_dir_len == system_len + 1 && !wcsnicmp( path, system, system_len )) continue;
                {
                    /* W269: Wine's KnownDLLs (wine.inf): always the system's copy, as on Windows */
                    static const WCHAR *const known[] = { L"advapi32.dll", L"clbcatq.dll", L"combase.dll", L"comdlg32.dll", L"coml2.dll", L"difxapi.dll", L"gdi32.dll", L"gdiplus.dll", L"imagehlp.dll", L"imm32.dll", L"kernel32.dll", L"msctf.dll", L"msvcrt.dll", L"normaliz.dll", L"nsi.dll", L"ole32.dll", L"oleaut32.dll", L"psapi.dll", L"rpcrt4.dll", L"sechost.dll", L"setupapi.dll", L"shcore.dll", L"shell32.dll", L"shlwapi.dll", L"user32.dll", L"wldap32.dll", L"ws2_32.dll" };
                    UINT k;

                    for (k = 0; k < ARRAY_SIZE(known); k++) if (!wcsicmp( base, known[k] )) break;
                    if (k < ARRAY_SIZE(known))
                    {
                        memcpy( candidate, dir, dir_len * sizeof(WCHAR) );
                        memcpy( candidate + dir_len, base, (base_len + 1) * sizeof(WCHAR) );
                        if (GetFileAttributesW( candidate ) != INVALID_FILE_ATTRIBUTES)
                            ERR( "PWGUEST clash_known name=%s app=%s (KnownDLL: the system's copy, as Windows)\\n",
                                 debugstr_w(base), debugstr_w(app_name) );
                        continue;
                    }
                }
''','A KnownDLL in the program\'s folder is no clash (W269).')
# W269 (W267: Max Payne 2 ended after C++ exceptions its own handlers caught): the type and message of a guest's first
# C++ exceptions, with the throwing frames. Read only.
revise('kernelbase','process','''static LONG CALLBACK ps4_guest_fault_trace( EXCEPTION_POINTERS *ptrs )
{''','''/* W269: a C++ exception of a guest (e06d7363): its first catchable type, a std::exception's message, and the frames
 * that threw it. Read through NtReadVirtualMemory: a bad pointer reads nothing. x86 ThrowInfo holds pointers, x64 RVAs
 * from the image base (ExceptionInformation[3]) */
static BOOL ps4_guest_read( ULONG_PTR addr, void *buffer, SIZE_T size )
{
    SIZE_T done = 0;

    return addr && !NtReadVirtualMemory( GetCurrentProcess(), (void *)addr, buffer, size, &done ) && done == size;
}

static void ps4_guest_read_string( ULONG_PTR addr, char *buffer, UINT size )
{
    UINT i;

    for (i = 0; i + 1 < size && ps4_guest_read( addr + i, buffer + i, 1 ) && buffer[i]; i++);
    buffer[i] = 0;
}

static const char *ps4_guest_where( ULONG_PTR addr, char *buffer, UINT size )
{
    LDR_DATA_TABLE_ENTRY *mod;
    char name[64];

    if (LdrFindEntryForAddress( (void *)addr, &mod ) || !mod->BaseDllName.Buffer)
        snprintf( buffer, size, "%Ix", addr );
    else
    {
        WideCharToMultiByte( CP_UTF8, 0, mod->BaseDllName.Buffer, -1, name, sizeof(name), NULL, NULL );
        snprintf( buffer, size, "%s+%Ix", name, addr - (ULONG_PTR)mod->DllBase );
    }
    return buffer;
}

static void ps4_guest_cxx_trace( EXCEPTION_RECORD *rec, CONTEXT *context )
{
    static LONG traced;
    ULONG_PTR base, object;
    DWORD info[4] = {0}, cta[2] = {0}, ct[2] = {0};
    char type[96] = "", what[160] = "", where[96];
    ULONG_PTR message = 0;
    LONG n;

    if (rec->NumberParameters < 3 || (n = InterlockedIncrement( &traced )) > 24) return;
    object = rec->ExceptionInformation[1];
    base = rec->NumberParameters >= 4 ? rec->ExceptionInformation[3] : 0;
    if (ps4_guest_read( rec->ExceptionInformation[2], info, sizeof(info) ) && info[3] &&
        ps4_guest_read( base + info[3], cta, sizeof(cta) ) && cta[0] > 0 && cta[1] &&
        ps4_guest_read( base + cta[1], ct, sizeof(ct) ) && ct[1])
        ps4_guest_read_string( base + ct[1] + 2 * sizeof(void *), type, sizeof(type) );
    /* std::exception (MSVC): the vtable, then the message */
    if (strstr( type, "exception" ) && ps4_guest_read( object + sizeof(void *), &message, sizeof(message) ))
        ps4_guest_read_string( message, what, sizeof(what) );
    ERR( "PWCXX n=%ld thread=%04lx type=%s what=%s throw=%s\\n", n, GetCurrentThreadId(), type, what,
         ps4_guest_where( (ULONG_PTR)rec->ExceptionAddress, where, sizeof(where) ) );
#ifdef __i386__
    {
        NT_TIB *tib = &NtCurrentTeb()->Tib;
        ULONG ebp = context->Ebp, eip = context->Eip;
        UINT frame;

        for (frame = 0; frame < 8 && eip; frame++)
        {
            ERR( "PWCXX n=%ld frame %u %s\\n", n, frame, ps4_guest_where( eip, where, sizeof(where) ) );
            if (ebp < (ULONG_PTR)tib->StackLimit || ebp + 8 > (ULONG_PTR)tib->StackBase) break;
            eip = ((ULONG *)ebp)[1];
            ebp = ((ULONG *)ebp)[0];
        }
    }
#endif
}

static LONG CALLBACK ps4_guest_fault_trace( EXCEPTION_POINTERS *ptrs )
{''','The C++ exceptions of guests are traced (W269).')
revise('kernelbase','process','''    if ((rec->ExceptionCode != EXCEPTION_ACCESS_VIOLATION && !fp) || !ps4_guest_current()) return EXCEPTION_CONTINUE_SEARCH;
''','''    if (rec->ExceptionCode == 0xe06d7363 && ps4_guest_current()) ps4_guest_cxx_trace( rec, ptrs->ContextRecord );  /* W269 */
    if ((rec->ExceptionCode != EXCEPTION_ACCESS_VIOLATION && !fp) || !ps4_guest_current()) return EXCEPTION_CONTINUE_SEARCH;
''','The C++ exceptions of guests are traced (W269).')
# W269 (W267: Call of Duty ended with status 3 after its GL start, no fault or message): return addresses into the
# program's own image on the exiting thread's stack. Read only.
revise('kernelbase','process','''    ps4_guest_exit_note( guest->ended, status, FALSE );  /* W267: for GetExitCodeProcess */
''','''    ps4_guest_exit_note( guest->ended, status, FALSE );  /* W267: for GetExitCodeProcess */
    {
        /* W269: words on this thread's stack that point into the program's image, nearest first (the code that
         * called exit, abort or ExitProcess, and some data pointers) */
        LDR_DATA_TABLE_ENTRY *mod;
        NT_TIB *tib = &NtCurrentTeb()->Tib;
        ULONG_PTR marker = 0, *sp = &marker;
        UINT found = 0;

        if (guest->module && !LdrFindEntryForAddress( guest->module, &mod ))
            for (; sp + 1 <= (ULONG_PTR *)tib->StackBase && found < 12; sp++)
                if (*sp - (ULONG_PTR)mod->DllBase < mod->SizeOfImage)
                    ERR( "PWGUEST exit_caller %u %s+%Ix at %p\\n", found++, debugstr_w( mod->BaseDllName.Buffer ),
                         *sp - (ULONG_PTR)mod->DllBase, sp );
    }
''','Who asked for a guest\'s exit (W269).')

# W285 (W284: NFS Underground 2 closed from the overlay left its audio stream in the mixer until OrbisDesk ended):
# the audio driver takes the streams created by a guest's threads out of the mixer when the guest unloads
# (tools/build-audio-ps4.py, its call after mmdevapi's).
revise('kernelbase','process','''static void ps4_guest_unload( struct ps4_guest *guest )
{''','''/* W285: the streams of the audio driver (wineps4) that this guest's threads created leave the mixer. The driver
 * records the guest of the creating thread; its call 37 follows mmdevapi's 37 calls. */
static void ps4_guest_release_audio( struct ps4_guest *guest )
{
    /* what winecrt0's __wine_load_unix_lib and __wine_unix_call do; kernelbase does not link winecrt0's */
    static NTSTATUS (WINAPI *dispatcher)( UINT64 handle, unsigned int code, void *args );
    static UINT64 driver;
    static LONG state;  /* 0 not tried, 1 loaded, -1 not available */
    struct { UINT64 owner; UINT32 orphaned, kept; } params = { (ULONG_PTR)guest };
    NTSTATUS status;

    if (!state)
    {
        UNICODE_STRING name = RTL_CONSTANT_STRING( L"wineps4.drv" );
        void **export = (void **)GetProcAddress( GetModuleHandleW( L"ntdll.dll" ), "__wine_unix_call_dispatcher" );
        UINT64 res[2];

        status = export ? NtQueryVirtualMemory( GetCurrentProcess(), &name, MemoryWineLoadUnixLibByName,
                                                res, sizeof(res), NULL ) : STATUS_ENTRYPOINT_NOT_FOUND;
        if (!status)
        {
            dispatcher = *export;
            driver = res[1];
        }
        state = status ? -1 : 1;
        if (status) ERR( "PWAUDIO guest %p: the audio driver did not load (%#lx); its streams stay in the mixer\\n",
                         guest->module, status );
    }
    if (state != 1) return;
    status = dispatcher( driver, 37, &params );
    if (status) ERR( "PWAUDIO guest %p: releasing its streams failed (%#lx)\\n", guest->module, status );
    else if (params.orphaned) ERR( "PWAUDIO guest %p: %u streams out of the mixer, %u of others kept\\n",
                                   guest->module, params.orphaned, params.kept );
}

static void ps4_guest_unload( struct ps4_guest *guest )
{''','Take a guest\'s audio streams out of the mixer (W285).')
revise('kernelbase','process','''    ps4_guest_restore_mode( guest ); /* W248 */''','''    ps4_guest_restore_mode( guest ); /* W248 */
    ps4_guest_release_audio( guest ); /* W285 */''','Release the audio of a guest that ends (W285).')

# W287 (the overlay's GRAFICOS, native/hw_overlay.c): kernelbase's 64-bit closer reads and writes a program's choice in
# HKCU\Software\Wine\AppDefaults\<exe>; the guests' i386 ntdll loads Wine's own d3d8/d3d9 for a 32-bit guest whose
# AppDefaults\<exe>\DllOverrides asks for builtin (explorer's load order is explorer.exe's, never the guest's).
revise('kernelbase','process','''    ps4_guest_pad_profile( L"<overlay-desktop>", desktop );
}
#endif
''','''    ps4_guest_pad_profile( L"<overlay-desktop>", desktop );
}

/* W287: the overlay's GRAFICOS (native/hw_overlay.c) for a 32-bit program, in HKCU\\Software\\Wine\\AppDefaults\\<exe>:
 * Direct3D "renderer" ("gl"; no value: the 32-bit world's renderer=vulkan, which wined3d lets a program's own value
 * override, tools/build-wined3d-hw.py) and DllOverrides "d3d8" and "d3d9" ("builtin": Wine's on wined3d, from
 * syswow64\\pw-wined3d through the guests' ntdll; no value: DXVK). Choice 0 DXVK and Vulkan, 1 DXVK and OpenGL,
 * 2 wined3d and Vulkan, 3 wined3d and OpenGL; -1 a value the menu does not set. Read when the program starts. */
static int ps4_overlay_render_read( const WCHAR *exe, LSTATUS *status )
{
    WCHAR key[160], value[32];
    DWORD size = sizeof(value);
    int choice = 0;

    swprintf( key, ARRAY_SIZE(key), L"Software\\\\Wine\\\\AppDefaults\\\\%s\\\\Direct3D", exe );
    *status = RegGetValueW( HKEY_CURRENT_USER, key, L"renderer", RRF_RT_REG_SZ, NULL, value, &size );
    if (*status && *status != ERROR_FILE_NOT_FOUND) return -1;
    if (!*status && !wcsicmp( value, L"gl" )) choice |= 1;
    else if (!*status && wcsicmp( value, L"vulkan" )) choice = -1;
    swprintf( key, ARRAY_SIZE(key), L"Software\\\\Wine\\\\AppDefaults\\\\%s\\\\DllOverrides", exe );
    size = sizeof(value);
    *status = RegGetValueW( HKEY_CURRENT_USER, key, L"d3d9", RRF_RT_REG_SZ, NULL, value, &size );
    if (*status == ERROR_FILE_NOT_FOUND) *status = 0;
    else if (*status) return -1;
    else if (value[0] == 'b' || value[0] == 'B') { if (choice >= 0) choice |= 2; }  /* builtin, b */
    else if (value[0] != 'n' && value[0] != 'N') choice = -1;  /* native, n: DXVK */
    return choice;
}

/* W287: write a choice; the caller reads it back */
static LSTATUS ps4_overlay_render_write( const WCHAR *exe, int choice )
{
    static const WCHAR *const dlls[] = {L"d3d8", L"d3d9"};
    WCHAR key[160];
    LSTATUS status;
    unsigned int i;

    swprintf( key, ARRAY_SIZE(key), L"Software\\\\Wine\\\\AppDefaults\\\\%s\\\\Direct3D", exe );
    if (choice & 1) status = RegSetKeyValueW( HKEY_CURRENT_USER, key, L"renderer", REG_SZ, L"gl", sizeof(L"gl") );
    else if ((status = RegDeleteKeyValueW( HKEY_CURRENT_USER, key, L"renderer" )) == ERROR_FILE_NOT_FOUND) status = 0;
    if (status) return status;
    swprintf( key, ARRAY_SIZE(key), L"Software\\\\Wine\\\\AppDefaults\\\\%s\\\\DllOverrides", exe );
    for (i = 0; i < ARRAY_SIZE(dlls) && !status; i++)
    {
        if (choice & 2) status = RegSetKeyValueW( HKEY_CURRENT_USER, key, dlls[i], REG_SZ, L"builtin", sizeof(L"builtin") );
        else if ((status = RegDeleteKeyValueW( HKEY_CURRENT_USER, key, dlls[i] )) == ERROR_FILE_NOT_FOUND) status = 0;
    }
    return status;
}

/* W287: the overlay's GRAFICOS request ("get <exe>", "set <choice> <exe>" or "-"), answered with
 * "<overlay-render-result>get|set <choice, - for another value> <status> <exe>" */
static void ps4_overlay_render_poll(void)
{
    char request[160], result[200];
    const char *name = NULL;
    WCHAR exe[64];
    LSTATUS status = 0;
    int choice = -1, set = 0;

    if (!ps4_overlay_call( "<overlay-render-poll>", request, sizeof(request) )) return;
    if (!strncmp( request, "get ", 4 )) name = request + 4;
    else if (!strncmp( request, "set ", 4 ) && request[4] >= '0' && request[4] <= '3' && request[5] == ' ')
    {
        set = 1;
        choice = request[4] - '0';
        name = request + 6;
    }
    if (!name) return;
    if (!MultiByteToWideChar( CP_UTF8, 0, name, -1, exe, ARRAY_SIZE(exe) ) || !exe[0] || wcspbrk( exe, L"\\\\/" ))
    {
        status = ERROR_INVALID_NAME;
        choice = -1;
    }
    else if (!set || !(status = ps4_overlay_render_write( exe, choice ))) choice = ps4_overlay_render_read( exe, &status );
    else choice = -1;
    ERR( "PWOVERLAY render %s exe=%s choice=%d status=%ld\\n", set ? "set" : "get", debugstr_a(name), choice, status );
    snprintf( result, sizeof(result), "<overlay-render-result>%s %c %ld %s", set ? "set" : "get",
              choice < 0 ? '-' : '0' + choice, status, name );
    ps4_overlay_call( result, NULL, 0 );
}
#endif
''',"The overlay's GRAFICOS in the registry (W287).")
revise('kernelbase','process','''        ps4_overlay_report_desktop();  /* W261 */
''','''        ps4_overlay_report_desktop();  /* W261 */
        ps4_overlay_render_poll();  /* W287 */
''','The closer answers GRAFICOS (W287).')
revise('ntdll','loader','''static NTSTATUS find_dll_file( const WCHAR *load_path, const WCHAR *libname, UNICODE_STRING *nt_name,''','''#ifndef _WIN64
/* Orbis-win W287 (the overlay's GRAFICOS, native/hw_overlay.c): a 32-bit guest of explorer's world whose own
 * HKCU\\Software\\Wine\\AppDefaults\\<exe>\\DllOverrides says "builtin" (or "b") for d3d8 or d3d9 gets Wine's
 * own from syswow64\\pw-wined3d (on wined3d) instead of syswow64's DXVK. The process's load order reads one
 * AppDefaults key, the main EXE's (explorer.exe), so the guest's is read here. The guest is the thread's
 * (TEB.UserReserved, kernelbase's struct ps4_guest) or, while its EXE loads, that EXE (as kernelbase W273).
 * NULL: the usual search. Loader lock held. */
static WCHAR *ps4_guest_d3d_builtin( const WCHAR *libname )
{
    static const WCHAR *const names[] = {L"d3d8", L"d3d9"};
    static const WCHAR dir[] = L"C:\\\\windows\\\\syswow64\\\\pw-wined3d\\\\";
    /* the first members of kernelbase's struct ps4_guest (ps4_guest.h) */
    const struct { void *exit_process; void *atexit_table[3]; HMODULE module; } *guest =
        *(void **)NtCurrentTeb()->UserReserved;
    LIST_ENTRY *list = &NtCurrentTeb()->Peb->LdrData->InLoadOrderModuleList, *entry;
    const UNICODE_STRING *program = NULL;
    char buffer[FIELD_OFFSET( KEY_VALUE_PARTIAL_INFORMATION, Data[34 * sizeof(WCHAR)] )];
    KEY_VALUE_PARTIAL_INFORMATION *info = (KEY_VALUE_PARTIAL_INFORMATION *)buffer;
    WCHAR path[128], *data, *fullname;
    UNICODE_STRING str;
    OBJECT_ATTRIBUTES attr;
    HANDLE root, key;
    NTSTATUS status;
    DWORD size;
    unsigned int i, len = 0;

    for (i = 0; i < ARRAY_SIZE(names); i++)
    {
        len = wcslen( names[i] );
        if (!wcsnicmp( libname, names[i], len ) && (!libname[len] || !wcsicmp( libname + len, L".dll" ))) break;
    }
    if (i == ARRAY_SIZE(names)) return NULL;
    if (!guest && NtCurrentTeb()->UserReserved[2] != 0x47345350 /* PS4 guest image load (W052) */) return NULL;
    for (entry = list->Blink; entry != list && !program; entry = entry->Blink)
    {
        LDR_DATA_TABLE_ENTRY *mod = CONTAINING_RECORD( entry, LDR_DATA_TABLE_ENTRY, InLoadOrderLinks );
        if (guest ? mod->DllBase == guest->module :
            !(mod->Flags & LDR_IMAGE_IS_DLL) && mod->DllBase != NtCurrentTeb()->Peb->ImageBaseAddress)
            program = &mod->BaseDllName;
    }
    if (!program || program->Length / sizeof(WCHAR) > 64) return NULL;
    wcscpy( path, L"Software\\\\Wine\\\\AppDefaults\\\\" );
    len = wcslen( path );
    memcpy( path + len, program->Buffer, program->Length );
    path[len + program->Length / sizeof(WCHAR)] = 0;
    wcscat( path, L"\\\\DllOverrides" );
    if (RtlOpenCurrentUser( KEY_READ, &root )) return NULL;
    RtlInitUnicodeString( &str, path );
    InitializeObjectAttributes( &attr, &str, OBJ_CASE_INSENSITIVE, root, NULL );
    status = NtOpenKey( &key, KEY_READ, &attr );
    NtClose( root );
    if (status) return NULL;
    RtlInitUnicodeString( &str, names[i] );
    status = NtQueryValueKey( key, &str, KeyValuePartialInformation, buffer, sizeof(buffer) - sizeof(WCHAR), &size );
    NtClose( key );
    if (status || info->Type != REG_SZ) return NULL;
    data = (WCHAR *)info->Data;
    data[info->DataLength / sizeof(WCHAR)] = 0;
    for (len = 0; data[len] && data[len] != ','; len++) {}
    if (!(len == 1 && (data[0] == 'b' || data[0] == 'B')) && !(len == 7 && !wcsnicmp( data, L"builtin", 7 ))) return NULL;
    if (!(fullname = RtlAllocateHeap( GetProcessHeap(), 0, sizeof(dir) + (wcslen( names[i] ) + 4) * sizeof(WCHAR) )))
        return NULL;
    wcscpy( fullname, dir );
    wcscat( fullname, names[i] );
    wcscat( fullname, L".dll" );
    ERR( "PWGUEST %s for %s: %s (its AppDefaults DllOverrides)\\n", debugstr_w(libname), debugstr_us(program),
         debugstr_w(fullname) );
    return fullname;
}
#endif

static NTSTATUS find_dll_file( const WCHAR *load_path, const WCHAR *libname, UNICODE_STRING *nt_name,''',
       "A 32-bit guest's own choice of Wine's d3d8/d3d9 (W287).")
revise('ntdll','loader','''    nt_name->Buffer = NULL;

    if (!contains_path( libname ))
    {
        status = find_apiset_dll( libname, &fullname );''','''    nt_name->Buffer = NULL;

#ifndef _WIN64
    /* Orbis-win W287: a 32-bit guest's own choice of Wine's d3d8/d3d9; fullname is freed below */
    if (!contains_path( libname ) && (fullname = ps4_guest_d3d_builtin( libname ))) libname = fullname;
#endif
    if (!contains_path( libname ))
    {
        status = find_apiset_dll( libname, &fullname );''',"A 32-bit guest's own choice of Wine's d3d8/d3d9 (W287).")

# W293 (W292: Portal 2's exit hung explorer: its own tier0 took the last reference to system32 WINMM.dll with it, and
# winmm's DllMain(DETACH) released dinput, which waits for its hook thread, process-wide since W281, while the exiting
# thread holds the loader lock; the hook thread ends with FreeLibraryAndExitThread, which needs that lock). A module
# whose thread lives for the whole process stays loaded and attached for the whole process (W173 did it for Mesa).
revise('kernelbase','thread','''            ERR( "PWGUEST shared_thread %04lx start=%s+%Ix: not the guest's\\n", GetThreadId( handle ),
                 debugstr_w( mod->BaseDllName.Buffer ), (ULONG_PTR)start - (ULONG_PTR)mod->DllBase );
            guest = NULL;''','''            ERR( "PWGUEST shared_thread %04lx start=%s+%Ix: not the guest's\\n", GetThreadId( handle ),
                 debugstr_w( mod->BaseDllName.Buffer ), (ULONG_PTR)start - (ULONG_PTR)mod->DllBase );
            guest = NULL;
            {
                /* W293 (W292: winmm's DllMain(DETACH) at a guest's exit waited for dinput's thread, which needs the
                 * loader lock to end): the module of a process-wide thread is never detached or unmapped under it */
                HMODULE pinned;

                if (GetModuleHandleExW( GET_MODULE_HANDLE_EX_FLAG_PIN | GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS,
                                        (const WCHAR *)(ULONG_PTR)start, &pinned ))
                    ERR( "PWGUEST shared_thread module %s pinned at %p\\n", debugstr_w( mod->BaseDllName.Buffer ), pinned );
                else ERR( "PWGUEST shared_thread module %s not pinned (error %lu)\\n", debugstr_w( mod->BaseDllName.Buffer ),
                          GetLastError() );
            }''','The module of a process-wide thread is pinned (W293).')
revise('kernelbase','process','''            static const WCHAR *const resident[] = { L"opengl32.dll", L"libgallium_wgl.dll" };''',
'''            /* W293 (W292): and winmm, dinput, dinput8, whose threads are process-wide since W281: winmm's
             * DllMain(DETACH) releases dinput, which waits for its hook thread under the loader lock */
            static const WCHAR *const resident[] = { L"opengl32.dll", L"libgallium_wgl.dll", L"winmm.dll",
                                                     L"dinput.dll", L"dinput8.dll" };''','The modules with process-wide threads stay (W293).')
revise('kernelbase','process','''static void ps4_guest_unload( struct ps4_guest *guest )
{''','''/* W293 (W292: a system module's DllMain(DETACH) hung a guest's exit): the system modules (Windows folder) this guest
 * loaded, before its unload; then which ones its unload took away, their DllMain(DETACH) run at the guest's exit */
struct ps4_guest_systems
{
    UINT count;
    struct { void *base; WCHAR name[48]; } entry[64];
};

static void ps4_guest_systems_before( struct ps4_guest *guest, struct ps4_guest_systems *systems )
{
    LIST_ENTRY *list = &NtCurrentTeb()->Peb->LdrData->InLoadOrderModuleList, *entry;
    ULONG_PTR magic;
    UINT j;

    systems->count = 0;
    if (LdrLockLoaderLock( 0, NULL, &magic )) return;
    for (entry = list->Flink; entry != list && systems->count < ARRAY_SIZE(systems->entry); entry = entry->Flink)
    {
        LDR_DATA_TABLE_ENTRY *mod = CONTAINING_RECORD( entry, LDR_DATA_TABLE_ENTRY, InLoadOrderLinks );

        if (mod->DllBase == guest->module || ps4_guest_outside_windows( &mod->FullDllName )) continue;
        for (j = 0; j < guest->modules_before_count; j++) if (guest->modules_before[j] == mod->DllBase) break;
        if (j < guest->modules_before_count) continue;
        systems->entry[systems->count].base = mod->DllBase;
        lstrcpynW( systems->entry[systems->count].name, mod->BaseDllName.Buffer ? mod->BaseDllName.Buffer : L"?",
                   ARRAY_SIZE(systems->entry[0].name) );
        ERR( "PWGUEST system_module %s base=%p refcount=%d\\n", debugstr_w( systems->entry[systems->count].name ),
             mod->DllBase, mod->LoadCount );
        systems->count++;
    }
    LdrUnlockLoaderLock( 0, magic );
}

static void ps4_guest_systems_after( struct ps4_guest *guest, const struct ps4_guest_systems *systems )
{
    UINT i, gone = 0;

    for (i = 0; i < systems->count; i++)
    {
        LDR_DATA_TABLE_ENTRY *mod;

        if (!LdrFindEntryForAddress( systems->entry[i].base, &mod ) && mod->DllBase == systems->entry[i].base) continue;
        ERR( "PWGUEST system_unloaded %s base=%p: its DllMain(DETACH) ran at the exit of module %p\\n",
             debugstr_w( systems->entry[i].name ), systems->entry[i].base, guest->module );
        gone++;
    }
    ERR( "PWGUEST system_modules module=%p loaded=%u unloaded=%u\\n", guest->module, systems->count, gone );
}

static void ps4_guest_unload( struct ps4_guest *guest )
{''','System modules loaded and unloaded by a guest are traced (W293).')
revise('kernelbase','process','''        UINT atom, unused = 0, unregistered = 0, in_use = 0, kept = 0;''','''        UINT atom, unused = 0, unregistered = 0, in_use = 0, kept = 0;
        struct ps4_guest_systems systems;  /* W293 */''','System modules of the guest (W293).')
revise('kernelbase','process','''        ERR( "PWGUEST unload_begin module=%p''','''        ps4_guest_systems_before( guest, &systems );  /* W293 */
        ERR( "PWGUEST unload_begin module=%p''','System modules before the unload (W293).')
revise('kernelbase','process','''        ps4_guest_unload_own( guest, FALSE );  /* W208 */''','''        ps4_guest_unload_own( guest, FALSE );  /* W208 */
        ps4_guest_systems_after( guest, &systems );  /* W293 */''','System modules the unload took away (W293).')
# W293 (W292: with the desktop hung, opening the program again waited 120 s and said only "error 1460"): when a start in
# the 32-bit world times out, the thread that holds the 32-bit loader lock, read through the waiting thread's TEB, in
# the log (PWOPEN world_loader_lock, world_failed ... cause=) and in the dialog.
revise('kernelbase','process','''static DWORD ps4_world_launch( const WCHAR *app_name, const WCHAR *cmd_line, const WCHAR *cur_dir, DWORD flags,
                               PROCESS_INFORMATION *info )
{''','''/* W293 (W292: a guest's exit hung holding the 32-bit loader lock, and the next 32-bit start waited for it): the thread
 * that holds the 32-bit world's loader lock, read through the TEB of a 32-bit thread that is still waiting */
static DWORD ps4_world_loader_owner;

static DWORD ps4_world_loader_holder( HANDLE thread )
{
    THREAD_BASIC_INFORMATION tbi;
    struct { ULONG debug_info; LONG lock_count, recursion; ULONG owner; } crit;  /* a 32-bit RTL_CRITICAL_SECTION */
    LONG offset = 0;
    ULONG peb32 = 0, lock32 = 0;
    char *teb;

    if (NtQueryInformationThread( thread, ThreadBasicInformation, &tbi, sizeof(tbi), NULL ) || !tbi.TebBaseAddress)
        return 0;
    teb = tbi.TebBaseAddress;
    if (!ReadProcessMemory( GetCurrentProcess(), teb + FIELD_OFFSET( TEB, WowTebOffset ), &offset, sizeof(offset), NULL ) ||
        !offset ||
        !ReadProcessMemory( GetCurrentProcess(), teb + offset + FIELD_OFFSET( TEB32, Peb ), &peb32, sizeof(peb32), NULL ) ||
        !peb32 ||
        !ReadProcessMemory( GetCurrentProcess(), (char *)ULongToPtr( peb32 ) + FIELD_OFFSET( PEB32, LoaderLock ), &lock32,
                            sizeof(lock32), NULL ) || !lock32 ||
        !ReadProcessMemory( GetCurrentProcess(), ULongToPtr( lock32 ), &crit, sizeof(crit), NULL ))
        return 0;
    ERR( "PWOPEN world_loader_lock owner=%04lx lock_count=%ld recursion=%ld\\n", crit.owner, crit.lock_count,
         crit.recursion );
    return crit.owner;
}

static DWORD ps4_world_launch( const WCHAR *app_name, const WCHAR *cmd_line, const WCHAR *cur_dir, DWORD flags,
                               PROCESS_INFORMATION *info )
{''','The holder of the 32-bit loader lock when a start times out (W293).')
revise('kernelbase','process','''    wait = ps4_world_wait( thread, 120000 );
    GetExitCodeThread( thread, &exit_code );''','''    wait = ps4_world_wait( thread, 120000 );
    ps4_world_loader_owner = wait == WAIT_OBJECT_0 ? 0 : ps4_world_loader_holder( thread );  /* W293 */
    GetExitCodeThread( thread, &exit_code );''','A timed-out start reads the loader lock holder (W293).')
# W293: the dialogs the guest model shows, in English (the meaning kept)
revise('kernelbase','process','''            swprintf( world_text, ARRAY_SIZE(world_text),
                      L"No se pudo abrir este programa de 32 bits dentro del escritorio (error %lu).\\n\\n"
                      L"Para abrirlo, OrbisDesk se reinicia y lo ejecuta solo; al cerrarlo vuelve al escritorio. "
                      L"Se cerrarán los programas abiertos. ¿Continuar?", error );''','''            if (error == ERROR_TIMEOUT && ps4_world_loader_owner)  /* W293 */
                swprintf( world_text, ARRAY_SIZE(world_text),
                          L"This 32-bit program could not be opened inside the desktop (error %lu: thread %04lx holds "
                          L"the 32-bit loader lock and has not released it, so 32-bit programs cannot start until "
                          L"OrbisDesk restarts).\\n\\n"
                          L"To open it, OrbisDesk restarts and runs it on its own; when you close it, you return to the "
                          L"desktop. Open programs will be closed. Continue?", error, ps4_world_loader_owner );
            else
                swprintf( world_text, ARRAY_SIZE(world_text),
                          L"This 32-bit program could not be opened inside the desktop (error %lu).\\n\\n"
                          L"To open it, OrbisDesk restarts and runs it on its own; when you close it, you return to the "
                          L"desktop. Open programs will be closed. Continue?", error );
            ERR( "PWOPEN world_failed image=%s error=%lu cause=%s loader_owner=%04lx\\n", debugstr_w(app_name), error,
                 error == ERROR_TIMEOUT ? (ps4_world_loader_owner ? "loader_lock_held" : "start_timeout") : "launch_error",
                 ps4_world_loader_owner );''','The world failure dialog in English, with the loader lock holder (W293).')
revise('kernelbase','process','''                      L"Este programa de 32 bits necesita la misma dirección de memoria que otro programa abierto "
                      L"en el escritorio y no se puede mover.\\n\\n"''','''                      L"This 32-bit program needs the same memory address as another program open on the "
                      L"desktop, and it cannot be moved.\\n\\n"''','Base taken dialog in English (W293).')
for spanish, english in (
    ('''L"Para abrirlo, OrbisDesk se reinicia y lo ejecuta solo, con los mismos argumentos; al cerrarlo "
                      L"vuelve al escritorio. Se cerrarán los programas abiertos. ¿Continuar?" );''',
     '''L"To open it, OrbisDesk restarts and runs it on its own, with the same arguments; when you close "
                      L"it, you return to the desktop. Open programs will be closed. Continue?" );'''),
    ('''L"Este es un programa de 32 bits. Para abrirlo, OrbisDesk se reinicia y lo ejecuta solo; "
                L"al cerrarlo vuelve al escritorio.\\n\\nSe cerrarán los programas abiertos. ¿Continuar?" :''',
     '''L"This is a 32-bit program. To open it, OrbisDesk restarts and runs it on its own; "
                L"when you close it, you return to the desktop.\\n\\nOpen programs will be closed. Continue?" :'''),
    ('''L"Este programa se ejecuta solo: OrbisDesk se reinicia para abrirlo y al cerrarlo vuelve al "
                L"escritorio.\\n\\nSe cerrarán los programas abiertos. ¿Continuar?",''',
     '''L"This program runs on its own: OrbisDesk restarts to open it, and when you close it, you return "
                L"to the desktop.\\n\\nOpen programs will be closed. Continue?",'''),
    ('''swprintf( text, ARRAY_SIZE(text), L"Este programa no puede abrirse ahora: usa su propia %s y ya hay otra cargada "
                      L"(%s).\\n\\nReiniciá OrbisDesk y abrilo antes que el otro programa.", clash, loaded );''',
     '''swprintf( text, ARRAY_SIZE(text), L"This program cannot be opened now: it uses its own %s, and another one is "
                      L"already loaded (%s).\\n\\nRestart OrbisDesk and open this program before the other one.", clash, loaded );'''),
):
    revise('kernelbase','process',spanish,english,'A dialog in English (W293).')
# the "already open" box, twice (64-bit second start and the 32-bit world's bridge)
_target=overlay/'kernelbase'/'process.c';_text=_target.read_text()
_old='L"Este programa ya está abierto. Esperá a que aparezca su ventana, o cerralo antes de volver a abrirlo."'
if _text.count(_old)!=2:raise SystemExit('Unexpected count of the already-open text: %d'%_text.count(_old))
_target.write_text(_text.replace(_old,'L"This program is already open. Wait for its window to appear, or close it before opening it again."'))
revisions.append({'path':sources['kernelbase']['process'],'module':'kernelbase','why':'The already-open dialog in English (W293).'})

# W235 (pe32-en-explorer-plan.md P6): the same modules, built for x86_64 (out/guest-hw) and for i386
# alpha-1 (W299: a 403 KB release run log): diagnostic lines of guests and of the 32-bit world follow OrbisDesk's
# trace switch, PW_TRACE=0|1 from the launcher (platform/ps4/pw_trace.h; unset counts as on). Failures still log.
revise('kernelbase','volume','''        ERR( "PWFS logical_drives accessible_roots=%08lx\\n", mask );''','''        {
            static DWORD logged_mask = ~0u;  /* alpha-1: the first answer and each change, not every call */

            if (mask != logged_mask) ERR( "PWFS logical_drives accessible_roots=%08lx\\n", mask );
            logged_mask = mask;
        }''','GetLogicalDrives logs its first answer and each change (alpha-1).')
revise('kernelbase','process','''static void WINAPI ps4_guest_exit_process( struct ps4_guest *guest, DWORD status )
{''','''/* alpha-1: OrbisDesk's trace switch as the launcher hands it to Windows code (PW_TRACE=0|1, platform/ps4/pw_trace.h);
 * unset counts as on. Read once. */
static BOOL ps4_guest_traced( void )
{
    static LONG traced = -1;

    if (traced < 0)
    {
        WCHAR value[4];

        traced = !(GetEnvironmentVariableW( L"PW_TRACE", value, ARRAY_SIZE(value) ) == 1 && value[0] == '0');
    }
    return traced;
}

static void WINAPI ps4_guest_exit_process( struct ps4_guest *guest, DWORD status )
{''','The trace switch in kernelbase (alpha-1).')
revise('kernelbase','process','''        if (guest->module && !LdrFindEntryForAddress( guest->module, &mod ))
            for (; sp + 1 <= (ULONG_PTR *)tib->StackBase && found < 12; sp++)''','''        /* alpha-1: for an exit with status 0 only with traces */
        if (guest->module && (status || ps4_guest_traced()) && !LdrFindEntryForAddress( guest->module, &mod ))
            for (; sp + 1 <= (ULONG_PTR *)tib->StackBase && found < 12; sp++)''','Exit callers of a clean exit only with traces (alpha-1).')
revise('kernelbase','process','''        ERR( "PWGUEST system_module %s base=%p refcount=%d\\n", debugstr_w( systems->entry[systems->count].name ),''','''        if (ps4_guest_traced())  /* alpha-1: system_unloaded and the system_modules summary always log */
        ERR( "PWGUEST system_module %s base=%p refcount=%d\\n", debugstr_w( systems->entry[systems->count].name ),''',
       'Per-DLL system module lines only with traces (alpha-1).')
revise('ntdll','loader','''/******************************************************************
 *		LdrShutdownThread (NTDLL.@)''','''#ifndef _WIN64
/* alpha-1: OrbisDesk's trace switch (PW_TRACE=0|1, platform/ps4/pw_trace.h); unset counts as on. Read once. */
static BOOL pw_loader_traced( void )
{
    static LONG traced = -1;

    if (traced < 0)
    {
        WCHAR buffer[4] = {0};
        UNICODE_STRING name, value;

        RtlInitUnicodeString( &name, L"PW_TRACE" );
        value.Buffer = buffer;
        value.Length = 0;
        value.MaximumLength = sizeof(buffer) - sizeof(WCHAR);
        traced = RtlQueryEnvironmentVariable_U( NULL, &name, &value ) || buffer[0] != '0';
    }
    return traced;
}
#endif

/******************************************************************
 *		LdrShutdownThread (NTDLL.@)''','The trace switch in the i386 ntdll (alpha-1).')
revise('ntdll','loader','''    ERR( "PWWOW guest32 thread %04lx ends\\n",''','''    if (pw_loader_traced())  /* alpha-1 */
    ERR( "PWWOW guest32 thread %04lx ends\\n",''','The end of a 32-bit thread only with traces (alpha-1).')
revise('ntdll','loader','''        ERR( "PWWOW guest32 thread %04lx loader_init: tls\\n",''','''        if (pw_loader_traced())  /* alpha-1 */
        ERR( "PWWOW guest32 thread %04lx loader_init: tls\\n",''','The steps of a 32-bit thread only with traces (alpha-1).')
revise('ntdll','loader','''        ERR( "PWWOW guest32 thread %04lx loader_init: attached\\n",''','''        if (pw_loader_traced())  /* alpha-1 */
        ERR( "PWWOW guest32 thread %04lx loader_init: attached\\n",''','The steps of a 32-bit thread only with traces (alpha-1).')

# (out/guest-hw-i386): the i386 ones are the guests' ntdll, kernelbase and ucrtbase in explorer's
# 32-bit world, in wine/lib/wine/i386-guest (tools/build-wine-hardware.py), which ntdll Unix searches
# only in a 64-bit process (tools/build-wow64-world-ps4.py).
def build(arch,work,out):
    for folder in (work,out):folder.mkdir(parents=True,exist_ok=True)
    modules={}
    for module in sources:
        units=sorted(sources[module])
        target=f'dlls/{module}/{arch}-windows/{module}.dll'
        dry=subprocess.run(['make','-n']+[f'-W../../source/{sources[module][u]}' for u in units]+[target],
                           cwd=BUILD,capture_output=True,text=True,check=True).stdout.replace('\\\n',' ')
        (work/module).mkdir(parents=True,exist_ok=True)
        commands=[]
        for line in dry.splitlines():
            if f'dlls/{module}/' not in line:continue
            for u in units:
                line=line.replace(f'../../source/{sources[module][u]}',str(overlay/module/(u+'.c')))
                line=re.sub(r'(?<![\w/.])dlls/%s/%s-windows/%s\.o\b'%(module,arch,u),str(work/module/(u+'.o')),line)
            line=re.sub(r'(?<![\w/.])%s(?![\w.])'%re.escape(target),str(work/module/(module+'.dll')),line)
            commands.append(line)
        if not any(str(work/module/(module+'.dll')) in c for c in commands):
            raise SystemExit('make -n did not give the %s link:\n%s'%(module,dry[-2000:]))
        for command in commands:
            run=subprocess.run(command,shell=True,cwd=BUILD,capture_output=True,text=True)
            if run.returncode:raise SystemExit(command[:300]+'\n'+run.stdout+run.stderr)
        shutil.copyfile(work/module/(module+'.dll'),out/(module+'.dll'))
        modules[module+'.dll']={'path':module+'.dll','sha256':sha(out/(module+'.dll')),'units':units,'commands':commands}
    manifest={'schema_version':1,'wine_commit':commit,'modules':modules,'revisions':revisions,
              'overlay_sha256':{str(p.relative_to(overlay)):sha(p) for p in sorted(overlay.rglob('*')) if p.is_file()}}
    if arch=='i386':manifest['builder_sha256']=sha(pathlib.Path(__file__))
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return modules
modules=build('x86_64',work,out)
modules32=build('i386',ROOT/'build/guest-hw-i386',ROOT/'out/guest-hw-i386')
print(json.dumps({name:e['sha256'] for name,e in modules.items()}|{'i386:'+name:e['sha256'] for name,e in modules32.items()}|{'revisions':len(revisions)}))
