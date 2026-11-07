/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "pw_wine_fs.h"
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
/* Real host filesystem for the path algorithms; the Orbis stat wire adapter
 * is exercised separately by the native diagnostics, not by these wrappers. */
int pw_wine_stat(const char *p,struct stat *s) {return stat(p,s);}
int pw_wine_lstat(const char *p,struct stat *s) {return lstat(p,s);}
int pw_wine_fstat(int fd,struct stat *s) {return fstat(fd,s);}
int main(void)
{
    char root[]="/tmp/orbisdesk-fs-XXXXXX";assert(mkdtemp(root));
    char client[PATH_MAX],server[PATH_MAX],sub[PATH_MAX],link[PATH_MAX],cycle1[PATH_MAX],cycle2[PATH_MAX];
    snprintf(client,sizeof(client),"%s/client",root);snprintf(server,sizeof(server),"%s/server",root);
    snprintf(sub,sizeof(sub),"%s/server/sub",root);snprintf(link,sizeof(link),"%s/client/link",root);
    snprintf(cycle1,sizeof(cycle1),"%s/client/cycle1",root);snprintf(cycle2,sizeof(cycle2),"%s/client/cycle2",root);
    assert(!mkdir(client,0700) && !mkdir(server,0700) && !mkdir(sub,0700));
    assert(!pw_wine_chdir(0,client) && !pw_wine_chdir(1,server));
    int a=pw_wine_open(0,"file",O_CREAT|O_EXCL|O_RDWR,0600);
    int b=pw_wine_open(1,"file",O_CREAT|O_EXCL|O_RDWR,0600);
    assert(a>=0 && b>=0 && write(a,"c",1)==1 && write(b,"s",1)==1);
    assert(!pw_wine_close(a) && !pw_wine_close(b));
    char cwd[PATH_MAX],resolved[PATH_MAX],expected[PATH_MAX];
    assert(pw_wine_getcwd(0,cwd,sizeof(cwd)) && !strcmp(cwd,client));
    assert(pw_wine_getcwd(1,cwd,sizeof(cwd)) && !strcmp(cwd,server));
    char tiny[]="abc";assert(!pw_wine_getcwd(0,tiny,1) && errno==ERANGE && !strcmp(tiny,"abc"));
    assert(!pw_wine_getcwd(0,NULL,1) && errno==ERANGE);
    char *allocated=pw_wine_getcwd(0,NULL,0);assert(allocated && !strcmp(allocated,client));free(allocated);
    assert(!symlink("../server/sub",link));
    snprintf(expected,sizeof(expected),"%s/server/file",root);
    assert(pw_wine_realpath(0,"link/../file",resolved) && !strcmp(resolved,expected));
    assert(!symlink("cycle2",cycle1) && !symlink("cycle1",cycle2));
    strcpy(resolved,"unchanged");assert(!pw_wine_realpath(0,"cycle1",resolved) && errno==ELOOP && !strcmp(resolved,"unchanged"));
    assert(pw_wine_chdir(0,"missing")==-1 && errno==ENOENT);
    assert(pw_wine_getcwd(0,cwd,sizeof(cwd)) && !strcmp(cwd,client));
    int directory=pw_wine_open(0,"../server",O_RDONLY);assert(directory>=0);
    int copy=pw_wine_dup(directory);assert(copy>=0 && copy!=directory);
    a=pw_wine_openat(0,copy,"file",O_RDONLY);assert(a>=0);
    char content=0;assert(read(a,&content,1)==1 && content=='s');assert(!pw_wine_close(a));
    a=pw_wine_openat(0,AT_FDCWD,"file",O_RDONLY);assert(a>=0);
    assert(read(a,&content,1)==1 && content=='c');assert(!pw_wine_close(a));
    assert(pw_wine_openat(0,-1,"file",O_RDONLY)==-1 && errno==EBADF);
    DIR *stream=pw_wine_fdopendir(copy);assert(stream && pw_wine_dirfd(stream)==copy);
    int found=0;struct dirent *entry;errno=0;
    while((entry=pw_wine_readdir(stream))) if(!strcmp(entry->d_name,"file")) found++;
    assert(errno==0 && found==1);pw_wine_rewinddir(stream);found=0;
    while((entry=pw_wine_readdir(stream))) if(!strcmp(entry->d_name,"file")) found++;
    assert(found==1 && !pw_wine_closedir(stream));
    assert(pw_wine_fchdir(0,copy)==-1 && errno==EBADF);
    assert(pw_wine_rename(0,"../server/sub","../server/moved")==-1 && errno==ENOTSUP);
    assert(!pw_wine_fchdir(0,directory));
    assert(pw_wine_getcwd(0,cwd,sizeof(cwd)) && !strcmp(cwd,server));
    assert(!pw_wine_close(directory));assert(pw_wine_fchdir(0,directory)==-1 && errno==EBADF);
    a=pw_wine_open(0,"file",O_RDONLY);assert(a>=0);
    assert(pw_wine_fchdir(0,a)==-1 && errno==ENOTDIR);assert(!pw_wine_close(a));
    assert(!pw_wine_unlink(0,"file"));
    assert(pw_wine_unlink(0,"sub/../file")==-1 && errno==ENOENT);
    assert(!unlink(link) && !unlink(cycle1) && !unlink(cycle2));
    snprintf(expected,sizeof(expected),"%s/client/file",root);assert(!unlink(expected));
    assert(!rmdir(sub) && !rmdir(server) && !rmdir(client) && !rmdir(root));
    puts("{\"status\":\"passed\",\"environment\":\"host path algorithms, not PS4 ABI\",\"sanitizers\":[\"ASan\",\"UBSan\",\"leaks\"]}");
}
