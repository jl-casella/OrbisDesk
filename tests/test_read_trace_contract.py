#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run original and instrumented pinned Wine read bodies against identical I/O doubles."""
import pathlib,subprocess,sys,tempfile
r=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(r/'tools'))
from wine_read_trace import patch
source=(r/'build/wow64-world-ps4/file.c').read_text()
def body(text):
 start=text.index('NTSTATUS WINAPI NtReadFile(')
 return text[start:text.index('\n/******************************************************************************',start)]
original=body(source).replace('NtReadFile(', 'original_read(',1)
changed=body(patch(source)).replace('NtReadFile(', 'traced_read(',1)
try:patch(source.replace('            total = result;','            total = result + 0;'))
except ValueError:pass
else:raise AssertionError('Changed source context must fail closed')
code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <poll.h>
#include "pw_optrace.h"
#define WINAPI
#define TRACE(...) ((void)0)
#define TRUE 1
#define FALSE 0
#define FILE_READ_DATA 1
#define FILE_SYNCHRONOUS_IO_ALERT 16
#define FILE_SYNCHRONOUS_IO_NONALERT 32
#define FILE_USE_FILE_POINTER_POSITION -2
#define STATUS_SUCCESS 0u
#define STATUS_PENDING 0x103u
#define STATUS_ACCESS_VIOLATION 0xc0000005u
#define STATUS_BAD_DEVICE_TYPE 0xc00000cbu
#define STATUS_INVALID_PARAMETER 0xc000000du
#define STATUS_END_OF_FILE 0xc0000011u
#define STATUS_PIPE_BROKEN 0xc000014bu
#define STATUS_TIMEOUT 0x102u
typedef int32_t NTSTATUS;typedef void *HANDLE;typedef unsigned ULONG,UINT;typedef int BOOL;
typedef uintptr_t ULONG_PTR,client_ptr_t;typedef struct {long long QuadPart;} LARGE_INTEGER;
typedef struct {unsigned status,bytes;} IO_STATUS_BLOCK;
typedef void (*PIO_APC_ROUTINE)(void);typedef void (*PNTAPCFUNC)(void);
enum server_fd_type {FD_TYPE_FILE,FD_TYPE_SERIAL,FD_TYPE_DEVICE,FD_TYPE_SOCKET,FD_TYPE_CHAR};
struct io_timeouts {int interval;};
struct result {unsigned status,events,resets,apcs,completions,closes,seeks,native,delegates;IO_STATUS_BLOCK io;char data[8];int error;};
static struct result out;static int mode,ends;static struct pw_readstamp ended;
static client_ptr_t iosb_client_ptr(IO_STATUS_BLOCK *io){return (uintptr_t)io;}
static int server_get_unix_fd(HANDLE h,unsigned a,int *fd,int *close_fd,enum server_fd_type *type,unsigned *options){
 (void)h;(void)a;*fd=123;*close_fd=1;*type=mode==8?FD_TYPE_SOCKET:FD_TYPE_FILE;*options=mode==9?FILE_SYNCHRONOUS_IO_NONALERT:0;
 return mode==5?(int)0xc0000008u:mode==7?(int)STATUS_BAD_DEVICE_TYPE:0;
}
static int virtual_check_buffer_for_write(void *p,unsigned n){(void)p;(void)n;return mode!=4;}
static int native_read(int fd,void *buf,unsigned len,long long offset){
 (void)fd;(void)offset;out.native++;if(mode==3){errno=EIO;return -1;}
 if(mode==2)return 0;unsigned n=len<3?len:3;memset(buf,'x',n);return (int)n;
}
#define virtual_locked_pread native_read
#define virtual_locked_read(fd,buf,len) native_read(fd,buf,len,0)
static unsigned delegated(void){out.delegates++;return 0x103;}
#define server_read_file(...) delegated()
#define sock_read(...) delegated()
#define register_async_file_read(...) delegated()
static int get_io_timeouts(HANDLE h,enum server_fd_type t,unsigned n,int async,struct io_timeouts *v){(void)h;(void)t;(void)n;(void)async;v->interval=0;return 0;}
static int get_io_avail_mode(HANDLE h,enum server_fd_type t,BOOL *v){(void)h;(void)t;*v=1;return 0;}
static int get_next_io_timeout(struct io_timeouts *t,unsigned n){(void)t;(void)n;return 0;}
static unsigned errno_to_status(int e){(void)e;return 0xc0000185u;}
static void set_sync_iosb(IO_STATUS_BLOCK *io,unsigned status,unsigned n,unsigned options){(void)options;io->status=status;io->bytes=n;}
static void NtSetEvent(HANDLE h,void *p){(void)h;(void)p;out.events++;}
static void NtResetEvent(HANDLE h,void *p){(void)h;(void)p;out.resets++;}
static void NtQueueApcThread(HANDLE h,PNTAPCFUNC cb,ULONG_PTR a,client_ptr_t io,int z){(void)h;(void)cb;(void)a;(void)io;(void)z;out.apcs++;}
#define GetCurrentThread() ((HANDLE)1)
static void add_completion(HANDLE h,ULONG_PTR v,unsigned status,unsigned bytes,BOOL async){(void)h;(void)v;(void)status;(void)bytes;(void)async;out.completions++;}
static int fake_close(int fd){(void)fd;out.closes++;return 0;}
static int fake_seek(int fd,long long offset,int whence){(void)fd;(void)offset;(void)whence;out.seeks++;return 0;}
#define close fake_close
#define lseek fake_seek
struct pw_readstamp pw_readtrace_begin(void){return (struct pw_readstamp){.active=1};}
void pw_readtrace_stage(struct pw_readstamp *s,unsigned stage){s->stage=stage;}
int32_t pw_readtrace_end(struct pw_readstamp *s,int32_t status,uint64_t n){assert(s->active&&n==8);ended=*s;s->active=0;ends++;return status;}
'''+original+changed+r'''
static void callback(void){}
typedef NTSTATUS (*reader)(HANDLE,HANDLE,PIO_APC_ROUTINE,void *,IO_STATUS_BLOCK *,void *,ULONG,LARGE_INTEGER *,ULONG *);
static struct result run(reader fn,int which){
 memset(&out,0,sizeof(out));mode=which;errno=73;LARGE_INTEGER offset={which==10?-1:4};
 out.io.status=0xdead;out.io.bytes=999;
 out.status=fn((HANDLE)1,(HANDLE)2,which==11?callback:NULL,(void *)3,which==6?NULL:&out.io,out.data,8,&offset,NULL);
 out.error=errno;return out;
}
int main(void){
 for(int i=0;i<12;i++){
  struct result a=run(original_read,i),b=run(traced_read,i);assert(!memcmp(&a,&b,sizeof(a)));
  assert(ends==i+1);
  if(i==0){assert(b.status==STATUS_PENDING&&b.io.bytes==3&&b.events==1&&b.completions==1);assert(ended.known&&ended.actual==3&&ended.event&&ended.completion);}
  if(i==2){assert(b.status==STATUS_PENDING&&b.io.status==STATUS_END_OF_FILE&&ended.known&&!ended.actual);}
  if(i==7||i==8)assert(!ended.known); /* don't interpret untrusted/deferred IOSBs */
  if(i==9)assert(!b.status&&b.seeks==1&&!b.completions);
  if(i==11)assert(b.apcs==1&&!b.completions);
 }
 puts("PASS: original versus transformed pinned NtReadFile: async Pending, EOF, errors, IOSB, bytes, event, APC, completion, delegation and sync file position");
}
'''
with tempfile.TemporaryDirectory() as t:
 p=pathlib.Path(t);(p/'check.c').write_text(code)
 subprocess.run(['cc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-variable','-Wno-unused-parameter','-Wno-misleading-indentation','-fsanitize=address,undefined','-no-pie','-I'+str(r/'platform/ps4'),str(p/'check.c'),'-o',str(p/'check')],check=True)
 subprocess.run([str(p/'check')],check=True)
