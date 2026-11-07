/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_WINE_NET_H
#define PW_WINE_NET_H
#include <poll.h>
#include <sys/socket.h>
int pw_wine_poll(struct pollfd *,nfds_t,int);
ssize_t pw_wine_sendmsg(int,const struct msghdr *,int);
ssize_t pw_wine_recvmsg(int,struct msghdr *,int);
/* Phase 8: a socket made non-blocking (fcntl, then libSceNet's SO_NBIO); 0 or -1 with errno */
int pw_wine_socket_nonblock(int);
/* Phase 8: the kernel's (FreeBSD's) MSG_* for the SDK's (Linux's) numbers; -1 for one it lacks */
int pw_wine_kernel_msg_flags(int);
#endif
