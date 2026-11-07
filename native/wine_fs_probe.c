/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "pw_wine_fs.h"
#include "pw_wine_platform.h"
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static void record(const char *name,int ok,long value)
{
    printf("PWSERVICE {\"case\":\"%s\",\"status\":\"%s\",\"observed\":%ld,\"errno\":%d}\n",
           name,ok?"passed":"blocked",value,ok?0:errno);fflush(stdout);
}
static int contents(int fd,char expected)
{
    if(fd<0) return 0;char value=0;int ok=read(fd,&value,1)==1 && value==expected;
    pw_wine_close(fd);return ok;
}
static void item_name(char name[160],int index)
{
    snprintf(name,160,"item-%02d-",index);size_t start=strlen(name);
    memset(name+start,'x',120);name[start+120]=0;
}
static int enumerate(DIR *stream)
{
    unsigned long long seen=0;struct dirent *entry;int file=0,empty=0,ok=1;errno=0;
    while((entry=pw_wine_readdir(stream))) {
        if(!strcmp(entry->d_name,"MixedCase.txt")) file++;
        else if(!strcmp(entry->d_name,"empty")) empty++;
        else if(!strncmp(entry->d_name,"item-",5)) {
            int index=atoi(entry->d_name+5);char expected[160];item_name(expected,index);
            if(index<0 || index>=40 || strcmp(entry->d_name,expected) || (seen&(1ull<<index))) ok=0;
            else seen|=1ull<<index;
        }
    }
    return ok && !errno && seen==((1ull<<40)-1) && file==1 && empty==1;
}
static int empty_directory(DIR *stream)
{
    if(!stream) return 0;struct dirent *entry;errno=0;
    while((entry=pw_wine_readdir(stream)))
        if(strcmp(entry->d_name,".") && strcmp(entry->d_name,"..")) return 0;
    return !errno;
}
int pw_wine_boot_fs_services(void)
{
    int all=1,ok=1;const char *root="/data/fs-services";
    ok=!pw_wine_mkdir(0,root,0700) && !pw_wine_mkdir(0,"/data/fs-services/client",0700) &&
       !pw_wine_mkdir(0,"/data/fs-services/server",0700) &&
       !pw_wine_chdir(0,"/data/fs-services/client") && !pw_wine_chdir(1,"/data/fs-services/server") &&
       !pw_wine_mkdir(0,"empty",0700);
    int fd=ok?pw_wine_open(0,"MixedCase.txt",O_CREAT|O_TRUNC|O_RDWR,0600):-1;
    ok=ok && fd>=0 && write(fd,"C",1)==1;if(fd>=0) pw_wine_close(fd);
    fd=ok?pw_wine_open(1,"MixedCase.txt",O_CREAT|O_TRUNC|O_RDWR,0600):-1;
    ok=ok && fd>=0 && write(fd,"S",1)==1;if(fd>=0) pw_wine_close(fd);
    record("fs-fixtures",ok,ok);if(!ok) return 92;
    int directory=pw_wine_open(0,".",O_RDONLY|O_DIRECTORY);
    ok=directory>=3 && contents(pw_wine_openat(1,directory,"MixedCase.txt",O_RDONLY),'C') &&
       contents(pw_wine_openat(1,AT_FDCWD,"MixedCase.txt",O_RDONLY),'S') &&
       contents(pw_wine_openat(0,-123,"/data/fs-services/server/MixedCase.txt",O_RDONLY),'S');
    record("fs-openat-namespaces",ok,directory);all&=ok;
    int copy=directory>=3?pw_wine_dup(directory):-1;
    if(directory>=3) pw_wine_close(directory);
    ok=copy>=3 && contents(pw_wine_openat(0,copy,"MixedCase.txt",O_RDONLY),'C');
    record("fs-openat-duplicate",ok,copy);all&=ok;
    if(copy>=3) pw_wine_close(copy);
    errno=0;ok=pw_wine_openat(0,-123,"file",O_RDONLY)==-1 && errno==EBADF;
    fd=pw_wine_open(0,"MixedCase.txt",O_RDONLY);
    errno=0;ok=ok && fd>=3 && pw_wine_openat(0,fd,"file",O_RDONLY)==-1 && errno==ENOTDIR;
    errno=0;ok=ok && !pw_wine_fdopendir(fd) && errno==ENOTDIR;
    ok=contents(fd,'C') && ok;
    errno=0;ok=ok && pw_wine_openat(0,AT_FDCWD,NULL,O_RDONLY)==-1 && errno==EFAULT;
    errno=0;ok=ok && pw_wine_openat(0,AT_FDCWD,"",O_RDONLY)==-1 && errno==ENOENT;
    record("fs-invalid-paths-ownership",ok,ok);all&=ok;
    int raw=open("/data/fs-services/client",O_RDONLY|O_DIRECTORY);
    errno=0;ok=raw>=3 && pw_wine_openat(0,raw,"MixedCase.txt",O_RDONLY)==-1 && errno==ENOTSUP;
    if(raw>=3) close(raw);record("fs-untracked-dirfd-rejected",ok,ok);all&=ok;
    int created=0;
    for(;created<40;created++) {
        char name[160];item_name(name,created);fd=pw_wine_open(0,name,O_CREAT|O_EXCL|O_RDWR,0600);
        if(fd<0) break;pw_wine_close(fd);
    }
    DIR *stream=created==40?pw_wine_opendir(0,"."):NULL;
    ok=stream && enumerate(stream);record("fs-directory-pages",ok,created);all&=ok;
    if(stream) {errno=0;pw_wine_rewinddir(stream);ok=!errno && enumerate(stream);}
    else ok=0;
    record("fs-directory-rewind",ok,ok);all&=ok;
    int previous=stream?pw_wine_dirfd(stream):-1;
    if(stream) pw_wine_closedir(stream);
    directory=pw_wine_open(1,".",O_RDONLY|O_DIRECTORY);
    ok=directory>=3 && directory==previous && contents(pw_wine_openat(0,directory,"MixedCase.txt",O_RDONLY),'S');
    record("fs-directory-close-reuse",ok,directory);all&=ok;
    if(directory>=3) pw_wine_close(directory);
    stream=pw_wine_opendir(0,"empty");errno=0;
    ok=empty_directory(stream);
    if(stream) {pw_wine_rewinddir(stream);ok=ok && !errno && empty_directory(stream);pw_wine_closedir(stream);}
    record("fs-empty-directory",ok,ok);all&=ok;
    errno=0;ok=!pw_wine_rename(0,"empty","renamed") && !pw_wine_rename(0,"renamed","empty");
    record("fs-directory-rename",ok,ok);all&=ok;
    errno=0;long processors=pw_wine_sysconf(_SC_NPROCESSORS_ONLN);
    ok=processors==-1 && errno==ENOTSUP && pw_wine_sysconf(_SC_PAGESIZE)==16384;
    record("fs-cpu-query-error-contract",ok,processors);all&=ok;
    for(int n=0;n<created;n++) {char name[160];item_name(name,n);pw_wine_unlink(0,name);}
    pw_wine_unlink(0,"MixedCase.txt");pw_wine_unlink(1,"MixedCase.txt");pw_wine_rmdir(0,"empty");
    pw_wine_chdir(0,"/data");pw_wine_chdir(1,"/data");
    pw_wine_rmdir(0,"fs-services/client");pw_wine_rmdir(0,"fs-services/server");pw_wine_rmdir(0,"fs-services");
    return all?0:92;
}
