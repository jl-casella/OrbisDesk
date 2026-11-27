#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual cache/PE adapter and transformed native dispatcher with modeled driver.

Host sanitizers validate CPU copies, invalidation and framing, not PS4 gameplay.
"""
import pathlib, re, subprocess, sys, tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from wine_vk_descriptor_cache import patch_pe, patch_unix, patch_vulkan
from wine_vk_batch_hotpath import patch_batch_hotpath
src=ROOT/'upstream/prospero-win/wine/ps5/vulkan'
for name,transform in [('pw_vk_batch_pe.c',lambda s:patch_pe(patch_batch_hotpath(s))),
                       ('pw_vk_batch_unix.c',patch_unix)]:
    text=transform((src/name).read_text())
    try:transform(text)
    except ValueError:pass
    else:raise AssertionError('duplicate transformation accepted: '+name)

adapter=(ROOT/'platform/ps4/pw_vk_descriptor_cache_pe.inc.c').read_text()
calls=sorted(set(re.findall(r'\bunix_\w+',adapter)))
P=r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdatomic.h>
#include "pw_vk_descriptor_cache.h"
typedef uint64_t UINT64;typedef int64_t LONG64;typedef uintptr_t UINT_PTR;
typedef int32_t LONG,NTSTATUS;typedef int BOOL;
#define DECLSPEC_ALIGN(x) __attribute__((aligned(x)))
#define STATUS_SUCCESS 0
#define InterlockedCompareExchange64(p,v,o) __sync_val_compare_and_swap(p,o,v)
#define InterlockedCompareExchange(p,v,o) __sync_val_compare_and_swap(p,o,v)
#define InterlockedIncrement64(p) __sync_add_and_fetch(p,1)
#define InterlockedExchange(p,v) __sync_lock_test_and_set(p,v)
#define WINE_MESSAGE(...) ((void)0)
#define ERR(...) ((void)0)
#define InitOnceExecuteOnce(...) ((void)0)
enum {VK_DESCRIPTOR_TYPE_SAMPLER=0,VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER,
 VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE,VK_DESCRIPTOR_TYPE_STORAGE_IMAGE,VK_DESCRIPTOR_TYPE_UNIFORM_TEXEL_BUFFER,
 VK_DESCRIPTOR_TYPE_STORAGE_TEXEL_BUFFER,VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER,VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,
 VK_DESCRIPTOR_TYPE_INPUT_ATTACHMENT=10};
enum {VK_STRUCTURE_TYPE_DESCRIPTOR_GET_INFO_EXT=42,VK_STRUCTURE_TYPE_DESCRIPTOR_ADDRESS_INFO_EXT=43};
typedef uint64_t VkSampler;
typedef struct {uint64_t sampler,imageView;uint32_t imageLayout;} VkDescriptorImageInfo;
typedef struct {uint32_t sType;void *pNext;uint64_t address,range;uint32_t format;} VkDescriptorAddressInfoEXT;
typedef union {const VkSampler *pSampler;const VkDescriptorImageInfo *pCombinedImageSampler,*pSampledImage,*pStorageImage,*pInputAttachmentImage;
 const VkDescriptorAddressInfoEXT *pUniformBuffer,*pStorageBuffer,*pUniformTexelBuffer,*pStorageTexelBuffer;} VkDescriptorDataEXT;
typedef struct {uint32_t sType;void *pNext;unsigned type;VkDescriptorDataEXT data;} VkDescriptorGetInfoEXT;
struct vkGetDescriptorEXT_params {void *device;const VkDescriptorGetInfoEXT *pDescriptorInfo;size_t dataSize;void *pDescriptor;};
static BOOL enabled=1,stats_enabled=1,fallback_profile=1,descriptor_requested=1;
static _Atomic int descriptor_capable=1;
static LONG descriptor_bad,sticky_disabled;
static UINT64 descriptor_epoch=1,descriptor_requests,descriptor_hits,descriptor_misses,descriptor_bypass;
static UINT64 descriptor_audits,descriptor_rejected,descriptor_invalidations,descriptor_types[12];
static UINT64 fallback_total,fallback_counts[256];
struct producer {struct pw_dc_cache descriptors;UINT64 descriptor_hit_sequence;};
static struct producer state;
static int no_producer,queries,cores,locked,change_epoch,fail_query,nondeterministic,driver_generation;
static void *pointers[16];static unsigned npointers;
static unsigned ptr(void *p){assert(npointers<15);pointers[++npointers]=p;return npointers;}
#define PW_DC_PTR(p) ptr(p)
static struct producer *producer(void){return no_producer?NULL:&state;}
static void enter(void){assert(!locked);locked=1;}
static void leave(void){assert(locked);locked=0;}
static void snapshot(unsigned c,void *a){(void)c;(void)a;}
static void driver(struct vkGetDescriptorEXT_params *q){
 unsigned char *p=q->pDescriptor;queries++;
 /* Realistic partial output, including both canary values as written bytes. */
 for(unsigned i=0;i<q->dataSize;i++)if(i%4!=3)p[i]=(unsigned char)(i+driver_generation);
 if(q->dataSize>1){p[0]=0xa5;p[1]=0x5a;}
 if(nondeterministic&&q->dataSize>2)p[2]=(unsigned char)queries;
}
static NTSTATUS raw_call(unsigned c,void *a){cores++;if(c==unix_vkGetDescriptorEXT)driver(a);return 0;}
static NTSTATUS pw_vk_batch_call_core(unsigned c,void *a){return raw_call(c,a);}
static NTSTATUS flush_call_query(unsigned c,void *a,const struct pw_dc_query *q){
 (void)a;assert(locked&&c==unix_vkGetDescriptorEXT&&q->version==1);
 if(change_epoch){descriptor_epoch++;change_epoch=0;}
 if(fail_query){fail_query=0;return -1;}
 driver(pointers[q->args_a]);driver(pointers[q->args_b]);npointers=0;return 0;
}
'''
C=r'''
static void reset(void){memset(&state,0,sizeof(state));descriptor_epoch++;descriptor_bad=0;
 queries=cores=locked=no_producer=change_epoch=fail_query=nondeterministic=driver_generation=0;npointers=0;}
int main(void){
 struct pw_dc_key k={{1}},k2={{2}};struct pw_dc_value v,w;unsigned char a[128],b[128],out[128];
 memset(a,0xa5,sizeof(a));memset(b,0x5a,sizeof(b));a[0]=b[0]=0xa5;a[1]=b[1]=0x5a;
 assert(pw_dc_learn(&v,a,b,128)&&!v.whole);memset(out,0x99,128);pw_dc_copy(out,&v);
 assert(out[0]==0xa5&&out[1]==0x5a&&out[2]==0x99);w=v;w.data[2]++;assert(pw_dc_equal(&v,&w));
 w.written[2]=1;assert(!pw_dc_equal(&v,&w));assert(!pw_dc_learn(&v,a,b,129));
 b[2]=0x66;assert(!pw_dc_learn(&v,a,b,128));
 struct pw_dc_cache *cache=calloc(1,sizeof(*cache));assert(cache);
 v=w;pw_dc_store(cache,&k,2,&v);assert(pw_dc_find(cache,&k,2)&&!pw_dc_find(cache,&k,3));
 assert(!pw_dc_find(cache,&k,0));pw_dc_store(cache,&k,0,&v);assert(!pw_dc_find(cache,&k,0));
 for(uint64_t n=2;n<100000;n++){k2.words[0]=n;if(pw_dc_hash(&k)==pw_dc_hash(&k2))break;}
 assert(k2.words[0]<100000);pw_dc_store(cache,&k2,2,&v);assert(pw_dc_find(cache,&k,2)&&pw_dc_find(cache,&k2,2));free(cache);
 VkSampler sampler=71;VkDescriptorGetInfoEXT info={42,NULL,0,{.pSampler=&sampler}};
 struct vkGetDescriptorEXT_params q={(void *)0x100,&info,32,out};
 reset();memset(out,0x33,32);assert(!pw_vk_batch_call(unix_vkGetDescriptorEXT,&q)&&queries==2);
 assert(out[0]==0xa5&&out[1]==0x5a&&out[3]==0x33&&out[2]==2);
 state.descriptor_hit_sequence=16;memset(out,0x44,32);
 assert(!pw_vk_batch_call(unix_vkGetDescriptorEXT,&q)&&queries==2&&out[3]==0x44&&out[2]==2);
 /* Every independent key component and resource lifetime must prevent stale hits. */
 sampler++;pw_vk_batch_call(unix_vkGetDescriptorEXT,&q);assert(queries==4);
 q.device=(void *)0x200;pw_vk_batch_call(unix_vkGetDescriptorEXT,&q);assert(queries==6);
 q.dataSize=16;pw_vk_batch_call(unix_vkGetDescriptorEXT,&q);assert(queries==8);
 for(unsigned i=0;i<sizeof(mutations)/sizeof(*mutations);i++){
  driver_generation++;int before=queries;UINT64 epoch=descriptor_epoch;
  pw_vk_batch_call(mutations[i],NULL);assert(descriptor_epoch==epoch+1);
  pw_vk_batch_call(unix_vkGetDescriptorEXT,&q);assert(queries==before+2&&out[2]==(unsigned char)(driver_generation+2));
 }
 reset();change_epoch=1;pw_vk_batch_call(unix_vkGetDescriptorEXT,&q);pw_vk_batch_call(unix_vkGetDescriptorEXT,&q);assert(queries==4);
 reset();pw_vk_batch_call(unix_vkGetDescriptorEXT,&q);driver_generation=9;
 pw_vk_batch_call(unix_vkGetDescriptorEXT,&q);assert(descriptor_bad&&out[2]==11);
 int before=cores;pw_vk_batch_call(unix_vkGetDescriptorEXT,&q);assert(cores==before+1);
 reset();fail_query=1;pw_vk_batch_call(unix_vkGetDescriptorEXT,&q);assert(descriptor_bad&&cores==1&&queries==1);
 reset();nondeterministic=1;pw_vk_batch_call(unix_vkGetDescriptorEXT,&q);assert(descriptor_bad&&cores==1&&queries==3);
 reset();info.pNext=&info;pw_vk_batch_call(unix_vkGetDescriptorEXT,&q);assert(cores==1);info.pNext=NULL;
 info.sType=0;pw_vk_batch_call(unix_vkGetDescriptorEXT,&q);assert(cores==2);info.sType=42;
 q.dataSize=129;q.pDescriptor=out; /* Unsupported size still routes to the real driver. Use larger output. */
 unsigned char large[256];q.pDescriptor=large;pw_vk_batch_call(unix_vkGetDescriptorEXT,&q);assert(cores==3);
 q.dataSize=16;q.pDescriptor=out;info.type=99;pw_vk_batch_call(unix_vkGetDescriptorEXT,&q);assert(cores==4);info.type=0;
 no_producer=1;pw_vk_batch_call(unix_vkGetDescriptorEXT,&q);assert(cores==5);no_producer=0;
 struct pw_dc_key key; q.pDescriptor=&sampler;assert(!descriptor_key(&q,&key));q.pDescriptor=out;
 VkDescriptorImageInfo image={12,13,14};info.type=1;info.data.pCombinedImageSampler=&image;
 assert(descriptor_key(&q,&k)&&k.words[3]==13&&k.words[4]==12&&k.words[5]==14);
 image.sampler++;assert(descriptor_key(&q,&k2)&&memcmp(&k,&k2,sizeof(k)));
 VkDescriptorAddressInfoEXT address={43,NULL,100,200,300};info.type=6;info.data.pUniformBuffer=&address;
 assert(descriptor_key(&q,&k)&&k.words[3]==100&&k.words[4]==200&&k.words[5]==300);
 address.pNext=&address;assert(!descriptor_key(&q,&k));address.pNext=NULL;
 reset();descriptor_capable=0;pw_vk_batch_call(unix_vkGetDescriptorEXT,&q);assert(cores==1&&queries==1);descriptor_capable=1;
 descriptor_report(300);
 puts("PASS: synchronous cache, padding, keys, collisions, resource generations, audits, real fallback and legacy capability");
}
'''
mutations=re.findall(r'case (unix_\w+)',adapter.split('static int descriptor_mutates')[1].split('static void descriptor_report')[0])
code=P.replace('#include "pw_vk_descriptor_cache.h"','#include "pw_vk_descriptor_cache.h"\nenum {'+','.join(calls)+'};')
code+=adapter+'\nstatic unsigned mutations[]={'+','.join(mutations)+'};\n'+C

# Compile the actual transformed native entry, with framing and dispatch modeled.
native=patch_unix((src/'pw_vk_batch_unix.c').read_text())
native=native[native.index('NTSTATUS pw_vk_batch_unix(void *args)'):]
N=r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include "pw_vk_descriptor_cache.h"
typedef int NTSTATUS;
#define STATUS_SUCCESS 0
#define STATUS_INVALID_PARAMETER (-1)
#define STATUS_UNSUCCESSFUL (-2)
#define PW_VK_BATCH_VERSION 2
#define PW_VK_BATCH_LEGACY_VERSION 1
#define PW_VK_BATCH_SCRATCH 4096
#define PW_VK_STREAM_OK 0
enum {unix_vkGetDescriptorEXT=7,unix_pw_vk_batch=9,unix_count=10};
struct pw_vk_batch_params {uint32_t version,batch,bytes,code,args;NTSTATUS status;};
struct replay_context {uint64_t local[512];void *arena;size_t capacity;unsigned version;NTSTATUS failure;};
static void *ptrs[4];
#define UlongToPtr(p) ptrs[p]
static int preflight,replay,preflights,replays,dispatches,fail_preflight,fail_dispatch;
static int pw_vk_stream_replay(void *data,size_t bytes,int cb,struct replay_context *ctx,size_t *done){
 (void)data;(void)bytes;*done=0;assert(ctx->version==1||ctx->version==2);
 if(cb==preflight){preflights++;if(fail_preflight)return -1;}else{assert(cb==replay);replays++;}return 0;
}
static NTSTATUS pw_vk_batch_dispatch(unsigned c,void *p){assert(c==7);assert(p==ptrs[2]||p==ptrs[3]);dispatches++;return fail_dispatch?-7:0;}
'''
NC=r'''
int main(void){
 preflight=1;replay=2;int a,b;struct pw_dc_query q={1,2,3,32};ptrs[1]=&q;ptrs[2]=&a;ptrs[3]=&b;
 struct pw_vk_batch_params p={PW_DC_BATCH_VERSION,0,64,7,1,99};
 assert(!pw_vk_batch_unix(&p)&&p.status==0&&preflights==1&&replays==1&&dispatches==2);
 fail_dispatch=1;assert(!pw_vk_batch_unix(&p)&&p.status==-7&&dispatches==3);fail_dispatch=0;
 fail_preflight=1;assert(pw_vk_batch_unix(&p)==-1&&replays==2&&dispatches==3);fail_preflight=0;
 int before=preflights;q.bytes=129;assert(pw_vk_batch_unix(&p)==-1&&preflights==before);q.bytes=32;
 q.version=2;assert(pw_vk_batch_unix(&p)==-1&&preflights==before);q.version=1;
 q.args_a=0;assert(pw_vk_batch_unix(&p)==-1&&preflights==before);q.args_a=2;
 p.code=8;assert(pw_vk_batch_unix(&p)==-1&&preflights==before);p.code=7;
 p.bytes=4097;assert(pw_vk_batch_unix(&p)==-1&&preflights==before);p.bytes=64;
 for(unsigned v=1;v<=2;v++){p.version=v;p.args=2;assert(!pw_vk_batch_unix(&p)&&p.status==0);}
 assert(dispatches==5);p.code=unix_count;assert(!pw_vk_batch_unix(&p)&&dispatches==5);
 puts("PASS: private query negotiation, validation before replay, prefix exactly once, real errors, standard v1/v2 dispatch");
}
'''
with tempfile.TemporaryDirectory() as tmp:
    base=pathlib.Path(tmp)
    for name,contents in [('pe',code),('unix',N+native+NC)]:
        path=base/(name+'.c');path.write_text(contents)
        subprocess.run(['cc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Wno-unused-parameter',
                        '-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie',
                        '-I'+str(ROOT/'platform/ps4'),str(path),'-o',str(base/name)],check=True)
        subprocess.run([str(base/name)],check=True,timeout=15)
