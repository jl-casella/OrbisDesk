/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Phase 8: the resolver calls of ws2_32's Unix side (dlls/ws2_32/unixlib.c), for the console.
 * Adapted from prospero-win's wine/ps5/pw_ws2_32_libc.c (LGPL-2.1-or-later, its contributors;
 * THIRD_PARTY.md): same rules, PS4 names, no host-test hooks.
 *
 * Wine's configure found no getaddrinfo for Orbis (HAVE_GETADDRINFO unset), so every lookup
 * returned an error. The SDK libc is musl: its resolver reads /etc/resolv.conf, which a PS4
 * application does not have, and asks 127.0.0.1. tools/build-unixlibs-ps4.py compiles ws2_32's
 * unixlib.c with HAVE_GETADDRINFO and with these names in place of the libc's (-Dgetaddrinfo=
 * pw_ws2_getaddrinfo and so on), so nothing else in the ELF changes resolver.
 *
 * Answered here without a name server: numeric addresses, the wildcard and loopback, and
 * "localhost" and the local name (PS4), both loopback. A name with a dot goes to the console's
 * resolver (libSceNet, sceNetResolverStartNtoa / Ntoa6) with a fixed timeout and retries. Any
 * other single-label name is EAI_NONAME at once (see prospero-win: a home router that answers
 * for DHCP host names made a game believe it was online). A dotted name that was not found is
 * remembered for 5 s. One address per family, IPv4 first. Services: a port number or one of a
 * few well-known names; any other name is EAI_SERVICE with a trace line. getnameinfo gives
 * numeric hosts only (and "localhost" for loopback): there is no reverse lookup, and a request
 * that needs one (NI_NAMEREQD) fails with EAI_NONAME. */
#include <arpa/inet.h>
#include <errno.h>
#include <netdb.h>
#include <netinet/in.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/socket.h>
#include "pw_trace.h"
#include <time.h>
#include <unistd.h>

int pw_ws2_getaddrinfo(const char *,const char *,const struct addrinfo *,struct addrinfo **);
void pw_ws2_freeaddrinfo(struct addrinfo *);
int pw_ws2_getnameinfo(const struct sockaddr *,socklen_t,char *,socklen_t,char *,socklen_t,int);
struct hostent *pw_ws2_gethostbyname(const char *);
struct hostent *pw_ws2_gethostbyaddr(const void *,socklen_t,int);
int pw_ws2_gethostname(char *,size_t);
int *pw_ws2_h_errno_location(void);

int sceNetInit(void);
int sceNetPoolCreate(const char *name,int size,int flags);
int sceNetPoolDestroy(int pool);
int sceNetResolverCreate(const char *name,int pool,int flags);
int sceNetResolverDestroy(int resolver);
int sceNetResolverStartNtoa(int resolver,const char *name,struct in_addr *address,int timeout_us,int retries,int flags);
int sceNetResolverStartNtoa6(int resolver,const char *name,struct in6_addr *address,int timeout_us,int retries,int flags);

static _Thread_local int h_errno_value;
int *pw_ws2_h_errno_location(void) {return &h_errno_value;}

struct address {int family;unsigned char bytes[16];};

/* One question waits 5 s and is asked 2 more times: an A lookup ends within 15 s; AAAA is asked
 * only when IPv6 was requested or there was no A. */
#define RESOLVE_TIMEOUT_US 5000000
#define RESOLVE_RETRIES 2
#define NEGATIVE_SECONDS 5

static int console_resolve(const char *name,int family,struct address answers[2],int *count)
{
    int pool,resolver,found=0,rc4=0,rc6=0;
    *count=0;
    sceNetInit();   /* once is enough; later calls return an error that changes nothing */
    if((pool=sceNetPoolCreate("orbisdesk-dns",0x4000,0))<0) {
        fprintf(stderr,"PWNET resolver pool_create rc=0x%08x\n",(unsigned)pool);return EAI_FAIL;
    }
    if((resolver=sceNetResolverCreate("orbisdesk-dns",pool,0))<0) {
        fprintf(stderr,"PWNET resolver create rc=0x%08x\n",(unsigned)resolver);
        sceNetPoolDestroy(pool);return EAI_FAIL;
    }
    if(family!=AF_INET6) {
        struct in_addr address;
        if((rc4=sceNetResolverStartNtoa(resolver,name,&address,RESOLVE_TIMEOUT_US,RESOLVE_RETRIES,0))>=0) {
            answers[found].family=AF_INET;memcpy(answers[found].bytes,&address,sizeof(address));found++;
        }
    }
    if(family!=AF_INET && !found) {
        struct in6_addr address;
        if((rc6=sceNetResolverStartNtoa6(resolver,name,&address,RESOLVE_TIMEOUT_US,RESOLVE_RETRIES,0))>=0) {
            answers[found].family=AF_INET6;memcpy(answers[found].bytes,&address,sizeof(address));found++;
        }
    }
    sceNetResolverDestroy(resolver);sceNetPoolDestroy(pool);
    /* alpha-1: a line per lookup (browsers, Steam); failures always, the rest with traces (pw_trace.h) */
    if(!found || pw_trace_on()) fprintf(stderr,"PWNET resolve name=%s family=%d found=%d rc4=0x%08x rc6=0x%08x\n",name,family,found,(unsigned)rc4,(unsigned)rc6);
    *count=found;
    return found?0:EAI_NONAME;
}

