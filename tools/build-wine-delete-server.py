#!/usr/bin/env python3
"""W109: audit the server's actual directory-empty check with the proven compile recipe.

Phase 8: the same build also revises server/sock.c (network sockets). wineserver made each
socket non-blocking with fcntl(F_SETFL, O_NONBLOCK), which the console refuses on a socket
(W013), so sockets stayed blocking and connect/accept would block the in-process server. The
three calls go to pw_wine_socket_nonblock (platform/ps4/pw_wine_net.c: fcntl, then libSceNet's
SO_NBIO, traced when both fail). The one MSG_DONTWAIT recv gets the kernel's flag number (the
SDK's 0x40 is FreeBSD's MSG_WAITALL)."""
import pathlib,json,hashlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
base=json.loads((ROOT/'build/wine-server/report.json').read_text())
entry=next(e for e in base['results'] if e['unit']=='fd')
source=ROOT/'.deps/wine/ps4-overlay/server/fd.c'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
if sha(source)!=entry['source_sha256']:raise SystemExit('Server fd source changed from proven input')
work=ROOT/'build/delete-server-ps4';work.mkdir(parents=True,exist_ok=True)
text=source.read_text();start=text.index('static int is_dir_empty( int fd )');end=text.index('\nstatic inline int is_valid_mounted_device',start)
replacement=r'''static int is_dir_empty( int original )
{
    DIR *dir;
    struct dirent *de;
    int fd, empty = 1, saved;
    if ((fd = dup(original)) == -1) return -1;
    if (!(dir = fdopendir(fd))) { saved = errno; close(fd); errno = saved; return -1; }
    errno = 0;
    rewinddir(dir);
    if (errno) empty = -1;
    while (empty == 1)
    {
        errno = 0;
        de = readdir(dir);
        if (!de) { if (errno) empty = -1; break; }
        if (!strcmp(de->d_name,".") || !strcmp(de->d_name,"..")) continue;
        fprintf(stderr,"PWDELETE blocking_entry fd=%d name=%s\n",original,de->d_name);
        empty = 0;
    }
    saved = errno;
    closedir(dir);
    {
        /* alpha-1: an empty directory (the delete goes on) is traced only with traces (platform/ps4/pw_trace.h);
         * a full or unreadable one always, with the blocking entry above */
        extern int pw_trace_enabled( void );
        if (empty != 1 || pw_trace_enabled())
            fprintf(stderr,"PWDELETE empty_check fd=%d result=%d errno=%d\n",original,empty,empty<0?saved:0);
    }
    errno = saved;
    return empty;
}
'''
selected=work/'fd.c';selected.write_text(text[:start]+replacement+text[end:]);obj=work/'fd.o'
# Wnnn (W199: Pale Moon as a guest; every thread that calls the server stopped, the explorer
# dump stopped at its first server call): a watchdog thread in the server reports a main-loop
# step (fd event, request included, or timer) running more than 5 s. Read only.
fd_text=selected.read_text()
for old,new in (
    ('''static inline void fd_poll_event( struct fd *fd, int event )
{
    if (fd->fd_ops->poll_event) fd->fd_ops->poll_event( fd, event );
    else default_poll_event( fd, event );
}''',
     '''#ifdef __ORBIS__
/* OrbisDesk Wnnn: the main loop's progress, for pw_server_watch. pw_server_step is odd while a
 * step runs; the watchdog reports one that has not ended after 5 s (tools/build-wine-delete-server.py) */
#include <pthread.h>
#include <stdio.h>
static volatile unsigned int pw_server_step;
static volatile int pw_server_kind, pw_server_unix_fd, pw_server_event;
static void *volatile pw_server_func;

static void *pw_server_watch( void *arg )
{
    unsigned int seen = 0, stuck = 0;

    for (;;)
    {
        unsigned int step;
        char text[256];
        int len = 0;

        sleep( 1 );
        step = pw_server_step;
        if ((step & 1) && step == seen)
        {
            if (++stuck == 5 || stuck == 20 || !(stuck % 60))
            {
                struct thread *client = current;  /* set while a request is handled */

                len = snprintf( text, sizeof(text),
                                "PWSERVER stuck_s=%u kind=%s func=%p watch=%p unix_fd=%d event=%x client=%04x req=%d\\n",
                                stuck, pw_server_kind == 1 ? "fd" : "timer", pw_server_func, (void *)pw_server_watch,
                                pw_server_unix_fd,
                                pw_server_event, client ? client->id : 0,
                                client ? (int)client->req.request_header.req : -1 );
            }
        }
        else
        {
            if (stuck >= 5) len = snprintf( text, sizeof(text), "PWSERVER resumed after_s=%u\\n", stuck );
            stuck = 0;
        }
        if (len > 0) write( 2, text, len < (int)sizeof(text) ? len : (int)sizeof(text) - 1 );
        seen = step;
    }
    return arg;
}
#endif

static inline void fd_poll_event( struct fd *fd, int event )
{
#ifdef __ORBIS__
    pw_server_kind = 1;
    pw_server_func = (void *)fd->fd_ops->poll_event;
    pw_server_unix_fd = fd->unix_fd;
    pw_server_event = event;
    pw_server_step++;
#endif
    if (fd->fd_ops->poll_event) fd->fd_ops->poll_event( fd, event );
    else default_poll_event( fd, event );
#ifdef __ORBIS__
    pw_server_step++;
#endif
}'''),
    ('''            list_remove( &timeout->entry );
            timeout->callback( timeout->private );
            free( timeout );''',
     '''            list_remove( &timeout->entry );
#ifdef __ORBIS__
            pw_server_kind = 2;
            pw_server_func = (void *)timeout->callback;
            pw_server_unix_fd = -1;
            pw_server_event = 0;
            pw_server_step++;
#endif
            timeout->callback( timeout->private );
#ifdef __ORBIS__
            pw_server_step++;
#endif
            free( timeout );'''),
    ('''        ret = poll( pollfd, nb_users, timeout );
        set_current_time();
''',
     '''        ret = poll( pollfd, nb_users, timeout );
        set_current_time();
#ifdef __ORBIS__
        /* OrbisDesk W202: a failing poll() reads no request at all (W192-W201: platform/ps4
         * pw_wine_poll refused more than 256 descriptors); traced, the loop is unchanged */
        if (ret < 0)
        {
            static unsigned int failures;
            if (failures++ < 5 || !(failures % 100000))
                fprintf( stderr, "PWSERVER poll_failed n=%u errno=%d users=%d active=%d\\n",
                         failures, errno, nb_users, active_users );
        }
#endif
'''),
    ('''    main_loop_epoll();
    /* fall through to normal poll loop */
''',
     '''    main_loop_epoll();
    /* fall through to normal poll loop */
#if defined(__ORBIS__) && defined(USE_EPOLL)
    fprintf( stderr, "PWSERVER poll_loop epoll_fd=%d\\n", epoll_fd );  /* OrbisDesk W202 */
#endif
'''),
    # W268 (W266: NFS Underground 2 stalled 1-4 s in explorer's world until a pad or key event): server timers that
    # fire late and poll() waits longer than asked. Read only.
    ('''static int get_next_timeout( struct timespec *ts )
{''',
     '''#ifdef __ORBIS__
/* OrbisDesk W268 (W266: NFS Underground 2 stalled until a pad or key event): server timers that expire more than
 * 50 ms late and poll() waits that last more than 50 ms past their timeout; the first 20 of each, then every 100th */
static unsigned int pw_late_timers, pw_late_wakes;
static timeout_t pw_poll_start;

extern int pw_trace_enabled( void );  /* alpha-1: W268's lines, traces only (platform/ps4/pw_trace.h) */

static void pw_late_timer( const char *list, timeout_t late, void *callback )
{
    if (late > 50 * 10000 && pw_trace_enabled() && (pw_late_timers++ < 20 || !(pw_late_timers % 100)))
        fprintf( stderr, "PWSERVER late_timer n=%u late_ms=%lld list=%s callback=%p\\n", pw_late_timers,
                 (long long)(late / 10000), list, callback );
}
#endif

static int get_next_timeout( struct timespec *ts )
{'''),
    ('''            if (timeout->when <= current_time)
            {
''',
     '''            if (timeout->when <= current_time)
            {
#ifdef __ORBIS__
                pw_late_timer( "abs", current_time - timeout->when, (void *)timeout->callback );  /* W268 */
#endif
'''),
    ('''            if (-timeout->when <= monotonic_time)
            {
''',
     '''            if (-timeout->when <= monotonic_time)
            {
#ifdef __ORBIS__
                pw_late_timer( "rel", monotonic_time + timeout->when, (void *)timeout->callback );  /* W268 */
#endif
'''),
    ('''        ret = poll( pollfd, nb_users, timeout );
        set_current_time();
''',
     '''#ifdef __ORBIS__
        pw_poll_start = pw_trace_enabled() ? monotonic_counter() : 0;  /* W268; alpha-1: no clock read without traces */
#endif
        ret = poll( pollfd, nb_users, timeout );
        set_current_time();
#ifdef __ORBIS__
        if (pw_poll_start && timeout >= 0 && (monotonic_time - pw_poll_start) / 10000 > (timeout_t)timeout + 50 &&
            (pw_late_wakes++ < 20 || !(pw_late_wakes % 100)))
            fprintf( stderr, "PWSERVER late_wake n=%u asked_ms=%d took_ms=%lld ret=%d users=%d\\n", pw_late_wakes,
                     timeout, (long long)((monotonic_time - pw_poll_start) / 10000), ret, nb_users );
#endif
'''),
    ('''void main_loop(void)
{
    int i, ret, timeout;
''',
     '''void main_loop(void)
{
    int i, ret, timeout;
#ifdef __ORBIS__
    pthread_t watch;
    int watch_rc = pthread_create( &watch, NULL, pw_server_watch, NULL );

    fprintf( stderr, "PWSERVER watch rc=%d\\n", watch_rc );
    if (!watch_rc) pthread_detach( watch );
#endif
''')):
    if fd_text.count(old)!=1:raise SystemExit('Unexpected context in server/fd.c: '+old[:60])
    fd_text=fd_text.replace(old,new)
