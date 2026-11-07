/* SPDX-License-Identifier: GPL-3.0-or-later */
/* The OpenOrbis SDK's headers give some socket constants with Linux's numbers, while the PS4
 * kernel is FreeBSD's (docs W188: Linux's TCP_KEEPIDLE, 4, is FreeBSD's TCP_NOPUSH, and the TLS
 * ClientHello never left). For the Steam client's own code (curl, Playden's backend) these are
 * replaced by FreeBSD's values; SOL_SOCKET, SO_* and O_NONBLOCK already are FreeBSD's.
 * Wine's side does the same at its edge with the kernel (platform/ps4/pw_wine_sockopt.c). */
#pragma once
#include <sys/socket.h>
#include <netinet/in.h>
#include <netinet/tcp.h>

/* Linux only (and SOL_IP with it): FreeBSD has no such option */
#undef IP_BIND_ADDRESS_NO_PORT

#undef MSG_DONTWAIT
#define MSG_DONTWAIT 0x80
#undef MSG_NOSIGNAL
#define MSG_NOSIGNAL 0x20000
#undef MSG_WAITALL
#define MSG_WAITALL 0x40
/* no socket(2) type flags on this kernel's FreeBSD 9 base: curl then sets them after creating */
#undef SOCK_NONBLOCK
#undef SOCK_CLOEXEC
#undef TCP_KEEPIDLE
#define TCP_KEEPIDLE 0x100
#undef TCP_KEEPINTVL
#define TCP_KEEPINTVL 0x200
#undef TCP_KEEPCNT
#define TCP_KEEPCNT 0x400