/* The SDK's CLOCK_MONOTONIC is Linux's number (1), FreeBSD's CLOCK_VIRTUAL on the console (W048);
 * CLOCK_REALTIME is the same on both, and a clock step only shortens or lengthens one 5 s entry. */
static long long now_seconds(void)
{
    return (long long)time(NULL);
}

#define NEGATIVE_SLOTS 16
static struct {char name[256];int family;long long until;} negatives[NEGATIVE_SLOTS];
static unsigned negative_next;
static pthread_mutex_t negative_lock=PTHREAD_MUTEX_INITIALIZER;

static int negative_known(const char *name,int family)
{
    long long now=now_seconds();int known=0;
    pthread_mutex_lock(&negative_lock);
    for(unsigned i=0;i<NEGATIVE_SLOTS && !known;i++)
        known=negatives[i].until>now && negatives[i].family==family && !strcasecmp(negatives[i].name,name);
    pthread_mutex_unlock(&negative_lock);
    return known;
}

static void negative_remember(const char *name,int family)
{
    unsigned slot;
    if(strlen(name)>=sizeof(negatives[0].name)) return;
    pthread_mutex_lock(&negative_lock);
    slot=negative_next++%NEGATIVE_SLOTS;
    strcpy(negatives[slot].name,name);negatives[slot].family=family;negatives[slot].until=now_seconds()+NEGATIVE_SECONDS;
    pthread_mutex_unlock(&negative_lock);
}

struct entry {struct addrinfo info;struct sockaddr_storage address;char name[];};

static socklen_t make_sockaddr(struct sockaddr_storage *storage,const struct address *address,unsigned short port)
{
    memset(storage,0,sizeof(*storage));
    if(address->family==AF_INET) {
        struct sockaddr_in *in=(struct sockaddr_in *)storage;
        in->sin_len=sizeof(*in);in->sin_family=AF_INET;in->sin_port=htons(port);
        memcpy(&in->sin_addr,address->bytes,sizeof(in->sin_addr));
        return sizeof(*in);
    } else {
        struct sockaddr_in6 *in6=(struct sockaddr_in6 *)storage;
        in6->sin6_len=sizeof(*in6);in6->sin6_family=AF_INET6;in6->sin6_port=htons(port);
        memcpy(&in6->sin6_addr,address->bytes,sizeof(in6->sin6_addr));
        return sizeof(*in6);
    }
}

/* A stable local name: the libc's may be empty, and Wine would then use the prefix's PC name,
 * which nothing here resolves. Winsock and this resolver agree on it. */
static const char local_name[]="PS4";

int pw_ws2_gethostname(char *name,size_t size)
{
    if(size<sizeof(local_name)) {errno=ENAMETOOLONG;return -1;}
    memcpy(name,local_name,sizeof(local_name));
    return 0;
}

static int is_local_name(const char *name) {return !strcasecmp(name,"localhost") || !strcasecmp(name,local_name);}

static int lookup(const char *node,int family,int flags,struct address addresses[2],int *count)
{
    int wildcard=!node && (flags&AI_PASSIVE);
    memset(addresses,0,2*sizeof(*addresses));
    *count=1;
    if(node) {
        if(family!=AF_INET6 && inet_pton(AF_INET,node,addresses[0].bytes)==1) {addresses[0].family=AF_INET;return 0;}
        if(family!=AF_INET && inet_pton(AF_INET6,node,addresses[0].bytes)==1) {addresses[0].family=AF_INET6;return 0;}
        if(flags&AI_NUMERICHOST) return EAI_NONAME;
        if(!is_local_name(node)) {
            int error;
            if(!*node || !strchr(node,'.')) return EAI_NONAME;
            if(negative_known(node,family)) return EAI_NONAME;
            if((error=console_resolve(node,family,addresses,count)) || !*count) {
                if(!error || error==EAI_NONAME) negative_remember(node,family);
                return error?error:EAI_NONAME;
            }
            return 0;
        }
    }
    *count=0;
    if(family!=AF_INET6) {
        addresses[*count].family=AF_INET;
        if(!wildcard) {addresses[*count].bytes[0]=127;addresses[*count].bytes[3]=1;}
        ++*count;
    }
    if(family!=AF_INET) {
        addresses[*count].family=AF_INET6;
        if(!wildcard) addresses[*count].bytes[15]=1;
        ++*count;
    }
    return 0;
}

