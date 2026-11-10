#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""W137: prospero-win's native WoW64 CPU backend (wow64native) for the PS4 runtime.

32-bit code runs in the CPU's compatibility mode (CS 0x33, measured in W135) instead of
through the IA-32 translator. Needs ntdll's raw signal entry (W136, tools/build-signal-ps4.py):
wow64native asks __wine_prospero_native_wow64_caps(1) and refuses to start without it.

Unix side: wow64native's unix.c compiled for Orbis and linked into the boot ELF
(link-wine-boot.py), found by ntdll through pw_wine_unixlibs.c as wow64native.so.
PE side: wow64native.dll at image base 0x7a400000 (its 32->64 thunks must be below 4 GiB),
and a wow64.dll whose WINE_PS4_WOW64_CPU accepts wow64native.dll or wowprospero.dll and
falls back to wowprospero.dll when wow64native's BTCpuProcessInit fails (prospero-win
patches 0611 and 0614). Every adaptation keeps the original and records both hashes.

Deliberate difference from PS5: ntdll on Orbis reports caps 1|2 only (Wine's Orbis signal
context keeps no xstate), so the Unix side requires those two bits and logs that exceptions
in 32-bit code do not carry the upper YMM halves.
"""
import hashlib,json,pathlib,shlex,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
# Keep the checkout and $HOME out of __FILE__ strings and debug info.
PREFIX_MAP=['-ffile-prefix-map=%s=.'%ROOT,'-ffile-prefix-map=%s=vk-h0'%(pathlib.Path.home()/'vk-h0')]
UP=ROOT/'upstream/prospero-win';MODULE=UP/'wine/wow64native'
WINE=ROOT/'.deps/wine/source';HOST=ROOT/'.deps/wine/runtime/build';UNIX=ROOT/'.deps/wine/ps4-unix'
work=ROOT/'build/wow64native-ps4';out=ROOT/'out/wow64native-ps4'
for path in (work/'src',work/'unix',work/'pe',out/'x86_64-windows'):path.mkdir(parents=True,exist_ok=True)
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def run(command,cwd=ROOT):
    with (work/'build.log').open('a') as handle:
        handle.write('$ '+' '.join(map(str,command))+'\n');handle.flush()
        subprocess.run(list(map(str,command)),cwd=cwd,check=True,stdout=handle,stderr=subprocess.STDOUT)
def adapt(original,target,replacements):
    text=original.read_text()
    for old,new in replacements:
        if text.count(old)!=1:raise SystemExit('Unexpected context in '+str(original)+': '+old[:70])
        text=text.replace(old,new)
    target.write_text(text)
    return {'original':str(original.relative_to(ROOT)),'original_sha256':sha(original),
            'adapted':str(target.relative_to(ROOT)),'adapted_sha256':sha(target)}
(work/'build.log').write_text('')
commit=subprocess.check_output(['git','-C',str(WINE),'rev-parse','HEAD'],text=True).strip()
if commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('Wine source is not the pinned revision')
adaptations=[]

# Unix side
unix_c=work/'src/unix.c'
adaptations.append(adapt(MODULE/'unix.c',unix_c,[
    ('#ifdef __PROSPERO__\n    extern int sysarch(int, void *);\n    /* Called with host FS active',
     '#if defined(__PROSPERO__) || defined(__ORBIS__)\n    extern int sysarch(int, void *);\n    /* Called with host FS active'),
    ('#ifdef __PROSPERO__\n    {\n        extern int sysarch(int, void *);',
     '#if defined(__PROSPERO__) || defined(__ORBIS__)\n    {\n        extern int sysarch(int, void *);'),
    # W168: the FS selector 32-bit code resumes with after an exception or NtContinue (cpu.c loads
    # context->SegFs, which it fills with fs32_sel, on the RESET_STATE iretq path). 0 is a null
    # selector, unusable for memory in compatibility mode: SuperMarioKart's C++ exceptions (Blitz3D,
    # every race since W153) resumed with fs=0000 and faulted at the next fs:0x18 (TEB) read,
    # in RtlNtStatusToDosError. FreeBSD runs every user thread with its own user FS selector
    # (_ufssel, 0x13 in the contexts of the W167 log) and the base in the MSR that sysarch sets;
    # that is the selector to resume with, read from this thread, which runs with host FS.
    ('    params->fs32_selector = 0;\n',
     '''    params->fs32_selector = 0;
#ifdef __ORBIS__
    {
        unsigned short selector;
        __asm__ volatile( "movw %%fs,%0" : "=r"(selector) );
        params->fs32_selector = selector;
        WINE_MESSAGE("PWNATIVE fs32_selector=%#x\\n", selector);
    }
#endif
'''),
    ('        query = dlsym(RTLD_DEFAULT, PW_NATIVE_SIGNAL_QUERY);\n        if (!query) return STATUS_NOT_SUPPORTED;\n        caps = query(PW_NW64_CAPS_VERSION);\n        if ((caps & PW_NW64_CAP_REQUIRED) != PW_NW64_CAP_REQUIRED)\n            return STATUS_NOT_SUPPORTED;',
     '''#ifdef __ORBIS__
        /* OrbisDesk: ntdll is linked into the same ELF (tools/build-signal-ps4.py). Its
         * signal context keeps no xstate, so bit 4 is not reported and not required here:
         * an exception in 32-bit code does not carry the upper YMM halves. */
        query = __wine_prospero_native_wow64_caps;
        caps = query(PW_NW64_CAPS_VERSION);
        if ((caps & (PW_NW64_CAP_RAW_TITLESAFE_HANDLERS | PW_NW64_CAP_HOST_FS_BEFORE_C)) !=
            (PW_NW64_CAP_RAW_TITLESAFE_HANDLERS | PW_NW64_CAP_HOST_FS_BEFORE_C))
        {
            WINE_MESSAGE("PWNATIVE wow64native refused: caps=%u\\n", caps);
            return STATUS_NOT_SUPPORTED;
        }
        WINE_MESSAGE("PWNATIVE wow64native caps=%u (no xstate in exception contexts)\\n", caps);
#else
        query = dlsym(RTLD_DEFAULT, PW_NATIVE_SIGNAL_QUERY);
        if (!query) return STATUS_NOT_SUPPORTED;
        caps = query(PW_NW64_CAPS_VERSION);
        if ((caps & PW_NW64_CAP_REQUIRED) != PW_NW64_CAP_REQUIRED)
            return STATUS_NOT_SUPPORTED;
#endif''')]))
wine_flags=['-I'+str(WINE/'include'),'-Iinclude','-D__WINESRC__','-D_NTSYSTEM_','-DWINE_UNIX_LIB','-D_REENTRANT',
            '-Wall','-fcf-protection=none','-fvisibility=hidden','-fno-stack-protector','-fno-strict-aliasing',
            '-gdwarf-4','-fasynchronous-unwind-tables','-g','-O2','-D__ORBIS__','-I'+str(ROOT/'platform/ps4'),
            '-ffunction-sections','-fdata-sections','-include',str(ROOT/'platform/ps4/pw_wine_posix.h'),*PREFIX_MAP]
unix_object=work/'unix/unix.o'
run([UNIX/'orbis-cc','-c','-o',unix_object,unix_c,*wine_flags,'-I'+str(MODULE),
     '-D__wine_unix_call_funcs=pw_wow64native_unix_call_funcs'],cwd=UNIX)

# PE side: wow64native.dll, as prospero-win's tools/build_wow64native.sh links it.
pe_flags=['-I'+str(MODULE),'-I'+str(HOST/'include'),'-I'+str(WINE/'include'),'-I'+str(WINE/'include/msvcrt'),
          '-D_MSVCR_VER=0','-D__WINESRC__','-D__WINE_PE_BUILD','-Wall','-fno-strict-aliasing',
          '-mcx16','-mcmodel=small','-O2','-g','-fno-builtin','-fshort-wchar',*PREFIX_MAP]
# W169: and the RESET_STATE return (NtContinue after an exception) loads that selector instead of
# context->SegFs. W168 set fs32_sel to 0x13, but the contexts 32-bit code hands to
# NtRaiseException/NtContinue come from its own RtlCaptureContext and still carry fs=0000, so the
# resumed code still faulted at fs:0x18. The guest FS is never anything else here: its base is
# the TEB, set by pw_native_restore_guest_fs right after.
cpu_c=work/'src/cpu.c'
adaptations.append(adapt(MODULE/'cpu.c',cpu_c,[
    ('                   "mov 0x90(%r13),%fs\\n\\t"     /* context->SegFs */\n',
     '                   "movzwl " __ASM_NAME("fs32_sel") "(%rip),%eax\\n\\t"  /* OrbisDesk W169: not context->SegFs */\n'
     '                   "mov %ax,%fs\\n\\t"\n'),
    # W170: the end of a SuperMarioKart race calls TerminateThread(NULL). NtTerminateThread(0) is not
    # the current thread: it fails with STATUS_INVALID_HANDLE and the caller keeps running, but
    # BTCpuThreadTerm took NULL as the current thread and cleared its state first, guest FS base
    # included, so the next pw_native_restore_guest_fs set base 0 and RtlNtStatusToDosError faulted
    # at fs:0x18 (W165-W169: the thread's final PW_NATIVE_PROFILE right before each fault).
    ('    if (!thread || thread == GetCurrentThread()) WINE_UNIX_CALL(pw_native_thread_term, NULL);\n',
     '''    /* OrbisDesk W170: only the current thread, by pseudo-handle or by a real handle to it.
     * NULL is an invalid handle to NtTerminateThread, which then returns to the caller. */
    if (thread != GetCurrentThread())
    {
        THREAD_BASIC_INFORMATION info;
        if (!thread || NtQueryInformationThread( thread, ThreadBasicInformation, &info, sizeof(info), NULL )) return;
        if (info.ClientId.UniqueThread != NtCurrentTeb()->ClientId.UniqueThread) return;
    }
    WINE_UNIX_CALL(pw_native_thread_term, NULL);
'''),
    # B1 (pe32-en-explorer-plan.md section 4): in a 64-bit process (32-bit guests of explorer) a 32-bit
    # thread whose state is missing ends alone; the process is explorer and everything open in it.
    ('void * WINAPI pw_native_prepare_simulate(void)\n{\n',
     '''/* OrbisDesk B1: a 32-bit thread of a 64-bit process ends alone */
static void pw_end_after_failure( NTSTATUS status )
{
    const IMAGE_NT_HEADERS *nt = RtlImageNtHeader( NtCurrentTeb()->Peb->ImageBaseAddress );

    if (nt && nt->FileHeader.Machine == IMAGE_FILE_MACHINE_AMD64)
    {
        ERR( "PWWOW wow64native thread %04lx not ready (%lx): this 32-bit thread ends\\n",
             HandleToULong( NtCurrentTeb()->ClientId.UniqueThread ), status );
        NtTerminateThread( GetCurrentThread(), status );
    }
    NtTerminateProcess( GetCurrentProcess(), status );
}

void * WINAPI pw_native_prepare_simulate(void)
{
'''),
    ('        NtTerminateProcess(GetCurrentProcess(), status);\n        RtlRaiseStatus(status);\n',
     '        pw_end_after_failure(status);\n        RtlRaiseStatus(status);\n'),
    # W262 (W261: NFS Underground 2 and Most Wanted unmask x87 exceptions; a pending one fired at an FWAIT in musl's
    # malloc, in 64-bit code, c0000090 that nothing could dispatch): the guest's x87/SSE state is saved at each
    # 32->64 transition and restored at each 64->32 one; the 64-bit side runs with this thread's own control words.
    # BTCpuSimulate's frame: guest FXSAVE image at 0x30, 64-bit FCW at 0x330 and MXCSR at 0x334.
    ('                   "fxrstor64 0x30(%rsp)\\n\\t"\n                   PW_RESTORE_YMM_HIGH("0x230")\n',
     '                   "fxrstor64 0x30(%rsp)\\n\\t"\n                   PW_RESTORE_YMM_HIGH("0x230")\n'
     '                   "fnstcw 0x330(%rsp)\\n\\t"     /* OrbisDesk W262: this thread\'s 64-bit FCW */\n'
     '                   "stmxcsr 0x334(%rsp)\\n\\t"    /* and MXCSR; 0x30 holds the guest\'s first state */\n'),
    ('                   "call pw_native_restore_host_fs\\n\\t"\n                   "movq %rax,%rcx\\n\\t"',
     '                   "call pw_native_restore_host_fs\\n\\t"\n'
     '                   "fxsave64 0x30(%rsp)\\n\\t"    /* OrbisDesk W262: the guest\'s x87/SSE state */\n'
     '                   "fninit\\n\\t"\n'
     '                   "fldcw 0x330(%rsp)\\n\\t"\n'
     '                   "ldmxcsr 0x334(%rsp)\\n\\t"\n'
     '                   "movq %rax,%rcx\\n\\t"'),
    ('                   "call pw_native_restore_host_fs\\n\\t"\n                   "movq 4(%r14),%rcx\\n\\t"',
     '                   "call pw_native_restore_host_fs\\n\\t"\n'
     '                   "fxsave64 0x30(%rsp)\\n\\t"    /* OrbisDesk W262: the guest\'s x87/SSE state */\n'
     '                   "fninit\\n\\t"\n'
     '                   "fldcw 0x330(%rsp)\\n\\t"\n'
     '                   "ldmxcsr 0x334(%rsp)\\n\\t"\n'
     '                   "movq 4(%r14),%rcx\\n\\t"'),
    ('                   "syscall_32to64_return:\\n\\t"\n',
     '                   "syscall_32to64_return:\\n\\t"\n'
     '                   "fxrstor64 0x30(%rsp)\\n\\t"   /* OrbisDesk W262: the guest\'s x87/SSE state */\n'),
    ('                   "callq *__wine_unix_call_dispatcher(%rip)\\n\\t"\n                   "movl %eax,0xb0(%r13)\\n\\t"',
     '                   "callq *__wine_unix_call_dispatcher(%rip)\\n\\t"\n'
     '                   "fxrstor64 0x30(%rsp)\\n\\t"   /* OrbisDesk W262: the guest\'s x87/SSE state */\n'
     '                   "movl %eax,0xb0(%r13)\\n\\t"')]))
run(['x86_64-w64-mingw32-gcc','-c','-o',work/'pe/cpu.o',cpu_c,*pe_flags])
dll=out/'x86_64-windows/wow64native.dll'
run([HOST/'tools/winegcc/winegcc','-o',dll,'--wine-objdir','.','--cc-cmd=x86_64-w64-mingw32-gcc','-b','x86_64-w64-mingw32',
     '-Wl,--wine-builtin','-shared',MODULE/'wow64native.spec','-nodefaultlibs','-Wl,--image-base,0x7a400000',work/'pe/cpu.o',
     'dlls/wow64/x86_64-windows/libwow64.a','dlls/ntdll/x86_64-windows/libntdll.a',
     'libs/winecrt0/x86_64-windows/libwinecrt0.a','dlls/ntdll/x86_64-windows/libntdll.a',
     'libs/compiler-rt/x86_64-windows/libcompiler-rt.a'],cwd=HOST)

# PE side: wow64.dll choosing the backend from WINE_PS4_WOW64_CPU, with the translator as
# fallback (prospero-win patches 0611 and 0614).
selection='''/**********************************************************************
 *           load_environment_cpu_dll
 *
 * PS4: WINE_PS4_WOW64_CPU names this process's CPU backend, wow64native.dll (32-bit
 * code in compatibility mode) or wowprospero.dll (the IA-32 translator). When it cannot
 * be loaded the prefix's own choice is used. Adapted from prospero-win patch 0611.
 */
static BOOL environment_cpu_native;

static HMODULE load_environment_cpu_dll(void)
{
    static const WCHAR * const names[] = { L"wow64native.dll", L"wowprospero.dll" };
    static const char * const ascii[] = { "wow64native.dll", "wowprospero.dll" };
    const WCHAR *dir = get_machine_wow64_dir( IMAGE_FILE_MACHINE_TARGET_HOST );
    WCHAR value[32], path[MAX_PATH];
    UNICODE_STRING name, str;
    HMODULE module;
    NTSTATUS status;
    unsigned int i;

    RtlInitUnicodeString( &name, L"WINE_PS4_WOW64_CPU" );
    str.Buffer = value;
    str.Length = 0;
    str.MaximumLength = sizeof(value) - sizeof(WCHAR);
    if (RtlQueryEnvironmentVariable_U( NULL, &name, &str )) return NULL;
    value[str.Length / sizeof(WCHAR)] = 0;
    for (i = 0; i < ARRAY_SIZE(names); i++) if (!wcscmp( value, names[i] )) break;
    if (i == ARRAY_SIZE(names))
    {
        ERR( "ignoring WINE_PS4_WOW64_CPU: not wow64native.dll or wowprospero.dll\\n" );
        return NULL;
    }
    swprintf( path, MAX_PATH, L"%s\\\\%s", dir, names[i] );
    RtlInitUnicodeString( &str, path );
    if ((status = LdrLoadDll( dir, 0, &str, &module )))
    {
        ERR( "%s not loaded (%lx); using the prefix's CPU\\n", ascii[i], status );
        return NULL;
    }
    MESSAGE( "wow64: CPU %s from WINE_PS4_WOW64_CPU\\n", ascii[i] );
    environment_cpu_native = (i == 0);
    return module;
}


'''
get_ptrs='''#define GET_CPU_PTRS() do { \\
    GET_PTR( BTCpuGetBopCode ); \\
    GET_PTR( BTCpuGetContext ); \\
    GET_PTR( BTCpuIsProcessorFeaturePresent ); \\
    GET_PTR( BTCpuProcessInit ); \\
    GET_PTR( BTCpuThreadInit ); \\
    GET_PTR( BTCpuResetToConsistentState ); \\
    GET_PTR( BTCpuSetContext ); \\
    GET_PTR( BTCpuSimulate ); \\
    GET_PTR( BTCpuFlushInstructionCache2 ); \\
    GET_PTR( BTCpuFlushInstructionCacheHeavy ); \\
    GET_PTR( BTCpuNotifyMapViewOfSection ); \\
    GET_PTR( BTCpuNotifyMemoryAlloc ); \\
    GET_PTR( BTCpuNotifyMemoryDirty ); \\
    GET_PTR( BTCpuNotifyMemoryFree ); \\
    GET_PTR( BTCpuNotifyMemoryProtect ); \\
    GET_PTR( BTCpuNotifyProcessExecuteFlagsChange ); \\
    GET_PTR( BTCpuNotifyReadFile ); \\
    GET_PTR( BTCpuNotifyUnmapViewOfSection ); \\
    GET_PTR( BTCpuUpdateProcessorInformation ); \\
    GET_PTR( BTCpuProcessTerm ); \\
    GET_PTR( BTCpuThreadTerm ); \\
    GET_PTR( __wine_get_unix_opcode ); \\
} while (0)
'''
old_ptrs=''.join('    GET_PTR( %s );\n'%n for n in ('BTCpuGetBopCode','BTCpuGetContext','BTCpuIsProcessorFeaturePresent',
    'BTCpuProcessInit','BTCpuThreadInit','BTCpuResetToConsistentState','BTCpuSetContext','BTCpuSimulate',
    'BTCpuFlushInstructionCache2','BTCpuFlushInstructionCacheHeavy','BTCpuNotifyMapViewOfSection','BTCpuNotifyMemoryAlloc',
    'BTCpuNotifyMemoryDirty','BTCpuNotifyMemoryFree','BTCpuNotifyMemoryProtect','BTCpuNotifyProcessExecuteFlagsChange',
    'BTCpuNotifyReadFile','BTCpuNotifyUnmapViewOfSection','BTCpuUpdateProcessorInformation','BTCpuProcessTerm',
    'BTCpuThreadTerm','__wine_get_unix_opcode'))
syscall_c=work/'src/syscall.c'
adaptations.append(adapt(WINE/'dlls/wow64/syscall.c',syscall_c,[
    ('/**********************************************************************\n *           get_cpu_dll_name\n',
     selection+'/**********************************************************************\n *           get_cpu_dll_name\n'),
    ('#define GET_PTR(name) p ## name = RtlFindExportedRoutineByName( module, #name )\n',
     '#define GET_PTR(name) p ## name = RtlFindExportedRoutineByName( module, #name )\n'+get_ptrs),
    ('    module = load_64bit_module( get_cpu_dll_name() );\n'+old_ptrs,
     '    if (!(module = load_environment_cpu_dll())) module = load_64bit_module( get_cpu_dll_name() );\n    GET_CPU_PTRS();\n'),
    ('    pBTCpuProcessInit();\n\n    module = (HMODULE)(ULONG_PTR)pLdrSystemDllInitBlock->ntdll_handle;',
     '''    /* PS4 (prospero-win patch 0614): wow64native.dll refuses to start when ntdll does not
     * report the signal path it needs; run the program on the translator then instead of
     * ending it at its first 32-bit instruction. Its failed init changes nothing. */
    if (environment_cpu_native)
    {
        NTSTATUS status = ((NTSTATUS (WINAPI *)(void))pBTCpuProcessInit)();
        if (status)
        {
            ERR( "wow64native.dll did not start (%lx); using wowprospero.dll\\n", status );
            module = load_64bit_module( L"wowprospero.dll" );
            GET_CPU_PTRS();
            pBTCpuProcessInit();
        }
    }
    else pBTCpuProcessInit();

    module = (HMODULE)(ULONG_PTR)pLdrSystemDllInitBlock->ntdll_handle;'''),
    ('#undef GET_PTR\n','#undef GET_CPU_PTRS\n#undef GET_PTR\n'),
    # B1 (pe32-en-explorer-plan.md P4): 32-bit threads of a 64-bit process (explorer's 32-bit guests).
    # The process's machine is AMD64 there, so the emulated one is i386 for a WoW64 thread; a failure
    # that would end the process ends that thread.
    ('''/**********************************************************************
 *           load_64bit_module
 */''','''/* OrbisDesk B1 (pe32-en-explorer-plan.md P4): 32-bit guests of a 64-bit process (explorer) */
BOOL pw_wow64_world = FALSE;
static BOOL pw_traced( void );  /* alpha-1: the trace switch, below */
/* wow64win's callback table: the PEB's is 64-bit user32's there, so each 32-bit thread gets it in this
 * TEB slot of wow64's reserved range, which the PE ntdll's KiUserCallbackDispatcher reads */
#define PW_WOW64_TLS_CALLBACKS 18
static void *pw_callback_table;

static void pw_wow64_fatal( NTSTATUS status )
{
    if (pw_wow64_world)
    {
        ERR( "PWWOW world_failed thread=%04lx status=%lx: this 32-bit thread ends, not the process\\n",
             HandleToULong( NtCurrentTeb()->ClientId.UniqueThread ), status );
        NtTerminateThread( GetCurrentThread(), status );
    }
    NtTerminateProcess( GetCurrentProcess(), status );
}


/**********************************************************************
 *           load_64bit_module
 */'''),
    ('''        ERR( "failed to load dll %lx\\n", status );
        NtTerminateProcess( GetCurrentProcess(), status );''','''        ERR( "failed to load dll %lx\\n", status );
        pw_wow64_fatal( status );'''),
    ('''    RtlWow64GetProcessMachines( GetCurrentProcess(), &current_machine, &native_machine );
    if (!current_machine) current_machine = native_machine;
''','''    RtlWow64GetProcessMachines( GetCurrentProcess(), &current_machine, &native_machine );
    if (!current_machine) current_machine = native_machine;
    if (current_machine == IMAGE_FILE_MACHINE_AMD64 && NtCurrentTeb()->WowTebOffset)
    {
        /* OrbisDesk B1: the first 32-bit thread of a 64-bit process (the 32-bit world of explorer) */
        current_machine = IMAGE_FILE_MACHINE_I386;
        pw_wow64_world = TRUE;
        ERR( "PWWOW wow64 process_init in a 64-bit process: emulating i386\\n" );
    }
'''),
    ('''    module = load_64bit_module( L"wow64win.dll" );
    GET_PTR( sdwhwin32 );''','''    module = load_64bit_module( L"wow64win.dll" );
    if (pw_wow64_world)  /* OrbisDesk B1: wow64win left its table in this thread's slot */
    {
        pw_callback_table = NtCurrentTeb()->TlsSlots[PW_WOW64_TLS_CALLBACKS];
        if (!pw_callback_table) ERR( "PWWOW wow64win.dll set no callback table (not B1's?)\\n" );
    }
    GET_PTR( sdwhwin32 );'''),
    ('''    NtCurrentTeb32()->WOW32Reserved = PtrToUlong( pBTCpuGetBopCode() );
    NtCurrentTeb()->TlsSlots[WOW64_TLS_WOW64INFO] = wow64info;''','''    NtCurrentTeb32()->WOW32Reserved = PtrToUlong( pBTCpuGetBopCode() );
    NtCurrentTeb()->TlsSlots[WOW64_TLS_WOW64INFO] = wow64info;
    if (pw_wow64_world)
    {
        NtCurrentTeb()->TlsSlots[PW_WOW64_TLS_CALLBACKS] = pw_callback_table;  /* OrbisDesk B1 */
        if (pw_traced())  /* alpha-1 */
            ERR( "PWWOW wow64 thread_init thread=%04lx\\n", HandleToULong( NtCurrentTeb()->ClientId.UniqueThread ) );  /* W236 */
    }'''),
    # W236 (W235 run-0003.log: 207 nested c0000005 at wow64+0x11ACD): an exception whose 32-bit context has no
    # stack (esp 0) cannot reach 32-bit code; in the world it ends that thread instead of faulting again.
    ('''void WINAPI Wow64PassExceptionToGuest( EXCEPTION_POINTERS *ptrs )
{
    EXCEPTION_RECORD32 rec32;
''','''void WINAPI Wow64PassExceptionToGuest( EXCEPTION_POINTERS *ptrs )
{
    EXCEPTION_RECORD32 rec32;

    if (pw_wow64_world)
    {
        I386_CONTEXT ctx32 = { CONTEXT_I386_CONTROL };
        ULONG esp = 0;

        /* W239 (W238: 15.4k nested faults; the context's Esp was not 0): the stack call_user_exception_dispatcher
         * uses, which is TEB32->SystemReserved1[0] when SegSs is not ss32_sel (0 in explorer's world) */
        if (!pBTCpuGetContext( GetCurrentThread(), GetCurrentProcess(), NULL, &ctx32 ))
            esp = LOWORD(ctx32.SegSs) != ss32_sel ? NtCurrentTeb32()->SystemReserved1[0] : ctx32.Esp;
        if (esp < 0x10000)
        {
            ERR( "PWWOW guest32 exception %lx at %p: no 32-bit stack to pass it to (esp=%lx ss=%lx/%x context_esp=%lx); "
                 "this 32-bit thread ends\\n", ptrs->ExceptionRecord->ExceptionCode, ptrs->ExceptionRecord->ExceptionAddress,
                 esp, ctx32.SegSs, ss32_sel, ctx32.Esp );
            NtTerminateThread( GetCurrentThread(), ptrs->ExceptionRecord->ExceptionCode );
        }
    }
'''),
    # W240 (W239: Wow64PassExceptionToGuest's check passed, the dispatcher then computed esp 0 and recursed):
    # the check where the 32-bit frame is placed.
    ("""            esp = LOWORD(ctx.SegSs) != ss32_sel ? NtCurrentTeb32()->SystemReserved1[0] : ctx.Esp;
