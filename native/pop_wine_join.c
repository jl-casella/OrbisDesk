/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Host-side driver for the Phase B / P014 slim Wine client (see pop_wine_join_core.h). Two independent
 * instances against one running wineserver prove the cross-process shared named-object mechanism:
 *   pop_wine_join create <Name>   -> creates the object (expects STATUS_SUCCESS), then holds it
 *   pop_wine_join open   <Name>   -> opens it (expects STATUS_OBJECT_NAME_EXISTS)
 * <Name>: an absolute path ("\\KernelObjects\\PrinceSM") is used as-is; otherwise it is placed under
 * \BaseNamedObjects. Env: WINEPREFIX, WINESERVERDIR (override server dir), POP_HOLD_SECONDS. */
#include "pop_wine_join_core.h"

int main(int argc,char **argv){
    if(argc<3){fprintf(stderr,"usage: %s create|open <ObjectName>\n",argv[0]);return 1;}
    int opening=!strcmp(argv[1],"open");
    char fullname[256];
    if(argv[2][0]=='\\')snprintf(fullname,sizeof(fullname),"%s",argv[2]);
    else snprintf(fullname,sizeof(fullname),"\\BaseNamedObjects\\%s",argv[2]);

    const char *hold=getenv("POP_HOLD_SECONDS");int secs=opening?0:(hold&&*hold?atoi(hold):15);
    struct pop_join j={.fd_socket=-1,.request_fd=-1,.reply_fd=-1,.log=NULL};
    int ok=pop_wine_join_run(&j,NULL,opening,fullname,secs);
    printf("{\"role\":\"%s\",\"name\":\"%s\",\"shared_namespace_ok\":%d}\n",opening?"open":"create",argv[2],ok);
    fflush(stdout);
    return ok?0:5;
}
