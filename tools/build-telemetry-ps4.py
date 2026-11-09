#!/usr/bin/env python3
"""Add one private telemetry query to the proven system.c, without running the CPU draft preparer."""
import hashlib,json,pathlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
base=json.loads((ROOT/'build/wine-boot/report.json').read_text())
entry=next(e for e in base['results'] if e['unit']=='system')
original=ROOT/'.deps/wine/ps4-overlay/dlls/ntdll/unix/system.c'
if sha(original)!=entry['source_sha256']:raise SystemExit('system.c differs from the proven build input')
work=ROOT/'build/telemetry-ps4';work.mkdir(parents=True,exist_ok=True)
text=original.read_text()
signature='NTSTATUS WINAPI NtQuerySystemInformation( SYSTEM_INFORMATION_CLASS class,'
if text.count(signature)!=1:raise SystemExit('Wine system query signature changed')
text=text.replace(signature,'#include "pw_telemetry.h"\n#include "pw_dos_audio.h"\nextern uint32_t pw_ps4_telemetry_query(void *,uint32_t,uint32_t *);\nextern uint32_t pw_dos_audio_query(void *,uint32_t,uint32_t *);\n\n'+signature,1)
start=text.index(signature);switch=text.index('    switch (class)\n    {',start)
text=text[:switch]+text[switch:].replace('    switch (class)\n    {',
    '    switch (class)\n    {\n    case PW_PS4_TELEMETRY_CLASS:\n        return pw_ps4_telemetry_query(info,size,ret_size);\n    case PW_DOS_AUDIO_CLASS:\n        return pw_dos_audio_query(info,size,ret_size);',1)
# W112: Task Manager stops each refresh when class 8 fails, so CPU, memory and processes
# stayed at 0. Report the title process's CPU time (same sources as the HUD) per processor:
# idle = wall - busy/capacity, so Task Manager's percentage is busy/(capacity*wall).
def substitute(old,new):
    global text
    if text.count(old)!=1:raise SystemExit('Wine system.c context changed: '+old[:60])
    text=text.replace(old,new,1)
substitute('extern int pw_wine_memory_info( unsigned long long *total, unsigned long long *available );',
r'''extern int pw_wine_memory_info( unsigned long long *total, unsigned long long *available );
extern int pw_ps4_cpu_times( unsigned long long *wall, unsigned long long *busy,
                             unsigned long long *sys, unsigned int *capacity );
/* 100 ns idle time of one processor for the title process; 0 or a negative errno */
static int pw_processor_idle( unsigned long long *idle, unsigned long long *busy, unsigned long long *sys )
{
    unsigned long long wall, used;
    unsigned int capacity;
    int rc = pw_ps4_cpu_times( &wall, busy, sys, &capacity );
    if (rc) return rc;
    *busy /= capacity;
    *sys /= capacity;
    used = *busy;
    *idle = wall > used ? wall - used : 0;
    return 0;
}''')
substitute(r'''    if (pw_wine_memory_info( &totalram, &freeram )) return STATUS_NOT_SUPPORTED;
    memset( info, 0, sizeof(*info) );
''',r'''    unsigned long long idle, busy, sys;
    int rc;

    if (pw_wine_memory_info( &totalram, &freeram )) return STATUS_NOT_SUPPORTED;
    memset( info, 0, sizeof(*info) );
    if ((rc = pw_processor_idle( &idle, &busy, &sys )))
        ERR( "PWTASK idle time unavailable rc=%d\n", rc );
    else info->IdleTime.QuadPart = idle * peb->NumberOfProcessors;
''')
# W303: tools/prepare-wine-boot.py's W096 per-CPU block (getrusage) may already fill class 8. This builder's
# version below (W112, the title's CPU time through pw_ps4_cpu_times, as Task Manager and the HUD read it)
# supersedes it: the W096 block is reduced to the unsupported stub it replaced, which the next step expects.
class8='    case SystemProcessorPerformanceInformation:  /* 8 */\n    {\n#ifdef __ORBIS__\n'
w096_end='        break;\n#else\n        SYSTEM_PROCESSOR_PERFORMANCE_INFORMATION *sppi = NULL;'
if text.count(class8)==1 and 'struct rusage usage;' in text[text.index(class8):text.index(w096_end,text.index(class8))]:
    start=text.index(class8)+len(class8);end=text.index(w096_end,start)
    text=text[:start]+'        ret = STATUS_NOT_SUPPORTED;\n'+text[end:]
