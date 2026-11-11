/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include <fcntl.h>
#include <stdio.h>
#include <sys/mman.h>
#include <unistd.h>
#include <orbis/libkernel.h>
#include "process_probe_shared.h"

int main(int argc,char **argv)
{
    if(argc!=2)return 80;
    char path[240];snprintf(path,sizeof(path),"%s/child.jsonl",argv[1]);
    FILE *log=fopen(path,"w");
    if(!log)return 81;
    fprintf(log,"{\"event\":\"child_entered\",\"pid\":%ld,\"ppid\":%ld}\n",(long)getpid(),(long)getppid());fflush(log);
    snprintf(path,sizeof(path),"%s/state.bin",argv[1]);
    int fd=open(path,O_RDWR);if(fd<0){fclose(log);return 82;}
    void *view=NULL;int rc=sceKernelMmap(NULL,P002_PAGE,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0,&view);
    if(rc){fprintf(log,"{\"event\":\"child_map_failed\",\"rc\":%d}\n",rc);fclose(log);close(fd);return 83;}
    struct p002_shared *state=view;
    if(state->magic!=P002_MAGIC || state->parent_pid==(uint32_t)getpid()) {
        fputs("{\"event\":\"child_identity_failed\"}\n",log);fclose(log);return 84;
    }
    void *low=NULL;
    rc=sceKernelMmap((void *)0x400000,P002_PAGE,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0,&low);
    int low_ok=!rc && low==(void *)0x400000;
    if(!rc)*(volatile uint32_t *)low=0x55667788;
    state->child_low_ok=low_ok;state->child_value=!rc?*(volatile uint32_t *)low:0;
    __atomic_store_n(&state->child_pid,(uint32_t)getpid(),__ATOMIC_RELEASE);
    uint32_t initial=__atomic_load_n(&state->heartbeat,__ATOMIC_ACQUIRE);
    for(unsigned n=0;n<150;n++) {
        if(__atomic_load_n(&state->heartbeat,__ATOMIC_ACQUIRE)>initial) {
            __atomic_store_n(&state->child_seen,1,__ATOMIC_RELEASE);break;
        }
        sceKernelUsleep(20000);
    }
    int seen=__atomic_load_n(&state->child_seen,__ATOMIC_ACQUIRE);
    fprintf(log,"{\"event\":\"child_result\",\"pid\":%ld,\"parent_pid\":%u,\"parent_progress\":%s,\"low_mapping_rc\":%d,\"low_mapping_at_400000\":%s,\"exit_code\":%d}\n",
            (long)getpid(),state->parent_pid,seen?"true":"false",rc,low_ok?"true":"false",seen?42:85);
    fflush(log);fsync(fileno(log));fclose(log);
    if(!rc)sceKernelMunmap(low,P002_PAGE);
    sceKernelMunmap(view,P002_PAGE);close(fd);
    return seen?42:85;
}
