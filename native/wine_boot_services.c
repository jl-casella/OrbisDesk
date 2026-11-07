/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "pw_wine_platform.h"
#include "pw_wine_net.h"
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <sys/socket.h>
#include <sys/statfs.h>
#include <sys/stat.h>
#include <unistd.h>
extern int sysarch(int,void *);
static void result(const char *name,int ok,long observed)
{
    printf("PWSERVICE {\"case\":\"%s\",\"status\":\"%s\",\"observed\":%ld}\n",name,ok?"passed":"blocked",observed);
    fflush(stdout);
}
int pw_wine_boot_services(void)
{
    int fd=open("/data/boot-services.tmp",O_CREAT|O_TRUNC|O_RDWR,0600);
    if(fd<0) {result("fixture",0,errno);return 92;}
    const char text[]="abc";int fixture=write(fd,text,3)==3 && lseek(fd,0,SEEK_SET)==0;
    result("fixture",fixture,fd);
    int copied=dup(fd);char a=0,b=0;struct stat st;
    int duplicate=fixture && copied>=3 && copied!=fd && !pw_wine_fstat(copied,&st) &&
        read(copied,&a,1)==1 && read(fd,&b,1)==1 && a=='a' && b=='b';
    result("dup-shared-offset",duplicate,copied);
    int descriptor_independent=0,close_survives=0;
    if(duplicate) {
        int set_original=fcntl(fd,F_SETFD,FD_CLOEXEC);
        int original_flags=fcntl(fd,F_GETFD),copy_flags=fcntl(copied,F_GETFD);
        descriptor_independent=set_original==0 && original_flags==FD_CLOEXEC && copy_flags==0;
        close(fd);fd=-1;
        char last=0;close_survives=read(copied,&last,1)==1 && last=='c';
    }
    result("dup-independent-flags",descriptor_independent,copied);
    result("dup-close-survival",close_survives,copied);
    if(copied>=3 && copied!=fd) close(copied);
    if(fd<0) fd=open("/data/boot-services.tmp",O_RDWR);
    int initial=fcntl(fd,F_GETFD),set=fcntl(fd,F_SETFD,FD_CLOEXEC),flags=fcntl(fd,F_GETFD);
    result("fcntl-cloexec",initial>=0 && set==0 && flags>=0 && (flags&FD_CLOEXEC),flags);
    struct statfs fs,before;memset(&fs,0xa5,sizeof(fs));before=fs;
    int fs_rc=fstatfs(fd,&fs);
    result("fstatfs-output",fs_rc==0 && memcmp(&fs,&before,sizeof(fs))!=0,fs_rc);
    close(fd);unlink("/data/boot-services.tmp");
    uintptr_t gs=UINTPTR_MAX;int gs_rc=sysarch(130,&gs);
    result("gs-query-output",gs_rc==0 && gs!=UINTPTR_MAX,(long)gs);
    int pair[2]={-1,-1};int paired=socketpair(AF_UNIX,SOCK_STREAM,0,pair)==0;
    int eof=0;struct pollfd pfd={0};
    if(paired && !shutdown(pair[0],SHUT_WR)) {
        pfd.fd=pair[1];pfd.events=POLLIN;
        int n=pw_wine_poll(&pfd,1,10);char byte;
        eof=n==1 && ((pfd.revents&POLLHUP) || ((pfd.revents&POLLIN) && read(pair[1],&byte,1)==0));
    }
    result("socket-poll-eof",eof,pfd.revents);
    if(paired) {close(pair[0]);close(pair[1]);}
    int pipes[2]={-123,-456};errno=0;int pipe_rc=pipe(pipes),pipe_error=errno;
    int pipe_ok=0;
    if(pipe_rc==0 && pipes[0]>=3 && pipes[1]>=3 && pipes[0]!=pipes[1]) {
        char byte=0;pipe_ok=write(pipes[1],"p",1)==1 && read(pipes[0],&byte,1)==1 && byte=='p';
        close(pipes[1]);pipe_ok=pipe_ok && read(pipes[0],&byte,1)==0;close(pipes[0]);
    }
    result("pipe-basic",pipe_ok,pipe_rc);
    result("pipe-error-contract",pipe_ok || (pipe_rc==-1 && pipe_error==EOPNOTSUPP && pipes[0]==-123 && pipes[1]==-456),pipe_error);
    return duplicate && descriptor_independent && close_survives && flags>=0 && (flags&FD_CLOEXEC) && fs_rc==0 &&
        memcmp(&fs,&before,sizeof(fs)) && gs_rc==0 && gs!=UINTPTR_MAX && eof ? 0:92;
}
