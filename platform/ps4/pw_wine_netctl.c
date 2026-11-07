/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Phase 8: two Unix sides built from the console's network settings (libSceNetCtl), linked
 * into the ELF by tools/build-unixlibs-ps4.py and found by platform/ps4/pw_wine_unixlibs.c:
 *
 * dnsapi.so  Wine's dnsapi has no Unix side here (all of dlls/dnsapi/libresolv.c needs
 *            libresolv). This one keeps its four calls and their parameters:
 *            - get_serverlist: the console's primary and secondary DNS (IPv4 only), or the
 *              list a caller set with set_serverlist;
 *            - get_searchlist: empty (the console has no search domain setting);
 *            - query: a real DNS question over UDP to those servers (2 s, 2 tries each), the
 *              answer returned as it came, for dnsapi's own parser. No TCP: a truncated answer
 *              is returned with its TC bit and a trace line; DNS_QUERY_USE_TCP_ONLY fails.
 * nsi.so     one call, pw_netctl_get_info (pw_netctl_info.h), for the hardware nsi.dll
 *            (tools/build-nsi-hw.py), which has no nsiproxy.sys to ask.
 *
 * libSceNetCtl is loaded at run time and resolved by name, as native/hw_pad.c does for the mouse
 * and keyboard, so the ELF keeps the same imports; a console where it cannot be loaded gets
 * errors with a trace line, never invented settings. */
#include "config.h"
#include <stdarg.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>
#include <time.h>
#include <errno.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <netinet/in.h>
#include <arpa/inet.h>

#include "ntstatus.h"
#define WIN32_NO_STATUS
#include "windef.h"
#include "winternl.h"
#include "winbase.h"
#include "windns.h"
#define USE_WS_PREFIX
#include "ws2def.h"
#include "ws2ipdef.h"

#include "wine/debug.h"
#include "dnsapi.h"
#include "pw_netctl_info.h"

#define EXPORTED __attribute__((visibility("default")))

unsigned int sceKernelLoadStartModule(const char *,size_t,const void *,unsigned int,void *,void *);
int sceKernelDlsym(int,const char *,void **);
const char *sceKernelGetFsSandboxRandomWord(void);

/* libSceNetCtl's items (orbis/NetCtl.h) */
enum {NETCTL_DEVICE=1,NETCTL_ETHER_ADDR=2,NETCTL_MTU=3,NETCTL_LINK=4,NETCTL_IP_ADDRESS=14,NETCTL_NETMASK=15,
      NETCTL_DEFAULT_ROUTE=16,NETCTL_PRIMARY_DNS=17,NETCTL_SECONDARY_DNS=18};
union netctl_value {unsigned int number;unsigned char ether[6];char text[256];};

static int (*netctl_init)(void);
static int (*netctl_get)(int,union netctl_value *);
static int netctl_load_rc;
static pthread_once_t netctl_once=PTHREAD_ONCE_INIT;

static void netctl_load(void)
{
    /* W030: the system libraries are under the sandbox's random word */
    const char *word=sceKernelGetFsSandboxRandomWord();
    char dirs[3][64],path[128];
    int module=-1,rc_init,rc_get;
    snprintf(dirs[0],sizeof(dirs[0]),"/%s/common/lib/",word?word:"system");
    snprintf(dirs[1],sizeof(dirs[1]),"/%s/priv/lib/",word?word:"system");
    snprintf(dirs[2],sizeof(dirs[2]),"/system/common/lib/");
    for(unsigned i=0;i<3 && module<0;i++) {
        snprintf(path,sizeof(path),"%slibSceNetCtl.sprx",dirs[i]);
        module=(int)sceKernelLoadStartModule(path,0,NULL,0,NULL,NULL);
    }
    rc_init=module<0?-1:sceKernelDlsym(module,"sceNetCtlInit",(void **)&netctl_init);
    rc_get=module<0?-1:sceKernelDlsym(module,"sceNetCtlGetInfo",(void **)&netctl_get);
    if(rc_init || rc_get || !netctl_init || !netctl_get) {netctl_init=NULL;netctl_get=NULL;}
    netctl_load_rc=module<0?module:netctl_get?0:-1;
    fprintf(stderr,"PWNET netctl module=0x%08x path=%s init_sym=0x%08x get_sym=0x%08x\n",
            (unsigned)module,path,(unsigned)rc_init,(unsigned)rc_get);
}

