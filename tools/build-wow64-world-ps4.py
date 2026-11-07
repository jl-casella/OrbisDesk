#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""B1 (pe32-en-explorer-plan.md P1): ntdll's Unix side with 32-bit threads inside a 64-bit process.

A 32-bit program runs today in a process of its own (W116, relaunched). The plan runs it as WoW64
threads of explorer instead, beside its 64-bit guests. Wine decides "WoW64" per process
(unix_private.h is_wow64(): wow_peb is set), so in a 64-bit process every thread would turn WoW64
the moment a 32-bit PEB exists. Here it becomes per thread:
- is_wow64() is true for a thread whose TEB has a 32-bit TEB (WowTebOffset), once the process has a
  32-bit PEB. A 32-bit main image keeps the old answer (every thread), so the relaunched mode is
  the same as before.
- NtSetInformationProcess class 1100 (PW_PROCESS_WOW64_WORLD, env.c pw_wow64_world_enable) creates
  the 32-bit world late, in a running 64-bit process: the 32-bit PEB (whose image is the 32-bit host
  the caller mapped), the 32-bit ntdll (loader.c), the API set map below 4 GiB and the address limit
  of a large-address-aware 32-bit program (virtual.c).
- NtCreateThreadEx with flag 0x01000000 (PW_THREAD_CREATE_WOW64) starts a WoW64 thread from a 64-bit
  one (thread.c), with its TEB below 4 GiB (virtual.c virtual_alloc_teb_ex), its CPU area for i386
  and a 32-bit stack. A 32-bit thread's own threads are WoW64 as they always were.
- ProcessWow64Information answers for the calling thread (process.c); get_cpu_area looks at the
  thread asked about (thread.c); the initial 32-bit code selector is 0x33 in every process
  (signal_x86_64.c, W137 set it only for a 32-bit main image).