selected.write_text(fd_text)
command=[str(selected) if arg==str(source) else str(obj) if arg==str(ROOT/'build/wine-server/fd.o') else arg for arg in entry['command']]
with (work/'compile.log').open('w') as log:subprocess.run(command,cwd=ROOT/'.deps/wine/ps4-unix',stdout=log,stderr=subprocess.STDOUT,check=True)
# Phase 8: server/sock.c, as described above
sock_entry=next(e for e in base['results'] if e['unit']=='sock')
sock_source=ROOT/'.deps/wine/ps4-overlay/server/sock.c'
if sha(sock_source)!=sock_entry['source_sha256']:raise SystemExit('Server sock source changed from proven input')
sock_text=sock_source.read_text()
for old,new in (('    fcntl(sockfd, F_SETFL, O_NONBLOCK); /* make socket nonblocking */',
                 '    pw_wine_socket_nonblock( sockfd ); /* make socket nonblocking (OrbisDesk phase 8) */'),
                ('        fcntl( acceptfd, F_SETFL, O_NONBLOCK );',
                 '        pw_wine_socket_nonblock( acceptfd ); /* OrbisDesk phase 8 */'),
                ('    fcntl( unix_fd, F_SETFL, O_NONBLOCK ); /* make socket nonblocking */',
                 '    pw_wine_socket_nonblock( unix_fd ); /* make socket nonblocking (OrbisDesk phase 8) */'),
                ('    r = recv( get_unix_fd(fd), buffer, sizeof(buffer), MSG_DONTWAIT );',
                 '    r = recv( get_unix_fd(fd), buffer, sizeof(buffer), pw_wine_kernel_msg_flags( MSG_DONTWAIT ) ); /* OrbisDesk phase 8 */')):
    if sock_text.count(old)!=1:raise SystemExit('Unexpected context in server/sock.c: '+old[:60])
    sock_text=sock_text.replace(old,new)
