/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "pw_wine_fs.h"
#include "pw_wine_platform.h"
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
static void record(const char *name,int ok,long value)
{
    printf("PWSERVICE {\"case\":\"%s\",\"status\":\"%s\",\"observed\":%ld,\"errno\":%d}\n",
           name,ok?"passed":"blocked",value,ok?0:errno);fflush(stdout);
}
static int same(const struct stat *a,const struct stat *b)
{return a->st_ino && a->st_ino==b->st_ino && a->st_dev==b->st_dev;}
int pw_wine_boot_metadata_services(void)
{
    struct stat file={0},hard={0},other={0},link={0},target={0},opened={0},before;
    int all=1,ok=!pw_wine_stat("/data/metadata/sample.bin",&file) &&
        !pw_wine_stat("/data/metadata/hard.bin",&hard) && !pw_wine_stat("/data/metadata/other.bin",&other) &&
        S_ISREG(file.st_mode) && file.st_size==7 && same(&file,&hard) && !same(&file,&other) && file.st_nlink>=2;
    record("metadata-file-identity",ok,(long)file.st_ino);all&=ok;
    int fd=open("/data/metadata/sample.bin",O_RDONLY);
    ok=fd>=3 && !pw_wine_fstat(fd,&opened) && same(&file,&opened) && opened.st_size==7;
    record("metadata-stat-fstat",ok,fd);all&=ok;
    ok=!pw_wine_lstat("/data/metadata/file-link",&link) && S_ISLNK(link.st_mode) &&
       !pw_wine_stat("/data/metadata/file-link",&target) && same(&file,&target) && !same(&file,&link);
    record("metadata-link-follow",ok,(long)link.st_size);all&=ok;
    char buffer[64];memset(buffer,0x5a,sizeof(buffer));
    ssize_t length=readlink("/data/metadata/file-link",buffer,sizeof(buffer));
    ok=length==10 && !memcmp(buffer,"sample.bin",10) && buffer[10]==0x5a;
    memset(buffer,0x5a,sizeof(buffer));ssize_t partial=readlink("/data/metadata/file-link",buffer,3);
    ok=ok && partial==3 && !memcmp(buffer,"sam",3) && buffer[3]==0x5a;
    record("metadata-readlink-bounds",ok,length);all&=ok;
    memset(&before,0xa5,sizeof(before));target=before;errno=0;
    ok=!pw_wine_lstat("/data/metadata/dangling",&link) && S_ISLNK(link.st_mode) &&
       pw_wine_stat("/data/metadata/dangling",&target)==-1 && errno==ENOENT &&
       !memcmp(&before,&target,sizeof(before));
    record("metadata-dangling-link",ok,ok);all&=ok;
    memset(buffer,0x5a,sizeof(buffer));errno=0;
    ok=readlink("/data/metadata/sample.bin",buffer,sizeof(buffer))==-1 && errno==EINVAL && buffer[0]==0x5a;
    errno=0;ok=ok && readlink("/data/metadata/file-link",NULL,3)==-1 && errno==EFAULT;
    errno=0;ok=ok && readlink("/data/metadata/file-link",buffer,0)==-1 && errno==EINVAL;
    record("metadata-readlink-errors",ok,ok);all&=ok;
    int directory=open("/data/metadata/dir",O_RDONLY|O_DIRECTORY);char canonical[4096];
    ok=directory>=3 && !pw_wine_fstat(directory,&opened) && S_ISDIR(opened.st_mode) &&
       !pw_wine_stat("/data/metadata/dir-link",&target) && same(&opened,&target) &&
       pw_wine_realpath(0,"/data/metadata/dir-link",canonical) && !strcmp(canonical,"/data/metadata/dir");
    record("metadata-directory-identity",ok,directory);all&=ok;
    int renamed=rename("/data/metadata/sample.bin","/data/metadata/renamed.bin");
    ok=fd>=3 && !renamed && !pw_wine_fstat(fd,&opened) && same(&opened,&file) &&
       !pw_wine_stat("/data/metadata/renamed.bin",&target) && same(&opened,&target);
    record("metadata-open-file-rename",ok,renamed);all&=ok;
    if(fd>=3) close(fd);
    renamed=rename("/data/metadata/dir","/data/metadata/renamed-dir");
    ok=directory>=3 && !renamed && !pw_wine_fstat(directory,&opened) &&
       !pw_wine_stat("/data/metadata/renamed-dir",&target) && same(&opened,&target);
    record("metadata-open-directory-rename",ok,renamed);all&=ok;
    if(directory>=3) close(directory);
    return all?0:92;
}
