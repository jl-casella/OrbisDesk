/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Entropy for Mbed TLS in the Steam client title (ORBS00001). native/steam/mbedtls_user_config.h
 * turns the library's platform sources off and MBEDTLS_ENTROPY_HARDWARE_ALT on, so every DRBG
 * and PSA's own RNG are seeded from here: /dev/urandom, read whole. A short or failed read
 * returns an error (MBEDTLS_ERR_ENTROPY_SOURCE_FAILED through the library), never made-up bytes.
 * W188 left the console's /dev/urandom unproven for a title; steam_entropy_check logs it. */
#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <string.h>
#include <unistd.h>

#include "steam_tls.h"

static int read_urandom(unsigned char *out,size_t len,int *error)
{
    size_t done=0;
    int fd;

    errno=0;fd=open("/dev/urandom",O_RDONLY);
    if(fd<0) {*error=errno;return -1;}
    while(done<len) {
        ssize_t got=read(fd,out+done,len-done);
        if(got<0 && errno==EINTR) continue;
        if(got<=0) {*error=got<0?errno:EIO;close(fd);return -1;}
        done+=(size_t)got;
    }
    close(fd);*error=0;
    return 0;
}

/* Mbed TLS's hook (entropy_poll.h); data is unused */
int mbedtls_hardware_poll(void *data,unsigned char *output,size_t len,size_t *olen)
{
    int error;

    (void)data;*olen=0;
    if(read_urandom(output,len,&error)) return -1;
    *olen=len;
    return 0;
}

/* Two reads of 32 bytes: both must succeed, neither may be all zeros, and they must differ.
 * Returns 0 when they do; *error is the errno of a failed open or read. */
int steam_entropy_check(int *error,int *zero,int *same)
{
    unsigned char a[32],b[32],none[32]={0};

    *zero=*same=0;
    if(read_urandom(a,sizeof(a),error) || read_urandom(b,sizeof(b),error)) return -1;
    *zero=!memcmp(a,none,sizeof(a)) || !memcmp(b,none,sizeof(b));
    *same=!memcmp(a,b,sizeof(a));
    memset(a,0,sizeof(a));memset(b,0,sizeof(b));
    return *zero || *same ? -1 : 0;
}
