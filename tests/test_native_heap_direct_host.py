#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The native heap's direct-memory fallback (Alice 04.91 run-0243): musl's anonymous mmap refused by the empty
flexible pool (EINVAL) takes direct memory, zeroed; its munmap releases it; anything else passes through."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
code = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
int pw_native_log_fd=7;
uintptr_t pw_native_raw_syscall=1;
static int flexible_error=EINVAL,direct_fail,map_fail,lines,real_unmaps,allocated,released;
static size_t last_unmap;
static char captured[512];
void *scePthreadSelf(void) {return (void *)1;}
int sceKernelUsleep(unsigned usec) {(void)usec;assert(0);return 0;}
void *__real_malloc(size_t size) {(void)size;return NULL;}
void *__real_calloc(size_t n,size_t size) {(void)n;(void)size;return NULL;}
void *__real_realloc(void *p,size_t size) {(void)p;(void)size;return NULL;}
void *__real_memalign(size_t a,size_t size) {(void)a;(void)size;return NULL;}
void *__real___memalign(size_t a,size_t size) {(void)a;(void)size;return NULL;}
void *__real_aligned_alloc(size_t a,size_t size) {(void)a;(void)size;return NULL;}
void __real_free(void *p) {(void)p;}
int __real_posix_memalign(void **p,size_t a,size_t size) {(void)p;(void)a;(void)size;return ENOMEM;}
/* the flexible pool: empty, refusing with flexible_error */
void *__real___mmap(void *a,size_t l,int p,int f,int fd,long o) {
    (void)a;(void)l;(void)p;(void)f;(void)fd;(void)o;errno=flexible_error;return (void *)-1;
}
int __real___munmap(void *a,size_t l) {(void)a;last_unmap=l;++real_unmaps;return 0;}
/* direct memory: the offset is the host block, so map and release can check each other */
int sceKernelAllocateDirectMemory(long s,long e,size_t l,size_t a,int t,long *o) {
    assert(!s&&e==1L<<32&&l%0x4000==0&&a==0x4000&&!t);
    if(direct_fail)return (int)0x8002000c;
    void *block=aligned_alloc(0x4000,l);assert(block);memset(block,0xa5,l);  /* direct memory is not zeroed */
    *o=(long)(uintptr_t)block;++allocated;return 0;
}
int sceKernelMapDirectMemory(void **a,size_t l,int p,int f,long o,size_t al) {
    assert(!*a&&l%0x4000==0&&p==3&&!f&&al==0x4000);
    if(map_fail)return (int)0x80020016;
    *a=(void *)(uintptr_t)o;return 0;
}
int sceKernelReleaseDirectMemory(long o,size_t l) {(void)l;free((void *)(uintptr_t)o);++released;return 0;}
size_t sceKernelGetDirectMemorySize(void) {return (size_t)1<<32;}
''' + (root/'native/native_heap.c').read_text() + r'''
long pw_native_syscall_at(uintptr_t entry,long call,long fd,long buffer,long size) {
    assert(entry==1&&call==4&&fd==7&&size>0&&size<256);
    memcpy(captured,(void *)buffer,(size_t)size);captured[size]=0;++lines;
    errno=EIO;return size;
}
int main(void) {
    /* musl's large-chunk map (0x1002 = MAP_PRIVATE|MAP_ANON) refused with EINVAL: direct memory, zeroed */
    errno=0;unsigned char *p=__wrap___mmap(NULL,0x23380,3,0x1002,-1,0);
    assert(p!=(void *)-1&&errno==EINVAL&&allocated==1&&lines==1);
    for(size_t i=0;i<0x24000;i++)assert(!p[i]);
    assert(strstr(captured,"PWHEAP direct v=1 n=0x0000000000000001 size=0x0000000000024000 errno=0x0000000000000016"));
    assert(strstr(captured,"total=0x0000000000024000 blocks=0x0000000000000001"));
    /* ENOMEM is the same refusal */
    flexible_error=ENOMEM;void *q=__wrap___mmap(NULL,0x28000,3,0x1002,-1,0);
    assert(q!=(void *)-1&&allocated==2&&heap_direct_count==2&&heap_direct_bytes==0x4c000);
    /* munmap of a direct block: the whole block unmapped, its memory released; then pass-through */
    assert(!__wrap___munmap(p,0x23380)&&last_unmap==0x24000&&released==1&&heap_direct_count==1);
    assert(!__wrap___munmap(p,0x23380)&&last_unmap==0x23380&&released==1&&real_unmaps==2);
    assert(!__wrap___munmap(q,0x28000)&&released==2&&!heap_direct_count&&!heap_direct_bytes);
    /* not the heap's anonymous map, or another error: unchanged failure, nothing allocated */
    flexible_error=EINVAL;
    assert(__wrap___mmap((void *)0x10000,0x4000,3,0x1012,-1,0)==(void *)-1&&errno==EINVAL);  /* fixed address */
    assert(__wrap___mmap(NULL,0x4000,1,0x0002,5,0)==(void *)-1);                               /* file map */
    assert(__wrap___mmap(NULL,0x4000,3,0x0002,-1,0)==(void *)-1);                              /* not anonymous */
    assert(__wrap___mmap(NULL,0,3,0x1002,-1,0)==(void *)-1);                                   /* empty */
    assert(__wrap___mmap(NULL,SIZE_MAX-10,3,0x1002,-1,0)==(void *)-1);                         /* rounds over */
    flexible_error=EACCES;assert(__wrap___mmap(NULL,0x4000,3,0x1002,-1,0)==(void *)-1&&errno==EACCES);
    assert(allocated==2&&lines==2);
    /* direct memory refused, or its map: the original failure, nothing kept, logged with rc */
    flexible_error=EINVAL;direct_fail=1;
    assert(__wrap___mmap(NULL,0x4000,3,0x1002,-1,0)==(void *)-1&&errno==EINVAL&&!heap_direct_count&&lines==3);
    assert(strstr(captured,"rc=0x000000008002000c ptr=0x0000000000000000"));
    direct_fail=0;map_fail=1;
    assert(__wrap___mmap(NULL,0x4000,3,0x1002,-1,0)==(void *)-1&&errno==EINVAL&&released==3&&!heap_direct_count);
    map_fail=0;
    /* a full table: the original failure */
    heap_direct_count=HEAP_DIRECT_MAX;
    assert(__wrap___mmap(NULL,0x4000,3,0x1002,-1,0)==(void *)-1&&errno==EINVAL);
    heap_direct_count=0;
    /* 16 lines at most */
    for(unsigned i=0;i<40;i++){void *r=__wrap___mmap(NULL,0x4000,3,0x1002,-1,0);assert(r!=(void *)-1);__wrap___munmap(r,0x4000);}
    assert(lines==16&&!heap_direct_count&&!heap_direct_lock);
    puts("PASS native heap direct fallback: EINVAL and ENOMEM maps, zeroed, release on munmap, pass-through, direct failure, full table, log budget");
}
'''
with tempfile.TemporaryDirectory() as temporary:
    path = Path(temporary)
    (path/'check.c').write_text(code)
    subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-O1', '-g',
                    '-fsanitize=address,undefined', '-no-pie', str(path/'check.c'),
                    '-o', str(path/'check')], check=True)
    subprocess.run([str(path/'check')], check=True, timeout=15)