static void read_address(int item,int *rc,unsigned char out[4])
{
    union netctl_value value;
    memset(&value,0,sizeof(value));memset(out,0,4);
    if((*rc=netctl_get(item,&value))) return;
    value.text[sizeof(value.text)-1]=0;
    if(inet_pton(AF_INET,value.text,out)!=1) {memset(out,0,4);*rc=-2;}
}

/* 0 when libSceNetCtl answered; the items each keep their own return code */
static int netctl_read(struct pw_netctl_info *info)
{
    static int reported;
    union netctl_value value;
    memset(info,0,sizeof(*info));
    pthread_once(&netctl_once,netctl_load);
    if(!netctl_get) {info->init_rc=netctl_load_rc?netctl_load_rc:-1;return -1;}
    info->init_rc=netctl_init();   /* an "already initialised" code leaves GetInfo working */
    memset(&value,0,sizeof(value));if(!(info->device_rc=netctl_get(NETCTL_DEVICE,&value))) info->device=value.number;
    memset(&value,0,sizeof(value));if(!(info->mac_rc=netctl_get(NETCTL_ETHER_ADDR,&value))) memcpy(info->mac,value.ether,6);
    memset(&value,0,sizeof(value));if(!(info->mtu_rc=netctl_get(NETCTL_MTU,&value))) info->mtu=value.number;
    memset(&value,0,sizeof(value));if(!(info->link_rc=netctl_get(NETCTL_LINK,&value))) info->link=value.number;
    read_address(NETCTL_IP_ADDRESS,&info->ip_rc,info->ip);
    read_address(NETCTL_NETMASK,&info->netmask_rc,info->netmask);
    read_address(NETCTL_DEFAULT_ROUTE,&info->route_rc,info->route);
    read_address(NETCTL_PRIMARY_DNS,&info->dns1_rc,info->dns1);
    read_address(NETCTL_SECONDARY_DNS,&info->dns2_rc,info->dns2);
    if(!reported++)
        fprintf(stderr,"PWNET netctl init=0x%08x device=%u/0x%08x link=%u/0x%08x mtu=%u ip=%u.%u.%u.%u/0x%08x "
                "mask=%u.%u.%u.%u route=%u.%u.%u.%u/0x%08x dns=%u.%u.%u.%u/0x%08x,%u.%u.%u.%u/0x%08x\n",
                (unsigned)info->init_rc,info->device,(unsigned)info->device_rc,info->link,(unsigned)info->link_rc,info->mtu,
                info->ip[0],info->ip[1],info->ip[2],info->ip[3],(unsigned)info->ip_rc,
                info->netmask[0],info->netmask[1],info->netmask[2],info->netmask[3],
                info->route[0],info->route[1],info->route[2],info->route[3],(unsigned)info->route_rc,
                info->dns1[0],info->dns1[1],info->dns1[2],info->dns1[3],(unsigned)info->dns1_rc,
                info->dns2[0],info->dns2[1],info->dns2[2],info->dns2[3],(unsigned)info->dns2_rc);
    return 0;
}

/* nsi.so */
static NTSTATUS nsi_get_info(void *args)
{
    return netctl_read(args)?STATUS_NOT_SUPPORTED:STATUS_SUCCESS;
}
EXPORTED const unixlib_entry_t pw_nsi_unix_call_funcs[]={nsi_get_info};
/* struct pw_netctl_info has no pointers: one layout for both callers */
EXPORTED const unixlib_entry_t pw_nsi_unix_call_wow64_funcs[]={nsi_get_info};

/* dnsapi.so: the servers queries go to. MAX_SERVERS is libresolv's MAXNS. */
#define MAX_SERVERS 3
static pthread_mutex_t servers_lock=PTHREAD_MUTEX_INITIALIZER;
static unsigned int servers[MAX_SERVERS],server_count;  /* network order */
static int servers_set;  /* by set_serverlist, which replaces the console's for the process */

