/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "pw_process_ps4.h"
#include "pw_cpu_ps4.h"
#include "pw_vm_ps4.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int probe_process(int kind,char *detail,size_t capacity)
{
    PwVmBackend vm={0};PwPs4Process p={0};PwPe32Image image={0};
    PwVmRegion data={0};PwPs4Cpu *cpu=NULL;uint32_t previous=0;int bound=0;
    FILE *f=fopen("/data/process32.exe","rb");size_t bytes=0;void *file=NULL;int rc=pw_vm_ps4_backend(&vm);
    if(!f) rc=1;
    if(!rc && fseek(f,0,SEEK_END)) rc=1;
    long length=!rc?ftell(f):0;if(length<=0 || length>PW_PE32_MAX_FILE) rc=1;
    if(!rc && fseek(f,0,SEEK_SET)) rc=1;
    if(!rc) {bytes=(size_t)length;file=malloc(bytes);if(!file) rc=1;}
    if(!rc && fread(file,1,bytes,f)!=bytes) rc=1;
    if(f && fclose(f)) rc=1;
    if(!rc) rc=pw_pe32_load(&vm,file,bytes,kind==1?0x34000000:0x30000000,&image);
    free(file);
    PwPe32Module module={"process32.exe",&image};
    if(!rc) rc=pw_process_ps4_create(&p,&vm,0x3c000000,&module,1,"C:\\process32.exe","process32.exe --verify","C:\\");
    if(!rc && kind==2) {
        PwPs4Process untouched={0};
        int rejected=pw_process_ps4_create(&untouched,&vm,p.peb,&module,1,"x","x","x");
        if(!rejected || untouched.region.handle) rc=1;
    }
    if(!rc) rc=vm.reserve_at(vm.context,0x38000000,2*PW_PE32_PAGE,PW_PE32_PAGE,&data);
    if(!rc) rc=vm.commit(vm.context,&data,0,data.bytes,3);
    if(!rc) rc=pw_cpu_ps4_create(&cpu,&vm,pw_pe32_source,&image);
    if(!rc) {
        memset(data.write_base,0,data.bytes);
        PwX86State *s=pw_cpu_ps4_state(cpu);
        s->stack_low=0x38000000;s->stack_high=0x38004000;s->gpr[4]=s->stack_high-16;
        s->fs_base=0x38004000;s->fs_bytes=PW_PE32_PAGE;
        uint32_t *teb=(void *)(uintptr_t)s->fs_base;
        teb[0]=UINT32_MAX;
        teb[0x18/4]=s->fs_base;teb[4/4]=s->stack_high;teb[8/4]=s->stack_low;
        s->memory[s->memory_count++]=(PwX86Memory){0x38000000,0x38008000,3};
        rc=pw_pe32_bind(&image,s);
        if(!rc) rc=pw_process_ps4_bind(&p,s,&previous);
        if(!rc) bound=1;
        if(!rc && pw_process_ps4_bind(&p,s,&previous)!=PW_ERR_STATE) rc=1;
        if(!rc && pw_process_ps4_destroy(&p)!=PW_ERR_STATE) rc=1;
        *(uint32_t *)(uintptr_t)s->gpr[4]=0x0badf00d;s->eip=image.entry;
        if(!rc) rc=pw_cpu_ps4_run(cpu,0x0badf00d,4096);
        if(!rc && s->gpr[0]!=42) rc=1;
    }
    unsigned result=cpu?pw_cpu_ps4_state(cpu)->gpr[0]:0;
    if(bound && pw_process_ps4_unbind(&p,pw_cpu_ps4_state(cpu),previous)) rc=1;
    if(cpu && pw_cpu_ps4_destroy(cpu)) rc=1;
    if(data.handle && vm.release(vm.context,&data)) rc=1;
    if(p.region.handle && pw_process_ps4_destroy(&p)) rc=1;
    if(image.region.handle && pw_pe32_unload(&image)) rc=1;
    PwPs4VmStats stats={0};if(pw_vm_ps4_stats(&stats) || stats.reservations) rc=1;
    snprintf(detail,capacity,"kind=%d rc=%d guest_result=%u peb_params_ldr=real live=%zu",kind,rc,result,stats.reservations);
    return rc;
}
