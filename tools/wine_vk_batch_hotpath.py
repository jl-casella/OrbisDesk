#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Context-checked PE batch housekeeping optimizations; no wire/dispatch changes."""


def patch_batch_hotpath(text):
    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise ValueError('Unexpected Vulkan batch hotpath context: ' + old[:85])
        text = text.replace(old, new)

    replace('static LONG sticky_disabled;', '''static LONG sticky_disabled;
/* OrbisDesk 04.50: retire publication precedes p->retired; a zero read can
 * postpone reclamation until the next drain but never free an active node. */
static LONG retired_pending;
static UINT64 empty_collect_skips,reclaim_skips,template_skips;''')
    replace('TlsSetValue(tls,NULL);InterlockedExchange(&p->retired,1);',
            'TlsSetValue(tls,NULL);InterlockedIncrement(&retired_pending);InterlockedExchange(&p->retired,1);')
    replace('''static void reclaim(void)
{
 struct producer **link,*p;
 EnterCriticalSection(&registry_gate);''', '''static void reclaim(void)
{
 struct producer **link,*p;
 if(!InterlockedCompareExchange(&retired_pending,0,0)){reclaim_skips++;return;}
 EnterCriticalSection(&registry_gate);''')
    replace('''   *link=p->next;heap_free(p);''',
            '''   *link=p->next;InterlockedDecrement(&retired_pending);heap_free(p);''')
    replace(''' uint64_t marker=pw_vk_spsc_marker(&stream_sequence);size_t n=producers(list),i;
 unsigned spins=0;DWORD start=0;BOOL reported=FALSE;
 *bytes=*records=0;''', ''' uint64_t marker=pw_vk_spsc_marker(&stream_sequence);size_t n,i;
 unsigned spins=0;DWORD start=0;BOOL reported=FALSE;
 *bytes=*records=0;
 /* Preserve the exact accepted-prefix snapshot. Newer tickets still belong
  * to a later drain; reserved but unpublished tickets still take the slow path. */
 if(next_replay>marker){enqueued_total=marker;empty_collect_skips++;return;}
 n=producers(list);''')
    replace('''static void template_created(unsigned code,void *args)
{
 EnterCriticalSection''', '''static void template_created(unsigned code,void *args)
{
 if(code!=unix_vkCreateDescriptorUpdateTemplate&&code!=unix_vkCreateDescriptorUpdateTemplateKHR){template_skips++;return;}
 EnterCriticalSection''')
    replace('''  WINE_MESSAGE("PW_VK_BATCH version=1''',
            '''  if(ordinal==1||!(ordinal%300)) {
  WINE_MESSAGE("PW_VK_FASTPATH version=1 present=%llu empty_collect_skips=%llu reclaim_skips=%llu template_skips=%llu retired_pending=%ld\\n",ordinal,empty_collect_skips,reclaim_skips,template_skips,InterlockedCompareExchange(&retired_pending,0,0));
  WINE_MESSAGE("PW_VK_BATCH version=1''')
    replace('''  fallback_snapshot(ordinal);
 }
}''', '''  }
  fallback_snapshot(ordinal);
 }
}''')
    return text


def patch_present_logging(text):
    old=''' copy=queues[i].stats;LeaveCriticalSection(&gate);
 /* A failed Unix call'''
    if text.count(old) != 1:
        raise ValueError('Unexpected Vulkan present logging context')
    return text.replace(old, ''' copy=queues[i].stats;LeaveCriticalSection(&gate);
 /* OrbisDesk 04.50: accumulate every present, log at most one normal report
  * per 300 successful intervals, with the first sample retained. */
 if(copy.intervals && copy.intervals%300)return;
 /* A failed Unix call''')
