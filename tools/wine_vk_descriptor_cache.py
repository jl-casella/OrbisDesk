#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Checked transformations for synchronous PE descriptor memoization (04.51)."""

def patch(text, replacements):
    for old, new in replacements:
        if text.count(old) != 1:
            raise ValueError('Unexpected descriptor-cache context: ' + old[:100])
        text = text.replace(old, new)
    return text

def patch_pe(text):
    return patch(text, [
        ('#include "pw_vk_template_cache.h"', '#include "pw_vk_template_cache.h"\n#include "pw_vk_descriptor_cache.h"'),
        ('struct producer {', 'struct producer {\n struct pw_dc_cache descriptors;UINT64 descriptor_hit_sequence;'),
        ('static LONG sticky_disabled;', '''static LONG sticky_disabled;
static BOOL descriptor_requested;
static _Atomic int descriptor_capable;
static LONG descriptor_bad;
static DECLSPEC_ALIGN(8) UINT64 descriptor_epoch=1;
static DECLSPEC_ALIGN(8) UINT64 descriptor_requests,descriptor_hits,descriptor_misses,descriptor_bypass;
static DECLSPEC_ALIGN(8) UINT64 descriptor_audits,descriptor_rejected,descriptor_invalidations,descriptor_types[12];
static void descriptor_report(UINT64 ordinal);'''),
        (' char env[8];(void)o;(void)p;(void)ctx;', ''' char env[8];(void)o;(void)p;(void)ctx;
 descriptor_requested=!(GetEnvironmentVariableA("PW_VK_DESCRIPTOR_CACHE",env,sizeof(env))==1&&env[0]=='0');'''),
        ('static NTSTATUS flush_call(unsigned int code,void *args)',
         'static NTSTATUS flush_call_query(unsigned int code,void *args,const struct pw_dc_query *query)'),
        (' if(!bytes&&!async_backend){', ' if(!bytes&&!async_backend&&!query){'),
        (' p.version=async_backend?PW_VK_BATCH_ASYNC_VERSION:PW_VK_BATCH_VERSION;p.batch=(UINT_PTR)scratch;p.bytes=bytes;p.code=code;p.args=(UINT_PTR)args;p.status=STATUS_SUCCESS;',
         ' p.version=query?PW_DC_BATCH_VERSION:(async_backend?PW_VK_BATCH_ASYNC_VERSION:PW_VK_BATCH_VERSION);p.batch=(UINT_PTR)scratch;p.bytes=bytes;p.code=code;p.args=(UINT_PTR)(query?(const void *)query:args);p.status=STATUS_SUCCESS;'),
        ('/* Manual loader wrappers unlink PE lists immediately,', '''static NTSTATUS flush_call(unsigned int code,void *args){return flush_call_query(code,args,NULL);}
/* Manual loader wrappers unlink PE lists immediately,'''),
        ('NTSTATUS pw_vk_batch_call(unsigned int code,void *args)\n{', 'static NTSTATUS pw_vk_batch_call_core(unsigned int code,void *args)\n{'),
        (''' InitOnceExecuteOnce(&once,initialize,NULL,NULL);
 /* Init and availability calls precede capability negotiation; old Unix never
  * receives the new table index. Disabled64 builds retain original macro. */
 if(!enabled||InterlockedCompareExchange(&sticky_disabled,0,0)){status=raw_call(code,args);snapshot(code,args);return status;}
 mapping_before(code,args);''', ' mapping_before(code,args);'),
        ('   else{cap.name=PW_VK_BATCH_NAME;negotiated=raw_call(unix_is_available_instance_function,&cap)==PW_VK_BATCH_CAPABILITY;}', '''   else{cap.name=PW_VK_BATCH_NAME;negotiated=raw_call(unix_is_available_instance_function,&cap)==PW_VK_BATCH_CAPABILITY;}
   if(negotiated&&!async_backend){cap.name=PW_DC_CAP_NAME;descriptor_capable=raw_call(unix_is_available_instance_function,&cap)==PW_DC_CAP;
    if(descriptor_requested&&!descriptor_capable)ERR("PW_DESCRIPTOR_CACHE configured requested=%u supported=%u (OrbisDesk 04.51)\\n",descriptor_requested,(unsigned)descriptor_capable);}'''),
        ('  WINE_MESSAGE("PW_VK_FASTPATH version=1', '  descriptor_report(ordinal);\n  WINE_MESSAGE("PW_VK_FASTPATH version=1'),
        (' leave();return status;\n}\n#endif',
         ' leave();return status;\n}\n#include "pw_vk_descriptor_cache_pe.inc.c"\n#endif'),
    ])

def patch_unix(text):
    return patch(text, [
        ('#include "pw_vk_batch.h"', '#include "pw_vk_batch.h"\n#include "pw_vk_descriptor_cache.h"'),
        (' if((p->version!=PW_VK_BATCH_VERSION&&p->version!=PW_VK_BATCH_LEGACY_VERSION)', ''' struct pw_dc_query *query=NULL;
 if(p->version==PW_DC_BATCH_VERSION){
  if(p->code!=unix_vkGetDescriptorEXT||!p->args)return STATUS_INVALID_PARAMETER;
  query=UlongToPtr(p->args);
  if(query->version!=1||!query->args_a||!query->args_b||!query->bytes||query->bytes>PW_DC_MAX_BYTES)return STATUS_INVALID_PARAMETER;
 }
 if((!query&&p->version!=PW_VK_BATCH_VERSION&&p->version!=PW_VK_BATCH_LEGACY_VERSION)'''),
        (' ctx.version=p->version;', ' ctx.version=query?PW_VK_BATCH_VERSION:p->version;'),
        (' if(p->code!=unix_count){\n  p->status=pw_vk_batch_dispatch(p->code,UlongToPtr(p->args));\n }', ''' if(query){
  p->status=pw_vk_batch_dispatch(p->code,UlongToPtr(query->args_a));
  if(!p->status)p->status=pw_vk_batch_dispatch(p->code,UlongToPtr(query->args_b));
 }else if(p->code!=unix_count){
  p->status=pw_vk_batch_dispatch(p->code,UlongToPtr(p->args));
 }'''),
    ])

def patch_vulkan(text):
    return patch(text, [
        ('static NTSTATUS is_available_instance_function(VkInstance handle, const char *name)',
         '#include "pw_vk_descriptor_cache.h"\nstatic NTSTATUS is_available_instance_function(VkInstance handle, const char *name)'),
        ('    if (!strcmp(name, PW_VK_BATCH_NAME)) return PW_VK_BATCH_CAPABILITY;', '''#ifdef __ORBIS__
    if (!strcmp(name, PW_DC_CAP_NAME)) return PW_DC_CAP;
#endif
    if (!strcmp(name, PW_VK_BATCH_NAME)) return PW_VK_BATCH_CAPABILITY;'''),
    ])
