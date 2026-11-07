#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""W120, phase 3 of the PE32 plan: Wine's audio for the console.

1. prospero-win's mmdevapi driver (upstream/prospero-win/wine/wineps5/unix.c with
   src/pw_audio_mix.c, LGPL-2.1-or-later) as "wineps4": the same stream and mixing code,
   with its sink linked (native/wine_audio.c, platform/ps4/pw_wine_audio.h) instead of found
   with dlsym. Compiled with the OrbisDesk recipe of a Unix library (ws2_32's), its call
   tables renamed pw_wineps4_unix_call_funcs / _wow64_funcs for platform/ps4/pw_wine_unixlibs.c.
2. ntdll's virtual.c with one addition: MemoryWineLoadUnixLibByName (how mmdevapi loads
   "wineps4.drv") looks in the static Unix library table first; unloading such a library
   is a no-op. The proven source is checked by hash and compiled with its own recipe, as
   tools/build-telemetry-ps4.py does for system.c.
"""
import hashlib,json,pathlib,shlex,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'.deps/wine/source';UNIX=ROOT/'.deps/wine/ps4-unix';UP=ROOT/'upstream/prospero-win'
work=ROOT/'build/audio-ps4';work.mkdir(parents=True,exist_ok=True)
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('Wine source is not the pinned revision')
report={'schema_version':1,'wine_commit':commit,'sources':{},'objects':{}}
def substitute(text,old,new,where):
    if text.count(old)!=1:raise SystemExit('Unexpected context in '+where+': '+old[:60])
    return text.replace(old,new,1)

# 1. the driver
driver_src=UP/'wine/wineps5/unix.c';mix_src=UP/'src/pw_audio_mix.c'
report['sources']['wineps5/unix.c']=sha(driver_src);report['sources']['pw_audio_mix.c']=sha(mix_src)
text=driver_src.read_text()
text=substitute(text,'#include <dlfcn.h>\n','','driver')
text=substitute(text,'#include "pw_wine_sink.h"','#include "pw_wine_audio.h"','driver')
text=substitute(text,'''    audio_available = dlsym(RTLD_DEFAULT, "pw_wine_audio_available");
    audio_output = dlsym(RTLD_DEFAULT, "pw_wine_audio_output");''','''    /* OrbisDesk: one static ELF; the sink is linked (native/wine_audio.c). */
    audio_available = pw_wine_audio_available;
    audio_output = pw_wine_audio_output;''','driver')
text=substitute(text,'static const char device_name[] = "ps5";','static const char device_name[] = "ps4";','driver')
text=substitute(text,"static const WCHAR endpoint_name[] = {'P','S','5',0};","static const WCHAR endpoint_name[] = {'P','S','4',0};",'driver')
# W274 (W273: after NFS Underground 2 crashed, its second run had no sound; the mixer kept writing silent
# grains): each stream's create, start, stop and release, and every ~5 s the streams the mixer holds
# (playing, held frames, written frames), to see a dead program's stream and the new one. Read only.
text=substitute(text,'''    pthread_mutex_lock(&lock);
    stream->next = streams;
    streams = stream;
    pthread_mutex_unlock(&lock);
''','''    pthread_mutex_lock(&lock);
    stream->next = streams;
    streams = stream;
    pthread_mutex_unlock(&lock);
    fprintf(stderr, "PWAUDIO stream create %p rate=%u channels=%u period=%u buffer=%u flags=%#x\\n", stream,
            (unsigned)params->fmt->nSamplesPerSec, (unsigned)params->fmt->nChannels, (unsigned)stream->period_frames,
            (unsigned)stream->bufsize_frames, (unsigned)stream->flags);
''','driver')
text=substitute(text,'''    /* the mixer only touches streams under the lock */
    pthread_mutex_lock(&lock);
''','''    /* the mixer only touches streams under the lock */
    fprintf(stderr, "PWAUDIO stream release %p\\n", stream);
    pthread_mutex_lock(&lock);
''','driver')
text=substitute(text,'''    stream->playing = TRUE;
    stream->since_event = 0;
    pthread_cond_signal(&started);
''','''    stream->playing = TRUE;
    stream->since_event = 0;
    pthread_cond_signal(&started);
    fprintf(stderr, "PWAUDIO stream start %p held=%u\\n", stream, (unsigned)stream->mix.held);
''','driver')
text=substitute(text,'''    stream->playing = FALSE;

    return unlock_result(&params->result, S_OK);
''','''    stream->playing = FALSE;
    fprintf(stderr, "PWAUDIO stream stop %p\\n", stream);

    return unlock_result(&params->result, S_OK);
''','driver')
text=substitute(text,'''        pw_audio_mix_store(accumulator, grain, PW_WINE_AUDIO_GRAIN);
        pthread_mutex_unlock(&lock);
''','''        pw_audio_mix_store(accumulator, grain, PW_WINE_AUDIO_GRAIN);
        {
            static unsigned int grains;
            if (!(++grains % 1000))
                for (stream = streams; stream; stream = stream->next)
                    fprintf(stderr, "PWAUDIO mixer grain=%u stream=%p playing=%d held=%u written=%llu\\n", grains,
                            stream, (int)stream->playing, (unsigned)stream->mix.held,
                            (unsigned long long)stream->written_frames);
        }
        pthread_mutex_unlock(&lock);
''','driver')
# W285 (W284: NFS Underground 2 closed from the overlay left its stream in the mixer, playing with nothing held,
# until OrbisDesk ended; a guest's threads are ended without its IAudioClient being released). Each stream
# records the guest of the thread that created it (TEB.UserReserved[0], of the 32-bit TEB for WoW64 calls;
# tools/build-guest-hw.py). One more call, after mmdevapi's, takes a guest's streams out of the mixer when the
# guest unloads. They are kept as orphans, not freed: mmdevapi's session list, shared by every guest of the
# process, still holds the dead guest's clients and their stream handles. A later release frees an orphan.
text=substitute(text,'''    PwAudioMixStream mix;
    struct ps5_stream *next;
};''','''    PwAudioMixStream mix;
    struct ps5_stream *next;
    UINT64 owner;   /* OrbisDesk W285: the guest that created it, 0 for none */
    BOOL owner_wow; /* the owner is a 32-bit guest */
};''','driver')
text=substitute(text,'static struct ps5_stream *streams;\n','''static struct ps5_stream *streams;
static struct ps5_stream *orphans; /* OrbisDesk W285: streams of guests that ended, out of the mixer */
''','driver')
text=substitute(text,'''    fprintf(stderr, "PWAUDIO stream create %p rate=%u channels=%u period=%u buffer=%u flags=%#x\\n", stream,''','''    stream->owner = *(ULONG_PTR *)NtCurrentTeb()->UserReserved;
    fprintf(stderr, "PWAUDIO stream create %p rate=%u channels=%u period=%u buffer=%u flags=%#x\\n", stream,''','driver')
text=substitute(text,'''    ps5_create_stream(&params);
    params32->result = params.result;
    return STATUS_SUCCESS;
}''','''    ps5_create_stream(&params);
    params32->result = params.result;
    if (SUCCEEDED(params.result))
    {
        /* OrbisDesk W285: the owner of a WoW64 stream is the 32-bit guest of the thread */
        TEB *teb = NtCurrentTeb();
        struct ps5_stream *stream = *(struct ps5_stream **)params.stream;

        pthread_mutex_lock(&lock);
        stream->owner = teb->WowTebOffset ? ((TEB32 *)((char *)teb + teb->WowTebOffset))->UserReserved[0] : 0;
        stream->owner_wow = TRUE;
        pthread_mutex_unlock(&lock);
        fprintf(stderr, "PWAUDIO stream %p owner=%#llx wow=1\\n", stream, (unsigned long long)stream->owner);
    }
    return STATUS_SUCCESS;
}''','driver')
text=substitute(text,'''    pthread_mutex_lock(&lock);
    for (link = &streams; *link; link = &(*link)->next)
        if (*link == stream)
        {
            *link = stream->next;
            break;
        }
    pthread_mutex_unlock(&lock);

    free_stream(stream);
    params->result = S_OK;
    return STATUS_SUCCESS;
}''','''    BOOL found = FALSE;

    pthread_mutex_lock(&lock);
    for (link = &streams; *link; link = &(*link)->next)
        if (*link == stream)
        {
            *link = stream->next;
            found = TRUE;
            break;
        }
    /* OrbisDesk W285: or an orphan; a handle in neither list is not a stream and is not freed */
    if (!found)
        for (link = &orphans; *link; link = &(*link)->next)
            if (*link == stream)
            {
                *link = stream->next;
                found = TRUE;
                fprintf(stderr, "PWAUDIO orphan %p released\\n", stream);
                break;
            }
    if (!found)
    {
        pthread_mutex_unlock(&lock);
        fprintf(stderr, "PWAUDIO stream release %p: not a stream of this driver\\n", stream);
        params->result = E_HANDLE;
        return STATUS_SUCCESS;
    }
    pthread_mutex_unlock(&lock);

    free_stream(stream);
    params->result = S_OK;
    return STATUS_SUCCESS;
}

/* OrbisDesk W285: called by kernelbase when a guest unloads (tools/build-guest-hw.py), with the guest
 * of its threads; its streams leave the mixer and wait as orphans for a release that may never come. */
struct pw_release_guest_streams_params
{
    UINT64 owner;
    UINT32 orphaned, kept;
};

static NTSTATUS pw_release_guest_streams_wow(struct pw_release_guest_streams_params *params, BOOL wow)
{
    struct ps5_stream *stream, **link;

    params->orphaned = params->kept = 0;
    if (!params->owner) return STATUS_INVALID_PARAMETER;
    pthread_mutex_lock(&lock);
    for (link = &streams; (stream = *link);)
    {
        if (stream->owner != params->owner || stream->owner_wow != wow)
        {
            params->kept++;
            link = &stream->next;
            continue;
        }
        *link = stream->next;
        stream->playing = FALSE;
        stream->next = orphans;
        orphans = stream;
        params->orphaned++;
        fprintf(stderr, "PWAUDIO stream %p orphaned: guest %#llx wow=%d ended (written=%llu)\\n", stream,
                (unsigned long long)params->owner, wow, (unsigned long long)stream->written_frames);
    }
    pthread_mutex_unlock(&lock);
    return STATUS_SUCCESS;
}

static NTSTATUS pw_release_guest_streams(void *args)
{
    return pw_release_guest_streams_wow(args, FALSE);
}

static NTSTATUS pw_wow64_release_guest_streams(void *args)
{
    return pw_release_guest_streams_wow(args, TRUE);
}''','driver')
text=substitute(text,'''    ps5_aux_message,
};

C_ASSERT(ARRAYSIZE(__wine_unix_call_funcs) == funcs_count);''','''    ps5_aux_message,
    pw_release_guest_streams, /* OrbisDesk W285: index funcs_count, 37 */
};

C_ASSERT(funcs_count == 37);
C_ASSERT(ARRAYSIZE(__wine_unix_call_funcs) == funcs_count + 1);''','driver')
text=substitute(text,'''    ps5_wow64_aux_message,
};

C_ASSERT(ARRAYSIZE(__wine_unix_call_wow64_funcs) == funcs_count);''','''    ps5_wow64_aux_message,
    pw_wow64_release_guest_streams, /* OrbisDesk W285 */
};

C_ASSERT(ARRAYSIZE(__wine_unix_call_wow64_funcs) == funcs_count + 1);''','driver')
driver=work/'wineps4.c';driver.write_text(text)
makefile=(UNIX/'Makefile').read_text().splitlines()
def recipe(target):
    index=next((i for i,line in enumerate(makefile) if line.startswith(target+': ') and i+1<len(makefile)
                and makefile[i+1].startswith('\t$(CC)')),None)
    if index is None:raise SystemExit('No recipe for '+target)
    parts=[];index+=1
    while True:
        line=makefile[index];parts.append(line.rstrip().removesuffix('\\'))
        if not line.rstrip().endswith('\\'):break
        index+=1
    return ' '.join(parts).replace('$(CC)',str(UNIX/'orbis-cc')).replace('$(CFLAGS)','-g -O2')
template=recipe('dlls/ws2_32/unixlib.o')
ws2_source=str(SOURCE/'dlls/ws2_32/unixlib.c')
objects=[]
for name,source in (('wineps4',driver),('pw_audio_mix',mix_src)):
    output=work/(name+'.o')
    command=shlex.split(template.replace('$@',str(output)))
    command=[str(source) if arg==ws2_source else arg for arg in command
             if arg not in ('-Idlls/ws2_32','-I'+str(SOURCE/'dlls/ws2_32'),'-D_WS2_32_')]
    if str(source) not in command:raise SystemExit('ws2_32 recipe changed: no source argument')
    # mmdevapi's unixlib.h and the mixer header come first; generated IDL headers last
    command[1:1]=['-I'+str(SOURCE/'dlls/mmdevapi'),'-I'+str(UP/'src'),'-I'+str(ROOT/'platform/ps4')]
    command+=['-D__ORBIS__','-ffunction-sections','-fdata-sections','-include',str(ROOT/'platform/ps4/pw_wine_posix.h'),
              '-idirafter',str(ROOT/'.deps/wine/runtime/build/include')]
    with (work/(name+'.log')).open('w') as log:
        run=subprocess.run(command,cwd=UNIX,stdout=log,stderr=subprocess.STDOUT)
    if run.returncode:raise SystemExit('cannot compile '+name+'; see '+str(work/(name+'.log')))
    objects.append(output)
combined=work/'wineps4-combined.o';final=work/'wineps4-unix.o'
subprocess.run(['ld.lld','-r','-o',str(combined),*map(str,objects)],check=True)
subprocess.run(['objcopy','--localize-hidden',
                '--redefine-sym','__wine_unix_call_funcs=pw_wineps4_unix_call_funcs',
                '--redefine-sym','__wine_unix_call_wow64_funcs=pw_wineps4_unix_call_wow64_funcs',
                '--redefine-sym','pthread_once=pw_wine_pthread_once',str(combined),str(final)],check=True)
report['objects']['driver']={'object':str(final.relative_to(ROOT)),'sha256':sha(final)}

# 2. ntdll virtual.c: load-by-name through the static table
base=json.loads((ROOT/'build/wine-boot/report.json').read_text())
entry=next(e for e in base['results'] if e['unit']=='virtual')
original=ROOT/'.deps/wine/ps4-overlay/dlls/ntdll/unix/virtual.c'
if sha(original)!=entry['source_sha256']:raise SystemExit('virtual.c differs from the proven build input')
text=original.read_text()
text=substitute(text,'''                if ((status = load_unixlib_by_name( name, &handle ))) return status;''','''#ifdef __ORBIS__
                /* OrbisDesk W120: one static ELF; a library loaded by name (mmdevapi's audio
                 * driver) comes from the static table. Its module handle is a marker that
                 * MemoryWineUnloadUnixLib accepts without dlclose. */
                {
                    extern int pw_wine_static_unixlib_by_name( const void *name, int wow, const void **funcs,
                                                               NTSTATUS (**init)(void) );
                    if (pw_wine_static_unixlib_by_name( name, info_class == MemoryWineLoadUnixLibByNameWow64,
                                                        &funcs, &entry ))
                    {
                        fprintf( stderr, "PWBOOT static_unixlib_by_name %s wow=%d\\n", debugstr_us(name),
                                 info_class == MemoryWineLoadUnixLibByNameWow64 );
                        res[0] = PW_STATIC_UNIXLIB_MODULE;
                        res[1] = (UINT_PTR)funcs;
                        status = entry ? entry() : (funcs ? STATUS_SUCCESS : STATUS_ENTRYPOINT_NOT_FOUND);
                        if (!status) memcpy( buffer, res, min( len, sizeof(res) ));
                        return status;
                    }
                }
#endif
                if ((status = load_unixlib_by_name( name, &handle ))) return status;''','virtual.c')
text=substitute(text,'''                const unixlib_module_t *handle = addr;
''','''                const unixlib_module_t *handle = addr;
#ifdef __ORBIS__
                if (*handle == PW_STATIC_UNIXLIB_MODULE) return STATUS_SUCCESS;
#endif
''','virtual.c')
text=substitute(text,'/***********************************************************************\n *           get_unixlib_funcs',
                '#define PW_STATIC_UNIXLIB_MODULE 0x50574c4942ull /* "PWLIB": a static Unix library */\n\n'
                '/***********************************************************************\n *           get_unixlib_funcs','virtual.c')
# W172: W171's log answered it: on the faulting page sceKernelVirtualQuery fails with EACCES
# (0x8002000d) before and after, while mprotect returns 0. Wine's PROT_NONE anon_mmap_fixed
# (decommit, release inside a reserved area) leaves pages the kernel does not report, and
# pw_wine_memory_protect commits only the pages the query reports as uncommitted, so committing
# such a page again changed nothing. When set_protection commits pages Wine has as uncommitted,
# a page the query cannot see gets flexible memory mapped over it first. Those pages hold no
# data, so the map is fixed; if it fails, the page is unmapped and mapped again.
text=substitute(text,'''    if (!set_vprot( view, base, size, vprot | VPROT_COMMITTED )) return STATUS_ACCESS_DENIED;
    return STATUS_SUCCESS;
}''','''#ifdef __ORBIS__
    if (get_unix_prot( vprot | VPROT_COMMITTED )) pw_commit_backing( base, size, get_unix_prot( vprot | VPROT_COMMITTED ) );
#endif
    if (!set_vprot( view, base, size, vprot | VPROT_COMMITTED )) return STATUS_ACCESS_DENIED;
    return STATUS_SUCCESS;
}''','virtual.c')
text=substitute(text,'''/***********************************************************************
 *           set_protection
''','''#ifdef __ORBIS__
/* OrbisDesk W175: W174's log: the flexible memory budget, not a leak. During the race the free
 * flexible memory moved between ~80 and ~170 MB; at the end SuperMarioKart committed 25 more
 * 3 MiB heap blocks without freeing and the last one got committed with 1 MB left
 * (flexible_free=1048576), so its pages were never there. The title has ~400 MB of flexible
 * memory and ~4.6 GB of free direct memory. A commit of 1 MiB or more now maps direct memory
 * (CPU write-back) over its uncommitted runs. Each run is recorded with its direct memory offset
 * and released when Wine releases or decommits any part of it. If the allocation or the map
 * fails, the commit takes the flexible path as before and the failure is logged.
 * virtual_mutex is held by every caller. */
extern int sceKernelAllocateDirectMemory( long start, long end, size_t size, size_t align, int type, long *offset );
extern int sceKernelMapDirectMemory( void **addr, size_t size, int prot, int flags, long offset, size_t align );
extern int sceKernelReleaseDirectMemory( long offset, size_t size );
extern size_t sceKernelGetDirectMemorySize( void );
static struct pw_direct { char *base; size_t size; long offset; } pw_directs[8192];
static unsigned int pw_direct_count;

/* OrbisDesk W220, a diagnostic: C:\\orbis\\nodirect.txt turns direct memory off for the title, so
 * every commit takes the flexible path as before W175 (W217/W218: SeaMonkey and Pale Moon ran on
 * freed memory; mozjemalloc's 1 MiB chunks are direct memory). Read once. */
static int pw_direct_disabled(void)
{
    static int disabled = -1;

    if (disabled < 0)
    {
        char path[512];
        struct stat st;

        snprintf( path, sizeof(path), "%s/drive_c/orbis/nodirect.txt", config_dir );
        disabled = !stat( path, &st );
        if (disabled) ERR( "PWVM direct memory off (%s)\\n", path );
    }
    return disabled;
}

static int pw_direct_map( char *addr, size_t size, int unix_prot )
{
    static unsigned int logged;
    long offset = 0;
    void *at = addr;
    int rc;

    if (pw_direct_disabled()) return -1;  /* W220: the flexible path takes it, unlogged */

    if (pw_direct_count == ARRAY_SIZE(pw_directs)) rc = -1;
    else if (!(rc = sceKernelAllocateDirectMemory( 0, (long)sceKernelGetDirectMemorySize(), size, host_page_size,
                                                   0 /* WB_ONION */, &offset )))
    {
        /* W176: direct memory keeps what was there before, and Windows hands out committed
         * memory zeroed: W175's SuperMarioKart parsed a .x file out of a fresh block and failed
         * ("Array cannot be used to specify variable array size"). Mapped read/write, zeroed
         * here; set_protection then applies the protection asked for. */
        rc = sceKernelMapDirectMemory( &at, size, PROT_READ | PROT_WRITE, 0x10 /* MAP_FIXED */, offset, host_page_size );
        if (!rc && at != addr) rc = -2;
        if (rc) sceKernelReleaseDirectMemory( offset, size );
        else memset( addr, 0, size );
    }
    if (rc)
    {
        if (logged++ < 32)
            ERR( "PWVM direct map %p-%p failed rc=%#x at=%p entries=%u; flexible path\\n",
                 addr, addr + size, rc, at, pw_direct_count );
        return rc;
    }
    pw_directs[pw_direct_count].base = addr;
    pw_directs[pw_direct_count].size = size;
    pw_directs[pw_direct_count].offset = offset;
    pw_direct_count++;
    return 0;
}

/* Give back the direct memory under [start, start + size). Called before Wine unmaps or
 * re-reserves the range; a record that covers more than the range keeps the rest. */
static void pw_direct_release( void *start, size_t size )
{
    char *lo = start, *hi = lo + size;
    unsigned int i = 0;

    while (i < pw_direct_count)
    {
        struct pw_direct *d = &pw_directs[i];
        char *a = d->base, *b = d->base + d->size;
        char *cut_lo = a > lo ? a : lo, *cut_hi = b < hi ? b : hi;
        int rc;

        if (cut_lo >= cut_hi) { i++; continue; }
        rc = sceKernelReleaseDirectMemory( d->offset + (cut_lo - a), cut_hi - cut_lo );
        if (rc) ERR( "PWVM direct release %p-%p failed rc=%#x\\n", cut_lo, cut_hi, rc );
        if (cut_lo > a && cut_hi < b && pw_direct_count < ARRAY_SIZE(pw_directs))
        {
            /* the middle went: keep the tail as a new record and the head in this one */
            pw_directs[pw_direct_count].base = cut_hi;
            pw_directs[pw_direct_count].size = b - cut_hi;
            pw_directs[pw_direct_count].offset = d->offset + (cut_hi - a);
            pw_direct_count++;
            d->size = cut_lo - a;
            i++;
        }
        else if (cut_lo > a) { d->size = cut_lo - a; i++; }
        else if (cut_hi < b)
        {
            d->offset += cut_hi - a;
            d->base = cut_hi;
            d->size = b - cut_hi;
            i++;
        }
        else *d = pw_directs[--pw_direct_count];
    }
}

/* OrbisDesk W172: see tools/build-audio-ps4.py. virtual_mutex is held by the caller.
 * A commit of 1 MiB or more takes direct memory (W175, pw_direct_map). Otherwise, and when that
 * fails, each page Wine has as uncommitted is checked: a page counts as backed only when the region
 * the kernel reports contains it and is committed (flags bit 4; a query also succeeds for an
 * address outside any region, reporting the next one), a reservation that contains it is left to
 * pw_wine_memory_protect, and any other page gets flexible memory mapped over it. */
static void pw_commit_backing( void *base, size_t size, int unix_prot )
{
    extern int sceKernelVirtualQuery( const void *addr, int flags, void *info, size_t size );
    extern int sceKernelMapFlexibleMemory( void **addr, size_t size, int prot, int flags );
    extern int sceKernelMunmap( void *addr, size_t size );
    struct { void *start, *end; long offset; int prot, type; unsigned char flags; char name[32]; } info;
    char *page = ROUND_ADDR( base, host_page_mask );
    char *end = (char *)ROUND_SIZE( 0, (char *)base + size, host_page_mask );

    if (size >= 0x100000)
    {
        unsigned int runs = 0, run_failures = 0;
        char *p, *run = NULL;
        for (p = page; ; p += host_page_size)
        {
            BOOL open = p < end && !(get_host_page_vprot( p ) & VPROT_COMMITTED);
            if (open && !run) run = p;
            if (!open && run)
            {
                if (pw_direct_map( run, p - run, unix_prot )) run_failures++;
                else runs++;
                run = NULL;
            }
            if (p >= end) break;
        }
        if (runs && !run_failures) return;
    }
    for (; page < end; page += host_page_size)
    {
        void *at = page;
        int query, map, unmap = 0;

        if (get_host_page_vprot( page ) & VPROT_COMMITTED) continue;
        memset( &info, 0, sizeof(info) );
        query = sceKernelVirtualQuery( page, 0, &info, sizeof(info) );
        if (!query && (char *)info.start <= page && page < (char *)info.end)
        {
            /* W224: W222's fault: commit_reserved maps flexible memory during Wine's mprotect, whose
             * result Wine ignores, so a commit with the title's flexible memory used up left the
             * page without memory. A reservation page is committed here; without flexible memory,
             * with direct memory. Committed and direct pages are already backed (flags bits 4, 1). */
            static unsigned int fallbacks;

            if (info.flags & 0x12) continue;
            map = sceKernelMapFlexibleMemory( &at, host_page_size, unix_prot, 0x10 /* MAP_FIXED */ );
            if (!map && at == page) continue;
            if (!pw_direct_map( page, host_page_size, unix_prot ))
            {
                if (fallbacks++ < 16)
                    ERR( "PWVM commit_backing page=%p flexible map=%#x at=%p; direct memory instead (%u)\\n",
                         page, map, at, fallbacks );
                continue;
            }
            ERR( "PWVM commit_backing page=%p flexible map=%#x at=%p and direct memory failed; no memory\\n",
                 page, map, at );
            continue;
        }
        map = sceKernelMapFlexibleMemory( &at, host_page_size, unix_prot, 0x10 /* MAP_FIXED */ );
        if (map)
        {
            unmap = sceKernelMunmap( page, host_page_size );
            at = page;
            map = sceKernelMapFlexibleMemory( &at, host_page_size, unix_prot, 0x10 );
        }
        if (map || at != page)
            ERR( "PWVM commit_backing page=%p query=%#x region=%p-%p flags=%#x unmap=%#x map=%#x at=%p\\n",
                 page, query, info.start, info.end, info.flags, unmap, map, at );
    }
}

/* OrbisDesk W174: W173's log: the faulting 3 MiB heap block was the last of a long run (2304
 * commits of 0x2F0000, 7.3 GiB committed over the race, with as many frees), each in a region
 * the kernel reports as flexible and uncommitted. Wine gives memory back by mapping PROT_NONE
 * over it with libc mmap, which may keep the flexible memory charged; the budget is ~400 MB.
 * Here the range is unmapped first (pw_wine_memory_release: sceKernelMunmap), which returns the
 * memory, and reserved again through pw_wine_anon_tryfixed (sceKernelReserveVirtualRange), the
 * reservation pw_wine_memory_protect knows how to commit. If either fails, Wine's own PROT_NONE
 * map runs as before and the failure is logged. virtual_mutex is held by the caller. */
static void pw_rereserve( void *addr, size_t size )
{
    static unsigned int logged;
    int unmapped, unmap_error;
    void *ptr;

    pw_direct_release( addr, size );  /* W175 */
    unmapped = munmap( addr, size );
    unmap_error = unmapped ? errno : 0;
    ptr = unmapped ? MAP_FAILED : pw_wine_anon_tryfixed( addr, size, PROT_NONE, 0 );

    if (ptr == addr) return;
    if (logged++ < 32)
        ERR( "PWVM rereserve %p-%p unmap=%d errno=%d reserve=%p errno=%d; falling back to a PROT_NONE map\\n",
             addr, (char *)addr + size, unmapped, unmap_error, ptr, ptr == addr ? 0 : errno );
    anon_mmap_fixed( addr, size, PROT_NONE, MAP_NORESERVE );
}

/* OrbisDesk W222: W220's dump (SeaMonkey, direct memory off): the main thread looped without end
 * in PLDHashTable's rehash, every slot of the new calloc'd table reading e5e5e5e5 (mozjemalloc's
 * freed fill). mozjemalloc decommits and commits 4 KiB pages and, as on Windows, counts a page
 * committed again as zeroed. The console's host pages are 16 KiB and decommit_pages gives back only
 * the whole host pages inside the range, so a 4 KiB page decommitted inside a host page kept its
 * contents. Here the committed pages of a decommit that covers only part of a host page are zeroed
 * before the bits are cleared. virtual_mutex is held by the caller. */
static void pw_decommit_partial( char *base, size_t size )
{
    static unsigned int logged;
    char *end = base + size, *last = ROUND_ADDR( end - 1, host_page_mask ), *host;

    for (host = ROUND_ADDR( base, host_page_mask ); host; host = host == last ? NULL : last)
    {
        char *start = host < base ? base : host, *page;
        char *stop = host + host_page_size > end ? end : host + host_page_size;
        int unix_prot = get_unix_prot( get_host_page_vprot( host ) ), restore = 0;
        int writable = (unix_prot & (PROT_READ | PROT_WRITE)) == (PROT_READ | PROT_WRITE);
        unsigned int zeroed = 0;

        if (start == host && stop == host + host_page_size) continue;  /* given back by the caller */
        for (page = start; page < stop; page += page_size)
        {
            if (!(get_page_vprot( page ) & VPROT_COMMITTED)) continue;
            if (!writable)
            {
                if (mprotect( host, host_page_size, PROT_READ | PROT_WRITE ))
                {
                    ERR( "PWVM decommit_partial host=%p mprotect errno %d; old contents stay\\n", host, errno );
                    break;
                }
                writable = restore = 1;
            }
            memset( page, 0, page_size );
            zeroed++;
        }
        if (restore) mprotect( host, host_page_size, unix_prot );
        if (zeroed && logged++ < 8)
            ERR( "PWVM decommit_partial host=%p range=%p-%p zeroed=%u\\n", host, start, stop, zeroed );
    }
}
#endif

/***********************************************************************
 *           set_protection
''','virtual.c')
# W182: a PROT_NONE reservation at any address is a kernel reservation. W180: Pale Moon reserves
# 1 GiB (0x40010000) with nothing mapped, and the console refused that anonymous mmap with EINVAL;
# Pale Moon then stopped on a breakpoint and took the title with it. sceKernelReserveVirtualRange
# holds address space without memory, as pw_wine_anon_tryfixed does for fixed addresses, and
# commits find it the same way. If the kernel refuses, the mmap runs as before.
text=substitute(text,'''void *anon_mmap_alloc( size_t size, int prot )
{
    assert( !(size & host_page_mask) );

    return mmap( NULL, size, prot, MAP_PRIVATE | MAP_ANON, -1, 0 );
}''','''void *anon_mmap_alloc( size_t size, int prot )
{
    assert( !(size & host_page_mask) );

#ifdef __ORBIS__
    if (prot == PROT_NONE)
    {
        extern int pw_ps4_kernel_reserve( void **address, size_t bytes, int flags, size_t alignment );
        void *ptr = NULL;
        int rc = pw_ps4_kernel_reserve( &ptr, size, 0, host_page_size );

        if (!rc && ptr) return ptr;
        ERR( "PWVM reserve of %#zx bytes failed rc=%#x; trying mmap\\n", size, rc );
    }
#endif
    return mmap( NULL, size, prot, MAP_PRIVATE | MAP_ANON, -1, 0 );
}''','virtual.c')
# W184: a new view of 1 MiB or more that is committed from the start takes direct memory too.
# W183: Pale Moon, run alone, asked for 8 MiB read/write (0x810000, prot 3); the console refused the
# anonymous mmap with EINVAL and xul then read NULL+0x80. Such a view is now a kernel reservation
# (anon_mmap_alloc with PROT_NONE, W182) and, after the alignment slack is trimmed, direct memory
# zeroed over it (pw_direct_map, as for large commits), released with the view (unmap_area). If
# that fails, the protection change commits flexible memory over the reservation; if that fails
# too, the allocation returns STATUS_NO_MEMORY with a line in the log.
text=substitute(text,'''        size_t unmap_size, view_size = host_size + align_mask + 1;''','''        size_t unmap_size, view_size = host_size + align_mask + 1;
#ifdef __ORBIS__
        int pw_backing_prot = (unix_prot && view_size >= 0x100000) ? unix_prot : 0;
#endif''','virtual.c')
text=substitute(text,'''            if ((ptr = anon_mmap_alloc( view_size, unix_prot )) == MAP_FAILED)''','''#ifdef __ORBIS__
            if ((ptr = anon_mmap_alloc( view_size, pw_backing_prot ? PROT_NONE : unix_prot )) == MAP_FAILED)
#else
            if ((ptr = anon_mmap_alloc( view_size, unix_prot )) == MAP_FAILED)
#endif''','virtual.c')
text=substitute(text,'''        ptr = unmap_extra_space( ptr, view_size, host_size, align_mask );''','''        ptr = unmap_extra_space( ptr, view_size, host_size, align_mask );
#ifdef __ORBIS__
        if (pw_backing_prot && pw_direct_map( ptr, host_size, pw_backing_prot ) &&
            mprotect( ptr, host_size, pw_backing_prot ))
        {
            ERR( "PWVM view %p-%p (prot %#x) got no memory, errno %d\\n", ptr, (char *)ptr + host_size,
                 pw_backing_prot, errno );
            unmap_area( ptr, host_size );
            return STATUS_NO_MEMORY;
        }
        if (pw_backing_prot && pw_backing_prot != (PROT_READ | PROT_WRITE)) mprotect( ptr, host_size, pw_backing_prot );
#endif''','virtual.c')
# W174: free and decommit return flexible memory (pw_rereserve above; unmap_area comes first in
# virtual.c, so it is declared there).
# W224: an access violation on a page Wine has committed with an access that allows it (W222:
# SeaMonkey's memcpy wrote to a page it had just committed) is logged with the kernel's view.
text=substitute(text,'''    mutex_unlock( &virtual_mutex );
    rec->ExceptionCode = ret;
    return ret;
}''','''#ifdef __ORBIS__
    if (ret == STATUS_ACCESS_VIOLATION && (get_page_vprot( addr ) & VPROT_COMMITTED) &&
        (get_unix_prot( get_page_vprot( addr )) & (err == EXCEPTION_WRITE_FAULT ? PROT_WRITE :
                                                   err == EXCEPTION_EXECUTE_FAULT ? PROT_EXEC : PROT_READ)))
    {
        extern int sceKernelVirtualQuery( const void *addr, int flags, void *info, size_t size );
        extern int sceKernelAvailableFlexibleMemorySize( size_t *size );
        struct { void *start, *end; long offset; int prot, type; unsigned char flags; char name[32]; } info;
        static unsigned int logged;
        size_t flexible = 0;
        int query, avail;

        if (logged++ < 16)
        {
            memset( &info, 0, sizeof(info) );
            query = sceKernelVirtualQuery( page, 0, &info, sizeof(info) );
            avail = sceKernelAvailableFlexibleMemorySize( &flexible );
            ERR( "PWVM fault_committed addr=%p err=%lu vprot=%02x,%02x,%02x,%02x query=%#x region=%p-%p prot=%#x "
                 "flags=%#x flexible_free=%zu (%#x)\\n", addr, (unsigned long)err,
                 get_page_vprot( page ), get_page_vprot( page + 0x1000 ), get_page_vprot( page + 0x2000 ),
                 get_page_vprot( page + 0x3000 ), query, info.start, info.end, info.prot, info.flags, flexible, avail );
        }
    }
#endif
    mutex_unlock( &virtual_mutex );
    rec->ExceptionCode = ret;
    return ret;
}''','virtual.c')
text=substitute(text,'''static void unmap_area( void *start, size_t size )
{''','''#ifdef __ORBIS__
static void pw_rereserve( void *addr, size_t size );
static void pw_direct_release( void *start, size_t size );
#endif
static void unmap_area( void *start, size_t size )
{''','virtual.c')
# W175: a released range gives its direct memory back first (outside reserved areas Wine only
# munmaps, which does not free direct memory).
text=substitute(text,'''    if (!(size = unmap_area_above_user_limit( start, size ))) return;

    end = (char *)start + size;''','''    if (!(size = unmap_area_above_user_limit( start, size ))) return;
#ifdef __ORBIS__
    pw_direct_release( start, size );
#endif

    end = (char *)start + size;''','virtual.c')
text=substitute(text,'''            anon_mmap_fixed( start, (char *)end - (char *)start, PROT_NONE, MAP_NORESERVE );
            return;''','''#ifdef __ORBIS__
            pw_rereserve( start, (char *)end - (char *)start );
#else
            anon_mmap_fixed( start, (char *)end - (char *)start, PROT_NONE, MAP_NORESERVE );
#endif
            return;''','virtual.c')
text=substitute(text,'''        anon_mmap_fixed( start, (char *)area_end - (char *)start, PROT_NONE, MAP_NORESERVE );''','''#ifdef __ORBIS__
        pw_rereserve( start, (char *)area_end - (char *)start );
#else
        anon_mmap_fixed( start, (char *)area_end - (char *)start, PROT_NONE, MAP_NORESERVE );
#endif''','virtual.c')
text=substitute(text,'''    if (host_start < host_end) anon_mmap_fixed( host_start, host_end - host_start, PROT_NONE, 0 );''','''#ifdef __ORBIS__
    pw_decommit_partial( base, size );  /* W222 */
    if (host_start < host_end) pw_rereserve( host_start, host_end - host_start );
#else
    if (host_start < host_end) anon_mmap_fixed( host_start, host_end - host_start, PROT_NONE, 0 );
#endif''','virtual.c')
selected=work/'virtual.c';selected.write_text(text)
obj=work/'virtual.o'
command=[str(selected) if arg==str(original) else str(obj) if arg==str(ROOT/'build/wine-boot/virtual.o') else arg
         for arg in entry['command']]
if str(obj) not in command or str(selected) not in command:raise SystemExit('virtual.o recipe changed')
with (work/'virtual.log').open('w') as log:
    run=subprocess.run(command,cwd=UNIX,stdout=log,stderr=subprocess.STDOUT)
if run.returncode:raise SystemExit('cannot compile virtual.c; see '+str(work/'virtual.log'))
report['objects']['virtual']={'object':str(obj.relative_to(ROOT)),'sha256':sha(obj),
                              'original_source_sha256':sha(original),'source_sha256':sha(selected)}
report['builder_sha256']=sha(pathlib.Path(__file__))
(work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v['sha256'] for k,v in report['objects'].items()}))
