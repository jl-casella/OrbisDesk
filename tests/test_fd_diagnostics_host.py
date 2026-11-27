#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Exercise first-failure diagnostics without altering the original open result."""
import pathlib, subprocess, tempfile
r=pathlib.Path(__file__).resolve().parents[1]
s=(r/'platform/ps4/pw_wine_fs.c').read_text()
start=s.index('/* Called only at the first EMFILE/ENFILE with lock held.')
end=s.index('\nint pw_wine_open(',start)
functions=s[start:end]
code=r'''
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#define __ORBIS__ 1
enum {FD_RECORDS=8,PATH_BYTES=256};
static struct {int used,fd,directory,flags,side,duplicated;char path[PATH_BYTES];} records[FD_RECORDS];
static unsigned reports,probes,closes;static int probe_result=77;static char log_buffer[8192];static size_t log_length;
static int capture(FILE *f,const char *fmt,...){va_list ap;va_start(ap,fmt);int n=vsnprintf(log_buffer+log_length,sizeof(log_buffer)-log_length,fmt,ap);va_end(ap);assert(n>=0);log_length+=n;return n;}
#define fprintf capture
static int fcntl_model(int fd,int cmd){assert(cmd==F_GETFD);return fd==99?-1:0;}
#define fcntl fcntl_model
static void descriptor_report(void){reports++;errno=EACCES;}
static void descriptor_growth(int fd){assert(fd>=128);}
static int sceKernelOpen(const char *p,int flags,int mode){assert(!flags && !mode && p);probes++;errno=EIO;return probe_result;}
static int sceKernelClose(int fd){assert(fd==77);closes++;return 0;}
void pw_wine_fd_cache_snapshot(unsigned *retained,unsigned *peak,unsigned *bypasses,unsigned *limit){*retained=41;*peak=57;*bypasses=0;*limit=64;}
''' + functions + r'''
int main(void){
 records[0].used=1;records[0].fd=3;records[0].side=1;strcpy(records[0].path,"/data/orbisdesk/steam-games/12210/GTAIV/map.img");
 records[1].used=1;records[1].fd=4;records[1].duplicated=1;strcpy(records[1].path,"/data/wine-prefix/.wineserver/ipc");
 records[2].used=1;records[2].fd=99;
 errno=EMFILE;open_trace(1,"/data/game/map.img",O_RDONLY|O_DIRECTORY,-1);
 assert(errno==EMFILE && reports==1 && probes==1 && closes==1);
 assert(strstr(log_buffer,"tracked=3/8 live=2 unqueryable=1 origin_client=1 origin_server=1 dup_records=1 game=1 ipc_files=1"));
 assert(strstr(log_buffer,"retained=41 peak=57 budget_bypasses=0 limit=64"));
 assert(strstr(log_buffer,"kernel_open_control flags=0 result=0x4d close_rc=0"));
 // Repeated failures remain errors, but do not repeatedly scan or probe the kernel.
 for(int i=0;i<32;i++){errno=EMFILE;open_trace(1,"/data/game/map.img",O_RDONLY,-1);assert(errno==EMFILE);}
 assert(reports==1 && probes==1 && closes==1);
 // Explicitly prove the control never repeats creation/truncation flags.
 probe_result=(int)0x80020018;descriptor_pressure("/data/not-created",0,O_CREAT|O_TRUNC|O_WRONLY);
 assert(probes==2 && closes==1);
 assert(records[0].used && records[1].used && records[2].used);
 puts("PASS: first-failure resource census, cache snapshot, read-only kernel control, errno preserved, no application descriptor closed");
}
'''
with tempfile.TemporaryDirectory() as tmp:
 p=pathlib.Path(tmp);(p/'check.c').write_text(code)
 subprocess.run(['cc','-std=gnu11','-O1','-g','-fsanitize=address,undefined','-no-pie',str(p/'check.c'),'-o',str(p/'check')],check=True)
 subprocess.run([str(p/'check')],check=True)
