/* SPDX-License-Identifier: GPL-3.0-or-later */
/* curl 8.22.0's configuration for the Steam client title on the PS4 (OpenOrbis), written by hand:
 * curl's CMake checks link test programs, which a cross build with OpenOrbis can't. Features as
 * the host build of tools/build-steam-deps.py (HTTP(S) and WebSocket over Mbed TLS, no IPv6, no
 * compression, no CA paths of its own), and only what the console's libc and libkernel give:
 *   - no fcntl/ioctl non-blocking: Playden's curl-ps5-native-nonblock.patch sets libSceNet's
 *     SO_NBIO (PLAYDEN_PS5_NATIVE_NONBLOCK), as platform/ps4/pw_wine_net.c does for Wine;
 *   - no getaddrinfo use: musl's resolver has no DNS server on the console; Playden's
 *     native_network.cpp resolves with sceNetResolver and hands curl CURLOPT_RESOLVE entries;
 *   - socket constants the SDK gives with Linux numbers are corrected in orbis_net_fix.h.
 * Every CURL_DISABLE_* here is one the host build has too. S2 01.03 also turned off the proxy,
 * cookies, alt-svc, HSTS, NTLM, Kerberos, Negotiate and AWS: with CURL_DISABLE_PROXY,
 * CURLOPT_PROXY is no option at all (setopt.c), Playden's clients set it (to ""), and every
 * request ended with CURLE_FAILED_INIT before resolving (console log of 2026-11-07). */
#define CURL_OS "ps4"
#define CURL_EXTERN_SYMBOL

#define CURL_DISABLE_DICT 1
#define CURL_DISABLE_FILE 1
#define CURL_DISABLE_FTP 1
#define CURL_DISABLE_GOPHER 1
#define CURL_DISABLE_HTTPSIG 1
#define CURL_DISABLE_IMAP 1
#define CURL_DISABLE_IPFS 1
#define CURL_DISABLE_LDAP 1
#define CURL_DISABLE_LDAPS 1
#define CURL_DISABLE_MQTT 1
#define CURL_DISABLE_NETRC 1
#define CURL_DISABLE_POP3 1
#define CURL_DISABLE_RTSP 1
#define CURL_DISABLE_SMTP 1
#define CURL_DISABLE_SOCKETPAIR 1
#define CURL_DISABLE_TELNET 1
#define CURL_DISABLE_TFTP 1

#define USE_MBEDTLS 1
#define HAVE_MBEDTLS_DES_CRYPT_ECB 1

#define HAVE_ARPA_INET_H 1
#define HAVE_BOOL_T 1
#define HAVE_CLOCK_GETTIME_MONOTONIC 1
#define HAVE_FCNTL_H 1
#define HAVE_FREEADDRINFO 1
#define HAVE_GETADDRINFO 1
#define HAVE_GETPEERNAME 1
#define HAVE_GETSOCKNAME 1
#define HAVE_GETTIMEOFDAY 1
#define HAVE_LOCALE_H 1
#define HAVE_NETDB_H 1
#define HAVE_NETINET_IN_H 1
#define HAVE_NETINET_TCP_H 1
#define HAVE_POLL 1
#define HAVE_POLL_H 1
#define HAVE_RECV 1
#define HAVE_SA_FAMILY_T 1
#define HAVE_SEND 1
#define HAVE_SIGACTION 1
#define HAVE_SIGNAL 1
#define HAVE_SOCKET 1
#define HAVE_STDATOMIC_H 1
#define HAVE_ATOMIC 1
#define HAVE_STDBOOL_H 1
#define HAVE_STRCASECMP 1
#define HAVE_STRINGS_H 1
#define HAVE_STRUCT_SOCKADDR_STORAGE 1
#define HAVE_STRUCT_TIMEVAL 1
#define HAVE_SUSECONDS_T 1
#define HAVE_SYS_PARAM_H 1
#define HAVE_SYS_SELECT_H 1
#define HAVE_SYS_TYPES_H 1
#define HAVE_UNISTD_H 1
#define HAVE_THREADS_POSIX 1

#define SIZEOF_CURL_OFF_T 8
#define SIZEOF_CURL_SOCKET_T 4
#define SIZEOF_INT 4
#define SIZEOF_LONG 8
#define SIZEOF_OFF_T 8
#define SIZEOF_SIZE_T 8
#define SIZEOF_TIME_T 8

#define PLAYDEN_PS5_NATIVE_NONBLOCK 1
#include "orbis_net_fix.h"