substitute(r'''#ifdef __ORBIS__
        ret = STATUS_NOT_SUPPORTED;
        break;
#else
        SYSTEM_PROCESSOR_PERFORMANCE_INFORMATION *sppi = NULL;''',r'''#ifdef __ORBIS__
        SYSTEM_PROCESSOR_PERFORMANCE_INFORMATION *sppi = info;
        unsigned long long idle, busy, sys;
        unsigned int n = min( peb->NumberOfProcessors, size / sizeof(*sppi) ), i;
        int rc;

        if (!n)
        {
            len = 0;
            ret = STATUS_INFO_LENGTH_MISMATCH;
            break;
        }
        if (!info)
        {
            ret = STATUS_ACCESS_VIOLATION;
            break;
        }
        if ((rc = pw_processor_idle( &idle, &busy, &sys )))
        {
            ERR( "PWTASK processor times unavailable rc=%d\n", rc );
            ret = STATUS_NOT_SUPPORTED;
            break;
        }
        memset( sppi, 0, n * sizeof(*sppi) );
        for (i = 0; i < n; i++)
        {
            sppi[i].IdleTime.QuadPart   = idle;
            sppi[i].KernelTime.QuadPart = idle + sys;
            sppi[i].UserTime.QuadPart   = busy - sys;
        }
        len = n * sizeof(*sppi);
        break;
#else
        SYSTEM_PROCESSOR_PERFORMANCE_INFORMATION *sppi = NULL;''')
# W191: random bytes (RtlGenRandom, BCryptGenRandom, so TLS keys and nonces) come from get_random.
# The SDK's getrandom() fails with ENOSYS, and whether the sandbox opens /dev/urandom was never
# checked; when both fail Wine only warns (not logged) and leaves the buffer as it was. The
# console's kernel is FreeBSD: sysctl kern.arandom (CTL_KERN 1, KERN_ARND 37, at most 256 bytes a
# call) is tried first, then /dev/urandom. The first call logs its source; a failure of both is
# logged every time, and the query (SystemInterruptInformation) then fails.
substitute('''static void get_random( void *buf, ULONG len )
{
#ifdef HAVE_GETRANDOM''',r'''#ifdef __ORBIS__
/* 0, or -1 with a PWRANDOM line when no source filled the buffer */
static int pw_get_random( void *buf, ULONG len )
{
    extern int sysctl( const int *name, unsigned int namelen, void *old, size_t *oldlen, const void *newp, size_t newlen );
    static int logged;
    static const int mib[2] = { 1 /* CTL_KERN */, 37 /* KERN_ARND */ };
    char *p = buf;
    ULONG done = 0;
    int fd, arandom_errno = 0, urandom_errno = 0;
    while (done < len)
    {
        size_t chunk = min( len - done, 256 );
        if (sysctl( mib, 2, p + done, &chunk, NULL, 0 )) { arandom_errno = errno; break; }
        if (!chunk) break;
        done += chunk;
    }
    if (done == len)
    {
        if (!logged) { logged = 1; fprintf( stderr, "PWRANDOM source=kern.arandom len=%u\n", (unsigned)len ); }
        return 0;
    }
    if ((fd = open( "/dev/urandom", O_RDONLY )) == -1) urandom_errno = errno;
    else
    {
        ssize_t got;
        done = 0;
        while (done < len)
        {
            if ((got = read( fd, p + done, len - done )) > 0) done += got;
            else if (got == -1 && errno == EINTR) continue;
            else { urandom_errno = got ? errno : 0; break; }
        }
        close( fd );
        if (done == len)
        {
            if (!logged) { logged = 1; fprintf( stderr, "PWRANDOM source=urandom len=%u arandom_errno=%d\n", (unsigned)len, arandom_errno ); }
            return 0;
        }
    }
    fprintf( stderr, "PWRANDOM unavailable len=%u arandom_errno=%d urandom_errno=%d\n", (unsigned)len, arandom_errno, urandom_errno );
    return -1;
}
#endif

static void get_random( void *buf, ULONG len )
{
#ifdef __ORBIS__
    pw_get_random( buf, len );  /* the process cookie; a failure is logged */
    return;
#endif
#ifdef HAVE_GETRANDOM''')
# The random query fails instead of returning the buffer unchanged.
substitute('''            else get_random( info, len );''','''#ifdef __ORBIS__
            else if (pw_get_random( info, len )) ret = STATUS_UNSUCCESSFUL;
#else
            else get_random( info, len );
#endif''')
# W278 (W276: Wine counted one processor, so every affinity mask was 0x1, all of them, and one core could not be
# asked for): the console has no _SC_NPROCESSORS_ONLN answer; the count is the cores this title may use.
substitute('''    peb->NumberOfProcessors = num;
    init_cpu_model();''','''#ifdef __ORBIS__
    if (num <= 1)
    {
        extern void *scePthreadSelf( void );
        extern void scePthreadGetaffinity( void *thread, unsigned long long *mask );  /* the SDK declares it void */
        unsigned long long cores = 0;

        scePthreadGetaffinity( scePthreadSelf(), &cores );
        cores &= 0xff;
        /* bit i of a Windows mask is core i (pw_wine_thread_setaffinity): only a run of cores from 0 counts */
        if (cores && !(cores & (cores + 1))) num = __builtin_popcountll( cores );
        fprintf( stderr, "PWBOOT processors=%ld title_cores=%llx\\n", num, cores );
    }
#endif
    peb->NumberOfProcessors = num;
    init_cpu_model();''')