sock_selected=work/'sock.c';sock_selected.write_text(sock_text);sock_obj=work/'sock.o'
sock_command=[str(sock_selected) if arg==str(sock_source) else str(sock_obj) if arg==str(ROOT/'build/wine-server/sock.o') else arg
              for arg in sock_entry['command']]
if str(sock_obj) not in sock_command or str(sock_selected) not in sock_command:raise SystemExit('sock.o recipe changed')
with (work/'sock-compile.log').open('w') as log:
    subprocess.run(sock_command,cwd=ROOT/'.deps/wine/ps4-unix',stdout=log,stderr=subprocess.STDOUT,check=True)
# W186: server/thread.c. Another thread's context needs that thread stopped, which the server
# asks for with SIGUSR1; the console has no thread-directed signal (W064, ptrace.c), so the
# request stayed STATUS_PENDING and GetThreadContext/SetThreadContext waited for good. Pale
# Moon's hang monitor does that while holding a lock its UI thread needs: W184/W185 froze with
# "RtlpWaitForCriticalSection … blocked by 0050" right after "thread_signal unavailable … sig=10".
# When the signal cannot be sent, the pending context is dropped as for a thread that died
# (cleanup_thread) and the context request fails with STATUS_UNSUCCESSFUL. SuspendThread itself
# is unchanged: the thread still stops at its next server call.
thread_entry=next(e for e in base['results'] if e['unit']=='thread')
thread_source=ROOT/'.deps/wine/source/server/thread.c'
if sha(thread_source)!=thread_entry['source_sha256']:raise SystemExit('Server thread source changed from proven input')
thread_text=thread_source.read_text()
for old,new in (
    ('''    if (is_process_init_done(thread->process)) send_thread_signal( thread, SIGUSR1 );''',
     '''    if (is_process_init_done(thread->process) && !send_thread_signal( thread, SIGUSR1 ))
    {
#ifdef __ORBIS__
        /* OrbisDesk W186: no signal reaches the thread here (tools/build-wine-delete-server.py) */
        thread->context->status = STATUS_UNSUCCESSFUL;
        signal_sync( thread->context->sync );
        release_object( thread->context );
        thread->context = NULL;
#endif
    }'''),
    ('''            if (thread != current) stop_thread( thread );''',
     '''            if (thread != current) stop_thread( thread );
            if (thread != current && !thread->context) set_error( STATUS_UNSUCCESSFUL );  /* OrbisDesk W186 */'''),
    ('''        if (thread != current) stop_thread( thread );
        else if (flags) set_thread_context( thread, &contexts[CTX_NATIVE], flags );''',
     '''        if (thread != current) stop_thread( thread );
        else if (flags) set_thread_context( thread, &contexts[CTX_NATIVE], flags );
        if (thread != current && !thread->context) set_error( STATUS_UNSUCCESSFUL );  /* OrbisDesk W186 */'''),
    # W278 (W276: SetThreadAffinityMask failed with ENOSYS, "can't map error Function not implemented"): the SDK's
    # sched_setaffinity is Linux's; a thread's cores are set through libkernel (platform/ps4/pw_wine_threads.c)
    ('''int set_thread_affinity( struct thread *thread, affinity_t affinity )
{
    int ret = 0;
#ifdef HAVE_SCHED_SETAFFINITY''',
     '''int set_thread_affinity( struct thread *thread, affinity_t affinity )
{
    int ret = 0;
#ifdef __ORBIS__
    if (thread->unix_tid != -1)
    {
        extern int pw_wine_thread_setaffinity( long tid, unsigned long long mask );
        ret = pw_wine_thread_setaffinity( thread->unix_tid, affinity );
    }
#elif defined(HAVE_SCHED_SETAFFINITY)''')):
    if thread_text.count(old)!=1:raise SystemExit('Unexpected context in server/thread.c: '+old[:60])
    thread_text=thread_text.replace(old,new)
