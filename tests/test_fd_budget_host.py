#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Exercise prepared Wine cache functions with real descriptors and a low host limit."""
import pathlib, re, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from wine_fd_pressure import patch_server, patch_cache_budget

source = (ROOT / '.deps/wine/source/dlls/ntdll/unix/server.c').read_text()
prepared = patch_cache_budget(patch_server(source))
assert patch_cache_budget(prepared) == prepared
for bad in ('unexpected', prepared.replace('PW_FILE_FD_CACHE_LIMIT = 64', 'PW_FILE_FD_CACHE_LIMIT = 63')):
    try:
        patch_cache_budget(bad)
    except ValueError:
        pass
    else:
        raise AssertionError('partial/stale cache patch accepted')

types = (ROOT / '.deps/wine/source/include/wine/server_protocol.h').read_text()
enum = re.search(r'enum server_fd_type\s*\{[^}]+\};', types).group()
cache = prepared[prepared.index('union fd_cache_entry\n{'):prepared.index('/***********************************************************************\n *           wine_server_fd_to_handle')]
code = r'''
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <unistd.h>
typedef int64_t LONG64;
typedef uintptr_t HANDLE;
typedef unsigned obj_handle_t;
typedef int BOOL;
typedef int32_t NTSTATUS;
#define TRUE 1
#define FALSE 0
#define __ORBIS__ 1
#define C_ASSERT(x) _Static_assert(x, #x)
#define STATUS_SUCCESS 0
#define STATUS_INVALID_HANDLE ((int)0xc0000008)
#define STATUS_TOO_MANY_OPENED_FILES ((int)0xc000011f)
#define STATUS_NO_MEMORY ((int)0xc0000017)
#define STATUS_INSUFFICIENT_RESOURCES ((int)0xc000009a)
#define FILE_READ_DATA 1
#define FILE_WRITE_DATA 2
#define FILE_APPEND_DATA 4
#define STATUS_ACCESS_DENIED ((int)0xc0000022)
#define PROT_READ 1
#define PROT_WRITE 2
#define MAP_FAILED ((void*)-1)
#define FIXME(...) ((void)0)
static void *anon_mmap_alloc(size_t n,int p){return calloc(1,n);}
static LONG64 interlocked_xchg64(LONG64 *p,LONG64 v){return __atomic_exchange_n(p,v,__ATOMIC_SEQ_CST);}
static LONG64 InterlockedCompareExchange64(LONG64 *p,LONG64 v,LONG64 c){__atomic_compare_exchange_n(p,&c,v,0,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST);return c;}
static unsigned wine_server_obj_handle(HANDLE h){return h;}
static HANDLE wine_server_ptr_handle(unsigned h){return h;}
static pthread_mutex_t fd_cache_mutex=PTHREAD_MUTEX_INITIALIZER;
static void server_enter_uninterrupted_section(pthread_mutex_t *m,sigset_t *s){assert(!pthread_mutex_lock(m));}
static void server_leave_uninterrupted_section(pthread_mutex_t *m,sigset_t *s){assert(!pthread_mutex_unlock(m));}
static unsigned current_handle;static int server_status,received,receive_fail;
static int server_fds[300];
struct response {int cacheable,type,access,options;};
static struct response mock_reply={1,1,7,0};
static int wine_server_call(void *req){return server_status;}
static int wine_server_receive_fd(obj_handle_t *h){received++;*h=current_handle;if(receive_fail)return -1;return dup(server_fds[current_handle/4-1]);}
#define SERVER_START_REQ(name) {struct {HANDLE handle;} request,*req=&request;struct response *reply=&mock_reply;
#define SERVER_END_REQ }
''' + enum + '\n' + cache + r'''
static void reset(void){
 for(unsigned i=0;i<300;i++){
  HANDLE h=(i+1)*4;
  pthread_mutex_lock(&fd_cache_mutex);int fd=remove_fd_from_cache(h);pthread_mutex_unlock(&fd_cache_mutex);
  if(fd>=0)assert(!close(fd));
  if(server_fds[i]>=0){assert(!close(server_fds[i]));server_fds[i]=-1;}
 }
 assert(!pw_cached_file_fds);
 unsigned retained,peak,bypasses,limit;
 pthread_mutex_lock(&fd_cache_mutex);
 pw_wine_fd_cache_snapshot(&retained,&peak,&bypasses,&limit);
 pthread_mutex_unlock(&fd_cache_mutex);
 assert(!retained && peak<=64 && limit==64);
}
static void *reuse(void *arg){
 HANDLE h=(uintptr_t)arg;
 for(int i=0;i<1000;i++){
  int fd,need;assert(!server_get_unix_fd(h,1,&fd,&need,NULL,NULL));
  assert(!need && fcntl(fd,F_GETFD)>=0);
 }
 return NULL;
}
int main(void){
 for(unsigned i=0;i<300;i++)server_fds[i]=-1;
 struct rlimit old,limit;assert(!getrlimit(RLIMIT_NOFILE,&old));limit=old;limit.rlim_cur=256;
 assert(!setrlimit(RLIMIT_NOFILE,&limit));
 // A real low-limit reproduction: retaining both sides cannot open 160 files.
 int kept[320],n=0;
 for(;n<320;n++){kept[n]=open("/dev/null",O_RDONLY);if(kept[n]<0)break;}
 assert(n<320 && errno==EMFILE);for(int i=0;i<n;i++)assert(!close(kept[i]));
 // Actual prepared Wine functions keep only 64 extra copies and serve all 160.
 for(unsigned i=0;i<160;i++){
  server_fds[i]=open("/dev/null",O_RDONLY);assert(server_fds[i]>=0);
  current_handle=(i+1)*4;int fd,need;
  assert(!server_get_unix_fd(current_handle,1,&fd,&need,NULL,NULL));
  assert(need==(i>=PW_FILE_FD_CACHE_LIMIT));
  assert(pw_cached_file_fds==(i<64?i+1:64));
  assert(fcntl(fd,F_GETFD)>=0);if(need)assert(!close(fd));
  assert(fcntl(server_fds[i],F_GETFD)>=0);
 }
 // Borrowed descriptors stay alive even as concurrent cache hits run.
 pthread_t a,b;assert(!pthread_create(&a,NULL,reuse,(void*)4));assert(!pthread_create(&b,NULL,reuse,(void*)8));
 assert(!pthread_join(a,NULL));assert(!pthread_join(b,NULL));
 // Free a normal cache slot; a later handle may use that slot again.
 int fd=remove_fd_from_cache(4);assert(fd>=0 && !close(fd));assert(pw_cached_file_fds==63);
 current_handle=161*4;server_fds[160]=open("/dev/null",O_RDONLY);assert(server_fds[160]>=0);
 int need;assert(!server_get_unix_fd(current_handle,1,&fd,&need,NULL,NULL));assert(!need && pw_cached_file_fds==64);
 // Other descriptor types retain normal caching even with a full file budget.
 current_handle=162*4;server_fds[161]=open("/dev/null",O_RDONLY);assert(server_fds[161]>=0);mock_reply.type=FD_TYPE_SOCKET;
 assert(!server_get_unix_fd(current_handle,1,&fd,&need,NULL,NULL));assert(!need && pw_cached_file_fds==64);
 reset();mock_reply.type=FD_TYPE_DIR;
 server_fds[0]=open("/dev/null",O_RDONLY);current_handle=4;
 assert(!server_get_unix_fd(4,1,&fd,&need,NULL,NULL));assert(pw_cached_file_fds==1);reset();
 // Transient server resource errors must be retried, never cached as permanent.
 for(int error=0;error<3;error++){
  server_status=(int[]){STATUS_TOO_MANY_OPENED_FILES,STATUS_NO_MEMORY,STATUS_INSUFFICIENT_RESOURCES}[error];
  assert(server_get_unix_fd(4,1,&fd,&need,NULL,NULL)==server_status);
  int type;assert(get_cached_fd(4,&fd,(void*)&type,NULL,NULL)==STATUS_INVALID_HANDLE);
 }
 server_status=0;server_fds[0]=open("/dev/null",O_RDONLY);current_handle=4;
 receive_fail=1;assert(server_get_unix_fd(4,1,&fd,&need,NULL,NULL)==STATUS_TOO_MANY_OPENED_FILES);
 receive_fail=0;assert(!server_get_unix_fd(4,1,&fd,&need,NULL,NULL));reset();
 // Repeated budget use/release must not retain entries or wrap the counter.
 for(int cycle=0;cycle<20;cycle++){
  for(unsigned i=0;i<100;i++){
   server_fds[i]=open("/dev/null",O_RDONLY);current_handle=(i+1)*4;
   assert(!server_get_unix_fd(current_handle,1,&fd,&need,NULL,NULL));if(need)assert(!close(fd));
  }
  reset();
 }
 assert(!setrlimit(RLIMIT_NOFILE,&old));
 puts("PASS: prepared Wine FD budget, real EMFILE reproduction, 160 files under a 256-fd limit, concurrent borrowed-fd reuse, retries and 20 lifecycle cycles");
}
'''
with tempfile.TemporaryDirectory() as tmp:
    path = pathlib.Path(tmp)
    (path/'check.c').write_text(code)
    subprocess.run(['cc', '-std=gnu11', '-g', '-O1', '-fsanitize=address,undefined', '-no-pie',
                    '-pthread', str(path/'check.c'), '-o', str(path/'check')], check=True)
    subprocess.run([str(path/'check')], check=True)
