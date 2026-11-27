#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise actual allocator wrappers with injected failures; verify errno and lock release."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
code = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
int pw_native_log_fd=7;
uintptr_t pw_native_raw_syscall=1;
static int fail,records;
static char captured[512];
static void *success=(void *)0x1234;
void *scePthreadSelf(void) {return (void *)1;}
int sceKernelUsleep(unsigned usec) {(void)usec;assert(0);return 0;}
void *__real_malloc(size_t size) {(void)size;if(fail){errno=ENOMEM;return NULL;}return success;}
void *__real_calloc(size_t n,size_t size) {(void)n;return __real_malloc(size);}
void *__real_realloc(void *p,size_t size) {(void)p;return __real_malloc(size);}
void *__real_memalign(size_t a,size_t size) {(void)a;return __real_malloc(size);}
void *__real___memalign(size_t a,size_t size) {return __real_memalign(a,size);}
void *__real_aligned_alloc(size_t a,size_t size) {return __real_memalign(a,size);}
void __real_free(void *p) {(void)p;}
int __real_posix_memalign(void **p,size_t a,size_t size) {(void)a;(void)size;if(fail)return ENOMEM;*p=success;return 0;}
/* the direct-memory fallback's imports (tests/test_native_heap_direct_host.py exercises it) */
void *__real___mmap(void *a,size_t l,int p,int f,int fd,long o) {(void)a;(void)l;(void)p;(void)f;(void)fd;(void)o;return (void *)-1;}
int __real___munmap(void *a,size_t l) {(void)a;(void)l;return 0;}
int sceKernelAllocateDirectMemory(long s,long e,size_t l,size_t a,int t,long *o) {(void)s;(void)e;(void)l;(void)a;(void)t;(void)o;return -1;}
int sceKernelMapDirectMemory(void **a,size_t l,int p,int f,long o,size_t al) {(void)a;(void)l;(void)p;(void)f;(void)o;(void)al;return -1;}
int sceKernelReleaseDirectMemory(long o,size_t l) {(void)o;(void)l;return 0;}
size_t sceKernelGetDirectMemorySize(void) {return 0;}
''' + (root/'native/native_heap.c').read_text() + r'''
long pw_native_syscall_at(uintptr_t entry,long call,long fd,long buffer,long size) {
    assert(entry==1&&call==4&&fd==7&&size>0&&size<256);
    assert(!owner&&!depth); /* diagnostics must run after unlocking */
    memcpy(captured,(void *)buffer,(size_t)size);captured[size]=0;++records;
    errno=EIO; /* logger must not leak its errno into allocator callers */
    return size;
}
static void regions(void) {
    /* a successful allocation writes nothing (the 04.87 per-GiB region lines were an investigation) */
    success=(void *)0x880dcb000;records=0;
    errno=EACCES;assert(__wrap_malloc(64)==success&&errno==EACCES&&records==0);
    success=(void *)0x1234;records=0;
}
int main(void) {
    regions();
    errno=EACCES;assert(__wrap_malloc(64)==success&&errno==EACCES&&records==0);
    fail=1;assert(!__wrap_malloc(0)&&records==0);
    assert(!__wrap_realloc(success,0)&&records==0);
    assert(!__wrap_calloc(0,64)&&records==0);
    assert(!__wrap_malloc(4096)&&errno==ENOMEM&&records==1);
    assert(strstr(captured,"kind=0x0000000000000001")&&strstr(captured,"size=0x0000000000001000"));
    assert(!__wrap_calloc(SIZE_MAX,2)&&errno==ENOMEM&&records==2);
    assert(strstr(captured,"count=0xffffffffffffffff")&&strstr(captured,"size=0x0000000000000002"));
    assert(!__wrap_realloc(success,64)&&records==3);
    assert(!__wrap_memalign(16,64)&&records==4);
    assert(!__wrap___memalign(16,64)&&records==5);
    assert(!__wrap_aligned_alloc(16,64)&&records==6);
    void *ptr=success;errno=EBUSY;
    assert(__wrap_posix_memalign(&ptr,16,64)==ENOMEM&&errno==EBUSY&&ptr==success&&records==7);
    for(unsigned i=0;i<80;i++)assert(!__wrap_malloc(64));
    assert(records==16&&!owner&&!depth);
    fail=0;assert(__wrap_malloc(64)==success);__wrap_free(success);assert(!owner&&!depth);
    puts("PASS native heap failures: allocation families, request size, zero size, overflow, errno, unlock before logging, budget, heap regions");
}
'''
with tempfile.TemporaryDirectory() as temporary:
    path = Path(temporary)
    (path/'check.c').write_text(code)
    subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-O1', '-g',
                    '-fsanitize=address,undefined', '-no-pie', str(path/'check.c'),
                    '-o', str(path/'check')], check=True)
    subprocess.run([str(path/'check')], check=True, timeout=15)