thread_selected=work/'thread.c';thread_selected.write_text(thread_text);thread_obj=work/'thread.o'
thread_command=[str(thread_selected) if arg==str(thread_source) else str(thread_obj) if arg==str(ROOT/'build/wine-server/thread.o') else arg
                for arg in thread_entry['command']]
if str(thread_obj) not in thread_command or str(thread_selected) not in thread_command:raise SystemExit('thread.o recipe changed')
with (work/'thread-compile.log').open('w') as log:
    subprocess.run(thread_command,cwd=ROOT/'.deps/wine/ps4-unix',stdout=log,stderr=subprocess.STDOUT,check=True)
# W190: server/registry.c. The server writes the registry to disk every 30 s and when it shuts
# down; the console kills the title, so a change made in the last 30 s was lost (W189: winecfg's
# theme, OK about 7 s before the app was quit, came back as the old one). RegFlushKey did nothing
# (flush_key). On the console flush_key writes the changed branches as Windows does, and the
# periodic save runs every 5 s; save_branch writes only branches that changed.
registry_entry=next(e for e in base['results'] if e['unit']=='registry')
registry_source=ROOT/'.deps/wine/source/server/registry.c'
if sha(registry_source)!=registry_entry['source_sha256']:raise SystemExit('Server registry source changed from proven input')
registry_text=registry_source.read_text()
for old,new in (
    ('''static const timeout_t save_period = 30 * -TICKS_PER_SEC;  /* delay between periodic saves */''',
     '''#ifdef __ORBIS__
/* OrbisDesk W190: the console kills the title without a server shutdown (tools/build-wine-delete-server.py) */
static const timeout_t save_period = 5 * -TICKS_PER_SEC;  /* delay between periodic saves */
#else
static const timeout_t save_period = 30 * -TICKS_PER_SEC;  /* delay between periodic saves */
#endif'''),
    ('''        /* we don't need to do anything here with the current implementation */
        release_object( key );''',
     '''#ifdef __ORBIS__
        /* OrbisDesk W190: write the changed branches now; the title is killed, not shut down */
        flush_registry();
#endif
        release_object( key );''')):
    if registry_text.count(old)!=1:raise SystemExit('Unexpected context in server/registry.c: '+old[:60])
    registry_text=registry_text.replace(old,new)