selected=work/'system.c';selected.write_text(text)
obj=work/'system.o';command=[str(selected) if arg==str(original) else str(obj) if arg==str(ROOT/'build/wine-boot/system.o') else arg for arg in entry['command']]
with (work/'compile.log').open('w') as log:subprocess.run(command,cwd=ROOT/'.deps/wine/ps4-unix',stdout=log,stderr=subprocess.STDOUT,check=True)
home=pathlib.Path.home()/'vk-h0'
gpu_source=home/'src/mesa-crema/src/amd/common/ac_ps4_drm.c'
subprocess.run(['python3',str(ROOT/'tools/vk-h0/patch-crema-telemetry.py'),str(gpu_source)],check=True)
# W286: RADV's own files (radv-ps4.log, GPU hang and fault reports, flight recorder) go to the renamed state
# folder; the old one was removed from the console and mkdir does not create its parent.
gpu_text=gpu_source.read_text()
if gpu_text.count('/data/orbis-win/gpu'):gpu_source.write_text(gpu_text.replace('/data/orbis-win/gpu','/data/orbisdesk/gpu'))
if '/data/orbis-win' in gpu_source.read_text() or gpu_source.read_text().count('/data/orbisdesk/gpu')<12:
    raise SystemExit('ac_ps4_drm.c: GPU log paths not as expected')
with (work/'gpu-build.log').open('w') as log:
    subprocess.run(['ninja','-C',str(home/'build/mesa-wine'),'src/amd/common/libamd_common.a'],stdout=log,stderr=subprocess.STDOUT,check=True)
gpu_lib=home/'build/mesa-wine/src/amd/common/libamd_common.a'
report={'wine_commit':base['wine_commit'],'original_source_sha256':sha(original),
        'source_sha256':sha(selected),'object':str(obj.relative_to(ROOT)),'object_sha256':sha(obj),'command':command}
report.update(gpu_source=str(gpu_source),gpu_source_sha256=sha(gpu_source),gpu_library=str(gpu_lib),gpu_library_sha256=sha(gpu_lib))
(work/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
