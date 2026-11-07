/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <sched.h>
extern int sysarch(int,void *);
static __thread uint64_t native_cookie;
struct GsRecord {uintptr_t self;uint64_t cookie;};
struct Worker {uint64_t cookie;int verified,restored;};
static void *worker(void *argument)
{
    struct Worker *work=argument;
    struct GsRecord record={(uintptr_t)&record,work->cookie};
    uintptr_t original=UINTPTR_MAX,observed=UINTPTR_MAX;
    native_cookie=work->cookie ^ UINT64_C(0xabcd1234);
    if(sysarch(130,&original) || original==UINTPTR_MAX) return NULL;
    uintptr_t requested=(uintptr_t)&record;
    if(sysarch(131,&requested)) return NULL;
    int valid=!sysarch(130,&observed) && observed==requested;
    if(valid) {
        for(int n=0;n<1000;++n) {
            uintptr_t self;uint64_t cookie;
            __asm__ volatile("movq %%gs:0,%0; movq %%gs:8,%1":"=r"(self),"=r"(cookie)::"memory");
            if(self!=requested || cookie!=work->cookie || native_cookie!=(work->cookie ^ UINT64_C(0xabcd1234))) {
                valid=0;break;
            }
            sched_yield();
        }
    }
    work->verified=valid;
    observed=UINTPTR_MAX;
    work->restored=!sysarch(131,&original) && !sysarch(130,&observed) && observed==original;
    return NULL;
}
static int fsbase_contract(void)
{
    uintptr_t fsbase=UINTPTR_MAX,self,untouched=UINTPTR_MAX;
    __asm__ volatile("movq %%fs:0,%0":"=r"(self));
    int read=!sysarch(128,&fsbase) && fsbase==self && fsbase;
    int refused=sysarch(129,&untouched)==-1 && untouched==UINTPTR_MAX;
    return read && refused;
}
int pw_wine_boot_gs_services(void)
{
    int fsbase=fsbase_contract();
    printf("PWSERVICE {\"case\":\"gs-fsbase-contract\",\"status\":\"%s\"}\n",fsbase?"passed":"blocked");
    fflush(stdout);
    struct Worker main_work={UINT64_C(0x123456789abcdef0),0,0};worker(&main_work);
    if(!main_work.verified || !main_work.restored) {
        printf("PWSERVICE {\"case\":\"gs-memory-and-native-tls\",\"status\":\"blocked\"}\n");
        fflush(stdout);return 93;
    }
    pthread_t threads[2];struct Worker work[2]={{UINT64_C(0x1111222233334444),0,0},{UINT64_C(0xaaaabbbbccccdddd),0,0}};
    int made=0,joined=1;
    for(int i=0;i<2;++i) {if(pthread_create(&threads[i],NULL,worker,&work[i])) break;++made;}
    for(int i=0;i<made;++i) if(pthread_join(threads[i],NULL)) joined=0;
    int valid=made==2 && joined && work[0].verified && work[0].restored && work[1].verified && work[1].restored;
    printf("PWSERVICE {\"case\":\"gs-memory-and-native-tls\",\"status\":\"%s\"}\n",valid?"passed":"blocked");
    fflush(stdout);return valid && fsbase?0:93;
}
