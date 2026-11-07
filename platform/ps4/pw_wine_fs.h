/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_WINE_FS_H
#define PW_WINE_FS_H
#include <sys/stat.h>
#include <stdio.h>
#include <dirent.h>
int pw_wine_chdir(int,const char *);
int pw_wine_fchdir(int,int);
char *pw_wine_getcwd(int,char *,size_t);
int pw_wine_open(int,const char *,int,...);
int pw_wine_openat(int,int,const char *,int,...);
int pw_wine_fstatat(int,int,const char *,struct stat *,int);
int pw_wine_dup(int);
int pw_wine_close(int);
int pw_wine_path_stat(int,const char *,struct stat *,int);
int pw_wine_mkdir(int,const char *,mode_t);
int pw_wine_unlink(int,const char *);
int pw_wine_rmdir(int,const char *);
int pw_wine_rename(int,const char *,const char *);
int pw_wine_access(int,const char *,int);
FILE *pw_wine_fopen(int,const char *,const char *);
char *pw_wine_realpath(int,const char *,char *);
DIR *pw_wine_opendir(int,const char *);
DIR *pw_wine_fdopendir(int);
struct dirent *pw_wine_readdir(DIR *);
int pw_wine_closedir(DIR *);
void pw_wine_rewinddir(DIR *);
int pw_wine_dirfd(DIR *);
int pw_wine_fs_drive_mounts(const char *);
ssize_t pw_wine_readlink(int,const char *,char *,size_t);
#endif