static const struct {const char *name;unsigned short port;} services[]={
    {"ftp",21},{"ssh",22},{"telnet",23},{"smtp",25},{"domain",53},{"http",80},{"www",80},{"pop3",110},
    {"ntp",123},{"imap",143},{"https",443},{"imaps",993},{"pop3s",995}};

static int service_port(const char *service,int flags,unsigned short *port)
{
    char *end;
    *port=0;
    if(!service) return 0;
    if(service[0]>='0' && service[0]<='9') {
        unsigned long value=strtoul(service,&end,10);
        if(!*end && value<=65535) {*port=(unsigned short)value;return 0;}
    }
    if(flags&AI_NUMERICSERV) return EAI_NONAME;
    for(unsigned i=0;i<sizeof(services)/sizeof(services[0]);i++)
        if(!strcasecmp(service,services[i].name)) {*port=services[i].port;return 0;}
    fprintf(stderr,"PWNET getaddrinfo service=%s not_in_table\n",service);
    return EAI_SERVICE;
}

void pw_ws2_freeaddrinfo(struct addrinfo *info)
{
    while(info) {struct addrinfo *next=info->ai_next;free(info);info=next;}
}

int pw_ws2_getaddrinfo(const char *node,const char *service,const struct addrinfo *hints,struct addrinfo **result)
{
    static const struct addrinfo no_hints;
    struct {int socktype,protocol;} kinds[2];
    struct address addresses[2];
    struct addrinfo *head=NULL,**tail=&head;
    unsigned short port;
    int count,kind_count=0,error;

    *result=NULL;
    if(!hints) hints=&no_hints;
    if(!node && !service) return EAI_NONAME;
    if(hints->ai_family!=AF_UNSPEC && hints->ai_family!=AF_INET && hints->ai_family!=AF_INET6) return EAI_FAMILY;
    if(!node && (hints->ai_flags&AI_CANONNAME)) return EAI_BADFLAGS;
    /* One answer per address and socket type: TCP and UDP when neither is given. */
    if(hints->ai_socktype==SOCK_STREAM || hints->ai_socktype==SOCK_DGRAM || hints->ai_socktype==SOCK_RAW) {
        int protocol=hints->ai_protocol?hints->ai_protocol:hints->ai_socktype==SOCK_STREAM?IPPROTO_TCP:
                     hints->ai_socktype==SOCK_DGRAM?IPPROTO_UDP:0;
        kinds[kind_count].socktype=hints->ai_socktype;kinds[kind_count++].protocol=protocol;
    } else if(hints->ai_socktype) return EAI_SOCKTYPE;
    else {
        if(!hints->ai_protocol || hints->ai_protocol==IPPROTO_TCP) {kinds[kind_count].socktype=SOCK_STREAM;kinds[kind_count++].protocol=IPPROTO_TCP;}
        if(!hints->ai_protocol || hints->ai_protocol==IPPROTO_UDP) {kinds[kind_count].socktype=SOCK_DGRAM;kinds[kind_count++].protocol=IPPROTO_UDP;}
        if(!kind_count) {kinds[kind_count].socktype=SOCK_RAW;kinds[kind_count++].protocol=hints->ai_protocol;}
    }
    if((error=service_port(service,hints->ai_flags,&port))) return error;
    if((error=lookup(node,hints->ai_family,hints->ai_flags,addresses,&count))) return error;
    for(int a=0;a<count;a++) for(int k=0;k<kind_count;k++) {
        /* The canonical name, the name as given, goes on the first. */
        size_t name_size=head || !(hints->ai_flags&AI_CANONNAME)?0:strlen(node)+1;
        struct entry *entry=calloc(1,sizeof(*entry)+name_size);
        if(!entry) {pw_ws2_freeaddrinfo(head);return EAI_MEMORY;}
        entry->info.ai_flags=hints->ai_flags;
        entry->info.ai_family=addresses[a].family;
        entry->info.ai_socktype=kinds[k].socktype;
        entry->info.ai_protocol=kinds[k].protocol;
        entry->info.ai_addrlen=make_sockaddr(&entry->address,&addresses[a],port);
        entry->info.ai_addr=(struct sockaddr *)&entry->address;
        if(name_size) {memcpy(entry->name,node,name_size);entry->info.ai_canonname=entry->name;}
        *tail=&entry->info;tail=&entry->info.ai_next;
    }
    *result=head;
    return 0;
}