Every unit whose code reads the changed header (is_wow64, in_wow64_call, wow_peb) is compiled again
here with that header first on the include path, from the source the hardware link uses now: the
proven Wine units (build/wine-boot/report.json), and env.c, signal_x86_64.c, system.c, virtual.c and
file.c from their own builders, whose sources are checked by hash. tools/build-wine-hardware.py puts
these objects in place of those ones. Run after tools/build-env-ps4.py, build-signal-ps4.py,
build-telemetry-ps4.py, build-audio-ps4.py and build-wine-directory-ps4.py.
"""
import hashlib,json,pathlib,re,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
UNIX=ROOT/'.deps/wine/ps4-unix';SOURCE=ROOT/'.deps/wine/source'
work=ROOT/'build/wow64-world-ps4';include=work/'include'
include.mkdir(parents=True,exist_ok=True)
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def rel(path):return str(pathlib.Path(path).resolve().relative_to(ROOT))
base=json.loads((ROOT/'build/wine-boot/report.json').read_text())
entries={e['unit']:e for e in base['results']}

# The source each unit of the hardware link has now, and the object it replaces there.
def builder_input(report_path,source,object_key=None):
    report=json.loads((ROOT/report_path).read_text())
    if object_key:report=report['objects'][object_key]
    if sha(ROOT/source)!=report['source_sha256']:raise SystemExit(source+' differs from its builder report')
    return ROOT/source,ROOT/report['object']
units={}
for unit in ('process','server','thread','cdrom','socket','loader','registry'):  # W242: registry
    command=entries[unit]['command'];source=pathlib.Path(command[command.index('-o')+2])
    if sha(source)!=entries[unit]['source_sha256']:raise SystemExit(unit+'.c differs from the proven build input')
    units[unit]=(source,ROOT/'build/wine-boot'/(unit+'.o'))
units['env']=builder_input('build/env-ps4/report.json','build/env-ps4/env.c')
units['signal_x86_64']=builder_input('build/signal-ps4/report.json','build/signal-ps4/signal_x86_64.c')
units['system']=builder_input('build/telemetry-ps4/report.json','build/telemetry-ps4/system.c')
units['virtual']=builder_input('build/audio-ps4/report.json','build/audio-ps4/virtual.c','virtual')
units['file']=builder_input('build/directory-ps4/report.json','build/directory-ps4/file.c')

# No other unit may read what the header changes (signal_arm, signal_arm64 and signal_i386 are
# compiled empty for x86_64; the harnesses are not linked).
uses=re.compile(r'\b(is_wow64|in_wow64_call|is_old_wow64|wow_peb|virtual_alloc_teb)\b')
for unit,entry in entries.items():
    if unit in units or unit in ('harness','loader-harness','signal_arm','signal_arm64','signal_i386'):continue
    command=entry['command'];source=pathlib.Path(command[command.index('-o')+2])
    if uses.search(source.read_text()):raise SystemExit(unit+'.c reads the WoW64 state too; add it to this builder')

texts={unit:source.read_text() for unit,(source,_) in units.items()}
def replace(unit,old,new):
    if texts[unit].count(old)!=1:raise SystemExit('%s.c context changed: %s'%(unit,old[:70]))
    texts[unit]=texts[unit].replace(old,new,1)

# unix_private.h: per-thread is_wow64(), the machine of 32-bit threads and the new entry points.
header=(SOURCE/'dlls/ntdll/unix/unix_private.h').read_text()
def header_replace(old,new):
    global header
    if header.count(old)!=1:raise SystemExit('unix_private.h context changed: '+old[:70])
    header=header.replace(old,new,1)
header_replace('''static inline BOOL is_wow64(void)
{
    return !!wow_peb;
}
''','''/* OrbisDesk (pe32-en-explorer-plan.md P1, tools/build-wow64-world-ps4.py): a 64-bit process can have
 * 32-bit threads (32-bit guests of explorer), so WoW64 is per thread there: the thread has a 32-bit
 * TEB. A 32-bit main image keeps the old answer, every thread. */
static inline BOOL is_wow64(void)
{
    if (!wow_peb) return FALSE;
    if (!is_machine_64bit( main_image_info.Machine )) return TRUE;
    return NtCurrentTeb()->WowTebOffset != 0;
}

/* the machine of this process's 32-bit threads */
static inline USHORT wow_machine(void)
{
    return is_machine_64bit( main_image_info.Machine ) ? IMAGE_FILE_MACHINE_I386 : main_image_info.Machine;
}

#ifdef __ORBIS__
/* NtSetInformationProcess( GetCurrentProcess(), PW_PROCESS_WOW64_WORLD, request, sizeof(request) ):
 * host_base 0 asks whether the world exists */
#define PW_PROCESS_WOW64_WORLD ((PROCESSINFOCLASS)1100)
/* NtCreateThreadEx flag: a WoW64 thread from a 64-bit thread */
#define PW_THREAD_CREATE_WOW64 0x01000000
struct pw_wow64_world_request
{
    ULONG64 host_base;          /* in: the 32-bit host image, mapped by the caller */
    ULONG64 world_peb;          /* out: the 32-bit PEB */
    WCHAR   image_path[260];    /* in: the host's DOS path, its 32-bit image and command line */
};
extern NTSTATUS pw_wow64_world_enable( struct pw_wow64_world_request *req );
extern NTSTATUS pw_wow64_load_ntdll32( ULONG *apiset32, void **ntdll32 );
extern void pw_virtual_set_wow_limit(void);
#endif
''')
header_replace('''extern NTSTATUS virtual_alloc_teb( struct thread_data *data );
''','''extern NTSTATUS virtual_alloc_teb( struct thread_data *data );
extern NTSTATUS virtual_alloc_teb_ex( struct thread_data *data, BOOL wow );
''')
(include/'unix_private.h').write_text(header)

# thread.c: the CPU area of the thread asked about; i386 for 32-bit threads of a 64-bit image;
# WoW64 threads started from 64-bit ones.
replace('thread','''    if (!is_wow64()) return NULL;
#ifdef _WIN64
    cpu = data->teb->TlsSlots[WOW64_TLS_CPURESERVED];''','''    if (!wow_peb || !data->teb->WowTebOffset) return NULL;  /* OrbisDesk P1: per thread */
#ifdef _WIN64
    cpu = data->teb->TlsSlots[WOW64_TLS_CPURESERVED];''')
replace('thread','''            ((get_machine_context_size( main_image_info.Machine ) + 7) & ~7) + sizeof(ULONG64);''',
        '''            ((get_machine_context_size( wow_machine() ) + 7) & ~7) + sizeof(ULONG64);''')
replace('thread','''        cpu->Machine = main_image_info.Machine;''','''        cpu->Machine = wow_machine();''')
replace('thread','''    if (flags & ~supported_flags)
        FIXME( "Unsupported flags %#x.\\n", flags );
''','''    BOOL pw_wow = FALSE;

#ifdef __ORBIS__
    /* OrbisDesk P1: a WoW64 thread started by a 64-bit thread, in the 32-bit world of this
     * 64-bit process (PW_PROCESS_WOW64_WORLD); its entry and argument are 32-bit addresses */
    if (flags & PW_THREAD_CREATE_WOW64)
    {
        flags &= ~PW_THREAD_CREATE_WOW64;
        if (!wow_peb || process != NtCurrentProcess() || !is_machine_64bit( main_image_info.Machine ) ||
            (ULONG_PTR)start >= limit_4g || (ULONG_PTR)param >= limit_4g)
        {
            fprintf( stderr, "PWWOW thread refused world=%p start=%p param=%p\\n", wow_peb, start, param );
            return STATUS_INVALID_PARAMETER;
        }
        pw_wow = TRUE;
    }
#endif
    if (flags & ~supported_flags)
        FIXME( "Unsupported flags %#x.\\n", flags );
''')
replace('thread','''    if ((status = virtual_alloc_teb( data ))) goto done;
    teb = data->teb;
    set_thread_id( data );
''','''    if ((status = virtual_alloc_teb_ex( data, is_wow64() || pw_wow ))) goto done;
    teb = data->teb;
    set_thread_id( data );
    /* W236: also the threads 32-bit code starts in the world (W235: gui-window32's thread was silent) */
    if (pw_wow || (wow_peb && is_wow64() && is_machine_64bit( main_image_info.Machine )))
        fprintf( stderr, "PWWOW thread tid=%04x teb=%p teb32=%p start=%p flags=%#x from=%s\\n",
                 (unsigned int)data->tid, teb, get_wow_teb( teb ), start, (unsigned int)flags, pw_wow ? "64" : "32" );
''')

# W262 (W261: Prince of Persia's launcher starts POP.exe, which needs the launcher's base): NtCreateUserProcess's switch
# hook (W043) also hands the starter's working directory and the variables it set to the relaunch
# (native/wine_hardware.c pw_hw_switch_context, weak: an ELF without the hardware launcher ignores it).
replace('process','''        if (!helper) pw_hw_switch_program( image, command );''','''        if (!helper)
        {
            /* OrbisDesk W262: the starter's working directory and the variables its environment set or changed */
            extern void pw_hw_switch_context( const char *dir, const char *env ) __attribute__((weak));
            if (pw_hw_switch_context)
            {
                static const char *const skip[] = {"PATH=", "TEMP=", "TMP=", "HOME=", "WINE", "PW_", "PROCESSOR_",
                    "PROGRAMFILES", "COMMONPROGRAMFILES", "PROGRAMW6432", "COMMONPROGRAMW6432", "SYSTEMROOT=",
                    "WINDIR=", "COMSPEC=", "USERPROFILE=", "APPDATA=", "LOCALAPPDATA=", "ALLUSERSPROFILE=",
                    "PROGRAMDATA=", "PUBLIC=", "SYSTEMDRIVE=", "="};
                const WCHAR *child = params->Environment, *own;
                const WCHAR *own_env = NtCurrentTeb()->Peb->ProcessParameters->Environment;
                const WCHAR *where = params->CurrentDirectory.DosPath.Buffer;
                char dir[400], env[2048];
                size_t used = 0, len, m;
                int count = 0;

                length = where ? params->CurrentDirectory.DosPath.Length / sizeof(WCHAR) : 0;
                while (length > 3 && where[length - 1] == '\\\\') length--;
                for (n = 0; n < length && n < sizeof(dir) - 1; n++) dir[n] = where[n] < 128 ? where[n] : '?';
                dir[n] = 0;
                env[0] = 0;
                for (; child && *child && count < 8; child += len + 1)
                {
                    BOOL keep = TRUE;

                    len = wcslen( child );
                    for (k = 0; k < ARRAY_SIZE(skip) && keep; k++)
                    {
                        const char *p = skip[k];
                        const WCHAR *c = child;
                        while (*p && *c && ((*c >= 'a' && *c <= 'z') ? *c - 32 : *c) == (WCHAR)*p) { p++; c++; }
                        if (!*p) keep = FALSE;
                    }
                    for (n = 0; n < len && keep; n++) if (child[n] < 32 || child[n] >= 128) keep = FALSE;
                    for (own = own_env; keep && own && *own; own += wcslen( own ) + 1)
                    {
                        for (m = 0; own[m] && own[m] == child[m]; m++);
                        if (!own[m] && !child[m]) keep = FALSE;
                    }
                    if (!keep || used + len + 2 > sizeof(env)) continue;
                    for (n = 0; n < len; n++) env[used++] = (char)child[n];
                    env[used++] = '\\n';
                    env[used] = 0;
                    count++;
                }
                pw_hw_switch_context( dir, env );
            }
            pw_hw_switch_program( image, command );
        }''')

# process.c: IsWow64Process answers for the calling thread; the world entry point.
replace('process','''            *(ULONG_PTR *)info = is_old_wow64() ? (ULONG_PTR)peb : (ULONG_PTR)wow_peb;''',
        '''            *(ULONG_PTR *)info = is_old_wow64() ? (ULONG_PTR)peb : is_wow64() ? (ULONG_PTR)wow_peb : 0;''')
replace('process','''    case ProcessWineMakeProcessSystem:
        if (size != sizeof(HANDLE *)) return STATUS_INFO_LENGTH_MISMATCH;''','''#ifdef __ORBIS__
    case PW_PROCESS_WOW64_WORLD:  /* OrbisDesk P1: the 32-bit world of this 64-bit process */
        if (handle != NtCurrentProcess()) return STATUS_INVALID_HANDLE;
        if (size != sizeof(struct pw_wow64_world_request)) return STATUS_INFO_LENGTH_MISMATCH;
        ret = pw_wow64_world_enable( info );
        break;
#endif

    case ProcessWineMakeProcessSystem:
        if (size != sizeof(HANDLE *)) return STATUS_INFO_LENGTH_MISMATCH;''')

# virtual.c: a WoW64 thread's TEB below 4 GiB; the 32-bit address limit, set late.
replace('virtual','''NTSTATUS virtual_alloc_teb( struct thread_data *data )
{
    sigset_t sigset;
    void *ptr = NULL;
    NTSTATUS status = STATUS_SUCCESS;
    SIZE_T block_size = 4 * page_size;

    server_enter_uninterrupted_section( &virtual_mutex, &sigset );
    if (next_free_teb)
    {
        ptr = next_free_teb;
        next_free_teb = *(void **)ptr;
        memset( ptr, 0, block_size );
    }
    else
    {
        if (!teb_block_pos)
        {''','''NTSTATUS virtual_alloc_teb( struct thread_data *data )
{
    return virtual_alloc_teb_ex( data, is_wow64() );
}

#ifdef __ORBIS__
/* OrbisDesk P1: the limit of a large-address-aware 32-bit program, for the 32-bit world of a 64-bit
 * process; TEB blocks reserved from now on are below it too */
void pw_virtual_set_wow_limit(void)
{
    if (!user_space_wow_limit) user_space_wow_limit = limit_4g - 1;
}
#endif

/* OrbisDesk P1: wow, a WoW64 thread (asked for explicitly in a 64-bit process); its TEB, which
 * 32-bit code reaches through a 32-bit FS base, is below 4 GiB */
NTSTATUS virtual_alloc_teb_ex( struct thread_data *data, BOOL wow )
{
    sigset_t sigset;
    void *ptr = NULL;
    NTSTATUS status = STATUS_SUCCESS;
    SIZE_T block_size = 4 * page_size;

    server_enter_uninterrupted_section( &virtual_mutex, &sigset );
    if (next_free_teb && (!wow || (ULONG_PTR)next_free_teb < limit_4g))
    {
        ptr = next_free_teb;
        next_free_teb = *(void **)ptr;
        memset( ptr, 0, block_size );
    }
    else
    {
        if (!teb_block_pos || (wow && (ULONG_PTR)teb_block >= limit_4g))
        {''')
replace('virtual','''    data->teb = init_teb( ptr, is_wow64() );
    list_add_head( &teb_list, &data->entry );''','''    data->teb = init_teb( ptr, wow );
    list_add_head( &teb_list, &data->entry );''')
# virtual.c: TlsFree clears its slot in the threads of its own world only. The 32-bit and the 64-bit
# loader hand out the same indices from their own bitmaps, and a 64-bit TlsFree would clear wow64's
# slots in the TEB64 of a 32-bit thread (WOW64_TLS_CPURESERVED is slot 1).
replace('virtual','''NTSTATUS virtual_clear_tls_index( ULONG index )
{
    struct thread_data *data;
    sigset_t sigset;
''','''NTSTATUS virtual_clear_tls_index( ULONG index )
{
    struct thread_data *data;
    sigset_t sigset;
    BOOL caller_wow = is_wow64();  /* OrbisDesk P1: the caller's world, 32- or 64-bit */
''')
replace('virtual','''            WOW_TEB *wow_teb = get_wow_teb( teb );
            if (wow_teb) wow_teb->TlsSlots[index] = 0;''','''            WOW_TEB *wow_teb = get_wow_teb( teb );
            if (!wow_teb != !caller_wow) continue;
            if (wow_teb) wow_teb->TlsSlots[index] = 0;''')
replace('virtual','''            WOW_TEB *wow_teb = get_wow_teb( teb );
            if (wow_teb)
            {
                if (wow_teb->TlsExpansionSlots)''','''            WOW_TEB *wow_teb = get_wow_teb( teb );
            if (!wow_teb != !caller_wow) continue;
            if (wow_teb)
            {
                if (wow_teb->TlsExpansionSlots)''')

# signal_x86_64.c: the compatibility-mode code selector for 32-bit threads in every process.
replace('signal_x86_64','''#elif defined(__ORBIS__)
        cs32_sel = 0x33;
#endif
    }
''','''#elif defined(__ORBIS__)
        cs32_sel = 0x33;
#endif
    }
#ifdef __ORBIS__
    /* OrbisDesk P1: a 64-bit process can start 32-bit threads later (its 32-bit world) */
    if (!cs32_sel) cs32_sel = 0x33;
#endif
''')

# loader.c: the 32-bit ntdll, late, with a status instead of ending the process.
replace('loader','''    load_ntdll_wow64_functions( module );
    TRACE("loaded %s at %p\\n", debugstr_w(path), module );
    free( path );
}
''','''    load_ntdll_wow64_functions( module );
    TRACE("loaded %s at %p\\n", debugstr_w(path), module );
    free( path );
}

#ifdef __ORBIS__
/***********************************************************************
 *           pw_wow64_load_ntdll32
 *
 * OrbisDesk P1: the 32-bit ntdll for the 32-bit world of this 64-bit process, as load_wow64_ntdll
 * maps it at the start of a 32-bit program, but returning a status (the process goes on) and
 * keeping this process's own Ctrl routine. Also the API set map for the 32-bit PEB, which needs an
 * address below 4 GiB (a copy when the 64-bit one is above).
 */
NTSTATUS pw_wow64_load_ntdll32( ULONG *apiset32, void **ntdll32 )
{
    static const WCHAR ntdllW[] = {'n','t','d','l','l','.','d','l','l',0};
    SECTION_IMAGE_INFORMATION info;
    UNICODE_STRING nt_name;
    void *module, *ctrl_routine = p__wine_ctrl_routine;
    unsigned int status;
    SIZE_T size;
    const WCHAR *wow64_dir;
    WCHAR *path;

    *apiset32 = 0;
    *ntdll32 = NULL;
    if (!(wow64_dir = get_machine_wow64_dir( IMAGE_FILE_MACHINE_I386 ))) return STATUS_NOT_SUPPORTED;
    path = malloc( sizeof("\\\\??\\\\C:\\\\windows\\\\system32\\\\ntdll.dll") * sizeof(WCHAR) );
    wcscpy( path, wow64_dir );
    wcscat( path, ntdllW );
    init_unicode_string( &nt_name, path );
    status = find_builtin_dll( &nt_name, NULL, &module, &size, &info, 0, limit_2g - 1,
                               IMAGE_FILE_MACHINE_I386, 0, FALSE, 0 );
    /* W234: wineserver reports STATUS_IMAGE_MACHINE_TYPE_MISMATCH for every i386 image in this
     * AMD64 process, after the view is mapped and in place of STATUS_IMAGE_NOT_AT_BASE; relocating
     * does nothing when the image is at its base */
    if ((status == STATUS_IMAGE_NOT_AT_BASE || status == STATUS_IMAGE_MACHINE_TYPE_MISMATCH) && module)
        status = virtual_relocate_module( module );
    free( path );
    if (status)
    {
        fprintf( stderr, "PWWOW ntdll32 failed status=%#x module=%p\\n", status, module );
        return status;
    }
    if ((ULONG_PTR)module + size > limit_4g) return STATUS_CONFLICTING_ADDRESSES;
    load_ntdll_wow64_functions( module );
    p__wine_ctrl_routine = ctrl_routine;
    *ntdll32 = module;

    if (peb->ApiSetMap)
    {
        const API_SET_NAMESPACE *map = peb->ApiSetMap;
        void *copy = NULL;
        SIZE_T copy_size = map->Size;

        if ((ULONG_PTR)map + map->Size <= limit_4g) *apiset32 = PtrToUlong( map );
        else if (!NtAllocateVirtualMemory( NtCurrentProcess(), &copy, limit_2g - 1, &copy_size,
                                           MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE ))
        {
            memcpy( copy, map, map->Size );  /* the namespace holds offsets only */
            *apiset32 = PtrToUlong( copy );
        }
    }
    return STATUS_SUCCESS;
}
#endif
''')

# env.c: the 32-bit world, built as init_peb builds it for a 32-bit program.
replace('env','''        wow_peb->SessionId                       = peb->SessionId;
    }
}
''','''        wow_peb->SessionId                       = peb->SessionId;
    }
}


#ifdef __ORBIS__
/*************************************************************************
 *		pw_wow64_world_enable
 *
 * OrbisDesk (pe32-en-explorer-plan.md P1): the 32-bit world of this 64-bit process, created the
 * first time a 32-bit program runs as a guest. 32-bit guests are WoW64 threads of this process;
 * they share this 32-bit PEB, whose image is the 32-bit host (orbis32host.exe, mapped by the
 * caller) and never a game, as explorer's PEB names explorer and not its 64-bit guests. The other
 * threads stay 64-bit (is_wow64() is per thread here). A failure leaves no world and changes
 * nothing the process uses.
 */
NTSTATUS pw_wow64_world_enable( struct pw_wow64_world_request *req )
{
    static pthread_mutex_t world_mutex = PTHREAD_MUTEX_INITIALIZER;
    PEB32 *peb32 = (PEB32 *)((char *)peb + page_size);
    RTL_USER_PROCESS_PARAMETERS params;
    const IMAGE_DOS_HEADER *dos;
    const IMAGE_NT_HEADERS32 *nt;
    void *ntdll32 = NULL, *wow64_params;
    ULONG apiset32 = 0;
    NTSTATUS status = STATUS_SUCCESS;
    USHORT len = 0;

    if (!is_win64 || !is_machine_64bit( main_image_info.Machine )) return STATUS_NOT_SUPPORTED;
    pthread_mutex_lock( &world_mutex );
    if (wow_peb)
    {
        req->world_peb = PtrToUlong( wow_peb );
        goto done;
    }
    if (!req->host_base)
    {
        status = STATUS_NOT_FOUND;
        goto done;
    }
    dos = (const IMAGE_DOS_HEADER *)(ULONG_PTR)req->host_base;
    if (req->host_base >= limit_4g || req->host_base & 0xffff || dos->e_magic != IMAGE_DOS_SIGNATURE)
    {
        status = STATUS_INVALID_IMAGE_FORMAT;
        goto done;
    }
    nt = (const IMAGE_NT_HEADERS32 *)((const char *)dos + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE || nt->FileHeader.Machine != IMAGE_FILE_MACHINE_I386 ||
        nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR32_MAGIC || (nt->FileHeader.Characteristics & IMAGE_FILE_DLL))
    {
        status = STATUS_INVALID_IMAGE_FORMAT;
        goto done;
    }
    while (len < ARRAY_SIZE(req->image_path) - 1 && req->image_path[len]) len++;
    if (!len)
    {
        status = STATUS_INVALID_PARAMETER;
        goto done;
    }

    pw_virtual_set_wow_limit();
    if ((status = pw_wow64_load_ntdll32( &apiset32, &ntdll32 ))) goto done;

    params = *peb->ProcessParameters;
    params.ImagePathName.Buffer = req->image_path;
    params.ImagePathName.Length = len * sizeof(WCHAR);
    params.ImagePathName.MaximumLength = (len + 1) * sizeof(WCHAR);
    params.CommandLine = params.ImagePathName;
    {
        /* W235: the 32-bit world's environment is explorer's with WINE_D3D_CONFIG=renderer=vulkan, as a
         * relaunched 32-bit program gets it (native/wine_hardware.c W127); explorer's renderer=no3d left
         * wined3d i386 without an adapter (ddraw, Direct3D 7: SuperMarioKart) */
        static const WCHAR d3dW[] = {'W','I','N','E','_','D','3','D','_','C','O','N','F','I','G','=',0};
        static const WCHAR vulkanW[] = {'W','I','N','E','_','D','3','D','_','C','O','N','F','I','G','=',
                                        'r','e','n','d','e','r','e','r','=','v','u','l','k','a','n',0};
        const WCHAR *src = params.Environment, *end = (const WCHAR *)((const char *)src + params.EnvironmentSize);
        WCHAR *env = src ? malloc( params.EnvironmentSize + sizeof(vulkanW) + sizeof(WCHAR) ) : NULL, *dst = env;

        if (env)
        {
            memcpy( dst, vulkanW, sizeof(vulkanW) );
            dst += ARRAY_SIZE(vulkanW);
            while (src < end && *src)
            {
                SIZE_T n = wcslen( src ) + 1;
                if (wcsncmp( src, d3dW, ARRAY_SIZE(d3dW) - 1 ))
                {
                    memcpy( dst, src, n * sizeof(WCHAR) );
                    dst += n;
                }
                src += n;
            }
            *dst++ = 0;
            params.Environment = env;
            params.EnvironmentSize = (dst - env) * sizeof(WCHAR);
        }
        wow64_params = build_wow64_parameters( &params );
        free( env );
    }

    peb32->ImageBaseAddress                = (ULONG)req->host_base;
    peb32->ProcessParameters               = PtrToUlong( wow64_params );
    peb32->ApiSetMap                       = apiset32;
    peb32->NumberOfProcessors              = peb->NumberOfProcessors;
    peb32->NtGlobalFlag                    = peb->NtGlobalFlag;
    peb32->CriticalSectionTimeout.QuadPart = peb->CriticalSectionTimeout.QuadPart;
    peb32->HeapSegmentReserve              = peb->HeapSegmentReserve;
    peb32->HeapSegmentCommit               = peb->HeapSegmentCommit;
    peb32->HeapDeCommitTotalFreeThreshold  = peb->HeapDeCommitTotalFreeThreshold;
    peb32->HeapDeCommitFreeBlockThreshold  = peb->HeapDeCommitFreeBlockThreshold;
    peb32->OSMajorVersion                  = peb->OSMajorVersion;
    peb32->OSMinorVersion                  = peb->OSMinorVersion;
    peb32->OSBuildNumber                   = peb->OSBuildNumber;
    peb32->OSPlatformId                    = peb->OSPlatformId;
    peb32->ImageSubSystem                  = nt->OptionalHeader.Subsystem;
    peb32->ImageSubSystemMajorVersion      = nt->OptionalHeader.MajorSubsystemVersion;
    peb32->ImageSubSystemMinorVersion      = nt->OptionalHeader.MinorSubsystemVersion;
    peb32->SessionId                       = peb->SessionId;
    __atomic_store_n( &wow_peb, peb32, __ATOMIC_RELEASE );
    req->world_peb = PtrToUlong( peb32 );
    fprintf( stderr, "PWWOW world peb32=%p host=%p ntdll32=%p apiset32=%#x limit=%#lx\\n",
             peb32, (void *)(ULONG_PTR)req->host_base, ntdll32, (unsigned int)apiset32,
             (unsigned long)user_space_wow_limit );
done:
    if (status) fprintf( stderr, "PWWOW world_failed status=%#x host=%p\\n", (unsigned int)status,
                         (void *)(ULONG_PTR)req->host_base );
    pthread_mutex_unlock( &world_mutex );
    return status;
}
#endif
''')

# W235 (pe32-en-explorer-plan.md P6): the guests' i386 ntdll, kernelbase and ucrtbase
# (tools/build-guest-hw.py, wine/lib/wine/i386-guest) load in explorer's 32-bit world, never in a
# relaunched 32-bit program: in a 64-bit process an i386 builtin is looked for there first.
replace('loader','''    for (i = 0; dll_paths[i]; i++)
    {
        ptr = file + pos;
        ptr = prepend( ptr, pe_dir, strlen(pe_dir) );
''','''    for (i = 0; dll_paths[i]; i++)
    {
#ifdef __ORBIS__
        if (search_machine == IMAGE_FILE_MACHINE_I386 && is_machine_64bit( main_image_info.Machine ))
        {
            static const char guest_dir[] = "/i386-guest";
            ptr = prepend( file + pos, guest_dir, sizeof(guest_dir) - 1 );
            ptr = prepend( ptr, dll_paths[i], strlen(dll_paths[i]) );
            status = open_builtin_pe_file( ptr, &attr, module, size_ptr, image_info, limit_low, limit_high,
                                           load_machine, prefer_native, offset );
            if (status != STATUS_DLL_NOT_FOUND)
            {
                TRACE( "W235 i386 guest builtin %s status %x\\n", debugstr_a(ptr), status );
                goto done;
            }
        }
#endif
        ptr = file + pos;
        ptr = prepend( ptr, pe_dir, strlen(pe_dir) );
''')

# W238 (d): a WoW64 thread of a 64-bit process (explorer's 32-bit world) exchanges only its native
# context with wineserver, which keeps none of i386 for a thread of an AMD64 process (select refuses a
# second context there). W236: every thread a 32-bit guest started suspended failed its wait_suspend
# and had an AMD64 context written over its i386 CPU area; it never ran.
replace('thread','''static void contexts_to_server( struct context_data server_contexts[2], CONTEXT *context )
{
    unsigned int count = 0;
    void *native_context = get_native_context( context );
    void *wow_context = get_wow_context( context );
''','''#ifdef __ORBIS__
/* OrbisDesk W238: in a 64-bit process the server has no WoW64 context for a thread (P2); a WoW64
 * thread's i386 context stays in its CPU area */
static void *pw_server_wow_context( CONTEXT *context )
{
    if (is_machine_64bit( main_image_info.Machine )) return NULL;
    return get_wow_context( context );
}
#else
#define pw_server_wow_context get_wow_context
#endif

static void contexts_to_server( struct context_data server_contexts[2], CONTEXT *context )
{
    unsigned int count = 0;
    void *native_context = get_native_context( context );
    void *wow_context = pw_server_wow_context( context );
''')
replace('thread','''static void contexts_from_server( CONTEXT *context, struct context_data server_contexts[2] )
{
    void *native_context = get_native_context( context );
    void *wow_context = get_wow_context( context );
''','''static void contexts_from_server( CONTEXT *context, struct context_data server_contexts[2] )
{
    void *native_context = get_native_context( context );
    void *wow_context = pw_server_wow_context( context );  /* OrbisDesk W238 */
''')

# W242 (1): the 32-bit registry view for explorer's 32-bit guests. wineserver redirects to Wow6432Node by
# process (create_key/open_key: is_wow64_process); explorer is AMD64, so a WoW64 thread asks for it with the
# server's own OBJ_KEY_WOW64 attribute, unless it wants the 64-bit view.
replace('registry','''    if ((ret = wine_server_alloc_object_attributes( attr, &objattr, &len ))) return ret;
    objattr->attributes |= OBJ_OPENIF | OBJ_CASE_INSENSITIVE;

    TRACE( "(%p,%s,%s,%x,%x,%p)\\n", attr->RootDirectory, debugstr_us(attr->ObjectName),
''','''    if ((ret = wine_server_alloc_object_attributes( attr, &objattr, &len ))) return ret;
    objattr->attributes |= OBJ_OPENIF | OBJ_CASE_INSENSITIVE;
#ifdef __ORBIS__
    /* OrbisDesk W242: a WoW64 thread of a 64-bit process sees the 32-bit view, as in a WoW64 process */
    if (is_wow64() && is_machine_64bit( main_image_info.Machine ) && !(access & KEY_WOW64_64KEY))
        objattr->attributes |= 0x100000;  /* OBJ_KEY_WOW64, server/registry.c */
#endif

    TRACE( "(%p,%s,%s,%x,%x,%p)\\n", attr->RootDirectory, debugstr_us(attr->ObjectName),
''')
replace('registry','''    attributes = attr->Attributes | OBJ_CASE_INSENSITIVE;
''','''    attributes = attr->Attributes | OBJ_CASE_INSENSITIVE;
#ifdef __ORBIS__
    /* OrbisDesk W242: as NtCreateKey */
    if (is_wow64() && is_machine_64bit( main_image_info.Machine ) && !(access & KEY_WOW64_64KEY))
        attributes |= 0x100000;  /* OBJ_KEY_WOW64, server/registry.c */
#endif
''')

# W244: in a 64-bit process wineserver has no i386 context (P2); a WoW64 thread's own i386 debug registers
# come from its cache. W242: call_user_exception_dispatcher asked CONTEXT_I386_ALL, went to the server, failed,
# and dispatched a zeroed context (esp=0 ss=0).
replace('signal_x86_64','''    if (needed_flags & CONTEXT_I386_DEBUG_REGISTERS) self = FALSE;
''','''    if (needed_flags & CONTEXT_I386_DEBUG_REGISTERS)
    {
#ifdef __ORBIS__
        if (self && is_machine_64bit( main_image_info.Machine ))  /* OrbisDesk W244 */
        {
            context->Dr0 = amd64_data->dr0;
            context->Dr1 = amd64_data->dr1;
            context->Dr2 = amd64_data->dr2;
            context->Dr3 = amd64_data->dr3;
            context->Dr6 = amd64_data->dr6;
            context->Dr7 = amd64_data->dr7;
            context->ContextFlags |= CONTEXT_I386_DEBUG_REGISTERS;
        }
        else
#endif
        self = FALSE;
    }
''')

# W246 (1): the legacy EXE window. In a 64-bit process (explorer) placement-free allocations keep out of
# [0x400000, 0x2000000) when there is room above, so a 32-bit EXE without relocations (Vice City) gets its
# base. W244: gta-vc.exe went to 00AE0000 unrelocated.
replace('virtual','''        if (limit_low && (void *)limit_low > start) start = (void *)limit_low;
        if (limit_high && (void *)limit_high < end) end = (char *)limit_high + 1;
''','''        if (limit_low && (void *)limit_low > start) start = (void *)limit_low;
        if (limit_high && (void *)limit_high < end) end = (char *)limit_high + 1;
#ifdef __ORBIS__
        /* OrbisDesk W246: keep the legacy EXE window [0x400000, 0x2000000) for 32-bit EXEs at their base */
        if (is_machine_64bit( main_image_info.Machine ) && !top_down &&
            (char *)start < (char *)0x2000000 && (char *)end > (char *)0x2000000)
        {
            if ((ptr = map_reserved_area( (void *)0x2000000, end, host_size, top_down, unix_prot, align_mask )))
                goto done;
            if ((start > address_space_start || end < host_addr_space_limit) &&
                (ptr = map_free_area( (void *)0x2000000, end, host_size, top_down, unix_prot, align_mask )))
                goto done;
        }
#endif
''')
# W246 (2): who holds the preferred base of a 32-bit image in a 64-bit process.
replace('virtual','''    if (base)
    {
        status = map_view( view_ret, base, size, alloc_type, vprot, limit_low, limit_high, 0 );
        if (!status) return status;
    }
''','''    if (base)
    {
        status = map_view( view_ret, base, size, alloc_type, vprot, limit_low, limit_high, 0 );
        if (!status) return status;
#ifdef __ORBIS__
        if (image_info->machine == IMAGE_FILE_MACHINE_I386 && is_machine_64bit( main_image_info.Machine ))
        {
            struct file_view *other = find_view_range( base, size );  /* OrbisDesk W246 */
            fprintf( stderr, "PWWOW image_not_at_base preferred=%p size=%#lx status=%#x occupied=%p+%#lx prot=%#x\\n",
                     base, (unsigned long)size, (unsigned int)status, other ? other->base : NULL,
                     other ? (unsigned long)other->size : 0ul, other ? (unsigned int)other->protect : 0u );
        }
#endif
    }
''')

# W249: the Wow6432Node of an opened key for explorer's 32-bit threads (wineserver's grab_wow6432node, which it
# applies only to a WoW64 process): the i386 combase's classes root is Software\Classes\Wow6432Node, so CLSIDs
# resolve in the 32-bit view (W248: "class {e436ebb3-...} not registered", VC's movies).
replace('registry','''NTSTATUS WINAPI NtCreateKey( HANDLE *key, ACCESS_MASK access, const OBJECT_ATTRIBUTES *attr,
''','''#ifdef __ORBIS__
/* OrbisDesk W249: the Wow6432Node of an opened key, for a WoW64 thread of a 64-bit process that did not ask
 * for the 64-bit view, as wineserver's grab_wow6432node does for a WoW64 process */
static void pw_world_wow6432node( HANDLE *key, ACCESS_MASK access, const OBJECT_ATTRIBUTES *attr )
{
    static const WCHAR wowW[] = {'W','o','w','6','4','3','2','N','o','d','e'};
    static LONG logged;
    UNICODE_STRING name = { sizeof(wowW), sizeof(wowW), (WCHAR *)wowW };
    OBJECT_ATTRIBUTES sub;
    HANDLE wow;

    if (!*key || !is_wow64() || !is_machine_64bit( main_image_info.Machine ) || (access & KEY_WOW64_64KEY)) return;
    InitializeObjectAttributes( &sub, &name, OBJ_CASE_INSENSITIVE, *key, NULL );
    if (NtOpenKeyEx( &wow, access | KEY_WOW64_64KEY, &sub, 0 )) return;
    if (InterlockedIncrement( &logged ) <= 32)
        fprintf( stderr, "PWWOW registry 32-bit view: %s -> its Wow6432Node\\n",
                 debugstr_us( attr->ObjectName ) );
    NtClose( *key );
    *key = wow;
}
#endif

NTSTATUS WINAPI NtCreateKey( HANDLE *key, ACCESS_MASK access, const OBJECT_ATTRIBUTES *attr,
''')
replace('registry','''    TRACE( "<- %p\\n", *key );
    free( objattr );
    return ret;
''','''#ifdef __ORBIS__
    if (!ret) pw_world_wow6432node( key, access, attr );  /* OrbisDesk W249 */
#endif
    TRACE( "<- %p\\n", *key );
    free( objattr );
    return ret;
''')
replace('registry','''    SERVER_END_REQ;
    TRACE("<- %p\\n", *key);
    return ret;
''','''    SERVER_END_REQ;
#ifdef __ORBIS__
    if (!ret) pw_world_wow6432node( key, access, attr );  /* OrbisDesk W249 */
#endif
    TRACE("<- %p\\n", *key);
    return ret;
''')

# W250: large views at a fixed address, in Wine's reserved areas or in its free area get direct memory, as W175's
# anonymous ones do (W248: the i386 Gecko's 69 MiB xul.dll found no flexible memory in explorer; mshtml failed).
replace('virtual','''                          ULONG_PTR limit_low, ULONG_PTR limit_high, size_t align_mask )
{
    int top_down = alloc_type & MEM_TOP_DOWN;
    void *ptr;
    int unix_prot = get_unix_prot( vprot );
    NTSTATUS status;
''','''                          ULONG_PTR limit_low, ULONG_PTR limit_high, size_t align_mask )
{
    int top_down = alloc_type & MEM_TOP_DOWN;
    void *ptr;
    int unix_prot = get_unix_prot( vprot );
    NTSTATUS status;
#ifdef __ORBIS__
    int pw_late_prot = 0;  /* OrbisDesk W250: backed at done:, direct memory first */
#endif
''')
replace('virtual','''        if ((status = map_fixed_area( base, size, unix_prot ))) return status;
''','''#ifdef __ORBIS__
        if (unix_prot && size >= 0x100000) pw_late_prot = unix_prot;  /* OrbisDesk W250 */
        if ((status = map_fixed_area( base, size, pw_late_prot ? PROT_NONE : unix_prot ))) return status;
#else
        if ((status = map_fixed_area( base, size, unix_prot ))) return status;
#endif
''')
replace('virtual','''        int pw_backing_prot = (unix_prot && view_size >= 0x100000) ? unix_prot : 0;
#endif
''','''        int pw_backing_prot = (unix_prot && view_size >= 0x100000) ? unix_prot : 0;
        int pw_area_prot = pw_backing_prot ? PROT_NONE : unix_prot;  /* OrbisDesk W250 */

        pw_late_prot = pw_backing_prot;
#else
        int pw_area_prot = unix_prot;
#endif
''')
for call in ('map_reserved_area( (void *)0x2000000, end, host_size, top_down, ',
             'map_free_area( (void *)0x2000000, end, host_size, top_down, ',
             'map_reserved_area( start, end, host_size, top_down, ',
             'map_free_area( start, end, host_size, top_down, '):
    replace('virtual', call + 'unix_prot, align_mask )', call + 'pw_area_prot, align_mask )')
replace('virtual','''#ifdef __ORBIS__
        if (pw_backing_prot && pw_direct_map( ptr, host_size, pw_backing_prot ) &&
''','''#ifdef __ORBIS__
        pw_late_prot = 0;  /* OrbisDesk W250: this path backs its own view (W175) */
        if (pw_backing_prot && pw_direct_map( ptr, host_size, pw_backing_prot ) &&
''')
replace('virtual','''done:
    status = create_view( view_ret, ptr, size, vprot );
''','''done:
#ifdef __ORBIS__
    if (pw_late_prot)  /* OrbisDesk W250: a large view placed PROT_NONE; direct memory, else flexible */
    {
        size_t host_size = ROUND_SIZE( 0, size, host_page_mask );

        if (pw_direct_map( ptr, host_size, pw_late_prot ) && mprotect( ptr, host_size, pw_late_prot ))
        {
            ERR( "PWVM view %p-%p (prot %#x) got no memory, errno %d\\n", ptr, (char *)ptr + host_size,
                 pw_late_prot, errno );
            unmap_area( ptr, host_size );
            return STATUS_NO_MEMORY;
        }
        if (pw_late_prot != (PROT_READ | PROT_WRITE)) mprotect( ptr, host_size, pw_late_prot );
    }
#endif
    status = create_view( view_ret, ptr, size, vprot );
''')

# W255 (W253: Vice City ended with no signal and no CE- code): Wine's own exits leave a line.
replace('thread','''void abort_process( int status )
{
    _exit( get_unix_exit_code( status ));''','''void abort_process( int status )
{
    fprintf( stderr, "PWEXIT abort_process status=%#x thread=%04x\\n", status,
             (unsigned int)HandleToULong( NtCurrentTeb()->ClientId.UniqueThread ) );  /* OrbisDesk W255 */
    _exit( get_unix_exit_code( status ));''')
replace('thread','''    pthread_sigmask( SIG_BLOCK, &server_block_set, NULL );
    if (InterlockedDecrement( &nb_threads ) <= 0) abort_process( status );''','''    pthread_sigmask( SIG_BLOCK, &server_block_set, NULL );
    if (InterlockedDecrement( &nb_threads ) <= 0)
    {
        fprintf( stderr, "PWEXIT last thread %04x aborted status=%#x nb_threads=%d\\n",  /* OrbisDesk W255 */
                 (unsigned int)HandleToULong( NtCurrentTeb()->ClientId.UniqueThread ), status, (int)nb_threads );
        abort_process( status );
    }''')
replace('thread','''    if (InterlockedDecrement( &nb_threads ) <= 0) exit_process( status );''','''    if (InterlockedDecrement( &nb_threads ) <= 0)
    {
        fprintf( stderr, "PWEXIT last thread %04x exits status=%#x nb_threads=%d\\n",  /* OrbisDesk W255 */
                 (unsigned int)HandleToULong( NtCurrentTeb()->ClientId.UniqueThread ), status, (int)nb_threads );
        exit_process( status );
    }''')
replace('server','''void process_exit_wrapper( int status )
{
    close( fd_socket );''','''void process_exit_wrapper( int status )
{
    fprintf( stderr, "PWEXIT process_exit status=%d thread=%04x\\n", status,
             (unsigned int)HandleToULong( NtCurrentTeb()->ClientId.UniqueThread ) );  /* OrbisDesk W255 */
    close( fd_socket );''')

objects={};inputs={}
for unit,(source,replaced) in sorted(units.items()):
    command=entries[unit]['command']
    original_source=command[command.index('-o')+2];original_object=command[command.index('-o')+1]
    selected=work/(unit+'.c');selected.write_text(texts[unit]);obj=work/(unit+'.o')
    recipe=[str(selected) if arg==original_source else str(obj) if arg==original_object else arg for arg in command]
    if recipe.count(str(selected))!=1 or recipe.count(str(obj))!=1:raise SystemExit(unit+'.o recipe changed')
    recipe[1:1]=['-I'+str(include)]  # the changed unix_private.h before every other copy
    with (work/(unit+'.log')).open('w') as log:
        run=subprocess.run(recipe,cwd=UNIX,stdout=log,stderr=subprocess.STDOUT)
    if run.returncode:raise SystemExit('cannot compile %s.c; see %s'%(unit,work/(unit+'.log')))
    objects[rel(replaced)]={'object':rel(obj),'sha256':sha(obj)}
    inputs[rel(source)]=sha(source)
report={'wine_commit':base['wine_commit'],'header_sha256':sha(include/'unix_private.h'),
        'original_header_sha256':sha(SOURCE/'dlls/ntdll/unix/unix_private.h'),'inputs':inputs,'replaces':objects,
        'sources':{unit:sha(work/(unit+'.c')) for unit in units},'builder_sha256':sha(pathlib.Path(__file__))}
(work/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'replaces':len(objects)}))