registry_selected=work/'registry.c';registry_selected.write_text(registry_text);registry_obj=work/'registry.o'
registry_command=[str(registry_selected) if arg==str(registry_source) else str(registry_obj) if arg==str(ROOT/'build/wine-server/registry.o') else arg
                  for arg in registry_entry['command']]
if str(registry_obj) not in registry_command or str(registry_selected) not in registry_command:raise SystemExit('registry.o recipe changed')
with (work/'registry-compile.log').open('w') as log:
    subprocess.run(registry_command,cwd=ROOT/'.deps/wine/ps4-unix',stdout=log,stderr=subprocess.STDOUT,check=True)
# W195: server/ptrace.c. SIGUSR1 (suspend, another thread's context) goes to the one thread
# through pw_wine_thread_kill (platform/ps4/pw_wine_threads.c: kernel id to pthread_t, then
# libkernel's pthread_kill). W194: Mono (The Lost Forest, Unity) stops other threads for its
# GC with SuspendThread/GetThreadContext; without the signal the request failed (W186) and was
# retried for good ("thread_signal unavailable thread=004c sig=10", about 17 800 times). Other
# signals stay unavailable as in W064 (SIGQUIT to a running thread had ended the title).
ptrace_entry=next(e for e in base['results'] if e['unit']=='ptrace')
ptrace_source=ROOT/'.deps/wine/ps4-overlay/server/ptrace.c'
if sha(ptrace_source)!=ptrace_entry['source_sha256']:raise SystemExit('Server ptrace source changed from proven input')
ptrace_text=ptrace_source.read_text()
for old,new in (
    ('''#ifdef __ORBIS__
        fprintf( stderr, "PWBOOT thread_signal unavailable thread=%04x sig=%d\\n", thread->id, sig );
        errno = ENOSYS;
#else''',
     '''#ifdef __ORBIS__
        extern int pw_wine_thread_kill( int pid, long tid, int sig );
        if (sig == SIGUSR1) ret = pw_wine_thread_kill( thread->unix_pid, thread->unix_tid, sig );  /* OrbisDesk W195 */
        else
        {
            fprintf( stderr, "PWBOOT thread_signal unavailable thread=%04x sig=%d\\n", thread->id, sig );
            errno = ENOSYS;
        }
#else'''),):
    if ptrace_text.count(old)!=1:raise SystemExit('Unexpected context in server/ptrace.c: '+old[:60])
    ptrace_text=ptrace_text.replace(old,new)
ptrace_selected=work/'ptrace.c';ptrace_selected.write_text(ptrace_text);ptrace_obj=work/'ptrace.o'
ptrace_command=[str(ptrace_selected) if arg==str(ptrace_source) else str(ptrace_obj) if arg==str(ROOT/'build/wine-server/ptrace.o') else arg
                for arg in ptrace_entry['command']]
