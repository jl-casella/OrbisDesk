/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "pw_process_ps4.h"
#include <string.h>

static void w32(void *p, uint32_t v) { memcpy(p,&v,4); }
static int wide(uint8_t *mem, uint32_t base, unsigned *cursor, unsigned descriptor, const char *text)
{
    if (!text) return PW_ERR_PRECONDITION;
    size_t n=0;while(n<=1023 && text[n]) ++n;
    if (n>1023 || *cursor+2*(n+1)>PW_PE32_PAGE) return PW_ERR_LIMIT;
    for(size_t i=0;i<n;++i) if ((unsigned char)text[i]<32 || (unsigned char)text[i]>126) return PW_ERR_UNSUPPORTED;
    uint16_t length=(uint16_t)(2*n), maximum=(uint16_t)(2*(n+1));
    memcpy(mem+descriptor,&length,2);memcpy(mem+descriptor+2,&maximum,2);
    w32(mem+descriptor+4,base+*cursor);
    for(size_t i=0;i<n;++i) mem[*cursor+2*i]=(uint8_t)text[i];
    *cursor+=(unsigned)maximum;return PW_OK;
}
int pw_process_ps4_create(PwPs4Process *out,const PwVmBackend *vm,uint32_t address,
                         const PwPe32Module *modules,size_t count,const char *image,
                         const char *command,const char *directory)
{
    if(!out || !pw_vm_backend_valid(vm) || !vm->reserve_at || vm->page_bytes!=PW_PE32_PAGE ||
       !(vm->capabilities&PW_VM_CAP_EXACT_ADDRESS) || !modules || !count || count>PW_PE32_MAX_MODULES ||
       !address || (uint64_t)address+PW_PE32_PAGE>0x100000000ull) return PW_ERR_PRECONDITION;
    for(size_t i=0;i<count;++i) {
        if(!modules[i].image || !modules[i].image->region.handle || !modules[i].name ||
           (i==0?modules[i].image->info.is_dll:!modules[i].image->info.is_dll)) return PW_ERR_STATE;
        for(size_t j=0;j<i;++j) if(modules[i].image==modules[j].image) return PW_ERR_PRECONDITION;
    }
    PwPs4Process p={0};p.backend=*vm;
    int rc=vm->reserve_at(vm->context,address,PW_PE32_PAGE,PW_PE32_PAGE,&p.region);
    if(!rc) rc=vm->commit(vm->context,&p.region,0,PW_PE32_PAGE,PW_PROT_READ|PW_PROT_WRITE);
    if(!rc) {
        uint8_t *m=p.region.write_base;memset(m,0,PW_PE32_PAGE);
        p.peb=address;p.parameters=address+0x100;p.ldr=address+0x400;
        if(modules[0].image->base!=modules[0].image->info.preferred) m[3]=4;
        w32(m+8,modules[0].image->base);w32(m+0xc,p.ldr);w32(m+0x10,p.parameters);
        w32(m+0x104,0x100);w32(m+0x108,1); /* normalized parameters */
        w32(m+0x400,0x30);m[0x404]=1;
        unsigned cursor=0x1000;
        rc=wide(m,address,&cursor,0x124,directory);
        if(!rc) rc=wide(m,address,&cursor,0x138,image);
        if(!rc) rc=wide(m,address,&cursor,0x140,command);
        /* Empty environment still has two UTF-16 terminators. */
        if(!rc && cursor+4>PW_PE32_PAGE) rc=PW_ERR_LIMIT;
        if(!rc) {w32(m+0x148,address+cursor);cursor+=4;}
        for(size_t i=0;!rc && i<count;++i) {
            unsigned e=0x500+(unsigned)i*0x80;
            PwPe32Image *module=modules[i].image;
            w32(m+e+0x18,module->base);w32(m+e+0x1c,module->entry);w32(m+e+0x20,module->info.image_bytes);
            rc=wide(m,address,&cursor,e+0x24,i?modules[i].name:image);
            if(!rc) rc=wide(m,address,&cursor,e+0x2c,modules[i].name);
        }
        /* Three circular doubly linked lists; initialization excludes the EXE. */
        for(unsigned list=0;!rc && list<3;++list) {
            unsigned head=0x40c+list*8, first=list==2?1:0;
            unsigned prev=head;
            for(unsigned i=first;i<count;++i) {
                unsigned node=0x500+i*0x80+list*8;
                w32(m+prev,address+node);w32(m+node+4,address+prev);prev=node;
            }
            w32(m+prev,address+head);w32(m+head+4,address+prev);
        }
        w32(m+0x100,cursor-0x100);
    }
    if(rc) {if(p.region.handle) vm->release(vm->context,&p.region);return rc;}
    *out=p;return PW_OK;
}
static int teb_valid(PwX86State *s)
{
    if(!s || !s->fs_base || s->fs_bytes<0x34) return 0;
    for(unsigned i=0;i<s->memory_count;++i)
        if(s->fs_base>=s->memory[i].low && (uint64_t)s->fs_base+0x34<=s->memory[i].high &&
           (s->memory[i].permissions&3)==3) return 1;
    return 0;
}
int pw_process_ps4_bind(PwPs4Process *p,PwX86State *s,uint32_t *previous)
{
    if(!p || !p->region.handle || !previous || !teb_valid(s) || s->memory_count>=PW_X86_MEMORY_REGIONS) return PW_ERR_PRECONDITION;
    for(unsigned i=0;i<s->memory_count;++i) if(s->memory[i].low==p->peb) return PW_ERR_STATE;
    memcpy(previous,(void *)(uintptr_t)(s->fs_base+0x30),4);
    w32((void *)(uintptr_t)(s->fs_base+0x30),p->peb);
    s->memory[s->memory_count++]=(PwX86Memory){p->peb,(uint64_t)p->peb+PW_PE32_PAGE,3};
    p->bindings++;
    return PW_OK;
}
int pw_process_ps4_unbind(PwPs4Process *p,PwX86State *s,uint32_t previous)
{
    if(!p || !p->region.handle || !teb_valid(s)) return PW_ERR_PRECONDITION;
    uint32_t current;memcpy(&current,(void *)(uintptr_t)(s->fs_base+0x30),4);
    if(current!=p->peb || !p->bindings) return PW_ERR_STATE;
    for(unsigned i=0;i<s->memory_count;++i) if(s->memory[i].low==p->peb) {
        w32((void *)(uintptr_t)(s->fs_base+0x30),previous);
        memmove(&s->memory[i],&s->memory[i+1],(s->memory_count-i-1)*sizeof(s->memory[0]));
        s->memory_count--;p->bindings--;return PW_OK;
    }
    return PW_ERR_STATE;
}
int pw_process_ps4_destroy(PwPs4Process *p)
{
    if(!p || !p->region.handle || p->bindings) return PW_ERR_STATE;
    int rc=p->backend.release(p->backend.context,&p->region);
    if(!rc) memset(p,0,sizeof(*p));return rc;
}
