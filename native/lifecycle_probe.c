/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "pw_pe32_lifecycle.h"
#include "pw_pe32_internal.h"
#include "pw_vm_ps4.h"
#include "pw_guest_call.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint32_t read32(const void *p) { uint32_t v; memcpy(&v,p,4); return v; }
static void write32(void *p,uint32_t v) { memcpy(p,&v,4); }
static uint8_t *file_read(const char *path,size_t *size)
{
    FILE *f=fopen(path,"rb"); if (!f) return NULL;
    int rc=fseek(f,0,SEEK_END); long bytes=ftell(f);
    if (bytes<=0 || bytes>PW_PE32_MAX_FILE) rc=1;
    if (!rc) rc=fseek(f,0,SEEK_SET);
    uint8_t *data=!rc?malloc((size_t)bytes):NULL;
    if (!data) rc=1;
    if (!rc && fread(data,1,(size_t)bytes,f)!=(size_t)bytes) rc=1;
    if (fclose(f)) rc=1;
    if (rc) {free(data);return NULL;} *size=(size_t)bytes;return data;
}
static uint32_t exported(PwPe32Image *image,const char *name)
{
    for(unsigned i=0;i<image->info.export_count;++i)
        if(!strcmp(image->info.exports[i].name,name)) return image->base+image->info.exports[i].rva;
    return 0;
}
static int call(PwPs4Cpu *cpu,PwPe32Image *image,const char *name,unsigned arg,uint32_t *result)
{
    PwGuestCallback callback={0}; uint64_t value=0;
    int rc=pw_guest_callback_enter(&callback,pw_cpu_ps4_state(cpu),exported(image,name),0x0badf00d,&arg,1,PW_GUEST_CDECL);
    if(!rc) rc=pw_cpu_ps4_run(cpu,0x0badf00d,256);
    if(!rc) rc=pw_guest_callback_leave(&callback,32,&value);
    if(!rc) *result=(uint32_t)value;
    return rc;
}
typedef struct Driver {PwPs4Cpu *cpu;PwVmRegion stack;PwPe32Thread thread;} Driver;
static int driver_create(Driver *driver,PwVmBackend *vm,PwPe32Lifecycle *life,PwPe32Modules *modules,int main_thread)
{
    uint32_t stack=main_thread?0x38000000:0x39000000;
    int rc=vm->reserve_at(NULL,stack,PW_PE32_PAGE,PW_PE32_PAGE,&driver->stack);
    if(!rc) rc=vm->commit(NULL,&driver->stack,0,PW_PE32_PAGE,3);
    if(!rc) rc=pw_cpu_ps4_create(&driver->cpu,vm,pw_pe32_modules_source,modules);
    if(!rc) {
        PwX86State *s=pw_cpu_ps4_state(driver->cpu);
        s->stack_low=stack;s->stack_high=stack+PW_PE32_PAGE;s->gpr[4]=s->stack_high-16;
        s->memory[s->memory_count++]=(PwX86Memory){stack,(uint64_t)stack+PW_PE32_PAGE,3};
        for(size_t i=0;!rc && i<modules->count;++i) rc=pw_pe32_bind(modules->modules[i].image,s);
        if(!rc) rc=pw_pe32_thread_create(life,driver->cpu,main_thread?0x3a000000:0x3b000000,main_thread,&driver->thread);
    }
    return rc;
}
static int driver_destroy(Driver *driver,PwVmBackend *vm)
{
    int rc=0;
    if(driver->thread.region.handle && pw_pe32_thread_destroy(&driver->thread)) rc=1;
    if(driver->cpu && pw_cpu_ps4_destroy(driver->cpu)) rc=1;
    driver->cpu=NULL;
    if(driver->stack.handle && vm->release(NULL,&driver->stack)) rc=1;
    return rc;
}
static int diagnostics(PwPe32Image *image,PwPe32Thread *thread,unsigned index,const unsigned *expected,unsigned count)
{
    uint32_t *block=(uint32_t *)(uintptr_t)thread->blocks[index];
    uint32_t address=block[3];
    if(address<image->base || (uint64_t)address+34*4>(uint64_t)image->base+image->info.image_bytes) return 1;
    volatile uint32_t *d=(volatile uint32_t *)(uintptr_t)address;
    if(d[0] || d[1]!=count || block[2]!=4) return 1;
    for(unsigned i=0;i<count;++i) if(d[i+2]!=expected[i]) return 1;
    return 0;
}
typedef struct Worker {
    PwVmBackend *vm;PwPe32Lifecycle *life;PwPe32Modules *modules;PwPe32Image *image;
    pthread_mutex_t mutex;pthread_cond_t condition;
    int ready,release,rc;uint32_t block;
} Worker;
static void *worker_run(void *opaque)
{
    Worker *w=opaque;Driver driver={0};uint32_t value=0;
    int rc=driver_create(&driver,w->vm,w->life,w->modules,0);
    if(!rc) rc=pw_pe32_thread_attach(&driver.thread);
    errno=129;
    if(!rc) rc=call(driver.cpu,w->image,"Touch",99,&value);
    if(!rc && value!=7) rc=1;
    w->block=driver.thread.blocks[0];
    pthread_mutex_lock(&w->mutex);w->rc=rc;w->ready=1;pthread_cond_broadcast(&w->condition);
    while(!w->release) pthread_cond_wait(&w->condition,&w->mutex);
    pthread_mutex_unlock(&w->mutex);
    if(!rc && errno!=129) rc=1;
    if(!rc) rc=call(driver.cpu,w->image,"Touch",100,&value);
    if(!rc && value!=99) rc=1;
    if(driver.thread.attached && pw_pe32_thread_detach(&driver.thread)) rc=1;
    if(driver.thread.region.handle && *(uint32_t *)(uintptr_t)(driver.thread.blocks[0]+8)!=4) rc=1;
    if(driver_destroy(&driver,w->vm)) rc=1;
    w->rc=rc;return NULL;
}
static int invalid_tls(uint8_t *file,size_t bytes,unsigned *checks)
{
    PwPe32Info info;if(pw_pe32_inspect(file,bytes,&info)) return 1;
    uint8_t *tls=(uint8_t *)pw_pe32_file_rva(file,&info,info.tls_rva,24);
    if(!tls) return 1;
    unsigned offsets[]={0,8,12,16,20};
    uint32_t values[]={0xffffffffu,info.preferred+info.entry_rva,0xffffffffu,0x1001,1};
    int expected[]={PW_ERR_LIMIT,PW_ERR_MALFORMED,PW_ERR_MALFORMED,PW_ERR_LIMIT,PW_ERR_UNSUPPORTED};
    for(unsigned i=0;i<5;++i) {
        uint32_t saved=read32(tls+offsets[i]);write32(tls+offsets[i],values[i]);
        int rc=pw_pe32_inspect(file,bytes,&info);write32(tls+offsets[i],saved);
        if(rc!=expected[i]) return 1;(*checks)++;
    }
    uint32_t callbacks=read32(tls+12)-info.preferred;
    uint8_t *array=(uint8_t *)pw_pe32_file_rva(file,&info,callbacks,17*4);
    if(!array) return 1;uint8_t before[17*4];memcpy(before,array,sizeof(before));
    for(unsigned i=0;i<17;++i) write32(array+i*4,info.preferred+info.tls_callbacks[0]);
    int rc=pw_pe32_inspect(file,bytes,&info);memcpy(array,before,sizeof(before));
    if(rc!=PW_ERR_LIMIT) return 1;(*checks)++;
    return 0;
}
int probe_lifecycle(int kind,char *detail,size_t capacity)
{
    PwVmBackend vm;int rc=pw_vm_ps4_backend(&vm);
    PwPe32Image images[2]={0};PwPe32Lifecycle life={0};Driver main={0};
    unsigned checks=0,events=0,status=0;int init_result=0;
    unsigned count=kind==3||kind==4?1:2;
    for(unsigned i=0;!rc && i<count;++i) {
        const char *path=i?(kind==2?"/data/lifecycle-fail.dll":"/data/lifecycle-peer.dll"):"/data/lifecycle.dll";
        size_t bytes=0;uint8_t *file=file_read(path,&bytes);
        if(!file) {rc=1;break;}
        if(kind==4) rc=invalid_tls(file,bytes,&checks);
        else rc=pw_pe32_load(&vm,file,bytes,kind==1?(i?0x35000000:0x34000000):0,&images[i]);
        free(file);
    }
    PwPe32Image *image_ptrs[]={&images[0],&images[1]};
    PwPe32Module entries[]={{"lifecycle.dll",&images[0]},{"lifecycle-peer.dll",&images[1]}};
    PwPe32Modules modules={entries,count};
    if(!rc && kind!=4) rc=pw_pe32_lifecycle_create(&life,&vm,image_ptrs,count);
    if(!rc && kind!=4) rc=driver_create(&main,&vm,&life,&modules,1);
    if(!rc && kind!=4) {
        if(pw_pe32_unload(&images[0])!=PW_ERR_STATE || pw_pe32_lifecycle_destroy(&life)!=PW_ERR_STATE) rc=1;
        const uint8_t *source;size_t bytes;
        if(pw_pe32_source(&images[0],images[0].entry,&source,&bytes)!=PW_ERR_STATE) rc=1;
    }
    if(!rc && kind!=4) {
        init_result=pw_pe32_process_attach(&main.thread);
        if(init_result!=(kind==2?PW_PE32_INIT_FAILED:PW_OK)) rc=1;
        if(kind==2) {
            if(life.status!=PW_PE32_LIFE_FAILED || life.events!=8 || life.trace[3].result!=0) rc=1;
            for(unsigned i=0;i<2;++i) {
                const unsigned expected[]={0x11,0x21,0x10,0x20};
                if(diagnostics(&images[i],&main.thread,i,expected,4)) rc=1;
            }
            if(!rc) checks++;
        } else if(!rc) {
            uint32_t value=0;
            rc=call(main.cpu,&images[0],"Touch",55,&value);
            if(!rc && value!=7) rc=1;
            if(!rc && kind==3) {
                Worker worker={.vm=&vm,.life=&life,.modules=&modules,.image=&images[0],
                    .mutex=PTHREAD_MUTEX_INITIALIZER,.condition=PTHREAD_COND_INITIALIZER};
                pthread_t child;errno=117;
                int created=pthread_create(&child,NULL,worker_run,&worker);
                if(created) rc=1;
                else {
                    pthread_mutex_lock(&worker.mutex);
                    while(!worker.ready) pthread_cond_wait(&worker.condition,&worker.mutex);
                    if(worker.rc || errno!=117) rc=1;
                    if(!rc) rc=call(main.cpu,&images[0],"Inspect",64,&value);
                    if(!rc && (value!=55 || worker.block==main.thread.blocks[0])) rc=1;
                    worker.release=1;pthread_cond_broadcast(&worker.condition);pthread_mutex_unlock(&worker.mutex);
                    if(pthread_join(child,NULL) || worker.rc) rc=1;
                }
                pthread_cond_destroy(&worker.condition);pthread_mutex_destroy(&worker.mutex);
            }
            if(!rc) rc=call(main.cpu,&images[0],"Inspect",64,&value);
            if(!rc && value!=55) rc=1;
            if(!rc) rc=pw_pe32_process_detach(&main.thread);
            if(!rc) {
                const unsigned simple[]={0x11,0x21,0x10,0x20};
                const unsigned threaded[]={0x11,0x21,0x12,0x22,0x13,0x23,0x10,0x20};
                for(unsigned i=0;i<count;++i)
                    if(diagnostics(&images[i],&main.thread,i,kind==3?threaded:simple,kind==3?8:4)) rc=1;
                if(!rc) checks++;
            }
        }
        if(!rc) {
            if(life.events!=8) rc=1;
            for(unsigned i=0;i<life.events;++i) {
                unsigned module=kind==3?0:i<4?i/2:(7-i)/2;
                unsigned reason=kind==3?(i<2?1:i<4?2:i<6?3:0):(i<4?1:0);
                if(life.trace[i].module!=module || life.trace[i].reason!=reason || life.trace[i].tls!=(i%2==0)) rc=1;
            }
            if(!rc) checks++;
        }
        if(!rc) {
            PwX86State *state=pw_cpu_ps4_state(main.cpu);
            uint32_t saved=state->eip;
            state->eip=kind==2?images[1].entry:exported(&images[0],"Touch");
            if(pw_cpu_ps4_step(main.cpu)!=PW_ERR_STATE) rc=1;
            state->eip=saved;
            if(!rc) checks++;
        }
    }
    events=life.events;status=life.status;
    if(main.thread.attached && life.status==PW_PE32_LIFE_ATTACHED && pw_pe32_process_detach(&main.thread)) rc=1;
    if(driver_destroy(&main,&vm)) rc=1;
    if(life.initialized && pw_pe32_lifecycle_destroy(&life)) rc=1;
    for(unsigned i=0;i<2;++i) if(images[i].region.handle && pw_pe32_unload(&images[i])) rc=1;
    PwPs4VmStats memory={0};
    if(pw_vm_ps4_stats(&memory)||memory.reservations||memory.committed_bytes) rc=1;
    snprintf(detail,capacity,"kind=%d rc=%d init_result=%d status=%u notifications=%u checks=%u live=%zu",
             kind,rc,init_result,status,events,checks,memory.reservations);
    return rc;
}