if str(ptrace_obj) not in ptrace_command or str(ptrace_selected) not in ptrace_command:raise SystemExit('ptrace.o recipe changed')
with (work/'ptrace-compile.log').open('w') as log:
    subprocess.run(ptrace_command,cwd=ROOT/'.deps/wine/ps4-unix',stdout=log,stderr=subprocess.STDOUT,check=True)
# W279 (W278: NFS Underground 2 called SetProcessAffinityMask(1); once thread affinity worked, that put every thread
# of the title on core 0, explorer and the server included, and its own new threads still went to the core its guest
# was kept on, so it ran on two cores again and crashed): programs run as guests of this one process, so a process
# affinity change is refused with STATUS_ACCESS_DENIED and traced; a thread's own affinity still applies.
process_entry=next(e for e in base['results'] if e['unit']=='process')
process_source=next(p for p in (ROOT/'.deps/wine/ps4-overlay/server/process.c',ROOT/'.deps/wine/source/server/process.c')
                    if p.exists() and sha(p)==process_entry['source_sha256'])
process_text=process_source.read_text()
old='''        if (req->mask & SET_PROCESS_INFO_AFFINITY) set_process_affinity( process, req->affinity );'''
if process_text.count(old)!=1:raise SystemExit('Unexpected context in server/process.c: '+old[:60])
process_text=process_text.replace(old,'''#ifdef __ORBIS__
        if (req->mask & SET_PROCESS_INFO_AFFINITY)
        {
            /* OrbisDesk W279: one process holds every program (tools/build-wine-delete-server.py) */
            fprintf( stderr, "PWTHREAD process_affinity refused mask=%llx by thread %04x\\n",
                     (unsigned long long)req->affinity, current ? current->id : 0 );
            set_error( STATUS_ACCESS_DENIED );
        }
#else
        if (req->mask & SET_PROCESS_INFO_AFFINITY) set_process_affinity( process, req->affinity );
#endif''')
process_selected=work/'process.c';process_selected.write_text(process_text);process_obj=work/'process.o'
process_command=[str(process_selected) if arg==str(process_source) else str(process_obj) if arg==str(ROOT/'build/wine-server/process.o') else arg
                 for arg in process_entry['command']]
if str(process_obj) not in process_command or str(process_selected) not in process_command:raise SystemExit('process.o recipe changed')
with (work/'process-compile.log').open('w') as log:
    subprocess.run(process_command,cwd=ROOT/'.deps/wine/ps4-unix',stdout=log,stderr=subprocess.STDOUT,check=True)
units=[]
for unit in base['results']:
    original=ROOT/'build/wine-server'/(unit['unit']+'.o')
    if sha(original)!=unit['object_sha256']:raise SystemExit('Original server object changed: '+unit['unit'])
    units.append(obj if unit['unit']=='fd' else sock_obj if unit['unit']=='sock' else
                 thread_obj if unit['unit']=='thread' else registry_obj if unit['unit']=='registry' else
                 ptrace_obj if unit['unit']=='ptrace' else process_obj if unit['unit']=='process' else original)
combined=work/'combined.o'
subprocess.run(['ld.lld','-r','-o',str(combined),*map(str,units)],check=True)
mapping=ROOT/'build/wine-server/namespace.txt'
namespaced=work/'inprocess.o'
subprocess.run(['objcopy','--redefine-syms='+str(mapping),str(combined),str(namespaced)],check=True)
report={'wine_commit':base['wine_commit'],'original_source_sha256':sha(source),'source_sha256':sha(selected),
        'fd_object_sha256':sha(obj),'object':str(namespaced.relative_to(ROOT)),'object_sha256':sha(namespaced),
        'namespace_sha256':sha(mapping),'original_units_verified':len(units),'command':command,
        'sock':{'original_source_sha256':sha(sock_source),'source_sha256':sha(sock_selected),
                'object_sha256':sha(sock_obj),'command':sock_command},
        'thread':{'original_source_sha256':sha(thread_source),'source_sha256':sha(thread_selected),
                  'object_sha256':sha(thread_obj),'command':thread_command},
        'registry':{'original_source_sha256':sha(registry_source),'source_sha256':sha(registry_selected),
                    'object_sha256':sha(registry_obj),'command':registry_command},
        'ptrace':{'original_source_sha256':sha(ptrace_source),'source_sha256':sha(ptrace_selected),
                  'object_sha256':sha(ptrace_obj),'command':ptrace_command}}
(work/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
