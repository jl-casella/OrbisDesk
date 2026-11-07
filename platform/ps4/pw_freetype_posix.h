/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_FREETYPE_POSIX_H
#define PW_FREETYPE_POSIX_H
#include <fcntl.h>
#include <unistd.h>
#include "pw_wine_fs.h"
#include "pw_wine_platform.h"
/* Use the same real Orbis file metadata service as Wine, not libc's _fstat. */
#define fstat(fd,buffer) pw_wine_fstat(fd,buffer)
/* win32u hands FreeType paths under dosdevices/c:, which on the PS4 is Wine's fixed
 * mount table rather than a symbolic link (W024: tahoma.ttf failed with err 1). */
#define open(...) pw_wine_open(0,__VA_ARGS__)
#endif
