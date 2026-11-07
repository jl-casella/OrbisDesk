#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""W136: ntdll's signal_x86_64.c with the raw signal entry native 32-bit code needs.

Phase 5A (wow64native, prospero-win): a 32-bit thread runs with the guest TEB as FS base,
and libkernel's signal wrapper reads its thread through %fs, so a signal there would crash
before Wine sees it. Adapted from prospero-win patch 0883: each Wine thread keeps its host
FS base in its TEB (amd64_thread_data at 0x348; pthread_teb stays NULL, because our
dispatcher would then issue its own sysarch system call), and a process started with
PW_NATIVE_SIGNALS=1 registers its handlers with the kernel directly
(pw_wine_native_signals_enable, platform/ps4/pw_wine_signals.c), after proving the
syscall instruction and the signal frame layout. __wine_prospero_native_wow64_caps reports
what is installed: 1 raw entries, 2 host FS before C. 4 (FP/xstate context) is not
reported: Wine's Orbis context keeps no xstate (XState_sig is NULL), so exceptions lose
the upper YMM halves. The proven source is checked by hash and compiled with its own
recipe, as tools/build-env-ps4.py does for env.c.
"""
import hashlib,json,pathlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
UNIX=ROOT/'.deps/wine/ps4-unix';work=ROOT/'build/signal-ps4';work.mkdir(parents=True,exist_ok=True)
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
base=json.loads((ROOT/'build/wine-boot/report.json').read_text())
entry=next(e for e in base['results'] if e['unit']=='signal_x86_64')
original=ROOT/'.deps/wine/ps4-overlay/dlls/ntdll/unix/signal_x86_64.c'
if sha(original)!=entry['source_sha256']:raise SystemExit('signal_x86_64.c differs from the proven build input')
text=original.read_text()
def replace(old,new):
    global text
    if text.count(old)!=1:raise SystemExit('signal_x86_64.c context changed: '+old[:60])
    text=text.replace(old,new,1)
replace('''    char                  syscall_dispatch; /* 0340 */
};
''','''    char                  syscall_dispatch; /* 0340 */
    void                 *pw_host_fs;    /* 0348 OrbisDesk: host FS base, for the raw signal entry */
};
''')
replace('''C_ASSERT( offsetof( TEB, GdiTebBatch ) + offsetof( struct amd64_thread_data, syscall_dispatch ) == 0x340 );
''','''C_ASSERT( offsetof( TEB, GdiTebBatch ) + offsetof( struct amd64_thread_data, syscall_dispatch ) == 0x340 );
C_ASSERT( offsetof( TEB, GdiTebBatch ) + offsetof( struct amd64_thread_data, pw_host_fs ) == 0x348 );

#ifdef __ORBIS__
/* OrbisDesk W136 (prospero-win patch 0883, adapted): what the signal path installed for
 * native 32-bit code. Version 1; bit 1 raw entries, bit 2 host FS before C. */
extern int pw_wine_native_signals_enable( char *detail, size_t size );
extern int pw_wine_native_signals_active(void);
static unsigned int pw_native_caps;
unsigned int __wine_prospero_native_wow64_caps( unsigned int version );
unsigned int __wine_prospero_native_wow64_caps( unsigned int version )
{
    return version == 1 ? __atomic_load_n( &pw_native_caps, __ATOMIC_ACQUIRE ) : 0;
}
#endif
''')
replace('''    sig_act.sa_mask = server_block_set;
    sig_act.sa_flags = SA_SIGINFO | SA_RESTART | SA_ONSTACK;
''','''#ifdef __ORBIS__
    {
        /* W136: a process that may run 32-bit code natively (PW_NATIVE_SIGNALS=1, set by
         * the launcher for a 32-bit program) registers its handlers with the kernel itself */
        const char *native = getenv( "PW_NATIVE_SIGNALS" );
        if (native && native[0] == '1' && !native[1])
        {
            char detail[192];
            int rc = pw_wine_native_signals_enable( detail, sizeof(detail) );
            fprintf( stderr, "PWNATIVE signals raw=%d %s\\n", !rc, detail );
        }
    }
#endif
    sig_act.sa_mask = server_block_set;
    sig_act.sa_flags = SA_SIGINFO | SA_RESTART | SA_ONSTACK;
''')
replace('''        else if (!dl_iterate_phdr( libc_addr_cb, act.sa_restorer ))
        {
            WARN_(seh)( "could not find library containing signal restorer trampoline\\n" );
            syscall_dispatch_enabled = FALSE;
        }
    }
#endif

    return;
''','''        else if (!dl_iterate_phdr( libc_addr_cb, act.sa_restorer ))
        {
            WARN_(seh)( "could not find library containing signal restorer trampoline\\n" );
            syscall_dispatch_enabled = FALSE;
        }
    }
#endif

#ifdef __ORBIS__
    /* every registration above went through the raw entry */
    if (pw_wine_native_signals_active())
    {
        __atomic_store_n( &pw_native_caps, 1 | 2, __ATOMIC_RELEASE );
        fprintf( stderr, "PWNATIVE caps=%u cs64=%x ss64=%x\\n", pw_native_caps, cs64_sel, ds64_sel );
    }
#endif
    return;
''')
replace('''    thread_data->pthread_teb = NULL; /* Keep the PS4 libc FS base unchanged. */
''','''    thread_data->pthread_teb = NULL; /* Keep the PS4 libc FS base unchanged. */
    /* W136: the raw signal entry (pw_wine_signals.c) puts this thread's FS base back
     * when a signal interrupts code running on another one (a 32-bit guest) */
    if (sysarch( 128, &thread_data->pw_host_fs )) thread_data->pw_host_fs = NULL;
''')
# W137: the initial 32-bit context gets the compatibility-mode code selector, FreeBSD's
# GUCODE32_SEL (0x33, measured in W135), as Wine's FreeBSD branch sets it; wow64native
# enters 32-bit code with it. It was 0 on Orbis, which only the translator tolerated.
replace('''#elif defined(__FreeBSD__) && !defined(__ORBIS__)
        cs32_sel = GSEL(GUCODE32_SEL, SEL_UPL);
#endif''','''#elif defined(__FreeBSD__) && !defined(__ORBIS__)
        cs32_sel = GSEL(GUCODE32_SEL, SEL_UPL);
#elif defined(__ORBIS__)
        cs32_sel = 0x33;
#endif''')
selected=work/'signal_x86_64.c';selected.write_text(text)
obj=work/'signal_x86_64.o'
command=[str(selected) if arg==str(original) else str(obj) if arg==str(ROOT/'build/wine-boot/signal_x86_64.o') else arg
         for arg in entry['command']]
if str(obj) not in command or str(selected) not in command:raise SystemExit('signal_x86_64.o recipe changed')
with (work/'signal_x86_64.log').open('w') as log:
    run=subprocess.run(command,cwd=UNIX,stdout=log,stderr=subprocess.STDOUT)
if run.returncode:raise SystemExit('cannot compile signal_x86_64.c; see '+str(work/'signal_x86_64.log'))
report={'wine_commit':base['wine_commit'],'original_source_sha256':sha(original),'source_sha256':sha(selected),
        'object':str(obj.relative_to(ROOT)),'object_sha256':sha(obj),'builder_sha256':sha(pathlib.Path(__file__)),
        'derived_from':'upstream/prospero-win/wine/patches/0883-ntdll-ps5-native-wow64-signal-entry.patch'}
(work/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