static unsigned int current_servers(unsigned int out[MAX_SERVERS])
{
    unsigned int count;
    pthread_mutex_lock(&servers_lock);
    if(!servers_set) {
        struct pw_netctl_info info;
        server_count=0;
        if(!netctl_read(&info)) {
            if(!info.dns1_rc && memcmp(info.dns1,"\0\0\0\0",4)) memcpy(&servers[server_count++],info.dns1,4);
            if(!info.dns2_rc && memcmp(info.dns2,"\0\0\0\0",4) && memcmp(info.dns2,info.dns1,4)) memcpy(&servers[server_count++],info.dns2,4);
        }
    }
    count=server_count;memcpy(out,servers,sizeof(servers));
    pthread_mutex_unlock(&servers_lock);
    if(!count) fprintf(stderr,"PWNET dnsapi no_servers set=%d\n",servers_set);
    return count;
}

static NTSTATUS resolv_get_searchlist(void *args)
{
    const struct get_searchlist_params *params=args;
    DWORD needed=sizeof(WCHAR);   /* the terminator alone: no search domains */
    if(!params->list || *params->len<needed) {
        *params->len=needed;
        return !params->list?ERROR_SUCCESS:ERROR_MORE_DATA;
    }
    *params->len=needed;
    params->list[0]=0;
    return ERROR_SUCCESS;
}

static NTSTATUS resolv_get_serverlist(void *args)
{
    const struct get_serverlist_params *params=args;
    DNS_ADDR_ARRAY *addrs=params->addrs;
    unsigned int list[MAX_SERVERS],count=current_servers(list);
    DWORD needed;
    if(!count) return DNS_ERROR_NO_DNS_SERVERS;
    if(!addrs && params->family!=WS_AF_INET && params->family!=WS_AF_INET6) {
        *params->len=FIELD_OFFSET(DNS_ADDR_ARRAY,AddrArray[count]);
        return ERROR_SUCCESS;
    }
    if(params->family==WS_AF_INET6) return DNS_ERROR_NO_DNS_SERVERS;  /* the console gives IPv4 servers */
    needed=FIELD_OFFSET(DNS_ADDR_ARRAY,AddrArray[count]);
    if(!addrs || *params->len<needed) {
        *params->len=needed;
        return !addrs?ERROR_SUCCESS:ERROR_MORE_DATA;
    }
    *params->len=needed;
    memset(addrs,0,needed);
    addrs->AddrCount=addrs->MaxCount=count;
    for(unsigned int i=0;i<count;i++) {
        SOCKADDR_IN *sa=(SOCKADDR_IN *)addrs->AddrArray[i].MaxSa;
        sa->sin_family=WS_AF_INET;
        sa->sin_addr.WS_s_addr=list[i];
        addrs->AddrArray[i].Data.DnsAddrUserDword[0]=sizeof(*sa);
    }
    return ERROR_SUCCESS;
}

static NTSTATUS resolv_set_serverlist(void *args)
{
    const IP4_ARRAY *addrs=args;
    if(!addrs || !addrs->AddrCount) return ERROR_SUCCESS;   /* as libresolv: the list stays */
    pthread_mutex_lock(&servers_lock);
    server_count=addrs->AddrCount>MAX_SERVERS?MAX_SERVERS:addrs->AddrCount;
    for(unsigned int i=0;i<server_count;i++) servers[i]=addrs->AddrArray[i];
    servers_set=1;
    pthread_mutex_unlock(&servers_lock);
    return ERROR_SUCCESS;
}

/* A DNS question (RFC 1035 4.1): header, name as labels, type, class IN. */
static int make_question(const char *name,WORD type,int recurse,unsigned short id,unsigned char *buffer,int size)
{
    int n=12;
    const char *label=name;
    if(size<12+2+4) return -1;
    memset(buffer,0,12);
    buffer[0]=id>>8;buffer[1]=id&0xff;
    buffer[2]=recurse?0x01:0x00;
    buffer[5]=1;
    while(*label) {
        const char *dot=strchr(label,'.');
        int length=dot?(int)(dot-label):(int)strlen(label);
        if(length<1 || length>63 || n+1+length+5>size) return -1;
        buffer[n++]=(unsigned char)length;
        memcpy(buffer+n,label,length);n+=length;
        label+=length;
        if(dot) label++;
    }
    buffer[n++]=0;
    buffer[n++]=type>>8;buffer[n++]=type&0xff;
    buffer[n++]=0;buffer[n++]=1;
    return n;
}