""","""            esp = LOWORD(ctx.SegSs) != ss32_sel ? NtCurrentTeb32()->SystemReserved1[0] : ctx.Esp;
            {
                extern BOOL pw_wow64_world;  /* OrbisDesk B1, below */

                /* OrbisDesk W242: a fault in 32-bit code (BTCpuResetToConsistentState put its context in the
                 * CPU area) has its own Esp; SystemReserved1[0], the dispatcher's choice when SegSs is not
                 * ss32_sel, is never set in explorer's world. The program's SEH gets the exception. */
                if (pw_wow64_world && esp < 0x10000 && LOWORD(ctx.SegSs) != ss32_sel && ctx.Esp >= 0x10000)
                {
                    static LONG logged;

                    if (InterlockedIncrement( &logged ) <= 32)
                        ERR( "PWWOW guest32 exception %x at %x: dispatched on its own stack esp=%x (ss=%x, ss32=%x)\\n",
                             (int)rec->ExceptionCode, (int)rec->ExceptionAddress, (int)ctx.Esp, (int)ctx.SegSs,
                             (int)ss32_sel );
                    esp = ctx.Esp;
                }
                if (pw_wow64_world && esp < 0x10000)  /* OrbisDesk W240 */
                {
                    ERR( "PWWOW guest32 exception %x at %x: no 32-bit stack in the dispatcher (esp=%x ss=%x/%x "
                         "context_esp=%x reserved=%x); this 32-bit thread ends\\n", (int)rec->ExceptionCode,
                         (int)rec->ExceptionAddress, (int)esp, (int)ctx.SegSs, (int)ss32_sel, (int)ctx.Esp,
                         (int)NtCurrentTeb32()->SystemReserved1[0] );
                    NtTerminateThread( GetCurrentThread(), rec->ExceptionCode );
                }
            }
