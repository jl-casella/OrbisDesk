/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <sys/uio.h>
#include <unistd.h>

static unsigned long chunks_written;
static unsigned int requests_logged;

unsigned long pw_wine_request_chunks_written(void);
unsigned long pw_wine_request_chunks_written(void)
{
    return __atomic_load_n(&chunks_written, __ATOMIC_RELAXED);
}

ssize_t pw_wine_request_writev(int fd, const struct iovec *iov, int count);
ssize_t pw_wine_request_writev(int fd, const struct iovec *iov, int count)
{
    /* Keep writes to the request pipe small. Wine advances the vectors by the
     * count returned and calls us again. Pass the original buffer to the kernel. */
    const struct iovec *part = NULL;
    size_t total = 0;
    for(int i = 0; i < count; ++i){
        total += iov[i].iov_len;
        if(!part && iov[i].iov_len) part = &iov[i];
    }
    if(!part) return 0;

    size_t chunk = part->iov_len > _POSIX_PIPE_BUF ? _POSIX_PIPE_BUF : part->iov_len;
    if(part == iov && total > _POSIX_PIPE_BUF && part->iov_len >= sizeof(int) &&
       __atomic_fetch_add(&requests_logged, 1, __ATOMIC_RELAXED) < 32){
        int code;
        memcpy(&code, part->iov_base, sizeof(code));
        fprintf(stderr, "PWIPC request_chunked fd=%d req=%d total=%zu chunk_limit=%d\n",
                fd, code, total, _POSIX_PIPE_BUF);
    }

    ssize_t written;
    do written = write(fd, part->iov_base, chunk); while(written < 0 && errno == EINTR);
    if(!written){
        errno = EIO;
        return -1;
    }
    if(written > 0) __atomic_add_fetch(&chunks_written, 1, __ATOMIC_RELAXED);
    return written;
}
