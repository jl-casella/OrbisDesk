/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Host-only adapter regression: synthetic kernel replies, never console IPC evidence. */
#ifndef PROBE_NET_SOURCE
#define PROBE_NET_SOURCE "../platform/ps4/pw_wine_net.c"
#endif
#include PROBE_NET_SOURCE
static int reply_flags,reply_error;
static unsigned reply_control;
int sceKernelDebugOutText(int channel,const char *text) {(void)channel;(void)text;return 0;}
ssize_t kernel_recvmsg(int fd,PwMessage *message,int flags)
{
    (void)fd;(void)flags;
    if(reply_error){errno=reply_error;return -1;}
    message->flags=reply_flags;message->controllen=reply_control;return 1;
}
#define CHECK(condition) do {if(!(condition)){fprintf(stderr,"failed at line %d: %s\n",__LINE__,#condition);return 1;}}while(0)
int main(void)
{
    struct msghdr message;memset(&message,0,sizeof(message));
    reply_flags=KERNEL_MSG_DONTWAIT;
    CHECK(pw_wine_recvmsg(99,&message,MSG_DONTWAIT)==1);
    CHECK(message.msg_flags==0);
    CHECK(pw_wine_recvmsg(99,&message,0)==-1 && errno==ENOTSUP);
    reply_flags=KERNEL_MSG_DONTWAIT|KERNEL_MSG_TRUNC;
    CHECK(pw_wine_recvmsg(99,&message,MSG_DONTWAIT)==1);
    CHECK(message.msg_flags==MSG_TRUNC);
    reply_flags=KERNEL_MSG_DONTWAIT|0x4000;
    CHECK(pw_wine_recvmsg(99,&message,MSG_DONTWAIT)==-1 && errno==ENOTSUP);
    reply_error=EAGAIN;
    CHECK(pw_wine_recvmsg(99,&message,MSG_DONTWAIT)==-1 && errno==EAGAIN);
    reply_error=0;reply_flags=0;reply_control=8;
    CHECK(pw_wine_recvmsg(99,&message,0)==-1 && errno==ENOTSUP);
    puts("recvmsg flag contracts passed");return 0;
}
