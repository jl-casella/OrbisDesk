#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build the hardware variants of ntdll.dll and kernelbase.dll (PE64) that run guest programs.

W052, multitasking experiment. The current Wine desktop backend runs a 64-bit
GUI program as a guest inside this process; the external native-process probes
are not yet a Wine process backend:
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
/* PoP D.6: kernelbase process.c; CreateMutexA/W and CreateEventA/W of a guest thread */
void ps4_guest_object_made( HANDLE handle, void *caller );
/* W208: kernelbase process.c; VirtualAlloc and VirtualFree of a guest thread */
void ps4_guest_memory_reserved( void *base, void *caller );
void ps4_guest_memory_released( void *base );
/* W224: kernelbase process.c; VirtualProtectEx and WriteProcessMemory of a guest thread */
void ps4_guest_code_writable( HANDLE process, void *addr, SIZE_T size, DWORD prot );
/* alpha 2: OrbisDesk's trace switch as the launcher hands it to Windows code (PW_TRACE=0|1,
 * platform/ps4/pw_trace.h); unset counts as on. Read once in each file that includes this. */
static inline BOOL ps4_pw_traced( void )
{
    static LONG traced = -1;

    if (traced < 0)
    {
        WCHAR value[4];

        traced = !(GetEnvironmentVariableW( L"PW_TRACE", value, ARRAY_SIZE(value) ) == 1 && value[0] == '0');
    }
    return traced;
}
'''
(overlay/'kernelbase').mkdir(parents=True,exist_ok=True);(overlay/'kernelbase/ps4_guest.h').write_text(GUEST_H)
for header in ('pw_execution_mode.h','pw_execution_policy.h'):
    shutil.copyfile(ROOT/'platform/ps4'/header,overlay/'kernelbase'/header)

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
# alpha-1 (run-0183, Warcraft III 1.07 "was unable to initialize"): the DLLs a guest EXE imports
# are its process's static imports, and Windows calls their DllMain(DLL_PROCESS_ATTACH) with a
# non-NULL lpReserved; LoadLibrary passes NULL. The guest EXE loads through LoadLibraryEx, so its
# imports got NULL. Storm.dll (Warcraft III) takes NULL to mean "loaded by another program" and
# builds its MPQ crypt table from another seed: every file in the game's archives was then not
# found. Only the guest EXE's own load (not a DLL a DllMain loads meanwhile) passes a CONTEXT, as
# loader_init does for a process.
revise('ntdll','loader','''    if (nts == STATUS_SUCCESS)
    {
        nts = process_attach( wm->ldr.DdagNode, NULL );''','''    if (nts == STATUS_SUCCESS)
    {
        nts = process_attach( wm->ldr.DdagNode,
                              (NtCurrentTeb()->UserReserved[2] == 0x47345350 /* PS4 guest image load (W052) */ &&
                               !(wm->ldr.Flags & LDR_IMAGE_IS_DLL)) ? &ps4_guest_static_context : NULL );''',
       "A guest EXE's imports are static imports: DllMain gets a non-NULL lpReserved.")
# alpha-1 (run-0203, 2026-11-17, 04.15: Alan Wake ended, and none of the 48 system modules it had loaded was unloaded;
# 04.12's run-0185 unloaded 13 of them, msvcr100 among them): ntdll's process_attach pins each module it attaches with
# a non-NULL lpReserved ("pin it if imported by the main exe"), and run-0183's context went down the guest EXE's whole
# import tree. Its own modules were unpinned again at its end (d13, "was pinned by the program": no line in run-0185,
# 15 in run-0203); the system ones stayed for the life of the title, with their C runtime heaps and state, and the next
# start reused them. DllMain still gets the context; the pin is skipped for it.
revise('ntdll','loader','''static NTSTATUS process_attach( LDR_DDAG_NODE *node, LPVOID lpReserved );''','''static NTSTATUS process_attach( LDR_DDAG_NODE *node, LPVOID lpReserved );
static CONTEXT ps4_guest_static_context;  /* alpha-1 (run-0183): DllMain's lpReserved for a guest EXE's imports */''',
       "The static-import context of a guest EXE (alpha-1, run-0183).")
revise('ntdll','loader','''    if (lpReserved) wm->ldr.LoadCount = -1;  /* pin it if imported by the main exe */''','''    /* alpha-1 (run-0203): not a guest EXE's imports, which end with the guest */
    if (lpReserved && lpReserved != &ps4_guest_static_context) wm->ldr.LoadCount = -1;  /* pin it if imported by the main exe */''',
       "A guest EXE's imports are not pinned (alpha-1, run-0203).")
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
GUEST_ARGS_C='''/* PS4 hardware build (W057): the arguments of a guest program (kernelbase ps4_guest),
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

int* CDECL __p___argc(void) { int slot = guest_slot(); return slot < 0 ? &MSVCRT___argc : &guest_args[slot].argc; }'''
revise('ucrtbase','data','''int* CDECL __p___argc(void) { return &MSVCRT___argc; }''',GUEST_ARGS_C,"A guest's argc.",'dlls/msvcrt/data.c')
revise('ucrtbase','data','''char*** CDECL __p___argv(void) { return &MSVCRT___argv; }''',
       '''char*** CDECL __p___argv(void) { int slot = guest_slot(); return slot < 0 ? &MSVCRT___argv : &guest_args[slot].argv; }''',
       "A guest's argv.",'dlls/msvcrt/data.c')
revise('ucrtbase','data','''wchar_t*** CDECL __p___wargv(void) { return &MSVCRT___wargv; }''',
       '''wchar_t*** CDECL __p___wargv(void) { int slot = guest_slot(); return slot < 0 ? &MSVCRT___wargv : &guest_args[slot].wargv; }''',
       "A guest's wargv.",'dlls/msvcrt/data.c')
# PoP D.4 (run-0061: separate_game.exe, a mingw program a separate process started in the title, had argc 1 although
# Explorer passed its argument): msvcrt.dll's __getmainargs and __wgetmainargs answered with the process's own
# arguments, the title's. msvcrt gets ucrtbase's per-guest arguments (W057) in both views; a guest's arguments
# are not wildcard-expanded.
revise('msvcrt','data','#include "msvcrt.h"\n','#include "msvcrt.h"\n#include <winternl.h>\n','TEB access.')
revise('msvcrt','data','''int* CDECL __p___argc(void) { return &MSVCRT___argc; }''',GUEST_ARGS_C,"A guest's argc (msvcrt).")
revise('msvcrt','data','''char*** CDECL __p___argv(void) { return &MSVCRT___argv; }''',
       '''char*** CDECL __p___argv(void) { int slot = guest_slot(); return slot < 0 ? &MSVCRT___argv : &guest_args[slot].argv; }''',
       "A guest's argv (msvcrt).")
revise('msvcrt','data','''wchar_t*** CDECL __p___wargv(void) { return &MSVCRT___wargv; }''',
       '''wchar_t*** CDECL __p___wargv(void) { int slot = guest_slot(); return slot < 0 ? &MSVCRT___wargv : &guest_args[slot].wargv; }''',
       "A guest's wargv (msvcrt).")
for _kind in ('wargv', 'argv'):
    revise('msvcrt','data','''    *argc = MSVCRT___argc;
    *%s = MSVCRT___%s;''' % (_kind, _kind),'''    *argc = MSVCRT___argc;
    *%s = MSVCRT___%s;
    {
        int slot = guest_slot();  /* PoP D.4: a guest's own arguments */
        if (slot >= 0) { *argc = guest_args[slot].argc; *%s = guest_args[slot].%s; }
    }''' % (_kind, _kind, _kind, _kind),"__%sgetmainargs answers with a guest's arguments (PoP D.4)." % ('w' if _kind == 'wargv' else ''))

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
        /* d14 (run-0077: with GIO unloaded, MangoJuice's second start got past g_object_new, then GDK aborted
         * with status 3): GDK registers its classes under libgtk's instance, which the pass above does not
         * visit, and libgtk is unloaded with the EXE below; its classes stayed registered and the next start's
         * RegisterClassExW failed. The modules of the guest's own folder loaded after its start are visited
         * here, while still loaded: a class registered under one of them whose procedure is in the guest's own
         * code (them or its image) ends with it */
        {
            LDR_DATA_TABLE_ENTRY *self;
            WCHAR dir[MAX_PATH], *slash;
            void *bases[256];
            SIZE_T sizes[256];
            UINT count = 0, j, k;
            ULONG_PTR magic;

            dir[0] = 0;
            if (!LdrFindEntryForAddress( guest->module, &self ) && self->FullDllName.Buffer)
            {
                lstrcpynW( dir, self->FullDllName.Buffer, MAX_PATH );
                if ((slash = wcsrchr( dir, '\\\\' ))) slash[1] = 0;
                else dir[0] = 0;
            }
            if (dir[0] && !LdrLockLoaderLock( 0, NULL, &magic ))
            {
                LIST_ENTRY *list = &NtCurrentTeb()->Peb->LdrData->InLoadOrderModuleList, *entry;

                for (entry = list->Flink; entry != list && count < ARRAY_SIZE(bases); entry = entry->Flink)
                {
                    LDR_DATA_TABLE_ENTRY *mod = CONTAINING_RECORD( entry, LDR_DATA_TABLE_ENTRY, InLoadOrderLinks );

                    if (mod->DllBase == (void *)guest->module || !mod->FullDllName.Buffer ||
                        wcsnicmp( mod->FullDllName.Buffer, dir, wcslen( dir ) )) continue;
                    for (j = 0; j < guest->modules_before_count; j++)
                        if ((void *)guest->modules_before[j] == mod->DllBase) break;
                    if (j < guest->modules_before_count) continue;
                    bases[count] = mod->DllBase;
                    sizes[count++] = mod->SizeOfImage;
                }
                LdrUnlockLoaderLock( 0, magic );
            }
            for (atom = 0xc000, unused = 0; count && atom <= 0xffff && unused < 256; atom++)
            {
                if (!atom_name( atom, name, ARRAY_SIZE(name) )) { unused++; continue; }
                unused = 0;
                for (k = 0; k < count; k++)
                {
                    BOOL ours;

                    info.size = sizeof(info);
                    if (!class_info( (HINSTANCE)bases[k], (const WCHAR *)(ULONG_PTR)atom, &info )) continue;
                    if (((ULONG_PTR)info.proc >> 16) == 0xffff)
                    {
                        info.size = sizeof(info);
                        if (!class_infoA( (HINSTANCE)bases[k], (const char *)(ULONG_PTR)atom, &info )) continue;
                    }
                    ours = (char *)info.proc >= image && (char *)info.proc < image_end;
                    for (j = 0; !ours && j < count; j++)
                        ours = (char *)info.proc >= (char *)bases[j] && (char *)info.proc < (char *)bases[j] + sizes[j];
                    if (!ours) continue;
                    if (unregister( (const WCHAR *)(ULONG_PTR)atom, (HINSTANCE)bases[k] ))
                    {
                        if (ps4_pw_traced()) ERR( "PWGUEST class %s of module %p unregistered\\n", debugstr_w(name), bases[k] );
                        unregistered++;
                    }
                    else
                    {
                        ERR( "PWGUEST class %s of module %p kept (error %lu)\\n", debugstr_w(name), bases[k], GetLastError() );
                        in_use++;
                    }
                    break;
                }
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
#include "pw_execution_policy.h"

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
        if (ps4_runs_alone( app_name ))
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

    if (ps4_execution_mode( app_name ) == PW_EXEC_SEPARATE ||
        (ps4_separate_thread && ps4_separate_thread == GetCurrentThreadId()))
    {
        /* PoP Phase D.3: the program runs in a separate native process. The title's watcher
         * (native/pop_loader_spawn.h) starts it through the GoldHEN loader and it runs the image under Wine
         * as a client of this wineserver (native/process_p014_child.c, native/pop_wine_child.c). The request
         * carries a token, the image, the command line and the current directory; the new process writes its
         * Windows process and thread ids under that token, and the caller gets real handles to it, as from
         * CreateProcess: it can wait for it and read its exit code. */
        static const WCHAR request_name[] = L"Z:\\\\orbisdesk\\\\process-p014\\\\spawn-request";
        WCHAR dir[MAX_PATH], started[96];
        char text[4096];
        DWORD token = (GetTickCount() ^ (GetCurrentThreadId() << 16)) | 1, wrote = 0, got = 0, pid = 0, tid = 0, i;
        int n = 0, tries, len;
        HANDLE file;

        if (cur_dir) lstrcpynW( dir, cur_dir, MAX_PATH );
        else GetCurrentDirectoryW( MAX_PATH, dir );
        {   /* token, as decimal text */
            char digits[12]; int d = 0; DWORD v = token;
            do { digits[d++] = '0' + v % 10; v /= 10; } while (v);
            while (d) text[n++] = digits[--d];
            text[n++] = '\\n';
        }
        len = WideCharToMultiByte( CP_UTF8, 0, app_name, -1, text + n, sizeof(text) - n - 4, NULL, NULL );
        n += len > 0 ? len - 1 : 0; text[n++] = '\\n';
        len = WideCharToMultiByte( CP_UTF8, 0, tidy_cmdline ? tidy_cmdline : app_name, -1, text + n, sizeof(text) - n - 4, NULL, NULL );
        n += len > 0 ? len - 1 : 0; text[n++] = '\\n';
        len = WideCharToMultiByte( CP_UTF8, 0, dir, -1, text + n, sizeof(text) - n - 2, NULL, NULL );
        n += len > 0 ? len - 1 : 0; text[n++] = '\\n';

        file = CreateFileW( request_name, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL );
        if (file == INVALID_HANDLE_VALUE)
        {
            ERR( "PWSEP separate_request_failed image=%s error=%lu\\n", debugstr_w(app_name), GetLastError() );
            status = STATUS_UNSUCCESSFUL;
            goto done;
        }
        WriteFile( file, text, n, &wrote, NULL );
        CloseHandle( file );
        ERR( "PWSEP separate_request image=%s token=%lu cmdline=%s dir=%s\\n", debugstr_w(app_name), token,
             debugstr_w(tidy_cmdline), debugstr_w(dir) );

        /* the new process reports "pid tid" in started-<token> once it has joined this server */
        lstrcpyW( started, L"Z:\\\\orbisdesk\\\\process-p014\\\\started-" );
        {
            WCHAR digits[12]; int d = 0, s = lstrlenW( started ); DWORD v = token;
            do { digits[d++] = '0' + v % 10; v /= 10; } while (v);
            while (d) started[s++] = digits[--d];
            started[s] = 0;
        }
        for (tries = 0; tries < 300; tries++)   /* 30 s: the loader spawn and Wine's start take a few */
        {
            /* PoP D.7: the title reports a start that failed (no resident loader even after sending it) */
            {
                WCHAR failed[96];
                lstrcpyW( failed, L"Z:\\\\orbisdesk\\\\process-p014\\\\failed-" );
                lstrcatW( failed, started + 34 );   /* the token digits after "started-" */
                if (GetFileAttributesW( failed ) != INVALID_FILE_ATTRIBUTES)
                {
                    ERR( "PWSEP separate_failed_reported image=%s token=%lu\\n", debugstr_w(app_name), token );
                    DeleteFileW( failed );
                    break;
                }
            }
            file = CreateFileW( started, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, NULL,
                                OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL );
            if (file != INVALID_HANDLE_VALUE)
            {
                got = 0; ReadFile( file, text, sizeof(text) - 1, &got, NULL ); CloseHandle( file );
                text[got] = 0;
                if (got && text[got - 1] == '\\n') break;   /* complete line */
            }
            Sleep( 100 );
        }
        for (i = 0, pid = 0; i < got && text[i] >= '0' && text[i] <= '9'; i++) pid = pid * 10 + (text[i] - '0');
        for (i++, tid = 0; i < got && text[i] >= '0' && text[i] <= '9'; i++) tid = tid * 10 + (text[i] - '0');
        DeleteFileW( started );
        if (!pid)
        {
            ERR( "PWSEP separate_start_timeout image=%s token=%lu\\n", debugstr_w(app_name), token );
            status = STATUS_UNSUCCESSFUL;
            goto done;
        }
        info->hProcess = OpenProcess( PROCESS_ALL_ACCESS, inherit, pid );
        info->hThread = tid ? OpenThread( THREAD_ALL_ACCESS, inherit, tid ) : 0;
        info->dwProcessId = pid;
        info->dwThreadId = tid;
        ERR( "PWSEP separate_started image=%s token=%lu pid=%04lx tid=%04lx process=%p thread=%p\\n",
             debugstr_w(app_name), token, pid, tid, info->hProcess, info->hThread );
        status = info->hProcess ? STATUS_SUCCESS : STATUS_UNSUCCESSFUL;
        goto done;
    }
    if (ps4_guest_launch( app_name, tidy_cmdline, flags, info ))
    {
        status = STATUS_SUCCESS;
        goto done;
    }
#ifndef _WIN64
    if (ps4_execution_mode( app_name ) == PW_EXEC_GUEST)
    {
        status = STATUS_NOT_SUPPORTED;
        goto done;
    }
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
        /* PoP D.7 (hardware 2026-11-13: Vampire - Bloodlines' vampire.exe, the game itself, starts a "CleanUp
         * Application" from %TEMP% at its own base 0x400000; D.6 moved the game to a separate process, where Direct3D
         * has no GPU). The games that launchers start import a graphics library (POP.EXE d3d9, Worms3D.exe d3d8,
         * d3d9 and opengl32); a started program that imports none runs in a separate process itself, and the
         * starter keeps the base and the GPU here. A file that cannot be read keeps D.6.
         * Hardware 2026-11-16 (run-0164): Warcraft III's war3.exe imports no graphics library itself; it loads
         * Game.dll at run time, and Game.dll imports d3d8. Sent to the separate process, it found no Direct3D 8 and
         * said DirectX 8 was missing. The same run sent Vampire's vampire.exe there, whose renderer is in Bin\\*.dll.
         * The DLLs in the started program's folder and in its bin folder count as its own, up to 64 of them. */
        {
            static const char *const graphics[] = {"d3d8.dll", "d3d9.dll", "d3d10.dll", "d3d10_1.dll", "d3d11.dll",
                                                   "d3d12.dll", "dxgi.dll", "ddraw.dll", "opengl32.dll", "d3dim.dll",
                                                   "d3drm.dll", "glu32.dll"};
            WCHAR scan[MAX_PATH];
            WIN32_FIND_DATAW found;
            HANDLE listing = INVALID_HANDLE_VALUE;
            BOOL parsed = FALSE, draws = FALSE, image_parsed = FALSE;
            DWORD read, dir_length = 0, base_length = 0, dlls = 0, pattern = 0;
            static const WCHAR *const patterns[] = {L"", L"bin\\\\"};

            lstrcpynW( scan, app_name, MAX_PATH );
            for (;;)
            {
            HANDLE file = CreateFileW( scan, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                                       NULL, OPEN_EXISTING, 0, NULL );

            parsed = FALSE;
            if (file != INVALID_HANDLE_VALUE)
            {
                IMAGE_DOS_HEADER dos;
                IMAGE_NT_HEADERS32 nt;
                IMAGE_SECTION_HEADER sections[96];
                IMAGE_IMPORT_DESCRIPTOR desc;
                DWORD rva, offset = 0, count = 0, i, j, k;

                if (ReadFile( file, &dos, sizeof(dos), &read, NULL ) && read == sizeof(dos) &&
                    dos.e_magic == IMAGE_DOS_SIGNATURE &&
                    SetFilePointer( file, dos.e_lfanew, NULL, FILE_BEGIN ) != INVALID_SET_FILE_POINTER &&
                    ReadFile( file, &nt, sizeof(nt), &read, NULL ) && read == sizeof(nt) &&
                    nt.Signature == IMAGE_NT_SIGNATURE && nt.OptionalHeader.Magic == IMAGE_NT_OPTIONAL_HDR32_MAGIC &&
                    nt.FileHeader.NumberOfSections <= ARRAY_SIZE(sections) &&
                    SetFilePointer( file, dos.e_lfanew + FIELD_OFFSET( IMAGE_NT_HEADERS32, OptionalHeader ) +
                                    nt.FileHeader.SizeOfOptionalHeader, NULL, FILE_BEGIN ) != INVALID_SET_FILE_POINTER &&
                    ReadFile( file, sections, nt.FileHeader.NumberOfSections * sizeof(sections[0]), &read, NULL ) &&
                    read == nt.FileHeader.NumberOfSections * sizeof(sections[0]))
                {
                    count = nt.FileHeader.NumberOfSections;
                    rva = nt.OptionalHeader.NumberOfRvaAndSizes > IMAGE_DIRECTORY_ENTRY_IMPORT ?
                          nt.OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress : 0;
                    parsed = TRUE;   /* no import table: imports nothing */
                    for (i = 0; rva && i < count; i++)
                        if (rva >= sections[i].VirtualAddress &&
                            rva < sections[i].VirtualAddress + max( sections[i].Misc.VirtualSize, sections[i].SizeOfRawData ))
                            offset = rva - sections[i].VirtualAddress + sections[i].PointerToRawData;
                    if (rva && !offset) parsed = FALSE;
                    for (j = 0; offset && j < 256 && !draws; j++)
                    {
                        char name[32];
                        DWORD name_offset = 0;

                        if (SetFilePointer( file, offset + j * sizeof(desc), NULL, FILE_BEGIN ) == INVALID_SET_FILE_POINTER ||
                            !ReadFile( file, &desc, sizeof(desc), &read, NULL ) || read != sizeof(desc))
                        {
                            parsed = FALSE;
                            break;
                        }
                        if (!desc.Name) break;
                        for (i = 0; i < count; i++)
                            if (desc.Name >= sections[i].VirtualAddress &&
                                desc.Name < sections[i].VirtualAddress + max( sections[i].Misc.VirtualSize, sections[i].SizeOfRawData ))
                                name_offset = desc.Name - sections[i].VirtualAddress + sections[i].PointerToRawData;
                        if (!name_offset || SetFilePointer( file, name_offset, NULL, FILE_BEGIN ) == INVALID_SET_FILE_POINTER ||
                            !ReadFile( file, name, sizeof(name) - 1, &read, NULL ))
                        {
                            parsed = FALSE;
                            break;
                        }
                        name[min( read, sizeof(name) - 1 )] = 0;
                        for (k = 0; k < ARRAY_SIZE(graphics); k++)
                            if (!lstrcmpiA( name, graphics[k] )) draws = TRUE;
                    }
                }
                CloseHandle( file );
            }
            if (!base_length) image_parsed = parsed;   /* the image itself */
            if (draws || !image_parsed) break;
            if (!base_length)
            {
                WCHAR *slash = wcsrchr( scan, '\\\\' );

                if (!slash || slash - scan + 16 >= MAX_PATH) break;
                base_length = slash - scan + 1;
            }
            /* the next DLL: in the folder, then in its bin folder */
            for (;;)
            {
                BOOL next;

                if (listing == INVALID_HANDLE_VALUE)
                {
                    if (pattern >= ARRAY_SIZE(patterns)) break;
                    lstrcpyW( scan + base_length, patterns[pattern] );
                    dir_length = base_length + lstrlenW( patterns[pattern++] );
                    lstrcpyW( scan + dir_length, L"*.dll" );
                    if ((listing = FindFirstFileW( scan, &found )) == INVALID_HANDLE_VALUE) continue;
                    next = TRUE;
                }
                else next = FindNextFileW( listing, &found );
                if (!next)
                {
                    FindClose( listing );
                    listing = INVALID_HANDLE_VALUE;
                    continue;
                }
                if (!(found.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) && dir_length + lstrlenW( found.cFileName ) < MAX_PATH)
                    break;
            }
            if (listing == INVALID_HANDLE_VALUE || ++dlls > 64) break;
            lstrcpyW( scan + dir_length, found.cFileName );
            }
            if (listing != INVALID_HANDLE_VALUE) FindClose( listing );
            parsed = image_parsed;
            ERR( "PWSEP base_taken started=%s parsed=%d draws=%d folder_dlls=%lu last=%s\\n", debugstr_w(app_name), parsed,
                 draws, dlls, debugstr_w(scan) );
            if (parsed && !draws && ps4_execution_mode( app_name ) == PW_EXEC_AUTO)
            {
                BOOL started;

                ps4_separate_thread = GetCurrentThreadId();
                started = CreateProcessW( app_name, tidy_cmdline, NULL, NULL, inherit, flags, env, cur_dir,
                                          (STARTUPINFOW *)startup_info, info );
                ps4_separate_thread = 0;
                ERR( "PWSEP base_taken helper_to_separate=%d error=%lu image=%s\\n", started, started ? 0 : GetLastError(),
                     debugstr_w(app_name) );
                if (started)
                {
                    ps4_base_taken = FALSE;
                    status = STATUS_SUCCESS;
                    goto done;
                }
                SetLastError( saved );
            }
        }
        /* PoP D.6 (Worms 3D's and Prince of Persia's launchers, user feedback 2026-11-13): before the relaunch
         * prompt, the starter that holds the base moves to a separate process (docs/POP_SEPARATE_PROCESS.md); started
         * there, it hands its program to this title (D.4, D.5), where the base is then free. The choice is kept in
         * AppDefaults, as winecfg's "Procesos separados" writes it, and the starter here ends: the separate one opens
         * its window again. Only for a starter with no execution mode chosen; when the separate start fails, the
         * value is removed and the prompt follows. */
        {
            struct ps4_guest *starter = ps4_guest_current();
            LDR_DATA_TABLE_ENTRY *mod;
            WCHAR starter_path[MAX_PATH], starter_dir[MAX_PATH], starter_cmd[MAX_PATH + 2], key[MAX_PATH + 64];
            WCHAR *starter_base;
            STARTUPINFOW si = {sizeof(si)};
            PROCESS_INFORMATION pi;
            HKEY hkey;

            starter_path[0] = 0;
            if (starter && starter->module && !LdrFindEntryForAddress( starter->module, &mod ) && mod->FullDllName.Buffer &&
                mod->FullDllName.Length / sizeof(WCHAR) < MAX_PATH)
            {
                memcpy( starter_path, mod->FullDllName.Buffer, mod->FullDllName.Length );
                starter_path[mod->FullDllName.Length / sizeof(WCHAR)] = 0;
            }
            starter_base = starter_path[0] ? wcsrchr( starter_path, '\\\\' ) : NULL;
            if (starter_base && ps4_execution_mode( starter_path ) == PW_EXEC_AUTO &&
                (size_t)(starter_base - starter_path) < MAX_PATH)
            {
                memcpy( starter_dir, starter_path, (starter_base - starter_path) * sizeof(WCHAR) );
                starter_dir[starter_base - starter_path] = 0;
                swprintf( key, ARRAY_SIZE(key), L"Software\\\\Wine\\\\AppDefaults\\\\%ls", starter_base + 1 );
                swprintf( starter_cmd, ARRAY_SIZE(starter_cmd), L"\\"%ls\\"", starter_path );
                if (!RegCreateKeyExW( HKEY_CURRENT_USER, key, 0, NULL, 0, KEY_SET_VALUE, NULL, &hkey, NULL ))
                {
                    BOOL moved;

                    RegSetValueExW( hkey, L"OrbisExecutionMode", 0, REG_SZ, (const BYTE *)L"separate", sizeof(L"separate") );
                    /* 04.15 (W303 run-0198, run-0199: Prince of Persia's launcher, moved from here, ended the title
                     * within 2 s of separate_request, before the server's periodic save (5 s, W190); the value was
                     * lost, so every start repeated this move instead of opening the launcher separately at once, as
                     * run-0115 did): the choice is on disk before the separate start (flush_key, W190) */
                    RegFlushKey( hkey );
                    moved = CreateProcessW( starter_path, starter_cmd, NULL, NULL, FALSE, 0, NULL, starter_dir, &si, &pi );
                    ERR( "PWSEP base_taken starter=%s to_separate=%d error=%lu image=%s\\n", debugstr_w(starter_path), moved,
                         moved ? 0 : GetLastError(), debugstr_w(app_name) );
                    if (!moved)
                    {
                        RegDeleteValueW( hkey, L"OrbisExecutionMode" );
                        RegFlushKey( hkey );
                    }
                    RegCloseKey( hkey );
                    if (moved)
                    {
                        CloseHandle( pi.hThread );
                        CloseHandle( pi.hProcess );
                        RtlExitUserProcess( 0 );   /* this guest alone ends (W196), as ExitProcess */
                    }
                    SetLastError( saved );
                }
            }
        }
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
            if (!pe32 && ps4_runs_alone( app_name )) alone = TRUE;
        }
#ifdef _WIN64
        /* W235 (pe32-en-explorer-plan.md P7): a PE32 runs as a guest of explorer's 32-bit world. The
         * relaunch stays for programs marked to run alone (OrbisRunsAlone), for every PE32 while
         * C:\\\\orbis\\\\pe32relaunch.txt exists, and when the world fails (the dialog says why) */
        if (pe32 && !ps4_runs_alone( app_name ) && !ps4_pe32_relaunch_forced())
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
        if (ps4_execution_mode( app_name ) == PW_EXEC_GUEST)
        {
            ERR( "PWOPEN desktop_mode_no_relaunch image=%s\\n", debugstr_w(app_name) );
            status = STATUS_NOT_SUPPORTED;
            goto done;
        }
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
            const WCHAR *ext = wcsrchr( name, '.' );

            /* Batch files (hardware 2026-11-13, NFS Most Wanted's .bat files from the desktop): a batch file runs
             * through cmd.exe, as CreateProcess does on Windows (Wine's create_cmd_process, which this guest path
             * never reaches); explorer's ShellExecute hands .bat and .cmd to CreateProcess as executables. cmd.exe
             * runs as a console guest (W056/W062). */
            if (ext && (!wcsicmp( ext, L".bat" ) || !wcsicmp( ext, L".cmd" )))
            {
                const WCHAR *what = tidy_cmdline ? tidy_cmdline : app_name;
                SIZE_T length = lstrlenW( what ) + 64;
                WCHAR *batch = HeapAlloc( GetProcessHeap(), 0, length * sizeof(WCHAR) ), dir[MAX_PATH];
                const WCHAR *slash = wcsrchr( app_name, '\\\\' );
                BOOL ok = FALSE;

                if (!cur_dir && slash && slash - app_name < MAX_PATH)
                {
                    memcpy( dir, app_name, (slash - app_name) * sizeof(WCHAR) );
                    dir[slash - app_name] = 0;
                }
                else dir[0] = 0;
                if (batch)
                {
                    swprintf( batch, length, L"C:\\\\windows\\\\system32\\\\cmd.exe /s /c \\"%ls\\"", what );
                    ok = CreateProcessInternalW( token, NULL, batch, process_attr, thread_attr, inherit, flags, env,
                                                 cur_dir ? cur_dir : dir[0] ? dir : NULL, startup_info, info, NULL );
                    ERR( "PWOPEN batch image=%s command=%s ok=%d error=%lu\\n", debugstr_w(app_name), debugstr_w(batch), ok,
                         ok ? 0 : GetLastError() );
                    HeapFree( GetProcessHeap(), 0, batch );
                }
                if (ok)
                {
                    status = STATUS_SUCCESS;
                    goto done;
                }
            }
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
    static DWORD ps4_separate_thread;  /* PoP D.7: this thread's next start runs in a separate process */

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
# PoP D.6: a guest's named mutexes and events, closed when it exits (ps4_guest_close_files)
revise('kernelbase','sync','#include "kernelbase.h"','#include "kernelbase.h"\n#include "ps4_guest.h"','Guest state.')
for name, inner, args in (('CreateEventA', 'CreateEventExA', 'sa, name, flags, EVENT_ALL_ACCESS'),
                          ('CreateEventW', 'CreateEventExW', 'sa, name, flags, EVENT_ALL_ACCESS'),
                          ('CreateMutexA', 'CreateMutexExA', 'sa, name, owner ? CREATE_MUTEX_INITIAL_OWNER : 0, MUTEX_ALL_ACCESS'),
                          ('CreateMutexW', 'CreateMutexExW', 'sa, name, owner ? CREATE_MUTEX_INITIAL_OWNER : 0, MUTEX_ALL_ACCESS')):
    revise('kernelbase','sync','    return %s( %s );\n}' % (inner, args),
           '    HANDLE ret = %s( %s );\n\n    if (name && ps4_guest_current()) ps4_guest_object_made( ret, __builtin_return_address( 0 ) );  /* PoP D.6 */\n    return ret;\n}' % (inner, args),
           'Record the named objects a guest makes (%s).' % name)
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

/* PoP D.6 (Prince of Persia's launcher, ended here and started again in a separate process, found its
 * POP_Launcher mutex still there and said the game was running): a guest's named mutexes and events are closed
 * when it exits too. Known by the hash of their name; the bit 62 tells them from a file index. */
#define PS4_GUEST_OBJECT_INDEX (1LL << 62)
static BOOL ps4_guest_object_index( HANDLE handle, LONGLONG *index )
{
    char buffer[sizeof(OBJECT_NAME_INFORMATION) + MAX_PATH * sizeof(WCHAR)];
    OBJECT_NAME_INFORMATION *info = (OBJECT_NAME_INFORMATION *)buffer;
    ULONGLONG hash = 0xcbf29ce484222325ULL;
    ULONG i, length;

    if (NtQueryObject( handle, ObjectNameInformation, info, sizeof(buffer), NULL ) || !info->Name.Length) return FALSE;
    for (i = 0, length = info->Name.Length / sizeof(WCHAR); i < length; i++)
    {
        hash ^= info->Name.Buffer[i];
        hash *= 0x100000001b3ULL;
    }
    *index = (LONGLONG)(hash & (PS4_GUEST_OBJECT_INDEX - 1)) | PS4_GUEST_OBJECT_INDEX;
    return TRUE;
}

static void ps4_guest_handle_add( struct ps4_guest *guest, HANDLE handle, LONGLONG index );

void ps4_guest_object_made( HANDLE handle, void *caller )
{
    struct ps4_guest *guest = ps4_guest_current();
    DWORD error = GetLastError();  /* ERROR_ALREADY_EXISTS stays for the caller */
    LONGLONG index;

    if (handle && guest && ps4_guest_own_code( caller ) && ps4_guest_object_index( handle, &index ))
        ps4_guest_handle_add( guest, handle, index );
    SetLastError( error );
}

void ps4_guest_file_opened( HANDLE handle, void *caller )
{
    struct ps4_guest *guest = ps4_guest_current();
    LONGLONG index;

    if (!guest || !ps4_guest_own_code( caller ) || !ps4_guest_file_index( handle, &index )) return;
    ps4_guest_handle_add( guest, handle, index );
}

static void ps4_guest_handle_add( struct ps4_guest *guest, HANDLE handle, LONGLONG index )
{
    static BOOL full_reported;

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
        BOOL object = (guest->files[i].index & PS4_GUEST_OBJECT_INDEX) != 0;  /* PoP D.6 */

        if (!(object ? ps4_guest_object_index( guest->files[i].handle, &index )
                     : ps4_guest_file_index( guest->files[i].handle, &index )) || index != guest->files[i].index ||
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
static UINT ps4_guest_threads_in( const struct ps4_guest_own *own, UINT own_count, BOOL end )
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
                if (tid == self || !ps4_guest_thread_in( tid, own, own_count )) continue;
                found++;
                if (end)
                {
                    HANDLE thread = OpenThread( THREAD_TERMINATE | SYNCHRONIZE, FALSE, tid );
                    DWORD wait = WAIT_FAILED;
                    if (thread && TerminateThread( thread, 0 )) wait = WaitForSingleObject( thread, 1000 );
                    if (ps4_pw_traced()) ERR( "PWGUEST ended: thread %04lx wait=%lu\\n", tid, wait );
                    if (thread) CloseHandle( thread );
                }
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

        if (!ps4_guest_outside_windows( &mod->FullDllName )) continue;
        if (mod->LoadCount == -1 && leftovers) continue;  /* d13: a pinned one only with its guest */
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
    /* 04.29 (run-0246: Doom 3, terminated, has no DLLs of its own, and its 79 MB heap and large blocks stayed): with
     * none, its heaps and the memory its code reserved are still released */
    if (!own_count) goto memory;

    threads = ps4_guest_threads_in( own, own_count, FALSE );
    /* run-0065 (MangoJuice did not start a second time): a thread of the ended guest's own DLLs that the guest
     * did not create through CreateThread (GIO's work on a thread of ntdll's pool) kept GLib loaded, and the
     * next start ran on that GLib's state and showed no window. The guest has ended, and its process would
     * take every thread with it on Windows: those threads end too, while the loader lock is held here, so
     * none of them owns it (W122), and the modules are counted again */
    if (threads && threads != ~0u && !trace_only)
    {
        ULONG lock_state = 0;
        ULONG_PTR end_magic = 0;
        int tries;

        for (tries = 0; tries < 100; tries++)
        {
            if (!LdrLockLoaderLock( 2 /* LDR_LOCK_LOADER_LOCK_FLAG_TRY_ONLY */, &lock_state, &end_magic ) &&
                lock_state == 1) break;
            Sleep( 10 );
        }
        if (lock_state == 1)
        {
            UINT ended = ps4_guest_threads_in( own, own_count, TRUE );
            LdrUnlockLoaderLock( 0, end_magic );
            threads = ps4_guest_threads_in( own, own_count, FALSE );
            ERR( "PWGUEST own_modules module=%p ended %u threads in their code, %u left\\n",
                 guest->module, ended == ~0u ? 0 : ended, threads == ~0u ? 0 : threads );
        }
        else ERR( "PWGUEST own_modules module=%p threads not ended: the loader lock is busy\\n", guest->module );
    }
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
                {
                    mod->Flags &= ~LDR_PROCESS_ATTACHED;
                    /* d13 (run-0076: MangoJuice's second start ended at once with c000001d): GIO pins
                     * itself, so it outlived the program, and with it the first start's GApplication type
                     * and class, whose property specs pointed into the freed libgobject; the next start
                     * jumped there. A module of the program's own that it pinned ends with it, as its
                     * process would */
                    if (mod->LoadCount == -1)
                    {
                        ERR( "PWGUEST own %s was pinned by the program: unpinned\\n",
                             debugstr_w( mod->BaseDllName.Buffer ) );
                        mod->LoadCount = 1;
                    }
                }
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

memory:
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
#ifdef __x86_64__
            /* d11 (run-0074: MangoJuice's second start ended with c000001d in the middle of an instruction of the
             * first start's libgobject, and nothing said who jumped there): where the address, the argument
             * registers and the return addresses on the stack are */
            {
                CONTEXT *ctx = epointers->ContextRecord;
                ULONG_PTR *sp = (ULONG_PTR *)ctx->Rsp;
                void *regs[8] = { rec->ExceptionAddress, (void *)ctx->Rax, (void *)ctx->Rcx, (void *)ctx->Rdx,
                                  (void *)ctx->R8, (void *)ctx->R9, (void *)ctx->R10, (void *)ctx->R11 };
                static const char * const names[8] = { "pc", "rax", "rcx", "rdx", "r8", "r9", "r10", "r11" };
                LDR_DATA_TABLE_ENTRY *mod;
                MEMORY_BASIC_INFORMATION info;
                unsigned int i, shown = 0;

                for (i = 0; i < 8; i++)
                    if (!LdrFindEntryForAddress( regs[i], &mod ) && mod->BaseDllName.Buffer)
                        ERR( "PWGUEST fault %s=%p %s+%lx\\n", names[i], regs[i], debugstr_w(mod->BaseDllName.Buffer),
                             (ULONG)((char *)regs[i] - (char *)mod->DllBase) );
                if (VirtualQuery( rec->ExceptionAddress, &info, sizeof(info) ))
                    ERR( "PWGUEST fault pc region=%p allocation=%p size=%lx state=%lx type=%lx protect=%lx\\n",
                         info.BaseAddress, info.AllocationBase, (ULONG)info.RegionSize, info.State, info.Type,
                         info.Protect );
                for (i = 0; i < 96 && shown < 16; i++)
                {
                    if (LdrFindEntryForAddress( (void *)sp[i], &mod ) || !mod->BaseDllName.Buffer) continue;
                    ERR( "PWGUEST fault stack[%u]=%p %s+%lx\\n", i, (void *)sp[i], debugstr_w(mod->BaseDllName.Buffer),
                         (ULONG)((char *)sp[i] - (char *)mod->DllBase) );
                    shown++;
                }
            }
#endif
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
# Wine Mono (2026-11-16, run-0172): an IL-only .NET EXE (PES 2014's settings.exe) starts at mscoree's _CorExeMain,
# which ntdll's fixup_imports_ilonly puts in the loader entry; its header entry jumps through an import table the
# loader never binds for such an image, and the guest faulted at its first instruction (c0000005 at the RVA 0x1359e0).
revise('kernelbase','process','''    ps4_guest_pad_profile( app_name, TRUE );  /* W213 */''','''    ps4_guest_pad_profile( app_name, TRUE );  /* W213 */
    if (nt->OptionalHeader.NumberOfRvaAndSizes > IMAGE_DIRECTORY_ENTRY_COM_DESCRIPTOR &&
        nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_COM_DESCRIPTOR].VirtualAddress)
    {
        LDR_DATA_TABLE_ENTRY *ldr;

        if (!LdrFindEntryForAddress( guest->module, &ldr ) && ldr->EntryPoint)
        {
            if (ps4_pw_traced()) ERR( "PWGUEST ilonly entry %p -> %p (loader entry) app=%s\\n", guest->entry, ldr->EntryPoint,
                 debugstr_w(app_name) );
            guest->entry = ldr->EntryPoint;
        }
    }''','A .NET EXE starts at the loader entry, mscoree\'s _CorExeMain (Wine Mono).')
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
    if (ps4_pw_traced()) ERR( "PWOVERLAY mangohud in_front=%d window=%p presented=%p guest64=%d loaded=%d loaded32=%d\\n", hud, hwnd,
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

# 04.26 (04.25 run-0233/0234: DOOM3.exe, "Unhandled page fault on read access to 04C7E02C at address 7BEE23C1",
# ntdll32 at 0x7be90000, so alloc_tls_slot reading teb->ThreadLocalStoragePointer): a module with static TLS
# gives its TLS block to every thread of the process, found with NtGetNextThread. In explorer's process most
# threads are 64-bit only. For them, wow64's ThreadBasicInformation answers the 64-bit TEB + 0x2000 cut to 32
# bits, which is unmapped memory or not a TEB at all when that TEB lies above 4 GiB. Only a TEB that is committed,
# writable and points to itself (Tib.Self, set by ntdll Unix init_teb for every 32-bit TEB) gets the block; the
# others cannot run 32-bit code, so they need none. One PWWOW line counts the threads left out.
revise('ntdll','loader','''static BOOL alloc_tls_slot( LDR_DATA_TABLE_ENTRY *mod )
{''','''#ifndef _WIN64
/* PS4 hardware build (04.26): a 32-bit TEB of explorer's 32-bit world, not a 64-bit-only thread's address */
static BOOL ps4_world_teb( const TEB *teb )
{
    MEMORY_BASIC_INFORMATION info;

    if (NtQueryVirtualMemory( GetCurrentProcess(), teb, MemoryBasicInformation, &info, sizeof(info), NULL ) ||
        info.State != MEM_COMMIT || (info.Protect & (PAGE_GUARD | PAGE_NOACCESS)) ||
        !(info.Protect & (PAGE_READWRITE | PAGE_EXECUTE_READWRITE)) ||
        (const char *)info.BaseAddress + info.RegionSize < (const char *)(teb + 1))
        return FALSE;
    return teb->Tib.Self == &teb->Tib;
}
#endif

static BOOL alloc_tls_slot( LDR_DATA_TABLE_ENTRY *mod )
{''',"Only 32-bit TEBs get a module's TLS block (04.26).")
revise('ntdll','loader','''    HANDLE thread = NULL, next;

    if (!(dir = RtlImageDirectoryEntryToData( mod->DllBase, TRUE, IMAGE_DIRECTORY_ENTRY_TLS, &size )))''','''    HANDLE thread = NULL, next;
#ifndef _WIN64
    UINT ps4_skipped = 0;  /* 04.26 */
#endif

    if (!(dir = RtlImageDirectoryEntryToData( mod->DllBase, TRUE, IMAGE_DIRECTORY_ENTRY_TLS, &size )))''',
       "Only 32-bit TEBs get a module's TLS block (04.26).")
revise('ntdll','loader','''        teb = tbi.TebBaseAddress;
        if (!teb->ThreadLocalStoragePointer)''','''        teb = tbi.TebBaseAddress;
#ifndef _WIN64
        if (!ps4_world_teb( teb ))  /* 04.26: a 64-bit-only thread of explorer's process */
        {
            ps4_skipped++;
            continue;
        }
#endif
        if (!teb->ThreadLocalStoragePointer)''',"Only 32-bit TEBs get a module's TLS block (04.26).")
revise('ntdll','loader','''    if (thread) NtClose( thread );

#ifndef _WIN64
    if (!ps4_guest_image_check( mod, dir )) return FALSE;  /* W244 */''','''    if (thread) NtClose( thread );

#ifndef _WIN64
    if (ps4_skipped)
        ERR( "PWWOW tls_slot module %s slot %lu: %u threads without a 32-bit TEB left out\\n",
             debugstr_w(mod->BaseDllName.Buffer), i, ps4_skipped );
    if (!ps4_guest_image_check( mod, dir )) return FALSE;  /* W244 */''',"Only 32-bit TEBs get a module's TLS block (04.26).")

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
#define PS4_ENUM_REGISTRY_SETTINGS ((DWORD)-2)
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
    DEVMODEW now = {.dmSize = sizeof(now)}, back = {.dmSize = sizeof(back)}, desktop = {.dmSize = sizeof(desktop)};
    WCHAR path[MAX_PATH];
    struct ps4_guest *newer = NULL;
    LONG ret;
    UINT i;

    if (!guest->mode_width || !settings || !change || !settings( NULL, PS4_ENUM_CURRENT_SETTINGS, &now )) return;
    if (now.dmPelsWidth == guest->mode_width && now.dmPelsHeight == guest->mode_height) return;
    if (!GetModuleFileNameW( guest->module, path, ARRAY_SIZE(path) )) path[0] = 0;
    /* W303 run-0206: WFM started while Prince of Persia had 800x600 set and, ending after it, set 800x600 back on
     * the desktop. Only a guest that started at the desktop's mode sets one back; the 64-bit and 32-bit worlds keep
     * separate guest lists, so the newer-guest check below cannot see the other world's game. */
    if (settings( NULL, PS4_ENUM_REGISTRY_SETTINGS, &desktop ) &&
        (desktop.dmPelsWidth != guest->mode_width || desktop.dmPelsHeight != guest->mode_height))
    {
        ERR( "PWSINK mode kept guest=%s %lux%lu: it started at %lux%lu, not the desktop's %lux%lu\\n", debugstr_w(path),
             now.dmPelsWidth, now.dmPelsHeight, guest->mode_width, guest->mode_height, desktop.dmPelsWidth,
             desktop.dmPelsHeight );
        return;
    }
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
# 04.19 (run-0218: SeaMonkey's second start ended in Gecko's crash reporter 4 s in, with no PWFAULT, no MozCrashReason
# and a 0-byte minidump; so not an access violation): the fatal codes a program's own handler takes are traced too.
revise('kernelbase','process','''    if ((rec->ExceptionCode != EXCEPTION_ACCESS_VIOLATION && !fp) || !ps4_guest_current()) return EXCEPTION_CONTINUE_SEARCH;
''','''    /* 04.19: fast fail (abort, /GS, ucrt's invalid parameter), illegal or privileged instruction, stack overflow,
     * heap corruption, assertion failure, breakpoint; for a fast fail access= is its FAST_FAIL code */
    BOOL fatal = rec->ExceptionCode == 0xc0000409 || rec->ExceptionCode == 0xc000001d || rec->ExceptionCode == 0xc0000096 ||
                 rec->ExceptionCode == 0xc00000fd || rec->ExceptionCode == 0xc0000374 || rec->ExceptionCode == 0xc0000420 ||
                 rec->ExceptionCode == 0x80000003 || rec->ExceptionCode == 0xc0000417;  /* 04.20: ucrt, no handler */
    if ((rec->ExceptionCode != EXCEPTION_ACCESS_VIOLATION && !fp && !fatal) || !ps4_guest_current())
        return EXCEPTION_CONTINUE_SEARCH;
''','The fatal codes a program\'s own handler takes are traced (04.19).')
# 04.30 (run-0243, run-0255: when PES 2013's settings.exe ended, 2-3 of its threads kept running, because the title
# cannot signal a thread ("thread_signal unavailable"). TerminateThread ended them in the server only. Each later ran
# into its unloaded EXE, faulted at 0x43f510 eight times (the whole PWFAULT budget) until its stack overflowed, and in
# both runs the title then ended with no line, when joy.cpl was opened). A thread the server already ended stops at its
# next server call (W064). So an access violation outside every module and in memory that is not committed, on a
# thread whose guest is no longer live, makes one server call: a thread the server ended goes there, a live one returns
# and its handlers run as before. The guest's pointer is only compared with the live ones, never read: it is freed.
revise('kernelbase','process','''/* at the end of a guest's unload */
static void ps4_guest_live_remove( struct ps4_guest *guest )
{''','''/* 04.30: has this guest ended? Its pointer is compared, never read (an ended guest's memory is freed) */
static BOOL ps4_guest_gone( const struct ps4_guest *guest )
{
    BOOL live = FALSE, full;
    UINT i;

    RtlAcquireSRWLockShared( &ps4_live_lock );
    for (i = 0; i < ps4_live_count && !live; i++) live = ps4_live_guests[i] == guest;
    full = ps4_live_count >= ARRAY_SIZE(ps4_live_guests);  /* a full list does not say who ended */
    RtlReleaseSRWLockShared( &ps4_live_lock );
    return guest && !live && !full;
}

/* at the end of a guest's unload */
static void ps4_guest_live_remove( struct ps4_guest *guest )
{''','04.30: whether a guest has ended.')
revise('kernelbase','process','''static LONG CALLBACK ps4_guest_fault_trace( EXCEPTION_POINTERS *ptrs )
{''','''static BOOL ps4_guest_gone( const struct ps4_guest *guest );  /* 04.30 */

static LONG CALLBACK ps4_guest_fault_trace( EXCEPTION_POINTERS *ptrs )
{''','04.30: declared before the fault trace.')
revise('kernelbase','process','''    if ((rec->ExceptionCode != EXCEPTION_ACCESS_VIOLATION && !fp && !fatal) || !ps4_guest_current())
        return EXCEPTION_CONTINUE_SEARCH;
''','''    if ((rec->ExceptionCode != EXCEPTION_ACCESS_VIOLATION && !fp && !fatal) || !ps4_guest_current())
        return EXCEPTION_CONTINUE_SEARCH;
    /* 04.30: a thread of an ended guest, running where that guest's code was */
    if (rec->ExceptionCode == EXCEPTION_ACCESS_VIOLATION && ps4_guest_gone( ps4_guest_current() ))
    {
        static LONG leftovers;
        LDR_DATA_TABLE_ENTRY *mod;
        MEMORY_BASIC_INFORMATION info;
        THREAD_BASIC_INFORMATION basic = {0};
        NTSTATUS query;
        LONG k;

        if (LdrFindEntryForAddress( rec->ExceptionAddress, &mod ) &&
            (!VirtualQuery( rec->ExceptionAddress, &info, sizeof(info) ) || info.State != MEM_COMMIT))
        {
            if ((k = InterlockedIncrement( &leftovers )) <= 16)
                ERR( "PWGUEST leftover thread %04lx of ended guest %p faults at %p: a server call ends it\\n",
                     GetCurrentThreadId(), ps4_guest_current(), rec->ExceptionAddress );
            query = NtQueryInformationThread( GetCurrentThread(), ThreadBasicInformation, &basic, sizeof(basic), NULL );
            if (k <= 16)
                ERR( "PWGUEST leftover thread %04lx still runs (query %#lx, exit status %#lx): its handlers run\\n",
                     GetCurrentThreadId(), query, basic.ExitStatus );
        }
    }
''','04.30: a thread of an ended guest that faults in freed memory makes a server call, which ends it if the server did.')

# 04.20 (run-0222: SeaMonkey's second start, with GPU compositing, again ended in Gecko's crash reporter, from its
# Compositor thread (0x298) during Mesa's WGL setup, with no PWFAULT for any traced code). Gecko's crash reporter also
# takes three ucrt paths that raise no exception: the invalid parameter handler, the pure virtual call handler and
# abort's SIGABRT handler. ucrtbase is shared by every guest, Mesa and MangoHud. Each of these paths is traced on a guest
# thread with its frames, the first 8 of the title. Read only.
revise('ucrtbase','errno','''void __cdecl _invalid_parameter(const wchar_t *expr, const wchar_t *func,
                                       const wchar_t *file, unsigned int line, uintptr_t arg)
{
''','''/* 04.20 (run-0222): the frames of a ucrt path that ends in a program's own handler (04.22: on any thread;
 * TEB.UserReserved[0] is kernelbase's ps4_guest) */
void pw_crt_fatal_trace( const char *what, const void *handler )
{
    static LONG traced;
    void *frames[12], *start = NULL;
    LDR_DATA_TABLE_ENTRY *mod;
    USHORT count, i;

    /* 04.22 (run-0223: no PWCRT line, on any guest thread): these handlers are the process's, so a thread of another
     * program, of Mesa or MangoHud, or of explorer reaches a program's own handler too. Every thread, where a handler
     * is set, and abort; with the thread's guest and start. */
    if ((!handler && what[0] != 'a') || InterlockedIncrement( &traced ) > 8) return;
    NtQueryInformationThread( GetCurrentThread(), ThreadQuerySetWin32StartAddress, &start, sizeof(start), NULL );
    count = RtlCaptureStackBackTrace( 1, ARRAY_SIZE(frames), frames, NULL );
    if (!LdrFindEntryForAddress( start, &mod ) && mod->BaseDllName.Buffer)
        ERR( "PWCRT %s thread=%04lx guest=%p start=%s+%Ix handler=%p frames=%u\\n", what,
             HandleToULong( NtCurrentTeb()->ClientId.UniqueThread ), *(void **)NtCurrentTeb()->UserReserved,
             debugstr_w( mod->BaseDllName.Buffer ), (ULONG_PTR)start - (ULONG_PTR)mod->DllBase, handler, count );
    else
        ERR( "PWCRT %s thread=%04lx guest=%p start=%p handler=%p frames=%u\\n", what,
             HandleToULong( NtCurrentTeb()->ClientId.UniqueThread ), *(void **)NtCurrentTeb()->UserReserved, start, handler, count );
    for (i = 0; i < count; i++)
    {
        if (!LdrFindEntryForAddress( frames[i], &mod ) && mod->BaseDllName.Buffer)
            ERR( "PWCRT %s frame %u %s+%Ix\\n", what, i, debugstr_w( mod->BaseDllName.Buffer ),
                 (ULONG_PTR)frames[i] - (ULONG_PTR)mod->DllBase );
        else
            ERR( "PWCRT %s frame %u %p\\n", what, i, frames[i] );
    }
}

void __cdecl _invalid_parameter(const wchar_t *expr, const wchar_t *func,
                                       const wchar_t *file, unsigned int line, uintptr_t arg)
{
''','The frames of a ucrt path that ends in a program\'s own handler (04.20).','dlls/msvcrt/errno.c')
revise('ucrtbase','errno','''#if _MSVCR_VER >= 140
    thread_data_t *data = msvcrt_get_thread_data();

    if (data->invalid_parameter_handler)
''','''#if _MSVCR_VER >= 140
    thread_data_t *data = msvcrt_get_thread_data();

    pw_crt_fatal_trace( "invalid_parameter", data->invalid_parameter_handler ?  /* 04.20 */
                        (const void *)data->invalid_parameter_handler : (const void *)invalid_parameter_handler );
    if (data->invalid_parameter_handler)
''','An invalid parameter on a guest thread is traced (04.20).','dlls/msvcrt/errno.c')
revise('ucrtbase','exit','''void CDECL abort(void)
{
  TRACE("()\\n");
''','''void pw_crt_fatal_trace( const char *what, const void *handler );  /* errno.c, 04.20 */

void CDECL abort(void)
{
  TRACE("()\\n");
  pw_crt_fatal_trace( "abort", NULL );
''','abort on a guest thread is traced (04.20).','dlls/msvcrt/exit.c')
revise('ucrtbase','exit','''_purecall_handler CDECL _get_purecall_handler(void)
{
    TRACE("\\n");
''','''_purecall_handler CDECL _get_purecall_handler(void)
{
    TRACE("\\n");
    /* 04.20: vcruntime's _purecall asks for the handler before calling it */
    pw_crt_fatal_trace( "purecall", purecall_handler );
''','A pure virtual call on a guest thread is traced (04.20).','dlls/msvcrt/exit.c')
revise('ucrtbase','exit','''void CDECL _purecall(void)
{
  TRACE("(void)\\n");
''','''void CDECL _purecall(void)
{
  TRACE("(void)\\n");
  pw_crt_fatal_trace( "purecall", purecall_handler );
''','A pure virtual call on a guest thread is traced (04.20).','dlls/msvcrt/exit.c')

# 04.22 (run-0223: SeaMonkey's second start, GPU compositing on, ended in Gecko's crash reporter 3 s in, before any WGL
# call, with no PWFAULT and no PWCRT; so no guest thread took a traced exception or a ucrt path).
# 1. A guest's exit waited for none of its other threads past 64: WaitForMultipleObjects takes at most 64 handles
#    (MAXIMUM_WAIT_OBJECTS) and failed at once ("other_threads_wait=4294967295", SeaMonkey 103 and 69 threads, every
#    run of a guest past 64 threads in the archive). The wait goes 64 at a time, within the same 2 s.
# 2. The start of each of the exiting guest's threads, by id, so that the server's "thread_signal unavailable thread=…"
#    line (run-0223: 0188, a thread that could not be signalled and so was not ended) names its code. Read only.
# 3. kernelbase's top-level filter is the process's: the program that set it last takes every thread's unhandled
#    exception, its own or not. What reaches it is traced, on every thread, before it is called. Read only.
revise('kernelbase','process','''/* ExitProcess from a guest thread (ntdll RtlExitUserProcess): end the guest's other
 * threads, then this one; their windows go with them. */''','''/* 04.22 (run-0223): the start of each of a guest's threads but this one, by id, six to a line. Read only. */
static void ps4_guest_thread_starts( struct ps4_guest *guest, DWORD self )
{
    char line[640], where[96];
    UINT i, len = 0, listed = 0;

    for (i = 0; i < guest->thread_count; i++)
    {
        DWORD id = GetThreadId( guest->threads[i] );
        void *start = NULL;

        if (id == self) continue;
        NtQueryInformationThread( guest->threads[i], ThreadQuerySetWin32StartAddress, &start, sizeof(start), NULL );
        len += snprintf( line + len, sizeof(line) - len, " %04lx=%s", id,
                         ps4_guest_where( (ULONG_PTR)start, where, sizeof(where) ) );
        if (++listed % 6 == 0)
        {
            ERR( "PWGUEST thread_starts module=%p%s\\n", guest->module, line );
            len = 0;
        }
    }
    if (len && ps4_pw_traced()) ERR( "PWGUEST thread_starts module=%p%s\\n", guest->module, line );
}

/* ExitProcess from a guest thread (ntdll RtlExitUserProcess): end the guest's other
 * threads, then this one; their windows go with them. */''','The start of each thread of an exiting guest is traced (04.22).')
revise('kernelbase','process','''    RtlEnterCriticalSection( &guest->lock );
    for (i = 0; i < guest->thread_count; i++)
        if (GetThreadId( guest->threads[i] ) != self)
        {
            TerminateThread( guest->threads[i], status );''','''    RtlEnterCriticalSection( &guest->lock );
    ps4_guest_thread_starts( guest, self );  /* 04.22 */
    for (i = 0; i < guest->thread_count; i++)
        if (GetThreadId( guest->threads[i] ) != self)
        {
            TerminateThread( guest->threads[i], status );''','The start of each thread of an exiting guest is traced (04.22).')
revise('kernelbase','process','''        DWORD wait = WaitForMultipleObjects( other_count, others, TRUE, 2000 );
''','''        /* 04.22: WaitForMultipleObjects takes at most 64 handles; past them it failed and nothing was waited for */
        DWORD wait = WAIT_OBJECT_0, begin = GetTickCount(), spent;
        UINT first;

        for (first = 0; first < other_count && wait == WAIT_OBJECT_0; first += 64)
        {
            spent = GetTickCount() - begin;
            wait = WaitForMultipleObjects( min( other_count - first, 64 ), others + first, TRUE,
                                           spent < 2000 ? 2000 - spent : 0 );
        }
''','A guest\'s exit waits for its other threads 64 at a time (04.22).')
revise('kernelbase','debug','''LONG WINAPI UnhandledExceptionFilter( EXCEPTION_POINTERS *epointers )
{''','''/* 04.22 (run-0223): what reaches the process's top-level filter, on any thread, before it is called; the first 8 of
 * the title. Read only. */
static void ps4_top_filter_trace( EXCEPTION_POINTERS *epointers )
{
    static LONG traced;
    const EXCEPTION_RECORD *rec = epointers->ExceptionRecord;
    NT_TIB *tib = &NtCurrentTeb()->Tib;
    LDR_DATA_TABLE_ENTRY *mod;
    ULONG_PTR *sp;
    void *start = NULL, *addrs[3];
    char where[3][96];
    unsigned int i, shown = 0;
    LONG n;

    if ((n = InterlockedIncrement( &traced )) > 8) return;
    NtQueryInformationThread( GetCurrentThread(), ThreadQuerySetWin32StartAddress, &start, sizeof(start), NULL );
    addrs[0] = rec->ExceptionAddress;
    addrs[1] = start;
    addrs[2] = (void *)top_filter;
    for (i = 0; i < 3; i++)
        if (!LdrFindEntryForAddress( addrs[i], &mod ) && mod->BaseDllName.Buffer)
            snprintf( where[i], sizeof(where[i]), "%s+%Ix", debugstr_w( mod->BaseDllName.Buffer ),
                      (ULONG_PTR)addrs[i] - (ULONG_PTR)mod->DllBase );
        else
            snprintf( where[i], sizeof(where[i]), "%p", addrs[i] );
    ERR( "PWTOP n=%ld thread=%04lx guest=%p code=%#lx flags=%#lx address=%s info=%Ix,%Ix start=%s filter=%s\\n", n,
         GetCurrentThreadId(), ps4_guest_current(), rec->ExceptionCode, rec->ExceptionFlags, where[0],
         rec->NumberParameters > 0 ? rec->ExceptionInformation[0] : 0,
         rec->NumberParameters > 1 ? rec->ExceptionInformation[1] : 0, where[1], where[2] );
#ifdef __x86_64__
    sp = (ULONG_PTR *)epointers->ContextRecord->Rsp;
#else
    sp = (ULONG_PTR *)epointers->ContextRecord->Esp;
#endif
    if ((void *)sp < tib->StackLimit || (void *)sp >= tib->StackBase) return;
    for (i = 0; i < 160 && sp + i + 1 <= (ULONG_PTR *)tib->StackBase && shown < 12; i++)
    {
        if (LdrFindEntryForAddress( (void *)sp[i], &mod ) || !mod->BaseDllName.Buffer) continue;
        ERR( "PWTOP n=%ld stack[%u] %s+%Ix\\n", n, i, debugstr_w( mod->BaseDllName.Buffer ),
             sp[i] - (ULONG_PTR)mod->DllBase );
        shown++;
    }
}

LONG WINAPI UnhandledExceptionFilter( EXCEPTION_POINTERS *epointers )
{''','What reaches the top-level filter is traced (04.22).')
revise('kernelbase','debug','''        if (top_filter && !nested)
        {
            LONG ret = top_filter( epointers );
''','''        if (top_filter && !nested)
        {
            LONG ret;

            ps4_top_filter_trace( epointers );  /* 04.22 */
            ret = top_filter( epointers );
''','What reaches the top-level filter is traced (04.22).')
# 04.28 (04.27 on the console, run-0244 and run-0245: SeaMonkey ended with an access violation in nss3.dll+13c67d both
# times, reading inside nssckbi.dll's image after it was unloaded). Opening WFM while SeaMonkey ran swept the leftovers
# of ended guests (W209), and SeaMonkey's own nssckbi.dll went with them ("own L"nssckbi.dll" ... leftovers=1 live=2").
# NSS loads it by its 8.3 path, C:/PROG~FBU/SEAM~E5Z/nssckbi.dll, so its FullDllName did not start with SeaMonkey's
# folder, C:/Program Files/SeaMonkey/, and the module counted as nobody's. Any program whose DLLs load by a short path
# had it, at another program's launch and at another guest's exit. Now a folder or a module path with a "~" is compared
# by its long form too (GetLongPathNameW: ntdll's directory reads, no loader lock).
revise('kernelbase','process','''        lstrcpynW( live_dirs[live_dir_count], mod->FullDllName.Buffer, MAX_PATH );
        if ((slash = wcsrchr( live_dirs[live_dir_count], '\\\\' ))) slash[1] = 0, live_dir_count++;
''','''        lstrcpynW( live_dirs[live_dir_count], mod->FullDllName.Buffer, MAX_PATH );
        if (wcschr( live_dirs[live_dir_count], '~' ))  /* 04.28: a guest started by its 8.3 path */
        {
            WCHAR long_dir[MAX_PATH];
            DWORD len = GetLongPathNameW( live_dirs[live_dir_count], long_dir, ARRAY_SIZE(long_dir) );

            if (len && len < ARRAY_SIZE(long_dir)) lstrcpyW( live_dirs[live_dir_count], long_dir );
        }
        if ((slash = wcsrchr( live_dirs[live_dir_count], '\\\\' ))) slash[1] = 0, live_dir_count++;
''','A live guest started by its 8.3 path keeps its folder in long form (04.28).')
revise('kernelbase','process','''        for (k = 0; k < live_dir_count; k++)
            if (!wcsnicmp( mod->FullDllName.Buffer, live_dirs[k], wcslen( live_dirs[k] ))) break;
''','''        for (k = 0; k < live_dir_count; k++)
            if (!wcsnicmp( mod->FullDllName.Buffer, live_dirs[k], wcslen( live_dirs[k] ))) break;
        if (k == live_dir_count && live_dir_count && wcschr( mod->FullDllName.Buffer, '~' ))
        {
            /* 04.28 (run-0244: NSS loads nssckbi.dll by its 8.3 path): a module loaded by its 8.3 path is in a live
             * guest's folder by its long path */
            WCHAR long_name[MAX_PATH];
            DWORD len = GetLongPathNameW( mod->FullDllName.Buffer, long_name, ARRAY_SIZE(long_name) );

            if (len && len < ARRAY_SIZE(long_name))
                for (k = 0; k < live_dir_count; k++)
                    if (!wcsnicmp( long_name, live_dirs[k], wcslen( live_dirs[k] ) )) break;
            if (k < live_dir_count)
                ERR( "PWGUEST own %s: by its 8.3 path in a live guest's folder, %s\\n", debugstr_w( mod->FullDllName.Buffer ),
                     debugstr_w( long_name ) );
        }
''','A module loaded by its 8.3 path counts in the folder of a live guest (04.28).')

# 04.26 (2026-11-18, the user's decision after run-0234): MangoHud is never shown for seamonkey.exe. A program on this
# list gets no MangoHud layer: the Vulkan loader (vulkan-1.dll, tools/vk-h0/build-vulkan-loader.sh) reads the layer's
# disable_environment, DISABLE_MANGOHUD (MangoHud.x86_64.json), with GetEnvironmentVariableW at each vkCreateInstance,
# and a thread of such a guest reads "1" there. Every guest shares the process environment, so the answer is the
# guest's, not a variable set for all. libMangoHud.dll may already be loaded for another program; the loader then
# leaves it out of this program's chain, so it hooks and draws nothing for it. The closer reports no MangoHud in front
# for it either ("PWOVERLAY mangohud in_front=0 ... excluded=1"), so ESTADISTICAS turns on the overlay's own readout and
# Shift+F12 is not sent. Every other program keeps MangoHud, MangoJuice's settings and the show/hide.
# 04.26 (run-0234, every MangoHud program that stops presenting): the closer counted MangoHud in front only while a
# Vulkan swapchain had presented to the window in front in the last 2 s. A page that does not change presents nothing,
# so with SeaMonkey in front the report went 0 and 1 (window=0x900ba presented=0) and ESTADISTICAS toggled the
# overlay's own readout instead of MangoHud: MangoHud could not be hidden. The window in front keeps the state it had
# while it presented until another window comes in front.
revise('kernelbase','process','''#ifdef _WIN64
/* W242: MangoHud counts for the program in front only (W240: one 64-bit program loaded it, and the''','''/* 04.26: the programs for which MangoHud is never shown (tools/build-guest-hw.py), by the guest EXE's file name */
static BOOL ps4_guest_no_hud( struct ps4_guest *guest )
{
    static const WCHAR *const excluded[] = { L"seamonkey.exe" };
    LDR_DATA_TABLE_ENTRY *mod;
    UINT i;

    if (!guest || !guest->module || LdrFindEntryForAddress( guest->module, &mod ) || !mod->BaseDllName.Buffer)
        return FALSE;
    for (i = 0; i < ARRAY_SIZE(excluded); i++)
        if (!wcsicmp( mod->BaseDllName.Buffer, excluded[i] )) return TRUE;
    return FALSE;
}

#ifdef _WIN64
/* W242: MangoHud counts for the program in front only (W240: one 64-bit program loaded it, and the''','MangoHud is never shown for seamonkey.exe (04.26).')
revise('kernelbase','process','''    HWND hwnd = front ? front() : NULL, presented = NULL;
    const char *at = reply;
    int loaded = ps4_overlay_mangohud_loaded(), guest64 = 0, loaded32, hud;
    static HANDLE hud32;
''','''    HWND hwnd = front ? front() : NULL, presented = NULL;
    const char *at = reply;
    int loaded = ps4_overlay_mangohud_loaded(), guest64 = 0, loaded32, hud, excluded = 0;
    static HANDLE hud32;
    static HWND kept;  /* 04.26: the window in front that presented, while it stays in front */
    struct ps4_guest *guest = NULL;
''','The window in front keeps its MangoHud state while it does not present (04.26).')
revise('kernelbase','process','''    if (presented && owner) guest64 = ps4_overlay_guest_of( owner( hwnd, NULL ) ) != NULL;
    /* W245: a window in front that is not a 64-bit guest's and that Vulkan presents to is a 32-bit guest's:
     * explorer's own windows do not present */
    hud = presented && (guest64 ? loaded : loaded32);
    if (hud == reported) return;
    reported = hud;
    if (ps4_pw_traced()) ERR( "PWOVERLAY mangohud in_front=%d window=%p presented=%p guest64=%d loaded=%d loaded32=%d\\n", hud, hwnd,
         presented, guest64, loaded, loaded32 );''','''    /* 04.26 (run-0234): a page that does not change presents nothing; its window keeps the state it had */
    if (presented) kept = hwnd;
    else if (hwnd && hwnd == kept) presented = hwnd;
    else kept = NULL;
    if (presented && owner) guest64 = (guest = ps4_overlay_guest_of( owner( hwnd, NULL ) )) != NULL;
    excluded = guest && ps4_guest_no_hud( guest );  /* 04.26: no MangoHud for it */
    /* W245: a window in front that is not a 64-bit guest's and that Vulkan presents to is a 32-bit guest's:
     * explorer's own windows do not present */
    hud = presented && !excluded && (guest64 ? loaded : loaded32);
    if (hud == reported) return;
    reported = hud;
    if (ps4_pw_traced()) ERR( "PWOVERLAY mangohud in_front=%d window=%p presented=%p guest64=%d loaded=%d loaded32=%d excluded=%d\\n", hud,
         hwnd, presented, guest64, loaded, loaded32, excluded );''','The window in front keeps its MangoHud state while it does not present (04.26).')
revise('kernelbase','process','''    TRACE( "(%s %p %lu)\\n", debugstr_w(name), val, size );

    RtlInitUnicodeString( &us_name, name );
    us_value.Length = 0;
    us_value.MaximumLength = (size ? size - 1 : 0) * sizeof(WCHAR);
    us_value.Buffer = val;
''','''    TRACE( "(%s %p %lu)\\n", debugstr_w(name), val, size );

    /* 04.26: the Vulkan loader leaves MangoHud's layer out for a guest that never shows it (ps4_guest_no_hud) */
    if (name && !wcsicmp( name, L"DISABLE_MANGOHUD" ) && ps4_guest_no_hud( ps4_guest_or_loading() ))
    {
        static LONG logged;

        if (!InterlockedExchange( &logged, 1 ))
            if (ps4_pw_traced()) ERR( "PWGUEST mangohud excluded module=%p: DISABLE_MANGOHUD=1 for its threads\\n", ps4_guest_or_loading()->module );
        if (size < 2) return 2;
        val[0] = '1';
        val[1] = 0;
        return 1;
    }
    RtlInitUnicodeString( &us_name, name );
    us_value.Length = 0;
    us_value.MaximumLength = (size ? size - 1 : 0) * sizeof(WCHAR);
    us_value.Buffer = val;
''','MangoHud is never shown for seamonkey.exe (04.26).')

# 04.24 (run-0224: SeaMonkey with GPU compositing ended 10 s in, after the title ran out of descriptors at open=798:
# pipes=435 of them, a Wine thread's seven pipe ends with the in-process server, about 62 live threads in the title).
# Who starts each of a guest's threads, and how many of its threads are alive: thread_starts names ucrtbase's
# _beginthreadex for 80 of SeaMonkey's 89, so the caller outside the C runtime is the one that tells Gecko's pools
# from Mesa's queues (zink: one flush thread, four compile threads, one per GL context). The first 256 of the title.
# Read only.
revise('kernelbase','thread','''/***************************************************************************
 *           CreateRemoteThread   (kernelbase.@)
 */''','''/* 04.24 (run-0224): who starts a guest's thread, outside the C runtime, and the guest's live threads. Read only. */
static void ps4_thread_new_trace( struct ps4_guest *guest, HANDLE handle, LPTHREAD_START_ROUTINE start )
{
    /* 04.25 (run-0229: 96 of SeaMonkey's threads by "nss3.dll"+1060f9, NSPR's thread start): past NSPR too */
    static const WCHAR *const plumbing[] = { L"kernelbase.dll", L"kernel32.dll", L"ntdll.dll", L"ucrtbase.dll",
                                             L"msvcrt.dll", L"vcruntime140.dll", L"msvcp140.dll", L"nss3.dll" };
    static LONG traced;
    LDR_DATA_TABLE_ENTRY *mod;
    void *frames[16];
    char by[96] = "?", from[96];
    USHORT count, i;
    UINT j, made, live = 0;

    if (InterlockedIncrement( &traced ) > 256) return;
    count = RtlCaptureStackBackTrace( 1, ARRAY_SIZE(frames), frames, NULL );
    for (i = 0; i < count; i++)
    {
        if (LdrFindEntryForAddress( frames[i], &mod ) || !mod->BaseDllName.Buffer) continue;
        for (j = 0; j < ARRAY_SIZE(plumbing); j++)
            if (!wcsicmp( mod->BaseDllName.Buffer, plumbing[j] )) break;
        if (j < ARRAY_SIZE(plumbing)) continue;
        snprintf( by, sizeof(by), "%s+%Ix", debugstr_w( mod->BaseDllName.Buffer ),
                  (ULONG_PTR)frames[i] - (ULONG_PTR)mod->DllBase );
        break;
    }
    if (!LdrFindEntryForAddress( (void *)start, &mod ) && mod->BaseDllName.Buffer)
        snprintf( from, sizeof(from), "%s+%Ix", debugstr_w( mod->BaseDllName.Buffer ),
                  (ULONG_PTR)start - (ULONG_PTR)mod->DllBase );
    else
        snprintf( from, sizeof(from), "%p", start );
    RtlEnterCriticalSection( &guest->lock );
    made = guest->thread_count;
    for (j = 0; j < guest->thread_count; j++)
        if (WaitForSingleObject( guest->threads[j], 0 ) == WAIT_TIMEOUT) live++;
    RtlLeaveCriticalSection( &guest->lock );
    if (ps4_pw_traced()) ERR( "PWGUEST thread_new module=%p id=%04lx made=%u live=%u by=%s start=%s\\n", guest->module,
         GetThreadId( handle ), made, live, by, from );
}

/***************************************************************************
 *           CreateRemoteThread   (kernelbase.@)
 */''','Who starts a guest thread is traced (04.24).')
revise('kernelbase','thread','''            else if (DuplicateHandle( GetCurrentProcess(), handle, GetCurrentProcess(), &copy, 0, FALSE, DUPLICATE_SAME_ACCESS ))
                guest->threads[guest->thread_count++] = copy;
            RtlLeaveCriticalSection( &guest->lock );
''','''            else if (DuplicateHandle( GetCurrentProcess(), handle, GetCurrentProcess(), &copy, 0, FALSE, DUPLICATE_SAME_ACCESS ))
                guest->threads[guest->thread_count++] = copy;
            RtlLeaveCriticalSection( &guest->lock );
            ps4_thread_new_trace( guest, handle, start );  /* 04.24 */
''','Who starts a guest thread is traced (04.24).')

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
    else if (params.orphaned && ps4_pw_traced()) ERR( "PWAUDIO guest %p: %u streams out of the mixer, %u of others kept\\n",
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
 * 04.26 (run-0238: Portal 2 after Alan Wake drew garbage through Wine's d3d9 and wined3d's Vulkan renderer): Wine's
 * copy an earlier guest loaded stays loaded in the world, and a name without a path matches a loaded module by its
 * base name first. While it is loaded, a guest without the override gets syswow64's (DXVK's) by its full name.
 * NULL: the usual search. Loader lock held. */
static WCHAR *ps4_guest_d3d_builtin( const WCHAR *libname )
{
    static const WCHAR *const names[] = {L"d3d8", L"d3d9"};
    static const WCHAR dir[] = L"C:\\\\windows\\\\syswow64\\\\pw-wined3d\\\\";
    static const WCHAR sysdir[] = L"C:\\\\windows\\\\syswow64\\\\";
    static const WCHAR subdir[] = L"\\\\pw-wined3d\\\\";
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
    unsigned int i, len = 0, name_len, tail;
    BOOL builtin = FALSE, wine_loaded = FALSE;

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
    /* 04.26: is Wine's copy (pw-wined3d/<name>.dll) loaded? */
    name_len = wcslen( names[i] );
    tail = ARRAY_SIZE(subdir) - 1 + name_len + 4;
    for (entry = list->Flink; entry != list && !wine_loaded; entry = entry->Flink)
    {
        LDR_DATA_TABLE_ENTRY *mod = CONTAINING_RECORD( entry, LDR_DATA_TABLE_ENTRY, InLoadOrderLinks );
        const WCHAR *end;

        if (!mod->FullDllName.Buffer || mod->FullDllName.Length / sizeof(WCHAR) < tail) continue;
        end = mod->FullDllName.Buffer + mod->FullDllName.Length / sizeof(WCHAR) - tail;
        wine_loaded = !wcsnicmp( end, subdir, ARRAY_SIZE(subdir) - 1 ) &&
                      !wcsnicmp( end + ARRAY_SIZE(subdir) - 1, names[i], name_len ) &&
                      !wcsnicmp( end + ARRAY_SIZE(subdir) - 1 + name_len, L".dll", 4 );
    }
    wcscpy( path, L"Software\\\\Wine\\\\AppDefaults\\\\" );
    len = wcslen( path );
    memcpy( path + len, program->Buffer, program->Length );
    path[len + program->Length / sizeof(WCHAR)] = 0;
    wcscat( path, L"\\\\DllOverrides" );
    if (!RtlOpenCurrentUser( KEY_READ, &root ))
    {
        RtlInitUnicodeString( &str, path );
        InitializeObjectAttributes( &attr, &str, OBJ_CASE_INSENSITIVE, root, NULL );
        status = NtOpenKey( &key, KEY_READ, &attr );
        NtClose( root );
        if (!status)
        {
            RtlInitUnicodeString( &str, names[i] );
            status = NtQueryValueKey( key, &str, KeyValuePartialInformation, buffer, sizeof(buffer) - sizeof(WCHAR),
                                      &size );
            NtClose( key );
            if (!status && info->Type == REG_SZ)
            {
                data = (WCHAR *)info->Data;
                data[info->DataLength / sizeof(WCHAR)] = 0;
                for (len = 0; data[len] && data[len] != ','; len++) {}
                builtin = (len == 1 && (data[0] == 'b' || data[0] == 'B')) || (len == 7 && !wcsnicmp( data, L"builtin", 7 ));
            }
        }
    }
    if (!builtin && !wine_loaded) return NULL;
    if (!(fullname = RtlAllocateHeap( GetProcessHeap(), 0, sizeof(dir) + (name_len + 4) * sizeof(WCHAR) )))
        return NULL;
    wcscpy( fullname, builtin ? dir : sysdir );
    wcscat( fullname, names[i] );
    wcscat( fullname, L".dll" );
    if (builtin)
        ERR( "PWGUEST %s for %s: %s (its AppDefaults DllOverrides)\\n", debugstr_w(libname), debugstr_us(program),
             debugstr_w(fullname) );
    else
        ERR( "PWGUEST %s for %s: %s (not Wine's, which an earlier guest left loaded)\\n", debugstr_w(libname),
             debugstr_us(program), debugstr_w(fullname) );
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

# alpha-1 (run-0165, 2026-11-16: Alan Wake's American Nightmare, 32-bit on DXVK, closed from the overlay after device
# losses; free memory at each start fell 4.92, 4.17, 3.46, 3.33, 2.70, 2.04 GB, until a level load found no memory):
# RADV's buffers are direct memory, given back only by vkFreeMemory, and a terminated guest never frees its device
# memory. win32u records the guest of the thread that created each Vulkan device ("pwguest", tools/build-win32u-ps4.py,
# platform/ps4/pw_wine_unixlibs.c); once the guest has unloaded (its threads ended, its modules' and the system
# modules' DllMain(DETACH) run), the device memory it left is freed. Its devices are kept, and so is Zink's memory.
# alpha-1 (run-0178, 2026-11-17: the same game on wined3d + OpenGL, through Zink, closed from the overlay: 4.77 ->
# 3.50 GB, "PWGUEST vulkan ... shared=1"): Zink's one device is the process's, made by the first OpenGL guest, and the
# terminated guest's GL contexts stay in it. When no other guest runs in the world, Mesa's WGL forgets its screen
# (tools/vk-h0/patch-mesa-wgl-guest.py), and win32u frees the memory of that world's Zink devices (PW_GUEST_RELEASE_GL).
revise('kernelbase','process','''static void ps4_guest_unload( struct ps4_guest *guest )
{''','''/* alpha-1 (run-0178): Mesa's WGL in this world lets go of its one screen (Zink's device) when no other guest runs
 * in the world (tools/vk-h0/patch-mesa-wgl-guest.py); 1 when it did, and win32u may free that device's memory */
static UINT32 ps4_guest_release_gl( struct ps4_guest *guest )
{
    int (CDECL *release)( unsigned int *contexts, unsigned int *desktop );
    HMODULE gallium = GetModuleHandleW( L"libgallium_wgl.dll" );
    unsigned int contexts = 0, desktop = 0;
    UINT i, others = 0;
    int result;

    if (!gallium) return 0;
    RtlAcquireSRWLockShared( &ps4_live_lock );
    for (i = 0; i < ps4_live_count; i++)
        if (ps4_live_guests[i] != guest) others++;
    RtlReleaseSRWLockShared( &ps4_live_lock );
    if (others)
    {
        ERR( "PWGUEST gl module=%p kept: %u other guests running\\n", guest->module, others );
        return 0;
    }
    if (!(release = (void *)GetProcAddress( gallium, "pw_wgl_release_screen" )))
    {
        ERR( "PWGUEST gl module=%p kept: libgallium_wgl has no pw_wgl_release_screen\\n", guest->module );
        return 0;
    }
    result = release( &contexts, &desktop );
    if (ps4_pw_traced()) ERR( "PWGUEST gl module=%p result=%d contexts=%u desktop=%u\\n", guest->module, result, contexts, desktop );
    return result == 1 ? 1 /* PW_GUEST_RELEASE_GL */ : 0;
}

/* alpha-1 (run-0165): what winecrt0's __wine_load_unix_lib and __wine_unix_call do, as for the audio driver (W285);
 * with no params, only whether win32u's "pwguest" library is there (STATUS_DLL_NOT_FOUND when not) */
static NTSTATUS ps4_guest_pwguest( struct ps4_guest *guest, unsigned int code, void *params )
{
    static NTSTATUS (WINAPI *dispatcher)( UINT64 handle, unsigned int code, void *args );
    static UINT64 library;
    static LONG state;  /* 0 not tried, 1 loaded, -1 not available */
    NTSTATUS status;

    if (!state)
    {
        UNICODE_STRING name = RTL_CONSTANT_STRING( L"pwguest" );
        void **export = (void **)GetProcAddress( GetModuleHandleW( L"ntdll.dll" ), "__wine_unix_call_dispatcher" );
        UINT64 res[2];

        status = export ? NtQueryVirtualMemory( GetCurrentProcess(), &name, MemoryWineLoadUnixLibByName,
                                                res, sizeof(res), NULL ) : STATUS_ENTRYPOINT_NOT_FOUND;
        if (!status)
        {
            dispatcher = *export;
            library = res[1];
        }
        state = status ? -1 : 1;
        if (status) ERR( "PWGUEST vulkan module=%p: no pwguest library (%#lx); its device memory stays\\n",
                         guest->module, status );
    }
    if (state != 1) return STATUS_DLL_NOT_FOUND;
    return params ? dispatcher( library, code, params ) : STATUS_SUCCESS;
}

/* alpha-1 (run-0185): win32u logs the free direct and flexible memory and the direct memory of Wine's commits at a
 * guest's start ("PWVK guest_memory ... why=start"), to compare with the lines of its release */
static void ps4_guest_memory_line( struct ps4_guest *guest, UINT32 why )
{
    /* why: 0 start, 1 heaps_before (run-0190) */
    struct { UINT64 owner; UINT32 heaps, why; } params = { (ULONG_PTR)guest, RtlGetProcessHeaps( 0, NULL ), why };
    NTSTATUS status = ps4_guest_pwguest( guest, 1, &params );  /* struct pw_guest_memory_params */

    if (status && status != STATUS_DLL_NOT_FOUND) ERR( "PWGUEST memory_line failed (%#lx)\\n", status );
}

static void ps4_guest_release_vulkan( struct ps4_guest *guest )
{
    struct  /* struct pw_release_guest_vulkan_params, tools/build-win32u-ps4.py */
    {
        UINT64 owner, bytes;
        UINT32 devices, memories, shared, others, flags, gl_devices;
        UINT64 gl_bytes;
        UINT32 gl_memories, heaps;
    } params = { (ULONG_PTR)guest };
    NTSTATUS status;
    C_ASSERT( sizeof(params) == 56 );

    if (ps4_guest_pwguest( guest, 0, NULL )) return;  /* without it, Zink's screen is kept too */
    params.flags = ps4_guest_release_gl( guest );  /* run-0178 */
    params.heaps = RtlGetProcessHeaps( 0, NULL );  /* run-0185 */
    status = ps4_guest_pwguest( guest, 0, &params );
    if (status) ERR( "PWGUEST vulkan module=%p release failed (%#lx)\\n", guest->module, status );
    else if ((params.devices || params.shared || params.gl_devices) && ps4_pw_traced())
        ERR( "PWGUEST vulkan module=%p devices=%u memories=%u bytes=%I64u shared=%u others=%u gl_devices=%u "
             "gl_memories=%u gl_bytes=%I64u\\n", guest->module, params.devices, params.memories, params.bytes,
             params.shared, params.others, params.gl_devices, params.gl_memories, params.gl_bytes );
}

static void ps4_guest_unload( struct ps4_guest *guest )
{''','The Vulkan device memory an ended guest left is freed (alpha-1, run-0165).')
revise('kernelbase','process','''        ps4_guest_systems_after( guest, &systems );  /* W293 */''','''        ps4_guest_systems_after( guest, &systems );  /* W293 */
        ps4_guest_release_vulkan( guest );  /* alpha-1 (run-0165) */''','The Vulkan device memory an ended guest left is freed (alpha-1, run-0165).')
# alpha-1 (run-0185, 2026-11-17, 04.12: the same OpenGL guest terminated, gl_bytes=523534416 freed, and still 0.49 GB
# less free direct memory and 0.22 GB less free flexible memory at the next start): direct memory is RADV's buffers and,
# since W175, Wine's commits of 1 MiB or more. win32u logs both, and the free memory, at each guest's start and
# around its release ("PWVK guest_memory").
revise('kernelbase','process','''static void ps4_guest_unload( struct ps4_guest *guest );
''','''static void ps4_guest_unload( struct ps4_guest *guest );
static void ps4_guest_memory_line( struct ps4_guest *guest, UINT32 why );  /* alpha-1 (run-0185) */
static void ps4_guest_claim_heaps( struct ps4_guest *guest );  /* alpha-1 (run-0203) */
''','Free memory and Wine direct memory at each guest start (alpha-1, run-0185).')
revise('kernelbase','process','''             GetModuleHandleW( L"libMangoHud.dll" ) );
    }
''','''             GetModuleHandleW( L"libMangoHud.dll" ) );
        ps4_guest_memory_line( guest, 0 );  /* alpha-1 (run-0185) */
    }
''','Free memory and Wine direct memory at each guest start (alpha-1, run-0185).')

# alpha-1 (run-0190, 2026-11-17, 04.13: Alan Wake on wined3d-gl, terminated from the overlay: 0.86 GB lost, of which
# Wine's commits of 1 MiB or more 0.41 GB and free flexible memory 0.29 GB, and the 32-bit world's process heaps went
# from 2 to 5, with regions=0: none of it was VirtualAlloc from the guest's code). A heap's blocks of 508 KB or more
# are commits of their own (direct memory from 1 MiB, W175) and the smaller ones grow it in 64 KB steps (flexible), so
# both can be a heap's memory, and no heap a guest created was ever destroyed.
# alpha-1 (run-0203, 2026-11-17, 04.15: "PWGUEST heaps ... destroyed=0 kept=0 gone=0" after Alan Wake and Portal 2,
# whose heaps went from 2 to 5 and from 5 to 8): run-0190's record was in kernelbase's HeapCreate, and nothing called
# it: kernel32's HeapCreate is Wine's own (dlls/kernel32/heap.c), which programs and their C runtimes import, and this
# build does not rebuild kernel32. ntdll's RtlCreateHeap, which every HeapCreate ends in, now records the guest of the
# creating thread (TEB.UserReserved), or the guest image load mark (UserReserved[2]); kernelbase gives the heaps made
# while a guest EXE loaded (its imports' DllMain, msvcr100's heap among them) to that guest at its load_end. When the
# guest has ended and its modules are unloaded, each heap still recorded for it is destroyed, unless a loaded module's
# writable data still holds its handle (a C runtime or a system DLL that stays, keeping its heap in a global); that one
# is kept and named. Reading or setting the record goes through RtlQueryHeapInformation and RtlSetHeapInformation with
# the class PW_HEAP_GUEST, which Windows does not have.
revise('ntdll','heap','''/***********************************************************************
 *           RtlCreateHeap   (NTDLL.@)
 */''','''/* OrbisDesk alpha-1 (run-0203): the guest of the thread that created each heap, from TEB.UserReserved[0..1] (a guest's
 * thread), or 1 while a guest EXE loads (UserReserved[2] is PS4_GUEST_LOADING); kernelbase reads and sets it through
 * RtlQueryHeapInformation and RtlSetHeapInformation with the class PW_HEAP_GUEST (tools/build-guest-hw.py). Kept under
 * the process heap's lock, with the heap list. The process heap is never recorded. */
#define PW_HEAP_GUEST 0x5057
static struct { struct heap *heap; void *guest; } pw_heap_guests[256];

static void *pw_heap_creator(void)
{
    void *guest = *(void **)NtCurrentTeb()->UserReserved;

    if (guest) return guest;
    return NtCurrentTeb()->UserReserved[2] == 0x47345350 /* PS4 guest image load (W052) */ ? (void *)1 : NULL;
}

/* the process heap's lock is held; a NULL guest forgets the heap */
static void pw_heap_guest_set( struct heap *heap, void *guest )
{
    unsigned int i, free_slot = ARRAY_SIZE(pw_heap_guests);
    static unsigned int reported;

    for (i = 0; i < ARRAY_SIZE(pw_heap_guests); i++)
    {
        if (pw_heap_guests[i].heap == heap)
        {
            if (guest) pw_heap_guests[i].guest = guest;
            else pw_heap_guests[i].heap = NULL;
            return;
        }
        if (!pw_heap_guests[i].heap && free_slot == ARRAY_SIZE(pw_heap_guests)) free_slot = i;
    }
    if (!guest) return;
    if (free_slot < ARRAY_SIZE(pw_heap_guests))
    {
        pw_heap_guests[free_slot].heap = heap;
        pw_heap_guests[free_slot].guest = guest;
    }
    else if (!reported++) ERR( "PWGUEST heaps not recorded past %u\\n", i );
}

static void *pw_heap_guest_get( struct heap *heap )
{
    unsigned int i;

    for (i = 0; i < ARRAY_SIZE(pw_heap_guests); i++)
        if (pw_heap_guests[i].heap == heap) return pw_heap_guests[i].guest;
    return NULL;
}

/***********************************************************************
 *           RtlCreateHeap   (NTDLL.@)
 */''','The guest of the thread that created each heap is recorded (alpha-1, run-0203).')
revise('ntdll','heap','''        list_add_head( &process_heap->entry, &heap->entry );''','''        list_add_head( &process_heap->entry, &heap->entry );
        pw_heap_guest_set( heap, pw_heap_creator() );  /* alpha-1 (run-0203) */''',
       'The guest of the thread that created each heap is recorded (alpha-1, run-0203).')
revise('ntdll','heap','''    list_remove( &heap->entry );''','''    list_remove( &heap->entry );
    pw_heap_guest_set( heap, NULL );  /* alpha-1 (run-0203) */''','A destroyed heap leaves the record (alpha-1, run-0203).')
revise('ntdll','heap','''    TRACE( "handle %p, info_class %u, info %p, size_in %Iu, size_out %p.\\n", handle, info_class, info, size_in, size_out );
''','''    TRACE( "handle %p, info_class %u, info %p, size_in %Iu, size_out %p.\\n", handle, info_class, info, size_in, size_out );

    if (info_class == (HEAP_INFORMATION_CLASS)PW_HEAP_GUEST)  /* alpha-1 (run-0203) */
    {
        if (!(heap = unsafe_heap_from_handle( handle, 0, &flags ))) return STATUS_INVALID_HANDLE;
        if (size_out) *size_out = sizeof(void *);
        if (size_in < sizeof(void *)) return STATUS_BUFFER_TOO_SMALL;
        RtlEnterCriticalSection( &process_heap->cs );
        *(void **)info = pw_heap_guest_get( heap );
        RtlLeaveCriticalSection( &process_heap->cs );
        return STATUS_SUCCESS;
    }
''','The guest of a heap can be read (alpha-1, run-0203).')
revise('ntdll','heap','''    TRACE( "handle %p, info_class %u, info %p, size %Iu.\\n", handle, info_class, info, size );
''','''    TRACE( "handle %p, info_class %u, info %p, size %Iu.\\n", handle, info_class, info, size );

    if (info_class == (HEAP_INFORMATION_CLASS)PW_HEAP_GUEST)  /* alpha-1 (run-0203) */
    {
        if (size < sizeof(void *)) return STATUS_BUFFER_TOO_SMALL;
        if (!(heap = unsafe_heap_from_handle( handle, 0, &flags )) || heap == process_heap) return STATUS_INVALID_HANDLE;
        RtlEnterCriticalSection( &process_heap->cs );
        pw_heap_guest_set( heap, *(void **)info );
        RtlLeaveCriticalSection( &process_heap->cs );
        return STATUS_SUCCESS;
    }
''','The guest of a heap can be set (alpha-1, run-0203).')
revise('kernelbase','process','''static void ps4_guest_unload_own( struct ps4_guest *guest, BOOL leftovers )
{
    static WCHAR live_dirs''','''/* alpha-1 (run-0203): the guest ntdll recorded for a heap (its heap.c revision): the guest of the thread that created
 * it, 1 for one made while a guest EXE loaded, or NULL */
#define PW_HEAP_GUEST 0x5057
static void *ps4_guest_heap_owner( HANDLE heap )
{
    void *owner = NULL;

    if (RtlQueryHeapInformation( heap, (HEAP_INFORMATION_CLASS)PW_HEAP_GUEST, &owner, sizeof(owner), NULL )) return NULL;
    return owner;
}

static void ps4_guest_heap_set_owner( HANDLE heap, void *owner )
{
    RtlSetHeapInformation( heap, (HEAP_INFORMATION_CLASS)PW_HEAP_GUEST, &owner, sizeof(owner) );
}

/* at its load_end, on the thread that loaded it: the heaps its imports' DllMain made (msvcr100's, run-0190) are the
 * guest's */
static void ps4_guest_claim_heaps( struct ps4_guest *guest )
{
    HANDLE heaps[256];
    ULONG count = RtlGetProcessHeaps( ARRAY_SIZE(heaps), heaps ), i, claimed = 0;

    if (count > ARRAY_SIZE(heaps))
    {
        ERR( "PWGUEST heaps module=%p: %lu heaps, not claimed\\n", guest->module, count );
        return;
    }
    for (i = 0; i < count; i++)
    {
        if (ps4_guest_heap_owner( heaps[i] ) != (void *)1) continue;
        ps4_guest_heap_set_owner( heaps[i], guest );
        claimed++;
    }
    if (claimed && ps4_pw_traced()) ERR( "PWGUEST heaps module=%p claimed=%lu made while it loaded\\n", guest->module, claimed );
}

/* a loaded module whose writable data holds the value (a heap handle in a global), or NULL; ntdll, which keeps the
 * record, is skipped. The loader lock is held. */
static const WCHAR *ps4_guest_heap_holder( HANDLE heap, HMODULE ntdll )
{
    LIST_ENTRY *list = &NtCurrentTeb()->Peb->LdrData->InLoadOrderModuleList, *entry;

    for (entry = list->Flink; entry != list; entry = entry->Flink)
    {
        LDR_DATA_TABLE_ENTRY *mod = CONTAINING_RECORD( entry, LDR_DATA_TABLE_ENTRY, InLoadOrderLinks );
        IMAGE_NT_HEADERS *nt;
        IMAGE_SECTION_HEADER *section;
        UINT s;

        if (mod->DllBase == (void *)ntdll || !(nt = RtlImageNtHeader( mod->DllBase ))) continue;
        section = IMAGE_FIRST_SECTION( nt );
        for (s = 0; s < nt->FileHeader.NumberOfSections; s++, section++)
        {
            const DWORD wanted = IMAGE_SCN_MEM_WRITE | IMAGE_SCN_MEM_READ;
            DWORD size = section->Misc.VirtualSize ? section->Misc.VirtualSize : section->SizeOfRawData;
            char *at, *stop;

            if ((section->Characteristics & wanted) != wanted || section->VirtualAddress >= mod->SizeOfImage) continue;
            if (size > mod->SizeOfImage - section->VirtualAddress) size = mod->SizeOfImage - section->VirtualAddress;
            at = (char *)mod->DllBase + section->VirtualAddress;
            stop = at + (size & ~(sizeof(HANDLE) - 1));
            while (at < stop)
            {
                MEMORY_BASIC_INFORMATION mbi;
                char *region_end;

                if (!VirtualQuery( at, &mbi, sizeof(mbi) )) break;
                region_end = (char *)mbi.BaseAddress + mbi.RegionSize;
                if (region_end > stop) region_end = stop;
                if (mbi.State == MEM_COMMIT && mbi.Protect && !(mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD)))
                {
                    const HANDLE *p;

                    for (p = (const HANDLE *)at; (const char *)(p + 1) <= region_end; p++)
                        if (*p == heap) return mod->BaseDllName.Buffer ? mod->BaseDllName.Buffer : L"?";
                }
                if (region_end <= at) break;
                at = region_end;
            }
        }
    }
    return NULL;
}

static void ps4_guest_memory_line( struct ps4_guest *guest, UINT32 why );

/* after its own modules (and the system modules only they used) are unloaded: each heap ntdll recorded for the guest is
 * destroyed, unless a loaded module still holds it. The free memory before is logged (PWVK guest_memory ...
 * why=heaps_before), and win32u's release_before line follows */
static void ps4_guest_release_heaps( struct ps4_guest *guest )
{
    HANDLE heaps[256], process = GetProcessHeap();
    HMODULE ntdll = GetModuleHandleW( L"ntdll.dll" );
    ULONG count, i, destroyed = 0, kept = 0;
    ULONG_PTR magic;

    ps4_guest_memory_line( guest, 1 );
    count = RtlGetProcessHeaps( ARRAY_SIZE(heaps), heaps );
    if (count > ARRAY_SIZE(heaps))
    {
        ERR( "PWGUEST heaps module=%p kept: %lu heaps, more than listed\\n", guest->module, count );
        return;
    }
    if (LdrLockLoaderLock( 0, NULL, &magic )) return;
    for (i = 0; i < count; i++)
    {
        const WCHAR *holder;

        if (heaps[i] == process || ps4_guest_heap_owner( heaps[i] ) != guest) continue;
        if ((holder = ps4_guest_heap_holder( heaps[i], ntdll )))
        {
            if (ps4_pw_traced()) ERR( "PWGUEST heap %p of module %p kept: held by %s\\n", heaps[i], guest->module, debugstr_w( holder ) );
            ps4_guest_heap_set_owner( heaps[i], NULL );
            kept++;
            continue;
        }
        if (!RtlDestroyHeap( heaps[i] )) destroyed++;
    }
    LdrUnlockLoaderLock( 0, magic );
    ERR( "PWGUEST heaps module=%p destroyed=%lu kept=%lu\\n", guest->module, destroyed, kept );
}

static void ps4_guest_unload_own( struct ps4_guest *guest, BOOL leftovers )
{
    static WCHAR live_dirs''','The heaps an ended guest made are destroyed unless a loaded module holds them (alpha-1, run-0203).')
revise('kernelbase','process','''    NtCurrentTeb()->UserReserved[2] = 0;
    ps4_guest_loading = NULL;''','''    NtCurrentTeb()->UserReserved[2] = 0;
    ps4_guest_loading = NULL;
    if (guest->module) ps4_guest_claim_heaps( guest );  /* alpha-1 (run-0203) */''',
       'The heaps made while a guest EXE loaded are its own (alpha-1, run-0203).')
revise('kernelbase','process','''    guest->region_count = guest->region_size = 0;
    RtlLeaveCriticalSection( &guest->lock );

done:
    RtlReleaseSRWLockExclusive( &own_lock );''','''    guest->region_count = guest->region_size = 0;
    RtlLeaveCriticalSection( &guest->lock );
    if (!leftovers) ps4_guest_release_heaps( guest );  /* alpha-1 (run-0190, run-0203) */

done:
    RtlReleaseSRWLockExclusive( &own_lock );''','The heaps an ended guest made are destroyed unless a loaded module holds them (alpha-1, run-0203).')

# alpha-1 (run-0212, 2026-11-17, 04.17: Alan Wake on wined3d-gl, terminated from the overlay, still 0.69 GB lost, 0.32 GB
# of it Wine's commits of 1 MiB or more; "heaps destroyed=1 kept=1" gave back nothing, as msvcr100 had already destroyed
# its own heap when it unloaded with the guest's modules). What is left is in heaps the guest did not create: the process
# heap (ucrtbase's malloc, a static C runtime, HeapAlloc) and msvcrt.dll's own heap (malloc of Wine's DLLs, DXVK and
# Mesa). A heap block of HEAP_MIN_LARGE_BLOCK_SIZE or more (about 508 KB on i386, 1020 KB on x86_64) is a virtual
# allocation of its own; ntdll now tags each with the guest of the allocating thread (TEB.UserReserved[0]), the code
# that called RtlAllocateHeap or RtlReAllocateHeap, and the frame above it, in a trailer past the block (the block's
# block_size stops before it, so an in-place resize cannot reach it). kernelbase lists a guest's tagged blocks through
# RtlQueryHeapInformation with the class PW_HEAP_LARGE, which Windows does not have. After the guest's heaps, each of
# its blocks whose allocating code is in no loaded module any more is freed; the others are kept and logged by the
# module that called and the one above it ("PWGUEST heap_large ... kept ... from ... via ..."). Each heap of 1 MiB or
# more is logged at the guest's start and at its release ("PWGUEST heap_usage"), so the next log shows which heap kept
# the rest.
revise('ntdll','heap','''static NTSTATUS heap_allocate_large( struct heap *heap, ULONG flags, SIZE_T block_size,
                                     SIZE_T size, void **ret )
{
    ARENA_LARGE *arena;
    SIZE_T total_size = ROUND_SIZE( sizeof(*arena) + size, REGION_ALIGN - 1 );''','''/* OrbisDesk alpha-1 (run-0212): each large block ends in a tag, past its block_size: the guest of the allocating thread
 * (TEB.UserReserved[0]), the code that called RtlAllocateHeap or RtlReAllocateHeap, and the frame above it.
 * kernelbase lists a guest's tagged blocks through RtlQueryHeapInformation with the class PW_HEAP_LARGE
 * (tools/build-guest-hw.py). */
#define PW_HEAP_LARGE 0x5058
#define PW_LARGE_TAG  0x544c5750  /* "PWLT" */
struct pw_large_tag { DWORD magic; void *guest; void *caller; void *via; };
struct pw_heap_large_block { void *ptr; SIZE_T size; void *caller; void *via; };
struct pw_heap_large_info
{
    void *guest;  /* in: the guest whose blocks are listed, or NULL */
    ULONG max;    /* in: room in blocks[] */
    ULONG listed;
    SIZE_T guest_blocks, guest_bytes, large_blocks, large_bytes, committed;
    struct pw_heap_large_block blocks[1];
};

static inline struct pw_large_tag *pw_large_tag( ARENA_LARGE *arena )
{
    return (struct pw_large_tag *)((char *)&arena->block + arena->block_size);
}

static void pw_large_tag_set( void *ptr, void *caller )
{
    ARENA_LARGE *arena = CONTAINING_RECORD( (struct block *)ptr - 1, ARENA_LARGE, block );
    struct pw_large_tag *tag = pw_large_tag( arena );
    void *frames[8];
    USHORT count, i;

    tag->guest = *(void **)NtCurrentTeb()->UserReserved;
    tag->caller = caller;
    tag->via = NULL;
    if (tag->guest)
    {
        count = RtlCaptureStackBackTrace( 0, ARRAY_SIZE(frames), frames, NULL );
        for (i = 0; i + 1 < count; i++)
        {
            if (frames[i] != caller) continue;
            tag->via = frames[i + 1];
            break;
        }
    }
    tag->magic = PW_LARGE_TAG;
}

/* what the heap's subheaps commit, its large blocks, and those tagged with info->guest (up to info->max listed) */
static void pw_heap_large_query( struct heap *heap, ULONG flags, struct pw_heap_large_info *info )
{
    ARENA_LARGE *arena;
    SUBHEAP *subheap;

    info->listed = 0;
    info->guest_blocks = info->guest_bytes = info->large_blocks = info->large_bytes = info->committed = 0;
    heap_lock( heap, flags );
    LIST_FOR_EACH_ENTRY( subheap, &heap->subheap_list, SUBHEAP, entry )
        info->committed += (const char *)subheap_commit_end( subheap ) - (const char *)subheap_base( subheap );
    LIST_FOR_EACH_ENTRY( arena, &heap->large_list, ARENA_LARGE, entry )
    {
        struct pw_large_tag *tag = pw_large_tag( arena );
        SIZE_T bytes = (char *)(tag + 1) - (char *)arena;

        info->large_blocks++;
        info->large_bytes += bytes;
        if (!info->guest || tag->magic != PW_LARGE_TAG || tag->guest != info->guest) continue;
        info->guest_blocks++;
        info->guest_bytes += bytes;
        if (info->listed >= info->max) continue;
        info->blocks[info->listed].ptr = &arena->block + 1;
        info->blocks[info->listed].size = bytes;
        info->blocks[info->listed].caller = tag->caller;
        info->blocks[info->listed].via = tag->via;
        info->listed++;
    }
    heap_unlock( heap, flags );
}

static NTSTATUS heap_allocate_large( struct heap *heap, ULONG flags, SIZE_T block_size,
                                     SIZE_T size, void **ret )
{
    ARENA_LARGE *arena;
    SIZE_T total_size = ROUND_SIZE( sizeof(*arena) + size + sizeof(struct pw_large_tag), REGION_ALIGN - 1 );''',
       'A large heap block ends in a tag: the allocating guest and code (alpha-1, run-0212).')
revise('ntdll','heap','''    arena->block_size = (char *)arena + total_size - (char *)block;''','''    /* alpha-1 (run-0212): the tag is past block_size */
    arena->block_size = (char *)arena + total_size - sizeof(struct pw_large_tag) - (char *)block;''',
       'A large heap block ends in a tag: the allocating guest and code (alpha-1, run-0212).')
revise('ntdll','heap','''    if (!status) valgrind_notify_alloc( ptr, size, flags & HEAP_ZERO_MEMORY );
''','''    if (!status) valgrind_notify_alloc( ptr, size, flags & HEAP_ZERO_MEMORY );
    if (!status && block_size >= HEAP_MIN_LARGE_BLOCK_SIZE)
        pw_large_tag_set( ptr, __builtin_return_address( 0 ) );  /* alpha-1 (run-0212) */
''','A large heap block ends in a tag: the allocating guest and code (alpha-1, run-0212).')
revise('ntdll','heap','''            memcpy( ret, ptr, min( size, old_size ) );
            RtlFreeHeap( heap, flags, ptr );
            status = STATUS_SUCCESS;''','''            memcpy( ret, ptr, min( size, old_size ) );
            RtlFreeHeap( heap, flags, ptr );
            status = STATUS_SUCCESS;
            if (block_get_flags( (struct block *)ret - 1 ) & BLOCK_FLAG_LARGE)
                pw_large_tag_set( ret, __builtin_return_address( 0 ) );  /* alpha-1 (run-0212) */''',
       'A large heap block ends in a tag: the allocating guest and code (alpha-1, run-0212).')
revise('ntdll','heap','''    if (info_class == (HEAP_INFORMATION_CLASS)PW_HEAP_GUEST)  /* alpha-1 (run-0203) */
    {
        if (!(heap = unsafe_heap_from_handle( handle, 0, &flags ))) return STATUS_INVALID_HANDLE;
        if (size_out) *size_out = sizeof(void *);''','''    if (info_class == (HEAP_INFORMATION_CLASS)PW_HEAP_LARGE)  /* alpha-1 (run-0212) */
    {
        struct pw_heap_large_info *large = info;
        SIZE_T head = offsetof( struct pw_heap_large_info, blocks );

        if (!(heap = unsafe_heap_from_handle( handle, 0, &flags ))) return STATUS_INVALID_HANDLE;
        if (size_in < head || large->max > (size_in - head) / sizeof(large->blocks[0])) return STATUS_BUFFER_TOO_SMALL;
        pw_heap_large_query( heap, flags, large );
        if (size_out) *size_out = head + large->listed * sizeof(large->blocks[0]);
        return STATUS_SUCCESS;
    }

    if (info_class == (HEAP_INFORMATION_CLASS)PW_HEAP_GUEST)  /* alpha-1 (run-0203) */
    {
        if (!(heap = unsafe_heap_from_handle( handle, 0, &flags ))) return STATUS_INVALID_HANDLE;
        if (size_out) *size_out = sizeof(void *);''','The large heap blocks of a guest can be listed (alpha-1, run-0212).')
revise('kernelbase','process','''static void ps4_guest_claim_heaps( struct ps4_guest *guest );  /* alpha-1 (run-0203) */
''','''static void ps4_guest_claim_heaps( struct ps4_guest *guest );  /* alpha-1 (run-0203) */
static void ps4_guest_heap_usage( struct ps4_guest *guest );  /* alpha-1 (run-0212) */
''','Each large heap is logged at the start of a guest (alpha-1, run-0212).')
revise('kernelbase','process','''        ps4_guest_memory_line( guest, 0 );  /* alpha-1 (run-0185) */
''','''        ps4_guest_memory_line( guest, 0 );  /* alpha-1 (run-0185) */
        ps4_guest_heap_usage( guest );  /* alpha-1 (run-0212) */
''','Each large heap is logged at the start of a guest (alpha-1, run-0212).')
revise('kernelbase','process','''/* after its own modules (and the system modules only they used) are unloaded: each heap ntdll recorded for the guest is''','''/* alpha-1 (run-0212): ntdll's large-block tags (its heap.c revision), listed through RtlQueryHeapInformation */
#define PW_HEAP_LARGE 0x5058
struct pw_heap_large_block { void *ptr; SIZE_T size; void *caller; void *via; };
struct pw_heap_large_info
{
    void *guest;  /* in: the guest whose blocks are listed, or NULL */
    ULONG max;    /* in: room in blocks[] */
    ULONG listed;
    SIZE_T guest_blocks, guest_bytes, large_blocks, large_bytes, committed;
    struct pw_heap_large_block blocks[1];
};

/* the name of the loaded module that holds the address, or NULL; valid while the loader lock is held */
static const WCHAR *ps4_guest_code_module( void *address )
{
    LDR_DATA_TABLE_ENTRY *mod;

    if (!address || LdrFindEntryForAddress( address, &mod )) return NULL;
    return mod->BaseDllName.Buffer ? mod->BaseDllName.Buffer : L"?";
}

/* at the guest's start: each heap of 1 MiB or more, what its subheaps commit and its large blocks */
static void ps4_guest_heap_usage( struct ps4_guest *guest )
{
    HANDLE heaps[256], process = GetProcessHeap();
    ULONG count = RtlGetProcessHeaps( ARRAY_SIZE(heaps), heaps ), i;
    struct pw_heap_large_info info;

    for (i = 0; i < count && i < ARRAY_SIZE(heaps); i++)
    {
        memset( &info, 0, sizeof(info) );
        if (RtlQueryHeapInformation( heaps[i], (HEAP_INFORMATION_CLASS)PW_HEAP_LARGE, &info, sizeof(info), NULL )) return;
        if (info.committed + info.large_bytes < 0x100000) continue;
        if (ps4_pw_traced()) ERR( "PWGUEST heap_usage owner=%p why=start heap=%p holder=%s committed=%Iu large=%Iu blocks=%Iu\\n", guest,
             heaps[i], heaps[i] == process ? "process" : "-", info.committed, info.large_bytes, info.large_blocks );
    }
}

/* 04.29 (run-0244: Alan Wake, terminated, kept 114 MB of large blocks that wined3d.dll had allocated through
 * ucrtbase): a module whose large blocks belong only to the objects a program made with it. wined3d's process-wide
 * state (its window procedure and swapchain-state tables, its budget notifications) holds small entries; a terminated
 * guest never releases its Direct3D objects, and its windows, through which wined3d would reach them, are gone.
 * DXVK is not one: its d3d9.dll keeps one instance for the process (run-0219). */
static BOOL ps4_guest_object_module( const WCHAR *name )
{
    return name && !wcsicmp( name, L"wined3d.dll" );
}

/* after the guest's own heaps: its large blocks in the heaps that stay (the process heap, msvcrt.dll's, a kept one).
 * A block whose allocating code is in no loaded module any more (the guest's own modules, a system module that went
 * with them) is freed, and so is, for a terminated guest, one that an object module called or allocated (04.29); the
 * others are kept and summed by the module that called RtlAllocateHeap and the module of the frame above it ("none"
 * when that is in no loaded module). The loader lock is held. */
static void ps4_guest_release_large( struct ps4_guest *guest, HMODULE ntdll )
{
    static const ULONG max = 4096;
    struct { const WCHAR *caller, *via; SIZE_T bytes; ULONG blocks; } kept[8];
    HANDLE heaps[256], process = GetProcessHeap();
    ULONG count = RtlGetProcessHeaps( ARRAY_SIZE(heaps), heaps ), i, j, k, names = 0, other_blocks = 0;
    SIZE_T size = offsetof( struct pw_heap_large_info, blocks ) + max * sizeof(struct pw_heap_large_block);
    SIZE_T other_bytes = 0, object_bytes = 0;  /* 04.29 */
    ULONG object_blocks = 0;
    struct pw_heap_large_info *info;

    if (count > ARRAY_SIZE(heaps)) count = ARRAY_SIZE(heaps);
    if (!(info = VirtualAlloc( NULL, size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE ))) return;
    for (i = 0; i < count; i++)
    {
        const WCHAR *holder = heaps[i] == process ? NULL : ps4_guest_heap_holder( heaps[i], ntdll );
        SIZE_T freed_bytes = 0;
        ULONG freed = 0;

        info->guest = guest;
        info->max = max;
        if (RtlQueryHeapInformation( heaps[i], (HEAP_INFORMATION_CLASS)PW_HEAP_LARGE, info, size, NULL )) break;
        if (info->committed + info->large_bytes >= 0x100000)
            if (ps4_pw_traced()) ERR( "PWGUEST heap_usage owner=%p why=release heap=%p holder=%s committed=%Iu large=%Iu blocks=%Iu\\n", guest,
                 heaps[i], heaps[i] == process ? "process" : holder ? debugstr_w( holder ) : "-", info->committed,
                 info->large_bytes, info->large_blocks );
        if (!info->guest_blocks) continue;
        for (j = 0; j < info->listed; j++)
        {
            const struct pw_heap_large_block *block = &info->blocks[j];
            const WCHAR *caller = ps4_guest_code_module( block->caller ), *via = NULL;
            BOOL object = FALSE;

            if (caller && guest->terminated)  /* 04.29 */
            {
                via = ps4_guest_code_module( block->via );
                object = ps4_guest_object_module( caller ) || ps4_guest_object_module( via );
            }
            if (!caller || object)
            {
                if (RtlFreeHeap( heaps[i], 0, block->ptr ))
                {
                    freed++;
                    freed_bytes += block->size;
                    if (object)
                    {
                        object_blocks++;
                        object_bytes += block->size;
                    }
                }
                continue;
            }
            via = ps4_guest_code_module( block->via );
            for (k = 0; k < names; k++) if (kept[k].caller == caller && kept[k].via == via) break;
            if (k == names && names < ARRAY_SIZE(kept))
            {
                kept[k].caller = caller;
                kept[k].via = via;
                kept[k].bytes = 0;
                kept[k].blocks = 0;
                names++;
            }
            if (k < names)
            {
                kept[k].bytes += block->size;
                kept[k].blocks++;
            }
            else
            {
                other_bytes += block->size;
                other_blocks++;
            }
        }
        if (ps4_pw_traced()) ERR( "PWGUEST heap_large module=%p heap=%p blocks=%Iu bytes=%Iu listed=%lu freed=%lu freed_bytes=%Iu\\n",
             guest->module, heaps[i], info->guest_blocks, info->guest_bytes, info->listed, freed, freed_bytes );
    }
    for (k = 0; k < names; k++)
        if (ps4_pw_traced()) ERR( "PWGUEST heap_large module=%p kept bytes=%Iu blocks=%lu from %s via %s\\n", guest->module, kept[k].bytes,
             kept[k].blocks, debugstr_w( kept[k].caller ), kept[k].via ? debugstr_w( kept[k].via ) : "none" );
    if (other_blocks)
        if (ps4_pw_traced()) ERR( "PWGUEST heap_large module=%p kept bytes=%Iu blocks=%lu from others\\n", guest->module, other_bytes,
             other_blocks );
    if (object_blocks)  /* 04.29: part of the freed ones above */
        if (ps4_pw_traced()) ERR( "PWGUEST heap_large module=%p objects freed_bytes=%Iu blocks=%lu: the terminated guest's, made through "
             "wined3d.dll\\n", guest->module, object_bytes, object_blocks );
    VirtualFree( info, 0, MEM_RELEASE );
}

/* after its own modules (and the system modules only they used) are unloaded: each heap ntdll recorded for the guest is''',
       'The large heap blocks of an ended guest whose code is gone are freed (alpha-1, run-0212).')
revise('kernelbase','process','''        if (!RtlDestroyHeap( heaps[i] )) destroyed++;
    }
    LdrUnlockLoaderLock( 0, magic );
    ERR( "PWGUEST heaps module=%p destroyed=%lu kept=%lu\\n", guest->module, destroyed, kept );''','''        if (!RtlDestroyHeap( heaps[i] )) destroyed++;
    }
    ERR( "PWGUEST heaps module=%p destroyed=%lu kept=%lu\\n", guest->module, destroyed, kept );
    ps4_guest_release_large( guest, ntdll );  /* alpha-1 (run-0212) */
    LdrUnlockLoaderLock( 0, magic );''','The large heap blocks of an ended guest whose code is gone are freed (alpha-1, run-0212).')

# 04.30 (run-0252, run-0253, 2026-11-19, 04.29: Alan Wake on wined3d-gl, terminated from the overlay, still 0.42-0.65 GB
# lost per start). Its large blocks made through wined3d were freed (123 MB); what stayed is in the process heap:
# 170-200 MB of small blocks, which carry no owner, and 80 MB of large blocks per start that no guest's thread made.
# On i386, a small block that a guest's thread allocates in the process heap now carries its allocation site (the
# guest, the code that called RtlAllocateHeap or RtlReAllocateHeap, the frame above it) in the heap's own user-value
# slot (HEAP_ADD_USER_INFO); such blocks bypass the LFH, so every one is reached under the heap lock. Each site counts
# its live blocks and bytes. After a guest's large blocks, kernelbase lists its sites and has the blocks of the sites
# it chose freed: those whose code is gone, or, for a terminated guest, made through wined3d.dll (as large blocks).
# "Code gone" now also covers a block a C runtime allocated for code that is gone (the frame above malloc). The large
# blocks of no guest's thread are listed too, with the frame above, and freed when their code is gone. Logged as
# "PWGUEST heap_small ..." and "PWGUEST heap_unowned ...". C:/orbis/nosmalltags.txt turns the small-block sites off.
revise('ntdll','heap','''    tag->via = NULL;
    if (tag->guest)
    {
        count = RtlCaptureStackBackTrace( 0, ARRAY_SIZE(frames), frames, NULL );
        for (i = 0; i + 1 < count; i++)
        {
            if (frames[i] != caller) continue;
            tag->via = frames[i + 1];
            break;
        }
    }''','''    tag->via = NULL;
    /* 04.30 (run-0253: 88 large blocks per start were no guest's): the frame above for every block */
    count = RtlCaptureStackBackTrace( 0, ARRAY_SIZE(frames), frames, NULL );
    for (i = 0; i + 1 < count; i++)
    {
        if (frames[i] != caller) continue;
        tag->via = frames[i + 1];
        break;
    }''','A large heap block of no guest records the frame above its caller too (04.30, run-0253).')
revise('ntdll','heap','''#define PW_LARGE_TAG  0x544c5750  /* "PWLT" */
''','''#define PW_LARGE_TAG  0x544c5750  /* "PWLT" */
#define PW_LARGE_NO_GUEST ((void *)~(ULONG_PTR)0)  /* 04.30: info->guest that lists the blocks of no guest */
''','The large heap blocks of no guest can be listed (04.30, run-0253).')
revise('ntdll','heap','''        if (!info->guest || tag->magic != PW_LARGE_TAG || tag->guest != info->guest) continue;''','''        if (!info->guest || tag->magic != PW_LARGE_TAG) continue;
        if (tag->guest != (info->guest == PW_LARGE_NO_GUEST ? NULL : info->guest)) continue;  /* 04.30 */''',
       'The large heap blocks of no guest can be listed (04.30, run-0253).')
revise('ntdll','heap','''/***********************************************************************
 *           RtlAllocateHeap   (NTDLL.@)
 */
void *WINAPI DECLSPEC_HOTPATCH RtlAllocateHeap( HANDLE handle, ULONG flags, SIZE_T size )
{
    struct heap *heap;
    SIZE_T block_size;
    void *ptr = NULL;
    ULONG heap_flags;
    NTSTATUS status;

    heap = unsafe_heap_from_handle( handle, flags, &heap_flags );
    if ((block_size = heap_get_block_size( heap, heap_flags, size )) == ~0U)
        status = STATUS_NO_MEMORY;
    else if (block_size >= HEAP_MIN_LARGE_BLOCK_SIZE)''','''/* OrbisDesk 04.30 (run-0252, run-0253: Alan Wake, terminated, kept 170-200 MB of small blocks in the process heap,
 * which carry no owner): on i386, a small block that a guest's thread (TEB.UserReserved[0]) allocates in the process
 * heap carries its allocation site in the heap's user-value slot (HEAP_ADD_USER_INFO): the guest, the code that called
 * RtlAllocateHeap or RtlReAllocateHeap, and the frame above it. Such blocks bypass the LFH, so all of them are reached
 * under the heap lock. A site counts its live blocks and bytes. kernelbase lists a guest's sites through
 * RtlQueryHeapInformation (PW_HEAP_SITES) and, after the guest ended, has the blocks of the sites it chose freed and
 * all its sites ended through RtlSetHeapInformation (PW_HEAP_SITES_FREE) (tools/build-guest-hw.py).
 * C:/orbis/nosmalltags.txt turns them off. */
#define PW_HEAP_SITES      0x5059
#define PW_HEAP_SITES_FREE 0x505a
#define PW_SITE_COUNT  8192
#define PW_SITE_PROBES 64
struct pw_site
{
    LONG state;    /* 0 never used, 2 in use, 3 its guest ended (reused once it has no block) */
    LONG release;  /* its blocks are being freed, under the process heap's lock */
    void *guest, *caller, *via;
    LONG blocks, bytes;
};
struct pw_heap_site { void *site, *caller, *via; LONG blocks, bytes; };
struct pw_heap_sites
{
    void *guest;  /* in: the guest whose sites are listed */
    ULONG max;    /* in: room in sites[] */
    ULONG listed, total, missed;
    SIZE_T blocks, bytes;
    struct pw_heap_site sites[1];
};
struct pw_heap_sites_free
{
    void *guest;  /* in: the guest that ended */
    ULONG count;  /* in: its sites whose blocks are freed */
    ULONG freed;  /* out */
    SIZE_T freed_bytes;
    void *sites[1];
};
static struct pw_site pw_sites[PW_SITE_COUNT];
static LONG pw_sites_lock, pw_sites_missed;

static inline void pw_sites_enter(void)
{
    while (InterlockedCompareExchange( &pw_sites_lock, 1, 0 )) NtYieldExecution();
}

static inline void pw_sites_leave(void)
{
    InterlockedExchange( &pw_sites_lock, 0 );
}

#ifndef _WIN64
static LONG pw_small_state;  /* 0 not read yet, 1 on, 2 off */

static BOOL pw_small_enabled(void)
{
    LONG state = ReadNoFence( &pw_small_state );

    if (!state)
    {
        static const WCHAR off[] = L"\\\\??\\\\C:\\\\orbis\\\\nosmalltags.txt";
        UNICODE_STRING name;
        OBJECT_ATTRIBUTES attr;
        FILE_BASIC_INFORMATION info;

        RtlInitUnicodeString( &name, off );
        InitializeObjectAttributes( &attr, &name, OBJ_CASE_INSENSITIVE, 0, NULL );
        InterlockedCompareExchange( &pw_small_state, NtQueryAttributesFile( &attr, &info ) ? 1 : 2, 0 );
        state = ReadNoFence( &pw_small_state );
    }
    return state == 1;
}
#endif

/* the guest whose small block of the process heap gets a site, or NULL; a resized block keeps its site's */
static inline void *pw_small_guest( const struct heap *heap, ULONG flags, const struct pw_site *site )
{
#ifdef _WIN64
    return NULL;
#else
    void *guest;

    if (!heap || heap != process_heap || (flags & (HEAP_ADD_USER_INFO | HEAP_NO_SERIALIZE))) return NULL;
    if (site) return site->guest;
    if (!(guest = *(void **)NtCurrentTeb()->UserReserved) || !pw_small_enabled()) return NULL;
    return guest;
#endif
}

/* where RtlSetUserValueHeap keeps a block's user value */
static inline struct pw_site **pw_small_slot( const struct block *block, ULONG flags )
{
    char *tmp = (char *)block + block_get_size( block ) - block->tail_size + sizeof(void *);

    if ((flags & HEAP_TAIL_CHECKING_ENABLED) || RUNNING_ON_VALGRIND) tmp += BLOCK_ALIGN;
    return (struct pw_site **)tmp;
}

static inline BOOL pw_site_valid( const struct pw_site *site )
{
    const char *at = (const char *)site, *start = (const char *)pw_sites;

    return at >= start && at < (const char *)(pw_sites + PW_SITE_COUNT) && !((at - start) % sizeof(*site));
}

/* the site of a tagged small block of the process heap, or NULL */
static struct pw_site *pw_small_site( const struct heap *heap, ULONG flags, const struct block *block )
{
    static const UINT mask = BLOCK_FLAG_FREE | BLOCK_FLAG_LARGE | BLOCK_FLAG_LFH | BLOCK_FLAG_USER_INFO;
    struct pw_site *site;

    if (heap != process_heap || (block_get_flags( block ) & mask) != BLOCK_FLAG_USER_INFO) return NULL;
    if (block_get_type( block ) != BLOCK_TYPE_USED) return NULL;
    site = *pw_small_slot( block, flags );
    return pw_site_valid( site ) ? site : NULL;
}

/* the site of (guest, caller, via), made if needed; NULL when its probe run is full */
static struct pw_site *pw_site_get( void *guest, void *caller, void *via )
{
    ULONG_PTR key = (ULONG_PTR)guest ^ ((ULONG_PTR)caller * 0x9e3779b1u) ^ ((ULONG_PTR)via * 0x85ebca6bu);
    unsigned int start = (unsigned int)((key ^ (key >> 15)) % PW_SITE_COUNT), i, n;
    struct pw_site *site, *found = NULL;

    for (n = 0, i = start; n < PW_SITE_PROBES; n++, i = (i + 1) % PW_SITE_COUNT)
    {
        LONG state = ReadAcquire( &pw_sites[i].state );

        site = &pw_sites[i];
        if (!state) break;
        if (state == 2 && site->guest == guest && site->caller == caller && site->via == via) return site;
    }
    pw_sites_enter();
    for (n = 0, i = start; n < PW_SITE_PROBES; n++, i = (i + 1) % PW_SITE_COUNT)
    {
        site = &pw_sites[i];
        if (site->state == 2)
        {
            if (site->guest != guest || site->caller != caller || site->via != via) continue;
            found = site;
            break;
        }
        if (site->state == 3 && ReadNoFence( &site->blocks )) continue;
        /* never used, or ended with no block left: readers skip it until it is in use */
        site->guest = guest;
        site->caller = caller;
        site->via = via;
        site->blocks = site->bytes = site->release = 0;
        WriteRelease( &site->state, 2 );
        found = site;
        break;
    }
    pw_sites_leave();
    return found;
}

static void pw_small_tag( ULONG flags, void *ptr, SIZE_T size, void *guest, void *caller, struct pw_site *site )
{
    struct block *block = (struct block *)ptr - 1;

    if (!site)
    {
        void *frames[8], *via = NULL;
        USHORT count, i;

        count = RtlCaptureStackBackTrace( 0, ARRAY_SIZE(frames), frames, NULL );
        for (i = 0; i + 1 < count; i++)
        {
            if (frames[i] != caller) continue;
            via = frames[i + 1];
            break;
        }
        if (!(site = pw_site_get( guest, caller, via ))) InterlockedIncrement( &pw_sites_missed );
    }
    *pw_small_slot( block, flags ) = site;
    if (!site) return;
    InterlockedIncrement( &site->blocks );
    InterlockedExchangeAdd( &site->bytes, (LONG)size );
}

/* before a small block of the process heap is freed */
static void pw_small_untag( const struct heap *heap, ULONG flags, struct block *block )
{
    struct pw_site *site = pw_small_site( heap, flags, block );

    if (!site) return;
    *pw_small_slot( block, flags ) = NULL;
    InterlockedDecrement( &site->blocks );
    InterlockedExchangeAdd( &site->bytes, -(LONG)(block_get_size( block ) - block_get_overhead( block )) );
}

/* RtlReAllocateHeap of a tagged block: its new block size, with room for the site kept */
static SIZE_T pw_small_resize_size( const struct heap *heap, ULONG *flags, const struct block *block, SIZE_T size,
                                    SIZE_T *old )
{
    *old = block_get_size( block ) - block_get_overhead( block );
    *flags |= HEAP_ADD_USER_INFO;
    return heap_get_block_size( heap, *flags, size );
}

/* after a tagged block was resized in place, which cleared its user value */
static void pw_small_resized( ULONG flags, void *ptr, struct pw_site *site, SIZE_T old, SIZE_T size )
{
    *pw_small_slot( (struct block *)ptr - 1, flags ) = site;
    InterlockedExchangeAdd( &site->bytes, (LONG)size - (LONG)old );
}

static void pw_small_query( struct pw_heap_sites *info )
{
    unsigned int i;

    info->listed = info->total = 0;
    info->blocks = info->bytes = 0;
    info->missed = ReadNoFence( &pw_sites_missed );
    for (i = 0; i < PW_SITE_COUNT; i++)
    {
        struct pw_site *site = &pw_sites[i];
        LONG blocks, bytes;

        if (ReadAcquire( &site->state ) != 2 || site->guest != info->guest) continue;
        if ((blocks = ReadNoFence( &site->blocks )) <= 0) continue;
        bytes = ReadNoFence( &site->bytes );
        info->total++;
        info->blocks += blocks;
        info->bytes += bytes;
        if (info->listed >= info->max) continue;
        info->sites[info->listed].site = site;
        info->sites[info->listed].caller = site->caller;
        info->sites[info->listed].via = site->via;
        info->sites[info->listed].blocks = blocks;
        info->sites[info->listed].bytes = bytes;
        info->listed++;
    }
}

/* the blocks of the listed sites of an ended guest are freed, then all its sites end; the heap lock is taken. A freed
 * block merges only with free neighbours, so the next block still in use is found before it is freed. */
static void pw_small_free( struct heap *heap, struct pw_heap_sites_free *req )
{
    SUBHEAP *subheap, *next_subheap;
    ULONG flags = heap->flags, i;

    req->freed = 0;
    req->freed_bytes = 0;
    heap_lock( heap, 0 );
    pw_sites_enter();
    for (i = 0; i < req->count; i++)
    {
        struct pw_site *site = req->sites[i];
        if (pw_site_valid( site ) && site->state == 2 && site->guest == req->guest) site->release = 1;
    }
    pw_sites_leave();
    if (req->count)
    {
        LIST_FOR_EACH_ENTRY_SAFE( subheap, next_subheap, &heap->subheap_list, SUBHEAP, entry )
        {
            struct block *block, *next;

            for (block = first_block( subheap ); block; block = next)
            {
                struct pw_site *site;
                SIZE_T size, block_size;

                if ((next = next_block( subheap, block )) && (block_get_flags( next ) & BLOCK_FLAG_FREE))
                    next = next_block( subheap, next );
                if (!(site = pw_small_site( heap, flags, block )) || !site->release) continue;
                block_size = block_get_size( block );
                size = block_size - block_get_overhead( block );
                *pw_small_slot( block, flags ) = NULL;
                InterlockedDecrement( &site->blocks );
                InterlockedExchangeAdd( &site->bytes, -(LONG)size );
                if (heap_free_block( heap, flags, block )) continue;
                if (heap->bins) InterlockedIncrement( &heap->bins[BLOCK_SIZE_BIN( block_size )].count_freed );
                req->freed++;
                req->freed_bytes += size;
            }
        }
    }
    pw_sites_enter();
    for (i = 0; i < PW_SITE_COUNT; i++)
    {
        struct pw_site *site = &pw_sites[i];

        if (site->state != 2 || site->guest != req->guest) continue;
        site->release = 0;
        WriteRelease( &site->state, 3 );
    }
    pw_sites_leave();
    heap_unlock( heap, 0 );
}

/* RtlAllocateHeap's body (04.30): caller is the code that called RtlAllocateHeap or RtlReAllocateHeap, site the one a
 * block moved by RtlReAllocateHeap keeps, or NULL */
static void *pw_allocate_heap( HANDLE handle, ULONG flags, SIZE_T size, void *caller, struct pw_site *site )
{
    struct heap *heap;
    SIZE_T block_size;
    void *ptr = NULL, *guest = NULL;
    ULONG heap_flags;
    NTSTATUS status;

    heap = unsafe_heap_from_handle( handle, flags, &heap_flags );
    if ((block_size = heap_get_block_size( heap, heap_flags, size )) == ~0U)
        status = STATUS_NO_MEMORY;
    else if (block_size < HEAP_MIN_LARGE_BLOCK_SIZE - BLOCK_ALIGN && (guest = pw_small_guest( heap, heap_flags, site )))
    {
        /* 04.30: a guest's small block of the process heap, with its site, not through the LFH */
        heap_flags |= HEAP_ADD_USER_INFO;
        block_size = heap_get_block_size( heap, heap_flags, size );
        heap_lock( heap, heap_flags );
        status = heap_allocate_block( heap, heap_flags, block_size, size, &ptr );
        heap_unlock( heap, heap_flags );

        if (!status)
        {
            if (heap->bins)
            {
                SIZE_T bin = BLOCK_SIZE_BIN( block_get_size( (struct block *)ptr - 1 ) );
                InterlockedIncrement( &heap->bins[bin].count_alloc );
                if (!ReadNoFence( &heap->bins[bin].enabled )) bin_try_enable( heap, &heap->bins[bin] );
            }
            pw_small_tag( heap_flags, ptr, size, guest, caller, site );
        }
    }
    else if (block_size >= HEAP_MIN_LARGE_BLOCK_SIZE)''','A small block a guest allocates in the process heap carries its site (04.30, run-0252).')
revise('ntdll','heap','''        pw_large_tag_set( ptr, __builtin_return_address( 0 ) );  /* alpha-1 (run-0212) */

    TRACE( "handle %p, flags %#lx, size %#Ix, return %p, status %#lx.\\n", handle, flags, size, ptr, status );
    heap_set_status( heap, flags, status );
    return ptr;
}''','''        pw_large_tag_set( ptr, caller );  /* alpha-1 (run-0212); 04.30: the caller given */

    TRACE( "handle %p, flags %#lx, size %#Ix, return %p, status %#lx.\\n", handle, flags, size, ptr, status );
    heap_set_status( heap, flags, status );
    return ptr;
}

/***********************************************************************
 *           RtlAllocateHeap   (NTDLL.@)
 */
void *WINAPI DECLSPEC_HOTPATCH RtlAllocateHeap( HANDLE handle, ULONG flags, SIZE_T size )
{
    return pw_allocate_heap( handle, flags, size, __builtin_return_address( 0 ), NULL );  /* 04.30 */
}''','A small block a guest allocates in the process heap carries its site (04.30, run-0252).')
revise('ntdll','heap','''    else if (!(block = heap_delay_free( heap, heap_flags, block )))
        status = STATUS_SUCCESS;''','''    else if (pw_small_untag( heap, heap_flags, block ), !(block = heap_delay_free( heap, heap_flags, block )))  /* 04.30 */
        status = STATUS_SUCCESS;''','A freed small block leaves its site (04.30, run-0252).')
revise('ntdll','heap','''    ULONG heap_flags;
    void *ret = NULL;
    NTSTATUS status;

    if (!ptr) return NULL;
''','''    ULONG heap_flags;
    void *ret = NULL;
    NTSTATUS status;
    struct pw_site *site = NULL;  /* 04.30 */
    SIZE_T site_size = 0;

    if (!ptr) return NULL;
''','A resized small block keeps its site (04.30, run-0252).')
revise('ntdll','heap','''    else if (!(block = unsafe_block_from_ptr( heap, heap_flags, ptr )))
        status = STATUS_INVALID_PARAMETER;
    else if ((status = heap_resize_in_place( heap, heap_flags, block, block_size, size,
                                        &old_size, &ret )))
    {
        if (flags & HEAP_REALLOC_IN_PLACE_ONLY)
            status = STATUS_NO_MEMORY;
        else if (!(ret = RtlAllocateHeap( heap, flags, size )))
            status = STATUS_NO_MEMORY;''','''    else if (!(block = unsafe_block_from_ptr( heap, heap_flags, ptr )))
        status = STATUS_INVALID_PARAMETER;
    /* 04.30: a tagged small block keeps its site, in place or moved */
    else if ((site = pw_small_site( heap, heap_flags, block )) &&
             (block_size = pw_small_resize_size( heap, &heap_flags, block, size, &site_size )) == ~0U)
        status = STATUS_NO_MEMORY;
    else if ((status = heap_resize_in_place( heap, heap_flags, block, block_size, size,
                                        &old_size, &ret )))
    {
        if (flags & HEAP_REALLOC_IN_PLACE_ONLY)
            status = STATUS_NO_MEMORY;
        else if (!(ret = pw_allocate_heap( heap, flags, size, __builtin_return_address( 0 ), site )))
            status = STATUS_NO_MEMORY;''','A resized small block keeps its site (04.30, run-0252).')
revise('ntdll','heap','''                pw_large_tag_set( ret, __builtin_return_address( 0 ) );  /* alpha-1 (run-0212) */
        }
    }
''','''                pw_large_tag_set( ret, __builtin_return_address( 0 ) );  /* alpha-1 (run-0212) */
        }
    }
    else if (site) pw_small_resized( heap_flags, ret, site, site_size, size );  /* 04.30 */
''','A resized small block keeps its site (04.30, run-0252).')
revise('ntdll','heap','''    if (info_class == (HEAP_INFORMATION_CLASS)PW_HEAP_LARGE)  /* alpha-1 (run-0212) */
''','''    if (info_class == (HEAP_INFORMATION_CLASS)PW_HEAP_SITES)  /* 04.30 (run-0252) */
    {
        struct pw_heap_sites *sites = info;
        SIZE_T head = offsetof( struct pw_heap_sites, sites );

        if (!(heap = unsafe_heap_from_handle( handle, 0, &flags )) || heap != process_heap) return STATUS_INVALID_HANDLE;
        if (size_in < head || sites->max > (size_in - head) / sizeof(sites->sites[0])) return STATUS_BUFFER_TOO_SMALL;
        pw_small_query( sites );
        if (size_out) *size_out = head + sites->listed * sizeof(sites->sites[0]);
        return STATUS_SUCCESS;
    }

    if (info_class == (HEAP_INFORMATION_CLASS)PW_HEAP_LARGE)  /* alpha-1 (run-0212) */
''','The small-block sites of a guest can be listed (04.30, run-0252).')
revise('ntdll','heap','''    if (info_class == (HEAP_INFORMATION_CLASS)PW_HEAP_GUEST)  /* alpha-1 (run-0203) */
    {
        if (size < sizeof(void *)) return STATUS_BUFFER_TOO_SMALL;''','''    if (info_class == (HEAP_INFORMATION_CLASS)PW_HEAP_SITES_FREE)  /* 04.30 (run-0252) */
    {
        struct pw_heap_sites_free *req = info;
        SIZE_T head = offsetof( struct pw_heap_sites_free, sites );

        if (!(heap = unsafe_heap_from_handle( handle, 0, &flags )) || heap != process_heap) return STATUS_INVALID_HANDLE;
        if (size < head || req->count > (size - head) / sizeof(req->sites[0])) return STATUS_BUFFER_TOO_SMALL;
        pw_small_free( heap, req );
        return STATUS_SUCCESS;
    }

    if (info_class == (HEAP_INFORMATION_CLASS)PW_HEAP_GUEST)  /* alpha-1 (run-0203) */
    {
        if (size < sizeof(void *)) return STATUS_BUFFER_TOO_SMALL;''','The blocks of the chosen sites of an ended guest are freed (04.30, run-0252).')
revise('kernelbase','process','''static BOOL ps4_guest_object_module( const WCHAR *name )
{
    return name && !wcsicmp( name, L"wined3d.dll" );
}
''','''static BOOL ps4_guest_object_module( const WCHAR *name )
{
    return name && !wcsicmp( name, L"wined3d.dll" );
}

/* 04.30 (run-0252): a module whose allocations are made for the code that called it: the C runtimes and the Win32
 * heap functions */
static BOOL ps4_guest_crt_module( const WCHAR *name )
{
    return name && (!wcsicmp( name, L"ucrtbase.dll" ) || !wcsnicmp( name, L"msvcr", 5 ) ||
                    !wcsicmp( name, L"kernelbase.dll" ) || !wcsicmp( name, L"kernel32.dll" ));
}

/* a block whose allocating code is in no loaded module any more: the code that called RtlAllocateHeap, or, when that
 * is a C runtime, the code that called it (04.30). The loader lock is held. */
static BOOL ps4_guest_code_gone( const WCHAR *caller, void *via_address, const WCHAR *via )
{
    if (!caller) return TRUE;
    return via_address && !via && ps4_guest_crt_module( caller );
}

/* 04.30: what was kept, summed by the module that called RtlAllocateHeap and the module of the frame above it */
#define PS4_KEPT_MAX 32
struct ps4_kept_list
{
    struct { const WCHAR *caller, *via; SIZE_T bytes; ULONG blocks; } names[PS4_KEPT_MAX];
    ULONG count, other_blocks;
    SIZE_T other_bytes;
};

static void ps4_kept_add( struct ps4_kept_list *list, const WCHAR *caller, const WCHAR *via, SIZE_T bytes, ULONG blocks )
{
    ULONG k;

    for (k = 0; k < list->count; k++) if (list->names[k].caller == caller && list->names[k].via == via) break;
    if (k == list->count)
    {
        if (k == PS4_KEPT_MAX)
        {
            list->other_bytes += bytes;
            list->other_blocks += blocks;
            return;
        }
        list->names[k].caller = caller;
        list->names[k].via = via;
        list->names[k].bytes = 0;
        list->names[k].blocks = 0;
        list->count++;
    }
    list->names[k].bytes += bytes;
    list->names[k].blocks += blocks;
}

/* the eight largest, then the rest as "others" */
static void ps4_kept_log( struct ps4_kept_list *list, void *module, const char *what )
{
    ULONG i, k, best;

    for (i = 0; i < list->count; i++)
    {
        for (best = i, k = i + 1; k < list->count; k++) if (list->names[k].bytes > list->names[best].bytes) best = k;
        if (best != i)
        {
            const WCHAR *caller = list->names[i].caller, *via = list->names[i].via;
            SIZE_T bytes = list->names[i].bytes;
            ULONG blocks = list->names[i].blocks;

            list->names[i] = list->names[best];
            list->names[best].caller = caller;
            list->names[best].via = via;
            list->names[best].bytes = bytes;
            list->names[best].blocks = blocks;
        }
        if (i >= 8)
        {
            list->other_bytes += list->names[i].bytes;
            list->other_blocks += list->names[i].blocks;
            continue;
        }
        if (ps4_pw_traced()) ERR( "PWGUEST %s module=%p kept bytes=%Iu blocks=%lu from %s via %s\\n", what, module, list->names[i].bytes,
             list->names[i].blocks, debugstr_w( list->names[i].caller ),
             list->names[i].via ? debugstr_w( list->names[i].via ) : "none" );
    }
    if (list->other_blocks)
        if (ps4_pw_traced()) ERR( "PWGUEST %s module=%p kept bytes=%Iu blocks=%lu from others\\n", what, module, list->other_bytes,
             list->other_blocks );
}
''','A block a C runtime made for code that is gone is freed; kept blocks are summed by module (04.30, run-0252).')
revise('kernelbase','process','''            const WCHAR *caller = ps4_guest_code_module( block->caller ), *via = NULL;
            BOOL object = FALSE;

            if (caller && guest->terminated)  /* 04.29 */
            {
                via = ps4_guest_code_module( block->via );
                object = ps4_guest_object_module( caller ) || ps4_guest_object_module( via );
            }
            if (!caller || object)''','''            const WCHAR *caller = ps4_guest_code_module( block->caller ), *via = ps4_guest_code_module( block->via );
            BOOL object = FALSE;

            if (caller && guest->terminated)  /* 04.29 */
                object = ps4_guest_object_module( caller ) || ps4_guest_object_module( via );
            if (ps4_guest_code_gone( caller, block->via, via ) || object)  /* 04.30: or a C runtime's, for gone code */''',
       'A large block a C runtime made for code that is gone is freed (04.30, run-0252).')
revise('kernelbase','process','''            via = ps4_guest_code_module( block->via );
            for (k = 0; k < names; k++)''','''            for (k = 0; k < names; k++)''','A large block a C runtime made for code that is gone is freed (04.30, run-0252).')
revise('kernelbase','process','''/* after its own modules (and the system modules only they used) are unloaded: each heap ntdll recorded for the guest is''',
'''/* 04.30 (run-0252, run-0253: Alan Wake, terminated, kept 170-200 MB of small blocks in the process heap per start):
 * ntdll's small-block sites (its heap.c revision), listed and freed through Rtl(Query|Set)HeapInformation */
#define PW_HEAP_SITES      0x5059
#define PW_HEAP_SITES_FREE 0x505a
#define PW_LARGE_NO_GUEST ((void *)~(ULONG_PTR)0)
struct pw_heap_site { void *site, *caller, *via; LONG blocks, bytes; };
struct pw_heap_sites
{
    void *guest;  /* in: the guest whose sites are listed */
    ULONG max;    /* in: room in sites[] */
    ULONG listed, total, missed;
    SIZE_T blocks, bytes;
    struct pw_heap_site sites[1];
};
struct pw_heap_sites_free
{
    void *guest;  /* in: the guest that ended */
    ULONG count;  /* in: its sites whose blocks are freed */
    ULONG freed;  /* out */
    SIZE_T freed_bytes;
    void *sites[1];
};

/* after its large blocks: the small blocks the guest's threads allocated in the process heap (i386). The blocks of a site
 * whose code is gone are freed, and, for a terminated guest, those of a site in an object module (as for large blocks);
 * then all its sites end. The others are kept and summed by module. The loader lock is held. */
static void ps4_guest_release_small( struct ps4_guest *guest )
{
    static const ULONG max = 8192;
    SIZE_T size = offsetof( struct pw_heap_sites, sites ) + max * sizeof(struct pw_heap_site);
    SIZE_T free_size = offsetof( struct pw_heap_sites_free, sites ) + max * sizeof(void *), object_bytes = 0;
    ULONG i, object_blocks = 0;
    struct ps4_kept_list kept;
    struct pw_heap_sites *info;
    struct pw_heap_sites_free *req;
    HANDLE process = GetProcessHeap();

    size = (size + 15) & ~(SIZE_T)15;
    if (!(info = VirtualAlloc( NULL, size + free_size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE ))) return;
    req = (struct pw_heap_sites_free *)((char *)info + size);
    memset( &kept, 0, sizeof(kept) );
    info->guest = guest;
    info->max = max;
    if (RtlQueryHeapInformation( process, (HEAP_INFORMATION_CLASS)PW_HEAP_SITES, info, size, NULL ))
    {
        VirtualFree( info, 0, MEM_RELEASE );
        return;
    }
    req->guest = guest;
    req->count = 0;
    for (i = 0; i < info->listed; i++)
    {
        const struct pw_heap_site *site = &info->sites[i];
        const WCHAR *caller = ps4_guest_code_module( site->caller ), *via = ps4_guest_code_module( site->via );
        BOOL object = caller && guest->terminated && (ps4_guest_object_module( caller ) || ps4_guest_object_module( via ));

        if (ps4_guest_code_gone( caller, site->via, via ) || object)
        {
            req->sites[req->count++] = site->site;
            if (object)
            {
                object_blocks += site->blocks;
                object_bytes += site->bytes;
            }
            continue;
        }
        ps4_kept_add( &kept, caller, via, site->bytes, site->blocks );
    }
    /* also ends its sites when none is freed */
    if (RtlSetHeapInformation( process, (HEAP_INFORMATION_CLASS)PW_HEAP_SITES_FREE, req, free_size ))
    {
        req->freed = 0;
        req->freed_bytes = 0;
    }
    if (info->total || info->missed)
        if (ps4_pw_traced()) ERR( "PWGUEST heap_small module=%p sites=%lu blocks=%Iu bytes=%Iu listed=%lu missed=%lu freed=%lu "
             "freed_bytes=%Iu\\n", guest->module, info->total, info->blocks, info->bytes, info->listed, info->missed,
             req->freed, req->freed_bytes );
    ps4_kept_log( &kept, guest->module, "heap_small" );
    if (object_blocks)  /* part of the freed ones above */
        if (ps4_pw_traced()) ERR( "PWGUEST heap_small module=%p objects bytes=%Iu blocks=%lu: the terminated guest's, made through "
             "wined3d.dll\\n", guest->module, object_bytes, object_blocks );
    VirtualFree( info, 0, MEM_RELEASE );
}

/* 04.30 (run-0253: 88 large blocks of 83 MB per start were made by no guest's thread): the process heap's large blocks
 * of no guest. Those whose code is gone are freed; the others are summed by module. The loader lock is held. */
static void ps4_guest_release_unowned( struct ps4_guest *guest )
{
    static const ULONG max = 4096;
    SIZE_T size = offsetof( struct pw_heap_large_info, blocks ) + max * sizeof(struct pw_heap_large_block);
    SIZE_T freed_bytes = 0;
    ULONG j, freed = 0;
    struct ps4_kept_list kept;
    struct pw_heap_large_info *info;
    HANDLE process = GetProcessHeap();

    if (!(info = VirtualAlloc( NULL, size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE ))) return;
    memset( &kept, 0, sizeof(kept) );
    info->guest = PW_LARGE_NO_GUEST;
    info->max = max;
    if (!RtlQueryHeapInformation( process, (HEAP_INFORMATION_CLASS)PW_HEAP_LARGE, info, size, NULL ) &&
        info->guest_blocks)
    {
        for (j = 0; j < info->listed; j++)
        {
            const struct pw_heap_large_block *block = &info->blocks[j];
            const WCHAR *caller = ps4_guest_code_module( block->caller ), *via = ps4_guest_code_module( block->via );

            if (ps4_guest_code_gone( caller, block->via, via ))
            {
                if (RtlFreeHeap( process, 0, block->ptr ))
                {
                    freed++;
                    freed_bytes += block->size;
                }
                continue;
            }
            ps4_kept_add( &kept, caller, via, block->size, 1 );
        }
        if (ps4_pw_traced()) ERR( "PWGUEST heap_unowned module=%p blocks=%Iu bytes=%Iu listed=%lu freed=%lu freed_bytes=%Iu\\n",
             guest->module, info->guest_blocks, info->guest_bytes, info->listed, freed, freed_bytes );
        ps4_kept_log( &kept, guest->module, "heap_unowned" );
    }
    VirtualFree( info, 0, MEM_RELEASE );
}

/* after its own modules (and the system modules only they used) are unloaded: each heap ntdll recorded for the guest is''',
       'The small blocks of an ended guest and the large blocks of no guest are released (04.30, run-0252).')
revise('kernelbase','process','''    ps4_guest_release_large( guest, ntdll );  /* alpha-1 (run-0212) */
''','''    ps4_guest_release_large( guest, ntdll );  /* alpha-1 (run-0212) */
    ps4_guest_release_small( guest );  /* 04.30 (run-0252) */
    ps4_guest_release_unowned( guest );  /* 04.30 (run-0253) */
''','The small blocks of an ended guest and the large blocks of no guest are released (04.30, run-0252).')

# 04.32 (run-0261, 2026-11-19, 04.30: Alan Wake on wined3d-gl, terminated from the overlay twice, lost 0.58 then 0.21
# GB). Of its small blocks in the process heap, 127 and 124 MB were freed; 74 and 59 MB stayed as "ucrtbase.dll via
# ucrtbase.dll": the C runtime allocated them through more of itself (_aligned_malloc -> _aligned_offset_malloc ->
# malloc, realloc -> malloc, _strdup), so the frame above malloc is ucrtbase again and neither "code gone" nor the
# wined3d rule could see who asked. A site now also records the three frames above that one (Wine builds its i386 PE
# modules with frame pointers, so the frames inside the C runtime are exact). At the release, when the caller is a C
# runtime, the frame that counts is the first one above it that is not a C runtime's; the rules and the kept lines use
# that frame. Large blocks are unchanged (their kept "ucrtbase via ucrtbase" share is 1-4 MB and does not grow).
revise('ntdll','heap','''    LONG release;  /* its blocks are being freed, under the process heap's lock */
    void *guest, *caller, *via;
    LONG blocks, bytes;
};
struct pw_heap_site { void *site, *caller, *via; LONG blocks, bytes; };''','''    LONG release;  /* its blocks are being freed, under the process heap's lock */
    void *guest, *caller, *via;
    void *up[3];  /* 04.32: the three frames above via */
    LONG blocks, bytes;
};
struct pw_heap_site { void *site, *caller, *via; LONG blocks, bytes; void *up[3]; };''','''A small block a C runtime allocated through more of the C runtime is counted for the code above it (04.32, run-0261).''')
revise('ntdll','heap','''static struct pw_site *pw_site_get( void *guest, void *caller, void *via )
{
    ULONG_PTR key = (ULONG_PTR)guest ^ ((ULONG_PTR)caller * 0x9e3779b1u) ^ ((ULONG_PTR)via * 0x85ebca6bu);''','''static struct pw_site *pw_site_get( void *guest, void *caller, void *via, void *const *up )
{
    ULONG_PTR key = (ULONG_PTR)guest ^ ((ULONG_PTR)caller * 0x9e3779b1u) ^ ((ULONG_PTR)via * 0x85ebca6bu) ^
                    ((ULONG_PTR)up[0] * 0xc2b2ae35u) ^ ((ULONG_PTR)up[1] * 0x27d4eb2fu) ^ ((ULONG_PTR)up[2] * 0x165667b1u);''','''A small block a C runtime allocated through more of the C runtime is counted for the code above it (04.32, run-0261).''')
revise('ntdll','heap','''        if (state == 2 && site->guest == guest && site->caller == caller && site->via == via) return site;''','''        if (state == 2 && site->guest == guest && site->caller == caller && site->via == via &&
            site->up[0] == up[0] && site->up[1] == up[1] && site->up[2] == up[2]) return site;''','''A small block a C runtime allocated through more of the C runtime is counted for the code above it (04.32, run-0261).''')
revise('ntdll','heap','''            if (site->guest != guest || site->caller != caller || site->via != via) continue;''','''            if (site->guest != guest || site->caller != caller || site->via != via ||
                site->up[0] != up[0] || site->up[1] != up[1] || site->up[2] != up[2]) continue;''','''A small block a C runtime allocated through more of the C runtime is counted for the code above it (04.32, run-0261).''')
revise('ntdll','heap','''        site->via = via;
        site->blocks = site->bytes = site->release = 0;''','''        site->via = via;
        site->up[0] = up[0];
        site->up[1] = up[1];
        site->up[2] = up[2];
        site->blocks = site->bytes = site->release = 0;''','''A small block a C runtime allocated through more of the C runtime is counted for the code above it (04.32, run-0261).''')
revise('ntdll','heap','''        void *frames[8], *via = NULL;
        USHORT count, i;

        count = RtlCaptureStackBackTrace( 0, ARRAY_SIZE(frames), frames, NULL );
        for (i = 0; i + 1 < count; i++)
        {
            if (frames[i] != caller) continue;
            via = frames[i + 1];
            break;
        }
        if (!(site = pw_site_get( guest, caller, via ))) InterlockedIncrement( &pw_sites_missed );''','''        void *frames[12], *via = NULL, *up[3] = { NULL, NULL, NULL };
        USHORT count, i;

        count = RtlCaptureStackBackTrace( 0, ARRAY_SIZE(frames), frames, NULL );
        for (i = 0; i + 1 < count; i++)
        {
            if (frames[i] != caller) continue;
            via = frames[i + 1];
            if (i + 2 < count) up[0] = frames[i + 2];  /* 04.32 */
            if (i + 3 < count) up[1] = frames[i + 3];
            if (i + 4 < count) up[2] = frames[i + 4];
            break;
        }
        if (!(site = pw_site_get( guest, caller, via, up ))) InterlockedIncrement( &pw_sites_missed );''','''A small block a C runtime allocated through more of the C runtime is counted for the code above it (04.32, run-0261).''')
revise('ntdll','heap','''        info->sites[info->listed].via = site->via;
''','''        info->sites[info->listed].via = site->via;
        info->sites[info->listed].up[0] = site->up[0];  /* 04.32 */
        info->sites[info->listed].up[1] = site->up[1];
        info->sites[info->listed].up[2] = site->up[2];
''','''A small block a C runtime allocated through more of the C runtime is counted for the code above it (04.32, run-0261).''')
revise('kernelbase','process','''struct pw_heap_site { void *site, *caller, *via; LONG blocks, bytes; };''','''struct pw_heap_site { void *site, *caller, *via; LONG blocks, bytes; void *up[3]; };''',
       '''A small block a C runtime allocated through more of the C runtime is counted for the code above it (04.32, run-0261).''')
revise('kernelbase','process','''/* after its large blocks: the small blocks the guest's threads allocated in the process heap (i386). The blocks of a site''','''/* 04.32 (run-0261: 74 and 59 MB kept as "ucrtbase.dll via ucrtbase.dll"): the frame that counts for a site. When the
 * caller is a C runtime and the frame above it is one too (_aligned_malloc or _strdup calling malloc), it is the first
 * of the three frames above that is not a C runtime's; *via is its module. Without them, via stays. The loader lock is
 * held. */
static void *ps4_site_frame( const WCHAR *caller, const struct pw_heap_site *site, const WCHAR **via )
{
    void *frame = site->via;
    ULONG i;

    if (!ps4_guest_crt_module( caller )) return frame;
    for (i = 0; i < ARRAY_SIZE(site->up) && site->up[i] && ps4_guest_crt_module( *via ); i++)
    {
        frame = site->up[i];
        *via = ps4_guest_code_module( frame );
    }
    return frame;
}

/* after its large blocks: the small blocks the guest's threads allocated in the process heap (i386). The blocks of a site''',
       '''A small block a C runtime allocated through more of the C runtime is counted for the code above it (04.32, run-0261).''')
revise('kernelbase','process','''        const WCHAR *caller = ps4_guest_code_module( site->caller ), *via = ps4_guest_code_module( site->via );
        BOOL object = caller && guest->terminated && (ps4_guest_object_module( caller ) || ps4_guest_object_module( via ));

        if (ps4_guest_code_gone( caller, site->via, via ) || object)''','''        const WCHAR *caller = ps4_guest_code_module( site->caller ), *via = ps4_guest_code_module( site->via );
        void *frame = ps4_site_frame( caller, site, &via );  /* 04.32 */
        BOOL object = caller && guest->terminated && (ps4_guest_object_module( caller ) || ps4_guest_object_module( via ));

        if (ps4_guest_code_gone( caller, frame, via ) || object)''','''A small block a C runtime allocated through more of the C runtime is counted for the code above it (04.32, run-0261).''')

# alpha-1 (run-0215, 2026-11-17, 04.17: GTA San Andreas, exit status 0, lost 0.47 and 0.39 GB of direct memory that
# was not Wine's own commits after its device memory was freed): a guest that ended by itself (not terminated by the
# overlay's close or a crash, W209) also has its Vulkan devices destroyed by win32u, with a time limit
# (PW_GUEST_RELEASE_DEVICES, tools/build-win32u-ps4.py). A terminated guest keeps today's release: its threads were
# stopped wherever they were, and a queue wait could block. run-0219: its instances stay (DXVK's d3d9.dll, which
# stays loaded, takes the same VkInstance at the next start).
revise('kernelbase','process','''    params.flags = ps4_guest_release_gl( guest );  /* run-0178 */''','''    params.flags = ps4_guest_release_gl( guest );  /* run-0178 */
    if (!guest->terminated) params.flags |= 2;  /* alpha-1 (run-0215): PW_GUEST_RELEASE_DEVICES */''',
       'The Vulkan devices of a guest that ended by itself are destroyed (alpha-1, run-0215).')

# alpha-1 (run-0121, 2026-11-13: PES 2014's settings.exe, an IL-only .NET EXE, failed to load at 0x400000 with
# "mscoree.dll not found" (c0000135); its next start found "image_not_at_base preferred=0x400000 size=0x156000
# status=0xc0000018 occupied=0x400000+0x156000", its own image). When build_module fails to resolve imports it takes
# the module out of the loader's lists but sets *module to NULL, so load_native_dll does not unmap the view: Wine
# leaves it, as the failed process normally ends. A guest EXE in explorer's shared process kept its fixed base taken
# until OrbisDesk ended. Its view is unmapped; the modref stays allocated, as upstream leaves it (dependencies may
# point to it), and nothing in the image has run.
revise('ntdll','loader','''             * As these might reference our wm, we don't free it.
             */
            *module = NULL;''','''             * As these might reference our wm, we don't free it.
             */
            /* PS4 hardware build (alpha-1, run-0121): a guest EXE's view is unmapped, or its fixed base
             * stays taken in explorer's process (c0000018 at the next start) */
            if (NtCurrentTeb()->UserReserved[2] == 0x47345350 /* PS4 guest image load (W052) */ &&
                !(nt->FileHeader.Characteristics & IMAGE_FILE_DLL))
            {
                ERR( "PWGUEST load_failed unmap %s at %p status %#lx\\n", debugstr_us( nt_name ), *module, status );
                NtUnmapViewOfSection( NtCurrentProcess(), *module );
            }
            *module = NULL;''','A guest EXE whose imports fail is unmapped (alpha-1, run-0121).')

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
              'input_sha256':{str((ROOT/'platform/ps4'/p.name).relative_to(ROOT)):sha(p) for p in
                              (overlay/'kernelbase/pw_execution_mode.h',overlay/'kernelbase/pw_execution_policy.h')},
              'overlay_sha256':{str(p.relative_to(overlay)):sha(p) for p in sorted(overlay.rglob('*')) if p.is_file()}}
    if arch=='i386':manifest['builder_sha256']=sha(pathlib.Path(__file__))
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return modules
modules=build('x86_64',work,out)
modules32=build('i386',ROOT/'build/guest-hw-i386',ROOT/'out/guest-hw-i386')
print(json.dumps({name:e['sha256'] for name,e in modules.items()}|{'i386:'+name:e['sha256'] for name,e in modules32.items()}|{'revisions':len(revisions)}))
