/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* P012 identity gate: do not send a SELF to a stale/unknown resident loader. */
#include "p012_expected_loader.h"
static int p012_verify_loader(void)
{
    int socket=sceNetSocket("p012-identity",2,1,0),one=1,result=0;
    char response[512]={0};unsigned used=0;
    if(socket<0){note("loader_identity_socket_failed",net_error());return 0;}
    if(sceNetSetsockopt(socket,0xffff,0x1200,&one,sizeof(one))<0)goto done;
    struct {uint8_t len,family;uint16_t port;uint8_t ip[4],zero[8];} address={16,2,0,{127,0,0,1},{0}};
    address.port=(uint16_t)((9021>>8)|((9021&255)<<8));
    int rc=sceNetConnect(socket,(const OrbisNetSockaddr *)&address,sizeof(address));
    if(rc<0 && net_error()!=-36)goto done;
    if(rc<0){
        int error=0;unsigned bytes=sizeof(error);
        if(wait_socket(socket,4,2000) || sceNetGetsockopt(socket,0xffff,0x1007,&error,&bytes) || error)goto done;
    }
    const char *query="ODI?";
    for(unsigned offset=0;offset<4;){
        if(wait_socket(socket,4,1000))goto done;
        int n=sceNetSend(socket,query+offset,4-offset,0x20000);if(n<=0)goto done;offset+=(unsigned)n;
    }
    sceNetShutdown(socket,1);
    for(unsigned tries=0;tries<5 && used<sizeof(response)-1;tries++){
        if(wait_socket(socket,1,500))continue;
        int n=sceNetRecv(socket,response+used,sizeof(response)-1-used,0);
        if(n<=0)break;
        used+=(unsigned)n;response[used]=0;if(strchr(response,'\n'))break;
    }
    char path[224];snprintf(path,sizeof(path),"%s/loader-identity.json",directory);
    FILE *file=fopen(path,"wb");if(file){fwrite(response,1,used,file);fflush(file);fsync(fileno(file));fclose(file);}
    result=strstr(response,"\"service\":\"orbisdesk-loader\"") && strstr(response,"\"protocol\":1,") &&
           strstr(response,"\"build\":\"P011\"") && strstr(response,"\"recipe\":\"" PW_EXPECTED_LOADER_RECIPE "\"");
    const char *pid=strstr(response,"\"pid\":");
    if(pid)note("loader_identity_pid",strtol(pid+6,NULL,10));
    note("loader_recipe_matched",result);
done:
    sceNetSocketClose(socket);if(!result)note("loader_identity_rejected",1);return result;
}
