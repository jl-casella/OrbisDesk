/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "pw_pe32.h"
#include "pw_vm_ps4.h"
#include <stdio.h>
#include <stdlib.h>
/* Feed the exact built DLL into the real PS4 parser/mapper. An unsupported
 * feature is evidence of a block, never a successful Wine startup. */
int probe_wine(int kind,char *detail,size_t capacity)
{
    const char *names[]={"ntdll.dll","kernelbase.dll","kernel32.dll"};
    if(kind<0 || kind>2) return PW_ERR_PRECONDITION;
    char path[96];snprintf(path,sizeof(path),"/data/%s",names[kind]);
    PwVmBackend vm={0};PwVmRegion buffer={0};
    int setup=pw_vm_ps4_backend(&vm);if(setup) return setup;
    FILE *f=fopen(path,"rb");if(!f) return 1;
    int rc=fseek(f,0,SEEK_END);long length=ftell(f);
    if(length<=0 || length>64*1024*1024) rc=1;
    if(!rc) rc=fseek(f,0,SEEK_SET);
    if(!rc) rc=vm.reserve(vm.context,(size_t)length,PW_PE32_PAGE,&buffer);
    if(!rc) rc=vm.commit(vm.context,&buffer,0,buffer.bytes,3);
    void *data=buffer.write_base;
    if(!rc && fread(data,1,(size_t)length,f)!=(size_t)length) rc=1;
    if(fclose(f)) rc=1;
    PwPe32Info info={0};PwPe32Image image={0};
    const char *stage="read";
    if(!rc) {stage="inspect";rc=pw_pe32_inspect(data,(size_t)length,&info);}
    if(!rc) stage="map";
    if(!rc) rc=pw_pe32_load(&vm,data,(size_t)length,info.preferred,&image);
    if(buffer.handle && vm.release(vm.context,&buffer)) rc=1;
    int original=rc;
    if(image.region.handle && pw_pe32_unload(&image)) rc=1;
    PwPs4VmStats memory={0};if(pw_vm_ps4_stats(&memory) || memory.reservations) rc=1;
    if(!rc) {stage="unix-bootstrap-not-implemented";rc=PW_ERR_UNSUPPORTED;}
    if(rc==PW_ERR_LIMIT) rc=PW_ERR_UNSUPPORTED;
    snprintf(detail,capacity,"module=%s bytes=%ld stage=%s loader_code=%d imports=%u exports=%u live=%zu Wine_booted=0",
             names[kind],length,stage,original,info.import_count,info.export_count,memory.reservations);
    return rc;
}