"""),
    # W178: W160's per-thread syscall counting (PWSYSCALL) is gone; Wow64SystemServiceEx is Wine's again.
    # W272 (W270: NFS U2 and Quake 3 move only while input arrives; the server wakes on time): a 32-bit syscall that
    # takes over 100 ms, with the timeout a wait asked for, its status and the 32-bit modules above it on the stack.
    ('''/**********************************************************************
 *           Wow64SystemServiceEx  (wow64.@)
 */''','''/* OrbisDesk W272 (W270: NFS U2 and Quake 3 move only while input arrives): a 32-bit syscall that takes over
 * 100 ms, with the timeout a wait asked for ("late": under 100 ms asked, over 100 ms past it), its status and the
 * 32-bit modules on the stack above it. At most 120 lines a thread and 4000 in all. */
static const char * const pw_syscall_names[] =
{
#define SYSCALL_ENTRY(id,name,args) #name,
    ALL_SYSCALLS32
#undef SYSCALL_ENTRY
};
static LONG pw_wait_lines, pw_wait_tids[128], pw_wait_counts[128];

struct pw_module32  /* the start of a 32-bit LDR_DATA_TABLE_ENTRY */
{
    LIST_ENTRY32     InLoadOrderLinks;
    LIST_ENTRY32     InMemoryOrderLinks;
    LIST_ENTRY32     InInitializationOrderLinks;
    ULONG            DllBase;
    ULONG            EntryPoint;
    ULONG            SizeOfImage;
    UNICODE_STRING32 FullDllName;
    UNICODE_STRING32 BaseDllName;
};

static BOOL pw_streq( const char *a, const char *b )
{
    while (*a && *a == *b) { a++; b++; }
    return *a == *b;
}

static char *pw_put( char *p, char *end, const char *s )
{
    while (*s && p < end - 1) *p++ = *s++;
    *p = 0;
    return p;
}

static char *pw_put_hex( char *p, char *end, ULONG value )
{
    char digits[12];
    int n = 0;

    do digits[n++] = "0123456789abcdef"[value & 15]; while (value >>= 4);
    p = pw_put( p, end, "+0x" );
    while (n && p < end - 1) *p++ = digits[--n];
    *p = 0;
    return p;
}

/* alpha-1: OrbisDesk's trace switch (platform/ps4/pw_trace.h) as the launcher hands it to Wine, PW_TRACE=0|1;
 * unset counts as on, as before the switch. Read once. */
static BOOL pw_traced( void )
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

static BOOL pw_wait_budget( LONG tid )
{
    unsigned int i;

    if (InterlockedIncrement( &pw_wait_lines ) > 4000) return FALSE;
    for (i = 0; i < ARRAY_SIZE(pw_wait_tids); i++)
    {
        LONG owner = InterlockedCompareExchange( &pw_wait_tids[i], tid, 0 );
        if (!owner || owner == tid) return InterlockedIncrement( &pw_wait_counts[i] ) <= 120;
    }
    return FALSE;
}

/* the timeout of a 32-bit wait, 100 ns units: -1 none (infinite), -2 an absolute time, -3 not a wait */
static LONGLONG pw_wait_asked( const char *name, const UINT *args )
{
    ULONG ptr;
    LONGLONG value;

    if (pw_streq( name, "NtWaitForSingleObject" )) ptr = args[2];
    else if (pw_streq( name, "NtWaitForMultipleObjects" ) || pw_streq( name, "NtRemoveIoCompletion" ) ||
             pw_streq( name, "NtRemoveIoCompletionEx" )) ptr = args[4];
    else if (pw_streq( name, "NtDelayExecution" ) || pw_streq( name, "NtWaitForAlertByThreadId" )) ptr = args[1];
    else if (pw_streq( name, "NtSignalAndWaitForSingleObject" ) || pw_streq( name, "NtWaitForKeyedEvent" ) ||
             pw_streq( name, "NtReleaseKeyedEvent" )) ptr = args[3];
    else return -3;
    if (!ptr) return -1;
    value = *(const LONGLONG *)ULongToPtr( ptr );
    if (value == 0x7fffffffffffffffll) return -1;
    if (value > 0) return -2;
    return -value;
}

/* the first 4 words of the 32-bit stack above the call that point into a 32-bit module other than ntdll,
 * kernelbase and kernel32, as " module+0xoffset" */
static void pw_wait_where( const UINT *args, char *out, char *end )
{
    TEB32 *teb32 = NtCurrentTeb32();
    PEB32 *peb32 = ULongToPtr( teb32->Peb );
    PEB_LDR_DATA32 *ldr = peb32 ? ULongToPtr( peb32->LdrData ) : NULL;
    const UINT *sp, *top = ULongToPtr( teb32->Tib.StackBase );
    unsigned int found = 0, scanned = 0;
    char *p = out;

    *p = 0;
    if (!ldr || (ULONG_PTR)args >= (ULONG_PTR)top) return;
    for (sp = args; sp < top && scanned < 2048 && found < 4; sp++, scanned++)
    {
        ULONG link = ldr->InLoadOrderModuleList.Flink, head = PtrToUlong( &ldr->InLoadOrderModuleList );
        unsigned int guard = 0;

        if (*sp < 0x10000) continue;
        while (link && link != head && guard++ < 512)
        {
            const struct pw_module32 *mod = ULongToPtr( link );

            if (*sp - mod->DllBase < mod->SizeOfImage)
            {
                const WCHAR *name = ULongToPtr( mod->BaseDllName.Buffer );
                unsigned int i, len = mod->BaseDllName.Length / sizeof(WCHAR);
                char ascii[48];

                for (i = 0; name && i < len && i < sizeof(ascii) - 1; i++)
                    ascii[i] = name[i] >= 'A' && name[i] <= 'Z' ? name[i] + 32 : name[i] < 0x80 ? name[i] : '?';
                ascii[i] = 0;
                if (!pw_streq( ascii, "ntdll.dll" ) && !pw_streq( ascii, "kernelbase.dll" ) &&
                    !pw_streq( ascii, "kernel32.dll" ))
                {
                    p = pw_put( p, end, " " );
                    p = pw_put( p, end, ascii );
                    p = pw_put_hex( p, end, *sp - mod->DllBase );
                    found++;
                }
                break;
            }
            link = mod->InLoadOrderLinks.Flink;
        }
    }
}

static void pw_wait_note( UINT num, const UINT *args, LONGLONG took, NTSTATUS status )
{
    UINT id = num & 0xfff, table = (num >> 12) & 3;
    ULONG tid = HandleToULong( NtCurrentTeb()->ClientId.UniqueThread );
    LONGLONG asked = -3;
    const char *name = NULL;
    char where[240];

    if (!table && id < ARRAY_SIZE(pw_syscall_names))
    {
        name = pw_syscall_names[id];
        asked = pw_wait_asked( name, args );
    }
    if (!pw_wait_budget( tid )) return;
    pw_wait_where( args, where, where + sizeof(where) );
    if (name)
        ERR( "PWWAIT thread=%04lx %s took_ms=%u asked_ms=%d%s status=%#lx args=%x,%x where:%s\\n", tid, name,
             (UINT)(took / 10000), asked >= 0 ? (int)(asked / 10000) : (int)asked,
             asked >= 0 && asked < 1000000 && took > asked + 1000000 ? " late" : "", status, args[0], args[1], where );
    else
        ERR( "PWWAIT thread=%04lx win32u#%03x took_ms=%u asked_ms=-3 status=%#lx args=%x,%x where:%s\\n", tid, id,
             (UINT)(took / 10000), status, args[0], args[1], where );
}


/**********************************************************************
 *           Wow64SystemServiceEx  (wow64.@)
 */'''),
    ('''    status = wow64_syscall( args, table->ServiceTable[id] );
    free_temp_data();
    return status;''','''    /* alpha-1: two clock reads around every 32-bit system call, for W272's wait lines: traces only */
    if (!pw_traced()) status = wow64_syscall( args, table->ServiceTable[id] );
    else
    {
        LARGE_INTEGER pw_start, pw_end;  /* OrbisDesk W272 */

        NtQueryPerformanceCounter( &pw_start, NULL );
        status = wow64_syscall( args, table->ServiceTable[id] );
        NtQueryPerformanceCounter( &pw_end, NULL );
        if (pw_end.QuadPart - pw_start.QuadPart > 1000000)
            pw_wait_note( num, args, pw_end.QuadPart - pw_start.QuadPart, status );
    }
    free_temp_data();
    return status;'''),
    ]))
# B1 (pe32-en-explorer-plan.md section 4): 32-bit code in a 64-bit process (explorer) never ends the
# process through NtTerminateProcess: "the others" is refused, "myself" ends the thread; the 32-bit host
# ends a guest before either (fixtures/win32/orbis32host.c).
process_c=work/'src/process.c'
adaptations.append(adapt(WINE/'dlls/wow64/process.c',process_c,[
    ('WINE_DEFAULT_DEBUG_CHANNEL(wow);\n','WINE_DEFAULT_DEBUG_CHANNEL(wow);\n\nextern BOOL pw_wow64_world;  /* OrbisDesk B1, syscall.c */\n'),
    ('''    LONG exit_code = get_ulong( &args );

    NTSTATUS status;

    if (!handle && pBTCpuProcessTerm) pBTCpuProcessTerm( handle, FALSE, 0 );''','''    LONG exit_code = get_ulong( &args );

    NTSTATUS status;

    if (pw_wow64_world && (!handle || handle == GetCurrentProcess()))
    {
        /* OrbisDesk B1: 32-bit code in a 64-bit process (explorer) */
        if (!handle)
        {
            ERR( "PWWOW terminate_process others refused code=%lx\\n", exit_code );
            return STATUS_SUCCESS;
        }
        ERR( "PWWOW terminate_process self: thread %04lx ends, not the process, code=%lx\\n",
             HandleToULong( NtCurrentTeb()->ClientId.UniqueThread ), exit_code );
        if (pBTCpuThreadTerm) pBTCpuThreadTerm( GetCurrentThread(), exit_code );
        return NtTerminateThread( GetCurrentThread(), exit_code );
    }
    if (!handle && pBTCpuProcessTerm) pBTCpuProcessTerm( handle, FALSE, 0 );''')]))
# W254 (W253: MangoHud i386 showed CPU and GPU as N/A): the private telemetry query (PW_PS4_TELEMETRY_CLASS,
# tools/build-telemetry-ps4.py) passes through for 32-bit programs; wow64 refused it as an unsupported class.
# struct pw_ps4_telemetry has fixed-width fields only, 80 bytes with the same layout in both architectures.
system_c=work/'src/system.c'
adaptations.append(adapt(WINE/'dlls/wow64/system.c',system_c,[
    ('''    NTSTATUS status;

    switch (class)
    {
    case SystemPerformanceInformation:  /* SYSTEM_PERFORMANCE_INFORMATION */''','''    NTSTATUS status;

    /* OrbisDesk W254: PW_PS4_TELEMETRY_CLASS, struct pw_ps4_telemetry (same layout in 32 and 64 bits), passed
     * through as SystemWineVersionInformation is; outside the switch, which has only the enum's classes */
    if (class == (SYSTEM_INFORMATION_CLASS)0x50573454) return NtQuerySystemInformation( class, ptr, len, retlen );

    switch (class)
    {
    case SystemPerformanceInformation:  /* SYSTEM_PERFORMANCE_INFORMATION */''')]))
recipe=subprocess.check_output(['make','-n','-W','../../source/dlls/wow64/syscall.c','-W','../../source/dlls/wow64/process.c',
                                '-W','../../source/dlls/wow64/system.c',
                                'dlls/wow64/x86_64-windows/wow64.dll'],
                               cwd=HOST,text=True).replace('\\\n',' ').splitlines()
compile_line=next(line for line in recipe if 'dlls/wow64/x86_64-windows/syscall.o' in line and ' -c ' in line)
compile_args=[str(work/'pe/syscall.o') if arg=='dlls/wow64/x86_64-windows/syscall.o' else
              str(syscall_c) if arg.endswith('dlls/wow64/syscall.c') else arg for arg in shlex.split(compile_line)]
run(compile_args,cwd=HOST)
process_line=next(line for line in recipe if 'dlls/wow64/x86_64-windows/process.o' in line and ' -c ' in line)
run([str(work/'pe/process.o') if arg=='dlls/wow64/x86_64-windows/process.o' else
     str(process_c) if arg.endswith('dlls/wow64/process.c') else arg for arg in shlex.split(process_line)],cwd=HOST)
system_line=next(line for line in recipe if 'dlls/wow64/x86_64-windows/system.o' in line and ' -c ' in line)
run([str(work/'pe/system.o') if arg=='dlls/wow64/x86_64-windows/system.o' else
     str(system_c) if arg.endswith('dlls/wow64/system.c') else arg for arg in shlex.split(system_line)],cwd=HOST)
link_line=next(line for line in recipe if 'winegcc' in line and 'wow64.dll' in line)
wow64=out/'x86_64-windows/wow64.dll'
link_args=[str(wow64) if arg=='dlls/wow64/x86_64-windows/wow64.dll' else
           str(work/'pe/syscall.o') if arg=='dlls/wow64/x86_64-windows/syscall.o' else
           str(work/'pe/process.o') if arg=='dlls/wow64/x86_64-windows/process.o' else
           str(work/'pe/system.o') if arg=='dlls/wow64/x86_64-windows/system.o' else arg for arg in shlex.split(link_line)]
run(link_args,cwd=HOST)

# B1 (pe32-en-explorer-plan.md P4): wow64win.dll leaves the 64-bit PEB's callback table to 64-bit user32 in a
# 64-bit process (explorer). Its 32-bit threads find wow64win's table in TlsSlots[18], which wow64.dll's
# thread_init sets and the PE ntdll's KiUserCallbackDispatcher reads on WoW64 threads only
# (tools/build-guest-hw.py). With a 32-bit main image it sets the PEB's table, as before.
win_syscall_c=work/'src/wow64win-syscall.c'
adaptations.append(adapt(WINE/'dlls/wow64win/syscall.c',win_syscall_c,[
    ('''    LdrDisableThreadCalloutsForDll( inst );
    NtCurrentTeb()->Peb->KernelCallbackTable = user_callbacks;''','''    LdrDisableThreadCalloutsForDll( inst );
    if (NtCurrentTeb()->WowTebOffset)
    {
        const IMAGE_NT_HEADERS *nt = RtlImageNtHeader( NtCurrentTeb()->Peb->ImageBaseAddress );

        /* OrbisDesk B1: a 32-bit guest of a 64-bit process; the PEB's table stays 64-bit user32's */
        if (nt && nt->FileHeader.Machine == IMAGE_FILE_MACHINE_AMD64)
        {
            NtCurrentTeb()->TlsSlots[18] = (void *)user_callbacks;
            return TRUE;
        }
    }
    NtCurrentTeb()->Peb->KernelCallbackTable = user_callbacks;''')]))
win_recipe=subprocess.check_output(['make','-n','-W','../../source/dlls/wow64win/syscall.c','dlls/wow64win/x86_64-windows/wow64win.dll'],
                                   cwd=HOST,text=True).replace('\\\n',' ').splitlines()
win_compile=next(line for line in win_recipe if 'dlls/wow64win/x86_64-windows/syscall.o' in line and ' -c ' in line)
run([str(work/'pe/wow64win-syscall.o') if arg=='dlls/wow64win/x86_64-windows/syscall.o' else
     str(win_syscall_c) if arg.endswith('dlls/wow64win/syscall.c') else arg for arg in shlex.split(win_compile)],cwd=HOST)
win_link=next(line for line in win_recipe if 'winegcc' in line and 'wow64win.dll' in line)
wow64win=out/'x86_64-windows/wow64win.dll'
run([str(wow64win) if arg=='dlls/wow64win/x86_64-windows/wow64win.dll' else
     str(work/'pe/wow64win-syscall.o') if arg=='dlls/wow64win/x86_64-windows/syscall.o' else arg for arg in shlex.split(win_link)],cwd=HOST)

manifest={'schema_version':1,'wine_commit':commit,'prospero_win_revision':
          subprocess.check_output(['git','-C',str(UP),'rev-parse','HEAD'],text=True).strip(),
          'adaptations':adaptations,'derived_from':['upstream/prospero-win/wine/wow64native (LGPL-2.1-or-later)',
          'upstream/prospero-win/wine/patches/0611-wow64-ps5-take-the-cpu-from-the-environment.patch',
          'upstream/prospero-win/wine/patches/0614-wow64-ps5-translator-when-the-native-cpu-does-not-start.patch'],
          'unix_objects':{str(unix_object.relative_to(ROOT)):sha(unix_object)},
          'modules':{path.name:{'path':'x86_64-windows/'+path.name,'sha256':sha(path)} for path in (dll,wow64,wow64win)},
          'builder_sha256':sha(pathlib.Path(__file__)),
          'selection_environment':'WINE_PS4_WOW64_CPU=wow64native.dll','Wine_booted':False}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'modules':manifest['modules']}))