int pw_ws2_getnameinfo(const struct sockaddr *address,socklen_t length,char *host,socklen_t host_size,
                       char *service,socklen_t service_size,int flags)
{
    const void *bytes;unsigned short port;int loopback;
    if(!address) return EAI_FAMILY;
    if(address->sa_family==AF_INET && length>=sizeof(struct sockaddr_in)) {
        const struct sockaddr_in *in=(const struct sockaddr_in *)address;
        bytes=&in->sin_addr;port=ntohs(in->sin_port);loopback=((const unsigned char *)bytes)[0]==127;
    } else if(address->sa_family==AF_INET6 && length>=sizeof(struct sockaddr_in6)) {
        static const unsigned char one[sizeof(struct in6_addr)]={[15]=1};
        const struct sockaddr_in6 *in6=(const struct sockaddr_in6 *)address;
        bytes=&in6->sin6_addr;port=ntohs(in6->sin6_port);loopback=!memcmp(bytes,one,sizeof(one));
    } else return EAI_FAMILY;
    if((!host || !host_size) && (!service || !service_size)) return EAI_NONAME;
    if(host && host_size) {
        if(!(flags&NI_NUMERICHOST) && loopback) {
            if(strlen("localhost")>=host_size) return EAI_OVERFLOW;
            strcpy(host,"localhost");
        } else if(flags&NI_NAMEREQD) {
            fprintf(stderr,"PWNET getnameinfo reverse_lookup_unsupported\n");
            return EAI_NONAME;
        } else if(!inet_ntop(address->sa_family,bytes,host,host_size)) return EAI_OVERFLOW;
    }
    if(service && service_size && (size_t)snprintf(service,service_size,"%u",port)>=service_size) return EAI_OVERFLOW;
    return 0;
}

/* The old resolver's single answer, in per-thread storage. */
static struct hostent *make_hostent(const char *name,int family,const void *address,int length)
{
    static _Thread_local struct hostent host;
    static _Thread_local char host_name[NI_MAXHOST];
    static _Thread_local char addresses[1][sizeof(struct in6_addr)];
    static _Thread_local char *address_list[2],*aliases[1];
    snprintf(host_name,sizeof(host_name),"%s",name);
    memcpy(addresses[0],address,length);
    address_list[0]=addresses[0];address_list[1]=NULL;aliases[0]=NULL;
    host.h_name=host_name;host.h_aliases=aliases;host.h_addrtype=family;host.h_length=length;host.h_addr_list=address_list;
    return &host;
}

struct hostent *pw_ws2_gethostbyname(const char *name)
{
    struct addrinfo hints={0},*info;struct hostent *host;
    hints.ai_family=AF_INET;hints.ai_socktype=SOCK_STREAM;hints.ai_flags=AI_CANONNAME;
    if(!name || pw_ws2_getaddrinfo(name,NULL,&hints,&info)) {h_errno_value=HOST_NOT_FOUND;return NULL;}
    host=make_hostent(info->ai_canonname,AF_INET,&((struct sockaddr_in *)info->ai_addr)->sin_addr,sizeof(struct in_addr));
    pw_ws2_freeaddrinfo(info);
    return host;
}

struct hostent *pw_ws2_gethostbyaddr(const void *address,socklen_t length,int family)
{
    struct sockaddr_storage storage={0};
    struct address answer={family,{0}};
    char name[NI_MAXHOST];
    socklen_t size;
    if((family!=AF_INET || length!=sizeof(struct in_addr)) && (family!=AF_INET6 || length!=sizeof(struct in6_addr))) {
        h_errno_value=NO_RECOVERY;return NULL;
    }
    memcpy(answer.bytes,address,length);
    size=make_sockaddr(&storage,&answer,0);
    if(pw_ws2_getnameinfo((struct sockaddr *)&storage,size,name,sizeof(name),NULL,0,NI_NAMEREQD)) {
        h_errno_value=HOST_NOT_FOUND;return NULL;
    }
    return make_hostent(name,family,address,(int)length);
}
