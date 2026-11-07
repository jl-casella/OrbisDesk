/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include <errno.h>
#include <stdio.h>
#include <sys/socket.h>
#include <orbis/libkernel.h>
/* W188: socket option numbers. The SDK's netinet headers carry Linux's values for the TCP, IP
 * and IPv6 levels, and the console's kernel reads FreeBSD's; the socket level (SOL_SOCKET
 * 0xffff) already matches. Wine's keep-alive values (SIO_KEEPALIVE_VALS) set TCP_KEEPIDLE, 4,
 * which is FreeBSD's TCP_NOPUSH: the kernel then held short segments back, and Pale Moon's TLS
 * hello and HTTP requests never left (W186: names resolved, pages blank, no error). The final
 * link wraps setsockopt and getsockopt (tools/build-wine-hardware.py, --wrap) so every caller,
 * ntdll's socket code included, comes here. An option with no FreeBSD equivalent fails with
 * ENOPROTOOPT and a trace instead of reaching a different option. This file is linked only
 * into that final link: elsewhere (ntdll.so, bootstrap) __real_* has nothing to resolve to, and
 * create-fself refuses an unresolved symbol. */
int __real_setsockopt(int,int,int,const void *,socklen_t);
int __real_getsockopt(int,int,int,void *,socklen_t *);
enum {LINUX_IPPROTO_IP=0,LINUX_IPPROTO_TCP=6,LINUX_IPPROTO_IPV6=41};
static int kernel_option(int level,int name)
{
    static const struct {int level,linux_name,kernel_name;} table[]={
        {LINUX_IPPROTO_TCP,1,1},{LINUX_IPPROTO_TCP,2,2},              /* TCP_NODELAY, TCP_MAXSEG */
        {LINUX_IPPROTO_TCP,4,0x100},{LINUX_IPPROTO_TCP,5,0x200},{LINUX_IPPROTO_TCP,6,0x400}, /* KEEPIDLE/INTVL/CNT */
        {LINUX_IPPROTO_IP,1,3},{LINUX_IPPROTO_IP,2,4},{LINUX_IPPROTO_IP,3,2},{LINUX_IPPROTO_IP,4,1}, /* TOS TTL HDRINCL OPTIONS */
        {LINUX_IPPROTO_IP,32,9},{LINUX_IPPROTO_IP,33,10},{LINUX_IPPROTO_IP,34,11}, /* MULTICAST_IF/TTL/LOOP */
        {LINUX_IPPROTO_IP,35,12},{LINUX_IPPROTO_IP,36,13},            /* ADD/DROP_MEMBERSHIP */
        {LINUX_IPPROTO_IP,12,65},{LINUX_IPPROTO_IP,13,68},            /* RECVTTL, RECVTOS */
        {LINUX_IPPROTO_IPV6,16,4},{LINUX_IPPROTO_IPV6,17,9},{LINUX_IPPROTO_IPV6,18,10},{LINUX_IPPROTO_IPV6,19,11},
        {LINUX_IPPROTO_IPV6,20,12},{LINUX_IPPROTO_IPV6,21,13},{LINUX_IPPROTO_IPV6,26,27}, /* JOIN LEAVE V6ONLY */
    };
    if(level!=LINUX_IPPROTO_TCP && level!=LINUX_IPPROTO_IP && level!=LINUX_IPPROTO_IPV6) return name;
    for(unsigned i=0;i<sizeof(table)/sizeof(table[0]);i++)
        if(table[i].level==level && table[i].linux_name==name) return table[i].kernel_name;
    return -1;
}
static int option_unsupported(const char *call,int fd,int level,int name)
{
    static unsigned reported;
    if(reported++<32) {
        char text[128];
        snprintf(text,sizeof(text),"PWNET %s fd=%d level=%d option=%d unsupported\n",call,fd,level,name);
        sceKernelDebugOutText(0,text);
    }
    errno=ENOPROTOOPT;
    return -1;
}
int __wrap_setsockopt(int fd,int level,int name,const void *value,socklen_t length)
{
    int kernel=kernel_option(level,name);
    if(kernel<0) return option_unsupported("setsockopt",fd,level,name);
    return __real_setsockopt(fd,level,kernel,value,length);
}
int __wrap_getsockopt(int fd,int level,int name,void *value,socklen_t *length)
{
    int kernel=kernel_option(level,name);
    if(kernel<0) return option_unsupported("getsockopt",fd,level,name);
    return __real_getsockopt(fd,level,kernel,value,length);
}
