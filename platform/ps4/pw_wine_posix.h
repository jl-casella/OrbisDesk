/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_WINE_POSIX_H
#define PW_WINE_POSIX_H
/* Forced before Wine units; configure must still precede system headers. */
#include "config.h"
#include <sys/stat.h>
#include <signal.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
/* W048: the SDK's <time.h> carries Linux clock numbers, which the console's kernel reads
 * with FreeBSD's meaning. CLOCK_REALTIME_COARSE (5) is FreeBSD's CLOCK_UPTIME: Wine
 * preferred it for NtQuerySystemTime and showed time since boot (9:11 PM at 2:30 AM).
 * CLOCK_REALTIME (0) is the same number on both. CLOCK_MONOTONIC_RAW (4), which Wine
 * uses for its counters, is FreeBSD's CLOCK_MONOTONIC. */
#include <time.h>
#undef CLOCK_REALTIME_COARSE
#include "pw_wine_platform.h"
#include "pw_wine_fs.h"
#include "pw_wine_net.h"
int pw_wine_sigaction(int,const struct sigaction *,struct sigaction *);
int pw_wine_sigprocmask(int,const sigset_t *,sigset_t *);
int pw_wine_pthread_sigmask(int,const sigset_t *,sigset_t *);
int pw_wine_sigaltstack(const stack_t *,stack_t *);
#ifdef PW_WINE_SERVER_SIDE
#define PW_WINE_SIDE 1
#else
#define PW_WINE_SIDE 0
#endif
#define stat(path,buffer) pw_wine_path_stat(PW_WINE_SIDE,path,buffer,1)
#define fstat(fd,buffer) pw_wine_fstat(fd,buffer)
#define lstat(path,buffer) pw_wine_path_stat(PW_WINE_SIDE,path,buffer,0)
#define open(...) pw_wine_open(PW_WINE_SIDE,__VA_ARGS__)
#define openat(fd,path,flags,...) pw_wine_openat(PW_WINE_SIDE,fd,path,flags,##__VA_ARGS__)
/* W050: Wine resolves a drive root (and some directory entries) only through fstatat */
#define fstatat(fd,path,buffer,flags) pw_wine_fstatat(PW_WINE_SIDE,fd,path,buffer,flags)
#define dup(fd) pw_wine_dup(fd)
#define opendir(path) pw_wine_opendir(PW_WINE_SIDE,path)
#define fdopendir(fd) pw_wine_fdopendir(fd)
#define readdir(directory) pw_wine_readdir(directory)
#define closedir(directory) pw_wine_closedir(directory)
#define rewinddir(directory) pw_wine_rewinddir(directory)
#define dirfd(directory) pw_wine_dirfd(directory)
#define sysconf(name) pw_wine_sysconf(name)
#define close(fd) pw_wine_close(fd)
#define chdir(path) pw_wine_chdir(PW_WINE_SIDE,path)
#define fchdir(fd) pw_wine_fchdir(PW_WINE_SIDE,fd)
#define getcwd(buffer,bytes) pw_wine_getcwd(PW_WINE_SIDE,buffer,bytes)
#define mkdir(path,mode) pw_wine_mkdir(PW_WINE_SIDE,path,mode)
#define unlink(path) pw_wine_unlink(PW_WINE_SIDE,path)
#define rmdir(path) pw_wine_rmdir(PW_WINE_SIDE,path)
#define rename(old,new) pw_wine_rename(PW_WINE_SIDE,old,new)
#define access(path,mode) pw_wine_access(PW_WINE_SIDE,path,mode)
#define fopen(path,mode) pw_wine_fopen(PW_WINE_SIDE,path,mode)
#define realpath(path,buffer) pw_wine_realpath(PW_WINE_SIDE,path,buffer)
#define poll(fds,count,timeout) pw_wine_poll(fds,count,timeout)
#define sendmsg(fd,message,flags) pw_wine_sendmsg(fd,message,flags)
#define recvmsg(fd,message,flags) pw_wine_recvmsg(fd,message,flags)
#define sigaction(signal,action,old) pw_wine_sigaction(signal,action,old)
#define sigprocmask(how,set,old) pw_wine_sigprocmask(how,set,old)
#define pthread_sigmask(how,set,old) pw_wine_pthread_sigmask(how,set,old)
#define sigaltstack(stack,old) pw_wine_sigaltstack(stack,old)
#undef sa_sigaction
#define sa_sigaction __sa_handler.__sa_sigaction
#undef sa_handler
#define sa_handler __sa_handler.sa_handler
#endif