static NTSTATUS resolv_query(void *args)
{
    const struct query_params *params=args;
    unsigned char question[300];
    unsigned int list[MAX_SERVERS],count;
    static unsigned short next_id;
    unsigned short id;
    int length,s,last_errno=0;
    struct timeval wait={2,0};

    if(params->options&DNS_QUERY_USE_TCP_ONLY) {
        fprintf(stderr,"PWNET dnsapi query name=%s tcp_only_unsupported\n",params->name);
        return ERROR_NOT_SUPPORTED;
    }
    if(!(count=current_servers(list))) return DNS_ERROR_NO_DNS_SERVERS;
    id=(unsigned short)(time(NULL)*2654435761u)^++next_id;
    if((length=make_question(params->name,params->type,!(params->options&DNS_QUERY_NO_RECURSION),id,question,sizeof(question)))<0)
        return ERROR_INVALID_NAME;
    if((s=socket(AF_INET,SOCK_DGRAM,0))<0) {
        fprintf(stderr,"PWNET dnsapi socket errno=%d\n",errno);
        return DNS_ERROR_RCODE_SERVER_FAILURE;
    }
    setsockopt(s,SOL_SOCKET,SO_RCVTIMEO,&wait,sizeof(wait));
    for(unsigned int attempt=0;attempt<2*count;attempt++) {
        struct sockaddr_in server={0},from;
        socklen_t from_length;
        unsigned char *reply=params->buf;
        ssize_t received;
        server.sin_len=sizeof(server);server.sin_family=AF_INET;server.sin_port=htons(53);
        server.sin_addr.s_addr=list[attempt%count];
        if(sendto(s,question,length,0,(struct sockaddr *)&server,sizeof(server))!=length) {last_errno=errno;continue;}
        for(;;) {
            from_length=sizeof(from);
            received=recvfrom(s,reply,*params->len,0,(struct sockaddr *)&from,&from_length);
            if(received<0) {last_errno=errno;break;}
            /* only the answer to this question, from the server asked */
            if(received>=12 && reply[0]==(id>>8) && reply[1]==(id&0xff) && from.sin_addr.s_addr==server.sin_addr.s_addr) break;
        }
        if(received<0) continue;
        close(s);
        if(reply[2]&0x02)
            fprintf(stderr,"PWNET dnsapi query name=%s type=%u truncated bytes=%d (no TCP retry)\n",
                    params->name,params->type,(int)received);
        *params->len=(DWORD)received;
        return ERROR_SUCCESS;
    }
    close(s);
    fprintf(stderr,"PWNET dnsapi query name=%s type=%u no_answer servers=%u errno=%d\n",params->name,params->type,count,last_errno);
    return DNS_ERROR_RCODE_SERVER_FAILURE;   /* as libresolv's TRY_AGAIN */
}

EXPORTED const unixlib_entry_t pw_dnsapi_unix_call_funcs[]=
{
    resolv_get_searchlist,
    resolv_get_serverlist,
    resolv_set_serverlist,
    resolv_query,
};
C_ASSERT(ARRAYSIZE(pw_dnsapi_unix_call_funcs)==unix_funcs_count);

typedef ULONG PTR32;

static NTSTATUS wow64_resolv_get_searchlist(void *args)
{
    struct {PTR32 list;PTR32 len;} const *params32=args;
    struct get_searchlist_params params={ULongToPtr(params32->list),ULongToPtr(params32->len)};
    return resolv_get_searchlist(&params);
}

static NTSTATUS wow64_resolv_get_serverlist(void *args)
{
    struct {USHORT family;PTR32 addrs;PTR32 len;} const *params32=args;
    struct get_serverlist_params params={params32->family,ULongToPtr(params32->addrs),ULongToPtr(params32->len)};
    return resolv_get_serverlist(&params);
}

static NTSTATUS wow64_resolv_query(void *args)
{
    struct {PTR32 name;WORD type;DWORD options;PTR32 buf;PTR32 len;} const *params32=args;
    struct query_params params={ULongToPtr(params32->name),params32->type,params32->options,
                                ULongToPtr(params32->buf),ULongToPtr(params32->len)};
    return resolv_query(&params);
}

EXPORTED const unixlib_entry_t pw_dnsapi_unix_call_wow64_funcs[]=
{
    wow64_resolv_get_searchlist,
    wow64_resolv_get_serverlist,
    resolv_set_serverlist,
    wow64_resolv_query,
};
C_ASSERT(ARRAYSIZE(pw_dnsapi_unix_call_wow64_funcs)==unix_funcs_count);
