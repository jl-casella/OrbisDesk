/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Freestanding payload: no SDK CRT, kernel patches, spawn, graphics or audio. */
#include "process_loader_protocol.h"
static long logfile=-1;
static void log_number(const char *event,uint64_t number)
{
    char line[192],digits[24];unsigned n=0,d=0;
    const char *p="{\"build\":\"P005\",\"event\":\"";while(*p)line[n++]=*p++;
    while(*event && n<128)line[n++]=*event++;
    p="\",\"value\":";while(*p)line[n++]=*p++;
    do{digits[d++]=(char)('0'+number%10);number/=10;}while(number && d<24);
    while(d)line[n++]=digits[--d];line[n++]='}';line[n++]='\n';
    if(logfile>=0){p005_sys(4,logfile,(long)line,n,0,0,0);p005_sys(95,logfile,0,0,0,0,0);}
    p005_sys(4,1,(long)line,n,0,0,0);
}
static void path_join(char *out,const char *dir,const char *name)
{
    unsigned n=0;while(n<159 && dir[n]){out[n]=dir[n];n++;}out[n++]='/';
    while(*name && n<220)out[n++]=*name++;out[n]=0;
}
__attribute__((noreturn,force_align_arg_pointer)) void _start(void)
{
    struct p005_request request;char path[224];int result=80;void *low=0;struct p005_state *state=0;
    long fd=p005_sys(5,(long)P005_REQUEST_PATH,0,0,0,0,0);
    if(fd<0)goto done;
    long bytes=p005_sys(3,fd,(long)&request,sizeof(request),0,0,0);p005_sys(6,fd,0,0,0,0,0);
    if(bytes!=sizeof(request) || request.magic!=P005_MAGIC || request.directory[159])goto done;
    /* Only our diagnostic run directories can be selected by this request. */
    const char *prefix="/data/orbisdesk/process-p005/run-";
#ifdef P005_HOST_REFERENCE
    prefix="/var/tmp/";
#endif
    unsigned i=0;while(prefix[i] && request.directory[i]==prefix[i])i++;
    if(prefix[i])goto done;
    for(unsigned j=i;request.directory[j];j++)if(request.directory[j]=='.')goto done;
    path_join(path,request.directory,"helper.jsonl");
    /* Orbis O_WRONLY|O_CREAT|O_EXCL; Linux reference uses its own constants. */
#ifdef P005_HOST_REFERENCE
    logfile=p005_sys(5,(long)path,1|64|128,0644,0,0,0);
#else
    logfile=p005_sys(5,(long)path,1|0x200|0x800,0644,0,0,0);
#endif
    log_number("helper_entered",p005_sys(20,0,0,0,0,0,0));
    path_join(path,request.directory,"state.bin");fd=p005_sys(5,(long)path,2,0,0,0,0);
    if(fd<0){result=81;goto done;}
    long view=p005_sys(477,0,P005_PAGE,3,1,fd,0);p005_sys(6,fd,0,0,0,0,0);
    if(view<0){result=82;goto done;}state=(void *)view;
    uint32_t pid=(uint32_t)p005_sys(20,0,0,0,0,0,0);
    if(state->magic!=P005_MAGIC || state->token[0]!=request.token[0] || state->token[1]!=request.token[1] ||
       state->observer_pid!=request.observer_pid || state->observer_pid==pid){result=83;goto done;}
    long mapping=p005_sys(477,0x400000,P005_PAGE,3,2|0x1000,-1,0);
    if(mapping>=0){low=(void *)mapping;*(volatile uint32_t *)low=0x55667788;}
    state->helper_low_ok=low==(void *)0x400000;
    state->helper_low_value=low?*(volatile uint32_t *)low:0;
    state->helper_ppid=(uint32_t)p005_sys(39,0,0,0,0,0,0);
    __atomic_store_n(&state->helper_pid,pid,__ATOMIC_RELEASE);
    uint32_t start=__atomic_load_n(&state->observer_tick,__ATOMIC_ACQUIRE);
    for(unsigned n=0;n<200;n++){
        __atomic_add_fetch(&state->helper_tick,1,__ATOMIC_RELEASE);
        if(__atomic_load_n(&state->observer_tick,__ATOMIC_ACQUIRE)>=start+5 &&
           __atomic_load_n(&state->observer_seen_child,__ATOMIC_ACQUIRE) && n>=10){
            state->helper_parent_progress=1;result=42;break;
        }
        p005_delay();
    }
    if(result!=42)result=84;
    log_number("observer_pid",state->observer_pid);log_number("helper_ppid",state->helper_ppid);
    log_number("parent_progress",state->helper_parent_progress);log_number("low_address",(uintptr_t)low);
    __atomic_store_n(&state->helper_done,(uint32_t)result,__ATOMIC_RELEASE);
done:
    log_number("helper_exit_requested",(uint32_t)result);
    if(low)p005_sys(73,(long)low,P005_PAGE,0,0,0,0);
    if(state)p005_sys(73,(long)state,P005_PAGE,0,0,0,0);
    if(logfile>=0)p005_sys(6,logfile,0,0,0,0,0);
    p005_sys(1,result,0,0,0,0,0);__builtin_trap();
}
