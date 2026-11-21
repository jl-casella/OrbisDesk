/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Read-only second-stage inspection; the build generates offsets from a prior capture. */
#include "inspection_plan.h"
static int p004_readable(const OrbisKernelModuleInfo *info,uintptr_t at,size_t bytes)
{
    for(unsigned s=0;s<info->segmentCount && s<4;s++){
        uintptr_t start=(uintptr_t)info->segmentInfo[s].address;size_t size=info->segmentInfo[s].size;
        if((info->segmentInfo[s].prot&PROT_READ) && at>=start && at-start<size && bytes<=size-(at-start))return 1;
    }
    return 0;
}
static int p004_save(unsigned index,const char *kind,uintptr_t at,size_t bytes)
{
    char path[240];snprintf(path,sizeof(path),"%s/call-%u-%s.bin",run_dir,index,kind);
    FILE *file=fopen(path,"wb");if(!file)return 0;
    int saved=fwrite((const void *)at,1,bytes,file)==bytes;fflush(file);fsync(fileno(file));fclose(file);return saved;
}
static void p004_inspect(void *entry,const OrbisKernelModuleInfo *owner,const OrbisKernelModule *modules,size_t count)
{
    uintptr_t base=(uintptr_t)entry;
    if(!p004_readable(owner,base,P004_REFERENCE_BYTES)){note("inspection_reference_unreadable",-1,0,0);return;}
    uint64_t fingerprint=UINT64_C(14695981039346656037);
    for(unsigned i=0;i<P004_REFERENCE_BYTES;i++){fingerprint^=((const unsigned char *)entry)[i];fingerprint*=UINT64_C(1099511628211);}
    if(fingerprint!=P004_REFERENCE_FNV){note("inspection_reference_changed",-1,0,0);return;}
    note("inspection_reference_matched",0,0,P004_REFERENCE_BYTES);
    for(unsigned i=0;i<sizeof(p004_calls)/sizeof(p004_calls[0]);i++){
        int64_t offset=p004_calls[i];
        if((offset<0 && base<(uint64_t)(-offset)) || (offset>0 && UINTPTR_MAX-base<(uint64_t)offset))continue;
        uintptr_t stub=offset<0?base-(uintptr_t)(-offset):base+(uintptr_t)offset;
        if(!p004_readable(owner,stub,32)){note("call_stub_unreadable",-1,0,i);continue;}
        int stub_saved=p004_save(i,"stub",stub,32);
        const unsigned char *code=(const unsigned char *)stub;
        uintptr_t got=0,target=0;int target_saved=0;unsigned target_module=0;
        if(code[0]==0xff && code[1]==0x25){
            int32_t displacement;memcpy(&displacement,code+2,sizeof(displacement));
            got=displacement<0?stub+6-(uintptr_t)(-(int64_t)displacement):stub+6+(uintptr_t)displacement;
            if(p004_readable(owner,got,sizeof(target))){
                memcpy(&target,(const void *)got,sizeof(target));
                for(size_t m=0;m<count;m++){
                    OrbisKernelModuleInfo info;memset(&info,0,sizeof(info));info.size=sizeof(info);
                    if(!sceKernelGetModuleInfo(modules[m],&info) && p004_readable(&info,target,64)){
                        target_saved=p004_save(i,"target",target,64);target_module=modules[m];break;
                    }
                }
            }
        }
        pthread_mutex_lock(&log_lock);
        if(log_file){fprintf(log_file,"{\"event\":\"call_inspection\",\"index\":%u,\"entry_delta\":%lld,\"stub\":\"%llx\",\"got\":\"%llx\",\"target\":\"%llx\",\"target_module\":%u,\"stub_saved\":%s,\"target_saved\":%s}\n",i,(long long)offset,(unsigned long long)stub,(unsigned long long)got,(unsigned long long)target,target_module,stub_saved?"true":"false",target_saved?"true":"false");fflush(log_file);fsync(fileno(log_file));}
        pthread_mutex_unlock(&log_lock);
    }
    const char *names[]={"vfork","_vfork","execve","_execve","_exit","exit","__error"};
    for(unsigned n=0;n<sizeof(names)/sizeof(names[0]);n++)for(size_t m=0;m<count;m++){
        void *address=NULL;if(sceKernelDlsym(modules[m],names[n],&address) || !address)continue;
        pthread_mutex_lock(&log_lock);
        if(log_file){fprintf(log_file,"{\"event\":\"related_export\",\"name\":\"%s\",\"module\":%u,\"address\":\"%llx\"}\n",names[n],modules[m],(unsigned long long)(uintptr_t)address);fflush(log_file);fsync(fileno(log_file));}
        pthread_mutex_unlock(&log_lock);
    }
}
